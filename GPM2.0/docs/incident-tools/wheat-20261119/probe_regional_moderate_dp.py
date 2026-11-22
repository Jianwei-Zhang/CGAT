"""Screen moderate Q0 DP caps on frozen real windows; never publish evidence."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time

from benchmark_regional_mapper_dispatch import GIB, LOOKUP_SHA, digest, read_json
from probe_regional_dp_budget import command_for, load_case, observed_timing, paired_quality, summarize_quality

QUALITY_SHA = 'b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438'
INDEXED_SHA = '1578e60a68ed9d86356702245a89031fc9fb8b58f3622911747d5a93e5de21db'
# Three earlier cap sentinels, three different slow parents not used in that
# cap ladder, and one cheap control. All are from existing frozen cohorts.
CASES = (1, 65, 68, 72, 77, 78, 81)
CAPS = ('50m', '70m')


def ordered_profiles(i):
    profiles = ('original', *CAPS)
    offset = i % len(profiles)
    return profiles[offset:] + profiles[:offset]


def argv_for(case, profile):
    argv = command_for(case['argv'], case['paths']['target.fa'], case['paths']['query.fa'], False)
    if argv[1] != '-c' or argv[-4:-2] != ['-t', '2'] or profile not in ('original', *CAPS):
        raise ValueError('unknown profile or noncanonical archived exact command')
    return argv if profile == 'original' else [*argv[:-2], '--cap-sw-mem', profile, *argv[-2:]]


def isolated(work, inputs, output):
    roots = [work, *inputs, output]
    if any(a.is_relative_to(b) or b.is_relative_to(a)
           for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise ValueError('diagnostic paths overlap')


def cross_disqualifiers(quality, pairs):
    """Provisional screen for larger replay, not production acceptance."""
    return [key for failed, key in (
        (quality['lost_core_bp'] * 100 > 2 * quality['old_core_bp'], 'cross_core_loss_above_2pct'),
        (quality['missing_oriented_targets_ge_1kb'] > 0, 'cross_oriented_target_missing'),
        (pairs['gained_previously_observed_but_unqualified_paired_bp'] > 0, 'new_cross_admission'),
        (pairs['lost_qualified_paired_bp'] * 100 > 2 * pairs['old_qualified_paired_bp'], 'cross_pair_loss_above_2pct'),
    ) if failed]


def indexed_gate(path):
    import probe_regional_cap_consumer as consumer

    if digest(path) != INDEXED_SHA:
        raise ValueError('indexed pairing implementation differs')
    spec = importlib.util.spec_from_file_location('lgz_core.q0_paths_indexed', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    consumer.qualify_pair_blocks = module.qualify_pair_blocks
    return consumer


def run_case(i, case, inputs, out):
    from lgz_core.q0_regional_mapping import _execute

    root = out / str(case['ordinal'])
    root.mkdir()
    results = {}
    order = ordered_profiles(i)
    for profile in order:
        dest = root / profile
        dest.mkdir()
        argv = argv_for(case, profile)
        start = time.monotonic()
        _execute(inputs, dest, case['context'], case['rel'], None, case['query'], case['targets'], argv, case['tool'], 4 * GIB)
        dispatch_wall = time.monotonic() - start
        tmp = dest / 'result.paf.tmp'
        sha = digest(tmp)
        if profile == 'original' and sha != case['raw_sha']:
            raise ValueError('same-node original differs from historical output')
        result = {'exact_dispatch_seconds': dispatch_wall, 'native': observed_timing(dest / 'stderr.log'), 'sha256': sha}
        tmp.rename(dest / 'result.paf')
        results[profile] = result
        print(json.dumps({'stage': 'exact_finished', 'ordinal': case['ordinal'], 'profile': profile, **result}), flush=True)
    return {'ordinal': case['ordinal'], 'profiles': results, 'order': order}


def analyze(result, case, out, lookup, consumer):
    from lgz_core.q0_alignments import read_paf

    profiles = result['profiles']
    ordinal = result['ordinal']
    part = case['query'].segment_id
    paths = {k: out / str(ordinal) / k / 'result.paf' for k in profiles}
    old_quality = paired_quality(paths['original'], case, read_paf)
    old_links = consumer.projected_links(paths['original'], case, lookup, f'diagnostic/{ordinal}/original')
    for cap in CAPS:
        quality = summarize_quality(old_quality, paired_quality(paths[cap], case, read_paf), case)
        links = consumer.projected_links(paths[cap], case, lookup, f'diagnostic/{ordinal}/{cap}')
        pairs = consumer.compare(part, old_links, links, lookup)
        profiles[cap].update(coverage=quality, pair_gate=pairs,
                             cross_screen_rejections=cross_disqualifiers(quality['cross'], pairs['cross']))
    if digest(case['raw']) != case['raw_sha'] or any(digest(p) != profiles[k]['sha256'] for k, p in paths.items()):
        raise ValueError('result changed during replay')
    result.update(query_dataset=case['qd'], source_part=part)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'archived', 'heldout', 'quality', 'lookup', 'indexed', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    work, archived, heldout = (path.resolve(strict=True) for path in (a.workspace, a.archived, a.heldout))
    out = a.output.resolve()
    isolated(work, (archived, heldout), out)
    if digest(a.quality) != QUALITY_SHA or digest(a.lookup) != LOOKUP_SHA:
        raise ValueError('frozen cohort identity differs')
    consumer = indexed_gate(a.indexed)
    rows = read_json(a.quality)['rows']
    lookup = read_json(a.lookup)
    cases = []
    for ordinal in CASES:
        row = rows[ordinal]
        if row['ordinal'] != ordinal or row['anchor_case'] != (ordinal == 1):
            raise ValueError('cohort ordinal or archive mismatch')
        origin = archived if row['anchor_case'] else heldout
        cases.append((load_case(work, origin, row, ordinal, lookup), origin))
    input_bytes = sum(c['bytes'] for c, _ in cases)
    if input_bytes > 512 * 1024**2 or len({c['query'].segment_id for c, _ in cases}) != len(CASES):
        raise ValueError('cohort exceeds bounds or repeats source parts')
    out.mkdir(exist_ok=False)
    print(json.dumps({'stage': 'inputs_verified', 'bytes': input_bytes, 'cases': CASES}), flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run_case, i, c, origin, out) for i, (c, origin) in enumerate(cases)]
        results = [f.result() for f in futures]
    print(json.dumps({'stage': 'all_exact_arms_finished'}), flush=True)
    report = {'status': 'moderate_cap_window_screen_only', 'host': socket.gethostname(), 'cases': [],
              'fasta_bytes_verified': input_bytes, 'archived_coarse_rerun': False,
              'comparison_scope': 'same-node exact dispatch and neutral pairwise gate, not full Q0 or end-to-end',
              'production_runtime_changed': False}
    for result, (case, _) in zip(results, cases):
        report['cases'].append(analyze(result, case, out, lookup, consumer))
        print(json.dumps({'stage': 'pair_gate_finished', 'ordinal': case['ordinal']}), flush=True)
    with (out / 'report.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write('\n')


if __name__ == '__main__':
    main()
