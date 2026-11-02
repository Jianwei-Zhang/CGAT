import { deferReferenceMember, iterateReferenceHits } from "./reference-evidence.js";

// Explicit deferral is used by Assembly; ordinary API callers still receive
// the same full hit arrays, and both previous desktop encodings remain valid.
export function decodeReferenceTracks(result, { deferHits = false } = {}) {
  if (!result?.encoding) return { items: result?.items || [] };
  if (!["reference-hits-v1", "reference-hits-v2"].includes(result.encoding)) {
    throw Error("Unsupported reference evidence encoding");
  }
  if (!deferHits && result.encoding === "reference-hits-v1") {
    // Keep the established eager API fast path for callers that explicitly
    // request full arrays; deferred Assembly never enters this branch.
    return { items: (result.items || []).map(({ hitGroups, hitRows, ...member }) => ({
      ...member, hits: hitRows.map(([group, queryStart, queryEnd, refStart, refEnd,
        matchLength, blockLength, ctgStart, ctgEnd]) => {
        const [hitId, datasetId, sourceSeqId, strand, identityPct, mapq] = hitGroups[group];
        return { hitId, datasetId, sourceSeqId, strand, queryStart, queryEnd,
          refStart, refEnd, matchLength, blockLength, identityPct, mapq, ctgStart, ctgEnd };
      }),
    })) };
  }
  return { items: (result.items || []).map(member => {
    const deferred = deferReferenceMember(member, result.encoding);
    if (deferHits) return deferred;
    const { referenceEvidence, ...metadata } = deferred;
    return { ...metadata, hits: Array.from(iterateReferenceHits(deferred)) };
  }) };
}
