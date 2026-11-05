import { readHitIdentityPct } from "./alignment-band-style.js";
import { formatBpIntervalEnUs, formatIntegerEnUs } from "./number-format.js";

const finiteNumber = (value) => {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

// Keep only the small, stable values needed by the tooltip. Dense Local View
// stores these beside the Canvas band and formats the text only on hover.
export function buildSubviewBandTooltipData({
  topName,
  bottomName,
  topSegment,
  bottomSegment,
  isDirectAlignment,
}) {
  const identity = readHitIdentityPct(topSegment);
  const alignLength = finiteNumber(topSegment?.alignLength ?? topSegment?.blockLength);
  return {
    t: String(topName || "Top"),
    b: String(bottomName || "Bottom"),
    ts: finiteNumber(topSegment?.ctgStart),
    te: finiteNumber(topSegment?.ctgEnd),
    bs: finiteNumber(bottomSegment?.ctgStart),
    be: finiteNumber(bottomSegment?.ctgEnd),
    i: identity,
    l: alignLength !== null && alignLength > 0 ? alignLength : null,
    d: isDirectAlignment === true ? 1 : 0,
    a: topSegment?.projectionApproximate || bottomSegment?.projectionApproximate ? 1 : 0,
  };
}

export function formatSubviewBandTooltipText(data) {
  const identity = finiteNumber(data?.i);
  const alignLength = finiteNumber(data?.l);
  return [
    `${String(data?.t || "Top")}: ${formatBpIntervalEnUs(data?.ts, data?.te)}`,
    `${String(data?.b || "Bottom")}: ${formatBpIntervalEnUs(data?.bs, data?.be)}`,
    Number(data?.d) === 1
      ? `Identity: ${identity === null ? "Unknown" : `${identity.toFixed(2)}%`} | Alignment length: ${alignLength !== null && alignLength > 0 ? `${formatIntegerEnUs(Math.round(alignLength))} bp` : "Unknown"}`
      : "Identity: Unknown (reference overlap; not a direct alignment)",
    Number(data?.a) === 1 ? "Approximate projection" : "",
  ].filter(Boolean).join(" | ");
}
