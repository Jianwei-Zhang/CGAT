"""Read-only, offline Final Path story cards. Only consume the public report projection."""
from __future__ import annotations

if __package__:
    from .render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_bp_short, fmt_int, table
else:
    from render_refinement_report import bi, disclosure, esc, fmt_bp, fmt_bp_short, fmt_int, table


def section(key, num, zh, en, body, *, sub_zh=None, sub_en=None, title_extra="", right=""):
    sub = f'<span class="story-sub">{bi(sub_zh, sub_en or sub_zh)}</span>' if sub_zh else ""
    extra = f'<div class="panel-head-right">{right}</div>' if right else ""
    return (
        f'<section class="panel path-story" id="{key}">'
        f'<div class="panel-head story-head">'
        f'<h2><small class="story-num">{esc(num)}</small><span>{bi(zh, en)}</span>{sub}{title_extra}</h2>'
        f'{extra}</div>{body}</section>'
    )


INPUT_STYLE = """<style>
.project-dataset-scroll{overflow-x:auto;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel)}
.project-dataset-table{width:100%;border-collapse:collapse;font-size:.875rem;text-align:left}
.project-dataset-table th,.project-dataset-table td{padding:11px 12px;border-top:0;border-bottom:1px solid var(--border-subtle);vertical-align:middle}
.project-dataset-table thead th{background:var(--surface-subtle);color:var(--text-secondary);font-size:.82rem;font-weight:600;white-space:nowrap;border-bottom:1px solid var(--border-subtle)}
.project-dataset-table tbody th[scope="row"]{background:transparent;color:var(--text-primary);font-weight:500;font-size:.875rem;white-space:normal}
.project-dataset-table tbody>tr:hover>td,.project-dataset-table tbody>tr:hover>th{background:var(--surface-subtle)}
.project-dataset-table tbody>tr:last-child>*{border-bottom:0}
.project-dataset-name{display:inline-flex;align-items:center;gap:.45rem;overflow-wrap:anywhere;font-weight:500;color:var(--text-primary)}
.project-dataset-table .numeric{white-space:nowrap;font-variant-numeric:tabular-nums}
.project-dataset-role{display:inline-block;padding:2px 9px;border:1px solid var(--border-default);border-radius:999px;background:var(--brand-soft);color:var(--brand);font-size:.79rem;font-weight:500;line-height:1.4;white-space:nowrap}
.project-dataset-role[data-dataset-role="reference"]{background:var(--ctg-ref-fill);border-color:var(--ctg-ref-stroke);color:var(--ctg-ref-text)}
.project-dataset-role[data-dataset-role="primary"]{background:var(--ctg-primary-fill);border-color:var(--ctg-primary-stroke);color:var(--ctg-primary-text)}
.project-dataset-role[data-dataset-role="support"]{background:var(--ctg-companion-fill);border-color:var(--ctg-companion-stroke);color:var(--ctg-companion-text)}
.input-aux-bar{display:flex;align-items:center;gap:.45rem .55rem;flex-wrap:wrap;margin-top:.65rem;font-size:.8rem;color:var(--text-secondary)}
.input-qc-tag{display:inline-flex;align-items:center;gap:.36rem;padding:3px 10px;border:1px solid var(--border-subtle);border-radius:999px;background:var(--surface-subtle);color:var(--text-secondary);font:500 .79rem/1.35 inherit;white-space:nowrap}
.input-qc-tag.is-enabled{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
button.input-qc-tag.is-clickable{cursor:pointer;transition:background .12s,border-color .12s,box-shadow .12s}
button.input-qc-tag.is-clickable:hover{border-color:var(--gen-closed);box-shadow:0 1px 3px rgba(15,23,42,.08);filter:brightness(.98)}
.input-qc-tag .qc-ico{display:inline-flex;align-items:center;opacity:.75}
.input-ann-note{font-size:.79rem;color:var(--text-secondary);line-height:1.5;max-width:44ch}
.input-ann-motif{display:inline-block;padding:1px 7px;border:1px solid var(--border-default);border-radius:4px;background:var(--surface-subtle);font:600 .8rem/1.35 var(--font-mono);color:var(--text-primary);letter-spacing:.03em}
.input-ann-src{display:inline-block;padding:1px 7px;border-radius:999px;border:1px solid var(--border-subtle);background:var(--surface-muted);color:var(--text-secondary);font-size:.74rem;font-weight:500;white-space:nowrap}
.input-ann-src.is-official{border-color:var(--tone-info-line);background:var(--tone-info-bg);color:var(--tone-info-ink)}
</style>"""

ASSIGN_STYLE = """<style>
.story-help-btn{display:inline-grid;place-items:center;width:20px;height:20px;padding:0;margin-left:.08rem;border-radius:50%;border:1px solid var(--border-default);background:var(--surface-subtle);color:var(--text-muted);font:700 11.5px/1 var(--font-mono);cursor:pointer;vertical-align:middle;transition:border-color .12s,background .12s,color .12s}
.story-help-btn:hover{border-color:var(--brand);background:var(--brand-soft);color:var(--brand)}
.assign-rule-grid{display:grid;grid-template-columns:minmax(280px,1.2fr) minmax(240px,1fr);gap:1rem;align-items:stretch;margin-top:.75rem}
.assign-rule-plot{display:flex;flex-direction:column;justify-content:center;padding:.85rem .95rem;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-subtle)}
.assign-help-svg{display:block;width:100%;height:auto}
.assign-rule-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;justify-content:space-between;gap:.5rem;font-size:.82rem;line-height:1.45;color:var(--text-secondary)}
.assign-rule-list li{display:flex;flex-direction:column;gap:.12rem;padding:.5rem .7rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
.assign-rule-list strong{color:var(--text-primary);font-size:.82rem;font-weight:600}
#multi-members-only{position:absolute;opacity:0;pointer-events:none}
.assign-filter-lbl{display:inline-flex;align-items:center;gap:.38rem;margin:0 0 .55rem;padding:.24rem .62rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-subtle);color:var(--text-secondary);font-size:.8rem;font-weight:500;cursor:pointer;user-select:none}
.assign-filter-lbl::before{content:"";width:12px;height:12px;border:1.5px solid var(--border-strong);border-radius:3px;background:var(--surface-panel)}
#multi-members-only:checked+.assign-filter-lbl{border-color:var(--brand);background:var(--brand-soft);color:var(--brand);font-weight:600}
#multi-members-only:checked+.assign-filter-lbl::before{border-color:var(--brand);background:var(--brand);box-shadow:inset 0 0 0 2px var(--surface-panel)}
#multi-members-only:focus-visible+.assign-filter-lbl{outline:2px solid var(--focus-ring);outline-offset:2px}
#multi-members-only:checked~.chr-members .member:not(.multi),#multi-members-only:checked~.chr-members .member-source:not(.multi),#multi-members-only:checked~.chr-members .member-more,#multi-members-only:checked~.chr-members .assign-unassigned-row{display:none}
.assign-table th,.assign-table td{padding:9px 12px}
.assign-chr-name{font:600 .85rem/1.3 var(--font-mono);color:var(--text-primary);white-space:nowrap}
.assign-count-cell{display:inline-flex;align-items:center;gap:.4rem;white-space:nowrap}
.assign-sources{display:flex;flex-direction:column;gap:.32rem}
.member-source{display:flex;align-items:center;gap:.38rem .55rem;flex-wrap:wrap;font-size:.82rem}
.member-ds{display:inline-flex;align-items:center;gap:.34rem;font-weight:600;color:var(--text-secondary);font-size:.8rem;white-space:nowrap}
.member-list{display:flex;flex-wrap:wrap;align-items:center;gap:.28rem .36rem;flex:1;min-width:0}
.chr-members .member{display:inline-flex;align-items:center;gap:.28rem;padding:2px 7px;border:1px solid var(--border-subtle);border-radius:4px;background:var(--surface-subtle);font:500 .79rem/1.3 var(--font-mono);color:var(--text-primary);cursor:default}
.chr-members .member:hover{border-color:var(--border-default);background:var(--surface-panel)}
.chr-members .member.multi{border-color:var(--tone-info-line);background:var(--tone-info-bg);color:var(--tone-info-ink)}
.chr-members .multi small{padding:.02rem .28rem;border-radius:2px;background:var(--surface-panel);color:var(--tone-info-ink);font:600 .7rem/1.2 sans-serif}
.chr-members .member.is-unassigned{border-style:dashed;color:var(--text-secondary);background:transparent}
details.member-more{display:inline-block}
details.member-more>summary{display:inline-flex;align-items:center;padding:2px 8px;border:1px dashed var(--border-default);border-radius:4px;background:var(--surface-panel);color:var(--accent);font-size:.77rem;font-weight:500;cursor:pointer;list-style:none}
details.member-more>summary::-webkit-details-marker{display:none}
details.member-more>summary:hover{border-color:var(--accent);background:var(--brand-soft)}
details.member-more[open]{display:block;flex-basis:100%;margin-top:.2rem}
details.member-more[open]>summary{margin-bottom:.3rem}
.member-more-list{display:flex;flex-wrap:wrap;gap:.28rem .36rem}
tr.assign-unassigned-row>th,tr.assign-unassigned-row>td{background:var(--surface-subtle);border-top:1px dashed var(--border-default)}
.assign-unassigned-badge{display:inline-block;padding:2px 8px;border:1px solid var(--border-default);border-radius:999px;background:var(--surface-panel);color:var(--text-muted);font-size:.78rem;font-weight:500;white-space:nowrap}
.assign-unassigned-note{font-size:.76rem;color:var(--text-muted);margin-left:.25rem}
@media (max-width:680px){.assign-rule-grid{grid-template-columns:1fr}}
</style>"""


def _fmt_catalog_length(value, missing):
    if value is None:
        return missing
    n = int(value)
    if abs(n) >= 1_000_000_000:
        disp = f"{n / 1_000_000_000:,.2f} Gb"
    elif abs(n) >= 1_000_000:
        disp = f"{n / 1_000_000:,.2f} Mb"
    elif abs(n) >= 1_000:
        disp = f"{n / 1_000:,.2f} kb"
    else:
        return esc(f"{n:,} bp")
    raw_bp = f"{n:,} bp"
    return f'<span title="{esc(raw_bp)}">{esc(disp)}</span>'


def _ann_source_badge(source):
    key = str(source or "").strip().lower()
    if key == "official":
        return '<span class="input-ann-src is-official">' + bi("官方库", "Official") + '</span>'
    if key in ("user", "local"):
        return '<span class="input-ann-src">' + bi("用户库", "User library") + '</span>'
    if key:
        return f'<span class="input-ann-src">{esc(source)}</span>'
    return '<span class="muted">—</span>'


def _tel_modal_body(ann):
    items = ann.get("items") or []
    count = ann.get("row_count")
    lead = (
        '<div class="story-verdict" style="margin:0 0 .75rem">'
        + bi(
            "用于在序列末端双向扫描端粒串联重复基序（正链与反向互补链），识别染色体 5′ / 3′ 端粒信号。最小重复次数为 CGAT/GPM 检测阈值。",
            "Scans tandem telomere repeat motifs on both strands (forward and reverse complement) to identify 5′ / 3′ terminal telomere signals. Min repeats is a CGAT/GPM detection threshold.",
        )
        + '</div>'
    )
    if not items:
        cnt_note = (
            bi(f"本次运行配置了 {count:,} 条端粒规则；当前摘要未附带规则明细。", f"{count:,} telomere rule(s) configured; detailed rows were not stored in this summary.")
            if isinstance(count, int) and count > 0
            else bi("已启用端粒规则；当前摘要未附带规则明细。", "Telomere rules configured; detailed rows were not stored in this summary.")
        )
        return lead + f'<p class="muted">{cnt_note}</p>'
    rows_html = []
    for item in items:
        min_rep = item.get("min_repeat")
        rep_txt = f'≥ {min_rep:,}×' if isinstance(min_rep, int) else '—'
        rc_txt = bi("是", "Yes") if item.get("reverse_complement", True) else bi("否", "No")
        note = esc(item["note"]) if item.get("note") else '<span class="muted">—</span>'
        rows_html.append(
            f'<tr><th scope="row"><span class="project-dataset-name">{esc(item.get("id") or "—")}</span></th>'
            f'<td>{_ann_source_badge(item.get("source"))}</td>'
            f'<td><span class="input-ann-motif">{esc(item.get("motif") or "—")}</span></td>'
            f'<td class="numeric">{esc(rep_txt)}</td>'
            f'<td>{rc_txt}</td>'
            f'<td><div class="input-ann-note">{note}</div></td></tr>'
        )
    return (
        lead
        + '<div class="project-dataset-scroll"><table class="project-dataset-table">'
        '<thead><tr>'
        f'<th scope="col">{bi("规则 ID", "Rule ID")}</th>'
        f'<th scope="col">{bi("来源", "Source")}</th>'
        f'<th scope="col">{bi("重复基序", "Motif")}</th>'
        f'<th scope="col">{bi("最小重复", "Min repeats")}</th>'
        f'<th scope="col">{bi("反向互补", "Rev-comp")}</th>'
        f'<th scope="col">{bi("说明与文献出处", "Notes & reference")}</th>'
        '</tr></thead><tbody>' + "".join(rows_html) + '</tbody></table></div>'
    )


def _cen_modal_body(ann):
    items = ann.get("items") or []
    count = ann.get("row_count")
    lead = (
        '<div class="story-verdict" style="margin:0 0 .75rem">'
        + bi(
            "将参考着丝粒重复单体序列比对至染色体，用于标记候选着丝粒区域（仅作候选区域证据，不等同于功能着丝粒实验验证）。",
            "Aligns reference centromeric repeat monomers against chromosomes to mark candidate centromere regions (candidate-region evidence only).",
        )
        + '</div>'
    )
    if not items:
        cnt_note = (
            bi(f"本次运行配置了 {count:,} 条着丝粒参考；当前摘要未附带参考明细。", f"{count:,} centromere reference(s) configured; detailed rows were not stored in this summary.")
            if isinstance(count, int) and count > 0
            else bi("已启用着丝粒参考；当前摘要未附带参考明细。", "Centromere reference configured; detailed rows were not stored in this summary.")
        )
        return lead + f'<p class="muted">{cnt_note}</p>'
    rows_html = []
    for item in items:
        scope = bi("全染色体 (*)", "All (*)") if item.get("chr_name") in (None, "", "*") else f'<code>{esc(item["chr_name"])}</code>'
        mlen = f'{item["length_bp"]:,} bp' if isinstance(item.get("length_bp"), int) else '—'
        thr_bits = []
        if isinstance(item.get("min_len"), int):
            thr_bits.append(f'≥ {item["min_len"]:,} bp')
        if item.get("min_identity"):
            thr_bits.append(f'≥ {item["min_identity"]}%')
        thr_txt = esc(" · ".join(thr_bits)) if thr_bits else '<span class="muted">—</span>'
        note = esc(item["note"]) if item.get("note") else '<span class="muted">—</span>'
        rows_html.append(
            f'<tr><th scope="row"><span class="project-dataset-name">{esc(item.get("id") or "—")}</span></th>'
            f'<td>{_ann_source_badge(item.get("source"))}</td>'
            f'<td>{scope}</td>'
            f'<td class="numeric">{esc(mlen)}</td>'
            f'<td class="numeric">{thr_txt}</td>'
            f'<td><div class="input-ann-note">{note}</div></td></tr>'
        )
    return (
        lead
        + '<div class="project-dataset-scroll"><table class="project-dataset-table">'
        '<thead><tr>'
        f'<th scope="col">{bi("参考 ID", "Reference ID")}</th>'
        f'<th scope="col">{bi("来源", "Source")}</th>'
        f'<th scope="col">{bi("适用范围", "Scope")}</th>'
        f'<th scope="col">{bi("单体长度", "Monomer")}</th>'
        f'<th scope="col">{bi("检出阈值", "Thresholds")}</th>'
        f'<th scope="col">{bi("说明与文献出处", "Notes & reference")}</th>'
        '</tr></thead><tbody>' + "".join(rows_html) + '</tbody></table></div>'
    )


def input_card(inputs):
    missing = '<span class="muted">' + bi("未记录", "Not recorded") + '</span>'

    def measure_int(st, key):
        return esc(fmt_int(st[key])) if st.get(key) is not None else missing

    rows = []
    for ref in inputs["reference"]:
        st = ref["stats"]
        rows.append((
            'reference',
            bi("参考", "Reference"),
            f'<span class="project-dataset-name">{esc(ref["name"])}</span>',
            measure_int(st, "sequence_count"),
            _fmt_catalog_length(st.get("length_bp"), missing),
            _fmt_catalog_length(st.get("n50_bp"), missing),
            _fmt_catalog_length(st.get("n90_bp"), missing),
        ))
    for index, assembly in enumerate(inputs["assemblies"]):
        st = assembly["stats"]
        raw_role = str(assembly.get("role") or "assembly_candidate")
        if raw_role in ("support", "companion") or (raw_role == "assembly_candidate" and index > 0):
            role_attr, role_lbl = "support", bi("辅助组装", "Auxiliary")
        else:
            role_attr, role_lbl = "primary", bi("主组装", "Primary")
        name_html = (
            f'<span class="project-dataset-name">'
            f'<i class="swatch" style="width:8px;height:8px;background:var(--ds-{index % 6})"></i>'
            f'{esc(assembly["name"])}</span>'
        )
        rows.append((
            role_attr,
            role_lbl,
            name_html,
            measure_int(st, "sequence_count"),
            _fmt_catalog_length(st.get("length_bp"), missing),
            _fmt_catalog_length(st.get("n50_bp"), missing),
            _fmt_catalog_length(st.get("n90_bp"), missing),
        ))

    headers = [
        f'<th scope="col">{bi("数据类型", "Data type")}</th>',
        f'<th scope="col">{bi("名称", "Name")}</th>',
        f'<th scope="col">{bi("序列数", "Sequences")}</th>',
        f'<th scope="col">{bi("总长度", "Total length")}</th>',
        '<th scope="col">N50</th>',
        '<th scope="col">N90</th>',
    ]
    thead = "<thead><tr>" + "".join(headers) + "</tr></thead>"
    if rows:
        body_rows = [
            f'<tr><td><span class="project-dataset-role" data-dataset-role="{esc(role_attr)}">{role_lbl}</span></td>'
            f'<th scope="row">{name_html}</th>'
            f'<td class="numeric">{seq_n}</td>'
            f'<td class="numeric">{tot_len}</td>'
            f'<td class="numeric">{n50}</td>'
            f'<td class="numeric">{n90}</td></tr>'
            for role_attr, role_lbl, name_html, seq_n, tot_len, n50, n90 in rows
        ]
        tbody = "<tbody>" + "".join(body_rows) + "</tbody>"
    else:
        tbody = f'<tbody><tr><td colspan="6" class="muted">{missing}</td></tr></tbody>'
    grid = (
        '<div class="project-dataset-scroll" tabindex="0" role="region" aria-label="Datasets">'
        f'<table class="project-dataset-table">{thead}{tbody}</table></div>'
    )

    info_svg = (
        '<span class="qc-ico" aria-hidden="true">'
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/>'
        '<path d="M12 16v-4"/><path d="M12 8h.01"/></svg></span>'
    )
    aux = [f'<span class="input-qc-tag">{esc({"hifi": "HiFi", "ont": "ONT", "reads": "Reads"}[r["technology"]])}: <b class="num">{r["file_count"]}</b> '
           + bi("个文件", "files") + '</span>' for r in inputs["typed_reads"]]
    templates = []
    annotations = inputs.get("annotations") or {}
    for key, zh, en, builder in (
        ("telomere_rules", "端粒规则", "Telomere rules", _tel_modal_body),
        ("centromere_reference", "着丝粒参考", "Centromere reference", _cen_modal_body),
    ):
        ann = annotations.get(key) or {}
        if ann.get("configured") is True:
            tid = f"input-ann-{key}"
            rc = ann.get("row_count")
            cnt_zh = f" · {rc} 条" if isinstance(rc, int) and rc > 0 else " · 已配置"
            cnt_en = f" · {rc}" if isinstance(rc, int) and rc > 0 else " · configured"
            title_zh = f"{zh}（{rc} 条）" if isinstance(rc, int) and rc > 0 else zh
            title_en = f"{en} ({rc})" if isinstance(rc, int) and rc > 0 else en
            aux.append(
                f'<button type="button" class="input-qc-tag is-enabled is-clickable" data-story-open="{tid}">'
                f'{bi(zh + cnt_zh, en + cnt_en)}{info_svg}</button>'
            )
            templates.append(
                f'<template id="{tid}" data-title="{esc(title_zh)}" '
                f'data-title-zh="{esc(title_zh)}" data-title-en="{esc(title_en)}">'
                f'{builder(ann)}</template>'
            )
    aux_html = ('<div class="input-aux-bar">' + "".join(aux) + '</div>') if aux else ""
    count_right = bi(f"{len(rows)} 个数据集", f"{len(rows)} datasets") if rows else ""
    return section("inputs", "01", "输入数据", "Inputs", INPUT_STYLE + grid + aux_html + "".join(templates), right=count_right)


def assignment_card(assignment, *, ref_tracks=None, assemblies=None, funnel=None):
    threshold = assignment.get("min_coverage_percent")
    cut = (bi("本次阈值未记录", "Run threshold not recorded") if threshold is None else
           bi(f"覆盖率阈值 ≥ {threshold:g}%", f"Coverage ≥ {threshold:g}%"))
    # A teaching schematic, not a measured alignment. No example bp or inferred run threshold.
    drawing = (
        '<svg class="assign-help-svg" viewBox="0 0 340 108" role="img" aria-label="Union coverage schematic / 并集覆盖示意">'
        '<text x="148" y="13" text-anchor="middle" font-size="10" font-weight="600" fill="var(--ds-1)">Union</text>'
        '<text x="249" y="13" text-anchor="middle" font-size="10" font-weight="600" fill="var(--ds-1)">Union</text>'
        '<path d="M90 22V17H206V22 M222 22V17H276V22" stroke="var(--ds-1)" stroke-width="1.5" fill="none"/>'
        '<text x="4" y="37" font-size="11.5" font-weight="600" fill="var(--text-primary)">contig</text>'
        '<rect x="58" y="27" width="272" height="12" rx="3" fill="var(--surface-panel)" stroke="var(--border-default)"/>'
        '<rect x="90" y="27" width="116" height="12" rx="2" fill="var(--ds-1)"/>'
        '<rect x="222" y="27" width="54" height="12" rx="2" fill="var(--ds-1)"/>'
        '<path d="M90 39L108 79H176L154 39Z M136 39L162 79H214L206 39Z M222 39L242 79H298L276 39Z" fill="var(--ds-1)" opacity=".24"/>'
        '<path d="M136 39L154 39L164 59L148 59Z" fill="var(--ds-1)" opacity=".22"/>'
        '<text x="4" y="90" font-size="11.5" font-weight="600" fill="var(--text-secondary)">ref_chr</text>'
        '<rect x="58" y="79" width="272" height="12" rx="3" fill="var(--ctg-ref-fill)" stroke="var(--ctg-ref-stroke)"/>'
        '<text x="194" y="104" text-anchor="middle" font-size="9.5" fill="var(--text-muted)">Σ Union / contig length</text>'
        '</svg>'
    )
    rule_btn = (
        '<button type="button" class="story-help-btn" data-story-open="assign-rule-modal" '
        'title="分配依据 / Assignment rule" aria-label="分配依据 / Assignment rule">?</button>'
    )
    rule_modal = (
        '<template id="assign-rule-modal" data-title="分配依据" data-title-zh="分配依据" data-title-en="Assignment Rule">'
        f'<div class="story-verdict" style="margin:0">{cut}</div>'
        '<div class="assign-rule-grid">'
        '<div class="assign-rule-plot">' + drawing + '</div>'
        '<ul class="assign-rule-list">'
        '<li><strong>' + bi("覆盖率", "Coverage") + '</strong><span>'
        + bi("合格比对区间并集长度 ÷ contig 总长（重叠只计一次）。", "Union of qualifying aligned spans ÷ contig length (overlaps counted once).")
        + '</span></li>'
        '<li><strong>' + bi("入组判定", "Grouping") + '</strong><span>'
        + bi("达到阈值即归入该染色体；可同时入多组（标为「多组」）。", "Assigned when meeting the threshold; may belong to multiple groups.")
        + '</span></li>'
        '<li><strong>' + bi("未分配", "Unassigned") + '</strong><span>'
        + bi("仅表示未达过滤或阈值，不等同于污染序列。", "Below alignment filter or threshold; does not imply contamination.")
        + '</span></li>'
        '</ul></div></template>'
    )
    groups = assignment.get("groups")
    if groups is None:
        return section("chr-groups", "02", "染色体分组", "Chromosome groups",
                       ASSIGN_STYLE + '<p class="muted">' + bi("未记录完整的分组成员表", "Complete membership table unavailable") + "</p>" + rule_modal,
                       title_extra=rule_btn, right=cut)

    ds_colors = {
        name: i % 6
        for i, name in enumerate(dict.fromkeys([
            *(a["name"] for a in (assemblies or []) if isinstance(a, dict) and a.get("name")),
            *(s["dataset"] for g in groups for s in g.get("sources", []) if s.get("dataset")),
        ]))
    }
    ref_map = ref_tracks if isinstance(ref_tracks, dict) else {}
    unassigned_obj = assignment.get("unassigned") if isinstance(assignment.get("unassigned"), dict) else None
    unassigned_count = (
        unassigned_obj.get("count")
        if unassigned_obj and isinstance(unassigned_obj.get("count"), int)
        else (funnel.get("unassigned_contigs") if isinstance(funnel, dict) and isinstance(funnel.get("unassigned_contigs"), int) else 0)
    )
    assigned_unique = funnel.get("assigned_unique_contigs") if isinstance(funnel, dict) and isinstance(funnel.get("assigned_unique_contigs"), int) else None

    def _member_chip(ds, member):
        multi = bool(member.get("multi"))
        tip_parts = [f'{ds} / {member["name"]}']
        if isinstance(member.get("length_bp"), int):
            tip_parts.append(f'{fmt_bp_short(member["length_bp"])} ({member["length_bp"]:,} bp)')
        if member.get("orientation") in ("+", "-"):
            tip_parts.append(f'({member["orientation"]})')
        if isinstance(member.get("coverage_percent"), (int, float)):
            tip_parts.append(f'{member["coverage_percent"]:g}%')
        if multi:
            tip_parts.append('multi-group')
        tip = " · ".join(tip_parts)
        label = esc(member["name"])
        if multi:
            label += " <small>" + bi("多组", "multi-group") + "</small>"
        cls = "member multi" if multi else "member"
        return f'<span class="{cls}" title="{esc(tip)}">{label}</span>'

    table_rows = []
    has_multi = False
    for group in groups:
        sources_html = []
        group_multi = 0
        for source in group["sources"]:
            ds = source["dataset"]
            m_list = source["members"]
            source_multi = any(m.get("multi") for m in m_list)
            group_multi += sum(1 for m in m_list if m.get("multi"))
            has_multi |= source_multi
            # Keep all multi-group members visible up front so CSS-only filtering works without opening foldouts.
            if len(m_list) > 8:
                multi_first = [m for m in m_list if m.get("multi")]
                non_multi = [m for m in m_list if not m.get("multi")]
                vis_budget = max(6, len(multi_first))
                visible = multi_first + non_multi[:max(0, vis_budget - len(multi_first))]
                hidden = non_multi[max(0, vis_budget - len(multi_first)):]
            else:
                visible, hidden = m_list, []
            chips = "".join(_member_chip(ds, m) for m in visible)
            if hidden:
                more_lbl = bi(f"+ 其余 {len(hidden)} 条", f"+ {len(hidden)} more")
                chips += (
                    f'<details class="member-more"><summary>{more_lbl}</summary>'
                    f'<div class="member-more-list">' + "".join(_member_chip(ds, m) for m in hidden) + '</div></details>'
                )
            swatch = f'<i class="swatch" style="width:7px;height:7px;background:var(--ds-{ds_colors.get(ds, 0)})"></i>'
            src_cls = "member-source multi" if source_multi else "member-source"
            sources_html.append(
                f'<div class="{src_cls}">'
                f'<span class="member-ds">{swatch}{esc(ds)}</span>'
                f'<div class="member-list">{chips}</div></div>'
            )
        ref_info = ref_map.get(group["chr"])
        ref_len = _fmt_catalog_length(ref_info.get("length_bp") if isinstance(ref_info, dict) else None, '<span class="muted">—</span>')
        count = group["member_count"]
        multi_lbl = bi(f"多组 {group_multi}", f"{group_multi} multi") if group_multi else ""
        multi_tag = f'<span class="badge tone-info">{multi_lbl}</span>' if group_multi else ""
        members_cell = f'<div class="assign-sources">{"".join(sources_html)}</div>' if sources_html else '<span class="muted">' + bi("无成员", "No members") + '</span>'
        table_rows.append(
            f'<tr><th scope="row"><span class="assign-chr-name">{esc(group["chr"])}</span></th>'
            f'<td class="numeric">{ref_len}</td>'
            f'<td class="numeric"><span class="assign-count-cell">{count:,}{multi_tag}</span></td>'
            f'<td>{members_cell}</td></tr>'
        )

    if unassigned_count > 0:
        un_items = (unassigned_obj or {}).get("items") or []
        if un_items:
            by_ds = {}
            for item in un_items:
                by_ds.setdefault(item["dataset"], []).append(item)
            un_sources = []
            for ds, items in by_ds.items():
                swatch = f'<i class="swatch" style="width:7px;height:7px;background:var(--ds-{ds_colors.get(ds, 0)})"></i>'
                chips = []
                for it in items[:8]:
                    tip_bits = [f'{ds} / {it["name"]}']
                    if isinstance(it.get("length_bp"), int):
                        tip_bits.append(f'{fmt_bp_short(it["length_bp"])} ({it["length_bp"]:,} bp)')
                    tip_bits.append("below alignment/coverage threshold")
                    tip_s = " · ".join(tip_bits)
                    chips.append(f'<span class="member is-unassigned" title="{esc(tip_s)}">{esc(it["name"])}</span>')
                if len(items) > 8:
                    extra_chips = "".join(
                        f'<span class="member is-unassigned">{esc(it["name"])}</span>' for it in items[8:]
                    )
                    more_un_lbl = bi(f"+ 其余 {len(items) - 8} 条", f"+ {len(items) - 8} more")
                    chips.append(
                        f'<details class="member-more"><summary>{more_un_lbl}</summary>'
                        f'<div class="member-more-list">{extra_chips}</div></details>'
                    )
                below_lbl = bi("未达覆盖率阈值", "Below threshold")
                un_sources.append(
                    f'<div class="member-source"><span class="member-ds">{swatch}{esc(ds)}</span>'
                    f'<div class="member-list">{"".join(chips)}'
                    f'<span class="assign-unassigned-note">{below_lbl}</span></div></div>'
                )
            un_cell = f'<div class="assign-sources">{"".join(un_sources)}</div>'
        else:
            un_cell = '<span class="muted">' + bi("未通过比对过滤或覆盖率阈值", "Did not pass alignment filter or coverage threshold") + '</span>'
        un_badge = bi("未分配", "Unassigned")
        table_rows.append(
            '<tr class="assign-unassigned-row">'
            f'<th scope="row"><span class="assign-unassigned-badge">{un_badge}</span></th>'
            '<td class="numeric"><span class="muted">—</span></td>'
            f'<td class="numeric">{unassigned_count:,}</td>'
            f'<td>{un_cell}</td></tr>'
        )

    thead = (
        '<thead><tr>'
        f'<th scope="col">{bi("参考染色体", "Reference Chr")}</th>'
        f'<th scope="col">{bi("参考长度", "Ref length")}</th>'
        f'<th scope="col">{bi("成员数", "Members")}</th>'
        f'<th scope="col">{bi("归属成员（按数据集）", "Assigned contigs (by dataset)")}</th>'
        '</tr></thead>'
    )
    empty_row = f'<tr><td colspan="4" class="muted">{bi("无已记录的染色体组", "No recorded chromosome groups")}</td></tr>'
    table_html = (
        '<div class="project-dataset-scroll chr-members" tabindex="0" role="region" aria-label="Chromosome groups">'
        f'<table class="project-dataset-table assign-table">{thead}<tbody>{"".join(table_rows) or empty_row}</tbody></table></div>'
    )

    # The checkbox filters names only: chromosome totals always describe the complete dataset.
    toggle = ('<input id="multi-members-only" type="checkbox">'
              '<label class="assign-filter-lbl" for="multi-members-only">'
              + bi("只看多组成员", "Only multi-group members") + "</label>") if has_multi else ""

    right_bits = [bi(f"{len(groups)} 组", f"{len(groups)} groups")]
    if assigned_unique is not None:
        right_bits.append(bi(f"{assigned_unique:,} 已分配", f"{assigned_unique:,} assigned"))
    if unassigned_count > 0:
        right_bits.append(bi(f"{unassigned_count:,} 未分配", f"{unassigned_count:,} unassigned"))
    right_bits.append(cut)
    return section("chr-groups", "02", "染色体分组", "Chromosome groups",
                   ASSIGN_STYLE + toggle + table_html + rule_modal,
                   title_extra=rule_btn, right=" · ".join(right_bits))


def _q0_visual_offset(track, domain):
    """Compute a bp-weighted median shift so most Ref↔q0 ribbons drop nearly vertically."""
    qlen = track.get("length_bp")
    bands = track.get("bands") or []
    if not isinstance(qlen, int) or qlen <= 0 or not bands:
        return 0
    pairs = sorted((b["ref"] - b["q"], b["bp"]) for b in bands if b.get("bp", 0) > 0)
    if not pairs:
        return 0
    total = sum(w for _, w in pairs)
    acc = 0
    med = 0
    for diff, w in pairs:
        acc += w
        if acc * 2 >= total:
            med = diff
            break
    clamped = max(0, min(med, max(0, domain - qlen)))
    return 0 if clamped < domain * 0.001 else clamped


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

    def mark(a, b, kind, tip, color=None, shift=0):
        style = f"left:{pct(a + shift)}%;width:{pct(b-a)}%" + (f";background:{color}" if color else "")
        return f'<span class="q0-mark {kind}" style="{style}" data-start="{a}" data-end="{b}" title="{esc(tip)}"></span>'

    style = """<style>
.q0-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.q0-axis,.q0-row{display:grid;grid-template-columns:168px 34px minmax(0,1fr);gap:.6rem;align-items:center}
.q0-axis{padding:.52rem .85rem .44rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600}
.q0-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:.75rem}
.q0-row{padding:.68rem .85rem;border-bottom:1px solid var(--border-subtle);transition:background .12s}
.q0-row:last-of-type{border-bottom:0}
.q0-row:hover{background:var(--surface-subtle)}
.q0-chr-meta{min-width:0}
.q0-chr-head{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.q0-chr-meta b{font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.q0-gap-pill{display:inline-flex;align-items:center;padding:1px 6px;border-radius:999px;font-size:.71rem;font-weight:500;font-variant-numeric:tabular-nums;border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-muted);white-space:nowrap}
.q0-gap-pill.is-clean{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.q0-chr-meta small{display:block;margin-top:.16rem;font-size:.75rem;color:var(--text-muted);font-variant-numeric:tabular-nums;line-height:1.35}
.q0-chr-meta small.q0-warn{color:var(--tone-warn-ink);font-weight:500}
.q0-role-col{display:flex;flex-direction:column;justify-content:space-between;height:56px;font:600 .7rem/1.1 var(--font-mono);color:var(--text-muted);text-align:right;user-select:none}
.q0-rails{position:relative;overflow:hidden;padding:1px 0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.q0-rail{position:relative;height:14px;border-radius:2px}
.q0-mark{position:absolute;display:block;height:100%;border-radius:2px}
.q0-mark:hover{filter:brightness(1.08);z-index:4}
.q0-mark.ctg{min-width:6px;z-index:1;box-shadow:inset 0 0 0 .7px rgba(255,255,255,.5)}
.q0-mark.ref,.q0-key.is-ref{background:var(--ctg-ref-fill);box-shadow:inset 0 0 0 1px var(--ctg-ref-stroke)}
.q0-mark.input-gap,.q0-mark.ref-gap,.q0-key.input-gap{min-width:5px;z-index:2;background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px);box-shadow:inset 0 0 0 1px var(--border-strong)}
.q0-mark.unknown-gap,.q0-key.unknown-gap{min-width:5px;z-index:2;background:var(--gen-gap);box-shadow:inset 0 0 0 1px rgba(255,255,255,.55)}
.q0-mark.unspecified-gap{min-width:5px;z-index:2;background:var(--gen-unfilled);box-shadow:inset 0 0 0 1px var(--border-strong)}
.q0-bands{width:100%;height:28px;display:block;color:var(--brand);fill:currentColor;fill-opacity:.18}
.q0-bands polygon{transition:fill-opacity .12s}
.q0-bands polygon:hover{fill-opacity:.52}
.q0-key{display:inline-block;width:11px;height:8px;border-radius:2px;vertical-align:middle;flex-shrink:0}
.q0-key.is-band{background:var(--brand);opacity:.28;transform:skewX(-18deg)}
.q0-zoom-btn{position:absolute;right:10px;bottom:8px;z-index:4;display:inline-flex;align-items:center;gap:.32rem;height:26px;padding:0 8px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-secondary);font:500 .75rem/1 inherit;cursor:pointer;box-shadow:0 1px 3px rgba(15,23,42,.07);transition:border-color .12s,background .12s,color .12s}
.q0-zoom-btn:hover{border-color:var(--brand);background:var(--brand-soft);color:var(--brand)}
.q0-zoom-bar{display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap;margin-bottom:.65rem}
.q0-zoom-ctrl{display:inline-flex;align-items:center;gap:.3rem;font-size:.8rem}
.q0-zoom-ctrl button{display:inline-grid;place-items:center;min-width:28px;height:28px;padding:0 .5rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-subtle);color:var(--text-primary);font:600 .8rem/1 var(--font-mono);cursor:pointer;transition:border-color .12s,background .12s,color .12s}
.q0-zoom-ctrl button:hover:not(:disabled){border-color:var(--brand);background:var(--brand-soft);color:var(--brand)}
.q0-zoom-ctrl button:disabled{opacity:.42;cursor:not-allowed}
.q0-zoom-pct{min-width:44px;text-align:center;font:600 .8rem/1 var(--font-mono);color:var(--text-secondary);font-variant-numeric:tabular-nums}
.q0-zoom-stage{overflow:auto;max-height:72vh;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel)}
.q0-zoom-stage .q0-frame{border:0;border-radius:0;padding-bottom:0;overflow:visible;min-width:100%;width:calc(100% * var(--q0-scale, 1))}
.q0-zoom-stage .q0-axis,.q0-zoom-stage .q0-row{grid-template-columns:186px 40px minmax(0,1fr);gap:.75rem}
.q0-zoom-stage .q0-axis{position:sticky;top:0;z-index:6}
.q0-zoom-stage .q0-axis>:first-child{position:sticky;left:0;z-index:7;background:var(--surface-subtle)}
.q0-zoom-stage .q0-row{padding:.95rem 1rem}
.q0-zoom-stage .q0-chr-meta{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding-right:.45rem}
.q0-zoom-stage .q0-row:hover .q0-chr-meta{background:var(--surface-subtle)}
.q0-zoom-stage .q0-chr-meta b{font-size:.9rem}
.q0-zoom-stage .q0-role-col{height:82px;font-size:.75rem}
.q0-zoom-stage .q0-rail{height:18px}
.q0-zoom-stage .q0-bands{height:46px}
.q0-zoom-stage .q0-mark.ctg{min-width:7px}
.q0-zoom-stage .q0-mark.input-gap,.q0-zoom-stage .q0-mark.ref-gap,.q0-zoom-stage .q0-mark.unknown-gap,.q0-zoom-stage .q0-mark.unspecified-gap{min-width:6px}
@media (max-width:760px){
  .q0-axis,.q0-row{grid-template-columns:104px 26px minmax(0,1fr);gap:.4rem;padding-left:.65rem;padding-right:.65rem}
  .q0-chr-meta b{font-size:.8rem}
}
</style>"""

    has_unknown_gap = any(p["kind"] == "reference_unknown" for t in tracks for p in t["parts"])
    legend = [
        '<span class="legend-item"><i class="q0-key is-ref"></i>Ref</span>',
        *[f'<span class="legend-item"><i class="q0-key" style="background:{color}"></i>{esc(ds)}</span>' for ds, color in colors.items()],
        '<span class="legend-item"><i class="q0-key is-band"></i>' + bi("证据投影带", "Projected anchor") + "</span>",
        '<span class="legend-item"><i class="q0-key input-gap"></i>' + bi("原有 Gap", "Original gap") + "</span>",
    ]
    if has_unknown_gap:
        legend.append('<span class="legend-item"><i class="q0-key unknown-gap"></i>' + bi("新增占位 N", "New placeholder Ns") + "</span>")
    gap_kind_tip = {
        "input_assembly_gap": "原有 Gap / Original gap",
        "reference_unknown": "新增占位 N / Placeholder Ns",
        "unspecified_gap": "未分类 Gap / Gap",
    }
    rows_html = []
    total_q0_bp = 0
    total_gaps = 0
    constructed = 0
    for track in tracks:
        name, ref = track["chr"], track["ref"]
        q_offset = _q0_visual_offset(track, domain)
        ref_marks = ""
        if ref:
            ref_marks = mark(0, ref["length_bp"], "ref", f"Ref · {name} · {ref['length_bp']:,} bp")
            for a, b in ref["gaps"] or []:
                ref_marks += mark(a, b, "ref-gap", f"Ref Gap · {a+1:,}–{b:,} · {b-a:,} N")
        bands = []
        for band in track["bands"]:
            v, q, n = band["ref"], band["q"], band["bp"]
            points = f"{pct(v)},0 {pct(v+n)},0 {pct(q+n+q_offset)},1 {pct(q+q_offset)},1"
            bands.append(f'<polygon points="{points}"><title>Ref {v+1:,}–{v+n:,} → q0 {q+1:,}–{q+n:,} · {esc(band["via"])}</title></polygon>')
        parts = []
        chr_gaps = 0
        for seg in track["parts"]:
            a, b, kind = seg["start"], seg["end"], seg["kind"]
            if kind == "source":
                tip = f"{seg['dataset']} / {seg['name']}:{seg['source_start']+1:,}–{seg['source_end']:,} ({seg['strand']}) · q0 {a+1:,}–{b:,}"
                parts.append(mark(a, b, "ctg", tip, colors[seg["dataset"]], shift=q_offset))
            else:
                chr_gaps += 1
                cls_name = {"input_assembly_gap": "input-gap", "reference_unknown": "unknown-gap", "unspecified_gap": "unspecified-gap"}[kind]
                parts.append(mark(a, b, cls_name, f"{gap_kind_tip[kind]} · q0 {a+1:,}–{b:,} · {b-a:,} N", shift=q_offset))
        if isinstance(track.get("length_bp"), int):
            total_q0_bp += track["length_bp"]
            constructed += 1
        total_gaps += chr_gaps
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
        gap_pill = ""
        if isinstance(track.get("length_bp"), int):
            if chr_gaps == 0:
                gap_pill = f'<span class="q0-gap-pill is-clean">{bi("无 Gap", "0 gaps")}</span>'
            else:
                gap_pill = f'<span class="q0-gap-pill">{bi(f"{chr_gaps} Gap", f"{chr_gaps} gap" + ("s" if chr_gaps != 1 else ""))}</span>'
        ref_len_txt = fmt_bp_short(ref["length_bp"] if ref else None)
        q0_len_txt = fmt_bp_short(track["length_bp"])
        title = (
            f'<div class="q0-chr-meta">'
            f'<div class="q0-chr-head"><b>{esc(name)}</b>{gap_pill}</div>'
            f'<small>Ref {esc(ref_len_txt)} · q0 {esc(q0_len_txt)}</small>'
            f'{note_html}</div>'
        )
        roles = '<div class="q0-role-col" aria-hidden="true"><span>Ref</span><span>q0</span></div>'
        rows_html.append(
            f'<div class="q0-row">{title}{roles}<div class="q0-rails"><div class="q0-rail">{ref_marks}</div>'
            '<svg class="q0-bands" viewBox="0 0 100 1" preserveAspectRatio="none" aria-hidden="true">' + "".join(bands) + "</svg>"
            '<div class="q0-rail">' + "".join(parts) + "</div></div></div>"
        )

    axis_html = (
        '<div class="q0-axis">'
        f'<span>{bi("染色体", "Chromosome")}</span>'
        f'<span class="muted" style="text-align:right;font-weight:500">{bi("轨道", "Track")}</span>'
        '<span class="story-ruler">'
        + "".join(f"<span>{esc(fmt_bp_short(round(domain * i / 4)))}</span>" for i in range(5))
        + "</span></div>"
    )
    zoom_btn = (
        '<button type="button" class="q0-zoom-btn" data-q0-zoom="1" '
        'title="放大查看 / Enlarge view" aria-label="放大查看 / Enlarge view">'
        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/>'
        '<line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>'
        f'<span>{bi("放大", "Zoom")}</span></button>'
    )
    zoom_script = """<script data-cgat-ui="1" data-q0-zoom-ui="1">(()=>{
  document.addEventListener('click',(ev)=>{
    const btn=ev.target.closest('[data-q0-zoom="1"]');
    if(!btn)return;
    const dlg=document.getElementById('path-event-dialog');
    const sec=btn.closest('#alignment-q0');
    const srcFrame=sec&&sec.querySelector('.q0-frame');
    if(!dlg||!srcFrame)return;
    const wrap=document.createElement('div');
    const bar=document.createElement('div');
    bar.className='q0-zoom-bar';
    const srcLegend=sec.querySelector('.legend-row');
    if(srcLegend)bar.appendChild(srcLegend.cloneNode(true));
    const ctrl=document.createElement('div');
    ctrl.className='q0-zoom-ctrl';
    const steps=[1,1.5,2,3,4];
    let idx=0;
    const outBtn=document.createElement('button');outBtn.type='button';outBtn.textContent='−';outBtn.title='Zoom out';
    const pctEl=document.createElement('span');pctEl.className='q0-zoom-pct';pctEl.textContent='100%';
    const inBtn=document.createElement('button');inBtn.type='button';inBtn.textContent='+';inBtn.title='Zoom in';
    const rstBtn=document.createElement('button');rstBtn.type='button';
    const rz=document.createElement('span');rz.className='t-zh';rz.textContent='重置';
    const re=document.createElement('span');re.className='t-en';re.textContent='Reset';
    rstBtn.append(rz,re);
    ctrl.append(outBtn,pctEl,inBtn,rstBtn);
    bar.appendChild(ctrl);
    const stage=document.createElement('div');
    stage.className='q0-zoom-stage';
    const clone=srcFrame.cloneNode(true);
    const cBtn=clone.querySelector('.q0-zoom-btn');
    if(cBtn)cBtn.remove();
    stage.appendChild(clone);
    function applyZoom(){
      const s=steps[idx];
      clone.style.setProperty('--q0-scale',String(s));
      pctEl.textContent=Math.round(s*100)+'%';
      outBtn.disabled=idx<=0;
      inBtn.disabled=idx>=steps.length-1;
      rstBtn.disabled=idx===0;
    }
    outBtn.addEventListener('click',()=>{if(idx>0){idx--;applyZoom();}});
    inBtn.addEventListener('click',()=>{if(idx<steps.length-1){idx++;applyZoom();}});
    rstBtn.addEventListener('click',()=>{idx=0;applyZoom();stage.scrollLeft=0;});
    applyZoom();
    wrap.append(bar,stage);
    dlg.dispatchEvent(new CustomEvent('cgat-open-custom',{detail:{
      trigger:btn,wide:true,
      titleZh:'03 初始路径 q0 · 放大视图',
      titleEn:'03 Initial path q0 · Enlarged view',
      content:wrap
    }}));
  });
})();</script>"""
    frame_html = f'<div class="q0-frame">{axis_html}{"".join(rows_html)}{zoom_btn}</div>'
    body_html = (
        style
        + '<div class="story-toolbar"><div class="legend-row" style="margin:0">' + "".join(legend) + "</div></div>"
        + frame_html
        + zoom_script
    )
    right_bits = [bi(f"{len(tracks)} 条染色体", f"{len(tracks)} chrs")]
    if constructed:
        right_bits.append(bi(f"q0 总长 {fmt_bp_short(total_q0_bp)}", f"q0 {fmt_bp_short(total_q0_bp)}"))
        right_bits.append(bi(f"{total_gaps} Gap", f"{total_gaps} gaps"))
    return section("alignment-q0", "03", "初始路径 q0", "Initial path q0", body_html,
                   right=" · ".join(right_bits))
