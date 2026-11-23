"""DEGAP adapter for the multi-tool refinement runner (no scheduler submission).

Stages a real sourced Final Path publication. The caller owns the workspace lock,
resume selection, per-tool error isolation and final/report/App publication.
"""
from __future__ import annotations

from dataclasses import replace
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import uuid
import time
from datetime import datetime, timezone

try:
    from workspace_layout import automatic_dir, WorkspaceLayout, workspace_join
    from post_lgz_degap import IndexedFasta, check_environment, digest, stat_key, atomic_json, read_groups
    from refinement_path import identity, source_blocks, PathError
    from refinement_sources import FastaCatalog
    from refinement_admission import degap_proposal, degap_family_proposal, exclude_conflicts, preserve_joint_sources
    from refinement_publication import prepare_publication, verify_baseline
    from refinement_tools import validate_runtime, load_lock, verify_directory_links
    from refinement_recipes import make_invocation
    from refinement_presets import effective as effective_degap
    from refinement_degap_units import ENGINE_REVISION as PIN, FAMILY, family_result
    from refinement_native_checkpoint import execute as execute_native, validate_native_job_summary
except ModuleNotFoundError:
    from .workspace_layout import automatic_dir, WorkspaceLayout, workspace_join
    from .post_lgz_degap import IndexedFasta, check_environment, digest, stat_key, atomic_json, read_groups
    from .refinement_path import identity, source_blocks, PathError
    from .refinement_sources import FastaCatalog
    from .refinement_admission import degap_proposal, degap_family_proposal, exclude_conflicts, preserve_joint_sources
    from .refinement_publication import prepare_publication, verify_baseline
    from .refinement_tools import validate_runtime, load_lock, verify_directory_links
    from .refinement_recipes import make_invocation
    from .refinement_presets import effective as effective_degap
    from .refinement_degap_units import ENGINE_REVISION as PIN, FAMILY, family_result
    from .refinement_native_checkpoint import execute as execute_native, validate_native_job_summary

RECIPE = "cgat.degap.family-junction.v3"
ADAPTER_FILES = ("refinement_degap.py", "refinement_admission.py", "refinement_path.py",
                 "refinement_sources.py", "refinement_publication.py", "refinement_tools.py",
                 "refinement_recipes.py", "refinement_presets.py", "refinement_native_trace.py", "refinement_native_checkpoint.py",
                 "refinement_native_units.py", "refinement_native_runner.py", "refinement_degap_units.py", "refinement_tgs_units.py", "refinement_lr_units.py")


def verify_engine(engine_root: Path) -> dict:
    manifest = json.loads((engine_root / "SOURCE.json").read_text())
    if manifest.get("revision") != PIN or manifest.get("schema") != "gpm.degap.runtime.v1":
        raise PathError("DEGAP source revision does not match the pinned recipe")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise PathError("DEGAP source content manifest is missing")
    for name, expected in files.items():
        if Path(name).is_absolute() or ".." in Path(name).parts or digest(engine_root / name) != expected:
            raise PathError(f"DEGAP pinned source differs: {name}")
    actual_python = {p.relative_to(engine_root).as_posix() for p in engine_root.rglob("*.py")}
    if actual_python != {name for name in files if name.endswith(".py")}:
        raise PathError("DEGAP runtime contains unpinned Python source")
    return manifest


def materialize_patches(edits, catalog, accepted_dir, *, tool="degap"):
    """Retain only inserted sequence in the permanent CGAT source dataset.

    Native full candidates remain untouched in 03_native; the evidence retains
    their exact original source slices. No chromosome is relabeled as a patch.
    """
    patch_edits = [edit for edit in edits if edit.replacement]
    if not patch_edits:
        return edits
    patch_file = accepted_dir / "patches.fa"
    dataset = "cgat_refinement_" + tool + "_" + accepted_dir.name
    if any(name == dataset for name, _ in catalog.sources):
        raise PathError("refinement dataset identity collides with an original dataset")
    lengths = {}
    with patch_file.open("xb") as stream:
        for edit in patch_edits:
            stream.write(b">" + edit.edit_id.encode("ascii") + b"\n")
            length = 0
            for block in source_blocks(edit.replacement, catalog):
                stream.write(block)
                length += len(block)
            stream.write(b"\n")
            lengths[edit.edit_id] = length
    result = []
    for edit in edits:
        if edit.replacement:
            catalog.register(dataset, edit.edit_id, patch_file, origin="refinement:" + tool)
            evidence = {**edit.evidence, "native_source": edit.replacement}
            replacement = {"dataset": dataset, "contig": edit.edit_id, "start": 1,
                           "end": lengths[edit.edit_id], "orientation": "+"}
            result.append(replace(edit, replacement=replacement, evidence=evidence))
        else:
            result.append(edit)
    return result


def _stage_degap(root: Path, groups: dict, threads: int, *, run_id: str) -> dict:
    stage_started = time.monotonic()
    stage_started_at = datetime.now(timezone.utc).isoformat()
    """Execute the pinned tool and stage final artifacts, or propagate failure.

    No success is returned until source reconstruction has finished. Input/output
    receipts are suitable for the outer runner to validate before cache reuse.
    """
    root = root.resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2:
        raise PathError("post-LGZ refinement requires explicit migration to the numbered workspace")
    if type(threads) is not int or threads < 1:
        raise PathError("refinement thread budget must be positive")
    run_id = run_id or uuid.uuid4().hex
    if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        raise PathError("invalid refinement run identity")
    groups = read_groups({"schema_version": 2, "purpose": "post_lgz_degap_v1", **groups})
    check_environment(root, groups["hifi"] + groups["ont"])
    tools_root = Path(__file__).resolve().parent
    engine_root = tools_root / "degap_core"
    engine_manifest = verify_engine(engine_root)
    lock = load_lock()
    runtime = validate_runtime(lock=lock, tool="degap")
    paths = {name: layout.path(f"04_refinement/01_degap/{name}/{run_id}")
             for name in ("01_inputs", "02_jobs", "03_native", "04_accepted", "05_report")}
    if paths["03_native"].exists() or paths["03_native"].is_symlink():
        raise PathError("native attempt directory already exists; validated resume must be explicit")
    # Native program creates 03_native itself. No previously completed attempt is overwritten.
    for name in ("01_inputs", "02_jobs", "04_accepted", "05_report"):
        paths[name].mkdir(parents=True, exist_ok=False)
    catalog = FastaCatalog(root, root / ".runtime/refinement/01_degap" / run_id / "indexes")
    catalog.load_workspace()
    baseline_path = workspace_join(root, "metadata/grt_final_path.json")
    baseline_identity = stat_key(baseline_path)
    baseline_digest = digest(baseline_path)
    baseline = json.loads(baseline_path.read_text())
    baseline_fasta = layout.path(baseline["q4_relpath"])
    fasta = IndexedFasta(baseline_fasta, catalog.index_directory / "baseline.fa")
    gaps = verify_baseline(baseline, catalog, fasta)
    if stat_key(baseline_path) != baseline_identity:
        raise PathError("baseline Final Path changed during validation")
    identities = {baseline_path: baseline_identity, baseline_fasta: stat_key(baseline_fasta)}
    reads_manifest = []
    for kind, reads in groups.items():
        for raw in reads:
            path = Path(raw)
            if not gaps:
                if not path.is_file():
                    raise PathError("requested reads input is missing")
                reads_manifest.append({"technology": kind, "path": str(path), "not_consumed": True,
                                       "reason": "no_remaining_gaps"})
                continue
            before = stat_key(path)
            sha256 = digest(path)
            if stat_key(path) != before:
                raise PathError("reads changed while fingerprinting")
            identities[path] = before
            reads_manifest.append({"technology": kind, "path": str(path), "sha256": sha256})
    parameters = effective_degap(root)
    recipe = {"schema": RECIPE, "tool": "degap", "extension_parameters": parameters, "version": lock["tools"]["degap"]["version"], "revision": PIN,
              "engine_manifest_sha256": identity(engine_manifest), "runtime_sha256": identity(runtime),
              "tool_lock_sha256": identity(lock), "reads": reads_manifest,
              "baseline_source_files": catalog.baseline_bindings(), "baseline_sha256": digest(baseline_fasta), "baseline_final_path_sha256": baseline_digest,
              "adapter_sources": {name: digest(tools_root / name) for name in ADAPTER_FILES}}
    atomic_json(paths["01_inputs"] / "recipe.json", recipe)
    native_invocation = make_invocation("degap", baseline_fasta, groups, paths["03_native"], threads,
                                        runtime=runtime, lock=lock, degap_parameters=parameters)
    command = list(native_invocation.command)
    for relative in engine_manifest["files"]:
        path = engine_root / relative
        identities[path] = stat_key(path)
    for group in (runtime.get("tools", {}), runtime.get("dependencies", {})):
        for record in group.values():
            for relative in record.get("files_sha256", {}):
                # Source-distributed tool paths are relative to their source
                # tree, not prefix. DEGAP uses only conda scientific dependencies.
                if record.get("name"):
                    path = Path(sys.prefix) / relative
                    identities[path] = stat_key(path)
    invocation = {"tool": "degap", "run_id": run_id, "command": command, "threads": threads,
                  "recipe_sha256": identity(recipe), "status": "running", "timing": {"started_at": stage_started_at}}
    atomic_json(paths["02_jobs"] / "invocation.json", invocation)
    native_artifacts, native_summary, completion = {}, {}, None
    if gaps:
        def verify_inputs():
            verify_directory_links(runtime)
            catalog.verify_unchanged()
            if any(stat_key(path) != expected for path, expected in identities.items()):
                raise PathError("baseline, reads, runtime or native evidence changed during refinement")
        input_hashes = {row["path"]: row["sha256"] for row in reads_manifest}
        input_hashes[str(baseline_fasta)] = recipe["baseline_sha256"]
        completion = execute_native(root, native_invocation, recipe, paths, invocation, identities, verify_inputs,
                                    chromosomes=set(fasta.records), parameters=lock["tools"]["degap"].get("parameters", {}),
                                    input_hashes=input_hashes, prepared_files=[path for values in groups.values() for path in values])
        native_artifacts.update(completion["result"]["artifacts"])
        native_summary = completion["result"]["native_assembly"]
        native_report = paths["03_native"] / "03.gap_filling/gap_filling_results.json"
        native_identity = stat_key(native_report)
        native_digest = digest(native_report)
        if native_artifacts.get(native_report.relative_to(root).as_posix()) != native_digest:
            raise PathError("DEGAP report changed after native completion")
        rows = json.loads(native_report.read_text())["gaps"]
        native_jobs = completion["result"]["native_jobs"]
        atomic_json(paths["02_jobs"] / "native_jobs.json", native_jobs)
        jobs_file = paths["02_jobs"] / "native_jobs.json"
        native_artifacts[jobs_file.relative_to(root).as_posix()] = digest(jobs_file)
    else:
        # The successful no-op is explicit and content-bound, not a failed-tool fallback.
        native_report = paths["02_jobs"] / "no_gaps.json"
        atomic_json(native_report, {"reason": "no_remaining_gaps", "baseline_sha256": recipe["baseline_sha256"]})
        rows = []
        native_identity = stat_key(native_report)
        native_digest = digest(native_report)
    identities.setdefault(native_report, native_identity)
    edits, rejected, candidate_artifacts = [], [], {}
    for index, row in enumerate(rows):
        covered = [gap.gap_id for gap in gaps if gap.chromosome == row.get("chromosome")
                   and type(row.get("gap_start")) is int and type(row.get("gap_end")) is int
                   and row["gap_start"] - 1 <= gap.start and gap.end <= row["gap_end"]]
        rejection = {"native_job": f"{native_report.relative_to(root)}#gap-{index}", "gap_ids": covered}
        if row.get("filled") is not True:
            # Unfilled is not a rejected candidate; preserve the native record separately.
            continue
        raw = row.get("final_sequence_file")
        if not isinstance(raw, str) or not raw:
            rejected.append({**rejection, "reason": "missing_native_candidate"})
            continue
        candidate_path = Path(raw)
        if not candidate_path.is_absolute():
            candidate_path = paths["03_native"] / candidate_path
        candidate_path = candidate_path.resolve()
        if not candidate_path.is_relative_to(paths["03_native"].resolve()) or not candidate_path.is_file():
            rejected.append({**rejection, "reason": "candidate_outside_native_attempt_or_missing"})
            continue
        before = stat_key(candidate_path)
        sha256 = digest(candidate_path)
        if native_artifacts.get(candidate_path.relative_to(root).as_posix()) != sha256:
            raise PathError("DEGAP candidate changed or was not sealed at native completion")
        dataset = f"native_degap_{run_id}_{index}"
        evidence_args = {"source_dataset": dataset, "native_job": rejection["native_job"], "artifact_sha256": sha256}
        bidirectional = row.get("report_direction") == "bidirectional"
        if bidirectional and row.get("junction") is not None:
            manifest_file = candidate_path.parent / FAMILY
            if native_artifacts.get(manifest_file.relative_to(root).as_posix()) != digest(manifest_file):
                raise PathError("DEGAP junction is not tied to its sealed family result")
            manifest = family_result(candidate_path.parent)
            full_path = candidate_path.parent / manifest["final_sequence"]
            full_before = stat_key(full_path)
            if (native_artifacts.get(full_path.relative_to(root).as_posix()) != digest(full_path)
                    or row["junction"] != manifest["junction"]):
                raise PathError("DEGAP full candidate changed after native completion")
            full = IndexedFasta(full_path, catalog.index_directory / f"full-candidate-{index}.fa")
            with candidate_path.open("rb") as file:
                header = file.readline(65536)
                empty = header.startswith(b">") and header.endswith(b"\n") and not file.read(1)
            candidate = None if empty else IndexedFasta(candidate_path, catalog.index_directory / f"candidate-{index}.fa")
            edit, reason = degap_family_proposal(row, fasta, candidate, full, gaps, **evidence_args,
                                                **lock["tools"]["degap"]["parameters"])
            if stat_key(full_path) != full_before:
                raise PathError("DEGAP full candidate changed during admission")
        else:
            candidate = IndexedFasta(candidate_path, catalog.index_directory / f"candidate-{index}.fa")
            # A full-family result without a junction uses the same exact-anchor
            # proof, with the new explicit 0-based inclusive replace coordinates.
            placement = ({**row, "replace_start": row["replace_start"] + 1,
                          "replace_end": row["replace_end"] + 1}
                         if bidirectional and type(row.get("replace_start")) is int
                         and type(row.get("replace_end")) is int else row)
            edit, reason = degap_proposal(placement, fasta, candidate, gaps, **evidence_args)
        if stat_key(candidate_path) != before:
            raise PathError("native candidate changed during admission")
        candidate_artifacts[candidate_path.relative_to(root).as_posix()] = sha256
        if edit:
            if edit.replacement:
                catalog.register(dataset, edit.replacement["contig"], candidate_path, origin="native:degap")
            edits.append(edit)
        else:
            rejected.append({**rejection, "reason": reason})
    edits, conflicting = exclude_conflicts(edits)
    rejected += conflicting
    edits, ambiguous = preserve_joint_sources(edits, fasta, catalog, gaps)
    rejected += ambiguous
    edits = materialize_patches(edits, catalog, paths["04_accepted"])
    verify_directory_links(runtime)
    if any(stat_key(path) != expected for path, expected in identities.items()):
        raise PathError("baseline or reads changed during refinement")
    catalog.verify_unchanged()
    invocation["timing"].update(before_publication_seconds=time.monotonic() - stage_started,
                                admission_finished_at=datetime.now(timezone.utc).isoformat())
    execution = {**invocation, "status": "success", "baseline_sha256": recipe["baseline_sha256"],
                 "native_executed": bool(gaps) and not completion["reused"], "native_outcome": "completed" if gaps else "no_remaining_gaps",
                 "skip_reason": None if gaps else "no_remaining_gaps",
                 "recipe": recipe, "native_assembly": native_summary,
                 "artifacts": {native_report.relative_to(root).as_posix(): native_digest, **native_artifacts, **candidate_artifacts}}
    atomic_json(paths["02_jobs"] / "execution.json", execution)
    staging = root / ".runtime/refinement/01_degap" / run_id / "final"
    provenance = prepare_publication(staging, baseline, baseline_fasta, catalog, edits, execution, rejected)
    verify_directory_links(runtime)
    if any(stat_key(path) != expected for path, expected in identities.items()):
        raise PathError("baseline, reads or native evidence changed during publication staging")
    atomic_json(paths["05_report"] / "report.json", provenance)
    atomic_json(paths["02_jobs"] / "invocation.json", {**invocation, "status": "staged", "native_status": "success",
                "provenance_sha256": digest(staging / "provenance.json")})
    return {"tool": "degap", "run_id": run_id, "staging": str(staging), "provenance": provenance}



def stage_degap(root: Path, groups: dict, threads: int, *, run_id: str | None = None) -> dict:
    run_id = run_id or uuid.uuid4().hex
    if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
        raise PathError("invalid refinement run identity")
    invocation_path = automatic_dir(root, 'degap') / "02_jobs" / run_id / "invocation.json"
    # Do not change an existing attempt, including its failure receipt.
    if invocation_path.parent.exists():
        raise PathError("refinement attempt already exists")
    try:
        return _stage_degap(root, groups, threads, run_id=run_id)
    except BaseException as error:
        if invocation_path.is_file():
            invocation = json.loads(invocation_path.read_text())
            invocation.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                              error_type=type(error).__name__, error=str(error))
            atomic_json(invocation_path, invocation)
        raise
