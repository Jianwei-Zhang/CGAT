"""Offline bidirectional gap report. Coordinates below are zero-based, half-open."""

from collections import defaultdict
import re
from urllib.parse import quote

from FamilyReportStyle import CSS, SCRIPT
from JunctionReport import render_junction_report
from ReportStyle import badge_bi, bi, degap_logo_html, esc, report_css

LEFT, RIGHT, ORIGINAL, BRIDGE = "#2563eb", "#d97706", "#cbd5e1", "#2b7a57"

_REASON_ZH = {
    "closed": "已闭合",
    "exhausted": "延伸耗尽",
    "round_limit": "达到轮次上限",
    "length_limit": "达到长度上限",
    "terminal": "末端终止",
    "no_extension_contigs": "无可用延伸序列",
    "no_extension_reads": "无可用延伸读长",
    "terminal_anchor_backoff": "末端锚点回退",
    "anchor_backoff_no_net_growth": "锚点回退后无净增长",
    "overlap_below_minimum": "重叠长度不足",
    "no_alignment": "无比对",
    "identity_below_minimum": "一致性不足",
    "overhang_above_maximum": "悬垂超限",
    "Winner": "胜出",
    "Eligible": "合格",
    "No alignment": "无比对",
    "No diagnostic recorded": "未记录诊断",
    "Rejected": "未通过",
    "preserved": "保持原序列",
    "repaired": "已修订",
    "conflict": "冲突保留",
    "fast": "快速筛选",
    "full": "全长比对",
}


def zh_term(code):
    if not code:
        return "—"
    return _REASON_ZH.get(str(code), str(code))


def format_display_title(name):
    """Turn 'OZ408684.1.1.bidirectional' into ('OZ408684.1 · Gap 1', 'OZ408684.1.1.bidirectional')."""
    m = re.fullmatch(r"(.+)\.(\d+)\.bidirectional", name)
    if m:
        return f"{m.group(1)} · Gap {m.group(2)}", name
    return name, ""


def bp(n):
    return "—" if n is None else f"{n:,} bp"


def rect(x, y, width, height, fill, title="", cls="", rx=0):
    cls_attr = f' class="{cls}"' if cls else ""
    rx_attr = f' rx="{rx}"' if rx else ""
    return (
        f'<rect x="{x:.3f}" y="{y}" width="{max(0, width):.3f}" height="{height}" fill="{fill}"{rx_attr}{cls_attr}>'
        f"<title>{esc(title)}</title></rect>"
    )


def text(x, y, label, anchor="start", cls=""):
    return f'<text x="{x:.3f}" y="{y}" text-anchor="{anchor}" class="{cls}">{esc(label)}</text>'


def svg(label, height, parts):
    return (
        f'<div class="canvas"><svg class="graphic" viewBox="0 0 800 {height}" role="img" '
        f'aria-label="{esc(label)}"><title>{esc(label)}</title>{"".join(parts)}</svg></div>'
    )


def ribbon(a, b, c, d, y1, y2):
    ym = (y1 + y2) / 2
    return (
        f'<path class="overlap-bridge" fill="{BRIDGE}" fill-opacity=".24" stroke="{BRIDGE}" stroke-width="1.2" '
        f'd="M{a:.3f},{y1} H{b:.3f} C{b:.3f},{ym} {d:.3f},{ym} {d:.3f},{y2} H{c:.3f} '
        f'C{c:.3f},{ym} {a:.3f},{ym} {a:.3f},{y1} Z"><title>Winning overlap / 闭合重叠</title></path>'
    )


def attempts(family, backoffs):
    """Backoff charges a round without adding a version. Terminal stops may do so too."""
    versions = family["versions"]
    current = 0
    records = []
    for attempt in range(1, family["attempts"] + 1):
        delta = 0
        if attempt in backoffs:
            reason = "terminal_anchor_backoff"
        else:
            if current + 1 < len(versions):
                delta = versions[current + 1]["length"] - versions[current]["length"]
                current += 1
            reason = family.get("stop_reason") if attempt == family["attempts"] else None
        records.append(
            dict(
                attempt=attempt,
                version=current,
                delta=delta,
                length=versions[current]["length"],
                reason=reason,
            )
        )
    return records


def timeline(rounds):
    # L is the primary in FamilyGap.run_gap; stopped sides are skipped by the scheduler.
    return [
        (side, records[i])
        for i in range(max(map(len, rounds.values()), default=0))
        for side, records in rounds.items()
        if i < len(records)
    ]


def pair(record):
    return record["left_version"], record["right_version"]


def cell_info(key, winner, diagnostic, eligible):
    if winner and key == pair(winner):
        return "win", "★", "Winner"
    if key in eligible or (diagnostic or {}).get("status") == "eligible":
        return "pass", "✓", "Eligible"
    if not diagnostic:
        return "unknown", "·", "No diagnostic recorded"
    if diagnostic.get("reason") == "no_alignment":
        return "none", "–", "No alignment"
    return "reject", "×", diagnostic.get("reason") or "Rejected"


def checks_by_step(events, diagnostics, eligible, winner):
    introduced = {"L": {0: 0}, "R": {0: 0}}
    for i, (side, event) in enumerate(events, 1):
        introduced[side].setdefault(event["version"], i)
    checks_en = defaultdict(list)
    checks_zh = defaultdict(list)
    for key in sorted(set(diagnostics) | eligible):
        left, right = key
        n = max(introduced["L"][left], introduced["R"][right])
        label = cell_info(key, winner, diagnostics.get(key), eligible)[2]
        checks_en[n].append(f"L/v{left} × R/v{right}: {label}")
        checks_zh[n].append(f"L/v{left} × R/v{right}：{zh_term(label)}")
    return checks_en, checks_zh


def coords(w):
    return w and all(
        isinstance(w.get(key), int) for key in ("left_start", "left_end", "right_start", "right_end")
    )


def scene(families, events, w):
    base = {s: f["versions"][0]["length"] for s, f in families.items()}
    gains = {s: f["versions"][-1]["length"] - base[s] for s, f in families.items()}
    if coords(w):
        # Place the right original boundary using the *winning version*, not the latest peer.
        r_growth = families["R"]["versions"][w["right_version"]]["length"] - base["R"]
        boundary = w["left_start"] - base["L"] - w["right_start"] + r_growth
        ends = (
            w["left_start"] - base["L"],
            w["left_end"] - base["L"],
            boundary - r_growth + w["right_start"],
            boundary - r_growth + w["right_end"],
        )
    else:
        boundary = sum(gains.values()) + max(1, sum(gains.values()) * 0.22)
        ends = ()
    low = min(0, boundary - gains["R"], *ends)
    high = max(gains["L"], boundary, *ends)
    margin = max(1, (high - low) * 0.10)
    low, high = low - margin, high + margin

    def x(n):
        return 62 + 706 * (n - low) / (high - low)

    def block(start, end, y, color, title, cls="", rx=3):
        a, b = x(max(low, start)), x(min(high, end))
        return rect(a, y, b - a, 20, color, title, cls=cls, rx=rx)

    parts = [
        '<path class="svg-guide" d="M62,38 H768 M62,103 H768" stroke="#e2e8f0" stroke-dasharray="3 3"/>',
        text(10, 43, "L →", cls="label"),
        text(10, 108, "R ←", cls="label"),
        block(-base["L"], 0, 28, ORIGINAL, "Left original flank / 左侧原始侧翼", cls="seg-orig"),
        block(boundary, boundary + base["R"], 93, ORIGINAL, "Right original flank / 右侧原始侧翼", cls="seg-orig"),
    ]
    for i, (side, event) in enumerate(events, 1):
        if not event["delta"]:
            continue
        delta = event["delta"]
        gain = event["length"] - base[side]
        a, b, y = (gain - delta, gain, 28) if side == "L" else (boundary - gain, boundary - gain + delta, 93)
        label = f"{side}/v{event['version']} · +{bp(delta)}"
        item = block(a, b, y, LEFT if side == "L" else RIGHT, label, cls="seg-bar", rx=2)
        item += f'<path class="seg-sep" d="M{x(a):.3f},{y} v20" stroke="#ffffff" stroke-width="1.2"/>'
        if x(b) - x(a) > 76:
            item += text((x(a) + x(b)) / 2, y + 14, "+" + bp(delta), "middle", "delta")
        parts.append(f'<g data-from="{i}">{item}</g>')
    if ends:
        layer = ribbon(*map(x, ends), 48, 93)
    elif not w:
        a, b = x(gains["L"]), x(boundary - gains["R"])
        layer = (
            '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse">'
            '<path d="M0,6 L6,0" stroke="#d97706" stroke-opacity="0.55"/></pattern></defs>'
            + rect(a, 49, b - a, 43, "url(#hatch)", "Unclosed interval; width unknown / 未闭合区间（宽度未知）")
            + text((a + b) / 2, 16, "Unclosed · span unknown", "middle", "tick")
        )
    else:
        layer = ""
    parts.append(f'<g data-from="{len(events)}">{layer}</g>')
    return svg("Inward extension · zoomed terminal regions", 132, parts)


def player(families, events, checks_en, checks_zh, w, status):
    pills, captions = [], []
    versions = {"L": 0, "R": 0}
    for i, entry in enumerate([None, *events]):
        if entry:
            s, e = entry
            versions[s] = e["version"]
            label_en = f"{s}→v{e['version']}" if e["delta"] else f"{s} · #{e['attempt']}"
            label_zh = label_en
            cap_en = f"Round {i} · {s}/v{e['version']} · +{bp(e['delta'])} → {bp(e['length'])}" + (
                " · " + e["reason"] if e["reason"] else ""
            )
            cap_zh = f"第 {i} 轮 · {s} 侧 v{e['version']}（+{bp(e['delta'])} → {bp(e['length'])}）" + (
                " · " + zh_term(e["reason"]) if e["reason"] else ""
            )
        else:
            label_en = "Init v0"
            label_zh = "初始 v0"
            cap_en = "Initial · L/v0 × R/v0"
            cap_zh = "初始状态 · L/v0 × R/v0"
        last = i == len(events)
        if last:
            label_en += " · Closed" if w else " · Unclosed"
            label_zh += " · 闭合" if w else " · 未闭合"
            cap_en += " · " + status
            cap_zh += " · " + zh_term(status)
        pill_label = bi(label_en, label_zh) if label_en != label_zh else esc(label_en)
        pills.append(
            f'<button type="button" data-step="{i}" aria-current="{"step" if last else "false"}">{pill_label}</button>'
        )
        detail_en = "; ".join(checks_en[i]) or (
            "No new pair · versions unchanged"
            if entry and not entry[1]["delta"]
            else "No pair-level diagnostic recorded"
        )
        detail_zh = "；".join(checks_zh[i]) or (
            "本轮无新增版本，未重复配对"
            if entry and not entry[1]["delta"]
            else "未记录配对诊断"
        )
        tracks = "".join(
            f'<span class="track-{s}">{s}/v{v} · {bp(families[s]["versions"][v]["length"])}</span>'
            for s, v in versions.items()
        )
        captions.append(
            f'<div data-caption="{i}"{"" if last else " hidden"}><div class="track-key">{tracks}</div>'
            f"<strong>{bi(cap_en, cap_zh)}</strong><span>{bi(detail_en, detail_zh)}</span></div>"
        )
    disabled = "" if events else " disabled"
    legend = (
        bi("Green bridge: winning overlap.", "绿带：闭合重叠。")
        if coords(w)
        else bi("Hatching: unclosed interval (span unknown).", "斜纹：未闭合区（不代表实际长度）。")
        if not w
        else bi("Winning interval coordinates not recorded.", "未记录胜出区间坐标。")
    )
    unclosed_html = ""
    if not w:
        stop_en = " · ".join(f"{s}: {f['stop_reason']}" for s, f in families.items() if f.get("stop_reason")) or status
        stop_zh = " · ".join(f"{s} 侧：{zh_term(f['stop_reason'])}" for s, f in families.items() if f.get("stop_reason")) or zh_term(status)
        unclosed_html = (
            '<div class="unclosed-banner">'
            f'<b>{bi("No eligible connection.", "未找到合格连接，两侧序列保持分离。")}</b>'
            f'<span>{bi(stop_en, stop_zh)}</span>'
            '</div>'
        )
    return (
        f'<div data-player><div class="player-bar"><div class="controls">'
        f'<button type="button" class="play" aria-pressed="false"{disabled}>▶ Play</button>'
        f'<button type="button" class="prev"{disabled}>{bi("← Prev", "← 上一步")}</button>'
        f'<button type="button" class="next" disabled>{bi("Next →", "下一步 →")}</button></div>'
        f'<div class="pills">{"".join(pills)}</div></div>'
        f'<div class="scene">{scene(families, events, w)}</div>'
        f'<div class="caption" aria-live="polite">{"".join(captions)}</div>'
        f'{unclosed_html}'
        f'<p class="note">{bi("Terminal zoom · Gray: original flanks · Blue: L · Amber: R. ", "末端放大 · 灰：原始侧翼 · 蓝：L 侧 · 橙：R 侧。")}{legend}</p></div>'
    )


def alignment(families, w):
    if not w:
        return ""
    stage = (w.get("evidence") or {}).get("stage") or "not recorded"
    stage_zh = zh_term(stage)
    # Header already shows Overlap & Identity; keep non-duplicate alignment metrics here.
    summary = (
        f'<p class="callout">'
        f'<span><span class="t-zh">悬垂 <b>{esc(bp(w["overhang"]))}</b></span><span class="t-en"><b>{esc(bp(w["overhang"]))}</b> overhang</span></span>'
        f'<span><span class="t-zh">检测阶段 <b>{esc(stage_zh)}</b></span><span class="t-en">Stage: {esc(stage)}</span></span>'
        f'</p>'
    )
    if not coords(w):
        return summary + f'<p class="note">{bi("Matched coordinates were not recorded.", "未记录比对区间坐标。")}</p>'
    lengths = {
        s: families[s]["versions"][w[k]]["length"] for s, k in (("L", "left_version"), ("R", "right_version"))
    }
    scale = 696 / max(lengths.values())
    origin = 84

    def x(n):
        return origin + n * scale

    ls, le, rs, re_ = (w[k] for k in ("left_start", "left_end", "right_start", "right_end"))
    parts = [ribbon(x(ls), x(le), x(rs), x(re_), 39, 83)]
    for s, y, start, end in [("L", 23, ls, le), ("R", 83, rs, re_)]:
        n = lengths[s]
        orig = families[s]["versions"][0]["length"]
        ext = n - orig
        parts += [
            text(10, y + 12, f"{s}/v{w['left_version' if s == 'L' else 'right_version']}", cls="label"),
            rect(origin, y, n * scale, 16, ORIGINAL, "Original flank / 原始侧翼", cls="seg-orig", rx=3),
            rect(
                x(orig if s == "L" else 0),
                y,
                ext * scale,
                16,
                LEFT if s == "L" else RIGHT,
                "Extended region / 延伸区",
                rx=2,
            ),
            rect(x(start), y + 6, (end - start) * scale, 4, BRIDGE, f"Matched [{start}, {end})", rx=1),
        ]
        tick_y = 17 if s == "L" else 116
        if n * scale < 120:
            parts.append(text(origin, tick_y, f"0–{bp(n)}", cls="tick"))
        else:
            parts += [text(origin, tick_y, "0", cls="tick"), text(x(n), tick_y, bp(n), "end", cls="tick")]
    return (
        '<div class="scene">' + svg("Full-sequence synteny of the winning pair", 124, parts) + "</div>"
        + f'<p class="callout">'
        f'<span><span class="t-zh">比对区间 <b>L [{ls:,}, {le:,}) ↔ R [{rs:,}, {re_:,})</b></span>'
        f'<span class="t-en">Matched: L [{ls:,}, {le:,}) ↔ R [{rs:,}, {re_:,})</span></span>'
        f'<span><span class="t-zh">悬垂 <b>{esc(bp(w["overhang"]))}</b></span><span class="t-en">{esc(bp(w["overhang"]))} overhang</span></span>'
        f'<span><span class="t-zh">阶段 <b>{esc(stage_zh)}</b></span><span class="t-en">Stage: {esc(stage)}</span></span>'
        f'</p>'
    )


def composition(families, j):
    if not j or j.get("gap_length") is None:
        return ""
    repairs = j.get("repairs") or []
    gap, trim = max(0, j["gap_length"]), j.get("overlap_trim", 0)
    accepted = {
        s: sorted(
            (r for r in repairs if r["side"] == s and r["status"] == "accepted"), key=lambda r: r["start0"]
        )
        for s in ("L", "R")
    }

    def delta(edit):
        return len(edit["proposed"]) - len(edit["original"])

    sizes = {s: f["versions"][0]["length"] + sum(map(delta, accepted[s])) for s, f in families.items()}
    sizes["R"] -= trim
    right = sizes["L"] + gap
    total = right + sizes["R"]

    canvas_w = 768.0
    x0 = 16.0
    linear_gap_w = canvas_w * gap / max(1, total)
    compressed = gap > 0 and linear_gap_w < 54.0 and (sizes["L"] > 0 or sizes["R"] > 0)
    if compressed:
        gap_w = 56.0
        rem_w = canvas_w - gap_w
        flank_sum = max(1, sizes["L"] + sizes["R"])
        lw = rem_w * sizes["L"] / flank_sum
        rw = rem_w * sizes["R"] / flank_sum
        l_x, g_x, r_x = x0, x0 + lw, x0 + lw + gap_w
    else:
        lw = canvas_w * sizes["L"] / max(1, total)
        gap_w = linear_gap_w
        rw = canvas_w * sizes["R"] / max(1, total)
        l_x, g_x, r_x = x0, x0 + lw, x0 + lw + gap_w

    def map_pos(side, pos):
        if side == "L":
            return l_x + (pos / max(1, sizes["L"])) * lw
        return r_x + ((pos - trim) / max(1, sizes["R"])) * rw

    parts = [
        rect(l_x, 26, lw, 18, LEFT, f"Left original flank · {bp(sizes['L'])}", rx=3),
        rect(g_x, 26, gap_w, 18, BRIDGE, f"Net gap-only fill · {bp(gap)}", rx=2),
        rect(r_x, 26, rw, 18, RIGHT, f"Right original flank · {bp(sizes['R'])}", rx=3),
        f'<path d="M{g_x:.3f},22 v26 M{r_x:.3f},22 v26" stroke="{BRIDGE}" stroke-width="1.2"/>',
    ]
    if gap_w >= 46:
        parts.append(text(g_x + gap_w / 2, 39, f"+{gap:,}" if gap < 10000 else bp(gap), "middle", "delta"))
    if compressed:
        for bx in (l_x + lw * 0.5, r_x + rw * 0.5):
            if bx > x0 + 18 and bx < x0 + canvas_w - 18:
                parts.append(
                    f'<path d="M{bx - 3:.2f},45 l4,-20 M{bx + 1:.2f},45 l4,-20" stroke="#ffffff" stroke-width="1.5"/>'
                )

    dense = len(repairs) > 24
    if not dense:
        for r in repairs:
            side, pos, status = r["side"], r.get("start0"), r["status"]
            if pos is None or side not in sizes:
                continue
            shift = sum(delta(a) for a in accepted[side] if a["end0"] <= pos and a["start0"] < pos)
            at = map_pos(side, pos + shift)
            y, color = {"accepted": (11, BRIDGE), "protected": (55, "#64748b")}.get(status, (64, "#d97706"))
            parts.append(
                f"<g><title>{esc(side)} [{pos}, {r.get('end0', pos)}) · {esc(status)}</title>"
                f'<path d="M{at:.3f},{y} V{26 if y < 26 else 44}" stroke="{color}"/>'
                f'<circle cx="{at:.3f}" cy="{y}" r="2.8" fill="{color}"/></g>'
            )
    else:
        buckets = defaultdict(list)
        for r in repairs:
            side, pos, status = r["side"], r.get("start0"), r["status"]
            if pos is None or side not in sizes:
                continue
            shift = sum(delta(a) for a in accepted[side] if a["end0"] <= pos and a["start0"] < pos)
            at = map_pos(side, pos + shift)
            key = (side, status, round(at / 8.0))
            buckets[key].append((at, r))
        for (side, status, _bin), group in buckets.items():
            at = sum(p for p, _ in group) / len(group)
            y, color = {"accepted": (11, BRIDGE), "protected": (55, "#64748b")}.get(status, (63, "#d97706"))
            tip = "; ".join(f"{side} [{r.get('start0')}, {r.get('end0', r.get('start0'))}) · {status}" for _, r in group[:8])
            if len(group) > 8:
                tip += f" (+{len(group) - 8} more)"
            radius = min(5.5, 2.4 + 0.6 * min(len(group), 5))
            parts.append(
                f"<g><title>{esc(tip)}</title>"
                f'<path d="M{at:.3f},{y} V{26 if y < 26 else 44}" stroke="{color}" stroke-opacity="0.7"/>'
                f'<circle cx="{at:.3f}" cy="{y}" r="{radius:.1f}" fill="{color}" fill-opacity="0.82"/></g>'
            )

    flanks_en = " · ".join(
        f"{s}: {info['status']} ({info.get('accepted_variants', 0)} accepted / "
        f"{info.get('proposed_variants', 0)} proposed)"
        for s, info in j.get("flanks", {}).items()
    )
    flanks_zh = " · ".join(
        f"{s} 侧：{zh_term(info['status'])}（采用 {info.get('accepted_variants', 0)} / 提议 {info.get('proposed_variants', 0)}）"
        for s, info in j.get("flanks", {}).items()
    )
    trim_zh = f" · 重叠裁剪 {bp(trim)}" if trim else ""
    scale_zh = " · 长侧翼已示意压缩" if compressed else ""
    scale_en = " · Long flanks compressed" if compressed else ""
    return (
        f'<div class="subfig"><h3>{bi("Final junction composition", "最终拼接组成")}</h3>'
        f'<div class="scene">{svg("Final sequence composition and terminal edit markers", 74, parts)}</div>'
        f'<p class="callout">'
        f'<span><span class="t-zh">左侧翼 <b>{esc(bp(sizes["L"]))}</b></span><span class="t-en"><b>Left flank {esc(bp(sizes["L"]))}</b></span></span>'
        f'<span><span class="t-zh">净填补 <b>{esc(bp(gap))}</b></span><span class="t-en"><b>Net fill {esc(bp(gap))}</b></span></span>'
        f'<span><span class="t-zh">右侧翼 <b>{esc(bp(sizes["R"]))}</b></span><span class="t-en"><b>Right flank {esc(bp(sizes["R"]))}</b></span></span>'
        f'</p>'
        f'<p class="note">'
        f'<span class="t-zh">标记：绿=已采用 · 灰=受保护 · 橙=保留/冲突{esc(trim_zh)}{esc(scale_zh)}'
        + (f' · {esc(flanks_zh)}' if flanks_zh else '')
        + f'</span><span class="t-en">original overlap trimmed: {esc(bp(trim))}. Markers: green accepted · slate protected · amber retained/conflict{esc(scale_en)}. {esc(flanks_en)}</span>'
        f"</p></div>"
    )


def table(headers, rows, *, raw_cols=()):
    raw_set = set(raw_cols)
    return (
        '<div class="well" tabindex="0"><table><thead><tr>'
        + "".join(f'<th scope="col">{c}</th>' for c in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{c if idx in raw_set else esc(c)}</td>" for idx, c in enumerate(row)) + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def growth_chart(events):
    """Compare cumulative added bases on one shared round axis, not two local attempt axes."""
    gain = {"L": 0, "R": 0}
    series = {s: [(0, 0)] for s in gain}
    for i, (side, event) in enumerate(events, 1):
        gain[side] += event["delta"]
        series[side].append((i, gain[side]))
    peak = max(gain.values())
    if not peak:
        return (
            f'<p class="note">{bi("No extension rounds.", "未进行延伸。")}</p>'
            if not events
            else f'<p class="note">{bi("No bases added across rounds.", "各轮均未产生净延伸。")}</p>'
        )

    def x(i):
        return 106 + 660 * i / len(events)

    def y(n):
        return 82 - 62 * n / peak

    marks = []
    for label, value, dash in [(bp(peak), peak, ""), (bp(peak // 2), peak // 2, ' stroke-dasharray="3 3"'), ("0 bp", 0, "")]:
        marks += [
            text(95, y(value) + 4, label, "end", "tick"),
            f'<path class="svg-grid" d="M106,{y(value):.2f} H766" stroke="#cbd5e1"{dash}/>',
        ]
    marks += [text(106, 102, "R0", cls="tick"), text(766, 102, f"R{len(events)}", "end", cls="tick")]
    if len(events) >= 2:
        mid = len(events) // 2
        marks.append(text(x(mid), 102, f"R{mid}", "middle", cls="tick"))
    for side, color in [("L", LEFT), ("R", RIGHT)]:
        points = series[side]
        segments = "".join(f"H{x(i):.2f} V{y(n):.2f} " for i, n in points[1:])
        dash = ' stroke-dasharray="6 3"' if side == "R" else ""
        marks.append(f'<path d="M106,82 {segments}H766 V82 Z" fill="{color}" fill-opacity="0.06"/>')
        marks.append(f'<path d="M106,82 {segments}H766" fill="none" stroke="{color}" stroke-width="2.4"{dash}/>')
        for i, n in points[1:]:
            marks.append(
                f'<circle cx="{x(i):.2f}" cy="{y(n):.2f}" r="3.2" fill="{color}" stroke="#ffffff" stroke-width="1"><title>'
                f"Round {i} · {side} +{bp(n)} cumulative</title></circle>"
            )
    return (
        f'<div class="subhead-row"><h3>{bi("Cumulative extension", "累计延伸曲线")}</h3>'
        f'<div class="track-key"><span class="track-L">{bi("L side", "L 侧")}</span>'
        f'<span class="track-R">{bi("R side", "R 侧")}</span></div></div>'
        '<div class="trend">' + svg("Cumulative L and R gain by shared round", 108, marks) + "</div>"
    )


def ledger(families, rounds):
    rows = []
    for i in range(max(map(len, rounds.values()), default=0)):
        row = [i + 1]
        for s in ("L", "R"):
            e = rounds[s][i] if i < len(rounds[s]) else None
            row.append(f"v{e['version']} · {bp(e['length'])} (+{e['delta']:,})" if e else "—")
        rows.append(row)
    headers = [bi("Attempt", "轮次"), bi("L → length (+gain)", "L 侧长度 (+净增)"), bi("R ← length (+gain)", "R 侧长度 (+净增)")]
    return f'<h3>{bi("Extension by attempt", "分侧轮次")}</h3>{table(headers, rows)}'


def matrix(families, w, diagnostics, eligible):
    ls, rs = [f["versions"] for f in families.values()]
    parts = ["<span>L × R</span>"] + [f"<span>v{v['number']}</span>" for v in rs]
    for left in ls:
        parts.append(f"<span>v{left['number']}</span>")
        for right in rs:
            key = left["number"], right["number"]
            d = diagnostics.get(key, {})
            cls, symbol, label = cell_info(key, w, d, eligible)
            desc = [f"L/v{key[0]} × R/v{key[1]}: {label}"]
            for stage in d.get("stages", []):
                counts = ", ".join(
                    f"{k}: {v}" for k, v in stage.get("rejections", {}).items() if k != "blocks"
                )
                desc.append(
                    f"{stage['stage']}: {stage.get('blocks', 0)} blocks · {stage.get('reason', '—')} · {counts}"
                )
            tip = esc("; ".join(desc))
            parts.append(
                f'<span class="cell {cls}" tabindex="0" title="{tip}" aria-label="{tip}">{symbol}</span>'
            )
    return (
        f'<h3>{bi("Pair checks", "连接矩阵")}</h3><div class="well"><div class="matrix" style="grid-template-columns:auto repeat({len(rs)},minmax(36px,1fr))">'
        f'{"".join(parts)}</div></div>'
        f'<p class="note">{bi("★ winner · ✓ eligible · × rejected · – no alignment · · unreported", "★ 胜出 · ✓ 合格 · × 拒收 · – 无比对 · · 未记录")}</p>'
    )


def drawer(label_html, content):
    return f'<details class="drawer"><summary>{label_html}</summary>{content}</details>'


def chapter(n, label_html, content):
    return (
        f'<section class="chapter"><div class="section-title"><span class="card-num">{n:02}</span>'
        f'<h2>{label_html}</h2></div><div class="chapter-body">{content}</div></section>'
    )


def render(result, checked):
    lookup = {f["key"]: f for f in result["families"]}
    if set(lookup) != {"L", "R"} or len(result["families"]) != 2:
        raise ValueError("Expected a bidirectional L/R gap result")
    families = {s: lookup[s] for s in ("L", "R")}
    w = result.get("winner")
    status = result["status"]
    j = result.get("junction")
    if (status == "closed") != (w is not None):
        raise ValueError("Closure status disagrees with the recorded winner")
    diags = result.get("connection_diagnostics") or []
    diagnostics = {pair(d): d for d in diags}
    candidates = [c for group in (checked or {}).values() for c in group]
    if w and w not in candidates:
        candidates.append(w)
    eligible = {pair(c) for c in candidates}
    requests = result.get("anchor_backoff_requests", result.get("anchor_retries", []))
    rounds = {
        s: attempts(f, {r["after_attempt"] for r in requests if r["family"] == s})
        for s, f in families.items()
    }
    events = timeline(rounds)
    checks_en, checks_zh = checks_by_step(events, diagnostics, eligible, w)
    final = result.get("final_sequence", "")
    # Only link a plain basename, never a URL, traversal, drive path or HTML fragment.
    safe_final = bool(re.fullmatch(r"[\w.\-+]+\.final\.fa", final))
    raw_name = final[:-9] if safe_final else "Bidirectional gap"
    display_title, sub_id = format_display_title(raw_name)
    gap = (j or {}).get("gap_length", result.get("gap_length"))
    if j or gap is None:
        gap_val = bp(max(0, gap)) if gap is not None else "—"
        gap_en, gap_zh = "Net gap-only fill", "净填补长度"
    else:
        gap_val = bp(gap)
        gap_en, gap_zh = "Net length vs original flanks", "相对原侧翼净变化"
    ext_val = " / ".join(f"{s} +{bp(f['added_bases'])}" for s, f in families.items())
    ov_val = f"{bp(w['overlap'])} · {w['identity']}%" if w else "—"
    metrics = [
        (gap_en, gap_zh, gap_val),
        ("Extension", "双向延伸", ext_val),
        ("Overlap", "闭合重叠", ov_val),
        ("Rounds", "总轮次", result["total_rounds"]),
    ]
    strip = "".join(
        f'<span><span class="t-zh">{esc(zh)} <b>{esc(val)}</b></span>'
        f'<span class="t-en">{esc(en)} <b>{esc(val)}</b></span></span>'
        for en, zh, val in metrics
    )
    badge = badge_bi(
        "Closed" if w else f"Unclosed ({status})",
        "已闭合" if w else f"未闭合 · {zh_term(status)}",
        "ok" if w else "warn",
    )

    sections = []
    sec_no = 1
    first = player(families, events, checks_en, checks_zh, w, status)
    sections.append(chapter(sec_no, bi("Extension & closure", "延伸与闭合"), first))
    sec_no += 1

    # Only render Alignment & composition chapter when closed (avoid empty redundant card on unclosed).
    if w:
        second = (
            f'<div class="subfig"><h3>{bi("Winning pair", "闭合版本对")}</h3>'
            + alignment(families, w)
            + "</div>"
            + composition(families, j)
        )
        sections.append(chapter(sec_no, bi("Alignment & composition", "比对与拼接"), second))
        sec_no += 1

    third = (
        growth_chart(events)
        + '<div class="layout"><div>'
        + ledger(families, rounds)
        + "</div><div>"
        + matrix(families, w, diagnostics, eligible)
        + "</div></div>"
    )
    sections.append(chapter(sec_no, bi("Rounds & connection checks", "延伸轮次与连接矩阵"), third))
    sec_no += 1

    evidence = render_junction_report(
        {
            "junction": {k: v for k, v in (j or {}).items() if k != "evidence_artifacts"},
            "connection_diagnostics": diags,
            "anchor_retries": result.get("anchor_retries"),
        }
    )
    details = (
        drawer(bi("Junction, terminal edits & diagnostics", "边界修订与逐对诊断"), evidence)
        if evidence
        else ""
    )
    if candidates:
        comparisons = [
            (
                f"L/{c['left_version']}",
                f"R/{c['right_version']}",
                c["identity"],
                c["overlap"],
                c["overhang"],
                bi("Selected", "已采用") if c == w else bi("Not selected", "未采用"),
            )
            for c in candidates
        ]
        details += drawer(
            bi(f"Eligible connections ({len(candidates)})", f"合格连接候选（{len(candidates)}）"),
            (f'<p class="note">{bi("Individual alternatives require families.json.", "完整候选项需依赖 families.json。")}</p>' if checked is None else "")
            + f'<p class="note">{bi("Rank: identity, overlap, overhang, fixed version order.", "排序规则：一致性、重叠长度、悬垂长度、固定版本序。")}</p>'
            + table(
                [bi("Left", "左侧"), bi("Right", "右侧"), bi("Identity %", "一致性 %"), bi("Overlap (bp)", "重叠 (bp)"), bi("Overhang (bp)", "悬垂 (bp)"), bi("Selection", "状态")],
                comparisons,
                raw_cols=(5,),
            ),
        )
    history = [
        (s, f"v{v['number']}", bp(v["length"]), f'<span class="hash hash-short" title="{esc(v["sha256"])}">{esc(v["sha256"])}</span>')
        for s, f in families.items()
        for v in f["versions"]
    ]
    details += drawer(
        bi("Sequence history & SHA-256", "版本历史与校验值"),
        table([bi("Family", "侧别"), bi("Version", "版本"), bi("Length", "长度"), "SHA-256"], history, raw_cols=(3,)),
    )
    links = ([final] if safe_final else []) + [
        "process.agp",
        "family-components.fa",
        "family-result.json",
        "families.json",
    ]
    if diags or "connection-diagnostics.json" in (result.get("evidence_artifacts") or {}).values():
        links.append("connection-diagnostics.json")
    if j:
        links.append("junction-evidence.json")
    details += drawer(
        bi("Artifacts & provenance", "输出文件与溯源"),
        '<nav class="links">'
        + "".join(f'<a href="{esc(quote(link))}">{esc(link)}</a>' for link in links)
        + "</nav>",
    )
    sections.append(chapter(sec_no, bi("Evidence & provenance", "证据与溯源"), details))

    lang_ctrl = (
        '<div class="lang-switch" data-lang-switch role="group" aria-label="Language Switcher">'
        '<button type="button" data-lang="zh" aria-pressed="false">中文</button>'
        '<button type="button" data-lang="en" aria-pressed="true">EN</button>'
        '</div>'
    )
    theme_ctrl = (
        '<div class="fr-theme-wrap">'
        '<button type="button" data-theme-toggle="1" aria-label="Toggle theme" title="Toggle theme" aria-pressed="false">'
        '<svg class="ico-moon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>'
        '<svg class="ico-sun" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2m-7.07-14.93 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>'
        '</button>'
        '</div>'
    )
    sub_id_html = f'<div class="sub-id">{esc(sub_id)}</div>' if sub_id else ""
    brand_icon = degap_logo_html(24)
    return f"""<!doctype html>
<html lang="en" data-lang="en" data-theme="light"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(display_title)} · DEGAP</title><style>{report_css(CSS)}</style></head>
<body><header class="fr-topbar"><div class="fr-topbar-inner"><div class="fr-topbar-left">{brand_icon}<div class="fr-title-block"><div class="fr-title-row"><h1><span class="fr-brand-tag">DEGAP</span> · {esc(display_title)}</h1>{badge}</div>{sub_id_html}</div></div><div class="fr-topbar-right">{lang_ctrl}{theme_ctrl}</div></div></header>
<main class="sheet"><section class="fr-kpi-card"><div class="strip">{strip}</div></section>
{"".join(sections)}
<footer>{bi("DEGAP · Bidirectional family extension report", "DEGAP · 双向缺口延伸报告")}</footer>
</main><script>{SCRIPT}</script></body></html>"""
