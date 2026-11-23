"""Public downstream configuration and a real LGZ-only worker (no native fill)."""
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import refinement_config as config
from run_all_runner import WorkspaceLock, Runner, PlanUnit
from workspace_layout import WorkspaceLayout, initialize_workspace
from refinement_bundle_fixture import FIXTURE
from post_lgz_refinement import validate_completion

TOOLS = Path(__file__).resolve().parents[1] / "tools"


class RefinementResultSummaryTests(unittest.TestCase):
    def test_zero_admission_is_explicitly_unchanged_not_an_applied_refinement(self):
        from post_lgz_refinement import final_result_lines
        paths = {"final": Path("05_final/01_degap"), "delivery": Path("07_delivery/01_degap")}
        for accepted in (0, 1):
            with self.subTest(accepted=accepted):
                provenance = {"accepted_edit_count": accepted,
                              "status": "completed" if accepted else "completed_zero_accepted",
                              "counts": {"closed": accepted, "partial": 0, "unfilled": 1 - accepted, "rejected": 0}}
                text = "\n".join(final_result_lines("degap", paths, provenance))
                self.assertIn(f"accepted_edits={accepted}", text)
                self.assertIn("[FINAL PATH] degap: 05_final/01_degap/final_path.json", text)
                self.assertEqual("[REFINED FINAL]" in text, bool(accepted))
                self.assertEqual("UNCHANGED AFTER REFINEMENT; ZERO ACCEPTED EDITS" in text, not accepted)


class RefinementConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        self.layout = initialize_workspace(self.root)
        self.reads = Path(self.temp.name) / "原始 reads.fa"
        self.reads.write_text(">read\nACGT\n")
        metadata = self.layout.path("metadata/prepare_options.tsv")
        metadata.parent.mkdir(parents=True)
        metadata.write_text("key\tvalue\nreads_qc\tlegacy-not-refinement\n")
        self.metadata = metadata

    def test_saved_reads_default_tool_and_one_invocation_none_do_not_rewrite_lgz(self):
        before = self.metadata.read_bytes()
        first = config.save_request(self.root, {"--hifi": [[str(self.reads)]]}, "first")
        self.assertEqual(first["selected"], ["degap"])
        second = config.save_request(self.root, {}, "second")
        self.assertEqual(second["groups"], first["groups"])
        disabled = config.save_request(self.root, {"--gapfill-tools": [["none"]]}, "third")
        self.assertEqual(disabled["selected"], [])
        resumed = config.save_request(self.root, {}, "fourth")
        self.assertEqual(resumed["selected"], ["degap"])
        self.assertEqual(config.load_request(self.root, "first"), first)
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_prepare_saved_config_still_creates_immutable_invocation_snapshot(self):
        stable, _ = config.resolve(self.root, {"--hifi": [[str(self.reads)]]})
        config.atomic_write_json(self.layout.path(config.CONFIG), stable)
        request = config.save_request(self.root, {}, "after-prepare")
        self.assertEqual(config.load_request(self.root, "after-prepare"), request)
        snapshot = self.layout.path(".runtime/refinement/configurations/" + request["configuration_sha256"] + ".json")
        snapshot.write_text("{}")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            config.save_request(self.root, {}, "must-not-repair-tampering")

    def test_explicit_read_selection_replaces_groups_and_unused_technology_is_not_consumed(self):
        config.save_request(self.root, {"--ont": [[str(self.reads)]]}, "first")
        _, request = config.resolve(self.root, {"--hifi": [[str(self.reads)]], "--gapfill-tools": [["tgsgapcloser"]]})
        self.assertEqual(request["groups"]["ont"], [])
        request["groups"]["ont"] = [str(Path(self.temp.name) / "unused-ont-not-present.fq")]
        config.preflight(request, runtime=False)
        with self.assertRaisesRegex(ValueError, "cannot be supplied twice"):
            config.resolve(self.root, {"--hifi": [[str(self.reads)]], "--ont": [[str(self.reads)]]})
        with self.assertRaises(ValueError):
            config.resolve(self.root, {"--gapfill-tools": [["unknown"]]})

    def test_plan_extension_is_owned_and_does_not_change_any_lgz_command(self):
        plan = self.layout.path(".run_all/plan.tsv")
        plan.parent.mkdir(parents=True)
        rows = [("first", "first.sh"), ("finalize_evidence", "finalize_lgz_evidence.sh"), ("package_full", "package_full_zip.sh"), ("package_light", "package_light_zip.sh")]
        original = {}
        for name, script in rows:
            path = self.layout.path(script)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/bash\necho " + name + "\n")
            original[path] = path.read_bytes()
        plan.write_text("unit_id\tcommand_relpath\tdetail_log_relpath\n" + "".join(f"{name}\t{self.layout.relative(script)}\t.runtime/logs/run_all.log\n" for name, script in rows))
        config.ensure_plan(self.root)
        first = plan.read_bytes()
        config.ensure_plan(self.root)
        self.assertEqual(first, plan.read_bytes())
        with plan.open() as stream:
            parsed = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual([row["unit_id"] for row in parsed], ["first", "finalize_evidence", "refinement", "package_full", "package_light"])
        self.assertTrue(all(path.read_bytes() == data for path, data in original.items()))
        command = self.layout.path(config.COMMAND)
        command.write_text("user-custom-script\n")
        with self.assertRaisesRegex(ValueError, "customized"):
            config.ensure_plan(self.root)
        self.assertEqual(command.read_text(), "user-custom-script\n")

    def test_run_sh_saves_downstream_options_separately_and_does_not_reprepare_for_new_reads(self):
        import server_run
        root = Path(self.temp.name) / "fresh-launch"
        ref, assembly = Path(self.temp.name) / "ref.fa", Path(self.temp.name) / "assembly.fa"
        ref.write_text(">chr1\nACGT\n")
        assembly.write_text(">ctg1\nACGT\n")
        prepared_arguments = []
        def prepare(script, argv, output):
            layout = config.WorkspaceLayout.detect(output)
            self.assertEqual(layout.version, 2)
            prepared_arguments.extend(argv)
            command = output / "first.sh"
            command.write_text("#!/bin/bash\nexit 0\n")
            (output / "run_all.sh").write_text("#!/bin/bash\nexit 0\n")
            plan = layout.path(".run_all/plan.tsv")
            plan.write_text("unit_id\tcommand_relpath\tdetail_log_relpath\nfirst\tfirst.sh\t.runtime/logs/run_all.log\n")
            return 0
        with mock.patch.object(server_run, "prepare_workspace", side_effect=prepare) as preparation, mock.patch.object(server_run.Runner, "run", return_value=0), mock.patch.object(server_run, "refinement_preflight"):
            self.assertEqual(server_run.execute(["--ref", str(ref), "--ds", str(assembly), "--hifi", str(self.reads), "-o", str(root)], TOOLS.parent), 0)
            self.assertNotIn("--hifi", prepared_arguments)
            self.assertNotIn("--gapfill-tools", prepared_arguments)
            layout = config.WorkspaceLayout.detect(root)
            launch = json.loads(layout.path(".run_all/launch.json").read_text())
            self.assertEqual(WorkspaceLayout.detect(root).result_prefix, root.name)
            self.assertNotIn("--hifi", launch["options"])
            self.assertNotIn(str(self.reads), launch["inputs"])
            self.reads.write_text(">new-read-content\nTTTT\n")
            self.assertEqual(server_run.execute(["-o", str(root), "--hifi", str(self.reads), "--gapfill-tools", "quartet"], TOOLS.parent), 0)
            self.assertEqual(preparation.call_count, 1)
            saved = json.loads(layout.path(config.CONFIG).read_text())
            self.assertEqual(saved["tools"], "quartet")
            self.assertEqual(saved["groups"]["hifi"], [str(self.reads)])
            ref.write_text(">changed\nTTTT\n")
            with self.assertRaisesRegex(server_run.RunnerError, "Input changed"):
                server_run.execute(["-o", str(root), "--ref", str(ref)], TOOLS.parent)

    def test_interrupted_first_preparation_preserves_downstream_reads_for_out_only_resume(self):
        import server_run
        root = Path(self.temp.name) / "interrupted-launch"
        ref, assembly = Path(self.temp.name) / "ref.fa", Path(self.temp.name) / "assembly.fa"
        ref.write_text(">chr1\nACGT\n")
        assembly.write_text(">ctg1\nACGT\n")
        attempts = []
        def prepare(script, argv, output):
            attempts.append(argv)
            if len(attempts) == 1:
                return 9
            layout = config.WorkspaceLayout.detect(output)
            (output / "run_all.sh").write_text("#!/bin/bash\nexit 0\n")
            (output / "first.sh").write_text("#!/bin/bash\nexit 0\n")
            layout.path(".run_all/plan.tsv").write_text("unit_id\tcommand_relpath\tdetail_log_relpath\nfirst\tfirst.sh\t.runtime/logs/run_all.log\n")
            return 0
        with mock.patch.object(server_run, "prepare_workspace", side_effect=prepare), mock.patch.object(server_run.Runner, "run", return_value=0), mock.patch.object(server_run, "refinement_preflight"):
            self.assertEqual(server_run.execute(["--ref", str(ref), "--ds", str(assembly), "--hifi", str(self.reads), "-o", str(root)], TOOLS.parent), 9)
            self.assertEqual(server_run.execute(["-o", str(root)], TOOLS.parent), 0)
        self.assertEqual(attempts[0], attempts[1])
        self.assertNotIn("--hifi", attempts[0])
        requests = list((root / ".runtime/refinement/requests").glob("*.json"))
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(config.load_request(root, path.stem)["groups"]["hifi"] == [str(self.reads)] for path in requests))

    def test_refinement_failure_keeps_downstream_dispatch_but_pipeline_fails(self):
        self.metadata.write_text("key\tvalue\nthreads\t1\n")
        for native_exit, expected in ((7, 7), (0, 2)):
            with self.subTest(native_exit=native_exit):
                units = []
                for unit_id, body in (("refinement", f"exit {native_exit}"),
                                      ("baseline_delivery_probe", "touch downstream-ran")):
                    path = self.layout.path(f".runtime/commands/{unit_id}.sh")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("#!/bin/bash\nset -euo pipefail\n" + body + "\n")
                    units.append(PlanUnit(unit_id, path.relative_to(self.root).as_posix(), ".runtime/logs/run_all.log"))
                marker = self.root / "downstream-ran"
                marker.unlink(missing_ok=True)
                run_id = f"failure-{native_exit}"
                config.save_request(self.root, {}, run_id)
                lock = WorkspaceLock(self.root, run_id)
                lock.acquire()
                try:
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        code = Runner(self.root, units, run_id, color="never").run()
                finally:
                    lock.release()
                self.assertEqual(code, expected)
                self.assertTrue(marker.is_file())
                with self.layout.path("logs/status.tsv").open() as stream:
                    rows = list(csv.DictReader(stream, delimiter="\t"))
                self.assertEqual([row["state"] for row in rows], ["failed", "success"])
                if native_exit == 0:
                    self.assertIn("terminal validation failed", self.layout.path("logs/run_all.log").read_text())

    def test_standalone_signal_reaches_native_grandchildren_before_return(self):
        ready = Path(self.temp.name) / "native-ready"
        child_ready = Path(self.temp.name) / "grandchild-ready"
        native = "import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path(" + repr(str(child_ready)) + ").write_text(str(os.getpid()));time.sleep(60)"
        worker = f"""import os, subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, '-B', '-c', {native!r}])
while not Path({str(child_ready)!r}).exists():
    time.sleep(.01)
Path({str(ready)!r}).write_text(str(os.getpid()))
time.sleep(60)
"""
        code = "import os,sys;sys.path.insert(0,sys.argv[1]);from post_lgz_refinement import run_child_group;raise SystemExit(run_child_group([sys.executable,'-B','-c',sys.argv[2]],environment=dict(os.environ)))"
        process = subprocess.Popen([sys.executable, "-B", "-c", code, str(TOOLS), worker], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Startup includes importing the installed runtime (slow on shared mounts).
            # The separate SIGTERM completion and descendant-death deadlines remain strict.
            deadline = time.monotonic() + 60
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            if not ready.exists():
                process.terminate()
                out, err = process.communicate(timeout=10)
                self.fail("native process did not become ready: " + out + err)
            grandchild = int(child_ready.read_text())
            process.send_signal(signal.SIGTERM)
            out, err = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 143, out + err)
            deadline = time.monotonic() + 2
            state = Path(f"/proc/{grandchild}/stat")
            while state.exists() and state.read_text().split(") ", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(not state.exists() or state.read_text().split(") ", 1)[1].split()[0] == "Z")
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    def test_run_all_signal_stops_redirected_native_grandchild_before_unlock(self):
        self.metadata.write_text("key\tvalue\nthreads\t1\n")
        ready = Path(self.temp.name) / "runner-native-ready"
        native = "import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path(" + repr(str(ready)) + ").write_text(str(os.getpid()));time.sleep(60)"
        worker = Path(self.temp.name) / "native_worker.py"
        worker.write_text(f"""import subprocess, sys, time
with open({str(Path(self.temp.name) / 'native.log')!r}, 'w') as stream:
    subprocess.Popen([sys.executable, '-B', '-c', {native!r}], stdout=stream, stderr=stream)
time.sleep(60)
""")
        commands = self.layout.path(".runtime/commands")
        commands.mkdir(parents=True)
        (commands / "cancel_probe.sh").write_text("#!/bin/bash\nexec " + shlex.join([sys.executable, "-B", str(worker)]) + "\n")
        (commands / "later.sh").write_text("#!/bin/bash\ntouch must-not-run\n")
        self.layout.path(".run_all/plan.tsv").parent.mkdir(parents=True)
        self.layout.path(".run_all/plan.tsv").write_text("unit_id\tcommand_relpath\tdetail_log_relpath\nrefinement\t.runtime/commands/cancel_probe.sh\t.runtime/logs/run_all.log\nlater\t.runtime/commands/later.sh\t.runtime/logs/run_all.log\n")
        process = subprocess.Popen([sys.executable, "-B", str(TOOLS / "run_all_runner.py"), "--server-dir", str(self.root), "--color", "never"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # Startup includes importing the installed runtime (slow on shared mounts).
            # The separate SIGTERM completion and descendant-death deadlines remain strict.
            deadline = time.monotonic() + 60
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            if not ready.exists():
                process.terminate()
                out, err = process.communicate(timeout=10)
                self.fail("runner native process did not become ready: " + out + err)
            grandchild = int(ready.read_text())
            process.send_signal(signal.SIGTERM)
            out, err = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 143, out + err)
            deadline = time.monotonic() + 2
            state = Path(f"/proc/{grandchild}/stat")
            while state.exists() and state.read_text().split(") ", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(not state.exists() or state.read_text().split(") ", 1)[1].split()[0] == "Z")
            self.assertFalse(self.layout.path(".run_all/lock").exists())
            self.assertFalse((self.root / "must-not-run").exists())
            with self.layout.path("logs/status.tsv").open() as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual([row["state"] for row in rows], ["interrupted", "pending"])
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)

    def test_borrowed_parent_lock_is_checked_and_never_reacquired(self):
        lock = WorkspaceLock(self.root, "owner-fixture")
        lock.acquire()
        try:
            code = "import sys;sys.path.insert(0,sys.argv[1]);from post_lgz_refinement import ParentLock;from pathlib import Path; lock=ParentLock(Path(sys.argv[2]),sys.argv[3]);assert lock.acquired"
            result = subprocess.run([sys.executable, "-B", "-c", code, str(TOOLS), str(self.root), "owner-fixture"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            rejected = subprocess.run([sys.executable, "-B", "-c", code, str(TOOLS), str(self.root), "different-owner"], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(json.loads((lock.lock_dir / "owner.json").read_text()), lock.owner)
        finally:
            lock.release()


@unittest.skipUnless(shutil.which("samtools"), "real baseline source indexing required")
class PublicRefinementWorkerTests(unittest.TestCase):
    def test_completed_lgz_only_worker_publishes_explicit_baseline_without_running_lgz(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            layout = initialize_workspace(root)
            files = json.loads(FIXTURE.read_text())["files"]
            for name, contents in files.items():
                target = layout.path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(contents)
            layout.path("metadata/prepare_options.tsv").write_text("key\tvalue\nthreads\t1\n")
            original = {path: path.read_bytes() for path in root.rglob("*") if path.is_file() and ".runtime/workspace.json" not in str(path)}
            result = subprocess.run([sys.executable, "-B", str(TOOLS / "post_lgz_refinement.py"), "--server-dir", str(root)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((root / "05_final/00_lgz/assembly.fa").is_file())
            overview = (root / "06_report/report.html").read_text()
            self.assertIn("../05_final/00_lgz/assembly.fa", overview)
            self.assertIn("LGZ 基线（非精修结果）", overview)
            self.assertFalse((root / "05_final/01_degap").exists())
            self.assertTrue(all(path.read_bytes() == data for path, data in original.items()))
            completion = next((root / ".runtime/refinement/completions").glob("*.json"))
            run_id = json.loads(completion.read_text())["run_id"]
            self.assertEqual(validate_completion(root, run_id)[0], True)
            overview_file = root / "06_report/report.html"
            overview_file.write_text("modified-overview")
            self.assertEqual(validate_completion(root, run_id)[0], False)
            overview_file.write_text(overview)
            self.assertEqual(validate_completion(root, run_id)[0], True)
            (root / "05_final/00_lgz/assembly.fa").write_text(">fake\nNN\n")
            self.assertEqual(validate_completion(root, run_id)[0], False)
            self.assertFalse((root / ".runtime/run_all/lock").exists())


if __name__ == "__main__":
    unittest.main()
