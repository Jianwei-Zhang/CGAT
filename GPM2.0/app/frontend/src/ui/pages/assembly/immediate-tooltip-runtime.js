import { bindAppTooltips, hideAppTooltips } from "../../app-tooltip-runtime.js";

const MARKER_RAISE_BOUND = Symbol("trackAnnotationMarkerRaiseBound");
const MARKER_SELECTOR = '[data-telomere-marker="1"], [data-centromere-marker="1"]';

function bindAnnotationMarkerElevation(host) {
  if (typeof host?.addEventListener !== "function" || host[MARKER_RAISE_BOUND]) {
    return;
  }
  host.addEventListener("pointerover", (event) => {
    const marker = event.target?.closest?.(MARKER_SELECTOR);
    if (!marker) {
      return;
    }
    const markerGroup = marker.parentNode;
    if (markerGroup && markerGroup.lastChild !== marker && typeof markerGroup.appendChild === "function") {
      markerGroup.appendChild(marker);
    }
  });
  host[MARKER_RAISE_BOUND] = true;
}

export function bindImmediateTooltips(host) {
  bindAnnotationMarkerElevation(host);
  return bindAppTooltips(host);
}
export function hideImmediateTooltips(host) { hideAppTooltips(host); }
// Route teardown must not destroy the document owner used by other pages/dialogs.
export function destroyImmediateTooltips(host) { hideAppTooltips(host); }
