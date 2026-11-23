"""Bounded, read-only candidate-screen quality probe over completed regional PAFs.

This measures retained OLD exact evidence and target volume, not runtime or the
outputs a reduced target set will generate. No approximate PAF becomes exact
negative evidence. Production caches and the running wheat job stay untouched.
"""
import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

VARIANTS = ((1, 2), (2, 4), (4, 8), (8, 16))


def union_length(rows):
    total = 0; low = high = None
    for start, end in sorted(rows):
        if start < 0 or end <= start:
            raise ValueError('invalid coverage interval')
        if low is None: low, high = start, end
        elif start <= high: high = max(high, end)
        else: total += high-low; low, high = start, end
    return total + (high-low if low is not None else 0)


def choose_targets(chains, target_datasets, query_dataset, cores, intra, cross):
    """Keep deterministic per-core/per-dataset shortlists plus strand diversity.

    Chains are validated upstream: (target, qs, qe, matches, span, s1, strand).
    These are APPROXIMATE ranking hints, never scientific coverage themselves.
    """
    if intra < 1 or cross < 1 or not cores:
        raise ValueError('invalid shortlist budget/cores')
    for start, end in cores:
        if start < 0 or end <= start: raise ValueError('invalid core')
    by_core = defaultdict(dict); by_strand = defaultdict(dict)
    for target, qs, qe, matches, span, score, strand in chains:
        if target not in target_datasets or not 0 <= qs < qe or span < 1 or not 0 <= matches <= span or score < 0 or strand not in ('+', '-'):
            raise ValueError('invalid validated chain hint')
        ds = target_datasets[target]
        identity = matches/span
        # Keep two directions represented even when one has a stronger repeat.
        rank = ((qe-qs)*identity, score, matches, qe-qs)
        strand_rows = by_strand[(ds, strand)]
        strand_rows[target] = max(strand_rows.get(target, rank), rank)
        for i, (low, high) in enumerate(cores):
            overlap = max(0, min(qe, high)-max(qs, low))
            if overlap:
                rank = (overlap*identity, score, matches, qe-qs)
                rows = by_core[(ds, i)]
                rows[target] = max(rows.get(target, rank), rank)
    selected = set()
    for (ds, _), rows in sorted(by_core.items()):
        budget = intra if ds == query_dataset else cross
        selected.update(sorted(rows, key=lambda k: (tuple(-x for x in rows[k]), k))[:budget])
    for rows in by_strand.values():
        selected.add(min(rows, key=lambda k: (tuple(-x for x in rows[k]), k)))
    return selected


def coverage_summary(by_target, target_datasets, query_dataset, selected):
    output = {}
    for kind in ('intra', 'cross'):
        rows = [interval for key, values in by_target.items()
                if key in selected and ('intra' if target_datasets[key] == query_dataset else 'cross') == kind
                for interval in values]
        output[kind] = union_length(rows)
    return output


def choose_cohort(trace, lookup, anchors, maximum):
    raw = {r['raw_receipt']: r for r in trace['raw_markers']}
    projects = {r['raw']: r for r in trace['new_projects'] if r['raw'] in raw}
    if len(projects) != len(raw): raise ValueError('frozen raw/project join differs')
    if len(anchors) != len(set(anchors)) or not set(anchors) <= projects.keys():
        raise ValueError('anchor cohort changed')
    selected = list(anchors); buckets = defaultdict(list)
    for key, row in projects.items():
        if key in selected: continue
        q = row['query']; core = sum(b-a for a, b in q['cores']); length = q['end']-q['start']; parent = lookup[q['segment_id']]
        strata = (parent['dataset'], parent['length'] >= 1000000, length < 20000,
                  core*5 < length, raw[key]['real_seconds'] >= 30, raw[key]['paf_bytes'] == 0)
        buckets[strata].append(key)
    queues = [deque(sorted(values, key=lambda k: hashlib.sha256(k.encode()).hexdigest()))
              for _, values in sorted(buckets.items())]
    while len(selected) < maximum and any(queues):
        for q in queues:
            if q and len(selected) < maximum: selected.append(q.popleft())
    if len(selected) != maximum: raise ValueError('not enough bounded cases')
    return [projects[key] for key in selected], raw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package-dir', 'trace', 'lookup', 'anchor-report', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--cases', type=int, default=128)
    a = p.parse_args(); started = time.monotonic()
    if not 64 <= a.cases <= 128: raise ValueError('unbounded cohort')
    from benchmark_regional_mapper_dispatch import digest, read_json, within, TRACE_SHA, LOOKUP_SHA
    if digest(a.trace) != TRACE_SHA or digest(a.lookup) != LOOKUP_SHA or digest(a.anchor_report) != '8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901':
        raise ValueError('frozen input changed')
    work = a.workspace.resolve(strict=True); out = a.output.resolve()
    if out.is_relative_to(work) or work.is_relative_to(out): raise ValueError('output overlaps main workspace')
    out.mkdir(exist_ok=False)
    sys.path.insert(0, str(a.package_dir.resolve(strict=True)))
    from lgz_core.q0_query_windows import QueryWindow, TargetWindow
    from lgz_core.q0_regional_mapping import chain_work
    from lgz_core.q0_cigar_policy import CigarWorkPolicy
    from lgz_core.q0_alignments import read_paf
    trace = read_json(a.trace); lookup = read_json(a.lookup); anchor = read_json(a.anchor_report)
    anchors = [r['raw_receipt'] for r in anchor['cases']]
    cohort, raw = choose_cohort(trace, lookup, anchors, a.cases)
    rows = []; paf_bytes = 0
    for ordinal, project in enumerate(cohort):
        receipt_path = within(work, project['raw']); r = read_json(receipt_path, 2*1024**2)
        if digest(receipt_path) != raw[project['raw']]['raw_receipt_sha256'] or r['status'] != 'success': raise ValueError('raw receipt changed')
        context_path = within(work, r['spec']['context']['path'])
        if digest(context_path) != r['spec']['context']['sha256']: raise ValueError('context changed')
        context = read_json(context_path, 2*1024**2); spec = context['spec']
        for key, sha in spec['members']:
            if lookup[key]['sequence_sha256'] != sha: raise ValueError('source member changed')
        query = QueryWindow(**{k: tuple(map(tuple, v)) if k == 'cores' else v for k, v in project['query'].items() if k != 'window_id'})
        targets = [TargetWindow(**{k: v for k, v in t.items() if k != 'window_id'}) for t in spec['targets']]
        if query.window_id != spec['query']['window_id'] or any(t.window_id != row['window_id'] for t, row in zip(targets, spec['targets'])):
            raise ValueError('query/target window identity differs from bound context')
        td = {t.window_id: lookup[t.segment_id]['dataset'] for t in targets}; qd = lookup[query.segment_id]['dataset']
        lengths = {t.window_id: t.length for t in targets}
        raw_id = next(o for o in r['outputs'] if o['path'].endswith('/result.paf')); raw_path = within(work, raw_id['path'])
        paf_bytes += raw_id['size']
        if paf_bytes > 1024**3 or digest(raw_path) != raw_id['sha256']: raise ValueError('raw output changed/unbounded read')
        pre_path = context_path.parent/'chaining/success.json'; chains = None; coarse_sha = None
        if pre_path.exists():
            pr = read_json(pre_path, 2*1024**2)
            if pr['status'] != 'success' or pr['spec']['context'] != r['spec']['context']: raise ValueError('coarse context differs')
            po = next(o for o in pr['outputs'] if o['path'].endswith('/result.paf')); path = within(work, po['path'])
            paf_bytes += po['size']
            if paf_bytes > 1024**3 or digest(path) != po['sha256']: raise ValueError('coarse output changed/unbounded read')
            chain_work(path, query, lengths, CigarWorkPolicy())
            chains = []
            with path.open() as f:
                for line in f:
                    if not line.strip() or line.startswith('#'): continue
                    v = line.rstrip('\n').split('\t')
                    chains.append((v[5], int(v[2]), int(v[3]), int(v[9]), int(v[10]), next(int(t[5:]) for t in v[12:] if t.startswith('s1:i:')), v[4]))
            coarse_sha = digest(pre_path)
        by_target = defaultdict(list)
        for hit in read_paf(raw_path, query_lengths={query.window_id: query.length}, target_lengths=lengths):
            if hit.matches/hit.block_length < 0.95: continue
            blocks = list(hit.aligned_blocks())
            if sum(b.query.length for b in blocks) < 100: continue
            for block in blocks:
                if block.operation == 'X': continue
                start, end = block.query.start+query.start, block.query.end+query.start
                for low, high in query.cores:
                    if max(start, low) < min(end, high): by_target[hit.target_name].append((max(start, low), min(end, high)))
        all_ids = set(td); base_coverage = coverage_summary(by_target, td, qd, all_ids); variants = {}
        for intra, cross in VARIANTS:
            chosen = all_ids if chains is None else choose_targets(chains, td, qd, tuple((lo-query.start, hi-query.start) for lo, hi in query.cores), intra, cross)
            cov = coverage_summary(by_target, td, qd, chosen)
            variants[f'intra{intra}_cross{cross}'] = {'target_windows': len(chosen), 'target_bases': sum(t.length for t in targets if t.window_id in chosen), 'retained_old_high_quality_core_bases': cov,
               'lost_old_high_quality_core_bases': {k: base_coverage[k]-cov[k] for k in cov}, 'selected_targets': sorted(chosen)}
        row = {'ordinal': ordinal, 'raw_receipt': project['raw'], 'raw_receipt_sha256': raw[project['raw']]['raw_receipt_sha256'], 'coarse_receipt_sha256': coarse_sha,
               'anchor_case': project['raw'] in anchors, 'query': query.record(), 'query_dataset': qd, 'source_parent_bases': lookup[query.segment_id]['length'],
               'historical_native_seconds': raw[project['raw']]['real_seconds'], 'raw_paf_sha256': raw_id['sha256'], 'coarse_chains': None if chains is None else len(chains),
               'legacy_target_windows': len(targets), 'legacy_target_bases': sum(t.length for t in targets), 'old_high_quality_core_bases': base_coverage, 'variants': variants}
        rows.append(row)
        print(json.dumps({'phase': 'case', 'ordinal': ordinal, 'query_dataset': qd, 'legacy_targets': len(targets), 'coarse_chains': row['coarse_chains'], 'old_coverage': base_coverage,
              'variant_results': {key: {k: v for k, v in value.items() if k != 'selected_targets'} for key, value in variants.items()}}), flush=True)
    aggregate = {'legacy_target_windows': sum(r['legacy_target_windows'] for r in rows), 'legacy_target_bases': sum(r['legacy_target_bases'] for r in rows),
                 'old_high_quality_core_bases': {k: sum(r['old_high_quality_core_bases'][k] for r in rows) for k in ('intra', 'cross')}, 'variants': {}}
    for intra, cross in VARIANTS:
        name = f'intra{intra}_cross{cross}'
        aggregate['variants'][name] = {'target_windows': sum(r['variants'][name]['target_windows'] for r in rows), 'target_bases': sum(r['variants'][name]['target_bases'] for r in rows),
           'retained_old_high_quality_core_bases': {k: sum(r['variants'][name]['retained_old_high_quality_core_bases'][k] for r in rows) for k in ('intra', 'cross')},
           'windows_losing_old_high_quality_core_bases': {k: sum(r['variants'][name]['lost_old_high_quality_core_bases'][k] > 0 for r in rows) for k in ('intra', 'cross')}}
    report = {'status': 'candidate_shortlist_static_quality_probe_completed', 'hostname': socket.gethostname(), 'cases': len(rows), 'anchor_cases': len(anchors), 'source_DNA_read': False,
      'native_mapper_executed': False, 'main_workspace_modified': False, 'independent_full_raw_and_coarse_PAF_hashes_checked': True,
      'PAF_bytes_read_for_hashing_and_parsing': paf_bytes, 'aggregate': aggregate, 'rows': rows, 'seconds': time.monotonic()-started,
      'limitations': ['Static subset of old exact evidence, NOT the outputs a reduced target-set mapper will generate.', 'Target-base reduction is not runtime speedup.',
          '64 anchor cases are contiguous bounded historical control; remaining cases are stratified within 1189 completed new raws, not the whole pending queue.',
          'Zero coarse candidates are not adopted as exact negatives. No production strategy has been enabled.', 'High-quality core coverage is a proxy, not whole-genome/final-assembly acceptance.']}
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, indent=2), flush=True)


if __name__ == '__main__': main()
