import { parseSplitCuts, splitCutFraction, splitCutFromFraction, splitBoundaryCuts, defaultSplitAssignments, splitCopy } from "./contig-split-state.js";

const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const bp = (value) => Number(value).toLocaleString("en-US");
const pct = (value) => `${Number(value).toFixed(2)}%`;
const colors = ["#567eab", "#967445", "#508574", "#98709d", "#b67456"];

export function renderSplitEvidence(preview, cuts, labels) {
  const source = preview.source;
  const chromosomes = [...new Set(preview.hits.map((h) => h.chrName))];
  const x = (k) => 180 + 800 * splitCutFraction(source, k);
  const height = 80 + chromosomes.length * 40;
  const hits = preview.hits.map((hit) => {
    const row = chromosomes.indexOf(hit.chrName);
    const a = x(Math.max(source.sourceStart, hit.queryStart) - 1);
    const b = x(Math.min(source.sourceEnd, hit.queryEnd));
    const title = `${hit.chrName}: ${bp(hit.refStart)}–${bp(hit.refEnd)} | source ${bp(hit.queryStart)}–${bp(hit.queryEnd)} | MAPQ ${hit.mapq}`;
    return `<g><rect x="${Math.min(a, b)}" y="${58 + row * 40}" width="${Math.max(1, Math.abs(b - a))}" height="14" fill="${colors[row % colors.length]}"><title>${escape(title)}</title></rect>${splitBoundaryCuts(hit, source).map((cut) => `<circle cx="${x(cut)}" cy="${65 + row * 40}" r="5" class="ctg-split-boundary" data-split-cut="${cut}" role="button" tabindex="0" aria-label="${escape(`${hit.chrName}: ${cut === hit.queryEnd ? labels.boundaryEnd : labels.boundaryStart} ${bp(cut)}`)}"><title>${escape(title)} | ${bp(cut)}</title></circle>`).join("")}</g>`;
  }).join("");
  return `<svg data-split-canvas="1" viewBox="0 0 1000 ${height}" role="img" aria-label="${escape(labels.title)}">
    <text x="180" y="16">${bp(source.orient === "-" ? source.sourceEnd : source.sourceStart)}</text>
    <text x="980" y="16" text-anchor="end">${bp(source.orient === "-" ? source.sourceStart : source.sourceEnd)}</text>
    <rect x="180" y="25" width="800" height="15" fill="#d2dfef" stroke="#567eab"/>
    ${chromosomes.map((chr, i) => `<text x="4" y="${70 + i * 40}">${escape(chr)}</text>`).join("")}${hits}
    ${cuts.map((cut) => `<line x1="${x(cut)}" x2="${x(cut)}" y1="20" y2="${height}" stroke="#c33" stroke-width="2" stroke-dasharray="5 3"/><text x="${x(cut)}" y="${height - 3}" text-anchor="middle" fill="#a22">${bp(cut)}</text>`).join("")}
  </svg>`;
}

function renderParts(preview, labels, choices) {
  return preview.parts.map((part, index) => {
    const candidates = part.candidates;
    const names = [...new Set([preview.source.assignedChrName, ...candidates.map((c) => c.chrName)].filter(Boolean))];
    return `<section class="ctg-split-part"><h3>${labels.fragment} ${index + 1}: ${bp(part.sourceStart)}–${bp(part.sourceEnd)} (${bp(part.length)} bp)</h3>
      <label>${labels.group} <select data-split-assignment="${index}"><option value="" ${choices[index] === null ? "selected" : ""}>${labels.unplaced}</option>${names.map((name) => `<option value="${escape(name)}" ${choices[index] === name ? "selected" : ""}>${escape(name)}</option>`).join("")}</select></label>
      ${candidates.length ? `<div class="ctg-split-table-scroll"><table><thead><tr><th>chr</th><th>${labels.coverage}</th><th>${labels.quality}</th><th>${labels.identity}</th><th>${labels.mapq}</th><th>${labels.direction}</th><th>${labels.target}</th></tr></thead><tbody>${candidates.map((c) => `<tr><td>${escape(c.chrName)}${c.approximate ? `<small title="${escape(labels.approximate)}"> ≈</small>` : ""}</td><td>${pct(c.coveragePercent)}</td><td>${pct(c.highQualityCoveragePercent)}</td><td>${pct(c.identityPercent)}</td><td>${c.minMapq}</td><td>${escape(c.orient)}</td><td>${bp(c.refStart)}–${bp(c.refEnd)}</td></tr>`).join("")}</tbody></table></div>` : `<p>${labels.noHits}</p>`}</section>`;
  }).join("");
}

/** deps.preview and deps.commit use the real workspace; failures never become mock success. */
export async function openContigSplitDialog(host, store, options, deps) {
  const doc = host?.ownerDocument || globalThis.document;
  if (!doc?.body || doc.querySelector(".ctg-split-dialog")) return false;
  const initialState = store.getState();
  const labels = splitCopy[initialState.locale === "en" ? "en" : "zh"];
  const identity = { workspaceRoot: initialState.session.workspacePath, projectId: initialState.session.projectId };
  const current = () => store.getState().session.workspacePath === identity.workspaceRoot
    && store.getState().session.projectId === identity.projectId
    && store.getState().assembly.selectedChrName === initialState.assembly.selectedChrName;
  const previousFocus = doc.activeElement;
  const dialog = doc.createElement("dialog");
  dialog.className = "app-dialog ctg-split-dialog";
  dialog.setAttribute("aria-label", labels.title);
  dialog.innerHTML = `<h2>${labels.title}</h2><p data-split-source></p>
    <div class="ctg-split-modes">${["manual", "boundary", "recommended"].map((mode) => `<button type="button" class="button ghost" data-split-mode="${mode}">${labels[mode]}</button>`).join("")}</div>
    <p>${labels.hint}</p><div data-split-evidence></div><div data-split-options></div>
    <label class="ctg-split-coordinate">${labels.cuts}<input type="text" inputmode="numeric" data-split-cuts aria-label="${escape(labels.cuts)}" /></label>
    <input type="range" data-split-slider aria-label="${escape(labels.cuts)}" /><button type="button" class="button ghost" data-split-refresh>${labels.preview}</button>
    <p data-split-error role="alert"></p><div data-split-parts></div><p data-split-impact></p><p>${labels.undoNotice}</p>
    <div class="app-dialog-actions"><button type="button" class="button ghost" data-split-cancel>${labels.cancel}</button><button type="button" class="button primary" data-split-confirm disabled>${labels.confirm}</button></div>`;
  doc.body.append(dialog);
  const el = (selector) => dialog.querySelector(selector);
  const input = el("[data-split-cuts]");
  input.disabled = true;
  const slider = el("[data-split-slider]");
  const confirm = el("[data-split-confirm]");
  const error = el("[data-split-error]");
  let preview = null; let sequence = 0; let closed = false; let committing = false;
  let mode = options.mode || "manual";
  let reason = options.cutAfter ? "alignment-boundary" : "manual";
  let choices = []; let readyCuts = ""; let dragging = false;
  let resolveDone;
  const done = new Promise((resolve) => { resolveDone = resolve; });
  const finish = (result) => {
    if (closed) return;
    closed = true; sequence += 1;
    if (dialog.open) dialog.close();
    dialog.remove();
    if (previousFocus?.isConnected) previousFocus.focus();
    resolveDone(result);
  };
  const cutsNow = () => parseSplitCuts(input.value, preview.source);
  const redraw = () => {
    if (!preview) return;
    let cuts = []; try { cuts = cutsNow(); } catch { /* invalid input has no cut line */ }
    el("[data-split-evidence]").innerHTML = renderSplitEvidence(preview, cuts, labels);
    slider.min = preview.source.sourceStart;
    slider.max = preview.source.sourceEnd - 1;
    slider.value = cuts[0] ?? Math.floor((preview.source.sourceStart + preview.source.sourceEnd) / 2);
    slider.style.direction = preview.source.orient === "-" ? "rtl" : "ltr";
  };
  const dirty = () => { confirm.disabled = true; redraw(); };
  const rememberChoices = () => new Map(preview?.parts.map((p, i) => [`${p.sourceStart}:${p.sourceEnd}`, choices[i]]) || []);
  const showOptions = () => {
    if (!preview) return;
    dialog.querySelectorAll("[data-split-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.splitMode === mode)));
    if (mode === "recommended") {
      el("[data-split-options]").innerHTML = preview.recommendations.length ? preview.recommendations.map((r, i) => `<p>${escape(r.leftChr)} → ${escape(r.rightChr)} · ${labels[r.kind === "overlap" ? "overlap" : r.kind === "unaligned" ? "unaligned" : "boundaryRegion"]} ${bp(r.regionStart)}–${bp(r.regionEnd)} <button type="button" class="button ghost" data-split-recommendation="${i}">${labels.choose}: ${r.cutAfter.map(bp).join(", ")}</button></p>`).join("") : `<p>${labels.noRecommendation}</p>`;
    } else if (mode === "boundary") {
      el("[data-split-options]").innerHTML = `<div class="ctg-split-boundary-list">${preview.hits.map((hit) => `<span>${escape(hit.chrName)} ${bp(hit.queryStart)}–${bp(hit.queryEnd)} ${splitBoundaryCuts(hit, preview.source).map((cut) => `<button type="button" class="button ghost tiny" data-split-cut="${cut}">${cut === hit.queryEnd ? labels.after : labels.before}: ${bp(cut)}</button>`).join("")}</span>`).join("")}</div>`;
    } else el("[data-split-options]").innerHTML = "";
  };
  async function refresh(initial = false) {
    if (committing || closed) return;
    const ticket = ++sequence;
    confirm.disabled = true;
    let cuts = [];
    try {
      if (!initial) cuts = cutsNow();
      error.textContent = labels.loading;
      const previous = rememberChoices();
      const result = await deps.preview({ ...identity, assemblyCtgId: options.assemblyCtgId, cutAfter: cuts });
      if (closed || ticket !== sequence) return;
      if (!current()) throw new Error(labels.stale);
      preview = result;
      input.disabled = false;
      if (initial) {
        const initialCut = options.cutAfter;
        input.value = initialCut != null ? String(initialCut)
          : mode === "manual" ? String(Math.floor((result.source.sourceStart + result.source.sourceEnd) / 2)) : "";
      }
      choices = defaultSplitAssignments(result, previous);
      readyCuts = JSON.stringify(result.cutAfter);
      const source = result.source;
      el("[data-split-source]").textContent = `${source.name} · ${labels.source}: ${bp(source.sourceStart)}–${bp(source.sourceEnd)} · ${labels.direction}: ${source.orient}${source.orient === "-" ? ` · ${labels.reverse}` : ""}`;
      el("[data-split-parts]").innerHTML = renderParts(result, labels, choices);
      el("[data-split-impact]").textContent = labels.pathNotice.replace("{count}", result.finalPathReferenceCount);
      error.textContent = "";
      redraw(); showOptions();
      confirm.disabled = !result.cutAfter.length;
      if (initial && input.value) await refresh();
    } catch (cause) {
      if (!closed && ticket === sequence) error.textContent = cause.message === "invalid-cuts" ? labels.invalid : String(cause.message || cause);
    }
  }
  const useCuts = async (cuts, nextMode) => {
    if (committing) return;
    mode = nextMode; reason = nextMode === "boundary" ? "alignment-boundary" : nextMode; input.value = cuts.join(", "); dirty(); showOptions(); await refresh();
  };
  dialog.addEventListener("click", async (event) => {
    if (committing) return;
    const target = event.target.closest?.("button,[data-split-cut]");
    if (!target) return;
    if (target.hasAttribute("data-split-cancel")) finish(false);
    else if (target.hasAttribute("data-split-refresh")) await refresh();
    else if (target.hasAttribute("data-split-mode")) { mode = target.dataset.splitMode; showOptions(); }
    else if (target.hasAttribute("data-split-cut")) await useCuts([Number(target.dataset.splitCut)], "boundary");
    else if (target.hasAttribute("data-split-recommendation")) await useCuts(preview.recommendations[Number(target.dataset.splitRecommendation)].cutAfter, "recommended");
    else if (target.hasAttribute("data-split-confirm")) {
      if (!preview || confirm.disabled) return;
      try {
        const cuts = cutsNow();
        if (!current() || JSON.stringify(cuts) !== readyCuts) throw new Error(labels.stale);
        committing = true;
        dialog.querySelectorAll("button,input,select").forEach((node) => { node.disabled = true; });
        await deps.commit({ ...identity, chrName: initialState.assembly.selectedChrName, action: "split-source-ctg", args: {
          assemblyCtgId: options.assemblyCtgId, cutAfter: cuts, assignments: choices,
          previewToken: preview.previewToken, reason,
        } });
        finish(true);
      } catch (cause) {
        committing = false;
        dialog.querySelectorAll("button,input,select").forEach((node) => { node.disabled = false; });
        confirm.disabled = true;
        error.textContent = String(cause.message || cause);
      }
    }
  });
  dialog.addEventListener("input", (event) => {
    if (event.target === input) { sequence += 1; reason = "manual"; mode = "manual"; dirty(); showOptions(); }
    if (event.target === slider) { sequence += 1; reason = "manual"; mode = "manual"; input.value = slider.value; dirty(); showOptions(); }
  });
  dialog.addEventListener("change", (event) => {
    if (event.target === slider) void refresh();
    const index = event.target.getAttribute?.("data-split-assignment");
    if (index !== null && index !== undefined) choices[Number(index)] = event.target.value || null;
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target === input) { event.preventDefault(); void refresh(); }
    if (["Enter", " "].includes(event.key) && event.target.hasAttribute?.("data-split-cut")) { event.preventDefault(); event.target.dispatchEvent(new doc.defaultView.MouseEvent("click", { bubbles: true })); }
  });
  const pointerCut = (event) => {
    const svg = el("[data-split-canvas]");
    if (!preview || !svg) return;
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0) return;
    const fraction = ((event.clientX - rect.left) / rect.width * 1000 - 180) / 800;
    input.value = String(splitCutFromFraction(preview.source, fraction));
    mode = "manual"; reason = "manual"; sequence += 1; dirty(); showOptions();
  };
  dialog.addEventListener("pointerdown", (event) => {
    if (committing || !event.target.closest?.("[data-split-canvas]") || event.target.closest?.("[data-split-cut]")) return;
    dragging = true; dialog.setPointerCapture?.(event.pointerId); pointerCut(event);
  });
  dialog.addEventListener("pointermove", (event) => { if (dragging) pointerCut(event); });
  dialog.addEventListener("pointerup", () => { if (dragging) { dragging = false; void refresh(); } });
  dialog.addEventListener("pointercancel", () => { dragging = false; });
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); if (!committing) finish(false); });
  dialog.addEventListener("close", () => { if (!committing) finish(false); });
  dialog.showModal();
  input.focus();
  void refresh(true);
  return done;
}
