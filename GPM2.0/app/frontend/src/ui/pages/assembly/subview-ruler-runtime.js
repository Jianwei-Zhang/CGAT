const SUBVIEW_RULER_BOUND = Symbol("subviewRulerBound");
const DEFAULT_VIEWPORT_WIDTH_PX = 1200;
const RULER_OVERSCAN_TICKS = 2;
const MAX_VISIBLE_RULER_TICKS = 256;

function readFiniteNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function readRulerNumber(layer, key, fallback = 0) {
  const value = layer?.dataset?.[key];
  return readFiniteNumber(value, fallback);
}

function formatRulerTickLabel(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  if (numeric >= 1_000_000 && numeric % 1_000_000 === 0) {
    return `${(numeric / 1_000_000).toLocaleString("en-US")}M`;
  }
  if (numeric >= 1_000) {
    const kbValue = Math.round((numeric / 1_000) * 10) / 10;
    return `${kbValue.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 1 })}k`;
  }
  return numeric.toLocaleString("en-US");
}

function formatRulerEndLabel(value) {
  return `${Number(value || 0).toLocaleString("en-US")} bp`;
}

function resolveRulerLabelBounds(tick) {
  const width = Math.max(12, String(tick?.labelText || "").length * 7);
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

function resolveVisibleRulerRange({
  windowStart,
  windowEnd,
  tickBp,
  innerWidth,
  domainSpanBp,
  viewportLeft,
  viewportWidth,
  viewBoxMinX,
}) {
  const safeStart = Math.min(windowStart, windowEnd);
  const safeEnd = Math.max(windowStart, windowEnd);
  const safeWidth = Math.max(1, innerWidth);
  const safeSpan = Math.max(1, domainSpanBp);
  const pixelsPerBp = safeWidth / safeSpan;
  const tickSpacingPx = Math.max(1, tickBp * pixelsPerBp);
  const overscanPx = Math.max(tickSpacingPx * RULER_OVERSCAN_TICKS, 24);
  const contentLeft = readFiniteNumber(viewportLeft, 0) + readFiniteNumber(viewBoxMinX, 0);
  const contentWidth = Math.max(1, readFiniteNumber(viewportWidth, DEFAULT_VIEWPORT_WIDTH_PX));
  const contentRight = contentLeft + contentWidth;
  const xToBp = (x) => safeStart + (x / safeWidth) * safeSpan;
  return {
    minBp: Math.max(safeStart, xToBp(contentLeft - overscanPx)),
    maxBp: Math.min(safeEnd, xToBp(contentRight + overscanPx)),
    firstTick: Math.max(0, Math.ceil(Math.max(0, safeStart) / tickBp) * tickBp),
    safeStart,
    safeEnd,
  };
}

export function buildVisibleSubviewRulerTicks(options = {}) {
  const windowStart = readFiniteNumber(options.windowStart, 0);
  const windowEnd = Math.max(windowStart, readFiniteNumber(options.windowEnd, windowStart));
  const tickBp = Math.max(1, readFiniteNumber(options.tickBp, 1));
  const innerWidth = Math.max(1, readFiniteNumber(options.innerWidth, 1));
  const domainSpanBp = Math.max(1, readFiniteNumber(options.domainSpanBp, windowEnd - windowStart));
  const range = resolveVisibleRulerRange({
    windowStart,
    windowEnd,
    tickBp,
    innerWidth,
    domainSpanBp,
    viewportLeft: options.viewportLeft,
    viewportWidth: options.viewportWidth,
    viewBoxMinX: options.viewBoxMinX,
  });
  const firstIndex = Math.max(
    0,
    Math.floor((range.minBp - range.firstTick) / tickBp) - RULER_OVERSCAN_TICKS,
  );
  const lastIndex = Math.max(
    firstIndex,
    Math.ceil((range.maxBp - range.firstTick) / tickBp) + RULER_OVERSCAN_TICKS,
  );
  const maxRegularIndex = Math.max(0, Math.floor((range.safeEnd - range.firstTick) / tickBp));
  const boundedLastIndex = Math.min(maxRegularIndex, lastIndex);
  const regularCount = Math.max(0, boundedLastIndex - firstIndex + 1);
  const indexStep = Math.max(1, Math.ceil(regularCount / MAX_VISIBLE_RULER_TICKS));
  const ticks = [];
  for (let index = firstIndex; index <= boundedLastIndex; index += indexStep) {
    const bp = range.firstTick + index * tickBp;
    const x = ((bp - windowStart) / domainSpanBp) * innerWidth;
    ticks.push({ bp, x });
  }
  const endX = ((windowEnd - windowStart) / domainSpanBp) * innerWidth;
  if (
    ticks.length === 0
    || Number(ticks[ticks.length - 1].bp) !== Number(windowEnd)
  ) {
    const visibleEnd = endX >= ((options.viewportLeft || 0) + (options.viewBoxMinX || 0) - 24)
      && endX <= ((options.viewportLeft || 0) + (options.viewBoxMinX || 0) + (options.viewportWidth || DEFAULT_VIEWPORT_WIDTH_PX) + 24);
    if (visibleEnd) {
      ticks.push({ bp: windowEnd, x: endX });
    }
  }
  const sortedTicks = Array.from(
    new Map(ticks.map((tick) => [Number(tick.bp), tick])).values(),
  ).sort((left, right) => left.bp - right.bp);
  return sortedTicks.map((tick, index) => {
    const isFirst = index === 0;
    const isLast = Number(tick.bp) === Number(windowEnd);
    const isSingle = isFirst && isLast;
    const labelAnchor = isSingle ? "middle" : isFirst ? "start" : isLast ? "end" : "middle";
    const edgePadding = Math.max(0, readFiniteNumber(options.edgeLabelPadding, 16));
    const labelX = isSingle
      ? tick.x
      : isFirst
        ? Math.min(innerWidth, tick.x + edgePadding)
        : isLast
          ? Math.max(0, tick.x - edgePadding)
          : tick.x;
    return {
      ...tick,
      labelAnchor,
      labelX,
      labelText: isLast ? formatRulerEndLabel(tick.bp) : formatRulerTickLabel(tick.bp),
      showLabel: true,
    };
  }).map((tick, index, allTicks) => {
    if (index < allTicks.length - 1 && Number(allTicks[index + 1].bp) === Number(windowEnd)) {
      const previousBounds = resolveRulerLabelBounds(tick);
      const endBounds = resolveRulerLabelBounds(allTicks[index + 1]);
      if (previousBounds.right > endBounds.left) {
        return { ...tick, showLabel: false };
      }
    }
    return tick;
  });
}

export function buildVisibleSubviewRulerMarkup(options = {}) {
  return buildVisibleSubviewRulerTicks(options)
    .map((tick) => `<line class="track-tick-guide is-major" x1="${tick.x.toFixed(2)}" y1="${Number(options.tickY1 || 0).toFixed(2)}" x2="${tick.x.toFixed(2)}" y2="${Number(options.tickY2 || 0).toFixed(2)}" />${tick.showLabel ? `<text class="track-tick-label" x="${tick.labelX.toFixed(2)}" y="${Number(options.tickLabelY || 0).toFixed(2)}" text-anchor="${tick.labelAnchor}">${tick.labelText}</text>` : ""}`)
    .join("");
}

function readRulerOptions(layer, scrollNode) {
  return {
    windowStart: readRulerNumber(layer, "subviewRulerWindowStart"),
    windowEnd: readRulerNumber(layer, "subviewRulerWindowEnd"),
    tickBp: Math.max(1, readRulerNumber(layer, "subviewRulerTickBp", 1)),
    innerWidth: Math.max(1, readRulerNumber(layer, "subviewRulerInnerWidth", 1)),
    domainSpanBp: Math.max(1, readRulerNumber(layer, "subviewRulerDomainSpanBp", 1)),
    edgeLabelPadding: readRulerNumber(layer, "subviewRulerEdgeLabelPadding", 16),
    tickY1: readRulerNumber(layer, "subviewRulerTickY1"),
    tickY2: readRulerNumber(layer, "subviewRulerTickY2"),
    tickLabelY: readRulerNumber(layer, "subviewRulerTickLabelY"),
    viewBoxMinX: readFiniteNumber(scrollNode?.dataset?.subviewViewboxMinX, 0),
    viewportLeft: readFiniteNumber(scrollNode?.scrollLeft, 0),
    viewportWidth: Math.max(1, readFiniteNumber(scrollNode?.clientWidth, DEFAULT_VIEWPORT_WIDTH_PX)),
  };
}

function updateSubviewRuler(layer, scrollNode) {
  if (!layer) {
    return;
  }
  const nextMarkup = buildVisibleSubviewRulerMarkup(readRulerOptions(layer, scrollNode));
  if (layer.innerHTML !== nextMarkup) {
    layer.innerHTML = nextMarkup;
  }
}

function resolveAnimationFrameApi() {
  const request = typeof globalThis.requestAnimationFrame === "function"
    ? globalThis.requestAnimationFrame.bind(globalThis)
    : (callback) => globalThis.setTimeout(() => callback(Date.now()), 16);
  const cancel = typeof globalThis.cancelAnimationFrame === "function"
    ? globalThis.cancelAnimationFrame.bind(globalThis)
    : (handle) => globalThis.clearTimeout(handle);
  return { request, cancel };
}

export function bindSubviewRulerRuntime(host) {
  const { request, cancel } = resolveAnimationFrameApi();
  const scrollNodes = host?.querySelectorAll?.(".subview-track-scroll") || [];
  Array.from(scrollNodes).forEach((scrollNode) => {
    const layer = scrollNode?.querySelector?.("[data-subview-virtual-ruler='1']");
    if (!layer) {
      return;
    }
    const previous = layer[SUBVIEW_RULER_BOUND] || null;
    if (!previous) {
      const onScroll = () => {
        const current = layer[SUBVIEW_RULER_BOUND];
        if (!current || current.frameHandle !== undefined) {
          return;
        }
        const frameHandle = request(() => {
          updateSubviewRuler(layer, scrollNode);
          const latest = layer[SUBVIEW_RULER_BOUND];
          if (latest) {
            layer[SUBVIEW_RULER_BOUND] = { ...latest, frameHandle: undefined };
          }
        });
        layer[SUBVIEW_RULER_BOUND] = { onScroll, frameHandle };
      };
      scrollNode.addEventListener?.("scroll", onScroll);
      layer[SUBVIEW_RULER_BOUND] = { onScroll, frameHandle: undefined };
    }
    updateSubviewRuler(layer, scrollNode);
  });
  return () => {
    Array.from(scrollNodes).forEach((scrollNode) => {
      const layer = scrollNode?.querySelector?.("[data-subview-virtual-ruler='1']");
      const state = layer?.[SUBVIEW_RULER_BOUND];
      if (state?.frameHandle !== undefined) {
        cancel(state.frameHandle);
      }
    });
  };
}
