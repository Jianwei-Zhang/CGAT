"""Isolated whole-wheat updated demand, not formal Q0: consume completed evidence, never start a mapper."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
from time import monotonic
import fcntl,gzip,json,os,shutil,sys,tempfile
from unittest.mock import patch

from census_wheat_q0_fork import bind,bounded,pack_context,require
from bound_regional_scope_from_native_receipts import EXPECTED
from fork_wheat_q0 import copy_bound,draft_stage_plan,member
from wheat_selection_checkpoint import Store
import replay_wheat_partial_queries as replay
from lgz_core import q0_admission as adm,q0_preparation as prep,q0_regional_mapping as mapping,q0_threshold_prepare as threshold
from lgz_core.q0_catalog import CandidateCatalog
from lgz_core.q0_native_frontier import PHASES
try:
    from lgz_core.q0_native_frontier import FallbackGate  # Frozen pre-cache-only incident bundle.
except ImportError:
    from wheat_legacy_fallback_gate import FallbackGate
from lgz_core.q0_query_windows import QueryWindow,TargetWindow
from lgz_core.q0_sources import SourceKey,split_source
from lgz_core.q0_threshold_acceptance import decode,record
from lgz_core.common import sha256_file,stable_id

SN='2c8bd6a23eb339f71f16ab0a1e68f74562546532733ae98d3deae3d6609b1f3d'; REQ='f9229b186ff3587d6929cb8f6116e61f03086f9807b08c51af089d653032be77'
FINAL='f1bde6a1f3ec3082bdc20eb8b2f62246db672e2af035c13a791f3a53e425efca';KNOWN='f2a2c95745193581ec0144a90ba77c3fd82153c7856baba59bc65c324f673b54'; EXPAND='0f61eb72ffce8a33449fd8a3f9fb91d7f028a08b6ec21ba06d82b759aab31649'
AUDITS={'known':'7c33ccedc2c24c2cb18c54f5e6c5c25ca220bfdeb45d13f455e085ad3a2d56ff','expanded':'4a12d60b9ad40dead8ab5e750688f012a4625a78d138efbb18aed30b99629a8f'}
NATIVE='14bbc01fad3743cdfdfb3ff4c6009d92caeb928c4b9291e156bac9aa827961d9'; REPLAY='9b7e12988d8fabe2fd360910d517a3e112e99da4b03578fe1ed9fdcff4d2a682'


def get(p,pin):
    data=bounded(p,128<<20,pin);return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)


def write(p,doc):
    raw=json.dumps(doc,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n';raw=gzip.compress(raw,compresslevel=1,mtime=0) if p.suffix=='.gz' else raw
    digest=sha256(raw).hexdigest()
    if p.exists():require(sha256_file(p)==digest,'refuse to replace a different sealed artifact');return digest
    tmp=p.with_name(p.name+f'.{os.getpid()}.partial');tmp.write_bytes(raw);os.link(tmp,p);tmp.unlink();return digest


def stage_copy(src,dest,row,rate=None):
    if dest.exists():
        require(dest.resolve()==dest and dest.stat().st_size==row['size'] and sha256_file(dest)==row['sha256'],'damaged staged input');return
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        f=Path(tmp)/'copy';copy_bound(src,f,row,rate);os.link(f,dest)


def checked_leaf(identity):
    p=member(ROOT,identity['path']); raw=bounded(p,64<<20,identity['sha256']);require(len(raw)==identity['size'],'leaf size changed');return json.loads(raw)


def raw_lines(path,identity):
    # Historical exact raw outputs are uncompressed. Bind the entire physical stream while projecting every record once.
    before=prep.file_signature(path);h=sha256();size=0
    with path.open('rb') as src:
        for line in src:
            size+=len(line);h.update(line);yield line.decode('utf-8')
    require(size==identity['size'] and h.hexdigest()==identity['sha256'] and before==prep.file_signature(path),'unbound raw stream')


def project_one(qid,stamp,entry):
    q=WINDOWS[qid];ctx=entry['context_file']; cs=checked_leaf(ctx)['spec'];raw=entry['raw_paf'];rr=entry['raw_receipt'];d=entry['decision_file']
    require(d is not None and ctx['path']==f"grt/evidence/q0_prepare/regional/{entry['context']}/context.json" and cs['tool']==TOOL and mapping._window_context(q)==cs['query'] and sha256(pack_context(entry['context'],cs,PARTS)).hexdigest()==stamp,'foreign cached window or parameters')
    decision=checked_leaf(d);leaf=checked_leaf(rr);require(rr['path'].rsplit('/',1)[0]==raw['path'].rsplit('/',1)[0] and raw in leaf['outputs'] and leaf['status']=='success' and leaf['spec']['context']==ctx and leaf['spec']['flags']==entry['flags'] and d['path'].endswith('/'+stable_id('q0-regional-decision',decision)+'.json'),'wrong raw leaf or decision')
    targets=[TargetWindow(v['segment_id'],v['segment_length'],v['start'],v['end']) for v in cs['targets']];require([t.window_id for t in targets]==sorted(t.window_id for t in targets),'target order differs')
    spec=mapping._normal(dict(schema=mapping.PROJECTION_SCHEMA,raw_receipt=rr,context=ctx,decision=d,query=q.record(),targets=[t.record() for t in targets],projector_sha256=PROJECTOR,validator_sha256=VALIDATOR));tid=stable_id('q0-regional-project',spec);rel='grt/evidence/q0_prepare/regional/projects/'+tid
    tids=sorted({t.segment_id for t in targets});task=dict(kind='regional_discovery',task_id=tid,query_ids=[q.segment_id],target_ids=tids,paf=rel+'/result.paf',receipt=rel+'/success.json');dest=STAGE/task['paf'];dest.parent.mkdir(parents=True,exist_ok=True)
    if (ROOT/task['receipt']).is_file():
        rc=mapping.verify_regional_task(ROOT,task,members=MEMBERS);require(rc['spec']==spec,'cached projection differs');ident,=[o for o in rc['outputs'] if o['path']==task['paf']];stage_copy(member(ROOT,ident['path']),dest,ident);digest=ident['sha256'];mode='projected_hit'
    else:
        # The prior sealed audit checked raw/chain command, spec and CIGAR. Rebind the actual files; no approximate PAF is fed to selection.
        for item in leaf['outputs']:
            if item!=raw:require(prep.identity(ROOT,item['path'])==item,'changed raw command/guard')
        cr=entry['chaining_receipt'];require(decision.get('chaining_receipt')==cr,'foreign chaining decision')
        if cr:
            chain=checked_leaf(cr);require(chain['status']=='success' and chain['spec']['context']==ctx and all(prep.identity(ROOT,o['path'])==o for o in chain['outputs']),'changed original chaining evidence')
        h=sha256(); source=raw_lines(member(ROOT,raw['path']),raw)
        with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False,prefix='.projection-') as dst:
            for line in mapping._projected_lines(source,q,targets,artifact=raw['path']):buf=line.encode();dst.write(buf);h.update(buf)
        digest=h.hexdigest();tmp=Path(dst.name)
        if dest.exists():require(sha256_file(dest)==digest,'local projection differs');tmp.unlink()
        else:tmp.rename(dest)
        mode='projection_only'
    return [qid,tid,PARTS[q.segment_id][0],[PARTS[p][0] for p in tids],digest,mode]


def stage_shard(job):
    a,ap,b,bp,name=job;results=[];rows=get(a,ap);audits=get(b,bp);require([r[0] for r in rows]==[q for q,p in audits],'different geometry/audit')
    dest=STAGE/'receipts'/(name+'.gz');seal=dest.with_suffix('.seal');binding=[CODE,ap,bp]
    if seal.is_file():
        saved=json.loads(bounded(seal,1<<20));require(saved['input']==binding,'foreign staged shard');arch=get(dest,saved['sha256']);eligible=[r[0] for r,(_,a) in zip(rows,audits) if a['status']=='verified'];require([r[0] for r in arch]==eligible,'incomplete staged shard')
        for q,tid,rank,targets,h,mode in arch:
            p=STAGE/f'grt/evidence/q0_prepare/regional/projects/{tid}/result.paf';require(p.resolve()==p and sha256_file(p)==h,'damaged staged PAF')
        return name,saved['sha256'],len(rows),len(arch)
    for row,(_,entry) in zip(rows,audits):
        q,r,lo,hi,ctx,stamp,left,right,reason=row
        eligible=r not in SKIP and r not in FALLBACK and bool(left or right)
        require(eligible==(entry['status']=='verified'),'different actual regional eligibility')
        if eligible:
            require(reason is None and entry['context']==ctx and (WINDOWS[q].start,WINDOWS[q].end)==(lo,hi),'foreign retained window')
            results.append(project_one(q,stamp,entry))
    digest=write(dest,results);write(seal,dict(input=binding,sha256=digest));return name,digest,len(rows),len(results)


LOCAL_WINDOW_RESULT='ffc6e0f5cd45948e5d5ff5140c1b6a15e977e6b8bcdf5c7477c699ed34c16f8e'
BASE_EVIDENCE='4f9609e581cdece932e18ad0e69ce57ea5557f732f1e8ab48242ea85127d4e23'


def ordered_extra(window_order, original, extra):
    """Insert at original query/window ordinals, never append a later completed batch to the end."""
    require(set(original).isdisjoint(extra) and set(original)|set(extra)<=set(window_order),'foreign or already included windows')
    return [item for q in window_order for item in ([original[q]] if q in original else extra.get(q,()))]


def stage_local_additions(path, stage, windows, originals):
    report=get(path/'result.json',LOCAL_WINDOW_RESULT);require(report['batches']==15 and report['windows']==13 and report['native_mapper_starts']==0 and report['projected_rows']==1660,'wrong local dataset')
    extra={};seen=set();ranks=set();n=0
    for i,digest in enumerate(report['receipts'],1):
        row=get(path/f'batch-{i:02d}.json',digest);q=windows[row['query']];t=row['task'];rank=PARTS[q.segment_id][0];require(row['index']==i and t['task_id'] not in seen and t['query_ids']==[q.segment_id] and q.cores==tuple(tuple(v) for v in row['cores']) and rank in FALLBACK,'foreign or duplicate local batch')
        require(row['batch']==len(extra.get(q.window_id,[])),'changed local batch order');seen.add(t['task_id']);ranks.add(rank)
        source=path/'workspace';rc=mapping.verify_regional_task(source,t,members=MEMBERS);require(sha256_file(source/t['receipt'])==row['receipt_sha256'],'local receipt changed');ident,=[v for v in rc['outputs'] if v['path']==t['paf']];require((ident['sha256'],ident['size'])==(row['projected_sha256'],row['projected_bytes']),'wrong projected PAF');stage_copy(member(source,t['paf']),member(stage,t['paf']),ident)
        extra.setdefault(q.window_id,[]).append((t,[t['task_id'],ident['sha256']]));n+=row['projected_rows']
    require(len(extra)==13 and len(seen)==15 and ranks==FALLBACK and n==report['projected_rows'],'incomplete local input')
    return ordered_extra(windows,originals,extra)


def run(base,stage,owner,threads,local_owner=None):
    global ROOT,STAGE,PARTS,WINDOWS,SKIP,FALLBACK,TOOL,MEMBERS,PROJECTOR,VALIDATOR,CODE
    began=monotonic();STAGE=stage;CODE=sha256_file(owner/'kit.sha256')
    require(stage.parent==Path('/tmp') and stage.name==owner.name+'-'+CODE[:12] and owner.resolve()==owner and owner.parent==base and owner.name.startswith('q0-whole-local-maps.' if local_owner else 'q0-whole-updated.') and not(owner/'result/summary.json').exists(),'unsafe or complete run')
    stage.mkdir(mode=0o700,exist_ok=True);require(stage.resolve()==stage and stage.stat().st_uid==os.getuid() and not(stage.stat().st_mode&0o077),'unsafe node-local cache');write(stage/'owner.json',dict(owner=str(owner),kit=CODE));(stage/'receipts').mkdir(exist_ok=True);root=base/'q0-whole-dispatch-20261125.9Icl9fR7';full=get(root/'report-v2/result/final.json',FINAL);native=get(root/'native/native.json',NATIVE)
    snap,ROOT,PARTS,order,lens=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json'); ids=sorted(PARTS);require(all(PARTS[p][0]==i for i,p in enumerate(ids)),'part ranks differ');SKIP={int(k) for k in native['parent_windows']};FALLBACK=set(native['retired_fallback_parents']);MEMBERS={p:(n,h) for p,(_,n,h) in PARTS.items()};TOOL=prep.executable_identity('minimap2');require(TOOL['sha256']=='cb7e8f228d516fe4632a2250d09d1635ddd7aa95588c9fd5442d1dbe6e9a20a3','foreign mapper identity');m=Path(mapping.__file__).parent;PROJECTOR=sha256_file(m/'q0_query_windows.py');VALIDATOR=sha256_file(m/'q0_alignments.py')
    before=decode(get(base/'q0-request-ready.44e274a7/control/global-first-request.json',REQ)['request'],lens);require(len(before)==3111 and sum(map(len,before.values()))==5599 and full['request_sha256']==REQ,'wrong initial demand')
    stage_rows,deferred_ref=draft_stage_plan(ROOT,snap);nbytes=sum(r['size'] for r in stage_rows);missing=sum(row['size'] for row in stage_rows if not (stage/row['path']).is_file());require(shutil.disk_usage(stage).free>missing+(48<<30) and os.statvfs(stage).f_favail>150000,'not enough local bytes/inodes')
    WINDOWS={};actual=replay.plan_query_windows
    def capture(*a,**kw):
        windows=actual(*a,**kw)
        if len(windows)==61000:WINDOWS.update((v.window_id,v) for v in windows)
        return windows
    earlier=get(base/'q0-fork-partial-queries-20261123-1556/plan/replay.json',REPLAY)
    with tempfile.TemporaryDirectory(dir=stage) as tmp:
        dst=Path(tmp)/'historical-cores'
        with patch.object(replay,'plan_query_windows',capture):replay.replay(base,dst)
        require(json.loads((dst/'replay.json').read_bytes())['queries_uncompressed_sha256']==earlier['queries_uncompressed_sha256'] and len(WINDOWS)==61000,'wrong original core plan')
    print('WHOLE_CORE_PLAN_READY',len(WINDOWS),flush=True)
    frozen=get(root/'result/known.json',KNOWN);rest=get(root/'expand/result/complete.json',EXPAND);jobs=[]
    for mode,db,plan in [('known',root/'result',frozen),('expanded',root/'expand/result',rest)]:
        audit_dir=root/('audit-'+mode)/'result';audit=get(audit_dir/'complete.json',AUDITS[mode]);require(audit['shards'].keys()==plan['shards'].keys(),'lost audit coverage')
        jobs += [(db/k,h,audit_dir/k,audit['shards'][k],mode+'-'+k) for k,h in plan['shards'].items()]
    proofs={};done=kept=0
    # Spawn only before loading any source DNA or selection heap. Never run an alignment subprocess.
    with ProcessPoolExecutor(max_workers=min(20,threads-1),mp_context=get_context('fork')) as pool:
        for future in as_completed([pool.submit(stage_shard,j) for j in jobs]):
            name,h,n,k=future.result();proofs[name]=h;done+=n;kept+=k
            if len(proofs)%30==0:print('CACHED_FRAMES_STAGED',done,'/61000',kept,'exact',flush=True)
    require(done==61000 and kept==full['window_counts']['reuse_exact_raw']==59278,'incomplete cached evidence');locations={};methods=Counter()
    for key,pin in sorted(proofs.items()):
        for q,tid,r,targets,h,mode in get(stage/'receipts'/(key+'.gz'),pin):
            require(q not in locations,'duplicate projected task');locations[q]=(tid,r,targets,h);methods[mode]+=1
    print('REGIONAL_INPUT_READY',methods,flush=True);tasks=[];paf_identities=[]
    # Bind the native seed consumption order to the actual retired producer run, not a directory sort.
    native_order=[replay.FIRST];producer_log=base/'q0-child-loader-cutover-20261122-180258/resume_43017096.out'
    with producer_log.open() as log:
        for line in log:
            token='weak seed: completed='
            if token in line and '[run='+snap['source_run']+']' in line:
                tid=line.split(token,1)[1].split()[0]; require(tid in EXPECTED,'foreign seed');
                if tid not in native_order:native_order.append(tid)
    require(set(native_order)==EXPECTED.keys(),'incomplete native order')
    for tid in native_order:
        leaf='grt/evidence/q0_prepare/tasks/'+tid;receipt=get(ROOT/leaf/'success.json',EXPECTED[tid]);spec=receipt['spec'];paf=leaf+'/result.paf';o,=[o for o in receipt['outputs'] if o['path']==paf];require(receipt['status']=='success' and stable_id('q0-map',spec)==tid and spec['tool']==TOOL and spec['members']==[[p,PARTS[p][2]] for p in sorted(set(spec['query_ids']+spec['target_ids']))] and earlier['native_matrices'][tid]['paf_sha256']==o['sha256'],'foreign native matrix');stage_copy(member(ROOT,paf),stage/paf,o)
        tasks.append(dict(task_id=tid,paf=paf,query_ids=spec['query_ids'],target_ids=spec['target_ids']));paf_identities.append([tid,o['sha256']])
    originals={}
    for q in WINDOWS:
        if q not in locations:continue
        tid,r,targets,h=locations.pop(q);paf='grt/evidence/q0_prepare/regional/projects/'+tid+'/result.paf';originals[q]=(dict(task_id=tid,paf=paf,query_ids=[ids[r]],target_ids=[ids[n] for n in targets]),[tid,h])
    require(not locations and len(originals)==59278 and len(tasks)==4,'incomplete ordered cache set')
    digest=lambda rows:sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
    if local_owner:
        require(local_owner.parent==base and local_owner.resolve()==local_owner and local_owner.name.startswith('q0-local-only-maps-') and digest(paf_identities+[v[1] for v in originals.values()])==BASE_EVIDENCE,'baseline ordered evidence changed')
        ordered=stage_local_additions(local_owner,stage,WINDOWS,originals);require(len(ordered)==59293,'incomplete extended batch list')
    else:ordered=originals.values()
    for task,identity in ordered:tasks.append(task);paf_identities.append(identity)
    generation=digest(paf_identities);del WINDOWS,locations,paf_identities,ordered,originals
    done=last=0
    for row in stage_rows:
        stage_copy(member(ROOT,row['path']),member(stage,row['path']),row,96<<20);done+=row['size']
        if done-last>=4<<30:print('BASE_INPUT_STAGED',done,'/',nbytes,flush=True);last=done
    ds=prep.table(stage,'metadata/datasets.tsv',('dataset_name','fasta_relpath'));seqs=prep._dataset_sequences(stage,ds);parts={};edges=[]
    for s,seq in seqs.items():
        info=split_source(s,seq);require(not info.adjacencies and len(info.segments)==1,'foreign wheat split');p,=info.segments;require(p.segment_id in MEMBERS and MEMBERS[p.segment_id]==(p.interval.length,p.sequence_sha256),'source identity changed');parts[p.segment_id]=p
    require(parts.keys()==PARTS.keys() and {k:len(v) for k,v in seqs.items()}==lens,'source cohort changed');catalog=CandidateCatalog({'original_connections':edges},seqs,parts);ref,=prep.table(stage,'metadata/reference.tsv',('fai_relpath',));refs={row[0]:int(row[1]) for row in (v.split('\t') for v in (stage/ref['fai_relpath']).read_text().splitlines())};assign=prep.table(stage,'metadata/chr_assignments.tsv',('dataset_name','seq_name','assigned_chr_name'));require(all(x['assigned_chr_name'] in refs and lens[SourceKey(x['dataset_name'],x['seq_name'])]==int(x['seq_length_bp']) for x in assign),'assignment drift')
    sel=owner/'selection';sel.mkdir(mode=0o700,exist_ok=True);require(sel.resolve()==sel and not(sel.stat().st_mode&0o077) and sel.stat().st_uid==os.getuid(),'unsafe private checkpoint directory'); result=owner/'result';result.mkdir(mode=0o700,exist_ok=True);require(result.resolve()==result,'linked result');proof=sha256_file(owner/'kit.sha256'); binding=['whole-wheat-local-supplement-v1' if local_owner else 'whole-wheat-updated-supplement-v1',SN,REQ,FINAL,proof,generation,threads];saved={};selector=adm.select_request_paths
    def capture_demand(need,have,counts,issues):
        detail=dict(schema='wheat_cached_full_updated_demand_v1',decision_only=True,source_snapshot=SN,first_request=REQ,evidence_inventory=generation,has_path=have,counts=counts,issues=issues,source_intervals=record(need)); saved['questions']=write(result/'updated-questions.json.gz',detail);saved['after']=None if need is None else dict(sources=len(need),intervals=sum(map(len,need.values())),bases=sum(iv.length for v in need.values() for iv in v));saved['counts']=counts
    with (sel/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);store=Store(sel,binding,False)
        def select(data,**kw):
            saved['pair_rows']=len(data.pair_links);require(saved['pair_rows']>=42698133 and 'checkpoint' not in kw,'invalid retained input or old checkpoint');return selector(data,checkpoint=store,**kw)
        def refresh(items):
            require(len(items)==(59297 if local_owner else 59282),'updated selector missing inputs');return threshold.initial_questions(stage,seqs,refs,assign,snap['alignments'],threads=threads,existing_catalog=catalog,supplementary=items,on_updated_questions=capture_demand)
        request=dict(kind='partial_source_discovery',query_ids=sorted(ids[r] for r in FALLBACK),target_ids=ids);gate=FallbackGate(parts,before,refresh);actions=[]
        def observe(req,only):require(req is request,'matrix changed');actions.append('cache_probe' if only else 'would_run_original');return None if only else {'diagnostic_only':True}
        print('WHOLE_UPDATED_SELECTOR_START',len(seqs),len(tasks),generation,flush=True)
        reader=threshold.read_retained_paf;progress=[0,0,monotonic()]
        def counted(path,**kw):
            n=0
            for v in reader(path,**kw):n+=1;yield v
            progress[0]+=1;progress[1]+=n
            if monotonic()-progress[2]>=60:print('DRAFT_PAF_READ',progress[0],progress[1],kw['artifact'],flush=True);progress[2]=monotonic()
        with patch.object(threshold,'read_retained_paf',counted), patch.object(adm,'select_request_paths',side_effect=select):
            if local_owner:
                refresh(tasks);actions.append('reuse_verified_evidence_rerank_only')  # no native dispatcher
            else:gate.dispatch(PHASES[0],[request],tasks,observe)
        require(saved.get('questions') and not(stage/prep.MANIFEST).exists(),'not a completed isolated draft');saved['selection_chain']=store.previous
    summary=dict(schema='wheat_whole_first_cached_native_decision_v1',**saved,inputs=SN,first_request=REQ,regional_inventory=FINAL,kit_sha256=proof,evidence_digest=generation,regional=len(tasks)-4,native=4,base_pair_rows=42698133,methods=methods,actions=actions,mapper_starts=0,published_q0=False,elapsed_s=round(monotonic()-began,2),scope='All frozen initial inputs, four adopted native matrices, 59,278 existing exact partial-regional results, before candidate discovery or a new native fallback. Planning selection only; no formal Q0.')
    if local_owner:
        summary.update(schema='wheat_whole_local_supplement_readmission_v1',baseline_evidence=BASE_EVIDENCE,local_mapping=LOCAL_WINDOW_RESULT,scope='All 22 groups, fresh admission and draft path selection from the 4 prior native matrices and 59,293 verified regional inputs. Not a formal Q0 or result publication.')
    print('WHOLE_UPDATED_DEMAND',saved['after'],actions,write(result/'summary.json',summary),flush=True)


if __name__=='__main__':
    run(*(Path(x) for x in sys.argv[1:4]),int(sys.argv[4]),*(Path(x) for x in sys.argv[5:]))
