"""Sequential, failure-isolated staging for one post-LGZ refinement batch.

The caller must hold the workspace lock and validate the LGZ completion receipt.
The batch does not publish private staging or pretend that App delivery is done.
It returns verified staged results so a separate publication transaction can
commit successful branches even when another native tool fails.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re
import uuid

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join
    from post_lgz_degap import atomic_json, digest
    from refinement_tools import ToolError
    from refinement_recipes import select_tools, select_reads
    from refinement_native import stage_refinement
    from refinement_cache import find_completed
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join
    from .post_lgz_degap import atomic_json, digest
    from .refinement_tools import ToolError
    from .refinement_recipes import select_tools, select_reads
    from .refinement_native import stage_refinement
    from .refinement_cache import find_completed


def baseline_seal(root):
    final_path = workspace_join(root, "metadata/grt_final_path.json")
    final_bytes = final_path.read_bytes()
    payload = json.loads(final_bytes)
    locator = workspace_join(root, "metadata/source_seq_locator.tsv")
    locator_bytes = locator.read_bytes()
    paths = {workspace_join(root, payload["q4_relpath"])}
    for row in csv.DictReader(io.StringIO(locator_bytes.decode("utf-8")), delimiter="\t"):
        paths.add(workspace_join(root, row["fasta_relpath"]))
    sealed = {str(path): digest(path) for path in sorted(paths)}
    sealed.update({str(final_path): hashlib.sha256(final_bytes).hexdigest(), str(locator): hashlib.sha256(locator_bytes).hexdigest()})
    check_seal(sealed)
    return sealed


def check_seal(seal):
    for path, expected in seal.items():
        if digest(Path(path)) != expected:
            raise ToolError(f"shared refinement input changed: {path}")


def read_bindings(recipe):
    rows = recipe.get("reads", [])
    if not isinstance(rows, list):
        raise ToolError("refinement recipe has an invalid reads binding")
    result = {}
    for row in rows:
        if row.get("not_consumed"):
            continue
        path, sha = row.get("path"), row.get("sha256")
        if not isinstance(path, str) or not Path(path).is_absolute() or not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ToolError("refinement recipe lacks a content-bound reads identity")
        if path in result and result[path] != sha:
            raise ToolError("refinement recipe has contradictory reads identities")
        result[path] = sha
    return result


def execute_batch(root, groups, threads, *, tools=None, batch_id=None):
    root = Path(root).resolve()
    if WorkspaceLayout.detect(root).version != 2:
        raise ToolError("refinement batch requires explicit migration to the numbered workspace")
    selected = select_tools(tools, has_reads=any(groups.values()))
    if type(threads) is not int or threads < 1:
        raise ToolError("refinement threads must be positive")
    batch_id = batch_id or uuid.uuid4().hex
    if not re.fullmatch(r"[0-9a-f]{32}", batch_id):
        raise ToolError("invalid refinement batch identity")
    target = root / ".runtime/refinement/batches" / (batch_id + ".json")
    if target.exists() or target.is_symlink():
        raise ToolError("refinement batch already exists; resume requires content validation")
    # No tools selected does not fabricate a refined result or require new reads.
    if not selected:
        batch = {"schema": "cgat.refinement-batch", "schema_version": 1, "batch_id": batch_id,
                 "status": "not_requested", "tools": {}, "exit_code": 0}
        atomic_json(target, batch)
        return {"batch": batch, "staged_results": {}, "exit_code": 0}
    for tool in selected:
        select_reads(tool, groups)
    sealed = baseline_seal(root)
    shared_reads, staged = {}, {}
    batch = {"schema": "cgat.refinement-batch", "schema_version": 1, "batch_id": batch_id,
             "status": "running", "baseline_inputs": sealed, "threads": threads,
             "tools": {tool: {"status": "pending"} for tool in selected}, "exit_code": None}
    atomic_json(target, batch)
    invalidated = False
    try:
        for tool in selected:
            record = batch["tools"][tool]
            try:
                check_seal(sealed)
                check_seal(shared_reads)
            except (OSError, ValueError) as error:
                invalidated = True
                record.update(status="invalidated", error=str(error))
                break
            attempt = uuid.uuid4().hex
            record.update(status="running", run_id=attempt)
            atomic_json(target, batch)
            result = None
            try:
                result = find_completed(root, tool, groups)
                if result is None:
                    result = stage_refinement(root, tool, groups, threads, run_id=attempt)
                else:
                    record["reused_from"] = result["run_id"]
                    record["requested_reads"] = select_reads(tool, groups)
                record.update(status="staged", run_id=result["run_id"], final_staging=result["staging"])
                staged[tool] = result
            except Exception as error:
                record.update(status="failed", error_type=type(error).__name__, error=str(error))
            recipe_path = root / "04_refinement" / TOOL_DIRECTORIES[tool] / "01_inputs" / attempt / "recipe.json"
            try:
                # Failed native attempts still attest which reads were actually
                # used. Their failure must not make later tools switch input bytes.
                if result is not None:
                    recipe = result["provenance"]["execution"]["recipe"]
                else:
                    recipe = json.loads(recipe_path.read_text()) if recipe_path.is_file() else {"reads": []}
                for path, sha in read_bindings(recipe).items():
                    if path in shared_reads and shared_reads[path] != sha:
                        raise ToolError("tools consumed different bytes for the same selected reads input")
                    shared_reads[path] = sha
                check_seal(sealed)
                check_seal(shared_reads)
            except (OSError, ValueError, KeyError) as error:
                invalidated = True
                record.update(status="invalidated", error=str(error))
                break
            atomic_json(target, batch)
        if invalidated:
            for record in batch["tools"].values():
                if record["status"] in {"pending", "running", "staged"}:
                    record["status"] = "invalidated"
            staged.clear()
            batch.update(status="invalidated", exit_code=1)
        else:
            failed = any(record["status"] == "failed" for record in batch["tools"].values())
            batch.update(status="partial_failure" if failed and staged else "failed" if failed else "staged", exit_code=int(failed))
        batch["reads_inputs"] = shared_reads
        atomic_json(target, batch)
        return {"batch": batch, "staged_results": staged, "exit_code": batch["exit_code"]}
    except BaseException:
        for record in batch["tools"].values():
            if record["status"] == "running":
                record["status"] = "interrupted"
            elif record["status"] == "pending":
                record["status"] = "not_started"
        batch.update(status="interrupted", exit_code=130)
        atomic_json(target, batch)
        raise
