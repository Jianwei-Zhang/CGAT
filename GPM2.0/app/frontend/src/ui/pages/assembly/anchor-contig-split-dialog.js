import { normalizeAnchorCuts, anchorSplitRanges } from "./anchor-contig-split.js";
const escape = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[c]);
const copy = {
  zh: { title: "锚定分割 Contig", hint: "点击 Contig 或比对边界设置／取消锚点。红线仅预览切口，确认后才分割。", fixed: "使用当前 Contig 已激活的锚点；不会分割锚线另一端的 Contig。", confirm: "确认分割", cancel: "取消", empty: "没有有效内部锚点", stale: "目标已变化，请重新打开。", failed: "分割未完成", count: "结果片段（源区间）" },
  en: { title: "Anchor-Based Contig Split", hint: "Click the contig or alignment edges to toggle anchors. Red lines preview cuts; only confirmation splits.", fixed: "Uses this contig's active anchors only; the opposite anchor endpoint is not split.", confirm: "Confirm split", cancel: "Cancel", empty: "No internal anchors", stale: "Target changed. Reopen this dialog.", failed: "Split was not completed", count: "Result fragments (source ranges)" },
};
export function renderAnchorSplitPreview(model, cuts) {
  const x = (cut) => 40 + 640 * (model.orient === "-" ? 1-(cut-model.sourceStart+1)/(model.sourceEnd-model.sourceStart+1)
    : (cut-model.sourceStart+1)/(model.sourceEnd-model.sourceStart+1));
  const anchors = normalizeAnchorCuts(cuts, model), selected = new Set(anchors);
  const candidates = normalizeAnchorCuts([...(model.hits || []).flatMap((h) => [h.queryStart-1,h.queryEnd]), ...anchors],model);
  return `<svg data-anchor-split-svg viewBox="0 0 720 160" style="width:100%;display:block" aria-label="${escape(model.name)}">
    <text x="40" y="20">${escape(model.name)} (${model.orient})</text>
    ${(model.hits || []).map((h) => `<polygon fill="var(--ctg-support-fill,#d8c9a6)" opacity=".5" points="${40+640*(h.refStart-1)/Math.max(1,model.refLength)},40 ${40+640*h.refEnd/Math.max(1,model.refLength)},40 ${x(h.strand === "-" ? h.queryStart-1 : h.queryEnd)},100 ${x(h.strand === "-" ? h.queryEnd : h.queryStart-1)},100"/>`).join("")}
    <rect data-anchor-split-bar x="40" y="100" width="640" height="16" rx="3" fill="var(--ctg-primary-fill,#bbd0e8)"/>
    ${candidates.map((cut) => `<g data-anchor-cut="${cut}" role="button" tabindex="0" aria-pressed="${selected.has(cut)}" aria-label="${cut} bp">
      <desc data-app-tooltip-source>${cut} bp</desc><line x1="${x(cut)}" x2="${x(cut)}" y1="80" y2="125" stroke="${selected.has(cut)?"red":"#8996a5"}" stroke-width="${selected.has(cut)?3:1}"/>
      <line x1="${x(cut)}" x2="${x(cut)}" y1="80" y2="125" stroke="transparent" stroke-width="12"/></g>`).join("")}
    <text x="40" y="150">${model.orient === "-" ? model.sourceEnd : model.sourceStart}</text>
    <text x="680" y="150" text-anchor="end">${model.orient === "-" ? model.sourceStart : model.sourceEnd}</text></svg>`;
}
export function openAnchorContigSplit(host, model, { locale = "zh", commit, isCurrent = () => true } = {}) {
  const doc = host?.ownerDocument || globalThis.document;
  if (!doc?.body || doc.querySelector(".anchor-contig-split-dialog")) return Promise.resolve(false);
  const labels = copy[locale === "en" ? "en" : "zh"], focus = doc.activeElement;
  const dialog = doc.createElement("dialog"); dialog.className = "app-dialog anchor-contig-split-dialog";
  dialog.style.width = "min(760px, 94vw)";
  dialog.setAttribute("aria-label",labels.title);
  dialog.innerHTML = `<h2>${labels.title}</h2><p>${model.readOnlyAnchors ? labels.fixed : labels.hint}</p>
    <div data-anchor-preview></div><p data-anchor-ranges></p><p data-anchor-error role="alert"></p>
    <div class="app-dialog-actions"><button data-anchor-cancel class="button ghost">${labels.cancel}</button><button data-anchor-confirm class="button primary">${labels.confirm}</button></div>`;
  let cuts = normalizeAnchorCuts(model.cuts, model), busy = false, closed = false, resolve;
  const result = new Promise((r) => { resolve=r; });
  const el = (s) => dialog.querySelector(s);
  const finish = (ok) => { if(closed)return;closed=true;if(dialog.open)dialog.close();dialog.remove();if(focus?.isConnected)focus.focus();resolve(ok); };
  const update = () => {
    el("[data-anchor-preview]").innerHTML=renderAnchorSplitPreview(model,cuts);
    el("[data-anchor-ranges]").textContent=cuts.length ? `${labels.count}: ${anchorSplitRanges(model,cuts).map(([a,b])=>`${a.toLocaleString()}–${b.toLocaleString()} (${(b-a+1).toLocaleString()} bp)`).join(" · ")}` : labels.empty;
    el("[data-anchor-confirm]").disabled=busy || !cuts.length;
  };
  const toggle = (event) => {
    if(busy || model.readOnlyAnchors)return;
    const edge=event.target?.closest?.("[data-anchor-cut]"), bar=event.target?.closest?.("[data-anchor-split-bar]");
    if(!edge && !bar)return;
    let cut=Number(edge?.getAttribute("data-anchor-cut"));
    if(!edge){const svg=el("[data-anchor-split-svg]"), point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
      const matrix=svg.getScreenCTM();if(!matrix)return;const ratio=(point.matrixTransform(matrix.inverse()).x-40)/640;
      cut=model.sourceStart-1+Math.round((model.orient==="-"?1-ratio:ratio)*(model.sourceEnd-model.sourceStart+1));}
    if(!normalizeAnchorCuts([cut],model).length)return;
    cuts=normalizeAnchorCuts(cuts.includes(cut)?cuts.filter((c)=>c!==cut):[...cuts,cut],model);update();
  };
  dialog.addEventListener("click",toggle);
  dialog.addEventListener("keydown",(e)=>{if(["Enter"," "].includes(e.key)&&e.target?.closest?.("[data-anchor-cut]")){e.preventDefault();toggle(e);}});
  el("[data-anchor-cancel]").addEventListener("click",()=>{if(!busy)finish(false);});
  dialog.addEventListener("cancel",(e)=>{e.preventDefault();if(!busy)finish(false);});
  dialog.addEventListener("close",()=>{if(!busy)finish(false);});
  el("[data-anchor-confirm]").addEventListener("click",async()=>{
    if(busy||!cuts.length)return;
    if(!isCurrent()){el("[data-anchor-error]").textContent=labels.stale;return;}
    busy=true;update();el("[data-anchor-cancel]").disabled=true;
    try {if(await commit({cuts:[...cuts]})===false)throw new Error(labels.failed);finish(true);}
    catch(error){busy=false;el("[data-anchor-cancel]").disabled=false;update();el("[data-anchor-error]").textContent=String(error?.message||error);}
  });
  doc.body.append(dialog);update();dialog.showModal();el("[data-anchor-cancel]").focus();return result;
}
