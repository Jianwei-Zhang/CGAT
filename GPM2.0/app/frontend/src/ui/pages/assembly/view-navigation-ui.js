// Navigation has no business right-click actions. Editable descendants keep
// their native copy/paste menu, and plot/Contig targets remain out of scope.
export function isViewNavigationContextMenuTarget(target) {
  const role = target?.closest?.("[data-view-navigation]")?.dataset?.viewNavigation;
  if (role !== "primary" && role !== "subview") return false;
  return !target.closest?.('input,select,textarea,[contenteditable]:not([contenteditable="false"])');
}

export const VIEW_NAV_TEXT = {
  zh: { group: "查看范围", interaction: "拖动空白平移；Ctrl / ⌘ + 拖动空白框选；横向拖动 Contig 调整位置，拖到目标视图添加；Ctrl + 滚轮缩放，普通滚轮上下滚动", left: "左移半屏", right: "右移半屏", fit: "全览", fitHint: "显示当前视图的全部范围", span: "窗口", axis: "总览范围；拖动范围框平移，Ctrl + 滚轮缩放，普通滚轮上下滚动", window: "当前查看窗口", edgeLeft: "调整窗口左边界", edgeRight: "调整窗口右边界", tick: "刻度间隔", tickOptions: "选择刻度间隔", tickInvalid: "请输入 Auto 或有效的正数；单位为 kb。" },
  en: { group: "Viewing range", interaction: "Drag blank space to pan; Ctrl / ⌘ + drag blank space to box-select; drag contigs horizontally to reposition or onto a destination view to add; Ctrl + wheel to zoom; plain wheel scrolls vertically", left: "Move left half a window", right: "Move right half a window", fit: "Full range", fitHint: "Display the complete viewing range", span: "Window", axis: "Overview range; drag the window to pan, Ctrl + wheel to zoom; plain wheel scrolls vertically", window: "Current viewing window", edgeLeft: "Resize left window edge", edgeRight: "Resize right window edge", tick: "Tick interval", tickOptions: "Choose tick interval", tickInvalid: "Enter Auto or a positive tick interval in kb." },
};
export function viewNavText(i18nOrLocale) {
  const locale = typeof i18nOrLocale === "string" ? i18nOrLocale
    : /[\u4e00-\u9fff]/.test(String(i18nOrLocale?.trackControls?.minTickUnitKb || "")) ? "zh" : "en";
  return VIEW_NAV_TEXT[locale === "en" ? "en" : "zh"];
}
const escape = (value) => String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
export function renderViewTickControl() {
  // Tick spacing is automatic in every assembly view; keep the shared setting hidden.
  return "";
}
const paths = {
  left: '<path d="m14 6-6 6 6 6M8 12h12"/>', right: '<path d="m10 6 6 6-6 6M4 12h12"/>',
};
export function renderViewNavigation(role, locale) {
  const t = viewNavText(locale);
  const icon = (action) => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[action]}</svg>`;
  const button = (action, title) => `<button type="button" class="view-nav-button" data-view-nav-action="${action}" aria-label="${escape(title)}" data-app-tooltip="${escape(title)}">${icon(action)}</button>`;
  return `<div class="assembly-view-navigation" data-view-navigation="${role}" role="group" aria-label="${t.group}" aria-description="${escape(t.interaction)}">
    <div class="view-nav-moves">${button("left", t.left)}${button("right", t.right)}</div>
    <div class="view-nav-range">
      <div class="view-nav-axis" data-view-nav-axis data-app-tooltip="${t.axis}" aria-label="${t.axis}">
        <div class="view-nav-window" data-view-nav-window tabindex="0" role="slider" aria-label="${t.window}" aria-orientation="horizontal">
          <button type="button" class="view-nav-edge is-left" data-view-nav-edge="left" aria-label="${t.edgeLeft}"></button>
          <button type="button" class="view-nav-edge is-right" data-view-nav-edge="right" aria-label="${t.edgeRight}"></button>
        </div>
        <div class="view-nav-grip" data-view-nav-grip aria-hidden="true" hidden></div>
      </div>
      <button type="button" class="view-nav-fit" data-view-nav-action="fit">${t.fit}</button>
    </div>
    <span class="view-nav-span">${t.span}${locale === "en" ? ":" : "："}<span data-view-nav-span aria-label="${t.window}">—</span></span>
  </div>`;
}

// Locale is presentation-only: retain the navigation owner, gesture state and
// focused elements instead of rebuilding its runtime-created sibling toolbar.
export function localizeViewNavigation(bar, locale) {
  const t = viewNavText(locale);
  const attrs = (node, values) => { for (const [key, value] of Object.entries(values)) node?.setAttribute?.(key, value); };
  attrs(bar, { "aria-label": t.group, "aria-description": t.interaction });
  for (const key of ["left", "right"]) attrs(bar.querySelector(`[data-view-nav-action='${key}']`), { "aria-label": t[key], title: t[key] });
  attrs(bar.querySelector("[data-view-nav-axis]"), { title: t.axis, "aria-label": t.axis });
  attrs(bar.querySelector("[data-view-nav-window]"), { "aria-label": t.window });
  attrs(bar.querySelector("[data-view-nav-edge='left']"), { "aria-label": t.edgeLeft });
  attrs(bar.querySelector("[data-view-nav-edge='right']"), { "aria-label": t.edgeRight });
  const fit = bar.querySelector("[data-view-nav-action='fit']");
  if (fit) { attrs(fit, { title: t.fitHint }); fit.textContent = t.fit; }
  const span = bar.querySelector("[data-view-nav-span]");
  attrs(span, { "aria-label": t.window });
  if (span?.previousSibling?.nodeType === 3) span.previousSibling.nodeValue = `${t.span}${locale === "en" ? ":" : "："}`;
}
