#!/usr/bin/env python3
"""Internal real-data experiments; no public CLI/defaults or active runs changed."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import shlex
import shutil
import statistics
import sys
import time
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""): h.update(b)
    return h.hexdigest()


def lengths(path):
    result = []
    with path.open("rb") as f:
        for line in f:
            if line.startswith(b">"): result.append(0)
            else: result[-1] += len(line.strip())
    return result


class Adaptive:
    """Non-preemptive admission with length-aware thread caps and completion feedback.

    The serial-fraction model is a heuristic, not measured minimap2 scaling.
    All allocated threads stay reserved until completion: no CPU overselling.
    """
    def __init__(self, features):
        self.features = features
        self.rates = []

    def desired(self, task, budget):
        f = self.features[task.unit_id]
        serial = f["largest_fraction"]
        cap = min(task.max_threads, budget)
        n = 1
        while n < cap:
            before = serial + (1 - serial) / n
            after = serial + (1 - serial) / (n + 1)
            if before / after - 1 < .08: break
            n += 1
        return n

    def complete(self, task, threads, seconds):
        f = self.features[task.unit_id]
        fraction = f["largest_fraction"] + (1 - f["largest_fraction"]) / threads
        self.rates.append(seconds / max(f["work"] * fraction, 1))

    def __call__(self, pending, available, budget, active, slots):
        if not available or not slots: return []
        ordered = sorted(pending, key=lambda t: self.features[t.unit_id]["work"], reverse=True)
        selected = []
        for task in ordered:
            need = self.desired(task, budget)
            if need > available:
                if not self.rates or not active: break
                # Backfill short work only; do not admit a long task at 1 thread
                # merely because its preferred allocation is currently unavailable.
                rate = statistics.median(self.rates)
                now = time.monotonic()
                remaining = [max(.1, self.features[x["task"].unit_id]["work"] * rate *
                    (self.features[x["task"].unit_id]["largest_fraction"] +
                     (1-self.features[x["task"].unit_id]["largest_fraction"])/x["threads"])
                    - (now-self.features[x["task"].unit_id].get("started",now))) for x in active]
                short = next((p for p in ordered if p not in [t for t,_ in selected]
                    and self.desired(p,budget)<=available
                    and self.features[p.unit_id]["work"]*rate <= min(remaining)/2), None)
                if short is not None: selected.append((short,self.desired(short,budget)))
                break
            selected.append((task,need));available-=need
            if not available or len(selected)>=slots: break
        return selected


def paf_summary(path):
    count=0;total=0;square=0;strong={};modulus=1<<256
    with path.open() as f:
        for line in f:
            fields=line.rstrip("\n").split("\t")
            if len(fields)<12 or not any(v.startswith("cg:Z:") for v in fields[12:]):
                raise ValueError("Incomplete PAF/CIGAR: "+str(path))
            qs,qe,ts,te=map(int,(fields[2],fields[3],fields[7],fields[8]))
            assert 0<=qs<=qe<=int(fields[1]) and 0<=ts<=te<=int(fields[6])
            canonical="\t".join(fields[:12]+sorted(fields[12:]))
            d=int.from_bytes(hashlib.sha256(canonical.encode()).digest(),"big")
            count+=1;total=(total+d)%modulus;square=(square+d*d)%modulus
            if qe-qs>=5000 and int(fields[10]) and int(fields[9])/int(fields[10])>=.9:
                key="|".join((fields[0],fields[5],fields[4]))
                strong.setdefault(key,[]).append((qs,qe))
    coverage={}
    for key,intervals in strong.items():
        merged=[]
        for a,b in sorted(intervals):
            if merged and a<=merged[-1][1]: merged[-1][1]=max(b,merged[-1][1])
            else: merged.append([a,b])
        coverage[key]=merged
    return {"rows":count,"ordered_sha256":sha(path),"unordered_digest_sum":hex(total),
            "unordered_digest_square_sum":hex(square),"strong_query_coverage_by_pair_strand":coverage}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--workspace",type=Path,required=True)
    p.add_argument("--tools",type=Path,required=True)
    p.add_argument("--mode",choices=("schedule","precision"),required=True)
    p.add_argument("--profile",choices=("baseline","rmq100","rmq0","freq100"),default="baseline")
    a=p.parse_args();sys.path.insert(0,str(a.tools))
    from alignment_tasks import AlignmentTask,run_tasks
    out=a.root/("schedule" if a.mode=="schedule" else "precision-"+a.profile)
    out.mkdir(parents=True,exist_ok=False)
    dirs=sorted(a.workspace.glob("runs/chr_*/*_vs_self"))
    if a.mode=="precision":
        dirs=[a.workspace/"runs/chr_BSWB01000001.1/hifiasm_vs_self",
              a.workspace/"runs/chr_BSWB01000003.1/flye_vs_self"]
    assert dirs
    mm=Path(shutil.which("minimap2"));budget=16 if a.mode=="schedule" else 2
    report={"status":"RUNNING","mode":a.mode,"profile":a.profile,"budget":budget,
            "tool":{"path":str(mm.resolve()),"sha256":sha(mm)},"inputs":{},"runs":{},
            "boundary":"Same-version self alignment only. No query/target splitting or old m40/n3 rerun. Schedule pair serial on one node; OS cache/order bias remains. Admission count bounds memory conservatively, not live resizing. PAF digest equality is content evidence, not Final Path acceptance."}
    def save():
        temp=out/"report.tmp";temp.write_text(json.dumps(report,indent=2)+"\n");temp.replace(out/"report.json")
    save();features={}
    for d in dirs:
        name=d.parent.name+"__"+d.name;lens=lengths(d/"self_query.fa")
        features[name]={"largest_fraction":max(lens)/sum(lens),"work":sum(lens)*(d/"self_target.fa").stat().st_size,"records":len(lens)}
        report["inputs"][name]={"path":str(d),"query_lengths":lens,**{n:sha(d/n) for n in ("self_query.fa","self_target.fa","self_name_map.tsv","restore_self_paf.py")}}
    save()
    profiles=("current","adaptive") if a.mode=="schedule" else (a.profile,)
    for profile in profiles:
        run=out/profile;run.mkdir();tasks=[];policy=Adaptive(features)
        for d in dirs:
            name=d.parent.name+"__"+d.name;dest=run/name;dest.mkdir()
            extra={"rmq100":["--rmq-inner","100"],"rmq0":["--rmq-inner","0"],"freq100":["-U","50,100"]}.get(profile,[])
            command=["/usr/bin/time","-v","-o","resource.txt",str(mm),"-c","-x","asm10","-X","--no-hash-name","-m","200","-n","100",*extra]
            text="#!/bin/bash\nset -euo pipefail\n"+shlex.join(command)+' -t "$GPM_TASK_THREADS" '+shlex.join([str(d/"self_target.fa"),str(d/"self_query.fa")])+" 2> minimap.stderr | "+shlex.join([sys.executable,str(d/"restore_self_paf.py"),str(d/"self_name_map.tsv")])+" > result.paf.tmp\nmv result.paf.tmp result.paf\n"
            script=dest/"command.sh";script.write_text(text)
            cap=min(budget,features[name]["records"])
            tasks.append(AlignmentTask(name,script,cap,features[name]["work"],1 if a.mode=="precision" else 8))
        if profile=="current":
            tasks=[AlignmentTask(t.unit_id,t.command,t.max_threads,t.priority) for t in tasks]
        active={};rows=[];start=time.monotonic();last=start;area=0;idle=0
        def account():
            nonlocal last,area,idle
            now=time.monotonic();used=sum(x["threads"] for x in active.values())
            area+=(now-last)*used
            if used<budget/2:idle+=now-last
            last=now
        def begin(task,n):
            account();now=time.monotonic();features[task.unit_id]["started"]=now
            active[task.unit_id]={"threads":n,"start":now}
            print(profile,"START",task.unit_id,"threads",n,flush=True)
        def finish(task,code,cancelled):
            account();row=active.pop(task.unit_id);seconds=time.monotonic()-row["start"]
            rows.append({"task":task.unit_id,"threads":row["threads"],"seconds":seconds,"exit":code,"cancelled":cancelled})
            if code==0:policy.complete(task,row["threads"],seconds)
            report["runs"][profile]={"state":"RUNNING","completed":rows};save()
            print(profile,"END",task.unit_id,"seconds",seconds,"exit",code,flush=True)
        # Deadline uses the production process-group cancellation mechanism.
        code=run_tasks(tasks,budget,{},lambda: 15 if time.monotonic()-start>43200 else None,
                       begin,lambda *_:None,finish,os.environ.copy(),dispatch=policy if profile=="adaptive" else None)
        account();wall=time.monotonic()-start
        report["runs"][profile]={"state":"PASS" if code==0 else "FAILED_OR_TIMEOUT","exit":code,"seconds":wall,"tasks":rows,
             "reserved_core_seconds":area,"reserved_utilization":area/(budget*wall),"below_half_reserved_seconds":idle,
             "note":"Reservation utilization is not measured CPU utilization."};save()
        if code:report["status"]="FAILED_OR_TIMEOUT";save();raise SystemExit(code)
        report["runs"][profile]["paf"]={t.unit_id:paf_summary(t.command.parent/"result.paf") for t in tasks};save()
    if a.mode=="schedule":
        left,right=(report["runs"][k]["paf"] for k in profiles)
        report["ordered_equal"]=all(left[k]["ordered_sha256"]==right[k]["ordered_sha256"] for k in left)
        report["content_equal"]=all(all(left[k][f]==right[k][f] for f in ("rows","unordered_digest_sum","unordered_digest_square_sum")) for k in left)
        report["status"]="PASS" if report["content_equal"] else "DIFFERENT"
    else: report["status"]="COMPLETED_AWAITING_PRECISION_COMPARISON"
    save()

if __name__=="__main__":main()
