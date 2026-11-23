"""Read-only pre-CIGAR chain sizing; approximate records are not evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--diagnostic-dir",type=Path,required=True);a=p.parse_args()
    proof=json.loads((a.diagnostic_dir/"summary.json").read_text())
    if proof.get("status")!="chaining_only_exit" or proof.get("exit_code")!=0:raise ValueError("complete chaining diagnostic required")
    path=a.diagnostic_dir/"approximate.paf";before=path.stat();digest=hashlib.sha256();rows=[];bins=Counter()
    with path.open("rb") as stream:
        for raw in stream:
            digest.update(raw);f=raw.decode().rstrip("\r\n").split("\t");tags={t.split(":",2)[0]:t.split(":",2)[2] for t in f[12:]}
            if "cg" in tags:raise ValueError("expected only approximate chains")
            qspan=int(f[3])-int(f[2]);tspan=int(f[8])-int(f[7]);score=int(tags["s1"]);fraction=int(f[9])/int(f[10])
            rows.append((score,qspan,tspan,fraction,int(f[9]),f[5]));bins[("span_ratio_lt_0.5" if min(qspan,tspan)/max(qspan,tspan)<.5 else "span_ratio_ge_0.5")]+=1
    after=path.stat()
    if (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError("approximate output changed")
    scores=[]
    for minimum in [40,200,500,1000,2000,5000,10000]:
        kept=[r for r in rows if r[0]>=minimum]
        scores.append(dict(minimum_chain_score=minimum,chains=len(kept),target_windows=len({r[-1] for r in kept}),
            sum_query_spans=sum(r[1] for r in kept),sum_target_spans=sum(r[2] for r in kept),approx_identity_ge_0_9=sum(r[3]>=.9 for r in kept),approx_identity_ge_0_95=sum(r[3]>=.95 for r in kept)))
    report=dict(status="read_only_chain_statistics",rows=len(rows),sha256=digest.hexdigest(),span_ratio_bins=dict(bins),score_thresholds=scores,
                strongest=[dict(score=r[0],query_span=r[1],target_span=r[2],estimated_identity=r[3],estimated_matches=r[4]) for r in sorted(rows,reverse=True)[:20]],
                scientific_acceptance=False,approximate_intervals_are_not_paired_coverage=True)
    Path("summary.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report),flush=True)


if __name__=="__main__":main()
