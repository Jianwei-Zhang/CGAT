"""Isolated 3D calibration and real ordinary-subset comparison; never adopt.

Run through Donau with the frozen x86 runtime. No full long-query remapping:
calibration uses only bounded windows; the native full-result is read-only.
"""
import dataclasses
import json
from pathlib import Path
import shutil

from long_query_cross_router import Router, RoutingError
from seed_filter_pilot import ROOT, WORK

HERE = Path(__file__).resolve().parent
COMMAND = "runs/chr_3D/JM19_flye_ABD_vs_JM19_hifiasm/command.sh"


def main():
    router = Router(WORK / "runs/chr_3D/datasets/JM19_flye_ABD.fa",
                    WORK / "runs/chr_3D/datasets/JM19_hifiasm.fa",
                    shutil.which("minimap2"), HERE / "calibration-cache",
                    WORK / ".prepare_lib/tools", threads=3)
    contract = router.contract
    checkpoint = ROOT / "memory-resume-20261118/cross-leaf-checkpoints" / (contract.fingerprint(COMMAND) + ".json")
    marker = json.loads(checkpoint.read_text())
    if marker["status"] != "success" or marker["command"] != COMMAND:
        raise RoutingError("native full-3D leaf not complete")
    if marker["inputs"]["tool"]["sha256"] != router.tool_hash:
        raise RoutingError("native tool identity differs")
    for row in marker["inputs"]["files"] + marker["outputs"]:
        if contract.file_identity(WORK / row["path"], relative_to=WORK) != row:
            raise RoutingError("native checkpoint content changed")
    baseline = (WORK / COMMAND).parent / "result.paf"
    router.validate_output(baseline, {r.name: r.length for r in router.query.records})
    report = {"scope": "3D calibration and ordinary-subset validation only",
              "candidate_adopted": False, "analysis_workspace_modified": False,
              "policy": dataclasses.asdict(router.policy), "tool_sha256": router.tool_hash,
              "dependencies": router.dependency_hashes, "native_checkpoint": str(checkpoint),
              "query_sha256": router.query.source_sha256,
              "target_sha256": router.target.source_sha256, "decisions": []}
    report_path = HERE / "real-calibration.json"
    if report_path.exists():
        raise RoutingError("preserve existing calibration report; use a fresh validation directory")
    with router.signals():
        router.stable(check_code=True)
        # Keep names, full sequence and order. Cap this verification at 3 Mb;
        # it checks regrouping on real inputs, not whole-dataset equivalence.
        names = [r.name for r in router.query.records if 100_000 <= r.length <= 1_000_000][:3]
        if not names:
            raise RoutingError("no suitably bounded ordinary-record fixture")
        query_path = router.materialize(names)
        lengths = {n: router.records[n].length for n in names}
        group = router.mapping(query_path, lengths, None, phase="whole_records", timeout=300)
        subset = HERE / "native-ordinary-subset.paf"
        with baseline.open("rb") as source, subset.open("xb") as output:
            for line in source:
                if line.split(b"\t", 1)[0].decode("ascii") in lengths:
                    output.write(line)
        identical = subset.read_bytes() == Path(group["path"]).read_bytes()
        report["ordinary_subset"] = {"names": names, "lengths": lengths,
             "byte_identical_to_completed_native": identical,
             "native_subset": contract.file_identity(subset), "mapping": group}
        contract.atomic_write_json(report_path, report)
        if not identical:
            raise RoutingError("ordinary record regrouping differs on real 3D fixture; do not adopt")
        target_size = sum(router.target_lengths.values())
        if not router.policy.minimum_target_bases <= target_size <= router.policy.maximum_target_bases:
            raise RoutingError("real target outside internal calibration domain")
        for record in router.query.records:
            if record.length >= router.policy.long_bases:
                decision = router.calibrate(record)
                report["decisions"].append(decision)
                contract.atomic_write_json(report_path, report)
                print("REAL_CALIBRATION", json.dumps(decision), flush=True)
        router.stable(check_code=True)
        report["status"] = "calibration_complete_not_adopted"
        contract.atomic_write_json(report_path, report)
        print("REAL_CALIBRATION_COMPLETE", json.dumps({"ordinary_subset_identical": identical,
              "long_records": len(report["decisions"])}), flush=True)


if __name__ == "__main__":
    main()
