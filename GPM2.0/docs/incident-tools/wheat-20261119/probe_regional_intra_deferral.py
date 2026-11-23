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
from probe_regional_cap_consumer import observed_maps, qualified_maps, qualify, source
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
    dataset = lookup[q]['dataset']
    intra_rows = sum(len(links) for t, links in groups.items() if lookup[t]['dataset'] == dataset)
    facts = {'core_bp': core_bp, 'interior_core': interior(query), 'intra_projected_rows': intra_rows,
             'distinct_cross_observed_core_maps': None, 'full_cross_qualified_core_maps': None,
             'intra_observed_core_maps': None, 'intra_qualified_core_maps': None,
             'intra_qualified_core_paired_bp': None, 'intra_qualified_whole_paired_bp': None,
             'intra_observed_whole_maps': None}

    def result(reason):
        return {**facts, 'screen_outcome': reason, 'single_full_cross_map_screen': reason == 'qualifies'}

    if not facts['interior_core']:
        return result('terminal_core')
    # Qualification cannot create new maps or paired bases. Reject scopes that
    # already fail uniqueness or coverage on the superset of observed maps,
    # before the expensive fitted-pair checks. Never truncate the links used
    # for qualification: records outside the core can still block a pair.
    cross = []
    for t, links in groups.items():
        if lookup[t]['dataset'] == dataset:
            continue
        for mapping, spans in observed_maps(links, policy).items():
            if (n := covered_bases(cores, spans)):
                cross.append((t, mapping, n))
    facts['distinct_cross_observed_core_maps'] = len(cross)
    if len(cross) != 1 or cross[0][2] != core_bp:
        return result('not_one_complete_observed_cross_map')
    target, mapping, _ = cross[0]
    qualified = qualified_maps(q, target, groups[target], lookup, policy)
    facts['full_cross_qualified_core_maps'] = int(covered_bases(cores, qualified.get(mapping, ())) == core_bp)
    if facts['full_cross_qualified_core_maps'] != 1:
        return result('cross_map_failed_qualification')

    summary = Counter(intra_observed_core_maps=0, intra_qualified_core_maps=0,
                      intra_qualified_core_paired_bp=0, intra_qualified_whole_paired_bp=0,
                      intra_observed_whole_maps=0)
    for t, links in groups.items():
        if lookup[t]['dataset'] != dataset:
            continue
        observed, qualified = qualify(q, t, links, lookup, policy)
        summary['intra_observed_whole_maps'] += len(observed)
        summary['intra_qualified_whole_paired_bp'] += sum(length(spans) for spans in qualified.values())
        summary['intra_observed_core_maps'] += sum(covered_bases(cores, spans) > 0 for spans in observed.values())
        qcov = [covered_bases(cores, spans) for spans in qualified.values()]
        summary['intra_qualified_core_maps'] += sum(n > 0 for n in qcov)
        summary['intra_qualified_core_paired_bp'] += sum(qcov)
    facts.update(summary)
    return result('qualifies')


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
    # Select high-CPU outliers first to keep cohort membership stable, but
    # finish some inexpensive short-interior observations before the long tail.
    selected = sorted(choose(trace), key=lambda pair: pair[0] != 'short_interior')
    for group, row in selected:
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
              'screen_outcomes': dict(Counter(r['screen_outcome'] for r in rows)),
              'screen_windows': len(passed), 'screen_with_qualified_intra_core': sum(r['intra_qualified_core_maps'] > 0 for r in passed),
              'screen_with_any_intra': sum(r['intra_projected_rows'] > 0 for r in passed),
              'main_workspace_modified': False, 'native_mapper_executed': False,
              'seconds': time.monotonic()-start}
    with out.open('x') as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write('\n')


if __name__ == '__main__':
    main()
