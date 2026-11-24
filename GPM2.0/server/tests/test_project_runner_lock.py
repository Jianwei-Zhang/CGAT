"""The production run.sh launcher must publish both real App archives under its original lock."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from job_final_catalog import publish_catalog
from lgz_final import publish_baseline
from refinement_bundle_fixture import create
from run_all_runner import RunnerError, WorkspaceLock, run_locked_plan
import server_run
from workspace_layout import WorkspaceLayout, initialize_workspace, render_workspace_shell
from refinement_commit import PublicationError, layout_and_lock


class ProjectRunnerLockTests(unittest.TestCase):
    def test_missing_released_foreign_and_replaced_lock_cannot_start_a_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"first"; other=Path(tmp)/"other"
            for p in (root, other): initialize_workspace(p, job_outputs=True, project_delivery=True)
            lock=WorkspaceLock(root,"owner")
            with self.assertRaisesRegex(PublicationError,"held numbered-workspace lock"): layout_and_lock(root,None)
            for invalid in (None,lock):
                with self.assertRaisesRegex(RunnerError,"held workspace lock"): run_locked_plan(root,[],invalid)
            lock.acquire()
            try:
                with self.assertRaisesRegex(RunnerError,"held workspace lock"): run_locked_plan(other,[],lock)
                saved=lock.lock_dir/"owner.json"; original=saved.read_bytes()
                try:
                    saved.write_text("{}")
                    with self.assertRaisesRegex(RunnerError,"held workspace lock"): run_locked_plan(root,[],lock)
                finally:
                    saved.write_bytes(original)
            finally:
                lock.release()
            with self.assertRaisesRegex(RunnerError,"held workspace lock"): run_locked_plan(root,[],lock)

    @unittest.skipUnless(all(shutil.which(t) for t in ("samtools", "minimap2", "zip")), "real project delivery requires closure tools")
    def test_public_launcher_finalizes_and_verifies_project_pair_with_held_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"example"; source=Path(__file__).resolve().parents[1]
            create(root, with_source_evidence=True, job_outputs=True, project_delivery=True, sequence="GTTTAC")
            layout=WorkspaceLayout.detect(root); lock=WorkspaceLock(root,"seed-baseline"); lock.acquire()
            try:
                publish_baseline(root,lock); publish_catalog(root,lock,"1"*32,{})
            finally:
                lock.release()
            runtime=layout.path(".prepare_lib")
            shutil.copytree(source/"tools",runtime/"tools",dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(source/"contracts",runtime/"contracts",dirs_exist_ok=True)
            plan=layout.path(".run_all/plan.tsv"); plan.parent.mkdir(parents=True,exist_ok=True)
            lines=["unit_id\tcommand_relpath\tdetail_log_relpath"]
            for kind in ("full","light"):
                unit="package_"+kind; script=unit+"_zip.sh"; p=layout.path(script); p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(render_workspace_shell((source/"templates"/script).read_text(),layout,script))
                lines.append(f"{unit}\t{p.relative_to(root)}\t.runtime/logs/run_all.log")
            plan.write_text("\n".join(lines)+"\n");layout.path("run_all.sh").write_text("# prepared\n")
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(server_run.execute(["-o",str(root)],source),0)
            proof=json.loads(layout.path(".runtime/refinement/project-delivery/committed.json").read_text())
            self.assertEqual(set(proof["files"]),{"full","light"}); self.assertFalse(proof["tools"])
            for kind,info in proof["files"].items():
                archive=root/"07_delivery"/info["file"]; self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),info["sha256"])
                with zipfile.ZipFile(archive) as z:
                    index=json.loads(z.read(f"{root.name}/project_versions/index.json"));self.assertEqual(index["mode"],kind)
                    self.assertEqual(index["generation"],proof["generation"]);self.assertIsNone(z.testzip())
            self.assertFalse(layout.path(".run_all/lock").exists())
