"""Publication protocol/integrity units; mock files are NOT native acceptance."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import native_first as nf
import recovery_publication as rp
import windowed_alignment as wa

ASSERTION=b"minimap2: align.c:301: mm_update_extra: Assertion `qoff == r->qe - r->qs && toff == r->re - r->rs\x27 failed.\n"


class NativePublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.private=self.root/"private.paf"
        self.part={"records":[{"name":"target","length":1000}]}
        self.state=[0,0,1000,0,0,1000,0,1000,1000,99,1000,1000,1000,1000,0,0,0,12345]
        self.decision={"key":"chain-1-fragment-0","input_index":0,"id":0,"parent":0,"subscore":0,
                       "subcount":0,"dp_max2":0,"mapq":60,"sam_primary":True}
        self.receipt={"selected":[self.decision]}
        self.row=(b"query\t1000\t0\t1000\t+\ttarget\t1000\t0\t1000\t1000\t1000\t60\t"
                  b"cg:Z:1000=\tnn:i:0\tNM:i:0\tzg:i:1\tzp:Z:experimental-native-evaluated\t"
                  b"cm:i:99\ts1:i:1000\tms:i:1000\trl:i:0\ttp:A:P\ts2:i:0\n")
        self.write()

    def write(self):
        (self.root/"selection.input.tsv").write_text("CGAT_POST_DP_V1 1000 0 1\n"+" ".join(map(str,self.state))+"\nEND 1\n")
        (self.root/"selection.stdout").write_text("S\tcgat-post-dp\t1\t2.31-r1302\tasm10\t1000\t0\t1\t1\nR\t0\t0\t0\t0\t0\t0\t60\t1\nEND\t1\n")
        self.private.write_bytes(self.row)

    def check(self):
        rp.bind_native_rows({"path":str(self.private)},self.receipt,self.root,self.part,1000)

    def test_complete_native_input_stdout_and_private_metadata_agree(self):
        self.check()

    def test_known_but_different_mapq_is_not_a_native_decision(self):
        self.private.write_bytes(self.row.replace(b"\t60\t",b"\t59\t"))
        with self.assertRaisesRegex(wa.ExperimentError,"path/MAPQ"):
            self.check()

    def test_score_chain_parent_and_subscore_tags_are_not_only_shape_checked(self):
        for before,after in ((b"cm:i:99",b"cm:i:98"),(b"s1:i:1000",b"s1:i:999"),
                             (b"ms:i:1000",b"ms:i:999"),(b"rl:i:0",b"rl:i:1"),
                             (b"tp:A:P",b"tp:A:S"),(b"s2:i:0",b"s2:i:2"),(b"zg:i:1",b"zg:i:2")):
            with self.subTest(tag=before):
                self.private.write_bytes(self.row.replace(before,after))
                with self.assertRaises(wa.ExperimentError):self.check()

    def test_actual_stdout_cannot_be_replaced_by_a_receipt_label(self):
        path=self.root/"selection.stdout"
        path.write_text(path.read_text().replace("\t60\t1\n","\t59\t1\n"))
        with self.assertRaisesRegex(wa.ExperimentError,"actual native stdout"):
            self.check()

    def test_coordinates_and_target_identity_are_bound_to_native_input(self):
        for position,value in ((2,999),(3,1),(4,1),(6,1),(10,999),(11,999)):
            with self.subTest(position=position):
                saved=self.state[:];self.state[position]=value;self.write()
                with self.assertRaises(wa.ExperimentError):self.check()
                self.state=saved

    def test_missing_and_extra_private_rows_are_refused(self):
        for raw in (b"",self.row+self.row):
            with self.subTest(raw=raw[:10]):
                self.private.write_bytes(raw)
                with self.assertRaises(wa.ExperimentError):self.check()

    def test_missing_native_footer_is_a_controlled_refusal(self):
        (self.root/"selection.stdout").write_text("S\tcgat-post-dp\t1\t2.31-r1302\tasm10\t1000\t0\t1\t1\n")
        with self.assertRaisesRegex(wa.ExperimentError,"truncated native protocol"):
            self.check()

    def test_duplicate_native_input_identity_is_refused(self):
        self.receipt["selected"].append(deepcopy(self.decision))
        with self.assertRaisesRegex(wa.ExperimentError,"duplicated"):
            self.check()


class NativeAttemptPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.directory=self.root/"native";self.directory.mkdir()

    def receipt(self,*,status="target_assertion",mid=None):
        flags=["-f",str(mid)] if mid is not None else []
        command=["/mock/minimap2","-c","-x","asm10",*flags,"-t","1","-o",str(self.directory/"native.partial.paf"),"/mock/ref","/mock/query"]
        execution={"command":command,"returncode":0 if status=="native_success" else -6}
        stderr=self.directory/"native.stderr";stderr.write_bytes(b"native complete\n" if status=="native_success" else ASSERTION)
        paf=self.directory/("native.complete.paf" if status=="native_success" else "native.partial.paf")
        paf.write_bytes(b"opaque bytes; never parsed as failed PAF\n")
        row={"status":status,"execution":execution,"path":str(paf),"paf_sha256":wa.sha256(paf),
             "paf_usable":status=="native_success","partial_PAF_reused":False,"stderr_sha256":wa.sha256(stderr)}
        wa.write_json(self.directory/"native-attempt.json",row)
        wa.write_json(self.directory/"native.execution.json",execution)
        wa.write_json(self.directory/"native.command.json",command)
        return row

    def check(self,status="target_assertion",mid=None):
        return rp.verify_attempt(self.directory/"native-attempt.json",self.root,status,
            tool="/mock/minimap2",target="/mock/ref",query="/mock/query",mid_occ=mid)

    def test_assertion_and_completed_native_bytes_have_distinct_acceptance(self):
        self.receipt();self.check()
        self.receipt(status="native_success");self.check("native_success")
        (self.directory/"native.complete.paf").write_bytes(b"changed")
        with self.assertRaisesRegex(wa.ExperimentError,"native-complete bytes"):
            self.check("native_success")

    def test_failed_paf_body_can_be_absent_and_is_never_used(self):
        self.receipt();(self.directory/"native.partial.paf").unlink()
        self.check()

    def test_inherited_threshold_is_exact_not_reestimated(self):
        self.receipt(mid=500);self.check(mid=500)
        with self.assertRaisesRegex(wa.ExperimentError,"flags"):
            self.check(mid=50)

    def test_masked_assertion_or_non_target_failure_is_not_a_completion(self):
        for code in (0,1,-9):
            with self.subTest(code=code):
                row=self.receipt();row["execution"]["returncode"]=code
                wa.write_json(self.directory/"native-attempt.json",row)
                wa.write_json(self.directory/"native.execution.json",row["execution"])
                with self.assertRaisesRegex(wa.ExperimentError,"completion/abort"):
                    self.check()

    def test_unmatched_command_file_and_changed_stderr_refuse(self):
        self.receipt();wa.write_json(self.directory/"native.command.json",["not this command"])
        with self.assertRaisesRegex(wa.ExperimentError,"files disagree"):self.check()
        self.receipt();(self.directory/"native.stderr").write_bytes(ASSERTION+b"changed\n")
        with self.assertRaisesRegex(wa.ExperimentError,"log evidence"):self.check()

    def test_evidence_cannot_escape_its_attempt_by_link(self):
        self.receipt()
        outside=self.root.parent/(self.root.name+"-outside.json")
        self.addCleanup(lambda:outside.unlink(missing_ok=True))
        outside.write_text("{}\n")
        path=self.directory/"linked.json";path.symlink_to(outside)
        with self.assertRaises(wa.ExperimentError):rp.regular_under(path,self.root)


if __name__=="__main__":
    unittest.main()
