"""Compact 06: original positions, one shared inspector, one tool at a time."""
import json
from collections import defaultdict

try:
    from render_path_story import section
    from render_refinement_report import bi, esc, fmt_bp_short
    from report_gap_story import NAMES, tool_order
except ModuleNotFoundError:
    from .render_path_story import section
    from .render_refinement_report import bi, esc, fmt_bp_short
    from .report_gap_story import NAMES, tool_order


def gap_card(vm):
    ref = vm['refinement_summary']
    tools = sorted(ref['tools'], key=lambda r: tool_order(r['tool']))
    if not tools:
        return ''
    groups = defaultdict(list)
    lengths = {r['chromosome']: r['length_bp'] for r in vm['lgz_summary']['chromosomes']}
    lengths.update(ref.get('baseline_lengths', {}))
    for g in ref.get('original_loci', []):
        groups[g['chromosome']].append(g)
    payload = {'tools': [[NAMES.get(t['tool'], t['tool']), t['status'], t.get('degap_global_href')] for t in tools], 'chr': []}
    max_len = 1
    for name, rows in groups.items():
        data = []
        for g in rows:
            gid = g['gap_id']
            attempts = []
            for t in tools:
                d = t.get('gap_decisions', {}).get(gid)
                if not t['publication_verified'] or not d:
                    attempts.append(['unknown'])
                    continue
                item = [d['state']]
                if d.get('edits') or d.get('candidates') or d.get('incomplete') or t.get('degap_jobs_by_gap', {}).get(gid):
                    item.extend([d['edits'], d['candidates'], d['incomplete'], d['residual_n_bp'], t.get('degap_jobs_by_gap', {}).get(gid, [])])
                attempts.append(item)
            data.append([gid, g['start'], g['end'], attempts])
        length = lengths.get(name)
        valid_len = length if type(length) is int and length >= max(g[2] for g in data) else None
        if valid_len:
            max_len = max(max_len, valid_len)
        payload['chr'].append([name, valid_len, data])
    total = ref['gap_matrix']['total_gap_count']
    # No HTML per gap/tool panel: very large denominators retain every locus.
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    statuses = {'staged': '已暂存，未发布 / Staged (not published)', 'pending': '等待中 / Pending', 'published': '已发布 / Published', 'failed': '失败 / Failed'}
    note = (bi('本批未记录有效的原始 gap 分母。', 'No valid original gap denominator for this batch.') if total is None else
            bi(f'{total:,} 个 LGZ 原始 gap', f'{total:,} original LGZ gaps'))
    if total and 'original_loci' not in ref:
        return section('auto-refinement', '06', '自动精修', 'Automatic refinement',
                       '<p class="muted">' + note + ' · ' + bi('旧报告只保存了预览，不绘制推测的位点。', 'Only a preview was recorded; a complete locus map is unavailable.') + '</p>')
    tool_sel = (
        '<label class="gap-tool-select-lbl">' + bi('当前工具', 'Current tool')
        + ' <select data-gap-tool>'
        + ''.join(f'<option value="{i}">{esc(NAMES.get(t["tool"], t["tool"]))} · {esc(statuses.get(t["status"], t["status"]))}</option>' for i, t in enumerate(tools))
        + '</select></label>'
    )
    ruler = (
        '<div class="gap-axis"><small>LGZ ' + bi('比例尺', 'scale') + '</small><small class="story-ruler">'
        + ''.join(f'<span>{esc(fmt_bp_short(round(max_len * i / 4)))}</span>' for i in range(5))
        + '</small><span></span></div>'
    ) if payload['chr'] else ''
    legend = (
        '<div class="story-toolbar">'
        '<div class="legend-row" style="margin:0">'
        '<span class="legend-item"><i class="gap-dot is-closed"></i>' + bi('完整闭合', 'Closed') + '</span>'
        '<span class="legend-item"><i class="gap-dot is-retained"></i>' + bi('保持原样', 'Unchanged') + '</span>'
        '<span class="legend-item"><i class="gap-dot is-unknown"></i>' + bi('无已验证结果', 'No verified result') + '</span>'
        '</div>' + tool_sel + '</div>'
    )
    body = (
        '<div id="auto-gap-story">' + legend + ruler + '<div data-gap-rows></div><noscript>'
        + bi('启用 JavaScript 以查看每个原始 gap。', 'Enable JavaScript to inspect individual gaps.')
        + '</noscript></div><template id="auto-gap-inspector" data-title="Gap"><div data-gap-inspector></div></template>'
        + '<template id="gap-svg-seed"><svg></svg></template><script type="application/json" id="auto-gap-data">' + data + '</script>'
        + STYLE + SCRIPT
    )
    return section('auto-refinement', '06', '自动精修', 'Automatic refinement', body, right=note)


STYLE = '''<style>
.gap-tool-select-lbl{display:inline-flex;align-items:center;gap:.4rem;font-size:.81rem;font-weight:500;color:var(--text-secondary)}
.gap-tool-select-lbl select,.gap-row select{padding:.22rem .48rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-primary);font:500 .8rem/1.25 inherit}
.gap-dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0}
.gap-dot.is-closed{background:var(--gen-closed)}
.gap-dot.is-retained{background:var(--surface-panel);border:1.8px solid var(--border-strong)}
.gap-dot.is-partial{background:var(--gen-partial)}
.gap-dot.is-unknown{width:8px;height:2px;border-radius:1px;background:var(--border-strong)}
.gap-axis,.gap-row{display:grid;grid-template-columns:148px minmax(2rem,1fr) auto;gap:.75rem;align-items:center}
.gap-axis{align-items:end;padding:0 0 .32rem;border-bottom:1px solid var(--border-default);color:var(--text-muted);font-size:.76rem}
.gap-row{border-bottom:1px solid var(--border-subtle);padding:.46rem 0}
.gap-row:last-child{border-bottom:1px solid var(--border-default)}
.gap-row b{display:block;font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gap-row small{display:block;margin-top:.1rem;font:400 .75rem/1.3 sans-serif;color:var(--text-muted);font-variant-numeric:tabular-nums}
.gap-row small.has-closed{color:var(--tone-ok-ink);font-weight:600}
.gap-row select{max-width:7.8rem;font-family:var(--font-mono);font-size:.76rem}
.gap-track-box{min-width:0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.gap-track{height:1.55rem;background:linear-gradient(var(--border-strong),var(--border-strong)) left center/100% 3px no-repeat;position:relative}
.gap-track button{position:absolute;top:0;transform:translateX(-50%);min-width:14px;height:100%;padding:0;border:0;background:transparent;cursor:pointer;display:inline-grid;place-items:center}
.gap-track button::after{content:"";width:9px;height:9px;border-radius:50%;background:var(--surface-panel);border:1.8px solid var(--border-strong);box-shadow:0 0 0 1.5px var(--surface-panel);transition:transform .1s}
.gap-track button.st-closed::after{background:var(--gen-closed);border-color:var(--gen-closed)}
.gap-track button.st-partial::after{background:var(--gen-partial);border-color:var(--gen-partial)}
.gap-track button.st-unknown::after{width:7px;height:3px;border-radius:1px;background:var(--border-strong);border:0}
.gap-track button:hover::after{transform:scale(1.3)}
.gap-track button:focus-visible{z-index:3}
.gap-info-sub{margin:0 0 .55rem;font-size:.82rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.gap-info-head{display:flex;align-items:center;justify-content:space-between;gap:.55rem;flex-wrap:wrap;padding-bottom:.65rem;margin-bottom:.65rem;border-bottom:1px solid var(--border-subtle)}
.gap-tools{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap}
.gap-tools button,.gap-tools>span{display:inline-flex;align-items:center;gap:.38rem;border:1px solid var(--border-default);border-radius:6px;background:var(--surface-panel);color:var(--text-secondary);padding:.36rem .72rem;font:600 .82rem/1.25 inherit}
.gap-tools button{cursor:pointer;transition:border-color .12s,background .12s,color .12s}
.gap-tools button:hover{border-color:var(--border-strong);background:var(--surface-subtle);color:var(--text-primary)}
.gap-tools [aria-pressed=true]{border-color:var(--brand);background:var(--brand-soft);color:var(--brand);box-shadow:inset 0 0 0 1px var(--brand)}
.gap-tools [aria-pressed=true].st-closed{border-color:var(--gen-closed);background:var(--tone-ok-bg);color:var(--tone-ok-ink);box-shadow:inset 0 0 0 1px var(--gen-closed)}
.gap-degap-links{display:inline-flex;align-items:center;gap:.45rem;flex-wrap:wrap}
.gap-degap-links a{display:inline-flex;align-items:center;padding:.26rem .58rem;border-radius:var(--radius-sm);border:1px solid var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-size:.8rem;font-weight:600;text-decoration:none}
.gap-degap-links a:hover{filter:brightness(.97);text-decoration:none}
.gap-inspector-svg{display:block;width:100%;max-height:165px}
.gap-evidence{margin:.45rem 0}
@media (max-width:760px){
  .gap-axis,.gap-row{grid-template-columns:96px minmax(2rem,1fr) auto;gap:.4rem}
  .gap-row select{max-width:5.6rem}
}
</style>'''

SCRIPT = r'''<script data-cgat-ui="1" data-gap-story-ui="1">(()=>{
const card=document.getElementById('auto-gap-story'), info=card?JSON.parse(document.getElementById('auto-gap-data').textContent):{tools:[],chr:[]};
const tools=info.tools, chr=info.chr, selector=card?.querySelector('[data-gap-tool]'), rows=card?.querySelector('[data-gap-rows]');
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
function bi(zh,en){const n=node('span');n.append(node('span','t-zh',zh),node('span','t-en',en));return n}
const fmt=n=>Number(n).toLocaleString('en-US'), pos=s=>`[${fmt(s[0])}, ${fmt(s[1])})`;
const states={closed:['●','闭合','Closed'],retained:['○','原样','Unchanged'],partial:['△','历史部分改动','Historical partial edit'],unknown:['—','无已验证结果','No verified result']};
const reasons={missing_native_candidate:['原生结果缺少候选序列。','Native result lacked the candidate sequence.'],candidate_shorter_than_anchors:['候选短于侧翼锚点。','Candidate was shorter than a required flank anchor.'],native_anchors_do_not_reconstruct_baseline:['候选侧翼与原路径不一致。','The native flanks did not reproduce the baseline.'],native_junction_exterior_does_not_reconstruct_baseline:['接缝外围未与原路径吻合。','The junction exteriors did not match the baseline.'],native_integration_slice_disagrees_with_full_candidate:['取用片段与完整候选不一致。','The integration slice differed from the full candidate.'],unproven_native_overlap:['未能验证末端重叠。','The proposed overlap could not be verified.'],overlap_crosses_another_gap:['重叠区跨越了另一个 gap。','The overlap crossed another gap.'],candidate_has_no_filled_bases:['候选没有非 N 的填补碱基。','Candidate supplied no non-N bases.'],candidate_does_not_change_baseline:['候选与原路径相同。','Candidate did not change the baseline.'],native_anchor_absent:['候选中找不到对应的侧翼锚点。','The required flank anchor was absent.'],native_anchor_not_unique:['候选中的侧翼锚点不唯一。','The flank anchor was not unique in the candidate.'],gap_and_flank_cannot_be_separated:['无法将 gap 修改与已知侧翼可靠分开。','The gap edit could not be separated reliably from the known flank.'],native_change_not_bound_to_an_original_gap:['修改无法归属到原始 gap。','The change could not be bound to an original gap.'],projected_gap_unchanged:['候选投影到 gap 后没有改动。','The candidate projection did not change the gap.']};
const rank={closed:0,retained:1,partial:2,unknown:3};
function attrs(n,ci,gi){n.dataset.storyOpen='auto-gap-inspector';n.dataset.gapChr=ci;n.dataset.gapIndex=gi}
const maxLength=chr.reduce((m,r)=>Math.max(m,r[1]||0),1);
function draw(){const tid=+selector.value;rows.replaceChildren();chr.forEach(([name,len,gaps],ci)=>{
  const row=node('div','gap-row'),label=node('b',null,name),closed=gaps.filter(g=>g[3][tid][0]==='closed').length;
  const sub=node('small',closed?'has-closed':null);
  sub.append(gaps.every(g=>g[3][tid][0]==='unknown')?bi(`无已验证结果 · ${gaps.length} gap`,`No verified result · ${gaps.length} gaps`):bi(`${closed} / ${gaps.length} 闭合`,`${closed} / ${gaps.length} closed`));
  label.append(sub);row.append(label);
  const box=node('div','gap-track-box'),rail=node('div',len?'gap-track':null);
  if(len)rail.style.width=(100*len/maxLength)+'%';else rail.append(bi('未记录 LGZ 长度','LGZ length unavailable'));
  box.append(rail);
  // The locus picker also reaches two positions that fall on the same pixel.
  const picker=node('select');picker.setAttribute('aria-label',name+' · Gap');picker.append(node('option',null,'Gap…'));
  gaps.forEach(([id,a,b,attempts],gi)=>{const code=attempts[tid][0],state=states[code],title=`${id} · ${pos([a,b])} · ${state[1]} / ${state[2]}`;
    if(len){const btn=node('button','st-'+code);btn.type='button';attrs(btn,ci,gi);btn.title=title;btn.setAttribute('aria-label',title);btn.style.left=((a+b)*50/len)+'%';rail.append(btn)}
    const op=node('option',null,`${state[0]} ${id}`);op.value=gi;picker.append(op)});
  picker.addEventListener('change',()=>{if(!picker.selectedIndex)return;attrs(picker,ci,+picker.value);picker.selectedIndex=0;
    picker.dispatchEvent(new CustomEvent('cgat-locus-picker',{bubbles:true}));delete picker.dataset.storyOpen});row.append(box,picker);rows.append(row)})}
if(selector){selector.addEventListener('change',draw);draw()}
const ns=document.getElementById('gap-svg-seed').content.firstElementChild.namespaceURI;function svgEl(type,atts,txt){const n=document.createElementNS(ns,type);Object.entries(atts).forEach(([k,v])=>n.setAttribute(k,v));if(txt!==undefined)n.textContent=txt;return n}
const scale=(a,b)=>v=>104+670*(v-a)/Math.max(1,b-a);
function shape(svg,span,ax,y,color,h=10){const a=ax(span[0]),b=ax(span[1]);svg.append(a===b?svgEl('path',{d:`M${a} ${y-5}v${h+10}`,stroke:color,'stroke-width':2.2}):svgEl('rect',{x:a,y,width:Math.max(2,b-a),height:h,rx:2,fill:color}))}
function graph(window,gap,edit,cand,state,topLbl,midLbl,botLbl){
  const svg=svgEl('svg',{viewBox:'0 0 800 132',class:'gap-inspector-svg',role:'img','aria-label':'Input → candidate → output / 原路径、候选与交付'}),ax=scale(...window),gray='var(--border-strong)',gapFill='var(--surface-muted)',green='var(--gen-closed)';
  svg.append(svgEl('text',{x:8,y:28,'font-size':'11','font-weight':'600',fill:'var(--text-secondary)'},topLbl));
  svg.append(svgEl('text',{x:8,y:70,'font-size':'11','font-weight':'600',fill:'var(--text-secondary)'},midLbl));
  svg.append(svgEl('text',{x:8,y:112,'font-size':'11','font-weight':'600',fill:'var(--text-primary)'},botLbl));
  shape(svg,window,ax,19,gray,10);
  const gx0=ax(gap[0]),gx1=ax(gap[1]),gw=Math.max(3,gx1-gx0);
  svg.append(svgEl('rect',{x:gx0,y:19,width:gw,height:10,fill:gapFill,stroke:'var(--border-strong)'}));
  if(gw>38)svg.append(svgEl('text',{x:(gx0+gx1)/2,y:27.5,'text-anchor':'middle','font-size':'9.5','font-weight':'700',fill:'var(--text-primary)'},`${fmt(gap[1]-gap[0])} N`));
  if(cand&&cand.before){shape(svg,cand.before,ax,61,'var(--text-muted)',10)}
  if(edit){const [a,b]=edit.before,[u,v]=edit.after;
    if(a<gap[0])shape(svg,[a,gap[0]],ax,19,'var(--gen-patch)',10);
    if(b>gap[1])shape(svg,[gap[1],b],ax,19,'var(--gen-patch)',10);
    const left=Math.max(0,u-(a-window[0])),right=v+(window[1]-b),out=scale(left,right);
    // Only the verified replacement is drawn on the output axis. Neighbouring edits may change the flanks.
    shape(svg,[left,right],out,103,'var(--border-default)',10);
    shape(svg,[u,v],out,102,green,12);
    if(v>u&&out(v)-out(u)>44)svg.append(svgEl('text',{x:(out(u)+out(v))/2,y:111.5,'text-anchor':'middle','font-size':'9.5','font-weight':'700',fill:'#fff'},`${fmt(v-u)} bp`));
    const pairs=edit.anchors||[];
    if(edit.native){const spans=[edit.native,...pairs.map(p=>p[1])];const lo=Math.min(...spans.map(s=>s[0])),hi=Math.max(...spans.map(s=>s[1])),na=scale(lo,hi);
      if(lo<hi)shape(svg,[lo,hi],na,61,'var(--border-default)',10);
      pairs.forEach(([p,q])=>svg.append(svgEl('polygon',{points:`${ax(p[0])},29 ${ax(p[1])},29 ${na(q[1])},61 ${na(q[0])},61`,fill:green,opacity:.24})));
      shape(svg,edit.native,na,60,green,12);
      if(edit.native[1]>edit.native[0]&&na(edit.native[1])-na(edit.native[0])>44)svg.append(svgEl('text',{x:(na(edit.native[0])+na(edit.native[1]))/2,y:69.5,'text-anchor':'middle','font-size':'9.5','font-weight':'700',fill:'#fff'},`${fmt(edit.native[1]-edit.native[0])} bp`));
    }else if(v>u){
      const cLen=v-u,cPad=Math.max(1,Math.ceil(Math.max(cLen,gap[1]-gap[0])/3)),ca=scale(-cPad,cLen+cPad);
      shape(svg,[0,cLen],ca,60,green,12);
      if(ca(cLen)-ca(0)>44)svg.append(svgEl('text',{x:(ca(0)+ca(cLen))/2,y:69.5,'text-anchor':'middle','font-size':'9.5','font-weight':'700',fill:'#fff'},`${fmt(cLen)} bp`));
    }else{
      shape(svg,[a,a],ax,61,green,10);
    }
  }else if(state==='retained'){
    if(!cand||!cand.before)svg.append(svgEl('line',{x1:104,y1:66,x2:774,y2:66,stroke:'var(--border-default)','stroke-width':'2','stroke-dasharray':'4 4'}));
    shape(svg,window,ax,103,gray,10);
    svg.append(svgEl('rect',{x:gx0,y:103,width:gw,height:10,fill:gapFill,stroke:'var(--border-strong)'}));
  }
  return svg}
function inspector(panel,ci,gi,initial,ctx=info){const tools=ctx.tools,manual=ctx.manual;const [name,length,gaps]=ctx.chr[ci], [gid,a,b,attempts]=gaps[gi];const out=panel.querySelector('[data-gap-inspector]');
 const order=tools.map((_,i)=>i).sort((i,j)=>rank[attempts[i][0]]-rank[attempts[j][0]]||i-j);const verified=attempts.filter(v=>['closed','retained'].includes(v[0])).length;
 const closed=attempts.filter(v=>v[0]==='closed').length;panel.querySelector('#path-event-title').replaceChildren(document.createTextNode(name+' · '+gid+'　'),verified?bi(`${closed} / ${verified} 个工具闭合`,`${closed} / ${verified} evaluated tools closed`):bi('无可计数的交付结果','No evaluated delivery'));
 const extent=[a,b];for(const item of attempts){for(const e of item[1]||[]){extent.push(...e.before);for(const [p] of e.anchors)extent.push(...p)}for(const c of item[2]||[])if(c.before)extent.push(...c.before)}
 const lo=Math.min(...extent),hi=Math.max(...extent),pad=Math.max(1,Math.ceil((hi-lo)/3));const window=[Math.max(0,lo-pad),length?Math.min(length,hi+pad):hi];
 const subLine=node('p','gap-info-sub');subLine.append(manual?bi('导出快照原 gap','Exported gap'):bi('LGZ 原始 gap','Original LGZ gap'),document.createTextNode(` · ${pos([a,b])} · ${fmt(b-a)} bp`));
 const top=node('div','gap-info-head'),tabs=node('div','gap-tools'),links=node('div','gap-degap-links'),body=node('div');top.append(tabs,links);out.append(subLine,top,body);
 const isZh=()=>document.documentElement.dataset.lang!=='en';
 const buttons=[];function select(i){buttons.forEach(([j,btn])=>btn.setAttribute('aria-pressed',String(j===i)));const [s,edits=[],cands=[],inc,n,jobs=[]]=attempts[i];links.replaceChildren();body.replaceChildren();
  if(tools[i][0]==='DEGAP'){const targets=jobs.filter(j=>j.href);if(!targets.length&&tools[i][2])targets.push({href:tools[i][2],global:true});for(const j of targets){const link=node('a');link.href=j.href;link.target='_blank';link.rel='noopener noreferrer';const t=targets.length>1?' · '+j.name:'';link.append(j.global?bi('DEGAP 总览 ↗','DEGAP overview ↗'):bi('查看 DEGAP 过程'+t+' ↗','DEGAP process'+t+' ↗'));links.append(link)}}
  if(manual){const r=manual.attempts[i],p=r.patch,w=manual.selected,admitted=w===r.tool;
    const delivered=manual.after?{before:[a,b],after:manual.after,anchors:[]}:null;
    const plotWrap=node('div','story-plot-frame');
    const drawing=graph(window,[a,b],delivered,null,delivered?'closed':'retained',isZh()?'导出时':'Exported',tools[i][0],isZh()?'本批结果':'Batch FASTA');
    if(p){const pad=Math.max(1,Math.ceil(Math.max(p.length,b-a)/3));shape(drawing,[0,p.length],scale(-pad,p.length+pad),61,admitted?'var(--gen-closed)':'var(--text-muted)',11)}
    plotWrap.append(drawing);body.append(plotWrap);
    const strip=node('div','story-meta-strip');
    const s1=node('span');s1.append(bi('上轨：App 导出时','Top: at App export'),document.createTextNode(' '+pos([a,b])));strip.append(s1);
    if(p){const s2=node('span');s2.append(bi('中轨：完整闭合候选','Middle: closed candidate'),document.createTextNode(` · ${fmt(p.length)} bp · SHA256 ${p.sha256.slice(0,12)}`));strip.append(s2)}
    const s3=node('span');s3.append(w?bi('下轨：本批实际采用','Bottom: admitted in batch'):bi('下轨：保留导出时的 gap','Bottom: retained as exported'));
    if(w)s3.append(document.createTextNode(' '+manual.winnerName+' '+pos(manual.after)));strip.append(s3);body.append(strip);
    const msg=node('div','story-verdict'+(admitted?' is-ok':''));if(admitted)msg.append(p.length?bi('完整闭合，已写入本批 FASTA。','Complete closure, included in this batch FASTA.'):bi('直接接合，没有补入片段。','Direct join; no sequence was inserted.'));
    else if(p)msg.append(bi('此工具也闭合了 gap，但本批未选择这个结果。','This tool also closed the gap, but its result was not selected.'));
    else if(r.message)msg.append(bi(...r.message));else msg.append(bi('没有可核对的闭合候选。','No verifiable closed candidate recorded.'),document.createTextNode(' · '+r.status));body.append(msg);return}
  if(s==='unknown'){const box=node('div','story-verdict is-warn');const why={failed:['本次工具执行失败。','The tool failed in this batch.'],pending:['该工具尚未执行。','This tool has not run.'],staged:['结果已暂存，尚未发布。','The result was staged, not published.'],invalidated:['本次发布已失效。','The publication was invalidated.'],publication_unverified:['无法核对本次交付回执。','This publication receipt could not be verified.']}[tools[i][1]];if(why)box.append(bi(...why),document.createTextNode(' '));box.append(bi('未取得此工具的本批交付结果，不计入原样。','No verified result for this tool in this batch; not counted as unchanged.'));body.append(box);return}
  if(s==='partial'){const box=node('div','story-verdict is-warn');box.append(bi('历史交付包含部分改动，不归入闭合或原样。','This historical delivery contains a partial edit; neither closed nor unchanged.'));body.append(box);return}
  const dsName=d=>d.startsWith('cgat_refinement_')?tools[i][0]:d;
  function add(e,c){const group=node('div','gap-evidence'),plotWrap=node('div','story-plot-frame');
    plotWrap.append(graph(window,[a,b],e,c,s,isZh()?'LGZ 原路径':'LGZ path',tools[i][0],isZh()?'交付结果':'Delivered'));
    group.append(plotWrap);
    const strip=node('div','story-meta-strip');
    const wSpan=node('span');wSpan.append(bi('LGZ 窗口','LGZ window'),document.createTextNode(' '+pos(window)));strip.append(wSpan);
    if(e){const rSpan=node('span');rSpan.append(bi('替换区间','Replaced'),document.createTextNode(' '+pos(e.before)));strip.append(rSpan);
      const dSpan=node('span');dSpan.append(e.source?bi('实际补入','Admitted bridge'):bi('直接接合（无补入片段）','Direct join (no inserted sequence)'),document.createTextNode(' '+pos(e.after)));
      if(e.source)dSpan.append(document.createTextNode(` · ${dsName(e.source.dataset)}/${e.source.name} (${e.source.strand}) ${pos(e.source.span)}`));strip.append(dSpan);
      if(e.native){const nSpan=node('span');nSpan.append(bi('候选采用区间','Admitted native interval'),document.createTextNode(' '+pos(e.native)));strip.append(nSpan)}
      if(e.gap_ids.length>1){const jSpan=node('span');jSpan.append(bi('联合编辑','Joint edit'),document.createTextNode(' '+e.id+' · '+e.gap_ids.join(', ')));strip.append(jSpan)}
    }else if(s==='retained'){const kSpan=node('span');kSpan.append(bi('结果：原始 gap 保留','Result: original gap retained'));strip.append(kSpan);
      if(c){const cSpan=node('span');cSpan.append(c.before?bi('灰色候选作用区间','Gray candidate footprint'):bi('候选未保存定位坐标','No candidate coordinates recorded'));if(c.before)cSpan.append(document.createTextNode(' '+pos(c.before)));if(c.source)cSpan.append(document.createTextNode(` · ${dsName(c.source.dataset)}/${c.source.name} (${c.source.strand}) ${pos(c.source.span)}`));if(c.gap_ids.length>1)cSpan.append(document.createTextNode(' · '+c.gap_ids.join(', ')));strip.append(cSpan);
        if(c.reason&&reasons[c.reason]){const whyP=node('p','muted');whyP.append(bi(...reasons[c.reason]));group.append(strip,whyP);body.append(group);return}}}
    group.append(strip);body.append(group)}
  if(edits.length)edits.forEach(e=>add(e,null));else if(cands.length)cands.forEach(c=>add(null,c));else add(null,null);
  const msg=node('div','story-verdict'+(s==='closed'?' is-ok':''));if(inc){msg.append(bi('候选未完整闭合所涉原始 gap，未采用。','The candidate did not close all affected gaps and was withheld.'));if(n!=null)msg.append(bi(` 候选仍有 ${fmt(n)} bp N；未推断其位置。`,` Candidate retained ${fmt(n)} bp N; positions not inferred.`))}
  else if(s==='closed')msg.append(edits.length?bi('该原始 gap 完整闭合，修改已纳入此工具交付。','The original gap was closed; this tool’s delivery includes the edit.'):bi('已记录闭合，旧记录缺少可核对的编辑坐标。','Closure was recorded; verified edit coordinates are unavailable.'));
  else msg.append(cands.length?bi('该候选未被接纳，交付保留原 gap。','Candidate not admitted; delivery retains the original gap.'):bi('交付未改变此 gap；未记录可核对的位点级候选。','The gap was retained; no verifiable locus-level candidate detail was recorded.'));body.append(msg)}
 for(const i of order){const code=attempts[i][0],st=states[code],btn=node(order.length===1?'span':'button','st-'+code);const dot=node('i','gap-dot is-'+(code==='closed'?'closed':code==='retained'?'retained':code==='partial'?'partial':'unknown'));dot.setAttribute('aria-hidden','true');btn.append(dot,document.createTextNode(tools[i][0]+' · '),bi(st[1],st[2]));if(manual&&manual.attempts[i].tool===manual.selected){btn.append(bi(' · 本批采用',' · Selected'))}if(order.length>1){btn.type='button';btn.addEventListener('click',()=>select(i))}tabs.append(btn);buttons.push([i,btn])}select(order.includes(initial)?initial:order[0])}
document.addEventListener('cgat-story-open',ev=>{const b=ev.detail.button;if(b.dataset.manualGap){const data=document.getElementById(b.dataset.manualGap);if(data)inspector(ev.target,0,0,null,JSON.parse(data.textContent));return}if(b.dataset.storyOpen==='auto-gap-inspector')inspector(ev.target,+b.dataset.gapChr,+b.dataset.gapIndex,b.hasAttribute('data-tool-index')?+b.dataset.toolIndex:null)});
})();</script>'''
