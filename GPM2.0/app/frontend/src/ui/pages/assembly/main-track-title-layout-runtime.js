const BOUND = Symbol("mainTrackTitleLayout");
export const MAIN_TRACK_TITLE_LAYOUT_EVENT = "assembly-main-title-layout";
const HEADER = "[data-main-view-header]";
const LABEL = "[data-main-chr-title-full][data-main-chr-title-short]";
const number = value => Number.parseFloat(value) || 0;
const sumStyle = (style, keys) => keys.reduce((sum, key) => sum + number(style[key]), 0);
const horizontalInsets = style => sumStyle(style, ["paddingLeft", "paddingRight", "borderLeftWidth", "borderRightWidth"]);
const horizontalMargins = style => sumStyle(style, ["marginLeft", "marginRight"]);

// Always budget the FULL title, even while showing Chr. Neither the current
// row count nor the shorter label participates in the restoration decision.
export function shouldCompactMainTrackTitle({ availableWidth, fullTitleWidth, groupWidths,
  headerGap = 0, toolbarGap = 0, toolbarInsets = 0 }) {
  if (!(availableWidth > 0) || !(fullTitleWidth > 0) || !groupWidths?.length
    || ![availableWidth, fullTitleWidth, headerGap, toolbarGap, toolbarInsets, ...groupWidths]
      .every(value => Number.isFinite(value) && value >= 0)) return null;
  const required = fullTitleWidth + headerGap + toolbarInsets
    + groupWidths.reduce((sum, width) => sum + width, 0) + toolbarGap * (groupWidths.length - 1);
  return required > availableWidth + 0.5; // tolerate subpixel layout rounding
}

// The only write is this label's text. Measure the full form synchronously,
// then apply the result before paint; controls, focus, popups, order and the
// existing CSS wrapping/scrolling fallback remain untouched.
function syncTitle(header, win) {
  const label = header.querySelector(LABEL);
  const title = header.querySelector("[data-main-track-control-title]");
  const toolbar = header.querySelector("[data-main-track-toolbar]");
  const width = header.getBoundingClientRect().width;
  if (!label || !title || !toolbar || !(width > 0)) return;
  const previous = label.textContent;
  const full = label.dataset.mainChrTitleFull, short = label.dataset.mainChrTitleShort;
  if (!full || !short) return;
  if (label.textContent !== full) label.textContent = full;
  try {
    const headerStyle = win.getComputedStyle(header), titleStyle = win.getComputedStyle(title);
    const toolbarStyle = win.getComputedStyle(toolbar), groupWidths = [];
    for (const group of toolbar.children) {
      const style = win.getComputedStyle(group);
      if (style.display === "none") continue;
      groupWidths.push(group.getBoundingClientRect().width + horizontalMargins(style));
    }
    const compact = shouldCompactMainTrackTitle({ availableWidth: width - horizontalInsets(headerStyle),
      fullTitleWidth: title.getBoundingClientRect().width + horizontalMargins(titleStyle),
      groupWidths, headerGap: number(headerStyle.columnGap), toolbarGap: number(toolbarStyle.columnGap),
      toolbarInsets: horizontalInsets(toolbarStyle) + horizontalMargins(toolbarStyle) });
    const next = compact === null ? previous : compact ? short : full;
    if (label.textContent !== next) label.textContent = next;
  } catch (error) {
    label.textContent = previous;
    throw error;
  }
}

export function bindMainTrackTitleLayout(host) {
  host = host?.closest?.("#route-host") || host;
  if (host?.[BOUND]) { host[BOUND].sync(); return; }
  const win = host?.ownerDocument?.defaultView;
  if (!win?.getComputedStyle || !host.querySelector?.(`${HEADER} ${LABEL}`)) return;
  let disposed = false, frame = null;
  const observed = new Map();
  const fonts = host.ownerDocument.fonts;
  const schedule = () => {
    if (disposed || frame !== null) return;
    if (win.requestAnimationFrame) frame = win.requestAnimationFrame(() => { frame = null; sync(); });
    else sync();
  };
  const observer = win.ResizeObserver ? new win.ResizeObserver(entries => {
    let changed = false;
    for (const entry of entries) {
      if (!observed.has(entry.target)) continue;
      // Label changes can change the number/height of rows. Only widths are
      // relevant, so a height-only notification cannot feed back into layout.
      const width = entry.contentRect.width;
      if (observed.get(entry.target) !== width) { observed.set(entry.target, width); changed = true; }
    }
    if (changed) schedule();
  }) : null;
  const sync = () => {
    if (disposed) return;
    if (host.isConnected === false) { destroy(); return; }
    const targets = new Set();
    for (const header of host.querySelectorAll(HEADER)) {
      if (!header.querySelector(LABEL)) continue;
      syncTitle(header, win);
      targets.add(header);
      for (const group of header.querySelector("[data-main-track-toolbar]")?.children || []) targets.add(group);
    }
    for (const target of observed.keys()) if (!targets.has(target)) {
      observer?.unobserve(target); observed.delete(target);
    }
    for (const target of targets) if (!observed.has(target)) {
      observed.set(target, null); observer?.observe(target);
    }
    // Fixed menus may have been positioned before this label reclaimed space.
    // Re-anchor open menus only, without reopening them or changing UI state.
    if (targets.size && host.dispatchEvent && win.Event) host.dispatchEvent(new win.Event(MAIN_TRACK_TITLE_LAYOUT_EVENT));
  };
  const destroy = () => {
    disposed = true;
    if (frame !== null) win.cancelAnimationFrame?.(frame);
    observer?.disconnect(); observed.clear();
    win.removeEventListener?.("resize", schedule);
    fonts?.removeEventListener?.("loadingdone", schedule);
    delete host[BOUND];
  };
  host[BOUND] = { sync, destroy };
  win.addEventListener?.("resize", schedule);
  fonts?.addEventListener?.("loadingdone", schedule);
  fonts?.ready?.then(schedule);
  sync();
}

export function destroyMainTrackTitleLayout(host) {
  (host?.closest?.("#route-host") || host)?.[BOUND]?.destroy();
}
