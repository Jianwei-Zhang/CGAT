import { normalizeNonNegativeInt, normalizePositiveInt } from "./track-prefs.js";
import { normalizeSupportDatasetId } from "./selection-state.js";

export function buildTrackTickItems({ windowStart, windowEnd, tickBp, innerWidth, domainSpanBp }) {
  const ticks = [];
  const resolvedEnd = Math.max(windowStart, windowEnd);
  const firstTick = Math.max(0, Math.ceil(Math.max(0, windowStart) / tickBp) * tickBp);
  for (let bp = firstTick; bp <= resolvedEnd; bp += tickBp) {
    const x = ((Math.min(bp, resolvedEnd) - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp, x });
  }
  const hasEndTick = ticks.length > 0 && Number(ticks[ticks.length - 1].bp) === Number(resolvedEnd);
  if (!hasEndTick) {
    const endX = ((resolvedEnd - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp: resolvedEnd, x: endX });
  }
  return ticks;
}

export function renderSubviewVirtualRuler({
  windowStart,
  windowEnd,
  tickBp,
  innerWidth,
  domainSpanBp,
  tickY1,
  tickY2,
  tickLabelY,
  edgeLabelPadding = 16,
}) {
  const attributes = [
    ["data-subview-virtual-ruler", "1"],
    ["data-subview-ruler-window-start", windowStart],
    ["data-subview-ruler-window-end", windowEnd],
    ["data-subview-ruler-tick-bp", tickBp],
    ["data-subview-ruler-inner-width", innerWidth],
    ["data-subview-ruler-domain-span-bp", domainSpanBp],
    ["data-subview-ruler-tick-y1", tickY1],
    ["data-subview-ruler-tick-y2", tickY2],
    ["data-subview-ruler-tick-label-y", tickLabelY],
    ["data-subview-ruler-edge-label-padding", edgeLabelPadding],
  ]
    .map(([name, value]) => `${name}="${name === "data-subview-virtual-ruler" ? value : Number(value || 0).toFixed(4)}"`)
    .join(" ");
  return `<g ${attributes}></g>`;
}

export function isTrackTickLabelOverlap(previousTick, endTick) {
  if (!previousTick || !endTick) {
    return false;
  }
  const previousBounds = resolveTrackTickLabelBounds(previousTick);
  const endBounds = resolveTrackTickLabelBounds(endTick);
  return previousBounds.right > endBounds.left;
}

function resolveTrackTickLabelBounds(tick) {
  const width = estimateTrackTickLabelWidth(tick?.labelText || "");
  if (tick?.labelAnchor === "start") {
    return { left: tick.labelX, right: tick.labelX + width };
  }
  if (tick?.labelAnchor === "end") {
    return { left: tick.labelX - width, right: tick.labelX };
  }
  return {
    left: tick.labelX - width / 2,
    right: tick.labelX + width / 2,
  };
}

function estimateTrackTickLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(12, text.length * 7);
}

export function buildTrackRect(ctg, { windowStart, domainSpanBp, innerWidth }) {
  const x = buildTrackBpX({
    bp: ctg.startBp,
    windowStart,
    domainSpanBp,
    innerWidth,
  });
  const width = Math.max(3, (ctg.lengthBp / domainSpanBp) * innerWidth);
  return {
    x,
    width,
    centerX: x + width / 2,
  };
}

export function sortTrackEntriesForRender(entries) {
  const sourceEntries = Array.isArray(entries) ? entries : [];
  const laneBuckets = new Map();
  sourceEntries.forEach((entry) => {
    const laneIndex = Math.max(0, Number(entry?.ctg?.laneIndex ?? 0));
    const bucket = laneBuckets.get(laneIndex) || [];
    bucket.push(entry);
    laneBuckets.set(laneIndex, bucket);
  });
  const laneIndices = Array.from(laneBuckets.keys()).sort((left, right) => left - right);
  return laneIndices.flatMap((laneIndex) => {
    const laneEntries = laneBuckets.get(laneIndex) || [];
    const sortedByX = laneEntries
      .slice()
      .sort((left, right) => {
        const leftX = Number(left?.rect?.x || 0);
        const rightX = Number(right?.rect?.x || 0);
        if (leftX !== rightX) {
          return leftX - rightX;
        }
        const leftCtgId = normalizeSupportDatasetId(left?.ctg?.assemblyCtgId) || 0;
        const rightCtgId = normalizeSupportDatasetId(right?.ctg?.assemblyCtgId) || 0;
        return leftCtgId - rightCtgId;
      });
    if (sortedByX.length <= 1) {
      return sortedByX;
    }

    const overlapGroups = [];
    let currentGroup = [];
    let currentGroupMaxRight = Number.NEGATIVE_INFINITY;
    const flushCurrentGroup = () => {
      if (!currentGroup.length) {
        return;
      }
      overlapGroups.push(currentGroup);
      currentGroup = [];
      currentGroupMaxRight = Number.NEGATIVE_INFINITY;
    };
    sortedByX.forEach((entry) => {
      const x = Number(entry?.rect?.x || 0);
      const width = Math.max(0, Number(entry?.rect?.width || 0));
      const right = x + width;
      if (!currentGroup.length) {
        currentGroup.push(entry);
        currentGroupMaxRight = right;
        return;
      }
      if (x <= currentGroupMaxRight + 0.01) {
        currentGroup.push(entry);
        currentGroupMaxRight = Math.max(currentGroupMaxRight, right);
        return;
      }
      flushCurrentGroup();
      currentGroup.push(entry);
      currentGroupMaxRight = right;
    });
    flushCurrentGroup();

    return overlapGroups.flatMap((group) => {
      if (group.length <= 1) {
        return group;
      }
      return group.sort((left, right) => {
        const leftLength = Math.max(0, Number(left?.ctg?.lengthBp || 0));
        const rightLength = Math.max(0, Number(right?.ctg?.lengthBp || 0));
        if (leftLength !== rightLength) {
          return rightLength - leftLength;
        }
        const leftWidth = Math.max(0, Number(left?.rect?.width || 0));
        const rightWidth = Math.max(0, Number(right?.rect?.width || 0));
        if (leftWidth !== rightWidth) {
          return rightWidth - leftWidth;
        }
        const leftX = Number(left?.rect?.x || 0);
        const rightX = Number(right?.rect?.x || 0);
        if (leftX !== rightX) {
          return leftX - rightX;
        }
        const leftCtgId = normalizeSupportDatasetId(left?.ctg?.assemblyCtgId) || 0;
        const rightCtgId = normalizeSupportDatasetId(right?.ctg?.assemblyCtgId) || 0;
        return leftCtgId - rightCtgId;
      });
    });
  });
}

export function buildTrackRectsWithMinGap(
  ctgs,
  { windowStart, domainSpanBp, innerWidth, minGapPx = 0 },
) {
  const sourceCtgs = Array.isArray(ctgs) ? ctgs : [];
  const rects = sourceCtgs.map((ctg) => buildTrackRect(ctg, { windowStart, domainSpanBp, innerWidth }));
  const resolvedMinGapPx = Math.max(0, Number(minGapPx) || 0);
  if (rects.length <= 1 || !resolvedMinGapPx) {
    return rects;
  }

  const laneBuckets = new Map();
  sourceCtgs.forEach((ctg, index) => {
    const laneIndex = Number(ctg?.laneIndex ?? 0);
    const bucket = laneBuckets.get(laneIndex) || [];
    bucket.push(index);
    laneBuckets.set(laneIndex, bucket);
  });

  laneBuckets.forEach((indices) => {
    indices.sort((leftIndex, rightIndex) => rects[leftIndex].x - rects[rightIndex].x);
    for (let cursor = 0; cursor < indices.length - 1; cursor += 1) {
      const current = rects[indices[cursor]];
      const next = rects[indices[cursor + 1]];
      const currentGap = next.x - (current.x + current.width);
      if (currentGap >= resolvedMinGapPx) {
        continue;
      }
      let neededPx = resolvedMinGapPx - currentGap;
      const maxReduciblePx = Math.max(0, current.width - 3);
      const reducePx = Math.min(maxReduciblePx, neededPx);
      if (reducePx > 0) {
        current.width -= reducePx;
        current.centerX = current.x + current.width / 2;
        neededPx -= reducePx;
      }
      if (neededPx <= 0) {
        continue;
      }
      for (let shiftIndex = cursor + 1; shiftIndex < indices.length; shiftIndex += 1) {
        const shifted = rects[indices[shiftIndex]];
        shifted.x += neededPx;
        shifted.centerX = shifted.x + shifted.width / 2;
      }
    }
  });

  return rects;
}

export function buildTrackHitRect({ ctgStartBp, ctgEndBp, windowStart, domainSpanBp, innerWidth }) {
  const startBp = Math.min(ctgStartBp, ctgEndBp);
  const endBp = Math.max(ctgStartBp, ctgEndBp);
  const x = buildTrackBpX({
    bp: startBp,
    windowStart,
    domainSpanBp,
    innerWidth,
  });
  const width = Math.max(3, ((endBp - startBp + 1) / domainSpanBp) * innerWidth);
  return {
    x,
    width,
    centerX: x + width / 2,
  };
}

export function buildTrackHitRectWithinCtgDisplay({
  ctgRect,
  ctgLengthBp,
  ctgStartOffset,
  ctgEndOffset,
}) {
  const baseX = Number(ctgRect?.x);
  const baseWidth = Number(ctgRect?.width);
  if (!Number.isFinite(baseX) || !Number.isFinite(baseWidth) || baseWidth <= 0) {
    return {
      x: 0,
      width: 1,
      centerX: 0.5,
    };
  }

  const resolvedLengthBp = Math.max(1, normalizePositiveInt(ctgLengthBp) ?? 1);
  const normalizedStart = Number.isFinite(ctgStartOffset) ? ctgStartOffset : 1;
  const normalizedEnd = Number.isFinite(ctgEndOffset) ? ctgEndOffset : resolvedLengthBp;
  const hitStartBp = Math.min(normalizedStart, normalizedEnd);
  const hitEndBp = Math.max(normalizedStart, normalizedEnd);
  const clampedStartBp = Math.max(1, Math.min(resolvedLengthBp, hitStartBp));
  const clampedEndBp = Math.max(1, Math.min(resolvedLengthBp, hitEndBp));
  const startRatio = (clampedStartBp - 1) / resolvedLengthBp;
  const hitSpanBp = Math.max(1, clampedEndBp - clampedStartBp + 1);
  const x = baseX + startRatio * baseWidth;
  const maxAvailableWidth = Math.max(1, baseX + baseWidth - x);
  const width = Math.max(1, Math.min(maxAvailableWidth, (hitSpanBp / resolvedLengthBp) * baseWidth));

  return {
    x,
    width,
    centerX: x + width / 2,
  };
}

export function resolveHitMapq(hit) {
  return Math.max(0, normalizeNonNegativeInt(hit?.mapq ?? hit?.mapQ) ?? 0);
}

export function buildTrackBpX({ bp, windowStart, domainSpanBp, innerWidth }) {
  return ((bp - windowStart) / domainSpanBp) * innerWidth;
}

export function buildTrackReferenceWidth(chrLength, domainSpanBp, innerWidth) {
  const spanBp = Math.max(1, normalizePositiveInt(chrLength) ?? domainSpanBp);
  return Math.max(3, (spanBp / domainSpanBp) * innerWidth);
}

export function resolveMaxTrackEndBp(ctgs) {
  return (Array.isArray(ctgs) ? ctgs : []).reduce((maxEndBp, ctg) => {
    const endBp = normalizePositiveInt(ctg?.endBp);
    if (endBp !== null) {
      return Math.max(maxEndBp, endBp);
    }
    const startBp = normalizePositiveInt(ctg?.startBp);
    const lengthBp = normalizePositiveInt(ctg?.lengthBp);
    if (startBp === null || lengthBp === null) {
      return maxEndBp;
    }
    return Math.max(maxEndBp, startBp + lengthBp - 1);
  }, 0);
}

export function buildCollinearityBandPoints({
  ctgRect,
  refRect,
  refLeftClamp = 0,
  refRightClamp = Number.POSITIVE_INFINITY,
  refTop,
  refBottom,
  ctgTop,
  ctgBottom,
  direction,
  reversed = false,
}) {
  const ctgLeft = ctgRect.x;
  const ctgRight = ctgRect.x + ctgRect.width;
  const refLeft = Math.max(refLeftClamp, refRect.x);
  const refRight = Math.min(refRightClamp, refRect.x + refRect.width);
  if (direction === "down") {
    if (reversed) {
      return [
        `${ctgLeft.toFixed(2)},${ctgBottom.toFixed(2)}`,
        `${ctgRight.toFixed(2)},${ctgBottom.toFixed(2)}`,
        `${refLeft.toFixed(2)},${refTop.toFixed(2)}`,
        `${refRight.toFixed(2)},${refTop.toFixed(2)}`,
      ].join(" ");
    }
    return [
      `${ctgLeft.toFixed(2)},${ctgBottom.toFixed(2)}`,
      `${ctgRight.toFixed(2)},${ctgBottom.toFixed(2)}`,
      `${refRight.toFixed(2)},${refTop.toFixed(2)}`,
      `${refLeft.toFixed(2)},${refTop.toFixed(2)}`,
    ].join(" ");
  }
  if (reversed) {
    return [
      `${refLeft.toFixed(2)},${refBottom.toFixed(2)}`,
      `${refRight.toFixed(2)},${refBottom.toFixed(2)}`,
      `${ctgLeft.toFixed(2)},${ctgTop.toFixed(2)}`,
      `${ctgRight.toFixed(2)},${ctgTop.toFixed(2)}`,
    ].join(" ");
  }
  return [
    `${refLeft.toFixed(2)},${refBottom.toFixed(2)}`,
    `${refRight.toFixed(2)},${refBottom.toFixed(2)}`,
    `${ctgRight.toFixed(2)},${ctgTop.toFixed(2)}`,
    `${ctgLeft.toFixed(2)},${ctgTop.toFixed(2)}`,
  ].join(" ");
}
