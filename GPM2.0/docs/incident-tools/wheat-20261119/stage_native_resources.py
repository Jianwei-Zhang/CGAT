"""Compute-node-only resource staging, without editing the analysis workspace."""
import argparse
import copy
import json
from pathlib import Path
import shlex
import shutil

from native_resource_bootstrap import SCHEMA, checked, digest, scientific_origin

HERE=Path(__file__).resolve().parent
MODULES={"native_bootstrap":"native_resource_bootstrap.py", "native_context":"native_resource_context.py",
    "native_support":"native_resource_bindings.py", "native_guard":"native_batch_guard.py",
    "native_stager":"stage_native_resources.py", "native_entry":"resume_native_resources.py",
    "native_reader":"read_native_resources.py", "native_audit":"native_resource_audit.py",
    "admission":"native_resource_admission.py"}
ADDITIONS=set(MODULES)-{"admission"}|{"native_origin","native_calibration","fast_admission"}
TOP_CHANGES={"dependencies","operations","resource_policy","prior_launcher",
             "native_resource_schema","native_runtime"}


def record(path):
    p=Path(path).resolve(strict=True);return {"path":str(p),"sha256":digest(p)}


def launcher_text(plan_path,plan):
    return ("#!/usr/bin/env bash\nset -euo pipefail\nexport PYTHONDONTWRITEBYTECODE=1\nexec python3 -B -u "
        +shlex.quote(plan["dependencies"]["native_reader"]["path"])+" --plan "+shlex.quote(str(plan_path))
        +" --server-dir "+shlex.quote(plan["workspace"])+" --threads 32 --minimap2 minimap2\n")


def verify_transition(plan,origin):
    import native_resource_admission as admission
    import native_batch_guard as guard
    if (plan.get("native_resource_schema")!=SCHEMA or origin.get("native_resource_schema")
            or origin.get("extension_schema")!="incident_self_extension_plan_v1"
            or plan.get("preview_only") is not False):
        raise ValueError("invalid native resource origin/schema")
    if {k:v for k,v in plan.items() if k not in TOP_CHANGES}!={k:v for k,v in origin.items() if k not in TOP_CHANGES}:
        raise ValueError("resource transition changed scientific plan fields")
    deps=plan["dependencies"]; old=origin["dependencies"]
    if set(deps)!=set(old)|ADDITIONS:
        raise ValueError("resource dependency inventory differs")
    for name,row in old.items():
        if name not in ("admission","launcher") and deps[name]!=row:
            raise ValueError("resource transition changed scientific dependency: "+name)
    if deps["fast_admission"]!=old["admission"]:
        raise ValueError("fast admission must remain the original implementation")
    if json.loads(checked(deps["native_origin"]).read_text())!=origin:
        raise ValueError("resource origin does not match its bound artifact")
    expected=copy.deepcopy(origin["resource_policy"]);expected["reservation_policy"]=admission.POLICY
    if plan["resource_policy"]!=expected or expected["max_fast"]!=2:
        raise ValueError("unexpected native resource policy")
    if len(plan["operations"])!=len(origin["operations"]):
        raise ValueError("resource operation inventory changed")
    for row,prior in zip(plan["operations"],origin["operations"]):
        if {k:v for k,v in row.items() if k not in ("native_scripts","native_specs")}!=prior:
            raise ValueError("resource transition changed scientific operation/profile/commands")
        if "native_scripts" not in row or "native_specs" not in row:
            raise ValueError("missing explicit native wrapper inventory")
    for row in deps.values(): checked(row)
    for role,name in MODULES.items():
        # The new modules form one immutable bundle, not guessed same-name imports.
        if Path(deps[role]["path"]).resolve()!=HERE/name:
            raise ValueError("native resource module is outside the declared bundle: "+role)
    launcher=checked(deps["launcher"])
    if launcher.read_text()!=launcher_text(launcher.parent/"self-plan.json",plan):
        raise ValueError("resource reader launcher is not canonical")
    before=plan["prior_launcher"]
    if before!={"path":str(Path(plan["workspace"])/"prepare_q0_evidence.sh"),"sha256":old["launcher"]["sha256"]}:
        raise ValueError("resource transition does not replace the current original reader")
    calibration=json.loads(checked(deps["native_calibration"]).read_text())
    cases=calibration.get("cases",[]);grants=calibration.get("thread_grants",[])
    if (calibration.get("status")!="guarded_native_replays_byte_identical"
            or calibration.get("main_workspace_modified") is not False
            or calibration.get("native_resource_policy")!=guard.POLICY
            or calibration.get("lanes")!=8 or len(cases)!=8
            or len(grants)!=8 or any(type(n) is not int or not 1<=n<=8 for n in grants)
            or sum(grants)>32
            or any(c.get("identical")!={"raw.paf":True,"result.paf":True}
                or c.get("native_resource_receipt",{}).get("runtime",{}).get("adapter",{}).get("sha256")!=deps["native_guard"]["sha256"]
                for c in cases)):
        raise ValueError("missing matching real eight-lane native guard acceptance")


def stage(origin_path,output,calibration):
    origin_path=Path(origin_path).resolve(strict=True);output=Path(output).resolve()
    before=digest(origin_path)
    with scientific_origin(origin_path) as origin:
        import self_profile_bindings as support
        import run_orchestration as contract
        import native_batch_guard as guard
        import native_resource_bindings as bindings
        import native_resource_admission as admission
        work=Path(origin["workspace"])
        if output.exists() or output==work or work in output.parents or output in work.parents:
            raise ValueError("a fresh isolated resource-plan directory is required")
        if (work/"metadata/grt_q0_evidence.json").exists():
            raise ValueError("q0 evidence already published; no implicit reader migration")
        original=support.SelfBindings(work,origin_path,contract)
        plan=copy.deepcopy(origin);plan["native_resource_schema"]=SCHEMA
        deps=plan["dependencies"]
        deps.update({name:record(HERE/file) for name,file in MODULES.items()})
        deps.update(native_origin=record(origin_path),native_calibration=record(calibration),fast_admission=origin["dependencies"]["admission"])
        plan["resource_policy"]["reservation_policy"]=copy.deepcopy(admission.POLICY)
        mapper=shutil.which("minimap2")
        if not mapper: raise ValueError("frozen mapper is not selected")
        plan["native_runtime"]={"helper":record(work/".prepare_lib/tools/self_alignment_batches.py"),
            "diagnostics":record(work/".prepare_lib/tools/minimap2_diagnostics.py"),"mapper":record(mapper)}
        for row in plan["operations"]:row.update(native_scripts={},native_specs={})
        # expected_spec is shared with actual controller/reader validation.
        view=copy.copy(original);view.plan=plan;view.rows={r["operation"]:r for r in plan["operations"]}
        temporary=object.__new__(bindings.NativeBindings);temporary.original=view
        output.mkdir();(output/"native").mkdir()
        count=0
        for row in plan["operations"]:
            rel=row["operation"];profile=original.profiles[rel]
            for key in sorted(bindings.eligible(profile),key=int):
                i=int(key);stem=rel.replace("/","__")+"__"+key
                spec=output/"native"/(stem+".json");script=output/"native"/(stem+".sh")
                spec.write_text(json.dumps(temporary.expected_spec(rel,i),indent=2,sort_keys=True)+"\n")
                script.write_text(bindings.wrapper_text(deps["native_guard"]["path"],spec));script.chmod(0o755)
                row["native_specs"][key]=record(spec);row["native_scripts"][key]=record(script);count+=1
        path=output/"self-plan.json";launcher=output/"prepare_q0_evidence.sh"
        launcher.write_text(launcher_text(path,plan));launcher.chmod(0o755)
        deps["launcher"]=record(launcher);plan["prior_launcher"]=record(work/"prepare_q0_evidence.sh")
        verify_transition(plan,origin)
        if digest(origin_path)!=before:raise ValueError("origin changed while staging resources")
        path.write_text(json.dumps(plan,indent=2,sort_keys=True)+"\n")
        verified=bindings.NativeBindings(support.SelfBindings(work,path,contract))
        verified.verify(full=True)
        admission.SelfDispatcher(verified,lambda task:True,max_fast=2)
        result={"status":"native_resource_plan_staged_not_installed","plan":record(path),
                "eligible_native_batches":count,"workspace_modified":False,"science_profiles_changed":False}
        (output/"staging-receipt.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps(result),flush=True);return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("origin-plan","output","calibration"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();stage(a.origin_plan,a.output,a.calibration)
