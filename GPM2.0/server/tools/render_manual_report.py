"""Manual refinement report templates, no filesystem access."""
from __future__ import annotations

from typing import Any

try:
    from render_refinement_report import (
        badge_bi,
        badge_html,
        bi,
        callout,
        copy_btn,
        disclosure,
        esc,
        fmt_bp,
        fmt_int,
        kv_grid,
        link,
        table,
        workbench_page,
    )
except ModuleNotFoundError:
    from .render_refinement_report import (
        badge_bi,
        badge_html,
        bi,
        callout,
        copy_btn,
        disclosure,
        esc,
        fmt_bp,
        fmt_int,
        kv_grid,
        link,
        table,
        workbench_page,
    )

BATCH_STATUS = {
    "pending_app_import": ("等待导回 App", "Pending App import", "warn"),
    "no_patch": ("无可导回补丁", "No patch to import", "neutral"),
}
TASK_STATUS = {
    "closed": ("已闭合", "Closed", "ok", "is-closed"),
    "extended": ("端粒延伸", "Extended", "ok", "is-closed"),
    "partial": ("部分填补", "Partial", "info", "is-partial"),
    "no_candidate": ("无候选", "No candidate", "neutral", "is-unfilled"),
    "rejected": ("已拒绝", "Rejected", "err", "is-rejected"),
    "missing_reads": ("缺 reads", "Missing reads", "warn", "is-rejected"),
    "input_unavailable": ("输入不可用", "Input unavailable", "warn", "is-rejected"),
    "failed": ("失败", "Failed", "err", "is-rejected"),
    "incomplete": ("未完成", "Incomplete", "warn", "is-unfilled"),
}
KIND_LABELS = {"gap": ("缺口", "Gap"), "tel_left": ("左端粒", "Left telomere"), "tel_right": ("右端粒", "Right telomere")}
OP_LABELS = {"replace_gap": ("替换缺口", "Replace gap"), "prepend_tel": ("左端延伸", "Prepend telomere"), "append_tel": ("右端延伸", "Append telomere")}


def _short(value: Any, n: int = 12) -> str:
    text = str(value or "")
    return text[:n] if len(text) > n else text


def _batch_status(summary: dict[str, Any]) -> str:
    has_patch = any(isinstance(r.get("patch"), dict) for r in (summary.get("results") or []))
    return "pending_app_import" if summary.get("report_status") == "pending_app_import" and has_patch else "no_patch"


def _batch_badge(status: str) -> str:
    zh, en, tone = BATCH_STATUS.get(status, BATCH_STATUS["no_patch"])
    return badge_bi(zh, en, tone)


def _task_badge(status: Any) -> str:
    key = str(status or "not_recorded")
    zh, en, tone, _ = TASK_STATUS.get(key, (key, key, "neutral", "is-unfilled"))
    return badge_bi(zh, en, tone)


def _counts_html(results: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in results:
        key = str(row.get("status") or "not_recorded")
        counts[key] = counts.get(key, 0) + 1
    chips = []
    for k, n in counts.items():
        zh, en, _, cls = TASK_STATUS.get(k, (k, k, "neutral", "is-unfilled"))
        chips.append(f'<span class="count-chip {cls}">{bi(zh, en)} <b>{esc(fmt_int(n))}</b></span>')
    return '<div class="count-chips">' + "".join(chips) + "</div>" if chips else '<span class="muted">—</span>'


def _links_html(links: dict[str, str] | None) -> str:
    items = [link(href, label) for label, href in (links or {}).items() if href]
    return " · ".join(items) if items else '<span class="muted">—</span>'


def _locus_cell(locus_id: str, meta: dict[str, Any]) -> str:
    head = ([f'<strong>{esc(meta["chr"])}</strong>'] if meta.get("chr") else []) + ([f'<code>{esc(meta["target"])}</code>'] if meta.get("target") else [])
    k = str(meta.get("kind") or "")
    k_txt = bi(*KIND_LABELS[k]) if k in KIND_LABELS else esc(k)
    sub = ([k_txt] if k_txt else []) + ([f'<code>{esc(_short(locus_id, 12))}</code>'] if locus_id else [])
    return "".join(([" · ".join(head)] if head else []) + ([f'<div><small class="muted">{" · ".join(sub)}</small></div>'] if sub else [])) or '<span class="muted">—</span>'


def _tool_cell(row: dict[str, Any]) -> str:
    ver = f' <small class="muted">v{esc(row["version"])}</small>' if row.get("version") else ""
    return f'<strong>{esc(row.get("tool") or "—")}</strong>{ver}'


def _patch_cell(patch: Any) -> str:
    if not isinstance(patch, dict):
        return '<span class="muted">—</span>'
    op = str(patch.get("operation") or "patch")
    op_html = bi(*OP_LABELS[op]) if op in OP_LABELS else esc(op)
    sizes = ([f'{fmt_bp(patch["original_length"])}'] if patch.get("original_length") is not None else []) + (
        [f'{fmt_bp(patch["length"])}'] if patch.get("length") is not None else []
    )
    parts = [op_html] + ([f'<small class="num">{" → ".join(sizes)}</small>'] if sizes else [])
    if patch.get("path"):
        parts.append(f'<div><small><code>{esc(patch["path"])}</code></small></div>')
    return " ".join(parts)


def _read_rows(reads: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for tool, items in reads.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            tech = str(item.get("technology") or "unknown").upper()
            digest = str(item.get("sha256") or "")
            rows.append((
                f"<strong>{esc(tool)}</strong>",
                badge_html(tech, "neutral"),
                (f"<code>{esc(_short(digest, 20))}…</code> " + copy_btn(digest, zh="复制", en="Copy")) if digest else "—",
            ))
    return rows


def render_batch(summary: dict[str, Any], links: dict[str, str] | None) -> str:
    batch_sha, completed_at = str(summary.get("batch_sha256") or ""), summary.get("completed_at")
    results, loci, reads = list(summary.get("results") or []), summary.get("loci") or {}, summary.get("reads") or {}
    state = _batch_status(summary)
    patch_count = sum(1 for row in results if isinstance(row.get("patch"), dict))

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
    kv = [("Batch SHA-256", f"<code>{esc(batch_sha)}</code> " + copy_btn(batch_sha, zh="复制", en="Copy"))]
    if summary.get("export_id"):
        kv.append(("Export ID", f'<code>{esc(summary["export_id"])}</code>'))
    if summary.get("origin_fasta_sha256"):
        kv.append((bi("基线 FASTA 摘要", "Origin FASTA SHA-256"), f'<code>{esc(_short(summary["origin_fasta_sha256"], 20))}</code>'))
    if summary.get("delivery_sha256"):
        kv.append((bi("交付包摘要", "Delivery SHA-256"), f'<code>{esc(_short(summary["delivery_sha256"], 20))}</code>'))

    status_note = (
        bi("候选补丁需导回原 CGAT App 核对，不会自动写回 05_final/。", "Patches await CGAT App import and never overwrite automatic 05_final/.")
        if state == "pending_app_import"
        else bi("未产出可导回补丁，05_final/ 无变化。", "No importable patch produced; automatic 05_final/ unchanged.")
    )
    body = (
        '<section id="task-results" class="panel">'
        f'<div class="summary-line"><span><b>{len(loci):,}</b> {bi("位点", "loci")}</span>'
        f'<span><b>{len(results):,}</b> {bi("任务", "tasks")}</span>'
        f'<span><b>{patch_count:,}</b> {bi("候选补丁", "patches")}</span>'
        f'<span class="muted">{status_note}</span></div>'
        + (f'<div class="link-row">{"".join(link(h, l, cls="link-pill") for l, h in (links or {}).items() if h)}</div>' if links else "")
        + table(
            [bi("位点", "Locus"), bi("工具", "Tool"), bi("状态", "Status"), bi("原因", "Reason"), bi("补丁", "Patch")],
            task_rows,
            empty=bi("无任务结果", "No task results"),
        )
        + disclosure(
            bi("批次标识与输入测序数据摘要", "Batch digests & reads summary"),
            kv_grid(kv)
            + table([bi("工具", "Tool"), bi("类型", "Tech"), "SHA-256"], read_rows, empty=bi("无测序记录", "No reads")),
        )
        + "</section>"
    )
    subtitle = f"Batch <code>{esc(_short(batch_sha, 16))}</code>" + (f" · {esc(completed_at)}" if completed_at else "")
    return workbench_page(
        "手动精修批次",
        "Manual Refinement Batch",
        body,
        subtitle_html=subtitle,
        badge_html_str=_batch_badge(state),
    )


def render_overview(entries: list[dict[str, Any]]) -> str:
    rows = []
    for entry in entries:
        summary = entry.get("summary") or {}
        results, batch_sha, completed_at = list(summary.get("results") or []), str(summary.get("batch_sha256") or ""), summary.get("completed_at")
        status = _batch_status(summary)
        tools = list(dict.fromkeys(str(r.get("tool") or "") for r in results if r.get("tool")))
        batch_cell = f'<code>{esc(_short(batch_sha, 12))}</code>' + (f' <small class="muted">{esc(completed_at)}</small>' if completed_at else "")
        rows.append((
            batch_cell,
            _batch_badge(status),
            ", ".join(esc(t) for t in tools) or "—",
            _counts_html(results),
            _links_html(entry.get("links")),
        ))
    return (
        '<section id="manual-refinement" class="panel">'
        f'<div class="panel-head"><h2>{bi("手动精修", "Manual Refinement")}</h2></div>'
        + table(
            [bi("批次", "Batch"), bi("状态", "Status"), bi("工具", "Tools"), bi("任务结果", "Outcomes"), bi("链接", "Links")],
            rows,
            empty=bi("暂无手动精修批次", "No manual refinement batches"),
        )
        + '<p class="muted">' + bi("独立于自动 05_final/；无 App 回执不标记为已导回。", "Separate from automatic 05_final/; never marked imported without an App receipt.") + '</p>'
        + "</section>"
    )


def render_landing(section: str, lgz_href: str | None) -> str:
    lgz_part = f' · {link(lgz_href, bi("LGZ 过程报告 →", "LGZ report →"), raw=True)}' if lgz_href else ""
    intro = (
        '<section id="lgz-baseline" class="panel">'
        f'<p>{bi("尚无自动总报告，仅展示手动精修批次。", "No automatic overview yet; manual refinement batches only.")}{lgz_part}</p>'
        "</section>"
    )
    return workbench_page(
        "CGAT 手动精修",
        "CGAT Manual Refinement",
        intro + "\n" + section,
    )
