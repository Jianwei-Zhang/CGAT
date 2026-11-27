import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from hashlib import sha256
import q0_exact_engineering_transition as exact
import prepare_q0_runtime_transition as prep


class ExactTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/"runtime").mkdir();(self.root/"support").mkdir()
        self.prefix="tools/lgz_core/"
        self.old={self.prefix+"q0_admission.py":b"class AdmissionPolicy:\n    threshold = 100\n",
                  self.prefix+"q0_paths.py":b"class PathPolicy:\n    padding = 100000\n",
                  self.prefix+"q0_collinear.py":b"class ContinuousAdmissionPolicy:\n    ratio = 10\n",
                  self.prefix+"q0_pair_lanes.py":b"old = True\n", "tools/workspace_layout.py":b"workspace = True\n"}
        self.new=dict(self.old);self.new[self.prefix+"q0_admission.py"]+=b"# exact cache\n"
        self.new[self.prefix+"q0_pair_lanes.py"]=b"new = True\n";self.new[self.prefix+"q0_pair_transport.py"]=b"shared = True\n"
        self.pins={n:sha256(self.new[self.prefix+n]).hexdigest() for n in exact.ENGINEERING_FILES}
        self.oldpath=self.archive("old.tgz",self.old);self.newpath=self.archive("new.tgz",self.new)
        for name,data in self.new.items():
            dest=(self.root/"runtime"/Path(name).name if name.startswith(self.prefix) else self.root/"support/workspace_layout.py")
            dest.write_bytes(data)
        self.report={"schema":"wheat_pair_engineering_qualification_v1","baseline_revision":exact.BASELINE_REVISION,
                     "field_exact_equal":True,"real_worker_dispatch_verified":True,"mapper_calls":0,"formal_workspace_modified":False,
                     "baseline_output_sha256":"b"*64,"candidate_output_sha256":"b"*64,
                     "baseline_tools_sha256":exact.digest(self.oldpath),"candidate_tools_sha256":exact.digest(self.newpath)}
        self.manifest={"git_revision":"c"*40,"exact_engineering_change":{
            "schema":"q0_exact_pair_engineering_v1","baseline_revision":exact.BASELINE_REVISION,"runtime_revision":"c"*40,
            "baseline_archive":self.record(self.oldpath),"candidate_archive":self.record(self.newpath)}}
        self.bind_report()
        self.context=patch.multiple(exact,BASELINE_ARCHIVE_SHA256=exact.digest(self.oldpath),ENGINEERING_FILES=self.pins)
        self.context.start()
    def tearDown(self):self.context.stop();self.temp.cleanup()
    def record(self,p):return {"path":str(p),"sha256":exact.digest(p)}
    def archive(self,name,values):
        p=self.root/name
        with tarfile.open(p,"w:gz") as tar:
            for name,data in values.items():
                m=tarfile.TarInfo(name);m.size=len(data);tar.addfile(m,io.BytesIO(data))
        return p
    def bind_report(self):
        p=self.root/"qualification.json";p.write_text(json.dumps(self.report))
        self.manifest["exact_engineering_change"]["qualification"]=self.record(p)
    def test_qualified_whole_tree_and_unchanged_policies(self):
        self.assertEqual(exact.validate(self.root,self.manifest),self.manifest["exact_engineering_change"])
    def test_mismatch_or_no_real_workers_is_not_authorization(self):
        for key,value in [("field_exact_equal",False),("real_worker_dispatch_verified",False),
                          ("candidate_output_sha256","d"*64),("mapper_calls",1),("formal_workspace_modified",True)]:
            original=self.report[key];self.report[key]=value;self.bind_report()
            with self.assertRaisesRegex(ValueError,"not qualified"):exact.validate(self.root,self.manifest)
            self.report[key]=original
    def test_transition_source_and_report_tampering_fail_closed(self):
        p=self.root/"runtime/q0_paths.py";p.write_bytes(p.read_bytes()+b"# tampered\n")
        with self.assertRaisesRegex(ValueError,"differs from qualified"):exact.validate(self.root,self.manifest)
        p.write_bytes(self.new[self.prefix+p.name])
        (self.root/"qualification.json").write_text("{}")
        with self.assertRaises(ValueError):exact.validate(self.root,self.manifest)
    def test_extra_code_change_cannot_hide_behind_equal_output(self):
        changed=dict(self.new);changed[self.prefix+"q0_paths.py"]+=b"# new scientific algorithm\n"
        self.archive("new.tgz",changed)
        self.report["candidate_tools_sha256"]=exact.digest(self.newpath);self.bind_report()
        self.manifest["exact_engineering_change"]["candidate_archive"]=self.record(self.newpath)
        with self.assertRaisesRegex(ValueError,"outside exact engineering scope"):exact.validate(self.root,self.manifest)
    def test_scientific_class_cannot_change_even_if_engineering_pin_is_replaced(self):
        changed=dict(self.new);changed[self.prefix+"q0_admission.py"]=changed[self.prefix+"q0_admission.py"].replace(b"100",b"99")
        self.pins["q0_admission.py"]=sha256(changed[self.prefix+"q0_admission.py"]).hexdigest()
        self.archive("new.tgz",changed);self.report["candidate_tools_sha256"]=exact.digest(self.newpath);self.bind_report()
        self.manifest["exact_engineering_change"]["candidate_archive"]=self.record(self.newpath)
        with self.assertRaisesRegex(ValueError,"scientific policy changed"):exact.validate(self.root,self.manifest)
    def test_engineering_requires_explicit_scientific_baseline(self):
        with self.assertRaisesRegex(ValueError,"requires reviewed continuity"):prep.validate_continuity_change(self.root,self.manifest)


class ReviewedBytesTests(unittest.TestCase):
    def test_pins_bind_the_actual_reviewed_engine(self):
        core=Path(__file__).resolve().parents[3]/"server/tools/lgz_core"
        for name,pin in exact.ENGINEERING_FILES.items():self.assertEqual(exact.digest(core/name),pin)
