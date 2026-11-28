"""Portable offline HTML helpers for junction composition and connection diagnostics.

Uses Python standard library only. Emits self-contained, escaped, responsive,
accessible HTML fragments that integrate with ReportStyle.py or render cleanly
standalone without external assets or JavaScript.
"""
from html import escape as _html_escape
import math
from urllib.parse import quote, urlsplit

try:
    from ReportStyle import badge_bi, badge_html, bi, esc, status_tone
except ImportError:
    try:
        from .ReportStyle import badge_bi, badge_html, bi, esc, status_tone
    except ImportError:
        def esc(value) -> str:
            """Escape dynamic text or HTML attribute values."""
            return _html_escape(str(value), quote=True)

        def bi(en: str, zh: str) -> str:
            return f'<span class="t-en">{esc(en)}</span><span class="t-zh">{esc(zh)}</span>'

        def status_tone(status: str) -> str:
            """Map a machine status string to a restrained semantic tone."""
            normalized = str(status or "").strip().lower()
            if normalized in ("closed", "complete", "completed", "success", "connected", "extended"):
                return "ok"
            if normalized in ("no_candidates", "not_targeted", "skipped", "none", "na"):
                return "muted"
            if any(token in normalized for token in ("limit", "exhaust", "unclosed", "partial", "manual", "warn")):
                return "warn"
            if any(token in normalized for token in ("fail", "error", "no_extension")):
                return "err"
            return "info"

        def badge_html(label: str, tone: str = "muted") -> str:
            safe_tone = tone if tone in ("ok", "warn", "err", "info", "muted") else "muted"
            return f'<span class="badge badge-{safe_tone}">{esc(label)}</span>'

        def badge_bi(en: str, zh: str, tone: str = "muted") -> str:
            safe_tone = tone if tone in ("ok", "warn", "err", "info", "muted") else "muted"
            return f'<span class="badge badge-{safe_tone}">{bi(en, zh)}</span>'


_TRUNCATE_LIMIT = 24
_TRUNCATE_HEAD = 12
_TRUNCATE_TAIL = 8
_OVERVIEW_REPAIR_LIMIT = 8

_JUNCTION_CSS = """
.jr-root {
    --jr-bg: var(--surface, #ffffff);
    --jr-subtle: var(--surface-subtle, #f8fafc);
    --jr-ink: var(--ink, #0f172a);
    --jr-ink-2: var(--ink-secondary, #334155);
    --jr-muted: var(--ink-muted, #64748b);
    --jr-border: var(--border, #e2e8f0);
    --jr-border-strong: var(--border-strong, #cbd5e1);
    --jr-accent: var(--accent, #2563eb);
    --jr-accent-soft: var(--accent-soft, #eff6ff);
    --jr-accent-border: var(--accent-border, #bfdbfe);
    --jr-ok-ink: var(--ok-ink, #166534);
    --jr-ok-bg: var(--ok-bg, #ecfdf5);
    --jr-ok-border: var(--ok-border, #86efac);
    --jr-warn-ink: var(--warn-ink, #92400e);
    --jr-warn-bg: var(--warn-bg, #fffbeb);
    --jr-warn-border: var(--warn-border, #fcd34d);
    --jr-err-ink: var(--err-ink, #991b1b);
    --jr-err-bg: var(--err-bg, #fef2f2);
    --jr-err-border: var(--err-border, #fca5a5);
    --jr-muted-ink: var(--muted-ink, #475569);
    --jr-muted-bg: var(--muted-bg, #f1f5f9);
    --jr-muted-border: var(--muted-border, #cbd5e1);
    --jr-mono: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
    font-family: var(--font-sans, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
    color: var(--jr-ink);
    background: var(--jr-bg);
}
html[data-lang="en"] .jr-root .t-zh { display: none !important; }
html[data-lang="zh"] .jr-root .t-en { display: none !important; }
html:not([data-lang]) .jr-root .t-zh::before { content: " / "; color: var(--jr-muted); }
html:not([data-lang]) .jr-root .t-zh { color: var(--jr-muted); font-weight: 400; }
.jr-root .mono { font-family: var(--jr-mono); font-size: 0.84em; overflow-wrap: anywhere; word-break: break-word; }
.jr-root .num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.jr-root .muted { color: var(--jr-muted); }
.jr-root .badge { display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 3px; font-size: 0.75rem; font-weight: 500; line-height: 1.35; border: 1px solid transparent; white-space: nowrap; }
.jr-root .badge-ok { background: var(--jr-ok-bg); color: var(--jr-ok-ink); border-color: var(--jr-ok-border); }
.jr-root .badge-warn { background: var(--jr-warn-bg); color: var(--jr-warn-ink); border-color: var(--jr-warn-border); }
.jr-root .badge-err { background: var(--jr-err-bg); color: var(--jr-err-ink); border-color: var(--jr-err-border); }
.jr-root .badge-info { background: var(--jr-accent-soft); color: var(--jr-accent); border-color: var(--jr-accent-border); }
.jr-root .badge-muted { background: var(--jr-muted-bg); color: var(--jr-muted-ink); border-color: var(--jr-muted-border); }
.jr-root .jr-block { margin-top: 14px; }
.jr-root .jr-block:first-child { margin-top: 0; }
.jr-root .jr-subhead { margin: 0 0 8px 0; font-size: 0.88rem; font-weight: 600; color: var(--jr-ink); display: flex; align-items: baseline; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.jr-root .jr-strip { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 20px; padding: 8px 0; border-top: 1px solid var(--jr-border); border-bottom: 1px solid var(--jr-border); margin-bottom: 10px; font-size: 0.83rem; }
.jr-root .jr-strip-item { display: inline-flex; align-items: baseline; gap: 6px; }
.jr-root .jr-strip-label { color: var(--jr-muted); font-size: 0.79rem; }
.jr-root .jr-strip-val { font-weight: 600; color: var(--jr-ink); font-variant-numeric: tabular-nums; }
.jr-root .jr-strip-val.accent { color: var(--jr-accent); }
.jr-root .jr-strip-val.ok { color: var(--jr-ok-ink); }
.jr-root .jr-strip-val.warn { color: var(--jr-warn-ink); }
.jr-root .jr-strip-val.err { color: var(--jr-err-ink); }
.jr-root .jr-footnote { margin: 6px 0 10px; font-size: 0.79rem; color: var(--jr-muted); line-height: 1.5; }
.jr-root .jr-warn { background: var(--jr-warn-bg); border-left: 2px solid var(--jr-warn-ink); color: var(--jr-warn-ink); padding: 7px 11px; border-radius: 0 4px 4px 0; margin: 8px 0 10px; font-size: 0.82rem; }
.jr-root .jr-warn ul { margin: 3px 0 0; padding-left: 16px; }
.jr-root .jr-warn p { margin: 0; }
.jr-root .jr-chips { display: flex; flex-wrap: wrap; gap: 5px; margin: 6px 0 10px; align-items: center; }
.jr-root .jr-chip { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 3px; border: 1px solid var(--jr-warn-border); background: var(--jr-warn-bg); color: var(--jr-warn-ink); font-size: 0.76rem; }
.jr-root .jr-details { border-top: 1px solid var(--jr-border); margin-top: 10px; }
.jr-root .jr-details > summary { list-style: none; cursor: pointer; padding: 8px 0; color: var(--jr-ink-2); font-size: 0.84rem; font-weight: 600; display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; user-select: none; }
.jr-root .jr-details > summary::-webkit-details-marker { display: none; }
.jr-root .jr-details > summary::before { content: "\\25B8"; margin-right: 6px; font-size: 0.72rem; color: var(--jr-muted); }
.jr-root .jr-details[open] > summary::before { content: "\\25BE"; }
.jr-root .jr-details > summary:hover { color: var(--jr-ink); }
.jr-root .jr-details > summary:focus-visible, .jr-root .jr-table-wrap:focus-visible, .jr-root a:focus-visible { outline: 2px solid var(--jr-accent); outline-offset: 2px; border-radius: 3px; }
.jr-root .jr-details-summary-main { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 6px; flex: 1 1 auto; }
.jr-root .jr-details-body { padding: 4px 0 10px; }
.jr-root .jr-table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.jr-root table { width: 100%; border-collapse: collapse; font-size: 0.83rem; }
.jr-root thead th { background: transparent; color: var(--jr-muted); font-weight: 600; font-size: 0.76rem; text-align: left; padding: 7px 9px; border-top: 1px solid var(--jr-border-strong); border-bottom: 1px solid var(--jr-border-strong); white-space: nowrap; }
.jr-root td { padding: 7px 9px; border-bottom: 1px solid var(--jr-border); color: var(--jr-ink); vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }
.jr-root tbody tr:last-child td { border-bottom: 1px solid var(--jr-border-strong); }
.jr-root .jr-allele { font-family: var(--jr-mono); font-size: 0.79rem; background: var(--jr-subtle); border: 1px solid var(--jr-border); border-radius: 3px; padding: 1px 4px; display: inline-block; max-width: 100%; overflow-wrap: anywhere; }
.jr-root .jr-seq-full { font-family: var(--jr-mono); font-size: 0.76rem; background: var(--jr-subtle); border: 1px solid var(--jr-border); border-radius: 3px; padding: 4px 6px; display: block; white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-all; max-height: 160px; overflow-y: auto; }
.jr-root .jr-empty-allele { font-style: italic; color: var(--jr-muted); font-size: 0.79rem; }
.jr-root .jr-stage-list { display: flex; flex-direction: column; gap: 3px; }
.jr-root .jr-stage-item { font-size: 0.78rem; color: var(--jr-ink-2); }
.jr-root .jr-stage-tag { display: inline-block; font-family: var(--jr-mono); font-size: 0.72rem; font-weight: 600; padding: 1px 5px; border-radius: 3px; border: 1px solid var(--jr-border-strong); background: var(--jr-subtle); margin-right: 4px; }
.jr-root .jr-stage-tag-full { background: var(--jr-accent-soft); border-color: var(--jr-accent-border); color: var(--jr-accent); }
.jr-root .jr-flank-pair { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.jr-root .jr-policy-list { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 0.8rem; color: var(--jr-ink-2); }
.jr-root .jr-policy-list span b { color: var(--jr-ink); font-family: var(--jr-mono); font-weight: 600; }
.jr-root .jr-artifacts { margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; font-size: 0.81rem; }
.jr-root .artifact-link { display: inline-flex; align-items: center; padding: 3px 9px; background: var(--jr-subtle); border: 1px solid var(--jr-border); border-radius: 4px; color: var(--jr-accent); font-size: 0.8rem; text-decoration: none; }
.jr-root .artifact-link:hover { background: var(--jr-accent-soft); border-color: var(--jr-accent-border); }
@media (max-width: 768px) {
    .jr-root .jr-strip { gap: 5px 14px; }
}
@media print {
    .jr-root .jr-table-wrap, .jr-root .jr-seq-full { max-height: none; overflow: visible; }
}
"""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _fmt_bp(value, *, signed: bool = False) -> str:
    if not _is_number(value):
        return "—"
    prefix = "+" if signed and value > 0 else ""
    if _is_int(value):
        return f"{prefix}{value:,} bp"
    return f"{prefix}{value:,.2f} bp"


def _fmt_int(value) -> str:
    if not _is_int(value):
        return "—"
    return f"{value:,}"


def _fmt_fraction(value) -> str:
    if not _is_number(value):
        return "—"
    val = float(value)
    return f"{val * 100:.1f}%"


def _truncate_sequence(seq: str, limit: int = _TRUNCATE_LIMIT):
    """Truncate raw sequence string BEFORE HTML escaping."""
    if len(seq) <= limit:
        return seq, False
    return f"{seq[:_TRUNCATE_HEAD]}\u2026{seq[-_TRUNCATE_TAIL:]}", True


def _safe_relative_href(raw) -> str:
    """Allow only explicit relative file paths without scheme or traversal."""
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    if not text or any(ord(ch) < 32 for ch in text):
        return ""
    if text.startswith(("/", "\\", "~")):
        return ""
    parsed = urlsplit(text)
    if parsed.scheme or parsed.netloc:
        return ""
    normalized = text.replace("\\", "/")
    parts = normalized.split("/")
    if not parts or any(part in ("..", "") for part in parts):
        return ""
    if not any(part != "." for part in parts):
        return ""
    if ":" in parts[0]:
        return ""
    return quote(normalized, safe="/._-")


def _extract_artifacts(*containers) -> list:
    """Collect explicit relative evidence artifacts only; never link raw paths."""
    found = []
    seen = set()
    for container in containers:
        if not isinstance(container, dict):
            continue
        raw = container.get("evidence_artifacts")
        if isinstance(raw, dict):
            items = [(str(k), v) for k, v in raw.items()]
        elif isinstance(raw, (list, tuple)):
            items = []
            for entry in raw:
                if isinstance(entry, dict):
                    path = entry.get("href") or entry.get("path") or entry.get("file")
                    label = entry.get("label") or entry.get("name") or path
                    items.append((str(label or ""), path))
                elif isinstance(entry, str):
                    items.append((entry, entry))
        else:
            continue
        for label, path in items:
            safe = _safe_relative_href(path)
            if safe and (label, safe) not in seen:
                seen.add((label, safe))
                found.append((label or safe, safe))
    return found


def _has_junction_data(junction) -> bool:
    if not isinstance(junction, dict) or not junction:
        return False
    keys = (
        "mode", "gap_length", "flank_length_delta", "overlap_trim",
        "policy", "flanks", "repairs", "warnings", "evidence_artifacts",
    )
    for key in keys:
        val = junction.get(key)
        if val is not None and val != "" and val != [] and val != {}:
            return True
    return False


def _has_diagnostics_data(diagnostics) -> bool:
    if not isinstance(diagnostics, (list, tuple)):
        return False
    return any(isinstance(item, dict) for item in diagnostics)


def _has_anchor_retries_data(retries) -> bool:
    if not isinstance(retries, (list, tuple)):
        return False
    return any(isinstance(item, dict) for item in retries)


def _strip_html(items) -> str:
    parts = []
    for label_html, val_html, tone in items:
        tone_cls = f" {tone}" if tone in ("accent", "ok", "warn", "err") else ""
        parts.append(
            '<span class="jr-strip-item">'
            f'<span class="jr-strip-label">{label_html}</span>'
            f'<span class="jr-strip-val{tone_cls}">{val_html}</span>'
            '</span>'
        )
    return f'<div class="jr-strip" role="group">{"".join(parts)}</div>'


def _flank_badge(status) -> str:
    norm = str(status or "").strip().lower()
    if norm == "preserved":
        return badge_bi("Preserved", "原序列保持", "ok")
    if norm == "repaired":
        return badge_bi("Repaired (read-backed)", "读长修订", "info")
    if norm == "conflict":
        return badge_bi("Conflict (original retained)", "冲突（保留原序列）", "warn")
    if not norm:
        return badge_bi("Unspecified", "未提供", "muted")
    return badge_html(str(status), "muted")


def _repair_badge(status) -> str:
    norm = str(status or "").strip().lower()
    if norm == "accepted":
        return badge_bi("Accepted (applied)", "已采用", "info")
    if norm == "retained":
        return badge_bi("Retained (not applied)", "未应用（保留）", "warn")
    if norm == "protected":
        return badge_bi("Protected (not applied)", "受保护（未应用）", "muted")
    if not norm:
        return badge_bi("Unspecified", "未提供", "muted")
    return badge_html(str(status), "muted")


def _diag_status_badge(status, reason="") -> str:
    norm = str(status or "").strip().lower()
    reason_low = str(reason or "").strip().lower()
    if norm == "eligible" and not any(
        tok in reason_low for tok in ("insufficient", "conflict", "ambiguous", "unresolved", "reject", "fail")
    ):
        return badge_bi("Eligible", "合格", "info")
    if norm in ("rejected", "ineligible", "failed", "unclosed"):
        return badge_bi("Rejected", "未通过", "warn")
    if not norm:
        return badge_bi("Recorded", "已记录", "muted")
    return badge_html(str(status), "muted")


def _mode_html(mode) -> str:
    norm = str(mode or "").strip().lower()
    if norm == "gap":
        return bi("Gap fill", "缺口填补")
    if norm == "overlap":
        return bi("Original overlap", "原始重叠去重")
    if not norm:
        return "—"
    return esc(str(mode))


def _format_version_ref(family, version) -> str:
    fam = str(family) if family not in (None, "") else "—"
    if _is_int(version):
        return f"{fam}/v{version}"
    if version not in (None, ""):
        return f"{fam}/{version}"
    return fam


def _format_coords(repair: dict) -> str:
    start = repair.get("start0") if "start0" in repair else repair.get("start")
    end = repair.get("end0") if "end0" in repair else repair.get("end")
    if _is_int(start) and _is_int(end):
        return f"{start:,}..{end:,}"
    if start is not None or end is not None:
        return f"{start if start is not None else '—'}..{end if end is not None else '—'}"
    return "—"


def _format_allele(value, *, full: bool = False) -> str:
    if value is None:
        return '<span class="muted">—</span>'
    text = str(value)
    if text == "":
        return '<span class="jr-empty-allele">\u2205 (0 bp)</span>'
    length = len(text)
    if full:
        return (
            f'<code class="jr-seq-full">{esc(text)}</code>'
            f'<span class="muted num" style="font-size:0.74rem;">{length:,} bp</span>'
        )
    preview, truncated = _truncate_sequence(text)
    if truncated:
        return f'<code class="jr-allele">{esc(preview)}</code> <span class="muted num">({length:,} bp)</span>'
    return f'<code class="jr-allele">{esc(text)}</code> <span class="muted num">({length:,} bp)</span>'


def _format_strands(strands) -> str:
    if strands is None:
        return "—"
    if isinstance(strands, str):
        items = list(strands.strip())
    elif isinstance(strands, (list, tuple, set)):
        items = [str(item) for item in strands if item not in (None, "")]
    else:
        return esc(strands)
    if not items:
        return '<span class="muted"><span class="t-en">none</span><span class="t-sep">/</span><span class="t-zh">无</span></span>'
    return f'<span class="mono">{esc(", ".join(items))}</span>'


def _render_policy_details(policy) -> str:
    if not isinstance(policy, dict) or not policy:
        return ""
    preferred = [
        ("repair_window", "Window", "窗口", "bp"),
        ("min_support", "Min support", "最小支持", "reads"),
        ("min_fraction", "Min fraction", "最小比例", "fraction"),
        ("min_mapq", "Min MAPQ", "最小 MAPQ", ""),
        ("anchor", "Anchor", "锚定", "bp"),
        ("read_margin", "Margin", "边距", "bp"),
        ("min_boundary_identity", "Min identity", "最小一致性", "%"),
        ("projection_padding", "Context pad", "定位边距", "bp"),
        ("projection_max_context_edits", "Max ctx edits", "最大差异", ""),
        ("version", "Version", "版本", ""),
    ]
    rendered_keys = set()
    items = []
    for key, en, zh, unit in preferred:
        if key not in policy or policy[key] is None:
            continue
        rendered_keys.add(key)
        val = policy[key]
        if unit == "bp" and _is_number(val):
            display = _fmt_bp(val)
        elif unit == "reads" and _is_int(val):
            display = f"{val:,}"
        elif unit == "fraction" and _is_number(val):
            display = _fmt_fraction(val)
        elif unit == "%" and _is_number(val):
            display = f"{float(val):.1f}%"
        else:
            display = str(val)
        items.append(f'<span>{bi(en, zh)}: <b>{esc(display)}</b></span>')
    for key in sorted(policy):
        if key in rendered_keys or policy[key] is None:
            continue
        items.append(f'<span><code class="mono">{esc(key)}</code>: <b>{esc(policy[key])}</b></span>')
    if not items:
        return ""
    return (
        '<details class="jr-details">'
        f'<summary><span class="jr-details-summary-main">{bi("Repair policy parameters", "修订策略参数")}'
        f' <span class="muted num">({len(items)})</span></span></summary>'
        f'<div class="jr-details-body"><div class="jr-policy-list">{"".join(items)}</div></div>'
        '</details>'
    )


def _summarize_diagnostics(diagnostics: list) -> dict:
    entries = [d for d in diagnostics if isinstance(d, dict)]
    checked = len(entries)
    eligible = rejected = other_status = fast_checks = full_checks = 0
    rejection_reasons = {}

    for entry in entries:
        status = str(entry.get("status") or "").strip().lower()
        if status == "eligible":
            eligible += 1
        elif status in ("rejected", "ineligible", "failed", "unclosed"):
            rejected += 1
            reason = str(entry.get("reason") or "unspecified").strip() or "unspecified"
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        else:
            other_status += 1
            reason = str(entry.get("reason") or "").strip()
            if reason:
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
        stages = entry.get("stages")
        if isinstance(stages, (list, tuple)):
            if any(isinstance(st, dict) and str(st.get("stage") or "").strip().lower() == "fast" for st in stages):
                fast_checks += 1
            if any(isinstance(st, dict) and str(st.get("stage") or "").strip().lower() == "full" for st in stages):
                full_checks += 1

    return {
        "entries": entries,
        "checked": checked,
        "eligible": eligible,
        "rejected": rejected,
        "other_status": other_status,
        "fast_checks": fast_checks,
        "full_checks": full_checks,
        "rejection_reasons": rejection_reasons,
    }


def _render_diagnostics_section(diagnostics: list, *, heading_tag: str = "h3") -> str:
    stats = _summarize_diagnostics(diagnostics)
    if stats["checked"] == 0:
        return ""

    reason_chips = [
        f'<span class="jr-chip"><span class="mono">{esc(reason)}</span><strong class="num">&times;{count:,}</strong></span>'
        for reason, count in sorted(stats["rejection_reasons"].items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    reasons_html = f'<div class="jr-chips">{"".join(reason_chips)}</div>' if reason_chips else ""

    rows = []
    for entry in stats["entries"]:
        left_ref = _format_version_ref(entry.get("left_family"), entry.get("left_version"))
        right_ref = _format_version_ref(entry.get("right_family"), entry.get("right_version"))
        stages = entry.get("stages")
        stage_parts = []
        if isinstance(stages, (list, tuple)):
            for st in stages:
                if not isinstance(st, dict):
                    continue
                sname = str(st.get("stage") or "unknown")
                tag_cls = "jr-stage-tag jr-stage-tag-full" if sname.strip().lower() == "full" else "jr-stage-tag"
                sreason = st.get("reason")
                sreason_html = f' · <span class="mono">{esc(sreason)}</span>' if sreason else ""
                stage_parts.append(
                    f'<div class="jr-stage-item"><span class="{tag_cls}">{esc(sname)}</span>'
                    f'<span class="num">{esc(_fmt_int(st.get("blocks")))} blk, {esc(_fmt_int(st.get("candidates")))} cand</span>'
                    f'{sreason_html}</div>'
                )
        stages_html = f'<div class="jr-stage-list">{"".join(stage_parts)}</div>' if stage_parts else '<span class="muted">—</span>'
        reason_val = entry.get("reason")
        reason_html = f'<span class="mono">{esc(reason_val)}</span>' if reason_val else '<span class="muted">—</span>'
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(left_ref)}</td>'
            f'<td class="mono">{esc(right_ref)}</td>'
            f'<td>{stages_html}</td>'
            f'<td>{_diag_status_badge(entry.get("status"), reason_val or "")}</td>'
            f'<td>{reason_html}</td>'
            "</tr>"
        )

    strip = _strip_html([
        (bi("Checked pairs", "检查对数"), esc(_fmt_int(stats["checked"])), ""),
        (bi("Fast", "快速"), esc(_fmt_int(stats["fast_checks"])), ""),
        (bi("Full", "全长"), esc(_fmt_int(stats["full_checks"])), "accent" if stats["full_checks"] else ""),
        (bi("Eligible", "合格"), esc(_fmt_int(stats["eligible"])), "accent" if stats["eligible"] else ""),
        (bi("Rejected", "未通过"), esc(_fmt_int(stats["rejected"])), "warn" if stats["rejected"] else ""),
    ])

    return (
        '<div class="jr-block">'
        f'<{heading_tag} class="jr-subhead">{bi("Connection Diagnostics", "连接检查诊断")}</{heading_tag}>'
        f'{strip}{reasons_html}'
        '<details class="jr-details">'
        f'<summary><span class="jr-details-summary-main">{bi("Pair-level diagnostics", "逐对检查明细")}'
        f' <span class="muted num">({stats["checked"]:,})</span></span></summary>'
        '<div class="jr-details-body"><div class="jr-table-wrap table-scroll" tabindex="0" role="region">'
        '<table><thead><tr>'
        f'<th scope="col">{bi("Left", "左侧")}</th>'
        f'<th scope="col">{bi("Right", "右侧")}</th>'
        f'<th scope="col">{bi("Stages", "阶段")}</th>'
        f'<th scope="col">{bi("Status", "状态")}</th>'
        f'<th scope="col">{bi("Reason", "原因")}</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div></div>'
        '</details>'
        '</div>'
    )


def _render_junction_details(junction: dict, *, heading_tag: str = "h3") -> str:
    if not _has_junction_data(junction):
        return ""

    mode_raw = junction.get("mode")
    mode = str(mode_raw or "").strip().lower()
    gap_length = junction.get("gap_length")
    flank_delta = junction.get("flank_length_delta")
    overlap_trim = junction.get("overlap_trim")
    is_overlap = mode == "overlap" or (_is_number(overlap_trim) and overlap_trim > 0)

    gap_label = (
        bi("Original overlap", "原始重叠")
        if is_overlap or (_is_number(gap_length) and gap_length < 0)
        else bi("Gap-only length", "纯缺口长度")
    )
    strip = _strip_html([
        (bi("Mode", "模式"), _mode_html(mode_raw), "accent" if mode in ("gap", "overlap") else ""),
        (gap_label, esc(_fmt_bp(gap_length)), "accent" if _is_number(gap_length) else ""),
        (bi("Flank delta", "末端变化"), esc(_fmt_bp(flank_delta, signed=True)), "warn" if (_is_number(flank_delta) and flank_delta != 0) else ""),
        (bi("Overlap trim", "重叠裁剪"), esc(_fmt_bp(overlap_trim)), "accent" if (_is_number(overlap_trim) and overlap_trim > 0) else ""),
    ])

    if is_overlap:
        footnote = (
            '<p class="jr-footnote">'
            + bi(
                "Overlap trim is deliberate deduplication, not silent polishing (left copy retained).",
                "重叠裁剪为明确去重而非静默修饰（保留左侧原序列副本）。",
            )
            + "</p>"
        )
    else:
        footnote = (
            '<p class="jr-footnote">'
            + bi(
                "Gap-only length and flank delta are separate; retained edits were not applied; applied edits are read-supported, not proven biological corrections.",
                "纯缺口长度与末端修订变化独立统计；retained 未应用；已采用修订为读长支持修订，非已证实生物学校正。",
            )
            + "</p>"
        )

    raw_warnings = junction.get("warnings")
    warning_items = []
    if isinstance(raw_warnings, str) and raw_warnings.strip():
        warning_items = [raw_warnings.strip()]
    elif isinstance(raw_warnings, (list, tuple)):
        warning_items = [str(w) for w in raw_warnings if w not in (None, "")]
    warn_html = ""
    if warning_items:
        warn_li = "".join(f"<li>{esc(w)}</li>" for w in warning_items)
        warn_html = f'<div class="jr-warn" role="note"><ul>{warn_li}</ul></div>'

    flanks = junction.get("flanks")
    flanks_html = ""
    if isinstance(flanks, dict) and flanks:
        ordered_keys = [k for k in ("L", "R") if k in flanks] + sorted(k for k in flanks if k not in ("L", "R"))
        flank_entries = [(side, flanks.get(side)) for side in ordered_keys if isinstance(flanks.get(side), dict)]
        has_flank_counts = any(
            (_is_int(info.get(k)) and info.get(k) > 0)
            for _, info in flank_entries
            for k in ("proposed_variants", "accepted_variants", "protected_variants")
        )
        flank_rows = []
        for side, info in flank_entries:
            if has_flank_counts:
                flank_rows.append(
                    "<tr>"
                    f'<td class="mono">{esc(side)}</td>'
                    f'<td>{_flank_badge(info.get("status"))}</td>'
                    f'<td class="num">{esc(_fmt_int(info.get("proposed_variants")))}</td>'
                    f'<td class="num">{esc(_fmt_int(info.get("accepted_variants")))}</td>'
                    f'<td class="num">{esc(_fmt_int(info.get("protected_variants")))}</td>'
                    "</tr>"
                )
            else:
                flank_rows.append(
                    "<tr>"
                    f'<td class="mono">{esc(side)}</td>'
                    f'<td>{_flank_badge(info.get("status"))}</td>'
                    "</tr>"
                )
        if flank_rows:
            extra_cols = (
                f'<th scope="col">{bi("Proposed", "提议")}</th>'
                f'<th scope="col">{bi("Accepted", "采用")}</th>'
                f'<th scope="col">{bi("Protected", "保护")}</th>'
                if has_flank_counts else ""
            )
            flanks_html = (
                '<div class="jr-block">'
                f'<{heading_tag} class="jr-subhead">{bi("Flanks", "两侧末端状态")}</{heading_tag}>'
                '<div class="jr-table-wrap table-scroll" tabindex="0" role="region">'
                '<table><thead><tr>'
                f'<th scope="col">{bi("Flank", "侧翼")}</th>'
                f'<th scope="col">{bi("Status", "状态")}</th>'
                f'{extra_cols}'
                f'</tr></thead><tbody>{"".join(flank_rows)}</tbody></table></div></div>'
            )

    raw_repairs = junction.get("repairs")
    repairs = [r for r in raw_repairs if isinstance(r, dict)] if isinstance(raw_repairs, (list, tuple)) else []
    repairs_html = ""
    if repairs:
        accepted_n = sum(1 for r in repairs if str(r.get("status") or "").strip().lower() == "accepted")
        retained_n = sum(1 for r in repairs if str(r.get("status") or "").strip().lower() == "retained")
        protected_n = sum(1 for r in repairs if str(r.get("status") or "").strip().lower() == "protected")

        overview_rows = []
        for rep in repairs[:_OVERVIEW_REPAIR_LIMIT]:
            alt_r, span_r = rep.get("alt_reads"), rep.get("spanning_reads")
            support_summary = f"{alt_r:,}/{span_r:,}" if (_is_int(alt_r) and _is_int(span_r)) else (f"{alt_r:,}" if _is_int(alt_r) else "—")
            overview_rows.append(
                "<tr>"
                f'<td class="mono">{esc(rep.get("side") or "—")}</td>'
                f'<td class="mono num">{esc(_format_coords(rep))}</td>'
                f'<td>{_repair_badge(rep.get("status"))}</td>'
                f'<td>{_format_allele(rep.get("original"), full=False)}</td>'
                f'<td>{_format_allele(rep.get("proposed"), full=False)}</td>'
                f'<td class="num">{esc(support_summary)}</td>'
                f'<td class="mono">{esc(rep.get("reason") or "—")}</td>'
                "</tr>"
            )

        overflow_note = (
            f'<p class="jr-footnote">{bi(f"Showing {_OVERVIEW_REPAIR_LIMIT} of {len(repairs):,}; expand below for full records.", f"仅示前 {_OVERVIEW_REPAIR_LIMIT} / {len(repairs):,} 条；完整记录见下方。")}</p>'
            if len(repairs) > _OVERVIEW_REPAIR_LIMIT else ""
        )

        detail_rows = []
        for rep in repairs:
            other = _fmt_int(rep.get("other_reads"))
            if _is_int(rep.get("unresolved_context_reads")):
                other += f" ({rep['unresolved_context_reads']:,} unresolved / 未定位)"
            detail_rows.append(
                "<tr>"
                f'<td class="mono">{esc(rep.get("side") or "—")}</td>'
                f'<td class="mono num">{esc(_format_coords(rep))}</td>'
                f'<td>{_repair_badge(rep.get("status"))}</td>'
                f'<td>{_format_allele(rep.get("original"), full=True)}</td>'
                f'<td>{_format_allele(rep.get("proposed"), full=True)}</td>'
                f'<td class="num">{esc(_fmt_int(rep.get("alt_reads")))}</td>'
                f'<td class="num">{esc(_fmt_int(rep.get("ref_reads")))}</td>'
                f'<td class="num">{esc(other)}</td>'
                f'<td class="num">{esc(_fmt_int(rep.get("spanning_reads")))}</td>'
                f'<td class="num">{esc(_fmt_fraction(rep.get("alt_fraction")))}</td>'
                f'<td>{_format_strands(rep.get("strands"))}</td>'
                f'<td class="mono">{esc(rep.get("reason") or "—")}</td>'
                "</tr>"
            )

        counts_summary = f"{len(repairs):,} ({accepted_n:,}A / {retained_n:,}R / {protected_n:,}P)"
        repairs_html = (
            '<div class="jr-block">'
            f'<{heading_tag} class="jr-subhead">{bi("Terminal Edits", "末端修订提议")}'
            f'<span class="muted num" style="font-size:0.78rem;font-weight:500;">{esc(counts_summary)}</span></{heading_tag}>'
            '<div class="jr-table-wrap table-scroll" tabindex="0" role="region">'
            '<table><thead><tr>'
            f'<th scope="col">{bi("Side", "侧翼")}</th>'
            f'<th scope="col">{bi("Coords", "坐标")}</th>'
            f'<th scope="col">{bi("Status", "状态")}</th>'
            f'<th scope="col">{bi("Original", "原序列")}</th>'
            f'<th scope="col">{bi("Proposed", "提议序列")}</th>'
            '<th scope="col">Alt/Span</th>'
            f'<th scope="col">{bi("Reason", "原因")}</th>'
            f'</tr></thead><tbody>{"".join(overview_rows)}</tbody></table></div>'
            f'{overflow_note}'
            '<details class="jr-details">'
            f'<summary><span class="jr-details-summary-main">{bi("Full sequences & read support", "完整序列与读长证据")}'
            f' <span class="muted num">({len(repairs):,})</span></span></summary>'
            '<div class="jr-details-body"><div class="jr-table-wrap table-scroll" tabindex="0" role="region">'
            '<table><thead><tr>'
            f'<th scope="col">{bi("Side", "侧翼")}</th>'
            f'<th scope="col">{bi("Coords", "坐标")}</th>'
            f'<th scope="col">{bi("Status", "状态")}</th>'
            f'<th scope="col">{bi("Original (full)", "完整原序列")}</th>'
            f'<th scope="col">{bi("Proposed (full)", "完整提议序列")}</th>'
            '<th scope="col">Alt</th><th scope="col">Ref</th><th scope="col">Other</th><th scope="col">Span</th>'
            f'<th scope="col">{bi("Frac", "比例")}</th>'
            f'<th scope="col">{bi("Strands", "链向")}</th>'
            f'<th scope="col">{bi("Reason", "原因")}</th>'
            f'</tr></thead><tbody>{"".join(detail_rows)}</tbody></table></div></div>'
            '</details></div>'
        )

    policy_html = _render_policy_details(junction.get("policy")) if repairs else ""
    return f'<div class="jr-block">{strip}{footnote}{warn_html}{flanks_html}{repairs_html}{policy_html}</div>'


def _render_anchor_retries_section(retries, *, heading_tag: str = "h3") -> str:
    if not _has_anchor_retries_data(retries):
        return ""
    entries = [item for item in retries if isinstance(item, dict)]
    rows = []
    for entry in entries:
        fam = entry.get("family")
        fam_text = str(fam) if fam not in (None, "") else "—"
        reason = entry.get("reason")
        reason_html = f'<span class="mono">{esc(reason)}</span>' if reason not in (None, "") else '<span class="muted">—</span>'
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(fam_text)}</td>'
            f'<td class="num">{esc(_fmt_int(entry.get("attempt")))}</td>'
            f'<td class="num">{esc(_fmt_bp(entry.get("backoff_bases")))}</td>'
            f'<td>{reason_html}</td>'
            "</tr>"
        )
    table_html = (
        '<div class="jr-table-wrap table-scroll" tabindex="0" role="region">'
        '<table><thead><tr>'
        f'<th scope="col">{bi("Family", "家族")}</th>'
        f'<th scope="col">{bi("Attempt", "轮次")}</th>'
        f'<th scope="col">{bi("Backoff", "回退")}</th>'
        f'<th scope="col">{bi("Reason", "原因")}</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )
    if len(entries) > 6:
        body_html = (
            '<details class="jr-details">'
            f'<summary><span class="jr-details-summary-main">{bi("Anchor backoff attempts", "末端回退尝试")}'
            f' <span class="muted num">({len(entries):,})</span></span></summary>'
            f'<div class="jr-details-body">{table_html}</div></details>'
        )
    else:
        body_html = table_html
    return (
        '<div class="jr-block">'
        f'<{heading_tag} class="jr-subhead">{bi("Anchor Backoff", "末端锚点回退")}'
        f' <span class="muted num" style="font-size:0.78rem;font-weight:500;">({len(entries):,})</span></{heading_tag}>'
        '<p class="jr-footnote">'
        + bi(
            "Counted in the shared round budget — not free hidden retries and not proven corrections.",
            "计入共享轮次预算，非免费重试，也不视为已证实校正。",
        )
        + '</p>'
        f'{body_html}</div>'
    )


def _format_artifact_label(label: str) -> str:
    if " / " in label:
        en, zh = label.split(" / ", 1)
        if en.strip() and zh.strip() and any("\u4e00" <= ch <= "\u9fff" for ch in zh):
            return bi(en.strip(), zh.strip())
    return esc(label)


def _render_artifacts_bar(artifacts: list) -> str:
    if not artifacts:
        return ""
    links = "".join(
        f'<a class="artifact-link" href="{esc(href)}">{_format_artifact_label(label)}</a>'
        for label, href in artifacts
    )
    return f'<nav class="jr-artifacts" aria-label="Evidence artifacts">{links}</nav>'


def _junction_header_badge(junction, diagnostics, anchor_retries=None) -> str:
    if _has_junction_data(junction):
        flanks = junction.get("flanks") if isinstance(junction.get("flanks"), dict) else {}
        statuses = {str(v.get("status") or "").strip().lower() for v in flanks.values() if isinstance(v, dict)}
        mode = str(junction.get("mode") or "").strip().lower()
        if "conflict" in statuses:
            return badge_bi("Flank conflict (original retained)", "末端冲突（保留原序列）", "warn")
        if "repaired" in statuses:
            return badge_bi("Bounded end edit applied", "已应用末端修订", "info")
        if mode == "overlap":
            return badge_bi("Overlap deduplicated", "重叠去重", "info")
        if "preserved" in statuses:
            return badge_bi("Original flanks preserved", "原末端保持", "ok")
        return badge_html(str(junction.get("mode") or "—"), "info")
    stats = _summarize_diagnostics(diagnostics or [])
    if stats["eligible"] > 0:
        return badge_bi(f'{stats["eligible"]} eligible', f'{stats["eligible"]} 合格', "info")
    if stats["rejected"] > 0:
        return badge_bi("No eligible connection", "无合格连接", "warn")
    if _has_anchor_retries_data(anchor_retries):
        count = sum(1 for item in anchor_retries if isinstance(item, dict))
        return badge_bi(f"{count:,} anchor backoff", f"{count:,} 末端回退", "warn")
    return badge_bi("Diagnostics", "诊断记录", "muted")


def _render_junction_body(junction, diagnostics, *, anchor_retries=None, artifacts=None, heading_tag: str = "h3") -> str:
    parts = []
    if _has_junction_data(junction):
        parts.append(_render_junction_details(junction, heading_tag=heading_tag))
    if _has_anchor_retries_data(anchor_retries):
        parts.append(_render_anchor_retries_section(anchor_retries, heading_tag=heading_tag))
    if _has_diagnostics_data(diagnostics):
        parts.append(_render_diagnostics_section(diagnostics, heading_tag=heading_tag))
    if artifacts:
        parts.append(_render_artifacts_bar(artifacts))
    return "".join(parts)


def render_junction_report(result) -> str:
    """Render junction composition, anchor backoff attempts, and connection diagnostics.

    Returns an empty string when no junction, connection_diagnostics, or
    anchor_retries evidence is present so legacy reports remain unchanged.
    """
    if not isinstance(result, dict):
        return ""
    junction = result.get("junction")
    diagnostics = result.get("connection_diagnostics")
    anchor_retries = result.get("anchor_retries")
    if anchor_retries is None and isinstance(junction, dict):
        anchor_retries = junction.get("anchor_retries")
    if (
        not _has_junction_data(junction)
        and not _has_diagnostics_data(diagnostics)
        and not _has_anchor_retries_data(anchor_retries)
    ):
        return ""

    artifacts = _extract_artifacts(result, junction if isinstance(junction, dict) else None)
    header_badge = _junction_header_badge(junction, diagnostics, anchor_retries)
    body = _render_junction_body(
        junction, diagnostics, anchor_retries=anchor_retries, artifacts=artifacts, heading_tag="h3"
    )

    return (
        '<section class="section jr-root" aria-label="Junction evidence and connection diagnostics">'
        f'<style>{_JUNCTION_CSS}</style>'
        '<div class="section-header">'
        f'<h2>{bi("Junction & Connection Diagnostics", "连接边界与诊断")}</h2>'
        f'<div>{header_badge}</div>'
        '</div>'
        f'<div class="section-body">{body}</div>'
        '</section>'
    )


def _event_label(event: dict, index: int) -> str:
    if event.get("number") is not None and event.get("primary"):
        direction = event.get("direction")
        suffix = f" ({direction})" if direction else ""
        return f'#{event["number"]} {event["primary"]}{suffix}'
    if event.get("chromosome") and event.get("gap_id"):
        return f'{event["chromosome"]}:{event["gap_id"]}'
    for key in ("id", "name", "label", "primary"):
        if event.get(key) not in (None, ""):
            return str(event[key])
    if event.get("number") is not None:
        return f'Event #{event["number"]}'
    return f"Event #{index}"


def _event_status_badge(status) -> str:
    if status in (None, ""):
        return '<span class="muted">—</span>'
    text = str(status)
    norm = text.strip().lower()
    if norm in ("closed", "filled"):
        return badge_bi(text, "已填补" if norm == "filled" else "已闭合", "ok")
    if norm in ("unfilled", "unclosed"):
        return badge_bi(text, "未填补" if norm == "unfilled" else "未闭合", "err")
    if norm == "exhausted":
        return badge_bi(text, "延伸耗尽", "warn")
    if norm == "round_limit":
        return badge_bi(text, "轮次上限", "warn")
    if norm == "length_limit":
        return badge_bi(text, "长度上限", "warn")
    tone = status_tone(text)
    if norm != "closed" and tone == "info":
        tone = "warn"
    return badge_html(text, tone)


def render_project_junctions(result, *, include_event_details: bool = True, event_href_fn=None) -> str:
    """Aggregate junction and connection diagnostics across project events.

    Accepts a project result dict (reading result.get('events') or
    result.get('history'), with fallback to 'gaps') or a direct event list.
    Returns an empty string when no event contains junction or diagnostic data.
    """
    project_artifacts = []
    if isinstance(result, (list, tuple)):
        raw_events = result
    elif isinstance(result, dict):
        project_artifacts = _extract_artifacts(result)
        raw_events = result.get("events") or result.get("history") or result.get("gaps") or []
    else:
        return ""

    if not isinstance(raw_events, (list, tuple)):
        return ""

    evidenced = []
    for idx, item in enumerate(raw_events, 1):
        if not isinstance(item, dict):
            continue
        junction = item.get("junction")
        diagnostics = item.get("connection_diagnostics")
        anchor_retries = item.get("anchor_retries")
        if anchor_retries is None and isinstance(junction, dict):
            anchor_retries = junction.get("anchor_retries")
        has_j = _has_junction_data(junction)
        has_d = _has_diagnostics_data(diagnostics)
        has_r = _has_anchor_retries_data(anchor_retries)
        if has_j or has_d or has_r:
            evidenced.append((
                idx, item,
                junction if has_j else None,
                diagnostics if has_d else None,
                anchor_retries if has_r else None,
            ))

    if not evidenced:
        return ""

    total_events = sum(1 for item in raw_events if isinstance(item, dict))
    has_any_anchor_retries = any(retries is not None for _, _, _, _, retries in evidenced)
    has_any_flank_delta = any(
        _is_number(j.get("flank_length_delta")) and j.get("flank_length_delta") != 0
        for _, _, j, _, _ in evidenced if isinstance(j, dict)
    )
    has_any_overlap_trim = any(
        _is_number(j.get("overlap_trim")) and j.get("overlap_trim") > 0
        for _, _, j, _, _ in evidenced if isinstance(j, dict)
    )
    junction_count = flanks_preserved = flanks_repaired = flanks_conflict = 0
    repairs_accepted = repairs_retained = repairs_protected = 0
    diag_checked = diag_eligible = diag_rejected = 0
    anchor_retry_total = anchor_retry_events = 0

    summary_rows = []
    detail_blocks = []

    for idx, event, junction, diagnostics, anchor_retries in evidenced:
        label = _event_label(event, idx)
        mode_display = "—"
        gap_len_display = delta_display = trim_display = repair_cell = "—"
        flank_badges = []

        if junction:
            junction_count += 1
            mode_display = _mode_html(junction.get("mode"))
            gap_len_display = _fmt_bp(junction.get("gap_length"))
            delta_display = _fmt_bp(junction.get("flank_length_delta"), signed=True)
            trim_display = _fmt_bp(junction.get("overlap_trim"))

            flanks = junction.get("flanks")
            if isinstance(flanks, dict):
                ordered = [k for k in ("L", "R") if k in flanks] + sorted(k for k in flanks if k not in ("L", "R"))
                for side in ordered:
                    info = flanks.get(side)
                    if not isinstance(info, dict):
                        continue
                    fstatus = str(info.get("status") or "").strip().lower()
                    if fstatus == "preserved":
                        flanks_preserved += 1
                    elif fstatus == "repaired":
                        flanks_repaired += 1
                    elif fstatus == "conflict":
                        flanks_conflict += 1
                    flank_badges.append(
                        f'<span class="jr-flank-pair"><span class="mono">{esc(side)}:</span>{_flank_badge(info.get("status"))}</span>'
                    )

            raw_repairs = junction.get("repairs")
            if isinstance(raw_repairs, (list, tuple)) and any(isinstance(r, dict) for r in raw_repairs):
                reps = [r for r in raw_repairs if isinstance(r, dict)]
                acc = sum(1 for r in reps if str(r.get("status") or "").strip().lower() == "accepted")
                ret = sum(1 for r in reps if str(r.get("status") or "").strip().lower() == "retained")
                prot = sum(1 for r in reps if str(r.get("status") or "").strip().lower() == "protected")
                repairs_accepted += acc
                repairs_retained += ret
                repairs_protected += prot
                repair_cell = f"{acc:,}/{ret:,}/{prot:,}"
            elif isinstance(raw_repairs, (list, tuple)):
                repair_cell = "0/0/0"

        diag_cell = "—"
        if diagnostics:
            ds = _summarize_diagnostics(diagnostics)
            diag_checked += ds["checked"]
            diag_eligible += ds["eligible"]
            diag_rejected += ds["rejected"]
            diag_cell = f'{ds["checked"]:,} ({ds["fast_checks"]:,}F/{ds["full_checks"]:,}Full)'

        retry_cell_html = ""
        if has_any_anchor_retries:
            if anchor_retries:
                ev_retry_count = sum(1 for r in anchor_retries if isinstance(r, dict))
                anchor_retry_total += ev_retry_count
                anchor_retry_events += 1
                retry_cell_html = f'<td class="num">{ev_retry_count:,}</td>'
            else:
                retry_cell_html = '<td class="num">—</td>'

        flanks_cell = f'<div class="jr-flank-pair">{" ".join(flank_badges)}</div>' if flank_badges else '<span class="muted">—</span>'
        ev_href = _safe_relative_href(event_href_fn(event)) if callable(event_href_fn) else None
        if ev_href:
            label_html = f'<a href="{esc(ev_href)}" target="_blank" rel="noopener">{esc(label)}</a>'
        else:
            label_html = esc(label)
        delta_td = f'<td class="num">{esc(delta_display)}</td>' if has_any_flank_delta else ""
        trim_td = f'<td class="num">{esc(trim_display)}</td>' if has_any_overlap_trim else ""
        ev_status = event.get("status")
        if ev_status in (None, "") and "filled" in event:
            ev_status = "filled" if event.get("filled") else "unfilled"
        summary_rows.append(
            "<tr>"
            f'<td class="mono">{label_html}</td>'
            f'<td>{_event_status_badge(ev_status)}</td>'
            f'<td>{mode_display}</td>'
            f'<td class="num">{esc(gap_len_display)}</td>'
            f'{delta_td}'
            f'{trim_td}'
            f'<td>{flanks_cell}</td>'
            f'<td class="num">{esc(repair_cell)}</td>'
            f'<td class="num">{esc(diag_cell)}</td>'
            f'{retry_cell_html}'
            "</tr>"
        )

        if include_event_details:
            ev_artifacts = _extract_artifacts(event, junction if isinstance(junction, dict) else None)
            ev_body = _render_junction_body(
                junction, diagnostics, anchor_retries=anchor_retries, artifacts=ev_artifacts, heading_tag="h4"
            )
            ev_badge = _junction_header_badge(junction, diagnostics, anchor_retries)
            detail_blocks.append(
                '<details class="jr-details">'
                f'<summary><span class="jr-details-summary-main"><span class="mono">{esc(label)}</span></span><span>{ev_badge}</span></summary>'
                f'<div class="jr-details-body">{ev_body}</div>'
                '</details>'
            )

    strip_items = [(bi("Events", "含证据事件"), esc(f"{len(evidenced):,} / {total_events:,}"), "accent")]
    if junction_count:
        strip_items.append((
            bi("Flanks (P/R/C)", "末端 (保持/修订/冲突)"),
            esc(f"{flanks_preserved:,}/{flanks_repaired:,}/{flanks_conflict:,}"),
            "warn" if flanks_conflict else ("ok" if not flanks_repaired else ""),
        ))
        if repairs_accepted or repairs_retained or repairs_protected:
            strip_items.append((
                bi("Edits (A/R/P)", "修订 (采用/保留/保护)"),
                esc(f"{repairs_accepted:,}/{repairs_retained:,}/{repairs_protected:,}"),
                "warn" if repairs_retained else "",
            ))
    if diag_checked:
        strip_items.append((
            bi("Checks", "连接检查"),
            esc(f"{diag_checked:,} ({diag_eligible:,}✓/{diag_rejected:,}×)"),
            "warn" if (diag_rejected and not diag_eligible) else "",
        ))
    if anchor_retry_total:
        strip_items.append((
            bi("Anchor backoff", "末端回退"),
            bi(f"{anchor_retry_total:,} ({anchor_retry_events:,} evt)", f"{anchor_retry_total:,} 次（{anchor_retry_events:,} 缺口）"),
            "warn",
        ))

    footnote_parts = [
        bi(
            "Gap-only lengths, overlap trims (deliberate deduplication, not silent polishing), and flank deltas are separate; retained edits were not applied.",
            "纯缺口长度、重叠裁剪（去重而非静默修饰）与末端变化分开统计；保留项未修改原序列。",
        )
    ]
    if anchor_retry_total:
        footnote_parts.append(
            bi(
                "Anchor backoff retries count in the shared round budget — not free hidden retries and not proven corrections.",
                "末端回退计入共享轮次预算，不视为已证实校正。",
            )
        )

    header_badge = (
        badge_bi(f"{flanks_conflict:,} conflict(s)", f"{flanks_conflict:,} 末端冲突", "warn")
        if flanks_conflict
        else badge_bi(f"{len(evidenced):,} event(s)", f"{len(evidenced):,} 事件", "info")
    )
    delta_th = f'<th scope="col">{bi("Flank delta", "末端变化")}</th>' if has_any_flank_delta else ""
    trim_th = f'<th scope="col">{bi("Overlap trim", "重叠裁剪")}</th>' if has_any_overlap_trim else ""
    retry_th = '<th scope="col"><span class="t-en">Anchor retries</span><span class="t-sep">/</span><span class="t-zh">末端回退</span></th>' if has_any_anchor_retries else ""
    per_event_html = (
        '<details class="jr-details">'
        f'<summary><span class="jr-details-summary-main">{bi("Per-event details", "逐事件明细")}'
        f' <span class="muted num">({len(detail_blocks):,})</span></span></summary>'
        f'<div class="jr-details-body">{"".join(detail_blocks)}</div>'
        '</details>'
        if detail_blocks else ""
    )

    return (
        '<section class="section jr-root" aria-label="Project junction and connection summary">'
        f'<style>{_JUNCTION_CSS}</style>'
        '<div class="section-header">'
        f'<h2>{bi("Junction & Connection Summary", "连接边界与诊断汇总")}</h2>'
        f'<div>{header_badge}</div>'
        '</div>'
        '<div class="section-body">'
        f'{_strip_html(strip_items)}'
        f'<p class="jr-footnote">{" ".join(footnote_parts)}</p>'
        '<div class="jr-table-wrap table-scroll" tabindex="0" role="region">'
        '<table><thead><tr>'
        f'<th scope="col">{bi("Event", "事件")}</th>'
        f'<th scope="col">{bi("Status", "状态")}</th>'
        f'<th scope="col">{bi("Mode", "模式")}</th>'
        f'<th scope="col">{bi("Gap-only", "纯缺口")}</th>'
        f'{delta_th}'
        f'{trim_th}'
        f'<th scope="col">{bi("Flanks", "末端")}</th>'
        f'<th scope="col" title="Accepted / Retained / Protected">{bi("A/R/P", "采用/保留/保护")}</th>'
        f'<th scope="col">{bi("Diagnostics", "诊断")}</th>'
        f'{retry_th}'
        f'</tr></thead><tbody>{"".join(summary_rows)}</tbody></table></div>'
        f'{per_event_html}'
        f'{_render_artifacts_bar(project_artifacts)}'
        '</div></section>'
    )
