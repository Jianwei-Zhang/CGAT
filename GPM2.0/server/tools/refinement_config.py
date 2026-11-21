"""Downstream reads/tool requests, independent of frozen LGZ preparation identity."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

try:
    from workspace_layout import WorkspaceLayout, relative_path
    from refinement_recipes import select_reads, select_tools
    from refinement_tools import fingerprint, validate_runtime
    from run_orchestration import atomic_write_json, sha256_file
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, relative_path
    from .refinement_recipes import select_reads, select_tools
    from .refinement_tools import fingerprint, validate_runtime
    from .run_orchestration import atomic_write_json, sha256_file

OPTIONS = {"--hifi", "--ont", "--gapfill-tools"}
CONFIG = ".runtime/refinement/config.json"
SCHEMA = "cgat.refinement-config"
REQUEST = "cgat.refinement-request"
UNIT = "refinement"
COMMAND = ".runtime/commands/run_refinement.sh"
SCRIPT = r'''#!/usr/bin/env bash
set -euo pipefail
server_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
exec python3 "${server_dir}/.runtime/prepared/tools/post_lgz_refinement.py" --server-dir "$server_dir" --runner-owned
'''


class ConfigError(ValueError):
    pass


def json_file(path):
    if path.is_symlink() or not path.is_file():
        raise ConfigError("refinement settings must be a regular file: " + str(path))
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ConfigError("invalid refinement settings object")
    return value


def validate_config(value):
    if (value.get("schema") != SCHEMA or value.get("schema_version") != 1
            or set(value.get("groups", {})) != {"hifi", "ont"}):
        raise ConfigError("unsupported refinement configuration")
    groups = value["groups"]
    if any(not isinstance(rows, list) or any(not isinstance(path, str) or not Path(path).is_absolute() for path in rows) for rows in groups.values()):
        raise ConfigError("refinement reads require absolute typed file lists")
    select_tools(value.get("tools"), has_reads=any(groups.values()))
    return value


def resolve(root, options, *, saved_reads=None):
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2:
        if any(name in options for name in OPTIONS):
            raise ConfigError("Appending refinement to a legacy workspace requires explicit numbered-layout migration; do not re-prepare it.")
        return None, None
    file = layout.path(CONFIG)
    saved = validate_config(json_file(file)) if file.exists() or file.is_symlink() else {
        "schema": SCHEMA, "schema_version": 1, "groups": {"hifi": [], "ont": []}, "tools": None}
    groups = saved["groups"]
    if not file.exists() and saved_reads:
        groups = {kind: [row[0] for row in saved_reads.get("--" + kind, [])] for kind in ("hifi", "ont")}
    if any("--" + kind in options for kind in ("hifi", "ont")):
        groups = {kind: [str(Path(row[0]).resolve()) for row in options.get("--" + kind, [])] for kind in ("hifi", "ont")}
    explicit = options.get("--gapfill-tools", [[None]])[-1][0]
    choice = saved["tools"] if explicit in {None, "none"} else explicit
    effective = "none" if explicit == "none" else choice
    selected = select_tools(effective, has_reads=any(groups.values()))
    if any(groups.values()):
        # Shape/duplicate validation does not consume an unsupported technology.
        select_reads("degap", groups)
    stable = {"schema": SCHEMA, "schema_version": 1, "groups": groups, "tools": choice}
    validate_config(stable)
    request = {"schema": REQUEST, "schema_version": 1, "groups": groups,
               "tools": effective, "selected": list(selected), "configuration_sha256": fingerprint(stable)}
    return stable, request


def preflight(request, *, runtime=True):
    if request is None:
        return
    for tool in request["selected"]:
        selection = select_reads(tool, request["groups"])
        for path in {path for values in selection["selected"].values() for path in values}:
            if not Path(path).is_file() or not os.access(path, os.R_OK):
                raise ConfigError("selected refinement reads are not readable: " + path)
        if runtime:
            validate_runtime(tool=tool)


def save_request(root, options, run_id, *, saved_reads=None):
    stable, request = resolve(root, options, saved_reads=saved_reads)
    if request is None:
        return None
    relative_path(run_id)
    if "/" in run_id:
        raise ConfigError("invalid refinement invocation ID")
    layout = WorkspaceLayout.detect(root)
    config_path = layout.path(CONFIG)
    snapshot = layout.path(".runtime/refinement/configurations/" + fingerprint(stable) + ".json")
    if snapshot.exists() or snapshot.is_symlink():
        if json_file(snapshot) != stable:
            raise ConfigError("refinement configuration snapshot changed")
    else:
        atomic_write_json(snapshot, stable)
    if not config_path.exists() or json_file(config_path) != stable:
        atomic_write_json(config_path, stable)
    request.update(run_id=run_id)
    path = layout.path(f".runtime/refinement/requests/{run_id}.json")
    if path.exists() and json_file(path) != request:
        raise ConfigError("refinement invocation settings already exist with different contents")
    atomic_write_json(path, request)
    return request


def load_request(root, run_id):
    relative_path(run_id)
    if "/" in run_id:
        raise ConfigError("invalid refinement invocation ID")
    layout = WorkspaceLayout.detect(root)
    request = json_file(layout.path(f".runtime/refinement/requests/{run_id}.json"))
    if request.get("schema") != REQUEST or request.get("schema_version") != 1 or request.get("run_id") != run_id:
        raise ConfigError("unsupported refinement invocation request")
    stable = validate_config(json_file(layout.path(".runtime/refinement/configurations/" + request["configuration_sha256"] + ".json")))
    if fingerprint(stable) != request["configuration_sha256"] or request["groups"] != stable["groups"]:
        raise ConfigError("refinement request/configuration binding changed")
    if list(select_tools(request["tools"], has_reads=any(request["groups"].values()))) != request["selected"]:
        raise ConfigError("refinement request has contradictory tool selection")
    return request


def ensure_plan(root):
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2:
        return
    plan = layout.path(".run_all/plan.tsv")
    with plan.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields, rows = list(reader.fieldnames or []), list(reader)
    if fields != ["unit_id", "command_relpath", "detail_log_relpath"]:
        raise ConfigError("cannot extend an unsupported execution plan")
    ids = [row["unit_id"] for row in rows]
    if "degap_gapfill" in ids:
        raise ConfigError("legacy post-LGZ DEGAP plan requires explicit migration before refinement append")
    # Test/custom plans without an LGZ finalizer are not silently expanded.
    if "finalize_evidence" not in ids:
        return
    expected = {"unit_id": UNIT, "command_relpath": COMMAND, "detail_log_relpath": ".runtime/logs/run_all.log"}
    script = layout.path(COMMAND)
    if script.exists() and (script.is_symlink() or script.read_text() != SCRIPT):
        raise ConfigError("refinement command was customized; refusing to overwrite it")
    script.parent.mkdir(parents=True, exist_ok=True)
    if not script.exists():
        with script.open("x", encoding="utf-8") as stream:
            stream.write(SCRIPT)
        script.chmod(0o755)
    if UNIT in ids:
        if (ids.count(UNIT) != 1 or rows[ids.index(UNIT)] != expected
                or ids.index(UNIT) != ids.index("finalize_evidence") + 1):
            raise ConfigError("refinement execution-plan placement was customized")
        return
    before = plan.read_bytes()
    backup = layout.path(".runtime/refinement/plans/" + sha256_file(plan) + ".tsv")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_bytes(before)
    rows.insert(ids.index("finalize_evidence") + 1, expected)
    temporary = plan.with_suffix(".refinement.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, plan)
