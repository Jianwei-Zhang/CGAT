"""Write a resource-gated launch script after the real read-only preflight.

This only prepares the isolated handoff packet. It does not submit resources,
stop a job, install code, or change the live workspace.
"""
import argparse
import json
from pathlib import Path
import shlex

from probe_q0_loader_allocation import checked, sha256, smoke_scope, POLICY


def record(path):
    return {"path": str(path), "sha256": sha256(path)}


def load_initial(path, transition_sha):
    data = json.loads(path.read_text())
    if (data.get("status") != "q0_transition_all_initial_checkpoints_verified_only"
            or data.get("transition_sha256") != transition_sha
            or any(data.get(k) is not False for k in ("workspace_modified", "main_task_submitted", "q0_runtime_installed"))):
        raise ValueError("no real read-only initial checkpoint preflight")
    rows = data["initial_checkpoints"]
    keys = [x["unit_id"] for x in rows]
    if (len(keys) != 25 or len(set(keys)) != 25 or keys[2] != "assign"
            or not all(k.startswith("ref:") for k in keys[:2])
            or not all(k.startswith("q0_chr:") for k in keys[3:])):
        raise ValueError("not all actual 25 initial checkpoints")
    return rows


def prepare(root, environment):
    root = root.resolve(strict=True)
    stage = json.loads((root / "candidate-prepared.json").read_text())
    if (stage.get("status") != "q0_candidate_prepared_not_installed"
            or stage.get("job_stopped") is not False or stage.get("workspace_modified") is not False
            or stage.get("previous_job") == stage.get("protected_baseline")):
        raise ValueError("not an uninstalled and isolated Q0 candidate")
    tpath = checked(stage["transition"], root)
    transition = json.loads(tpath.read_text())
    work = Path(transition["workspace"]).resolve(strict=True)
    if (root.is_relative_to(work) or transition.get("regional_mapper_loader_policy") != POLICY
            or (work / "metadata/grt_q0_evidence.json").exists()
            or (root / "installation").exists()):
        raise ValueError("unexpected cutover scope, or Q0 already completed")
    previous = checked(stage["previous_transition"], root.parent)
    old_validation = previous.with_name("validation.json")
    fresh = root / "validation.json"
    if load_initial(fresh, stage["transition"]["sha256"]) != load_initial(old_validation, stage["previous_transition"]["sha256"]):
        raise ValueError("one of the protected initial identities changed")
    smoke = root / "smoke-v2/smoke.jsonl"
    smoke_scope(smoke)
    sample = root / "live-sample.json"
    for row in transition["runtime"]:
        runtime = work / row["relative"]
        if (not runtime.resolve(strict=True).is_relative_to(work) or runtime.is_symlink()
                or sha256(runtime) != row["prior_sha256"]
                or sha256(checked(row["source"], root)) != row["new_sha256"]):
            raise ValueError("installed or staged runtime drifted")
    if (sha256(work / "prepare_q0_evidence.sh") != transition["prior_launcher_sha256"]
            or sha256(work / "metadata/incident_q0_routing_reader.json") != transition["prior_declaration_sha256"]):
        raise ValueError("installed Q0 entry or declaration drifted")
    config_path = root / "handoff-config.json"
    script_path = root / "resume.dsub"
    checksum = root / "resource-launch.sha256"
    if any(path.exists() or path.is_symlink() for path in (config_path, script_path, checksum,
            root / "loader-ready.json", root / "ready.json", root / "handoff.json")):
        raise ValueError("handoff launch already staged; will not overwrite")
    environment = environment.resolve(strict=True)
    probe = root / "probe_q0_loader_allocation.py"
    cwd = shlex.quote(str(root))
    config = {"workspace": str(work), "old_job": stage["previous_job"], "protected_baseline": stage["protected_baseline"],
              "transition": stage["transition"], "initial_preflight": record(fresh), "loader_smoke": record(smoke),
              "loader_probe": record(probe), "environment": record(environment), "old_window_sample": record(sample)}
    script = f'''#!/usr/bin/env bash
#DSUB -n jm19_q0_verified_loader_cutover
#DSUB -q x86
#DSUB -aa
#DSUB -R "cpu=32,mem=327680MB"
#DSUB -o {root}/resume_%J.out
set -eo pipefail
umask 077
cd {cwd}
sha256sum -c resource-launch.sha256
source {shlex.quote(str(environment))}
sha256sum -c code.sha256
# This timeout applies only to the isolated loader check, never the analysis.
test ! -e loader-ready.json
PYTHONPATH={cwd}/package/server/tools${{PYTHONPATH:+:$PYTHONPATH}} timeout --signal=TERM --kill-after=10s 350s \\
  python3 -B -u probe_q0_loader_allocation.py --config handoff-config.json > loader-ready.json.tmp
mv loader-ready.json.tmp loader-ready.json
sha256sum loader-ready.json
# The existing resource/owner gate still needs old terminal + no pids + no lock.
exec python3 -B -u q0_science_handoff_gate.py --config handoff-config.json
'''
    with config_path.open("x") as stream:
        json.dump(config, stream, sort_keys=True, indent=2)
        stream.write("\n")
    with script_path.open("x") as stream:
        stream.write(script)
    script_path.chmod(0o755)
    with checksum.open("x") as stream:
        for path in (config_path, script_path, probe, environment, fresh, smoke, sample, tpath):
            stream.write(f"{sha256(path)}  {path}\n")
    return {"status": "loader_resource_gate_configured_not_submitted", "config": record(config_path),
            "script": record(script_path), "checksums": record(checksum), "workspace_modified": False}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--environment", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.bundle, a.environment), sort_keys=True, indent=2))
