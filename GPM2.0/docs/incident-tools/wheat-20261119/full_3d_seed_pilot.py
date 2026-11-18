"""One full-context 3D candidate, isolated; reuse the in-flight native baseline.

The candidate is never automatically adopted into the production workspace.
Use --compare-only after a verified native leaf checkpoint exists. Run all
full-content validation and alignment through the scheduler, not a login node.
"""
import json
import shutil
import sys
from pathlib import Path
import seed_filter_pilot as pilot
from paf_anchor_comparison import compare

ROOT, WORK = pilot.ROOT, pilot.WORK
HERE = ROOT / "seed-filter-full-3D-pilot-20261119"
COMMAND = "runs/chr_3D/JM19_flye_ABD_vs_JM19_hifiasm/command.sh"


def main():
    sys.path.insert(0, str(WORK / ".prepare_lib/tools"))
    from run_orchestration import file_identity, fingerprint, sha256_file, validate_paf
    expected = {row["path"]: row for row in json.loads(
        (WORK / ".run_all/checkpoints/assign.80a737d469c64759.json").read_text())["outputs"]}
    inputs = [COMMAND, "runs/chr_3D/datasets/JM19_flye_ABD.fa",
              "runs/chr_3D/datasets/JM19_hifiasm.fa"]
    identities = [file_identity(WORK / name, relative_to=WORK) for name in inputs]
    assert identities == [expected[name] for name in inputs]
    tool = Path(shutil.which("minimap2")).resolve()
    proof = json.loads((ROOT / "memory-resume-20261118/reference.before.json").read_text())
    tool_hash = next(t["sha256"] for t in proof["input_payload"]["tools"] if t["command"] == "minimap2")
    assert sha256_file(tool) == tool_hash
    report_path = HERE / "result.json"
    candidate = HERE / "f0005/result.paf"
    if sys.argv[1:] == ["--compare-only"]:
        report = json.loads(report_path.read_text())
        assert report["mapping"]["returncode"] == 0
        assert report["inputs"] == identities and report["tool_sha256"] == tool_hash
        assert report["outputs"] == [file_identity(HERE / row["path"], relative_to=HERE)
                                     for row in report["outputs"]]
    else:
        assert not sys.argv[1:] and not report_path.exists()
        pilot.TIMEOUT = 1800
        command = [str(tool), "-c", "-x", "asm10", "-t", "3", "-f", "0.005",
                   "-o", str(candidate), str(WORK / inputs[1]), str(WORK / inputs[2])]
        mapping = pilot.run(command, candidate.parent)
        report = {"scope": "full 3D candidate only; not full-wheat completion",
                  "inputs": identities, "tool_sha256": tool_hash, "command": command,
                  "mapping": mapping, "native_baseline_job": 42646893,
                  "analysis_workspace_modified": False, "candidate_adopted": False}
        if mapping["returncode"] != 0:
            report["status"] = "candidate_failed_or_timed_out"
            report_path.write_text(json.dumps(report, indent=2) + "\n")
            raise SystemExit(mapping["returncode"] if mapping["returncode"] > 0 else 1)
        validate_paf(candidate, require_cigar=True)
        assert identities == [file_identity(WORK / name, relative_to=WORK) for name in inputs]
        report["metrics"], _ = pilot.measure(candidate)
        report["outputs"] = [file_identity(candidate.parent / name, relative_to=HERE)
                             for name in ("result.paf", "stdout.log", "stderr.log")]
        report["status"] = "candidate_complete_native_comparison_pending"
    marker = ROOT / "memory-resume-20261118/cross-leaf-checkpoints" / (fingerprint(COMMAND) + ".json")
    if marker.is_file():
        record = json.loads(marker.read_text())
        assert record["status"] == "success" and record["command"] == COMMAND
        assert record["inputs"]["files"] == identities
        assert record["inputs"]["tool"]["sha256"] == tool_hash
        assert record["outputs"] == [file_identity(WORK / row["path"], relative_to=WORK)
                                     for row in record["outputs"]]
        baseline = (WORK / COMMAND).parent / "result.paf"
        validate_paf(baseline, require_cigar=True)
        report["native_metrics"], left = pilot.measure(baseline)
        _, right = pilot.measure(candidate)
        report["same_primary_target_strand_supported_bases"] = pilot.shared_primary_support(left, right)
        report["cigar_anchor_comparison"] = compare(baseline, candidate)
        report["native_leaf_checkpoint"] = str(marker)
        report["native_leaf_origin"] = record["origin"]
        report["status"] = "candidate_and_native_compared_not_adopted"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
