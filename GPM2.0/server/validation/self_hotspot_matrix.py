#!/usr/bin/env python3
"""Short sensitivity matrix on calibrated real windows, not whole-genome timing."""
import argparse
import json
from pathlib import Path
import shutil
import signal
import time

from self_hotspot_fixture import bounded, comparison
from self_query_batches import FLAGS, atomic_json, sha, records, validate_raw
from self_alignment_experiments import paf_summary

PROFILES = {
    "current-n100": FLAGS,
    "freq100": [*FLAGS, "-U", "50,100"],
    "freq500": [*FLAGS, "-U", "50,500"],
    "freq1000": [*FLAGS, "-U", "50,1000"],
    "rmq100": [*FLAGS, "--rmq-inner", "100"],
    "rmq0": [*FLAGS, "--rmq-inner", "0"],
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fixture", required=True, type=Path)
    p.add_argument("--root", required=True, type=Path)
    a = p.parse_args()
    a.root = a.root.resolve()
    a.root.mkdir(parents=True, exist_ok=False)
    r = {"status": "RUNNING", "fixture": str(a.fixture), "profiles": PROFILES, "trials": [],
         "boundary": "Two 250kb query windows, complete original target index, fixed same tool/thread count and shared node. Two rounds with reversed order. Loading overhead included. Coverage is per-pair/strand strong query coverage against current-n100, not true biological precision; no acceptance or whole-workflow speed claim."}
    start = time.monotonic()
    def save():
        r["elapsed_seconds"] = time.monotonic() - start
        atomic_json(a.root / "report.json", r)
    def interrupt(signum, frame):
        raise InterruptedError(f"Received signal {signum}")
    signal.signal(signal.SIGTERM, interrupt)
    save()
    try:
        fixture = json.loads((a.fixture / "report.json").read_text())
        if fixture["status"] not in ("CALIBRATED", "NO_SLOW_WINDOW_FOUND"):
            raise ValueError("Calibration has not completed")
        mm = shutil.which("minimap2")
        if not mm or sha(mm) != fixture["tool"]["sha256"]:
            raise ValueError("Tool identity changed")
        index = a.fixture / "target.mmi"
        if sha(index) != fixture["index"]["sha256"]:
            raise ValueError("Index identity changed")
        target = Path(fixture["source"]["directory"]) / "self_target.fa"
        if sha(target) != fixture["source"]["target_sha256"]:
            raise ValueError("Target identity changed")
        target_names = {h[1:].split()[0].decode(): sum(len(s.strip()) for s in b.splitlines()) for h, b in records(target)}
        r["tool"] = fixture["tool"]; r["index_sha256"] = fixture["index"]["sha256"]
        for label in ("250000-start", "250000-middle"):
            case = next(c for c in fixture["cases"] if c["name"] == label)
            query = a.fixture / label / "query.fa"
            if sha(query) != case["query_sha256"]:
                raise ValueError("Query identity changed")
            entries = [{"name": case["original_query"], "length": case["interval_0based_half_open"][1] - case["interval_0based_half_open"][0]}]
            for repeat in range(2):
                row = {"case": label, "repeat": repeat, "query_sha256": case["query_sha256"], "profiles": {}, "comparisons": {}}
                r["trials"].append(row); save()
                order = list(PROFILES)
                if repeat:
                    order.reverse()
                row["profile_order"] = order
                for profile in order:
                    directory = a.root / f"{label}-r{repeat}-{profile}"
                    result = bounded([mm, *PROFILES[profile], "-t", "1", str(index), str(query)], directory, 15)
                    if result["status"] == "COMPLETED":
                        if (directory / "stderr.log").read_text().count("distinct minimizers:") != 1:
                            raise ValueError("Index part count changed")
                        validate_raw(directory / "raw.paf", entries, target_names)
                        result["paf"] = paf_summary(directory / "raw.paf")
                    row["profiles"][profile] = result; save()
                base = row["profiles"]["current-n100"]
                for profile, result in row["profiles"].items():
                    if "paf" in base and "paf" in result:
                        row["comparisons"][profile] = comparison(base["paf"], result["paf"])
                        row["comparisons"][profile]["wall_ratio"] = base["seconds"] / result["seconds"]
                save()
        if any(v["status"] == "FAILED" for row in r["trials"] for v in row["profiles"].values()):
            raise RuntimeError("A profile failed")
        r["status"] = "MEASURED_NOT_APPROVED"; save()
        print(r["status"], r["elapsed_seconds"], flush=True)
    except BaseException as error:
        r["status"] = "FAILED"; r["error"] = repr(error); save()
        raise


if __name__ == "__main__":
    main()
