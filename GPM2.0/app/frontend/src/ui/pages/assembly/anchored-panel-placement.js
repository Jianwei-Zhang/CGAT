// Placement only: never measures/reorders toolbar groups or mutates app state.
const naturalWidths = new WeakMap();
const finite = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

export function resolveAnchoredPanelRect({ anchor, width, height, viewportWidth, viewportHeight, margin = 8, gap = 4, matchAnchorWidth = true }) {
  const vw = finite(viewportWidth), vh = finite(viewportHeight);
  if (vw <= 0 || vh <= 0) return null;
  const inset = Math.min(margin, vw / 4, vh / 4);
  const left = finite(anchor?.left), top = finite(anchor?.top);
  const right = finite(anchor?.right ?? left + finite(anchor?.width));
  const bottom = finite(anchor?.bottom ?? top + finite(anchor?.height));
  if (bottom <= 0 || top >= vh || right <= 0 || left >= vw) return null;
  const panelWidth = clamp(Math.max(finite(width), matchAnchorWidth ? right - left : 1), 1, vw - 2 * inset);
  const below = Math.max(0, vh - bottom - gap - inset), above = Math.max(0, top - gap - inset);
  const upward = finite(height) > below && above > below;
  const maxHeight = Math.max(1, upward ? above : below);
  const panelHeight = Math.min(Math.max(1, finite(height)), maxHeight);
  return { left: clamp(left, inset, vw - inset - panelWidth),
    top: clamp(upward ? top - gap - panelHeight : bottom + gap, inset, vh - inset - panelHeight),
    width: panelWidth, maxHeight, upward };
}

export function placeAnchoredPanel(anchor, panel, options = {}) {
  if (!anchor?.getBoundingClientRect || !panel?.getBoundingClientRect || !panel.style) return null;
  const win = anchor.ownerDocument?.defaultView || globalThis.window;
  const viewportWidth = finite(options.viewportWidth ?? win?.innerWidth);
  const viewportHeight = finite(options.viewportHeight ?? win?.innerHeight);
  if (!viewportWidth || !viewportHeight) return null;
  const anchorRect = anchor.getBoundingClientRect(), panelRect = panel.getBoundingClientRect();
  if (!naturalWidths.has(panel)) naturalWidths.set(panel, panelRect.width);
  const horizontal = resolveAnchoredPanelRect({ anchor: anchorRect,
    width: options.preferredWidth ?? naturalWidths.get(panel), height: 1, viewportWidth, viewportHeight, ...options });
  if (!horizontal) { panel.style.visibility = "hidden"; return null; }
  // Constrain width first: a button grid can become much taller when it wraps.
  // Vertical/upward placement must use that reflowed height, not the old width.
  Object.assign(panel.style, { position: "fixed", boxSizing: "border-box", width: `${horizontal.width}px`, minWidth: "0", maxWidth: `${viewportWidth}px` });
  const constrainedRect = panel.getBoundingClientRect();
  const rect = resolveAnchoredPanelRect({ anchor: anchorRect,
    width: horizontal.width,
    height: Math.max(finite(panel.scrollHeight), finite(constrainedRect.height)), viewportWidth, viewportHeight,
    ...options });
  if (!rect) { panel.style.visibility = "hidden"; return null; }
  Object.assign(panel.style, { position: "fixed", boxSizing: "border-box", right: "auto", bottom: "auto",
    left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, minWidth: "0",
    maxWidth: `${viewportWidth}px`, maxHeight: `${rect.maxHeight}px`, overflowY: "auto", visibility: "" });
  return rect;
}

export function clearAnchoredPanelPlacement(panel) {
  if (!panel?.style) return;
  naturalWidths.delete(panel);
  for (const key of ["position", "boxSizing", "left", "right", "top", "bottom", "width", "minWidth", "maxWidth", "maxHeight", "overflowY", "visibility"]) panel.style[key] = "";
}
