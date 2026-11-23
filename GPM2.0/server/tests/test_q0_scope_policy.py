import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from server.tools.lgz_core import q0_preparation as prep
from server.tools.workspace_layout import WorkspaceLayout, initialize_workspace

from server.tools.lgz_core.q0_scope_policy import (
    AUTO_SCOPE,
    FULL_SCOPE,
    PROOF_REPAIR_SCOPE,
    ScopeWorkload,
    decide_scope,
)


class AutomaticQ0ScopeTests(unittest.TestCase):
    def workload(self, **overrides):
        values = dict(
            regional_enabled=True,
            reads_qc_enabled=False,
            reference_bp=5_000_000_000,
            source_bp=2_000_000_000,
            longest_source_bp=30_000_000,
            source_count=200,
            paf_bytes=3 * 1024**3,
            base_alignment_count=20,
        )
        values.update(overrides)
        return ScopeWorkload(**values)

    def test_large_no_reads_regional_workload_selects_proof_repair(self):
        decision = decide_scope(self.workload())
        self.assertEqual(decision.requested_scope, AUTO_SCOPE)
        self.assertEqual(decision.effective_scope, PROOF_REPAIR_SCOPE)
        self.assertIn("large_paf_inventory", decision.signals)
        self.assertEqual(decision.record()["schema"], "lgz_q0_scope_decision_v1")

    def test_small_workload_stays_full(self):
        decision = decide_scope(self.workload(paf_bytes=100, source_bp=100, longest_source_bp=100,
                                              source_count=1, base_alignment_count=1))
        self.assertEqual(decision.effective_scope, FULL_SCOPE)
        self.assertEqual(decision.reason, "paf_inventory_below_complexity_gate")

    def test_nonregional_workload_stays_full_even_if_large(self):
        decision = decide_scope(self.workload(regional_enabled=False))
        self.assertEqual(decision.effective_scope, FULL_SCOPE)
        self.assertEqual(decision.reason, "regional_route_disabled")

    def test_reads_qc_or_unknown_input_fails_closed_to_full(self):
        for value in (True, None):
            with self.subTest(reads_qc_enabled=value):
                decision = decide_scope(self.workload(reads_qc_enabled=value))
                self.assertEqual(decision.effective_scope, FULL_SCOPE)
                self.assertEqual(decision.reason, "reads_qc_enabled_or_unknown")

    def test_large_paf_alone_is_not_enough(self):
        decision = decide_scope(self.workload(source_bp=10, longest_source_bp=10,
                                              source_count=1, base_alignment_count=1))
        self.assertEqual(decision.effective_scope, FULL_SCOPE)
        self.assertEqual(decision.reason, "no_independent_complexity_signal")

    def test_old_evidence_scripts_without_a_scope_keep_full_search(self):
        from server.tools import lgz_prepare_evidence as cli
        for extra, scope in (([], "full"), (["--supplement-scope", "auto"], "auto"),
                             (["--supplement-scope", "positive_threshold"], "positive_threshold")):
            with self.subTest(scope=scope), mock.patch("sys.argv", ["q0", "--server-dir", ".", *extra]), \
                    mock.patch.object(cli, "prepare_evidence") as prepare:
                cli.main()
                self.assertEqual(prepare.call_args.kwargs["supplement_scope"], scope)

    def test_invalid_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            self.workload(paf_bytes=-1)


class ScopeInventoryTests(unittest.TestCase):
    def workspace(self, root, *, numbered=False, physical=False):
        layout = initialize_workspace(root) if numbered else WorkspaceLayout.detect(root)

        def put(relative, text):
            path = layout.path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return path

        put("metadata/reference.tsv", "fasta_relpath\tfai_relpath\ndata/ref.fa\tdata/ref.fa.fai\n")
        put("metadata/datasets.tsv", "dataset_name\tfasta_relpath\tfai_relpath\nA\tdata/A.fa\tdata/A.fa.fai\n")
        put("metadata/package.tsv", "reads_qc_enabled\nfalse\n")
        put("metadata/prepare_options.tsv", "key\tvalue\nminimap_preset\tasm10\n")
        put("data/ref.fa.fai", "1A\t5000000000\nUn\t1000\n")
        put("data/A.fa.fai", "ctg\t1000000000\n")
        ref_paf = put("runs/A_vs_ref/result.paf", "abc")
        member = "runs/chr_1A/A_vs_self/result.paf"
        matrix = put(member, "012345678")
        row = {"paf": layout.relative(member) if physical else member,
               "target_dataset": "A", "query_dataset": "A"}
        descriptor = put("runs/chr_1A/q0_alignment_inputs.json", json.dumps(
            {"version": 1, "chromosome": "1A", "alignments": [row]}))
        empty = put("runs/chr_Un/q0_alignment_inputs.json", json.dumps(
            {"version": 1, "chromosome": "Un", "alignments": []}))
        put("runs/chr_ghost/retry/result.paf", "unrelated scratch output")
        put("runs/chr_ghost/q0_alignment_inputs.json", "unrelated stale descriptor")
        return ref_paf, matrix, descriptor, empty

    def test_only_declared_files_count_in_legacy_and_numbered_layouts(self):
        records = []
        real_open = Path.open

        def no_paf_open(path, *args, **kwargs):
            self.assertNotEqual(path.suffix, ".paf", "scope routing must not read PAF content")
            return real_open(path, *args, **kwargs)

        for numbered, physical in ((False, False), (True, False), (True, True)):
            with self.subTest(numbered=numbered, physical=physical), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.workspace(root, numbered=numbered, physical=physical)
                with mock.patch.object(Path, "open", no_paf_open), mock.patch.object(
                        Path, "glob", side_effect=AssertionError("scope routing must not walk runs")):
                    record = prep._automatic_scope_decision(root).record()
                self.assertEqual(record["workload"]["paf_bytes"], 12)
                self.assertEqual(record["workload"]["base_alignment_count"], 1)
                self.assertEqual(record["reason"], "paf_inventory_below_complexity_gate")
                records.append(record)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[1:], records[:2])

    def test_incomplete_or_ambiguous_metadata_falls_back_to_full(self):
        for case in ("missing_descriptor", "missing_paf", "linked_paf", "linked_descriptor",
                     "duplicate", "wrong_chromosome", "escape", "malformed_row"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                ref_paf, matrix, descriptor, empty = self.workspace(root, numbered=True)
                if case == "missing_descriptor":
                    empty.unlink()
                elif case == "missing_paf":
                    ref_paf.unlink()
                elif case == "linked_paf":
                    matrix.unlink()
                    matrix.symlink_to(ref_paf)
                elif case == "linked_descriptor":
                    target = descriptor.rename(descriptor.with_suffix(".copy"))
                    descriptor.symlink_to(target)
                else:
                    value = json.loads(descriptor.read_text())
                    if case == "duplicate":
                        value["alignments"] *= 2
                    elif case == "wrong_chromosome":
                        value["chromosome"] = "Un"
                    elif case == "escape":
                        value["alignments"][0]["paf"] = "../outside/result.paf"
                    else:
                        value["alignments"] = [None]
                    descriptor.write_text(json.dumps(value))
                decision = prep._automatic_scope_decision(root)
                self.assertEqual((decision.effective_scope, decision.reason),
                                 (FULL_SCOPE, "automatic_metadata_unavailable"))


if __name__ == "__main__":
    unittest.main()
