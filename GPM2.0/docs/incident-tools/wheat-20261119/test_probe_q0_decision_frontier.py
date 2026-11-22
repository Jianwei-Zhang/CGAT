from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import probe_q0_decision_frontier as probe
from lgz_core.q0_admission import EvidenceInput
from lgz_core.q0_preparation import MANIFEST, identity
from lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey
from server.tests.test_q0_admission import bridge_fixture


class DecisionFrontierTests(unittest.TestCase):
    def test_unknown_gap_retains_correct_sides_of_reverse_slice(self):
        x, y, z = (SourceKey("dataset", name) for name in ("x", "y", "z"))
        slices = [SimpleNamespace(placement_id=str(i), source=s, orientation=d, interval=Interval(100, 200))
                  for i, (s, d) in enumerate(((x, "+"), (y, "-"), (z, "+")))]
        placements = [SimpleNamespace(**{**vars(s), "interval": Interval(90, 210)}) for s in slices]
        path = SimpleNamespace(slices=slices, joins=[SimpleNamespace(kind="reference_unknown"),
                                                    SimpleNamespace(kind="sequence_overlap")])
        c = SimpleNamespace(paths={"chr": SimpleNamespace(path=path)},
                            admission=SimpleNamespace(placements=placements))
        self.assertEqual(probe.decision_frontier(c, 5), {
            x: (Interval(95, 105), Interval(195, 205)),
            y: (Interval(195, 205),), z: (Interval(195, 205),)})

    def test_target_only_input_retained_with_source_offset_and_no_projection_lookahead(self):
        q, t = (SourceKey("dataset", name) for name in ("q", "t"))
        parts = {"q": SimpleNamespace(source=q, interval=Interval(100, 200)),
                 "t": SimpleNamespace(source=t, interval=Interval(500, 600))}
        def row(k):
            return {"segment_id": k, "segment_length": 100, "start": 10, "end": 80}
        task = {"query_ids": ["q"], "target_ids": ["t"]}
        spec = {"query": row("q"), "targets": [row("t")], "raw_receipt": {"path": "raw"},
                "context": {"path": "context"}}
        r = probe.projected_task(task, spec, parts, {q: (Interval(180, 200),), t: (Interval(540, 541),)})
        self.assertEqual(r, {"query": False, "target": True, "query_bp": 70, "target_bp": 70,
                             "raw": "raw", "context": "context"})
        with self.assertRaises(Q0EvidenceError):
            probe.projected_task({**task, "target_ids": []}, spec, parts, {})

    def test_skipped_projection_does_not_claim_shared_raw_work_was_skipped(self):
        q, t = (SourceKey("dataset", label) for label in ("query", "target"))
        parts = {"q": SimpleNamespace(source=q, interval=Interval(0, 1000)),
                 "t": SimpleNamespace(source=t, interval=Interval(0, 1000))}
        rows = ((0, "raw-a"), (100, "raw-a"), (200, "raw-b"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks, output_ids = [], {}
            for n, (start, raw) in enumerate(rows):
                name = f"{n}.json"
                def coord(seg):
                    return {"segment_id": seg, "segment_length": 1000, "start": start, "end": start + 10}
                spec = {"query": coord("q"), "targets": [coord("t")],
                        "raw_receipt": {"path": raw}, "context": {"path": raw + "-ctx"}}
                (root / name).write_text(json.dumps({"spec": spec}))
                output_ids[name] = identity(root, name)
                tasks.append({"receipt": name, "paf": f"{n}.paf", "kind": "regional_discovery",
                              "query_ids": ["q"], "target_ids": ["t"]})
            data = SimpleNamespace(parts=parts, catalog={"supplementary_alignments": tasks})
            full, keep, counts = probe.task_plan(root, data, {q: (Interval(0, 5),)}, output_ids)
            self.assertEqual(full, {"0.paf", "1.paf", "2.paf"})
            self.assertEqual(keep, {"0.paf"})
            self.assertEqual(counts["unique_raw_omitted"], 1)
            self.assertEqual(counts["projected_task_query_bp_omitted"], 20)
            (root / "1.json").write_text("{}")
            with self.assertRaisesRegex(Q0EvidenceError, "no longer matches"):
                probe.task_plan(root, data, {}, output_ids)

    def test_removed_negative_or_positive_evidence_is_not_a_ready_manifest(self):
        a = SimpleNamespace(hit=SimpleNamespace(artifact="a", evidence_id="base-e"))
        b = SimpleNamespace(hit=SimpleNamespace(artifact="b", evidence_id="supp-e"))
        data = EvidenceInput({}, {}, {}, {}, (a, b), (), {"base-e": {}, "supp-e": {}, "ref-e": {}}, "input", {
            "base_alignments": [{"paf": "a"}], "supplementary_alignments": [{"paf": "b"}],
            "candidates": ["discovered-through-b"]}, "verified-id")
        base = probe.subset_input(data, set())
        self.assertEqual(base.pair_links, (a,))
        self.assertEqual(set(base.evidence), {"base-e", "ref-e"})
        self.assertEqual((base.catalog, base.ready_manifest_identity), ({}, ""))
        self.assertEqual(probe.subset_input(data, {"b"}).pair_links, (a, b))
        with self.assertRaises(Q0EvidenceError):
            probe.subset_input(data, {"rogue"})

    def test_compare_distinguishes_known_gap_from_aligned_overlap(self):
        fixture, truth = bridge_fixture(reverse=True)
        data = fixture.data()
        full = probe.construct_q0(data)
        empty = probe.construct_q0(replace(data, pair_links=()))
        row = probe.compare(full, empty)["chr1"]
        self.assertEqual(full.records["chr1"], truth)
        self.assertFalse(row["same_sequence"])
        self.assertGreater(row["changed_or_lost_overlap_cuts"], 0)
        self.assertEqual(row["changed_or_new_overlap_cuts"], 0)
        self.assertGreater(row["arm_join_kinds"]["reference_unknown"], 0)

    def test_replay_loads_a_verified_manifest_and_does_not_write(self):
        fixture, truth = bridge_fixture(reverse=True)
        fixture.reference_sequences = {"chr1": truth}
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = fixture.workspace(tmp.name)
        manifest = (root / MANIFEST).read_bytes()
        report = probe.replay(root, 100)
        self.assertEqual((root / MANIFEST).read_bytes(), manifest)
        self.assertEqual(report["projection_inventory"].get("regional_tasks", 0), 0)
        self.assertTrue(report["ready"])
        self.assertEqual(probe.replay(root, 100)["full_sequence_sha256"], report["full_sequence_sha256"])


if __name__ == "__main__":
    unittest.main()
