"""Validate and inspect an isolated self candidate; compare only a committed baseline.

No mapper is launched and no native marker/output is modified. Full input/index
hashes and real PAF analysis require a scheduler job. Candidate-only inventory
is explicitly not a baseline comparison or admission decision.
"""
import argparse
import importlib
import json
from pathlib import Path
import sys

import full_self_seed_pilot as pilot
import self_paf_comparison as comparison


OUTPUT_NAMES = {"raw.paf", "result.paf", "stderr.log"}


def checked_files(expected):
    actual = pilot.identities([Path(path) for path in expected])
    if actual != expected:
        raise ValueError("artifact identity changed")
    return actual


def candidate_contract(report, manifest, batch):
    if (report.get("status") != "candidate_complete_not_compared_not_adopted"
            or report.get("candidate_adopted") is not False
            or report.get("analysis_workspace_modified") is not False
            or report.get("mapping", {}).get("returncode") != 0
            or report.get("native_batch_key") != batch["key"]):
        raise ValueError("candidate is not a successful isolated full-self execution")
    if pilot.candidate_command(manifest, batch, report["native_command"]) != report.get("command"):
        raise ValueError("candidate command is not the declared one-flag self variant")
    if report.get("driver_sha256") != pilot.digest(Path(pilot.__file__)):
        raise ValueError("candidate driver differs; use its frozen verifier")


def native_commit(directory, key):
    path = directory / "complete.json"
    if not path.is_file():
        raise ValueError("native batch is not committed; do not compare its temporary PAF")
    raw = path.read_bytes(); marker = json.loads(raw)
    if marker.get("key") != key or set(marker.get("outputs", {})) != OUTPUT_NAMES:
        raise ValueError("native completion marker does not match this batch")
    files = pilot.identities([directory / name for name in sorted(OUTPUT_NAMES)])
    if any(files[str(directory / name)]["sha256"] != marker["outputs"][name] for name in OUTPUT_NAMES):
        raise ValueError("native committed output hash changed")
    if path.read_bytes() != raw:
        raise ValueError("native completion marker changed during validation")
    return {"marker": pilot.identities([path]), "outputs": files, "key": key}


def execute(work, manifest_path, batch_index, candidate_dir, output, *, candidate_only=False):
    work = work.resolve(strict=True)
    pilot.require_isolated(work, output)
    manifest_path.resolve(strict=True).relative_to(work)
    manifest = json.loads(manifest_path.read_text())
    if not 0 <= batch_index < len(manifest["batches"]):
        raise ValueError("invalid self batch index")
    batch = manifest["batches"][batch_index]
    directory = Path(batch["directory"])
    directory.resolve(strict=True).relative_to(work)
    candidate_dir = candidate_dir.resolve(strict=True)
    if candidate_dir == work or work in candidate_dir.parents:
        raise ValueError("candidate must be outside the analysis workspace")
    source_report = candidate_dir / "pilot.json"
    raw_report = source_report.read_bytes()
    report = json.loads(raw_report)
    candidate_contract(report, manifest, batch)
    required_outputs = {str(candidate_dir / name) for name in OUTPUT_NAMES | {"restore.stderr.log"}}
    if set(report["outputs"]) != required_outputs:
        raise ValueError("candidate output inventory is not exactly this isolated run")
    inputs = checked_files(report["inputs"])
    outputs = checked_files(report["outputs"])
    if str(manifest_path) not in inputs or str(Path(batch["query"])) not in inputs:
        raise ValueError("candidate does not bind the requested manifest and query")
    native_commands = [p for p in directory.glob("attempt-*/command.json") if str(p) in inputs]
    if len(native_commands) != 1 or json.loads(native_commands[0].read_text()) != report["native_command"]:
        raise ValueError("native command trace is absent or disagrees")
    tools = work / ".prepare_lib/tools"
    helper_path = tools / "self_alignment_batches.py"
    if str(helper_path) not in inputs:
        raise ValueError("candidate did not bind its self helper")
    sys.path.insert(0, str(tools))
    helper = importlib.import_module("self_alignment_batches")
    if Path(helper.__file__).resolve() != helper_path.resolve():
        raise ValueError("wrong self validation helper imported")
    queries = {row["name"]: row["length"] for row in batch["entries"]}
    targets = manifest["target_lengths"]
    names = dict(line.split("\t", 1) for line in Path(manifest["name_map"]).read_text().splitlines() if line)
    restored_queries = {names[k]: v for k, v in queries.items()}
    restored_targets = {names[k]: v for k, v in targets.items()}
    def validate(directory):
        pilot.verify_completion(directory / "stderr.log", len(queries))
        helper.validate_raw(directory / "raw.paf", queries, targets)
        helper.validate_raw(directory / "result.paf", restored_queries, restored_targets)
    validate(candidate_dir)
    candidate = comparison.read_evidence(candidate_dir / "result.paf", step=1000)
    result = {"scope": "one_full_self_query_diagnostic", "candidate_adopted": False,
        "analysis_workspace_modified": False, "candidate_mapping": report["mapping"],
        "candidate_inventory_1kb": comparison.inventory(candidate),
        "candidate_inputs": inputs, "candidate_outputs": outputs,
        "code_sha256": {"inspection": pilot.digest(Path(__file__)),
                        "comparison": pilot.digest(Path(comparison.__file__)),
                        "candidate_driver": report["driver_sha256"]}}
    if candidate_only:
        result["status"] = "candidate_inventory_only_not_compared_not_adopted"
    else:
        proof = native_commit(directory, batch["key"])
        validate(directory)
        baseline = comparison.read_evidence(directory / "result.paf", step=1000)
        result["comparison_1kb"] = comparison.compare_evidence(baseline, candidate, step=1000)
        result["comparison_10kb"] = comparison.compare(directory / "result.paf", candidate_dir / "result.paf", step=10000)
        if native_commit(directory, batch["key"]) != proof:
            raise ValueError("native commit changed during comparison")
        result["native_commit"] = proof
        result["status"] = "candidate_and_committed_native_compared_not_adopted"
    checked_files(inputs); checked_files(outputs)
    if source_report.read_bytes() != raw_report:
        raise ValueError("candidate report changed during inspection")
    if output.exists():
        raise ValueError("refusing to replace an inspection report")
    helper.atomic_json(output, result)
    print(json.dumps({key: value for key, value in result.items() if key not in (
        "candidate_inputs", "candidate_outputs", "native_commit", "comparison_1kb", "comparison_10kb")}, indent=2))
    for name in ("comparison_1kb", "comparison_10kb"):
        if name in result:
            print(name, json.dumps({key: value for key, value in result[name].items() if key != "pairs"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "manifest", "candidate-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--candidate-only", action="store_true")
    args = parser.parse_args()
    execute(args.work, args.manifest, args.batch_index, args.candidate_dir, args.output,
            candidate_only=args.candidate_only)


if __name__ == "__main__":
    main()
