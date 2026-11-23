"""Portable refinement reports with static CGAT pages and managed native views.

A report is not a publication receipt. It records the complete LGZ gap denominator
and labels staged, native and accepted results separately. No external JS, reads
FASTA, native genome or workstation-only hyperlink is needed to view the report.
"""
from __future__ import annotations

from collections import defaultdict, Counter
from bisect import bisect_right
import csv
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import quote

try:
    from workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
    from refinement_tools import fingerprint
    import refinement_native_reports as native_reports
    from refinement_degap_units import terminal as degap_child_terminal
except ModuleNotFoundError:
    from .workspace_layout import TOOL_DIRECTORIES, WorkspaceLayout
    from .run_orchestration import sha256_file as digest, atomic_write_json as atomic_json
    from .refinement_tools import fingerprint
    from . import refinement_native_reports as native_reports
    from .refinement_degap_units import terminal as degap_child_terminal

SCHEMA = "cgat.refinement-report"
PAGE_SIZE = 200
MAX_ASSET = 20 * 1024 * 1024
MAX_ASSETS_TOTAL = 200 * 1024 * 1024
TEXT_ENDINGS = (".json", ".log", ".tsv", ".paf", ".txt", ".agp", ".detail", ".gap_fill_detail", "_scaff_infos", ".name_map", "/info_filter2")
CSS = """
:root{
  color-scheme:light;
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC","Noto Sans CJK SC",sans-serif;
  font-size:14px;
  --font-mono:ui-monospace,"Cascadia Code",Consolas,monospace;
  --card-radius:6px;
  --control-radius:5px;
  --surface-app:#f1f5f9;
  --surface-panel:#ffffff;
  --surface-subtle:#f8fafc;
  --surface-muted:#eef2f6;
  --border-subtle:#dbe3ec;
  --border-default:#cbd5e1;
  --border-strong:#94a3b8;
  --text-primary:#1e293b;
  --text-secondary:#334155;
  --text-muted:#64748b;
  --accent:#2563eb;
  --action-primary-bg:#234b76;
  --action-primary-border:#1d3f63;
  --focus-ring:#4f82b5;
  --shadow-xs:0 1px 2px rgba(15,23,42,.04);
  --shadow-sm:0 1px 3px rgba(15,23,42,.06),0 1px 2px rgba(15,23,42,.04);
  --tone-ok-ink:#166534;--tone-ok-bg:#ecfdf5;--tone-ok-line:#86efac;
  --tone-warn-ink:#92400e;--tone-warn-bg:#fffbeb;--tone-warn-line:#f59e0b;
  --tone-err-ink:#991b1b;--tone-err-bg:#fef2f2;--tone-err-line:#fca5a5;
  --tone-info-ink:#1e40af;--tone-info-bg:#eff6ff;--tone-info-line:#93c5fd;
  --tone-purple-ink:#5b21b6;--tone-purple-bg:#f5f3ff;--tone-purple-line:#c4b5fd;
  --tone-neutral-ink:#334155;--tone-neutral-bg:#eef2f6;--tone-neutral-line:#cbd5e1;
}
@media (prefers-color-scheme:dark){
  :root{
    color-scheme:dark;
    --surface-app:#101720;
    --surface-panel:#17212e;
    --surface-subtle:#1d2938;
    --surface-muted:#243244;
    --border-subtle:#344458;
    --border-default:#42546a;
    --border-strong:#748ba5;
    --text-primary:#e5edf7;
    --text-secondary:#c7d5e6;
    --text-muted:#9bacc1;
    --accent:#8abaff;
    --action-primary-bg:#2f5f92;
    --action-primary-border:#648db8;
    --focus-ring:#91bfff;
    --shadow-xs:0 1px 2px #0003;
    --shadow-sm:0 2px 5px #0004;
    --tone-ok-ink:#a2dfb3;--tone-ok-bg:#20382d;--tone-ok-line:#77b38b;
    --tone-warn-ink:#f4d098;--tone-warn-bg:#3a3022;--tone-warn-line:#b79966;
    --tone-err-ink:#ffb4ae;--tone-err-bg:#422b31;--tone-err-line:#c68989;
    --tone-info-ink:#a6ccff;--tone-info-bg:#253d57;--tone-info-line:#7fa4d1;
    --tone-purple-ink:#d3bbff;--tone-purple-bg:#352c49;--tone-purple-line:#ad91d7;
    --tone-neutral-ink:#c7d5e6;--tone-neutral-bg:#243244;--tone-neutral-line:#42546a;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--surface-app);color:var(--text-primary);line-height:1.5;font-size:14px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
a:focus-visible,summary:focus-visible,button:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:3px}
code,pre{font-family:var(--font-mono)}
code{font-size:.9em;overflow-wrap:anywhere;background:var(--surface-muted);padding:.1em .35em;border-radius:4px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--card-radius);padding:.85rem 1rem;margin:.5rem 0;font-size:12.5px;line-height:1.45;max-height:420px;overflow:auto}
h1,h2,h3,h4,p{margin:0}
h1{font-size:1.65rem;line-height:1.25;letter-spacing:-.01em}
h2{font-size:1.2rem;line-height:1.3;margin:0 0 .65rem}
h3{font-size:1.02rem;line-height:1.35;margin:.85rem 0 .45rem}
p{margin:.4rem 0}
small,.muted{color:var(--text-muted);font-size:.88rem}
.num{font-variant-numeric:tabular-nums}
.cgat-header{background:var(--surface-panel);border-bottom:1px solid var(--border-default);border-top:3px solid var(--action-primary-bg);box-shadow:var(--shadow-xs)}
.cgat-header-inner,.cgat-main{max-width:1240px;margin:0 auto;padding:1rem 1.25rem}
.cgat-header-inner{padding-top:1.15rem;padding-bottom:1rem}
.cgat-eyebrow{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.4rem}
.scope-pill{display:inline-flex;align-items:center;padding:.15rem .55rem;border-radius:4px;font-size:.78rem;font-weight:600;letter-spacing:.03em;text-transform:uppercase;background:var(--surface-muted);color:var(--text-secondary);border:1px solid var(--border-default)}
.cgat-title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;flex-wrap:wrap}
.cgat-subtitle{margin-top:.35rem;color:var(--text-secondary);font-size:.92rem}
.cgat-nav{display:flex;flex-wrap:wrap;gap:.45rem .65rem;margin-top:.85rem;padding-top:.75rem;border-top:1px solid var(--border-subtle);align-items:center}
.cgat-nav a{display:inline-flex;align-items:center;gap:.35rem;padding:.28rem .6rem;border-radius:var(--control-radius);border:1px solid var(--border-default);background:var(--surface-subtle);color:var(--text-primary);font-size:.88rem;font-weight:500}
.cgat-nav a:hover{border-color:var(--border-strong);background:var(--surface-muted);text-decoration:none}
.step-nav{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.85rem;padding-top:.75rem;border-top:1px solid var(--border-subtle)}
.step-link{display:inline-flex;align-items:center;gap:.45rem;padding:.35rem .7rem;border-radius:var(--control-radius);border:1px solid var(--border-default);background:var(--surface-subtle);color:var(--text-primary);font-size:.88rem;font-weight:500}
.step-link:hover{border-color:var(--border-strong);background:var(--surface-muted);text-decoration:none}
.step-num{display:inline-flex;align-items:center;justify-content:center;min-width:1.45rem;height:1.45rem;padding:0 .3rem;border-radius:4px;background:var(--action-primary-bg);color:#fff;font-family:var(--font-mono);font-size:.76rem;font-weight:700}
.cgat-main{padding-top:1.25rem;padding-bottom:2.25rem;display:flex;flex-direction:column;gap:1rem}
.panel{background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--card-radius);padding:1rem 1.15rem;box-shadow:var(--shadow-xs)}
.panel.is-baseline{border-left:4px solid var(--action-primary-bg);background:var(--surface-panel)}
.panel-head{display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;margin-bottom:.65rem}
.panel-head h2{margin:0}
.badge{display:inline-flex;align-items:center;gap:.3rem;padding:.16rem .55rem;border-radius:999px;font-size:.8rem;font-weight:600;line-height:1.35;border:1px solid transparent;white-space:nowrap}
.tone-ok{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border-color:var(--tone-ok-line)}
.tone-warn{color:var(--tone-warn-ink);background:var(--tone-warn-bg);border-color:var(--tone-warn-line)}
.tone-err{color:var(--tone-err-ink);background:var(--tone-err-bg);border-color:var(--tone-err-line)}
.tone-info{color:var(--tone-info-ink);background:var(--tone-info-bg);border-color:var(--tone-info-line)}
.tone-purple{color:var(--tone-purple-ink);background:var(--tone-purple-bg);border-color:var(--tone-purple-line)}
.tone-neutral{color:var(--tone-neutral-ink);background:var(--tone-neutral-bg);border-color:var(--tone-neutral-line)}
.callout,.note{border-left:3px solid var(--tone-warn-line);background:var(--tone-warn-bg);color:var(--text-primary);padding:.7rem .9rem;border-radius:0 var(--card-radius) var(--card-radius) 0;margin:.5rem 0;font-size:.93rem}
.callout.tone-info{border-left-color:var(--tone-info-line);background:var(--tone-info-bg)}
.callout.tone-ok{border-left-color:var(--tone-ok-line);background:var(--tone-ok-bg)}
.callout.tone-err{border-left-color:var(--tone-err-line);background:var(--tone-err-bg)}
.callout.tone-neutral{border-left-color:var(--border-strong);background:var(--surface-subtle)}
.callout-title{font-weight:600;margin-bottom:.2rem}
.status-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem}
.status-box{border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-subtle);padding:.8rem .9rem;display:flex;flex-direction:column;gap:.4rem}
.status-box-label{font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.03em;color:var(--text-muted)}
.metrics-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.6rem;margin:.5rem 0}
.metric-cell{border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-subtle);padding:.65rem .75rem;display:flex;flex-direction:column;gap:.15rem}
.metric-label{font-size:.8rem;color:var(--text-muted)}
.metric-value{font-size:1.3rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1.25}
.count-chips{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center}
.count-chip{display:inline-flex;align-items:center;gap:.3rem;padding:.15rem .48rem;border-radius:4px;font-size:.82rem;border:1px solid var(--border-subtle);background:var(--surface-subtle);font-variant-numeric:tabular-nums;white-space:nowrap}
.count-chip b{font-weight:700}
.count-chip.is-closed{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.count-chip.is-partial{border-color:var(--tone-info-line);background:var(--tone-info-bg);color:var(--tone-info-ink)}
.count-chip.is-unfilled{border-color:var(--border-default);background:var(--surface-subtle);color:var(--text-secondary)}
.count-chip.is-rejected{border-color:var(--tone-err-line);background:var(--tone-err-bg);color:var(--tone-err-ink)}
.kv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.65rem .9rem;margin:.5rem 0}
.kv-item{border-left:2px solid var(--border-default);padding-left:.65rem;min-width:0}
.kv-item dt{font-size:.8rem;color:var(--text-muted)}
.kv-item dd{margin:.1rem 0 0;font-weight:600;overflow-wrap:anywhere}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-panel);margin:.6rem 0}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border-bottom:1px solid var(--border-subtle);padding:.55rem .7rem;text-align:left;vertical-align:top}
th{background:var(--surface-subtle);color:var(--text-secondary);font-weight:600;font-size:.84rem;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--surface-subtle)}
td{overflow-wrap:anywhere}
details.fold{border:1px solid var(--border-subtle);border-radius:var(--card-radius);background:var(--surface-panel);margin:.55rem 0}
details.fold>summary{cursor:pointer;padding:.55rem .8rem;font-weight:600;font-size:.9rem;color:var(--text-secondary);list-style-position:inside}
details.fold[open]>summary{border-bottom:1px solid var(--border-subtle);background:var(--surface-subtle)}
.fold-body{padding:.7rem .85rem}
.link-row{display:flex;flex-wrap:wrap;gap:.45rem .65rem;align-items:center;margin:.45rem 0}
.link-pill{display:inline-flex;align-items:center;padding:.24rem .6rem;border-radius:var(--control-radius);border:1px solid var(--border-default);background:var(--surface-subtle);color:var(--accent);font-size:.86rem;font-weight:500}
.link-pill:hover{border-color:var(--border-strong);background:var(--surface-muted);text-decoration:none}
.gap-card,.job-card{background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--card-radius);padding:.95rem 1.1rem;box-shadow:var(--shadow-xs)}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:.6rem;flex-wrap:wrap;padding-bottom:.55rem;margin-bottom:.65rem;border-bottom:1px solid var(--border-subtle)}
.card-head h2{margin:0;font-size:1.08rem;font-family:var(--font-mono)}
.reason-list{margin:.35rem 0;padding-left:1.2rem}
.reason-list li{margin:.2rem 0;overflow-wrap:anywhere}
.error-box{border:1px solid var(--tone-err-line);background:var(--tone-err-bg);color:var(--tone-err-ink);border-radius:var(--card-radius);padding:.75rem .9rem;font-family:var(--font-mono);font-size:.86rem;white-space:pre-wrap;overflow-wrap:anywhere;margin:.45rem 0}
.pager{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center;margin:.5rem 0}
.pager a{padding:.22rem .55rem;border:1px solid var(--border-default);border-radius:4px;background:var(--surface-subtle);font-size:.85rem}
.pager a:hover{background:var(--surface-muted);text-decoration:none}
.page-footer{color:var(--text-muted);font-size:.82rem;padding-top:.5rem;border-top:1px solid var(--border-subtle)}
@media (max-width:860px){
  .status-grid{grid-template-columns:1fr}
  .cgat-header-inner,.cgat-main{padding-left:.85rem;padding-right:.85rem}
}
@media print{
  body{background:#fff;color:#000}
  .cgat-nav,.step-nav,.pager{display:none}
  .panel,.gap-card,.job-card{box-shadow:none;break-inside:avoid}
}
"""

REPORT_CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

STATUS_VOCAB = {
    "published": ("Published / 已发布", "ok"),
    "staged": ("Staged (not published) / 已暂存（未发布）", "warn"),
    "completed": ("Completed / 已完成", "ok"),
    "complete": ("Completed / 已完成", "ok"),
    "completed_without_native_fill": ("Completed (gap not filled) / 已完成（未补上）", "neutral"),
    "exception": ("Execution error / 执行异常", "err"),
    "not_started": ("Not started / 未开始", "neutral"),
    "publication_unverified": ("Publication not verified / 发布未验证", "warn"),
    "completed_no_changes": ("Completed (0 accepted changes) / 已完成（无接纳修改）", "neutral"),
    "unchanged": ("Unchanged / 无变更", "neutral"),
    "success": ("Success / 成功", "ok"),
    "running": ("Running / 运行中", "info"),
    "pending": ("Pending / 等待中", "neutral"),
    "failed": ("Failed / 失败", "err"),
    "invalidated": ("Invalidated / 已失效", "err"),
    "partial_failure": ("Partial failure / 部分失败", "warn"),
    "report_failed": ("Report failed / 报告生成失败", "err"),
    "interrupted": ("Interrupted / 已中断", "warn"),
    "skipped": ("Skipped / 已跳过", "neutral"),
    "not_recorded": ("Not recorded / 未记录", "neutral"),
    "closed": ("Closed / 已闭合", "ok"),
    "partial": ("Partial / 部分填补", "info"),
    "unfilled": ("Unfilled / 未填补", "neutral"),
    "rejected": ("Rejected / 已拒绝", "err"),
    "embedded": ("Embedded / 已嵌入", "ok"),
    "server_only_size_limit": ("Server-only (size limit) / 仅服务器（超体积限制）", "warn"),
    "server_only_native_script": ("Server-only (native script) / 仅服务器（原生脚本）", "neutral"),
    "server_only_sequence_or_binary": ("Server-only (sequence/binary) / 仅服务器（序列/二进制）", "neutral"),
    "available": ("Available / 可用", "ok"),
    "not_available": ("Not available / 不可用", "neutral"),
}


PHASE_LABELS = {
    "native": "Native execution / 原生执行",
    "admission": "CGAT admission / CGAT 接纳",
    "source_evidence": "Source evidence / 来源证据",
    "report": "Report generation / 生成报告",
    "app_delivery": "App packaging / App 打包",
    "publication": "Publication / 发布",
}


class ReportError(ValueError):
    pass


def safe_file(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or Path(relative).is_absolute() or any(p in {".", ".."} for p in relative.split("/")):
        raise ReportError("report artifact is not a safe relative file")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(p.is_symlink() for p in (path, *path.parents) if p != root and root in p.parents):
        raise ReportError("report artifact traverses a symlink or leaves its root")
    if not path.is_file():
        raise ReportError("report artifact is missing: " + relative)
    return path


def stat_key(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def read_bound(path, expected, *, limit=None):
    before = stat_key(path)
    if limit is not None and path.stat().st_size > limit:
        raise ReportError("report JSON exceeds supported metadata bound")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected or stat_key(path) != before:
        raise ReportError("report input changed: " + str(path))
    return data


def esc(value):
    return escape(str(value), quote=True)


def json_text(value):
    return escape(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def fmt_int(value):
    if value is None:
        return "Not recorded / 未记录"
    if isinstance(value, bool):
        return "Yes / 是" if value else "No / 否"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def fmt_bp(value):
    if value is None:
        return "Not recorded / 未记录"
    if not isinstance(value, (int, float)):
        return str(value)
    n = int(value)
    if abs(n) >= 1_000_000_000:
        return f"{n:,} bp ({n / 1_000_000_000:.2f} Gb)"
    if abs(n) >= 1_000_000:
        return f"{n:,} bp ({n / 1_000_000:.2f} Mb)"
    if abs(n) >= 10_000:
        return f"{n:,} bp ({n / 1_000:.1f} kb)"
    return f"{n:,} bp"


def fmt_bytes(value):
    if not isinstance(value, (int, float)):
        return "Not recorded / 未记录"
    n = int(value)
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n:,} B"


def status_meta(status):
    key = str(status) if status is not None else "not_recorded"
    if key in STATUS_VOCAB:
        return STATUS_VOCAB[key]
    return (key, "neutral")


def badge_html(text, tone="neutral"):
    return f'<span class="badge tone-{esc(tone)}">{esc(text)}</span>'


def status_badge(status, label=None):
    text, tone = status_meta(status)
    return badge_html(label if label is not None else text, tone)


def callout(body_html, tone="info", title=None):
    heading = f'<div class="callout-title">{esc(title)}</div>' if title else ""
    return f'<div class="callout tone-{esc(tone)}">{heading}{body_html}</div>'


def disclosure(summary_html, body_html, *, open_by_default=False, cls="fold"):
    open_attr = " open" if open_by_default else ""
    return f'<details class="{esc(cls)}"{open_attr}><summary>{summary_html}</summary><div class="fold-body">{body_html}</div></details>'


def kv_grid(items):
    parts = []
    for key, value_html in items:
        parts.append(f'<div class="kv-item"><dt>{esc(key)}</dt><dd>{value_html}</dd></div>')
    return '<dl class="kv-grid">' + "".join(parts) + '</dl>'


def format_counts_html(counts, *, status=None, invalidated=False):
    if invalidated:
        return '<span class="muted">Unavailable (batch invalidated) / 无统计（批次已失效）</span>'
    if not isinstance(counts, dict):
        if status in {"failed", "pending", "running", "invalidated", "report_failed"}:
            return f'<span class="muted">Not available ({esc(status)}) / 无可用统计</span>'
        return '<span class="muted">Not recorded / 未记录</span>'
    labels = (
        ("closed", "Closed / 已闭合", "is-closed"),
        ("partial", "Partial / 部分填补", "is-partial"),
        ("unfilled", "Unfilled / 未填补", "is-unfilled"),
        ("rejected", "Rejected / 已拒绝", "is-rejected"),
    )
    chips = []
    for key, label, css_cls in labels:
        if key in counts and counts[key] is not None:
            chips.append(f'<span class="count-chip {css_cls}">{esc(label)}: <b>{esc(fmt_int(counts[key]))}</b></span>')
    if not chips:
        return '<span class="muted">Not recorded / 未记录</span>'
    return '<div class="count-chips">' + "".join(chips) + '</div>'


def extract_recorded_reasons(obj):
    if not isinstance(obj, dict):
        return []
    found = []
    for key in ("reason", "status_message", "message", "error", "detail", "note"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            found.append((key, val.strip()))
    reasons = obj.get("reasons")
    if isinstance(reasons, list):
        for item in reasons:
            if isinstance(item, str) and item.strip():
                found.append(("reason", item.strip()))
            elif isinstance(item, dict):
                found.append(("reason", json.dumps(item, ensure_ascii=False, sort_keys=True)))
    return found


def link(relative, label, *, cls=None):
    attr = f' class="{esc(cls)}"' if cls else ""
    return f'<a{attr} href="' + quote(relative, safe="/#-_.") + '">' + esc(label) + '</a>'


def page(title, body, *, scope=None, subtitle=None, nav=None, badge=None):
    eyebrow = f'<div class="cgat-eyebrow"><span class="scope-pill">{esc(scope)}</span></div>' if scope else ""
    badge_part = badge or ""
    sub_part = f'<p class="cgat-subtitle">{subtitle}</p>' if subtitle else ""
    nav_part = f'<nav class="cgat-nav" aria-label="Report navigation">{nav}</nav>' if nav else ""
    header = (
        '<header class="cgat-header"><div class="cgat-header-inner">'
        + eyebrow
        + '<div class="cgat-title-row"><h1>' + esc(title) + '</h1>' + badge_part + '</div>'
        + sub_part + nav_part
        + '</div></header>'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + esc(REPORT_CSP) + '">'
        '<title>' + esc(title) + '</title><style>' + CSS + '</style></head>'
        '<body>' + header + '<main class="cgat-main">' + body + '</main></body></html>\n'
    )


def table(headers, rows, *, empty=None):
    thead = '<thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in headers) + '</tr></thead>'
    if rows:
        tbody = '<tbody>' + ''.join('<tr>' + ''.join('<td>' + str(cell) + '</td>' for cell in row) + '</tr>' for row in rows) + '</tbody>'
    elif empty is not None:
        tbody = f'<tbody><tr><td colspan="{max(1, len(headers))}" class="muted">{esc(empty)}</td></tr></tbody>'
    else:
        tbody = '<tbody></tbody>'
    return '<div class="table-wrap"><table>' + thead + tbody + '</table></div>'


def gap_anchor(gap_id):
    return "gap-" + hashlib.sha256(gap_id.encode()).hexdigest()[:24]


def native_diagnostics(root, tool, run_id, execution):
    """Only known native diagnostic entrypoints; never recursive reads copying."""
    code = TOOL_DIRECTORIES[tool]
    base = Path("04_refinement") / code
    origin = execution.get("native_origin")
    native_run = origin["run_id"] if origin else run_id
    native = base / "03_native" / native_run
    if origin and (not re.fullmatch(r"[0-9a-f]{32}", native_run) or origin.get("native_root") != native.as_posix()
                   or origin.get("receipt") != (base / "02_jobs" / native_run / "native_complete.json").as_posix()):
        raise ReportError("native origin does not identify this tool's owned completion")
    selected = dict(execution.get("artifacts", {}))
    if origin:
        receipt = safe_file(root, origin["receipt"])
        value = json.loads(read_bound(receipt, origin["receipt_sha256"], limit=128 * 1024 * 1024))
        checksum = value.pop("payload_sha256")
        if (checksum != fingerprint(value) or value.get("schema") != "cgat.native-refinement-completion"
                or value.get("schema_version") != 1 or value.get("status") != "completed"
                or value.get("run_id") != native_run or value.get("tool") != tool):
            raise ReportError("native origin completion receipt is invalid")
        for relative, sha in value["result"]["artifacts"].items():
            if relative in selected and selected[relative] != sha:
                raise ReportError("native origin artifact binding changed")
            selected[relative] = sha
        selected[origin["receipt"]] = origin["receipt_sha256"]
    def select(relative):
        file = safe_file(root, relative)
        sha = digest(file)
        if relative in selected and selected[relative] != sha:
            raise ReportError("native evidence changed before report generation: " + relative)
        selected[relative] = sha
        return file, sha
    log = (base / "02_jobs" / native_run / "native.log").as_posix()
    if (root / log).is_file():
        selected.setdefault(log, digest(safe_file(root, log)))
    if tool in {"quartet", "degap", "tgsgapcloser", "lrgapcloser"} and not origin:
        # Failed/interrupted attempts may contain completed units even though
        # no whole-native completion exists. Only named owned diagnostics.
        unit_base = base / "02_jobs" / native_run
        for name in ("native_launch.json", "native_substeps.json"):
            relative = (unit_base / name).as_posix()
            if (root / relative).exists():
                select(relative)
        for receipt in sorted((root / unit_base / "native_units").glob("*/unit_complete.json")):
            if not re.fullmatch(r"[0-9a-f]{64}", receipt.parent.name):
                continue
            for name in ("unit_complete.json", "producer.json", "output.paf", "stdout.paf", "stdout.fasta", "stderr.log", "gapclosed.fasta", "info_filter2"):
                file = receipt.parent / name
                if file.exists() or file.is_symlink():
                    select(file.relative_to(root).as_posix())
            if tool == "degap":
                for file in sorted((receipt.parent / "outputs").glob("*")):
                    if file.name in {"process.log", "run.stdout.log", "run.stderr.log"} or file.name.endswith(".final.fa"):
                        select(file.relative_to(root).as_posix())
    jobs, native_gaps = [], []
    if tool == "degap":
        gap_report = (native / "03.gap_filling/gap_filling_results.json").as_posix()
        if (root / gap_report).exists():
            select(gap_report)
            native_gaps = json.loads(read_bound(safe_file(root, gap_report), selected[gap_report], limit=128 * 1024 * 1024)).get("gaps", [])
        config = (native / "03.gap_filling/job_manager_config.json").as_posix()
        if (root / config).exists():
            file, sha = select(config)
            payload = json.loads(read_bound(file, sha, limit=MAX_ASSET))
            selected[config] = sha
            for item in payload.get("jobs", []):
                if not item.get("job_dir"):
                    jobs.append({"job_name": item.get("job_name"), "chromosome": item.get("chromosome"),
                                 "native_gap_id": item.get("gap_id"), "direction": item.get("direction"),
                                 "artifacts": [], "diagnostics_availability": "not_recorded"})
                    continue
                job_dir = Path(item["job_dir"])
                if not job_dir.is_absolute():
                    job_dir = root / native / job_dir
                if not job_dir.resolve().is_relative_to((root / native).resolve()):
                    raise ReportError("native job diagnostics leave their attempt")
                files = []
                visual_html = None
                family = item.get("direction") == "bidirectional"
                fileset = ("family-result.json", "family-report.html", "junction-evidence.json", "connection-diagnostics.json",
                           "process.summary", "process.agp", "families.json") if family else ("visualization_output/gapfiller_report.html",)
                for name in ("run.stdout.log", "run.stderr.log", "process.log", *fileset):
                    file = job_dir / name
                    if file.exists() or file.is_symlink():
                        relative = file.relative_to(root).as_posix()
                        select(relative)
                        files.append(relative)
                        if name.endswith(".html"):
                            visual_html = relative
                jobs.append({"job_name": item.get("job_name"), "chromosome": item.get("chromosome"),
                             "native_gap_id": item.get("gap_id"), "direction": item.get("direction"),
                             "artifacts": files, "visualization_html": visual_html})
        visual_dir = WorkspaceLayout(root, 1).path((native / "05.visualization").as_posix())
        if visual_dir.is_symlink():
            raise ReportError("native visualization directory cannot be an alias")
        present = {path.name for path in visual_dir.iterdir()} if visual_dir.is_dir() else set()
        for gap in native_gaps:
            direction = native_reports.reported_direction(gap)
            try:
                name = native_reports.detail_name(gap.get("chromosome"), gap.get("gap_id"), direction)
            except native_reports.UnsupportedView:
                continue  # Raw evidence is retained; unsupported names are never rewritten.
            relative = (native / "05.visualization" / name).as_posix()
            if name in present:
                select(relative)
        for name in ("autogapfiller_summary.json", "05.visualization/gap_filling_report.html", "05.visualization/Global.report.html"):
            relative = (native / name).as_posix()
            if (root / relative).exists():
                select(relative)
    if tool == "degap":
        summary_path = (native / "autogapfiller_summary.json").as_posix()
        if summary_path in selected:
            summary = json.loads(read_bound(safe_file(root, summary_path), selected[summary_path], limit=128 * 1024 * 1024))
            results = summary.get("steps", {}).get("step3", {}).get("result", {})
            executions = {row["job_name"]: row for field in ("completed_jobs", "failed_jobs", "skipped_jobs") for row in results.get(field, [])}
            for job in jobs:
                job["execution_result"] = executions.get(job["job_name"], {"status": "not_recorded"})
    return selected, jobs, native_gaps


def embedded_size(rows):
    # Identical source copies keep their logical/provenance rows but share one
    # inert content-addressed attachment and one byte-budget charge.
    return sum({row["report_path"]: row["size_bytes"] for row in rows if "report_path" in row}.values())


def asset_plan(root, artifacts):
    rows, total, copied = [], 0, set()
    visual = any(name.endswith(("/05.visualization/Global.report.html", "/visualization_output/gapfiller_report.html")) for name in artifacts)
    raw_budget = MAX_ASSETS_TOTAL // 2 if visual else MAX_ASSETS_TOTAL
    def priority(item):
        name = item[0]
        rank = 0 if name.endswith("/05.visualization/Global.report.html") else 1 if name.endswith(".html") else 2
        return rank, name
    for relative, expected in sorted(artifacts.items(), key=priority):
        path = safe_file(root, relative)
        size = path.stat().st_size
        # Originals are always inert. Reserve part of the shared quota for the
        # separate closed native view, instead of spending it all on raw logs.
        text = relative.endswith(TEXT_ENDINGS) or relative.endswith(".html")
        include = text and size <= MAX_ASSET and (expected in copied or total + size <= raw_budget)
        row = {"workspace_path": relative, "sha256": expected, "size_bytes": size,
               "availability": "embedded" if include else "server_only_size_limit" if text else
                               "server_only_native_script" if relative.endswith(".sh") or "/native_commands/" in relative else "server_only_sequence_or_binary"}
        if include:
            if expected not in copied:
                total += size
                copied.add(expected)
            row["report_path"] = "assets/" + quote(expected, safe="") + ".txt"
            row["view"] = "original_html_source" if relative.endswith(".html") else "native_text"
        rows.append(row)
    return rows


def native_view_plan(root, tool, run_id, execution, jobs, native_gaps, assets, *, failed=False):
    origin = execution.get("native_origin")
    native_run = origin["run_id"] if origin else run_id
    native = f"04_refinement/{TOOL_DIRECTORIES[tool]}/03_native/{native_run}"
    return native_reports.prepare(tool, native, jobs, native_gaps, assets,
        lambda name, sha: read_bound(safe_file(root, name), sha, limit=MAX_ASSET),
        remaining_budget=MAX_ASSETS_TOTAL - embedded_size(assets),
        page_size=PAGE_SIZE, sealed=set(execution.get("artifacts", {})),
        diagnostics_page="report.html" if failed else "native.html")


def summarize(provenance, final, remaining, jobs, native_gaps):
    if final.get("baseline") != provenance.get("baseline") or final.get("recipe_sha256") != provenance["execution"]["recipe_sha256"]:
        raise ReportError("report Final Path/provenance binding disagrees")
    outcomes = provenance["gap_outcomes"]
    original = {row["gap_id"]: row for row in final["original_gaps"]}
    if len(original) != len(final["original_gaps"]) or len(outcomes) != len(original) or {g["gap_id"] for g in outcomes} != set(original):
        raise ReportError("report omitted or duplicated an original LGZ gap")
    counts = {name: sum(row["status"] == name for row in outcomes) for name in ("closed", "partial", "unfilled", "rejected")}
    if (counts != provenance["counts"] or sum(counts.values()) != len(outcomes)
            or provenance.get("original_gap_count") != len(outcomes)
            or provenance.get("accepted_edit_count") != len(final["edits"])):
        raise ReportError("report counts disagree with the complete original-gap denominator")
    for row in outcomes:
        if any(row[key] != original[row["gap_id"]][key] for key in ("chromosome", "start", "end")):
            raise ReportError("report original gap coordinates changed")
    gap_lookup = defaultdict(list)
    for gap in original.values():
        gap_lookup[gap["chromosome"]].append(gap)
    for rows in gap_lookup.values():
        rows.sort(key=lambda row: row["start"])
    ends = {name: [row["end"] for row in rows] for name, rows in gap_lookup.items()}
    native_by_original = defaultdict(list)
    native_to_original = {}
    for row in native_gaps:
        name, start, end = row.get("chromosome"), row.get("gap_start"), row.get("gap_end")
        if name not in gap_lookup or type(start) is not int or type(end) is not int or start < 1 or end < start:
            continue
        # Fixed DEGAP diagnostics are 1-based inclusive, unlike original LGZ gaps.
        start -= 1
        matching = []
        for index in range(bisect_right(ends[name], start), len(gap_lookup[name])):
            gap = gap_lookup[name][index]
            if gap["start"] >= end:
                break
            matching.append(gap["gap_id"])
            native_by_original[gap["gap_id"]].append(row)
        native_to_original[(name, str(row.get("gap_id")))] = matching
    for job in jobs:
        job["original_gap_ids"] = native_to_original.get((job["chromosome"], str(job["native_gap_id"])), [])
    n_bases = defaultdict(int)
    for row in remaining:
        n_bases[row["chromosome"]] += int(row["end"]) - int(row["start"])
    comparison = []
    native = provenance["execution"].get("native_assembly", {})
    for row in final["chromosomes"]:
        observed = native.get(row["chr"])
        comparison.append({"chromosome": row["chr"], "accepted_length": row["length"],
                           "accepted_n_bases": n_bases[row["chr"]], "accepted_sha256": row["sha256"],
                           "native": observed, "native_equals_accepted": observed["sha256"] == row["sha256"] if observed else None})
    return {"schema": SCHEMA, "schema_version": 1, "tool": provenance["tool"], "run_id": provenance["run_id"],
            "publication_state": "not_asserted_by_report", "outcome": provenance["status"],
            "baseline": final["baseline"], "original_gap_count": len(outcomes), "counts": counts,
            "accepted_edit_count": provenance["accepted_edit_count"], "remaining_gap_count": len(remaining),
            "retained_flank_count": len(retained_flanks(final["edits"]) + [
                row for candidate in provenance["rejected_candidates"]
                for row in candidate.get("flank_decisions", []) if row.get("decision") == "retained_lgz"]),
            "chromosomes": comparison, "execution": provenance["execution"], "native_jobs": jobs, "native_gaps_by_original": dict(native_by_original),
            "coordinate_system": "0-based half-open placement; 1-based inclusive sources",
            "biological_accuracy_validated": False, "automatic_best_tool": None}


def retained_flanks(edits):
    return [row for edit in edits for row in edit.get("evidence", {}).get("flank_decisions", [])
            if row.get("decision") == "retained_lgz"]


def render_retained_flanks(rows):
    return (
        '<h3>Original flanks retained / 保留 LGZ 原侧翼</h3>'
        '<p>Gap admission is separate. The native flank change lacks independent support. '
        '/ 缺口补丁单独判定；原生侧翼变化缺乏独立支持，未写入终版。</p>'
        + table(["Flank / 侧翼", "LGZ interval / LGZ 区间", "Native interval / 原生区间", "Native length difference / 原生长度差"], [
            (esc({"left": "Left / 左", "right": "Right / 右"}.get(row["side"], row["side"])),
             esc(str(row["baseline_interval"])), esc(str(row["native_interval"])),
             esc(f'{row["native_length_delta_bp"]:+,} bp')) for row in rows
        ])
    )


def _summarize_reasons_html(rows, *, empty_text="None recorded / 无记录"):
    if not rows:
        return f'<p class="muted">{esc(empty_text)}</p>'
    items = []
    for row in rows:
        reasons = extract_recorded_reasons(row)
        parts = []
        for ident in ("edit_id", "candidate_id", "gap_id"):
            if row.get(ident) is not None:
                parts.append(f'<code>{esc(row[ident])}</code>')
        if row.get("chromosome") is not None and row.get("start") is not None and row.get("end") is not None:
            parts.append(f'<span class="num">{esc(row["chromosome"])}:{esc(fmt_int(row["start"]))}–{esc(fmt_int(row["end"]))}</span>')
        if row.get("status") is not None:
            parts.append(status_badge(row["status"]))
        if reasons:
            descriptions = {
                "gap_and_flank_cannot_be_separated": "Gap and original sequence could not be separated reliably / 无法可靠区分缺口补丁和已有组装序列",
                "projected_gap_unchanged": "Gap unchanged after retaining original flanks / 保留原侧翼后缺口未变化",
            }
            reason_str = " · ".join(f'{esc(k)}: {esc(descriptions.get(v, v) if isinstance(v, str) else v)}' for k, v in reasons)
            parts.append(reason_str)
        elif not parts:
            parts.append('<span class="muted">Recorded entry (see raw JSON) / 已记录条目（见原始 JSON）</span>')
        items.append("<li>" + " — ".join(parts) + "</li>")
    return '<ul class="reason-list">' + "".join(items) + '</ul>'


def _job_status_summary(job):
    result = job.get("execution_result")
    if not isinstance(result, dict):
        return badge_html("No execution row recorded / 未记录执行条目"), ""
    status = result.get("status") or "not_recorded"
    if status == "failed" and degap_child_terminal(result):
        status = "completed_without_native_fill"
    details = [value for _, value in extract_recorded_reasons(result)]
    for keys, label in ((("exit_code", "return_code", "returncode"), "Exit / 退出码"),
                        (("elapsed_time", "elapsed_seconds", "elapsed", "duration"), "Time / 耗时 (s)")):
        value = next((result[key] for key in keys if result.get(key) is not None), None)
        if value is not None:
            details.append(f"{label}: {value}")
    return status_badge(status), " · ".join(details)


def render_site(directory, summary, provenance, final, assets):
    tool = summary["tool"]
    run_id = summary["run_id"]
    execution = summary["execution"]
    counts = summary["counts"]
    accepted_edits = summary["accepted_edit_count"]
    orig_gaps = summary["original_gap_count"]
    remaining_gaps = summary["remaining_gap_count"]
    outcome = summary["outcome"]
    no_accepted_changes = (accepted_edits == 0 and counts.get("closed", 0) == 0 and counts.get("partial", 0) == 0)

    # 1. Native execution state (distinct from CGAT acceptance & publication)
    native_reused = bool(execution.get("native_reused"))
    native_executed = execution.get("native_executed")
    native_origin = execution.get("native_origin")
    native_status = execution.get("native_status")
    if native_reused:
        origin_run = native_origin.get("run_id") if isinstance(native_origin, dict) else None
        native_badge = badge_html("Reused native evidence / 复用原生证据", "warn")
        native_desc = f'Origin run / 原始运行: <code>{esc(origin_run)}</code>' if origin_run else ""
    elif native_executed is True:
        native_badge = badge_html("Executed this attempt / 本次原生执行", "info")
        native_desc = ""
    elif native_executed is False:
        native_badge = badge_html("Native not executed / 未执行原生工具")
        native_desc = ""
    else:
        native_badge = status_badge("not_recorded")
        native_desc = ""
    if native_status is not None:
        native_desc += ("<br>" if native_desc else "") + status_badge(native_status)

    # 2. CGAT acceptance state
    if no_accepted_changes:
        accept_badge = status_badge("completed_no_changes")
        reason = {
            "native_no_candidates": "No native candidates / 原生工具未产生候选",
            "native_no_eligible_gaps": "No eligible gaps / 无符合条件的缺口",
            "native_no_eligible_flanks": "No eligible flanks / 无符合条件的侧翼",
            "native_no_remaining_gaps": "No gaps remained after LGZ / LGZ 后无剩余缺口",
        }.get(outcome)
        accept_desc = (esc(reason) + " · " if reason else "") + "LGZ sequence retained / 保留 LGZ 序列。"
    else:
        accept_badge = status_badge(outcome)
        accept_desc = "Details below / 见下方缺口结果。"

    pub_badge = badge_html("Not asserted here / 本页不确认发布")
    pub_desc = "This page records the attempt. Check current delivery in the workflow overview. / 本页记录本次尝试；当前交付以流程总览为准。"

    nav_html = (
        '<a href="#status-separation">Status / 状态分层</a>'
        '<a href="#counts">Outcomes / 缺口统计</a>'
        '<a href="#chromosomes">Native vs Accepted / 原生与接纳</a>'
        '<a href="#gaps-nav">Original Gaps / 原始缺口</a>'
        + link("native.html", "Native Jobs & Logs / 原生任务与日志")
        + link("native_visualization/index.html", "Offline Visualization / 离线原生可视化")
    )

    body = (
        '<section id="status-separation" class="panel">'
        '<div class="panel-head"><h2>Execution, Acceptance &amp; Publication / 执行、接纳与发布状态</h2></div>'
        '<div class="status-grid">'
        f'<div class="status-box"><div class="status-box-label">1. Native Execution / 原生执行</div><div>{native_badge}</div><p>{native_desc}</p></div>'
        f'<div class="status-box"><div class="status-box-label">2. CGAT Admission / CGAT 接纳</div><div>{accept_badge}</div><p>{accept_desc}</p></div>'
        f'<div class="status-box"><div class="status-box-label">3. Publication / 发布状态</div><div>{pub_badge}</div><p>{pub_desc}</p></div>'
        '</div>'
        '<p class="muted" style="margin-top:.65rem">All original LGZ gaps remain in the denominator. Fewer gaps are not proof of biological accuracy; no best tool is ranked. Coordinates: 0-based half-open placement; 1-based inclusive sources. '
        '/ 保留全部原始缺口作为分母；不以缺口更少判定准确率或评选最佳工具。坐标：放置位置 0-based 半开区间，来源诊断 1-based 闭区间。</p>'
        '</section>'
    )

    # One concise count summary
    metric_cards = [
        ("Original LGZ gaps / 原始缺口", fmt_int(orig_gaps)),
        ("Closed / 已闭合", fmt_int(counts.get("closed"))),
        ("Partial / 部分填补", fmt_int(counts.get("partial"))),
        ("Unfilled / 未填补", fmt_int(counts.get("unfilled"))),
        ("Rejected / 已拒绝", fmt_int(counts.get("rejected"))),
        ("Accepted edits / 接纳修改", fmt_int(accepted_edits)),
        ("Remaining gaps / 剩余缺口", fmt_int(remaining_gaps)),
    ]
    if summary.get("retained_flank_count"):
        metric_cards.append(("Original flanks retained / 保留原侧翼", fmt_int(summary["retained_flank_count"])))
    body += (
        '<section id="counts" class="panel">'
        '<div class="panel-head"><h2>Accepted Gap Outcomes / 接纳缺口汇总</h2></div>'
        '<div class="metrics-strip">'
        + "".join(f'<div class="metric-cell"><span class="metric-label">{esc(k)}</span><span class="metric-value">{esc(v)}</span></div>' for k, v in metric_cards)
        + '</div>'
        + '</section>'
    )

    # Native versus accepted chromosomes
    chr_rows = []
    for r in summary["chromosomes"]:
        if r["native"]:
            native_cell = f'<span class="num">{esc(fmt_bp(r["native"]["length"]))}</span><br><small class="num">N: {esc(fmt_int(r["native"]["n_bases"]))} bp</small>'
        else:
            native_cell = '<span class="muted">Not recorded / 未记录</span>'
        accepted_cell = f'<span class="num">{esc(fmt_bp(r["accepted_length"]))}</span><br><small class="num">N: {esc(fmt_int(r["accepted_n_bases"]))} bp</small>'
        eq = r["native_equals_accepted"]
        if eq is True:
            match_cell = badge_html("Identical / 序列一致", "ok")
        elif eq is False:
            match_cell = badge_html("Different / 序列不同", "warn")
        else:
            match_cell = badge_html("Not comparable / 无法比较", "neutral")
        chr_rows.append((f'<code>{esc(r["chromosome"])}</code>', native_cell, accepted_cell, match_cell))
    body += (
        '<section id="chromosomes" class="panel">'
        '<div class="panel-head"><h2>Native versus Accepted / 原生输出与 CGAT 接纳对比</h2></div>'
        + table(["Chromosome", "Native length / N", "Accepted length / N", "Sequence match"], chr_rows, empty="No chromosomes recorded / 无染色体记录")
        + '</section>'
    )

    # Source evidence (optional)
    measured = summary.get("source_evidence")
    if measured is not None:
        sources = measured["sources"]
        ref_status_counts = Counter(row["ref_alignment_status"] for row in sources)
        ref_status_html = " · ".join(f'<code>{esc(k)}</code>: <b class="num">{esc(fmt_int(v))}</b>' for k, v in sorted(ref_status_counts.items())) or '<span class="muted">None / 无</span>'
        source_summary_payload = {
            "patch_source_placements": len(sources), "reference_status": dict(ref_status_counts),
            "final_annotation_rows": measured["final_annotation_rows"], "policy": measured["annotation_policy"],
            "coordinate_domain": measured["coordinate_domain"]
        }
        src_section = (
            '<section id="source-evidence" class="panel">'
            '<div class="panel-head"><h2>Accepted-source Measurements / 精修来源测量</h2></div>'
            + kv_grid([
                ("Patch source placements / 补丁来源定位", f'<span class="num">{esc(fmt_int(len(sources)))}</span>'),
                ("Reference alignment status / 参考比对状态", ref_status_html),
                ("Final annotation rows / 终版注释行数", f'<span class="num">{esc(fmt_int(measured["final_annotation_rows"]))}</span>'),
                ("Annotation policy / 注释策略", f'<code>{esc(measured["annotation_policy"])}</code>'),
                ("Coordinate domain / 坐标域", f'<code>{esc(measured["coordinate_domain"])}</code>'),
            ])
            + '<p class="muted">Context placement is not a homology claim. Clipped source marks are coordinate projections, not a complete final-genome rescan. '
            '/ 显示上下文不是同源证据；切片注释是坐标映射，不冒充完整终版基因组重扫描。</p>'
        )
        if sources:
            pages = [sources[i:i + PAGE_SIZE] for i in range(0, len(sources), PAGE_SIZE)]
            src_section += '<div class="link-row">' + link("sources-0001.html", f"All measured source placements ({len(sources):,}) / 全部来源测量", cls="link-pill") + '</div>'
            for number, page_rows in enumerate(pages, 1):
                src_nav = link("report.html", "Tool report / 工具报告")
                if number > 1:
                    src_nav += link(f"sources-{number - 1:04}.html", "Previous / 上一页")
                if number < len(pages):
                    src_nav += link(f"sources-{number + 1:04}.html", "Next / 下一页")
                src_table_rows = []
                for row in page_rows:
                    ann = row["annotations"]
                    ann_str = json.dumps(ann, ensure_ascii=False)
                    ann_cell = disclosure(f"Annotations ({len(ann)})", '<pre>' + json_text(ann) + '</pre>') if isinstance(ann, (list, dict)) and len(ann_str) > 120 else f'<code>{esc(ann_str)}</code>'
                    src_table_rows.append((
                        esc(row["dataset"]), f'<code>{esc(row["contig"])}</code>', f'<code>{esc(row["chromosome"])}</code>',
                        f'<span class="num">{esc(fmt_int(row["length"]))}</span>', status_badge(row["ref_alignment_status"]),
                        f'<span class="num">{esc(row["hits_on_chromosome"])} / {esc(row["reference_hits"])}</span>', ann_cell
                    ))
                src_body = '<section class="panel">' + table(
                    ["Source dataset", "Contig", "Chromosome", "Length", "Reference measurement", "Hits: this chr / all", "Annotations"],
                    src_table_rows
                ) + '</section>'
                (directory / f"sources-{number:04}.html").write_text(
                    page(
                        "Accepted-source measurements / 精修来源测量",
                        src_body,
                        scope="CGAT Source Evidence / 来源测量",
                        subtitle=f'Tool: <code>{esc(tool)}</code> · Page {number} / {len(pages)}',
                        nav=src_nav,
                    ),
                    encoding="utf-8",
                )
        files = [row for row in assets if "/01_source_evidence/" in row["workspace_path"] and "/04_projection/" in row["workspace_path"]]
        src_section += table(["Coordinate/summary artifact", "Availability"], [
            (link(row["report_path"], Path(row["workspace_path"]).name) if row.get("report_path") else esc(Path(row["workspace_path"]).name),
             status_badge(row["availability"])) for row in files
        ], empty="No projection artifacts listed / 无投影文件")
        src_section += disclosure("Technical details: Source measurement summary JSON / 来源测量摘要 JSON", '<pre>' + json_text(source_summary_payload) + '</pre>')
        src_section += '</section>'
        body += src_section

    # Original gaps -> jobs -> decisions
    edits = {row["edit_id"]: row for row in final["edits"]}
    rejected = defaultdict(list)
    for row in provenance["rejected_candidates"]:
        for gap_id in row.get("gap_ids", []):
            rejected[gap_id].append(row)
    gaps = provenance["gap_outcomes"]
    jobs_by_gap = defaultdict(list)
    for job in summary["native_jobs"]:
        for gap_id in job["original_gap_ids"]:
            jobs_by_gap[gap_id].append(job)

    gap_page_map = {}
    gap_links = []
    (directory / "gaps").mkdir()
    total_gap_pages = (len(gaps) + PAGE_SIZE - 1) // PAGE_SIZE if gaps else 0
    for offset in range(0, len(gaps), PAGE_SIZE):
        number = offset // PAGE_SIZE + 1
        relative = f"gaps/{number:06d}.html"
        for gap in gaps[offset:offset + PAGE_SIZE]:
            gap_page_map[gap["gap_id"]] = relative
        gap_links.append(link(relative, f"{offset + 1}–{min(offset + PAGE_SIZE, len(gaps))}"))

    for offset in range(0, len(gaps), PAGE_SIZE):
        number = offset // PAGE_SIZE + 1
        relative = f"gaps/{number:06d}.html"
        gap_nav = link("../report.html", "Tool report / 工具报告") + link("../native.html", "Native jobs, reports & logs / 原生任务与日志")
        if number > 1:
            gap_nav += link(f"{number - 1:06d}.html", "Previous / 上一页")
        if number < total_gap_pages:
            gap_nav += link(f"{number + 1:06d}.html", "Next / 下一页")
        content = callout(
            "CGAT gap placement coordinates are <strong>0-based half-open</strong>; native gap diagnostics (when present) use <strong>1-based inclusive</strong> coordinates. "
            "/ CGAT 缺口坐标采用 <strong>0-based 半开区间</strong>；原生诊断记录采用 <strong>1-based 闭区间</strong>。",
            tone="info",
        )
        for gap in gaps[offset:offset + PAGE_SIZE]:
            gid = gap["gap_id"]
            g_chr = gap.get("chromosome", "")
            g_start = gap.get("start")
            g_end = gap.get("end")
            g_len = (g_end - g_start) if isinstance(g_start, int) and isinstance(g_end, int) else None
            g_status = gap.get("status")
            g_reasons = extract_recorded_reasons(gap)
            g_edits = [edits[name] for name in gap["edit_ids"]]
            g_rejected = rejected[gid]
            g_native = summary["native_gaps_by_original"].get(gid, [])
            g_jobs = jobs_by_gap[gid]

            card = f'<section id="{gap_anchor(gid)}" class="gap-card">'
            card += (
                '<div class="card-head">'
                f'<h2>{esc(gid)}</h2>'
                f'<div class="count-chips">{status_badge(g_status)}'
                f'<span class="count-chip"><code>{esc(g_chr)}</code>:<span class="num">{esc(fmt_int(g_start))}–{esc(fmt_int(g_end))}</span>'
                + (f' ({esc(fmt_int(g_len))} bp)' if g_len is not None else '')
                + ' · 0-based half-open</span></div></div>'
            )
            reason_html = (
                '<ul class="reason-list">' + "".join(f'<li><b>{esc(k)}</b>: {esc(v)}</li>' for k, v in g_reasons) + '</ul>'
                if g_reasons else '<span class="muted">No additional decision reason text recorded / 未记录额外原因文本</span>'
            )
            job_link_html = (
                ' · '.join(link("../native.html#" + gap_anchor(str(job["job_name"])), job["job_name"], cls="link-pill") for job in g_jobs)
                or link("../native.html", "Tool diagnostics / 工具诊断", cls="link-pill")
            )
            card += kv_grid([
                ("Recorded reason / 记录原因", reason_html),
                ("Accepted edits / 接纳修改", f'<span class="num">{esc(fmt_int(len(g_edits)))}</span>'),
                ("Not accepted candidates / 未接纳候选", f'<span class="num">{esc(fmt_int(len(g_rejected)))}</span>'),
            ])
            card += '<h3>Native jobs &amp; native diagnostics / 原生任务与原生诊断</h3>'
            card += f'<div class="link-row">{job_link_html}</div>'
            if g_native:
                ng_rows = []
                for ng in g_native:
                    ng_coords = f'{ng.get("chromosome", "")}:{fmt_int(ng.get("gap_start"))}–{fmt_int(ng.get("gap_end"))} (1-based incl.)'
                    ng_filled = ng.get("filled")
                    ng_filled_html = badge_html("Filled (native) / 原生判定已补", "info") if ng_filled is True else (
                        badge_html("Not filled (native) / 原生判定未补", "neutral") if ng_filled is False else badge_html("Not recorded / 未记录", "neutral")
                    )
                    ng_reasons = extract_recorded_reasons(ng)
                    ng_reason_cell = "; ".join(f"{k}: {v}" for k, v in ng_reasons) if ng_reasons else "—"
                    flank_statuses = [f"{direction}: {ng[direction + '_status']}" for direction in ("left", "right")
                                      if ng.get(direction + "_status") is not None]
                    if flank_statuses:
                        ng_filled_html += '<br><small>' + esc(" · ".join(flank_statuses)) + '</small>'
                    ng_rows.append((
                        f'<code>{esc(ng.get("gap_id", ""))}</code>',
                        f'<span class="num">{esc(ng_coords)}</span>',
                        ng_filled_html,
                        esc(ng.get("fill_direction") or "—"),
                        esc(ng_reason_cell),
                    ))
                card += table(["Native gap ID", "Native coords (1-based inclusive)", "Native judgment", "Direction", "Recorded reason"], ng_rows)
                card += disclosure("Raw native gap diagnostics JSON / 原始原生缺口 JSON", '<pre>' + json_text(g_native) + '</pre>')
            else:
                card += '<p class="muted">No overlapping per-gap native diagnostic rows recorded. / 未记录重叠的逐缺口原生诊断条目。</p>'

            card += '<h3>Accepted changes / 接纳修改</h3>'
            if g_edits:
                card += _summarize_reasons_html(g_edits)
                card += disclosure(f"Raw accepted edits JSON ({len(g_edits)}) / 原始接纳修改 JSON", '<pre>' + json_text(g_edits) + '</pre>')
            else:
                card += '<p class="muted">No accepted changes for this gap. / 该缺口无接纳修改。</p>'

            flanks = retained_flanks(g_edits) + [row for candidate in g_rejected
                                                for row in candidate.get("flank_decisions", [])
                                                if row.get("decision") == "retained_lgz"]
            if flanks:
                card += render_retained_flanks(flanks)

            card += '<h3>Not accepted / 未接纳候选</h3>'
            if g_rejected:
                card += _summarize_reasons_html(g_rejected)
                card += disclosure(f"Raw rejected candidates JSON ({len(g_rejected)}) / 原始未接纳候选 JSON", '<pre>' + json_text(g_rejected) + '</pre>')
            else:
                card += '<p class="muted">No rejected candidates attributed to this gap. / 无归属该缺口的未接纳候选。</p>'

            card += disclosure("Raw CGAT gap outcome JSON / 原始 CGAT 缺口记录 JSON", '<pre>' + json_text(gap) + '</pre>')
            card += '</section>'
            content += card

        (directory / relative).write_text(
            page(
                "Original gaps / 原始缺口",
                content,
                scope="CGAT Gap Detail / 原始缺口明细",
                subtitle=f'Tool: <code>{esc(tool)}</code> · Gaps {offset + 1}–{min(offset + PAGE_SIZE, len(gaps))} of {len(gaps):,} · Page {number} / {total_gap_pages}',
                nav=gap_nav,
            ),
            encoding="utf-8",
        )

    unattributed = [row for row in provenance["rejected_candidates"] if not row.get("gap_ids")]
    body += (
        '<section id="gaps-nav" class="panel">'
        '<div class="panel-head"><h2>Original Gap → Job → Decision / 原始缺口 → 任务 → 接纳</h2>'
        f'<span class="badge tone-neutral num">{esc(fmt_int(len(gaps)))} original gaps / 个原始缺口</span></div>'
        + ('<div class="pager">' + ''.join(gap_links) + '</div>' if gap_links else '<p class="muted">No original gaps / 无原始缺口</p>')
        + f'<h3>Unattributed rejected candidates / 无法归属原始缺口的未接纳候选 ({len(unattributed):,})</h3>'
        + (_summarize_reasons_html(unattributed) + disclosure("Raw unattributed rejected candidates JSON / 原始 JSON", '<pre>' + json_text(unattributed) + '</pre>')
           if unattributed else '<p class="muted">None recorded / 无无法归属原始缺口的未接纳候选。</p>')
        + '</section>'
    )

    # Inputs, recipe and resources (concise primary + technical fold-out)
    recipe = execution.get("recipe") or {}
    exec_payload = {
        "tool": tool, "run_id": run_id, "threads": execution.get("threads"),
        "timing": execution.get("timing", "not recorded"), "peak_rss": "not measured",
        "native_executed_this_attempt": native_executed, "native_reused": native_reused,
        "native_origin": native_origin, "requested_threads": execution.get("requested_threads"),
        "recipe": execution.get("recipe"),
        "launcher_command": execution.get("launcher_command"), "native_substeps": execution.get("native_substeps"),
        "command": execution.get("command")
    }
    timing = execution.get("timing")
    timing_str = json.dumps(timing, ensure_ascii=False) if isinstance(timing, (dict, list)) else (str(timing) if timing is not None else "Not recorded / 未记录")
    recipe_name = recipe.get("name") or recipe.get("schema") or "Not recorded / 未记录"
    body += (
        '<section id="execution" class="panel">'
        '<div class="panel-head"><h2>Inputs, Recipe &amp; Resources / 输入、配方与资源</h2></div>'
        + kv_grid([
            ("Tool / 工具", f'<code>{esc(tool)}</code>'),
            ("Run ID", f'<code>{esc(run_id)}</code>'),
            ("Threads (actual / requested) / 线程", f'<span class="num">{esc(fmt_int(execution.get("threads")))} / {esc(fmt_int(execution.get("requested_threads")))}</span>'),
            ("Recipe / 配方", f'<code>{esc(recipe_name)}</code>' + (f' <small>rev {esc(recipe.get("revision"))}</small>' if recipe.get("revision") else "")),
            ("Timing / 耗时", f'<code>{esc(timing_str)}</code>'),
            ("Peak RSS / 峰值内存", '<span class="muted">Not measured / 未测量</span>'),
        ])
        + disclosure("Technical details: Recipe, commands & execution metadata JSON / 配方、命令与执行元数据", '<pre>' + json_text(exec_payload) + '</pre>')
        + '<div class="link-row" style="margin-top:.75rem">'
        + link("native.html", "Native job reports and logs / 原生任务报告与日志", cls="link-pill")
        + link("native_visualization/index.html", "Offline native visualization / 离线原生可视化", cls="link-pill")
        + link("summary.json", "Machine-readable summary (summary.json)", cls="link-pill")
        + link("final_path.json", "Accepted sourced Final Path (final_path.json)", cls="link-pill")
        + '</div>'
        + '</section>'
    )

    # Native jobs & diagnostics page (native.html)
    vis_info = summary.get("native_visualization", {})
    vis_status = vis_info.get("status", "not_available")
    vis_reason = vis_info.get("reason", "")
    visualization_links = {
        source["workspace_path"]: row["wrapper_path"]
        for row in vis_info.get("views", []) if "wrapper_path" in row
        for source in row["sources"]
    }
    lookup = {row["workspace_path"]: row for row in assets}

    origin_run = (native_origin or {}).get("run_id", run_id)
    execution_log = lookup.get(f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{origin_run}/native.log", {})
    native_nav = (
        link("report.html", "Tool report / 工具报告")
        + (link(execution_log["report_path"], "Execution log / 执行日志") if "report_path" in execution_log else "")
        + link("native_visualization/index.html", "Offline native visualization / 离线原生可视化")
        + '<a href="#native-jobs">Native jobs / 原生任务</a>'
        + '<a href="#native-artifacts">Artifacts / 原生文件</a>'
    )
    native_body = callout(
        "Original HTML and diagnostics are retained verbatim as inert text. Managed native views are separately sandboxed and offline with no external CDN. Large sequences remain Server-only. "
        "/ 原始 HTML 与诊断以静态原文保留；管理的原生可视化另设离线隔离视图，不联网加载 CDN，也不复制大 reads 或原生基因组。",
        tone="info",
    )
    native_body += (
        '<section class="panel">'
        '<div class="panel-head"><h2>Offline Native Visualization / 离线原生可视化</h2>' + status_badge(vis_status) + '</div>'
        + (f'<p class="muted">Status reason / 状态原因: <code>{esc(vis_reason)}</code></p>' if vis_reason else '')
        + '<div class="link-row">' + link("native_visualization/index.html", "Open native visualization & availability index / 打开原生可视化与可用性目录", cls="link-pill") + '</div>'
        + '</section>'
    )

    native_body += '<section id="native-jobs" class="panel"><div class="panel-head"><h2>Native Jobs / 原生任务记录</h2>'
    native_body += f'<span class="badge tone-neutral num">{len(summary["native_jobs"]):,} recorded / 条已记录</span></div>'
    if not summary["native_jobs"]:
        native_body += callout(
            "No per-job rows were recorded in this report. This does not imply success, failure, or that no native jobs existed; inspect the recorded native logs and artifacts below. "
            "/ 本报告未记录逐任务条目。这不代表成功、失败或不存在原生任务；请查看下方原生日志与文件。",
            tone="neutral",
        )
    else:
        for job in summary["native_jobs"]:
            jname = str(job.get("job_name"))
            j_badge, j_detail = _job_status_summary(job)
            orig_links = []
            for gid in job.get("original_gap_ids", []):
                target = gap_page_map.get(gid)
                orig_links.append(link(target + "#" + gap_anchor(gid), gid) if target else f'<code>{esc(gid)}</code>')
            art_links = []
            for name in job.get("artifacts", []):
                art = lookup.get(name, {})
                if "report_path" in art:
                    art_links.append(link(art["report_path"], Path(name).name, cls="link-pill"))
                else:
                    art_links.append(f'<span class="count-chip">{esc(Path(name).name)} ({esc(art.get("availability", "server_only"))})</span>')
            if job.get("visualization_html") in visualization_links:
                art_links.append(link(visualization_links[job["visualization_html"]], "Offline native job visualization / 离线原生任务可视化", cls="link-pill"))

            native_body += f'<article class="job-card" style="margin-top:.75rem">'
            native_body += f'<div class="card-head"><h2 id="{gap_anchor(jname)}">{esc(jname)}</h2>{j_badge}</div>'
            native_body += kv_grid([
                ("Chromosome / 染色体", f'<code>{esc(job.get("chromosome") or "Not recorded / 未记录")}</code>'),
                ("Native gap ID / 原生缺口", f'<code>{esc(job.get("native_gap_id") if job.get("native_gap_id") is not None else "Not recorded / 未记录")}</code>'),
                ("Direction / 方向", f'<code>{esc(job.get("direction") or "Not recorded / 未记录")}</code>'),
                ("Linked original gaps / 关联原始缺口", " · ".join(orig_links) if orig_links else '<span class="muted">None mapped / 未映射</span>'),
            ])
            if j_detail:
                native_body += f'<p class="muted">{esc(j_detail)}</p>'
            if art_links:
                native_body += '<div class="link-row">' + "".join(art_links) + '</div>'
            else:
                native_body += '<p class="muted">No job-specific log or visualization artifacts recorded. / 未记录该任务专属日志或可视化文件。</p>'
            native_body += disclosure("Technical details: Raw job JSON / 原始任务记录 JSON", '<pre>' + json_text(job) + '</pre>')
            native_body += '</article>'
    native_body += '</section>'

    art_rows = []
    for row in assets:
        path_cell = link(row["report_path"], row["workspace_path"]) if "report_path" in row else f'<code>{esc(row["workspace_path"])}</code>'
        sha_cell = f'<code>{esc(row["sha256"][:16])}…</code>' + disclosure("Full SHA-256", f'<code>{esc(row["sha256"])}</code>')
        art_rows.append((path_cell, status_badge(row["availability"]), f'<span class="num">{esc(fmt_bytes(row.get("size_bytes")))}</span>', sha_cell))
    native_body += (
        '<section id="native-artifacts" class="panel">'
        '<div class="panel-head"><h2>Native Artifacts &amp; Checksums / 原生文件与校验值</h2>'
        f'<span class="badge tone-neutral num">{len(assets):,} files / 个文件</span></div>'
        + table(["Native artifact", "Availability", "Size", "SHA-256"], art_rows, empty="No native artifacts recorded / 无原生文件记录")
        + '</section>'
    )

    (directory / "native.html").write_text(
        page(
            "Native reports / 原生报告",
            native_body,
            scope="CGAT Native Diagnostics / 原生任务与诊断",
            subtitle=f'Tool: <code>{esc(tool)}</code> · Run ID: <code>{esc(run_id)}</code>',
            nav=native_nav,
        ),
        encoding="utf-8",
    )
    (directory / "report.html").write_text(
        page(
            tool + " refinement / 精修",
            body,
            scope="CGAT Refinement Tool Report / 精修工具报告",
            subtitle=f'Run ID: <code>{esc(run_id)}</code> · Coordinates: 0-based half-open (placement) / 1-based inclusive (sources)',
            nav=nav_html,
        ),
        encoding="utf-8",
    )


def build_tool_report(root, result):
    root = Path(root).resolve()
    tool, run_id = result["tool"], result["run_id"]
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ReportError("invalid refinement report workspace/tool/run")
    staging = Path(result["staging"]).resolve()
    if not staging.is_relative_to(root):
        raise ReportError("staged result is outside its workspace")
    provenance_path = safe_file(root, (staging / "provenance.json").relative_to(root).as_posix())
    marker_path = safe_file(root, f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{run_id}/invocation.json")
    marker = json.loads(marker_path.read_text())
    sha = marker.get("provenance_sha256")
    provenance = json.loads(read_bound(provenance_path, sha))
    if (marker.get("status") not in {"staged", "published"} or marker.get("tool") != tool or marker.get("run_id") != run_id
            or provenance.get("tool") != tool or provenance.get("run_id") != run_id
            or provenance.get("schema") != "cgat.refinement-publication" or provenance.get("schema_version") != 1):
        raise ReportError("native attempt has no completed content-bound result")
    for name, expected in provenance["artifacts"].items():
        path = safe_file(staging, name)
        if digest(path) != expected:
            raise ReportError("staged report artifact changed: " + name)
    final_bytes = read_bound(staging / "final_path.json", provenance["artifacts"]["final_path.json"])
    final = json.loads(final_bytes)
    with (staging / "remaining_gaps.tsv").open(newline="", encoding="utf-8") as stream:
        remaining = list(csv.DictReader(stream, delimiter="\t"))
    artifacts, jobs, native_gaps = native_diagnostics(root, tool, run_id, provenance["execution"])
    assets = asset_plan(root, artifacts)
    source_binding, source_summary = {}, None
    if result.get("source_evidence"):
        try:
            from refinement_source_evidence import load, verify_inputs, RECEIPT
        except ModuleNotFoundError:
            from .refinement_source_evidence import load, verify_inputs, RECEIPT
        evidence = result["source_evidence"]
        directory = Path(evidence["directory"])
        receipt_path = safe_file(directory, RECEIPT)
        receipt = load(directory)
        if digest(receipt_path) != evidence["receipt_sha256"] or receipt["recipe"]["provenance_sha256"] != sha:
            raise ReportError("source measurements do not bind the reported accepted result")
        verify_inputs(receipt["recipe"])
        source_binding = {"source_evidence_receipt_sha256": evidence["receipt_sha256"],
                          "source_evidence_generation_sha256": receipt["generation_sha256"]}
        artifacts[receipt_path.relative_to(root).as_posix()] = evidence["receipt_sha256"]
        for row in receipt["payload"]:
            artifacts[safe_file(directory, row["file"]).relative_to(root).as_posix()] = row["sha256"]
        source_summary = json.loads(safe_file(directory, "04_projection/summary.json").read_text())
        source_summary["generation_sha256"] = receipt["generation_sha256"]
        assets = asset_plan(root, artifacts)
    visual = native_view_plan(root, tool, run_id, provenance["execution"], jobs, native_gaps, assets)
    summary = summarize(provenance, final, remaining, jobs, native_gaps)
    summary["native_visualization"] = visual.binding
    summary["artifacts"] = assets
    if source_summary is not None:
        summary["source_evidence"] = source_summary
    binding = {"provenance_sha256": sha, "generator_sha256": digest(Path(__file__)), "assets": assets, "native_visualization": visual.binding, **source_binding}
    identity = fingerprint(binding)
    home = layout.path(f"04_refinement/{TOOL_DIRECTORIES[tool]}/05_report/{run_id}")
    destination = home / ("site-" + identity[:20])
    if destination.exists():
        receipt = json.loads(safe_file(destination, "manifest.json").read_text())
        if receipt.get("binding") != binding or not all(digest(safe_file(destination, name)) == expected for name, expected in receipt["files"].items()):
            raise ReportError("existing portable report was modified")
        return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}
    home.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".report-build-", dir=home))
    try:
        (temporary / "assets").mkdir()
        for row in assets:
            if "report_path" not in row:
                continue
            data = read_bound(safe_file(root, row["workspace_path"]), row["sha256"], limit=MAX_ASSET)
            (temporary / row["report_path"]).write_bytes(data)
        visual.write(temporary)
        (temporary / "final_path.json").write_bytes(final_bytes)
        atomic_json(temporary / "summary.json", summary)
        render_site(temporary, summary, provenance, final, assets)
        atomic_json(temporary / "manifest.json", {"schema": SCHEMA, "schema_version": 1, "binding": binding,
                    "files": {p.relative_to(temporary).as_posix(): digest(p) for p in sorted(temporary.rglob("*")) if p.is_file()}})
        if digest(provenance_path) != sha:
            raise ReportError("result changed during report generation")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}


def build_failure_report(root, tool, run_id, error, *, phase="native"):
    """Explain failed/preflight attempts without inventing any final assembly."""
    root = Path(root).resolve()
    layout = WorkspaceLayout.detect(root)
    if layout.version != 2 or tool not in TOOL_DIRECTORIES or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ReportError("invalid failed-attempt report identity")
    code = TOOL_DIRECTORIES[tool]
    artifacts = {}
    for name in ("invocation.json", "native_jobs.json", "native.log"):
        relative = f"04_refinement/{code}/02_jobs/{run_id}/{name}"
        if (root / relative).exists():
            artifacts[relative] = digest(safe_file(root, relative))
    diagnostics_error = None
    execution = {}
    native_gaps = []
    try:
        invocation_relative = f"04_refinement/{code}/02_jobs/{run_id}/invocation.json"
        if invocation_relative in artifacts:
            execution = json.loads(read_bound(safe_file(root, invocation_relative), artifacts[invocation_relative], limit=MAX_ASSET))
        artifacts, jobs, native_gaps = native_diagnostics(root, tool, run_id, {**execution, "artifacts": artifacts})
    except (OSError, ValueError, KeyError, TypeError) as diagnostic:
        jobs = []
        diagnostics_error = str(diagnostic)
    source_diagnostics = getattr(error, "source_evidence_diagnostics", None)
    if phase == "source_evidence" and source_diagnostics is not None:
        try:
            directory = Path(source_diagnostics)
            parent = layout.path(f"04_refinement/{code}/04_accepted/{run_id}/01_source_evidence")
            if directory.parent != parent or re.fullmatch(r"failed-[0-9a-f]{20}-[0-9a-f]{32}", directory.name) is None:
                raise ReportError("source failure diagnostics are outside this attempt")
            relative = (directory / "failure.json").relative_to(root).as_posix()
            failure = json.loads(safe_file(root, relative).read_text())
            if (failure.get("schema") != "cgat.refinement-source-evidence-failure" or failure.get("schema_version") != 1
                    or failure.get("status") not in {"failed", "interrupted"} or failure.get("recipe", {}).get("tool") != tool
                    or failure.get("recipe", {}).get("run_id") != run_id):
                raise ReportError("source failure diagnostics do not bind this attempt")
            artifacts[relative] = digest(safe_file(root, relative))
            for name, sha in failure["files"].items():
                if name.endswith(TEXT_ENDINGS):
                    relative = (directory / name).relative_to(root).as_posix()
                    if digest(safe_file(root, relative)) != sha:
                        raise ReportError("source failure diagnostic changed")
                    artifacts[relative] = sha
        except (OSError, ValueError, KeyError, TypeError) as diagnostic:
            diagnostics_error = (diagnostics_error + "; " if diagnostics_error else "") + str(diagnostic)
    assets = asset_plan(root, artifacts)
    visual = native_view_plan(root, tool, run_id, execution, jobs, native_gaps, assets, failed=True)
    summary = {"native_visualization": visual.binding, "schema": "cgat.refinement-failure-report", "schema_version": 1, "tool": tool, "run_id": run_id,
               "status": "failed", "phase": phase, "error": str(error), "native_jobs": jobs,
               "diagnostics_error": diagnostics_error, "source_diagnostics": str(source_diagnostics) if source_diagnostics else None,
               "final_available": False, "artifacts": assets,
               "native_status": execution.get("native_status"), "native_reused": execution.get("native_reused", False),
               "native_origin": execution.get("native_origin")}
    binding = {"summary": summary, "generator_sha256": digest(Path(__file__))}
    destination = layout.path(f"04_refinement/{code}/05_report/{run_id}/failure-{fingerprint(binding)[:20]}")
    if destination.exists():
        manifest = json.loads(safe_file(destination, "manifest.json").read_text())
        if manifest.get("binding") != binding or not all(digest(safe_file(destination, name)) == sha for name, sha in manifest["files"].items()):
            raise ReportError("failed-attempt report was modified")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".failure-report-", dir=destination.parent))
        try:
            (temporary / "assets").mkdir()
            visual.write(temporary)
            for row in assets:
                if "report_path" in row:
                    (temporary / row["report_path"]).write_bytes(read_bound(safe_file(root, row["workspace_path"]), row["sha256"], limit=MAX_ASSET))
            atomic_json(temporary / "summary.json", summary)
            vis_info = summary.get("native_visualization", {})
            vis_status = vis_info.get("status", "not_available")
            vis_reason = vis_info.get("reason", "")
            embedded_count = sum(1 for row in assets if "report_path" in row)
            lookup = {row["workspace_path"]: row for row in assets}
            vis_links = {
                source["workspace_path"]: row["wrapper_path"]
                for row in vis_info.get("views", []) if "wrapper_path" in row
                for source in row["sources"]
            }

            fail_body = (
                '<section class="panel">'
                '<div class="panel-head"><h2>Attempt Failure Summary / 失败尝试摘要</h2>' + status_badge("failed") + '</div>'
                + callout(
                    "Earlier successful files remain historical. / 先前的成功文件仍属于历史结果。",
                    tone="err",
                    title="No Final Path published for this attempt / 本次无最终路径发布",
                )
                + kv_grid([
                    ("Failing phase / 失败阶段", esc(PHASE_LABELS.get(phase, phase))),
                    ("Native status / 原生状态", status_badge(summary["native_status"]) if summary.get("native_status") else '<span class="muted">Not recorded / 未记录</span>'),
                    *([("Native origin / 原生来源", "Reused / 复用")] if summary.get("native_reused") else []),
                    ("Native diagnostics / 原生诊断文件", f'<span class="num">{embedded_count:,} embedded / {len(assets):,} total</span>'),
                    ("Offline visualization / 离线可视化", status_badge(vis_status) + (f' <small><code>{esc(vis_reason)}</code></small>' if vis_reason else '')),
                ])
                + '<h3>Actual error / 实际错误信息</h3>'
                + f'<div class="error-box">{esc(error)}</div>'
                + (callout(f'Diagnostics collection note / 诊断收集错误: <code>{esc(diagnostics_error)}</code>', tone="warn") if diagnostics_error else '')
                + (f'<p class="muted">Source diagnostics directory / 来源诊断目录: <code>{esc(source_diagnostics)}</code></p>' if source_diagnostics else '')
                + '<div class="link-row" style="margin-top:.65rem">'
                + link("native_visualization/index.html", "Offline native visualization / 离线原生可视化", cls="link-pill")
                + link("summary.json", "Failure summary JSON (summary.json)", cls="link-pill")
                + '</div>'
                + '</section>'
            )

            fail_body += '<section id="native-jobs" class="panel"><div class="panel-head"><h2>Recorded Native Jobs / 已记录原生任务</h2>'
            fail_body += f'<span class="badge tone-neutral num">{len(jobs):,} recorded / 条</span></div>'
            if not jobs:
                fail_body += '<p class="muted">No per-job rows were recorded for this failed attempt. This does not imply whether native jobs ran or succeeded; check the diagnostics table below. / 本次失败尝试未记录逐任务条目，不据此推断原生任务是否运行或成功；请查看下方诊断文件。</p>'
            else:
                j_rows = []
                for job in jobs:
                    j_badge, j_detail = _job_status_summary(job)
                    j_links = [
                        link(lookup[name]["report_path"], Path(name).name)
                        for name in job.get("artifacts", []) if name in lookup and "report_path" in lookup[name]
                    ]
                    if job.get("visualization_html") in vis_links:
                        j_links.append(link(vis_links[job["visualization_html"]], "Offline view / 离线视图"))
                    j_rows.append((
                        f'<code id="{gap_anchor(str(job.get("job_name")))}">{esc(job.get("job_name"))}</code>',
                        f'<code>{esc(job.get("chromosome") or "—")}</code>',
                        f'<code>{esc(job.get("native_gap_id") if job.get("native_gap_id") is not None else "—")}</code>',
                        j_badge + (f'<br><small>{esc(j_detail)}</small>' if j_detail else ''),
                        ' · '.join(j_links) if j_links else '<span class="muted">None embedded / 无嵌入日志</span>',
                    ))
                fail_body += table(["Job", "Chromosome", "Native gap", "Recorded status / reason", "Logs & views"], j_rows)
            fail_body += '</section>'

            diag_rows = [
                (
                    link(row["report_path"], row["workspace_path"]) if "report_path" in row else f'<code>{esc(row["workspace_path"])}</code>',
                    status_badge(row["availability"]),
                    f'<span class="num">{esc(fmt_bytes(row.get("size_bytes")))}</span>',
                )
                for row in assets
            ]
            fail_body += (
                '<section id="diagnostics" class="panel">'
                '<div class="panel-head"><h2>Native &amp; Source Diagnostics / 原生与来源诊断文件</h2></div>'
                + table(["Native/source diagnostic", "Availability", "Size"], diag_rows, empty="No diagnostic artifacts recorded / 无诊断文件记录")
                + disclosure("Technical details: Full failure summary JSON / 完整失败摘要 JSON", '<pre>' + json_text(summary) + '</pre>')
                + '</section>'
            )

            fail_nav = (
                '<a href="#native-jobs">Native jobs / 原生任务</a>'
                '<a href="#diagnostics">Diagnostics / 诊断文件</a>'
                + link("native_visualization/index.html", "Offline visualization / 离线原生可视化")
            )
            (temporary / "report.html").write_text(
                page(
                    tool + " failed attempt / 失败任务",
                    fail_body,
                    scope="CGAT Failed Attempt Report / 失败尝试报告",
                    subtitle=f'Run ID: <code>{esc(run_id)}</code> · Failing phase / 失败阶段: <code>{esc(phase)}</code>',
                    nav=fail_nav,
                    badge=status_badge("failed"),
                ),
                encoding="utf-8",
            )
            atomic_json(temporary / "manifest.json", {"schema": summary["schema"], "schema_version": 1, "binding": binding,
                        "files": {path.relative_to(temporary).as_posix(): digest(path) for path in temporary.rglob("*") if path.is_file()}})
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return {"directory": str(destination), "report": str(destination / "report.html"), "manifest_sha256": digest(destination / "manifest.json")}
