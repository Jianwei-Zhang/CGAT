"""Deferred checks only: not executed during the implementation phase.

The optional native oracle requires CGAT_MINIMAP2_NATIVE_SOURCE pointing to an
unmodified v2.31 source checkout. It builds a private copy OUTSIDE the checkout,
not the installed tool or the customer workspace. Do not enable until the user
opens final validation. Merely adding these cases does not establish a pass.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

import post_dp_selection as ps
from windowed_alignment import ExperimentError


def state(key, **updates):
    values = dict(key=key, query_start=0, query_end=1000, target_id=0,
                  target_start=0, target_end=1000, reverse=False,
                  chain_score=10000, original_chain_score=10000, anchor_count=100,
                  matches=1000, block_length=1000, dp_max=10000,
                  previous_subscore=0, previous_subcount=0, previous_dp_max2=0,
                  native_hash=0)
    values.update(updates)
    return ps.NativePostDpState(**values)


def retained(report):
    return {row["state"]["key"]: row for row in report["retained_candidates"]}


class PostDpSelectionTests(unittest.TestCase):
    def test_decoy_rejected_by_chain_score_not_dp_score_and_prior_subsc_kept(self):
        rows = [state("exact", query_end=200000, target_end=200000,
                      chain_score=199976, original_chain_score=199976, anchor_count=19986,
                      matches=200000, block_length=200000, dp_max=200000,
                      previous_subscore=160915),
                state("head", target_id=1, query_end=185000, target_end=185000,
                      chain_score=146016, original_chain_score=160915, anchor_count=12927,
                      matches=160340, block_length=185000, dp_max=160340),
                state("tail", target_id=1, query_start=187000, query_end=200000,
                      target_start=187000, target_end=200000, chain_score=14899,
                      original_chain_score=160915, anchor_count=1319,
                      matches=13000, block_length=13000, dp_max=13000)]
        report = ps.replay_post_dp_selection(rows, query_length=200000)
        self.assertEqual(list(retained(report)), ["exact"])
        self.assertEqual(retained(report)["exact"]["subscore"], 160915)
        self.assertEqual(retained(report)["exact"]["dp_max2"], 160340)
        self.assertFalse(report["mapq_reconstructed"])
        self.assertFalse(report["production_ready"])

    def test_target_and_strand_do_not_partition_primary_competition(self):
        report = ps.replay_post_dp_selection([state("p"), state("s", target_id=1,
            reverse=True, dp_max=9000, chain_score=9000)], query_length=1000)
        self.assertEqual(retained(report)["s"]["parent"], retained(report)["p"]["id"])
        self.assertFalse(retained(report)["s"]["sam_primary"])

    def test_primary_coverage_is_union_over_all_current_primaries(self):
        a = state("a", query_end=100, dp_max=3000)
        b = state("b", query_start=100, query_end=200, dp_max=2000, target_id=1)
        c = state("c", query_end=200, dp_max=1000, target_id=2)
        alone = retained(ps.replay_post_dp_selection([a,c],query_length=1000))
        together = retained(ps.replay_post_dp_selection([a,b,c],query_length=1000))
        self.assertEqual(alone["c"]["parent"],alone["c"]["id"])
        self.assertEqual(together["c"]["parent"],together["a"]["id"])

    def test_identical_hit_suppression_does_not_compare_strand(self):
        rows = [state("p", previous_dp_max2=17), state("duplicate", reverse=True, dp_max=9000)]
        report = ps.replay_post_dp_selection(rows, query_length=1000)
        self.assertEqual(list(retained(report)),["p"])
        self.assertEqual(retained(report)["p"]["dp_max2"],17)
        self.assertEqual(retained(report)["p"]["subcount"],1)
        self.assertEqual(report["decisions"][1]["reason"],"identical_hit")

    def test_nested_query_same_target_extent_excludes_dp_max2_not_row(self):
        rows = [state("p", previous_dp_max2=17),
                state("nested", query_start=10, query_end=990, dp_max=9000)]
        report = ps.replay_post_dp_selection(rows,query_length=1000)
        self.assertEqual(len(retained(report)),2)
        self.assertEqual(retained(report)["p"]["dp_max2"],17)

    def test_first_primary_retains_prior_counter_other_primary_resets_only_counter(self):
        rows = [state("a", query_end=400, previous_subcount=7, previous_subscore=123),
                state("b", query_start=600, dp_max=9000, previous_subcount=9,
                      previous_subscore=456, previous_dp_max2=789)]
        result = retained(ps.replay_post_dp_selection(rows,query_length=1000))
        self.assertEqual(result["a"]["subcount"],7)
        self.assertEqual(result["b"]["subcount"],0)
        self.assertEqual(result["b"]["subscore"],456)
        self.assertEqual(result["b"]["dp_max2"],789)
        self.assertTrue(result["a"]["sam_primary"])
        self.assertFalse(result["b"]["sam_primary"])

    def test_dp_difference_or_seed_count_updates_subcounter(self):
        for updates in ({"dp_max":9995,"anchor_count":10},
                        {"dp_max":3000,"anchor_count":100}):
            with self.subTest(updates=updates):
                rows = [state("p"),state("s",target_id=1,**updates)]
                result = retained(ps.replay_post_dp_selection(rows,query_length=1000))
                self.assertEqual(result["p"]["subcount"],1)
        rows = [state("p"),state("s",target_id=1,dp_max=3000,anchor_count=99)]
        self.assertEqual(retained(ps.replay_post_dp_selection(rows,query_length=1000))["p"]["subcount"],0)

    def test_secondary_limit_is_global_not_per_primary(self):
        rows = [state("a", query_end=400, dp_max=100000),
                state("b", query_start=600, dp_max=99000)]
        for i in range(52):
            rows.append(state(f"s{i}",target_id=i+1,query_start=0 if i%2==0 else 600,
                query_end=400 if i%2==0 else 1000,chain_score=9000,dp_max=1000,native_hash=i))
        report = ps.replay_post_dp_selection(rows,query_length=1000)
        self.assertEqual(report["secondary_count"],50)
        self.assertEqual(len(retained(report)),52)
        self.assertEqual(sum(d["reason"]=="secondary_limit" for d in report["decisions"]),2)

    def test_large_float_comparison_rounds_both_integer_operands(self):
        rows = [state("p",query_end=200000000,target_end=200000000,
                      chain_score=100000001,original_chain_score=100000001,dp_max=200000000),
                state("s",target_id=1,query_end=200000000,target_end=200000000,
                      chain_score=79999999,original_chain_score=79999999,dp_max=199999999)]
        report = ps.replay_post_dp_selection(rows,query_length=200000000)
        self.assertIn("s",retained(report))

    def test_small_exact_sort_tie_reverses_original_order(self):
        rows = [state("a"),state("b",target_id=1),state("c",target_id=2)]
        report = ps.replay_post_dp_selection(rows,query_length=1000)
        self.assertEqual([d["candidate"] for d in report["decisions"]],["c","b","a"])

    def test_no_input_mutation_no_defaulted_native_metadata_and_no_paf_adapter(self):
        rows = [state("a"),state("b",target_id=1)]
        before = [asdict(r) for r in rows]
        ps.replay_post_dp_selection(rows,query_length=1000)
        self.assertEqual([asdict(r) for r in rows],before)
        with self.assertRaises(ExperimentError):
            ps.replay_post_dp_selection([asdict(rows[0])],query_length=1000)
        with self.assertRaises(TypeError):
            ps.NativePostDpState(key="no native state")
        for updates in ({"anchor_count":2},{"dp_max":199},{"native_hash":-1},
                        {"chain_score":ps.INT_MAX},{"reverse":1}):
            with self.subTest(updates=updates),self.assertRaises(ExperimentError):
                ps.replay_post_dp_selection([replace(rows[0],**updates)],query_length=1000)


class NativeSourceOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("CGAT_MINIMAP2_NATIVE_SOURCE")
        if not source:
            raise unittest.SkipTest("deferred native oracle: explicit unmodified source path required")
        source = Path(source).resolve()
        for name, expected in ps.UPSTREAM.items():
            if name == "version":
                continue
            file = name.removesuffix("_sha256")
            if hashlib.sha256((source/file).read_bytes()).hexdigest() != expected:
                raise AssertionError(f"native oracle source identity mismatch: {file}")
        cls.tmp = tempfile.TemporaryDirectory(prefix="cgat-post-dp-native-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        copied = cls.root/"minimap2-source"
        # Avoid stale .o/.a and do not write to the provided checkout.
        shutil.copytree(source,copied,ignore=shutil.ignore_patterns(".git","*.o","*.a","minimap2"))
        subprocess.run(["make","-C",str(copied),"-j2","libminimap2.a"],check=True,
                       capture_output=True,timeout=180)
        cls.exe = cls.root/"post-dp-native-oracle"
        subprocess.run(["cc","-O2","-ffp-contract=off","-I",str(copied),
                        str(Path(__file__).with_name("post_dp_native_oracle.c")),
                        str(copied/"libminimap2.a"),"-lz","-lm","-lpthread","-o",str(cls.exe)],
                       check=True,capture_output=True,timeout=60)

    def compare_native(self,rows):
        keys = ("query_start","query_end","target_id","target_start","target_end","reverse",
                "chain_score","original_chain_score","anchor_count","matches","block_length",
                "dp_max","previous_subscore","previous_subcount","previous_dp_max2","native_hash")
        text = str(len(rows))+"\n"+"".join(" ".join(str(int(getattr(r,k))) for k in keys)+"\n" for r in rows)
        # Validate before native input; the oracle's C parser is not a public API.
        report = ps.replay_post_dp_selection(rows,query_length=2000000000)
        completed = subprocess.run([str(self.exe)],input=text,text=True,check=True,capture_output=True,timeout=30)
        lines = completed.stdout.splitlines()
        actual = [tuple(map(int,line.split())) for line in lines[1:]]
        self.assertEqual(int(lines[0]),len(actual))
        original = {r.key:i for i,r in enumerate(rows)}
        expected = [(original[r["state"]["key"]],r["id"],r["parent"],r["subscore"],
                     r["subcount"],r["dp_max2"],int(r["sam_primary"])) for r in report["retained_candidates"]]
        self.assertEqual(actual,expected)

    def test_large_ties_both_strands_prior_state_and_float_boundaries(self):
        rng = random.Random(2311302)
        for count in (0,1,2,63,64,65,100,257,600):
            rows = []
            for i in range(count):
                start = rng.randrange(0,8)*100
                rows.append(state(str(i),query_start=start,query_end=start+rng.randrange(2,9)*100,
                    target_id=i%9,reverse=bool(i%2),chain_score=rng.choice((600,800,1000,79999999,100000001)),
                    anchor_count=rng.randrange(3,200),dp_max=rng.choice((800,1000,100000000)),
                    native_hash=rng.choice((0,0,5,2**32-1)),previous_subcount=i%4,
                    previous_subscore=i%5,previous_dp_max2=i%3))
            with self.subTest(count=count):
                self.compare_native(rows)


if __name__ == "__main__":
    unittest.main()
