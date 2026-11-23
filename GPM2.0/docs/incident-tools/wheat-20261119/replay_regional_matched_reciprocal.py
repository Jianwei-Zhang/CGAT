"""Verify a deterministic holdout selected by observed reciprocal overlap.

The seed PAFs stay fixed. Select holdouts from the older SHA-bound trace using
only their query cores and metadata, not holdout PAF contents. A target-only
union is deliberately not treated as equivalent evidence for Q0/Q1.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import json
from pathlib import Path
import socket
import time

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, TRACE_SHA
from lgz_core.q0_sources import Interval, merged_intervals
from replay_regional_reciprocal_coverage import (MIB, STATIC_SHA, add_reverse, bound_bytes, clip_pair,
    covered_bases, length, load, locus_loss, projected, qualified_pairs, query_window)


def ranked_matches(trace, seeds, cover):
    raw={r['raw_receipt']:r for r in trace['raw_markers']}
    projects={p['raw']:p for p in trace['new_projects'] if p['raw'] in raw}
    if not len(raw)==len(trace['raw_markers'])==len(projects)==1189:
        raise ValueError('frozen raw/project join differs')
    full=[]; partial=[]; ids=set()
    for key,meta in raw.items():
        query=query_window(projects[key]['query'])
        if query.window_id in ids:
            raise ValueError('duplicate held-out query frame')
        ids.add(query.window_id)
        if query.window_id in seeds or query.segment_id not in cover:
            continue
        cores=tuple(Interval(*i) for i in query.cores)
        bases=length(cores); n=covered_bases(cores,cover[query.segment_id])
        if n:
            row={**meta,'query':projects[key]['query'],'core_bases':bases,'covered_core_bases':n}
            (full if n==bases else partial).append(row)
    full.sort(key=lambda r:(-r['cpu_seconds'],r['raw_receipt']))
    partial.sort(key=lambda r:(-Fraction(r['covered_core_bases'],r['core_bases']),-r['cpu_seconds'],r['raw_receipt']))
    return full,partial


def locus_groups(raw_hits,datasets,cores):
    groups={}
    for hit in raw_hits:
        for q,t in qualified_pairs(hit,datasets):
            for core in cores:
                pair=clip_pair(q,t,hit.strand,core)
                if pair:
                    qs,ts=groups.setdefault((hit.query_name,hit.target_name,hit.strand),([],[]))
                    qs.append(pair[0]); ts.append(pair[1])
    return groups


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','cohort','trace','lookup','output'):
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args(); start=time.monotonic(); work=a.workspace.resolve(strict=True); out=a.output.resolve()
    if out.is_relative_to(work):
        raise ValueError('output must be outside production workspace')
    static=json.loads(bound_bytes(a.cohort,STATIC_SHA,16*MIB))['rows']
    rows=static[:64]
    if [r['ordinal'] for r in rows]!=list(range(64)) or not all(r['anchor_case'] for r in rows):
        raise ValueError('wrong original seed cohort')
    lookup=json.loads(bound_bytes(a.lookup,LOOKUP_SHA,32*MIB)); datasets={k:v['dataset'] for k,v in lookup.items()}
    trace=json.loads(bound_bytes(a.trace,TRACE_SHA,4*MIB))
    cover=defaultdict(list); rev={}; seeds=set(); total=0
    for row in rows:
        q,targets,raw=load(work,row,lookup,128*MIB-total); total+=len(raw)
        if q.window_id in seeds:
            raise ValueError('duplicate seed')
        seeds.add(q.window_id)
        for hit in projected(q,targets,raw,row['raw_receipt']):
            for qb,tb in qualified_pairs(hit,datasets):
                cover[hit.target_name].append(tb); add_reverse(rev,hit,qb,tb)
    cover={key:merged_intervals(values) for key,values in cover.items()}
    rev={key:tuple(merged_intervals(side) for side in values) for key,values in rev.items()}
    full,partial=ranked_matches(trace,seeds,cover)
    print(json.dumps({'matched_full':len(full),'matched_partial':len(partial),'seed_parts':len(cover),'seed_raw_bytes':total}),flush=True)
    answers=[]
    # Bound proof reads even if more targeted holdouts are available. Full
    # candidates first; partial controls measure difference on their covered subset.
    selected=[*full[:32],*partial[:32]]
    for row in selected:
        q,targets,raw=load(work,row,lookup,192*MIB-total); total+=len(raw)
        evidence=cover[q.segment_id]
        cores=tuple(Interval(max(a,x.start),min(b,x.end)) for a,b in q.cores for x in evidence if a<x.end and x.start<b)
        if length(cores)!=row['covered_core_bases']:
            raise ValueError('held-out candidate coverage changed')
        groups=locus_groups(projected(q,targets,raw,row['raw_receipt']),datasets,cores)
        answers.append({'raw_receipt':row['raw_receipt'],'raw_receipt_sha256':row['raw_receipt_sha256'],
            'segment_id':q.segment_id,'window_id':q.window_id,'core_bases':row['core_bases'],
            'covered_core_bases':row['covered_core_bases'],'historical_exact_cpu_seconds':row['cpu_seconds'],
            'raw_paf_bytes':len(raw),'oriented_locus_loss_if_covered_cores_omitted':locus_loss(groups,rev)})
    summary={'status':'matched_geometry_and_paired_locus_only_NOT_production_admission','node':socket.gethostname(),
        'matched_full_metadata':len(full),'matched_partial_metadata':len(partial),'seed_windows':len(seeds),
        'seed_parts':len(cover),'trace_raw_windows':len(trace['raw_markers']),'verified_raw_bytes':total,
        'verified_candidate_cases':answers,'seconds':time.monotonic()-start,
        'main_workspace_modified':False,'native_mapper_executed':False,
        'limits':['Windows from one frozen trace, not representative or live pending count.',
          'Compare both coordinates within oriented segment pairs; not paired position identity, intra-assembly or final candidate equivalence.',
          'Historical CPU covers native exact work only; partial-window time is not reducible in proportion to bp.']}
    with out.open('x') as f:
        json.dump(summary,f,indent=2,sort_keys=True); f.write('\n')


if __name__=='__main__':
    main()
