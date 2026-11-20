import contextlib,copy,hashlib,io,json,runpy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
SOURCE=Path(__file__).with_name("native_fair_handoff_gate.py").read_text()
PRODUCTION="/share/home/xbzhang26/cgat-reads-debug/jm19-compare-614589f-20261118"
class GateTests(unittest.TestCase):
    def check(self,mutate=None,error=None,locked=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/"work";work.mkdir();(work/".run_all").mkdir()
            if locked:(work/".run_all/lock").mkdir()
            plan=root/"plan.json";plan.write_text("{}")
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
            gate=root/"gate.py"
            source=SOURCE.replace(PRODUCTION+"/native-fair-revision-20261120-1350/plan/self-plan.json",str(plan)).replace(PRODUCTION+"/gpm_server",str(work)).replace("343f1d1933c71d79105405f958b5241887d1fa0f0c936ed1a3d3a70befe039f3",sha(plan))
            gate.write_text(source)
            old={"jobId":"42943728","state":"FAILED","resGroups":[{"nodeResUsages":[{"pids":"-"}]}]}
            new={"jobId":"99999999","state":"RUNNING","queue":"x86","taskExecNodes":"fixture-node","taskExecNodesCount":1,
                 "resGroups":[{"resAlloc":{"cpu":32,"mem":327680},"resLimit":{"mem":327680}}]}
            def release(_):
                h={"old_job":42943728,"new_job":99999999,"protected_baseline":42523432,
                    "status":"old_job_terminal_and_normal_lock_released","plan_sha256":sha(plan),
                    "ready_sha256":sha(root/"ready.json")}
                if mutate:mutate(old,new,h)
                for key,obj in (("old_scheduler",old),("new_scheduler",new)):
                    path=root/(key+".json");path.write_text(json.dumps({"data":{"successData":[obj]}}))
                    h[key]={"path":str(path),"sha256":sha(path)}
                (root/"handoff.json").write_text(json.dumps(h))
            with patch("time.sleep",side_effect=release),patch("socket.gethostname",return_value="fixture-node"),contextlib.redirect_stdout(io.StringIO()):
                if error:
                    with self.assertRaisesRegex(SystemExit,error):runpy.run_path(str(gate),run_name="__main__")
                else:runpy.run_path(str(gate),run_name="__main__")
    def test_valid(self):self.check()
    def test_old_running(self):self.check(lambda o,n,h:o.update(state="RUNNING"),"not terminal")
    def test_children_live(self):self.check(lambda o,n,h:o["resGroups"][0]["nodeResUsages"][0].update(pids="123"),"children")
    def test_locked(self):self.check(locked=True,error="locked")
    def test_wrong_old(self):self.check(lambda o,n,h:o.update(jobId="42876793"),"not terminal")
    def test_protected_baseline(self):self.check(lambda o,n,h:h.update(protected_baseline=0),"invalid handoff")
    def test_wrong_new(self):self.check(lambda o,n,h:n.update(jobId="1"),"allocation")
    def test_low_cpu(self):self.check(lambda o,n,h:n["resGroups"][0]["resAlloc"].update(cpu=16),"allocation")
    def test_low_memory_limit(self):self.check(lambda o,n,h:n["resGroups"][0]["resLimit"].update(mem=163840),"allocation")
    def test_wrong_node(self):self.check(lambda o,n,h:n.update(taskExecNodes="other-node"),"allocation")
    def test_wrong_plan(self):self.check(lambda o,n,h:h.update(plan_sha256="changed"),"invalid handoff")
    def test_wrong_ready(self):self.check(lambda o,n,h:h.update(ready_sha256="changed"),"invalid handoff")
if __name__=="__main__":unittest.main()
