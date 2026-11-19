"""Bounded native self probe against an already completed full-query candidate.

Retain the original query name and FULL length; mask outside three fixed windows
with N. Retain the original index and every native self flag. Compare all hit
placements inside these windows with the complete candidate, not a candidate
made from the masked input. This is LOCAL calibration only: masking can change
chaining context. Never adopt a candidate or write native batch checkpoints.
"""
import argparse
import importlib
import json
from pathlib import Path
import signal
import sys

import full_self_seed_pilot as pilot
import inspect_full_self_pilot as inspection
import self_paf_comparison as comparison

LIMITS = {"minimum_baseline_placements": 1000, "maximum_missing_fraction": 0.002,
          "maximum_extra_fraction": 0.002, "maximum_pair_query_coverage_loss": 0.001,
          "significant_pair_bases": 10000, "position_tolerance_bp": 100}


def fixed_windows(length, width=5_000_000):
    if length < 6 * width or width < 1:
        raise ValueError("query too short for three disjoint calibration windows")
    middle = length // 2 - width // 2
    return [(0, width), (middle, middle + width), (length - width, length)]


def write_masked_query(source, output, name, length, windows):
    if output.exists():
        raise ValueError("masked query already exists")
    if (comparison.union(windows) != list(windows)
            or any(type(lo) is not int or type(hi) is not int or not 0 <= lo < hi <= length
                   for lo, hi in windows)):
        raise ValueError("invalid or overlapping probe windows")
    with source.open("rb") as stream:
        header = stream.readline()
        if not header.startswith(b">") or header[1:].split()[0].decode() != name:
            raise ValueError("source query name changed")
        sequence = bytearray()
        for line in stream:
            if line.startswith(b">"):
                raise ValueError("probe requires exactly one original query record")
            sequence.extend(line.strip())
    if len(sequence) != length:
        raise ValueError("source query length changed")
    masked = bytearray(b"N") * length
    for lo, hi in windows:
        masked[lo:hi] = sequence[lo:hi]
    with output.open("xb") as stream:
        stream.write(header.rstrip(b"\r\n") + b"\n")
        stream.write(masked); stream.write(b"\n")


def window_quality(report):
    baseline = report["baseline"]["sampled_distinct_placements"]
    positions = report["position_support"][str(LIMITS["position_tolerance_bp"])]
    coverage = sum(row["query_aligned_coverage"]["baseline"] for row in report["pairs"])
    lost = sum(row["query_aligned_coverage"]["missing"] for row in report["pairs"])
    reasons = []
    if baseline < LIMITS["minimum_baseline_placements"]: reasons.append("insufficient_baseline_placements")
    if baseline and positions["missing_baseline_placements"] / baseline > LIMITS["maximum_missing_fraction"]:
        reasons.append("missing_positions")
    if baseline and positions["extra_candidate_placements"] / baseline > LIMITS["maximum_extra_fraction"]:
        reasons.append("extra_positions")
    if not coverage or lost / coverage > LIMITS["maximum_pair_query_coverage_loss"]:
        reasons.append("pair_query_coverage_loss")
    if any(not row["candidate_present"] and row["query_aligned_coverage"]["baseline"] >= LIMITS["significant_pair_bases"]
           for row in report["pairs"]):
        reasons.append("significant_pair_missing")
    return {"limits": LIMITS, "passes_proposed_window_limits": not reasons, "reasons": reasons,
            "baseline_pair_query_aligned_bases": coverage, "missing_pair_query_aligned_bases": lost,
            "whole_query_agreement_guaranteed": False, "candidate_adopted": False}


def execute(work, manifest_path, batch_index, candidate_dir, output, *, window_bases=5_000_000):
    work = work.resolve(strict=True)
    pilot.require_isolated(work, output)
    manifest_path.resolve(strict=True).relative_to(work)
    manifest = json.loads(manifest_path.read_text())
    if not 0 <= batch_index < len(manifest["batches"]):
        raise ValueError("invalid self batch index")
    batch = manifest["batches"][batch_index]
    candidate_dir = candidate_dir.resolve(strict=True)
    if work == candidate_dir or work in candidate_dir.parents:
        raise ValueError("candidate must be outside the analysis workspace")
    source_report = candidate_dir / "pilot.json"; report_bytes = source_report.read_bytes()
    source = json.loads(report_bytes)
    inspection.candidate_contract(source, manifest, batch)
    if set(source["outputs"]) != {str(candidate_dir / name) for name in inspection.OUTPUT_NAMES | {"restore.stderr.log"}}:
        raise ValueError("candidate output inventory belongs to another run")
    inputs = inspection.checked_files(source["inputs"])
    outputs = inspection.checked_files(source["outputs"])
    if str(manifest_path) not in inputs or str(Path(batch["query"])) not in inputs:
        raise ValueError("candidate does not bind the requested manifest/query")
    entry = batch["entries"][0]
    if entry["length"] < 100_000_000:
        raise ValueError("this pilot is restricted to >=100 Mb whole self queries")
    helper_path = work / ".prepare_lib/tools/self_alignment_batches.py"
    if str(helper_path) not in inputs:
        raise ValueError("candidate did not bind the frozen self helper")
    sys.path.insert(0, str(helper_path.parent))
    helper = importlib.import_module("self_alignment_batches")
    if Path(helper.__file__).resolve() != helper_path.resolve():
        raise ValueError("wrong self helper imported")
    if window_bases not in (1_000_000, 5_000_000):
        raise ValueError("pilot supports only fixed 1 Mb or 5 Mb windows")
    windows = fixed_windows(entry["length"], window_bases)
    output.mkdir()
    masked = output / "masked-query.fa"
    write_masked_query(Path(batch["query"]), masked, entry["name"], entry["length"], windows)
    masked_identity = pilot.identities([masked])
    command = source["native_command"][:-1] + [str(masked)]
    report = {"scope": "masked_native_windows_vs_completed_full_self_candidate",
        "full_length_and_name_preserved": True, "windows_0based_half_open": windows,
        "query_name": entry["name"], "query_length": entry["length"],
        "observed_source_bases": sum(hi-lo for lo,hi in windows), "window_bases": window_bases,
        "native_command": command,
        "native_probe_timeout_seconds": 300, "candidate_adopted": False,
        "analysis_workspace_modified": False, "source_inputs": inputs, "candidate_outputs": outputs,
        "masked_query": masked_identity, "proposed_limits": LIMITS, "status": "running",
        "accuracy_boundary": "masking changes chaining context; local agreement is not a full-query guarantee",
        "code_sha256": {"probe": pilot.digest(Path(__file__)),
                        "comparison": pilot.digest(Path(comparison.__file__)),
                        "inspection": pilot.digest(Path(inspection.__file__)),
                        "candidate_driver": pilot.digest(Path(pilot.__file__))}}
    helper.atomic_json(output / "probe.json", report)
    try:
        report["mapping"] = pilot.run_child(command, output / "raw.paf", output / "stderr.log", 300)
        if report["mapping"]["returncode"]:
            raise ValueError("bounded native probe failed or timed out; do not adopt candidate")
        pilot.verify_completion(output / "stderr.log", 1)
        helper.validate_raw(output / "raw.paf", {entry["name"]: entry["length"]}, manifest["target_lengths"])
        helper.validate_raw(candidate_dir / "raw.paf", {entry["name"]: entry["length"]}, manifest["target_lengths"])
        selected = {entry["name"]: windows}
        left = comparison.read_evidence(output / "raw.paf", step=1000, query_windows=selected)
        right = comparison.read_evidence(candidate_dir / "raw.paf", step=1000, query_windows=selected)
        report["comparison_1kb"] = comparison.compare_evidence(left, right, step=1000)
        report["quality"] = window_quality(report["comparison_1kb"])
        inspection.checked_files(inputs); inspection.checked_files(outputs); inspection.checked_files(masked_identity)
        if source_report.read_bytes() != report_bytes:
            raise ValueError("candidate report changed during calibration")
        report["outputs"] = pilot.identities([output / name for name in ("raw.paf", "stderr.log")])
        report["status"] = "masked_native_vs_complete_candidate_compared_not_adopted"
    except BaseException as error:
        report.update(status="probe_failed_or_interrupted_not_adopted", error=str(error))
        raise
    finally:
        helper.atomic_json(output / "probe.json", report)
    print(json.dumps({k: report[k] for k in ("scope", "status", "mapping", "quality")}, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "manifest", "candidate-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--window-bases", type=int, choices=(1_000_000, 5_000_000), default=5_000_000)
    args = parser.parse_args()
    def stop(signum, _frame): raise KeyboardInterrupt("signal " + str(signum))
    signal.signal(signal.SIGTERM, stop)
    execute(args.work, args.manifest, args.batch_index, args.candidate_dir, args.output,
            window_bases=args.window_bases)


if __name__ == "__main__":
    main()
