"""Frontend rendering, visual hierarchy, security boundary and 8-scenario coverage tests."""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from regenerate_reports import regenerate
from render_overview_report import render_overview
from report_scenarios_fixture import PRIVATE, SCENARIOS, workspace


class SecurityInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.csp = []
        self.scripts = []
        self.external_urls = []
        self.main_close_count = 0
        self._in_script = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        vals = dict(attrs)
        if tag == "meta" and vals.get("http-equiv", "").lower() == "content-security-policy":
            self.csp.append(vals.get("content", ""))
        for attr in ("src", "href", "action", "poster"):
            v = vals.get(attr, "")
            if isinstance(v, str) and re.match(r"^(?:https?:|//)", v, re.I):
                self.external_urls.append((tag, attr, v))
        if tag == "script":
            if "src" in vals:
                raise AssertionError("external script tag forbidden")
            if vals.get("data-cgat-ui") != "1" and vals.get("type") != "application/json":
                raise AssertionError(f"unexpected untrusted script tag: {vals}")
            self._in_script = True
            self._buf = []

    def handle_data(self, data):
        if self._in_script:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "main":
            self.main_close_count += 1
        if tag == "script" and self._in_script:
            body = "".join(self._buf)
            self.scripts.append(body)
            self._in_script = False


class ReportFrontendUITests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.parent = Path(tmp.name)

    def _assert_offline_safe(self, html_text, *, expect_single_main=False):
        ins = SecurityInspector()
        ins.feed(html_text)
        self.assertTrue(ins.csp, "CSP meta tag is required")
        self.assertIn("connect-src 'none'", ins.csp[0])
        self.assertEqual(ins.external_urls, [], f"external URLs found: {ins.external_urls}")
        self.assertNotIn("<script>", html_text)
        for body in ins.scripts:
            if body.startswith("{"):
                continue  # application/json data block
            for bad in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "eval(", "Function(", "http://", "https://"):
                self.assertNotIn(bad, body)
        if expect_single_main:
            self.assertEqual(html_text.count("</main>"), 1)
            self.assertEqual(ins.main_close_count, 1)

    def test_all_eight_scenarios_render_offline_safe_with_visual_sections(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                root = self.parent / scenario
                vm = workspace(root, scenario)
                html = render_overview(vm)
                self._assert_offline_safe(html, expect_single_main=True)
                self.assertIn('data-lang="zh"', html)
                self.assertIn('data-lang-btn="zh"', html)
                self.assertIn('data-lang-btn="en"', html)
                self.assertIn('data-theme-toggle="1"', html)
                self.assertIn('class="wb-sidebar"', html)
                self.assertNotIn('id="improvement-overview"', html)
                self.assertIn('id="pseudomolecule-evolution"', html)
                self.assertIn('id="inputs"', html)
                self.assertIn('id="alignment-q0"', html)
                self.assertIn('id="lgz-baseline"', html)
                self.assertIn('id="refinement-comparison"', html)
                self.assertIn('id="result-files"', html)
                self.assertIn('id="diagnostics-fold"', html)
                self.assertIn('id="ws-tree"', html)
                self.assertIn('data-tree-action="expand"', html)
                self.assertNotIn(PRIVATE, html)
                if scenario == "success":
                    self.assertIn('class="ideo-seg ideo-gap-link', html)
                    self.assertIn('class="gap-job-chip', html)
                    self.assertIn('target="_blank"', html)
                # Ensure top-level directory tree nodes start collapsed (not <details class="tree-node" open>)
                self.assertNotRegex(html, r'<details class="tree-node[^"]*"\s+open\b')

    def test_input_and_assignment_cards_are_first_and_preserve_complete_membership(self):
        from report_lgz_data import assignment_groups
        from render_path_story import assignment_card
        root = self.parent / "story"
        vm = workspace(root, "success")
        model = vm["lgz_summary"]["assignment"]
        self.assertEqual(model["min_coverage_percent"], 12.5)
        self.assertEqual([group["chr"] for group in model["groups"]], ["chr1", "chr2"])
        html = render_overview(vm)
        self.assertLess(html.index('id="inputs"'), html.index('id="chr-groups"'))
        self.assertLess(html.index('id="chr-groups"'), html.index('id="pseudomolecule-evolution"'))
        self.assertEqual(html.count('id="inputs"'), 1)
        self.assertIn("12.5%", html)
        def row(ds, ctg, chrom):
            return dict(dataset_name=ds, seq_name=ctg, assigned_chr_name=chrom)
        rows = [row("A", f"ctg{i}", "chr1") for i in range(202)]
        rows.extend([row("A", "ctg201", "chr2"), row("B", "ctg201", "chr1"), row("B", "<unsafe>", "chr2")])
        groups = assignment_groups(dict(rows=rows, available=True), ["chr2", "chr1", "empty"])
        self.assertEqual([g["member_count"] for g in groups], [2, 203, 0])
        page = assignment_card({"groups": groups})
        self.assertEqual(page.count('class="member multi"'), 2)
        self.assertIn('for="multi-members-only"', page)
        self.assertIn("&lt;unsafe&gt;", page)
        self.assertIn("本次阈值未记录", page)
        self.assertNotIn("<unsafe>", page)
        for table in ({"available": False}, {"available": True, "rows": rows, "preview_only": True},
                      {"available": True, "rows": [], "row_count": 1}):
            self.assertIsNone(assignment_groups(table, ["chr1"]))

    def test_first_repair_keeps_unchanged_chr_and_multiple_local_events_in_one_modal(self):
        from copy import deepcopy
        from render_repair_story import repair_card, DIALOG
        from render_refinement_report import workbench_page
        from report_repair_story import repair_stage
        h0, h1 = "a" * 64, "b" * 64
        def record(sha, size):
            return {"sha256":sha,"sequences":[{"sequence":"chr1","length_bp":size},{"sequence":"chr2","length_bp":50}]}
        def edit(eid, start):
            return {"event_id":eid,"stage":"step1","chr":"chr1","status":"accepted","action":"patch","reason":"selected",
                    "q_before":{"version":"q0","sha256":h0,"start":start,"end":start+9},
                    "q_after":{"version":"q1","sha256":h1,"start":start,"end":start+9},
                    "source":{"dataset":"A","contig":"ctg<1>","start":11,"end":20,"orientation":"-"}}
        facts = {"result":{"stage":"step1","q_input_version":"q0","q_output_version":"q1","q_input_sha256":h0,"q_output_sha256":h1,
                           "events":[edit("first",20),edit("later",50)]},
                 "sequence_versions":{"q0":record(h0,100),"q1":record(h1,100)}}
        scene = repair_stage(facts)
        self.assertEqual([len(row["events"]) for row in scene], [2,0])
        page = workbench_page("报告", "Report", repair_card({"inputs":{"assemblies":[]},"step1_scene":scene}) + DIALOG)
        self._assert_offline_safe(page, expect_single_main=True)
        self.assertEqual(page.count('<dialog id="path-event-dialog"'), 1)
        self.assertEqual(page.count('<template id="step1-inspect-'), 2)
        self.assertIn("未改动", page)
        self.assertIn("ctg&lt;1&gt;", page)
        self.assertNotIn("<polygon", page)  # no recorded anchors
        incomplete = deepcopy(facts)
        incomplete["result"]["report_array_counts"] = {"events":3}
        self.assertIsNone(repair_stage(incomplete))
        foreign = deepcopy(facts)
        foreign["result"]["events"][1]["q_before"]["sha256"] = h1
        with self.assertRaisesRegex(ValueError, "coordinate space"):
            repair_stage(foreign)

    def test_large_scenario_stays_bounded_and_preserves_full_chromosome_heatmap(self):
        root = self.parent / "large"
        vm = workspace(root, "large")
        html = render_overview(vm)
        self._assert_offline_safe(html, expect_single_main=True)
        # 21 chromosomes x 16 gaps = 336 original gaps; preview capped at 200 rows
        self.assertEqual(html.count('data-states="'), 200)
        self.assertIn("200", html)
        self.assertIn("336", html)
        self.assertIn("chr21", html)
        self.assertIn("gap_comparison.tsv", html)
        self.assertLess(len(html.encode("utf-8")), 350_000)

    def test_detached_regeneration_all_pages_pass_security_boundary(self):
        root = self.parent / "success"
        workspace(root, "success")
        out = self.parent / "detached_report"
        regenerate(root, out)
        overview_html = (out / "report.html").read_text(encoding="utf-8")
        self._assert_offline_safe(overview_html, expect_single_main=True)
        self.assertIn("独立便携副本说明", overview_html)
        self.assertIn("data-copy=", overview_html)
        self.assertIn("compact_refinement.py", overview_html)
        self.assertNotIn("../07_delivery", overview_html)
        for html_file in out.rglob("*.html"):
            if "native_visualization" in html_file.parts:
                continue
            text = html_file.read_text(encoding="utf-8")
            self.assertNotIn(PRIVATE, text)
            self._assert_offline_safe(text)

    def test_xss_escaping_in_overview_workspace_name_and_reasons(self):
        root = self.parent / "partial"
        vm = workspace(root, "partial")
        payload = '<script>alert(1)</script><img src=x onerror=alert(2)>'
        vm["meta"]["workspace_name"] = payload
        vm["refinement_summary"]["tools"][1]["reason"] = payload
        html = render_overview(vm)
        self._assert_offline_safe(html, expect_single_main=True)
        self.assertNotIn(payload, html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_detached_regeneration_redacts_legacy_native_visualization_read_paths(self):
        root = self.parent / "legacy_nv"
        workspace(root, "success")
        site = root / "06_report/02_refinement/01_degap"
        nv_page = site / "native_visualization/pages/Global.report.html"
        nv_page.parent.mkdir(parents=True, exist_ok=True)
        nv_page.write_text(f'{{"hifi":[{{"path":"{PRIVATE}"}}]}}', encoding="utf-8")
        nv_manifest = site / "native_visualization/manifest.json"
        nv_manifest.write_text(json.dumps({"schema": "cgat.native-report-view", "files": {}}), encoding="utf-8")
        # Re-seal synthetic tool manifest and publication journal for this test workspace
        import hashlib
        manifest = json.loads((site / "manifest.json").read_text())
        for rel in ("native_visualization/pages/Global.report.html", "native_visualization/manifest.json"):
            manifest["files"][rel] = hashlib.sha256((site / rel).read_bytes()).hexdigest()
        (site / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        new_msha = hashlib.sha256((site / "manifest.json").read_bytes()).hexdigest()
        tx = "3" * 32
        jpath = root / f".runtime/refinement/publications/{tx}/journal.json"
        jdata = json.loads(jpath.read_text())
        jdata["areas"]["report"]["new"]["files"]["manifest.json"] = new_msha
        jpath.write_text(json.dumps(jdata), encoding="utf-8")
        pptr = root / ".runtime/refinement/publication/degap.json"
        pdata = json.loads(pptr.read_text())
        pdata["journal_sha256"] = hashlib.sha256(jpath.read_bytes()).hexdigest()
        pptr.write_text(json.dumps(pdata), encoding="utf-8")
        out = self.parent / "legacy_nv_out"
        regenerate(root, out)
        exported_nv = (out / "02_refinement/01_degap/native_visualization/pages/Global.report.html").read_text(encoding="utf-8")
        self.assertNotIn(PRIVATE, exported_nv)
        self.assertIn("[private reads]", exported_nv)
        detached_nv_manifest = json.loads((out / "02_refinement/01_degap/native_visualization/manifest.json").read_text())
        self.assertEqual(detached_nv_manifest["schema"], "cgat.detached-native-report-view.v1")
        self.assertTrue(detached_nv_manifest["private_reads_redacted"])


if __name__ == "__main__":
    unittest.main()
