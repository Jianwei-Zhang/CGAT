import { SUBVIEW_TOOLS_ID, SUBVIEW_TOOLS_TABS } from "./subview-tools-state.js";

export function renderSubviewToolsToggle(labels, { escapeHtml, escapeAttr }) {
  return `<button type="button" class="button ghost tiny subview-tools-toggle"
    data-subview-tools-toggle="1" aria-controls="${SUBVIEW_TOOLS_ID}" aria-expanded="false"
    title="${escapeAttr(labels.title)}"><svg viewBox="0 0 20 20" fill="none" aria-hidden="true"
    focusable="false"><rect x="2.5" y="3.5" width="15" height="13" rx="1.5"/>
    <path d="M12 4v12M14 7h1M14 10h1M14 13h1"/></svg>${escapeHtml(labels.toggle)}</button>`;
}

export function renderSubviewTools(preferences, labels, { escapeHtml, escapeAttr, content = "" }) {
  return `<section id="${SUBVIEW_TOOLS_ID}" class="subview-tools-window" role="dialog"
    aria-modal="false" aria-labelledby="subview-tools-title" data-subview-tools-window="1">
    <header class="subview-tools-header" data-subview-tools-drag="1">
      <strong id="subview-tools-title">${escapeHtml(labels.title)}</strong>
      <button type="button" class="button ghost tiny" data-subview-tools-close="1"
        aria-label="${escapeAttr(labels.close)}" title="${escapeAttr(labels.close)}">×</button>
    </header>
    <div class="subview-tools-tabs" role="tablist" aria-label="${escapeAttr(labels.title)}">
      ${SUBVIEW_TOOLS_TABS.map((tab) => `<button type="button" role="tab"
        id="subview-tools-tab-${tab}" data-subview-tools-tab="${tab}"
        aria-controls="subview-tools-content" aria-selected="${tab === preferences.tab}"
        tabindex="${tab === preferences.tab ? 0 : -1}">${escapeHtml(labels[tab])}</button>`).join("")}
    </div>
    <div id="subview-tools-content" class="subview-tools-content" role="tabpanel" tabindex="0"
      aria-labelledby="subview-tools-tab-${preferences.tab}" data-subview-tools-content="1">
      ${content || `<p class="muted subview-tools-empty">${escapeHtml(labels[`${preferences.tab}Hint`])}</p>`}
    </div>
    <div class="subview-tools-resize-edge is-right" data-subview-tools-resize="right" aria-hidden="true"></div>
    <div class="subview-tools-resize-edge is-bottom" data-subview-tools-resize="bottom" aria-hidden="true"></div>
    <button type="button" class="subview-tools-resize" data-subview-tools-resize="both"
      aria-label="${escapeAttr(labels.resize)}" title="${escapeAttr(labels.resize)}">◢</button>
  </section>`;
}
