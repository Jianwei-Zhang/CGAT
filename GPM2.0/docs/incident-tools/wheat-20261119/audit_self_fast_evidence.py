"""Stratify existing full self PAFs; no mapper, workspace writes, or adoption.

Uses the previously verified native/candidate comparison as an input receipt.
The q0 identity stratum is a NECESSARY filter, not full q0 admission. In
particular, dropping alternative placements can manufacture apparent uniqueness.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import sys

import full_self_seed_pilot as pilot
import inspect_full_self_pilot as inspection
import self_paf_comparison as comparison


def filter_identity(source, destination, minimum_identity, minimum_length=0):
    counts = Counter()
    if not 0 < minimum_identity <= 1 or minimum_length < 0:
        raise ValueError('invalid diagnostic filter')
    with source.open() as inp, destination.open('x') as out:
        for number, line in enumerate(inp, 1):
            fields = line.rstrip('\r\n').split('\t')
            if len(fields) < 12:
                raise ValueError('short PAF row %d' % number)
            matches, length = int(fields[9]), int(fields[10])
            if not 0 <= matches <= length or length <= 0:
                raise ValueError('invalid PAF identity')
            counts['input_rows'] += 1
            if matches / length >= minimum_identity and length >= minimum_length:
                out.write(line)
                counts['retained_rows'] += 1
    return dict(counts)


def uniqueness_transition(baseline, candidate):
    """Exact sampled forward-query maps, including opposing strand alternatives.

This does not test reference consistency, sequence complexity, target-side
uniqueness, or all 100-bp competing overlaps. It must not be called q0 acceptance.
"""
    def grouped(evidence):
        result = defaultdict(set)
        for (query, target, strand, q), positions in evidence.anchors.items():
            result[(query, target, q)].update((strand, t) for t in positions)
        return result
    a, b = grouped(baseline), grouped(candidate)
    counts = Counter()
    for key in a.keys() | b.keys():
        left, right = a.get(key, set()), b.get(key, set())
        if len(left) > 1:
            counts['baseline_multiple_grid_keys'] += 1
            if len(right) == 1:
                counts['multiple_to_single_grid_keys'] += 1
                counts['multiple_to_single_survivor_observed_in_baseline'] += bool(right <= left)
        if len(left) == 1:
            counts['baseline_single_grid_keys'] += 1
            if left <= right:
                counts['baseline_single_map_retained_exactly'] += 1
            else:
                counts['baseline_single_map_missing_or_shifted'] += 1
        if len(right) == 1:
            counts['candidate_single_grid_keys'] += 1
            if not left:
                counts['candidate_single_absent_from_baseline_grid'] += 1
    return {'scope': 'sampled_query_side_maps_per_contig_pair_including_both_strands',
            'q0_admission_evaluated': False, 'exact_coordinates_no_tolerance': True,
            'counts': dict(counts)}


def summarize(report):
    result = {key: report[key] for key in ('baseline', 'candidate', 'position_support')}
    for axis in ('query', 'target'):
        sums = Counter()
        for row in report['pairs']:
            sums.update(row[axis + '_aligned_coverage'])
        result['pair_' + axis + '_coverage'] = dict(sums)
    return result


def execute(work, source_report, output):
    work, source_report = work.resolve(strict=True), source_report.resolve(strict=True)
    output = output.resolve()
    if output.exists() or output == work or output.is_relative_to(work) or work.is_relative_to(output):
        raise ValueError('use a fresh isolated output directory')
    raw = source_report.read_bytes()
    prior = json.loads(raw)
    if (prior.get('status') != 'candidate_and_committed_native_compared_not_adopted'
            or prior.get('candidate_adopted') is not False
            or prior.get('analysis_workspace_modified') is not False):
        raise ValueError('successful complete native-versus-candidate comparison required')
    expected = {**prior['native_commit']['marker'], **prior['native_commit']['outputs'],
                **prior['candidate_outputs']}
    inspection.checked_files(expected)
    def result_path(rows):
        paths = [Path(p) for p in rows if Path(p).name == 'result.paf']
        if len(paths) != 1:
            raise ValueError('one restored result per source required')
        return paths[0]
    native = result_path(prior['native_commit']['outputs'])
    candidate = result_path(prior['candidate_outputs'])
    sys.path.insert(0, str(work / '.prepare_lib/tools'))
    from lgz_core import q0_paths
    if Path(q0_paths.__file__).resolve() != work / '.prepare_lib/tools/lgz_core/q0_paths.py':
        raise ValueError('wrong q0 policy module imported')
    policy = q0_paths.PathPolicy()
    output.mkdir()
    result = {'status': 'full_self_identity_strata_compared_not_adopted',
        'candidate_adopted': False, 'analysis_workspace_modified': False,
        'q0_admission_evaluated': False,
        'limitations': ['identity is necessary but not sufficient for q0 admission',
            'reference placement, sequence complexity and full conflicting overlaps are not evaluated',
            'secondary and MAPQ-zero alignments remain included',
            'sampling does not measure biological accuracy or end-to-end output equivalence'],
        'policy': asdict(policy), 'source_report': pilot.identities([source_report]),
        'checked_source_files': expected, 'strata': {}}
    for name, length in (('q0_identity_necessary', 0), ('long_high_identity_diagnostic', 10000)):
        left, right = output / (name + '-native.paf'), output / (name + '-fast.paf')
        counts = [filter_identity(src, dst, policy.minimum_pair_identity, length)
                  for src, dst in ((native, left), (candidate, right))]
        a, b = comparison.read_evidence(left), comparison.read_evidence(right)
        report = comparison.compare_evidence(a, b)
        result['strata'][name] = {'minimum_identity': policy.minimum_pair_identity,
            'minimum_paf_block_length': length, 'row_filter_counts': counts,
            'comparison': report, 'uniqueness_transition': uniqueness_transition(a, b)}
        print(name, json.dumps({'comparison': summarize(report),
            'uniqueness_transition': result['strata'][name]['uniqueness_transition']}), flush=True)
        del a, b
    inspection.checked_files(expected)
    if source_report.read_bytes() != raw:
        raise ValueError('source receipt changed during audit')
    result['code'] = pilot.identities([Path(__file__), Path(comparison.__file__),
        Path(pilot.__file__), Path(inspection.__file__), Path(q0_paths.__file__)])
    result['outputs'] = pilot.identities(sorted(output.glob('*.paf')))
    with (output / 'audit.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('work', 'source-report', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    execute(args.work, args.source_report, args.output)
