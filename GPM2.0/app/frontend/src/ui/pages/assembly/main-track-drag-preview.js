import { createSubviewBandCanvasDragPreview } from "./band-canvas-runtime.js";
import { compileTrackDragPreview } from "./track-drag-preview-runtime.js";

// Fixed-window Main View: collect the rendered geometry once per gesture.
// Canvas owns only band paint; active anchors, labels and evidence stay in SVG.
export function createMainTrackDragPreview(scroll, payload) {
  const svg = scroll?.querySelector?.("svg.assembly-track-svg");
  if (!svg) return null;
  const viewBox = String(svg.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
  const width = Number(svg.getAttribute("width")), height = Number(svg.getAttribute("height"));
  if (viewBox.length !== 4 || !viewBox.every(Number.isFinite)
    || !(viewBox[2] > 0 && viewBox[3] > 0 && width > 0 && height > 0)) return null;
  const plan = compileTrackDragPreview(scroll, payload);
  let bandPreview = null;
  try {
    bandPreview = createSubviewBandCanvasDragPreview(scroll, plan.actions, { width, height });
  } catch {
    // A complete compiled SVG preview remains authoritative if Canvas fails.
  }
  const first = svg.firstElementChild, children = svg.childElementCount;
  let restored = false;
  return {
    isCurrent: () => !restored && scroll.isConnected !== false && svg.isConnected !== false
      && scroll.contains(svg) && svg.firstElementChild === first && svg.childElementCount === children,
    update(offsetPx) {
      if (restored) return false;
      let canvasReady = false;
      try { canvasReady = bandPreview?.draw(offsetPx, viewBox) === true; }
      catch {
        bandPreview?.restore();
        bandPreview = null;
      }
      plan.apply(offsetPx, { skipBandNodes: canvasReady ? bandPreview.nodes : null, hideInactiveAnchors: true });
      return true;
    },
    restore() {
      if (restored) return;
      restored = true;
      bandPreview?.restore();
      plan.clear();
    },
  };
}
