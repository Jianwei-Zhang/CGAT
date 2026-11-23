"""Retrospective ceiling for a *no eligible hit* screen on a fixed completed wheat cohort.
A witness is only a necessary Q0 hit threshold, not proof of selection or a mandatory mapper call.
"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from benchmark_regional_mapper_dispatch import TRACE_SHA, LOOKUP_SHA, within
from lgz_core.common import stable_id
from replay_regional_reciprocal_coverage import MIB, bound_bytes, load, projected


def join_trace(trace):
    raw={r['raw_receipt']:r for r in trace['raw_markers']}
    projects=[p for p in trace['new_projects'] if p['raw'] in raw]
    if (len(raw)!=len(trace['raw_markers']) or set(raw)!={p['raw'] for p in projects}
            or len(projects)!=len(raw) or len({p['project'] for p in projects})!=len(raw)):
        raise ValueError('ambiguous raw/project association')
    return [(raw[p['raw']],p) for p in projects]


def verify_project(work, raw, row):
    path=within(work,row['project'])
    with path.open('rb') as f: b=f.read(2*MIB+1)
    if len(b)>2*MIB:raise ValueError('oversized projection receipt')
    receipt=json.loads(b); spec=receipt['spec']; bound=spec['raw_receipt']
    if (receipt['status']!='success' or path.parent.name!=stable_id('q0-regional-project',spec)
            or bound['path']!=raw['raw_receipt'] or bound['sha256']!=raw['raw_receipt_sha256']
            or spec['query']!=row['query'] or path.name!='success.json'):
        raise ValueError('project differs from bound raw or query cores')
    return spec


def witness(query,targets,buf,art):
    any_row=False
    for hit in projected(query,targets,buf,art):
        any_row=True
        if 20*hit.matches>=19*hit.block_length and sum(n for n,op in hit.cigar if op in 'M=')>=100:
            return 'has_threshold_witness'
    return 'only_subthreshold_projection' if any_row else 'no_projected_rows'


def run(work,trace_path,lookup_path):
    trace=json.loads(bound_bytes(trace_path,TRACE_SHA,4*MIB)); lookup=json.loads(bound_bytes(lookup_path,LOOKUP_SHA,192*MIB))
    cohort=join_trace(trace); budget=sum(raw['paf_bytes'] for raw,_ in cohort)
    if len(cohort)!=1189 or budget>256*MIB:raise ValueError('unexpected cohort or byte budget')
    counts=Counter(); secs=Counter(); rows=[]
    for i,(raw,p) in enumerate(cohort):
        spec=verify_project(work,raw,p)
        q,ts,data=load(work,{**raw,'query':p['query']},lookup,budget)
        if ([r['window_id'] for r in spec['targets']]!=list(ts)
                or any({k:v for k,v in vars(ts[r['window_id']]).items() if k!='window_id'} != {k:v for k,v in r.items() if k!='window_id'} for r in spec['targets'])):
            raise ValueError('projection target inventory differs from bound context')
        budget-=len(data); verdict=witness(q,ts,data,raw['raw_receipt'])
        counts[verdict]+=1;secs[verdict]+=raw['real_seconds']; rows.append([raw['raw_receipt_sha256'],verdict])
        if (i+1)%100==0: print('VERIFIED',i+1,dict(counts),flush=True)
    if budget!=0:raise ValueError('incomplete cohort read')
    return {'schema':'wheat_frozen_threshold_witness_v1','trace_sha256':TRACE_SHA,'lookup_sha256':LOOKUP_SHA,
            'windows':len(rows),'paf_bytes':sum(r['paf_bytes'] for r,_ in cohort),'new_mapper_executions':0,
            'counts':dict(counts),'historical_mapper_real_seconds_sum':dict(secs),
            'per_receipt_verdict_digest':sha256(json.dumps(sorted(rows)).encode()).hexdigest(),
            'scope':'completed nonrandom windows; a threshold witness is not an admitted or necessary path decision'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('work','trace','lookup','out'):p.add_argument(n,type=Path)
    a=p.parse_args();work=a.work.resolve(strict=True);out=a.out.resolve()
    if out.is_relative_to(work) or out.exists():raise ValueError('output overlaps source')
    r=run(work,a.trace,a.lookup)
    with out.open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n')
