export const VIEW_SPAN_KB_OPTIONS = Object.freeze([500, 5000]);
export const TICK_LENGTH_OPTIONS = Object.freeze([10000, 100000]);
export const MIN_TICK_UNIT_KB_OPTIONS = Object.freeze([250, 500, 750, 1000, 10000, 100000]);
export const MAX_TICK_COUNT_OPTIONS = Object.freeze([5, 10, 15, 20]);
export const ALIGNMENT_LENGTH_OPTIONS = Object.freeze([1000, 10000, 100000]);
export const IDENTITY_PCT_OPTIONS = Object.freeze([0, 85, 90, 95]);
export const SUPPORT_DS_CTG_LEN_BP_OPTIONS = Object.freeze([0, 1000, 10000, 100000]);

export const DEFAULT_VIEW_SPAN_KB = VIEW_SPAN_KB_OPTIONS[0];
export const DEFAULT_TICK_LENGTH = TICK_LENGTH_OPTIONS[0];
export const DEFAULT_MIN_TICK_UNIT_KB = 10000;
export const DEFAULT_MAX_TICK_COUNT = MAX_TICK_COUNT_OPTIONS[1];
export const DEFAULT_ALIGNMENT_LENGTH = ALIGNMENT_LENGTH_OPTIONS[1];
export const DEFAULT_MIN_IDENTITY_PCT = IDENTITY_PCT_OPTIONS[0];
export const DEFAULT_SUPPORT_DS_CTG_LEN_BP = SUPPORT_DS_CTG_LEN_BP_OPTIONS[0];
// Bound full SVG dimensions independently of biological sequence length.
export const MAX_TRACK_RENDER_PX = 4_000_000;
export const TRACK_PREF_OPTIONS = Object.freeze({
  supportDsCtgLen: SUPPORT_DS_CTG_LEN_BP_OPTIONS,
  minTickUnitKb: MIN_TICK_UNIT_KB_OPTIONS,
  maxTickCount: MAX_TICK_COUNT_OPTIONS,
  alignmentLength: ALIGNMENT_LENGTH_OPTIONS,
  minIdentityPct: IDENTITY_PCT_OPTIONS,
});

// Manual input is stricter than legacy persisted preference normalization.
export function normalizeTrackPrefInputValue(field, rawValue) {
  const text = String(rawValue ?? "");
  if (!/^[0-9]+$/.test(text)) return null;
  const value = Number(text);
  const minimum = field === "minIdentityPct" || field === "supportDsCtgLen" ? 0 : 1;
  const maximum = field === "minIdentityPct" ? 100 : Number.MAX_SAFE_INTEGER;
  return Number.isSafeInteger(value) && value >= minimum && value <= maximum ? value : null;
}

export function resolveTrackPrefs(trackView) {
  const minTickUnitKb = resolvePositiveTrackPref(
    trackView,
    ["minTickUnitKb", "minTickKb"],
    DEFAULT_MIN_TICK_UNIT_KB,
  );
  const maxTickCount = resolvePositiveTrackPref(
    trackView,
    ["maxTickCount"],
    DEFAULT_MAX_TICK_COUNT,
  );
  const viewSpanKb = resolveAllowedTrackPref(
    trackView,
    ["viewSpanKb", "pixelUnit"],
    VIEW_SPAN_KB_OPTIONS,
    DEFAULT_VIEW_SPAN_KB,
  );
  const hasLegacyTick = hasAnyTrackPref(trackView, ["tickLength", "tickBp"]);
  const tickLength = hasLegacyTick
    ? resolveAllowedTrackPref(trackView, ["tickLength", "tickBp"], TICK_LENGTH_OPTIONS, DEFAULT_TICK_LENGTH)
    : DEFAULT_TICK_LENGTH;
  const alignmentLength = resolvePositiveTrackPref(
    trackView,
    ["alignmentLength", "block_length"],
    DEFAULT_ALIGNMENT_LENGTH,
  );
  const minIdentityPct = resolveAllowedTrackPref(
    trackView,
    ["minIdentityPct", "identityPct"],
    IDENTITY_PCT_OPTIONS,
    DEFAULT_MIN_IDENTITY_PCT,
    normalizeNonNegativeInt,
  );
  const resolvedMinIdentityPct = Math.min(
    100,
    resolveNonNegativeTrackPref(
      trackView,
      ["minIdentityPct", "identityPct"],
      minIdentityPct,
    ),
  );
  const supportDsCtgLen = resolveNonNegativeTrackPref(
    trackView,
    ["supportDsCtgLen", "supportDsCtgLenBp"],
    DEFAULT_SUPPORT_DS_CTG_LEN_BP,
  );

  return {
    // Legacy fields remain readable for compatibility, but are not the live scale model.
    visibleSpanBp: normalizePositiveInt(trackView?.visibleSpanBp)
      ?? Math.min(Number.MAX_SAFE_INTEGER, minTickUnitKb * 1000 * maxTickCount),
    tickMode: trackView?.tickMode === "manual" ? "manual" : "auto",
    tickIntervalBp: normalizePositiveInt(trackView?.tickIntervalBp) ?? minTickUnitKb * 1000,
    showTelomeres: trackView?.showTelomeres !== false,
    showCentromeres: trackView?.showCentromeres !== false,
    supportDsCtgLen,
    supportDsCtgLenBp: supportDsCtgLen,
    minTickUnitKb,
    minTickKb: minTickUnitKb,
    maxTickCount,
    viewSpanKb,
    pixelUnit: minTickUnitKb,
    tickLength,
    tickBp: tickLength,
    alignmentLength,
    block_length: alignmentLength,
    minIdentityPct: resolvedMinIdentityPct,
  };
}

export function resolveTickBpFromScale({
  domainSpanBp, minTickUnitKb, maxTickCount, fallbackTickBp = DEFAULT_TICK_LENGTH,
  tickMode, tickIntervalBp, visibleSpanBp, baseViewportPx = 1200,
}) {
  // Calls without the new ruler contract retain their legacy behavior.
  if (tickMode === undefined) {
    if (normalizePositiveInt(domainSpanBp) === null || normalizePositiveInt(maxTickCount) === null) {
      return normalizePositiveInt(fallbackTickBp) ?? DEFAULT_TICK_LENGTH;
    }
    return (normalizePositiveInt(minTickUnitKb) ?? DEFAULT_MIN_TICK_UNIT_KB) * 1000;
  }
  if (tickMode === "manual") return normalizePositiveInt(tickIntervalBp) ?? 10_000;
  const span = Math.min(normalizePositiveInt(domainSpanBp) ?? 1,
    normalizePositiveInt(visibleSpanBp) ?? normalizePositiveInt(domainSpanBp) ?? 1);
  const count = Math.max(2, Math.floor((Number(baseViewportPx) || 1200) / 110));
  const raw = Math.max(1, span / count);
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].find((value) => value * power >= raw) ?? 10;
  return Math.max(1, Math.ceil(step * power));
}

export function resolveTrackInnerWidthFromScale({
  domainSpanBp, minTickUnitKb, maxTickCount, visibleSpanBp,
  baseViewportPx = 1200, fallbackInnerWidth = baseViewportPx,
}) {
  const spanBp = normalizePositiveInt(domainSpanBp);
  const viewportPx = Math.max(1, normalizePositiveInt(baseViewportPx) ?? 1200);
  const fallback = Math.max(viewportPx, normalizePositiveInt(fallbackInnerWidth) ?? viewportPx);
  if (spanBp === null) return fallback;
  const requestedSpan = normalizePositiveInt(visibleSpanBp)
    ?? (normalizePositiveInt(minTickUnitKb) ?? DEFAULT_MIN_TICK_UNIT_KB) * 1000
      * (normalizePositiveInt(maxTickCount) ?? DEFAULT_MAX_TICK_COUNT);
  // Short content always fills the plot, including when restoring legacy settings.
  const lowerWidth = viewportPx;
  return Math.min(MAX_TRACK_RENDER_PX,
    Math.max(lowerWidth, Math.ceil(spanBp / requestedSpan * viewportPx)));
}

export function normalizeAllowedOption(value, allowedOptions, defaultValue) {
  const parsed = normalizePositiveInt(value);
  if (parsed === null) {
    return defaultValue;
  }
  return resolveNearestAllowedOption(parsed, allowedOptions);
}

export function normalizeNonNegativeInt(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return Math.trunc(parsed);
}

function resolveNearestAllowedOption(parsed, allowedOptions) {
  let bestValue = allowedOptions[0];
  let bestDistance = Math.abs(parsed - bestValue);
  for (let index = 1; index < allowedOptions.length; index += 1) {
    const candidate = allowedOptions[index];
    const candidateDistance = Math.abs(parsed - candidate);
    if (candidateDistance < bestDistance) {
      bestValue = candidate;
      bestDistance = candidateDistance;
    }
  }
  return bestValue;
}

export const normalizeToAllowedOption = normalizeAllowedOption;

export function normalizePositiveInt(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.max(1, Math.trunc(parsed));
}

function resolveAllowedTrackPref(
  trackView,
  keys,
  allowedOptions,
  defaultValue,
  normalizeValue = normalizePositiveInt,
) {
  for (const key of keys) {
    const normalized = normalizeValue(trackView?.[key]);
    if (normalized !== null) {
      return resolveNearestAllowedOption(normalized, allowedOptions);
    }
  }
  return defaultValue;
}

function resolvePositiveTrackPref(trackView, keys, defaultValue) {
  for (const key of keys) {
    const normalized = normalizePositiveInt(trackView?.[key]);
    if (normalized !== null) {
      return normalized;
    }
  }
  return defaultValue;
}

function resolveNonNegativeTrackPref(trackView, keys, defaultValue) {
  for (const key of keys) {
    const normalized = normalizeNonNegativeInt(trackView?.[key]);
    if (normalized !== null) {
      return normalized;
    }
  }
  return defaultValue;
}

function hasAnyTrackPref(trackView, keys) {
  return keys.some((key) => normalizePositiveInt(trackView?.[key]) !== null);
}
