import {
  buildFinalPathLogModel,
  canUseFinalPathLog,
} from "./assembly/final-path-log-state.js";
import {
  isFinalPathRefSegment,
  normalizeFinalPathByChr,
} from "./assembly/final-path-state.js";
import { normalizeHiddenPrimaryCtgIds } from "./assembly/selection-state.js";

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizePositiveInteger(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function formatNumber(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? Math.trunc(numeric).toLocaleString("en-US") : "0";
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
  const normalizedDatasetName = normalizeString(datasetName).toLowerCase();
  return normalizedCtgName ? `name:${normalizedDatasetName}:${normalizedCtgName}` : "";
}

function buildPrimaryCtgInfo(ctg, primaryDatasetName = "") {
  const assemblyCtgId = normalizePositiveInteger(ctg?.assemblyCtgId);
  const datasetName = normalizeString(ctg?.datasetName) || normalizeString(primaryDatasetName);
  const ctgName = normalizeString(ctg?.name || ctg?.ctgName || (assemblyCtgId ? `Ctg${assemblyCtgId}` : ""));
  const originId = normalizeString(ctg?.originId ?? ctg?.origin_id);
  const totalLength = Math.max(0, Number(ctg?.totalLength || 0));
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

function sumLengthsByIdentity(items) {
  const seen = new Set();
  return (Array.isArray(items) ? items : []).reduce((sum, item) => {
    const identity = normalizeString(item?.identity);
    if (!identity || seen.has(identity)) {
      return sum;
    }
    seen.add(identity);
    return sum + Math.max(0, Number(item?.totalLength || item?.lengthBp || item?.countedLengthBp || 0));
  }, 0);
}

function collectUniquePrimaryInfos(primaryCtgsByChr, primaryDatasetName = "") {
  const byIdentity = new Map();
  Object.values(primaryCtgsByChr && typeof primaryCtgsByChr === "object" ? primaryCtgsByChr : {}).forEach((ctgs) => {
    (Array.isArray(ctgs) ? ctgs : []).forEach((ctg) => {
      const info = buildPrimaryCtgInfo(ctg, primaryDatasetName);
      if (info.identity && !byIdentity.has(info.identity)) {
        byIdentity.set(info.identity, info);
      }
    });
  });
  return Array.from(byIdentity.values());
}

function collectUsedPrimaryRows(logModels) {
  const byIdentity = new Map();
  logModels.forEach(({ model }) => {
    [
      ...(Array.isArray(model?.primaryCount?.appendedRows) ? model.primaryCount.appendedRows : []),
      ...(Array.isArray(model?.primaryCount?.hiddenRows) ? model.primaryCount.hiddenRows : []),
    ].forEach((row) => {
      if (row?.counted === false) {
        return;
      }
      const identity = normalizeString(row?.identity);
      if (!identity || byIdentity.has(identity)) {
        return;
      }
      byIdentity.set(identity, row);
    });
  });
  return Array.from(byIdentity.values());
}

function collectPrimaryUsageParts(logModels) {
  const appendedIdentities = new Set();
  const hiddenIdentities = new Set();
  let appendedBp = 0;
  let hiddenBp = 0;
  logModels.forEach(({ model }) => {
    (Array.isArray(model?.primaryCount?.appendedRows) ? model.primaryCount.appendedRows : []).forEach((row) => {
      const identity = normalizeString(row?.identity);
      if (identity) {
        appendedIdentities.add(identity);
      }
    });
    (Array.isArray(model?.primaryCount?.hiddenRows) ? model.primaryCount.hiddenRows : []).forEach((row) => {
      if (row?.counted === false) {
        return;
      }
      const identity = normalizeString(row?.identity);
      if (identity && !appendedIdentities.has(identity)) {
        hiddenIdentities.add(identity);
      }
    });
    appendedBp += Math.max(0, Number(model?.primaryLength?.appendedBp || 0));
    hiddenBp += Math.max(0, Number(model?.primaryLength?.hiddenBp || 0));
  });
  return {
    appendedCount: appendedIdentities.size,
    hiddenCount: hiddenIdentities.size,
    appendedBp,
    hiddenBp,
  };
}

function resolveHiddenPrimaryCtgIdsForChr(entry, chrName, hiddenPrimaryCtgIdsByChr) {
  const hiddenIds = new Set();
  [
    entry?.hiddenPrimaryCtgIds,
    hiddenPrimaryCtgIdsByChr?.[chrName],
    hiddenPrimaryCtgIdsByChr?.[entry?.chrName],
  ].forEach((ids) => {
    normalizeHiddenPrimaryCtgIds(ids).forEach((id) => hiddenIds.add(id));
  });
  return Array.from(hiddenIds.values());
}

export function buildProjectExportStatsModel({
  chromosomes = [],
  finalPathByChr = {},
  primaryCtgsByChr = {},
  hiddenPrimaryCtgIdsByChr = {},
  primaryDatasetName = "",
  unplacedCtgCount = 0,
  unplacedBp = 0,
} = {}) {
  const normalizedFinalPathByChr = normalizeFinalPathByChr(finalPathByChr);
  const finalPathEntries = Object.entries(normalizedFinalPathByChr)
    .filter(([, entry]) => Array.isArray(entry?.segments) && entry.segments.length > 0)
    .map(([chrName, entry]) => ({
      chrName: normalizeString(entry?.chrName || chrName),
      entry,
    }));
  const refChrNames = finalPathEntries
    .filter(({ entry }) => (entry.segments || []).some((segment) => isFinalPathRefSegment(segment)))
    .map(({ chrName }) => chrName);
  const statsDisabledByRef = refChrNames.length > 0;
  const logModels = statsDisabledByRef
    ? []
    : finalPathEntries
        .filter(({ entry }) => canUseFinalPathLog(entry))
        .map(({ chrName, entry }) => ({
          chrName,
          model: buildFinalPathLogModel({
            chrName,
            finalPathEntry: entry,
            finalPathByChr: normalizedFinalPathByChr,
            primaryCtgs: primaryCtgsByChr?.[chrName] || [],
            hiddenPrimaryCtgIds: resolveHiddenPrimaryCtgIdsForChr(
              entry,
              chrName,
              hiddenPrimaryCtgIdsByChr,
            ),
            primaryDatasetName,
          }),
        }));
  const assignedPrimaryInfos = collectUniquePrimaryInfos(primaryCtgsByChr, primaryDatasetName);
  const usedPrimaryRows = collectUsedPrimaryRows(logModels);
  const supportRows = logModels.flatMap(({ chrName, model }) =>
    (Array.isArray(model.supportRows) ? model.supportRows : []).map((row) => ({
      ...row,
      chrName,
      type: "support",
    })),
  );
  const otherChrPrimaryRows = logModels.flatMap(({ chrName, model }) =>
    (Array.isArray(model.otherChrPrimaryRows) ? model.otherChrPrimaryRows : []).map((row) => ({
      ...row,
      chrName,
      type: "other_chr_primary",
    })),
  );
  const assignedCount = assignedPrimaryInfos.length;
  const assignedBp = sumLengthsByIdentity(assignedPrimaryInfos);
  const usedCount = usedPrimaryRows.length;
  const usedBp = logModels.reduce((sum, { model }) =>
    sum + Math.max(0, Number(model?.primaryLength?.usedBp || 0)), 0);
  const usageParts = collectPrimaryUsageParts(logModels);
  const normalizedUnplacedCount = Math.max(0, Number(unplacedCtgCount || 0));
  const normalizedUnplacedBp = Math.max(0, Number(unplacedBp || 0));
  const placedNotUsedCount = Math.max(0, assignedCount - usedCount);
  const placedNotUsedBp = Math.max(0, assignedBp - usedBp);
  return {
    chromosomeCount: Array.isArray(chromosomes) ? chromosomes.length : 0,
    finalPathChrCount: finalPathEntries.length,
    statsDisabledByRef,
    refChrNames,
    canExportLog: !statsDisabledByRef,
    primaryDatasetName: normalizeString(primaryDatasetName),
    primaryCount: {
      used: usedCount,
      assigned: assignedCount,
      unassigned: normalizedUnplacedCount,
      total: assignedCount,
      appended: usageParts.appendedCount,
      hidden: usageParts.hiddenCount,
      label: `${formatNumber(usedCount)}/${formatNumber(assignedCount)}`,
    },
    primaryLength: {
      usedBp,
      assignedBp,
      unassignedBp: normalizedUnplacedBp,
      totalBp: assignedBp,
      appendedBp: usageParts.appendedBp,
      hiddenBp: usageParts.hiddenBp,
      label: `${formatNumber(usedBp)}/${formatNumber(assignedBp)}`,
    },
    assignment: {
      usedCount,
      usedBp,
      assignedCount,
      assignedBp,
      placedNotUsedCount,
      placedNotUsedBp,
      unassignedCount: normalizedUnplacedCount,
      unassignedBp: normalizedUnplacedBp,
    },
    supportRows,
    otherChrPrimaryRows,
  };
}

export function buildProjectExportLogText(model) {
  if (!model || model.statsDisabledByRef) {
    return "";
  }
  const rows = [
    ["section", "metric", "count", "length_bp"].join("\t"),
    ["primary", "used", model.primaryCount.used, model.primaryLength.usedBp].join("\t"),
    ["primary", "assigned", model.assignment.assignedCount, model.assignment.assignedBp].join("\t"),
    ["primary", "unassigned", model.assignment.unassignedCount, model.assignment.unassignedBp].join("\t"),
    "",
    ["section", "chr", "dataset", "ctg", "origin_id", "start", "end", "length_bp", "used_by_chr"].join("\t"),
  ];
  model.supportRows.forEach((row) => {
    rows.push([
      "support",
      row.chrName,
      row.datasetName,
      row.ctgName,
      row.originId,
      row.finalPathStart || "",
      row.finalPathEnd || "",
      row.lengthBp || "",
      row.chrName,
    ].join("\t"));
  });
  model.otherChrPrimaryRows.forEach((row) => {
    rows.push([
      "other_chr_primary",
      row.chrName,
      row.datasetName,
      row.ctgName,
      row.originId,
      row.finalPathStart || "",
      row.finalPathEnd || "",
      row.lengthBp || "",
      (row.usedByChrNames || []).join(","),
    ].join("\t"));
  });
  return `${rows.join("\n")}\n`;
}
