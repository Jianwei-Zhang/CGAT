"""LGZ implementation identity with backward-compatible GRT interfaces."""
from __future__ import annotations

import importlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[2]
TOOLS = PROJECT / "server/tools"
sys.path.insert(0, str(TOOLS))


class LgzCompatibilityTests(unittest.TestCase):
    def test_old_imports_share_the_canonical_module_and_exception_identity(self):
        for path in sorted((TOOLS / "lgz_core").rglob("*.py")):
            if path.name == "__init__.py":
                continue
            suffix = ".".join(path.relative_to(TOOLS / "lgz_core").with_suffix("").parts)
            with self.subTest(module=suffix):
                old = importlib.import_module("server.tools.grt_core." + suffix)
                new = importlib.import_module("server.tools.lgz_core." + suffix)
                self.assertIs(old, new)
        for path in TOOLS.glob("lgz_*.py"):
            if path.name == "lgz_compat.py":
                continue
            with self.subTest(module=path.stem):
                self.assertIs(importlib.import_module("server.tools." + path.stem),
                              importlib.import_module("server.tools." + path.stem.replace("lgz_", "grt_", 1)))
        from server.tools.grt_core.contract import ContractError as old_error
        from server.tools.lgz_core.contract import ContractError
        self.assertIs(old_error, ContractError)

    def test_top_level_and_package_style_imports_both_forward(self):
        code = """import importlib
for prefix in ('', 'server.tools.'):
 for name in ('step1', 'step2', 'step3', 'contract', 'app_package'):
  assert importlib.import_module(prefix+'grt_'+name) is importlib.import_module(prefix+'lgz_'+name)
 for name in ('common', 'repair_mummer', 'contract.errors'):
  assert importlib.import_module(prefix+'grt_core.'+name) is importlib.import_module(prefix+'lgz_core.'+name)
"""
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(PROJECT), str(TOOLS))))
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_old_and_new_cli_help_are_equivalent_except_program_name(self):
        for path in sorted(TOOLS.glob("lgz_*.py")):
            if path.name == "lgz_compat.py":
                continue
            old = path.with_name(path.name.replace("lgz_", "grt_", 1))
            with self.subTest(module=path.stem):
                first = subprocess.run([sys.executable, str(old), "--help"], capture_output=True, text=True)
                second = subprocess.run([sys.executable, str(path), "--help"], capture_output=True, text=True)
                self.assertEqual((first.returncode, second.returncode), (0, 0), first.stderr + second.stderr)
                self.assertEqual(first.stdout.replace(old.name, path.name), second.stdout)

    def test_old_and_new_contract_entrypoints_validate_the_same_legacy_bundle(self):
        bundle = PROJECT / "tests/fixtures/grt_contract_v2/valid/gpm_server"
        values = []
        for name in ("grt_contract.py", "lgz_contract.py"):
            result = subprocess.run([sys.executable, str(TOOLS / name), "--bundle", str(bundle)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            values.append(json.loads(result.stdout))
        self.assertEqual(*values)

    def test_engine_identity_covers_both_namespaces_and_shims(self):
        from server.tools import update_workspace_runtime as updater
        from server.tools.lgz_core.repair_common import repair_engine_sha256
        from server.tools.lgz_compat import engine_source_files
        self.assertEqual(updater.engine_hash(TOOLS), repair_engine_sha256(TOOLS / "lgz_core"))
        self.assertEqual(updater.engine_hash(TOOLS), repair_engine_sha256(TOOLS / "grt_core"))
        files = {p.relative_to(TOOLS).as_posix() for p in engine_source_files(TOOLS)}
        for name in ("lgz_core/step2_engine.py", "grt_core/step2_engine.py", "lgz_step3.py", "grt_step3.py", "lgz_compat.py"):
            self.assertIn(name, files)

    def test_new_cli_flags_preserve_existing_persisted_option_identity(self):
        from server.tools.server_run import parse_options
        pairs = {"execution-profile": "optimized", "step3-mummer-scope": "full",
                 "qc-memory-gb": "64", "kmer-size": "21"}
        for option, value in pairs.items():
            self.assertEqual(parse_options(["--lgz-" + option, value], PROJECT),
                             parse_options(["--grt-" + option, value], PROJECT))

    def test_report_and_helper_function_aliases_are_single_implementations(self):
        from server.tools.lgz_core.repair_mummer import grt_mummer_parameters, lgz_mummer_parameters
        self.assertIs(grt_mummer_parameters, lgz_mummer_parameters)
        for name, old, new in (("server_report", "record_grt_result", "record_lgz_result"),
                               ("server_report_collect", "collect_grt_inputs", "collect_lgz_inputs"),
                               ("server_report_collect", "collect_grt_result", "collect_lgz_result"),
                               ("render_server_report", "grt_flow_html", "lgz_flow_html")):
            module = importlib.import_module("server.tools." + name)
            self.assertIs(getattr(module, old), getattr(module, new))

    def test_general_updater_recognizes_canonical_runtime_files(self):
        from server.tools.update_server import runtime_file
        self.assertTrue(runtime_file("tools/lgz_core/contract/validator.py"))
        self.assertTrue(runtime_file("tools/grt_core/contract/validator.py"))
        self.assertTrue(runtime_file("tools/lgz_step3.py"))
        self.assertFalse(runtime_file("data/input.fa"))


    def test_active_reference_handoff_inventory_accepts_the_complete_lgz_tree_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            staged = workspace / ".prepare_lib/tools"
            for path in TOOLS.rglob("*.py"):
                relative = path.relative_to(TOOLS)
                if "__pycache__" in relative.parts or relative.parts[0] == "long_cigar_recovery":
                    continue
                target = staged / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            code = """import json,sys
from pathlib import Path
runtime=Path(sys.argv[1])
sys.path.insert(0,str(runtime))
import resume_reference as resume
base=json.loads((runtime/'resume-base.json').read_text())
print(resume.baseline_matches(Path(sys.argv[2]),runtime.parents[1],base))
"""
            command = [sys.executable, "-c", code, str(TOOLS / "long_cigar_recovery"), str(workspace)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "installed_server_tools")
            (staged / "lgz_core/step2_engine.py").write_text("tampered")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("staged Server provenance differs", result.stderr)
