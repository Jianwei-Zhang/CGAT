// Shared endpoint provenance belongs to a rendered group, never to persisted
// evidence. Per-edge identity/cuts and every hit target remain independent.
const SHARED_FIELDS = ["endpoint-key", "length-bp", "name", "source-label", "source-role", "source-kind", "source-name"];
const SHARED_ATTRIBUTES = ["top", "bottom"].flatMap(side => SHARED_FIELDS.map(field => [
  `data-subview-anchor-${side}-${field}`,
  side + field.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()).replace(/^./, c => c.toUpperCase()),
]));

export function readSubviewAnchorAttribute(node, name) {
  const own = node?.getAttribute?.(name);
  if (own !== null && own !== undefined) return own;
  if (!name.startsWith("data-subview-anchor-")) return null;
  const group = node?.closest?.("[data-subview-anchor-metadata='1']");
  return group?.getAttribute?.(name) ?? null;
}

export function renderCompactSubviewAnchors(edges, metrics, { escapeAttr, buildObjectId }) {
  const chunks = [], activeLines = [];
  let previous = null;
  for (const edge of edges) {
    if (!previous || SHARED_ATTRIBUTES.some(([, field]) => (previous[field] ?? "") !== (edge[field] ?? ""))) {
      if (previous) chunks.push("</g>");
      chunks.push(`<g data-subview-anchor-metadata="1" ${SHARED_ATTRIBUTES.map(([name, field]) => `${name}="${escapeAttr(edge[field] ?? "")}"`).join(" ")}>`);
      previous = edge;
    }
    const kind = edge.manualAnchorId ? "manual" : "evidence";
    const side = edge.manualAnchorId ? "manual" : String(edge.edge || "");
    const objectId = buildObjectId(kind, edge.manualAnchorId || edge.hitKey, side);
    const coordinates = `x1="${Number(edge.topX || 0).toFixed(2)}" y1="${Number(metrics.hitTopY ?? edge.hitTopY ?? edge.topY ?? metrics.topY ?? 0).toFixed(2)}" x2="${Number(edge.bottomX || 0).toFixed(2)}" y2="${Number(metrics.hitBottomY ?? edge.hitBottomY ?? edge.bottomY ?? metrics.bottomY ?? 0).toFixed(2)}"`;
    const ownership = `data-subview-anchor-preview="1" data-subview-anchor-top-contig-id="${Number(edge.topContigId || 0)}" data-subview-anchor-bottom-contig-id="${Number(edge.bottomContigId || 0)}"`;
    if (edge.active) activeLines.push(`<line class="subview-anchor-line is-active" ${coordinates} stroke="red" stroke-width="3" pointer-events="none" data-subview-anchor-object-id="${escapeAttr(objectId)}" ${ownership}/>`);
    chunks.push(`<line class="subview-anchor-hit-zone${edge.active ? " is-active" : ""}" ${coordinates} stroke="transparent" stroke-width="3" pointer-events="stroke" ${ownership} data-subview-anchor-kind="${kind}" data-subview-anchor-object-id="${escapeAttr(objectId)}" data-subview-anchor-hit-key="${escapeAttr(edge.hitKey)}" data-subview-anchor-edge="${escapeAttr(side)}" data-subview-anchor-active="${edge.active ? "1" : "0"}" data-subview-manual-anchor-id="${escapeAttr(edge.manualAnchorId || "")}" data-subview-anchor-top-cut-bp="${Number(edge.topCutBp || 0)}" data-subview-anchor-bottom-cut-bp="${Number(edge.bottomCutBp || 0)}" data-subview-anchor-top-x="${Number(edge.topX || 0).toFixed(4)}" data-subview-anchor-bottom-x="${Number(edge.bottomX || 0).toFixed(4)}"/>`);
  }
  if (previous) chunks.push("</g>");
  return chunks.join("") + activeLines.join("");
}
