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
    from refinement_tools import ToolError, fingerprint
    from refinement_recipes import select_tools, select_reads
    from refinement_native import stage_refinement
    from refinement_cache import find_completed
    from refinement_presets import sync_workspace
    from refinement_reports import build_tool_report, build_failure_report
    from refinement_overview import render_overview
    from refinement_source_evidence import build as build_source_evidence
    from refinement_source_marks import annotation_inputs
    from degap_manual_catalog import content_digest
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, workspace_join
    from .post_lgz_degap import atomic_json, digest
    from .refinement_tools import ToolError, fingerprint
    from .refinement_recipes import select_tools, select_reads
    from .refinement_native import stage_refinement
    from .refinement_cache import find_completed
    from .refinement_presets import sync_workspace
    from .refinement_reports import build_tool_report, build_failure_report
    from .refinement_overview import render_overview
    from .refinement_source_evidence import build as build_source_evidence
    from .refinement_source_marks import annotation_inputs
    from .degap_manual_catalog import content_digest


def baseline_seal(root):
    final_path = workspace_join(root, "metadata/grt_final_path.json")
    final_bytes = final_path.read_bytes()
    payload = json.loads(final_bytes)
    locator = workspace_join(root, "metadata/source_seq_locator.tsv")
    locator_bytes = locator.read_bytes()
    paths = {workspace_join(root, payload["q4_relpath"])}
    for row in csv.DictReader(io.StringIO(locator_bytes.decode("utf-8")), delimiter="\t"):
        paths.add(workspace_join(root, row["fasta_relpath"]))
    reference = workspace_join(root, "metadata/reference.tsv")
    if reference.is_file():
        with reference.open(newline="", encoding="utf-8") as stream:
            references = list(csv.DictReader(stream, delimiter="\t"))
        if len(references) != 1:
            raise ToolError("shared refinement reference catalog is ambiguous")
        paths.update((reference, workspace_join(root, references[0]["fasta_relpath"])))
    for name in ("metadata/prepare_options.tsv", "metadata/annotation_library_snapshot.json", "tel/rules.tsv", "cen/reference.tsv", "cen/library.fa"):
        path = workspace_join(root, name)
        if path.exists() or path.is_symlink():
            paths.add(path)
    paths.update(row["path"] for row in annotation_inputs(root, [row["chr"] for row in payload.get("chromosomes", [])]))
    sealed = {str(path): content_digest(path) for path in sorted(paths)}
    sealed.update({str(final_path): hashlib.sha256(final_bytes).hexdigest(), str(locator): hashlib.sha256(locator_bytes).hexdigest()})
    check_seal(sealed)
    return sealed


def check_seal(seal):
    for path, expected in seal.items():
        if content_digest(Path(path)) != expected:
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
            record.update(status="running", run_id=attempt, phase="native")
            atomic_json(target, batch)
            result = None
            try:
                if tool == "degap":
                    sync_workspace(root)
                result = find_completed(root, tool, groups)
                if result is None:
                    result = stage_refinement(root, tool, groups, threads, run_id=attempt)
                else:
                    record["reused_from"] = result["run_id"]
                    record["requested_reads"] = select_reads(tool, groups)
                record.update(status="staged", run_id=result["run_id"], final_staging=result["staging"])
                staged[tool] = result
                execution = result.get("provenance", {}).get("execution", {})
                record.update(phase="source_evidence", native_status="staged", native_reused=execution.get("native_reused", False),
                              native_origin=execution.get("native_origin"))
                atomic_json(target, batch)
                result["source_evidence"] = build_source_evidence(root, result, threads)
                record["source_evidence"] = result["source_evidence"]
                record["phase"] = "report"
                record["report"] = build_tool_report(root, result)
                record["phase"] = "staged"
            except Exception as error:
                record.update(status="failed", error_type=type(error).__name__, error=str(error))
                if record["phase"] == "native":
                    marker = root / "04_refinement" / TOOL_DIRECTORIES[tool] / "02_jobs" / record["run_id"] / "invocation.json"
                    try:
                        if marker.is_symlink():
                            raise ValueError("invalid invocation marker")
                        state = json.loads(marker.read_text())
                        if state.get("native_status") == "success" and state.get("phase") == "admission":
                            record.update(phase="admission", native_status="success", native_reused=state.get("native_reused", False),
                                          native_origin=state.get("native_origin"))
                    except (OSError, ValueError, TypeError):
                        pass
                try:
                    record["report"] = build_failure_report(root, tool, record["run_id"], error, phase=record["phase"])
                except Exception as report_error:
                    record["report_error"] = str(report_error)
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
            ready = any(record["status"] == "staged" for record in batch["tools"].values())
            batch.update(status="partial_failure" if failed and ready else "failed" if failed else "staged", exit_code=int(failed))
        batch["reads_inputs"] = shared_reads
        try:
            batch["overview"] = render_overview(root, batch, staged)
        except Exception as error:
            batch["overview_error"] = {"type": type(error).__name__, "message": str(error)}
            if batch["exit_code"] == 0:
                batch["status"] = "report_failed"
            batch["exit_code"] = 1
        atomic_json(target, batch)
        return {"batch": batch, "staged_results": staged, "exit_code": batch["exit_code"]}
    except BaseException as error:
        for record in batch["tools"].values():
            if record["status"] == "running":
                record["status"] = "interrupted"
            elif record["status"] == "pending":
                record["status"] = "not_started"
        batch.update(status="interrupted", exit_code=128 + getattr(error, "signal_number", 2))
        atomic_json(target, batch)
        raise


def publish_batch(root, lock, batch_result):
    """Publish every successful branch with the real full/light App validator.

    This does not hold/reacquire a second lock or rerun native tools. The caller
    owns the existing outer lock for execution, archive creation and publication.
    """
    try:
        from refinement_commit import layout_and_lock, publish_result, current_publication
        from refinement_delivery import build_delivery, validate_delivery, delivery_generation
    except ModuleNotFoundError:
        from .refinement_commit import layout_and_lock, publish_result, current_publication
        from .refinement_delivery import build_delivery, validate_delivery, delivery_generation
    layout = layout_and_lock(root, lock)
    batch = batch_result["batch"]
    if not batch["tools"]:
        return batch_result
    results = batch_result["staged_results"]
    if batch["status"] == "invalidated":
        raise ToolError("shared-input-invalidated refinement results cannot be published")
    for tool, result in results.items():
        record = batch["tools"][tool]
        if record["status"] not in {"staged", "published"}:
            continue
        try:
            previous = current_publication(layout.root, tool)
            if (previous and previous["run_id"] == result["run_id"]
                    and previous["areas"]["report"]["new"]["files"].get("manifest.json") == record["report"]["manifest_sha256"]
                    and previous["delivery_validation"].get("generation_sha256") == fingerprint(
                        delivery_generation(layout.root, result, record["report"]))):
                record.update(status="published", publication_transaction=previous["transaction"], phase="published")
                continue
            record["phase"] = "app_delivery"
            delivery = build_delivery(layout.root, result, record["report"])
            record["phase"] = "publication"
            receipt = publish_result(layout.root, lock, result, record["report"], delivery, validate_delivery)
            record.update(status="published", publication_transaction=receipt["transaction"], phase="published")
        except Exception as error:
            record.update(status="failed", error_type=type(error).__name__, error=str(error))
        atomic_json(layout.path(f".runtime/refinement/batches/{batch['batch_id']}.json"), batch)
    failed = any(row["status"] != "published" for row in batch["tools"].values())
    success = any(row["status"] == "published" for row in batch["tools"].values())
    batch.update(status="partial_failure" if failed and success else "failed" if failed else "published", exit_code=int(failed))
    try:
        batch["overview"] = render_overview(layout.root, batch, results)
    except Exception as error:
        batch.update(overview_error={"type": type(error).__name__, "message": str(error)}, exit_code=1)
        if not failed:
            batch["status"] = "report_failed"
    atomic_json(layout.path(f".runtime/refinement/batches/{batch['batch_id']}.json"), batch)
    batch_result["exit_code"] = batch["exit_code"]
    return batch_result
