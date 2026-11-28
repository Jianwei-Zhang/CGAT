"""Private execution budgets, separate from immutable preparation/cache identity."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import os
if __package__:
    from .long_cigar_recovery.minimap_options import batch_size, BATCH_ENV
else:
    from long_cigar_recovery.minimap_options import batch_size, BATCH_ENV
from pathlib import Path

try:
    from workspace_layout import workspace_path
    from run_orchestration import atomic_write_json
except ModuleNotFoundError:
    from .workspace_layout import workspace_path
    from .run_orchestration import atomic_write_json

RESOURCE_OPTIONS = {"--threads": "threads", "--grt-qc-memory-gb": "qc_memory_gb",
                    "--minimap-batch": "minimap_batch", "--reference-schedule": "reference_schedule"}
ENV_KEYS = {"threads": "GPM_RUN_THREADS", "qc_memory_gb": "GPM_RUN_QC_MEMORY_GB",
            "minimap_batch": BATCH_ENV}


def positive(value, name: str) -> int:
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdecimal() or int(value) < 1:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def reference_schedule(value: str) -> str:
    if value not in ("shared", "exclusive"):
        raise ValueError("--reference-schedule must be shared or exclusive")
    return value


def read_resources(root: Path) -> dict:
    path = workspace_path(root, ".run_all/resources.json")
    if not path.exists() and not path.is_symlink():
        return {"schema_version": 1, "effective": {}, "history": []}
    if path.is_symlink() or not path.is_file():
        raise ValueError("Resource settings must be a regular file")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict) or value.get("schema_version") != 1
            or not isinstance(value.get("effective"), dict)
            or not isinstance(value.get("history"), list)
            or set(value["effective"]) - set(RESOURCE_OPTIONS.values())):
        raise ValueError("Invalid workspace resource settings")
    for key, budget in value["effective"].items():
        if key == "reference_schedule":
            reference_schedule(budget)
        elif key == "minimap_batch":
            if type(budget) is not str or batch_size(budget) != budget:
                raise ValueError("Invalid minimap2 batch size")
        else:
            if type(budget) is not int:
                raise ValueError(f"Invalid resource budget: {key}")
            positive(budget, key)
    return value


def prepared_resources(root: Path) -> dict:
    path = workspace_path(root, "metadata/prepare_options.tsv")
    with path.open(newline="", encoding="utf-8") as handle:
        options = {row["key"]: row["value"] for row in csv.DictReader(handle, delimiter="\t")}
    return {"threads": positive(options["threads"], "threads"),
            "reference_schedule": reference_schedule(options.get("reference_schedule", "shared")),
            "qc_memory_gb": positive(options.get("grt_qc_memory_gb", "80"), "QC memory"),
            "minimap_batch": batch_size(options.get("minimap_batch", "500M"))}


def update_resources(root: Path, options: dict, run_id: str) -> None:
    """Called only while the launcher holds the workspace lock; one atomic receipt."""
    requested = {}
    for flag, name in RESOURCE_OPTIONS.items():
        if flag not in options:
            continue
        value = options[flag][-1][0]
        if name == "reference_schedule":
            requested[name] = reference_schedule(value)
        elif name == "minimap_batch":
            requested[name] = batch_size(value)
        else:
            requested[name] = positive(value, flag)
    if not requested:
        return
    state = read_resources(root)
    previous = {**prepared_resources(root), **state["effective"]}
    changes = {name: {"from": previous[name], "to": budget}
               for name, budget in requested.items() if previous[name] != budget}
    if not changes:
        return
    runtime = workspace_path(root, ".prepare_lib")
    if runtime.is_dir() and not (runtime / "tools/run_resources.py").is_file():
        raise ValueError("This workspace runtime predates resource-only resume; update its Server runtime first")
    if "reference_schedule" in changes and runtime.is_dir():
        runner = runtime / "tools/run_all_runner.py"
        if not runner.is_file() or "--reference-schedule" not in runner.read_text(encoding="utf-8"):
            raise ValueError("This workspace runner predates --reference-schedule; update its runtime first")
    if "minimap_batch" in requested and runtime.is_dir():
        for command in (workspace_path(root, "runs")).glob("*_vs_ref/command.sh"):
            text = command.read_text(encoding="utf-8")
            if "long_cigar_recovery/server_alignment.py" not in text and BATCH_ENV not in text:
                raise ValueError("This workspace command predates -K overrides; preserve it and use a new output directory")
    plan = workspace_path(root, ".run_all/plan.tsv")
    if plan.is_file():
        with plan.open(newline="", encoding="utf-8") as handle:
            if any(row.get("unit_id") == "grt_step23" for row in csv.DictReader(handle, delimiter="\t")):
                raise ValueError("This legacy combined Step2/3 workspace does not support resource-only resume")
    state["effective"].update(requested)
    state["history"].append({"run_id": run_id,
        "at": datetime.now(timezone.utc).isoformat(), "changes": changes})
    atomic_write_json(workspace_path(root, ".run_all/resources.json"), state)
    print("[RESUME] " + "; ".join(f"{name}: {change['from']} -> {change['to']}"
                                 for name, change in changes.items()), flush=True)


def resource_environment(root: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if key not in ENV_KEYS.values()}
    for key, budget in read_resources(root)["effective"].items():
        if key in ENV_KEYS:  # reference scheduling is owned by the runner, not its children
            environment[ENV_KEYS[key]] = str(budget)
    return environment


def execution_threads(prepared: int, *, root: Path | None = None) -> int:
    """Use only at execution boundaries; leave legacy fingerprint parameters alone."""
    override = (read_resources(root)["effective"].get("threads") if root is not None
                else os.environ.get(ENV_KEYS["threads"]))
    if override is None:
        return prepared
    budget = positive(override, "threads")
    available = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else (os.cpu_count() or 1)
    return min(budget, available)


def execution_qc_memory(prepared: int) -> int:
    return positive(os.environ.get(ENV_KEYS["qc_memory_gb"], prepared), "QC memory")
