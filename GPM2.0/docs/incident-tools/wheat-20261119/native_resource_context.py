"""Original context loaded at its actual path, wrapped only for native resources."""
from pathlib import Path
import json

from native_resource_bootstrap import checked, module
from native_resource_bindings import NativeBindings


def load_context(work,path,*,role,caller):
    plan=json.loads(Path(path).read_text());deps=plan["dependencies"]
    if checked(deps["native_context"]).resolve()!=Path(__file__).resolve():
        raise ValueError("unbound native context adapter")
    original=module("authentic_original_self_context",checked(deps["context"]))
    # Original checks bind its genuine __file__, support and the declared caller.
    ctx=original.load_context(work,path,role=role,caller=caller)
    ctx.selfs=NativeBindings(ctx.selfs)
    previous=ctx.verify
    def verify():
        previous();ctx.selfs.verify_native_resources()
    ctx.verify=verify;ctx.native_original_context=original
    return ctx


def compose(ctx,base_class,*,readonly=False):
    return ctx.native_original_context.compose(ctx,base_class,readonly=readonly)
