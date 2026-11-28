"""Isolated complete direct-insertion classification of frozen 1A no-slot nodes.

Reuses the previously verified read-only graph loader and reproduces its frozen
winner before probes. Probes preserve existing joins/coverage gates; inability
to insert directly is not a proof that replacements or another path cannot work.
"""
import argparse
from collections import Counter
from dataclasses import replace
from hashlib import sha256
from itertools import product
import json,pickle,subprocess
from pathlib import Path
from time import monotonic
from unittest.mock import patch
import wheat_single_group_replay_readonly as replay
from wheat_local_chain_primitives import chain,trimmed_reference
from lgz_core.q0_sources import Interval,merged_intervals
from lgz_core import q0_admission as adm
from lgz_core import q0_paths as paths
from wheat_selection_checkpoint import encode


class Complete(Exception):pass


def slots(graph,path,p):
    return [i for i in range(len(path.nodes)+1) if (i==0 or graph.reference_order(graph.placements[path.nodes[i-1]],p)) and (i==len(path.nodes) or graph.reference_order(p,graph.placements[path.nodes[i]]))]


def alter(p,refs):
    return replace(p,reference_blocks=tuple(refs),reference_intervals=merged_intervals(a.reference for a in refs))


def evaluate_reason(graph,nodes,joins):
    used={};slices=[]
    for i,n in enumerate(nodes):
        p=graph.placements[n];lo=joins[i-1].right_start if i else 0;hi=joins[i].left_end if i<len(joins) else p.interval.length
        if lo>=hi:return 'crossed_or_empty_cuts',None
        iv=p.source_interval(Interval(lo,hi))
        if any(iv.intersection(v) for v in used.get(p.source,())):return 'same_source_overlap',None
        used.setdefault(p.source,[]).append(iv);slices.append((p.source,iv))
    result=graph._score_candidate(tuple(nodes),tuple(joins))
    if result is None:
        if graph.coverage.unique_selected_bp(slices) is not None:raise ValueError('unclassified score veto')
        return 'paired_equivalence_duplicate',None
    return 'valid',result


def analyse(graph,path,owner):
    began=monotonic();selected=set(path.nodes);omitted=[p for k,p in graph.placements.items() if k not in selected];no_slot=[p for p in omitted if p.reference_intervals and not slots(graph,path,p)]
    replay.need(len(omitted)==229 and len(no_slot)==200,'frozen 1A triage changed')
    raw=pickle.dumps(graph,protocol=5);(owner/'frozen-1A-graph.pickle').write_bytes(raw)
    graph_pin=sha256(raw).hexdigest();allrows=[];summary=Counter();ref_before=replay.footprint(path,graph.placements)['reference_union_bp']
    for ordinal,p in enumerate(no_slot,1):
        main=chain(p.reference_blocks,p.orientation);trim=trimmed_reference(p);c=Counter();best=None;best_index=None;raw_neighbors=qualified_neighbors=end_neighbors=0
        for key in path.nodes:
            neighbor=graph.placements[key]
            if graph.links.get(tuple(sorted((p.source,neighbor.source)))):raw_neighbors+=1
            for left,right in ((p,neighbor),(neighbor,p)):
                blocks=graph.homologous_blocks(left,right)
                if blocks:qualified_neighbors+=1
                if blocks and paths._end_spanning_evidence(blocks,left.interval.length):end_neighbors+=1
        for i in range(len(path.nodes)+1):
            left=graph.joins(path.nodes[i-1],p.placement_id) if i else (None,)
            right=graph.joins(p.placement_id,path.nodes[i]) if i<len(path.nodes) else (None,)
            if not left or not right:c['no_two_sided_join_slot']+=1;continue
            c['two_sided_join_slots']+=1
            for a,b in product(left,right):
                joins=list(path.joins[:max(0,i-1)])+[v for v in (a,b) if v is not None]+list(path.joins[i:]);nodes=path.nodes[:i]+(p.placement_id,)+path.nodes[i:]
                reason,candidate=evaluate_reason(graph,nodes,joins);c[reason]+=1
                if candidate is not None and (best is None or graph.rank(candidate)<graph.rank(best)):best=candidate;best_index=i
        if best is not None:primary='valid_score_improving' if best.score>path.score else 'valid_but_not_score_improving'
        elif not raw_neighbors:primary='no_pair_evidence_to_selected'
        elif not qualified_neighbors:primary='no_qualified_pair_blocks_to_selected'
        elif not end_neighbors:primary='no_end_spanning_pair_evidence'
        elif not c['two_sided_join_slots']:primary='no_two_sided_compatible_join_slot'
        elif c['paired_equivalence_duplicate']:primary='duplicate_veto_with_possible_other_cut_vetoes'
        elif c['same_source_overlap']:primary='same_source_overlap_veto'
        else:primary='crossed_or_empty_cut_veto'
        row={'placement_id':p.placement_id,'source':[p.source.dataset,p.source.contig],'source_bp':p.interval.length,'reference_bp':adm._size(p.reference_intervals),'reference_hull_bp':max(v.end for v in p.reference_intervals)-min(v.start for v in p.reference_intervals),'primary':primary,'probe_counts':dict(c),'raw_pair_neighbors':raw_neighbors,'qualified_directed_neighbors':qualified_neighbors,'end_spanning_directed_neighbors':end_neighbors,'max_chain_support_fraction':adm._size(a.source for a in main)/max(1,adm._size(a.source for a in p.reference_blocks)),'chain_reference_slots':len(slots(graph,path,alter(p,main))),'central_99pct_reference_slots':len(slots(graph,path,alter(p,trim)))}
        if best is not None:
            represented,duplicates,_=graph.coverage.assess((s.source,s.interval) for s in best.slices);replay.need(not duplicates and represented==best.score[0],'probe failed final gate');row['best_probe']={'index':best_index,'metrics':replay.footprint(best,graph.placements),'net_reference_bp':replay.footprint(best,graph.placements)['reference_union_bp']-ref_before,'score_improves':best.score>path.score}
        allrows.append(row);summary[primary]+=1
        if ordinal%10==0:
            (owner/'blocker-progress.json').write_text(json.dumps({'done':ordinal,'total':len(no_slot),'elapsed_s':monotonic()-began,'summary':dict(summary)},indent=2)+'\n');print('BLOCKER_PROGRESS',ordinal,len(no_slot),round(monotonic()-began,1),flush=True)
    report={'schema':'wheat_1A_no_slot_classification_v1','frozen_summary_sha256':replay.SUMMARY,'baseline_full_path_equal':True,'unselected':len(omitted),'no_reference_order_slot':len(no_slot),'baseline_metrics':replay.footprint(path,graph.placements),'graph_pickle_sha256':graph_pin,'counts':dict(summary),'rows':allrows,'elapsed_s':monotonic()-began,'mapper_calls':0,'formal_workspace_modified':False,'limitations':['This diagnoses insertion into the frozen winner, not global impossibility or all replacements.','99% central-reference trimming is a sensitivity flag, not proof that omitted anchors are biologically erroneous.','Maximum chain uses source-disjoint actual anchors and may conservatively omit partially overlapping legitimate anchors.','Aggregate candidate bp can overlap and is not net recoverable genome coverage.']}
    (owner/'blockers.json').write_text(json.dumps(report,indent=2)+'\n');(owner/'baseline-path.json').write_text(json.dumps(encode(path))+'\n');print('BLOCKER_DONE',json.dumps(dict(summary)),flush=True)


def run(base,owner):
    _,_,_,frozen,_=replay.load_arm(base/'q0-whole-local-maps.soHq9Z6J',replay.SUMMARY,'whole-wheat-local-supplement-v1');original=replay.search_variant
    def hook(mode):
        replay.need(mode=='baseline','unexpected second search');fn,pin=original(mode)
        def wrapped(graph,*,progress):
            result=fn(graph,progress=progress);replay.need(result.path==frozen['1A'],'baseline differs');analyse(graph,result.path,owner);raise Complete()
        return wrapped,pin
    with patch.object(replay,'search_variant',hook):
        try:replay.run(base,owner,'1A')
        except Complete:pass


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);a=p.parse_args();replay.need(a.owner.resolve().parent==a.base.resolve() and a.owner.name.startswith('q0-local-chain-'),'bad isolated owner')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external command prohibited in isolated diagnostic')):run(a.base.resolve(),a.owner.resolve())
