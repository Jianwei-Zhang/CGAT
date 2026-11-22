"""Resume only NEW wheat with explicit changed-q0 science and frozen initial work.

Allocation-ready handoff and validation must precede this owner. No update.sh,
full runtime replacement, old caller impersonation or checkpoint migration.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from q0_science_context import opened_transition, checked, digest


def installed(ctx):
    for row in ctx.transition['runtime']:
        target=ctx.work/row['relative']
        if target.is_symlink() or not target.resolve().is_relative_to(ctx.work) or digest(target)!=row['new_sha256']:
            raise ValueError('installed q0 science changed')
    if digest(ctx.work/ctx.helper.LAUNCHER)!=ctx.transition['launcher']['sha256']:
        raise ValueError('installed q0 reader launcher changed')


def execute(path,*,install_runtime=False,threads=32,validate_only=False):
    if threads not in (16,32):raise ValueError('unmeasured CPU budget')
    with opened_transition(path,role='entry',caller=__file__,require_installed=not (install_runtime or validate_only)) as ctx:
        owning=ctx.native_bootstrap.module('authentic_initial_alignment_owner',checked(ctx.plan['dependencies']['entry']))
        rr=ctx.base.rr
        if validate_only:
            units=rr.load_plan(ctx.work)
            if len(units)!=55 or any(unit.unit_id=='degap_gapfill' for unit in units):
                raise ValueError('comparison workflow changed')
            # The real old owner configures the same original checkpoint identities;
            # no Runner/lock/install/commit is invoked in this disposable process.
            owning.configure(ctx)
            from run_outer_checkpoints import OuterCheckpointManager
            readonly=ctx.native_original_context.compose(ctx,OuterCheckpointManager,readonly=True)(ctx.work)
            preceding=[]
            for unit in units:
                if unit.unit_id=='q0_evidence':break
                prepared=readonly.prepare(unit.unit_id,unit.command_relpath)
                if prepared is None:raise ValueError('unverifiable preceding unit: '+unit.unit_id)
                valid,reason=readonly.validate(prepared)
                if not valid:raise ValueError('preceding checkpoint rejected: '+unit.unit_id+': '+reason)
                preceding.append({'unit_id':unit.unit_id,'input_fingerprint':prepared.input_fingerprint,
                    'checkpoint_sha256':ctx.contract.sha256_file(prepared.path)})
                print('Q0_ORIGIN_CHECKPOINT_VALID',unit.unit_id,flush=True)
            if len(preceding)!=25:raise ValueError('unexpected initial alignment checkpoint count')
            ctx.verify()
            report={'status':'q0_transition_all_initial_checkpoints_verified_only',
                'transition_sha256':ctx.transition_sha,'initial_checkpoints':preceding,
                'workspace_modified':False,'q0_runtime_installed':False,'main_task_submitted':False}
            ctx.contract.atomic_write_json(ctx.transition_path.parent/'validation.json',report)
            print(json.dumps(report),flush=True)
            return 0
        run_id=rr.new_run_id();lock=rr.WorkspaceLock(ctx.work,run_id)
        try:
            lock.acquire()
            # install() performs the same full pre-install audit itself. Keep
            # the direct-resume path audited here, but do not pay for that
            # audit twice when the transactional installer is active.
            if not install_runtime:ctx.verify()
            units=rr.load_plan(ctx.work)
            if len(units)!=55 or any(unit.unit_id=='degap_gapfill' for unit in units):
                raise ValueError('comparison workflow changed')
            available=len(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else (os.cpu_count() or 1)
            if available<threads:raise ValueError('allocated CPU affinity is below the requested budget')
            # The old origin verifier may import geometry helpers. Keep those
            # authentic objects untouched; the new declaration and actual q0
            # builder execute in fresh reader processes after installation.
            reader=ctx.native_bootstrap.module('explicit_q0_reader',checked(ctx.transition['dependencies']['reader']))
            if install_runtime:
                stager=ctx.native_bootstrap.module('explicit_q0_installer',checked(ctx.transition['dependencies']['stager']))
                def declaration():return reader.describe_in_fresh_process(ctx)
                stager.install(ctx,lock,declaration)
            installed(ctx)
            prior_verify=ctx.verify
            def verify():prior_verify();installed(ctx)
            ctx.verify=verify
            import run_resources
            if Path(run_resources.__file__).resolve()!=(ctx.work/'.prepare_lib/tools/run_resources.py').resolve():
                raise ValueError('resource update is not the frozen runtime')
            resources=ctx.work/'.run_all/resources.json'
            if resources.exists():
                saved=ctx.transition_path.parent/('resources-before-'+run_id+'.json')
                with saved.open('xb') as stream:stream.write(resources.read_bytes())
                if digest(saved)!=digest(resources):raise ValueError('resource backup differs')
            run_resources.update_resources(ctx.work,{'--threads':[[str(threads)]]},run_id)
            checkpoints=owning.configure(ctx)
            runner=rr.Runner(ctx.work,units,run_id,log_style='detailed',color='never')
            runner.outer_checkpoints=checkpoints(ctx.work)
            print('EXPLICIT_Q0_SCIENCE_RESUME',json.dumps({'transition_sha256':ctx.transition_sha,
                'original_plan_sha256':ctx.plan_sha,'threads':threads,'scientific_builder_modified':True,
                'initial_alignment_profiles_modified':False,'native_checkpoint_rewritten':False}),flush=True)
            return runner.run()
        finally:lock.release()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transition',type=Path,required=True)
    p.add_argument('--validate-only',action='store_true');p.add_argument('--install-runtime',action='store_true');p.add_argument('--threads',type=int,choices=(16,32),default=32)
    a=p.parse_args();raise SystemExit(execute(a.transition,install_runtime=a.install_runtime,threads=a.threads,validate_only=a.validate_only))
