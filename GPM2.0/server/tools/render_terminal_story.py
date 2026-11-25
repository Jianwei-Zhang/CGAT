"""q3 end markers and local before/candidate/result views. Never connect a missing PAF."""
from render_path_story import section
from render_refinement_report import bi, esc, fmt_bp_short
from render_repair_story import _coord


def _axis(lo,hi):
    return lambda x: 24+750*(x-lo)/max(1,hi-lo)


def _rect(span,axis,y,fill):
    start,end=map(axis,span)
    return f'<rect x="{min(start,end):.5f}" y="{y}" width="{abs(end-start):.5f}" height="8" fill="{fill}"/>'


def _zoom(t, cand, side, outsize):
    sel=t["selected"]; hits=((cand or {}).get("alignment") or {}).get("hits",[]); w=t["window"]
    qrange=[*w,*([sel["cut"]] if sel else []),*(n for h in hits for n in h["q2"])]; qax=_axis(min(qrange),max(qrange))
    svg=['<svg class="repair-zoom" viewBox="0 0 800 112" role="img" aria-label="Terminal evidence / 末端证据">']
    if cand:
        extract=cand["source"][1]-cand["source"][0];dax=_axis(0,extract)
        for h in hits:
            a,b=h["q2"];u,v=h["extract"] if h["strand"]=="+" else reversed(h["extract"])
            svg.append(f'<polygon points="{qax(a):.4f},19 {qax(b):.4f},19 {dax(v):.4f},55 {dax(u):.4f},55" opacity=".3" fill="var(--{("tone-warn-ink" if h["failed"] else ("ds-1" if h.get("selected") and cand["status"]=="accepted" else "text-muted"))})"/>')
        svg.append(_rect([0,extract],dax,55,"var(--border-strong)"))
        if sel and cand["event"]==sel["event"] and cand["status"]=="accepted" and cand["used"]:
            svg.append(_rect(cand["used"],dax,55,"var(--ds-1)"))
        for interval in cand["signals"] or []: svg.append(_rect(interval,dax,52,"var(--ds-2)"))
    svg.extend([_rect([min(qrange),max(qrange)],qax,11,"var(--text-muted)"),_rect(w,qax,11,"var(--gen-unfilled)")]);
    for interval in t["q2_signals"] or []: svg.append(_rect(interval,qax,10,"var(--ds-2)"))
    if sel:
        cut=qax(sel["cut"]);svg.append(f'<path d="M{cut:.4f} 4v22" stroke="var(--gen-patch)" stroke-width="2"/>')
        span=sel["span"]; lo=max(0,span[0]-(2000 if side=="3prime" else 0));hi=min(outsize,span[1]+(2000 if side=="5prime" else 0))
        ax=_axis(lo,hi);svg.extend([_rect([lo,hi],ax,91,"var(--text-muted)"),_rect(span,ax,91,"var(--ds-1)")]);
        for u,v in t["q3_signals"] or []:
            if min(hi,v)>max(lo,u):svg.append(_rect([max(lo,u),min(hi,v)],ax,89,"var(--ds-2)"))
    svg.append("</svg>");return "".join(svg)


def _inspection(t,side,size):
    if t is None:return bi("本次未记录此末端的检测结果。", "No assessment recorded for this end.")
    state=t["state"]; sel=t["selected"]; count=t["count"]
    names={"already_present":("原已具备端粒，未修改", "Telomere already present; unchanged"),"recovered":("已恢复端粒", "Terminal signal restored"),"unresolved":("未恢复，保留原末端", "Not recovered; original end retained")}
    msg=[f'<p><strong>{bi(*names[state])}</strong> · q2 {_coord(t["window"])}</p>'];cs=t["candidates"] or []
    def one(c):
        rows=[_zoom(t,c,side,size),bi("上轨：q2 检查窗口", "Top: q2 inspection window")]
        if c:
            rows.append(f'<p>{bi("中轨：定向候选", "Middle: oriented candidate")}　{esc(c["dataset"])} / {esc(c["name"])} ({esc(c["strand"])}) · {_coord(c["source"])}</p>')
        if sel:
            rows.append(f'<p>q2 {bi("切点", "cut")} {sel["cut"]:,} · {bi("下轨：实际写入 q3", "Bottom: inserted into q3")} {_coord(sel["span"])} · {esc(sel["dataset"])} / {esc(sel["name"])} ({esc(sel["strand"])}) {_coord(sel["source"])}</p>')
        if c and c["status"]!="accepted":
            reasons={"no_high_stringency_terminal_overlap":("没有比对同时通过末端重叠的全部门槛。","No alignment passed all terminal overlap gates."),
                     "validated_overlap_does_not_extend_terminal":("比对通过，但按切点取用后没有净延伸。","The overlap passed, but the cut would not extend the end."),
                     "telomere_repeat_not_at_external_end":("候选外端未检出合格的端粒重复。","No qualifying repeat was detected at the outer end of the candidate.")}
            reason=bi(*reasons[c["reason"]]) if c["reason"] in reasons else esc(c["reason"])
            rows.append(f'<p>{bi("未采用", "Not admitted")} · {reason}</p>')
        if c and c["alignment"]:
            gates=c["alignment"]["gates"]; hh=c["alignment"]["hits"]
            if not hh:rows.append(bi("已核对的 PAF 无匹配记录。", "Verified PAF contains no alignments."))
            for h in hh:
                limits=[]
                if "overlap" in h["failed"]: limits.append(f'{h["extract"][1]-h["extract"][0]:,} bp &lt; {gates["overlap"]:,} bp')
                if "mapq" in h["failed"]: limits.append(f'MAPQ {h["mapq"]} &lt; {gates["mapq"]}')
                if "identity" in h["failed"]: limits.append(f'{h["identity"]:.2%} &lt; {gates["identity"]:.2%}')
                if "strand" in h["failed"]:limits.append(bi("匹配方向不符","Wrong orientation"))
                if limits:rows.append("<p>q2 "+_coord(h["q2"])+" · "+" · ".join(limits)+"</p>")
        elif c: rows.append(bi("未记录可核对的候选 PAF；不绘制比对带。", "No verified candidate PAF available; no ribbon drawn."))
        return "".join(rows)
    primary=next((c for c in cs if sel and c["status"]=="accepted" and c["event"]==sel["event"]),None) or next(iter(cs),None)
    msg.append(one(primary));
    if t["q2_signals"] or t["q3_signals"] or primary and primary["signals"]:
        msg.append('<p><i class="q0-key" style="background:var(--ds-2)"></i> '+bi("已检测的端粒重复区间", "Measured terminal repeat intervals")+"</p>")
    elif state!="unresolved":msg.append(bi("历史记录未保存重复区间坐标。", "Repeat positions were not recorded in this snapshot."))
    if state=="unresolved" and not cs:
        msg.append(bi("本末端没有候选。", "No candidate recorded for this end.") if count==0 else bi("有候选，但缺少可核验的位点详情。", "Candidates were recorded, but their details are unavailable."))
    for c in cs:
        if c is not primary:msg.append("<details><summary>"+bi("另一候选", "Other candidate")+" · "+esc(c["name"])+"</summary>"+one(c)+"</details>")
    return "".join(msg)


def terminal_card(lgz):
    rows=lgz.get("terminal_scene"); head=("terminal-process","q2 → q3","端粒处理","Telomere processing")
    if not rows:return section(*head,bi("本次没有可核验的 q2 → q3 末端检测记录。", "No verifiable q2 → q3 end assessment is available."))
    m=max(r["length_bp"] for r in rows);path=lgz.get("stage_paths",{}).get("q3",{}); tracks={t["chr"]:t for t in (path.get("tracks") or [])}
    colors={v["name"]:f"var(--ds-{i%6})" for i,v in enumerate(lgz["inputs"]["assemblies"])}; body=[];templates=[]
    for row in rows:
        c=row["chr"];n=row["length_bp"];marks=[]; buttons=[];t=tracks.get(c)
        if path.get("sha256")==row["sha256"] and t and t["length_bp"]==n:
            for p in t["parts"]:
                color=colors.get(p.get("dataset"),"var(--gen-unfilled)");marks.append(f'<span class="repair-part" style="left:{100*p["start"]/n:.8g}%;width:{100*(p["end"]-p["start"])/n:.8g}%;background:{color}"></span>')
        for k in ("5prime","3prime"):
            info=row["ends"].get(k); text="TEL" if info and info["state"] in ("already_present","recovered") else "○"; end="5′" if k=="5prime" else "3′"; key=f"terminal-{len(templates)}"; title=esc(c)+" · "+end
            buttons.append(f'<button class="tel-end" type="button" data-story-open="{key}" aria-label="{title} · {text}" style="{("right:100%" if k=="5prime" else "left:100%")}">{text}</button>')
            templates.append(f'<template id="{key}" data-title="{title}">{_inspection(info,k,n)}</template>')
        body.append(f'<div class="repair-rows"><b>{esc(c)} <small>{fmt_bp_short(n)}</small></b><div style="padding-inline:2.1rem"><div style="position:relative;width:{100*n/m:.9g}%;padding:.9em 0"><div class="repair-base" style="background:var(--text-muted)">{"".join(marks)}</div>{"".join(buttons)}</div></div></div>')
    return section(*head,'<style>.tel-end{position:absolute;top:0;font:inherit;font-size:.78rem;cursor:pointer;color:var(--brand);background:var(--surface-panel);border:1px solid var(--border-strong);border-radius:.3em;padding:0 .22em}</style>'+"".join(body+templates))
