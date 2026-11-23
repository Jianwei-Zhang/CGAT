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
# The report is a portable overview, not another copy of the evidence registry.
# Exact counts and original provenance stay visible; full audit files stay on
# the Server. This projection also bounds legacy report snapshots at render time.
REPORT_PREVIEW_ROWS = 200


def project_report_facts(facts: dict) -> dict:
    projected = dict(facts)
    projected_tables = {}
    for name, value in facts.get("tables", {}).items():
        rows = value.get("rows", [])
        count = value.get("row_count", len(rows))
        projected_tables[name] = {**value, "rows": rows[:REPORT_PREVIEW_ROWS],
                                  "row_count": count,
                                  "preview_only": count > min(len(rows), REPORT_PREVIEW_ROWS)}
    if "tables" in facts:
        projected["tables"] = projected_tables
    if isinstance(facts.get("result"), dict):
        result = dict(facts["result"])
        counts = dict(result.get("report_array_counts", {}))
        audit_arrays = {"events", "strategies", "classification_rows", "terminal_rows",
                        "evidence_rows", "usage_rows", "q_rows", "attempts"}
        for key, value in list(result.items()):
            if key in audit_arrays and isinstance(value, list):
                counts.setdefault(key, len(value))
                # final_summary reconciles every published event against q4.
                # Keep the complete event snapshot; HTML still previews it.
                if key != "events":
                    result[key] = value[:REPORT_PREVIEW_ROWS]
        for key, name in (("evidence_rows", "evidence"), ("usage_rows", "usage"), ("q_rows", "q_segments")):
            table = projected_tables.get(name)
            if key in result and table and table.get("available"):
                result[key] = {"report_table": name, "row_count": table["row_count"],
                               "source": table.get("source")}
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
    "computed": "本次执行", "cache_reused": "复用已验证缓存", "frozen_original_lgz": "保留原引擎 LGZ 结果（未重新运行）", "not_started": "尚未开始",
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
# This renderer also runs standalone inside exported reports.
PREPARE_IDS = ("lgz_prepare", "grt_prepare")

METHODS = {
    "prepare": "记录原始文件身份、数据角色与规范化后的 FASTA 统计。",
    "assign": "依据经过过滤的参考比对及覆盖率阈值分配染色体，记录方向与排列顺序。",
    "degap_gapfill": "LGZ 完成后使用 reads 补剩余内部 gap，保留原始 LGZ 结果；不延伸端粒。",
    **dict.fromkeys(PREPARE_IDS, "构建 q0，锁定普通供体与端粒供体；旧工作区按保存的配方保留 reads 质量评估。"),
    "step1": "生成并验证补丁候选，按染色体选择补丁或结构修正分支，生成 q1。",
    "step2": "处理结构问题、重叠与后续优化填补，记录过滤和未解决的问题，生成 q2。",
    "step3": "检查染色体两端、验证端粒供体并记录处理结果，生成 q3 / Final Path。",
}


def label(value) -> str:
    return LABELS.get(str(value), str(value))


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def display(value) -> str:
    if value is None or value == "":
        return "未记录 / 未测量"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, dict):
        return "；".join(f"{k}：{display(v)}" for k, v in value.items()) or "无"
    if isinstance(value, list):
        return "、".join(display(v) for v in value) or "无"
    return str(value)


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
        for key, value in values.items()) + "</dl>"


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
        return f'<strong>{esc(version)}</strong><span class="muted">统计尚不可用</span>'
    return (f'<strong>{esc(version)}</strong><span>{esc(compact_number(stats.get("length_bp")))} · '
            f'{esc(display(stats.get("sequence_count")))} 条序列</span>'
            f'<span>{esc(display(stats.get("gap_count")))} Gap · N50 {esc(compact_number(stats.get("n50_bp")))}</span>')


def stage_io_html(record: dict) -> str:
    facts = record.get("facts", {})
    result = facts.get("result", {})
    versions = facts.get("sequence_versions", {})
    stage_id = record.get("stage_id", "")
    input_version = result.get("q_input_version")
    output_version = result.get("q_output_version")
    if input_version:
        input_body = sequence_snapshot(input_version, versions.get(input_version))
    elif stage_id.startswith("ref:"):
        input_body = f'<strong>{esc(stage_id.split(":", 1)[1])} FASTA</strong><span>参考染色体 FASTA</span>'
    elif stage_id == "assign":
        input_body = '<strong>参考比对 PAF</strong><span>全部数据集的过滤后比对</span>'
    elif stage_id in PREPARE_IDS:
        input_body = ('<strong>多组装候选与完整比对证据</strong><span>全部 ds 的参考/ctg 比对及可选 QC 数据</span>'
                      if facts.get("q0_construction") else
                      '<strong>归属与排列结果</strong><span>主组装、辅助组装及可选 QC 数据</span>')
    elif stage_id.startswith("chr:"):
        input_body = f'<strong>Final Path · {esc(stage_id.split(":", 1)[1])}</strong><span>最终染色体与路径证据</span>'
    elif stage_id == "finalize_evidence":
        input_body = '<strong>Final Path</strong><span>阶段事件、供体使用和比对证据</span>'
    elif stage_id.startswith("package_"):
        input_body = '<strong>已验证工作目录</strong><span>结果、元数据和交付脚本</span>'
    else:
        input_body = '<strong>上一阶段结果</strong><span>详见参数与溯源记录</span>'

    outputs = facts.get("outputs", [])
    if output_version:
        output_body = sequence_snapshot(output_version, versions.get(output_version))
    elif stage_id.startswith("ref:"):
        summary = facts.get("summary", {})
        output_body = (f'<strong>参考比对结果 PAF</strong><span>{esc(display(summary.get("alignment_count")))} 条比对</span>'
                       f'<span>{esc(display(summary.get("aligned_query_count")))} 条 contig 有比对</span>')
    elif stage_id == "assign":
        summary = facts.get("summary", {})
        output_body = (f'<strong>染色体归属与顺序</strong><span>{esc(display(summary.get("assigned_unique_contigs")))} 条 contig 已分配</span>'
                       f'<span>{esc(display(summary.get("unassigned_contigs")))} 条未分配</span>')
    elif stage_id in PREPARE_IDS:
        output_body = sequence_snapshot("q0", versions.get("q0"))
    elif stage_id.startswith("chr:"):
        output_body = '<strong>染色体级证据</strong><span>路径片段、事件与来源坐标</span>'
    elif stage_id == "finalize_evidence":
        summary = facts.get("summary", {})
        output_body = (f'<strong>可追溯 LGZ 结果</strong><span>{esc(display(summary.get("events")))} 个事件 · '
                       f'{esc(display(summary.get("evidence")))} 条证据</span>')
    elif outputs:
        output_body = (f'<strong>{esc(outputs[0].get("file", "交付文件"))}</strong>'
                       f'<span>{esc(compact_number(outputs[0].get("size_bytes")))} · SHA-256 已记录</span>')
    else:
        output_body = '<strong>阶段输出</strong><span>尚未生成或未记录</span>'

    method = METHODS.get(stage_id, record.get("title", "执行阶段"))
    return (f'<div class="io-flow"><div class="io-card input"><small>INPUT</small>{input_body}</div>'
            f'<div class="io-arrow" aria-hidden="true">→</div><div class="io-card process"><small>PROCESS</small>'
            f'<strong>{esc(record.get("title", stage_id))}</strong><span>{esc(method)}</span></div>'
            f'<div class="io-arrow" aria-hidden="true">→</div><div class="io-card output"><small>OUTPUT</small>{output_body}</div></div>')


def pipeline_map_html(records: list[dict], input_facts: dict, final: dict) -> str:
    datasets = input_facts.get("datasets", [])
    refs = [row for row in records if row.get("stage_id", "").startswith("ref:")]
    assignment = next((row for row in records if row.get("stage_id") == "assign"), {})
    prepare_record = next((row for row in records if row.get("stage_id") in PREPARE_IDS), {})
    q0 = prepare_record.get("facts", {}).get("sequence_versions", {}).get("q0", {})
    q4 = final.get("sequence_versions", {}).get(final.get("final_q_version", "q4"), {})
    assigned = assignment.get("facts", {}).get("summary", {}).get("assigned_unique_contigs")
    stages = [
        ("01", "原始输入", f"{len(datasets)} 组 FASTA",
         "参考与多组装候选" if input_facts.get("q0_mode") == "evidence_guided_multi_source" else "参考、主组装与辅助组装"),
        ("02", "参考比对", f"{len(refs)} 个比对任务", "生成覆盖与定位证据"),
        ("03", "染色体归属", f"{display(assigned)} 条 contig", "按覆盖、方向和锚点排序"),
        ("04", "构建 q0 与供体", f"{compact_number(q0.get('length_bp'))}", f"{display(q0.get('gap_count'))} 个初始 Gap"),
        ("05", "LGZ 修复", ("q0 → q1 → q2 → q3" if final.get("final_q_version") == "q3" else "q0 → q1 → q2 → q3 → q4"), "填补、结构修正与端粒处理"),
        ("06", "最终结果", f"{compact_number(q4.get('length_bp'))}", f"{display(q4.get('sequence_count'))} 条输出序列 · {display(q4.get('gap_count'))} 个 Gap"),
        ("07", "证据与交付", f"{display(final.get('process_summary', {}).get('event_count'))} 个事件", "HTML、JSON 与 Server ZIP"),
    ]
    cards = []
    for index, (number, title, metric, description) in enumerate(stages):
        cards.append(f'<div class="pipeline-node"><span class="pipeline-number">{number}</span><strong>{esc(title)}</strong>'
                     f'<b>{esc(metric)}</b><small>{esc(description)}</small></div>')
        if index < len(stages) - 1:
            cards.append('<div class="pipeline-arrow" aria-hidden="true">→</div>')
    return '<div class="pipeline-map">' + "".join(cards) + '</div>'


def lgz_flow_html(grt: list[dict], final: dict) -> str:
    stats_by_version = {}
    stage_by_output = {}
    for record in grt:
        facts = record.get("facts", {})
        stats_by_version.update(facts.get("sequence_versions", {}))
        output = facts.get("result", {}).get("q_output_version")
        if output:
            stage_by_output[output] = record
    stats_by_version.update(final.get("sequence_versions", {}))
    order = [version for version in ("q0", "q0r1", "q0f", "q1", "q2", "q3", "q4") if version in stats_by_version]
    nodes = []
    for index, version in enumerate(order):
        record = stage_by_output.get(version, {})
        summary = record.get("facts", {}).get("summary", {})
        status = summary.get("by_status", {})
        stats = stats_by_version[version]
        nodes.append(f'<div class="grt-node"><strong>{esc(version)}</strong><b>{esc(compact_number(stats.get("length_bp")))}</b>'
                     f'<span>{esc(display(stats.get("gap_count")))} Gap · N50 {esc(compact_number(stats.get("n50_bp")))}</span>'
                     f'<small>{esc(display(summary.get("event_count")))} 事件 · {esc(display(status.get("accepted", 0)))} 接受</small></div>')
        if index < len(order) - 1:
            nodes.append('<div class="grt-arrow" aria-hidden="true">→</div>')
    return '<div class="grt-flow" id="grt-flow">' + "".join(nodes) + '</div>' if nodes else '<p class="note">LGZ 序列版本尚不可用。</p>'


def outcome_summary_html(final: dict) -> str:
    summary = final.get("outcome_summary", {})
    t2t_status = summary.get("t2t_status", "unavailable")
    t2t_text = {"achieved": "已达到", "not_achieved": "尚未达到",
                "unknown": "待评估", "unavailable": "暂无结果"}.get(t2t_status, "待评估")
    t2t_detail = {
        "achieved": "已输出序列无 N/Gap，且两端均检测到端粒信号；不等于全基因组完整性验收",
        "not_achieved": "仍有 N/Gap，或至少一个染色体末端缺少端粒信号",
        "unknown": "端粒末端记录不完整，暂不能判断",
        "unavailable": "最终路径 尚未生成",
    }.get(t2t_status, "")
    complete = summary.get("telomere_ends_complete")
    total = summary.get("telomere_ends_total")
    telomere_value = f"{display(complete)} / {display(total)}" if complete is not None and total else "未测量"
    telomere_detail = ("染色体端点完整" if summary.get("telomeres_complete")
                        else ("完整端点 / 应有端点" if total else "等待最终端粒检测结果"))
    chromosome_count = summary.get("chromosome_count")
    starting_gaps = summary.get("starting_gap_count")
    remaining_gaps = summary.get("remaining_gap_count")
    gap_change = summary.get("gap_count_change")
    if gap_change is None and starting_gaps is not None and remaining_gaps is not None:
        gap_change = remaining_gaps - starting_gaps
    gap_text = f"{gap_change:+,}" if isinstance(gap_change, int) and gap_change != 0 else display(gap_change)
    cards = [
        ("总长度", compact_number(summary.get("total_length_bp")),
         f'{display(chromosome_count)} 条最终序列' if chromosome_count is not None else "最终序列尚未生成", "length"),
        ("Gap 数净变化", gap_text,
         "Final Path − q0；减少不等于真实缺失序列闭合", "remaining" if isinstance(gap_change, int) and gap_change > 0 else "closed"),
        ("剩余 Gap", display(summary.get("remaining_gap_count")),
         "连续 N ≥ 100 bp", "remaining"),
        ("端粒完整性", telomere_value, telomere_detail, "telomere"),
        ("T2T 结构条件", t2t_text, t2t_detail, f"t2t {t2t_status}"),
    ]
    return '<div class="outcome-grid">' + "".join(
        f'<article class="outcome-card {esc(kind)}"><span>{esc(title)}</span><strong>{esc(value)}</strong><small>{esc(detail)}</small></article>'
        for title, value, detail, kind in cards) + '</div>'


def annotation_evidence_text(raw) -> str:
    try:
        entries = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return ""
    if not isinstance(entries, list):
        return ""
    return "; ".join(": ".join(str(entry.get(k, "")) for k in ("source", "id", "note") if entry.get(k))
                     for entry in entries if isinstance(entry, dict))


def final_path_visual_html(final: dict) -> str:
    chromosomes = final.get("final_path", {}).get("chromosomes", [])
    if not chromosomes:
        return '<p class="warn">本次运行尚无可绘制的 Final Path。</p>'
    contributions = final.get("source_contribution_bp", {})
    total_contribution = sum(value for value in contributions.values() if isinstance(value, (int, float))) or 1
    contribution_parts = []
    for index, (dataset, value) in enumerate(contributions.items()):
        percentage = 100 * value / total_contribution
        contribution_parts.append(f'<i class="source-{index % 5}" style="width:{percentage:.6f}%" title="{esc(dataset)}: {esc(display(value))} bp"></i>')
    contribution_legend = "".join(
        f'<span><i class="legend-dot source-{index % 5}"></i>{esc(dataset)} · {esc(compact_number(value))}</span>'
        for index, (dataset, value) in enumerate(contributions.items()))

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
    tracks = []
    for chromosome in chromosomes:
        segments = chromosome.get("segments", [])
        total = chromosome.get("q4_length") or sum(max(0, segment.get("length", 0)) for segment in segments) or 1
        pieces = []
        segment_rows = []
        for segment in segments:
            length = max(0, segment.get("length", 0) or 0)
            kind = segment.get("kind", "source")
            source = segment.get("source") or {}
            dataset = source.get("dataset", "")
            contig = source.get("contig", "")
            orientation = source.get("orientation", segment.get("orientation", ""))
            title = (f'{chromosome.get("chr")} · {label(kind)} · {dataset}:{contig} · {display(length)} bp'
                     f' · {orientation or "方向未记录"} · event {segment.get("event_id") or "无"}')
            class_name = "gap" if kind == "gap" else ("patch" if kind == "patch" else "source")
            text = "GAP" if kind == "gap" else (contig if 100 * length / total >= 8 else "")
            pieces.append(f'<i class="path-segment {class_name}" style="flex-grow:{max(1, length)}" title="{esc(title)}"><span>{esc(text)}</span></i>')
            segment_rows.append({"kind": label(kind), "dataset": dataset, "contig": contig,
                                 "length_bp": length, "orientation": orientation,
                                 "source_range": f'{source.get("start", "-")}–{source.get("end", "-")}',
                                 "event_id": segment.get("event_id")})
        chromosome_name = chromosome.get("chr")
        markers = []
        terminal_rows = terminal_by_chr.get(chromosome_name, {})
        if telomere.get("configured"):
            for terminal, side in (("5prime", "left"), ("3prime", "right")):
                row = terminal_rows.get(terminal, {})
                complete = row.get("final_status") in complete_statuses
                marker_title = f'{chromosome_name} {terminal} · {"端粒完整" if complete else "未检测到完整端粒"}'
                evidence = "; ".join(annotation_evidence_text(rules_by_id.get(rule_id, {}).get("provenance"))
                                     for rule_id in row.get("matched_rule_ids", []))
                marker_title += f" · {evidence}" if evidence else ""
                markers.append(f'<span class="path-marker telomere {side} {"complete" if complete else "missing"}" title="{esc(marker_title)}"></span>')
        chromosome_centromeres = centromere_by_chr.get(chromosome_name, [])
        if centromere.get("configured"):
            for marker in chromosome_centromeres:
                start = max(1, marker.get("q4_start", 1))
                end = min(total, marker.get("q4_end", total))
                left = 100 * (start - 1) / total
                width = max(.45, 100 * max(1, end - start + 1) / total)
                marker_title = (f'{chromosome_name} 着丝粒候选区域 · Final Path:{display(start)}–{display(end)} · '
                                f'{marker.get("dataset_name", "")}:{marker.get("ctg_name", "")}')
                evidence = annotation_evidence_text(marker.get("provenance"))
                marker_title += f" · {evidence}" if evidence else ""
                markers.append(f'<span class="path-marker centromere" style="left:{left:.6f}%;width:{width:.6f}%" title="{esc(marker_title)}"></span>')
        details = "".join(
            f'<li><span class="segment-chip {"gap" if row["kind"] == label("gap") else ("patch" if row["kind"] == label("patch") else "source")}">{esc(row["kind"])}</span>'
            f'<strong>{esc(row["dataset"] or "连接片段")} {esc(row["contig"])}</strong><span>{esc(compact_number(row["length_bp"]))} · '
            f'{esc(row["orientation"] or "-")} · {esc(row["source_range"])}</span></li>' for row in segment_rows)
        annotation_bits = []
        if telomere.get("configured"):
            complete_count = sum(row.get("final_status") in complete_statuses for row in terminal_rows.values())
            annotation_bits.append(f"端粒 {complete_count}/2")
        if centromere.get("configured"):
            annotation_bits.append(f"着丝粒候选区域 {len(chromosome_centromeres)} 处")
        annotation_html = (f'<div class="chromosome-annotations">{esc(" · ".join(annotation_bits))}</div>'
                           if annotation_bits else "")
        tracks.append(f'<details class="path-row"><summary><b>{esc(chromosome_name)}</b><div class="path-bar">{"".join(pieces)}{"".join(markers)}</div>'
                      f'<span class="path-length">{esc(compact_number(total))}</span></summary>{annotation_html}<ul class="segment-list">{details}</ul></details>')
    annotation_legend = ""
    if telomere.get("configured"):
        annotation_legend += ('<span><i class="legend-symbol telomere"></i>端粒完整</span>'
                              '<span><i class="legend-symbol telomere-missing"></i>端粒缺失</span>')
    if centromere.get("configured"):
        annotation_legend += '<span><i class="legend-symbol centromere"></i>着丝粒候选区域</span>'
    return (f'<div class="source-summary"><div><h3>最终序列来源贡献</h3><div class="source-bar">{"".join(contribution_parts)}</div>'
            f'<div class="legend">{contribution_legend}</div></div></div>'
            '<div class="legend path-legend"><span><i class="legend-dot source"></i>主路径来源</span>'
            f'<span><i class="legend-dot patch"></i>LGZ 补丁 / 替换</span><span><i class="legend-dot gap"></i>仍保留的 Gap</span>{annotation_legend}</div>'
            f'<div class="path-map" id="grt-final-path">{"".join(tracks)}</div>'
            '<p class="note">每行是一条最终染色体，色块和标记按最终坐标缩放。点击染色体查看片段来源与标记数量，悬停查看坐标。</p>')


CSS = """
:root{
  color-scheme:light;
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
  --font-mono:ui-monospace,"Cascadia Code",Consolas,monospace;
  --card-radius:6px;--control-radius:5px;
  --surface-app:#f1f5f9;--surface-panel:#ffffff;--surface-subtle:#f8fafc;--surface-muted:#eef2f6;
  --border-subtle:#dbe3ec;--border-default:#cbd5e1;--border-strong:#94a3b8;
  --ink:#1e293b;--text-secondary:#334155;--muted:#64748b;
  --line:#dbe3ec;--accent:#2563eb;
  --action-primary-bg:#234b76;--action-primary-hover:#1b3c60;--focus-ring:#4f82b5;
  --shadow-xs:0 1px 2px rgba(15,23,42,.04);--shadow-sm:0 1px 3px rgba(15,23,42,.06),0 1px 2px rgba(15,23,42,.04);
  --tone-ok-ink:#166534;--tone-ok-bg:#ecfdf5;--tone-ok-line:#86efac;
  --tone-warn-ink:#92400e;--tone-warn-bg:#fffbeb;--tone-warn-line:#f59e0b;
  --tone-err-ink:#991b1b;--tone-err-bg:#fef2f2;--tone-err-line:#fca5a5;
  --tone-info-ink:#1e40af;--tone-info-bg:#eff6ff;--tone-info-line:#93c5fd;
  --source:#2d6a9f;--patch:#d97706;--gap:#dc2626;--process:#4f46e5;--telomere:#15803d;--centromere:#6d28d9;
}
@media (prefers-color-scheme:dark){
  :root{
    color-scheme:dark;
    --surface-app:#101720;--surface-panel:#17212e;--surface-subtle:#1d2938;--surface-muted:#243244;
    --border-subtle:#344458;--border-default:#42546a;--border-strong:#748ba5;
    --ink:#e5edf7;--text-secondary:#c7d5e6;--muted:#9bacc1;
    --line:#344458;--accent:#8abaff;
    --action-primary-bg:#2f5f92;--action-primary-hover:#386fa8;--focus-ring:#91bfff;
    --shadow-xs:0 1px 2px #0003;--shadow-sm:0 2px 5px #0004;
    --tone-ok-ink:#a2dfb3;--tone-ok-bg:#20382d;--tone-ok-line:#77b38b;
    --tone-warn-ink:#f4d098;--tone-warn-bg:#3a3022;--tone-warn-line:#b79966;
    --tone-err-ink:#ffb4ae;--tone-err-bg:#422b31;--tone-err-line:#c68989;
    --tone-info-ink:#a6ccff;--tone-info-bg:#253d57;--tone-info-line:#7fa4d1;
    --source:#3c7bb3;--patch:#d98a2b;--gap:#e0626c;--process:#818cf8;--telomere:#34a866;--centromere:#9575cd;
  }
}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);background:var(--surface-app);font:14px/1.55 system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:3px}
code,pre{font-family:var(--font-mono)}
code{font-size:.9em;background:var(--surface-muted);padding:.1em .35em;border-radius:4px;overflow-wrap:anywhere}
header{background:var(--surface-panel);color:var(--ink);border-top:3px solid var(--action-primary-bg);border-bottom:1px solid var(--border-default);box-shadow:var(--shadow-xs);padding:18px max(20px,calc((100vw - 1240px)/2)) 16px}
.header-eyebrow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px}
.tagline{font-size:11.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--text-secondary)}
.scope-pill{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:11.5px;font-weight:600;background:var(--tone-info-bg);color:var(--tone-info-ink);border:1px solid var(--tone-info-line)}
.header-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap}
header p{color:var(--text-secondary);margin:4px 0 0;font-size:13.5px}
h1{font-size:24px;line-height:1.25;margin:0;letter-spacing:-.01em}
h2{font-size:18px;line-height:1.3;margin:0 0 12px}
h3{font-size:15px;line-height:1.35;margin:16px 0 8px}
main{max-width:1280px;margin:auto;padding:18px 20px 32px}
section,.stage{background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--card-radius);margin-bottom:16px;padding:18px 20px;min-width:0;box-shadow:var(--shadow-xs)}
nav{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 0;padding-top:11px;border-top:1px solid var(--border-subtle)}
nav a{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:var(--control-radius);border:1px solid var(--border-default);background:var(--surface-subtle);color:var(--ink);font-size:13px;font-weight:500}
nav a:hover{border-color:var(--border-strong);background:var(--surface-muted);text-decoration:none}
.nav-num{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;padding:0 4px;border-radius:4px;background:var(--action-primary-bg);color:#fff;font:700 11px/1 var(--font-mono)}
button{font:inherit;cursor:pointer;background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--control-radius);padding:5px 12px;color:var(--ink)}
button:hover{background:var(--surface-muted);border-color:var(--border-strong)}button:disabled{opacity:.45;cursor:default}
.badge{display:inline-flex;align-items:center;gap:4px;background:var(--surface-muted);color:var(--text-secondary);border:1px solid var(--border-default);border-radius:999px;padding:2px 10px;font-size:12px;font-weight:600;white-space:nowrap}
.success,.prepared{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border-color:var(--tone-ok-line)}
.failed{color:var(--tone-err-ink);background:var(--tone-err-bg);border-color:var(--tone-err-line)}
.interrupted{color:var(--tone-warn-ink);background:var(--tone-warn-bg);border-color:var(--tone-warn-line)}
.running,.preparing{color:var(--tone-info-ink);background:var(--tone-info-bg);border-color:var(--tone-info-line)}
.topline-bar{display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;padding:9px 12px;border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-subtle);margin:8px 0 12px;font-size:13px;font-variant-numeric:tabular-nums}
.topline-bar strong{color:var(--ink)}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(185px,1fr));gap:12px;margin:10px 0}.facts div{border-left:2px solid var(--border-default);padding-left:10px}.facts dt{color:var(--muted);font-size:12px}.facts dd{margin:2px 0;overflow-wrap:anywhere;font-weight:600;font-variant-numeric:tabular-nums}
.note,.muted{color:var(--muted);font-size:13px}.note{margin:7px 0}
.warn{border-left:3px solid var(--tone-warn-line);padding:10px 12px;background:var(--tone-warn-bg);color:var(--ink);border-radius:0 var(--card-radius) var(--card-radius) 0;margin:8px 0;font-size:13.5px}
.warn.is-error{border-left-color:var(--tone-err-line);background:var(--tone-err-bg)}
details>summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}details{margin-top:10px}details.block{border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:10px 12px;background:var(--surface-panel)}details.block>summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.stage>summary{font-size:16px}.stage-body{padding-top:10px}
.scroll{overflow:auto;-webkit-overflow-scrolling:touch;max-height:540px;border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-panel)}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--border-subtle);padding:8px 11px;text-align:left;vertical-align:top}
th{background:var(--surface-subtle);color:var(--text-secondary);position:sticky;top:0;z-index:1;white-space:nowrap;font-weight:600}
td{max-width:480px;min-width:96px;overflow-wrap:anywhere}tbody tr:hover{background:var(--surface-subtle)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:10px 12px;max-height:420px;overflow:auto;color:var(--ink)}
.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}.toolbar input{flex:1;min-width:160px;padding:6px 9px;border:1px solid var(--border-default);border-radius:var(--control-radius);background:var(--surface-panel);color:var(--ink);font:inherit}
.timeline{list-style:none;padding:0;margin:0}.timeline li{display:flex;gap:10px;align-items:center;padding:7px 0;border-bottom:1px solid var(--border-subtle);flex-wrap:wrap}.timeline a{flex:1;min-width:210px}
.bar{height:5px;background:var(--surface-muted);border-radius:3px;overflow:hidden;margin-top:4px}.bar i{display:block;height:100%;background:var(--accent)}
.metric{font-variant-numeric:tabular-nums}.footer{color:var(--muted);font-size:12px;margin:18px 0;text-align:center}
.summary-panel{border-left:4px solid var(--action-primary-bg)}
.summary-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap}.summary-heading p{margin:2px 0;color:var(--muted);font-size:13px}
.outcome-grid{display:grid;grid-template-columns:repeat(5,minmax(140px,1fr));gap:10px;margin-top:12px}
.outcome-card{position:relative;overflow:hidden;min-height:112px;border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:12px 13px;background:var(--surface-subtle);display:flex;flex-direction:column}
.outcome-card:before{content:'';position:absolute;inset:0 auto 0 0;width:3px;background:var(--accent)}
.outcome-card span{color:var(--muted);font-size:12px}.outcome-card strong{font-size:22px;line-height:1.2;margin:6px 0 5px;font-variant-numeric:tabular-nums}.outcome-card small{color:var(--muted);line-height:1.35;font-size:12px}
.outcome-card.closed:before,.outcome-card.telomere:before,.outcome-card.t2t.achieved:before{background:var(--telomere)}
.outcome-card.remaining:before,.outcome-card.t2t.not_achieved:before{background:var(--gap)}
.outcome-card.t2t.unknown:before,.outcome-card.t2t.unavailable:before{background:var(--border-strong)}
.pipeline-map{display:flex;align-items:stretch;gap:7px;overflow:auto;padding:4px 2px 12px}
.pipeline-node{flex:1 0 142px;min-height:132px;border:1px solid var(--border-subtle);border-top:3px solid var(--action-primary-bg);border-radius:var(--card-radius);padding:11px;background:var(--surface-subtle);display:flex;flex-direction:column;gap:4px}
.pipeline-node strong{font-size:14.5px}.pipeline-node b{font-size:16px;margin-top:auto;font-variant-numeric:tabular-nums}.pipeline-node small{color:var(--muted);font-size:12px}
.pipeline-number{font:700 11.5px/1 var(--font-mono);color:var(--accent);letter-spacing:.5px}
.pipeline-arrow,.io-arrow,.grt-arrow{display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:20px;font-weight:300}.workflow-copy{max-width:820px;color:var(--muted);font-size:13.5px}
.io-flow{display:grid;grid-template-columns:minmax(0,1fr) 24px minmax(0,1.15fr) 24px minmax(0,1fr);align-items:stretch;gap:6px;margin:12px 0}
.io-card{border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:11px;display:flex;flex-direction:column;gap:3px;min-width:0;background:var(--surface-subtle)}
.io-card small{font:700 10.5px/1.2 var(--font-mono);letter-spacing:1px;color:var(--muted)}.io-card strong{overflow-wrap:anywhere}.io-card span{font-size:12.5px;color:var(--muted)}
.io-card.input{border-top:3px solid var(--source)}.io-card.process{border-top:3px solid var(--process)}.io-card.output{border-top:3px solid var(--accent)}
.grt-flow{display:flex;align-items:stretch;overflow:auto;padding:4px 2px 12px;gap:6px}
.grt-node{flex:1 0 140px;border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:11px;display:flex;flex-direction:column;gap:3px;background:var(--surface-subtle)}
.grt-node strong{color:var(--accent);font:700 16px/1 var(--font-mono)}.grt-node b{font-size:15.5px;margin-top:4px;font-variant-numeric:tabular-nums}.grt-node span,.grt-node small{color:var(--muted);font-size:12px}
.grt-node:last-of-type{border-color:var(--tone-ok-line);background:var(--tone-ok-bg)}
.source-summary{background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:13px;margin:10px 0}.source-summary h3{margin:0 0 8px}
.source-bar{display:flex;height:18px;overflow:hidden;border-radius:5px;background:var(--surface-muted)}.source-bar i{display:block;min-width:2px}
.source-0{background:#2d6a9f}.source-1{background:#d97706}.source-2{background:#4d8b55}.source-3{background:#6d51a6}.source-4{background:#b85d82}
.legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;color:var(--muted);font-size:12.5px}
.legend-dot,.legend-symbol{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}
.legend-dot.source{background:var(--source)}.legend-dot.patch{background:var(--patch)}.legend-dot.gap{background:repeating-linear-gradient(45deg,var(--gap),var(--gap) 3px,#fff 3px,#fff 5px);border:1px solid var(--gap);box-sizing:border-box}
.legend-symbol.telomere{background:var(--telomere);border-radius:50%}.legend-symbol.telomere-missing{border:2px solid var(--gap);border-radius:50%;background:var(--surface-panel)}.legend-symbol.centromere{background:var(--centromere);transform:rotate(45deg);border-radius:1px}
.path-legend{margin:14px 0 8px}
.path-map{border:1px solid var(--border-subtle);border-radius:var(--card-radius);overflow:hidden;background:var(--surface-panel)}
.path-row{margin:0;border-bottom:1px solid var(--border-subtle)}.path-row:last-child{border:0}
.path-row>summary{display:grid;grid-template-columns:76px minmax(220px,1fr) 82px;gap:10px;align-items:center;padding:8px 11px;list-style:none}
.path-row>summary::-webkit-details-marker{display:none}.path-row>summary:hover{background:var(--surface-subtle)}
.path-bar{position:relative;display:flex;align-items:stretch;height:26px;border-radius:4px;overflow:hidden;background:var(--surface-muted)}
.path-segment{display:block;min-width:2px;border-right:1px solid rgba(255,255,255,.65);overflow:hidden;font-style:normal}
.path-segment.source{background:var(--source)}.path-segment.patch{background:var(--patch);min-width:5px}.path-segment.gap{background:repeating-linear-gradient(45deg,var(--gap),var(--gap) 3px,#fff 3px,#fff 5px);min-width:5px}
.path-segment span{display:block;color:#fff;font-size:10px;line-height:26px;padding:0 5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.path-marker{position:absolute;z-index:2;pointer-events:auto}.path-marker.telomere{top:3px;width:9px;height:20px;background:var(--telomere);border:2px solid var(--surface-panel);border-radius:8px}
.path-marker.telomere.left{left:2px}.path-marker.telomere.right{right:2px}.path-marker.telomere.missing{background:var(--surface-panel);border-color:var(--gap)}
.path-marker.centromere{top:2px;height:22px;min-width:7px;background:var(--centromere);border:2px solid var(--surface-panel);border-radius:3px}
.path-length{text-align:right;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.chromosome-annotations{padding:5px 11px 5px 96px;color:var(--muted);font-size:12px;background:var(--surface-subtle)}
.segment-list{list-style:none;margin:0;padding:7px 11px 12px 96px;background:var(--surface-subtle)}
.segment-list li{display:grid;grid-template-columns:105px minmax(140px,1fr) minmax(150px,1fr);gap:8px;padding:5px 0;border-bottom:1px solid var(--border-subtle);font-size:12.5px}
.segment-chip{display:inline-block;border-radius:10px;padding:1px 7px;width:max-content;color:#fff;font-size:11.5px}.segment-chip.source{background:var(--source)}.segment-chip.patch{background:var(--patch)}.segment-chip.gap{background:var(--gap)}
.audit-box{background:transparent;border:0;padding:0;margin:0}.audit-box>summary{background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:11px 14px;font-size:15px;margin-bottom:12px}.audit-box[open]>summary{border-color:var(--border-strong)}
.secondary-results{margin-top:14px}.technical-section{padding:0}.section-disclosure{margin:0}.section-disclosure>summary{padding:14px 18px;font-size:16px;list-style-position:inside}.section-disclosure[open]{padding:0 18px 18px}.section-disclosure[open]>summary{margin:0 -18px 14px;border-bottom:1px solid var(--border-subtle);background:var(--surface-subtle)}
@media(max-width:980px){.outcome-grid{grid-template-columns:repeat(2,minmax(140px,1fr))}.outcome-card.t2t{grid-column:1/-1}}
@media(max-width:760px){main{padding:12px}section,.stage{padding:14px}h1{font-size:20px}.facts{grid-template-columns:1fr 1fr}.summary-heading{display:block}.outcome-grid{grid-template-columns:1fr}.outcome-card.t2t{grid-column:auto}.pipeline-map{scroll-snap-type:x proximity}.pipeline-node{scroll-snap-align:start;flex-basis:75vw}.io-flow{grid-template-columns:1fr}.io-arrow{transform:rotate(90deg);height:20px}.path-row>summary{grid-template-columns:58px minmax(160px,1fr)}.path-length{display:none}.chromosome-annotations,.segment-list{padding-left:12px}.segment-list li{grid-template-columns:92px 1fr}.segment-list li span:last-child{grid-column:2}.grt-node{flex-basis:58vw}}
@media print{body{background:#fff;color:#000}header{background:#fff;color:#000;padding:12px;box-shadow:none}main{padding:0}button,.toolbar,nav{display:none}section,.stage{break-inside:avoid;border-radius:0;box-shadow:none}.scroll{max-height:none}details:not([open])>summary:after{content:'（明细见电子版）';font-size:12px}}
"""

JS = r"""
const data=JSON.parse(document.getElementById('report-data').textContent);
const labels=data.labels, enums=new Set(['status','action','reason','outcome','role','process_status','process_reason','final_status','final_reason','reads_qc','self_alignment','kind','qc']), fmt=(v,key)=>v===null||v===undefined||v===''?'未记录 / 未测量':typeof v==='object'?JSON.stringify(v,null,2):(enums.has(key)?labels[String(v)]||String(v):String(v));
const save=(value,name)=>{const a=document.createElement('a');const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
document.getElementById('download').onclick=()=>save({...data.payload,tables:data.tables},'server-report.json');
for(const box of document.querySelectorAll('[data-table]')){
 let ready=false;
 box.addEventListener('toggle',()=>{if(!box.open||ready)return;ready=true;
 const rows=data.tables[Number(box.dataset.table)], cols=[...new Set(rows.flatMap(r=>Object.keys(r)))];
 const toolbar=document.createElement('div');toolbar.className='toolbar';
 const search=document.createElement('input');search.type='search';search.placeholder='搜索本报告已嵌入的记录';search.setAttribute('aria-label',box.querySelector('summary').textContent+' 搜索');
 const prev=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span'),download=document.createElement('button');prev.textContent='上一页';next.textContent='下一页';download.textContent='下载表格展示数据 JSON';toolbar.append(search,prev,count,next,download);box.append(toolbar);
 const scroll=document.createElement('div');scroll.className='scroll';const table=document.createElement('table');const head=document.createElement('thead'),tr=document.createElement('tr');for(const key of cols){const th=document.createElement('th');th.textContent=labels[key]||key;tr.append(th)}head.append(tr);const body=document.createElement('tbody');table.append(head,body);scroll.append(table);box.append(scroll);
 let page=0,filtered=rows;const size=50;
 const draw=()=>{body.replaceChildren();for(const row of filtered.slice(page*size,(page+1)*size)){const tr=document.createElement('tr');for(const key of cols){const td=document.createElement('td'),value=row[key];if(value&&typeof value==='object'){const d=document.createElement('details'),s=document.createElement('summary'),p=document.createElement('pre');s.textContent='查看详情';p.textContent=fmt(value,key);d.append(s,p);td.append(d)}else{td.textContent=fmt(value,key)}tr.append(td)}body.append(tr)}count.textContent=`${filtered.length? page*size+1:0}–${Math.min((page+1)*size,filtered.length)} / ${filtered.length}`;prev.disabled=page===0;next.disabled=(page+1)*size>=filtered.length};
 search.oninput=()=>{const q=search.value.toLocaleLowerCase();filtered=rows.filter(row=>Object.entries(row).some(([k,v])=>fmt(v,k).toLocaleLowerCase().includes(q)||String(v).toLocaleLowerCase().includes(q)));page=0;draw()};prev.onclick=()=>{page--;draw()};next.onclick=()=>{page++;draw()};download.onclick=()=>save(rows,'report-table.json');draw();
 });
}
"""


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
    tables = []
    table_sources = []  # Keep source identities alive until payload references are built.
    table_ids = {}

    def data_table(name, rows, available=True, metadata=None):
        if not available:
            return f'<p class="note">{esc(label(name))}：未记录 / 未测量</p>'
        count = (metadata or {}).get("row_count", len(rows))
        if id(rows) not in table_ids:
            table_ids[id(rows)] = len(tables)
            tables.append(rows if len(rows) <= REPORT_PREVIEW_ROWS else rows[:REPORT_PREVIEW_ROWS])
            table_sources.append(rows)
        index = table_ids[id(rows)]
        preview = len(tables[index])
        detail = ""
        if count > preview:
            source = (metadata or {}).get("source")
            origin = f'；完整明细来源：{esc(source)}' if source else ''
            detail = f'<p class="note">本报告仅预览前 {preview:,} / 共 {count:,} 条{origin}。完整审计文件保留在服务器工作目录中。</p>'
        return f'<details class="block" data-table="{index}"><summary>{esc(label(name))}<span class="badge">{count:,} 条</span></summary>{detail}</details>'

    def export_payload(value, path=()):
        if isinstance(value, list):
            # Input provenance keeps its established JSON shape. Only audit
            # snapshots/final-detail lists use the separate table store.
            if path and path[0] in {"steps", "grt_steps", "final_summary"} and id(value) in table_ids:
                return {"table_index": table_ids[id(value)]}
            return [export_payload(item, (*path, str(index))) for index, item in enumerate(value)]
        if isinstance(value, dict):
            return {key: export_payload(item, (*path, key)) for key, item in value.items()}
        return value

    def stats_table(name, versions):
        rows = [{"sequence": version, **{key: value.get(key) for key in
                ("sequence_count", "length_bp", "n_bp", "gap_count", "gap_bp", "n50_bp")}}
                for version, value in versions.items() if value]
        if not rows:
            return '<p class="note">序列统计尚不可用。</p>'
        columns = list(rows[0])
        max_length = max(row["length_bp"] for row in rows) or 1
        return f'<h3>{esc(name)}</h3><div class="scroll"><table><thead><tr>' + ''.join(
            f'<th>{esc(label(key))}</th>' for key in columns) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join(f'<td class="metric">{esc(display(row[key]))}' +
                (f'<div class="bar"><i style="width:{100*row[key]/max_length:.2f}%"></i></div>' if key == "length_bp" else '') +
                '</td>' for key in columns) + '</tr>' for row in rows) + '</tbody></table></div>'

    def q0_summary_html(value):
        if not value:
            return '<p class="note">本次运行尚无成功发布的 q0 构建摘要。</p>'
        summary = dict(value["summary"])
        summary["qc"] = label(summary.get("qc"))
        body = '<h3>多组装候选 → q0</h3>' + key_values(summary)
        body += notes(value.get("notes", []))
        body += key_values({"搜索限制": value.get("policy", {})})
        for name, table in value.get("tables", {}).items():
            body += data_table(name, table.get("rows", []), table.get("available", False), table)
        body += notes([f"决策来源：{value.get('source')} · SHA-256 {value.get('source_sha256')}"])
        return body

    def stage_html(record, element_id):
        facts = record.get("facts", {})
        runtime = record.get("runtime", {})
        state = record.get("status", "pending")
        body = f'<details class="stage" id="{element_id}"><summary>{esc(record["title"])} <span class="badge {esc(state)}">{esc(label(state))}</span></summary><div class="stage-body">'
        body += stage_io_html(record)
        body += key_values({"执行方式": label(record.get("execution", "unknown")),
                            "开始时间": runtime.get("started_at"), "耗时 / s": runtime.get("elapsed_seconds"),
                            "退出码": runtime.get("exit_code")})
        body += key_values(facts.get("summary", {})) + notes(facts.get("notes", []))
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
            body += '<details class="block"><summary>本次执行日志尾部（最多 80 行）</summary><pre>' + esc('\n'.join(record["output_tail"])) + '</pre></details>'
        body += '<details class="block"><summary>参数、命令与溯源记录</summary><pre>' + esc(json.dumps(
            {"command": record.get("command_text", record.get("command")),
             "parameters": facts.get("parameters"),
             "tool_version": facts.get("tool_version"), "history": record.get("history"),
             "identity": {key: value for key, value in result.items() if key not in
                          {"events", "q_rows", "usage_rows", "evidence_rows", "attempts", "classification_rows", "terminal_rows", "strategies"}}},
            ensure_ascii=False, indent=2)) + '</pre></details></div></details>'
        return body

    state = manifest["status"]
    completed_stages = sum(r.get("status") == "success" for r in records)
    cached_stages = sum(r.get("execution") == "cache_reused" for r in records)
    manifest_reasons = []
    for key in ("reason", "status_reason", "message"):
        val = manifest.get(key)
        if isinstance(val, str) and val.strip():
            manifest_reasons.append(val.strip())
    manifest_errors = [str(item) for item in manifest.get("errors", []) if item]
    non_ok_stages = [f'{r.get("title", r.get("stage_id", ""))} ({label(r.get("status"))})' for r in records if r.get("status") in {"failed", "interrupted"}]

    body = (
        '<header>'
        '<div class="header-eyebrow"><span class="tagline">CGAT · LGZ Baseline Report</span>'
        '<span class="scope-pill">非精修结果</span></div>'
        '<div class="header-title-row"><div><h1>LGZ 流程报告</h1>'
        f'<p>{esc(manifest["workspace_name"])} · Run ID: <code>{esc(manifest["run_id"])}</code></p></div>'
        f'<span class="badge {esc(state)}">{esc(label(state))}</span></div>'
        '<nav>'
        '<a href="#summary"><span class="nav-num">01</span>结果摘要 / Summary</a>'
        '<a href="#results"><span class="nav-num">02</span>染色体组成 / Chromosomes</a>'
        '<a href="#delivery"><span class="nav-num">03</span>交付文件 / Delivery</a>'
        '<a href="#workflow"><span class="nav-num">04</span>分析与审计 / Audit</a>'
        '</nav></header><main>'
    )
    input_facts = input_record.get("facts", {})
    q0_construction = final.get("q0_construction")
    if not q0_construction:
        q0_construction = next((record.get("facts", {}).get("q0_construction") for record in records
                                if record.get("stage_id") in PREPARE_IDS and record.get("status") == "success"), None)
    modern_q0 = (bool(q0_construction) or input_facts.get("q0_mode") == "evidence_guided_multi_source"
                 or final.get("q0_mode") == "evidence_guided_multi_source")
    reason_summary_parts = list(dict.fromkeys([*manifest_reasons, *manifest_errors]))
    topline_reason_html = ""
    if reason_summary_parts:
        warn_cls = "warn is-error" if state == "failed" else "warn"
        topline_reason_html = f'<div class="{warn_cls}"><strong>状态原因 / Reason: </strong>' + "；".join(esc(item) for item in reason_summary_parts) + '</div>'
    elif state != "success":
        stage_hint = f"（异常阶段：{'、'.join(non_ok_stages)}）" if non_ok_stages else ""
        topline_reason_html = f'<p class="warn">本次运行未完成{esc(stage_hint)}，未测量的指标不计入结果。</p>'

    body += (
        '<section id="summary" class="summary-panel">'
        '<div class="summary-heading"><h2>LGZ 基线结果 / Baseline Outcome</h2></div>'
        '<div class="topline-bar">'
        f'<span>完成阶段：<strong>{completed_stages} / {len(records)}</strong></span>'
        f'<span>复用缓存：<strong>{cached_stages}</strong></span>'
        + (f'<span>结束时间：<strong>{esc(manifest.get("ended_at"))}</strong></span>' if manifest.get("ended_at") else '')
        + '</div>'
        + topline_reason_html
        + outcome_summary_html(final)
    )
    if q0_construction and q0_construction.get("summary", {}).get("not_constructed_chromosomes", 0):
        count = q0_construction["summary"]["not_constructed_chromosomes"]
        body += (f'<p class="warn">q0 中有 {esc(display(count))} 个参考 chr 未构建；'
                 '输出序列的结构条件不能代表完整基因组。<a href="#q0-construction">查看 q0 构建范围</a></p>')
    body += '</section><section id="results"><h2>染色体组成与标记</h2>'
    if not final.get("available"):
        body += '<p class="warn">本次运行尚无经过确认的最终路径 / Final Path。</p>'
    else:
        body += final_path_visual_html(final)
    if modern_q0:
        body += '<div class="block" id="q0-construction"><h2>q0 构建与未解决范围</h2>' + q0_summary_html(q0_construction) + '</div>'
    body += '<details class="block secondary-results"><summary>查看 q0 → Final Path 演化和组装统计</summary><h3>q0 → Final Path 序列演化</h3>'
    body += lgz_flow_html(grt, final)
    versions = {}
    if modern_q0:
        candidates = {f"输入 {row['name']}": row.get("stats") for row in input_facts.get("datasets", []) if row["role"] != "reference"}
        body += stats_table("各组装输入（可重叠，不能相加作为 q0 基线）", candidates)
    else:
        primary = next((d for d in input_facts.get("datasets", []) if d["role"] == "primary"), {})
        versions["原始主组装"] = primary.get("stats")
    for record in records:
        if record["stage_id"] in PREPARE_IDS:
            versions.update(record.get("facts", {}).get("sequence_versions", {}))
    versions.update(final.get("sequence_versions", {}))
    body += stats_table("初始构建与 LGZ 处理对比", versions) + notes(final.get("notes", [])) + '</details>'
    body += '<details class="block secondary-results"><summary>查看事件与最终路径审计明细</summary>'
    body += data_table("event_reconciliation", final.get("event_reconciliation", []))
    remaining = [e for e in final.get("events", []) if e.get("status") in {"unresolved", "rejected"}]
    body += '<p class="note">历史未接受事件可能已由后续阶段解决；最终剩余 gap 以最终路径的序列统计为准。</p>'
    body += data_table("历史未接受事件与原因", remaining)
    body += data_table("最终染色体路径", final.get("final_path", {}).get("chromosomes", []))
    body += data_table("各染色体最终统计", (final.get("sequence_versions", {}).get(final.get("final_q_version", "q4")) or {}).get("sequences", []))
    body += '</details></section>'
    body += ('<section id="workflow" class="technical-section"><details class="section-disclosure"><summary>分析流程与任务概览</summary>'
             '<p class="workflow-copy">从原始 FASTA 开始，依次经过参考比对、染色体归属、q0 与供体构建、LGZ 修复和证据固化。</p>'
             + pipeline_map_html(records, input_facts, final))
    body += '<div id="overview">' + key_values({"开始": manifest.get("started_at"), "结束": manifest.get("ended_at"),
              "完成阶段": f'{sum(r.get("status")=="success" for r in records)} / {len(records)}',
              "复用缓存阶段": sum(r.get("execution")=="cache_reused" for r in records)})
    body += f'<details class="audit-box"><summary>查看完整执行清单 · {len(records)} 个阶段</summary><ol class="timeline">'
    for index, record in enumerate(records):
        body += f'<li><span class="badge {esc(record["status"])}">{esc(label(record["status"]))}</span><a href="#stage-{index}">{esc(record["title"])}</a><span class="muted">{esc(label(record.get("execution", "")))}</span></li>'
    body += '</ol></details></div></details></section><section id="inputs" class="technical-section"><details class="section-disclosure"><summary>原始输入与运行参数</summary>'
    body += key_values({"准备状态": label(input_record["status"]) if input_record.get("status") else None,
                        "准备开始": input_record.get("started_at"), "准备结束": input_record.get("ended_at")})
    body += notes(input_record.get("notes", []))
    body += data_table("原始文件来源", input_record.get("sources", []))
    input_versions = {f'{d["name"]} · {label(d["role"])}': d.get("stats") for d in input_facts.get("datasets", [])}
    body += stats_table("输入序列统计", input_versions)
    body += data_table("实际准备参数", [{"参数": k, "值": v} for k, v in input_facts.get("parameters", {}).items()])
    body += '<details class="block"><summary>准备命令参数</summary><pre>' + esc(json.dumps(input_record.get("argv"), ensure_ascii=False, indent=2)) + '</pre></details></details></section>'
    body += ('<section id="process" class="technical-section"><details class="section-disclosure"><summary>逐步输入、处理与输出</summary>'
             '<p class="workflow-copy">展开各阶段可查看统计、事件、命令和原始 JSON。</p>'
             f'<details class="audit-box"><summary>全部 Input → Process → Output · {len(records)} 个执行单元</summary>')
    for index, record in enumerate(records):
        body += stage_html(record, f"stage-{index}")
        for sub in grt:
            if sub.get("parent_unit") == record["stage_id"]:
                body += stage_html(sub, "grt-" + sub["stage_id"])
    body += '</details></details></section><section id="delivery"><h2>交付文件</h2>'
    outputs = [output for record in records if record["stage_id"].startswith("package_")
               for output in record.get("facts", {}).get("outputs", [])]
    body += data_table("交付包 App 数据载荷", outputs)
    body += '<p class="note">为避免报告对所在 ZIP 产生自引用，表中校验值只覆盖嵌入报告前的 App 数据载荷。最终 ZIP 的 SHA-256 会在流程结束时写入终端和 run_all.log。报告随两个交付包提供，也可在服务端工作目录中直接打开；完整报告目录可用 Python 标准库重新生成。报告只内嵌有限行预览和准确总行数，全量审计明细保留在服务器原始文件中，不在 HTML 或 App 报告中反复复制。</p><button id="download" type="button">下载报告展示数据 JSON</button></section><p class="footer">CGAT · 独立离线报告 · 坐标沿用各源记录定义；q/source 区间为 1-based inclusive，PAF 区间为 0-based half-open。</p></main>'
    payload = export_payload({"report_data_kind": "summary_with_table_previews_v1", "preview_row_limit": REPORT_PREVIEW_ROWS,
                              "manifest": manifest, "inputs": input_record, "steps": records, "grt_steps": grt, "final_summary": final})
    embedded = json.dumps({"labels": LABELS, "tables": tables, "payload": payload}, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; connect-src \'none\'; base-uri \'none\'"><title>CGAT Server 报告</title><style>' + CSS + '</style></head><body>' + body + '<noscript>汇总可直接阅读。搜索、分页和 JSON 下载需要浏览器启用 JavaScript。</noscript><script id="report-data" type="application/json">' + embedded + '</script><script>' + JS + '</script></body></html>\n'
    fd, temporary = tempfile.mkstemp(prefix=".report.html.", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
        os.replace(temporary, root / "report.html")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return root / "report.html"



# Compatibility aliases for existing Python consumers.
grt_flow_html = lgz_flow_html

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=Path(__file__).resolve().parent)
    print(render(parser.parse_args().report_dir))
