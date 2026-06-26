import {
  isFinalPathCtgSegment,
  isFinalPathGapSegment,
  isFinalPathRefSegment,
  normalizeFinalPathByChr,
  resolveFinalPathSegmentDisplayName,
  resolveFinalPathSegmentLengthBp,
} from "./final-path-state.js";

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizePositiveInteger(value) {
  const numeric = Number(value);
  if (!Number.isInteger(numeric) || numeric <= 0) {
    return null;
  }
  return numeric;
}

function normalizeDatasetName(value) {
  return normalizeString(value).toLowerCase();
}

function buildCtgIdentity({ assemblyCtgId = null, datasetName = "", ctgName = "", originId = "" } = {}) {
  const normalizedAssemblyCtgId = normalizePositiveInteger(assemblyCtgId);
  if (normalizedAssemblyCtgId) {
    return `id:${normalizedAssemblyCtgId}`;
  }
  const normalizedOriginId = normalizeString(originId).toLowerCase();
  if (normalizedOriginId) {
    return `origin:${normalizedOriginId}`;
  }
  const normalizedCtgName = normalizeString(ctgName).toLowerCase();
  const normalizedDatasetName = normalizeDatasetName(datasetName);
  if (normalizedCtgName) {
    return `name:${normalizedDatasetName}:${normalizedCtgName}`;
  }
  return "";
}

function buildPrimaryCtgInfo(ctg, primaryDatasetName = "") {
  const assemblyCtgId = normalizePositiveInteger(ctg?.assemblyCtgId);
  const ctgName = normalizeString(ctg?.name || ctg?.ctgName || (assemblyCtgId ? `Ctg${assemblyCtgId}` : ""));
  const datasetName = normalizeString(ctg?.datasetName) || normalizeString(primaryDatasetName);
  const originId = normalizeString(ctg?.originId ?? ctg?.origin_id);
  const totalLength = normalizePositiveInteger(ctg?.totalLength) || 0;
  return {
    assemblyCtgId,
    datasetName,
    ctgName,
    originId,
    totalLength,
    identity: buildCtgIdentity({
      assemblyCtgId,
      datasetName,
      ctgName,
      originId,
    }),
  };
}

function buildPrimaryCtgMaps(primaryCtgs, primaryDatasetName = "") {
  const infos = (Array.isArray(primaryCtgs) ? primaryCtgs : [])
    .map((ctg) => buildPrimaryCtgInfo(ctg, primaryDatasetName))
    .filter((info) => info.assemblyCtgId || info.identity);
  return {
    infos,
    byId: new Map(
      infos
        .filter((info) => info.assemblyCtgId)
        .map((info) => [info.assemblyCtgId, info]),
    ),
    byIdentity: new Map(
      infos
        .filter((info) => info.identity)
        .map((info) => [info.identity, info]),
    ),
  };
}

function isPrimaryDatasetSegment(segment, { primaryDatasetName = "", primaryById, primaryByIdentity }) {
  if (!isFinalPathCtgSegment(segment) || isFinalPathGapSegment(segment) || isFinalPathRefSegment(segment)) {
    return false;
  }
  const assemblyCtgId = normalizePositiveInteger(segment?.assemblyCtgId);
  if (assemblyCtgId && primaryById?.has(assemblyCtgId)) {
    return true;
  }
  const identity = buildCtgIdentity(segment);
  if (identity && primaryByIdentity?.has(identity)) {
    return true;
  }
  const segmentDatasetName = normalizeDatasetName(segment?.datasetName);
  return Boolean(segmentDatasetName && segmentDatasetName === normalizeDatasetName(primaryDatasetName));
}

function resolveSegmentCtgInfo(segment, primaryById, primaryByIdentity, primaryDatasetName = "") {
  const assemblyCtgId = normalizePositiveInteger(segment?.assemblyCtgId);
  const identity = buildCtgIdentity(segment);
  const primaryInfo = (assemblyCtgId ? primaryById?.get(assemblyCtgId) : null)
    || (identity ? primaryByIdentity?.get(identity) : null)
    || null;
  return {
    assemblyCtgId,
    datasetName: normalizeString(segment?.datasetName) || primaryInfo?.datasetName || primaryDatasetName,
    ctgName: normalizeString(segment?.ctgName) || primaryInfo?.ctgName || resolveFinalPathSegmentDisplayName(segment),
    originId: normalizeString(segment?.originId) || primaryInfo?.originId || "",
    identity: identity || primaryInfo?.identity || "",
  };
}

function collectFinalPathSegmentRows(finalPathEntry) {
  let cursor = 1;
  return (Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : []).map((segment, index) => {
    const lengthBp = Math.max(0, resolveFinalPathSegmentLengthBp(segment));
    const finalPathStart = lengthBp > 0 ? cursor : null;
    const finalPathEnd = lengthBp > 0 ? cursor + lengthBp - 1 : null;
    if (lengthBp > 0) {
      cursor = finalPathEnd + 1;
    }
    return {
      segment,
      index,
      lengthBp,
      finalPathStart,
      finalPathEnd,
    };
  });
}

export function canUseFinalPathLog(finalPathEntry) {
  const segments = Array.isArray(finalPathEntry?.segments) ? finalPathEntry.segments : [];
  return segments.length > 0 && !segments.some((segment) => isFinalPathRefSegment(segment));
}

function collectOtherChrPrimaryIdentities(finalPathByChr, currentChrName, primaryDatasetName) {
  const normalizedFinalPathByChr = normalizeFinalPathByChr(finalPathByChr);
  const currentChr = normalizeString(currentChrName);
  const identities = new Map();
  Object.entries(normalizedFinalPathByChr).forEach(([chrName, entry]) => {
    const normalizedChrName = normalizeString(chrName || entry?.chrName);
    if (!normalizedChrName || normalizedChrName === currentChr) {
      return;
    }
    collectFinalPathSegmentRows(entry).forEach(({ segment }) => {
      if (
        !isFinalPathCtgSegment(segment)
        || isFinalPathGapSegment(segment)
        || isFinalPathRefSegment(segment)
        || normalizeDatasetName(segment?.datasetName) !== normalizeDatasetName(primaryDatasetName)
      ) {
        return;
      }
      const identity = buildCtgIdentity(segment);
      if (!identity) {
        return;
      }
      const existing = identities.get(identity) || [];
      identities.set(identity, [...existing, normalizedChrName]);
    });
  });
  return identities;
}

export function buildFinalPathLogModel({
  chrName = "",
  finalPathEntry = null,
  finalPathByChr = {},
  primaryCtgs = [],
  hiddenPrimaryCtgIds = [],
  primaryDatasetName = "",
} = {}) {
  const normalizedChrName = normalizeString(chrName || finalPathEntry?.chrName);
  const primaryMaps = buildPrimaryCtgMaps(primaryCtgs, primaryDatasetName);
  const segmentRows = collectFinalPathSegmentRows(finalPathEntry);
  const hasRefSegments = segmentRows.some(({ segment }) => isFinalPathRefSegment(segment));
  const primaryRows = [];
  const supportRows = [];
  const appendedPrimaryIdentities = new Set();
  let appendedPrimaryBp = 0;

  segmentRows.forEach(({ segment, index, lengthBp, finalPathStart, finalPathEnd }) => {
    if (!isFinalPathCtgSegment(segment) || isFinalPathGapSegment(segment) || isFinalPathRefSegment(segment)) {
      return;
    }
    const isPrimary = isPrimaryDatasetSegment(segment, {
      primaryDatasetName,
      primaryById: primaryMaps.byId,
      primaryByIdentity: primaryMaps.byIdentity,
    });
    const ctgInfo = resolveSegmentCtgInfo(
      segment,
      primaryMaps.byId,
      primaryMaps.byIdentity,
      primaryDatasetName,
    );
    const row = {
      rowIndex: index + 1,
      datasetName: ctgInfo.datasetName,
      ctgName: ctgInfo.ctgName,
      originId: ctgInfo.originId,
      assemblyCtgId: ctgInfo.assemblyCtgId,
      identity: ctgInfo.identity,
      finalPathStart,
      finalPathEnd,
      lengthBp,
    };
    if (isPrimary) {
      if (row.identity) {
        appendedPrimaryIdentities.add(row.identity);
      }
      appendedPrimaryBp += lengthBp;
      primaryRows.push(row);
      return;
    }
    supportRows.push(row);
  });

  const hiddenRows = (Array.isArray(hiddenPrimaryCtgIds) ? hiddenPrimaryCtgIds : [])
    .map((ctgId) => primaryMaps.byId.get(normalizePositiveInteger(ctgId)))
    .filter((info) => info)
    .map((info) => {
      const alreadyAppended = appendedPrimaryIdentities.has(info.identity);
      return {
        rowIndex: null,
        datasetName: info.datasetName,
        ctgName: info.ctgName,
        originId: info.originId,
        assemblyCtgId: info.assemblyCtgId,
        identity: info.identity,
        finalPathStart: null,
        finalPathEnd: null,
        lengthBp: info.totalLength,
        countedLengthBp: alreadyAppended ? 0 : info.totalLength,
        counted: !alreadyAppended,
      };
    });
  const countedHiddenRows = hiddenRows.filter((row) => row.counted);
  const usedPrimaryIdentities = new Set([
    ...appendedPrimaryIdentities,
    ...countedHiddenRows.map((row) => row.identity).filter(Boolean),
  ]);
  const totalPrimaryLengthBp = primaryMaps.infos.reduce((sum, info) => sum + Math.max(0, info.totalLength), 0);
  const hiddenPrimaryBp = countedHiddenRows.reduce((sum, row) => sum + Math.max(0, row.countedLengthBp), 0);
  const otherChrPrimaryIdentities = collectOtherChrPrimaryIdentities(
    finalPathByChr,
    normalizedChrName,
    primaryDatasetName,
  );
  const otherChrPrimaryRows = primaryRows
    .filter((row) => row.identity && otherChrPrimaryIdentities.has(row.identity))
    .map((row) => ({
      ...row,
      usedByChrNames: otherChrPrimaryIdentities.get(row.identity) || [],
    }));

  return {
    chrName: normalizedChrName,
    hasSegments: segmentRows.length > 0,
    hasRefSegments,
    canLog: canUseFinalPathLog(finalPathEntry),
    primaryDatasetName: normalizeString(primaryDatasetName),
    primaryCount: {
      used: usedPrimaryIdentities.size,
      total: primaryMaps.infos.length,
      appended: appendedPrimaryIdentities.size,
      hidden: countedHiddenRows.length,
      appendedRows: primaryRows,
      hiddenRows,
    },
    primaryLength: {
      usedBp: appendedPrimaryBp + hiddenPrimaryBp,
      totalBp: totalPrimaryLengthBp,
      appendedBp: appendedPrimaryBp,
      hiddenBp: hiddenPrimaryBp,
      appendedRows: primaryRows,
      hiddenRows,
    },
    supportRows,
    otherChrPrimaryRows,
  };
}

function formatNullableNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? String(Math.trunc(numeric)) : "";
}

export function buildFinalPathLogTsvText(logModel) {
  const model = logModel || buildFinalPathLogModel();
  const rows = [
    [
      "primary_ctg_count",
      model.primaryDatasetName,
      "",
      "",
      "",
      "",
      "",
      "",
      `${model.primaryCount.used}/${model.primaryCount.total}`,
    ].join("\t"),
    [
      "primary_ctg_length",
      model.primaryDatasetName,
      "",
      "",
      "",
      "",
      "",
      "",
      `${model.primaryLength.usedBp}/${model.primaryLength.totalBp}`,
    ].join("\t"),
  ];
  const detailRows = [];
  model.supportRows.forEach((row) => {
    detailRows.push([
      "support",
      row.datasetName,
      row.ctgName,
      row.originId,
      formatNullableNumber(row.finalPathStart),
      formatNullableNumber(row.finalPathEnd),
      formatNullableNumber(row.lengthBp),
      "",
      "true",
    ].join("\t"));
  });
  model.otherChrPrimaryRows.forEach((row) => {
    detailRows.push([
      "other_chr_primary",
      row.datasetName,
      row.ctgName,
      row.originId,
      formatNullableNumber(row.finalPathStart),
      formatNullableNumber(row.finalPathEnd),
      formatNullableNumber(row.lengthBp),
      (row.usedByChrNames || []).join(","),
      "true",
    ].join("\t"));
  });
  if (detailRows.length) {
    rows.push(
      ["section", "dataset", "ctg", "origin_id", "start", "end", "length_bp", "used_by_chr", "counted"].join("\t"),
      ...detailRows,
    );
  }
  return `${rows.join("\n")}\n`;
}
