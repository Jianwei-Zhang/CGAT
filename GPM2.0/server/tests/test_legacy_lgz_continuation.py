"""Original reviewed controller/cache behavior with controlled scientific commands.

Set CGAT_TEST_LEGACY_SERVER to a git-archived f2ceafb0 Server source. No mapper,
LGZ biological algorithm, environment installation or customer workspace runs.
"""
import hashlib
import importlib.util
import marshal
import struct
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from legacy_lgz_continuation import preview, continue_lgz, check_script_roots
from legacy_lgz_runner import owned, verify_engine
import test_completed_workspace_migration as completed_fixture
import test_run_outer_checkpoints as outer_fixture
write = outer_fixture.write

OLD = os.environ.get("CGAT_TEST_LEGACY_SERVER")


class ContinuationPathTests(unittest.TestCase):
    def test_owned_files_and_reviewed_inventory_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / ".prepare_lib/tools/test.py", "# reviewed\n")
            engine = {"files_sha256": {"tools/test.py": hashlib.sha256(b"# reviewed\n").hexdigest()}}
            verify_engine(root, engine)
            write(root / ".prepare_lib/tools/unreviewed.py", "raise Exception('must not import')\n")
            with self.assertRaisesRegex(ValueError, "unreviewed"):
                verify_engine(root, engine)
            for name in ("../bad", "/bad", "a\\b"):
                with self.assertRaisesRegex(ValueError, "invalid"):
                    owned(root, name)
            (root / "alias").symlink_to(root / ".prepare_lib", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "regular owned"):
                owned(root, "alias/tools/test.py")

    def test_moved_script_roots_are_not_rebased_or_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "current"
            root.mkdir()
            command = root / "command.sh"
            rows = [{"command_relpath": "command.sh"}]
            for text in ("python3 /old/.prepare_lib/tools/lgz_step1.py --server-dir /old\n",
                         "GPM_FAST_WORK_ROOT=/old\n", "python3 local.py --server-dir /old\n"):
                command.write_text(text)
                with self.assertRaisesRegex(ValueError, "must not write another workspace"):
                    check_script_roots(root, rows)
                self.assertEqual(command.read_text(), text)
            command.write_text("python3 " + shlex.quote(str(root / ".prepare_lib/tools/lgz_step1.py"))
                               + " --server-dir " + shlex.quote(str(root)) + "\n")
            self.assertTrue(check_script_roots(root, rows))


@unittest.skipUnless(OLD and Path(OLD).is_dir(), "opt-in exact archived legacy engine required")
class OriginalEngineContinuationTests(unittest.TestCase):
    def workspace(self, directory, *, cached_stage=False):
        root, fake_bin = outer_fixture.OuterCheckpointTests().make_server(Path(directory))
        registry = json.loads((TOOLS.parent / "contracts/legacy_lgz_engines.json").read_text())
        engine = registry["engines"][0]
        for name in engine["files_sha256"]:
            target = root / ".prepare_lib" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(OLD) / name, target)
        rows = [("ref:ds", "runs/ds_vs_ref/command.sh"), ("q0_evidence", "prepare_q0_evidence.sh"),
                ("finalize_evidence", "finalize_grt_evidence.sh"), ("package_full", "package_full_zip.sh"),
                ("package_light", "package_light_zip.sh")]
        write(root / ".run_all/plan.tsv", "unit_id\tcommand_relpath\tdetail_log_relpath\n" +
              "".join(unit + "\t" + command + "\tlogs/run_all.log\n" for unit, command in rows))
        for _unit, command in rows:
            write(root / command, "#!/bin/bash\nset -euo pipefail\necho MUST-NOT-EXECUTE >> forbidden\nexit 91\n")
        write(root / "run_all.sh", "#!/bin/bash\nexit 92\n")
        python = "import sys;sys.path.insert(0," + repr(str(root / ".prepare_lib/tools")) + ");"
        python += "from pathlib import Path;from run_outer_checkpoints import OuterCheckpointManager;"
        python += "m=OuterCheckpointManager(Path(" + repr(str(root)) + "));m.commit(m.prepare('ref:ds','runs/ds_vs_ref/command.sh'))"
        env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}
        committed = subprocess.run([sys.executable, "-I", "-B", "-c", python], env=env, capture_output=True, text=True)
        self.assertEqual(committed.returncode, 0, committed.stderr)
        if cached_stage:
            write(root / "grt/keep.fa", ">kept\nACGT\n")
            result = {"stage": "step1", "input_fingerprint": "agreed"}
            write(root / "grt/result.json", json.dumps(result))
            value = {"workflow": "gpm_grt_precomputed_v2", "stage": "step1", "status": "success",
                     "input_fingerprint": "agreed", "result_relpath": "grt/result.json", "output_hashes":
                     {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in ("grt/keep.fa", "grt/result.json")}}
            write(root / "grt/checkpoints/step1.json", json.dumps(value))
        # Force a controlled interruption, after exercising real child startup
        # and (when requested) the exact original stage cache lookup.
        check = ""
        if cached_stage:
            code = ("from pathlib import Path;import os;from lgz_core.stage_cache import checkpoint_result;"
                    + "r=checkpoint_result(Path(" + repr(str(root)) + "),'step1',os.environ.get('CGAT_TEST_LEGACY_FINGERPRINT','agreed'));"
                    + "assert r is not None;Path('after-cache').write_text('valid')")
            check = "python3 -B -c " + shlex.quote(code) + "\n"
        write(root / "prepare_q0_evidence.sh", "#!/bin/bash\nset -euo pipefail\n" + check + "echo pending >> pending.calls\nexit 7\n")
        return root, env, engine

    def test_failed_prefix_retry_keeps_reference_and_never_runs_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root, env, engine = self.workspace(directory, cached_stage=True)
            original = {str(path): path.read_bytes() for path in (root / ".run_all").glob("checkpoints/*.json")}
            original[str(root / ".run_all/plan.tsv")] = (root / ".run_all/plan.tsv").read_bytes()
            original[str(root / "grt/checkpoints/step1.json")] = (root / "grt/checkpoints/step1.json").read_bytes()
            before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            with patch.dict(os.environ, env):
                prepared = preview(root, TOOLS.parent)
                self.assertEqual(before, {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()})
                self.assertEqual(prepared.summary()["analysis_started"], False)
                public = subprocess.run([sys.executable, "-B", str(TOOLS / "migrate_workspace.py"),
                                         "--server-dir", str(root), "--preview-lgz-continuation"],
                                        env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(public.returncode, 0, public.stderr)
                self.assertEqual(json.loads(public.stdout)["approval_sha256"], prepared.digest)
                for _attempt in range(2):
                    prepared = preview(root, TOOLS.parent)
                    result = continue_lgz(root, TOOLS.parent, prepared.digest, confirm_idle=True)
                    self.assertEqual(result["status"], "failed")
                    self.assertEqual(result["exit_code"], 7)
            self.assertEqual((root / "pending.calls").read_text().splitlines(), ["pending", "pending"])
            self.assertFalse((root / "forbidden").exists())
            self.assertFalse((root / ".runtime/layout.json").exists())
            self.assertFalse((root / ".run_all/lock").exists())
            for name, content in original.items():
                self.assertEqual(Path(name).read_bytes(), content)
            verify_engine(root, engine)
            events = list(root.glob(".run_all/legacy_continuation/*/cache_events.jsonl"))
            self.assertEqual(len(events), 2)
            self.assertTrue(all("ORIGINAL_CACHE_VALID" in path.read_text() for path in events))

    def test_original_stage_cache_miss_stops_before_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root, env, _engine = self.workspace(directory, cached_stage=True)
            env["CGAT_TEST_LEGACY_FINGERPRINT"] = "changed-inputs-or-parameters"
            saved = (root / "grt/checkpoints/step1.json").read_bytes()
            with patch.dict(os.environ, env):
                prepared = preview(root, TOOLS.parent)
                result = continue_lgz(root, TOOLS.parent, prepared.digest, confirm_idle=True)
            self.assertNotEqual(result["exit_code"], 0)
            self.assertEqual((root / "grt/checkpoints/step1.json").read_bytes(), saved)
            self.assertFalse((root / "after-cache").exists())
            self.assertFalse((root / "pending.calls").exists())
            self.assertIn("REFUSED_COMPLETED_CACHE_MISS", next(root.glob(".run_all/legacy_continuation/*/cache_events.jsonl")).read_text())

    def test_q0_cache_miss_barrier_uses_the_exact_original_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root, env, engine = self.workspace(directory)
            write(root / "metadata/grt_q0_evidence.json", "{}")
            code = ("import sys,runpy,json;from pathlib import Path;"
                    + "api=runpy.run_path(" + repr(str(TOOLS / "legacy_lgz_runner.py")) + ");"
                    + "root=Path(" + repr(str(root)) + ");sys.path.insert(0,str(root/'.prepare_lib/tools'));"
                    + "import lgz_core.q0_preparation as q;"
                    + "q._initial_inputs=lambda root: ({},{},[],{},[],[],set());"
                    + "q.executable_identity=lambda tool: {'controlled':True};"
                    + "api['install_cache_fence'](root," + repr(engine) + ",root/'events.jsonl');"
                    + "q.prepare_evidence(root)")
            run = subprocess.run([sys.executable, "-I", "-B", "-c", code], env=env, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("refuses to recompute completed work", run.stderr)
            self.assertIn("REFUSED_COMPLETED_CACHE_MISS", (root / "events.jsonl").read_text())
            self.assertFalse((root / "grt/evidence/q0_prepare").exists())

    @unittest.skipUnless(shutil.which("samtools"), "real frozen source indexing requires samtools")
    def test_finished_prefix_returns_a_separate_applicable_migration_approval(self):
        from migrate_workspace import apply
        from lgz_contract import validate_contract
        from workspace_layout import WorkspaceLayout
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "legacy"
            root.mkdir()
            engine = json.loads((TOOLS.parent / "contracts/legacy_lgz_engines.json").read_text())["engines"][0]
            for name in engine["files_sha256"]:
                target = root / ".prepare_lib" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(OLD) / name, target)
            rows = [("finalize_evidence", "finalize_grt_evidence.sh"),
                    ("package_full", "package_full_zip.sh"), ("package_light", "package_light_zip.sh")]
            write(root / ".run_all/plan.tsv", "unit_id\tcommand_relpath\tdetail_log_relpath\n" +
                  "".join(unit + "\t" + command + "\tlogs/run_all.log\n" for unit, command in rows))
            write(root / "metadata/prepare_options.tsv", "key\tvalue\nthreads\t1\narchive_format\tzip\n")
            write(root / "run_all.sh", "#!/bin/bash\nexit 92\n")
            for name in ("package_full_zip.sh", "package_light_zip.sh"):
                write(root / name, "#!/bin/bash\necho MUST-NOT-EXECUTE > forbidden\nexit 91\n")
            # Produce a genuinely validated frozen scientific packet with a
            # disclosed controlled script. Do not weaken continuation checks to
            # make an exported fixture (which omits raw caches) resumable.
            code = ("import json;from pathlib import Path;from lgz_contract import validate_contract;"
                    + "root=Path(" + repr(str(root)) + ");"
                    + "files=json.loads(Path(" + repr(str(completed_fixture.FIXTURE)) + ").read_text())['files'];"
                    + "[(p.parent.mkdir(parents=True,exist_ok=True),p.write_text(v)) for n,v in files.items() for p in [root/n]];"
                    + "(root/'metadata/grt_contract_summary.json').write_text(json.dumps(validate_contract(root)))")
            write(root / "finalize_grt_evidence.sh", "#!/bin/bash\nset -euo pipefail\npython3 -B -c " + shlex.quote(code) + "\n")
            prepared = preview(root, TOOLS.parent)
            result = continue_lgz(root, TOOLS.parent, prepared.digest, confirm_idle=True)
            self.assertEqual(result["status"], "lgz_complete_ready_for_migration")
            self.assertEqual(WorkspaceLayout.detect(root).version, 1)
            original_contract = validate_contract(root)
            scientific = {p.relative_to(root).as_posix():p.read_bytes() for area in ("data", "metadata", "grt")
                          for p in (root / area).rglob("*") if p.is_file()}
            # The digest remains usable after lock release. No late receipt
            # write may invalidate the next physical migration approval.
            migrated = apply(root, TOOLS.parent, result["migration_approval_sha256"], confirm_idle=True)
            self.assertEqual(migrated["status"], "committed")
            layout = WorkspaceLayout.detect(root)
            self.assertEqual(layout.version, 2)
            self.assertEqual(validate_contract(root), original_contract)
            for name, content in scientific.items():
                self.assertEqual(layout.path(name).read_bytes(), content, name)
            self.assertFalse((root / "forbidden").exists())

    def test_matching_metadata_does_not_make_old_bytecode_trusted(self):
        with tempfile.TemporaryDirectory() as directory:
            root, env, _engine = self.workspace(directory)
            source = root / ".prepare_lib/tools/run_all_runner.py"
            cached = Path(importlib.util.cache_from_source(str(source)))
            info = source.stat()
            header = importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(info.st_mtime), info.st_size)
            payload = header + marshal.dumps(compile("raise RuntimeError('unverified historical bytecode')", str(source), "exec"))
            cached.parent.mkdir(exist_ok=True)
            cached.write_bytes(payload)
            with patch.dict(os.environ, env):
                self.assertTrue(preview(root, TOOLS.parent).summary()["eligible"])
            self.assertEqual(cached.read_bytes(), payload)
            self.assertFalse(list((root / ".run_all").glob("unused-pycache-*")))

    def test_stale_proof_changed_engine_and_approval_do_not_start_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root, env, _engine = self.workspace(directory)
            with patch.dict(os.environ, env):
                prepared = preview(root, TOOLS.parent)
                write(root / "user-note.txt", "changed inventory after approval\n")
                with self.assertRaisesRegex(ValueError, "changed after preview"):
                    continue_lgz(root, TOOLS.parent, prepared.digest, confirm_idle=True)
                write(root / "runs/ds_vs_ref/result.paf", "corrupt completed output\n")
                with self.assertRaisesRegex(ValueError, "refuse to rerun completed outer"):
                    preview(root, TOOLS.parent)
                write(root / ".prepare_lib/tools/lgz_step1.py", "raise RuntimeError('must not execute')\n")
                with self.assertRaisesRegex(ValueError, "no reviewed historical engine"):
                    preview(root, TOOLS.parent)
            self.assertFalse((root / "pending.calls").exists())
            self.assertFalse((root / ".run_all/lock").exists())
