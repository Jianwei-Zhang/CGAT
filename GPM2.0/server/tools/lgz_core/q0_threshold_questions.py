"""Ask for evidence of a missing Q0 decision, not evidence that competitors do not exist.

Draft routing cannot authorize a placement/cut, convert an unknown join to an exact join,
or certify search completeness. It consumes the shared selector's winner, not its report.
"""
from collections import Counter, defaultdict
from dataclasses import replace

from .q0_admission import admit_placements

from .q0_paths import PathPolicy, pair_blocks, reference_consistent
from .q0_sources import Interval, Q0EvidenceError, merged_intervals, subtract_intervals


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


def _supported_unknown_joins(paths, placed, links, policy):
    """Stream observed links only until each selected join has its first positive witness."""
    # A source pair may contain multiple selected intervals or orientations. Close only
    # the ordered placement pair that passed; a different join still needs its own proof.
    lookup = {}
    for row in paths.values():
        path = row.path
        if path is None:
            continue
        for left, join, right in zip(path.slices, path.joins, path.slices[1:]):
            if join.kind == 'reference_unknown':
                lp, rp = placed[left.placement_id], placed[right.placement_id]
                # facing_evidence requires an anchor on BOTH sides. This is an
                # unresolved join, not a positive: keep its shoulder request,
                # but don't keep scanning links for a witness it cannot have.
                if not lp.anchor_intervals or not rp.anchor_intervals:
                    continue
                a, b = lp.source, rp.source
                joins = lookup.get((a, b))
                if joins is None:
                    # Both input directions share the same outstanding questions.
                    lookup[a, b] = lookup[b, a] = joins = {}
                joins[lp.placement_id, rp.placement_id] = (lp, rp)
    positive = set()
    if not lookup:
        return positive
    for link in links:
        a, b = link.query_source, link.target_source
        joins = lookup.get((a, b))
        if joins is None:
            continue
        passed = [ids for ids, (lp, rp) in joins.items() if facing_evidence(lp, rp, (link,), policy)]
        for ids in passed:
            positive.add(ids)
            del joins[ids]
        if not joins:
            del lookup[a, b]
            if a != b:
                del lookup[b, a]
            if not lookup:
                break
    return positive


def questions(data, draft, assignments, *, reach=2000, policy=PathPolicy()):
    minimum = policy.minimum_anchor_bp
    if type(reach) is not int or reach < minimum:
        raise ValueError('question shoulders shorter than the required paired support')
    stats = Counter(); needed = defaultdict(list)
    if draft is None or not any(r.path for r in draft.paths.values()):
        # Fixed reference hits + fixed sources, with the ordinary admission defaults. Pairwise
        # expansion and input adjacency inherit an existing chromosome; they cannot name one.
        # Lack of a selected path alone is NOT evidence that a chromosome has no reference root.
        direct = draft.admission if draft is not None else admit_placements(replace(data, pair_links=(), original_adjacencies=()))
        if not any(p.localization_kind == 'reference' for p in direct.placements):
            return {}, {'no_reference_seed_no_backbone': 1}
        return None, {'rooted_no_path_full_fallback': 1}
    placed = {p.placement_id: p for p in draft.admission.placements}
    required = defaultdict(set)
    sources = {(s.dataset, s.contig): s for s in data.sources}
    for row in assignments:
        c = row['assigned_chr_name']; s = sources.get((row['dataset_name'], row['seq_name']))
        if s is None:
            raise Q0EvidenceError('assignment source not in blind draft input')
        if c in data.reference_lengths:
            required[c].add(s)
    roots = {p.chromosome for p in placed.values() if p.localization_kind == 'reference'}
    # A tail split retains its original reference seed; the new tail inherits another
    # existing seed. Seeing any placements off this lineage would invalidate the bound.
    if not {p.chromosome for p in placed.values()} <= roots:
        raise Q0EvidenceError('admitted chromosome has no reference lineage')
    absent = {c for c in required if c not in draft.paths or draft.paths[c].path is None}
    stats['unbuilt_without_reference_seed'] = len(absent - roots)
    missing = {s for c in absent & roots for s in required[c]}
    strong_on_missing = defaultdict(list)
    positive_joins = _supported_unknown_joins(draft.paths, placed, data.pair_links, policy)
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
            if (lp.placement_id, rp.placement_id) in positive_joins:
                stats['observed_facing_match_leave_gap'] += 1
                continue
            stats['unproven_join'] += 1
            for p, local in ((lp, j.left_end), (rp, j.right_start)):
                lo, hi = max(0, local-reach), min(p.interval.length, local+reach)
                needed[p.source].append(p.source_interval(Interval(lo, hi)))
    # A secondary assignment to an unbuilt chromosome is a possible rival, not an
    # independent reason to redo an already supported placement. Do not exempt the
    # rest of its contig or erase an independent weak-junction request on this axis.
    if missing:
        fixed = {s: merged_intervals(v) for s, v in strong_on_missing.items()}
        for part in data.parts.values():
            if part.source in missing:
                remaining = subtract_intervals(part.interval, fixed.get(part.source, ()))
                stats['missing_chromosome_parts'] += 1
                stats['secondary_assignment_supported_bp_not_requested'] += part.interval.length - sum(i.length for i in remaining)
                needed[part.source].extend(remaining)
    return {s: merged_intervals(v) for s, v in needed.items() if v}, dict(stats)
