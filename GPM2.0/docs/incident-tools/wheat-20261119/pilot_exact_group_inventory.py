"""Read-only exact raw/chain audit of every demand-touching *observed 4D-query* context."""
from collections import Counter
import csv
from dataclasses import asdict
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from time import monotonic

from census_wheat_q0_fork import bind, bounded, pack_context, require, write
from pilot_exact_group_windows import AXES, REQUEST, TOOL, select
from lgz_core import q0_regional_mapping as m
from lgz_core.q0_alignments import read_paf
from lgz_core.q0_cigar_policy import CigarWorkPolicy, select_cigar_profile
from lgz_core.q0_query_windows import QueryWindow
from lgz_core.q0_sources import SourceKey
from lgz_core.q0_threshold_acceptance import decode
from lgz_core.common import sha256_file,stable_id


def audit(root,lookup,tool,rb,category,name,stamp,*,locators=False):
    rel="grt/evidence/q0_prepare/regional/"+name; d=root/rel; raw=bounded(d/"context.json",64<<20); c=json.loads(raw);spec=c["spec"];w=spec["query"]
    require(sha256(pack_context(name,spec,lookup)).hexdigest()==stamp and spec["tool"]==tool and spec["targets"]==sorted(spec["targets"],key=lambda v:v["window_id"]),"different frozen context/order/tool")
    ctx=m._ops().identity(root,rel+"/context.json");require(ctx["sha256"]==sha256(raw).hexdigest(),"context changed")
    targets={x["window_id"]:x["end"]-x["start"] for x in spec["targets"]};require(len(targets)==len(spec["targets"]),"duplicate targets")
    q=QueryWindow(w["segment_id"],w["segment_length"],w["start"],w["end"],((w["start"],w["end"]),));policy=CigarWorkPolicy();need_chain=rb>=policy.minimum_reference_bases and q.length>=policy.minimum_query_bases
    def verify(sub,specification):
        receipt=sub+"/success.json"
        if not (root/receipt).is_file():return None
        record=m._read_receipt(root,receipt,spec=specification,required={sub+"/"+n for n in ("guard.py","command.json","result.paf")})
        m._verify_command(root,sub,rel,spec,specification["flags"])
        return record
    row=dict(context=name,category=category)
    if need_chain:
        chain=rel+"/chaining"; record=verify(chain,dict(schema="lgz_q0_regional_chaining_v1",context=ctx,flags=m.BASE_FLAGS))
        if record is None:return dict(row,status="missing_chain")
        work=m.chain_work(root/chain/"result.paf",q,targets,policy);decision=select_cigar_profile(rb,q.length,work,complete=True,preset=spec["preset"],policy=policy)
        decision["chaining_receipt"]=m._ops().identity(root,chain+"/success.json")
    else:
        decision=dict(schema="lgz_q0_cigar_profile_v1",policy=asdict(policy),reason="screening_not_needed",reference_bases=rb,query_bases=q.length,additional_flags=[],approximate_chaining_is_evidence=False)
    path=d/(stable_id("q0-regional-decision",decision)+".json")
    if not path.is_file():return dict(row,status="missing_matching_decision")
    require(json.loads(bounded(path,1<<20))==decision,"decision drift")
    rs=dict(schema="lgz_q0_regional_raw_v1",context=ctx,flags=["-c",*m.BASE_FLAGS,*decision["additional_flags"]]);sub=rel+"/"+stable_id("q0-regional-raw",rs); leaf=verify(sub,rs)
    if leaf is None:return dict(row,status="missing_raw")
    nr=sum(1 for _ in read_paf(root/sub/"result.paf",query_lengths={q.window_id:q.length},target_lengths=targets)); pin=next(v for v in leaf["outputs"] if v["path"]==sub+"/result.paf")
    if locators:
        row.update(context_file=ctx,decision_file=m._ops().identity(root,rel+"/"+path.name),chaining_receipt=decision.get("chaining_receipt"),raw_receipt=m._ops().identity(root,sub+"/success.json"),raw_paf=pin)
    return dict(row,status="verified",raw_sha256=pin["sha256"],raw_bytes=pin["size"],raw_rows=nr,coarse_required=need_chain,flags=rs["flags"])


def main(base,out):
    s,root,lookup,order,lengths=bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json");pins={r["path"]:r["sha256"] for r in s["files"]}
    def table(p):return list(csv.DictReader(io.StringIO(bounded(root/p,64<<20,pins[p]).decode()),delimiter="\t"))
    members={SourceKey(r["dataset_name"],r["seq_name"]) for r in table("metadata/chr_assignments.tsv") if r["assigned_chr_name"]=="4D"};require(len(members)==766 and sum(lengths[s] for s in members)==1074672025,"wrong group")
    ref,=table("metadata/reference.tsv");f=ref["fai_relpath"]; rb=sum(int(v.split(b"\t")[1]) for v in bounded(root/f,4<<20,pins[f]).splitlines());req=decode(json.loads(bounded(base/"q0-request-ready.44e274a7/qualification/4d-first-request.json",4<<20,REQUEST)),lengths);require(len(req)==181 and set(req)<=members,"wrong demand")
    ranks={i for i,s in enumerate(order) if s in members};idx={i:(tuple(v.start for v in req[s]),tuple(v.end for v in req[s])) for i,s in enumerate(order) if s in req}
    counts,selected=select(base/"q0-fork-window-census-20261123-1505/census/axes.bin.gz",ranks,idx,limit=None);require(counts=={"neither":131,"query":29,"target_only":147},"sample and census disagree")
    packed=bounded(base/"q0-fork-partial-queries-20261123-1556/plan/queries.tsv.gz",8<<20,"e01cb1aaed6f22804e42832db38944e9c5d43018668fc3a3bd1e20927de3e113");planned=direct=total=0
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as inp:
        from bisect import bisect_right
        for line in inp:
            _,r,a,b=line.split();total+=1;r,a,b=map(int,(r,a,b));planned+=r in ranks
            if r in idx:
                starts,ends=idx[r];i=bisect_right(ends,a);direct+=i<len(starts) and starts[i]<b
    require(total==61000 and planned>=sum(counts.values()),"wrong historical census")
    tool=m._ops().executable_identity("minimap2");require(tool["sha256"]==TOOL,"wrong binary");t=monotonic(); rows=[]
    for category,picks in sorted(selected.items()):
        for name,stamp in picks:
            rows.append(audit(root,lookup,tool,rb,category,name,stamp))
            if len(rows)%20==0:print("RAW_AUDIT",len(rows),"/176",flush=True)
    require(len(rows)==176 and len({r["context"] for r in rows})==176 and sha256_file(Path(tool["resolved"]))==TOOL,"incomplete or changed tool")
    summary=dict(group="4D",query_members=len(members),reference_bases=rb,all_planned_4D_queries=planned,direct_hits_all_planned_4D_queries=direct,observed=counts,unobserved_4D_queries=planned-sum(counts.values()),status_counts=dict(Counter(r["status"] for r in rows)),raw_rows=sum(r.get("raw_rows",0) for r in rows),raw_bytes=sum(r.get("raw_bytes",0) for r in rows),audit_wall_s=monotonic()-t,launched_mappers=0,request_sha256=REQUEST,axes_sha256=AXES,contexts=rows,scope="Historical original 4D-query contexts; verified decision, raw and any required chaining. Not a projection/ready receipt, a guarantee for other target scopes, a count for other query groups, or a cold 4D speedup.")
    write(out/"inventory.json",summary);print({k:v for k,v in summary.items() if k!="contexts"},flush=True)


if __name__=="__main__":main(*map(Path,sys.argv[1:]))
