"""Discover automatic jobs without moving their evidence or publishing receipts."""
from __future__ import annotations

import json
from pathlib import Path
import re

from refinement_commit import current_publication
from run_orchestration import sha256_file
from workspace_layout import TOOL_DIRECTORIES, relative_path
from workspace_migration import durable_json


def verify_reference(layout, relative, expected):
    path = layout.path(relative)
    return path.is_file() and not path.is_symlink() and sha256_file(path) == expected


def write_automatic_index(layout, completion_path):
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    batch_id = completion["batch_id"]
    if (completion.get("schema") != "cgat.refinement-invocation"
            or not re.fullmatch(r"[a-f0-9]{32}", batch_id)):
        raise ValueError("invalid automatic refinement completion receipt")
    batch_rel = f".runtime/refinement/batches/{batch_id}.json"
    if not verify_reference(layout, batch_rel, completion["batch_sha256"]):
        raise ValueError("automatic refinement batch differs from its completion receipt")
    batch = json.loads(layout.path(batch_rel).read_text(encoding="utf-8"))
    if (batch.get("schema") != "cgat.refinement-batch" or batch.get("schema_version") != 1
            or batch.get("batch_id") != batch_id or set(batch["tools"]) - TOOL_DIRECTORIES.keys()):
        raise ValueError("invalid automatic refinement batch")

    index_dir = "08_refinement_jobs/01_automatic"
    overview = "06_report/report.html"
    overview_sha = completion["overview_files"].get(overview)
    if not verify_reference(layout, overview, overview_sha):
        raise ValueError("automatic refinement overview differs from its completion receipt")
    jobs = []
    for tool, record in batch["tools"].items():
        code = TOOL_DIRECTORIES[tool]
        row = {"schema": "cgat.refinement-job-index.v1", "source": "automatic", "tool": tool,
               "batch_id": batch_id, "run_id": record.get("run_id"), "status": record["status"],
               "phase": record.get("phase"), "reason": record.get("error"), "overview": overview,
               "report": None, "delivery": {}}
        if row["status"] == "published":
            try:
                journal = current_publication(layout.root, tool, verify=False)
            except (ValueError, OSError):
                journal = None
            if (not journal or journal["transaction"] != record.get("publication_transaction")
                    or journal["run_id"] != row["run_id"]):
                row.update(status="publication_unverified", reason="No matching committed publication receipt")
            else:
                report = f"06_report/02_refinement/{code}/report.html"
                report_files = journal["areas"]["report"]["new"]["files"]
                delivery = f"07_delivery/{code}"
                files = journal["areas"]["delivery"]["new"]["files"]
                manifest_path = f"{delivery}/delivery.json"
                if (verify_reference(layout, report, report_files.get("report.html"))
                        and verify_reference(layout, manifest_path, files.get("delivery.json"))):
                    definition = json.loads(layout.path(manifest_path).read_text(encoding="utf-8"))
                    for mode in ("full", "light"):
                        archive = definition["archives"][mode]
                        name = relative_path(archive["file"])
                        path = layout.path(f"{delivery}/{name}")
                        if (len(Path(name).parts) != 1 or not path.is_file() or path.is_symlink()
                                or files.get(name) != archive["sha256"]):
                            break
                        row["delivery"][mode] = f"{delivery}/{name}"
                    if len(row["delivery"]) == 2:
                        row["report"] = report
                        row["publication_transaction"] = journal["transaction"]
                if not row["report"]:
                    row.update(status="publication_unverified", reason="Published report or delivery reference changed", delivery={})
        if row["status"] != "published" and record.get("report"):
            report_path = Path(record["report"]["report"])
            manifest_path = report_path.parent / "manifest.json"
            if (report_path.is_absolute() and report_path.is_relative_to(layout.root)
                    and report_path.name == "report.html" and not manifest_path.is_symlink()
                    and manifest_path.is_file()
                    and sha256_file(manifest_path) == record["report"].get("manifest_sha256")):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                relative = report_path.relative_to(layout.root).as_posix()
                if verify_reference(layout, relative, manifest["files"].get("report.html")):
                    row["report"] = relative
        entry = f"{index_dir}/{code}/job.json"
        durable_json(layout.path(entry), row)
        jobs.append(entry)
    index = layout.path(f"{index_dir}/index.json")
    durable_json(index, {"schema": "cgat.refinement-jobs-index.v1", "batch_id": batch_id,
                         "status": batch["status"], "overview": overview,
                         "completion": completion_path.relative_to(layout.root).as_posix(), "jobs": jobs})
    return index
