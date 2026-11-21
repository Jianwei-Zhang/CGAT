"""Current-batch overview with a shared original-gap denominator, no ranking."""
from __future__ import annotations

from collections import defaultdict
from html import escape
import json
import hashlib
import os
from pathlib import Path
import re
import uuid

try:
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES
    from refinement_reports import page, table, link, gap_anchor, ReportError, stat_key
    from refinement_tools import fingerprint
    from refinement_commit import current_publication
    from run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
except ModuleNotFoundError:
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES
    from .refinement_reports import page, table, link, gap_anchor, ReportError, stat_key
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


def local_link(root, page_path, target, label):
    if not target.resolve().is_relative_to(root) or not target.is_file():
        raise ReportError("overview link is outside its workspace or missing")
    return link(Path(os.path.relpath(target, page_path.parent)).as_posix(), label)


def render_overview(root, batch, results):
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or not re.fullmatch(r"[0-9a-f]{32}", batch["batch_id"]):
        raise ReportError("invalid overview workspace/batch")
    report = layout.path("06_report/report.html")
    comparison_dir = layout.path("06_report/03_comparison/" + batch["batch_id"])
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
                if candidate and candidate["run_id"] == result["run_id"]:
                    published = candidate
            except (OSError, ValueError):
                pass
        summary = summaries.get(tool, {})
        recipe = summary.get("execution", {}).get("recipe", {})
        rows.append({"tool": tool, "status": "published" if published else record["status"],
                     "run_id": record.get("run_id"), "publication_transaction": published["transaction"] if published else None,
                     "counts": summary.get("counts"), "error": record.get("error"), "phase": record.get("phase"),
                     "actual_threads": summary.get("execution", {}).get("threads"),
                     "timing": summary.get("execution", {}).get("timing"),
                     "reads": recipe.get("reads", []), "input_selection": recipe.get("original_selection"),
                     "recipe": recipe.get("name", recipe.get("schema")), "revision": recipe.get("revision"),
                     "native_vs_accepted": summary.get("chromosomes")})
    if original is None and not invalidated:
        original = baseline_gaps(layout)
    original = original or []
    comparison = {"schema": "cgat.refinement-comparison", "schema_version": 1, "batch_id": batch["batch_id"],
                  "batch_status": batch["status"], "exit_code": batch["exit_code"],
                  "baseline_valid": not invalidated, "original_gap_count": None if invalidated else len(original),
                  "tools": rows, "best_tool": None, "biological_accuracy_validated": False}
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
    body = '<p>Batch: <code>' + escape(batch["batch_id"]) + '</code> · ' + escape(batch["status"]) + '</p>'
    body += '<p class="note">No accuracy claim or best-tool ranking. Native output and CGAT admission are distinct. / 不宣称准确率或自动评选最佳工具；原生输出与 CGAT 接纳结果分别记录。</p>'
    body += '<p>Original LGZ gap denominator / 原始 LGZ 缺口数: ' + escape(str(comparison["original_gap_count"])) + '</p>'
    links = []
    lgz_report = layout.path("report/report.html")
    if lgz_report.is_file():
        links.append(local_link(root, report, lgz_report, "LGZ process / LGZ 过程"))
    links += [local_link(root, report, comparison_dir / "comparison.json", "Comparison / 比较 JSON"),
              local_link(root, report, comparison_dir / "gap_comparison.tsv", "All original gaps / 全部原始缺口对照")]
    body += '<p>' + ' · '.join(links) + '</p>'
    display = []
    for row in rows:
        record = batch["tools"][row["tool"]]
        report_link = "No completed report / 无完整报告"
        if record.get("report", {}).get("report") and Path(record["report"]["report"]).is_file():
            report_link = local_link(root, report, Path(record["report"]["report"]), "Jobs, native evidence, decisions / 任务、原生证据与接纳")
        if not record.get("report"):
            failed_log = layout.path(f"04_refinement/{TOOL_DIRECTORIES[row['tool']]}/02_jobs/{row['run_id']}/native.log")
            if failed_log.is_file():
                report_link = local_link(root, report, failed_log, "Native execution log / 原生执行日志")
        final_links = "Not published in this batch / 本批次尚未发布"
        if row["publication_transaction"]:
            code = TOOL_DIRECTORIES[row["tool"]]
            final_links = ' · '.join(local_link(root, report, layout.path(f"05_final/{code}/{name}"), label) for name, label in
                                     (("assembly.fa", "Final FASTA"), ("final_path.json", "Final Path"), ("provenance.json", "Provenance / 来源")))
        display.append((escape(row["tool"]), escape(row["status"]), escape(str(row["counts"])),
                        report_link, final_links, escape(row["error"] or "")))
    body += table(["Tool", "State", "Accepted gap outcomes", "Process report", "Final publication", "Error"], display)
    body += '<p>Only a complete publication receipt makes final/report/full/light deliveries current. Old successful folders are not relabeled as this batch after failure. / 仅完整发布回执代表本批结果；失败不会把历史成功目录标成本次完成。</p>'
    write_html(report, page("CGAT workflow / 流程总览", body))
    return {"report": str(report), "comparison": str(comparison_dir / "comparison.json"),
            "gap_comparison": str(comparison_dir / "gap_comparison.tsv")}
