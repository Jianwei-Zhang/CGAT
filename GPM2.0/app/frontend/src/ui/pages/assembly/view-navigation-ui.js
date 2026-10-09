import { MIN_TICK_UNIT_KB_OPTIONS, resolveTrackPrefs } from "./track-prefs.js";

export const VIEW_NAV_TEXT = {
  zh: { group: "查看范围", mode: "手形拖动模式（关闭时使用鼠标选择和编辑）", mouse: "鼠标模式：选择和编辑", hand: "手形模式：拖动视野", left: "左移半屏", right: "右移半屏", fit: "全览", fitHint: "显示当前视图的全部范围", span: "窗口", axis: "总览范围；滚轮缩放，拖动范围框平移", window: "当前查看窗口", edgeLeft: "调整窗口左边界", edgeRight: "调整窗口右边界", tick: "刻度间隔", tickOptions: "选择刻度间隔", tickInvalid: "请输入 Auto 或有效的正数；单位为 kb。" },
  en: { group: "Viewing range", mode: "Hand panning mode (off: mouse selection and editing)", mouse: "Mouse mode: select and edit", hand: "Hand mode: pan the view", left: "Move left half a window", right: "Move right half a window", fit: "Full range", fitHint: "Display the complete viewing range", span: "Window", axis: "Overview range; wheel to zoom, drag the window to pan", window: "Current viewing window", edgeLeft: "Resize left window edge", edgeRight: "Resize right window edge", tick: "Tick interval", tickOptions: "Choose tick interval", tickInvalid: "Enter Auto or a positive tick interval in kb." },
};
export function viewNavText(i18nOrLocale) {
  const locale = typeof i18nOrLocale === "string" ? i18nOrLocale
    : /[\u4e00-\u9fff]/.test(String(i18nOrLocale?.trackControls?.minTickUnitKb || "")) ? "zh" : "en";
  return VIEW_NAV_TEXT[locale === "en" ? "en" : "zh"];
}
const escape = (value) => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
export function renderViewTickControl(trackPrefs, i18n, viewKey) {
  const prefs = resolveTrackPrefs(trackPrefs), t = viewNavText(i18n);
  const value = prefs.tickMode === "auto" ? "Auto" : String(prefs.tickIntervalBp / 1000);
  const listId = `view-tick-options-${viewKey}`;
  const options = ["Auto", ...MIN_TICK_UNIT_KB_OPTIONS.map(String)];
  // One inline, editable combobox: preset selection and custom values share the same field.
  return `<label class="view-tick-control" data-view-tick-control="${viewKey}">
    <span>${t.tick} (kb)</span>
    <span class="view-tick-combo">
      <input type="text" data-view-tick-interval role="combobox" aria-autocomplete="list" aria-controls="${listId}" aria-expanded="false" aria-label="${t.tick} (kb)" value="${escape(value)}" autocomplete="off" spellcheck="false">
      <button type="button" class="view-tick-toggle" data-view-tick-toggle aria-label="${t.tickOptions}" aria-controls="${listId}" aria-expanded="false"><span aria-hidden="true">▾</span></button>
      <span class="view-tick-options" id="${listId}" data-view-tick-options role="listbox" aria-label="${t.tickOptions}" hidden>${options.map((option, index) => `<button type="button" role="option" id="${listId}-${index}" data-view-tick-option="${option}" aria-selected="${option === value}">${option}</button>`).join("")}</span>
    </span>
  </label>`;
}
const paths = {
  mouse: '<path d="M5 3v16l4-4 3 6 3-2-3-6h6Z"/>',
  hand: '<path d="M8 12V5a1.5 1.5 0 0 1 3 0v6-7a1.5 1.5 0 0 1 3 0v7-5a1.5 1.5 0 0 1 3 0v6-3a1.5 1.5 0 0 1 3 0v7c0 4-3 6-7 6-2 0-3-1-4-3l-4-5a1.5 1.5 0 0 1 2-2l2 2Z"/>',
  left: '<path d="m14 6-6 6 6 6M8 12h12"/>', right: '<path d="m10 6 6 6-6 6M4 12h12"/>',
};
export function renderViewNavigation(role, locale) {
  const t = viewNavText(locale);
  const icon = (action) => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[action]}</svg>`;
  const button = (action, title) => `<button type="button" class="view-nav-button" data-view-nav-action="${action}" aria-label="${escape(title)}" title="${escape(title)}">${icon(action)}</button>`;
  return `<div class="assembly-view-navigation" data-view-navigation="${role}" role="group" aria-label="${t.group}">
    <button type="button" class="view-nav-mode-switch" data-view-nav-action="toggle-mode" role="switch" aria-checked="false" aria-label="${t.mode}" title="${t.mouse}">
      <span class="view-nav-mode-thumb" aria-hidden="true"></span>
      <span class="view-nav-mode-icon is-mouse" aria-hidden="true">${icon("mouse")}</span>
      <span class="view-nav-mode-icon is-hand" aria-hidden="true">${icon("hand")}</span>
    </button>
    <div class="view-nav-moves">${button("left", t.left)}${button("right", t.right)}</div>
    <div class="view-nav-range">
      <div class="view-nav-axis" data-view-nav-axis title="${t.axis}" aria-label="${t.axis}">
        <div class="view-nav-window" data-view-nav-window tabindex="0" role="slider" aria-label="${t.window}" aria-orientation="horizontal">
          <button type="button" class="view-nav-edge is-left" data-view-nav-edge="left" aria-label="${t.edgeLeft}"></button>
          <button type="button" class="view-nav-edge is-right" data-view-nav-edge="right" aria-label="${t.edgeRight}"></button>
        </div>
      </div>
      <button type="button" class="view-nav-fit" data-view-nav-action="fit" title="${t.fitHint}">${t.fit}</button>
    </div>
    <span class="view-nav-span">${t.span}${locale === "en" ? ":" : "："}<span data-view-nav-span aria-label="${t.window}">—</span></span>
  </div>`;
}
