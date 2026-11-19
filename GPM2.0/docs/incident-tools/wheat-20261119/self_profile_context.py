"""Load the same frozen native/cross/self context for controller and reader."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import self_profile_bindings as self_support


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checked_dependencies(plan, contract):
    for row in plan['dependencies'].values():
        if contract.sha256_file(Path(row['path'])) != row['sha256']:
            raise ValueError('frozen self resume dependency changed: ' + row['path'])


def compose(ctx, base_class, *, readonly=False):
    cross_class = ctx.cross_support.checkpoint_class(base_class, ctx.cross, ctx.native_inputs, ctx.assignment)
    combined = self_support.checkpoint_class(cross_class, ctx.selfs)
    if not readonly:
        return combined
    class ReadOnly(combined):
        def commit(self, prepared):
            raise ValueError('evidence reader cannot publish or migrate alignment checkpoints')
    return ReadOnly


def load_context(work, path, *, role, caller):
    work, path = Path(work).resolve(strict=True), Path(path).resolve(strict=True)
    plan = json.loads(path.read_text())
    if plan.get('workspace') != str(work):
        raise ValueError('self resume context belongs to another workspace')
    sys.path.insert(0, str(work / '.prepare_lib/tools'))
    import run_orchestration as contract
    checked_dependencies(plan, contract)
    for name, expected in (('context', Path(__file__)), ('support', Path(self_support.__file__)), (role, Path(caller))):
        if Path(plan['dependencies'][name]['path']).resolve() != expected.resolve():
            raise ValueError('unbound self context module: ' + name)
    cross_path = Path(plan['dependencies']['cross_plan']['path'])
    cross_plan = json.loads(cross_path.read_text())
    checked_dependencies(cross_plan, contract)
    cross_support = load_source('wheat_frozen_cross_support_for_self', cross_plan['dependencies']['support']['path'])
    cross = cross_support.RoutingBindings(work, cross_path, contract)
    base_path = Path(cross_plan['dependencies']['base_entry']['path'])
    sys.path.insert(0, str(base_path.parent))
    base = load_source('wheat_native_entry_for_self', base_path)
    if base.WORK.resolve() != work:
        raise ValueError('original native entry belongs to another workspace')
    for row in json.loads((base.HERE / 'receipt.json').read_text())['runtime_files']:
        if contract.sha256_file(Path(row['path'])) != row['sha256']:
            raise ValueError('original incident runtime changed')
    if json.loads((base.ROOT / 'reference-import-receipt.json').read_text()).get('status') != 'verified_reference_only_import':
        raise ValueError('missing verified initial reference import')
    # Raw/result/log identities are now also reused. Every memo entry still
    # comes from real stable bytes and checks the complete file stat signature.
    contract._SHA256_CACHE_LIMIT = 16384
    selfs = self_support.SelfBindings(work, path, contract)
    helper = load_source('wheat_frozen_q0_reader_helper', plan['dependencies']['reader_helper']['path'])
    ctx = SimpleNamespace(work=work, path=path, plan=plan, contract=contract,
        plan_sha=contract.sha256_file(path), cross=cross, selfs=selfs,
        cross_support=cross_support, base=base, helper=helper,
        native_inputs=base.bound_inputs, native_outputs=base.leaf_outputs,
        assignment=json.loads((base.HERE / 'assign.before.json').read_text()))
    def verify():
        cross.verify(); selfs.verify()
    ctx.verify = verify
    return ctx
