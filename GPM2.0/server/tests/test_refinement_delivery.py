"""Real archives and publication over controlled admission, not real native tools."""
import json
import io
import gzip
import tarfile
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
import warnings

from server.tests.refinement_bundle_fixture import create
from refinement_delivery import build_delivery, validate_delivery, _extract
from refinement_reports import build_tool_report
from refinement_batch import publish_batch
from refinement_commit import current_publication
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
                validate_delivery(delivery, root / "05_final/01_degap")
            finally:
                lock.release()

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
