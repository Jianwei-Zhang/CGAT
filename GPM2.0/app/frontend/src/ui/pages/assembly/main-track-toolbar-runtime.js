import { syncToolbarControlWidth, syncToolbarControlWidths } from "./toolbar-control-sizing.js";
import { MAIN_TRACK_TITLE_LAYOUT_EVENT } from "./main-track-title-layout-runtime.js";
import { placeAnchoredPanel, clearAnchoredPanelPlacement } from "./anchored-panel-placement.js";

const BOUND = Symbol("mainTrackToolbarPopupsBound");
export const ALIGNMENT_TOOLBAR_SELECTOR = ":is([data-main-track-toolbar], [data-subview-toolbar])";
const TOOLBAR = ALIGNMENT_TOOLBAR_SELECTOR;

// Only parameter/layer popup placement follows resize/scroll. Toolbar groups
// stay visible; wrapping and reading order are entirely CSS-owned.
export function bindMainTrackToolbarPopups(host) {
  host = host?.closest?.("#route-host") || host;
  if (host?.[BOUND]) { host[BOUND].refresh(); return; }
  if (!host?.addEventListener || !host.querySelector?.(TOOLBAR)) return;
  const win = host.ownerDocument?.defaultView || globalThis.window;
  const destroy = () => {
    host.removeEventListener?.(MAIN_TRACK_TITLE_LAYOUT_EVENT, sync);
    host.removeEventListener?.("scroll", sync, true);
    host.removeEventListener?.("toggle", sync, true);
    host.removeEventListener?.("input", onInput);
    host.removeEventListener?.("change", onInput);
    host.ownerDocument?.fonts?.removeEventListener?.("loadingdone", refresh);
    win?.removeEventListener?.("resize", sync);
    win?.removeEventListener?.("scroll", onViewportScroll, true);
    delete host[BOUND];
  };
  const sync = () => {
    if (host.isConnected === false) return destroy();
    for (const combo of host.querySelectorAll(`${TOOLBAR} [data-track-combo-field].is-open`)) {
      placeAnchoredPanel(combo, combo.querySelector(".assembly-track-combo-menu"), { matchAnchorWidth: false });
    }
    for (const root of host.querySelectorAll(`${TOOLBAR} .assembly-marker-display`)) {
      const panel = root.querySelector(".assembly-marker-display-menu");
      if (panel && !panel.hidden) placeAnchoredPanel(root, panel);
    }
    for (const root of host.querySelectorAll(`${TOOLBAR} .grt-result-layer-menu`)) {
      const panel = root.querySelector(".grt-result-layer-options");
      if (root.open) placeAnchoredPanel(root.querySelector("summary") || root, panel);
      else clearAnchoredPanelPlacement(panel);
    }
  };
  const onInput = event => {
    if (syncToolbarControlWidth(event.target?.closest?.("[data-track-combo-field]"))) sync();
  };
  const refresh = () => { syncToolbarControlWidths(host); sync(); };
  const onViewportScroll = event => { if (!host.contains?.(event.target)) sync(); };
  host.addEventListener(MAIN_TRACK_TITLE_LAYOUT_EVENT, sync);
  host.addEventListener("scroll", sync, true);
  host.addEventListener("toggle", sync, true);
  win?.addEventListener?.("resize", sync);
  win?.addEventListener?.("scroll", onViewportScroll, true);
  host.addEventListener("input", onInput);
  host.addEventListener("change", onInput);
  host.ownerDocument?.fonts?.addEventListener?.("loadingdone", refresh);
  host[BOUND] = { sync, refresh, destroy };
  refresh();
}

export function destroyMainTrackToolbarPopups(host) {
  (host?.closest?.("#route-host") || host)?.[BOUND]?.destroy();
}
