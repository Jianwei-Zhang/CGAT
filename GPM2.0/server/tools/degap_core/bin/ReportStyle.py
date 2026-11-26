"""Shared offline presentation styles and HTML helpers for DEGAP reports.

Uses Python standard library only so generated HTML reports remain completely
self-contained, offline-readable, responsive, keyboard-accessible, and
print-friendly.
"""
from html import escape


BASE_CSS = """
:root {
    --bg: #f7f8fa;
    --surface: #ffffff;
    --surface-subtle: #f8fafc;
    --surface-muted: #f1f3f5;
    --surface-hover: #f4f6f8;
    --ink: #111827;
    --ink-secondary: #374151;
    --ink-muted: #6b7280;
    --border: #e5e7eb;
    --border-strong: #d1d5db;
    --accent: #0f6d74;
    --accent-hover: #0b545a;
    --accent-soft: #eef7f7;
    --accent-border: #b8dce0;
    --ok-ink: #1b5e3c;
    --ok-bg: #f0f8f4;
    --ok-border: #b7dfc9;
    --warn-ink: #854d0e;
    --warn-bg: #fdf9ed;
    --warn-border: #e5cc85;
    --err-ink: #991b1b;
    --err-bg: #fdf2f2;
    --err-border: #eab3b3;
    --muted-ink: #4b5563;
    --muted-bg: #f3f4f6;
    --muted-border: #d1d5db;
    --radius-sm: 4px;
    --radius-md: 6px;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

*, *::before, *::after {
    box-sizing: border-box;
}

html {
    -webkit-text-size-adjust: 100%;
}

html[data-lang="en"] .t-zh,
html[data-lang="en"] .lang-zh {
    display: none !important;
}

html[data-lang="zh"] .t-en,
html[data-lang="zh"] .lang-en {
    display: none !important;
}

.t-sep {
    display: none !important;
}

body {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--font-sans);
    font-size: 14px;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
}

a {
    color: var(--accent);
    text-decoration: none;
    text-underline-offset: 2px;
}

a:hover {
    color: var(--accent-hover);
    text-decoration: underline;
}

:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 3px;
}

code, .mono {
    font-family: var(--font-mono);
    font-size: 0.85em;
    overflow-wrap: anywhere;
    word-break: break-word;
}

code {
    background: var(--surface-muted);
    border-radius: 3px;
    padding: 0.08em 0.34em;
    color: var(--ink);
}

.num {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.hash {
    font-family: var(--font-mono);
    font-size: 0.78rem;
    color: var(--ink-secondary);
    overflow-wrap: anywhere;
    word-break: break-all;
}

.hash-short {
    display: inline-block;
    max-width: 11ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: bottom;
}

.muted {
    color: var(--ink-muted);
}

.bilingual-zh {
    color: var(--ink-muted);
    font-weight: 400;
}

.container, .report-shell {
    max-width: 1120px;
    margin: 0 auto;
    padding: 20px 20px 44px;
}

/* Header */
.header, .report-header {
    background: var(--surface);
    border: 1px solid var(--border);
    border-top: 2px solid var(--accent);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 14px;
}

.header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px 16px;
    flex-wrap: wrap;
}

.header-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
}

.header-actions {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    flex-shrink: 0;
}

.report-eyebrow {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--accent);
}

.header h1, .report-header h1 {
    margin: 0;
    font-size: 1.32rem;
    font-weight: 650;
    line-height: 1.25;
    letter-spacing: -0.015em;
    color: var(--ink);
    overflow-wrap: anywhere;
}

.header p, .report-header .report-subtitle, .header .sub {
    margin: 2px 0 0;
    color: var(--ink-muted);
    font-size: 0.84rem;
}

.header-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 14px;
    margin-top: 8px;
    font-size: 0.82rem;
    color: var(--ink-muted);
}

.header-badges, .badges {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 8px;
}

/* Inline Summary Strip (flat hairline bar, replaces bulky KPI card grids) */
.summary-strip {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px 22px;
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    font-size: 0.84rem;
    color: var(--ink-secondary);
}

.summary-strip-item {
    display: inline-flex;
    align-items: baseline;
    gap: 6px;
    white-space: nowrap;
}

.summary-strip-label {
    color: var(--ink-muted);
    font-size: 0.8rem;
}

.summary-strip-val {
    color: var(--ink);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

.summary-strip-val.accent { color: var(--accent); }
.summary-strip-val.ok { color: var(--ok-ink); }
.summary-strip-val.warn { color: var(--warn-ink); }
.summary-strip-val.err { color: var(--err-ink); }

.summary-strip-note {
    font-size: 0.78rem;
    color: var(--ink-muted);
}

/* Language Switcher */
.language-switcher {
    display: inline-flex;
    align-items: center;
    background: var(--surface-muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 2px;
    gap: 2px;
    flex-shrink: 0;
}

.language-btn {
    background: transparent;
    border: 0;
    color: var(--ink-muted);
    padding: 3px 10px;
    border-radius: 3px;
    font-size: 0.78rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.12s ease, color 0.12s ease;
    min-width: 38px;
}

.language-btn:hover {
    color: var(--ink);
}

.language-btn.active {
    background: var(--surface);
    color: var(--ink);
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

/* Legacy Metric Overview (kept minimal for compatibility) */
.metrics-grid, .stats-overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
    margin-bottom: 14px;
}

.metric-card, .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 11px 14px;
    min-width: 0;
}

.metric-label, .stat-label {
    font-size: 0.76rem;
    font-weight: 500;
    color: var(--ink-muted);
    margin: 0 0 4px 0;
    line-height: 1.3;
}

.metric-value, .stat-value {
    font-size: 1.2rem;
    font-weight: 650;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
    line-height: 1.25;
    overflow-wrap: anywhere;
}

.metric-value.accent { color: var(--accent); }
.metric-value.ok, .stat-value.positive { color: var(--ok-ink); }
.metric-value.warn { color: var(--warn-ink); }
.metric-value.err, .stat-value.negative { color: var(--err-ink); }

.metric-note {
    margin-top: 3px;
    font-size: 0.76rem;
    color: var(--ink-muted);
    overflow-wrap: anywhere;
}

/* Callout / Notice */
.notice {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 2px solid var(--accent);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 9px 13px;
    margin-bottom: 14px;
    font-size: 0.84rem;
    color: var(--ink-secondary);
}

.notice p { margin: 0; }
.notice p + p { margin-top: 4px; }

.notice-ok {
    background: var(--ok-bg);
    border-color: var(--ok-border);
    border-left-color: var(--ok-ink);
    color: var(--ok-ink);
}

.notice-warn {
    background: var(--warn-bg);
    border-color: var(--warn-border);
    border-left-color: var(--warn-ink);
    color: var(--warn-ink);
}

.notice-neutral {
    background: var(--surface-subtle);
    border-color: var(--border);
    border-left-color: var(--border-strong);
    color: var(--ink-secondary);
}

/* Artifact Links */
.artifact-bar {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 16px;
    margin-bottom: 14px;
}

.artifact-bar-title {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--ink-muted);
    margin: 0 0 8px 0;
}

.artifact-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px 8px;
    margin: 0;
    padding: 0;
    list-style: none;
}

.artifact-link {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    background: var(--surface-subtle);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--accent);
    font-size: 0.81rem;
    font-weight: 500;
    overflow-wrap: anywhere;
    transition: background-color 0.12s ease, border-color 0.12s ease;
}

.artifact-link:hover {
    background: var(--accent-soft);
    border-color: var(--accent-border);
    color: var(--accent-hover);
    text-decoration: none;
}

/* Crisp Paper Panels (no heavy gray header slabs) */
.card, .section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    margin-bottom: 14px;
    overflow: hidden;
}

.card-header, .section-header {
    background: transparent;
    border-bottom: 1px solid var(--border);
    padding: 12px 18px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 0.96rem;
    font-weight: 600;
    color: var(--ink);
}

.section-header h2, .card-header h2 {
    margin: 0;
    font-size: 0.96rem;
    font-weight: 600;
    color: var(--ink);
}

.section-title {
    background: transparent;
    border-bottom: 1px solid var(--border);
    padding: 12px 18px;
    font-size: 0.96rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
}

.card-content, .section-body {
    padding: 14px 18px;
}

.section-note {
    margin: 0 0 10px 0;
    font-size: 0.82rem;
    color: var(--ink-muted);
}

/* Fold / Disclosure Drawers */
.fold-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 4px 18px;
    margin-bottom: 14px;
}

details.fold {
    border-top: 1px solid var(--border);
}

details.fold:first-child {
    border-top: 0;
}

details.fold > summary {
    list-style: none;
    cursor: pointer;
    padding: 11px 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--ink-secondary);
    user-select: none;
}

details.fold > summary::-webkit-details-marker {
    display: none;
}

details.fold > summary .fold-title {
    display: inline-flex;
    align-items: center;
    gap: 7px;
}

details.fold > summary .fold-title::before {
    content: "\\25B8";
    font-size: 0.72rem;
    color: var(--ink-muted);
    transition: transform 0.12s ease;
}

details.fold[open] > summary .fold-title::before {
    transform: rotate(90deg);
}

details.fold > summary:hover {
    color: var(--ink);
}

.fold-body {
    padding: 2px 0 14px;
}

details.fold-inline {
    margin: 0 0 10px;
}

details.fold-inline > summary {
    cursor: pointer;
    font-size: 0.81rem;
    color: var(--ink-muted);
    list-style-position: inside;
}

details.fold-inline > summary:hover {
    color: var(--ink);
}

details.fold-inline > p, details.fold-inline > div {
    margin: 6px 0 0;
    font-size: 0.82rem;
    color: var(--ink-secondary);
}

/* Booktabs Academic Tables (clean horizontal rules, no outer double-boxing) */
.table-scroll, .scroll, .table-container {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    background: var(--surface);
}

.table-container {
    max-height: 480px;
    overflow-y: auto;
    position: relative;
}

.table-container-limited {
    width: 100%;
    max-height: 380px;
    overflow-x: auto;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    background: var(--surface);
    position: relative;
}

.table-container-limited.expanded {
    max-height: none;
    overflow-y: visible;
}

table, .table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}

thead th, .table thead th {
    background: var(--surface);
    color: var(--ink-muted);
    font-weight: 600;
    font-size: 0.78rem;
    text-align: left;
    padding: 8px 10px;
    border-top: 1px solid var(--border-strong);
    border-bottom: 1px solid var(--border-strong);
    white-space: nowrap;
}

.table-container thead th, .table-container-limited thead th {
    position: sticky;
    top: 0;
    z-index: 15;
    background: var(--surface);
}

td, .table td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    color: var(--ink);
    text-align: left;
    vertical-align: top;
    overflow-wrap: anywhere;
    word-break: break-word;
}

tbody tr:last-child td {
    border-bottom: 1px solid var(--border-strong);
}

tbody tr:hover {
    background: var(--surface-hover);
}

tr.row-selected {
    background: var(--ok-bg);
}

tr.row-selected:hover {
    background: #e2f5ea;
}

/* Key-Value Table */
.kv {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
}

.kv td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    overflow-wrap: anywhere;
}

.kv tr:last-child td {
    border-bottom: none;
}

.kv td:first-child {
    width: 210px;
    color: var(--ink-muted);
    font-weight: 500;
    background: transparent;
}

/* Restrained Flat Badges */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 0.76rem;
    font-weight: 500;
    line-height: 1.35;
    border: 1px solid transparent;
    white-space: nowrap;
}

.badge-ok, .badge.success, .badge-yes, .badge-connected {
    background: var(--ok-bg);
    color: var(--ok-ink);
    border-color: var(--ok-border);
}

.badge-warn, .badge.warn, .badge-failed {
    background: var(--warn-bg);
    color: var(--warn-ink);
    border-color: var(--warn-border);
}

.badge-err, .badge.danger, .badge-no {
    background: var(--err-bg);
    color: var(--err-ink);
    border-color: var(--err-border);
}

.badge-info, .badge.info, .badge-direct, .badge-extension, .badge-selected, .badge-targeted {
    background: var(--accent-soft);
    color: var(--accent);
    border-color: var(--accent-border);
}

.badge-muted, .badge-na, .badge-not-targeted {
    background: var(--muted-bg);
    color: var(--muted-ink);
    border-color: var(--muted-border);
}

.badge-manual-review {
    background: var(--warn-bg);
    color: var(--warn-ink);
    border-color: var(--warn-border);
}

.empty-state {
    text-align: center;
    padding: 20px 14px;
    color: var(--ink-muted);
    font-size: 0.84rem;
}

.footer, .report-footer {
    margin-top: 16px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    color: var(--ink-muted);
    font-size: 0.78rem;
}

.footer p, .report-footer p { margin: 0; }
.footer p + p, .report-footer p + p { margin-top: 3px; }

/* Responsive */
.metrics-grid-six {
    grid-template-columns: repeat(3, minmax(0, 1fr));
}

@media (min-width: 1200px) {
    .metrics-grid-six { grid-template-columns: repeat(6, minmax(0, 1fr)); }
}

@media (max-width: 768px) {
    .metrics-grid-six { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .container, .report-shell {
        padding: 12px 12px 28px;
    }

    .header, .report-header {
        padding: 14px;
    }

    .header h1, .report-header h1 {
        font-size: 1.18rem;
    }

    .card-header, .section-header, .section-title {
        padding: 10px 14px;
    }

    .card-content, .section-body {
        padding: 12px 14px;
    }

    .fold-panel {
        padding: 2px 14px;
    }

    .metrics-grid, .stats-overview {
        grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
    }

    .kv td:first-child {
        width: 40%;
    }
}

/* Print */
@media print {
    body {
        background: #ffffff;
        color: #000000;
        font-size: 11pt;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }

    .container, .report-shell {
        max-width: none;
        padding: 0;
    }

    .header, .report-header, .card, .section, .fold-panel, .metric-card, .stat-card, .artifact-bar {
        box-shadow: none;
        border-color: #cbd5e1;
        break-inside: avoid;
    }

    .card, .section, .fold-panel {
        break-inside: auto;
    }

    .table-scroll, .scroll, .table-container, .table-container-limited {
        max-height: none !important;
        overflow: visible !important;
    }

    thead th, .table thead th {
        position: static !important;
    }

    .language-switcher, .table-toggle-container, .chrom-filter-icon, #trackLengthControl {
        display: none !important;
    }

    a {
        color: #111827;
        text-decoration: underline;
    }
}
"""


LANG_SWITCHER_JS = (
    "(function(){"
    "var r=document.documentElement;"
    "function set(l){l=l==='zh'?'zh':'en';r.setAttribute('data-lang',l);r.lang=l==='zh'?'zh-CN':'en';"
    "document.querySelectorAll('.language-btn[data-lang]').forEach(function(b){"
    "var a=b.getAttribute('data-lang')===l;b.classList.toggle('active',a);b.setAttribute('aria-pressed',a?'true':'false');});}"
    "document.addEventListener('click',function(e){"
    "var b=e.target&&e.target.closest?e.target.closest('.language-btn[data-lang]'):null;"
    "if(b)set(b.getAttribute('data-lang'));});"
    "})();"
)


def esc(value) -> str:
    """Escape dynamic text or HTML attribute values."""
    return escape(str(value), quote=True)


def bi(en: str, zh: str) -> str:
    """Render CSS-toggleable bilingual text so only one language is shown at a time."""
    return f'<span class="t-en">{esc(en)}</span><span class="t-zh">{esc(zh)}</span>'


def lang_switcher_html(default: str = "en") -> str:
    """Render a compact EN / 中文 switcher control."""
    en_cls = " active" if default != "zh" else ""
    zh_cls = " active" if default == "zh" else ""
    en_pressed = "true" if default != "zh" else "false"
    zh_pressed = "true" if default == "zh" else "false"
    return (
        '<div class="language-switcher" role="group" aria-label="Language Switcher">'
        f'<button type="button" class="language-btn{en_cls}" data-lang="en" aria-pressed="{en_pressed}">EN</button>'
        f'<button type="button" class="language-btn{zh_cls}" data-lang="zh" aria-pressed="{zh_pressed}">中文</button>'
        '</div>'
    )


def lang_switcher_js() -> str:
    """Return minimal inline script to toggle html[data-lang]."""
    return LANG_SWITCHER_JS


def summary_strip_html(items) -> str:
    """Render a compact single-row inline summary strip.

    Each item is (label_html, value_text, tone, note_text).
    """
    parts = []
    for item in items:
        label_html = item[0]
        value = item[1]
        tone = item[2] if len(item) > 2 else ""
        note = item[3] if len(item) > 3 else ""
        tone_cls = f" {tone}" if tone in ("accent", "ok", "warn", "err") else ""
        note_html = f'<span class="summary-strip-note mono">({esc(note)})</span>' if note else ""
        parts.append(
            '<span class="summary-strip-item">'
            f'<span class="summary-strip-label">{label_html}</span>'
            f'<span class="summary-strip-val{tone_cls}">{esc(value)}</span>'
            f'{note_html}'
            '</span>'
        )
    return f'<div class="summary-strip" role="group" aria-label="Summary metrics">{"".join(parts)}</div>'


def report_css(extra: str = "") -> str:
    """Return shared inline CSS combined with optional report-specific rules."""
    if not extra:
        return BASE_CSS.strip()
    return f"{BASE_CSS.strip()}\n\n{extra.strip()}"


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
    """Render a semantic status badge with escaped text."""
    safe_tone = tone if tone in ("ok", "warn", "err", "info", "muted") else "muted"
    return f'<span class="badge badge-{safe_tone}">{esc(label)}</span>'


def badge_bi(en: str, zh: str, tone: str = "muted") -> str:
    """Render a CSS-toggleable bilingual status badge."""
    safe_tone = tone if tone in ("ok", "warn", "err", "info", "muted") else "muted"
    return f'<span class="badge badge-{safe_tone}">{bi(en, zh)}</span>'
