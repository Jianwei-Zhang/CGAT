"""08 is a replaceable overlay; never bake manual batches into the automatic receipt."""
import json

try:
    from render_final_story import STYLE as PREVIEW_STYLE, _part
    from render_gap_story import STYLE as GAP_STYLE, SCRIPT as GAP_SCRIPT
    from render_path_story import section
    from render_refinement_report import badge_bi, bi, esc, fmt_bp_short
    from render_repair_story import DIALOG
    from render_terminal_story import _axis, _rect
    from report_gap_story import NAMES, tool_order
    from report_manual_story import REASONS
except ModuleNotFoundError:
    from .render_final_story import STYLE as PREVIEW_STYLE, _part
    from .render_gap_story import STYLE as GAP_STYLE, SCRIPT as GAP_SCRIPT
    from .render_path_story import section
    from .render_refinement_report import badge_bi, bi, esc, fmt_bp_short
    from .render_repair_story import DIALOG
    from .render_terminal_story import _axis, _rect
    from .report_gap_story import NAMES, tool_order
    from .report_manual_story import REASONS


OUTCOMES = {
    'closed': ('闭合', 'Closed'), 'extended': ('已延伸', 'Extended'),
    'no_candidate': ('未产生候选', 'No candidate'), 'rejected': ('候选未接纳', 'Candidate rejected'),
    'failed': ('执行失败', 'Execution failed'), 'missing_reads': ('缺少 reads', 'Reads missing'),
    'partial': ('未闭合', 'Unclosed'),
}

MANUAL_STYLE = """<style>
.manual-head-bar{display:flex;align-items:center;justify-content:space-between;gap:.5rem 1rem;flex-wrap:wrap;margin:0 0 .55rem;font-size:.8rem}
.manual-batch-picker{display:inline-flex;align-items:center;gap:.4rem;font-size:.81rem;color:var(--text-secondary)}
.manual-batch-picker select{padding:.22rem .5rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-primary);font:600 .8rem/1.25 var(--font-mono)}
.manual-locus-bar{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;padding:.45rem .85rem .15rem}
.manual-locus-lbl{font-size:.75rem;color:var(--text-muted);font-weight:600}
.manual-legacy-row{padding:.38rem .55rem;border-bottom:1px solid var(--border-subtle);font-size:.83rem}
#manual-refinement .final-axis,#manual-refinement .final-preview-row>summary,#manual-refinement .preview-detail-row{grid-template-columns:196px minmax(0,1fr)}
@media (max-width:760px){
  #manual-refinement .final-axis,#manual-refinement .final-preview-row>summary,#manual-refinement .preview-detail-row{grid-template-columns:124px minmax(0,1fr)}
}
</style>"""


def outcome(value):
    return bi(*OUTCOMES[value]) if value in OUTCOMES else esc(value)


def safe_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def _terminal(sc, retained):
    before = sc['before']
    after = sc['after']
    ax = _axis(*before)
    span = retained['start'], retained['end']
    lo = min(span[0], after[0]) if after else span[0]
    hi = max(span[1], after[1]) if after else span[1]
    bx = _axis(lo, hi)
    view = (
        '<text x="8" y="29" font-size="11" font-weight="600" fill="var(--text-secondary)">Export</text>'
        + _rect(before, ax, 20, 'var(--border-strong)', h=10)
        + '<text x="8" y="76" font-size="11" font-weight="600" fill="var(--text-primary)">Batch</text>'
        + _rect(span, bx, 67, 'var(--border-strong)', h=10)
    )
    if after:
        view += _rect(after, bx, 66, 'var(--gen-patch)', h=12)
    tone = ' is-ok' if after else ''
    result = (
        bi('原端保留，延伸片段已纳入本批 FASTA。', 'Original end retained; the extension was included in this batch FASTA.')
        if after else bi('本批未接纳末端延伸。', 'No extension was admitted at this end.')
    )
    details = []
    for r in sc['attempts']:
        p = r['patch']
        msg = REASONS.get(r['reason'])
        details.append(
            '<p><b>DEGAP / TelSeeker</b> · ' + outcome(r['status'])
            + (' · ' + bi(*msg) if msg else '')
            + (f' · {p["length"]:,} bp · <code>{esc(p["sha256"][:12])}</code>' if p else '')
            + '</p>'
        )
    return (
        f'<div class="story-plot-frame"><svg class="repair-zoom" viewBox="0 0 800 96" role="img" aria-label="App endpoint and batch result">{view}</svg></div>'
        '<div class="story-meta-strip">'
        f'<span>{bi("上轨：App 导出时末端", "Top: endpoint at App export")} <code>[{before[0]:,}, {before[1]:,})</code></span>'
        f'<span>{bi("下轨：本批实际路径", "Bottom: path in batch FASTA")} <code>[{lo:,}, {hi:,})</code></span>'
        '</div>'
        + ''.join(details)
        + f'<div class="story-verdict{tone}">{result}</div>'
    )


def _gap(sc, n):
    attempts = []
    tools = []
    cells = []
    for r in sc['attempts']:
        attempts.append(dict(r, message=REASONS.get(r['reason'])))
        tools.append([NAMES[r['tool']], r['status'], None])
        cells.append(['closed' if r['status'] == 'closed' else 'retained' if r['status'] in ('no_candidate', 'rejected', 'partial') else 'unknown'])
    return dict(manual=dict(selected=sc['selected'], winnerName=NAMES.get(sc['selected']), after=sc['after'], attempts=attempts),
                tools=tools, chr=[[sc['chr'], n, [[sc['target'], *sc['before'], cells]]]])


def _batch(batch, number):
    story = batch['story']
    dom = f'manual-{number}'
    tracks = story['tracks']
    templates = []
    body = []
    if tracks is None:
        body.append('<p class="muted">' + bi('旧任务未保存可核对的完整导出路径；不使用自动结果代画。', 'No verifiable complete export snapshot. The automatic path is not substituted.') + '</p>')
        if not story.get('legacy_verified'):
            body.append('<p class="muted">' + bi('未取得与该批次匹配的结果包，不列出未经核对的位点。', 'No matching return bundle could be verified; unverified locus outcomes are omitted.') + '</p>')
        for r in story['legacy']:
            location = ' · '.join(esc(x) for x in (r.get('chr'), r.get('target')) if x)
            body.append('<div class="manual-legacy-row">' + location + (' · ' if location else '') + esc(NAMES.get(r['tool'], r['tool'])) + ' · ' + outcome(r['status']) + '</div>')
        return ''.join(body)
    domain = max([1, *(max(c['length'], c['original_length']) for c in tracks)])
    scenes = story['loci']
    keys = {lid: f'{dom}-locus-{i}' for i, lid in enumerate(scenes)}
    colors = {k: i % 6 for i, k in enumerate(dict.fromkeys(m[0] for c in tracks for p in c['before'] for m in p['members']))}

    legend_bits = [f'<span class="legend-item"><i class="swatch" style="background:var(--ds-{col})"></i>{esc(ds)}</span>' for ds, col in colors.items()]
    legend_bits.append('<span class="legend-item"><i class="swatch" style="background:var(--gen-closed)"></i>' + bi('本批已闭合 / 延伸', 'Admitted closure / extension') + '</span>')
    legend_bits.append('<span class="legend-item"><i class="swatch is-orig-gap"></i>' + bi('未闭合 Gap', 'Unclosed gap') + '</span>')
    body.append('<div class="story-toolbar"><div class="legend-row" style="margin:0">' + ''.join(legend_bits) + '</div></div>')
    body.append(
        '<div class="final-frame is-no-zoom"><div class="final-axis"><span>' + bi('染色体', 'Chromosome') + '</span><span class="story-ruler">'
        + ''.join(f'<span>{esc(fmt_bp_short(round(domain * i / 4)))}</span>' for i in range(5))
        + '</span></div><div class="final-preview-list">'
    )

    for c in tracks:
        def attributes(lid):
            key = keys[lid]
            return 'data-story-open="' + key + '"' + (' data-manual-gap="' + key + '-data"' if scenes[lid]['kind'] == 'gap' else '')

        def rail(parts):
            boxes = []
            for p in parts:
                a, b = p['start'], p['end']
                if a == b:
                    continue  # Direct join: the inspector can show the cut, but there is no new path segment.
                changed = p.get('adopted')
                attr = attributes(p['loci'][0]) if p['loci'] and (changed or p['kind'] == 'gap') else ''
                if not p['members']:
                    desc = f'{p["id"]} · [{a:,}, {b:,})' + (' · ' + NAMES[scenes[p['loci'][0]]['selected']] if changed else '')
                    cls = 'adopted refined' if changed else 'path-gap'
                    shade = 'background:var(--gen-closed);' if changed else ''
                    boxes.append(_part(a, b, domain, cls, desc, attrs=attr, shade=shade))
                else:
                    x = a
                    for ds, name, u, v, strand in p['members']:
                        y = x + v - u
                        desc = f'{ds} / {name} ({strand}) [{u:,}, {v:,}) → [{x:,}, {y:,})'
                        boxes.append(_part(x, y, domain, 'adopted', desc, shade=f'background:var(--ds-{colors[ds]});'))
                        x = y
            return '<span class="preview-rail">' + ''.join(boxes) + '</span>'

        note = bi(f'{c["changed"]} 处改动', f'{c["changed"]} edits') if c['changed'] else bi('与导出时一致', 'Unchanged since export')
        title = f'<span class="preview-heading"><strong class="preview-chr-name">{esc(c["chr"])}</strong><small class="preview-chr-len">{esc(fmt_bp_short(c["length"]))} · {note}</small></span>'
        links = []
        retained = {p['id']: p for p in c['after'] if not p['adopted']}
        for lid in c['loci']:
            sc = scenes[lid]
            key = keys[lid]
            gap = sc['kind'] == 'gap'
            name = sc['target'] if gap else ('5′' if sc['kind'] == 'tel_left' else '3′')
            title_text = f'{c["chr"]} · {name}'
            links.append(f'<button type="button" class="ctrl-btn" {attributes(lid)}>{esc(name)}</button>')
            content = '<div data-gap-inspector></div>' if gap else _terminal(sc, retained[sc['target']])
            templates.append(f'<template id="{key}" data-title="{esc(title_text)}">{content}</template>')
            if gap:
                templates.append(f'<script type="application/json" id="{key}-data">{safe_json(_gap(sc, c["original_length"]))}</script>')
        detail_tracks = ''.join(
            '<div class="preview-detail-row"><span class="preview-track-lbl">' + label + '</span>' + rail(parts) + '</div>'
            for label, parts in ((bi('App 导出时', 'At App export'), c['before']), (bi('本批接纳后', 'After this batch'), c['after']))
        )
        locus_bar = ('<div class="manual-locus-bar"><span class="manual-locus-lbl">' + bi('任务位点：', 'Task loci:') + '</span>' + ''.join(links) + '</div>') if links else ''
        body.append(
            '<details class="final-preview-row"><summary>' + title + rail(c['after']) + '</summary>'
            '<div class="preview-expanded">' + detail_tracks + locus_bar + '</div></details>'
        )
    body.append('</div></div>')
    return ''.join(body + templates)


def _manual_timing_bar(tool_timing):
    if not isinstance(tool_timing, dict) or not tool_timing:
        return ''
    def _dur(s):
        v = max(0.0, float(s or 0.0))
        if v >= 3600:
            h = int(v // 3600); m = int(round((v - h * 3600) / 60.0))
            return f'{h}h {m}m' if m else f'{h}h'
        return f'{v / 60.0:.1f}m' if v >= 60 else (f'{v:.0f}s' if v >= 10 else f'{v:.1f}s')
    def _mem(mb):
        v = float(mb)
        return f'{v / 1024.0:.2f} GB' if v >= 1024.0 else f'{v:.0f} MB'
    bits = []
    for tkey in sorted(tool_timing, key=lambda k: (tool_order(k), k)):
        rec = tool_timing[tkey]
        if not isinstance(rec, dict):
            continue
        sec = rec.get('elapsed_seconds')
        rss = rec.get('peak_rss_mb')
        if sec is None and rss is None:
            continue
        name = NAMES.get(tkey, tkey)
        parts = []
        if sec is not None:
            parts.append(_dur(sec))
        if rss is not None and float(rss) > 0:
            parts.append(_mem(rss))
        bits.append(f'<span class="badge tone-neutral"><b>{esc(name)}</b> {esc(" · ".join(parts))}</span>')
    if not bits:
        return ''
    return '<div class="manual-locus-bar" style="margin:.15rem 0 .45rem"><span class="manual-locus-lbl">' + bi('工具耗时与内存：', 'Per-tool runtime:') + '</span>' + ''.join(bits) + '</div>'


def manual_card(batches, base=''):
    if not batches:
        return ''
    options = []
    panels = []
    for i, b in enumerate(batches):
        if 'story' not in b:
            b = dict(b, story=dict(tracks=None, loci={}, legacy=[], legacy_verified=False))
        full = esc(b['batch_sha256'])
        short = esc(b['batch_sha256'][:12])
        if b['story'].get('legacy_verified') is False:
            status = badge_bi('结果包未核对', 'Return bundle unverified', 'warn')
        elif b['report_status'] == 'pending_app_import':
            status = badge_bi('有补丁，待导回 App', 'Pending App import', 'info')
        else:
            status = badge_bi('无可导回补丁', 'No patch to import', 'neutral')
        options.append(f'<option value="{i}" title="{full}">{short}</option>')
        timing_bar = _manual_timing_bar(b.get('tool_timing'))
        panels.append(
            f'<div data-manual-batch="{i}"' + (' hidden' if i else '') + '>'
            f'<div class="manual-head-bar">{status}<span class="muted">{bi("基线是该批导出时的 App 路径；纳入本批 FASTA 不等于已导回 App。", "Baseline: App path at this export; inclusion in batch FASTA does not mean imported into App.")}</span></div>'
            + timing_bar + _batch(b, i) + '</div>'
        )
    chooser = (
        '<label class="manual-batch-picker">' + bi('导出批次', 'Export batch') + ' <select data-manual-select>' + ''.join(options) + '</select></label>'
        if len(batches) > 1 else f'<code title="{full}">{short}</code>'
    )
    base_head = base.partition('<!-- CGAT:MANUAL_REFINEMENT_SECTION:START -->')[0]
    num = '09' if 'id="auto-refinement"' in base_head else ('08' if 'id="final-path"' in base_head else '01')
    shared = (
        ('' if 'id="path-event-dialog"' in base_head else DIALOG)
        + ('' if 'data-gap-story-ui="1"' in base_head else '<template id="gap-svg-seed"><svg></svg></template>' + GAP_STYLE + GAP_SCRIPT)
        + ('' if '.final-preview-row' in base_head else PREVIEW_STYLE)
        + MANUAL_STYLE
    )
    return section('manual-refinement', num, '手动精修', 'Manual Refinement', shared + ''.join(panels) + SCRIPT.replace('__NUM__', num), right=chooser)


SCRIPT = '''<script data-cgat-ui="1">(()=>{const card=document.getElementById('manual-refinement'),select=card.querySelector('[data-manual-select]');if(select)select.addEventListener('change',()=>{for(const p of card.querySelectorAll('[data-manual-batch]'))p.hidden=p.dataset.manualBatch!==select.value});card.addEventListener('click',e=>{if(e.target.closest('summary [data-story-open]'))e.preventDefault()});const nav=document.querySelector('.wb-sidebar .wb-toc');if(nav&&!nav.querySelector('[href="#manual-refinement"]')){const a=document.createElement('a');a.href='#manual-refinement';const n=document.createElement('span');n.className='toc-num';n.textContent='__NUM__';const wrap=document.createElement('span');for(const [lang,text] of [['zh','手动精修'],['en','Manual Refinement']]){const s=document.createElement('span');s.className='t-'+lang;s.textContent=text;wrap.append(s)}a.append(n,wrap);const li=document.createElement('li');li.append(a);nav.append(li)}})();</script>'''
