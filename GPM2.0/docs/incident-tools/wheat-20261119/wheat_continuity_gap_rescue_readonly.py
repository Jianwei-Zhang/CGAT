"""Cached 1A forensics: exact-gated hull rescue and split-before-dominance.

The hull experiment retains the ENTIRE original coverage model (nonadjacent and
transitive equivalences included). New IDs describe strict subintervals; neither
duplicate relations nor original candidates vanish. No formal workspace writes.
"""
import argparse, gzip, json, subprocess
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_admission as adm
from lgz_core.q0_sources import Interval, SourceKey, SourceSegment, merged_intervals, subtract_intervals
from wheat_selection_checkpoint import encode, decode
from wheat_local_chain_selection_readonly import checked_pickle
from wheat_continuity_path_refinement_readonly import need, metrics, refs, selected_risk, common_anchor_joins
from wheat_continuous_dominant_admission_readonly import old_routes, risk, foreign_barriers, POLICY
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex, indexed_native
from wheat_local_chain_primitives import chain, clipped
from wheat_selected_path_risk_audit import minus
from wheat_reference_funnel_readonly import digest, write
import wheat_continuous_dominant_admission_readonly as continuous


def load_rows(file):
    with gzip.open(file, 'rt') as f:
        return [decode(json.loads(line)) for line in f]


def dp_nodes(graph):
    rows=sorted((p for p in graph.placements.values() if p.reference_intervals),
                key=lambda p:(max(i.end for i in p.reference_intervals), min(i.start for i in p.reference_intervals), p.placement_id))
    ends=[max(v.end for v in p.reference_intervals) for p in rows]
    dp=[(0,0)];back=[];take=[]
    for i,p in enumerate(rows):
        j=bisect_right(ends,min(v.start for v in p.reference_intervals),0,i)
        value=(dp[j][0]+p.interval.length,dp[j][1]-1);chosen=value>dp[-1]
        dp.append(value if chosen else dp[-1]);back.append(j);take.append(chosen)
    chosen=[];i=len(rows)
    while i:
        if take[i-1]:chosen.append(rows[i-1].placement_id);i=back[i-1]
        else:i-=1
    return tuple(reversed(chosen)),dp[-1][0]


def append_options(graph,current,node):
    if current is None:
        p=graph._score_candidate((node,),())
        return [p] if p else []
    return [p for j in graph.joins(current.nodes[-1],node)
            if (p:=graph._score_candidate(current.nodes+(node,),current.joins+(j,))) is not None]


def candidate_slices(graph,nodes,joins):
    out=[]
    for i,node in enumerate(nodes):
        p=graph.placements[node];start=joins[i-1].right_start if i else 0
        end=joins[i].left_end if i<len(joins) else p.interval.length
        if start>=end:return None
        out.append((p.source,p.source_interval(Interval(start,end))))
    return out


def hull_variant(graph,node):
    p=graph.placements[node]
    if not p.reference_blocks:return None
    hull=adm._hull(a.source for a in p.reference_blocks)
    if hull==p.interval:return None
    anchors=merged_intervals(iv for a in p.anchor_intervals if (iv:=a.intersection(hull)) is not None)
    key='diagnostic-anchor-hull-'+sha256((node+':'+str(hull.start)+':'+str(hull.end)).encode()).hexdigest()[:24]
    new=replace(p,placement_id=key,interval=hull,anchor_intervals=anchors,
                localization_kind='diagnostic_duplicate_overhang_hull')
    graph.placements[key]=new
    return key


def path_for_nodes(graph,nodes):
    joins=[]
    for a,b in zip(nodes,nodes[1:]):
        choices=graph.joins(a,b)
        if not choices:return None
        joins.append(next((j for j in choices if j.kind=='reference_unknown'),choices[0]))
    return graph._score_candidate(tuple(nodes),tuple(joins))


def reference_order_flags(path,graph):
    previous=None;flags=[]
    for s in path.slices:
        anchors=clipped(graph.placements[s.placement_id].reference_blocks,s.interval,s.orientation)
        if not anchors:continue
        lo=min(a.reference.start for a in anchors);hi=max(a.reference.end for a in anchors)
        if previous and lo<previous[1]:flags.append([previous[0],s.placement_id,previous[1]-lo])
        previous=s.placement_id,hi
    return flags


def selection(source,admission,out):
    start=monotonic();receipt=json.loads((source/'continuity-final-selection.json').read_text())
    seal=json.loads((source/'continuous-graph.json').read_text())
    graph=checked_pickle(source/'continuous-graph.pickle',seal['sha256'])
    old=old_routes(admission/'old-grt-q-segments.tsv')
    row=receipt['results']['validated_initial_backbone'];file=source/row['path_file']
    need(digest(file)==row['path_sha256'],'backbone artifact changed')
    with gzip.open(file,'rt') as f:baseline=decode(json.load(f))
    need(graph._score_candidate(baseline.nodes,baseline.joins)==baseline,'cached backbone is not legal')
    nodes,weight=dp_nodes(graph)
    need(len(nodes)==receipt['spine_diagnostics']['proposal_nodes'] and weight==receipt['spine_diagnostics']['proposal_source_length_weight'],'DP proposal differs')
    current=None;failures=[]
    for node in nodes:
        opts=append_options(graph,current,node)
        if opts:current=min(opts,key=graph.rank);continue
        p=graph.placements[node];hull=adm._hull(a.source for a in p.reference_blocks)
        row={'node':node,'source':[p.source.dataset,p.source.contig], 'source_bp':p.interval.length,
             'interval':encode(p.interval),'anchor_hull':encode(hull),'overhang_bp':p.interval.length-hull.length,
             'reference_bp':adm._size(p.reference_intervals),'attempts':[]}
        conflicts=set()
        for j in graph.joins(current.nodes[-1],node) if current else ():
            slices=candidate_slices(graph,current.nodes+(node,),current.joins+(j,))
            if slices is None:row['attempts'].append({'reason':'empty_slice'});continue
            same=any(a==b and x.intersection(y) for i,(a,x) in enumerate(slices) for b,y in slices[:i])
            _,dup,_=graph.coverage.assess(slices)
            local=[]
            for sl,(src,iv) in zip(current.slices,slices[:-1]):
                if graph.coverage.unique_selected_bp(((src,iv),slices[-1])) is None:
                    conflicts.add(sl.placement_id);local.append(sl.placement_id)
            row['attempts'].append({'join_kind':j.kind,'source_overlap':same,'duplicate':dup,'conflict_nodes':local})
        variant=hull_variant(graph,node)
        row['candidate_hull_alone_passes']=bool(append_options(graph,current,variant)) if variant else False
        with common_anchor_joins(graph):
            row['common_anchor_join_alone_passes']=bool(append_options(graph,current,node))
        graph._joins.clear()
        row['conflict_nodes']=sorted(conflicts)
        row['conflicts_adjacent_only']=bool(conflicts) and conflicts=={current.nodes[-1]}
        failures.append(row)
        print('SKIPPED_NODE_FORENSICS',len(failures),json.dumps(row),flush=True)
    need(current==baseline,'22-node original fallback not reproduced exactly')
    need(len(failures)==22,'unexpected skip count')
    # Same DP sequence; crop on exact failure only. A second bounded arm crops
    # specific conflicting previous placements, never every placement globally.
    current=None;actions=[]
    for node in nodes:
        opts=append_options(graph,current,node)
        if opts:current=min(opts,key=graph.rank);continue
        variant=hull_variant(graph,node);opts=append_options(graph,current,variant) if variant else []
        action={'node':node,'candidate_hull':variant,'kind':'candidate_hull','accepted':False}
        if not opts and current:
            offenders=[]
            for s in current.slices:
                p=graph.placements[node]
                if graph.coverage.unique_selected_bp(((s.source,s.interval),(p.source,p.interval))) is None:
                    offenders.append(s.placement_id)
            mapping={v:hull_variant(graph,v) for v in offenders}
            mapping={k:v for k,v in mapping.items() if v}
            for newnode in (variant,node) if variant else (node,):
                trial=path_for_nodes(graph,tuple(mapping.get(n,n) for n in current.nodes)+(newnode,))
                if trial and trial.score>=current.score and adm._size(refs(trial,graph))>=adm._size(refs(current,graph)):
                    opts.append(trial)
            if opts:action.update(kind='conflicting_hulls',prior_replacements=mapping)
        if opts:
            best=min(opts,key=graph.rank)
            if current is None or (best.score>=current.score and adm._size(refs(best,graph))>=adm._size(refs(current,graph))):
                current=best;action['accepted']=True
        actions.append(action)
        print('HULL_RESCUE_ACTION',json.dumps(action),flush=True)
    need(current is not None,'empty rescue')
    represented,dup,_=graph.coverage.assess((s.source,s.interval) for s in current.slices)
    need(not dup and represented==current.score[0],'original exact duplicate assessment failed')
    result={'schema':'wheat_continuity_gap_rescue_selection_v1','input_graph_sha256':seal['sha256'],
            'input_selection_sha256':digest(source/'continuity-final-selection.json'),
            'proposal_nodes':len(nodes),'proposal_source_bp':weight,'original_skips':failures,'actions':actions,
            'original_metrics':metrics(baseline,graph),'rescued_metrics':metrics(current,graph),
            'risk':selected_risk(current,graph,old),'reference_order_flags':reference_order_flags(current,graph),
            'exact_original_coverage_gate_passed':True,'same_coverage_model_preserved':True,
            'meets_incumbent_score_and_reference_lower_bounds':current.score>=baseline.score and adm._size(refs(current,graph))>=adm._size(refs(baseline,graph)),
            'new_reference_gain_bp':adm._size(minus(refs(current,graph),refs(baseline,graph))),
            'reference_loss_bp':adm._size(minus(refs(baseline,graph),refs(current,graph))),
            'mapper_calls':0,'formal_workspace_modified':False,'elapsed_s':monotonic()-start}
    with gzip.open(out/'hull-rescued-path.json.gz','wt') as f:json.dump(encode(current),f)
    with gzip.open(out/'hull-rescue-placements.jsonl.gz','wt') as f:
        for p in graph.placements.values():f.write(json.dumps(encode(p))+'\n')
    result['path_sha256']=digest(out/'hull-rescued-path.json.gz')
    result['placements_sha256']=digest(out/'hull-rescue-placements.jsonl.gz')
    write(out/'hull-rescue-selection.json',result)
    print('HULL_RESCUE_DONE',json.dumps({k:v for k,v in result.items() if k not in ('original_skips','actions')}),flush=True)


def split_first(part,groups,high,key,minimum=500_000):
    main=chain(groups[key],key[1]);main_bp=adm._size(a.source for a in main)
    if main_bp<minimum:return [],{'reason':'main_chain_below_500kb','main_chain_bp':main_bp}
    barriers,foreign=foreign_barriers(groups,high,key,main,part.interval.length)
    out=[];regions=[]
    for region in subtract_intervals(part.interval,barriers):
        anchors=clipped(main,region,key[1]);bp=adm._size(a.source for a in anchors)
        high_bp=continuous.legacy.overlap_bp((a.source for a in anchors),high.get(key,()))
        total=adm._size(iv for rows in groups.values() for a in rows if (iv:=a.source.intersection(region)))
        local_fraction=bp/max(1,total)
        accepted=(bp>=minimum and high_bp>=continuous.frozen.POLICY.minimum_anchor_bp
                  and bp>=POLICY.minimum_chain_fraction_of_carried_source*region.length and local_fraction>=0.75)
        regions.append({'interval':encode(region),'support_bp':bp,'high_mapq_bp':high_bp,'local_fraction':local_fraction,'accepted':accepted})
        if not accepted:continue
        need(adm._ordered(anchors,key[1]),'split-first main chain is unordered')
        out.append(adm._placement(part,*key,region,(a.source for a in anchors),anchors,(a.evidence_id for a in anchors),kind='diagnostic_split_first_local75_chain'))
    return out,{'main_chain_bp':main_bp,'foreign_chains':foreign,'regions':regions}


def admission_audit(source,out):
    start=monotonic();receipt=json.loads((source/'continuity-admission.json').read_text())
    for name in ('screened-reference-anchors.jsonl.gz','continuity-source-audit.jsonl.gz','frozen-placements.jsonl.gz','continuous75-placements.jsonl.gz'):
        need(digest(source/name)==receipt['outputs'][name]['sha256'],'cached admission artifact differs: '+name)
    with gzip.open(source/'continuity-source-audit.jsonl.gz','rt') as f:audit={tuple(v['source']):v for l in f if (v:=json.loads(l))}
    frozen=load_rows(source/'frozen-placements.jsonl.gz');retained=load_rows(source/'continuous75-placements.jsonl.gz')
    old=old_routes(source/'old-grt-q-segments.tsv')
    before=merged_intervals(a.reference for p in frozen+retained for a in p.reference_blocks)
    qualified=[];by_reason=defaultdict(list);rescued=[];rows_out=[];count=Counter()
    lookup=continuous.frozen.checked(source.parent/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',continuous.frozen.LOOK)
    parts={SourceKey(v['dataset'],v['contig']):(k,v) for k,v in lookup.items()}
    with gzip.open(source/'screened-reference-anchors.jsonl.gz','rt') as f:
        for line in f:
            row=json.loads(line);src=SourceKey(*row['source']);detail=audit[tuple(row['source'])]
            groups={};high={}
            for key,aa,hh in row['groups']:
                key=tuple(key);groups[key]=tuple(adm.ReferenceAnchor(Interval(a,b),Interval(c,d),e) for a,b,c,d,e in aa)
                high[key]=tuple(Interval(a,b) for a,b in hh)
            target_refs=[a.reference for k,aa in groups.items() if k[0]=='1A' for a in aa]
            qualified.extend(target_refs)
            reason=detail.get('reason','passed_global_dominance')
            if reason=='main_chain_support_or_dominance':
                reason=('main_chain_below_100kb' if detail['main_chain_bp']<POLICY.minimum_main_chain_bp else 'global_dominance_below75')
            by_reason[reason].extend(target_refs);count[reason]+=1
            if reason not in ('global_dominance_below75','dominant_group_is_not_target'):continue
            key_id,meta=parts[src]
            need(row['length']==meta['length'] and row['sequence_sha256']==meta['sequence_sha256'],'cached source identity differs')
            part=SourceSegment(key_id,src,Interval(0,row['length']),row['sequence_sha256'],0,'start','end')
            for key in sorted(k for k in groups if k[0]=='1A'):
                new,report=split_first(part,groups,high,key)
                if report['main_chain_bp']<500_000:continue
                rows_out.append({'source':row['source'],'original_reason':reason,'original_dominance_fraction':detail.get('dominance_fraction'), 'key':list(key),**report,'placements':len(new), 'reference_bp':adm._size(a.reference for p in new for a in p.reference_blocks)})
                rescued.extend(new)
            if sum(count.values())%1000==0:print('ADMISSION_LEDGER_PROGRESS',sum(count.values()),len(rescued),flush=True)
    missing=minus(qualified,before)
    # Contributions overlap: show overlapping unions AND disjoint attribution.
    remaining=missing;ledger={}
    order=['global_dominance_below75','dominant_group_is_not_target','main_chain_below_100kb','passed_global_dominance','no_qualified_group']
    for reason in order:
        spans=by_reason.get(reason,[])
        ledger[reason]={'sources':count[reason],'missing_reference_overlap_bp':continuous.legacy.overlap_bp(missing,spans),'exclusive_in_priority_order_bp':continuous.legacy.overlap_bp(remaining,spans)}
        remaining=minus(remaining,spans)
    categories=defaultdict(list);conflicts=[]
    for p in rescued:
        rr,ss=risk(p,old)
        for k,v in rr.items():categories[k].extend(v)
        if any(k!='same_group_same_orientation' and v for k,v in ss.items()):conflicts.append(p.placement_id)
    after=merged_intervals(tuple(before)+tuple(a.reference for p in rescued for a in p.reference_blocks))
    result={'schema':'wheat_continuity_split_first_audit_v1','source_admission_sha256':digest(source/'continuity-admission.json'),
            'qualified_reference_bp':adm._size(qualified),'original_combined_reference_bp':adm._size(before),'missing_reference_bp':adm._size(missing),
            'reason_priority':order,'reason_ledger':ledger,'unattributed_missing_bp':adm._size(remaining),
            'split_first_minimum_local_chain_bp':500000,'split_first_minimum_local_fraction':0.75,
            'split_first_added_placements':len(rescued),'split_first_added_sources':len({p.source for p in rescued}),
            'split_first_combined_reference_bp':adm._size(after),'split_first_reference_gain_bp':adm._size(minus(after,before)),
            'old_q0_conflict_placements':conflicts,'old_q0_reference_overlap_bp':{k:adm._size(v) for k,v in categories.items()},
            'candidates':rows_out,'mapper_calls':0,'formal_workspace_modified':False,'elapsed_s':monotonic()-start}
    with gzip.open(out/'split-first-extra-placements.jsonl.gz','wt') as f:
        for p in rescued:f.write(json.dumps(encode(p))+'\n')
    result['extra_placements_sha256']=digest(out/'split-first-extra-placements.jsonl.gz')
    need(result['qualified_reference_bp']==445132656 and result['original_combined_reference_bp']==362240671,'original admission unions not reproduced')
    write(out/'split-first-admission-audit.json',result)
    print('SPLIT_FIRST_AUDIT_DONE',json.dumps({k:v for k,v in result.items() if k!='candidates'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('selection_owner',type=Path);p.add_argument('admission_owner',type=Path);p.add_argument('owner',type=Path);p.add_argument('--stage',choices=('selection','admission','both'),default='both');a=p.parse_args()
    need(a.owner.resolve().parent==a.selection_owner.resolve().parent==a.admission_owner.resolve().parent and a.owner.stat().st_mode&0o077==0,'private sibling owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('no external programs in cached diagnostic')):
        with indexed_native(AnchorSupportIndex()):
            if a.stage in ('selection','both'):selection(a.selection_owner,a.admission_owner,a.owner)
            if a.stage in ('admission','both'):admission_audit(a.admission_owner,a.owner)
