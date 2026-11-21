"""Explicit q0 science transition over unchanged frozen alignment provenance.

This does not call an old entry with a fabricated caller or modify __file__.
A new transition binds its actual caller, and separately verifies the authentic
old scientific/resource libraries. The old native plan stays byte-for-byte
unchanged, including its protected checkpoint dependency dictionaries.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

SCHEMA = 'incident_q0_science_transition_v1'


def digest(path):
    path=Path(path);before=path.stat();h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    after=path.stat()
    signature=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if signature(before)!=signature(after):raise ValueError('transition file changed while hashing')
    return h.hexdigest()


def checked(row):
    path=Path(row['path'])
    if not path.is_absolute() or path.is_symlink() or digest(path)!=row['sha256']:
        raise ValueError('changed/unbound q0 transition dependency: '+str(path))
    return path.resolve(strict=True)


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@contextmanager
def native_libraries(record):
    """Verify the frozen native plan, without impersonating its entry role."""
    path=checked(record);plan=json.loads(path.read_text());deps=plan['dependencies']
    if plan.get('native_resource_schema')!='incident_native_resource_overlay_v1' or plan.get('preview_only') is not False:
        raise ValueError('a final native resource origin is required')
    for row in deps.values():checked(row)
    bootstrap=module('authentic_q0_native_bootstrap',checked(deps['native_bootstrap']))
    if Path(bootstrap.__file__).resolve()!=checked(deps['native_bootstrap']):raise ValueError('native bootstrap path differs')
    names=set(bootstrap.NAMES)|{'native_resource_bootstrap'}
    saved={name:sys.modules.get(name) for name in names};old_path=list(sys.path)
    try:
        sys.modules['native_resource_bootstrap']=bootstrap
        with bootstrap.scientific_origin(checked(deps['native_origin'])) as origin:
            bootstrap.select('native_batch_guard',deps['native_guard'])
            bootstrap.select('native_resource_bindings',deps['native_support'])
            admission=bootstrap.select('native_resource_admission',deps['admission'])
            sys.modules['self_profile_admission']=admission
            verifier=bootstrap.module('authentic_q0_resource_transition',checked(deps['native_stager']))
            verifier.verify_transition(plan,origin)
            bootstrap.select('self_profile_context',deps['native_context'])
            checked(record)
            yield path,plan,bootstrap
            checked(record)
    finally:
        sys.path[:]=old_path
        for name,previous in saved.items():
            if previous is None:sys.modules.pop(name,None)
            else:sys.modules[name]=previous


def origin_context(path,plan,bootstrap):
    """Construct only the old immutable alignment context for a NEW caller.

    The caller identity is checked by opened_transition below, not by passing an
    old pathname to old load_context. All old content/runtime/profile checks
    remain explicit here and in the authentic frozen binding classes.
    """
    work=Path(plan['workspace']).resolve(strict=True);deps=plan['dependencies']
    sys.path.insert(0,str(work/'.prepare_lib/tools'))
    import run_orchestration as contract
    if Path(contract.__file__).resolve()!=(work/'.prepare_lib/tools/run_orchestration.py').resolve():
        raise ValueError('orchestration library is not the workspace runtime')
    original=bootstrap.module('authentic_q0_original_context',checked(deps['context']))
    original.checked_dependencies(plan,contract)
    if Path(original.__file__).resolve()!=checked(deps['context']) or Path(original.self_support.__file__).resolve()!=checked(deps['support']):
        raise ValueError('original context/support are not authentic')
    cross_path=checked(deps['cross_plan']);cross_plan=json.loads(cross_path.read_text())
    original.checked_dependencies(cross_plan,contract)
    cross_support=original.load_source('authentic_q0_cross_support',cross_plan['dependencies']['support']['path'])
    cross=cross_support.RoutingBindings(work,cross_path,contract)
    base_path=Path(cross_plan['dependencies']['base_entry']['path'])
    sys.path.insert(0,str(base_path.parent))
    base=original.load_source('authentic_q0_native_owner',base_path)
    if base.WORK.resolve()!=work:raise ValueError('native owner belongs to another workspace')
    runtime=json.loads((base.HERE/'receipt.json').read_text())['runtime_files']
    def original_runtime():
        for row in runtime:
            if contract.sha256_file(Path(row['path']))!=row['sha256']:
                raise ValueError('original protected runtime changed')
        if json.loads((base.ROOT/'reference-import-receipt.json').read_text()).get('status')!='verified_reference_only_import':
            raise ValueError('verified reference import is absent')
    original_runtime()
    contract._SHA256_CACHE_LIMIT=16384
    from native_resource_bindings import NativeBindings
    selfs=NativeBindings(original.self_support.SelfBindings(work,path,contract))
    helper=original.load_source('authentic_q0_reader_helper',deps['reader_helper']['path'])
    ctx=SimpleNamespace(work=work,path=path,plan=plan,contract=contract,plan_sha=contract.sha256_file(path),
        cross=cross,selfs=selfs,cross_support=cross_support,base=base,helper=helper,
        native_inputs=base.bound_inputs,native_outputs=base.leaf_outputs,
        assignment=json.loads((base.HERE/'assign.before.json').read_text()),native_original_context=original)
    def verify():
        original_runtime();cross.verify();selfs.verify()
    ctx.verify=verify
    return ctx


@contextmanager
def opened_transition(path,*,role,caller,require_installed):
    path=Path(path).resolve(strict=True);identity=digest(path);transition=json.loads(path.read_text())
    if transition.get('schema')!=SCHEMA:
        raise ValueError('explicit q0 science transition is required')
    phase=transition.get('phase')
    if phase=='origin_probe':
        if role!='probe' or require_installed or transition.get('scientific_builder_modified') is not False:
            raise ValueError('origin-only probe cannot install or execute changed q0 science')
        required_roles={'context','probe'}
    elif phase=='prepared':
        if transition.get('scientific_builder_modified') is not True or role not in {'entry','reader','stager'}:
            raise ValueError('prepared q0 transition needs a real bound execution role')
        required_roles={'context','entry','reader','stager'}
    else:raise ValueError('unsupported q0 transition phase')
    dependencies=transition['dependencies']
    if set(dependencies)!=required_roles:raise ValueError('q0 transition dependency inventory differs')
    for row in dependencies.values():checked(row)
    if checked(dependencies['context'])!=Path(__file__).resolve() or checked(dependencies[role])!=Path(caller).resolve():
        raise ValueError('new q0 caller/context is not bound to this transition')
    work=Path(transition['workspace']).resolve(strict=True)
    if path.is_relative_to(work):raise ValueError('transition plan must be isolated from its workspace')
    if phase=='prepared':
        runtime=transition.get('runtime')
        if not isinstance(runtime,list) or not runtime:raise ValueError('prepared transition has no runtime inventory')
        seen=set()
        for row in runtime:
            relative=Path(row['relative'])
            if (relative.is_absolute() or '..' in relative.parts or '\\' in row['relative']
                    or relative.parent.as_posix()!='.prepare_lib/tools/lgz_core'
                    or relative.suffix!='.py' or row['relative'] in seen):
                raise ValueError('unsafe or duplicate q0 runtime path')
            seen.add(row['relative']);source=checked(row['source'])
            if source.is_relative_to(work) or row['new_sha256']!=row['source']['sha256']:
                raise ValueError('runtime source must be isolated and exactly bound')
        if checked(transition['launcher']).is_relative_to(work):raise ValueError('new launcher source is not isolated')

    with native_libraries(transition['native_origin']) as (old_path,old_plan,bootstrap):
        if Path(old_plan['workspace']).resolve()!=work:raise ValueError('transition and native origin workspaces differ')
        ctx=origin_context(old_path,old_plan,bootstrap)
        def verify_transition():
            if digest(path)!=identity:raise ValueError('q0 transition plan changed')
            for row in dependencies.values():checked(row)
            checked(transition['native_origin'])
            if phase=='prepared':
                for row in transition['runtime']:checked(row['source'])
                checked(transition['launcher'])
            if require_installed:
                for row in transition['runtime']:
                    target=work/row['relative']
                    if target.is_symlink() or not target.resolve().is_relative_to(work) or digest(target)!=row['new_sha256']:
                        raise ValueError('q0 runtime is not installed as declared')
                if digest(work/ctx.helper.LAUNCHER)!=transition['launcher']['sha256']:
                    raise ValueError('new q0 launcher is not installed')
        original_verify=ctx.verify
        def verify():original_verify();verify_transition()
        ctx.verify=verify;ctx.transition=transition;ctx.transition_path=path;ctx.transition_sha=identity
        ctx.native_bootstrap=bootstrap
        ctx.verify()
        yield ctx
        ctx.verify()
