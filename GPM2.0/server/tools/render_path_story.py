"""Read-only, offline Final Path story cards. Only consume the public report projection."""
from __future__ import annotations

if __package__:
    from .render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_bp_short, fmt_int, table
else:
    from render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_bp_short, fmt_int, table


def section(key, num, zh, en, body, *, sub_zh=None, sub_en=None, right=""):
    sub = f'<span class="story-sub">{bi(sub_zh, sub_en or sub_zh)}</span>' if sub_zh else ""
    extra = f'<div class="panel-head-right">{right}</div>' if right else ""
    return (
        f'<section class="panel path-story" id="{key}">'
        f'<div class="panel-head story-head">'
        f'<h2><small class="story-num">{esc(num)}</small><span>{bi(zh, en)}</span>{sub}</h2>'
        f'{extra}</div>{body}</section>'
    )


INPUT_STYLE = """<style>
.input-ref-band{display:flex;align-items:center;justify-content:space-between;gap:.45rem 1.25rem;flex-wrap:wrap;padding:.55rem .85rem;margin-bottom:.65rem;border:1px solid var(--border-subtle);border-left:3px solid var(--brand);border-radius:var(--radius-sm);background:var(--brand-soft);font-size:.85rem}
.input-ref-main{display:flex;align-items:baseline;gap:.45rem .85rem;flex-wrap:wrap}
.input-ref-role{font-size:.76rem;font-weight:700;letter-spacing:.02em;color:var(--brand)}
.input-ref-name{font:700 .9rem/1.2 var(--font-mono);color:var(--text-primary)}
.input-ref-stat{color:var(--text-secondary);font-variant-numeric:tabular-nums}
.input-ref-note{font-size:.79rem;color:var(--text-muted)}
.input-table th.num-col,.input-table td.num-col{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.input-ds-cell{display:inline-flex;align-items:center;gap:.48rem;font-weight:600;color:var(--text-primary)}
.input-aux-bar{display:flex;align-items:center;gap:.4rem .9rem;flex-wrap:wrap;margin-top:.55rem;padding-top:.5rem;border-top:1px dashed var(--border-subtle);font-size:.81rem;color:var(--text-secondary)}
.input-aux-lbl{font-size:.76rem;font-weight:700;color:var(--text-muted);margin-right:.15rem}
.input-aux-item{display:inline-flex;align-items:center;gap:.3rem}
.input-aux-item::before{content:"";width:4px;height:4px;border-radius:50%;background:var(--border-strong)}
.input-aux-bar>.input-aux-lbl+.input-aux-item::before{display:none}
</style>"""

ASSIGN_STYLE = """<style>
details.assign-help{margin:0 0 .6rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
details.assign-help>summary{display:inline-flex;align-items:center;gap:.45rem;width:100%;padding:.42rem .72rem;cursor:pointer;list-style:none;font-size:.82rem;font-weight:600;color:var(--accent)}
details.assign-help>summary::-webkit-details-marker{display:none}
details.assign-help>summary:hover{background:var(--surface-hover)}
.assign-qmark{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:50%;border:1px solid var(--accent);font:700 11px/1 var(--font-mono);flex-shrink:0}
.assign-help-cut{margin-left:auto;font-weight:500;color:var(--text-secondary);font-variant-numeric:tabular-nums}
.assign-help-body{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:.85rem;align-items:center;padding:.65rem .8rem;border-top:1px solid var(--border-subtle);background:var(--surface-panel);font-size:.82rem;color:var(--text-secondary)}
.assign-help-svg{display:block;width:100%;max-width:300px;height:auto}
#multi-members-only{position:absolute;opacity:0;pointer-events:none}
.assign-filter-lbl{display:inline-flex;align-items:center;gap:.38rem;margin:0 0 .55rem;padding:.24rem .62rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-subtle);color:var(--text-secondary);font-size:.8rem;font-weight:500;cursor:pointer;user-select:none}
.assign-filter-lbl::before{content:"";width:12px;height:12px;border:1.5px solid var(--border-strong);border-radius:3px;background:var(--surface-panel)}
#multi-members-only:checked+.assign-filter-lbl{border-color:var(--brand);background:var(--brand-soft);color:var(--brand);font-weight:600}
#multi-members-only:checked+.assign-filter-lbl::before{border-color:var(--brand);background:var(--brand);box-shadow:inset 0 0 0 2px var(--surface-panel)}
#multi-members-only:focus-visible+.assign-filter-lbl{outline:2px solid var(--focus-ring);outline-offset:2px}
#multi-members-only:checked~.chr-members .member:not(.multi),#multi-members-only:checked~.chr-members .member-source:not(.multi){display:none}
.chr-members{border:1px solid var(--border-subtle);border-radius:var(--radius-sm);overflow:hidden;background:var(--surface-panel)}
details.chr-group-row{border-bottom:1px solid var(--border-subtle)}
details.chr-group-row:last-child{border-bottom:0}
details.chr-group-row>summary{display:flex;align-items:center;justify-content:space-between;gap:.65rem;padding:.48rem .75rem;cursor:pointer;list-style:none;font-size:.84rem;transition:background .12s}
details.chr-group-row>summary::-webkit-details-marker{display:none}
details.chr-group-row>summary:hover{background:var(--surface-subtle)}
.chr-group-name{display:inline-flex;align-items:center;gap:.45rem;font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary)}
.chr-group-name::before{content:"▸";font-size:10px;color:var(--text-muted);transition:transform .12s}
details.chr-group-row[open]>summary .chr-group-name::before{transform:rotate(90deg)}
.chr-group-meta{display:inline-flex;align-items:center;gap:.45rem;font-size:.79rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.chr-group-body{padding:.55rem .8rem .65rem 1.65rem;border-top:1px solid var(--border-subtle);background:var(--surface-subtle)}
.member-source{display:flex;align-items:baseline;gap:.45rem .65rem;flex-wrap:wrap;margin:.25rem 0;font-size:.82rem}
.member-ds{font-weight:600;color:var(--text-secondary);min-width:4.5rem}
.member-list{display:flex;flex-wrap:wrap;gap:.32rem .42rem;flex:1;min-width:0}
.chr-members .member{display:inline-flex;align-items:center;gap:.3rem;padding:.12rem .46rem;border:1px solid var(--border-subtle);border-radius:3px;background:var(--surface-panel);font:500 .8rem/1.3 var(--font-mono);color:var(--text-primary)}
.chr-members .member.multi{border-color:var(--tone-info-line);background:var(--tone-info-bg);color:var(--tone-info-ink)}
.chr-members .multi small{padding:.02rem .28rem;border-radius:2px;background:var(--surface-panel);color:var(--tone-info-ink);font:600 .7rem/1.2 sans-serif}
@media (max-width:680px){.assign-help-body{grid-template-columns:1fr}.chr-group-body{padding-left:.85rem}}
</style>"""


def input_card(inputs):
    missing = '<span class="muted">' + bi("未记录", "Not recorded") + '</span>'

    def measure(st, key, formatter):
        return esc(formatter(st[key])) if st.get(key) is not None else missing

    refs = []
    for ref in inputs["reference"]:
        st = ref["stats"]
        refs.append(
            '<div class="input-ref-band">'
            '<div class="input-ref-main">'
            f'<span class="input-ref-role">{bi("参考基因组", "Reference")}</span>'
            f'<strong class="input-ref-name">{esc(ref["name"])}</strong>'
            f'<span class="input-ref-stat">{measure(st, "sequence_count", fmt_int)} {bi("条序列", "sequences")}</span>'
            f'<span class="input-ref-stat">{measure(st, "length_bp", fmt_bp)}</span>'
            '</div>'
            f'<span class="input-ref-note">{bi("比对与染色体定位的坐标参照", "Coordinate reference for alignment and placement")}</span>'
            '</div>'
        )
    headers = [
        (bi("候选组装", "Candidate assembly"), ""),
        (bi("序列数", "Sequences"), ' class="num-col"'),
        (bi("总长", "Total length"), ' class="num-col"'),
        (bi("序列 N50", "Sequence N50"), ' class="num-col"'),
        (bi("Gap 数（连续 N ≥100 bp）", "Gaps (N runs ≥100 bp)"), ' class="num-col"'),
    ]
    thead = "<thead><tr>" + "".join(f"<th{cls}>{h}</th>" for h, cls in headers) + "</tr></thead>"
    if inputs["assemblies"]:
        body_rows = []
        for index, assembly in enumerate(inputs["assemblies"]):
            st = assembly["stats"]
            ds_cell = f'<span class="input-ds-cell"><i class="swatch" style="background:var(--ds-{index % 6})"></i>{esc(assembly["name"])}</span>'
            vals = [measure(st, "sequence_count", fmt_int), measure(st, "length_bp", fmt_bp),
                    measure(st, "n50_bp", fmt_bp), measure(st, "gap_count", fmt_int)]
            body_rows.append("<tr><td>" + ds_cell + "</td>" + "".join(f'<td class="num-col">{v}</td>' for v in vals) + "</tr>")
        tbody = "<tbody>" + "".join(body_rows) + "</tbody>"
    else:
        tbody = f'<tbody><tr><td colspan="5" class="muted">{missing}</td></tr></tbody>'
    grid = f'<div class="table-wrap"><table class="input-table">{thead}{tbody}</table></div>'

    aux = [f'<span class="input-aux-item">{esc({"hifi": "HiFi", "ont": "ONT", "reads": "Reads"}[r["technology"]])}: <b class="num">{r["file_count"]}</b> '
           + bi("个文件", "files") + '</span>' for r in inputs["typed_reads"]]
    for key, zh, en in (("telomere_rules", "端粒规则", "Telomere rules"), ("centromere_reference", "着丝粒参考", "Centromere reference")):
        if (inputs["annotations"].get(key) or {}).get("configured") is True:
            aux.append('<span class="input-aux-item">' + bi(zh, en) + ": " + bi("已配置", "configured") + '</span>')
    aux_html = ('<div class="input-aux-bar"><span class="input-aux-lbl">' + bi("辅助输入", "Auxiliary inputs") + '</span>'
                + "".join(aux) + '</div>') if aux else ""
    ref_html = "".join(refs) or f'<div class="input-ref-band">{missing}</div>'
    return section("inputs", "01", "输入数据", "Inputs", INPUT_STYLE + ref_html + grid + aux_html)


def assignment_card(assignment):
    threshold = assignment.get("min_coverage_percent")
    cut = (bi("本次阈值未记录", "Run threshold not recorded") if threshold is None else
           bi(f"本次阈值 {threshold:g}%", f"Run threshold {threshold:g}%"))
    # A teaching schematic, not a measured alignment. No example bp or inferred run threshold.
    drawing = (
        '<svg class="assign-help-svg" viewBox="0 0 288 82" role="img" aria-label="Union coverage schematic / 并集覆盖示意">'
        '<text x="4" y="25" font-size="11" font-weight="600" fill="var(--text-primary)">ctg</text>'
        '<text x="4" y="69" font-size="11" font-weight="600" fill="var(--text-secondary)">ref_chr</text>'
        '<path d="M74 11V7H156V11 M172 11V7H226V11" stroke="var(--ds-1)" stroke-width="1.4" fill="none"/>'
        '<rect x="52" y="18" width="224" height="9" rx="2" fill="var(--surface-muted)" stroke="var(--border-default)"/>'
        '<rect x="74" y="18" width="82" height="9" fill="var(--ds-1)"/>'
        '<rect x="172" y="18" width="54" height="9" fill="var(--ds-1)"/>'
        '<path d="M74 27L88 60H142L126 27Z M112 27L132 60H174L156 27Z M172 27L190 60H244L226 27Z" fill="var(--ds-1)" opacity=".26"/>'
        '<rect x="52" y="60" width="224" height="9" rx="2" fill="var(--border-strong)"/>'
        '</svg>'
    )
    rule = (
        '<details class="assign-help">'
        '<summary><span class="assign-qmark" aria-hidden="true">?</span>'
        + bi("分配依据", "Assignment rule")
        + f'<span class="assign-help-cut">{cut}</span></summary>'
        '<div class="assign-help-body">'
        + drawing
        + '<div><p>'
        + bi(
            "示意：将该 ctg 对该 ref_chr 的合格比对区间在 ctg 上取并集（重叠区间不重复计数），覆盖长度除以整条 ctg 长度。达到本次阈值即入组；同一条 ctg 可同时进入多个组。",
            "Schematic: take the union of qualifying query intervals on the contig (overlapping hits counted once) and divide by full contig length. Every chromosome meeting the run threshold forms a group; one contig may belong to multiple groups.",
        )
        + f' · <b>{cut}</b></p></div></div></details>'
    )
    groups = assignment.get("groups")
    if groups is None:
        return section("chr-groups", "02", "染色体分组", "Chromosome groups",
                       ASSIGN_STYLE + rule + '<p class="muted">' + bi("未记录完整的分组成员表", "Complete membership table unavailable") + "</p>",
                       right=cut)
    result = []
    has_multi = False
    for group in groups:
        sources = []
        group_multi = 0
        for source in group["sources"]:
            members = []
            source_multi = False
            for member in source["members"]:
                multi = member["multi"]
                source_multi |= multi
                if multi:
                    group_multi += 1
                label = esc(member["name"])
                if multi:
                    label += " <small>" + bi("多组", "multi-group") + "</small>"
                members.append(f'<span class="member{" multi" if multi else ""}">{label}</span>')
            has_multi |= source_multi
            sources.append(
                f'<div class="member-source{" multi" if source_multi else ""}">'
                f'<span class="member-ds">{esc(source["dataset"])}</span>'
                f'<div class="member-list">' + "".join(members) + "</div></div>"
            )
        count = group["member_count"]
        multi_lbl = bi(f"多组 {group_multi}", f"{group_multi} multi") if group_multi else ""
        multi_tag = f'<span class="badge tone-info">{multi_lbl}</span>' if group_multi else ""
        count_txt = bi(f"{count} 个成员", f"{count} member" + ("" if count == 1 else "s"))
        empty_txt = '<span class="muted">' + bi("无成员", "No members") + '</span>'
        body_inner = "".join(sources) or empty_txt
        result.append(
            '<details class="chr-group-row">'
            f'<summary><span class="chr-group-name">{esc(group["chr"])}</span>'
            f'<span class="chr-group-meta">{multi_tag}<span>{count_txt}</span></span></summary>'
            f'<div class="chr-group-body">{body_inner}</div>'
            '</details>'
        )
    # The checkbox filters names only: chromosome totals always describe the complete dataset.
    toggle = ('<input id="multi-members-only" type="checkbox">'
              '<label class="assign-filter-lbl" for="multi-members-only">'
              + bi("只看多组成员", "Only multi-group members") + "</label>" if has_multi else "")
    grp_lbl = bi(f"{len(groups)} 个参考组", f"{len(groups)} ref groups")
    head_right = f"{grp_lbl} · {cut}"
    return section("chr-groups", "02", "染色体分组", "Chromosome groups",
                   ASSIGN_STYLE + rule + toggle
                   + '<div class="chr-members">' + ("".join(result) or ('<p class="muted" style="padding:.6rem .8rem">' + bi("无已记录的染色体组", "No recorded chromosome groups") + '</p>')) + "</div>",
                   right=head_right)


def q0_card(lgz):
    tracks = lgz.get("q0_scene")
    if not tracks:
        return section("alignment-q0", "03", "初始路径 q0", "Initial path q0",
                       '<p class="muted">' + bi(
                           "没有可核对的完整 q0 路径与定位证据，不绘制推测比对。",
                           "No verified complete q0 selection is available; alignments have not been inferred.",
                       ) + "</p>")
    domain = max([1] + [max(t["length_bp"] or 0, (t["ref"] or {}).get("length_bp", 0)) for t in tracks])
    sources = [d["name"] for d in lgz["inputs"]["assemblies"]]
    sources.extend(sorted({p["dataset"] for t in tracks for p in t["parts"] if p["kind"] == "source"} - set(sources)))
    colors = {ds: f"var(--ds-{i % 6})" for i, ds in enumerate(sources)}

    def pct(pos):
        return format(100 * pos / domain, ".10g")

    def mark(a, b, kind, tip, color=None):
        style = f"left:{pct(a)}%;width:{pct(b-a)}%" + (f";background:{color}" if color else "")
        return f'<span class="q0-mark {kind}" style="{style}" data-start="{a}" data-end="{b}" title="{esc(tip)}"></span>'

    style = """<style>
.q0-axis,.q0-row{display:grid;grid-template-columns:148px 30px minmax(0,1fr);gap:.55rem;align-items:center}
.q0-axis{padding:0 0 .32rem;border-bottom:1px solid var(--border-default);color:var(--text-muted);font-size:.76rem}
.q0-row{padding:.62rem 0;border-bottom:1px solid var(--border-subtle)}
.q0-row:last-of-type{border-bottom:1px solid var(--border-default)}
.q0-chr-meta{min-width:0}
.q0-chr-meta b{display:block;font:600 .86rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.q0-chr-meta small{display:block;margin-top:.12rem;font-size:.76rem;color:var(--text-muted);font-variant-numeric:tabular-nums;line-height:1.35}
.q0-chr-meta small.q0-warn{color:var(--tone-warn-ink);font-weight:500}
.q0-role-col{display:flex;flex-direction:column;justify-content:space-between;height:44px;font:600 .7rem/1 var(--font-mono);color:var(--text-muted);text-align:right;user-select:none}
.q0-rails{position:relative;overflow:hidden;padding:1px 0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.q0-rail{position:relative;height:10px;border-radius:2px}
.q0-mark{position:absolute;display:block;height:100%;border-radius:1.5px}
.q0-mark.ctg{min-width:3px;box-shadow:inset 0 0 0 .6px rgba(255,255,255,.45)}
.q0-mark.ref,.q0-key.is-ref{background:var(--border-strong);box-shadow:inset 0 0 0 1px rgba(15,23,42,.14)}
.q0-mark.input-gap,.q0-mark.ref-gap,.q0-key.input-gap{background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 4px);z-index:1}
.q0-mark.unknown-gap,.q0-key.unknown-gap{background:var(--gen-gap);z-index:1}
.q0-mark.unspecified-gap{background:var(--gen-unfilled);z-index:1}
.q0-bands{width:100%;height:24px;display:block;color:var(--ds-1);fill:currentColor;fill-opacity:.24}
.q0-bands polygon{transition:fill-opacity .1s}
.q0-bands polygon:hover{fill-opacity:.58}
.q0-key{display:inline-block;width:11px;height:8px;border-radius:2px;vertical-align:middle;flex-shrink:0}
.q0-key.is-band{background:var(--ds-1);opacity:.38;transform:skewX(-18deg)}
@media (max-width:760px){
  .q0-axis,.q0-row{grid-template-columns:96px 26px minmax(0,1fr);gap:.4rem}
  .q0-chr-meta b{font-size:.8rem}
}
</style>"""
    legend = [
        '<span class="legend-item"><i class="q0-key is-ref"></i>Ref</span>',
        *[f'<span class="legend-item"><i class="q0-key" style="background:{color}"></i>{esc(ds)}</span>' for ds, color in colors.items()],
        '<span class="legend-item"><i class="q0-key is-band"></i>' + bi("证据投影带", "Projected anchor") + "</span>",
        '<span class="legend-item"><i class="q0-key input-gap"></i>' + bi("原有 Gap", "Original gap") + "</span>",
        '<span class="legend-item"><i class="q0-key unknown-gap"></i>' + bi("新增占位 N", "New placeholder Ns") + "</span>",
    ]
    body = [
        style,
        '<div class="story-toolbar"><div class="legend-row" style="margin:0">' + "".join(legend) + "</div></div>",
        '<div class="q0-axis"><small>' + bi("共用比例尺", "Shared scale") + '</small><span></span><small class="story-ruler">'
        + "".join(f"<span>{esc(fmt_bp_short(round(domain * i / 4)))}</span>" for i in range(5)) + "</small></div>",
    ]
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
        notes = []
        if track["status"] == "not_constructed":
            notes.append(bi("q0 未构建", "q0 not constructed"))
        elif track["status"] == "layout_only":
            notes.append(bi("仅有路径；未记录对应比对", "Path only; no recorded alignment"))
        elif track["length_bp"] is None:
            notes.append(bi("q0 未记录", "q0 not recorded"))
        if ref is None:
            notes.append(bi("参考长度未记录", "Reference length not recorded"))
        elif ref["gaps"] is None:
            notes.append(bi("参考 Gap 位置未记录", "Reference gap positions not recorded"))
        note_html = f'<small class="q0-warn">{" · ".join(notes)}</small>' if notes else ""
        title = (f'<div class="q0-chr-meta"><b>{esc(name)}</b>'
                 f'<small>Ref {esc(fmt_bp_short(ref["length_bp"] if ref else None))} · q0 {esc(fmt_bp_short(track["length_bp"]))}</small>'
                 f'{note_html}</div>')
        roles = '<div class="q0-role-col" aria-hidden="true"><span>Ref</span><span>q0</span></div>'
        body += [
            f'<div class="q0-row">{title}{roles}<div class="q0-rails"><div class="q0-rail">{ref_marks}</div>',
            '<svg class="q0-bands" viewBox="0 0 100 1" preserveAspectRatio="none" aria-hidden="true">' + "".join(bands) + "</svg>",
            '<div class="q0-rail">' + "".join(parts) + "</div></div></div>",
        ]
    body.append('<p class="story-foot">' + bi(
        "上轨 Ref、下轨 q0 均按同一 bp/像素绘制；连带为已选来源片段向参考坐标的证据投影（非 q0 直接重比对），Gap 按真实坐标绘制不放大。",
        "Top: Ref; bottom: q0 on one shared bp/pixel scale. Ribbons project verified source-to-reference anchors (not a direct q0 realignment); gaps keep true coordinates without inflation.",
    ) + "</p>")
    return section("alignment-q0", "03", "初始路径 q0", "Initial path q0", "".join(body),
                   sub_zh="Ref ↔ q0 证据投影", sub_en="Ref ↔ q0 projection",
                   right=bi(f"最大跨度 {fmt_bp_short(domain)}", f"Scale {fmt_bp_short(domain)}"))
