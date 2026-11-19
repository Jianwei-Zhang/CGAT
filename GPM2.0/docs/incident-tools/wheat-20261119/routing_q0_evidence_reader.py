"""Read explicit routed q0 checkpoints without rewriting their native identity.

Incident entry only. The original evidence builder and its consumers remain
unchanged. A read-only checkpoint manager interprets the already-bound routing
profile, validates all normal outputs plus routing receipts, and adds this
reader declaration and the actual launcher to the evidence input inventory.
No mapping/checkpoint is rewritten and no failed validation is bypassed.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

RECEIPT = "metadata/incident_q0_routing_reader.json"
LAUNCHER = "prepare_q0_evidence.sh"


def reader_class(base, bindings, native_inputs, assignment, support):
    adapted = support.checkpoint_class(base, bindings, native_inputs, assignment)
    class ReadOnlyRoutingCheckpoints(adapted):
        def commit(self, prepared):
            raise support.OverrideError("evidence reader cannot publish or migrate alignment checkpoints")
    return ReadOnlyRoutingCheckpoints


def prepare_with_reader(module, root, reader, bindings, declaration, *, threads, minimap2):
    root = Path(root).resolve(strict=True)
    if root != bindings.work:
        raise ValueError("q0 reader belongs to another workspace")
    bindings.verify()
    contract = bindings.contract
    receipt = root / RECEIPT
    if receipt.is_symlink():
        raise ValueError("linked reader declaration is forbidden")
    if receipt.exists():
        if json.loads(receipt.read_text()) != declaration:
            raise ValueError("reader declaration changed; explicit migration is required")
    else:
        contract.atomic_write_json(receipt, declaration)
    before = contract.file_identity(receipt, relative_to=root)
    original_builder = module.builder_identity
    builder = original_builder()
    launcher_before = contract.file_identity(root / LAUNCHER, relative_to=root)
    original_class, original_inputs = module.OuterCheckpointManager, module._initial_inputs
    def checked_builder():
        # The original builder calls this before its atomic success publication.
        # Keep its exact identity value, but also fence this reader and launcher.
        bindings.verify()
        if (contract.file_identity(receipt, relative_to=root) != before
                or contract.file_identity(root / LAUNCHER, relative_to=root) != launcher_before):
            raise ValueError("reader declaration or launcher changed before publication")
        return original_builder()
    def inputs(path):
        if Path(path).resolve(strict=True) != root:
            raise ValueError("unexpected workspace in q0 input reader")
        values = list(original_inputs(path))
        if len(values) != 7:
            raise ValueError("unexpected q0 input-reader contract")
        values[4] = sorted(set(values[4]) | {RECEIPT, LAUNCHER})
        return tuple(values)
    module.OuterCheckpointManager, module._initial_inputs = reader, inputs
    module.builder_identity = checked_builder
    try:
        result = module.prepare_evidence(root, threads=threads, minimap2=minimap2)
        bindings.verify()
        if (contract.file_identity(receipt, relative_to=root) != before
                or module.builder_identity() != builder):
            raise ValueError("reader declaration or scientific builder changed")
        # The unchanged downstream consumer must accept the published manifest.
        verified = module.load_verified_evidence(root)
        paths = {row["path"] for row in verified["inputs"]}
        if verified != result or not {RECEIPT, LAUNCHER} <= paths:
            raise ValueError("reader provenance was not bound into q0 evidence")
        return result
    finally:
        module.OuterCheckpointManager, module._initial_inputs = original_class, original_inputs
        module.builder_identity = original_builder


def load_source(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--validate-reader-only", action="store_true",
                        help="verify frozen modules and plan without building or writing evidence")
    parser.add_argument("--server-dir", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--minimap2", default="minimap2")
    args = parser.parse_args()
    work = args.server_dir.resolve(strict=True)
    sys.path.insert(0, str(work / ".prepare_lib/tools"))
    import run_orchestration as contract
    from run_outer_checkpoints import OuterCheckpointManager
    from run_resources import execution_threads
    from lgz_core import q0_preparation
    plan = json.loads(args.plan.read_text())
    if plan.get("workspace") != str(work):
        raise ValueError("routing plan belongs to another workspace")
    for name in ("support", "base_entry"):
        row = plan["dependencies"][name]
        if contract.sha256_file(Path(row["path"])) != row["sha256"]:
            raise ValueError("frozen routing reader dependency changed: " + name)
    support = load_source("wheat_frozen_routing_support", plan["dependencies"]["support"]["path"])
    bindings = support.RoutingBindings(work, args.plan, contract)
    base_path = Path(plan["dependencies"]["base_entry"]["path"])
    sys.path.insert(0, str(base_path.parent))
    base = load_source("wheat_frozen_native_entry", base_path)
    if base.WORK.resolve() != work:
        raise ValueError("native entry belongs to another workspace")
    assignment = json.loads((base.HERE / "assign.before.json").read_text())
    # Same runtime-only memo as the running controller; values still come from
    # actual reads and no persisted receipts preseed this cache.
    contract._SHA256_CACHE_LIMIT = 8192
    reader = reader_class(OuterCheckpointManager, bindings, base.bound_inputs, assignment, support)
    declaration = {"schema": "incident_q0_routing_reader_v1", "scope": "q0_evidence_checkpoint_reader",
        "reader_sha256": contract.sha256_file(Path(__file__)),
        "routing_plan_sha256": bindings.plan_hash,
        "routing_dependencies": {name: row["sha256"] for name, row in plan["dependencies"].items()},
        "scientific_builder_identity": q0_preparation.builder_identity(),
        "launcher_sha256": contract.sha256_file(work / LAUNCHER),
        "native_checkpoint_rewritten": False, "scientific_builder_modified": False,
        "validation": "native_full_input_output_validation_plus_explicit_routing_receipts"}
    print("Q0_ROUTING_AWARE_READER", json.dumps(declaration), flush=True)
    if args.validate_reader_only:
        print("READER_VALIDATED_ONLY no q0 completion or scientific acceptance claimed", flush=True)
        return
    prepare_with_reader(q0_preparation, work, reader, bindings, declaration,
                        threads=execution_threads(args.threads), minimap2=args.minimap2)


if __name__ == "__main__":
    main()
