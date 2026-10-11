import { resolveTrackPrefs } from "./track-prefs.js";

// Removing content is not a fit-to-content request. Capture the rendered scale
// before hiding anything, including the extra display space used by overview.
export function preserveSubviewRemovalViewport(assembly, host, {
  viewport,
  viewportWidthPx = 1_200,
} = {}) {
  const scroll = host?.querySelector?.(".subview-track-scroll");
  const width = Number(scroll?.clientWidth || viewportWidthPx);
  const span = Number(scroll?.dataset?.subviewDomainSpanBp);
  const innerWidth = Number(scroll?.dataset?.subviewInnerWidth);
  const savedScale = Number(viewport?.bpPerPx);
  const bpPerPx = Number.isFinite(savedScale) && savedScale > 0 ? savedScale
    : Number.isFinite(span) && span > 0 && Number.isFinite(innerWidth) && innerWidth > 0
      ? span / innerWidth : null;
  const prefs = resolveTrackPrefs(assembly?.subviewTrackView);
  return {
    ...assembly,
    subviewTrackView: {
      ...assembly?.subviewTrackView,
      fullRange: false,
      allowSubViewportScale: true,
      visibleSpanBp: bpPerPx > 0 && Number.isFinite(width) && width > 0
        ? Math.max(1, Math.round(bpPerPx * width)) : prefs.visibleSpanBp,
    },
  };
}

export function normalizeSubviewTrackPairLayoutViewport(value) {
  if (!value || typeof value !== "object") return null;
  const keys = ["windowStartBp", "domainSpanBp", "innerWidth", "viewportWidthPx",
    "visibleSpanBp", "viewboxMinX", "renderInnerWidth"];
  const viewport = Object.fromEntries(keys.map((key) => [key, Number(value[key])]));
  if (!Object.values(viewport).every(Number.isFinite)
    || ["domainSpanBp", "innerWidth", "viewportWidthPx", "visibleSpanBp", "renderInnerWidth"]
      .some((key) => viewport[key] <= 0)) return null;
  return viewport;
}

export function captureSubviewTrackPairRemovalLayout(assembly, host) {
  const savedGap = assembly?.subview?.trackPairLayoutGapBp;
  const hasSavedGap = typeof savedGap === "number" && Number.isFinite(savedGap) && savedGap >= 0;
  const scroll = host?.querySelector?.(".subview-track-scroll");
  const span = Number(scroll?.dataset?.subviewDomainSpanBp);
  const innerWidth = Number(scroll?.dataset?.subviewInnerWidth);
  const viewportWidth = Number(scroll?.clientWidth);
  if (!(span > 0 && innerWidth > 0 && viewportWidth > 0)) {
    return hasSavedGap ? { trackPairLayoutGapBp: savedGap } : {};
  }
  const gapPx = 20 * (assembly?.subviewTrackView?.fullRange
    ? Math.min(1, innerWidth / viewportWidth) : 1);
  const viewport = normalizeSubviewTrackPairLayoutViewport({
    windowStartBp: Number(scroll.dataset.subviewWindowStartBp || 0),
    domainSpanBp: span,
    innerWidth,
    viewportWidthPx: viewportWidth,
    visibleSpanBp: Math.max(1, Math.round(span / innerWidth * viewportWidth)),
    viewboxMinX: Number(scroll.dataset.subviewViewboxMinX || 0),
    renderInnerWidth: Number(scroll.scrollWidth) || Math.max(innerWidth, viewportWidth),
  });
  return {
    trackPairLayoutGapBp: hasSavedGap ? savedGap : gapPx * span / innerWidth,
    ...(viewport ? { trackPairLayoutViewport: viewport } : {}),
  };
}
