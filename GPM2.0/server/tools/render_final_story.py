"""Inline, read-only project-style preview. Coordinates always use the shared bp ruler."""
from collections import defaultdict
import heapq
from render_path_story import section
from render_refinement_report import bi, esc, copy_btn, fmt_bp_short
from report_gap_story import NAMES, tool_order


def _style(a,b,n):
    return f'left:{100*a/n:.9g}%;width:{100*(b-a)/n:.9g}%;'


def _part(a,b,n,css,title,*,attrs='',shade=''):
    button=bool(attrs);tag='button' if button else 'span'; attr=(' type="button" '+attrs if button else '')
    return f'<{tag}{attr} class="preview-part {css}" title="{esc(title)}" aria-label="{esc(title)}" style="{_style(a,b,n)}{shade}"></{tag}>'


def _track(name,inner):
    return f'<div class="preview-detail-row"><span>{esc(name)}</span><div class="preview-rail">{inner}</div></div>'


def _row(c,domain,ref,idx,colors):
    title=c['chr']; n=c['length']; upper=[]; by_source=defaultdict(list)
    for p in c['parts']:
        a,b=p['start'],p['end'];src=p['source'];edit=p['edit'];attr='';desc=f'{title} [{a:,}, {b:,}) · {b-a:,} bp';k=p['kind'];key=src['dataset'] if src else None
        if src:
            x,y=src['span'];name=f'{key} / {src["name"]} ({src["strand"]}) [{x:,}, {y:,})';desc+=' · '+name
            if edit:desc+=' · '+edit+' · '+', '.join(p['gaps'])
        else:desc+=' · '+k
        if edit and p['gaps'] and p['gaps'][0] in idx:
            ci,gi,ti=idx[p['gaps'][0]];attr=f'data-story-open="auto-gap-inspector" data-gap-chr="{ci}" data-gap-index="{gi}" data-tool-index="{ti}"'
        color='var(--gen-unfilled)' if k=='gap' else ('var(--gen-patch)' if edit else f'var(--ds-{colors[key]})')
        shade=f'background:{color};';upper.append(_part(a,b,domain,'adopted refined' if edit and k!='gap' else 'adopted' if k!='gap' else 'path-gap',desc,attrs=attr,shade=shade))
        if not src:continue
        full=src['length'];offset=x if src['strand']=='+' else (full-y if full else 0)
        start,end=(max(0,a-offset),min(domain,a-offset+full)) if full else (a,b)
        by_source[key, bool(edit)].append((start,end,a,b,desc,full,shade,attr,src['name']+(' →' if src['strand']=='+' else ' ←')))
    rows=[]
    if ref:
        rows.append(_track('Ref · '+title,_part(0,ref['length_bp'],domain,'','Ref · '+title,shade='background:var(--text-muted)')+
                     ''.join(_part(a,b,domain,'path-gap','Ref gap',shade='background:var(--gen-unfilled)') for a,b in (ref.get('gaps') or []))))
    else: rows.append(_track('Ref',bi('未记录参考坐标','Reference coordinates unavailable')))
    for (dataset,is_patch),parts in sorted(by_source.items()):
        lanes=[];ends=[]
        for start,end,a,b,desc,full,shade,attr,text in sorted(parts):
            if ends and ends[0][0]<=start:_,lane=heapq.heappop(ends)
            else: lane=len(lanes);lanes.append([])
            if full:lanes[lane].append(_part(start,end,domain,'source-body',desc+f' · ctg {full:,} bp',shade=shade))
            lanes[lane].append(_part(a,b,domain,'adopted refined' if is_patch else 'adopted',desc,attrs=attr,shade=shade))
            lanes[lane].append(f'<span aria-hidden="true" class="preview-label" style="{_style(start,end,domain)}"><span>{esc(text)}</span></span>')
            heapq.heappush(ends,(end,lane))
        for lane in lanes: rows.append(_track(('＋ ' if is_patch else '')+dataset,''.join(lane)))
    heading=f'<strong>{esc(title)}</strong> <small>{esc(fmt_bp_short(n))}</small>'
    return ('<details class="final-preview-row"><summary><span class="preview-heading">'+heading+'</span><span class="preview-rail">'+''.join(upper)+'</span></summary>' + ''.join(rows)+'</details>')


def final_card(vm):
    if vm['meta']['mode'] in ('manual_only','lgz_failed'):return ''
    tools=sorted(vm['refinement_summary']['tools'],key=lambda r:tool_order(r['tool']));auto=bool(tools);versions=vm.get('final_versions')
    num='07' if auto else '06';refs=vm['lgz_summary'].get('reference_tracks',{}); ids=defaultdict(list)
    for g in vm['refinement_summary'].get('original_loci',[]):ids[g['chromosome']].append(g['gap_id'])
    index={gid:(ci,gi) for ci,gids in enumerate(ids.values()) for gi,gid in enumerate(gids)}
    if versions is None:return section('final-path',num,'Final Path','Final Path',bi('此旧报告未记录可核对的交付路径。','No verified delivery path was recorded in this report model.'))
    if not versions: return section('final-path', num,'Final Path','Final Path','<p>'+ (bi('本批没有已验证的自动精修交付。','No verified refined version was published in this batch.') if auto else bi('本批未记录可核对的 LGZ 成品。','No verified LGZ delivery recorded for this run.'))+'</p>')
    domain=max([1,*[r['length_bp'] for r in refs.values()],*[c['length'] for v in versions for c in (v['tracks'] or [])]])
    colors={k:i%6 for i,k in enumerate(dict.fromkeys([r['name'] for r in vm['lgz_summary']['inputs']['assemblies']]+[p['source']['dataset'] for v in versions for c in v['tracks'] or [] for p in c['parts'] if p['source']]))}
    panels=[];opts=[]
    for i,v in enumerate(versions):
        tool=v['tool'];name='LGZ + '+NAMES.get(tool,tool) if auto else 'LGZ-only';opts.append(f'<option value="{i}">{esc(name)}</option>')
        idx={k:(*pair,next(j for j,t in enumerate(tools) if t['tool']==tool)) for k,pair in index.items()} if auto else {}
        note=bi('服务器 FASTA','Server FASTA') if v['absolute'] else bi('工作区相对路径','Workspace-relative path')
        path='<div class="final-fasta">'+note+' <code>'+esc(v['fasta'])+'</code> '+copy_btn(v['fasta'],zh='复制路径',en='Copy path')+'</div>'
        unchanged='<p>'+bi('本版本未接纳新编辑，沿用 LGZ 序列。','No new edits were admitted; the LGZ sequence was retained.')+'</p>' if v['edits']==0 else ''
        tracks=''.join(_row(c,domain,refs.get(c['chr']),idx,colors) for c in v['tracks']) if v['tracks'] else '<p>'+bi('已验证 FASTA，未取得可核对的完整片段坐标，不绘制推测路径。','FASTA verified; a complete segment track is unavailable in this record.')+'</p>'
        if v.get('geometry_note')=='source_extents_unverified':
            tracks='<p>'+bi('来源 ctg 总长未通过核对，只绘制已采用的区间。','Source contig lengths were not verified; only adopted intervals are drawn.')+'</p>'+tracks
        panels.append(f'<div class="final-version" data-version-panel="{i}"'+(' hidden' if i else '')+'>'+path+unchanged+tracks+'</div>')
    switch='<label>'+bi('交付版本','Published version')+' <select data-final-version>'+''.join(opts)+'</select></label>' if len(opts)>1 else '<b>'+esc(name)+'</b>'
    return section('final-path',num,'Final Path','Final Path',STYLE+switch+''.join(panels)+SCRIPT)


STYLE='''<style>.final-version[hidden]{display:none}.final-fasta{display:flex;flex-wrap:wrap;gap:.45em;align-items:center;margin:.45em 0}.final-fasta code{overflow-wrap:anywhere}.final-preview-row{border-top:1px solid var(--border-subtle)}.final-preview-row>summary,.preview-detail-row{display:grid;grid-template-columns:minmax(8.5rem,22%) minmax(0,1fr);align-items:center;gap:.5rem}.final-preview-row>summary{cursor:pointer;list-style:none;min-height:2rem}.final-preview-row>summary::-webkit-details-marker{display:none}.preview-heading{white-space:nowrap;text-overflow:ellipsis;overflow:hidden}.preview-heading:before{content:'▸';margin-right:.4em}.final-preview-row[open]>summary .preview-heading:before{content:'▾'}.preview-heading small{color:var(--text-muted)}.preview-rail{position:relative;display:block;height:1.1rem}.preview-part{position:absolute;display:block;top:25%;height:50%;border:0;padding:0}.preview-part.adopted{min-width:1px}.preview-part.source-body{opacity:.28;height:70%;top:15%}.preview-part.path-gap{z-index:1}.preview-part:is(button){cursor:pointer}.preview-part.refined{height:76%;top:12%;outline:1px solid var(--text-primary);z-index:2}.preview-part[data-story-open]::after{content:"";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:max(100%,14px);height:max(100%,18px)}.preview-label{container-type:inline-size;position:absolute;inset-block:0;pointer-events:none;overflow:hidden;z-index:3}.preview-label>span{display:none;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;font-size:.72rem;line-height:1.2;background:var(--surface-panel);color:var(--text-primary);padding:0 .15em;max-width:90%}@container (min-width:6rem){.preview-label>span{display:inline-block}}.preview-detail-row{font-size:.8em;color:var(--text-muted);min-height:1.35rem}.preview-detail-row>span{padding-left:1em;overflow-wrap:anywhere}</style>'''
SCRIPT='''<script data-cgat-ui="1">(()=>{const card=document.getElementById('final-path'),sel=card.querySelector('[data-final-version]');if(sel)sel.addEventListener('change',()=>{for(const p of card.querySelectorAll('[data-version-panel]'))p.hidden=p.dataset.versionPanel!==sel.value});card.addEventListener('click',e=>{if(e.target.closest('summary [data-story-open]'))e.preventDefault()})})();</script>'''
