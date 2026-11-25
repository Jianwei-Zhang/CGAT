"""Current-batch overview with a shared original-gap denominator, no ranking."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import uuid

try:
    from workspace_layout import WorkspaceLayout
    from refinement_reports import ReportError, stat_key
    from refinement_tools import fingerprint
    from refinement_commit import current_publication
    from run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout
    from .refinement_reports import ReportError, stat_key
    from .refinement_tools import fingerprint
    from .refinement_commit import current_publication
    from .run_orchestration import sha256_file as digest, atomic_write_json as atomic_json


def baseline_gaps(layout):
    """Bounded FASTA scan, including cross-line N runs, when every tool fails.

    This reads the already validated LGZ assembly; it does not run LGZ, faidx or
    any refinement tool. Gap IDs use the same chromosome/sequence/interval identity.
    """
    baseline_file = layout.path("metadata/grt_final_path.json")
    before = stat_key(baseline_file)
    payload = json.loads(baseline_file.read_text())
    expected = {row["chr"]: row for row in payload["chromosomes"]}
    fasta = layout.path(payload["q4_relpath"])
    fasta_before = stat_key(fasta)
    seen, gaps = set(), []
    name, length, sha, pending, intervals = None, 0, None, None, []
    def finish():
        if name is None:
            return
        if name not in expected or name in seen:
            raise ReportError("LGZ baseline chromosome identity changed")
        if pending is not None:
            intervals.append(pending)
        sequence_sha = sha.hexdigest()
        if length != expected[name]["q4_length"] or sequence_sha != expected[name]["q4_sha256"]:
            raise ReportError("LGZ baseline sequence changed while constructing report denominator")
        seen.add(name)
        for start, end in intervals:
            gaps.append({"gap_id": "gap-" + fingerprint([name, sequence_sha, start, end])[:24],
                         "chromosome": name, "start": start, "end": end})
    with fasta.open("rb") as stream:
        at_line_start = True
        while True:
            raw = stream.readline(1024 * 1024)
            if not raw:
                break
            if at_line_start and raw.startswith(b">"):
                if not raw.endswith(b"\n") and len(raw) == 1024 * 1024:
                    raise ReportError("LGZ FASTA header is unreasonably long")
                finish()
                name = raw[1:].split()[0].decode("utf-8")
                length, sha, pending, intervals = 0, hashlib.sha256(), None, []
            else:
                sequence = raw.strip().upper()
                if sequence and name is None:
                    raise ReportError("LGZ FASTA has no header")
                if sequence:
                    sha.update(sequence)
                    for match in re.finditer(b"N+", sequence):
                        start, end = length + match.start(), length + match.end()
                        if pending is not None and pending[1] == start:
                            pending = (pending[0], end)
                        else:
                            if pending is not None:
                                intervals.append(pending)
                            pending = (start, end)
                    length += len(sequence)
                    if pending is not None and pending[1] < length:
                        intervals.append(pending)
                        pending = None
            at_line_start = raw.endswith(b"\n")
    finish()
    if seen != set(expected) or stat_key(fasta) != fasta_before or stat_key(baseline_file) != before:
        raise ReportError("LGZ baseline changed or is incomplete")
    return gaps


def write_html(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(contents, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def overview_html(layout, batch=None, *, mode=None, verify_content=False):
    from report_overview_data import build_overview_view_model
    from render_overview_report import render_overview as render_page
    vm = build_overview_view_model(layout.root, batch, mode=mode, verify_content=verify_content)
    return render_page(vm)


def refresh_diagnostic_overview(layout):
    """Only replace our own previous diagnostic. Preserve manual overlays and all
    unknown/automatic overview pages, including after a new failed invocation."""
    if layout.version != 2:
        return
    from refine_report import automatic_overview_digest
    from report_inventory import physical
    path = physical(layout.root, '06_report/report.html')
    owner = physical(layout.root, '.runtime/run_all/diagnostic-overview.json')
    if path.exists():
        if not owner.is_file() or json.loads(owner.read_text()).get('automatic_sha256') != automatic_overview_digest(path):
            return
    write_html(path, overview_html(layout, mode='lgz_failed'))
    atomic_json(owner, {'schema':'cgat.diagnostic-overview.v1','automatic_sha256':automatic_overview_digest(path)})


def render_overview(root, batch, results):
    from report_overview_data import sanitized_reason
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or not re.fullmatch(r"[0-9a-f]{32}", batch["batch_id"]):
        raise ReportError("invalid overview workspace/batch")
    report = layout.path("06_report/report.html")
    comparison_dir = layout.path("06_report/03_comparison/" + batch["batch_id"])
    compare = not layout.project_delivery or bool(batch["tools"])
    if compare:
        comparison_dir.mkdir(parents=True, exist_ok=True)
    invalidated = batch["status"] == "invalidated"
    original, summaries, outcomes, rows = None, {}, {}, []
    for tool, record in batch["tools"].items():
        result = results.get(tool)
        if result is not None and record.get("report") and record["status"] in {"staged", "published"} and not invalidated:
            directory = Path(record["report"]["directory"])
            manifest = json.loads((directory / "manifest.json").read_text())
            if digest(directory / "manifest.json") != record["report"]["manifest_sha256"]:
                raise ReportError("tool report changed before comparison")
            for name in ("summary.json", "final_path.json"):
                if digest(directory / name) != manifest["files"][name]:
                    raise ReportError("tool comparison input changed")
            summary = json.loads((directory / "summary.json").read_text())
            final = json.loads((directory / "final_path.json").read_text())
            if original is not None and original != final["original_gaps"]:
                raise ReportError("tools do not share the same original LGZ gap denominator")
            original = final["original_gaps"]
            summaries[tool] = summary
            outcomes[tool] = {row["gap_id"]: row["status"] for row in result["provenance"]["gap_outcomes"]}
        published = None
        if record["status"] in {"staged", "published"} and result is not None:
            try:
                candidate = current_publication(root, tool)
                if candidate and candidate["run_id"] == result["run_id"] and record.get("report"):
                    current_manifest = candidate.get("areas", {}).get("report", {}).get("new", {}).get("files", {}).get("manifest.json")
                    if current_manifest == record["report"]["manifest_sha256"]:
                        published = candidate
            except (OSError, ValueError):
                pass
        summary = summaries.get(tool, {})
        recipe = summary.get("execution", {}).get("recipe", {})
        rows.append({"tool": tool, "status": "published" if published else record["status"],
                     "run_id": record.get("run_id"), "publication_transaction": published["transaction"] if published else None,
                     "counts": summary.get("counts"),
                     "native_status":summary.get("execution",{}).get("native_status"),
                     "native_executed":summary.get("execution",{}).get("native_executed"), "error": sanitized_reason(record.get("error")), "phase": record.get("phase"),
                     "actual_threads": summary.get("execution", {}).get("threads"),
                     "requested_thread_budget": batch.get("threads"), "result_reused": bool(record.get("reused_from")),
                     "native_reused": bool(record.get("native_reused") or record.get("reused_from")),
                     "native_origin": record.get("native_origin"),
                     "timing": summary.get("execution", {}).get("timing"),
                     "reads": [{k:r[k] for k in ("technology", "sha256") if k in r} for r in recipe.get("reads", []) if isinstance(r,dict)],
                     "recipe": recipe.get("name", recipe.get("schema")), "revision": recipe.get("revision"),
                     "native_vs_accepted": summary.get("chromosomes")})
    if compare and original is None and not invalidated:
        original = baseline_gaps(layout)
    original = original or []
    comparison = {"schema": "cgat.refinement-comparison", "schema_version": 1, "batch_id": batch["batch_id"],
                  "batch_status": batch["status"], "exit_code": batch["exit_code"],
                  "baseline_valid": not invalidated, "original_gap_count": None if invalidated or not compare else len(original),
                  "tools": rows, "best_tool": None, "biological_accuracy_validated": False}
    if compare:
        atomic_json(comparison_dir / "comparison.json", comparison)
        atomic_json(comparison_dir / "original_gaps.json", original)
        # Failed/unattempted tools retain a cell for every original gap. They are
        # not counted as successful zero-fill experiments or removed from denominators.
        columns = list(batch["tools"])
        lines = ["gap_id\tchromosome\tstart\tend" + "".join("\t" + tool for tool in columns)]
        for gap in original:
            cells = [gap["gap_id"], gap["chromosome"], str(gap["start"]), str(gap["end"])]
            cells += [outcomes.get(tool, {}).get(gap["gap_id"], "tool_" + batch["tools"][tool]["status"]) for tool in columns]
            if any("\t" in value or "\n" in value or "\r" in value for value in cells):
                raise ReportError("invalid comparison table identity")
            lines.append("\t".join(cells))
        write_html(comparison_dir / "gap_comparison.tsv", "\n".join(lines) + "\n")
    write_html(report, overview_html(layout, batch))
    if not compare:
        return {"report": str(report)}
    return {"report": str(report), "comparison": str(comparison_dir / "comparison.json"),
            "gap_comparison": str(comparison_dir / "gap_comparison.tsv")}
