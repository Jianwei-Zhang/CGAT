// One absolute scale for Canvas, SVG, drag previews and serialized SVGs.
// Missing evidence is not a measured zero; MAPQ is never a fallback.
export function readHitIdentityPct(hit) {
  const numeric = (value) => value === null || value === undefined || String(value).trim() === ""
    ? null : Number.isFinite(Number(value)) ? Number(value) : null;
  const explicit = numeric(hit?.identityPct ?? hit?.identity_pct);
  if (explicit !== null) return Math.max(0, Math.min(100, explicit));
  const matches = numeric(hit?.matchLength ?? hit?.match_length ?? hit?.matches);
  const length = numeric(hit?.blockLength ?? hit?.block_length ?? hit?.alignLength ?? hit?.align_length);
  return matches !== null && matches >= 0 && length !== null && length > 0
    ? Math.max(0, Math.min(100, matches * 100 / length)) : null;
}

export function resolveAlignmentBandStyle(tone, identityPct) {
  const identity = readHitIdentityPct({ identityPct });
  if (identity === null) return { fill: "rgb(222, 224, 227)", stroke: "rgb(194, 198, 204)" };
  const base = tone === "companion" ? [154, 126, 78] : [97, 129, 170];
  const strength = 0.18 + 0.82 * Math.max(0, Math.min(1, (identity - 80) / 20));
  const blend = (amount) => `rgb(${base.map((channel) => Math.round(255 + (channel - 255) * amount)).join(", ")})`;
  return { fill: blend(strength), stroke: blend(Math.min(1, strength + 0.1)) };
}

export function sortAlignmentBands(bands) {
  // Sort render records only, never source hits: hit keys and anchors stay stable.
  return [...bands].sort((left, right) =>
    (readHitIdentityPct(left) ?? -1) - (readHitIdentityPct(right) ?? -1));
}

export function alignmentBandSvgAttrs(band, tone = band?.tone) {
  const identity = readHitIdentityPct(band);
  const { fill, stroke } = resolveAlignmentBandStyle(tone, identity);
  // Attributes survive standalone SVG export; variables let Canvas proxies
  // become transparent and drag previews restore exactly the same colors.
  return `data-band-identity-pct="${identity ?? ""}" fill="${fill}" stroke="${stroke}" style="--alignment-band-fill:${fill};--alignment-band-stroke:${stroke}"`;
}

export function alignmentBandTooltipMetrics(hit) {
  const identity = readHitIdentityPct(hit);
  const length = Number(hit?.alignLength ?? hit?.blockLength);
  return `Identity: ${identity === null ? "Unknown" : `${identity.toFixed(2)}%`} | Alignment length: ${Number.isFinite(length) && length > 0 ? `${Math.round(length).toLocaleString("en-US")} bp` : "Unknown"}`;
}

export function renderAlignmentIdentityLegend(labels, escapeAttr) {
  const gradient = (tone) => `linear-gradient(to right, ${resolveAlignmentBandStyle(tone, 80).fill}, ${resolveAlignmentBandStyle(tone, 100).fill})`;
  const hint = labels?.identityLegendHint || "Darker means higher Identity. Fixed scale; ≤80% uses the lightest shade.";
  return `<div class="alignment-identity-legend" title="${escapeAttr(hint)}" aria-label="${escapeAttr(hint)}">
    <span>Identity</span><span>≤80%</span><span class="alignment-identity-scale" aria-hidden="true">
      <i style="background:${gradient("primary")}"></i><i style="background:${gradient("companion")}"></i>
    </span><span>100%</span>
  </div>`;
}
