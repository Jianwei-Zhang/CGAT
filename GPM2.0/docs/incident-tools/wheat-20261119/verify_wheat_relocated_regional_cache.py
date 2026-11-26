"""Verify the sealed 15-batch cache in a fresh numbered workspace without creating alignments."""
from contextlib import ExitStack
from hashlib import sha256
import gzip,json,re,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from census_wheat_q0_fork import bind,bounded,require
from fork_wheat_q0 import member
from run_wheat_local_only_batches import FaiDNA,sig,TOOL
from lgz_core import q0_preparation as prep,q0_regional_mapping as regional
from lgz_core.common import sha256_file
from lgz_core.q0_query_windows import QueryWindow,TargetWindow
from lgz_core.q0_sources import SourceKey,Interval,Q0EvidenceError
from workspace_layout import initialize_workspace

MAP='ffc6e0f5cd45948e5d5ff5140c1b6a15e977e6b8bcdf5c7477c699ed34c16f8e'
LOOK='2e09b9ff5c849f4d4a83c177c46a4586c29d84b1407666dab8087615ad8c1c89'

def checked(p,pin,limit=8<<20):return json.loads(bounded(p,limit,pin))

def run(base,owner,dst,output):
    require(owner.parent==base and owner.name=='q0-local-only-maps-20261126.uWC4iQQn' and dst.parent.parent==Path('/tmp') and dst.resolve()==dst and not dst.exists(),'foreign or nonempty receiver')
    layout=initialize_workspace(dst);require(layout.version==2,'wrong receiving layout');src=owner/'workspace';report=checked(owner/'result.json',MAP);tasks=[];files={};fastas={};before={};total=0
    require(len(report['receipts'])==report['batches']==15 and report['native_mapper_starts']==0,'wrong mapping result')
    snap,root,lookup,order,lengths=bind(base/'q0-latest-fork-20261123-1435/control/snapshot.json',base/'q0-source-part-lookup-20261121-1600/source-part-lookup.json');pins={v['path']:v for v in snap['files']}
    parts={k:SimpleNamespace(source=order[r],segment_id=k,interval=Interval(0,n),sequence_sha256=h) for k,(r,n,h) in lookup.items()};tool=prep.executable_identity('minimap2');require(tool['sha256']==TOOL,'different mapper binary')
    ref,=[x for x in pins if x.startswith('data/reference/') and x.endswith('.fai')];ref_bp=sum(int(row.split('\t')[1]) for row in bounded(member(root,ref),1<<20,pins[ref]['sha256']).decode().splitlines())

    def transfer(name,fingerprint,size):
        nonlocal total
        require(re.fullmatch(r'grt/evidence/q0_prepare/regional/[\w./-]+',name) and '..' not in Path(name).parts and name.endswith(('.json','.py','.paf')),'foreign cache member')
        if name in files:
            require(files[name]==[fingerprint,size],'conflicting sealed files');return
        p=src/name;require(p==p.resolve(strict=True) and p.is_file() and p.stat().st_size==size and total+size<=64<<20,'foreign, oversized or non-regular source')
        before[p]=sig(p);f=layout.path(name);f.parent.mkdir(parents=True,exist_ok=True);h=sha256()
        with p.open('rb') as inp,f.open('xb') as out:
            for chunk in iter(lambda:inp.read(1<<20),b''):out.write(chunk);h.update(chunk)
        require(h.hexdigest()==fingerprint and sig(p)==before[p],'changed source');total+=size;files[name]=[fingerprint,size]

    for i,pin in enumerate(report['receipts'],1):
        batch=checked(owner/f'batch-{i:02d}.json',pin);t=batch['task'];key=t['task_id'];rel=t['receipt'];require(batch['index']==i and re.fullmatch(r'q0-regional-project-[0-9a-f]{24}',key) and rel==f'grt/evidence/q0_prepare/regional/projects/{key}/success.json','foreign project')
        record=checked(src/rel,batch['receipt_sha256']);spec=record['spec'];require(record['status']=='success','incomplete projection');transfer(rel,batch['receipt_sha256'],(src/rel).stat().st_size)
        require(t['paf']==rel.removesuffix('success.json')+'result.paf','wrong result path');transfer(t['paf'],batch['projected_sha256'],batch['projected_bytes'])
        if i==1:
            try:regional.verify_regional_task(dst,t,members=parts)
            except Q0EvidenceError:pass
            else:raise ValueError('a bare projection plus its receipt was accepted without dependencies')
        for row in record['outputs']:transfer(row['path'],row['sha256'],row['size'])
        ctx=checked(layout.path(spec['context']['path']),spec['context']['sha256']);require(ctx['input_fastas_reconstructible_from_bound_windows'] is True and ctx['spec']['tool']==tool,'foreign or non-reconstructible context')
        for row in ctx['inputs']:require(fastas.setdefault(row['path'],row['size'])==row['size'],'ambiguous FASTA identity')
        q=spec['query'];query=QueryWindow(q['segment_id'],q['segment_length'],q['start'],q['end'],tuple(tuple(v) for v in q['cores']));targets=[TargetWindow(v['segment_id'],v['segment_length'],v['start'],v['end']) for v in spec['targets']];require(query.window_id==batch['query'] and q['cores']==batch['cores'],'query core changed');tasks.append((query,targets,t))
    require(len({t['task_id'] for _,_,t in tasks})==15 and not any(layout.path(n).exists() for n in fastas),'unexpected scopes or staged DNA')
    used={w.segment_id for q,t,_ in tasks for w in (q,*t)}; require(len(used)==report['source_parts_verified'] and sum(parts[k].interval.length for k in used)==report['verified_source_bp'],'wrong source coverage')
    with ExitStack() as stack:
        seqs={}
        for ds in sorted({parts[k].source.dataset for k in used}):
            rel=f'data/datasets/{ds}.fa';f=member(root,rel);require(f.stat().st_size==pins[rel]['size'],'foreign assembly');before[f]=sig(f);fd=stack.enter_context(f.open('rb')).fileno();fai=bounded(member(root,rel+'.fai'),8<<20,pins[rel+'.fai']['sha256'])
            for row in fai.decode().splitlines():
                name,n,off,bs,wd=row.split('\t')[:5];key=SourceKey(ds,name);fields=tuple(map(int,(n,off,bs,wd)));require(fields[0]==lengths[key] and 0<fields[2]<=fields[3]<=fields[2]+2,'invalid bound FAI');seqs[key]=FaiDNA(fd,fields)
        cat=SimpleNamespace(parts=parts,sequences=seqs);work=regional.RegionalWorkLog('isolated_relocation');seq_bp=sum(parts[k].interval.length for k in used)
        # Keep all production content checks. Trap every expensive cold/rebuild path.
        for mod,name in ((regional,'_execute'),(regional,'_write_windows'),(regional,'_fresh_directory'),(prep,'_supplement')):
            stack.enter_context(patch.object(mod,name,side_effect=AssertionError('cold operation forbidden: '+name)))
        with work:
            for i,(q,t,task) in enumerate(tasks,1):
                got=work.run(regional.prepare_regional_mapping,dst,cat,q,t,tool,reference_bases=ref_bp,threads=1)
                require(got==task,'different projection on reuse');print('RELOCATED_BATCH_HIT',i,task['task_id'],flush=True)
        require(set(cat._regional_verified_parts)==used and all(sig(p)==v for p,v in before.items()),'source verification incomplete or input changed')
    require(work.counts['chain_reused']==work.counts['raw_reused']==work.counts['projection_reused']==15 and all(work.counts[k]==0 for k in ('chain_started','raw_started','projection_built','projection_only')),'not an exact warm replay')
    require(not any(layout.path(n).exists() for n in fastas) and sha256_file(owner/'result.json')==MAP and sha256_file(Path(tool['resolved']))==TOOL,'input identity drift or unexpected FASTA')
    closure=dict(schema='wheat_regional_cache_adoption_files_v1',mapping=MAP,lookup=LOOK,files=[dict(path=n,sha256=v[0],size=v[1]) for n,v in sorted(files.items())]);pack=output/'adoption-files.json.gz'
    with pack.open('xb') as f:f.write(gzip.compress((json.dumps(closure,sort_keys=True,separators=(',',':'))+'\n').encode(),mtime=0))
    res=dict(schema='wheat_relocated_regional_cache_v1',mapping=MAP,closure=sha256_file(pack),source_layout=1,receiver_layout=layout.version,tasks=len(tasks),query_windows=len({q.window_id for q,_,_ in tasks}),source_parts=len(used),source_bp_verified=seq_bp,transferred_files=len(files),transferred_bytes=total,generated_fasta_count=len(fastas),generated_fasta_bytes_not_transferred=sum(fastas.values()),bare_projection_rejected=True,native_mapper_starts=0,work=work.counts,rows=report['projected_rows'],scope='Exact replay of the 15 previous requests in a fresh numbered workspace with real source DNA verified. Does not establish that a future planner requests these batches, or that other caches are complete. No production workspace writes.')
    with (output/'result.json').open('x') as f:json.dump(res,f,indent=2,sort_keys=True);f.write('\n')

if __name__=='__main__':run(*(Path(a).resolve() for a in sys.argv[1:]))
