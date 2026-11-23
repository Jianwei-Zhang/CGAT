"""Bounded, content-verified original window reconstruction for a disjoint cohort.

Only 24 explicitly predeclared completed windows, including slow, short, empty,
long-parent and both assemblies. No complete source genome is loaded. Every
reconstructed FASTA must match the original native input bytes; no production
result is changed or adopted. These windows were in the earlier static probe,
so they are disjoint from native tuning anchors, not an unseen genome dataset.
"""
import csv
from pathlib import Path
from benchmark_regional_mapper_dispatch import digest, read_json, within, window_bytes, GIB

ORDINALS = tuple(range(64,84)) + (90,100,105,119)


def signature(path):
    st=path.stat();return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)


def select_rows(static, anchors):
    by_id={r['ordinal']:r for r in static['rows']}
    if len(by_id) != len(static['rows']) or any(i not in by_id for i in ORDINALS):
        raise ValueError('invalid expanded cohort inventory')
    rows=[by_id[i] for i in ORDINALS]
    if len({r['raw_receipt'] for r in rows}) != 24 or any(r['anchor_case'] or r['raw_receipt'] in anchors for r in rows):
        raise ValueError('expanded cohort must exclude every native tuning anchor')
    if sum(r['legacy_target_bases'] for r in rows)>1024**3:
        raise ValueError('expanded target volume exceeds 1GiB')
    return rows


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
    static = read_json(a.quality_report); lookup = read_json(a.lookup); trace = read_json(a.trace)
    anchors = {r['raw_receipt'] for r in read_json(a.anchor_report)['cases']}
    selected = select_rows(static, anchors)
    anchor = {'cases':[{'raw_receipt':r['raw_receipt'],'receipt_sha256':r['raw_receipt_sha256'],'paf_sha256':r['raw_paf_sha256']} for r in selected]}
    projects = {r['raw_receipt']:{'query':r['query']} for r in selected}
    tables = list(csv.DictReader(within(work,'metadata/datasets.tsv').read_text().splitlines(),delimiter='\t'))
    paths = {r['dataset_name']:within(work,r['fasta_relpath']) for r in tables}
    signatures = {str(p):signature(p) for p in paths.values()}
    indices = {r['dataset_name']:{f[0]:tuple(map(int,f[1:5])) for f in
        (line.split('\t') for line in within(work,r['fai_relpath']).read_text().splitlines())} for r in tables}
    inputs.mkdir(exist_ok=False); cases = []; input_bytes = 0
    for row in anchor['cases']:
        rp = within(work, row['raw_receipt']); receipt = read_json(rp, 2*1024**2)
        if digest(rp) != row['receipt_sha256'] or receipt['status'] != 'success': raise ValueError('original raw changed')
        cp = within(work, receipt['spec']['context']['path'])
        if digest(cp) != receipt['spec']['context']['sha256']: raise ValueError('context changed')
        context = read_json(cp, 2*1024**2); spec = context['spec']; rel = str(cp.parent.relative_to(work))
        qrow = projects[row['raw_receipt']]['query']; query = QueryWindow(**{k: tuple(map(tuple, v)) if k == 'cores' else v for k,v in qrow.items() if k != 'window_id'})
        targets = [TargetWindow(**{k:v for k,v in r.items() if k != 'window_id'}) for r in spec['targets']]
        if query.window_id != spec['query']['window_id'] or any(w.window_id != r['window_id'] for w,r in zip(targets,spec['targets'])):
            raise ValueError('source window inventory changed')
        for key,sha in spec['members']:
            if lookup[key]['sequence_sha256'] != sha: raise ValueError('member sequence identity differs')
        def records(windows):
            for window in windows:
                member = lookup[window.segment_id]; ds = member['dataset']; name = member['contig']
                if member['length'] != window.segment_length: raise ValueError('source coordinate frame changed')
                yield window.window_id,window_bytes(paths[ds],indices[ds][name],window.start,window.end)
        for name,windows in [('query',[query]),('target',sorted(targets,key=lambda w:w.window_id))]:
            dest=inputs/rel/(name+'.fa');write_fasta(dest,records(windows))
            expected=next(r for r in context['inputs'] if r['path']==rel+'/'+name+'.fa')
            if dest.stat().st_size != expected['size'] or digest(dest) != expected['sha256']:
                raise ValueError('reconstructed FASTA differs from original native input')
            input_bytes += expected['size']
        if input_bytes > 1024**3: raise ValueError('held-out input reconstruction exceeds 1GiB')
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
    if len(cases) != 24: raise ValueError('expected 24 disjoint expanded cases')
    if any(signature(p) != signatures[str(p)] for p in paths.values()): raise ValueError('source FASTA changed during reconstruction')
    return cases, input_bytes

