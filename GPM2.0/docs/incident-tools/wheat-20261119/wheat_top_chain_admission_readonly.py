"""Isolated Top-1/Top-2 collinear admission from sealed screened anchors."""
import gzip,json
from collections import defaultdict,Counter
from pathlib import Path
from time import monotonic
from lgz_core.q0_sources import SourceKey,SourceSegment,Interval,subtract_intervals
from wheat_continuity_gap_rescue_readonly import need,load_rows
from wheat_split_first_indexed_readonly import indexed_barriers,OverlapIndex
from wheat_local_chain_primitives import chain,clipped
from wheat_continuous_dominant_admission_readonly import adm,POLICY,old_routes,risk
import wheat_continuous_dominant_admission_readonly as continuous
from wheat_reference_funnel_readonly import digest,write
from wheat_selection_checkpoint import encode
from wheat_selected_path_risk_audit import minus

FOREIGN_BARRIERS=indexed_barriers()[0]


def top_chain(part,groups,high,key,minimum=500_000,ratios=(10,5),single_group_limit=.25):
    main=chain(groups[key],key[1]);bp=adm._size(a.source for a in main)
    results={str(v):[] for v in ratios}
    if bp<minimum:return results,{'main_chain_bp':bp,'reason':'short_main'}
    barriers,foreign=FOREIGN_BARRIERS(groups,high,key,main,part.interval.length)
    audit={'main_chain_bp':bp,'foreign_cluster_count':len(foreign),'foreign_barrier_count':sum(r['split'] for r in foreign),'regions':[]}
    high_index=OverlapIndex(high.get(key,()))
    for region in subtract_intervals(part.interval,barriers):
        anchors=clipped(main,region,key[1]);support=adm._size(a.source for a in anchors)
        if support<minimum:continue
        high_bp=high_index.overlap(a.source for a in anchors)
        competitors=[]
        for other,rows in groups.items():
            if other==key:continue
            local=clipped(rows,region,other[1]);other_chain=chain(local,other[1])
            competitors.append({'group':list(other),'chain_bp':adm._size(a.source for a in other_chain),'group_support_bp':adm._size(a.source for a in local)})
        top=max((r['chain_bp'] for r in competitors),default=0)
        max_group=max((r['group_support_bp'] for r in competitors),default=0)
        safe=(high_bp>=continuous.frozen.POLICY.minimum_anchor_bp and support>=.2*region.length and max_group<=single_group_limit*support)
        accepted=[str(r) for r in ratios if safe and support>=r*top]
        row={'interval':[region.start,region.end],'main_bp':support,'high_mapq_bp':high_bp,'max_foreign_chain_bp':top,'max_foreign_group_support_bp':max_group,'accepted_ratios':accepted,'competitors':competitors}
        audit['regions'].append(row)
        if not accepted:continue
        need(adm._ordered(anchors,key[1]),'unordered main chain')
        p=adm._placement(part,*key,region,(a.source for a in anchors),anchors,(a.evidence_id for a in anchors),kind='diagnostic_top_collinear_chain')
        for r in accepted:results[r].append(p)
    return results,audit


def run(source,out):
    began=monotonic();receipt=json.loads((source/'continuity-admission.json').read_text())
    cache=source/'screened-reference-anchors.jsonl.gz'
    need(digest(cache)==receipt['outputs'][cache.name]['sha256'],'screened cache changed')
    lookup=continuous.frozen.checked(source.parent/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',continuous.frozen.LOOK)
    parts={SourceKey(v['dataset'],v['contig']):(k,v) for k,v in lookup.items()}
    old=old_routes(source/'old-grt-q-segments.tsv')
    original=load_rows(source/'frozen-placements.jsonl.gz')+load_rows(source/'continuous75-placements.jsonl.gz')
    before=[a.reference for p in original for a in p.reference_blocks]
    placements={'10':[],'5':[]};audit=[];done=0;last=monotonic()
    with gzip.open(cache,'rt') as stream:
        for raw in stream:
            row=json.loads(raw);done+=1;src=SourceKey(*row['source'])
            # Source support is an upper bound on chain support. Avoid building
            # irrelevant chains; does not change any >=500kb candidate.
            keys=[tuple(k) for k,aa,hh in row['groups'] if k[0]=='1A' and adm._size(Interval(a[0],a[1]) for a in aa)>=500000]
            if not keys:continue
            groups={};high={}
            for k,aa,hh in row['groups']:
                key=tuple(k);groups[key]=tuple(adm.ReferenceAnchor(Interval(a,b),Interval(c,d),e) for a,b,c,d,e in aa)
                high[key]=tuple(Interval(a,b) for a,b in hh)
            part_id,meta=parts[src]
            need(row['length']==meta['length'] and row['sequence_sha256']==meta['sequence_sha256'],'source identity differs')
            part=SourceSegment(part_id,src,Interval(0,row['length']),row['sequence_sha256'],0,'start','end')
            for key in keys:
                new,detail=top_chain(part,groups,high,key)
                if detail['main_chain_bp']<500000:continue
                audit.append({'source':row['source'],'key':list(key),**detail})
                for r,ps in new.items():placements[r].extend(ps)
                print('TOP_CHAIN_SOURCE',row['source'],key,detail['main_chain_bp'],{r:len(ps) for r,ps in new.items()},flush=True)
            if monotonic()-last>30:print('TOP_CHAIN_PROGRESS',done,round(monotonic()-began,1),flush=True);last=monotonic()
    variants={};outputs={}
    for r,ps in placements.items():
        refs=[a.reference for p in ps for a in p.reference_blocks];categories=defaultdict(list);conflicts=[]
        for p in ps:
            rr,ss=risk(p,old)
            for k,vs in rr.items():categories[k].extend(vs)
            if any(vs and k!='same_group_same_orientation' for k,vs in ss.items()):conflicts.append(p.placement_id)
        path=out/('top-chain-'+r+'-placements.jsonl.gz')
        with gzip.open(path,'wt') as f:
            for p in sorted(ps,key=lambda p:(p.source,p.interval,p.orientation,p.placement_id)):f.write(json.dumps(encode(p))+'\n')
        outputs[path.name]=digest(path)
        variants[r]={'placements':len(ps),'sources':len({p.source for p in ps}),'reference_bp':adm._size(refs),'combined_reference_bp':adm._size(before+refs),'new_reference_bp':adm._size(minus(refs,before)),'source_bp_sum':sum(p.interval.length for p in ps),'old_q0_conflict_placements':conflicts,'old_q0_reference_bp':{k:adm._size(vs) for k,vs in categories.items()}}
    report={'schema':'wheat_1A_top_chain_admission_v1','source_receipt_sha256':digest(source/'continuity-admission.json'),'screened_cache_sha256':receipt['outputs'][cache.name]['sha256'],'processed_sources':done,'minimum_chain_bp':500000,'minimum_carried_support_fraction':.2,'maximum_single_foreign_group_support_over_main':.25,'variants':variants,'outputs':outputs,'source_audit':audit,'elapsed_s':monotonic()-began,'mapper_calls':0,'formal_workspace_modified':False}
    write(out/'top-chain-admission.json',report)
    print('TOP_CHAIN_DONE',json.dumps(variants),flush=True)
    return report
