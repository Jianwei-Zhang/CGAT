"""Public initial-reference K/f options and execution-only K resumes."""
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TOOLS=Path(__file__).resolve().parents[1]/"tools"
sys.path.insert(0,str(TOOLS))
import run_resources as resources
import server_run
from long_cigar_recovery import minimap_options as mo
from server.tests import test_run_all_runner as runner_fixtures
from server.tools.run_outer_checkpoints import OuterCheckpointManager


class PublicMinimapOptionsTests(unittest.TestCase):
    def test_resource_options_package_import_works_without_flat_tools_path(self):
        env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
        result=subprocess.run([sys.executable,'-B','-c',
            "from server.tools import run_resources, lgz_prepare_inputs; "
            "assert run_resources.batch_size('1g') == '1G'; "
            "assert run_resources.BATCH_ENV == 'GPM_RUN_MINIMAP_BATCH'"],
            cwd=TOOLS.parents[1],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_short_and_long_aliases_share_typed_values(self):
        a=server_run.parse_options(["-K","500m","-f","0.0100"],Path.cwd())
        b=server_run.parse_options(["--minimap-batch","500M","--minimap-filter","0.01"],Path.cwd())
        self.assertEqual(a,b)
        self.assertEqual(a,{"--minimap-batch":[["500M"]],"--minimap-filter":[["0.01"]]})
        for flags in (["-K","0"],["-K","1G --secondary=no"],["-f","50"],["-f","NaN"],["-f","0"]):
            with self.subTest(flags=flags),self.assertRaises(server_run.RunnerError):server_run.parse_options(flags,Path.cwd())

    def test_f_is_frozen_and_k_can_be_changed_without_preparing_again(self):
        server_run.check_resume_options({"--minimap-batch":[["500M"]]}, {}, {})
        server_run.check_resume_options({"--minimap-filter":[["0.01"]]}, {"--minimap-filter":[["0.01"]]}, {})
        for saved in ({},{"--minimap-filter":[["0.005"]]}):
            with self.assertRaisesRegex(server_run.RunnerError,"new -o"):
                server_run.check_resume_options({"--minimap-filter":[["0.01"]]},saved,{})

    def test_k_receipt_is_persisted_and_metadata_bytes_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=runner_fixtures.RunAllRunnerTests().make_workspace(Path(tmp),[("only",'printf "%s" "$GPM_RUN_MINIMAP_BATCH" > batch.txt')])
            (workspace/"run_all.sh").write_text("# prepared\n")
            options=workspace/"metadata/prepare_options.tsv"
            options.write_text(options.read_text()+"minimap_batch\t1G\nminimap_filter\tdefault\n")
            before=options.read_bytes()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(server_run.execute(["-o",str(workspace),"-K","500M"],Path(tmp)),0)
                self.assertEqual(server_run.execute(["-o",str(workspace)],Path(tmp)),0)
            self.assertEqual((workspace/"batch.txt").read_text(),"500M")
            self.assertEqual(options.read_bytes(),before)
            state=resources.read_resources(workspace)
            self.assertEqual(state["effective"]["minimap_batch"],"500M")
            self.assertEqual(len(state["history"]),1)
            self.assertEqual(state["history"][0]["changes"]["minimap_batch"],{"from":"1G","to":"500M"})
            self.assertEqual(json.loads((workspace/"report/manifest.json").read_text())["execution_resources"],state)

    def test_environment_does_not_inject_a_batch_policy(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{mo.BATCH_ENV:"999G"}):
            self.assertNotIn(mo.BATCH_ENV,resources.resource_environment(Path(tmp)))

    def test_batch_receipt_rejects_invalid_or_wrong_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/".run_all/resources.json";path.parent.mkdir()
            for value in (0,500000000,True,"0G","500m","1G --secondary=no"):
                path.write_text(json.dumps({"schema_version":1,"effective":{"minimap_batch":value},"history":[]}))
                with self.subTest(value=value),self.assertRaises(ValueError):resources.read_resources(Path(tmp))

    def test_generated_reference_script_uses_k_but_pairwise_and_self_do_not(self):
        text=(TOOLS.parent/"prepare.sh").read_text()
        body=text[text.index("write_alignment_command_script() {"):text.index("\nresolve_required_command() {")]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            script=root/"generate.sh"
            script.write_text('''#!/usr/bin/env bash
set -euo pipefail
THREADS=4
MINIMAP_PRESET=asm5
MINIMAP_BATCH=1G
MINIMAP_FILTER=0.01
shell_quote() { printf '%q' "$1"; }
make_executable_if_supported() { chmod +x "$1"; }
'''+body+'''
write_alignment_command_script "$1/ref.sh" "$1" target.fa query.fa false result.paf true
write_alignment_command_script "$1/pair.sh" "$1" target.fa query.fa false
write_alignment_command_script "$1/self.sh" "$1" target.fa query.fa true
''')
            subprocess.run(["bash",str(script),str(root)],check=True)
            ref=(root/"ref.sh").read_text()
            self.assertIn('-K "${GPM_RUN_MINIMAP_BATCH:-1G}" -f 0.01',ref)
            for name in ("pair.sh","self.sh"):
                command=(root/name).read_text()
                self.assertNotIn("-K",command);self.assertNotIn("-f 0.01",command)

    def test_help_describes_default_batch_and_explicit_fast_filter(self):
        result=subprocess.run(["bash",str(TOOLS.parent/"prepare.sh"),"--help"],text=True,capture_output=True,check=True)
        self.assertIn("defaults to 1G",result.stdout)
        self.assertIn("500M",result.stdout)
        self.assertIn("may change alignments",result.stdout)

    def test_incremental_reference_inherits_frozen_filter_and_persisted_k(self):
        # No user config is introduced: these are the existing prepared metadata
        # and launcher-owned execution receipt, also used by initial runs.
        for prepared, override, expected in (
            ("", None, []),
            ("minimap_batch\t1G\nminimap_filter\tdefault\n", None, ["-K", "1G"]),
            ("minimap_batch\t1G\nminimap_filter\t0.01\n", "500M", ["-K", "500M", "-f", "0.01"]),
        ):
            with self.subTest(prepared=prepared, override=override), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/"metadata").mkdir();(root/"runs/new_vs_ref").mkdir(parents=True)
                options=root/"metadata/prepare_options.tsv"
                options.write_text("key\tvalue\nthreads\t12\n"+prepared)
                before=options.read_bytes()
                (root/"metadata/datasets.tsv").write_text("dataset_name\tassembler\tassembler_version\tfasta_relpath\tfai_relpath\tself_alignment_available\n")
                (root/"metadata/reference.tsv").write_text("reference_name\tfasta_relpath\nref\tdata/ref.fa\n")
                (root/"assign_chr_groups.sh").write_text("export GPM_FAST_WORK_ROOT=old\nexport GPM_FAST_MINIMAP_PRESET=asm5\n")
                if override:
                    (root/".run_all").mkdir()
                    (root/".run_all/resources.json").write_text(json.dumps({"schema_version":1,"effective":{"minimap_batch":override},"history":[]}))
                subprocess.run([sys.executable,str(TOOLS/"add_dataset_stage.py"),str(root),"new","asm5","12","true"],check=True)
                import shlex
                command=shlex.split((root/"runs/new_vs_ref/command.sh").read_text().splitlines()[-1].split(" > stdout.log")[0])
                self.assertEqual(command[:4],["minimap2","-c","-x","asm5"])
                self.assertEqual(command[4:command.index("-t")],expected)
                self.assertEqual(options.read_bytes(),before)

    def test_reference_fingerprint_contains_f_not_mutable_k(self):
        # Test the real reference recipe without filesystem-heavy hashing.
        manager=object.__new__(OuterCheckpointManager)
        manager.server_dir=Path("/not-a-workspace")
        ref={"fasta_relpath":"ref.fa","fai_relpath":"ref.fa.fai"}
        ds={"dataset_name":"ds","fasta_relpath":"ds.fa","fai_relpath":"ds.fa.fai"}
        with patch.object(manager,"_read_single_tsv",return_value=ref),patch.object(manager,"_read_datasets",return_value=[ds]),patch.object(manager,"_alignment_options",return_value={"minimap_preset":"asm10"}),patch.object(manager,"_alignment_tools",return_value={}),patch.object(manager,"_identities",return_value={}),patch.object(manager,"_read_options",return_value={"minimap_filter":"0.01","minimap_batch":"1G"}):
            params=manager._reference_inputs("ds","runs/ds_vs_ref/command.sh")["parameters"]
        self.assertEqual(params["minimap_filter"],"0.01")
        self.assertNotIn("minimap_batch",params)
