"""Contracts for provisional guidance, NOT production DP-ranking acceptance."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import compare_grt as grt
import guided_alignment as ga
import windowed_alignment as wa


def chain(row=1, target="a", kind="P", **kw):
    return replace(ga.Chain(row, "q", 100, 0, 100, "+", target, 100, 0, 100, 60, kind, 100, 10), **kw)


def paf(target="a", qs=0, qe=100, ts=0, te=100, match=100, block=100, cigar="100=", strand="+", extra=""):
    return f"q\t100\t{qs}\t{qe}\t{strand}\t{target}\t100\t{ts}\t{te}\t{match}\t{block}\t255\tcg:Z:{cigar}{extra}\n"


class GuidanceContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def store(self, name, data):
        source = self.root / (name + ".fa")
        source.write_bytes(data)
        store = wa.FastaStore(source, self.root / (name + ".bases"))
        self.addCleanup(store.close)
        return store

    def inputs(self, query=None):
        q = self.store("query", b">q\n" + (query or b"A" * 100) + b"\n")
        t = self.store("target", b"".join(b">" + n + b"\n" + b"A"*100 + b"\n" for n in (b"a", b"b", b"c")))
        return q, t

    def select(self, rows, chains, q, t, slack=0):
        source = self.root / "stitched.paf"
        source.write_text(rows)
        return ga.select_guided(source, chains, self.root / "guided.pending.paf", self.root / "provenance.jsonl",
                                self.root / "coverage.json", q, t, slack)

    def test_chain_parser_rejects_dp_tags_duplicates_bad_identity_and_truncation(self):
        q, t = self.inputs()
        valid = "q\t100\t2\t98\t+\ta\t100\t2\t98\t96\t96\t60\ttp:A:P\ts1:i:96\tcm:i:8\n"
        path = self.root / "chains.paf"
        path.write_text(valid)
        self.assertEqual(ga.read_chains(path, q.records, t.records)[0].score, 96)
        for text in (valid.rstrip()+"\tcg:Z:96=\n", valid.rstrip()+"\tAS:i:96\n",
                     valid.rstrip()+"\ts1:i:96\n", valid.replace("tp:A:P", "tp:A:I"),
                     valid.replace("q\t", "unknown\t"), valid.replace("cm:i:8", "cm:i:0"),
                     valid.replace("\t60\t", "\t256\t"), valid.rstrip(), ""):
            path.write_text(text)
            with self.assertRaises(wa.ExperimentError):
                ga.read_chains(path, q.records, t.records)

    def test_keep_real_secondary_but_exclude_unsupported_whole_query_pair(self):
        q, t = self.inputs()
        report = self.select(paf("a")+paf("b")+paf("c"), [chain(), chain(2, "b", "S", chain_mapq=0)], q, t)
        self.assertEqual((report["kept_rows"], report["excluded_rows"]), (2, 1))
        lines = (self.root / "guided.pending.paf").read_text().splitlines()
        self.assertEqual([l.split("\t")[5] for l in lines], ["a", "b"])
        self.assertEqual({l.split("\t")[11] for l in lines}, {"255"})
        self.assertTrue(all("tp:" not in l and "AS:" not in l for l in lines))
        audit = [json.loads(l) for l in (self.root / "provenance.jsonl").read_text().splitlines()]
        self.assertEqual(audit[-1]["status"], "no_whole_query_placement_candidate")
        self.assertFalse(report["dp_ranking_reconstructed"])

    def test_secondary_candidate_loss_is_failure_not_silent_success(self):
        q, t = self.inputs()
        with self.assertRaisesRegex(wa.ExperimentError, "not completely recovered"):
            self.select(paf(), [chain(), chain(2, "b", "S")], q, t)
        self.assertFalse((self.root / "guided.pending.paf").exists())
        coverage = json.loads((self.root / "coverage.json").read_text())
        self.assertEqual(coverage[1]["uncovered_canonical_bases"], 100)

    def test_ambiguous_chain_ownership_stops(self):
        q, t = self.inputs()
        with self.assertRaisesRegex(wa.ExperimentError, "multiple whole-query"):
            self.select(paf(), [chain(), chain(2)], q, t)
        self.assertFalse((self.root / "guided.pending.paf").exists())
        self.assertIn("ambiguous_chain_ownership", (self.root / "provenance.jsonl").read_text())

    def test_unrecovered_canonical_bases_are_not_excused_as_context(self):
        q, t = self.inputs()
        with self.assertRaisesRegex(wa.ExperimentError, "not completely recovered"):
            self.select(paf(qe=40, te=40, match=40, block=40, cigar="40=") +
                        paf(qs=60, ts=60, match=40, block=40, cigar="40="), [chain()], q, t)
        row = json.loads((self.root / "coverage.json").read_text())[0]
        self.assertEqual(row["uncovered_intervals"], [[40, 60]])
        self.assertEqual(row["uncovered_canonical_bases"], 20)

    def test_n_gaps_are_visible_and_not_claimed_as_aligned_bases(self):
        q, t = self.inputs(b"A"*40+b"N"*20+b"A"*40)
        result = self.select(paf(qe=40, te=40, match=40, block=40, cigar="40=") +
                             paf(qs=60, ts=60, match=40, block=40, cigar="40="), [chain()], q, t)
        row = result["candidate_coverage"][0]
        self.assertEqual(row["query_coverage"]["covered_bases"], 80)
        self.assertEqual(row["uncovered_intervals"], [[40, 60]])
        self.assertEqual(row["uncovered_canonical_bases"], 0)

    def test_reverse_geometry_uses_oriented_query_coordinates(self):
        c = chain(strand="-", qs=20, qe=80, ts=10, te=70)
        hit = wa.Hit("q", 100, 30, 80, "-", "a", 100, 10, 60, 50, 50, 255, ((50, "="),))
        self.assertTrue(ga.compatible(hit, c, 0))
        self.assertFalse(ga.compatible(replace(hit, ts=20, te=70), c, 0))

    def test_cancelling_indels_outside_corridor_fail_instead_of_being_filtered(self):
        q, t = self.inputs()
        rows = paf(match=80, block=120, cigar="30=20I10=20D40=")
        with self.assertRaisesRegex(wa.ExperimentError, "geometry"):
            self.select(rows, [chain()], q, t, slack=10)
        self.assertFalse((self.root / "guided.pending.paf").exists())

    def test_window_scores_must_not_leak_into_guided_output(self):
        q, t = self.inputs()
        with self.assertRaisesRegex(wa.ExperimentError, "must not be inherited"):
            self.select(paf(extra="\ttp:A:P\tAS:i:100"), [chain()], q, t)

    def test_query_names_resembling_tags_are_not_removed_from_core_columns(self):
        name = "zp:Z:query"
        q = self.store("query", b">zp:Z:query\n" + b"A"*100 + b"\n")
        t = self.store("target", b">a\n" + b"A"*100 + b"\n")
        self.select(paf().replace("q\t", name+"\t", 1), [chain(query=name)], q, t)
        fields = (self.root / "guided.pending.paf").read_text().split("\t")
        self.assertEqual(fields[0], name)
        self.assertEqual(fields[5], "a")

    def test_full_coverage_is_rechecked_after_guidance_not_only_before_filtering(self):
        q, t = self.inputs()
        rows = paf(qe=50, te=50, match=50, block=50, cigar="50=") + paf("b", qs=50, ts=50, match=50, block=50, cigar="50=")
        result = self.select(rows, [chain(qe=50, te=50)], q, t)
        self.assertEqual(result["queries"]["q"]["covered_bases"], 50)
        self.assertEqual(result["targets"]["b"]["covered_bases"], 0)
        with self.assertRaisesRegex(wa.ExperimentError, "after chain guidance"):
            ga.require_full_query_coverage(result)
        self.assertFalse((self.root / "guided.experimental.paf").exists())

    def test_invalid_slack_does_not_start_an_experiment(self):
        for value in (-1, 1001):
            options = argparse.Namespace(guide_slack=value, context_bases=1000, out=self.root / "new")
            with self.assertRaisesRegex(wa.ExperimentError, "no automatic widening"):
                ga.experiment(options)
        self.assertFalse((self.root / "new").exists())

    def test_no_cigar_input_is_never_published_as_guided_alignment(self):
        q, t = self.inputs()
        with self.assertRaisesRegex(wa.ExperimentError, "CIGAR"):
            self.select(paf().replace("cg:Z:100=", "s1:i:100"), [chain()], q, t)


@unittest.skipUnless(shutil.which("minimap2"), "real minimap2 unavailable")
class RealGuidanceTests(unittest.TestCase):
    def test_repeat_counterexamples_fixed_without_losing_selected_secondaries(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mm = shutil.which("minimap2")
            wanted = {"local_repeat_competition", "repeat_assignment_threshold", "competing_targets", "reverse_indel", "gap_with_external_donor"}
            for name, refs, seqs, _ in grt.fixtures():
                if name not in wanted:
                    continue
                with self.subTest(case=name):
                    directory = root / name
                    directory.mkdir()
                    target, query = directory / "target.fa", directory / "query.fa"
                    grt.write_fasta(target, refs)
                    grt.write_fasta(query, seqs)
                    baseline = directory / "baseline.paf"
                    wa.run_command([mm, "-c", "--eqx", "-x", "asm10", "-t", "2", "-o", str(baseline), str(target), str(query)], directory, "baseline", 30, 4)
                    options = argparse.Namespace(target=target, query=query, out=directory / "guided", minimap2=mm, preset="asm10",
                                                 core_bases=200_000, context_bases=10_000, guide_slack=1000,
                                                 threads=2, timeout=30, memory_gib=4, require_full_query_coverage=False)
                    report = ga.experiment(options)
                    output = options.out / "guided.experimental.paf"
                    self.assertEqual(grt.relation_signature(baseline), grt.relation_signature(output))
                    self.assertFalse(report["production_ready"])
                    self.assertTrue(all(l.split("\t")[11] == "255" for l in output.read_text().splitlines()))
                    if "repeat" in name:
                        self.assertEqual(report["selection"]["excluded_rows"], 1)
                        self.assertNotEqual(grt.relation_signature(baseline), grt.relation_signature(Path(report["unfiltered_paf"])))
                    if name == "competing_targets":
                        self.assertEqual(report["selection"]["whole_query_candidates"], 2)
                        self.assertEqual(report["selection"]["excluded_rows"], 0)
                    with self.assertRaises(FileExistsError):
                        ga.experiment(options)

    def test_dp_split_decoy_is_refused_instead_of_borrowing_chain_confidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            import random
            rng = random.Random(29102030)
            seq = bytes(rng.choices(b"ACGT", k=200_000))
            decoy = seq[:99_000] + bytes(rng.choices(b"ACGT", k=2000)) + seq[101_000:]
            target, query = root / "target.fa", root / "query.fa"
            grt.write_fasta(target, {"exact": seq, "decoy": decoy})
            grt.write_fasta(query, {"query": seq})
            mm, baseline = shutil.which("minimap2"), root / "baseline.paf"
            wa.run_command([mm, "-c", "--eqx", "-x", "asm10", "-t", "2", "-o", str(baseline), str(target), str(query)], root, "baseline", 30, 4)
            self.assertEqual({l.split("\t")[5] for l in baseline.read_text().splitlines()}, {"exact"})
            options = argparse.Namespace(target=target, query=query, out=root / "guided", minimap2=mm, preset="asm10",
                                         core_bases=50_000, context_bases=2000, guide_slack=1000,
                                         threads=2, timeout=30, memory_gib=4, require_full_query_coverage=False)
            with self.assertRaisesRegex(wa.ExperimentError, "not completely recovered"):
                ga.experiment(options)
            rows = json.loads((options.out / "chain-coverage.json").read_text())
            self.assertEqual({r["chain"]["target"] for r in rows}, {"exact", "decoy"})
            self.assertGreater(next(r for r in rows if r["chain"]["target"] == "decoy")["uncovered_canonical_bases"], 0)
            self.assertFalse((options.out / "guided.experimental.paf").exists())
            self.assertEqual(json.loads((options.out / "guidance.json").read_text())["status"], "failed")

    def test_mutated_index_does_not_publish_final_guidance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            import random
            seq = bytes(random.Random(123).choices(b"ACGT", k=120_000))
            target, query = root / "target.fa", root / "query.fa"
            grt.write_fasta(target, {"t": seq})
            grt.write_fasta(query, {"q": seq})
            options = argparse.Namespace(target=target, query=query, out=root / "guided", minimap2=shutil.which("minimap2"), preset="asm10",
                                         core_bases=30_000, context_bases=2000, guide_slack=1000,
                                         threads=2, timeout=30, memory_gib=4, require_full_query_coverage=True)
            actual = wa.run_command
            def mutate_after_chain(command, directory, name, timeout, memory_gib):
                result = actual(command, directory, name, timeout, memory_gib)
                if name == "whole-query":
                    with (directory / "windows/target.mmi").open("ab") as handle:
                        handle.write(b"test-mutation")
                return result
            with patch.object(wa, "run_command", mutate_after_chain):
                with self.assertRaisesRegex(wa.ExperimentError, "input/index/tool changed"):
                    ga.experiment(options)
            self.assertFalse((options.out / "guided.experimental.paf").exists())
            self.assertEqual(json.loads((options.out / "guidance.json").read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
