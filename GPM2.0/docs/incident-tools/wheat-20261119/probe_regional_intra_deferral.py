"""Falsify a simple intra-assembly deferral gate on archived exact windows.

Use the real pair-qualification kernel on bound original projected hits; the
cross results are held fixed. A single qualified cross locus covers the whole
interior core in the proposed optimistic screen. This is NOT full admission,
path equivalence, proof that the fast path can recognize this without exact
alignment, or a measurement of saved mapper time.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import socket
import time

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, TRACE_SHA
from lgz_core.q0_paths import PairLink, PathPolicy
from lgz_core.q0_sources import Interval
from probe_regional_cap_consumer import qualify, source
from replay_regional_reciprocal_coverage import MIB, bound_bytes, covered_bases, length, load, projected, query_window

EDGE_BP = 1000
SHORT_BP = 1000
PER_GROUP = 8


def choose(trace, limit=PER_GROUP):
    raw = {r['raw_receipt']: r for r in trace['raw_markers']}
    projects = {r['raw']: r for r in trace['new_projects'] if r['raw'] in raw}
    if (len(raw) != len(trace['raw_markers']) or len(raw) != len(projects)
            or sum(r['raw'] in raw for r in trace['new_projects']) != len(projects)):
        raise ValueError('ambiguous frozen raw/project join')
    candidates = []
    for name, row in raw.items():
        q = query_window(projects[name]['query'])
        candidates.append((q, {**row, 'query': projects[name]['query']}))
    by_cpu = sorted(candidates, key=lambda item: (-item[1]['cpu_seconds'], item[1]['raw_receipt']))
    short = sorted((item for item in candidates if interior(item[0])
                    and sum(b-a for a,b in item[0].cores) <= SHORT_BP),
                   key=lambda item: item[1]['raw_receipt_sha256'])
    other = sorted(candidates, key=lambda item: item[1]['raw_receipt_sha256'])
    used = set()
    for group, rows in (('high_cpu', by_cpu), ('short_interior', short), ('other', other)):
        n = 0
        for q, row in rows:
            if q.segment_id in used:
                continue
            used.add(q.segment_id)
            yield group, row
            n += 1
            if n == limit:
                break


def interior(query):
    return query.cores[0][0] >= EDGE_BP and query.cores[-1][1] <= query.segment_length-EDGE_BP


def score(query, hits, lookup):
    q = query.segment_id
    cores = tuple(Interval(*row) for row in query.cores)
    core_bp = length(cores)
    groups = defaultdict(list)
    policy = PathPolicy()
    for hit in hits:
        t = hit.target_name
        if (hit.query_name != q or hit.query_length != query.segment_length
                or hit.target_length != lookup[t]['length'] or t == q):
            raise ValueError('wrong projected part frame')
        groups[t].append(PairLink(hit, source(q, lookup), source(t, lookup)))
    summary = Counter(core_bp=core_bp, distinct_cross_observed_core_maps=0, full_cross_qualified_core_maps=0,
                      intra_observed_core_maps=0, intra_qualified_core_maps=0,
                      intra_qualified_core_paired_bp=0, intra_qualified_whole_paired_bp=0,
                      intra_observed_whole_maps=0, intra_projected_rows=0)
    for t, links in groups.items():
        observed, qualified = qualify(q, t, links, lookup, policy)
        if lookup[q]['dataset'] != lookup[t]['dataset']:
            summary['distinct_cross_observed_core_maps'] += sum(covered_bases(cores, spans) > 0 for spans in observed.values())
            summary['full_cross_qualified_core_maps'] += sum(covered_bases(cores, spans) == core_bp for spans in qualified.values())
        else:
            summary['intra_projected_rows'] += len(links)
            summary['intra_observed_whole_maps'] += len(observed)
            summary['intra_qualified_whole_paired_bp'] += sum(length(spans) for spans in qualified.values())
            summary['intra_observed_core_maps'] += sum(covered_bases(cores, spans) > 0 for spans in observed.values())
            qcov = [covered_bases(cores, spans) for spans in qualified.values()]
            summary['intra_qualified_core_maps'] += sum(n > 0 for n in qcov)
            summary['intra_qualified_core_paired_bp'] += sum(qcov)
    return {**summary, 'interior_core': interior(query),
            'single_full_cross_map_screen': (interior(query) and summary['full_cross_qualified_core_maps'] == 1
                                             and summary['distinct_cross_observed_core_maps'] == 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('workspace', 'lookup', 'trace', 'output'):
        parser.add_argument('--'+arg, type=Path, required=True)
    a = parser.parse_args()
    work, out = a.workspace.resolve(strict=True), a.output.resolve()
    if out.is_relative_to(work):
        raise ValueError('output must not be in the main workspace')
    trace = json.loads(bound_bytes(a.trace, TRACE_SHA, 4*MIB))
    lookup = json.loads(bound_bytes(a.lookup, LOOKUP_SHA, 32*MIB))
    if len(trace['raw_markers']) != 1189:
        raise ValueError('unexpected frozen cohort')
    rows = []
    total = 0
    start = time.monotonic()
    for group, row in choose(trace):
        query, targets, raw = load(work, row, lookup, 128*MIB-total)
        total += len(raw)
        result = score(query, projected(query, targets, raw, row['raw_receipt']), lookup)
        proof = {'group': group, 'raw_receipt': row['raw_receipt'], 'raw_receipt_sha256': row['raw_receipt_sha256'],
                 'historical_exact_cpu_seconds_whole_window': row['cpu_seconds'], **result}
        rows.append(proof)
        print(json.dumps(proof), flush=True)
    passed = [r for r in rows if r['single_full_cross_map_screen']]
    report = {'status': 'archived_intra_deferral_screen_NOT_admission_or_speed', 'node': socket.gethostname(),
              'verified_paf_bytes': total, 'rows': rows, 'cohort': dict(Counter(r['group'] for r in rows)),
              'screen_windows': len(passed), 'screen_with_qualified_intra_core': sum(r['intra_qualified_core_maps'] > 0 for r in passed),
              'screen_with_any_intra': sum(r['intra_projected_rows'] > 0 for r in passed),
              'main_workspace_modified': False, 'native_mapper_executed': False,
              'seconds': time.monotonic()-start}
    with out.open('x') as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
