"""Ask for evidence of a missing Q0 decision, not evidence that competitors do not exist.

Experimental draft routing; cannot authorize a placement/cut, convert an unknown join to an
exact join, or certify search completeness. Input must be the ordinary selector's draft.
"""
from collections import Counter, defaultdict

from lgz_core.q0_paths import PathPolicy, pair_blocks, reference_consistent
from lgz_core.q0_sources import Interval, Q0EvidenceError, merged_intervals, subtract_intervals


def ends(span, minimum):
    """Disjoint outer quarters (or halves on short slices); coordinates are source-local."""
    width = min(span.length // 2, max(minimum, span.length // 4))
    if not width:
        return ()
    return Interval(span.start, span.start + width), Interval(span.end - width, span.end)


def supported(region, anchors, minimum):
    return any((clip := i.intersection(region)) is not None and clip.length >= minimum for i in anchors)


def facing_evidence(left, right, links, policy):
    """Evidence on the actual contacting ends. A positive here can keep a gap, never close it."""
    minimum = policy.minimum_anchor_bp
    for link in links:
        h = link.hit
        if h.matches < policy.minimum_pair_identity * h.block_length:
            continue
        for b in pair_blocks(link, left, right):
            if (b.left.length < minimum or not reference_consistent(b, left, right)
                    or left.interval.length - b.left.end > minimum or b.right.start > minimum):
                continue
            # A *corresponding* contiguous paired stretch needs support on both axes.
            for a in left.anchor_intervals:
                cut = b.clip_left(left.local(a))
                if cut and supported(cut.right, (right.local(v) for v in right.anchor_intervals), minimum):
                    return True
    return False


def questions(data, draft, assignments, *, reach=2000, policy=PathPolicy()):
    minimum = policy.minimum_anchor_bp
    if type(reach) is not int or reach < minimum:
        raise ValueError('question shoulders shorter than the required paired support')
    stats = Counter(); needed = defaultdict(list)
    if draft is None or not any(r.path for r in draft.paths.values()):
        return None, {'no_path_full_fallback': 1}
    placed = {p.placement_id: p for p in draft.admission.placements}
    required = defaultdict(set)
    sources = {(s.dataset, s.contig): s for s in data.sources}
    for row in assignments:
        c = row['assigned_chr_name']; s = sources.get((row['dataset_name'], row['seq_name']))
        if s is None:
            raise Q0EvidenceError('assignment source not in blind draft input')
        if c in data.reference_lengths:
            required[c].add(s)
    missing = {s for c, keys in required.items() if c not in draft.paths or draft.paths[c].path is None for s in keys}
    strong_on_missing = defaultdict(list)
    # Index just the pairs under question (not the full duplicated evidence inventory).
    pairs = {tuple(sorted((l.source, r.source))) for row in draft.paths.values() if row.path
             for l, j, r in zip(row.path.slices, row.path.joins, row.path.slices[1:]) if j.kind == 'reference_unknown'}
    by_pair = defaultdict(list)
    if pairs:
        for link in data.pair_links:
            key = tuple(sorted((link.query_source, link.target_source)))
            if key in pairs:
                by_pair[key].append(link)
    for row in draft.paths.values():
        path = row.path
        if path is None:
            continue
        for s in path.slices:
            p = placed[s.placement_id]
            if p.source != s.source or p.orientation != s.orientation or not p.interval.contains(s.interval):
                raise Q0EvidenceError('slice differs from admitted placement')
            sides = ends(s.interval, minimum)
            anchors = merged_intervals(p.anchor_intervals) if p.localization_kind in ('reference', 'pairwise') else ()
            weak = [v for v in sides if not supported(v, anchors, minimum)] if sides else [s.interval]
            if weak:
                needed[s.source].extend(weak); stats['weak_placement'] += 1
            else:
                stats['positive_placement_stop'] += 1
                if s.source in missing:
                    strong_on_missing[s.source].append(s.interval)
        for left, j, right in zip(path.slices, path.joins, path.slices[1:]):
            lp, rp = placed[left.placement_id], placed[right.placement_id]
            if (j.left_id, j.right_id) != (lp.placement_id, rp.placement_id) or not j.evidence_ids:
                raise Q0EvidenceError('unbound selected join')
            if j.kind in ('sequence_overlap', 'input_assembly_gap'):
                # The selector already enforced the paired-CIGAR cut / exact input gap contract.
                stats[j.kind + '_stop'] += 1
                continue
            if j.kind != 'reference_unknown':
                raise Q0EvidenceError('unrecognized join')
            if facing_evidence(lp, rp, by_pair[tuple(sorted((lp.source, rp.source)))], policy):
                stats['observed_facing_match_leave_gap'] += 1
                continue
            stats['unproven_join'] += 1
            for p, local in ((lp, j.left_end), (rp, j.right_start)):
                lo, hi = max(0, local-reach), min(p.interval.length, local+reach)
                needed[p.source].append(p.source_interval(Interval(lo, hi)))
    # A secondary assignment to an unbuilt chromosome is a possible rival, not an
    # independent reason to redo an already supported placement. Do not exempt the
    # rest of its contig or erase an independent weak-junction request on this axis.
    fixed = {s: merged_intervals(v) for s, v in strong_on_missing.items()}
    for part in data.parts.values():
        if part.source in missing:
            remaining = subtract_intervals(part.interval, fixed.get(part.source, ()))
            stats['missing_chromosome_parts'] += 1
            stats['secondary_assignment_supported_bp_not_requested'] += part.interval.length - sum(i.length for i in remaining)
            needed[part.source].extend(remaining)
    return {s: merged_intervals(v) for s, v in needed.items() if v}, dict(stats)
