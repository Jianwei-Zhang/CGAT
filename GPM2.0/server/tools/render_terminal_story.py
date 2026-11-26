"""q3 end markers and local before/candidate/result views. Never connect a missing PAF."""
try:
    from render_path_story import section, zoom_button
    from render_refinement_report import bi, esc, fmt_bp_short
    from render_repair_story import _coord
except ModuleNotFoundError:
    from .render_path_story import section, zoom_button
    from .render_refinement_report import bi, esc, fmt_bp_short
    from .render_repair_story import _coord


TERMINAL_STYLE = """<style>
.tel-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.tel-axis,.tel-row{display:grid;grid-template-columns:168px minmax(0,1fr);gap:.75rem;align-items:center}
.tel-axis{padding:.52rem .85rem .44rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600}
.tel-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:.75rem}
.tel-axis-pad{padding-inline:2.45rem}
.tel-row{border-bottom:1px solid var(--border-subtle);padding:.68rem .85rem;transition:background .12s}
.tel-row:last-of-type{border-bottom:0}
.tel-row:hover{background:var(--surface-subtle)}
.tel-chr-col{min-width:0}
.tel-chr-head{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.tel-chr-col b{font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tel-chr-col small{display:block;margin-top:.16rem;font-size:.75rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.tel-pill{display:inline-flex;align-items:center;padding:1px 6px;border-radius:999px;font-size:.71rem;font-weight:500;font-variant-numeric:tabular-nums;border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-muted);white-space:nowrap}
.tel-pill.is-full{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.tel-pill.is-part{border-color:var(--tone-info-line);background:var(--tone-info-bg);color:var(--tone-info-ink)}
.tel-gutter{padding-inline:2.45rem;min-width:0}
.tel-canvas{background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%;padding:.2rem 0}
.tel-bar-wrap{position:relative;min-width:8px;height:24px;display:flex;align-items:center}
.tel-bar{position:relative;width:100%;height:14px;border-radius:2px;background:var(--border-strong);overflow:hidden}
.tel-part{position:absolute;top:0;height:14px;border-radius:2px}
.tel-part.is-ctg{min-width:6px;z-index:1;box-shadow:inset 0 0 0 .7px rgba(255,255,255,.5)}
.tel-part.is-gap{min-width:5px;z-index:2;background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px)!important;box-shadow:inset 0 0 0 1px var(--border-strong)}
.tel-end{position:absolute;top:50%;transform:translateY(-50%);display:inline-flex;align-items:center;justify-content:center;font:700 .7rem/1 var(--font-mono);cursor:pointer;border-radius:999px;padding:.22rem .4rem;white-space:nowrap;transition:transform .1s,border-color .12s,background .12s}
.tel-end.is-5p{right:calc(100% + 5px)}
.tel-end.is-3p{left:calc(100% + 5px)}
.tel-end.is-present{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border:1px solid var(--tone-ok-line)}
.tel-end.is-present:hover{background:var(--gen-tel);border-color:var(--gen-tel);color:#fff}
.tel-end.is-missing{color:var(--text-secondary);background:var(--surface-panel);border:1px solid var(--border-strong);padding:.18rem .38rem;font-size:.73rem}
.tel-end.is-missing:hover{border-color:var(--brand);color:var(--brand);background:var(--brand-soft)}
.tel-cand-fold{margin-top:.5rem;padding-top:.45rem;border-top:1px dashed var(--border-subtle)}
.tel-cand-fold>summary{cursor:pointer;font-size:.8rem;font-weight:600;color:var(--accent)}
.tel-dlg-head{display:flex;align-items:center;justify-content:space-between;gap:.5rem .85rem;flex-wrap:wrap;padding:.5rem .72rem;border:1px solid var(--border-subtle);border-left:3px solid var(--border-strong);border-radius:var(--radius-sm);background:var(--surface-subtle);font-size:.83rem;line-height:1.4}
.tel-dlg-head.is-ok{border-left-color:var(--gen-closed);background:var(--tone-ok-bg)}
.tel-dlg-status{display:inline-flex;align-items:center;gap:.45rem;flex-wrap:wrap}
.tel-dlg-status strong{color:var(--text-primary);font-weight:600}
.tel-dlg-sub{padding:1px 7px;border-radius:999px;border:1px solid var(--border-subtle);background:var(--surface-panel);color:var(--text-secondary);font-size:.73rem;font-weight:500}
.tel-dlg-win{font-size:.78rem;color:var(--text-secondary);font-variant-numeric:tabular-nums;white-space:nowrap}
.tel-dlg-win code{font-size:.78rem}
.tel-dlg-plot{margin:.5rem 0 0;padding:.45rem .65rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
.tel-dlg-meta{display:flex;flex-wrap:wrap;gap:.3rem .85rem;margin:.45rem 0 0;font-size:.8rem;color:var(--text-secondary);line-height:1.45}
.tel-dlg-meta code{font-size:.79rem}
.tel-dlg-note{margin:.42rem 0 0;font-size:.79rem;color:var(--text-muted);line-height:1.45}
.tel-dlg-reject{margin:.45rem 0 0;padding:.38rem .6rem;border-radius:var(--radius-sm);background:var(--tone-warn-bg);border:1px solid var(--tone-warn-line);color:var(--tone-warn-ink);font-size:.8rem;line-height:1.45}
.tel-gate-list{margin:.35rem 0 0;padding-left:1.1rem;font-size:.79rem;color:var(--tone-warn-ink);line-height:1.45}
.story-zoom-stage .tel-frame{border:0;border-radius:0;padding-bottom:0;overflow:visible;min-width:100%;width:calc(100% * var(--chart-scale, 1))}
.story-zoom-stage .tel-axis,.story-zoom-stage .tel-row{grid-template-columns:196px minmax(0,1fr);gap:0;padding:0;align-items:stretch}
.story-zoom-stage .tel-axis{position:sticky;top:0;z-index:8;background:var(--surface-subtle)}
.story-zoom-stage .tel-axis>:first-child{position:sticky;left:0;z-index:9;background:var(--surface-subtle);padding:.55rem .7rem .45rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;align-items:center}
.story-zoom-stage .tel-axis-pad{margin:.55rem 1rem .45rem .8rem;padding-inline:2.45rem}
.story-zoom-stage .tel-chr-col{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding:.85rem .7rem .85rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;flex-direction:column;justify-content:center}
.story-zoom-stage .tel-row:hover .tel-chr-col{background:var(--surface-subtle)}
.story-zoom-stage .tel-gutter{margin:.85rem 1rem .85rem .8rem;padding-inline:2.45rem;display:flex;align-items:center}
.story-zoom-stage .tel-canvas{width:100%}
.story-zoom-stage .tel-bar-wrap{height:28px}
.story-zoom-stage .tel-bar,.story-zoom-stage .tel-part{height:18px}
.story-zoom-stage .tel-part.is-ctg{min-width:7px}
.story-zoom-stage .tel-part.is-gap{min-width:6px}
@media (max-width:760px){
  .tel-axis,.tel-row{grid-template-columns:108px minmax(0,1fr);gap:.4rem;padding-left:.65rem;padding-right:.65rem}
  .tel-axis-pad,.tel-gutter{padding-inline:2.05rem}
  .story-zoom-stage .tel-axis,.story-zoom-stage .tel-row{grid-template-columns:136px minmax(0,1fr);gap:0;padding:0}
}
</style>"""


def _axis(lo, hi, pad_l=96, width=676):
    return lambda x: pad_l + width * (x - lo) / max(1, hi - lo)


def _rect(span, axis, y, fill, h=9, rx=2):
    start, end = map(axis, span)
    return f'<rect x="{min(start, end):.5f}" y="{y}" width="{max(1.8, abs(end - start)):.5f}" height="{h}" rx="{rx}" fill="{fill}"/>'


def _zoom(t, cand, side, outsize):
    sel = t["selected"]
    hits = ((cand or {}).get("alignment") or {}).get("hits", [])
    w = t["window"]
    qrange = [*w, *([sel["cut"]] if sel else []), *(n for h in hits for n in h["q2"])]
    qlo, qhi = min(qrange), max(qrange)
    compact = not cand and not sel
    vb_w = 560 if compact else 800
    pad_l = 42 if compact else 96
    plot_w = vb_w - pad_l - (14 if compact else 28)
    qax = _axis(qlo, qhi, pad_l=pad_l, width=plot_w)
    svg_h = 136 if sel else (92 if cand else 44)
    svg = [f'<svg class="repair-zoom" viewBox="0 0 {vb_w} {svg_h}" role="img" aria-label="Terminal evidence / 末端证据">']

    # Track 1: q2 terminal inspection window
    svg.append('<text x="6" y="31" font-size="11.5" font-weight="600" fill="var(--text-primary)">q2</text>')
    svg.append(f'<text x="{pad_l}" y="14" font-size="10" fill="var(--text-muted)">{qlo+1:,}</text>')
    svg.append(f'<text x="{pad_l + plot_w}" y="14" text-anchor="end" font-size="10" fill="var(--text-muted)">{qhi:,}</text>')

    if cand:
        extract = cand["source"][1] - cand["source"][0]
        dax = _axis(0, extract, pad_l=pad_l, width=plot_w)
        for h in hits:
            a, b = h["q2"]
            u, v = h["extract"] if h["strand"] == "+" else reversed(h["extract"])
            tone = "tone-warn-ink" if h["failed"] else ("ds-0" if h.get("selected") and cand["status"] == "accepted" else "text-muted")
            svg.append(f'<polygon points="{qax(a):.4f},32 {qax(b):.4f},32 {dax(v):.4f},66 {dax(u):.4f},66" opacity=".26" fill="var(--{tone})"/>')
        cname = cand["name"] if len(cand["name"]) <= 12 else cand["name"][:11] + "…"
        svg.append(f'<text x="6" y="74" font-size="11" font-weight="600" fill="var(--text-secondary)"><title>{esc(cand["name"])}</title>{esc(cname)}</text>')
        svg.append(_rect([0, extract], dax, 66, "var(--border-strong)"))
        if sel and cand["event"] == sel["event"] and cand["status"] == "accepted" and cand["used"]:
            svg.append(_rect(cand["used"], dax, 65, "var(--ds-0)", h=11))
        for interval in cand["signals"] or []:
            svg.append(_rect(interval, dax, 61, "var(--gen-tel)", h=5, rx=1))

    svg.append(_rect([qlo, qhi], qax, 22, "var(--border-default)", h=10))
    svg.append(_rect(w, qax, 22, "var(--tone-info-line)", h=10))
    for interval in t["q2_signals"] or []:
        svg.append(_rect(interval, qax, 20, "var(--gen-tel)", h=14))

    if sel:
        cut = qax(sel["cut"])
        svg.append(f'<path d="M{cut:.4f} 16v22" stroke="var(--gen-patch)" stroke-width="2.2"/>')
        span = sel["span"]
        lo = max(0, span[0] - (2000 if side == "3prime" else 0))
        hi = min(outsize, span[1] + (2000 if side == "5prime" else 0))
        ax = _axis(lo, hi, pad_l=pad_l, width=plot_w)
        svg.append('<text x="6" y="116" font-size="11.5" font-weight="600" fill="var(--text-primary)">q3</text>')
        svg.append(f'<text x="{pad_l}" y="132" font-size="10" fill="var(--text-muted)">{lo+1:,}</text>')
        svg.append(f'<text x="{pad_l + plot_w}" y="132" text-anchor="end" font-size="10" fill="var(--text-muted)">{hi:,}</text>')
        svg.append(_rect([lo, hi], ax, 108, "var(--border-strong)"))
        svg.append(_rect(span, ax, 107, "var(--ds-0)", h=11))
        for u, v in t["q3_signals"] or []:
            if min(hi, v) > max(lo, u):
                svg.append(_rect([max(lo, u), min(hi, v)], ax, 103, "var(--gen-tel)", h=5, rx=1))

    svg.append("</svg>")
    return f'<div class="tel-dlg-plot">{"".join(svg)}</div>'


def _inspection(t, side, size):
    if t is None:
        return '<p class="tel-dlg-note">' + bi("本次未记录该末端检测结果。", "No assessment recorded for this end.") + '</p>'
    state = t["state"]
    sel = t["selected"]
    count = t["count"]
    states = {
        "already_present": ("原已具备端粒", "Telomere present", "未修改", "Unchanged"),
        "recovered": ("已补齐端粒", "Telomere restored", "写入 q3", "Added to q3"),
        "unresolved": ("未检出端粒", "No telomere", "保留原末端", "Kept unchanged"),
    }
    zh_main, en_main, zh_sub, en_sub = states[state]
    tone_cls = "is-ok" if state in ("already_present", "recovered") else ""
    win_bp = t["window"][1] - t["window"][0]
    msg = [
        f'<div class="tel-dlg-head {tone_cls}">'
        f'<div class="tel-dlg-status"><strong>{bi(zh_main, en_main)}</strong>'
        f'<span class="tel-dlg-sub">{bi(zh_sub, en_sub)}</span></div>'
        f'<span class="tel-dlg-win">{bi("检测窗口", "Window")} <code>{_coord(t["window"])}</code> ({win_bp:,} bp)</span>'
        '</div>'
    ]
    cs = t["candidates"] or []

    def one(c):
        rows = [_zoom(t, c, side, size)]
        meta_bits = []
        if c:
            meta_bits.append(
                f'<span>{bi("候选供体：", "Candidate: ")}<b>{esc(c["dataset"])} / {esc(c["name"])}</b> '
                f'({esc(c["strand"])}) <code>{_coord(c["source"])}</code></span>'
            )
        if sel:
            meta_bits.append(
                f'<span>q2 {bi("切点", "cut")} <code>{sel["cut"]:,}</code> → q3 '
                f'<code>{_coord(sel["span"])}</code></span>'
            )
        if meta_bits:
            rows.append('<div class="tel-dlg-meta">' + "".join(meta_bits) + '</div>')
        if c and c["status"] != "accepted":
            reasons = {
                "no_high_stringency_terminal_overlap": ("未通过末端重叠质控门槛。", "Failed terminal overlap QC gates."),
                "validated_overlap_does_not_extend_terminal": ("比对通过，但切点后无净延伸。", "Overlap passed, but yields no net extension."),
                "telomere_repeat_not_at_external_end": ("候选外端未检出端粒重复。", "No telomere repeat at candidate outer end."),
            }
            reason = bi(*reasons[c["reason"]]) if c["reason"] in reasons else f'<code>{esc(c["reason"])}</code>'
            rows.append(f'<div class="tel-dlg-reject"><b>{bi("未采纳", "Rejected")}</b> · {reason}</div>')
        if c and c["alignment"]:
            gates = c["alignment"]["gates"]
            hh = c["alignment"]["hits"]
            if not hh:
                rows.append('<p class="tel-dlg-note">' + bi("已核对的 PAF 无匹配记录。", "Verified PAF contains no alignments.") + '</p>')
            gate_items = []
            for h in hh:
                limits = []
                if "overlap" in h["failed"]:
                    limits.append(f'{h["extract"][1]-h["extract"][0]:,} bp &lt; {gates["overlap"]:,} bp')
                if "mapq" in h["failed"]:
                    limits.append(f'MAPQ {h["mapq"]} &lt; {gates["mapq"]}')
                if "identity" in h["failed"]:
                    limits.append(f'{h["identity"]:.2%} &lt; {gates["identity"]:.2%}')
                if "strand" in h["failed"]:
                    limits.append(bi("方向不符", "Wrong strand"))
                if limits:
                    gate_items.append(f'<li>q2 <code>{_coord(h["q2"])}</code> · {" · ".join(limits)}</li>')
            if gate_items:
                rows.append('<ul class="tel-gate-list">' + "".join(gate_items) + '</ul>')
        elif c:
            rows.append('<p class="tel-dlg-note">' + bi("缺少可核对的 PAF，未绘制比对带。", "No verified PAF available; alignment ribbon omitted.") + '</p>')
        return "".join(rows)

    primary = next((c for c in cs if sel and c["status"] == "accepted" and c["event"] == sel["event"]), None) or next(iter(cs), None)
    msg.append(one(primary))
    if t["q2_signals"] or t["q3_signals"] or (primary and primary["signals"]):
        msg.append('<p class="tel-dlg-note"><i class="swatch" style="background:var(--gen-tel);margin-right:.35rem"></i>' + bi("绿色区间：检出的端粒重复序列", "Green: detected telomere repeat intervals") + "</p>")
    elif state != "unresolved":
        msg.append('<p class="tel-dlg-note">' + bi("已检出端粒基序（本快照未保存具体重复坐标）。", "Telomere motif detected (repeat coordinates not stored in this snapshot).") + '</p>')
    if state == "unresolved" and not cs:
        msg.append('<p class="tel-dlg-note">' + (
            bi("未找到可用候选供体，保留 q2 原末端。", "No candidate donor found; original q2 end retained.")
            if count == 0 else bi(f"记录到 {count} 条候选，但缺少位点明细。", f"{count} candidate(s) recorded without locus details.")
        ) + '</p>')
    for c in cs:
        if c is not primary:
            msg.append('<details class="tel-cand-fold"><summary>' + bi("其他候选", "Other candidate") + " · " + esc(c["name"]) + "</summary>" + one(c) + "</details>")
    return "".join(msg)


def terminal_card(lgz):
    rows = lgz.get("terminal_scene")
    head = ("terminal-process", "06", "端粒处理", "Telomere processing")
    if not rows:
        return section(*head, '<p class="muted">' + bi("本次没有可核验的 q2 → q3 末端检测记录。", "No verifiable q2 → q3 end assessment is available.") + '</p>',
                       sub_zh="q2 → q3", sub_en="q2 → q3")
    m = max([1] + [r["length_bp"] for r in rows])
    path = lgz.get("stage_paths", {}).get("q3", {})
    tracks = {t["chr"]: t for t in (path.get("tracks") or [])}
    colors = {v["name"]: f"var(--ds-{i%6})" for i, v in enumerate(lgz["inputs"]["assemblies"])}

    present_ends = sum(1 for r in rows for k in ("5prime", "3prime") if (r["ends"].get(k) or {}).get("state") in ("already_present", "recovered"))
    recovered_ends = sum(1 for r in rows for k in ("5prime", "3prime") if (r["ends"].get(k) or {}).get("state") == "recovered")
    total_ends = len(rows) * 2
    right_txt = bi(f"{present_ends} / {total_ends} 个末端具备 TEL", f"{present_ends} / {total_ends} ends with TEL")
    if recovered_ends:
        right_txt += " · " + bi(f"恢复 {recovered_ends}", f"{recovered_ends} restored")

    has_gaps = any(
        p["kind"] != "source"
        for r in rows
        for t in (tracks.get(r["chr"]),)
        if t and path.get("sha256") == r["sha256"] and t["length_bp"] == r["length_bp"]
        for p in t["parts"]
    )
    legend = [
        '<span class="legend-item"><span class="badge tone-ok" style="padding:.04rem .36rem;border-radius:999px;font:700 .68rem/1.2 var(--font-mono)">TEL</span>' + bi("已检出端粒（点击查看）", "Telomere detected (click)") + '</span>',
        '<span class="legend-item"><span class="badge tone-neutral" style="padding:.04rem .36rem;border-radius:999px;font:700 .7rem/1.1 var(--font-mono)">○</span>' + bi("未检出端粒（点击查看原因）", "Absent (click for reason)") + '</span>',
        *[f'<span class="legend-item"><i class="swatch" style="background:{c}"></i>{esc(ds)}</span>' for ds, c in colors.items()],
    ]
    if has_gaps:
        legend.append('<span class="legend-item"><i class="swatch is-orig-gap"></i>Gap</span>')

    body = [
        TERMINAL_STYLE,
        '<div class="story-toolbar"><div class="legend-row" style="margin:0">' + "".join(legend) + '</div></div>',
        '<div class="tel-frame" data-zoom-frame="1">',
        f'<div class="tel-axis"><span>{bi("染色体", "Chromosome")}</span><div class="tel-axis-pad"><span class="story-ruler">'
        + "".join(f"<span>{esc(fmt_bp_short(round(m * i / 4)))}</span>" for i in range(5)) + "</span></div></div>",
    ]
    templates = []
    for row in rows:
        c = row["chr"]
        n = row["length_bp"]
        marks = []
        buttons = []
        t = tracks.get(c)
        if path.get("sha256") == row["sha256"] and t and t["length_bp"] == n:
            for p in t["parts"]:
                is_src = p["kind"] == "source"
                color = colors.get(p.get("dataset"), "var(--ds-0)") if is_src else "var(--gen-unfilled)"
                cls = "tel-part is-ctg" if is_src else "tel-part is-gap"
                tip = f'{p.get("dataset", "")} / {p.get("name", "")} · q3 {p["start"]+1:,}–{p["end"]:,}' if is_src else f'Gap · q3 {p["start"]+1:,}–{p["end"]:,} · {p["end"]-p["start"]:,} N'
                marks.append(f'<span class="{cls}" title="{esc(tip)}" style="left:{100*p["start"]/n:.8g}%;width:{100*(p["end"]-p["start"])/n:.8g}%;background:{color}"></span>')
        chr_tel = 0
        for k in ("5prime", "3prime"):
            info = row["ends"].get(k)
            has_tel = bool(info and info["state"] in ("already_present", "recovered"))
            if has_tel:
                chr_tel += 1
            text = "TEL" if has_tel else "○"
            end = "5′" if k == "5prime" else "3′"
            side_cls = "is-5p" if k == "5prime" else "is-3p"
            state_cls = "is-present" if has_tel else "is-missing"
            key = f"terminal-{len(templates)}"
            title = esc(c) + " · " + end
            buttons.append(
                f'<button class="tel-end {side_cls} {state_cls}" type="button" data-story-open="{key}" '
                f'title="{title} · {text}" aria-label="{title} · {text}">{text}</button>'
            )
            is_compact = not info or (not info.get("candidates") and not info.get("selected"))
            compact_attr = ' data-compact="1"' if is_compact else ""
            templates.append(f'<template id="{key}" data-title="{title}"{compact_attr}>{_inspection(info, k, n)}</template>')
        pill_cls = "is-full" if chr_tel == 2 else ("is-part" if chr_tel == 1 else "")
        pill_html = f'<span class="tel-pill {pill_cls}">{chr_tel}/2 TEL</span>'
        body.append(
            f'<div class="tel-row">'
            f'<div class="tel-chr-col"><div class="tel-chr-head"><b>{esc(c)}</b>{pill_html}</div><small>{esc(fmt_bp_short(n))}</small></div>'
            f'<div class="tel-gutter"><div class="tel-canvas">'
            f'<div class="tel-bar-wrap" style="width:{100*n/m:.9g}%">'
            f'<div class="tel-bar">{"".join(marks)}</div>{"".join(buttons)}'
            f'</div></div></div></div>'
        )
    body.append(zoom_button("06 端粒处理 · 放大视图", "06 Telomere processing · Enlarged view") + '</div>')
    return section(*head, "".join(body + templates), sub_zh="q2 → q3", sub_en="q2 → q3", right=right_txt)
