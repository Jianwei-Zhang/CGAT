"""Check this allocation against the successful regional-loader smoke before ready.

Run from a staged candidate package, not from the live workspace. Never starts
or stops a main job, and never enables the optimization in the parent process.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import socket


POLICY = "clear_same_dependencies_v1"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(row, root):
    path = Path(row["path"])
    if (not path.is_absolute() or path.is_symlink() or not path.resolve(strict=True).is_relative_to(root)
            or sha256(path) != row["sha256"]):
        raise ValueError("loader handoff proof drifted or escaped its packet")
    return path


def smoke_scope(path):
    last = json.loads(path.read_text().splitlines()[-1])
    if (last.get("status") != "real_regional_writer_parity_and_old_reader_reuse"
            or last.get("production_modified") is not False or len(last["old_project_receipts"]) != 2
            or len({row["project"] for row in last["old_project_receipts"]}) != 2
            or len(last["new_execution_in_isolated_dir"]) != 2):
        raise ValueError("no successful isolated producer and reader test")
    observed = {row["mode"]: row["child_loader"] for row in last["new_execution_in_isolated_dir"]}
    if (set(observed) != {"precise", "chaining"} or observed["precise"] != observed["chaining"]
            or observed["precise"]["policy"] != POLICY):
        raise ValueError("isolated chaining and exact loader proofs differ")
    return observed["precise"]


def probe(config_path):
    from lgz_core import q0_regional_mapping as mapping

    config_path = config_path.resolve(strict=True)
    root = config_path.parent
    raw = config_path.read_bytes()
    config_sha = hashlib.sha256(raw).hexdigest()
    config = json.loads(raw)
    transition_path = checked(config["transition"], root)
    transition = json.loads(transition_path.read_text())
    work = Path(transition["workspace"]).resolve(strict=True)
    if (root.is_relative_to(work) or config["workspace"] != str(work)
            or transition.get("regional_mapper_loader_policy") != POLICY
            or config["old_job"] == config["protected_baseline"]):
        raise ValueError("invalid q0 loader handoff scope")
    stored = smoke_scope(checked(config["loader_smoke"], root))
    row = next(row for row in transition["runtime"] if row["relative"].endswith("/q0_regional_mapping.py"))
    module_path = root / "package/server/tools/lgz_core/q0_regional_mapping.py"
    if (Path(mapping.__file__).resolve(strict=True) != module_path or sha256(module_path) != row["new_sha256"]
            or sha256(checked(row["source"], root)) != row["new_sha256"]):
        raise ValueError("allocation probe did not import the confirmed candidate")
    loader = mapping._probe_mapper_loader("minimap2")
    if loader is None:
        raise ValueError("this allocation cannot safely enable the regional mapper loader")
    tool = {"resolved": loader.tool_path, "sha256": loader.tool_sha256}
    _, enabled = loader.child(tool)
    if enabled != stored:
        raise ValueError("the new allocation's loader identities differ from the successful smoke")
    if len(os.sched_getaffinity(0)) < 32:
        raise ValueError("new allocation has less than 32 CPUs in its affinity")
    if sha256(config_path) != config_sha:
        raise ValueError("allocation configuration changed while checking the loader")
    checked(config["transition"], root)
    checked(config["loader_smoke"], root)
    return {"status": "regional_loader_ready_before_handoff", "host": socket.gethostname(),
            "config_sha256": config_sha, "transition_sha256": config["transition"]["sha256"],
            "candidate_sha256": sha256(module_path), "loader_smoke_sha256": config["loader_smoke"]["sha256"],
            "loader": asdict(loader), "workspace_modified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.config), indent=2, sort_keys=True), flush=True)
