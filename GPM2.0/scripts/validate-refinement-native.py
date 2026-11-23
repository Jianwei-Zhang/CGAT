#!/usr/bin/env python3
"""Run the checked-in synthetic case through the real public Server entrypoints.

Run inside the installed cgat-server environment. Creates a new evidence root;
never installs software, edits a checkpoint, or accepts external data inputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parent
SERVER = SCRIPTS.parent / "server"
TOOLS = ("degap", "tgsgapcloser", "quartet", "lrgapcloser")
TOOL_DIR = {tool: f"{i:02d}_{tool}" for i, tool in enumerate(TOOLS, 1)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load(path):
    return json.loads(path.read_text())


def fasta_sequences(path):
    # A publication may rewrap the same chromosome; a file hash difference
    # does not establish a biological sequence change.
    sequences = {}
    name = None
    for row in path.read_bytes().splitlines():
        if row.startswith(b">"):
            name = row[1:].split()[0]
            require(name not in sequences, f"duplicate FASTA chromosome: {path}")
            sequences[name] = []
        else:
            require(name is not None and row, f"invalid FASTA: {path}")
            sequences[name].append(row)
    require(sequences, f"empty FASTA: {path}")
    return {name: b"".join(rows) for name, rows in sequences.items()}


def snapshot(root, paths):
    return {p.relative_to(root).as_posix(): {"sha256": digest(p), "mtime_ns": p.stat().st_mtime_ns}
            for p in sorted(paths)}


def baseline_snapshot(workspace):
    paths = [*workspace.glob("02_alignments/**/result.paf"), *workspace.glob("03_lgz/*/q[0-3].fa")]
    require(any(p.suffix == ".paf" for p in paths), "missing real reference alignment")
    require({p.name for p in paths if p.suffix == ".fa"} == {"q0.fa", "q1.fa", "q2.fa", "q3.fa"},
            "incomplete LGZ stage assemblies")
    return snapshot(workspace, paths)


def verify_case(workspace, expected, reads, *, previously_finished=False):
    # Validate what the real Server published, without importing the path writer.
    from refinement_commit import current_publication
    from refinement_delivery import validate_delivery

    baseline = workspace / "05_final/00_lgz"
    require(load(baseline / "provenance.json")["refinement_applied"] is False, "LGZ no longer labelled baseline")
    baseline_sha = digest(baseline / "assembly.fa")
    baseline_sequences = fasta_sequences(baseline / "assembly.fa")
    require((workspace / "06_report/report.html").is_file(), "missing batch overview")
    found = {p.name for p in (workspace / "05_final").iterdir()}
    require(found == {"00_lgz"} | {TOOL_DIR[t] for t in expected}, "unexpected tool final directories")
    results = {}
    for tool, keys in expected.items():
        group = TOOL_DIR[tool]
        final = workspace / "05_final" / group
        report = workspace / "06_report/02_refinement" / group
        delivery = workspace / "07_delivery" / group
        provenance = load(final / "provenance.json")
        summary = load(report / "summary.json")
        publication = current_publication(workspace, tool, verify=True)
        require(publication is not None, f"{tool}: no committed tool publication")
        require(provenance["tool"] == tool == summary["tool"], f"{tool}: mismatched result/report")
        require(provenance["run_id"] == summary["run_id"], f"{tool}: report belongs to another run")
        execution = provenance["execution"]
        if not previously_finished:
            require(execution["native_executed"] and not execution["native_reused"],
                    f"{tool}: required fresh native invocation did not execute")
        jobs = list(workspace.glob(f"04_refinement/{group}/02_jobs/*/native_complete.json"))
        require(len(jobs) == 1, f"{tool}: expected one sealed native producer, found {len(jobs)}")
        producer = load(jobs[0])
        require(producer["status"] == "completed" and producer["tool"] == tool,
                f"{tool}: missing completed native producer")
        require(producer["execution"]["command"] and producer["execution"]["ended_at"],
                f"{tool}: native execution receipt is incomplete")
        require(producer["binding"]["reads"] == [reads[key] for key in keys],
                f"{tool}: wrong reads were selected")
        require(baseline_sha == execution["baseline_sha256"], f"{tool}: execution is not tied to LGZ baseline")
        accepted = provenance["accepted_edit_count"]
        require(type(accepted) is int and accepted >= 0, f"{tool}: invalid accepted edit count")
        different = fasta_sequences(final / "assembly.fa") != baseline_sequences
        require((accepted > 0) == different, f"{tool}: accepted edits and chromosome sequence disagree")
        status = "completed" if accepted else "completed_zero_accepted"
        require(provenance["status"] == status == summary["outcome"] and summary["accepted_edit_count"] == accepted,
                f"{tool}: acceptance outcome differs in report")
        # This opens the actual Full/Light archives. The validator reconstructs
        # sources from detached Full contents and checks Light availability.
        validation = validate_delivery(delivery, final)
        require(validation["modes"] == ["full", "light"], f"{tool}: both archive modes were not validated")
        results[tool] = {"status": provenance["status"], "accepted_edit_count": accepted,
                         "chromosome_sequence_changed": different, "final_sha256": digest(final / "assembly.fa"),
                         "native_producer": jobs[0].relative_to(workspace).as_posix(),
                         "native_receipt_sha256": digest(jobs[0]), "native_command": producer["execution"]["command"],
                         "reads": producer["binding"]["reads"], "delivery": validation}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new output directory; parent must exist")
    parser.add_argument("--arch", choices=("x86_64", "aarch64"), required=True)
    parser.add_argument("--manager", choices=("mamba", "micromamba", "conda"), required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    out = args.out.resolve()
    require(platform.system() == "Linux" and platform.machine() == args.arch,
            f"this run requires Linux {args.arch}; found {platform.system()} {platform.machine()}")
    require(re.fullmatch(r"/[a-zA-Z0-9_./-]+", str(out)), "native drivers require a shell-safe output path")
    require(not out.is_relative_to(SERVER.parent.parent), "validation output must be outside the source checkout")
    require(args.threads > 0, "threads must be positive")
    prefix = os.environ.get("CONDA_PREFIX")
    require(prefix and Path(prefix).name == "cgat-server" and Path(sys.prefix).resolve() == Path(prefix).resolve(),
            "use the private managed cgat-server environment (not system Python)")
    sys.path.insert(0, str(SERVER / "tools"))
    revision = subprocess.check_output(["git", "-C", str(SERVER), "rev-parse", "HEAD"], text=True).strip()
    require(not subprocess.check_output(["git", "-C", str(SERVER), "status", "--porcelain", "--", "."], text=True),
            "validate a clean Server source tree")
    out.mkdir()
    receipt = {"schema": "cgat.refinement-native-validation", "schema_version": 1,
               "status": "running", "reported_machine": platform.machine(), "is_scientific_benchmark": False,
               "git_revision": revision, "harness_sha256": digest(Path(__file__)),
               "runtime_lock_sha256": digest(SERVER / "contracts/refinement-tools.lock.json"), "steps": {}}
    receipt_path = out / "validation.json"

    def save():
        temp = out / "validation.json.tmp"
        temp.write_text(json.dumps(receipt, indent=2) + "\n")
        temp.replace(receipt_path)

    def step(label, *command):
        command = list(map(str, command))
        log = out / (label + ".log")
        record = receipt["steps"][label] = {"command": command, "log": log.name,
                                             "started_at": datetime.now(timezone.utc).isoformat()}
        with log.open("xb") as output:
            process = subprocess.Popen(command, cwd=out, stdout=output, stderr=subprocess.STDOUT)
            record["pid"] = process.pid
            save()
            print(f"{label}: PID {process.pid}; {log}", flush=True)
            record["exit_code"] = process.wait()
        record["log_sha256"] = digest(log)
        save()
        require(record["exit_code"] == 0, f"{label} exited {record['exit_code']}; see {log}")

    try:
        # Separate public environment check and validation of the prefix used below.
        step("install-check", "bash", SERVER / "install.sh", "--check", "--manager", args.manager)
        step("active-runtime", sys.executable, "-B", SERVER / "tools/refinement_tools.py", "--check")
        runtime = load(out / "active-runtime.log")
        require(runtime["platform"] == {"x86_64": "linux-64", "aarch64": "linux-aarch64"}[args.arch]
                and set(runtime["tools"]) == set(TOOLS), "wrong architecture or incomplete runtime")
        receipt["environment"] = runtime
        case = out / "case"
        step("generate", sys.executable, "-B", SCRIPTS / "make-refinement-validation-case.py", "--out", case)
        receipt["input_manifest_sha256"] = digest(case / "case.json")
        names = {"hifi_a": "hifi", "hifi_b": "hifi", "ont": "ont"}
        reads = {}
        for key, technology in names.items():
            path = case / key / "reads.fastq.gz"
            reads[key] = {"path": str(path), "technology": technology, "sha256": digest(path)}
        public = ("bash", SERVER / "run.sh", "--ref", case / "reference.fa", "--ds", case / "assembly.fa",
                  "--threads", args.threads)
        hifi = ("--hifi", reads["hifi_a"]["path"], reads["hifi_b"]["path"])
        ont = ("--ont", reads["ont"]["path"])
        mixed = {t: list(names if t in {"degap", "quartet"} else ("hifi_a", "hifi_b")) for t in TOOLS}

        default = out / "default"
        step("fresh-default", *public, "--out", default, *hifi, *ont)
        receipt["default"] = verify_case(default, {"degap": list(names)}, reads)
        workspace = out / "append"
        step("lgz-only", *public, "--out", workspace)
        verify_case(workspace, {}, reads)
        frozen = baseline_snapshot(workspace)
        step("append-four", "bash", workspace / "run_all.sh", *hifi, *ont, "--gapfill-tools", ",".join(TOOLS))
        receipt["four_tools"] = verify_case(workspace, mixed, reads)
        require(baseline_snapshot(workspace) == frozen, "append changed native LGZ or reference files")
        step("unchanged-repeat", "bash", workspace / "run_all.sh")
        repeat = verify_case(workspace, mixed, reads, previously_finished=True)
        require(baseline_snapshot(workspace) == frozen, "unchanged repeat changed LGZ or reference files")
        for t in TOOLS:
            require(repeat[t]["native_receipt_sha256"] == receipt["four_tools"][t]["native_receipt_sha256"]
                    and repeat[t]["final_sha256"] == receipt["four_tools"][t]["final_sha256"],
                    f"{t}: unchanged run changed sealed producer or final assembly")
        receipt["preserved_lgz_and_reference"] = frozen
        control = out / "ont-only"
        step("fresh-ont-tgs", *public, "--out", control, *ont, "--gapfill-tools", "tgsgapcloser")
        receipt["ont_tgs"] = verify_case(control, {"tgsgapcloser": ["ont"]}, reads)
        tgs = receipt["ont_tgs"]["tgsgapcloser"]
        producer = load(control / tgs["native_producer"])
        substeps = load(control / producer["execution"]["native_substeps"]["summary"])
        racon = [row for row in substeps["units"] if row["unit"]["program"] == "racon"]
        require(racon and all(not row["reused"] and digest(control / row["receipt"]) == row["receipt_sha256"]
                              for row in racon), "ONT TGS did not compute the pinned Racon substeps")
        tgs["racon_substeps"] = len(racon)
        require(any(row["accepted_edit_count"] > 0 for row in (*receipt["four_tools"].values(), tgs)),
                "no synthetic bridge was accepted; inspect the native/admission reports")
        # Accept actual platform results, not x86_64-specific exact edit counts.
        for relpath, expected in load(case / "case.json")["files_sha256"].items():
            require(digest(case / relpath) == expected, f"synthetic input changed: {relpath}")
    except (OSError, ValueError, KeyError) as error:
        receipt.update(status="failed", error=str(error))
        save()
        raise SystemExit(f"{error}; evidence: {receipt_path}") from error
    receipt["status"] = "passed"
    save()
    print(receipt_path)


if __name__ == "__main__":
    main()
