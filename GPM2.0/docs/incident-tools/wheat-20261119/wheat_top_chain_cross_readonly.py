"""3B/3D isolated cross-validation. Reuse screened rows and completed mappings.

No mapper. Any missing pair-cache cohort is read from already-completed PAFs,
never synthesized or substituted with an incomplete evidence set. Shared union
of both groups is read once. Admission and link artifacts are resume points.
"""
import argparse,gzip,json,pickle,subprocess,gc,inspect,multiprocessing as mp
from dataclasses import asdict
from collections import defaultdict,Counter
from pathlib import Path
from hashlib import sha256
from time import monotonic
from unittest.mock import patch
from lgz_core import q0_paths as paths
from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
import wheat_continuous_dominant_admission_readonly as original
from wheat_top_chain_admission_readonly import top_chain
from wheat_continuity_gap_rescue_readonly import need,load_rows,reference_order_flags
from wheat_continuity_path_refinement_readonly import metrics,refs,selected_risk
from wheat_top_chain_locus_loop_readonly import mapped_incumbent,save_path
from wheat_selection_checkpoint import encode,decode
from wheat_reference_funnel_readonly import digest,write
from wheat_local_chain_selection_readonly import checked_pickle,reference_spine
from wheat_group_evidence_readonly import load_links
from wheat_sparse_pair_graph_readonly import sparse_constructor
from wheat_indexed_anchor_support_readonly import AnchorSupportIndex,indexed_native
from wheat_locus_guard_readonly import replace_coverage
from compare_wheat_local_only_paths import load_arm

GROUPS=('3B','3D')
CACHED={}


def screen_task(task):
    group,src=task;row=CACHED.get(src);cached=row is not None
    if cached:
        groups={};high={}
        for k,aa,hh in row['groups']:
            groups[tuple(k)]=tuple(original.adm.ReferenceAnchor(Interval(a,b),Interval(c,d),e) for a,b,c,d,e in aa)
            high[tuple(k)]=tuple(Interval(a,b) for a,b in hh)
    else:
        original.GROUP=group
        groups,high,_=original.screened(src)
        row={'source':[src.dataset,src.contig],'length':original.frozen.FAI[src][0],'sequence_sha256':original.frozen.LOOKUP[src]['sequence_sha256'],
             'groups':[[list(k),[[a.source.start,a.source.end,a.reference.start,a.reference.end,a.evidence_id] for a in aa],[[v.start,v.end] for v in high.get(k,())]] for k,aa in sorted(groups.items())]}
    need(row['length']==original.frozen.LOOKUP[src]['length'] and row['sequence_sha256']==original.frozen.LOOKUP[src]['sequence_sha256'],'cached source identity mismatch')
    part=SourceSegment(original.legacy.PART_ID[src],src,Interval(0,row['length']),row['sequence_sha256'],0,'start','end')
    old,_=original.continuous_candidates(part,groups,high,target=group)
    new=[];audit=[]
    for key in sorted(k for k in groups if k[0]==group):
        if original.adm._size(a.source for a in groups[key])<500000:continue
        variants,detail=top_chain(part,groups,high,key,ratios=(10,))
        if detail['main_chain_bp']>=500000:audit.append({'key':list(key),**detail})
        new.extend(variants['10'])
    return {'group':group,'cached':cached,'source':row['source'],'row':row,'old':[encode(p) for p in old['75']],'new':[encode(p) for p in new],'audit':audit,
            'qualified':[[a.reference.start,a.reference.end] for k,aa in groups.items() if k[0]==group for a in aa]}


def admission_identity():
    return {'top_chain_sha256':sha256(inspect.getsource(top_chain).encode()).hexdigest(),
            'screen_task_sha256':sha256(inspect.getsource(screen_task).encode()).hexdigest(),
            'screened_sha256':sha256(inspect.getsource(original.screened).encode()).hexdigest(),
            'foreign_policy':asdict(original.POLICY),'reference_policy':asdict(original.frozen.POLICY),
            'groups':list(GROUPS),'chain_ratio':10}


def admission(base,source,owner,workers):
    began=monotonic();receipt=json.loads((source/'continuity-admission.json').read_text());cache=source/'screened-reference-anchors.jsonl.gz'
    need(digest(cache)==receipt['outputs'][cache.name]['sha256'],'old screened cache changed')
    before,lengths=original.initialize(base)
    wanted={src for src,hits in original.frozen.HITS.items() if any(h.target_name in GROUPS for h in hits)}
    with gzip.open(cache,'rt') as f:
        for line in f:
            row=json.loads(line);src=SourceKey(*row['source'])
            # Nonempty groups prove the previous full DNA/all-locus screen ran.
            # Empty rows may have exited at the 1A prefilter; never reuse those.
            if src in wanted and row['groups']:CACHED[src]=row
    tasks=[(g,src) for g in GROUPS for src in sorted(wanted) if any(h.target_name==g for h in original.frozen.HITS[src])]
    print('CROSS_SCREEN_SCOPE',len(tasks),'complete_cached_sources',len(CACHED),flush=True)
    counts={g:Counter() for g in GROUPS};qualified={g:[] for g in GROUPS};oldrows={g:[] for g in GROUPS};newrows={g:[] for g in GROUPS};audits={g:[] for g in GROUPS}
    streams={g:gzip.open(owner/(g+'-screened-anchors.jsonl.gz'),'wt',compresslevel=1) for g in GROUPS};last=monotonic()
    try:
        with mp.get_context('fork').Pool(workers) as pool:
            for r in pool.imap_unordered(screen_task,tasks,chunksize=1):
                g=r['group'];counts[g]['sources']+=1;counts[g]['cached_sources']+=r['cached'];counts[g]['new_source_screens']+=not r['cached']
                streams[g].write(json.dumps(r['row'])+'\n');qualified[g].extend(Interval(a,b) for a,b in r['qualified'])
                oldrows[g].extend(decode(v) for v in r['old']);newrows[g].extend(decode(v) for v in r['new'])
                if r['audit']:audits[g].append({'source':r['source'],'chains':r['audit']})
                if monotonic()-last>=30:print('CROSS_SCREEN_PROGRESS',json.dumps({g:dict(c) for g,c in counts.items()}),flush=True);last=monotonic()
    finally:
        for f in streams.values():f.close()
    output={};old_comparator=original.old_routes(source/'old-grt-q-segments.tsv')
    for g in GROUPS:
        files={}
        for name,ps in [('continuous75',oldrows[g]),('top10',newrows[g])]:
            file=owner/(g+'-'+name+'-placements.jsonl.gz')
            with gzip.open(file,'wt') as f:
                for p in sorted(ps,key=lambda p:(p.source,p.interval,p.orientation,p.placement_id)):f.write(json.dumps(encode(p))+'\n')
            conflicts=[];risk_refs=defaultdict(list)
            for p in ps:
                rr,ss=original.risk(p,old_comparator)
                for kind,ivs in rr.items():risk_refs[kind].extend(ivs)
                if any(ivs and kind!='same_group_same_orientation' for kind,ivs in ss.items()):conflicts.append(p.placement_id)
            files[name]={'file':file.name,'sha256':digest(file),'placements':len(ps),'reference_bp':original.adm._size(a.reference for p in ps for a in p.reference_blocks),'old_q0_conflict_placements':conflicts,'old_q0_reference_bp':{kind:original.adm._size(ivs) for kind,ivs in risk_refs.items()}}
        output[g]={'counts':dict(counts[g]),'qualified_reference_bp':original.adm._size(qualified[g]),'reference_length':lengths[g],'outputs':files,'source_audit':audits[g]}
    for path,sig in before.items():need(original.frozen.signature(path)==sig,'source inputs changed during screen')
    write(owner/'cross-admission.json',{'schema':'wheat_3B_3D_top_chain_admission_v1','groups':output,'admission_identity':admission_identity(),'source_1A_cache_sha256':receipt['outputs'][cache.name]['sha256'],'mapper_calls':0,'formal_workspace_modified':False,'elapsed_s':monotonic()-began})
    return output


def cross_source_overlaps(named_paths):
    used=defaultdict(list);conflicts=[]
    for name,path in named_paths.items():
        for source,iv in [(s.source,s.interval) for s in path.slices]+[(j.gap_source,j.gap_interval) for j in path.joins if j.gap_source is not None and j.gap_interval is not None]:
            for prior_group,prior in used[source]:
                overlap=iv.intersection(prior)
                if prior_group!=name and overlap is not None:
                    conflicts.append({'source':[source.dataset,source.contig],'groups':[prior_group,name],'interval':[overlap.start,overlap.end],'bp':overlap.length})
            used[source].append((name,iv))
    return conflicts


def run(base,source,legacy,owner,workers,one_a_owner):
    began=monotonic()
    one_a=json.loads((one_a_owner/'top-chain-locus-closed-loop.json').read_text())
    verified=json.loads((one_a_owner/'top-chain-locus-independent-audit.json').read_text())
    need(verified['loop_report_sha256']==digest(one_a_owner/'top-chain-locus-closed-loop.json'),'1A independent audit binding differs')
    primary=one_a['results']['chain_10_locus_1000000']
    need(primary['incumbent_lower_bounds_passed'] and not primary['risk']['conflict_flags'] and not primary['reference_order_flags'],'1A safety gate not met')
    need(all(primary['guard']['native_equivalence_reconstruction_proof'].values()),'1A native-equivalence proof missing')
    need(verified['results']['chain_10_locus_1000000']['reopened_native_graph_and_path_verified'],'1A primary path not independently reopened')
    if (owner/'cross-admission.json').exists():
        saved=json.loads((owner/'cross-admission.json').read_text())
        need(saved['admission_identity']==admission_identity(),'cross admission scientific policy changed')
        need(saved['source_1A_cache_sha256']==json.loads((source/'continuity-admission.json').read_text())['outputs']['screened-reference-anchors.jsonl.gz']['sha256'],'cross screened cache binding changed')
        admitted=saved['groups'];print('CROSS_ADMISSION_REUSED',flush=True)
    else:admitted=admission(base,source,owner,workers)
    CACHED.clear();original.frozen.HITS.clear();gc.collect()
    main=base/'q0-whole-local-maps.soHq9Z6J';_,_,records,baselines,_=load_arm(main,'d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4','whole-wheat-local-supplement-v1')
    frozen={g:[] for g in GROUPS}
    with (main/'selection/admission.jsonl').open('rb') as f:
        f.readline()
        for raw in f:
            row=json.loads(raw)
            if isinstance(row,list):break
            p=decode(row)
            if p.chromosome in GROUPS:
                need(records[p.chromosome][p.placement_id]==sha256(raw).hexdigest(),'frozen admission changed');frozen[p.chromosome].append(p)
    groups={};all_sources=set();old=original.old_routes(source/'old-grt-q-segments.tsv')
    for g in GROUPS:
        for meta in admitted[g]['outputs'].values():need(digest(owner/meta['file'])==meta['sha256'],'cross admission output changed')
        oldextra=load_rows(owner/admitted[g]['outputs']['continuous75']['file']);new=load_rows(owner/admitted[g]['outputs']['top10']['file'])
        values={}
        for p in frozen[g]+oldextra+new:
            key=(p.source,p.interval,p.orientation,p.reference_blocks)
            values.setdefault(key,p)
        groups[g]=list(values.values());all_sources.update(p.source for p in groups[g])
    binding={'admission_sha256':digest(owner/'cross-admission.json'),'sources':sorted([s.dataset,s.contig] for s in all_sources)}
    linkseal=owner/'cross-links.json';cache=owner/'cross-links.pickle'
    if linkseal.exists():
        saved=json.loads(linkseal.read_text());need(saved['binding']==binding,'pair cache binding changed');links=checked_pickle(cache,saved['sha256'])
    else:
        seal=json.loads((legacy/'expanded-links-regional.json').read_text());available={SourceKey(*v) for v in seal['binding']['sources']}
        missing=all_sources-available
        write(owner/'cross-pair-cache-scope.json',{'required_sources':len(all_sources),'missing_from_1A_pair_cache':len(missing),'missing_sources':sorted([s.dataset,s.contig] for s in missing),'cold_mapper_permitted':False})
        if not missing:
            links=checked_pickle(legacy/'expanded-links-regional.pickle',seal['sha256']);links=[l for l in links if l.query_source in all_sources and l.target_source in all_sources]
        else:
            print('CROSS_READ_EXISTING_COMPLETED_PAFS',len(missing),'sources not in 1A cache; one shared 3B+3D read; NO MAPPER',flush=True)
            links=load_links(base,owner,all_sources,group_label="3B+3D")
        raw=pickle.dumps(links,protocol=5);cache.write_bytes(raw);write(linkseal,{'binding':binding,'sha256':sha256(raw).hexdigest(),'count':len(links)});del raw
    results={}
    for g in GROUPS:
        def build(ps,label):
            file=owner/(g+'-'+label+'-graph.pickle');sealfile=file.with_suffix('.json')
            if sealfile.exists():
                seal=json.loads(sealfile.read_text());need(seal['binding']==binding,'graph binding changed');return checked_pickle(file,seal['sha256'])
            src={p.source for p in ps};counts=Counter();ctor,_,_=sparse_constructor(counts)
            with patch.object(paths.PathGraph,'__init__',ctor):graph=paths.PathGraph(ps,[l for l in links if l.query_source in src and l.target_source in src],(),paths.PathPolicy(),first_request=True,progress=lambda s:print('CROSS_GRAPH',g,label,s,flush=True))
            raw=pickle.dumps(graph,protocol=5);file.write_bytes(raw);write(sealfile,{'binding':binding,'sha256':sha256(raw).hexdigest(),'counts':dict(counts)})
            return graph
        baseline_graph=build(frozen[g],'frozen');baseline=baselines[g]
        replay=baseline_graph._score_candidate(baseline.nodes,baseline.joins)
        need(replay and replay.slices==baseline.slices and replay.score==baseline.score,'cross baseline physical path not reproduced')
        graph=build(groups[g],'top10-native');native_spine,native_diag=reference_spine(graph)
        if native_spine:
            results[g+'_native']=save_path(owner,g+'-top10-native',native_spine,graph,old,baseline,baseline_graph)|{'spine_diagnostics':native_diag,'control_only':True}
        for padding in (1_000_000,100_000):
            guard=replace_coverage(graph,padding,progress=lambda s:print('CROSS_LOCUS',g,padding,s,flush=True))
            spine,diag=reference_spine(graph);incumbent=mapped_incumbent(graph,baseline)
            valid=[p for p in (spine,incumbent) if p and p.score>=baseline.score and original.adm._size(refs(p,graph))>=original.adm._size(refs(baseline,baseline_graph))]
            name=g+'_locus_'+str(padding)
            if not valid:results[name]={'failed':'no legal path meeting baseline bounds','guard':guard}
            else:
                winner=min(valid,key=graph.rank)
                results[name]=save_path(owner,name,winner,graph,old,baseline,baseline_graph)|{'guard':guard,'spine_diagnostics':diag,'admission_reference_bp':original.adm._size(a.reference for p in groups[g] for a in p.reference_blocks),'frozen_metrics':metrics(replay,baseline_graph)}
        write(owner/'cross-validation-progress.json',{'results':results,'mapper_calls':0})
    occupancy={}
    for padding in (1_000_000,100_000):
        row=one_a['results']['chain_10_locus_'+str(padding)]
        file=one_a_owner/row['path_file'];need(digest(file)==row['path_sha256'],'1A chosen path changed')
        with gzip.open(file,'rt') as f:named={'1A':decode(json.load(f))}
        complete=True
        for g in GROUPS:
            row=results[g+'_locus_'+str(padding)]
            if 'failed' in row:complete=False;continue
            file=owner/row['path_file'];need(digest(file)==row['path_sha256'],'cross path changed')
            with gzip.open(file,'rt') as f:named[g]=decode(json.load(f))
        conflicts=cross_source_overlaps(named)
        occupancy[str(padding)]={'all_three_paths_available':complete,'source_interval_conflicts':conflicts,'passed':complete and not conflicts}
    checks={}
    for padding in (1_000_000,100_000):
        rows=[results[g+'_locus_'+str(padding)] for g in GROUPS]
        checks[str(padding)]=occupancy[str(padding)]['passed'] and all(not admitted[g]['outputs']['top10']['old_q0_conflict_placements'] for g in GROUPS) and all('failed' not in r and r['incumbent_lower_bounds_passed'] and not r['risk']['conflict_flags'] and not r['reference_order_flags'] and r['guard']['union_audit'].get('rejected_large_map_unions',0)==0 for r in rows)
    write(owner/'cross-validation.json',{'schema':'wheat_3B_3D_top_chain_locus_cross_v1','results':results,'cross_group_occupancy':occupancy,'three_group_policy_checks_passed':checks,'formal_q0_lgz':'HOLD','one_a_loop_sha256':digest(one_a_owner/'top-chain-locus-closed-loop.json'),'admission_receipt_sha256':digest(owner/'cross-admission.json'),'pair_receipt_sha256':digest(linkseal),'mapper_calls':0,'formal_workspace_modified':False,'fragment_refinement_run':False,'elapsed_s':monotonic()-began})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('source',type=Path);p.add_argument('legacy',type=Path);p.add_argument('owner',type=Path);p.add_argument('--workers',type=int,default=4);p.add_argument('--one-a-owner',type=Path,required=True);a=p.parse_args()
    need(a.owner.resolve().parent==a.base.resolve() and a.owner.stat().st_mode&0o077==0,'private owner required')
    with patch.object(subprocess,'Popen',side_effect=RuntimeError('external commands/mapper forbidden')),indexed_native(AnchorSupportIndex()):run(a.base,a.source,a.legacy,a.owner,a.workers,a.one_a_owner)
