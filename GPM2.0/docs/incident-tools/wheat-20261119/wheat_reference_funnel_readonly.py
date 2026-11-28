"""Frozen reference-admission funnel. No mapper, selection or production writes.

Coverage uses exact per-reference bitmaps, not sums of PAF lengths. Competing
masks precede complexity in the actual engine. The same-subgenome counterfactual
is reported separately; it does not replace actual all-locus masking.
"""
import argparse
from collections import defaultdict, Counter
from hashlib import sha256
import json
import multiprocessing as mp
import os
from pathlib import Path
from time import monotonic
from lgz_core import q0_admission as adm
from lgz_core.q0_reference_competition import reference_masks
from lgz_core.q0_sources import SourceKey, Interval, merged_intervals
from lgz_core.q0_retained_hits import read_retained_paf, retained_names, retained_geometry_cache

SNAP='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'
LOOK='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'
STAGES=('paf_target_envelope','paired_blocks_all_identity','identity_pass_non_X',
        'same_subgenome_mask_only','all_competition_mask','minimum_possible_support','complexity_pass',
        'minimum_anchor_group','unique_chr_strand','high_mapq_group','collinear_reference_seed')
HITS={};FAI={};LOOKUP={};ROOT=None;POLICY=adm.AdmissionPolicy()


def digest(path):
    h=sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()


def checked(path,pin):
    if digest(path)!=pin:raise ValueError('changed input '+str(path))
    return json.loads(path.read_text())


def signature(path):
    s=path.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def project(block,span):
    return adm._project(block.query,block.target,block.strand,span)


def sequence(source):
    n,offset,bases,width=FAI[source];path=ROOT/('data/datasets/'+source.dataset+'.fa')
    count=((n-1)//bases)*width+(n-1)%bases+1
    with path.open('rb') as stream:stream.seek(offset);raw=stream.read(count)
    text=raw.replace(b'\n',b'').replace(b'\r',b'').decode('ascii').upper()
    if len(text)!=n or sha256(text.encode()).hexdigest()!=LOOKUP[source]['sequence_sha256']:
        raise ValueError('source sequence identity changed '+str(source))
    return text


def one(source):
    stages={k:defaultdict(list) for k in STAGES};blocks=[];n=FAI[source][0]
    for hit in HITS.get(source,()):
        stages['paf_target_envelope'][hit.target_name].append(hit.target)
        good=hit.matches/hit.block_length>=POLICY.minimum_reference_identity
        for b in hit.aligned_blocks():
            stages['paired_blocks_all_identity'][hit.target_name].append(b.target)
            if good and b.operation!='X':
                stages['identity_pass_non_X'][hit.target_name].append(b.target)
                blocks.append(adm._RefBlock(b.query,b.target,hit.target_name,hit.strand,hit.evidence_id,hit.matches/hit.block_length,hit.mapping_quality))
    # Independent within-subgenome masks: isolates the additional effect of
    # cross-A/B/D competition in an explicitly same-subgenome-first decomposition.
    categories=defaultdict(list)
    for b in blocks:categories[b.chromosome[-1] if b.chromosome[-1] in 'ABD' else b.chromosome].append(b)
    for subset in categories.values():
        masks,_=reference_masks(subset,POLICY.competing_identity_margin)
        for b,spans in zip(subset,masks):
            stages['same_subgenome_mask_only'][b.chromosome].extend(project(b,v) for v in spans)
    masks,_=reference_masks(blocks,POLICY.competing_identity_margin)
    groups=defaultdict(list);high=defaultdict(list);minimum=min(POLICY.minimum_anchor_bp,n)
    dna=None;bounds=None
    for b,spans in zip(blocks,masks):
        stages['all_competition_mask'][b.chromosome].extend(project(b,v) for v in spans)
        if not spans:continue
        key=b.chromosome,b.strand
        if spans[0].length<minimum:
            if bounds is None:bounds=adm._possible_support_bp(blocks,masks,minimum)
            if bounds[key]<minimum:continue
        stages['minimum_possible_support'][b.chromosome].extend(project(b,v) for v in spans)
        if dna is None:dna=sequence(source)
        for span in spans:
            for iv in adm._complex_intervals(dna,span,POLICY):
                anchor=adm.ReferenceAnchor(iv,project(b,iv),b.evidence_id)
                groups[key].append(anchor);stages['complexity_pass'][b.chromosome].append(anchor.reference)
                if b.mapq is not None and b.mapq>=POLICY.minimum_reference_mapq:high[key].append(iv)
    groups={k:tuple(sorted(set(v),key=lambda a:(a.source,a.reference,a.evidence_id))) for k,v in groups.items()
            if adm._size(a.source for a in v)>=minimum}
    high={k for k in groups if adm._size(high[k])>=minimum}
    for (g,_),anchors in groups.items():stages['minimum_anchor_group'][g].extend(a.reference for a in anchors)
    stats=Counter(source_count=1,reference_hit_rows=len(HITS.get(source,())))
    if not groups:stats['no_qualified_group']=1
    elif len(groups)>1:stats['multiple_chr_strand_groups']=1
    else:
        (g,strand),anchors=next(iter(groups.items()))
        stages['unique_chr_strand'][g].extend(a.reference for a in anchors)
        if high:
            stages['high_mapq_group'][g].extend(a.reference for a in anchors)
            if adm._ordered(anchors,strand):
                stages['collinear_reference_seed'][g].extend(a.reference for a in anchors)
                stats['direct_seed_sources']=1
                if adm._size(a.source for a in anchors)/n<POLICY.minimum_whole_support_fraction:stats['seed_hull_not_whole_source']=1
            else:stats['noncollinear_groups']=1
        else:stats['no_high_mapq_support_group']=1
    return {k:{g:[(v.start,v.end) for v in merged_intervals(rows)] for g,rows in by.items()} for k,by in stages.items()},dict(stats)


class Bitmap:
    def __init__(self,lengths):self.lengths=lengths;self.bits={}
    def add(self,g,a,b):
        if not 0<=a<b<=self.lengths[g]:raise ValueError('reference bounds')
        buf=self.bits.setdefault(g,bytearray())
        if not buf:buf.extend(bytes((self.lengths[g]+7)//8))
        while a<b and a%8:buf[a//8]|=1<<(a%8);a+=1
        end=b//8
        if end>a//8:buf[a//8:end]=b'\xff'*(end-a//8);a=end*8
        while a<b:buf[a//8]|=1<<(a%8);a+=1
    def counts(self):
        return {g:sum(int.from_bytes(buf[i:i+(1<<20)],'little').bit_count() for i in range(0,len(buf),1<<20)) for g,buf in self.bits.items()}
    def different(self,other):
        count=0
        for g in self.lengths:
            a=self.bits.get(g,b'');b=other.bits.get(g,b'')
            for i in range(0,max(len(a),len(b)),1<<20):
                x=int.from_bytes(a[i:i+(1<<20)],'little');y=int.from_bytes(b[i:i+(1<<20)],'little')
                count+=(x&~y).bit_count()
        return count


def write(path,doc):
    tmp=path.with_suffix('.partial');tmp.write_text(json.dumps(doc,indent=2,sort_keys=True)+'\n');os.replace(tmp,path)


def run(base,owner,workers):
    global HITS,FAI,LOOKUP,ROOT
    start=monotonic();snapshot=checked(base/'q0-latest-fork-20261123-1435/control/snapshot.json',SNAP);ROOT=Path(snapshot['source'])
    lookup=checked(base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json',LOOK)
    LOOKUP={SourceKey(v['dataset'],v['contig']):v for v in lookup.values()};rows={r['path']:r for r in snapshot['files']}
    lengths={};before={};datasets=sorted({s.dataset for s in LOOKUP})
    for ds in datasets:
        for relative in ('data/datasets/'+ds+'.fa.fai','runs/'+ds+'_vs_ref/result.paf'):
            path=ROOT/relative
            if digest(path)!=rows[relative]['sha256']:raise ValueError('source differs '+relative)
            before[path]=signature(path)
        fa=ROOT/('data/datasets/'+ds+'.fa');before[fa]=signature(fa)
        if fa.stat().st_size!=rows[str(fa.relative_to(ROOT))]['size']:raise ValueError('FASTA size')
        for line in (ROOT/('data/datasets/'+ds+'.fa.fai')).read_text().splitlines():
            name,n,offset,bases,width,*_=line.split('\t');FAI[SourceKey(ds,name)]=tuple(map(int,(n,offset,bases,width)))
    rp=ROOT/'data/reference/IWGSC.fa.fai'
    if digest(rp)!=rows['data/reference/IWGSC.fa.fai']['sha256']:raise ValueError('reference FAI')
    lengths={r.split()[0]:int(r.split()[1]) for r in rp.read_text().splitlines()}
    if {s:v[0] for s,v in FAI.items()}!={s:v['length'] for s,v in LOOKUP.items()}:raise ValueError('lookup/FAI mismatch')
    HITS=defaultdict(list);geometry=retained_geometry_cache()
    for ds in datasets:
        rel='runs/'+ds+'_vs_ref/result.paf'
        for hit in read_retained_paf(ROOT/rel,artifact=rel,query_names=retained_names({s.contig:n[0] for s,n in FAI.items() if s.dataset==ds}),target_names=retained_names(lengths),short_geometry=geometry):HITS[SourceKey(ds,hit.query_name)].append(hit)
        print('REFERENCE_PAF_LOADED',ds,len(HITS),round(monotonic()-start,1),flush=True)
    # Fork before allocating parent bitmaps; workers inherit only immutable hit
    # inventory and fetch/verify one source sequence at a time from the frozen FAI.
    stages={};stats=Counter();done=0;last=monotonic()
    with mp.get_context('fork').Pool(workers) as pool:
        for result,counts in pool.imap_unordered(one,sorted(FAI),chunksize=1):
            for name,groups in result.items():
                bitmap=stages.setdefault(name,Bitmap(lengths))
                for g,spans in groups.items():
                    for a,b in spans:bitmap.add(g,a,b)
            stats.update(counts);done+=1
            if monotonic()-last>60:
                write(owner/'progress.json',{'sources_done':done,'sources_total':len(FAI),'elapsed_s':round(monotonic()-start,1),'counts':dict(stats)})
                print('REFERENCE_FUNNEL_PROGRESS',done,'/',len(FAI),round(monotonic()-start,1),flush=True);last=monotonic()
    # Use actual frozen admission; do not assume its final extension/splitting is
    # a strict subset of the initial direct seeds. Report both lost AND gained.
    from compare_wheat_local_only_paths import load_arm
    from wheat_selection_checkpoint import decode
    main=base/'q0-whole-local-maps.soHq9Z6J'
    summary,_,records,paths,_=load_arm(main,'d23a49af479b6c9b81916518e8034d4044ea31b5c97229c5d0ce1624138fc9d4','whole-wheat-local-supplement-v1')
    final=Bitmap(lengths)
    with (main/'selection/admission.jsonl').open('rb') as f:
        f.readline()
        for raw in f:
            row=json.loads(raw)
            if isinstance(row,list):break
            p=decode(row)
            if records[p.chromosome][p.placement_id]!=sha256(raw).hexdigest():raise ValueError('admission changed')
            for a in p.reference_blocks:final.add(p.chromosome,a.reference.start,a.reference.end)
    stages['final_frozen_admission']=final
    counts={k:v.counts() for k,v in stages.items()};totals={k:sum(v.values()) for k,v in counts.items()}
    if totals['final_frozen_admission']!=5108838629:raise ValueError('frozen final footprint differs')
    order=[k for k in STAGES if k!='same_subgenome_mask_only'];losses={a+' -> '+b:stages[a].different(stages[b]) for a,b in zip(order,order[1:])}
    for a,b in zip(order,order[1:]):
        if stages[b].different(stages[a]):raise ValueError('unexpected nonmonotone reference filter '+b)
    for path,old in before.items():
        if signature(path)!=old:raise ValueError('input changed during audit '+str(path))
    report={'schema':'wheat_reference_funnel_readonly_v1','reference_total_bp':sum(lengths.values()),'stages_bp':totals,'per_chr':counts,'sequential_losses_bp':losses,
        'no_raw_paf_envelope_bp':sum(lengths.values())-totals['paf_target_envelope'],
        'cross_ABD_extra_after_same_subgenome_bp':stages['same_subgenome_mask_only'].different(stages['all_competition_mask']),
        'seed_to_final_lost_bp':stages['collinear_reference_seed'].different(final),'seed_to_final_gained_bp':final.different(stages['collinear_reference_seed']),
        'counts':dict(stats),'elapsed_s':round(monotonic()-start,1),'mapper_calls':0,'selection_calls':0,'formal_workspace_modified':False,
        'snapshot':SNAP,'summary':summary['selection_chain'],'notes':['All totals are reference-coordinate unions across datasets, not sums of alignment lengths.',
        'Actual order: identity/non-X, competition, complexity, minimum support, one chr/strand, high-MAPQ group, collinearity.',
        '20% whole support selects whole contig versus anchor hull; not outright rejection.',
        'MAPQ is sufficient accumulated high-MAPQ anchor support in the surviving group, not a per-base mask.',
        'Same-subgenome-only mask is a counterfactual; extra cross-ABD loss is order-dependent attribution, not additive independent blame.',
        'minimum_possible_support isolates the safe small-group upper-bound shortcut before complexity; final group minimum is separate.']}
    write(owner/'reference-funnel.json',report);print('REFERENCE_FUNNEL_DONE',json.dumps(totals),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',type=Path);p.add_argument('owner',type=Path);p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    if a.owner.resolve().parent!=a.base.resolve() or a.owner.name.startswith('gpm_server'):raise ValueError('diagnostic owner scope')
    run(a.base.resolve(),a.owner.resolve(),a.workers)
