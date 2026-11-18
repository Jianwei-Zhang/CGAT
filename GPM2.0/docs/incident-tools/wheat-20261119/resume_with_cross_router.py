"""Explicit incident resume; stage first, submit only after the old job stops.

No workspace command/helper/manifest changes. The alternate execution and its
receipts are bound into both cross-leaf and q0 outer checkpoint identities.
Native references, assignment and completed leaves retain their original keys.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

from routing_resume_support import RoutingBindings, OverrideError, checkpoint_class


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    plan_path = Path(args.plan).resolve(strict=True)
    plan = json.loads(plan_path.read_text())
    work = Path(plan["workspace"])
    sys.path.insert(0, str(work / ".prepare_lib/tools"))
    import run_orchestration as contract
    bindings = RoutingBindings(work, plan_path, contract)
    base_path = Path(plan["dependencies"]["base_entry"]["path"])
    sys.path.insert(0, str(base_path.parent))
    spec = importlib.util.spec_from_file_location("wheat_native_resume", base_path)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    if base.WORK.resolve() != work.resolve():
        raise OverrideError("base entry belongs to another workspace")
    if Path(__file__).resolve() != Path(plan["dependencies"]["entry"]["path"]).resolve():
        raise OverrideError("unbound resume entry")
    for row in json.loads((base.HERE / "receipt.json").read_text())["runtime_files"]:
        if contract.sha256_file(Path(row["path"])) != row["sha256"]:
            raise OverrideError("frozen incident runtime changed")
    imported = json.loads((base.ROOT / "reference-import-receipt.json").read_text())
    if imported.get("status") != "verified_reference_only_import":
        raise OverrideError("missing verified initial reference import")
    # Real hashes still originate from reads; no persistent receipts seed this
    # process-local memo. Avoid evicting a ~3300-file workspace after 256 reads.
    contract._SHA256_CACHE_LIMIT = 8192
    rr = base.rr
    run_id = rr.new_run_id()
    lock = rr.WorkspaceLock(work, run_id)
    try:
        lock.acquire()
        bindings.verify()
        assignment = json.loads((base.HERE / "assign.before.json").read_text())
        original_bound, original_outputs = base.bound_inputs, base.leaf_outputs
        for rel in bindings.rows:
            marker = base.HERE / "cross-leaf-checkpoints" / (contract.fingerprint(rel) + ".json")
            if marker.exists():
                record = json.loads(marker.read_text())
                if (record.get("status") != "success" or record.get("command") != rel
                        or record.get("inputs", {}).get("execution_override") != bindings.proof(rel)):
                    raise OverrideError("native leaf completed or plan changed; preserve it and regenerate plan: " + rel)
        def bound(task, assigned):
            return bindings.bind_inputs(task, original_bound(task, assigned))
        def outputs(task):
            rows = original_outputs(task)
            receipt = bindings.receipt_identity(task, original_bound(task, assignment))
            return rows + ([receipt] if receipt is not None else [])
        base.bound_inputs, base.leaf_outputs = bound, outputs
        RoutingCheckpoints = checkpoint_class(base.ProtectedCheckpoints, bindings, original_bound, assignment)
        units = rr.load_plan(work)
        if len(units) != 55 or any(u.unit_id == "degap_gapfill" for u in units):
            raise OverrideError("comparison workflow changed")
        rr.AdaptiveDispatcher = base.TwoMappingDispatcher
        rr.run_tasks = base.wrap_tasks(bindings.dispatch(rr.run_tasks), assignment)
        runner = rr.Runner(work, units, run_id, log_style="detailed", color="never")
        runner.outer_checkpoints = RoutingCheckpoints(work)
        print("EXPLICIT_ROUTING_RESUME", json.dumps({"plan_sha256": bindings.plan_hash,
              "overridden_leaves": sorted(bindings.rows), "process_hash_cache": 8192,
              "workspace_commands_modified": False}), flush=True)
        return runner.run()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
