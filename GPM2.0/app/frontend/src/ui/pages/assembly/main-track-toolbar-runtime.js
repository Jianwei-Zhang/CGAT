import { placeAnchoredPanel, clearAnchoredPanelPlacement } from "./anchored-panel-placement.js";

const BOUND = Symbol("mainTrackToolbarPopupsBound");
export const ALIGNMENT_TOOLBAR_SELECTOR = ":is([data-main-track-toolbar], [data-subview-toolbar])";
const TOOLBAR = ALIGNMENT_TOOLBAR_SELECTOR;

// Fixed popups escape the toolbar's extreme-width scrollport. Only popup
// placement follows resize/scroll; wrapping and reading order remain CSS-owned.
export function bindMainTrackToolbarPopups(host) {
  host = host?.closest?.("#route-host") || host;
  if (host?.[BOUND]) { host[BOUND].sync(); return; }
  if (!host?.addEventListener || !host.querySelector?.(TOOLBAR)) return;
  const win = host.ownerDocument?.defaultView || globalThis.window;
  const destroy = () => {
    host.removeEventListener?.("scroll", sync, true);
    host.removeEventListener?.("toggle", sync, true);
    win?.removeEventListener?.("resize", sync);
    win?.removeEventListener?.("scroll", onViewportScroll, true);
    delete host[BOUND];
  };
  const sync = () => {
    if (host.isConnected === false) return destroy();
    for (const combo of host.querySelectorAll(`${TOOLBAR} [data-track-combo-field].is-open`)) {
      placeAnchoredPanel(combo, combo.querySelector(".assembly-track-combo-menu"));
    }
    for (const root of host.querySelectorAll(`${TOOLBAR} .assembly-marker-display`)) {
      const panel = root.querySelector(".assembly-marker-display-menu");
      if (panel && !panel.hidden) placeAnchoredPanel(root, panel);
    }
    for (const root of host.querySelectorAll(`${TOOLBAR} .subview-panel-help`)) {
      const panel = root.querySelector(".subview-panel-guide");
      if (root.open) placeAnchoredPanel(root.querySelector("summary") || root, panel,
        { preferredWidth: 360, matchAnchorWidth: false });
      else clearAnchoredPanelPlacement(panel);
    }
    for (const root of host.querySelectorAll(`${TOOLBAR} .grt-result-layer-menu`)) {
      const panel = root.querySelector(".grt-result-layer-options");
      if (root.open) placeAnchoredPanel(root.querySelector("summary") || root, panel);
      else clearAnchoredPanelPlacement(panel);
    }
  };
  const onViewportScroll = event => { if (!host.contains?.(event.target)) sync(); };
  host.addEventListener("scroll", sync, true);
  host.addEventListener("toggle", sync, true);
  win?.addEventListener?.("resize", sync);
  win?.addEventListener?.("scroll", onViewportScroll, true);
  host[BOUND] = { sync, destroy };
}

export function destroyMainTrackToolbarPopups(host) {
  (host?.closest?.("#route-host") || host)?.[BOUND]?.destroy();
}
