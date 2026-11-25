"""Read-only, offline Final Path story cards. Only consume the public report projection."""
from __future__ import annotations

if __package__:
    from .render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_int, table
else:
    from render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_int, table


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
