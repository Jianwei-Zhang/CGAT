"""Compact 07: unified refinement card — single-row tool tabs, 14px chromosome tracks, icon matrix, shared inspector."""
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
        f'<a class="refine-ext-link" href="{esc(degap_href)}" target="_blank" rel="noopener noreferrer">'
        + bi('DEGAP 报告 ↗', 'DEGAP report ↗') + '</a>'
    ) if degap_href else ''

    view_switch = (
        '<div class="refine-view-switch" role="group" aria-label="View mode">'
        '<button type="button" data-gap-view="track" aria-pressed="true">' + bi('分布图', 'Tracks') + '</button>'
        '<button type="button" data-gap-view="matrix" aria-pressed="false">' + bi('对比表', 'Matrix') + '</button>'
        '</div>'
    ) if payload['chr'] else ''

    top_bar = (
        '<div class="refine-bar">'
        '<div class="refine-bar-left">'
        '<div class="refine-tabs" data-gap-tool-tabs></div>'
        '<span class="refine-matrix-lbl" data-gap-matrix-lbl hidden>' + bi('跨工具逐位点对比（点击图标查看详情）', 'Cross-tool comparison (click any icon for details)') + '</span>'
        '</div>'
        '<div class="refine-bar-right">' + degap_top_link + view_switch + '</div>'
        '</div>'
    )

    legend_bits = [
        '<span class="legend-item" data-legend-track><i class="gap-key is-chr"></i>' + bi('LGZ 序列', 'LGZ track') + '</span>',
        '<span class="legend-item"><i class="gap-key is-closed"></i>' + bi('已闭合', 'Closed') + '</span>',
        '<span class="legend-item"><i class="gap-key is-retained"></i>' + bi('未闭合', 'Unclosed') + '</span>',
    ]
    if 'unknown' in seen_states:
        legend_bits.append('<span class="legend-item"><i class="gap-key is-unknown"></i>' + bi('未验证', 'Unverified') + '</span>')
    legend_row = (
        '<div class="refine-legend">'
        '<div class="legend-row" style="margin:0">' + ''.join(legend_bits) + '</div>'
        '<span class="refine-hint" data-legend-track>' + bi('点击位点查看比对证据', 'Click locus for evidence') + '</span>'
        '</div>'
    ) if payload['chr'] else ''

    ruler = (
        '<div class="gap-axis"><span>' + bi('染色体', 'Chromosome') + '</span><span class="story-ruler">'
        + ''.join(f'<span>{esc(fmt_bp_short(round(max_len * i / 4)))}</span>' for i in range(5))
        + '</span></div>'
    ) if payload['chr'] else ''
    zbtn = zoom_button('07 自动精修 · 放大视图', '07 Automatic refinement · Enlarged view') if payload['chr'] else ''
    track_view = (
        '<div class="gap-frame" data-zoom-frame="1" data-gap-panel="track">'
        + ruler + '<div data-gap-rows></div>' + zbtn + '</div>'
    )
    matrix_view = '<div class="gap-matrix-wrap" data-gap-panel="matrix" hidden></div>'

    body = (
        '<div id="auto-gap-story">'
        + top_bar + legend_row + track_view + matrix_view
        + '<noscript>' + bi('启用 JavaScript 以查看每个原始 gap。', 'Enable JavaScript to inspect individual gaps.') + '</noscript>'
        '</div>'
        '<template id="auto-gap-inspector" data-title="Gap"><div data-gap-inspector></div></template>'
        '<template id="gap-svg-seed"><svg></svg></template>'
        '<script type="application/json" id="auto-gap-data">' + data + '</script>'
        + STYLE + SCRIPT
    )
    return section('auto-refinement', '07', '自动精修', 'Automatic refinement', body, right=note)


STYLE = '''<style>
.refine-bar{display:flex;align-items:center;justify-content:space-between;gap:.55rem .85rem;flex-wrap:wrap;margin-bottom:.55rem}
.refine-bar-left{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap;min-width:0}
.refine-bar-right{display:inline-flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-left:auto}
.refine-tabs{display:inline-flex;align-items:center;gap:.35rem;flex-wrap:wrap}
.refine-tabs[hidden],.refine-matrix-lbl[hidden]{display:none}
.refine-tab{display:inline-flex;align-items:center;gap:.4rem;padding:4px 10px;border:1px solid var(--border-subtle);border-radius:999px;background:var(--surface-subtle);color:var(--text-secondary);font-family:var(--font-sans);font-size:var(--text-sm);font-weight:500;line-height:1.3;cursor:pointer;transition:border-color .12s,background .12s,color .12s,box-shadow .12s}
.refine-tab:hover{border-color:var(--border-default);background:var(--surface-panel);color:var(--text-primary)}
.refine-tab[aria-pressed="true"]{border-color:var(--brand);background:var(--surface-panel);color:var(--text-primary);font-weight:600;box-shadow:inset 0 0 0 1px var(--brand)}
.refine-tab-cnt{padding:0 6px;border-radius:999px;background:var(--surface-muted);color:var(--text-muted);font-family:var(--font-mono);font-size:var(--text-xs);font-weight:600;line-height:1.45;font-variant-numeric:tabular-nums}
.refine-tab-cnt.is-ok{background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.refine-tab-cnt.is-err{background:var(--tone-warn-bg);color:var(--tone-warn-ink)}
.refine-matrix-lbl{font-size:var(--text-sm);color:var(--text-muted)}
.refine-ext-link{display:inline-flex;align-items:center;padding:3px 9px;border-radius:999px;border:1px solid var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-size:var(--text-xs);font-weight:600;text-decoration:none;white-space:nowrap}
.refine-ext-link:hover{filter:brightness(.97);text-decoration:none}
.refine-view-switch{display:inline-flex;padding:2px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-subtle);gap:2px}
.refine-view-switch button{padding:3px 10px;border:0;border-radius:4px;background:transparent;color:var(--text-secondary);font-family:var(--font-sans);font-size:var(--text-xs);font-weight:500;line-height:1.3;cursor:pointer;transition:background .12s,color .12s}
.refine-view-switch button[aria-pressed="true"]{background:var(--surface-panel);color:var(--text-primary);font-weight:600;box-shadow:0 1px 2px rgba(15,23,42,.08)}
.refine-legend{display:flex;align-items:center;justify-content:space-between;gap:.45rem .85rem;flex-wrap:wrap;margin:0 0 .5rem}
.refine-hint{font-size:.75rem;color:var(--text-muted)}
.gap-key{display:inline-block;width:11px;height:8px;border-radius:2px;vertical-align:middle;flex-shrink:0}
.gap-key.is-chr{background:var(--ds-0)}
.gap-key.is-closed{background:var(--gen-closed)}
.gap-key.is-retained{background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px);box-shadow:inset 0 0 0 1px var(--border-strong)}
.gap-key.is-unknown{background:var(--surface-muted);box-shadow:inset 0 0 0 1px var(--border-strong)}
.gap-dot{display:inline-block;width:9px;height:9px;border-radius:50%;flex-shrink:0}
.gap-dot.is-closed{background:var(--gen-closed)}
.gap-dot.is-retained{background:var(--surface-panel);border:1.8px solid var(--border-strong)}
.gap-dot.is-unknown{width:8px;height:2.5px;border-radius:1px;background:var(--border-strong)}
.gap-frame{position:relative;border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow:hidden;padding-bottom:2.3rem}
.gap-frame[hidden],.gap-matrix-wrap[hidden]{display:none}
.gap-axis,.gap-row{display:grid;grid-template-columns:168px minmax(0,1fr);gap:.75rem;align-items:center}
.gap-axis{padding:.52rem .85rem .44rem;background:var(--surface-subtle);border-bottom:1px solid var(--border-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600}
.gap-axis .story-ruler{font-weight:500;color:var(--text-muted);font-size:.75rem}
.gap-row{border-bottom:1px solid var(--border-subtle);padding:.68rem .85rem;transition:background .12s}
.gap-row:last-child{border-bottom:0}
.gap-row:hover{background:var(--surface-subtle)}
.gap-chr-meta{min-width:0}
.gap-chr-head{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap}
.gap-chr-meta b{font:600 .85rem/1.25 var(--font-mono);color:var(--text-primary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gap-chr-pill{display:inline-flex;align-items:center;padding:1px 6px;border-radius:999px;font-size:.71rem;font-weight:500;font-variant-numeric:tabular-nums;border:1px solid var(--border-subtle);background:var(--surface-subtle);color:var(--text-muted);white-space:nowrap}
.gap-chr-pill.has-closed{border-color:var(--tone-ok-line);background:var(--tone-ok-bg);color:var(--tone-ok-ink);font-weight:600}
.gap-chr-meta small{display:block;margin-top:.14rem;font-size:.75rem;color:var(--text-muted);font-variant-numeric:tabular-nums}
.gap-track-box{min-width:0;padding:.24rem 0;background-image:linear-gradient(to right,var(--border-subtle) 1px,transparent 1px);background-size:25% 100%}
.gap-track{position:relative;height:14px;border-radius:2px;background:var(--ds-0);min-width:8px}
.gap-mark{position:absolute;top:0;height:14px;padding:0;border:0;border-radius:2px;cursor:pointer;transition:transform .1s,filter .1s}
.gap-mark::after{content:"";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:max(100%,16px);height:26px}
.gap-mark.st-closed{min-width:7px;top:-2px;height:18px;border-radius:2.5px;background:var(--gen-closed);box-shadow:0 0 0 1.5px var(--surface-panel);z-index:3}
.gap-mark.st-retained{min-width:6px;background:repeating-linear-gradient(135deg,var(--border-strong) 0 1.5px,var(--surface-panel) 1.5px 3.5px);box-shadow:inset 0 0 0 1px var(--border-strong),0 0 0 1px var(--surface-panel);z-index:2}
.gap-mark.st-unknown{min-width:6px;background:var(--surface-muted);box-shadow:inset 0 0 0 1px var(--border-strong);z-index:2}
.gap-mark:hover{transform:scaleY(1.16);filter:brightness(1.06);z-index:5}
.gap-mark:focus-visible{outline:2px solid var(--focus-ring);outline-offset:1px;z-index:5}
.gap-matrix-wrap{border:1px solid var(--border-subtle);border-radius:var(--radius);background:var(--surface-panel);overflow-x:auto}
.gap-matrix-table{width:100%;border-collapse:collapse;font-size:.83rem;text-align:left}
.gap-matrix-table th,.gap-matrix-table td{padding:7px 12px;border-bottom:1px solid var(--border-subtle);vertical-align:middle}
.gap-matrix-table thead th{background:var(--surface-subtle);color:var(--text-secondary);font-size:.78rem;font-weight:600;white-space:nowrap}
.gap-matrix-table th.is-tool,.gap-matrix-table td.is-tool{text-align:center}
.gap-th-cnt{display:inline-block;margin-left:.32rem;padding:0 5px;border-radius:999px;background:var(--surface-muted);color:var(--text-muted);font:600 .7rem/1.4 var(--font-mono);font-variant-numeric:tabular-nums}
.gap-th-cnt.is-ok{background:var(--tone-ok-bg);color:var(--tone-ok-ink)}
.gap-matrix-table tbody tr:hover{background:var(--surface-subtle)}
.gap-matrix-table tbody tr:last-child>*{border-bottom:0}
.gap-matrix-chr{font:600 .82rem/1.25 var(--font-mono);color:var(--text-primary);white-space:nowrap}
.gap-matrix-pos{font:500 .79rem/1.25 var(--font-mono);color:var(--text-secondary);white-space:nowrap;font-variant-numeric:tabular-nums}
.gap-matrix-len{font-size:.75rem;color:var(--text-muted);margin-left:.4rem;font-variant-numeric:tabular-nums}
.gap-ico-btn{display:inline-grid;place-items:center;width:26px;height:26px;padding:0;border:1px solid transparent;border-radius:50%;background:transparent;cursor:pointer;transition:background .12s,border-color .12s,transform .1s}
.gap-ico-btn:hover{transform:scale(1.1);background:var(--brand-soft);border-color:var(--brand)}
.gap-ico-btn.st-closed{color:var(--gen-closed)}
.gap-ico-btn.st-retained{color:var(--border-strong)}
.gap-ico-btn.st-unknown{color:var(--text-muted)}
.gap-matrix-more{display:flex;justify-content:center;padding:.55rem;border-top:1px solid var(--border-subtle);background:var(--surface-subtle)}
.gap-matrix-more button{padding:4px 12px;border:1px solid var(--border-default);border-radius:var(--radius-sm);background:var(--surface-panel);color:var(--accent);font-family:var(--font-sans);font-size:var(--text-sm);font-weight:500;line-height:1.3;cursor:pointer}
.gap-info-sub{margin:0 0 .55rem;font-size:var(--text-sm);color:var(--text-secondary);font-variant-numeric:tabular-nums;display:flex;flex-wrap:wrap;align-items:center;gap:.35rem .75rem}
.gap-info-sub code{font-size:var(--text-xs)}
.gap-info-head{display:flex;align-items:center;justify-content:space-between;gap:.55rem;flex-wrap:wrap;padding-bottom:.65rem;margin-bottom:.65rem;border-bottom:1px solid var(--border-subtle)}
.gap-tools{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap}
.gap-tools button,.gap-tools>span{display:inline-flex;align-items:center;gap:.38rem;border:1px solid var(--border-default);border-radius:6px;background:var(--surface-panel);color:var(--text-secondary);padding:.36rem .72rem;font-family:var(--font-sans);font-size:var(--text-sm);font-weight:600;line-height:1.25}
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
.story-zoom-stage .gap-axis,.story-zoom-stage .gap-row{grid-template-columns:196px minmax(0,1fr);gap:0;padding:0;align-items:stretch}
.story-zoom-stage .gap-axis{position:sticky;top:0;z-index:8;background:var(--surface-subtle)}
.story-zoom-stage .gap-axis>:first-child{position:sticky;left:0;z-index:9;background:var(--surface-subtle);padding:.55rem .7rem .45rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;align-items:center}
.story-zoom-stage .gap-axis .story-ruler{margin:.55rem 1rem .45rem .8rem;min-width:0}
.story-zoom-stage .gap-chr-meta{position:sticky;left:0;z-index:5;background:var(--surface-panel);padding:.85rem .7rem .85rem 1rem;border-right:1px solid var(--border-subtle);box-shadow:4px 0 8px -4px rgba(15,23,42,.12);display:flex;flex-direction:column;justify-content:center}
.story-zoom-stage .gap-row:hover .gap-chr-meta{background:var(--surface-subtle)}
.story-zoom-stage .gap-track-box{margin:.85rem 1rem .85rem .8rem;z-index:1;display:flex;align-items:center}
.story-zoom-stage .gap-track{height:18px}
.story-zoom-stage .gap-mark{height:18px}
.story-zoom-stage .gap-mark.st-closed{height:22px;top:-2px;min-width:8px}
.story-zoom-stage .gap-mark.st-retained,.story-zoom-stage .gap-mark.st-unknown{min-width:7px}
@media (max-width:760px){
  .gap-axis,.gap-row{grid-template-columns:108px minmax(0,1fr);gap:.45rem;padding-left:.65rem;padding-right:.65rem}
  .story-zoom-stage .gap-axis,.story-zoom-stage .gap-row{grid-template-columns:136px minmax(0,1fr);gap:0;padding:0}
}
</style>'''

SCRIPT = r'''<script data-cgat-ui="1" data-gap-story-ui="1">(()=>{
const card=document.getElementById('auto-gap-story'), info=card?JSON.parse(document.getElementById('auto-gap-data').textContent):{tools:[],chr:[]};
const tools=info.tools, chr=info.chr, tabsBox=card?.querySelector('[data-gap-tool-tabs]'), matrixLbl=card?.querySelector('[data-gap-matrix-lbl]'), rows=card?.querySelector('[data-gap-rows]'), matrixBox=card?.querySelector('[data-gap-panel="matrix"]'), trackBox=card?.querySelector('[data-gap-panel="track"]');
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
function bi(zh,en){const n=node('span');n.append(node('span','t-zh',zh),node('span','t-en',en));return n}
const fmt=n=>Number(n).toLocaleString('en-US');
const fmtShort=n=>{const v=Number(n);if(v>=1e6)return (v/1e6).toFixed(2)+' Mb';if(v>=1e3)return (v/1e3).toFixed(1)+' kb';return fmt(v)+' bp'};
const pos=s=>`${fmt(s[0]+1)}–${fmt(s[1])}`;
const states={closed:['●','已闭合','Closed'],retained:['○','未闭合','Unclosed'],unknown:['—','未验证','Unverified']};
const normState=c=>c==='partial'?'retained':c;
const reasons={missing_native_candidate:['原生结果缺少候选序列。','Native result lacked the candidate sequence.'],candidate_shorter_than_anchors:['候选短于侧翼锚点。','Candidate was shorter than a required flank anchor.'],native_anchors_do_not_reconstruct_baseline:['候选侧翼与原路径不一致。','The native flanks did not reproduce the baseline.'],native_junction_exterior_does_not_reconstruct_baseline:['接缝外围未与原路径吻合。','The junction exteriors did not match the baseline.'],native_integration_slice_disagrees_with_full_candidate:['取用片段与完整候选不一致。','The integration slice differed from the full candidate.'],unproven_native_overlap:['未能验证末端重叠。','The proposed overlap could not be verified.'],overlap_crosses_another_gap:['重叠区跨越了另一个 gap。','The overlap crossed another gap.'],candidate_has_no_filled_bases:['候选没有非 N 的填补碱基。','Candidate supplied no non-N bases.'],candidate_does_not_change_baseline:['候选与原路径相同。','Candidate did not change the baseline.'],native_anchor_absent:['候选中找不到对应的侧翼锚点。','The required flank anchor was absent.'],native_anchor_not_unique:['候选中的侧翼锚点不唯一。','The flank anchor was not unique in the candidate.'],gap_and_flank_cannot_be_separated:['无法将 gap 修改与已知侧翼可靠分开。','The gap edit could not be separated reliably from the known flank.'],native_change_not_bound_to_an_original_gap:['修改无法归属到原始 gap。','The change could not be bound to an original gap.'],projected_gap_unchanged:['候选投影到 gap 后没有改动。','The candidate projection did not change the gap.']};
const rank={closed:0,retained:1,unknown:2};
function attrs(n,ci,gi,ti){n.dataset.storyOpen='auto-gap-inspector';n.dataset.gapChr=ci;n.dataset.gapIndex=gi;if(ti!==undefined&&ti!==null)n.dataset.toolIndex=ti}
const maxLength=chr.reduce((m,r)=>Math.max(m,r[1]||0),1);
const totalLoci=chr.reduce((s,r)=>s+r[2].length,0);
const ns=document.getElementById('gap-svg-seed').content.firstElementChild.namespaceURI;
function svgEl(type,atts,txt){const n=document.createElementNS(ns,type);Object.entries(atts).forEach(([k,v])=>n.setAttribute(k,v));if(txt!==undefined)n.textContent=txt;return n}
let activeTool=0, matrixShown=80, matrixBuilt=false;

function toolCounts(ti){
  let closed=0, unknown=0;
  chr.forEach(([, , gaps])=>gaps.forEach(g=>{const c=normState(g[3][ti][0]);if(c==='closed')closed++;else if(c==='unknown')unknown++;}));
  return {closed, unknown};
}

function renderToolTabs(){
  if(!tabsBox||!tools.length)return;
  tabsBox.replaceChildren();
  tools.forEach(([tname,tst],ti)=>{
    const {closed, unknown}=toolCounts(ti);
    const btn=node('button','refine-tab');btn.type='button';btn.setAttribute('aria-pressed',String(ti===activeTool));
    btn.append(node('span',null,tname));
    const cnt=node('span','refine-tab-cnt');
    if(totalLoci>0&&unknown===totalLoci){
      cnt.classList.add('is-err');
      cnt.append(tst==='failed'?bi('失败','Failed'):bi('未验证','N/A'));
    }else{
      if(closed>0)cnt.classList.add('is-ok');
      cnt.textContent=`${closed}/${totalLoci}`;
    }
    btn.append(cnt);
    btn.addEventListener('click',()=>{activeTool=ti;renderToolTabs();draw();});
    tabsBox.append(btn);
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
    if(len){
      rail.style.width=(100*len/maxLength)+'%';
      gaps.forEach(([id,a,b,attempts],gi)=>{
        const code=normState(attempts[tid][0]), state=states[code], bp=b-a;
        const title=`${name} · #${gi+1} · ${pos([a,b])} (${fmt(bp)} bp) · ${state[1]} / ${state[2]}`;
        const btn=node('button','gap-mark st-'+code);btn.type='button';
        attrs(btn,ci,gi,tid);btn.title=title;btn.setAttribute('aria-label',title);
        btn.style.left=(100*a/len)+'%';
        btn.style.width=(100*bp/len)+'%';
        rail.append(btn);
      });
    }else{
      rail.append(bi('未记录 LGZ 长度','LGZ length unavailable'));
    }
    box.append(rail);
    row.append(box);rows.append(row);
  });
}

function statusIcon(code){
  const svg=svgEl('svg',{width:'18',height:'18',viewBox:'0 0 20 20',fill:'none','aria-hidden':'true'});
  if(code==='closed'){
    svg.append(svgEl('circle',{cx:'10',cy:'10',r:'8.5',fill:'currentColor'}));
    svg.append(svgEl('path',{d:'M6.2 10.2L8.8 12.8L14 7.4',stroke:'#fff','stroke-width':'2.1','stroke-linecap':'round','stroke-linejoin':'round'}));
  }else if(code==='retained'){
    svg.append(svgEl('circle',{cx:'10',cy:'10',r:'7.2',stroke:'currentColor','stroke-width':'1.7'}));
  }else{
    svg.append(svgEl('line',{x1:'6',y1:'10',x2:'14',y2:'10',stroke:'currentColor','stroke-width':'2','stroke-linecap':'round'}));
  }
  return svg;
}

function drawMatrix(){
  if(!matrixBox)return;
  matrixBox.replaceChildren();
  const flat=[];
  chr.forEach(([name, , gaps],ci)=>gaps.forEach((g,gi)=>flat.push([name,ci,gi,g])));
  const tbl=node('table','gap-matrix-table'), thead=node('thead'), hr=node('tr');
  const h1=node('th');h1.scope='col';h1.append(bi('染色体','Chr'));
  const h2=node('th');h2.scope='col';h2.append(bi('位置与长度','Position & length'));
  hr.append(h1,h2);
  tools.forEach(([tname],ti)=>{
    const {closed, unknown}=toolCounts(ti);
    const th=node('th','is-tool');th.scope='col';
    th.append(document.createTextNode(tname));
    if(totalLoci>0&&unknown<totalLoci){
      const c=node('span','gap-th-cnt'+(closed?' is-ok':''),`${closed}/${totalLoci}`);
      th.append(c);
    }
    hr.append(th);
  });
  thead.append(hr);tbl.append(thead);
  const tbody=node('tbody');
  flat.slice(0,matrixShown).forEach(([name,ci,gi,[id,a,b,attempts]])=>{
    const tr=node('tr');
    const c1=node('td','gap-matrix-chr',`${name} #${gi+1}`);c1.title=id;
    const c2=node('td');
    c2.append(node('span','gap-matrix-pos',pos([a,b])),node('span','gap-matrix-len',fmtShort(b-a)));
    tr.append(c1,c2);
    attempts.forEach((att,ti)=>{
      const td=node('td','is-tool'), code=normState(att[0]), st=states[code];
      const btn=node('button','gap-ico-btn st-'+code);btn.type='button';
      const tip=`${name} #${gi+1} · ${tools[ti][0]} · ${st[1]} / ${st[2]}`;
      btn.title=tip;btn.setAttribute('aria-label',tip);
      attrs(btn,ci,gi,ti);
      btn.append(statusIcon(code));
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
  renderToolTabs();
  draw();
  card.querySelectorAll('[data-gap-view]').forEach(btn=>{
    btn.addEventListener('click',()=>{
      const mode=btn.dataset.gapView, isTrack=mode==='track';
      card.querySelectorAll('[data-gap-view]').forEach(b=>b.setAttribute('aria-pressed',String(b===btn)));
      if(tabsBox)tabsBox.hidden=!isTrack;
      if(matrixLbl)matrixLbl.hidden=isTrack;
      card.querySelectorAll('[data-legend-track]').forEach(el=>el.hidden=!isTrack);
      if(trackBox)trackBox.hidden=!isTrack;
      if(matrixBox){matrixBox.hidden=isTrack;if(!isTrack&&!matrixBuilt)drawMatrix();}
    });
  });
}

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
