"""Cold blinded draft-threshold vs full Q0 on a preregistered natural panel. No production ready output."""
import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
from pathlib import Path
import shutil
from threading import Lock
from time import monotonic
from unittest.mock import patch

from lgz_core import q0_admission as adm, q0_preparation as prep, q0_regional_mapping as mapping
from lgz_core.common import read_fasta, stable_id
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.q0_frontier_scope import UnsearchedQ0Context, audit_selected_scope
from lgz_core.q0_sources import Q0EvidenceError
from audit_q0_draft_consumers import footprint, differences, source
from q0_threshold_questions import questions
from run_wheat_frontier_panel import base_input, digest, within


def construct(data):
    try:
        return adm.construct_q0(data)
    except Q0EvidenceError as exc:
        if str(exc) != 'no chromosome has a trustworthy q0 path':
            raise
        return None


def arm(panel, meta, data, assignments, desc, root, tool, threads, blind):
    start = monotonic(); before = None; stats = {}; frontier = None
    counts = Counter(); native = Counter(); lock = Lock()
    orig_execute, orig_run = mapping._execute, prep.subprocess.run

    def initial(path):
        if path != root:
            raise ValueError('unexpected input root')
        seen = ObservedSourcePairs({s: len(seq) for s, seq in data.sources.items()})
        for l in data.pair_links:
            seen.observe_alignment(l.hit, l.query_source, l.target_source)
        return data.sources, data.reference_lengths, assignments, {'minimap_preset':'asm10'}, sorted(meta['artifacts']), desc, seen

    def execute(path, directory, *args, **kwargs):
        v = orig_execute(path, directory, *args, **kwargs)
        with lock:
            counts['coarse' if directory.name == 'chaining' else 'regional_exact'] += 1
        return v

    def run(args, *pos, **kw):
        v = orig_run(args, *pos, **kw)
        if isinstance(args, list) and args[0] == str(tool) and '-o' in args and kw.get('cwd') is not None and v.returncode == 0:
            native['native'] += 1
        return v

    if blind:
        before = construct(data); frontier, stats = questions(data, before, assignments)
    def report():
        return {'wall_seconds':monotonic()-start, 'fresh_mapper_processes':{**counts, **native}, 'initial_questions':stats,
                'requested_sources':None if frontier is None else len(frontier),
                'request_digest':None if frontier is None else stable_id('q0-threshold-request', [
                    [asdict(s), [asdict(i) for i in iv]] for s, iv in sorted(frontier.items())])}
    if blind and frontier == {}:
        return before, {**report(), 'route':'base_stop_no_planner', 'regional_tasks':0, 'native_tasks':0,
                        'publication':'draft_only', 'unsearched_guard':'not_checked_no_regional_inventory'}
    for rel, sha in meta['artifacts'].items():
        dst = root/rel; dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(within(panel, rel), dst)
        if digest(dst) != sha:
            raise ValueError('panel changed while copying')
    mode = 'decision_frontier' if frontier is not None else 'full'
    with (patch.object(prep, '_initial_inputs', initial), patch.object(mapping, '_execute', execute),
          patch.object(prep.subprocess, 'run', run)):
        receipt, routed, cached = prep._prepare_evidence_pass(root, threads=threads, minimap2=str(tool),
                                    supplement_scope=mode, draft=True, frontier_override=frontier)
    if cached or routed != frontier or (root/prep.MANIFEST).exists():
        raise ValueError('not a fresh private draft or wrong routing')
    with patch.object(adm, 'read_fasta', lambda p: ([(c, range(n)) for c,n in data.reference_lengths.items()]
                                                   if p == root/'reference-lengths.json' else read_fasta(p))):
        observed = adm.load_evidence_input(root, _draft=receipt)
    tasks = observed.catalog['supplementary_alignments']; regional = sum(t['kind']=='regional_discovery' for t in tasks)
    if len({t['receipt'] for t in tasks if t['kind'] != 'regional_discovery'}) != native['native']:
        raise ValueError('fresh native mapper count differs from tasks on empty scratch')
    # Use only the observed hits to reconstruct a *draft*, never a public ready artifact.
    result = construct(replace(observed, catalog={}, ready_manifest_identity='')) if blind else construct(observed)
    gate = 'full' if mode == 'full' else 'no_path'
    if mode != 'full' and result is not None:
        try:
            audit_selected_scope(observed, result.admission, result.paths)
        except UnsearchedQ0Context:
            gate = 'reject_unsearched_context'
        else:
            gate = 'passed'
    return result, {**report(), 'regional_tasks':regional, 'native_tasks':len(tasks)-regional, 'route':mode,
                    'publication':'private_only', 'unsearched_guard':gate}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('panel', 'scratch', 'tool', 'out'):
        p.add_argument(n, type=Path)
    for n in ('panel-sha', 'tool-sha'):
        p.add_argument('--'+n, required=True)
    p.add_argument('--threads', type=int, choices=(2, 4, 6), required=True); a=p.parse_args()
    panel=a.panel.resolve(strict=True); tool=a.tool.resolve(strict=True); scratch=a.scratch.resolve(); out=a.out.resolve()
    if (scratch.exists() or not scratch.is_relative_to('/tmp') or scratch.is_relative_to(panel) or panel.is_relative_to(scratch)
            or out.exists() or out.is_relative_to(panel) or out.is_relative_to(scratch) or digest(tool)!=a.tool_sha
            or digest(panel/'panel.json')!=a.panel_sha):
        raise ValueError('invalid frozen inputs, scratch or report path')
    meta=json.loads((panel/'panel.json').read_text())
    if meta['panel']!=panel.name or any(digest(within(panel,k))!=v for k,v in meta['artifacts'].items()):
        raise ValueError('invalid panel identity')
    start=monotonic(); data,assignments,desc=base_input(panel, meta); common=monotonic()-start
    scratch.mkdir(mode=0o700)
    report={'panel':meta['panel'], 'panel_sha256':a.panel_sha, 'mapper_sha256':a.tool_sha, 'threads':a.threads,
            'common_input_seconds':common, 'builder':prep.builder_identity(), 'selector':adm.selector_identity(),
            'schema':'q0_cold_draft_threshold_holdout_v1', 'order':['draft','full']}
    geo={}; seqs={source(s):seq for s,seq in data.sources.items()}
    for name in ('draft','full'):
        built,report[name]=arm(panel,meta,data,assignments,desc,scratch/name,tool,a.threads,name=='draft')
        geo[name]=footprint(built,seqs) if built is not None else None
        report[name]['sequences']=len(built.records) if built is not None else 0
        print('ARM',name,json.dumps(report[name],sort_keys=True),flush=True)
    report['fields']=differences(geo['draft'],geo['full']) if all(v is not None for v in geo.values()) else None
    if digest(tool)!=a.tool_sha or digest(panel/'panel.json')!=a.panel_sha:
        raise ValueError('binding drift during experiment')
    with out.open('x') as f:
        json.dump(report,f,sort_keys=True,indent=2);f.write('\n')


if __name__ == '__main__':
    main()
