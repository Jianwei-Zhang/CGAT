"""Real native tools through the prepared-workspace adapter and atomic publisher."""
import argparse
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import proactive_reference_plan as pp
import recovery_publication as rp
import server_alignment as sa
import windowed_alignment as wa


class PrivateScopeTests(unittest.TestCase):
    def test_only_adapter_owned_attempt_scope_can_materialize_inside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/".prepare_lib").mkdir(); (root/"metadata").mkdir()
            good=root/"runs/x_vs_ref/.long-cigar-attempt-abcd/selective"
            good.mkdir(parents=True)
            pp.check_prepared_scope(good,root)
            pp.check_prepared_scope(good/"inputs",root,leaf="inputs")
            for path in (root/"data",root/".prepare_lib/tools",root/"runs/x_vs_ref/selective",
                         root/"runs/x_vs_local/.long-cigar-attempt-abcd/selective"):
                with self.subTest(path=path),self.assertRaises(pp.PlanError):
                    pp.check_prepared_scope(path,root)
            with self.assertRaises(pp.PlanError): pp.check_prepared_scope(good)
            link=root/"alias"; link.symlink_to(good,target_is_directory=True)
            with self.assertRaises(pp.PlanError): pp.check_prepared_scope(link,root)


class ProactiveServerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get("CGAT_MINIMAP2_BINARY")
        cls.bundle=os.environ.get("CGAT_NATIVE_CHAIN_STATE_BUNDLE")
        if not cls.mm or not cls.bundle:
            raise unittest.SkipTest("explicit pinned mapper and portable companion required")

    def run_case(self,mode):
        with tempfile.TemporaryDirectory(prefix="cgat-proactive-adapter-") as tmp:
            root=Path(tmp); runtime=root/"runtime"; runtime.mkdir()
            for name in sa.RUNTIME_FILES:
                shutil.copyfile(Path(sa.__file__).with_name(name),runtime/name)
            checked=sa.nst.validate_bundle(self.bundle)
            bundle=runtime/"native"/checked["platform"]
            shutil.copytree(Path(self.bundle),bundle)
            wa.write_json(runtime/sa.MANIFEST,dict(schema=1,status="source_checked_recovery_runtime",
                scope="initial_reference_asm10_only",recovered_output_admission=sa.pub.POLICY,
                native_companion_sha256=checked["sha256"],native_companion_platform=checked["platform"],
                files_sha256=sa.runtime_files(runtime)))
            ws=root/"workspace"; (ws/".prepare_lib").mkdir(parents=True); (ws/"metadata").mkdir()
            run=ws/"runs/query_vs_ref"; run.mkdir(parents=True)
            rng=random.Random(2311302); sequence=bytes(rng.choices(b"ACGT",k=120000))
            target=root/"ref.fa"; query=root/"query.fa"
            target.write_bytes(b">ref\n"+sequence+b"\n")
            if mode=="native": data=b">short\n"+sequence[5000:9000]+b"\n"
            elif mode=="unmapped": data=b">longN\n"+b"N"*90000+b"\n"
            else: data=b">short\n"+sequence[5000:9000]+b"\n>long\n"+sequence[10000:100000]+b"\n"
            query.write_bytes(data)
            args=argparse.Namespace(server_dir=ws,run_dir=run,target=target,query=query,threads=1,preset="asm10",result="result.paf")
            make_plan=pp.make_plan
            def plan(catalog,policy=None): return make_plan(catalog,policy or pp.WindowPolicy(20000,4000))
            with patch.dict(os.environ,{"PATH":str(Path(self.mm).parent)+os.pathsep+os.environ["PATH"]}), \
                    patch.object(pp,"MAX_OPERATION",64000),patch.object(rp,"PROACTIVE_QUERY_LIMIT",64000), \
                    patch.object(pp,"make_plan",side_effect=plan),patch.object(wa,"run_command",wraps=wa.run_command) as commands,redirect_stderr(io.StringIO()):
                if mode=="native":
                    # No helper lookup on the all-normal path, even in an enabled package.
                    with patch.object(sa.nst,"validate_bundle",side_effect=AssertionError("unexpected native companion")):
                        report=sa.run_reference(args,runtime_root=runtime)
                else: report=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(report["result_published"])
            self.assertFalse(report["customer_configuration_required"])
            self.assertEqual(report["proactive_routing"],mode!="native")
            self.assertEqual(report["status"],"native_complete_published" if mode=="native" else "proactive_complete_published")
            attempt=Path(report["attempt"])
            candidate=json.loads((attempt/"selective/proactive-candidate.json").read_bytes())
            self.assertFalse(candidate["whole_input_failure_trial"])
            self.assertFalse(candidate["singleton_assertion_replay"])
            self.assertEqual(wa.sha256(run/"result.paf"),report["publication"]["sha256"])
            self.assertEqual((attempt/"publication.complete.paf").read_bytes(),(run/"result.paf").read_bytes())
            if mode=="unmapped":
                self.assertEqual((run/"result.paf").read_bytes(),b"")
                self.assertFalse(report["recovered_native_confidence_published"])
                admission=json.loads((attempt/"recovery-admission.json").read_bytes())
                self.assertEqual(admission["no_candidate_cells"],1)
                self.assertEqual(admission["recovered_cells"],0)
            elif mode=="mixed":
                self.assertTrue(report["recovered_native_confidence_published"])
                admission=json.loads((attempt/"recovery-admission.json").read_bytes())
                self.assertEqual(admission["recovered_cells"],1)
                self.assertEqual(admission["policy"],sa.pub.POLICY)
                fields=[line.split(b"\t") for line in (run/"result.paf").read_bytes().splitlines()]
                self.assertEqual([f[0] for f in fields],[b"short",b"long"])
                self.assertEqual({f[11] for f in fields},{b"60"})
            else:
                baseline=root/"baseline.paf"
                subprocess.run([self.mm,"-c","-x","asm10","-t","1","-o",str(baseline),str(target),str(query)],
                               check=True,capture_output=True)
                self.assertEqual((run/"result.paf").read_bytes(),baseline.read_bytes())
                execution=json.loads((attempt/"selective/ordinary-native/native.execution.json").read_bytes())
                native_calls=[call for call in commands.call_args_list if call.args[2]=="native"]
                self.assertEqual(len(native_calls),1)
                self.assertIsNone(native_calls[0].args[3])
            for path in attempt.rglob("*.execution.json"):
                execution=json.loads(path.read_bytes()); self.assertEqual(execution["returncode"],0)
                if "-c" in execution["command"] and mode!="native":
                    self.assertNotEqual(execution["command"][-1],str(query))

    def test_native_prepared_workspace_publishes_identical_bytes(self): self.run_case("native")
    def test_mixed_prepared_workspace_admits_then_publishes(self): self.run_case("mixed")
    def test_unmapped_long_query_publishes_checked_empty_output(self): self.run_case("unmapped")


if __name__=="__main__": unittest.main()
