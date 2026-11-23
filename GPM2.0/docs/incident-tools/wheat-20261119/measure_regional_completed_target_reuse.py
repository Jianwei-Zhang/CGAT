"""Bounded read-only target pruning measurement; exact and scoped approximate matrices."""
import collections,csv,hashlib,json,os,resource,shutil,socket,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
BASE=Path('/share/home/xbzhang26/cgat-reads-debug/jm19-compare-614589f-20261118')
WORK=BASE/'gpm_server'
PACKAGE=BASE/'q0-native-dispatch-control-20261122-110235/package/server/tools'
sys.path.insert(0,str(PACKAGE))
from lgz_core.common import stable_id
from lgz_core.q0_sources import SourceKey,SourceSegment,Interval
from lgz_core.q0_query_windows import WindowPolicy,plan_query_windows
from lgz_core.q0_reference_index import ReferenceIndex
from lgz_core.q0_regional_candidates import CompletedNativeScopes
from lgz_core.q0_regional_mapping import BASE_FLAGS
from lgz_core.q0_catalog import DISCOVERY_REFERENCE_IDENTITY
from lgz_core.q0_cigar_policy import WEAK_GLOBAL_SEED_POLICY
FAST='q0-map-2b19c2c859bdfb5f2e9177e8'
EXPECT={
 'q0-map-2b19c2c859bdfb5f2e9177e8':'ba5553ff1640cd1feff0db518b671baabed44fba84e02c7992e30a1cb76dd50a',
 'q0-map-8024dde83cbf20e7ffa6d8ee':'994bfaa20bd68d035bedb7d8abacf616d826ebbb0bdc9c2cdc0b1e13b561245e',
 'q0-map-a2e519761e94eff6ca09e121':'c36e5d98b8cbeac165865060565ed8c8953824f42baafa9c7db2e94b1ec7679f',
 'q0-map-b30137a13323db8a99874448':'26e6cb45d97322add5409035f06cdbeed6a2f367ea5ceb6ee5aed3b0e57442f3'}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def bound_json(path,sha):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('changed bound input: '+str(path))
    return json.loads(raw)
lookup=bound_json(BASE/'q0-source-part-lookup-20261121-1600/source-part-lookup.json','2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89')
residual=bound_json(BASE/'q0-existing-cross-coverage-20261121-v2/residual-coverage.json','03b79fc96cc80ccfa8a6560be2141efd4126afd73d21ad1021c944508a04d171')
parts={};byname={}
for pid,r in lookup.items():
    if stable_id('q0-source-part',[r['dataset'],r['contig'],0,r['length'],r['sequence_sha256']])!=pid:raise ValueError('split/changed source')
    key=SourceKey(r['dataset'],r['contig']);byname[key]=pid
    parts[pid]=SourceSegment(pid,key,Interval(0,r['length']),r['sequence_sha256'],0,'record_start','record_end')
holes={byname[SourceKey(r['dataset'],r['contig'])]:tuple(Interval(*i) for i in r['uncovered']) for r in residual if r['uncovered']}
windows=plan_query_windows({k:p.interval.length for k,p in parts.items()},holes,policy=WindowPolicy(core_bases=100000,context_bases=10000,trigger_query_bases=1,trigger_longest_bases=1)) or ()
groups=collections.defaultdict(list)
for w in windows:groups[w.segment_id].append(w)
refs_table=list(csv.DictReader((WORK/'metadata/reference.tsv').read_text().splitlines(),delimiter='\t'))
refs={f[0]:int(f[1]) for f in (line.split('\t') for line in (WORK/refs_table[0]['fai_relpath']).read_text().splitlines())}
complete=[]
for tid,sha in EXPECT.items():
    rel='grt/evidence/q0_prepare/tasks/'+tid
    rec=bound_json(WORK/rel/'success.json',sha);s=rec['spec']
    if s['alignment_flags']!=BASE_FLAGS and not (tid==FAST and s['alignment_flags']==[*BASE_FLAGS,'-m',str(WEAK_GLOBAL_SEED_POLICY['minimum_chain_score'])]):raise ValueError('unsupported native profile')
    complete.append({'task_id':tid,'kind':('candidate_unroutable_seed' if tid==FAST else 'unplaced_discovery'),'query_ids':s['query_ids'],'target_ids':s['target_ids'],'paf':rel+'/result.paf','receipt':rel+'/success.json'})
if len({json.dumps(bound_json(WORK/t['receipt'],EXPECT[t['task_id']])['spec']['tool'],sort_keys=True) for t in complete})!=1:raise ValueError('tool cohort differs')
tool=bound_json(WORK/complete[0]['receipt'],EXPECT[complete[0]['task_id']])['spec']['tool']
selected=[]
for ds in sorted({p.source.dataset for p in parts.values()}):
    ids=sorted((k for k in groups if parts[k].source.dataset==ds),key=lambda k:(parts[k].interval.length,k))
    selected += [ids[int((len(ids)-1)*i/15)] for i in range(16)]
query_union={k for t in complete if t['task_id']!=FAST for k in t['query_ids']}
extra=sorted(query_union & groups.keys(),key=lambda k:(parts[k].interval.length,k))
if extra:selected += [extra[int((len(extra)-1)*i/7)] for i in range(8)]
selected=list(dict.fromkeys(selected));selected_windows=[]
for k in selected:
    g=groups[k]
    for j in sorted({0,len(g)//2}):selected_windows.append(g[j])
print(json.dumps({'phase':'selection','parents':len(selected),'windows':len(selected_windows),'all_frozen_windows':len(windows)}),flush=True)
started=time.monotonic();rows=[]
resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
with tempfile.TemporaryDirectory(prefix='q0-pair-reuse-',dir='/tmp') as tmp:
    db=Path(tmp)/'reference.sqlite';shutil.copyfile(BASE/'q0-exact-reference-index-20261121/reference.sqlite',db)
    if digest(db)!='18677df675e1a3c5fe9071d3edcd908215c8a20d2fbba4d5effd39411c0909a3':raise ValueError('sealed index changed')
    pafs=Path(tmp)/'pafs';pafs.mkdir()
    index=ReferenceIndex.open(db,WORK,parts,refs,local_paf_directory=pafs)
    try:
        fast=next(t for t in complete if t['task_id']==FAST)
        qualified=set()
        for key in fast['query_ids']:
            part=parts[key]
            for hit in index._source_hits(part.source,part.interval):
                if hit.matches/hit.block_length>=DISCOVERY_REFERENCE_IDENTITY and any(b.operation!='X' and b.query.intersection(part.interval) is not None for b in hit.aligned_blocks()):
                    qualified.add(key)
        if qualified:raise ValueError('fast seed contains a qualified reference source: '+str(sorted(qualified)))
        # Only the fast seed query membership is used by weak_global_seed_scope.
        # Its absence from qualified routing is proven above using the actual sealed input records.
        scope=CompletedNativeScopes(WORK,SimpleNamespace(parts=parts,reference_routable_parts=frozenset()),index,complete,tool,'asm10')
        fullmask=(1<<len(index.part_order))-1
        for number,w in enumerate(selected_windows):
            regions=index.regions(w.segment_id,Interval(w.start,w.end),anchor_context=1000000,reference_context=10000)
            mask=scope.remaining_targets(w.segment_id,fullmask,include_approximate=True)
            eligible=set(scope.keys(mask));selection=index.target_selection(mask)
            # Alternate order to reduce warm bias. This is lookup timing, not end-to-end runtime.
            plans={};times={};decodes={};orig=index._hit
            for name in (('legacy','filtered') if number%2==0 else ('filtered','legacy')):
                count=[0]
                def counted_hit(row):count[0]+=1;return orig(row)
                index._hit=counted_hit;start=time.monotonic()
                try:
                    kw={} if name=='legacy' else {'selection':selection}
                    plans[name]=index.targets(regions,context=10000,exclude=[w.segment_id],**kw)
                    times[name]=time.monotonic()-start;decodes[name]=count[0]
                finally:index._hit=orig
            expected={k:v for k,v in plans['legacy'].items() if k in eligible}
            if plans['filtered']!=expected:raise ValueError('filtered target geometry differs from exact legacy subset')
            counts={n:sum(len(v) for v in plans[n].values()) for n in plans}
            bases={n:sum(i.length for v in plans[n].values() for i in v) for n in plans}
            r={'query_part':w.segment_id,'dataset':lookup[w.segment_id]['dataset'],'query_start':w.start,'query_end':w.end,'core_bases':sum(b-a for a,b in w.cores),
              'legacy_targets':len(plans['legacy']),'filtered_targets':len(plans['filtered']),'target_windows':counts,'target_bases':bases,
              'lookup_seconds':times,'paf_decodes':decodes,'filter_equals_exact_legacy_subset':True,
              'query_in_native_query_union':w.segment_id in query_union,'empty_before':not plans['legacy'],'empty_after':not plans['filtered']}
            rows.append(r);print(json.dumps({'phase':'window','number':number+1,**r}),flush=True)
        index.verify_inputs()
    finally:index.close()
report={'status':'all_scoped_completed_target_subsets_verified','hostname':socket.gethostname(),'metadata_only_not_native_output_revalidation':True,
 'native_receipt_sha256':EXPECT,'approximate_seed_matrix_omitted':False,'fast_seed_queries_verified_unroutable':len(fast['query_ids']),'fast_seed_effective_query_parts':len(scope.keys(scope.scopes[0][0])),'DNA_read':False,'reference_PAF_read':True,'native_mapper_executed':False,'main_workspace_modified':False,
 'sample_parents':len(selected),'sample_windows':len(rows),'frozen_planned_windows':len(windows),
 'aggregate':{field:{mode:sum(r[field][mode] for r in rows) for mode in ('legacy','filtered')} for field in ('target_windows','target_bases','lookup_seconds','paf_decodes')},
 'windows_with_target_pruning':sum(r['legacy_targets']!=r['filtered_targets'] for r in rows),
 'newly_empty_windows':sum(not r['empty_before'] and r['empty_after'] for r in rows),'rows':rows,
 'limitations':['Stratified sample, deliberately includes native-query parents; not weighted to live queue.','Frozen holes predate current weak-seed evidence; whole-parent fallback decisions not predicted.','No native mapping executed, no claim of final PAF equivalence or speedup.','Includes the fourth approximate seed only within production weak_global_seed_scope; query routing verified from actual sealed reference records.','Removing tested targets changes mapper context; existing complete cache must retain priority.'],
 'seconds':time.monotonic()-started}
Path('summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
