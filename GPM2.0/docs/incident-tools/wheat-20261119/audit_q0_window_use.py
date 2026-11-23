"""Measure use of verified regional Q0 evidence, not a prospective window selector."""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from lgz_core import q0_admission as admission, q0_preparation as prep
from lgz_core.q0_frontier_scope import UnsearchedWindows
from lgz_core.q0_sources import Q0EvidenceError
from probe_q0_decision_frontier import compare, projected_task, subset_input
from replay_q0_reverse_parents import alternatives, has_unsearched_context, load_panel


def path_ids(path, placements):
    return ({eid for s in path.slices for eid in placements[s.placement_id].evidence_ids},
            {eid for join in path.joins for eid in join.evidence_ids})


def classify(full, links, windows):
    """Attribute distinct projected tasks (not PAF lines); categories are exclusive."""
    placements = {p.placement_id: p for p in full.admission.placements}
    selected, joins, alts = set(), set(), set()
    for row in full.paths.values():
        if row.path is not None:
            p, j = path_ids(row.path, placements)
            selected.update(p | j)
            joins.update(j)
        for path in row.alternatives:
            p, j = path_ids(path, placements)
            alts.update(p | j)
    report_ids = set(full.decisions['evidence'])
    by_task = defaultdict(set)
    for link in links:
        if link.hit.artifact in windows:
            by_task[link.hit.artifact].add(link.hit.evidence_id)
    counts = Counter()
    selected_tasks = set()
    for task in windows:
        ids = by_task.get(task, set())
        if ids & selected:
            selected_tasks.add(task)
            counts['selected_placement_or_join'] += 1
        elif ids & alts:
            counts['alternative_placement_or_join_only'] += 1
        elif ids & report_ids:
            counts['other_decision_record_only'] += 1
        elif ids:
            counts['projected_hits_not_cited'] += 1
        else:
            counts['no_projected_hits'] += 1
    return selected_tasks, dict(counts), sum(bool(ids & joins) for ids in by_task.values())


def ablate(data, full, kept, windows, native):
    # Diagnostic even when the omission guard rejects this arm. Never publish it.
    arm = subset_input(data, kept | native)
    omitted = UnsearchedWindows()
    for paf, (q, ts) in windows.items():
        if paf not in kept:
            omitted.observe(q, ts, data.parts)
    try:
        built = admission.construct_q0(arm)
    except Q0EvidenceError as exc:
        if str(exc) != 'no chromosome has a trustworthy q0 path':
            raise
        return {'regional_kept': len(kept), 'verdict': 'no_path'}
    guarded = replace(arm, catalog={'supplement_scope': {'unsearched_part_intervals': omitted.record()}})
    guard = 'reject_unsearched_context' if has_unsearched_context(guarded, built) else 'passed'
    a, b = alternatives(full), alternatives(built)
    return {'regional_kept': len(kept), 'guard': guard, 'comparison': compare(full, built),
            'alternative_geometry': {c: {'lost': len(a[c]-b[c]), 'new': len(b[c]-a[c])} for c in a}}


def audit(root, panel, expected_ready):
    ready = prep.load_verified_evidence(root)
    data = load_panel(root, panel, ready)
    if data.ready_manifest_identity != expected_ready:
        raise ValueError('wrong full evidence archive')
    outputs = {r['path']: r for r in ready['outputs']}
    windows, native = {}, set()
    for task in data.catalog['supplementary_alignments']:
        paf = task['paf']
        if paf in native or paf in windows:
            raise ValueError('duplicate task')
        if task['kind'] != 'regional_discovery':
            native.add(paf)
            continue
        rel = task['receipt']
        if prep.identity(root, rel) != outputs[rel]:
            raise ValueError('unbound projection receipt')
        spec = prep.json_file(prep.artifact_path(root, rel))['spec']
        projected_task(task, spec, data.parts, {})
        windows[paf] = SimpleNamespace(**spec['query']), tuple(SimpleNamespace(**t) for t in spec['targets'])
    full = admission.construct_q0(data)
    selected, counts, join_windows = classify(full, data.pair_links, windows)
    result = {'schema': 'q0_archived_window_usage_v1', 'panel': panel['panel'], 'ready': expected_ready,
              'regional_windows': len(windows), 'native_retained': len(native), 'new_mapper_executions': 0,
              'window_roles': counts, 'selected_join_cited_windows': join_windows,
              'native_plus_base_only': ablate(data, full, set(), windows, native),
              'hindsight_direct_only': ablate(data, full, selected, windows, native)}
    if prep.load_verified_evidence(root) != ready:
        raise ValueError('source evidence changed')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path); p.add_argument('panel', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--panel-sha', required=True); p.add_argument('--ready', required=True)
    args = p.parse_args(); root = args.root.resolve(strict=True); raw = args.panel.read_bytes()
    if sha256(raw).hexdigest() != args.panel_sha or args.output.resolve().is_relative_to(root) or args.output.exists():
        raise ValueError('panel binding or isolated output invalid')
    result = audit(root, json.loads(raw), args.ready)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True); f.write('\n')
