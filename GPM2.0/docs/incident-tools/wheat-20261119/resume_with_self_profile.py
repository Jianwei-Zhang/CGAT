"""Owning incident resume with immutable cross routing plus explicit self profiles.

Requires normal workspace ownership. No native source/manifest/command edits;
completed cross leaves and ordinary self batches keep their verified identities.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

from self_profile_context import compose, load_context


def configure(ctx):
    import self_profile_admission as admission
    if Path(admission.__file__).resolve() != Path(ctx.plan['dependencies']['admission']['path']).resolve():
        raise ValueError('unbound self admission implementation')
    base, cross = ctx.base, ctx.cross
    original_bound, original_outputs = ctx.native_inputs, ctx.native_outputs
    for rel in cross.rows:
        marker = base.HERE / 'cross-leaf-checkpoints' / (ctx.contract.fingerprint(rel) + '.json')
        if marker.exists():
            record = json.loads(marker.read_text())
            if (record.get('status') != 'success' or record.get('command') != rel
                    or record.get('inputs', {}).get('execution_override') != cross.proof(rel)):
                raise ValueError('completed cross leaf or frozen cross plan changed')
    def bound(task, assignment):
        return cross.bind_inputs(task, original_bound(task, assignment))
    def outputs(task):
        result = original_outputs(task)
        receipt = cross.receipt_identity(task, original_bound(task, ctx.assignment))
        return result + ([receipt] if receipt is not None else [])
    base.bound_inputs, base.leaf_outputs = bound, outputs
    base.rr.run_tasks = base.wrap_tasks(ctx.selfs.dispatch(cross.dispatch(base.rr.run_tasks)), ctx.assignment)
    resource = ctx.plan['resource_policy']
    if resource['reservation_policy'] != admission.POLICY:
        raise ValueError('self admission reservation policy differs from staged plan')
    native_exclusive = base.TwoMappingDispatcher().exclusive
    base.rr.AdaptiveDispatcher = lambda: admission.SelfDispatcher(ctx.selfs, native_exclusive, max_fast=resource['max_fast'])
    return compose(ctx, base.ProtectedCheckpoints)


def install_reader(ctx, lock):
    """One launcher replacement, only with the normal acquired workspace lock.

A frozen backup/receipt lives outside the workspace. Never migrate already
published q0 evidence or an existing old reader declaration implicitly.
"""
    if (not lock.acquired or lock.server_dir.resolve() != ctx.work
            or lock._existing_owner().get('run_id') != lock.run_id):
        raise ValueError('reader installation requires current workspace ownership')
    if ctx.plan.get('preview_only') is not False:
        raise ValueError('preview cannot install a reader')
    target = ctx.work / ctx.helper.LAUNCHER
    source = Path(ctx.plan['dependencies']['launcher']['path'])
    before = ctx.plan['prior_launcher']
    expected = ctx.plan['dependencies']['launcher']['sha256']
    if source.is_symlink() or target.is_symlink() or ctx.contract.sha256_file(source) != expected:
        raise ValueError('reader launcher identity differs')
    backup = ctx.path.parent / 'reader-installation'
    receipt_path = backup / 'receipt.json'
    current = ctx.contract.sha256_file(target)
    if current == expected:
        receipt = json.loads(receipt_path.read_text())
        if (receipt.get('installed_sha256') != expected or receipt.get('plan_sha256') != ctx.plan_sha
                or ctx.contract.sha256_file(backup / 'prepare_q0_evidence.sh') != before['sha256']):
            raise ValueError('installed reader has no matching backup/receipt')
        return
    if (str(target) != before['path'] or current != before['sha256']
            or (ctx.work / 'metadata/grt_q0_evidence.json').exists()
            or (ctx.work / ctx.helper.RECEIPT).exists()):
        raise ValueError('prior launcher changed or q0 evidence/declaration already exists')
    backup.mkdir(exist_ok=False)
    old = target.read_bytes()
    old_mode = target.stat().st_mode & 0o777
    saved = backup / 'prepare_q0_evidence.sh'
    saved.write_bytes(old); saved.chmod(old_mode)
    if ctx.contract.sha256_file(saved) != before['sha256']:
        raise ValueError('reader backup differs')
    def replace(data):
        fd, name = tempfile.mkstemp(prefix='.self-reader-install-', dir=ctx.work)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.chmod(name, old_mode); os.replace(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
    try:
        replace(source.read_bytes())
        if ctx.contract.sha256_file(target) != expected:
            raise ValueError('installed launcher differs')
        ctx.contract.atomic_write_json(receipt_path, {'status': 'installed', 'plan_sha256': ctx.plan_sha,
            'prior_sha256': before['sha256'], 'installed_sha256': expected, 'run_id': lock.run_id,
            'backup': str(saved), 'scope': 'launcher_only_under_workspace_lock'})
    except BaseException:
        replace(old)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--install-reader', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    ctx = load_context(Path(plan['workspace']), args.plan, role='entry', caller=__file__)
    if args.validate_only:
        print(json.dumps({'status': 'self_resume_context_verified_only',
            'self_operations': len(ctx.selfs.profiles),
            'approximate_batches': sum(len(p.selected) for p in ctx.selfs.profiles.values()),
            'workspace_modified': False}), flush=True)
        return
    if ctx.plan.get('preview_only') is not False:
        raise ValueError('preview self plan cannot execute a scientific workflow')
    rr = ctx.base.rr
    run_id = rr.new_run_id()
    lock = rr.WorkspaceLock(ctx.work, run_id)
    try:
        lock.acquire()
        ctx.verify()
        if args.install_reader:
            install_reader(ctx, lock)
        if ctx.contract.sha256_file(ctx.work / ctx.helper.LAUNCHER) != ctx.plan['dependencies']['launcher']['sha256']:
            raise ValueError('combined downstream reader launcher has not been installed')
        units = rr.load_plan(ctx.work)
        if len(units) != 55 or any(unit.unit_id == 'degap_gapfill' for unit in units):
            raise ValueError('comparison workflow changed')
        checkpoints = configure(ctx)
        runner = rr.Runner(ctx.work, units, run_id, log_style='detailed', color='never')
        runner.outer_checkpoints = checkpoints(ctx.work)
        print('EXPLICIT_SELF_PROFILE_RESUME', json.dumps({'plan_sha256': ctx.plan_sha,
            'cross_plan_sha256': ctx.cross.plan_hash, 'self_operations': len(ctx.selfs.profiles),
            'approximate_batches': sum(len(p.selected) for p in ctx.selfs.profiles.values()),
            'hash_memo_entries': 16384, 'resource_policy': ctx.plan['resource_policy'], 'native_commands_modified': False}), flush=True)
        return runner.run()
    finally:
        lock.release()


if __name__ == '__main__':
    raise SystemExit(main())
