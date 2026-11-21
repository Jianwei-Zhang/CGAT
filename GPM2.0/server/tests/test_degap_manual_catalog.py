"""Manual catalog publication/recovery; these are not native/App acceptance tests."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import degap_manual_catalog as catalog
from run_all_runner import WorkspaceLock
from workspace_layout import initialize_workspace, workspace_join


class ProcessStopped(BaseException):
    pass


class ManualCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.server = self.root / "server"
        initialize_workspace(self.server)
        metadata = workspace_join(self.server, "metadata")
        metadata.mkdir()
        (metadata / "prepare_options.tsv").write_text("key\tvalue\nthreads\t1\n")
        source = workspace_join(self.server, "data/reference/ref.fa")
        source.parent.mkdir(parents=True)
        source.write_text(">reference\nACGT\n")
        self.original = {path: path.read_bytes() for path in self.server.rglob("*") if path.is_file()}
        self.lock = WorkspaceLock(self.server, "manual-catalog-fixture")
        self.lock.acquire()
        self.addCleanup(self.lock.release)
        self.output = self.root / "degap_results.zip"

    def prepared(self, label):
        staged = self.root / ("staged-" + label)
        initialize_workspace(staged)
        shutil.copytree(workspace_join(self.server, "metadata"), workspace_join(staged, "metadata"))
        source = workspace_join(staged, "data/reference/ref.fa")
        source.parent.mkdir(parents=True)
        source.symlink_to(workspace_join(self.server, "data/reference/ref.fa"))
        (workspace_join(staged, "metadata") / "controlled_candidate.tsv").write_text(label)
        pointer = catalog.seal(self.server, staged, catalog.new_path(self.server), catalog.base_binding(self.server), {})
        archive = self.root / (label + ".zip")
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("controlled-transaction-only.txt", label)
        return pointer, archive

    def publish(self, pointer, archive):
        return catalog.publish(self.server, self.lock, pointer, archive, self.output)

    def test_repeated_catalog_verification_hashes_original_fasta_once_and_rechecks_changes(self):
        source = workspace_join(self.server, "data/reference/ref.fa")
        original = source.stat()
        real = catalog.digest
        calls = []
        def counted(path):
            if Path(path).resolve() == source:
                calls.append(str(path))
            return real(path)
        with mock.patch.object(catalog, "digest", side_effect=counted):
            pointer, archive = self.prepared("first")
            self.publish(pointer, archive)
            catalog.current(self.server)
            catalog.current(self.server)
            self.assertEqual(len(calls), 1)
            source.write_bytes(b">reference\nTTTT\n")
            os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
            with self.assertRaisesRegex(ValueError, "catalog.*base changed"):
                catalog.current(self.server)
            self.assertEqual(len(calls), 2)

    def test_pointer_failure_restores_prior_catalog_and_exact_zip_bytes(self):
        first, archive = self.prepared("first")
        previous = self.publish(first, archive)
        output_before = self.output.read_bytes()
        pointer_before = (self.server / catalog.POINTER).read_bytes()
        second, archive = self.prepared("second")
        real = catalog.durable_json
        def fail(path, value):
            if path == self.server / catalog.POINTER and value.get("catalog") == second["catalog"]:
                raise OSError("controlled pointer failure")
            return real(path, value)
        with mock.patch.object(catalog, "durable_json", side_effect=fail):
            with self.assertRaisesRegex(OSError, "controlled"):
                self.publish(second, archive)
        self.assertEqual(self.output.read_bytes(), output_before)
        self.assertEqual((self.server / catalog.POINTER).read_bytes(), pointer_before)
        self.assertEqual(catalog.current(self.server)[2], previous)
        for path, content in self.original.items():
            self.assertEqual(path.read_bytes(), content)

    def test_interrupted_zip_swap_finishes_verified_catalog_without_any_alignment(self):
        first, archive = self.prepared("first")
        self.publish(first, archive)
        second, archive = self.prepared("second")
        real = catalog.durable_json
        def stop(path, value):
            if path == self.server / catalog.POINTER:
                raise ProcessStopped()
            return real(path, value)
        with mock.patch.object(catalog, "durable_json", side_effect=stop):
            with self.assertRaises(ProcessStopped):
                self.publish(second, archive)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            catalog.current(self.server)
        self.assertEqual(catalog.recover(self.server, self.lock), "committed")
        self.assertEqual(catalog.current(self.server)[2]["catalog"], second["catalog"])
        self.assertEqual(self.output.read_bytes(), archive.read_bytes())
        self.assertIsNone(catalog.recover(self.server, self.lock))

    def test_changed_interrupted_zip_is_not_overwritten_by_recovery(self):
        pointer, archive = self.prepared("first")
        real = catalog.durable_json
        def stop(path, value):
            if path == self.server / catalog.POINTER:
                raise ProcessStopped()
            return real(path, value)
        with mock.patch.object(catalog, "durable_json", side_effect=stop):
            with self.assertRaises(ProcessStopped):
                self.publish(pointer, archive)
        self.output.write_bytes(b"user-modified-export")
        with self.assertRaisesRegex(ValueError, "ZIP changed"):
            catalog.recover(self.server, self.lock)
        self.assertEqual(self.output.read_bytes(), b"user-modified-export")
        self.assertTrue((self.server / catalog.PENDING).is_file())
        self.output.write_bytes(archive.read_bytes())
        self.assertEqual(catalog.recover(self.server, self.lock), "committed")

    def test_interruption_before_zip_swap_retains_the_previous_commit(self):
        first, archive = self.prepared("first")
        previous = self.publish(first, archive)
        previous_zip = self.output.read_bytes()
        second, archive = self.prepared("second")
        real = catalog.copy_synced
        def stop(source, destination):
            if source.name == "output.next" and destination == self.output:
                raise ProcessStopped()
            return real(source, destination)
        with mock.patch.object(catalog, "copy_synced", side_effect=stop):
            with self.assertRaises(ProcessStopped):
                self.publish(second, archive)
        self.assertEqual(catalog.recover(self.server, self.lock), "rolled_back")
        self.assertEqual(catalog.current(self.server)[2], previous)
        self.assertEqual(self.output.read_bytes(), previous_zip)

    def test_base_mutation_input_link_change_and_unowned_output_are_refused(self):
        pointer, archive = self.prepared("first")
        self.output.write_bytes(b"foreign archive")
        with self.assertRaisesRegex(ValueError, "unowned"):
            self.publish(pointer, archive)
        self.assertEqual(self.output.read_bytes(), b"foreign archive")
        self.output.unlink()
        self.publish(pointer, archive)
        source = workspace_join(self.server, "data/reference/ref.fa")
        before = source.read_bytes()
        source.write_bytes(b">reference\nTTTT\n")
        with self.assertRaisesRegex(ValueError, "catalog.*base changed"):
            catalog.current(self.server)
        source.write_bytes(before)
        options = workspace_join(self.server, "metadata/prepare_options.tsv")
        options.write_text("key\tvalue\nthreads\t2\n")
        with self.assertRaisesRegex(ValueError, "base changed"):
            catalog.current(self.server)


if __name__ == "__main__":
    unittest.main()
