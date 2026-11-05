#!/usr/bin/env python3
"""Maintainer-only initial-reference cost comparison, not a production mapper.

Direct FASTA versus a fresh original-policy MMI plus original-part scheduling.
Both paths keep whole queries, preset/filter/K and index policy. Candidate time
includes building, reading/copying parts, mapping, merge, validation and hashes.
This is NOT complete CGAT workflow time or an OS-cache-cold disk benchmark.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import statistics
import subprocess
import time

import benchmark_ordinary_existing as existing
import benchmark_ordinary_partitions as parts
import ordinary_batch_performance as perf

MODES = ('native-fasta', 'prepared-index')


def index_flags(args):
    return [] if args.control_index_bases is None else ['-I', str(args.control_index_bases)]


def native_layout(log, reference, query, batch_bases):
    """Read membership counts from actual native completion; never invent indices."""
    native = perf.parse_log(log.read_text())
    layout, offset = [], 0
    for number, row in enumerate(native['parts']):
        count = row['target_records']
        records = reference[offset:offset + count]
        if count < 1 or len(records) != count:
            raise ValueError('native index membership exceeds complete reference')
        layout.append({'part_index': number, 'records': records})
        offset += count
    if offset != len(reference):
        raise ValueError('native log omitted reference records')
    parts.check_native_log(log, layout, query, batch_bases)
    return layout


def layout_records(catalog):
    return [{'part_index': p['part_index'], 'records': p['records']} for p in catalog['parts']]


def source_guard(sources, code):
    for source in sources.values():
        if any(existing.identity(Path(source['source']))[key] != source[key]
               for key in ('size', 'mtime_ns', 'ctime_ns', 'inode')):
            raise ValueError('read-only original input identity changed')
    for name, row in code.items():
        if perf.sha256(row['path']) != row['sha256']:
            raise ValueError('frozen experiment source/tool changed: ' + name)


def run_one(mm, mic, sources, root, mode, repeat, args):
    root.mkdir()
    output = root / 'complete.paf'
    reference, query = sources['reference'], sources['query']
    expected = {r['name']: r for r in reference['records']}
    started = time.monotonic()
    preparation = 0.0
    result = {'mode': mode, 'repeat': repeat, 'queries_split': False,
              'extra_threshold_probe_mapping': False, 'automatic_retry': False}
    index = None
    if mode == 'native-fasta':
        command = parts.command(mm, reference['source'], query['source'], output,
                                args.threads, args.batch_bases)
        command[4:4] = index_flags(args)
        native = perf.run(command, root, 'native', args.timeout, args.memory_mib - parts.RESERVE_MIB)
        layout = native_layout(root / 'native.stderr', reference['records'], query['records'], args.batch_bases)
        result.update(mapping=native, mapping_and_merge_wall_seconds=time.monotonic() - started,
                      mid_occ=parts.thresholds(root / 'native.stderr')[0])
    elif mode == 'prepared-index':
        before = time.monotonic()
        index = root / 'target.mmi'
        build = perf.run([mm, '-x', 'asm10', *index_flags(args), '-t', str(args.threads),
                          '-d', str(index), reference['source']], root, 'index', args.timeout,
                         args.memory_mib - parts.RESERVE_MIB)
        catalog = mic.copy_parts(index, root / 'index-parts', expected, reuse_single_part=True)
        perf.write_json(root / 'index-context.json', catalog)
        preparation = time.monotonic() - before
        layout = layout_records(catalog)
        if args.expected_parts is not None and len(layout) != args.expected_parts:
            raise ValueError('unexpected actual index part count; no repartition or retry')
        before = time.monotonic()
        if len(layout) == 1:
            command = parts.command(mm, index, query['source'], output, args.threads, args.batch_bases)
            mapping = perf.run(command, root, 'native', args.timeout, args.memory_mib - parts.RESERVE_MIB)
            parts.check_native_log(root / 'native.stderr', catalog['parts'], query['records'], args.batch_bases)
            mid = parts.thresholds(root / 'native.stderr')[0]
            selected = 'single_original_part_no_duplicate_copy'
        else:
            mapping = parts.map_parts(mm, catalog['parts'], query['source'], root, args, args.parallel_parts)
            parts.merge_parts(catalog['parts'], root, output, query['records'], args.batch_bases)
            mid = mapping['mid_occ']
            selected = 'original_parts_parallel' if mapping['admission']['slots'] > 1 else 'original_parts_serial'
        result.update(index_build=build, index_context=catalog, mapping=mapping, mid_occ=mid,
                      selected_schedule=selected, mapping_and_merge_wall_seconds=time.monotonic() - before)
    else:
        raise ValueError('unknown preprocessing comparison mode')
    before = time.monotonic()
    if args.expected_parts is not None and len(layout) != args.expected_parts:
        raise ValueError('native/reference layout count differs from the explicit control')
    rows = parts.validate_paf(output, query['records'], reference['records'])
    digest = perf.sha256(output)
    if args.expected_paf_sha256 and digest != args.expected_paf_sha256:
        raise ValueError('complete PAF differs from independently established same-policy output')
    if index is not None:
        if perf.sha256(index) != catalog['sha256']:
            raise ValueError('serialized index changed during mapping')
        for part in catalog['parts']:
            if perf.sha256(part['path']) != part['sha256']:
                raise ValueError('serialized original part changed during mapping')
    result.update(preparation_wall_seconds=preparation,
                  output_validation_wall_seconds=time.monotonic() - before,
                  execution_stage_wall_seconds=time.monotonic() - started,
                  actual_index_parts=len(layout), layout=layout, paf_rows=rows,
                  paf_sha256=digest, paf_path=str(output), complete_original_inputs=True)
    perf.write_json(root / 'trial.json', result)
    return result


def summarize(runs):
    summary = {}
    for mode in MODES:
        rows = [r for r in runs if r['mode'] == mode]
        if not rows:
            raise ValueError('both original and candidate completions are required')
        summary[mode] = {'trials': len(rows),
            **{key: statistics.median(r[key] for r in rows) for key in (
                'execution_stage_wall_seconds', 'preparation_wall_seconds',
                'mapping_and_merge_wall_seconds', 'output_validation_wall_seconds')}}
    native = summary['native-fasta']['execution_stage_wall_seconds']
    candidate = summary['prepared-index']['execution_stage_wall_seconds']
    summary.update(speedup_including_preparation_and_audit=native / candidate,
                   wall_reduction_percent=100 * (1 - candidate / native),
                   candidate_faster_in_this_control=candidate < native,
                   not_complete_CGAT_workflow_time=True,
                   not_OS_cache_cold_measurement=True)
    return summary


def execute(args):
    mm = shutil.which(args.minimap2)
    if not mm or subprocess.check_output([mm, '--version'], text=True, timeout=10).strip() != perf.VERSION:
        raise ValueError('explicit pinned minimap2 ' + perf.VERSION + ' required')
    mic, reader = parts.index_reader()
    root = args.out.resolve()
    if shutil.disk_usage(root.parent).free < args.min_free_gib * 1024**3:
        raise ValueError('insufficient experiment free space')
    setup = time.monotonic()
    sources = {'reference': existing.catalog(args.target),
               'query': existing.catalog(args.query, ordinary_query=True)}
    common_seconds = time.monotonic() - setup
    for role in ('reference', 'query'):
        expected = getattr(args, 'expected_' + role + '_sha256', None)
        if expected and sources[role]['sha256'] != expected:
            raise ValueError('original ' + role + ' differs from the pinned read-only input')
    paths = {'mapper': mm, 'harness': __file__, 'scheduler': parts.__file__,
             'runner': perf.__file__, 'catalog_reader': existing.__file__, 'index_reader': reader, 'index_binding': mic.wa.__file__}
    code = {name: {'path': str(Path(path).resolve()), 'sha256': perf.sha256(path)} for name, path in paths.items()}
    root.mkdir(parents=True, exist_ok=False)
    report = {'schema_version': 1, 'status': 'running', 'sources': sources, 'code': code, 'runs': [],
              'resource_snapshot': existing.resource_snapshot(),
              'common_input_catalog_and_hash_wall_seconds': common_seconds,
              'common_input_check_is_shared_not_credited_as_candidate_saving': True,
              'timing_scope': 'initial_reference_execution_including_fresh_index_preparation_and_output_audits',
              'threads': args.threads, 'memory_mib': args.memory_mib, 'batch_bases': args.batch_bases,
              'original_default_index_policy': args.control_index_bases is None,
              'control_index_bases': args.control_index_bases,
              'production_runtime_modified': False, 'customer_wheat_data': False,
              'sensitivity_flags_changed': False, 'production_admission': False}
    perf.write_json(root / 'benchmark.json', report)
    previous = signal.getsignal(signal.SIGTERM)
    def stop(signum, frame):
        raise InterruptedError('preprocessing experiment cancelled')
    signal.signal(signal.SIGTERM, stop)
    try:
        expected_layout, digest = None, None
        for repeat in range(args.repeats):
            for mode in (MODES if repeat % 2 == 0 else MODES[::-1]):
                source_guard(sources, code)
                result = run_one(mm, mic, sources, root / f'r{repeat:02d}-{mode}', mode, repeat, args)
                if expected_layout is None:
                    expected_layout, digest = result['layout'], result['paf_sha256']
                if result['layout'] != expected_layout or result['paf_sha256'] != digest:
                    raise ValueError('original layout or exact ordered complete PAF changed')
                source_guard(sources, code)
                result['exact_original_layout_and_ordered_paf_equal'] = True
                report['runs'].append(result)
                perf.write_json(root / 'benchmark.json', report)
                print(json.dumps({k: result[k] for k in ('mode', 'repeat', 'actual_index_parts',
                    'preparation_wall_seconds', 'execution_stage_wall_seconds', 'paf_sha256')}), flush=True)
        for source in sources.values():
            if perf.sha256(source['source']) != source['sha256']:
                raise ValueError('original input content changed after comparison')
        source_guard(sources, code)
        report.update(status='completed_same_layout_initial_reference_stage_comparison',
                      input_content_unchanged=True, exact_ordered_paf_equal=True,
                      summary=summarize(report['runs']))
    except BaseException as error:
        report.update(status='failed_no_recommendation', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        signal.signal(signal.SIGTERM, previous)
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
    p.add_argument('--batch-bases', type=int, default=1_000_000_000)
    p.add_argument('--repeats', type=int, default=2)
    p.add_argument('--expected-parts', type=int)
    p.add_argument('--expected-paf-sha256')
    p.add_argument('--expected-reference-sha256')
    p.add_argument('--expected-query-sha256')
    p.add_argument('--control-index-bases', type=int, help='explicit fixed TEST layout only, never a production recommendation')
    p.add_argument('--min-free-gib', type=int, default=16)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args(argv)
    try:
        if not (1 <= args.threads <= 64 and 1 <= args.parallel_parts <= args.threads
                and 1280 <= args.memory_mib <= 262144 and 1 <= args.timeout <= 7200
                and 0 < args.batch_bases <= 5_000_000_000 and 1 <= args.repeats <= 5
                and args.min_free_gib >= 0 and (args.expected_parts is None or args.expected_parts > 0)
                and (args.control_index_bases is None or args.control_index_bases > 0)):
            raise ValueError('bounded experiment resources required')
        for digest in (args.expected_paf_sha256, args.expected_reference_sha256, args.expected_query_sha256):
            if digest and not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError('expected SHA-256 must be 64 lower-case hex digits')
    except ValueError as error:
        p.error(str(error))
    result = execute(args) if args.execute else {'execute': False, 'files_created': False,
        'mapper_started': False, 'production_admission': False,
        'plan': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
