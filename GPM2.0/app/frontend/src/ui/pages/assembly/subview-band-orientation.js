import { resolveTrackCtgOrient } from "./track-label-geometry.js";

// Reference hits retain raw source strand, but their query coordinates have
// already been projected into the displayed CTG orientation.
export function resolveReferenceHitDisplayReversed(ctg, hit) {
  const strand = String(hit?.strand || "").trim();
  return (strand === "+" || strand === "-") && resolveTrackCtgOrient(ctg) !== strand;
}

export function resolveSubviewSegmentPairReversed(top, bottom) {
  // Independent reference-relative endpoints compose by XOR. Direct pairwise
  // evidence instead repeats the SAME pair-level flag on both endpoints.
  if (typeof top?.referenceReversed === "boolean" || typeof bottom?.referenceReversed === "boolean") {
    return (top?.referenceReversed === true) !== (bottom?.referenceReversed === true);
  }
  return top?.reversed === true || bottom?.reversed === true;
}
