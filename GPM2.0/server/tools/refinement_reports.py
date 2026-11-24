"""Portable refinement reports with static CGAT pages and managed native views.

A report is not a publication receipt. It records the complete LGZ gap denominator
and labels staged, native and accepted results separately. No external JS, reads
FASTA, native genome or workstation-only hyperlink is needed to view the report.
"""
from __future__ import annotations

from collections import defaultdict
from bisect import bisect_right
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

try:
    from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
    from report_privacy import recipe_paths, hide_paths
    from refinement_tools import fingerprint
    import refinement_native_reports as native_reports
except ModuleNotFoundError:
    from .workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from .run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
    from .report_privacy import recipe_paths, hide_paths
    from .refinement_tools import fingerprint
    from . import refinement_native_reports as native_reports

SCHEMA = "cgat.refinement-report"
MAX_ASSET = 20 * 1024 * 1024
MAX_ASSETS_TOTAL = 200 * 1024 * 1024
TEXT_ENDINGS = (".json", ".log", ".tsv", ".paf", ".txt", ".agp", ".detail", ".gap_fill_detail", "_scaff_infos", ".name_map", "/info_filter2")
try:
    from render_refinement_report import (render_tool_pages, render_failure, retained_flanks, gap_anchor, PAGE_SIZE)
except ModuleNotFoundError:
    from .render_refinement_report import (render_tool_pages, render_failure, retained_flanks, gap_anchor, PAGE_SIZE)


class ReportError(ValueError):
    pass


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or Path(relative).is_absolute() or any(p in {".", ".."} for p in relative.split("/")):
        raise ReportError("report artifact is not a safe relative file")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents):
        raise ReportError("report artifact traverses a symlink or leaves its root")
    if not path.is_file():
        raise ReportError("report artifact is missing: " + relative)
    return path


def stat_key(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def read_bound(path, expected, *, limit=None):
    before = stat_key(path)
    if limit is not None and path.stat().st_size > limit:
        raise ReportError("report JSON exceeds supported metadata bound")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected or stat_key(path) != before:
        raise ReportError("report input changed: " + str(path))
    return data


def native_diagnostics(root, tool, run_id, execution):
    """Only known native diagnostic entrypoints; never recursive reads copying."""
    code = TOOL_DIRECTORIES[tool]
    base = Path(WorkspaceLayout.detect(root).relative(f"04_refinement/{code}"))
    origin = execution.get("native_origin")
    native_run = origin["run_id"] if origin else run_id
    native = base / "03_native" / native_run
    if origin and (not re.fullmatch(r"[0-9a-f]{32}", native_run) or origin.get("native_root") != native.as_posix()
                   or origin.get("receipt") != (base / "02_jobs" / native_run / "native_complete.json").as_posix()):
        raise ReportError("native origin does not identify this tool's owned completion")
    selected = dict(execution.get("artifacts", {}))
    if origin:
        receipt = safe_file(root, origin["receipt"])
        value = json.loads(read_bound(receipt, origin["receipt_sha256"], limit=128 * 1024 * 1024))
        checksum = value.pop("payload_sha256")
        if (checksum != fingerprint(value) or value.get("schema") != "cgat.native-refinement-completion"
                or value.get("schema_version") != 1 or value.get("status") != "completed"
                or value.get("run_id") != native_run or value.get("tool") != tool):
            raise ReportError("native origin completion receipt is invalid")
        for relative, sha in value["result"]["artifacts"].items():
            if relative in selected and selected[relative] != sha:
                raise ReportError("native origin artifact binding changed")
            selected[relative] = sha
        selected[origin["receipt"]] = origin["receipt_sha256"]
    def select(relative):
        file = safe_file(root, relative)
        sha = digest(file)
        if relative in selected and selected[relative] != sha:
            raise ReportError("native evidence changed before report generation: " + relative)
        selected[relative] = sha
        return file, sha
    log = (base / "02_jobs" / native_run / "native.log").as_posix()
    if (root / log).is_file():
        selected.setdefault(log, digest(safe_file(root, log)))
    if tool in {"quartet", "degap", "tgsgapcloser", "lrgapcloser"} and not origin:
        # Failed/interrupted attempts may contain completed units even though
        # no whole-native completion exists. Only named owned diagnostics.
        unit_base = base / "02_jobs" / native_run
        for name in ("native_launch.json", "native_substeps.json"):
            relative = (unit_base / name).as_posix()
            if (root / relative).exists():
                select(relative)
        for receipt in sorted((root / unit_base / "native_units").glob("*/unit_complete.json")):
            if not re.fullmatch(r"[0-9a-f]{64}", receipt.parent.name):
                continue
            for name in ("unit_complete.json", "producer.json", "output.paf", "stdout.paf", "stdout.fasta", "stderr.log", "gapclosed.fasta", "info_filter2"):
                file = receipt.parent / name
                if file.exists() or file.is_symlink():
                    select(file.relative_to(root).as_posix())
            if tool == "degap":
                for file in sorted((receipt.parent / "outputs").glob("*")):
                    if file.name in {"process.log", "run.stdout.log", "run.stderr.log"} or file.name.endswith(".final.fa"):
                        select(file.relative_to(root).as_posix())
    jobs, native_gaps = [], []
    if tool == "degap":
        gap_report = (native / "03.gap_filling/gap_filling_results.json").as_posix()
        if (root / gap_report).exists():
            select(gap_report)
            native_gaps = json.loads(read_bound(safe_file(root, gap_report), selected[gap_report], limit=128 * 1024 * 1024)).get("gaps", [])
        config = (native / "03.gap_filling/job_manager_config.json").as_posix()
        if (root / config).exists():
            file, sha = select(config)
            payload = json.loads(read_bound(file, sha, limit=MAX_ASSET))
            selected[config] = sha
            for item in payload.get("jobs", []):
                if not item.get("job_dir"):
                    jobs.append({"job_name": item.get("job_name"), "chromosome": item.get("chromosome"),
                                 "native_gap_id": item.get("gap_id"), "direction": item.get("direction"),
                                 "artifacts": [], "diagnostics_availability": "not_recorded"})
                    continue
                job_dir = Path(item["job_dir"])
                if not job_dir.is_absolute():
                    job_dir = root / native / job_dir
                if not job_dir.resolve().is_relative_to((root / native).resolve()):
                    raise ReportError("native job diagnostics leave their attempt")
                files = []
                visual_html = None
                family = item.get("direction") == "bidirectional"
                fileset = ("family-result.json", "family-report.html", "junction-evidence.json", "connection-diagnostics.json",
                           "process.summary", "process.agp", "families.json") if family else ("visualization_output/gapfiller_report.html",)
                for name in ("run.stdout.log", "run.stderr.log", "process.log", *fileset):
                    file = job_dir / name
                    if file.exists() or file.is_symlink():
                        relative = file.relative_to(root).as_posix()
                        select(relative)
                        files.append(relative)
                        if name.endswith(".html"):
                            visual_html = relative
                jobs.append({"job_name": item.get("job_name"), "chromosome": item.get("chromosome"),
                             "native_gap_id": item.get("gap_id"), "direction": item.get("direction"),
                             "artifacts": files, "visualization_html": visual_html})
        visual_dir = WorkspaceLayout(root, 1).path((native / "05.visualization").as_posix())
        if visual_dir.is_symlink():
            raise ReportError("native visualization directory cannot be an alias")
        present = {path.name for path in visual_dir.iterdir()} if visual_dir.is_dir() else set()
        for gap in native_gaps:
            direction = native_reports.reported_direction(gap)
            try:
                name = native_reports.detail_name(gap.get("chromosome"), gap.get("gap_id"), direction)
            except native_reports.UnsupportedView:
                continue  # Raw evidence is retained; unsupported names are never rewritten.
            relative = (native / "05.visualization" / name).as_posix()
            if name in present:
                select(relative)
        for name in ("autogapfiller_summary.json", "05.visualization/gap_filling_report.html", "05.visualization/Global.report.html"):
            relative = (native / name).as_posix()
            if (root / relative).exists():
                select(relative)
    if tool == "degap":
        summary_path = (native / "autogapfiller_summary.json").as_posix()
        if summary_path in selected:
            summary = json.loads(read_bound(safe_file(root, summary_path), selected[summary_path], limit=128 * 1024 * 1024))
            results = summary.get("steps", {}).get("step3", {}).get("result", {})
            executions = {row["job_name"]: row for field in ("completed_jobs", "failed_jobs", "skipped_jobs") for row in results.get(field, [])}
            for job in jobs:
                job["execution_result"] = executions.get(job["job_name"], {"status": "not_recorded"})
    return selected, jobs, native_gaps


def embedded_size(rows):
    # Identical source copies keep their logical/provenance rows but share one
    # inert content-addressed attachment and one byte-budget charge.
    return sum({row["report_path"]: row["size_bytes"] for row in rows if "report_path" in row}.values())


def asset_plan(root, artifacts):
    rows, total, copied = [], 0, set()
    visual = any(name.endswith(("/05.visualization/Global.report.html", "/visualization_output/gapfiller_report.html")) for name in artifacts)
    raw_budget = MAX_ASSETS_TOTAL // 2 if visual else MAX_ASSETS_TOTAL
    def priority(item):
        name = item[0]
        rank = 0 if name.endswith("/05.visualization/Global.report.html") else 1 if name.endswith(".html") else 2
        return rank, name
    for relative, expected in sorted(artifacts.items(), key=priority):
        path = safe_file(root, relative)
        size = path.stat().st_size
        # Originals are always inert. Reserve part of the shared quota for the
        # separate closed native view, instead of spending it all on raw logs.
        text = relative.endswith(TEXT_ENDINGS) or relative.endswith(".html")
        include = text and size <= MAX_ASSET and (expected in copied or total + size <= raw_budget)
        row = {"workspace_path": relative, "sha256": expected, "size_bytes": size,
               "availability": "embedded" if include else "server_only_size_limit" if text else
                               "server_only_native_script" if relative.endswith(".sh") or "/native_commands/" in relative else "server_only_sequence_or_binary"}
        if include:
            if expected not in copied:
                total += size
                copied.add(expected)
            row["report_path"] = "assets/" + quote(expected, safe="") + ".txt"
            row["view"] = "original_html_source" if relative.endswith(".html") else "native_text"
        rows.append(row)
    return rows


def guard_report_assets(root, assets, secrets):
    """Keep a private log on the server; never change bytes under a source hash."""
    if not secrets:
        return
    needles = tuple(p.encode() for p in secrets)
    private = set()
    for row in assets:
        if 'report_path' in row and row['sha256'] not in private:
            data = read_bound(safe_file(root,row['workspace_path']),row['sha256'],limit=MAX_ASSET)
            if any(p in data for p in needles): private.add(row['sha256'])
        if row['sha256'] in private:
            row.pop('report_path',None); row.pop('view',None)
            row['availability']='server_only_private_reads'


def native_view_plan(root, tool, run_id, execution, jobs, native_gaps, assets, *, failed=False):
    origin = execution.get("native_origin")
    native_run = origin["run_id"] if origin else run_id
    native = WorkspaceLayout.detect(root).relative(f"04_refinement/{TOOL_DIRECTORIES[tool]}/03_native/{native_run}")
    return native_reports.prepare(tool, native, jobs, native_gaps, assets,
        lambda name, sha: read_bound(safe_file(root, name), sha, limit=MAX_ASSET),
        remaining_budget=MAX_ASSETS_TOTAL - embedded_size(assets),
        page_size=PAGE_SIZE, sealed=set(execution.get("artifacts", {})),
        diagnostics_page="report.html" if failed else "native.html")


def summarize(provenance, final, remaining, jobs, native_gaps):
    if final.get("baseline") != provenance.get("baseline") or final.get("recipe_sha256") != provenance["execution"]["recipe_sha256"]:
        raise ReportError("report Final Path/provenance binding disagrees")
    outcomes = provenance["gap_outcomes"]
    original = {row["gap_id"]: row for row in final["original_gaps"]}
    if len(original) != len(final["original_gaps"]) or len(outcomes) != len(original) or {g["gap_id"] for g in outcomes} != set(original):
        raise ReportError("report omitted or duplicated an original LGZ gap")
    counts = {name: sum(row["status"] == name for row in outcomes) for name in ("closed", "partial", "unfilled", "rejected")}
    if (counts != provenance["counts"] or sum(counts.values()) != len(outcomes)
            or provenance.get("original_gap_count") != len(outcomes)
            or provenance.get("accepted_edit_count") != len(final["edits"])):
        raise ReportError("report counts disagree with the complete original-gap denominator")
    for row in outcomes:
        if any(row[key] != original[row["gap_id"]][key] for key in ("chromosome", "start", "end")):
            raise ReportError("report original gap coordinates changed")
    gap_lookup = defaultdict(list)
    for gap in original.values():
        gap_lookup[gap["chromosome"]].append(gap)
    for rows in gap_lookup.values():
        rows.sort(key=lambda row: row["start"])
    ends = {name: [row["end"] for row in rows] for name, rows in gap_lookup.items()}
    native_by_original = defaultdict(list)
    native_to_original = {}
    for row in native_gaps:
        name, start, end = row.get("chromosome"), row.get("gap_start"), row.get("gap_end")
        if name not in gap_lookup or type(start) is not int or type(end) is not int or start < 1 or end < start:
            continue
        # Fixed DEGAP diagnostics are 1-based inclusive, unlike original LGZ gaps.
        start -= 1
        matching = []
        for index in range(bisect_right(ends[name], start), len(gap_lookup[name])):
            gap = gap_lookup[name][index]
            if gap["start"] >= end:
                break
            matching.append(gap["gap_id"])
            native_by_original[gap["gap_id"]].append(row)
        native_to_original[(name, str(row.get("gap_id")))] = matching
    for job in jobs:
        job["original_gap_ids"] = native_to_original.get((job["chromosome"], str(job["native_gap_id"])), [])
    n_bases = defaultdict(int)
    for row in remaining:
        n_bases[row["chromosome"]] += int(row["end"]) - int(row["start"])
    comparison = []
    native = provenance["execution"].get("native_assembly", {})
    for row in final["chromosomes"]:
        observed = native.get(row["chr"])
        comparison.append({"chromosome": row["chr"], "accepted_length": row["length"],
                           "accepted_n_bases": n_bases[row["chr"]], "accepted_sha256": row["sha256"],
                           "native": observed, "native_equals_accepted": observed["sha256"] == row["sha256"] if observed else None})
    return {"schema": SCHEMA, "schema_version": 1, "tool": provenance["tool"], "run_id": provenance["run_id"],
            "publication_state": "not_asserted_by_report", "outcome": provenance["status"],
            "baseline": final["baseline"], "original_gap_count": len(outcomes), "counts": counts,
            "accepted_edit_count": provenance["accepted_edit_count"], "remaining_gap_count": len(remaining),
            "retained_flank_count": len(retained_flanks(final["edits"]) + [
                row for candidate in provenance["rejected_candidates"]
                for row in candidate.get("flank_decisions", []) if row.get("decision") == "retained_lgz"]),
            "chromosomes": comparison, "execution": provenance["execution"], "native_jobs": jobs, "native_gaps_by_original": dict(native_by_original),
            "coordinate_system": "0-based half-open placement; 1-based inclusive sources",
            "biological_accuracy_validated": False, "automatic_best_tool": None}


def build_tool_report(root, result):
    root = Path(root).resolve()
    tool, run_id = result["tool"], result["run_id"]
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ReportError("invalid refinement report workspace/tool/run")
    staging = Path(result["staging"]).resolve()
    if not staging.is_relative_to(root):
        raise ReportError("staged result is outside its workspace")
    provenance_path = safe_file(root, (staging / "provenance.json").relative_to(root).as_posix())
    marker_path = safe_file(root, layout.relative(f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}/invocation.json"))
    marker = json.loads(marker_path.read_text())
    sha = marker.get("provenance_sha256")
    provenance = json.loads(read_bound(provenance_path, sha))
    if (marker.get("status") not in {"staged", "published"} or marker.get("tool") != tool or marker.get("run_id") != run_id
            or provenance.get("tool") != tool or provenance.get("run_id") != run_id
            or provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1):
        raise ReportError("native attempt has no completed content-bound result")
    for name, expected in provenance["artifacts"].items():
        path = safe_file(staging, name)
        if digest(path) != expected:
            raise ReportError("staged report artifact changed: " + name)
    final_bytes = read_bound(staging / "final_path.json", provenance["artifacts"]["final_path.json"])
    final = json.loads(final_bytes)
    with (staging / "remaining_gaps.tsv").open(newline="", encoding="utf-8") as stream:
        remaining = list(csv.DictReader(stream, delimiter="\t"))
    artifacts, jobs, native_gaps = native_diagnostics(root, tool, run_id, provenance["execution"])
    assets = asset_plan(root, artifacts)
    source_binding, source_summary = {}, None
    if result.get("source_evidence"):
        try:
            from refinement_source_evidence import load, verify_inputs, RECEIPT
        except ModuleNotFoundError:
            from .refinement_source_evidence import load, verify_inputs, RECEIPT
        evidence = result["source_evidence"]
        directory = Path(evidence["directory"])
        receipt_path = safe_file(directory, RECEIPT)
        receipt = load(directory)
        if digest(receipt_path) != evidence["receipt_sha256"] or receipt["recipe"]["provenance_sha256"] != sha:
            raise ReportError("source measurements do not bind the reported accepted result")
        verify_inputs(receipt["recipe"], root)
        source_binding = {"source_evidence_receipt_sha256": evidence["receipt_sha256"],
                          "source_evidence_generation_sha256": receipt["generation_sha256"]}
        artifacts[receipt_path.relative_to(root).as_posix()] = evidence["receipt_sha256"]
        for row in receipt["payload"]:
            artifacts[safe_file(directory, row["file"]).relative_to(root).as_posix()] = row["sha256"]
        source_summary = json.loads(safe_file(directory, "04_projection/summary.json").read_text())
        source_summary["generation_sha256"] = receipt["generation_sha256"]
        assets = asset_plan(root, artifacts)
    secrets = recipe_paths(provenance["execution"].get("recipe") or {})
    guard_report_assets(root,assets,secrets)
    visual = native_view_plan(root, tool, run_id, provenance["execution"], jobs, native_gaps, assets)
    summary = summarize(provenance, final, remaining, jobs, native_gaps)
    summary["native_visualization"] = visual.binding
    summary["artifacts"] = assets
    if source_summary is not None:
        summary["source_evidence"] = source_summary
    summary = hide_paths(summary,secrets)
    if isinstance(summary['execution'].get('recipe',{}).get('reads'),list):
        recipe=summary['execution']['recipe']
        recipe['reads']=[{k:r[k] for k in ('technology','sha256','not_consumed') if k in r} for r in recipe['reads'] if isinstance(r,dict)]
    binding = {"privacy_sha256":digest(Path(__file__).with_name("report_privacy.py")), "provenance_sha256": sha, "generator_sha256": digest(Path(__file__)),
               "renderer_sha256": digest(Path(__file__).with_name("render_refinement_report.py")), "assets": assets, "native_visualization": visual.binding, **source_binding}
    identity = fingerprint(binding)
    home = layout.path(f"04_refinement/{TOOL_DIRECTORIES[tool]}/05_report/{run_id}")
    destination = home / ("site-" + identity[:20])
    if layout.project_delivery:
        from refinement_commit import current_publication, targets
        previous = current_publication(root,tool,verify=False)
        if previous and previous["run_id"] == run_id:
            public = targets(layout,tool)["report"]
            if (digest(safe_file(public,"manifest.json")) == previous["areas"]["report"]["new"]["files"]["manifest.json"]
                    and json.loads((public / "manifest.json").read_text()).get("binding") == binding):
                destination = public
    if destination.exists():
        receipt = json.loads(safe_file(destination, "manifest.json").read_text())
        if receipt.get("binding") != binding or not all(digest(safe_file(destination, name)) == expected for name, expected in receipt["files"].items()):
            raise ReportError("existing portable report was modified")
        return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}
    home.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".report-build-", dir=home))
    try:
        (temporary / "assets").mkdir()
        for row in assets:
            if "report_path" not in row:
                continue
            data = read_bound(safe_file(root, row["workspace_path"]), row["sha256"], limit=MAX_ASSET)
            (temporary / row["report_path"]).write_bytes(data)
        visual.write(temporary)
        (temporary / "final_path.json").write_bytes(final_bytes)
        atomic_json(temporary / "summary.json", summary)
        for relative, html in render_tool_pages(summary, hide_paths(provenance,secrets), final, assets, page_size=PAGE_SIZE):
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html, encoding="utf-8")
        atomic_json(temporary / "manifest.json", {"schema": SCHEMA, "schema_version": 1, "binding": binding,
                    "files": {p.relative_to(temporary).as_posix(): digest(p) for p in sorted(temporary.rglob("*")) if p.is_file()}})
        if digest(provenance_path) != sha:
            raise ReportError("result changed during report generation")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}


def build_failure_report(root, tool, run_id, error, *, phase="native"):
    """Explain failed/preflight attempts without inventing any final assembly."""
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ReportError("invalid failed-attempt report identity")
    code = TOOL_DIRECTORIES[tool]
    artifacts = {}
    for name in ("invocation.json", "native_jobs.json", "native.log"):
        relative = layout.relative(f"04_refinement/{code}/02_jobs/{run_id}/{name}")
        if (root / relative).exists():
            artifacts[relative] = digest(safe_file(root, relative))
    diagnostics_error = None
    execution = {}
    native_gaps = []
    try:
        invocation_relative = layout.relative(f"04_refinement/{code}/02_jobs/{run_id}/invocation.json")
        if invocation_relative in artifacts:
            execution = json.loads(read_bound(safe_file(root, invocation_relative), artifacts[invocation_relative], limit=MAX_ASSET))
        artifacts, jobs, native_gaps = native_diagnostics(root, tool, run_id, {**execution, "artifacts": artifacts})
    except (OSError, ValueError, KeyError, TypeError) as diagnostic:
        jobs = []
        diagnostics_error = str(diagnostic)
    source_diagnostics = getattr(error, "source_evidence_diagnostics", None)
    if phase == "source_evidence" and source_diagnostics is not None:
        try:
            directory = Path(source_diagnostics)
            parent = layout.path(f"04_refinement/{code}/04_accepted/{run_id}/01_source_evidence")
            if directory.parent != parent or re.fullmatch(r"failed-[0-9a-f]{20}-[0-9a-f]{32}", directory.name) is None:
                raise ReportError("source failure diagnostics are outside this attempt")
            relative = (directory / "failure.json").relative_to(root).as_posix()
            failure = json.loads(safe_file(root, relative).read_text())
            if (failure.get("schema") != "cgat.refinement-source-evidence-failure" or failure.get("schema_version") != 1
                    or failure.get("status") not in {"failed", "interrupted"} or failure.get("recipe", {}).get("tool") != tool
                    or failure.get("recipe", {}).get("run_id") != run_id):
                raise ReportError("source failure diagnostics do not bind this attempt")
            artifacts[relative] = digest(safe_file(root, relative))
            for name, sha in failure["files"].items():
                if name.endswith(TEXT_ENDINGS):
                    relative = (directory / name).relative_to(root).as_posix()
                    if digest(safe_file(root, relative)) != sha:
                        raise ReportError("source failure diagnostic changed")
                    artifacts[relative] = sha
        except (OSError, ValueError, KeyError, TypeError) as diagnostic:
            diagnostics_error = (diagnostics_error + "; " if diagnostics_error else "") + str(diagnostic)
    assets = asset_plan(root, artifacts)
    recipe_file=layout.path(f"04_refinement/{code}/01_inputs/{run_id}/recipe.json")
    recipe=(json.loads(recipe_file.read_text()) if recipe_file.is_file() and not recipe_file.is_symlink() else execution.get("recipe",{}))
    secrets=recipe_paths(recipe or {})
    guard_report_assets(root,assets,secrets)
    visual = native_view_plan(root, tool, run_id, execution, jobs, native_gaps, assets, failed=True)
    summary = {"native_visualization": visual.binding, "schema": "cgat.refinement-failure-report", "schema_version": 1, "tool": tool, "run_id": run_id,
               "status": "failed", "phase": phase, "error": str(error), "native_jobs": jobs,
               "diagnostics_error": diagnostics_error, "source_diagnostics": str(source_diagnostics) if source_diagnostics else None,
               "final_available": False, "artifacts": assets,
               "native_status": execution.get("native_status"), "native_reused": execution.get("native_reused", False),
               "native_origin": execution.get("native_origin")}
    summary=hide_paths(summary,secrets)
    binding = {"privacy_sha256":digest(Path(__file__).with_name("report_privacy.py")), "summary": summary, "generator_sha256": digest(Path(__file__)),
               "renderer_sha256": digest(Path(__file__).with_name("render_refinement_report.py"))}
    destination = layout.path(f"04_refinement/{code}/05_report/{run_id}/failure-{fingerprint(binding)[:20]}")
    if destination.exists():
        manifest = json.loads(safe_file(destination, "manifest.json").read_text())
        if manifest.get("binding") != binding or not all(digest(safe_file(destination, name)) == sha for name, sha in manifest["files"].items()):
            raise ReportError("failed-attempt report was modified")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".failure-report-", dir=destination.parent))
        try:
            (temporary / "assets").mkdir()
            visual.write(temporary)
            for row in assets:
                if "report_path" in row:
                    (temporary / row["report_path"]).write_bytes(read_bound(safe_file(root, row["workspace_path"]), row["sha256"], limit=MAX_ASSET))
            atomic_json(temporary / "summary.json", summary)
            (temporary / "report.html").write_text(render_failure(summary), encoding="utf-8")
            atomic_json(temporary / "manifest.json", {"schema": summary["schema"], "schema_version": 1, "binding": binding,
                        "files": {path.relative_to(temporary).as_posix(): digest(path) for path in temporary.rglob("*") if path.is_file()}})
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}
