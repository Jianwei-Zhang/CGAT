// Exact hits have already been split using CIGAR in the backend. Legacy hits
// retain only endpoints: clip their interval projection, never bridge ref gaps.
export function splitReferenceBandHit(hit, referenceMembers, reversed = false) {
  const refStart = Number(hit.refStart ?? hit.ref_start);
  const refEnd = Number(hit.refEnd ?? hit.ref_end);
  const ctgStart = Number(hit.ctgStart ?? hit.ctg_start);
  const ctgEnd = Number(hit.ctgEnd ?? hit.ctg_end);
  if (![refStart, refEnd, ctgStart, ctgEnd].every(Number.isFinite)
      || refEnd < refStart || ctgEnd < ctgStart) return [];
  if (!referenceMembers.length) return [hit];
  return referenceMembers.flatMap((member) => {
    const start = Math.max(refStart, Number(member.segmentStartBp));
    const end = Math.min(refEnd, Number(member.segmentEndBp));
    if (!Number.isFinite(start) || !Number.isFinite(end) || start > end) return [];
    if (start === refStart && end === refEnd) return [hit];
    const span = refEnd - refStart + 1;
    const left = (start - refStart) / span;
    const right = (end - refStart + 1) / span;
    const ctgSpan = ctgEnd - ctgStart + 1;
    const projectedStart = Math.min(ctgEnd, ctgStart + (reversed ? 1 - right : left) * ctgSpan);
    const projectedEnd = Math.max(projectedStart, ctgStart + (reversed ? 1 - left : right) * ctgSpan - 1);
    return [{
      ...hit,
      refStart: start,
      refEnd: end,
      ctgStart: projectedStart,
      ctgEnd: Math.min(ctgEnd, projectedEnd),
      referenceProjectionApproximate: true,
    }];
  });
}
