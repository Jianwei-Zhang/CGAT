"""Render and publish project-scoped manual refinement reports."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

try:
    from render_manual_report import render_batch, render_overview, render_landing
    from run_orchestration import sha256_file
    from workspace_migration import durable_json, rename_synced
except ModuleNotFoundError:
    from .render_manual_report import render_batch, render_overview, render_landing
    from .run_orchestration import sha256_file
    from .workspace_migration import durable_json, rename_synced

INDEX_SCHEMA = "cgat.server-manual-refinement-index.v1"
REPORT_SCHEMA = "cgat.server-manual-refinement-report.v1"
SECTION_START = "<!-- CGAT:MANUAL_REFINEMENT_SECTION:START -->"
SECTION_END = "<!-- CGAT:MANUAL_REFINEMENT_SECTION:END -->"

def _relative(page_path: Path, target: Path) -> str:
    return Path(os.path.relpath(target, page_path.parent)).as_posix()


def _write_text(path: Path, text: str) -> None:
    _require_regular(path)
    data = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".manual-report-", dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        rename_synced(temporary, path)


def _require_regular(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"report destination is not a regular file: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    _require_regular(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"report metadata must be a JSON object: {path}")
    return data


def _with_manual_section(current: str, section: str) -> str:
    block = f"{SECTION_START}\n{section}\n{SECTION_END}\n"
    if current.count(SECTION_START) or current.count(SECTION_END):
        start, end = current.find(SECTION_START), current.find(SECTION_END)
        if (current.count(SECTION_START) != 1 or current.count(SECTION_END) != 1
                or not 0 <= start < end or not current.startswith("\n</main>", end + len(SECTION_END))):
            raise ValueError("invalid manual section in the workspace overview")
        current = current[:start] + current[end + len(SECTION_END) + 1:]
    position = current.rfind("</main>")
    if position < 0:
        raise ValueError("unsupported workspace overview: missing </main>")
    return current[:position] + block + current[position:]


def automatic_overview_digest(path: Path) -> str:
    """A manual-only edit does not invalidate a sealed automatic overview."""
    data = path.read_bytes()
    start, end = SECTION_START.encode(), SECTION_END.encode() + b"\n"
    if data.count(start) == data.count(end) == 1:
        prefix, _, tail = data.partition(start)
        _, separator, suffix = tail.partition(end)
        if separator and suffix.startswith(b"</main>"):
            data = prefix + suffix
    return hashlib.sha256(data).hexdigest()


def merge_manual_overview(layout, current: str) -> str:
    """Assemble relative links from our own index, not paths stored in JSON."""
    index = _read_json(layout.path("06_report/manual_refinement.json"))
    if not index:
        return current
    batches = index.get("batches")
    if index.get("schema") != INDEX_SCHEMA or not isinstance(batches, list):
        raise ValueError("invalid manual refinement report index")
    overview = layout.path("06_report/report.html")
    entries = []
    for record in batches:
        batch = record["batch_sha256"]
        if not isinstance(batch, str) or re.fullmatch(r"[a-f0-9]{64}", batch) is None:
            raise ValueError("invalid manual refinement batch identity")
        batch_dir = _batch_dir(layout, batch)
        report = layout.path((batch_dir / "03_report/report.html").relative_to(layout.root).as_posix())
        delivery = manual_patch_path(layout,batch)
        links = {label: _relative(overview, target) for label, target in
                 (("Batch report / 批次报告", report), ("Result bundle / 结果包", delivery))
                 if not target.is_symlink() and target.is_file()}
        entries.append({"summary": record, "links": links})
    if not current:
        from report_overview_data import build_overview_view_model
        from render_overview_report import render_overview as render_workflow
        current = render_workflow(build_overview_view_model(layout.root, mode="manual_only"))
    return _with_manual_section(current, render_overview(entries))


def _batch_dir(layout, batch):
    parent = "08_refinement_jobs/02_manual" if layout.version == 2 else ".run_all/manual_refinement"
    return layout.path(f"{parent}/{batch}")


def manual_patch_path(layout, batch):
    if not re.fullmatch(r"[0-9a-f]{64}", batch):
        raise ValueError("invalid manual batch identity")
    if layout.project_delivery:
        return layout.path(f"07_delivery/manual/{layout.result_prefix}.manual-{batch[:16]}.patch.zip")
    return _batch_dir(layout,batch) / "04_delivery/refinement_results.zip"


def publish_manual_report(layout, batch_dir: Path, manifest: dict, data: dict, reads: dict, delivery: Path) -> dict[str, str]:
    """Publish a batch and refresh the manual section while holding the workspace lock."""
    root = layout.root
    batch = data["batch_sha256"]
    if re.fullmatch(r"[a-f0-9]{64}", batch) is None or _batch_dir(layout, batch) != batch_dir:
        raise ValueError("invalid manual report batch identity")
    batch_report = layout.path((batch_dir / "03_report/report.html").relative_to(root).as_posix())
    summary_path = batch_report.with_name("summary.json")
    overview = layout.path("06_report/report.html")
    index = layout.path("06_report/manual_refinement.json")
    for path in (batch_report, summary_path, overview, index, delivery):
        _require_regular(path)
    previous = _read_json(summary_path)
    if previous and previous.get("batch_sha256") != batch:
        raise ValueError("existing manual report belongs to another batch")
    status = "pending_app_import" if any(row.get("patch") is not None for row in data["results"]) else "no_patch"
    # Legacy Python callers use result['report'] as a private audit record, including
    # exact reads identities. Never expose that object as the public HTML/JSON target.
    original_reads = reads
    private_paths = [r['path'] for group in reads.values() for r in group if r.get('path')]
    from report_privacy import hide_paths
    data = hide_paths(data,private_paths)
    reads = {t: [{k:r[k] for k in ('technology','sha256') if k in r} for r in group] for t,group in reads.items()}
    summary = {**data, "report_schema": REPORT_SCHEMA, "export_id": manifest["export_id"],
               "origin_fasta_sha256": manifest["origin_fasta_sha256"], "report_status": status,
               "loci": {row["id"]: {key: row[key] for key in ("chr", "target", "kind")} for row in manifest["loci"]},
               "reads": reads, "delivery": delivery.relative_to(root).as_posix(), "delivery_sha256": sha256_file(delivery)}
    # A retry with identical execution outcomes is not a second completion.
    if previous.get("results") == data["results"] and previous.get("reads") == reads and previous.get("completed_at"):
        summary["completed_at"] = previous["completed_at"]
    else:
        summary["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    batch_links = {
        "Overview / 总览": _relative(batch_report, overview) + "#manual-refinement",
        "Result bundle / 结果包": _relative(batch_report, delivery),
        "Machine-readable summary / 机器摘要": "summary.json",
    }
    if data.get("schema") == "cgat.app-refinement-results.v2":
        from manual_genome import names
        genome=names(layout,batch)["fasta"]
        if not genome.is_file() or sha256_file(genome)!=data["assembly"]["genome_sha256"]:
            raise ValueError("manual report has no matching committed whole genome")
        batch_links["Final genome / 本批全基因组"]=_relative(batch_report,genome)
        summary["fasta"]=genome.relative_to(root).as_posix()
    catalog = _read_json(index)
    if catalog and (catalog.get("schema") != INDEX_SCHEMA or not isinstance(catalog.get("batches"), list)):
        raise ValueError("invalid manual refinement report index")
    entries = {entry["batch_sha256"]: entry for entry in catalog.get("batches", [])}
    entries[batch] = {key: summary[key] for key in ("batch_sha256", "completed_at", "report_status")}
    entries[batch]["results"] = [
        {"tool": row["tool"], "version": row.get("version"), "status": row["status"],
         "patch": {} if row.get("patch") is not None else None}
        for row in data["results"]
    ]
    current = overview.read_bytes().decode("utf-8") if overview.is_file() else ""
    _write_text(batch_report, render_batch(summary, batch_links))
    if summary != previous:
        durable_json(summary_path, summary)
    result_catalog = {"schema": INDEX_SCHEMA, "batches": [entries[key] for key in sorted(entries)]}
    if catalog != result_catalog:
        durable_json(index, result_catalog)
    _write_text(overview, merge_manual_overview(layout, current))
    audit_rel = ".runtime/refinement/manual-audit" if layout.version == 2 else ".run_all/manual-audit"
    audit = layout.path(f"{audit_rel}/{batch}.json")
    _require_regular(audit)
    audit_record = {**summary, 'reads':original_reads}
    if _read_json(audit) != audit_record:
        from server_report_io import write_json
        write_json(audit, audit_record)  # private mkstemp-created file (0600), not a report member
    return {"report": str(audit), "public_summary": str(summary_path), "batch_report": str(batch_report), "overview": str(overview), "index": str(index)}
