"""Read-only deeper pair-gate/endpoint diagnosis using the saved exact 1A graph."""
import argparse,json,pickle,subprocess
from pathlib import Path
from collections import Counter,defaultdict
from dataclasses import replace
from hashlib import sha256
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_paths as paths,q0_admission as adm
from lgz_core.q0_sources import Interval,merged_intervals
from wheat_local_chain_primitives import clipped
from wheat_single_group_replay_readonly import need
from wheat_selection_checkpoint import decode
from wheat_reference_funnel_readonly import write,digest


def supported_bp(blocks,left,right):
    supported=[]
    for b in blocks:
        for iv in left.anchor_intervals:
            q=b.clip_left(left.local(iv))
            if q is None:continue
            for anchor in right.anchor_intervals:
                ov=q.right.intersection(right.local(anchor))
                if ov is not None:
                    start=q.left.start+ov.start-q.right.start;supported.append(Interval(start,start+ov.length))
    return adm._size(supported)


def cropped(p,interval):
    refs=clipped(p.reference_blocks,interval,p.orientation);anchors=merged_intervals(ov for a in p.anchor_intervals if (ov:=a.intersection(interval)) is not None)
    if not anchors:return None
    return replace(p,placement_id=p.placement_id+'-diagnostic-trim',interval=interval,reference_blocks=refs,reference_intervals=merged_intervals(a.reference for a in refs),anchor_intervals=anchors)


def overlap_bp(rows,iv):return adm._size(v for a in rows if (v:=a.intersection(iv)) is not None)


def run(owner):
    began=monotonic();report=json.loads((owner/'blockers.json').read_text());raw=(owner/'frozen-1A-graph.pickle').read_bytes();need(sha256(raw).hexdigest()==report['graph_pickle_sha256'],'graph cache changed');graph=pickle.loads(raw);path=decode(json.loads((owner/'baseline-path.json').read_text()));results=[]
    for row in report['rows']:
        if row['primary'] not in ('no_end_spanning_pair_evidence','no_qualified_pair_blocks_to_selected'):continue
        p=graph.placements[row['placement_id']];out={'placement_id':p.placement_id,'source':[p.source.dataset,p.source.contig],'source_bp':p.interval.length,'original_class':row['primary']}
        if row['primary']=='no_end_spanning_pair_evidence':
            options=[]
            for key in path.nodes:
                neighbor=graph.placements[key]
                for left,right in ((p,neighbor),(neighbor,p)):
                    groups=defaultdict(list)
                    for block,eid in graph.homologous_blocks(left,right):groups[eid].append(block)
                    for eid,blocks in groups.items():
                        end=max(b.left.end for b in blocks);start=min(b.right.start for b in blocks);a=left.interval.length-end;b=start
                        if a==0 and b==0:raise ValueError('original no-end classification inconsistent')
                        li=left.source_interval(Interval(0,end));ri=right.source_interval(Interval(start,right.interval.length));new_left=cropped(left,li);new_right=cropped(right,ri);links=graph.links[tuple(sorted((left.source,right.source)))];after=paths.qualify_pair_blocks(new_left,new_right,links,graph.policy) if new_left is not None and new_right is not None else ();valid=bool(after and paths._end_spanning_evidence(after,new_left.interval.length))
                        lost_left=adm._size(left.anchor_intervals)-overlap_bp(left.anchor_intervals,li);lost_right=adm._size(right.anchor_intervals)-overlap_bp(right.anchor_intervals,ri)
                        options.append({'left':left.placement_id,'right':right.placement_id,'evidence_id':eid,'left_tail_bp':a,'right_head_bp':b,'total_trim_bp':a+b,'trimmed_supported_anchor_bp':lost_left+lost_right,'pair_end_gate_passes_after_exact_crop':valid,'candidate_is_left':left.placement_id==p.placement_id})
            need(bool(options),'missing qualified endpoint candidates');out['pair_chain_options']=len(options);out['minimum_trim']=min(options,key=lambda v:(v['total_trim_bp'],v['trimmed_supported_anchor_bp'],v['left'],v['right'],v['evidence_id']));safe=[v for v in options if v['trimmed_supported_anchor_bp']==0 and v['pair_end_gate_passes_after_exact_crop']];out['zero_anchor_loss_crop_available']=bool(safe)
            if safe:out['minimum_zero_anchor_loss_trim']=min(safe,key=lambda v:(v['total_trim_bp'],v['left'],v['right'],v['evidence_id']))
        else:
            count=Counter()
            for key in path.nodes:
                neighbor=graph.placements[key];links=graph.links.get(tuple(sorted((p.source,neighbor.source))),())
                for left,right in ((p,neighbor),(neighbor,p)):
                    for link in links:
                        count['identity_passing_directed_links']+=1;blocks=paths.pair_blocks(link,left,right)
                        if not blocks:continue
                        count['with_oriented_overlapping_geometry']+=1
                        if any(not paths.reference_consistent(b,left,right) for b in blocks):continue
                        count['all_pair_blocks_reference_consistent']+=1
                        if supported_bp(blocks,left,right)<graph.policy.minimum_anchor_bp:continue
                        count['joint_anchor_support_sufficient']+=1
            if not count['with_oriented_overlapping_geometry']:reason='orientation_or_local_coordinate_overlap'
            elif not count['all_pair_blocks_reference_consistent']:reason='whole_alignment_reference_consistency_veto'
            elif not count['joint_anchor_support_sufficient']:reason='insufficient_joint_supported_anchor_bp'
            else:reason='supported_but_no_coordinate_unique_pair_block'
            out['subreason']=reason;out['gate_counts']=dict(count)
        results.append(out)
        if len(results)%20==0:print('EDGE_FORENSICS_PROGRESS',len(results),round(monotonic()-began,1),flush=True)
    noend=[r for r in results if r['original_class']=='no_end_spanning_pair_evidence'];thresholds={str(n):sum(r['minimum_trim']['total_trim_bp']<=n for r in noend) for n in (10,100,1000,10000,100000,1000000)}
    output={'schema':'wheat_1A_pair_edge_forensics_v1','blocker_report_sha256':digest(owner/'blockers.json'),'graph_sha256':report['graph_pickle_sha256'],'rows':results,'no_end_count':len(noend),'minimum_trim_le_bp_counts':thresholds,'zero_anchor_loss_crop_count':sum(r['zero_anchor_loss_crop_available'] for r in noend),'unqualified_subreasons':dict(Counter(r['subreason'] for r in results if 'subreason' in r)),'elapsed_s':monotonic()-began,'mapper_calls':0,'formal_workspace_modified':False,'limitations':['Minimum endpoint crop is for one directed pair, not proof of a valid complete two-sided path insertion.','Zero observed anchor loss does not prove discarded source bases biologically dispensable.','Reference-consistency veto is an exact coordinate check on every paired block of an alignment; this audit does not relax it.','No pair evidence in the parent classification means no identity-passing pair evidence in this frozen graph, not absence of every raw PAF row.']}
    write(owner/'pair-edge-forensics.json',output);print('EDGE_FORENSICS_DONE',json.dumps({k:v for k,v in output.items() if k not in ('rows','limitations')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('owner',type=Path);a=p.parse_args();need(a.owner.name.startswith('q0-local-chain-') and a.owner.stat().st_mode&0o077==0,'private isolated owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external process forbidden')):run(a.owner.resolve())
