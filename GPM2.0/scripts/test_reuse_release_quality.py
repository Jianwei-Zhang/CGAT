import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("reuse", Path(__file__).with_name("reuse-release-quality.py"))
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)


class ReusedQualityTests(unittest.TestCase):
    def setUp(self):
        self.repo = "Jianwei-Zhang/CGAT"
        self.run = {"repository": {"full_name": self.repo}, "head_repository": {"full_name": self.repo},
                    "path": ".github/workflows/release-installers.yml", "head_sha": "a" * 40}
        self.jobs = [{"name": name, "status": "completed", "conclusion": "success"} for name in reuse.QUALITY_JOBS]
        self.workflow = "  quality:\n    uses: ./.github/workflows/quality.yml\n    with:\n      full: true\n  prepare-release:\n"

    def test_only_explicit_successful_full_jobs_can_be_reused(self):
        self.assertEqual(reuse.verify_baseline(self.run, self.jobs, self.repo, self.workflow), "a" * 40)
        for conclusion in ("failure", "cancelled", "skipped", None):
            jobs = [dict(job) for job in self.jobs]
            jobs[0]["conclusion"] = conclusion
            with self.assertRaises(ValueError): reuse.verify_baseline(self.run, jobs, self.repo, self.workflow)

    def test_missing_duplicate_or_running_jobs_fail_closed(self):
        for jobs in (self.jobs[:1], self.jobs + [self.jobs[0]],
                     [{**self.jobs[0], "status": "in_progress"}, self.jobs[1]]):
            with self.assertRaises(ValueError): reuse.verify_baseline(self.run, jobs, self.repo, self.workflow)

    def test_fork_and_light_workflows_are_rejected(self):
        for run in ({**self.run, "head_repository": {"full_name": "other/fork"}},
                    {**self.run, "path": ".github/workflows/quality.yml"}):
            with self.assertRaises(ValueError): reuse.verify_baseline(run, self.jobs, self.repo, self.workflow)
        with self.assertRaises(ValueError):
            reuse.verify_baseline(self.run, self.jobs, self.repo, self.workflow.replace("full: true", "full: false"))

    def test_only_ui_and_named_release_documentation_paths_are_allowed(self):
        reuse.verify_changed_paths(["GPM2.0/app/frontend/src/styles/importer.css", "GPM2.0/README.md",
                                    "GPM2.0/server/README.md", "GPM2.0/releases/v2.0.15.md",
                                    ".github/workflows/release-installers.yml"])
        for path in ("GPM2.0/app/backend/src/lib.rs", "GPM2.0/app/src-tauri/src/lib.rs",
                     "GPM2.0/server/tools/server_run.py", "GPM2.0/app/frontend/package-lock.json",
                     "GPM2.0/scripts/quality-gate-server.sh", ".github/workflows/quality.yml"):
            with self.assertRaises(ValueError): reuse.verify_changed_paths([path])

    def test_default_full_gate_and_pinned_package_checkouts_remain_in_workflow(self):
        workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/release-installers.yml").read_text()
        self.assertIn("if: ${{ !inputs.quality_run_id }}", workflow)
        self.assertIn("full: true", workflow)
        self.assertIn("needs: [quality, verify-reused-quality]", workflow)
        self.assertIn("--revision \"$GITHUB_SHA\"", workflow)
        self.assertNotIn("ref: ${{ inputs.tag || github.ref }}", workflow)


if __name__ == "__main__": unittest.main()
