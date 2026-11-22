"""Truthful changed-q0 reader over unchanged, verified initial alignments."""
import argparse
from contextlib import nullcontext
import json
import subprocess
import sys
from pathlib import Path
from q0_science_context import opened_transition, checked


def declaration(ctx, module):
    old_reader=ctx.native_bootstrap.module('authentic_q0_provenance_reader',checked(ctx.plan['dependencies']['reader']))
    extra=old_reader.provenance_inputs(ctx)
    record = {'schema':'incident_q0_regional_science_reader_v1',
        'scope':'q0_evidence_regional_discovery_with_original_alignments',
        'reader_sha256':ctx.contract.sha256_file(Path(__file__)),
        'transition_sha256':ctx.transition_sha,'self_plan_sha256':ctx.plan_sha,
        'cross_plan_sha256':ctx.cross.plan_hash,'self_dependencies':ctx.plan['dependencies'],
        'self_profiles':[profile.spec for _,profile in sorted(ctx.selfs.profiles.items())],
        'scientific_builder_identity':module.builder_identity(),
        'launcher_sha256':ctx.transition['launcher']['sha256'],'additional_inputs':extra,
        'scientific_builder_modified':True,'initial_alignment_profiles_modified':False,
        'native_checkpoint_rewritten':False}
    if 'regional_mapper_loader_policy' in ctx.transition:
        record['regional_mapper_loader_policy'] = ctx.transition['regional_mapper_loader_policy']
    return record



def describe_in_fresh_process(ctx):
    """Never import the new q0 package into an owner holding old binding classes.

    Frozen alignment verification legitimately imports old q0 geometry helpers.
    The genuine new reader runs after installation in a fresh interpreter and
    returns its real builder/provenance declaration; no __file__ spoof/reload.
    """
    path=checked(ctx.transition['dependencies']['reader'])
    try:
        result=subprocess.run([sys.executable,'-B','-u',str(path),'--transition',str(ctx.transition_path),
            '--server-dir',str(ctx.work),'--describe-only'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            universal_newlines=True,check=True)
    except subprocess.CalledProcessError as error:
        raise ValueError('fresh q0 reader declaration failed: '+(error.stderr or '')[-4000:]) from error
    record=json.loads(result.stdout)
    if (record.get('reader_sha256')!=ctx.contract.sha256_file(path)
            or record.get('transition_sha256')!=ctx.transition_sha
            or record.get('scientific_builder_modified') is not True):
        raise ValueError('fresh reader returned an unbound builder declaration')
    return record

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
    parser.add_argument('--describe-only',action='store_true')
    args=parser.parse_args()
    with opened_transition(args.transition,role='reader',caller=__file__,require_installed=True) as ctx:
        if args.server_dir.resolve(strict=True)!=ctx.work:raise ValueError('reader workspace differs')
        from run_outer_checkpoints import OuterCheckpointManager
        from run_resources import execution_threads
        from lgz_core import q0_preparation
        if args.describe_only:
            print(json.dumps(declaration(ctx,q0_preparation)),flush=True)
            return
        reader=ctx.native_original_context.compose(ctx,OuterCheckpointManager,readonly=True)
        policy = ctx.transition.get('regional_mapper_loader_policy')
        if policy is None:
            loader = nullcontext(False)
        elif policy == 'clear_same_dependencies_v1':
            from lgz_core.q0_regional_mapping import verified_mapper_loader
            loader = verified_mapper_loader(args.minimap2)
        else:
            raise ValueError('unknown regional mapper loader policy')
        with loader as active:
            if policy is not None:
                print('LGZ q0 regional mapper loader: '+('verified_child_only' if active else 'inherited_fallback'), flush=True)
            prepare(ctx,q0_preparation,reader,threads=execution_threads(args.threads),minimap2=args.minimap2)


if __name__=='__main__':main()
