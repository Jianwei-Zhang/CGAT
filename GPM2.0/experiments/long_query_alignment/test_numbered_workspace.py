"""Numbered workspace routing only; no alignments or environment changes."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import adaptive_screening as screening
import minimap_options as mo
import proactive_reference_plan as plan
import resume_reference as resume
import server_alignment as alignment
import workspace_binding as binding
import windowed_alignment as wa


class NumberedRecoveryPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "workspace"
        (self.root / ".runtime").mkdir(parents=True)
        (self.root / ".runtime/workspace.json").write_text(json.dumps(
            {"schema": "cgat.workspace", "layout_version": 2, "state": "ready"}))
        for name in ("metadata", ".prepare_lib", "runs/assembly_vs_ref"):
            binding.workspace_path(self.root, name).mkdir(parents=True)
        self.run = binding.workspace_path(self.root, "runs/assembly_vs_ref")

    def test_options_do_not_fall_back_to_legacy_defaults_and_invalid_layout_is_rejected(self):
        path = binding.workspace_path(self.root, "metadata/prepare_options.tsv")
        path.write_text("key\tvalue\nminimap_batch\t500M\nchr_assignment_min_coverage_percent\t72\n")
        self.assertEqual(mo.prepared_options(self.root)["minimap_batch"], "500M")
        self.assertEqual(screening.prepared_assignment_coverage(self.root), .72)
        self.assertEqual(resume.regular(self.root, "metadata/prepare_options.tsv"), path)
        (self.root / ".runtime/workspace.json").write_text('{"layout_version": 99}')
        with self.assertRaises(ValueError):
            mo.prepared_options(self.root)

    def test_private_output_guard_accepts_only_adapter_owned_numbered_run(self):
        destination = self.run / ".long-cigar-attempt-fixture/selective"
        destination.parent.mkdir()
        plan.check_prepared_scope(destination, self.root)
        with self.assertRaises(plan.PlanError):
            plan.check_prepared_scope(destination)
        with self.assertRaises(plan.PlanError):
            plan.check_prepared_scope(self.root / "01_inputs/.long-cigar-attempt-fixture/selective", self.root)
        args = SimpleNamespace(server_dir=self.root, run_dir=self.run, result="result.paf", preset="asm10", threads=1)
        with patch.object(alignment, "validate_runtime", side_effect=RuntimeError("reached verified runtime gate")):
            with self.assertRaisesRegex(RuntimeError, "reached verified runtime gate"):
                alignment.run_reference(args)
        self.assertFalse((self.root / "runs").exists())

    def test_handoff_journal_accepts_only_exact_owned_logical_or_physical_commands(self):
        entry = {"unit_id": "ref:assembly", "path": "02_alignments/assembly_vs_ref/command.sh",
                 "mode": 0o755, "backup": "000000.command.sh", "old_sha256": "a" * 64, "new_sha256": "b" * 64}
        journal = {"workspace": str(self.root), "commands": [entry]}
        resume.validate_journal_commands(journal)
        entry["path"] = "runs/assembly_vs_ref/command.sh"
        resume.validate_journal_commands(journal)
        entry["path"] = "02_alignments/other_vs_ref/command.sh"
        with self.assertRaises(wa.ExperimentError):
            resume.validate_journal_commands(journal)


if __name__ == "__main__":
    unittest.main()
