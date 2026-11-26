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
.tel-end[data-end-side="5p"]{right:calc(100% + 5px)}
.tel-end[data-end-side="3p"]{left:calc(100% + 5px)}
.tel-end[data-end-state="present"]{color:var(--tone-ok-ink);background:var(--tone-ok-bg);border:1px solid var(--tone-ok-line)}
.tel-end[data-end-state="present"]:hover{background:var(--gen-tel);border-color:var(--gen-tel);color:#fff}
.tel-end[data-end-state="missing"]{color:var(--text-secondary);background:var(--surface-panel);border:1px solid var(--border-strong);padding:.18rem .38rem;font-size:.73rem}
.tel-end[data-end-state="missing"]:hover{border-color:var(--brand);color:var(--brand);background:var(--brand-soft)}
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
.tel-motif-bar{display:flex;flex-wrap:wrap;align-items:center;gap:.38rem .6rem;margin:.5rem 0 0;padding:.45rem .65rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle);font-size:.8rem;color:var(--text-secondary)}
.tel-motif-lbl{font-weight:600;color:var(--text-primary)}
.tel-motif-chip{display:inline-flex;align-items:center;gap:.35rem;flex-wrap:wrap}
.tel-motif-code{display:inline-block;padding:1px 7px;border:1px solid var(--tone-ok-line);border-radius:4px;background:var(--tone-ok-bg);color:var(--tone-ok-ink);font:700 .79rem/1.35 var(--font-mono);letter-spacing:.03em}
.tel-hist-card{margin:.55rem 0 0;padding:.55rem .7rem .5rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
.tel-hist-head{display:flex;align-items:baseline;justify-content:space-between;gap:.4rem .8rem;flex-wrap:wrap;margin-bottom:.25rem;font-size:.78rem;color:var(--text-secondary)}
.tel-hist-head strong{font-size:.8rem;color:var(--text-primary)}
.tel-hist-svg{display:block;width:100%;height:auto}
.tel-hist-foot{display:flex;align-items:center;justify-content:space-between;gap:.4rem .8rem;flex-wrap:wrap;margin-top:.32rem;padding-top:.32rem;border-top:1px solid var(--border-subtle);font-size:.75rem;color:var(--text-muted)}
.tel-hist-keys{display:inline-flex;align-items:center;gap:.35rem .75rem;flex-wrap:wrap}
.tel-dlg-note{margin:.45rem 0 0;font-size:.79rem;color:var(--text-muted);line-height:1.45}
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
    svg_h = 136 if sel else (92 if cand else 54)
    svg = [f'<svg class="repair-zoom" viewBox="0 0 {vb_w} {svg_h}" role="img" aria-label="Terminal evidence / 末端证据">']

    # Track 1: q2 terminal inspection window
    svg.append('<text x="6" y="34" font-size="11.5" font-weight="600" fill="var(--text-primary)">q2</text>')
    svg.append(f'<text x="{pad_l}" y="14" font-size="10" fill="var(--text-muted)">{qlo+1:,}</text>')
    svg.append(f'<text x="{pad_l + plot_w}" y="14" text-anchor="end" font-size="10" fill="var(--text-muted)">{qhi:,}</text>')
    if compact:
        for i in (1, 2, 3):
            tx = pad_l + plot_w * i / 4
            svg.append(f'<line x1="{tx:.1f}" y1="20" x2="{tx:.1f}" y2="41" stroke="var(--border-subtle)" stroke-width="1"/>')
            tpos = round(qlo + (qhi - qlo) * i / 4)
            svg.append(f'<text x="{tx:.1f}" y="51" text-anchor="middle" font-size="9" fill="var(--text-muted)">{tpos:,}</text>')

    if cand:
        extract = cand["source"][1] - cand["source"][0]
        dax = _axis(0, extract, pad_l=pad_l, width=plot_w)
        for h in hits:
            a, b = h["q2"]
            u, v = h["extract"] if h["strand"] == "+" else reversed(h["extract"])
            tone = "tone-warn-ink" if h["failed"] else ("ds-0" if h.get("selected") and cand["status"] == "accepted" else "text-muted")
            svg.append(f'<polygon points="{qax(a):.4f},35 {qax(b):.4f},35 {dax(v):.4f},68 {dax(u):.4f},68" opacity=".26" fill="var(--{tone})"/>')
        cname = cand["name"] if len(cand["name"]) <= 12 else cand["name"][:11] + "…"
        svg.append(f'<text x="6" y="76" font-size="11" font-weight="600" fill="var(--text-secondary)"><title>{esc(cand["name"])}</title>{esc(cname)}</text>')
        svg.append(_rect([0, extract], dax, 68, "var(--border-strong)"))
        if sel and cand["event"] == sel["event"] and cand["status"] == "accepted" and cand["used"]:
            svg.append(_rect(cand["used"], dax, 67, "var(--ds-0)", h=11))
        for interval in cand["signals"] or []:
            s_a, s_b = interval
            svg.append(
                f'<rect x="{min(dax(s_a), dax(s_b)):.5f}" y="63" width="{max(2.5, abs(dax(s_b)-dax(s_a))):.5f}" height="6" rx="1" fill="var(--gen-tel)">'
                f'<title>Motif · {s_a+1:,}–{s_b:,} ({s_b-s_a:,} bp)</title></rect>'
            )

    if compact:
        svg.append(f'<rect x="{pad_l}" y="24" width="{plot_w}" height="12" rx="3" fill="var(--surface-panel)" stroke="var(--border-default)"/>')
    else:
        svg.append(_rect([qlo, qhi], qax, 25, "var(--border-default)", h=10))
        svg.append(_rect(w, qax, 25, "var(--tone-info-line)", h=10))
    motifs = t.get("matched_motifs") or []
    motif_lbl = "/".join(m["motif"] for m in motifs) if motifs else "Telomere motif"
    motif_len = len(motifs[0]["motif"]) if len(motifs) == 1 and motifs[0].get("motif") else 0
    for interval in t["q2_signals"] or []:
        s_a, s_b = interval
        bp = s_b - s_a
        rep_note = f" · ~{bp // motif_len}×" if motif_len else ""
        sx0, sx1 = sorted((qax(s_a), qax(s_b)))
        svg.append(
            f'<rect x="{sx0:.5f}" y="22" width="{max(3.0, sx1 - sx0):.5f}" height="16" rx="2" fill="var(--gen-tel)">'
            f'<title>{esc(motif_lbl)} · {s_a+1:,}–{s_b:,} ({bp:,} bp{rep_note})</title></rect>'
        )

    if sel:
        cut = qax(sel["cut"])
        svg.append(f'<path d="M{cut:.4f} 18v23" stroke="var(--gen-patch)" stroke-width="2.2"/>')
        span = sel["span"]
        lo = max(0, span[0] - (2000 if side == "3prime" else 0))
        hi = min(outsize, span[1] + (2000 if side == "5prime" else 0))
        ax = _axis(lo, hi, pad_l=pad_l, width=plot_w)
        svg.append('<text x="6" y="118" font-size="11.5" font-weight="600" fill="var(--text-primary)">q3</text>')
        svg.append(f'<text x="{pad_l}" y="134" font-size="10" fill="var(--text-muted)">{lo+1:,}</text>')
        svg.append(f'<text x="{pad_l + plot_w}" y="134" text-anchor="end" font-size="10" fill="var(--text-muted)">{hi:,}</text>')
        svg.append(_rect([lo, hi], ax, 110, "var(--border-strong)"))
        svg.append(_rect(span, ax, 109, "var(--ds-0)", h=11))
        for u, v in t["q3_signals"] or []:
            if min(hi, v) > max(lo, u):
                sx0, sx1 = sorted((ax(max(lo, u)), ax(min(hi, v))))
                svg.append(
                    f'<rect x="{sx0:.5f}" y="104" width="{max(2.5, sx1 - sx0):.5f}" height="6" rx="1" fill="var(--gen-tel)">'
                    f'<title>{esc(motif_lbl)} · q3 {u+1:,}–{v:,} ({v-u:,} bp)</title></rect>'
                )

    svg.append("</svg>")
    return f'<div class="tel-dlg-plot">{"".join(svg)}</div>'


def _motif_histogram(t, side):
    prof = t.get("motif_profile")
    if not isinstance(prof, dict):
        return ""
    fwd = prof.get("forward") or []
    rev = prof.get("reverse") or []
    if not fwd or len(fwd) != len(rev):
        return ""
    win_a, win_b = prof["window"]
    bin_bp = prof["bin_bp"]
    n_bins = len(fwd)
    span = max(1, win_b - win_a)
    totals = [f + r for f, r in zip(fwd, rev)]
    max_val = max(totals) if totals else 0
    # Clean integer Y ceiling (minimum 10 so empty ends show a clear flat 0 baseline).
    if max_val <= 10:
        y_top = 10
    elif max_val <= 20:
        y_top = 20
    elif max_val <= 30:
        y_top = 30
    else:
        y_top = ((max_val + 9) // 10) * 10
    y_mid = y_top // 2

    vb_w, vb_h = 560, 148
    pad_l, pad_r, pad_t, pad_b = 44, 16, 16, 30
    plot_w = vb_w - pad_l - pad_r
    plot_h = vb_h - pad_t - pad_b
    base_y = pad_t + plot_h

    def x_of(bp_pos):
        return pad_l + plot_w * (bp_pos - win_a) / span

    def y_of(val):
        return base_y - plot_h * val / y_top

    svg = [f'<svg class="tel-hist-svg" viewBox="0 0 {vb_w} {vb_h}" role="img" aria-label="Terminal motif distribution / 末端 Motif 分布">']

    # Shade the 2,000 bp detection window inside the 5,000 bp terminal profile.
    det_w = t.get("window")
    if det_w and len(det_w) == 2:
        da, db = max(win_a, det_w[0]), min(win_b, det_w[1])
        if da < db:
            dx0, dx1 = x_of(da), x_of(db)
            svg.append(f'<rect x="{dx0:.2f}" y="{pad_t}" width="{dx1-dx0:.2f}" height="{plot_h}" fill="var(--brand)" opacity=".06"/>')
            bound_x = dx1 if side == "5prime" else dx0
            if pad_l + 4 < bound_x < pad_l + plot_w - 4:
                svg.append(f'<line x1="{bound_x:.2f}" y1="{pad_t}" x2="{bound_x:.2f}" y2="{base_y}" stroke="var(--brand)" stroke-width="1" stroke-dasharray="3 3" opacity=".55"/>')

    # Horizontal gridlines & Y ticks
    for tick in (0, y_mid, y_top):
        ty = y_of(tick)
        stroke = "var(--border-default)" if tick == 0 else "var(--border-subtle)"
        dash = '' if tick == 0 else ' stroke-dasharray="2 3"'
        svg.append(f'<line x1="{pad_l}" y1="{ty:.2f}" x2="{pad_l + plot_w}" y2="{ty:.2f}" stroke="{stroke}" stroke-width="1"{dash}/>')
        svg.append(f'<text x="{pad_l - 6}" y="{ty + 3.5:.2f}" text-anchor="end" font-size="9.5" fill="var(--text-muted)">{tick}</text>')
    svg.append(f'<text x="{pad_l - 6}" y="10" text-anchor="end" font-size="9" fill="var(--text-muted)">cnt</text>')

    # Bars (stacked forward + reverse per fixed bin)
    fwd_lbl = prof.get("forward_label") or "+"
    rev_lbl = prof.get("reverse_label") or "-"
    slot_w = plot_w / n_bins
    gap = min(2.0, slot_w * 0.18)
    bar_w = max(2.0, slot_w - gap)
    for i, (fc, rc) in enumerate(zip(fwd, rev)):
        bx = pad_l + i * slot_w + gap / 2
        b_start = win_a + i * bin_bp
        b_end = min(win_b, b_start + bin_bp)
        tip = f'{b_start+1:,}–{b_end:,} bp · {fwd_lbl}(+): {fc} · {rev_lbl}(-): {rc}'
        if fc > 0:
            fh = plot_h * fc / y_top
            fy = base_y - fh
            svg.append(f'<rect x="{bx:.2f}" y="{fy:.2f}" width="{bar_w:.2f}" height="{max(1.5, fh):.2f}" rx="1.5" fill="var(--gen-tel)"><title>{esc(tip)}</title></rect>')
        if rc > 0:
            rh = plot_h * rc / y_top
            ry = base_y - (plot_h * (fc + rc) / y_top)
            svg.append(f'<rect x="{bx:.2f}" y="{ry:.2f}" width="{bar_w:.2f}" height="{max(1.5, rh):.2f}" rx="1.5" fill="var(--ds-1)"><title>{esc(tip)}</title></rect>')
        if fc == 0 and rc == 0:
            svg.append(f'<rect x="{bx:.2f}" y="{pad_t}" width="{bar_w:.2f}" height="{plot_h}" fill="transparent"><title>{esc(tip)}</title></rect>')

    # X axis ticks (5 evenly spaced coordinates across the profile window)
    for i in range(5):
        pos_bp = round(win_a + span * i / 4)
        tx = x_of(pos_bp)
        anchor = "start" if i == 0 else ("end" if i == 4 else "middle")
        svg.append(f'<line x1="{tx:.2f}" y1="{base_y}" x2="{tx:.2f}" y2="{base_y + 4}" stroke="var(--border-strong)" stroke-width="1"/>')
        lbl = f"{pos_bp+1:,}" if i == 0 else f"{pos_bp:,}"
        svg.append(f'<text x="{tx:.2f}" y="{base_y + 15}" text-anchor="{anchor}" font-size="9.5" fill="var(--text-muted)">{lbl}</text>')
    svg.append(f'<text x="{pad_l + plot_w / 2:.1f}" y="{vb_h - 3}" text-anchor="middle" font-size="9.5" fill="var(--text-muted)">bp</text>')
    svg.append("</svg>")

    total_f, total_r = sum(fwd), sum(rev)
    total_all = total_f + total_r
    head_left = bi("末端 Motif 分布", "Terminal motif distribution")
    head_right = bi(f"末端 {span:,} bp · 每 {bin_bp} bp 统计 · 合计 {total_all:,} 次", f"{span:,} bp end · {bin_bp} bp bins · {total_all:,} hits")
    keys = []
    if total_f > 0 or total_all == 0:
        keys.append(f'<span class="legend-item"><i class="swatch" style="background:var(--gen-tel)"></i>{esc(fwd_lbl)} (+) · {total_f:,}</span>')
    if total_r > 0 or total_all == 0:
        keys.append(f'<span class="legend-item"><i class="swatch" style="background:var(--ds-1)"></i>{esc(rev_lbl)} (−) · {total_r:,}</span>')
    keys.append('<span class="legend-item"><i class="swatch" style="background:var(--brand);opacity:.2;border:1px dashed var(--brand)"></i>' + bi("2 kb 检测区", "2 kb scan zone") + '</span>')
    return (
        '<div class="tel-hist-card">'
        f'<div class="tel-hist-head"><strong>{head_left}</strong><span>{head_right}</span></div>'
        + "".join(svg)
        + f'<div class="tel-hist-foot"><div class="tel-hist-keys">{"".join(keys)}</div></div>'
        '</div>'
    )


def _motif_summary_bar(t):
    motifs = t.get("matched_motifs") or []
    sigs = t.get("q3_signals") if t.get("selected") and t.get("q3_signals") else t.get("q2_signals")
    chips = []
    for m in motifs:
        strand_txt = bi(f"反向互补（来自 {m['base_motif']}）", f"RC of {m['base_motif']}") if m.get("strand") == "-" else bi("正链", "Forward")
        rule_txt = f' · <span>{esc(m["rule_name"])}</span>' if m.get("rule_name") else ""
        chips.append(f'<span class="tel-motif-chip"><span class="tel-motif-code">{esc(m["motif"])}</span><span>{strand_txt}</span>{rule_txt}</span>')
    if sigs:
        total_bp = sum(b - a for a, b in sigs)
        span_preview = ", ".join(f"{a+1:,}–{b:,}" for a, b in sigs[:4]) + (" …" if len(sigs) > 4 else "")
        dist_txt = bi(f"{len(sigs)} 处重复区 · 共 {total_bp:,} bp（{span_preview}）", f"{len(sigs)} hit span(s) · {total_bp:,} bp ({span_preview})")
        chips.append(f'<span>{dist_txt}</span>')
    if not chips:
        return ""
    return f'<div class="tel-motif-bar"><span class="tel-motif-lbl">{bi("命中基序", "Matched motif")}</span>{"".join(chips)}</div>'


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
    hist_html = _motif_histogram(t, side)

    def one(c):
        has_plot_data = bool(c or sel or (not hist_html and (t["q2_signals"] or t["q3_signals"])))
        rows = [_zoom(t, c, side, size)] if has_plot_data else []
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
    if hist_html:
        msg.append(hist_html)
    motif_bar = _motif_summary_bar(t)
    if motif_bar:
        msg.append(motif_bar)
    if t["q2_signals"] or t["q3_signals"] or (primary and primary["signals"]):
        msg.append('<p class="tel-dlg-note"><i class="swatch" style="background:var(--gen-tel);margin-right:.35rem"></i>' + bi("绿色区间：窗口内检出的端粒串联重复分布（悬停查看坐标与重复数）", "Green: detected tandem telomere repeat distribution (hover for coordinates)") + "</p>")
    elif state != "unresolved" and not hist_html:
        msg.append('<p class="tel-dlg-note">' + bi("本历史快照仅保存了规则命中结果，未记录逐段基序坐标；新版本运行将直接绘制末端基序分布图。", "This earlier snapshot recorded rule hits only; new runs plot per-hit motif positions here.") + '</p>')
    if state == "unresolved" and not cs:
        msg.append('<p class="tel-dlg-note">' + (
            bi("末端检测窗口内未检出端粒基序，且无可用候选供体，保留 q2 原末端。", "No telomere motif detected in the terminal window and no candidate donor found; original q2 end retained.")
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
            side_val = "5p" if k == "5prime" else "3p"
            state_val = "present" if has_tel else "missing"
            key = f"terminal-{len(templates)}"
            title = esc(c) + " · " + end
            buttons.append(
                f'<button class="tel-end" data-end-side="{side_val}" data-end-state="{state_val}" type="button" data-story-open="{key}" '
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
