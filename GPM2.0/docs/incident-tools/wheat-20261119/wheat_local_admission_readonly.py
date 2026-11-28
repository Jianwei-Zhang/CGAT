"""1A local-chain admission counterfactual; existing all-chromosome PAF only.

Preserves identity, competing-locus masks, complexity, minimum support, MAPQ
and exact collinearity. Changes only whole-source unique-group admission into
source regions separated by surviving foreign chr/strand anchors. No mapping,
no full formal admission propagation and no production writes.
"""
import argparse,gzip,json,multiprocessing as mp,os,re
from bisect import bisect_left,bisect_right
from collections import defaultdict,Counter
from pathlib import Path
from time import monotonic
from hashlib import sha256
import wheat_reference_funnel_readonly as frozen
from wheat_local_chain_primitives import chain,clipped
from lgz_core import q0_admission as adm
from lgz_core.q0_sources import SourceKey,SourceSegment,Interval,merged_intervals,subtract_intervals
from lgz_core.q0_reference_competition import reference_masks
from lgz_core.q0_retained_hits import read_retained_paf,retained_names,retained_geometry_cache
from wheat_selection_checkpoint import encode,decode
from compare_wheat_local_only_paths import load_arm

GROUP='1A';PART_ID={}


def overlap_bp(intervals,others):
    left=merged_intervals(intervals);right=merged_intervals(others);i=j=total=0
    while i<len(left) and j<len(right):
        a,b=left[i],right[j];total+=max(0,min(a.end,b.end)-max(a.start,b.start))
        if a.end<=b.end:i+=1
        else:j+=1
    return total


def index_rows(rows,key=lambda a:a):
    rows=sorted(rows,key=lambda a:(key(a).start,key(a).end));starts=[];ends=[];farthest=-1
    for a in rows:
        iv=key(a);starts.append(iv.start);farthest=max(farthest,iv.end);ends.append(farthest)
    return rows,starts,ends


def nearby(index,region):
    rows,starts,ends=index
    return rows[bisect_right(ends,region.start):bisect_left(starts,region.end)]


def one(source):
    policy=frozen.POLICY;n=frozen.FAI[source][0];minimum=min(policy.minimum_anchor_bp,n);blocks=[]
    for hit in frozen.HITS.get(source,()):
        identity=hit.matches/hit.block_length
        if identity<policy.minimum_reference_identity:continue
        for b in hit.aligned_blocks():
            if b.operation!='X':blocks.append(adm._RefBlock(b.query,b.target,hit.target_name,hit.strand,hit.evidence_id,identity,hit.mapping_quality))
    masks,ambiguous=reference_masks(blocks,policy.competing_identity_margin)
    target_support=adm._size(iv for b,vs in zip(blocks,masks) if b.chromosome==GROUP for iv in vs)
    if target_support<minimum:return {'source':[source.dataset,source.contig],'source_bp':n,'dna_verified_bp':0,'skipped':'insufficient_masked_target_support','rows':[],'placements':{'regional':[],'dominant90':[]},'target_qualified_reference':[]}
    dna=frozen.sequence(source);groups=defaultdict(list);high=defaultdict(list);bounds=None
    for b,spans in zip(blocks,masks):
        if not spans:continue
        key=b.chromosome,b.strand
        if spans[0].length<minimum:
            if bounds is None:bounds=adm._possible_support_bp(blocks,masks,minimum)
            if bounds[key]<minimum:continue
        for iv in spans:
            for clean in adm._complex_intervals(dna,iv,policy):
                groups[key].append(adm.ReferenceAnchor(clean,adm._project(b.query,b.target,b.strand,clean),b.evidence_id))
                if b.mapq is not None and b.mapq>=policy.minimum_reference_mapq:high[key].append(clean)
    groups={key:tuple(sorted(set(rows),key=lambda a:(a.source,a.reference,a.evidence_id))) for key,rows in groups.items() if adm._size(a.source for a in rows)>=minimum}
    high={key:merged_intervals(rows) for key,rows in high.items() if key in groups}
    support={key:adm._size(a.source for a in rows) for key,rows in groups.items()};total_support=adm._size(a.source for rows in groups.values() for a in rows)
    dominant=min(groups,key=lambda k:(-support[k],k)) if groups else None
    dominant=dominant if dominant is not None and support[dominant]>=.9*total_support else None
    part=SourceSegment(PART_ID[source],source,Interval(0,n),frozen.LOOKUP[source]['sequence_sha256'],0,'start','end')
    output={'regional':[],'dominant90':[]};diagnostics=[];ambiguous_index=index_rows(ambiguous)
    for key,anchors in groups.items():
        if key[0]!=GROUP:continue
        foreign=merged_intervals(a.source for other,rows in groups.items() if other!=key for a in rows)
        cross=merged_intervals(a.source for other,rows in groups.items() if other[0][-1] in 'ABD' and other[0][-1]!=GROUP[-1] for a in rows)
        forbidden=foreign;anchor_index=index_rows(anchors,lambda a:a.source);high_index=index_rows(high.get(key,()))
        for region in subtract_intervals(part.interval,forbidden):
            local=clipped(nearby(anchor_index,region),region,key[1]);chosen=chain(local,key[1]);bp=adm._size(a.source for a in chosen)
            if bp<minimum:continue
            high_bp=overlap_bp((a.source for a in chosen),nearby(high_index,region))
            if high_bp<minimum:continue
            hull=adm._hull(a.source for a in chosen)
            p=adm._placement(part,key[0],key[1],hull,(a.source for a in chosen),chosen,(a.evidence_id for a in chosen),kind='diagnostic_local_collinear_chain')
            if not adm._ordered(chosen,key[1]) or not region.contains(hull):raise ValueError('foreign qualified anchor crossed')
            row={'placement_id':p.placement_id,'interval':[hull.start,hull.end],'orientation':key[1],'source_support_bp':bp,'reference_bp':adm._size(a.reference for a in chosen),'high_mapq_support_bp':high_bp,'chain_fraction_of_region_support':bp/max(1,adm._size(a.source for a in local)),'source_hull_bp':hull.length,'foreign_qualified_anchor_overlap_bp':0,'cross_ABD_qualified_anchor_overlap_bp':0,'all_locus_conflict_union_carried_bp':overlap_bp((hull,),nearby(ambiguous_index,hull)),'dominant90':key==dominant and bp>=.9*adm._size(a.source for a in local)}
            diagnostics.append(row);output['regional'].append(encode(p))
            if row['dominant90']:output['dominant90'].append(encode(p))
    return {'source':[source.dataset,source.contig],'source_bp':n,'dna_verified_bp':n,'original_assignment':frozen.LOOKUP[source].get('original_assigned_chromosomes',[]),'group_support':[[k[0],k[1],support[k],adm._size(high.get(k,()))] for k in sorted(groups)],'target_qualified_reference':[[iv.start,iv.end] for iv in merged_intervals(a.reference for key,rows in groups.items() if key[0]==GROUP for a in rows)],'rows':diagnostics,'placements':output}


def run(base,owner,workers):
    began=monotonic();snap=frozen.checked(base/'q0-latest-fork-20261123-1435/control/snapshot.json',frozen.SNAP);frozen.ROOT=Path(snap['source']);lookup=frozen.checked(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',frozen.LOOK);files={r['path']:r for r in snap['files']};before={}
    frozen.LOOKUP={SourceKey(v['dataset'],v['contig']):v for v in lookup.values()};PART_ID.update({SourceKey(v['dataset'],v['contig']):k for k,v in lookup.items()});frozen.FAI={}
    for ds in sorted({s.dataset for s in frozen.LOOKUP}):
        for rel in ('data/datasets/'+ds+'.fa.fai','runs/'+ds+'_vs_ref/result.paf'):
            p=frozen.ROOT/rel
            if frozen.digest(p)!=files[rel]['sha256']:raise ValueError('changed input '+rel)
            before[p]=frozen.signature(p)
        p=frozen.ROOT/('data/datasets/'+ds+'.fa');before[p]=frozen.signature(p)
        if p.stat().st_size!=files[str(p.relative_to(frozen.ROOT))]['size']:raise ValueError('source FASTA size')
        for line in (frozen.ROOT/('data/datasets/'+ds+'.fa.fai')).read_text().splitlines():
            name,n,offset,bases,width,*_=line.split('\t');frozen.FAI[SourceKey(ds,name)]=tuple(map(int,(n,offset,bases,width)))
    if {k:v[0] for k,v in frozen.FAI.items()}!={k:v['length'] for k,v in frozen.LOOKUP.items()}:raise ValueError('FAI lookup differs')
    rp=frozen.ROOT/'data/reference/IWGSC.fa.fai'
    if frozen.digest(rp)!=files[str(rp.relative_to(frozen.ROOT))]['sha256']:raise ValueError('reference FAI differs')
    lengths={r.split('\t')[0]:int(r.split('\t')[1]) for r in rp.read_text().splitlines()};frozen.HITS=defaultdict(list);geometry=retained_geometry_cache()
    for ds in sorted({s.dataset for s in frozen.FAI}):
        rel='runs/'+ds+'_vs_ref/result.paf'
        for hit in read_retained_paf(frozen.ROOT/rel,artifact=rel,query_names=retained_names({s.contig:n[0] for s,n in frozen.FAI.items() if s.dataset==ds}),target_names=retained_names(lengths),short_geometry=geometry):frozen.HITS[SourceKey(ds,hit.query_name)].append(hit)
        print('LOCAL_CHAIN_PAF_LOADED',ds,round(monotonic()-began,1),flush=True)
    sources=sorted(s for s,hits in frozen.HITS.items() if any(h.target_name==GROUP for h in hits));total_bp=sum(frozen.FAI[s][0] for s in sources)
    print('LOCAL_CHAIN_SCREEN_TARGETS',len(sources),total_bp,flush=True);maps={k:frozen.Bitmap({GROUP:lengths[GROUP]}) for k in ('qualified','regional','dominant90','frozen')};counts=Counter();done=0;last=monotonic();mode_counts=Counter();source_labels={k:Counter() for k in ('regional','dominant90')};warnings=Counter()
    streams={k:gzip.open(owner/(k+'-placements.jsonl.gz'),'wt',compresslevel=1) for k in ('regional','dominant90')}
    try:
        with gzip.open(owner/'local-chain-source-audit.jsonl.gz','wt',compresslevel=1) as audit,mp.get_context('fork').Pool(workers) as pool:
            for row in pool.imap_unordered(one,sources,chunksize=1):
                for lo,hi in row.pop('target_qualified_reference'):maps['qualified'].add(GROUP,lo,hi)
                outputs=row.pop('placements');done+=1;counts['processed_source_bp']+=row['source_bp'];counts['dna_verified_bp']+=row['dna_verified_bp'];counts['sources_with_regional_placements']+=bool(outputs['regional']);counts['sources_with_dominant90_placements']+=bool(outputs['dominant90']);counts['skipped_before_DNA']+=bool(row.get('skipped'))
                for key,encoded in outputs.items():
                    for item in encoded:
                        p=decode(item);streams[key].write(json.dumps(item,separators=(',',':'))+'\n');mode_counts[key]+=1
                        for a in p.reference_blocks:maps[key].add(GROUP,a.reference.start,a.reference.end)
                        match=re.match(r'JM19flye([ABD])_',p.source.contig);label=match.group(1) if match else 'unlabelled';source_labels[key][label]+=p.interval.length
                warnings['regional_all_locus_conflict_union_carried_bp_sum']+=sum(r['all_locus_conflict_union_carried_bp'] for r in row['rows'])
                warnings['regional_foreign_qualified_anchor_overlap_bp_sum']+=sum(r['foreign_qualified_anchor_overlap_bp'] for r in row['rows'])
                warnings['regional_cross_ABD_qualified_anchor_overlap_bp_sum']+=sum(r['cross_ABD_qualified_anchor_overlap_bp'] for r in row['rows'])
                audit.write(json.dumps(row,separators=(',',':'))+'\n')
                if monotonic()-last>=45:
                    frozen.write(owner/'local-chain-progress.json',{'sources_done':done,'sources_total':len(sources),'source_bp_total':total_bp,'counts':dict(counts),'placements':dict(mode_counts),'elapsed_s':round(monotonic()-began,1)});print('LOCAL_CHAIN_PROGRESS',done,len(sources),dict(mode_counts),round(monotonic()-began,1),flush=True);last=monotonic()
    finally:
        for f in streams.values():f.close()
    main=base/'q0-whole-local-maps.soHq9Z6J';_,_,records,_,_=load_arm(main,'d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4','whole-wheat-local-supplement-v1');frozen_count=0
    with (main/'selection/admission.jsonl').open('rb') as f,gzip.open(owner/'frozen-placements.jsonl.gz','wt',compresslevel=1) as out:
        f.readline()
        for raw in f:
            item=json.loads(raw)
            if isinstance(item,list):break
            p=decode(item)
            if p.chromosome!=GROUP:continue
            if records[GROUP][p.placement_id]!=sha256(raw).hexdigest():raise ValueError('frozen admission changed')
            out.write(raw.decode());frozen_count+=1
            for a in p.reference_blocks:maps['frozen'].add(GROUP,a.reference.start,a.reference.end)
    coverage={k:sum(b.counts().values()) for k,b in maps.items()}
    if coverage['qualified']!=445132656 or coverage['frozen']!=129162948:raise ValueError('1A earlier funnel not reproduced '+str(coverage))
    for path,pin in before.items():
        if frozen.signature(path)!=pin:raise ValueError('source changed during read-only audit')
    if warnings['regional_foreign_qualified_anchor_overlap_bp_sum']:raise ValueError('foreign-anchor conflict')
    outputs={p.name:{'sha256':frozen.digest(p),'bytes':p.stat().st_size} for p in owner.glob('*-placements.jsonl.gz')};p=owner/'local-chain-source-audit.jsonl.gz';outputs[p.name]={'sha256':frozen.digest(p),'bytes':p.stat().st_size}
    report={'schema':'wheat_local_chain_admission_diagnostic_v1','group':GROUP,'source_count':len(sources),'counts':dict(counts),'placement_counts':dict(mode_counts,frozen=frozen_count),'reference_coverage_bp':coverage,'gain_loss_vs_frozen':{k:{'gained_bp':maps[k].different(maps['frozen']),'lost_bp':maps['frozen'].different(maps[k])} for k in ('regional','dominant90')},'source_label_bp_sum':{k:dict(v) for k,v in source_labels.items()},'safety':dict(warnings),'outputs':outputs,'elapsed_s':monotonic()-began,'mapper_calls':0,'formal_workspace_modified':False,'policy':{'admission':vars(frozen.POLICY),'dominance_fraction':.9,'conflict_rule':'split source intervals at all surviving foreign chr/strand anchors','chain':'maximum weighted source-disjoint exact collinear actual anchors','carried_sequence':'anchor hull may bridge unsupported sequence and overlap the all-locus conflict union; that union includes conflicts rejected only for weaker hits, not a veto on stronger qualifying anchors'},'limitations':['Reference footprints are actual paired-block unions, not hulls.','These are reference-only counterfactual placements, not full formal admission propagation.','No independent truth assembly; zero surviving-anchor conflict does not prove no biological cross-subgenome misplacement.','Flye A/B/D name labels are flags, not ground truth.','Original identity/competition/complexity/MAPQ/collinearity gates remain; central-99% trimming is not used for admission.','The interval chain is conservative about overlapping anchors and does not certify global optimum.','Dominant90 additionally requires the local chain to retain at least 90% of its region group support.','The all-locus conflict union includes inferior-hit conflicts; each retained anchor still passed its own original identity-margin mask.','Worker completion order is not scientific candidate order; subsequent selection must sort candidate placements deterministically.']}
    frozen.write(owner/'local-admission.json',report);print('LOCAL_ADMISSION_DONE',json.dumps(coverage),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    if a.owner.resolve().parent!=a.base.resolve() or not a.owner.name.startswith('q0-local-chain-'):raise ValueError('isolated owner required')
    run(a.base.resolve(),a.owner.resolve(),a.workers)
