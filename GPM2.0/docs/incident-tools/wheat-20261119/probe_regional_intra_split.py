"""Isolated test: run unmodified cross-assembly scope and cap only intra scope.

Both groups use true guarded native mapping. A split/uncapped control separates
changed target context from the DP cap. Existing PAFs anchor the full-scope
control. This is a pair-qualification pilot, not full-path acceptance.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from benchmark_regional_mapper_dispatch import GIB, LOOKUP_SHA, digest, read_json, within
from probe_regional_dp_budget import load_case, observed_timing
from probe_regional_dp_cap_ladder import QUALITY_SHA
import probe_regional_cap_consumer as consumer
from probe_regional_cap_consumer import compare, projected_links
from lgz_core.q0_alignments import read_paf
from lgz_core import q0_regional_mapping

# Two different archived slow source parts, including a weak-density negative.
ORDINALS = (72, 77)
GUARD = 'b87e4a3f604127319789cc27503fa145acc4a1397549ae5b821eb94ba3002780'
INDEXED_GATE = '1578e60a68ed9d86356702245a89031fc9fb8b58f3622911747d5a93e5de21db'
BASE = ['-D','-P','--dual=yes','--no-long-join']


def split_fasta(source, intra, cross, membership, lengths):
    """Partition only whole, existing window records; no rewriting sequence."""
    count = 0
    key = None
    seen = set()
    with source.open('rb') as inf, intra.open('xb') as iout, cross.open('xb') as cout:
        outs = {True:iout, False:cout}
        for line in inf:
            if line.startswith(b'>'):
                if key is not None and count != lengths[key]:
                    raise ValueError('original target length mismatch')
                key = line[1:].rstrip(b'\r\n').decode('ascii')
                if key in seen or key not in membership:
                    raise ValueError('duplicate or unexpected input window')
                seen.add(key); count = 0
            else:
                if key is None:raise ValueError('sequence before target identifier')
                count += len(line.rstrip(b'\r\n'))
            outs[membership[key]].write(line)
        if key is None or count != lengths[key] or seen != set(membership) or set(membership.values()) != {True,False}:
            raise ValueError('incomplete mixed target inventory')


def build_command(original, tool, target, query, mode):
    prefix = [tool,'-c','-x','asm10',*BASE]
    if original[:-2] not in ([*prefix,'-t','2'],[*prefix,'-m','2000','-t','2']):
        raise ValueError('unexpected original guarded precision profile')
    if mode not in ('mixed','cross','intra','intra_cap'):
        raise ValueError('unapproved split profile')
    return [*original[:-2],*(['--cap-sw-mem','30m'] if mode=='intra_cap' else []),str(target),str(query)]


def combine(intra, cross):
    if intra.keys() & cross.keys():raise ValueError('split output crossed its target scope')
    return {**intra,**cross}


def run_case(root, case, lookup, guard, reverse):
    out = root/str(case['ordinal']); out.mkdir()
    lengths = case['lengths']; query = case['query']; original = case['paths']['target.fa']
    query_path = case['paths']['query.fa']; input_sha = [digest(p) for p in (original,query_path)]
    membership={key:dataset==case['qd'] for key,dataset in case['td'].items()}
    intra=out/'intra.fa';cross=out/'cross.fa'; start=time.monotonic()
    split_fasta(original,intra,cross,membership,lengths)
    setup_s=time.monotonic()-start
    paths={'mixed':original,'cross':cross,'intra':intra,'intra_cap':intra}
    inputs={p:digest(p) for p in (intra,cross)}; results={}; links={}
    order=('cross','intra_cap','intra','mixed') if reverse else ('mixed','cross','intra_cap','intra')
    for mode in order:
        argv=build_command(case['argv'],case['tool']['resolved'],paths[mode],query_path,mode)
        if mode=='mixed': target_lengths=lengths
        else:target_lengths={k:v for k,v in lengths.items() if membership[k] == mode.startswith('intra')}
        paf=out/(mode+'.paf'); err=out/(mode+'.stderr'); t=time.monotonic()
        with paf.open('xb') as stdout,err.open('xb') as stderr:
            subprocess.run([sys.executable,str(guard),'--address-space-bytes',str(4*GIB),'--',*argv],
                           cwd=out,stdout=stdout,stderr=stderr,check=True)
        wall=time.monotonic()-t
        sha=digest(paf)
        if mode=='mixed' and sha!=case['raw_sha']:
            raise ValueError('mixed same-node native output differs from archived original')
        n=sum(1 for _ in read_paf(paf,query_lengths={query.window_id:query.length},target_lengths=target_lengths))
        links[mode]=projected_links(paf,case,lookup,f'diagnostic/{case["ordinal"]}/{mode}')
        if mode!='mixed' and any((lookup[k]['dataset']==case['qd'])!=mode.startswith('intra') for k in links[mode]):
            raise ValueError('projected source pair escaped its native scope')
        results[mode]={'subprocess_seconds':wall,'native':observed_timing(err),'paf_sha256':sha,'raw_records':n,'argv':argv}
        print(json.dumps({'case':case['ordinal'],'mode':mode,'seconds':wall,'raw_records':n,'sha256':sha}),flush=True)
    if [digest(p) for p in (original,query_path)]!=input_sha or any(digest(p)!=sha for p,sha in inputs.items()):
        raise ValueError('input changed during bounded native trial')
    exact_split=combine(links['intra'],links['cross']); hybrid=combine(links['intra_cap'],links['cross'])
    geometric={name:compare(query.segment_id,links['mixed'],variant,lookup)
               for name,variant in [('split_exact',exact_split),('split_intra_cap',hybrid)]}
    geometric['intra_cap_vs_split_exact']=compare(query.segment_id,exact_split,hybrid,lookup)
    hybrid_wall=setup_s+sum(results[name]['subprocess_seconds'] for name in ('cross','intra_cap'))
    return {'ordinal':case['ordinal'],'query_part':query.segment_id,'split_preparation_seconds':setup_s,
            'split_exact_input_size':{k:paths[k].stat().st_size for k in ('cross','intra')},'original_size':case['bytes'],
            'run_order':order,'modes':results,'pair_gate':geometric,
            'mixed_seconds':results['mixed']['subprocess_seconds'],'hybrid_seconds_including_split':hybrid_wall,
            'source_paf_sha256':case['raw_sha']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','heldout','quality','lookup','indexed-gate','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();w=a.workspace.resolve(strict=True);archive=a.heldout.resolve(strict=True);out=a.output.resolve()
    if any(out.is_relative_to(r) or r.is_relative_to(out) for r in (w,archive)):
        raise ValueError('diagnostic not isolated')
    if digest(a.lookup)!=LOOKUP_SHA or digest(a.quality)!=QUALITY_SHA:
        raise ValueError('frozen cohort inputs differ')
    if digest(a.indexed_gate)!=INDEXED_GATE:
        raise ValueError('qualification gate differs from the approved replay source')
    name='lgz_core.q0_paths_split_probe'
    spec=importlib.util.spec_from_file_location(name,a.indexed_gate.resolve(strict=True))
    module=importlib.util.module_from_spec(spec); sys.modules[name]=module
    spec.loader.exec_module(module)
    consumer.qualify_pair_blocks=module.qualify_pair_blocks
    guard=Path(q0_regional_mapping.__file__).with_name('q0_mapper_guard.py')
    if digest(guard)!=GUARD or len(os.sched_getaffinity(0))<6:
        raise ValueError('unexpected guard or compute allocation')
    lookup=read_json(a.lookup); rows=read_json(a.quality)['rows'];cases=[]
    for n in ORDINALS:
        row=rows[n]
        if row['ordinal']!=n or row['anchor_case']:
            raise ValueError('changed case strata')
        cases.append(load_case(w,archive,row,n,lookup))
    if len({c['query'].segment_id for c in cases})!=len(cases) or sum(c['bytes'] for c in cases)>128*1024**2:
        raise ValueError('bounded pilot requires separate source parts and at most 128MiB archived inputs')
    out.mkdir(exist_ok=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(run_case,out,c,lookup,guard,bool(i)) for i,c in enumerate(cases)]
        finished=[f.result() for f in jobs]
    report={'status':'two_tail_target_split_pair_gate_pilot_NOT_production_acceptance','node':socket.gethostname(),
            'results':finished,'new_native_job_limit_per_case':4,'address_space_bytes':4*GIB,
            'scope':'preexisting -c profile frozen; same-node mixed timing; no chaining rerun or full Q0/Q1 path replay',
            'main_workspace_modified':False}
    with (out/'report.json').open('x') as handle:json.dump(report,handle,indent=2);handle.write('\n')
    print(json.dumps({'status':report['status'],'cases':[{k:x[k] for k in ('ordinal','mixed_seconds','hybrid_seconds_including_split','pair_gate')} for x in finished]}),flush=True)


if __name__=='__main__':main()
