import { LOCAL_VIEW_RESIZE_EDGES } from "./subview-window-geometry.js";
import { PictureInPicture2, PanelTopClose, Pin, PinOff } from "lucide";
const escapeHtml = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const escapeAttr = escapeHtml;

export function subviewWindowAssembly(state) {
  const project = state.initializer?.existingProjects?.find(item => Number(item.projectId) === Number(state.session?.projectId));
  return { ...state.assembly, subviewWindowDatasets: state.initializer?.datasets || [],
    subviewWindowPrimaryDatasetId: project?.primaryDatasetId };
}

// One identity/description contract for task buttons, window chrome and destinations.
export function subviewWindowDescription(item, labels, assembly = {}) {
  const w = labels.window;
  const summary = item.snapshot?.subview?.summary;
  const number = item.number ?? String(item.id).split("-").at(-1);
  const role = entry => {
    const value = entry?.role || entry?.source?.role;
    if (value === "phased") return `${w.phased} ${entry.haplotypeKey || entry.phasedHaplotypeKey || entry.source?.phasedHaplotypeKey || entry.source?.hap || entry.phasedTrackId || ""}`.trim();
    return w[value] || w.unknown;
  };
  const dataset = entry => {
    const value = entry?.role || entry?.source?.role;
    const id = entry?.datasetId || entry?.source?.datasetId
      || (value === "primary" || value === "phased" ? assembly.subviewWindowPrimaryDatasetId
        : value === "support" ? assembly.supportDatasetId : null);
    return entry?.source?.datasetName || assembly.subviewWindowDatasets?.find(ds => Number(ds.datasetId) === Number(id))?.name
      || assembly.subviewWindowDatasets?.find(ds => Number(ds.datasetId) === Number(id))?.label || "";
  };
  const contig = entry => {
    const value = entry?.role || entry?.source?.role;
    const pool = value === "support" ? assembly.supportChrCtgs : value === "ref" ? assembly.refTrackMembers : assembly.chrCtgs;
    const id = entry?.contigId || entry?.assemblyCtgId;
    return entry?.label || entry?.name || entry?.contigName
      || (id && pool?.find(ctg => Number(ctg.assemblyCtgId) === Number(id))?.name)
      || (id ? `Ctg${id}` : "");
  };
  const detail = entry => `[${role(entry)}] ${[dataset(entry), contig(entry)].filter(Boolean).join(" · ") || assembly.selectedChrName || ""}`;
  let short, lines;
  if (summary?.mode === "composition") {
    const members = summary.members || [];
    const lane = name => members.filter(member => member.lane === name);
    const describe = name => {
      const entries = lane(name);
      return `${entries.length}: ${entries.slice(0, 3).map(detail).join("; ")}${entries.length > 3 ? " …" : ""}`;
    };
    short = `${labels.compositionBadgeName} · ${w.top}${lane("top").length} / ${w.bottom}${lane("bottom").length}`;
    lines = [`${w.top}: ${describe("top")}`, `${w.bottom}: ${describe("bottom")}`];
  } else {
    const top = summary?.top || summary?.topTrack;
    const bottom = summary?.bottom || summary?.bottomTrack;
    const name = summary?.mode === "track-pair" ? role : entry => contig(entry) || role(entry);
    short = [name(top), name(bottom)].join(" ↔ ");
    lines = [`${w.top}: ${detail(top)}`, `${w.bottom}: ${detail(bottom)}`];
  }
  return { title: item.name || `${w.view} ${number}`, tooltip: [
    ...(item.name ? [item.name] : []),
    short,
    `${labels.panelTitle} #${number} · ${summary?.mode === "track-pair" ? w.trackPair : summary?.mode === "composition" ? labels.compositionBadgeName : w.contigPair}`,
    `${w.chromosome}: ${assembly.selectedChrName || "—"}`, ...lines,
    ...(assembly.subviewNativeWindows && item.floating ? [w.nativeDropHint] : []),
    ...(item.note ? [`${w.note}: ${item.note}`] : []),
  ].join("\n") };
}

export function subviewWindowTitle(item, labels, assembly = {}) {
  return subviewWindowDescription(item, labels, assembly).title;
}

export function renderSubviewDockIcon(floating) {
  const nodes = floating ? PanelTopClose : PictureInPicture2;
  return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${nodes.map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([key, value]) => `${key}="${value}"`).join(" ")}></${tag}>`).join("")}</svg>`;
}

export function renderSubviewPinIcon(pinned) {
  const nodes = pinned ? Pin : PinOff;
  return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${nodes.map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([key, value]) => `${key}="${value}"`).join(" ")}></${tag}>`).join("")}</svg>`;
}

export function syncSubviewPinButton(node, item, labels) {
  const button = node?.querySelector?.('[data-local-view-action="pin"]');
  if (!button) return;
  const pinned = item.pinned !== false, label = pinned ? labels.window.unpin : labels.window.pin;
  button.hidden = !item.floating;
  button.innerHTML = renderSubviewPinIcon(pinned);
  button.classList.toggle("is-pinned", pinned);
  button.setAttribute("aria-pressed", String(pinned));
  button.setAttribute("aria-label", label);
  button.setAttribute("data-app-tooltip", label);
}

export function renderSubviewWindowChrome(assembly, labels, end = false) {
  const item = assembly.subviewWorkspace?.windows.find(item => item.id === assembly.subviewWindowRendering);
  if (!item) return "";
  const w = labels.window;
  if (end) return `<div class="subview-window-actions">
    ${item.floating && assembly.subviewNativeWindows ? `<button type="button" class="subview-window-pin${item.pinned !== false ? " is-pinned" : ""}" data-local-view-action="pin" data-local-view-id="${item.id}" aria-pressed="${item.pinned !== false}" aria-label="${escapeAttr(item.pinned !== false ? w.unpin : w.pin)}" data-app-tooltip="${escapeAttr(item.pinned !== false ? w.unpin : w.pin)}">${renderSubviewPinIcon(item.pinned !== false)}</button>` : ""}
    <button type="button" data-local-view-action="minimize" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.minimize)}" data-app-tooltip="${escapeAttr(w.minimize)}">−</button>
    <button type="button" data-local-view-action="close" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.close)}" data-app-tooltip="${escapeAttr(w.close)}">×</button></div>`;
  const { title, tooltip } = subviewWindowDescription(item, labels, assembly);
  const action = item.floating ? w.dock : w.float;
  return `<div class="subview-window-heading">
    <button type="button" data-local-view-action="dock" data-local-view-id="${item.id}" aria-label="${escapeAttr(action)}" data-app-tooltip="${escapeAttr(action)}">${renderSubviewDockIcon(item.floating)}</button>
    <strong data-local-view-title tabindex="0" data-app-tooltip="${escapeAttr(tooltip)}">${escapeHtml(title)}</strong></div>`;
}

export function renderSubviewEmptyGuide(labels) {
  const text = escapeHtml(labels.guide);
  const tool = escapeHtml(labels.tools.toggle);
  const entry = `<button type="button" class="subview-guide-tools" data-subview-tools-toggle="1"
    aria-expanded="false">${tool}</button>`;
  return `<p class="muted subview-empty-guide" data-app-tooltip="${escapeAttr(labels.guide)}"
    data-app-tooltip-overflow>${text.replace(tool, entry)}</p>`;
}

export function renderSubviewTaskbar(workspace, labels, assembly = {}) {
  if (!workspace?.windows.length) return "";
  const w = labels.window;
  return `<div class="subview-taskbar" data-local-view-generation="${workspace.generation}" role="toolbar" aria-label="${escapeAttr(w.taskbar)}">
    ${workspace.windows.map(item => `<div class="subview-task${workspace.activeId === item.id ? " is-active" : ""}${item.minimized ? " is-minimized" : ""}" data-subview-task="${item.id}" draggable="false">
      <button type="button" data-local-view-action="activate" data-local-view-id="${item.id}"
        aria-expanded="${!item.minimized && item.opened !== false}" ${assembly.subviewNativeWindows && item.floating ? "" : `aria-controls="${item.id}"`} class="subview-task-name"
        data-app-tooltip="${escapeAttr(subviewWindowDescription(item, labels, assembly).tooltip)}">${escapeHtml(subviewWindowTitle(item, labels, assembly))}</button>
      <button type="button" data-local-view-action="close" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.close)}" data-app-tooltip="${escapeAttr(w.close)}">×</button>
    </div>`).join("")}
  </div>`;
}

export function renderSubviewWorkspace(state, labels, renderPanel) {
  const assembly = subviewWindowAssembly(state);
  const workspace = assembly.subviewWorkspace;
  if (state.assembly.subviewWindowRendering) return renderPanel({ ...state, assembly });
  // First paint can precede store binding. The binder installs the runtime
  // workspace before attaching interactive controls.
  if (!workspace) return `<section data-subview-workspace="1">${renderPanel(state)}</section>`;
  return `<section data-subview-workspace="1">
    ${renderSubviewTaskStatus(assembly, labels)}
    ${workspace.windows.length ? renderSubviewTaskbar(workspace, labels, assembly) : renderPanel(state)}
    ${workspace.windows.filter(item => !(assembly.subviewNativeWindows && item.floating)).map(item => `<section id="${item.id}" data-local-view-window="${item.id}" data-local-view-generation="${workspace.generation}"
      class="subview-window${item.floating ? " is-floating" : ""}" ${item.minimized || item.opened === false ? "hidden" : ""}
      role="region" aria-label="${escapeAttr(subviewWindowTitle(item, labels, assembly))}"
      style="--local-x:${item.x}px;--local-y:${item.y}px;--local-z:${item.z}${item.width > 0 ? `;--local-width:${item.width}px` : ""}${item.height > 0 ? `;--local-height:${item.height}px` : ""}">
      <div data-local-view-context-menu class="context-menu is-hidden"></div>
      <div class="subview-window-content">${renderPanel({ ...state, assembly: { ...assembly,
        ...item.snapshot, subviewWindowRendering: item.id } })}</div>
      ${LOCAL_VIEW_RESIZE_EDGES.map(edge => `<div class="subview-window-resize" data-local-view-resize="${edge}" aria-hidden="true"></div>`).join("")}
    </section>`).join("")}
  </section>`;
}

export function subviewTaskMenuItems(item, labels, assembly = {}) {
  const w = labels.window;
  const opened = item.opened !== false;
  return [
    { action: "open-docked", label: w.openDocked, group: "open", checked: opened && !item.floating },
    { action: "open-floating", label: w.openFloating, group: "open", checked: opened && item.floating },
    ...(item.floating && assembly.subviewNativeWindows
      ? [{ action: "pin", label: w.keepAboveMain, group: "window", role: "menuitemcheckbox", checked: item.pinned !== false, disabled: !opened }] : []),
    { action: "minimize", label: w.minimize, group: "window", disabled: !opened || item.minimized },
    { action: "rename", label: w.rename, group: "metadata" },
    { action: "note", label: w.editNote, group: "metadata" },
    { action: "close", label: w.taskClose, group: "close", danger: true },
  ];
}

export function renderSubviewTaskStatus(assembly, labels) {
  const error = assembly.subviewNativeError || assembly.localViewTaskSaveError;
  return `<div data-local-view-task-status role="status" ${error ? "" : "hidden"}>
    ${error ? `<span>${escapeHtml(assembly.subviewNativeError ? labels.window.openFailed : labels.window.saveFailed)}: ${escapeHtml(error)}</span>
      ${assembly.subviewNativeError ? "" : `<button type="button" class="button ghost" data-local-view-action="retry-save">${escapeHtml(labels.window.retrySave)}</button>`}` : ""}
  </div>`;
}
