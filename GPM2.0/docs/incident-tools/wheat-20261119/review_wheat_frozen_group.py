"""Real Q0 review of one frozen wheat path, against its complete chromosome graph (never a main-run receipt)."""
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from types import SimpleNamespace
from time import monotonic
import json, os, shutil, sys, tempfile
from unittest.mock import patch

import refresh_whole_wheat_cached_demand as old
from measure_wheat_junction_bound import frozen, measure
from wheat_selection_checkpoint import need, decode
from lgz_core import q0_junction_review as review, q0_regional_mapping as mapping
from lgz_core.q0_catalog import CandidateCatalog
from lgz_core.q0_paths import PathGraph, PairLink, search_request_path
from lgz_core.q0_retained_hits import _checked_line, retained_geometry_cache
from lgz_core.q0_sources import split_source
from lgz_core.common import canonical_json, sha256_file


def shard(job):
    a,ap,b,bp=job;rows=old.get(a,ap);audit=old.get(b,bp);need([x[0] for x in rows]==[q for q,_ in audit],'different audit order');out=[];n=0
    for (q,rank,lo,hi,ctx,stamp,left,right,reason),(_,entry) in zip(rows,audit):
        eligible=rank not in old.SKIP and rank not in old.FALLBACK and bool(left or right)
        need(eligible==(entry['status']=='verified'),'wrong cohort');n+=eligible
        if not eligible or rank not in RANKS:continue
        w=old.WINDOWS[q];need(old.PARTS[w.segment_id][0]==rank and w.start==lo and w.end==hi and reason is None and ctx==entry['context'],'wrong frame')
        spec=old.checked_leaf(entry['context_file'])['spec'];need(mapping._window_context(w)==spec['query'] and sha256(old.pack_context(ctx,spec,old.PARTS)).hexdigest()==stamp,'wrong target inventory')
        if any(t['segment_id'] in PARTSET for t in spec['targets']):out.append(old.project_one(q,stamp,entry))
    return len(rows),n,out


def filter_one(job):
    rel,qd,td,src,identity=job;dst=old.STAGE/('rows-'+sha256(rel.encode()).hexdigest());h=sha256();n=0
    qnames=NAMES[qd];tnames=NAMES[td];before=old.prep.file_signature(src)
    with src.open('rb') as raw,dst.open('xb') as f:
        for i,line in enumerate(raw,1):
            h.update(line)
            if line.startswith(b'#') or line.isspace():continue
            cells=line.split(b'\t',6)
            if cells[0] in qnames and cells[5] in tnames:f.write(str(i).encode()+b'\t'+line);n+=1
    need(src.stat().st_size==identity['size'] and h.hexdigest()==identity['sha256'] and old.prep.file_signature(src)==before,'old PAF changed: '+rel)
    return rel,qd,td,dst,n


def genome_subset(root,snap,parts,targets):
    rows={r['path']:r for r in snap['files']}; seqs={}; segments={}; indexes={}
    for k in sorted(targets):
        source=BYID[k]; rel='data/datasets/'+source.dataset+'.fa'; fai=rel+'.fai'
        if fai not in indexes:indexes[fai]={x[0]:tuple(map(int,x[1:5])) for line in old.bounded(root/fai,16<<20,rows[fai]['sha256']).decode().splitlines() if (x:=line.split('\t'))}
        n,start,width,stride=indexes[fai][source.contig]
        with (root/rel).open('rb') as f:
            f.seek(start); count=(n-1)//width*stride+(n-1)%width+1;seq=f.read(count).replace(b'\n',b'').replace(b'\r',b'').decode('ascii').upper()
        need(n==len(seq)==parts[k][1] and sha256(seq.encode()).hexdigest()==parts[k][2],'wrong mapped candidate DNA');info=split_source(source,seq);seg,=info.segments;need(not info.adjacencies and seg.segment_id==k,'not whole part');seqs[source]=seq;segments[k]=seg
    return CandidateCatalog({},seqs,segments)


def run(base,owner,stage,chrom,workers):
    global PARTSET,RANKS,NAMES,BYID
    start=monotonic();prior=base/'q0-whole-updated.We9jf3UC';summary,detail,positions,paths=frozen(prior/'selection',prior/'result'); screen=chrom=='all-screen'; cases=[]; placements=[]
    if screen:
        def candidate(group,pid,alt,sides):cases.append((group,pid,alt,sides))
        bound=measure(prior/'selection',prior/'result',on_candidate=candidate,checkpoints=(summary,detail,positions,paths))
        need(bound['eligible_local_windows_upper']==24,'foreign candidate bound')
        placements=list({p.placement_id:p for _,_,_,sides in cases for l,r,_,_ in sides for p in (l,r)}.values())
    else:
        expected=next(p for p in paths if p.chromosome==chrom)
        with (prior/'selection/admission.jsonl').open('rb') as f:
            for pos in positions[chrom]:f.seek(pos);placements.append(decode(json.loads(f.readline())))
    snap,old.ROOT,old.PARTS,order,lens=old.bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json')
    PARTSET={p.segment_id for p in placements};RANKS={old.PARTS[k][0] for k in PARTSET};BYID={k:order[v[0]] for k,v in old.PARTS.items()};NAMES=defaultdict(dict)
    for k in PARTSET:
        s=BYID[k];NAMES[s.dataset][s.contig.encode()]=s;NAMES[None][k.encode()]=s
    inv={r['path']:r for r in snap['files']};old.STAGE=stage;m=Path(mapping.__file__).parent;old.PROJECTOR=sha256_file(m/'q0_query_windows.py');old.VALIDATOR=sha256_file(m/'q0_alignments.py');old.MEMBERS={k:v[1:] for k,v in old.PARTS.items()};old.TOOL=old.prep.executable_identity('minimap2');need(old.TOOL['sha256']=='cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3','foreign native executable')
    dispatch=base/'q0-whole-dispatch-20261125.9Icl9fR7';native=old.get(dispatch/'native/native.json',old.NATIVE);old.SKIP={int(r) for r in native['parent_windows']}; old.FALLBACK=set(native['retired_fallback_parents'])
    old.WINDOWS={};actual=old.replay.plan_query_windows
    def capture(*a,**kw):
        windows=actual(*a,**kw)
        if len(windows)==61000:old.WINDOWS.update((v.window_id,v) for v in windows)
        return windows
    log=lambda *v:print(chrom,round(monotonic()-start,1),*v,flush=True)
    log('INPUTS_BOUND placements',len(placements),'sources',len(PARTSET));earlier=old.get(base/'q0-fork-partial-queries-20261123-1556/plan/replay.json',old.REPLAY)
    with patch.object(old.replay,'plan_query_windows',capture):old.replay.replay(base,stage/'historical')
    need(len(old.WINDOWS)==61000 and json.loads((stage/'historical/replay.json').read_bytes())['queries_uncompressed_sha256']==earlier['queries_uncompressed_sha256'],'wrong historical cores');jobs=[];orig=[]
    for r in snap['alignments']:
        rel=r['paf'];orig.append((rel,r['query_dataset'],r['target_dataset'],old.ROOT/rel,inv[rel]))
    native_order=[old.replay.FIRST];logpath=base/'q0-child-loader-cutover-20261122-180258/resume_43017096.out'
    for line in logpath.open():
        if 'weak seed: completed=' in line and '[run='+snap['source_run']+']' in line:
            tid=line.split('weak seed: completed=',1)[1].split()[0]
            if tid not in native_order:native_order.append(tid)
    need(set(native_order)==set(old.EXPECTED),'unbound native order')
    for tid in native_order:
        leaf='grt/evidence/q0_prepare/tasks/'+tid;rt=old.get(old.ROOT/leaf/'success.json',old.EXPECTED[tid]);rel=leaf+'/result.paf';o,=(r for r in rt['outputs'] if r['path']==rel);spec=rt['spec'];need(rt['status']=='success' and old.stable_id('q0-map',spec)==tid and o['sha256']==earlier['native_matrices'][tid]['paf_sha256'],'wrong native search')
        if not (PARTSET.isdisjoint(spec['query_ids']) or PARTSET.isdisjoint(spec['target_ids'])):orig.append((rel,None,None,old.ROOT/rel,o))
    for mode,db,plan in [('known',dispatch/'result',old.get(dispatch/'result/known.json',old.KNOWN)),('expanded',dispatch/'expand/result',old.get(dispatch/'expand/result/complete.json',old.EXPAND))]:
        ad=dispatch/('audit-'+mode)/'result';au=old.get(ad/'complete.json',old.AUDITS[mode]);need(au['shards'].keys()==plan['shards'].keys(),'incomplete audit');jobs.extend((db/k,h,ad/k,au['shards'][k]) for k,h in plan['shards'].items())
    frames=eligible=0;projected={};spools={}; log('SCAN_BEGIN',len(orig),'matrix PAFs',len(jobs),'regional shards')
    with ProcessPoolExecutor(max_workers=workers,mp_context=get_context('fork')) as pool:
        futures={pool.submit(filter_one,j):'paf' for j in orig}; futures.update({pool.submit(shard,j):'shard' for j in jobs})
        for ix,ft in enumerate(as_completed(futures),1):
            if futures[ft]=='paf':v=ft.result();spools[v[0]]=v
            else:
                size,n,out=ft.result();frames+=size;eligible+=n
                for q,tid,r,t,digest,mode in out:
                    need(q not in projected,'duplicate projection');projected[q]=(tid,digest)
            if ix%30==0:log('SCAN_PROGRESS',ix,'/',len(futures),'qualified projections',len(projected))
        need((frames,eligible)==(61000,59278),'incomplete frozen regional cohort');regional=[]
        for q in old.WINDOWS:
            if q not in projected:continue
            tid,d=projected[q];rel=f'grt/evidence/q0_prepare/regional/projects/{tid}/result.paf';src=stage/rel;regional.append((rel,None,None,src,dict(size=src.stat().st_size,sha256=d)))
        for v in pool.map(filter_one,regional,chunksize=8):spools[v[0]]=v
    log('GRAPH_INPUT_READY',len(regional),'projected PAFs; selected pair rows',sum(v[-1] for v in spools.values()))
    names={ds:{k.decode():(k.decode(),lens[s]) for k,s in v.items()} for ds,v in NAMES.items()};cache=retained_geometry_cache()
    def links():
        for rel,qd,td,*_ in [*orig,*regional]:
            path=spools[rel][3];prefix=('['+canonical_json(rel)+',').encode('ascii')
            with path.open('rb') as f:
                for line in f:
                    number,raw=line.split(b'\t',1);hit=_checked_line(raw.decode(),path,rel,int(number),prefix,names[qd],names[td],cache);yield PairLink(hit,NAMES[qd][hit.query_name.encode()],NAMES[td][hit.target_name.encode()])
    if screen:
        from screen_wheat_junction_flanks import screen_all
        doc=screen_all(cases,links(),[p.chromosome for p in paths]);doc.update(selection=summary['selection_chain'],questions=summary['questions'],regional_cohort=eligible,referenced_regional=len(regional),elapsed_s=round(monotonic()-start,2),published_q0=False)
        old.write(owner/'result.json',doc);log('ALL_SCREEN_DONE',doc['needs_graph']);return
    graph=PathGraph(placements,links(),(),progress=log,first_request=True);winner=search_request_path(graph,progress=log).path
    need(winner==expected,'reconstructed graph winner/cuts differ from sealed full-input winner');reviewer=review.Review();reviewer.observe(graph,winner);selection=SimpleNamespace(paths={p.chromosome:SimpleNamespace(path=p) for p in paths});windows=reviewer.windows(selection)
    log('EXACT_REVIEW',dict(reviewer.counts),'requests',len(windows)); root=owner/'local-evidence';root.mkdir(exist_ok=True);catalog=genome_subset(old.ROOT,snap,old.PARTS,{k for w in windows for k in (w.query,w.target)})
    for w in windows:
        q,t=w.windows(catalog.parts);members=sorted([q.segment_id,t.segment_id]);spec=mapping._normal(dict(schema=mapping.CONTEXT_SCHEMA,query=mapping._window_context(q),targets=[mapping._window_context(t)],members=[[k,old.PARTS[k][2]] for k in members],tool=old.TOOL,preset='asm10',fasta_format='wrap80_v1'))
        rel=Path('grt/evidence/q0_prepare/regional')/old.stable_id('q0-regional-context',spec);src=old.ROOT/rel;dst=root/rel
        if src.is_dir() and not dst.exists():
            need(not src.is_symlink() and not any(p.is_symlink() for p in src.rglob('*')),'linked context');dst.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(src,dst)
    refrow,=(r for r in snap['files'] if r['path'].startswith('data/reference/') and r['path'].endswith('.fai'));refbp=sum(int(line.split()[1]) for line in old.bounded(old.ROOT/refrow['path'],4<<20,refrow['sha256']).splitlines());tasks=review.dispatch(reviewer,selection,root,catalog,[],old.TOOL,'asm10',workers,refbp);fresh=list(old.threshold._supplement_links(root,catalog.parts,tasks,cache,1)); log('NEW_PAIR_ROWS',len(fresh)); kept_path=None
    if fresh:
        aug=PathGraph(placements,(*[v for vv in graph.links.values() for v in vv],*fresh),(),first_request=True,progress=log);kept_path=search_request_path(aug,progress=log).path
    doc=dict(schema='wheat_frozen_chr_review_v1',selection=summary['selection_chain'],questions=summary['questions'],chromosome=chrom,placements=len(placements),referenced_regional=len(regional),reconstructed_path=winner.path_id,counts=reviewer.counts,requests=len(windows),new_pair_rows=len(fresh),fixed_admission_path=(kept_path or winner).path_id,needs_global_readmission=bool(fresh),tasks=tasks,elapsed_s=round(monotonic()-start,2),published_q0=False)
    old.write(owner/'result.json',doc);log('GROUP_DONE',len(windows),len(fresh))

if __name__=='__main__':
    owner=Path.cwd();need(not (owner/'result.json').exists(),'already complete')
    with tempfile.TemporaryDirectory(dir='/tmp',prefix='wheat-real-group-') as scratch:run(owner.parent,owner,Path(scratch),sys.argv[1],int(sys.argv[2]))
