"""Truthful changed-q0 reader over unchanged, verified initial alignments."""
import argparse
from pathlib import Path
from q0_science_context import opened_transition, checked


def declaration(ctx, module):
    old_reader=ctx.native_bootstrap.module('authentic_q0_provenance_reader',checked(ctx.plan['dependencies']['reader']))
    extra=old_reader.provenance_inputs(ctx)
    return {'schema':'incident_q0_regional_science_reader_v1',
        'scope':'q0_evidence_regional_discovery_with_original_alignments',
        'reader_sha256':ctx.contract.sha256_file(Path(__file__)),
        'transition_sha256':ctx.transition_sha,'self_plan_sha256':ctx.plan_sha,
        'cross_plan_sha256':ctx.cross.plan_hash,'self_dependencies':ctx.plan['dependencies'],
        'self_profiles':[profile.spec for _,profile in sorted(ctx.selfs.profiles.items())],
        'scientific_builder_identity':module.builder_identity(),
        'launcher_sha256':ctx.transition['launcher']['sha256'],'additional_inputs':extra,
        'scientific_builder_modified':True,'initial_alignment_profiles_modified':False,
        'native_checkpoint_rewritten':False}


def prepare(ctx,module,reader,*,threads,minimap2):
    record=declaration(ctx,module);extra=record['additional_inputs'];original=module._initial_inputs
    def inputs(root):
        if Path(root).resolve(strict=True)!=ctx.work:raise ValueError('unexpected q0 reader workspace')
        values=list(original(root))
        if len(values)!=7:raise ValueError('q0 input-reader contract changed')
        values[4]=sorted(set(values[4])|{row['path'] for row in extra})
        return tuple(values)
    module._initial_inputs=inputs
    try:
        result=ctx.helper.prepare_with_reader(module,ctx.work,reader,ctx,record,threads=threads,minimap2=minimap2)
        ctx.verify()
        if declaration(ctx,module)!=record:raise ValueError('q0 science provenance changed during preparation')
        if not {row['path'] for row in extra}<={row['path'] for row in result['inputs']}:
            raise ValueError('original alignment provenance is missing from q0 evidence')
        return result
    finally:module._initial_inputs=original


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transition',type=Path,required=True)
    parser.add_argument('--server-dir',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=1)
    parser.add_argument('--minimap2',default='minimap2')
    args=parser.parse_args()
    with opened_transition(args.transition,role='reader',caller=__file__,require_installed=True) as ctx:
        if args.server_dir.resolve(strict=True)!=ctx.work:raise ValueError('reader workspace differs')
        from run_outer_checkpoints import OuterCheckpointManager
        from run_resources import execution_threads
        from lgz_core import q0_preparation
        reader=ctx.native_original_context.compose(ctx,OuterCheckpointManager,readonly=True)
        prepare(ctx,q0_preparation,reader,threads=execution_threads(args.threads),minimap2=args.minimap2)


if __name__=='__main__':main()
