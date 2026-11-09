import { buildFinalPathAppendPreview } from "./final-path-runtime.js";

const SVG = "http://www.w3.org/2000/svg";
function stripIds(root) {
  root.removeAttribute?.("id");
  for (const node of root.querySelectorAll?.("[id]") || []) node.removeAttribute("id");
}

// Copy the actual visible source bar, cropping the SVG to the selected fragment.
// The original node is never detached, transformed or faded.
export function createFinalPathDragCopy(doc, target) {
  const fragment = target.closest?.("[data-main-fragment-start], [data-subview-fragment-key]");
  const bar = target.closest?.("[data-track-contig-id][data-track-role], [data-subview-track-pair-contig-id]");
  const region = fragment || bar;
  if (!region?.getBBox || !bar?.cloneNode || !doc.createElementNS) return null;
  let box;
  try { box = region.getBBox(); } catch { return null; }
  if (!(box.width > 0 && box.height > 0)) return null;
  const svg = doc.createElementNS(SVG, "svg");
  const copy = bar.cloneNode(true);
  stripIds(copy); copy.removeAttribute("transform");
  svg.setAttribute("viewBox", `${box.x} ${box.y} ${box.width} ${box.height}`);
  svg.setAttribute("width", String(Math.max(100, Math.min(360, box.width))));
  svg.setAttribute("height", String(Math.max(18, Math.min(42, box.height))));
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("final-path-append-source-copy");
  svg.appendChild(copy);
  return svg;
}

export function createFinalPathAppendPreview(doc, state, context, target, renderCard) {
  const candidate = buildFinalPathAppendPreview(state, context, { targetChrName: target.targetChrName });
  if (!candidate) return null;
  const projected = { ...state, assembly: { ...state.assembly,
    finalPathByChr: { ...state.assembly.finalPathByChr, [target.targetChrName]: candidate.entry } } };
  const template = doc.createElement("template");
  template.innerHTML = renderCard(projected);
  const card = [...template.content.querySelectorAll("[data-final-path-all-card]")]
    .find(node => node.dataset.finalPathAllCard === target.targetChrName)
    || template.content.querySelector(".final-path-card");
  const graph = target.surface.matches("[data-final-path-graph-viewport]");
  const preview = card?.querySelector(graph ? "[data-final-path-graph-viewport]" : "[data-final-path-card-list]");
  if (!preview) return null;
  const added = new Set(candidate.nextSegments.map(segment => segment.segmentId));
  for (const node of preview.querySelectorAll("[data-final-path-segment-id]")) {
    if (added.has(node.dataset.finalPathSegmentId)) node.classList.add("is-final-path-append-candidate");
  }
  stripIds(preview);
  const overlay = doc.createElement("div");
  overlay.className = `final-path-append-preview is-${graph ? "graph" : "table final-path-card-table-body"}`;
  overlay.setAttribute("aria-hidden", "true");
  overlay.appendChild(preview);
  preview.setAttribute("data-final-path-append-preview-scroll", "1");
  return overlay;
}
