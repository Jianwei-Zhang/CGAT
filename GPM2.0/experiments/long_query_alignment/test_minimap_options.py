"""Approved K/f surface: narrow commands, frozen scientific policy, legacy reuse."""
import argparse
import json
import os
from pathlib import Path
import random
import shutil
import tempfile
import unittest
from unittest.mock import patch

import minimap_options as mo
import native_first as nf
import proactive_reference_alignment as pa
import proactive_resume as pr
import recovery_publication as rp
import windowed_alignment as wa


class MinimapOptionTests(unittest.TestCase):
    def test_batch_validation_and_no_shell_or_arbitrary_args(self):
        for value, expected in (("1G", "1G"), ("500m", "500M"), ("1000", "1000")):
            self.assertEqual(mo.batch_size(value), expected)
        for value in (0, -1, "1.5G", "1GiB", "1G --secondary=no", "1G;true", "0G", "9"*30, True):
            with self.subTest(value=value), self.assertRaises(ValueError):mo.batch_size(value)

    def test_filter_is_fraction_only_not_integer_mid_occ(self):
        self.assertEqual(mo.seed_fraction("0.0100"), "0.01")
        for value in ("0", "0.0", "1", "50", "-0.1", "NaN", "inf", "0.01 -c", "1e-2", "0."+"9"*40, "0."+"0"*400+"1"):
            with self.subTest(value=value), self.assertRaises(ValueError):mo.seed_fraction(value)

    def test_legacy_args_have_identical_native_flags_and_inheritance_wins_once(self):
        self.assertEqual(mo.native_flags(argparse.Namespace()), [])
        args = argparse.Namespace(minimap_batch="1G", minimap_filter="0.01")
        self.assertEqual(mo.native_flags(args), ["-K","1G","-f","0.01"])
        self.assertEqual(mo.native_flags(args,mid_occ=50), ["-K","1G","-f","50"])
        with self.assertRaises(ValueError):mo.native_flags(args,mid_occ=True)

    def test_receipt_whitelist_does_not_allow_conflicting_or_undeclared_filter(self):
        tail = ["-t","64","-o","o","t","q"]
        for batch in ([],["-K","500M"],["-K","1G"]):
            self.assertEqual(mo.command_tail(["mm","-c","-x","asm10",*batch,*tail],"mm"),tail)
            command=["mm","-c","-x","asm10",*batch,"-f","0.01",*tail]
            self.assertEqual(mo.command_tail(command,"mm",fraction="0.01"),tail)
            # With no declared f the tail contains an unexpected flag; the native
            # verifier's exact tail check, rather than arbitrary-args forwarding, refuses it.
            self.assertNotEqual(mo.command_tail(command,"mm"),tail)
            with self.assertRaises(ValueError):mo.command_tail(command,"mm",fraction="0.005")

    def test_prepared_defaults_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{},clear=True):
            root=Path(tmp);(root/"metadata").mkdir()
            self.assertEqual(mo.workspace_options(root),{})
            path=root/"metadata/prepare_options.tsv"
            path.write_text("key\tvalue\nthreads\t64\n")
            self.assertEqual(mo.workspace_options(root),{})
            path.write_text(path.read_text()+"minimap_batch\t1G\nminimap_filter\tdefault\n")
            self.assertEqual(mo.workspace_options(root),{"minimap_batch":"1G"})
            with patch.dict(os.environ,{mo.BATCH_ENV:"500M"}):
                self.assertEqual(mo.workspace_options(root),{"minimap_batch":"500M"})
            path.write_text(path.read_text().replace("default","0.01"))
            self.assertEqual(mo.workspace_options(root),{"minimap_batch":"1G","minimap_filter":"0.01"})

    def test_k_is_execution_only_but_explicit_f_changes_private_identity(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pr.shutil,"which",return_value=None):
            path=Path(tmp)/"f.fa";path.write_text(">a\nACGT\n")
            args=argparse.Namespace(target=path,query=path,threads=64,preset="asm10")
            old=pr.adapter_key(args,{"sha256":"a"*64})
            args.minimap_batch="1G"
            self.assertEqual(pr.adapter_key(args,{"sha256":"a"*64}),old)
            args.minimap_filter="0.01"
            self.assertNotEqual(pr.adapter_key(args,{"sha256":"a"*64}),old)


class NativeOptionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get("CGAT_MINIMAP2_BINARY")
        if not cls.mm:raise unittest.SkipTest("explicit pinned minimap2 required")

    def fixture(self, root):
        seq=bytes(random.Random(2311302).choices(b"ACGT",k=160000))
        target=root/"target.fa";query=root/"query.fa"
        target.write_bytes(b">ref\n"+seq+b"\n")
        query.write_bytes(b">q\n"+seq[10000:90000]+b"\n")
        return target,query

    def test_native_k_fast_receipt_and_cache_reuse_after_lowering_k(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,query=self.fixture(root)
            args=argparse.Namespace(threads=2,timeout=60,memory_gib=0,minimap_batch="1G",minimap_filter="0.01")
            receipt=nf.attempt(self.mm,target,query,root/"ordinary-native",args)
            self.assertEqual(receipt["status"],"native_success")
            kwargs=dict(tool=self.mm,target=target,query=query)
            with self.assertRaises(wa.ExperimentError):rp.verify_attempt(root/"ordinary-native/native-attempt.json",root,"native_success",**kwargs)
            rp.verify_attempt(root/"ordinary-native/native-attempt.json",root,"native_success",fraction="0.01",**kwargs)
            cache=pr.Checkpoint(root,{"minimap_filter":"0.01"});cache.save_ordinary()
            with patch.dict(os.environ,{mo.BATCH_ENV:"500M"}),patch.object(wa,"run_command",side_effect=AssertionError("must not remap completed data")):
                self.assertEqual(cache.ordinary(self.mm,target,query,fraction="0.01"),receipt)
            with self.assertRaises(wa.ExperimentError):cache.ordinary(self.mm,target,query,fraction="0.005")

    def test_all_long_threshold_uses_explicit_fraction_and_no_mapping_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,query=self.fixture(root)
            args=argparse.Namespace(threads=2,timeout=60,memory_gib=0,minimap_filter="0.01")
            mid,receipt=pa.first_part_threshold(self.mm,{"path":str(target),"sha256":wa.sha256(target)},root,args)
            self.assertEqual(receipt["alignment_queries"],0)
            command=receipt["execution"]["command"]
            self.assertEqual(command[command.index("-f")+1],"0.01")
            self.assertGreaterEqual(mid,50)
            self.assertEqual((root/"first-part-metadata/empty.paf").stat().st_size,0)

    def test_pure_ordinary_new_default_never_builds_an_extra_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target,query=self.fixture(root)
            args=argparse.Namespace(target=target,query=query,out=root/"candidate",minimap2=self.mm,
                threads=2,timeout=60,memory_gib=0,minimap_batch="1G",minimap_filter="0.01")
            with patch.object(pa.sr,"build_default_index",side_effect=AssertionError("unnecessary index preprocessing")),patch.object(pa.nst,"validate_bundle",side_effect=AssertionError("normal-only does not need companion")):
                result=pa.experiment(args)
            self.assertEqual(result["routing_mode"],"native_complete_unchanged")
            self.assertIn("-K",result["native"]["execution"]["command"])
            self.assertEqual(Path(result["output_path"]).read_bytes(),(args.out/"ordinary-native/native.complete.paf").read_bytes())


class FastRecoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get("CGAT_MINIMAP2_BINARY")
        cls.bundle=os.environ.get("CGAT_NATIVE_CHAIN_STATE_BUNDLE")
        if not cls.mm or not cls.bundle:raise unittest.SkipTest("explicit pinned mapper/helper required")

    def run_control(self, *, all_long):
        # Reuse only the established fixture builder/length-window controls,
        # not a second mapper implementation or a fabricated abort receipt.
        import test_proactive_resume as fixtures
        import server_alignment as sa
        owner=fixtures.RealResumeTests()
        owner.mm=self.mm;owner.bundle=self.bundle
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);runtime,args=owner.fixture(root,all_long=all_long)
            (args.server_dir/"metadata/prepare_options.tsv").write_text(
                "key\tvalue\nminimap_batch\t1G\nminimap_filter\t0.01\n")
            with owner.controls():
                result=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(result["result_published"])
            self.assertEqual(result["initial_reference_options"],{"minimap_batch":"1G","minimap_filter":"0.01"})
            output=(args.run_dir/"result.paf").read_bytes()
            attempt=Path(result["attempt"])/"selective"
            candidate=json.loads((attempt/"proactive-candidate.json").read_text())
            self.assertEqual(candidate["minimap_filter"],"0.01")
            context=json.loads((attempt/"index-context.json").read_text())
            self.assertEqual({p["mid_occ"] for p in context["parts"]},{50})
            for path in attempt.rglob("*.command.json"):
                command=json.loads(path.read_text())
                if "-f" in command:
                    self.assertEqual(command.count("-f"),1)
            with owner.controls(),patch.dict(os.environ,{mo.BATCH_ENV:"500M"}),patch.object(wa,"run_command",side_effect=AssertionError("K-only resume must not remap completed data")):
                again=sa.run_reference(args,runtime_root=runtime)
            self.assertTrue(again["attempt_reused"])
            self.assertEqual(again["initial_reference_options"]["minimap_batch"],"500M")
            self.assertEqual((args.run_dir/"result.paf").read_bytes(),output)
            self.assertEqual(again["cache_reused"]["ordinary_group"],0 if all_long else 1)
            self.assertEqual(again["cache_reused"]["long_cells"],2)

    def test_mixed_ordinary_and_long_with_explicit_fast_filter_and_k_resume(self):
        self.run_control(all_long=False)

    def test_all_long_with_explicit_fast_filter_and_k_resume(self):
        self.run_control(all_long=True)
