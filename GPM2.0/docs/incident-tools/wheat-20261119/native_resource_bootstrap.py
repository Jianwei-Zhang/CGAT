"""Select authentic frozen science modules and an explicit resource overlay.

Old extension verification receives the OLD plan, never a relaxed new policy.
No module __file__ is spoofed. Temporary module selections are restored on exit.
"""
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

SCHEMA = "incident_native_resource_overlay_v1"
NAMES = ("full_self_seed_pilot", "composite_self_profile", "extended_self_seed_profile",
         "self_seed_profile", "self_extension_context", "self_profile_bindings",
         "self_profile_context", "self_profile_admission", "self_two_lane_admission",
         "native_batch_guard", "native_resource_bindings", "native_resource_admission",
         "export_routing_provenance")


def digest(path):
    p=Path(path); before=p.stat(); h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    after=p.stat()
    sig=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    if sig(before)!=sig(after): raise ValueError("artifact changed during hashing")
    return h.hexdigest()


def checked(row):
    p=Path(row["path"])
    if not p.is_absolute() or p.is_symlink() or digest(p)!=row["sha256"]:
        raise ValueError("unbound or changed resource overlay dependency: "+str(p))
    return p


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def select(name,row):
    result=module(name,checked(row));sys.modules[name]=result;return result


@contextmanager
def scientific_origin(path):
    path=Path(path).resolve(strict=True); sha=digest(path); plan=json.loads(path.read_text())
    if (plan.get("extension_schema")!="incident_self_extension_plan_v1"
            or plan.get("native_resource_schema") or plan.get("preview_only") is not False):
        raise ValueError("an original final self extension is required")
    deps=plan["dependencies"]
    for row in deps.values(): checked(row)
    parent_path=checked(deps["extension_parent"]); parent=json.loads(parent_path.read_text())
    for row in parent["dependencies"].values(): checked(row)
    previous={name:sys.modules.get(name) for name in NAMES}; before=list(sys.path)
    try:
        sys.path[:0]=[str(Path(plan["workspace"])/".prepare_lib/tools"),
                      str(Path(deps["entry"]["path"]).parent),str(Path(__file__).parent)]
        select("full_self_seed_pilot",deps["pilot"])
        select("self_extension_context",deps["extension_bootstrap"])
        select("extended_self_seed_profile",deps["extension_runtime"])
        factory=select("composite_self_profile",deps["profile_factory"])
        sys.modules["self_seed_profile"]=factory
        select("self_profile_bindings",deps["support"])
        select("self_profile_context",deps["context"])
        old_admission=select("self_two_lane_admission",deps["admission"])
        sys.modules["self_profile_admission"]=old_admission
        select("export_routing_provenance",deps["cross_audit"])
        verifier=module("authentic_original_extension_verifier",checked(deps["extension_stager"]))
        verifier.verify_transition(plan,parent)
        if digest(path)!=sha: raise ValueError("origin plan changed during validation")
        yield plan
    finally:
        sys.path[:]=before
        for name,old in previous.items():
            if old is None: sys.modules.pop(name,None)
            else: sys.modules[name]=old


@contextmanager
def previous_resources(row):
    """Verify a first-generation overlay with its own authentic frozen modules.

    Revision chains are deliberately unsupported here. They need an explicit
    protocol, not recursion through possibly circular plan references.
    """
    path=checked(row); plan=json.loads(path.read_text())
    if (plan.get("native_resource_schema")!=SCHEMA
            or "native_previous" in plan.get("dependencies",{})):
        raise ValueError("a first-generation native resource plan is required")
    deps=plan["dependencies"]
    old_bootstrap=module("authentic_previous_native_bootstrap",checked(deps["native_bootstrap"]))
    names=set(NAMES)|set(old_bootstrap.NAMES)|{"native_resource_bootstrap"}
    saved={name:sys.modules.get(name) for name in names}; before=list(sys.path)
    try:
        sys.modules["native_resource_bootstrap"]=old_bootstrap
        with old_bootstrap.installed(path,role="native_stager",caller=deps["native_stager"]["path"]) as verified:
            if verified!=plan:
                raise ValueError("previous resource plan changed during selection")
            yield verified
            checked(row)
    finally:
        sys.path[:]=before
        for name,old in saved.items():
            if old is None: sys.modules.pop(name,None)
            else: sys.modules[name]=old


@contextmanager
def installed(path,*,role,caller):
    path=Path(path).resolve(strict=True); sha=digest(path); plan=json.loads(path.read_text())
    deps=plan["dependencies"]
    if plan.get("native_resource_schema")!=SCHEMA or plan.get("preview_only") is not False:
        raise ValueError("a final explicit native resource overlay is required")
    for row in deps.values(): checked(row)
    for key,actual in (("native_bootstrap",__file__),(role,caller)):
        if checked(deps[key]).resolve()!=Path(actual).resolve():
            raise ValueError("unbound native resource entry: "+key)
    with scientific_origin(checked(deps["native_origin"])) as origin:
        select("native_batch_guard",deps["native_guard"])
        select("native_resource_bindings",deps["native_support"])
        admission=select("native_resource_admission",deps["admission"])
        sys.modules["self_profile_admission"]=admission
        verifier=module("native_resource_transition",checked(deps["native_stager"]))
        verifier.verify_transition(plan,origin)
        select("self_profile_context",deps["native_context"])
        if digest(path)!=sha: raise ValueError("resource plan changed during validation")
        yield plan
