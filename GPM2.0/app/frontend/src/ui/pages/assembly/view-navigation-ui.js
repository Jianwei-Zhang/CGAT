import { resolveTrackPrefs } from "./track-prefs.js";

export const VIEW_NAV_TEXT = {
  zh: { group: "查看范围", mouse: "鼠标模式：选择和编辑", hand: "手形模式：拖动视野", left: "左移半屏", right: "右移半屏", minus: "缩小", plus: "放大", fit: "适应全部", span: "跨度", axis: "总览范围；滚轮缩放，拖动范围框平移", window: "当前查看窗口", edgeLeft: "调整窗口左边界", edgeRight: "调整窗口右边界", settings: "显示设置", tick: "刻度间隔", auto: "自动", manual: "手动", invalid: "请输入有效的正数；单位为 kb 或 Mb。", bounded: "已限制到可显示范围。", tickInvalid: "刻度间隔必须为正数，单位为 kb。" },
  en: { group: "Viewing range", mouse: "Mouse mode: select and edit", hand: "Hand mode: pan the view", left: "Move left half a window", right: "Move right half a window", minus: "Zoom out", plus: "Zoom in", fit: "Fit all", span: "Span", axis: "Overview range; wheel to zoom, drag the window to pan", window: "Current viewing window", edgeLeft: "Resize left window edge", edgeRight: "Resize right window edge", settings: "Display settings", tick: "Tick interval", auto: "Auto", manual: "Manual", invalid: "Enter a positive span in kb or Mb.", bounded: "Limited to the supported viewing range.", tickInvalid: "Enter a positive tick interval in kb." },
};
export function viewNavText(i18nOrLocale) {
  const locale = typeof i18nOrLocale === "string" ? i18nOrLocale
    : /[\u4e00-\u9fff]/.test(String(i18nOrLocale?.trackControls?.minTickUnitKb || "")) ? "zh" : "en";
  return VIEW_NAV_TEXT[locale === "en" ? "en" : "zh"];
}
const escape = (value) => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
export function renderViewTickControl(trackPrefs, i18n, viewKey, compact = false) {
  const prefs = resolveTrackPrefs(trackPrefs), t = viewNavText(i18n);
  const control = `<label class="view-tick-control" data-view-tick-control="${viewKey}"><span>${t.tick}</span><select data-view-tick-mode aria-label="${t.tick}"><option value="auto"${prefs.tickMode === "auto" ? " selected" : ""}>${t.auto}</option><option value="manual"${prefs.tickMode === "manual" ? " selected" : ""}>${t.manual}</option></select><input type="number" min="0.001" step="any" inputmode="decimal" data-view-tick-interval aria-label="${t.tick} (kb)" value="${prefs.tickIntervalBp / 1000}"${prefs.tickMode === "manual" ? "" : " hidden"}><span${prefs.tickMode === "manual" ? "" : " hidden"}>kb</span></label>`;
  return compact ? control : `<details class="view-display-settings"><summary>${t.settings}</summary><div class="view-display-settings-body">${control}</div></details>`;
}
const paths = {
  mouse: '<path d="M5 3v16l4-4 3 6 3-2-3-6h6Z"/>',
  hand: '<path d="M8 12V5a1.5 1.5 0 0 1 3 0v6-7a1.5 1.5 0 0 1 3 0v7-5a1.5 1.5 0 0 1 3 0v6-3a1.5 1.5 0 0 1 3 0v7c0 4-3 6-7 6-2 0-3-1-4-3l-4-5a1.5 1.5 0 0 1 2-2l2 2Z"/>',
  left: '<path d="m14 6-6 6 6 6M8 12h12"/>', right: '<path d="m10 6 6 6-6 6M4 12h12"/>',
  minus: '<path d="M5 12h14"/>', plus: '<path d="M5 12h14M12 5v14"/>',
};
export function renderViewNavigation(role, locale) {
  const t = viewNavText(locale);
  const button = (action, title) => `<button type="button" class="view-nav-button" data-view-nav-action="${action}" aria-label="${escape(title)}" title="${escape(title)}"${action === "mouse" || action === "hand" ? ' aria-pressed="false"' : ""}><svg viewBox="0 0 24 24" aria-hidden="true">${paths[action]}</svg></button>`;
  return `<div class="assembly-view-navigation" data-view-navigation="${role}" role="group" aria-label="${t.group}"><div class="view-nav-modes">${button("mouse", t.mouse)}${button("hand", t.hand)}</div><div class="view-nav-shift">${button("left", t.left)}${button("right", t.right)}</div><div class="view-nav-axis" data-view-nav-axis title="${t.axis}" aria-label="${t.axis}"><div class="view-nav-window" data-view-nav-window tabindex="0" role="slider" aria-label="${t.window}" aria-orientation="horizontal"><button type="button" class="view-nav-edge is-left" data-view-nav-edge="left" aria-label="${t.edgeLeft}"></button><button type="button" class="view-nav-edge is-right" data-view-nav-edge="right" aria-label="${t.edgeRight}"></button></div></div><div class="view-nav-zoom">${button("minus", t.minus)}${button("plus", t.plus)}</div><label class="view-nav-span">${t.span}<input data-view-nav-span type="text" inputmode="decimal" aria-label="${t.span}" autocomplete="off"><select data-view-nav-unit aria-label="${t.span} unit"><option>kb</option><option>Mb</option></select></label><button type="button" class="view-nav-fit" data-view-nav-action="fit">${t.fit}</button><span class="view-nav-message" data-view-nav-message role="status"></span></div>`;
}
