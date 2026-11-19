"""One whole-record f=.001 candidate reusing the validated original self inputs.

The already-running native batch is NOT rerun. This candidate may later be
adopted only under an explicit approximate execution profile; no native cache
marker is created. Keep the earlier f=.005 pilot and its verifier immutable.
"""
import argparse
import importlib
import json
from pathlib import Path
import signal
import sys

import full_self_seed_pilot as pilot
import inspect_full_self_pilot as inspection

TIMEOUT = 5400
SCOPE = "one_complete_self_query_moderate_candidate_only"


def moderate_command(manifest, batch, native):
    # Validate every native flag, complete query and cached index using the
    # original frozen contract; then change exactly the fixed seed fraction.
    original = pilot.candidate_command(manifest, batch, native)
    if batch["entries"][0]["length"] < 100_000_000:
        raise ValueError("moderate candidate is restricted to >=100 Mb whole queries")
    original[-3] = "0.001"
    return original


def execute(work, manifest_path, batch_index, source_dir, output):
    work = work.resolve(strict=True)
    pilot.require_isolated(work, output)
    manifest_path = manifest_path.resolve(strict=True)
    manifest_path.relative_to(work)
    source_dir = source_dir.resolve(strict=True)
    if (source_dir == work or work in source_dir.parents or source_dir == output.resolve()
            or source_dir in output.resolve().parents or output.resolve() in source_dir.parents):
        raise ValueError("candidate output must be separate from immutable source pilot")
    manifest = json.loads(manifest_path.read_text())
    if not 0 <= batch_index < len(manifest["batches"]):
        raise ValueError("invalid self batch index")
    batch = manifest["batches"][batch_index]
    source_path = source_dir / "pilot.json"
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    inspection.candidate_contract(source, manifest, batch)
    if set(source["outputs"]) != {str(source_dir / n) for n in inspection.OUTPUT_NAMES | {"restore.stderr.log"}}:
        raise ValueError("original pilot output inventory belongs to another directory")
    expected = {**source["inputs"], **source["outputs"]}
    if str(manifest_path) not in source["inputs"] or str(Path(batch["query"])) not in source["inputs"]:
        raise ValueError("source pilot does not bind the requested manifest/query")
    helper_path = work / ".prepare_lib/tools/self_alignment_batches.py"
    if str(helper_path) not in expected:
        raise ValueError("original helper is not bound")
    command = moderate_command(manifest, batch, source["native_command"])
    expected.update(pilot.identities([source_path]))
    inspection.checked_files(expected)
    if source_path.read_bytes() != source_bytes:
        raise ValueError("source pilot changed during preparation")
    sys.path.insert(0, str(helper_path.parent))
    helper = importlib.import_module("self_alignment_batches")
    contract = importlib.import_module("run_orchestration")
    if Path(helper.__file__).resolve() != helper_path.resolve():
        raise ValueError("wrong frozen helper imported")
    queries = {entry["name"]: entry["length"] for entry in batch["entries"]}
    if list(helper.fasta_lengths(Path(batch["query"])).items()) != list(queries.items()):
        raise ValueError("whole query names/lengths/order changed")
    names = dict(line.split("\t", 1) for line in Path(manifest["name_map"]).read_text().splitlines() if line)
    restored_queries = {names[k]: v for k, v in queries.items()}
    restored_targets = {names[k]: v for k, v in manifest["target_lengths"].items()}
    output.mkdir()
    report = {"scope": SCOPE, "status": "running", "native_batch_key": batch["key"],
        "native_command": source["native_command"], "command": command,
        "candidate_adopted": False, "analysis_workspace_modified": False,
        "whole_records_preserved": True, "mapping_timeout_seconds": TIMEOUT,
        "inputs": expected, "seed_fraction": "0.001",
        "target_fasta_sha256_basis": "recorded_index_source_identity_not_fresh_target_fasta_read",
        "source_target_sha256": manifest["identities"]["target"],
        "accuracy_boundary": "local calibration is not a full-query agreement or biological accuracy guarantee",
        "code": pilot.identities([Path(__file__), Path(pilot.__file__), Path(inspection.__file__)])}
    helper.atomic_json(output / "candidate.json", report)
    try:
        report["mapping"] = pilot.run_child(command, output / "raw.paf", output / "stderr.log", TIMEOUT)
        if report["mapping"]["returncode"]:
            raise ValueError("moderate mapper failed or reached its time limit")
        pilot.verify_completion(output / "stderr.log", 1)
        helper.validate_raw(output / "raw.paf", queries, manifest["target_lengths"])
        contract.validate_paf(output / "raw.paf", require_cigar=True)
        with (output / "raw.paf").open("rb") as raw:
            report["restoration"] = pilot.run_child(
                [sys.executable, manifest["restore"], manifest["name_map"]],
                output / "result.paf", output / "restore.stderr.log", 300, stdin=raw)
        if report["restoration"]["returncode"]:
            raise ValueError("whole candidate name restoration failed")
        helper.validate_raw(output / "result.paf", restored_queries, restored_targets)
        contract.validate_paf(output / "result.paf", require_cigar=True)
        inspection.checked_files(expected)
        inspection.checked_files(report["code"])
        report["outputs"] = pilot.identities([output / name for name in
            ("raw.paf", "result.paf", "stderr.log", "restore.stderr.log")])
        report["status"] = "moderate_candidate_complete_not_adopted"
    except BaseException as error:
        report.update(status="failed_or_interrupted_not_adopted", error=str(error))
        raise
    finally:
        helper.atomic_json(output / "candidate.json", report)
    print(json.dumps({k: report[k] for k in ("scope", "status", "mapping")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "manifest", "source-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    args = parser.parse_args()
    def stop(signum, _frame):
        raise KeyboardInterrupt("signal " + str(signum))
    signal.signal(signal.SIGTERM, stop)
    execute(args.work, args.manifest, args.batch_index, args.source_dir, args.output)


if __name__ == "__main__":
    main()
