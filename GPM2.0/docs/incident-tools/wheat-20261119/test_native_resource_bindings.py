import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server/tools"))
import minimap2_diagnostics
import self_alignment_batches
import run_orchestration as contract
import self_profile_bindings as scientific
import native_batch_guard as guard
import native_resource_bindings as resources
import test_self_profile_bindings as fixtures


class NativeBindingTests(unittest.TestCase):
    def setUp(self):
        self.base=fixtures.SelfBindingTests(); self.base.setUp(); self.addCleanup(self.base.doCleanups)
        b=self.base; f=b.fx
        self.rel=b.row["operation"]
        self.spec_path=f.root/"native-spec.json"
        self.wrapper=f.root/"native-wrapper.sh"
        b.plan["dependencies"].update(native_support=f.row(Path(resources.__file__)),native_guard=f.row(Path(guard.__file__)))
        b.plan["native_runtime"]={"helper":f.row(Path(self_alignment_batches.__file__)),
            "diagnostics":f.row(Path(minimap2_diagnostics.__file__)),"mapper":f.row(f.tool)}
        b.plan_path.write_text(json.dumps(b.plan))
        original=scientific.SelfBindings(f.work,b.plan_path,contract)
        temporary=object.__new__(resources.NativeBindings); temporary.original=original
        self.spec=temporary.expected_spec(self.rel,1)
        self.spec_path.write_text(json.dumps(self.spec))
        self.wrapper.write_text(resources.wrapper_text(guard.__file__,self.spec_path))
        b.row["native_specs"]={"1":f.row(self.spec_path)}
        b.row["native_scripts"]={"1":f.row(self.wrapper)}
        self.rebuild()

    def rebuild(self):
        b=self.base
        b.plan_path.write_text(json.dumps(b.plan))
        self.original=scientific.SelfBindings(b.fx.work,b.plan_path,contract)
        self.bindings=resources.NativeBindings(self.original)
        b.bindings=self.bindings

    def publish(self, threads=1):
        b=self.base; b.fx.publish_native_small()
        batch=b.fx.native["batches"][1]; path=Path(batch["directory"])
        marker=json.loads((path/"complete.json").read_text())
        receipt={"schema":guard.SCHEMA,"status":"complete","native_key":batch["key"],
            "spec_sha256":contract.sha256_file(self.spec_path),"manifest":self.spec["manifest"],
            "runtime":self.spec["runtime"],"policy":guard.POLICY,"thread_grant":threads,
            "children":[{"kind":"mapping","as_limit_bytes":guard.POLICY["mapper_as_bytes"],"returncode":0},
                        {"kind":"restore","as_limit_bytes":guard.POLICY["restore_as_bytes"],"returncode":0}],
            "complete_marker_sha256":contract.sha256_file(path/"complete.json"),"outputs":marker["outputs"],
            "scientific_parameters_changed":False}
        (path/guard.RECEIPT).write_text(json.dumps(receipt))
        return path/guard.RECEIPT

    def mapper(self,tasks,budget,children,signal,start,line,finish,environment,*,dispatch=None):
        self.assertEqual((budget,environment,dispatch),(16,{"frozen":"environment"},"dispatch-sentinel"))
        for task in tasks:
            start(task,1)
            if task.command==self.wrapper:
                self.publish()
            else:
                self.assertEqual(task.command,self.base.script)
                self.base.fx.run_profile()
            line(task,"child output"); finish(task,0,False)
        return "resource-dispatch-result"

    def test_only_pending_native_replaced_callbacks_restored_and_merge_retained(self):
        result,events=self.base.invoke(self.mapper)
        self.assertEqual(result,"resource-dispatch-result")
        starts=[e[1] for e in events if e[0]=="start"]
        self.assertEqual(starts,[t.command for t in self.base.tasks])
        self.assertTrue(any("NATIVE_RESOURCE_OVERRIDE" in str(e) for e in events))
        self.assertTrue([e for e in events if e[0]=="finish"][-1][3])
        identities=self.bindings.output_identities("q0_chr:X")
        self.assertTrue(any(row["path"].endswith(guard.RECEIPT) for row in identities))

    def test_historical_cache_reused_without_guard_claim_or_launch(self):
        self.base.fx.run_profile(); self.base.fx.publish_native_small()
        def no_work(tasks,*args,**kwargs):
            self.assertEqual(tasks,[])
        self.base.invoke(no_work)
        self.assertIsNone(self.bindings.receipt(self.rel,1))
        rows=self.bindings.output_identities("q0_chr:X")
        self.assertFalse(any(row["path"].endswith(guard.RECEIPT) for row in rows))

    def test_new_success_requires_resource_receipt_before_final_callback(self):
        self.base.fx.run_profile()
        def missing(tasks,budget,children,signal,start,line,finish,env,**kwargs):
            self.assertEqual(len(tasks),1)
            start(tasks[0],1); self.base.fx.publish_native_small(); finish(tasks[0],0,False)
        with self.assertRaisesRegex(ValueError,"no resource receipt"):
            self.base.invoke(missing)
        self.assertFalse((self.base.fx.op/"self_batch_result.json").exists())

    def test_failed_or_cancelled_native_never_claimed_or_merged(self):
        self.base.fx.run_profile()
        for code,cancelling in ((1,False),(0,True)):
            def fail(tasks,budget,children,signal,start,line,finish,env,**kwargs):
                start(tasks[0],1); finish(tasks[0],code,cancelling)
            with patch.object(self.bindings.profiles[self.rel],"merge",side_effect=AssertionError("bad merge")):
                self.base.invoke(fail)
            self.assertIsNone(self.bindings.receipt(self.rel,1))

    def test_receipt_runtime_threads_children_and_output_fences(self):
        path=self.publish(); valid=json.loads(path.read_text())
        for field,value in (("thread_grant",9),("children",[]),("runtime",{}),
                            ("spec_sha256","wrong"),("outputs",{}),("scientific_parameters_changed",True)):
            with self.subTest(field=field):
                changed={**valid,field:value}; path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError): self.bindings.receipt(self.rel,1)
        path.write_text(json.dumps(valid))
        self.assertEqual(self.bindings.receipt(self.rel,1,threads=1),path)
        with self.assertRaises(ValueError): self.bindings.receipt(self.rel,1,threads=2)
        (path.parent/"result.paf").write_text("damaged")
        with self.assertRaises(ValueError): self.bindings.receipt(self.rel,1)

    def test_missing_inventory_and_changed_wrapper_rejected(self):
        scripts=self.base.row["native_scripts"]
        self.base.row["native_scripts"]={}
        with self.assertRaisesRegex(ValueError,"inventory"): self.rebuild()
        self.base.row["native_scripts"]=scripts
        self.wrapper.write_text("#!/bin/bash\nexit 0\n")
        scripts["1"]=self.base.fx.row(self.wrapper)
        with self.assertRaisesRegex(ValueError,"canonical"): self.rebuild()

    def test_changed_key_and_tool_spec_rejected_even_with_new_digest(self):
        valid=self.spec_path.read_text()
        for field,value in (("native_key","other"),("batch_index",0),("runtime",{})):
            changed=json.loads(valid); changed[field]=value
            self.spec_path.write_text(json.dumps(changed))
            self.base.row["native_specs"]["1"]=self.base.fx.row(self.spec_path)
            with self.assertRaisesRegex(ValueError,"spec changes"): self.rebuild()

    def test_eligibility_never_includes_fast_or_oversized(self):
        p=self.bindings.profiles[self.rel]
        self.assertEqual(resources.eligible(p),{"1"})
        clone=copy.copy(p); clone.native=copy.deepcopy(p.native)
        clone.native["batches"][1]["entries"][0]["length"]=20_000_001
        self.assertEqual(resources.eligible(clone),set())
        clone.native["target_lengths"]={"t":1_000_000_001}
        self.assertEqual(resources.eligible(clone),set())

    def test_resource_receipt_is_validated_by_fresh_reader_bindings(self):
        self.base.invoke(self.mapper)
        reader=resources.NativeBindings(scientific.SelfBindings(self.base.fx.work,self.base.plan_path,contract))
        self.assertEqual(reader.output_identities("q0_chr:X"),self.bindings.output_identities("q0_chr:X"))
        path=Path(self.base.fx.native["batches"][1]["directory"])/guard.RECEIPT
        obj=json.loads(path.read_text());obj["native_key"]="changed";path.write_text(json.dumps(obj))
        with self.assertRaises(ValueError): reader.output_identities("q0_chr:X")


if __name__=="__main__": unittest.main()
