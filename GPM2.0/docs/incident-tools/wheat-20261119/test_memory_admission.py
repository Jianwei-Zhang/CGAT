import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
from alignment_tasks import AlignmentTask
from memory_admission import MemoryBoundedDispatcher, needs_exclusive, _manifest


def task(name, work=10):
    return AlignmentTask(name, Path("/tmp") / name, 4, work, None, work, 0.5)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.d = MemoryBoundedDispatcher(lambda t: t.unit_id.startswith("large"))
        self.big = task("large", 100)
        self.small = task("small", 10)
        self.other = task("other", 5)

    def test_large_is_exclusive(self):
        got = self.d([self.small, self.big], 16, 16, [], 16)
        self.assertEqual([t for t, _ in got], [self.big])

    def test_running_large_blocks_everything(self):
        self.assertEqual(self.d([self.small], 15, 16, [{"task": self.big}], 15), [])

    def test_large_waits_for_small_to_drain(self):
        self.assertEqual(self.d([self.big, self.other], 15, 16, [{"task": self.small}], 15), [])

    def test_small_overlap_capped_at_two(self):
        got = self.d([self.small, self.other, task("third", 1)], 16, 16, [], 16)
        self.assertEqual(len(got), 2)
        self.assertLessEqual(sum(n for _, n in got), 16)
        self.assertEqual(len(self.d([self.other], 14, 16, [{"task": self.small}], 8)), 1)
        self.assertEqual(self.d([self.other], 12, 16, [{"task": self.small}, {"task": self.small}], 8), [])

    def test_empty_slots_and_thread_budget(self):
        self.assertEqual(self.d([self.big], 16, 16, [], 0), [])
        self.assertEqual(self.d([self.small], 0, 16, [], 2), [])

    def test_unknown_is_exclusive(self):
        self.assertTrue(needs_exclusive(task("missing")))

    def test_cross_and_self_profiles_boundary_and_malformed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "assembly_vs_self"
            parent.mkdir()
            batch = parent / "batches/batch-00000"
            p = parent / "self_batch_manifest.json"
            cross = AlignmentTask("q0_chr:X", root / "other_vs_assembly/command.sh", 4)
            self_task = AlignmentTask("q0_chr:X", batch / "command.sh", 4)
            for length, expected in [(99_999_999, False), (100_000_000, True), (289_508_469, True), (-1, True), ("bad", True)]:
                p.write_text(json.dumps({"target_lengths": {"x": length}, "batches": [{"directory": str(batch), "entries": [{"length": length}]}]}))
                _manifest.cache_clear()
                self.assertEqual(needs_exclusive(cross), expected)
                self.assertEqual(needs_exclusive(self_task), expected)
            p.write_text(json.dumps({"target_lengths": {}, "batches": [{"directory": str(batch), "entries": [{"length": 60_000_000}, {"length": 60_000_000}]}]}))
            _manifest.cache_clear()
            self.assertTrue(needs_exclusive(cross))
            self.assertTrue(needs_exclusive(self_task))


if __name__ == "__main__":
    unittest.main()
