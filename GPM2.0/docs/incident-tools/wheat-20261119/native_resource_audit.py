"""Portable scientific audit plus actual, non-retroactive native guard evidence."""
import argparse
import json
from pathlib import Path
from native_resource_bootstrap import installed, module, checked


def native_rows(ctx):
    rows=[]
    for rel,profile in sorted(ctx.selfs.profiles.items()):
        for i,b in enumerate(profile.native["batches"]):
            if i in profile.selected:continue
            if not profile.validate_batch(i):raise ValueError("native output is incomplete at resource audit")
            path=ctx.selfs.receipt(rel,i)
            row={"operation":rel,"batch_index":i,"native_key":b["key"],
                "result_paf":ctx.contract.file_identity(Path(b["directory"])/"result.paf",relative_to=ctx.work),
                "guard_execution_proven":path is not None}
            if path is not None:
                receipt=json.loads(path.read_text())
                row.update(receipt=ctx.contract.file_identity(path,relative_to=ctx.work),
                    policy=receipt["policy"],thread_grant=receipt["thread_grant"],children=receipt["children"],
                    runtime_sha256={k:v["sha256"] for k,v in receipt["runtime"].items()},
                    specification_sha256=receipt["spec_sha256"])
            else:row["resource_provenance"]="native_without_resource_execution_receipt"
            rows.append(row)
    return rows


def build(ctx):
    scientific=module("authentic_original_cross_self_audit",checked(ctx.plan["dependencies"]["audit_exporter"]))
    result=scientific.build(ctx)
    rows=native_rows(ctx);ctx.verify()
    result["native_resources"]={"schema":"cgat_incident_native_resource_provenance_v1",
        "scientific_parameters_changed":False,"rows":rows,
        "guarded_native_count":sum(row["guard_execution_proven"] for row in rows),
        "historical_receipts_rewritten":False,"reservation_policy":ctx.plan["resource_policy"]}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("work","plan"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--output",type=Path);p.add_argument("--validate-only",action="store_true")
    a=p.parse_args()
    with installed(a.plan,role="native_audit",caller=__file__):
        from self_profile_context import load_context
        import export_routing_provenance as cross_audit
        ctx=load_context(a.work,a.plan,role="native_audit",caller=__file__)
        if a.validate_only:
            ctx.verify();module("authentic_original_cross_self_audit",checked(ctx.plan["dependencies"]["audit_exporter"]))
            print(json.dumps({"status":"native_resource_audit_imports_and_plan_verified_only",
                "q0_completed":False,"workspace_modified":False}),flush=True);return
        if a.output is None or a.output.resolve().is_relative_to(ctx.work) or a.output.is_symlink():
            raise ValueError("portable audit output must be outside the analysis workspace")
        result=build(ctx);cross_audit.publish(result,a.output,ctx.contract)
        print(json.dumps({"status":"portable_native_resource_audit_written","output":str(a.output),
            "sha256":ctx.contract.sha256_file(a.output)}),flush=True)


if __name__=="__main__":main()
