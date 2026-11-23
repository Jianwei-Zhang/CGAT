"""Can known geometry explain draft requests? Fixed graph; no claims of unique sequence mapping."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from lgz_core import q0_preparation as prep, q0_admission as admission
from lgz_core.q0_sources import Interval
from lgz_core.q0_frontier_scope import window_touches_frontier
from audit_q0_window_use import classify
from probe_q0_decision_frontier import compare, projected_task, subset_input
from replay_q0_draft_requests import challenge_unlocalized, cut_questions, with_omissions
from replay_q0_reverse_parents import alternatives, has_unsearched_context, load_panel
from q0_locus_geometry import LocusIndex, Ranges


def known_index(visible, queries):
    idx=LocusIndex()
    for l in visible.pair_links:
        h=l.hit; q,t=l.query_source,l.target_source
        if (q not in queries and t not in queries) or 20*h.matches<19*h.block_length or sum(n for n,op in h.cigar if op in 'M=')<100:continue
        for a,b in l.source_blocks():
            if q in queries: idx.add(q,t,a,b,h.strand)
            if t in queries: idx.add(t,q,b,a,h.strand)
    idx.seal();return idx


def explained(idx,q,t,cores,target):
    """A single previously observed signed map covers every core *in this target*.

    Other observed maps here abstain. Even a unique known map need not be
    unique in the sequences: this hypothesis is subjected to a held-out PAF check.
    """
    if q==t or not cores:return False
    best=False; competitors=0
    for (strand,c),rows in idx.rows.get((q,t),{}).items():
        lo,hi=(target.start-c,target.end-c) if strand=='+' else (c-target.end,c-target.start)
        all_covered=True; any_overlap=False
        for core in cores:
            a,b=max(lo,core.start),min(hi,core.end)
            if a>=b:
                all_covered=False;continue
            clip=Interval(a,b)
            if next(rows.intersect(clip),None) is not None:any_overlap=True
            if clip!=core or next(rows.gaps(clip),None) is not None: all_covered=False
        competitors+=int(any_overlap);best|=all_covered
        if competitors>1:return False
    return bool(best and competitors==1)


def task_inputs(root,data,ready):
    outputs={r['path']:r for r in ready['outputs']}; windows={};native=set()
    for task in data.catalog['supplementary_alignments']:
        k=task['paf']
        if k in windows or k in native:raise ValueError('duplicate task')
        if task['kind']!='regional_discovery':native.add(k);continue
        rel=task['receipt']
        if prep.identity(root,rel)!=outputs[rel]:raise ValueError('unbound projection')
        spec=prep.json_file(prep.artifact_path(root,rel))['spec'];projected_task(task,spec,data.parts,{})
        windows[k]=SimpleNamespace(**spec['query']),tuple(SimpleNamespace(**t) for t in spec['targets'])
    return windows,native


def coords(data,q,t):
    a,b=data.parts[q.segment_id],data.parts[t.segment_id]
    return (a.source,b.source,tuple(Interval(a.interval.start+s,a.interval.start+e) for s,e in q.cores),
            Interval(b.interval.start+t.start,b.interval.start+t.end))


def run(root,panel,msha):
    manifest=root/prep.MANIFEST
    if sha256(manifest.read_bytes()).hexdigest()!=msha:raise ValueError('wrong full archive')
    ready=prep.load_verified_evidence(root); data=load_panel(root,panel,ready); windows,native=task_inputs(root,data,ready)
    edges={(k,t.window_id):(q,(t,)) for k,(q,ts) in windows.items() for t in ts}
    frames={pk:coords(data,q,ts[0]) for pk,(q,ts) in edges.items()}
    queries={f[0] for f in frames.values()}; base=subset_input(data,set()); prior=known_index(base,queries)
    before={pk for pk,frame in frames.items() if explained(prior,*frame)}  # before exposing any supplementary output
    kept=set();rounds=[];arm=base
    for i in range(4):
        selection=admission.select_q0_paths(arm);demand=cut_questions(arm,selection)
        if demand is None or i==3: need=set(edges);requests=set(windows);skipped=set()
        else:
            need=challenge_unlocalized(edges,arm.parts,selection.admission.placements)
            need.update(pk for pk,(q,ts) in edges.items() if window_touches_frontier(q,ts,arm.parts,demand))
            skipped=before & need; requests={k for k,_ in need-skipped}
        rounds.append({'need_pairs':len(need),'previously_explained_pairs':len(skipped),'new_windows':len(requests-kept),
                       'full_fallback':demand is None or i==3})
        if i and not requests-kept:break
        kept.update(requests);arm=subset_input(data,kept|native)
        if len(kept)==len(windows):break
    chosen=admission.construct_q0(arm);guard='reject_unsearched_context' if has_unsearched_context(with_omissions(arm,windows,kept),chosen) else 'passed'
    # Only now inspect the full results. Separate single-base changes from continuous 100-bp changes within a query core.
    full=admission.construct_q0(data);direct,_,_=classify(full,data.pair_links,windows)
    checked={k:Ranges(next(frames[k,t.window_id][2] for t in ts)) for k,(q,ts) in windows.items()}
    native_index=known_index(subset_input(data,native),queries)
    high=set();novel1=set();novel100=set();residual100=set();counterexamples=set();forms=Counter()
    for l in data.pair_links:
        h=l.hit;k=h.artifact
        if k not in windows or 20*h.matches<19*h.block_length or sum(n for n,op in h.cigar if op in 'M=')<100:continue
        target,=[v[5:] for v in h.tags if v.startswith('tw:Z:')];pk=k,target
        if (l.query_source,l.target_source)!=frames[pk][:2]:raise ValueError('wrong projected source pair')
        high.add(k);core=checked[k]
        for a,b in l.source_blocks():
            def find(idx,n): return idx.novel(l.query_source,l.target_source,a,b,h.strand,core,n)
            if k not in novel1 and find(prior,1):novel1.add(k)
            if (k not in novel100 or (pk in before and pk not in counterexamples)) and (reason:=find(prior,100)):
                if k not in novel100: forms[reason]+=1;novel100.add(k)
                if pk in before:counterexamples.add(pk)
            if k not in residual100 and find(native_index,100):residual100.add(k)
    a,b=alternatives(full),alternatives(chosen)
    if prep.load_verified_evidence(root)!=ready or sha256(manifest.read_bytes()).hexdigest()!=msha:raise ValueError('archive changed')
    return {'schema':'q0_signed_locus_blind_control_v1','panel':panel['panel'],'ready':data.ready_manifest_identity,
            'window_count':len(windows),'pair_count':len(edges),'kept':len(kept),'native':len(native),'rounds':rounds,
            'eligible_windows':len(high),'novel_1bp_in_core_windows':len(novel1),'novel_100bp_in_core_windows':len(novel100),
            'first_novel_100bp_categories':dict(forms),'novel_100bp_after_native':len(residual100),
            'directly_cited_windows':len(direct),'cited_with_new_100bp':len(novel100&direct),
            'blind_explained_pairs':len(before),'explained_pairs_with_new_100bp':len(counterexamples),
            'guard':guard,'new_mapper_executions':0,'fixed_task_graph':True,'comparison':compare(full,chosen),
            'alternative_geometry':{c:{'lost':len(a[c]-b[c]),'new':len(b[c]-a[c])} for c in a}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','panel','out'):p.add_argument(n,type=Path)
    p.add_argument('--panel-sha',required=True);p.add_argument('--manifest-sha',required=True);a=p.parse_args();root=a.root.resolve(strict=True);out=a.out.resolve();raw=a.panel.read_bytes()
    if out.exists() or out.is_relative_to(root) or sha256(raw).hexdigest()!=a.panel_sha:raise ValueError('output or panel identity')
    r=run(root,json.loads(raw),a.manifest_sha)
    with out.open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
