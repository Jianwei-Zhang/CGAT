// Apply only to a detached export clone. Live objects use app-owned tooltips.
export function restoreSvgTooltipTitles(clone) {
  const restored = new Set();
  const restore = (node, text) => {
    if (!node || !text || restored.has(node) || node.querySelector?.(":scope > title")) return;
    const title = node.ownerDocument.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = text; node.append(title); restored.add(node);
  };
  for (const attribute of ["data-final-path-tooltip", "data-app-tooltip", "data-member-tooltip", "data-subview-band-tooltip"]) {
    for (const node of clone.querySelectorAll(`[${attribute}]`)) restore(node, node.getAttribute(attribute));
  }
  for (const desc of clone.querySelectorAll("desc[data-app-tooltip-source]")) restore(desc.parentElement, desc.textContent);
  return clone;
}
