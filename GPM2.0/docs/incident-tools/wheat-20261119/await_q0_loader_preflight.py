"""Bounded site watcher: submit one waiting resource job, never stop/install.

The normal handoff still requires a separate operator decision. In ambiguous
submission states the intent receipt is retained; this tool never retries dsub.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import time

from prepare_q0_loader_launch import prepare, record
from probe_q0_loader_allocation import checked, smoke_scope

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "CANCELED", "ENDED"}


def emit(**fields):
    print(json.dumps({"at": datetime.datetime.now().astimezone().isoformat(), **fields}, sort_keys=True), flush=True)


def query(job):
    response = subprocess.run(["djob", "-J", str(job)], text=True, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    # A failed/missing/ambiguous lookup is not a terminal job.
    rows = json.loads(response.stdout)["data"]["successData"]
    if len(rows) != 1 or str(rows[0].get("jobId")) != str(job):
        raise ValueError("scheduler did not return exactly the requested job")
    return rows[0]


def load_config(config_path):
    root = config_path.parent
    config = json.loads(config_path.read_text())
    stage = json.loads(checked(config["candidate"], root).read_text())
    smoke_scope(checked(config["loader_smoke"], root))
    if (stage.get("status") != "q0_candidate_prepared_not_installed" or stage["transition"] != config["transition"]
            or stage["previous_job"] != config["running_job"] or stage["protected_baseline"] != config["baseline_job"]):
        raise ValueError("watcher is not bound to the staged handoff and job IDs")
    transition = json.loads(checked(config["transition"], root).read_text())
    work = Path(transition["workspace"]).resolve(strict=True)
    if work == root or root.is_relative_to(work):
        raise ValueError("watcher must run from isolated handoff packet")
    if len({config[name] for name in ("running_job", "baseline_job", "preflight_job", "smoke_job")}) != 4:
        raise ValueError("four distinct jobs required")
    return config, work


def maybe_submit(config_path, expected, work):
    root = config_path.parent
    config, current_work = load_config(config_path)
    if record(config_path) != expected or current_work != work:
        raise ValueError("watcher configuration drifted")
    preflight = query(config["preflight_job"])
    state = preflight["state"]
    if state not in TERMINAL:
        return None, state
    if state != "SUCCEEDED":
        raise ValueError("read-only preflight reached terminal state without success: " + state)
    if query(config["smoke_job"])["state"] != "SUCCEEDED":
        raise ValueError("the successful loader smoke no longer verifies")
    main = query(config["running_job"])
    if main["state"] != "RUNNING" or query(config["baseline_job"])["state"] != "RUNNING":
        raise ValueError("main or baseline state changed; reassess rather than submit")
    owner = json.loads((work / ".run_all/lock/owner.json").read_text())
    if (owner.get("workspace") != str(work) or owner.get("run_id") != config["running_run_id"]
            or owner.get("hostname") != main.get("execNodes")):
        raise ValueError("main workspace owner changed; reassess rather than submit")
    if (work / "metadata/grt_q0_evidence.json").exists():
        raise ValueError("Q0 already completed; no cutover needed")
    env = Path(config["environment"]["path"])
    if record(env) != config["environment"]:
        raise ValueError("environment bytes differ from staged watcher")
    result = prepare(root, env)  # validates fresh 25 proofs against the exact previous identities
    script = checked(result["script"], root)
    # Never submit twice, even if dsub commits remotely before its stdout is lost.
    intent = root / "loader-resource-submit-intent.json"
    with intent.open("x") as stream:
        json.dump({"state": "submit_once_waiting_only", "watcher": expected, "prepared": result}, stream, sort_keys=True)
        stream.write("\n")
    r = subprocess.run(["dsub", "-s", str(script)], cwd=root, text=True, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    match = re.search(r"Submit job <([1-9][0-9]*)> successfully", r.stdout)
    if match is None:
        raise ValueError("dsub result ambiguous, inspect scheduler rather than retry")
    receipt = {"state": "resource_job_submitted_waiting_only", "resource_job": int(match[1]),
               "running_job": config["running_job"], "baseline_job": config["baseline_job"],
               "preflight_job": config["preflight_job"], "config": result["config"], "intent": record(intent)}
    with (root / "loader-resource-submitted.json").open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return receipt, state


def watch(config_path, rounds):
    config_path = config_path.resolve(strict=True)
    expected = record(config_path)
    config, work = load_config(config_path)
    emit(status="waiting_for_readonly_preflight", preflight=config["preflight_job"])
    for iteration in range(rounds):
        try:
            result, state = maybe_submit(config_path, expected, work)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
            if (config_path.parent / "loader-resource-submit-intent.json").exists():
                raise  # ambiguous dsub; never auto-retry
            emit(status="observation_failed_will_poll_same_preflight", preflight=config["preflight_job"])
        else:
            if result:
                emit(**result)
                return
            if iteration % 5 == 0:
                emit(status="read_only_preflight_live", preflight=config["preflight_job"], scheduler_state=state)
        if iteration + 1 < rounds:
            time.sleep(60)
    emit(status="observation_window_expired_no_job_stopped", preflight=config["preflight_job"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--rounds", type=int, default=90, choices=range(1, 121), metavar="1..120")
    args = p.parse_args()
    watch(args.config, args.rounds)
