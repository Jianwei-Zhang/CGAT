"""Inline, read-only project-style preview. Coordinates always use the shared bp ruler."""
from collections import defaultdict
import heapq

try:
    from render_path_story import section, zoom_button
    from render_refinement_report import bi, esc, copy_btn, fmt_bp_short
    from report_gap_story import NAMES, tool_order
except ModuleNotFoundError:
    from .render_path_story import section, zoom_button
    from .render_refinement_report import bi, esc, copy_btn, fmt_bp_short
    from .report_gap_story import NAMES, tool_order


def _style(a, b, n):
    return f'left:{100*a/n:.9g}%;width:{100*(b-a)/n:.9g}%;'


def _part(a, b, n, css, title, *, attrs='', shade=''):
    button = bool(attrs)
    tag = 'button' if button else 'span'
    attr = (' type="button" ' + attrs if button else '')
    return f'<{tag}{attr} class="preview-part {css}" title="{esc(title)}" aria-label="{esc(title)}" style="{_style(a, b, n)}{shade}"></{tag}>'


def _track(name_html, inner, *, raw_name=False):
    lbl = name_html if raw_name else esc(name_html)
    return f'<div class="preview-detail-row"><span class="preview-track-lbl">{lbl}</span><div class="preview-rail">{inner}</div></div>'


def _row(c, domain, ref, idx, colors, tool_label=None, suppressed_gids=None):
    title = c['chr']
    n = c['length']
    suppressed = suppressed_gids or set()
    upper = []
    # Group collinear adopted slices of the same source contig so split internal
    # gaps render on one source body instead of repeating duplicate rows.
    grouped = defaultdict(list)
    for p in c['parts']:
        a, b = p['start'], p['end']
        src = p['source']
        edit = p['edit']
        is_partial_edit = bool(edit and p.get('gaps') and any(g in suppressed for g in p['gaps']))
        if is_partial_edit:
            desc = f'{title} [{a:,}, {b:,}) · {b-a:,} bp · gap (unclosed)'
            upper.append(_part(a, b, domain, 'path-gap', desc))
            continue
        attr = ''
        desc = f'{title} [{a:,}, {b:,}) · {b-a:,} bp'
        k = p['kind']
        key = src['dataset'] if src else None
        if src:
            x, y = src['span']
            disp_key = (tool_label or key) if edit and key.startswith('cgat_refinement_') else key
            name = f'{disp_key} / {src["name"]} ({src["strand"]}) [{x:,}, {y:,})'
            desc += ' · ' + name
            if edit:
                desc += ' · ' + edit + ' · ' + ', '.join(p['gaps'])
        else:
            desc += ' · ' + k
        if edit and p['gaps'] and p['gaps'][0] in idx:
            ci, gi, ti = idx[p['gaps'][0]]
            attr = f'data-story-open="auto-gap-inspector" data-gap-chr="{ci}" data-gap-index="{gi}" data-tool-index="{ti}"'
        color = 'var(--gen-unfilled)' if k == 'gap' else ('var(--gen-patch)' if edit else f'var(--ds-{colors[key]})')
        shade = '' if k == 'gap' else f'background:{color};'
        upper.append(_part(a, b, domain, 'adopted refined' if edit and k != 'gap' else 'adopted' if k != 'gap' else 'path-gap', desc, attrs=attr, shade=shade))
        if not src:
            continue
        full = src['length']
        offset = x if src['strand'] == '+' else (full - y if full else 0)
        start, end = (max(0, a - offset), min(domain, a - offset + full)) if full else (a, b)
        label_txt = src['name'] + (' →' if src['strand'] == '+' else ' ←')
        buckets = grouped[key, bool(edit)]
        if (buckets and buckets[-1]['ctg'] == (src['name'], src['strand'])
                and buckets[-1]['last_b'] <= a and not (edit and buckets[-1]['has_edit'])):
            g = buckets[-1]
            g['start'] = min(g['start'], start)
            g['end'] = max(g['end'], end)
            g['last_b'] = b
            g['slices'].append((a, b, desc, shade, attr))
        else:
            buckets.append({
                'ctg': (src['name'], src['strand']),
                'start': start,
                'end': end,
                'last_b': b,
                'full': full,
                'shade': shade,
                'label': label_txt,
                'has_edit': bool(edit),
                'slices': [(a, b, desc, shade, attr)],
            })

    rows = []
    if ref:
        rows.append(_track(
            'Ref',
            _part(0, ref['length_bp'], domain, 'ref-body', f'Ref · {title} · {ref["length_bp"]:,} bp')
            + ''.join(_part(a, b, domain, 'path-gap', f'Ref gap [{a:,}, {b:,})', shade='') for a, b in (ref.get('gaps') or [])),
        ))
    else:
        rows.append(_track('Ref', '<span class="muted">' + bi('未记录参考坐标', 'Reference coordinates unavailable') + '</span>'))

    for (dataset, is_patch), items in sorted(grouped.items()):
        lanes = []
        ends = []
        for item in sorted(items, key=lambda r: (r['start'], r['end'])):
            start, end = item['start'], item['end']
            if ends and ends[0][0] <= start:
                _, lane = heapq.heappop(ends)
            else:
                lane = len(lanes)
                lanes.append([])
            if item['full']:
                tip_body = f'{dataset} / {item["ctg"][0]} ({item["ctg"][1]}) · ctg {item["full"]:,} bp'
                lanes[lane].append(_part(start, end, domain, 'source-body', tip_body, shade=item['shade']))
            for a, b, desc, shade, attr in item['slices']:
                lanes[lane].append(_part(a, b, domain, 'adopted refined' if is_patch else 'adopted', desc, attrs=attr, shade=shade))
            lanes[lane].append(f'<span aria-hidden="true" class="preview-label" style="{_style(start, end, domain)}"><span>{esc(item["label"])}</span></span>')
            heapq.heappush(ends, (end, lane))
        dot_col = 'var(--gen-patch)' if is_patch else f'var(--ds-{colors[dataset]})'
        disp_ds = (tool_label or dataset) if is_patch and dataset.startswith('cgat_refinement_') else dataset
        lbl_html = f'<i class="swatch" style="width:8px;height:8px;background:{dot_col};margin-right:.35rem"></i>{esc(("＋ " if is_patch else "") + disp_ds)}'
        for lane in lanes:
            rows.append(_track(lbl_html, ''.join(lane), raw_name=True))

    heading = f'<strong class="preview-chr-name">{esc(title)}</strong><small class="preview-chr-len">{esc(fmt_bp_short(n))}</small>'
    return (
        '<details class="final-preview-row">'
        f'<summary><span class="preview-heading">{heading}</span><span class="preview-rail">{"".join(upper)}</span></summary>'
        f'<div class="preview-expanded">{"".join(rows)}</div></details>'
    )


def final_card(vm):
    if vm['meta']['mode'] in ('manual_only', 'lgz_failed'):
        return ''
    tools = sorted(vm['refinement_summary']['tools'], key=lambda r: tool_order(r['tool']))
    auto = bool(tools)
    versions = vm.get('final_versions')
    num = '08' if auto else '07'
    refs = vm['lgz_summary'].get('reference_tracks', {})
    ids = defaultdict(list)
    for g in vm['refinement_summary'].get('original_loci', []):
        ids[g['chromosome']].append(g['gap_id'])
    index = {gid: (ci, gi) for ci, gids in enumerate(ids.values()) for gi, gid in enumerate(gids)}
    if versions is None:
        return section('final-path', num, 'Final Path', 'Final Path',
                       '<p class="muted">' + bi('此旧报告未记录可核对的交付路径。', 'No verified delivery path was recorded in this report model.') + '</p>')
    if not versions:
        return section('final-path', num, 'Final Path', 'Final Path',
                       '<p class="muted">' + (bi('本批没有已验证的自动精修交付。', 'No verified refined version was published in this batch.') if auto else bi('本批未记录可核对的 LGZ 成品。', 'No verified LGZ delivery recorded for this run.')) + '</p>')
    domain = max([1, *[r['length_bp'] for r in refs.values()], *[c['length'] for v in versions for c in (v['tracks'] or [])]])
    colors = {k: i % 6 for i, k in enumerate(dict.fromkeys([r['name'] for r in vm['lgz_summary']['inputs']['assemblies']] + [p['source']['dataset'] for v in versions for c in v['tracks'] or [] for p in c['parts'] if p['source'] and not p['edit']]))}

    legend_bits = [f'<span class="legend-item"><i class="swatch" style="background:var(--ds-{c})"></i>{esc(ds)}</span>' for ds, c in colors.items()]
    if auto:
        legend_bits.append('<span class="legend-item"><i class="swatch" style="background:var(--gen-patch)"></i>' + bi('精修补入', 'Refined patch') + '</span>')
    legend_bits.append('<span class="legend-item"><i class="swatch is-orig-gap"></i>Gap</span>')

    ruler = (
        '<div class="final-axis"><span>' + bi('染色体', 'Chromosome') + '</span><span class="story-ruler">'
        + ''.join(f'<span>{esc(fmt_bp_short(round(domain * i / 4)))}</span>' for i in range(5))
        + '</span></div>'
    )

    panels = []
    opts = []
    single_name = ''
    for i, v in enumerate(versions):
        tool = v['tool']
        tool_disp = NAMES.get(tool, tool)
        name = 'LGZ + ' + tool_disp if auto else 'LGZ-only'
        single_name = name
        opts.append(f'<option value="{i}">{esc(name)}</option>')
        idx = {k: (*pair, next(j for j, t in enumerate(tools) if t['tool'] == tool)) for k, pair in index.items()} if auto else {}
        tool_rec = next((t for t in tools if t['tool'] == tool), None) if auto else None
        suppressed_gids = {
            gid for gid, dec in ((tool_rec or {}).get('gap_decisions') or {}).items()
            if dec.get('state') == 'partial'
        }
        closed_count = (
            sum(1 for dec in (tool_rec.get('gap_decisions') or {}).values() if dec.get('state') == 'closed')
            if tool_rec and tool_rec.get('gap_decisions') else v['edits']
        )
        note = bi('FASTA · 服务器路径', 'FASTA · Server path') if v['absolute'] else bi('FASTA · 工作区相对路径', 'FASTA · Workspace-relative path')
        path = (
            '<div class="final-fasta">'
            f'<span class="final-fasta-lbl">{note}</span>'
            f'<code class="final-fasta-code">{esc(v["fasta"])}</code>'
            + copy_btn(v['fasta'], zh='复制路径', en='Copy path')
            + '</div>'
        )
        unchanged = '<p class="muted" style="margin:.35rem 0">' + bi('本版本未接纳完整闭合编辑，沿用 LGZ 序列。', 'No closed gap edits were admitted; the LGZ sequence was retained.') + '</p>' if closed_count == 0 else ''
        v_tracks = v['tracks'] or []
        chr_count = len(v_tracks)
        tot_bp = sum(c['length'] for c in v_tracks)
        tot_gaps = sum(1 for c in v_tracks for p in c['parts'] if p['kind'] == 'gap')
        meta_bits = []
        if chr_count:
            meta_bits.append(bi(f'{chr_count} 条染色体', f'{chr_count} chrs'))
            meta_bits.append(bi(f'总长 {fmt_bp_short(tot_bp)}', f'total {fmt_bp_short(tot_bp)}'))
            meta_bits.append(bi(f'{tot_gaps} Gap', f'{tot_gaps} gaps'))
        chr_lbl = ' · '.join(meta_bits)
        sub_bar = (
            '<div class="final-subhead">'
            f'<div class="final-subhead-left"><strong>{bi("假分子预览", "Pseudomolecule preview")}</strong>'
            + (f'<span class="muted">{chr_lbl}</span>' if chr_lbl else '')
            + '</div>'
            f'<div class="legend-row" style="margin:0">{"".join(legend_bits)}</div></div>'
        )
        if v['tracks']:
            zbtn = zoom_button(f"{num} Final Path · 放大视图", f"{num} Final Path · Enlarged view")
            tracks = (
                '<div class="final-frame" data-zoom-frame="1">' + ruler
                + '<div class="final-preview-list">' + ''.join(_row(c, domain, refs.get(c['chr']), idx, colors, tool_disp, suppressed_gids) for c in v['tracks']) + '</div>'
                + zbtn + '</div>'
            )
        else:
            tracks = '<p class="muted">' + bi('已验证 FASTA，未取得可核对的完整片段坐标，不绘制推测路径。', 'FASTA verified; a complete segment track is unavailable in this record.') + '</p>'
        if v.get('geometry_note') == 'source_extents_unverified':
            tracks = '<p class="muted">' + bi('来源 ctg 总长未通过核对，只绘制已采用的区间。', 'Source contig lengths were not verified; only adopted intervals are drawn.') + '</p>' + tracks
        panels.append(f'<div class="final-version" data-version-panel="{i}"' + (' hidden' if i else '') + '>' + path + unchanged + sub_bar + tracks + '</div>')

    right_ctrl = (
        '<label class="final-ver-switch">' + bi('交付版本', 'Published version') + ' <select data-final-version>' + ''.join(opts) + '</select></label>'
        if len(opts) > 1 else (f'<span class="badge tone-neutral">{esc(single_name)}</span>' if auto else '')
    )
    sub_zh = "LGZ 自动构建" if not auto else None
    sub_en = "LGZ-only" if not auto else None
    return section('final-path', num, 'Final Path', 'Final Path', STYLE + ''.join(panels) + SCRIPT,
                   sub_zh=sub_zh, sub_en=sub_en, right=right_ctrl)


STYLE = '''<style>
.final-version[hidden]{display:none}
.final-ver-switch{display:inline-flex;align-items:center;gap:.4rem;font-size:.81rem;color:var(--text-secondary)}
.final-ver-switch select{padding:.22rem .5rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-primary);font:600 .8rem/1.25 inherit}
.final-fasta{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin:0 0 .75rem;padding:.48rem .65rem;border:1px solid var(--border-subtle);border-radius:var(--radius-sm);background:var(--surface-subtle)}
.final-fasta-lbl{font-size:.8rem;font-weight:600;color:var(--text-secondary);white-space:nowrap}
.final-fasta-code{flex:1 1 220px;min-width:0;padding:.24rem .55rem;border:1px solid var(--border-subtle);border-radius:3px;background:var(--surface-panel);font-size:.8rem;overflow-wrap:anywhere}
.final-fasta .copy-btn{padding:.26rem .68rem;border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-weight:600;font-size:.79rem}
.final-fasta .copy-btn:hover{filter:brightness(.97)}
.final-subhead{display:flex;align-items:center;justify-content:space-between;gap:.5rem 1rem;flex-wrap:wrap;margin:.2rem 0 .55rem}
.final-subhead-left{display:inline-flex;align-items:baseline;gap:.55rem;font-size:.88rem;flex-wrap:wrap}
.final-subhead-left .muted{font-size:.8rem}
.final-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.final-frame.is-no-zoom{padding-bottom:0}
.final-axis,.final-preview-row>summary,.preview-detail-row{display:grid;grid-template-columns:168px minmax(0,1fr);align-items:center;gap:.75rem}
.final-axis{padding:.52rem .85rem .44rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600}
.final-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:.75rem}
.final-preview-list{border-bottom:0}
.final-preview-row{border-bottom:1px solid var(--border-subtle)}
.final-preview-row:last-child{border-bottom:0}
.final-preview-row>summary{cursor:pointer;list-style:none;padding:.44rem .85rem;min-height:2.2rem;transition:background .12s}
.final-preview-row>summary::-webkit-details-marker{display:none}
.final-preview-row>summary:hover,.final-preview-row[open]>summary{background:var(--surface-subtle)}
.preview-heading{display:flex;align-items:baseline;justify-content:space-between;gap:.35rem;min-width:0;white-space:nowrap;overflow:hidden}
.preview-chr-name{display:inline-flex;align-items:center;gap:.36rem;font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis}
.preview-chr-name::before{content:'▸';font-size:10px;color:var(--text-muted);flex-shrink:0}
.final-preview-row[open]>summary .preview-chr-name::before{content:'▾'}
.preview-chr-len{color:var(--text-muted);font-size:.75rem;font-variant-numeric:tabular-nums;flex-shrink:0}
.preview-rail{position:relative;display:block;height:20px;min-width:0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.preview-part{position:absolute;display:block;top:3px;height:14px;border:0;padding:0;border-radius:2px}
.preview-part.adopted{min-width:6px;z-index:1;box-shadow:inset 0 0 0 .7px rgba(255,255,255,.5)}
.preview-part.ref-body{background:var(--ctg-ref-fill);box-shadow:inset 0 0 0 1px var(--ctg-ref-stroke);height:12px;top:4px;opacity:1}
.preview-part.source-body{opacity:.22;height:14px;top:3px}
.preview-part.path-gap{min-width:5px;background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px);box-shadow:inset 0 0 0 1px var(--border-strong);z-index:2}
.preview-part:is(button){cursor:pointer}
.preview-part.refined{min-width:6px;height:16px;top:2px;outline:1.2px solid var(--text-primary);z-index:3}
.preview-part[data-story-open]::after{content:"";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:max(100%,14px);height:max(100%,18px)}
.preview-expanded{padding:.4rem .85rem .55rem;border-top:1px dashed var(--border-subtle);background:var(--surface-subtle)}
.preview-label{container-type:inline-size;position:absolute;inset-block:0;display:flex;align-items:center;justify-content:center;pointer-events:none;overflow:hidden;z-index:3}
.preview-label>span{display:none;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;font:600 .69rem/1.15 var(--font-mono);background:rgba(255,255,255,.86);color:var(--text-primary);padding:0 .22em;border-radius:2px;max-width:92%}
html[data-theme="dark"] .preview-label>span{background:rgba(15,20,25,.82)}
@container (min-width:5.5rem){.preview-label>span{display:inline-block}}
.preview-detail-row{font-size:.78rem;color:var(--text-secondary);min-height:1.55rem}
.preview-track-lbl{display:inline-flex;align-items:center;padding-left:.85rem;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.story-zoom-stage .final-frame{border:0;border-radius:0;padding-bottom:0;overflow:visible;min-width:100%;width:calc(100% * var(--chart-scale, 1))}
.story-zoom-stage .final-axis,.story-zoom-stage .final-preview-row>summary,.story-zoom-stage .preview-detail-row{grid-template-columns:196px minmax(0,1fr);gap:0;padding:0;align-items:stretch}
.story-zoom-stage .final-axis{position:sticky;top:0;z-index:8;background:var(--surface-subtle)}
.story-zoom-stage .final-axis>:first-child{position:sticky;left:0;z-index:9;background:var(--surface-subtle);padding:.55rem .7rem .45rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;align-items:center}
.story-zoom-stage .final-axis .story-ruler{margin:.55rem 1rem .45rem .8rem;min-width:0}
.story-zoom-stage .preview-heading{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding:.62rem .7rem .62rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);align-items:center}
.story-zoom-stage .final-preview-row>summary:hover .preview-heading,.story-zoom-stage .final-preview-row[open]>summary .preview-heading{background:var(--surface-subtle)}
.story-zoom-stage .preview-expanded{padding:0}
.story-zoom-stage .preview-track-lbl{position:sticky;left:0;z-index:5;background:var(--surface-subtle);padding:.35rem .7rem .35rem 1.4rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12)}
.story-zoom-stage .preview-rail{margin:.5rem 1rem .5rem .8rem;height:24px;z-index:1}
.story-zoom-stage .preview-expanded .preview-rail{margin:.25rem 1rem .25rem .8rem}
.story-zoom-stage .preview-part{top:3px;height:18px}
.story-zoom-stage .preview-part.adopted{min-width:7px}
.story-zoom-stage .preview-part.path-gap{min-width:6px}
.story-zoom-stage .preview-part.ref-body{height:14px;top:5px}
.story-zoom-stage .preview-part.refined{height:20px;top:2px;min-width:7px}
@media (max-width:760px){
  .final-axis,.final-preview-row>summary,.preview-detail-row{grid-template-columns:108px minmax(0,1fr);gap:.45rem;padding-left:.65rem;padding-right:.65rem}
  .preview-expanded{padding:.35rem .65rem .45rem}
  .preview-chr-name{font-size:.79rem}
  .preview-chr-len{font-size:.71rem}
  .preview-track-lbl{padding-left:.4rem}
  .story-zoom-stage .final-axis,.story-zoom-stage .final-preview-row>summary,.story-zoom-stage .preview-detail-row{grid-template-columns:136px minmax(0,1fr);gap:0;padding:0}
}
</style>'''
SCRIPT = '''<script data-cgat-ui="1">(()=>{const card=document.getElementById('final-path'),sel=card.querySelector('[data-final-version]');if(sel)sel.addEventListener('change',()=>{for(const p of card.querySelectorAll('[data-version-panel]'))p.hidden=p.dataset.versionPanel!==sel.value});card.addEventListener('click',e=>{if(e.target.closest('summary [data-story-open]'))e.preventDefault()})})();</script>'''
