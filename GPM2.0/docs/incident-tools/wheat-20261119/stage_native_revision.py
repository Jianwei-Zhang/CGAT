"""Stage a first native admission revision without rewriting any native receipts.

Compute-node only. No workspace writes, job termination, or reader installation.
The old scientific plan, native specs/wrappers, guard/support modules, and eight-
lane memory acceptance remain exact dependencies. A separate complete pilot
binds the proposed thread rebudgeting. Only the new owner/reader/dispatcher
bundle changes; old success receipts retain their genuine execution identity.
"""
import argparse
import copy
import json
from pathlib import Path
import shlex

from native_resource_bootstrap import (SCHEMA, checked, digest, previous_resources,
                                       scientific_origin, select)

HERE=Path(__file__).resolve().parent
MODULES={"native_bootstrap":"native_resource_bootstrap.py",
    "native_context":"native_resource_context.py", "native_stager":"stage_native_revision.py",
    "native_entry":"resume_native_resources.py", "native_reader":"read_native_resources.py",
    "native_audit":"native_resource_audit.py", "admission":"native_fair_admission.py"}
ADDITIONS={"native_previous","native_thread_calibration","native_thread_pilot"}


def record(path):
    path=Path(path).resolve(strict=True)
    return {"path":str(path),"sha256":digest(path)}


def launcher_text(path,plan):
    return ("#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\nexec python3 -B -u "
        +shlex.quote(plan["dependencies"]["native_reader"]["path"])+" --plan "+shlex.quote(str(path))
        +" --server-dir "+shlex.quote(plan["workspace"])+" --threads 32 --minimap2 minimap2\n")


def verify_thread_calibration(plan):
    """Validate the additional replay proof, not a substitute memory calibration."""
    import native_batch_guard as guard
    deps=plan["dependencies"]
    report=json.loads(checked(deps["native_thread_calibration"]).read_text())
    if report.get("implementation")!=deps["native_thread_pilot"]:
        raise ValueError("thread replay implementation is not bound")
    config=json.loads(checked(report["config"]).read_text())
    cases=report.get("cases",[]); grants=report.get("thread_grants",[])
    baseline=report.get("baseline_thread_grants",[])
    source_cases=config.get("cases",[])
    if (report.get("status")!="guarded_native_replays_byte_identical"
            or report.get("main_workspace_modified") is not False
            or report.get("thread_counts_changed") is not True
            or config.get("allow_thread_rebudget") is not True
            or config.get("workspace")!=plan["workspace"]
            or report.get("native_resource_policy")!=guard.POLICY
            or report.get("lanes")!=2 or config.get("lanes")!=2
            or len(cases)!=2 or len(source_cases)!=2
            or baseline!=[8,8] or grants!=[2,2]
            or [c.get("baseline_threads") for c in source_cases]!=baseline
            or [c.get("threads") for c in source_cases]!=grants):
        raise ValueError("missing complete matching two-case 8-to-2 thread replay")
    runtime=config.get("runtime",{})
    for role,target in (("helper","helper"),("tool","mapper"),("minimap_diagnostics","diagnostics")):
        if runtime.get(role)!=plan["native_runtime"][target]:
            raise ValueError("thread replay used a different native runtime: "+role)
    pilot_adapter=runtime.get("native_adapter",{})
    checked(pilot_adapter)
    if pilot_adapter.get("sha256")!=deps["native_guard"]["sha256"]:
        raise ValueError("thread replay used a different native guard")
    # The pilot ran an isolated byte-identical guard copy. Preserve its genuine
    # path in the proof; production receipts still bind their old production path.
    if len({(c["manifest"]["path"],c["batch_index"]) for c in source_cases})!=2:
        raise ValueError("thread replay requires two distinct native batches")
    for case,source,grant in zip(cases,source_cases,grants):
        receipt=case.get("native_resource_receipt",{})
        if (case.get("source")!=source
                or case.get("identical")!={"raw.paf":True,"result.paf":True}
                or receipt.get("status")!="complete" or receipt.get("policy")!=guard.POLICY
                or receipt.get("thread_grant")!=grant
                or receipt.get("runtime",{}).get("adapter")!=pilot_adapter
                or receipt.get("scientific_parameters_changed") is not False):
            raise ValueError("thread replay has an incomplete or mismatched case")
    # Verify small source records, not multi-GB PAFs on every reader startup.
    # The bound completed pilot performed full source/output byte comparisons.
    checked(report["implementation"])


def verify_transition(plan,origin):
    import native_resource_admission as admission
    deps=plan["dependencies"]
    with previous_resources(deps["native_previous"]) as previous:
        old=previous["dependencies"]
        if (plan.get("native_resource_schema")!=SCHEMA or plan.get("preview_only") is not False
                or json.loads(checked(old["native_origin"]).read_text())!=origin):
            raise ValueError("native revision has a different scientific origin")
        # This exact comparison includes operations/specs/scripts, native_runtime,
        # science parameters, resource reservations, and every other plan field.
        exclude={"dependencies","prior_launcher"}
        if {k:v for k,v in plan.items() if k not in exclude}!={k:v for k,v in previous.items() if k not in exclude}:
            raise ValueError("native revision changed preserved plan/receipt identity")
        if set(deps)!=set(old)|ADDITIONS:
            raise ValueError("native revision dependency inventory differs")
        changed=set(MODULES)|{"launcher"}
        if any(deps[k]!=v for k,v in old.items() if k not in changed):
            raise ValueError("native revision changed a preserved dependency")
        if plan["prior_launcher"]!={"path":str(Path(plan["workspace"])/"prepare_q0_evidence.sh"),
                                    "sha256":old["launcher"]["sha256"]}:
            raise ValueError("native revision does not replace the previous native reader")
    for row in deps.values():checked(row)
    for role,filename in MODULES.items():
        if Path(deps[role]["path"]).resolve()!=HERE/filename:
            raise ValueError("native revision module is outside its declared bundle: "+role)
    if plan["resource_policy"]["reservation_policy"]!=admission.POLICY:
        raise ValueError("native revision changed the resource reservation policy")
    launcher=checked(deps["launcher"])
    if launcher.read_text()!=launcher_text(launcher.parent/"self-plan.json",plan):
        raise ValueError("native revision reader launcher is not canonical")
    verify_thread_calibration(plan)


def stage(previous_path,output,thread_calibration):
    prior_record=record(previous_path); output=Path(output).resolve()
    with previous_resources(prior_record) as previous:
        work=Path(previous["workspace"])
        if output.exists() or output==work or work in output.parents or output in work.parents:
            raise ValueError("a fresh isolated native revision directory is required")
        if (work/"metadata/grt_q0_evidence.json").exists():
            raise ValueError("q0 evidence already published; no implicit reader migration")
        reader=record(work/"prepare_q0_evidence.sh")
        if reader["sha256"]!=previous["dependencies"]["launcher"]["sha256"]:
            raise ValueError("workspace reader is not the previous native reader")
        # The old bootstrap selected the authentic old support and runtime.
        import self_profile_bindings as old_support
        import native_resource_bindings as old_native
        import run_orchestration as contract
        old_native.NativeBindings(old_support.SelfBindings(work,Path(previous_path),contract)).verify(full=True)
        plan=copy.deepcopy(previous)
    deps=plan["dependencies"]
    deps.update({role:record(HERE/name) for role,name in MODULES.items()})
    deps["native_previous"]=prior_record
    deps["native_thread_calibration"]=record(thread_calibration)
    proof=json.loads(checked(deps["native_thread_calibration"]).read_text())
    deps["native_thread_pilot"]=proof["implementation"]
    plan["prior_launcher"]=reader
    with scientific_origin(checked(deps["native_origin"])) as origin:
        select("native_batch_guard",deps["native_guard"])
        bindings=select("native_resource_bindings",deps["native_support"])
        admission=select("native_resource_admission",deps["admission"])
        verify_thread_calibration(plan)
        output.mkdir(); path=output/"self-plan.json"; launcher=output/"prepare_q0_evidence.sh"
        launcher.write_text(launcher_text(path,plan));launcher.chmod(0o755)
        deps["launcher"]=record(launcher)
        verify_transition(plan,origin)
        checked(prior_record)
        if record(work/"prepare_q0_evidence.sh")!=reader:
            raise ValueError("workspace reader changed during native revision staging")
        path.write_text(json.dumps(plan,indent=2,sort_keys=True)+"\n")
        import self_profile_bindings as support
        verified=bindings.NativeBindings(support.SelfBindings(work,path,contract))
        verified.verify(full=True)
        admission.SelfDispatcher(verified,lambda task:True,max_fast=2)
        # Existing guarded outputs must retain acceptance; never re-label them as
        # executions of this dispatcher. Historical unguarded cache remains so.
        receipts=0
        for rel,row in verified.rows.items():
            for key in row["native_specs"]:
                if verified.receipt(rel,int(key)) is not None:receipts+=1
        result={"status":"native_revision_staged_not_installed","plan":record(path),
            "previous_plan":prior_record,"preserved_guarded_receipts":receipts,
            "workspace_modified":False,"native_specs_rewritten":False,"science_profiles_changed":False}
        (output/"staging-receipt.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result),flush=True)
        return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("previous-plan","output","thread-calibration"):
        parser.add_argument("--"+name,type=Path,required=True)
    args=parser.parse_args();stage(args.previous_plan,args.output,args.thread_calibration)
