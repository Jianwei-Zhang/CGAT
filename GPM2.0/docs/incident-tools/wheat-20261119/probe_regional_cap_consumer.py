"""Replay archived DP-cap PAFs through the Q0 pair-qualification gate.

This is a source-pair diagnostic, not a Q0 construction. Full parts on a
neutral chromosome stand in for admitted placements; the gate is run with
require_supported=False, as in pairwise admission. Real reference anchors,
other windows/base evidence, and final path selection are not in this replay.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from benchmark_regional_mapper_dispatch import LOOKUP_SHA, digest, read_json, within
from probe_regional_dp_budget import load_case
from probe_regional_dp_cap_ladder import CASES, QUALITY_SHA

from lgz_core.q0_alignments import parse_paf_line
from lgz_core.q0_paths import PairLink, PathPolicy, Placement, qualify_pair_blocks
from lgz_core.q0_query_windows import project_regional_paf
from lgz_core.q0_sources import Interval, SourceKey, merged_intervals, subtract_intervals

LADDER_SHA = '9c868e678b47947c38332c41812d4d37911f193b917a07896e600a239d699f34'


def source(part, lookup):
    row = lookup[part]
    return SourceKey(row['dataset'], row['contig'])


def projected_links(path, case, lookup, artifact):
    query = case['query']
    queries = {query.window_id: query}
    targets = {window.window_id: window for window in case['targets']}
    grouped = defaultdict(list)
    with path.open() as raw:
        projected_number = 0
        for number, line in enumerate(raw, 1):
            if not line.strip() or line.startswith('#'):
                continue
            projected = project_regional_paf(line, queries, targets, artifact=artifact, line_number=number)
            if projected is None:
                continue
            # Same dense line numbers as the projected PAF, not raw line numbers.
            projected_number += 1
            hit = parse_paf_line(projected, artifact=artifact+'.projected', line_number=projected_number)
            if (lookup[hit.query_name]['length'], lookup[hit.target_name]['length']) != (hit.query_length, hit.target_length):
                raise ValueError('projected whole-source length mismatch')
            grouped[hit.target_name].append(PairLink(hit, source(hit.query_name, lookup), source(hit.target_name, lookup)))
    return dict(grouped)


def sum_rows(groups):
    return sum(len(links) for links in groups.values())


def neutral_placement(part, orientation, lookup):
    interval = Interval(0, lookup[part]['length'])
    return Placement(part+orientation, part, source(part, lookup), interval, orientation,
                     'diagnostic_neutral', (), (interval,), ('diagnostic_not_a_reference_anchor',))


def add_geometry(groups, strand, query, target):
    # Group by the actual paired-base map, not by single-sided coverage.
    offset = target.start-query.start if strand == '+' else target.end+query.start
    groups[strand, offset].append(query)


def merged(groups):
    return {key: merged_intervals(intervals) for key, intervals in groups.items()}


def qualify(query, target, links, lookup, policy):
    observed, qualified = defaultdict(list), defaultdict(list)
    left = neutral_placement(query, '+', lookup)
    for link in links:
        if link.hit.matches / link.hit.block_length >= policy.minimum_pair_identity:
            for a, b in link.source_blocks():
                add_geometry(observed, link.hit.strand, a, b)
    for strand in ('+', '-'):
        right = neutral_placement(target, strand, lookup)
        for block, _ in qualify_pair_blocks(left, right, links, policy, require_supported=False):
            add_geometry(qualified, strand, left.source_interval(block.left), right.source_interval(block.right))
    return merged(observed), merged(qualified)


def subtract(left, right):
    return {key: remaining for key, intervals in left.items()
            if (remaining := tuple(piece for interval in intervals
                                   for piece in subtract_intervals(interval, right.get(key, ()))))}


def size(groups):
    return sum(interval.length for intervals in groups.values() for interval in intervals)


def compare(query, exact, capped, lookup, policy=PathPolicy()):
    stats = {kind: dict(changed_source_pairs=0, old_observed_paired_bp=0, cap_observed_paired_bp=0,
                        old_qualified_paired_bp=0, cap_qualified_paired_bp=0,
                        lost_qualified_paired_bp=0, gained_qualified_paired_bp=0,
                        gained_previously_observed_but_unqualified_paired_bp=0,
                        pairs_with_qualified_loss=0, pairs_with_qualified_gain=0,
                        pairs_with_previously_unqualified_gain=0)
             for kind in ('intra', 'cross')}
    for target in sorted(exact.keys() | capped.keys()):
        old, new = exact.get(target, ()), capped.get(target, ())
        if {link.hit.record_sha256 for link in old} == {link.hit.record_sha256 for link in new}:
            continue
        kind = 'intra' if lookup[query]['dataset'] == lookup[target]['dataset'] else 'cross'
        row = stats[kind]
        prior, a = qualify(query, target, old, lookup, policy)
        post, b = qualify(query, target, new, lookup, policy)
        lost, gained = subtract(a, b), subtract(b, a)
        gain_prior = size(gained) - size(subtract(gained, prior))
        row['changed_source_pairs'] += 1
        row['old_observed_paired_bp'] += size(prior)
        row['cap_observed_paired_bp'] += size(post)
        row['old_qualified_paired_bp'] += size(a)
        row['cap_qualified_paired_bp'] += size(b)
        row['lost_qualified_paired_bp'] += size(lost)
        row['gained_qualified_paired_bp'] += size(gained)
        row['gained_previously_observed_but_unqualified_paired_bp'] += gain_prior
        row['pairs_with_qualified_loss'] += bool(lost)
        row['pairs_with_qualified_gain'] += bool(gained)
        row['pairs_with_previously_unqualified_gain'] += gain_prior > 0
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('workspace', 'archived', 'heldout', 'quality', 'lookup', 'ladder'):
        parser.add_argument('--'+arg, required=True, type=Path)
    args = parser.parse_args()
    work = args.workspace.resolve(strict=True)
    ladder = args.ladder.resolve(strict=True)
    if ladder.is_relative_to(work) or Path.cwd().resolve().is_relative_to(work):
        raise ValueError('diagnostic cannot operate inside the main workspace')
    report_path = within(ladder, 'report.json')
    for path, expected in ((report_path, LADDER_SHA), (args.quality, QUALITY_SHA), (args.lookup, LOOKUP_SHA)):
        if digest(path) != expected:
            raise ValueError(f'changed frozen input: {path.name}')
    report, cohort, lookup = (read_json(report_path), read_json(args.quality), read_json(args.lookup))
    rows = {case['ordinal']: case for case in report['cases']}
    results = []
    for ordinal, archive, _reason in CASES:
        case = load_case(work, getattr(args, archive).resolve(strict=True), cohort['rows'][ordinal], ordinal, lookup)
        query = case['query'].segment_id
        run = rows[ordinal]
        if run['source_part'] != query:
            raise ValueError('pilot source identity changed')
        paths = {r['profile']: (within(ladder, f'{ordinal}/{r["profile"]}/result.paf'), r['output_sha256'])
                 for r in run['results']}
        _, exact_sha = paths['original']
        if exact_sha != case['raw_sha']:
            raise ValueError('control differs from archive')
        versions = {}
        for profile, (path, sha) in paths.items():
            if digest(path) != sha:
                raise ValueError('archived diagnostic output SHA mismatch')
            versions[profile] = projected_links(path, case, lookup, f'diagnostic/{ordinal}/{profile}')
            if digest(path) != sha:
                raise ValueError('archived diagnostic output changed during replay')
        results.append({'ordinal': ordinal, 'raw_paf_digests': {k: sha for k, (_, sha) in paths.items()},
                        'projected_rows': {k: sum_rows(v) for k, v in versions.items()},
                        'comparison': {profile: compare(query, versions['original'], versions[profile], lookup)
                                       for profile in ('30m', '10m')}})
    print(json.dumps({'status': 'pair_qualification_only_NOT_production_acceptance',
                      'scope': 'changed pairs in three archived windows only; neutral placements; no other PAFs, anchors or path selection',
                      'gate': 'production qualify_pair_blocks with require_supported=False',
                      'unit': 'part pair, strand and affine paired-base map, separately unioned',
                      'input_report_sha256': LADDER_SHA, 'cases': results}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
