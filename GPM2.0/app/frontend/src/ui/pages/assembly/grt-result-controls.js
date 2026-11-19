function escapeMarkup(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const SETTINGS_ICON_SVG = `<svg class="toolbar-settings-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;

export function renderGrtResultControls({
  scope,
  context,
  i18n,
  escapeHtml = escapeMarkup,
  escapeAttr = escapeMarkup,
} = {}) {
  if (!context?.available || !["main", "subview"].includes(scope)) {
    return "";
  }
  const enabled = scope === "main" ? context.mainEnabled : context.subviewEnabled;
  const layers = scope === "main" ? context.mainLayers : context.subviewLayers;
  return `<div class="grt-result-controls" data-grt-result-controls="${escapeAttr(scope)}">
    <label class="grt-result-switch" data-app-tooltip="${escapeAttr(i18n.grtResult.showResultHint || i18n.grtResult.showResult)}">
      <input type="checkbox" aria-label="${escapeAttr(i18n.grtResult.showResultHint || i18n.grtResult.showResult)}"
        data-grt-result-toggle="${escapeAttr(scope)}" ${enabled ? "checked" : ""} />
      <span>${escapeHtml(i18n.grtResult.showResult)}</span>
    </label>
    <details class="grt-result-layer-menu">
      <summary class="grt-result-layer-trigger" aria-label="${escapeAttr(i18n.grtResult.displayItems)}" data-app-tooltip="${escapeAttr(i18n.grtResult.displayItems)}">${SETTINGS_ICON_SVG}</summary>
      <div class="grt-result-layer-options" role="group" aria-label="${escapeAttr(i18n.grtResult.displayItems)}">
        <label>
          <input type="checkbox" data-grt-result-layer="resultPath" data-grt-result-layer-scope="${escapeAttr(scope)}" ${layers?.resultPath !== false ? "checked" : ""} />
          <span>${escapeHtml(i18n.grtResult.resultPath)}</span>
        </label>
        <label>
          <input type="checkbox" data-grt-result-layer="alignmentEvidence" data-grt-result-layer-scope="${escapeAttr(scope)}" ${layers?.alignmentEvidence !== false ? "checked" : ""} />
          <span>${escapeHtml(i18n.grtResult.alignmentEvidence)}</span>
        </label>
      </div>
    </details>
  </div>`;
}
