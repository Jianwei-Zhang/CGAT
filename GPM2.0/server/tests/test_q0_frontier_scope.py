from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import os
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch

from server.tests.test_q0_admission import EvidenceFixture, bridge_fixture, dna
from server.tools.lgz_core import q0_admission, q0_preparation
from server.tools.lgz_core.q0_catalog import build_catalog
from server.tools.lgz_core.q0_frontier_scope import UnsearchedWindows, decision_frontier, window_touches_frontier
from server.tools.lgz_core.q0_sources import Interval, Q0EvidenceError, SourceKey


class FrontierScopeTests(unittest.TestCase):
    def test_unresolved_join_keeps_both_oriented_shoulders(self):
        left_source = SourceKey("d", "left")
        right_source = SourceKey("d", "right")
        placements = [
            SimpleNamespace(placement_id="l", source=left_source, orientation="+", interval=Interval(100, 300)),
            SimpleNamespace(placement_id="r", source=right_source, orientation="-", interval=Interval(400, 600)),
        ]
        slices = [
            SimpleNamespace(placement_id="l", source=left_source, orientation="+", interval=Interval(100, 300)),
            SimpleNamespace(placement_id="r", source=right_source, orientation="-", interval=Interval(400, 600)),
        ]
        path = SimpleNamespace(slices=slices, joins=[SimpleNamespace(kind="reference_unknown")])
        construction = SimpleNamespace(paths={"chr": SimpleNamespace(path=path)},
                                       admission=SimpleNamespace(placements=placements))
        frontier = decision_frontier(construction, flank_bp=10)
        self.assertEqual(frontier[left_source], (Interval(100, 110), Interval(290, 300)))
        self.assertEqual(frontier[right_source], (Interval(400, 410), Interval(590, 600)))

    def test_no_provisional_path_disables_lossy_scope(self):
        construction = SimpleNamespace(paths={"chr": SimpleNamespace(path=None)})
        self.assertIsNone(decision_frontier(construction))

    def test_provisional_frontier_reads_real_base_paf_without_publishing_evidence(self):
        fixture, _truth = bridge_fixture()
        data = fixture.data()
        with tempfile.TemporaryDirectory() as temporary:
            root = fixture.workspace(temporary)
            catalog = build_catalog(root, data.sources, data.reference_lengths, [])
            descriptors = [
                {"paf": "runs/chr_chr1/a_vs_c/result.paf", "query_dataset": "c", "target_dataset": "a"},
                {"paf": "runs/chr_chr1/b_vs_c/result.paf", "query_dataset": "c", "target_dataset": "b"},
            ]
            before = set(root.rglob("*"))
            frontier = q0_preparation._provisional_frontier(
                root, data.sources, data.reference_lengths, catalog, descriptors)
            self.assertEqual(set(frontier), {SourceKey("a", "a"), SourceKey("b", "b")})
            self.assertEqual(set(root.rglob("*")), before)

    def test_provisional_frontier_preserves_original_gap_and_its_evidence(self):
        fixture = EvidenceFixture()
        key = fixture.source("gapped", dna(400) + "N" * 108 + dna(550, seed=44))
        fixture.ref(key, (0, 400), (0, 400))
        fixture.ref(key, (508, 1058), (508, 1058))
        data = fixture.data()
        with tempfile.TemporaryDirectory() as temporary:
            root = fixture.workspace(temporary)
            catalog = build_catalog(root, data.sources, data.reference_lengths, [])
            frontier = q0_preparation._provisional_frontier(root, data.sources, data.reference_lengths, catalog, [])
        self.assertEqual(frontier[key], (Interval(0, 400), Interval(508, 1058)))

    def test_q0_only_opt_in_binds_ready_identity_without_changing_chr_checkpoints(self):
        fixture, _ = bridge_fixture()
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(StringIO()):
            root = fixture.workspace(temporary)
            mapper = str(Path(temporary) / "q0-fixture-bin/minimap2")
            ready = q0_preparation.load_verified_evidence(root)
            fixed = {root / row["path"]: row["sha256"] for row in ready["inputs"]}
            env = {"PATH": str(Path(mapper).parent) + os.pathsep + os.environ.get("PATH", "")}
            with patch.dict(os.environ, env), patch.object(q0_preparation, "regional_enabled", return_value=True):
                targeted = q0_preparation.prepare_evidence(root, minimap2=mapper, supplement_scope="decision_frontier")
            self.assertEqual(targeted, q0_preparation.load_verified_evidence(root))
            self.assertEqual(ready["inputs"], targeted["inputs"])
            self.assertTrue(all(sha256(p.read_bytes()).hexdigest() == digest for p, digest in fixed.items()))
            self.assertNotEqual(ready["input_fingerprint"], targeted["input_fingerprint"])
            c = q0_preparation.json_file(root / targeted["catalog"])
            self.assertEqual(c["supplement_scope"]["effective"], "decision_frontier")
            self.assertEqual(c["supplement_scope"]["requested"], "decision_frontier")
            with patch.object(q0_admission, "selector_identity", return_value="different-selector"):
                with self.assertRaisesRegex(Q0EvidenceError, "stale identity"):
                    q0_preparation.load_verified_evidence(root)
            with patch.dict(os.environ, env):
                rebuild = q0_preparation.prepare_evidence(root, minimap2=mapper)
            self.assertEqual(rebuild, ready)

    def test_bound_scope_refuses_positive_pair_when_only_other_axis_was_omitted(self):
        fixture, truth = bridge_fixture()
        data = fixture.data()
        part = next(p for p in data.parts.values() if p.source.contig == "c")
        control = q0_admission.construct_q0(data)
        self.assertEqual(control.records["chr1"], truth)
        self.assertTrue(any(j.kind == "sequence_overlap" for j in control.paths["chr1"].path.joins))
        omitted = UnsearchedWindows()
        passing = replace(data, catalog={"supplement_scope": {"unsearched_part_intervals": omitted.record()}})
        self.assertEqual(q0_admission.construct_q0(passing).records, control.records)
        other = next(p for p in data.parts.values() if p.source.contig == "a")
        def window(p, start, end):
            return SimpleNamespace(segment_id=p.segment_id, segment_length=p.interval.length, start=start, end=end)
        omitted.observe(window(other, 0, 100), (), data.parts)
        unrelated = replace(data, catalog={"supplement_scope": {"unsearched_part_intervals": omitted.record()}})
        self.assertEqual(q0_admission.construct_q0(unrelated).records, control.records)
        # Interior non-overlap on the other participant; only c's axis can refute its proof.
        omitted.observe(window(other, 0, 100), (window(part, 0, 400),), data.parts)
        with self.assertRaisesRegex(Q0EvidenceError, "unsearched competing context"):
            q0_admission.construct_q0(replace(data, catalog={
                "supplement_scope": {"unsearched_part_intervals": omitted.record()}}))

    def test_omissions_merge_relative_intervals_and_reject_bad_frame(self):
        source = SourceKey("d", "ctg")
        parts = {"a": SimpleNamespace(source=source, interval=Interval(1000, 1100))}
        def w(start,end):
            return SimpleNamespace(segment_id="a", segment_length=100, start=start, end=end)
        omitted = UnsearchedWindows()
        omitted.observe(w(0,30),(w(20,50),w(75,85)),parts)
        self.assertEqual(omitted.record(), [["a",[[0,50],[75,85]]]])
        with self.assertRaisesRegex(Q0EvidenceError,"exceeds"):
            omitted.observe(w(99,101),(),parts)

    def test_foreign_scope_rejected_before_reading_inputs(self):
        with patch.object(q0_preparation, "_initial_inputs", side_effect=AssertionError("unexpected read")):
            with self.assertRaisesRegex(Q0EvidenceError, "unsupported q0 supplement scope"):
                q0_preparation.prepare_evidence(Path("not-used"), supplement_scope="frontier-by-default")

    def test_window_scope_keeps_whole_target_inventory(self):
        source = SourceKey("d", "ctg")
        parts = {"part": SimpleNamespace(source=source, interval=Interval(1000, 2000))}
        window = SimpleNamespace(segment_id="part", segment_length=1000, start=0, end=100)
        self.assertTrue(window_touches_frontier(window, (), parts, {source: (Interval(1000, 1100),)}))
        self.assertFalse(window_touches_frontier(window, (), parts, {source: (Interval(1500, 1600),)}))
        self.assertTrue(window_touches_frontier(window, (), parts, None))


if __name__ == "__main__":
    unittest.main()
