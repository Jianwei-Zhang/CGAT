import { resolveTrackPrefs } from "./track-prefs.js";

const MIN_ADJACENT_GAP_PX = 20;
const BASE_VIEWPORT_PX = 1200;
const MAX_TRACK_WIDTH_PX = 16000;

export function normalizeCtgs(ctgs, { preserveInputOrder = false } = {}) {
  if (!Array.isArray(ctgs) || ctgs.length === 0) {
    return [];
  }

  const sorted = preserveInputOrder
    ? ctgs.slice()
    : ctgs
      .map((ctg, index) => ({ ctg, index }))
      .sort((left, right) => compareByAnchorStart(left.ctg, right.ctg) || left.index - right.index)
      .map(({ ctg }) => ctg);

  let layoutCursorBp = 0;
  return sorted.map((ctg) => {
    const lengthBp = Math.max(1, normalizePositiveInt(ctg?.totalLength) ?? 1);
    const startBp = layoutCursorBp;
    const endBp = startBp + lengthBp - 1;
    layoutCursorBp = endBp + 1;
    return {
      ...ctg,
      startBp,
      endBp,
      lengthBp,
    };
  });
}

export function placeIntoLanes(ctgs, laneGapBp = 1) {
  if (!Array.isArray(ctgs) || ctgs.length === 0) {
    return [];
  }

  const normalizedGap = Math.max(0, normalizePositiveInt(laneGapBp) ?? 0);
  const laneEnds = [];
  return ctgs.map((ctg) => {
    let laneIndex = 0;
    while (laneIndex < laneEnds.length && ctg.startBp <= laneEnds[laneIndex] + normalizedGap) {
      laneIndex += 1;
    }
    laneEnds[laneIndex] = ctg.endBp;
    return {
      ...ctg,
      laneIndex,
    };
  });
}

export function buildSingleTrackModel({
  ctgs,
  selectedCtgId = null,
  prefs,
  windowStart = null,
  windowEnd = null,
  innerWidth = null,
  preserveInputOrder = false,
}) {
  const trackPrefs = resolveTrackPrefs(prefs);
  const viewSpanBp = resolveViewSpanBp(trackPrefs.viewSpanKb);
  const tickBp = trackPrefs.tickBp;
  const alignmentLength = trackPrefs.alignmentLength;
  const normalizedCtgs = normalizeCtgs(ctgs, { preserveInputOrder });
  const dataStart = normalizedCtgs.length ? normalizedCtgs[0].startBp : 0;
  const dataEnd = normalizedCtgs.length
    ? Math.max(...normalizedCtgs.map((ctg) => ctg.endBp))
    : dataStart + viewSpanBp - 1;
  const resolvedWindowStart =
    windowStart !== null && windowStart !== undefined
      ? Math.trunc(windowStart)
      : alignDown(dataStart, alignmentLength);
  const resolvedWindowEnd =
    windowEnd !== null && windowEnd !== undefined
      ? Math.max(resolvedWindowStart, Math.trunc(windowEnd))
      : Math.max(alignUp(dataEnd + 1, alignmentLength) - 1, resolvedWindowStart + viewSpanBp - 1);
  const domainSpanBp = Math.max(1, resolvedWindowEnd - resolvedWindowStart + 1);
  const desiredWidth = Math.max(1, Math.ceil((domainSpanBp / viewSpanBp) * BASE_VIEWPORT_PX));
  const resolvedInnerWidth =
    innerWidth !== null && innerWidth !== undefined
      ? Math.max(BASE_VIEWPORT_PX, Math.trunc(innerWidth))
      : clamp(desiredWidth, BASE_VIEWPORT_PX, MAX_TRACK_WIDTH_PX);
  const laneGapBp = 0;
  const laneCtgs = placeIntoLanes(normalizedCtgs, laneGapBp);
  const renderedCtgs = applyVisualLaneGap(laneCtgs.map((ctg) => {
    const x = roundToTwo(((ctg.startBp - resolvedWindowStart) / domainSpanBp) * resolvedInnerWidth);
    const width = roundToTwo(Math.max(3, (ctg.lengthBp / domainSpanBp) * resolvedInnerWidth));
    return {
      ...ctg,
      isSelected: Number(ctg.assemblyCtgId) === Number(selectedCtgId),
      x,
      width,
      labelX: roundToTwo(x + 4),
    };
  }), MIN_ADJACENT_GAP_PX);
  const focusCtg = renderedCtgs.find((ctg) => ctg.isSelected) || renderedCtgs[0] || null;
  const ticks = buildTicks({
    windowStart: resolvedWindowStart,
    windowEnd: resolvedWindowEnd,
    tickBp,
    innerWidth: resolvedInnerWidth,
    domainSpanBp,
  });

  return {
    windowStart: resolvedWindowStart,
    windowEnd: resolvedWindowEnd,
    viewSpanBp,
    innerWidth: resolvedInnerWidth,
    domainSpanBp,
    laneCount: renderedCtgs.length
      ? Math.max(...renderedCtgs.map((ctg) => ctg.laneIndex)) + 1
      : 0,
    ticks,
    ctgs: renderedCtgs,
    focusCenterX: focusCtg ? roundToTwo(focusCtg.x + focusCtg.width / 2) : 0,
    compressed: desiredWidth > resolvedInnerWidth,
  };
}

export function buildDualTrackModel({
  primaryCtgs,
  companionCtgs,
  selectedPrimaryCtgId = null,
  selectedCompanionCtgId = null,
  prefs,
  preserveInputOrder = false,
}) {
  const trackPrefs = resolveTrackPrefs(prefs);
  const viewSpanBp = resolveViewSpanBp(trackPrefs.viewSpanKb);
  const alignmentLength = trackPrefs.alignmentLength;
  const allCtgs = [
    ...normalizeCtgs(primaryCtgs, { preserveInputOrder }),
    ...normalizeCtgs(companionCtgs, { preserveInputOrder }),
  ];
  const sharedDataStart = allCtgs.length ? Math.min(...allCtgs.map((ctg) => ctg.startBp)) : 0;
  const sharedWindowStart = allCtgs.length ? alignDown(sharedDataStart, alignmentLength) : 0;
  const sharedDataEnd = allCtgs.length ? Math.max(...allCtgs.map((ctg) => ctg.endBp)) : viewSpanBp - 1;
  const sharedWindowEnd = Math.max(
    alignUp(sharedDataEnd + 1, alignmentLength) - 1,
    sharedWindowStart + viewSpanBp - 1,
  );
  const sharedDomainSpanBp = Math.max(1, sharedWindowEnd - sharedWindowStart + 1);
  const sharedInnerWidth = clamp(
    Math.ceil((sharedDomainSpanBp / viewSpanBp) * BASE_VIEWPORT_PX),
    BASE_VIEWPORT_PX,
    MAX_TRACK_WIDTH_PX,
  );

  const primary = buildSingleTrackModel({
    ctgs: primaryCtgs,
    selectedCtgId: selectedPrimaryCtgId,
    prefs,
    windowStart: sharedWindowStart,
    windowEnd: sharedWindowEnd,
    innerWidth: sharedInnerWidth,
    preserveInputOrder,
  });
  const companion = buildSingleTrackModel({
    ctgs: companionCtgs,
    selectedCtgId: selectedCompanionCtgId,
    prefs,
    windowStart: sharedWindowStart,
    windowEnd: sharedWindowEnd,
    innerWidth: sharedInnerWidth,
    preserveInputOrder,
  });

  return {
    windowStart: sharedWindowStart,
    windowEnd: sharedWindowEnd,
    innerWidth: sharedInnerWidth,
    viewSpanBp,
    primary,
    companion,
  };
}

function buildTicks({ windowStart, windowEnd, tickBp, innerWidth, domainSpanBp }) {
  const ticks = [];
  const firstTick = Math.max(tickBp, Math.ceil(windowStart / tickBp) * tickBp);
  let index = 1;
  for (let bp = firstTick; bp <= windowEnd + 1; bp += tickBp) {
    const clampedBp = Math.min(bp, windowEnd + 1);
    const x = roundToTwo(((clampedBp - windowStart) / domainSpanBp) * innerWidth);
    ticks.push({ bp, x, index });
    index += 1;
  }
  return ticks;
}

function compareByAnchorStart(left, right) {
  const leftStart = normalizeAnchorStart(left?.anchorStart);
  const rightStart = normalizeAnchorStart(right?.anchorStart);
  if (leftStart === null && rightStart === null) {
    return 0;
  }
  if (leftStart === null) {
    return 1;
  }
  if (rightStart === null) {
    return -1;
  }
  return leftStart - rightStart;
}

function resolveViewSpanBp(viewSpanKb) {
  return Math.max(1, (normalizePositiveInt(viewSpanKb) ?? 1) * 1000);
}

function normalizePositiveInt(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.max(1, Math.trunc(parsed));
}

function normalizeAnchorStart(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.trunc(parsed);
}

function alignDown(value, step) {
  return Math.floor(value / step) * step;
}

function alignUp(value, step) {
  return Math.ceil(value / step) * step;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function roundToTwo(value) {
  return Math.round(value * 100) / 100;
}

function applyVisualLaneGap(ctgs, minGapPx) {
  if (!Array.isArray(ctgs) || ctgs.length <= 1) {
    return ctgs;
  }
  const resolvedMinGapPx = Math.max(0, Number(minGapPx) || 0);
  if (!resolvedMinGapPx) {
    return ctgs;
  }

  const adjusted = ctgs.map((ctg) => ({ ...ctg }));
  const laneIndices = new Map();
  adjusted.forEach((ctg, index) => {
    const lane = Number(ctg.laneIndex || 0);
    const bucket = laneIndices.get(lane) || [];
    bucket.push(index);
    laneIndices.set(lane, bucket);
  });

  laneIndices.forEach((indices) => {
    indices.sort((leftIndex, rightIndex) => adjusted[leftIndex].x - adjusted[rightIndex].x);
    for (let cursor = 0; cursor < indices.length - 1; cursor += 1) {
      const current = adjusted[indices[cursor]];
      const next = adjusted[indices[cursor + 1]];
      const currentRight = current.x + current.width;
      const currentGap = next.x - currentRight;
      if (currentGap >= resolvedMinGapPx) {
        continue;
      }
      let neededPx = resolvedMinGapPx - currentGap;
      const maxReduciblePx = Math.max(0, current.width - 3);
      const reducePx = Math.min(maxReduciblePx, neededPx);
      if (reducePx > 0) {
        current.width = roundToTwo(current.width - reducePx);
        current.labelX = roundToTwo(current.x + 4);
        neededPx = roundToTwo(neededPx - reducePx);
      }
      if (neededPx <= 0) {
        continue;
      }
      for (let shiftIndex = cursor + 1; shiftIndex < indices.length; shiftIndex += 1) {
        const shifted = adjusted[indices[shiftIndex]];
        shifted.x = roundToTwo(shifted.x + neededPx);
        shifted.labelX = roundToTwo(shifted.x + 4);
      }
    }
  });

  return adjusted;
}
