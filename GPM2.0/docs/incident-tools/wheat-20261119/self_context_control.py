"""Reuse a completed masked native probe; vary only seed filtering on SAME input.

Also compare masked f=.005 to the existing whole-query f=.005 result in the
same windows to measure context sensitivity separately. No admission, native
checkpoint publication, rerun of native mapping, or analysis-workspace writes.
Run on a compute node: validation hashes the existing source and index.
"""
import argparse
import importlib
import json
from pathlib import Path
import signal
import sys

import full_self_seed_pilot as pilot
import inspect_full_self_pilot as inspection
import masked_self_probe as masked
import self_paf_comparison as comparison


def variant_command(native, fraction):
    if fraction not in ("0.005", "0.002", "0.001") or "-f" in native:
        raise ValueError("expected an unchanged native command and fixed seed variant")
    return native[:-2] + ["-f", fraction] + native[-2:]


def source_contract(report, candidate, manifest, batch, probe_dir):
    if (report.get("status") != "masked_native_vs_complete_candidate_compared_not_adopted"
            or report.get("mapping", {}).get("returncode") != 0
            or report.get("candidate_adopted") is not False
            or report.get("analysis_workspace_modified") is not False):
        raise ValueError("masked native source is not a successful isolated probe")
    inspection.candidate_contract(candidate, manifest, batch)
    entry = batch["entries"][0]
    query = probe_dir / "masked-query.fa"
    if (report.get("query_name") != entry["name"] or report.get("query_length") != entry["length"]
            or report.get("window_bases") != 1_000_000
            or report.get("windows_0based_half_open") != [list(w) for w in masked.fixed_windows(entry["length"], 1_000_000)]
            or report.get("native_command") != candidate["native_command"][:-1] + [str(query)]
            or report.get("source_inputs") != candidate["inputs"]
            or report.get("candidate_outputs") != candidate["outputs"]
            or set(report.get("masked_query", {})) != {str(query)}
            or set(report.get("outputs", {})) != {str(probe_dir / n) for n in ("raw.paf", "stderr.log")}):
        raise ValueError("probe input, windows, command or provenance differs")
    return query


def write_stratum(source, output, stratum):
    """Diagnostic categories, NOT assertions of correctness or admission rules."""
    if stratum not in ("tp_P", "long_high_identity"):
        raise ValueError("unknown diagnostic stratum")
    with source.open() as inp, output.open("x") as out:
        for line in inp:
            fields = line.rstrip("\n").split("\t")
            selected = ("tp:A:P" in fields[12:] if stratum == "tp_P" else
                        int(fields[10]) >= 10_000 and int(fields[9]) / int(fields[10]) >= .95)
            if selected:
                out.write(line)


def comparisons(left_path, right_path, windows, directory):
    directory.mkdir()
    reports = {}
    for stratum in ("all_hits", "tp_P", "long_high_identity"):
        left, right = left_path, right_path
        if stratum != "all_hits":
            left, right = directory / (stratum + "-left.paf"), directory / (stratum + "-right.paf")
            write_stratum(left_path, left, stratum)
            write_stratum(right_path, right, stratum)
        a = comparison.read_evidence(left, step=1000, query_windows=windows)
        b = comparison.read_evidence(right, step=1000, query_windows=windows)
        reports[stratum] = comparison.compare_evidence(a, b, step=1000)
        reports[stratum]["diagnostic_stratum"] = stratum
        reports[stratum]["primary_or_mapq_filter_applied"] = stratum == "tp_P"
        reports[stratum]["stratum_filter_applied"] = stratum != "all_hits"
        reports[stratum]["filters"] = ({"tp": "P"} if stratum == "tp_P" else
            {"minimum_block_length": 10000, "minimum_matching_bases_over_block_length": .95}
            if stratum == "long_high_identity" else {})
    return reports


def execute(work, manifest_path, batch_index, candidate_dir, probe_dir, output, fraction):
    work = work.resolve(strict=True)
    pilot.require_isolated(work, output)
    manifest_path = manifest_path.resolve(strict=True)
    manifest_path.relative_to(work)
    candidate_dir, probe_dir = candidate_dir.resolve(strict=True), probe_dir.resolve(strict=True)
    for source in (candidate_dir, probe_dir):
        if source == work or work in source.parents or source == output.resolve() or source in output.resolve().parents or output.resolve() in source.parents:
            raise ValueError("control outputs and immutable sources must be separate")
    manifest = json.loads(manifest_path.read_text())
    if not 0 <= batch_index < len(manifest["batches"]):
        raise ValueError("invalid batch index")
    batch = manifest["batches"][batch_index]
    candidate = json.loads((candidate_dir / "pilot.json").read_text())
    probe = json.loads((probe_dir / "probe.json").read_text())
    source_contract(probe, candidate, manifest, batch, probe_dir)
    if set(candidate["outputs"]) != {str(candidate_dir / n) for n in inspection.OUTPUT_NAMES | {"restore.stderr.log"}}:
        raise ValueError("candidate output paths differ")
    if str(manifest_path) not in candidate["inputs"]:
        raise ValueError("candidate does not bind requested manifest")
    expected = {}
    for group in (probe["source_inputs"], probe["candidate_outputs"], probe["masked_query"], probe["outputs"]):
        for path, value in group.items():
            if path in expected and expected[path] != value:
                raise ValueError("conflicting source identities")
            expected[path] = value
    reports = pilot.identities([probe_dir / "probe.json", candidate_dir / "pilot.json"])
    expected.update(reports)
    inspection.checked_files(expected)
    helper_path = work / ".prepare_lib/tools/self_alignment_batches.py"
    if str(helper_path) not in expected:
        raise ValueError("source helper not bound")
    sys.path.insert(0, str(helper_path.parent))
    helper = importlib.import_module("self_alignment_batches")
    if Path(helper.__file__).resolve() != helper_path.resolve():
        raise ValueError("wrong source validation helper")
    entry = batch["entries"][0]
    queries = {entry["name"]: entry["length"]}
    windows = {entry["name"]: probe["windows_0based_half_open"]}
    for directory in (probe_dir, candidate_dir):
        pilot.verify_completion(directory / "stderr.log", 1)
        helper.validate_raw(directory / "raw.paf", queries, manifest["target_lengths"])
    command = variant_command(probe["native_command"], fraction)
    output.mkdir()
    report = {"scope": "same_masked_input_seed_effect_and_same_filter_context_effect",
        "status": "running", "candidate_adopted": False, "analysis_workspace_modified": False,
        "seed_fraction": fraction, "command": command, "inputs": expected,
        "windows": windows, "mapping_timeout_seconds": 300,
        "accuracy_boundary": "diagnostics only; neither primary labels nor long high-identity hits prove correctness",
        "code": pilot.identities([Path(__file__), Path(pilot.__file__), Path(inspection.__file__),
                                  Path(masked.__file__), Path(comparison.__file__)])}
    helper.atomic_json(output / "control.json", report)
    try:
        report["mapping"] = pilot.run_child(command, output / "raw.paf", output / "stderr.log", 300)
        if report["mapping"]["returncode"]:
            raise ValueError("bounded control mapper failed or timed out")
        pilot.verify_completion(output / "stderr.log", 1)
        helper.validate_raw(output / "raw.paf", queries, manifest["target_lengths"])
        report["same_input_seed_effect"] = comparisons(probe_dir / "raw.paf", output / "raw.paf", windows, output / "seed-effect")
        if fraction == "0.005":
            report["same_filter_context_effect"] = comparisons(output / "raw.paf", candidate_dir / "raw.paf", windows, output / "context-effect")
        inspection.checked_files(expected)
        inspection.checked_files(report["code"])
        report["outputs"] = pilot.identities(sorted(output.rglob("*.paf")) + [output / "stderr.log"])
        report["status"] = "compared_not_adopted"
    except BaseException as error:
        report.update(status="failed_or_interrupted_not_adopted", error=str(error))
        raise
    finally:
        helper.atomic_json(output / "control.json", report)
    print(json.dumps({k: report[k] for k in ("status", "seed_fraction", "mapping")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("work", "manifest", "candidate-dir", "probe-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--fraction", choices=("0.005", "0.002", "0.001"), required=True)
    args = parser.parse_args()
    def stop(signum, _frame):
        raise KeyboardInterrupt("signal " + str(signum))
    signal.signal(signal.SIGTERM, stop)
    execute(args.work, args.manifest, args.batch_index, args.candidate_dir, args.probe_dir, args.output, args.fraction)


if __name__ == "__main__":
    main()
