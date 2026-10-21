import { MAX_TRACK_RENDER_PX } from "./track-prefs.js";

export function clampViewRange({ start, span }, domain) {
  const min = Number(domain?.start), max = Number(domain?.end);
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return null;
  const minimum = Math.min(max - min, Math.max(1, (max - min) * Math.max(1, Number(domain.viewportWidth) || 1200) / MAX_TRACK_RENDER_PX));
  const width = Math.max(minimum, Math.min(max - min, Number(span) || max - min));
  const left = Math.max(min, Math.min(max - width, Number.isFinite(Number(start)) ? Number(start) : min));
  return { start: left, span: width };
}

export function zoomViewRange(range, domain, factor, anchorFraction = 0.5) {
  const current = clampViewRange(range, domain);
  if (!current || !Number.isFinite(factor) || factor <= 0) return current;
  const fraction = Math.max(0, Math.min(1, anchorFraction));
  const next = clampViewRange({ start: current.start, span: current.span * factor }, domain);
  return clampViewRange({ start: current.start + current.span * fraction - next.span * fraction, span: next.span }, domain);
}

export function moveViewRange(range, domain, deltaBp) {
  return clampViewRange({ start: range.start + deltaBp, span: range.span }, domain);
}

export function parseViewSpan(value, unit = "Mb") {
  const text = String(value ?? "").trim();
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text)) return null;
  const multiplier = unit === "kb" ? 1000 : unit === "Mb" ? 1_000_000 : null;
  const bp = Math.round(Number(text) * multiplier);
  return multiplier && Number.isSafeInteger(bp) && bp > 0 ? bp : null;
}

const VIEW_SPAN_UNITS = ["bp", "kb", "Mb", "Gb", "Tb", "Pb"];

export function formatViewSpan(bp) {
  let unitIndex = 0;
  while (unitIndex < VIEW_SPAN_UNITS.length - 1 && bp >= 1000 ** (unitIndex + 1)) unitIndex++;
  let value = Number((Number(bp) / 1000 ** unitIndex).toFixed(unitIndex === 0 ? 0 : 2));
  // Rounding near a unit boundary must not leave a wider "1000" label.
  if (value >= 1000 && unitIndex < VIEW_SPAN_UNITS.length - 1) {
    value = Number((value / 1000).toFixed(2));
    unitIndex++;
  }
  return { unit: VIEW_SPAN_UNITS[unitIndex], value: String(value) };
}

export function readViewNavigationGeometry(scrollEl, metrics) {
  if (!metrics || !scrollEl || scrollEl.dataset?.viewNavigationContent === "0") return null;
  const bpPerPx = metrics.domainSpanBp / metrics.innerWidth;
  const min = metrics.windowStartBp + metrics.viewboxMinX * bpPerPx;
  const width = Math.max(metrics.viewportWidth, Number(scrollEl.scrollWidth) || metrics.innerWidth);
  // A fitted SVG may be narrower than its viewport. scrollWidth then includes
  // empty viewport padding, which must not become a historical content bound.
  const contentStart = Number(scrollEl.dataset?.viewNavigationStartBp);
  const contentEnd = Number(scrollEl.dataset?.viewNavigationEndBp);
  const hasContentBounds = Number.isFinite(contentStart) && Number.isFinite(contentEnd) && contentEnd > contentStart;
  const domain = {
    start: hasContentBounds ? contentStart : min,
    end: hasContentBounds ? contentEnd : min + width * bpPerPx,
    viewportWidth: metrics.viewportWidth,
  };
  const range = clampViewRange({ start: min + (Number(scrollEl.scrollLeft) || 0) * bpPerPx, span: metrics.viewportWidth * bpPerPx }, domain);
  return range ? { domain, range, bpPerPx } : null;
}

// Refit from current marks plus reference/ruler bounds, never from scrollWidth
// or a remembered maximum. The same calculation handles either side.
export function resolveFullRangeVisibleSpan({ contentWidth, innerWidth, domainSpanBp, viewportWidth }) {
  if (![contentWidth, innerWidth, domainSpanBp, viewportWidth].every((value) => Number.isFinite(value) && value > 0)) return null;
  if (contentWidth <= viewportWidth && viewportWidth - contentWidth <= 1) return null;
  return Math.max(1, Math.ceil(contentWidth * domainSpanBp / innerWidth));
}
