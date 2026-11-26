"""Compact 07: original positions, tool comparison strip, track/matrix toggle, one shared inspector."""
import json
from collections import defaultdict

try:
    from render_path_story import section, zoom_button
    from render_refinement_report import bi, esc, fmt_bp_short
    from report_gap_story import NAMES, tool_order
except ModuleNotFoundError:
    from .render_path_story import section, zoom_button
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
    seen_states = set()
    for name, rows in groups.items():
        data = []
        for g in rows:
            gid = g['gap_id']
            attempts = []
            for t in tools:
                d = t.get('gap_decisions', {}).get(gid)
                if not t['publication_verified'] or not d:
                    attempts.append(['unknown'])
                    seen_states.add('unknown')
                    continue
                st_code = d['state']
                if st_code == 'partial':
                    # Only present closed vs unclosed; never surface partial edits as closures.
                    seen_states.add('retained')
                    attempts.append(['retained'])
                    continue
                seen_states.add(st_code)
                item = [st_code]
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
    note = (bi('本批未记录有效的原始 gap 分母。', 'No valid original gap denominator for this batch.') if total is None else
            bi(f'{total:,} 个原始 Gap · {len(tools)} 个工具', f'{total:,} original gaps · {len(tools)} tools'))
    if total and 'original_loci' not in ref:
        return section('auto-refinement', '07', '自动精修', 'Automatic refinement',
                       '<p class="muted">' + note + ' · ' + bi('旧报告只保存了预览，不绘制推测的位点。', 'Only a preview was recorded; a complete locus map is unavailable.') + '</p>')

    degap_href = next((t.get('degap_global_href') for t in tools if t['tool'] == 'degap' and t.get('degap_global_href')), None)
    degap_top_link = (
        f'<a class="gap-ext-link" href="{esc(degap_href)}" target="_blank" rel="noopener noreferrer">'
        + bi('DEGAP 详细报告 ↗', 'DEGAP report ↗') + '</a>'
    ) if degap_href else ''

    legend_bits = [
        '<span class="legend-item"><i class="gap-dot is-closed"></i>' + bi('已闭合', 'Closed') + '</span>',
        '<span class="legend-item"><i class="gap-dot is-retained"></i>' + bi('未闭合', 'Unclosed') + '</span>',
    ]
    if 'unknown' in seen_states:
        legend_bits.append('<span class="legend-item"><i class="gap-dot is-unknown"></i>' + bi('无已验证结果', 'Unverified') + '</span>')

    view_switch = (
        '<div class="gap-view-switch" role="group" aria-label="View mode">'
        '<button type="button" data-gap-view="track" aria-pressed="true">' + bi('分布图', 'Tracks') + '</button>'
        '<button type="button" data-gap-view="matrix" aria-pressed="false">' + bi('对比表', 'Matrix') + '</button>'
        '</div>'
    ) if payload['chr'] else ''

    toolbar = (
        '<div class="story-toolbar">'
        '<div class="legend-row" style="margin:0">' + ''.join(legend_bits) + '</div>'
        '<div class="gap-toolbar-right">' + degap_top_link + view_switch + '</div>'
        '</div>'
    )
    ruler = (
        '<div class="gap-axis"><span>' + bi('染色体', 'Chromosome') + '</span><span class="story-ruler">'
        + ''.join(f'<span>{esc(fmt_bp_short(round(max_len * i / 4)))}</span>' for i in range(5))
        + '</span><span class="muted" style="text-align:right;font-weight:500">' + bi('位点', 'Locus') + '</span></div>'
    ) if payload['chr'] else ''
    zbtn = zoom_button('07 自动精修 · 放大视图', '07 Automatic refinement · Enlarged view') if payload['chr'] else ''
    track_view = (
        '<div class="gap-frame" data-zoom-frame="1" data-gap-panel="track">'
        + ruler + '<div data-gap-rows></div>' + zbtn + '</div>'
    )
    matrix_view = '<div class="gap-matrix-wrap" data-gap-panel="matrix" hidden></div>'

    body = (
        '<div id="auto-gap-story">'
        '<div class="gap-tool-cards" data-gap-tool-cards></div>'
        + toolbar + track_view + matrix_view
        + '<noscript>' + bi('启用 JavaScript 以查看每个原始 gap。', 'Enable JavaScript to inspect individual gaps.') + '</noscript>'
        '</div>'
        '<template id="auto-gap-inspector" data-title="Gap"><div data-gap-inspector></div></template>'
        '<template id="gap-svg-seed"><svg></svg></template>'
        '<script type="application/json" id="auto-gap-data">' + data + '</script>'
        + STYLE + SCRIPT
    )
    return section('auto-refinement', '07', '自动精修', 'Automatic refinement', body, right=note)


STYLE = '''<style>
.gap-tool-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:.55rem;margin-bottom:.75rem}
.gap-tool-card{display:flex;flex-direction:column;gap:.38rem;padding:.58rem .75rem;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-subtle);text-align:left;cursor:pointer;transition:border-color .12s,background .12s,box-shadow .12s}
.gap-tool-card:hover{border-color:var(--border-default);background:var(--surface-panel)}
.gap-tool-card[aria-pressed="true"]{border-color:var(--brand);background:var(--surface-panel);box-shadow:inset 0 0 0 1px var(--brand),0 1px 3px rgba(15,23,42,.06)}
.gap-tc-head{display:flex;align-items:center;justify-content:space-between;gap:.4rem}
.gap-tc-name{font:700 .86rem/1.2 inherit;color:var(--text-primary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gap-tc-status{padding:1px 6px;border-radius:999px;font-size:.69rem;font-weight:500;border:1px solid var(--border-subtle);background:var(--surface-panel);color:var(--text-muted);white-space:nowrap}
.gap-tc-status.is-ok{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.gap-tc-status.is-err{border-color:var(--tone-warn-line);background:var(--tone-warn-bg);color:var(--tone-warn-ink)}
.gap-tc-stat{display:flex;align-items:baseline;justify-content:space-between;gap:.4rem;font-size:.77rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.gap-tc-stat b{font-size:.98rem;font-weight:700;color:var(--text-primary);margin-right:.2rem}
.gap-tc-stat b.has-closed{color:var(--tone-ok-ink)}
.gap-tc-bar{display:flex;height:5px;border-radius:999px;background:var(--surface-muted);overflow:hidden}
.gap-tc-bar i{display:block;height:100%}
.gap-tc-bar .is-c{background:var(--gen-closed)}
.gap-tc-bar .is-p{background:var(--gen-partial)}
.gap-toolbar-right{display:inline-flex;align-items:center;gap:.55rem;flex-wrap:wrap}
.gap-ext-link{display:inline-flex;align-items:center;padding:3px 9px;border-radius:999px;border:1px solid var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-size:.77rem;font-weight:600;text-decoration:none;white-space:nowrap}
.gap-ext-link:hover{filter:brightness(.97);text-decoration:none}
.gap-view-switch{display:inline-flex;padding:2px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-subtle);gap:2px}
.gap-view-switch button{padding:3px 10px;border:0;border-radius:4px;background:transparent;color:var(--text-secondary);font:500 .78rem/1.3 inherit;cursor:pointer;transition:background .12s,color .12s}
.gap-view-switch button[aria-pressed="true"]{background:var(--surface-panel);color:var(--text-primary);font-weight:600;box-shadow:0 1px 2px rgba(15,23,42,.08)}
.gap-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.gap-frame[hidden],.gap-matrix-wrap[hidden]{display:none}
.gap-dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0}
.gap-dot.is-closed{background:var(--gen-closed)}
.gap-dot.is-retained{background:var(--surface-panel);border:1.8px solid var(--border-strong)}
.gap-dot.is-partial{background:var(--gen-partial)}
.gap-dot.is-unknown{width:8px;height:2.5px;border-radius:1px;background:var(--border-strong)}
.gap-axis,.gap-row{display:grid;grid-template-columns:168px minmax(2rem,1fr) 152px;gap:.75rem;align-items:center}
.gap-axis{padding:.52rem .85rem .44rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600}
.gap-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:.75rem}
.gap-row{border-bottom:1px solid var(--border-subtle);padding:.62rem .85rem;transition:background .12s}
.gap-row:last-child{border-bottom:0}
.gap-row:hover{background:var(--surface-subtle)}
.gap-chr-meta{min-width:0}
.gap-chr-head{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.gap-chr-meta b{font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gap-chr-pill{display:inline-flex;align-items:center;padding:1px 6px;border-radius:999px;font-size:.71rem;font-weight:500;font-variant-numeric:tabular-nums;border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-muted);white-space:nowrap}
.gap-chr-pill.has-closed{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-weight:600}
.gap-chr-meta small{display:block;margin-top:.14rem;font-size:.75rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.gap-row select{width:100%;max-width:9.5rem;justify-self:end;padding:.24rem .45rem;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--text-primary);font:500 .75rem/1.25 var(--font-mono)}
.gap-track-box{min-width:0;padding:.2rem 0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.gap-track{height:1.65rem;position:relative}
.gap-track::before{content:"";position:absolute;left:0;right:0;top:50%;height:10px;transform:translateY(-50%);border-radius:2px;background:var(--ctg-ref-fill);box-shadow:inset 0 0 0 1px var(--ctg-ref-stroke)}
.gap-track button{position:absolute;top:0;transform:translateX(-50%);min-width:18px;height:100%;padding:0;border:0;background:transparent;cursor:pointer;display:inline-grid;place-items:center;z-index:2}
.gap-track button::after{content:"";width:11px;height:11px;border-radius:50%;background:var(--surface-panel);border:2px solid var(--border-strong);box-shadow:0 0 0 1.5px var(--surface-panel);transition:transform .1s}
.gap-track button.st-closed::after{background:var(--gen-closed);border-color:var(--gen-closed)}
.gap-track button.st-partial::after{background:var(--gen-partial);border-color:var(--gen-partial)}
.gap-track button.st-unknown::after{width:8px;height:3px;border-radius:1px;background:var(--border-strong);border:0}
.gap-track button:hover{z-index:4}
.gap-track button:hover::after{transform:scale(1.32)}
.gap-track button:focus-visible{z-index:5}
.gap-matrix-wrap{border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow-x:auto}
.gap-matrix-table{width:100%;border-collapse:collapse;font-size:.83rem;text-align:left}
.gap-matrix-table th,.gap-matrix-table td{padding:8px 11px;border-bottom:1px solid var(--border-subtle);vertical-align:middle}
.gap-matrix-table thead th{background:var(--surface-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600;white-space:nowrap}
.gap-matrix-table tbody tr:hover{background:var(--surface-subtle)}
.gap-matrix-table tbody tr:last-child>*{border-bottom:0}
.gap-matrix-chr{font:600 .82rem/1.25 var(--font-mono);color:var(--text-primary);white-space:nowrap}
.gap-matrix-pos{font:500 .79rem/1.25 var(--font-mono);color:var(--text-secondary);white-space:nowrap;font-variant-numeric:tabular-nums}
.gap-matrix-len{font-size:.76rem;color:var(--text-muted);margin-left:.35rem;font-variant-numeric:tabular-nums}
.gap-cell-btn{display:inline-flex;align-items:center;gap:.32rem;padding:2px 8px;border-radius:999px;border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-secondary);font:500 .75rem/1.3 inherit;cursor:pointer;white-space:nowrap;transition:border-color .12s,background .12s}
.gap-cell-btn:hover{border-color:var(--brand);background:var(--brand-soft);color:var(--brand)}
.gap-cell-btn.st-closed{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-weight:600}
.gap-cell-btn.st-partial{border-color:var(--tone-warn-line);background:var(--tone-warn-bg);color:var(--tone-warn-ink);font-weight:600}
.gap-matrix-more{display:flex;justify-content:center;padding:.55rem;border-top:1px solid var(--border-subtle);background:var(--surface-subtle)}
.gap-matrix-more button{padding:4px 12px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--accent);font:500 .8rem/1.3 inherit;cursor:pointer}
.gap-info-sub{margin:0 0 .55rem;font-size:.82rem;color:var(--text-secondary);font-variant-numeric:tabular-nums;display:flex;flex-wrap:wrap;align-items:center;gap:.35rem .75rem}
.gap-info-sub code{font-size:.79rem}
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
.gap-inspector-svg{display:block;width:100%;height:auto}
.gap-evidence{margin:.45rem 0}
.story-zoom-stage .gap-frame{border:0;border-radius:0;padding-bottom:0;overflow:visible;min-width:100%;width:calc(100% * var(--chart-scale, 1))}
.story-zoom-stage .gap-axis,.story-zoom-stage .gap-row{grid-template-columns:196px minmax(2rem,1fr) 152px;gap:0;padding:0;align-items:stretch}
.story-zoom-stage .gap-axis{position:sticky;top:0;z-index:8;background:var(--surface-subtle)}
.story-zoom-stage .gap-axis>:first-child{position:sticky;left:0;z-index:9;background:var(--surface-subtle);padding:.55rem .7rem .45rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;align-items:center}
.story-zoom-stage .gap-axis .story-ruler{margin:.55rem 1rem .45rem .8rem;min-width:0}
.story-zoom-stage .gap-axis>:last-child{padding:.55rem 1rem .45rem .5rem;display:flex;align-items:center;justify-content:flex-end}
.story-zoom-stage .gap-chr-meta{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding:.82rem .7rem .82rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;flex-direction:column;justify-content:center}
.story-zoom-stage .gap-row:hover .gap-chr-meta{background:var(--surface-subtle)}
.story-zoom-stage .gap-track-box{margin:.7rem .8rem;display:flex;align-items:center;z-index:1}
.story-zoom-stage .gap-row select{margin:.75rem 1rem .75rem .4rem;align-self:center}
@media (max-width:760px){
  .gap-axis,.gap-row{grid-template-columns:108px minmax(2rem,1fr) 96px;gap:.4rem;padding-left:.65rem;padding-right:.65rem}
  .gap-row select{max-width:6rem}
  .story-zoom-stage .gap-axis,.story-zoom-stage .gap-row{grid-template-columns:136px minmax(2rem,1fr) 110px;gap:0;padding:0}
}
</style>'''

SCRIPT = r'''<script data-cgat-ui="1" data-gap-story-ui="1">(()=>{
const card=document.getElementById('auto-gap-story'), info=card?JSON.parse(document.getElementById('auto-gap-data').textContent):{tools:[],chr:[]};
const tools=info.tools, chr=info.chr, cardsBox=card?.querySelector('[data-gap-tool-cards]'), rows=card?.querySelector('[data-gap-rows]'), matrixBox=card?.querySelector('[data-gap-panel="matrix"]'), trackBox=card?.querySelector('[data-gap-panel="track"]');
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
function bi(zh,en){const n=node('span');n.append(node('span','t-zh',zh),node('span','t-en',en));return n}
const fmt=n=>Number(n).toLocaleString('en-US');
const fmtShort=n=>{const v=Number(n);if(v>=1e6)return (v/1e6).toFixed(2)+' Mb';if(v>=1e3)return (v/1e3).toFixed(1)+' kb';return fmt(v)+' bp'};
const pos=s=>`${fmt(s[0]+1)}–${fmt(s[1])}`;
const states={closed:['●','已闭合','Closed'],retained:['○','未闭合','Unclosed'],unknown:['—','未验证','Unverified']};
const normState=c=>c==='partial'?'retained':c;
const toolStatus={published:['已发布','Published','is-ok'],staged:['已暂存','Staged',''],pending:['等待中','Pending',''],failed:['失败','Failed','is-err'],invalidated:['已失效','Invalidated','is-err']};
const reasons={missing_native_candidate:['原生结果缺少候选序列。','Native result lacked the candidate sequence.'],candidate_shorter_than_anchors:['候选短于侧翼锚点。','Candidate was shorter than a required flank anchor.'],native_anchors_do_not_reconstruct_baseline:['候选侧翼与原路径不一致。','The native flanks did not reproduce the baseline.'],native_junction_exterior_does_not_reconstruct_baseline:['接缝外围未与原路径吻合。','The junction exteriors did not match the baseline.'],native_integration_slice_disagrees_with_full_candidate:['取用片段与完整候选不一致。','The integration slice differed from the full candidate.'],unproven_native_overlap:['未能验证末端重叠。','The proposed overlap could not be verified.'],overlap_crosses_another_gap:['重叠区跨越了另一个 gap。','The overlap crossed another gap.'],candidate_has_no_filled_bases:['候选没有非 N 的填补碱基。','Candidate supplied no non-N bases.'],candidate_does_not_change_baseline:['候选与原路径相同。','Candidate did not change the baseline.'],native_anchor_absent:['候选中找不到对应的侧翼锚点。','The required flank anchor was absent.'],native_anchor_not_unique:['候选中的侧翼锚点不唯一。','The flank anchor was not unique in the candidate.'],gap_and_flank_cannot_be_separated:['无法将 gap 修改与已知侧翼可靠分开。','The gap edit could not be separated reliably from the known flank.'],native_change_not_bound_to_an_original_gap:['修改无法归属到原始 gap。','The change could not be bound to an original gap.'],projected_gap_unchanged:['候选投影到 gap 后没有改动。','The candidate projection did not change the gap.']};
const rank={closed:0,retained:1,unknown:2};
function attrs(n,ci,gi,ti){n.dataset.storyOpen='auto-gap-inspector';n.dataset.gapChr=ci;n.dataset.gapIndex=gi;if(ti!==undefined&&ti!==null)n.dataset.toolIndex=ti}
const maxLength=chr.reduce((m,r)=>Math.max(m,r[1]||0),1);
const totalLoci=chr.reduce((s,r)=>s+r[2].length,0);
let activeTool=0, matrixShown=80, matrixBuilt=false;

function renderToolCards(){
  if(!cardsBox||!tools.length)return;
  cardsBox.replaceChildren();
  tools.forEach(([tname,tst],ti)=>{
    let closed=0, unknown=0;
    chr.forEach(([, , gaps])=>gaps.forEach(g=>{const c=normState(g[3][ti][0]);if(c==='closed')closed++;else if(c==='unknown')unknown++;}));
    const btn=node('button','gap-tool-card');btn.type='button';btn.setAttribute('aria-pressed',String(ti===activeTool));
    const head=node('div','gap-tc-head');
    head.append(node('span','gap-tc-name',tname));
    const stInfo=toolStatus[tst]||[tst,tst,''];
    const stTag=node('span','gap-tc-status'+(stInfo[2]?' '+stInfo[2]:''));stTag.append(bi(stInfo[0],stInfo[1]));
    head.append(stTag);
    const stat=node('div','gap-tc-stat');
    const left=node('span');
    if(totalLoci>0&&unknown===totalLoci){
      left.append(bi('无已验证结果','Unverified'));
    }else{
      const num=node('b',closed?'has-closed':null,`${closed} / ${totalLoci}`);
      left.append(num,bi('闭合','closed'));
    }
    stat.append(left);
    if(totalLoci>0&&unknown<totalLoci){stat.append(node('span',null,`${Math.round(100*closed/totalLoci)}%`));}
    const bar=node('div','gap-tc-bar');
    if(totalLoci>0&&closed>0){const cEl=node('i','is-c');cEl.style.width=(100*closed/totalLoci)+'%';bar.append(cEl);}
    btn.append(head,stat,bar);
    btn.addEventListener('click',()=>{activeTool=ti;renderToolCards();draw();});
    cardsBox.append(btn);
  });
}

function draw(){
  if(!rows)return;
  const tid=activeTool;
  rows.replaceChildren();
  chr.forEach(([name,len,gaps],ci)=>{
    const row=node('div','gap-row'), meta=node('div','gap-chr-meta'), head=node('div','gap-chr-head');
    const closed=gaps.filter(g=>normState(g[3][tid][0])==='closed').length;
    const allUnk=gaps.every(g=>normState(g[3][tid][0])==='unknown');
    head.append(node('b',null,name));
    const pill=node('span','gap-chr-pill'+(closed?' has-closed':''));
    pill.append(allUnk?bi('未验证','Unverified'):bi(`${closed}/${gaps.length} 闭合`,`${closed}/${gaps.length}`));
    head.append(pill);
    meta.append(head);
    const sub=node('small');
    sub.append(len?document.createTextNode(fmtShort(len)+' · '):bi('长度未记录 · ','No length · '),bi(`${gaps.length} Gap`,`${gaps.length} gap`+(gaps.length===1?'':'s')));
    meta.append(sub);
    row.append(meta);
    const box=node('div','gap-track-box'), rail=node('div',len?'gap-track':null);
    if(len)rail.style.width=(100*len/maxLength)+'%';else rail.append(bi('未记录 LGZ 长度','LGZ length unavailable'));
    box.append(rail);
    const picker=node('select');picker.setAttribute('aria-label',name+' · Gap');
    const ph=node('option',null,`Gap (${gaps.length})…`);picker.append(ph);
    gaps.forEach(([id,a,b,attempts],gi)=>{
      const code=normState(attempts[tid][0]), state=states[code], bp=b-a;
      const title=`${name} · #${gi+1} · ${pos([a,b])} (${fmt(bp)} bp) · ${state[1]} / ${state[2]} · ${id}`;
      if(len){
        const btn=node('button','st-'+code);btn.type='button';attrs(btn,ci,gi,tid);btn.title=title;btn.setAttribute('aria-label',title);
        btn.style.left=((a+b)*50/len)+'%';rail.append(btn);
      }
      const op=node('option',null,`${state[0]} #${gi+1} · ${fmtShort(a)} (${fmtShort(bp)})`);op.value=gi;picker.append(op);
    });
    picker.addEventListener('change',()=>{
      if(!picker.selectedIndex)return;
      attrs(picker,ci,+picker.value,tid);picker.selectedIndex=0;
      picker.dispatchEvent(new CustomEvent('cgat-locus-picker',{bubbles:true}));
      delete picker.dataset.storyOpen;
    });
    row.append(box,picker);rows.append(row);
  });
}

function drawMatrix(){
  if(!matrixBox)return;
  matrixBox.replaceChildren();
  const flat=[];
  chr.forEach(([name, , gaps],ci)=>gaps.forEach((g,gi)=>flat.push([name,ci,gi,g])));
  const tbl=node('table','gap-matrix-table'), thead=node('thead'), hr=node('tr');
  const h1=node('th');h1.scope='col';h1.append(bi('染色体','Chr'));
  const h2=node('th');h2.scope='col';h2.append(bi('位点与长度','Position & length'));
  hr.append(h1,h2);
  tools.forEach(([tname])=>{const th=node('th');th.scope='col';th.textContent=tname;hr.append(th);});
  thead.append(hr);tbl.append(thead);
  const tbody=node('tbody');
  flat.slice(0,matrixShown).forEach(([name,ci,gi,[id,a,b,attempts]])=>{
    const tr=node('tr');
    const c1=node('td','gap-matrix-chr',`${name} #${gi+1}`);c1.title=id;
    const c2=node('td');
    c2.append(node('span','gap-matrix-pos',pos([a,b])),node('span','gap-matrix-len',fmtShort(b-a)));
    tr.append(c1,c2);
    attempts.forEach((att,ti)=>{
      const td=node('td'), code=normState(att[0]), st=states[code];
      const btn=node('button','gap-cell-btn st-'+code);btn.type='button';
      attrs(btn,ci,gi,ti);
      const dot=node('i','gap-dot is-'+code);dot.setAttribute('aria-hidden','true');
      btn.append(dot,bi(st[1],st[2]));
      td.append(btn);tr.append(td);
    });
    tbody.append(tr);
  });
  tbl.append(tbody);matrixBox.append(tbl);
  if(flat.length>matrixShown){
    const foot=node('div','gap-matrix-more'), more=node('button');more.type='button';
    more.append(bi(`显示全部 ${flat.length} 个位点（当前 ${matrixShown}）`,`Show all ${flat.length} loci (${matrixShown} shown)`));
    more.addEventListener('click',()=>{matrixShown=flat.length;drawMatrix();});
    foot.append(more);matrixBox.append(foot);
  }
  matrixBuilt=true;
}

if(card){
  renderToolCards();
  draw();
  card.querySelectorAll('[data-gap-view]').forEach(btn=>{
    btn.addEventListener('click',()=>{
      const mode=btn.dataset.gapView;
      card.querySelectorAll('[data-gap-view]').forEach(b=>b.setAttribute('aria-pressed',String(b===btn)));
      if(trackBox)trackBox.hidden=mode!=='track';
      if(matrixBox){matrixBox.hidden=mode!=='matrix';if(mode==='matrix'&&!matrixBuilt)drawMatrix();}
    });
  });
}

const ns=document.getElementById('gap-svg-seed').content.firstElementChild.namespaceURI;
function svgEl(type,atts,txt){const n=document.createElementNS(ns,type);Object.entries(atts).forEach(([k,v])=>n.setAttribute(k,v));if(txt!==undefined)n.textContent=txt;return n}
const scale=(a,b)=>v=>112+722*(v-a)/Math.max(1,b-a);
function shape(svg,span,ax,y,color,h=12,tip=''){
  const a=ax(span[0]),b=ax(span[1]);
  const el=a===b?svgEl('path',{d:`M${a} ${y-5}v${h+10}`,stroke:color,'stroke-width':2.4}):svgEl('rect',{x:a,y,width:Math.max(2.5,b-a),height:h,rx:2.5,fill:color});
  if(tip)el.append(svgEl('title',{},tip));
  svg.append(el);
}
function graph(window,gap,edit,cand,state,topLbl,midLbl,botLbl){
  const svg=svgEl('svg',{viewBox:'0 0 860 156',class:'gap-inspector-svg',role:'img','aria-label':'Input → candidate → output / 原路径、候选与交付'});
  const ax=scale(...window), gray='var(--border-strong)', gapFill='var(--surface-muted)', green='var(--gen-closed)';
  svg.append(svgEl('text',{x:10,y:34,'font-size':'11.5','font-weight':'600',fill:'var(--text-secondary)'},topLbl));
  svg.append(svgEl('text',{x:10,y:82,'font-size':'11.5','font-weight':'600',fill:'var(--text-secondary)'},midLbl));
  svg.append(svgEl('text',{x:10,y:130,'font-size':'11.5','font-weight':'600',fill:'var(--text-primary)'},botLbl));
  svg.append(svgEl('text',{x:112,y:15,'font-size':'10',fill:'var(--text-muted)'},fmt(window[0]+1)));
  svg.append(svgEl('text',{x:834,y:15,'text-anchor':'end','font-size':'10',fill:'var(--text-muted)'},fmt(window[1])));
  shape(svg,window,ax,23,gray,12,`${topLbl} · ${pos(window)}`);
  const gx0=ax(gap[0]),gx1=ax(gap[1]),gw=Math.max(4,gx1-gx0);
  const gRect=svgEl('rect',{x:gx0,y:23,width:gw,height:12,rx:2,fill:gapFill,stroke:'var(--border-strong)'});
  gRect.append(svgEl('title',{},`Gap · ${pos(gap)} · ${fmt(gap[1]-gap[0])} N`));
  svg.append(gRect);
  svg.append(svgEl('text',{x:Math.min(796,Math.max(150,(gx0+gx1)/2)),y:15,'text-anchor':'middle','font-size':'10','font-weight':'600',fill:'var(--text-secondary)'},`${fmt(gap[1]-gap[0])} N`));
  if(cand&&cand.before){shape(svg,cand.before,ax,71,'var(--text-muted)',12,`Candidate · ${pos(cand.before)}`)}
  if(edit){
    const [a,b]=edit.before,[u,v]=edit.after;
    if(a<gap[0])shape(svg,[a,gap[0]],ax,23,'var(--gen-patch)',12,`Trimmed flank · ${pos([a,gap[0]])}`);
    if(b>gap[1])shape(svg,[gap[1],b],ax,23,'var(--gen-patch)',12,`Trimmed flank · ${pos([gap[1],b])}`);
    const left=Math.max(0,u-(a-window[0])),right=v+(window[1]-b),out=scale(left,right);
    svg.append(svgEl('text',{x:112,y:149,'font-size':'10',fill:'var(--text-muted)'},fmt(left+1)));
    svg.append(svgEl('text',{x:834,y:149,'text-anchor':'end','font-size':'10',fill:'var(--text-muted)'},fmt(right)));
    shape(svg,[left,right],out,119,'var(--border-default)',12);
    shape(svg,[u,v],out,117,green,16,`${botLbl} · ${pos([u,v])} (${fmt(v-u)} bp)`);
    if(v>u){
      const ux=out(u),vx=out(v);
      if(vx-ux>46)svg.append(svgEl('text',{x:(ux+vx)/2,y:128.5,'text-anchor':'middle','font-size':'10','font-weight':'700',fill:'#fff'},`${fmt(v-u)} bp`));
      else svg.append(svgEl('text',{x:Math.min(796,Math.max(150,(ux+vx)/2)),y:149,'text-anchor':'middle','font-size':'10','font-weight':'600',fill:'var(--tone-ok-ink)'},`${fmt(v-u)} bp`));
    }
    const pairs=edit.anchors||[];
    if(edit.native){
      const spans=[edit.native,...pairs.map(p=>p[1])];
      const lo=Math.min(...spans.map(s=>s[0])),hi=Math.max(...spans.map(s=>s[1])),na=scale(lo,hi);
      if(lo<hi)shape(svg,[lo,hi],na,71,'var(--border-default)',12);
      pairs.forEach(([p,q])=>{
        const poly=svgEl('polygon',{points:`${ax(p[0])},35 ${ax(p[1])},35 ${na(q[1])},71 ${na(q[0])},71`,fill:green,opacity:.22});
        poly.append(svgEl('title',{},`Anchor · ${pos(p)} ↔ ${pos(q)}`));
        svg.append(poly);
      });
      shape(svg,edit.native,na,69,green,16,`Native · ${pos(edit.native)} (${fmt(edit.native[1]-edit.native[0])} bp)`);
      if(edit.native[1]>edit.native[0]&&na(edit.native[1])-na(edit.native[0])>46)svg.append(svgEl('text',{x:(na(edit.native[0])+na(edit.native[1]))/2,y:80.5,'text-anchor':'middle','font-size':'10','font-weight':'700',fill:'#fff'},`${fmt(edit.native[1]-edit.native[0])} bp`));
    }else if(v>u){
      const cLen=v-u,cPad=Math.max(1,Math.ceil(Math.max(cLen,gap[1]-gap[0])/3)),ca=scale(-cPad,cLen+cPad);
      shape(svg,[0,cLen],ca,69,green,16,`Patch · ${fmt(cLen)} bp`);
      if(ca(cLen)-ca(0)>46)svg.append(svgEl('text',{x:(ca(0)+ca(cLen))/2,y:80.5,'text-anchor':'middle','font-size':'10','font-weight':'700',fill:'#fff'},`${fmt(cLen)} bp`));
    }else{
      shape(svg,[a,a],ax,71,green,12,'Direct join');
    }
  }else if(state==='retained'){
    if(!cand||!cand.before)svg.append(svgEl('line',{x1:112,y1:77,x2:834,y2:77,stroke:'var(--border-default)','stroke-width':'2','stroke-dasharray':'4 4'}));
    shape(svg,window,ax,119,gray,12);
    svg.append(svgEl('rect',{x:gx0,y:119,width:gw,height:12,rx:2,fill:gapFill,stroke:'var(--border-strong)'}));
  }
  return svg;
}

function inspector(panel,ci,gi,initial,ctx=info){
  const tools=ctx.tools,manual=ctx.manual;
  const [name,length,gaps]=ctx.chr[ci], [gid,a,b,attempts]=gaps[gi];
  const out=panel.querySelector('[data-gap-inspector]');
  const order=tools.map((_,i)=>i).sort((i,j)=>rank[normState(attempts[i][0])]-rank[normState(attempts[j][0])]||i-j);
  const verified=attempts.filter(v=>['closed','retained'].includes(normState(v[0]))).length;
  const closed=attempts.filter(v=>normState(v[0])==='closed').length;
  const titleHead=manual?(name+' · '+gid):(name+' · Gap #'+(gi+1));
  panel.querySelector('#path-event-title').replaceChildren(
    document.createTextNode(titleHead+'　'),
    verified?bi(`${closed} / ${verified} 个工具闭合`,`${closed} / ${verified} tools closed`):bi('无已验证结果','No verified delivery')
  );
  const extent=[a,b];
  for(const item of attempts){
    for(const e of item[1]||[]){extent.push(...e.before);for(const [p] of e.anchors)extent.push(...p)}
    for(const c of item[2]||[])if(c.before)extent.push(...c.before)
  }
  const lo=Math.min(...extent),hi=Math.max(...extent),pad=Math.max(1,Math.ceil((hi-lo)/3));
  const window=[Math.max(0,lo-pad),length?Math.min(length,hi+pad):hi];
  const subLine=node('div','gap-info-sub');
  const sA=node('span');sA.append(manual?bi('导出时 Gap','Exported gap'):bi('原 Gap 位置','Original gap'),document.createTextNode(` ${pos([a,b])} (${fmt(b-a)} bp)`));
  subLine.append(sA);
  if(!manual){const idCode=node('code',null,gid);subLine.append(idCode);}
  const top=node('div','gap-info-head'),tabs=node('div','gap-tools'),links=node('div','gap-degap-links'),body=node('div');
  top.append(tabs,links);out.append(subLine,top,body);
  const isZh=()=>document.documentElement.dataset.lang!=='en';
  const buttons=[];

  function select(i){
    buttons.forEach(([j,btn])=>btn.setAttribute('aria-pressed',String(j===i)));
    const [rawS,rawEdits=[],cands=[],inc,n,jobs=[]]=attempts[i];
    const s=normState(rawS), edits=s==='closed'?rawEdits:[];
    links.replaceChildren();body.replaceChildren();
    if(tools[i][0]==='DEGAP'){
      const targets=jobs.filter(j=>j.href);
      if(!targets.length&&tools[i][2])targets.push({href:tools[i][2],global:true});
      for(const j of targets){
        const link=node('a');link.href=j.href;link.target='_blank';link.rel='noopener noreferrer';
        const t=targets.length>1?' · '+j.name:'';
        link.append(j.global?bi('DEGAP 总览 ↗','DEGAP overview ↗'):bi('查看 DEGAP 过程'+t+' ↗','DEGAP process'+t+' ↗'));
        links.append(link);
      }
    }
    if(manual){
      const r=manual.attempts[i],p=r.patch,w=manual.selected,admitted=w===r.tool;
      const delivered=manual.after?{before:[a,b],after:manual.after,anchors:[]}:null;
      const plotWrap=node('div','story-plot-frame');
      const drawing=graph(window,[a,b],delivered,null,delivered?'closed':'retained',isZh()?'导出时':'Exported',tools[i][0],isZh()?'本批结果':'Batch FASTA');
      if(p){const pd=Math.max(1,Math.ceil(Math.max(p.length,b-a)/3));shape(drawing,[0,p.length],scale(-pd,p.length+pd),71,admitted?'var(--gen-closed)':'var(--text-muted)',12,`Candidate · ${fmt(p.length)} bp`)}
      plotWrap.append(drawing);body.append(plotWrap);
      const strip=node('div','story-meta-strip');
      const s1=node('span');s1.append(bi('上轨：导出时','Top: exported'),document.createTextNode(' '+pos([a,b])));strip.append(s1);
      if(p){const s2=node('span');s2.append(bi('中轨：闭合候选','Middle: closed candidate'),document.createTextNode(` · ${fmt(p.length)} bp · ${p.sha256.slice(0,12)}`));strip.append(s2)}
      const s3=node('span');s3.append(w?bi('下轨：本批采用','Bottom: admitted'):bi('下轨：保持原样','Bottom: retained'));
      if(w)s3.append(document.createTextNode(' '+manual.winnerName+' '+pos(manual.after)));strip.append(s3);body.append(strip);
      const msg=node('div','story-verdict'+(admitted?' is-ok':''));
      if(admitted)msg.append(p.length?bi('完整闭合，已写入本批 FASTA。','Complete closure, included in this batch FASTA.'):bi('直接接合，无补入片段。','Direct join; no sequence was inserted.'));
      else if(p)msg.append(bi('此工具也闭合了 gap，但本批未选择这个结果。','This tool also closed the gap, but its result was not selected.'));
      else if(r.message)msg.append(bi(...r.message));
      else msg.append(bi('没有可核对的闭合候选。','No verifiable closed candidate recorded.'),document.createTextNode(' · '+r.status));
      body.append(msg);return;
    }
    if(s==='unknown'){
      const box=node('div','story-verdict is-warn');
      const why={failed:['工具执行失败。','Tool failed in this batch.'],pending:['工具尚未执行。','Tool has not run.'],staged:['结果已暂存，尚未发布。','Result staged, not published.'],invalidated:['发布已失效。','Publication invalidated.'],publication_unverified:['无法核对交付回执。','Publication receipt unverified.']}[tools[i][1]];
      if(why)box.append(bi(...why),document.createTextNode(' '));
      box.append(bi('无本批已验证交付结果，不计入未闭合。','No verified delivery for this tool; not counted as unclosed.'));
      body.append(box);return;
    }
    const dsName=d=>d.startsWith('cgat_refinement_')?tools[i][0]:d;
    function add(e,c){
      const group=node('div','gap-evidence'),plotWrap=node('div','story-plot-frame');
      plotWrap.append(graph(window,[a,b],e,c,s,isZh()?'LGZ 原路径':'LGZ path',tools[i][0],isZh()?'交付结果':'Delivered'));
      group.append(plotWrap);
      const strip=node('div','story-meta-strip');
      if(e){
        const rSpan=node('span');rSpan.append(bi('替换区间：','Replaced: '),document.createTextNode(`${pos(e.before)} (${fmt(e.before[1]-e.before[0])} bp)`));strip.append(rSpan);
        const insBp=e.after[1]-e.after[0];
        const dSpan=node('span');
        dSpan.append(insBp?bi('实际补入：','Admitted: '):bi('直接接合：','Direct join: '),document.createTextNode(`${pos(e.after)} (${fmt(insBp)} bp)`));
        if(e.source&&!e.source.dataset.startsWith('cgat_refinement_'))dSpan.append(document.createTextNode(` · ${dsName(e.source.dataset)}/${e.source.name} (${e.source.strand})`));
        strip.append(dSpan);
        if(e.gap_ids.length>1){const jSpan=node('span');jSpan.append(bi('联合闭合：','Joint closure: '),document.createTextNode(e.gap_ids.length+' gaps'));strip.append(jSpan)}
      }else if(s==='retained'){
        const kSpan=node('span');kSpan.append(bi('结果：保留原 Gap','Result: original gap retained'));strip.append(kSpan);
        if(c){
          const cSpan=node('span');
          cSpan.append(c.before?bi('候选区间：','Candidate span: '):bi('未保存候选坐标','No candidate coordinates'));
          if(c.before)cSpan.append(document.createTextNode(`${pos(c.before)} (${fmt(c.before[1]-c.before[0])} bp)`));
          strip.append(cSpan);
          if(c.reason&&reasons[c.reason]){const whyP=node('p','muted');whyP.append(bi(...reasons[c.reason]));group.append(strip,whyP);body.append(group);return}
        }
      }
      group.append(strip);body.append(group);
    }
    if(edits.length)edits.forEach(e=>add(e,null));else if(cands.length)cands.forEach(c=>add(null,c));else add(null,null);
    const msg=node('div','story-verdict'+(s==='closed'?' is-ok':''));
    if(inc){
      msg.append(bi('候选未完整闭合该位点，未采纳。','Candidate did not fully close the gap and was withheld.'));
      if(n!=null)msg.append(bi(` 候选残余 ${fmt(n)} bp N。`,` ${fmt(n)} bp N remained.`));
    }else if(s==='closed'){
      msg.append(edits.length?bi('已完整闭合，修改已写入此工具交付结果。','Gap closed and admitted into this tool’s delivery.'):bi('已闭合（旧记录缺少编辑坐标）。','Closed (edit coordinates unavailable in snapshot).'));
    }else{
      msg.append(cands.length?bi('候选未通过校验，保留原 Gap。','Candidate failed validation; original gap retained.'):bi('此工具未修改该位点。','No edit made by this tool at this locus.'));
    }
    body.append(msg);
  }

  for(const i of order){
    const code=normState(attempts[i][0]),st=states[code],btn=node(order.length===1?'span':'button','st-'+code);
    const dot=node('i','gap-dot is-'+code);dot.setAttribute('aria-hidden','true');
    btn.append(dot,document.createTextNode(tools[i][0]+' · '),bi(st[1],st[2]));
    if(manual&&manual.attempts[i].tool===manual.selected){btn.append(bi(' · 本批采用',' · Selected'))}
    if(order.length>1){btn.type='button';btn.addEventListener('click',()=>select(i))}
    tabs.append(btn);buttons.push([i,btn]);
  }
  select(order.includes(initial)?initial:order[0]);
}

document.addEventListener('cgat-story-open',ev=>{
  const b=ev.detail.button;
  if(b.dataset.manualGap){const data=document.getElementById(b.dataset.manualGap);if(data)inspector(ev.target,0,0,null,JSON.parse(data.textContent));return}
  if(b.dataset.storyOpen==='auto-gap-inspector')inspector(ev.target,+b.dataset.gapChr,+b.dataset.gapIndex,b.hasAttribute('data-tool-index')?+b.dataset.toolIndex:null);
});
})();</script>'''
