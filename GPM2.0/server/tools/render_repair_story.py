"""Single shared offline inspector. All biological labels are escaped text."""
from heapq import heappop, heappush

from render_refinement_report import bi, esc
from render_path_story import section


DIALOG = """<dialog id="path-event-dialog" aria-labelledby="path-event-title"><header><b id="path-event-title"></b><button type="button" data-story-close aria-label="Close / 关闭">×</button></header><div data-story-content></div></dialog>
<style>html:has(#path-event-dialog){scrollbar-gutter:stable}html:has(#path-event-dialog[open]){overflow:hidden}#path-event-dialog{padding:1rem;box-sizing:border-box;width:min(860px,93vw);max-height:88vh;overflow:auto;color:var(--text-primary);background:var(--surface-panel);border:1px solid var(--border-default);border-radius:var(--radius);box-shadow:0 12px 50px #0004}#path-event-dialog::backdrop{background:#17232f66}#path-event-dialog header{display:flex;justify-content:space-between;align-items:center}.repair-zoom{width:100%;height:108px}.repair-rows{display:grid;grid-template-columns:minmax(6rem,12%) minmax(0,1fr);align-items:center;border-top:1px solid var(--border-subtle);padding:.5rem 0;gap:.7rem}.repair-rows small{display:block;color:var(--text-muted)}.repair-base{position:relative;height:9px}.repair-part{position:absolute;height:9px}.repair-hits{position:relative;min-height:19px}.repair-locus{position:absolute;top:0;transform:translateX(-50%);min-width:16px;border:0;background:transparent;color:var(--accent);padding:0 .12em;font-weight:bold;cursor:pointer}.repair-local{position:relative}.repair-local button{position:absolute;max-width:25%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.repair-mini{display:block;height:6px;background:var(--surface-muted);position:relative}.repair-mini i{position:absolute;height:6px;background:var(--ds-1)}.repair-local button{font:inherit;color:var(--text-primary);cursor:pointer;border:0;border-bottom:1px solid var(--border-strong);background:transparent;padding:.1rem .22rem}.repair-slice{display:inline-block;width:1.5em;height:5px;background:var(--ds-1);vertical-align:middle}</style>
<script data-cgat-ui="1" data-path-story-ui="1">(()=>{
  const panel=document.getElementById('path-event-dialog');
  let prior=null, scroll=0;
  function handleOpen(ev){
    const button=ev.target.closest('[data-story-open]');
    if(button){
      const t=document.getElementById(button.dataset.storyOpen);
      if(!t||t.tagName!=='TEMPLATE')return;
      prior=button; scroll=window.scrollY;
      panel.querySelector('#path-event-title').textContent=t.dataset.title;
      panel.querySelector('[data-story-content]').replaceChildren(t.content.cloneNode(true));
      panel.dispatchEvent(new CustomEvent("cgat-story-open",{bubbles:true,detail:{button}}));
      if(!panel.open)panel.showModal();
      return;
    }
    if(!panel.open)return;
    if(ev.target.closest('[data-story-close]'))panel.close();
    else if(ev.target===panel){const r=panel.getBoundingClientRect();
      if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)panel.close();}
  }
  document.addEventListener('click',handleOpen);
  document.addEventListener('cgat-locus-picker',handleOpen);
  panel.addEventListener('close',()=>{
    panel.querySelector('[data-story-content]').replaceChildren();
    if(prior&&prior.isConnected)prior.focus({preventScroll:true});
    window.scrollTo({top:scroll,left:window.scrollX,behavior:"instant"}); prior=null;
  });
})();</script>"""


def _zoom(e):
    donor = e["source"]
    a,b = e["before"]
    anchors = e["anchors"]
    # Separate, explicitly labelled local coordinate axes. Never extrapolate across the gap.
    qmin = min([a]+[h["q"][0] for h in anchors]); qmax = max([b]+[h["q"][1] for h in anchors])
    def axis(x,lo,hi):
        return 25 + (x-lo) * 750 / max(1,hi-lo)
    svg = ['<svg class="repair-zoom" viewBox="0 0 800 108" role="img" aria-label="Local repair evidence / 局部修补证据">']
    if donor:
        dmin=min([donor["start"]]+[h["source"][0] for h in anchors]); dmax=max([donor["end"]]+[h["source"][1] for h in anchors]); rev=donor["strand"]=="-"
        def dx(x): return axis(dmax-x if rev else x-dmin,0,dmax-dmin)
        for h in anchors:
            x,y=h["source"] if h["strand"]=="+" else h["source"][::-1]
            svg.append(f'<polygon points="{axis(h["q"][0],qmin,qmax):.4f},30 {axis(h["q"][1],qmin,qmax):.4f},30 {dx(y):.4f},77 {dx(x):.4f},77" fill="var(--ds-1)" opacity=".28"/>')
        start,end=sorted((dx(donor["start"]),dx(donor["end"])))
        svg.append(f'<path d="M25 81H775" stroke="var(--text-muted)" stroke-width="5"/><rect x="{start:.4f}" y="75" width="{end-start:.4f}" height="12" fill="var(--ds-1)"/>')
    lo,hi=axis(a,qmin,qmax),axis(b,qmin,qmax)
    # State only the changed interval, not that every base here is N: a repair may trim flanks.
    svg.append(f'<path d="M25 26H775" stroke="var(--text-muted)" stroke-width="5"/><rect x="{lo:.4f}" y="21" width="{hi-lo:.4f}" height="10" fill="var(--gen-patch)"/></svg>')
    return "".join(svg)


def _coord(span):
    a,b=span
    return f"{a+1:,}–{b:,}" if a<b else f"{a:,} | {a+1:,}"


def structural_detail(d):
    kind=d["kind"]; reason=f'<small>{esc(d["reason"])}</small>'
    if kind=="refill":
        src=d["source"]; local=d.get("local_before") or d["before"]
        title=bi("再填补：采用供体", "Refill: donor admitted")
        if d.get("round"):
            title+=f' · {bi("第", "Round")} {d["round"]} · '+bi("中间序列坐标", "Intermediate sequence coordinates")
        msg = _zoom({"source":src,"before":local,"anchors":d["anchors"]})
        msg+=f'<p>{esc(src["dataset"])} / {esc(src["name"])} ({src["strand"]}) · {_coord([src["start"],src["end"]])}</p>'
    elif kind=="filter":
        title=bi("筛选孤立片段", "Filter isolated components")
        # The filter ran on the corrected/refilled intermediate. Do not map these intervals onto q1 by offset.
        ranges=[(ab,bi("保留","Kept"),"--ds-1") for ab in d["kept"]]+[(ab,bi("移除","Removed") if d["applied"] else bi("未采用移除","Removal withheld"),"--tone-warn-line") for ab in d["removed"]]+[(ab,bi("受保护","Protected"),"--ds-2") for ab in d["protected"]]
        scale=max((ab[1] for ab,_,_ in ranges),default=1)
        msg=bi("筛选输入坐标", "Filter-input coordinates")+''.join(f'<div>{text} · {_coord(ab)}<div class="repair-base"><span class="repair-part" style="left:{100*ab[0]/scale:.6g}%;width:{100*(ab[1]-ab[0])/scale:.6g}%;background:var({color})"></span></div></div>' for ab,text,color in ranges)
    elif kind=="overlap":
        title=bi("侧翼直接去重接合", "Direct overlap closure")
        n=d["bp"]; a,b=map(esc,d["sides"])
        msg=f'<p>{a} <b>▰</b> · {n:,} bp · <b>▰</b> {b}</p>'+bi("两端精确重叠，只保留一份；未写入引导序列。", "The oriented ends overlap exactly. One copy remains; no guide sequence was inserted.")
    elif kind=="gap":
        title=bi("修正接缝，留下占位 Gap", "Correct the boundary; retain a placeholder gap")
        msg=f'<p>━━ ┊ {d["bp"]:,} N ┊ ━━</p>'+bi("引导比对用于决定切点，不是填入序列。", "Guide evidence locates the cut; the guide is not inserted.")
    elif kind=="remove":
        title=bi("移除被覆盖片段", "Remove redundant component");msg=bi("原区间被移除，没有新增供体序列。", "The interval was removed without inserting donor sequence.")
    else:
        title=bi("记录的结构修正", "Recorded correction");msg=esc(d["action"])
    if d.get("guide") and d["anchors"]:
        g=d["guide"]; spans=[a["source"] for a in d["anchors"]]; lo=min(ab[0] for ab in spans);hi=max(ab[1] for ab in spans)
        msg+=f'<p>q1 ↔ {esc(g["dataset"])} / {esc(g["name"])} · '+bi("引导比对（未写入）", "Guide alignment (not inserted)")+'</p>'
        msg+=_zoom({"before":d["before"],"anchors":d["anchors"],"source":{"start":lo,"end":hi,"strand":"+"}})
    return f'<div class="repair-decision"><strong>{title}</strong>{msg}<p>{reason}</p></div>'


def repair_card(lgz, structural=False):
    key, num, prior, after = (("structural-repair","05","q1","q2") if structural else ("first-repair","04","q0","q1"))
    zh,en=(("结构修正与再填补","Structural correction and refill") if structural else ("第一轮修补","First repair"))
    title_zh, title_en=f"{zh} · {prior} → {after}",f"{en} · {prior} → {after}"
    rows = lgz.get("step2_scene" if structural else "step1_scene")
    if rows is None:
        return section(key, num, title_zh, title_en, bi(f"未记录可核对的 {prior} → {after} 事件。",f"No verifiable {prior} → {after} event record."))
    path=lgz.get("stage_paths",{}).get("q1",{}) if structural else {"tracks":lgz.get("q0_scene"),"sha256":lgz.get("q0_scene_sha256")}
    domain=max([1]+[r["length_bp"] for r in rows]); base={t["chr"]:t for t in (path.get("tracks") or [])}
    colors={d["name"]:f"var(--ds-{i%6})" for i,d in enumerate(lgz["inputs"]["assemblies"])}
    body=[];templates=[]
    for r in rows:
        chrom=r["chr"];events=r["events"];n=len(events);length=r["length_bp"]
        state = bi(f"{n} 处修补",f"{n} repairs") if n else bi("未改动", "Unchanged")
        rail=[f'<span class="repair-part" style="left:0;width:{100*length/domain:.8g}%;background:var(--text-muted)"></span>']
        t=base.get(chrom)
        if t and t["length_bp"] == length and path.get("sha256") == r["input_sha256"]:
            for p in t["parts"]:
                color=colors.get(p.get("dataset"),"var(--gen-unfilled)")
                rail.append(f'<span class="repair-part" title="{esc(p.get("name",p["kind"]))}" style="left:{100*p["start"]/domain:.8g}%;width:{100*(p["end"]-p["start"])/domain:.8g}%;background:{color}"></span>')
        hits=[];local=[];lanes=[];nlanes=0
        for e in sorted(events,key=lambda e:e["before"]):
            target=f"{'step2' if structural else 'step1'}-inspect-{len(templates)}"; a,b=e["before"]; pos=50*(a+b)/domain
            span=_coord(e["before"]); title=esc(f"{chrom} · {prior} {span}")
            if not e.get("whole_chr"): hits.append(f'<button type="button" class="repair-locus" style="left:{pos:.8g}%" data-story-open="{target}" aria-label="{title}">◆</button>')
            src=e["source"]
            badge=f"{src['dataset']} / {src['name']} ({src['strand']})" if src else e["action"]
            # Keep the marker at its real q0 coordinate. Only label boxes are clamped to the plot.
            left=max(0,min(75,pos-12.5))
            lane=heappop(lanes)[1] if lanes and lanes[0][0]<=left else nlanes
            nlanes=max(nlanes,lane+1);heappush(lanes,(left+25,lane))
            mini=""
            if src:
                low=min([src["start"]]+[h["source"][0] for h in e["anchors"]]); high=max([src["end"]]+[h["source"][1] for h in e["anchors"]]); width=high-low
                offset=(src["start"]-low) if src["strand"]=="+" else (high-src["end"])
                mini=(f'<span class="repair-mini"><i style="left:{100*offset/width:.8g}%;'
                      f'width:{100*(src["end"]-src["start"])/width:.8g}%"></i></span>')
            local.append(f'<button type="button" data-story-open="{target}" style="left:{left:.8g}%;width:25%;top:{lane*2}em" title="{title} · {esc(badge)}">{mini}{esc(badge)}</button>')
            msg=[f'<p>q0 {span} → q1 {_coord(e["after"])}</p>', _zoom(e)]
            if src:
                msg.append("<p>"+bi("下轨：实际采用的供体区间", "Lower track: admitted donor slice")+f'　<b>{esc(badge)}</b> · {_coord([src["start"],src["end"]])}</p>')
            if src and not e["anchors"]:
                msg.append(bi("未记录可核对的两侧匹配坐标；不绘制比对带。", "Verified flank coordinates unavailable; no alignment ribbons shown."))
            if len(e["anchors"]) == 2:
                msg.append("<p>"+bi("q0 两侧均匹配同一供体；上图高亮的供体区间已写入 q1。", "Both q0 flanks match this donor; the highlighted donor slice is present in q1.")+"</p>")
            else:
                msg.append("<p>"+bi("采用依据", "Recorded decision")+f'：{esc(e["reason"])}</p>')
            if structural:
                msg=[f'<p>{prior} {span} → {after} {_coord(e["after"])}</p>']
                msg.extend(structural_detail(d) for d in e["history"])
            templates.append(f'<template id="{target}" data-title="{title}">{"".join(msg)}</template>')
        for d in r.get("inspections",[]):
            target=f"step2-inspect-{len(templates)}"; text=bi("查看筛选依据", "Filter decision")
            local.append(f'<button type="button" data-story-open="{target}" style="left:0;top:{nlanes*2}em">{text}</button>');nlanes+=1
            templates.append(f'<template id="{target}" data-title="{esc(chrom)} · Filter">{structural_detail(d)}</template>')
        body.append(f'<div class="repair-rows"><div><b>{esc(chrom)}</b><small>{state}</small></div><div><div class="repair-base" title="{prior} {length:,} bp">{"".join(rail)}</div>'
                    + (f'<div class="repair-hits">{"".join(hits)}</div><div class="repair-local" style="height:{nlanes*2}em">{"".join(local)}</div>' if local else "")+"</div></div>")
    return section(key, num, title_zh, title_en, "".join(body+templates))
