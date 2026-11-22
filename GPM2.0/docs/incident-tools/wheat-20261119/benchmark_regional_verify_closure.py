"""Read-only, same-node ABBA of complete regional receipt verification."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import socket
import time
from unittest.mock import patch

from benchmark_regional_mapper_dispatch import TRACE_SHA, digest, read_json, within
from lgz_core import q0_preparation


def load(path, lane):
    spec=importlib.util.spec_from_file_location('lgz_core._regional_verify_'+lane,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','trace','baseline','candidate','output'):
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--projection-cache-hit',action='store_true')
    a=p.parse_args();work=a.workspace.resolve(strict=True);out=a.output.resolve()
    if out.is_relative_to(work) or digest(a.trace)!=TRACE_SHA:
        raise ValueError('outside diagnostic or wrong frozen trace')
    modules={name:load(getattr(a,name),name) for name in ('baseline','candidate')}
    trace=read_json(a.trace,4*1024**2)
    raw={r['raw_receipt']:r for r in trace['raw_markers']}
    project={r['raw']:r for r in trace['new_projects'] if r['raw'] in raw}
    keys=sorted(raw,key=lambda k:(raw[k]['paf_bytes'],k)); center=len(keys)//2
    keys=keys[center:center+4]+keys[-4:]
    if len(keys)!=8 or sum(raw[k]['paf_bytes'] for k in keys)>32*1024**2:
        raise ValueError('unbounded verification sample')
    identity=q0_preparation.identity; cases=[]
    for key in keys:
        if digest(within(work,key))!=raw[key]['raw_receipt_sha256']:
            raise ValueError('historical raw receipt changed')
        marker=project[key]['project']; marked=within(work,marker); receipt=read_json(marked,2*1024**2)
        spec=receipt['spec']; paf=marked.with_name('result.paf').relative_to(work).as_posix()
        if spec['raw_receipt']['path']!=key or spec['raw_receipt']['sha256']!=raw[key]['raw_receipt_sha256']:
            raise ValueError('frozen projected receipt points at a different raw task')
        task={'task_id':marked.parent.name,'kind':'regional_discovery','receipt':marker,'paf':paf,
            'query_ids':[spec['query']['segment_id']],'target_ids':sorted({r['segment_id'] for r in spec['targets']})}
        phases=[]
        for mode in ('baseline','candidate','candidate','baseline'):
            calls=Counter(); bytes_by_file=Counter()
            def measured(root,relative):
                row=identity(root,relative); calls[relative]+=1; bytes_by_file[relative]+=row['size']
                return row
            with patch.object(q0_preparation,'identity',side_effect=measured):
                wall=time.monotonic(); cpu=time.process_time(); module=modules[mode]
                if a.projection_cache_hit:
                    paths={row['path'] for row in receipt['outputs']}
                    if mode=='candidate':
                        checked=module._verified_projection_hit(work,task,spec,paths,members=None)
                    elif module._reuse(work,marker,spec,paths) is not None:
                        checked=module.verify_regional_task(work,task)
                    else:
                        raise ValueError('historical project cache no longer matches its inventory')
                else:
                    checked=module.verify_regional_task(work,task)
                elapsed=time.monotonic()-wall; used=time.process_time()-cpu
            if checked!=receipt:
                raise ValueError('verification accepted a different receipt')
            paf_calls={k:calls[k] for k in calls if k.endswith('/result.paf')}
            if mode=='candidate' and any(n!=1 for n in paf_calls.values()):
                raise ValueError('candidate hashed a PAF twice')
            phases.append({'mode':mode,'wall_seconds':elapsed,'cpu_seconds':used,'identity_calls':sum(calls.values()),
                'identity_bytes':sum(bytes_by_file.values()),'paf_identity_calls':sum(paf_calls.values())})
        cases.append({'receipt':marker,'raw_receipt':key,'raw_paf_bytes':raw[key]['paf_bytes'],'phases':phases})
        print(json.dumps(cases[-1]),flush=True)
    with out.open('x') as f:
        json.dump({'status':'complete_archived_receipt_ABBA_not_deployed','node':socket.gethostname(),
            'main_workspace_modified':False,'native_mapper_executed':False,'all_original_receipts_equal':True,
            'baseline_sha256':digest(a.baseline),'candidate_sha256':digest(a.candidate),'cases':cases,
            'projection_cache_hit_included':a.projection_cache_hit,
            'limits':['Actual complete verifying of eight archived project closures, not mapping/restart or end-to-end timing.',
                      'Identity totals omit the independently scanned geometry and code/guard digests.']},f,indent=2,sort_keys=True); f.write('\n')


if __name__=='__main__':
    main()
