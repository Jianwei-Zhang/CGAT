"""Exercise real Server readers/writers against the numbered physical layout.

Fixture conversion is test setup, not a production migration adapter. Scientific
receipt bytes stay frozen; the real validator must resolve their artifact roles.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from server.tools.workspace_layout import WorkspaceLayout, initialize_workspace, render_workspace_shell
from server.tools.lgz_contract import validate_contract
from server.tools.lgz_prepare_inputs import commit_prepared_outputs
from server.tests.test_grt_contract import VALID_BUNDLE
from server.tests import test_run_all_runner as runner_fixture
from server.tests import test_source_structural_pipeline as real_fixture


def numbered_copy(source: Path, destination: Path) -> WorkspaceLayout:
    layout = initialize_workspace(destination)
    for path in sorted(source.rglob("*")):
        if path.is_file():
            target = layout.path(path.relative_to(source).as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    return layout


class NumberedWorkspaceTests(unittest.TestCase):
    def assert_clean_root(self, root):
        for legacy in ("metadata", "data", "grt", "runs", "report", "logs", ".run_all", ".prepare_lib"):
            self.assertFalse((root / legacy).exists(), legacy)

    def test_shell_renderer_preserves_stage_roles_and_command_root(self):
        template = ('server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"\n'
                    'cat "${server_dir}/grt/q/q0.fa" "${server_dir}/grt/q/.q1.fa.tmp.123"\n'
                    'bash "${server_dir}/run_lgz_step2.sh"\n'
                    'cat "${server_dir}/metadata/datasets.tsv"\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(render_workspace_shell(template, WorkspaceLayout(root, 1),
                                                    "run_lgz_step1.sh"), template)
            layout = initialize_workspace(root)
            rendered = render_workspace_shell(template, layout, "run_lgz_step1.sh")
            self.assertIn('${BASH_SOURCE[0]}")/../.."', rendered)
            self.assertIn("${server_dir}/03_lgz/01_q0/q0.fa", rendered)
            self.assertIn("${server_dir}/03_lgz/02_step1/.q1.fa.tmp.123", rendered)
            self.assertIn("${server_dir}/.runtime/commands/run_lgz_step2.sh", rendered)
            self.assertIn("${server_dir}/.runtime/metadata/datasets.tsv", rendered)
            checked = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_initializer_refuses_existing_data_and_allocates_no_shadow_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            layout = initialize_workspace(root)
            self.assertEqual(WorkspaceLayout.detect(root).version, 2)
            self.assertEqual(layout.path("grt/q/q0.fa"), root / "03_lgz/01_q0/q0.fa")
            before = (root / ".runtime/workspace.json").read_bytes()
            with self.assertRaisesRegex(ValueError, "empty"):
                initialize_workspace(root)
            self.assertEqual((root / ".runtime/workspace.json").read_bytes(), before)
            self.assert_clean_root(root)

    def test_frozen_contract_resolves_all_original_proofs_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "numbered"
            legacy_result = validate_contract(VALID_BUNDLE)
            layout = numbered_copy(VALID_BUNDLE, root)
            self.assertEqual(validate_contract(root), legacy_result)
            for relative in ("metadata/grt_final_path.json", "metadata/grt_recipe.tsv", "grt/q/q4.fa"):
                self.assertEqual(layout.path(relative).read_bytes(), (VALID_BUNDLE / relative).read_bytes())
            self.assert_clean_root(root)

    def test_runner_creates_logs_and_portable_report_only_in_numbered_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            fixture = runner_fixture.RunAllRunnerTests()
            legacy = fixture.make_workspace(parent, [("first", "echo first"), ("second", "echo second")])
            root = parent / "numbered"
            layout = numbered_copy(legacy, root)
            result = subprocess.run([sys.executable, "-B", str(runner_fixture.RUNNER), "--server-dir", str(root)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("first", layout.path("logs/run_all.log").read_text())
            self.assertTrue(layout.path("report/report.html").is_file())
            manifest = json.loads(layout.path("report/manifest.json").read_text())
            self.assertEqual(manifest["status"], "success")
            portable = parent / "moved_report"
            shutil.copytree(layout.path("report"), portable)
            rendered = subprocess.run([sys.executable, "-B", str(portable / "render_report.py"), "--report-dir", str(portable)],
                                      capture_output=True, text=True, cwd=parent)
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            self.assert_clean_root(root)

    def test_real_prepare_writes_numbered_inputs_scripts_and_lgz_report(self):
        server = Path(__file__).resolve().parents[1]
        selected = os.environ.get("GPM_TEST_MUMMER_BIN")
        environment = dict(os.environ)
        if selected:
            environment["PATH"] = selected + os.pathsep + environment.get("PATH", "")
        for executable in ("samtools", "minimap2", "nucmer", "show-coords", "delta-filter", "zip", "gzip"):
            if not shutil.which(executable, path=environment["PATH"]):
                self.skipTest("prepare requires " + executable)
        help_result = subprocess.run(["nucmer", "--help"], env=environment, capture_output=True, text=True)
        if "--batch" not in help_result.stdout + help_result.stderr:
            if selected:
                self.fail("explicit MUMmer4 environment has no --batch support")
            self.skipTest("requires MUMmer4; set GPM_TEST_MUMMER_BIN")
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            reference, assembly = parent / "ref.fa", parent / "assembly.fa"
            reference.write_text(">chr1\n" + "ACGT" * 250 + "\n")
            assembly.write_text(">ctg1\n" + "ACGT" * 250 + "\n")
            root = parent / "numbered"
            command = ["bash", str(server / "prepare.sh"), "--ref", "ref", str(reference),
                       "--ds", "assembly", str(assembly), "--threads", "1", "--skip-self",
                       "--archive-format", "zip", "-o", str(root)]
            result = subprocess.run(command, capture_output=True, text=True, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout[-2000:] + result.stderr[-4000:])
            layout = WorkspaceLayout.detect(root)
            self.assertEqual(layout.version, 2)
            self.assertEqual(layout.result_prefix, root.name)
            plan = layout.path(".run_all/plan.tsv").read_text()
            self.assertLess(plan.index("finalize_evidence"), plan.index("refinement\t"))
            self.assertLess(plan.index("refinement\t"), plan.index("package_full"))
            self.assertFalse(layout.path("metadata/degap_inputs.json").exists())
            for logical in ("metadata/datasets.tsv", "metadata/annotation_library_snapshot.json",
                            "data/reference/ref.fa", "data/datasets/assembly.fa", ".run_all/plan.tsv",
                            "run_lgz_step1.sh", ".prepare_lib/tools/run_all_runner.py", "report/report.html"):
                self.assertTrue(layout.path(logical).is_file(), logical)
            self.assertEqual(layout.path("report/report.html"), root / "06_report/01_lgz/report.html")
            self.assertFalse((root / "06_report/report.html").exists())
            self.assertIn("${GPM_FAST_WORK_ROOT}/.lib/tools/assign_chr_groups.py",
                          layout.path("assign_chr_groups.sh").read_text())
            for path in [root / "run_all.sh", *layout.path("run_lgz_step1.sh").parent.glob("*.sh")]:
                checked = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, checked.stderr)
            from server.tools.annotation_library import verify_snapshot
            verify_snapshot(root)
            self.assert_clean_root(root)

    def test_numbered_launcher_uses_private_runtime_without_legacy_shadow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "numbered"
            layout = initialize_workspace(root)
            server = Path(__file__).resolve().parents[1]
            runtime = layout.path(".prepare_lib")
            (runtime / "tools").mkdir(parents=True)
            shutil.copyfile(server / "tools/workspace_layout.py", runtime / "tools/workspace_layout.py")
            (runtime / "tools/run_all_runner.py").write_text(
                'import sys\nprint("PREPARED-RUNNER", *sys.argv[1:])\n')
            shutil.copyfile(server / "lib/run_all_launcher.sh", root / "run_all.sh")
            result = subprocess.run(["bash", str(root / "run_all.sh"), "--threads", "7"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PREPARED-RUNNER --server-dir " + str(root) + " --threads 7", result.stdout)
            self.assert_clean_root(root)
            (root / ".runtime/workspace.json").write_text('{"layout_version":99}')
            result = subprocess.run(["bash", str(root / "run_all.sh")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("PREPARED-RUNNER", result.stdout)

    def test_numbered_runtime_update_and_rollback_preserve_science_and_real_paths(self):
        from server.tests.test_workspace_runtime_update import WorkspaceRuntimeUpdateTests
        from server.tools import update_workspace_runtime as updater
        fixture = WorkspaceRuntimeUpdateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        layout = numbered_copy(fixture.workspace, fixture.root / "numbered")
        fixture.workspace = layout.root
        before = layout.path("grt/q/q3.fa").read_bytes()
        original = layout.path(".prepare_lib/tools/grt_step3.py").read_bytes()
        receipt = fixture.update()
        self.assertTrue(str(receipt["backup"]).startswith(str(layout.path(".run_all"))))
        self.assertEqual(layout.path(".prepare_lib/tools/grt_step3.py").read_bytes(), b"new code\n")
        self.assertEqual(layout.path("grt/q/q3.fa").read_bytes(), before)
        updater.rollback(Path(receipt["backup"]))
        self.assertEqual(layout.path(".prepare_lib/tools/grt_step3.py").read_bytes(), original)
        self.assertEqual(layout.path("grt/q/q3.fa").read_bytes(), before)
        self.assert_clean_root(layout.root)

    def test_numbered_lgz_app_projection_preserves_logical_payload_and_omits_reads(self):
        from server.tests.test_grt_app_package import grt_app_package
        build = grt_app_package.build
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            layout = numbered_copy(VALID_BUNDLE, parent / "numbered")
            reads = layout.path("data/reads/converted/private_reads.fa")
            reads.parent.mkdir(parents=True)
            reads.write_text(">private\nACGT\n")
            for full in (False, True):
                legacy_payload = parent / ("legacy-full" if full else "legacy-light")
                numbered_payload = parent / ("numbered-full" if full else "numbered-light")
                build(VALID_BUNDLE, legacy_payload, full)
                build(layout.root, numbered_payload, full)
                snapshot = lambda root: {p.relative_to(root).as_posix(): p.read_bytes()
                                         for p in root.rglob("*") if p.is_file()}
                self.assertEqual(snapshot(numbered_payload), snapshot(legacy_payload))
                self.assertFalse((numbered_payload / "data/reads").exists())
            self.assert_clean_root(layout.root)

    @unittest.skipUnless(shutil.which("zip"), "archive smoke requires zip")
    def test_numbered_lgz_delivery_lives_under_out_and_never_archives_workspace(self):
        import zipfile
        from server.tools.delivery_archive import delivery_path, delivery_staging_path, create_archive
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "numbered"
            layout = initialize_workspace(root)
            options = layout.path("metadata/prepare_options.tsv")
            options.parent.mkdir(parents=True)
            options.write_text("key\tvalue\narchive_format\tzip\nthreads\t1\n")
            staging = delivery_staging_path(root, "full")
            (staging / "metadata").mkdir(parents=True)
            (staging / "metadata/fixture.txt").write_text("only explicit payload")
            output = delivery_path(root, "full")
            self.assertEqual(output, root / "07_delivery/00_lgz/numbered.zip")
            self.assertTrue(staging.is_relative_to(root / ".runtime"))
            create_archive(staging, output, "zip", 1)
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("numbered/metadata/fixture.txt"), b"only explicit payload")
                self.assertFalse(any(".runtime" in name or "07_delivery" in name for name in archive.namelist()))
            self.assert_clean_root(root)

    def test_numbered_q0_publication_preserves_frozen_annotation_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root, stage = parent / "workspace", parent / "stage"
            layout = initialize_workspace(root)
            frozen = {}
            for name in ("tel/rules.tsv", "cen/library.fa", "cen/reference.tsv"):
                path = layout.path(name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("frozen " + name)
                frozen[path] = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino)
            old = layout.path("grt/q/q0.fa")
            old.parent.mkdir(parents=True, exist_ok=True)
            old.write_text(">chr1\nAAAA\n")
            for name, content in {"grt/q/q0.fa": ">chr1\nTTTT\n", "metadata/grt_new.tsv": "new"}.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            commit_prepared_outputs(stage / "grt", stage / "metadata", root)
            self.assertEqual(old.read_text(), ">chr1\nTTTT\n")
            for path, identity in frozen.items():
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_ino), identity)
            self.assert_clean_root(root)

    def test_numbered_q0_publication_rolls_back_multiple_physical_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root, staged = parent / "workspace", parent / "stage"
            layout = initialize_workspace(root)
            for relative, content in {"grt/q/q0.fa": ">chr1\nAAAA\n", "grt/checkpoints/donor_freeze.json": "old-checkpoint",
                                      "metadata/grt_old.tsv": "old-metadata", "metadata/package.tsv": "keep",
                                      "tel/rules.tsv": "frozen-rule", "cen/library.fa": ">centromere\nACGT\n",
                                      "grt/owned.txt": "old-root-file"}.items():
                path = layout.path(relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            for relative, content in {"grt/q/q0.fa": ">chr1\nTTTT\n", "grt/checkpoints/donor_freeze.json": "new-checkpoint",
                                      "metadata/grt_new.tsv": "new-metadata", "grt/owned.txt": "new-root-file"}.items():
                path = staged / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            annotations = {layout.path(name): (layout.path(name).read_bytes(), layout.path(name).stat().st_mtime_ns)
                           for name in ("tel/rules.tsv", "cen/library.fa")}
            original = os.replace
            def interrupted(source, target):
                if Path(source).name == "grt_new.tsv":
                    raise OSError("injected numbered metadata failure")
                return original(source, target)
            with mock.patch("server.tools.lgz_prepare_inputs.os.replace", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "injected"):
                    commit_prepared_outputs(staged / "grt", staged / "metadata", root)
            self.assertEqual(layout.path("grt/q/q0.fa").read_text(), ">chr1\nAAAA\n")
            self.assertEqual(layout.path("grt/checkpoints/donor_freeze.json").read_text(), "old-checkpoint")
            self.assertEqual(layout.path("metadata/grt_old.tsv").read_text(), "old-metadata")
            self.assertEqual(layout.path("metadata/package.tsv").read_text(), "keep")
            self.assertFalse(layout.path("metadata/grt_new.tsv").exists())
            self.assertEqual(layout.path("grt/owned.txt").read_text(), "old-root-file")
            for path, identity in annotations.items():
                self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), identity)
            self.assert_clean_root(root)


class NumberedScientificPipelineTests(unittest.TestCase):
    setUpClass = classmethod(real_fixture.RealSourceStructuralPipelineTests.setUpClass.__func__)

    def test_numbered_q0_to_q3_matches_legacy_sequence_and_reuses_completed_stages(self):
        from server.tests.test_q0_admission import EvidenceFixture, dna
        from server.tests.test_q0_publication import complete_workspace, run_prepare, PROJECT
        from server.tools.lgz_core.common import read_fasta
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            fixture = EvidenceFixture({"chr1": 60000})
            backbone = dna(50000, 601)
            source = fixture.source("primary", backbone)
            fixture.ref(source, (0, len(backbone)), (0, len(backbone)))
            fixture.source("tel", backbone[-30000:] + "TTTAGGG" * 80)
            legacy = complete_workspace(fixture, parent / "legacy")
            layout = numbered_copy(legacy, parent / "numbered")
            for root in (legacy, layout.root):
                prepared = run_prepare(root)
                self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
                for script in ("lgz_step1.py", "lgz_step2.py", "lgz_step3.py"):
                    command = [sys.executable, "-B", str(PROJECT / "server/tools" / script),
                               "--server-dir", str(root), "--threads", "1"]
                    for name, executable in self.tools.items():
                        command += ["--" + name, executable]
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, script + "\n" + result.stdout + result.stderr)
            self.assertEqual(dict(read_fasta(layout.path("grt/q/q3.fa"))), dict(read_fasta(legacy / "grt/q/q3.fa")))
            self.assertTrue(layout.path("metadata/grt_final_path.json").is_file())
            for root in (legacy, layout.root):
                result = subprocess.run([sys.executable, "-B", str(PROJECT / "server/tools/lgz_evidence_package.py"),
                                         "--server-dir", str(root), "--threads", "1", "--minimap2", shutil.which("minimap2")],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                validate_contract(root)
            cached = run_prepare(layout.root)
            self.assertEqual(cached.returncode, 0, cached.stdout + cached.stderr)
            self.assertIn("LGZ prepare inputs are current:", cached.stdout)
            NumberedWorkspaceTests().assert_clean_root(layout.root)


if __name__ == "__main__":
    unittest.main()
