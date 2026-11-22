"""Portable offline HTML helpers for junction composition and connection diagnostics.

Uses Python standard library only. Emits self-contained, escaped, responsive,
accessible HTML fragments that integrate with ReportStyle.py or render cleanly
standalone without external assets or JavaScript.
"""
from html import escape as _html_escape
import math
from urllib.parse import quote, urlsplit

try:
    from ReportStyle import badge_html, esc, status_tone
except ImportError:
    try:
        from .ReportStyle import badge_html, esc, status_tone
    except ImportError:
        def esc(value) -> str:
            """Escape dynamic text or HTML attribute values."""
            return _html_escape(str(value), quote=True)

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
            """Render a semantic status pill with escaped text."""
            safe_tone = tone if tone in ("ok", "warn", "err", "info", "muted") else "muted"
            return f'<span class="badge badge-{safe_tone}">{esc(label)}</span>'


_TRUNCATE_LIMIT = 24
_TRUNCATE_HEAD = 12
_TRUNCATE_TAIL = 8
_OVERVIEW_REPAIR_LIMIT = 8

_JUNCTION_CSS = """
.jr-root {
    --jr-bg: var(--surface, #ffffff);
    --jr-subtle: var(--surface-subtle, #f1f5f9);
    --jr-ink: var(--ink, #0f172a);
    --jr-ink-2: var(--ink-secondary, #334155);
    --jr-muted: var(--ink-muted, #64748b);
    --jr-border: var(--border, #e2e8f0);
    --jr-border-strong: var(--border-strong, #cbd5e1);
    --jr-accent: var(--accent, #0b6b7c);
    --jr-accent-soft: var(--accent-soft, #eef7f9);
    --jr-accent-border: var(--accent-border, #b8dde4);
    --jr-ok-ink: var(--ok-ink, #166534);
    --jr-ok-bg: var(--ok-bg, #f0fdf4);
    --jr-ok-border: var(--ok-border, #bbf7d0);
    --jr-warn-ink: var(--warn-ink, #92400e);
    --jr-warn-bg: var(--warn-bg, #fffbeb);
    --jr-warn-border: var(--warn-border, #fde68a);
    --jr-err-ink: var(--err-ink, #991b1b);
    --jr-err-bg: var(--err-bg, #fef2f2);
    --jr-err-border: var(--err-border, #fecaca);
    --jr-muted-ink: var(--muted-ink, #475569);
    --jr-muted-bg: var(--muted-bg, #f1f5f9);
    --jr-muted-border: var(--muted-border, #cbd5e1);
    --jr-mono: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace);
    font-family: var(--font-sans, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif);
    color: var(--jr-ink);
    background: var(--jr-bg);
    border: 1px solid var(--jr-border);
    border-radius: var(--radius-md, 8px);
    box-shadow: var(--shadow-sm, 0 1px 2px rgba(15, 23, 42, 0.05));
    margin-bottom: 20px;
    overflow: hidden;
}
.jr-root .section-header {
    background: var(--jr-subtle);
    border-bottom: 1px solid var(--jr-border);
    padding: 12px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
}
.jr-root .section-header h2 {
    margin: 0;
    font-size: 0.98rem;
    font-weight: 600;
    color: var(--jr-ink);
}
.jr-root .section-body {
    padding: 16px 20px;
}
.jr-root .bilingual-zh {
    color: var(--jr-muted);
    font-weight: 400;
}
.jr-root .mono {
    font-family: var(--jr-mono);
    font-size: 0.84em;
    overflow-wrap: anywhere;
    word-break: break-word;
}
.jr-root .num {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}
.jr-root .muted {
    color: var(--jr-muted);
}
.jr-root .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.77rem;
    font-weight: 600;
    line-height: 1.4;
    border: 1px solid transparent;
    white-space: nowrap;
}
.jr-root .badge::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
}
.jr-root .badge-ok { background: var(--jr-ok-bg); color: var(--jr-ok-ink); border-color: var(--jr-ok-border); }
.jr-root .badge-warn { background: var(--jr-warn-bg); color: var(--jr-warn-ink); border-color: var(--jr-warn-border); }
.jr-root .badge-err { background: var(--jr-err-bg); color: var(--jr-err-ink); border-color: var(--jr-err-border); }
.jr-root .badge-info { background: var(--jr-accent-soft); color: var(--jr-accent); border-color: var(--jr-accent-border); }
.jr-root .badge-muted { background: var(--jr-muted-bg); color: var(--jr-muted-ink); border-color: var(--jr-muted-border); }
.jr-root .artifact-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
}
.jr-root .artifact-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 11px;
    background: var(--jr-subtle);
    border: 1px solid var(--jr-border);
    border-radius: var(--radius-sm, 6px);
    color: var(--jr-accent);
    font-size: 0.82rem;
    font-weight: 500;
    text-decoration: none;
}
.jr-root .artifact-link:hover {
    background: var(--jr-accent-soft);
    border-color: var(--jr-accent-border);
}
.jr-root .jr-block {
    margin-top: 16px;
}
.jr-root .jr-block:first-child {
    margin-top: 0;
}
.jr-root .jr-subhead {
    margin: 0 0 10px 0;
    font-size: 0.92rem;
    font-weight: 600;
    color: var(--jr-ink);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    flex-wrap: wrap;
}
.jr-root .jr-metrics {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 10px;
    margin-bottom: 14px;
}
.jr-root .jr-metric {
    background: var(--jr-bg);
    border: 1px solid var(--jr-border);
    border-radius: var(--radius-sm, 6px);
    padding: 11px 14px;
    min-width: 0;
}
.jr-root .jr-metric-label {
    font-size: 0.76rem;
    font-weight: 600;
    color: var(--jr-muted);
    margin: 0 0 4px 0;
    line-height: 1.35;
}
.jr-root .jr-metric-value {
    font-size: 1.15rem;
    font-weight: 650;
    color: var(--jr-ink);
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
    overflow-wrap: anywhere;
}
.jr-root .jr-metric-value.accent { color: var(--jr-accent); }
.jr-root .jr-metric-value.ok { color: var(--jr-ok-ink); }
.jr-root .jr-metric-value.warn { color: var(--jr-warn-ink); }
.jr-root .jr-metric-value.err { color: var(--jr-err-ink); }
.jr-root .jr-metric-note {
    margin-top: 4px;
    font-size: 0.75rem;
    color: var(--jr-muted);
    line-height: 1.35;
    overflow-wrap: anywhere;
}
.jr-root .jr-notice {
    background: var(--jr-subtle);
    border: 1px solid var(--jr-border);
    border-left: 3px solid var(--jr-border-strong);
    border-radius: var(--radius-sm, 6px);
    padding: 10px 14px;
    margin: 0 0 12px 0;
    font-size: 0.84rem;
    color: var(--jr-ink-2);
    line-height: 1.5;
}
.jr-root .jr-notice-warn {
    background: var(--jr-warn-bg);
    border-color: var(--jr-warn-border);
    border-left-color: var(--jr-warn-ink);
    color: var(--jr-warn-ink);
}
.jr-root .jr-notice-info {
    background: var(--jr-accent-soft);
    border-color: var(--jr-accent-border);
    border-left-color: var(--jr-accent);
    color: var(--jr-ink-2);
}
.jr-root .jr-notice p, .jr-root .jr-notice ul {
    margin: 0;
}
.jr-root .jr-notice p + p {
    margin-top: 4px;
}
.jr-root .jr-notice ul {
    padding-left: 18px;
    margin-top: 4px;
}
.jr-root .jr-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 8px 0 12px 0;
}
.jr-root .jr-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 9px;
    border-radius: 999px;
    border: 1px solid var(--jr-border-strong);
    background: var(--jr-subtle);
    color: var(--jr-ink-2);
    font-size: 0.77rem;
    line-height: 1.35;
}
.jr-root .jr-chip-warn {
    background: var(--jr-warn-bg);
    border-color: var(--jr-warn-border);
    color: var(--jr-warn-ink);
}
.jr-root .jr-details {
    border: 1px solid var(--jr-border);
    border-radius: var(--radius-sm, 6px);
    background: var(--jr-bg);
    margin-top: 12px;
}
.jr-root .jr-details > summary {
    list-style: none;
    cursor: pointer;
    padding: 10px 14px;
    background: var(--jr-subtle);
    color: var(--jr-ink);
    font-size: 0.86rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    border-radius: var(--radius-sm, 6px);
    user-select: none;
}
.jr-root .jr-details > summary::-webkit-details-marker {
    display: none;
}
.jr-root .jr-details > summary::before {
    content: "\\25B8";
    display: inline-block;
    margin-right: 6px;
    color: var(--jr-accent);
    transition: transform 0.12s ease;
}
.jr-root .jr-details[open] > summary {
    border-bottom: 1px solid var(--jr-border);
    border-bottom-left-radius: 0;
    border-bottom-right-radius: 0;
}
.jr-root .jr-details[open] > summary::before {
    content: "\\25BE";
}
.jr-root .jr-details > summary:hover {
    background: var(--jr-accent-soft);
}
.jr-root .jr-details > summary:focus-visible,
.jr-root .jr-table-wrap:focus-visible,
.jr-root a:focus-visible {
    outline: 2px solid var(--jr-accent);
    outline-offset: 2px;
}
.jr-root .jr-details-summary-main {
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    flex: 1 1 auto;
}
.jr-root .jr-details-body {
    padding: 12px 14px;
}
.jr-root .jr-table-wrap {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    border: 1px solid var(--jr-border);
    border-radius: var(--radius-sm, 6px);
    background: var(--jr-bg);
}
.jr-root table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
}
.jr-root thead th {
    background: var(--jr-subtle);
    color: var(--jr-ink-2);
    font-weight: 600;
    font-size: 0.78rem;
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid var(--jr-border-strong);
    white-space: nowrap;
}
.jr-root td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--jr-border);
    color: var(--jr-ink);
    vertical-align: top;
    overflow-wrap: anywhere;
    word-break: break-word;
}
.jr-root tbody tr:last-child td {
    border-bottom: none;
}
.jr-root .jr-allele {
    font-family: var(--jr-mono);
    font-size: 0.8rem;
    background: var(--jr-subtle);
    border: 1px solid var(--jr-border);
    border-radius: 4px;
    padding: 1px 5px;
    display: inline-block;
    max-width: 100%;
    overflow-wrap: anywhere;
}
.jr-root .jr-seq-full {
    font-family: var(--jr-mono);
    font-size: 0.78rem;
    background: var(--jr-subtle);
    border: 1px solid var(--jr-border);
    border-radius: 4px;
    padding: 4px 6px;
    display: block;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    word-break: break-all;
    max-height: 180px;
    overflow-y: auto;
}
.jr-root .jr-empty-allele {
    font-style: italic;
    color: var(--jr-muted);
    font-size: 0.8rem;
}
.jr-root .jr-stage-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.jr-root .jr-stage-item {
    font-size: 0.79rem;
    color: var(--jr-ink-2);
    line-height: 1.4;
}
.jr-root .jr-stage-tag {
    display: inline-block;
    font-family: var(--jr-mono);
    font-size: 0.74rem;
    font-weight: 600;
    padding: 1px 6px;
    border-radius: 4px;
    border: 1px solid var(--jr-border-strong);
    background: var(--jr-subtle);
    color: var(--jr-ink);
    margin-right: 4px;
}
.jr-root .jr-stage-tag-full {
    background: var(--jr-accent-soft);
    border-color: var(--jr-accent-border);
    color: var(--jr-accent);
}
.jr-root .jr-flank-pair {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
}
.jr-root .jr-policy-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 8px;
}
.jr-root .jr-policy-item {
    border: 1px solid var(--jr-border);
    border-radius: 5px;
    padding: 8px 10px;
    background: var(--jr-subtle);
}
.jr-root .jr-policy-key {
    font-size: 0.74rem;
    color: var(--jr-muted);
    font-weight: 600;
}
.jr-root .jr-policy-val {
    font-family: var(--jr-mono);
    font-size: 0.84rem;
    color: var(--jr-ink);
    margin-top: 2px;
}
.jr-root .jr-artifacts {
    margin-top: 12px;
}
@media (max-width: 768px) {
    .jr-root .jr-metrics {
        grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
    }
    .jr-root .jr-details > summary {
        padding: 9px 11px;
    }
    .jr-root .jr-details-body {
        padding: 10px 11px;
    }
}
@media print {
    .jr-root {
        box-shadow: none;
        border-color: #cbd5e1;
    }
    .jr-root .jr-table-wrap,
    .jr-root .jr-seq-full {
        max-height: none;
        overflow: visible;
    }
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
    if _is_int(value):
        prefix = "+" if signed and value > 0 else ""
        return f"{prefix}{value:,} bp"
    prefix = "+" if signed and value > 0 else ""
    return f"{prefix}{value:,.2f} bp"


def _fmt_int(value) -> str:
    if not _is_int(value):
        return "—"
    return f"{value:,}"


def _fmt_fraction(value) -> str:
    if not _is_number(value):
        return "—"
    val = float(value)
    return f"{val * 100:.1f}% ({val:.3f})"


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


def _flank_badge(status) -> str:
    norm = str(status or "").strip().lower()
    if norm == "preserved":
        return badge_html("Preserved / 原序列保持", "ok")
    if norm == "repaired":
        return badge_html("Repaired (read-backed) / 有界读长修订", "info")
    if norm == "conflict":
        return badge_html("Conflict (original retained) / 冲突（保留原序列）", "warn")
    if not norm:
        return badge_html("Unspecified / 未提供", "muted")
    return badge_html(str(status), "muted")


def _repair_badge(status) -> str:
    norm = str(status or "").strip().lower()
    if norm == "accepted":
        return badge_html("Accepted (applied) / 已采用（已应用）", "info")
    if norm == "retained":
        return badge_html("Retained (not applied) / 保留原序列（未应用）", "warn")
    if norm == "protected":
        return badge_html("Protected (not applied) / 受保护（未应用）", "muted")
    if not norm:
        return badge_html("Unspecified / 未提供", "muted")
    return badge_html(str(status), "muted")


def _diag_status_badge(status, reason="") -> str:
    norm = str(status or "").strip().lower()
    reason_low = str(reason or "").strip().lower()
    if norm == "eligible" and not any(
        tok in reason_low for tok in ("insufficient", "conflict", "ambiguous", "unresolved", "reject", "fail")
    ):
        return badge_html("Eligible / 合格", "info")
    if norm in ("rejected", "ineligible", "failed", "unclosed"):
        return badge_html("Rejected / 未通过", "warn")
    if not norm:
        return badge_html("Recorded / 已记录", "muted")
    return badge_html(str(status), "muted")


def _mode_label(mode) -> str:
    norm = str(mode or "").strip().lower()
    if norm == "gap":
        return "Gap fill / 缺口填补"
    if norm == "overlap":
        return "Original overlap / 原始重叠去重"
    if not norm:
        return "—"
    return str(mode)


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
            f'<div class="muted num" style="font-size:0.74rem;margin-top:2px;">{length:,} bp</div>'
        )
    preview, truncated = _truncate_sequence(text)
    if truncated:
        return (
            f'<code class="jr-allele">{esc(preview)}</code> '
            f'<span class="muted num">({length:,} bp, truncated / 已截断)</span>'
        )
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
        return '<span class="muted">none / 无</span>'
    return f'<span class="mono">{esc(", ".join(items))}</span>'


def _render_policy_details(policy) -> str:
    if not isinstance(policy, dict) or not policy:
        return ""
    preferred = [
        ("repair_window", "Repair window / 末端修订窗口", "bp"),
        ("min_support", "Min read support / 最小支持读长", "reads"),
        ("min_fraction", "Min allele fraction / 最小支持比例", "fraction"),
        ("min_mapq", "Min MAPQ / 最小比对质量", ""),
        ("anchor", "Interior anchor / 内部锚定长度", "bp"),
        ("read_margin", "Read margin / 读长覆盖边距", "bp"),
        ("min_boundary_identity", "Min boundary identity / 边界最小一致性", "%"),
        ("projection_padding", "Clipped-end context per side / 裁剪末端单侧定位长度", "bp"),
        ("projection_max_context_edits", "Max differences per context / 单侧定位允许的最大差异", ""),
        ("version", "Policy version / 策略版本", ""),
    ]
    rendered_keys = set()
    items = []
    for key, label, unit in preferred:
        if key not in policy or policy[key] is None:
            continue
        rendered_keys.add(key)
        val = policy[key]
        if unit == "bp" and _is_number(val):
            display = _fmt_bp(val)
        elif unit == "reads" and _is_int(val):
            display = f"{val:,} reads"
        elif unit == "fraction" and _is_number(val):
            display = _fmt_fraction(val)
        elif unit == "%" and _is_number(val):
            display = f"{float(val):.1f}%"
        else:
            display = str(val)
        items.append(
            '<div class="jr-policy-item">'
            f'<div class="jr-policy-key">{esc(label)}</div>'
            f'<div class="jr-policy-val">{esc(display)}</div>'
            '</div>'
        )
    for key in sorted(policy):
        if key in rendered_keys or policy[key] is None:
            continue
        items.append(
            '<div class="jr-policy-item">'
            f'<div class="jr-policy-key mono">{esc(key)}</div>'
            f'<div class="jr-policy-val">{esc(policy[key])}</div>'
            '</div>'
        )
    if not items:
        return ""
    return (
        '<details class="jr-details">'
        '<summary><span class="jr-details-summary-main">'
        'Bounded Repair Policy Parameters <span class="bilingual-zh">/ 有界末端修订策略参数</span>'
        f'<span class="muted num">({len(items)})</span>'
        '</span></summary>'
        '<div class="jr-details-body">'
        f'<div class="jr-policy-grid">{"".join(items)}</div>'
        '</div>'
        '</details>'
    )


def _summarize_diagnostics(diagnostics: list) -> dict:
    entries = [d for d in diagnostics if isinstance(d, dict)]
    checked = len(entries)
    eligible = 0
    rejected = 0
    other_status = 0
    fast_checks = 0
    full_checks = 0
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
            seen_fast = False
            seen_full = False
            for st in stages:
                if not isinstance(st, dict):
                    continue
                sname = str(st.get("stage") or "").strip().lower()
                if sname == "fast":
                    seen_fast = True
                elif sname == "full":
                    seen_full = True
            if seen_fast:
                fast_checks += 1
            if seen_full:
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

    reason_chips = []
    for reason, count in sorted(stats["rejection_reasons"].items(), key=lambda kv: (-kv[1], kv[0])):
        reason_chips.append(
            f'<span class="jr-chip jr-chip-warn">'
            f'<span class="mono">{esc(reason)}</span>'
            f'<strong class="num">&times;{count:,}</strong>'
            f'</span>'
        )
    reasons_html = ""
    if reason_chips:
        reasons_html = (
            '<div class="jr-chips" aria-label="Connection rejection reasons / 连接拒绝原因汇总">'
            '<span class="muted" style="font-size:0.78rem;align-self:center;">'
            'Rejection / non-eligible reasons <span class="bilingual-zh">/ 未通过原因</span>:</span>'
            f'{"".join(reason_chips)}'
            '</div>'
        )

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
                sname_low = sname.strip().lower()
                tag_cls = "jr-stage-tag jr-stage-tag-full" if sname_low == "full" else "jr-stage-tag"
                blocks = _fmt_int(st.get("blocks"))
                candidates = _fmt_int(st.get("candidates"))
                sreason = st.get("reason")
                sreason_html = f' &middot; <span class="mono">{esc(sreason)}</span>' if sreason else ""
                stage_parts.append(
                    '<div class="jr-stage-item">'
                    f'<span class="{tag_cls}">{esc(sname)}</span>'
                    f'<span class="num">{esc(blocks)} blocks, {esc(candidates)} cand</span>'
                    f'{sreason_html}'
                    '</div>'
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

    metrics = [
        ("Checked pairs / 检查对数", _fmt_int(stats["checked"]), "", ""),
        ("Fast-stage checks / 快速阶段检查", _fmt_int(stats["fast_checks"]), "", "Clipped terminal alignment / 末端截断比对"),
        ("Full-stage checks / 全长回退检查", _fmt_int(stats["full_checks"]), "accent" if stats["full_checks"] else "", "Full-sequence fallback / 全长序列回退"),
        ("Eligible / 合格连接", _fmt_int(stats["eligible"]), "accent" if stats["eligible"] else "", "Passed connection check / 通过连接检查"),
        ("Rejected / 未通过", _fmt_int(stats["rejected"]), "warn" if stats["rejected"] else "", "Not accepted as eligible / 未接受为合格连接"),
    ]
    cards = []
    for label, val, tone, note in metrics:
        tone_cls = f" {tone}" if tone else ""
        note_html = f'<div class="jr-metric-note">{esc(note)}</div>' if note else ""
        cards.append(
            '<div class="jr-metric">'
            f'<div class="jr-metric-label">{esc(label)}</div>'
            f'<div class="jr-metric-value{tone_cls}">{esc(val)}</div>'
            f'{note_html}'
            '</div>'
        )

    return (
        '<div class="jr-block">'
        f'<{heading_tag} class="jr-subhead">Connection Diagnostics '
        f'<span class="bilingual-zh">/ 连接检查诊断</span></{heading_tag}>'
        f'<div class="jr-metrics" role="group" aria-label="Connection diagnostics metrics / 连接诊断统计">{"".join(cards)}</div>'
        f'{reasons_html}'
        '<details class="jr-details">'
        '<summary><span class="jr-details-summary-main">'
        'Pair-level Fast / Full Diagnostics &amp; Rejection Details '
        '<span class="bilingual-zh">/ 逐对快速与全长检查及拒绝详情</span>'
        f'<span class="muted num">({stats["checked"]:,} pairs / 对)</span>'
        '</span></summary>'
        '<div class="jr-details-body">'
        '<div class="jr-table-wrap table-scroll" tabindex="0" role="region" '
        'aria-label="Connection diagnostics table / 连接诊断明细表">'
        '<table>'
        '<thead><tr>'
        '<th scope="col">Left / 左侧</th>'
        '<th scope="col">Right / 右侧</th>'
        '<th scope="col">Stages (fast / full) / 阶段</th>'
        '<th scope="col">Status / 状态</th>'
        '<th scope="col">Reason / 原因</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div>'
        '</div>'
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

    # Metrics: keep gap-only length strictly independent from flank length delta.
    metrics = [
        (
            "Junction mode / 连接模式",
            _mode_label(mode_raw),
            "accent" if mode in ("gap", "overlap") else "",
            (
                "Deliberate overlap deduplication, not silent polishing / 明确重叠去重，非静默修饰"
                if is_overlap
                else "Boundary-aware composition / 边界感知拼接"
            ),
        ),
        (
            (
                "Original overlap (gap_length) / 原始重叠长度"
                if is_overlap or (_is_number(gap_length) and gap_length < 0)
                else "Gap-only length / 纯缺口长度"
            ),
            _fmt_bp(gap_length, signed=False),
            "accent" if _is_number(gap_length) else "",
            (
                "Signed original overlap; independent of flank delta / 有符号原始重叠；独立于末端修订变化"
                if is_overlap or (_is_number(gap_length) and gap_length < 0)
                else "New gap-only sequence; independent of flank delta / 仅新增缺口长度，不含末端修订净变化"
            ),
        ),
        (
            "Flank length delta / 末端修订净变化",
            _fmt_bp(flank_delta, signed=True),
            "warn" if (_is_number(flank_delta) and flank_delta != 0) else "",
            "Net change from accepted bounded end edits only / 仅统计已采用的有界末端修订",
        ),
        (
            "Overlap trim / 重叠去重裁剪",
            _fmt_bp(overlap_trim, signed=False),
            "accent" if (_is_number(overlap_trim) and overlap_trim > 0) else "",
            (
                "Deliberate deduplication (left copy retained) / 明确去重（保留左侧原序列副本）"
                if (_is_number(overlap_trim) and overlap_trim > 0)
                else "No original overlap trimmed / 无原始重叠裁剪"
            ),
        ),
    ]
    metric_cards = []
    for label, val, tone, note in metrics:
        tone_cls = f" {tone}" if tone else ""
        metric_cards.append(
            '<div class="jr-metric">'
            f'<div class="jr-metric-label">{esc(label)}</div>'
            f'<div class="jr-metric-value{tone_cls}">{esc(val)}</div>'
            f'<div class="jr-metric-note">{esc(note)}</div>'
            '</div>'
        )

    notices = []
    if is_overlap:
        notices.append(
            '<div class="jr-notice jr-notice-info" role="note">'
            '<p><strong>Original overlap deduplication / 原始重叠去重：</strong> '
            'Overlap trim removes duplicated bases from the overlapping original end (retaining the left original copy). '
            'This is deliberate deduplication, not silent polishing.</p>'
            '<p class="bilingual-zh">重叠裁剪用于去除两侧原始序列重叠部分的重复碱基（保留左侧原序列副本），属于明确去重而非静默修饰。</p>'
            '</div>'
        )
    else:
        notices.append(
            '<div class="jr-notice" role="note">'
            '<p>Original interior sequences remain protected; only read-supported edits inside the bounded terminal window may be applied. '
            '<code>retained</code> means a proposed change was <strong>not applied</strong> and original sequence was kept; '
            'applied edits are read-supported revisions, not proven biological corrections.</p>'
            '<p class="bilingual-zh">原始内部序列受保护；仅在有界末端窗口内且满足独立读长支持阈值时应用修订。'
            '<code>retained</code> 表示提议改动<strong>未应用</strong>并保留原序列；已采用修订为读长支持修订，不视为已证实的生物学校正。</p>'
            '</div>'
        )

    raw_warnings = junction.get("warnings")
    warning_items = []
    if isinstance(raw_warnings, str) and raw_warnings.strip():
        warning_items = [raw_warnings.strip()]
    elif isinstance(raw_warnings, (list, tuple)):
        warning_items = [str(w) for w in raw_warnings if w not in (None, "")]
    if warning_items:
        warn_li = "".join(f"<li>{esc(w)}</li>" for w in warning_items)
        notices.append(
            '<div class="jr-notice jr-notice-warn" role="note" aria-label="Junction warnings / 连接警示">'
            '<p><strong>Warnings / 注意事项</strong></p>'
            f'<ul>{warn_li}</ul>'
            '</div>'
        )

    # Flanks table
    flanks = junction.get("flanks")
    flanks_html = ""
    if isinstance(flanks, dict) and flanks:
        ordered_keys = [k for k in ("L", "R") if k in flanks] + sorted(k for k in flanks if k not in ("L", "R"))
        flank_rows = []
        for side in ordered_keys:
            info = flanks.get(side)
            if not isinstance(info, dict):
                continue
            side_label = "L (Left / 左侧)" if side == "L" else ("R (Right / 右侧)" if side == "R" else str(side))
            flank_rows.append(
                "<tr>"
                f'<td class="mono">{esc(side_label)}</td>'
                f'<td>{_flank_badge(info.get("status"))}</td>'
                f'<td class="num">{esc(_fmt_int(info.get("proposed_variants")))}</td>'
                f'<td class="num">{esc(_fmt_int(info.get("accepted_variants")))}</td>'
                f'<td class="num">{esc(_fmt_int(info.get("protected_variants")))}</td>'
                "</tr>"
            )
        if flank_rows:
            flanks_html = (
                '<div class="jr-block">'
                f'<{heading_tag} class="jr-subhead">Terminal Flank Integrity '
                f'<span class="bilingual-zh">/ 两侧原始末端状态</span></{heading_tag}>'
                '<div class="jr-table-wrap table-scroll" tabindex="0" role="region" '
                'aria-label="Terminal flank status table / 两侧末端状态表">'
                '<table>'
                '<thead><tr>'
                '<th scope="col">Flank / 侧翼</th>'
                '<th scope="col">Status / 状态</th>'
                '<th scope="col">Proposed / 提议变异</th>'
                '<th scope="col">Accepted / 已采用</th>'
                '<th scope="col">Protected / 受保护</th>'
                '</tr></thead>'
                f'<tbody>{"".join(flank_rows)}</tbody>'
                '</table>'
                '</div>'
                '</div>'
            )

    # Repairs: truncated overview + full safely escaped sequences & read counts in <details>
    raw_repairs = junction.get("repairs")
    repairs = [r for r in raw_repairs if isinstance(r, dict)] if isinstance(raw_repairs, (list, tuple)) else []
    repairs_html = ""
    if repairs:
        accepted_n = sum(1 for r in repairs if str(r.get("status") or "").strip().lower() == "accepted")
        retained_n = sum(1 for r in repairs if str(r.get("status") or "").strip().lower() == "retained")
        protected_n = sum(1 for r in repairs if str(r.get("status") or "").strip().lower() == "protected")

        overview_rows = []
        for rep in repairs[:_OVERVIEW_REPAIR_LIMIT]:
            alt_r = rep.get("alt_reads")
            span_r = rep.get("spanning_reads")
            if _is_int(alt_r) and _is_int(span_r):
                support_summary = f"{alt_r:,} / {span_r:,}"
            elif _is_int(alt_r):
                support_summary = f"{alt_r:,}"
            else:
                support_summary = "—"
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

        overflow_note = ""
        if len(repairs) > _OVERVIEW_REPAIR_LIMIT:
            overflow_note = (
                f'<p class="section-note" style="margin-top:8px;">'
                f'Showing first {_OVERVIEW_REPAIR_LIMIT} of {len(repairs):,} proposed edits in overview; '
                f'expand details below for all records and full sequences. '
                f'<span class="bilingual-zh">概览仅显示前 {_OVERVIEW_REPAIR_LIMIT} 条，共 {len(repairs):,} 条；展开下方详情查看全部记录与完整序列。</span>'
                f'</p>'
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

        counts_summary = (
            f"{len(repairs):,} total / "
            f"{accepted_n:,} accepted / {retained_n:,} retained / {protected_n:,} protected"
        )
        repairs_html = (
            '<div class="jr-block">'
            f'<{heading_tag} class="jr-subhead">'
            'Terminal Flank Edit Proposals (Overview) '
            '<span class="bilingual-zh">/ 末端修订提议概览</span>'
            f'<span class="muted num" style="font-size:0.78rem;font-weight:500;">{esc(counts_summary)}</span>'
            f'</{heading_tag}>'
            '<div class="jr-table-wrap table-scroll" tabindex="0" role="region" '
            'aria-label="Terminal flank edits overview / 末端修订概览表">'
            '<table>'
            '<thead><tr>'
            '<th scope="col">Side / 侧翼</th>'
            '<th scope="col">Coords (0-based) / 坐标</th>'
            '<th scope="col">Status / 状态</th>'
            '<th scope="col">Original (preview) / 原序列</th>'
            '<th scope="col">Proposed (preview) / 提议序列</th>'
            '<th scope="col">Alt / Span</th>'
            '<th scope="col">Reason / 原因</th>'
            '</tr></thead>'
            f'<tbody>{"".join(overview_rows)}</tbody>'
            '</table>'
            '</div>'
            f'{overflow_note}'
            '<details class="jr-details">'
            '<summary><span class="jr-details-summary-main">'
            'Full Sequences &amp; Read-Support Evidence '
            '<span class="bilingual-zh">/ 完整序列与读长支持证据</span>'
            f'<span class="muted num">({len(repairs):,} entries / 条)</span>'
            '</span></summary>'
            '<div class="jr-details-body">'
            '<div class="jr-table-wrap table-scroll" tabindex="0" role="region" '
            'aria-label="Full terminal flank repair evidence table / 完整末端修订与读长证据表">'
            '<table>'
            '<thead><tr>'
            '<th scope="col">Side / 侧翼</th>'
            '<th scope="col">Coords / 坐标</th>'
            '<th scope="col">Status / 状态</th>'
            '<th scope="col">Original (full) / 完整原序列</th>'
            '<th scope="col">Proposed (full) / 完整提议序列</th>'
            '<th scope="col">Alt</th>'
            '<th scope="col">Ref</th>'
            '<th scope="col">Other</th>'
            '<th scope="col">Span</th>'
            '<th scope="col">Alt frac / 比例</th>'
            '<th scope="col">Strands / 链向</th>'
            '<th scope="col">Reason / 原因</th>'
            '</tr></thead>'
            f'<tbody>{"".join(detail_rows)}</tbody>'
            '</table>'
            '</div>'
            '</div>'
            '</details>'
            '</div>'
        )

    policy_html = _render_policy_details(junction.get("policy"))

    return (
        '<div class="jr-block">'
        f'<div class="jr-metrics" role="group" aria-label="Junction metrics / 连接指标">{"".join(metric_cards)}</div>'
        f'{"".join(notices)}'
        f'{flanks_html}'
        f'{repairs_html}'
        f'{policy_html}'
        '</div>'
    )


def _render_anchor_retries_section(retries, *, heading_tag: str = "h3") -> str:
    if not _has_anchor_retries_data(retries):
        return ""
    entries = [item for item in retries if isinstance(item, dict)]
    rows = []
    for entry in entries:
        fam = entry.get("family")
        fam_text = str(fam) if fam not in (None, "") else "—"
        attempt_text = _fmt_int(entry.get("attempt"))
        backoff_text = _fmt_bp(entry.get("backoff_bases"))
        reason = entry.get("reason")
        reason_html = f'<span class="mono">{esc(reason)}</span>' if reason not in (None, "") else '<span class="muted">—</span>'
        rows.append(
            "<tr>"
            f'<td class="mono">{esc(fam_text)}</td>'
            f'<td class="num">{esc(attempt_text)}</td>'
            f'<td class="num">{esc(backoff_text)}</td>'
            f'<td>{reason_html}</td>'
            "</tr>"
        )
    table_html = (
        '<div class="jr-table-wrap table-scroll" tabindex="0" role="region" '
        'aria-label="Terminal anchor backoff attempts table / 末端锚点回退尝试表">'
        '<table>'
        '<thead><tr>'
        '<th scope="col">Family / 家族</th>'
        '<th scope="col">Attempt / 轮次</th>'
        '<th scope="col">Backoff / 回退长度</th>'
        '<th scope="col">Reason / 原因</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div>'
    )
    if len(entries) > 6:
        body_html = (
            '<details class="jr-details">'
            '<summary><span class="jr-details-summary-main">'
            'Scheduled Anchor Backoff Attempts <span class="bilingual-zh">/ 已调度的末端锚点回退尝试</span>'
            f'<span class="muted num">({len(entries):,})</span>'
            '</span></summary>'
            f'<div class="jr-details-body">{table_html}</div>'
            '</details>'
        )
    else:
        body_html = table_html
    return (
        '<div class="jr-block">'
        f'<{heading_tag} class="jr-subhead">Terminal Anchor Backoff Attempts '
        '<span class="bilingual-zh">/ 末端锚点回退尝试</span>'
        f'<span class="muted num" style="font-size:0.78rem;font-weight:500;">({len(entries):,})</span>'
        f'</{heading_tag}>'
        '<div class="jr-notice" role="note">'
        '<p>Terminal anchor backoff retries are <strong>separate scheduled attempts counted in the shared round budget</strong> '
        '— not free hidden retries and not proven corrections.</p>'
        '<p class="bilingual-zh">末端锚点回退重试属于<strong>计入共享轮次预算的独立调度尝试</strong>，'
        '并非免费隐藏重试，也不视为已证实校正。</p>'
        '</div>'
        f'{body_html}'
        '</div>'
    )


def _render_artifacts_bar(artifacts: list) -> str:
    if not artifacts:
        return ""
    links = "".join(
        f'<li><a class="artifact-link" href="{esc(href)}">{esc(label)}</a></li>'
        for label, href in artifacts
    )
    return (
        '<nav class="jr-artifacts" aria-label="Junction evidence artifacts / 连接证据文件">'
        '<div class="artifact-bar-title">Evidence Artifacts <span class="bilingual-zh">/ 相对路径证据文件</span></div>'
        f'<ul class="artifact-list">{links}</ul>'
        '</nav>'
    )


def _junction_header_badge(junction, diagnostics, anchor_retries=None) -> str:
    if _has_junction_data(junction):
        flanks = junction.get("flanks") if isinstance(junction.get("flanks"), dict) else {}
        statuses = {str(v.get("status") or "").strip().lower() for v in flanks.values() if isinstance(v, dict)}
        mode = str(junction.get("mode") or "").strip().lower()
        if "conflict" in statuses:
            return badge_html("Flank conflict (original retained) / 末端冲突（保留原序列）", "warn")
        if "repaired" in statuses:
            return badge_html("Bounded end edit applied / 已应用有界末端修订", "info")
        if mode == "overlap":
            return badge_html("Overlap deduplicated / 原始重叠去重", "info")
        if "preserved" in statuses:
            return badge_html("Original flanks preserved / 原始末端保持", "ok")
        return badge_html(_mode_label(junction.get("mode")), "info")
    stats = _summarize_diagnostics(diagnostics or [])
    if stats["eligible"] > 0:
        return badge_html(f'{stats["eligible"]} eligible / 合格', "info")
    if stats["rejected"] > 0:
        return badge_html("No eligible connection / 无合格连接", "warn")
    if _has_anchor_retries_data(anchor_retries):
        count = sum(1 for item in anchor_retries if isinstance(item, dict))
        return badge_html(f"{count:,} anchor backoff attempt(s) / 末端回退尝试", "warn")
    return badge_html("Diagnostics recorded / 已记录诊断", "muted")


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
        '<section class="section jr-root" aria-label="Junction evidence and connection diagnostics / 连接与末端修订证据">'
        f'<style>{_JUNCTION_CSS}</style>'
        '<div class="section-header">'
        '<h2>Junction Composition &amp; Connection Diagnostics '
        '<span class="bilingual-zh">/ 连接边界与诊断证据</span></h2>'
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
    if norm == "closed":
        return badge_html(text, "ok")
    tone = status_tone(text)
    if norm != "closed" and tone == "info":
        tone = "warn"
    return badge_html(text, tone)


def render_project_junctions(result) -> str:
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
                idx,
                item,
                junction if has_j else None,
                diagnostics if has_d else None,
                anchor_retries if has_r else None,
            ))

    if not evidenced:
        return ""

    total_events = sum(1 for item in raw_events if isinstance(item, dict))
    has_any_anchor_retries = any(retries is not None for _, _, _, _, retries in evidenced)
    junction_count = 0
    gap_mode_count = 0
    overlap_mode_count = 0
    flanks_preserved = 0
    flanks_repaired = 0
    flanks_conflict = 0
    repairs_accepted = 0
    repairs_retained = 0
    repairs_protected = 0
    diag_checked = 0
    diag_fast = 0
    diag_full = 0
    diag_eligible = 0
    diag_rejected = 0
    anchor_retry_total = 0
    anchor_retry_events = 0
    warning_events = 0

    summary_rows = []
    detail_blocks = []

    for idx, event, junction, diagnostics, anchor_retries in evidenced:
        label = _event_label(event, idx)
        mode_display = "—"
        gap_len_display = "—"
        delta_display = "—"
        trim_display = "—"
        flank_badges = []
        repair_cell = "—"

        if junction:
            junction_count += 1
            mode_norm = str(junction.get("mode") or "").strip().lower()
            mode_display = _mode_label(junction.get("mode"))
            if mode_norm == "gap":
                gap_mode_count += 1
            elif mode_norm == "overlap":
                overlap_mode_count += 1

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
                repair_cell = f"{acc:,} / {ret:,} / {prot:,}"
            elif isinstance(raw_repairs, (list, tuple)):
                repair_cell = "0 / 0 / 0"

            raw_warnings = junction.get("warnings")
            has_warn = (
                (isinstance(raw_warnings, str) and bool(raw_warnings.strip()))
                or (isinstance(raw_warnings, (list, tuple)) and any(w not in (None, "") for w in raw_warnings))
            )
            if has_warn:
                warning_events += 1

        diag_cell = "—"
        if diagnostics:
            ds = _summarize_diagnostics(diagnostics)
            diag_checked += ds["checked"]
            diag_fast += ds["fast_checks"]
            diag_full += ds["full_checks"]
            diag_eligible += ds["eligible"]
            diag_rejected += ds["rejected"]
            diag_cell = f'{ds["checked"]:,} ({ds["fast_checks"]:,}F/{ds["full_checks"]:,}Full, {ds["rejected"]:,} rej)'

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
        summary_rows.append(
            "<tr>"
            f'<td class="mono">{esc(label)}</td>'
            f'<td>{_event_status_badge(event.get("status"))}</td>'
            f'<td>{esc(mode_display)}</td>'
            f'<td class="num">{esc(gap_len_display)}</td>'
            f'<td class="num">{esc(delta_display)}</td>'
            f'<td class="num">{esc(trim_display)}</td>'
            f'<td>{flanks_cell}</td>'
            f'<td class="num">{esc(repair_cell)}</td>'
            f'<td class="num">{esc(diag_cell)}</td>'
            f'{retry_cell_html}'
            "</tr>"
        )

        ev_artifacts = _extract_artifacts(event, junction if isinstance(junction, dict) else None)
        ev_body = _render_junction_body(
            junction, diagnostics, anchor_retries=anchor_retries, artifacts=ev_artifacts, heading_tag="h4"
        )
        ev_badge = _junction_header_badge(junction, diagnostics, anchor_retries)
        detail_blocks.append(
            '<details class="jr-details">'
            '<summary>'
            f'<span class="jr-details-summary-main"><span class="mono">{esc(label)}</span></span>'
            f'<span>{ev_badge}</span>'
            '</summary>'
            f'<div class="jr-details-body">{ev_body}</div>'
            '</details>'
        )

    metrics = [
        (
            "Events with evidence / 含证据事件",
            f"{len(evidenced):,} / {total_events:,}",
            "accent",
            f"Junctions: {junction_count:,} (gap: {gap_mode_count:,}, overlap: {overlap_mode_count:,})",
        ),
    ]
    if junction_count:
        metrics.append((
            "Flank integrity / 末端状态汇总",
            f"{flanks_preserved:,}P / {flanks_repaired:,}R / {flanks_conflict:,}C",
            "warn" if flanks_conflict else ("info" if flanks_repaired else "ok"),
            "Preserved / Repaired (read-backed) / Conflict (retained)",
        ))
        metrics.append((
            "End edit proposals / 末端修订统计",
            f"{repairs_accepted:,} / {repairs_retained:,} / {repairs_protected:,}",
            "warn" if repairs_retained else "",
            "Accepted (applied) / Retained (not applied) / Protected",
        ))
    if diag_checked:
        metrics.append((
            "Connection checks / 连接诊断汇总",
            f"{diag_checked:,} checked",
            "warn" if (diag_rejected and not diag_eligible) else "",
            f"Fast: {diag_fast:,}, Full: {diag_full:,}, Eligible: {diag_eligible:,}, Rejected: {diag_rejected:,}",
        ))
    if anchor_retry_total:
        metrics.append((
            "Anchor backoff attempts / 末端回退尝试",
            f"{anchor_retry_total:,} ({anchor_retry_events:,} evt)",
            "warn",
            "Counted in shared round budget; not free hidden retries / 计入共享轮次预算，非免费重试",
        ))
    metric_cards = []
    for mlabel, mval, mtone, mnote in metrics:
        tone_cls = f" {mtone}" if mtone in ("accent", "ok", "warn", "err") else ""
        metric_cards.append(
            '<div class="jr-metric">'
            f'<div class="jr-metric-label">{esc(mlabel)}</div>'
            f'<div class="jr-metric-value{tone_cls}">{esc(mval)}</div>'
            f'<div class="jr-metric-note">{esc(mnote)}</div>'
            '</div>'
        )

    notices = [
        '<div class="jr-notice" role="note">'
        '<p>Gap-only lengths, original overlap trims, and bounded flank deltas are reported separately per event. '
        'Overlap trim is deliberate deduplication, not silent polishing; <code>retained</code> edits were not applied.</p>'
        '<p class="bilingual-zh">纯缺口长度、原始重叠去重裁剪与有界末端修订净变化按事件独立列出；'
        '重叠裁剪为明确去重而非静默修饰，<code>retained</code> 修订未应用且保留原序列。</p>'
        '</div>'
    ]
    if anchor_retry_total:
        notices.append(
            '<div class="jr-notice" role="note">'
            '<p>Terminal anchor backoff retries are <strong>separate scheduled attempts counted in the shared round budget</strong> '
            '— not free hidden retries and not proven corrections.</p>'
            '<p class="bilingual-zh">末端锚点回退重试属于<strong>计入共享轮次预算的独立调度尝试</strong>，'
            '并非免费隐藏重试，也不视为已证实校正。</p>'
            '</div>'
        )
    if warning_events or flanks_conflict or repairs_retained:
        notices.append(
            '<div class="jr-notice jr-notice-warn" role="note">'
            f'<p>Attention / 复核提示: {warning_events:,} event(s) reported warnings, '
            f'{flanks_conflict:,} flank(s) had unconfirmed conflicts (original retained), '
            f'and {repairs_retained:,} proposed edit(s) were retained without modification.</p>'
            '</div>'
        )

    header_badge = (
        badge_html(f"{flanks_conflict:,} conflict(s) retained / 冲突保留", "warn")
        if flanks_conflict
        else (
            badge_html(f"{len(evidenced):,} event(s) with evidence / 含证据事件", "info")
        )
    )
    retry_th = '<th scope="col">Anchor retries / 末端回退</th>' if has_any_anchor_retries else ""

    return (
        '<section class="section jr-root" aria-label="Project junction and connection summary / 项目连接与末端修订汇总">'
        f'<style>{_JUNCTION_CSS}</style>'
        '<div class="section-header">'
        '<h2>Project Junctions &amp; Connection Diagnostics '
        '<span class="bilingual-zh">/ 项目连接边界与诊断汇总</span></h2>'
        f'<div>{header_badge}</div>'
        '</div>'
        '<div class="section-body">'
        f'<div class="jr-metrics" role="group" aria-label="Project junction summary metrics / 项目连接汇总指标">{"".join(metric_cards)}</div>'
        f'{"".join(notices)}'
        '<div class="jr-table-wrap table-scroll" tabindex="0" role="region" '
        'aria-label="Project junctions overview table / 项目连接概览表">'
        '<table>'
        '<thead><tr>'
        '<th scope="col">Event / 事件</th>'
        '<th scope="col">Status / 状态</th>'
        '<th scope="col">Mode / 模式</th>'
        '<th scope="col">Gap-only / 纯缺口</th>'
        '<th scope="col">Flank delta / 末端变化</th>'
        '<th scope="col">Overlap trim / 重叠裁剪</th>'
        '<th scope="col">Flanks / 两侧末端</th>'
        '<th scope="col">Repairs (A/R/P)</th>'
        '<th scope="col">Diagnostics / 诊断</th>'
        f'{retry_th}'
        '</tr></thead>'
        f'<tbody>{"".join(summary_rows)}</tbody>'
        '</table>'
        '</div>'
        '<div class="jr-block">'
        '<h3 class="jr-subhead">Per-Event Evidence Details '
        '<span class="bilingual-zh">/ 逐事件详细证据</span></h3>'
        f'{"".join(detail_blocks)}'
        '</div>'
        f'{_render_artifacts_bar(project_artifacts)}'
        '</div>'
        '</section>'
    )
