"""08 is a replaceable overlay; never bake manual batches into the automatic receipt."""
import json
from render_final_story import STYLE as PREVIEW_STYLE, _part
from render_gap_story import STYLE as GAP_STYLE, SCRIPT as GAP_SCRIPT
from render_refinement_report import bi, esc, fmt_bp_short
from render_repair_story import DIALOG
from render_terminal_story import _axis, _rect
from report_gap_story import NAMES
from report_manual_story import REASONS


OUTCOMES = {
    'closed': ('闭合','Closed'), 'extended': ('已延伸','Extended'),
    'no_candidate': ('未产生候选','No candidate'), 'rejected': ('候选未接纳','Candidate rejected'),
    'failed': ('执行失败','Execution failed'), 'missing_reads': ('缺少 reads','Reads missing'),
    'partial': ('历史部分改动','Historical partial edit'),
}


def outcome(value):
    return bi(*OUTCOMES[value]) if value in OUTCOMES else esc(value)


def safe_json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')


def _terminal(sc, retained):
    before=sc['before']; after=sc['after'];ax=_axis(*before);span=retained['start'],retained['end']
    lo=min(span[0],after[0]) if after else span[0];hi=max(span[1],after[1]) if after else span[1];bx=_axis(lo,hi)
    view=(_rect(before,ax,19,'var(--text-muted)')+_rect(span,bx,70,'var(--text-muted)'))
    if after:
        view+=_rect(after,bx,70,'var(--gen-patch)')
    result=bi('原端保留，延伸片段已纳入本批 FASTA。','Original end retained; the extension was included in this batch FASTA.') if after else bi('本批未接纳末端延伸。','No extension was admitted at this end.')
    details=[]
    for r in sc['attempts']:
        p=r['patch']; msg=REASONS.get(r['reason']);details.append('<p>DEGAP / TelSeeker · '+outcome(r['status'])+(' · '+bi(*msg) if msg else '')+(f' · {p["length"]:,} bp · <code>{esc(p["sha256"][:12])}</code>' if p else '')+'</p>')
    return (f'<p>{result}</p><svg class="repair-zoom" viewBox="0 0 800 95" role="img" aria-label="App endpoint and batch result">{view}</svg>'+
            bi('上轨：App 导出时的末端片段','Top: endpoint at App export')+f' [{before[0]:,}, {before[1]:,})<br>'+bi('下轨：本批实际路径','Bottom: path in the batch FASTA')+f' [{lo:,}, {hi:,})'+''.join(details))


def _gap(sc,n):
    attempts=[];tools=[];cells=[]
    for r in sc['attempts']:
        attempts.append(dict(r,message=REASONS.get(r['reason'])));tools.append([NAMES[r['tool']],r['status'],None])
        cells.append(['closed' if r['status']=='closed' else 'retained' if r['status'] in ('no_candidate','rejected') else 'unknown'])
    return dict(manual=dict(selected=sc['selected'],winnerName=NAMES.get(sc['selected']),after=sc['after'],attempts=attempts),
                tools=tools,chr=[[sc['chr'],n,[[sc['target'],*sc['before'],cells]]]])


def _batch(batch,number):
    story=batch['story']; dom=f'manual-{number}';tracks=story['tracks'];templates=[];body=[]
    if tracks is None:
        body.append('<p>'+bi('旧任务未保存可核对的完整导出路径；不使用自动结果代画。','No verifiable complete export snapshot. The automatic path is not substituted.')+'</p>')
        if not story.get('legacy_verified'):body.append('<p>'+bi('未取得与该批次匹配的结果包，不列出未经核对的位点。','No matching return bundle could be verified; unverified locus outcomes are omitted.')+'</p>')
        for r in story['legacy']:
            location=' · '.join(esc(x) for x in (r.get('chr'),r.get('target')) if x)
            body.append('<div>'+location+(' · ' if location else '')+esc(NAMES.get(r['tool'],r['tool']))+' · '+outcome(r['status'])+'</div>')
        return ''.join(body)
    domain=max(max(c['length'],c['original_length']) for c in tracks);scenes=story['loci'];keys={lid:f'{dom}-locus-{i}' for i,lid in enumerate(scenes)}
    colors={k:i%6 for i,k in enumerate(dict.fromkeys(m[0] for c in tracks for p in c['before'] for m in p['members']))}
    for c in tracks:
        def attributes(lid):
            key=keys[lid];return 'data-story-open="'+key+'"'+(' data-manual-gap="'+key+'-data"' if scenes[lid]['kind']=='gap' else '')
        def rail(parts):
            boxes=[]
            for p in parts:
                a,b=p['start'],p['end']
                if a==b:continue  # Direct join: the inspector can show the cut, but there is no new path segment.
                changed=p.get('adopted');color='var(--gen-patch)' if changed else 'var(--gen-unfilled)' if p['kind']=='gap' else 'var(--text-muted)';attr=attributes(p['loci'][0]) if p['loci'] and (changed or p['kind']=='gap') else ''
                if not p['members']:
                    desc=f'{p["id"]} · [{a:,}, {b:,})'+(' · '+NAMES[scenes[p['loci'][0]]['selected']] if changed else '')
                    boxes.append(_part(a,b,domain,'adopted' if changed else 'path-gap',desc,attrs=attr,shade='background:'+color+';'))
                else:
                    x=a
                    for ds,name,u,v,strand in p['members']:
                        y=x+v-u;desc=f'{ds} / {name} ({strand}) [{u:,}, {v:,}) → [{x:,}, {y:,})';boxes.append(_part(x,y,domain,'adopted',desc,shade=f'background:var(--ds-{colors[ds]});'));x=y
            return '<span class="preview-rail">'+''.join(boxes)+'</span>'
        note=bi(f'{c["changed"]} 处改动',f'{c["changed"]} edits') if c['changed'] else bi('与导出时一致','Unchanged since export')
        title=f'<span class="preview-heading"><strong>{esc(c["chr"])}</strong> <small>{esc(fmt_bp_short(c["length"]))} · {note}</small></span>'
        links=[];retained={p['id']:p for p in c['after'] if not p['adopted']}
        for lid in c['loci']:
            sc=scenes[lid];key=keys[lid];gap=sc['kind']=='gap';name=sc['target'] if gap else ('5′' if sc['kind']=='tel_left' else '3′');title_text=f'{c["chr"]} · {name}'
            links.append(f'<button type="button" {attributes(lid)}>{esc(name)}</button>')
            content='<div data-gap-inspector></div>' if gap else _terminal(sc,retained[sc['target']]);templates.append(f'<template id="{key}" data-title="{esc(title_text)}">{content}</template>')
            if gap: templates.append(f'<script type="application/json" id="{key}-data">{safe_json(_gap(sc,c["original_length"]))}</script>')
        body.append('<details class="final-preview-row"><summary>'+title+rail(c['after'])+'</summary>'+''.join('<div class="preview-detail-row"><span>'+label+'</span>'+rail(parts)+'</div>' for label,parts in ((bi('App 导出时','At App export'),c['before']),(bi('本批接纳后','After this batch'),c['after'])))+('<div class="gap-tools">'+''.join(links)+'</div>' if links else '')+'</details>')
    return ''.join(body+templates)


def manual_card(batches,base=''):
    if not batches:return ''
    options=[];panels=[]
    for i,b in enumerate(batches):
        if 'story' not in b:b=dict(b,story=dict(tracks=None,loci={},legacy=[],legacy_verified=False))
        full=esc(b['batch_sha256']);short=esc(b['batch_sha256'][:12])
        if b['story'].get('legacy_verified') is False:status=bi('结果包未核对','Return bundle unverified')
        elif b['report_status']=='pending_app_import':status=bi('有补丁，待导回 App','Pending App import')
        else:status=bi('无可导回补丁','No patch to import')
        options.append(f'<option value="{i}" title="{full}">{short}</option>')
        panels.append(f'<div data-manual-batch="{i}"'+(' hidden' if i else '')+'>'+status+_batch(b,i)+'</div>')
    chooser='<label>'+bi('导出批次','Export batch')+' <select data-manual-select>'+''.join(options)+'</select></label>' if len(batches)>1 else f'<code title="{full}">{short}</code>'
    base=base.partition('<!-- CGAT:MANUAL_REFINEMENT_SECTION:START -->')[0]
    shared=('' if 'id="path-event-dialog"' in base else DIALOG)+('' if 'data-gap-story-ui="1"' in base else '<template id="gap-svg-seed"><svg></svg></template>'+GAP_STYLE+GAP_SCRIPT)
    return ('<section class="panel" id="manual-refinement"><h2><small>08</small>　'+bi('手动精修','Manual refinement')+'</h2>'+chooser+'<p class="muted">'+bi('基线是该批导出时的 App 路径。纳入本批 FASTA 不等于已导回 App。','Baseline: the App path at this export. Inclusion in a batch FASTA does not mean it was imported into the App.')+'</p>'+PREVIEW_STYLE+''.join(panels)+shared+SCRIPT+'</section>')


SCRIPT='''<script data-cgat-ui="1">(()=>{const card=document.getElementById('manual-refinement'),select=card.querySelector('[data-manual-select]');if(select)select.addEventListener('change',()=>{for(const p of card.querySelectorAll('[data-manual-batch]'))p.hidden=p.dataset.manualBatch!==select.value});card.addEventListener('click',e=>{if(e.target.closest('summary [data-story-open]'))e.preventDefault()});const nav=document.querySelector('.wb-sidebar .wb-toc');if(nav&&!nav.querySelector('[href="#manual-refinement"]')){const a=document.createElement('a');a.href='#manual-refinement';for(const [lang,text] of [['zh','08 手动精修'],['en','08 Manual refinement']]){const s=document.createElement('span');s.className='t-'+lang;s.textContent=text;a.append(s)}const li=document.createElement('li');li.append(a);nav.append(li)}})();</script>'''
