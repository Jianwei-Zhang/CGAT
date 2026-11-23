"""Native ABBA pilot of full-target versus coarse-to-shortlist regional work.

Uses the 64 SHA-verified historical window FASTAs, never whole source DNA or the
production cache. Old exact stdout must match historical evidence byte-for-byte.
Candidate stdout is independently validated and compared by high-quality paired
core coverage; it is NOT presumed equivalent and never adopted by the main job.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import socket
import sys
import time

from benchmark_regional_mapper_dispatch import digest, read_json, within, dispatch, GIB
from probe_regional_candidate_screen import choose_targets, coverage_summary


def input_argv(argv, target, query, *, coarse=False):
    if not isinstance(argv, list) or not argv or '-t' not in argv or argv[argv.index('-t')+1] != '2':
        raise ValueError('native pilot requires the original two-thread command')
    prefix = list(argv[:-2])
    if coarse: prefix = [v for v in prefix if v != '-c']
    elif prefix.count('-c') != 1: raise ValueError('exact command needs precisely one CIGAR flag')
    return [*prefix, str(target), str(query)]



def merged(rows):
    result = []
    for start, end in sorted(rows):
        if start < 0 or end <= start: raise ValueError('invalid covered interval')
        if result and start <= result[-1][1]: result[-1] = (result[-1][0], max(end, result[-1][1]))
        else: result.append((start, end))
    return result


def difference_bases(left, right):
    """Set difference, not net total coverage: gains must never hide losses."""
    right = merged(right); total = 0; index = 0
    for start, end in merged(left):
        while index < len(right) and right[index][1] <= start: index += 1
        cursor = start; j = index
        while j < len(right) and right[j][0] < end:
            low, high = right[j]
            total += max(0, min(end, low)-cursor); cursor = max(cursor, min(end, high)); j += 1
        total += max(0, end-cursor)
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package-dir', 'control-artifacts', 'anchor-report', 'quality-report', 'trace', 'lookup', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); started = time.monotonic(); work = a.workspace.resolve(strict=True); inputs = a.control_artifacts.resolve(strict=True); out = a.output.resolve()
    if out.is_relative_to(work) or inputs.is_relative_to(work) or out.is_relative_to(inputs) or inputs.is_relative_to(out): raise ValueError('diagnostic/input/main overlap')
    if digest(a.anchor_report) != '8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901' or digest(a.quality_report) != 'b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438':
        raise ValueError('fixed control/quality cohort changed')
    if digest(a.trace) != 'e74626d25d32da75377c79092f275f77501ccb3e340dcca100aedd3ec8b387be' or digest(a.lookup) != '2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89': raise ValueError('frozen metadata changed')
    out.mkdir(exist_ok=False); sys.path.insert(0, str(a.package_dir.resolve(strict=True)))
    from lgz_core.common import read_fasta, write_fasta
    from lgz_core.q0_alignments import read_paf
    from lgz_core.q0_regional_mapping import _execute, chain_work
    from lgz_core.q0_regional_execution import allocation_memory_limit
    from lgz_core.q0_query_windows import QueryWindow, TargetWindow
    from lgz_core.q0_cigar_policy import CigarWorkPolicy
    if allocation_memory_limit(16) != 160*GIB: raise ValueError('pilot requires a checked 16CPU/160GiB allocation')
    anchor = read_json(a.anchor_report); quality = read_json(a.quality_report); lookup = read_json(a.lookup); trace = read_json(a.trace)
    projects = {r['raw']: r for r in trace['new_projects'] if not r['raw_before_new_owner']}; cases = []; input_bytes = 0
    for row in anchor['cases']:
        rp = within(work, row['raw_receipt']); receipt = read_json(rp, 2*1024**2)
        if digest(rp) != row['receipt_sha256'] or receipt['status'] != 'success': raise ValueError('original raw changed')
        cp = within(work, receipt['spec']['context']['path'])
        if digest(cp) != receipt['spec']['context']['sha256']: raise ValueError('context changed')
        context = read_json(cp, 2*1024**2); spec = context['spec']; rel = str(cp.parent.relative_to(work))
        for identity in context['inputs']:
            path = within(inputs, identity['path'])
            if path.stat().st_size != identity['size'] or digest(path) != identity['sha256']: raise ValueError('existing control FASTA changed')
            input_bytes += identity['size']
        if input_bytes > 2*GIB: raise ValueError('unbounded window input')
        qrow = projects[row['raw_receipt']]['query']; query = QueryWindow(**{k: tuple(map(tuple, v)) if k == 'cores' else v for k, v in qrow.items() if k != 'window_id'})
        targets = [TargetWindow(**{k: v for k, v in r.items() if k != 'window_id'}) for r in spec['targets']]
        td = {t.window_id: lookup[t.segment_id]['dataset'] for t in targets}; lengths = {t.window_id: t.length for t in targets}; qd = lookup[query.segment_id]['dataset']
        command = read_json(rp.parent/'command.json', 2*1024**2)
        cmd_id = next(r for r in receipt['outputs'] if r['path'].endswith('/command.json'))
        if digest(rp.parent/'command.json') != cmd_id['sha256'] or command['address_space_bytes'] != 4*GIB: raise ValueError('native command changed')
        argv = command['argv']; tool = spec['tool']
        if argv[0] != tool['resolved'] or digest(Path(tool['resolved'])) != tool['sha256']: raise ValueError('native executable changed')
        raw_id = next(r for r in receipt['outputs'] if r['path'].endswith('/result.paf'))
        if raw_id['sha256'] != row['paf_sha256'] or digest(within(work, raw_id['path'])) != row['paf_sha256']: raise ValueError('historical output changed')
        pre = cp.parent/'chaining/success.json'; preargv = None; presha = None
        if pre.exists():
            pr = read_json(pre, 2*1024**2)
            if pr['status'] != 'success' or pr['spec']['context'] != receipt['spec']['context']: raise ValueError('old coarse context differs')
            for r in pr['outputs']:
                if digest(within(work, r['path'])) != r['sha256']: raise ValueError('old coarse output changed')
            preargv = read_json(pre.parent/'command.json')['argv']; presha = next(r['sha256'] for r in pr['outputs'] if r['path'].endswith('/result.paf'))
        cases.append({'raw_receipt': row['raw_receipt'], 'context': context, 'rel': rel, 'query': query, 'targets': targets, 'td': td, 'qd': qd, 'lengths': lengths,
                      'argv': argv, 'tool': tool, 'rawsha': row['paf_sha256'], 'preargv': preargv, 'presha': presha})
    if len(cases) != 64: raise ValueError('anchor cohort is not the expected 64 cases')
    print(json.dumps({'phase': 'inputs_verified', 'cases': len(cases), 'input_bytes': input_bytes, 'seconds': time.monotonic()-started}), flush=True)

    def quality_of(path, case, chosen):
        values = defaultdict(list); query = case['query']
        for hit in read_paf(path, query_lengths={query.window_id: query.length}, target_lengths={k: v for k, v in case['lengths'].items() if k in chosen}):
            if hit.matches/hit.block_length < .95: continue
            blocks = list(hit.aligned_blocks())
            if sum(b.query.length for b in blocks) < 100: continue
            for b in blocks:
                if b.operation == 'X': continue
                start, end = b.query.start+query.start, b.query.end+query.start
                for lo, hi in query.cores:
                    if max(start, lo) < min(end, hi): values[hit.target_name].append((max(start, lo), min(end, hi)))
        by_kind = {kind: merged([interval for key, rows in values.items() if ('intra' if case['td'][key] == case['qd'] else 'cross') == kind for interval in rows]) for kind in ('intra', 'cross')}
        return {'bases': coverage_summary(values, case['td'], case['qd'], chosen), 'intervals': by_kind}

    phases = []; fresh_coarse_shas = {}
    for phase, mode in enumerate(('full', 'screened', 'screened', 'full')):
        directory = out/f'phase-{phase}-{mode}'; directory.mkdir(); begin = time.monotonic()
        def run(ordinal, case):
            dest = directory/str(ordinal); dest.mkdir(); t = time.monotonic(); query = case['query']; all_ids = set(case['td']); chosen = all_ids
            full_target, full_query = inputs/case['rel']/'target.fa', inputs/case['rel']/'query.fa'
            coarse_seconds = 0; coarse_sha = None
            if case['preargv'] is not None or mode == 'screened':
                d = dest/'coarse'; d.mkdir(); ct = time.monotonic()
                argv = input_argv(case['preargv'] or case['argv'], full_target, full_query, coarse=True)
                _execute(inputs, d, case['context'], case['rel'], None, query, case['targets'], argv, case['tool'], 4*GIB)
                path = d/'result.paf.tmp'; chain_work(path, query, case['lengths'], CigarWorkPolicy()); coarse_sha = digest(path)
                if case['presha'] is not None and coarse_sha != case['presha']: raise ValueError('replayed coarse stdout differs from old complete PAF')
                if case['presha'] is None:
                    old = fresh_coarse_shas.setdefault(ordinal, coarse_sha)
                    if coarse_sha != old: raise ValueError('fresh small-query coarse run is not deterministic')
                if mode == 'screened':
                    chains = []
                    with path.open() as f:
                        for line in f:
                            if not line.strip() or line.startswith('#'): continue
                            v = line.rstrip('\n').split('\t'); chains.append((v[5], int(v[2]), int(v[3]), int(v[9]), int(v[10]), next(int(tag[5:]) for tag in v[12:] if tag.startswith('s1:i:')), v[4]))
                    chosen = choose_targets(chains, case['td'], case['qd'], tuple((lo-query.start, hi-query.start) for lo, hi in query.cores), 4, 8)
                path.rename(d/'result.paf'); coarse_seconds = time.monotonic()-ct
            native_exact = bool(chosen); exact = dest/'exact'; exact.mkdir()
            if native_exact:
                if mode == 'full':
                    _execute(inputs, exact, case['context'], case['rel'], None, query, case['targets'], input_argv(case['argv'], full_target, full_query), case['tool'], 4*GIB)
                else:
                    sub = dest/'subset'; sub.mkdir(); shutil.copyfile(full_query, sub/'query.fa')
                    def records():
                        seen = set()
                        for name, sequence in read_fasta(full_target):
                            if name in chosen:
                                if name in seen or len(sequence) != case['lengths'][name]: raise ValueError('subset target identity differs')
                                seen.add(name); yield name, sequence
                        if seen != chosen: raise ValueError('selected target missing from verified full FASTA')
                    write_fasta(sub/'target.fa', records()); relative = str(sub.relative_to(out))
                    identities = [{'path': str((sub/name).relative_to(out)), 'size': (sub/name).stat().st_size, 'sha256': digest(sub/name)} for name in ('query.fa', 'target.fa')]
                    subset = {'inputs': identities}; selected = [r for r in case['targets'] if r.window_id in chosen]
                    _execute(out, exact, subset, relative, None, query, selected, input_argv(case['argv'], sub/'target.fa', sub/'query.fa'), case['tool'], 4*GIB)
                (exact/'result.paf.tmp').rename(exact/'result.paf')
            else:
                # DIAGNOSTIC proposal only, never a native success/negative receipt.
                (exact/'result.paf').write_text('')
            sha = digest(exact/'result.paf')
            if mode == 'full' and sha != case['rawsha']: raise ValueError('full native stdout differs from historical complete raw')
            cov = quality_of(exact/'result.paf', case, chosen)
            return {'ordinal': ordinal, 'raw_receipt': case['raw_receipt'], 'seconds': time.monotonic()-t, 'coarse_seconds': coarse_seconds,
               'target_windows': len(chosen), 'target_bases': sum(r.length for r in case['targets'] if r.window_id in chosen), 'native_exact_executed': native_exact,
               'coarse_sha256': coarse_sha, 'exact_sha256': sha, 'high_quality_core_bases': cov['bases'], 'high_quality_core_intervals': cov['intervals']}
        results, order = dispatch(cases, run, 7, 'completed'); elapsed = time.monotonic()-begin
        phases.append({'phase': phase, 'mode': mode, 'seconds': elapsed, 'results': results, 'completion_order': order})
        print(json.dumps({'phase': phase, 'mode': mode, 'seconds': elapsed, 'target_bases': sum(r['target_bases'] for r in results), 'high_quality_core_bases': {k: sum(r['high_quality_core_bases'][k] for r in results) for k in ('intra', 'cross')}}), flush=True)
    for i in range(64):
        if phases[0]['results'][i]['exact_sha256'] != phases[3]['results'][i]['exact_sha256'] or phases[1]['results'][i]['exact_sha256'] != phases[2]['results'][i]['exact_sha256']:
            raise ValueError('within-mode native outputs differ between repetitions')
    full = sum(r['seconds'] for r in phases if r['mode'] == 'full'); screened = sum(r['seconds'] for r in phases if r['mode'] == 'screened')
    comparisons = []
    for i in range(64):
        before = phases[0]['results'][i]['high_quality_core_bases']; after = phases[1]['results'][i]['high_quality_core_bases']
        bi = phases[0]['results'][i]['high_quality_core_intervals']; ai = phases[1]['results'][i]['high_quality_core_intervals']
        comparisons.append({'ordinal': i, 'old': before, 'screened': after, 'lost': {k: difference_bases(bi[k], ai[k]) for k in before}, 'gained': {k: difference_bases(ai[k], bi[k]) for k in before}})
    report = {'status': 'native_coarse_shortlist_abba_completed_NOT_production_acceptance', 'hostname': socket.gethostname(), 'cases': 64, 'intra_budget_per_core': 4, 'cross_budget_per_core': 8,
       'threads': 16, 'mappers': 7, 'threads_per_mapper': 2, 'mapper_AS_bytes': 4*GIB, 'input_bytes_verified': input_bytes,
       'phases': phases, 'full_over_screened_pipeline_mapper_time': full/screened, 'old_exact_stdout_all_equal_historical': True,
       'quality': {'old': {k: sum(r['old'][k] for r in comparisons) for k in ('intra', 'cross')}, 'screened': {k: sum(r['screened'][k] for r in comparisons) for k in ('intra', 'cross')},
          'old_core_bases_not_covered_by_screened_output': {k: sum(r['lost'][k] for r in comparisons) for k in ('intra', 'cross')}, 'comparisons': comparisons},
       'main_workspace_modified': False, 'production_strategy_enabled': False, 'source_DNA_loaded_whole': False, 'native_mapper_executed': True, 'seconds': time.monotonic()-started,
       'limitations': ['64 previously completed, bounded contiguous anchor cases; not a held-out or whole-queue sample.', 'No planning/catalog/whole-genome acceptance or production large-heap fork cost measured.',
          'Subset selection changes mapper context and output, explicitly not byte-equivalent to full targets.', 'Coarse-empty proposals never become production exact negative evidence.', 'Cold/hot/shared-node variance reduced, not eliminated, by ABBA.']}
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('phases', 'quality')}, indent=2), flush=True)


if __name__ == '__main__': main()
