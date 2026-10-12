import { isFinalPathCtgSegment, isFinalPathGapSegment } from "./final-path-state.js";

export const FINAL_PATH_SEGMENT_MIN_WIDTH_PX = 8;

function distributeWidthsWithMinimums(baseWidths, totalWidth, minWidths) {
  const resolvedBaseWidths = (Array.isArray(baseWidths) ? baseWidths : []).map((width) =>
    Math.max(0, Number(width) || 0),
  );
  const resolvedMinWidths = (Array.isArray(minWidths) ? minWidths : []).map((width) =>
    Math.max(0, Number(width) || 0),
  );
  const resolvedTotalWidth = Math.max(0, Number(totalWidth) || 0);
  const minWidthSum = resolvedMinWidths.reduce((sum, width) => sum + width, 0);
  if (minWidthSum >= resolvedTotalWidth) {
    const factor = minWidthSum > 0 ? resolvedTotalWidth / minWidthSum : 0;
    return resolvedMinWidths.map((width) => width * factor);
  }
  const leftoverWidth = resolvedTotalWidth - minWidthSum;
  const flexWeights = resolvedBaseWidths.map((width, index) =>
    Math.max(0, width - resolvedMinWidths[index]),
  );
  const flexWeightSum = flexWeights.reduce((sum, width) => sum + width, 0);
  if (flexWeightSum <= 0) {
    const eligibleIndexes = resolvedBaseWidths
      .map((width, index) => (width > 0 || resolvedMinWidths[index] > 0 ? index : -1))
      .filter((index) => index >= 0);
    const sharedExtraWidth = eligibleIndexes.length > 0 ? leftoverWidth / eligibleIndexes.length : 0;
    return resolvedMinWidths.map((width, index) =>
      width + (eligibleIndexes.includes(index) ? sharedExtraWidth : 0),
    );
  }
  return resolvedMinWidths.map((width, index) =>
    width + (leftoverWidth * flexWeights[index]) / flexWeightSum,
  );
}

export function resolveFinalPathVisualLayouts(items, innerWidth) {
  const resolvedInnerWidth = Math.max(0, Number(innerWidth) || 0);
  const ctgItems = [];
  const gapItems = [];
  items.forEach((item, index) => {
    if (isFinalPathGapSegment(item?.segment)) {
      gapItems.push({
        index,
        baseWidth: Math.max(0, Number(item?.width) || 0),
      });
      return;
    }
    if (isFinalPathCtgSegment(item?.segment)) {
      ctgItems.push({
        index,
        baseWidth: Math.max(0, Number(item?.width) || 0),
      });
    }
  });
  const minimumWidth = Math.min(
    FINAL_PATH_SEGMENT_MIN_WIDTH_PX,
    resolvedInnerWidth / Math.max(1, ctgItems.length + gapItems.length),
  );
  const ctgMinWidths = ctgItems.map(() => minimumWidth);
  const desiredGapWidths = gapItems.map(({ baseWidth }) =>
    Math.max(FINAL_PATH_SEGMENT_MIN_WIDTH_PX, baseWidth),
  );
  const maxGapBudget = Math.max(
    0,
    resolvedInnerWidth - ctgMinWidths.reduce((sum, width) => sum + width, 0),
  );
  const gapWidthSum = desiredGapWidths.reduce((sum, width) => sum + width, 0);
  const gapWidths = gapWidthSum <= maxGapBudget
    ? desiredGapWidths
    : distributeWidthsWithMinimums(
      desiredGapWidths,
      maxGapBudget,
      desiredGapWidths.map(() => minimumWidth),
    );
  const ctgBudget = Math.max(0, resolvedInnerWidth - gapWidths.reduce((sum, width) => sum + width, 0));
  const ctgWidths = distributeWidthsWithMinimums(
    ctgItems.map(({ baseWidth }) => baseWidth),
    ctgBudget,
    ctgMinWidths,
  );
  const gapWidthByIndex = new Map(gapItems.map(({ index }, gapIndex) => [index, gapWidths[gapIndex] || 0]));
  const ctgWidthByIndex = new Map(ctgItems.map(({ index }, ctgIndex) => [index, ctgWidths[ctgIndex] || 0]));
  let cursorX = 0;
  return items.map((item, index) => {
    const width = gapWidthByIndex.has(index)
      ? gapWidthByIndex.get(index)
      : ctgWidthByIndex.get(index) || 0;
    const x = cursorX;
    cursorX += width;
    return {
      x,
      width,
    };
  });
}


// Keep the same visual minimum and gap budget as Assembly, without changing
// biological lengths, export coordinates, or segment order.
export function layoutFinalPathStrip(items, viewportWidth, domainLengthBp) {
  const width = Math.max(0, Number(viewportWidth) || 0);
  const total = items.reduce((sum, item) => sum + Math.max(0, Number(item.length) || 0), 0);
  const domain = Math.max(1, Number(domainLengthBp) || 0, total);
  const budget = Math.min(width, Math.max(width * total / domain,
    Math.min(width, FINAL_PATH_SEGMENT_MIN_WIDTH_PX * items.length)));
  return resolveFinalPathVisualLayouts(items.map(item => ({
    segment: item.segment, width: Math.max(0, Number(item.length) || 0) / domain * width,
  })), budget);
}

function syncFullLabelVisibility(label) {
  if (!label?.style) return;
  const needed = Number(label.scrollWidth || 0);
  const available = Number(label.clientWidth || 0);
  label.style.visibility = needed > available ? "hidden" : "";
}

export function syncFinalPathStripGeometry(host) {
  if (!host?.querySelectorAll) return;
  for (const strip of host.querySelectorAll("[data-final-path-strip]")) {
    if (!strip.dataset?.finalPathStrip || !(strip.clientWidth > 0)) continue;
    const nodes = [...strip.querySelectorAll("[data-final-path-segment]")];
    const items = nodes.map(node => ({ segment: { type: node.dataset.finalPathKind },
      length: Math.max(0, Number(node.dataset.finalPathLength) || 0) }));
    const layouts = layoutFinalPathStrip(items, strip.clientWidth, strip.dataset.finalPathDomain);
    nodes.forEach((node, index) => {
      const layout = layouts[index];
      node.style.left = `${layout.x}px`;
      node.style.width = `${layout.width}px`;
      // Preview names are all-or-nothing; preserve the complete tooltip, not
      // a few clipped letters on a short contig or gap. Re-evaluate on resize.
      syncFullLabelVisibility(node.querySelector?.("[data-final-path-fit-label]"));
    });
    for (const label of strip.querySelectorAll("[data-final-path-gap-label]")) {
      const layout = layouts[Number(label.dataset.finalPathGapLabel)];
      if (!layout) continue;
      const halfLabel = Math.min(strip.clientWidth / 2, Math.max(14, Number(label.offsetWidth || 0) / 2));
      label.style.left = `${Math.min(strip.clientWidth - halfLabel, Math.max(halfLabel, layout.x + layout.width / 2))}px`;
    }
    const card = strip.closest?.(".project-preview-card");
    if (!card) continue;
    for (const source of card.querySelectorAll("[data-final-path-aligned-source]")) {
      if (source.dataset.finalPathSourcePath !== strip.dataset.finalPathName) continue;
      const index = Number(source.dataset.finalPathSourceIndex), layout = layouts[index];
      const partLength = items[index]?.length;
      if (!layout || !(partLength > 0)) continue;
      const scale = layout.width / partLength;
      const usedStart = Number(source.dataset.finalPathUsedStart);
      const usedEnd = Number(source.dataset.finalPathUsedEnd);
      const offset = Number(source.dataset.finalPathSourceOffset);
      const length = Number(source.dataset.finalPathSourceLength);
      const x = layout.x + (offset - usedStart) * scale;
      const left = Math.max(0, x), right = Math.min(strip.clientWidth, x + length * scale);
      source.style.left = `${left}px`;
      source.style.width = `${Math.max(0, right - left)}px`;
      source.style.minWidth = "0";
      const patch = source.querySelector(".project-preview-used");
      if (patch) {
        // Absolute children use the parent's inner box (one-pixel borders).
        const usedLeft = layout.x + offset * scale;
        const usedRight = usedLeft + (usedEnd - usedStart) * scale;
        patch.style.left = `${Math.max(0, usedLeft - left - 1)}px`;
        patch.style.width = `${Math.max(0, Math.min(right, usedRight) - Math.max(left, usedLeft) - 1)}px`;
        patch.style.minWidth = "0";
        const label = source.querySelector(".project-preview-contig-label");
        if (label) {
          label.style.position = "absolute";
          label.style.left = patch.style.left;
          label.style.width = patch.style.width;
        }
      }
    }
  }
  // Source labels must be measured after their adopted intervals have been
  // aligned above, not against the much wider whole-contig background strip.
  for (const label of host.querySelectorAll("[data-preview-source-fit-label]")) {
    if (label.dataset?.previewSourceFitLabel === "1") syncFullLabelVisibility(label);
  }
}
