"""Filesystem commit/rollback tests, not acceptance of an App archive format."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_all_runner import WorkspaceLock
from server.tools import refinement_commit as commit
from server.tools import refinement_reports as reports
from server.tests.test_refinement_reports import fixture


class ProcessStopped(BaseException):
    """Simulate termination outside ordinary exception rollback."""


def fixture_delivery_validator(delivery, final):
    # Deliberately reads two small fixture files, not production App archives.
    # Production callers must supply the real versioned App format validator.
    path = json.loads((final / "final_path.json").read_text())
    provenance = json.loads((final / "provenance.json").read_text())
    expected = reports.digest(final / "final_path.json")
    for mode in ("full", "light"):
        if (delivery / (mode + ".fixture")).read_text() != expected:
            raise ValueError("fixture delivery differs from Final Path")
    return {"schema": "cgat.refinement-delivery-validation", "schema_version": 1,
            "validator": "controlled-fixture-only", "tool": path["tool"], "run_id": provenance["run_id"],
            "modes": ["full", "light"], "final_path_sha256": expected,
            "assemblies": {row["chr"]: {"length": row["length"], "sha256": row["sha256"]} for row in path["chromosomes"]}}


class RefinementCommitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "workspace"
        self.result = fixture(self.root)
        self.report = reports.build_tool_report(self.root, self.result)
        self.delivery = self.root / ".runtime/delivery-fixture"
        self.delivery.mkdir()
        for mode in ("full", "light"):
            (self.delivery / (mode + ".fixture")).write_text(reports.digest(Path(self.result["staging"]) / "final_path.json"))
        self.lock = WorkspaceLock(self.root, "publication-fixture")
        self.lock.acquire()
        self.addCleanup(self.lock.release)

    def publish(self):
        return commit.publish_result(self.root, self.lock, self.result, self.report, self.delivery, fixture_delivery_validator)

    def test_commit_requires_all_three_areas_and_preserves_private_native_result(self):
        self.assertIsNone(commit.current_publication(self.root, "degap"))
        result = self.publish()
        self.assertEqual(result["state"], "committed")
        self.assertEqual(commit.current_publication(self.root, "degap"), result)
        for relative in ("05_final/01_degap/final_path.json", "06_report/02_refinement/01_degap/report.html", "07_delivery/01_degap/full.fixture", "07_delivery/01_degap/light.fixture"):
            self.assertTrue((self.root / relative).is_file())
        self.assertTrue((Path(self.result["staging"]) / "assembly.fa").is_file())
        (self.root / "07_delivery/01_degap/light.fixture").write_text("changed")
        with self.assertRaisesRegex(ValueError, "delivery changed"):
            commit.current_publication(self.root, "degap")

    def test_failed_replacement_restores_previous_publication_and_its_receipt(self):
        previous = self.publish()
        (self.delivery / "new-attempt.txt").write_text("second publication")
        real = commit.rename_synced
        def fail(source, target):
            if source.name == "report" and source.parent.name == "prepared":
                raise OSError("controlled rename failure")
            return real(source, target)
        with mock.patch.object(commit, "rename_synced", side_effect=fail):
            with self.assertRaisesRegex(OSError, "controlled"):
                self.publish()
        self.assertEqual(commit.current_publication(self.root, "degap"), previous)
        self.assertFalse((self.root / "07_delivery/01_degap/new-attempt.txt").exists())
        self.assertTrue((self.delivery / "new-attempt.txt").is_file())

    def test_interrupted_swap_is_fenced_then_recovered_without_rerunning_native(self):
        real = commit.rename_synced
        def stop(source, target):
            result = real(source, target)
            if source.name == "final" and source.parent.name == "prepared":
                raise ProcessStopped()
            return result
        with mock.patch.object(commit, "rename_synced", side_effect=stop):
            with self.assertRaises(ProcessStopped):
                self.publish()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            commit.current_publication(self.root, "degap")
        restored = commit.recover_publication(self.root, self.lock, "degap", fixture_delivery_validator)
        self.assertEqual(restored["status"], "rolled_back")
        self.assertIsNone(commit.current_publication(self.root, "degap"))
        self.assertFalse((self.root / "05_final/01_degap").exists())
        self.assertTrue((Path(self.result["staging"]) / "provenance.json").is_file())
        self.publish()
        self.assertIsNotNone(commit.current_publication(self.root, "degap"))

    def test_interruption_after_validation_finishes_the_commit_receipt(self):
        with mock.patch.object(commit, "_commit_pointer", side_effect=ProcessStopped):
            with self.assertRaises(ProcessStopped):
                self.publish()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            commit.current_publication(self.root, "degap")
        result = commit.recover_publication(self.root, self.lock, "degap", fixture_delivery_validator)
        self.assertEqual(result["status"], "committed")
        self.assertEqual(commit.current_publication(self.root, "degap")["transaction"], result["transaction"])

    def test_unowned_targets_and_missing_delivery_are_not_overwritten_or_accepted(self):
        (self.delivery / "light.fixture").write_text("not this refined result")
        with self.assertRaisesRegex(ValueError, "differs"):
            self.publish()
        self.assertFalse((self.root / "05_final").exists())
        with self.assertRaisesRegex(ValueError, "staging cannot contain"):
            commit.publish_result(self.root, self.lock, self.result, self.report, self.root, fixture_delivery_validator)
        target = self.root / "05_final/01_degap"
        target.mkdir(parents=True)
        (target / "user.txt").write_text("do not replace")
        with self.assertRaisesRegex(ValueError, "unowned"):
            self.publish()
        self.assertEqual((target / "user.txt").read_text(), "do not replace")
        self.lock.release()
        with self.assertRaisesRegex(ValueError, "held numbered-workspace lock"):
            self.publish()


if __name__ == "__main__":
    unittest.main()
