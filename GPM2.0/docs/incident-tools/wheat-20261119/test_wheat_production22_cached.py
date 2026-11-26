"""Small synthetic checks for the isolated validation report, never a mapper."""
import json
from pathlib import Path
import tempfile
import unittest

from lgz_core.q0_paths import PathGraph, Placement, ReferenceAnchor, RequestPathResult
from lgz_core.q0_sources import Interval, SourceKey
import wheat_production22_cached as audit


def placement():
    iv = Interval(0, 1000)
    return Placement("p", "p", SourceKey("assembly", "contig"), iv, "+", "1A",
                     (Interval(2000, 3000),), (iv,), ("ref",),
                     (ReferenceAnchor(iv, Interval(2000, 3000), "ref"),))


class AuditTests(unittest.TestCase):
    def test_source_n50_handles_empty_and_weighted_lengths(self):
        self.assertEqual(audit.n50([]), 0)
        self.assertEqual(audit.n50([5, 20, 10]), 20)

    def test_metrics_use_actual_anchors_not_carried_length(self):
        from dataclasses import replace
        p = placement()
        p = replace(p, reference_intervals=(Interval(2000, 2500),),
                    anchor_intervals=(Interval(0, 500),),
                    reference_blocks=(ReferenceAnchor(Interval(0, 500), Interval(2000, 2500), "ref"),))
        graph = PathGraph([p], (), ())
        metrics = audit.group_metrics({p.placement_id: p}, graph._score_candidate((p.placement_id,), ()))
        self.assertEqual(metrics["selected_source_bp"], 1000)
        self.assertEqual(metrics["selected_reference_bp"], 500)
        self.assertEqual(metrics["source_slice_n50"], 1000)

    def test_old_route_conflicts_use_half_open_source_intersection(self):
        p = placement()
        routes = {p.source: [(Interval(0, 200), "1A", "+"), (Interval(200, 300), "1B", "+"),
                             (Interval(300, 400), "1A", "-")]}
        rows = audit.conflict_rows(p.source, Interval(250, 350), "1A", "+", routes)
        self.assertEqual([r["bp"] for r in rows], [50, 50])
        self.assertEqual([r["category"] for r in rows], ["other_chromosome", "opposite_orientation"])
        self.assertFalse(audit.conflict_rows(p.source, Interval(0, 200), "1A", "+", routes))

    def test_checkpoint_reader_checks_complete_chain_and_kit(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner = Path(tmp)
            (owner / "selection").mkdir(); (owner / "result").mkdir()
            (owner / "kit.sha256").write_text("synthetic proof\n")
            proof = audit.sha256_file(owner / "kit.sha256")
            binding = ["whole-wheat-local-supplement-v1", audit.frozen.SN, audit.frozen.REQ,
                       audit.frozen.FINAL, proof, "evidence", 32]
            store = audit.Store(owner / "selection", binding, False)
            p = placement()
            store.save_admission(audit.admission.RequestAdmission((p,)))
            path = PathGraph([p], (), ())._score_candidate((p.placement_id,), ())
            store.save_group(1, "1A", RequestPathResult(path))
            summary = dict(kit_sha256=proof, evidence_digest="evidence", selection_chain=store.previous)
            (owner / "result/summary.json").write_text(json.dumps(summary))
            admitted, paths, _ = audit.read_selection(owner, ["1A"])
            self.assertEqual(admitted.placements, (p,)); self.assertEqual(paths["1A"], path)
            summary["selection_chain"] = "wrong"
            (owner / "result/summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "chain incomplete"):
                audit.read_selection(owner, ["1A"])
            (owner / "kit.sha256").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "kit changed"):
                audit.read_selection(owner, ["1A"])


if __name__ == "__main__":
    unittest.main()
