function escapeMarkup(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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
    <label class="grt-result-switch">
      <input type="checkbox" data-grt-result-toggle="${escapeAttr(scope)}" ${enabled ? "checked" : ""} />
      <span>${escapeHtml(i18n.grtResult.showResult)}</span>
    </label>
    <details class="grt-result-layer-menu">
      <summary class="grt-result-layer-trigger" aria-label="${escapeAttr(i18n.grtResult.displayItems)}" title="${escapeAttr(i18n.grtResult.displayItems)}"><span aria-hidden="true">⚙</span></summary>
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
