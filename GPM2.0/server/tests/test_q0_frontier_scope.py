from types import SimpleNamespace
import tempfile
import unittest

from server.tests.test_q0_admission import bridge_fixture
from server.tools.lgz_core import q0_preparation
from server.tools.lgz_core.q0_catalog import build_catalog
from server.tools.lgz_core.q0_frontier_scope import decision_frontier, window_touches_frontier
from server.tools.lgz_core.q0_sources import Interval, SourceKey


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

    def test_window_scope_keeps_whole_target_inventory(self):
        source = SourceKey("d", "ctg")
        parts = {"part": SimpleNamespace(source=source, interval=Interval(1000, 2000))}
        window = SimpleNamespace(segment_id="part", segment_length=1000, start=0, end=100)
        self.assertTrue(window_touches_frontier(window, (), parts, {source: (Interval(1000, 1100),)}))
        self.assertFalse(window_touches_frontier(window, (), parts, {source: (Interval(1500, 1600),)}))
        self.assertTrue(window_touches_frontier(window, (), parts, None))


if __name__ == "__main__":
    unittest.main()
