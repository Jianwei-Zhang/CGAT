"""Reuse only complete, content-verified refinement publications/staging results.

Missing or changed artifacts are not a cache hit. Completed native phase recovery
is handled separately by refinement_native_checkpoint.py; this module never treats
an orphan native directory, a zero exit code or a timestamp as completion proof.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re

try:
    from workspace_layout import TOOL_DIRECTORIES, workspace_join
    from post_lgz_degap import digest
    from refinement_tools import load_lock, validate_runtime, fingerprint
    from refinement_recipes import select_reads
    from refinement_degap import ADAPTER_FILES as DEGAP_FILES
    from refinement_native import ADAPTER_FILES as NATIVE_FILES
except ModuleNotFoundError:
    from .workspace_layout import TOOL_DIRECTORIES, workspace_join
    from .post_lgz_degap import digest
    from .refinement_tools import load_lock, validate_runtime, fingerprint
    from .refinement_recipes import select_reads
    from .refinement_degap import ADAPTER_FILES as DEGAP_FILES
    from .refinement_native import ADAPTER_FILES as NATIVE_FILES


def checked_artifact(root, relative, expected):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return False
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        return False
    return digest(path) == expected


def validate_candidate(root, tool, groups, directory, runtime, lock):
    try:
        provenance_file = directory / "provenance.json"
        if provenance_file.is_symlink() or not provenance_file.resolve().is_relative_to(root):
            return None
        provenance = json.loads(provenance_file.read_text())
        if provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1 or provenance.get("tool") != tool:
            return None
        run_id = provenance.get("run_id")
        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
            return None
        marker = root / "04_refinement" / TOOL_DIRECTORIES[tool] / "02_jobs" / run_id / "invocation.json"
        state = json.loads(marker.read_text())
        if digest(provenance_file) != state.get("provenance_sha256"):
            return None
        if provenance.get("status") not in {"completed", "completed_zero_accepted", "native_no_candidates", "native_no_eligible_gaps", "native_no_eligible_flanks", "native_no_remaining_gaps"}:
            return None
        execution = provenance["execution"]
        if (state.get("status") not in {"staged", "published"} or state.get("tool") != tool or state.get("run_id") != run_id
                or execution.get("status") != "success" or execution.get("tool") != tool or execution.get("run_id") != run_id):
            return None
        recipe = execution["recipe"]
        if fingerprint(recipe) != execution.get("recipe_sha256") or state.get("recipe_sha256") != execution["recipe_sha256"]:
            return None
        definition = lock["tools"][tool]
        if (recipe.get("name", recipe.get("schema")) != definition["recipe"]
                or recipe.get("revision") != definition["revision"] or recipe.get("runtime_sha256") != fingerprint(runtime)):
            return None
        names = DEGAP_FILES if tool == "degap" else NATIVE_FILES
        if set(recipe.get("adapter_sources", {})) != set(names):
            return None
        for name in names:
            if digest(Path(__file__).parent / name) != recipe["adapter_sources"][name]:
                return None
        baseline_path = workspace_join(root, "metadata/grt_final_path.json")
        baseline = json.loads(baseline_path.read_text())
        if (digest(baseline_path) != recipe.get("baseline_final_path_sha256")
                or digest(workspace_join(root, baseline["q4_relpath"])) != recipe.get("baseline_sha256")):
            return None
        selection = select_reads(tool, groups)["selected"]
        requested = [(kind, path) for kind in ("hifi", "ont") for path in selection[kind]]
        saved = recipe.get("reads", [])
        if requested != [(row["technology"], row["path"]) for row in saved]:
            return None
        for row in saved:
            if row.get("not_consumed"):
                if execution.get("native_executed") is not False or not Path(row["path"]).is_file():
                    return None
            elif digest(Path(row["path"])) != row.get("sha256"):
                return None
        required = {"assembly.fa", "final_path.json", "sources.tsv", "remaining_gaps.tsv"}
        if set(provenance.get("artifacts", {})) != required:
            return None
        if not all(checked_artifact(directory, path, sha) for path, sha in provenance["artifacts"].items()):
            return None
        artifacts = execution.get("artifacts")
        if not isinstance(artifacts, dict) or not artifacts or not all(checked_artifact(root, path, sha) for path, sha in artifacts.items()):
            return None
        with (directory / "sources.tsv").open(newline="") as stream:
            sources = list(csv.DictReader(stream, delimiter="\t"))
        sources += provenance.get("trace_sources", [])
        if not recipe.get("baseline_source_files"):
            return None
        sources += recipe["baseline_source_files"]
        for source in sources:
            if source["path_scope"] == "workspace":
                path = workspace_join(root, source["fasta_path"])
            elif source["path_scope"] == "external" and Path(source["fasta_path"]).is_absolute():
                path = Path(source["fasta_path"])
            else:
                return None
            if digest(path) != source["fasta_sha256"]:
                return None
        final = json.loads((directory / "final_path.json").read_text())
        if (final.get("schema") != "cgat.refined-final-path" or final.get("schema_version") != 1 or final.get("tool") != tool
                or final.get("recipe_sha256") != execution["recipe_sha256"] or final.get("baseline") != provenance["baseline"]):
            return None
        return {"tool": tool, "run_id": run_id, "staging": str(directory), "provenance": provenance, "cache_hit": True}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def find_completed(root, tool, groups):
    root = Path(root).resolve()
    code = TOOL_DIRECTORIES[tool]
    published = root / "05_final" / code
    candidates = ([published] if (published / "provenance.json").is_file() else [])
    candidates += [path.parent for path in sorted((root / ".runtime/refinement" / code).glob("*/final/provenance.json"))]
    if not candidates:
        return None
    lock = load_lock()
    runtime = validate_runtime(lock=lock, tool=tool)
    # Prefer the already published matching result; otherwise choose a stable
    # matching receipt. Never rank by gap count, genome size or apparent quality.
    for directory in candidates:
        result = validate_candidate(root, tool, groups, directory, runtime, lock)
        if result:
            result["already_published"] = False
            if directory == published:
                try:
                    try:
                        from refinement_commit import current_publication
                    except ModuleNotFoundError:
                        from .refinement_commit import current_publication
                    receipt = current_publication(root, tool)
                    result["already_published"] = receipt is not None and receipt["run_id"] == result["run_id"]
                except (OSError, ValueError, KeyError):
                    # Still a verified native/admission result, but not a final
                    # three-area publication. The runner must recover/publish.
                    pass
            return result
    return None
