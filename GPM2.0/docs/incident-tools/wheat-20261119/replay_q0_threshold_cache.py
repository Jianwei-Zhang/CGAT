"""Can this threshold runtime reuse the actual old wheat mapper bytes for retained windows?

Replay published whole contexts, not the whole-wheat threshold selection. Never create files
in a production workspace. Skip DNA reload only at _source: an independently frozen source
index binds every complete part; no FASTA reconstruction or new mapper call is permitted.
The production context, coarse, exact, projection and readback implementations are unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

from benchmark_regional_mapper_dispatch import TRACE_SHA, LOOKUP_SHA, digest, read_json, within
from lgz_core import q0_regional_mapping as m
from lgz_core.common import stable_id
from lgz_core.q0_query_windows import QueryWindow, TargetWindow
from lgz_core.q0_sources import Interval, Q0EvidenceError

MIB=1024**2


def contexts(trace):
    raw={r['raw_receipt']:r for r in trace['raw_markers']}
    projs={r['raw']:r for r in trace['new_projects'] if r['raw'] in raw}
    ids=sorted(projs,key=lambda k:(raw[k]['paf_bytes'],k)); mid=len(ids)//2
    selected=ids[mid:mid+4]+ids[-4:]
    if len(set(selected))!=8 or sum(raw[k]['paf_bytes'] for k in selected)>32*MIB:
        raise ValueError('not the bounded eight-window replay')
    return [(raw[k],projs[k]) for k in selected]


def freeze(root,scratch,row):
    name=row['path']; n=row['size']; p=within(root,name); dest=scratch/name
    if (p!=root/name or not name.startswith('grt/evidence/q0_prepare/regional/') or type(n)!=int or not 0<=n<=16*MIB):
        raise ValueError('unexpected archived output')
    with p.open('rb') as f: data=f.read(n+1)
    if len(data)!=n or hashlib.sha256(data).hexdigest()!=row['sha256']: raise ValueError('original output bytes differ')
    if dest.exists():
        if digest(dest)!=row['sha256']: raise ValueError('different blobs for same archived path')
    else:
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('xb') as f:f.write(data)


def replay(work,scratch,trace,lookup):
    t0=monotonic(); rows=[]; seen={}; catalog=SimpleNamespace(parts={}); taken=0
    for raw,proj in contexts(trace):
        rel=proj['project']; marked=within(work,rel); receipt=read_json(marked,2*MIB); spec=receipt['spec']; q=spec['query']; target=spec['targets']
        query=QueryWindow(q['segment_id'],q['segment_length'],q['start'],q['end'],tuple(map(tuple,q['cores'])))
        ts=[TargetWindow(**{k:v for k,v in r.items() if k!='window_id'}) for r in target]
        if (receipt['status']!='success' or not rel.endswith('/'+stable_id('q0-regional-project',spec)+'/success.json')
                or query.window_id!=q['window_id'] or [w.window_id for w in ts]!=[r['window_id'] for r in target]
                or spec['raw_receipt']['path']!=raw['raw_receipt'] or spec['raw_receipt']['sha256']!=raw['raw_receipt_sha256']):
            raise ValueError('frozen task identities disagree')
        leaves=receipt['outputs']; taken+=sum(r['size'] for r in leaves)
        if taken>96*MIB:raise ValueError('replay copy budget exceeded')
        for row in leaves:freeze(work,scratch,row)
        freeze(work,scratch,{'path':rel,'size':marked.stat().st_size,'sha256':digest(marked)})
        ctx=json.loads((scratch/spec['context']['path']).read_bytes())['spec']; dec=json.loads((scratch/spec['decision']['path']).read_bytes())
        for w in (query,*ts):
            key=w.segment_id; row=lookup[key]; n=row['length']; sha=row['sequence_sha256']; ds,name=row['dataset'],row['contig']
            if key!=stable_id('q0-source-part',[ds,name,0,n,sha]) or n!=w.segment_length: raise ValueError('wrong source snapshot')
            catalog.parts[key]=SimpleNamespace(interval=Interval(0,n),sequence_sha256=sha)
        old_task={'task_id':marked.parent.name,'kind':'regional_discovery','receipt':rel,'paf':str(Path(rel).with_name('result.paf')),
                  'query_ids':[query.segment_id],'target_ids':sorted({w.segment_id for w in ts})}
        try: m.verify_regional_task(scratch,old_task,members=catalog.parts)
        except Q0EvidenceError as e:
            if str(e)!='regional projection implementation changed':raise
            direct=False
        else: direct=True
        def bound(member_set,key):
            if member_set is not catalog or key not in catalog.parts: raise ValueError('unbound member')
            seen[key]=True  # _context normally rereads source DNA; bound here to the immutable lookup, not regenerated.
        start=monotonic()
        with (patch.object(m,'_source',bound),patch.object(m,'_sequence',side_effect=AssertionError('would regenerate FASTA')),
              patch.object(m,'_execute',side_effect=AssertionError('would run mapper')) as exe):
            task=m.prepare_regional_mapping(scratch,catalog,query,ts,ctx['tool'],reference_bases=dec['reference_bases'],preset=ctx['preset'])
            new=m.verify_regional_task(scratch,task,members=catalog.parts)
        seconds=monotonic()-start
        if (new['spec']['raw_receipt']!=spec['raw_receipt'] or new['spec']['decision']!=spec['decision'] or
                new['spec']['context']!=spec['context'] or digest(scratch/task['paf'])!=digest(scratch/old_task['paf']) or
                exe.call_count or (task['task_id']==old_task['task_id'])!=direct):raise ValueError('changed mapping, projection bytes or unexpected cache state')
        rows.append({'old_project':old_task['task_id'],'new_project':task['task_id'],'old_projection_admitted':direct,
                     'same_context_decision_and_raw_receipt':True,'identical_projected_paf':True,'mapper_calls':exe.call_count,
                     'raw_bytes':raw['paf_bytes'],'allocator_replay_seconds':seconds,'old_validator':spec['validator_sha256'],
                     'new_validator':new['spec']['validator_sha256'],'projected_sha256':digest(scratch/task['paf'])})
    return {'schema':'q0_threshold_real_wheat_cache_replay_v1','trace_sha256':TRACE_SHA,'lookup_sha256':LOOKUP_SHA,'cases':rows,'distinct_bound_members':len(seen),
            'archived_closure_bytes_with_repeats':taken,'total_wall_s':monotonic()-t0,'node':socket.gethostname(),
            'scope':'Conditional on retaining these historical complete window contexts. Does not establish future demand, eligibility of all live receipts, or whole-run speedup. No whole source DNA reread or mapping allowed.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('workspace','scratch','trace','lookup','output'):p.add_argument(k,type=Path)
    a=p.parse_args();work=a.workspace.resolve(strict=True);scratch=a.scratch.resolve();out=a.output.resolve()
    if (scratch.exists() or scratch.is_relative_to(work) or work.is_relative_to(scratch) or out.is_relative_to(work) or out.is_relative_to(scratch) or out.exists()
            or digest(a.trace)!=TRACE_SHA or digest(a.lookup)!=LOOKUP_SHA):raise ValueError('unsafe diagnostic root or changed frozen input')
    scratch.mkdir(); doc=replay(work,scratch,read_json(a.trace,4*MIB),read_json(a.lookup,32*MIB))
    with out.open('x') as f:json.dump(doc,f,indent=2,sort_keys=True);f.write('\n')
    print('verified',len(doc['cases']),'conditional raw hits; mapper starts',sum(r['mapper_calls'] for r in doc['cases']),flush=True)
