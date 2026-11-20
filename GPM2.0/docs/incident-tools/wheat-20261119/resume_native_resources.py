"""Own the unchanged scientific workflow with guarded native resource admission.

Submission/handoff must first verify a single x86 node allocation of 32 CPUs and
320 GiB, stop only the newer job, and confirm its children and normal lock exited.
This entry never bypasses workspace ownership or changes scientific parameters.
"""
import argparse
import json
import os
from pathlib import Path

from native_resource_bootstrap import installed, module, checked


def execute(path,*,validate_only=False,install_reader=False,threads=32):
    if threads not in (16,32):raise ValueError("only the measured 16/32 CPU budgets are supported")
    with installed(path,role="native_entry",caller=__file__) as plan:
        from self_profile_context import load_context
        import self_profile_admission as admission
        ctx=load_context(Path(plan["workspace"]),path,role="native_entry",caller=__file__)
        admission.SelfDispatcher(ctx.selfs,ctx.base.TwoMappingDispatcher().exclusive,
                                 max_fast=plan["resource_policy"]["max_fast"])
        owning=module("authentic_original_self_owner",checked(plan["dependencies"]["entry"]))
        if validate_only:
            # Exercise the real configuration/cross-receipt checks in this
            # disposable process; no Runner, installation or ownership occurs.
            owning.configure(ctx)
            print(json.dumps({"status":"native_resource_controller_verified_only",
                "self_operations":len(ctx.selfs.profiles),"eligible_native_batches":len(ctx.selfs.native_tasks),
                "workspace_modified":False,"q0_completed":False}),flush=True)
            return 0
        rr=ctx.base.rr;run_id=rr.new_run_id();lock=rr.WorkspaceLock(ctx.work,run_id)
        try:
            lock.acquire();ctx.verify()
            units=rr.load_plan(ctx.work)
            if len(units)!=55 or any(unit.unit_id=="degap_gapfill" for unit in units):
                raise ValueError("comparison workflow changed")
            available=len(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else (os.cpu_count() or 1)
            if available<threads:raise ValueError("allocated CPU affinity is below the requested budget")
            if install_reader:owning.install_reader(ctx,lock)
            if ctx.contract.sha256_file(ctx.work/ctx.helper.LAUNCHER)!=plan["dependencies"]["launcher"]["sha256"]:
                raise ValueError("native resource evidence reader has not been installed")
            import run_resources
            if Path(run_resources.__file__).resolve()!=(ctx.work/".prepare_lib/tools/run_resources.py").resolve():
                raise ValueError("resource update is not using the frozen workspace runtime")
            prior=ctx.work/".run_all/resources.json"
            saved=ctx.path.parent/("resources-before-"+run_id+".json")
            if prior.exists():
                with saved.open("xb") as f:f.write(prior.read_bytes())
                if ctx.contract.sha256_file(saved)!=ctx.contract.sha256_file(prior):
                    raise ValueError("resource backup differs before budget update")
            run_resources.update_resources(ctx.work,{"--threads":[[str(threads)]]},run_id)
            checkpoints=owning.configure(ctx)
            runner=rr.Runner(ctx.work,units,run_id,log_style="detailed",color="never")
            runner.outer_checkpoints=checkpoints(ctx.work)
            print("EXPLICIT_NATIVE_RESOURCE_RESUME",json.dumps({"plan_sha256":ctx.plan_sha,
                "threads":threads,"resource_policy":plan["resource_policy"],
                "native_commands_modified":False,"scientific_profiles_changed":False}),flush=True)
            return runner.run()
        finally:lock.release()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--validate-only",action="store_true");p.add_argument("--install-reader",action="store_true")
    p.add_argument("--threads",type=int,choices=(16,32),default=32)
    a=p.parse_args();raise SystemExit(execute(a.plan,validate_only=a.validate_only,install_reader=a.install_reader,threads=a.threads))
