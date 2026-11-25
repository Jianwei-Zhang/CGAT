"""Publish a readable, exact per-group dispatch census; do not open raw PAFs or start a mapper."""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import csv
import gzip
import json
import sys

from census_wheat_q0_fork import require
from wheat_dispatch_scope import get, put, REQ
from wheat_dispatch_audit import KNOWN

NATIVE = '14bbc01fad3743cdfdfb3ff4c6009d92caeb928c4b9291e156bac9aa827961d9'
FIELDS = ('skip_complete_native','skip_scoped_native','whole_parent_fallback','omit_both_axes',
          'reuse_exact_raw','cold_exact','needs_review')


def disposition(native_kind, fallback, left, right, raw):
    if native_kind:
        return {'exact_complete_matrices':'skip_complete_native','declared_long_part_scope':'skip_scoped_native'}[native_kind]
    if fallback:return 'whole_parent_fallback'
    if not (left or right):return 'omit_both_axes'
    if raw=='verified':return 'reuse_exact_raw'
    if raw in ('missing_raw','no_stored_context','missing_chain_and_raw'):return 'cold_exact'
    return 'needs_review'


def digest(path):return sha256(path.read_bytes()).hexdigest()


def main(run,out):
    # The predecessor's final manifest hash is printed in its successful job log.
    earlier=run/'rollup/result/group-summary.json'; pin=digest(earlier)
    log=(run/'rollup/summary_43060892.out').read_text();require(any(line.startswith('WHOLE_FIRST_DISPATCH ') and line.endswith('sha256 '+pin) for line in log.splitlines()),'unpublished group rollup')
    v1=get(earlier,pin);known=get(run/'result/known.json',KNOWN);native=get(run/'native/native.json',NATIVE)
    require(v1['known_manifest']==KNOWN and v1['request_sha256']==REQ and v1['total_windows']==61000 and native['mapper_starts']==0,'foreign cohort')
    refs=get(run/'result/issues.json.gz',known['issues']);book=get(earlier.parent/'questions.json.gz',v1['artifacts']['questions.json.gz']); issues=book['questions'];sources=book['source_table']
    require(refs['issues']==issues and book['request']==REQ and len(sources)==native['required_targets'],'foreign issues/source order')
    missing=get(earlier.parent/'cold-exact.json.gz',v1['artifacts']['cold-exact.json.gz']); review=get(earlier.parent/'fallback-or-review.json.gz',v1['artifacts']['fallback-or-review.json.gz'])
    prior={row['query']:row['classification'] for row in missing+review};require(len(prior)==len(missing)+len(review),'duplicate archived action')
    fallback={row['source_rank'] for row in review if row['classification']=='whole_parent_native_fallback'};require(fallback==set(native['retired_fallback_parents']), 'rebuilt fallback differs from executed historical dispatch')
    skip={int(rank):row for rank,row in native['parent_windows'].items()};skipped_ids={q for row in skip.values() for q in row['windows']}; require(not(skip.keys() & fallback),'retired fallback also claimed skipped')
    phase_specs=[('known',run/'result',known),('expanded',run/'expand/result',get(run/'expand/result/complete.json',v1['expanded_manifest']))]
    groups=defaultdict(Counter); issue_counts=defaultdict(Counter); linked=defaultdict(set); totals=Counter(); histogram=Counter(); axes=Counter(); used_prior=set();seen=set();seen_skip=set();actions=[];parents={}
    for i,issue in enumerate(issues):issue_counts[issue['group']][issue['kind']]+=1
    for phase,src,plan in phase_specs:
        dest=run/('audit-'+phase)/'result';audit=get(dest/'complete.json',v1['audit_manifests'][phase]);require(audit['shards'].keys()==plan['shards'].keys(),'lost part of audit')
        for name,stamp in sorted(plan['shards'].items()):
            rows=get(src/name,stamp); proofs=get(dest/name,audit['shards'][name]);require([r[0] for r in rows]==[q for q,p in proofs],'plan/audit disagreement')
            for row,(_,proof) in zip(rows,proofs):
                q,r,a,b,ctx,axis,left,right,why=row;require(q not in seen,'duplicate query');seen.add(q); raw=proof['status'];histogram[raw]+=1
                axes['query' if left else 'target_only' if right else 'neither']+=1; category=prior.get(q)
                if category:used_prior.add(q)
                else:require((not left and not right) or raw=='verified','missing prior exception')
                group='+'.join(refs['memberships'].get(str(r),[])) or 'unassigned'; native_kind=skip.get(r,{}).get('kind');case=disposition(native_kind,r in fallback,left,right,raw)
                require((q in skipped_ids)==bool(native_kind),'incomplete native scope');
                if native_kind:seen_skip.add(q)
                totals[case]+=1;groups[group][case]+=1
                inds=sorted(set(left+right)); affected=sorted({issues[i]['group'] for i in inds})
                for c in affected:
                    if case in ('cold_exact','whole_parent_fallback','needs_review'):issue_counts[c][case]+=1
                if case in ('cold_exact','needs_review','whole_parent_fallback'):
                    require(category is not None,'new action was absent from original census');linked[case].update(inds)
                    actions.append((case,q,group,*sources[r],a,b,ctx or '',axis or '',why or raw,','.join(affected),','.join(map(str,left)),','.join(map(str,right))))
                if case=='whole_parent_fallback':
                    part=parents.setdefault(r,dict(source=sources[r],query_group=group,windows=[],trigger_windows={},query_issues=set(),target_issues=set()));part['windows'].append(q)
                    if why:part['trigger_windows'][q]=why
                    part['query_issues'].update(left);part['target_issues'].update(right)
    require(historic_ok(v1,axes,histogram,seen,prior,used_prior) and seen_skip==skipped_ids and sum(totals.values())==61000,'inconsistent census')
    for v in parents.values():
        require(v['trigger_windows'],'whole parent without triggering window')
        for k in ('windows','query_issues','target_issues'):v[k]=sorted(v[k])
    out.mkdir(); files={}
    def tsv(name,header,rows):
        path=out/name; opener=gzip.open if name.endswith('.gz') else open
        with opener(path,'xt',encoding='utf-8',newline='') as handle:
            writer=csv.writer(handle,delimiter='\t',lineterminator='\n');writer.writerow(header);writer.writerows(rows)
        files[name]=digest(path)
    tsv('by-query-group.tsv',['query_group','historical_windows',*FIELDS],((g,sum(c.values()),*(c[f] for f in FIELDS)) for g,c in sorted(groups.items())))
    qfields=('weak_placement','unproven_join','cold_exact','whole_parent_fallback','needs_review')
    tsv('by-issue-group.tsv',['issue_group',*qfields],((g,*(c[f] for f in qfields)) for g,c in sorted(issue_counts.items())))
    tsv('actions.tsv.gz',['disposition','query_window_id','query_group','dataset','contig','start','end','context_id','frame_sha256','reason','issue_groups','query_issue_indices','target_issue_indices'],sorted(actions))
    tsv('questions.tsv.gz',['issue_index','issue_group','kind','stable_id','strand_or_join_strands','endpoint_source_intervals_json'],
        ((i,v['group'],v['kind'],v['id'],v.get('strand') or ','.join(v['strands']),json.dumps([[*sources[r],a,b] for r,a,b in v['spans']],separators=(',',':'))) for i,v in enumerate(issues)))
    files['fallback-parents.json']=put(out/'fallback-parents.json',parents)
    result=dict(schema='whole_wheat_frozen_partial_work_v2',parent_report=pin,request_sha256=REQ,native_sha256=NATIVE,window_counts={f:totals[f] for f in FIELDS},totals_by_raw_status=histogram,axes_before_native=axes,question_counts=Counter(v['kind'] for v in issues),linked_distinct_questions={k:len(v) for k,v in linked.items()},artifacts=files,mapper_starts_in_diagnostics=0,
        scope='Historical first partial stage with whole-wheat first-demand intervals; full native scopes precede fallback and regional filters. Scoped native coverage is not new exact evidence. Cold means same-context exact raw is missing, not an observation of a new process. Query groups are exclusive labels; issue-group window counts overlap. Fallbacks are whole parents, not one new native mapper per window. No main job, later rounds or final Q0.')
    print('VERIFIED_DISPATCH',result['window_counts'],put(out/'final.json',result),flush=True)


def historic_ok(report,axes,histogram,seen,prior,used):
    return axes==report['two_axis'] and histogram==report['raw_observations'] and len(seen)==report['total_windows'] and used==prior.keys()


if __name__=='__main__':main(*map(Path,sys.argv[1:]))
