const escapeHtml = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
const escapeAttr = escapeHtml;

export function subviewWindowTitle(item, labels, assembly = {}) {
  const summary = item.snapshot?.subview?.summary;
  if (summary?.mode === "composition") return labels.compositionBadgeName;
  const name = entry => {
    const pool = entry?.role === "primary" ? assembly.chrCtgs
      : entry?.role === "support" ? assembly.supportChrCtgs : [];
    return pool?.find(ctg => Number(ctg.assemblyCtgId) === Number(entry?.contigId))?.name
      || entry?.label || entry?.name || entry?.contigName
      || (entry?.contigId ? `Ctg${entry.contigId}` : entry?.role || "");
  };
  return [name(summary?.top || summary?.topTrack), name(summary?.bottom || summary?.bottomTrack)]
    .filter(Boolean).join(" ↔ ") || labels.panelTitle;
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
  return `<div class="subview-taskbar" role="toolbar" aria-label="${escapeAttr(w.taskbar)}">
    ${workspace.windows.map(item => `<div class="subview-task${workspace.activeId === item.id ? " is-active" : ""}${item.minimized ? " is-minimized" : ""}" data-subview-task="${item.id}">
      <button type="button" data-local-view-action="activate" data-local-view-id="${item.id}"
        aria-expanded="${!item.minimized}" aria-controls="${item.id}" class="subview-task-name"
        data-app-tooltip="${escapeAttr(subviewWindowTitle(item, labels, assembly))}" data-app-tooltip-overflow>${escapeHtml(subviewWindowTitle(item, labels, assembly))}</button>
      <button type="button" data-local-view-action="minimize" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.minimize)}" data-app-tooltip="${escapeAttr(w.minimize)}">−</button>
      <button type="button" data-local-view-action="close" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.close)}" data-app-tooltip="${escapeAttr(w.close)}">×</button>
    </div>`).join("")}
  </div>`;
}

export function renderSubviewWorkspace(state, labels, renderPanel) {
  const assembly = state.assembly;
  const workspace = assembly.subviewWorkspace;
  if (state.assembly.subviewWindowRendering) return renderPanel(state);
  // First paint can precede store binding. The binder installs the runtime
  // workspace before attaching interactive controls.
  if (!workspace) return `<section data-subview-workspace="1">${renderPanel(state)}</section>`;
  const w = labels.window;
  return `<section data-subview-workspace="1">
    ${workspace.windows.length ? renderSubviewTaskbar(workspace, labels, assembly) : renderPanel(state)}
    ${workspace.windows.map(item => `<section id="${item.id}" data-local-view-window="${item.id}"
      class="subview-window${item.floating ? " is-floating" : ""}" ${item.minimized ? "hidden" : ""}
      role="region" aria-label="${escapeAttr(subviewWindowTitle(item, labels, assembly))}"
      style="--local-x:${item.x}px;--local-y:${item.y}px;--local-z:${item.z}">
      <header class="subview-window-header" data-local-view-drag="1">
        <button type="button" data-local-view-action="dock" data-local-view-id="${item.id}"
          aria-label="${escapeAttr(item.floating ? w.dock : w.float)}">${escapeHtml(item.floating ? w.dock : w.float)}</button>
        <strong>${escapeHtml(subviewWindowTitle(item, labels, assembly))}</strong>
        <button type="button" data-local-view-action="minimize" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.minimize)}" data-app-tooltip="${escapeAttr(w.minimize)}">−</button>
        <button type="button" data-local-view-action="close" data-local-view-id="${item.id}" aria-label="${escapeAttr(w.close)}" data-app-tooltip="${escapeAttr(w.close)}">×</button>
      </header>
      <div data-local-view-context-menu class="context-menu is-hidden"></div>
      <div class="subview-window-content">${renderPanel({ ...state, assembly: { ...state.assembly,
        ...item.snapshot, subviewWindowRendering: item.id } })}</div>
    </section>`).join("")}
  </section>`;
}
