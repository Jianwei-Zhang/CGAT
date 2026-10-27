const positive = value => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
const text = value => String(value || "").trim();

// Inclusive biological source coordinates, independent of reference placement,
// screen geometry, Final Path cumulative positions and editing selections.
export function buildSourceIntervalProjection(ctg, orient = "+") {
  const reference = ctg?.reference;
  const referenceChrName = text(reference?.chrName || (ctg?.sourceKind === "ref_segment" && ctg?.referenceChrName));
  if (referenceChrName) {
    const sourceStart = positive(reference?.startBp ?? ctg?.segmentStartBp);
    const sourceEnd = positive(reference?.endBp ?? ctg?.segmentEndBp);
    return sourceStart && sourceEnd >= sourceStart
      ? { referenceChrName, sourceStart, sourceEnd, orient } : null;
  }
  const fragment = ctg?.localFragment || ctg?.sourceFragment;
  const length = positive(ctg?.totalLength ?? ctg?.lengthBp);
  const sourceStart = positive(fragment?.sourceStart) || 1;
  const sourceEnd = positive(fragment?.sourceEnd) || (length ? sourceStart + length - 1 : null);
  const assemblyCtgId = positive(ctg?.assemblyCtgId);
  if (!sourceEnd || sourceEnd < sourceStart || (!assemblyCtgId && !ctg?.localFragment)) return null;
  return { assemblyCtgId, sourceStart, sourceEnd, orient,
    sourceSeqId: positive(fragment?.sourceSeqId ?? ctg?.originSourceSeqId),
    datasetName: text(ctg?.datasetName || ctg?.source?.datasetName),
    contigName: text(ctg?.originId || ctg?.name),
    ...(ctg?.localFragment ? { parts: ctg.localFragment.parts } : {}),
  };
}

export function sourceIntervalProjectionAttrs(ctg, escapeAttr, orient = "+") {
  const range = buildSourceIntervalProjection(ctg, orient);
  return range ? `data-source-interval-projection="${escapeAttr(JSON.stringify(range))}"` : "";
}

export function intersectSourceInterval(selected, target) {
  if (!selected || !target) return null;
  if (selected.referenceChrName || target.referenceChrName) {
    if (!selected.referenceChrName || selected.referenceChrName !== target.referenceChrName) return null;
  } else if (selected.sourceSeqId && target.sourceSeqId) {
    if (selected.sourceSeqId !== target.sourceSeqId) return null;
  } else {
    const direct = selected.assemblyCtgId && (selected.assemblyCtgId === target.assemblyCtgId
      || target.parts?.some(part => part.assemblyCtgId === selected.assemblyCtgId));
    const original = selected.originalCoordinates && selected.datasetName && selected.contigName
      && selected.datasetName === target.datasetName && selected.contigName === target.contigName;
    if (!direct && !original) return null;
  }
  const sourceStart = Math.max(selected.sourceStart, target.sourceStart);
  const sourceEnd = Math.min(selected.sourceEnd, target.sourceEnd);
  if (!Number.isSafeInteger(sourceStart) || !Number.isSafeInteger(sourceEnd) || sourceStart > sourceEnd) return null;
  const span = target.sourceEnd - target.sourceStart + 1;
  const left = (sourceStart - target.sourceStart) / span;
  const right = (sourceEnd - target.sourceStart + 1) / span;
  return { sourceStart, sourceEnd, startFraction: target.orient === "-" ? 1 - right : left,
    endFraction: target.orient === "-" ? 1 - left : right };
}
