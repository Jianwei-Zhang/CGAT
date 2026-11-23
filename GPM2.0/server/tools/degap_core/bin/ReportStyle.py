"""Shared offline presentation styles and HTML helpers for DEGAP reports.

Uses Python standard library only so generated HTML reports remain completely
self-contained, offline-readable, responsive, keyboard-accessible, and
print-friendly.
"""
from html import escape


BASE_CSS = """
:root {
    --bg: #f8fafc;
    --surface: #ffffff;
    --surface-subtle: #f1f5f9;
    --surface-hover: #f8fafc;
    --ink: #0f172a;
    --ink-secondary: #334155;
    --ink-muted: #64748b;
    --border: #e2e8f0;
    --border-strong: #cbd5e1;
    --accent: #0b6b7c;
    --accent-hover: #095563;
    --accent-soft: #eef7f9;
    --accent-border: #b8dde4;
    --ok-ink: #166534;
    --ok-bg: #f0fdf4;
    --ok-border: #bbf7d0;
    --warn-ink: #92400e;
    --warn-bg: #fffbeb;
    --warn-border: #fde68a;
    --err-ink: #991b1b;
    --err-bg: #fef2f2;
    --err-border: #fecaca;
    --muted-ink: #475569;
    --muted-bg: #f1f5f9;
    --muted-border: #cbd5e1;
    --radius-sm: 6px;
    --radius-md: 8px;
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
    --font-sans: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

*, *::before, *::after {
    box-sizing: border-box;
}

html {
    -webkit-text-size-adjust: 100%;
}

body {
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: var(--font-sans);
    font-size: 15px;
    line-height: 1.6;
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
}

code, .mono {
    font-family: var(--font-mono);
    font-size: 0.84em;
    overflow-wrap: anywhere;
    word-break: break-word;
}

code {
    background: var(--surface-subtle);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 5px;
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

.muted {
    color: var(--ink-muted);
}

.bilingual-zh {
    color: var(--ink-muted);
    font-weight: 400;
}

.container, .report-shell {
    max-width: 1140px;
    margin: 0 auto;
    padding: 24px 20px 48px;
}

/* Header */
.header, .report-header {
    background: var(--surface);
    border: 1px solid var(--border);
    border-top: 3px solid var(--accent);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    padding: 20px 24px;
    margin-bottom: 20px;
}

.header-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
}

.header-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
}

.report-eyebrow {
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--accent);
}

.header h1, .report-header h1 {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 650;
    line-height: 1.25;
    letter-spacing: -0.015em;
    color: var(--ink);
}

.header p, .report-header .report-subtitle, .header .sub {
    margin: 0;
    color: var(--ink-secondary);
    font-size: 0.93rem;
}

.header-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
    margin-top: 10px;
    font-size: 0.85rem;
    color: var(--ink-muted);
}

.header-badges, .badges {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 12px;
}

/* Language Switcher */
.language-switcher {
    display: inline-flex;
    align-items: center;
    background: var(--surface-subtle);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 2px;
    gap: 2px;
    flex-shrink: 0;
}

.language-btn {
    background: transparent;
    border: 1px solid transparent;
    color: var(--ink-secondary);
    padding: 5px 12px;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    transition: background-color 0.15s ease, color 0.15s ease;
    min-width: 44px;
}

.language-btn:hover {
    background: var(--surface);
    color: var(--ink);
}

.language-btn.active {
    background: var(--accent);
    color: #ffffff;
    border-color: var(--accent);
}

/* Metric Overview */
.metrics-grid, .stats-overview {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(175px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
}

.metric-card, .stat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    padding: 14px 16px;
    min-width: 0;
}

.metric-label, .stat-label {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--ink-muted);
    margin: 0 0 6px 0;
    line-height: 1.35;
}

.metric-value, .stat-value {
    font-size: 1.35rem;
    font-weight: 650;
    color: var(--ink);
    font-variant-numeric: tabular-nums;
    line-height: 1.25;
    overflow-wrap: anywhere;
    word-break: break-word;
}

.metric-value.accent {
    color: var(--accent);
}

.metric-value.ok, .stat-value.positive {
    color: var(--ok-ink);
}

.metric-value.warn {
    color: var(--warn-ink);
}

.metric-value.err, .stat-value.negative {
    color: var(--err-ink);
}

.metric-note {
    margin-top: 4px;
    font-size: 0.78rem;
    color: var(--ink-muted);
    overflow-wrap: anywhere;
}

/* Callout / Notice */
.notice {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius-sm);
    padding: 12px 16px;
    margin-bottom: 18px;
    font-size: 0.88rem;
    color: var(--ink-secondary);
}

.notice p {
    margin: 0;
}

.notice p + p {
    margin-top: 4px;
}

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

/* Artifact Download Links */
.artifact-bar {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    padding: 14px 18px;
    margin-bottom: 20px;
}

.artifact-bar-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--ink-muted);
    margin: 0 0 10px 0;
}

.artifact-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
}

.artifact-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: var(--surface-subtle);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--accent);
    font-size: 0.84rem;
    font-weight: 500;
    overflow-wrap: anywhere;
    transition: background-color 0.15s ease, border-color 0.15s ease;
}

.artifact-link:hover {
    background: var(--accent-soft);
    border-color: var(--accent-border);
    color: var(--accent-hover);
    text-decoration: none;
}

/* Cards & Sections */
.card, .section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-sm);
    margin-bottom: 20px;
    overflow: hidden;
}

.card-header, .section-header {
    background: var(--surface-subtle);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 0.98rem;
    font-weight: 600;
    color: var(--ink);
}

.section-header h2, .card-header h2 {
    margin: 0;
    font-size: 0.98rem;
    font-weight: 600;
    color: var(--ink);
}

.section-title {
    background: var(--surface-subtle);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    font-size: 0.98rem;
    font-weight: 600;
    color: var(--ink);
    margin: 0;
}

.card-content, .section-body {
    padding: 16px 20px;
}

.section-note {
    margin: 0 0 12px 0;
    font-size: 0.86rem;
    color: var(--ink-secondary);
}

/* Tables */
.table-scroll, .scroll, .table-container {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface);
}

.table-container {
    max-height: 520px;
    overflow-y: auto;
    position: relative;
}

.table-container-limited {
    width: 100%;
    max-height: 400px;
    overflow-x: auto;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
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
    font-size: 0.875rem;
}

thead th, .table thead th {
    background: var(--surface-subtle);
    color: var(--ink-secondary);
    font-weight: 600;
    font-size: 0.8rem;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border-strong);
    white-space: nowrap;
}

.table-container thead th, .table-container-limited thead th {
    position: sticky;
    top: 0;
    z-index: 15;
}

td, .table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    color: var(--ink);
    text-align: left;
    vertical-align: top;
    overflow-wrap: anywhere;
    word-break: break-word;
}

tbody tr:last-child td {
    border-bottom: none;
}

tbody tr:hover {
    background: var(--surface-hover);
}

tr.row-selected {
    background: var(--ok-bg);
}

tr.row-selected:hover {
    background: #dcfce7;
}

/* Key-Value Table */
.kv {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}

.kv td {
    padding: 9px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    overflow-wrap: anywhere;
}

.kv tr:last-child td {
    border-bottom: none;
}

.kv td:first-child {
    width: 230px;
    color: var(--ink-secondary);
    font-weight: 600;
    background: var(--surface-subtle);
}

/* Badges (text + color + subtle indicator dot) */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.4;
    border: 1px solid transparent;
    white-space: nowrap;
}

.badge::before {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
    flex-shrink: 0;
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
    padding: 28px 16px;
    color: var(--ink-muted);
    font-size: 0.88rem;
}

.footer, .report-footer {
    margin-top: 24px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
    color: var(--ink-muted);
    font-size: 0.82rem;
}

.footer p, .report-footer p {
    margin: 0;
}

.footer p + p, .report-footer p + p {
    margin-top: 4px;
}

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
        padding: 14px 12px 32px;
    }

    .header, .report-header {
        padding: 16px;
    }

    .header h1, .report-header h1 {
        font-size: 1.28rem;
    }

    .card-header, .section-header, .section-title {
        padding: 10px 14px;
    }

    .card-content, .section-body {
        padding: 12px 14px;
    }

    .metrics-grid, .stats-overview {
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
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

    .header, .report-header, .card, .section, .metric-card, .stat-card, .artifact-bar {
        box-shadow: none;
        border-color: #cbd5e1;
        break-inside: avoid;
    }

    .card, .section {
        break-inside: auto;
    }

    .table-scroll, .scroll, .table-container, .table-container-limited {
        max-height: none !important;
        overflow: visible !important;
        border-color: #cbd5e1;
    }

    thead th, .table thead th {
        position: static !important;
    }

    .language-switcher, .table-toggle-container, .chrom-filter-icon, #trackLengthControl {
        display: none !important;
    }

    a {
        color: #0f172a;
        text-decoration: underline;
    }
}
"""


def esc(value) -> str:
    """Escape dynamic text or HTML attribute values."""
    return escape(str(value), quote=True)


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
    """Render a semantic status pill with escaped text."""
    safe_tone = tone if tone in ("ok", "warn", "err", "info", "muted") else "muted"
    return f'<span class="badge badge-{safe_tone}">{esc(label)}</span>'
