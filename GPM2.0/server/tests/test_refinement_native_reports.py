"""Portable native HTML closure using the pinned visualizers, not native biology."""
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import refinement_reports as reports
import refinement_native_reports as visual
from test_refinement_reports import fixture, dump
import native_visualizer_fixture as native_fixture


class Documents(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.frames, self.csp = [], [], []
    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        for name in ("href", "src"):
            if values.get(name):
                self.links.append(values[name])
        if tag == "iframe":
            self.frames.append(values)
        if tag == "meta" and values.get("http-equiv", "").lower() == "content-security-policy":
            self.csp.append(values["content"])


def closed_site(test, site):
    for path in site.rglob("*.html"):
        doc = Documents()
        doc.feed(path.read_text())
        for name in doc.links:
            url = urlsplit(name)
            test.assertFalse(url.scheme or url.netloc or url.path.startswith("/"), name)
            target = (path.parent / unquote(url.path)).resolve()
            test.assertTrue(target.is_relative_to(site.resolve()), name)
            test.assertTrue(target.is_file(), name)
        for frame in doc.frames:
            test.assertEqual(frame["sandbox"], "allow-scripts")
            test.assertEqual(frame["referrerpolicy"], "no-referrer")
            test.assertNotIn("allow-same-origin", frame["sandbox"])
            test.assertTrue(doc.csp)


def native(root, run_id):
    return root / "04_refinement/01_degap/03_native" / run_id


class NativeReportTests(unittest.TestCase):
    def test_actual_global_and_both_job_reports_detach_without_changing_native_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            original_native = native_fixture.create(native(root, result["run_id"]))
            before = {p:p.read_bytes() for p in original_native.rglob("*.html")}
            gaps = json.loads((original_native / "03.gap_filling/gap_filling_results.json").read_text())["gaps"]
            changed = json.loads(json.dumps(gaps));changed[0]["gap_start"] += 1
            with self.assertRaisesRegex(ValueError, "differs from current native gap"):
                visual.global_details((original_native / "05.visualization/Global.report.html").read_bytes(), changed)
            with patch.object(reports, "PAGE_SIZE", 2), patch("subprocess.Popen", side_effect=AssertionError("report cannot rerun native science")):
                built = reports.build_tool_report(root, result)
            site = Path(directory) / "detached"
            shutil.copytree(built["directory"], site)
            for source, content in before.items():
                self.assertEqual(source.read_bytes(), content)
            summary = json.loads((site / "summary.json").read_text())
            view = summary["native_visualization"]
            self.assertEqual(summary["original_gap_count"], 3)
            self.assertEqual(view["status"], "available")
            self.assertEqual({row["name"] for row in view["views"] if "wrapper_path" in row},
                             {"Global.report.html", "chr1.1.left.html", "chr1.1.right.html"})
            self.assertTrue((site / "native_visualization/index-2.html").is_file())
            self.assertEqual(sum(row.get("transformations", {}).get("removed_unused_external_scripts", 0) for row in view["views"]), 2)
            self.assertTrue(all(source["binding"] == "observed_diagnostic" for row in view["views"] for source in row["sources"]))
            for row in view["views"]:
                if "display_path" in row:
                    self.assertEqual(reports.digest(site / row["display_path"]), row["display_sha256"])
                for source in row["sources"]:
                    raw = site / "native_visualization" / source["raw_report_path"]
                    self.assertEqual(reports.digest(raw), source["sha256"])
            root.rename(root.with_name("original-server-is-not-at-its-old-path"))
            closed_site(self, site)
            self.assertIn("offline", (site / "native.html").read_text().lower())
            self.assertFalse(any(p.suffix in {".fa", ".fasta", ".fq"} for p in site.rglob("*")))

    @unittest.skipUnless(shutil.which("node"), "light native JS VM check requires Node, not a browser")
    def test_actual_inline_js_parses_and_language_controls_run_without_chartjs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            native_fixture.create(native(root, result["run_id"]))
            built = reports.build_tool_report(root, result)
            site = Path(built["directory"])
            samples = []
            for name in ("Global.report.html", "chr1.1.left.html"):
                text = (site / "native_visualization/pages" / name).read_text()
                parser = visual.Inspector(text.replace('<meta http-equiv="Content-Security-Policy" content="' + escape(visual.CSP, quote=True) + '">', ''), [],
                                          {"Global.report.html", "chr1.1.left.html", "chr1.1.right.html"})
                parser.feed(text.replace('<meta http-equiv="Content-Security-Policy" content="' + escape(visual.CSP, quote=True) + '">', ''))
                samples.append({"name":name, "code":"\n".join(parser.scripts)})
            code = r"""
const vm = require('node:vm');
let input='';process.stdin.setEncoding('utf8');process.stdin.on('data',x=>input+=x);process.stdin.on('end',()=>{
 for (const sample of JSON.parse(input)) {
  const en={style:{}}, zh={style:{}};
  const context=vm.createContext({console,document:{addEventListener(){},querySelectorAll(q){return q==='.lang-en'?[en]:q==='.lang-zh'?[zh]:[];}},event:{target:{classList:{add(){}}}},window:{}});
  vm.runInContext(sample.code,context,{timeout:2000});
  if (sample.name==='Global.report.html') {
   context.switchLanguage('zh');if(en.style.display!=='none'||zh.style.display!=='') throw Error('language handler did not run');
   if(typeof context.formatBP(1234)!=='string') throw Error('native formatter is missing');
  } else {
   const title=vm.runInContext("currentLanguage='en';t('header.title')",context);
   if(!title.includes('Visualization')) throw Error('native child translations are missing');
  }
 }
 console.log('native inline JS and language checks passed without Chart.js');
});
"""
            run = subprocess.run([shutil.which("node"), "-e", code], input=json.dumps(samples), capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("passed without Chart.js", run.stdout)

    def test_missing_detail_and_unapproved_script_remain_explicit_and_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            home = native(root, result["run_id"])
            gaps = home / "03.gap_filling/gap_filling_results.json"
            value = json.loads(gaps.read_text())
            value["gaps"].append({"chromosome":"chr1", "gap_id":2, "gap_start":14, "gap_end":20, "filled":False})
            dump(gaps, value)
            result["provenance"]["execution"]["artifacts"][gaps.relative_to(root).as_posix()] = reports.digest(gaps)
            dump(Path(result["staging"]) / "provenance.json", result["provenance"])
            marker = root / "04_refinement/01_degap/02_jobs" / result["run_id"] / "invocation.json"
            payload = json.loads(marker.read_text());payload["provenance_sha256"] = reports.digest(Path(result["staging"]) / "provenance.json");dump(marker, payload)
            native_fixture.create(home)
            for name in ("03.gap_filling/chr1.1.left/visualization_output/gapfiller_report.html", "05.visualization/chr1.1.left.html"):
                path = home / name
                path.write_text(path.read_text().replace("</head>", '<script src="https://unapproved.invalid/a.js"></script></head>'))
            built = reports.build_tool_report(root, result)
            site = Path(built["directory"])
            views = {row["name"]:row for row in json.loads((site / "summary.json").read_text())["native_visualization"]["views"]}
            self.assertEqual(views["chr1.1.left.html"]["availability"], "unsupported_native_display")
            self.assertEqual(views["chr1.2.left.html"]["availability"], "native_report_not_generated")
            for name in ("chr1.1.left.html", "chr1.2.left.html"):
                self.assertIn("No native result is invented", (site / "native_visualization/pages" / name).read_text())
            self.assertIn("wrapper_path", views["Global.report.html"])
            closed_site(self, site)

    def test_native_view_quota_cannot_publish_a_dangling_overview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            native_fixture.create(native(root, result["run_id"]))
            prepare = visual.prepare
            def tiny(*args, **kwargs):
                kwargs["remaining_budget"] = 1
                return prepare(*args, **kwargs)
            with patch.object(visual, "prepare", side_effect=tiny):
                built = reports.build_tool_report(root, result)
            site = Path(built["directory"])
            view = json.loads((site / "summary.json").read_text())["native_visualization"]
            self.assertEqual(view["status"], "not_available")
            self.assertFalse((site / "native_visualization/pages/Global.report.html").exists())
            closed_site(self, site)

    def test_large_job_display_cannot_evict_overview_or_duplicate_source_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            native_fixture.create(native(root, result["run_id"]))
            artifacts, _jobs, _gaps = reports.native_diagnostics(root, "degap", result["run_id"], result["provenance"]["execution"])
            assets = reports.asset_plan(root, artifacts)
            duplicated = [row for row in assets if row["workspace_path"].endswith(("/05.visualization/chr1.1.left.html", "/chr1.1.left/visualization_output/gapfiller_report.html"))]
            self.assertEqual(len(duplicated), 2)
            self.assertEqual(duplicated[0]["report_path"], duplicated[1]["report_path"])
            self.assertLess(reports.embedded_size(assets), sum(row["size_bytes"] for row in assets if "report_path" in row))
            prepare = visual.prepare
            def limited(*args, **kwargs):
                # The real overview is smaller than either real child report.
                # Leave room for it and a placeholder, not all child JS bodies.
                kwargs["remaining_budget"] = 100000
                return prepare(*args, **kwargs)
            with patch.object(visual, "prepare", side_effect=limited):
                built = reports.build_tool_report(root, result)
            site = Path(built["directory"])
            view = json.loads((site / "summary.json").read_text())["native_visualization"]
            overview = next(row for row in view["views"] if row["name"] == "Global.report.html")
            self.assertEqual(overview["availability"], "offline_interactive")
            self.assertTrue(any(row["availability"] == "server_only_display_size_limit" for row in view["views"]))
            closed_site(self, site)

    def test_index_navigation_is_bounded_and_keeps_neighbours_reachable(self):
        self.assertEqual(visual.nearby_pages(0, 1), [0])
        for index in (0, 2500, 4999):
            links = visual.nearby_pages(index, 5000)
            self.assertLessEqual(len(links), 5)
            self.assertIn(index, links)
            self.assertIn(0, links)
            self.assertIn(4999, links)
            if index < 4999:
                self.assertIn(index + 1, links)
            if index:
                self.assertIn(index - 1, links)

    def test_failure_report_links_native_views_without_claiming_a_final_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            result = fixture(root)
            native_fixture.create(native(root, result["run_id"]))
            built = reports.build_failure_report(root, "degap", result["run_id"], RuntimeError("controlled admission failure"), phase="admission")
            site = Path(built["directory"])
            summary = json.loads((site / "summary.json").read_text())
            self.assertFalse(summary["final_available"])
            self.assertEqual(summary["native_visualization"]["status"], "available")
            self.assertIn("native_visualization/index.html", (site / "report.html").read_text())
            closed_site(self, site)

    def test_plain_diagnostic_names_are_not_mistaken_for_network_calls(self):
        source = b'<html><head><title>diagnostic</title><style>path{fill:url(#gradient)}</style></head><body><script>const chromosome="fetch";const folder="Worker";</script></body></html>'
        managed, _changes = visual.transform(source, [], [])
        self.assertIn(b'chromosome="fetch"', managed)
        with self.assertRaisesRegex(ValueError, "unsupported browser/network"):
            visual.transform(source.replace(b'const chromosome="fetch";', b'fetch("https://unapproved.invalid");'), [], [])

    def test_non_html_tool_outputs_and_unknown_html_are_not_promoted(self):
        for tool in ("tgsgapcloser", "quartet", "lrgapcloser"):
            plan = visual.prepare(tool, "native", [], [], [], lambda *_:self.fail("no HTML may be read"), remaining_budget=1000)
            self.assertEqual(plan.binding["reason"], "not_generated_by_pinned_tool")
            self.assertEqual(plan.binding["status"], "not_available")
            self.assertFalse(any(name.startswith("pages/") for name in plan.files))


@unittest.skipUnless(shutil.which("samtools"), "real serializer/source indexing requires samtools")
class NativeReportDeliveryTests(unittest.TestCase):
    def test_full_and_light_keep_the_same_detached_native_visualization(self):
        from refinement_bundle_fixture import create
        from refinement_bundle_validate import validate_payload
        with tempfile.TemporaryDirectory() as directory:
            result, full, light = create(Path(directory) / "workspace", native_diagnostics=native_fixture.create)
            self.assertEqual(validate_payload(full, full=True)["assemblies"], validate_payload(light, full=False)["assemblies"])
            full_files = {p.relative_to(full / "report").as_posix():p.read_bytes() for p in (full / "report").rglob("*") if p.is_file()}
            light_files = {p.relative_to(light / "report").as_posix():p.read_bytes() for p in (light / "report").rglob("*") if p.is_file()}
            self.assertEqual(full_files, light_files)
            self.assertIn("native_visualization/pages/Global.report.html", full_files)
            self.assertTrue(any(name.endswith(".right.html") for name in full_files))
            closed_site(self, full / "report")
            closed_site(self, light / "report")
