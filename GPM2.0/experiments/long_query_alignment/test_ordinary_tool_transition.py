import copy
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ordinary_tool_transition as transition
import windowed_alignment as wa


class ToolTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def binary(name, machine):
            data = bytearray(64)
            data[:7] = b"\x7fELF\x02\x01\x01"
            data[18:20] = struct.pack("<H", machine)
            path = self.root / name
            path.write_bytes(data)
            return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
        self.arm = binary("arm", 183)
        self.x86 = binary("x86", 62)
        reviewed = {self.arm["sha256"]: (183, "aarch64"), self.x86["sha256"]: (62, "x86_64")}
        for target, value in (("_REVIEWED", reviewed), ("_PAIRS", {(self.arm["sha256"], self.x86["sha256"])})):
            mock = patch.object(transition, target, value)
            mock.start(); self.addCleanup(mock.stop)
        self.probe = patch.object(transition.subprocess, "check_output", return_value="2.31-r1302\n").start()
        self.addCleanup(patch.stopall)

    def test_exact_pair_retains_both_identities(self):
        record = transition.transition_record(self.arm, self.x86)
        self.assertEqual(record["origin"]["sha256"], self.arm["sha256"])
        self.assertEqual(record["execution"]["sha256"], self.x86["sha256"])
        self.assertTrue(record["completed_payload_revalidation_required"])
        self.assertFalse(record["historical_commands_rewritten"])
        self.assertEqual(transition.verify_transition(record), record)
        self.assertTrue(all(call.args[0] == [self.x86["path"], "--version"] for call in self.probe.call_args_list))

    def test_historical_audit_never_executes_foreign_binary(self):
        self.assertEqual(transition.historical_version(self.arm), transition.VERSION)
        self.probe.assert_not_called()

    def test_source_identity_form(self):
        old = {"source": self.arm["path"], "sha256": self.arm["sha256"]}
        self.assertEqual(transition.transition_record(old, self.x86)["origin"]["path"], self.arm["path"])

    def test_reject_reverse_and_same_tool(self):
        for old,new in ((self.x86,self.arm),(self.arm,self.arm),(self.x86,self.x86)):
            with self.subTest(old=old,new=new), self.assertRaises(wa.ExperimentError):
                transition.transition_record(old,new)
        self.probe.assert_not_called()

    def test_unknown_build_not_admitted_by_version(self):
        tool = {**self.x86,"sha256":"f"*64}
        with self.assertRaises(wa.ExperimentError):transition.transition_record(self.arm,tool)
        self.probe.assert_not_called()

    def test_mutated_binary_not_admitted_by_cached_sha(self):
        transition.historical_version(self.arm)
        Path(self.arm["path"]).write_bytes(b"replacement")
        with self.assertRaises(wa.ExperimentError):transition.historical_version(self.arm)

    def test_reject_malformed_descriptors(self):
        for invalid in (None,[],{}, {"path":42,"sha256":self.arm["sha256"]},
                        {**self.arm,"sha256":{}}, {**self.arm,"path":"arm"}):
            with self.subTest(invalid=invalid),self.assertRaises(wa.ExperimentError):
                transition.historical_version(invalid)

    def test_path_and_source_must_agree(self):
        with self.assertRaises(wa.ExperimentError):
            transition.historical_version({**self.arm,"source":self.x86["path"]})

    def test_symlink_is_not_historical_identity(self):
        link=self.root/'link';link.symlink_to(self.arm["path"])
        with self.assertRaises(wa.ExperimentError):
            transition.historical_version({**self.arm,"path":str(link)})

    def test_elf_architecture_is_checked(self):
        wrong={**transition._REVIEWED,self.arm["sha256"]:(62,"x86_64")}
        with patch.object(transition,"_REVIEWED",wrong),self.assertRaises(wa.ExperimentError):
            transition.historical_version(self.arm)

    def test_probe_must_succeed_and_report_pinned_version(self):
        for outcome in ("2.28-r1209", OSError("foreign executable"), subprocess.TimeoutExpired("version",5)):
            with self.subTest(outcome=outcome):
                self.probe.side_effect=outcome if isinstance(outcome,Exception) else None
                self.probe.return_value=outcome
                with self.assertRaises(wa.ExperimentError):transition.transition_record(self.arm,self.x86)

    def test_mutation_during_version_probe_rejected(self):
        def probe(*args,**kwargs):
            Path(self.x86["path"]).write_bytes(b"changed after initial hash")
            return transition.VERSION
        self.probe.side_effect=probe
        with self.assertRaises(wa.ExperimentError):transition.transition_record(self.arm,self.x86)

    def test_receipt_cannot_weaken_proof_or_add_inventory(self):
        record=transition.transition_record(self.arm,self.x86)
        for key,value in (("schema",2),("schema",True),("completed_payload_revalidation_required",1),
                          ("historical_commands_rewritten",0),("completed_payload_revalidation_required",False),
                          ("historical_commands_rewritten",True),("extra_allowed_pairs",[])):
            altered={**record,key:value}
            with self.subTest(key=key),self.assertRaises(wa.ExperimentError):transition.verify_transition(altered)
        altered=copy.deepcopy(record);altered["origin"]["version"]="2.28"
        with self.assertRaises(wa.ExperimentError):transition.verify_transition(altered)

    def test_missing_historical_binary_rejected(self):
        Path(self.arm["path"]).unlink()
        with self.assertRaises(wa.ExperimentError):transition.transition_record(self.arm,self.x86)


if __name__ == "__main__":unittest.main()
