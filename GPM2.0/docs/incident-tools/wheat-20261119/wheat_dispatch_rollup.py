"""Join the frozen questions, two-axis windows and verified raw results after *whole-parent* fallback."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import json
import sys

from bound_regional_scope_from_native_receipts import EXPECTED
from census_wheat_q0_fork import bounded, require
from lgz_core.common import stable_id
from wheat_dispatch_scope import get, inputs, original_queries, put, REQ
from wheat_dispatch_audit import KNOWN


def main(base,run,out):
    known=get(run/'result/known.json',KNOWN); question=get(run/'result/issues.json.gz',known['issues']); reasons=question['issues']
    snap,root,parts,order,_=inputs(base); queries=original_queries(base,parts,order); native_candidates=set(); anchor_sets=[]
    for key,stamp in EXPECTED.items():
        receipt=json.loads(bounded(root/'grt/evidence/q0_prepare/tasks'/key/'success.json',32<<20,stamp));spec=receipt['spec'];require(receipt['status']=='success' and stable_id('q0-map',spec)==key,'unbound native matrix')
        native_candidates.update(parts[p][0] for p in spec['query_ids'])
        if len(spec['target_ids'])>10000:anchor_sets.append(frozenset(parts[p][0] for p in spec['target_ids']))
    require(anchor_sets and len(set(anchor_sets))==1 and len(anchor_sets[0]-native_candidates)>1,'cannot bound native coverage outside native-query parents')
    expanded=get(run/'expand/result/complete.json');require(expanded['parent']==KNOWN and expanded['windows']==known['pending_count'],'foreign expanded scope')
    def batches():
        for mode,manifest,src in [('known',known['shards'],run/'result'),('expanded',expanded['shards'],run/'expand/result')]:
            dest=run/('audit-'+mode)/'result'; inv=get(dest/'complete.json'); require(inv['phase']==mode and inv['scope']==KNOWN and set(inv['shards'])==set(manifest) and inv['mapping_processes_launched']==0,'incomplete audit')
            for key,stamp in sorted(manifest.items()):
                rows=get(src/key,stamp);seal=get((dest/key).with_suffix('.seal')); require(seal['input']==stamp and seal['sha256']==inv['shards'][key],'mixed plan/audit')
                audits=get(dest/key,seal['sha256']);require([r[0] for r in rows]==[q for q,v in audits], 'incomplete or reordered audit')
                yield rows, audits
    # Any one invalid sibling sends *the entire parent* to native, not only that window.
    fallback=set(); axes=Counter(); seen=set()
    for rows, audits in batches():
        for q,r,a,b,ctx,stamp,left,right,why in rows:
            require(q not in seen and queries[q]==[r,a,b],'missing or foreign historical query');seen.add(q)
            if why:fallback.add(r)
            axes['query' if left else 'target_only' if right else 'neither']+=1
    require(seen==queries.keys() and axes=={'query':1917,'target_only':57374,'neither':1709},'cannot reproduce independent all-wheat geometry')
    out.mkdir(); totals=Counter(); groups=defaultdict(Counter); affected=defaultdict(Counter); cold=[]; review=[]; active=set(); disposition=Counter(); receipts={}; overlap_groups=Counter()
    for rows,audits in batches():
        for (q,r,a,b,ctx,axis,left,right,why),(_,proof) in zip(rows,audits):
            status=proof['status'];group='+'.join(question['memberships'].get(str(r),[])) or 'unassigned'; issue_ids=sorted(set(left+right)); links=sorted({reasons[i]['group'] for i in issue_ids}); disposition[status]+=1
            if r in fallback:case='whole_parent_native_fallback'
            elif not issue_ids:case='omitted_before_mapping'
            elif status=='verified':case='exact_raw_reusable'
            elif r in native_candidates:case='check_existing_native_parent_scope'
            elif status in ('no_stored_context','missing_raw','missing_chain_and_raw'):case='cold_exact'
            else:case='resolve_chain_or_cache_integrity'
            totals[case]+=1;groups[group][case]+=1
            if case=='exact_raw_reusable':continue
            if case=='omitted_before_mapping':continue
            item=dict(query=q,source_rank=r,start=a,end=b,query_group=group,context=ctx,frame_sha256=axis,query_issues=left,target_issues=right,issue_groups=links,classification=case,reason=why or status)
            if 'error' in proof:item['error']=proof['error']
            if case=='cold_exact':cold.append(item);active.update(issue_ids);overlap_groups['+'.join(links)]+=1
            else:review.append(item)
            for c in links:affected[c][case]+=1
    require(sum(totals.values())==len(queries) and len(cold)==totals['cold_exact'],'coverage mismatch')
    receipts['questions.json.gz']=put(out/'questions.json.gz',dict(request=REQ,source_table=[[s.dataset,s.contig] for s in order],questions=reasons))
    for name,data in [('cold-exact.json.gz',cold),('fallback-or-review.json.gz',review)]:receipts[name]=put(out/name,data)
    report=dict(schema='wheat_first_demand_frozen_partial_dispatch_v1',request_sha256=REQ,known_manifest=KNOWN,expanded_manifest=sha256((run/'expand/result/complete.json').read_bytes()).hexdigest(),audit_manifests={s:sha256((run/('audit-'+s)/'result/complete.json').read_bytes()).hexdigest() for s in ('known','expanded')},
        total_windows=len(queries),two_axis=axes,window_outcomes=totals,raw_observations=disposition,query_membership_groups=groups,issue_groups_nonexclusive=affected,cold_by_issue_group_combination=overlap_groups,cold_linked_questions=len(active),native_fallback_parents=len(fallback),artifacts=receipts,mapper_starts_during_diagnostic=0,
        limits='Historical first partial regional dispatch only. Cold means no usable exact-context result here, not an actual Popen count. Coarse/profile, possible native scope and native fallback are separate. Geometry links may inform a question, not proof that a join changes. Query membership groups are exclusive labels; affected groups can overlap. No approximation substitutes for exact sequence evidence or projection. Later rounds and native/candidate phases excluded.')
    print('WHOLE_FIRST_DISPATCH',dict(totals),'sha256',put(out/'group-summary.json',report),flush=True)


if __name__=='__main__':main(*map(Path,sys.argv[1:]))
