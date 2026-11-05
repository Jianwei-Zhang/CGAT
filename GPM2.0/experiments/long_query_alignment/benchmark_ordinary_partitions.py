#!/usr/bin/env python3
"""Opt-in original-MMI-part scheduling experiment, NOT a production mapper.

Compare the full serialized MMI with serial/parallel byte-identical parts. The
first real part emits mid_occ before other parts start: no probe or retry maps.
All queries remain whole and ordered. Every accepted output must be byte-equal.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import time

import benchmark_ordinary_existing as existing
import ordinary_batch_performance as perf

MID_OCC = re.compile(rb"\[M::mm_mapopt_update::[^\]\r\n]+\] mid_occ = ([1-9][0-9]*)\r?\n")
CIGAR = re.compile(r"([0-9]+)([MIDNSHP=X])")
RESERVE_MIB = 1024


def index_reader():
    # In-tree source or explicitly shipped, hash-guarded standalone source.
    path = Path(__file__).resolve().parents[2] / 'server/tools/long_cigar_recovery/minimap_index_context.py'
    if not path.is_file():
        path = Path(__file__).with_name('minimap_index_context.py')
    spec = importlib.util.spec_from_file_location('ordinary_partition_index_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def thresholds(path):
    if path.stat().st_size > 4 * 1024**2:
        raise ValueError('unexpectedly large native log')
    values = [int(n) for n in MID_OCC.findall(path.read_bytes())]
    if any(n > 2147483647 for n in values):
        raise ValueError('invalid inherited mid_occ')
    return values


def admission(threads, memory_mib, parallel_parts, part_count):
    if not 1 <= threads <= 64 or not 1 <= parallel_parts <= threads or part_count < 2:
        raise ValueError('multipart comparison requires >=2 parts and bounded thread shares')
    slots = min(parallel_parts, part_count)
    child_mib = (memory_mib - RESERVE_MIB) // slots
    if child_mib < 256:
        raise ValueError('insufficient experiment memory for all worker address-space caps')
    shares = [threads // slots + (i < threads % slots) for i in range(slots)]
    return {'slots': slots, 'thread_shares': shares, 'worker_address_space_mib': child_mib,
            'reserved_mib': RESERVE_MIB, 'configured_memory_mib': memory_mib,
            'sum_worker_address_space_mib': slots * child_mib}


def command(mm, index, query, output, threads, batch_bases, mid_occ=None):
    extra = [] if mid_occ is None else ['-f', str(mid_occ)]
    return [mm, '-c', '-x', 'asm10', *extra, '-t', str(threads), '-K', str(batch_bases),
            '-o', str(output), str(index), str(query)]


def validate_paf(path, query_records, target_records, *, allow_empty=False):
    q = {r['name']: r['length'] for r in query_records}
    t = {r['name']: r['length'] for r in target_records}
    rows = 0
    with path.open() as stream:
        for raw in stream:
            f = raw.rstrip('\n').split('\t')
            if len(f) < 12:
                raise ValueError('invalid PAF columns')
            ql, qs, qe, tl, ts, te = map(int, [f[1], f[2], f[3], f[6], f[7], f[8]])
            matches, block, mapq = map(int, f[9:12])
            if not (q.get(f[0]) == ql and t.get(f[5]) == tl and
                    0 <= qs < qe <= ql and 0 <= ts < te <= tl and f[4] in ('+', '-') and
                    0 <= matches <= block and 0 <= mapq <= 255):
                raise ValueError('PAF escaped original query/index-part coordinates')
            tags = [x[5:] for x in f[12:] if x.startswith('cg:Z:')]
            if len(tags) != 1:
                raise ValueError('one native CIGAR required')
            ops = CIGAR.findall(tags[0])
            if (''.join(n + op for n, op in ops) != tags[0] or not ops or
                    any(int(n) <= 0 for n, _ in ops) or
                    sum(int(n) for n, op in ops if op in 'MI=X') != qe - qs or
                    sum(int(n) for n, op in ops if op in 'MDN=X') != te - ts):
                raise ValueError('CIGAR consumption differs from native spans')
            rows += 1
    if not rows and not allow_empty:
        raise ValueError('empty aggregate PAF is not a successful comparison')
    return rows


def sampled_rss_kib(pids):
    """Linux process-tree RSS sample; not a kernel-measured group high-water mark."""
    todo, seen, rss = list(pids), set(), 0
    while todo:
        pid = todo.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            status = Path(f'/proc/{pid}/status').read_text()
            match = re.search(r'^VmRSS:\s+(\d+) kB$', status, re.M)
            if match:
                rss += int(match[1])
            todo.extend(map(int, Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return rss


def start_child(cmd, root, stem, timeout, memory_mib):
    stats, stdout, stderr = [root / (stem + ext) for ext in ('.resources', '.stdout', '.stderr')]
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mib * 1024**2,) * 2)
    wrapped = ['/usr/bin/time', '-f', '%e %U %S %M', '-o', str(stats), *cmd]
    with stdout.open('xb') as out, stderr.open('xb') as err:
        child = subprocess.Popen(wrapped, stdout=out, stderr=err, start_new_session=True,
                                 preexec_fn=limits, env={**os.environ, 'LC_ALL': 'C'})
    return {'process': child, 'command': cmd, 'stem': stem, 'started': time.monotonic(),
            'timeout': timeout, 'memory_mib': memory_mib, 'stderr': stderr, 'stats': stats}


def terminate(children):
    # Signal the process group even if /usr/bin/time exited before its mapper.
    for child in children:
        try:
            os.killpg(child['process'].pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    for child in children:
        try:
            child['process'].wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child['process'].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child['process'].wait()


def child_result(child, root):
    code = child['process'].returncode
    result = {'command': child['command'], 'returncode': code,
              'observed_wall_seconds': time.monotonic() - child['started'],
              'worker_address_space_limit_mib': child['memory_mib']}
    perf.write_json(root / (child['stem'] + '.execution.json'), result)
    if code != 0:
        raise ValueError('partition mapper failed; no retry: ' + str(child['stderr']))
    fields = child['stats'].read_text().split()
    if len(fields) != 4:
        raise ValueError('invalid GNU time resource summary')
    wall, user, system, rss = map(float, fields)
    result.update(wall_seconds=wall, cpu_seconds=user + system, peak_rss_kib=int(rss))
    return result


def map_parts(mm, parts, query, root, args, slots):
    """Single-threaded controller: no unsafe threaded preexec or trial mapping."""
    plan = admission(args.threads, args.memory_mib, slots, len(parts))
    children, active, results, events = [], {}, {}, []
    inherited, next_part, peak_sample = None, 0, 0
    started = time.monotonic()
    previous_handler = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise InterruptedError('partition experiment interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    def launch(slot, part):
        nonlocal next_part
        stem = f'part-{part["part_index"]:04d}'
        output = root / (stem + '.paf')
        cmd = command(mm, part['path'], query, output, plan['thread_shares'][slot],
                      args.batch_bases, None if next_part == 0 else inherited)
        child = start_child(cmd, root, stem, args.timeout, plan['worker_address_space_mib'])
        child.update(slot=slot, part_index=part['part_index'], paf=output)
        children.append(child); active[slot] = child
        next_part += 1
        events.append({'event': 'start', 'part_index': child['part_index'],
                       'after_seconds': time.monotonic() - started,
                       'threads': plan['thread_shares'][slot],
                       'mid_occ': None if child['part_index'] == 0 else inherited})
    try:
        launch(0, parts[0])
        while active:
            if inherited is None:
                values = thresholds(children[0]['stderr'])
                if len(values) > 1:
                    raise ValueError('first original part emitted multiple thresholds')
                if values:
                    inherited = values[0]
                    events.append({'event': 'inherit_first_part_mid_occ', 'value': inherited,
                                   'after_seconds': time.monotonic() - started})
            peak_sample = max(peak_sample, sampled_rss_kib(c['process'].pid for c in active.values()))
            for slot, child in list(active.items()):
                if child['process'].poll() is not None:
                    results[child['part_index']] = child_result(child, root)
                    events.append({'event': 'complete', 'part_index': child['part_index'],
                                   'after_seconds': time.monotonic() - started})
                    del active[slot]
                elif time.monotonic() - child['started'] > child['timeout']:
                    raise subprocess.TimeoutExpired(child['command'], child['timeout'])
            if inherited is not None:
                for slot in range(plan['slots']):
                    if slot not in active and next_part < len(parts):
                        launch(slot, parts[next_part])
            elif not active:
                raise ValueError('first part completed without a complete mid_occ log line')
            time.sleep(0.05)
        if next_part != len(parts):
            raise ValueError('not all original index parts completed')
        for c in children:
            if thresholds(c['stderr']) != [inherited]:
                raise ValueError('original part did not use inherited first-part mid_occ')
        elapsed = time.monotonic() - started
        return {'parts': [results[i] for i in range(len(parts))], 'admission': plan,
                'observed_mapping_wall_seconds': elapsed,
                'cpu_seconds': sum(r['cpu_seconds'] for r in results.values()),
                'sampled_process_tree_peak_rss_kib': peak_sample,
                'rss_sample_is_not_kernel_group_peak': True,
                'sum_individual_peak_rss_kib_upper_bound': sum(r['peak_rss_kib'] for r in results.values()),
                'mid_occ': inherited, 'events': events}
    finally:
        terminate([c for c in children if c['part_index'] not in results])
        signal.signal(signal.SIGTERM, previous_handler)
        perf.write_json(root / 'schedule.json', {'admission': plan, 'events': events,
                        'launched_parts': next_part, 'completed_parts': len(results),
                        'observed_mapping_wall_seconds': time.monotonic() - started})


def check_native_log(path, expected_parts, query_records, batch_bases):
    parsed = perf.parse_log(path.read_text())
    counts = [len(b) for b in perf.partition(query_records, batch_bases)]
    if ([p['target_records'] for p in parsed['parts']] != [len(p['records']) for p in expected_parts] or
            any([b['records'] for b in p['batches']] != counts for p in parsed['parts'])):
        raise ValueError('native log lost original target/query partition membership')
    values = thresholds(path)
    if len(values) != len(expected_parts) or len(set(values)) != 1:
        raise ValueError('original multipart threshold inheritance changed')
    return parsed


def merge_parts(parts, root, output, query_records, batch_bases):
    """Restore original index-part order, not worker completion order."""
    with output.open('xb') as dest:
        for part in parts:
            p = root / f'part-{part["part_index"]:04d}.paf'
            validate_paf(p, query_records, part['records'], allow_empty=True)
            check_native_log(p.with_suffix('.stderr'), [part], query_records, batch_bases)
            with p.open('rb') as source:
                shutil.copyfileobj(source, dest, 1024**2)


def execute(args):
    mm = shutil.which(args.minimap2)
    if not mm or subprocess.check_output([mm, '--version'], text=True).strip() != perf.VERSION:
        raise ValueError('pinned minimap2 ' + perf.VERSION + ' required')
    mic, reader_path = index_reader()
    sources = {'reference': existing.catalog(args.target),
               'query': existing.catalog(args.query, ordinary_query=True)}
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = {'status': 'running', 'scope': 'ordinary_original_index_part_scheduling_experiment',
              'production_runtime_modified': False, 'customer_wheat_data': False,
              'resource_snapshot': existing.resource_snapshot(), 'sources': sources, 'runs': [],
              'threads': args.threads, 'memory_mib': args.memory_mib, 'batch_bases': args.batch_bases,
              'harness_sha256': perf.sha256(__file__), 'runner_sha256': perf.sha256(perf.__file__),
              'catalog_reader_sha256': perf.sha256(existing.__file__),
              'index_reader_sha256': perf.sha256(reader_path), 'mapper_sha256': perf.sha256(mm),
              'original_default_index_policy': args.control_index_bases is None,
              'control_index_bases': args.control_index_bases,
              'timing_scope': 'mapping_only; index build/copy/audit separately recorded'}
    perf.write_json(root / 'benchmark.json', report)
    try:
        index = root / 'target.mmi'
        flags = [] if args.control_index_bases is None else ['-I', str(args.control_index_bases)]
        prep = time.monotonic()
        report['index_build'] = perf.run([mm, '-x', 'asm10', *flags, '-t', str(args.threads),
                                         '-d', str(index), sources['reference']['source']],
                                        root, 'index', args.timeout, args.memory_mib - RESERVE_MIB)
        expected = {r['name']: r for r in sources['reference']['records']}
        catalog = mic.copy_parts(index, root / 'index-parts', expected)
        if len(catalog['parts']) < 2:
            raise ValueError('requires a true multipart MMI; no automatic repartition or retry')
        report['index_context'] = catalog
        report['preparation_wall_seconds'] = time.monotonic() - prep
        admission(args.threads, args.memory_mib, args.parallel_parts, len(catalog['parts']))
        reference_digest = None
        for rep in range(args.repeats):
            modes = ['baseline', 'serial-parts', 'parallel-parts']
            if rep % 2:
                modes.reverse()
            for mode in modes:
                runroot = root / f'r{rep:02d}-{mode}'
                runroot.mkdir()
                before = time.monotonic()
                output = runroot / 'complete.paf'
                if mode == 'baseline':
                    result = perf.run(command(mm, index, sources['query']['source'], output,
                        args.threads, args.batch_bases), runroot, 'native', args.timeout,
                        args.memory_mib - RESERVE_MIB)
                    native = check_native_log(runroot / 'native.stderr', catalog['parts'],
                                              sources['query']['records'], args.batch_bases)
                    result.update(observed_mapping_wall_seconds=result['observed_wall_seconds'],
                                  mid_occ=thresholds(runroot / 'native.stderr')[0], native=native)
                else:
                    result = map_parts(mm, catalog['parts'], sources['query']['source'], runroot,
                                       args, 1 if mode == 'serial-parts' else args.parallel_parts)
                    merge_parts(catalog['parts'], runroot, output, sources['query']['records'], args.batch_bases)
                result['mapping_and_merge_wall_seconds'] = time.monotonic() - before
                result['paf_rows'] = validate_paf(output, sources['query']['records'], sources['reference']['records'])
                digest = perf.sha256(output)
                if reference_digest is None:
                    reference_digest = digest
                if digest != reference_digest:
                    raise ValueError('exact ordered PAF differs; scheduling experiment rejected')
                result.update(mode=mode, repeat=rep, paf_sha256=digest, exact_ordered_paf_equal=True)
                report['runs'].append(result)
                perf.write_json(root / 'benchmark.json', report)
                print(json.dumps({'mode': mode, 'repeat': rep,
                      'mapping_wall_seconds': result['observed_mapping_wall_seconds'],
                      'exact_ordered_paf_equal': True}), flush=True)
                for name, path in [('mapper', mm), ('index', index),
                    ('harness', __file__), ('runner', perf.__file__),
                    ('catalog_reader', existing.__file__), ('index_reader', reader_path)]:
                    expected_hash = catalog['sha256'] if name == 'index' else report[name + '_sha256']
                    if perf.sha256(path) != expected_hash:
                        raise ValueError(name + ' content changed during experiment')
                for part in catalog['parts']:
                    if perf.sha256(part['path']) != part['sha256']:
                        raise ValueError('serialized index part changed')
                for source in sources.values():
                    if existing.identity(Path(source['source'])) != {k: source[k] for k in ('size','mtime_ns','ctime_ns','inode')}:
                        raise ValueError('original FASTA metadata changed')
        for source in sources.values():
            if perf.sha256(source['source']) != source['sha256']:
                raise ValueError('original FASTA content changed')
        report.update(status='completed_exact_PAF_scheduling_comparison',
                      input_content_unchanged=True, sensitivity_flags_changed=False,
                      original_serialized_part_bytes_and_order_preserved=True,
                      automatic_retry=False, extra_threshold_probe_mapping=False)
    except BaseException as error:
        report.update(status='failed_no_recommendation', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        perf.write_json(root / 'benchmark.json', report)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('target', 'query', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--minimap2', default='minimap2')
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--parallel-parts', type=int, default=2)
    p.add_argument('--memory-mib', type=int, default=8192)
    p.add_argument('--timeout', type=int, default=1800)
    p.add_argument('--batch-bases', type=int, default=500_000_000)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--control-index-bases', type=int, help='synthetic/scaled controls ONLY; not original default partitioning')
    p.add_argument('--execute', action='store_true')
    a = p.parse_args(argv)
    try:
        admission(a.threads, a.memory_mib, a.parallel_parts, 2)
        if not (1280 <= a.memory_mib <= 262144 and 0 < a.timeout <= 7200 and
                0 < a.batch_bases <= 5_000_000_000 and 1 <= a.repeats <= 5 and
                (a.control_index_bases is None or a.control_index_bases > 0)):
            raise ValueError('bounded resources required')
    except ValueError as error:
        p.error(str(error))
    if a.execute:
        result = execute(a)
    else:
        result = {'execute': False, 'files_created': False, 'mapper_started': False,
                  'plan': {k: str(v) if isinstance(v, Path) else v for k, v in vars(a).items()}}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
