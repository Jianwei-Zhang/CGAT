import { normalizeSupportDatasetId, normalizeTrackDragOffsets, normalizeTrackRole } from "./selection-state.js";
import { normalizeCtgs } from "./track-layout.js";

export function rebaseTrackDragOffsetsForStableCtgPositions({
  trackRole = "primary",
  previousCtgs = [],
  nextCtgs = [],
  trackDragOffsets = [],
} = {}) {
  const normalizedTrackRole = normalizeTrackRole(trackRole);
  if (!normalizedTrackRole) {
    return normalizeTrackDragOffsets(trackDragOffsets);
  }

  const previousBaseStartBpById = buildBaseStartBpByAssemblyCtgId(previousCtgs);
  const nextBaseStartBpById = buildBaseStartBpByAssemblyCtgId(nextCtgs);
  const rebased = normalizeTrackDragOffsets(trackDragOffsets).map((item) => {
    if (item.trackRole !== normalizedTrackRole || !Number.isFinite(Number(item.offsetBp))) {
      return item;
    }
    const assemblyCtgId = normalizeSupportDatasetId(item.assemblyCtgId);
    if (!assemblyCtgId) {
      return item;
    }
    if (!previousBaseStartBpById.has(assemblyCtgId) || !nextBaseStartBpById.has(assemblyCtgId)) {
      return item;
    }
    const previousDisplayStartBp = previousBaseStartBpById.get(assemblyCtgId) + Number(item.offsetBp);
    const nextOffsetBp = previousDisplayStartBp - nextBaseStartBpById.get(assemblyCtgId);
    return {
      trackRole: item.trackRole,
      assemblyCtgId,
      offsetBp: roundTrackMetric(nextOffsetBp),
    };
  });

  return normalizeTrackDragOffsets(rebased);
}

function buildBaseStartBpByAssemblyCtgId(ctgs) {
  const starts = new Map();
  normalizeCtgs(ctgs).forEach((ctg) => {
    const assemblyCtgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
    if (!assemblyCtgId) {
      return;
    }
    starts.set(assemblyCtgId, Number.isFinite(Number(ctg.startBp)) ? Number(ctg.startBp) : 0);
  });
  return starts;
}

function roundTrackMetric(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}
