"""Use only verified node-local reference PAF/index bytes. Never construct Q0 or start a mapper."""
from bisect import bisect_right
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing,contextmanager
import gzip
from hashlib import sha256
import json
from multiprocessing import get_context
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace

from census_wheat_q0_fork import bind,bounded,GEOM,HEAD,MAGIC,require,write,SNAP
from fork_wheat_q0 import copy_bound,member
from inverse_wheat_target_evidence import invert,target_hit
from measure_replayed_wheat_demand import QUERIES,REPLAY
from replay_wheat_partial_queries import AXES
from lgz_core.common import stable_id
from lgz_core.q0_reference_index import ReferenceIndex
from lgz_core.q0_sources import Interval,merged_intervals
from lgz_core.q0_threshold_acceptance import decode
from lgz_core.q0_preparation import supplement_policy
from lgz_core import q0_regional_execution as execution

CACHE='reference-index-fdad41a395b84a35a2176f31'
RECEIPT='69b80ca1859b83018376434f803707f396f5c4b304cb10c40e2ab81bd69f9e68'


def axes(path,inspect):
    """Verify the frozen stream in order; only expand target geometries the caller will inspect."""
    h=sha256(); n=0; seen=set()
    with gzip.open(path,'rb') as f:
        magic=f.read(len(MAGIC));require(magic==MAGIC,'wrong census');h.update(magic)
        while head:=f.read(HEAD.size):
            ctx,qid,size=HEAD.unpack(head);require(1<size<=2_000_000 and qid not in seen,'not the unique-query census');seen.add(qid)
            data=f.read(GEOM.size*size);require(len(data)==GEOM.size*size,'short census');h.update(head);h.update(data);inspect(n,qid,data);n+=1
    require(n==23845 and h.hexdigest()==AXES,'wrong frozen contexts');return seen


@contextmanager
def reference(frozen,root,meta,order,lengths,tmp):
    rows={r['path']:r for r in frozen['files']}; directory='grt/evidence/q0_prepare/indexes/'+CACHE+'/'; receipt=json.loads(bounded(member(root,directory+'success.json'),1<<20,RECEIPT)); require(receipt['key']==CACHE and receipt['status']=='success' and receipt['inputs']==sorted((r for n,r in rows.items() if n.startswith('runs/') and n.endswith('_vs_ref/result.paf')),key=lambda v:v['path']),'wrong index inputs')
    rel=next(n for n in rows if n.startswith('data/reference/') and n.endswith('.fai')); refs={line[0]:int(line[1]) for line in (v.split('\t') for v in bounded(member(root,rel),8<<20,rows[rel]['sha256']).decode().splitlines())};parts={p:SimpleNamespace(segment_id=p,source=order[rank],interval=Interval(0,size),sequence_sha256=d) for p,(rank,size,d) in meta.items()};require(stable_id('reference-index',{'binding':ReferenceIndex.bindings(parts,refs),'inputs':receipt['inputs']})==CACHE,'wrong reference geometry')
    require(shutil.disk_usage(tmp).free>receipt['size']+sum(v['size'] for v in receipt['inputs'])+(8<<30),'insufficient private disk')
    db=tmp/'reference.sqlite';copy_bound(member(root,directory+'reference.sqlite'),db,{**receipt,'path':directory+'reference.sqlite'},96<<20)
    for row in receipt['inputs']:copy_bound(member(root,row['path']),tmp/row['path'],row,96<<20)
    with closing(ReferenceIndex.open(db,tmp,parts,refs)) as index:
        yield index
        index.verify_inputs()


def calibrate(index,lookup,order,part_ids,archive):
    samples=[]
    def take(n,qid,data):
        if n%719==31:samples.append((qid.hex(),tuple(GEOM.iter_unpack(data))))
    axes(archive,take);need=defaultdict(list)
    for _,(_, *targets) in samples[::8]:
        for rank,a,b in (targets[0],targets[-1]):need[order[rank]].append(Interval(max(a,b-100),b))
    frontier={s:merged_intervals(v) for s,v in need.items()};start=monotonic(); mask=invert(index,frontier);build=monotonic()-start
    counts=Counter(); timing=Counter(); fingerprint=sha256()
    for qid,((rank,a,b),*targets) in samples:
        q=part_ids[rank]; start=monotonic(); regions=index.regions(q,Interval(a,b),anchor_context=1000000,reference_context=10000);timing['query_regions']+=monotonic()-start
        start=monotonic(); baseline=index.targets(regions,context=10000,exclude=[q]); timed=monotonic()-start
        actual=sorted((lookup[p][0],i.start,i.end) for p,vals in baseline.items() for i in vals);require(actual==sorted(targets),'frozen target inventory differs from full regional planner'); forward=any(any(a<j.end and j.start<b for j in frontier.get(order[r],())) for r,a,b in actual);timing['ordinary_target_enumeration']+=timed
        start=monotonic(); reverse=target_hit(mask,regions,q);timing['inverse_lookup']+=monotonic()-start;require(forward==reverse,'inverse predicate differs');counts['target_hit' if reverse else 'target_miss']+=1;fingerprint.update(bytes.fromhex(qid)+bytes([reverse]));
    require(len(counts)==2,'calibration needs positive and negative witnesses');return {'windows':len(samples),'artificial_probe_sources':len(frontier),'outcomes':counts,'verdict_sha256':fingerprint.hexdigest(),'seconds':{**timing,'inverse_build':build},'limits':'Predeclared ordinal sample from frozen contexts. Probe shoulders deliberately taken from a few real target windows, not the global first request; not mapper savings.'}


def lookups(demand,order):
    return {r:(tuple(i.start for i in demand[s]),tuple(i.end for i in demand[s])) for r,s in enumerate(order) if s in demand}


def intersects(geom,idx):
    rank,a,b=geom
    if rank not in idx:return False
    starts,ends=idx[rank];i=bisect_right(ends,a);return i<len(starts) and starts[i]<b


def init_worker(snapshot,mask):
    global _MASK
    execution._initialize_reader(snapshot);_MASK=mask


def inverse_group(group):
    index=execution._WORKER_INDEX;index.verify_inputs(); answers=[]
    for qid,p,a,b in group:
        regions=index.regions(p,Interval(a,b),anchor_context=1000000,reference_context=10000)
        answers.append((qid,target_hit(_MASK,regions,p)))
    index.verify_inputs();return answers


def whole(index,mask,demand,order,part_ids,lookup,archive,plan,counts,workers):
    idx=lookups(demand,order); known={}; check={}; controls=defaultdict(int)
    def observed(n,qid,data):
        q=GEOM.unpack_from(data); touched=intersects(q,idx); targets=GEOM.iter_unpack(data);next(targets); t=any(intersects(g,idx) for g in targets);known[qid]=(q,touched,t)
        # Always include positive and negative target controls if present, not just easy misses.
        if controls[t]<32:check[qid]=t;controls[t]+=1
    axes(archive,observed); hist=Counter();groups=defaultdict(list);seen=set(); digest=sha256()
    for line in gzip.decompress(bounded(plan/'queries.tsv.gz',8<<20,QUERIES)).splitlines(keepends=True):
        digest.update(line);s,rank,a,b=line.decode().split();r,a,b=map(int,(rank,a,b)); p=part_ids[r];qid=bytes.fromhex(s.rsplit('-',1)[1]);q=(r,a,b);require(qid not in seen and s==stable_id('q0-query-window',{'segment_id':p,'segment_length':lookup[p][1],'start':a,'end':b}),'query identity mismatch');seen.add(qid)
        if qid in known:
            geom,hit,t=known[qid];require(q==geom,'census geometry mismatch');hist['known_query' if hit else 'known_target_only' if t else 'known_neither']+=1
            if qid not in check:continue
        elif intersects(q,idx):hist['unseen_query']+=1;continue
        groups[p].append((qid,p,a,b))
    require(len(seen)==61000 and known.keys()<=seen and digest.hexdigest()==json.loads(bounded(plan/'replay.json',1<<20,REPLAY))['queries_uncompressed_sha256'],'wrong replay inventory'); acc=counts['accounting'];require(hist['known_query']+hist['known_target_only']==acc['known_either_axis'] and hist['known_neither']==acc['known_neither_axis'] and hist['unseen_query']==acc['without_target_inventory_query_intersects'],'census and full-query accounting disagree');
    # Fresh metadata-only processes; CPU count includes the coordinating parent. Return only verdicts.
    jobs=(rows[i:i+64] for rows in groups.values() for i in range(0,len(rows),64)); completed=set(); total=sum(map(len,groups.values())); print('INVERSE_LOOKUPS',total,'including',len(check),'controls',flush=True)
    with ProcessPoolExecutor(max_workers=workers,mp_context=get_context('spawn'),initializer=init_worker,initargs=(index.reader_snapshot(),mask)) as pool:
        for batch in pool.map(inverse_group,jobs,chunksize=8):
            for qid,t in batch:
                require(qid not in completed,'duplicate result');completed.add(qid)
                if qid in check:require(t is check[qid],'real frozen target verdict and inverse disagree')
                else:hist['unseen_target_only' if t else 'unseen_neither']+=1
            if len(completed)%500==0:print('INVERSE_COMPLETED',len(completed),'/',total,flush=True)
    require(len(completed)==total and check.keys()<=completed and sum(hist.values())==len(seen),'incomplete result');return {'categories':hist,'different_known_targets_checked':len(check),'query_or_target_hit':len(seen)-hist['known_neither']-hist['unseen_neither'],'neither_axis_hit':hist['known_neither']+hist['unseen_neither'],'conditional_on':'Original partial regional targets, before parent native coverage, absence/target-budget fallback, candidate stage and repair. Not executed mapper calls.'}


def run(base,out,mode,workers):
    ctrl=base/'q0-latest-fork-20261123-1435/control'; frozen,root,lookup,order,lengths=bind(ctrl/'snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json');require(not out.exists() and not out.is_relative_to(root) and mode in ('calibrate','first') and 1<=workers<=4,'unsafe invocation');parts=[p for p,v in sorted(lookup.items(),key=lambda pair:pair[1][0])];archive=base/'q0-fork-window-census-20261123-1505/census/axes.bin.gz';qbase=base/'q0-fork-partial-queries-20261123-1556';report={'schema':'wheat_inverse_exact_target_test_v1','mode':mode,'snapshot':SNAP,'index_receipt_sha256':RECEIPT,'mapper_calls':0}
    if mode=='first':
        raw=bounded(ctrl/'global-first-request.json',64<<20);req=json.loads(raw); acc_raw=bounded(qbase/'demand/full-query-accounting.json',1<<20);counts=json.loads(acc_raw);h=sha256(raw).hexdigest();require(req['schema']=='wheat_threshold_global_first_request_v1' and req['revision']==frozen['revision'] and req['snapshot_sha256']==SNAP and req['threshold_contract']==supplement_policy('positive_threshold')['decision_frontier'] and req['mapper_calls']==0 and req['published_q0'] is False and type(req['has_path']) is bool and counts['schema']=='wheat_partial_query_and_observed_target_first_demand_v1' and counts['snapshot']==SNAP and counts['replay_sha256']==REPLAY and counts['request_sha256']==h and counts['has_path'] is req['has_path'],'wrong request or accounting');demand=decode(req['request'],lengths); kind='full_fallback' if demand is None else 'localized' if demand else 'base_only' if req['has_path'] else 'no_supported_backbone';require(counts['accounting']['request_kind']==kind,'wrong demand mode');report.update(request_kind=kind,request_sha256=h,accounting_sha256=sha256(acc_raw).hexdigest())
        if kind!='localized':write(out,report);print('NOT_LOCALIZED',kind);return
    with TemporaryDirectory(prefix='wheat-inverse-',dir='/tmp') as tmp, reference(frozen,root,lookup,order,lengths,Path(tmp)) as index:
        if mode=='calibrate':report['calibration']=calibrate(index,lookup,order,parts,archive)
        else:report['first_partial_geometry']=whole(index,invert(index,demand),demand,order,parts,lookup,archive,qbase/'plan',counts,workers)
    write(out,report);print(json.dumps(report),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),sys.argv[3],int(sys.argv[4]))
