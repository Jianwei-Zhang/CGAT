"""Finish the frozen 4D-query plan: use archived windows first, reconstruct only missing target sets."""
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
import csv
import gzip
from hashlib import sha256
import io
import json
from multiprocessing import get_context
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from census_wheat_q0_fork import GEOM,HEAD,MAGIC,bind,bounded,pack_context,require,write
from check_wheat_inverse_targets import reference,intersects,lookups
from lgz_core import q0_regional_execution as execution, q0_regional_mapping as mapping
from lgz_core.common import stable_id
from lgz_core.q0_query_windows import QueryWindow,TargetWindow
from lgz_core.q0_sources import Interval,SourceKey
from lgz_core.q0_threshold_acceptance import decode
from pilot_exact_group_windows import REQUEST,AXES,TOOL


def init(snapshot,parts,demand,tool):
    global _parts,_demand,_tool
    execution._initialize_reader(snapshot);_parts,_demand,_tool=parts,demand,tool


def plan(rows):
    index=execution._WORKER_INDEX;result=[];index.verify_inputs()
    for qid,key,a,b in rows:
        rank,n,_=_parts[key]; regions=index.regions(key,Interval(a,b),anchor_context=1_000_000,reference_context=10_000)
        values=index.targets(regions,context=10_000,exclude=[key]);bases=sum(i.length for v in values.values() for i in v)
        direct=intersects((rank,a,b),_demand);touch=any(intersects((_parts[p][0],i.start,i.end),_demand) for p,v in values.items() for i in v)
        row=dict(query=qid,part=key,category="query" if direct else "target_only" if touch else "neither")
        if not values or bases>mapping.MAX_TARGET_BASES:
            result.append(dict(row,fallback="no_reference_targets" if not values else "regional_target_budget"));continue
        q=QueryWindow(key,n,a,b,((a,b),)); targets=sorted((TargetWindow(p,_parts[p][1],i.start,i.end) for p,ivs in values.items() for i in ivs),key=lambda v:v.window_id); members=sorted({key,*values}); spec=dict(schema=mapping.CONTEXT_SCHEMA,query=mapping._window_context(q),targets=[mapping._window_context(t) for t in targets],members=[[p,_parts[p][2]] for p in members],tool=_tool,preset="asm10",fasta_format="wrap80_v1")
        ctx=stable_id("q0-regional-context",spec);result.append(dict(row,context=ctx,axis_hash=sha256(pack_context(ctx,spec,_parts)).hexdigest()))
    index.verify_inputs();return result


def main(base,out):
    snap,root,lookup,order,lengths=bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json");pins={v["path"]:v["sha256"] for v in snap["files"]}
    p="metadata/chr_assignments.tsv";members={SourceKey(r["dataset_name"],r["seq_name"]) for r in csv.DictReader(io.StringIO(bounded(root/p,64<<20,pins[p]).decode()),delimiter="\t") if r["assigned_chr_name"]=="4D"};require(len(members)==766 and sum(lengths[s] for s in members)==1074672025,"wrong group")
    req=decode(json.loads(bounded(base/"q0-request-ready.44e274a7/qualification/4d-first-request.json",4<<20,REQUEST)),lengths);idx=lookups(req,order);require(len(req)==181 and set(req)<=members,"wrong request");rank_to_part={v[0]:k for k,v in lookup.items()};seen={}; digest=sha256()
    with gzip.open(base/"q0-fork-window-census-20261123-1505/census/axes.bin.gz","rb") as f:
        magic=f.read(len(MAGIC));require(magic==MAGIC,"bad census");digest.update(magic)
        while head:=f.read(HEAD.size):
            ctx,qid,size=HEAD.unpack(head);require(1<size<=2_000_000,"invalid target count");data=f.read(size*GEOM.size);require(len(data)==size*GEOM.size,"short census");digest.update(head);digest.update(data);rows=GEOM.iter_unpack(data);q=next(rows);r,a,b=q
            if order[r] not in members:continue
            hit=intersects(q,idx); target=any(intersects(v,idx) for v in rows);name="q0-query-window-"+qid.hex();require(name not in seen,"duplicate observed query");seen[name]=dict(query=name,part=rank_to_part[r],category="query" if hit else "target_only" if target else "neither",context="q0-regional-context-"+ctx.hex(),axis_hash=sha256(head+data).hexdigest())
    require(digest.hexdigest()==AXES and len(seen)==307,"observed archive changed");control={};todo=[];seen_ids=set();old=dict(seen)
    packed=bounded(base/"q0-fork-partial-queries-20261123-1556/plan/queries.tsv.gz",8<<20,"e01cb1aaed6f22804e42832db38944e9c5d43018668fc3a3bd1e20927de3e113")
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as f:
        for line in f:
            token,r,a,b=line.split();r,a,b=map(int,(r,a,b));qid=token.decode();p=rank_to_part[r]
            if order[r] not in members:continue
            require(qid not in seen_ids and qid==QueryWindow(p,lengths[order[r]],a,b,((a,b),)).window_id,"wrong group query id");seen_ids.add(qid)
            if qid not in seen:todo.append((qid,p,a,b))
            elif seen[qid]["category"] not in control:control[seen[qid]["category"]]=qid;todo.append((qid,p,a,b))
    require(len(seen_ids)==754 and seen.keys()<=seen_ids and len(control)==3 and len(todo)==450,"unexpected plans or controls")
    tool=mapping._ops().executable_identity("minimap2");require(tool["sha256"]==TOOL,"wrong tool")
    print("EXACT_GROUP_TARGETS",len(todo),"including",len(control),"frozen context controls",flush=True)
    with TemporaryDirectory(prefix="4d-plan-") as tmp, reference(snap,root,lookup,order,lengths,Path(tmp)) as index, ProcessPoolExecutor(max_workers=4,mp_context=get_context("spawn"),initializer=init,initargs=(index.reader_snapshot(),lookup,idx,tool)) as pool:
        for j,batch in enumerate(pool.map(plan,(todo[i:i+4] for i in range(0,len(todo),4)))):
            for v in batch:
                q=v["query"]
                if q in old:require(old[q]==v,"historical full targets differ from original observed context")
                else:require(q not in seen,"duplicate output");seen[q]=v
            if j%10==9:print("EXACT_GROUP_TARGETS_COMPLETED",min(4*(j+1),len(todo)),flush=True)
    require(seen.keys()==seen_ids,"incomplete group plan");fallback={v["part"] for v in seen.values() if "fallback" in v};groups=Counter(v["category"] for v in seen.values()); kept=[];scope=Counter()
    for q,v in sorted(seen.items()):
        if v["part"] in fallback:scope["whole_parent_fallback_windows"]+=1;continue
        if v["category"]=="neither":scope["neither"]+=1;continue
        kept.append(v);scope["observed_touched" if q in old else "reconstructed_touched"]+=1
    write(out/"planned.json",dict(group="4D",all_queries=754,computed_target_sets=447,checked_exact_context_controls=3,categories_before_parent_fallback=groups,partial_after_parent_rule=scope,fallback_parents=len(fallback),all_rows=[dict(v,archived=q in old) for q,v in sorted(seen.items())],eligible_regions=kept,scope="Original historical partial stage, restricted by query membership. Not native parent coverage or final Q0."))
    print("PLAN",groups,scope,"fallback parents",len(fallback),flush=True)


if __name__=="__main__":main(*map(Path,sys.argv[1:]))
