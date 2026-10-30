"""Logging is a view: report facts, cache markers and raw diagnostics must survive."""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from run_progress import ProgressDisplay, colorize, plain, use_color
from view_run_log import tail
import test_run_all_runner as fixtures
from types import SimpleNamespace
from run_all_runner import GRT_CACHE_MARKERS, Runner


class ProgressTests(unittest.TestCase):
    def test_runner_normalizes_legacy_cache_markers_without_changing_raw_logs(self):
        for name in ("GRT", "LGZ"):
            with self.subTest(name=name):
                runner = Runner.__new__(Runner)
                runner.minimap2_failure_hints = {}
                runner.log_handle = io.StringIO()
                runner.report = None
                runner.progress = Mock()
                runner.run_id = "legacy-prefix"
                runner.child_cache_markers = set()
                line = f"{name} step3 cache hit: cached artifacts"
                runner._child_line(SimpleNamespace(unit_id="grt_step3"), line)
                self.assertEqual(runner.child_cache_markers, set(GRT_CACHE_MARKERS["grt_step3"]))
                self.assertIn(line, runner.log_handle.getvalue())

    def test_legacy_and_current_algorithm_prefixes_share_progress_parsing(self):
        for name in ("GRT", "LGZ"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                stream = io.StringIO()
                with ProgressDisplay(Path(temp) / "progress.log", {}, stream=stream) as view:
                    view.child("grt_step3", f"{name} step3 execution: profile=optimized chromosomes=1")
                    view.child("grt_step3", f"{name} step3 MUMmer Chr01: cache hit")
                    view.child("grt_step3", f"{name} step3 Chr01 artifact metrics: seconds=1")
                self.assertIn("1/1 chromosomes · computed=0 cached=1", stream.getvalue())
                self.assertNotIn("artifact metrics", stream.getvalue())

    def display(self, root, **kwargs):
        return ProgressDisplay(root / "progress.log", {"grt_step3": "07/28"}, **kwargs)

    def test_metrics_reduced_progress_deduplicated_and_errors_never_hidden(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = [0.0]
            stream = io.StringIO()
            with self.display(Path(temp), stream=stream, clock=lambda: clock[0]) as view:
                view.event("START", "grt_step3", "attempt=2 command=run.sh")
                view.child("grt_step3", "LGZ step3 execution: profile=optimized shared_workers=32 chromosomes=3")
                view.child("grt_step3", "LGZ step3 MUMmer Chr12: computed")
                view.child("grt_step3", "LGZ step3 MUMmer Chr02: cache hit")
                view.child("grt_step3", "LGZ step3 MUMmer Chr02: cache hit")
                metric = "LGZ step3 Chr12 artifact metrics: copy_seconds=0.046 post_copy_parse_seconds=0.000 parse_reused=True"
                view.child("grt_step3", metric)
                view.child("grt_step3", "LGZ step3 MUMmer Chr12 1/2: START")
                view.child("grt_step3", "LGZ step3 screen Chr12 1/2: SUCCESS (0.03s)")
                view.child("grt_step3", "LGZ step3 MUMmer Chr12: 2/2 partitions, workers=2, nucmer_threads=1, thread_budget=32")
                self.assertNotIn("Chr12 1/2", stream.getvalue())
                self.assertNotIn("nucmer_threads", stream.getvalue())
                view.child("grt_step3", "LGZ step3 MUMmer Chr12 1/2: FAILED bad coords")
                self.assertIn("FAILED bad coords", stream.getvalue())
                self.assertNotIn("artifact metrics", stream.getvalue())
                self.assertEqual(stream.getvalue().count("[PROGRESS]"), 1)
                clock[0] = 6.0
                view.tick()
                self.assertIn("2/3 chromosomes · computed=1 cached=1", stream.getvalue())
                view.child("grt_step3", metric + " WARNING: missing artifact")
                view.child("grt_step3", "Traceback (most recent call last):")
                view.child("grt_step3", "  file.py, line 12")
                view.child("grt_step3", "RuntimeError: bad <source>")
                view.child("grt_step3", "LGZ step3 MUMmer Chr15: computed")
                view.event("FAILED", "grt_step3", "exit_code=1 detail=logs/run_all.log")
                output = stream.getvalue()
                self.assertIn("3/3 chromosomes · computed=2 cached=1", output)
                self.assertIn("[WARN]", output)
                self.assertIn("RuntimeError: bad <source>", output)
                self.assertIn("file.py, line 12", output)
                self.assertIn("exit_code=1 detail=logs/run_all.log", output)
                self.assertNotIn("[CHILD]", output)
                self.assertNotIn("LGZ step3 execution", output)

    def test_heartbeat_partial_flush_stop_and_midnight(self):
        with tempfile.TemporaryDirectory() as temp:
            clock = [0.0]
            now = [datetime(2026, 10, 26, 23, 59, 59, tzinfo=timezone.utc)]
            stream = io.StringIO()
            with self.display(Path(temp), stream=stream, clock=lambda: clock[0], now=lambda: now[0]) as view:
                view.event("START", "grt_step3", "attempt=1")
                view.child("grt_step3", "LGZ step3 MUMmer Chr1: computed")
                view.child("grt_step3", "LGZ step3 MUMmer Chr2: computed")
                # Flush a partial count on failure, not a fabricated completed total.
                view.event("FAILED", "grt_step3", "exit_code=2")
                self.assertIn("2 chromosomes", stream.getvalue())
                view.event("START", "grt_step3", "attempt=2")
                clock[0] = 61.0
                now[0] += timedelta(seconds=61)
                view.tick()
                self.assertIn("Date: 2026-10-27", stream.getvalue())
                self.assertIn("still running · elapsed 1m 1s", stream.getvalue())
                view.event("SUCCESS", "grt_step3", "elapsed=61.000s")
                before = stream.getvalue()
                clock[0] = 200.0
                view.tick()
                self.assertEqual(stream.getvalue(), before)

    def test_colors_only_on_stdout_auto_no_color_and_plain_persistent_log(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(use_color("auto", io.StringIO()))
            class TTY(io.StringIO):
                def isatty(self):
                    return True
            self.assertTrue(use_color("auto", TTY()))
            with patch.dict(os.environ, {"NO_COLOR": ""}):
                self.assertFalse(use_color("auto", TTY()))
                self.assertTrue(use_color("always", TTY()))
            with patch.dict(os.environ, {"TERM": "dumb"}):
                self.assertFalse(use_color("auto", TTY()))
        with tempfile.TemporaryDirectory() as temp:
            stream = io.StringIO()
            with self.display(Path(temp), stream=stream, color="always") as view:
                view.event("START", "grt_step3", "attempt=1")
                view.child("grt_step3", "\x1b[31mERROR: diagnostic\x1b[0m")
            saved = (Path(temp) / "progress.log").read_text()
            self.assertIn("\x1b[", stream.getvalue())
            self.assertNotIn("\x1b", saved)
            self.assertEqual(plain(stream.getvalue()), saved)
        self.assertEqual(plain("\x1b]0;title\x07[START]"), "[START]")
        self.assertEqual(plain(colorize("[FAILED] text", True)), "[FAILED] text")

    def test_live_heartbeat_thread_stops_and_parallel_counts_stay_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            stream = io.StringIO()
            with self.display(Path(temp), stream=stream, heartbeat=.01) as view:
                view.event("START", "grt_step3", "attempt=1")
                view.event("START", "other", "attempt=1")
                view.child("grt_step3", "LGZ step3 MUMmer Chr1: computed")
                view.child("other", "LGZ step3 MUMmer Chr1: cache hit")
                view.event("SUCCESS", "other", "elapsed=0.01s")
                for _ in range(150):
                    if "[RUNNING] [grt_step3]" in stream.getvalue():
                        break
                    time.sleep(.01)
                self.assertIn("[RUNNING] [grt_step3]", stream.getvalue())
                self.assertNotIn("[RUNNING] [other]", stream.getvalue())
                self.assertIn("computed=1 cached=0", stream.getvalue())
                self.assertIn("computed=0 cached=1", stream.getvalue())
                self.assertTrue(view.thread.is_alive())
            self.assertFalse(view.thread.is_alive())

    def test_cache_details_and_zero_time_are_compact_only(self):
        with tempfile.TemporaryDirectory() as temp:
            stream = io.StringIO()
            with self.display(Path(temp), stream=stream) as view:
                view.event("SKIP_VALID", "grt_step3", "elapsed=0.000s checkpoint=long/path")
                view.child("grt_step3", "LGZ step3 cache hit: " + "a" * 64)
                view.event("CACHE_HIT", "grt_step3", "elapsed=1.223s full checkpoint details")
                view.event("SUCCESS", "grt_step3", "elapsed=1.223s")
            self.assertIn("[CACHED]", stream.getvalue())
            self.assertIn("cached · 1.2s", stream.getvalue())
            self.assertNotIn("a" * 64, stream.getvalue())
            self.assertNotIn("0.000", stream.getvalue())

    def test_read_only_viewer_tail_and_follow_rotation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "logs").mkdir()
            log = root / "logs/progress.log"
            log.write_text("old\n" + "x" * 70000 + "\n[DONE] 你好\n")
            with log.open("rb") as handle:
                self.assertEqual(tail(handle, 1), ["[DONE] 你好"])
                self.assertEqual(tail(handle, 0), [])
            original = log.read_bytes()
            result = subprocess.run([sys.executable, str(TOOLS / "view_run_log.py"), "--server-dir", str(root), "-n", "1", "--color", "always"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("\x1b[32m[DONE]", result.stdout)
            self.assertEqual(log.read_bytes(), original)
            output = root / "viewer.out"
            with output.open("w") as handle:
                process = subprocess.Popen([sys.executable, str(TOOLS / "view_run_log.py"), "--server-dir", str(root), "-n", "1", "-f", "--color", "never"], stdout=handle, stderr=subprocess.PIPE, text=True)
                try:
                    def wait_for(text):
                        for _ in range(100):
                            if text in output.read_text():
                                return
                            time.sleep(.02)
                        self.fail(f"viewer missing {text}: {output.read_text()}")
                    wait_for("你好")
                    with log.open("a") as writer:
                        writer.write("[START] appended\n")
                    wait_for("appended")
                    log.write_text("[START] truncated\n")
                    wait_for("truncated")
                    log.rename(root / "old.log")
                    log.write_text("[DONE] rotated\n")
                    wait_for("rotated")
                finally:
                    process.terminate()
                    process.communicate(timeout=5)


class ReportCompatibilityTests(unittest.TestCase):
    def test_compact_detailed_report_equivalence_success_and_failure(self):
        for code in (0, 7):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                records = []
                for style in ("compact", "detailed"):
                    parent = root / style
                    parent.mkdir()
                    metric = "LGZ step3 Chr12 artifact metrics: copy_seconds=0.046 post_copy_parse_seconds=0.000 parse_reused=True"
                    script = f"echo '{metric}'\necho 'LGZ step3 cache hit: fixture'\nprintf '\\033[31mWARNING: <source> & detail\\033[0m\\n'\necho 'diagnostic continuation'\nexit {code}"
                    server = fixtures.RunAllRunnerTests().make_workspace(parent, [("example", script)])
                    result = subprocess.run([sys.executable, str(fixtures.RUNNER), "--server-dir", str(server), "--log-style", style, "--color", "always"], capture_output=True, text=True)
                    self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                    detailed = (server / "logs/run_all.log").read_text()
                    progress = (server / "logs/progress.log").read_text()
                    self.assertIn(metric, detailed)
                    self.assertNotIn(metric, progress)
                    self.assertEqual(metric in result.stdout, style == "detailed")
                    self.assertNotIn("\x1b", detailed + progress)
                    self.assertIn("WARNING: <source> & detail", progress)
                    manifest = json.loads((server / "report/manifest.json").read_text())
                    record = json.loads((server / "report" / manifest["steps"][0]).read_text())
                    self.assertIn(metric, record["output_tail"])
                    self.assertIn("LGZ step3 cache hit: fixture", record["output_tail"])
                    self.assertEqual(record["status"], "success" if code == 0 else "failed")
                    self.assertNotIn("\x1b", json.dumps(record, ensure_ascii=False))
                    html = (server / "report/report.html").read_text()
                    self.assertNotIn("\x1b", html)
                    self.assertIn("parse_reused=True", html)
                    records.append(record)
                for key in ("status", "execution", "output_tail", "facts"):
                    self.assertEqual(records[0].get(key), records[1].get(key), key)
                self.assertEqual([h["event"] for h in records[0]["history"]], [h["event"] for h in records[1]["history"]])


if __name__ == "__main__":
    unittest.main()
