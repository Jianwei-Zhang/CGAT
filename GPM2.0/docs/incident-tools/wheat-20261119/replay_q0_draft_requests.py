"""Blinded, fixed-graph screening of draft-first Q0 requests. Never invokes a mapper.

The decision function receives only the visible arm and planned input windows. The
replay harness owns archived hits and the full comparator; the first arm has no
supplementary hits (including native). Counts are not a cold deployment benchmark.
"""
import argparse
from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from lgz_core import q0_admission as admission, q0_preparation as prep
from lgz_core.q0_frontier_scope import (UnsearchedWindows, decision_frontier,
                                        selected_proof_frontier, window_touches_frontier)
from lgz_core.q0_sources import Interval, Q0EvidenceError, merged_intervals, subtract_intervals
from probe_q0_decision_frontier import compare, projected_task, subset_input
from replay_q0_reverse_parents import Ranges, alternatives, has_unsearched_context, load_panel


def cut_questions(draft, selection):
    """Ask about the actual cuts and positive proofs, not 100 kb on every shoulder."""
    cuts = decision_frontier(selection, flank_bp=1)
    if cuts is None:
        return None
    spans = defaultdict(list)
    for group in (cuts, selected_proof_frontier(draft, selection.admission, selection.paths)):
        for source, rows in group.items():
            spans[source].extend(rows)
    # Rank ties are real alternatives, not negative evidence. Include the ends
    # of slices on either side of a disagreement, independent of orientation.
    for search in selection.paths.values():
        if search.path is None:
            continue
        def geometry(path):
            return {(s.source, s.interval, s.orientation) for s in path.slices}
        best = geometry(search.path)
        for alt in search.alternatives:
            if alt.score != search.path.score:
                continue
            for source, region, _ in best ^ geometry(alt):
                spans[source].extend((Interval(region.start, region.start+1), Interval(region.end-1, region.end)))
    return {k: merged_intervals(v) for k, v in spans.items()}


def pick(windows, parts, demand):
    if demand is None:
        return set(windows)
    return {key for key, (q, ts) in windows.items() if window_touches_frontier(q, ts, parts, demand)}


def challenge_unlocalized(windows, parts, placements):
    """Seek missing placements on either side of an actual possible query/target pair.

    Window coordinates are part-relative. An unplaced subinterval cannot become
    rooted just by co-occurring with a placed target of another target in a batch.
    Revisiting after a discovery allows a newly rooted part to become the next anchor.
    This geometric test selects work, not positive evidence or proof of absence.
    """
    covered = defaultdict(list)
    for placement in placements:
        part = parts[placement.segment_id]
        if part.source != placement.source or not part.interval.contains(placement.interval):
            raise Q0EvidenceError('draft placement escapes its bound source part')
        covered[part.segment_id].append(Interval(placement.interval.start-part.interval.start,
                                                 placement.interval.end-part.interval.start))
    masks = {key: (Ranges(rows), Ranges(subtract_intervals(Interval(0, parts[key].interval.length), rows)))
             for key, rows in covered.items()}
    def flags(w):
        part = parts[w.segment_id]
        if w.segment_length != part.interval.length or w.end > w.segment_length:
            raise Q0EvidenceError('query or target frame differs from bound source part')
        span = Interval(w.start, w.end)
        if w.segment_id not in masks:
            return False, True
        placed, unknown = masks[w.segment_id]
        return placed.touches(span), unknown.touches(span)
    wanted = set()
    for key, (q, ts) in windows.items():
        q_anchor, q_unknown = flags(q)
        for t in ts:
            t_anchor, t_unknown = flags(t)
            if (q_anchor and t_unknown) or (q_unknown and t_anchor):
                wanted.add(key)
                break
    return wanted


def with_omissions(arm, windows, kept):
    omitted = UnsearchedWindows()
    for key, (q, ts) in windows.items():
        if key not in kept:
            omitted.observe(q, ts, arm.parts)
    return replace(arm, catalog={'supplement_scope': {'unsearched_part_intervals': omitted.record()}})


def decide(base, windows, native, reveal, maximum_requests=3, *, localization=True):
    """reveal() is called only *after* committing the next query set; never sees the full answer."""
    if base.catalog or base.ready_manifest_identity or maximum_requests < 1:
        raise ValueError('unblinded base or invalid repair budget')
    arm, kept, history, have_native = base, set(), [], False
    for round_id in range(maximum_requests+1):
        selection = admission.select_q0_paths(arm)
        demand = cut_questions(arm, selection)
        geometry = pick(windows, arm.parts, demand)
        extra = (challenge_unlocalized(windows, arm.parts, selection.admission.placements)
                 if localization and demand is not None else set())
        fresh = (geometry | extra) - kept
        fallback = None
        if demand is None:
            fallback = 'no_draft_path'
        elif not fresh and (have_native or not native):
            checked = with_omissions(arm, windows, kept)
            if not has_unsearched_context(checked, selection):
                return checked, kept, history, None
            fallback = 'unresolved_competition'
        elif round_id == maximum_requests:
            fallback = 'request_budget_exhausted'
        if fallback:
            fresh = set(windows) - kept
        # Freeze the identities before allowing access to newly requested rows.
        kept = kept | fresh
        history.append({'round': round_id, 'visible_regional_before': len(kept)-len(fresh),
                        'visible_native_before': len(native) if have_native else 0,
                        'requested_regional': len(fresh), 'localization_only': len((extra - geometry) & fresh),
                        'demand_sources': len(demand or {}),
                        'request_digest': sha256(json.dumps(sorted(fresh)).encode()).hexdigest()})
        arm = reveal(frozenset(kept) | native)
        have_native = True
        if fallback or len(kept) == len(windows):
            return with_omissions(arm, windows, kept), kept, history, fallback
    raise AssertionError('unreachable')


def run(root, panel, manifest_sha, *, localization=True):
    manifest = root / prep.MANIFEST
    if sha256(manifest.read_bytes()).hexdigest() != manifest_sha:
        raise ValueError('full archive is not bound to this control')
    ready = prep.load_verified_evidence(root)
    data = load_panel(root, panel, ready)
    outputs = {r['path']: r for r in ready['outputs']}
    windows, native, raw = {}, set(), {}
    for task in data.catalog['supplementary_alignments']:
        key = task['paf']
        if key in windows or key in native:
            raise ValueError('duplicate projected task')
        if task['kind'] != 'regional_discovery':
            native.add(key)
            continue
        rel = task['receipt']
        if prep.identity(root, rel) != outputs[rel]:
            raise ValueError('unbound projection receipt')
        spec = prep.json_file(prep.artifact_path(root, rel))['spec']
        raw[key] = projected_task(task, spec, data.parts, {})['raw']
        windows[key] = SimpleNamespace(**spec['query']), tuple(SimpleNamespace(**t) for t in spec['targets'])
    arm, kept, history, fallback = decide(subset_input(data, set()), windows, native,
                                          lambda ids: subset_input(data, ids), localization=localization)
    # No comparison with the full path, its supporting rows, or its competitors until here.
    chosen = admission.construct_q0(arm)  # real publication omission guard, even after fallback
    full = admission.construct_q0(data)
    floor = pick(windows, data.parts, selected_proof_frontier(data, full.admission, full.paths))
    a, b = alternatives(full), alternatives(chosen)
    if prep.load_verified_evidence(root) != ready or sha256(manifest.read_bytes()).hexdigest() != manifest_sha:
        raise ValueError('source changed during replay')
    return {'schema': 'q0_blind_draft_request_v2', 'localization_challenges': localization, 'panel': panel['panel'], 'ready': data.ready_manifest_identity,
            'regional': len(windows), 'retained': len(kept), 'raw_full': len(set(raw.values())),
            'raw_retained': len({raw[k] for k in kept}), 'native_retained': len(native), 'rounds': history,
            'fallback': fallback, 'guard': 'passed', 'new_mapper_executions': 0, 'fixed_task_graph': True,
            'posthoc_windows_intersecting_full_proof_axes': len(floor), 'comparison': compare(full, chosen),
            'alternative_geometry': {c: {'lost': len(a[c]-b[c]), 'new': len(b[c]-a[c])} for c in a}}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path); p.add_argument('panel', type=Path); p.add_argument('out', type=Path)
    p.add_argument('--panel-sha', required=True); p.add_argument('--manifest-sha', required=True)
    p.add_argument('--cuts-only', action='store_true', help='diagnostic negative control, not a Server option')
    args = p.parse_args(); root = args.root.resolve(strict=True); raw = args.panel.read_bytes()
    if sha256(raw).hexdigest() != args.panel_sha or args.out.resolve().is_relative_to(root) or args.out.exists():
        raise ValueError('panel identity or output invalid')
    result = run(root, json.loads(raw), args.manifest_sha, localization=not args.cuts_only)
    with args.out.open('x') as f:
        json.dump(result, f, sort_keys=True, indent=2); f.write('\n')
