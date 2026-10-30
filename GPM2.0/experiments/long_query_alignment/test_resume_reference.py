"""Deferred handoff/rollback checks. NOT RUN; mocks are not customer acceptance."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import resume_reference as rr
import server_alignment as sa
import windowed_alignment as wa


class Manager:
    def __init__(self,complete=()):
        self.complete = set(complete)
    def prepare(self,unit_id,path):
        return SimpleNamespace(unit_id=unit_id)
    def validate(self,prepared):
        return prepared.unit_id in self.complete,"fixture checkpoint missing"
    def commit(self,*args):
        raise AssertionError("handoff may not commit a success checkpoint")


class ReferenceResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws,self.source = self.root/"workspace",self.root/"server"
        for name in (".run_all/lock","metadata","data","logs",".prepare_lib/tools"):
            (self.ws/name).mkdir(parents=True)
        (self.source/"tools").mkdir(parents=True)
        self.run_id = "deferred-unit-owner"
        wa.write_json(self.ws/".run_all/lock/owner.json",{
            "run_id":self.run_id,"pid":os.getpid(),"hostname":socket.gethostname(),"workspace":str(self.ws)})
        (self.ws/"metadata/prepare_options.tsv").write_text("key\tvalue\nalignment_engine\tminimap2\nminimap_preset\tasm10\nthreads\t10\ngrt_workflow\tgpm_grt_precomputed_v2\n")
        (self.ws/"metadata/reference.tsv").write_text("fasta_relpath\nfdata\n".replace("fdata","data/ref.fa"))
        (self.ws/"metadata/datasets.tsv").write_text("dataset_name\tfasta_relpath\na\tdata/a.fa\nb\tdata/b.fa\n")
        for name in ("ref","a","b"):
            (self.ws/f"data/{name}.fa").write_bytes(b">q\nACGT\n")
        self.units = [SimpleNamespace(unit_id="ref:"+n,command_relpath=f"runs/{n}_vs_ref/command.sh") for n in ("a","b")]
        self.units.append(SimpleNamespace(unit_id="assign",command_relpath="assign_chr_groups.sh"))
        (self.ws/".run_all/plan.tsv").write_text("unit_id\tcommand_relpath\tdetail_log_relpath\n"+"".join(
            f"{u.unit_id}\t{u.command_relpath}\tlogs/run_all.log\n" for u in self.units))
        (self.ws/"assign_chr_groups.sh").write_bytes(b"# must not edit downstream commands\n")
        self.base_hashes = {}
        for name in ("tools/server_run.py","tools/run_outer_checkpoints.py","tools/grt_core_fixture.py","tools/aux_fixture.py"):
            original = b"# fixture original Server source; never execute\n"
            (self.source/name).write_bytes(original)
            (self.ws/".prepare_lib"/name).write_bytes(original)
            self.base_hashes[name] = hashlib.sha256(original).hexdigest()
        self.runtime = self.source/"tools/long_cigar_recovery"
        self.runtime.mkdir()
        for name in sa.RUNTIME_FILES:
            (self.runtime/name).write_bytes(b"# fixture runtime receipt bytes; NEVER imported/executed\n")
        profile = {"revision":"fixture-original","base_tools_files_sha256":self.base_hashes,
                   "reference_launch_checkpoint_recipe_equal":True}
        self.base = {"schema":1,"source_profiles":[profile]}
        wa.write_json(self.runtime/rr.BASE,self.base)
        wa.write_json(self.runtime/sa.MANIFEST,{
            "schema":1,"status":"unvalidated_branch_runtime","scope":"initial_reference_asm10_only",
            "recovered_output_admission":"closed_pending_final_acceptance","files_sha256":sa.runtime_files(self.runtime),
            "handoff_base_sha256":wa.sha256(self.runtime/rr.BASE)})
        self.platform = "linux-x86_64"
        binary_dir = self.runtime/"native"/self.platform
        binary_dir.mkdir(parents=True)
        (binary_dir/rr.build.BINARY).write_bytes(b"mock companion; do not execute")
        (binary_dir/rr.build.BINARY).chmod(0o755)
        (binary_dir/rr.build.MANIFEST).write_text('{"mock":"not a compiled native receipt"}\n')
        self.original = {}
        with patch.object(rr,"quote_values",side_effect=self.quotes):
            for name in ("a","b"):
                run = self.ws/f"runs/{name}_vs_ref"
                run.mkdir(parents=True)
                old,_ = rr.render_commands(self.ws,run,self.ws/"data/ref.fa",self.ws/f"data/{name}.fa","10")
                command = run/"command.sh"
                command.write_bytes(old); command.chmod(0o755)
                self.original[name] = old
                (run/"stderr.log").write_bytes(b"retained original assertion/log evidence\n")
                (run/"result.paf").write_bytes(b"retained original partial PAF\n")
        self.preserved = {str(p.relative_to(self.ws)):p.read_bytes() for p in self.ws.rglob("*")
                          if p.is_file() and ("data" in p.parts or p.name in ("result.paf","stderr.log","assign_chr_groups.sh","grt_core_fixture.py"))}

    @staticmethod
    def quotes(values):
        # Pure mocked formatter; actual Bash-generator equality is a separate
        # integration gate. Do not label these mocks as shell/native evidence.
        return ["$'unknown\\n'" if str(v)=="unknown\n" else shlex.quote(str(v)) for v in values]

    @contextmanager
    def helpers(self):
        with patch.object(rr,"quote_values",side_effect=self.quotes), \
             patch.object(rr,"direct_process_guard"),patch.object(rr.build,"host_platform",return_value=self.platform), \
             patch.object(rr.nst,"validate_bundle",return_value={"platform":self.platform}):
            yield

    def execute(self,complete=()):
        with self.helpers():
            return rr.handoff(self.ws,self.source,self.run_id,self.units,Manager(complete))

    def assert_preserved(self):
        self.assertEqual({n:(self.ws/n).read_bytes() for n in self.preserved},self.preserved)

    def test_only_unfinished_command_is_adapted_and_original_logs_data_results_GRT_are_preserved(self):
        result = self.execute(complete={"ref:a"})
        self.assertEqual(result["adapted_units"],["ref:b"])
        self.assertEqual(result["preserved_completed_units"],["ref:a"])
        self.assertEqual((self.ws/"runs/a_vs_ref/command.sh").read_bytes(),self.original["a"])
        self.assertIn(b"long_cigar_recovery/server_alignment.py",(self.ws/"runs/b_vs_ref/command.sh").read_bytes())
        self.assertFalse(result["analysis_started"])
        self.assertFalse(result["production_ready"])
        backup = Path(result["backup"])
        journal = json.loads((backup/"journal.json").read_text())
        self.assertEqual(journal["status"],"applied")
        self.assertEqual((backup/journal["commands"][0]["backup"]).read_bytes(),self.original["b"])
        self.assertEqual((backup/journal["preserved_logs"][0]["backup"]).read_bytes(),b"retained original assertion/log evidence\n")
        self.assert_preserved()
        self.assertFalse((self.ws/".run_all/checkpoints").exists())

    def test_same_package_retry_is_idempotent_and_never_requires_customer_configuration(self):
        first = self.execute()
        count = len(list((self.ws/".run_all").glob(rr.PREFIX+"*")))
        second = self.execute()
        self.assertEqual(second["status"],"no_reference_command_handoff_needed")
        self.assertEqual(second["already_adapted_units"],["ref:a","ref:b"])
        self.assertEqual(len(list((self.ws/".run_all").glob(rr.PREFIX+"*"))),count)
        self.assertTrue(Path(first["backup"]).is_dir())
        self.assert_preserved()

    def test_all_completed_native_commands_need_no_companion_validation_or_runtime_install(self):
        with self.helpers(),patch.object(rr.nst,"validate_bundle",side_effect=AssertionError("completed native cache needs no helper")):
            result = rr.handoff(self.ws,self.source,self.run_id,self.units,Manager({"ref:a","ref:b"}))
        self.assertEqual(result["status"],"no_reference_command_handoff_needed")
        self.assertFalse((self.ws/".prepare_lib/tools/long_cigar_recovery").exists())
        self.assertFalse(list((self.ws/".run_all").glob(rr.PREFIX+"*")))

    def test_custom_or_unbound_runtime_does_not_get_overwritten(self):
        (self.ws/"runs/a_vs_ref/command.sh").write_bytes(self.original["a"]+b"# custom user command\n")
        with self.assertRaisesRegex(wa.ExperimentError,"customized"):
            self.execute()
        self.assertTrue((self.ws/"runs/a_vs_ref/command.sh").read_bytes().endswith(b"# custom user command\n"))
        self.assertFalse(list((self.ws/".run_all").glob(rr.PREFIX+"*")))
        self.assert_preserved()

    def test_source_profile_must_match_all_staged_modules_not_just_a_version_label(self):
        (self.ws/".prepare_lib/tools/grt_core_fixture.py").write_bytes(b"changed unbound scientific code")
        with self.assertRaisesRegex(wa.ExperimentError,"provenance differs"):
            self.execute()
        self.assertEqual((self.ws/"runs/a_vs_ref/command.sh").read_bytes(),self.original["a"])
        self.assertFalse(list((self.ws/".run_all").glob(rr.PREFIX+"*")))

    def test_a_whole_prebound_prior_profile_is_supported_but_mixed_source_is_not_guessed(self):
        old = dict(self.base_hashes)
        for name in ("tools/grt_core_fixture.py","tools/aux_fixture.py"):
            data = ("# older recorded revision "+name+"\n").encode()
            old[name] = hashlib.sha256(data).hexdigest()
            (self.ws/".prepare_lib"/name).write_bytes(data)
        base = {"schema":1,"source_profiles":[*self.base["source_profiles"],{
            "revision":"older-compatible-fixture","base_tools_files_sha256":old,
            "reference_launch_checkpoint_recipe_equal":True}]}
        self.assertEqual(rr.baseline_matches(self.ws,self.source,base),"older-compatible-fixture")
        (self.ws/".prepare_lib/tools/aux_fixture.py").write_bytes((self.source/"tools/aux_fixture.py").read_bytes())
        with self.assertRaisesRegex(wa.ExperimentError,"provenance differs"):
            rr.baseline_matches(self.ws,self.source,base)

    def test_previously_successful_but_invalid_checkpoint_is_not_reclassified_as_the_failed_task(self):
        (self.ws/"logs/status.tsv").write_text("unit_id\tstate\nref:a\tsuccess\nref:b\tfailed\n")
        with self.assertRaisesRegex(wa.ExperimentError,"previously completed"):
            self.execute()
        self.assertEqual((self.ws/"runs/a_vs_ref/command.sh").read_bytes(),self.original["a"])
        self.assertFalse(list((self.ws/".run_all").glob(rr.PREFIX+"*")))

    def test_wrong_owner_or_active_standalone_process_prevents_any_code_handoff(self):
        with self.helpers(),self.assertRaisesRegex(wa.ExperimentError,"workspace lock"):
            rr.handoff(self.ws,self.source,"not-the-owner",self.units,Manager())
        with self.helpers(),patch.object(rr,"direct_process_guard",side_effect=wa.ExperimentError("active process")), \
             self.assertRaisesRegex(wa.ExperimentError,"active process"):
            rr.handoff(self.ws,self.source,self.run_id,self.units,Manager())
        self.assertFalse(list((self.ws/".run_all").glob(rr.PREFIX+"*")))

    def test_failure_after_first_command_rolls_back_only_command_code_and_keeps_evidence_for_retry(self):
        atomic = rr.atomic_script
        def fail_second(path,data,mode):
            if path.parent.name=="b_vs_ref" and b"exec python3" in data:
                raise OSError("fixture interrupted apply")
            return atomic(path,data,mode)
        with patch.object(rr,"atomic_script",side_effect=fail_second),self.assertRaisesRegex(OSError,"interrupted apply"):
            self.execute()
        for name in ("a","b"):
            self.assertEqual((self.ws/f"runs/{name}_vs_ref/command.sh").read_bytes(),self.original[name])
        backup = next((self.ws/".run_all").glob(rr.PREFIX+"*"))
        self.assertEqual(json.loads((backup/"journal.json").read_text())["status"],"rolled_back")
        self.assert_preserved()
        self.assertEqual(self.execute()["adapted_units"],["ref:a","ref:b"])

    def test_incomplete_journal_is_recovered_on_same_original_run_command_without_a_repair_flag(self):
        result = self.execute()
        backup = Path(result["backup"])
        journal = json.loads((backup/"journal.json").read_text())
        journal["status"] = "applying"  # Simulate a stopped transaction, not a live job.
        rr.save_json(backup/"journal.json",journal)
        (self.ws/"runs/b_vs_ref/command.sh").write_bytes(self.original["b"])
        resumed = self.execute()
        self.assertIn(str(backup),resumed["prior_recoveries"])
        self.assertEqual(json.loads((backup/"journal.json").read_text())["status"],"rolled_back")
        self.assert_preserved()

    def test_rollback_never_overwrites_a_concurrent_user_edit(self):
        atomic = rr.atomic_script
        custom = b"# deliberate concurrent user change; preserve it\n"
        def conflict(path,data,mode):
            if path.parent.name=="b_vs_ref" and b"exec python3" in data:
                (self.ws/"runs/a_vs_ref/command.sh").write_bytes(custom)
                raise OSError("fixture apply interruption")
            return atomic(path,data,mode)
        with patch.object(rr,"atomic_script",side_effect=conflict),self.assertRaisesRegex(wa.ExperimentError,"user edits"):
            self.execute()
        self.assertEqual((self.ws/"runs/a_vs_ref/command.sh").read_bytes(),custom)
        self.assert_preserved()

    def test_forged_journal_cannot_target_FASTA_or_non_reference_files(self):
        data = {"commands":[{"unit_id":"ref:a","path":"data/a.fa","backup":"000000.command.sh","mode":0o755,
                              "old_sha256":"a"*64,"new_sha256":"b"*64}]}
        with self.assertRaisesRegex(wa.ExperimentError,"exact reference-command"):
            rr.validate_journal_commands(data)
        self.assert_preserved()

    def test_different_existing_branch_runtime_is_not_replaced(self):
        installed = self.ws/".prepare_lib/tools/long_cigar_recovery"
        installed.mkdir()
        (installed/"user-owned.txt").write_bytes(b"not this package")
        with self.assertRaisesRegex(wa.ExperimentError,"different branch runtime"):
            self.execute()
        self.assertEqual((installed/"user-owned.txt").read_bytes(),b"not this package")
        self.assertFalse(list((self.ws/".run_all").glob(rr.PREFIX+"*")))

    def test_local_direct_process_guard_handles_relative_mapper_paths_without_touching_a_live_process(self):
        proc = self.root/"fake-proc"
        pid = proc/"99999999"
        pid.mkdir(parents=True)
        (pid/"cmdline").write_bytes(b"minimap2\0../../data/ref.fa\0../../data/a.fa\0")
        (pid/"cwd").symlink_to(self.ws/"runs/a_vs_ref",target_is_directory=True)
        with self.assertRaisesRegex(wa.ExperimentError,"active standalone"):
            rr.direct_process_guard(self.ws,proc_root=proc)
        (pid/"cmdline").write_bytes(b"minimap2\0-t\0"+b"2\0-x\0asm10\0-o\0/elsewhere/out.paf\0/elsewhere/ref.fa\0/elsewhere/query.fa\0")
        rr.direct_process_guard(self.ws,proc_root=proc)
        (pid/"cmdline").write_bytes(b"minimap2\0-o\0new-result.paf\0/elsewhere/ref.fa\0/elsewhere/query.fa\0")
        with self.assertRaisesRegex(wa.ExperimentError,"active standalone"):
            rr.direct_process_guard(self.ws,proc_root=proc)


if __name__=="__main__":
    unittest.main()
