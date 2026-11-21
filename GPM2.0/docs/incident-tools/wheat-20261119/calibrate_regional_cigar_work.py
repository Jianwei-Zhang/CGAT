"""Compare weak-chain span products before CIGAR; no production policy change."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import profile_regional_chaining as profile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control-dir",type=Path,required=True)
    p.add_argument("--residual-dir",type=Path,required=True)
    p.add_argument("--minimap2",type=Path,required=True)
    a=p.parse_args();root=Path.cwd().resolve();reports=[];inputs={}
    for role,directory in [("control",a.control_dir),("residual",a.residual_dir)]:
        path=directory/"summary.json";raw=path.read_bytes();inputs[str(path)]=hashlib.sha256(raw).hexdigest();proof=json.loads(raw)
        if proof.get("status")!="isolated_regional_pilot_complete":raise ValueError("complete regional pilot required")
        for i,site in enumerate(proof["sites"]):
            out=root/f"{role}-{i}";out.mkdir();old=list(sys.argv)
            try:
                os.chdir(out);sys.argv=["profile","--source-site",str(directory/f"site-{i}"),"--minimap2",str(a.minimap2)];profile.main()
            finally:os.chdir(root);sys.argv[:]=old
            status=json.loads((out/"summary.json").read_text())
            if status["status"]!="chaining_only_exit" or status["exit_code"]!=0:raise ValueError("calibration chaining did not complete")
            count=0;heavy={str(cut):dict(chains=0,span_product=0) for cut in (1000,5000,10000)};all_area=0
            with (out/"approximate.paf").open() as f:
                for line in f:
                    fields=line.rstrip("\r\n").split("\t");tags={t.split(":",2)[0]:t.split(":",2)[2] for t in fields[12:]}
                    qs=int(fields[3])-int(fields[2]);ts=int(fields[8])-int(fields[7]);score=int(tags["s1"]);count+=1;all_area+=qs*ts
                    for cut,row in heavy.items():
                        if min(qs,ts)>=int(cut) and score/max(qs,ts)<.25:row["chains"]+=1;row["span_product"]+=qs*ts
            reports.append(dict(role=role,core_start=site["core_start"],chains=count,all_span_product=all_area,weak_chain_span_product=heavy,chaining_seconds=status["seconds"]))
    for path,sha in inputs.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError("calibration source report changed")
    report=dict(status="read_only_cigar_work_calibration",sites=reports,inputs=inputs,scientific_acceptance=False,production_policy_changed=False,
                limitations="span product is a cost proxy, not measured DP cells; seed score density is not base identity; approximate PAF never serves as paired evidence")
    (root/"summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)


if __name__=="__main__":main()
