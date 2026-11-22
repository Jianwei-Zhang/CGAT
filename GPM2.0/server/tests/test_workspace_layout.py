"""Numbered paths and recoverable physical migration, not an end-to-end adapter."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
from workspace_layout import (LAYOUT_VERSION, MANIFEST, MIGRATION, LayoutError,
                              WorkspaceLayout, canonical_relative, migration_validation)
import workspace_migration
from workspace_migration import MigrationTransaction, durable_json, plan_migration, json_digest
from run_all_runner import WorkspaceLock, RunnerError, load_plan
from migration_lock import MigrationLock
from run_resources import update_resources, read_resources


class LayoutTests(unittest.TestCase):
    def test_mapping_is_component_bounded_and_idempotent(self):
        expected = {
            "data/reference/ref.fa": "01_inputs/01_reference/ref.fa",
            "data/datasets/ds.fa.fai": "01_inputs/02_assemblies/ds.fa.fai",
            "data/reads/reads.fq": "01_inputs/03_reads/reads.fq",
            "data/degap/post_lgz.fa": "04_refinement/01_degap/04_accepted/post_lgz.fa",
            "runs/chr_chr1/ds/result.paf": "02_alignments/chr_chr1/ds/result.paf",
            "metadata/package.tsv": ".runtime/metadata/package.tsv",
            "grt/q/q0.fa": "03_lgz/01_q0/q0.fa",
            "grt/q/q1.fa.fai": "03_lgz/02_step1/q1.fa.fai",
            "grt/q/q2.fa.sha256": "03_lgz/03_step2/q2.fa.sha256",
            "grt/q/.q1.fa.tmp.123": "03_lgz/02_step1/.q1.fa.tmp.123",
            "grt/q/q3.fa": "03_lgz/04_step3/q3.fa",
            "grt/q/q4.fa": "03_lgz/04_step3/q4.fa",
            "grt/checkpoints/step3.json": ".runtime/checkpoints/lgz/step3.json",
            "grt/evidence/events.jsonl": "03_lgz/05_evidence/events.jsonl",
            "run_lgz_step3.sh": ".runtime/commands/run_lgz_step3.sh",
            "assign_chr_groups.sh": ".runtime/commands/assign_chr_groups.sh",
            "finalize_lgz_evidence.sh": ".runtime/commands/finalize_lgz_evidence.sh",
            "report/report.html": "06_report/01_lgz/report.html",
            ".prepare_lib/tools/a.py": ".runtime/prepared/tools/a.py",
            ".run_all/plan.tsv": ".runtime/run_all/plan.tsv",
            "run_all.sh": "run_all.sh",
            "commands/ref:ds.sh": "commands/ref:ds.sh",
            "my_metadata/report.txt": "my_metadata/report.txt",
        }
        for source, target in expected.items():
            with self.subTest(source=source):
                self.assertEqual(canonical_relative(source), target)
                self.assertEqual(canonical_relative(target), target)

    def test_unsafe_paths_are_rejected(self):
        for value in ("", "/etc/passwd", "../x", "a/../x", "a//x", "a/./x", "a/", "C:/x", "a\\x", "x\ny"):
            with self.subTest(value=value), self.assertRaises(LayoutError):
                canonical_relative(value)

    def test_legacy_paths_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = WorkspaceLayout.detect(root)
            self.assertEqual(layout.version, 1)
            self.assertEqual(layout.path("metadata/package.tsv"), root / "metadata/package.tsv")
            self.assertEqual(list(root.iterdir()), [])

    def test_strict_manifest_and_pending_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            layout = WorkspaceLayout(root, 2)
            durable_json(root / MANIFEST, layout.manifest())
            self.assertEqual(WorkspaceLayout.detect(root).version, 2)
            for value in ([], {}, {**layout.manifest(), "layout_version": True},
                          {**layout.manifest(), "layout_version": 3},
                          {**layout.manifest(), "state": "building"}):
                durable_json(root / MANIFEST, value)
                with self.assertRaises(LayoutError):
                    WorkspaceLayout.detect(root)
            durable_json(root / MANIFEST, layout.manifest())
            durable_json(root / MIGRATION, {"state": "moving"})
            with self.assertRaisesRegex(LayoutError, "migration"):
                WorkspaceLayout.detect(root)

    def test_committed_migration_cannot_fall_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            durable_json(root / MIGRATION, {"schema": "cgat.workspace-migration", "from_version": 1,
                         "to_version": 2, "state": "committed", "id": "a" * 32})
            with self.assertRaisesRegex(LayoutError, "missing"):
                WorkspaceLayout.detect(root)
            durable_json(root / MANIFEST, {**WorkspaceLayout(root, 2).manifest(), "migration_id": "b" * 32})
            with self.assertRaisesRegex(LayoutError, "disagrees"):
                WorkspaceLayout.detect(root)

    def test_no_parent_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / "01_inputs").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(LayoutError, "symlink"):
                WorkspaceLayout(root, 2).path("data/reference/ref.fa")
            (root / ".runtime").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(LayoutError):
                WorkspaceLayout.detect(root)

    def test_tool_paths_stable_for_single_and_multiple_tools(self):
        layout = WorkspaceLayout(Path("/tmp/example"), 2)
        for area in ("04_refinement", "05_final", "07_delivery"):
            self.assertEqual(layout.tool_relative(area, "quartet"), area + "/03_quartet")
        self.assertEqual(layout.tool_relative("05_final", "lgz"), "05_final/00_lgz")
        with self.assertRaises(LayoutError):
            layout.tool_relative("04_refinement", "lgz")
        with self.assertRaises(LayoutError):
            layout.tool_relative("05_final", "../../x")


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "workspace"
        self.root.mkdir()
        self.put("run_all.sh", "#!/bin/bash\necho legacy\n")
        self.put(".run_all/plan.tsv", "unit_id\tcommand_relpath\tdetail_log_relpath\ngrt_step3\trun_lgz_step3.sh\tlogs/run_all.log\n")
        self.put("run_lgz_step3.sh", "#!/bin/bash\nexit 0\n")
        self.put("metadata/prepare_options.tsv", "key\tvalue\nthreads\t4\n")
        self.put("data/reference/ref.fa", ">chr1\nAAAANNNNCCCC\n")
        self.put("grt/q/q3.fa", ">chr1\nAAAAGGGGCCCC\n")
        self.put("grt/checkpoints/step3.json", json.dumps({"frozen": "receipt"}) + "\n")
        self.put("notes.txt", "user notes stay here\n")
        self.lock = None

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        if name.endswith(".sh"):
            path.chmod(0o755)
        return path

    def snapshot(self):
        result = {}
        for path in self.root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                result[path.relative_to(self.root).as_posix()] = path.read_bytes()
            elif path.is_symlink():
                result[path.relative_to(self.root).as_posix()] = ("link", os.readlink(path))
        return result

    def acquire(self, migration=False, recovery=False):
        lock = (MigrationLock(self.root, "test-migration", recovery=recovery) if migration
                else WorkspaceLock(self.root, "test-ordinary"))
        lock.acquire()
        self.addCleanup(lock.release)
        self.lock = lock
        return lock

    def begin(self, rewrites=None):
        plan = plan_migration(self.root)
        lock = self.acquire(migration=True)
        return MigrationTransaction.begin(self.root, lock, plan, adapter="fixture.v1", rewrites=rewrites or {})

    def validate(self, layout):
        self.assertEqual(layout.path("grt/q/q3.fa").read_text(), ">chr1\nAAAAGGGGCCCC\n")
        self.assertEqual(layout.path("grt/checkpoints/step3.json").read_text(), json.dumps({"frozen": "receipt"}) + "\n")
        return {"adapter": "fixture.v1", "test_only": True, "q3_and_receipt_unchanged": True}

    def test_preview_is_read_only_and_cli_does_not_apply(self):
        before = self.snapshot()
        summary = plan_migration(self.root).summary()
        self.assertGreater(summary["move_count"], 0)
        self.assertFalse(summary["applied"])
        result = subprocess.run([sys.executable, "-B", str(TOOLS / "workspace_migration.py"),
                                 "--server-dir", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["analysis_started"])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.root / ".runtime").exists())

    def test_moves_real_data_rewrites_command_and_preserves_original(self):
        before_inode = (self.root / "grt/q/q3.fa").stat().st_ino
        transaction = self.begin({"run_all.sh": b"#!/bin/bash\necho layout2\n"})
        with self.assertRaises(LayoutError):
            WorkspaceLayout.detect(self.root)
        transaction.apply(self.validate)
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 2)
        self.assertFalse((self.root / "grt").exists())
        self.assertEqual((self.root / "03_lgz/04_step3/q3.fa").stat().st_ino, before_inode)
        self.assertEqual((self.root / "03_lgz").stat().st_mode & 0o777, 0o700)
        self.assertFalse((self.root / "data").exists())
        self.assertFalse((self.root / "metadata").exists())
        self.assertEqual((self.root / "run_all.sh").read_text(), "#!/bin/bash\necho layout2\n")
        self.assertEqual((transaction.private / "originals/run_all.sh").read_text(), "#!/bin/bash\necho legacy\n")
        self.assertEqual((self.root / "notes.txt").read_text(), "user notes stay here\n")
        self.assertEqual((self.root / "run_all.sh").stat().st_mode & 0o777, 0o755)
        self.lock.release()
        transaction.prune_empty_legacy_directories()
        self.assertFalse((self.root / ".run_all").exists())

    def test_adds_runtime_files_transactionally_and_resumes_after_install(self):
        plan = plan_migration(self.root)
        lock = self.acquire(migration=True)
        transaction = MigrationTransaction.begin(self.root, lock, plan, adapter="fixture.v1", rewrites={},
            additions={".runtime/prepared/tools/new_worker.py": (b"# actual new runtime module\n", 0o640)},
            adapter_metadata={"approved_runtime": "fixture-only"})
        target = self.root / ".runtime/prepared/tools/new_worker.py"
        original = transaction._install_addition
        def interrupted(addition):
            original(addition)
            raise InterruptedError("after owned addition install")
        with mock.patch.object(transaction, "_install_addition", side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                transaction.apply(self.validate)
        inode = target.stat().st_ino
        lock.release()
        restored = MigrationTransaction.resume(self.root, self.acquire(migration=True, recovery=True), adapter="fixture.v1")
        restored.apply(self.validate)
        self.assertEqual(target.read_bytes(), b"# actual new runtime module\n")
        self.assertEqual(target.stat().st_ino, inode)
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual(restored.journal["adapter_metadata"], {"approved_runtime": "fixture-only"})

    def test_addition_rollback_removes_only_unchanged_owned_output(self):
        transaction = MigrationTransaction.begin(self.root, self.acquire(migration=True), plan_migration(self.root),
            adapter="fixture.v1", rewrites={}, additions={".runtime/prepared/tools/new.py": (b"# new\n", 0o600)})
        def invalid(_layout):
            raise ValueError("injected validation failure")
        with self.assertRaises(ValueError):
            transaction.apply(invalid)
        target = self.root / ".runtime/prepared/tools/new.py"
        target.write_text("user modified")
        with self.assertRaisesRegex(LayoutError, "changed migration addition"):
            transaction.rollback()
        self.assertEqual(target.read_text(), "user modified")
        target.write_bytes(b"# new\n")
        transaction.rollback()
        self.assertFalse(target.exists())
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 1)
        self.assertTrue(plan_migration(self.root).entries)

    def test_destination_validation_is_scoped_to_live_owner_and_not_inherited_by_process(self):
        transaction = self.begin()
        def validate(layout):
            with self.assertRaises(LayoutError):
                WorkspaceLayout.detect(self.root)
            with migration_validation(self.root, self.lock, transaction.journal["id"]):
                self.assertEqual(WorkspaceLayout.detect(self.root).version, 2)
                self.assertEqual(WorkspaceLayout.detect(self.root).path("grt/q/q3.fa"), layout.path("grt/q/q3.fa"))
                code = "import sys;sys.path.insert(0,sys.argv[1]);from workspace_layout import WorkspaceLayout;WorkspaceLayout.detect(sys.argv[2])"
                child = subprocess.run([sys.executable, "-B", "-c", code, str(TOOLS), str(self.root)], capture_output=True, text=True)
                self.assertNotEqual(child.returncode, 0)
                self.assertIn("migration is incomplete", child.stderr)
            with self.assertRaises(LayoutError):
                WorkspaceLayout.detect(self.root)
            return self.validate(layout)
        transaction.apply(validate)
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 2)

    def test_resume_after_moved_file_without_recopying_or_recomputing(self):
        transaction = self.begin({"run_all.sh": b"#!/bin/bash\necho new\n"})
        original = transaction._install
        counter = 0
        def interrupted(entry):
            nonlocal counter
            original(entry)
            counter += 1
            if counter == 4:
                raise InterruptedError("injected interruption after rename")
        with mock.patch.object(transaction, "_install", side_effect=interrupted):
            with self.assertRaises(InterruptedError):
                transaction.apply(self.validate)
        self.lock.release()
        with self.assertRaises(LayoutError):
            WorkspaceLock(self.root, "ordinary-run")
        lock = self.acquire(migration=True, recovery=True)
        restored = MigrationTransaction.resume(self.root, lock, adapter="fixture.v1")
        restored.apply(self.validate)
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 2)

    def test_validator_failure_blocks_execution_and_can_roll_back(self):
        before = self.snapshot()
        transaction = self.begin({"run_all.sh": b"#!/bin/bash\necho new\n"})
        def invalid(layout):
            raise ValueError("fixture path contract not valid")
        with self.assertRaisesRegex(ValueError, "contract"):
            transaction.apply(invalid)
        with self.assertRaises(LayoutError):
            WorkspaceLayout.detect(self.root)
        transaction.rollback()
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 1)
        self.lock.release()
        restored = self.snapshot()
        for name, content in before.items():
            self.assertEqual(restored[name], content)
        self.assertFalse((self.root / MANIFEST).exists())

    def test_stale_preview_rejected_before_marker_created(self):
        plan = plan_migration(self.root)
        lock = self.acquire(migration=True)
        self.put("grt/q/q3.fa", ">chr1\nchanged\n")
        with self.assertRaisesRegex(LayoutError, "changed after"):
            MigrationTransaction.begin(self.root, lock, plan, adapter="fixture.v1", rewrites={})
        self.assertFalse((self.root / MIGRATION).exists())

    def test_destination_collision_is_never_overwritten(self):
        self.put("03_lgz/04_step3/q3.fa", "existing user data\n")
        before = self.snapshot()
        with self.assertRaisesRegex(LayoutError, "already exists"):
            plan_migration(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_destination_parent_file_is_rejected_in_preview(self):
        self.put("01_inputs", "not a directory\n")
        with self.assertRaisesRegex(LayoutError, "not a directory"):
            plan_migration(self.root)
        self.assertFalse((self.root / MIGRATION).exists())

    def test_no_mutations_without_lock(self):
        plan = plan_migration(self.root)
        lock = WorkspaceLock(self.root, "not-acquired")
        with self.assertRaisesRegex(LayoutError, "held legacy"):
            MigrationTransaction.begin(self.root, lock, plan, adapter="fixture.v1", rewrites={})
        self.assertFalse((self.root / MIGRATION).exists())

    def test_ordinary_lock_is_not_sufficient_to_authorize_migration(self):
        plan = plan_migration(self.root)
        lock = self.acquire()
        with self.assertRaisesRegex(LayoutError, "held legacy"):
            MigrationTransaction.begin(self.root, lock, plan, adapter="fixture.v1", rewrites={})
        self.assertFalse((self.root / MIGRATION).exists())

    def test_foreign_host_lock_is_not_stolen(self):
        path = self.root / ".run_all/lock/owner.json"
        durable_json(path, {"workspace": str(self.root), "hostname": socket.gethostname() + "-other",
                            "pid": 1, "run_id": "remote"})
        with self.assertRaisesRegex(RunnerError, "already running"):
            self.acquire(migration=True)
        self.assertEqual(json.loads(path.read_text())["run_id"], "remote")

    def test_malformed_local_owner_is_not_treated_as_a_dead_process(self):
        path = self.root / ".run_all/lock/owner.json"
        for extra in ({"pid": "not-a-pid"}, {"pid": -1}, {"pid": 99999999, "process_start": "invalid"}):
            with self.subTest(extra=extra):
                owner = {"workspace": str(self.root), "hostname": socket.gethostname(), **extra}
                durable_json(path, owner)
                with self.assertRaisesRegex(RunnerError, "already running"):
                    self.acquire(migration=True)
                self.assertEqual(json.loads(path.read_text()), owner)

    def test_internal_and_external_relative_symlinks_rebased(self):
        external = self.root.parent / "external.fa"
        external.write_text(">r\nACGT\n")
        (self.root / "data/reference/link.fa").symlink_to("ref.fa")
        (self.root / "data/reference/external.fa").symlink_to("../../../external.fa")
        transaction = self.begin()
        transaction.apply(self.validate)
        layout = WorkspaceLayout.detect(self.root)
        self.assertEqual(layout.path("data/reference/link.fa").read_bytes(), layout.path("data/reference/ref.fa").read_bytes())
        self.assertEqual(layout.path("data/reference/external.fa").read_bytes(), external.read_bytes())
        self.assertEqual(external.read_text(), ">r\nACGT\n")

    def test_changed_destination_is_not_deleted_by_rollback(self):
        transaction = self.begin()
        with self.assertRaises(ValueError):
            transaction.apply(lambda layout: (_ for _ in ()).throw(ValueError("test")))
        destination = self.root / canonical_relative("grt/q/q3.fa")
        destination.write_text("changed after migration\n")
        with self.assertRaisesRegex(LayoutError, "changed"):
            transaction.rollback()
        self.assertEqual(destination.read_text(), "changed after migration\n")

    def test_tampered_journal_cannot_escape_root(self):
        transaction = self.begin()
        path = self.root / MIGRATION
        journal = json.loads(path.read_text())
        journal["entries"][0]["destination"] = "../../outside"
        journal["inventory_sha256"] = json_digest({"entries": journal["entries"], "directories": journal["directories"]})
        durable_json(path, journal)
        with self.assertRaises(LayoutError):
            MigrationTransaction.resume(self.root, self.lock, adapter="fixture.v1")

    def test_crash_before_active_marker_can_recover_private_intent(self):
        plan = plan_migration(self.root)
        lock = self.acquire(migration=True)
        def interrupt(path, value):
            if path == self.root / MIGRATION:
                raise InterruptedError("before active marker")
            return durable_json(path, value)
        with mock.patch.object(workspace_migration, "durable_json", side_effect=interrupt):
            with self.assertRaises(InterruptedError):
                MigrationTransaction.begin(self.root, lock, plan, adapter="fixture.v1", rewrites={})
        self.assertFalse((self.root / MIGRATION).exists())
        lock.release()
        self.assertTrue((self.root / ".run_all/lock").is_dir())
        lock = self.acquire(migration=True, recovery=True)
        resumed = MigrationTransaction.resume(self.root, lock, adapter="fixture.v1")
        resumed.rollback()
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 1)
        self.assertTrue(plan_migration(self.root).entries)

    def test_crash_after_layout_marker_before_commit_can_resume(self):
        transaction = self.begin()
        original_save = transaction.save
        def interrupt(state):
            if state == "committed":
                raise InterruptedError("before commit")
            original_save(state)
        with mock.patch.object(transaction, "save", side_effect=interrupt):
            with self.assertRaises(InterruptedError):
                transaction.apply(self.validate)
        self.assertTrue((self.root / MANIFEST).is_file())
        with self.assertRaises(LayoutError):
            WorkspaceLayout.detect(self.root)
        resumed = MigrationTransaction.resume(self.root, self.lock, adapter="fixture.v1")
        resumed.apply(self.validate)
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 2)

    def test_rollback_can_be_followed_by_a_new_migration(self):
        first = self.begin({"run_all.sh": b"#!/bin/bash\necho first\n"})
        with self.assertRaises(ValueError):
            first.apply(lambda layout: (_ for _ in ()).throw(ValueError("test")))
        first.rollback()
        first_id = first.journal["id"]
        self.lock.release()
        plan = plan_migration(self.root)
        second = MigrationTransaction.begin(self.root, self.acquire(migration=True), plan,
                                            adapter="fixture.v1", rewrites={})
        second.apply(self.validate)
        self.assertNotEqual(second.journal["id"], first_id)
        self.assertEqual(json.loads((first.private / "journal.json").read_text())["state"], "rolled_back")
        self.assertEqual(WorkspaceLayout.detect(self.root).version, 2)

    def test_pending_fence_blocks_legacy_owner_and_only_one_explicit_recovery(self):
        transaction = self.begin()
        path = self.root / ".run_all/lock/owner.json"
        record = json.loads(path.read_text())
        # The reviewed old runner's compatibility boundary is the legacy
        # hostname test, not knowledge of the new journal.
        self.assertEqual(record["workspace"], str(self.root))
        self.assertNotEqual(record["hostname"], socket.gethostname())
        self.assertEqual(record["migration_fence"]["host"], socket.gethostname())
        contender = MigrationLock(self.root, "contender", recovery=True)
        with self.assertRaisesRegex(LayoutError, "live controller"):
            contender.acquire()
        self.lock.release()
        self.assertEqual(json.loads(path.read_text()), record)
        with self.assertRaisesRegex(RunnerError, "already running"):
            self.acquire(migration=True)
        first_recovery = self.acquire(migration=True, recovery=True)
        self.assertEqual(first_recovery.bound_id, transaction.journal["id"])
        with self.assertRaisesRegex(LayoutError, "live controller"):
            contender.acquire()
        self.assertEqual(json.loads(path.read_text()), record)
        restored = MigrationTransaction.resume(self.root, first_recovery, adapter="fixture.v1")
        restored.rollback()
        first_recovery.release()
        self.assertFalse(path.exists())
        self.acquire()  # legacy becomes runnable only after rollback

    def test_explicit_recovery_refuses_foreign_fenced_owner(self):
        self.begin()
        path = self.root / ".run_all/lock/owner.json"
        owner = json.loads(path.read_text())
        self.lock.release()
        owner["migration_fence"]["host"] += "-foreign"
        owner["hostname"] += "-foreign"
        durable_json(path, owner)
        with self.assertRaisesRegex(LayoutError, "foreign host"):
            self.acquire(migration=True, recovery=True)
        self.assertEqual(json.loads(path.read_text()), owner)

    def test_unknown_lock_owner_is_not_stolen_for_migration(self):
        (self.root / ".run_all/lock").mkdir()
        with self.assertRaisesRegex(RunnerError, "already running"):
            self.acquire(migration=True)
        self.assertTrue((self.root / ".run_all/lock").is_dir())

    def test_extra_file_during_validation_blocks_commit(self):
        transaction = self.begin()
        def writer(layout):
            self.put("unexpected.fa", ">r\nACGT\n")
            return self.validate(layout)
        with self.assertRaisesRegex(LayoutError, "unexpected file"):
            transaction.apply(writer)
        self.assertFalse((self.root / MANIFEST).exists())

    def test_missing_rewrite_staging_does_not_publish_and_can_roll_back(self):
        original = self.snapshot()
        transaction = self.begin({"run_all.sh": b"#!/bin/bash\necho new\n"})
        (transaction.private / "rewrites/run_all.sh").unlink()
        with self.assertRaisesRegex(LayoutError, "staging"):
            transaction.apply(self.validate)
        self.assertEqual(json.loads((self.root / MIGRATION).read_text())["state"], "prepared")
        self.assertFalse((self.root / canonical_relative("grt/q/q3.fa")).exists())
        transaction.rollback()
        for name, content in original.items():
            self.assertEqual(self.snapshot()[name], content)

    def test_adapter_identity_is_required_for_resume(self):
        self.begin()
        with self.assertRaisesRegex(LayoutError, "same migration adapter"):
            MigrationTransaction.resume(self.root, self.lock, adapter="different.v1")

    def test_layout_aware_plan_and_resource_budget(self):
        transaction = self.begin()
        transaction.apply(self.validate)
        self.lock.release()
        transaction.prune_empty_legacy_directories()
        units = load_plan(self.root)
        self.assertEqual(units[0].command_relpath, ".runtime/commands/run_lgz_step3.sh")
        self.assertEqual(units[0].detail_log_relpath, ".runtime/logs/run_all.log")
        new_lock = WorkspaceLock(self.root, "new-layout")
        new_lock.acquire()
        try:
            self.assertTrue((self.root / ".runtime/run_all/lock/owner.json").is_file())
            update_resources(self.root, {"--threads": [["8"]]}, "new-layout")
            self.assertEqual(read_resources(self.root)["effective"]["threads"], 8)
            self.assertFalse((self.root / ".run_all").exists())
        finally:
            new_lock.release()


if __name__ == "__main__":
    unittest.main()
