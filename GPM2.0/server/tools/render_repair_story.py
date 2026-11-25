"""Single shared offline inspector. All biological labels are escaped text."""
from heapq import heappop, heappush

try:
    from render_refinement_report import bi, esc, fmt_bp_short
    from render_path_story import section, zoom_button
except ModuleNotFoundError:
    from .render_refinement_report import bi, esc, fmt_bp_short
    from .render_path_story import section, zoom_button


REASON_LABELS = {
    "accepted_by_global_interval_arbitration": ("通过全局区间仲裁并采纳", "Admitted after global interval arbitration"),
    "selected": ("通过侧翼校验并采纳", "Validated on flanks and admitted"),
    "supported": ("接缝支持度校验通过", "Junction support validation passed"),
    "q0_component_protected": ("包含受保护的 q0 初始片段，不予移除", "Protected q0 component retained"),
}

ACTION_LABELS = {
    "patch": ("供体修补", "Donor patch"),
    "refill": ("供体再填补", "Donor refill"),
    "replace": ("接缝修正", "Junction update"),
    "correct_boundary": ("边界修正", "Boundary trim"),
    "filter_component": ("孤立片段筛选", "Component filter"),
}


def _human_reason(code):
    if code in REASON_LABELS:
        return bi(*REASON_LABELS[code])
    return f'<code>{esc(code)}</code>'


def _human_action(code):
    if code in ACTION_LABELS:
        return bi(*ACTION_LABELS[code])
    return esc(code)


DIALOG = """<dialog id="path-event-dialog" tabindex="-1" aria-labelledby="path-event-title"><header class="story-dlg-head"><div class="story-dlg-title-wrap"><b id="path-event-title"></b></div><button type="button" class="story-dlg-close" data-story-close aria-label="Close / 关闭">×</button></header><div class="story-dlg-body" data-story-content></div></dialog>
<style>
html:has(#path-event-dialog){scrollbar-gutter:stable}
html:has(#path-event-dialog[open]){overflow:hidden}
#path-event-dialog{padding:0;box-sizing:border-box;width:min(840px,94vw);max-height:88vh;overflow:auto;color:var(--text-primary);background:var(--surface-panel);border:1px solid var(--border-default);border-radius:10px;box-shadow:0 20px 50px rgba(15,23,42,.24)}
#path-event-dialog.is-wide{width:min(1480px,96vw);max-height:92vh}
#path-event-dialog:focus{outline:none}
#path-event-dialog::backdrop{background:rgba(15,23,42,.44);backdrop-filter:blur(1.5px)}
.story-dlg-head{position:sticky;top:0;z-index:5;display:flex;justify-content:space-between;align-items:center;gap:.75rem;padding:.85rem 1.15rem;background:var(--surface-panel);border-bottom:1px solid var(--border-subtle)}
.story-dlg-title-wrap{min-width:0;display:flex;align-items:baseline;gap:.55rem;flex-wrap:wrap}
#path-event-title{font-size:1.05rem;font-weight:700;letter-spacing:-.01em;line-height:1.35}
#path-event-title>span:not(.t-zh):not(.t-en){font-size:.85rem;font-weight:500;color:var(--text-muted)}
.story-dlg-close{flex-shrink:0;display:inline-grid;place-items:center;width:28px;height:28px;padding:0;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle);color:var(--text-secondary);font:600 18px/1 sans-serif;cursor:pointer;transition:background .12s,border-color .12s,color .12s}
.story-dlg-close:hover{background:var(--surface-hover);border-color:var(--border-default);color:var(--text-primary)}
.story-dlg-body{padding:1rem 1.15rem 1.15rem;font-size:.86rem;line-height:1.55}
.story-plot-frame{margin:.55rem 0;padding:.55rem .65rem;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-subtle)}
.story-meta-strip{display:flex;flex-wrap:wrap;gap:.35rem .9rem;align-items:center;font-size:.82rem;color:var(--text-secondary);margin:.35rem 0}
.story-meta-strip code{font-size:.82em}
.story-verdict{margin:.65rem 0 0;padding:.5rem .75rem;border-left:3px solid var(--brand);border-radius:0 var(--radius-sm) var(--radius-sm) 0;background:var(--surface-subtle);color:var(--text-primary);font-size:.84rem}
.story-verdict.is-ok{border-left-color:var(--gen-closed);background:var(--tone-ok-bg)}
.story-verdict.is-warn{border-left-color:var(--gen-patch);background:var(--tone-warn-bg)}
.repair-zoom{display:block;width:100%;height:auto}
.chart-zoom-btn{position:absolute;right:10px;bottom:8px;z-index:4;display:inline-flex;align-items:center;gap:.32rem;height:26px;padding:0 8px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-secondary);font:500 .75rem/1 inherit;cursor:pointer;box-shadow:0 1px 3px rgba(15,23,42,.07);transition:border-color .12s,background .12s,color .12s}
.chart-zoom-btn:hover{border-color:var(--brand);background:var(--brand-soft);color:var(--brand)}
.story-zoom-bar{display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;margin-bottom:.65rem}
.story-zoom-ctrl{display:inline-flex;align-items:center;gap:.3rem;font-size:.8rem}
.story-zoom-ctrl button{display:inline-grid;place-items:center;min-width:28px;height:28px;padding:0 .5rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-subtle);color:var(--text-primary);font:600 .8rem/1 var(--font-mono);cursor:pointer;transition:border-color .12s,background .12s,color .12s}
.story-zoom-ctrl button:hover:not(:disabled){border-color:var(--brand);background:var(--brand-soft);color:var(--brand)}
.story-zoom-ctrl button:disabled{opacity:.42;cursor:not-allowed}
.story-zoom-pct{min-width:44px;text-align:center;font:600 .8rem/1 var(--font-mono);color:var(--text-secondary);font-variant-numeric:tabular-nums}
.story-zoom-stage{overflow:auto;max-height:72vh;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel)}
.story-zoom-stage.is-pannable{cursor:grab}
.story-zoom-stage.is-dragging{cursor:grabbing;user-select:none}
</style>
<script data-cgat-ui="1" data-path-story-ui="1">(()=>{
  const panel=document.getElementById('path-event-dialog');
  let prior=null, scroll=0;
  function openCustom(d){
    if(!d||!d.content)return;
    prior=d.trigger||null; scroll=window.scrollY;
    panel.classList.toggle('is-wide',!!d.wide);
    const titleEl=panel.querySelector('#path-event-title');
    if(d.titleZh&&d.titleEn){
      const z=document.createElement('span');z.className='t-zh';z.textContent=d.titleZh;
      const e=document.createElement('span');e.className='t-en';e.textContent=d.titleEn;
      titleEl.replaceChildren(z,e);
    }else{titleEl.textContent=d.title||'';}
    panel.querySelector('[data-story-content]').replaceChildren(d.content);
    if(!panel.open){panel.showModal();panel.focus({preventScroll:true});}
  }
  function openChartZoom(btn){
    const srcFrame=btn.closest('[data-zoom-frame="1"]');
    const scope=btn.closest('[data-version-panel]')||btn.closest('.panel.path-story');
    if(!srcFrame)return;
    const wrap=document.createElement('div');
    const bar=document.createElement('div');
    bar.className='story-zoom-bar';
    const srcLegend=scope&&scope.querySelector('.legend-row');
    if(srcLegend)bar.appendChild(srcLegend.cloneNode(true));
    const ctrl=document.createElement('div');
    ctrl.className='story-zoom-ctrl';
    const steps=[1,1.5,2,3,4];
    let idx=0;
    const outBtn=document.createElement('button');outBtn.type='button';outBtn.textContent='−';outBtn.title='Zoom out';
    const pctEl=document.createElement('span');pctEl.className='story-zoom-pct';pctEl.textContent='100%';
    const inBtn=document.createElement('button');inBtn.type='button';inBtn.textContent='+';inBtn.title='Zoom in';
    const rstBtn=document.createElement('button');rstBtn.type='button';
    const rz=document.createElement('span');rz.className='t-zh';rz.textContent='重置';
    const re=document.createElement('span');re.className='t-en';re.textContent='Reset';
    rstBtn.append(rz,re);
    ctrl.append(outBtn,pctEl,inBtn,rstBtn);
    bar.appendChild(ctrl);
    const stage=document.createElement('div');
    stage.className='story-zoom-stage';
    const clone=srcFrame.cloneNode(true);
    const cBtn=clone.querySelector('.chart-zoom-btn');
    if(cBtn)cBtn.remove();
    stage.appendChild(clone);
    function applyZoom(){
      const s=steps[idx];
      clone.style.setProperty('--chart-scale',String(s));
      pctEl.textContent=Math.round(s*100)+'%';
      outBtn.disabled=idx<=0;
      inBtn.disabled=idx>=steps.length-1;
      rstBtn.disabled=idx===0;
      stage.classList.toggle('is-pannable',s>1);
    }
    let drag=null;
    stage.addEventListener('mousedown',(e)=>{
      if(e.button!==0||steps[idx]<=1||e.target.closest('button,select,a'))return;
      if(!e.target.closest('.q0-rails,.repair-track-col,.tel-gutter,.preview-rail,.story-ruler'))return;
      drag={x:e.clientX,y:e.clientY,sl:stage.scrollLeft,st:stage.scrollTop};
      stage.classList.add('is-dragging');
    });
    stage.addEventListener('mousemove',(e)=>{
      if(!drag)return;
      stage.scrollLeft=drag.sl-(e.clientX-drag.x);
      stage.scrollTop=drag.st-(e.clientY-drag.y);
    });
    const endDrag=()=>{if(drag){drag=null;stage.classList.remove('is-dragging');}};
    stage.addEventListener('mouseup',endDrag);
    stage.addEventListener('mouseleave',endDrag);
    outBtn.addEventListener('click',()=>{if(idx>0){idx--;applyZoom();}});
    inBtn.addEventListener('click',()=>{if(idx<steps.length-1){idx++;applyZoom();}});
    rstBtn.addEventListener('click',()=>{idx=0;applyZoom();stage.scrollLeft=0;});
    applyZoom();
    wrap.append(bar,stage);
    openCustom({
      trigger:btn,wide:true,
      titleZh:btn.dataset.zoomTitleZh||'放大视图',
      titleEn:btn.dataset.zoomTitleEn||'Enlarged view',
      content:wrap
    });
  }
  function handleOpen(ev){
    const zbtn=ev.target.closest('[data-chart-zoom="1"]');
    if(zbtn){openChartZoom(zbtn);return;}
    const button=ev.target.closest('[data-story-open]');
    if(button){
      const t=document.getElementById(button.dataset.storyOpen);
      if(!t||t.tagName!=='TEMPLATE')return;
      prior=button; scroll=window.scrollY;
      panel.classList.toggle('is-wide',t.dataset.wide==='1');
      const titleEl=panel.querySelector('#path-event-title');
      if(t.dataset.titleZh&&t.dataset.titleEn){
        const z=document.createElement('span');z.className='t-zh';z.textContent=t.dataset.titleZh;
        const e=document.createElement('span');e.className='t-en';e.textContent=t.dataset.titleEn;
        titleEl.replaceChildren(z,e);
      }else{titleEl.textContent=t.dataset.title||'';}
      panel.querySelector('[data-story-content]').replaceChildren(t.content.cloneNode(true));
      panel.dispatchEvent(new CustomEvent("cgat-story-open",{bubbles:true,detail:{button}}));
      if(!panel.open){panel.showModal();panel.focus({preventScroll:true});}
      return;
    }
    if(!panel.open)return;
    if(ev.target.closest('[data-story-close]'))panel.close();
    else if(ev.target===panel){const r=panel.getBoundingClientRect();
      if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)panel.close();}
  }
  panel.addEventListener('cgat-open-custom',(ev)=>openCustom(ev.detail));
  document.addEventListener('click',handleOpen);
  document.addEventListener('cgat-locus-picker',handleOpen);
  panel.addEventListener('close',()=>{
    panel.classList.remove('is-wide');
    panel.querySelector('[data-story-content]').replaceChildren();
    if(prior&&prior.isConnected)prior.focus({preventScroll:true});
    window.scrollTo({top:scroll,left:window.scrollX,behavior:"instant"}); prior=null;
  });
})();</script>"""

REPAIR_STYLE = """<style>
.repair-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.repair-axis,.repair-rows{display:grid;grid-template-columns:168px minmax(0,1fr);gap:.75rem;align-items:center}
.repair-axis{padding:.52rem .85rem .44rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600}
.repair-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:.75rem}
.repair-rows{border-bottom:1px solid var(--border-subtle);padding:.68rem .85rem;transition:background .12s}
.repair-rows.has-events{align-items:start}
.repair-rows:last-of-type{border-bottom:0}
.repair-rows:hover{background:var(--surface-subtle)}
.repair-chr-col{min-width:0}
.repair-chr-head{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.repair-chr-head b{font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary)}
.repair-state{display:inline-flex;align-items:center;padding:1px 7px;border-radius:999px;font-size:.71rem;font-weight:500;line-height:1.35;white-space:nowrap}
.repair-state.is-idle{color:var(--text-muted);background:var(--surface-subtle);border:1px solid var(--border-subtle)}
.repair-state.is-edited{color:var(--tone-warn-ink);background:var(--tone-warn-bg);border:1px solid var(--tone-warn-line);font-weight:600}
.repair-chr-len{display:block;margin-top:.16rem;font-size:.75rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.repair-track-col{min-width:0;padding:.14rem 0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.repair-base{position:relative;height:14px;border-radius:2px}
.repair-part{position:absolute;top:0;height:14px;border-radius:2px}
.repair-part.is-ctg{min-width:6px;z-index:1;box-shadow:inset 0 0 0 .7px rgba(255,255,255,.5)}
.repair-part.is-gap{min-width:5px;z-index:2;background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px)!important;box-shadow:inset 0 0 0 1px var(--border-strong)}
.repair-part.is-site{background:var(--gen-patch)!important;min-width:5px;z-index:3;border-radius:2px;box-shadow:inset 0 0 0 .8px rgba(255,255,255,.6)}
.repair-hits{position:relative;height:18px;margin-top:2px}
.repair-locus{position:absolute;top:0;transform:translateX(-50%);min-width:18px;height:18px;border:0;background:transparent;color:var(--gen-patch);padding:0;font-size:12px;line-height:18px;font-weight:700;cursor:pointer;z-index:3}
.repair-locus:hover{color:var(--brand);transform:translateX(-50%) scale(1.18)}
.repair-local{position:relative;margin-top:2px}
.repair-chip{position:absolute;display:inline-flex;align-items:center;gap:.38rem;max-width:32%;padding:.16rem .5rem;border:1px solid var(--border-default);border-radius:4px;background:var(--surface-panel);color:var(--text-primary);font:500 .76rem/1.25 var(--font-mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;box-shadow:0 1px 2px rgba(15,23,42,.05);transition:border-color .12s,background .12s}
.repair-chip:hover{border-color:var(--brand);background:var(--brand-soft)}
.repair-chip-txt{overflow:hidden;text-overflow:ellipsis}
.repair-mini{display:inline-block;width:24px;height:5px;border-radius:2px;background:var(--surface-muted);border:1px solid var(--border-subtle);position:relative;flex-shrink:0;overflow:hidden}
.repair-mini i{position:absolute;top:0;bottom:0;min-width:2px;background:var(--ds-1)}
.repair-decision{padding:.65rem .8rem;margin:.5rem 0;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-panel)}
.repair-decision-head{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;flex-wrap:wrap;margin-bottom:.35rem}
.repair-step-badge{display:inline-block;padding:.05rem .36rem;border-radius:3px;background:var(--brand-soft);color:var(--brand);font:600 .72rem/1.3 var(--font-mono);margin-right:.35rem}
.repair-junction-box{margin:.45rem 0;padding:.55rem .7rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
.repair-filter-row{margin:.35rem 0;font-size:.8rem}
.repair-filter-row .repair-base{margin-top:.18rem;height:10px;background:var(--surface-muted)}
.repair-filter-row .repair-part{height:10px}
.story-zoom-stage .repair-frame{border:0;border-radius:0;padding-bottom:0;overflow:visible;min-width:100%;width:calc(100% * var(--chart-scale, 1))}
.story-zoom-stage .repair-axis,.story-zoom-stage .repair-rows{grid-template-columns:196px minmax(0,1fr);gap:0;padding:0;align-items:stretch}
.story-zoom-stage .repair-axis{position:sticky;top:0;z-index:8;background:var(--surface-subtle)}
.story-zoom-stage .repair-axis>:first-child{position:sticky;left:0;z-index:9;background:var(--surface-subtle);padding:.55rem .7rem .45rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;align-items:center}
.story-zoom-stage .repair-axis .story-ruler{margin:.55rem 1rem .45rem .8rem;min-width:0}
.story-zoom-stage .repair-chr-col{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding:.85rem .7rem .85rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;flex-direction:column;justify-content:center}
.story-zoom-stage .repair-rows:hover .repair-chr-col{background:var(--surface-subtle)}
.story-zoom-stage .repair-track-col{margin:.85rem 1rem .85rem .8rem;z-index:1;display:flex;flex-direction:column;justify-content:center}
.story-zoom-stage .repair-base,.story-zoom-stage .repair-part{height:18px}
.story-zoom-stage .repair-part.is-ctg{min-width:7px}
.story-zoom-stage .repair-part.is-gap,.story-zoom-stage .repair-part.is-site{min-width:6px}
@media (max-width:760px){
  .repair-axis,.repair-rows{grid-template-columns:108px minmax(0,1fr);gap:.45rem;padding-left:.65rem;padding-right:.65rem}
  .repair-chip{max-width:44%;font-size:.72rem}
  .story-zoom-stage .repair-axis,.story-zoom-stage .repair-rows{grid-template-columns:136px minmax(0,1fr);gap:0;padding:0}
}
</style>"""


def _coord(span):
    a, b = span
    return f"{a+1:,}–{b:,}" if a < b else f"{a:,} | {a+1:,}"


def _zoom(e, *, top_label="q0", bottom_label="Donor", is_guide=False):
    donor = e["source"]
    a, b = e["before"]
    anchors = e["anchors"]
    # Separate, explicitly labelled local coordinate axes. Never extrapolate across the gap.
    qmin = min([a] + [h["q"][0] for h in anchors])
    qmax = max([b] + [h["q"][1] for h in anchors])
    if qmin == qmax:
        qmin = max(0, a - 50)
        qmax = b + 50
    pad_l, plot_w = 92, 680

    def axis(x, lo, hi):
        return pad_l + (x - lo) * plot_w / max(1, hi - lo)

    h_svg = 122 if donor else 64
    svg = [f'<svg class="repair-zoom" viewBox="0 0 800 {h_svg}" role="img" aria-label="Local repair evidence / 局部修补证据">']
    svg.append(f'<text x="8" y="34" font-size="11.5" font-weight="600" fill="var(--text-primary)">{esc(top_label)}</text>')
    svg.append(f'<text x="{pad_l}" y="16" font-size="10" fill="var(--text-muted)">{qmin+1:,}</text>')
    svg.append(f'<text x="{pad_l + plot_w}" y="16" text-anchor="end" font-size="10" fill="var(--text-muted)">{qmax:,}</text>')

    if donor:
        dmin = min([donor["start"]] + [h["source"][0] for h in anchors])
        dmax = max([donor["end"]] + [h["source"][1] for h in anchors])
        rev = donor["strand"] == "-"

        def dx(x):
            return axis(dmax - x if rev else x - dmin, 0, max(1, dmax - dmin))

        rib_fill = "var(--border-strong)" if is_guide else "var(--ds-1)"
        for h in anchors:
            x, y = h["source"] if h["strand"] == "+" else h["source"][::-1]
            svg.append(
                f'<polygon points="{axis(h["q"][0], qmin, qmax):.4f},36 {axis(h["q"][1], qmin, qmax):.4f},36 '
                f'{dx(y):.4f},84 {dx(x):.4f},84" fill="{rib_fill}" opacity=".26"/>'
            )
        start, end = sorted((dx(donor["start"]), dx(donor["end"])))
        svg.append(f'<text x="8" y="92" font-size="11.5" font-weight="600" fill="var(--text-secondary)">{esc(bottom_label)}</text>')
        l_coord = f"{dmax:,} (rev)" if rev else f"{dmin+1:,}"
        r_coord = f"{dmin+1:,}" if rev else f"{dmax:,}"
        svg.append(f'<text x="{pad_l}" y="112" font-size="10" fill="var(--text-muted)">{esc(l_coord)}</text>')
        svg.append(f'<text x="{pad_l + plot_w}" y="112" text-anchor="end" font-size="10" fill="var(--text-muted)">{esc(r_coord)}</text>')
        svg.append(f'<rect x="{pad_l}" y="85" width="{plot_w}" height="8" rx="2" fill="var(--border-default)"/>')
        if is_guide:
            svg.append(f'<rect x="{start:.4f}" y="84" width="{max(2.0, end-start):.4f}" height="10" rx="2" fill="var(--tone-info-line)" stroke="var(--accent)" stroke-dasharray="3 2"/>')
        else:
            svg.append(f'<rect x="{start:.4f}" y="83" width="{max(2.5, end-start):.4f}" height="12" rx="2" fill="var(--ds-1)"/>')

    lo, hi = axis(a, qmin, qmax), axis(b, qmin, qmax)
    # State only the changed interval, not that every base here is N: a repair may trim flanks.
    svg.append(f'<rect x="{pad_l}" y="26" width="{plot_w}" height="8" rx="2" fill="var(--border-strong)"/>')
    for h in anchors:
        qa, qb = axis(h["q"][0], qmin, qmax), axis(h["q"][1], qmin, qmax)
        svg.append(f'<rect x="{min(qa, qb):.4f}" y="26" width="{max(1.5, abs(qb-qa)):.4f}" height="8" fill="var(--brand)" opacity=".55"/>')
    svg.append(f'<rect x="{lo:.4f}" y="24" width="{max(2.5, hi-lo):.4f}" height="12" rx="2" fill="var(--gen-patch)"/>')
    mid = (lo + hi) / 2
    if b > a:
        svg.append(f'<text x="{min(pad_l + plot_w - 36, max(pad_l + 36, mid)):.1f}" y="16" text-anchor="middle" font-size="10" font-weight="600" fill="var(--tone-warn-ink)">{b-a:,} bp</text>')
    svg.append("</svg>")
    return f'<div class="story-plot-frame">{"".join(svg)}</div>'


def structural_detail(d, step_idx=None, total_steps=1):
    kind = d["kind"]
    step_tag = f'<span class="repair-step-badge">{step_idx}/{total_steps}</span>' if step_idx and total_steps > 1 else ""
    reason_html = _human_reason(d["reason"])
    if kind == "refill":
        src = d["source"]
        local = d.get("local_before") or d["before"]
        title = bi("再填补：采用供体片段", "Refill: donor slice admitted")
        if d.get("round"):
            rnd = d["round"]
            rnd_lbl = bi(f"第 {rnd} 轮 · 中间序列坐标", f"Round {rnd} · intermediate coordinates")
            title += f' · <small class="muted">{rnd_lbl}</small>'
        msg = _zoom({"source": src, "before": local, "anchors": d["anchors"]}, top_label="q1*", bottom_label=src["name"])
        slice_bp = src["end"] - src["start"]
        msg += (
            '<div class="story-meta-strip">'
            f'<span>{bi("采用供体：", "Admitted donor: ")}<b>{esc(src["dataset"])} / {esc(src["name"])}</b> ({esc(src["strand"])})</span>'
            f'<span>{bi("切取区间：", "Slice: ")}<code>{_coord([src["start"], src["end"]])}</code> ({slice_bp:,} bp)</span>'
            '</div>'
        )
        if not d["anchors"]:
            msg += '<p class="muted">' + bi("未记录可核对的两侧匹配坐标；不绘制比对带。", "Verified flank coordinates unavailable; no alignment ribbons shown.") + '</p>'
    elif kind == "filter":
        title = bi("筛选孤立片段", "Filter isolated components")
        # The filter ran on the corrected/refilled intermediate. Do not map these intervals onto q1 by offset.
        ranges = (
            [(ab, bi("保留", "Kept"), "--ds-1") for ab in d["kept"]]
            + [(ab, bi("移除", "Removed") if d["applied"] else bi("未采用移除", "Removal withheld"), "--gen-patch") for ab in d["removed"]]
            + [(ab, bi("受保护", "Protected"), "--ds-2") for ab in d["protected"]]
        )
        scale = max((ab[1] for ab, _, _ in ranges), default=1)
        rows_html = "".join(
            f'<div class="repair-filter-row"><span><b>{text}</b> · <code>{_coord(ab)}</code> ({ab[1]-ab[0]:,} bp)</span>'
            f'<div class="repair-base"><span class="repair-part" style="left:{100*ab[0]/scale:.6g}%;width:{max(0.6, 100*(ab[1]-ab[0])/scale):.6g}%;background:var({color})"></span></div></div>'
            for ab, text, color in ranges
        )
        msg = '<p class="muted">' + bi("筛选输入坐标（中间序列）", "Filter-input coordinates (intermediate sequence)") + '</p>' + rows_html
    elif kind == "overlap":
        title = bi("侧翼直接去重接合（无 Gap）", "Direct overlap closure (gapless)")
        n = d["bp"]
        a, b = map(esc, d["sides"])
        diagram = (
            '<div class="repair-junction-box">'
            '<svg class="repair-zoom" viewBox="0 0 800 78" role="img" aria-label="Direct overlap deduplication / 重叠去重接合">'
            '<text x="8" y="25" font-size="11" font-weight="600" fill="var(--text-secondary)">q1</text>'
            '<rect x="88" y="16" width="300" height="9" rx="2" fill="var(--ds-0)"/>'
            '<rect x="338" y="15" width="50" height="11" rx="1" fill="var(--ds-1)"/>'
            '<rect x="412" y="15" width="50" height="11" rx="1" fill="var(--ds-1)"/>'
            '<rect x="412" y="16" width="300" height="9" rx="2" fill="var(--ds-3)" opacity=".85"/>'
            '<path d="M363 30V38H437V30" stroke="var(--text-muted)" fill="none"/>'
            '<text x="8" y="62" font-size="11" font-weight="600" fill="var(--text-primary)">q2</text>'
            '<rect x="88" y="53" width="300" height="10" rx="2" fill="var(--ds-0)"/>'
            '<rect x="388" y="53" width="250" height="10" rx="2" fill="var(--ds-3)"/>'
            '</svg>'
            f'<div class="story-meta-strip"><span><b>{a}</b> ↔ <b>{b}</b></span><span>{bi("精确末端重叠：", "Exact terminal overlap: ")}<b>{n:,} bp</b></span></div>'
            '</div>'
        )
        msg = diagram + '<p>' + bi("两条定向来源片段首尾精确重叠，移除间隔 N 与重复前缀后只保留一份，未插入引导序列。", "Oriented source ends overlap exactly; one copy is retained and no guide sequence was inserted.") + '</p>'
    elif kind == "gap":
        title = bi("修正边界切点，保留占位 Gap", "Boundary refined; placeholder gap retained")
        diagram = (
            '<div class="repair-junction-box">'
            '<svg class="repair-zoom" viewBox="0 0 800 46" role="img" aria-label="Placeholder gap retained / 保留占位 Gap">'
            '<text x="8" y="28" font-size="11" font-weight="600" fill="var(--text-primary)">q2</text>'
            '<rect x="88" y="18" width="265" height="10" rx="2" fill="var(--ds-0)"/>'
            '<rect x="353" y="18" width="94" height="10" fill="var(--tone-warn-bg)" stroke="var(--gen-patch)"/>'
            f'<text x="400" y="27" text-anchor="middle" font-size="10.5" font-weight="700" fill="var(--tone-warn-ink)">{d["bp"]:,} N</text>'
            '<rect x="447" y="18" width="265" height="10" rx="2" fill="var(--ds-3)"/>'
            '</svg></div>'
        )
        msg = diagram + '<p>' + bi("两侧比对在引导序列上定位切点，但来源序列本身不直接重叠；此处保留序列占位 N，引导序列不写入 q2。", "Guide alignments locate the trim points, not an inserted sequence; placeholder Ns remain in q2.") + '</p>'
    elif kind == "remove":
        title = bi("移除冗余被覆盖片段", "Remove redundant component")
        msg = '<p>' + bi("原区间被相邻可靠片段覆盖而移除，没有新增供体序列。", "The redundant interval was removed without inserting donor sequence.") + '</p>'
    else:
        title = bi("记录的结构修正", "Recorded correction")
        msg = f'<p><code>{esc(d["action"])}</code></p>'

    if d.get("guide") and d["anchors"]:
        g = d["guide"]
        spans = [a["source"] for a in d["anchors"]]
        lo = min(ab[0] for ab in spans)
        hi = max(ab[1] for ab in spans)
        msg += (
            '<div class="story-meta-strip">'
            f'<span>{bi("引导参照（未写入 q2）：", "Guide alignment (not inserted): ")}<b>{esc(g["dataset"])} / {esc(g["name"])}</b></span>'
            '</div>'
        )
        msg += _zoom({"before": d["before"], "anchors": d["anchors"], "source": {"start": lo, "end": hi, "strand": "+"}},
                     top_label="q1", bottom_label="Guide", is_guide=True)
    return (
        f'<div class="repair-decision">'
        f'<div class="repair-decision-head"><strong>{step_tag}{title}</strong><small class="muted">{reason_html}</small></div>'
        f'{msg}</div>'
    )


def repair_card(lgz, structural=False):
    key, num, prior, after = (("structural-repair", "05", "q1", "q2") if structural else ("first-repair", "04", "q0", "q1"))
    zh, en = (("结构修正与再填补", "Structural correction and refill") if structural else ("第一轮修补", "First repair"))
    rows = lgz.get("step2_scene" if structural else "step1_scene")
    if rows is None:
        return section(key, num, zh, en,
                       '<p class="muted">' + bi(f"未记录可核对的 {prior} → {after} 事件。", f"No verifiable {prior} → {after} event record.") + "</p>",
                       sub_zh=f"{prior} → {after}", sub_en=f"{prior} → {after}")
    path = lgz.get("stage_paths", {}).get("q1", {}) if structural else {"tracks": lgz.get("q0_scene"), "sha256": lgz.get("q0_scene_sha256")}
    domain = max([1] + [r["length_bp"] for r in rows])
    base = {t["chr"]: t for t in (path.get("tracks") or [])}
    colors = {d["name"]: f"var(--ds-{i%6})" for i, d in enumerate(lgz["inputs"]["assemblies"])}

    total_events = sum(len(r["events"]) for r in rows)
    edited_chrs = sum(1 for r in rows if r["events"])
    right_summary = (
        bi(f"{edited_chrs} 条 chr · 共 {total_events} 处改动", f"{edited_chrs} chr · {total_events} edits")
        if total_events else bi("全部染色体未改动", "All chromosomes unchanged")
    )

    legend = [f'<span class="legend-item"><i class="swatch" style="background:{c}"></i>{esc(ds)}</span>' for ds, c in colors.items()]
    legend.append('<span class="legend-item"><i class="swatch is-orig-gap"></i>Gap</span>')
    if total_events:
        legend.append('<span class="legend-item"><b style="color:var(--gen-patch)">◆</b> ' + bi("点击查看局部证据", "Click locus for local evidence") + '</span>')

    body = [
        REPAIR_STYLE,
        '<div class="story-toolbar"><div class="legend-row" style="margin:0">' + "".join(legend) + '</div></div>',
        '<div class="repair-frame" data-zoom-frame="1">',
        f'<div class="repair-axis"><span>{bi("染色体", "Chromosome")}</span><span class="story-ruler">'
        + "".join(f"<span>{esc(fmt_bp_short(round(domain * i / 4)))}</span>" for i in range(5)) + "</span></div>",
    ]
    templates = []
    for r in rows:
        chrom = r["chr"]
        events = r["events"]
        n = len(events)
        length = r["length_bp"]
        out_len = r.get("output_bp", length)
        if n:
            verb = bi(f"{n} 处修正", f"{n} edits") if structural else bi(f"{n} 处修补", f"{n} repairs")
            state_badge = f'<span class="repair-state is-edited">{verb}</span>'
        else:
            state_badge = f'<span class="repair-state is-idle">{bi("未改动", "Unchanged")}</span>'
        len_note = (
            f"{fmt_bp_short(length)} → {fmt_bp_short(out_len)}"
            if out_len is not None and out_len != length else fmt_bp_short(length)
        )
        rail = [f'<span class="repair-part" style="left:0;width:{100*length/domain:.8g}%;background:var(--border-strong)"></span>']
        t = base.get(chrom)
        if t and t["length_bp"] == length and path.get("sha256") == r["input_sha256"]:
            for p in t["parts"]:
                is_src = p["kind"] == "source"
                color = colors.get(p.get("dataset"), "var(--ds-0)") if is_src else "var(--gen-unfilled)"
                cls = "repair-part is-ctg" if is_src else "repair-part is-gap"
                rail.append(
                    f'<span class="{cls}" title="{esc(p.get("name", p["kind"]))}" '
                    f'style="left:{100*p["start"]/domain:.8g}%;width:{100*(p["end"]-p["start"])/domain:.8g}%;background:{color}"></span>'
                )
        hits = []
        local = []
        lanes = []
        nlanes = 0
        for e in sorted(events, key=lambda e: e["before"]):
            target = f"{'step2' if structural else 'step1'}-inspect-{len(templates)}"
            a, b = e["before"]
            pos = 50 * (a + b) / domain
            span = _coord(e["before"])
            title = esc(f"{chrom} · {prior} {span}")
            if not e.get("whole_chr"):
                rail.append(f'<span class="repair-part is-site" style="left:{100*a/domain:.8g}%;width:{100*max(1, b-a)/domain:.8g}%"></span>')
                hits.append(f'<button type="button" class="repair-locus" style="left:{pos:.8g}%" data-story-open="{target}" title="{title}" aria-label="{title}">◆</button>')
            src = e["source"]
            badge_html = f'{esc(src["dataset"])}/{esc(src["name"])} ({esc(src["strand"])})' if src else _human_action(e["action"])
            badge_plain = f"{src['dataset']} / {src['name']} ({src['strand']})" if src else e["action"]
            # Keep the marker at its real coordinate. Compact chip avoids implying a megabase span.
            left = max(0, min(67, pos - 6.5))
            lane = heappop(lanes)[1] if lanes and lanes[0][0] <= left else nlanes
            nlanes = max(nlanes, lane + 1)
            heappush(lanes, (left + 33.0, lane))
            mini = ""
            if src:
                low = min([src["start"]] + [h["source"][0] for h in e["anchors"]])
                high = max([src["end"]] + [h["source"][1] for h in e["anchors"]])
                width = max(1, high - low)
                offset = (src["start"] - low) if src["strand"] == "+" else (high - src["end"])
                mini = (f'<span class="repair-mini" aria-hidden="true"><i style="left:{100*offset/width:.8g}%;'
                        f'width:{max(8.0, 100*(src["end"]-src["start"])/width):.8g}%"></i></span>')
            local.append(
                f'<button type="button" class="repair-chip" data-story-open="{target}" '
                f'style="left:{left:.8g}%;top:{lane*1.95}rem" title="{title} · {esc(badge_plain)}">'
                f'{mini}<span class="repair-chip-txt">{badge_html}</span></button>'
            )
            if not structural:
                before_bp = e["before"][1] - e["before"][0]
                after_bp = e["after"][1] - e["after"][0]
                msg = [
                    '<div class="story-meta-strip">'
                    f'<span><b>{esc(prior)}</b> <code>{span}</code> ({before_bp:,} bp)</span>'
                    f'<span>→</span>'
                    f'<span><b>{esc(after)}</b> <code>{_coord(e["after"])}</code> ({after_bp:,} bp)</span>'
                    '</div>',
                    _zoom(e, top_label=prior, bottom_label=src["name"] if src else "Donor"),
                ]
                if src:
                    msg.append(
                        '<div class="story-meta-strip">'
                        f'<span>{bi("采用供体：", "Admitted donor: ")}<b>{esc(badge_plain)}</b></span>'
                        f'<span>{bi("切取区间：", "Slice: ")}<code>{_coord([src["start"], src["end"]])}</code> ({src["end"]-src["start"]:,} bp)</span>'
                        '</div>'
                    )
                if src and not e["anchors"]:
                    msg.append('<p class="muted">' + bi("未记录可核对的两侧匹配坐标；不绘制比对带。", "Verified flank coordinates unavailable; no alignment ribbons shown.") + '</p>')
                if len(e["anchors"]) == 2:
                    msg.append('<div class="story-verdict is-ok">' + bi("q0 两侧均匹配同一供体；上图高亮的供体切取区间已写入 q1。", "Both q0 flanks match this donor; the highlighted donor slice is admitted into q1.") + '</div>')
                else:
                    msg.append('<div class="story-verdict">' + bi("采用依据：", "Recorded decision: ") + _human_reason(e["reason"]) + '</div>')
            else:
                before_bp = e["before"][1] - e["before"][0]
                after_bp = e["after"][1] - e["after"][0]
                msg = [
                    '<div class="story-meta-strip">'
                    f'<span><b>{esc(prior)}</b> <code>{span}</code> ({before_bp:,} bp)</span>'
                    f'<span>→</span>'
                    f'<span><b>{esc(after)}</b> <code>{_coord(e["after"])}</code> ({after_bp:,} bp)</span>'
                    '</div>'
                ]
                hist = e["history"]
                msg.extend(structural_detail(d, idx, len(hist)) for idx, d in enumerate(hist, 1))
            templates.append(f'<template id="{target}" data-title="{title}">{"".join(msg)}</template>')
        for d in r.get("inspections", []):
            target = f"step2-inspect-{len(templates)}"
            text = bi("查看筛选依据", "Filter decision")
            local.append(f'<button type="button" class="repair-chip" data-story-open="{target}" style="left:0;top:{nlanes*1.95}rem"><span class="repair-chip-txt">{text}</span></button>')
            nlanes += 1
            templates.append(f'<template id="{target}" data-title="{esc(chrom)} · Filter">{structural_detail(d)}</template>')
        row_cls = "repair-rows has-events" if local else "repair-rows"
        body.append(
            f'<div class="{row_cls}">'
            f'<div class="repair-chr-col"><div class="repair-chr-head"><b>{esc(chrom)}</b>{state_badge}</div>'
            f'<small class="repair-chr-len">{esc(len_note)}</small></div>'
            f'<div class="repair-track-col"><div class="repair-base" title="{prior} {length:,} bp">{"".join(rail)}</div>'
            + (f'<div class="repair-hits">{"".join(hits)}</div><div class="repair-local" style="height:{nlanes*1.95:.3g}rem">{"".join(local)}</div>' if local else "")
            + "</div></div>"
        )
    body.append(zoom_button(f"{num} {zh} · 放大视图", f"{num} {en} · Enlarged view") + "</div>")
    return section(key, num, zh, en, "".join(body + templates),
                   sub_zh=f"{prior} → {after}", sub_en=f"{prior} → {after}",
                   right=right_summary)
