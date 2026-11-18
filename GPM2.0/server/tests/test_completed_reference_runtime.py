"""A code-only checkpoint rebind must not certify changed scientific work."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from server.tools.run_outer_checkpoints import OuterCheckpointManager,PreparedOuterCheckpoint
from server.tools.run_orchestration import file_identity,fingerprint

class CompletedReferenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.prefix=".prepare_lib/tools/long_cigar_recovery/"
        self.codes=("server_alignment.py","adaptive_ordinary_controller.py")
        self.names=["input.fa","command.sh",*[self.prefix+n for n in self.codes],self.prefix+"branch-runtime.json",self.prefix+"resume-base.json",self.prefix+"native/native.bin"]
        for name in self.names:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text("original "+name)
        self.output=self.root/"result.paf";self.output.write_bytes(b"original completed output")
        self.manager=OuterCheckpointManager(self.root)
        self.checkpoint=self.root/".run_all/checkpoints/reference.json"
        self.manager._output_identities=lambda prepared:[file_identity(self.output,relative_to=self.root)]
        self.manager.prepare=lambda unit,command:self.prepared()
        self.old=self.prepared();self.manager.commit(self.old);self.original=self.checkpoint.read_bytes()
        self.old_profile=fingerprint({n:file_identity(self.root/(self.prefix+n))["sha256"] for n in self.codes})
        for name in (self.prefix+self.codes[1],self.prefix+"branch-runtime.json",self.prefix+"resume-base.json"):(self.root/name).write_text("updated "+name)
        code={n:file_identity(self.root/(self.prefix+n))["sha256"] for n in self.codes}
        self.runtime={"files_sha256":code,"sha256":file_identity(self.root/(self.prefix+"branch-runtime.json"))["sha256"],"handoff_base_sha256":file_identity(self.root/(self.prefix+"resume-base.json"))["sha256"],"completed_reference_resume_source_profiles":[[self.old_profile,fingerprint(code)]]}
    def prepared(self):
        payload={"parameters":{"preset":"asm10"},"tools":[{"sha256":"unchanged"}],"inputs":[file_identity(self.root/n,relative_to=self.root) for n in sorted(self.names)]}
        return PreparedOuterCheckpoint("ref:sample","reference_alignment",self.checkpoint,payload,fingerprint(payload))
    def migrate(self,**kw):return self.manager.migrate_reference_runtime(self.prepared(),"command.sh",self.runtime,**kw)
    def test_readonly_then_metadata_only_migration_preserves_exact_backup_and_output(self):
        before=self.output.read_bytes();valid,reason=self.migrate(dry_run=True)
        self.assertTrue(valid,reason);self.assertEqual(self.checkpoint.read_bytes(),self.original)
        self.assertEqual(list(self.checkpoint.parent.glob("*.before-runtime-*")),[])
        valid,reason=self.migrate();self.assertTrue(valid,reason)
        backups=list(self.checkpoint.parent.glob("*.before-runtime-*"));self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),self.original);self.assertEqual(self.output.read_bytes(),before)
        self.assertTrue(self.manager.validate(self.prepared())[0])
        record=json.loads(self.checkpoint.read_text());self.assertTrue(record["runtime_transitions"][0]["outputs_unchanged"])
        self.assertEqual(record["runtime_transitions"][0]["from_source_profile"],self.old_profile)
    def test_changed_input_command_native_asset_output_and_unreviewed_pair_refuse(self):
        for kind in ("input.fa","command.sh",self.prefix+"native/native.bin","output","pair","binding"):
            with self.subTest(kind=kind):
                path=self.output if kind=="output" else self.root/kind
                before=path.read_bytes() if path.is_file() else None
                runtime=copy.deepcopy(self.runtime)
                if before is not None:path.write_bytes(before+b" changed")
                elif kind=="pair":self.runtime["completed_reference_resume_source_profiles"]=[]
                elif kind=="binding":self.runtime["sha256"]="0"*64
                valid,_=self.migrate();self.assertFalse(valid)
                self.assertEqual(self.checkpoint.read_bytes(),self.original)
                self.assertEqual(list(self.checkpoint.parent.glob("*.before-runtime-*")),[])
                if before is not None:path.write_bytes(before)
                self.runtime=runtime
    def test_changed_parameters_tools_corrupt_checkpoint_and_planning_race_refuse(self):
        for kind in ("parameters","tools","checkpoint","race"):
            with self.subTest(kind=kind):
                prepared=self.prepared()
                if kind in ("parameters","tools"):
                    payload=copy.deepcopy(prepared.input_payload);payload[kind]={"changed":True}
                    prepared=PreparedOuterCheckpoint(prepared.unit_id,prepared.kind,prepared.path,payload,fingerprint(payload))
                if kind=="checkpoint":
                    record=json.loads(self.original);record["input_fingerprint"]="0"*64;self.checkpoint.write_text(json.dumps(record))
                before=self.checkpoint.read_bytes()
                if kind=="race":
                    with patch.object(self.manager,"prepare",return_value=self.old):valid,_=self.manager.migrate_reference_runtime(prepared,"command.sh",self.runtime)
                else:valid,_=self.manager.migrate_reference_runtime(prepared,"command.sh",self.runtime)
                self.assertFalse(valid);self.assertEqual(self.checkpoint.read_bytes(),before)
                self.checkpoint.write_bytes(self.original)
    def test_postwrite_validation_failure_restores_original_checkpoint(self):
        with patch.object(self.manager,"validate",return_value=(False,"controlled output race")):
            valid,_=self.migrate()
        self.assertFalse(valid);self.assertEqual(json.loads(self.checkpoint.read_text()),json.loads(self.original))
        backups=list(self.checkpoint.parent.glob("*.before-runtime-*"));self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),self.original)
