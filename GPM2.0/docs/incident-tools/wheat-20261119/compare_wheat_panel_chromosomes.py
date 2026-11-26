"""Replay both existing native arms on the COMPLETE graphs for the indirect wheat controls.

This tests third-source competition in real wheat first-request ranking. Locations are
frozen, not freshly admitted; local fresh admission is audited separately. No mapper.
"""
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
import json

from lgz_core.common import canonical_json
from lgz_core.q0_paths import PairLink,PathGraph,search_request_path
from lgz_core.q0_retained_hits import _checked_line,retained_geometry_cache
from lgz_core.q0_threshold_questions import questions
from lgz_core.q0_threshold_acceptance import record
from plan_wheat_panel_neighborhoods import INDIRECT
from probe_wheat_native_pair_scope import checked
from wheat_selection_checkpoint import need

MAPPING='b43c87a03d6f9b3e7cb33aea22293086f88e95a961d6149f47303736b5231538'

def matched_panel(base):
    d=base/'q0-indirect-panel-20261126.GWoN0Il5';return d,checked(d/'panel.json',INDIRECT)

def path_geometry(path):
    if path is None:return None
    return dict(slices=[[s.source.dataset,s.source.contig,s.orientation,s.interval.start,s.interval.end] for s in path.slices],
                joins=[[j.kind,j.n_bp] for j in path.joins])

def observed(case,path,byid):
    if not path:return False
    for l,j,r in zip(path.slices,path.joins,path.slices[1:]):
        x=l.interval.end if l.orientation=='+' else l.interval.start;y=r.interval.start if r.orientation=='+' else r.interval.end
        if (l.source,r.source,l.orientation,r.orientation,j.kind,x,y)==(byid[case['left']],byid[case['right']],case['left_strand'],case['right_strand'],case['kind'],case['left_cut'],case['right_cut']):return True
    return False

def ranked(job):
    c,arm=job;start=monotonic();rows=PS[c];links=OLD[c] if arm=='original' else BACKGROUND[c]+NEW[arm,c]; g=PathGraph(rows,links,(),first_request=True)
    search=search_request_path(g);path=search.path
    if arm=='original':need(path==WIN[c],'complete original graph did not reproduce the sealed path and evidence')
    # Every original group had a path. If an arm loses it, record the loss instead of
    # treating a single-group empty request as the global result for an unbuilt chromosome.
    req=None;counts={};issues=[]
    if path:
        need(any(p.localization_kind=='reference' for p in rows),'absent reference lineage')
        # With a built path in this single-group call there are no missing chromosomes;
        # assignments/part expansion are not involved. Check the full original issue list below.
        d=SimpleNamespace(sources={p.source for p in rows},reference_lengths={c:True},parts={},pair_links=links)
        pending,counts=questions(d,SimpleNamespace(admission=SimpleNamespace(placements=rows),paths={c:search}),[],issue_sink=issues.append);req=record(pending)
    if arm=='original':need(sorted(map(canonical_json,issues))==sorted(map(canonical_json,ISSUES[c])),'original per-group questions/coordinates differ')
    cases=[dict(stratum=r['stratum'],old_junction_selected=observed(r,path,BYID)) for r in PLAN['cases'] if r['chromosome']==c]; geom=path_geometry(path)
    print('PAIRED_GRAPH_ARM',c,arm,'links',len(links),'old_joins',sum(r['old_junction_selected'] for r in cases),'seconds',round(monotonic()-start,2),flush=True)
    return c,arm,dict(selected=geom,request=req,request_assessable=path is not None,counts=counts,cases=cases,pair_rows=len(links),elapsed_s=round(monotonic()-start,2))

def compare_groups(base,old,placements,paths,detail,summary,byid,lens,workers):
    global PLAN,BYID,PS,WIN,ISSUES,OLD,BACKGROUND,NEW
    d,PLAN=matched_panel(base);mapping=checked(d/'mapping.json',MAPPING);need(mapping['panel']==INDIRECT and PLAN['selection']==summary['selection_chain'] and PLAN['questions']==summary['questions'],'mixed generation');BYID=byid
    PS=defaultdict(list);groups_by_source=defaultdict(set);name_by_part={}; OLD=defaultdict(list);BACKGROUND=defaultdict(list);NEW=defaultdict(list)
    for p in placements:PS[p.chromosome].append(p);groups_by_source[p.source].add(p.chromosome);name_by_part[p.segment_id]=(p.segment_id,lens[p.source])
    groups=sorted(PS);WIN={p.chromosome:p for p in paths if p.chromosome in PS};ISSUES={c:[v for v in detail['issues'] if c in v['groups']] for c in groups}; qsrc={byid[k] for k in PLAN['queries']};need(groups==['1A','4A','7D'] and all(len(i['groups'])==1 for i in detail['issues']),'unexpected graph cohort')
    for z in old:
        for c in groups_by_source[z.query_source]&groups_by_source[z.target_source]:
            OLD[c].append(z)
            if z.query_source not in qsrc and z.target_source not in qsrc:BACKGROUND[c].append(z)
    cache=retained_geometry_cache();qs=set(PLAN['queries']); kept=set(PLAN['retained'])
    for arm in ('full','reduced'):
        fn=arm+'.paf';p=d/fn;h=sha256();prefix=('['+canonical_json(fn)+',').encode('ascii')
        with p.open('rb') as f:
            for i,line in enumerate(f,1):
                h.update(line);a=line.split(b'\t',6);q=a[0].decode();t=a[5].decode();need(q in qs and t in byid and (arm=='full' or t in kept),'foreign arm row')
                matching=groups_by_source.get(byid[q],set()) & groups_by_source.get(byid[t],set())
                if matching:
                    hit=_checked_line(line.decode(),p,fn,i,prefix,name_by_part,name_by_part,cache);z=PairLink(hit,byid[q],byid[t]);
                    for c in matching:NEW[arm,c].append(z)
        need(h.hexdigest()==mapping['mapper'][arm]['paf_sha256'],'PAF changed')
    jobs=[(c,arm) for c in groups for arm in ('original','full','reduced')];arms=defaultdict(dict)
    with ProcessPoolExecutor(max_workers=min(len(jobs),workers),mp_context=get_context('fork')) as pool:
        for c,arm,v in pool.map(ranked,jobs):arms[c][arm]=v
    same_sel={c:arms[c]['full']['selected']==arms[c]['reduced']['selected'] for c in groups};same_req={c:arms[c]['full']['request']==arms[c]['reduced']['request'] if all(arms[c][k]['request_assessable'] for k in ('full','reduced')) else None for c in groups}
    return dict(schema='wheat_indirect_full_chromosome_graphs_v1',panel=INDIRECT,mapping=MAPPING,selection=summary['selection_chain'],questions=summary['questions'],placements={c:len(v) for c,v in PS.items()},groups=arms,same_selected=same_sel,same_request=same_req,mapper_starts=0,published_q0=False,limits='Complete graph and stock first-request rank in three chromosomes; immutable whole-wheat admission. Not a fresh whole-wheat placement pass and not either retired query.')
