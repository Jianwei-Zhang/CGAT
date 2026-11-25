"""Read-only, offline Final Path story cards. Only consume the public report projection."""
from __future__ import annotations

if __package__:
    from .render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_bp_short, fmt_int, table
else:
    from render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_bp_short, fmt_int, table


def section(key, num, zh, en, body):
    return (f'<section class="panel path-story" id="{key}"><h2><small class="muted">{num}</small>'
            f'　{bi(zh, en)}</h2>{body}</section>')


def input_card(inputs):
    missing = bi("未记录", "Not recorded")

    def measure(st, key, formatter):
        return esc(formatter(st[key])) if st.get(key) is not None else missing

    refs = []
    for ref in inputs["reference"]:
        st = ref["stats"]
        refs.append(f'<p><strong>{esc(ref["name"])}</strong> · {measure(st, "sequence_count", fmt_int)} '
                    + bi("条序列", "sequences") + " · " + measure(st, "length_bp", fmt_bp)
                    + " · " + bi("比对与染色体定位的坐标参照", "Coordinate reference for alignment and placement") + "</p>")
    rows = []
    for index, assembly in enumerate(inputs["assemblies"]):
        st = assembly["stats"]
        rows.append([f'<i class="swatch" style="background:var(--ds-{index % 6})"></i> {esc(assembly["name"])}',
                     measure(st, "sequence_count", fmt_int), measure(st, "length_bp", fmt_bp),
                     measure(st, "n50_bp", fmt_bp), measure(st, "gap_count", fmt_int)])
    grid = table([bi("候选组装", "Candidate assembly"), bi("序列数", "Sequences"), bi("总长", "Total length"),
                  bi("序列 N50", "Sequence N50"), bi("Gap 数（连续 N ≥100 bp）", "Gaps (N runs ≥100 bp)")],
                 rows, empty=missing)
    aux = [f'{esc({"hifi": "HiFi", "ont": "ONT", "reads": "Reads"}[r["technology"]])}: {r["file_count"]} '
           + bi("个文件", "files") for r in inputs["typed_reads"]]
    for key, zh, en in (("telomere_rules", "端粒规则", "Telomere rules"), ("centromere_reference", "着丝粒参考", "Centromere reference")):
        if (inputs["annotations"].get(key) or {}).get("configured") is True:
            aux.append(bi(zh, en) + ": " + bi("已配置", "configured"))
    return section("inputs", "01", "输入数据", "Inputs", ("".join(refs) or missing) + grid
                   + ('<p class="muted">' + " · ".join(aux) + "</p>" if aux else ""))


def assignment_card(assignment):
    threshold = assignment.get("min_coverage_percent")
    cut = (bi("本次阈值未记录", "Run threshold not recorded") if threshold is None else
           bi(f"本次阈值 {threshold:g}%", f"Run threshold {threshold:g}%"))
    # A teaching schematic, not a measured alignment. No example bp or inferred run threshold.
    drawing = ('<svg viewBox="0 0 260 68" width="260" height="68" aria-hidden="true">'
               '<g font-size="12" fill="currentColor"><text x="0" y="16">ctg</text><text x="0" y="60">ref_chr</text></g>'
               '<path d="M55 12H245M55 55H245" stroke="currentColor" fill="none"/>'
               '<path d="M75 12h45l15 43H90z M135 12h38l21 43h-38z" fill="var(--ds-1)" opacity=".5"/></svg>')
    rule = disclosure(bi("?　分配依据", "?　Assignment rule"), drawing + "<p>" + bi(
        "示意：将该 ctg 对该 ref_chr 的合格比对区间在 ctg 上取并集，覆盖长度除以整条 ctg 长度。达到本次阈值即入组；一个 ctg 可以属于多个组。",
        "Schematic: take the union of qualifying query intervals for this chromosome and divide by the full contig length. Each chromosome meeting the threshold is a group; a contig can belong to several.") + " · " + cut + "</p>")
    groups = assignment.get("groups")
    if groups is None:
        return section("chr-groups", "02", "染色体分组", "Chromosome groups", rule + "<p>" + bi("未记录完整的分组成员表", "Complete membership table unavailable") + "</p>")
    result = []
    has_multi = False
    for group in groups:
        sources = []
        for source in group["sources"]:
            members = []
            source_multi = False
            for member in source["members"]:
                multi = member["multi"]
                source_multi |= multi
                label = esc(member["name"])
                if multi:
                    label += " <small>" + bi("多组", "multi-group") + "</small>"
                members.append(f'<span class="member{" multi" if multi else ""}">{label}</span>')
            has_multi |= source_multi
            sources.append(f'<p class="member-source{" multi" if source_multi else ""}"><b>{esc(source["dataset"])}</b>　' + " ".join(members) + "</p>")
        count = group["member_count"]
        result.append(disclosure(esc(group["chr"]) + " · " + bi(f"{count} 个成员", f"{count} members"),
                                 "".join(sources) or bi("无成员", "No members")))
    # The checkbox filters names only: chromosome totals always describe the complete dataset.
    toggle = ('<input id="multi-members-only" type="checkbox"> <label for="multi-members-only">'
              + bi("只看多组成员", "Only multi-group members") + "</label>" if has_multi else "")
    style = ("<style>#multi-members-only:checked~.chr-members .member:not(.multi),"
             "#multi-members-only:checked~.chr-members .member-source:not(.multi){display:none}"
             ".chr-members .member{display:inline-block;margin-inline-end:.65em}"
             ".chr-members .multi small{color:var(--tone-info-ink)}</style>")
    return section("chr-groups", "02", "染色体分组", "Chromosome groups", style + rule + toggle
                   + '<div class="chr-members">' + ("".join(result) or bi("无已记录的染色体组", "No recorded chromosome groups")) + "</div>")


def q0_card(lgz):
    tracks = lgz.get("q0_scene")
    if not tracks:
        return section("alignment-q0", "03", "初始路径 q0", "Initial path q0", bi(
            "没有可核对的完整 q0 路径与定位证据，不绘制推测比对。",
            "No verified complete q0 selection is available; alignments have not been inferred."))
    domain = max([1] + [max(t["length_bp"] or 0, (t["ref"] or {}).get("length_bp", 0)) for t in tracks])
    sources = [d["name"] for d in lgz["inputs"]["assemblies"]]
    sources.extend(sorted({p["dataset"] for t in tracks for p in t["parts"] if p["kind"] == "source"} - set(sources)))
    colors = {ds: f"var(--ds-{i % 6})" for i, ds in enumerate(sources)}
    def pct(pos):
        return format(100 * pos / domain, ".10g")

    def mark(a, b, kind, tip, color=None):
        style = f"left:{pct(a)}%;width:{pct(b-a)}%" + (f";background:{color}" if color else "")
        return f'<span class="q0-mark {kind}" style="{style}" data-start="{a}" data-end="{b}" title="{esc(tip)}"></span>'

    style = """<style>.q0-row,.q0-axis{display:grid;grid-template-columns:minmax(6rem,12%) minmax(0,1fr);gap:.65rem;align-items:center}.q0-row{padding:.55rem 0;border-top:1px solid var(--border-subtle)}.q0-row small{display:block}.q0-rail{position:relative;height:9px}.q0-mark{position:absolute;display:block;height:100%}.q0-mark.ctg{min-width:3px}.q0-mark.ref{background:var(--text-muted)}.q0-mark.input-gap,.q0-mark.ref-gap,.q0-key.input-gap{background:repeating-linear-gradient(120deg,var(--text-muted) 0 1px,var(--surface-panel) 1px 4px);z-index:1}.q0-mark.unknown-gap,.q0-key.unknown-gap{background:var(--gen-gap);z-index:1}.q0-bands{width:100%;height:22px;display:block;color:var(--ds-1);fill:currentColor;fill-opacity:.22}.q0-mark.unspecified-gap{background:var(--gen-unfilled);z-index:1}.q0-key{display:inline-block;width:.85rem;height:.52rem}.q0-ruler{display:flex;justify-content:space-between;font-variant-numeric:tabular-nums}.q0-rails{overflow:hidden}</style>"""
    legend = [f'<span><i class="q0-key" style="background:{color}"></i> {esc(ds)}</span>' for ds, color in colors.items()]
    legend += ['<span><i class="q0-key input-gap"></i> ' + bi("原有 Gap", "Original gap") + "</span>",
               '<span><i class="q0-key unknown-gap"></i> ' + bi("新增占位 N", "New placeholder Ns") + "</span>"]
    body = [style, '<div class="legend-row">' + " ".join(legend) + "</div>",
            '<div class="q0-axis muted"><small>' + bi("共用比例尺", "Shared scale") + '</small><small class="q0-ruler">'
            + "".join(f"<span>{esc(fmt_bp_short(round(domain * i/4)))}</span>" for i in range(5)) + "</small></div>"]
    for track in tracks:
        name, ref = track["chr"], track["ref"]
        ref_marks = ""
        if ref:
            ref_marks = mark(0, ref["length_bp"], "ref", f"{name} · {ref['length_bp']:,} bp")
            for a, b in ref["gaps"] or []:
                ref_marks += mark(a, b, "ref-gap", f"Ref {a+1:,}–{b:,} · {b-a:,} N")
        bands = []
        for band in track["bands"]:
            v, q, n = band["ref"], band["q"], band["bp"]
            points = f"{pct(v)},0 {pct(v+n)},0 {pct(q+n)},1 {pct(q)},1"
            bands.append(f'<polygon points="{points}"><title>Ref {v+1:,}–{v+n:,} → q0 {q+1:,}–{q+n:,} · {esc(band["via"])}</title></polygon>')
        parts = []
        for seg in track["parts"]:
            a, b, kind = seg["start"], seg["end"], seg["kind"]
            if kind == "source":
                tip = f"{seg['dataset']} / {seg['name']}:{seg['source_start']+1:,}–{seg['source_end']:,} ({seg['strand']}) · q0 {a+1:,}–{b:,}"
                parts.append(mark(a, b, "ctg", tip, colors[seg["dataset"]]))
            else:
                parts.append(mark(a, b, {"input_assembly_gap": "input-gap", "reference_unknown": "unknown-gap", "unspecified_gap": "unspecified-gap"}[kind], f"{kind} · q0 {a+1:,}–{b:,} · {b-a:,} N"))
        note = ""
        if track["status"] == "not_constructed":
            note = bi("q0 未构建", "q0 not constructed")
        elif track["status"] == "layout_only":
            note = bi("仅有路径；未记录对应比对", "Path only; no recorded alignment")
        elif track["length_bp"] is None:
            note = bi("q0 未记录", "q0 not recorded")
        if ref is None:
            note += " " + bi("参考长度未记录", "Reference length not recorded")
        elif ref["gaps"] is None:
            note += " " + bi("参考 Gap 位置未记录", "Reference gap positions not recorded")
        title = f'<b>{esc(name)}</b><small>Ref {fmt_bp_short(ref["length_bp"] if ref else None)} · q0 {fmt_bp_short(track["length_bp"])}</small>'
        body += [f'<div class="q0-row"><div>{title}<small>{note}</small></div><div class="q0-rails"><div class="q0-rail">{ref_marks}</div>',
                 '<svg class="q0-bands" viewBox="0 0 100 1" preserveAspectRatio="none" aria-hidden="true">' + "".join(bands) + "</svg>",
                 '<div class="q0-rail">' + "".join(parts) + "</div></div></div>"]
    body.append('<small class="muted">' + bi("上：Ref；下：q0。连带为已选来源片段向参考的证据投影；没有对应区间时不连线。",
        "Top: Ref; bottom: q0. Ribbons project selected source evidence onto the reference; absent anchors are not connected.") + "</small>")
    return section("alignment-q0", "03", "初始路径 q0", "Initial path q0", "".join(body))
