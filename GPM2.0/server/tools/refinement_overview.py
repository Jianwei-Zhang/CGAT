"""Current-batch overview with a shared original-gap denominator, no ranking."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import uuid
from urllib.parse import quote

try:
    from refine_report import merge_manual_overview
    from workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, relative_path
    from refinement_reports import (
        page, table, link, ReportError, stat_key,
        esc, fmt_int, badge_html, status_badge, callout, format_counts_html, kv_grid, PHASE_LABELS,
    )
    from refinement_tools import fingerprint
    from refinement_commit import current_publication
    from run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
except ModuleNotFoundError:
    from .refine_report import merge_manual_overview
    from .workspace_layout import WorkspaceLayout, TOOL_DIRECTORIES, relative_path
    from .refinement_reports import (
        page, table, link, ReportError, stat_key,
        esc, fmt_int, badge_html, status_badge, callout, format_counts_html, kv_grid, PHASE_LABELS,
    )
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


def local_href(root, page_path, target):
    if not target.resolve().is_relative_to(root) or not target.is_file():
        raise ReportError("overview link is outside its workspace or missing")
    return Path(os.path.relpath(target, page_path.parent)).as_posix()


def local_link(root, page_path, target, label, *, cls=None):
    return link(local_href(root, page_path, target), label, cls=cls)


def step_link(number, href, label):
    return (
        f'<a class="step-link" href="{quote(href, safe="/#-_.")}">'
        f'<span class="step-num">{esc(number)}</span><span>{esc(label)}</span></a>'
    )


def render_overview(root, batch, results):
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
                     "counts": summary.get("counts"), "error": record.get("error"), "phase": record.get("phase"),
                     "actual_threads": summary.get("execution", {}).get("threads"),
                     "requested_thread_budget": batch.get("threads"), "result_reused": bool(record.get("reused_from")),
                     "native_reused": bool(record.get("native_reused") or record.get("reused_from")),
                     "native_origin": record.get("native_origin"),
                     "timing": summary.get("execution", {}).get("timing"),
                     "reads": recipe.get("reads", []), "input_selection": recipe.get("original_selection"),
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
    lgz_report = layout.path("report/report.html")
    has_lgz_report = lgz_report.is_file()
    comparison_json = comparison_dir / "comparison.json"
    gap_tsv = comparison_dir / "gap_comparison.tsv"

    nav_html = "".join((
        step_link("01", "#lgz-baseline", "LGZ Baseline / LGZ 基线"),
        step_link("02", "#refinement-comparison", "Refinement / 精修"),
        step_link("03", "#comparison-data", "Comparison data / 对照数据") if compare else "",
    ))

    # A current receipt for a reused run ID is not sufficient to relabel a
    # staged or failed attempt as published. Preserve the comparison data ABI.
    published_tools = {row["tool"] for row in rows if not invalidated
                       and batch["tools"][row["tool"]]["status"] == "published"
                       and row["publication_transaction"]
                       and row["publication_transaction"] == batch["tools"][row["tool"]].get("publication_transaction")}
    published_count = len(published_tools)
    batch_state = batch["status"]
    if batch_state == "published" and published_count != len(rows):
        batch_state = "publication_unverified"
    denom_html = (
        f'<span class="num">{esc(fmt_int(comparison["original_gap_count"]))}</span>'
        if comparison["original_gap_count"] is not None
        else '<span class="muted">Unavailable (invalidated) / 不可用（已失效）</span>' if invalidated
        else '<span class="muted">No refinement requested / 本轮未请求精修</span>'
    )

    body = '<section class="panel"><h2>Batch Summary / 批次摘要</h2>'
    if invalidated:
        body += callout(
            "This batch or its LGZ baseline is marked <code>invalidated</code>. Original gap counts are unavailable (not zero) and no delivery in this batch is published. "
            "/ 本批次或 LGZ 基线已失效；原始缺口统计不可用（不计为 0），本批次无已发布交付。",
            tone="err",
            title="Batch Invalidated / 批次已失效",
        )
    body += kv_grid([
        ("Original LGZ gap denominator / 原始 LGZ 缺口数", denom_html),
        ("Verified publications in batch / 本批已发布工具", f'<span class="num">{published_count:,} / {len(rows):,}</span>'),
    ])
    body += '</section>'

    # LGZ Baseline section — visibly distinct from refined delivery
    try:
        from lgz_final import validate_baseline
    except ModuleNotFoundError:
        from .lgz_final import validate_baseline
    baseline_valid_ok = (not invalidated) and bool(validate_baseline(root))
    body += (
        '<section id="lgz-baseline" class="panel is-baseline">'
        '<div class="panel-head"><h2>01 · LGZ Baseline / LGZ 基线（非精修结果）</h2>'
        + '</div>'
        '<p class="muted">LGZ baseline outputs define the shared original-gap denominator and are kept separate from post-LGZ refinement deliveries. '
        '/ LGZ 基线定义了共享原始缺口分母，与 LGZ 后的精修交付严格区分。</p>'
    )
    baseline_action_links = []
    if has_lgz_report:
        baseline_action_links.append(local_link(root, report, lgz_report, "LGZ process report / LGZ 过程报告", cls="link-pill"))
    body += '<div class="link-row">' + "".join(baseline_action_links) + '</div>'
    if baseline_valid_ok:
        baseline_file_links = "".join(
            local_link(root, report, layout.path("05_final/00_lgz/" + name), label, cls="link-pill")
            for name, label in (
                ("assembly.fa", "LGZ FASTA"),
                ("final_path.json", "LGZ Final Path"),
                ("provenance.json", "Baseline provenance / 基线来源"),
            )
        )
        body += (
            '<div class="link-row">' + baseline_file_links + '</div>'
        )
    elif invalidated:
        body += '<p class="muted">LGZ baseline files are withheld because this batch is invalidated. / 批次已失效，不展示基线交付链接。</p>'
    else:
        body += '<p class="muted">Validated LGZ baseline delivery files are not currently present. / 当前未检测到已验证的 LGZ 基线文件。</p>'
    body += '</section>'

    # Refinement comparison table
    display = []
    for row in rows:
        record = batch["tools"][row["tool"]]
        tool_tags = []
        if row.get("result_reused"):
            tool_tags.append(badge_html("Result reused / 复用结果", "warn"))
        elif row.get("native_reused"):
            tool_tags.append(badge_html("Native reused / 复用原生", "warn"))
        tool_cell = f'<strong>{esc(row["tool"])}</strong>'
        if tool_tags:
            tool_cell += '<div style="margin-top:.25rem">' + " ".join(tool_tags) + '</div>'
        if row.get("run_id"):
            tool_cell += f'<div><small><code>{esc(row["run_id"])}</code></small></div>'

        state = record["status"]
        if invalidated:
            state = "invalidated"
        elif state == "published" and row["tool"] not in published_tools:
            state = "publication_unverified"
        state_cell = status_badge(state)
        counts_cell = format_counts_html(row["counts"], status=state, invalidated=invalidated)

        report_link = '<span class="muted">No completed report / 无完整报告</span>'
        if row["tool"] in published_tools:
            # Keep the current-process link inside a copied 06_report tree.
            # Only the matching verified publication can use this public slot.
            target = layout.path(f"06_report/02_refinement/{TOOL_DIRECTORIES[row['tool']]}/report.html")
            report_link = local_link(root, report, target, "Jobs, native evidence, decisions / 任务、原生证据与接纳", cls="link-pill")
        elif record.get("report", {}).get("report") and Path(record["report"]["report"]).is_file():
            report_link = local_link(root, report, Path(record["report"]["report"]),
                                     "Attempt diagnostics (workspace) / 尝试诊断（工作区）", cls="link-pill")
        if not record.get("report") and row["run_id"]:
            failed_log = layout.path(f"04_refinement/{TOOL_DIRECTORIES[row['tool']]}/02_jobs/{row['run_id']}/native.log")
            if failed_log.is_file():
                report_link = local_link(root, report, failed_log, "Native execution log / 原生执行日志", cls="link-pill")

        reason_bits = []
        if row.get("phase") and state in {"failed", "invalidated", "interrupted", "running"}:
            phase = PHASE_LABELS.get(row["phase"], row["phase"])
            reason_bits.append(f'<div><small>Phase / 阶段:</small> {esc(phase)}</div>')
        if state == "publication_unverified":
            reason_bits.append("No matching publication receipt / 无匹配的发布回执")
        if row.get("error"):
            reason_bits.append(f'<div style="color:var(--tone-err-ink)">{esc(row["error"])}</div>')
        reason_cell = "".join(reason_bits) if reason_bits else '<span class="muted">—</span>'

        if row["tool"] in published_tools:
            code = TOOL_DIRECTORIES[row["tool"]]
            pub_links = [
                local_link(root, report, layout.path(f"05_final/{code}/{name}"), label, cls="link-pill")
                for name, label in (
                    ("assembly.fa", "Final FASTA"),
                    ("final_path.json", "Final Path"),
                    ("provenance.json", "Provenance / 来源"),
                )
            ]
            delivery_dir = layout.path(f"07_delivery/{code}")
            delivery = json.loads((delivery_dir / "delivery.json").read_text())
            if layout.project_delivery:
                from project_delivery_publish import tool_links
                files = tool_links(layout,row["tool"],row["run_id"],delivery["light_manifest"])
                pub_links.extend(local_link(root, report, layout.path(path), label, cls="link-pill")
                                 for mode,label in (("full","Project Full"),("light","Project Light")) if (path := files.get(mode)))
            else:
                pub_links += [
                    local_link(root, report, delivery_dir / relative_path(delivery["archives"][mode]["file"]), label, cls="link-pill")
                    for mode, label in (("full", "Full App package / 完整包"), ("light", "Light App package / 轻量包"))
                ]
            final_links = '<div class="link-row">' + "".join(pub_links) + '</div>'
        elif invalidated:
            final_links = '<span class="muted">Invalidated — not published / 已失效，未发布</span>'
        else:
            final_links = '<span class="muted">Not published in this batch / 本批次尚未发布</span>'

        display.append((tool_cell, state_cell, counts_cell, report_link, reason_cell, final_links))

    body += (
        '<section id="refinement-comparison" class="panel">'
        '<div class="panel-head"><h2>02 · Refinement Comparison / 精修工具对照</h2>'
        f'<span class="badge tone-neutral num">{len(rows):,} tools / 个工具</span></div>'
        + table(
            [
                "Tool / 工具",
                "State / 状态",
                "Accepted gap outcomes / 接纳缺口结果",
                "Process report / 过程报告",
                "Phase & reason / 阶段与原因",
                "Final publication / 最终发布",
            ],
            display,
            empty="No refinement tools recorded in this batch / 本批次无精修工具记录",
        )
        + '<p class="muted">Final files are shown only for verified publications in this batch. / 仅展示本批次经回执验证的交付文件。</p>'
        + '</section>'
    )
    if compare:
        body += (
            '<section id="comparison-data" class="panel"><h2>03 · Comparison Data / 对照数据</h2>'
            '<p>Gap counts do not measure biological accuracy or rank tools. / 缺口数不代表生物学准确率，也不用于工具排名。</p>'
            '<div class="link-row">'
            + local_link(root, report, comparison_json, "Comparison JSON / 比较 JSON", cls="link-pill")
            + local_link(root, report, gap_tsv, "Original gap outcomes TSV / 原始缺口对照", cls="link-pill")
            + '</div></section>'
        )
    write_html(
        report,
        merge_manual_overview(layout, page(
            "CGAT workflow / 流程总览",
            body,
            scope="CGAT Workflow Overview / 流程总览",
            subtitle=f'Batch: <code>{esc(batch["batch_id"])}</code> · Exit code: <code>{esc(batch["exit_code"])}</code>',
            nav=nav_html,
            badge=status_badge(batch_state),
        )),
    )
    if not compare:
        return {"report": str(report)}
    return {"report": str(report), "comparison": str(comparison_dir / "comparison.json"),
            "gap_comparison": str(comparison_dir / "gap_comparison.tsv")}
