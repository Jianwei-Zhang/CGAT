"""Read-only, same-node exact planning comparison; never reads DNA or maps.

A metadata-only sample of the completed residual snapshot is planned in fresh
processes and then in the owner. All window/target coordinates and whole-parent
fallback decisions must match, not just counts. The second (serial) phase may
benefit from warmed OS pages; report this, not an end-to-end wheat multiplier.
"""
import argparse
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import resource
import shutil
import sys
import tempfile
import time

LOOKUP_SHA = '2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'
RESIDUAL_SHA = '03b79fc96cc80ccfa8a6560be2141efd4126afd73d21ad1021c944508a04d171'
INDEX_SHA = '18677df675e1a3c5fe9071d3edcd908215c8a20d2fbba4d5effd39411c0909a3'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(result):
    return json.dumps(result, default=asdict, sort_keys=True, separators=(',', ':')).encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package-dir', 'lookup-dir', 'index-dir', 'residual'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--planners', type=int, default=3)
    p.add_argument('--allocation-memory-mib', type=int, required=True)
    a = p.parse_args()
    if not 1 <= a.planners <= 3 or a.allocation_memory_mib < 49152:
        raise ValueError('benchmark needs a checked >=48GiB allocation and <=3 planners')
    sys.path[:0] = [str(a.package_dir), str(a.workspace/'.prepare_lib/tools')]
    from lgz_core.common import stable_id
    from lgz_core.q0_sources import SourceKey, SourceSegment, Interval
    from lgz_core.q0_reference_index import ReferenceIndex
    from lgz_core.q0_query_windows import WindowPolicy, plan_query_windows
    from lgz_core.q0_regional_execution import RegionalExecutor, ParentRequest, ExecutionBudget, plan_request, GIB, PLANNER_ADDRESS_SPACE, PLAN_RESERVATION, cgroup_memory_limit, allocation_memory_limit
    scheduler_memory = allocation_memory_limit(a.planners+1)
    if scheduler_memory is not None and scheduler_memory != a.allocation_memory_mib*1024**2:
        raise ValueError("current-job scheduler memory differs from calibration request")
    started = time.monotonic()
    lookup_path = a.lookup_dir/'source-part-lookup.json'
    if digest(lookup_path) != LOOKUP_SHA or digest(a.residual) != RESIDUAL_SHA:
        raise ValueError('source metadata/residual snapshot changed')
    inventory = json.loads(lookup_path.read_text()); parts = {}; by_name = {}
    for pid, row in inventory.items():
        key = SourceKey(row['dataset'], row['contig']); n = row['length']; sha = row['sequence_sha256']
        if stable_id('q0-source-part', [key.dataset, key.contig, 0, n, sha]) != pid:
            raise ValueError('not a full original source')
        parts[pid] = SourceSegment(pid, key, Interval(0, n), sha, 0, 'record_start', 'record_end')
        by_name[key] = pid
    refs_table = list(csv.DictReader((a.workspace/'metadata/reference.tsv').read_text().splitlines(), delimiter='\t'))
    refs = {f[0]:int(f[1]) for f in (line.split('\t') for line in (a.workspace/refs_table[0]['fai_relpath']).read_text().splitlines())}
    holes = {by_name[SourceKey(row['dataset'], row['contig'])]:tuple(Interval(*i) for i in row['uncovered'])
             for row in json.loads(a.residual.read_text()) if row['uncovered']}
    lengths = {key:p.interval.length for key, p in parts.items()}
    policy = WindowPolicy(core_bases=100000, context_bases=10000, trigger_query_bases=1, trigger_longest_bases=1)
    groups = {}
    for w in plan_query_windows(lengths, holes, policy=policy) or ():
        groups.setdefault(w.segment_id, []).append(w)
    candidates = []
    for ds in sorted({p.source.dataset for p in parts.values()}):
        ids = sorted((k for k in groups if parts[k].source.dataset == ds), key=lambda k:(-lengths[k], k))
        if ids:
            candidates += ids[:8]+[ids[min(len(ids)-1, int((len(ids)-1)*i/15))] for i in range(16)]
    selected = []; n = 0
    for pid in dict.fromkeys(candidates):
        if n+len(groups[pid]) <= 256:
            selected.append(pid); n += len(groups[pid])
    requests = [ParentRequest('partial', pid, tuple(groups[pid])) for pid in selected]
    print(json.dumps({'phase':'selection', 'parents':len(requests), 'windows':n}), flush=True)
    with tempfile.TemporaryDirectory(prefix='cgat-q0-planner-benchmark-', dir='/tmp') as tmp:
        db = Path(tmp)/'reference.sqlite'; shutil.copyfile(a.index_dir/'reference.sqlite', db)
        if digest(db) != INDEX_SHA:
            raise ValueError('sealed database changed')
        mirrors = Path(tmp)/'pafs'; mirrors.mkdir()
        begin = time.monotonic()
        index = ReferenceIndex.open(db, a.workspace, parts, refs, local_paf_directory=mirrors)
        input_verification_seconds = time.monotonic()-begin
        try:
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
            reserved = peak+16*GIB+a.planners*(PLANNER_ADDRESS_SPACE+2*PLAN_RESERVATION)
            memory = a.allocation_memory_mib*1024**2
            if reserved > memory:
                raise ValueError('metadata planner reservation exceeds checked allocation')
            budget = ExecutionBudget(a.planners, 0, 0, a.planners+1, memory, peak, reserved, 'metadata_only_calibration')
            hashes = []; parallel_windows = 0
            begin = time.monotonic()
            with RegionalExecutor(index, a.planners+1, budget=budget) as pool:
                for request, result in pool.ordered(requests):
                    hashes.append(hashlib.sha256(canonical(result)).hexdigest())
                    parallel_windows += len(result[0])
                    print(json.dumps({'phase':'parallel', 'parent':len(hashes), 'windows':len(result[0])}), flush=True)
            parallel_seconds = time.monotonic()-begin
            serial_hashes = []; serial_windows = 0
            begin = time.monotonic()
            for request in requests:
                result = plan_request(request, index)
                serial_hashes.append(hashlib.sha256(canonical(result)).hexdigest())
                serial_windows += len(result[0])
            serial_seconds = time.monotonic()-begin
            if hashes != serial_hashes:
                raise ValueError('ordered exact plans/fallbacks differ')
            if pool.report['pool_failure'] or pool.report['exact_owner_replans']:
                raise ValueError('resource fallback occurred: not a clean parallel comparison')
            index.verify_inputs()
        finally:
            index.close()
    report = {'status':'exact_plans_equal', 'hostname':__import__('socket').gethostname(),
              'python':sys.version, 'sample_parents':len(requests), 'sample_windows':n,
              'parallel_windows':parallel_windows, 'serial_windows':serial_windows,
              'parallel_seconds_including_snapshot_spawn_shutdown':parallel_seconds,
              'serial_seconds_after_parallel':serial_seconds, 'input_verification_seconds':input_verification_seconds,
              'serial_over_parallel':serial_seconds/parallel_seconds,
              'owner_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
              'child_max_rss_bytes':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024,
              'execution':pool.report, 'cgroup_memory_limit_bytes':cgroup_memory_limit(),
              'scheduler_memory_limit_bytes':scheduler_memory,
              'ordered_result_hashes':hashes, 'seconds':time.monotonic()-started,
              'mapper_executed':False, 'main_workspace_modified':False, 'whole_dataset_acceptance':False,
              'order_note':'parallel first; serial may benefit from warmed OS pages; no source DNA read',
              'inputs':{'lookup':LOOKUP_SHA, 'residual':RESIDUAL_SHA, 'index':INDEX_SHA},
              'code_sha256':{p.name:digest(p) for p in (a.package_dir/'lgz_core').glob('*.py')}}
    Path('summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('code_sha256', 'ordered_result_hashes')}), flush=True)


if __name__ == '__main__':
    main()
