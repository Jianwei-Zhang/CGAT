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
LABELS = {
    "success": "完成", "failed": "失败", "interrupted": "中断", "pending": "未执行",
    "running": "运行中", "prepared": "输入已准备，等待运行", "preparing": "准备中",
    "computed": "本次执行", "cache_reused": "复用已验证缓存", "not_started": "尚未开始",
    "see_parent_unit": "执行方式见所属阶段", "accepted": "接受", "rejected": "拒绝",
    "unresolved": "未解决", "superseded": "已被替换", "not_finalized": "尚未最终确认",
    "not_enabled": "未启用", "measured": "已测量", "enabled": "已启用",
    "reference": "参考序列", "primary": "主组装", "support": "辅助组装",
    "sequence_count": "序列数", "length_bp": "总长度 / bp", "n_bp": "N 碱基数",
    "gap_count": "Gap 数（连续 N ≥100 bp）", "gap_bp": "Gap 长度 / bp", "n50_bp": "N50 / bp",
    "alignment_count": "比对记录数", "aligned_query_count": "有比对的 contig 数",
    "unaligned_query_count": "无比对的 contig 数", "assignment_rows": "归属记录数",
    "assigned_unique_contigs": "已分配的唯一 contig 数", "unassigned_contigs": "未分配 contig 数",
    "reads_qc": "Reads 质量评估", "event_count": "事件数", "by_status": "事件状态",
    "by_action": "处理动作", "by_reason": "原因分布", "available": "记录可用",
    "alignment_task_count": "染色体比对任务数", "self_alignment": "自比对",
    "archive": "交付文件", "sequence": "序列", "aligned_bp": "比对覆盖 / bp",
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
    "alignments": "比对任务", "telomeres": "端粒注释", "centromeres": "着丝粒注释",
    "used_contigs": "最终使用的 Contig", "evidence": "证据记录", "usage": "供体使用记录",
}
METHODS = {
    "prepare": "记录原始文件身份、数据角色与规范化后的 FASTA 统计。",
    "assign": "依据经过过滤的参考比对及覆盖率阈值分配染色体，记录方向与排列顺序。",
    "grt_prepare": "构建 q0，锁定普通供体与端粒供体；提供 reads 时执行输入质量评估。",
    "step1_round1": "记录外部 contig 模式的第一阶段及其实际序列变化。",
    "step1_filter": "记录过滤阶段；延期处理会保留原因。",
    "step1_round2": "记录第二阶段及通往 q1 的序列变化。",
    "step2": "生成并验证补丁候选，按染色体选择补丁或结构修正分支，生成 q2。",
    "step3": "处理结构问题、重叠与后续优化填补，记录过滤和未解决的问题，生成 q3。",
    "step4_telomere": "检查染色体两端、验证端粒供体并记录处理结果，生成 q4。",
    "finalize_evidence": "整理最终路径使用的 contig 和比对证据，执行结果契约校验。",
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


CSS = """
:root{color-scheme:light;--ink:#172b38;--muted:#536774;--line:#dbe5e9;--accent:#087f8c}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f3f7f8;font:15px/1.65 system-ui,-apple-system,'Segoe UI',sans-serif}
header{background:#113849;color:white;padding:38px max(24px,calc((100vw - 1240px)/2)) 30px}header p{color:#bfdae4;margin:5px 0}
h1{font-size:32px;margin:4px 0 12px;letter-spacing:-.5px}h2{font-size:22px;margin:0 0 16px}h3{font-size:17px;margin:20px 0 10px}
main{max-width:1288px;margin:auto;padding:24px}section,.stage{background:white;border:1px solid var(--line);border-radius:12px;margin-bottom:22px;padding:24px;min-width:0}
nav{display:flex;flex-wrap:wrap;gap:18px;margin:18px 0 0}a{color:var(--accent)}header a{color:#d4f6f5}button{font:inherit;cursor:pointer;background:white;border:1px solid #a9bcc4;border-radius:6px;padding:5px 12px;color:var(--ink)}button:hover{background:#e9f6f6}button:disabled{opacity:.45;cursor:default}
.badge{display:inline-block;background:#e9f0f3;border-radius:20px;padding:2px 11px;font-size:13px;white-space:nowrap}.success,.prepared{color:#126044;background:#e2f5eb}.failed{color:#982830;background:#fbe7e7}.interrupted{background:#fff0d4;color:#805500}.running,.preparing{background:#dff2fb;color:#126184}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:12px 0}.facts div{border-left:3px solid #dcecee;padding-left:12px}.facts dt{color:var(--muted);font-size:13px}.facts dd{margin:2px 0;overflow-wrap:anywhere;font-weight:600}.note,.muted{color:var(--muted);font-size:14px}.note{margin:8px 0}.warn{border-left:4px solid #cd941e;padding:12px;background:#fff8e8}
details>summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}details{margin-top:12px}details.block{border:1px solid var(--line);border-radius:7px;padding:12px}details.block>summary{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.stage>summary{font-size:19px}.stage-body{padding-top:12px}
.scroll{overflow:auto;max-height:560px;border:1px solid var(--line);border-radius:6px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:9px 12px;text-align:left;vertical-align:top}th{background:#edf4f6;position:sticky;top:0;z-index:1;white-space:nowrap}td{max-width:480px;min-width:100px;overflow-wrap:anywhere}tbody tr:hover{background:#f2fafa}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f3f6f7;padding:12px;max-height:420px;overflow:auto}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}.toolbar input{flex:1;min-width:160px;padding:8px;border:1px solid #a9bcc4;border-radius:6px;font:inherit}.timeline{list-style:none;padding:0;margin:0}.timeline li{display:flex;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid #edf1f3;flex-wrap:wrap}.timeline a{flex:1;min-width:220px}.bar{height:6px;background:#dfeeee;border-radius:3px;overflow:hidden;margin-top:5px}.bar i{display:block;height:100%;background:var(--accent)}.metric{font-variant-numeric:tabular-nums}.tagline{font-size:12px;letter-spacing:2px}.footer{color:var(--muted);font-size:12px;margin:20px 0;text-align:center}
@media(max-width:650px){main{padding:12px}section,.stage{padding:16px}h1{font-size:25px}.facts{grid-template-columns:1fr 1fr}.facts dd{font-size:14px}}
@media print{body{background:white}header{background:white;color:#172b38;padding:12px}header p,header a{color:#536774}main{padding:0}button,.toolbar,nav{display:none}section,.stage{break-inside:avoid;border-radius:0}.scroll{max-height:none}details:not([open])>summary:after{content:'（明细见电子版）';font-size:12px}}
"""

JS = r"""
const data=JSON.parse(document.getElementById('report-data').textContent);
const labels=data.labels, enums=new Set(['status','action','reason','outcome','role','process_status','process_reason','final_status','final_reason','reads_qc','self_alignment']), fmt=(v,key)=>v===null||v===undefined||v===''?'未记录 / 未测量':typeof v==='object'?JSON.stringify(v,null,2):(enums.has(key)?labels[String(v)]||String(v):String(v));
const save=(value,name)=>{const a=document.createElement('a');const u=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)};
document.getElementById('download').onclick=()=>save(data.payload,'server-report.json');
for(const box of document.querySelectorAll('[data-table]')){
 let ready=false;
 box.addEventListener('toggle',()=>{if(!box.open||ready)return;ready=true;
 const rows=data.tables[Number(box.dataset.table)], cols=[...new Set(rows.flatMap(r=>Object.keys(r)))];
 const toolbar=document.createElement('div');toolbar.className='toolbar';
 const search=document.createElement('input');search.type='search';search.placeholder='搜索此表的所有记录';search.setAttribute('aria-label',box.querySelector('summary').textContent+' 搜索');
 const prev=document.createElement('button'),next=document.createElement('button'),count=document.createElement('span'),download=document.createElement('button');prev.textContent='上一页';next.textContent='下一页';download.textContent='下载完整 JSON';toolbar.append(search,prev,count,next,download);box.append(toolbar);
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
    records = [load(root, relative) for relative in manifest["steps"]]
    grt = [load(root, p.relative_to(root).as_posix()) for p in sorted((root / "steps").glob("grt-*.json"))]
    stage_order = ["step1_round1", "step1_filter", "step1_round2", "step2", "step3", "step4_telomere"]
    grt.sort(key=lambda row: stage_order.index(row["stage_id"]) if row["stage_id"] in stage_order else len(stage_order))
    for record in [*records, *grt]:
        if record.get("run_id") != manifest["run_id"] or record.get("schema_version") != SCHEMA:
            raise ValueError("mixed invocation or schema in report stage records")
    final = load(root, "final_summary.json", optional=True)
    if final and (final.get("run_id") != manifest["run_id"] or final.get("schema_version") != SCHEMA):
        raise ValueError("mixed invocation or schema in final report summary")
    tables = []

    def data_table(name, rows, available=True):
        if not available:
            return f'<p class="note">{esc(label(name))}：未记录 / 未测量</p>'
        index = len(tables)
        tables.append(rows)
        return f'<details class="block" data-table="{index}"><summary>{esc(label(name))}<span class="badge">{len(rows):,} 条</span></summary></details>'

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

    def stage_html(record, element_id):
        facts = record.get("facts", {})
        runtime = record.get("runtime", {})
        state = record.get("status", "pending")
        body = f'<details class="stage" id="{element_id}"><summary>{esc(record["title"])} <span class="badge {esc(state)}">{esc(label(state))}</span></summary><div class="stage-body">'
        body += f'<p>{esc(METHODS.get(record["stage_id"], ""))}</p>'
        body += key_values({"执行方式": label(record.get("execution", "unknown")),
                            "开始时间": runtime.get("started_at"), "耗时 / s": runtime.get("elapsed_seconds"),
                            "退出码": runtime.get("exit_code")})
        body += key_values(facts.get("summary", {})) + notes(facts.get("notes", []))
        if facts.get("sequence_versions"):
            body += stats_table("阶段前后对比", facts["sequence_versions"])
        for name, value in facts.get("tables", {}).items():
            body += data_table(name, value["rows"], value["available"])
        result = facts.get("result", {})
        for name in ("events", "strategies", "classification_rows", "terminal_rows"):
            if name in result:
                body += data_table("处理事件" if name == "events" else name, result[name])
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
    body = f'<header><div class="tagline">CGAT · SERVER REPORT</div><h1>从输入到最终结果</h1><p>{esc(manifest["workspace_name"])} · {esc(manifest["run_id"])}</p><span class="badge {esc(state)}">{esc(label(state))}</span><nav><a href="#overview">任务概览</a><a href="#inputs">原始输入</a><a href="#process">处理过程</a><a href="#results">最终结果</a><a href="#delivery">交付文件</a></nav></header><main>'
    body += '<section id="overview"><h2>任务概览</h2>' + key_values({"开始": manifest.get("started_at"), "结束": manifest.get("ended_at"),
              "完成阶段": f'{sum(r.get("status")=="success" for r in records)} / {len(records)}',
              "复用缓存阶段": sum(r.get("execution")=="cache_reused" for r in records)})
    body += notes(manifest.get("errors", []))
    if state != "success":
        body += '<p class="warn">任务尚未全部完成。未执行阶段和未测量指标均明确保留，不作为成功结果。</p>'
    body += '<ol class="timeline">'
    for index, record in enumerate(records):
        body += f'<li><span class="badge {esc(record["status"])}">{esc(label(record["status"]))}</span><a href="#stage-{index}">{esc(record["title"])}</a><span class="muted">{esc(label(record.get("execution", "")))}</span></li>'
    body += '</ol></section><section id="inputs"><h2>原始输入与运行参数</h2>'
    input_facts = input_record.get("facts", {})
    body += key_values({"准备状态": label(input_record["status"]) if input_record.get("status") else None, "准备开始": input_record.get("started_at"),
                        "准备结束": input_record.get("ended_at")})
    body += notes(input_record.get("notes", []))
    body += data_table("原始文件来源", input_record.get("sources", []))
    input_versions = {f'{d["name"]} · {label(d["role"])}': d.get("stats") for d in input_facts.get("datasets", [])}
    body += stats_table("输入序列统计", input_versions)
    body += data_table("实际准备参数", [{"参数": k, "值": v} for k, v in input_facts.get("parameters", {}).items()])
    body += '<details class="block"><summary>准备命令参数</summary><pre>' + esc(json.dumps(input_record.get("argv"), ensure_ascii=False, indent=2)) + '</pre></details></section><div id="process"><h2>处理过程</h2>'
    for index, record in enumerate(records):
        body += stage_html(record, f"stage-{index}")
        for sub in grt:
            if sub.get("parent_unit") == record["stage_id"]:
                body += stage_html(sub, "grt-" + sub["stage_id"])
    body += '</div><section id="results"><h2>最终结果与仍待解决的问题</h2>'
    versions = {}
    primary = next((d for d in input_facts.get("datasets", []) if d["role"] == "primary"), {})
    versions["原始主组装"] = primary.get("stats")
    for record in records:
        if record["stage_id"] == "grt_prepare":
            versions.update(record.get("facts", {}).get("sequence_versions", {}))
    versions.update(final.get("sequence_versions", {}))
    body += stats_table("初始构建与 GRT 处理对比", versions) + notes(final.get("notes", []))
    if not final.get("available"):
        body += '<p class="warn">本次运行尚无经过确认的最终 q4 / Final Path。</p>'
    else:
        body += key_values({"最终来源贡献 / bp": final.get("source_contribution_bp"),
                            "显式连接 gap 片段数": final.get("explicit_connector_segments")})
    body += data_table("event_reconciliation", final.get("event_reconciliation", []))
    remaining = [e for e in final.get("events", []) if e.get("status") in {"unresolved", "rejected"}]
    body += '<p class="note">历史未接受事件可能已由后续阶段解决；最终剩余 gap 以 q4 的序列统计为准。</p>'
    body += data_table("历史未接受事件与原因", remaining)
    body += data_table("最终染色体路径", final.get("final_path", {}).get("chromosomes", []))
    body += data_table("各染色体最终统计", (final.get("sequence_versions", {}).get("q4") or {}).get("sequences", []))
    body += '</section><section id="delivery"><h2>交付文件</h2>'
    outputs = [output for record in records if record["stage_id"].startswith("package_")
               for output in record.get("facts", {}).get("outputs", [])]
    body += data_table("交付文件与 SHA-256", outputs)
    body += '<p class="note">文件名和路径用于说明来源。本 HTML 的阅读不依赖这些文件，离线即可打开；完整报告目录可用 Python 标准库重新生成。</p><button id="download" type="button">下载本报告完整 JSON</button></section><p class="footer">CGAT · 独立离线报告 · 坐标沿用各源记录定义；q/source 区间为 1-based inclusive，PAF 区间为 0-based half-open。</p></main>'
    payload = {"manifest": manifest, "inputs": input_record, "steps": records, "grt_steps": grt, "final_summary": final}
    embedded = json.dumps({"labels": LABELS, "tables": tables, "payload": payload}, ensure_ascii=False, allow_nan=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data:; connect-src \'none\'; base-uri \'none\'"><title>CGAT Server 报告</title><style>' + CSS + '</style></head><body>' + body + '<noscript>汇总可直接阅读。搜索、分页和 JSON 下载需要浏览器启用 JavaScript。</noscript><script id="report-data" type="application/json">' + embedded + '</script><script>' + JS + '</script></body></html>\n'
    fd, temporary = tempfile.mkstemp(prefix=".report.html.", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
        os.replace(temporary, root / "report.html")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return root / "report.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=Path(__file__).resolve().parent)
    print(render(parser.parse_args().report_dir))
