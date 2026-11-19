"""Explicit hash-bound module selection for owning/reading a self extension."""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

SCHEMA = 'incident_self_extension_plan_v1'


def digest(path):
    path=Path(path); before=path.stat(); sha=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):sha.update(block)
    after=path.stat()
    signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if signature(before)!=signature(after):raise ValueError('file changed while hashing')
    return sha.hexdigest()


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


@contextmanager
def installed(plan_path,*,role,caller):
    path=Path(plan_path).resolve(strict=True); plan=json.loads(path.read_text()); deps=plan['dependencies']
    if plan.get('extension_schema')!=SCHEMA or plan.get('preview_only') is not False:
        raise ValueError('a final explicit self extension plan is required')
    for row in deps.values():
        if digest(row['path'])!=row['sha256']:raise ValueError('extension execution dependency changed')
    if (Path(deps['extension_bootstrap']['path']).resolve()!=Path(__file__).resolve()
            or Path(deps[role]['path']).resolve()!=Path(caller).resolve()):
        raise ValueError('unbound extension execution entry')
    names=('self_seed_profile','self_profile_admission','self_profile_context','self_profile_bindings')
    previous={name:sys.modules.get(name) for name in names}; before=list(sys.path)
    try:
        sys.path[:0]=[str(Path(plan['workspace'])/'.prepare_lib/tools'),
                      str(Path(deps['entry']['path']).parent),str(Path(__file__).parent)]
        import full_self_seed_pilot as pilot
        if Path(pilot.__file__).resolve()!=Path(deps['pilot']['path']).resolve():
            raise ValueError('unbound frozen pilot dependency')
        for name in names:sys.modules.pop(name,None)
        sys.modules['self_seed_profile']=module('self_seed_profile',deps['profile_factory']['path'])
        sys.modules['self_profile_admission']=module('self_profile_admission',deps['admission']['path'])
        verifier=module('self_extension_transition',deps['extension_stager']['path'])
        parent=json.loads(Path(deps['extension_parent']['path']).read_text())
        verifier.verify_transition(plan,parent)
        yield plan
    finally:
        sys.path[:]=before
        for name,old in previous.items():
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old
