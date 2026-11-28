"""Couple isolated local-chain admission to actual 1A selection and exact gates.

Only consumes successful diagnostic artifacts plus existing completed PAFs.
Keeps original admitted placements and adds independently screened candidates;
this is an incremental counterfactual, not a full rerun of admission propagation.
"""
import argparse,gzip,json,pickle,subprocess
from bisect import bisect_right
from collections import defaultdict,Counter
from pathlib import Path
from hashlib import sha256
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_paths as paths
from lgz_core.q0_sources import Interval
from wheat_selection_checkpoint import encode,decode
from wheat_single_group_replay_readonly import need,footprint
from wheat_group_evidence_readonly import load_links
from wheat_reference_funnel_readonly import digest,write


def link_identity(link):return (link.hit.evidence_id,link.query_source,link.target_source,link.query_offset,link.target_offset)


def reference_spine(graph):
    """Weighted interval-scheduling proposal followed by ORIGINAL exact gates.

    Full placement hulls must be reference ordered. The weight is source length,
    the original primary score before overlap cuts/equivalence. A rejected full
    proposal falls back to exact-gated prefix construction, recording all skips.
    This is a bounded alternative proposal, not a global optimum claim.
    """
    rows=sorted((p for p in graph.placements.values() if p.reference_intervals),key=lambda p:(max(i.end for i in p.reference_intervals),min(i.start for i in p.reference_intervals),p.placement_id))
    ends=[max(v.end for v in p.reference_intervals) for p in rows];dp=[(0,0)];back=[];take=[]
    for i,p in enumerate(rows):
        j=bisect_right(ends,min(v.start for v in p.reference_intervals),0,i);value=(dp[j][0]+p.interval.length,dp[j][1]-1);chosen=value>dp[-1];dp.append(value if chosen else dp[-1]);back.append(j);take.append(chosen)
    chosen=[];i=len(rows)
    while i:
        if take[i-1]:chosen.append(rows[i-1].placement_id);i=back[i-1]
        else:i-=1
    nodes=tuple(reversed(chosen));joins=[];missing_edge=False
    for a,b in zip(nodes,nodes[1:]):
        variants=graph.joins(a,b)
        if not variants:missing_edge=True;break
        joins.append(next((j for j in variants if j.kind=='reference_unknown'),variants[0]))
    candidate=None if missing_edge else graph._score_candidate(nodes,tuple(joins));full_valid=candidate is not None;skipped=Counter();evaluations=1
    if candidate is None:
        current=None
        for node in nodes:
            options=[]
            if current is None:
                evaluations+=1;path=graph._score_candidate((node,),())
                if path is not None:options.append(path)
            else:
                variants=graph.joins(current.nodes[-1],node)
                if not variants:skipped['no_legal_join']+=1;continue
                for join in variants:
                    evaluations+=1;path=graph._score_candidate(current.nodes+(node,),current.joins+(join,))
                    if path is not None:options.append(path)
            if options:current=min(options,key=graph.rank)
            else:skipped['exact_score_or_duplicate_gate']+=1
        candidate=current
    return candidate,{'proposal_nodes':len(nodes),'proposal_source_length_weight':dp[-1][0],'full_proposal_passed':full_valid,'score_calls':evaluations,'fallback_skips':dict(skipped)}


def checked_pickle(path,pin):
    raw=path.read_bytes();need(sha256(raw).hexdigest()==pin,'diagnostic pickle identity differs')
    # Only our private owner (0700) artifacts whose SHA was saved by the successful
    # producer job are accepted, never an arbitrary external/customer pickle.
    return pickle.loads(raw)


def run(base,owner,modes):
    start=monotonic();admission=json.loads((owner/'local-admission.json').read_text());blocked=json.loads((owner/'blockers.json').read_text());need(admission['group']=='1A' and admission['reference_coverage_bp']['frozen']==129162948,'wrong admission receipt');need(blocked['baseline_full_path_equal'] and blocked['no_reference_order_slot']==200,'wrong blocker baseline')
    frozen=checked_pickle(owner/'frozen-1A-graph.pickle',blocked['graph_pickle_sha256']);baseline=decode(json.loads((owner/'baseline-path.json').read_text()));need(json.loads(json.dumps(footprint(baseline,frozen.placements)))==blocked['baseline_metrics'],'baseline path changed')
    candidates={}
    for mode in modes:
        name=mode+'-placements.jsonl.gz';need(digest(owner/name)==admission['outputs'][name]['sha256'],'admission candidates changed')
        with gzip.open(owner/name,'rt') as f:rows=[decode(json.loads(s)) for s in f]
        need(len(rows)==admission['placement_counts'][mode] and len({p.placement_id for p in rows})==len(rows),'candidate count/identity differs');candidates[mode]=sorted(rows,key=lambda p:(p.source,p.interval,p.orientation,p.placement_id))
    sources={p.source for p in frozen.placements.values()}|{p.source for rows in candidates.values() for p in rows};binding={'producer_tools_sha256':'19cebdc7667d912f6d3ace4a59783d3e49fbb02e668ff5f5efbb50c618c27ad2','local_admission_sha256':digest(owner/'local-admission.json'),'sources':[[s.dataset,s.contig] for s in sorted(sources)]}
    mode_key='-'.join(modes);seal=owner/('expanded-links-'+mode_key+'.json');cache=owner/('expanded-links-'+mode_key+'.pickle')
    if seal.exists():
        saved=json.loads(seal.read_text());need(saved['binding']==binding,'expanded evidence binding changed');links=checked_pickle(cache,saved['sha256']);print('EXPANDED_LINKS_REUSED',len(links),flush=True)
    else:
        links=load_links(base,owner,sources);raw=pickle.dumps(links,protocol=5);cache.write_bytes(raw);write(seal,{'binding':binding,'sha256':sha256(raw).hexdigest(),'count':len(links)});print('EXPANDED_LINKS_READY',len(links),round(monotonic()-start,1),flush=True)
    old_sources={p.source for p in frozen.placements.values()};old_pairs={k:[link_identity(v) for v in rows] for k,rows in frozen.links.items() if rows};new_pairs=defaultdict(list)
    for link in links:
        if link.query_source in old_sources and link.target_source in old_sources and link.hit.matches/link.hit.block_length>=frozen.policy.minimum_pair_identity:new_pairs[tuple(sorted((link.query_source,link.target_source)))].append(link_identity(link))
    need(old_pairs==dict(new_pairs),'expanded evidence lost/reordered frozen baseline links')
    del new_pairs,old_pairs
    results={}
    for mode,extra in candidates.items():
        admitted=list(frozen.placements.values())+extra;need(len({p.placement_id for p in admitted})==len(admitted),'old/new placement collision');member_sources={p.source for p in admitted};selected_links=[l for l in links if l.query_source in member_sources and l.target_source in member_sources]
        print('CANDIDATE_GRAPH_START',mode,len(admitted),len(selected_links),round(monotonic()-start,1),flush=True)
        graph=paths.PathGraph(admitted,selected_links,(),paths.PathPolicy(),first_request=True,progress=lambda s:print(mode,'GRAPH',s,flush=True));mode_result={'admitted_count':len(admitted),'extra_count':len(extra),'input_source_count':len(member_sources),'pair_links':len(selected_links),'searches':{}}
        for name in ('original_search','reference_spine'):
            at=monotonic();messages=[]
            def log(s):messages.append(s);print(mode,name,s,flush=True)
            if name=='original_search':result=paths._search_paths(graph,progress=log).path;diagnostics={'logs':messages}
            else:result,diagnostics=reference_spine(graph)
            need(result is not None,'empty selected path');represented,duplicates,_=graph.coverage.assess((s.source,s.interval) for s in result.slices);need(not duplicates and represented==result.score[0],'candidate exact gate failed')
            met=footprint(result,graph.placements);met['net_reference_bp_vs_frozen']=met['reference_union_bp']-blocked['baseline_metrics']['reference_union_bp'];met['net_source_bp_vs_frozen']=met['source_bp']-blocked['baseline_metrics']['source_bp'];kinds=Counter(graph.placements[s.placement_id].localization_kind for s in result.slices)
            file=owner/(mode+'-'+name+'-path.json.gz')
            with gzip.open(file,'wt',compresslevel=1) as f:json.dump(encode(result),f)
            mode_result['searches'][name]={'metrics':met,'seconds':monotonic()-at,'selected_localization_kinds':dict(kinds),'diagnostics':diagnostics,'full_coverage_gate_passed':True,'path_file':file.name,'path_sha256':digest(file)}
            print('CANDIDATE_SEARCH_DONE',mode,name,json.dumps(met),flush=True);write(owner/('candidate-selection-'+mode_key+'-progress.json'),{'current_mode':mode,'results':results,'current':mode_result,'elapsed_s':monotonic()-start})
        results[mode]=mode_result;del graph,selected_links
    report={'schema':'wheat_local_chain_to_selection_diagnostic_v1','group':'1A','modes':list(modes),'baseline_metrics':blocked['baseline_metrics'],'frozen_pair_order_preserved':True,'input_binding':binding,'results':results,'elapsed_s':monotonic()-start,'mapper_calls':0,'formal_workspace_modified':False,'limitations':['Frozen admission is preserved and augmented; this is not a full rerun of the downstream admission propagation algorithm.','All comparisons use actual existing pair PAF rows; no mapper, no fabricated overlap cut.','The interval-scheduling proposal is a diagnostic alternative with original exact gates, not a proven global optimum.','Graph caches are reused within a mode; timings do not establish controlled speedup.','Candidate source order is frozen original order followed by source/interval/orientation/id sorted added placements.','Zero cross-group anchor overlap does not establish biological subgenome truth.','Full formal Q0-LGZ remains held regardless of these diagnostic results.']}
    write(owner/('candidate-selection-'+mode_key+'.json'),report);print('CANDIDATE_SELECTION_DONE',round(monotonic()-start,1),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);p.add_argument('--mode',choices=('dominant90','regional','both'),default='dominant90');a=p.parse_args();need(a.owner.resolve().parent==a.base.resolve() and a.owner.name.startswith('q0-local-chain-'),'private diagnostic owner required');need(a.owner.stat().st_mode&0o077==0,'owner must not be group/world writable or readable')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external command forbidden in diagnostic selection')):run(a.base.resolve(),a.owner.resolve(),('dominant90','regional') if a.mode=='both' else (a.mode,))
