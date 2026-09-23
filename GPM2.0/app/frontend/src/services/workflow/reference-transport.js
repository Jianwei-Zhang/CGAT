// Expand the desktop IPC representation once; all callers retain the usual hit objects.
export function decodeReferenceTracks(result) {
  if (result?.encoding !== "reference-hits-v1") return { items: result?.items || [] };
  return {
    items: (result.items || []).map(({ hitGroups, hitRows, ...member }) => ({
      ...member,
      hits: hitRows.map(([group, queryStart, queryEnd, refStart, refEnd,
        matchLength, blockLength, ctgStart, ctgEnd]) => {
        const [hitId, datasetId, sourceSeqId, strand, identityPct, mapq] = hitGroups[group];
        return { hitId, datasetId, sourceSeqId, strand, queryStart, queryEnd,
          refStart, refEnd, matchLength, blockLength, identityPct, mapq, ctgStart, ctgEnd };
      }),
    })),
  };
}
