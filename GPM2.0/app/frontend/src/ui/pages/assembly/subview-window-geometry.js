// Window geometry is UI-only; resizing never alters biological coordinates.
const clamp = (value, low, high) => Math.max(low, Math.min(Number(value) || 0, high));
export const LOCAL_VIEW_RESIZE_EDGES = ["n", "e", "s", "w", "ne", "se", "sw", "nw"];

export function constrainLocalViewRect(rect, viewportWidth, viewportHeight) {
  const vw = Math.max(1, Number(viewportWidth) || 1), vh = Math.max(1, Number(viewportHeight) || 1);
  const width = clamp(rect.width, Math.min(480, vw), vw);
  const height = clamp(rect.height, Math.min(220, vh), vh);
  return { x: clamp(rect.x ?? rect.left, 0, vw - width), y: clamp(rect.y ?? rect.top, 0, vh - height), width, height };
}

export function resizeLocalViewRect(rect, edge, dx, dy, viewportWidth, viewportHeight) {
  const base = constrainLocalViewRect(rect, viewportWidth, viewportHeight);
  if (!LOCAL_VIEW_RESIZE_EDGES.includes(edge)) return base;
  const minWidth = Math.min(480, viewportWidth), minHeight = Math.min(220, viewportHeight);
  let { x: left, y: top } = base;
  let right = left + base.width, bottom = top + base.height;
  if (edge.includes("w")) left = clamp(left + dx, 0, right - minWidth);
  if (edge.includes("e")) right = clamp(right + dx, left + minWidth, viewportWidth);
  if (edge.includes("n")) top = clamp(top + dy, 0, bottom - minHeight);
  if (edge.includes("s")) bottom = clamp(bottom + dy, top + minHeight, viewportHeight);
  return { x: left, y: top, width: right - left, height: bottom - top };
}

// Parameter labels, menus and controls retain their own interactions. Only
// the header's title and unoccupied space start a window move.
export function resolveLocalViewWindowGesture(target) {
  const edge = target?.closest?.("[data-local-view-resize]")?.dataset?.localViewResize;
  if (LOCAL_VIEW_RESIZE_EDGES.includes(edge)) return edge;
  if (!target?.closest?.("[data-local-view-drag]")) return null;
  if (target.closest('button,input,select,textarea,label,a,details,summary,[role="button"],[role="slider"],[contenteditable]:not([contenteditable="false"]),.assembly-track-inline-field,.assembly-track-combo,.subview-history-controls,[data-view-tick-control]')) return null;
  return "move";
}
