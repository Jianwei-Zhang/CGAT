"""Isolated exact-output comparison of a smaller per-extension DP matrix cap.

Keep all target windows, chain parameters and -P. Compare only the new exact
outputs against already complete historical PAFs. Two bounded same-node exact
controls separate mapper effects from historical node/load differences. This
is a scientific approximation experiment, NOT an exact cache producer.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import socket
import sys
import time

from benchmark_regional_mapper_dispatch import digest, dispatch, GIB, read_json, within
from benchmark_regional_candidate_screen import input_argv, merged, difference_bases
from regional_heldout_case_inputs import select_rows

# Indices in the disjoint 24-case cohort; chosen to cover dominant slow tails,
# short and ordinary workloads, both assemblies, and an empty previous output.
ORDINALS=(0,1,4,5,8,13,14,16,17,20,21,22,23)
# One short query with many alternatives and one large, repetitive query.
CONTROLS=(4,8)
CAP='10m'
TIMING=re.compile(r'Real time: ([\d.]+) sec; CPU: ([\d.]+) sec; Peak RSS: ([\d.]+) GB')


def command_for(argv, target, query, capped):
    res=input_argv(argv,target,query)
    if res[:-2].count('-P')!=1 or any(x.startswith('--cap-sw-mem') for x in res[:-2]):
        raise ValueError('need the archived all-chain command with implicit DP cap')
    return [*res[:-2], '--cap-sw-mem', CAP, *res[-2:]] if capped else res


def paired_quality(path, case, read_paf):
    query=case['query'];qkind=case['qd'];td=case['td'];lengths=case['lengths']
    qs=defaultdict(list);ts=defaultdict(list);buckets=defaultdict(list);rows=0
    for hit in read_paf(path,query_lengths={query.window_id:query.length},target_lengths=lengths):
        rows+=1
        if hit.matches*100<hit.block_length*95 or sum(n for n,op in hit.cigar if op in 'M=')<100:continue
        # Exact target-window identity and orientation, not just a dataset union.
        key=(hit.target_name,hit.strand);kind='intra' if td[hit.target_name]==qkind else 'cross'
        for b in hit.aligned_blocks():
            if b.operation=='X':continue
            for lo,hi in query.cores:
                a=max(lo-query.start,b.query.start); z=min(hi-query.start,b.query.end)
                if a>=z:continue
                t0=b.target.start+(a-b.query.start if hit.strand=='+' else b.query.end-z)
                qs[key].append((a,z));ts[key].append((t0,t0+z-a));buckets[kind].append((a,z))
    return {'rows':rows,'by_kind':{k:merged(buckets[k]) for k in ('intra','cross')},
            'query_by_oriented_target':{k:merged(v) for k,v in qs.items()},
            'target_by_oriented_target':{k:merged(v) for k,v in ts.items()}}


def summarize_quality(old,new,case):
    length=lambda ranges:sum(z-a for a,z in ranges)
    result={}
    for kind in ('intra','cross'):
        x,y=old['by_kind'][kind],new['by_kind'][kind]
        hitkeys=[key for key in old['query_by_oriented_target'] if (case['td'][key[0]]==case['qd'])==(kind=='intra')]
        groups={'old_oriented_targets':len(hitkeys),'missing_oriented_targets':0,'missing_oriented_targets_ge_1kb':0,
                'old_target_group_query_bp':0,'lost_target_group_query_bp':0,
                'old_target_group_target_bp':0,'lost_target_group_target_bp':0}
        for key in hitkeys:
            q,t=old['query_by_oriented_target'][key],old['target_by_oriented_target'][key]
            groups['old_target_group_query_bp']+=length(q);groups['old_target_group_target_bp']+=length(t)
            groups['lost_target_group_query_bp']+=difference_bases(q,new['query_by_oriented_target'].get(key,[]))
            groups['lost_target_group_target_bp']+=difference_bases(t,new['target_by_oriented_target'].get(key,[]))
            if key not in new['query_by_oriented_target']:
                groups['missing_oriented_targets']+=1
                groups['missing_oriented_targets_ge_1kb']+=int(length(q)>=1000)
        result[kind]={'old_core_bp':length(x),'new_core_bp':length(y),'lost_core_bp':difference_bases(x,y),
                      'gained_core_bp':difference_bases(y,x),**groups}
    return result


def observed_timing(path):
    match=TIMING.findall(path.read_text())
    if len(match)!=1:raise ValueError(f'no unique mapper timing in {path}')
    wall,cpu,rss=map(float,match[0]);return {'wall_seconds':wall,'cpu_seconds':cpu,'native_peak_rss_gb':rss}


def load_case(work, inputs, row, ordinal, lookup):
    from lgz_core.q0_query_windows import QueryWindow, TargetWindow
    receipt_path=within(work,row['raw_receipt']);receipt=read_json(receipt_path,2*1024**2)
    if digest(receipt_path)!=row['raw_receipt_sha256'] or receipt['status']!='success':raise ValueError('historical receipt changed')
    bind=receipt['spec']['context'];path=within(work,bind['path'])
    if digest(path)!=bind['sha256']:raise ValueError('historical context changed')
    context=read_json(path,2*1024**2);spec=context['spec'];rel=path.parent.relative_to(work).as_posix()
    inventory={}
    for it in context['inputs']:
        p=within(inputs,it['path']);inventory[p.name]=(p,it)
        if p.stat().st_size!=it['size'] or digest(p)!=it['sha256']:raise ValueError('archived FASTA changed')
    if set(inventory)!={'query.fa','target.fa'}:raise ValueError('unexpected FASTA inventory')
    qrow=row['query'];query=QueryWindow(**{k:tuple(map(tuple,v)) if k=='cores' else v for k,v in qrow.items() if k!='window_id'})
    targets=[TargetWindow(**{k:v for k,v in r.items() if k!='window_id'}) for r in spec['targets']]
    if query.window_id!=spec['query']['window_id'] or [t.window_id for t in targets]!=[r['window_id'] for r in spec['targets']]:
        raise ValueError('historical geometry changed')
    if any(lookup[k]['sequence_sha256']!=sha for k,sha in spec['members']):raise ValueError('historical source digest changed')
    outputs={Path(r['path']).name:r for r in receipt['outputs']}
    command_id=outputs['command.json'];command=within(work,command_id['path']);record=read_json(command)
    if digest(command)!=command_id['sha256'] or record['address_space_bytes']!=4*GIB:raise ValueError('historical guard or command changed')
    tool=spec['tool'];argv=record['argv'];paf=within(work,outputs['result.paf']['path'])
    if (argv[0]!=tool['resolved'] or digest(argv[0])!=tool['sha256'] or
            command.parent!=paf.parent or paf.parent!=receipt_path.parent):raise ValueError('historical native binding differs')
    if digest(paf)!=outputs['result.paf']['sha256'] or outputs['result.paf']['sha256']!=row['raw_paf_sha256']:
        raise ValueError('historical output changed')
    return {'ordinal':ordinal,'query':query,'targets':targets,'raw':paf,'raw_sha':row['raw_paf_sha256'],
            'context':context,'rel':rel,'argv':argv,'tool':tool,'paths':{k:v[0] for k,v in inventory.items()},
            'bytes':sum(it['size'] for p,it in inventory.values()),
            'lengths':{t.window_id:t.length for t in targets},'qd':lookup[query.segment_id]['dataset'],
            'td':{t.window_id:lookup[t.segment_id]['dataset'] for t in targets},
            'historical_timing':observed_timing(paf.parent/'stderr.log')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','inputs','package-dir','anchor-report','quality-report','lookup','output'):
        p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();work=a.workspace.resolve(strict=True);inputs=a.inputs.resolve(strict=True);out=a.output.resolve()
    if any(x.is_relative_to(y) or y.is_relative_to(x) for x,y in [(out,work),(inputs,work),(out,inputs)]):
        raise ValueError('not an isolated diagnostic')
    if digest(a.anchor_report)!='8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901' or digest(a.quality_report)!='b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438':
        raise ValueError('fixed cohorts differ')
    if digest(a.lookup)!='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89':raise ValueError('source lookup differs')
    sys.path.insert(0,str(a.package_dir.resolve(strict=True)))
    from lgz_core.q0_alignments import read_paf
    from lgz_core.q0_regional_execution import allocation_memory_limit
    from lgz_core.q0_regional_mapping import _execute
    if allocation_memory_limit(16)!=160*GIB:raise ValueError('missing same-job 16CPU/160GiB proof')
    out.mkdir(exist_ok=False);lookup=read_json(a.lookup);anchors={r['raw_receipt'] for r in read_json(a.anchor_report)['cases']}
    rows=select_rows(read_json(a.quality_report),anchors)
    cases=[load_case(work,inputs,rows[i],i,lookup) for i in ORDINALS]
    size=sum(c['bytes'] for c in cases)
    if size>GIB:raise ValueError('diagnostic inputs exceed cap')
    print(json.dumps({'phase':'inputs_verified','cases':len(cases),'bytes':size}),flush=True)
    phases=[]
    for capped in (True,False):
        phase='cap-sw-mem-'+CAP if capped else 'historical-default-replay';directory=out/phase;directory.mkdir();begin=time.monotonic()
        def run(unused,c):
            ordinal=c['ordinal'];dest=directory/str(ordinal);dest.mkdir();started=time.monotonic()
            argv=command_for(c['argv'],c['paths']['target.fa'],c['paths']['query.fa'],capped)
            _execute(inputs,dest,c['context'],c['rel'],None,c['query'],c['targets'],argv,c['tool'],4*GIB)
            paf=dest/'result.paf.tmp';sha=digest(paf);timing=observed_timing(dest/'stderr.log')
            if not capped and sha!=c['raw_sha']:raise ValueError('same-node control not equal to original')
            old=paired_quality(c['raw'],c,read_paf);new=paired_quality(paf,c,read_paf)
            if digest(c['raw'])!=c['raw_sha']:raise ValueError('historical output drifted between reads')
            paf.rename(dest/'result.paf')
            result={'ordinal':ordinal,'raw_receipt':str(c['raw'].parent.relative_to(work)/'success.json'),
                    'same_as_historical':sha==c['raw_sha'],'stdout_sha256':sha,'seconds':time.monotonic()-started,
                    'candidate_native_timing':timing,'historical_native_timing':c['historical_timing'],
                    'old_paf_rows':old['rows'],'new_paf_rows':new['rows'],'coverage':summarize_quality(old,new,c)}
            (dest/'comparison.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
            print(json.dumps({'phase':phase,**result}),flush=True)
            return result
        chosen=cases if capped else [c for c in cases if c['ordinal'] in CONTROLS]
        answers,order=dispatch(chosen,run,7,'completed')
        phases.append({'phase':phase,'seconds':time.monotonic()-begin,'results':answers,'completion_order':order})
    report={'status':'bounded_dp_budget_pilot_completed_NOT_production_acceptance','host':socket.gethostname(),
            'archived_original_inputs_verified':True,'input_bytes':size,'exact_additional_flags':['--cap-sw-mem',CAP],
            'all_chain_flags_preserved':True,'coarse_rerun':False,'main_workspace_modified':False,
            'production_strategy_enabled':False,'phases':phases,
            'coverage_scope':'95% PAF identity / >=100 M/= bp; interval differences within original query cores; plus oriented target-window groups; not synteny or final assembly acceptance',
            'timing_scope':'native work isolated; historical episode is not same-node paired control except two explicit exact replays'}
    (out/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')


if __name__=='__main__':main()
