"""Shared offline presentation styles and HTML helpers for DEGAP reports.

Uses Python standard library only so generated HTML reports remain completely
self-contained, offline-readable, responsive, keyboard-accessible, and
print-friendly.
"""
from html import escape


BASE_CSS = """
:root {
    color-scheme: light;
    --surface-app: #f7f8fa;
    --surface-panel: #ffffff;
    --surface-header: rgba(255, 255, 255, 0.92);
    --surface-subtle: #f9fafb;
    --surface-muted: #f1f3f5;
    --surface-hover: #eef1f4;
    --border-subtle: #e5e7eb;
    --border-default: #d1d5db;
    --border-strong: #9ca3af;
    --text-primary: #111827;
    --text-secondary: #374151;
    --text-muted: #6b7280;
    --brand: #1d3557;
    --brand-soft: #eef3f8;
    --accent: #1e4e79;
    --accent-hover: #1d3557;
    --accent-soft: #eef3f8;
    --accent-border: #b6cce6;
    --focus-ring: #2563eb;
    --action-primary: #1d3557;
    --gen-closed: #2b7a57;
    --gen-partial: #356ea8;
    --gen-unfilled: #cbd5e1;
    --gen-gap: #b91c1c;
    --ds-0: #335c81;
    --ds-1: #2a7b76;
    --ds-2: #5e548e;
    --ds-3: #b07d3b;
    --ds-4: #9e4765;
    --ds-5: #4a6fa5;
    --tone-ok-ink: #1b5e3c;
    --tone-ok-bg: #f0f8f4;
    --tone-ok-line: #a7d7be;
    --tone-warn-ink: #854d0e;
    --tone-warn-bg: #fdf9ed;
    --tone-warn-line: #e2c275;
    --tone-err-ink: #991b1b;
    --tone-err-bg: #fdf2f2;
    --tone-err-line: #e5a4a4;
    --tone-info-ink: #1e4273;
    --tone-info-bg: #f2f6fb;
    --tone-info-line: #b6cce6;
    --tone-neutral-ink: #4b5563;
    --tone-neutral-bg: #f3f4f6;
    --tone-neutral-line: #d1d5db;
    /* Legacy aliases preserved for sub-reports */
    --bg: var(--surface-app);
    --surface: var(--surface-panel);
    --ink: var(--text-primary);
    --ink-secondary: var(--text-secondary);
    --ink-muted: var(--text-muted);
    --border: var(--border-subtle);
    --ok-ink: var(--tone-ok-ink);
    --ok-bg: var(--tone-ok-bg);
    --ok-border: var(--tone-ok-line);
    --warn-ink: var(--tone-warn-ink);
    --warn-bg: var(--tone-warn-bg);
    --warn-border: var(--tone-warn-line);
    --err-ink: var(--tone-err-ink);
    --err-bg: var(--tone-err-bg);
    --err-border: var(--tone-err-line);
    --muted-ink: var(--tone-neutral-ink);
    --muted-bg: var(--tone-neutral-bg);
    --muted-border: var(--tone-neutral-line);
    --radius: 6px;
    --radius-sm: 4px;
    --radius-md: 6px;
    --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.03);
    --text-page: 15px;
    --text-card: 15px;
    --text-sub: 13px;
    --text-body: 13px;
    --text-sm: 12px;
    --text-xs: 11px;
    --svg-kpi: 12px;
    --svg-label: 9.5px;
    --svg-micro: 8.5px;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    --font-mono: ui-monospace, "SFMono-Regular", "Cascadia Code", Consolas, monospace;
}

html[data-theme="dark"] {
    color-scheme: dark;
    --surface-app: #0f1419;
    --surface-panel: #151c24;
    --surface-header: rgba(21, 28, 36, 0.92);
    --surface-subtle: #1b242e;
    --surface-muted: #222d3a;
    --surface-hover: #273444;
    --border-subtle: #263240;
    --border-default: #344354;
    --border-strong: #5b6e82;
    --text-primary: #edf2f7;
    --text-secondary: #c4d0dc;
    --text-muted: #8a99aa;
    --brand: #7da4d4;
    --brand-soft: #1b2a3c;
    --accent: #8cb4e6;
    --accent-hover: #a8c8f0;
    --accent-soft: #1b2a3c;
    --accent-border: #375a82;
    --focus-ring: #93c5fd;
    --action-primary: #7da4d4;
    --gen-closed: #3ea374;
    --gen-partial: #5c98d4;
    --gen-unfilled: #475569;
    --gen-gap: #dc5964;
    --ds-0: #5585b5;
    --ds-1: #3f9e98;
    --ds-2: #8b7ec2;
    --ds-3: #cc9852;
    --ds-4: #c26e8a;
    --ds-5: #6890c4;
    --tone-ok-ink: #8dd3ad;
    --tone-ok-bg: #152920;
    --tone-ok-line: #2f684c;
    --tone-warn-ink: #e8c97a;
    --tone-warn-bg: #2a2315;
    --tone-warn-line: #80642b;
    --tone-err-ink: #f2a2a2;
    --tone-err-bg: #2f191d;
    --tone-err-line: #843e46;
    --tone-info-ink: #9ec0e6;
    --tone-info-bg: #172638;
    --tone-info-line: #375a82;
    --tone-neutral-ink: #b6c2cf;
    --tone-neutral-bg: #202b37;
    --tone-neutral-line: #364556;
}

@media (prefers-color-scheme: dark) {
    html:not([data-theme="light"]) {
        color-scheme: dark;
        --surface-app: #0f1419;
        --surface-panel: #151c24;
        --surface-header: rgba(21, 28, 36, 0.92);
        --surface-subtle: #1b242e;
        --surface-muted: #222d3a;
        --surface-hover: #273444;
        --border-subtle: #263240;
        --border-default: #344354;
        --border-strong: #5b6e82;
        --text-primary: #edf2f7;
        --text-secondary: #c4d0dc;
        --text-muted: #8a99aa;
        --brand: #7da4d4;
        --brand-soft: #1b2a3c;
        --accent: #8cb4e6;
        --accent-hover: #a8c8f0;
        --accent-soft: #1b2a3c;
        --accent-border: #375a82;
        --focus-ring: #93c5fd;
        --action-primary: #7da4d4;
        --gen-closed: #3ea374;
        --gen-partial: #5c98d4;
        --gen-unfilled: #475569;
        --gen-gap: #dc5964;
        --ds-0: #5585b5;
        --ds-1: #3f9e98;
        --ds-2: #8b7ec2;
        --ds-3: #cc9852;
        --ds-4: #c26e8a;
        --ds-5: #6890c4;
        --tone-ok-ink: #8dd3ad;
        --tone-ok-bg: #152920;
        --tone-ok-line: #2f684c;
        --tone-warn-ink: #e8c97a;
        --tone-warn-bg: #2a2315;
        --tone-warn-line: #80642b;
        --tone-err-ink: #f2a2a2;
        --tone-err-bg: #2f191d;
        --tone-err-line: #843e46;
        --tone-info-ink: #9ec0e6;
        --tone-info-bg: #172638;
        --tone-info-line: #375a82;
        --tone-neutral-ink: #b6c2cf;
        --tone-neutral-bg: #202b37;
        --tone-neutral-line: #364556;
    }
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
    max-width: 1200px;
    margin: 0 auto;
    padding: 18px 20px 44px;
}

/* Sticky Single-Row Topbar (aligned with CGAT Server Report) */
.degap-topbar {
    position: sticky;
    top: 0;
    z-index: 40;
    background: var(--surface-panel);
    background: var(--surface-header);
    backdrop-filter: saturate(180%) blur(10px);
    -webkit-backdrop-filter: saturate(180%) blur(10px);
    border-bottom: 1px solid var(--border-subtle);
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
}

.degap-topbar-inner {
    max-width: 1200px;
    margin: 0 auto;
    min-height: 48px;
    padding: 7px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px 18px;
}

.degap-topbar-left {
    display: flex;
    align-items: center;
    gap: 9px;
    min-width: 0;
    flex: 1 1 auto;
}

.degap-brand-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.degap-topbar h1 {
    margin: 0;
    display: inline-flex;
    align-items: baseline;
    gap: 2px;
    min-width: 0;
    font-size: var(--text-page);
    font-weight: 700;
    line-height: 1.3;
    letter-spacing: -0.01em;
    color: var(--text-primary);
}

.degap-heading-prefix {
    font-weight: 600;
    color: var(--text-secondary);
    white-space: nowrap;
    flex-shrink: 0;
}

.degap-heading-project {
    font-weight: 700;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
}

.degap-topbar-right {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    flex-shrink: 0;
}

.degap-time {
    font-size: var(--text-xs);
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
}

.hdr-sep {
    display: inline-block;
    width: 1px;
    height: 14px;
    background: var(--border-default);
    opacity: 0.7;
    flex-shrink: 0;
}

.theme-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border-radius: 6px;
    border: 1px solid var(--border-subtle);
    background: var(--surface-panel);
    color: var(--text-secondary);
    cursor: pointer;
    transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}

.theme-btn:hover {
    background: var(--surface-hover);
    border-color: var(--border-default);
    color: var(--text-primary);
}

.theme-btn .ico-sun { display: none; }
.theme-btn .ico-moon { display: block; }
html[data-theme="dark"] .theme-btn .ico-moon { display: none; }
html[data-theme="dark"] .theme-btn .ico-sun { display: block; }
@media (prefers-color-scheme: dark) {
    html:not([data-theme="light"]) .theme-btn .ico-moon { display: none; }
    html:not([data-theme="light"]) .theme-btn .ico-sun { display: block; }
}

/* Input Dataset Table & Aux Tags (aligned with CGAT 01 Input Data) */
.dataset-scroll {
    overflow-x: auto;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface);
}

.dataset-table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-sm);
    text-align: left;
}

.dataset-table th, .dataset-table td {
    padding: 9px 12px;
    border-top: 0;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
}

.dataset-table thead th {
    background: var(--surface-subtle);
    color: var(--ink-secondary);
    font-size: var(--text-xs);
    font-weight: 600;
    white-space: nowrap;
    border-bottom: 1px solid var(--border);
}

.dataset-table tbody tr:last-child td {
    border-bottom: 0;
}

.dataset-name {
    font-family: var(--font-mono);
    font-weight: 600;
    color: var(--ink);
    overflow-wrap: anywhere;
}

.dataset-role {
    display: inline-flex;
    align-items: center;
    padding: 2px 9px;
    border-radius: 999px;
    border: 1px solid var(--accent-border);
    background: var(--accent-soft);
    color: var(--accent);
    font-size: var(--text-xs);
    font-weight: 500;
    line-height: 1.35;
    white-space: nowrap;
}

.dataset-role.is-reads {
    border-color: var(--ok-border);
    background: var(--ok-bg);
    color: var(--ok-ink);
}

.input-aux-bar {
    display: flex;
    align-items: center;
    gap: 6px 8px;
    flex-wrap: wrap;
    margin-top: 10px;
}

.input-aux-tag {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 10px;
    border: 1px solid var(--border);
    border-radius: 999px;
    background: var(--surface-subtle);
    color: var(--ink-secondary);
    font-size: var(--text-xs);
    font-weight: 500;
    line-height: 1.35;
    white-space: nowrap;
}

.input-aux-tag b {
    color: var(--ink);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

/* Header */
.header, .report-header {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-xs);
    padding: 16px 20px;
    margin-bottom: 14px;
}

.card-num {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 1px 6px;
    border-radius: 3px;
    background: var(--brand-soft);
    color: var(--brand);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    line-height: 1.3;
    flex-shrink: 0;
}

a[aria-disabled="true"] {
    display: inline-flex;
    align-items: center;
    padding: 3px 9px;
    border-radius: var(--radius-sm);
    background: var(--surface-muted);
    border: 1px solid var(--border);
    color: var(--ink-muted);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    text-decoration: none;
    cursor: default;
    pointer-events: none;
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

/* Language Switcher (aligned with CGAT .seg-ctrl) */
.language-switcher {
    display: inline-flex;
    align-items: center;
    height: 28px;
    background: var(--surface-muted);
    border: 1px solid var(--border-subtle);
    border-radius: 6px;
    padding: 2px;
    gap: 1px;
    flex-shrink: 0;
}

.language-btn {
    height: 22px;
    background: transparent;
    border: 0;
    color: var(--text-secondary);
    padding: 0 9px;
    border-radius: 4px;
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.12s ease, color 0.12s ease;
    min-width: 34px;
}

.language-btn:hover:not(.active) {
    background: var(--surface-hover);
    color: var(--text-primary);
}

.language-btn.active {
    background: var(--surface-panel);
    color: var(--brand);
    font-weight: 650;
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
    box-shadow: var(--shadow-xs);
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
    font-size: var(--text-card);
    font-weight: 600;
    color: var(--ink);
}

.section-header h2, .card-header h2 {
    margin: 0;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-card);
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
    box-shadow: var(--shadow-xs);
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

    .degap-topbar {
        position: static;
        box-shadow: none;
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

DEGAP_LOGO_DATA_URI = (
    "data:image/png;base64,"
    "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"
)


def degap_logo_html(size: int = 24) -> str:
    """Return the official DEGAP circular emblem as an offline inline PNG icon."""
    return (
        '<span class="degap-brand-icon" aria-hidden="true">'
        f'<img src="{DEGAP_LOGO_DATA_URI}" alt="DEGAP" width="{int(size)}" height="{int(size)}" '
        'style="display:block;border-radius:50%;object-fit:contain;">'
        '</span>'
    )
