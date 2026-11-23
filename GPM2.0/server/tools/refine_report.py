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
    from refinement_reports import badge_html, callout, esc, fmt_bp, fmt_int, kv_grid, link, page, table
    from run_orchestration import sha256_file
    from workspace_migration import durable_json, rename_synced
except ModuleNotFoundError:
    from .refinement_reports import badge_html, callout, esc, fmt_bp, fmt_int, kv_grid, link, page, table
    from .run_orchestration import sha256_file
    from .workspace_migration import durable_json, rename_synced

INDEX_SCHEMA = "cgat.server-manual-refinement-index.v1"
REPORT_SCHEMA = "cgat.server-manual-refinement-report.v1"
SECTION_START = "<!-- CGAT:MANUAL_REFINEMENT_SECTION:START -->"
SECTION_END = "<!-- CGAT:MANUAL_REFINEMENT_SECTION:END -->"

BATCH_STATUS = {
    "pending_app_import": ("Pending App import / 等待导回 App", "warn"),
    "no_patch": ("No patch to import / 无可导回补丁", "neutral"),
}
TASK_STATUS = {
    "closed": ("Closed / 已闭合", "ok", "is-closed"),
    "extended": ("Extended / 端粒延伸", "ok", "is-closed"),
    "partial": ("Partial / 部分填补", "info", "is-partial"),
    "no_candidate": ("No candidate / 无候选", "neutral", "is-unfilled"),
    "rejected": ("Rejected / 已拒绝", "err", "is-rejected"),
    "missing_reads": ("Missing reads / 缺 reads", "warn", "is-rejected"),
    "input_unavailable": ("Input unavailable / 输入不可用", "warn", "is-rejected"),
    "failed": ("Failed / 失败", "err", "is-rejected"),
    "incomplete": ("Incomplete / 未完成", "warn", "is-unfilled"),
}
KIND_LABELS = {"gap": "Gap / 缺口", "tel_left": "Left telomere / 左端粒", "tel_right": "Right telomere / 右端粒"}
OP_LABELS = {"replace_gap": "Replace gap / 替换缺口", "prepend_tel": "Prepend telomere / 左端延伸", "append_tel": "Append telomere / 右端延伸"}


def _short(value: Any, n: int = 12) -> str:
    text = str(value or "")
    return text[:n] if len(text) > n else text


def _batch_status(summary: dict[str, Any]) -> str:
    has_patch = any(isinstance(r.get("patch"), dict) for r in (summary.get("results") or []))
    return "pending_app_import" if summary.get("report_status") == "pending_app_import" and has_patch else "no_patch"


def _batch_badge(status: str) -> str:
    return badge_html(*BATCH_STATUS.get(status, BATCH_STATUS["no_patch"]))


def _task_badge(status: Any) -> str:
    key = str(status or "not_recorded")
    text, tone, _ = TASK_STATUS.get(key, (key, "neutral", "is-unfilled"))
    return badge_html(text, tone)


def _counts_html(results: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in results:
        key = str(row.get("status") or "not_recorded")
        counts[key] = counts.get(key, 0) + 1
    chips = [
        f'<span class="count-chip {TASK_STATUS.get(k, (k, "neutral", "is-unfilled"))[2]}">'
        f'{esc(TASK_STATUS.get(k, (k, "neutral", "is-unfilled"))[0])}: <b>{esc(fmt_int(n))}</b></span>'
        for k, n in counts.items()
    ]
    return '<div class="count-chips">' + "".join(chips) + "</div>" if chips else '<span class="muted">No tasks / 无任务</span>'


def _links_html(links: dict[str, str] | None) -> str:
    items = [link(href, label, cls="link-pill") for label, href in (links or {}).items() if href]
    return '<div class="link-row">' + "".join(items) + "</div>" if items else '<span class="muted">—</span>'


def _locus_cell(locus_id: str, meta: dict[str, Any]) -> str:
    head = ([f'<strong>{esc(meta["chr"])}</strong>'] if meta.get("chr") else []) + ([f'<code>{esc(meta["target"])}</code>'] if meta.get("target") else [])
    sub = ([badge_html(KIND_LABELS.get(str(meta["kind"]), str(meta["kind"])), "neutral")] if meta.get("kind") else []) + (
        [f'<small><code>{esc(_short(locus_id, 16))}</code></small>'] if locus_id else []
    )
    return "".join(([" · ".join(head)] if head else []) + (["<div>" + " ".join(sub) + "</div>"] if sub else [])) or '<span class="muted">—</span>'


def _tool_cell(row: dict[str, Any]) -> str:
    meta = ([f'v{esc(row["version"])}'] if row.get("version") else []) + ([f'rev <code>{esc(_short(row["revision"], 12))}</code>'] if row.get("revision") else [])
    return f'<strong>{esc(row.get("tool") or "—")}</strong>' + (f'<div><small>{" · ".join(meta)}</small></div>' if meta else "")


def _patch_cell(patch: Any) -> str:
    if not isinstance(patch, dict):
        return '<span class="muted">None / 无补丁</span>'
    op = str(patch.get("operation") or "patch")
    sizes = ([f'orig {fmt_bp(patch["original_length"])}'] if patch.get("original_length") is not None else []) + (
        [f'new {fmt_bp(patch["length"])}'] if patch.get("length") is not None else []
    )
    lines = [f'<div><strong>{esc(OP_LABELS.get(op, op))}</strong></div>']
    if sizes:
        lines.append(f'<div><small class="num">{esc(" → ".join(sizes))}</small></div>')
    if patch.get("path"):
        lines.append(f'<div><small><code>{esc(patch["path"])}</code></small></div>')
    if patch.get("sha256"):
        lines.append(f'<div><small>sha256 <code>{esc(_short(patch["sha256"], 16))}</code></small></div>')
    return "".join(lines)


def _metrics_strip(cells: list[tuple[str, str, str]]) -> str:
    items = [
        '<div class="metric-cell">'
        f'<div class="label">{esc(label)}</div>'
        f'<div class="value num">{value_html}</div>'
        + (f'<div class="sub">{sub_html}</div>' if sub_html else "")
        + "</div>"
        for label, value_html, sub_html in cells
    ]
    return '<div class="metrics-strip">' + "".join(items) + "</div>" if items else ""


def _read_rows(reads: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for tool, items in reads.items():
        if not isinstance(items, list):
            continue
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            tech = str(item.get("technology") or "unknown").upper()
            digest = str(item.get("sha256") or "")
            rows.append((
                f"<strong>{esc(tool)}</strong>",
                badge_html(tech, "info"),
                f'<span class="muted">Server input #{index} (path omitted) / 服务端输入 #{index}（不公开路径）</span>',
                f"<code>{esc(digest)}</code>" if digest else '<span class="muted">—</span>',
            ))
    return rows


def render_batch(summary: dict[str, Any], links: dict[str, str] | None) -> str:
    batch_sha, completed_at = str(summary.get("batch_sha256") or ""), summary.get("completed_at")
    results, loci, reads = list(summary.get("results") or []), summary.get("loci") or {}, summary.get("reads") or {}
    state = _batch_status(summary)
    patch_count = sum(1 for row in results if isinstance(row.get("patch"), dict))
    note = (
        callout(
            "Server 已完成计算并生成候选补丁，当前处于「等待导回 App」状态；在原 CGAT App 完成核对并生成回执前，"
            "不会标记为已导回，也不会写入自动终版 05_final/。"
            " / Candidate patches are ready for CGAT App review and import; they are never marked imported without an App receipt "
            "and never overwrite automatic 05_final/ deliveries.",
            tone="warn",
            title="Pending App Import / 等待导回 App",
        )
        if state == "pending_app_import"
        else callout(
            "本批次未产出可导回补丁（无候选、被拒绝、缺 reads 或执行失败），不属于等待导回状态，也不写入自动终版 05_final/。"
            " / No importable patch was produced in this batch (no candidate, rejected, missing reads, or failed); "
            "not awaiting App import and automatic 05_final/ is unchanged.",
            tone="neutral",
            title="No Patch to Import / 无可导回补丁",
        )
    )
    metrics = _metrics_strip([
        ("Loci / 位点数", esc(fmt_int(len(loci))), "Project-scoped targets / 项目内位点"),
        ("Tasks / 任务数", esc(fmt_int(len(results))), "Executed tool tasks / 工具任务总数"),
        ("Patches / 可导回补丁", esc(fmt_int(patch_count)), "Candidate patches / 候选补丁"),
        ("Receipt / 导回状态", _batch_badge(state), "App receipt required / 需 App 回执确认"),
    ])
    kv = [("Batch SHA-256 / 批次标识", f"<code>{esc(batch_sha)}</code>"), ("Status / 状态", _batch_badge(state))]
    if summary.get("export_id"):
        kv.append(("Export ID / 导出标识", f'<code>{esc(summary["export_id"])}</code>'))
    if summary.get("origin_fasta_sha256"):
        kv.append(("Origin FASTA SHA-256 / 基线序列摘要", f'<code>{esc(_short(summary["origin_fasta_sha256"], 24))}</code>'))
    if summary.get("delivery_sha256"):
        kv.append(("Delivery ZIP SHA-256 / 交付包摘要", f'<code>{esc(_short(summary["delivery_sha256"], 24))}</code>'))
    if completed_at:
        kv.append(("Completed / 完成时间", f"<code>{esc(completed_at)}</code>"))
    kv.append(("Outcomes / 状态统计", _counts_html(results)))
    task_rows = [
        (
            _locus_cell(str(r.get("locus_id") or ""), loci.get(r.get("locus_id"), {})),
            _tool_cell(r),
            _task_badge(r.get("status")),
            f'<code>{esc(r["reason"])}</code>' if r.get("reason") else '<span class="muted">—</span>',
            _patch_cell(r.get("patch")),
        )
        for r in results
    ]
    read_rows = _read_rows(reads)
    nav = '<a href="#batch-summary">Summary / 摘要</a><a href="#task-results">Results / 任务结果</a><a href="#reads-used">Reads / 测序数据</a>' + "".join(
        link(href, label) for label, href in (links or {}).items() if href
    )
    body = (
        f'<section id="batch-summary" class="panel"><div class="panel-head"><h2>Batch Summary / 批次摘要</h2>{_batch_badge(state)}</div>'
        + metrics + note + kv_grid(kv) + _links_html(links) + "</section>"
        + f'<section id="task-results" class="panel"><div class="panel-head"><h2>Task Results / 任务结果</h2>'
        f'<span class="badge tone-neutral num">{len(results):,} tasks / 个任务</span></div>'
        + table(["Locus / 位点", "Tool / Version / Revision", "Status / 状态", "Reason / 原因", "Patch / 补丁"], task_rows, empty="No task results recorded / 无任务结果")
        + "</section>"
        + f'<section id="reads-used" class="panel"><div class="panel-head"><h2>Reads / 输入测序数据</h2>'
        f'<span class="badge tone-neutral num">{len(read_rows):,} entries / 条</span></div>'
        + '<p class="muted">Private server file paths are intentionally omitted from shareable HTML reports; SHA-256 digests identify each consumed read input. '
        '/ 可分享 HTML 报告不公开服务器私有 reads 路径，仅保留技术类型与 SHA-256 摘要用于核验。</p>'
        + table(["Tool / 工具", "Technology / 类型", "Input / 输入来源", "SHA-256"], read_rows, empty="No reads recorded / 无测序数据记录")
        + "</section>"
    )
    subtitle = f"Batch: <code>{esc(batch_sha)}</code>" + (f" · Completed: <code>{esc(completed_at)}</code>" if completed_at else "")
    return page("Manual Refinement Batch / 手动精修批次报告", body, scope="CGAT Manual Refinement / 手动精修", subtitle=subtitle, nav=nav, badge=_batch_badge(state))


def render_overview(entries: list[dict[str, Any]]) -> str:
    rows = []
    pending_batches = 0
    no_patch_batches = 0
    total_patches = 0
    for entry in entries:
        summary = entry.get("summary") or {}
        results, batch_sha, completed_at = list(summary.get("results") or []), str(summary.get("batch_sha256") or ""), summary.get("completed_at")
        status = _batch_status(summary)
        if status == "pending_app_import":
            pending_batches += 1
        else:
            no_patch_batches += 1
        total_patches += sum(1 for row in results if isinstance(row.get("patch"), dict))
        tools: dict[str, str | None] = {}
        for r in results:
            name = str(r.get("tool") or "")
            if name and (name not in tools or tools[name] is None):
                tools[name] = r.get("version")
        tool_badges = [badge_html(f"{t} v{v}" if v else t, "neutral") for t, v in tools.items()]
        batch_cell = f'<code>{esc(_short(batch_sha, 16))}</code>' + (f'<div><small>{esc(completed_at)}</small></div>' if completed_at else "")
        rows.append((batch_cell, _batch_badge(status),
                     '<div class="count-chips">' + "".join(tool_badges) + "</div>" if tool_badges else '<span class="muted">—</span>',
                     _counts_html(results), _links_html(entry.get("links"))))
    metrics = _metrics_strip([
        ("Batches / 批次数", esc(fmt_int(len(entries))), "Recorded manual batches / 已记录手动批次"),
        ("Awaiting import / 等待导回", esc(fmt_int(pending_batches)), "Batches with candidate patches / 含候选补丁"),
        ("No patch / 无可导回补丁", esc(fmt_int(no_patch_batches)), "Zero importable patches / 无可导回补丁"),
        ("Candidate patches / 候选补丁", esc(fmt_int(total_patches)), "Not yet imported / 未自动写回"),
    ])
    return (
        '<section id="manual-refinement" class="panel"><div class="panel-head"><h2>04 · Manual Refinement / 手动精修</h2>'
        f'<span class="badge tone-neutral num">{len(entries):,} batches / 个批次</span></div>'
        + metrics
        + table(["Batch / 批次", "Status / 状态", "Tools / 工具", "Outcomes / 状态计数", "Links / 链接"], rows, empty="No manual refinement batches recorded / 暂无手动精修批次")
        + '<p class="muted">Manual refinement batches stay separate from automatic 05_final publications, omit private server read paths in HTML, and are never marked imported without an App receipt. '
        '/ 手动精修批次与自动 05_final 区分，HTML 报告不公开服务器私有 reads 路径，无 App 回执绝不标记为已导回。</p></section>'
    )


def render_landing(section: str, lgz_href: str | None) -> str:
    lgz_link = '<div class="link-row">' + link(lgz_href, "LGZ process report / LGZ 过程报告", cls="link-pill") + "</div>" if lgz_href else ""
    intro = (
        '<section id="lgz-baseline" class="panel is-baseline"><div class="panel-head"><h2>01 · LGZ Baseline / LGZ 基线</h2>'
        + badge_html("No automatic overview / 尚无自动总报告", "neutral") + "</div>"
        + callout(
            "当前工作区尚无自动精修总报告，本页仅汇总手动精修批次，不代表已发布自动终版 05_final/，也不代表补丁已导回 App。"
            " / No automatic refinement overview exists yet; this page lists manual refinement batches only and does not imply an automatic 05_final/ publication or App import.",
            tone="info",
            title="Manual Refinement Overview / 手动精修总览",
        )
        + lgz_link + "</section>"
    )
    nav = (link(lgz_href, "LGZ report / LGZ 报告") if lgz_href else "") + '<a href="#manual-refinement">04 · Manual Refinement / 手动精修</a>'
    return page("CGAT workflow / 流程总览（手动精修）", intro + "\n" + section, scope="CGAT Workflow Overview / 流程总览",
                subtitle="No automatic overview yet · Manual refinement only / 尚无自动总报告，仅展示手动精修",
                nav=nav, badge=badge_html("Manual only / 仅手动精修", "neutral"))



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
        lgz = layout.path("report/report.html")
        current = render_landing("", _relative(overview, lgz) if lgz.is_file() and not lgz.is_symlink() else None)
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
    return {"report": str(summary_path), "batch_report": str(batch_report), "overview": str(overview), "index": str(index)}
