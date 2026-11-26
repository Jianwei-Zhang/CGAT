"""Opening overview card: single-rail q0->Final stage switcher (P1), 4 genome quality charts (P2), and runtime bar."""
from __future__ import annotations

from datetime import datetime
import json
import math

try:
    from render_final_story import _select_version
    from render_path_story import zoom_button
    from render_refinement_report import bi, esc, fmt_bp_short
    from report_gap_story import NAMES, tool_order
except ModuleNotFoundError:
    from .render_final_story import _select_version
    from .render_path_story import zoom_button
    from .render_refinement_report import bi, esc, fmt_bp_short
    from .report_gap_story import NAMES, tool_order

_SHORT_TOOL = {
    "degap": "DEGAP",
    "lrgapcloser": "LR",
    "tgsgapcloser": "TGS",
    "quartet": "quarTeT",
}

_GAP_KINDS = frozenset({"gap", "unspecified_gap", "reference_gap", "reference_unknown", "unknown"})


def _calc_n50(lengths):
    vals = sorted((int(x) for x in lengths if x and x > 0), reverse=True)
    if not vals:
        return 0
    half = sum(vals) / 2.0
    acc = 0
    for v in vals:
        acc += v
        if acc >= half:
            return v
    return vals[-1]


def _contig_continuity(stage_rows):
    """Compute gap-split Contig N50 and contiguous block count from stage_rows."""
    if not stage_rows:
        return None
    blocks = []
    for r in stage_rows.values():
        segs = r.get("segs") or []
        if not segs:
            continue
        cur = 0
        for a, b, code in segs:
            if code == 9:
                if cur > 0:
                    blocks.append(cur)
                    cur = 0
            else:
                cur += max(0, int(b) - int(a))
        if cur > 0:
            blocks.append(cur)
    if not blocks:
        return None
    return _calc_n50(blocks), len(blocks)


def _fmt_compact_bp(bp):
    if bp is None:
        return "—"
    v = abs(int(bp))
    sign = "-" if bp < 0 else ""
    if v >= 1_000_000_000:
        return f"{sign}{v / 1_000_000_000:.2f}G"
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.0f}k" if v >= 100_000 else f"{sign}{v / 1_000:.1f}k"
    return f"{sign}{v}bp"


def _fmt_dur(seconds):
    s = max(0.0, float(seconds or 0.0))
    if s >= 3600:
        h = int(s // 3600)
        m = int(round((s - h * 3600) / 60.0))
        if m == 60:
            h += 1
            m = 0
        return f"{h}h {m}m" if m else f"{h}h"
    if s >= 60:
        m = s / 60.0
        return f"{m:.0f}m" if m >= 100 else f"{m:.1f}m"
    return f"{s:.0f}s" if s >= 10 else f"{s:.1f}s"


def _suppressed_partials(tool_rec):
    if not tool_rec:
        return set()
    return {
        gid for gid, dec in (tool_rec.get("gap_decisions") or {}).items()
        if dec.get("state") == "partial"
    }


def _final_track_stats(v, tool_rec):
    """Return verified Final Path track metrics, merging legacy adjacent partial+gap spans."""
    tracks = (v or {}).get("tracks") or []
    suppressed = _suppressed_partials(tool_rec)
    total_gaps = 0
    total_gap_bp = 0
    total_bp = 0
    gap_free = 0
    lens = []
    source_bp = {}
    patch_bp = 0
    per_chr = {}
    for c in tracks:
        cname = c.get("chr")
        clen = int(c.get("length") or 0)
        lens.append(clen)
        total_bp += clen
        cgaps = 0
        prev_gap = False
        for p in c.get("parts") or []:
            a, b = int(p.get("start") or 0), int(p.get("end") or 0)
            span = max(0, b - a)
            edit = p.get("edit")
            is_partial = bool(edit and p.get("gaps") and any(g in suppressed for g in p["gaps"]))
            if p.get("kind") == "gap" or is_partial:
                if not prev_gap:
                    cgaps += 1
                prev_gap = True
                total_gap_bp += span
            elif edit:
                prev_gap = False
                patch_bp += span
            else:
                prev_gap = False
                src = p.get("source") or {}
                ds = src.get("dataset") or "assembly"
                source_bp[ds] = source_bp.get(ds, 0) + span
        total_gaps += cgaps
        if cgaps == 0:
            gap_free += 1
        if cname:
            per_chr[cname] = {"len": clen, "gaps": cgaps}
    return {
        "gaps": total_gaps,
        "gap_bp": total_gap_bp,
        "total_bp": total_bp,
        "n50_bp": _calc_n50(lens),
        "gap_free_chrs": gap_free,
        "chr_count": len(tracks),
        "source_bp": source_bp,
        "patch_bp": patch_bp,
        "per_chr": per_chr,
    }


def _telomere_summary(lgz, chr_order):
    tscene = lgz.get("terminal_scene")
    chrs = lgz.get("chromosomes") or []
    per_chr = {}
    if isinstance(tscene, list) and tscene:
        for row in tscene:
            cname = row.get("chr")
            ends = row.get("ends") or {}
            s5 = (ends.get("5prime") or {}).get("state")
            s3 = (ends.get("3prime") or {}).get("state")
            if cname:
                per_chr[cname] = (s5, s3)
    elif chrs:
        for row in chrs:
            cname = row.get("chromosome")
            tels = row.get("telomeres") or {}
            if cname and tels:
                per_chr[cname] = (tels.get("5prime"), tels.get("3prime"))
    if not per_chr:
        return {"available": False, "present": 0, "extended": 0, "missing": 0, "total": 0, "both": 0, "chr_total": 0, "per_chr": {}}
    names = [c for c in chr_order if c in per_chr] or list(per_chr.keys())
    present = extended = missing = both = 0
    for cname in names:
        s5, s3 = per_chr.get(cname, (None, None))
        ok = 0
        for st in (s5, s3):
            if st == "already_present":
                present += 1
                ok += 1
            elif st in ("extended", "accepted", "added"):
                extended += 1
                ok += 1
            else:
                missing += 1
        if ok == 2:
            both += 1
    total = present + extended + missing
    return {
        "available": total > 0,
        "present": present,
        "extended": extended,
        "missing": missing,
        "total": total,
        "both": both,
        "chr_total": len(names),
        "per_chr": per_chr,
    }


def _centromere_map(lgz):
    out = {}
    for row in lgz.get("chromosomes") or []:
        cname = row.get("chromosome")
        marks = row.get("centromere_markers") or []
        if cname and marks:
            out[cname] = [
                (int(m.get("q4_start") or 0), int(m.get("q4_end") or 0))
                for m in marks
                if isinstance(m, dict) and (m.get("q4_end") or 0) > (m.get("q4_start") or 0)
            ]
    return out


def _build_stage_tracks(vm, chr_order, colors, winning_v, winning_tool_rec, tel_info, auto):
    lgz = vm["lgz_summary"]
    sv = lgz.get("sequence_versions") or {}
    vt = lgz.get("version_tracks") or {}
    sp = lgz.get("stage_paths") or {}
    q0_scene = lgz.get("q0_scene") if isinstance(lgz.get("q0_scene"), list) else []
    q0_map = {r.get("chr"): r for r in q0_scene if isinstance(r, dict) and r.get("chr")}
    chr_map = {r.get("chromosome"): r for r in (lgz.get("chromosomes") or []) if isinstance(r, dict) and r.get("chromosome")}
    suppressed = _suppressed_partials(winning_tool_rec)
    final_map = {c["chr"]: c for c in ((winning_v or {}).get("tracks") or [])}

    def _from_vt(stage_key):
        block = vt.get(stage_key) if isinstance(vt, dict) else None
        cmap = (block or {}).get("chromosomes") if isinstance(block, dict) else None
        if not cmap:
            return None
        rows = {}
        for cname in chr_order:
            c = cmap.get(cname)
            if not c:
                continue
            segs = []
            gaps = 0
            for s in c.get("segments") or []:
                a, b = int(s.get("start") or 0), int(s.get("end") or 0)
                if b <= a:
                    continue
                k = s.get("kind") or ""
                if k in _GAP_KINDS:
                    code = 9
                    gaps += 1
                elif s.get("patch"):
                    code = 8
                else:
                    code = colors.get(s.get("source"), 0)
                segs.append([a, b, code])
            rows[cname] = {
                "len": int(c.get("length_bp") or 0),
                "gaps": int(c.get("gap_count") if c.get("gap_count") is not None else gaps),
                "segs": segs,
            }
        return rows if rows else None

    def _from_stage_paths(stage_key):
        block = sp.get(stage_key) if isinstance(sp, dict) else None
        tracks = (block or {}).get("tracks") if isinstance(block, dict) else None
        if not tracks:
            return None
        tmap = {t.get("chr"): t for t in tracks if isinstance(t, dict) and t.get("chr")}
        rows = {}
        for cname in chr_order:
            c = tmap.get(cname)
            if not c:
                continue
            segs = []
            gaps = 0
            for p in c.get("parts") or []:
                a, b = int(p.get("start") or 0), int(p.get("end") or 0)
                if b <= a:
                    continue
                k = p.get("kind") or ""
                if k in _GAP_KINDS:
                    code = 9
                    gaps += 1
                elif k in ("patch", "refined", "repair"):
                    code = 8
                else:
                    code = colors.get(p.get("dataset"), 0)
                segs.append([a, b, code])
            rows[cname] = {"len": int(c.get("length_bp") or 0), "gaps": gaps, "segs": segs}
        return rows if rows else None

    def _from_q0_scene():
        if not q0_map:
            return None
        rows = {}
        for cname in chr_order:
            c = q0_map.get(cname)
            if not c:
                continue
            segs = []
            gaps = 0
            for s in c.get("q0_segments") or c.get("segments") or []:
                a = int(s.get("start") if s.get("start") is not None else (s.get("q0_start") or 0))
                b = int(s.get("end") if s.get("end") is not None else (s.get("q0_end") or 0))
                if b <= a:
                    continue
                k = s.get("kind") or ""
                if k in _GAP_KINDS:
                    code = 9
                    gaps += 1
                else:
                    code = colors.get(s.get("dataset") or s.get("source"), 0)
                segs.append([a, b, code])
            rows[cname] = {"len": int(c.get("q0_length_bp") or c.get("length_bp") or 0), "gaps": gaps, "segs": segs}
        return rows if rows else None

    def _from_chromosomes():
        if not chr_map:
            return None
        rows = {}
        for cname in chr_order:
            c = chr_map.get(cname)
            if not c:
                continue
            segs = []
            gaps = 0
            for s in c.get("segments") or []:
                a, b = int(s.get("start") or 0), int(s.get("end") or 0)
                if b <= a:
                    continue
                k = s.get("kind") or ""
                if k in _GAP_KINDS:
                    code = 9
                    gaps += 1
                elif s.get("patch"):
                    code = 8
                else:
                    code = colors.get(s.get("source"), 0)
                segs.append([a, b, code])
            rows[cname] = {
                "len": int(c.get("length_bp") or 0),
                "gaps": int(c.get("remaining_gap_count") if c.get("remaining_gap_count") is not None else gaps),
                "segs": segs,
            }
        return rows if rows else None

    def _from_final():
        if not final_map:
            return None
        rows = {}
        for cname in chr_order:
            c = final_map.get(cname)
            if not c:
                continue
            segs = []
            gaps = 0
            for p in c.get("parts") or []:
                a, b = int(p.get("start") or 0), int(p.get("end") or 0)
                if b <= a:
                    continue
                edit = p.get("edit")
                is_partial = bool(edit and p.get("gaps") and any(g in suppressed for g in p["gaps"]))
                if p.get("kind") == "gap" or is_partial:
                    if segs and segs[-1][2] == 9 and segs[-1][1] == a:
                        segs[-1][1] = b
                        continue
                    code = 9
                    gaps += 1
                elif edit:
                    code = 8
                else:
                    src = p.get("source") or {}
                    code = colors.get(src.get("dataset"), 0)
                segs.append([a, b, code])
            rows[cname] = {"len": int(c.get("length") or 0), "gaps": gaps, "segs": segs}
        return rows if rows else None

    q0_rows = _from_vt("q0") or _from_q0_scene()
    q1_rows = _from_vt("q1") or _from_stage_paths("q1")
    q2_rows = _from_vt("q2") or _from_stage_paths("q2")
    q3_rows = _from_vt("q3") or _from_stage_paths("q3") or _from_chromosomes()
    final_rows = _from_final()
    if not auto and not q3_rows and final_rows:
        q3_rows = final_rows

    def _delta_pill(cur_g, prev_g):
        if cur_g is None:
            return ("—", "—")
        if prev_g is None:
            return (f"{cur_g} Gap", f"{cur_g} gaps")
        diff = cur_g - prev_g
        if diff < 0:
            return (f"{diff} Gap · 剩 {cur_g}", f"{diff} · {cur_g} left")
        if diff == 0:
            return (f"未变 · {cur_g} Gap", f"same · {cur_g}")
        return (f"+{diff} Gap · 剩 {cur_g}", f"+{diff} · {cur_g} left")

    q0_g = (sv.get("q0") or {}).get("gap_count")
    q1_g = (sv.get("q1") or {}).get("gap_count")
    q2_g = (sv.get("q2") or {}).get("gap_count")
    q3_g = (sv.get("q3") or {}).get("gap_count")

    q0_sub_zh, q0_sub_en = _delta_pill(q0_g, None)
    q1_sub_zh, q1_sub_en = _delta_pill(q1_g, q0_g)
    q2_sub_zh, q2_sub_en = _delta_pill(q2_g, q1_g)
    if tel_info["available"]:
        ok_t = tel_info["present"] + tel_info["extended"]
        tot_t = tel_info["total"]
        ext_t = tel_info["extended"]
        if ext_t > 0:
            q3_sub_zh = f"+{ext_t} 端粒 · {ok_t}/{tot_t}"
            q3_sub_en = f"+{ext_t} tel · {ok_t}/{tot_t}"
        else:
            q3_sub_zh = f"{ok_t}/{tot_t} 端粒"
            q3_sub_en = f"{ok_t}/{tot_t} tel"
    else:
        q3_sub_zh, q3_sub_en = _delta_pill(q3_g, q2_g)

    stages = [
        {
            "key": "q0", "tag": "q0", "zh": "初始路径", "en": "Initial Path",
            "sub_zh": q0_sub_zh, "sub_en": q0_sub_en,
            "href": "#alignment-q0", "jump_zh": "03 初始路径", "jump_en": "03 Initial Path",
            "show_tel": False, "is_final": False, "rows": q0_rows,
        },
        {
            "key": "q1", "tag": "q1", "zh": "局部修补", "en": "Local Repair",
            "sub_zh": q1_sub_zh, "sub_en": q1_sub_en,
            "href": "#first-repair", "jump_zh": "04 局部修补", "jump_en": "04 Local Repair",
            "show_tel": False, "is_final": False, "rows": q1_rows,
        },
        {
            "key": "q2", "tag": "q2", "zh": "结构修复", "en": "Structural Repair",
            "sub_zh": q2_sub_zh, "sub_en": q2_sub_en,
            "href": "#structural-repair", "jump_zh": "05 结构修复", "jump_en": "05 Structural Repair",
            "show_tel": False, "is_final": False, "rows": q2_rows,
        },
        {
            "key": "q3",
            "tag": "q3" if auto else "Final",
            "zh": "端粒处理" if auto else "最终路径",
            "en": "Telomere Processing" if auto else "Final Path",
            "sub_zh": q3_sub_zh, "sub_en": q3_sub_en,
            "href": "#terminal-process" if auto else "#final-path",
            "jump_zh": "06 端粒处理" if auto else "07 最终路径",
            "jump_en": "06 Telomere Processing" if auto else "07 Final Path",
            "show_tel": True, "is_final": not auto, "rows": q3_rows,
        },
    ]

    if auto and winning_v:
        fstats = _final_track_stats(winning_v, winning_tool_rec)
        fg = fstats["gaps"]
        tname = NAMES.get(winning_v["tool"], winning_v["tool"])
        if q3_g is not None:
            diff = fg - q3_g
            fsub_zh = f"{diff} Gap · 剩 {fg}" if diff < 0 else f"剩 {fg} Gap"
            fsub_en = f"{diff} · {fg} left" if diff < 0 else f"{fg} left"
        else:
            fsub_zh = f"剩 {fg} Gap"
            fsub_en = f"{fg} gaps"
        stages.append({
            "key": "final", "tag": "Final", "zh": f"最终路径 · {tname}", "en": f"Final · {tname}",
            "sub_zh": fsub_zh, "sub_en": fsub_en,
            "href": "#final-path", "jump_zh": "08 最终路径", "jump_en": "08 Final Path",
            "show_tel": True, "is_final": True, "rows": final_rows or q3_rows,
        })

    default_key = stages[-1]["key"]
    for st in reversed(stages):
        if st["rows"]:
            default_key = st["key"]
            break
    return stages, default_key


def _render_rail_html(segs, domain, tel_pair=None, show_tel=False, cen_marks=None):
    parts = []
    for a, b, code in segs:
        left = 100.0 * a / domain
        width = 100.0 * (b - a) / domain
        if code == 9:
            parts.append(f'<span class="ov-seg is-gap" style="left:{left:.6g}%;width:{width:.6g}%"></span>')
        elif code == 8:
            parts.append(f'<span class="ov-seg is-patch" style="left:{left:.6g}%;width:{width:.6g}%"></span>')
        else:
            parts.append(f'<span class="ov-seg is-src" style="left:{left:.6g}%;width:{width:.6g}%;background:var(--ds-{code})"></span>')
    if show_tel and cen_marks:
        for a, b in cen_marks:
            left = 100.0 * a / domain
            width = max(0.35, 100.0 * (b - a) / domain)
            parts.append(f'<span class="ov-cen" style="left:{left:.6g}%;width:{width:.6g}%" title="Candidate centromere"></span>')
    if show_tel and tel_pair:
        s5, s3 = tel_pair
        end_pct = 100.0 * (segs[-1][1] if segs else 0) / domain
        for side, st, pos in (("5′", s5, 0.0), ("3′", s3, end_pct)):
            ok = st in ("already_present", "extended", "accepted", "added")
            cls = "ov-tel is-ext" if st in ("extended", "accepted", "added") else ("ov-tel is-ok" if ok else "ov-tel is-miss")
            tip = f"{side} telomere: {st or 'missing'}"
            parts.append(f'<span class="{cls}" style="left:{pos:.6g}%" title="{esc(tip)}"></span>')
    return "".join(parts)


def _svg_gap_combo(vm, sv, versions, tools, winning_v, fstats, auto):
    """Chart 1: Combined Gap count trajectory (line + tool branches) & Gap total bp (background bars)."""
    W, H = 460, 176
    has_branches = bool(auto and versions)
    pad_l, pad_r, pad_t, pad_b = 34, 118 if has_branches else 34, 24, 26
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b

    base_stages = []
    for k in ("q0", "q1", "q2", "q3"):
        rec = sv.get(k) or {}
        g = rec.get("gap_count")
        gbp = rec.get("gap_bp") if rec.get("gap_bp") is not None else rec.get("n_bp")
        if g is not None:
            base_stages.append((k, int(g), int(gbp or 0)))

    by_tool = {t["tool"]: t for t in tools}
    loci_total = len((vm.get("refinement_summary") or {}).get("original_loci") or [])
    tool_branches = []
    if has_branches:
        win_tool = winning_v["tool"] if winning_v else None
        for v in versions:
            t = v["tool"]
            trec = by_tool.get(t)
            st = _final_track_stats(v, trec) if v.get("tracks") else None
            if st is None:
                continue
            decs = (trec or {}).get("gap_decisions") or {}
            cnts = (trec or {}).get("counts") or {}
            if decs:
                closed = sum(1 for d in decs.values() if d.get("state") == "closed")
                denom = loci_total or len(decs)
            elif cnts:
                closed = int(cnts.get("closed") or 0)
                denom = loci_total or sum(int(cnts.get(x) or 0) for x in ("closed", "partial", "rejected", "unfilled"))
            else:
                closed = v.get("edits") or 0
                denom = loci_total
            tool_branches.append({
                "tool": t,
                "name": _SHORT_TOOL.get(t, NAMES.get(t, t)),
                "full_name": NAMES.get(t, t),
                "gaps": st["gaps"],
                "gap_bp": st["gap_bp"],
                "closed": closed,
                "denom": denom,
                "winner": t == win_tool,
                "order": tool_order(t),
            })
        tool_branches.sort(key=lambda r: (0 if r["winner"] else 1, r["gaps"], r["order"]))

    if not base_stages and not tool_branches:
        return '<p class="muted" style="margin:.5rem 0">' + bi("暂无阶段 Gap 数据。", "No stage gap data.") + "</p>", ""

    all_cnt = [g for _, g, _ in base_stages] + [b["gaps"] for b in tool_branches]
    max_cnt = max(all_cnt) if all_cnt else 1
    if max_cnt <= 0:
        max_cnt = 4
    step = max(1, int(math.ceil(max_cnt / 4.0)))
    if step > 2 and step % 2 == 1 and max_cnt > 10:
        step += 1
    y_top = step * 4

    bar_bps = [bp for _, _, bp in base_stages]
    if tool_branches:
        bar_bps.append(tool_branches[0]["gap_bp"])
    max_bp = max([1, *bar_bps])

    cols = len(base_stages) + (1 if tool_branches else 0)
    xs = [pad_l + (plot_w * i / max(1, cols - 1)) for i in range(cols)]
    base_y = pad_t + plot_h

    def y_cnt(val):
        return pad_t + plot_h * (1.0 - max(0, val) / max(1, y_top))

    svg = [f'<svg class="ov-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Gap trajectory">']
    # Micro legend top-left
    svg.append(
        f'<g transform="translate({pad_l},11)">'
        '<rect x="0" y="-6.5" width="7" height="7" rx="1.5" fill="var(--surface-muted)" stroke="var(--border-default)"/>'
        '<text x="10" y="0" class="ov-leg-txt t-zh">Gap 长度</text><text x="10" y="0" class="ov-leg-txt t-en">Gap bp</text>'
        '<line x1="60" y1="-3" x2="72" y2="-3" stroke="var(--brand)" stroke-width="2"/>'
        '<circle cx="66" cy="-3" r="2.2" fill="var(--brand)"/>'
        '<text x="76" y="0" class="ov-leg-txt t-zh">剩余 Gap 数</text><text x="76" y="0" class="ov-leg-txt t-en">Gap count</text>'
        "</g>"
    )

    # Horizontal gridlines & left Y ticks (Gap count)
    for i in range(5):
        val = step * i
        y = y_cnt(val)
        dash = "" if i == 0 else ' stroke-dasharray="2.5 3"'
        svg.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r + 4}" y2="{y:.1f}" stroke="var(--border-subtle)"{dash}/>')
        svg.append(f'<text x="{pad_l - 7}" y="{y + 3:.1f}" text-anchor="end" class="ov-ax-txt">{val}</text>')

    # Background bars: Gap total bp per stage
    bw = min(26.0, (plot_w / max(1, cols)) * 0.42)
    for i, bp in enumerate(bar_bps):
        if bp <= 0:
            continue
        bh = max(3.0, (plot_h * 0.72) * (bp / max_bp))
        y = base_y - bh
        is_win_bar = bool(tool_branches and i == len(bar_bps) - 1)
        fill = "var(--tone-ok-bg)" if is_win_bar else "var(--surface-muted)"
        stroke = "var(--tone-ok-line)" if is_win_bar else "var(--border-subtle)"
        svg.append(f'<rect x="{xs[i] - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2" fill="{fill}" stroke="{stroke}"><title>Gap length: {bp:,} bp</title></rect>')
        # Label Gap bp subtly inside bar bottom for clean reading without clashing with line above
        if bh >= 14:
            svg.append(f'<text x="{xs[i]:.1f}" y="{base_y - 4:.1f}" text-anchor="middle" class="ov-bar-bp">{esc(_fmt_compact_bp(bp))}</text>')

    # Foreground LGZ polyline (q0..q3)
    if base_stages:
        poly_coords = [(xs[i], y_cnt(g)) for i, (_, g, _) in enumerate(base_stages)]
        pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in poly_coords)
        svg.append(f'<polyline points="{pts_str}" fill="none" stroke="var(--brand)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')

    # Multi-tool branches from q3 to Final
    if tool_branches and base_stages:
        x0, y0 = xs[len(base_stages) - 1], y_cnt(base_stages[-1][1])
        x1 = xs[-1]
        for b in reversed(tool_branches):
            y1 = y_cnt(b["gaps"])
            if b["winner"]:
                svg.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="var(--gen-closed)" stroke-width="2.2" stroke-linecap="round"/>')
            else:
                svg.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="var(--border-strong)" stroke-width="1.2" stroke-dasharray="3.5 3" stroke-linecap="round"/>')

        placed = sorted(
            [{"b": b, "y": y_cnt(b["gaps"]), "ly": y_cnt(b["gaps"])} for b in tool_branches],
            key=lambda r: (r["y"], 0 if r["b"]["winner"] else 1),
        )
        min_dy = 13.5
        for i in range(1, len(placed)):
            if placed[i]["ly"] - placed[i - 1]["ly"] < min_dy:
                placed[i]["ly"] = placed[i - 1]["ly"] + min_dy
        max_ly = base_y + 2
        if placed and placed[-1]["ly"] > max_ly:
            shift = placed[-1]["ly"] - max_ly
            for p in placed:
                p["ly"] -= shift
        for i in range(len(placed) - 2, -1, -1):
            if placed[i + 1]["ly"] - placed[i]["ly"] < min_dy:
                placed[i]["ly"] = placed[i + 1]["ly"] - min_dy

        for p in placed:
            b = p["b"]
            y1, ly = p["y"], p["ly"]
            if abs(ly - y1) > 2.5:
                svg.append(f'<line x1="{x1 + 4:.1f}" y1="{y1:.1f}" x2="{x1 + 9:.1f}" y2="{ly:.1f}" stroke="var(--border-default)" stroke-width=".9"/>')
            cl_str = f" ({b['closed']}/{b['denom']})" if b["denom"] else ""
            if b["winner"]:
                svg.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="3.8" fill="var(--gen-closed)" stroke="var(--surface-panel)" stroke-width="1.4"><title>{esc(b["full_name"])}: {b["gaps"]} gaps, closed {b["closed"]}/{b["denom"]}</title></circle>')
                svg.append(f'<text x="{x1 + 10:.1f}" y="{ly + 3:.1f}" class="ov-lbl-win">★ {esc(b["name"])} {b["gaps"]}{esc(cl_str)}</text>')
            else:
                svg.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="2.7" fill="var(--surface-panel)" stroke="var(--border-strong)" stroke-width="1.4"><title>{esc(b["full_name"])}: {b["gaps"]} gaps, closed {b["closed"]}/{b["denom"]}</title></circle>')
                svg.append(f'<text x="{x1 + 10:.1f}" y="{ly + 3:.1f}" class="ov-lbl-sub">{esc(b["name"])} {b["gaps"]}{esc(cl_str)}</text>')

    for i, (lbl, g, _) in enumerate(base_stages):
        x, y = xs[i], y_cnt(g)
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="var(--brand)" stroke="var(--surface-panel)" stroke-width="1.4"><title>{esc(lbl)}: {g} gaps</title></circle>')
        svg.append(f'<text x="{x:.1f}" y="{y - 7:.1f}" text-anchor="middle" class="ov-val-txt">{g}</text>')
        svg.append(f'<text x="{x:.1f}" y="{H - 8}" text-anchor="middle" class="ov-ax-lbl">{esc(lbl)}</text>')

    if tool_branches:
        svg.append(f'<text x="{xs[-1]:.1f}" y="{H - 8}" text-anchor="middle" class="ov-ax-lbl is-win">Final</text>')

    svg.append("</svg>")

    meta_bits = []
    if base_stages:
        s_g = base_stages[0][1]
        e_g = tool_branches[0]["gaps"] if tool_branches else base_stages[-1][1]
        meta_bits.append(f"{s_g} → {e_g}")
    if len(bar_bps) >= 2 and bar_bps[0] > 0:
        d_bp = bar_bps[-1] - bar_bps[0]
        pct = round(100 * d_bp / bar_bps[0])
        if d_bp < 0:
            meta_bits.append(f"N {pct}%")
    meta = f'<span class="ov-chart-meta is-ok">{esc(" · ".join(meta_bits))}</span>' if meta_bits else ""
    return "".join(svg), meta


def _svg_contig_continuity(stages, sv, fstats, auto):
    """Chart 2: Gap-split Contig N50 leap & block count reduction across stages (with Scaffold N50 reference line)."""
    W, H = 460, 176
    pad_l, pad_r, pad_t, pad_b = 44, 18, 24, 34
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    base_y = pad_t + plot_h

    items = []
    use_contig = True
    for st in stages:
        res = _contig_continuity(st["rows"])
        if res is not None:
            cn50, ccnt = res
            items.append((st["tag"], cn50, ccnt, st["is_final"]))

    if not items:
        use_contig = False
        for k in ("q0", "q1", "q2", "q3"):
            v = (sv.get(k) or {}).get("n50_bp")
            if v:
                items.append((k, int(v), None, False))
        if auto and fstats and fstats.get("n50_bp"):
            items.append(("Final", int(fstats["n50_bp"]), None, True))

    if not items:
        return '<p class="muted" style="margin:.5rem 0">' + bi("暂无连续性统计数据。", "No continuity data.") + "</p>", ""

    scaf_n50 = (fstats or {}).get("n50_bp") or (sv.get("q3") or {}).get("n50_bp") or (sv.get("q0") or {}).get("n50_bp") or 0
    max_v = max([1, *(x[1] for x in items), scaf_n50 if use_contig else 0])
    y_top = max_v * 1.15

    def y_pos(val):
        return pad_t + plot_h * (1.0 - max(0, val) / max(1, y_top))

    svg = [f'<svg class="ov-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Contig continuity">']
    # Y-axis gridlines (0, 50%, 100% of max_v)
    for frac in (0.0, 0.5, 1.0):
        v = max_v * frac
        y = y_pos(v)
        dash = "" if frac == 0 else ' stroke-dasharray="2.5 3"'
        svg.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{W - pad_r}" y2="{y:.1f}" stroke="var(--border-subtle)"{dash}/>')
        svg.append(f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" class="ov-ax-txt">{esc("0" if frac == 0 else _fmt_compact_bp(round(v)))}</text>')

    # Scaffold N50 dashed reference line when showing Contig N50
    if use_contig and scaf_n50 > 0:
        sy = y_pos(scaf_n50)
        svg.append(f'<line x1="{pad_l}" y1="{sy:.1f}" x2="{W - pad_r}" y2="{sy:.1f}" stroke="var(--border-strong)" stroke-width="1" stroke-dasharray="4 3"/>')
        svg.append(f'<text x="{W - pad_r}" y="{sy - 4:.1f}" text-anchor="end" class="ov-ax-txt">Scaffold N50 {esc(_fmt_compact_bp(scaf_n50))}</text>')

    n = len(items)
    slot = plot_w / max(1, n)
    bw = min(34.0, slot * 0.48)
    for i, (lbl, val, cnt, is_fin) in enumerate(items):
        cx = pad_l + slot * (i + 0.5)
        y = y_pos(val)
        bh = max(3.0, base_y - y)
        col = "var(--gen-closed)" if is_fin else "var(--brand)"
        op = ".92" if is_fin else ".8"
        tip = f"{lbl}: {'Contig' if use_contig else 'Scaffold'} N50 {val:,} bp" + (f" ({cnt} blocks)" if cnt else "")
        svg.append(f'<rect x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="2.5" fill="{col}" opacity="{op}"><title>{esc(tip)}</title></rect>')
        svg.append(f'<text x="{cx:.1f}" y="{y - 5:.1f}" text-anchor="middle" class="ov-val-txt">{esc(_fmt_compact_bp(val))}</text>')
        lcls = "ov-ax-lbl is-win" if is_fin else "ov-ax-lbl"
        svg.append(f'<text x="{cx:.1f}" y="{base_y + 13:.1f}" text-anchor="middle" class="{lcls}">{esc(lbl)}</text>')
        if cnt is not None:
            svg.append(f'<text x="{cx:.1f}" y="{base_y + 25:.1f}" text-anchor="middle" class="ov-ax-txt t-zh">{cnt}段</text>')
            svg.append(f'<text x="{cx:.1f}" y="{base_y + 25:.1f}" text-anchor="middle" class="ov-ax-txt t-en">{cnt} ctgs</text>')

    svg.append("</svg>")

    meta = ""
    if use_contig and len(items) >= 2 and items[0][1] > 0:
        v0, v1 = items[0][1], items[-1][1]
        pct = round(100 * (v1 - v0) / v0)
        if pct > 0:
            meta = f'<span class="ov-chart-meta is-ok">Contig N50 {_fmt_compact_bp(v0)} → {_fmt_compact_bp(v1)} (+{pct}%)</span>'
        else:
            meta = f'<span class="ov-chart-meta">Contig N50 {_fmt_compact_bp(v1)}</span>'
    elif scaf_n50:
        n90 = (sv.get("q3") or {}).get("n90_bp")
        txt = f"N50 {_fmt_compact_bp(scaf_n50)}" + (f" · N90 {_fmt_compact_bp(n90)}" if n90 else "")
        meta = f'<span class="ov-chart-meta">{esc(txt)}</span>'
    return "".join(svg), meta


def _donut_svg(cx, cy, r, sw, slices, center_big, center_sub):
    circ = 2.0 * math.pi * r
    total = sum(max(0.0, float(v)) for v, _ in slices)
    out = [f'<g><circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="var(--surface-muted)" stroke-width="{sw}"/>']
    if total > 0:
        offset = 0.0
        for val, col in slices:
            frac = max(0.0, float(val)) / total
            if frac <= 0:
                continue
            dash = frac * circ
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-width="{sw}" '
                f'stroke-dasharray="{dash:.2f} {circ:.2f}" stroke-dashoffset="{-offset:.2f}" '
                f'transform="rotate(-90 {cx} {cy})"/>'
            )
            offset += dash
    out.append(f'<text x="{cx}" y="{cy + 1}" text-anchor="middle" class="ov-donut-big">{esc(center_big)}</text>')
    if center_sub:
        out.append(f'<text x="{cx}" y="{cy + 13}" text-anchor="middle" class="ov-donut-sub">{esc(center_sub)}</text>')
    out.append("</g>")
    return "".join(out)


def _svg_donuts(sv, fstats, tel_info, lgz, colors, auto):
    """Chart 3: Refined 3-donut structural completeness trio + Anchoring & N% header meta."""
    W, H = 460, 172
    r, sw, cy = 34, 8.5, 58
    cxs = (78, 230, 382)

    q0_g = (sv.get("q0") or {}).get("gap_count")
    q3_g = (sv.get("q3") or {}).get("gap_count")
    fin_g = fstats["gaps"] if fstats else q3_g
    if q0_g is None:
        q0_g = fin_g or 0
    if q3_g is None:
        q3_g = q0_g
    if fin_g is None:
        fin_g = q3_g
    lgz_closed = max(0, q0_g - q3_g)
    ref_closed = max(0, q3_g - fin_g) if auto else 0
    rem_g = max(0, fin_g)
    tot_closed = lgz_closed + ref_closed
    if q0_g > 0:
        pct = round(100 * tot_closed / q0_g)
        d1 = _donut_svg(cxs[0], cy, r, sw, [(lgz_closed, "var(--brand)"), (ref_closed, "var(--gen-closed)"), (rem_g, "var(--surface-muted)")], f"{pct}%", f"{tot_closed}/{q0_g}")
        cap1_zh = f"LGZ {lgz_closed} · 精修 {ref_closed}" if auto else f"LGZ 闭合 {lgz_closed}"
        cap1_en = f"LGZ {lgz_closed} · Ref {ref_closed}" if auto else f"LGZ {lgz_closed} closed"
    else:
        d1 = _donut_svg(cxs[0], cy, r, sw, [(1, "var(--gen-closed)")], "100%", "0 Gap")
        cap1_zh, cap1_en = "无初始 Gap", "No initial gaps"

    if tel_info["available"]:
        ok_t = tel_info["present"] + tel_info["extended"]
        tot_t = tel_info["total"]
        pct_t = round(100 * ok_t / max(1, tot_t))
        d2 = _donut_svg(cxs[1], cy, r, sw, [(tel_info["present"], "var(--brand)"), (tel_info["extended"], "var(--gen-closed)"), (tel_info["missing"], "var(--surface-muted)")], f"{ok_t}/{tot_t}", f"{pct_t}%")
        both, chrt = tel_info["both"], tel_info["chr_total"]
        if tel_info["extended"] > 0:
            cap2_zh = f"补齐 +{tel_info['extended']} · 双端 {both}/{chrt}"
            cap2_en = f"+{tel_info['extended']} ext · {both}/{chrt} both"
        else:
            cap2_zh = f"双端完整 {both}/{chrt}"
            cap2_en = f"Both ends {both}/{chrt}"
    else:
        d2 = _donut_svg(cxs[1], cy, r, sw, [], "—", "N/A")
        cap2_zh, cap2_en = "未扫描", "Not scanned"

    assemblies = (lgz.get("inputs") or {}).get("assemblies") or []
    src_bp = (fstats or {}).get("source_bp") or {}
    if len(assemblies) >= 2 and src_bp:
        slices = [(bp, f"var(--ds-{colors.get(ds, 0)})") for ds, bp in sorted(src_bp.items(), key=lambda kv: -kv[1])]
        if (fstats or {}).get("patch_bp"):
            slices.append((fstats["patch_bp"], "var(--gen-closed)"))
        if (fstats or {}).get("gap_bp"):
            slices.append((fstats["gap_bp"], "var(--surface-muted)"))
        tot_bp = (fstats or {}).get("total_bp") or sum(src_bp.values())
        d3 = _donut_svg(cxs[2], cy, r, sw, slices, _fmt_compact_bp(tot_bp), f"{len(src_bp)} src")
        t3_zh, t3_en = "序列来源", "Sources"
        _, top_bp = max(src_bp.items(), key=lambda kv: kv[1])
        top_pct = round(100 * top_bp / max(1, tot_bp))
        cap3_zh, cap3_en = f"主来源 {top_pct}%", f"Top {top_pct}%"
    else:
        gf = (fstats or {}).get("gap_free_chrs")
        cn = (fstats or {}).get("chr_count")
        if gf is None:
            chrs = lgz.get("chromosomes") or []
            cn = len(chrs)
            gf = sum(1 for c in chrs if (c.get("remaining_gap_count") or 0) == 0)
        pct_gf = round(100 * gf / max(1, cn)) if cn else 0
        d3 = _donut_svg(cxs[2], cy, r, sw, [(gf, "var(--gen-closed)"), (max(0, (cn or 0) - gf), "var(--surface-muted)")], f"{gf}/{cn or 0}", f"{pct_gf}%")
        t3_zh, t3_en = "无 Gap 染色体", "Gap-free"
        cen_n = (lgz.get("outcome") or {}).get("centromere_chromosome_count")
        if cen_n:
            cap3_zh, cap3_en = f"着丝粒 {cen_n}/{cn or 0}", f"Cen {cen_n}/{cn or 0}"
        else:
            tot_bp = (fstats or {}).get("total_bp") or (sv.get("q3") or {}).get("length_bp") or 0
            cap3_zh, cap3_en = fmt_bp_short(tot_bp), fmt_bp_short(tot_bp)

    titles = [
        (cxs[0], "Gap 闭合", "Gap Closure", cap1_zh, cap1_en),
        (cxs[1], "端粒覆盖", "Telomeres", cap2_zh, cap2_en),
        (cxs[2], t3_zh, t3_en, cap3_zh, cap3_en),
    ]
    svg = [f'<svg class="ov-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Completeness gauges">', d1, d2, d3]
    for cx, zh, en, czh, cen in titles:
        svg.append(f'<text x="{cx}" y="114" text-anchor="middle" class="ov-donut-title t-zh">{esc(zh)}</text>')
        svg.append(f'<text x="{cx}" y="114" text-anchor="middle" class="ov-donut-title t-en">{esc(en)}</text>')
        svg.append(f'<text x="{cx}" y="129" text-anchor="middle" class="ov-donut-cap t-zh">{esc(czh)}</text>')
        svg.append(f'<text x="{cx}" y="129" text-anchor="middle" class="ov-donut-cap t-en">{esc(cen)}</text>')
    svg.append(
        '<g transform="translate(110,154)">'
        '<rect x="0" y="-6.5" width="7" height="7" rx="1.5" fill="var(--brand)"/>'
        '<text x="11" y="0" class="ov-leg-txt t-zh">LGZ / 原有</text><text x="11" y="0" class="ov-leg-txt t-en">LGZ / Orig</text>'
        '<rect x="88" y="-6.5" width="7" height="7" rx="1.5" fill="var(--gen-closed)"/>'
        '<text x="99" y="0" class="ov-leg-txt t-zh">精修 / 达标</text><text x="99" y="0" class="ov-leg-txt t-en">Refined / OK</text>'
        '<rect x="180" y="-6.5" width="7" height="7" rx="1.5" fill="var(--surface-muted)" stroke="var(--border-default)"/>'
        '<text x="191" y="0" class="ov-leg-txt t-zh">剩余 / 缺失</text><text x="191" y="0" class="ov-leg-txt t-en">Remaining</text>'
        "</g>"
    )
    svg.append("</svg>")

    # Header right meta: Anchoring rate & N%
    meta_bits = []
    sel_bp = (lgz.get("q0") or {}).get("selected_source_bp")
    in_bp = sum(int((a.get("stats") or {}).get("length_bp") or 0) for a in assemblies)
    if sel_bp and in_bp > 0:
        anc = min(100.0, 100.0 * sel_bp / in_bp)
        meta_bits.append(bi(f"锚定 {anc:.1f}%", f"Anchored {anc:.1f}%"))
    tot_fin_bp = (fstats or {}).get("total_bp") or (sv.get("q3") or {}).get("length_bp") or 0
    fin_nbp = (fstats or {}).get("gap_bp") if fstats is not None else (sv.get("q3") or {}).get("n_bp")
    if tot_fin_bp > 0 and fin_nbp is not None:
        npct = 100.0 * fin_nbp / tot_fin_bp
        meta_bits.append(f"N {npct:.2f}%")
    meta = f'<span class="ov-chart-meta">{" · ".join(meta_bits)}</span>' if meta_bits else ""
    return "".join(svg), meta


def _svg_chr_coverage_t2t(lgz, chr_order, fstats, tel_info, cen_map):
    """Chart 4: Per-chromosome Assembly/Ref coverage ratio & T2T structural badges."""
    W, H = 460, 172
    refs = lgz.get("reference_tracks") or {}
    chrs_map = {c.get("chromosome"): c for c in (lgz.get("chromosomes") or []) if isinstance(c, dict)}
    fper = (fstats or {}).get("per_chr") or {}

    items = []
    for cname in chr_order:
        if cname in fper:
            clen, cgaps = fper[cname]["len"], fper[cname]["gaps"]
        elif cname in chrs_map:
            clen = int(chrs_map[cname].get("length_bp") or 0)
            cgaps = int(chrs_map[cname].get("remaining_gap_count") or 0)
        else:
            continue
        rlen = int((refs.get(cname) or {}).get("length_bp") or 0)
        ratio = (100.0 * clen / rlen) if rlen > 0 else None
        tpair = tel_info["per_chr"].get(cname) if tel_info["available"] else None
        ok5 = bool(tpair and tpair[0] in ("already_present", "extended", "accepted", "added"))
        ok3 = bool(tpair and tpair[1] in ("already_present", "extended", "accepted", "added"))
        has_cen = bool(cen_map.get(cname))
        is_t2t = (cgaps == 0) and (not tel_info["available"] or (ok5 and ok3))
        items.append({
            "chr": cname, "len": clen, "gaps": cgaps, "ref_len": rlen,
            "ratio": ratio, "ok5": ok5, "ok3": ok3, "has_cen": has_cen, "t2t": is_t2t,
        })

    if not items:
        return '<p class="muted" style="margin:.5rem 0">' + bi("暂无染色体统计数据。", "No chromosome data.") + "</p>", ""

    has_ref = any(x["ratio"] is not None for x in items)
    max_len = max(1, max(x["len"] for x in items))
    shown = items[:6] if len(items) > 6 else items
    row_h = min(24.0, (H - 34.0) / max(1, len(shown)))
    bar_x, bar_w = 92, 198

    svg = [f'<svg class="ov-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Chromosome coverage">']
    # Reference 100% dashed vertical guide line
    if has_ref:
        svg.append(f'<line x1="{bar_x + bar_w}" y1="10" x2="{bar_x + bar_w}" y2="{12 + len(shown) * row_h:.1f}" stroke="var(--border-default)" stroke-dasharray="2.5 3"/>')
        svg.append(f'<text x="{bar_x + bar_w}" y="{H - 8}" text-anchor="end" class="ov-ax-txt">Ref 100%</text>')

    for i, it in enumerate(shown):
        y = 14 + i * row_h
        frac = min(1.0, (it["ratio"] / 100.0)) if (has_ref and it["ratio"] is not None) else (it["len"] / max_len)
        bw = max(4.0, bar_w * frac)
        if it["t2t"]:
            fill = "var(--gen-closed)"
        elif has_ref and it["ratio"] is not None and it["ratio"] < 70.0:
            fill = "var(--gen-patch)"
        else:
            fill = "var(--brand)"
        tip = f'{it["chr"]}: {it["len"]:,} bp' + (f' / Ref {it["ref_len"]:,} bp ({it["ratio"]:.1f}%)' if it["ratio"] is not None else "") + f' · {it["gaps"]} gaps'
        svg.append(f'<text x="{bar_x - 8}" y="{y + 10:.1f}" text-anchor="end" class="ov-bar-lbl">{esc(it["chr"])}</text>')
        svg.append(f'<rect x="{bar_x}" y="{y + 2:.1f}" width="{bar_w}" height="10" rx="2" fill="var(--surface-muted)"/>')
        svg.append(f'<rect x="{bar_x}" y="{y + 2:.1f}" width="{bw:.1f}" height="10" rx="2" fill="{fill}" opacity=".9"><title>{esc(tip)}</title></rect>')

        val_str = f"{it['ratio']:.1f}%" if it["ratio"] is not None else _fmt_compact_bp(it["len"])
        t_str = f" · {'●' if it['ok5'] else '○'}{'●' if it['ok3'] else '○'}" if tel_info["available"] else ""
        c_str = " ◆" if it["has_cen"] else ""
        vcls = "ov-bar-val is-win" if it["t2t"] else "ov-bar-val"
        svg.append(f'<text x="{bar_x + bar_w + 8}" y="{y + 10:.1f}" class="{vcls}">{esc(val_str)} · {it["gaps"]}G{t_str}{c_str}</text>')

    # Compact symbol legend bottom-left
    leg_bits = []
    if tel_info["available"]:
        leg_bits.append("●/○ 5′/3′ 端粒" )
    if any(x["has_cen"] for x in items):
        leg_bits.append("◆ 着丝粒")
    if len(items) > len(shown):
        leg_bits.append(f"前 {len(shown)}/{len(items)} 条")
    if leg_bits:
        svg.append(f'<text x="{bar_x}" y="{H - 8}" class="ov-leg-txt">{esc(" · ".join(leg_bits))}</text>')
    svg.append("</svg>")

    t2t_n = sum(1 for x in items if x["t2t"])
    meta_bits = []
    if tel_info["available"]:
        meta_bits.append(f"T2T {t2t_n}/{len(items)}")
    else:
        meta_bits.append(bi(f"无Gap {t2t_n}/{len(items)}", f"Gap-free {t2t_n}/{len(items)}"))
    if has_ref:
        avg_cov = sum(x["ratio"] for x in items if x["ratio"] is not None) / max(1, sum(1 for x in items if x["ratio"] is not None))
        meta_bits.append(bi(f"均覆盖 {avg_cov:.1f}%", f"Avg {avg_cov:.1f}%"))
    meta = f'<span class="ov-chart-meta">{" · ".join(meta_bits)}</span>'
    return "".join(svg), meta


def _fmt_mem(mb):
    if mb is None:
        return "—"
    v = max(0.0, float(mb))
    if v >= 1024.0:
        return f"{v / 1024.0:.2f} GB"
    return f"{v:.0f} MB" if v >= 10 else f"{v:.1f} MB"


def _parse_iso_ts(raw):
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _runtime_modal_html(units, buckets, total_sec, wall_span, max_rss):
    """Build detailed SVG charts (unit durations, Gantt timeline / peak memory) + table for modal."""
    stage_meta = {k: (zh, en, col) for k, zh, en, col in buckets}

    # Summary strip
    n_comp = sum(1 for u in units if u.get("execution") == "computed")
    n_cache = sum(1 for u in units if u.get("execution") == "cache_reused")
    strip_bits = [
        f'<span>{bi("累计单元耗时", "Total unit time")} <b>{esc(_fmt_dur(total_sec))}</b></span>',
    ]
    if wall_span is not None and wall_span > 0:
        strip_bits.append(f'<span>{bi("墙钟跨度", "Wall span")} <b>{esc(_fmt_dur(wall_span))}</b></span>')
    strip_bits.append(f'<span>{bi(f"单元 {len(units)}（计算 {n_comp} · 复用 {n_cache}）", f"{len(units)} units ({n_comp} computed · {n_cache} cached)")}</span>')
    if max_rss is not None:
        strip_bits.append(f'<span>{bi("峰值内存", "Peak RSS")} <b class="is-ok">{esc(_fmt_mem(max_rss))}</b></span>')
    else:
        strip_bits.append(f'<span class="muted">{bi("内存：未采集（新运行自动记录）", "Memory: not recorded (captured on new runs)")}</span>')
    summary_strip = f'<div class="story-meta-strip ov-rt-strip">{"".join(strip_bits)}</div>'

    # Chart A: Horizontal Unit Duration Breakdown (show non-zero units; cap at 16 by grouping smallest tail)
    nz = [u for u in units if float(u.get("elapsed_seconds") or 0.0) > 0]
    chart_rows = []
    if len(nz) <= 16:
        chart_rows = [(u["unit"], u.get("stage") or "", float(u["elapsed_seconds"]), u.get("execution") == "cache_reused") for u in nz]
    else:
        top = sorted(nz, key=lambda u: float(u["elapsed_seconds"]), reverse=True)[:15]
        top_ids = {u["unit"] for u in top}
        for u in nz:
            if u["unit"] in top_ids:
                chart_rows.append((u["unit"], u.get("stage") or "", float(u["elapsed_seconds"]), u.get("execution") == "cache_reused"))
        rest = sum(float(u["elapsed_seconds"]) for u in nz if u["unit"] not in top_ids)
        if rest > 0:
            chart_rows.append((f"+{len(nz) - len(top_ids)} others", "", rest, False))

    W = 460
    max_s = max([0.1, *(r[2] for r in chart_rows)])
    rh_a = 20
    H_a = max(144, 16 + len(chart_rows) * rh_a + 10)
    bx_a, bw_a = 128, 224
    svg_a = [f'<svg class="ov-svg" viewBox="0 0 {W} {H_a}" role="img" aria-label="Unit duration breakdown">']
    for i, (uname, st, sec, is_cached) in enumerate(chart_rows):
        y = 12 + i * rh_a
        col = stage_meta.get(st, ("", "", "var(--brand)"))[2]
        fw = max(3.0, bw_a * sec / max_s)
        pct = 100.0 * sec / max(0.001, total_sec)
        disp = uname if len(uname) <= 19 else uname[:18] + "…"
        svg_a.append(f'<text x="{bx_a - 8}" y="{y + 10}" text-anchor="end" class="ov-bar-lbl"><title>{esc(uname)}</title>{esc(disp)}</text>')
        svg_a.append(f'<rect x="{bx_a}" y="{y + 1.5}" width="{bw_a}" height="10" rx="2" fill="var(--surface-muted)"/>')
        op = ".48" if is_cached else ".92"
        svg_a.append(f'<rect x="{bx_a}" y="{y + 1.5}" width="{fw:.1f}" height="10" rx="2" fill="{col}" opacity="{op}"><title>{esc(uname)}: {_fmt_dur(sec)} ({sec:.1f}s, {pct:.1f}%)</title></rect>')
        svg_a.append(f'<text x="{bx_a + bw_a + 8}" y="{y + 10}" class="ov-bar-val">{esc(_fmt_dur(sec))} · {pct:.1f}%</text>')
    svg_a.append("</svg>")
    card_a = f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("任务耗时分布", "Unit Durations")}</h4><span class="ov-chart-meta">{bi("浅色 = 缓存复用", "Faded = cached")}</span></div>{"".join(svg_a)}</article>'

    # Chart B1: Peak Memory Chart (when peak_rss_mb is recorded)
    mem_units = [u for u in units if u.get("peak_rss_mb") is not None and float(u["peak_rss_mb"]) > 0]
    card_mem = ""
    if mem_units:
        mem_shown = mem_units[:12] if len(mem_units) <= 12 else sorted(mem_units, key=lambda u: float(u["peak_rss_mb"]), reverse=True)[:12]
        max_m = max(1.0, max(float(u["peak_rss_mb"]) for u in mem_shown))
        rh_m = 20
        H_m = max(144, 16 + len(mem_shown) * rh_m + 10)
        bx_m, bw_m = 128, 240
        svg_m = [f'<svg class="ov-svg" viewBox="0 0 {W} {H_m}" role="img" aria-label="Peak memory breakdown">']
        for i, u in enumerate(mem_shown):
            y = 12 + i * rh_m
            mb = float(u["peak_rss_mb"])
            col = stage_meta.get(u.get("stage") or "", ("", "", "var(--brand)"))[2]
            fw = max(3.0, bw_m * mb / max_m)
            disp = u["unit"] if len(u["unit"]) <= 19 else u["unit"][:18] + "…"
            svg_m.append(f'<text x="{bx_m - 8}" y="{y + 10}" text-anchor="end" class="ov-bar-lbl"><title>{esc(u["unit"])}</title>{esc(disp)}</text>')
            svg_m.append(f'<rect x="{bx_m}" y="{y + 1.5}" width="{bw_m}" height="10" rx="2" fill="var(--surface-muted)"/>')
            svg_m.append(f'<rect x="{bx_m}" y="{y + 1.5}" width="{fw:.1f}" height="10" rx="2" fill="{col}" opacity=".88"><title>{esc(u["unit"])}: {_fmt_mem(mb)}</title></rect>')
            svg_m.append(f'<text x="{bx_m + bw_m + 8}" y="{y + 10}" class="ov-bar-val">{esc(_fmt_mem(mb))}</text>')
        svg_m.append("</svg>")
        card_mem = f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("峰值内存分布 (RSS)", "Peak Memory (RSS)")}</h4><span class="ov-chart-meta is-ok">{esc(_fmt_mem(max_rss))}</span></div>{"".join(svg_m)}</article>'

    # Chart B2: Wall-clock Gantt Timeline (when timestamps are available)
    gantt_items = []
    for u in units:
        t0 = _parse_iso_ts(u.get("started_at"))
        t1 = _parse_iso_ts(u.get("ended_at"))
        sec = float(u.get("elapsed_seconds") or 0.0)
        if t1 is not None and t0 is None and sec > 0:
            t0 = t1 - sec
        if t0 is not None and t1 is not None and t1 >= t0 and (t1 - t0 > 0 or sec > 0):
            gantt_items.append((u["unit"], u.get("stage") or "", t0, max(t1, t0 + sec), u.get("elapsed_seconds"), u.get("execution") == "cache_reused"))
    card_gantt = ""
    if gantt_items:
        t_min = min(x[2] for x in gantt_items)
        t_max = max(x[3] for x in gantt_items)
        span = max(1.0, t_max - t_min)
        g_shown = gantt_items[:18]
        rh_g = 18
        H_g = max(144, 18 + len(g_shown) * rh_g + 22)
        bx_g, bw_g = 128, 312
        svg_g = [f'<svg class="ov-svg" viewBox="0 0 {W} {H_g}" role="img" aria-label="Execution timeline">']
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            gx = bx_g + bw_g * frac
            svg_g.append(f'<line x1="{gx:.1f}" y1="10" x2="{gx:.1f}" y2="{H_g - 20}" stroke="var(--border-subtle)" stroke-dasharray="{"" if frac in (0.0, 1.0) else "2.5 3"}"/>')
            svg_g.append(f'<text x="{gx:.1f}" y="{H_g - 7}" text-anchor="{"start" if frac == 0 else ("end" if frac == 1 else "middle")}" class="ov-ax-txt">{esc("0" if frac == 0 else _fmt_dur(span * frac))}</text>')
        for i, (uname, st, t0, t1, sec, is_cached) in enumerate(g_shown):
            y = 14 + i * rh_g
            col = stage_meta.get(st, ("", "", "var(--brand)"))[2]
            rx = bx_g + bw_g * ((t0 - t_min) / span)
            rw = max(3.5, bw_g * ((t1 - t0) / span))
            disp = uname if len(uname) <= 19 else uname[:18] + "…"
            svg_g.append(f'<text x="{bx_g - 8}" y="{y + 9}" text-anchor="end" class="ov-bar-lbl"><title>{esc(uname)}</title>{esc(disp)}</text>')
            svg_g.append(f'<rect x="{rx:.1f}" y="{y + 1.5}" width="{rw:.1f}" height="9" rx="2" fill="{col}" opacity="{".48" if is_cached else ".92"}"><title>{esc(uname)}: {_fmt_dur(sec) if sec is not None else "—"} (offset +{_fmt_dur(t0 - t_min)})</title></rect>')
        svg_g.append("</svg>")
        card_gantt = f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("执行时间轴 (甘特图)", "Execution Timeline")}</h4><span class="ov-chart-meta">{esc(_fmt_dur(span))}</span></div>{"".join(svg_g)}</article>'

    # Arrange charts neatly (2-col grid; if 3 charts, Gantt spans full width cleanly)
    charts_html = ""
    if card_mem and card_gantt:
        charts_html = f'<div class="ov-charts-grid">{card_a}{card_mem}</div><div style="margin-top:.75rem">{card_gantt}</div>'
    elif card_mem:
        charts_html = f'<div class="ov-charts-grid">{card_a}{card_mem}</div>'
    elif card_gantt:
        charts_html = f'<div class="ov-charts-grid">{card_a}{card_gantt}</div>'
    else:
        charts_html = card_a

    # Detail table
    exec_labels = {
        "computed": bi("实际计算", "Computed"),
        "cache_reused": bi("缓存复用", "Cached"),
        "frozen_original_lgz": bi("复用原 LGZ", "Frozen LGZ"),
        "failed": bi("失败", "Failed"),
    }
    trows = []
    for u in units:
        sec = u.get("elapsed_seconds")
        sec_f = float(sec) if sec is not None else 0.0
        pct = f"{100.0 * sec_f / total_sec:.1f}%" if (sec is not None and total_sec > 0) else "—"
        st = u.get("stage") or ""
        st_lbl = bi(stage_meta[st][0], stage_meta[st][1]) if st in stage_meta else esc(st or "—")
        ex_lbl = exec_labels.get(u.get("execution") or "", esc(u.get("execution") or "—"))
        rss = _fmt_mem(u.get("peak_rss_mb"))
        st_txt = u.get("status") or "—"
        st_cls = "tone-ok" if st_txt == "success" else ("tone-err" if st_txt in ("failed", "interrupted") else "tone-neutral")
        trows.append(
            f'<tr><th scope="row"><code>{esc(u["unit"])}</code></th>'
            f'<td>{st_lbl}</td><td>{ex_lbl}</td>'
            f'<td class="numeric">{esc(_fmt_dur(sec_f)) if sec is not None else "—"}</td>'
            f'<td class="numeric">{esc(pct)}</td>'
            f'<td class="numeric">{esc(rss)}</td>'
            f'<td><span class="badge {st_cls}">{esc(st_txt)}</span></td></tr>'
        )
    table_html = (
        '<div class="project-dataset-scroll" style="margin-top:.85rem">'
        '<table class="project-dataset-table ov-rt-table">'
        '<thead><tr>'
        f'<th scope="col">{bi("执行单元", "Unit")}</th>'
        f'<th scope="col">{bi("阶段", "Stage")}</th>'
        f'<th scope="col">{bi("方式", "Mode")}</th>'
        f'<th scope="col">{bi("耗时", "Duration")}</th>'
        f'<th scope="col">{bi("占比", "Share")}</th>'
        f'<th scope="col">{bi("峰值内存", "Peak RSS")}</th>'
        f'<th scope="col">{bi("状态", "Status")}</th>'
        f'</tr></thead><tbody>{"".join(trows)}</tbody></table></div>'
    )

    return (
        '<template id="ov-runtime-modal" data-title-zh="运行耗时与资源详情" data-title-en="Runtime & Resource Details">'
        + summary_strip + charts_html + table_html
        + "</template>"
    )


def _expand_refinement_units(vm, raw_units):
    """Expand the coarse `refinement` unit into per-tool auto-refinement rows and include manual tool timings."""
    auto_tools = (vm.get("refinement_summary") or {}).get("tools") or []
    auto_rows = []
    for t in auto_tools:
        tm = t.get("timing")
        if not isinstance(tm, dict):
            continue
        sec = tm.get("elapsed_seconds")
        if sec is None:
            sec = tm.get("native_seconds")
        if sec is None and tm.get("peak_rss_mb") is None:
            continue
        tname = NAMES.get(t["tool"], t["tool"])
        reused = bool(t.get("native_reused") or t.get("result_reused"))
        st_raw = t.get("status") or "published"
        st_norm = "success" if st_raw == "published" else ("failed" if st_raw in ("failed", "invalidated") else st_raw)
        auto_rows.append({
            "unit": f"refine:{tname}",
            "stage": "refinement",
            "status": st_norm,
            "execution": "cache_reused" if reused else "computed",
            "elapsed_seconds": float(sec) if sec is not None else None,
            "peak_rss_mb": tm.get("peak_rss_mb"),
            "started_at": tm.get("started_at"),
            "ended_at": tm.get("ended_at"),
            "_order": (tm.get("started_at") or "9999", tool_order(t["tool"])),
        })
    auto_rows.sort(key=lambda r: r["_order"])
    for r in auto_rows:
        r.pop("_order", None)

    expanded = []
    inserted_auto = False
    for u in raw_units:
        if u.get("unit") == "refinement" and auto_rows:
            inserted_auto = True
            # Keep the measured parent total until every tool has a duration.
            # Missing tool time is not zero or inferred publication overhead.
            if any(row["elapsed_seconds"] is None for row in auto_rows):
                expanded.append(u)
                continue
            expanded.extend(auto_rows)
            parent_sec = float(u.get("elapsed_seconds") or 0.0)
            tools_sum = sum(float(r.get("elapsed_seconds") or 0.0) for r in auto_rows)
            overhead = parent_sec - tools_sum
            if overhead > 10.0:
                last_end = max((r["ended_at"] for r in auto_rows if r.get("ended_at")), default=None)
                expanded.append({
                    "unit": "refine:publish",
                    "stage": "refinement",
                    "status": u.get("status") or "success",
                    "execution": u.get("execution") or "computed",
                    "elapsed_seconds": round(overhead, 3),
                    "peak_rss_mb": None,
                    "started_at": last_end,
                    "ended_at": u.get("ended_at"),
                })
        else:
            expanded.append(u)
    if auto_rows and not inserted_auto:
        expanded.extend(auto_rows)

    # Append manual refinement per-tool timings (if recorded on any manual batch)
    manual_batches = (vm.get("manual_summary") or {}).get("batches") or []
    manual_agg = {}
    for b in manual_batches:
        tt = b.get("tool_timing")
        if not isinstance(tt, dict):
            continue
        for tkey, rec in tt.items():
            if not isinstance(rec, dict):
                continue
            sec = rec.get("elapsed_seconds")
            rss = rec.get("peak_rss_mb")
            if sec is None and rss is None:
                continue
            slot = manual_agg.setdefault(tkey, {
                "elapsed_seconds": 0.0, "peak_rss_mb": None,
                "started_at": None, "ended_at": None,
            })
            if sec is None:
                slot["elapsed_seconds"] = None
            elif slot["elapsed_seconds"] is not None:
                slot["elapsed_seconds"] = round(slot["elapsed_seconds"] + float(sec), 3)
            if rss is not None and float(rss) > 0:
                slot["peak_rss_mb"] = max(slot["peak_rss_mb"] or 0.0, float(rss))
            st, en = rec.get("started_at"), rec.get("ended_at")
            if st and (slot["started_at"] is None or st < slot["started_at"]):
                slot["started_at"] = st
            if en and (slot["ended_at"] is None or en > slot["ended_at"]):
                slot["ended_at"] = en
    for tkey in sorted(manual_agg, key=lambda k: (tool_order(k), k)):
        rec = manual_agg[tkey]
        tname = NAMES.get(tkey, tkey)
        expanded.append({
            "unit": f"manual:{tname}",
            "stage": "manual",
            "status": "success",
            "execution": "computed",
            "elapsed_seconds": rec["elapsed_seconds"],
            "peak_rss_mb": rec["peak_rss_mb"],
            "started_at": rec["started_at"],
            "ended_at": rec["ended_at"],
        })
    return expanded


def _runtime_bar_html(vm):
    """Compact 1-row clickable runtime bar + modal template with per-tool auto/manual breakdown."""
    lgz = vm.get("lgz_summary") or {}
    timing = lgz.get("timing") or {}
    raw_units = timing.get("units") or []
    units = _expand_refinement_units(vm, raw_units)
    if not units:
        return ""
    buckets = [
        ("alignment", "比对分组", "Align", "var(--ds-0)"),
        ("q0", "q0 构建", "q0", "var(--ds-5)"),
        ("lgz", "LGZ 修补", "LGZ", "var(--ds-1)"),
        ("refinement", "自动精修", "Refine", "var(--gen-closed)"),
        ("delivery", "打包交付", "Package", "var(--border-strong)"),
        ("manual", "手动精修", "Manual", "var(--ds-2)"),
    ]
    sums = {k: 0.0 for k, _, _, _ in buckets}
    reused = {k: True for k, _, _, _ in buckets}
    seen = {k: False for k, _, _, _ in buckets}
    rss_vals = []
    starts, ends = [], []
    for u in units:
        st = u.get("stage") or ""
        sec = float(u.get("elapsed_seconds") or 0.0)
        if st in sums:
            sums[st] += max(0.0, sec)
            seen[st] = True
            if u.get("execution") != "cache_reused":
                reused[st] = False
        if u.get("peak_rss_mb") is not None:
            try:
                rv = float(u["peak_rss_mb"])
                if rv > 0:
                    rss_vals.append(rv)
            except (ValueError, TypeError):
                pass
        t0 = _parse_iso_ts(u.get("started_at"))
        t1 = _parse_iso_ts(u.get("ended_at"))
        if t0 is not None:
            starts.append(t0)
        if t1 is not None:
            ends.append(t1)
    total = sum(sums.values())
    if total <= 0:
        return ""

    max_rss = max(rss_vals) if rss_vals else timing.get("peak_rss_mb")
    wall_span = (max(ends) - min(starts)) if (starts and ends and max(ends) >= min(starts)) else None

    segs = []
    legs = []
    for key, zh, en, col in buckets:
        sec = sums[key]
        if sec <= 0:
            continue
        pct = 100.0 * sec / total
        dur = _fmt_dur(sec)
        tag = " (cached)" if (seen[key] and reused[key]) else ""
        tip = f"{zh} / {en}: {dur} ({sec:.1f}s, {pct:.1f}%){tag}"
        segs.append(f'<span class="ov-rt-seg" style="width:{max(1.2, pct):.3f}%;background:{col}" title="{esc(tip)}"></span>')
        legs.append(f'<span class="ov-rt-item"><i class="ov-rt-dot" style="background:{col}"></i>{bi(zh, en)} <b>{esc(dur)}</b></span>')

    mem_bit = f'<span class="ov-rt-mem">{bi("峰值内存", "Peak")} <b>{esc(_fmt_mem(max_rss))}</b></span>' if max_rss else ""
    modal = _runtime_modal_html(units, buckets, total, wall_span, max_rss)
    return (
        '<button type="button" class="ov-runtime-bar" data-story-open="ov-runtime-modal" '
        'title="点击查看各任务与工具耗时、时间轴及内存详情 / Click for per-unit & per-tool runtime details">'
        f'<span class="ov-rt-head">{bi("运行耗时", "Runtime")} <b>{esc(_fmt_dur(total))}</b></span>'
        f"{mem_bit}"
        f'<span class="ov-rt-track" aria-hidden="true">{"".join(segs)}</span>'
        f'<span class="ov-rt-legend">{"".join(legs)}</span>'
        f'<span class="ov-rt-more">{bi("详情 ↗", "Details ↗")}</span>'
        "</button>"
        + modal
    )


def overview_summary_card(vm):
    """Render the opening Overview card (P1 single-rail switcher + P2 4 quality charts + runtime bar)."""
    mode = vm["meta"].get("mode")
    if mode in ("manual_only", "lgz_failed"):
        return ""
    lgz = vm.get("lgz_summary") or {}
    sv = lgz.get("sequence_versions") or {}
    chrs = lgz.get("chromosomes") or []
    versions = vm.get("final_versions") or []
    if not sv and not chrs and not versions:
        return ""

    tools = sorted((vm.get("refinement_summary") or {}).get("tools") or [], key=lambda r: tool_order(r["tool"]))
    auto = bool(tools)
    winning_v = _select_version(versions, tools, auto) if versions else None
    winning_tool_rec = (
        next((t for t in tools if winning_v and t["tool"] == winning_v["tool"]), None)
        if auto and winning_v else None
    )
    fstats = _final_track_stats(winning_v, winning_tool_rec) if (winning_v and winning_v.get("tracks")) else None

    chr_order = []
    if winning_v and winning_v.get("tracks"):
        chr_order = [c["chr"] for c in winning_v["tracks"]]
    elif chrs:
        chr_order = [c["chromosome"] for c in chrs]
    elif isinstance(lgz.get("q0_scene"), list):
        chr_order = [r["chr"] for r in lgz["q0_scene"] if isinstance(r, dict) and r.get("chr")]

    ds_names = [r["name"] for r in ((lgz.get("inputs") or {}).get("assemblies") or [])]
    if winning_v and winning_v.get("tracks"):
        for c in winning_v["tracks"]:
            for p in c.get("parts") or []:
                if p.get("source") and not p.get("edit"):
                    ds_names.append(p["source"]["dataset"])
    colors = {k: i % 6 for i, k in enumerate(dict.fromkeys(ds_names))}

    tel_info = _telomere_summary(lgz, chr_order)
    cen_map = _centromere_map(lgz)
    stages, default_key = _build_stage_tracks(vm, chr_order, colors, winning_v, winning_tool_rec, tel_info, auto)

    domain = max(
        [1]
        + [int(r.get("length_bp") or 0) for r in (lgz.get("reference_tracks") or {}).values()]
        + [int(row["len"]) for st in stages if st["rows"] for row in st["rows"].values()]
    )

    chr_n = len(chr_order) or (sv.get("q3") or {}).get("sequence_count") or 0
    tot_bp = (fstats or {}).get("total_bp") or (sv.get("q3") or {}).get("length_bp") or 0
    head_bits = []
    if chr_n:
        head_bits.append(bi(f"{chr_n} 条染色体", f"{chr_n} chrs"))
        head_bits.append(esc(fmt_bp_short(tot_bp)))
    if auto and winning_v:
        head_bits.append(esc("LGZ + " + NAMES.get(winning_v["tool"], winning_v["tool"])))
    else:
        head_bits.append("LGZ-only")
    head_right = f'<span class="ov-head-meta">{" · ".join(head_bits)}</span>'

    # P1: Stepper with animated flow connectors + single-rail stage view (zoomable & expandable)
    active_idx = next((idx for idx, st in enumerate(stages) if st["key"] == default_key), len(stages) - 1)
    active_is_final = bool(stages[active_idx]["is_final"]) if stages else False
    step_btns = []
    for i, st in enumerate(stages):
        active = i == active_idx
        done = i < active_idx
        has_rows = bool(st["rows"])
        cls = (
            "ov-step"
            + (" is-active" if active else "")
            + (" is-done" if done else "")
            + (" is-final" if st["is_final"] else "")
        )
        step_btns.append(
            f'<button type="button" class="{cls}" '
            f'data-ov-stage="{esc(st["key"])}" data-ov-idx="{i}" aria-pressed="{"true" if active else "false"}"'
            f'{"" if has_rows else " disabled"}>'
            f'<span class="ov-step-top"><span class="ov-step-tag">{esc(st["tag"])}</span>'
            f'<span class="ov-step-name">{bi(st["zh"], st["en"])}</span></span>'
            f'<span class="ov-step-sub">{bi(st["sub_zh"], st["sub_en"])}</span>'
            f"</button>"
        )
        if i + 1 < len(stages):
            passed = i < active_idx
            c_cls = "ov-step-conn" + (" is-passed" if passed else "") + (" is-final-flow" if (passed and active_is_final) else "")
            step_btns.append(
                f'<span class="{c_cls}" data-ov-conn="{i}" aria-hidden="true">'
                '<svg viewBox="0 0 28 14" width="28" height="14" fill="none">'
                '<line x1="1" y1="7" x2="21" y2="7" class="ov-conn-base"/>'
                '<line x1="1" y1="7" x2="21" y2="7" class="ov-conn-flow"/>'
                '<polyline points="17.5,3.2 22.5,7 17.5,10.8" class="ov-conn-head"/>'
                "</svg></span>"
            )

    active_stage = next((s for s in stages if s["key"] == default_key), stages[-1])
    jump_html = (
        f'<a class="ov-jump" data-ov-jump href="{esc(active_stage["href"])}">'
        f'{bi("查看", "Jump to")} <span data-ov-jump-lbl>{bi(active_stage["jump_zh"], active_stage["jump_en"])}</span> ↓</a>'
    )

    legend_bits = [f'<span class="legend-item"><i class="swatch" style="background:var(--ds-{c})"></i>{esc(ds)}</span>' for ds, c in colors.items()]
    legend_bits.append('<span class="legend-item"><i class="swatch" style="background:var(--gen-closed)"></i>' + bi("修补 / 闭合", "Repaired") + "</span>")
    legend_bits.append('<span class="legend-item"><i class="swatch is-orig-gap"></i>Gap</span>')
    if tel_info["available"]:
        legend_bits.append('<span class="legend-item"><i class="ov-tel-swatch"></i>' + bi("端粒", "Tel") + "</span>")

    ruler = (
        '<div class="ov-axis"><span>' + bi("染色体", "Chromosome") + '</span><span class="story-ruler">'
        + "".join(f"<span>{esc(fmt_bp_short(round(domain * i / 4)))}</span>" for i in range(5))
        + "</span></div>"
    )

    def _chr_row_html(cname):
        r = (active_stage["rows"] or {}).get(cname) if active_stage["rows"] else None
        clen = r["len"] if r else 0
        cgaps = r["gaps"] if r else 0
        segs = r["segs"] if r else []
        rail = _render_rail_html(
            segs, domain,
            tel_pair=tel_info["per_chr"].get(cname),
            show_tel=active_stage["show_tel"],
            cen_marks=cen_map.get(cname),
        )
        gcls = "ov-chr-gap is-zero" if cgaps == 0 else "ov-chr-gap"
        return (
            f'<details class="ov-chr-row" data-ov-chr="{esc(cname)}">'
            f'<summary>'
            f'<span class="ov-chr-meta">'
            f'<strong class="ov-chr-name" title="{esc(cname)}">{esc(cname)}</strong>'
            f'<span class="ov-chr-stats">'
            f'<small class="ov-chr-len" data-ov-len>{esc(fmt_bp_short(clen))}</small>'
            f'<small class="{gcls}" data-ov-gap>{cgaps}G</small>'
            f"</span></span>"
            f'<span class="ov-rail" data-ov-rail>{rail}</span>'
            f"</summary>"
            f'<div class="ov-chr-detail" data-ov-detail></div>'
            f"</details>"
        )

    if active_stage["rows"] and chr_order:
        visible_chrs = chr_order[:10]
        extra_chrs = chr_order[10:]
        rows_html = "".join(_chr_row_html(c) for c in visible_chrs)
        if extra_chrs:
            rows_html += (
                f'<details class="ov-more-chrs"><summary>{bi(f"展开其余 {len(extra_chrs)} 条染色体", f"Show {len(extra_chrs)} more chromosomes")}</summary>'
                + "".join(_chr_row_html(c) for c in extra_chrs)
                + "</details>"
            )
        zbtn = zoom_button("总览 · 阶段演化放大视图", "Overview · Stage Evolution Zoom")
        p1_tracks = f'<div class="ov-track-frame" data-zoom-frame="1">{ruler}<div class="ov-track-list">{rows_html}</div>{zbtn}</div>'
    else:
        p1_tracks = '<p class="muted" style="margin:.4rem 0">' + bi("当前摘要未附带分阶段片段坐标。", "Per-stage segment coordinates were not recorded.") + "</p>"

    stage_payload = {
        "domain": domain,
        "active": default_key,
        "order": [st["key"] for st in stages if st["rows"]],
        "stages": {
            st["key"]: {
                "tag": st["tag"], "zh": st["zh"], "en": st["en"],
                "href": st["href"], "jump_zh": st["jump_zh"], "jump_en": st["jump_en"],
                "show_tel": st["show_tel"], "is_final": st["is_final"],
                "rows": {
                    cname: {"l": fmt_bp_short(r["len"]), "g": r["gaps"], "s": r["segs"]}
                    for cname, r in (st["rows"] or {}).items()
                },
            }
            for st in stages if st["rows"]
        },
        "tel": {
            cname: [
                2 if s5 in ("extended", "accepted", "added") else (1 if s5 == "already_present" else 0),
                2 if s3 in ("extended", "accepted", "added") else (1 if s3 == "already_present" else 0),
            ]
            for cname, (s5, s3) in tel_info["per_chr"].items()
        } if tel_info["available"] else {},
        "cen": {cname: [[a, b] for a, b in marks] for cname, marks in cen_map.items()},
    }
    payload_json = json.dumps(stage_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    # P2: 4 genome quality charts + compact runtime strip
    c1_svg, c1_meta = _svg_gap_combo(vm, sv, versions, tools, winning_v, fstats, auto)
    c2_svg, c2_meta = _svg_contig_continuity(stages, sv, fstats, auto)
    c3_svg, c3_meta = _svg_donuts(sv, fstats, tel_info, lgz, colors, auto)
    c4_svg, c4_meta = _svg_chr_coverage_t2t(lgz, chr_order, fstats, tel_info, cen_map)
    rt_html = _runtime_bar_html(vm)

    p2_html = (
        '<div class="ov-subblock">'
        f'<div class="ov-sub-head"><h3>{bi("关键指标", "Key Metrics")}</h3></div>'
        '<div class="ov-charts-grid">'
        f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("Gap 数量与长度", "Gap Count & Length")}</h4>{c1_meta}</div>{c1_svg}</article>'
        f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("连续性跃升", "Contig Continuity")}</h4>{c2_meta}</div>{c2_svg}</article>'
        f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("结构完整度", "Structural Completeness")}</h4>{c3_meta}</div>{c3_svg}</article>'
        f'<article class="ov-chart-card"><div class="ov-chart-head"><h4>{bi("染色体覆盖与 T2T", "Chr Coverage & T2T")}</h4>{c4_meta}</div>{c4_svg}</article>'
        "</div>"
        f"{rt_html}"
        "</div>"
    )

    return (
        STYLE
        + '<section class="panel path-story" id="assembly-overview">'
        '<div class="panel-head story-head">'
        f'<h2><span>{bi("总览", "Overview")}</span></h2>'
        f'<div class="panel-head-right">{head_right}</div>'
        "</div>"
        '<div class="ov-subblock">'
        '<div class="ov-sub-head">'
        f'<h3>{bi("阶段演化", "Stage Evolution")}</h3>'
        f'<div class="ov-p1-bar"><div class="legend-row" style="margin:0">{"".join(legend_bits)}</div><span class="ov-bar-sep" aria-hidden="true"></span>{jump_html}</div>'
        "</div>"
        f'<div class="ov-stepper" role="group" aria-label="Pipeline stages">{"".join(step_btns)}</div>'
        f"{p1_tracks}"
        "</div>"
        f"{p2_html}"
        f'<script type="application/json" id="ov-stage-data">{payload_json}</script>'
        + SCRIPT
        + "</section>"
    )


STYLE = """<style>
.ov-head-meta{font-size:var(--text-sm);font-weight:500;color:var(--text-muted);font-variant-numeric:tabular-nums}
.ov-subblock+.ov-subblock{margin-top:1.05rem;padding-top:.95rem;border-top:1px solid var(--border-subtle)}
.ov-sub-head{display:flex;align-items:center;justify-content:space-between;gap:.5rem 1rem;flex-wrap:wrap;margin:0 0 .55rem}
.ov-sub-head h3{margin:0;font-size:var(--text-sub);font-weight:600;color:var(--text-primary)}
.ov-p1-bar{display:inline-flex;align-items:center;gap:.65rem;flex-wrap:wrap}
.ov-bar-sep{display:inline-block;width:1px;height:12px;background:var(--border-default)}
.ov-jump{font-size:var(--text-sm);font-weight:500;color:var(--accent);white-space:nowrap}
.ov-jump:hover{text-decoration:underline}
.ov-stepper{display:flex;align-items:center;gap:0;padding:.45rem .5rem;margin:0 0 .65rem;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-subtle)}
.ov-step{position:relative;flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:.16rem;padding:.44rem .62rem;border:1px solid var(--border-subtle);border-radius:7px;background:var(--surface-panel);color:var(--text-secondary);font-family:var(--font-sans);text-align:left;cursor:pointer;transition:background .15s ease,border-color .15s ease,box-shadow .15s ease,color .15s ease}
.ov-step:hover:not(:disabled):not(.is-active){border-color:var(--border-default);background:var(--surface-hover);color:var(--text-primary)}
.ov-step.is-done{border-color:var(--border-subtle);background:var(--surface-panel)}
.ov-step.is-active{border-color:var(--brand);background:var(--brand-soft);color:var(--brand);box-shadow:0 2px 6px -1px rgba(29,53,87,.12)}
.ov-step.is-active.is-final{border-color:var(--gen-closed);background:var(--tone-ok-bg);color:var(--tone-ok-ink);box-shadow:0 2px 6px -1px rgba(43,122,87,.14)}
.ov-step:disabled{opacity:.55;cursor:default}
.ov-step-top{display:flex;align-items:center;gap:.36rem;min-width:0}
.ov-step-tag{display:inline-flex;align-items:center;padding:.04rem .36rem;border-radius:4px;background:var(--surface-muted);font-family:var(--font-mono);font-size:var(--text-xs);font-weight:650;line-height:1.25;color:var(--text-secondary);flex-shrink:0;transition:background .15s ease,color .15s ease}
.ov-step.is-done .ov-step-tag{background:var(--brand-soft);color:var(--brand)}
.ov-step.is-active .ov-step-tag{background:var(--brand);color:#fff}
.ov-step.is-active.is-final .ov-step-tag{background:var(--gen-closed);color:#fff}
.ov-step-name{font-size:var(--text-sm);font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-step.is-active .ov-step-name{font-weight:700;color:var(--brand)}
.ov-step.is-active.is-final .ov-step-name{color:var(--tone-ok-ink)}
.ov-step-sub{font-size:var(--text-xs);color:var(--text-muted);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-step.is-active .ov-step-sub{color:var(--text-secondary);font-weight:500}
.ov-step-conn{flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;width:28px;color:var(--border-strong);user-select:none}
.ov-step-conn svg{display:block;overflow:visible}
.ov-conn-base{stroke:var(--border-default);stroke-width:1.4;stroke-linecap:round;opacity:.55}
.ov-conn-flow{stroke:var(--border-strong);stroke-width:1.6;stroke-linecap:round;stroke-dasharray:4 5;opacity:.55;animation:ov-flow 1.35s linear infinite}
.ov-conn-head{stroke:var(--border-strong);stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;opacity:.7;transition:stroke .16s ease,opacity .16s ease}
.ov-step-conn.is-passed .ov-conn-base{stroke:var(--brand);opacity:.22}
.ov-step-conn.is-passed .ov-conn-flow{stroke:var(--brand);stroke-width:1.8;opacity:.92;animation-duration:.9s}
.ov-step-conn.is-passed .ov-conn-head{stroke:var(--brand);opacity:1}
.ov-step-conn.is-passed.is-final-flow .ov-conn-base{stroke:var(--gen-closed)}
.ov-step-conn.is-passed.is-final-flow .ov-conn-flow,.ov-step-conn.is-passed.is-final-flow .ov-conn-head{stroke:var(--gen-closed)}
@keyframes ov-flow{from{stroke-dashoffset:18}to{stroke-dashoffset:0}}
@media (prefers-reduced-motion:reduce){.ov-conn-flow{animation:none}}
.ov-tel-swatch{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--brand);border:1.5px solid var(--surface-panel);box-shadow:0 0 0 1px var(--brand)}
.ov-track-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.ov-axis,.ov-chr-row>summary,.ov-stage-row{display:grid;grid-template-columns:168px minmax(0,1fr);align-items:center;gap:.75rem}
.ov-axis{padding:.42rem .85rem .36rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:var(--text-xs);font-weight:600}
.ov-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:var(--text-xs)}
.ov-chr-row{border-bottom:1px solid var(--border-subtle)}
.ov-chr-row:last-child{border-bottom:0}
.ov-chr-row>summary{cursor:pointer;list-style:none;padding:.34rem .85rem;min-height:2.05rem;transition:background .1s}
.ov-chr-row>summary::-webkit-details-marker{display:none}
.ov-chr-row>summary:hover,.ov-chr-row[open]>summary{background:var(--surface-subtle)}
.ov-chr-meta{display:flex;align-items:baseline;justify-content:space-between;gap:.32rem;min-width:0}
.ov-chr-name{display:inline-flex;align-items:center;gap:.32rem;font-family:var(--font-mono);font-size:var(--text-sm);font-weight:600;line-height:1.25;color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ov-chr-name::before{content:'▸';font-size:10px;color:var(--text-muted);flex-shrink:0}
.ov-chr-row[open]>summary .ov-chr-name::before{content:'▾'}
.ov-chr-stats{display:inline-flex;align-items:baseline;gap:.3rem;flex-shrink:0;font-variant-numeric:tabular-nums}
.ov-chr-len{font-size:var(--text-xs);color:var(--text-muted)}
.ov-chr-gap{font-family:var(--font-mono);font-size:var(--text-xs);font-weight:600;line-height:1.2;padding:.02rem .28rem;border-radius:3px;background:var(--surface-muted);color:var(--text-secondary)}
.ov-chr-gap.is-zero{background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.ov-chr-detail{padding:.38rem .85rem .5rem;border-top:1px dashed var(--border-subtle);background:var(--surface-subtle)}
.ov-chr-summary{display:flex;flex-wrap:wrap;align-items:center;gap:.32rem .75rem;margin:0 0 .35rem;padding-left:.85rem;font-size:var(--text-xs);color:var(--text-secondary);font-variant-numeric:tabular-nums}
.ov-chr-summary b{color:var(--text-primary);font-weight:600}
.ov-chr-summary .is-ok{color:var(--gen-closed);font-weight:600}
.ov-stage-row{min-height:1.48rem;padding:.08rem 0;border-radius:3px}
.ov-stage-row.is-current{background:var(--brand-soft)}
.ov-stage-row.is-current.is-final{background:var(--tone-ok-bg)}
.ov-stage-lbl{display:flex;align-items:center;justify-content:space-between;gap:.32rem;padding-left:.85rem;padding-right:.15rem;min-width:0;font-size:var(--text-xs);color:var(--text-secondary)}
.ov-stage-lbl-l{display:inline-flex;align-items:center;gap:.3rem;min-width:0;overflow:hidden}
.ov-stage-lbl-tag{display:inline-flex;align-items:center;padding:.02rem .26rem;border-radius:3px;background:var(--surface-panel);border:1px solid var(--border-subtle);font-family:var(--font-mono);font-size:10px;font-weight:650;line-height:1.25;color:var(--text-secondary);flex-shrink:0}
.ov-stage-row.is-current .ov-stage-lbl-tag{background:var(--brand);border-color:var(--brand);color:#fff}
.ov-stage-row.is-current.is-final .ov-stage-lbl-tag{background:var(--gen-closed);border-color:var(--gen-closed);color:#fff}
.ov-stage-lbl-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ov-rail{position:relative;display:block;height:18px;min-width:0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.ov-seg{position:absolute;top:3px;height:12px;border-radius:2px}
.ov-seg.is-src{min-width:4px;box-shadow:inset 0 0 0 .6px rgba(255,255,255,.35)}
.ov-seg.is-patch{min-width:5px;background:var(--gen-closed);box-shadow:inset 0 0 0 .8px rgba(255,255,255,.5),0 0 0 .7px var(--gen-closed);z-index:3}
.ov-seg.is-gap{min-width:5px;background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px);box-shadow:inset 0 0 0 1px var(--border-strong);z-index:2}
.ov-cen{position:absolute;bottom:0;height:2.5px;border-radius:1px;background:var(--gen-cen);opacity:.72;z-index:4}
.ov-tel{position:absolute;top:50%;width:7px;height:7px;border-radius:50%;transform:translate(-50%,-50%);z-index:5}
.ov-tel.is-ok{background:var(--brand);border:1.5px solid var(--surface-panel)}
.ov-tel.is-ext{background:var(--gen-closed);border:1.5px solid var(--surface-panel)}
.ov-tel.is-miss{background:var(--surface-panel);border:1.5px solid var(--border-strong)}
.ov-more-chrs>summary{padding:.42rem .85rem;font-size:var(--text-sm);font-weight:500;color:var(--accent);background:var(--surface-subtle);cursor:pointer;border-top:1px dashed var(--border-subtle);list-style:none}
.ov-more-chrs>summary::-webkit-details-marker{display:none}
.ov-more-chrs>summary:hover{background:var(--surface-hover)}
.story-zoom-stage .ov-track-frame{border:0;border-radius:0;padding-bottom:0;overflow:visible;min-width:100%;width:calc(100% * var(--chart-scale, 1))}
.story-zoom-stage .ov-axis,.story-zoom-stage .ov-chr-row>summary,.story-zoom-stage .ov-stage-row{grid-template-columns:196px minmax(0,1fr);gap:0;padding:0;align-items:stretch}
.story-zoom-stage .ov-axis{position:sticky;top:0;z-index:8;background:var(--surface-subtle)}
.story-zoom-stage .ov-axis>:first-child{position:sticky;left:0;z-index:9;background:var(--surface-subtle);padding:.52rem .7rem .42rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;align-items:center}
.story-zoom-stage .ov-axis .story-ruler{margin:.52rem 1rem .42rem .8rem;min-width:0}
.story-zoom-stage .ov-chr-meta{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding:.55rem .7rem .55rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);align-items:center}
.story-zoom-stage .ov-chr-row>summary:hover .ov-chr-meta,.story-zoom-stage .ov-chr-row[open]>summary .ov-chr-meta{background:var(--surface-subtle)}
.story-zoom-stage .ov-chr-detail{padding:0}
.story-zoom-stage .ov-chr-summary{position:sticky;left:0;width:fit-content;max-width:100%;margin:0;padding:.38rem 1rem .32rem 1.4rem;background:var(--surface-subtle)}
.story-zoom-stage .ov-stage-lbl{position:sticky;left:0;z-index:5;background:var(--surface-subtle);padding:.26rem .7rem .26rem 1.4rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12)}
.story-zoom-stage .ov-stage-row.is-current .ov-stage-lbl{background:var(--brand-soft)}
.story-zoom-stage .ov-stage-row.is-current.is-final .ov-stage-lbl{background:var(--tone-ok-bg)}
.story-zoom-stage .ov-rail{margin:.42rem 1rem .42rem .8rem;height:22px;z-index:1}
.story-zoom-stage .ov-chr-detail .ov-rail{margin:.2rem 1rem .2rem .8rem}
.story-zoom-stage .ov-seg{top:3px;height:16px}
.story-zoom-stage .ov-seg.is-src,.story-zoom-stage .ov-seg.is-gap,.story-zoom-stage .ov-seg.is-patch{min-width:6px}
.ov-charts-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.8rem}
.ov-chart-card{display:flex;flex-direction:column;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-subtle);padding:.68rem .85rem .58rem;min-width:0}
.ov-chart-head{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem;margin:0 0 .32rem}
.ov-chart-head h4{margin:0;font-size:var(--text-sub);font-weight:600;color:var(--text-primary)}
.ov-chart-meta{font-family:var(--font-mono);font-size:var(--text-xs);font-weight:500;line-height:1.2;color:var(--text-muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.ov-chart-meta.is-ok{color:var(--gen-closed);font-weight:600}
.ov-svg{display:block;width:100%;height:auto;flex:1 1 auto;background:var(--surface-panel);border:1px solid var(--border-subtle);border-radius:var(--radius-sm);padding:.18rem}
.ov-ax-txt{font-family:var(--font-mono);font-size:var(--svg-micro);font-weight:500;fill:var(--text-muted)}
.ov-ax-lbl{font-family:var(--font-mono);font-size:var(--svg-label);font-weight:600;fill:var(--text-secondary)}
.ov-ax-lbl.is-win{fill:var(--gen-closed)}
.ov-val-txt{font-family:var(--font-mono);font-size:var(--svg-label);font-weight:600;fill:var(--text-primary)}
.ov-bar-bp{font-family:var(--font-mono);font-size:var(--svg-micro);font-weight:500;fill:var(--text-muted)}
.ov-lbl-win{font-family:var(--font-mono);font-size:var(--svg-label);font-weight:650;fill:var(--gen-closed)}
.ov-lbl-sub{font-family:var(--font-mono);font-size:var(--svg-micro);font-weight:500;fill:var(--text-muted)}
.ov-donut-big{font-family:var(--font-mono);font-size:var(--svg-kpi);font-weight:700;fill:var(--text-primary)}
.ov-donut-sub{font-family:var(--font-mono);font-size:var(--svg-micro);font-weight:500;fill:var(--text-muted)}
.ov-donut-title{font-family:var(--font-sans);font-size:var(--svg-label);font-weight:600;fill:var(--text-primary)}
.ov-donut-cap{font-family:var(--font-sans);font-size:var(--svg-micro);font-weight:500;fill:var(--text-muted)}
.ov-leg-txt{font-family:var(--font-sans);font-size:var(--svg-micro);font-weight:500;fill:var(--text-secondary)}
.ov-bar-lbl{font-family:var(--font-mono);font-size:var(--svg-label);font-weight:600;fill:var(--text-secondary)}
.ov-bar-lbl.is-win{fill:var(--gen-closed)}
.ov-bar-val{font-family:var(--font-mono);font-size:var(--svg-micro);font-weight:600;fill:var(--text-secondary)}
.ov-bar-val.is-win{fill:var(--gen-closed)}
.ov-runtime-bar{width:100%;display:flex;align-items:center;gap:.55rem .85rem;flex-wrap:wrap;margin-top:.75rem;padding:.48rem .78rem;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-subtle);font-family:var(--font-sans);font-size:var(--text-xs);color:var(--text-secondary);font-variant-numeric:tabular-nums;text-align:left;cursor:pointer;transition:border-color .12s,background .12s,box-shadow .12s}
.ov-runtime-bar:hover{border-color:var(--brand);background:var(--surface-panel);box-shadow:0 1px 3px rgba(15,23,42,.06)}
.ov-rt-head{white-space:nowrap;color:var(--text-muted)}
.ov-rt-head b{color:var(--text-primary);font-family:var(--font-mono);font-weight:600}
.ov-rt-mem{white-space:nowrap;color:var(--text-muted)}
.ov-rt-mem b{color:var(--gen-closed);font-family:var(--font-mono);font-weight:600}
.ov-rt-track{flex:1 1 150px;min-width:110px;display:flex;height:7px;border-radius:999px;overflow:hidden;background:var(--surface-muted);gap:1px}
.ov-rt-seg{display:block;height:100%}
.ov-rt-legend{display:inline-flex;align-items:center;gap:.35rem .65rem;flex-wrap:wrap}
.ov-rt-item{display:inline-flex;align-items:center;gap:.26rem;white-space:nowrap}
.ov-rt-item b{font-family:var(--font-mono);font-weight:600;color:var(--text-primary)}
.ov-rt-dot{display:inline-block;width:7px;height:7px;border-radius:2px;flex-shrink:0}
.ov-rt-more{margin-left:auto;color:var(--accent);font-weight:600;white-space:nowrap}
.ov-rt-strip{margin:0 0 .75rem;padding:.45rem .65rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
.ov-rt-strip b.is-ok{color:var(--gen-closed)}
.ov-rt-table th,.ov-rt-table td{padding:7px 10px;font-size:var(--text-sm)}
.ov-rt-table thead th{font-size:var(--text-xs)}
@media (max-width:860px){
  .ov-charts-grid{grid-template-columns:1fr}
  .ov-stepper{flex-wrap:wrap;gap:.35rem}
  .ov-step{flex:1 1 118px}
  .ov-step-conn{display:none}
}
@media (max-width:760px){
  .ov-axis,.ov-chr-row>summary,.ov-stage-row{grid-template-columns:116px minmax(0,1fr);gap:.45rem;padding-left:.65rem;padding-right:.65rem}
  .ov-chr-detail{padding:.32rem .65rem .42rem}
  .ov-chr-summary,.ov-stage-lbl{padding-left:.35rem}
  .ov-chr-name{font-size:var(--text-xs)}
  .ov-bar-sep{display:none}
  .story-zoom-stage .ov-axis,.story-zoom-stage .ov-chr-row>summary,.story-zoom-stage .ov-stage-row{grid-template-columns:136px minmax(0,1fr);gap:0;padding:0}
}
</style>"""

SCRIPT = """<script data-cgat-ui="1">(()=>{
const card=document.getElementById('assembly-overview'),raw=document.getElementById('ov-stage-data');
if(!card||!raw)return;
let data;try{data=JSON.parse(raw.textContent||'{}');}catch(_){return;}
const btns=Array.from(card.querySelectorAll('[data-ov-stage]'));
const conns=Array.from(card.querySelectorAll('[data-ov-conn]'));
const jump=card.querySelector('[data-ov-jump]'),jumpLbl=card.querySelector('[data-ov-jump-lbl]');
const domain=Math.max(1,Number(data.domain)||1);
let activeKey=data.active||'';
function mk(cls,left,width,bg,title){
  const el=document.createElement('span');
  el.className=cls;
  el.style.left=left.toFixed(4)+'%';
  if(width!=null)el.style.width=width.toFixed(4)+'%';
  if(bg)el.style.background=bg;
  if(title)el.title=title;
  return el;
}
function biEl(zh,en){
  const f=document.createDocumentFragment();
  const s1=document.createElement('span');s1.className='t-zh';s1.textContent=zh;
  const s2=document.createElement('span');s2.className='t-en';s2.textContent=en;
  f.append(s1,s2);return f;
}
function fillRail(rail,cname,info,showTel){
  const frag=document.createDocumentFragment();
  const segs=(info&&info.s)||[];
  for(const seg of segs){
    const a=seg[0],b=seg[1],c=seg[2],l=100*a/domain,w=100*(b-a)/domain;
    if(c===9)frag.appendChild(mk('ov-seg is-gap',l,w));
    else if(c===8)frag.appendChild(mk('ov-seg is-patch',l,w));
    else frag.appendChild(mk('ov-seg is-src',l,w,'var(--ds-'+c+')'));
  }
  if(showTel){
    const cens=(data.cen||{})[cname]||[];
    for(const m of cens){frag.appendChild(mk('ov-cen',100*m[0]/domain,Math.max(0.35,100*(m[1]-m[0])/domain),null,'Candidate centromere'));}
    const tp=(data.tel||{})[cname];
    if(tp){
      const endPct=segs.length?100*segs[segs.length-1][1]/domain:0;
      const defs=[['5′',tp[0],0],['3′',tp[1],endPct]];
      for(const d of defs){
        const cls=d[1]===2?'ov-tel is-ext':(d[1]===1?'ov-tel is-ok':'ov-tel is-miss');
        frag.appendChild(mk(cls,d[2],null,null,d[0]+' telomere'));
      }
    }
  }
  rail.replaceChildren(frag);
}
function renderDetail(detailsEl){
  const box=detailsEl.querySelector('[data-ov-detail]');
  if(!box)return;
  const cname=detailsEl.dataset.ovChr,order=data.order||[],stages=data.stages||{};
  const frag=document.createDocumentFragment();
  const firstSt=order.length?stages[order[0]]:null,lastSt=order.length?stages[order[order.length-1]]:null;
  const firstInfo=firstSt&&firstSt.rows?firstSt.rows[cname]:null;
  const lastInfo=lastSt&&lastSt.rows?lastSt.rows[cname]:null;
  const sum=document.createElement('div');sum.className='ov-chr-summary';
  if(lastInfo){
    const sLen=document.createElement('span');sLen.append(biEl('终长 ','Length '));
    const bLen=document.createElement('b');bLen.textContent=lastInfo.l;sLen.append(bLen);sum.append(sLen);
  }
  if(firstInfo&&lastInfo){
    const g0=firstInfo.g,gf=lastInfo.g,diff=gf-g0;
    const sGap=document.createElement('span');sGap.textContent='Gap ';
    const bGap=document.createElement('b');
    bGap.textContent=g0===gf?String(gf):(g0+' → '+gf+(diff<0?' ('+diff+')':''));
    if(diff<0||gf===0)bGap.className='is-ok';
    sGap.append(bGap);sum.append(sGap);
  }
  const tp=(data.tel||{})[cname];
  if(tp){
    const sTel=document.createElement('span');sTel.append(biEl('端粒 ','Tel '));
    const fmtEnd=(code,side)=>side+(code===2?' +✓':(code===1?' ✓':' ○'));
    const bTel=document.createElement('b');bTel.textContent=fmtEnd(tp[0],'5′')+' / '+fmtEnd(tp[1],'3′');
    if(tp[0]>0&&tp[1]>0)bTel.className='is-ok';
    sTel.append(bTel);sum.append(sTel);
  }
  const cens=(data.cen||{})[cname];
  if(cens&&cens.length){
    const sCen=document.createElement('span');sCen.append(biEl('着丝粒候选 '+cens.length+' 处','Centromere '+cens.length));sum.append(sCen);
  }
  frag.append(sum);
  for(const k of order){
    const st=stages[k],info=st&&st.rows?st.rows[cname]:null;
    if(!info)continue;
    const row=document.createElement('div');
    row.className='ov-stage-row'+(k===activeKey?' is-current':'')+(st.is_final?' is-final':'');
    row.dataset.ovStageRow=k;
    const lbl=document.createElement('div');lbl.className='ov-stage-lbl';
    const left=document.createElement('span');left.className='ov-stage-lbl-l';
    const tag=document.createElement('span');tag.className='ov-stage-lbl-tag';tag.textContent=st.tag||k;
    const nm=document.createElement('span');nm.className='ov-stage-lbl-name';nm.append(biEl(st.zh||k,st.en||k));
    left.append(tag,nm);
    const gap=document.createElement('small');gap.className='ov-chr-gap'+(info.g===0?' is-zero':'');gap.textContent=String(info.g)+'G';
    lbl.append(left,gap);
    const rail=document.createElement('div');rail.className='ov-rail';
    fillRail(rail,cname,info,!!st.show_tel);
    row.append(lbl,rail);
    frag.append(row);
  }
  box.replaceChildren(frag);
  detailsEl.dataset.ovRendered='1';
}
function applyStage(key){
  const st=(data.stages||{})[key];
  if(!st)return;
  activeKey=key;
  let activeIdx=-1;
  for(const b of btns){
    const idx=Number(b.dataset.ovIdx);
    if(b.dataset.ovStage===key)activeIdx=idx;
  }
  const isFinalFlow=!!st.is_final;
  for(const b of btns){
    const idx=Number(b.dataset.ovIdx);
    const on=idx===activeIdx;
    b.classList.toggle('is-active',on);
    b.classList.toggle('is-done',activeIdx>=0&&idx<activeIdx);
    b.setAttribute('aria-pressed',on?'true':'false');
  }
  for(const c of conns){
    const idx=Number(c.dataset.ovConn);
    const passed=activeIdx>=0&&idx<activeIdx;
    c.classList.toggle('is-passed',passed);
    c.classList.toggle('is-final-flow',passed&&isFinalFlow);
  }
  if(jump&&st.href)jump.setAttribute('href',st.href);
  if(jumpLbl){
    const zh=jumpLbl.querySelector('.t-zh'),en=jumpLbl.querySelector('.t-en');
    if(zh)zh.textContent=st.jump_zh||'';
    if(en)en.textContent=st.jump_en||'';
  }
  for(const row of card.querySelectorAll('[data-ov-chr]')){
    const cname=row.dataset.ovChr,info=(st.rows||{})[cname];
    if(!info)continue;
    const lenEl=row.querySelector('[data-ov-len]'),gapEl=row.querySelector('[data-ov-gap]'),rail=row.querySelector('[data-ov-rail]');
    if(lenEl)lenEl.textContent=info.l||'';
    if(gapEl){gapEl.textContent=String(info.g)+'G';gapEl.classList.toggle('is-zero',info.g===0);}
    if(rail)fillRail(rail,cname,info,!!st.show_tel);
    for(const sr of row.querySelectorAll('[data-ov-stage-row]')){
      sr.classList.toggle('is-current',sr.dataset.ovStageRow===key);
    }
  }
}
for(const b of btns){b.addEventListener('click',()=>applyStage(b.dataset.ovStage));}
document.addEventListener('toggle',e=>{
  const d=e.target;
  if(d&&d.matches&&d.matches('details.ov-chr-row[data-ov-chr]')&&d.open&&!d.dataset.ovRendered)renderDetail(d);
},true);
})();</script>"""
