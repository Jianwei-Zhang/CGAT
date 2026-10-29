"""Light contracts for isolated harnesses, not full GRT/native acceptance."""
from __future__ import annotations

import copy
import argparse
from types import SimpleNamespace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import compare_grt as grt
import compare_self as self_audit
import windowed_alignment as wa

SERVER = Path(__file__).resolve().parents[2] / "server"


class DownstreamExperiments(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def aliases(self):
        source = self.root / "original.fa"
        source.write_text(">ctg2\nAAAA\n>ctg10\nAAAA\n>rc_ctg\nTTTT\n")
        definitions = self_audit.assignment_definitions(SERVER)
        _, _, mapping, _ = definitions["write_self_pair_inputs"](self.root, source)
        return mapping, self_audit.read_aliases(mapping)

    def test_window_suffix_preserves_original_no_dual_contract(self):
        _, (targets, queries) = self.aliases()
        records = {name: {"length": 100} for name in reversed(list(queries.values()))}
        windows = self_audit.canonical_windows(records, 30, 5, queries)
        self.assertEqual(len(windows), 12)
        self.assertEqual(len({w.alias for w in windows}), 12)
        for w in windows:
            for alias, original in targets.items():
                self.assertEqual(w.alias < alias, w.query.encode() < original.encode())

    def test_changed_or_ambiguous_aliases_are_rejected(self):
        mapping, _ = self.aliases()
        original = mapping.read_text()
        for changed in (original + original.splitlines()[0] + "\n",
                        original.replace("000000001", "000000004"),
                        original.replace("000000001b\tctg10", "000000001b\tother")):
            mapping.write_text(changed)
            with self.assertRaises(wa.ExperimentError):
                self_audit.read_aliases(mapping)

    def test_unknown_or_duplicate_window_mapping_rejected(self):
        for aliases in ({"a": "q", "b": "q"}, {"b": "other"}):
            with self.assertRaises(wa.ExperimentError):
                self_audit.canonical_windows({"q": {"length": 10}}, 5, 1, aliases)

    def test_self_diagonal_reverse_dual_and_unknown_rejected(self):
        path = self.root / "raw.paf"
        for q, t in (("q1", "t1"), ("q2", "t1"), ("unknown", "t2")):
            path.write_text(f"{q}\t4\t0\t4\t+\t{t}\t4\t0\t4\t4\t4\t0\tcg:Z:4=\n")
            with self.assertRaises(wa.ExperimentError):
                self_audit.validate_pairs(path, {"q1": "a", "q2": "b"}, {"t1": "a", "t2": "b"})
        path.write_text("q1\t4\t0\t4\t-\tt2\t4\t0\t4\t4\t4\t0\tcg:Z:4=\n")
        self.assertEqual(self_audit.validate_pairs(path, {"q1": "a"}, {"t1": "a", "t2": "b"}), [("a", "b", "-")])

    def test_restore_targets_preserves_reverse_coordinates_and_alternatives(self):
        source, output = self.root / "in.paf", self.root / "out.paf"
        rows = [f"a\t10\t2\t6\t-\t{target}\t12\t3\t7\t4\t4\t255\tcg:Z:4=" for target in ("tb", "tc")]
        source.write_text("\n".join(rows) + "\n")
        self_audit.restore_targets(source, output, {"ta": "a", "tb": "b", "tc": "c"}, {"a": {}})
        self.assertEqual(output.read_text(), source.read_text().replace("\ttb\t", "\tb\t").replace("\ttc\t", "\tc\t"))
        with self.assertRaises(FileExistsError):
            self_audit.restore_targets(source, output, {"ta": "a", "tb": "b", "tc": "c"}, {"a": {}})

    def test_missing_mapq_is_reported_not_promoted(self):
        path = self.root / "scores.paf"
        path.write_text("".join(f"q\t4\t0\t4\t+\tt\t4\t0\t4\t4\t4\t{score}\tcg:Z:4=\n" for score in (0, 19, 20, 60, 255)))
        summary = grt.confidence_summary(path)
        self.assertEqual(summary["numeric_mapq_ge_20"], 3)
        self.assertEqual(summary["known_mapq_ge_20"], 2)
        self.assertEqual(summary["unknown_mapq"], 1)
        self.assertEqual(summary["primary_tags"], 0)
        path.write_text(path.read_text().replace("\t255\t", "\t256\t"))
        with self.assertRaises(wa.ExperimentError):
            grt.confidence_summary(path)

    def test_final_path_projection_keeps_scientific_differences(self):
        validator = grt.load_module(SERVER / "validation/grt_formal_optimized.py", "test_formal")
        doc = {"chromosomes": [{"chr": "chr1", "q4_length": 4, "q4_sha256": "dna1", "segments": [
            {"kind": "source", "length": 4, "orientation": "+", "source": {"dataset": "assembly", "contig": "a", "start": 1, "end": 4, "orientation": "+"}}]}]}
        for field, value in (("kind", "gap"), ("length", 5), ("orientation", "-"),
                             ("source", {"dataset": "assembly", "contig": "b", "start": 1, "end": 4, "orientation": "+"})):
            changed = copy.deepcopy(doc)
            changed["chromosomes"][0]["segments"][0][field] = value
            self.assertNotEqual(validator.final_path(doc), validator.final_path(changed))
        changed = copy.deepcopy(doc)
        changed["chromosomes"][0]["q4_sha256"] = "dna2"
        self.assertNotEqual(validator.final_path(doc), validator.final_path(changed))

    def test_event_comparison_keeps_cross_gap_and_future_scientific_fields(self):
        ref = SimpleNamespace(normalize=lambda value: value)
        event = {"event_id": "e1", "run_id": "r1", "covered_object_ids": ["gap1", "gap2"],
                 "output_interval_by_object": {"gap1": [1, 5], "gap2": [8, 10]}, "source_card_key": "source1"}
        changed = {**event, "event_id": "e2", "run_id": "r2"}
        self.assertEqual(grt.event_semantics([event], ref), grt.event_semantics([changed], ref))
        for key, value in (("covered_object_ids", ["gap1"]), ("output_interval_by_object", {"gap1": [1, 6]}),
                           ("source_card_key", "source2"), ("future_scientific_field", "different")):
            changed = {**event, key: value}
            self.assertNotEqual(grt.event_semantics([event], ref), grt.event_semantics([changed], ref))

    @unittest.skipUnless(shutil.which("minimap2"), "real minimap2 unavailable")
    def test_real_repeat_competition_is_a_difference_not_an_accepted_workaround(self):
        _, references, sequences, _ = next(c for c in grt.fixtures() if c[0] == "repeat_assignment_threshold")
        target, query = self.root / "target.fa", self.root / "query.fa"
        grt.write_fasta(target, references)
        grt.write_fasta(query, sequences)
        mm, baseline = shutil.which("minimap2"), self.root / "baseline.paf"
        wa.run_command([mm, "-c", "--eqx", "-x", "asm10", "-t", "2", "-o", str(baseline), str(target), str(query)],
                       self.root, "baseline", 30, 4)
        output = self.root / "windowed"
        wa.experiment(argparse.Namespace(target=target, query=query, out=output, minimap2=mm, preset="asm10",
                                        core_bases=200_000, context_bases=10_000, threads=2, timeout=30,
                                        memory_gib=4, require_full_query_coverage=True))
        candidate = output / "stitched.experimental.paf"
        self.assertNotEqual(grt.relation_signature(baseline), grt.relation_signature(candidate))
        targets = lambda path: {line.split("\t")[5] for line in path.read_text().splitlines()}
        self.assertEqual(targets(baseline), {"chr1"})
        self.assertEqual(targets(candidate), {"chr1", "chr2"})
        self.assertFalse(json.loads((output / "experiment.json").read_text())["production_ready"])

    @unittest.skipUnless(shutil.which("minimap2"), "real minimap2 unavailable")
    def test_real_self_alias_window_and_empty_negative_control(self):
        output = self.root / "self-experiment"
        command = [sys.executable, str(Path(self_audit.__file__)), "--server-dir", str(SERVER),
                   "--minimap2", shutil.which("minimap2"), "--out", str(output)]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
        report = json.loads((output / "comparison.json").read_text())
        self.assertFalse(report["production_ready"])
        self.assertEqual(len(report["cases"]), 3)
        for case in report["cases"]:
            self.assertTrue(case["pair_sets_equal"])
            self.assertTrue(case["relation_equal"])
            self.assertEqual(case["baseline_rows"], 3)
            self.assertEqual(case["stitched_rows"], 3)
            self.assertEqual(case["naive_rows"], 0)
        original = (output / "comparison.json").read_bytes()
        retry = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(retry.returncode, 0)
        self.assertEqual(original, (output / "comparison.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
