export const FINAL_PATH_GAP_BP = 100;
export const FINAL_PATH_ALL_KEY = "__all__";

function normalizePositiveInteger(value) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizePositiveIntegerList(value) {
  const seen = new Set();
  return (Array.isArray(value) ? value : [])
    .map((item) => normalizePositiveInteger(item))
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

export function normalizeFinalPathViewMode(value, { allowLog = true } = {}) {
  const normalized = normalizeString(value).toLowerCase();
  if (allowLog && normalized === "log") {
    return "log";
  }
  if (normalized === "degap") {
    return "degap";
  }
  if (normalized === "table") {
    return "table";
  }
  return "graph";
}

function normalizeSourceKind(value) {
  return normalizeString(value).toLowerCase() === "ref_segment" ? "ref_segment" : "assembly_ctg";
}

function normalizeSegmentOrient(value) {
  const normalized = normalizeString(value);
  return normalized === "+" || normalized === "-" ? normalized : "";
}

function normalizeSegmentId(value, fallbackIndex = 0) {
  const normalized = normalizeString(value);
  if (normalized) {
    return normalized;
  }
  return `seg-${Math.max(1, Number(fallbackIndex) + 1)}`;
}

export function isFinalPathGapSegment(segment) {
  return normalizeString(segment?.type).toLowerCase() === "gap";
}

export function isFinalPathCtgSegment(segment) {
  return normalizeString(segment?.type).toLowerCase() !== "gap";
}

export function isFinalPathRefSegment(segment) {
  return isFinalPathCtgSegment(segment) && normalizeSourceKind(segment?.sourceKind) === "ref_segment";
}

export function resolveFinalPathRefSegmentAbsoluteRange(segment) {
  if (!isFinalPathRefSegment(segment)) {
    return null;
  }
  const memberStartBp = normalizePositiveInteger(segment?.memberStartBp);
  const memberEndBp = normalizePositiveInteger(segment?.memberEndBp);
  const start = normalizePositiveInteger(segment?.start);
  const end = normalizePositiveInteger(segment?.end);
  if (!memberStartBp || !memberEndBp || !start || !end || memberEndBp < memberStartBp) {
    return null;
  }
  const absoluteStart = memberStartBp + Math.min(start, end) - 1;
  const absoluteEnd = memberStartBp + Math.max(start, end) - 1;
  if (absoluteStart > memberEndBp || absoluteEnd > memberEndBp) {
    return null;
  }
  return {
    startBp: absoluteStart,
    endBp: absoluteEnd,
  };
}

export function resolveFinalPathSegmentDisplayName(segment) {
  if (isFinalPathGapSegment(segment)) {
    return "Gap";
  }
  if (isFinalPathRefSegment(segment)) {
    const referenceChrName = normalizeString(segment?.referenceChrName) || `Chr${normalizeString(segment?.referenceChrId)}`;
    const absoluteRange = resolveFinalPathRefSegmentAbsoluteRange(segment);
    if (!referenceChrName || !absoluteRange) {
      return normalizeString(segment?.ctgName);
    }
    return `ref_${referenceChrName}:${absoluteRange.startBp}-${absoluteRange.endBp}`;
  }
  const ctgName = normalizeString(segment?.ctgName) || `Ctg${normalizeString(segment?.assemblyCtgId)}`;
  const datasetName = normalizeString(segment?.datasetName);
  if (!datasetName) {
    return ctgName;
  }
  const prefix = `${datasetName}_`;
  if (ctgName.toLowerCase().startsWith(prefix.toLowerCase())) {
    return ctgName;
  }
  return `${datasetName}_${ctgName}`;
}

export function buildFinalPathGapSegment({ segmentId = "", gapSizeBp = FINAL_PATH_GAP_BP } = {}, index = 0) {
  const normalizedGapSizeBp = normalizePositiveInteger(gapSizeBp) || FINAL_PATH_GAP_BP;
  return {
    segmentId: normalizeSegmentId(segmentId, index),
    type: "gap",
    gapSizeBp: normalizedGapSizeBp,
  };
}

export function buildFinalPathCtgSegment(
  {
    segmentId = "",
    sourceKind = "assembly_ctg",
    assemblyCtgId = null,
    referenceChrId = null,
    referenceChrName = "",
    memberStartBp = null,
    memberEndBp = null,
    datasetName = "",
    ctgName = "",
    originId = "",
    overallLen = null,
    orient = "",
    start = null,
    end = null,
  } = {},
  index = 0,
) {
  const normalizedSourceKind = normalizeSourceKind(sourceKind);
  const normalizedAssemblyCtgId = normalizePositiveInteger(assemblyCtgId);
  const normalizedReferenceChrId = normalizePositiveInteger(referenceChrId);
  const normalizedReferenceChrName = normalizeString(referenceChrName);
  const normalizedMemberStartBp = normalizePositiveInteger(memberStartBp);
  const normalizedMemberEndBp = normalizePositiveInteger(memberEndBp);
  const normalizedDatasetName = normalizeString(datasetName);
  const normalizedCtgName = normalizeString(ctgName);
  const normalizedOriginId = normalizeString(originId);
  const normalizedOverallLen = normalizePositiveInteger(overallLen);
  const normalizedStart = normalizePositiveInteger(start);
  const normalizedEnd = normalizePositiveInteger(end);
  const normalizedOrient = normalizeSegmentOrient(orient);
  const isDraft = normalizedSourceKind !== "ref_segment"
    && !normalizedAssemblyCtgId
    && !normalizedDatasetName
    && !normalizedCtgName
    && !normalizedOriginId
    && !normalizedOverallLen
    && !normalizedStart
    && !normalizedEnd;
  if (isDraft) {
    return {
      segmentId: normalizeSegmentId(segmentId, index),
      type: "ctg",
      assemblyCtgId: null,
      datasetName: "",
      ctgName: "",
      overallLen: null,
      start: null,
      end: null,
    };
  }
  if (
    !normalizedOverallLen
    || !normalizedStart
    || !normalizedEnd
    || normalizedStart > normalizedOverallLen
    || normalizedEnd > normalizedOverallLen
  ) {
    return null;
  }
  const shouldSwapRange =
    (normalizedOrient === "-" && normalizedStart < normalizedEnd)
    || (normalizedOrient === "+" && normalizedStart > normalizedEnd);
  const orientedStart = shouldSwapRange ? normalizedEnd : normalizedStart;
  const orientedEnd = shouldSwapRange ? normalizedStart : normalizedEnd;
  if (normalizedSourceKind === "ref_segment") {
    if (
      !normalizedReferenceChrName
      || !normalizedMemberStartBp
      || !normalizedMemberEndBp
      || normalizedMemberEndBp < normalizedMemberStartBp
    ) {
      return null;
    }
    const derivedOverallLen = normalizedMemberEndBp - normalizedMemberStartBp + 1;
    if (normalizedOverallLen !== derivedOverallLen) {
      return null;
    }
    const refSegment = {
      segmentId: normalizeSegmentId(segmentId, index),
      type: "ctg",
      sourceKind: "ref_segment",
      assemblyCtgId: normalizedAssemblyCtgId || null,
      ...(normalizedReferenceChrId ? { referenceChrId: normalizedReferenceChrId } : {}),
      referenceChrName: normalizedReferenceChrName,
      datasetName: "",
      ctgName: "",
      originId: normalizedOriginId || normalizedReferenceChrName,
      overallLen: normalizedOverallLen,
      memberStartBp: normalizedMemberStartBp,
      memberEndBp: normalizedMemberEndBp,
      start: orientedStart,
      end: orientedEnd,
    };
    return {
      ...refSegment,
      ctgName: resolveFinalPathSegmentDisplayName(refSegment),
    };
  }
  if (!normalizedCtgName) {
    return null;
  }
  return {
    segmentId: normalizeSegmentId(segmentId, index),
    type: "ctg",
    assemblyCtgId: normalizedAssemblyCtgId || null,
    datasetName: normalizedDatasetName,
    ctgName: normalizedCtgName,
    ...(normalizedOriginId ? { originId: normalizedOriginId } : {}),
    overallLen: normalizedOverallLen,
    start: orientedStart,
    end: orientedEnd,
  };
}

export function resolveFinalPathSegmentLengthBp(segment) {
  if (!segment || typeof segment !== "object") {
    return 0;
  }
  if (isFinalPathGapSegment(segment)) {
    return normalizePositiveInteger(segment.gapSizeBp) || FINAL_PATH_GAP_BP;
  }
  const start = normalizePositiveInteger(segment.start);
  const end = normalizePositiveInteger(segment.end);
  if (!start || !end) {
    return 0;
  }
  return Math.abs(end - start) + 1;
}

function normalizeSegment(segment, index = 0) {
  if (!segment || typeof segment !== "object") {
    return null;
  }
  if (isFinalPathGapSegment(segment)) {
    return buildFinalPathGapSegment(
      {
        segmentId: segment.segmentId,
        gapSizeBp: segment.gapSizeBp,
      },
      index,
    );
  }
  return buildFinalPathCtgSegment(
    {
      segmentId: segment.segmentId,
      sourceKind: segment.sourceKind,
      assemblyCtgId: segment.assemblyCtgId,
      referenceChrId: segment.referenceChrId,
      referenceChrName: segment.referenceChrName,
      memberStartBp: segment.memberStartBp,
      memberEndBp: segment.memberEndBp,
      datasetName: segment.datasetName,
      ctgName: segment.ctgName,
      originId: segment.originId,
      overallLen: segment.overallLen,
      orient: segment.orient,
      start: segment.start,
      end: segment.end,
    },
    index,
  );
}

export function buildFinalPathEntry({
  chrName,
  segments = [],
  totalLength = null,
  updatedAt = "",
  hiddenPrimaryCtgIds = [],
}) {
  const normalizedChrName = normalizeString(chrName);
  if (!normalizedChrName) {
    return null;
  }
  const normalizedSegments = (Array.isArray(segments) ? segments : [])
    .map((segment, index) => normalizeSegment(segment, index))
    .filter((segment) => segment !== null);
  const computedTotalLength = normalizedSegments.reduce(
    (sum, segment) => sum + resolveFinalPathSegmentLengthBp(segment),
    0,
  );
  const normalizedTotalLength = normalizePositiveInteger(totalLength) || computedTotalLength;
  const normalizedHiddenPrimaryCtgIds = normalizePositiveIntegerList(hiddenPrimaryCtgIds);
  return {
    mode: "segments",
    chrName: normalizedChrName,
    segments: normalizedSegments,
    totalLength: normalizedTotalLength,
    updatedAt: String(updatedAt || ""),
    ...(normalizedHiddenPrimaryCtgIds.length ? { hiddenPrimaryCtgIds: normalizedHiddenPrimaryCtgIds } : {}),
  };
}

function normalizeSegmentEntry(chrName, entry) {
  const mode = normalizeString(entry?.mode).toLowerCase();
  if (mode !== "segments" || !Array.isArray(entry?.segments)) {
    return null;
  }
  return buildFinalPathEntry({
    chrName: normalizeString(entry?.chrName) || chrName,
    segments: entry?.segments,
    totalLength: entry?.totalLength,
    updatedAt: entry?.updatedAt,
    hiddenPrimaryCtgIds: entry?.hiddenPrimaryCtgIds,
  });
}

export function normalizeFinalPathByChr(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const next = {};
  for (const [chrName, entry] of Object.entries(source)) {
    const normalizedEntry = normalizeSegmentEntry(chrName, entry);
    if (!normalizedEntry) {
      continue;
    }
    next[normalizedEntry.chrName] = normalizedEntry;
  }
  return next;
}

export function resolveFinalPathTotalLengthBp(entry) {
  const normalizedTotal = normalizePositiveInteger(entry?.totalLength);
  if (normalizedTotal) {
    return normalizedTotal;
  }
  const segments = Array.isArray(entry?.segments) ? entry.segments : [];
  return segments.reduce((sum, segment) => sum + resolveFinalPathSegmentLengthBp(segment), 0);
}

export function getCurrentChrFinalPath(assembly) {
  const normalized = normalizeFinalPathByChr(assembly?.finalPathByChr);
  const selectedChrName = resolveCurrentFinalPathChrName(assembly);
  if (!selectedChrName) {
    return null;
  }
  return normalized[selectedChrName] || null;
}

export function resolveFinalPathSelectionKey(assembly) {
  const selectedChrName = normalizeString(assembly?.selectedChrName);
  if (!selectedChrName) {
    return "";
  }
  const tracks = Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [];
  if (!assembly?.isChrPhased || !tracks.length) {
    return "";
  }
  const byChr = assembly?.activeFinalPathKeyByChr && typeof assembly.activeFinalPathKeyByChr === "object"
    ? assembly.activeFinalPathKeyByChr
    : {};
  const rawKey = normalizeString(byChr[selectedChrName] || assembly?.activeFinalPathKey);
  if (!rawKey || rawKey === FINAL_PATH_ALL_KEY) {
    return FINAL_PATH_ALL_KEY;
  }
  const matched = tracks.find((track) => normalizeString(track?.haplotypeKey) === rawKey);
  return matched ? rawKey : FINAL_PATH_ALL_KEY;
}

export function isFinalPathAllSelection(assembly) {
  return resolveFinalPathSelectionKey(assembly) === FINAL_PATH_ALL_KEY;
}

export function resolveCurrentFinalPathChrName(assembly) {
  const selectedChrName = normalizeString(assembly?.selectedChrName);
  if (!selectedChrName) {
    return "";
  }
  const tracks = Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [];
  if (!assembly?.isChrPhased || !tracks.length) {
    return selectedChrName;
  }
  const activeKey = resolveFinalPathSelectionKey(assembly);
  const activeTrack = tracks.find((track) => normalizeString(track?.haplotypeKey) === activeKey) || tracks[0];
  return normalizeString(activeTrack?.label) || selectedChrName;
}
