// Drop geometry belongs to the rendered destination, not to Main's viewport.
export function resolveSubviewContigDropTarget(node, y) {
  const window = node?.closest?.("[data-local-view-window]");
  if (!window || window.hidden || window.inert || window.closest?.("[hidden]")) return null;
  const surface = node.closest?.(".subview-track-scroll");
  const svg = surface?.querySelector?.("svg[data-subview-drop-top-y]");
  if (!svg) return null;
  const rect = svg.getBoundingClientRect();
  const top = Number(svg.dataset.subviewDropTopY), bottom = Number(svg.dataset.subviewDropBottomY);
  const height = Number(svg.viewBox?.baseVal?.height || svg.getAttribute("height"));
  if (!(rect.height > 0 && height > 0 && bottom > top)) return null;
  const worldY = (y - rect.top) * height / rect.height;
  // Reject rulers and empty card margins, but retain both empty lane targets.
  if (worldY < top - 28 || worldY > bottom + 42) return null;
  const middle = (top + bottom) / 2;
  const lane = worldY < middle ? "top" : "bottom";
  const bounds = surface.getBoundingClientRect();
  const start = lane === "top" ? top - 24 : middle;
  const end = lane === "top" ? middle : bottom + 38;
  return { kind: "local", surface, window, id: window.dataset.localViewWindow, lane,
    rect: { left: bounds.left, width: bounds.width,
      top: Math.max(bounds.top, rect.top + start * rect.height / height),
      bottom: Math.min(bounds.bottom, rect.top + end * rect.height / height) } };
}
