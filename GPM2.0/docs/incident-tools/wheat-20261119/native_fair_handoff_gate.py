import datetime,hashlib,json,os,socket,time
from pathlib import Path
root=Path(__file__).resolve().parent
plan=Path('/share/home/xbzhang26/cgat-reads-debug/jm19-compare-614589f-20261118/native-fair-revision-20261120-1350/plan/self-plan.json')
work=Path('/share/home/xbzhang26/cgat-reads-debug/jm19-compare-614589f-20261118/gpm_server')
expected='343f1d1933c71d79105405f958b5241887d1fa0f0c936ed1a3d3a70befe039f3'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if digest(plan)!=expected:raise SystemExit("plan changed")
ready={"status":"resource_ready_waiting_handoff", "protected_baseline":42523432,"pid":os.getpid(),"host":socket.gethostname(),
       "plan_sha256":expected,"old_job":42943728,"at":datetime.datetime.now().astimezone().isoformat()}
with (root/"ready.json").open("x") as f:json.dump(ready,f,indent=2);f.flush();os.fsync(f.fileno())
ready_sha=digest(root/"ready.json")
print("NATIVE_FAIR_READY_WAITING_HANDOFF",json.dumps(ready),flush=True)
for _ in range(10800):
    release=root/"handoff.json"
    if release.is_file():
        h=json.loads(release.read_text())
        if (h.get("old_job")!=42943728 or h.get("status")!="old_job_terminal_and_normal_lock_released"
                or h.get("protected_baseline")!=42523432
                or h.get("plan_sha256")!=expected or h.get("ready_sha256")!=ready_sha
                or digest(plan)!=expected or (work/".run_all/lock").exists()):
            raise SystemExit("invalid handoff or workspace still locked")
        def evidence(name):
            row=h[name];p=Path(row["path"])
            if p.parent!=root or digest(p)!=row["sha256"]:raise SystemExit("scheduler proof changed")
            return json.loads(p.read_text())["data"]["successData"][0]
        old=evidence("old_scheduler");new=evidence("new_scheduler")
        if str(old["jobId"])!="42943728" or old["state"] not in ("FAILED","SUCCEEDED"):
            raise SystemExit("prior newer job is not terminal")
        usages=[u for g in old["resGroups"] for u in g.get("nodeResUsages",[])]
        if not usages or any(u.get("pids") not in ("-", "", []) for u in usages):
            raise SystemExit("prior newer children are not confirmed gone")
        groups=new["resGroups"]
        if (str(new["jobId"])!=str(h["new_job"]) or new["state"]!="RUNNING" or new["queue"]!="x86"
                or len(groups)!=1 or new["taskExecNodesCount"]!=1
                or groups[0]["resAlloc"]["cpu"]<32 or groups[0]["resAlloc"]["mem"]<327680
                or groups[0]["resLimit"]["mem"]<327680
                or new["taskExecNodes"]!=socket.gethostname()):
            raise SystemExit("new job does not have the verified single-node 32CPU/320GiB allocation")
        print("NATIVE_FAIR_HANDOFF_ACCEPTED",json.dumps(h),flush=True)
        break
    time.sleep(2)
else:raise SystemExit("handoff wait expired without workspace modification")
