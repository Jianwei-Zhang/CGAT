const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const bp = (value) => Number(value).toLocaleString("en-US");
const X = 64, WIDTH = 632, REF_Y = 44, CTG_Y = 116, BAR_HEIGHT = 16;
const copy = {
  zh: { title: "手动分割 contig", position: "在原始位置", after: "bp 后分割", left: "左段", right: "右段",
    cancel: "取消", split: "分割", reverse: "反向显示", forward: "正向显示", invalid: "请输入 {start}–{end} 的整数。", failed: "分割失败，请重试。", stale: "contig 已变化，请重新打开面板。" },
  en: { title: "Manual contig split", position: "Split after source base", after: "bp", left: "Left", right: "Right",
    cancel: "Cancel", split: "Split", reverse: "Reverse display", forward: "Forward display", invalid: "Enter an integer from {start} to {end}.", failed: "Split failed. Try again.", stale: "Contig changed. Reopen the panel." },
};

export function parseManualCut(value, model) {
  const text = String(value ?? "").trim();
  const cut = /^\d+$/.test(text) ? Number(text) : NaN;
  return Number.isSafeInteger(cut) && cut >= model.sourceStart && cut < model.sourceEnd ? cut : null;
}

export function manualCutGeometry(model, cut) {
  const lowLength = cut - model.sourceStart + 1;
  const highLength = model.sourceEnd - cut;
  const reverse = model.orient === "-";
  const leftLength = reverse ? highLength : lowLength;
  return { leftLength, rightLength: reverse ? lowLength : highLength,
    x: X + WIDTH * leftLength / (lowLength + highLength) };
}

export function manualBoundaryX(model, cut) {
  const fraction = (cut - model.sourceStart + 1) / (model.sourceEnd - model.sourceStart + 1);
  return X + WIDTH * (model.orient === "-" ? 1 - fraction : fraction);
}

export function renderManualSplitPreview(model, labels = copy.zh) {
  const refX = (coordinate) => X + WIDTH * coordinate / Math.max(1, model.refLength);
  const hits = model.hits.filter((h) => Number.isFinite(h.refStart) && Number.isFinite(h.refEnd) && h.refStart >= 1 && h.refEnd >= h.refStart);
  const bands = hits.map((h) => {
    const a = manualBoundaryX(model,h.queryStart-1), b = manualBoundaryX(model,h.queryEnd);
    const r1 = refX(h.refStart-1), r2 = refX(h.refEnd);
    const q1 = h.strand === "-" ? b : a, q2 = h.strand === "-" ? a : b;
    return `<polygon class="manual-split-band" points="${r1},${REF_Y+12} ${r2},${REF_Y+12} ${q2},${CTG_Y} ${q1},${CTG_Y}"/>`;
  }).join("");
  const edges = hits.flatMap((h) => [
    {cut:h.queryStart-1, ref:h.strand === "-" ? h.refEnd : h.refStart-1},
    {cut:h.queryEnd, ref:h.strand === "-" ? h.refStart-1 : h.refEnd},
  ]).filter(({cut}) => cut >= model.sourceStart && cut < model.sourceEnd).map(({cut,ref}) => {
    const x=manualBoundaryX(model,cut), points=`${x},${CTG_Y} ${refX(ref)},${REF_Y+12}`;
    return `<g class="manual-split-edge" data-manual-cut="${cut}" role="button" tabindex="0" aria-label="${escape(`${labels.position} ${bp(cut)} ${labels.after}`)}">
      <title>${bp(cut)} bp</title><polyline class="manual-split-edge-hit" points="${points}"/>
      <polyline class="manual-split-edge-focus" points="${points}"/><circle cx="${x}" cy="${CTG_Y}" r="4"/>
    </g>`;
  }).join("");
  return `<svg class="manual-split-svg" viewBox="0 0 720 166" role="group" aria-label="${escape(labels.title)}">
    <text x="${X}" y="30">${escape(model.chrName)}</text><text x="${X+WIDTH}" y="30" text-anchor="end">${model.refLength ? bp(model.refLength)+" bp" : ""}</text>
    <rect x="${X}" y="${REF_Y}" width="${WIDTH}" height="12" class="manual-split-ref"/>
    ${bands}<text x="${X}" y="105">${escape(model.name)}</text>
    <rect x="${X}" y="${CTG_Y}" width="${WIDTH}" height="${BAR_HEIGHT}" class="manual-split-contig"/>
    <rect data-manual-left-fill x="${X}" y="${CTG_Y}" height="${BAR_HEIGHT}" class="manual-split-left"/>
    <rect data-manual-right-fill y="${CTG_Y}" height="${BAR_HEIGHT}" class="manual-split-right"/>
    ${edges}<line data-manual-cut-line y1="${CTG_Y-6}" y2="${CTG_Y+BAR_HEIGHT+8}" class="manual-split-cut-line"/>
    <text x="${X}" y="158">${bp(model.orient === "-" ? model.sourceEnd : model.sourceStart)}</text>
    <text x="${X+WIDTH}" y="158" text-anchor="end">${bp(model.orient === "-" ? model.sourceStart : model.sourceEnd)}</text>
  </svg>`;
}

// Local preview only. No backend call, database write or recommendation while editing.
export function openManualContigSplit(host, model, { locale = "zh", commit, isCurrent = () => true } = {}) {
  const doc = host?.ownerDocument || globalThis.document;
  if (!doc?.body || !model || doc.querySelector(".manual-contig-split-dialog")) return Promise.resolve(false);
  const labels = copy[locale === "en" ? "en" : "zh"];
  const previousFocus = doc.activeElement;
  const dialog = doc.createElement("dialog");
  dialog.className = "app-dialog manual-contig-split-dialog";
  dialog.setAttribute("aria-label",labels.title);
  dialog.innerHTML = `<h2 class="app-dialog-title">${labels.title}</h2>
    ${renderManualSplitPreview(model,labels)}
    <form data-manual-split-form novalidate>
      <label class="manual-split-coordinate">${labels.position} <input data-manual-split-position type="number" step="1" min="${model.sourceStart}" max="${model.sourceEnd-1}" aria-label="${labels.position}"/> ${labels.after}</label>
      <div class="manual-split-summary"><span data-manual-split-lengths></span><span>${model.orient === "-" ? labels.reverse : labels.forward}</span></div>
      <p data-manual-split-error role="alert"></p>
      <div class="app-dialog-actions"><button type="button" class="button ghost" data-manual-split-cancel>${labels.cancel}</button><button type="submit" class="button primary" data-manual-split-confirm>${labels.split}</button></div>
    </form>`;
  doc.body.append(dialog);
  const el = (selector) => dialog.querySelector(selector);
  const input = el("[data-manual-split-position]"), confirm = el("[data-manual-split-confirm]");
  const error = el("[data-manual-split-error]"), summary = el("[data-manual-split-lengths]");
  let closed = false, busy = false, resolveDone;
  const done = new Promise((resolve) => { resolveDone = resolve; });
  const finish = (result) => {
    if (closed) return;
    closed = true;
    if (dialog.open) dialog.close();
    dialog.remove();
    if (previousFocus?.isConnected) previousFocus.focus();
    resolveDone(result);
  };
  const update = () => {
    const cut = parseManualCut(input.value,model);
    confirm.disabled = cut === null || busy;
    error.textContent = cut === null ? labels.invalid.replace("{start}",bp(model.sourceStart)).replace("{end}",bp(model.sourceEnd-1)) : "";
    const line = el("[data-manual-cut-line]");
    line.setAttribute("visibility",cut === null ? "hidden" : "visible");
    el("[data-manual-left-fill]").setAttribute("visibility",cut === null ? "hidden" : "visible");
    el("[data-manual-right-fill]").setAttribute("visibility",cut === null ? "hidden" : "visible");
    if (cut === null) { summary.textContent=""; return; }
    const {x,leftLength,rightLength} = manualCutGeometry(model,cut);
    line.setAttribute("x1",x);line.setAttribute("x2",x);
    el("[data-manual-left-fill]").setAttribute("width",x-X);
    el("[data-manual-right-fill]").setAttribute("x",x);
    el("[data-manual-right-fill]").setAttribute("width",X+WIDTH-x);
    summary.textContent=`${labels.left} ${bp(leftLength)} bp · ${labels.right} ${bp(rightLength)} bp`;
  };
  const selectEdge = (target) => {
    if (busy) return;
    const edge = target?.closest?.("[data-manual-cut]");
    if (!edge) return;
    input.value=edge.getAttribute("data-manual-cut");update();
  };
  input.addEventListener("input",update);
  dialog.addEventListener("click",(event) => selectEdge(event.target));
  dialog.addEventListener("keydown",(event) => {
    if (["Enter"," "].includes(event.key) && event.target?.closest?.("[data-manual-cut]")) {
      event.preventDefault();selectEdge(event.target);
    }
  });
  el("[data-manual-split-cancel]").addEventListener("click",() => { if (!busy) finish(false); });
  el("[data-manual-split-form]").addEventListener("submit",async (event) => {
    event.preventDefault();
    const cut=parseManualCut(input.value,model);
    if (busy || closed || cut === null) { if (!closed) update(); return; }
    if (!isCurrent()) { confirm.disabled=true;error.textContent=labels.stale;return; }
    busy=true;dialog.querySelectorAll("button,input").forEach((node)=>{node.disabled=true;});
    try {
      const result=await commit({assemblyCtgId:model.assemblyCtgId,cutAfter:cut,
        sourceStart:model.sourceStart,sourceEnd:model.sourceEnd,orient:model.orient});
      if (result === false) throw new Error(labels.failed);
      finish(true);
    } catch (cause) {
      busy=false;
      dialog.querySelectorAll("button,input").forEach((node)=>{node.disabled=false;});
      error.textContent=String(cause?.message || cause);confirm.disabled=false;
    }
  });
  dialog.addEventListener("cancel",(event)=>{event.preventDefault();if(!busy)finish(false);});
  dialog.addEventListener("close",()=>{if(!busy)finish(false);});
  input.value=String(Math.floor((model.sourceStart+model.sourceEnd)/2));update();
  dialog.showModal();input.focus();input.select?.();
  return done;
}
