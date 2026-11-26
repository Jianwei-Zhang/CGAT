"""Actual fresh Q0 admission on preregistered local source cohorts, not the frozen placement shortcut."""
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from time import monotonic
import gzip,json,sys

from probe_wheat_native_pair_scope import checked
from census_wheat_q0_fork import bounded,bind,require
from lgz_core import q0_admission as admission
from lgz_core.common import canonical_json,sha256_file
from lgz_core.q0_paths import PairLink
from lgz_core.q0_retained_hits import _checked_line,retained_geometry_cache
from lgz_core.q0_sources import SourceKey
from lgz_core.q0_threshold_questions import questions
from lgz_core.q0_threshold_acceptance import record
from plan_wheat_panel_neighborhoods import PANEL,INDIRECT,pinned_panel

HOOD='bcf5a6370946d0e2dff0557511143eba9cd5a06c196a4a800ae4252e001f4ccd'

HOODS={PANEL:HOOD, INDIRECT:'fa5f6891eb1b5423ade9214b1acb7bd9f59d269dd5e8d4697e9a632303f2bd1c'}

def neighborhood(owner):
    raw=(owner/'neighborhoods.json').read_bytes(); h=json.loads(raw)
    require(HOODS.get(h['panel'])==sha256(raw).hexdigest(),'unknown panel/neighborhood pair');return h

def prepare(owner,snap,root,orig,regional,spools,names,hood):
    inv={r['path']:r for r in snap['files']};files=[];counts=Counter()
    with gzip.open(owner/'common-rows.gz','xb',compresslevel=1) as out:
        def emit(i,raw):out.write(str(i).encode()+b'\t'+raw)
        for rel,qd,td,*_ in [*orig,*regional]:
            i=len(files);files.append((rel,qd,td,'pair'));src=spools[rel][3]
            with src.open('rb') as f:
                for row in f:emit(i,row);counts['pair']+=1
        for ds in sorted(k for k in names if k is not None):
            rel=f'runs/{ds}_vs_ref/result.paf';ident=inv[rel];h=sha256();i=len(files);files.append((rel,ds,None,'reference'))
            with (root/rel).open('rb') as f:
                for n,line in enumerate(f,1):
                    h.update(line)
                    if line.split(b'\t',1)[0] in names[ds]:emit(i,str(n).encode()+b'\t'+line);counts['reference']+=1
            require(h.hexdigest()==ident['sha256'] and (root/rel).stat().st_size==ident['size'],'foreign reference PAF')
    data=dict(schema='wheat_panel_fresh_common_v1',neighborhoods=HOODS[hood['panel']],panel=hood['panel'],selection=hood['selection'],rows_sha256=sha256_file(owner/'common-rows.gz'),files=files,rows=counts)
    with (owner/'common.json').open('x') as f:json.dump(data,f,sort_keys=True,separators=(',',':'));f.write('\n')


def readhit(raw,rel,n,qn,tn):return _checked_line(raw.decode(),rel,rel,n,('['+canonical_json(rel)+',').encode('ascii'),qn,tn,CACHE)


def select_case(spec):
    start=monotonic();subset=set(spec['parts']);case=next(v for v in PLAN['cases'] if v['join']==spec['join']);sources={BYID[k] for k in subset}; sequences={s:CAT.sequences[s] for s in sources};parts={k:CAT.parts[k] for k in sorted(subset)}
    refhits={s:REFS[s] for s in sources};background=[z for z in COMMON if z.query_source in sources and z.target_source in sources];assignment=[dict(dataset_name=s.dataset,seq_name=s.contig,assigned_chr_name=c) for k,s in BYID.items() if k in subset for c in LOOKUP[k]['original_assigned_chromosomes']];results={}
    for label in ('original_background','full','reduced'):
        links=tuple(background+[z for z in ARMS[label] if z.query_source in sources and z.target_source in sources]); data=admission.EvidenceInput(sequences,parts,RLENS,refhits,links,(),{},'private-paired-local-'+label)
        draft=admission.select_request_paths(data,screen_threads=1);frontier,counts=questions(data,draft,assignment);selected={}; old_observed=False
        for c,result in draft.paths.items():
            path=result.path
            if path is None:continue
            selected[c]={'slices':[[s.source.dataset,s.source.contig,s.orientation,s.interval.start,s.interval.end] for s in path.slices],'joins':[j.kind for j in path.joins]}
            if c!=case['chromosome']:continue
            for l,j,r in zip(path.slices,path.joins,path.slices[1:]):
                if (l.source,r.source)==(BYID[case['left']],BYID[case['right']]) and (l.orientation,r.orientation)==(case['left_strand'],case['right_strand']) and j.kind==case['kind']:
                    old_observed|=(l.interval.end if l.orientation=='+' else l.interval.start,r.interval.start if r.orientation=='+' else r.interval.end)==(case['left_cut'],case['right_cut'])
        placed=sorted((p.segment_id,p.chromosome,p.orientation,p.interval.start,p.interval.end,p.localization_kind) for p in draft.admission.placements)
        results[label]=dict(frozen_junction_reproduced=old_observed,placed=placed,selected=selected,request=record(frontier),counts=counts,background_rows=len(background),total_rows=len(links))
    return dict(stratum=case['stratum'],group=case['chromosome'],join=case['join'],sources=len(subset),local_source_bp=spec['bp'],same_placements=results['full']['placed']==results['reduced']['placed'],same_selected=results['full']['selected']==results['reduced']['selected'],same_request=results['full']['request']==results['reduced']['request'],arms=results,elapsed_s=round(monotonic()-start,3))


def run(owner,stage,mapped):
    global PLAN,LOOKUP,CAT,BYID,REFS,COMMON,ARMS,CACHE,RLENS
    import review_wheat_frozen_group as worker
    from bound_regional_scope_from_native_receipts import LOOKUP_SHA
    common=json.loads((stage/'common.json').read_bytes());hood=neighborhood(stage);PLAN,pin=pinned_panel(mapped/'panel.json');recording=json.loads((mapped/'mapping.json').read_bytes());require(common['neighborhoods']==HOODS[pin] and common['panel']==hood['panel']==pin==recording['panel'] and common['selection']==PLAN['selection'] and sha256_file(stage/'common-rows.gz')==common['rows_sha256'],'unbound panel inputs')
    base=owner.parent; lookup=base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json';LOOKUP=checked(lookup,LOOKUP_SHA);snap,root,parts,order,lens=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',lookup);subset={k for r in hood['cases'] for k in r['parts']};BYID={k:order[parts[k][0]] for k in subset};worker.BYID=BYID;CAT=worker.genome_subset(root,snap,parts,subset);ref,=(r for r in snap['files'] if r['path'].startswith('data/reference/') and r['path'].endswith('.fai'));RLENS={r[0]:int(r[1]) for line in bounded(root/ref['path'],4<<20,ref['sha256']).decode().splitlines() if (r:=line.split('\t'))}
    names=defaultdict(dict);keys=defaultdict(dict);queries=set(PLAN['queries']);qsrc={BYID[k] for k in queries}; CACHE=retained_geometry_cache()
    for k,s in BYID.items():
        n=lens[s];names[s.dataset][s.contig]=(s.contig,n);keys[s.dataset][s.contig]=s;names[None][k]=(k,n);keys[None][k]=s
    refnames={c:(c,n) for c,n in RLENS.items()}; REFS=defaultdict(list);COMMON=[];observed=Counter();heldout=0
    old_tested=[]
    with gzip.open(stage/'common-rows.gz','rb') as f:
        for line in f:
            i,n,raw=line.split(b'\t',2);rel,qd,td,kind=common['files'][int(i)];observed[kind]+=1;hit=readhit(raw,rel,int(n),names[qd],refnames if kind=='reference' else names[td]);q=keys[qd][hit.query_name]
            if kind=='reference':REFS[q].append(hit);continue
            t=keys[td][hit.target_name]
            if q in qsrc or t in qsrc:heldout+=1;old_tested.append(PairLink(hit,q,t));continue  # also excludes reciprocals/duplicate regional projections
            COMMON.append(PairLink(hit,q,t))
    require(observed==common['rows'],'missing background input');ARMS={'original_background':old_tested}
    for arm in ('full','reduced'):
        p=mapped/(arm+'.paf');digest=sha256();links=[]
        with p.open('rb') as f:
            for n,line in enumerate(f,1):
                digest.update(line);a=line.split(b'\t',6);q=a[0].decode();t=a[5].decode();require(q in queries,'unknown panel query')
                if t not in subset:continue
                z=readhit(line,p.name,n,names[None],names[None]);links.append(PairLink(z,BYID[q],BYID[t]))
        require(digest.hexdigest()==recording['mapper'][arm]['paf_sha256'],'unbound native output');ARMS[arm]=links
    with ProcessPoolExecutor(max_workers=8,mp_context=get_context('fork')) as pool:cases=list(pool.map(select_case,hood['cases']))
    doc=dict(schema='wheat_paired_local_fresh_admission_v1',panel=pin,neighborhoods=HOODS[pin],common_sha256=sha256_file(stage/'common.json'),mapping_sha256=sha256_file(mapped/'mapping.json'),excluded_old_pair_rows=heldout,cases=cases,published_q0=False,scope='All original reference hits and fresh Q0 placement/path/next request in the predeclared local source cohorts. Not full wheat or either retired parent.')
    with (owner/'readmission.json').open('x') as f:json.dump(doc,f,sort_keys=True,separators=(',',':'));f.write('\n')

if __name__=='__main__':run(Path.cwd(),*map(Path,sys.argv[1:3]))
