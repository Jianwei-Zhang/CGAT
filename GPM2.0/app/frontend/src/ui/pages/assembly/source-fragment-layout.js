// Gap lengths are source bases, independent of the minimum screen spacing.
export function sourceGapBetween(left, right) {
  const a = left?.sourceFragment;
  const b = right?.sourceFragment;
  if (!a || !b || a.sourceSeqId !== b.sourceSeqId || a.groupKey !== b.groupKey) return null;
  const reverse = (left.orient ?? left.refOrient) === "-";
  if (reverse !== ((right.orient ?? right.refOrient) === "-")) return null;
  const length = reverse ? a.sourceStart - b.sourceEnd - 1 : b.sourceStart - a.sourceEnd - 1;
  return length > 0 && length === (reverse ? a.gapBeforeBp : a.gapAfterBp)
    && length === (reverse ? b.gapAfterBp : b.gapBeforeBp) ? length : null;
}

export function sourceTerminalGap(ctg, before) {
  const part = ctg?.sourceFragment;
  if (!part) return 0;
  const reverse = (ctg.orient ?? ctg.refOrient) === "-";
  if (before !== reverse) return part.sourceStart === part.gapBeforeBp + 1 ? part.gapBeforeBp : 0;
  return part.sourceEnd + part.gapAfterBp === part.sourceLength ? part.gapAfterBp : 0;
}

// Each entry supplies the fragment rectangle's top edge and height.
export function renderSourceGapConnections(entries, escapeHtml) {
  return entries.slice(1).map((right, index) => {
    const left = entries[index];
    const length = sourceGapBetween(left.ctg, right.ctg);
    const x1 = left.rect.x + left.rect.width;
    const x2 = right.rect.x;
    if (!length || x2 <= x1 || left.y !== right.y || left.height !== right.height) return "";
    return ["top", "bottom"].map((edge) => {
      const y = left.y + (edge === "bottom" ? left.height : 0);
      return `<line class="track-source-gap" data-source-gap-left-key="${escapeHtml(left.dragKey || "")}" data-source-gap-right-key="${escapeHtml(right.dragKey || "")}" data-source-gap-bp="${length}" data-source-gap-edge="${edge}" x1="${x1.toFixed(2)}" x2="${x2.toFixed(2)}" y1="${y}" y2="${y}" stroke="#64748b" stroke-width="1" stroke-dasharray="2 2" pointer-events="stroke"><title>${escapeHtml(`Gap: ${length} bp N`)}</title></line>`;
    }).join("");
  }).join("");
}

// Drag-only identity: selection/editing still address each fragment separately.
export function sourceFragmentDragAttrs(ctg, escapeAttr) {
  const part = ctg?.sourceFragment;
  if (!part?.sourceSeqId || !part?.groupKey) return "";
  return `data-source-fragment-seq-id="${Number(part.sourceSeqId)}" data-source-fragment-group="${escapeAttr(part.groupKey)}"`;
}

// A manual child can retain an exterior N-delimited edge from its parent.
// That edge is not a new cut merely because its source coordinate is not 1.
// The gap metadata is source-owned, so this works even after its sibling moves
// to another view/chromosome or is deleted.
export function resolveManualSplitSourceCuts(ctg) {
  const part = ctg?.sourceFragment;
  if (!String(part?.groupKey || "").startsWith("manual-fragment:")) return [];
  return [Number(part.sourceStart) > 1 && !(Number(part.gapBeforeBp) > 0) ? Number(part.sourceStart) - 1 : null,
    Number(part.sourceEnd) < Number(part.sourceLength) && !(Number(part.gapAfterBp) > 0) ? Number(part.sourceEnd) : null]
    .filter((cut) => Number.isSafeInteger(cut) && cut > 0);
}

// Render actual source cuts on any presentation of their retained interval.
// Joined Local View members can contain a real cut internally; clipping a local
// interval must neither move that cut to an outer edge nor invent a new one.
export function renderSourceSplitMarkers(cuts, range, rect, y, height, escapeHtml) {
  const start = Number(range?.sourceStart), end = Number(range?.sourceEnd);
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 1 || end < start) return "";
  const reverse = range.orient === "-";
  return [...new Set(cuts)].filter((cut) => Number.isSafeInteger(cut) && cut >= start - 1 && cut <= end && cut > 0)
    .sort((a, b) => a - b).map((source) => {
      const fraction = (source - start + 1) / (end - start + 1);
      const x = rect.x + (reverse ? 1 - fraction : fraction) * rect.width;
      return `<path class="track-manual-split" data-manual-split-after="${source}" d="M ${x - 2} ${y - 3} l 4 5 l -4 5 l 4 ${height - 4}" fill="none" stroke="#a45528" stroke-width="1.5" pointer-events="none"><title>${escapeHtml(`Split after source base ${source}; no inserted bases`)}</title></path>`;
    }).join("");
}

export function renderManualSplitMarkers(ctg, rect, y, height, escapeHtml) {
  return renderSourceSplitMarkers(resolveManualSplitSourceCuts(ctg), {
    ...ctg?.sourceFragment, orient: ctg?.orient ?? ctg?.refOrient,
  }, rect, y, height, escapeHtml);
}
