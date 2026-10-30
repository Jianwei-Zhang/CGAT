"""Explicit real-tool proactive routing controls (small lowered test limit)."""
import argparse
import contextlib
from copy import deepcopy
import json
import os
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import native_evaluation as ne
import proactive_reference_alignment as pa
import proactive_publication as pub
import proactive_reference_plan as pp
import recovery_publication as rp
import windowed_alignment as wa


class ProactiveSafetyTests(unittest.TestCase):
    def test_cli_defaults_to_plan_without_files_or_processes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(pa, "experiment") as execute:
            root = Path(tmp)
            with contextlib.redirect_stdout(__import__("io").StringIO()):
                self.assertEqual(pa.main(["--query", str(root/"missing"), "--target", str(root/"missing2"),
                                          "--out", str(root/"out")]), 0)
            execute.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_empty_cell_cannot_hide_nonempty_raw_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/"windows").mkdir()
            for name in ("guided.experimental.paf", "whole-query.chains.paf", "windows/raw.windows.paf",
                         "windows/stitched.experimental.paf"):
                (root/name).write_bytes(b"")
            (root/"windows/raw.windows.paf").write_bytes(b"nonempty\n")
            report={"status":"no_candidates_in_original_part", "original_inputs_unchanged":True,
                    "output_sha256":wa.sha256(root/"guided.experimental.paf")}
            with self.assertRaisesRegex(wa.ExperimentError,"zero-candidate"):
                pa.add_empty_cell(None,root,report,"q",{"part_index":0})


class ProactiveRealToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mm=os.environ.get("CGAT_MINIMAP2_BINARY")
        cls.bundle=os.environ.get("CGAT_NATIVE_CHAIN_STATE_BUNDLE")
        if not cls.mm or not cls.bundle:
            raise unittest.SkipTest("explicit pinned minimap2 and portable companion required")

    def run_case(self, *, mode, multipart=False, audit=False):
        with tempfile.TemporaryDirectory(prefix="cgat-proactive-routing-") as tmp:
            root=Path(tmp)
            rng=random.Random(2311302)
            sequence=bytes(rng.choices(b"ACGT",k=120000))
            target=root/"target.fa"; query=root/"query.fa"
            target.write_bytes(b">chr1\n"+sequence+b"\n"+
                (b">chr2\n"+bytes(rng.choices(b"ACGT",k=120000))+b"\n" if multipart else b""))
            small=[(b"ordinary", sequence[1000:4000]), (b"ordinaryN", b"N"*2500)]
            long=[(b"long_record", sequence[10000:100000]), (b"longN", b"N"*90000)]
            rows=small if mode=="normal" else long if mode=="all_long" else [small[0],long[0],small[1]]
            query.write_bytes(b"".join(b">"+name+b" comment\n"+body+b"\n" for name,body in rows))
            args=argparse.Namespace(target=target,query=query,out=root/"candidate",minimap2=self.mm,
                native_state_bundle=Path(self.bundle),threads=1,timeout=120,memory_gib=0)
            make_plan=pp.make_plan; run_command=wa.run_command
            commands=[]
            def plan(catalog, policy=None):
                return make_plan(catalog, policy or pp.WindowPolicy(20000,4000))
            def run(command,*a,**kw):
                command=list(command)
                if multipart and "-d" in command:
                    command[1:1]=["-I","100000"]  # TEST ONLY: exercise part boundaries with small data.
                commands.append(command)
                return run_command(command,*a,**kw)
            with patch.object(pp,"MAX_OPERATION",64000), patch.object(rp,"PROACTIVE_QUERY_LIMIT",64000), patch.object(pp,"make_plan",side_effect=plan), \
                    patch.object(wa,"run_command",side_effect=run):
                result=pa.experiment(args)
            self.assertEqual(result["status"],"proactive_candidate_complete")
            self.assertFalse(result["result_published"])
            self.assertFalse((args.out/"result.paf").exists())
            self.assertFalse(result["whole_input_failure_trial"])
            self.assertFalse(result["singleton_assertion_replay"])
            self.assertFalse(result["bisection"])
            index=args.out/"target.default.mmi"
            baseline=root/"baseline.paf"
            # Independent QA baseline, not part of the product path.
            subprocess.run([self.mm,"-c","--eqx","-x","asm10","-t","1","-o",str(baseline),
                            str(index if index.exists() else target),str(query)],check=True,capture_output=True)
            if mode=="normal":
                plain=root/"native.paf"
                subprocess.run([self.mm,"-c","-x","asm10","-t","1","-o",str(plain),str(target),str(query)],
                               check=True,capture_output=True)
                self.assertEqual(Path(result["output_path"]).read_bytes(),plain.read_bytes())
                self.assertEqual(len(commands),1)
                self.assertFalse(index.exists())
                self.assertFalse(result["companion_required"])
            else:
                self.assertEqual([r for r in ne.comparison_signature(result["private_path"]) if r[0][0].startswith("long")],
                                 [r for r in ne.comparison_signature(baseline) if r[0][0].startswith("long")])
                self.assertEqual(result["admission"]["status"], "proactive_recovery_admitted")
                self.assertFalse(result["admission"]["result_published"])
                self.assertEqual(result["index_part_count"],2 if multipart else 1)
                self.assertEqual(result["combination"]["original_cells"],len(rows)*(2 if multipart else 1))
                self.assertEqual(len(list(args.out.rglob("target.bases"))),1)
                self.assertEqual(len(list(args.out.rglob("query.bases"))),len(long) if mode=="all_long" else 1)
                if not multipart:
                    self.assertFalse((args.out/"index-parts").exists())
                for command in commands:
                    if "-c" in command:
                        self.assertTrue(command[-1].endswith("windows.fa") or command[-1] in {g["path"] for g in result["groups"]["groups"] if g["route"] == "native"},command)
                if mode=="all_long":
                    self.assertEqual(result["threshold_source"]["alignment_queries"],0)
                    self.assertTrue(any(p["status"]=="no_candidates_in_original_part" for p in result["parts"]))
                else:
                    self.assertEqual(result["threshold_source"]["kind"],"ordinary_original_index_mapping")
                    plain=root/"native.paf"
                    subprocess.run([self.mm,"-c","-x","asm10","-t","1","-o",str(plain),str(index),str(query)],
                                   check=True,capture_output=True)
                    ordinary=lambda data:b"".join(row for row in data.splitlines(keepends=True)
                        if row.split(b"\t",1)[0] in {r[0] for r in small})
                    self.assertEqual(ordinary(Path(result["private_path"]).read_bytes()),ordinary(plain.read_bytes()))
                self.assertEqual(sum("-d" in c for c in commands),1)
            if audit:
                def reject(changed):
                    with patch.object(pp,"MAX_OPERATION",64000), patch.object(rp,"PROACTIVE_QUERY_LIMIT",64000):
                        with self.assertRaises(wa.ExperimentError):
                            pub.admit(changed,args.out,bundle=result["helper"])
                for key,value in (("partial_PAF_reused",True),("bisection",True),("original_inputs_unchanged",False)):
                    changed=deepcopy(result); changed[key]=value; reject(changed)
                changed=deepcopy(result); changed["parts"]=changed["parts"][:-1]; reject(changed)
                changed=deepcopy(result); changed["parts"] += changed["parts"][:1]; reject(changed)
                changed=deepcopy(result); changed["combination"]["original_cells"] += 1; reject(changed)
                changed=deepcopy(result); changed["native_evaluation_combination"]["evaluated_replacements"]=[]; reject(changed)
                original=Path(result["private_path"]).read_bytes()
                Path(result["private_path"]).write_bytes(original+b"foreign\n")
                reject(result)
                Path(result["private_path"]).write_bytes(original)
                empty=next((r for r in result["parts"] if r["status"]=="no_candidates_in_original_part"),None)
                if empty:
                    path=Path(empty["directory"])/"windows/raw.windows.paf"
                    path.write_bytes(b"hidden candidate\n"); reject(result); path.write_bytes(b"")
                if mode=="mixed":
                    path=Path(result["ordinary_native"]["path"]); old=path.read_bytes()
                    path.write_bytes(old+b"foreign\n"); reject(result); path.write_bytes(old)
                else:
                    path=args.out/"first-part-metadata/empty.fa"
                    path.write_bytes(b">hidden\nACGT\n"); reject(result); path.write_bytes(b"")
                # Even a rehashed leaf cannot change its scientific eligibility.
                leaf=next(r for r in result["parts"] if r["status"]=="validated_experimental_guidance")
                path=Path(leaf["publication"]["publication_proof_path"])
                old=path.read_bytes(); proof=json.loads(old); proof["eligibility"]="exact_assertion"
                wa.write_json(path,proof)
                changed=deepcopy(result)
                row=next(r for r in changed["parts"] if r["directory"]==leaf["directory"])
                row["publication"]["publication_proof_sha256"]=wa.sha256(path)
                reject(changed); path.write_bytes(old)
            for path in args.out.rglob("*.execution.json"):
                self.assertEqual(json.loads(path.read_bytes())["returncode"],0)

    def test_admission_tampering_mixed(self): self.run_case(mode="mixed",audit=True)
    def test_admission_tampering_all_long_multipart(self): self.run_case(mode="all_long",multipart=True,audit=True)

    def test_normal_unchanged(self): self.run_case(mode="normal")
    def test_mixed_one_part(self): self.run_case(mode="mixed")
    def test_all_long_one_part_includes_unmapped(self): self.run_case(mode="all_long")
    def test_mixed_two_original_parts(self): self.run_case(mode="mixed",multipart=True)
    def test_all_long_two_original_parts_includes_unmapped(self): self.run_case(mode="all_long",multipart=True)


if __name__=="__main__": unittest.main()
