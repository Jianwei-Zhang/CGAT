// Explicit interval metadata must survive both context menus and drag-to-path.
// Source coordinates refer to the original source; display coordinates refer
// to the visible oriented contig. Never silently widen an invalid interval.
export function readMainFinalPathInterval(target) {
  const node = target?.closest?.("[data-main-fragment-start][data-main-fragment-end]");
  return node ? { start: Number(node.getAttribute("data-main-fragment-start")),
    end: Number(node.getAttribute("data-main-fragment-end")), coordinateSpace: "source" } : {};
}

export function buildSubviewFinalPathContext(context) {
  if (!context) return null;
  const result = {
    assemblyCtgId: context.assemblyCtgId, slot: context.slot, trackRole: context.trackRole,
    datasetId: context.datasetId, isMirror: context.isMirror === true, refOrient: context.refOrient,
    ...(context.compositionEntityKey ? { localFragmentEntityKey: context.compositionEntityKey } : {}),
    ...(context.start != null || context.end != null ? { start: context.start, end: context.end,
      sourceKind: context.sourceKind, referenceChrId: context.referenceChrId,
      referenceChrName: context.referenceChrName, segmentStartBp: context.segmentStartBp, segmentEndBp: context.segmentEndBp } : {}),
    ...(context.coordinateSpace ? { coordinateSpace: context.coordinateSpace } : {}),
  };
  for (const key of ["phasedTrackId", "phasedTrackItemId"]) if (Number(context[key]) > 0) result[key] = Number(context[key]);
  if (context.phasedHaplotypeKey) result.phasedHaplotypeKey = context.phasedHaplotypeKey;
  return result;
}
