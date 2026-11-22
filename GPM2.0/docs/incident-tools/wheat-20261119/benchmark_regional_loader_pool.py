"""Compare the verified mapper-only loader switch on a concurrent, exact wheat cohort."""
import argparse
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import time

from benchmark_regional_thread_split import GIB, GUARD_SHA, TOOL_SHA, digest, load_cases, run_phase, stamp, within

WINDOWS = 8
WORKERS = 4
THREADS = 2
CPU_BUDGET = 10
MEMORY_BUDGET_MIB = 32768
LOADER_SHA = '25866e25156c2bf5d7cc90b66ee821c1b7d1485fc64752050092f75c9037c33a'


def exact_child_env(inherited, candidate):
    if not inherited.get('LD_LIBRARY_PATH') or candidate is None:
        raise ValueError('no verified child-only loader change')
    expected = {name:value for name,value in inherited.items() if name != 'LD_LIBRARY_PATH'}
    if candidate != expected:
        raise ValueError('an environment field unrelated to the loader changed')
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace','archive','stage','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args = parser.parse_args()
    work, archive, stage, out = (p.resolve() for p in (args.workspace,args.archive,args.stage,args.output))
    if any(out.is_relative_to(p) or p.is_relative_to(out) for p in (work,archive,stage)):
        raise ValueError('benchmark must remain outside all input workspaces and frozen packages')
    if len(os.sched_getaffinity(0)) < CPU_BUDGET or WORKERS*THREADS >= CPU_BUDGET or WORKERS*4*1024 >= MEMORY_BUDGET_MIB:
        raise ValueError('insufficient single-node CPU/mapper budget')
    package = within(stage,'package/server/tools')
    guard, module = (within(package,'lgz_core/'+name) for name in ('q0_mapper_guard.py','q0_regional_mapping.py'))
    if digest(guard) != GUARD_SHA or digest(module) != LOADER_SHA:
        raise ValueError('loader/guard are not the frozen tested implementation')
    sys.path.insert(0,str(package))
    sys.path.insert(0,str(stage))
    from lgz_core import q0_regional_mapping as mapping
    from probe_q0_loader_allocation import smoke_scope
    if Path(mapping.__file__).resolve(strict=True) != module:
        raise ValueError('import did not load the frozen candidate')
    inherited = dict(os.environ)
    out.mkdir()
    begin = time.monotonic()
    loader = mapping._probe_mapper_loader('minimap2')
    if loader is None or loader.tool_sha256 != TOOL_SHA:
        raise ValueError('active node does not pass the same-loader dependencies check')
    smoke = within(stage,'smoke-v2/smoke.jsonl')
    tool = {'resolved':loader.tool_path,'sha256':loader.tool_sha256}
    child, source = loader.child(tool)
    clean = exact_child_env(inherited,child)
    if source != smoke_scope(smoke):
        raise ValueError('loader dependency/byte identities differ from validated writer smoke')
    loader_time = time.monotonic() - begin
    print(json.dumps({'phase':'loader_verified','seconds':loader_time}),flush=True)
    begin = time.monotonic()
    hashes = {}
    cases, identities, nbytes = load_cases(work,archive,WINDOWS,input_digests=hashes)
    signatures = {p:stamp(p) for p in (guard,module,smoke)}
    if any(s.argv[THREADS-1][0] != loader.tool_path for case in cases for s in case.stages):
        raise ValueError('archive mapper path has drifted')
    print(json.dumps({'phase':'inputs_verified','seconds':time.monotonic()-begin,'windows':len(cases),'input_bytes':nbytes}),flush=True)
    arms = []
    for i, (name, env) in enumerate((('original',inherited),('verified_child',clean),('verified_child',clean),('original',inherited))):
        result = run_phase(out/f'phase-{i}',cases,guard,THREADS,WORKERS,child_env=env)
        if dict(os.environ) != inherited or any(stamp(p) != sig for p,sig in {**identities,**signatures}.items()):
            raise ValueError('environment escaped mapper scope or a frozen artifact changed')
        result['mode'] = name
        with (out/f'phase-{i}.json').open('x') as handle:
            json.dump(result,handle,indent=2,sort_keys=True)
            handle.write('\n')
        print(json.dumps({k:v for k,v in result.items() if k != 'rows'}),flush=True)
        arms.append(result)
    if mapping._probe_mapper_loader('minimap2') != loader or any(digest(p)!=expected for p,expected in hashes.items()):
        raise ValueError('loader or original FASTA bytes changed during the benchmark')
    base = [r['seconds'] for r in arms if r['mode']=='original']
    candidate = [r['seconds'] for r in arms if r['mode']=='verified_child']
    def window_mean(mode):
        return statistics.mean(sum(s['seconds'] for s in rows) for r in arms if r['mode']==mode for _, rows in r['rows'])
    with (out/'report.json').open('x') as handle:
        json.dump({'status':'native_loader_pool_abba_raw_pair_byte_identical','host':socket.gethostname(),
                   'main_workspace_modified':False,'input_bytes':nbytes,'windows':WINDOWS,'measured_workers':WORKERS,
                   'coarse_and_precise_equal_original_stdout':True,'loader_proof':source,'loader_check_seconds':loader_time,
                   'original_seconds':base,'verified_child_seconds':candidate,
                   'pool_wall_seconds_saved_per_completed_window':(statistics.mean(base)-statistics.mean(candidate))/WINDOWS,
                   'mean_window_service_seconds':{mode:window_mean(mode) for mode in ('original','verified_child')},
                   'not_end_to_end':'no large owner state, planning, lock transition, or final projection; does not predict production throughput',
                   'phases':arms},handle,indent=2,sort_keys=True)
        handle.write('\n')


if __name__ == '__main__':
    main()
