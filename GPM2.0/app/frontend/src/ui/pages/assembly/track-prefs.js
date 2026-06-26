export const VIEW_SPAN_KB_OPTIONS = Object.freeze([500, 5000]);
export const TICK_LENGTH_OPTIONS = Object.freeze([10000, 100000]);
export const MIN_TICK_UNIT_KB_OPTIONS = Object.freeze([250, 500, 750, 1000, 10000, 100000]);
export const MAX_TICK_COUNT_OPTIONS = Object.freeze([5, 10, 15, 20]);
export const ALIGNMENT_LENGTH_OPTIONS = Object.freeze([1000, 10000, 100000]);
export const MAPQ_OPTIONS = Object.freeze([0, 30, 60, 90]);
export const SUPPORT_DS_CTG_LEN_BP_OPTIONS = Object.freeze([0, 1000, 10000, 100000]);

export const DEFAULT_VIEW_SPAN_KB = VIEW_SPAN_KB_OPTIONS[0];
export const DEFAULT_TICK_LENGTH = TICK_LENGTH_OPTIONS[0];
export const DEFAULT_MIN_TICK_UNIT_KB = 10000;
export const DEFAULT_MAX_TICK_COUNT = MAX_TICK_COUNT_OPTIONS[1];
export const DEFAULT_ALIGNMENT_LENGTH = ALIGNMENT_LENGTH_OPTIONS[1];
export const DEFAULT_MAPQ = MAPQ_OPTIONS[0];
export const DEFAULT_SUPPORT_DS_CTG_LEN_BP = SUPPORT_DS_CTG_LEN_BP_OPTIONS[0];
export const TRACK_PREF_OPTIONS = Object.freeze({
  supportDsCtgLen: SUPPORT_DS_CTG_LEN_BP_OPTIONS,
  minTickUnitKb: MIN_TICK_UNIT_KB_OPTIONS,
  maxTickCount: MAX_TICK_COUNT_OPTIONS,
  alignmentLength: ALIGNMENT_LENGTH_OPTIONS,
  mapq: MAPQ_OPTIONS,
});

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
  const mapq = resolveAllowedTrackPref(
    trackView,
    ["mapq", "mapQ", "minMapq"],
    MAPQ_OPTIONS,
    DEFAULT_MAPQ,
    normalizeNonNegativeInt,
  );
  const resolvedMapq = resolveNonNegativeTrackPref(trackView, ["mapq", "mapQ", "minMapq"], mapq);
  const supportDsCtgLen = resolveNonNegativeTrackPref(
    trackView,
    ["supportDsCtgLen", "supportDsCtgLenBp"],
    DEFAULT_SUPPORT_DS_CTG_LEN_BP,
  );

  return {
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
    mapq: resolvedMapq,
  };
}

export function resolveTickBpFromScale({
  domainSpanBp,
  minTickUnitKb,
  maxTickCount,
  fallbackTickBp = DEFAULT_TICK_LENGTH,
}) {
  const fallback = normalizePositiveInt(fallbackTickBp) ?? DEFAULT_TICK_LENGTH;
  const resolvedMinTickUnitKb = normalizePositiveInt(minTickUnitKb) ?? DEFAULT_MIN_TICK_UNIT_KB;
  if (normalizePositiveInt(domainSpanBp) === null || normalizePositiveInt(maxTickCount) === null) {
    return fallback;
  }
  return resolvedMinTickUnitKb * 1000;
}

export function resolveTrackInnerWidthFromScale({
  domainSpanBp,
  minTickUnitKb,
  maxTickCount,
  baseViewportPx = 1200,
  fallbackInnerWidth = baseViewportPx,
}) {
  const spanBp = normalizePositiveInt(domainSpanBp);
  const viewportPx = Math.max(1, normalizePositiveInt(baseViewportPx) ?? 1200);
  const fallback = Math.max(viewportPx, normalizePositiveInt(fallbackInnerWidth) ?? viewportPx);
  const resolvedMinTickUnitKb = normalizePositiveInt(minTickUnitKb) ?? DEFAULT_MIN_TICK_UNIT_KB;
  const resolvedMaxTickCount = normalizePositiveInt(maxTickCount) ?? DEFAULT_MAX_TICK_COUNT;
  if (spanBp === null) {
    return fallback;
  }
  const visibleSpanBp = Math.max(1, resolvedMinTickUnitKb * 1000 * resolvedMaxTickCount);
  return Math.max(viewportPx, Math.ceil((spanBp / visibleSpanBp) * viewportPx));
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
