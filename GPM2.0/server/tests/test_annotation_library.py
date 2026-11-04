"""Library regression cases; execution intentionally deferred to unified review."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from annotation_library import manage, snapshot, load_entries, write_tsv, TEL_FIELDS, CEN_FIELDS, verify_snapshot


class AnnotationLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.server = self.root / "server"
        self.project = self.root / "project"
        shutil.copytree(TOOLS.parent / "library", self.server / "library")

    def prepare(self, tel=(), cen=None):
        snapshot(self.server, self.project, tel, cen, 10000, 80)
        return json.loads((self.project / "metadata/annotation_library_snapshot.json").read_text())

    def test_official_only_is_automatic_and_source_data_are_pinned(self):
        manifest = self.prepare()
        self.assertEqual(len(manifest["tel"]), 3)
        self.assertEqual(len(manifest["cen"]), 4)
        for entry in json.loads((self.server / "library/cen/sources.json").read_text())["entries"]:
            path = self.server / "library/cen" / (entry["id"] + ".fa")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["fasta_sha256"])

    def test_union_deduplicates_but_keeps_every_note_and_source(self):
        write_tsv(self.server / "local/library/tel.tsv", TEL_FIELDS,
                  [{"id": "custom", "motif": "TTAGGG", "min_repeat": 5, "note": 'local "evidence"'}])
        manifest = self.prepare([("TTAGGG", 5), ("TTAGGG", 20)])
        group = next(row for row in manifest["tel"] if row["motif"] == "TTAGGG" and row["min_repeat"] == 5)
        self.assertEqual([e["source"] for e in group["entries"]], ["official", "local", "parameter"])
        self.assertEqual(group["entries"][1]["note"], 'local "evidence"')
        self.assertEqual(len(manifest["tel"]), 4)
        local = self.server / "local/library/tel.tsv"
        self.assertNotIn("parameter", local.read_text())

    def test_old_headers_have_no_chromosome_binding_and_exact_sequences_merge(self):
        explicit = self.root / "input.fa"
        explicit.write_text(">unknown_chr_centromere\nACGTACGT\n>arbitrary\nACGTACGT\n")
        manifest = self.prepare(cen=str(explicit))
        group = next(e for e in manifest["cen"] if e["length"] == 8)
        self.assertEqual(len(group["entries"]), 2)
        with (self.project / "cen/reference.tsv").open() as handle:
            self.assertEqual({r["chr_name"] for r in csv.DictReader(handle, delimiter="\t")}, {"*"})

    def test_official_update_does_not_change_local_or_prepared_inputs(self):
        local = self.server / "local/library/tel.tsv"
        write_tsv(local, TEL_FIELDS, [{"id": "local_rule", "motif": "ACTG", "min_repeat": 3, "note": ""}])
        self.prepare()
        before_local = local.read_bytes()
        paths = [self.project / path for path in ("cen/library.fa", "cen/reference.tsv", "tel/rules.tsv",
                                                  "metadata/annotation_library_snapshot.json")]
        before = [p.read_bytes() for p in paths]
        write_tsv(self.server / "library/tel.tsv", TEL_FIELDS,
                  [{"id": "next", "motif": "ATGC", "min_repeat": 12, "note": "new version"}])
        self.assertEqual(local.read_bytes(), before_local)
        self.assertEqual([p.read_bytes() for p in paths], before)

    def test_local_management_empty_note_and_official_removal_guard(self):
        args = SimpleNamespace(server_root=self.server, command="add-tel", motif="ACG", min_repeat="4", note="")
        manage(args)
        tel, _ = load_entries(self.server / "local/library", "local", optional=True)
        self.assertEqual(tel[0]["note"], "")
        with self.assertRaisesRegex(ValueError, "official"):
            manage(SimpleNamespace(server_root=self.server, command="remove", id="tel_plant_TTTAGGG"))
        manage(SimpleNamespace(server_root=self.server, command="remove", id=tel[0]["id"]))
        tel, _ = load_entries(self.server / "local/library", "local", optional=True)
        self.assertEqual(tel, [])

    def test_edited_or_partial_snapshots_fail_closed(self):
        self.prepare()
        verify_snapshot(self.project)
        (self.project / "cen/library.fa").write_text(">changed\nACGT\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            verify_snapshot(self.project)
        (self.project / "metadata/annotation_library_snapshot.json").unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify_snapshot(self.project)

    def test_invalid_local_data_fails_before_replacing_project_inputs(self):
        self.prepare()
        path = self.project / "tel/rules.tsv"
        before = path.read_bytes()
        write_tsv(self.server / "local/library/cen/cen.tsv", CEN_FIELDS, [{"id": "missing", "note": ""}])
        with self.assertRaises(OSError):
            self.prepare()
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
