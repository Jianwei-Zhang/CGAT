#!/usr/bin/env python3
"""Regenerate report.html using only this directory and Python's standard library."""
from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
from pathlib import Path

SCHEMA = "cgat_server_report_v1"
REPORT_PREVIEW_ROWS = 200


def project_report_facts(facts: dict) -> dict:
    projected = dict(facts)
    projected_tables = {}
    for name, value in facts.get("tables", {}).items():
        rows = value.get("rows", [])
        count = value.get("row_count", len(rows))
        projected_tables[name] = {
            **value,
            "rows": rows[:REPORT_PREVIEW_ROWS],
            "row_count": count,
            "preview_only": count > min(len(rows), REPORT_PREVIEW_ROWS),
        }
    if "tables" in facts:
        projected["tables"] = projected_tables
    if isinstance(facts.get("result"), dict):
        result = dict(facts["result"])
        counts = dict(result.get("report_array_counts", {}))
        audit_arrays = {
            "events", "strategies", "classification_rows", "terminal_rows",
            "evidence_rows", "usage_rows", "q_rows", "attempts",
        }
        for key, value in list(result.items()):
            if key in audit_arrays and isinstance(value, list):
                counts.setdefault(key, len(value))
                if key != "events":
                    result[key] = value[:REPORT_PREVIEW_ROWS]
        for key, name in (("evidence_rows", "evidence"), ("usage_rows", "usage"), ("q_rows", "q_segments")):
            table = projected_tables.get(name)
            if key in result and table and table.get("available"):
                result[key] = {"report_table": name, "row_count": table["row_count"], "source": table.get("source")}
        if counts:
            result["report_array_counts"] = counts
        projected["result"] = result
    return projected


def project_report_record(record: dict) -> dict:
    return {**record, "facts": project_report_facts(record.get("facts", {}))}


LABELS = {
    "degap_gapfill": "LGZ 后 DEGAP 补洞", "gap_count": "原始 gap 数",
    "accepted_count": "已接纳 gap 数", "unfilled_count": "保留 gap 数",
    "reads_type": "Reads 类型", "lgz_unchanged": "保留原始 LGZ",
    "gap_decisions": "逐 gap 接纳记录",
    "success": "完成", "failed": "失败", "interrupted": "中断", "pending": "未执行",
    "running": "运行中", "prepared": "输入已准备，等待运行", "preparing": "准备中",
    "computed": "本次执行", "cache_reused": "复用已验证缓存",
    "frozen_original_lgz": "保留原引擎 LGZ 结果（未重新运行）", "not_started": "尚未开始",
    "see_parent_unit": "执行方式见所属阶段", "accepted": "接受", "rejected": "拒绝",
    "unresolved": "未解决", "superseded": "已被替换", "not_finalized": "尚未最终确认",
    "not_enabled": "未启用", "measured": "已测量", "enabled": "已启用",
    "reference": "参考序列", "primary": "主组装", "support": "辅助组装",
    "assembly_candidate": "候选组装", "not_measured": "未测量",
    "partial_path": "可用路径（完整性未确认）", "not_constructed": "未构建",
    "input_assembly_gap": "输入原有 N 连接", "reference_unknown": "新增未知连接",
    "sequence_overlap": "序列证据支持的 overlap",
    "q0_unused_source_intervals": "未选区间（包括冗余或未通过筛选的来源）",
    "q0_candidate_admission": "候选准入过程记录", "unplaced_component_count": "未准入的逻辑区段数",
    "ambiguous_interval_count": "歧义区间数", "evidence_count": "证据记录数",
    "q0_chromosomes": "各 chr 的构建范围", "q0_source_composition": "各 chr 的来源构成",
    "q0_retained_joins": "q0 最终保留的连接", "q0_reference_unrepresented": "参考未被选中锚点覆盖的范围",
    "q0_source_unrepresented": "候选来源未被路径表示的范围", "q0_search": "有界搜索记录（不是修补计数）",
    "selected_chromosomes": "已有路径的 chr 数", "not_constructed_chromosomes": "未构建的 chr 数",
    "selected_datasets": "实际采用的 ds 数", "selected_source_bp": "来源片段长度 / bp",
    "source_bp_by_dataset": "各 ds 来源片段 / bp", "source_bp": "来源片段 / bp",
    "source_piece_count": "来源片段数", "source_contig_count": "原始 contig 数",
    "input_gap_joins": "原有 N 连接数", "input_gap_n_bp": "原有连接 N / bp",
    "unknown_joins": "新增未知连接数", "unknown_join_n_bp": "新增未知连接 N / bp",
    "sequence_overlap_joins": "最终保留的 overlap 连接数", "qc": "输入质量评估状态",
    "reference_unrepresented_bp": "参考未被选中锚点覆盖 / bp",
    "search_operation_counts": "搜索过程操作数", "global_optimality_claimed": "是否声称全局最优",
    "pruning_record_counts": "剪枝记录数（按类型）",
    "evaluations": "候选评估次数", "rounds": "搜索轮数", "stop_reasons": "停止原因",
    "sequence_count": "序列数", "length_bp": "总长度 / bp", "n_bp": "N 碱基数",
    "gap_count": "Gap 数（连续 N ≥100 bp）", "gap_bp": "Gap 长度 / bp", "n50_bp": "N50 / bp",
    "alignment_count": "比对记录数", "aligned_query_count": "有比对的 contig 数",
    "unaligned_query_count": "无比对的 contig 数", "assignment_rows": "归属记录数",
    "assigned_unique_contigs": "已分配的唯一 contig 数", "unassigned_contigs": "未分配 contig 数",
    "reads_qc": "Reads 质量评估", "event_count": "事件数", "by_status": "事件状态",
    "by_action": "处理动作", "by_reason": "原因分布", "available": "记录可用",
    "alignment_task_count": "染色体比对任务数", "self_alignment": "自比对",
    "archive": "交付文件", "staging_ready": "App 数据载荷已就绪",
    "payload_file_count": "App 数据载荷文件数", "payload_size_bytes": "App 数据载荷大小 / bytes",
    "payload_archive_size_bytes": "App 数据载荷大小 / bytes",
    "payload_archive_sha256": "App 数据载荷 SHA-256", "checksum_scope": "校验范围",
    "sequence": "序列", "aligned_bp": "比对覆盖 / bp",
    "coverage_percent": "覆盖率 / %", "dataset_name": "数据集", "contig_name": "Contig",
    "seq_name": "Contig", "assigned_chr_name": "归属染色体", "source_orientation": "方向",
    "support_bp": "支持长度 / bp", "support_percent": "支持覆盖率 / %",
    "anchor_start": "排列锚点", "reason": "原因", "status": "状态", "chr": "染色体",
    "event_id": "事件 ID", "stage": "阶段", "action": "动作", "event_reconciliation": "过程与最终状态",
    "process_status": "阶段结束时状态", "process_reason": "当时原因", "final_status": "最终状态",
    "final_reason": "最终原因", "final_path_segment_ids": "最终路径片段", "final_event": "最终事件详情",
    "source_dataset": "来源数据集", "source_contig": "来源 Contig", "source_start": "来源起点",
    "source_end": "来源终点", "orientation": "方向", "q_start": "结果起点", "q_end": "结果终点",
    "q_version": "序列版本", "qv": "输入 QV", "craq": "输入 CRAQ", "reads_qc_pass": "Reads QC 通过",
    "candidate_count": "候选数", "outcome": "处理结果", "file": "文件", "size_bytes": "大小 / bytes",
    "fill": "填补", "filter_component": "片段过滤", "extend_telomere": "端粒延伸",
    "source": "主路径来源", "gap": "Gap", "patch": "补丁 / 替换",
    "upstream_external_contigs_stage1_noop": "外部 contig 模式：本阶段保留原序列",
    "deferred_to_post_correction_optimized_fill": "延后至结构修正后的优化填补",
    "no_assignment_passing_filters_and_coverage_threshold": "无通过过滤及覆盖率阈值的归属",
    "no_gaps": "没有待处理 gap", "no_patch_fixer": "无补丁候选，进入结构修正",
    "full_fixer_reuse_patches": "补丁均未接受，进入结构修正分支",
    "partial_success_no_fixer": "补丁部分成功，保留补丁结果",
    "coverage": "Contig 比对覆盖", "assignments": "染色体归属", "track_order": "排列顺序",
    "unassigned": "未分配序列", "recipe": "锁定的处理方案", "quality": "输入质量评估",
    "selection": "序列入选与排除", "donor_sets": "供体集合", "donor_members": "供体成员",
    "q_segments": "序列组成", "telomere_rules": "端粒规则", "tools": "工具与版本",
    "candidates": "候选明细", "rejections": "拒绝原因", "arbitration": "候选仲裁",
    "gap_attempts": "Gap 处理尝试", "terminal_status": "染色体端点状态", "terminal_rows": "端点处理",
    "strategies": "按染色体处理分支", "classification_rows": "结构问题分类",
    "alignments": "比对任务", "telomeres": "端粒注释", "centromeres": "着丝粒候选区域",
    "used_contigs": "最终使用的 Contig", "evidence": "证据记录", "usage": "供体使用记录",
}
PREPARE_IDS = ("lgz_prepare", "grt_prepare")

METHODS = {
    "prepare": "记录原始文件身份与统计。",
    "assign": "按参考比对分配染色体与顺序。",
    "degap_gapfill": "使用 reads 补剩余内部 gap，保留原 LGZ 结果。",
    **dict.fromkeys(PREPARE_IDS, "构建 q0 并锁定供体。"),
    "step1": "补丁验证与分支选择，生成 q1。",
    "step2": "结构修正与优化填补，生成 q2。",
    "step3": "端粒检查与延伸，生成 q3 / Final Path。",
}


def label(value) -> str:
    return LABELS.get(str(value), str(value))


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def bi(zh: str, en: str) -> str:
    return f'<span class="t-zh">{esc(zh)}</span><span class="t-en">{esc(en)}</span>'


def display(value) -> str:
    if value is None or value == "":
        return "未记录"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, dict):
        return "；".join(f"{k}：{display(v)}" for k, v in value.items()) or "无"
    if isinstance(value, list):
        return "、".join(display(v) for v in value) or "无"
    return str(value)


def fmt_duration(value) -> str:
    try:
        sec = float(value)
    except (TypeError, ValueError):
        return "—"
    if sec < 0:
        return "—"
    if sec < 60:
        return f"{sec:.1f}s" if sec < 10 else f"{sec:.0f}s"
    total = int(round(sec))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def exec_label(record: dict) -> str:
    execution = record.get("execution", "")
    if record.get("status") == "success" and execution in ("", "not_started", "pending", None):
        return "并行已完成"
    return label(execution or "unknown")


def load(root: Path, relative: str, optional=False):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"report path escapes directory: {relative}")
    if optional and not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def key_values(values: dict) -> str:
    return '<dl class="facts">' + "".join(
        f"<div><dt>{esc(label(key))}</dt><dd>{esc(display(value))}</dd></div>"
        for key, value in values.items()
    ) + "</dl>"


def notes(values: list) -> str:
    return "".join(f'<p class="note">{esc(value)}</p>' for value in values)


def compact_number(value) -> str:
    if not isinstance(value, (int, float)):
        return display(value)
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} Gb"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f} Mb"
    if absolute >= 1_000:
        return f"{value / 1_000:.1f} kb"
    return f"{value:,}"


def sequence_snapshot(version: str, stats: dict | None) -> str:
    if not stats:
        return f'<strong>{esc(version)}</strong><span class="muted">尚不可用</span>'
    return (
        f'<strong>{esc(version)}</strong><span>{esc(compact_number(stats.get("length_bp")))} · '
        f'{esc(display(stats.get("sequence_count")))} 条 · {esc(display(stats.get("gap_count")))} Gap</span>'
    )


def stage_io_html(record: dict) -> str:
    facts = record.get("facts", {})
    result = facts.get("result", {})
    versions = facts.get("sequence_versions", {})
    stage_id = record.get("stage_id", "")
    input_version, output_version = result.get("q_input_version"), result.get("q_output_version")
    if input_version:
        input_body = sequence_snapshot(input_version, versions.get(input_version))
    elif stage_id.startswith("ref:"):
        input_body = f'<strong>{esc(stage_id.split(":", 1)[1])}</strong><span>参考 FASTA</span>'
    elif stage_id == "assign":
        input_body = '<strong>参考比对 PAF</strong>'
    elif stage_id in PREPARE_IDS:
        input_body = '<strong>多组装候选证据</strong>' if facts.get("q0_construction") else '<strong>归属与排列</strong>'
    else:
        input_body = '<strong>上游输入</strong>'

    outputs = facts.get("outputs", [])
    if output_version:
        output_body = sequence_snapshot(output_version, versions.get(output_version))
    elif stage_id.startswith("ref:"):
        s = facts.get("summary", {})
        output_body = f'<strong>PAF</strong><span>{esc(display(s.get("alignment_count")))} 条比对</span>'
    elif stage_id == "assign":
        s = facts.get("summary", {})
        output_body = f'<strong>归属</strong><span>{esc(display(s.get("assigned_unique_contigs")))} 已分配</span>'
    elif stage_id in PREPARE_IDS:
        output_body = sequence_snapshot("q0", versions.get("q0"))
    elif outputs:
        output_body = f'<strong>{esc(outputs[0].get("file", "交付文件"))}</strong><span>{esc(compact_number(outputs[0].get("size_bytes")))}</span>'
    else:
        output_body = '<strong>阶段输出</strong>'

    method = METHODS.get(stage_id, record.get("title", "执行阶段"))
    return (
        f'<div class="io-flow"><div class="io-card"><small>INPUT</small>{input_body}</div>'
        f'<div class="io-arrow" aria-hidden="true">→</div><div class="io-card"><small>PROCESS</small><span>{esc(method)}</span></div>'
        f'<div class="io-arrow" aria-hidden="true">→</div><div class="io-card"><small>OUTPUT</small>{output_body}</div></div>'
    )


def pipeline_map_html(records: list[dict], input_facts: dict, final: dict) -> str:
    datasets = input_facts.get("datasets", [])
    refs = [row for row in records if row.get("stage_id", "").startswith("ref:")]
    assignment = next((row for row in records if row.get("stage_id") == "assign"), {})
    prepare_record = next((row for row in records if row.get("stage_id") in PREPARE_IDS), {})
    q0 = prepare_record.get("facts", {}).get("sequence_versions", {}).get("q0", {})
    q_final = final.get("sequence_versions", {}).get(final.get("final_q_version", "q4"), {})
    assigned = assignment.get("facts", {}).get("summary", {}).get("assigned_unique_contigs")
    chain = "q0 → q1 → q2 → q3" if final.get("final_q_version") == "q3" else "q0 → q1 → q2 → q3 → q4"
    stages = [
        ("原始输入", f"{len(datasets)} 组 FASTA", "#inputs"),
        ("参考比对", f"{len(refs)} 任务", "#process"),
        ("染色体归属", f"{display(assigned)} contigs", "#process"),
        ("构建 q0", f"{display(q0.get('gap_count'))} Gap", "#q0-construction" if final.get("q0_construction") else "#results"),
        ("LGZ 修复", chain, "#grt-flow"),
        ("Final Path", f"{compact_number(q_final.get('length_bp'))}", "#results"),
        ("证据交付", f"{display(final.get('process_summary', {}).get('event_count'))} 事件", "#delivery"),
    ]
    cards = []
    for idx, (title, metric, href) in enumerate(stages):
        cards.append(f'<a class="pipeline-node" href="{esc(href)}"><strong>{esc(title)}</strong><small>{esc(metric)}</small></a>')
        if idx < len(stages) - 1:
            cards.append('<span class="pipeline-arrow" aria-hidden="true">→</span>')
    return '<div class="pipeline-map">' + "".join(cards) + '</div>'


def svg_evolution_html(order: list[str], stats_by_version: dict) -> str:
    if len(order) < 2:
        return ""
    w, h = max(560, len(order) * 135 + 140), 214
    pl, pr, pt, pb = 76, 52, 34, 40
    pw, ph = w - pl - pr, h - pt - pb
    lens = [int((stats_by_version[v] or {}).get("length_bp") or 0) for v in order]
    n50s = [int((stats_by_version[v] or {}).get("n50_bp") or 0) for v in order]
    gaps = [(stats_by_version[v] or {}).get("gap_count") for v in order]
    max_len = max([*lens, *n50s, 1])
    gap_vals = [g for g in gaps if isinstance(g, int)]
    max_gap = max(gap_vals) if gap_vals and max(gap_vals) > 0 else 1
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="LGZ sequence version evolution">']
    for i in range(4):
        gy = pt + ph * i / 3
        lv = max_len * (3 - i) / 3
        parts.append(f'<line x1="{pl}" y1="{gy:.1f}" x2="{w - pr}" y2="{gy:.1f}" stroke="var(--border-subtle)" stroke-dasharray="2 3"/>')
        parts.append(f'<text x="{pl - 8}" y="{gy + 4:.1f}" text-anchor="end" fill="var(--muted)" font-size="10.5">{esc(compact_number(lv))}</text>')
    parts.append(f'<text x="{pl}" y="14" fill="var(--muted)" font-size="10.5" font-weight="600">Length / N50</text>')
    parts.append(f'<text x="{w - pr}" y="14" text-anchor="end" fill="var(--gap)" font-size="10.5" font-weight="600">Gaps (≥100 N)</text>')
    step_x = pw / len(order)
    bar_w = min(28, step_x * 0.22)
    pts = []
    for idx, ver in enumerate(order):
        st = stats_by_version[ver] or {}
        cx = pl + step_x * (idx + 0.5)
        lb, n5 = int(st.get("length_bp") or 0), int(st.get("n50_bp") or 0)
        lh, nh = ph * lb / max_len, ph * n5 / max_len
        parts.append(f'<rect x="{cx - bar_w - 2:.1f}" y="{pt + ph - lh:.1f}" width="{bar_w:.1f}" height="{max(2.0, lh):.1f}" rx="2" fill="var(--source)" opacity=".88"><title>{esc(ver)} Length: {lb:,} bp</title></rect>')
        parts.append(f'<rect x="{cx + 2:.1f}" y="{pt + ph - nh:.1f}" width="{bar_w:.1f}" height="{max(2.0, nh):.1f}" rx="2" fill="var(--telomere)" opacity=".88"><title>{esc(ver)} N50: {n5:,} bp</title></rect>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 17}" text-anchor="middle" fill="var(--ink)" font-size="11.5" font-weight="600">{esc(ver)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 3}" text-anchor="middle" fill="var(--muted)" font-size="10">{esc(compact_number(lb))}</text>')
        g = st.get("gap_count")
        if isinstance(g, int):
            gy = pt + ph - (ph * g / max_gap if max_gap > 0 else 0)
            pts.append((cx, gy, ver, g))
    if len(pts) >= 2:
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y, _, _) in enumerate(pts))
        parts.append(f'<path d="{d}" fill="none" stroke="var(--gap)" stroke-width="2" stroke-linecap="round"/>')
    for x, y, ver, g in pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var(--surface-panel)" stroke="var(--gap)" stroke-width="2"><title>{esc(ver)} Gaps: {g:,}</title></circle>')
        parts.append(f'<text x="{x:.1f}" y="{max(pt - 10, y - 9):.1f}" text-anchor="middle" fill="var(--gap)" font-size="10.5" font-weight="600">{g:,}</text>')
    parts.append("</svg>")
    return (
        '<div class="chart-box">' + "".join(parts)
        + '<div class="legend"><span><i class="legend-dot source"></i>总长度</span>'
        '<span><i class="legend-dot" style="background:var(--telomere)"></i>N50</span>'
        '<span><i class="legend-dot" style="background:var(--gap)"></i>Gap (≥100 N)</span></div></div>'
    )


def timing_waterfall_html(records: list[dict]) -> str:
    measured = []
    for rec in records:
        el = (rec.get("runtime") or {}).get("elapsed_seconds")
        try:
            sec = float(el)
        except (TypeError, ValueError):
            continue
        if sec >= 0:
            measured.append((rec.get("title") or rec.get("stage_id", ""), sec, rec.get("status", ""), rec.get("execution", "")))
    if not measured:
        return ""
    measured.sort(key=lambda r: -r[1])
    top = measured[:10]
    max_s = max((r[1] for r in top), default=1) or 1.0
    row_h, w, lbl_w, bar_max = 28, 640, 185, 305
    h = len(top) * row_h + 10
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Stage runtime hotspots">']
    for idx, (title, sec, st, ex) in enumerate(top):
        y = 5 + idx * row_h
        bw = max(3.0, bar_max * sec / max_s) if sec > 0 else 2.0
        col = "var(--gap)" if st == "failed" else "var(--telomere)" if ex == "cache_reused" else "var(--patch)" if idx == 0 and sec >= 60 else "var(--source)"
        short = title if len(title) <= 22 else title[:20] + "…"
        tag = label(ex) if ex == "cache_reused" else ("并行完成" if st == "success" and ex in ("", "not_started") else label(st))
        parts.append(
            f'<g><text x="{lbl_w - 8}" y="{y + 17}" text-anchor="end" fill="var(--ink)" font-size="11.5"><title>{esc(title)}</title>{esc(short)}</text>'
            f'<rect x="{lbl_w}" y="{y + 6}" width="{bar_max}" height="14" rx="3" fill="var(--surface-muted)"/>'
            f'<rect x="{lbl_w}" y="{y + 6}" width="{bw:.1f}" height="14" rx="3" fill="{col}"><title>{esc(title)}: {esc(fmt_duration(sec))}</title></rect>'
            f'<text x="{lbl_w + bar_max + 10}" y="{y + 17}" fill="var(--ink)" font-size="11.5" font-weight="600">{esc(fmt_duration(sec))}</text>'
            f'<text x="{lbl_w + bar_max + 76}" y="{y + 17}" fill="var(--muted)" font-size="10.5">{esc(tag)}</text></g>'
        )
    parts.append("</svg>")
    return '<div class="chart-box">' + "".join(parts) + '</div>'


def lgz_flow_html(grt: list[dict], final: dict) -> str:
    stats_by_version = {}
    for record in grt:
        stats_by_version.update(record.get("facts", {}).get("sequence_versions", {}))
    stats_by_version.update(final.get("sequence_versions", {}))
    order = [v for v in ("q0", "q0r1", "q0f", "q1", "q2", "q3", "q4") if v in stats_by_version]
    if not order:
        return '<p class="note">LGZ 序列版本尚不可用。</p>'
    chain = " → ".join(order)
    return (
        f'<div class="grt-flow" id="grt-flow"><span class="muted">版本序列：<b>{esc(chain)}</b></span></div>'
        + svg_evolution_html(order, stats_by_version)
    )


def outcome_summary_html(final: dict) -> str:
    summary = final.get("outcome_summary", {})
    t2t_status = summary.get("t2t_status", "unavailable")
    t2t_text = {"achieved": "已达到", "not_achieved": "尚未达到", "unknown": "待评估", "unavailable": "暂无结果"}.get(t2t_status, "待评估")
    complete, total = summary.get("telomere_ends_complete"), summary.get("telomere_ends_total")
    telomere_value = f"{display(complete)} / {display(total)}" if complete is not None and total else "未测量"
    chromosome_count = summary.get("chromosome_count")
    starting_gaps, remaining_gaps = summary.get("starting_gap_count"), summary.get("remaining_gap_count")
    gap_change = summary.get("gap_count_change")
    if gap_change is None and starting_gaps is not None and remaining_gaps is not None:
        gap_change = remaining_gaps - starting_gaps
    gap_text = f"{gap_change:+,}" if isinstance(gap_change, int) and gap_change != 0 else display(gap_change)
    return (
        '<div class="summary-line">'
        f'<span><b>{esc(display(chromosome_count))}</b> 条序列</span>'
        f'<span>总长 <b>{esc(compact_number(summary.get("total_length_bp")))}</b></span>'
        f'<span>Gap 数净变化 <b>{esc(gap_text)}</b></span>'
        f'<span>剩余 <b>{esc(display(remaining_gaps))}</b> Gap <small class="muted">(≥100 N)</small></span>'
        f'<span>端粒 <b>{esc(telomere_value)}</b></span>'
        f'<span>T2T 结构条件（已输出序列） <b>{esc(t2t_text)}</b></span>'
        '</div>'
        '<p class="note" style="margin-top:0">Gap 数净变化 = Final Path − q0；减少不等于真实缺失序列闭合。</p>'
    )


def annotation_evidence_text(raw) -> str:
    try:
        entries = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return ""
    if not isinstance(entries, list):
        return ""
    return "; ".join(
        ": ".join(str(entry.get(k, "")) for k in ("source", "id", "note") if entry.get(k))
        for entry in entries if isinstance(entry, dict)
    )


def final_path_visual_html(final: dict) -> str:
    chromosomes = final.get("final_path", {}).get("chromosomes", [])
    if not chromosomes:
        return '<p class="warn">本次运行尚无可绘制的 Final Path。</p>'
    contributions = final.get("source_contribution_bp", {})
    total_contribution = sum(value for value in contributions.values() if isinstance(value, (int, float))) or 1
    ds_color_map = {dataset: index % 5 for index, dataset in enumerate(contributions)}

    annotations = final.get("annotations", {})
    telomere = annotations.get("telomere", {})
    centromere = annotations.get("centromere", {})
    rules_by_id = {row.get("rule_id"): row for row in telomere.get("rules", [])}
    terminal_by_chr = {}
    for row in telomere.get("terminal_rows", []):
        terminal_by_chr.setdefault(row.get("chr"), {})[row.get("terminal")] = row
    centromere_by_chr = {}
    for row in centromere.get("markers", []):
        centromere_by_chr.setdefault(row.get("chr"), []).append(row)
    complete_statuses = {"already_present", "recovered"}
    max_chr_len = max(
        (c.get("q4_length") or sum(max(0, s.get("length", 0)) for s in c.get("segments", [])) for c in chromosomes[:REPORT_PREVIEW_ROWS]),
        default=1,
    ) or 1

    has_patch = False
    has_gap = False
    tracks = []
    for chromosome in chromosomes[:REPORT_PREVIEW_ROWS]:
        segments = chromosome.get("segments", [])
        total = chromosome.get("q4_length") or sum(max(0, segment.get("length", 0)) for segment in segments) or 1
        rel_w = max(12.0, 100.0 * total / max_chr_len)
        pieces, segment_rows = [], []
        for segment in segments[:REPORT_PREVIEW_ROWS]:
            length = max(0, segment.get("length", 0) or 0)
            kind = segment.get("kind", "source")
            source = segment.get("source") or {}
            dataset, contig = source.get("dataset", ""), source.get("contig", "")
            orientation = source.get("orientation", segment.get("orientation", ""))
            title = f'{chromosome.get("chr")} · {label(kind)} · {dataset}:{contig} · {display(length)} bp · {orientation or "-"}'
            if kind == "gap":
                has_gap = True
                class_name = "gap"
            elif kind == "patch":
                has_patch = True
                class_name = "patch"
            else:
                class_name = f"source source-{ds_color_map.get(dataset, 0)}"
            pieces.append(f'<i class="path-segment {class_name}" style="flex-grow:{max(1, length)}" title="{esc(title)}"></i>')
            segment_rows.append({"kind": label(kind), "dataset": dataset, "contig": contig, "length_bp": length, "orientation": orientation, "source_range": f'{source.get("start", "-")}–{source.get("end", "-")}'})
        chromosome_name = chromosome.get("chr")
        if len(segments) > len(segment_rows):
            hidden_bp = max(0, total - sum(r["length_bp"] for r in segment_rows))
            pieces.append(f'<i style="flex-grow:{hidden_bp}" title="其余片段未展开"></i>')
        markers = []
        terminal_rows = terminal_by_chr.get(chromosome_name, {})
        if telomere.get("configured"):
            for terminal, side in (("5prime", "left"), ("3prime", "right")):
                row = terminal_rows.get(terminal, {})
                complete = row.get("final_status") in complete_statuses
                marker_title = f'{chromosome_name} {terminal} · {"端粒完整" if complete else "端粒缺失"}'
                evidence = "; ".join(annotation_evidence_text(rules_by_id.get(rid, {}).get("provenance")) for rid in row.get("matched_rule_ids", []))
                marker_title += f" · {evidence}" if evidence else ""
                markers.append(f'<span class="path-marker telomere {side} {"complete" if complete else "missing"}" title="{esc(marker_title)}"></span>')
        chromosome_centromeres = centromere_by_chr.get(chromosome_name, [])
        if centromere.get("configured"):
            for marker in chromosome_centromeres[:REPORT_PREVIEW_ROWS]:
                start = max(1, marker.get("q4_start", 1))
                end = min(total, marker.get("q4_end", total))
                left = 100 * (start - 1) / total
                width = max(.45, 100 * max(1, end - start + 1) / total)
                marker_title = f'{chromosome_name} 着丝粒候选 · {display(start)}–{display(end)} (1-based incl.)'
                markers.append(f'<span class="path-marker centromere" style="left:{left:.6f}%;width:{width:.6f}%" title="{esc(marker_title)}"></span>')
        details = "".join(
            f'<li><span class="segment-chip {"gap" if r["kind"] == label("gap") else ("patch" if r["kind"] == label("patch") else "source")}">{esc(r["kind"])}</span>'
            f'<strong>{esc(r["dataset"] or "连接")} {esc(r["contig"])}</strong><span>{esc(compact_number(r["length_bp"]))} · {esc(r["orientation"] or "-")} · {esc(r["source_range"])}</span></li>'
            for r in segment_rows
        )
        tracks.append(
            f'<details class="path-row"><summary><b>{esc(chromosome_name)}</b>'
            f'<div class="path-bar-wrap"><div class="path-bar" style="width:{rel_w:.2f}%">{"".join(pieces)}{"".join(markers)}</div></div>'
            f'<span class="path-length">{esc(compact_number(total))}</span></summary><ul class="segment-list">{details}</ul></details>'
        )

    src_legend = "".join(f'<span><i class="legend-dot source-{i % 5}"></i>{esc(ds)} ({esc(compact_number(v))})</span>' for i, (ds, v) in enumerate(contributions.items()))
    extra_legend = (
        ('<span><i class="legend-dot patch"></i>LGZ 补丁</span>' if has_patch else "")
        + ('<span><i class="legend-dot gap"></i>Gap</span>' if has_gap else "")
        + ('<span><i class="legend-symbol telomere"></i>端粒完整</span><span><i class="legend-symbol telomere-missing"></i>端粒缺失</span>' if telomere.get("configured") else "")
        + ('<span><i class="legend-symbol centromere"></i>着丝粒候选</span>' if centromere.get("configured") and centromere_by_chr else "")
    )
    multi_bar = ""
    if len(contributions) > 1:
        c_parts = [f'<i class="source-{i % 5}" style="width:{100 * v / total_contribution:.4f}%" title="{esc(ds)}: {esc(display(v))} bp"></i>' for i, (ds, v) in enumerate(contributions.items())]
        multi_bar = f'<div class="source-bar" style="margin-bottom:8px">{"".join(c_parts)}</div>'
    fallback_src = '<span><i class="legend-dot source"></i>主路径来源</span>'
    return (
        multi_bar
        + f'<div class="legend path-legend">{src_legend or fallback_src}{extra_legend}</div>'
        + f'<div class="path-map" id="grt-final-path">{"".join(tracks)}</div>'
        + '<p class="note">点击染色体展开分段来源与坐标（q/source 区间 1-based inclusive，PAF 区间 0-based half-open）。</p>'
    )


CSS = """
:root{
  color-scheme:light;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  --font-mono:ui-monospace,"SFMono-Regular","Cascadia Code",Consolas,monospace;
  --card-radius:6px;--control-radius:4px;
  --surface-app:#f7f8fa;--surface-panel:#ffffff;--surface-subtle:#f9fafb;--surface-muted:#f1f3f5;--surface-hover:#eef1f4;
  --border-subtle:#e5e7eb;--border-default:#d1d5db;--border-strong:#9ca3af;
  --ink:#111827;--text-secondary:#374151;--muted:#6b7280;
  --accent:#1e4e79;--action-primary-bg:#1d3557;--focus-ring:#2563eb;
  --tone-ok-ink:#1b5e3c;--tone-ok-bg:#f0f8f4;--tone-ok-line:#a7d7be;
  --tone-warn-ink:#854d0e;--tone-warn-bg:#fdf9ed;--tone-warn-line:#e2c275;
  --tone-err-ink:#991b1b;--tone-err-bg:#fdf2f2;--tone-err-line:#e5a4a4;
  --tone-info-ink:#1e4273;--tone-info-bg:#f2f6fb;--tone-info-line:#b6cce6;
  --source:#335c81;--patch:#c97a2b;--gap:#b91c1c;--telomere:#2b7a57;--centromere:#6d4c9c;
}
html[data-theme="dark"]{
  color-scheme:dark;
  --surface-app:#0f1419;--surface-panel:#151c24;--surface-subtle:#1b242e;--surface-muted:#222d3a;--surface-hover:#273444;
  --border-subtle:#263240;--border-default:#344354;--border-strong:#5b6e82;
  --ink:#edf2f7;--text-secondary:#c4d0dc;--muted:#8a99aa;
  --accent:#8cb4e6;--action-primary-bg:#7da4d4;--focus-ring:#93c5fd;
  --tone-ok-ink:#8dd3ad;--tone-ok-bg:#152920;--tone-ok-line:#2f684c;
  --tone-warn-ink:#e8c97a;--tone-warn-bg:#2a2315;--tone-warn-line:#80642b;
  --tone-err-ink:#f2a2a2;--tone-err-bg:#2f191d;--tone-err-line:#843e46;
  --tone-info-ink:#9ec0e6;--tone-info-bg:#172638;--tone-info-line:#375a82;
  --source:#5585b5;--patch:#dfa048;--gap:#dc5964;--telomere:#43b37d;--centromere:#9e82cc;
}
@media (prefers-color-scheme:dark){
  html:not([data-theme="light"]){
    color-scheme:dark;
    --surface-app:#0f1419;--surface-panel:#151c24;--surface-subtle:#1b242e;--surface-muted:#222d3a;--surface-hover:#273444;
    --border-subtle:#263240;--border-default:#344354;--border-strong:#5b6e82;
    --ink:#edf2f7;--text-secondary:#c4d0dc;--muted:#8a99aa;
    --accent:#8cb4e6;--action-primary-bg:#7da4d4;--focus-ring:#93c5fd;
    --tone-ok-ink:#8dd3ad;--tone-ok-bg:#152920;--tone-ok-line:#2f684c;
    --tone-warn-ink:#e8c97a;--tone-warn-bg:#2a2315;--tone-warn-line:#80642b;
    --tone-err-ink:#f2a2a2;--tone-err-bg:#2f191d;--tone-err-line:#843e46;
    --tone-info-ink:#9ec0e6;--tone-info-bg:#172638;--tone-info-line:#375a82;
    --source:#5585b5;--patch:#dfa048;--gap:#dc5964;--telomere:#43b37d;--centromere:#9e82cc;
  }
}
html[data-lang="zh"] .t-en{display:none!important}
html[data-lang="en"] .t-zh{display:none!important}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);background:var(--surface-app);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:3px}
code,pre{font-family:var(--font-mono)}
code{font-size:.86em;background:var(--surface-muted);padding:.1em .34em;border-radius:3px;overflow-wrap:anywhere}
header{background:var(--surface-panel);border-bottom:1px solid var(--border-subtle)}
.header-inner{max-width:1280px;margin:0 auto;padding:16px 24px 14px}
.header-title-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
header p{color:var(--muted);margin:4px 0 0;font-size:12.5px}
.wb-controls{display:inline-flex;align-items:center;gap:5px}
.ctrl-btn{padding:3px 9px;border-radius:var(--control-radius);border:1px solid var(--border-subtle);background:transparent;color:var(--muted);font:500 12px/1.3 inherit;cursor:pointer}
.ctrl-btn:hover{background:var(--surface-subtle);border-color:var(--border-default);color:var(--ink)}
.ctrl-btn.is-active{background:var(--surface-muted);border-color:var(--border-default);color:var(--ink);font-weight:600}
h1{font-size:19.5px;line-height:1.3;margin:0;font-weight:600;letter-spacing:-.015em}
h2{font-size:15px;line-height:1.35;margin:0 0 12px;font-weight:600;padding-bottom:7px;border-bottom:1px solid var(--border-subtle)}
h3{font-size:13.5px;line-height:1.4;margin:14px 0 7px;font-weight:600;color:var(--text-secondary)}
.wb-shell{max-width:1280px;margin:0 auto;padding:20px 24px 36px;display:grid;grid-template-columns:168px minmax(0,1fr);gap:28px;align-items:start}
.wb-sidebar{position:sticky;top:18px}
.wb-toc{list-style:none;margin:0;padding:0;border-left:1px solid var(--border-subtle);display:flex;flex-direction:column;gap:2px}
.wb-toc a{display:block;padding:5px 12px;margin-left:-1px;border-left:2px solid transparent;color:var(--muted);font-size:13px;font-weight:500}
.wb-toc a:hover{color:var(--ink);text-decoration:none}
.wb-toc a.is-current{color:var(--action-primary-bg);border-left-color:var(--action-primary-bg);font-weight:600}
main{min-width:0}
section,.stage{background:var(--surface-panel);border:1px solid var(--border-subtle);border-radius:var(--card-radius);margin-bottom:16px;padding:18px 22px;min-width:0;scroll-margin-top:18px}
button{font:inherit;cursor:pointer;background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--control-radius);padding:4px 11px;color:var(--ink);font-size:13px}
button:hover{background:var(--surface-subtle);border-color:var(--border-strong)}button:disabled{opacity:.45;cursor:default}
.badge{display:inline-flex;align-items:center;background:var(--surface-muted);color:var(--text-secondary);border:1px solid var(--border-default);border-radius:3px;padding:1px 8px;font-size:11.5px;font-weight:500;white-space:nowrap}
.success,.prepared{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border-color:var(--tone-ok-line)}
.failed{color:var(--tone-err-ink);background:var(--tone-err-bg);border-color:var(--tone-err-line)}
.interrupted{color:var(--tone-warn-ink);background:var(--tone-warn-bg);border-color:var(--tone-warn-line)}
.running,.preparing{color:var(--tone-info-ink);background:var(--tone-info-bg);border-color:var(--tone-info-line)}
.summary-line{display:flex;flex-wrap:wrap;gap:6px 18px;align-items:baseline;font-size:13.5px;color:var(--text-secondary);margin-bottom:8px}
.summary-line b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:8px 0}.facts div{border-left:2px solid var(--border-subtle);padding-left:9px}.facts dt{color:var(--muted);font-size:11.5px}.facts dd{margin:2px 0;overflow-wrap:anywhere;font-weight:600;font-size:13px;font-variant-numeric:tabular-nums}
.note,.muted{color:var(--muted);font-size:12.5px}.note{margin:6px 0}
.warn{border-left:2px solid var(--tone-warn-line);padding:8px 11px;background:var(--tone-warn-bg);color:var(--ink);border-radius:0 var(--control-radius) var(--control-radius) 0;margin:8px 0;font-size:13px}
.warn.is-error{border-left-color:var(--tone-err-line);background:var(--tone-err-bg)}
details>summary{cursor:pointer;font-weight:500;font-size:13px;color:var(--text-secondary);overflow-wrap:anywhere}details>summary:hover{color:var(--ink)}details{margin-top:8px}
details.block{border-top:1px solid var(--border-subtle);padding-top:8px}details.block>summary{display:flex;align-items:center;gap:6px;flex-wrap:wrap;list-style:none}details.block>summary::-webkit-details-marker{display:none}details.block>summary::before{content:"▸";color:var(--muted);font-size:11px;display:inline-block;width:10px}details.block[open]>summary::before{content:"▾"}.stage>summary{font-size:14px;font-weight:600}.stage-body{padding-top:8px}
.scroll{overflow:auto;-webkit-overflow-scrolling:touch;max-height:480px;margin:6px 0}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{border-bottom:1px solid var(--border-subtle);padding:7px 9px;text-align:left;vertical-align:top}
th{border-top:1px solid var(--border-default);border-bottom:1px solid var(--border-default);background:transparent;color:var(--muted);white-space:nowrap;font-weight:600;font-size:11.5px}
tbody tr:last-child td{border-bottom:1px solid var(--border-default)}tbody tr:hover{background:var(--surface-subtle)}
td{max-width:440px;min-width:84px;overflow-wrap:anywhere}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11.5px;background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--control-radius);padding:9px 11px;max-height:380px;overflow:auto;color:var(--ink)}
.toolbar{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin:8px 0}.toolbar input{flex:1;min-width:150px;padding:4px 8px;border:1px solid var(--border-default);border-radius:var(--control-radius);background:var(--surface-panel);color:var(--ink);font:inherit;font-size:12.5px}
.timeline{list-style:none;padding:0;margin:4px 0}.timeline li{display:flex;gap:10px;align-items:center;padding:5px 0;border-bottom:1px solid var(--border-subtle);flex-wrap:wrap;font-size:13px}.timeline a{flex:1;min-width:200px}
.metric{font-variant-numeric:tabular-nums}
.chart-box{padding:8px 0;margin:4px 0;overflow-x:auto}.chart-box svg{display:block;max-width:100%;height:auto}
.pipeline-map{display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:6px 0}
.pipeline-node{display:inline-flex;flex-direction:column;padding:5px 10px;border:1px solid var(--border-subtle);border-radius:var(--control-radius);background:var(--surface-subtle);color:var(--ink);text-decoration:none}
.pipeline-node:hover{border-color:var(--border-default);background:var(--surface-hover);text-decoration:none}
.pipeline-node strong{font-size:12.5px;font-weight:600}.pipeline-node small{color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.pipeline-arrow,.io-arrow{color:var(--border-strong);font-size:13px}
.io-flow{display:grid;grid-template-columns:minmax(0,1fr) 20px minmax(0,1.1fr) 20px minmax(0,1fr);align-items:stretch;gap:6px;margin:8px 0}
.io-card{border:1px solid var(--border-subtle);border-radius:var(--control-radius);padding:8px 10px;display:flex;flex-direction:column;gap:2px;background:var(--surface-subtle);font-size:12.5px}
.io-card small{font:600 10px/1.2 var(--font-mono);color:var(--muted)}
.grt-flow{margin:6px 0 2px;font-size:12.5px}
.source-bar{display:flex;height:12px;overflow:hidden;border-radius:3px;background:var(--surface-muted)}.source-bar i{display:block;min-width:2px}
.source-0{background:#335c81}.source-1{background:#2a7b76}.source-2{background:#5e548e}.source-3{background:#b07d3b}.source-4{background:#9e4765}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin:6px 0;color:var(--muted);font-size:12px}
.legend-dot,.legend-symbol{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.legend-dot.source{background:var(--source)}.legend-dot.patch{background:var(--patch)}.legend-dot.gap{background:repeating-linear-gradient(45deg,var(--gap),var(--gap) 3px,#fff 3px,#fff 5px);border:1px solid var(--gap);box-sizing:border-box}
.legend-symbol.telomere{background:var(--telomere);border-radius:50%}.legend-symbol.telomere-missing{border:1.5px solid var(--gap);border-radius:50%;background:var(--surface-panel)}.legend-symbol.centromere{background:var(--centromere);transform:rotate(45deg);border-radius:1px}
.path-map{border-top:1px solid var(--border-default);border-bottom:1px solid var(--border-default)}
.path-row{margin:0;border-bottom:1px solid var(--border-subtle)}.path-row:last-child{border:0}
.path-row>summary{display:grid;grid-template-columns:96px minmax(180px,1fr) 80px;gap:10px;align-items:center;padding:7px 4px;list-style:none}
.path-row>summary::-webkit-details-marker{display:none}.path-row>summary:hover{background:var(--surface-subtle)}
.path-bar-wrap{min-width:0}
.path-bar{position:relative;display:flex;align-items:stretch;height:18px;border-radius:3px;overflow:hidden;background:var(--surface-muted)}
.path-segment{display:block;min-width:2px;border-right:1px solid rgba(255,255,255,.45);font-style:normal}
.path-segment.source{background:var(--source)}.path-segment.source.source-0{background:#335c81}.path-segment.source.source-1{background:#2a7b76}.path-segment.source.source-2{background:#5e548e}.path-segment.source.source-3{background:#b07d3b}.path-segment.source.source-4{background:#9e4765}
.path-segment.patch{background:var(--patch);min-width:4px}.path-segment.gap{background:repeating-linear-gradient(45deg,var(--gap),var(--gap) 3px,#fff 3px,#fff 5px);min-width:5px}
.path-marker{position:absolute;z-index:2}.path-marker.telomere{top:2px;width:7px;height:14px;background:var(--telomere);border:1.5px solid var(--surface-panel);border-radius:5px}
.path-marker.telomere.left{left:2px}.path-marker.telomere.right{right:2px}.path-marker.telomere.missing{background:var(--surface-panel);border-color:var(--gap)}
.path-marker.centromere{top:2px;height:14px;min-width:6px;background:var(--centromere);border:1.5px solid var(--surface-panel);border-radius:2px}
.path-length{text-align:right;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.segment-list{list-style:none;margin:0;padding:6px 10px 10px 106px;background:var(--surface-subtle)}
.segment-list li{display:grid;grid-template-columns:92px minmax(120px,1fr) minmax(140px,1fr);gap:8px;padding:4px 0;border-bottom:1px solid var(--border-subtle);font-size:12px}
.segment-chip{display:inline-block;border-radius:3px;padding:1px 6px;width:max-content;color:#fff;font-size:11px}.segment-chip.source{background:var(--source)}.segment-chip.patch{background:var(--patch)}.segment-chip.gap{background:var(--gap)}
.technical-section{padding:0}.section-disclosure{margin:0}.section-disclosure>summary{padding:13px 20px;font-size:14px;font-weight:600;color:var(--ink);list-style-position:inside}.section-disclosure[open]{padding:0 20px 16px}.section-disclosure[open]>summary{margin:0 -20px 12px;border-bottom:1px solid var(--border-subtle)}
@media(max-width:1024px){
  .wb-shell{grid-template-columns:1fr;padding:14px;gap:12px}
  .wb-sidebar{position:static}
  .wb-toc{flex-direction:row;overflow-x:auto;border-left:0;border-bottom:1px solid var(--border-subtle);gap:4px}
  .wb-toc a{white-space:nowrap;margin-left:0;border-left:0;border-bottom:2px solid transparent;padding:6px 10px}
  .wb-toc a.is-current{border-bottom-color:var(--action-primary-bg)}
}
@media(max-width:760px){.header-inner{padding:12px 14px}section,.stage{padding:14px}.io-flow{grid-template-columns:1fr}.io-arrow{transform:rotate(90deg);text-align:center}.path-row>summary{grid-template-columns:72px minmax(120px,1fr) 64px}.segment-list{padding-left:10px}.segment-list li{grid-template-columns:80px 1fr}}
@media print{body{background:#fff;color:#000}.wb-sidebar,.wb-controls,button,.toolbar{display:none!important}.wb-shell{display:block;padding:0;max-width:none}section,.stage{break-inside:avoid;border-radius:0}.scroll{max-height:none}}
"""

JS = r"""
const rootEl=document.documentElement;
const store=(k,v)=>{try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v);}catch(_){return null;}};
const setLang=(lang)=>{lang=(lang==='en')?'en':'zh';rootEl.dataset.lang=lang;rootEl.lang=(lang==='en')?'en':'zh-CN';document.querySelectorAll('[data-lang-btn]').forEach(b=>b.classList.toggle('is-active',b.dataset.langBtn===lang));store('cgat_report_lang',lang);};
const setTheme=(t)=>{if(t==='dark'||t==='light'){rootEl.dataset.theme=t;store('cgat_report_theme',t);}};
const sL=store('cgat_report_lang');if(sL==='zh'||sL==='en')setLang(sL);
const sT=store('cgat_report_theme');if(sT==='dark'||sT==='light')setTheme(sT);
document.addEventListener('click',(ev)=>{
  const lb=ev.target.closest('[data-lang-btn]');if(lb){setLang(lb.dataset.langBtn);return;}
  const tb=ev.target.closest('[data-theme-toggle]');if(tb){const dk=rootEl.dataset.theme==='dark'||(!rootEl.dataset.theme&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);setTheme(dk?'light':'dark');return;}
});
if('IntersectionObserver' in window){
  const tocLinks=[...document.querySelectorAll('.wb-toc a[href^="#"]')];
  const map=new Map();tocLinks.forEach(a=>{const el=document.getElementById(a.getAttribute('href').slice(1));if(el)map.set(el,a);});
  if(map.size){const io=new IntersectionObserver((entries)=>{for(const e of entries){if(e.isIntersecting){tocLinks.forEach(a=>a.classList.remove('is-current'));const a=map.get(e.target);if(a)a.classList.add('is-current');}}},{rootMargin:'-12% 0px -70% 0px',threshold:0});map.forEach((_,el)=>io.observe(el));}
}
const data=JSON.parse(document.getElementById('report-data').textContent);
const labels=data.labels, enums=new Set(['status','action','reason','outcome','role','process_status','process_reason','final_status','final_reason','reads_qc','self_alignment','kind','qc']), fmt=(v,key)=>v===null||v===undefined||v===''?'未记录':typeof v==='object'?JSON.stringify(v,null,2):(enums.has(key)?labels[String(v)]||String(v):String(v));
const save=(value,name)=>{const a=document.createElement('a');const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
const dlBtn=document.getElementById('download');if(dlBtn)dlBtn.onclick=()=>save({...data.payload,tables:data.tables},'server-report.json');
for(const box of document.querySelectorAll('[data-table]')){
 let ready=false;
 box.addEventListener('toggle',()=>{if(!box.open||ready)return;ready=true;
 const rows=data.tables[Number(box.dataset.table)], cols=[...new Set(rows.flatMap(r=>Object.keys(r)))];
 const toolbar=document.createElement('div');toolbar.className='toolbar';
 const search=document.createElement('input');search.type='search';search.placeholder='搜索已嵌入记录';search.setAttribute('aria-label',box.querySelector('summary').textContent+' 搜索');
 const prev=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span'),download=document.createElement('button');prev.textContent='上一页';next.textContent='下一页';download.textContent='下载表格展示数据 JSON';toolbar.append(search,prev,count,next,download);box.append(toolbar);
 const scroll=document.createElement('div');scroll.className='scroll';const table=document.createElement('table');const head=document.createElement('thead'),tr=document.createElement('tr');for(const key of cols){const th=document.createElement('th');th.textContent=labels[key]||key;tr.append(th)}head.append(tr);const body=document.createElement('tbody');table.append(head,body);scroll.append(table);box.append(scroll);
 let page=0,filtered=rows;const size=50;
 const draw=()=>{body.replaceChildren();for(const row of filtered.slice(page*size,(page+1)*size)){const tr=document.createElement('tr');for(const key of cols){const td=document.createElement('td'),value=row[key];if(value&&typeof value==='object'){const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent='查看详情';p.textContent=fmt(value,key);d.append(s,p);td.append(d)}else{td.textContent=fmt(value,key)}tr.append(td)}body.append(tr)}count.textContent=`${filtered.length? page*size+1:0}–${Math.min((page+1)*size,filtered.length)} / ${filtered.length}`;prev.disabled=page===0;next.disabled=(page+1)*size>=filtered.length};
 search.oninput=()=>{const q=search.value.toLocaleLowerCase();filtered=rows.filter(row=>Object.entries(row).some(([k,v])=>fmt(v,k).toLocaleLowerCase().includes(q)||String(v).toLocaleLowerCase().includes(q)));page=0;draw()};prev.onclick=()=>{page--;draw()};next.onclick=()=>{page++;draw()};download.onclick=()=>save(rows,'report-table.json');draw();
 });
}
"""


def bounded_id_projection(value):
    """View-only projection; never mutate report-local audit data."""
    if isinstance(value, dict):
        return {
            k: (
                {"count": len(v), "preview": v[:10]}
                if k in {"evidence_ids", "usage_ids", "final_path_segment_ids"} and isinstance(v, list) and len(v) > 10
                else bounded_id_projection(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [bounded_id_projection(v) for v in value]
    return value


def render(root: Path) -> Path:
    root = root.resolve()
    manifest = load(root, "manifest.json")
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("unsupported server report schema")
    input_record = load(root, "inputs.json")
    if input_record.get("run_id") != manifest["run_id"] or input_record.get("schema_version") != SCHEMA:
        raise ValueError("mixed invocation or schema in report input record")
    records = [project_report_record(load(root, relative)) for relative in manifest["steps"]]
    grt = [project_report_record(load(root, p.relative_to(root).as_posix())) for p in sorted((root / "steps").glob("grt-*.json"))]
    stage_order = ["step1", "step2", "step3"]
    grt.sort(key=lambda row: stage_order.index(row["stage_id"]) if row["stage_id"] in stage_order else len(stage_order))
    for record in [*records, *grt]:
        if record.get("run_id") != manifest["run_id"] or record.get("schema_version") != SCHEMA:
            raise ValueError("mixed invocation or schema in report stage records")
    final = load(root, "final_summary.json", optional=True)
    if final and (final.get("run_id") != manifest["run_id"] or final.get("schema_version") != SCHEMA):
        raise ValueError("mixed invocation or schema in final report summary")
    final = bounded_id_projection(final)
    records = bounded_id_projection(records)
    grt = bounded_id_projection(grt)
    paths = {r.get("original_path") for r in input_record.get("sources", []) if r.get("option") in ("--hifi", "--ont", "--reads")}
    reading = False
    for arg in input_record.get("argv", []):
        if arg.startswith("-"):
            reading = arg in ("--hifi", "--ont", "--reads")
        elif reading:
            paths.add(arg)
    private = sorted((p for p in paths if p and p != "[private reads]"), key=len, reverse=True)

    def redact(v):
        if isinstance(v, str):
            for p in private:
                v = v.replace(p, "[private reads]")
        elif isinstance(v, list):
            return [redact(i) for i in v]
        elif isinstance(v, dict):
            return {redact(k): redact(i) for k, i in v.items()}
        return v

    if private:
        input_record, manifest, records, grt, final = redact([input_record, manifest, records, grt, final])

    tables, table_sources, table_ids = [], [], {}

    def data_table(name, rows, available=True, metadata=None):
        if not available:
            return f'<p class="note">{esc(label(name))}：未记录</p>'
        count = (metadata or {}).get("row_count", len(rows))
        if id(rows) not in table_ids:
            table_ids[id(rows)] = len(tables)
            tables.append(export_payload(rows[:REPORT_PREVIEW_ROWS]))
            table_sources.append(rows)
        index = table_ids[id(rows)]
        preview = len(tables[index])
        detail = ""
        if count > preview:
            source = (metadata or {}).get("source")
            origin = f"；来源：{esc(source)}" if source else ""
            detail = f'<p class="note">仅预览前 {preview:,} / 共 {count:,} 条{origin}，完整审计文件保留在服务器工作目录。</p>'
        return f'<details class="block" data-table="{index}"><summary>{esc(label(name))}<span class="badge">{count:,}</span></summary>{detail}</details>'

    def export_payload(value, path=()):
        if isinstance(value, list):
            if path and path[0] in {"steps", "grt_steps", "final_summary"} and id(value) in table_ids:
                return {"table_index": table_ids[id(value)]}
            return [export_payload(item, (*path, str(index))) for index, item in enumerate(value[:REPORT_PREVIEW_ROWS])]
        if isinstance(value, dict):
            return {key: export_payload(item, (*path, key)) for key, item in value.items()}
        return value

    def stats_table(name, versions):
        rows = [
            {"sequence": version, **{key: value.get(key) for key in ("sequence_count", "length_bp", "n_bp", "gap_count", "gap_bp", "n50_bp")}}
            for version, value in versions.items() if value
        ]
        if not rows:
            return '<p class="note">序列统计尚不可用。</p>'
        columns = list(rows[0])
        return (
            f'<h3>{esc(name)}</h3><div class="scroll"><table><thead><tr>'
            + "".join(f"<th>{esc(label(key))}</th>" for key in columns)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f'<td class="metric">{esc(display(row[key]))}</td>' for key in columns) + "</tr>" for row in rows)
            + "</tbody></table></div>"
        )

    def q0_summary_html(value):
        if not value:
            return '<p class="note">本次运行尚无成功发布的 q0 构建摘要。</p>'
        summary = dict(value["summary"])
        summary["qc"] = label(summary.get("qc"))
        core_keys = ("selected_chromosomes", "not_constructed_chromosomes", "selected_datasets", "selected_source_bp", "input_gap_joins", "unknown_joins", "sequence_overlap_joins")
        core = {k: summary[k] for k in core_keys if k in summary}
        extra = {k: v for k, v in summary.items() if k not in core}
        detail_inner = (key_values(extra) if extra else "") + notes(value.get("notes", [])) + key_values({"搜索限制": value.get("policy", {})})
        for name, tbl in value.get("tables", {}).items():
            detail_inner += data_table(name, tbl.get("rows", []), tbl.get("available", False), tbl)
        detail_inner += notes([f"来源：{value.get('source')} · SHA-256 {value.get('source_sha256')}"])
        return (
            f'<details class="block"><summary>多组装候选 → q0（{display(core.get("selected_chromosomes"))} chr · {compact_number(core.get("selected_source_bp"))} · {len(value.get("tables", {}))} 张明细表）</summary>'
            + key_values(core) + detail_inner + '</details>'
        )

    def stage_html(record, element_id):
        facts, runtime, state = record.get("facts", {}), record.get("runtime", {}), record.get("status", "pending")
        body = (
            f'<details class="stage" id="{element_id}"><summary>{esc(record["title"])} '
            f'<span class="badge {esc(state)}">{esc(label(state))}</span>'
            + (f' <span class="muted" style="font-weight:400;margin-left:6px">{esc(fmt_duration(runtime.get("elapsed_seconds")))}</span>' if runtime.get("elapsed_seconds") is not None else "")
            + '</summary><div class="stage-body">'
            + stage_io_html(record)
            + key_values({"执行方式": exec_label(record), "耗时 / s": runtime.get("elapsed_seconds"), "退出码": runtime.get("exit_code")})
            + key_values(facts.get("summary", {})) + notes(facts.get("notes", []))
        )
        if facts.get("sequence_versions"):
            body += stats_table("阶段前后对比", facts["sequence_versions"])
        for name, value in facts.get("tables", {}).items():
            body += data_table(name, value["rows"], value["available"], value)
        result = facts.get("result", {})
        for name in ("events", "strategies", "classification_rows", "terminal_rows"):
            if name in result:
                body += data_table("处理事件" if name == "events" else name, result[name], metadata={"row_count": result.get("report_array_counts", {}).get(name, len(result[name]))})
        if facts.get("outputs"):
            body += data_table("输出文件与校验值", facts["outputs"])
        if record.get("output_tail"):
            body += '<details class="block"><summary>日志尾部（最多 80 行）</summary><pre>' + esc("\n".join(record["output_tail"])) + "</pre></details>"
        body += (
            '<details class="block"><summary>命令与溯源</summary><pre>'
            + esc(json.dumps(export_payload({
                "command": record.get("command_text", record.get("command")),
                "parameters": facts.get("parameters"),
                "tool_version": facts.get("tool_version"),
                "identity": {k: v for k, v in result.items() if k not in {"events", "q_rows", "usage_rows", "evidence_rows", "attempts", "classification_rows", "terminal_rows", "strategies"}},
            }), ensure_ascii=False, indent=2))
            + "</pre></details></div></details>"
        )
        return body

    state = manifest["status"]
    completed_stages = sum(r.get("status") == "success" for r in records)
    cached_stages = sum(r.get("execution") == "cache_reused" for r in records)
    manifest_reasons = [manifest[k].strip() for k in ("reason", "status_reason", "message") if isinstance(manifest.get(k), str) and manifest[k].strip()]
    manifest_errors = [str(item) for item in manifest.get("errors", []) if item]
    non_ok_stages = [f'{r.get("title", r.get("stage_id", ""))} ({label(r.get("status"))})' for r in records if r.get("status") in {"failed", "interrupted"}]

    input_facts = input_record.get("facts", {})
    q0_construction = final.get("q0_construction") or next(
        (r.get("facts", {}).get("q0_construction") for r in records if r.get("stage_id") in PREPARE_IDS and r.get("status") == "success"),
        None,
    )
    modern_q0 = bool(q0_construction) or input_facts.get("q0_mode") == "evidence_guided_multi_source" or final.get("q0_mode") == "evidence_guided_multi_source"
    reason_parts = list(dict.fromkeys([*manifest_reasons, *manifest_errors]))
    topline_reason_html = ""
    if reason_parts:
        topline_reason_html = f'<div class="warn{" is-error" if state == "failed" else ""}">' + "；".join(esc(i) for i in reason_parts) + "</div>"
    elif state != "success":
        hint = f"（{'、'.join(non_ok_stages)}）" if non_ok_stages else ""
        topline_reason_html = f'<p class="warn">本次运行未完成{esc(hint)}，未测量指标不计入结果。</p>'

    header_html = (
        '<header><div class="header-inner">'
        '<div class="header-title-row"><div>'
        f'<h1>{esc(manifest["workspace_name"])} · {bi("LGZ 基线（非精修结果）", "LGZ Baseline (Non-Refined)")}</h1>'
        f'<p>Run <code>{esc(manifest["run_id"])}</code> · {completed_stages}/{len(records)} 阶段 · 缓存 {cached_stages}'
        + (f' · {esc(manifest.get("ended_at"))}' if manifest.get("ended_at") else "") + '</p></div>'
        '<div class="wb-controls">'
        '<button type="button" class="ctrl-btn is-active" data-lang-btn="zh">中文</button>'
        '<button type="button" class="ctrl-btn" data-lang-btn="en">EN</button>'
        '<button type="button" class="ctrl-btn" data-theme-toggle="1">' + bi("深/浅", "Theme") + '</button>'
        '</div></div></div></header>'
    )
    sidebar_html = (
        '<aside class="wb-sidebar" aria-label="LGZ sections"><ol class="wb-toc">'
        '<li><a href="#summary" class="is-current">' + bi("基线摘要", "Summary") + '</a></li>'
        '<li><a href="#results">' + bi("染色体与演化", "Chromosomes") + '</a></li>'
        '<li><a href="#workflow">' + bi("运行耗时", "Timing") + '</a></li>'
        '<li><a href="#inputs">' + bi("输入与参数", "Inputs") + '</a></li>'
        '<li><a href="#process">' + bi("逐步明细", "Step I/O") + '</a></li>'
        '<li><a href="#delivery">' + bi("数据导出", "Export") + '</a></li>'
        '</ol></aside>'
    )

    body = header_html + '<div class="wb-shell">' + sidebar_html + "<main>"
    body += (
        '<section id="summary">'
        + topline_reason_html
        + outcome_summary_html(final)
    )
    if q0_construction and q0_construction.get("summary", {}).get("not_constructed_chromosomes", 0):
        count = q0_construction["summary"]["not_constructed_chromosomes"]
        body += f'<p class="warn">q0 中有 {esc(display(count))} 个参考 chr 未构建；以下结构条件仅针对已输出序列。<a href="#q0-construction">查看构建范围</a></p>'
    body += '<details class="block"><summary>过程阶段索引</summary>' + pipeline_map_html(records, input_facts, final) + '</details></section>'

    body += '<section id="results"><h2>' + bi("染色体组成与版本演化", "Chromosomes & Evolution") + "</h2>"
    body += final_path_visual_html(final) if final.get("available") else '<p class="warn">尚无经过确认的 Final Path。</p>'
    body += '<h3>' + bi("q0 → Final Path 演化", "q0 → Final Path Evolution") + "</h3>" + lgz_flow_html(grt, final)
    if modern_q0:
        body += '<div id="q0-construction">' + q0_summary_html(q0_construction) + "</div>"
    versions, stats_inner = {}, ""
    if modern_q0:
        candidates = {f"输入 {row['name']}": row.get("stats") for row in input_facts.get("datasets", []) if row["role"] != "reference"}
        stats_inner += stats_table("各组装输入（可重叠，不作求和基线）", candidates)
    else:
        primary = next((d for d in input_facts.get("datasets", []) if d["role"] == "primary"), {})
        versions["原始主组装"] = primary.get("stats")
    for record in records:
        if record["stage_id"] in PREPARE_IDS:
            versions.update(record.get("facts", {}).get("sequence_versions", {}))
    versions.update(final.get("sequence_versions", {}))
    stats_inner += stats_table("版本统计对照", versions) + notes(final.get("notes", []))
    body += '<details class="block"><summary>版本精确统计表</summary>' + stats_inner + "</details>"
    remaining = [e for e in final.get("events", []) if e.get("status") in {"unresolved", "rejected"}]
    body += (
        '<details class="block"><summary>事件对账与最终路径审计明细</summary>'
        + data_table("event_reconciliation", final.get("event_reconciliation", []))
        + '<p class="note">历史未接受事件非最终剩余缺口；最终剩余 gap 以 Final Path 统计为准。</p>'
        + data_table("历史未接受事件与原因", remaining)
        + data_table("最终染色体路径", final.get("final_path", {}).get("chromosomes", []))
        + data_table("各染色体最终统计", (final.get("sequence_versions", {}).get(final.get("final_q_version", "q4")) or {}).get("sequences", []))
        + "</details></section>"
    )

    body += (
        '<section id="workflow"><h2>' + bi("运行耗时热点", "Runtime Hotspots") + "</h2>"
        '<div id="overview">' + timing_waterfall_html(records)
        + f'<details class="block"><summary>完整执行清单（{len(records)} 阶段）</summary><ol class="timeline">'
    )
    for index, record in enumerate(records):
        el_txt = fmt_duration((record.get("runtime") or {}).get("elapsed_seconds"))
        body += f'<li><span class="badge {esc(record["status"])}">{esc(label(record["status"]))}</span><a href="#stage-{index}">{esc(record["title"])}</a><span class="muted">{esc(exec_label(record))}</span><span class="muted metric">{esc(el_txt)}</span></li>'
    body += "</ol></details></div></section>"

    body += (
        '<section id="inputs" class="technical-section"><details class="section-disclosure"><summary>'
        + bi("原始输入与准备参数", "Inputs & Preparation Options") + "</summary>"
        + notes(input_record.get("notes", []))
        + data_table("原始文件来源", input_record.get("sources", []))
        + stats_table("输入序列统计", {f'{d["name"]} · {label(d["role"])}': d.get("stats") for d in input_facts.get("datasets", [])})
        + data_table("实际准备参数", [{"参数": k, "值": v} for k, v in input_facts.get("parameters", {}).items()])
        + '<details class="block"><summary>准备命令参数</summary><pre>' + esc(json.dumps(input_record.get("argv"), ensure_ascii=False, indent=2)) + "</pre></details></details></section>"
    )

    body += (
        '<section id="process" class="technical-section"><details class="section-disclosure"><summary>'
        + bi(f"逐步处理明细（{len(records)} 单元）", f"Step-by-Step Details ({len(records)} units)") + "</summary>"
    )
    for index, record in enumerate(records):
        body += stage_html(record, f"stage-{index}")
        for sub in grt:
            if sub.get("parent_unit") == record["stage_id"]:
                body += stage_html(sub, "grt-" + sub["stage_id"])
    body += "</details></section>"

    outputs = [output for record in records if record["stage_id"].startswith("package_") for output in record.get("facts", {}).get("outputs", [])]
    body += '<section id="delivery">'
    if outputs:
        body += '<h2>' + bi("交付包载荷与数据导出", "Delivery Payload & Data Export") + '</h2>' + data_table("交付包 App 数据载荷", outputs) + '<p class="note">载荷校验值覆盖嵌入报告前的数据（最终 ZIP SHA-256 见 run_all.log）。</p>'
    body += '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap"><span class="muted">全量审计明细保留在服务器工作目录。</span><button id="download" type="button">下载报告展示数据 JSON</button></div></section></main></div>'

    payload = export_payload({
        "report_data_kind": "summary_with_table_previews_v1", "preview_row_limit": REPORT_PREVIEW_ROWS,
        "manifest": manifest, "inputs": input_record, "steps": records, "grt_steps": grt, "final_summary": final,
    })
    embedded = (
        json.dumps({"labels": LABELS, "tables": tables, "payload": payload}, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    )
    document = (
        '<!doctype html><html lang="zh-CN" data-lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; connect-src \'none\'; base-uri \'none\'">'
        f'<title>{esc(manifest["workspace_name"])} · LGZ 基线</title><style>' + CSS + "</style></head><body>"
        + body
        + '<noscript>汇总可直接阅读；搜索与导出需启用 JavaScript。</noscript>'
        + '<script id="report-data" type="application/json">' + embedded + '</script>'
        + '<script data-cgat-ui="1">' + JS + "</script></body></html>\n"
    )
    fd, temporary = tempfile.mkstemp(prefix=".report.html.", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
        os.replace(temporary, root / "report.html")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return root / "report.html"


grt_flow_html = lgz_flow_html

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=Path(__file__).resolve().parent)
    print(render(parser.parse_args().report_dir))
