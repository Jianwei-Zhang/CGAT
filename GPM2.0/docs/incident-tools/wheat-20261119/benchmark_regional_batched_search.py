"""Isolated native test of shared-target query batching and an explicit seed filter.

This is not production evidence. A frozen legacy control is replayed twice and
must match all historical PAF bytes. Candidate batching changes target context;
its paired-core interval losses and gains are reported independently. Original
full-target per-query CIGAR profile choices remain frozen in this experiment.
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
from benchmark_regional_candidate_screen import input_argv, merged, difference_bases


def make_groups(cases, maximum=4, target_cap=100000000):
    """Group compatible frozen commands without exceeding a target-memory cap."""
    if maximum < 1 or target_cap < 1: raise ValueError('invalid batch budget')
    pending = {}; groups = []
    for ordinal, case in enumerate(cases):
        argv = case['argv']; key = (tuple(argv[:-2]), json.dumps(case['tool'], sort_keys=True))
        lengths = {w.window_id: w.length for w in case['targets']}
        if sum(lengths.values()) > target_cap: raise ValueError('single case exceeds declared target cap')
        group = pending.get(key)
        union = {**(group['lengths'] if group else {}), **lengths}
        if group and (len(group['ordinals']) >= maximum or sum(union.values()) > target_cap
                      or case['query'].window_id in group['queries']):
            groups.append(group); group = None
        if group is None:
            group = {'ordinals': [], 'lengths': {}, 'queries': set()}; pending[key] = group
        group['ordinals'].append(ordinal); group['lengths'].update(lengths); group['queries'].add(case['query'].window_id)
    groups.extend(pending.values()); groups.sort(key=lambda g: min(g['ordinals']))
    if sorted(i for g in groups for i in g['ordinals']) != list(range(len(cases))): raise ValueError('batch ownership changed')
    return groups


def filtered_argv(argv, target, query, *, coarse=False, filtered=False):
    result = input_argv(argv, target, query, coarse=coarse)
    if filtered:
        if '-f' in result: raise ValueError('do not silently override existing seed filter')
        result[-2:-2] = ['-f', '0.005']
    return result


def interval_quality(path, case, read_paf):
    values = defaultdict(list); query = case['query']
    for hit in read_paf(path, query_lengths={query.window_id: query.length}, target_lengths=case['lengths']):
        if hit.matches/hit.block_length < .95: continue
        blocks = list(hit.aligned_blocks())
        if sum(b.query.length for b in blocks) < 100: continue
        kind = 'intra' if case['td'][hit.target_name] == case['qd'] else 'cross'
        for b in blocks:
            if b.operation == 'X': continue
            start, end = b.query.start+query.start, b.query.end+query.start
            for lo, hi in query.cores:
                if max(start, lo) < min(end, hi): values[kind].append((max(start, lo), min(end, hi)))
    intervals = {kind: merged(values[kind]) for kind in ('intra', 'cross')}
    return {'intervals': intervals, 'bases': {k: sum(b-a for a,b in v) for k,v in intervals.items()}}


def load_cases(a, work, inputs):
    if digest(a.anchor_report) != '8d774d0fd5ac8652f503375a75c997c8182852041d5fe052e3c6a88c66047901' or digest(a.quality_report) != 'b2b8b2b06cd25aa9c511b198e406c308d00736923dce615f584471d00060a438':
        raise ValueError('fixed control/quality cohort changed')
    if digest(a.trace) != 'e74626d25d32da75377c79092f275f77501ccb3e340dcca100aedd3ec8b387be' or digest(a.lookup) != '2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89': raise ValueError('frozen metadata changed')
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
    if len(cases) != 64: raise ValueError('expected 64 anchor cases')
    return cases, input_bytes


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('workspace', 'package-dir', 'control-artifacts', 'anchor-report', 'quality-report', 'trace', 'lookup', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); started = time.monotonic(); work = a.workspace.resolve(strict=True)
    inputs = a.control_artifacts.resolve(strict=True); out = a.output.resolve()
    if any(x.is_relative_to(y) or y.is_relative_to(x) for x,y in [(out,work),(out,inputs),(inputs,work)]):
        raise ValueError('diagnostic/input/main directories overlap')
    out.mkdir(exist_ok=False); sys.path.insert(0, str(a.package_dir.resolve(strict=True)))
    from lgz_core.common import read_fasta, write_fasta
    from lgz_core.q0_alignments import read_paf
    from lgz_core.q0_regional_mapping import _execute, chain_work
    from lgz_core.q0_cigar_policy import CigarWorkPolicy
    cases, input_bytes = load_cases(a, work, inputs)
    print(json.dumps({'phase':'inputs_verified','cases':len(cases),'input_bytes':input_bytes,'seconds':time.monotonic()-started}), flush=True)
    prep = time.monotonic(); groups = make_groups(cases); prepared = []
    for ordinal, group in enumerate(groups):
        dest = out/'batched-inputs'/str(ordinal); dest.mkdir(parents=True)
        query_windows = []; targets = {}
        for index in group['ordinals']:
            case = cases[index]; query_windows.append(case['query'])
            for w in case['targets']:
                if w.window_id in targets and targets[w.window_id] != w: raise ValueError('target ID collision')
                targets[w.window_id] = w
        def query_records():
            for index in group['ordinals']:
                case = cases[index]; records = list(read_fasta(inputs/case['rel']/'query.fa'))
                if len(records) != 1 or records[0][0] != case['query'].window_id or len(records[0][1]) != case['query'].length:
                    raise ValueError('query FASTA inventory differs')
                yield records[0]
        def target_records():
            seen = {}
            for index in group['ordinals']:
                case = cases[index]
                for name, sequence in read_fasta(inputs/case['rel']/'target.fa'):
                    sha = hashlib.sha256(sequence.encode('ascii')).hexdigest()
                    if name not in targets or len(sequence) != targets[name].length: raise ValueError('target FASTA inventory differs')
                    if name in seen:
                        if seen[name] != sha: raise ValueError('shared target content differs')
                    else:
                        seen[name] = sha; yield name, sequence
            if set(seen) != set(targets): raise ValueError('missing batched target')
        # Native order is explicitly recorded: deterministic first occurrence,
        # not presumed equivalent to any original per-case target ordering.
        write_fasta(dest/'query.fa', query_records()); write_fasta(dest/'target.fa', target_records())
        rel = str(dest.relative_to(out)); identities = [{'path': str((dest/name).relative_to(out)), 'size': (dest/name).stat().st_size, 'sha256': digest(dest/name)} for name in ('query.fa','target.fa')]
        prepared.append({'ordinals':group['ordinals'], 'rel':rel, 'context':{'inputs':identities}, 'targets':list(targets.values()), 'queries':query_windows})
    prep_seconds = time.monotonic()-prep
    print(json.dumps({'phase':'batches_prepared','groups':len(groups),'seconds':prep_seconds,'largest_target_bases':max(sum(w.length for w in g['targets']) for g in prepared)}), flush=True)
    phases = []
    # ABC CBA, same allocation/tool/7 slots, no special treatment of quiet jobs.
    for phase, mode in enumerate(('legacy','batched','batched_f005','batched_f005','batched','legacy')):
        directory = out/f'phase-{phase}-{mode}'; directory.mkdir(); begin = time.monotonic()
        def run(ordinal, item):
            dest = directory/str(ordinal); dest.mkdir(); begin_case = time.monotonic()
            indices = [ordinal] if mode == 'legacy' else item['ordinals']; first = cases[indices[0]]
            if mode == 'legacy':
                root = inputs; context = first['context']; rel = first['rel']; targets = first['targets']; queries = [first['query']]
            else:
                root = out; context = item['context']; rel = item['rel']; targets = item['targets']; queries = item['queries']
            target = root/rel/'target.fa'; query = root/rel/'query.fa'
            coarse = dest/'coarse'; coarse_seconds = 0
            if mode != 'legacy' or first['preargv'] is not None:
                coarse.mkdir(); ct = time.monotonic()
                argv = filtered_argv(first['preargv'] or first['argv'], target, query, coarse=True, filtered=mode=='batched_f005')
                # Legacy coarse flags are admitted separately from raw flags.
                _execute(root, coarse, context, rel, None, queries[0], targets, argv, first['tool'], 4*GIB)
                coarse_sha = digest(coarse/'result.paf.tmp')
                if mode == 'legacy' and coarse_sha != first['presha']: raise ValueError('legacy coarse differs from historical')
                coarse_paths = {q.window_id:coarse/f'query-{j}.paf' for j,q in enumerate(queries)}
                handles = {key:p.open('w') for key,p in coarse_paths.items()}
                try:
                    with (coarse/'result.paf.tmp').open() as f:
                        for line in f:
                            if not line.strip() or line.startswith('#'): continue
                            key = line.split('\t',1)[0]
                            if key not in handles: raise ValueError('unknown coarse query')
                            handles[key].write(line)
                finally:
                    for f in handles.values(): f.close()
                for q in queries:
                    chain_work(coarse_paths[q.window_id],q,{w.window_id:w.length for w in targets},CigarWorkPolicy())
                (coarse/'result.paf.tmp').rename(coarse/'result.paf'); coarse_seconds = time.monotonic()-ct
            exact = dest/'exact'; exact.mkdir()
            _execute(root, exact, context, rel, None, queries[0], targets,
                     filtered_argv(first['argv'],target,query,filtered=mode=='batched_f005'), first['tool'],4*GIB)
            path = exact/'result.paf.tmp'; qlengths = {w.window_id:w.length for w in queries}; tlengths = {w.window_id:w.length for w in targets}
            # Validate ALL rows, including extra hits outside original pair scopes.
            for _ in read_paf(path,query_lengths=qlengths,target_lengths=tlengths): pass
            per_case = {i:dest/f'case-{i}.paf' for i in indices}; handles = {i:p.open('w') for i,p in per_case.items()}
            owners = {cases[i]['query'].window_id:i for i in indices}
            try:
                with path.open() as f:
                    for line in f:
                        if not line.strip() or line.startswith('#'): continue
                        row = line.split('\t'); i = owners[row[0]]
                        if row[5] in cases[i]['lengths']: handles[i].write(line)
            finally:
                for f in handles.values(): f.close()
            result = []
            for i,p in per_case.items():
                sha = digest(p)
                if mode == 'legacy' and sha != cases[i]['rawsha']: raise ValueError('legacy exact differs from historical')
                quality = interval_quality(p,cases[i],read_paf)
                result.append({'ordinal':i,'sha256':sha,'quality':quality})
            path.rename(exact/'result.paf')
            return {'batch':ordinal,'ordinals':indices,'seconds':time.monotonic()-begin_case,'coarse_seconds':coarse_seconds,'results':result}
        jobs = cases if mode == 'legacy' else prepared
        batches, order = dispatch(jobs,run,7,'completed'); elapsed = time.monotonic()-begin
        results = sorted([r for b in batches for r in b['results']],key=lambda r:r['ordinal'])
        if [r['ordinal'] for r in results] != list(range(len(cases))): raise ValueError('case inventory changed')
        phases.append({'phase':phase,'mode':mode,'seconds':elapsed,'native_batches':len(batches),'batches':batches,'results':results,'completion_order':order})
        print(json.dumps({'phase':phase,'mode':mode,'seconds':elapsed,'native_batches':len(batches)}),flush=True)
    for left,right in [(0,5),(1,4),(2,3)]:
        if [r['sha256'] for r in phases[left]['results']] != [r['sha256'] for r in phases[right]['results']]: raise ValueError('within-mode output is not deterministic')
    quality = {}
    for mode,index in [('batched',1),('batched_f005',2)]:
        comparisons = []
        for old,new in zip(phases[0]['results'],phases[index]['results']):
            before=old['quality'];after=new['quality']
            comparisons.append({'ordinal':old['ordinal'],'old':before['bases'],'candidate':after['bases'],
                'lost':{k:difference_bases(before['intervals'][k],after['intervals'][k]) for k in ('intra','cross')},
                'gained':{k:difference_bases(after['intervals'][k],before['intervals'][k]) for k in ('intra','cross')}})
        quality[mode]={'comparisons':comparisons,'lost_old_paired_core_bases':{k:sum(r['lost'][k] for r in comparisons) for k in ('intra','cross')},
            'old_paired_core_bases':{k:sum(r['old'][k] for r in comparisons) for k in ('intra','cross')}}
    legacy=sum(p['seconds'] for p in phases if p['mode']=='legacy')
    report={'status':'native_batched_search_pilot_completed_NOT_production_acceptance','hostname':socket.gethostname(),'cases':len(cases),'threads':16,'mappers':7,'mapper_AS_bytes':4*GIB,
        'batch_size_cap':4,'target_base_cap':100000000,'batch_input_preparation_seconds':prep_seconds,'input_bytes_verified':input_bytes,'phases':phases,'quality':quality,
        'legacy_over_candidate_time':{m:legacy/sum(p['seconds'] for p in phases if p['mode']==m) for m in quality},
        'historical_full_exact_stdout_all_equal':True,'main_workspace_modified':False,'production_strategy_enabled':False,'seconds':time.monotonic()-started,
        'limitations':['64 previously completed bounded anchors, not held-out or whole-queue acceptance.',
          'Batched targets change seed/index context and extra hits are filtered to each original target inventory; not output equivalent.',
          'Per-query historical CIGAR profile choices are frozen; batching coarse-to-policy admission is not implemented.',
          'Common input reconstruction excluded; batch union preparation separately timed and must be charged for production estimates.',
          'No planning/catalog/large-owner-heap/final assembly measured. f0.005 is an explicit scientific approximation in this diagnostic only.']}
    (out/'summary.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'phase':'completed','seconds':report['seconds'],'speedups':report['legacy_over_candidate_time'],'quality':{k:v['lost_old_paired_core_bases'] for k,v in quality.items()}}),flush=True)


if __name__ == '__main__': main()
