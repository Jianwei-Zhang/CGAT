"""Bounded cross-assembly locus novelty in historical whole-wheat regional jobs. No mapper."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from benchmark_regional_mapper_dispatch import LOOKUP_SHA,TRACE_SHA,within
from lgz_core.common import stable_id
from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_sources import Interval
from measure_wheat_window_witnesses import join_trace,verify_project
from q0_locus_geometry import Ranges,LocusIndex
from replay_regional_reciprocal_coverage import MIB,bound_bytes,load,projected


def source_key(pid,lookup):
    r=lookup[pid]; s=r['dataset'],r['contig']
    if stable_id('q0-source-part',[*s,0,r['length'],r['sequence_sha256']])!=pid:
        raise ValueError('whole-source frames required; no guessing part offsets')
    return s


def base_index(work,freeze,queries,lookup):
    index=LocusIndex(); paths=set(); seen_bytes=0; counts=Counter()
    lengths={(r['dataset'],r['contig']):r['length'] for r in lookup.values()}
    for chrom,meta in freeze.items():
        doc=json.loads(bound_bytes(within(work,meta['path']),meta['sha256'],4*MIB))
        if (doc['unit_id'],doc['status'])!=(f'q0_chr:{chrom}','success'):raise ValueError('invalid base checkpoint')
        inputs={x['path']:x for x in doc['input_payload']['inputs']}; outputs={x['path']:x for x in doc['outputs']}
        rel=f'runs/chr_{chrom}/q0_alignment_inputs.json';ds=json.loads(bound_bytes(within(work,rel),inputs[rel]['sha256'],MIB))
        if ds['chromosome']!=chrom:raise ValueError('wrong descriptor')
        calls=[x for x in ds['alignments'] if x['query_dataset']!=x['target_dataset']]
        if len(calls)!=1:raise ValueError('expected exactly one cross assembly alignment per chromosome')
        x=calls[0]; qd,td=x['query_dataset'],x['target_dataset']; rel=x['paf']; r=outputs[rel]
        if rel in paths or {qd,td}!={'JM19_hifiasm','JM19_flye_ABD'}:raise ValueError('ambiguous base inputs')
        paths.add(rel);seen_bytes+=r['size']
        if seen_bytes>32*MIB:raise ValueError('over budget for initial cross PAFs')
        buf=bound_bytes(within(work,rel),r['sha256'],min(16*MIB,r['size']))
        if len(buf)!=r['size']:raise ValueError('wrong PAF size')
        for n,line in enumerate(buf.splitlines(),1):
            if not line.strip() or line.startswith(b'#'): continue
            # Index only pairs with a query that occurs in the preregistered cohort (either input orientation).
            f=line.split(b'\t',6); a,b=(qd,f[0].decode()),(td,f[5].decode())
            if a not in queries and b not in queries:continue
            h=parse_paf_line(line.decode(),artifact=rel,line_number=n)
            if lengths.get(a)!=h.query_length or lengths.get(b)!=h.target_length:raise ValueError('base/source length mismatch')
            counts['base_rows_for_cohort']+=1
            for v in h.aligned_blocks():
                if v.operation=='X':continue
                if a in queries:index.add(a,b,v.query,v.target,h.strand)
                if b in queries:index.add(b,a,v.target,v.query,h.strand)
    index.seal();return index,{'cross_pafs':len(paths),'cross_paf_bytes':seen_bytes,**counts}


def window(work,raw,p,lookup,index,budget):
    spec=verify_project(work,raw,p)
    q,ts,buf=load(work,{**raw,'query':p['query']},lookup,budget)
    if [t.record() for t in ts.values()]!=spec['targets']:raise ValueError('project targets differ')
    qs=source_key(q.segment_id,lookup); target_sources={t.segment_id:source_key(t.segment_id,lookup) for t in ts.values()}
    cores=Ranges([Interval(a,b) for a,b in q.cores]); high=False
    for h in projected(q,ts,buf,raw['raw_receipt']):
        target=target_sources[h.target_name]
        if (target[0]==qs[0] or 20*h.matches<19*h.block_length or sum(n for n,op in h.cigar if op in 'M=')<100):continue
        high=True
        for v in h.aligned_blocks():
            if v.operation=='X':continue
            reason=index.novel(qs,target,v.query,v.target,h.strand,cores,100)
            if reason is not None:return reason,len(buf)
    return ('no_new_contiguous_100bp_in_core' if high else 'no_threshold_cross_hit'),len(buf)


def run(work,trace,lookup_path,freeze):
    cohort=join_trace(json.loads(bound_bytes(trace,TRACE_SHA,4*MIB))); lookup=json.loads(bound_bytes(lookup_path,LOOKUP_SHA,32*MIB))
    if set(freeze)!={str(i)+s for i in range(1,8) for s in 'ABD'}|{'Un'}:raise ValueError('incomplete chromosome inventory')
    queries={source_key(p['query']['segment_id'],lookup) for _,p in cohort};index,base=base_index(work,freeze,queries,lookup)
    budget=sum(r['paf_bytes'] for r,_ in cohort)
    if len(cohort)!=1189 or budget>256*MIB:raise ValueError('wrong regional cohort')
    counts=Counter(); seconds=Counter(); verdicts=[]
    for i,(r,p) in enumerate(cohort):
        reason,n=window(work,r,p,lookup,index,budget);budget-=n;counts[reason]+=1;seconds[reason]+=r['real_seconds'];verdicts.append([r['raw_receipt_sha256'],reason])
        if (i+1)%100==0: print('VERIFIED',i+1,dict(counts),flush=True)
    if budget:raise ValueError('unfinished cohort')
    return {'schema':'wheat_cross_locus_novelty_v1','base':base,'query_sources':len(queries),'windows':len(cohort),
            'first_witness_categories':dict(counts),'historical_mapper_real_seconds_sum':dict(seconds),
            'verdict_digest':sha256(json.dumps(sorted(verdicts)).encode()).hexdigest(), 'new_mapper_executions':0,
            'scope':'100 continuous paired bases in the queried core outside identical signed cross-source base geometry, including weak prior PAFs; first witness only; not a Q0 necessity test'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('work','trace','lookup','freeze','out'):p.add_argument(n,type=Path)
    p.add_argument('--freeze-sha',required=True);a=p.parse_args();root=a.work.resolve(strict=True);out=a.out.resolve()
    if out.exists() or out.is_relative_to(root):raise ValueError('output overlaps source')
    freeze=json.loads(bound_bytes(a.freeze,a.freeze_sha,64*1024));r=run(root,a.trace,a.lookup,freeze);r['freeze_sha256']=a.freeze_sha
    with out.open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n')
