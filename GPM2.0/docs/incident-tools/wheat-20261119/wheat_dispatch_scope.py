"""Frozen whole-wheat first-request routing; read-only data and atomic diagnostic shard files."""
from bisect import bisect_left,bisect_right
from collections import Counter,defaultdict
import csv,gzip,io,json,os
from hashlib import sha256
from pathlib import Path
from census_wheat_q0_fork import SNAP,LOOK,GEOM,HEAD,MAGIC,bind,bounded,require
from lgz_core.common import stable_id
from lgz_core.q0_sources import SourceKey,merged_intervals
from lgz_core.q0_threshold_acceptance import decode,record

REV="44e274a715308e3d15598832947b83aa32b88450"; SN="1ca1582715d7b2eef8d7d007db6825d04b77d2c513ddd7ae073efff690e14d66"
REQ="f9229b186ff3587d6929cb8f6116e61f03086f9807b08c51af089d653032be77"; AX="7c93bb87545a40a561ac09a88260cc043a297f1236a6d5875c837d4d17542c31"
QUERIES="e01cb1aaed6f22804e42832db38944e9c5d43018668fc3a3bd1e20927de3e113"; ACCOUNT="ec3acc7d8831833563a1a9c208aa26c611e60d77bc409c9c6b5c9c694204af4f"
TGZ="0f06edd183467d950cd99d5c11ca8ed23ff57aaeacce96a6580b7527573dac28"; CK="ee15ca3032344729505abea30036c2799d8a06fb8d702db589d62de98a9445f4"; FORK="3027c5d33b8891223b336a5f4f8ea07dae1f643287c66590680c5e0f7389ff19"

def put(p,v):
    d=(json.dumps(v,separators=(",",":"),sort_keys=True,allow_nan=False)+"\n").encode();d=gzip.compress(d,compresslevel=1,mtime=0) if p.suffix==".gz" else d
    tmp=p.with_name(p.name+f".{os.getpid()}.partial")
    with tmp.open("xb") as f:f.write(d)
    os.link(tmp,p);tmp.unlink();return sha256(d).hexdigest()

def get(p,pin=None):
    d=p.read_bytes(); require(pin is None or sha256(d).hexdigest()==pin,"content drift: "+str(p));return json.loads(gzip.decompress(d) if p.suffix==".gz" else d)

def inputs(base):return bind(base/"q0-latest-fork-20261123-1435/control/snapshot.json",base/"q0-source-part-lookup-20261121-1600/source-part-lookup.json")

def questions_from_store(base,out):
    from wheat_selection_checkpoint import Store
    from lgz_core.q0_threshold_prepare import prep
    from lgz_core.q0_threshold_questions import ends,supported
    run=base/"q0-request-ready.44e274a7"; snap,root,lookup,order,lens=inputs(base);rank={s:i for i,s in enumerate(order)}; pins={r["path"]:r["sha256"] for r in snap["files"]}
    def table(p):return list(csv.DictReader(io.StringIO(bounded(root/p,64<<20,pins[p]).decode()),delimiter="\t"))
    chk=json.loads(bounded(run/"control/snapshot.json",1<<20,SN));require(chk==dict(snap,revision=REV),"producer inputs changed")
    req=json.loads(bounded(run/"control/global-first-request.json",4<<20,REQ));require(req["revision"]==REV and req["has_path"] and not req["published_q0"] and req["mapper_calls"]==0 and req["snapshot_sha256"]==SN and req["threshold_contract"]==prep.supplement_policy("positive_threshold")["decision_frontier"],"wrong frozen request")
    expected=decode(req["request"],lens); account=json.loads(bounded(run/"accounting/result/first-demand.json",1<<20,ACCOUNT));require(account["request_sha256"]==REQ,"foreign accounting")
    log=bounded(run/"gate-v2/whole_43058410.out",32<<20,"a43b3ecba2bcf862b03205b212e6ae5932e5b2d296de6107a9a727ea129c8d90");require(b"placements: sufficient=2735 weak=390; unknown joins: sufficient_to_keep_gap=0 need_evidence=2946" in log,"cannot infer unknown join causes without original facing result")
    ref,=table("metadata/reference.tsv");p=ref["fai_relpath"]; references={s[0]:int(s[1]) for s in (v.split("\t") for v in bounded(root/p,8<<20,pins[p]).decode().splitlines())};groups=defaultdict(set)
    for row in table("metadata/chr_assignments.tsv"):groups[rank[SourceKey(row["dataset_name"],row["seq_name"]) ]].add(row["assigned_chr_name"])
    store=Store(run/"selection",[SN,REV,32,TGZ,CK,FORK],False);ad=store.load_admission();require(ad is not None and len(ad.placements)==8985,"wrong admission");placed={p.placement_id:p for p in ad.placements}; issues=[];union=defaultdict(list);strong=0
    def issue(kind,c,key,spans,extra):
        for source,iv in spans:union[source].append(iv)
        issues.append(dict(kind=kind,group=c,id=key,spans=[[rank[s],iv.start,iv.end] for s,iv in spans],**extra))
    for i,c in enumerate(sorted(references),1):
        row=store.load_group(i,c);require(row is not None and row.path is not None,"missing chromosome or path; new decision replay needed");path=row.path
        for s in path.slices:
            p=placed[s.placement_id];require(p.source==s.source and p.orientation==s.orientation and p.interval.contains(s.interval),"slice binding")
            sides=ends(s.interval,100);anchors=merged_intervals(p.anchor_intervals) if p.localization_kind in ("reference","pairwise") else ();weak=[v for v in sides if not supported(v,anchors,100)] if sides else [s.interval]
            if weak:issue("weak_placement",c,p.placement_id,[(p.source,v) for v in weak],dict(strand=s.orientation))
            else:strong+=1
        for l,j,r in zip(path.slices,path.joins,path.slices[1:]):
            if j.kind!="reference_unknown":continue
            lp,rp=placed[l.placement_id],placed[r.placement_id];require((j.left_id,j.right_id)==(l.placement_id,r.placement_id) and j.evidence_ids,"join binding")
            from lgz_core.q0_sources import Interval
            spans=[(v.source,v.source_interval(Interval(max(0,x-2000),min(v.interval.length,x+2000)))) for v,x in ((lp,j.left_end),(rp,j.right_start))];issue("unproven_join",c,j.join_id,spans,dict(placements=[j.left_id,j.right_id],strands=[lp.orientation,rp.orientation]))
    require(store.previous=="6e1849c34a1f6e2f91a1e7f2f5549f0224a70134892fd941f9856f3e5ff74288" and strong==2735 and Counter(v["kind"] for v in issues)=={"weak_placement":390,"unproven_join":2946} and len({(v["group"],v["id"]) for v in issues})==len(issues),"decision counts/binding changed")
    require(record({s:merged_intervals(v) for s,v in union.items()})==req["request"] and len(expected)==3111,"question causes do not reproduce exact request")
    receipt=put(out/"issues.json.gz",dict(request_sha256=REQ,issues=issues,memberships={k:sorted(v) for k,v in groups.items()},reference_bases=sum(references.values()),reference_names=sorted(references)));print("BOUND_QUESTIONS",len(issues),receipt,flush=True)

class Shoulders:
    def __init__(self,issues):
        by=defaultdict(list)
        for i,q in enumerate(issues):
            for r,a,b in q["spans"]:by[r].append((a,b,i))
        self.by={}
        for r,v in by.items():
            v.sort();hi=0;prefix=[]
            for a,b,i in v:hi=max(hi,b);prefix.append(hi)
            self.by[r]=[x[0] for x in v],prefix,v
    def collect(self,geom,out):
        r,a,b=geom;s=self.by.get(r)
        if s:
            starts,ends,rows=s
            for j in range(bisect_right(ends,a),bisect_left(starts,b)):
                if rows[j][1]>a:out.add(rows[j][2])

def original_queries(base,lookup,order):
    path=base/"q0-fork-partial-queries-20261123-1556/plan/queries.tsv.gz";keys={r:k for k,(r,_,_) in lookup.items()};queries={}
    with gzip.GzipFile(fileobj=io.BytesIO(bounded(path,8<<20,QUERIES))) as f:
        for line in f:
            token,r,a,b=line.split();r,a,b=map(int,(r,a,b));qid=token.decode();k=keys[r];n=lookup[k][1];require(0<=a<b<=n and qid==stable_id("q0-query-window",dict(segment_id=k,segment_length=n,start=a,end=b)) and qid not in queries,"invalid query inventory");queries[qid]=[r,a,b]
    require(len(queries)==61000,"wrong plan size");return queries

def observed(base,out):
    snap,root,lookup,order,lens=inputs(base);queries=original_queries(base,lookup,order);shoulders=Shoulders(get(out/"issues.json.gz")["issues"]);seen=set();h=sha256();batch=[];shards={};known={}
    def publish():
        name=f"seen-{len(shards):04d}.json.gz";shards[name]=put(out/name,batch);batch.clear()
    with gzip.open(base/"q0-fork-window-census-20261123-1505/census/axes.bin.gz","rb") as f:
        magic=f.read(len(MAGIC));require(magic==MAGIC,"wrong census");h.update(magic)
        while head:=f.read(HEAD.size):
            ctx,token,size=HEAD.unpack(head);require(1<size<=2_000_000,"bad window size");body=f.read(GEOM.size*size);require(len(body)==GEOM.size*size,"truncated census");h.update(head);h.update(body)
            name="q0-regional-context-"+ctx.hex();qid="q0-query-window-"+token.hex();rows=GEOM.iter_unpack(body);q=next(rows);require(queries[qid]==list(q) and qid not in seen,"query does not match plan");seen.add(qid)
            left=set();right=set();shoulders.collect(q,left)
            for v in rows:shoulders.collect(v,right)
            batch.append([qid,*q,name,sha256(head+body).hexdigest(),sorted(left),sorted(right),None]);known[qid]=name
            if len(batch)==256:publish()
    if batch:publish()
    require(h.hexdigest()==AX and len(seen)==23845,"historical window census changed")
    # Reuse previously proven 4D context IDs, but recompute question overlaps for WHOLE wheat, not 4D-only demand.
    prior=get(base/"q0-fast4d-20261125.T0MmzPVx/all-plan/result/planned.json","0c7e45935500147f51fe5616f73d6dff44a93af12d0a3b1853199b72d836ef73");rows=[];known4=0
    from census_wheat_q0_fork import pack_context
    for v in prior["all_rows"]:
        qid=v["query"]
        if qid in seen:require(known[qid]==v["context"],"4D observed identity changed");continue
        ctx=v["context"];p=root/"grt/evidence/q0_prepare/regional"/ctx/"context.json"
        if not p.is_file():continue
        spec=json.loads(bounded(p,64<<20))["spec"];packed=pack_context(ctx,spec,lookup);require(sha256(packed).hexdigest()==v["axis_hash"],"4D proven target frame differs"); geoms=GEOM.iter_unpack(packed[HEAD.size:]);q=next(geoms);require(list(q)==queries[qid],"4D query mismatch");left=set();right=set();shoulders.collect(q,left)
        for axis in geoms:shoulders.collect(axis,right)
        batch.append([qid,*q,ctx,v["axis_hash"],sorted(left),sorted(right),None]);seen.add(qid);known4+=1
        if len(batch)==256:publish()
    if batch:publish()
    todo=[[q,*v] for q,v in queries.items() if q not in seen];pending=put(out/"pending.json.gz",todo);issues=sha256((out/"issues.json.gz").read_bytes()).hexdigest();put(out/"known.json",dict(request=REQ,issues=issues,shards=shards,archive_count=23845,restored_4d=known4,pending_sha256=pending,pending_count=len(todo)));print("KNOWN_GEOMETRY_READY",len(seen),"PLANNER_REMAINING",len(todo),flush=True)
