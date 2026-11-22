"""Offline report contracts; synthetic receipts are not native-engine acceptance."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
from urllib.parse import unquote, urlsplit

from server.tools import refinement_reports as reports
from server.tools.workspace_layout import initialize_workspace


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False))


def fixture(root):
    initialize_workspace(root)
    run_id = "a" * 32
    native = root / "04_refinement/01_degap/03_native" / run_id
    native.mkdir(parents=True)
    jobs = root / "04_refinement/01_degap/02_jobs" / run_id
    jobs.mkdir(parents=True)
    (jobs / "native.log").write_text("native process completed\n")
    directory = native / "03.gap_filling/chr1.1.left"
    directory.mkdir(parents=True)
    (directory / "process.log").write_text("actual per-job diagnostic\n")
    dump(native / "03.gap_filling/job_manager_config.json", {"jobs": [
        {"job_name": "<img src=x onerror=alert(1)>", "job_dir": str(directory), "chromosome": "chr1", "gap_id": 1, "direction": "left"}]})
    native_gap = native / "03.gap_filling/gap_filling_results.json"
    dump(native_gap, {"gaps": [{"chromosome": "chr1", "gap_id": 1, "gap_start": 4, "gap_end": 9,
                               "filled": True, "fill_direction": "left", "left_status": "success", "right_status": "skipped"}]})
    visual = native / "05.visualization/gap_filling_report.html"
    visual.parent.mkdir()
    visual.write_text('<script src="https://example.invalid/chart.js"></script>')
    final_dir = root / ".runtime/refinement/01_degap" / run_id / "final"
    final_dir.mkdir(parents=True)
    gaps = [{"gap_id": "gap-" + str(i), "chromosome": "chr1", "start": start, "end": start + 6}
            for i, start in enumerate((4, 14, 24), 1)]
    edit = {"edit_id": "accepted-1", "gap_ids": ["gap-1"], "native_job": "gap_filling_results.json#gap-0", "evidence": {"decision": "unique source"}}
    baseline = {"final_path_sha256": "b" * 64, "assembly_sha256": "c" * 64}
    final = {"schema": "cgat.refined-final-path", "schema_version": 1, "tool": "degap", "baseline": baseline,
             "recipe_sha256": "d" * 64, "original_gaps": gaps, "edits": [edit],
             "chromosomes": [{"chr": "chr1", "length": 30, "sha256": "e" * 64, "segments": []}]}
    dump(final_dir / "final_path.json", final)
    (final_dir / "assembly.fa").write_text(">chr1\nAAAAGTCCCC\n")
    (final_dir / "sources.tsv").write_text("dataset\tcontig\n")
    (final_dir / "remaining_gaps.tsv").write_text("chromosome\tstart\tend\nchr1\t10\t16\nchr1\t20\t26\n")
    provenance = {"schema": "cgat.refinement-publication", "schema_version": 1, "tool": "degap", "run_id": run_id,
                  "status": "completed", "baseline": baseline, "accepted_edit_count": 1, "original_gap_count": 3,
                  "counts": {"closed": 1, "partial": 0, "unfilled": 1, "rejected": 1},
                  "gap_outcomes": [{**g, "status": status, "edit_ids": ["accepted-1"] if status == "closed" else []}
                                   for g, status in zip(gaps, ("closed", "unfilled", "rejected"))],
                  "rejected_candidates": [{"gap_ids": ["gap-3"], "reason": "ambiguous source", "native_job": "third"}],
                  "execution": {"status": "success", "run_id": run_id, "tool": "degap", "threads": 2,
                                "native_executed": True, "recipe_sha256": "d" * 64,
                                "recipe": {"reads": [], "revision": "f" * 40},
                                "native_assembly": {"chr1": {"length": 28, "n_bases": 6, "sha256": "f" * 64}},
                                "artifacts": {native_gap.relative_to(root).as_posix(): reports.digest(native_gap)}},
                  "artifacts": {name: reports.digest(final_dir / name) for name in ("assembly.fa", "final_path.json", "sources.tsv", "remaining_gaps.tsv")}}
    dump(final_dir / "provenance.json", provenance)
    dump(jobs / "invocation.json", {"tool": "degap", "run_id": run_id, "status": "staged",
                                    "provenance_sha256": reports.digest(final_dir / "provenance.json")})
    return {"tool": "degap", "run_id": run_id, "staging": str(final_dir), "provenance": provenance}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "href" in values:
            self.links.append(values["href"])
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "script":
            raise AssertionError("report must not execute scripts")


class RefinementReportTests(unittest.TestCase):
    def test_portable_pages_include_every_gap_jobs_differences_and_no_absolute_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            with mock.patch.object(reports, "PAGE_SIZE", 2):
                built = reports.build_tool_report(root, result)
            moved = Path(directory) / "detached"
            shutil.copytree(built["directory"], moved)
            summary = json.loads((moved / "summary.json").read_text())
            self.assertEqual(summary["original_gap_count"], 3)
            self.assertEqual(summary["counts"], result["provenance"]["counts"])
            self.assertFalse(summary["chromosomes"][0]["native_equals_accepted"])
            self.assertEqual(summary["chromosomes"][0]["accepted_n_bases"], 12)
            self.assertEqual(summary["native_jobs"][0]["original_gap_ids"], ["gap-1"])
            self.assertEqual(summary["publication_state"], "not_asserted_by_report")
            self.assertFalse(summary["biological_accuracy_validated"])
            self.assertEqual(len(list((moved / "gaps").glob("*.html"))), 2)
            for path in moved.rglob("*.html"):
                parsed = Links()
                parsed.feed(path.read_text())
                for href in parsed.links:
                    url = urlsplit(href)
                    self.assertFalse(url.scheme or url.netloc or url.path.startswith("/"), href)
                    target = (path.parent / unquote(url.path)).resolve()
                    self.assertTrue(target.is_relative_to(moved))
                    self.assertTrue(target.is_file(), href)
                    if url.fragment:
                        linked = Links()
                        linked.feed(target.read_text())
                        self.assertIn(url.fragment, linked.ids)
            self.assertIn("&lt;img", (moved / "native.html").read_text())
            self.assertFalse((root / "05_final").exists())
            self.assertFalse(any(p.suffix in {".fa", ".fasta", ".fq"} for p in moved.rglob("*")))

    def test_changed_result_and_report_are_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            report = reports.build_tool_report(root, result)
            self.assertEqual(reports.build_tool_report(root, result), report)
            Path(report["report"]).write_text("changed report")
            with self.assertRaisesRegex(ValueError, "modified"):
                reports.build_tool_report(root, result)
            (Path(result["staging"]) / "assembly.fa").write_text(">fake\nNNNN\n")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                reports.build_tool_report(root, result)

    def test_unknown_gap_and_outside_native_job_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            final = json.loads((Path(result["staging"]) / "final_path.json").read_text())
            bad = dict(result["provenance"])
            bad["gap_outcomes"] = bad["gap_outcomes"][:-1]
            with self.assertRaisesRegex(ValueError, "omitted or duplicated"):
                reports.summarize(bad, final, [], [], [])
            config = root / "04_refinement/01_degap/03_native" / result["run_id"] / "03.gap_filling/job_manager_config.json"
            data = json.loads(config.read_text())
            data["jobs"][0]["job_dir"] = str(Path(directory) / "outside")
            dump(config, data)
            with self.assertRaisesRegex(ValueError, "leave their attempt"):
                reports.build_tool_report(root, result)

    def test_size_limited_assets_are_explicit_not_broken_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            with mock.patch.object(reports, "MAX_ASSETS_TOTAL", 0):
                built = reports.build_tool_report(root, result)
            summary = json.loads((Path(built["directory"]) / "summary.json").read_text())
            self.assertTrue(all(row["availability"] == "server_only_size_limit" for row in summary["artifacts"]))
            self.assertFalse(list((Path(built["directory"]) / "assets").iterdir()))


if __name__ == "__main__":
    unittest.main()
