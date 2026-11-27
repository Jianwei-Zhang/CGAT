"""Fail-closed, single-shot Donau successor: validated production Q0 -> LGZ.

No polling daemon, resubmission, checkpoint mutation or mapper runs in the gate.
The scheduler releases this job after BOTH validation and install jobs end.
Only the genuine installed routed owner can start the original 55-unit plan.
"""
import argparse
from collections import defaultdict
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile

SOURCE_REVISION = "adfe5e31831bc995aaec127a5ab98c1b65a37567"
SOURCE_PARENT = "9291117613910937da5f4f9c3c57beadb7885254"
SOURCE_ARCHIVE = "36c1573bf59a8fa6427fbb8e71d6c3a963ee9b821b16666dd2b27b3800daa560"
MINIMUM_SOURCE_BP = 11_000_000_000
MAIN_GROUPS = {str(n) + genome for n in range(1, 8) for genome in "ABD"}
GROUPS = MAIN_GROUPS | {"Un"}
DJOB = "/opt/batch/cli/bin/djob"


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    need(path.is_file() and not path.is_symlink(), "missing/linked file: " + str(path))
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_once(path, value):
    with path.open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write("\n")
        f.flush(); os.fsync(f.fileno())


def bound(row):
    p = Path(row["path"])
    need(p.resolve() == p and digest(p) == row["sha256"], "bound file changed: " + str(p))
    return p


def verify_kit(owner, kit="kit.sha256"):
    for line in (owner / kit).read_text().splitlines():
        sha, name = line.split()
        rel = Path(name)
        need(not rel.is_absolute() and ".." not in rel.parts, "unsafe kit member")
        p = owner / rel
        need(p.resolve() == p and digest(p) == sha, "kit member changed: " + name)


def job(spec, state):
    raw = subprocess.check_output([DJOB, "-ll", "-J", str(spec["job_id"])], timeout=60)
    rows = json.loads(raw)["data"]["successData"]
    need(len(rows) == 1, "ambiguous scheduler response")
    row = rows[0]
    for key, expected in (("jobId", str(spec["job_id"])), ("jobName", spec["name"]),
                          ("execPath", spec["owner"]), ("user", "xbzhang26"), ("queue", "x86")):
        need(str(row.get(key)) == expected, "wrong scheduler identity: " + key)
    need(row["state"] == state, "job " + str(spec["job_id"]) + " is " + row["state"] + ", not " + state)
    return row, json.loads(raw)


def new_cross_conflicts(current, prior):
    """Subtract baseline conflicts by source coordinates, never just by count."""
    def key(row):
        return (tuple(row["source"]), row["current_group"], row["old_group"],
                row["current_orientation"], row["old_orientation"])
    old = defaultdict(list)
    for row in prior:
        if row["category"] == "other_chromosome":
            old[key(row)].append(row["interval"])
    new = []
    for row in current:
        if row["category"] != "other_chromosome":
            continue
        intervals = [tuple(row["interval"])]
        for a, b in sorted(old[key(row)]):
            rest = []
            for lo, hi in intervals:
                if hi <= a or lo >= b:
                    rest.append((lo, hi))
                else:
                    if lo < a: rest.append((lo, a))
                    if b < hi: rest.append((b, hi))
            intervals = rest
        new.extend({**row, "interval": [lo, hi], "bp": hi-lo} for lo, hi in intervals)
    return new


def hard_gates(metrics, overlaps, new_conflicts):
    need(set(metrics) == GROUPS, "22 group coverage is incomplete")
    for group in MAIN_GROUPS:
        m = metrics[group]
        need(m["has_path"] is True and m["slices"] > 0 and m["selected_reference_bp"] > 0,
             "main chromosome lacks a trusted anchored path: " + group)
    total = sum(m["selected_source_bp"] for m in metrics.values())
    need(all(type(m["selected_source_bp"]) is int and m["selected_source_bp"] >= 0
             for m in metrics.values()), "invalid source coverage metrics")
    need(total >= MINIMUM_SOURCE_BP, "selected source length below 11 Gb: " + str(total))
    need(not overlaps, "source coordinate duplicate occupation")
    need(not new_conflicts, "new selected cross-chromosome old-Q0 conflict")
    return {"selected_source_bp": total, "minimum_source_bp": MINIMUM_SOURCE_BP,
            "main_paths": 21, "groups": 22, "source_duplicates": 0, "new_cross_chromosome_conflicts": 0}


def inspect_paths(audit, admitted, paths, routes):
    groups, occupied = defaultdict(dict), defaultdict(list)
    for p in admitted.placements:
        groups[p.chromosome][p.placement_id] = p
    metrics, conflicts, overlaps = {}, [], []
    for group, path in paths.items():
        metrics[group] = audit.group_metrics(groups[group], path)
        if path is None:
            continue
        for piece in path.slices:
            conflicts.extend(audit.conflict_rows(piece.source, piece.interval, group, piece.orientation, routes))
        entries = [(s.source, s.interval) for s in path.slices]
        entries += [(j.gap_source, j.gap_interval) for j in path.joins if j.gap_source is not None]
        for source, iv in entries:
            for prior_group, prior in occupied[source]:
                ov = iv.intersection(prior)
                if ov is not None:
                    overlaps.append({"source": [source.dataset, source.contig], "groups": [prior_group, group],
                                     "interval": [ov.start, ov.end]})
            occupied[source].append((group, iv))
    return metrics, conflicts, overlaps


def verify_validation_source(config, source):
    need(source["engine_commit"] == config.get("runtime_revision", config["engine_revision"])
         and source["path_policy"]["reference_locus_padding_bp"] == 100000,
         "wrong production validation engine/padding")
    if config.get("runtime_revision") == SOURCE_REVISION:
        need(source.get("scientific_baseline_commit") == SOURCE_PARENT
             and source.get("tools_sha256") == SOURCE_ARCHIVE
             and source.get("selector_identity") == "q0-selector-37bb033a42a3772eae997621", "wrong source-ownership validation")
    elif "runtime_revision" in config:
        need(source.get("scientific_baseline_commit") == config["engine_revision"],
             "wrong qualified scientific baseline")


@contextmanager
def validation_code(config):
    source_path = bound(config["validation_source"])
    owner = source_path.parent
    need(bound(config["validation_kit"]) == owner / "kit.sha256", "foreign validation kit")
    verify_kit(owner)
    source = json.loads(source_path.read_text())
    verify_validation_source(config, source)
    archive = owner / "tools.tgz"
    need(digest(archive) == source["tools_sha256"], "validation tools changed")
    with tempfile.TemporaryDirectory(prefix="wheat-relay-code-") as tmp:
        code = Path(tmp)
        with tarfile.open(archive) as tar:
            for item in tar.getmembers():
                rel = Path(item.name)
                need(not rel.is_absolute() and ".." not in rel.parts and (item.isfile() or item.isdir()), "unsafe source archive")
            tar.extractall(code)
        sys.path[:0] = [str(code / "tools"), str(owner)]
        import wheat_production22_cached as audit
        need(audit.admission.selector_identity() == source["selector_identity"], "wrong loaded selector")
        yield owner, code, audit, source


def verify(config, root):
    validation, vraw = job(config["validation_job"], "SUCCEEDED")
    installation, iraw = job(config["install_job"], "SUCCEEDED")
    own_id = (root / "relay-jobid").read_text().strip()
    own_spec = dict(job_id=own_id, name="jm19_q0_formal_continuity", owner=str(root))
    own, allocation = job(own_spec, "RUNNING")
    group, = own["resGroups"]
    need(own["taskExecNodesCount"] == 1 and own["taskExecNodes"] == socket.gethostname()
         and group["resAlloc"]["cpu"] >= 32
         and min(group["resAlloc"]["mem"], group["resLimit"]["mem"]) >= 327680, "formal allocation insufficient")
    transition_path = bound(config["transition"])
    troot = transition_path.parent
    need(bound(config["transition_kit"]) == troot / "kit.sha256", "foreign transition kit")
    verify_kit(troot)
    transition = json.loads(transition_path.read_text())
    need(transition["continuous_q0_policy_change"]["engine_revision"] == config["engine_revision"], "wrong installed scientific policy")
    install = json.loads((troot / "entry-repair.json").read_text())
    verify_engineering_binding(config, transition, install)
    need(install["status"] == "continuity_engine_installed_and_one_original_parent_verified"
         and install["transition_sha256"] == config["transition"]["sha256"]
         and install["source_revision"] == config.get("runtime_revision", config["engine_revision"])
         and install["checkpoint_files_unchanged"] == 25 and install["protected_control_files_unchanged"] is True
         and install["formal_main_started"] is False, "installation is not accepted")
    preflight = json.loads((troot / "validation-selected.json").read_text())
    need(preflight["transition_sha256"] == config["transition"]["sha256"]
         and preflight["initial_checkpoints"] == [install["representative_parent"]]
         and install["representative_parent"]["unit_id"] == "q0_chr:Un", "Un parent preflight differs")
    work = Path(transition["workspace"])
    controls = json.loads((troot / "control-before.json").read_text())
    for name, sha in controls.items():
        need(digest(work / name) == sha, "original checkpoint/control changed before relay: " + name)
    journal_path = troot / "installation/receipt.json"
    need(digest(journal_path) == install["installation_receipt_sha256"], "installation journal changed")
    journal = json.loads(journal_path.read_text())
    need(journal["status"] == "installed" and journal["transition_sha256"] == config["transition"]["sha256"], "installation not complete")
    for row in journal["installed"]:
        need(digest(work / row["relative"]) == row["sha256"], "installed runtime drift")
    need(not (work / "metadata/grt_q0_evidence.json").exists() and not (work / "grt/q/q0.fa").exists(),
         "formal Q0 already published; never overwrite or repeat relay")
    with validation_code(config) as (owner, code, audit, source):
        need(str(owner) == config["validation_job"]["owner"], "foreign validation owner")
        for row in transition["runtime"]:
            relative = Path(row["relative"]).relative_to(".prepare_lib/tools")
            need(digest(code / "tools" / relative) == row["new_sha256"], "formal runtime differs from tested production source")
        report_path = owner / "result/production22-audit.json"
        report_sha = digest(report_path); report = json.loads(report_path.read_text())
        need(report["selector_identity"] == source["selector_identity"] and report["mapper_starts"] == 0,
             "validation report source/scope mismatch")
        admitted, paths, summary = audit.read_selection(owner, sorted(GROUPS))
        need(digest(owner / "result/summary.json") == report["summary_sha256"] and summary["mapper_starts"] == 0,
             "validation completion summary mismatch")
        baseline = owner.parent / "q0-whole-local-maps.soHq9Z6J"
        old, old_paths, old_summary = audit.read_selection(baseline, sorted(GROUPS), audit.BASELINE_SHA)
        need(summary["evidence_digest"] == old_summary["evidence_digest"], "validation evidence cohort changed")
        routes = audit.old_routes(owner.parent / "q0-continuity-20261126.RAbGvNba/old-grt-q-segments.tsv")
        metrics, conflicts, overlaps = inspect_paths(audit, admitted, paths, routes)
        _, prior_conflicts, _ = inspect_paths(audit, old, old_paths, routes)
        for name, values in metrics.items():
            need(all(report["groups"][name][k] == v for k, v in values.items()), "report differs from sealed paths: " + name)
        new_conflicts = new_cross_conflicts(conflicts, prior_conflicts)
        verdict = hard_gates(metrics, overlaps, new_conflicts)
        if config.get("runtime_revision") == SOURCE_REVISION:
            from wheat_source_collision_controls import control_audit, validate_admission_occupancy
            validate_admission_occupancy(admitted.placements)
            controls = control_audit(owner, metrics)
            need(controls == json.loads((owner/"result/source-control-audit.json").read_text()), "control report mismatch")
            need(controls["passed"], "control regression: " + json.dumps(controls["groups"]))
            verdict["source_controls"] = controls
            verdict["cross_chromosome_admission_overlaps"] = 0
        need(digest(report_path) == report_sha, "validation report changed during gate")
    return {"status": "GO", "hard_gates": verdict, "validation_report_sha256": report_sha,
            "validation_job": validation["jobId"], "install_job": installation["jobId"],
            "transition_sha256": config["transition"]["sha256"], "engine_revision": config["engine_revision"],
            "runtime_revision": config.get("runtime_revision", config["engine_revision"]),
            "current_cross_conflict_rows": sum(r["category"] == "other_chromosome" for r in conflicts),
            "baseline_cross_conflict_rows": sum(r["category"] == "other_chromosome" for r in prior_conflicts)}, allocation


def verify_engineering_binding(config, transition, install):
    engineering = transition.get("exact_engineering_change")
    revision = config.get("runtime_revision")
    ownership = transition.get("source_occupancy_change")
    if revision == SOURCE_REVISION or ownership is not None:
        need(engineering is None and isinstance(ownership, dict)
             and ownership.get("schema") == "q0_cross_chromosome_source_occupancy_v1"
             and ownership.get("runtime_revision") == revision == install.get("source_revision") == SOURCE_REVISION
             and ownership.get("baseline_revision") == SOURCE_PARENT
             and ownership["candidate_archive"]["sha256"] == SOURCE_ARCHIVE, "wrong installed source-occupancy transition")
        bound(ownership["candidate_archive"])
        return
    if engineering is None:
        need(revision is None, "unqualified engineering runtime")
        return
    need(engineering.get("schema") in ("q0_exact_pair_engineering_v1", "q0_exact_owner_pair_v1")
         and engineering.get("baseline_revision") == config["engine_revision"]
         and engineering.get("runtime_revision") == revision == install.get("source_revision"),
         "installed engineering revision differs from qualified relay")
    report = json.loads(bound(engineering["qualification"]).read_text())
    if engineering["schema"] == "q0_exact_owner_pair_v1":
        need(report.get("schema") == "wheat_owner_pair_qualification_v1" and report.get("owner_only_verified") is True
             and report.get("checkpoint_output_sha256") == "99f36fc6fc16535e315aa4d6d0511b2c0028789bc00f3293d9e4a8af1d199b2a"
             and report.get("candidate_output_sha256") == "eb50499368308cef375a82619bb043a8d679b9a17238582c75c2556bee7f9a47",
             "owner-only qualification differs")
    else:
        need(report.get("real_worker_dispatch_verified") is True, "engineering field equivalence gate failed")
    need(report.get("field_exact_equal") is True
         and report.get("baseline_revision") == config["engine_revision"]
         and report.get("candidate_output_sha256") == report.get("baseline_output_sha256")
         and report.get("mapper_calls") == 0 and report.get("formal_workspace_modified") is False,
         "engineering field equivalence gate failed")


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--config", type=Path, required=True)
    path = parser.parse_args().config.resolve(strict=True); root = path.parent
    need(Path(__file__).resolve().parent == root and root.stat().st_mode & 0o077 == 0, "unsafe relay owner")
    config_sha = digest(path); config = json.loads(path.read_text())
    need(config.get("schema") == "wheat_continuity_conditional_relay_v1"
         and config.get("engine_revision") == "2064cb4cfd51b5c886f60af19f020caf0b18950f", "unsupported relay policy")
    verify_kit(root, "relay-kit.sha256")
    with (root / "relay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(not any((root / n).exists() for n in ("gate-hold.json", "gate-go.json", "formal-start.intent.json")), "relay already consumed; no automatic retry")
        try:
            verdict, allocation = verify(config, root)
            need(digest(path) == config_sha, "relay config changed")
            write_once(root / "gate-go.json", {**verdict, "config_sha256": config_sha})
            proof = root / "formal-allocation.json"; write_once(proof, allocation)
            transition = json.loads(bound(config["transition"]).read_text())
            entry = bound(transition["dependencies"]["entry"])
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", GPM_RUN_THREADS="32",
                       _GPM_Q0_SCHEDULER_PROOF=str(proof), _GPM_Q0_SCHEDULER_SHA256=digest(proof))
            env.pop("PYTHONPATH", None)
            write_once(root / "formal-start.intent.json", {"transition_sha256": config["transition"]["sha256"], "threads": 32,
                       "entry": str(entry), "gate_sha256": digest(root / "gate-go.json")})
            print("CONDITIONAL_Q0_LGZ_GO", json.dumps(verdict), flush=True)
            os.execve(sys.executable, [sys.executable, "-B", "-u", str(entry), "--transition",
                                      config["transition"]["path"], "--threads", "32"], env)
        except Exception as error:
            write_once(root / "gate-hold.json", {"status": "HOLD", "reason": str(error),
                       "error_type": type(error).__name__, "config_sha256": config_sha,
                       "formal_owner_exec_completed": False, "automatic_retry": False})
            print("CONDITIONAL_Q0_LGZ_HOLD", type(error).__name__, str(error), flush=True)
            return 42


if __name__ == "__main__":
    raise SystemExit(main())
