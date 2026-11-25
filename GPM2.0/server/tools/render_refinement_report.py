"""Pure offline HTML renderers and shared CGAT formal report UI kit.

Restrained publication-grade styling, zero workspace access, zero external
requests, strict CSP, and progressive-enhancement inline controls.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

try:
    from refinement_degap_units import terminal as degap_child_terminal
    from workspace_layout import TOOL_DIRECTORIES
except ModuleNotFoundError:
    from .refinement_degap_units import terminal as degap_child_terminal
    from .workspace_layout import TOOL_DIRECTORIES

PAGE_SIZE = 200

REPORT_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
)

# Desaturated scientific data palette
DATASET_COLORS = ("#335c81", "#2a7b76", "#5e548e", "#b07d3b", "#9e4765", "#4a6fa5")

CSS = """
:root{
  color-scheme:light;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  font-size:14px;
  --font-mono:ui-monospace,"SFMono-Regular","Cascadia Code",Consolas,monospace;
  --radius:6px;
  --radius-sm:4px;
  --surface-app:#f7f8fa;
  --surface-panel:#ffffff;
  --surface-header:rgba(255,255,255,.92);
  --surface-subtle:#f9fafb;
  --surface-muted:#f1f3f5;
  --surface-hover:#eef1f4;
  --border-subtle:#e5e7eb;
  --border-default:#d1d5db;
  --border-strong:#9ca3af;
  --text-primary:#111827;
  --text-secondary:#374151;
  --text-muted:#6b7280;
  --brand:#1d3557;
  --brand-soft:#eef3f8;
  --accent:#1e4e79;
  --focus-ring:#2563eb;
  --tone-ok-ink:#1b5e3c;--tone-ok-bg:#f0f8f4;--tone-ok-line:#a7d7be;
  --tone-warn-ink:#854d0e;--tone-warn-bg:#fdf9ed;--tone-warn-line:#e2c275;
  --tone-err-ink:#991b1b;--tone-err-bg:#fdf2f2;--tone-err-line:#e5a4a4;
  --tone-info-ink:#1e4273;--tone-info-bg:#f2f6fb;--tone-info-line:#b6cce6;
  --tone-neutral-ink:#4b5563;--tone-neutral-bg:#f3f4f6;--tone-neutral-line:#d1d5db;
  --gen-closed:#2b7a57;--gen-partial:#356ea8;--gen-unfilled:#cbd5e1;--gen-rejected:#b91c1c;--gen-na:#e2e8f0;
  --gen-patch:#c97a2b;--gen-gap:#b91c1c;--gen-tel:#2b7a57;--gen-cen:#6d4c9c;
  --ds-0:#335c81;--ds-1:#2a7b76;--ds-2:#5e548e;--ds-3:#b07d3b;--ds-4:#9e4765;--ds-5:#4a6fa5;
}
html[data-theme="dark"]{
  color-scheme:dark;
  --surface-app:#0f1419;
  --surface-panel:#151c24;
  --surface-header:rgba(21,28,36,.92);
  --surface-subtle:#1b242e;
  --surface-muted:#222d3a;
  --surface-hover:#273444;
  --border-subtle:#263240;
  --border-default:#344354;
  --border-strong:#5b6e82;
  --text-primary:#edf2f7;
  --text-secondary:#c4d0dc;
  --text-muted:#8a99aa;
  --brand:#7da4d4;
  --brand-soft:#1b2a3c;
  --accent:#8cb4e6;
  --focus-ring:#93c5fd;
  --tone-ok-ink:#8dd3ad;--tone-ok-bg:#152920;--tone-ok-line:#2f684c;
  --tone-warn-ink:#e8c97a;--tone-warn-bg:#2a2315;--tone-warn-line:#80642b;
  --tone-err-ink:#f2a2a2;--tone-err-bg:#2f191d;--tone-err-line:#843e46;
  --tone-info-ink:#9ec0e6;--tone-info-bg:#172638;--tone-info-line:#375a82;
  --tone-neutral-ink:#b6c2cf;--tone-neutral-bg:#202b37;--tone-neutral-line:#364556;
  --gen-closed:#3ea374;--gen-partial:#5c98d4;--gen-unfilled:#475569;--gen-rejected:#dc5964;--gen-na:#334155;
  --gen-patch:#dfa048;--gen-gap:#dc5964;--gen-tel:#43b37d;--gen-cen:#9e82cc;
  --ds-0:#5585b5;--ds-1:#3f9e98;--ds-2:#8b7ec2;--ds-3:#cc9852;--ds-4:#c26e8a;--ds-5:#6890c4;
}
@media (prefers-color-scheme:dark){
  html:not([data-theme="light"]){
    color-scheme:dark;
    --surface-app:#0f1419;
    --surface-panel:#151c24;
    --surface-header:rgba(21,28,36,.92);
    --surface-subtle:#1b242e;
    --surface-muted:#222d3a;
    --surface-hover:#273444;
    --border-subtle:#263240;
    --border-default:#344354;
    --border-strong:#5b6e82;
    --text-primary:#edf2f7;
    --text-secondary:#c4d0dc;
    --text-muted:#8a99aa;
    --brand:#7da4d4;
    --brand-soft:#1b2a3c;
    --accent:#8cb4e6;
    --focus-ring:#93c5fd;
    --tone-ok-ink:#8dd3ad;--tone-ok-bg:#152920;--tone-ok-line:#2f684c;
    --tone-warn-ink:#e8c97a;--tone-warn-bg:#2a2315;--tone-warn-line:#80642b;
    --tone-err-ink:#f2a2a2;--tone-err-bg:#2f191d;--tone-err-line:#843e46;
    --tone-info-ink:#9ec0e6;--tone-info-bg:#172638;--tone-info-line:#375a82;
    --tone-neutral-ink:#b6c2cf;--tone-neutral-bg:#202b37;--tone-neutral-line:#364556;
    --gen-closed:#3ea374;--gen-partial:#5c98d4;--gen-unfilled:#475569;--gen-rejected:#dc5964;--gen-na:#334155;
    --gen-patch:#dfa048;--gen-gap:#dc5964;--gen-tel:#43b37d;--gen-cen:#9e82cc;
    --ds-0:#5585b5;--ds-1:#3f9e98;--ds-2:#8b7ec2;--ds-3:#cc9852;--ds-4:#c26e8a;--ds-5:#6890c4;
  }
}
html[data-lang="zh"] .t-en{display:none!important}
html[data-lang="en"] .t-zh{display:none!important}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--surface-app);color:var(--text-primary);line-height:1.55;font-size:14px;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
a:focus-visible,summary:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--focus-ring);outline-offset:2px;border-radius:3px}
code,pre{font-family:var(--font-mono)}
code{font-size:.86em;overflow-wrap:anywhere;background:var(--surface-muted);color:var(--text-primary);padding:.1em .34em;border-radius:3px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:.8rem .95rem;margin:.5rem 0;font-size:12px;line-height:1.48;max-height:400px;overflow:auto}
h1,h2,h3,h4,p{margin:0}
h1{font-size:1.38rem;line-height:1.3;font-weight:600;letter-spacing:-.015em;color:var(--text-primary)}
h2{font-size:1.05rem;line-height:1.35;font-weight:600;color:var(--text-primary)}
h3{font-size:.92rem;line-height:1.4;font-weight:600;color:var(--text-secondary);margin:.9rem 0 .45rem}
p{margin:.38rem 0}
small,.muted{color:var(--text-muted);font-size:.84rem}
.num{font-variant-numeric:tabular-nums}
.is-hidden{display:none!important}

/* Sticky Single-Row Topbar Header */
.cgat-header{position:sticky;top:0;z-index:40;background:var(--surface-panel);background:var(--surface-header);backdrop-filter:saturate(180%) blur(10px);-webkit-backdrop-filter:saturate(180%) blur(10px);border-top:2.5px solid var(--brand);border-bottom:1px solid var(--border-subtle);box-shadow:0 1px 2px rgba(15,23,42,.03)}
.cgat-header-inner{max-width:1280px;margin:0 auto;min-height:48px;padding:.46rem 1.5rem;display:flex;flex-direction:column;justify-content:center}
.cgat-header.is-centered .cgat-header-inner{max-width:1140px}
.cgat-title-row{display:flex;align-items:center;justify-content:space-between;gap:.75rem 1.25rem;min-width:0}
.cgat-title-left{display:flex;align-items:center;gap:.55rem;min-width:0;flex:1 1 auto}
.cgat-brand-icon{display:inline-flex;align-items:center;justify-content:center;color:var(--brand);flex-shrink:0}
.cgat-brand{display:inline-flex;align-items:center;gap:.42rem;font-size:.86rem;font-weight:700;letter-spacing:.02em;color:var(--brand);white-space:nowrap}
.cgat-brand svg{flex-shrink:0}
.cgat-sep{display:inline-block;width:1px;height:16px;background:var(--border-default);flex-shrink:0}
.cgat-title-group{display:inline-flex;align-items:baseline;gap:.5rem;min-width:0;max-width:100%}
.cgat-title-group h1{display:inline-flex;align-items:baseline;min-width:0;font-size:1.02rem;font-weight:700;letter-spacing:-.01em;line-height:1.3}
.cgat-heading-prefix{font-weight:600;color:var(--text-secondary);white-space:nowrap;flex-shrink:0}
.cgat-heading-project{font-weight:700;font-size:1.05rem;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.cgat-doc-role{font-size:.86rem;font-weight:500;color:var(--text-muted);white-space:nowrap}
.cgat-subtitle{margin-top:.28rem;color:var(--text-muted);font-size:.82rem;display:flex;flex-wrap:wrap;gap:.35rem .7rem;align-items:center}
.wb-controls{display:inline-flex;align-items:center;gap:.55rem;flex-shrink:0}
.cgat-time{font-size:.8rem;color:var(--text-muted);font-variant-numeric:tabular-nums;letter-spacing:.01em;white-space:nowrap}
.hdr-sep{display:inline-block;width:1px;height:14px;background:var(--border-default);opacity:.7;flex-shrink:0}
.seg-ctrl{display:inline-flex;align-items:center;height:28px;padding:2px;gap:1px;border-radius:6px;background:var(--surface-muted);border:1px solid var(--border-subtle)}
.seg-ctrl .ctrl-btn{height:22px;border:0;background:transparent;padding:0 .54rem;border-radius:4px;font-size:12px;font-weight:500;color:var(--text-secondary)}
.seg-ctrl .ctrl-btn:hover:not(.is-active){background:var(--surface-hover);color:var(--text-primary)}
.seg-ctrl .ctrl-btn.is-active{background:var(--surface-panel);color:var(--brand);font-weight:650;box-shadow:0 1px 2px rgba(15,23,42,.08)}
.ctrl-btn{display:inline-flex;align-items:center;justify-content:center;gap:.28rem;padding:.24rem .58rem;border-radius:var(--radius-sm);border:1px solid var(--border-subtle);background:var(--surface-panel);color:var(--text-muted);font:500 12px/1.3 inherit;cursor:pointer;white-space:nowrap;transition:background .12s,border-color .12s,color .12s}
.ctrl-btn:hover{background:var(--surface-subtle);border-color:var(--border-default);color:var(--text-primary)}
.ctrl-btn.is-active{background:var(--surface-muted);border-color:var(--border-default);color:var(--text-primary);font-weight:600}
.theme-btn{width:28px;height:28px;padding:0;border-radius:6px;color:var(--text-secondary)}
.theme-btn:hover{background:var(--surface-hover);border-color:var(--border-default);color:var(--text-primary)}
.theme-btn .ico-sun{display:none}
.theme-btn .ico-moon{display:block}
html[data-theme="dark"] .theme-btn .ico-moon{display:none}
html[data-theme="dark"] .theme-btn .ico-sun{display:block}
@media (prefers-color-scheme:dark){
  html:not([data-theme="light"]) .theme-btn .ico-moon{display:none}
  html:not([data-theme="light"]) .theme-btn .ico-sun{display:block}
}
.cgat-nav{display:flex;flex-wrap:wrap;gap:.45rem;margin-top:.45rem;padding-top:.45rem;border-top:1px solid var(--border-subtle);align-items:center}
.cgat-nav a{font-size:.84rem;color:var(--text-secondary);padding:.18rem .48rem;border-radius:var(--radius-sm)}
.cgat-nav a:hover{background:var(--surface-subtle);color:var(--text-primary);text-decoration:none}

/* Clean Frameless-Sidebar / Centered Single-Column Layout */
.wb-shell{max-width:1280px;margin:0 auto;padding:1.25rem 1.5rem 2.5rem;display:grid;grid-template-columns:184px minmax(0,1fr);gap:1.65rem;align-items:start}
.wb-shell.no-sidebar{display:block;max-width:1140px}
.wb-sidebar{position:sticky;top:66px;padding-top:.15rem}
.wb-toc{list-style:none;margin:0;padding:0;border-left:1px solid var(--border-subtle);display:flex;flex-direction:column;gap:.12rem}
.wb-toc a{display:flex;align-items:baseline;gap:.42rem;padding:.34rem .72rem;margin-left:-1px;border-left:2px solid transparent;color:var(--text-muted);font-size:.83rem;font-weight:500;line-height:1.35;transition:color .12s,border-color .12s,background .12s;border-radius:0 var(--radius-sm) var(--radius-sm) 0}
.wb-toc a:hover{color:var(--text-primary);background:var(--surface-hover);text-decoration:none}
.wb-toc a.is-current{color:var(--brand);border-left-color:var(--brand);background:var(--brand-soft);font-weight:600}
.toc-num{display:inline-block;min-width:1.45rem;font:600 .74rem/1 var(--font-mono);color:var(--text-muted);font-variant-numeric:tabular-nums;flex-shrink:0}
.wb-toc a.is-current .toc-num{color:var(--brand)}
.cgat-main{min-width:0;display:flex;flex-direction:column;gap:1.1rem}

/* Crisp Paper Panels & Shared Story Kit */
.panel{background:var(--surface-panel);border:1px solid var(--border-subtle);border-radius:var(--radius);padding:1.1rem 1.35rem;min-width:0;scroll-margin-top:66px;box-shadow:0 1px 2px rgba(15,23,42,.03)}
.panel.is-alert{border-color:var(--tone-err-line)}
.panel-head{display:flex;align-items:baseline;justify-content:space-between;gap:.75rem;flex-wrap:wrap;margin-bottom:.8rem;padding-bottom:.55rem;border-bottom:1px solid var(--border-subtle)}
.panel-head-right{font-size:.82rem;color:var(--text-muted);font-weight:500;display:inline-flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.story-head h2{display:inline-flex;align-items:baseline;gap:.5rem;flex-wrap:wrap;font-size:1.06rem;font-weight:650;letter-spacing:-.01em}
.story-num{display:inline-flex;align-items:center;padding:.08rem .38rem;border-radius:3px;background:var(--brand-soft);color:var(--brand);font:600 .76rem/1.3 var(--font-mono);font-variant-numeric:tabular-nums;letter-spacing:0}
.story-sub{font-size:.82rem;font-weight:500;color:var(--text-muted)}
.story-toolbar{display:flex;align-items:center;justify-content:space-between;gap:.5rem 1rem;flex-wrap:wrap;margin:0 0 .55rem;font-size:.81rem;color:var(--text-secondary)}
.story-scale-row{display:grid;grid-template-columns:148px minmax(0,1fr);gap:.75rem;align-items:end;padding:0 0 .28rem;margin-bottom:.15rem;border-bottom:1px solid var(--border-subtle);color:var(--text-muted);font-size:.76rem}
.story-ruler{position:relative;display:flex;justify-content:space-between;font-variant-numeric:tabular-nums;padding-bottom:4px}
.story-ruler span{position:relative;line-height:1.1}
.story-ruler span::after{content:"";position:absolute;left:50%;bottom:-5px;width:1px;height:4px;background:var(--border-strong)}
.story-ruler span:first-child::after{left:0}
.story-ruler span:last-child::after{left:auto;right:0}
.story-foot{margin:.6rem 0 0;padding-top:.45rem;border-top:1px dashed var(--border-subtle);color:var(--text-muted);font-size:.79rem;line-height:1.45}
.swatch.is-orig-gap{background:repeating-linear-gradient(135deg,var(--border-strong) 0 2px,var(--surface-panel) 2px 4.5px);border:1px solid var(--border-strong)}
.swatch.is-unk-gap{background:repeating-linear-gradient(135deg,var(--gen-gap) 0 2.5px,var(--surface-panel) 2.5px 5px);border:1px solid var(--gen-gap)}
.num-col{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}

/* Subtle Formal Status Indicators */
.badge{display:inline-flex;align-items:center;gap:.35rem;padding:.12rem .5rem;border-radius:3px;font-size:.78rem;font-weight:500;line-height:1.35;border:1px solid transparent;white-space:nowrap}
.tone-ok{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border-color:var(--tone-ok-line)}
.tone-warn{color:var(--tone-warn-ink);background:var(--tone-warn-bg);border-color:var(--tone-warn-line)}
.tone-err{color:var(--tone-err-ink);background:var(--tone-err-bg);border-color:var(--tone-err-line)}
.tone-info{color:var(--tone-info-ink);background:var(--tone-info-bg);border-color:var(--tone-info-line)}
.tone-neutral{color:var(--tone-neutral-ink);background:var(--tone-neutral-bg);border-color:var(--tone-neutral-line)}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;flex-shrink:0}
.dot.ok{background:var(--gen-closed)}.dot.warn{background:var(--gen-patch)}.dot.err{background:var(--gen-gap)}.dot.info{background:var(--brand)}.dot.neutral{background:var(--border-strong)}

.callout,.note{border-left:2px solid var(--tone-warn-line);background:var(--tone-warn-bg);color:var(--text-primary);padding:.58rem .85rem;border-radius:0 var(--radius-sm) var(--radius-sm) 0;margin:.5rem 0;font-size:.86rem}
.callout.tone-info{border-left-color:var(--tone-info-line);background:var(--tone-info-bg)}
.callout.tone-ok{border-left-color:var(--tone-ok-line);background:var(--tone-ok-bg)}
.callout.tone-err{border-left-color:var(--tone-err-line);background:var(--tone-err-bg)}
.callout.tone-neutral{border-left-color:var(--border-default);background:var(--surface-subtle)}
.callout-title{font-weight:600;margin-bottom:.15rem}

/* Minimal Pipeline Locator Bar */
.flow-strip{display:flex;align-items:center;gap:.35rem;flex-wrap:wrap;padding:.15rem 0}
.flow-node{display:inline-flex;align-items:center;gap:.4rem;padding:.32rem .7rem;border-radius:var(--radius-sm);border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-primary);font-size:.84rem;font-weight:500;text-decoration:none}
.flow-node:hover{border-color:var(--border-default);background:var(--surface-hover);text-decoration:none}
.flow-node.tone-err{border-color:var(--tone-err-line);background:var(--tone-err-bg);color:var(--tone-err-ink)}
.flow-node.tone-warn{border-color:var(--tone-warn-line);background:var(--tone-warn-bg);color:var(--tone-warn-ink)}
.flow-arrow{color:var(--border-strong);font-size:.85rem;user-select:none}

/* Inline Summary Strips & Grids */
.summary-line{display:flex;flex-wrap:wrap;gap:.4rem 1.25rem;align-items:baseline;font-size:.88rem;color:var(--text-secondary);margin:0 0 .75rem}
.summary-line b{color:var(--text-primary);font-weight:600;font-variant-numeric:tabular-nums}
.compact-strip{display:flex;flex-wrap:wrap;gap:.35rem .8rem;align-items:center;font-size:.84rem;color:var(--text-secondary);margin:.45rem 0}
.split-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.1rem;margin:.55rem 0}
.sub-card{border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle);padding:.8rem .95rem;min-width:0}
.sub-card h3{margin:0 0 .5rem;font-size:.88rem}
.kv-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:.55rem .9rem;margin:.5rem 0}
.kv-item{border-left:2px solid var(--border-subtle);padding-left:.6rem;min-width:0}
.kv-item dt{font-size:.77rem;color:var(--text-muted)}
.kv-item dd{margin:.1rem 0 0;font-weight:600;font-size:.88rem;overflow-wrap:anywhere}

/* Booktabs Academic Tables */
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:.5rem 0}
table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{border-bottom:1px solid var(--border-subtle);padding:.52rem .65rem;text-align:left;vertical-align:middle}
th{border-top:1px solid var(--border-default);border-bottom:1px solid var(--border-default);background:transparent;color:var(--text-muted);font-weight:600;font-size:.79rem;white-space:nowrap}
tbody tr:last-child td{border-bottom:1px solid var(--border-default)}
tbody tr:hover{background:var(--surface-subtle)}
td{overflow-wrap:anywhere}

/* Charts & Legends */
.chart-box{padding:.65rem 0;margin:.35rem 0;overflow-x:auto}
.chart-box svg{display:block;max-width:100%;height:auto}
.legend-row{display:flex;flex-wrap:wrap;gap:.4rem 1rem;margin:.4rem 0;font-size:.8rem;color:var(--text-muted);align-items:center}
.legend-item{display:inline-flex;align-items:center;gap:.35rem;white-space:nowrap}
.legend-item b{color:var(--text-primary);font-weight:600;font-variant-numeric:tabular-nums}
.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;flex-shrink:0}
.swatch.is-gap{background:repeating-linear-gradient(45deg,var(--gen-gap),var(--gen-gap) 3px,#fff 3px,#fff 5px);border:1px solid var(--gen-gap)}
.swatch.is-tel{border-radius:50%;background:var(--gen-tel)}
.swatch.is-tel-miss{border-radius:50%;border:1.5px solid var(--gen-gap);background:var(--surface-panel)}
.swatch.is-cen{transform:rotate(45deg);border-radius:1px;background:var(--gen-cen)}

/* Chromosome Ideogram & Step-by-Step Pseudomolecule Evolution */
.stage-tabs{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center;margin:0 0 .75rem}
.stage-tab{display:inline-flex;align-items:center;gap:.35rem;padding:.28rem .65rem;border-radius:var(--radius-sm);border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-secondary);font:500 12.5px/1.3 inherit;cursor:pointer;transition:background .12s,border-color .12s,color .12s}
.stage-tab:hover{background:var(--surface-hover);border-color:var(--border-default);color:var(--text-primary)}
.stage-tab.is-active{background:var(--brand);border-color:var(--brand);color:#fff}
.stage-tab small{font-size:11px;opacity:.78;font-variant-numeric:tabular-nums}
.stage-tab.is-active small{color:rgba(255,255,255,.88);opacity:1}
.ideo-list{border-top:1px solid var(--border-default);border-bottom:1px solid var(--border-default)}
.ideo-row{border-bottom:1px solid var(--border-subtle);margin:0}
.ideo-row:last-child{border-bottom:0}
.ideo-row>summary{display:grid;grid-template-columns:120px minmax(180px,1fr) 96px 72px;gap:.75rem;align-items:center;padding:.54rem .35rem;cursor:pointer;list-style:none}
.ideo-row>summary::-webkit-details-marker{display:none}
.ideo-row>summary:hover{background:var(--surface-subtle)}
.ideo-name{display:inline-flex;align-items:center;gap:.35rem;font:600 .84rem/1.2 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ideo-name::before{content:"▸";color:var(--text-muted);font-size:10px;flex-shrink:0;transition:transform .12s}
.ideo-row[open]>summary .ideo-name::before{transform:rotate(90deg)}
.ideo-track-barbox{min-width:0}
.ideo-track{position:relative;display:flex;align-items:stretch;height:20px;border-radius:3px;overflow:hidden;background:var(--surface-muted);min-width:16px}
.ideo-track.is-mini{height:15px}
.ideo-seg{display:block;min-width:1.5px;border-right:1px solid rgba(255,255,255,.4);font-style:normal}
.ideo-seg.ds-0{background:var(--ds-0)}.ideo-seg.ds-1{background:var(--ds-1)}.ideo-seg.ds-2{background:var(--ds-2)}.ideo-seg.ds-3{background:var(--ds-3)}.ideo-seg.ds-4{background:var(--ds-4)}.ideo-seg.ds-5{background:var(--ds-5)}
.ideo-seg.is-patch{background:var(--gen-patch)!important;min-width:5px}
.ideo-seg.is-gap{background:repeating-linear-gradient(45deg,var(--gen-gap),var(--gen-gap) 3px,#fff 3px,#fff 5px)!important;min-width:6px}
.ideo-seg.is-closed{background:var(--gen-closed)!important;min-width:7px}
.ideo-seg.is-partial{background:var(--gen-partial)!important;min-width:7px}
.ideo-seg.is-rejected{background:repeating-linear-gradient(45deg,var(--gen-rejected),var(--gen-rejected) 3px,#fff 3px,#fff 5px)!important;min-width:7px}
.ideo-gap-link{cursor:pointer;text-decoration:none;position:relative;z-index:2;transition:filter .1s,box-shadow .1s}
.ideo-gap-link:hover{filter:brightness(1.16);box-shadow:inset 0 0 0 1.5px #fff;z-index:4}
.ideo-cap{position:absolute;top:2px;width:6px;height:calc(100% - 4px);border-radius:4px;border:1.5px solid var(--surface-panel);z-index:3;pointer-events:none}
.ideo-cap.left{left:2px}.ideo-cap.right{right:2px}
.ideo-cap.complete{background:var(--gen-tel)}.ideo-cap.missing{background:var(--surface-panel);border-color:var(--gen-gap)}
.ideo-cen{position:absolute;top:2px;height:calc(100% - 4px);min-width:5px;background:var(--gen-cen);border:1.5px solid var(--surface-panel);border-radius:2px;z-index:3;pointer-events:none}
.ideo-meta{text-align:right;font-size:.79rem;color:var(--text-muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.ideo-meta.has-gain{color:var(--tone-ok-ink);font-weight:500}
.ideo-detail{padding:.65rem .75rem .75rem 1.25rem;background:var(--surface-subtle);border-top:1px solid var(--border-subtle);font-size:.82rem;color:var(--text-secondary)}
.chr-evo-tracks{display:flex;flex-direction:column;gap:.38rem;margin-bottom:.55rem}
.chr-evo-row{display:grid;grid-template-columns:88px minmax(160px,1fr) 172px;gap:.65rem;align-items:center}
.chr-evo-lbl{font:600 .78rem/1.2 var(--font-mono);color:var(--text-secondary);white-space:nowrap}
.chr-evo-note{font-size:.76rem;color:var(--text-muted);font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
.chr-evo-note b{color:var(--tone-ok-ink);font-weight:600}
.gap-chip-group{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center;margin-top:.45rem;padding-top:.45rem;border-top:1px solid var(--border-subtle)}
.gap-chip-lbl{font-size:.76rem;color:var(--text-muted);font-weight:600;margin-right:.2rem}
.gap-job-chip{display:inline-flex;align-items:center;gap:.3rem;padding:.18rem .52rem;border-radius:3px;border:1px solid var(--border-default);background:var(--surface-panel);color:var(--text-primary);font-size:.76rem;font-variant-numeric:tabular-nums;text-decoration:none;transition:border-color .12s,background .12s}
a.gap-job-chip:hover{border-color:var(--brand);background:var(--surface-hover);text-decoration:none}
.gap-job-chip.is-closed{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.gap-job-chip.is-partial{border-color:var(--tone-info-line);background:var(--tone-info-bg);color:var(--tone-info-ink)}
.gap-job-chip.is-rejected{border-color:var(--tone-err-line);background:var(--tone-err-bg);color:var(--tone-err-ink)}
.gap-job-chip.is-unfilled{border-color:var(--border-default);background:var(--surface-panel);color:var(--text-secondary)}
.gap-job-chip .chip-arrow{opacity:.65;font-size:.72rem}
.swatch.is-closed{background:var(--gen-closed)}
.swatch.is-partial{background:var(--gen-partial)}
.swatch.is-rejected{background:repeating-linear-gradient(45deg,var(--gen-rejected),var(--gen-rejected) 3px,#fff 3px,#fff 5px);border:1px solid var(--gen-rejected)}
.evo-ladder{display:flex;flex-direction:column;gap:.55rem;margin:.2rem 0 .75rem}
.evo-step-row{display:grid;grid-template-columns:152px minmax(180px,1fr) 210px;gap:.85rem;align-items:center}
.evo-step-lbl{font-size:.84rem;font-weight:600;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.evo-step-lbl small{display:block;font-weight:400;font-size:.74rem;color:var(--text-muted)}
.evo-step-bar{min-width:0}
.evo-step-val{text-align:right;font-size:.81rem;color:var(--text-secondary);font-variant-numeric:tabular-nums;white-space:nowrap}
.evo-step-val b{color:var(--text-primary);font-weight:600}
.evo-step-val .gain{color:var(--tone-ok-ink);font-weight:600}

/* Filter Toolbar & Gap Matrix */
.filter-bar{display:flex;flex-wrap:wrap;gap:.45rem;align-items:center;margin:.5rem 0}
.filter-bar select,.filter-bar input[type="search"]{padding:.26rem .52rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-primary);font:inherit;font-size:.82rem}
.filter-bar input[type="search"]{flex:1;min-width:160px}
.filter-chips{display:flex;flex-wrap:wrap;gap:.25rem}
.matrix-cell{display:inline-flex;align-items:center;padding:.1rem .42rem;border-radius:3px;font-size:.76rem;font-weight:500;white-space:nowrap}
.mc-closed{background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.mc-partial{background:var(--tone-info-bg);color:var(--tone-info-ink)}
.mc-unfilled{color:var(--text-muted)}
.mc-rejected{background:var(--tone-err-bg);color:var(--tone-err-ink)}
.mc-na{color:var(--text-muted);font-style:italic}

/* Copy Button, Disclosures, Directory Tree */
.copy-btn{display:inline-flex;align-items:center;padding:.14rem .46rem;border-radius:3px;border:1px solid var(--border-default);background:var(--surface-panel);color:var(--text-secondary);font:500 11.5px/1.25 inherit;cursor:pointer;white-space:nowrap}
.copy-btn:hover{background:var(--surface-subtle);color:var(--text-primary);border-color:var(--border-strong)}
.copy-btn.is-copied{background:var(--tone-ok-bg);border-color:var(--tone-ok-line);color:var(--tone-ok-ink)}
.action-inline{display:inline-flex;align-items:center;gap:.45rem;white-space:nowrap}

details.fold{border-top:1px solid var(--border-subtle);margin-top:.7rem;padding-top:.55rem}
.panel>details.fold:first-child{border-top:0;margin-top:0;padding-top:0}
details.fold>summary{cursor:pointer;font-weight:500;font-size:.86rem;color:var(--text-secondary);list-style-position:inside;padding:.15rem 0}
details.fold>summary:hover{color:var(--text-primary)}
.fold-body{padding:.6rem 0 .2rem}

.tree-controls{display:flex;align-items:center;justify-content:space-between;gap:.5rem;flex-wrap:wrap;margin:.35rem 0 .45rem}
.tree-list{border-top:1px solid var(--border-subtle)}
details.tree-node{border-bottom:1px solid var(--border-subtle)}
details.tree-node>summary{display:flex;align-items:center;justify-content:space-between;gap:.6rem;flex-wrap:wrap;padding:.45rem .25rem;cursor:pointer;list-style:none;font-size:.84rem}
details.tree-node>summary::-webkit-details-marker{display:none}
details.tree-node>summary:hover{background:var(--surface-subtle)}
.tree-node-main{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;min-width:0}
.tree-caret{display:inline-block;width:10px;color:var(--text-muted);font-size:10px;transition:transform .12s}
details.tree-node[open]>summary .tree-caret{transform:rotate(90deg)}
.tree-path{font:600 .83rem/1.2 var(--font-mono);color:var(--text-primary)}
.tree-role{color:var(--text-muted);font-size:.82rem}
.tree-node-right{display:flex;align-items:center;gap:.45rem;font-size:.79rem;color:var(--text-muted)}
.tree-body{padding:.45rem .5rem .65rem 1.4rem;background:var(--surface-subtle)}
.tree-children{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.24rem}
.tree-child{font-size:.81rem;padding:.22rem 0}
.tree-child-head{display:flex;align-items:center;justify-content:space-between;gap:.5rem}
.tree-sublist{list-style:none;margin:.2rem 0 0;padding:.15rem 0 0 .8rem;border-left:1px solid var(--border-default);display:flex;flex-direction:column;gap:.12rem;font-size:.78rem;color:var(--text-muted)}
.cmd-box{display:flex;align-items:center;justify-content:space-between;gap:.6rem;flex-wrap:wrap;background:var(--surface-subtle);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:.45rem .7rem;margin:.5rem 0;font-size:.82rem}
.cmd-box code{background:transparent;padding:0}

/* Links, Chips, Cards, Pager */
.link-row{display:flex;flex-wrap:wrap;gap:.4rem .65rem;align-items:center;margin:.45rem 0}
.link-pill{display:inline-flex;align-items:center;gap:.25rem;padding:.22rem .58rem;border-radius:var(--radius-sm);border:1px solid var(--border-default);background:var(--surface-panel);color:var(--accent);font-size:.82rem;font-weight:500}
.link-pill:hover{border-color:var(--border-strong);background:var(--surface-subtle);text-decoration:none}
.count-chips{display:flex;flex-wrap:wrap;gap:.3rem .65rem;align-items:center;font-size:.81rem;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.count-chip{display:inline-flex;align-items:center;gap:.25rem;white-space:nowrap}
.count-chip b{font-weight:600;color:var(--text-primary)}
.count-chip.is-closed b{color:var(--tone-ok-ink)}
.count-chip.is-partial b{color:var(--tone-info-ink)}
.count-chip.is-rejected b{color:var(--tone-err-ink)}
.gap-card,.job-card{background:var(--surface-panel);border:1px solid var(--border-subtle);border-radius:var(--radius);padding:.95rem 1.15rem}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:.6rem;flex-wrap:wrap;padding-bottom:.5rem;margin-bottom:.6rem;border-bottom:1px solid var(--border-subtle)}
.card-head h2{margin:0;font-size:1rem;font-family:var(--font-mono)}
.reason-list{margin:.3rem 0;padding-left:1.15rem}
.reason-list li{margin:.18rem 0;overflow-wrap:anywhere}
.error-box{border:1px solid var(--tone-err-line);background:var(--tone-err-bg);color:var(--tone-err-ink);border-radius:var(--radius-sm);padding:.65rem .85rem;font-family:var(--font-mono);font-size:.83rem;white-space:pre-wrap;overflow-wrap:anywhere;margin:.45rem 0}
.pager{display:flex;flex-wrap:wrap;gap:.35rem;align-items:center;margin:.45rem 0}
.pager a{padding:.2rem .55rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);font-size:.82rem}
.pager a:hover{background:var(--surface-subtle);text-decoration:none}

@media (max-width:1024px){
  .wb-shell{grid-template-columns:minmax(0,1fr);padding:1rem;gap:.9rem}
  .wb-sidebar{position:static;padding:0;min-width:0}
  .wb-toc{flex-direction:row;overflow-x:auto;border-left:0;border-bottom:1px solid var(--border-subtle);gap:.2rem}
  .wb-toc a{white-space:nowrap;margin-left:0;border-left:0;border-bottom:2px solid transparent;border-radius:var(--radius-sm) var(--radius-sm) 0 0;padding:.38rem .62rem}
  .wb-toc a.is-current{border-bottom-color:var(--brand)}
  .toc-num{min-width:auto}
  .split-grid{grid-template-columns:1fr}
}
@media (max-width:760px){
  .cgat-header-inner{padding:.45rem 1rem}
  .panel{padding:.9rem 1rem}
  .story-scale-row{grid-template-columns:104px minmax(0,1fr);gap:.5rem}
  .ideo-row>summary{grid-template-columns:84px minmax(120px,1fr) 64px 66px}
  .ideo-detail{padding-left:.75rem}
}
@media (max-width:640px){
  .cgat-title-row{flex-wrap:wrap;gap:.35rem .65rem}
  .cgat-title-left{flex:1 1 100%}
  .wb-controls{margin-left:auto;gap:.45rem}
  .cgat-time{font-size:.75rem}
}
@media print{
  body{background:#fff;color:#000}
  .cgat-header{position:static;backdrop-filter:none;-webkit-backdrop-filter:none;box-shadow:none}
  .wb-controls,.wb-sidebar,.cgat-nav,.pager,.filter-bar,.copy-btn,.tree-controls{display:none!important}
  .wb-shell{display:block;padding:0;max-width:none}
  .panel,.gap-card,.job-card{break-inside:avoid}
}
"""

WORKBENCH_JS = r"""
(()=>{
  const root=document.documentElement;
  const store=(k,v)=>{try{if(v===undefined)return localStorage.getItem(k);localStorage.setItem(k,v);}catch(_){return null;}};
  const isDark=()=>root.dataset.theme==='dark'||(!root.dataset.theme&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);
  const syncThemeBtn=()=>{
    const dark=isDark(),en=root.dataset.lang==='en';
    const lbl=dark?(en?'Switch to light theme':'切换为浅色主题'):(en?'Switch to dark theme':'切换为深色主题');
    document.querySelectorAll('[data-theme-toggle]').forEach(b=>{b.title=lbl;b.setAttribute('aria-label',lbl);b.setAttribute('aria-pressed',String(dark));});
  };
  const setLang=(lang)=>{
    lang=(lang==='en')?'en':'zh';
    root.dataset.lang=lang;
    root.lang=(lang==='en')?'en':'zh-CN';
    document.querySelectorAll('[data-lang-btn]').forEach(b=>b.classList.toggle('is-active',b.dataset.langBtn===lang));
    syncThemeBtn();
    store('cgat_report_lang',lang);
  };
  const setTheme=(theme)=>{
    if(theme==='dark'||theme==='light'){root.dataset.theme=theme;syncThemeBtn();store('cgat_report_theme',theme);}
  };
  const savedLang=store('cgat_report_lang');
  if(savedLang==='zh'||savedLang==='en')setLang(savedLang);
  const savedTheme=store('cgat_report_theme');
  if(savedTheme==='dark'||savedTheme==='light')setTheme(savedTheme);
  syncThemeBtn();
  document.addEventListener('click',(ev)=>{
    const lb=ev.target.closest('[data-lang-btn]');
    if(lb){setLang(lb.dataset.langBtn);return;}
    const tb=ev.target.closest('[data-theme-toggle]');
    if(tb){
      setTheme(isDark()?'light':'dark');return;
    }
    const cb=ev.target.closest('[data-copy]');
    if(cb){
      const txt=cb.dataset.copy||'';
      const done=()=>{cb.classList.add('is-copied');setTimeout(()=>cb.classList.remove('is-copied'),1500);};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(txt).then(done,()=>{
          const ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.opacity='0';
          document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(_){}ta.remove();
        });
      }else{
        const ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.opacity='0';
        document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done();}catch(_){}ta.remove();
      }
      return;
    }
    const gl=ev.target.closest('a.ideo-gap-link');
    if(gl){ev.stopPropagation();return;}
    const sb=ev.target.closest('[data-stage-btn]');
    if(sb){
      const rootBox=sb.closest('[data-evo-root]');
      if(rootBox){
        const target=sb.dataset.stageTarget||sb.dataset.stageBtn;
        rootBox.querySelectorAll('[data-stage-btn]').forEach(b=>b.classList.toggle('is-active',b===sb));
        rootBox.querySelectorAll('[data-stage-panel]').forEach(p=>p.classList.toggle('is-hidden',p.dataset.stagePanel!==target));
      }
      return;
    }
    const ta=ev.target.closest('[data-tree-action]');
    if(ta){
      const box=document.querySelector(ta.dataset.treeTarget||'[data-tree-root]');
      if(box){const open=ta.dataset.treeAction==='expand';box.querySelectorAll('details.tree-node').forEach(d=>{d.open=open;});}
      return;
    }
    const mf=ev.target.closest('[data-matrix-chip]');
    if(mf){
      const box=mf.closest('[data-matrix-root]');
      if(box){
        box.querySelectorAll('[data-matrix-chip]').forEach(b=>b.classList.toggle('is-active',b===mf));
        box.dataset.statusFilter=mf.dataset.matrixChip;
        applyMatrixFilter(box);
      }
      return;
    }
    const gf=ev.target.closest('[data-gap-chip]');
    if(gf){
      const box=gf.closest('[data-gap-filter-root]');
      if(box){
        box.querySelectorAll('[data-gap-chip]').forEach(b=>b.classList.toggle('is-active',b===gf));
        box.dataset.statusFilter=gf.dataset.gapChip;
        applyGapFilter(box);
      }
      return;
    }
  });
  const applyMatrixFilter=(box)=>{
    const chrSel=box.querySelector('[data-matrix-chr]');
    const qInp=box.querySelector('[data-matrix-search]');
    const chrVal=chrSel?chrSel.value:'';
    const qVal=(qInp?qInp.value:'').trim().toLowerCase();
    const stVal=box.dataset.statusFilter||'all';
    let shown=0,total=0;
    box.querySelectorAll('tbody tr[data-chr]').forEach(tr=>{
      total++;
      const okChr=!chrVal||tr.dataset.chr===chrVal;
      const states=(tr.dataset.states||'').split(',');
      const okSt=(stVal==='all')||(stVal==='closed'&&states.includes('closed'))||(stVal==='partial'&&states.includes('partial'))||(stVal==='rejected'&&states.includes('rejected'))||(stVal==='unfilled'&&states.every(s=>s==='unfilled'||s.startsWith('tool_')));
      const okQ=!qVal||(tr.textContent||'').toLowerCase().includes(qVal);
      const vis=okChr&&okSt&&okQ;
      tr.classList.toggle('is-hidden',!vis);
      if(vis)shown++;
    });
    const out=box.querySelector('[data-matrix-count]');
    if(out)out.textContent=shown+' / '+total;
  };
  const applyGapFilter=(box)=>{
    const qInp=box.querySelector('[data-gap-search]');
    const qVal=(qInp?qInp.value:'').trim().toLowerCase();
    const stVal=box.dataset.statusFilter||'all';
    let shown=0,total=0;
    document.querySelectorAll('section.gap-card[data-gap-status]').forEach(card=>{
      total++;
      const okSt=stVal==='all'||card.dataset.gapStatus===stVal;
      const okQ=!qVal||(card.textContent||'').toLowerCase().includes(qVal);
      const vis=okSt&&okQ;
      card.classList.toggle('is-hidden',!vis);
      if(vis)shown++;
    });
    const out=box.querySelector('[data-gap-count]');
    if(out)out.textContent=shown+' / '+total;
  };
  document.addEventListener('input',(ev)=>{
    const mb=ev.target.closest('[data-matrix-root]');
    if(mb)applyMatrixFilter(mb);
    const gb=ev.target.closest('[data-gap-filter-root]');
    if(gb)applyGapFilter(gb);
  });
  document.addEventListener('change',(ev)=>{
    const mb=ev.target.closest('[data-matrix-root]');
    if(mb)applyMatrixFilter(mb);
  });
  if('IntersectionObserver' in window){
    const tocLinks=[...document.querySelectorAll('.wb-toc a[href^="#"]')];
    const map=new Map();
    tocLinks.forEach(a=>{const el=document.getElementById(a.getAttribute('href').slice(1));if(el)map.set(el,a);});
    if(map.size){
      const io=new IntersectionObserver((entries)=>{
        for(const e of entries){
          if(e.isIntersecting){
            tocLinks.forEach(a=>a.classList.remove('is-current'));
            const a=map.get(e.target);if(a)a.classList.add('is-current');
          }
        }
      },{rootMargin:'-12% 0px -70% 0px',threshold:0});
      map.forEach((_,el)=>io.observe(el));
    }
  }
})();
"""

STATUS_VOCAB = {
    "published": ("已发布", "Published", "ok"),
    "staged": ("已暂存（未发布）", "Staged (not published)", "warn"),
    "completed": ("已完成", "Completed", "ok"),
    "complete": ("已完成", "Completed", "ok"),
    "completed_without_native_fill": ("已完成（未补上）", "Completed (gap not filled)", "neutral"),
    "exception": ("执行异常", "Execution error", "err"),
    "not_started": ("未开始", "Not started", "neutral"),
    "not_requested": ("仅 LGZ 基线", "LGZ Baseline Only", "info"),
    "publication_unverified": ("发布未验证", "Publication not verified", "warn"),
    "completed_no_changes": ("已完成（无接纳修改）", "Completed (0 accepted changes)", "neutral"),
    "completed_zero_accepted": ("已完成（无接纳修改）", "Completed (0 accepted changes)", "neutral"),
    "unchanged": ("无变更", "Unchanged", "neutral"),
    "success": ("成功", "Success", "ok"),
    "running": ("运行中", "Running", "info"),
    "pending": ("等待中", "Pending", "neutral"),
    "failed": ("失败", "Failed", "err"),
    "invalidated": ("已失效", "Invalidated", "err"),
    "partial_failure": ("部分失败", "Partial failure", "warn"),
    "report_failed": ("报告生成失败", "Report failed", "err"),
    "interrupted": ("已中断", "Interrupted", "warn"),
    "skipped": ("已跳过", "Skipped", "neutral"),
    "not_recorded": ("未记录", "Not recorded", "neutral"),
    "closed": ("已闭合", "Closed", "ok"),
    "partial": ("部分填补", "Partial", "info"),
    "unfilled": ("未填补", "Unfilled", "neutral"),
    "rejected": ("已拒绝", "Rejected", "err"),
    "embedded": ("已嵌入", "Embedded", "ok"),
    "server_only_size_limit": ("仅服务器（超体积限制）", "Server-only (size limit)", "warn"),
    "server_only_native_script": ("仅服务器（原生脚本）", "Server-only (native script)", "neutral"),
    "server_only_sequence_or_binary": ("仅服务器（序列/二进制）", "Server-only (sequence/binary)", "neutral"),
    "server_only_private_reads": ("仅服务器（含私有 reads 路径）", "Server-only (private reads)", "neutral"),
    "available": ("可用", "Available", "ok"),
    "not_available": ("不可用", "Not available", "neutral"),
    "observed": ("已存在", "Observed", "neutral"),
    "historical": ("历史版本", "Historical", "neutral"),
    "changed": ("内容已变更", "Changed", "err"),
    "not_generated": ("未生成", "Not generated", "neutral"),
    "not_enabled": ("未启用", "Not enabled", "neutral"),
    "external_not_inspected": ("工作区外（未检查）", "External (not inspected)", "neutral"),
}

PHASE_LABELS = {
    "native": ("原生执行", "Native execution"),
    "admission": ("CGAT 接纳", "CGAT admission"),
    "source_evidence": ("来源证据", "Source evidence"),
    "report": ("生成报告", "Report generation"),
    "app_delivery": ("App 打包", "App packaging"),
    "publication": ("发布", "Publication"),
}


def esc(value):
    return escape(str(value), quote=True)


def bi(zh, en):
    return f'<span class="t-zh">{esc(zh)}</span><span class="t-en">{esc(en)}</span>'


def bi_raw(zh_html, en_html):
    return f'<span class="t-zh">{zh_html}</span><span class="t-en">{en_html}</span>'


def json_text(value):
    return escape(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def fmt_int(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def fmt_bp(value):
    if value is None:
        return "—"
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


def fmt_bp_short(value):
    if value is None or not isinstance(value, (int, float)):
        return "—"
    n = float(value)
    a = abs(n)
    if a >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f} Gb"
    if a >= 1_000_000:
        return f"{n / 1_000_000:.2f} Mb"
    if a >= 1_000:
        return f"{n / 1_000:.1f} kb"
    return f"{int(n):,} bp"


def fmt_bytes(value):
    if not isinstance(value, (int, float)):
        return "—"
    n = int(value)
    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024 * 1024):.2f} GiB"
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:.1f} KiB"
    return f"{n:,} B"


def fmt_duration(seconds):
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "—"
    s = float(seconds)
    if s < 60:
        return f"{s:.1f}s" if s < 10 else f"{s:.0f}s"
    total = int(round(s))
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {sec:02d}s"
    return f"{m}m {sec:02d}s"


def status_meta(status):
    key = str(status) if status is not None else "not_recorded"
    if key in STATUS_VOCAB:
        return STATUS_VOCAB[key]
    return (key, key, "neutral")


def badge_html(text, tone="neutral", *, raw=False):
    inner = text if raw else esc(text)
    return f'<span class="badge tone-{esc(tone)}">{inner}</span>'


def badge_bi(zh, en, tone="neutral"):
    return f'<span class="badge tone-{esc(tone)}">{bi(zh, en)}</span>'


def status_badge(status, label=None):
    zh, en, tone = status_meta(status)
    if label is not None:
        return badge_html(label, tone)
    return badge_bi(zh, en, tone)


def copy_btn(text, *, zh="复制", en="Copy"):
    return (
        f'<button type="button" class="copy-btn" data-copy="{esc(text)}" title="{esc(text)}">'
        f'<span class="t-zh">{esc(zh)}</span><span class="t-en">{esc(en)}</span></button>'
    )


def callout(body_html, tone="info", title=None, *, title_raw=False):
    heading = f'<div class="callout-title">{title if title_raw else esc(title)}</div>' if title else ""
    return f'<div class="callout tone-{esc(tone)}">{heading}{body_html}</div>'


def disclosure(summary_html, body_html, *, open_by_default=False, cls="fold"):
    open_attr = " open" if open_by_default else ""
    return f'<details class="{esc(cls)}"{open_attr}><summary>{summary_html}</summary><div class="fold-body">{body_html}</div></details>'


def kv_grid(items):
    parts = []
    for key, value_html in items:
        key_html = key if isinstance(key, str) and "<span class=" in key else esc(key)
        parts.append(f'<div class="kv-item"><dt>{key_html}</dt><dd>{value_html}</dd></div>')
    return '<dl class="kv-grid">' + "".join(parts) + '</dl>'


def format_counts_html(counts, *, status=None, invalidated=False, omit_zero=False):
    if invalidated:
        return '<span class="muted">' + bi("无统计（批次已失效）", "Unavailable (batch invalidated)") + '</span>'
    if not isinstance(counts, dict):
        if status in {"failed", "pending", "running", "invalidated", "report_failed"}:
            return '<span class="muted">' + bi(f"无可用统计（{status}）", f"Not available ({status})") + '</span>'
        return '<span class="muted">' + bi("未记录", "Not recorded") + '</span>'
    labels = (
        ("closed", "已闭合", "Closed", "is-closed"),
        ("partial", "部分填补", "Partial", "is-partial"),
        ("unfilled", "未填补", "Unfilled", "is-unfilled"),
        ("rejected", "已拒绝", "Rejected", "is-rejected"),
    )
    chips = []
    for key, zh, en, css_cls in labels:
        val = counts.get(key)
        if val is not None and (not omit_zero or val > 0):
            chips.append(f'<span class="count-chip {css_cls}">{bi(zh, en)} <b>{esc(fmt_int(val))}</b></span>')
    if not chips:
        return '<span class="muted">' + bi("无记录", "None") + '</span>'
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


def link(relative, label, *, cls=None, raw=False):
    attr = f' class="{esc(cls)}"' if cls else ""
    inner = label if raw else esc(label)
    return f'<a{attr} href="' + quote(relative, safe="/#-_.") + '">' + inner + '</a>'


def svg_stacked_bar(segments, *, width=260, height=14, aria_label="Stacked distribution"):
    total = sum(max(0, v) for v, _, _ in segments)
    if total <= 0:
        return (
            f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{esc(aria_label)}" style="vertical-align:middle">'
            f'<rect x="0" y="0" width="{width}" height="{height}" rx="3" fill="var(--surface-muted)"/></svg>'
        )
    rects = []
    x = 0.0
    for val, color, tip in segments:
        if val <= 0:
            continue
        w = max(1.5, width * val / total)
        if x + w > width:
            w = max(0.5, width - x)
        rects.append(
            f'<rect x="{x:.2f}" y="0" width="{w:.2f}" height="{height}" fill="{esc(color)}">'
            f'<title>{esc(tip)}</title></rect>'
        )
        x += w
    clip_id = "cb-" + hashlib.sha256((aria_label + str(segments)).encode()).hexdigest()[:10]
    return (
        f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-label="{esc(aria_label)}" style="vertical-align:middle">'
        f'<defs><clipPath id="{clip_id}"><rect x="0" y="0" width="{width}" height="{height}" rx="3"/></clipPath></defs>'
        f'<g clip-path="url(#{clip_id})">' + "".join(rects) + '</g></svg>'
    )


def svg_funnel(steps):
    valid = [s[2] for s in steps if isinstance(s[2], int) and s[2] > 0]
    max_val = max(valid) if valid else 1
    row_h = 36
    h = max(1, len(steps)) * row_h + 8
    w = 500
    bar_x = 136
    bar_max = 260
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Alignment and assignment distribution">']
    for idx, (l_zh, l_en, val, color, note) in enumerate(steps):
        y = 5 + idx * row_h
        bw = (bar_max * val / max_val) if isinstance(val, int) and val > 0 else 0
        bw_draw = max(4.0, bw) if isinstance(val, int) and val > 0 else 0
        val_txt = fmt_int(val) if isinstance(val, int) else "—"
        pct = f" ({100 * val / max_val:.1f}%)" if isinstance(val, int) and max_val > 0 and idx > 0 else ""
        parts.append(
            f'<g>'
            f'<text x="{bar_x - 10}" y="{y + 18}" text-anchor="end" fill="var(--text-primary)" font-size="11.5" font-weight="500">{esc(l_zh)}</text>'
            f'<rect x="{bar_x}" y="{y + 6}" width="{bar_max}" height="18" rx="3" fill="var(--surface-muted)"/>'
            + (
                f'<rect x="{bar_x}" y="{y + 6}" width="{bw_draw:.1f}" height="18" rx="3" fill="{esc(color)}">'
                f'<title>{esc(l_zh)} / {esc(l_en)}: {esc(val_txt)}{esc(pct)}</title></rect>'
                if bw_draw > 0 else ""
            )
            + f'<text x="{bar_x + bar_max + 10}" y="{y + 19}" fill="var(--text-primary)" font-size="11.5" font-weight="600">{esc(val_txt)}{esc(pct)}</text>'
            + '</g>'
        )
    parts.append('</svg>')
    return "".join(parts)


def svg_evolution_chart(version_items):
    if not version_items:
        return ""
    n = len(version_items)
    w = max(560, n * 135 + 140)
    h = 216
    pad_l, pad_r, pad_t, pad_b = 76, 56, 34, 40
    plot_w = w - pad_l - pad_r
    plot_h = h - pad_t - pad_b
    lengths = [int(s.get("length_bp") or 0) for _, s in version_items]
    n50s = [int(s.get("n50_bp") or 0) for _, s in version_items]
    gaps = [s.get("gap_count") for _, s in version_items]
    max_len = max([*lengths, *n50s, 1])
    gap_vals = [g for g in gaps if isinstance(g, int)]
    max_gap = max(gap_vals) if gap_vals and max(gap_vals) > 0 else 1

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="LGZ sequence version evolution">']
    for i in range(4):
        gy = pad_t + plot_h * i / 3
        lv = max_len * (3 - i) / 3
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w - pad_r}" y2="{gy:.1f}" stroke="var(--border-subtle)" stroke-dasharray="2 3"/>')
        parts.append(f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" fill="var(--text-muted)" font-size="10.5">{esc(fmt_bp_short(lv))}</text>')
    parts.append(f'<text x="{pad_l}" y="14" fill="var(--text-muted)" font-size="10.5" font-weight="600">Length / N50</text>')
    parts.append(f'<text x="{w - pad_r}" y="14" text-anchor="end" fill="var(--gen-gap)" font-size="10.5" font-weight="600">Gaps (≥100 N)</text>')

    gap_pts = []
    step_x = plot_w / max(1, n)
    bar_w = min(28, step_x * 0.22)
    for idx, (ver, st) in enumerate(version_items):
        cx = pad_l + step_x * (idx + 0.5)
        l_bp = int(st.get("length_bp") or 0)
        n50 = int(st.get("n50_bp") or 0)
        lh = plot_h * l_bp / max_len
        nh = plot_h * n50 / max_len
        parts.append(f'<rect x="{cx - bar_w - 2:.1f}" y="{pad_t + plot_h - lh:.1f}" width="{bar_w:.1f}" height="{max(2.0, lh):.1f}" rx="2" fill="var(--ds-0)" opacity=".88"><title>{esc(ver)} Length: {esc(fmt_bp(l_bp))}</title></rect>')
        parts.append(f'<rect x="{cx + 2:.1f}" y="{pad_t + plot_h - nh:.1f}" width="{bar_w:.1f}" height="{max(2.0, nh):.1f}" rx="2" fill="var(--ds-1)" opacity=".88"><title>{esc(ver)} N50: {esc(fmt_bp(n50))}</title></rect>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 17}" text-anchor="middle" fill="var(--text-primary)" font-size="11.5" font-weight="600">{esc(ver)}</text>')
        parts.append(f'<text x="{cx:.1f}" y="{h - 3}" text-anchor="middle" fill="var(--text-muted)" font-size="10">{esc(fmt_bp_short(l_bp))}</text>')
        g = st.get("gap_count")
        if isinstance(g, int):
            gy = pad_t + plot_h - (plot_h * g / max_gap if max_gap > 0 else 0)
            gap_pts.append((cx, gy, ver, g))

    if len(gap_pts) >= 2:
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y, _, _) in enumerate(gap_pts))
        parts.append(f'<path d="{d}" fill="none" stroke="var(--gen-gap)" stroke-width="2" stroke-linecap="round"/>')
    for x, y, ver, g in gap_pts:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="var(--surface-panel)" stroke="var(--gen-gap)" stroke-width="2"><title>{esc(ver)} Gaps: {g:,}</title></circle>')
        parts.append(f'<text x="{x:.1f}" y="{max(pad_t - 10, y - 9):.1f}" text-anchor="middle" fill="var(--gen-gap)" font-size="10.5" font-weight="600">{g:,}</text>')
    parts.append('</svg>')
    return "".join(parts)


def svg_timing_bars(items):
    measured = [x for x in items if isinstance(x[1], (int, float)) and x[1] >= 0]
    if not measured:
        return ""
    max_s = max((x[1] for x in measured), default=1) or 1.0
    row_h, w, lbl_w, bar_max = 28, 620, 172, 300
    h = len(measured) * row_h + 10
    tone_colors = {
        "ok": "var(--ds-0)", "cache": "var(--ds-1)", "warn": "var(--gen-patch)",
        "err": "var(--gen-gap)", "hot": "var(--gen-patch)", "neutral": "var(--border-strong)",
    }
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Execution timing breakdown">']
    for idx, (name, sec, tone, tag) in enumerate(measured):
        y = 5 + idx * row_h
        bw = max(3.0, bar_max * sec / max_s) if sec > 0 else 2.0
        col = tone_colors.get(tone, "var(--ds-0)")
        short_name = name if len(name) <= 23 else name[:21] + "…"
        parts.append(
            f'<g><text x="{lbl_w - 8}" y="{y + 17}" text-anchor="end" fill="var(--text-primary)" font-size="11.5"><title>{esc(name)}</title>{esc(short_name)}</text>'
            f'<rect x="{lbl_w}" y="{y + 6}" width="{bar_max}" height="14" rx="3" fill="var(--surface-muted)"/>'
            f'<rect x="{lbl_w}" y="{y + 6}" width="{bw:.1f}" height="14" rx="3" fill="{col}"><title>{esc(name)}: {esc(fmt_duration(sec))}</title></rect>'
            f'<text x="{lbl_w + bar_max + 10}" y="{y + 17}" fill="var(--text-primary)" font-size="11.5" font-weight="600">{esc(fmt_duration(sec))}</text>'
            + (f'<text x="{lbl_w + bar_max + 74}" y="{y + 17}" fill="var(--text-muted)" font-size="10.5">{esc(tag)}</text>' if tag else "")
            + '</g>'
        )
    parts.append('</svg>')
    return "".join(parts)


def _header_controls_html(header_time_html="", *, time_raw=False):
    if header_time_html:
        t_node = header_time_html if time_raw else f'<time class="cgat-time">{header_time_html}</time>'
        time_part = t_node + '<span class="hdr-sep" aria-hidden="true"></span>'
    else:
        time_part = ""
    return (
        '<div class="wb-controls">'
        + time_part
        + '<div class="seg-ctrl" role="group" aria-label="Language">'
        '<button type="button" class="ctrl-btn is-active" data-lang-btn="zh" aria-label="切换中文">中文</button>'
        '<button type="button" class="ctrl-btn" data-lang-btn="en" aria-label="Switch to English">EN</button>'
        '</div>'
        '<button type="button" class="ctrl-btn theme-btn" data-theme-toggle="1" title="切换为深色主题" aria-label="切换为深色主题">'
        '<svg class="ico-moon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>'
        '<svg class="ico-sun" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.93 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>'
        '</button>'
        '</div>'
    )


def workbench_page(
    title_zh,
    title_en,
    body,
    *,
    scope_zh=None,
    scope_en=None,
    title_html=None,
    brand_html="",
    brand_sep=True,
    role_zh=None,
    role_en=None,
    header_time_html="",
    header_time_raw=False,
    subtitle_html="",
    badge_html_str="",
    nav_html="",
    sidebar_items=None,
    sidebar_links=None,
    page_title_plain=None,
    footer_html=None,
):
    """Render the formal, restrained offline CGAT report shell with EXACTLY ONE </main>."""
    sub_part = f'<div class="cgat-subtitle">{subtitle_html}</div>' if subtitle_html else ""
    nav_part = f'<nav class="cgat-nav" aria-label="Report navigation">{nav_html}</nav>' if nav_html else ""
    brand_part = (brand_html + ('<span class="cgat-sep" aria-hidden="true"></span>' if brand_sep else "")) if brand_html else ""
    role_part = f'<span class="cgat-doc-role">{bi(role_zh, role_en or role_zh)}</span>' if role_zh else ""
    h1_inner = title_html if title_html is not None else bi(title_zh, title_en)
    hdr_cls = "cgat-header" if sidebar_items else "cgat-header is-centered"
    header = (
        f'<header class="{hdr_cls}"><div class="cgat-header-inner">'
        '<div class="cgat-title-row">'
        '<div class="cgat-title-left">'
        + brand_part
        + '<div class="cgat-title-group"><h1>' + h1_inner + '</h1>' + role_part + (badge_html_str or "") + '</div>'
        + '</div>'
        + _header_controls_html(header_time_html, time_raw=header_time_raw)
        + '</div>'
        + sub_part + nav_part
        + '</div></header>'
    )
    sidebar_html = ""
    shell_cls = "wb-shell"
    if sidebar_items:
        has_nums = any(item[1] for item in sidebar_items)
        toc_rows = []
        for idx, item in enumerate(sidebar_items):
            sec_id, num, l_zh, l_en = item
            cur = ' class="is-current"' if idx == 0 else ""
            prefix = f'<span class="toc-num">{esc(num or "·")}</span>' if has_nums else ""
            toc_rows.append(f'<li><a href="#{esc(sec_id)}"{cur}>{prefix}<span>{bi(l_zh, l_en)}</span></a></li>')
        sidebar_html = (
            '<aside class="wb-sidebar" aria-label="Report sections">'
            '<ol class="wb-toc">' + "".join(toc_rows) + '</ol></aside>'
        )
    else:
        shell_cls = "wb-shell no-sidebar"
    doc_title = page_title_plain or f"{title_zh}"
    return (
        '<!doctype html><html lang="zh-CN" data-lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + esc(REPORT_CSP) + '">'
        '<title>' + esc(doc_title) + '</title><style>' + CSS + '</style></head>'
        '<body>' + header
        + f'<div class="{shell_cls}">' + sidebar_html
        + '<main class="cgat-main">' + body + '</main>'
        + '</div>'
        + '<script data-cgat-ui="1">' + WORKBENCH_JS + '</script></body></html>\n'
    )


def page(title, body, *, scope=None, subtitle=None, nav=None, badge=None):
    return workbench_page(
        title,
        title,
        body,
        subtitle_html=subtitle or "",
        badge_html_str=badge or "",
        nav_html=nav or "",
        page_title_plain=title,
    )


def table(headers, rows, *, empty=None, attrs=""):
    th_cells = [
        "<th>" + (h if isinstance(h, str) and "<span class=" in h else esc(h)) + "</th>"
        for h in headers
    ]
    thead = "<thead><tr>" + "".join(th_cells) + "</tr></thead>"
    if rows:
        body_rows = []
        for row in rows:
            if isinstance(row, tuple) and len(row) == 2 and isinstance(row[0], str) and isinstance(row[1], (list, tuple)):
                tr_attr, cells = row
                body_rows.append(f"<tr {tr_attr}>" + "".join("<td>" + str(c) + "</td>" for c in cells) + "</tr>")
            else:
                body_rows.append("<tr>" + "".join("<td>" + str(c) + "</td>" for c in row) + "</tr>")
        tbody = "<tbody>" + "".join(body_rows) + "</tbody>"
    elif empty is not None:
        empty_html = empty if isinstance(empty, str) and "<span class=" in empty else esc(empty)
        tbody = f'<tbody><tr><td colspan="{max(1, len(headers))}" class="muted">{empty_html}</td></tr></tbody>'
    else:
        tbody = "<tbody></tbody>"
    tbl_attr = f" {attrs}" if attrs else ""
    return f'<div class="table-wrap"><table{tbl_attr}>' + thead + tbody + "</table></div>"


def gap_anchor(gap_id):
    return "gap-" + hashlib.sha256(gap_id.encode()).hexdigest()[:24]


def retained_flanks(edits):
    return [
        row
        for edit in edits
        for row in edit.get("evidence", {}).get("flank_decisions", [])
        if row.get("decision") == "retained_lgz"
    ]


def render_retained_flanks(rows):
    return (
        '<h3>' + bi("保留 LGZ 原侧翼", "Original flanks retained") + '</h3>'
        '<p class="muted">'
        + bi("缺口补丁单独判定；原生侧翼变化缺乏独立支持，未写入终版。", "Gap admission is separate; unsupported native flank edits were not admitted.")
        + '</p>'
        + table(
            [bi("侧翼", "Flank"), bi("LGZ 区间", "LGZ interval"), bi("原生区间", "Native interval"), bi("原生长度差", "Native delta")],
            [
                (
                    bi("左", "Left") if row["side"] == "left" else bi("右", "Right") if row["side"] == "right" else esc(row["side"]),
                    f'<code>{esc(str(row["baseline_interval"]))}</code>',
                    f'<code>{esc(str(row["native_interval"]))}</code>',
                    '<span class="num">' + esc(f'{row["native_length_delta_bp"]:+,} bp') + '</span>',
                )
                for row in rows
            ],
        )
    )


def _summarize_reasons_html(rows, *, empty_zh="无记录", empty_en="None recorded"):
    if not rows:
        return '<p class="muted">' + bi(empty_zh, empty_en) + '</p>'
    descriptions = {
        "gap_and_flank_cannot_be_separated": (
            "无法可靠区分缺口补丁和已有组装序列",
            "Gap and original sequence could not be separated reliably",
        ),
        "projected_gap_unchanged": (
            "保留原侧翼后缺口未变化",
            "Gap unchanged after retaining original flanks",
        ),
    }
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
            r_bits = []
            for k, v in reasons:
                if isinstance(v, str) and v in descriptions:
                    zh_d, en_d = descriptions[v]
                    r_bits.append(f'<b>{esc(k)}</b>: {bi(zh_d, en_d)}')
                else:
                    r_bits.append(f'<b>{esc(k)}</b>: {esc(v)}')
            parts.append(" · ".join(r_bits))
        elif not parts:
            parts.append('<span class="muted">' + bi("见原始 JSON", "See raw JSON") + '</span>')
        items.append("<li>" + " — ".join(parts) + "</li>")
    return '<ul class="reason-list">' + "".join(items) + '</ul>'


def _job_status_summary(job):
    result = job.get("execution_result")
    if not isinstance(result, dict):
        return badge_bi("未记录执行条目", "No execution row recorded", "neutral"), ""
    status = result.get("status") or "not_recorded"
    if status == "failed" and degap_child_terminal(result):
        status = "completed_without_native_fill"
    details = [value for _, value in extract_recorded_reasons(result)]
    for keys, lbl in (
        (("exit_code", "return_code", "returncode"), "exit"),
        (("elapsed_time", "elapsed_seconds", "elapsed", "duration"), "time(s)"),
    ):
        value = next((result[key] for key in keys if result.get(key) is not None), None)
        if value is not None:
            details.append(f"{lbl}: {value}")
    return status_badge(status), " · ".join(details)


def render_tool_pages(summary, provenance, final, assets, *, page_size=PAGE_SIZE):
    tool = summary["tool"]
    run_id = summary["run_id"]
    execution = summary["execution"]
    counts = summary["counts"]
    accepted_edits = summary["accepted_edit_count"]
    orig_gaps = summary["original_gap_count"]
    remaining_gaps = summary["remaining_gap_count"]
    outcome = summary["outcome"]
    no_accepted_changes = (
        accepted_edits == 0 and counts.get("closed", 0) == 0 and counts.get("partial", 0) == 0
    )

    # 1. Single-row status strip (native execution | CGAT admission | publication)
    native_reused = bool(execution.get("native_reused"))
    native_executed = execution.get("native_executed")
    native_origin = execution.get("native_origin")
    native_status = execution.get("native_status")
    if native_reused:
        native_badge = badge_bi("复用原生证据", "Reused native evidence", "warn")
    elif native_executed is True:
        native_badge = badge_bi("本次执行", "Executed", "info")
    elif native_executed is False:
        native_badge = badge_bi("未执行", "Not executed", "neutral")
    else:
        native_badge = status_badge("not_recorded")
    native_extra = (" " + status_badge(native_status)) if native_status is not None else ""

    if no_accepted_changes:
        accept_badge = status_badge("completed_no_changes")
        reason_pair = {
            "native_no_candidates": ("原生无候选", "No native candidates"),
            "native_no_eligible_gaps": ("无符合条件缺口", "No eligible gaps"),
            "native_no_eligible_flanks": ("无符合条件侧翼", "No eligible flanks"),
            "native_no_remaining_gaps": ("LGZ 无剩余缺口", "No remaining LGZ gaps"),
        }.get(outcome)
        accept_desc = " · ".join(filter(None, [
            bi(*reason_pair) if reason_pair else "",
            bi("保留 LGZ 序列", "LGZ sequence retained"),
        ]))
    else:
        accept_badge = status_badge(outcome)
        accept_desc = ""

    status_strip = (
        '<div id="status-separation" class="compact-strip" style="margin:0">'
        f'<span>{bi("原生：", "Native: ")}{native_badge}{native_extra}</span>'
        '<span class="muted">｜</span>'
        f'<span>{bi("CGAT 接纳：", "CGAT: ")}{accept_badge}' + (f' <small class="muted">{accept_desc}</small>' if accept_desc else "") + '</span>'
        '<span class="muted">｜</span>'
        f'<span class="muted">{bi("发布状态以总览页为准", "Publication confirmed in overview")}</span>'
        '</div>'
    )

    # 2. Hero Visual: 100% Stacked Gap Outcomes Bar (no redundant 4-7 KPI cards!)
    c_closed = counts.get("closed") or 0
    c_partial = counts.get("partial") or 0
    c_unfilled = counts.get("unfilled") or 0
    c_rejected = counts.get("rejected") or 0
    stacked = svg_stacked_bar(
        [
            (c_closed, "var(--gen-closed)", f"Closed / 已闭合: {c_closed}"),
            (c_partial, "var(--gen-partial)", f"Partial / 部分填补: {c_partial}"),
            (c_unfilled, "var(--gen-unfilled)", f"Unfilled / 未填补: {c_unfilled}"),
            (c_rejected, "var(--gen-rejected)", f"Rejected / 已拒绝: {c_rejected}"),
        ],
        width=760,
        height=20,
        aria_label=f"{tool} gap outcomes",
    )
    legend_bits = [
        f'<span class="legend-item"><i class="swatch" style="background:var(--gen-closed)"></i>{bi("已闭合", "Closed")} <b>{c_closed:,}</b></span>',
        f'<span class="legend-item"><i class="swatch" style="background:var(--gen-partial)"></i>{bi("部分填补", "Partial")} <b>{c_partial:,}</b></span>' if c_partial else "",
        f'<span class="legend-item"><i class="swatch" style="background:var(--gen-unfilled)"></i>{bi("未填补", "Unfilled")} <b>{c_unfilled:,}</b></span>' if c_unfilled else "",
        f'<span class="legend-item"><i class="swatch" style="background:var(--gen-rejected)"></i>{bi("已拒绝", "Rejected")} <b>{c_rejected:,}</b></span>' if c_rejected else "",
    ]
    exact_metrics = [
        (bi("原始 LGZ 缺口分母", "Original LGZ gaps"), f'<span class="num">{orig_gaps:,}</span>'),
        (bi("CGAT 接纳修改数", "Accepted edits"), f'<span class="num">{accepted_edits:,}</span>'),
        (bi("最终剩余 N 区间", "Remaining N-runs"), f'<span class="num">{remaining_gaps:,}</span>'),
    ]
    if summary.get("retained_flank_count"):
        exact_metrics.append((bi("保留 LGZ 原侧翼", "Original flanks retained"), f'<span class="num">{summary["retained_flank_count"]:,}</span>'))

    body = (
        '<section id="counts" class="panel">'
        f'<div class="panel-head"><h2>{bi(f"原始缺口接纳结果（共 {orig_gaps:,} 个）", f"Accepted Gap Outcomes ({orig_gaps:,} original gaps)")}</h2></div>'
        + status_strip
        + '<div class="chart-box">' + stacked
        + '<div class="legend-row">' + "".join(b for b in legend_bits if b) + '</div></div>'
        + disclosure(
            bi("查看独立精确计数（接纳修改 / 剩余 N 区间 / 保留侧翼）", "Exact separate metrics (edits / remaining N-runs / retained flanks)"),
            kv_grid(exact_metrics)
            + '<p class="muted">' + bi("全部原始 LGZ 缺口保留在分母中；不自动排名，不代表生物学准确性验证。", "All original LGZ gaps stay in denominator; no ranking or biological accuracy claim.") + '</p>',
        )
        + '</section>'
    )

    # 3. Native vs Accepted Chromosomes (1 line when identical; full table folded unless diffs exist!)
    chr_list = summary["chromosomes"]
    diff_chrs = [r for r in chr_list if r["native_equals_accepted"] is not True]
    all_identical = bool(chr_list) and not diff_chrs

    def _chr_table(rows_src):
        rows = []
        for r in rows_src:
            nat = (
                f'<span class="num">{esc(fmt_bp(r["native"]["length"]))}</span> · <small>N {esc(fmt_int(r["native"]["n_bases"]))}</small>'
                if r["native"] else '<span class="muted">—</span>'
            )
            acc = f'<span class="num">{esc(fmt_bp(r["accepted_length"]))}</span> · <small>N {esc(fmt_int(r["accepted_n_bases"]))}</small>'
            eq = r["native_equals_accepted"]
            match_cell = (
                badge_bi("一致", "Identical", "ok") if eq is True
                else badge_bi("不同", "Different", "warn") if eq is False
                else badge_bi("不可比", "N/A", "neutral")
            )
            rows.append((f'<code>{esc(r["chromosome"])}</code>', nat, acc, match_cell))
        return table(
            [bi("染色体", "Chromosome"), bi("原生序列 / N", "Native / N"), bi("CGAT 接纳 / N", "Accepted / N"), bi("对比", "Match")],
            rows,
            empty=bi("无染色体记录", "No chromosomes recorded"),
        )

    if all_identical:
        chr_inner = (
            '<div class="summary-line">'
            + badge_bi("全部一致", "All identical", "ok")
            + f'<span>{bi(f"{len(chr_list)}/{len(chr_list)} 条染色体与原生输出序列完全一致", f"{len(chr_list)}/{len(chr_list)} chromosomes identical to native output")}</span></div>'
            + disclosure(bi(f"展开全部 {len(chr_list)} 条染色体长度与 N 碱基表", f"Expand all {len(chr_list)} chromosomes"), _chr_table(chr_list))
        )
    elif diff_chrs:
        ident_n = len(chr_list) - len(diff_chrs)
        chr_inner = (
            f'<p class="muted">{bi(f"{len(diff_chrs)}/{len(chr_list)} 条染色体与原生输出存在差异或无法比较：", f"{len(diff_chrs)}/{len(chr_list)} chromosomes differ or are not comparable:")}</p>'
            + _chr_table(diff_chrs)
            + (disclosure(bi(f"展开其余 {ident_n} 条完全一致的染色体", f"Expand {ident_n} identical chromosomes"), _chr_table([r for r in chr_list if r["native_equals_accepted"] is True])) if ident_n else "")
        )
    else:
        chr_inner = '<p class="muted">' + bi("无染色体记录。", "No chromosomes recorded.") + '</p>'

    body += '<section id="chromosomes" class="panel"><div class="panel-head"><h2>' + bi("原生输出与 CGAT 接纳对比", "Native vs Accepted") + '</h2></div>' + chr_inner + '</section>'

    # 4. Original gaps -> jobs -> decisions (concise entry + paginated pages)
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
    total_gap_pages = (len(gaps) + page_size - 1) // page_size if gaps else 0
    for offset in range(0, len(gaps), page_size):
        number = offset // page_size + 1
        relative = f"gaps/{number:06d}.html"
        chunk = gaps[offset:offset + page_size]
        for gap in chunk:
            gap_page_map[gap["gap_id"]] = relative
        gap_links.append(link(relative, f"{offset + 1}–{min(offset + page_size, len(gaps))}"))

    for offset in range(0, len(gaps), page_size):
        number = offset // page_size + 1
        relative = f"gaps/{number:06d}.html"
        chunk = gaps[offset:offset + page_size]
        gap_nav = (
            link("../report.html", bi("返回工具报告", "Tool report"), raw=True)
            + link("../native.html", bi("原生任务与日志", "Native jobs & logs"), raw=True)
        )
        if number > 1:
            gap_nav += link(f"{number - 1:06d}.html", bi("上一页", "Previous"), raw=True)
        if number < total_gap_pages:
            gap_nav += link(f"{number + 1:06d}.html", bi("下一页", "Next"), raw=True)

        content = (
            '<div class="filter-bar" data-gap-filter-root="1" data-status-filter="all">'
            '<div class="filter-chips">'
            '<button type="button" class="ctrl-btn is-active" data-gap-chip="all">' + bi("全部", "All") + '</button>'
            '<button type="button" class="ctrl-btn" data-gap-chip="closed">' + bi("已闭合", "Closed") + '</button>'
            '<button type="button" class="ctrl-btn" data-gap-chip="partial">' + bi("部分填补", "Partial") + '</button>'
            '<button type="button" class="ctrl-btn" data-gap-chip="unfilled">' + bi("未填补", "Unfilled") + '</button>'
            '<button type="button" class="ctrl-btn" data-gap-chip="rejected">' + bi("已拒绝", "Rejected") + '</button>'
            '</div>'
            '<input type="search" data-gap-search="1" placeholder="搜索 Gap ID / 染色体 · Search..." aria-label="Filter gaps">'
            f'<span class="muted num" data-gap-count="1">{len(chunk)} / {len(chunk)}</span>'
            '</div>'
            '<p class="muted">' + bi("放置坐标：0-based 半开区间；原生诊断：1-based 闭区间。", "Placement: 0-based half-open; native diagnostics: 1-based inclusive.") + '</p>'
        )
        for gap in chunk:
            gid = gap["gap_id"]
            g_chr = gap.get("chromosome", "")
            g_start, g_end = gap.get("start"), gap.get("end")
            g_len = (g_end - g_start) if isinstance(g_start, int) and isinstance(g_end, int) else None
            g_status = gap.get("status") or "not_recorded"
            g_reasons = extract_recorded_reasons(gap)
            g_edits = [edits[name] for name in gap["edit_ids"]]
            g_rejected = rejected[gid]
            g_native = summary["native_gaps_by_original"].get(gid, [])
            g_jobs = jobs_by_gap[gid]

            card = f'<section id="{gap_anchor(gid)}" class="gap-card" data-gap-status="{esc(g_status)}">'
            card += (
                '<div class="card-head">'
                f'<h2>{esc(gid)}</h2>'
                f'<div class="count-chips">{status_badge(g_status)}'
                f'<span><code>{esc(g_chr)}</code>:<span class="num">{esc(fmt_int(g_start))}–{esc(fmt_int(g_end))}</span>'
                + (f' ({esc(fmt_int(g_len))} bp)' if g_len is not None else "")
                + '</span></div></div>'
            )
            if g_reasons:
                card += '<ul class="reason-list">' + "".join(f'<li><b>{esc(k)}</b>: {esc(v)}</li>' for k, v in g_reasons) + '</ul>'
            job_link_html = (
                " ".join(link("../native.html#" + gap_anchor(str(job["job_name"])), job["job_name"], cls="link-pill") for job in g_jobs)
                or link("../native.html", bi("原生诊断", "Native diagnostics"), cls="link-pill", raw=True)
            )
            card += f'<div class="link-row"><span class="muted">{bi("原生任务：", "Native jobs: ")}</span>{job_link_html}</div>'
            if g_native:
                ng_rows = []
                for ng in g_native:
                    ng_coords = f'{ng.get("chromosome", "")}:{fmt_int(ng.get("gap_start"))}–{fmt_int(ng.get("gap_end"))} (1-based incl.)'
                    ng_filled = ng.get("filled")
                    ng_filled_html = (
                        badge_bi("原生已补", "Filled (native)", "info") if ng_filled is True
                        else badge_bi("原生未补", "Not filled", "neutral") if ng_filled is False
                        else badge_bi("未记录", "Not recorded", "neutral")
                    )
                    ng_reasons = extract_recorded_reasons(ng)
                    ng_reason_cell = "; ".join(f"{k}: {v}" for k, v in ng_reasons) if ng_reasons else "—"
                    flank_statuses = [f"{d}: {ng[d + '_status']}" for d in ("left", "right") if ng.get(d + "_status") is not None]
                    if flank_statuses:
                        ng_filled_html += '<br><small class="muted">' + esc(" · ".join(flank_statuses)) + '</small>'
                    ng_rows.append((f'<code>{esc(ng.get("gap_id", ""))}</code>', f'<span class="num">{esc(ng_coords)}</span>', ng_filled_html, esc(ng.get("fill_direction") or "—"), esc(ng_reason_cell)))
                card += table([bi("原生 ID", "Native ID"), bi("坐标 (1-based 闭)", "Coords (1-based incl.)"), bi("原生判定", "Judgment"), bi("方向", "Dir"), bi("原因", "Reason")], ng_rows)
            if g_edits:
                card += '<h3>' + bi("接纳修改", "Accepted changes") + '</h3>' + _summarize_reasons_html(g_edits)
            flanks = retained_flanks(g_edits) + [
                row for candidate in g_rejected for row in candidate.get("flank_decisions", []) if row.get("decision") == "retained_lgz"
            ]
            if flanks:
                card += render_retained_flanks(flanks)
            if g_rejected:
                card += '<h3>' + bi("未接纳候选", "Not accepted") + '</h3>' + _summarize_reasons_html(g_rejected)
            raw_bundle = {"gap": gap, "accepted_edits": g_edits, "rejected_candidates": g_rejected, "native_gaps": g_native}
            card += disclosure(bi("原始记录 JSON", "Raw JSON"), '<pre>' + json_text(raw_bundle) + '</pre>')
            card += '</section>'
            content += card

        yield (
            relative,
            workbench_page(
                f"{tool} · 原始缺口明细",
                f"{tool} · Original Gaps",
                content,
                subtitle_html=bi(f"第 {offset + 1}–{min(offset + page_size, len(gaps))} / 共 {len(gaps):,} 个 · 第 {number}/{total_gap_pages} 页", f"Gaps {offset + 1}–{min(offset + page_size, len(gaps))} of {len(gaps):,} · Page {number}/{total_gap_pages}"),
                nav_html=gap_nav,
            ),
        )

    unattributed = [row for row in provenance["rejected_candidates"] if not row.get("gap_ids")]
    unattr_html = (
        '<h3>' + bi(f"无法归属原始缺口的未接纳候选 ({len(unattributed):,})", f"Unattributed rejected candidates ({len(unattributed):,})") + '</h3>'
        + _summarize_reasons_html(unattributed)
        + disclosure(bi("原始 JSON", "Raw JSON"), '<pre>' + json_text(unattributed) + '</pre>')
        if unattributed else ""
    )
    body += (
        '<section id="gaps-nav" class="panel">'
        '<div class="panel-head"><h2>' + bi("逐缺口决策明细", "Per-Gap Decisions") + '</h2></div>'
        + ('<div class="pager">' + "".join(gap_links) + '</div>' if gap_links else '<p class="muted">' + bi("无原始缺口", "No original gaps") + '</p>')
        + '<p class="muted">' + bi("放置坐标 0-based 半开区间；原生诊断 1-based 闭区间。", "Placement: 0-based half-open; native diagnostics: 1-based inclusive.") + '</p>'
        + unattr_html
        + '</section>'
    )

    # 5. Source evidence (optional, folded cleanly so it doesn't clutter the primary view)
    measured = summary.get("source_evidence")
    if measured is not None:
        sources = measured["sources"]
        ref_status_counts = Counter(row["ref_alignment_status"] for row in sources)
        ref_status_txt = " · ".join(f"{k}: {v}" for k, v in sorted(ref_status_counts.items())) or "—"
        source_summary_payload = {
            "patch_source_placements": len(sources),
            "reference_status": dict(ref_status_counts),
            "final_annotation_rows": measured["final_annotation_rows"],
            "policy": measured["annotation_policy"],
            "coordinate_domain": measured["coordinate_domain"],
        }
        src_pills = []
        if sources:
            pages = [sources[i:i + page_size] for i in range(0, len(sources), page_size)]
            src_pills.append(link("sources-0001.html", bi(f"全部来源定位表 ({len(sources):,})", f"All source placements ({len(sources):,})"), cls="link-pill", raw=True))
            for number, page_rows in enumerate(pages, 1):
                src_nav = link("report.html", bi("返回工具报告", "Tool report"), raw=True)
                if number > 1:
                    src_nav += link(f"sources-{number - 1:04}.html", bi("上一页", "Previous"), raw=True)
                if number < len(pages):
                    src_nav += link(f"sources-{number + 1:04}.html", bi("下一页", "Next"), raw=True)
                src_table_rows = []
                for row in page_rows:
                    ann = row["annotations"]
                    ann_str = json.dumps(ann, ensure_ascii=False)
                    ann_cell = (
                        disclosure(bi(f"注释 ({len(ann)})", f"Annotations ({len(ann)})"), '<pre>' + json_text(ann) + '</pre>')
                        if isinstance(ann, (list, dict)) and len(ann_str) > 120
                        else f'<code>{esc(ann_str)}</code>'
                    )
                    src_table_rows.append((
                        esc(row["dataset"]), f'<code>{esc(row["contig"])}</code>', f'<code>{esc(row["chromosome"])}</code>',
                        f'<span class="num">{esc(fmt_int(row["length"]))}</span>', status_badge(row["ref_alignment_status"]),
                        f'<span class="num">{esc(row["hits_on_chromosome"])} / {esc(row["reference_hits"])}</span>', ann_cell,
                    ))
                src_body = '<section class="panel">' + table(
                    [bi("来源", "Dataset"), "Contig", bi("染色体", "Chr"), bi("长度", "Length"), bi("参考比对", "Ref status"), bi("命中", "Hits"), bi("注释", "Annotations")],
                    src_table_rows,
                ) + '</section>'
                yield (
                    f"sources-{number:04}.html",
                    workbench_page(f"{tool} · 精修来源测量", f"{tool} · Source Measurements", src_body, subtitle_html=bi(f"第 {number}/{len(pages)} 页 · 来源 1-based 闭区间", f"Page {number}/{len(pages)} · 1-based inclusive"), nav_html=src_nav),
                )
        files = [row for row in assets if "/01_source_evidence/" in row["workspace_path"] and "/04_projection/" in row["workspace_path"]]
        for row in files:
            fname = Path(row["workspace_path"]).name
            lbl = bi("来源测量摘要 (summary.json)", "Source summary.json") if fname == "summary.json" else esc(fname)
            if row.get("report_path"):
                src_pills.append(link(row["report_path"], lbl, cls="link-pill", raw=True))
        src_inner = (
            '<div class="link-row">' + "".join(src_pills) + '</div>'
            + '<p class="muted">' + bi("坐标投影，非同源验证或全基因组重扫描。", "Coordinate projection; not homology or whole-genome rescan.") + '</p>'
            + disclosure(bi("来源策略 JSON", "Policy JSON"), '<pre>' + json_text(source_summary_payload) + '</pre>')
        )
        body += (
            '<section id="source-evidence" class="panel">'
            + disclosure(
                bi(f"来源证据（{len(sources):,} 个补丁定位 · 参考 {ref_status_txt} · {measured['final_annotation_rows']:,} 行注释）", f"Source evidence ({len(sources):,} placements · {ref_status_txt} · {measured['final_annotation_rows']:,} annotations)"),
                src_inner,
            )
            + '</section>'
        )

    # 6. Native diagnostics & metadata (folded cleanly, single entrypoint per resource)
    recipe = execution.get("recipe") or {}
    exec_payload = {
        "tool": tool, "run_id": run_id, "threads": execution.get("threads"),
        "timing": execution.get("timing", "not recorded"),
        "native_executed_this_attempt": native_executed, "native_reused": native_reused,
        "native_origin": native_origin, "requested_threads": execution.get("requested_threads"),
        "recipe": execution.get("recipe"), "launcher_command": execution.get("launcher_command"),
        "native_substeps": execution.get("native_substeps"), "command": execution.get("command"),
    }
    timing = execution.get("timing")
    if isinstance(timing, dict):
        t_parts = []
        if isinstance(timing.get("native_seconds"), (int, float)):
            t_parts.append(bi(f'原生 {fmt_duration(timing["native_seconds"])}', f'Native {fmt_duration(timing["native_seconds"])}'))
        if isinstance(timing.get("before_publication_seconds"), (int, float)):
            t_parts.append(bi(f'总计 {fmt_duration(timing["before_publication_seconds"])}', f'Total {fmt_duration(timing["before_publication_seconds"])}'))
        timing_cell = '<span class="num">' + " · ".join(t_parts) + '</span>' if t_parts else f'<code>{esc(json.dumps(timing, ensure_ascii=False))}</code>'
    elif timing is not None:
        timing_cell = f'<code>{esc(str(timing))}</code>'
    else:
        timing_cell = '<span class="muted">—</span>'
    recipe_name = recipe.get("name") or recipe.get("schema") or "—"
    origin_run = (native_origin or {}).get("run_id") if isinstance(native_origin, dict) else None
    meta_kv = [
        ("Run ID", f'<code>{esc(run_id)}</code>'),
        *([(bi("来源 Run", "Origin run"), f'<code>{esc(origin_run)}</code>')] if origin_run else []),
        (bi("线程", "Threads"), f'<span class="num">{esc(fmt_int(execution.get("threads")))}</span>'),
        (bi("配方", "Recipe"), f'<code>{esc(recipe_name)}</code>'),
        (bi("耗时", "Timing"), timing_cell),
    ]
    body += (
        '<section id="execution" class="panel">'
        '<div class="link-row" style="margin-top:0">'
        + link("native.html", bi("原生任务与日志", "Native jobs & logs"), cls="link-pill", raw=True)
        + link("native_visualization/index.html", bi("离线原生可视化", "Offline native visualization"), cls="link-pill", raw=True)
        + link("summary.json", bi("工具摘要 (summary.json)", "Tool summary.json"), cls="link-pill", raw=True)
        + link("final_path.json", "final_path.json", cls="link-pill")
        + '</div>'
        + disclosure(bi("运行参数与元数据 JSON", "Run parameters & metadata JSON"), kv_grid(meta_kv) + '<pre>' + json_text(exec_payload) + '</pre>')
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
    origin_run_id = (native_origin or {}).get("run_id", run_id)
    execution_log = next(
        (lookup[k] for k in (
            f"04_refinement/automatic/{tool}/02_jobs/{origin_run_id}/native.log",
            f"04_refinement/{TOOL_DIRECTORIES[tool]}/02_jobs/{origin_run_id}/native.log",
        ) if k in lookup),
        {},
    )
    native_nav = (
        link("report.html", bi("返回工具报告", "Tool report"), raw=True)
        + (link(execution_log["report_path"], bi("执行日志", "Execution log"), raw=True) if "report_path" in execution_log else "")
        + link("native_visualization/index.html", bi("离线原生可视化", "Offline native visualization"), raw=True)
    )
    job_count = len(summary["native_jobs"])
    native_body = (
        '<section class="panel"><div class="panel-head"><h2>' + bi("离线原生可视化", "Offline Native Visualization") + '</h2>' + status_badge(vis_status) + '</div>'
        + (f'<p class="muted"><code>{esc(vis_reason)}</code></p>' if vis_reason else "")
        + '<div class="link-row">' + link("native_visualization/index.html", bi("打开原生可视化目录", "Open native visualization index"), cls="link-pill", raw=True) + '</div>'
        + '</section>'
    )
    native_body += f'<section id="native-jobs" class="panel"><div class="panel-head"><h2>{bi(f"原生任务记录（{job_count:,}）", f"Native Jobs ({job_count:,})")}</h2></div>'
    if not summary["native_jobs"]:
        native_body += '<p class="muted">' + bi("未记录逐任务条目；请查看下方日志与原生文件。", "No per-job rows recorded; inspect logs and artifacts below.") + '</p>'
    else:
        for job in summary["native_jobs"]:
            jname = str(job.get("job_name"))
            j_badge, j_detail = _job_status_summary(job)
            orig_links = [
                link(gap_page_map[gid] + "#" + gap_anchor(gid), gid) if gid in gap_page_map else f'<code>{esc(gid)}</code>'
                for gid in job.get("original_gap_ids", [])
            ]
            art_links = []
            for name in job.get("artifacts", []):
                art = lookup.get(name, {})
                if "report_path" in art:
                    art_links.append(link(art["report_path"], Path(name).name, cls="link-pill"))
                else:
                    art_links.append(f'<span class="muted">{esc(Path(name).name)} ({esc(art.get("availability", "server_only"))})</span>')
            if job.get("visualization_html") in visualization_links:
                art_links.append(link(visualization_links[job["visualization_html"]], bi("离线视图", "Offline view"), cls="link-pill", raw=True))
            native_body += (
                '<article class="job-card" style="margin-top:.65rem">'
                f'<div class="card-head"><h2 id="{gap_anchor(jname)}">{esc(jname)}</h2>{j_badge}</div>'
                + kv_grid([
                    (bi("染色体", "Chr"), f'<code>{esc(job.get("chromosome") or "—")}</code>'),
                    (bi("原生缺口", "Native gap"), f'<code>{esc(job.get("native_gap_id") if job.get("native_gap_id") is not None else "—")}</code>'),
                    (bi("方向", "Direction"), f'<code>{esc(job.get("direction") or "—")}</code>'),
                    (bi("关联原始缺口", "Original gaps"), " · ".join(orig_links) if orig_links else '<span class="muted">—</span>'),
                ])
                + (f'<p class="muted">{esc(j_detail)}</p>' if j_detail else "")
                + (f'<div class="link-row">{"".join(art_links)}</div>' if art_links else "")
                + disclosure(bi("任务 JSON", "Job JSON"), '<pre>' + json_text(job) + '</pre>')
                + '</article>'
            )
    native_body += '</section>'

    art_rows = [
        (
            link(row["report_path"], row["workspace_path"]) if "report_path" in row else f'<code>{esc(row["workspace_path"])}</code>',
            status_badge(row["availability"]),
            f'<span class="num">{esc(fmt_bytes(row.get("size_bytes")))}</span>',
            f'<code>{esc(row["sha256"][:16])}…</code> ' + copy_btn(row["sha256"], zh="复制", en="Copy"),
        )
        for row in assets
    ]
    native_body += (
        '<section id="native-artifacts" class="panel">'
        + disclosure(
            bi(f"原生文件与校验值（{len(assets):,}）", f"Native Artifacts & Checksums ({len(assets):,})"),
            table([bi("文件", "Artifact"), bi("可用性", "Availability"), bi("大小", "Size"), "SHA-256"], art_rows, empty=bi("无文件记录", "No artifacts")),
            open_by_default=(len(assets) <= 20),
        )
        + '</section>'
    )
    yield (
        "native.html",
        workbench_page(f"{tool} · 原生任务与日志", f"{tool} · Native Jobs & Logs", native_body, nav_html=native_nav),
    )

    tool_sidebar = [
        ("counts", "", "缺口结果", "Outcomes"),
        ("chromosomes", "", "原生对比", "Native vs Accepted"),
        ("gaps-nav", "", "逐缺口明细", "Gap Details"),
    ]
    if measured is not None:
        tool_sidebar.append(("source-evidence", "", "来源证据", "Sources"))
    tool_sidebar.append(("execution", "", "日志与文件", "Logs & Files"))
    yield (
        "report.html",
        workbench_page(
            f"{tool} 精修结果",
            f"{tool} Refinement",
            body,
            sidebar_items=tool_sidebar,
            page_title_plain=f"{tool} 精修结果",
        ),
    )


def render_failure(summary):
    tool, run_id, phase, error = (summary[k] for k in ("tool", "run_id", "phase", "error"))
    jobs, assets = summary["native_jobs"], summary["artifacts"]
    diagnostics_error, source_diagnostics = summary["diagnostics_error"], summary["source_diagnostics"]
    vis_info = summary.get("native_visualization", {})
    vis_links = {
        source["workspace_path"]: row["wrapper_path"]
        for row in vis_info.get("views", []) if "wrapper_path" in row
        for source in row["sources"]
    }
    lookup = {row["workspace_path"]: row for row in assets}
    phase_zh, phase_en = PHASE_LABELS.get(phase, (phase, phase))

    fail_body = (
        '<section id="failure-summary" class="panel is-alert">'
        + callout(
            bi(f"失败阶段：{phase_zh}。本次无新发布，先前成功产物仍属历史结果。", f"Failed at {phase_en}. No new publication; earlier files remain historical."),
            tone="err",
        )
        + f'<div class="error-box">{esc(error)}</div>'
        + (callout(f'<code>{esc(diagnostics_error)}</code>', tone="warn") if diagnostics_error else "")
        + (f'<p class="muted">{bi("来源诊断：", "Source diagnostics: ")}<code>{esc(source_diagnostics)}</code></p>' if source_diagnostics else "")
        + '<div class="link-row">'
        + link("native_visualization/index.html", bi("离线原生可视化", "Offline native visualization"), cls="link-pill", raw=True)
        + link("summary.json", "summary.json", cls="link-pill")
        + '</div>'
    )
    if jobs:
        j_rows = []
        for job in jobs:
            j_badge, j_detail = _job_status_summary(job)
            j_links = [link(lookup[n]["report_path"], Path(n).name) for n in job.get("artifacts", []) if n in lookup and "report_path" in lookup[n]]
            if job.get("visualization_html") in vis_links:
                j_links.append(link(vis_links[job["visualization_html"]], bi("离线视图", "Offline view"), raw=True))
            j_rows.append((
                f'<code id="{gap_anchor(str(job.get("job_name")))}">{esc(job.get("job_name"))}</code>',
                f'<code>{esc(job.get("chromosome") or "—")}</code>',
                j_badge + (f' <small class="muted">{esc(j_detail)}</small>' if j_detail else ""),
                " · ".join(j_links) if j_links else "—",
            ))
        fail_body += disclosure(bi(f"已记录原生任务（{len(jobs):,}）", f"Recorded native jobs ({len(jobs):,})"), table([bi("任务", "Job"), bi("染色体", "Chr"), bi("状态", "Status"), bi("日志", "Logs")], j_rows))

    diag_rows = [
        (
            link(row["report_path"], row["workspace_path"]) if "report_path" in row else f'<code>{esc(row["workspace_path"])}</code>',
            status_badge(row["availability"]),
            f'<span class="num">{esc(fmt_bytes(row.get("size_bytes")))}</span>',
        )
        for row in assets
    ]
    fail_body += disclosure(
        bi(f"诊断文件与完整 JSON（{len(assets):,}）", f"Diagnostic artifacts & JSON ({len(assets):,})"),
        table([bi("文件", "Artifact"), bi("可用性", "Availability"), bi("大小", "Size")], diag_rows, empty=bi("无文件", "None"))
        + '<pre>' + json_text(summary) + '</pre>',
    )
    fail_body += '</section>'
    return workbench_page(
        f"{tool} 失败尝试",
        f"{tool} Failed Attempt",
        fail_body,
        subtitle_html=f'Run <code>{esc(run_id)}</code>',
        badge_html_str=status_badge("failed"),
    )
