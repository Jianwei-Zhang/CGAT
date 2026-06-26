import { normalizeNonNegativeInt, normalizePositiveInt } from "./track-prefs.js";

export function normalizeSupportDatasetId(datasetId) {
  const parsed = Number(datasetId);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.trunc(parsed);
}

export function normalizeTrackRole(role) {
  const normalizedRole = String(role || "").trim();
  if (
    normalizedRole === "primary"
    || normalizedRole === "support"
    || normalizedRole === "ref"
    || normalizedRole === "phased"
  ) {
    return normalizedRole;
  }
  return "";
}

function normalizeSubviewTrackSlot(slot) {
  const normalizedSlot = String(slot || "").trim();
  if (normalizedSlot === "top" || normalizedSlot === "bottom") {
    return normalizedSlot;
  }
  return "";
}

function roundTrackMetric(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

function isFiniteTrackMetric(value) {
  return Number.isFinite(Number(value));
}

function buildPrimaryCtgIdSet(assembly) {
  return new Set(
    (Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [])
      .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
      .filter((ctgId) => ctgId !== null),
  );
}

export function normalizeTrackSelectionCtgIds(values) {
  const list = Array.isArray(values) ? values : [];
  const normalized = new Set();
  list.forEach((value) => {
    const parsed = normalizeSupportDatasetId(value);
    if (parsed) {
      normalized.add(parsed);
    }
  });
  return Array.from(normalized.values()).sort((left, right) => left - right);
}

export function normalizeHiddenPrimaryCtgIds(values) {
  return normalizeTrackSelectionCtgIds(values);
}

export function normalizeHiddenPrimaryCtgIdsByChr(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const normalized = {};
  Object.entries(source).forEach(([chrName, hiddenIds]) => {
    const normalizedChrName = String(chrName || "").trim();
    const normalizedHiddenIds = normalizeHiddenPrimaryCtgIds(hiddenIds);
    if (normalizedChrName && normalizedHiddenIds.length) {
      normalized[normalizedChrName] = normalizedHiddenIds;
    }
  });
  return normalized;
}

export function buildSupportMirrorKey(datasetId, assemblyCtgId) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId) || 0;
  const normalizedAssemblyCtgId = normalizeSupportDatasetId(assemblyCtgId) || 0;
  return `${normalizedDatasetId}:${normalizedAssemblyCtgId}`;
}

export function normalizeSupportMirrorEntry(entry) {
  const datasetId = normalizeSupportDatasetId(entry?.datasetId);
  const assemblyCtgId = normalizeSupportDatasetId(entry?.assemblyCtgId);
  if (!datasetId || !assemblyCtgId) {
    return null;
  }
  const originId = String(entry?.originId ?? entry?.origin_id ?? "").trim();
  const totalLength = Math.max(
    1,
    normalizePositiveInt(entry?.totalLength ?? entry?.lengthBp ?? entry?.lenBp) ?? 1,
  );
  const lengthBp = Math.max(1, normalizePositiveInt(entry?.lengthBp ?? totalLength) ?? totalLength);
  const startBp = Math.max(0, normalizeNonNegativeInt(entry?.startBp) ?? 0);
  const resolvedEndBp = Math.max(1, normalizePositiveInt(entry?.endBp) ?? (startBp + lengthBp - 1));
  const laneIndex = Math.max(0, normalizeNonNegativeInt(entry?.laneIndex) ?? 0);
  const hits = Array.isArray(entry?.hits)
    ? entry.hits
      .filter((hit) => hit && typeof hit === "object")
      .map((hit) => ({ ...hit }))
    : [];
  return {
    datasetId,
    datasetName: String(entry?.datasetName || ""),
    chrName: String(entry?.chrName || "").trim(),
    assemblyCtgId,
    name: String(entry?.name || `Ctg${assemblyCtgId}`),
    originId,
    totalLength,
    anchorStart: normalizeNonNegativeInt(entry?.anchorStart),
    lengthBp,
    startBp,
    endBp: resolvedEndBp,
    laneIndex,
    hits,
    isSelected: Boolean(entry?.isSelected),
  };
}

export function normalizeSupportMirroredCtgs(values) {
  const list = Array.isArray(values) ? values : [];
  const normalized = new Map();
  list.forEach((entry) => {
    const normalizedEntry = normalizeSupportMirrorEntry(entry);
    if (!normalizedEntry) {
      return;
    }
    normalized.set(
      buildSupportMirrorKey(normalizedEntry.datasetId, normalizedEntry.assemblyCtgId),
      normalizedEntry,
    );
  });
  return Array.from(normalized.values());
}

export function buildSubviewTrackDragOffsetKey(slot, contigId) {
  const normalizedSlot = normalizeSubviewTrackSlot(slot) || "top";
  const normalizedContigId = normalizeSupportDatasetId(contigId) || 0;
  return `${normalizedSlot}:${normalizedContigId}`;
}

export function buildTrackDragOffsetKey(trackRole, assemblyCtgId, scope = {}) {
  const normalizedRole = normalizeTrackRole(trackRole);
  const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId) || 0;
  if (normalizedRole === "support") {
    const datasetId = normalizeSupportDatasetId(scope?.datasetId);
    if (datasetId) {
      return `${normalizedRole}:${datasetId}:${normalizedCtgId}`;
    }
  }
  if (normalizedRole === "phased") {
    const phasedTrackItemId = normalizeSupportDatasetId(scope?.phasedTrackItemId);
    if (phasedTrackItemId) {
      return `${normalizedRole}:item:${phasedTrackItemId}`;
    }
    const phasedTrackId = normalizeSupportDatasetId(scope?.phasedTrackId);
    if (phasedTrackId) {
      return `${normalizedRole}:track:${phasedTrackId}:${normalizedCtgId}`;
    }
  }
  return `${normalizedRole}:${normalizedCtgId}`;
}

export function normalizeTrackDragOffsets(values) {
  const list = Array.isArray(values) ? values : [];
  const normalized = new Map();
  list.forEach((item) => {
    const trackRole = normalizeTrackRole(item?.trackRole);
    const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId);
    const datasetId = normalizeSupportDatasetId(item?.datasetId);
    const phasedTrackId = normalizeSupportDatasetId(item?.phasedTrackId);
    const phasedTrackItemId = normalizeSupportDatasetId(item?.phasedTrackItemId);
    const hasOffsetBp = isFiniteTrackMetric(item?.offsetBp);
    const hasOffsetPx = isFiniteTrackMetric(item?.offsetPx);
    if (!trackRole || !assemblyCtgId || (!hasOffsetBp && !hasOffsetPx)) {
      return;
    }
    if (hasOffsetBp) {
      const roundedOffsetBp = roundTrackMetric(item.offsetBp);
      if (Math.abs(roundedOffsetBp) < 0.01) {
        return;
      }
      normalized.set(buildTrackDragOffsetKey(trackRole, assemblyCtgId, { datasetId, phasedTrackId, phasedTrackItemId }), {
        trackRole,
        ...(datasetId && trackRole === "support" ? { datasetId } : {}),
        assemblyCtgId,
        ...(phasedTrackId ? { phasedTrackId } : {}),
        ...(phasedTrackItemId ? { phasedTrackItemId } : {}),
        offsetBp: roundedOffsetBp,
      });
      return;
    }
    const roundedOffsetPx = roundTrackMetric(item.offsetPx);
    if (Math.abs(roundedOffsetPx) < 0.01) {
      return;
    }
    normalized.set(buildTrackDragOffsetKey(trackRole, assemblyCtgId, { datasetId, phasedTrackId, phasedTrackItemId }), {
      trackRole,
      ...(datasetId && trackRole === "support" ? { datasetId } : {}),
      assemblyCtgId,
      ...(phasedTrackId ? { phasedTrackId } : {}),
      ...(phasedTrackItemId ? { phasedTrackItemId } : {}),
      offsetPx: roundedOffsetPx,
    });
  });
  return Array.from(normalized.values()).sort((left, right) => {
    if (left.trackRole !== right.trackRole) {
      return left.trackRole === "primary" ? -1 : 1;
    }
    const datasetCompare = (left.datasetId || 0) - (right.datasetId || 0);
    if (datasetCompare !== 0) {
      return datasetCompare;
    }
    return left.assemblyCtgId - right.assemblyCtgId;
  });
}

export function normalizeSubviewTrackDragOffsets(values) {
  const list = Array.isArray(values) ? values : [];
  const normalized = new Map();
  list.forEach((item) => {
    const slot = normalizeSubviewTrackSlot(item?.slot);
    const contigId = normalizeSupportDatasetId(item?.contigId);
    const hasOffsetBp = isFiniteTrackMetric(item?.offsetBp);
    const hasOffsetPx = isFiniteTrackMetric(item?.offsetPx);
    if (!slot || !contigId || (!hasOffsetBp && !hasOffsetPx)) {
      return;
    }
    if (hasOffsetBp) {
      const roundedOffsetBp = roundTrackMetric(item.offsetBp);
      if (Math.abs(roundedOffsetBp) < 0.01) {
        return;
      }
      normalized.set(buildSubviewTrackDragOffsetKey(slot, contigId), {
        slot,
        contigId,
        offsetBp: roundedOffsetBp,
      });
      return;
    }
    const roundedOffsetPx = roundTrackMetric(item.offsetPx);
    if (Math.abs(roundedOffsetPx) < 0.01) {
      return;
    }
    normalized.set(buildSubviewTrackDragOffsetKey(slot, contigId), {
      slot,
      contigId,
      offsetPx: roundedOffsetPx,
    });
  });
  return Array.from(normalized.values()).sort((left, right) => {
    if (left.slot !== right.slot) {
      return left.slot === "top" ? -1 : 1;
    }
    return left.contigId - right.contigId;
  });
}

export function setTrackDragOffset(offsets, nextOffset) {
  const normalized = normalizeTrackDragOffsets(offsets);
  const trackRole = normalizeTrackRole(nextOffset?.trackRole);
  const assemblyCtgId = normalizeSupportDatasetId(nextOffset?.assemblyCtgId);
  const datasetId = normalizeSupportDatasetId(nextOffset?.datasetId);
  const phasedTrackId = normalizeSupportDatasetId(nextOffset?.phasedTrackId);
  const phasedTrackItemId = normalizeSupportDatasetId(nextOffset?.phasedTrackItemId);
  const hasOffsetBp = isFiniteTrackMetric(nextOffset?.offsetBp);
  const hasOffsetPx = isFiniteTrackMetric(nextOffset?.offsetPx);
  if (!trackRole || !assemblyCtgId || (!hasOffsetBp && !hasOffsetPx)) {
    return normalized;
  }
  const roundedOffset = hasOffsetBp
    ? roundTrackMetric(nextOffset.offsetBp)
    : roundTrackMetric(nextOffset.offsetPx);
  const targetKey = buildTrackDragOffsetKey(trackRole, assemblyCtgId, { datasetId, phasedTrackId, phasedTrackItemId });
  const legacySupportKey = trackRole === "support"
    ? buildTrackDragOffsetKey(trackRole, assemblyCtgId)
    : "";
  const map = new Map(normalized.map((item) => [
    buildTrackDragOffsetKey(item.trackRole, item.assemblyCtgId, item),
    item,
  ]));
  if (legacySupportKey && legacySupportKey !== targetKey) {
    map.delete(legacySupportKey);
  }
  if (Math.abs(roundedOffset) < 0.01) {
    map.delete(targetKey);
  } else {
    map.set(targetKey, {
      trackRole,
      ...(datasetId && trackRole === "support" ? { datasetId } : {}),
      assemblyCtgId,
      ...(phasedTrackId ? { phasedTrackId } : {}),
      ...(phasedTrackItemId ? { phasedTrackItemId } : {}),
      ...(hasOffsetBp ? { offsetBp: roundedOffset } : { offsetPx: roundedOffset }),
    });
  }
  return normalizeTrackDragOffsets(Array.from(map.values()));
}

export function setSubviewTrackDragOffset(offsets, nextOffset) {
  const normalized = normalizeSubviewTrackDragOffsets(offsets);
  const slot = normalizeSubviewTrackSlot(nextOffset?.slot);
  const contigId = normalizeSupportDatasetId(nextOffset?.contigId);
  const hasOffsetBp = isFiniteTrackMetric(nextOffset?.offsetBp);
  const hasOffsetPx = isFiniteTrackMetric(nextOffset?.offsetPx);
  if (!slot || !contigId || (!hasOffsetBp && !hasOffsetPx)) {
    return normalized;
  }
  const roundedOffset = hasOffsetBp
    ? roundTrackMetric(nextOffset.offsetBp)
    : roundTrackMetric(nextOffset.offsetPx);
  const targetKey = buildSubviewTrackDragOffsetKey(slot, contigId);
  const map = new Map(
    normalized.map((item) => [buildSubviewTrackDragOffsetKey(item.slot, item.contigId), item]),
  );
  if (Math.abs(roundedOffset) < 0.01) {
    map.delete(targetKey);
  } else {
    map.set(targetKey, {
      slot,
      contigId,
      ...(hasOffsetBp ? { offsetBp: roundedOffset } : { offsetPx: roundedOffset }),
    });
  }
  return normalizeSubviewTrackDragOffsets(Array.from(map.values()));
}

export function swapSubviewTrackDragOffsetsForSummarySwap(offsets) {
  const normalized = normalizeSubviewTrackDragOffsets(offsets);
  const swapped = normalized.map((item) => ({
    ...item,
    slot: item.slot === "top" ? "bottom" : "top",
  }));
  return normalizeSubviewTrackDragOffsets(swapped);
}

export function areTrackDragOffsetsEqual(left, right) {
  const normalizedLeft = normalizeTrackDragOffsets(left);
  const normalizedRight = normalizeTrackDragOffsets(right);
  if (normalizedLeft.length !== normalizedRight.length) {
    return false;
  }
  return normalizedLeft.every((leftItem, index) => {
    const rightItem = normalizedRight[index];
    return (
      leftItem.trackRole === rightItem.trackRole &&
      (leftItem.datasetId || null) === (rightItem.datasetId || null) &&
      leftItem.assemblyCtgId === rightItem.assemblyCtgId &&
      (leftItem.phasedTrackId || null) === (rightItem.phasedTrackId || null) &&
      (leftItem.phasedTrackItemId || null) === (rightItem.phasedTrackItemId || null) &&
      (isFiniteTrackMetric(leftItem.offsetBp) ? leftItem.offsetBp : null)
        === (isFiniteTrackMetric(rightItem.offsetBp) ? rightItem.offsetBp : null) &&
      (isFiniteTrackMetric(leftItem.offsetPx) ? leftItem.offsetPx : null)
        === (isFiniteTrackMetric(rightItem.offsetPx) ? rightItem.offsetPx : null)
    );
  });
}

export function areSubviewTrackDragOffsetsEqual(left, right) {
  const normalizedLeft = normalizeSubviewTrackDragOffsets(left);
  const normalizedRight = normalizeSubviewTrackDragOffsets(right);
  if (normalizedLeft.length !== normalizedRight.length) {
    return false;
  }
  return normalizedLeft.every((leftItem, index) => {
    const rightItem = normalizedRight[index];
    return (
      leftItem.slot === rightItem.slot &&
      leftItem.contigId === rightItem.contigId &&
      (isFiniteTrackMetric(leftItem.offsetBp) ? leftItem.offsetBp : null)
        === (isFiniteTrackMetric(rightItem.offsetBp) ? rightItem.offsetBp : null) &&
      (isFiniteTrackMetric(leftItem.offsetPx) ? leftItem.offsetPx : null)
        === (isFiniteTrackMetric(rightItem.offsetPx) ? rightItem.offsetPx : null)
    );
  });
}

export function normalizeDeletedCtgRecordIds(values) {
  const list = Array.isArray(values) ? values : [];
  const normalized = new Set();
  list.forEach((value) => {
    const parsed = normalizeSupportDatasetId(value);
    if (parsed) {
      normalized.add(parsed);
    }
  });
  return Array.from(normalized.values()).sort((left, right) => left - right);
}

export function filterPrimaryTrackSelectionCtgIds(selectedIds, assembly) {
  const primaryIds = buildPrimaryCtgIdSet(assembly);
  return normalizeTrackSelectionCtgIds(selectedIds).filter((ctgId) => primaryIds.has(ctgId));
}

export function filterTrackDragOffsets(offsets, assembly, options = {}) {
  const preserveUnmatchedSupportOffsets = Boolean(options?.preserveUnmatchedSupportOffsets);
  const supportDatasetId = normalizeSupportDatasetId(assembly?.supportDatasetId);
  const primaryIds = new Set(
    (Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [])
      .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
      .filter((ctgId) => ctgId !== null)
      .map((ctgId) => buildTrackDragOffsetKey("primary", ctgId)),
  );
  const supportIds = new Set(
    (Array.isArray(assembly?.supportChrCtgs) ? assembly.supportChrCtgs : [])
      .map((ctg) => ({
        ctgId: normalizeSupportDatasetId(ctg?.assemblyCtgId),
        datasetId: normalizeSupportDatasetId(ctg?.datasetId) || supportDatasetId,
      }))
      .filter((item) => item.ctgId !== null)
      .flatMap((item) => [
        buildTrackDragOffsetKey("support", item.ctgId, { datasetId: item.datasetId }),
        buildTrackDragOffsetKey("support", item.ctgId),
      ]),
  );
  const supportMirrorIds = new Set(
    normalizeSupportMirroredCtgs(assembly?.supportMirroredCtgs).flatMap((entry) => [
      buildTrackDragOffsetKey("support", entry.assemblyCtgId, { datasetId: entry.datasetId }),
      buildTrackDragOffsetKey("support", entry.assemblyCtgId),
    ]),
  );
  const phasedIds = new Set(
    (Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [])
      .flatMap((track) =>
        (Array.isArray(track?.items) ? track.items : []).map((item) =>
          buildTrackDragOffsetKey("phased", item?.assemblyCtgId, {
            phasedTrackId: track?.phasedTrackId,
            phasedTrackItemId: item?.itemId ?? item?.phasedTrackItemId,
          }),
        ),
      ),
  );
  const allowed = new Set([...primaryIds, ...supportIds, ...supportMirrorIds, ...phasedIds]);
  return normalizeTrackDragOffsets(offsets).filter((item) =>
    allowed.has(buildTrackDragOffsetKey(item.trackRole, item.assemblyCtgId, item))
      || (
        preserveUnmatchedSupportOffsets
        && item.trackRole === "support"
      ),
  );
}

export function filterSubviewTrackDragOffsetsBySummary(offsets, summary) {
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  if (!top || !bottom) {
    return [];
  }
  const allowed = new Set([
    buildSubviewTrackDragOffsetKey("top", top.contigId),
    buildSubviewTrackDragOffsetKey("bottom", bottom.contigId),
  ]);
  return normalizeSubviewTrackDragOffsets(offsets).filter((item) =>
    allowed.has(buildSubviewTrackDragOffsetKey(item.slot, item.contigId)),
  );
}

function normalizeSubviewSummarySelection(selection) {
  const contigId = normalizeSupportDatasetId(selection?.contigId);
  if (!contigId) {
    return null;
  }
  return {
    contigId,
  };
}
