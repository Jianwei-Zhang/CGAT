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


def prior_window_tool(work, sample):
    """Read only receipt metadata; its bound native tool is part of every key."""
    row = json.loads(sample.read_text())["rows"][0]
    project = Path(row["project"])
    if len(project.parts) != 1 or not project.name.startswith("q0-regional-project-"):
        raise ValueError("invalid cached window smoke identity")
    marker = work / "grt/evidence/q0_prepare/regional/projects" / project / "success.json"
    if not marker.resolve(strict=True).is_relative_to(work):
        raise ValueError("prior window escaped the workspace")
    declared = json.loads(marker.read_text())["spec"]
    for item in (declared["raw_receipt"], declared["context"]):
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid cached window artifact path")
        checked({**item, "path": str(work / relative)}, work)
    if declared["raw_receipt"]["sha256"] != row["raw_receipt_sha256"]:
        raise ValueError("prior window receipt changed")
    return json.loads((work / declared["context"]["path"]).read_text())["spec"]["tool"]


REPLAY_FILES = frozenset(('probe_q0_loader_allocation.py', 'benchmark_regional_thread_split.py',
                          'benchmark_regional_mapper_dispatch.py', 'q0_allocation_loader_replay.py'))


def replay_controls(config, root):
    records = config['loader_replay_controls']
    if set(records) != REPLAY_FILES:
        raise ValueError('incomplete allocation replay controls')
    paths = {name: checked(record, root.parent) for name, record in records.items()}
    parent = paths['probe_q0_loader_allocation.py'].parent
    if (parent == root or parent.parent != root.parent
            or any(path.parent != parent or path.name != name for name, path in paths.items())
            or paths['probe_q0_loader_allocation.py'] != Path(__file__).resolve()):
        raise ValueError('allocation replay controls are not an isolated bound packet')
    if config['loader_probe'] != records['probe_q0_loader_allocation.py']:
        raise ValueError('allocation probe has a different identity')
    return paths


def qualify_loader(enabled, stored, replay=None):
    if enabled is not None and enabled == stored:
        return {'mode': 'original_writer_smoke_match'}
    scope = {'policy', 'tool_sha256', 'dependencies_sha256', 'inherited_path_sha256'}
    if (replay is None or not isinstance(enabled, dict) or set(enabled) != scope or set(stored) != scope
            or {key for key in scope if enabled[key] != stored[key]} != {'inherited_path_sha256'}):
        raise ValueError("the new allocation's loader identities differ from the successful smoke")
    return {'mode': 'inherited_path_changed_with_same_allocation_archive_replay', **replay()}


def probe(config_path):
    from lgz_core import q0_regional_mapping as mapping
    from lgz_core.common import executable_identity

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
    # The regular builder includes the version string in context/raw keys. A
    # slow/dead --version probe may return "unknown" with the *same* binary.
    # Byte compatibility alone would then fail to reuse thousands of caches.
    expected_tool = prior_window_tool(work, checked(config["old_window_sample"], root))
    if expected_tool.get("version") in (None, "unknown") or executable_identity("minimap2") != expected_tool:
        raise ValueError("mapper cache identity (including version) differs on this allocation")
    row = next(row for row in transition["runtime"] if row["relative"].endswith("/q0_regional_mapping.py"))
    module_path = root / "package/server/tools/lgz_core/q0_regional_mapping.py"
    if (Path(mapping.__file__).resolve(strict=True) != module_path or sha256(module_path) != row["new_sha256"]
            or sha256(checked(row["source"], root)) != row["new_sha256"]):
        raise ValueError("allocation probe did not import the confirmed candidate")
    loader = mapping._probe_mapper_loader("minimap2")
    if loader is None:
        raise ValueError("this allocation cannot safely enable the regional mapper loader")
    tool = {"resolved": loader.tool_path, "sha256": loader.tool_sha256}
    env, enabled = loader.child(tool)
    if len(os.sched_getaffinity(0)) < 32:
        raise ValueError("new allocation has less than 32 CPUs in its affinity")
    replay = None
    if 'loader_replay_controls' in config:
        paths = replay_controls(config, root)
        from q0_allocation_loader_replay import replay_archive
        if Path(replay_archive.__code__.co_filename).resolve(strict=True) != paths['q0_allocation_loader_replay.py']:
            raise ValueError('wrong allocation replay module loaded')
        replay = lambda: replay_archive(root, work, env)
    acceptance = qualify_loader(enabled, stored, replay)
    if sha256(config_path) != config_sha:
        raise ValueError("allocation configuration changed while checking the loader")
    checked(config["transition"], root)
    checked(config["loader_smoke"], root)
    if replay is not None:
        replay_controls(config, root)
    return {"status": "regional_loader_ready_before_handoff", "host": socket.gethostname(),
            "config_sha256": config_sha, "transition_sha256": config["transition"]["sha256"],
            "candidate_sha256": sha256(module_path), "loader_smoke_sha256": config["loader_smoke"]["sha256"],
            "loader": asdict(loader), "acceptance": acceptance, "expected_cached_tool": expected_tool, "workspace_modified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.config), indent=2, sort_keys=True), flush=True)
