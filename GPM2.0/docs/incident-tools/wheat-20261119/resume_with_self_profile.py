"""Owning incident resume with immutable cross routing plus explicit self profiles.

Requires normal workspace ownership. No native source/manifest/command edits;
completed cross leaves and ordinary self batches keep their verified identities.
"""
import argparse
import json
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--validate-only', action='store_true')
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
