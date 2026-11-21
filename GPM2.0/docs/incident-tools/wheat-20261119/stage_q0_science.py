"""Transactional q0-only installation under the normal acquired workspace lock.

The old declaration is explicitly migrated, never silently accepted as the new
builder. Initial alignment files/checkpoints and old source plans are untouched.
A failure restores every changed path; the complete backup remains for audit.
"""
import json
import os
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


def install(ctx,lock,make_declaration):
    owned(ctx,lock);ctx.verify()
    if (ctx.work/'metadata/grt_q0_evidence.json').exists():
        raise ValueError('published q0 evidence must not be migrated by this incident installer')
    rows=targets(ctx)
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
             'initial_alignments_modified':False,'old_baseline_modified':False}
    journal=backup/'receipt.json'
    ctx.contract.atomic_write_json(journal,receipt)
    changed=[]
    try:
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
            expected=row['source']['sha256'] if row['source'] else __import__('hashlib').sha256(declaration_bytes).hexdigest()
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
        receipt['status']='rolled_back';ctx.contract.atomic_write_json(journal,receipt)
        raise
    return journal
