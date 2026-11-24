"""One-shot Donau release of the pinned f9ed324f whole first request; no tests or mapper launched here."""
import fcntl
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REV = "f9ed324f3984efc41eb780159f8294b5f4db2545"
SNAP = "451a42a602e5359a3783e1fc139620ba3a1b47d74bfe55b46e1d8c94e66e9512"
OLD_SNAP = "1ac0f77f60dce3398fa10372f641baa19bc2dbb2ce80c31f28281258a9a5cfc5"
BASE = Path.home() / "cgat-reads-debug/jm19-compare-614589f-20261118"
ROOT = BASE / "q0-request-ready.f9ed324f"
QUAL = ROOT / "qualification"
PREV = BASE / "q0-whole-hybrid.u1ylvM"
JOB = "43054355"
NAME = "jm19_whole_request_f9ed"
FIELDS = {"ambiguous", "has_path", "occupied", "paths", "placements", "records", "request", "sequences", "unplaced"}


def must(ok, msg):
    if not ok:
        raise ValueError(msg)


def read(p, pin=None):
    must(not p.is_symlink() and p.is_file() and p.stat().st_size < 8*1024**2, "invalid gate file: " + str(p))
    raw = p.read_bytes()
    must(pin is None or sha256(raw).hexdigest() == pin, "digest mismatch: " + str(p))
    return raw


def write(p, s):
    with p.open("x") as f:
        f.write(s)


def query(*args):
    return subprocess.check_output(list(args), timeout=45).decode()


def jobrow(raw):
    rows = json.loads(raw)["data"]["successData"]
    must(len(rows) == 1, "ambiguous qualification job")
    r = rows[0]
    must(str(r["jobId"]) == JOB and r["jobName"] == "jm19_4D_request_f9ed324f" and r["user"] == "xbzhang26"
         and Path(r["execPath"]) == QUAL and r["queue"] == "x86", "wrong qualification identity")
    return r


def allocation(r):
    g, = r["resGroups"]
    must(r["taskExecNodesCount"] == 1 and r["taskExecNodes"] == "agent-X86-52" and g["resAlloc"]["cpu"] == 8
         and min(g["resAlloc"]["mem"], g["resLimit"]["mem"]) >= 65536, "wrong frozen 4D allocation")


def verify():
    must(Path.cwd() == ROOT and read(QUAL/"candidate.jobid").decode().strip() == JOB, "wrong stage or job")
    must(jobrow(read(ROOT/"qualification-terminal.json"))["state"] == "SUCCEEDED", "4D did not succeed")
    run = jobrow(read(QUAL/"allocation.json")); must(run["state"] == "RUNNING", "no live allocation evidence"); allocation(run)
    for d, manifests in ((ROOT, {"transfer.sha256":"6344a2d9bbdfbd09b6578902d656b381dc24b036cc40f78d64e3d6f15a822feb"}),
                         (QUAL, {"inputs.sha256":"5e4dea497d50798b9f25b9bf3085b3b07a70ca6ab758f474a39d7e56cdc77c67",
                                 "candidate.sha256":"b98c2c4d7747a528b73375c9807f1c284642c56e75b5c6dd1a378fed8fb150dc"})):
        for filename, pin in manifests.items():
            for line in read(d/filename, pin).decode().splitlines():
                digest, name = line.split(); read(d/name, digest)
    frozen = json.loads(read(PREV/"control/snapshot.json", OLD_SNAP))
    must(json.loads(read(ROOT/"control/snapshot.json", SNAP)) == dict(frozen, revision=REV), "whole input differs")
    baseline = json.loads(read(BASE/"q0-4d-pair-lanes.Nf85nm/candidate.json", "cb03d0c4b81dc403570d886c3c911f0d61151d53173b4550c776dd284e885a8a"))
    previous = json.loads(read(BASE/"q0-4d-hybrid-grid.CTICeL/candidate.json", "f3945261d443a9e4c04adf2e197270feb8f5c036f2015a9b5a8f10396000d1ba"))
    c = json.loads(read(QUAL/"candidate.json")); comp = json.loads(read(QUAL/"comparison.json")); req = json.loads(read(QUAL/"4d-first-request.json", "1a51ebcfef103cb8c986ca7e98cb11eb7e86f6d68f9100d057fc3446e9698ec5"))
    must(comp["revision"] == c["revision"] == REV and baseline["revision"] == comp["baseline"] and comp["equal"] is True
         and comp["raw_request_equal"] is True and comp["different"] == [], "comparison did not pass")
    must(c["scientific"] == baseline["scientific"] == previous["scientific"] and set(c["scientific"]) == FIELDS
         and c["scientific"]["has_path"] is True and "4D" in c["scientific"]["sequences"], "scientific field differs")
    must(all(c[k] == baseline[k] for k in ("members", "bp", "chromosome", "matrix_bytes", "ref_records"))
         and c["members"] == 766 and c["chromosome"] == "4D" and len(req) == c["request_sources"] == 181
         and sum(len(v) for _, v in req) == c["request_intervals"] == comp["request_intervals"] == 300, "different inventory")
    elapsed = c["timing"]["draft_s"]; ceiling = baseline["timing"]["draft_s"]
    must(math.isfinite(elapsed) and 0 < elapsed == comp["draft_s"] < ceiling == comp["baseline_draft_s"],
         "4D draft did not beat the frozen baseline: {} vs {} s".format(elapsed, ceiling))
    print("4D_GATE_PASS", JOB, REV, "draft_s", elapsed, "baseline_s", ceiling, flush=True)


def node():
    rows = [l.split() for l in query("dnode").splitlines()]; choices = []
    for r in rows:
        if (len(r) >= 7 and re.fullmatch(r"agent-X86-\d+", r[0]) and r[0] not in {"agent-X86-05","agent-X86-52","agent-X86-57"}
                and r[1] == "OK" and int(r[3]) >= 32 and int(r[6]) >= 327680):
            choices.append((int(r[3]), int(r[6]), r[0]))
    return max(choices)[2] if choices else None


def replace_one(s, a, b):
    must(s.count(a) == 1, "changed frozen scheduler template: " + a); return s.replace(a, b)


def submit(target):
    existing = [ROOT, PREV, BASE/"q0-whole-pair-lanes.xzqe7b", BASE/"q0-whole-repaired.ewp15v"]
    must(not any((d/"control/global-first-request.json").exists() for d in existing), "a whole request already exists; review first")
    must(NAME not in query("djob", "--output", "jobId:10 name:36 state:12"), "whole job already present")
    batch = read(PREV/"whole.dsub", "3e10fc1962a98e36acc6868a9e542fddaf99d1e98e5e8be85b3bc925f4d61793").decode()
    pub = read(PREV/"publish.py", "60bb66606e0de48a120f37c9936a27a93f268ee1f9290f97217f0b166b3cab06").decode()
    for a,b in (("jm19_whole_hybrid", NAME), ("agent-X86-14", target)):
        batch = replace_one(batch, a, b); pub = replace_one(pub, a, b)
    batch = replace_one(replace_one(replace_one(batch, str(PREV), str(ROOT)), OLD_SNAP, SNAP),
                        "python3 -B verify.py", "python3 -B gate_f9ed_wheat_resubmit.py verify")
    write(ROOT/"whole.dsub", batch); (ROOT/"whole.dsub").chmod(0o700); write(ROOT/"publish.py", pub)
    names = ["whole.dsub", "publish.py", "gate_f9ed_wheat_resubmit.py", "qualification-terminal.json", "qualification/allocation.json",
             "qualification/candidate.json", "qualification/comparison.json", "qualification/4d-first-request.json", "control/snapshot.json"]
    write(ROOT/"launch.sha256", "".join(sha256(read(ROOT/n)).hexdigest()+"  "+n+"\n" for n in names))
    write(ROOT/"whole-submit.intent", "{} {} {}\n".format(REV, JOB, target)); print("SUBMIT_INTENT", target, flush=True)
    with (ROOT/"whole-submit.output").open("x") as f:
        subprocess.run(["dsub", "-s", str(ROOT/"whole.dsub")], stdout=f, stderr=subprocess.STDOUT, timeout=60, check=True)
    match = re.search(r"Submit job <(\d+)> successfully", (ROOT/"whole-submit.output").read_text()); must(match, "inspect submission output; do not retry")
    j = match.group(1); write(ROOT/"whole.jobid", j+"\n")
    with (ROOT/"whole-allocation.log").open("x") as f:
        proc=subprocess.Popen([sys.executable, "publish.py", j], stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
    print("WHOLE_SUBMITTED", j, target, "allocation_observer", proc.pid, flush=True)


def watch():
    must(Path.cwd() == ROOT and (QUAL/"candidate.jobid").read_text().strip() == JOB, "wrong stage or job")
    with (ROOT/"whole-gate.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); last = None
        while True:
            try: raw = query("djob", "-ll", "-J", JOB)
            except (OSError, subprocess.SubprocessError) as e:
                print("SCHEDULER_UNAVAILABLE", type(e).__name__, flush=True); time.sleep(30); continue
            state = jobrow(raw)["state"]
            if state != last: print("QUAL_STATE", state, flush=True); last = state
            if state == "SUCCEEDED": break
            if state in ("FAILED", "ENDED", "CANCELLED", "CANCELED", "LOST"): raise ValueError("no whole: "+state)
            time.sleep(30)
        write(ROOT/"qualification-terminal.json", raw); verify()
        while True:
            target = node()
            if target: break
            print("WAIT_RESOURCE 32cpu/320GiB", flush=True); time.sleep(60)
        submit(target)


if __name__ == "__main__":
    os.umask(0o077)
    if sys.argv[1:] == ["verify"]: verify()
    elif sys.argv[1:] == ["watch"]: watch()
    else: raise SystemExit("use watch or verify")
