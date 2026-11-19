"""Read combined native/cross/self evidence without changing scientific builders."""
import argparse
import json
from pathlib import Path

from self_profile_context import compose, load_context


def provenance_inputs(ctx):
    rows = []
    for unit in sorted({row['unit_id'] for row in ctx.selfs.rows.values()}):
        rows.extend(ctx.selfs.output_identities(unit))
    for row in ctx.cross.rows.values():
        rows.append(ctx.contract.file_identity(Path(row['receipt']), relative_to=ctx.work))
    return sorted(rows, key=lambda row: row['path'])


def prepare(ctx, module, reader, *, threads, minimap2):
    if ctx.plan.get('preview_only') is not False:
        raise ValueError('preview self plan cannot publish q0 evidence')
    expected_launcher = ctx.plan['dependencies']['launcher']['sha256']
    if ctx.contract.sha256_file(ctx.work / ctx.helper.LAUNCHER) != expected_launcher:
        raise ValueError('combined q0 launcher is not installed as planned')
    extra = provenance_inputs(ctx)
    declaration = {'schema': 'incident_q0_cross_self_reader_v1',
        'scope': 'q0_evidence_combined_checkpoint_reader',
        'reader_sha256': ctx.contract.sha256_file(Path(__file__)),
        'self_plan_sha256': ctx.plan_sha, 'cross_plan_sha256': ctx.cross.plan_hash,
        'self_dependencies': ctx.plan['dependencies'],
        'self_profiles': [profile.spec for _rel, profile in sorted(ctx.selfs.profiles.items())],
        'scientific_builder_identity': module.builder_identity(),
        'launcher_sha256': expected_launcher, 'additional_inputs': extra,
        'scientific_builder_modified': False, 'native_checkpoint_rewritten': False}
    original = module._initial_inputs
    def inputs(root):
        if Path(root).resolve(strict=True) != ctx.work:
            raise ValueError('unexpected workspace in combined evidence reader')
        values = list(original(root))
        if len(values) != 7:
            raise ValueError('unexpected q0 input-reader contract')
        values[4] = sorted(set(values[4]) | {row['path'] for row in extra})
        return tuple(values)
    module._initial_inputs = inputs
    try:
        result = ctx.helper.prepare_with_reader(module, ctx.work, reader, ctx, declaration,
                                                threads=threads, minimap2=minimap2)
        ctx.verify()
        if provenance_inputs(ctx) != extra:
            raise ValueError('cross/self provenance changed during q0 evidence preparation')
        if not {row['path'] for row in extra} <= {row['path'] for row in result['inputs']}:
            raise ValueError('cross/self provenance is absent from evidence manifest')
        return result
    finally:
        module._initial_inputs = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--server-dir', type=Path, required=True)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--minimap2', default='minimap2')
    parser.add_argument('--validate-reader-only', action='store_true')
    args = parser.parse_args()
    ctx = load_context(args.server_dir, args.plan, role='reader', caller=__file__)
    from run_outer_checkpoints import OuterCheckpointManager
    from run_resources import execution_threads
    from lgz_core import q0_preparation
    reader = compose(ctx, OuterCheckpointManager, readonly=True)
    if args.validate_reader_only:
        print(json.dumps({'status': 'combined_reader_imports_and_plan_verified_only',
            'self_operations': len(ctx.selfs.profiles),
            'approximate_batches': sum(len(p.selected) for p in ctx.selfs.profiles.values()),
            'launcher_installation_verified': False, 'q0_completed': False}), flush=True)
        return
    prepare(ctx, q0_preparation, reader, threads=execution_threads(args.threads), minimap2=args.minimap2)


if __name__ == '__main__':
    main()
