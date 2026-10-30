"""Deferred definitions only. Mocks/tiny writers are NEVER native receipts.

Nothing in this module has been run in the implementation phase. No real long
input, helper build or minimap2 execution belongs inside the mock unit checks.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import compare_long_identity as comparison
import windowed_alignment as wa

ASSERTION = b"minimap2: align.c:301: mm_update_extra: Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs\x27 failed.\n"


def fixture_metadata():
    return {"length":comparison.LENGTH,"ordinary_start":100,"ordinary_length":1000,"unmapped_length":3000}


def ordinary_row(fixture):
    length,start,size = fixture["length"],fixture["ordinary_start"],fixture["ordinary_length"]
    return f"{comparison.ORDINARY}\t{size}\t0\t{size}\t+\t{comparison.TARGET}\t{length}\t{start}\t{start+size}\t{size}\t{size}\t60\tcg:Z:{size}M\tAS:i:{size}\n".encode()


def long_row(name,*,private=False,**changes):
    length = comparison.LENGTH
    strand = "-" if name==comparison.REVERSE else "+"
    core = [name,length,0,length,strand,comparison.TARGET,length,0,length,length,length,60 if private else 255]
    for key,value in changes.items():
        core[int(key)] = value
    cigar = f"{wa.LIMIT}={length-wa.LIMIT}="
    tags = ["cg:Z:"+cigar,"NM:i:0","nn:i:0"]
    if private:
        tags.extend([f"ms:i:{length}","tp:A:P","rl:i:0"])
    return ("\t".join(map(str,core))+"\t"+"\t".join(tags)+"\n").encode()


class LongIdentityControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_plan_only_does_not_discover_generate_map_or_create_output(self):
        out = self.root/"preview"
        with patch.object(comparison,"write_fixtures",side_effect=AssertionError("fixture generation forbidden")), \
             patch.object(comparison.shutil,"which",side_effect=AssertionError("tool discovery forbidden")), \
             patch.object(comparison.nst,"validate_bundle",side_effect=AssertionError("bundle access forbidden")), \
             patch.object(comparison.sr,"experiment",side_effect=AssertionError("mapping forbidden")), \
             redirect_stdout(io.StringIO()) as output:
            self.assertEqual(comparison.main(["--out",str(out)]),0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["status"],"plan_only")
        self.assertGreater(plan["long_query_bases_each"],wa.LIMIT)
        self.assertEqual(plan["query_order"],list(comparison.QUERY_ORDER))
        self.assertFalse(plan["actual_assertion_recovery_executed"])
        self.assertFalse(out.exists())

    def test_tiny_writer_preserves_chunked_reverse_complement_and_original_record_order(self):
        # Later unit execution writes ONLY 317 reference bases, not a long case.
        with patch.object(comparison.wa,"CHUNK",64):
            result = comparison.write_fixtures(self.root/"tiny-writer",length=317)
        def records(path):
            pieces = Path(path).read_bytes().split(b">")[1:]
            return [(piece.split(b"\n",1)[0].decode(),b"".join(piece.split(b"\n")[1:])) for piece in pieces]
        reference = records(result["target"])[0][1]
        rows = records(result["query"])
        self.assertEqual([n for n,_ in rows],list(comparison.QUERY_ORDER))
        by_name = dict(rows)
        self.assertEqual(by_name[comparison.FORWARD],reference)
        self.assertEqual(by_name[comparison.REVERSE],reference.translate(wa.RC)[::-1])
        start,size = result["ordinary_start"],result["ordinary_length"]
        self.assertEqual(by_name[comparison.ORDINARY],reference[start:start+size])
        self.assertEqual(by_name[comparison.UNMAPPED],b"N"*result["unmapped_length"])
        self.assertEqual(records(result["ordinary_query"]),[(n,b) for n,b in rows if n in (comparison.ORDINARY,comparison.UNMAPPED)])
        self.assertLessEqual(set(reference),set(b"ACGT"))
        with self.assertRaisesRegex(wa.ExperimentError,"shortened fixture"):
            comparison.audit_selective({},self.root,result,{},b"")

    def test_analytic_view_checks_both_strands_order_complete_paths_and_private_confidence(self):
        fixture = fixture_metadata()
        ordinary = ordinary_row(fixture)
        for private in (False,True):
            with self.subTest(private=private):
                path = self.root/"mock-view.paf"
                path.write_bytes(ordinary+long_row(comparison.REVERSE,private=private)+long_row(comparison.FORWARD,private=private))
                result = comparison.view_rows(path,fixture,private=private,ordinary_native=ordinary)
                self.assertEqual(result["ordered_queries"],[n for n in comparison.QUERY_ORDER if n!=comparison.UNMAPPED])
                self.assertTrue(result["ordinary_bytes_preserved"])
                self.assertEqual(result["unmapped_rows"],0)
                self.assertTrue(all(r["CIGAR_logical_over_28bit"] for r in result["long_identity_rows"].values()))
                self.assertEqual({r["mapq"] for r in result["long_identity_rows"].values()},{60 if private else 255})

    def test_missing_duplicate_order_MAPQ_strand_path_and_ordinary_mutations_refuse(self):
        fixture = fixture_metadata()
        ordinary,reverse,forward = ordinary_row(fixture),long_row(comparison.REVERSE),long_row(comparison.FORWARD)
        bad = [ordinary+reverse,ordinary+reverse+forward+forward,ordinary+forward+reverse,
               ordinary+long_row(comparison.REVERSE,**{"4":"+"})+forward,
               ordinary+long_row(comparison.REVERSE,**{"11":60})+forward,
               ordinary+reverse.replace(b"NM:i:0",b"NM:i:1")+forward,
               ordinary+reverse.replace(f"{wa.LIMIT}=".encode(),f"{wa.LIMIT}M".encode())+forward,
               ordinary.replace(b"AS:i:1000",b"AS:i:999")+reverse+forward]
        for data in bad:
            with self.subTest(data=data[:100]):
                path = self.root/"mock-bad.paf";path.write_bytes(data)
                with self.assertRaises(wa.ExperimentError):
                    comparison.view_rows(path,fixture,private=False,ordinary_native=ordinary)
        path.write_bytes(ordinary+long_row(comparison.REVERSE,private=True,**{"11":255})+long_row(comparison.FORWARD,private=True))
        with self.assertRaises(wa.ExperimentError):
            comparison.view_rows(path,fixture,private=True,ordinary_native=ordinary)

    def test_actual_exit_and_assertion_are_both_required_not_just_a_receipt_label(self):
        directory = self.root/"mock-attempt";directory.mkdir()
        stderr,paf,path = directory/"native.stderr",directory/"native.partial.paf",directory/"native-attempt.json"
        stderr.write_bytes(ASSERTION);paf.write_bytes(b"mock failed partial; NEVER reused")
        command = ["mock-only-minimap2","-c","-x","asm10","-t","1","-o",str(paf),"mock-ref","mock-query"]
        row = {"status":"target_assertion","execution":{"returncode":-6,"command":command},"path":str(paf),
               "paf_sha256":wa.sha256(paf),"stderr_sha256":wa.sha256(stderr),"paf_usable":False,"partial_PAF_reused":False}
        wa.write_json(path,row)
        wa.write_json(directory/"native.command.json",command)
        wa.write_json(directory/"native.execution.json",row["execution"])
        self.assertEqual(comparison.audit_attempt(path,"target_assertion")["status"],"target_assertion")
        for rc in (0,-9,1):
            with self.subTest(rc=rc):
                row["execution"]["returncode"] = rc;wa.write_json(path,row)
                wa.write_json(directory/"native.execution.json",row["execution"])
                with self.assertRaisesRegex(wa.ExperimentError,"actual exit/assertion/log"):
                    comparison.audit_attempt(path,"target_assertion")

        row["execution"]["returncode"] = -6
        for bad_command in (command[:1]+command[2:],command[:3]+["asm5"]+command[4:],
                            command[:4]+["--max-qlen","250M"]+command[4:]):
            row["execution"]["command"] = bad_command
            wa.write_json(path,row)
            wa.write_json(directory/"native.command.json",bad_command)
            wa.write_json(directory/"native.execution.json",row["execution"])
            with self.assertRaisesRegex(wa.ExperimentError,"changed original -c asm10"):
                comparison.audit_attempt(path,"target_assertion")

    def mocked_tool(self):
        tool,helper,manifest = self.root/"mm",self.root/"helper",self.root/"helper.json"
        for path in (tool,helper,manifest):path.write_bytes(b"mock bytes, not executable/build receipt")
        bundle = {"path":str(helper),"sha256":wa.sha256(helper),"manifest_path":str(manifest),"manifest_sha256":wa.sha256(manifest)}
        args = argparse.Namespace(out=self.root/"new-run",minimap2=str(tool),native_state_bundle=self.root,
                                  threads=2,timeout=60,memory_gib=0)
        return tool,bundle,args

    def test_missing_prebuilt_bundle_refuses_before_creating_large_input(self):
        tool,bundle,args = self.mocked_tool()
        with patch.object(comparison.shutil,"which",return_value=str(tool)), \
             patch.object(comparison.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(comparison.nst,"validate_bundle",side_effect=wa.ExperimentError("missing prebuilt helper")), \
             patch.object(comparison,"write_fixtures",side_effect=AssertionError("large generation forbidden")):
            with self.assertRaisesRegex(wa.ExperimentError,"missing prebuilt"):
                comparison.experiment(args)
        self.assertFalse(args.out.exists())

    def test_native_success_is_not_relabelled_as_real_assertion_recovery(self):
        tool,bundle,args = self.mocked_tool()
        def mocked_fixture(root):
            root.mkdir()
            return {"target":str(root/"mock-ref"),"query":str(root/"mock-query"),"length":comparison.LENGTH}
        with patch.object(comparison.shutil,"which",return_value=str(tool)), \
             patch.object(comparison.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(comparison.nst,"validate_bundle",return_value=bundle), \
             patch.object(comparison,"write_fixtures",side_effect=mocked_fixture), \
             patch.object(comparison.sr,"experiment",return_value={"routing_mode":"native_complete_unchanged"}), \
             patch.object(comparison.wa,"run_command",side_effect=AssertionError("ordinary baseline forbidden")):
            with self.assertRaisesRegex(wa.ExperimentError,"assertion/isolation did not occur"):
                comparison.experiment(args)
        receipt = json.loads((args.out/"long-identity.json").read_text())
        self.assertEqual(receipt["status"],"refused_or_failed")
        self.assertFalse(receipt["actual_assertion_recovery_executed"])
        self.assertFalse(receipt["production_ready"])

    def test_cancellation_retains_receipt_and_does_not_start_ordinary_baseline(self):
        tool,bundle,args = self.mocked_tool()
        def mocked_fixture(root):
            root.mkdir()
            return {"target":str(root/"mock-ref"),"query":str(root/"mock-query"),"length":comparison.LENGTH}
        def cancelled(options):
            try:
                signal.getsignal(signal.SIGINT)(signal.SIGINT,None)  # No actual process/signal.
            except KeyboardInterrupt:
                pass
            raise wa.ExperimentError("mock child cancellation retained")
        with patch.object(comparison.shutil,"which",return_value=str(tool)), \
             patch.object(comparison.subprocess,"check_output",return_value="2.31-r1302\n"), \
             patch.object(comparison.nst,"validate_bundle",return_value=bundle), \
             patch.object(comparison,"write_fixtures",side_effect=mocked_fixture), \
             patch.object(comparison.sr,"experiment",side_effect=cancelled), \
             patch.object(comparison.wa,"run_command",side_effect=AssertionError("ordinary baseline forbidden")):
            with self.assertRaises(KeyboardInterrupt):
                comparison.experiment(args)
        receipt = json.loads((args.out/"long-identity.json").read_text())
        self.assertEqual(receipt["status"],"interrupted")
        self.assertFalse(receipt["actual_assertion_recovery_executed"])
        self.assertFalse(receipt["production_ready"])


if __name__=="__main__":
    unittest.main()
