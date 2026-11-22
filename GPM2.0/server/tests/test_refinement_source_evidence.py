"""Small accepted-source measurements; not four native tool/environment acceptance."""
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import refinement_source_evidence as evidence
from refinement_source_marks import project
from workspace_layout import WorkspaceLayout
from refinement_bundle_fixture import create


@unittest.skipUnless(shutil.which("samtools") and shutil.which("minimap2"), "small source measurement requires base tools")
class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "workspace"
        self.result, self.full, _ = create(self.root)
        self.layout = WorkspaceLayout.detect(self.root)

    def test_real_small_reference_no_hit_cache_and_original_science_immutability(self):
        original = {path: (path.stat().st_mtime_ns, path.read_bytes())
                    for area in ("01_inputs", "02_alignments", "03_lgz", ".runtime/metadata", "04_refinement/01_degap/03_native")
                    for path in (self.root / area).rglob("*") if path.is_file()}
        accepted = self.root / "04_refinement/01_degap/04_accepted"
        accepted_inputs = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in accepted.rglob("*") if path.is_file()}
        built = evidence.build(self.root, self.result, 1)
        receipt = evidence.load(built["directory"])
        for path, expected in accepted_inputs.items():
            self.assertEqual((path.stat().st_mtime_ns, path.read_bytes()), expected)
        self.assertTrue(all(path in accepted_inputs or path.is_relative_to(Path(built["directory"]))
                            for path in accepted.rglob("*") if path.is_file()), "private source indexes must not leak into accepted inputs")
        self.assertTrue(receipt["sources"])
        self.assertTrue(all(row["ref_alignment_status"] == "no_hit" and row["reference_hits"] == 0 for row in receipt["sources"]))
        self.assertTrue(all(row["annotations"] == {"tel": "disabled", "cen": "disabled"} for row in receipt["sources"]))
        self.assertEqual(receipt["recipe"]["preset_source"], "legacy_default_asm10")
        with mock.patch.object(evidence.subprocess, "run", side_effect=AssertionError("completed source measurement must not rerun")):
            self.assertEqual(evidence.build(self.root, self.result, 1), built)
        for path, expected in original.items():
            self.assertEqual((path.stat().st_mtime_ns, path.read_bytes()), expected, str(path))
        for legacy in ("data", "runs", "metadata", "tel", "cen"):
            self.assertFalse((self.root / legacy).exists())
        table = Path(built["directory"]) / "04_projection/source_intervals.tsv"
        table.write_bytes(table.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "incomplete or changed"):
            evidence.build(self.root, self.result, 1)

    def frozen_rules(self, *, chromosome="*"):
        from refinement_source_evidence_fixture import frozen_rules
        return frozen_rules(self.root, chromosome=chromosome)

    def controlled_mummer(self):
        from refinement_source_evidence_fixture import controlled_mummer
        return controlled_mummer(Path(self.tmp.name))

    def test_frozen_source_scans_and_measured_full_light_serialization(self):
        from refinement_bundle import build_full, build_light
        from refinement_bundle_validate import validate_payload
        from refinement_reports import build_tool_report
        frozen = self.frozen_rules()
        folder = self.controlled_mummer()
        with mock.patch.dict(os.environ, {"PATH": str(folder) + os.pathsep + os.environ["PATH"]}):
            built = evidence.build(self.root, self.result, 1)
            receipt = evidence.load(built["directory"])
            self.assertTrue(all(row["annotations"] == {"tel": "scanned", "cen": "scanned"} for row in receipt["sources"]))
            self.result["source_evidence"] = built
            report = build_tool_report(self.root, self.result)
            full, light = self.root / ".runtime/measured/full", self.root / ".runtime/measured/light"
            build_full(self.root, self.result, report, full)
            build_light(full, light)
            self.assertEqual(validate_payload(full, full=True)["assemblies"], validate_payload(light, full=False)["assemblies"])
            projection = json.loads((full / evidence.PROJECTION).read_text())
            self.assertEqual(projection, json.loads((light / evidence.PROJECTION).read_text()))
            self.assertTrue(any(row["kind"] == "cen" and row["origin"] == "refinement_patch" for row in evidence.table(full / "metadata/refinement/final_annotations.tsv")))
            self.assertTrue((Path(report["directory"]) / "sources-0001.html").is_file())
            for path, original in frozen.items():
                self.assertEqual(path.read_bytes(), original)
            with mock.patch.object(evidence.subprocess, "run", side_effect=AssertionError("report/delivery refresh must reuse measurements")):
                self.assertEqual(evidence.build(self.root, self.result, 1), built)
                self.assertEqual(build_tool_report(self.root, self.result), report)

    def test_resealed_measurement_labels_and_coordinates_are_checked_against_actual_evidence(self):
        from refinement_bundle import build_full, seal_manifest
        from refinement_bundle_validate import validate_payload
        from refinement_reports import build_tool_report
        built = evidence.build(self.root, self.result, 1)
        self.result["source_evidence"] = built
        report = build_tool_report(self.root, self.result)
        full = self.root / ".runtime/negative-proof/full"
        build_full(self.root, self.result, report, full)
        proof_path = full / evidence.PROJECTION
        manifest_path = full / "metadata/refinement/manifest.json"
        proof_bytes, manifest_bytes = proof_path.read_bytes(), manifest_path.read_bytes()
        proof = json.loads(proof_bytes)
        proof["sources"][0]["ref_alignment_status"] = "hit"
        proof_path.write_text(json.dumps(proof))
        manifest = json.loads(manifest_bytes)
        manifest["source_evidence"]["sha256"] = evidence.content_digest(proof_path)
        seal_manifest(full, manifest)
        with self.assertRaisesRegex(ValueError, "source status does not describe"):
            validate_payload(full, full=True)
        proof_path.write_bytes(proof_bytes)
        manifest_path.write_bytes(manifest_bytes)
        interval_path = full / "metadata/refinement/source_intervals.tsv"
        with interval_path.open() as stream:
            import csv
            fields = csv.DictReader(stream, delimiter="\t").fieldnames
        rows = evidence.table(interval_path)
        rows[0]["final_start"] = str(int(rows[0]["final_start"]) + 1)
        evidence.write_table(interval_path, fields, rows)
        proof = json.loads(proof_bytes)
        proof["files"]["metadata/refinement/source_intervals.tsv"] = evidence.content_digest(interval_path)
        proof_path.write_text(json.dumps(proof))
        manifest = json.loads(manifest_bytes)
        manifest["source_evidence"]["sha256"] = evidence.content_digest(proof_path)
        seal_manifest(full, manifest)
        with self.assertRaisesRegex(ValueError, "coordinates differ"):
            validate_payload(full, full=True)

    def test_failed_measurement_retains_job_diagnostics_and_retry_does_not_touch_native(self):
        from refinement_reports import build_failure_report
        native = self.root / "04_refinement/01_degap/03_native"
        original = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in native.rglob("*") if path.is_file()}
        actual_run = subprocess.run
        def controlled_failure(command, **kwargs):
            if Path(command[0]).name == "minimap2" and "--version" not in command:
                kwargs["stderr"].write("controlled source-reference failure; native gap producer was not executed\n")
                raise subprocess.CalledProcessError(17, command)
            return actual_run(command, **kwargs)
        with mock.patch.object(evidence.subprocess, "run", side_effect=controlled_failure):
            with self.assertRaises(evidence.SourceEvidenceError) as caught:
                evidence.build(self.root, self.result, 1)
        failure_home = caught.exception.source_evidence_diagnostics
        failure = json.loads((failure_home / "failure.json").read_text())
        self.assertEqual(failure["status"], "failed")
        self.assertFalse((failure_home / evidence.RECEIPT).exists())
        logs = list(failure_home.glob("02_reference/*/stderr.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("controlled source-reference failure", logs[0].read_text())
        self.assertEqual(json.loads(logs[0].with_name("command.json").read_text())["status"], "failed")
        report = build_failure_report(self.root, "degap", self.result["run_id"], caught.exception, phase="source_evidence")
        summary = json.loads((Path(report["directory"]) / "summary.json").read_text())
        self.assertFalse(summary["final_available"])
        self.assertIsNone(summary["diagnostics_error"])
        source_log = next(row for row in summary["artifacts"] if row["workspace_path"].endswith("/stderr.log"))
        self.assertEqual(source_log["availability"], "embedded")
        self.assertIn("controlled source-reference failure", (Path(report["directory"]) / source_log["report_path"]).read_text())
        built = evidence.build(self.root, self.result, 1)
        self.assertNotEqual(Path(built["directory"]), failure_home)
        self.assertEqual(evidence.load(built["directory"])["sources"][0]["ref_alignment_status"], "no_hit")
        for path, expected in original.items():
            self.assertEqual((path.stat().st_mtime_ns, path.read_bytes()), expected)

    def test_reference_input_drift_invalidates_shared_seal_and_existing_measurements(self):
        from refinement_batch import baseline_seal, check_seal
        built = evidence.build(self.root, self.result, 1)
        receipt = evidence.load(built["directory"])
        sealed = baseline_seal(self.root)
        reference = self.layout.path("data/reference/ref.fa")
        reference.write_bytes(reference.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "shared refinement input changed"):
            check_seal(sealed)
        with self.assertRaisesRegex(ValueError, "source evidence input changed"):
            evidence.verify_inputs(receipt["recipe"])

    def test_empty_prepared_telomere_rules_are_not_a_scanned_negative(self):
        rules = self.layout.path("tel/rules.tsv")
        rules.parent.mkdir(parents=True)
        rules.write_text("rule_id\tmotif\tmin_repeat\n")
        built = evidence.build(self.root, self.result, 1)
        receipt = evidence.load(built["directory"])
        self.assertTrue(all(row["annotations"]["tel"] == "no_rules" for row in receipt["sources"]))

    def test_missing_chromosome_cen_library_is_not_a_scanned_negative(self):
        self.frozen_rules(chromosome="different_chr")
        built = evidence.build(self.root, self.result, 1)
        receipt = evidence.load(built["directory"])
        self.assertNotIn("nucmer", receipt["recipe"]["tools"])
        self.assertTrue(all(row["annotations"]["cen"] == "no_chr_library" for row in receipt["sources"]))


class SourceMarkProjectionTests(unittest.TestCase):
    def test_clipping_reverse_orientation_repeated_source_and_final_coordinate_shift(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.tsv"
            path.write_text("rule_id\tdataset_name\tseq_name\tassigned_chr_name\tstart_bp\tend_bp\tstrand\n"
                            "middle\tds\tu\tchr\t3\t7\t+\nclipped\tds\tu\tchr\t1\t3\t+\n")
            def segment(name, offset, orientation):
                return {"segment_id": name, "kind": "patch", "output_start": offset, "length": 8,
                        "source": {"dataset": "ds", "contig": "u", "start": 2, "end": 9, "orientation": orientation}}
            final = {"chromosomes": [{"chr": "chr", "segments": [segment("forward", 0, "+"), segment("reverse", 8, "-")]}]}
            intervals, rows = project(final, {("ds", "u"): 10}, [{"kind": "tel", "chromosome": "chr", "path": path, "origin": "refinement_patch"}])
            middle = {row["segment_id"]: row for row in rows if row["annotation_id"] == "middle"}
            self.assertEqual((middle["forward"]["final_start"], middle["forward"]["final_end"], middle["forward"]["final_strand"]), (1, 6, "+"))
            self.assertEqual((middle["reverse"]["final_start"], middle["reverse"]["final_end"], middle["reverse"]["final_strand"]), (10, 15, "-"))
            clipped = {row["segment_id"]: row for row in rows if row["annotation_id"] == "clipped"}
            self.assertEqual((clipped["reverse"]["final_start"], clipped["reverse"]["final_end"]), (14, 16))
            self.assertTrue(all(row["projection"] == "clipped_source_support_not_rescanned" for row in clipped.values()))
            self.assertEqual(intervals[1]["final_start"], 8)


if __name__ == "__main__":
    unittest.main()
