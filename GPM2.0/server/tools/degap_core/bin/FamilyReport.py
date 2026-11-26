"""Offline bidirectional gap report. Coordinates below are zero-based, half-open."""

from collections import defaultdict
import re
from urllib.parse import quote

from FamilyReportStyle import CSS, SCRIPT
from JunctionReport import render_junction_report
from ReportStyle import badge_html, esc, report_css

LEFT, RIGHT, ORIGINAL, BRIDGE = "#426e99", "#a25c3d", "#b9c6cb", "#298a6a"


def bp(n):
    return "—" if n is None else f"{n:,} bp"


def rect(x, y, width, height, fill, title=""):
    return (
        f'<rect x="{x:.3f}" y="{y}" width="{max(0, width):.3f}" height="{height}" fill="{fill}">'
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
        f'<path class="overlap-bridge" fill="{BRIDGE}" fill-opacity=".28" stroke="{BRIDGE}" '
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
    checks = defaultdict(list)
    for key in sorted(set(diagnostics) | eligible):
        left, right = key
        n = max(introduced["L"][left], introduced["R"][right])
        label = cell_info(key, winner, diagnostics.get(key), eligible)[2]
        checks[n].append(f"L/v{left} × R/v{right}: {label}")
    return checks


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
        return 58 + 712 * (n - low) / (high - low)

    def block(start, end, y, color, title):
        a, b = x(max(low, start)), x(min(high, end))
        return rect(a, y, b - a, 19, color, title)

    parts = [
        text(8, 43, "L →", cls="label"),
        text(8, 108, "R ←", cls="label"),
        block(-base["L"], 0, 28, ORIGINAL, "Left original flank"),
        block(boundary, boundary + base["R"], 93, ORIGINAL, "Right original flank"),
    ]
    for i, (side, event) in enumerate(events, 1):
        if not event["delta"]:
            continue
        delta = event["delta"]
        gain = event["length"] - base[side]
        a, b, y = (gain - delta, gain, 28) if side == "L" else (boundary - gain, boundary - gain + delta, 93)
        label = f"{side}/v{event['version']} · +{bp(delta)}"
        item = block(a, b, y, LEFT if side == "L" else RIGHT, label)
        item += f'<path d="M{x(a):.3f},{y} v19" stroke="white"/>'
        if x(b) - x(a) > 80:
            item += text((x(a) + x(b)) / 2, y + 14, "+" + bp(delta), "middle", "delta")
        parts.append(f'<g data-from="{i}">{item}</g>')
    if ends:
        layer = ribbon(*map(x, ends), 47, 93)
    elif not w:
        a, b = x(gains["L"]), x(boundary - gains["R"])
        layer = (
            '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse">'
            '<path d="M0,6 L6,0" stroke="#bd9258"/></pattern></defs>'
            + rect(a, 48, b - a, 43, "url(#hatch)", "Unclosed interval; width unknown")
            + text((a + b) / 2, 14, "Unclosed · span unknown", "middle")
        )
    else:
        layer = ""
    parts.append(f'<g data-from="{len(events)}">{layer}</g>')
    return svg("Inward extension · zoomed terminal regions", 130, parts)


def player(families, events, checks, w, status):
    pills, captions = [], []
    versions = {"L": 0, "R": 0}
    for i, entry in enumerate([None, *events]):
        if entry:
            s, e = entry
            versions[s] = e["version"]
            label = f"{s}→v{e['version']}" if e["delta"] else f"{s} · #{e['attempt']}"
            caption = f"Round {i} · {s}/v{e['version']} · +{bp(e['delta'])} → {bp(e['length'])}" + (
                " · " + e["reason"] if e["reason"] else ""
            )
        else:
            label, caption = "初始 v0", "Initial · L/v0 × R/v0"
        last = i == len(events)
        if last:
            label += " · 闭合" if w else " · 未闭合"
            caption += " · " + status
        pills.append(
            f'<button data-step="{i}" aria-current="{"step" if last else "false"}">{esc(label)}</button>'
        )
        detail = "; ".join(checks[i]) or (
            "No new pair · versions unchanged"
            if entry and not entry[1]["delta"]
            else "No pair-level diagnostic recorded"
        )
        tracks = "".join(
            f'<span class="track-{s}">{s}/v{v} · {bp(families[s]["versions"][v]["length"])}</span>'
            for s, v in versions.items()
        )
        captions.append(
            f'<div data-caption="{i}"{"" if last else " hidden"}><div class="track-key">{tracks}</div>'
            f"<strong>{esc(caption)}</strong>{esc(detail)}</div>"
        )
    disabled = "" if events else " disabled"
    legend = (
        "Green bridge: winning overlap / 绿色连接带为胜出重叠。"
        if coords(w)
        else "Hatching: unclosed interval, width unknown / 斜纹表示未闭合，不代表缺口长度。"
        if not w
        else "Winning interval coordinates not recorded / 未记录胜出区间坐标。"
    )
    return (
        f'<div data-player><div class="controls"><button class="play" aria-pressed="false"{disabled}>▶ 播放过程 / Play</button>'
        f'<button class="prev"{disabled}>← 上一步 / Prev</button><button class="next" disabled>下一步 / Next →</button></div>'
        f'<div class="pills">{"".join(pills)}</div><div class="scene">{scene(families, events, w)}</div>'
        f'<div class="caption" aria-live="polite">{"".join(captions)}</div>'
        f'<p class="note">Terminal zoom / 末端放大 · Gray: original flanks / 灰色为原始侧翼。{legend}</p></div>'
    )


def alignment(families, w):
    if not w:
        return '<p class="note">No eligible connection / 无合格连接。The two sequences remain separate.</p>'
    stage = (w.get("evidence") or {}).get("stage") or "not recorded"
    summary = (
        f'<p class="callout"><b>{bp(w["overlap"])} overlap</b><span>{esc(w["identity"])}% identity</span>'
        f"<span>{bp(w['overhang'])} overhang</span><span>Stage: {esc(stage)}</span></p>"
    )
    if not coords(w):
        return summary + '<p class="note">Matched coordinates were not recorded.</p>'
    # One bp has the same width on both axes. Offset the two bars slightly in y,
    # not x: each sequence starts at its own zero; the ribbon shows correspondence.
    lengths = {
        s: families[s]["versions"][w[k]]["length"] for s, k in (("L", "left_version"), ("R", "right_version"))
    }
    scale = 699 / max(lengths.values())
    origin = 82

    def x(n):
        return origin + n * scale

    ls, le, rs, re_ = (w[k] for k in ("left_start", "left_end", "right_start", "right_end"))
    parts = [ribbon(x(ls), x(le), x(rs), x(re_), 38, 83)]
    for s, y, start, end in [("L", 23, ls, le), ("R", 83, rs, re_)]:
        n = lengths[s]
        orig = families[s]["versions"][0]["length"]
        ext = n - orig
        parts += [
            text(8, y + 12, f"{s}/v{w['left_version' if s == 'L' else 'right_version']}", cls="label"),
            rect(origin, y, n * scale, 15, ORIGINAL, "Original flank / 原始侧翼"),
            rect(
                x(orig if s == "L" else 0),
                y,
                ext * scale,
                15,
                LEFT if s == "L" else RIGHT,
                "Extended region / 延伸区",
            ),
            rect(x(start), y + 6, (end - start) * scale, 3, BRIDGE, f"Matched [{start}, {end})"),
        ]
        tick_y = 18 if s == "L" else 115
        if n * scale < 120:
            parts.append(text(origin, tick_y, f"0–{bp(n)}"))
        else:
            parts += [text(origin, tick_y, "0"), text(x(n), tick_y, bp(n), "end")]
    return (
        svg("Full-sequence synteny of the winning pair", 122, parts)
        + summary
        + f'<p class="note">Matched intervals (0-based, end-exclusive): L [{ls:,}, {le:,}) ↔ R [{rs:,}, {re_:,}). '
        "Gray: original flank · blue/rust: cumulative gain.</p>"
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

    def x(n):
        return 16 + n * 768 / max(1, total)

    parts = [
        rect(x(offset), 25, x(offset + length) - x(offset), 17, color, label)
        for offset, length, color, label in [
            (0, sizes["L"], LEFT, "Left original flank"),
            (sizes["L"], gap, BRIDGE, "Net gap-only fill"),
            (right, sizes["R"], RIGHT, "Right original flank"),
        ]
    ]
    # Keep a subpixel fill proportional; mark the exact boundaries separately.
    for boundary in (sizes["L"], right):
        parts.append(f'<path d="M{x(boundary):.3f},21 v25" stroke="{BRIDGE}"/>')
    for r in repairs:
        side, pos, status = r["side"], r.get("start0"), r["status"]
        if pos is None or side not in sizes:
            continue
        shift = sum(delta(a) for a in accepted[side] if a["end0"] <= pos and a["start0"] < pos)
        at = x(pos + shift + (right - trim if side == "R" else 0))
        y, color = {"accepted": (11, BRIDGE), "protected": (54, "#667882")}.get(status, (63, "#ac6726"))
        parts.append(
            f"<g><title>{esc(side)} [{pos}, {r.get('end0', pos)}) · {esc(status)}</title>"
            f'<path d="M{at:.3f},{y} V{25 if y < 25 else 42}" stroke="{color}"/>'
            f'<circle cx="{at:.3f}" cy="{y}" r="2.6" fill="{color}"/></g>'
        )
    flanks = " · ".join(
        f"{s}: {info['status']} ({info.get('accepted_variants', 0)} accepted / "
        f"{info.get('proposed_variants', 0)} proposed)"
        for s, info in j.get("flanks", {}).items()
    )
    return (
        f'<div class="subfig"><h3>Final junction composition / 最终拼接组成</h3>'
        f"{svg('Final sequence composition and terminal edit markers', 70, parts)}"
        f'<p class="callout"><b>Left flank {bp(sizes["L"])}</b><b>Net fill {bp(gap)}</b>'
        f'<b>Right flank {bp(sizes["R"])}</b></p><p class="note">Final flank lengths include accepted edits; '
        f"original overlap trimmed: {bp(trim)}. Markers: green accepted · slate protected · amber retained/conflict. "
        f"{esc(flanks)}</p></div>"
    )


def table(headers, rows):
    return (
        '<div class="well" tabindex="0"><table><thead><tr>'
        + "".join(f'<th scope="col">{esc(c)}</th>' for c in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in row) + "</tr>" for row in rows)
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
            '<p class="note">No extension rounds / 未进行延伸。</p>'
            if not events
            else '<p class="note">No bases added / 各轮均未产生净延伸。</p>'
        )

    def x(i):
        return 106 + 660 * i / len(events)

    def y(n):
        return 90 - 69 * n / peak

    marks = []
    for label, value in [(bp(peak), peak), ("0 bp", 0)]:
        marks += [text(95, y(value) + 4, label, "end"), f'<path d="M106,{y(value)} H766" stroke="#ccd6d8"/>']
    marks += [text(106, 113, "Round 0"), text(766, 113, f"Round {len(events)}", "end")]
    for side, color in [("L", LEFT), ("R", RIGHT)]:
        points = series[side]
        segments = "".join(f"H{x(i):.2f} V{y(n):.2f} " for i, n in points[1:])
        dash = ' stroke-dasharray="6 3"' if side == "R" else ""
        marks.append(
            f'<path d="M106,90 {segments}H766" fill="none" stroke="{color}" stroke-width="2.5"{dash}/>'
        )
        for i, n in points[1:]:
            marks.append(
                f'<circle cx="{x(i):.2f}" cy="{y(n):.2f}" r="3" fill="{color}"><title>'
                f"Round {i} · {side} +{bp(n)} cumulative</title></circle>"
            )
    return (
        '<h3>Cumulative extension / 累计延伸</h3><div class="trend">'
        + svg("Cumulative L and R gain by shared round", 120, marks)
        + "</div>"
        f'<p class="track-key"><span class="track-L">L +{bp(gain["L"])}</span><span class="track-R">R +{bp(gain["R"])}</span></p>'
    )


def ledger(families, rounds):
    rows = []
    for i in range(max(map(len, rounds.values()))):
        row = [i + 1]
        for s in ("L", "R"):
            e = rounds[s][i] if i < len(rounds[s]) else None
            row.append(f"v{e['version']} · {bp(e['length'])} (+{e['delta']:,})" if e else "—")
        rows.append(row)
    notes = " · ".join(f"{s}: {f['stop_reason']}" for s, f in families.items() if f.get("stop_reason"))
    return (
        f"<h3>Extension by attempt / 分侧轮次</h3>{table(['Attempt', 'L → length (+gain)', 'R ← length (+gain)'], rows)}"
        f'<p class="stop">{esc(notes)}</p>'
    )


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
        f'<h3>Pair checks / 连接矩阵</h3><div class="well"><div class="matrix" style="grid-template-columns:auto repeat({len(rs)},minmax(35px,1fr))">'
        f'{"".join(parts)}</div></div><p class="note">★ winner · ✓ eligible · × rejected · – no alignment · · unreported</p>'
    )


def drawer(label, content):
    return f'<details class="drawer"><summary>{esc(label)}</summary>{content}</details>'


def chapter(n, label, content):
    return (
        f'<section class="chapter"><div class="section-title"><span class="section-no">{n:02}</span>'
        f"<h2>{esc(label)}</h2></div>{content}</section>"
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
    checks = checks_by_step(events, diagnostics, eligible, w)
    final = result.get("final_sequence", "")
    # Only link a plain basename, never a URL, traversal, drive path or HTML fragment.
    safe_final = bool(re.fullmatch(r"[\w.\-+]+\.final\.fa", final))
    name = final[:-9] if safe_final else "Bidirectional gap"
    gap = (j or {}).get("gap_length", result.get("gap_length"))
    # Pre-junction publications only record final length minus the two original flanks.
    gap_metric = (
        ("Net gap-only fill", bp(max(0, gap)) if gap is not None else "—")
        if j or gap is None
        else ("Net length vs original flanks", bp(gap))
    )
    metrics = [
        gap_metric,
        ("Extension", " / ".join(f"{s} +{bp(f['added_bases'])}" for s, f in families.items())),
        ("Overlap", f"{bp(w['overlap'])} · {w['identity']}%" if w else "—"),
        ("Rounds", result["total_rounds"]),
    ]
    strip = "".join(f"<span>{esc(label)} <b>{esc(value)}</b></span>" for label, value in metrics)
    badge = badge_html("Closed / 已闭合" if w else f"Unclosed / 未闭合 ({status})", "ok" if w else "warn")
    first = player(families, events, checks, w, status)
    second = (
        ('<div class="subfig"><h3>Winning pair / 闭合版本对</h3>' if w else '<div class="subfig">')
        + alignment(families, w)
        + "</div>"
    )
    if w:
        second += composition(families, j)
    else:
        stop_reasons = " · ".join(
            f"{s}: {f['stop_reason']}" for s, f in families.items() if f.get("stop_reason")
        )
        second += f'<p class="stop">{esc(stop_reasons or status)}</p>'
    third = (
        growth_chart(events)
        + '<div class="layout"><div>'
        + ledger(families, rounds)
        + "</div><div>"
        + matrix(families, w, diagnostics, eligible)
        + "</div></div>"
    )
    # The generic evidence renderer also accepts links. This report owns its own strict allowlist.
    evidence = render_junction_report(
        {
            "junction": {k: v for k, v in (j or {}).items() if k != "evidence_artifacts"},
            "connection_diagnostics": diags,
            "anchor_retries": result.get("anchor_retries"),
        }
    )
    details = (
        drawer("Junction, terminal edits & fast/full diagnostics / 边界修订与逐对诊断", evidence)
        if evidence
        else ""
    )
    comparisons = [
        (
            f"L/{c['left_version']}",
            f"R/{c['right_version']}",
            c["identity"],
            c["overlap"],
            c["overhang"],
            "Selected" if c == w else "Not selected",
        )
        for c in candidates
    ]
    details += drawer(
        "Eligible connections / 合格连接",
        ("<p>Individual alternatives require families.json.</p>" if checked is None else "")
        + '<p class="note">Rank: identity, overlap, overhang, fixed version order.</p>'
        + table(["Left", "Right", "Identity %", "Overlap (bp)", "Overhang (bp)", "Selection"], comparisons),
    )
    history = [
        (s, f"v{v['number']}", bp(v["length"]), v["sha256"])
        for s, f in families.items()
        for v in f["versions"]
    ]
    details += drawer(
        "Sequence history / 版本与 SHA-256", table(["Family", "Version", "Length", "SHA-256"], history)
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
        "Artifacts & provenance / 输出与溯源",
        '<nav class="links">'
        + "".join(f'<a href="{esc(quote(link))}">{esc(link)}</a>' for link in links)
        + "</nav>",
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(name)} · DEGAP family extension</title><style>{report_css(CSS)}</style></head>
<body><main class="sheet"><header><div class="kicker">DEGAP / Bidirectional family extension · 双向延伸</div>
<div class="top"><h1>{esc(name)}</h1>{badge}</div><div class="strip">{strip}</div></header>
{chapter(1, "Extension & closure / 延伸与闭合", first)}
{chapter(2, "Alignment & composition / 比对与拼接", second)}
{chapter(3, "Rounds & connection checks / 延伸与连接检查", third)}
{chapter(4, "Evidence & provenance / 证据与溯源", details)}
<footer>Attempt-level mappings, local assemblies and receipts, when retained: <code>attempts/</code>.</footer>
</main><script>{SCRIPT}</script></body></html>"""
