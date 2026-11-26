"""Static inline assets for the offline L/R family report. No job data in JS."""

CSS = """
body {background:#f5f7f6}
.sheet {max-width:1060px;margin:auto;padding:28px clamp(14px,4vw,46px);background:white;min-height:100vh}
.sheet h1,.sheet h2,.sheet h3,.sheet p,.sheet figure {margin:0}
.sheet h1 {font-size:clamp(20px,3vw,30px);font-weight:650;letter-spacing:-.035em;overflow-wrap:anywhere}
.sheet h2 {font-size:20px;line-height:1.3;font-weight:650;letter-spacing:-.02em}
.sheet h3 {font-size:14px;margin:8px 0}
.kicker,.section-no {font-size:11px;font-weight:700;letter-spacing:.12em;color:#48716b;text-transform:uppercase}
.top,.section-title,.controls,.legend,.strip,.pills,.callout {display:flex;align-items:center;flex-wrap:wrap;gap:8px 14px}
.top {justify-content:space-between}.strip {margin-top:13px;padding:9px 0;border-block:1px solid var(--border);font-size:13px;gap:4px 18px;color:var(--ink-secondary)}
.strip b {color:var(--ink);font-variant-numeric:tabular-nums}
.chapter {padding:18px 0;border-bottom:1px solid var(--border)}.sheet .section-title {margin-bottom:10px;gap:10px;flex-wrap:nowrap;background:transparent;border:0;padding:0}
.sheet button {font:inherit;font-size:13px;border:1px solid var(--border-strong);background:white;color:var(--ink);border-radius:5px;cursor:pointer;padding:5px 10px}
.sheet button:disabled {opacity:.49;cursor:default} .sheet button:hover:not(:disabled) {border-color:#247062}
.sheet .play {background:#185b50;color:white;border-color:#185b50}.controls {gap:6px}
.pills {gap:4px;margin:8px 0;max-height:92px;overflow:auto}.pills button {padding:3px 9px;border-radius:14px;font-size:12px}
.pills [aria-current=step] {border-color:#277769;background:#e3f2ed;color:#114e41;font-weight:700}
.scene {background:#f5f8f7;border-radius:6px;padding:4px 8px}.graphic {width:100%;display:block;height:auto}.canvas {min-width:0}
.graphic text {font:13px var(--font-sans);fill:#263f43}.graphic .label {font-size:14px;font-weight:650}.graphic .delta {font-size:12px;fill:white;font-weight:650}
.sheet [hidden],.graphic [hidden] {display:none!important}
.caption {padding:8px 2px;font-size:14px}.caption strong {display:block}.note,.legend,.callout {font-size:12px;color:#485965}.callout {gap:3px 16px}
.track-key {display:flex;flex-wrap:wrap;gap:3px 16px;margin-bottom:3px;font-size:13px;font-variant-numeric:tabular-nums}
.track-key span::before {content:"";display:inline-block;width:16px;vertical-align:middle;border-top:3px solid #426e99;margin-right:5px}
.track-key .track-R::before {border-top:3px dashed #a25c3d}.trend {background:#f7f9fa;border-radius:5px}.layout {margin-top:10px}
.subfig + .subfig {margin-top:12px;padding-top:9px;border-top:1px solid var(--border)}.legend {gap:4px 14px}
.layout {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:24px}.well {overflow:auto;max-height:300px}
.sheet table {font-size:13px}.sheet td,.sheet th {padding:5px 8px}.stop {font-size:12px;color:#875019}
.matrix {display:grid;width:max-content;min-width:120px;gap:3px;align-items:stretch;font:12px var(--font-mono);text-align:center}
.matrix span {padding:3px 6px}.cell {border-radius:4px}.win {color:#07543d;background:#c2e9da}.pass {color:#164d78;background:#dcebf8}
.reject {color:#764908;background:#f6e6bb}.none {color:#425462;background:#e8ecee}.unknown {color:#62717b;background:#fff;border:1px dashed #bdc7ca}
.drawer {border-bottom:1px solid var(--border);padding:8px 0}.drawer>summary {cursor:pointer;font-weight:600}.drawer>.well,.drawer>nav {margin:8px 0}
.sheet footer {font-size:12px;color:var(--ink-muted);padding:12px 0}.links {display:flex;flex-wrap:wrap;gap:8px 16px}
@media(max-width:700px){.layout{grid-template-columns:minmax(0,1fr);gap:10px}.sheet{padding-top:14px}.chapter{padding:14px 0}.section-title h2{font-size:17px}
.sheet button{font-size:12px;padding:5px 7px}.controls{gap:4px}.graphic .label{font-size:22px}.graphic .delta{display:none}
.trend .graphic text,.subfig .graphic text{font-size:18px}
.caption,.track-key,.stop,.links {overflow-wrap:anywhere}.matrix span{padding:3px 4px}}
@media print {.controls,.pills{display:none}.sheet{max-width:none;padding:0}.graphic{min-width:0}.chapter{break-inside:avoid}.well{max-height:none}}
"""

SCRIPT = """(() => {
  const root = document.querySelector('[data-player]');
  const pills = [...root.querySelectorAll('[data-step]')];
  const layers = [...root.querySelectorAll('[data-from]')];
  const captions = [...root.querySelectorAll('[data-caption]')];
  const play = root.querySelector('.play'), prev = root.querySelector('.prev'), next = root.querySelector('.next');
  const last = pills.length - 1;
  let step = last, clock = null;
  function stop() {
    clearInterval(clock); clock = null;
    play.textContent = '▶ 播放过程 / Play'; play.setAttribute('aria-pressed', 'false');
  }
  function show(n) {
    step = n;
    pills.forEach((p,i) => p.setAttribute('aria-current', i === n ? 'step' : 'false'));
    captions.forEach((c,i) => c.hidden = i !== n);
    layers.forEach(el => el.toggleAttribute('hidden', Number(el.dataset.from) > n));
    prev.disabled = n === 0; next.disabled = n === last;
    if (n === last) stop();
  }
  pills.forEach((p,i) => p.addEventListener('click', () => {stop(); show(i);}));
  prev.addEventListener('click', () => {stop(); show(Math.max(0, step-1));});
  next.addEventListener('click', () => {stop(); show(Math.min(last, step+1));});
  play.addEventListener('click', () => {
    if (clock !== null) {stop(); return;}
    if (step === last) show(0);
    play.textContent = 'Ⅱ 暂停 / Pause'; play.setAttribute('aria-pressed','true');
    clock = setInterval(() => show(Math.min(last,step+1)), 1300);
  });
  show(last);
})();"""
