"""Isolate recurring target-window dictionary creation on archived raw PAF.

Two ABBA repetitions per case over the same verified original PAF data in
memory (CPU path, not shared-storage or end-to-end timing). Exact projector
and validators are shared. The candidate must return identical rendered lines.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import time

from benchmark_regional_mapper_dispatch import LOOKUP_SHA
from lgz_core.q0_query_windows import project_regional_paf
from replay_regional_reciprocal_coverage import MIB, STATIC_SHA, bound_bytes, load


def before(source, query, targets, artifact):
    for number,line in enumerate(source,1):
        if not line.strip() or line.startswith('#'):
            continue
        value=project_regional_paf(line,{query.window_id:query},{w.window_id:w for w in targets},artifact=artifact,line_number=number)
        if value is not None:
            yield value+'\n'


def output_identity(lines):
    h=hashlib.sha256(); n=0
    for line in lines:
        h.update(line.encode('utf-8')); n+=1
    return (h.hexdigest(),n)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('workspace','cohort','lookup','candidate','output'):
        p.add_argument('--'+n,type=Path,required=True)
    args=p.parse_args(); work=args.workspace.resolve(strict=True); out=args.output.resolve()
    if out.is_relative_to(work):
        raise ValueError('isolated diagnostic only')
    candidate=importlib.util.spec_from_file_location('lgz_core.q0_regional_mapping_candidate',args.candidate)
    module=importlib.util.module_from_spec(candidate); candidate.loader.exec_module(module)
    if module.project_regional_paf is not project_regional_paf:
        raise ValueError('both lanes must use the original validated projector')
    rows=json.loads(bound_bytes(args.cohort,STATIC_SHA,16*MIB))['rows']
    lookup=json.loads(bound_bytes(args.lookup,LOOKUP_SHA,32*MIB))
    ordered=sorted(rows,key=lambda r:(r['legacy_target_windows'],r['ordinal']))
    selected=ordered[58:64]+ordered[-6:]
    output=[]; verified=0
    for row in selected:
        q,targets,data=load(work,row,lookup,96*MIB-verified); verified+=len(data)
        phases=[]; expected=None; raw=data.decode('utf-8'); artifact=row['raw_receipt']
        for mode in ('original','candidate','candidate','original'):
            source=io.StringIO(raw,newline=''); t=time.process_time()
            lines=(before(source,q,targets.values(),artifact) if mode=='original' else
                   module._projected_lines(source,q,targets.values(),artifact=artifact))
            ident=output_identity(lines); elapsed=time.process_time()-t
            if expected is not None and expected!=ident:
                raise ValueError('regional projection output changed')
            expected=ident
            phases.append({'mode':mode,'cpu_seconds':elapsed,'rendered_sha256':ident[0],'rendered_rows':ident[1]})
        result={'ordinal':row['ordinal'],'raw_receipt':row['raw_receipt'],'target_windows':len(targets),
                'raw_bytes':len(data),'phases':phases}
        print(json.dumps(result),flush=True); output.append(result)
    report={'status':'same_projection_bytes_A_B_B_A_not_deployed','node':socket.gethostname(),
        'source_bytes_verified':verified,'candidate_sha256':hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
        'main_workspace_modified':False,'native_mapper_executed':False,'cases':output,
        'limits':['CPU time for Python projection only on authenticated PAF text, no I/O/mapping speedup claim.',
                  'Six middle and six largest archived target inventories, not an estimated whole-wheat distribution.']}
    with out.open('x') as f:
        json.dump(report,f,indent=2,sort_keys=True); f.write('\n')


if __name__=='__main__':
    main()
