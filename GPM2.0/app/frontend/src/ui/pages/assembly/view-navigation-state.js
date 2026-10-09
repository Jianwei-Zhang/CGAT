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

export function formatViewSpan(bp, preferredUnit) {
  const unit = preferredUnit === "kb" || preferredUnit === "Mb" ? preferredUnit : bp >= 1_000_000 ? "Mb" : "kb";
  const value = Number(bp) / (unit === "Mb" ? 1_000_000 : 1000);
  return { unit, value: String(Number(value.toFixed(unit === "Mb" ? 6 : 3))) };
}

export function readViewNavigationGeometry(scrollEl, metrics) {
  if (!metrics || !scrollEl || scrollEl.dataset?.viewNavigationContent === "0") return null;
  const bpPerPx = metrics.domainSpanBp / metrics.innerWidth;
  const min = metrics.windowStartBp + metrics.viewboxMinX * bpPerPx;
  const width = Math.max(metrics.viewportWidth, Number(scrollEl.scrollWidth) || metrics.innerWidth);
  const domain = { start: min, end: min + width * bpPerPx, viewportWidth: metrics.viewportWidth };
  const range = clampViewRange({ start: min + (Number(scrollEl.scrollLeft) || 0) * bpPerPx, span: metrics.viewportWidth * bpPerPx }, domain);
  return range ? { domain, range, bpPerPx } : null;
}
