"""Reopen selected paths and saved graph; audit actual cuts, metrics and lower bounds."""
import argparse,gzip,json,subprocess
from pathlib import Path
from unittest.mock import patch
from lgz_core.q0_sources import Interval,merged_intervals
from wheat_continuity_path_refinement_readonly import (
    need,digest,write,checked_pickle,decode,common_anchor_joins,metrics,selected_risk,refs,old_routes,clipped)


def check_cut(graph,join):
    left=graph.placements[join.left_id];right=graph.placements[join.right_id]
    for block,evidence_id in graph.homologous_blocks(left,right):
        if evidence_id not in join.evidence_ids:continue
        if join.right_start!=block.right.start+join.left_end-block.left.start:continue
        support=[]
        for a in left.anchor_intervals:
            local=left.local(a);overlap=local.intersection(block.left)
            if overlap is None:continue
            for b in right.anchor_intervals:
                r=right.local(b).intersection(block.right)
                if r is None:continue
                mapped=Interval(block.left.start+r.start-block.right.start,
                                block.left.start+r.end-block.right.start)
                both=overlap.intersection(mapped)
                if both is not None:support.append(both)
        if any(v.length>=graph.policy.minimum_anchor_bp and v.start<=join.left_end<=v.end for v in merged_intervals(support)):
            return True
    return False


def run(owner,old_path):
    receipt=json.loads((owner/'continuity-final-selection.json').read_text())
    graph_receipt=json.loads((owner/'continuous-graph.json').read_text())
    graph=checked_pickle(owner/'continuous-graph.pickle',graph_receipt['sha256'])
    need(digest(old_path)=='cd9069e54e64cce94ba7d4790afd2c575d85ffc227722b04eca56bf6e04ea847','old comparator changed')
    old=old_routes(old_path);observed={};paths={}
    with common_anchor_joins(graph) as (native,pin):
        need(pin==receipt['join_variant_sha256'],'join code identity differs')
        for name,row in receipt['results'].items():
            path=owner/row['path_file'];need(digest(path)==row['path_sha256'],'selected path changed')
            with gzip.open(path,'rt') as f:selected=decode(json.load(f))
            need(graph._score_candidate(selected.nodes,selected.joins)==selected,'actual saved path not legal')
            represented,duplicate,_=graph.coverage.assess((s.source,s.interval) for s in selected.slices)
            need(not duplicate and represented==selected.score[0],'global coverage/duplicate assessment failed')
            met=json.loads(json.dumps(metrics(selected,graph)));risk=selected_risk(selected,graph,old)
            need(met==row['metrics'] and risk==row['risk'],'actual selected metrics or risk differ')
            new=[j for j in selected.joins if j not in native[j.left_id,j.right_id]]
            need(all(j.kind=='sequence_overlap' and check_cut(graph,j) for j in new),'new cut lacks actual common anchor witness')
            reference_order_flags=[]
            previous=None
            for s in selected.slices:
                placement=graph.placements[s.placement_id]
                anchors=clipped(placement.reference_blocks,s.interval,s.orientation)
                if not anchors:continue
                lo=min(a.reference.start for a in anchors);hi=max(a.reference.end for a in anchors)
                if previous and lo<previous[1]:
                    reference_order_flags.append({'previous':previous[0],'current':s.placement_id,'overlap_or_backtrack_bp':previous[1]-lo})
                previous=(s.placement_id,hi)
            observed[name]={'metrics':met,'risk':risk,'new_common_anchor_joins':len(new),
                            'reference_order_flags':reference_order_flags,'exact_gate':True}
            paths[name]=selected
        initial=paths['validated_initial_backbone'];final=paths['common_anchor_refined'];baseline=paths['frozen_baseline']
        need(final.score>=initial.score>=baseline.score,'score incumbent lower bound lost')
        n=lambda p:sum(v.length for v in refs(p,graph))
        need(n(final)>=n(initial)>=n(baseline),'reference length incumbent lower bound lost')
    result={'schema':'wheat_continuity_actual_path_audit_v1','selection_report_sha256':digest(owner/'continuity-final-selection.json'),
            'graph_sha256':graph_receipt['sha256'],'results':observed,'actual_paths_reopened':True,
            'native_exact_global_gates_passed':True,'new_cuts_have_real_common_anchors':True,
            'incumbent_score_and_reference_length_lower_bounds_verified':True,
            'mapper_calls':0,'formal_workspace_modified':False}
    write(owner/'continuity-selected-path-audit.json',result)
    print('ACTUAL_SELECTED_PATH_AUDIT_DONE',json.dumps(observed['common_anchor_refined']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('owner',type=Path);p.add_argument('old_q0',type=Path);a=p.parse_args()
    need(a.owner.stat().st_mode&0o077==0 and a.owner.name.startswith('q0-continuity-'),'private owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external command forbidden')):run(a.owner.resolve(),a.old_q0.resolve())
