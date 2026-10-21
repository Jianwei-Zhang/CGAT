import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveTrackCtgOrient } from "./track-label-geometry.js";

// Inspection is independent of split eligibility (including single-base contigs).
export function resolveContigChrAlignmentModel(assembly, context) {
  const target = typeof context === "object" ? context : { assemblyCtgId: context };
  const support = target.trackRole === "support";
  const pool = support ? assembly?.supportChrCtgs : assembly?.chrCtgs;
  const ctg = pool?.find((c) => Number(c.assemblyCtgId) === Number(target.assemblyCtgId));
  if (!ctg || Number(ctg.memberCount || 1) !== 1
    || !support && (assembly.hiddenPrimaryCtgIds || []).map(Number).includes(Number(target.assemblyCtgId))) return null;
  const sourceStart = Number(ctg.sourceFragment?.sourceStart ?? 1);
  const sourceEnd = Number(ctg.sourceFragment?.sourceEnd ?? ctg.totalLength);
  if (!Number.isSafeInteger(sourceStart) || !Number.isSafeInteger(sourceEnd) || sourceStart < 1 || sourceEnd < sourceStart) return null;
  const prefs = resolveTrackPrefs(assembly.trackView);
  return { assemblyCtgId: Number(target.assemblyCtgId), sourceStart, sourceEnd,
    colorRole: support ? "companion" : "primary",
    sourceSeqId: Number(ctg.originSourceSeqId ?? ctg.sourceFragment?.sourceSeqId) || null,
    orient: resolveTrackCtgOrient(ctg), chrName: String(assembly.selectedChrName || ""),
    sourceChrName: ctg.assignedChrName === null ? "unplaced" : String(ctg.assignedChrName || assembly.selectedChrName || "unplaced"),
    minAlignmentLength: prefs.alignmentLength, minIdentityPct: prefs.minIdentityPct };
}

const html = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
const bp = (v) => Number(v).toLocaleString("en-US");
export const chrAlignmentCopy = {
  zh: {title:"跨 chr 比对…",chr:"chr",coverage:"覆盖率",identity:"一致性",action:"操作",add:"添加",locate:"定位",show:"显示已有",close:"关闭",
    existing:"已存在",contained:"已有包含区间",overlap:"区间重叠",hidden:"已隐藏",confirm:"确认添加",overlapConfirm:"目标中已有部分重叠区间。再次点击“确认添加”继续。",
    loading:"正在读取比对…",empty:"当前筛选下没有其他 chr 比对。",stale:"当前对象已变化，请重新打开面板。",done:"已添加到目标 chr，原对象保留；可在目标 chr 撤销。",
    shown:"已显示已有对象，未创建重复对象；可在目标 chr 撤销。",filter:"沿用主视图比对筛选",identityHint:"按原始比对块加权，非截取区间的逐碱基一致性。",failed:"操作失败，请重试。"},
  en: {title:"Cross-chr alignments…",chr:"chr",coverage:"Coverage",identity:"Identity",action:"Action",add:"Add",locate:"Locate",show:"Show existing",close:"Close",
    existing:"Exists",contained:"Containing interval exists",overlap:"Overlapping interval",hidden:"Hidden",confirm:"Confirm add",overlapConfirm:"An overlapping source interval exists. Click Confirm add to continue.",
    loading:"Loading alignments…",empty:"No other chr alignments pass the current filters.",stale:"Contig changed. Reopen the panel.",done:"Added to the target chr; original retained. Undo from the target chr.",
    shown:"Existing object shown without creating a duplicate. Undo from the target chr.",filter:"Using main-view alignment filters",identityHint:"Weighted original-hit identity, not per-base identity of the clipped interval.",failed:"Operation failed. Try again."},
};
export function chrAlignmentAction(item) {
  if (item.presence === "hidden" || item.presence === "contained" && item.existingHidden) return "show";
  return ["existing","contained"].includes(item.presence) ? "locate" : "add";
}

export function renderChrAlignmentPreview(source, item, sourceRole = "primary") {
  const X=64,W=632,Y=116;
  const q=(cut)=>X+W*(item.orient==="-" ? (source.sourceEnd-cut)/(source.sourceEnd-source.sourceStart+1) : (cut-source.sourceStart+1)/(source.sourceEnd-source.sourceStart+1));
  const r=(cut)=>X+W*cut/Math.max(1,item.refLength);
  const bands=(item.hits||[]).map(h=>{
    const a=q(h.queryStart-1),b=q(h.queryEnd),left=h.strand==="-"?b:a,right=h.strand==="-"?a:b;
    return `<polygon class="manual-split-band" points="${r(h.refStart-1)},56 ${r(h.refEnd)},56 ${right},${Y} ${left},${Y}"/>`;
  }).join("");
  return `<svg class="manual-split-svg" data-contig-role="${sourceRole === "companion" ? "companion" : "primary"}" viewBox="0 0 720 166" role="img" aria-label="${html(source.name)} / ${html(item.chrName)}">
    <text x="64" y="30">${html(item.chrName)}</text><text x="696" y="30" text-anchor="end">${bp(item.refLength)} bp</text>
    <rect x="64" y="44" width="632" height="12" class="manual-split-ref"/>${bands}
    <text x="64" y="105">${html(source.name)} (${item.orient === "-" ? "−" : "+"})</text>
    <rect x="64" y="116" width="632" height="16" class="manual-split-contig"/>
    <text x="64" y="158">${bp(item.orient==="-"?source.sourceEnd:source.sourceStart)}</text>
    <text x="696" y="158" text-anchor="end">${bp(item.orient==="-"?source.sourceStart:source.sourceEnd)}</text></svg>`;
}

// Read-only loading/row selection; the only write is an explicitly clicked Add/Show.
export function openContigChrAlignments(host,{locale="zh",sourceRole="primary",load,add,locate,isCurrent=()=>true}={}) {
  const doc=host?.ownerDocument||globalThis.document;
  if(!doc?.body||doc.querySelector(".contig-chr-dialog")) return Promise.resolve(false);
  const labels=chrAlignmentCopy[locale==="en"?"en":"zh"],previousFocus=doc.activeElement;
  const dialog=doc.createElement("dialog");dialog.className="app-dialog contig-chr-dialog";
  dialog.setAttribute("aria-label",labels.title);
  dialog.innerHTML=`<h2 class="app-dialog-title">${labels.title}</h2><div data-chr-table class="contig-chr-table"></div>
    <div data-chr-preview></div><p class="contig-chr-filter">${labels.filter}</p>
    <p data-chr-error role="alert"></p><p data-chr-status role="status"></p>
    <div class="app-dialog-actions"><button type="button" class="button ghost" data-chr-close>${labels.close}</button></div>`;
  doc.body.append(dialog);
  const el=(s)=>dialog.querySelector(s),error=el("[data-chr-error]"),status=el("[data-chr-status]");
  let closed=false,busy=false,data=null,selected=0,overlapChr=null,resolveDone;
  const done=new Promise(resolve=>{resolveDone=resolve;});
  const finish=()=>{if(closed)return;closed=true;if(dialog.open)dialog.close();dialog.remove();if(previousFocus?.isConnected)previousFocus.focus();resolveDone(true);};
  const renderPreview=()=>{el("[data-chr-preview]").innerHTML=data?.items[selected]?renderChrAlignmentPreview(data.source,data.items[selected],sourceRole):"";
    dialog.querySelectorAll("tr[data-chr-index]").forEach(row=>row.setAttribute("aria-selected",String(Number(row.getAttribute("data-chr-index"))===selected)));};
  const renderTable=()=>{
    const items=data?.items||[];
    el("[data-chr-table]").innerHTML=items.length?`<table><thead><tr><th>${labels.chr}</th><th>${labels.coverage}</th><th title="${labels.identityHint}">${labels.identity}</th><th>${labels.action}</th></tr></thead><tbody>${items.map((item,i)=>{
      const action=chrAlignmentAction(item),hint=labels[item.presence]||"";
      const label=overlapChr===item.chrName?labels.confirm:labels[action];
      return `<tr data-chr-index="${i}" tabindex="0" aria-selected="${i===selected}"><td>${html(item.chrName)}</td><td>${Number(item.coveragePercent).toFixed(1)}%</td><td title="${labels.identityHint}">≈${Number(item.identityPercent).toFixed(1)}%</td>
        <td>${hint?`<span class="contig-chr-presence">${hint}</span>`:""}<button type="button" class="button tiny" data-chr-action="${i}">${label}</button></td></tr>`;
    }).join("")}</tbody></table>`:`<p>${labels.empty}</p>`;
    renderPreview();
  };
  const refresh=async()=>{
    const result=await load();if(closed)return;
    if(!isCurrent())throw new Error(labels.stale);
    const previous=data?.items[selected]?.chrName;data=result;selected=Math.max(0,data.items.findIndex(i=>i.chrName===previous));renderTable();
  };
  const selectRow=(i)=>{if(busy||!data?.items[i])return;selected=i;overlapChr=null;error.textContent="";renderPreview();
    dialog.querySelectorAll("[data-chr-action]").forEach(button=>{button.textContent=labels[chrAlignmentAction(data.items[Number(button.getAttribute("data-chr-action"))])];});
  };
  const act=async(index)=>{
    if(busy||closed)return;
    if(!isCurrent()){error.textContent=labels.stale;return;}
    const item=data?.items[index];if(!item)return;selected=index;renderPreview();
    const action=chrAlignmentAction(item);
    if(action==="add"&&item.presence==="overlap"&&overlapChr!==item.chrName){overlapChr=item.chrName;error.textContent=labels.overlapConfirm;renderTable();el(`[data-chr-action="${index}"]`)?.focus();return;}
    busy=true;error.textContent="";status.textContent="";dialog.querySelectorAll("button").forEach(n=>{n.disabled=true;});
    try {
      if(action==="locate"){await locate(item);finish();return;}
      const result=await add({assemblyCtgId:data.source.assemblyCtgId,sourceSeqId:data.source.sourceSeqId,sourceChrName:data.source.assignedChrName || "unplaced",sourceStart:data.source.sourceStart,sourceEnd:data.source.sourceEnd,orient:data.source.orient,targetChrName:item.chrName,allowOverlap:item.presence==="overlap",revealContained:item.presence==="contained"},{showExisting:action==="show"});
      if(result===false)throw new Error(labels.failed);
      overlapChr=null;await refresh();if(!closed){status.textContent=result?.changed===false?labels.existing:action==="show"?labels.shown:labels.done;el(`[data-chr-action="${selected}"]`)?.focus();}
    } catch(cause){if(!closed)error.textContent=String(cause?.message||cause);}
    finally{busy=false;if(!closed)dialog.querySelectorAll("button").forEach(n=>{n.disabled=false;});}
  };
  dialog.addEventListener("click",event=>{
    const action=event.target?.closest?.("[data-chr-action]");
    if(action){void act(Number(action.getAttribute("data-chr-action")));return;}
    const row=event.target?.closest?.("[data-chr-index]");if(row)selectRow(Number(row.getAttribute("data-chr-index")));
  });
  dialog.addEventListener("keydown",event=>{
    if(["Enter"," "].includes(event.key)&&event.target?.matches?.("tr[data-chr-index]")){event.preventDefault();selectRow(Number(event.target.getAttribute("data-chr-index")));}
  });
  el("[data-chr-close]").addEventListener("click",()=>{if(!busy)finish();});
  dialog.addEventListener("cancel",e=>{e.preventDefault();if(!busy)finish();});
  dialog.addEventListener("close",()=>{if(!busy)finish();});
  el("[data-chr-table]").textContent=labels.loading;
  dialog.showModal();el("[data-chr-close]").focus();
  void refresh().catch(cause=>{if(!closed){el("[data-chr-table]").textContent="";error.textContent=String(cause?.message||cause);}});
  return done;
}
