"""Compact 06: original positions, one shared inspector, one tool at a time."""
import json
from collections import defaultdict

from render_path_story import section
from render_refinement_report import bi, esc
from report_gap_story import NAMES, tool_order


def gap_card(vm):
    ref = vm['refinement_summary']
    tools = sorted(ref['tools'], key=lambda r: tool_order(r['tool']))
    if not tools:
        return ''
    groups = defaultdict(list)
    lengths = {r['chromosome']: r['length_bp'] for r in vm['lgz_summary']['chromosomes']}
    lengths.update(ref.get('baseline_lengths',{}))
    for g in ref.get('original_loci', []):
        groups[g['chromosome']].append(g)
    payload = {'tools': [[NAMES.get(t['tool'],t['tool']), t['status'], t.get('degap_global_href')] for t in tools], 'chr': []}
    for name, rows in groups.items():
        data = []
        for g in rows:
            gid = g['gap_id']; attempts = []
            for t in tools:
                d = t.get('gap_decisions', {}).get(gid)
                if not t['publication_verified'] or not d:
                    attempts.append(['unknown']); continue
                item = [d['state']]
                if d.get('edits') or d.get('candidates') or d.get('incomplete') or t.get('degap_jobs_by_gap', {}).get(gid):
                    item.extend([d['edits'], d['candidates'], d['incomplete'], d['residual_n_bp'], t.get('degap_jobs_by_gap',{}).get(gid,[])])
                attempts.append(item)
            data.append([gid, g['start'], g['end'], attempts])
        length = lengths.get(name)
        payload['chr'].append([name, length if type(length) is int and length >= max(g[2] for g in data) else None, data])
    total = ref['gap_matrix']['total_gap_count']
    # No HTML per gap/tool panel: very large denominators retain every locus.
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    statuses={'staged':'已暂存，未发布 / Staged (not published)','pending':'等待中 / Pending','published':'已发布 / Published','failed':'失败 / Failed'}
    note = (bi('本批未记录有效的原始 gap 分母。', 'No valid original gap denominator for this batch.') if total is None else
            bi(f'{total:,} 个 LGZ 原始 gap', f'{total:,} original LGZ gaps'))
    if total and 'original_loci' not in ref:
        return section('auto-refinement','06','自动精修','Automatic refinement',note+' · '+bi('旧报告只保存了预览，不绘制推测的位点。','Only a preview was recorded; a complete locus map is unavailable.'))
    body = ('<div id="auto-gap-story"><div class="gap-controls"><strong>'+note+'</strong>　<label>'+bi('当前工具','Current tool')+
            ' <select data-gap-tool>'+''.join(f'<option value="{i}">{esc(NAMES.get(t["tool"],t["tool"]))} · {esc(statuses.get(t["status"],t["status"]))}</option>' for i,t in enumerate(tools))+
            '</select></label></div><p class="muted">'+bi('● 闭合　○ 原样　— 无已验证结果','● Closed　○ Unchanged　— No verified result')+
            '</p><div data-gap-rows></div><noscript>'+bi('启用 JavaScript 以查看每个原始 gap。','Enable JavaScript to inspect individual gaps.')+
            '</noscript></div><template id="auto-gap-inspector" data-title="Gap"><div data-gap-inspector></div></template>'+
            '<template id="gap-svg-seed"><svg></svg></template><script type="application/json" id="auto-gap-data">'+data+'</script>'+STYLE+SCRIPT)
    return section('auto-refinement','06','自动精修','Automatic refinement',body)


STYLE = '''<style>.gap-controls,.gap-tools,.gap-info-head{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap}.gap-info-head{justify-content:space-between}.gap-info-head a{margin-left:.5rem}.gap-tools button{border:1px solid var(--border-default);border-radius:.4em;background:var(--surface-panel);color:inherit;padding:.25em .55em;cursor:pointer}.gap-tools [aria-pressed=true]{outline:2px solid var(--accent);outline-offset:1px}.gap-track{height:1.4rem;background:linear-gradient(var(--border-strong),var(--border-strong)) left center/100% 2px no-repeat;position:relative}.gap-track button{position:absolute;transform:translateX(-50%);min-width:14px;height:100%;padding:0;border:0;background:transparent;color:var(--brand);cursor:pointer}.gap-row{display:grid;grid-template-columns:minmax(8rem,18%) minmax(2rem,1fr) auto;gap:.75rem;align-items:center;border-top:1px solid var(--border-subtle);padding:.4rem 0}.gap-row select{max-width:9em}.gap-row small{display:block;color:var(--text-muted)}.gap-inspector-svg{display:block;width:100%;max-height:155px}.gap-evidence{border-top:1px solid var(--border-subtle);padding:.45rem 0}.gap-tools{margin:.5rem 0}.gap-row button:focus-visible{z-index:2;background:var(--surface-panel)}</style>'''

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
  const row=node('div','gap-row'),label=node('b',null,name),sub=node('small');const closed=gaps.filter(g=>g[3][tid][0]==='closed').length;
  sub.append(gaps.every(g=>g[3][tid][0]==='unknown')?bi(`无已验证结果 · ${gaps.length} 原始 gap`,`No verified result · ${gaps.length} original gaps`):bi(`${closed} 闭合 / ${gaps.length} 原始 gap`,`${closed} closed / ${gaps.length} original gaps`));label.append(sub);row.append(label);
  const rail=node('div',len?'gap-track':null);if(len)rail.style.width=(100*len/maxLength)+'%';else rail.append(bi('未记录 LGZ 长度','LGZ length unavailable'));
  // The locus picker also reaches two positions that fall on the same pixel.
  const picker=node('select');picker.setAttribute('aria-label',name+' · Gap');picker.append(node('option',null,'Gap…'));
  gaps.forEach(([id,a,b,attempts],gi)=>{const state=states[attempts[tid][0]],title=`${id} · ${pos([a,b])} · ${state[1]} / ${state[2]}`;
    if(len){const btn=node('button',null,state[0]);btn.type='button';attrs(btn,ci,gi);btn.title=title;btn.setAttribute('aria-label',title);btn.style.left=((a+b)*50/len)+'%';rail.append(btn)}
    const op=node('option',null,`${state[0]} ${id}`);op.value=gi;picker.append(op)});
  picker.addEventListener('change',()=>{if(!picker.selectedIndex)return;attrs(picker,ci,+picker.value);picker.selectedIndex=0;
    picker.dispatchEvent(new CustomEvent('cgat-locus-picker',{bubbles:true}));delete picker.dataset.storyOpen});row.append(rail,picker);rows.append(row)})}
if(selector){selector.addEventListener('change',draw);draw()}
const ns=document.getElementById('gap-svg-seed').content.firstElementChild.namespaceURI;function svgEl(type,atts){const n=document.createElementNS(ns,type);Object.entries(atts).forEach(([k,v])=>n.setAttribute(k,v));return n}
const scale=(a,b)=>v=>26+748*(v-a)/Math.max(1,b-a);
function shape(svg,span,ax,y,color){const a=ax(span[0]),b=ax(span[1]);svg.append(a===b?svgEl('path',{d:`M${a} ${y-6}v17`,stroke:color,'stroke-width':2}):svgEl('rect',{x:a,y,width:b-a,height:7,fill:color}))}
function graph(window,gap,edit,cand,state){const svg=svgEl('svg',{viewBox:'0 0 800 112',class:'gap-inspector-svg',role:'img','aria-label':'Input → candidate → output / 原路径、候选与交付'}),ax=scale(...window),gray='var(--text-muted)',amber='var(--gen-unfilled)',blue='var(--ds-1)';
  shape(svg,window,ax,13,gray);shape(svg,gap,ax,13,amber);
  if(cand&&cand.before){shape(svg,cand.before,ax,47,gray)}
  if(edit){const [a,b]=edit.before,[u,v]=edit.after;if(a<gap[0])shape(svg,[a,gap[0]],ax,13,'var(--gen-patch)');if(b>gap[1])shape(svg,[gap[1],b],ax,13,'var(--gen-patch)');const left=Math.max(0,u-(a-window[0])),right=v+(window[1]-b),out=scale(left,right);
    // Only the verified replacement is drawn on the output axis. Neighbouring edits may change the flanks.
    shape(svg,[u,v],out,85,blue);
    const pairs=edit.anchors||[];if(edit.native){const spans=[edit.native,...pairs.map(p=>p[1])];const lo=Math.min(...spans.map(s=>s[0])),hi=Math.max(...spans.map(s=>s[1])),na=scale(lo,hi);if(lo<hi)shape(svg,[lo,hi],na,47,gray);
      pairs.forEach(([p,q])=>svg.append(svgEl('polygon',{points:`${ax(p[0])},20 ${ax(p[1])},20 ${na(q[1])},47 ${na(q[0])},47`,fill:blue,opacity:.3})));shape(svg,edit.native,na,47,blue)}
  }else if(state==='retained'){shape(svg,gap,ax,85,amber)}return svg}
function inspector(panel,ci,gi,initial,ctx=info){const tools=ctx.tools,manual=ctx.manual;const [name,length,gaps]=ctx.chr[ci], [gid,a,b,attempts]=gaps[gi];const out=panel.querySelector('[data-gap-inspector]');
 const order=tools.map((_,i)=>i).sort((i,j)=>rank[attempts[i][0]]-rank[attempts[j][0]]||i-j);const verified=attempts.filter(v=>['closed','retained'].includes(v[0])).length;
 const closed=attempts.filter(v=>v[0]==='closed').length;panel.querySelector('#path-event-title').replaceChildren(document.createTextNode(name+' · '+gid+'　'),verified?bi(`${closed} / ${verified} 个工具闭合`,`${closed} / ${verified} evaluated tools closed`):bi('无可计数的交付结果','No evaluated delivery'));
 const extent=[a,b];for(const item of attempts){for(const e of item[1]||[]){extent.push(...e.before);for(const [p] of e.anchors)extent.push(...p)}for(const c of item[2]||[])if(c.before)extent.push(...c.before)}
 const lo=Math.min(...extent),hi=Math.max(...extent),pad=Math.max(1,Math.ceil((hi-lo)/3));const window=[Math.max(0,lo-pad),length?Math.min(length,hi+pad):hi];
 const top=node('div','gap-info-head'),tabs=node('div','gap-tools'),links=node('div'),body=node('div');top.append(tabs,links);out.append(top,body);
 const buttons=[];function select(i){buttons.forEach(([j,btn])=>btn.setAttribute('aria-pressed',String(j===i)));const [s,edits=[],cands=[],inc,n,jobs=[]]=attempts[i];links.replaceChildren();body.replaceChildren();
  if(tools[i][0]==='DEGAP'){const targets=jobs.filter(j=>j.href);if(!targets.length&&tools[i][2])targets.push({href:tools[i][2],global:true});for(const j of targets){const link=node('a');link.href=j.href;link.target='_blank';link.rel='noopener noreferrer';const t=targets.length>1?' · '+j.name:'';link.append(j.global?bi('DEGAP 总览 ↗','DEGAP overview ↗'):bi('查看 DEGAP 过程'+t+' ↗','DEGAP process'+t+' ↗'));links.append(link)}}
  if(manual){const r=manual.attempts[i],p=r.patch,w=manual.selected,admitted=w===r.tool;
    const delivered=manual.after?{before:[a,b],after:manual.after,anchors:[]}:null;
    const drawing=graph(window,[a,b],delivered,null,delivered?'closed':'retained');
    if(p){const pad=Math.max(1,Math.ceil(Math.max(p.length,b-a)/3));shape(drawing,[0,p.length],scale(-pad,p.length+pad),47,admitted?'var(--ds-1)':'var(--text-muted)')}
    body.append(drawing,bi('上轨：App 导出时的 gap','Top: gap at App export'),document.createTextNode(' '+pos([a,b])));
    if(p){body.append(node('br'),bi('中轨：完整闭合候选','Middle: fully closed candidate'),document.createTextNode(` · ${fmt(p.length)} bp · SHA256 ${p.sha256.slice(0,12)}`))}
    body.append(node('br'),w?bi('下轨：本批实际采用','Bottom: admitted in this batch'):bi('下轨：保留导出时的 gap','Bottom: gap retained as exported'));
    if(w)body.append(document.createTextNode(' '+manual.winnerName+' '+pos(manual.after)));
    const msg=node('p');if(admitted)msg.append(p.length?bi('完整闭合，已写入本批 FASTA。','Complete closure, included in this batch FASTA.'):bi('直接接合，没有补入片段。','Direct join; no sequence was inserted.'));
    else if(p)msg.append(bi('此工具也闭合了 gap，但本批未选择这个结果。','This tool also closed the gap, but its result was not selected.'));
    else if(r.message)msg.append(bi(...r.message));else msg.append(bi('没有可核对的闭合候选。','No verifiable closed candidate recorded.'),document.createTextNode(' · '+r.status));body.append(msg);return}
  const intro=node('p');intro.append(bi('LGZ 原始 gap','Original LGZ gap'),document.createTextNode(' '+pos([a,b])+' · '+fmt(b-a)+' bp'));body.append(intro);
  if(s==='unknown'){const why={failed:['本次工具执行失败。','The tool failed in this batch.'],pending:['该工具尚未执行。','This tool has not run.'],staged:['结果已暂存，尚未发布。','The result was staged, not published.'],invalidated:['本次发布已失效。','The publication was invalidated.'],publication_unverified:['无法核对本次交付回执。','This publication receipt could not be verified.']}[tools[i][1]];if(why)body.append(bi(...why),node('br'));body.append(bi('未取得此工具的本批交付结果，不计入原样。','No verified result for this tool in this batch; not counted as unchanged.'));return}
  if(s==='partial'){body.append(bi('历史交付包含部分改动，不归入闭合或原样。','This historical delivery contains a partial edit; neither closed nor unchanged.'));return}
  function add(e,c){const group=node('div','gap-evidence');group.append(graph(window,[a,b],e,c,s));group.append(bi('上轨：LGZ 窗口','Top: LGZ window'),document.createTextNode(' '+pos(window)));
    if(e){group.append(node('br'),bi('修改的 LGZ 区间','LGZ interval replaced'),document.createTextNode(' '+pos(e.before)));const label=e.source?bi('下轨：实际补入','Bottom: admitted bridge'):bi('下轨：直接接合（切点，无补入片段）','Bottom: direct join (cut; no inserted sequence)');group.append(node('br'),label,document.createTextNode(' '+pos(e.after)));
      if(e.source)group.append(document.createTextNode(` · ${e.source.dataset} / ${e.source.name} (${e.source.strand}) ${pos(e.source.span)}`));
      if(e.native)group.append(node('br'),bi('中轨：候选采用区间','Middle: admitted native interval'),document.createTextNode(' '+pos(e.native)));
      if(e.gap_ids.length>1)group.append(node('br'),bi('同一联合编辑','One joint edit'),document.createTextNode(' '+e.id+' · '+e.gap_ids.join(', ')));
    }else if(s==='retained'){group.append(node('br'),bi('下轨：原始 gap 保留','Bottom: original gap retained'));if(c){group.append(node('br'),c.before?bi('灰色：未采用的候选作用区间','Gray: candidate footprint, not admitted'):bi('候选未保存定位坐标','No candidate coordinates recorded'));if(c.before)group.append(document.createTextNode(' '+pos(c.before)));if(c.source)group.append(document.createTextNode(` · ${c.source.dataset} / ${c.source.name} (${c.source.strand}) ${pos(c.source.span)}`));if(c.reason&&reasons[c.reason])group.append(node('br'),bi(...reasons[c.reason]));if(c.gap_ids.length>1)group.append(document.createTextNode(' · '+c.gap_ids.join(', ')))}}
    body.append(group)}
  if(edits.length)edits.forEach(e=>add(e,null));else if(cands.length)cands.forEach(c=>add(null,c));else add(null,null);
  const msg=node('p');if(inc){msg.append(bi('候选未完整闭合所涉原始 gap，未采用。','The candidate did not close all affected gaps and was withheld.'));if(n!=null)msg.append(bi(` 候选仍有 ${fmt(n)} bp N；未推断其位置。`,` Candidate retained ${fmt(n)} bp N; positions not inferred.`))}
  else if(s==='closed')msg.append(edits.length?bi('该原始 gap 完整闭合，修改已纳入此工具交付。','The original gap was closed; this tool’s delivery includes the edit.'):bi('已记录闭合，旧记录缺少可核对的编辑坐标。','Closure was recorded; verified edit coordinates are unavailable.'));
  else msg.append(cands.length?bi('该候选未被接纳，交付保留原 gap。','Candidate not admitted; delivery retains the original gap.'):bi('交付未改变此 gap；未记录可核对的位点级候选。','The gap was retained; no verifiable locus-level candidate detail was recorded.'));body.append(msg)}
 for(const i of order){const st=states[attempts[i][0]],btn=node(order.length===1?'span':'button');btn.append(document.createTextNode(tools[i][0]+' '+st[0]+' '),bi(st[1],st[2]));if(manual&&manual.attempts[i].tool===manual.selected){btn.append(bi(' · 本批采用',' · Selected'))}if(order.length>1){btn.type='button';btn.addEventListener('click',()=>select(i))}tabs.append(btn);buttons.push([i,btn])}select(order.includes(initial)?initial:order[0])}
document.addEventListener('cgat-story-open',ev=>{const b=ev.detail.button;if(b.dataset.manualGap){const data=document.getElementById(b.dataset.manualGap);if(data)inspector(ev.target,0,0,null,JSON.parse(data.textContent));return}if(b.dataset.storyOpen==='auto-gap-inspector')inspector(ev.target,+b.dataset.gapChr,+b.dataset.gapIndex,b.hasAttribute('data-tool-index')?+b.dataset.toolIndex:null)});
})();</script>'''
