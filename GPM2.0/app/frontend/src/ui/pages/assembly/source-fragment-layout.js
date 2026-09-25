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

export function renderSourceGapConnections(entries, escapeHtml) {
  return entries.slice(1).map((right, index) => {
    const left = entries[index];
    const length = sourceGapBetween(left.ctg, right.ctg);
    const x1 = left.rect.x + left.rect.width;
    const x2 = right.rect.x;
    if (!length || x2 <= x1 || left.y !== right.y) return "";
    return `<line class="track-source-gap" data-source-gap-bp="${length}" x1="${x1.toFixed(2)}" x2="${x2.toFixed(2)}" y1="${left.y}" y2="${right.y}" stroke="#64748b" stroke-width="1" stroke-dasharray="2 2" pointer-events="stroke"><title>${escapeHtml(`Gap: ${length} bp N`)}</title></line>`;
  }).join("");
}
