"""Real archives and publication over controlled admission, not real native tools."""
import json
import io
import gzip
import tarfile
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile
import warnings

from server.tests.refinement_bundle_fixture import create
from refinement_delivery import build_delivery, validate_delivery, _extract
from refinement_reports import build_tool_report
from refinement_batch import publish_batch
from refinement_commit import current_publication, publish_result
import refinement_delivery as delivery_module
from run_orchestration import sha256_file as digest
from run_all_runner import WorkspaceLock


@unittest.skipUnless(shutil.which("samtools") and shutil.which("zip"), "delivery requires indexing/zip")
class RefinedDeliveryTests(unittest.TestCase):
    def test_real_full_light_archives_commit_as_one_refined_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result, _, _ = create(root)
            report = build_tool_report(root, result)
            lock = WorkspaceLock(root, "real-delivery-fixture")
            lock.acquire()
            try:
                batch = {"batch_id": "b" * 32, "status": "staged", "exit_code": 0,
                         "tools": {"degap": {"status": "staged", "run_id": result["run_id"], "report": report}}}
                complete = publish_batch(root, lock, {"batch": batch, "staged_results": {"degap": result}, "exit_code": 0})
                self.assertEqual(complete["exit_code"], 0, complete)
                self.assertEqual(complete["batch"]["status"], "published")
                receipt = current_publication(root, "degap")
                self.assertEqual(receipt["delivery_validation"]["validator"], "cgat.refinement-archive-and-sources.v1")
                delivery = root / "07_delivery/01_degap"
                archives = json.loads((delivery / "delivery.json").read_text())["archives"]
                self.assertEqual(set(archives), {"full", "light"})
                for mode, row in archives.items():
                    with zipfile.ZipFile(delivery / row["file"]) as archive:
                        self.assertIsNone(archive.testzip())
                        self.assertIn("workspace.degap/metadata/refinement/final_path.json", archive.namelist())
                        self.assertIn("workspace.degap/data/refinement/final.fa", archive.namelist()) if mode == "full" else self.assertNotIn("workspace.degap/data/refinement/final.fa", archive.namelist())
                        self.assertFalse(any(".runtime" in name or "03_native" in name or "07_delivery" in name for name in archive.namelist()))
                summary = json.loads((root / "06_report/03_comparison" / batch["batch_id"] / "comparison.json").read_text())
                self.assertEqual(summary["tools"][0]["status"], "published")
                self.assertIsNotNone(summary["tools"][0]["publication_transaction"])
                overview = (root / "06_report/report.html").read_text()
                for row in archives.values():
                    self.assertIn("../07_delivery/01_degap/" + row["file"], overview)
                self.assertIn("../05_final/01_degap/assembly.fa", overview)
                validate_delivery(delivery, root / "05_final/01_degap")
            finally:
                lock.release()

    def test_same_admission_refreshes_report_and_serializer_without_replacing_final(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result, _, _ = create(root)
            report = build_tool_report(root, result)
            lock = WorkspaceLock(root, "delivery-refresh-fixture")
            lock.acquire()
            try:
                def publish(current_report):
                    batch = {"batch_id": "b" * 32, "status": "staged", "exit_code": 0,
                             "tools": {"degap": {"status": "staged", "run_id": result["run_id"], "report": current_report}}}
                    with mock.patch("refinement_batch.stage_refinement", side_effect=AssertionError("must not rerun science")):
                        outcome = publish_batch(root, lock, {"batch": batch, "staged_results": {"degap": result}, "exit_code": 0})
                    self.assertEqual(outcome["exit_code"], 0, outcome)
                    return current_publication(root, "degap")

                first = publish(report)
                final = root / "05_final/01_degap"
                before = {p.name: (digest(p), p.stat().st_ino, p.stat().st_mtime_ns) for p in final.iterdir()}
                # The actual cache can return the published scientific tree.
                # It must never be copied/renamed just to update a report/package.
                result = dict(result, staging=str(final))
                with mock.patch.object(delivery_module, "build_delivery", side_effect=AssertionError("unchanged delivery rebuilt")):
                    self.assertEqual(publish(report)["transaction"], first["transaction"])

                report_dir = root / ".runtime/controlled-report-revision"
                shutil.copytree(report["directory"], report_dir)
                manifest = json.loads((report_dir / "manifest.json").read_text())
                with (report_dir / "report.html").open("a") as output:
                    output.write("\n<p>Controlled report-only revision</p>\n")
                manifest["files"]["report.html"] = digest(report_dir / "report.html")
                (report_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
                revised = {"directory": str(report_dir), "report": str(report_dir / "report.html"),
                           "manifest_sha256": digest(report_dir / "manifest.json")}
                # Equal DNA/run IDs are not proof that an old archive contains
                # the current report. Reject this combination before any swap.
                with self.assertRaisesRegex(ValueError, "validator did not prove"):
                    publish_result(root, lock, result, revised, root / "07_delivery/01_degap", validate_delivery)
                self.assertEqual(current_publication(root, "degap")["transaction"], first["transaction"])
                second = publish(revised)
                self.assertNotEqual(first["transaction"], second["transaction"])
                self.assertTrue(second["areas"]["final"]["unchanged"])
                self.assertFalse(second["areas"]["report"]["unchanged"])
                self.assertEqual(second["delivery_validation"]["report_manifest_sha256"], revised["manifest_sha256"])
                delivery = root / "07_delivery/01_degap"
                definition = json.loads((delivery / "delivery.json").read_text())
                for row in definition["archives"].values():
                    with zipfile.ZipFile(delivery / row["file"]) as archive:
                        self.assertEqual(archive.read("workspace.degap/report/manifest.json"), (report_dir / "manifest.json").read_bytes())
                        self.assertIn(b"Controlled report-only revision", archive.read("workspace.degap/report/report.html"))

                # A serializer-only revision is also independent of admission.
                with mock.patch.object(delivery_module, "GENERATOR_FILES", delivery_module.GENERATOR_FILES + ("refinement_batch.py",)):
                    third = publish(revised)
                    self.assertNotEqual(third["transaction"], second["transaction"])
                    self.assertTrue(third["areas"]["final"]["unchanged"])
                    self.assertTrue(third["areas"]["report"]["unchanged"])
                    self.assertFalse(third["areas"]["delivery"]["unchanged"])
                    with mock.patch.object(delivery_module, "build_delivery", side_effect=AssertionError("unchanged delivery rebuilt")):
                        self.assertEqual(publish(revised)["transaction"], third["transaction"])
                self.assertEqual({p.name: (digest(p), p.stat().st_ino, p.stat().st_mtime_ns) for p in final.iterdir()}, before)
            finally:
                lock.release()

    def test_delivery_validation_cache_cannot_hide_a_changed_report_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result, _, _ = create(root)
            report = build_tool_report(root, result)
            delivery = build_delivery(root, result, report)
            proof = validate_delivery(delivery, result["staging"])
            self.assertEqual(proof["report_manifest_sha256"], report["manifest_sha256"])
            definition = json.loads((delivery / "delivery.json").read_text())
            legacy = {key: value for key, value in definition.items() if key != "generation"}
            (delivery / "delivery.json").write_text(json.dumps(legacy))
            historical = validate_delivery(delivery, result["staging"])
            self.assertIsNone(historical["generation_sha256"])
            self.assertEqual(historical["report_manifest_sha256"], report["manifest_sha256"])
            provenance_file = Path(result["staging"]) / "provenance.json"
            original = provenance_file.read_bytes()
            changed = json.loads(original)
            changed["controlled_changed_provenance"] = True
            provenance_file.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "different admitted provenance"):
                validate_delivery(delivery, result["staging"])
            provenance_file.write_bytes(original)
            definition["generation"]["report_manifest_sha256"] = "0" * 64
            (delivery / "delivery.json").write_text(json.dumps(definition))
            with self.assertRaisesRegex(ValueError, "report/format differs"):
                validate_delivery(delivery, result["staging"])

    def test_tar_reader_checks_real_gzip_trailer_not_only_valid_tar_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "payload.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                entry = tarfile.TarInfo("tool/metadata/fixture.txt")
                entry.size = 4
                output.addfile(entry, io.BytesIO(b"data"))
            target = root / "valid"
            target.mkdir()
            payload = _extract(archive, target)
            self.assertEqual((payload / "metadata/fixture.txt").read_bytes(), b"data")
            data = bytearray(archive.read_bytes())
            data[-8] ^= 1
            archive.write_bytes(data)
            target = root / "bad"
            target.mkdir()
            with self.assertRaises((gzip.BadGzipFile, OSError)):
                _extract(archive, target)

    def test_archive_extraction_rejects_paths_links_and_duplicate_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for number, names in enumerate((("../outside",), ("root/../../outside",), ("a/file", "b/file"), ("root/same", "root/same"))):
                archive = root / f"unsafe-{number}.zip"
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(archive, "w") as output:
                        for name in names:
                            output.writestr(name, "unsafe")
                destination = root / f"unpack-{number}"
                destination.mkdir()
                with self.assertRaises(ValueError):
                    _extract(archive, destination)
            self.assertFalse((root / "outside").exists())


if __name__ == "__main__":
    unittest.main()
