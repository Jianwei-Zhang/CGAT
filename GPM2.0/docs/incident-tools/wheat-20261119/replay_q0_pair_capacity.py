"""Measure a two-axis sequence-capacity gate on a frozen Q0 graph; no publication or mapper."""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryFile
from types import SimpleNamespace

from lgz_core import q0_admission as admission, q0_preparation as prep
from lgz_core.q0_frontier_scope import window_touches_frontier
from probe_q0_decision_frontier import compare, projected_task, subset_input
from replay_q0_draft_requests import challenge_unlocalized, cut_questions, with_omissions
from replay_q0_reverse_parents import alternatives, has_unsearched_context, load_panel


def extract(data, w):
    p = data.parts[w.segment_id]
    if w.segment_length != p.interval.length or not 0 <= w.start < w.end <= p.interval.length:
        raise ValueError('invalid source-coordinate frame')
    s = data.sources[p.source][p.interval.start+w.start:p.interval.start+w.end]
    if len(s) != w.end-w.start:
        raise ValueError('missing source bases')
    return s.upper().encode('ascii')


def capacities(binary, data, windows):
    pairs = {}
    # Only bound source bytes go into the filter, never mapper outputs, path IDs or full-graph decisions.
    with TemporaryFile() as out:
        with subprocess.Popen([binary], stdin=subprocess.PIPE, stdout=out) as p:
            try:
                for key,(q,ts) in windows.items():
                    p.stdin.write(b'Q\t'+extract(data,q)+b'\n')
                    for t in ts:
                        pk = key, t.window_id
                        if pk in pairs:
                            raise ValueError('duplicate window target')
                        pairs[pk] = None
                        p.stdin.write(b'T\t'+extract(data,t)+b'\n')
                p.stdin.close()
                if p.wait() != 0:
                    raise ValueError('capacity screen failed')
            except BaseException:
                p.kill(); raise
        out.seek(0)
        for pk in pairs:
            status = out.readline().strip().decode('ascii')
            if status not in {'possible','uncertain','short','excluded'}:
                raise ValueError('incomplete screen')
            pairs[pk] = status
        if out.read(1): raise ValueError('trailing screen results')
    return pairs


def audit(root, panel, binary, manifest_sha):
    manifest = root/prep.MANIFEST
    if sha256(manifest.read_bytes()).hexdigest() != manifest_sha: raise ValueError('archive mismatch')
    ready = prep.load_verified_evidence(root); data = load_panel(root,panel,ready)
    outputs = {r['path']:r for r in ready['outputs']}
    windows, native, raw = {},set(),{}
    for task in data.catalog['supplementary_alignments']:
        key = task['paf']
        if key in windows or key in native: raise ValueError('duplicate task')
        if task['kind']!='regional_discovery': native.add(key);continue
        rel=task['receipt']
        if prep.identity(root,rel)!=outputs[rel]: raise ValueError('unbound projection')
        spec=prep.json_file(prep.artifact_path(root,rel))['spec']
        raw[key]=projected_task(task,spec,data.parts,{})['raw']
        windows[key]=SimpleNamespace(**spec['query']),tuple(SimpleNamespace(**t) for t in spec['targets'])
    # Create the base view before planning. A pair key is an opaque project + input target ID.
    base=subset_input(data,set()); screened=capacities(binary,base,windows)
    edges={(k,t.window_id):(q,(t,)) for k,(q,ts) in windows.items() for t in ts}
    kept=set(); arm=base; rounds=[]
    for n in range(4):
        sel=admission.select_q0_paths(arm); demand=cut_questions(arm,sel)
        if demand is None or n==3:
            asks=set(windows); need=set(edges); admitted=need
        else:
            need=challenge_unlocalized(edges,arm.parts,sel.admission.placements)
            need.update(pk for pk,(q,ts) in edges.items() if window_touches_frontier(q,ts,arm.parts,demand))
            admitted={pk for pk in need if screened[pk] in ('possible','uncertain')}
            asks={k for k,_ in admitted}
        rounds.append({'demand_pairs':len(need),'capable_pairs':len(admitted),
                       'requested_windows':len(asks-kept),'no_path_or_budget_full_fallback':demand is None or n==3,
                       'geometry_windows':len({k for k,_ in need}),
                       'request_digest':sha256(json.dumps(sorted(asks-kept)).encode()).hexdigest()})
        if n and not asks-kept: break
        kept.update(asks); arm=subset_input(data,kept|native)
        if len(kept)==len(windows): break
    # Freeze selection before reading any full-arm result. Never apply the pair mask to retained target inventories.
    chosen=admission.construct_q0(arm)
    guard='reject_unsearched_context' if has_unsearched_context(with_omissions(arm,windows,kept),chosen) else 'passed'
    full=admission.construct_q0(data)
    high=set(); weak=set(); high_rows=0; misses=[]
    for l in data.pair_links:
        h=l.hit
        if h.artifact not in windows: continue
        tags=[v[5:] for v in h.tags if v.startswith('tw:Z:')]
        if len(tags)!=1 or (h.artifact,tags[0]) not in edges: raise ValueError('unbound observed pair')
        pk=h.artifact,tags[0]
        if 20*h.matches>=19*h.block_length and sum(k for k,op in h.cigar if op in 'M=')>=100:
            high.add(pk); high_rows+=1
            if screened[pk] not in ('possible','uncertain'): misses.append(h.evidence_id)
        else: weak.add(pk)
    if prep.load_verified_evidence(root)!=ready or sha256(manifest.read_bytes()).hexdigest()!=manifest_sha:
        raise ValueError('changed archive')
    a,b=alternatives(full),alternatives(chosen)
    excluded={pk for pk,v in screened.items() if v in ('short','excluded')}
    possible_tasks={k for k,_ in set(edges)-excluded}
    return {'schema':'q0_pair_capacity_control_v1','ready':data.ready_manifest_identity,'panel':panel['panel'],
            'raw_full':len(set(raw.values())),'raw_requested':len({raw[k] for k in kept}),
            'native_retained':len(native),'regional':len(windows),'requested':len(kept),'rounds':rounds,
            'pair_count':len(edges),'screen':dict(Counter(screened.values())),
            'whole_windows_with_no_capable_pair':len(set(windows)-possible_tasks),'eligible_observed_rows':high_rows,
            'eligible_observed_pairs':len(high),'false_exclusions_of_observed_eligible_rows':len(misses),
            'weak_observed_pairs_among_sequence_exclusions':len(weak & excluded),
            'guard':guard,'new_mapper_executions':0,'fixed_task_graph':True,'comparison':compare(full,chosen),
            'alternative_geometry':{c:{'lost':len(a[c]-b[c]),'new':len(b[c]-a[c])} for c in a}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','panel','out'): p.add_argument(name,type=Path)
    p.add_argument('--binary',required=True,type=Path); p.add_argument('--manifest-sha',required=True);p.add_argument('--panel-sha',required=True)
    a=p.parse_args();root=a.root.resolve(strict=True);raw=a.panel.read_bytes()
    if sha256(raw).hexdigest()!=a.panel_sha or a.out.exists() or a.out.resolve().is_relative_to(root): raise ValueError('output or panel identity')
    r=audit(root,json.loads(raw),a.binary.resolve(strict=True),a.manifest_sha)
    with a.out.open('x') as f: json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
