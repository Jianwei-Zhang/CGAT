"""Static inline assets for the offline L/R family report. No job data in JS."""

CSS = """
body {background:var(--bg)}
.sheet {max-width:1200px;margin:0 auto;padding:20px 20px 44px;background:transparent}
.sheet h1,.sheet h2,.sheet h3,.sheet p,.sheet figure {margin:0}
.fr-header {background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:var(--shadow-xs);padding:16px 20px;margin-bottom:14px}
.sheet h1 {font-size:var(--text-page);font-weight:650;letter-spacing:-.02em;line-height:1.28;overflow-wrap:anywhere;color:var(--ink)}
.sub-id {margin-top:3px;font-family:var(--font-mono);font-size:var(--text-xs);color:var(--ink-muted)}
.sheet h2 {font-size:var(--text-card);line-height:1.3;font-weight:600;color:var(--ink)}
.sheet h3 {font-size:var(--text-sub);font-weight:600;color:var(--ink);margin:0 0 8px}
.kicker {font-size:0.72rem;font-weight:600;letter-spacing:.06em;color:var(--accent);text-transform:uppercase;margin-bottom:3px}
.top,.header-right,.section-title,.player-bar,.controls,.legend,.strip,.pills,.callout,.subhead-row {display:flex;align-items:center;flex-wrap:wrap;gap:8px 14px}
.top {justify-content:space-between;align-items:flex-start}
.subhead-row {justify-content:space-between;margin-bottom:8px}
.subhead-row h3 {margin:0}
.header-right {gap:8px;flex-shrink:0}
.lang-switch {display:inline-flex;align-items:center;background:var(--surface-muted);border:1px solid var(--border);border-radius:var(--radius-sm);padding:2px;gap:2px}
.lang-switch button {font-family:var(--font-sans);font-size:var(--text-xs);font-weight:600;border:0;background:transparent;color:var(--ink-muted);padding:3px 10px;border-radius:4px;cursor:pointer;min-width:38px;transition:background-color .12s ease,color .12s ease}
.lang-switch button:hover {color:var(--ink)}
.lang-switch button[aria-pressed="true"] {background:var(--surface);color:var(--ink);box-shadow:0 1px 2px rgba(15,23,42,.08)}
.strip {margin-top:12px;padding-top:10px;border-top:1px solid var(--border);font-size:var(--text-sm);gap:6px 22px;color:var(--ink-muted)}
.strip b {color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums;margin-left:4px}
.chapter {background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-md);box-shadow:var(--shadow-xs);margin-bottom:14px;overflow:hidden}
.sheet .section-title {background:transparent;border-bottom:1px solid var(--border);padding:12px 18px;margin:0;gap:8px;flex-wrap:nowrap}
.chapter-body {padding:14px 18px}
.player-bar {justify-content:space-between;align-items:center;gap:8px 12px;margin-bottom:10px}
.controls {gap:6px;flex-shrink:0}
.controls button {font-family:var(--font-sans);font-size:var(--text-xs);font-weight:600;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:var(--radius-sm);cursor:pointer;padding:5px 11px;transition:background-color .12s ease,border-color .12s ease}
.controls button:disabled {opacity:.45;cursor:default}
.controls button:hover:not(:disabled) {border-color:var(--accent);background:var(--accent-soft);color:var(--accent)}
.controls .play {background:var(--action-primary);color:#fff;border-color:var(--action-primary)}
.controls .play:hover:not(:disabled) {background:var(--accent-hover);border-color:var(--accent-hover);color:#fff}
.pills {gap:5px;max-height:76px;overflow:auto}
.pills button {font-family:var(--font-mono);font-size:var(--text-xs);font-weight:500;padding:3px 10px;border-radius:999px;border:1px solid var(--border-strong);background:var(--surface-subtle);color:var(--ink-secondary);cursor:pointer;transition:background-color .12s ease,border-color .12s ease}
.pills button:hover {border-color:var(--accent);color:var(--accent)}
.pills [aria-current="step"] {border-color:var(--accent);background:var(--accent-soft);color:var(--accent);font-weight:700}
.scene {background:var(--surface-subtle);border:1px solid var(--border);border-radius:var(--radius-sm);padding:8px 10px}
.graphic {width:100%;display:block;height:auto}
.canvas {min-width:0}
.graphic text {font-family:var(--font-sans);font-size:12.5px;fill:#334155}
.graphic .label {font-size:13px;font-weight:650;fill:#0f172a}
.graphic .delta {font-size:11.5px;fill:#ffffff;font-weight:650;font-family:var(--font-mono)}
.graphic .tick {font-size:11px;fill:#64748b;font-family:var(--font-mono)}
.graphic [data-current="true"] rect.seg-bar {stroke:#0f172a;stroke-width:1.6}
.sheet [hidden],.graphic [hidden] {display:none!important}
.caption {margin-top:10px;padding:10px 12px;background:var(--surface-subtle);border:1px solid var(--border);border-radius:var(--radius-sm);font-size:var(--text-sm);color:var(--ink-secondary)}
.caption strong {display:block;color:var(--ink);font-size:var(--text-body);margin-bottom:2px}
.unclosed-banner {margin-top:10px;padding:9px 12px;border-radius:var(--radius-sm);background:var(--warn-bg);border:1px solid var(--warn-border);color:var(--warn-ink);font-size:var(--text-sm);display:flex;flex-wrap:wrap;gap:4px 16px;align-items:baseline}
.unclosed-banner b {font-weight:600}
.note,.legend,.callout {font-size:var(--text-xs);color:var(--ink-muted)}
.note {margin-top:8px;line-height:1.5}
.callout {gap:6px 18px;margin-top:8px;font-size:var(--text-sm);color:var(--ink-secondary)}
.callout b {color:var(--ink);font-variant-numeric:tabular-nums}
.track-key {display:flex;flex-wrap:wrap;gap:4px 16px;margin-bottom:4px;font-size:var(--text-xs);font-family:var(--font-mono);font-variant-numeric:tabular-nums;color:var(--ink-secondary)}
.subhead-row .track-key {margin-bottom:0}
.track-key span::before {content:"";display:inline-block;width:14px;vertical-align:middle;border-top:3px solid #2563eb;margin-right:6px;border-radius:2px}
.track-key .track-R::before {border-top:3px dashed #d97706}
.trend {background:var(--surface-subtle);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px}
.subfig + .subfig {margin-top:16px;padding-top:14px;border-top:1px solid var(--border)}
.legend {gap:4px 14px}
.layout {display:grid;grid-template-columns:minmax(0,1.35fr) minmax(240px,0.85fr);gap:20px;margin-top:14px;align-items:start}
.well {overflow:auto;max-height:300px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface)}
.sheet table {font-size:var(--text-sm)}
.sheet td,.sheet th {padding:6px 9px}
.stop {font-size:var(--text-xs);color:var(--warn-ink);margin-top:6px}
.matrix {display:grid;width:max-content;min-width:140px;gap:4px;align-items:stretch;padding:8px;font-family:var(--font-mono);font-size:var(--text-xs);text-align:center}
.matrix span {padding:4px 7px;border-radius:4px}
.cell {border:1px solid transparent;transition:border-color .12s ease}
.cell:hover,.cell:focus-visible {border-color:var(--ink)}
.win {color:var(--ok-ink);background:var(--ok-bg);border-color:var(--ok-border);font-weight:700}
.pass {color:#1e40af;background:#eff6ff;border-color:#bfdbfe}
.reject {color:var(--warn-ink);background:var(--warn-bg);border-color:var(--warn-border)}
.none {color:var(--muted-ink);background:var(--muted-bg)}
.unknown {color:var(--ink-muted);background:var(--surface);border:1px dashed var(--border-strong)}
.drawer {border-top:1px solid var(--border);padding:2px 0}
.drawer:first-child {border-top:0}
.drawer > summary {list-style:none;cursor:pointer;padding:10px 0;font-size:var(--text-sub);font-weight:600;color:var(--ink-secondary);display:flex;align-items:center;gap:7px;user-select:none}
.drawer > summary::-webkit-details-marker {display:none}
.drawer > summary::before {content:"\\25B8";font-size:0.72rem;color:var(--ink-muted);transition:transform .12s ease}
.drawer[open] > summary::before {transform:rotate(90deg)}
.drawer > summary:hover {color:var(--ink)}
.drawer > .well,.drawer > nav,.drawer > .jr-root {margin:4px 0 12px}
.drawer > .jr-root {border:0;box-shadow:none}
.drawer > .jr-root > .section-header {display:none}
.drawer > .jr-root > .section-body {padding:4px 0 0}
.sheet footer {font-size:var(--text-xs);color:var(--ink-muted);padding:4px 2px 0}
.links {display:flex;flex-wrap:wrap;gap:6px 8px}
.links a:not([aria-disabled="true"]) {display:inline-flex;align-items:center;padding:3px 9px;border-radius:var(--radius-sm);border:1px solid var(--accent-border);background:var(--accent-soft);color:var(--accent);font-family:var(--font-mono);font-size:var(--text-xs);font-weight:500}
.links a:not([aria-disabled="true"]):hover {background:#dbeafe;text-decoration:none}
@media(max-width:768px){.layout{grid-template-columns:minmax(0,1fr);gap:14px}.sheet{padding:12px 12px 28px}.fr-header,.chapter-body{padding:12px 14px}.sheet .section-title{padding:10px 14px}
.controls button{font-size:12px;padding:4px 8px}.controls{gap:4px}.graphic .label{font-size:14px}.graphic .delta{display:none}
.caption,.track-key,.stop,.links {overflow-wrap:anywhere}.matrix span{padding:3px 5px}}
@media print {.controls,.pills,.lang-switch{display:none}.sheet{max-width:none;padding:0}.graphic{min-width:0}.chapter{break-inside:avoid;box-shadow:none}.well{max-height:none}}
"""

SCRIPT = """(() => {
  const root = document.querySelector('[data-player]');
  const pills = [...root.querySelectorAll('[data-step]')];
  const layers = [...root.querySelectorAll('[data-from]')];
  const captions = [...root.querySelectorAll('[data-caption]')];
  const play = root.querySelector('.play'), prev = root.querySelector('.prev'), next = root.querySelector('.next');
  const last = pills.length - 1;
  let step = last, clock = null;
  function langIsEn() {
    return !!(typeof document !== 'undefined' && document.documentElement && document.documentElement.getAttribute && document.documentElement.getAttribute('data-lang') === 'en');
  }
  function updatePlayLabel() {
    if (!play) return;
    play.textContent = clock !== null
      ? (langIsEn() ? 'Ⅱ Pause' : 'Ⅱ 暂停')
      : (langIsEn() ? '▶ Play' : '▶ 播放过程');
  }
  function stop() {
    clearInterval(clock); clock = null;
    updatePlayLabel(); play.setAttribute('aria-pressed', 'false');
  }
  function show(n) {
    step = n;
    pills.forEach((p,i) => p.setAttribute('aria-current', i === n ? 'step' : 'false'));
    captions.forEach((c,i) => c.hidden = i !== n);
    layers.forEach(el => {
      const from = Number(el.dataset.from);
      el.toggleAttribute('hidden', from > n);
      el.setAttribute('data-current', from === n && n > 0 ? 'true' : 'false');
    });
    prev.disabled = n === 0; next.disabled = n === last;
    if (n === last) stop();
  }
  pills.forEach((p,i) => p.addEventListener('click', () => {stop(); show(i);}));
  prev.addEventListener('click', () => {stop(); show(Math.max(0, step-1));});
  next.addEventListener('click', () => {stop(); show(Math.min(last, step+1));});
  play.addEventListener('click', () => {
    if (clock !== null) {stop(); return;}
    if (step === last) show(0);
    play.setAttribute('aria-pressed','true');
    clock = setInterval(() => show(Math.min(last,step+1)), 1300);
    updatePlayLabel();
  });
  show(last);
  if (document.documentElement && document.addEventListener && document.querySelectorAll) {
    document.addEventListener('click', (e) => {
      const btn = e.target && e.target.closest ? e.target.closest('[data-lang-switch] button[data-lang]') : null;
      if (!btn) return;
      const l = btn.getAttribute('data-lang') === 'en' ? 'en' : 'zh';
      document.documentElement.setAttribute('data-lang', l);
      document.documentElement.lang = l === 'zh' ? 'zh-CN' : 'en';
      document.querySelectorAll('[data-lang-switch] button[data-lang]').forEach(b => {
        b.setAttribute('aria-pressed', b.getAttribute('data-lang') === l ? 'true' : 'false');
      });
      updatePlayLabel();
    });
  }
})();"""
