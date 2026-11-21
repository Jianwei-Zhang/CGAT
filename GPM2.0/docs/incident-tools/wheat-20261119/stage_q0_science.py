"""Transactional q0-only installation under the normal acquired workspace lock.

The old declaration is explicitly migrated, never silently accepted as the new
builder. Initial alignment files/checkpoints and old source plans are untouched.
A failure restores every changed path; the complete backup remains for audit.
"""
import json
import hashlib
import os
import re
from pathlib import Path
import tempfile
from q0_science_context import checked, digest


def atomic_bytes(path,data,mode):
    fd,name=tempfile.mkstemp(prefix='.q0-transition-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,mode);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)


def owned(ctx,lock):
    if (not lock.acquired or lock.server_dir.resolve()!=ctx.work
            or lock._existing_owner().get('run_id')!=lock.run_id):
        raise ValueError('q0 transition requires current normal workspace ownership')


def targets(ctx):
    rows=[{'relative':row['relative'],'prior_sha256':row['prior_sha256'],
           'source':row['source']} for row in ctx.transition['runtime']]
    rows.append({'relative':ctx.helper.LAUNCHER,'prior_sha256':ctx.transition['prior_launcher_sha256'],
                 'source':ctx.transition['launcher']})
    rows.append({'relative':ctx.helper.RECEIPT,'prior_sha256':ctx.transition['prior_declaration_sha256'],
                 'source':None})
    seen=set()
    for row in rows:
        relative=Path(row['relative']);path=ctx.work/relative
        if (relative.is_absolute() or '..' in relative.parts or '\\' in row['relative']
                or row['relative'] in seen or path.is_symlink()
                or not path.resolve().is_relative_to(ctx.work)):
            raise ValueError('unsafe q0 installation target')
        seen.add(row['relative'])
        if not path.parent.is_dir():raise ValueError('q0 installation target parent is missing')
        if row['source'] is not None:checked(row['source'])
    return rows


def file_stamp(path):
    stat=path.stat()
    return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns


def cache_adoption(ctx,row,*,mapping=False):
    """Check complete immutable cache bytes; never adopt tmp or overwrite."""
    proof=json.loads(checked(row).read_text())
    expected_status=('complete_mapping_cache_ready_for_owned_adoption' if mapping else 'complete_reference_cache_ready_for_owned_adoption')
    if (proof.get('status')!=expected_status
            or proof.get('workspace_modified') is not False):
        raise ValueError('q0 cache is not ready for explicit adoption')
    relative=proof.get('relative','')
    pattern=(r'grt/evidence/q0_prepare/tasks/q0-map-[a-f0-9]{24}' if mapping else r'grt/evidence/q0_prepare/indexes/reference-index-[a-f0-9]{24}')
    if not re.fullmatch(pattern,relative):
        raise ValueError('unsafe q0 cache destination')
    source=Path(proof['source']);target=ctx.work/relative
    if (not source.is_absolute() or source.is_symlink() or not source.is_dir()
            or source.resolve().is_relative_to(ctx.work)
            or not source.resolve().is_relative_to(ctx.work.parent)
            or source.name!=target.name or target.exists() or target.is_symlink()):
        raise ValueError('q0 cache source/destination is unsafe or already exists')
    current=ctx.work
    for part in Path(relative).parts:
        current/=part
        if current.is_symlink():raise ValueError('linked q0 cache destination')
    rows=proof.get('files',[])
    required=({'query.fa','target.fa','result.paf','command.json','success.json'} if mapping else {'reference.sqlite','success.json'})
    allowed=required | ({'stdout.log','stderr.log'} if mapping else set())
    names={item.get('name') for item in rows}
    if len(rows)!=len(names) or not required<=names<=allowed:
        raise ValueError('q0 cache file inventory differs')
    if {path.name for path in source.iterdir()}!=names:
        raise ValueError('q0 cache contains incomplete or unexpected files')
    stamps={}
    for item in rows:
        path=source/item['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink!=1:raise ValueError('linked or missing q0 cache file')
        before=file_stamp(path)
        if digest(path)!=item['sha256'] or path.stat().st_size!=item['size'] or file_stamp(path)!=before:
            raise ValueError('q0 cache content changed')
        stamps[item['name']]=before
    receipt=json.loads((source/'success.json').read_text())
    if mapping:
        spec=receipt.get('spec',{})
        raw_key='q0-map-'+hashlib.sha256(json.dumps(spec,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
        expected_outputs={relative+'/'+name:next(item for item in rows if item['name']==name)
                          for name in ('query.fa','target.fa','result.paf','command.json')}
        outputs=receipt.get('outputs',[])
        if (receipt.get('status')!='success' or spec.get('schema')!='lgz_q0_mapping_v1'
                or raw_key!=target.name or proof.get('task_id')!=raw_key
                or len(outputs)!=4 or {item.get('path') for item in outputs}!=set(expected_outputs)
                or any(item['sha256']!=expected_outputs[item['path']]['sha256']
                       or item['size']!=expected_outputs[item['path']]['size'] for item in outputs)
                or proof.get('normal_cache_validation_completed') is not True):
            raise ValueError('mapping cache normal receipt differs')
    else:
        db=next(item for item in rows if item['name']=='reference.sqlite')
        if (receipt.get('status')!='success' or receipt.get('key')!=target.name
                or receipt.get('sha256')!=db['sha256'] or receipt.get('size')!=db['size']):
            raise ValueError('q0 cache normal receipt differs')
    checked(row)
    return {'source':str(source),'target':str(target),'relative':relative,
            'ready_receipt':row,'files':rows,'stamps':stamps,'moved':False}


def reference_adoption(ctx):
    row=ctx.transition.get('reference_index_adoption')
    return cache_adoption(ctx,row) if row is not None else None


def move_reference(ctx,lock,record):
    if record is None:return
    owned(ctx,lock);checked(record['ready_receipt'])
    source,target=Path(record['source']),Path(record['target'])
    if source.is_symlink() or not source.is_dir():raise ValueError('q0 cache source changed before adoption')
    if target.exists() or target.is_symlink():raise ValueError('q0 cache destination appeared')
    for name,stamp in record['stamps'].items():
        if file_stamp(source/name)!=stamp:raise ValueError('q0 cache changed before adoption')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.parent.resolve().is_relative_to(ctx.work):raise ValueError('q0 cache parent escaped workspace')
    source.rename(target);record['moved']=True
    for name,stamp in record['stamps'].items():
        if file_stamp(target/name)!=stamp:raise ValueError('q0 cache changed during atomic adoption')


def restore_reference(record):
    if record is None or not record['moved']:return
    source,target=Path(record['source']),Path(record['target'])
    if source.exists() or source.is_symlink():raise ValueError('q0 cache rollback source collision')
    for item in record['files']:
        if digest(target/item['name'])!=item['sha256']:raise ValueError('q0 cache rollback artifact changed')
    target.rename(source);record['moved']=False


def install(ctx,lock,make_declaration):
    owned(ctx,lock);ctx.verify()
    if (ctx.work/'metadata/grt_q0_evidence.json').exists():
        raise ValueError('published q0 evidence must not be migrated by this incident installer')
    rows=targets(ctx);reference=reference_adoption(ctx)
    mappings=[cache_adoption(ctx,row,mapping=True) for row in ctx.transition.get('mapping_adoptions',[])]
    adopted=([reference] if reference is not None else [])+mappings
    if len({row['target'] for row in adopted})!=len(adopted):raise ValueError('duplicate cache adoption destination')
    backup=ctx.transition_path.parent/'installation'
    # Do not guess how to recover an interrupted/previous installation.
    if backup.exists():raise ValueError('prior q0 installation journal requires explicit inspection')
    for row in rows:
        target=ctx.work/row['relative'];expected=row['prior_sha256']
        actual=digest(target) if target.exists() else None
        if actual!=expected:raise ValueError('q0 installation prior identity changed: '+row['relative'])
    backup.mkdir(exist_ok=False);saved=[]
    for i,row in enumerate(rows):
        target=ctx.work/row['relative'];present=target.exists();mode=(target.stat().st_mode&0o777) if present else 0o644
        saved_path=backup/f'{i:03d}.before'
        if present:
            with saved_path.open('xb') as stream:stream.write(target.read_bytes())
            saved_path.chmod(mode)
            if digest(saved_path)!=row['prior_sha256']:raise ValueError('q0 installation backup changed')
        saved.append({**row,'present':present,'mode':mode,'backup':str(saved_path) if present else None})
    receipt={'schema':'incident_q0_installation_v1','status':'backed_up','run_id':lock.run_id,
             'transition_sha256':ctx.transition_sha,'files':saved,
             'initial_alignments_modified':False,'old_baseline_modified':False,'reference_index_adoption':reference,'mapping_adoptions':mappings}
    journal=backup/'receipt.json'
    ctx.contract.atomic_write_json(journal,receipt)
    changed=[]
    try:
        for cache in adopted:
            move_reference(ctx,lock,cache)
            receipt['status']='complete_cache_adopted';ctx.contract.atomic_write_json(journal,receipt)
        # Backup completed before any runtime replacement.
        for row in saved:
            owned(ctx,lock)
            if row['source'] is None:continue
            target=ctx.work/row['relative'];changed.append(row)
            atomic_bytes(target,checked(row['source']).read_bytes(),row['mode'])
            if digest(target)!=row['source']['sha256']:raise ValueError('installed q0 runtime differs')
        declaration=make_declaration()
        if (declaration.get('scientific_builder_modified') is not True
                or declaration.get('native_checkpoint_rewritten') is not False
                or declaration.get('transition_sha256')!=ctx.transition_sha):
            raise ValueError('q0 reader declaration is not the explicit science transition')
        row=saved[-1];owned(ctx,lock);changed.append(row)
        declaration_bytes=(json.dumps(declaration,indent=2,sort_keys=True)+'\n').encode()
        atomic_bytes(ctx.work/row['relative'],declaration_bytes,row['mode'])
        ctx.verify()
        for row in saved:
            expected=row['source']['sha256'] if row['source'] else hashlib.sha256(declaration_bytes).hexdigest()
            if digest(ctx.work/row['relative'])!=expected:raise ValueError('q0 runtime changed during installation')
        receipt.update(status='installed',installed=[{'relative':row['relative'],'sha256':digest(ctx.work/row['relative'])} for row in saved])
        ctx.contract.atomic_write_json(journal,receipt)
    except BaseException:
        # Normal lock is still owned by the caller; restore exact old bytes/mode.
        for row in reversed(changed):
            target=ctx.work/row['relative']
            if row['present']:
                previous=Path(row['backup'])
                if digest(previous)!=row['prior_sha256']:raise ValueError('cannot restore changed q0 backup')
                atomic_bytes(target,previous.read_bytes(),row['mode'])
            else:target.unlink(missing_ok=True)
        for cache in reversed(adopted):restore_reference(cache)
        receipt['status']='rolled_back';ctx.contract.atomic_write_json(journal,receipt)
        raise
    return journal
