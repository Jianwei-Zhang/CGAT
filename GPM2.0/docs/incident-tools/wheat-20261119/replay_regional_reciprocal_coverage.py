"""Read-only two-wave replay of reciprocal coverage, not a work-omission gate.

Use authenticated completed raw PAFs plus their original projected frames. The
first 64 frozen windows supply only observed cross-assembly target-side blocks.
Measure coverage against the frozen 61k plan, and compare oriented loci in the
separate 64 completed controls. Do not read DNA, map, or write any cache.
"""
import argparse
from collections import defaultdict
import hashlib
import io
import json
from pathlib import Path
import socket
import time

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, within
from lgz_core.common import stable_id
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_query_windows import QueryWindow, TargetWindow, WindowPolicy, plan_query_windows, project_regional_paf
from lgz_core.q0_sources import Interval, merged_intervals, subtract_intervals

STATIC_SHA = 'b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438'
RESIDUAL_SHA = '03b79fc96cc80ccfa8a6560be2141efd4126afd73d21ad1021c944508a04d171'
MIB = 1024**2


def bound_bytes(path, sha, limit):
    with path.open('rb') as f:
        data=f.read(limit+1)
    if len(data)>limit or hashlib.sha256(data).hexdigest()!=sha:
        raise ValueError(f'unbounded or changed diagnostic input: {path}')
    return data


def length(rows):
    return sum(i.length for i in rows)


def covered_bases(cores, covered):
    return sum(core.length-length(subtract_intervals(core,covered)) for core in cores) if covered else 0


def qualified_pairs(hit, datasets):
    if (datasets[hit.query_name]==datasets[hit.target_name]
            or hit.matches/hit.block_length<.95 or sum(n for n,op in hit.cigar if op in 'M=')<100):
        return
    for block in hit.aligned_blocks():
        if block.operation!='X':
            yield block.query,block.target


def clip_pair(query,target,strand,core):
    a=max(query.start,core.start); b=min(query.end,core.end)
    if a>=b:
        return None
    t=target.start+(a-query.start if strand=='+' else query.end-b)
    return Interval(a,b),Interval(t,t+b-a)


def query_window(record):
    q=QueryWindow(**{k:tuple(map(tuple,v)) if k=='cores' else v for k,v in record.items() if k!='window_id'})
    if q.window_id!=record['window_id']:
        raise ValueError('cohort query frame changed')
    return q


def load(work,row,lookup,parse_budget):
    marker=within(work,row['raw_receipt']); receipt=json.loads(bound_bytes(marker,row['raw_receipt_sha256'],2*MIB))
    spec=receipt['spec']; ctx=within(work,spec['context']['path']); context=json.loads(bound_bytes(ctx,spec['context']['sha256'],2*MIB))['spec']
    if receipt['status']!='success' or spec['schema']!='lgz_q0_regional_raw_v1' or '-c' not in spec['flags']:
        raise ValueError('replay requires a successful complete CIGAR raw output')
    query=query_window(row['query'])
    targets={r['window_id']:TargetWindow(**{k:v for k,v in r.items() if k!='window_id'}) for r in context['targets']}
    if (context['query']!={k:v for k,v in query.record().items() if k!='cores'}
            or len(targets)!=row['legacy_target_windows'] or any(w.window_id!=k for k,w in targets.items())):
        raise ValueError('original context inventory differs')
    members={w.segment_id for w in [query,*targets.values()]}
    if (dict(context['members'])!={k:lookup[k]['sequence_sha256'] for k in members}
            or any(lookup[w.segment_id]['length']!=w.segment_length for w in [query,*targets.values()])):
        raise ValueError('replay frame must match original whole source bindings')
    items=[x for x in receipt['outputs'] if x['path'].endswith('/result.paf')]
    if len(items)!=1:
        raise ValueError('missing/ambiguous raw PAF')
    item=items[0]; raw=within(work,item['path'])
    if (raw!=marker.parent/'result.paf' or item['sha256']!=row['raw_paf_sha256']
            or type(item['size']) is not int or not 0<=item['size']<=min(parse_budget,16*MIB)):
        raise ValueError('unexpected raw PAF binding or byte budget')
    data=bound_bytes(raw,item['sha256'],item['size'])
    if len(data)!=item['size']:
        raise ValueError('unexpected raw PAF byte count')
    return query,targets,data


def projected(query,targets,data,artifact):
    q={query.window_id:query}
    for line_number,line in enumerate(io.StringIO(data.decode('utf-8'),newline=''),1):
        if not line.strip() or line.startswith('#'):
            continue
        result=project_regional_paf(line,q,targets,artifact=artifact,line_number=line_number)
        if result is not None:
            yield parse_paf_line(result,artifact=artifact+'.regional_projected',line_number=line_number)


def add_reverse(groups,hit,query_pair,target_pair):
    q,t=groups.setdefault((hit.target_name,hit.query_name,hit.strand),([],[]))
    q.append(target_pair); t.append(query_pair)


def locus_loss(groups, seeds):
    missing=0; q_loss=0; t_loss=0
    for key,(q,t) in groups.items():
        oldq=merged_intervals(q); oldt=merged_intervals(t)
        seedq,seedt=seeds.get(key,((),()))
        if not seedq and length(oldq)>=1000:
            missing+=1
        q_loss+=length(oldq)-covered_bases(oldq,seedq)
        t_loss+=length(oldt)-covered_bases(oldt,seedt)
    return {'groups_total':len(groups),'groups_completely_missing_ge_1kb':missing,
            'query_group_bp_not_covered':q_loss,'target_group_bp_not_covered':t_loss}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','cohort','lookup','residual','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); started=time.monotonic(); work=a.workspace.resolve(strict=True); out=a.output.resolve()
    if out.is_relative_to(work):
        raise ValueError('output must be outside the production workspace')
    cohort=json.loads(bound_bytes(a.cohort,STATIC_SHA,16*MIB))['rows']
    lookup=json.loads(bound_bytes(a.lookup,LOOKUP_SHA,32*MIB))
    sources={}; lengths={}; datasets={}
    for key,row in lookup.items():
        ds=row['dataset']; name=row['contig']; n=row['length']
        if key!=stable_id('q0-source-part',[ds,name,0,n,row['sequence_sha256']]) or (ds,name) in sources:
            raise ValueError('not an original whole source inventory')
        sources[ds,name]=key; lengths[key]=n; datasets[key]=ds
    residual=json.loads(bound_bytes(a.residual,RESIDUAL_SHA,64*MIB))
    holes={sources[row['dataset'],row['contig']]:tuple(Interval(*i) for i in row['uncovered']) for row in residual if row['uncovered']}
    windows=plan_query_windows(lengths,holes,policy=WindowPolicy(trigger_query_bases=1,trigger_longest_bases=1,
        core_bases=100_000,context_bases=10_000,minimum_uncovered_bases=100))
    if len(windows)!=61087 or [row['ordinal'] for row in cohort]!=list(range(128)) or any(row['anchor_case']!=(i<64) for i,row in enumerate(cohort)):
        raise ValueError('frozen cohorts or plan differ')
    cover=defaultdict(list); rev={}; measured=set(); nbytes=0; heldout=[]
    for i,row in enumerate(cohort):
        query,targets,raw=load(work,row,lookup,192*MIB-nbytes); nbytes+=len(raw)
        if query.window_id in measured:
            raise ValueError('cohorts need disjoint original query windows')
        if i<64:
            measured.add(query.window_id)
            for hit in projected(query,targets,raw,row['raw_receipt']):
                for q,t in qualified_pairs(hit,datasets):
                    cover[hit.target_name].append(t)
                    add_reverse(rev,hit,q,t)
            continue
        if i==64:
            cover={key:merged_intervals(values) for key,values in cover.items()}
            rev={key:tuple(merged_intervals(side) for side in values) for key,values in rev.items()}
        cores=tuple(Interval(*core) for core in query.cores)
        covered=covered_bases(cores,cover.get(query.segment_id,()))
        summary={'ordinal':i,'covered_core_bases':covered,'core_bases':length(cores),
                 'historical_mapper_wall_seconds':row['historical_native_seconds']}
        # Parse all held-out outputs, but retain only evidence where the full
        # geometry-only rule would have suppressed the original task.
        groups={}
        for hit in projected(query,targets,raw,row['raw_receipt']):
            if covered!=length(cores):
                continue
            for q,t in qualified_pairs(hit,datasets):
                for core in cores:
                    pair=clip_pair(q,t,hit.strand,core)
                    if pair:
                        qs,ts=groups.setdefault((hit.query_name,hit.target_name,hit.strand),([],[]))
                        qs.append(pair[0]); ts.append(pair[1])
        if covered==length(cores):
            summary['oriented_cross_locus_loss_if_skipped']=locus_loss(groups,rev)
        heldout.append(summary)
    report={'status':'frozen_geometric_opportunity_NOT_a_skip_gate','host':socket.gethostname(),
            'seed_windows':len(measured),'seed_target_parts':len(cover),'seed_reciprocal_oriented_pairs':len(rev),
            'raw_PAF_bytes_verified':nbytes,'main_workspace_modified':False,'native_mapper_executed':False,
            'frozen_windows':len(windows),'cached_seed_windows_removed_from_opportunity':0,
            'frozen_unseeded_core_bases':0,'frozen_unseeded_backfilled_bases':0,
            'frozen_unseeded_fully_backfilled_windows':0,'frozen_unseeded_partially_backfilled_windows':0,
            'heldout':heldout}
    for w in windows:
        if w.window_id in measured:
            report['cached_seed_windows_removed_from_opportunity']+=1
            continue
        cores=tuple(Interval(*core) for core in w.cores); bases=length(cores)
        n=covered_bases(cores,cover.get(w.segment_id,()))
        report['frozen_unseeded_core_bases']+=bases; report['frozen_unseeded_backfilled_bases']+=n
        report['frozen_unseeded_fully_backfilled_windows']+=int(n==bases)
        report['frozen_unseeded_partially_backfilled_windows']+=int(0<n<bases)
    report['seconds']=time.monotonic()-started
    report['limitations']=['Frozen residual differs from the live plan. First 64 completed windows are not a random sample.',
        'No new negative evidence. Geometry-only cover is not complete orientation, locus, or candidate equivalence.',
        'Held-out locus accounting separates oriented segment pairs and both coordinates, not collinearity or final Q0/Q1 acceptance.']
    with out.open('x') as f:
        json.dump(report,f,indent=2,sort_keys=True); f.write('\n')


if __name__=='__main__':
    main()
