"""Isolated, restartable execution of the 15 regional batches. Never run native whole-source fallback."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from hashlib import sha256
import gzip,json,os,re,shutil,sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace

from census_wheat_q0_fork import bind,bounded,require
from check_wheat_inverse_targets import reference
from fork_wheat_q0 import member,copy_bound
from replay_wheat_partial_queries import residual,HIST,SCANS,FIRST,POLICY
from lgz_core import q0_regional_mapping as m, q0_preparation as prep
from lgz_core.q0_regional_discovery import plan_parent
from lgz_core.q0_regional_execution import choose_budget,execution_memory_limit
from lgz_core.q0_frontier_scope import window_touches_frontier
from lgz_core.q0_threshold_acceptance import decode
from lgz_core.q0_query_windows import plan_query_windows
from lgz_core.q0_sources import Interval,SourceKey,merged_intervals
from lgz_core.q0_alignments import read_paf_observations
from lgz_core.q0_catalog import ObservedSourcePairs
from lgz_core.common import stable_id,sha256_file

PLAN='aa84f79c0d5faa4d253850c5bf8635be308145f8efa47f4d3de934b34290a28e'
REPLAY='9b7e12988d8fabe2fd360910d517a3e112e99da4b03578fe1ed9fdcff4d2a682'
DEMAND='9c0a2e5569e4161e7ef59f7332b232f1d2d2ea4480c4a1c8445490c61ee62d97'
TOOL='cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3'

def atomic(path,value):
    tmp=path.with_suffix('.writing');tmp.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');tmp.replace(path)

def sig(path):
    st=path.stat();return st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns

class FaiDNA:
    """Support the production reader's bounded slices without allocating an entire multi-Gb assembly."""
    def __init__(self,fd,fields): self.fd=fd;self.n,self.offset,self.bases,self.width=fields
    def __getitem__(self,key):
        a,b=key.start,key.stop
        require(key.step is None and 0<=a<=b<=self.n,'out-of-source read')
        if a==b:return ''
        pos=lambda i:self.offset+i//self.bases*self.width+i%self.bases
        x,y=pos(a),pos(b-1)+1;raw=os.pread(self.fd,y-x,x);out=raw.replace(b'\n',b'').replace(b'\r',b'')
        require(len(raw)==y-x and len(out)==b-a,'source length or FAI wrapping mismatch');return out.decode('ascii')

def original_cores(base,root,lookup,order,lengths,parents,tmp):
    replay=json.loads(bounded(base/'q0-fork-partial-queries-20261123-1556/plan/replay.json',1<<20,REPLAY)); old=base/'q0-existing-cross-coverage-20261121-v2'
    require(replay['archived_residual_sha256']==HIST and replay['archived_scan_receipt_sha256']==SCANS and replay['replayed_query_count']==61000,'foreign old core inventory')
    source_ids={order[lookup[k][0]]:k for k in parents};holes={}
    for row in json.loads(bounded(old/'residual-coverage.json',16<<20,HIST)):
        src=SourceKey(row['dataset'],row['contig'])
        if src in source_ids:
            spans=tuple(Interval(*v) for v in row['uncovered']);key=source_ids[src]
            require(key not in holes and spans==merged_intervals(spans) and spans[-1].end<=row['length']==lengths[src],'unbound original residual');holes[key]=spans
    require(set(holes)==set(parents),'missing real cores');obs=ObservedSourcePairs(lengths)
    for matrix,pin in replay['native_matrices'].items():
        if matrix==FIRST:continue  # Already included in the sealed starting residual.
        rel='grt/evidence/q0_prepare/tasks/'+matrix+'/';rec=json.loads(bounded(member(root,rel+'success.json'),32<<20,pin['receipt_sha256']));spec=rec['spec']
        require(rec['status']=='success' and stable_id('q0-map',spec)==matrix and spec['alignment_flags']==pin['alignment_flags'],'wrong historical PAF')
        if not set(parents).intersection(spec['query_ids']+spec['target_ids']):continue
        row,=[v for v in rec['outputs'] if v['path']==rel+'result.paf'];require(row['sha256']==pin['paf_sha256'],'wrong raw bytes');path=tmp/(matrix+'.paf');copy_bound(member(root,row['path']),path,row)
        qlens={k:lookup[k][1] for k in spec['query_ids']};tlens={k:lookup[k][1] for k in spec['target_ids']}
        for hit in read_paf_observations(path,query_lengths=qlens,target_lengths=tlens,artifact=row['path']):
            if hit.query_name in parents or hit.target_name in parents:
                obs.observe_alignment(hit,order[lookup[hit.query_name][0]],order[lookup[hit.target_name][0]])
    left={k:residual(spans,obs.cross_coverage.get(order[lookup[k][0]],())) for k,spans in holes.items()}
    return plan_query_windows({k:lookup[k][1] for k in parents},left,policy=POLICY)

def context_key(q,targets,parts,tool):
    ids=sorted({q.segment_id,*(t.segment_id for t in targets)})
    return stable_id('q0-regional-context',dict(schema=m.CONTEXT_SCHEMA,query=m._window_context(q),targets=[m._window_context(t) for t in sorted(targets,key=lambda t:t.window_id)],members=[[k,parts[k].sequence_sha256] for k in ids],tool=tool,preset='asm10',fasta_format='wrap80_v1'))

def import_cache(root,dest,key):
    rel=f'grt/evidence/q0_prepare/regional/{key}'; src=member(root,rel); dst=member(dest,rel)
    if not src.is_dir() or dst.exists():return False
    # Only complete leaves and bound metadata, never copy generated FASTAs or a producer's partial writes.
    paths=[src/'context.json',*src.glob('q0-regional-decision-*.json')]
    for leaf in [src/'chaining',*src.glob('q0-regional-raw-*')]:
        if (leaf/'success.json').is_file(): paths.extend(leaf/n for n in ('command.json','guard.py','result.paf','success.json'))
    if not (src/'context.json').is_file():return False
    tmp=dst.with_name(key+'.importing');tmp.mkdir(parents=True,exist_ok=False)
    for path in paths:
        require(path.resolve()==path and path.is_file(),'unsafe cache member');state=sig(path);copy=tmp/path.relative_to(src);copy.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,copy)
        require(sig(path)==state,'source cache changed during import')
    tmp.rename(dst);return True  # Producer checks raw, decision, source/tool IDs and stored file hashes before use.

def run(base,owner):
    plan=json.loads(bounded(owner/'verified-plan.json',1<<20,PLAN));tool=prep.executable_identity('minimap2');require(tool['sha256']==TOOL,'wrong mapper')
    snap,root,lookup,order,lengths=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json');stage=owner/'workspace'
    require(owner.parent==base and owner.name.startswith('q0-local-only-maps-') and owner.resolve()==owner and not (owner/'result.json').exists(),'invalid or completed isolation');stage.mkdir(exist_ok=True)
    require(stage.resolve()==stage and shutil.disk_usage(stage).free>8<<30,'unsafe private workspace or inadequate free storage')
    known={'JM19flyeA_contig_4549','ptg000010l'};parents={k for k,(r,_,_) in lookup.items() if order[r].contig in known};require(len(parents)==2,'foreign parents'); parts={k:SimpleNamespace(segment_id=k,source=order[r],interval=Interval(0,n),sequence_sha256=h) for k,(r,n,h) in lookup.items()}
    demand=json.loads(gzip.decompress(bounded(base/'q0-whole-updated.We9jf3UC/result/updated-questions.json.gz',4<<20,DEMAND)));frontier=decode(demand['source_intervals'],lengths); by_query={row['query']:row for doc in plan['parents'] for row in doc['rows']}
    jobs=[];used=set();before={};tic=monotonic(); integrity={}
    with TemporaryDirectory(dir='/tmp',prefix='wheat-regional-real-') as td, ExitStack() as stack:
        tmp=Path(td); windows=original_cores(base,root,lookup,order,lengths,parents,tmp);require(len(windows)==13 and {q.window_id for q in windows}==set(by_query),'different historical query frames');indexed=defaultdict(list)
        for q in windows:indexed[q.segment_id].append(q)
        print('TRUE_CORES_READY',len(windows),sum(len(q.cores) for q in windows),flush=True)
        with reference(snap,root,lookup,order,lengths,tmp) as index:
            for k,qs in sorted(indexed.items()):
                rows,reason=plan_parent(SimpleNamespace(parts=parts),index,qs); require(reason is None and [q for q,_ in rows]==qs,'native fallback forbidden')
                for q,targets in rows:
                    require(window_touches_frontier(q,targets,parts,frontier),'window no longer required; do not map unnecessary work'); expected=by_query[q.window_id]; batches=list(m.target_batches(targets))
                    require(Counter(t.window_id for t in targets)==Counter(t.window_id for b in batches for t in b) and [sum(t.length for t in b) for b in batches]==expected['batches'] and len(targets)==expected['targets'],'lost target window or different partition')
                    for bi,batch in enumerate(batches):
                        key=context_key(q,batch,parts,tool); jobs.append((q,bi,batch,key));used.add(k);used.update(t.segment_id for t in batch)
            ref_bp=sum(index.reference_lengths.values())
        require(len(jobs)==15 and len({j[-1] for j in jobs})==15,'not the frozen 15 contexts');seqs={};pins={r['path']:r for r in snap['files']}
        for ds in sorted({p.source.dataset for p in parts.values()}):
            rel='data/datasets/'+ds+'.fa'; fasta=member(root,rel);require(fasta.stat().st_size==pins[rel]['size'],'foreign assembly');before[fasta]=sig(fasta);fd=stack.enter_context(fasta.open('rb')).fileno()
            fai=bounded(member(root,rel+'.fai'),8<<20,pins[rel+'.fai']['sha256']).decode().splitlines()
            for line in fai:
                name,n,off,bs,wd=line.split('\t')[:5];source=SourceKey(ds,name);fields=tuple(map(int,(n,off,bs,wd)));require(fields[0]==lengths[source] and 0<fields[2]<=fields[3] and fields[3]-fields[2]<=2,'invalid FAI');seqs[source]=FaiDNA(fd,fields)
        cat=SimpleNamespace(parts=parts,sequences=seqs); total_bp=sum(parts[k].interval.length for k in used)
        print('LOCAL_PLAN_BOUND',len(jobs),'parts',len(used),'source_bp_to_verify',total_bp,flush=True);tick=monotonic()
        for i,k in enumerate(sorted(used),1):
            m._source(cat,k)
            if i%500==0:print('SOURCE_VERIFIED',i,'/',len(used),flush=True)
        require(all(sig(p)==s for p,s in before.items()),'source file changed');source_s=monotonic()-tick
        imported=sum(import_cache(root,stage,key) for *_,key in jobs);limit=execution_memory_limit(32);require(limit and limit>=80<<30,'32-core allocation missing required verified memory'); budget=choose_budget(32,limit,0); workers=min(len(jobs),budget.mapper_workers); mt=budget.mapper_threads
        print('REGIONAL_DISPATCH',len(jobs),'workers',workers,'threads_each',mt,'cache_contexts_imported',imported,'source_verify_s',round(source_s,1),flush=True)
        def one(index,job):
            q,bi,batch,key=job; stamp=monotonic(); print('BATCH_START',index,q.window_id,bi,len(batch),flush=True);work=m.RegionalWorkLog('isolated')
            task=work.run(m.prepare_regional_mapping,stage,cat,q,batch,tool,reference_bases=ref_bp,preset='asm10',threads=mt)
            rec=m.verify_regional_task(stage,task,members=parts);paf=stage/task['paf'];size=paf.stat().st_size;sha=sha256_file(paf)
            with paf.open('rb') as f:count=sum(1 for line in f if line.strip())
            doc=dict(index=index,context=key,query=q.window_id,cores=q.cores,batch=bi,task=task,receipt_sha256=sha256_file(stage/task['receipt']),projected_sha256=sha,projected_bytes=size,projected_rows=count,seconds=round(monotonic()-stamp,3),work=work.counts)
            atomic(owner/f'batch-{index:02d}.json',doc); print('BATCH_DONE',index,'rows',count,'raw_started',work.counts['raw_started'],'seconds',doc['seconds'],flush=True);return doc
        with m.verified_mapper_loader(tool['resolved']), ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(one,i,j) for i,j in enumerate(jobs,1)]; results=sorted((f.result() for f in as_completed(futures)),key=lambda v:v['index'])
        require(all(sig(p)==s for p,s in before.items()) and sha256_file(Path(tool['resolved']))==TOOL,'mapper or sources changed'); totals=Counter()
        for v in results:totals.update(v['work'])
        doc=dict(schema='wheat_actual_regional_only_fallback_windows_v1',plan=PLAN,query_replay=REPLAY,updated_questions=DEMAND,kit=sha256_file(owner/'kit.sha256'),tool=TOOL,windows=len(windows),core_pieces=sum(len(q.cores) for q in windows),core_bp=sum(b-a for q in windows for a,b in q.cores),query_context_bp_sum=sum(q.length for q in windows),batches=len(results),source_parts_verified=len(used),verified_source_bp=total_bp,source_verify_s=round(source_s,3),workers=workers,threads_per_mapper=mt,verified_memory_limit=limit,work=totals,imported_contexts=imported,projected_rows=sum(x['projected_rows'] for x in results),projected_bytes=sum(x['projected_bytes'] for x in results),receipts=[sha256_file(owner/f"batch-{x['index']:02d}.json") for x in results],native_mapper_starts=0,wall_s=round(monotonic()-tic,3),scope='Actual regional mapping and verified projections only. Affected Q0 decisions require independent reranking; no whole-library mapping, production write, or final Q0.')
        atomic(owner/'result.json',doc); print('REGIONAL_15_DONE',len(results),doc['projected_rows'],dict(totals),flush=True)

if __name__=='__main__':run(Path(sys.argv[1]),Path.cwd())
