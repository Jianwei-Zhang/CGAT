"""Join actual whole-wheat first demand to all replayed partial queries and the proven two-axis subset."""
from bisect import bisect_right
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import sys

from census_wheat_q0_fork import bind, bounded, require, SNAP, write
from replay_wheat_partial_queries import AXES
from lgz_core.common import stable_id
from lgz_core.q0_preparation import supplement_policy
from lgz_core.q0_threshold_acceptance import decode

REPLAY='9b7e12988d8fabe2fd360910d517a3e112e99da4b03578fe1ed9fdcff4d2a682'
QUERIES='e01cb1aaed6f22804e42832db38944e9c5d43018668fc3a3bd1e20927de3e113'


def account(mode, total, query_hits, known, hist):
    require(0<=query_hits<=total and 0<=known<=total and sum(hist.values())==known and all(type(v) is int and v>=0 for v in hist.values()),'invalid known counts')
    if mode!='localized':
        require(mode in ('base_only','full_fallback','no_supported_backbone') and (not known or hist=={('full_fallback' if mode=='full_fallback' else 'omitted'):known}), 'inconsistent nonlocal scope')
        return {'request_kind':mode,'localized_intersection_applicable':False,'base_only_first_request':mode=='base_only'}
    require(set(hist)<={'both','query_only','target_only','omitted'},'wrong two-axis census categories')
    unknown=total-known; direct=query_hits-hist.get('both',0)-hist.get('query_only',0); require(0<=direct<=unknown,'known query hits disagree with complete inventory')
    return {'request_kind':mode,'localized_intersection_applicable':True,'all_queries_directly_intersecting':query_hits,'known_either_axis':known-hist.get('omitted',0),'known_neither_axis':hist.get('omitted',0),'without_target_inventory_query_intersects':direct,'without_target_inventory_needs_target_check':unknown-direct}


def main(base,out):
    root=base/'q0-latest-fork-20261123-1435/control'; s,src,index,order,lengths=bind(root/'snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json'); require(not out.is_relative_to(src) and not out.exists(),'unsafe output')
    plan=base/'q0-fork-partial-queries-20261123-1556/plan'; replay=json.loads(bounded(plan/'replay.json',1<<20,REPLAY)); census=base/'q0-fork-window-census-20261123-1505/census/first-request-count.json'; raw=bounded(census,1<<20); measured=json.loads(raw); first=bounded(root/'global-first-request.json',64<<20); req=json.loads(first)
    require(req['schema']=='wheat_threshold_global_first_request_v1' and req['threshold_contract']==supplement_policy('positive_threshold')['decision_frontier'] and req['snapshot_sha256']==SNAP and req['revision']==s['revision'] and type(req['has_path']) is bool and req['published_q0'] is False and req['mapper_calls']==0,'wrong first request'); demand=decode(req['request'],lengths); mode='full_fallback' if demand is None else 'localized' if demand else 'base_only' if req['has_path'] else 'no_supported_backbone'
    require(measured['schema']=='existing_wheat_context_first_request_count_v1' and measured['snapshot']==SNAP and measured['mode']==mode and measured['has_path'] is req['has_path'] and measured['request_sha256']==sha256(first).hexdigest() and measured['inventory_sha256']==AXES,'two-axis result differs from demand')
    member=replay['membership_in_frozen_census']; known=member['contexts']; c=measured['counts']; require(replay['snapshot']==SNAP and replay['count_matches'] and member['matching_contexts']==member['planned_queries_with_observed_target_sets']==c['contexts']==c['distinct_query_windows']==known and not member['distinct_other_queries'],'cannot subtract duplicated or foreign query geometries')
    idx={k:(tuple(v.start for v in spans),tuple(v.end for v in spans)) for k,spans in (demand or {}).items()}; by_rank=[k for k,value in sorted(index.items(),key=lambda v:v[1][0])]; seen=set(); h=sha256(); touched=0
    with gzip.GzipFile(fileobj=io.BytesIO(bounded(plan/'queries.tsv.gz',8<<20,QUERIES))) as f:
        for row in f:
            h.update(row); raw_id,r,a,b=row.rstrip(b'\n').split(b'\t'); rank,a,b=map(int,(r,a,b)); require(0<=rank<len(order) and 0<=a<b<=lengths[order[rank]],'invalid query coordinates'); qid=raw_id.decode('ascii'); require(qid not in seen and qid==stable_id('q0-query-window',{'segment_id':by_rank[rank],'segment_length':lengths[order[rank]],'start':a,'end':b}),'invalid query identity'); seen.add(qid)
            if order[rank] in idx:
                starts,ends=idx[order[rank]]; i=bisect_right(ends,a); touched+=i<len(starts) and starts[i]<b
    require(h.hexdigest()==replay['queries_uncompressed_sha256'] and len(seen)==replay['logged_plan_count']==replay['replayed_query_count'],'wrong reconstructed query plan'); counts=account(mode,len(seen),touched,known,c['axes_breakdown'])
    report={'schema':'wheat_partial_query_and_observed_target_first_demand_v1','snapshot':SNAP,'revision':s['revision'],'request_sha256':sha256(first).hexdigest(),'replay_sha256':REPLAY,'two_axis_report_sha256':sha256(raw).hexdigest(),'has_path':req['has_path'],'first_request_sources':None if demand is None else len(demand),'first_request_intervals':None if demand is None else sum(len(v) for v in demand.values()),'planned_queries':len(seen),'frozen_two_axis_contexts':known,'accounting':counts,'limits':'This is partial-stage geometry before native parent reuse, fallback, candidate discovery, or repair. For a localized request, a missing target set can retain a query-side miss. No final Q0 or mapper call count inferred.'};write(out,report);print(json.dumps(report),flush=True)

if __name__=='__main__':main(*(Path(arg).resolve() for arg in sys.argv[1:]))
