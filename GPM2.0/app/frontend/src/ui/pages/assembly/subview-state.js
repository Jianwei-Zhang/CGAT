import {
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackRole,
} from "./selection-state.js";
import {
  normalizeNonNegativeInt,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  normalizeSubviewActiveAnchors,
  normalizeSubviewManualAnchors,
} from "./subview-anchor-state.js";
import {
  buildChrLengthsByName,
  filterSupportCtgsBySupportDsCtgLenRules,
  getSupportDsCtgLenRulesForChr,
} from "./support-ds-ctg-len-rules.js";
import { tAssembly } from "./i18n.js";

function tSubview(stateOrLocale, path, vars = {}) {
  return tAssembly(stateOrLocale, `subview.${path}`, vars);
}

function normalizeBoolean(value) {
  if (value === true || value === "true") {
    return true;
  }
  if (value === false || value === "false") {
    return false;
  }
  return null;
}

function buildDeletedAssemblyCtgIdSet(deletedCtgs) {
  const deletedAssemblyCtgIds = new Set();
  (Array.isArray(deletedCtgs) ? deletedCtgs : []).forEach((ctg) => {
    const assemblyCtgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
    if (assemblyCtgId) {
      deletedAssemblyCtgIds.add(assemblyCtgId);
    }
  });
  return deletedAssemblyCtgIds;
}

function filterDeletedAssemblyCtgs(ctgs, deletedAssemblyCtgIds) {
  const list = Array.isArray(ctgs) ? ctgs : [];
  if (!(deletedAssemblyCtgIds instanceof Set) || !deletedAssemblyCtgIds.size) {
    return list;
  }
  return list.filter((ctg) => {
    const assemblyCtgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
    return assemblyCtgId === null || !deletedAssemblyCtgIds.has(assemblyCtgId);
  });
}

function cloneHits(hits) {
  return Array.isArray(hits) ? hits.map((hit) => ({ ...hit })) : [];
}

export function resolveSubviewCtgOrientValue(ctg) {
  const orient = String((ctg?.orient ?? ctg?.refOrient ?? ctg?.ref_orient) || "").trim();
  return orient === "-" ? "-" : "+";
}

export function flipSubviewHitRange(hit, totalLength, startKey, endKey) {
  const start = Number(hit?.[startKey]);
  const end = Number(hit?.[endKey]);
  if (!Number.isFinite(start) || !Number.isFinite(end)) {
    return {};
  }
  return {
    [startKey]: totalLength - end + 1,
    [endKey]: totalLength - start + 1,
  };
}

export function buildPhasedSubviewCtgHits({ sourceCtg, totalLength, itemOrient } = {}) {
  const hits = cloneHits(sourceCtg?.hits);
  if (itemOrient === resolveSubviewCtgOrientValue(sourceCtg)) {
    return hits;
  }
  const safeLength = Math.max(1, normalizeNonNegativeInt(totalLength) ?? 1);
  return hits.map((hit) => ({
    ...hit,
    ...flipSubviewHitRange(hit, safeLength, "ctgStart", "ctgEnd"),
    ...flipSubviewHitRange(hit, safeLength, "ctg_start", "ctg_end"),
    ...flipSubviewHitRange(hit, safeLength, "queryStart", "queryEnd"),
    ...flipSubviewHitRange(hit, safeLength, "query_start", "query_end"),
    ...flipSubviewHitRange(hit, safeLength, "hitStart", "hitEnd"),
    ...flipSubviewHitRange(hit, safeLength, "hit_start", "hit_end"),
  }));
}

function buildSupportMirrorCtgPool({
  supportChrCtgs,
  supportMirroredCtgs,
  supportDatasetId = null,
  selectedChrName = "",
  deletedCtgs = [],
  minSupportLengthBp = 0,
  supportDsCtgLenRules = [],
  supportDsCtgLenRulesChrLength = null,
}) {
  const targetChrName = String(selectedChrName || "").trim();
  const deletedAssemblyCtgIds = buildDeletedAssemblyCtgIdSet(deletedCtgs);
  const activeSupportDatasetId = normalizeSupportDatasetId(supportDatasetId);
  const liveSupportById = new Map(
    (Array.isArray(supportChrCtgs) ? supportChrCtgs : [])
      .map((ctg) => [normalizeSupportDatasetId(ctg?.assemblyCtgId), ctg])
      .filter(([assemblyCtgId]) => assemblyCtgId),
  );
  return normalizeSupportMirroredCtgs(supportMirroredCtgs)
    .filter((entry) => !targetChrName || !entry.chrName || entry.chrName === targetChrName)
    .filter((entry) => !deletedAssemblyCtgIds.has(entry.assemblyCtgId))
    .map((entry) => {
      const liveCtg = activeSupportDatasetId !== null && entry.datasetId === activeSupportDatasetId
        ? liveSupportById.get(entry.assemblyCtgId) || null
        : null;
      const source = liveCtg || entry;
      const totalLength = Math.max(
        1,
        normalizeNonNegativeInt(source?.totalLength)
          ?? normalizeNonNegativeInt(source?.lengthBp)
          ?? entry.totalLength
          ?? 1,
      );
      const lengthBp = Math.max(
        1,
        normalizeNonNegativeInt(source?.lengthBp)
          ?? normalizeNonNegativeInt(source?.totalLength)
          ?? totalLength,
      );
      const startBp = Math.max(0, normalizeNonNegativeInt(source?.startBp) ?? entry.startBp ?? 0);
      return {
        ...entry,
        name: String(source?.name || entry.name || `Ctg${entry.assemblyCtgId}`),
        totalLength,
        anchorStart: normalizeNonNegativeInt(source?.anchorStart ?? entry.anchorStart),
        lengthBp,
        startBp,
        endBp: Math.max(
          1,
          normalizeNonNegativeInt(source?.endBp)
            ?? (startBp + lengthBp - 1),
        ),
        laneIndex: Math.max(0, normalizeNonNegativeInt(source?.laneIndex) ?? entry.laneIndex ?? 0),
        hits: liveCtg && Array.isArray(liveCtg?.hits) ? cloneHits(liveCtg.hits) : cloneHits(entry.hits),
        subviewSource: "mirror",
      };
    })
    .filter((entry) => filterSupportCtgsBySupportDsCtgLenRules([entry], {
      rules: supportDsCtgLenRules,
      defaultSupportDsCtgLen: minSupportLengthBp,
      chrLength: supportDsCtgLenRulesChrLength,
    }).length > 0);
}

export function buildSupportSubviewCtgPool({
  supportChrCtgs,
  supportMirroredCtgs,
  supportDatasetId = null,
  selectedChrName = "",
  deletedCtgs = [],
  minSupportLengthBp = 0,
  supportDsCtgLenRules = [],
  supportDsCtgLenRulesChrLength = null,
}) {
  const deletedAssemblyCtgIds = buildDeletedAssemblyCtgIdSet(deletedCtgs);
  const merged = new Map();
  filterSupportCtgsBySupportDsCtgLenRules(
    filterDeletedAssemblyCtgs(supportChrCtgs, deletedAssemblyCtgIds),
    {
      rules: supportDsCtgLenRules,
      defaultSupportDsCtgLen: minSupportLengthBp,
      chrLength: supportDsCtgLenRulesChrLength,
    },
  ).forEach((ctg) => {
    const assemblyCtgId = normalizeSupportDatasetId(ctg?.assemblyCtgId);
    if (!assemblyCtgId) {
      return;
    }
    merged.set(assemblyCtgId, {
      ...ctg,
      subviewSource: "mother",
    });
  });
  buildSupportMirrorCtgPool({
    supportChrCtgs,
    supportMirroredCtgs,
    supportDatasetId,
    selectedChrName,
    deletedCtgs,
    minSupportLengthBp,
    supportDsCtgLenRules,
  })
    .forEach((entry) => {
      if (merged.has(entry.assemblyCtgId)) {
        return;
      }
      merged.set(entry.assemblyCtgId, {
        ...entry,
        subviewSource: "mirror",
      });
    });
  return Array.from(merged.values());
}

export function buildPhasedSubviewCtgPool({ phasedChrTracks = [], primaryCtgs = [], deletedCtgs = [] } = {}) {
  const deletedAssemblyCtgIds = buildDeletedAssemblyCtgIdSet(deletedCtgs);
  const primaryById = new Map(
    (Array.isArray(primaryCtgs) ? primaryCtgs : [])
      .map((ctg) => [normalizeSupportDatasetId(ctg?.assemblyCtgId), ctg])
      .filter(([assemblyCtgId]) => assemblyCtgId),
  );
  return (Array.isArray(phasedChrTracks) ? phasedChrTracks : [])
    .flatMap((track) => {
      const phasedTrackId = normalizeSupportDatasetId(track?.phasedTrackId);
      const haplotypeKey = String(track?.haplotypeKey || "").trim();
      return (Array.isArray(track?.items) ? track.items : [])
        .map((item) => {
          const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId);
          if (!phasedTrackId || !assemblyCtgId || deletedAssemblyCtgIds.has(assemblyCtgId)) {
            return null;
          }
          const source = item?.sourceCtg || primaryById.get(assemblyCtgId) || item;
          const totalLength = Math.max(
            1,
            normalizeNonNegativeInt(source?.totalLength ?? source?.lengthBp) ?? 1,
          );
          const lengthBp = Math.max(
            1,
            normalizeNonNegativeInt(source?.lengthBp ?? source?.totalLength) ?? totalLength,
          );
          const startBp = Math.max(
            0,
            normalizeNonNegativeInt(source?.startBp ?? source?.anchorStart) ?? 0,
          );
          const rawItemOrient = String(item?.orient || "").trim();
          const sourceOrient = resolveSubviewCtgOrientValue(source);
          const itemOrient = rawItemOrient === "-" || rawItemOrient === "+"
            ? rawItemOrient
            : sourceOrient;
          return {
            ...source,
            assemblyCtgId,
            orient: itemOrient,
            refOrient: itemOrient,
            ref_orient: itemOrient,
            phasedTrackId,
            phasedTrackItemId: normalizeSupportDatasetId(item?.itemId ?? item?.phasedTrackItemId),
            phasedHaplotypeKey: haplotypeKey,
            displayOrder: Number(item?.displayOrder || 0),
            totalLength,
            lengthBp,
            startBp,
            endBp: Math.max(
              1,
              normalizeNonNegativeInt(source?.endBp) ?? (startBp + lengthBp - 1),
            ),
            laneIndex: Math.max(0, normalizeNonNegativeInt(source?.laneIndex) ?? 0),
            hits: buildPhasedSubviewCtgHits({ sourceCtg: source, totalLength, itemOrient }),
            subviewPhasedOrientFlipped: itemOrient !== sourceOrient,
            subviewSource: "phased",
          };
        })
        .filter((item) => item);
    });
}

function containsAssemblyCtgId(primaryCtgs, supportCtgs, assemblyCtgId) {
  const targetId = Number(assemblyCtgId || 0);
  if (!targetId) {
    return false;
  }
  return [...(Array.isArray(primaryCtgs) ? primaryCtgs : []), ...(Array.isArray(supportCtgs) ? supportCtgs : [])]
    .some((ctg) => Number(ctg?.assemblyCtgId || 0) === targetId);
}

export function buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
  const normalizedTrackRole = normalizeSubviewTrackRole(trackRole);
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  if (!normalizedTrackRole || !normalizedContigId) {
    return "";
  }
  return `${normalizedTrackRole}:${normalizedContigId}`;
}

export function buildSubviewFlippedCtgKey(slot, contigId) {
  const normalizedSlot = String(slot || "").trim().toLowerCase();
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  if ((normalizedSlot !== "top" && normalizedSlot !== "bottom") || !normalizedContigId) {
    return "";
  }
  return `${normalizedSlot}:${normalizedContigId}`;
}

function normalizeSubviewMode(mode) {
  return String(mode || "").trim() === "track-pair" ? "track-pair" : "2-contig";
}

export function normalizeSubviewRole(role) {
  const normalized = String(role || "").trim();
  if (normalized === "support" || normalized === "primary" || normalized === "ref" || normalized === "phased") {
    return normalized;
  }
  return "";
}

function normalizeSubviewCandidateSelectionItem(selection) {
  const contigId = normalizeSupportDatasetId(selection?.contigId);
  const role = normalizeSubviewRole(selection?.role);
  if (!contigId || !role) {
    return null;
  }
  const normalized = {
    contigId,
    role,
  };
  if (role === "phased") {
    const phasedTrackId = normalizeSupportDatasetId(selection?.phasedTrackId);
    const phasedTrackItemId = normalizeSupportDatasetId(selection?.phasedTrackItemId);
    const phasedHaplotypeKey = String(
      selection?.phasedHaplotypeKey ?? selection?.haplotypeKey ?? "",
    ).trim();
    if (phasedTrackId !== null) {
      normalized.phasedTrackId = phasedTrackId;
    }
    if (phasedTrackItemId !== null) {
      normalized.phasedTrackItemId = phasedTrackItemId;
    }
    if (phasedHaplotypeKey) {
      normalized.phasedHaplotypeKey = phasedHaplotypeKey;
    }
  }
  return normalized;
}

export function buildSubviewCandidateSelectionKey(selection) {
  const normalizedSelection = normalizeSubviewCandidateSelectionItem(selection);
  if (!normalizedSelection) {
    return "";
  }
  if (normalizedSelection.role !== "phased") {
    return `${normalizedSelection.role}:${normalizedSelection.contigId}`;
  }
  return [
    normalizedSelection.role,
    normalizedSelection.contigId,
    normalizedSelection.phasedTrackItemId || 0,
    normalizedSelection.phasedTrackId || 0,
    normalizedSelection.phasedHaplotypeKey || "",
  ].join(":");
}

export function normalizeSubviewTrackRole(role) {
  return normalizeTrackRole(role);
}

export function normalizeSubviewTrackSource(source) {
  return String(source || "").trim() === "mirror" ? "mirror" : "mother";
}

export function normalizeSubviewTrackSelectionItem(item) {
  const role = normalizeSubviewTrackRole(item?.role || item);
  if (!role) {
    return null;
  }
  if (role === "phased") {
    return {
      role,
      source: "mother",
      datasetId: null,
      isMirror: false,
      phasedTrackId: normalizeSupportDatasetId(item?.phasedTrackId),
      haplotypeKey: String(item?.haplotypeKey || item?.phasedHaplotypeKey || "").trim(),
    };
  }
  if (role !== "support") {
    return {
      role,
      source: "mother",
      datasetId: null,
      isMirror: false,
    };
  }
  const mirrorFlag = normalizeBoolean(item?.isMirror) === true;
  const source = mirrorFlag ? "mirror" : normalizeSubviewTrackSource(item?.source);
  return {
    role,
    source,
    datasetId: normalizeSupportDatasetId(item?.datasetId),
    isMirror: source === "mirror",
  };
}

export function buildSubviewTrackSelectionKey(selection) {
  const normalizedSelection = normalizeSubviewTrackSelectionItem(selection);
  if (!normalizedSelection) {
    return "";
  }
  if (normalizedSelection.role !== "support") {
    if (normalizedSelection.role === "phased") {
      return `${normalizedSelection.role}:${normalizedSelection.phasedTrackId || 0}:${normalizedSelection.haplotypeKey || ""}`;
    }
    return normalizedSelection.role;
  }
  const datasetToken = normalizedSelection.datasetId === null ? "0" : String(normalizedSelection.datasetId);
  return `${normalizedSelection.role}:${normalizedSelection.source}:${datasetToken}`;
}

export function normalizeSubviewTrackSelections(values) {
  const normalizedMap = new Map();
  (Array.isArray(values) ? values : []).forEach((item) => {
    const normalizedItem = normalizeSubviewTrackSelectionItem(item);
    if (!normalizedItem) {
      return;
    }
    const key = buildSubviewTrackSelectionKey(normalizedItem);
    if (!key) {
      return;
    }
    normalizedMap.set(key, normalizedItem);
  });
  const normalizedList = Array.from(normalizedMap.values());
  if (normalizedList.length <= 2) {
    return normalizedList;
  }
  return normalizedList.slice(normalizedList.length - 2);
}

export function getSubviewSelections(subview) {
  const selections = [];
  const selectedAContigId = normalizeSupportDatasetId(subview?.selectedAContigId);
  const selectedARole =
    normalizeSubviewRole(subview?.selectedARole) || (selectedAContigId ? "primary" : "");
  const selectedBContigId = normalizeSupportDatasetId(subview?.selectedBContigId);
  const selectedBRole =
    normalizeSubviewRole(subview?.selectedBRole) || (selectedBContigId ? "support" : "");
  if (selectedAContigId && selectedARole) {
    selections.push(normalizeSubviewCandidateSelectionItem({
      contigId: selectedAContigId,
      role: selectedARole,
      phasedTrackId: subview?.selectedAPhasedTrackId,
      phasedTrackItemId: subview?.selectedAPhasedTrackItemId,
      phasedHaplotypeKey: subview?.selectedAPhasedHaplotypeKey,
    }));
  }
  if (selectedBContigId && selectedBRole) {
    selections.push(normalizeSubviewCandidateSelectionItem({
      contigId: selectedBContigId,
      role: selectedBRole,
      phasedTrackId: subview?.selectedBPhasedTrackId,
      phasedTrackItemId: subview?.selectedBPhasedTrackItemId,
      phasedHaplotypeKey: subview?.selectedBPhasedHaplotypeKey,
    }));
  }
  return selections.filter(Boolean);
}

export function getSubviewTrackSelections(subview) {
  const explicitSelections = normalizeSubviewTrackSelections(subview?.selectedTrackSelections);
  if (explicitSelections.length) {
    return explicitSelections;
  }
  const selections = [];
  const selectedTrackARole = normalizeSubviewTrackRole(subview?.selectedTrackARole);
  const selectedTrackBRole = normalizeSubviewTrackRole(subview?.selectedTrackBRole);
  const supportSelectionMeta = {
    source: normalizeSubviewTrackSource(subview?.selectedTrackBSource),
    datasetId: normalizeSupportDatasetId(subview?.selectedTrackBDatasetId),
    isMirror: normalizeBoolean(subview?.selectedTrackBIsMirror) === true,
  };
  if (selectedTrackARole) {
    selections.push(
      selectedTrackARole === "support"
        ? {
            role: selectedTrackARole,
            ...supportSelectionMeta,
          }
        : { role: selectedTrackARole },
    );
  }
  if (selectedTrackBRole) {
    selections.push(
      selectedTrackBRole === "support"
        ? {
            role: selectedTrackBRole,
            ...supportSelectionMeta,
          }
        : { role: selectedTrackBRole },
    );
  }
  return normalizeSubviewTrackSelections(selections);
}

export function applySubviewSelections(subview, selections) {
  const slotA = selections[0] || null;
  const slotB = selections[1] || null;
  return {
    ...subview,
    selectedAContigId: slotA ? slotA.contigId : null,
    selectedARole: slotA ? slotA.role : "",
    selectedAPhasedTrackId: slotA?.role === "phased" ? (slotA.phasedTrackId ?? null) : null,
    selectedAPhasedTrackItemId: slotA?.role === "phased" ? (slotA.phasedTrackItemId ?? null) : null,
    selectedAPhasedHaplotypeKey: slotA?.role === "phased" ? (slotA.phasedHaplotypeKey || "") : "",
    selectedBContigId: slotB ? slotB.contigId : null,
    selectedBRole: slotB ? slotB.role : "",
    selectedBPhasedTrackId: slotB?.role === "phased" ? (slotB.phasedTrackId ?? null) : null,
    selectedBPhasedTrackItemId: slotB?.role === "phased" ? (slotB.phasedTrackItemId ?? null) : null,
    selectedBPhasedHaplotypeKey: slotB?.role === "phased" ? (slotB.phasedHaplotypeKey || "") : "",
  };
}

export function applySubviewTrackSelections(subview, selections) {
  const uniqueSelections = normalizeSubviewTrackSelections(selections);
  const first = uniqueSelections[0] || null;
  const second = uniqueSelections[1] || null;
  const supportSelection = uniqueSelections.find((entry) => entry.role === "support") || null;
  return {
    ...subview,
    selectedTrackSelections: uniqueSelections,
    selectedTrackARole: first?.role || "",
    selectedTrackBRole: second?.role || "",
    selectedTrackBSource: supportSelection?.source || "",
    selectedTrackBDatasetId: supportSelection?.datasetId || null,
    selectedTrackBIsMirror: supportSelection?.isMirror === true,
  };
}

export function normalizeSubviewSummarySelection(selection) {
  return normalizeSubviewCandidateSelectionItem(selection);
}

export function normalizeSubviewTrackSummary(selection) {
  return normalizeSubviewTrackSelectionItem(selection);
}

export function getSubviewState(assembly) {
  const subview = assembly?.subview || {};
  const selectedAContigId = normalizeSupportDatasetId(subview.selectedAContigId);
  const selectedBContigId = normalizeSupportDatasetId(subview.selectedBContigId);
  const selectedAPhasedTrackId = normalizeSupportDatasetId(subview.selectedAPhasedTrackId);
  const selectedAPhasedTrackItemId = normalizeSupportDatasetId(subview.selectedAPhasedTrackItemId);
  const selectedAPhasedHaplotypeKey = String(subview.selectedAPhasedHaplotypeKey || "").trim();
  const selectedBPhasedTrackId = normalizeSupportDatasetId(subview.selectedBPhasedTrackId);
  const selectedBPhasedTrackItemId = normalizeSupportDatasetId(subview.selectedBPhasedTrackItemId);
  const selectedBPhasedHaplotypeKey = String(subview.selectedBPhasedHaplotypeKey || "").trim();
  const explicitTrackSelections = normalizeSubviewTrackSelections(subview.selectedTrackSelections);
  const legacyTrackSelections = normalizeSubviewTrackSelections([
    subview.selectedTrackARole
      ? {
          role: subview.selectedTrackARole,
          source: subview.selectedTrackBSource,
          datasetId: subview.selectedTrackBDatasetId,
          isMirror: subview.selectedTrackBIsMirror,
        }
      : null,
    subview.selectedTrackBRole
      ? {
          role: subview.selectedTrackBRole,
          source: subview.selectedTrackBSource,
          datasetId: subview.selectedTrackBDatasetId,
          isMirror: subview.selectedTrackBIsMirror,
        }
      : null,
  ]);
  const selectedTrackSelections = explicitTrackSelections.length
    ? explicitTrackSelections
    : legacyTrackSelections;
  const firstTrackSelection = selectedTrackSelections[0] || null;
  const secondTrackSelection = selectedTrackSelections[1] || null;
  const supportTrackSelection = selectedTrackSelections.find((entry) => entry.role === "support") || null;
  const selectedARole = normalizeSubviewRole(subview.selectedARole) || (selectedAContigId ? "primary" : "");
  const selectedBRole = normalizeSubviewRole(subview.selectedBRole) || (selectedBContigId ? "support" : "");
  const normalized = {
    mode: normalizeSubviewMode(subview.mode),
    selectedAContigId,
    selectedARole,
    selectedBContigId,
    selectedBRole,
    selectedTrackSelections,
    selectedTrackARole: firstTrackSelection?.role || "",
    selectedTrackBRole: secondTrackSelection?.role || "",
    selectedTrackBSource: supportTrackSelection?.source || "",
    selectedTrackBDatasetId: supportTrackSelection?.datasetId || null,
    selectedTrackBIsMirror: supportTrackSelection?.isMirror === true,
    activeAnchors: normalizeSubviewActiveAnchors(subview.activeAnchors),
    manualAnchors: normalizeSubviewManualAnchors(subview.manualAnchors),
    flippedCtgs: normalizeSubviewFlippedCtgs(subview.flippedCtgs),
    trackPairHiddenCtgs: normalizeSubviewTrackPairHiddenCtgs(subview.trackPairHiddenCtgs),
    trackPairSelectedCtgs: normalizeSubviewTrackPairSelectionCtgs(subview.trackPairSelectedCtgs),
    message: String(subview.message || ""),
    error: String(subview.error || ""),
    summary: subview.summary || null,
  };
  if (subview.pairwiseEvidence) {
    normalized.pairwiseEvidence = subview.pairwiseEvidence;
  }
  if (
    selectedARole === "phased"
    || selectedAPhasedTrackId !== null
    || selectedAPhasedTrackItemId !== null
    || selectedAPhasedHaplotypeKey
  ) {
    normalized.selectedAPhasedTrackId = selectedAPhasedTrackId;
    normalized.selectedAPhasedTrackItemId = selectedAPhasedTrackItemId;
    normalized.selectedAPhasedHaplotypeKey = selectedAPhasedHaplotypeKey;
  }
  if (
    selectedBRole === "phased"
    || selectedBPhasedTrackId !== null
    || selectedBPhasedTrackItemId !== null
    || selectedBPhasedHaplotypeKey
  ) {
    normalized.selectedBPhasedTrackId = selectedBPhasedTrackId;
    normalized.selectedBPhasedTrackItemId = selectedBPhasedTrackItemId;
    normalized.selectedBPhasedHaplotypeKey = selectedBPhasedHaplotypeKey;
  }
  return normalized;
}

export function normalizeSubviewFlippedCtgs(values) {
  const normalizedMap = new Map();
  (Array.isArray(values) ? values : []).forEach((item) => {
    const slot = String(item?.slot || "").trim().toLowerCase();
    const contigId = normalizeSupportDatasetId(item?.contigId);
    const key = buildSubviewFlippedCtgKey(slot, contigId);
    if (!key) {
      return;
    }
    normalizedMap.set(key, {
      slot,
      contigId,
    });
  });
  return Array.from(normalizedMap.values()).sort((left, right) =>
    buildSubviewFlippedCtgKey(left.slot, left.contigId)
      .localeCompare(buildSubviewFlippedCtgKey(right.slot, right.contigId)),
  );
}

function swapSubviewFlippedCtgSlots(values) {
  return normalizeSubviewFlippedCtgs(values).map((entry) => ({
    ...entry,
    slot: entry.slot === "top" ? "bottom" : "top",
  }));
}

export function normalizeSubviewTrackPairHiddenCtgs(values) {
  const normalizedMap = new Map();
  (Array.isArray(values) ? values : []).forEach((item) => {
    const trackRole = normalizeSubviewTrackRole(item?.trackRole);
    const contigId = normalizeSupportDatasetId(item?.contigId);
    const key = buildSubviewTrackPairHiddenCtgKey(trackRole, contigId);
    if (!key) {
      return;
    }
    normalizedMap.set(key, {
      trackRole,
      contigId,
    });
  });
  return Array.from(normalizedMap.values()).sort((left, right) => {
    const leftKey = buildSubviewTrackPairHiddenCtgKey(left.trackRole, left.contigId);
    const rightKey = buildSubviewTrackPairHiddenCtgKey(right.trackRole, right.contigId);
    return leftKey.localeCompare(rightKey);
  });
}

export function normalizeSubviewTrackPairSelectionCtgs(values) {
  return normalizeSubviewTrackPairHiddenCtgs(values);
}

export function resolveSubviewCtgOrder(ctg) {
  const chrOrder = Number(ctg?.order);
  if (Number.isFinite(chrOrder) && chrOrder >= 0) {
    return chrOrder;
  }
  const anchorStart = Number(ctg?.anchorStart);
  if (Number.isFinite(anchorStart) && anchorStart >= 0) {
    return anchorStart;
  }
  return Number.MAX_SAFE_INTEGER;
}

function comparePhasedSubviewCtgsByVisualOrder(left, right) {
  const leftOrder = resolveSubviewCtgOrder(left);
  const rightOrder = resolveSubviewCtgOrder(right);
  if (leftOrder !== rightOrder) {
    return leftOrder - rightOrder;
  }
  const leftDisplayOrder = Number(left?.displayOrder || 0);
  const rightDisplayOrder = Number(right?.displayOrder || 0);
  if (leftDisplayOrder !== rightDisplayOrder) {
    return leftDisplayOrder - rightDisplayOrder;
  }
  const leftItemId = normalizeSupportDatasetId(left?.phasedTrackItemId);
  const rightItemId = normalizeSupportDatasetId(right?.phasedTrackItemId);
  if (leftItemId !== rightItemId) {
    return (leftItemId || 0) - (rightItemId || 0);
  }
  return (normalizeSupportDatasetId(left?.assemblyCtgId) || 0)
    - (normalizeSupportDatasetId(right?.assemblyCtgId) || 0);
}

export function resolveSubviewSelectionCtg(selection, { primaryCtgs, supportCtgs, refCtgs, phasedCtgs } = {}) {
  const normalizedSelection = normalizeSubviewSummarySelection(selection);
  if (!normalizedSelection) {
    return null;
  }
  const pool = normalizedSelection.role === "support"
    ? supportCtgs
    : normalizedSelection.role === "ref"
      ? refCtgs
      : normalizedSelection.role === "phased"
        ? phasedCtgs
        : primaryCtgs;
  if (normalizedSelection.role === "phased") {
    const list = Array.isArray(pool) ? pool : [];
    const phasedTrackItemId = normalizeSupportDatasetId(normalizedSelection.phasedTrackItemId);
    if (phasedTrackItemId !== null) {
      const matchedItem = list.find(
        (ctg) =>
          Number(ctg?.assemblyCtgId || 0) === normalizedSelection.contigId
          && normalizeSupportDatasetId(ctg?.phasedTrackItemId) === phasedTrackItemId,
      );
      if (matchedItem) {
        return matchedItem;
      }
    }
    const phasedTrackId = normalizeSupportDatasetId(normalizedSelection.phasedTrackId);
    const phasedHaplotypeKey = String(normalizedSelection.phasedHaplotypeKey || "").trim();
    if (phasedTrackId !== null || phasedHaplotypeKey) {
      const matchedTrack = list.find((ctg) => {
        if (Number(ctg?.assemblyCtgId || 0) !== normalizedSelection.contigId) {
          return false;
        }
        if (phasedTrackId !== null && normalizeSupportDatasetId(ctg?.phasedTrackId) !== phasedTrackId) {
          return false;
        }
        if (phasedHaplotypeKey && String(ctg?.phasedHaplotypeKey || "").trim() !== phasedHaplotypeKey) {
          return false;
        }
        return true;
      });
      if (matchedTrack) {
        return matchedTrack;
      }
    }
  }
  return (Array.isArray(pool) ? pool : []).find(
    (ctg) => Number(ctg?.assemblyCtgId || 0) === normalizedSelection.contigId,
  ) || null;
}

function isDatasetSelfAlignmentAvailable(datasets, datasetId) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
  if (normalizedDatasetId === null) {
    return true;
  }
  const matched = (Array.isArray(datasets) ? datasets : []).find(
    (dataset) => normalizeSupportDatasetId(dataset?.datasetId) === normalizedDatasetId,
  );
  if (!matched) {
    return true;
  }
  return matched.selfAlignmentAvailable !== false && matched.selfAlignmentAvailable !== "false";
}

function resolveSubviewCandidateDatasetId(selection, ctg, { primaryDatasetId = null, supportDatasetId = null }) {
  const ctgDatasetId = normalizeSupportDatasetId(ctg?.datasetId);
  if (ctgDatasetId !== null) {
    return ctgDatasetId;
  }
  const normalizedSelection = normalizeSubviewSummarySelection(selection);
  if (normalizedSelection?.role === "ref") {
    return null;
  }
  if (normalizedSelection?.role === "primary" || normalizedSelection?.role === "phased") {
    return normalizeSupportDatasetId(primaryDatasetId);
  }
  if (normalizedSelection?.role === "support") {
    return normalizeSupportDatasetId(supportDatasetId);
  }
  return null;
}

function resolveSubviewTrackSummaryDatasetScope({
  datasets = [],
  primaryDatasetId = null,
  stateOrLocale = "zh",
} = {}) {
  const state = stateOrLocale && typeof stateOrLocale === "object" ? stateOrLocale : null;
  const normalizedDatasets = Array.isArray(datasets) && datasets.length
    ? datasets
    : (Array.isArray(state?.initializer?.datasets) ? state.initializer.datasets : []);
  const normalizedPrimaryDatasetId = normalizeSupportDatasetId(primaryDatasetId);
  if (normalizedPrimaryDatasetId !== null) {
    return {
      datasets: normalizedDatasets,
      primaryDatasetId: normalizedPrimaryDatasetId,
    };
  }
  const projects = Array.isArray(state?.initializer?.existingProjects) ? state.initializer.existingProjects : [];
  const projectId = normalizeSupportDatasetId(state?.session?.projectId);
  const matchedProject = projects.find(
    (project) => normalizeSupportDatasetId(project?.projectId) === projectId,
  ) || (projects.length === 1 ? projects[0] : null);
  return {
    datasets: normalizedDatasets,
    primaryDatasetId: normalizeSupportDatasetId(matchedProject?.primaryDatasetId),
  };
}

function resolveSubviewTrackSelectionDatasetId(trackSelection, { primaryDatasetId = null } = {}) {
  const normalizedTrack = normalizeSubviewTrackSummary(trackSelection);
  if (!normalizedTrack || normalizedTrack.role === "ref") {
    return null;
  }
  if (normalizedTrack.role === "primary" || normalizedTrack.role === "phased") {
    return normalizeSupportDatasetId(primaryDatasetId);
  }
  if (normalizedTrack.role === "support") {
    return normalizeSupportDatasetId(normalizedTrack.datasetId);
  }
  return null;
}

export function resolveSubviewTrackSummaryCtgs(
  trackSelection,
  {
    primaryCtgs,
    supportCtgs,
    supportMirrorCtgs,
    refCtgs,
    phasedCtgs,
  },
) {
  const normalizedTrack = normalizeSubviewTrackSummary(trackSelection);
  if (!normalizedTrack) {
    return [];
  }
  if (normalizedTrack.role === "ref") {
    return Array.isArray(refCtgs) ? refCtgs : [];
  }
  if (normalizedTrack.role === "phased") {
    const phasedList = Array.isArray(phasedCtgs) ? phasedCtgs : [];
    const normalizedPhasedTrackId = normalizeSupportDatasetId(normalizedTrack.phasedTrackId);
    if (normalizedPhasedTrackId !== null) {
      return phasedList.filter(
        (ctg) => normalizeSupportDatasetId(ctg?.phasedTrackId) === normalizedPhasedTrackId,
      ).sort(comparePhasedSubviewCtgsByVisualOrder);
    }
    return phasedList.slice().sort((left, right) => {
      const leftTrackId = normalizeSupportDatasetId(left?.phasedTrackId) || 0;
      const rightTrackId = normalizeSupportDatasetId(right?.phasedTrackId) || 0;
      if (leftTrackId !== rightTrackId) {
        return leftTrackId - rightTrackId;
      }
      return comparePhasedSubviewCtgsByVisualOrder(left, right);
    });
  }
  if (normalizedTrack.role !== "support") {
    return Array.isArray(primaryCtgs) ? primaryCtgs : [];
  }
  if (normalizedTrack.source === "mirror" || normalizedTrack.isMirror) {
    const mirrorList = Array.isArray(supportMirrorCtgs) ? supportMirrorCtgs : [];
    const normalizedMirrorDatasetId = normalizeSupportDatasetId(normalizedTrack.datasetId);
    if (normalizedMirrorDatasetId !== null) {
      return mirrorList.filter(
        (ctg) => normalizeSupportDatasetId(ctg?.datasetId) === normalizedMirrorDatasetId,
      );
    }
    return mirrorList;
  }
  const motherList = Array.isArray(supportCtgs) ? supportCtgs : [];
  const normalizedMotherDatasetId = normalizeSupportDatasetId(normalizedTrack.datasetId);
  return motherList.filter((ctg) => {
    if (String(ctg?.subviewSource || "mother") === "mirror") {
      return false;
    }
    if (normalizedMotherDatasetId === null) {
      return true;
    }
    const ctgDatasetId = normalizeSupportDatasetId(ctg?.datasetId);
    return ctgDatasetId === null || ctgDatasetId === normalizedMotherDatasetId;
  });
}

export function resolveSubviewTrackRoleCtgs(
  trackRole,
  {
    primaryCtgs,
    supportCtgs,
    supportMirrorCtgs,
    refCtgs,
    phasedCtgs,
    supportTrackSource = "mother",
    supportMirrorDatasetId = null,
  },
) {
  return resolveSubviewTrackSummaryCtgs(
    {
      role: trackRole,
      source: supportTrackSource,
      datasetId: supportMirrorDatasetId,
      isMirror: supportTrackSource === "mirror",
    },
    {
      primaryCtgs,
      supportCtgs,
      supportMirrorCtgs,
      refCtgs,
      phasedCtgs,
    },
  );
}

export function filterSubviewTrackPairHiddenCtgs(values, { primaryCtgs, supportCtgs, supportMirrorCtgs, refCtgs, phasedCtgs }) {
  return normalizeSubviewTrackPairHiddenCtgs(values).filter((entry) => {
    const pool = resolveSubviewTrackRoleCtgs(entry.trackRole, {
      primaryCtgs,
      supportCtgs,
      supportMirrorCtgs,
      refCtgs,
      phasedCtgs,
    });
    if (containsAssemblyCtgId(pool, [], entry.contigId)) {
      return true;
    }
    return normalizeSubviewTrackRole(entry.trackRole) === "support"
      && containsAssemblyCtgId(supportMirrorCtgs, [], entry.contigId);
  });
}

export function filterSubviewTrackPairSelectionCtgs(values, { primaryCtgs, supportCtgs, supportMirrorCtgs, refCtgs, phasedCtgs }) {
  return normalizeSubviewTrackPairSelectionCtgs(values).filter((entry) => {
    const pool = resolveSubviewTrackRoleCtgs(entry.trackRole, {
      primaryCtgs,
      supportCtgs,
      supportMirrorCtgs,
      refCtgs,
      phasedCtgs,
    });
    if (containsAssemblyCtgId(pool, [], entry.contigId)) {
      return true;
    }
    return normalizeSubviewTrackRole(entry.trackRole) === "support"
      && containsAssemblyCtgId(supportMirrorCtgs, [], entry.contigId);
  });
}

function filterRefTrackHitsByDataset(hits, datasetId = null) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
  const list = Array.isArray(hits) ? hits : [];
  if (normalizedDatasetId === null) {
    return list.map((hit) => ({ ...hit }));
  }
  return list
    .filter((hit) => normalizeSupportDatasetId(hit?.datasetId) === normalizedDatasetId)
    .map((hit) => ({ ...hit }));
}

function resolveSubviewSummaryRefDatasetId(subviewSummary, { primaryDatasetId = null } = {}) {
  if (String(subviewSummary?.mode || "").trim() !== "track-pair") {
    return null;
  }
  const trackSelections = [subviewSummary?.topTrack, subviewSummary?.bottomTrack]
    .map((track) => normalizeSubviewTrackSummary(track))
    .filter(Boolean);
  const nonRefTrack = trackSelections.find((track) => track.role !== "ref");
  if (!nonRefTrack) {
    return null;
  }
  if (nonRefTrack.role === "primary" || nonRefTrack.role === "phased") {
    return normalizeSupportDatasetId(primaryDatasetId);
  }
  return normalizeSupportDatasetId(nonRefTrack.datasetId);
}

export function buildRefSubviewCtgPool(refTrackMembers, { datasetId = null } = {}) {
  return (Array.isArray(refTrackMembers) ? refTrackMembers : [])
    .map((item) => {
      const assemblyCtgId = normalizeSupportDatasetId(item?.assemblyCtgId);
      if (!assemblyCtgId) {
        return null;
      }
      const segmentStartBp = Math.max(1, Number(item?.segmentStartBp || item?.anchorStart || 1));
      const totalLength = Math.max(1, Number(item?.totalLength || item?.lengthBp || 1));
      const segmentEndBp = Math.max(
        segmentStartBp,
        Number(item?.segmentEndBp || item?.endBp || (segmentStartBp + totalLength - 1)),
      );
      return {
        ...item,
        assemblyCtgId,
        sourceKind: String(item?.sourceKind || "ref_segment"),
        name: String(item?.name || `ref:${segmentStartBp}-${segmentEndBp}`),
        anchorStart: segmentStartBp,
        totalLength,
        lengthBp: Math.max(1, Number(item?.lengthBp || totalLength)),
        startBp: segmentStartBp,
        endBp: segmentEndBp,
        refOrient: String(item?.refOrient || "+") === "-" ? "-" : "+",
        hits: filterRefTrackHitsByDataset(item?.hits, datasetId),
        subviewSource: "mother",
      };
    })
    .filter((item) => item);
}

export function buildSubviewTrackPairPoolsFromAssembly(assembly) {
  const deletedCtgs = Array.isArray(assembly?.deletedCtgs) ? assembly.deletedCtgs : [];
  const trackPrefs = resolveTrackPrefs(assembly?.trackView);
  const minSupportLengthBp = Math.max(0, normalizeNonNegativeInt(trackPrefs?.supportDsCtgLen) ?? 0);
  const selectedChrName = String(assembly?.selectedChrName || "").trim();
  const chrLengthsByName = buildChrLengthsByName(assembly?.chromosomes);
  const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
    assembly?.supportDsCtgLenRulesByChr,
    selectedChrName,
    { chrLength: chrLengthsByName[selectedChrName] },
  );
  const supportMirrorCtgs = buildSupportMirrorCtgPool({
    supportChrCtgs: assembly?.supportChrCtgs || [],
    supportMirroredCtgs: assembly?.supportMirroredCtgs || [],
    supportDatasetId: assembly?.supportDatasetId,
    selectedChrName,
    deletedCtgs,
    minSupportLengthBp,
    supportDsCtgLenRules,
    supportDsCtgLenRulesChrLength: chrLengthsByName[selectedChrName],
  });
  const refDatasetId = resolveSubviewSummaryRefDatasetId(assembly?.subview?.summary, {
    primaryDatasetId: assembly?.primaryDatasetId,
  });
  return {
    primaryCtgs: filterDeletedAssemblyCtgs(assembly?.chrCtgs, buildDeletedAssemblyCtgIdSet(deletedCtgs)),
    supportCtgs: buildSupportSubviewCtgPool({
      supportChrCtgs: assembly?.supportChrCtgs || [],
      supportMirroredCtgs: supportMirrorCtgs,
      supportDatasetId: assembly?.supportDatasetId,
      selectedChrName,
      deletedCtgs,
      minSupportLengthBp,
      supportDsCtgLenRules,
      supportDsCtgLenRulesChrLength: chrLengthsByName[selectedChrName],
    }),
    supportMirrorCtgs,
    phasedCtgs: buildPhasedSubviewCtgPool({
      phasedChrTracks: assembly?.phasedChrTracks || [],
      primaryCtgs: assembly?.chrCtgs || [],
      deletedCtgs,
    }),
    refCtgs: buildRefSubviewCtgPool(assembly?.refTrackMembers || [], { datasetId: refDatasetId }),
  };
}

export function selectSubviewCandidate({
  mode,
  subview,
  trackRole,
  contigId,
  phasedTrackId = null,
  phasedTrackItemId = null,
  phasedHaplotypeKey = "",
  stateOrLocale = "zh",
}) {
  const currentSubview = getSubviewState({
    subview: {
      ...subview,
      mode,
    },
  });
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  const normalizedTrackRole = normalizeSubviewRole(trackRole);
  if (normalizedContigId === null || !normalizedTrackRole) {
    return currentSubview;
  }
  const candidateSelection = normalizeSubviewCandidateSelectionItem({
    contigId: normalizedContigId,
    role: normalizedTrackRole,
    phasedTrackId,
    phasedTrackItemId,
    phasedHaplotypeKey,
  });
  if (!candidateSelection) {
    return currentSubview;
  }
  const candidateKey = buildSubviewCandidateSelectionKey(candidateSelection);

  const selections = getSubviewSelections(currentSubview);
  const existingIndex = selections.findIndex(
    (selection) => buildSubviewCandidateSelectionKey(selection) === candidateKey,
  );
  if (existingIndex >= 0) {
    selections.splice(existingIndex, 1);
  } else {
    selections.push(candidateSelection);
    if (selections.length > 2) {
      selections.shift();
    }
  }
  const nextSubview = applySubviewSelections(currentSubview, selections);
  nextSubview.selectedTrackSelections = [];
  nextSubview.selectedTrackARole = "";
  nextSubview.selectedTrackBRole = "";
  nextSubview.selectedTrackBSource = "";
  nextSubview.selectedTrackBDatasetId = null;
  nextSubview.selectedTrackBIsMirror = false;
  nextSubview.trackPairHiddenCtgs = [];
  nextSubview.trackPairSelectedCtgs = [];
  nextSubview.summary = null;
  nextSubview.error = "";
  nextSubview.message = selections.length
    ? tSubview(stateOrLocale, "selectedContigs", { count: selections.length })
    : "";
  return nextSubview;
}

export function selectSubviewTrack({
  subview,
  trackRole,
  source = "mother",
  datasetId = null,
  isMirror = false,
  phasedTrackId = null,
  haplotypeKey = "",
  stateOrLocale = "zh",
}) {
  const currentSubview = getSubviewState({ subview });
  const normalizedTrackRole = normalizeSubviewTrackRole(trackRole);
  if (!normalizedTrackRole) {
    return currentSubview;
  }
  const candidateSelection = normalizeSubviewTrackSelectionItem({
    role: normalizedTrackRole,
    source,
    datasetId,
    isMirror,
    phasedTrackId,
    haplotypeKey,
  });
  if (!candidateSelection) {
    return currentSubview;
  }
  const candidateKey = buildSubviewTrackSelectionKey(candidateSelection);
  const selections = getSubviewTrackSelections(currentSubview);
  const existingIndex = selections.findIndex(
    (selection) => buildSubviewTrackSelectionKey(selection) === candidateKey,
  );
  if (existingIndex >= 0) {
    selections.splice(existingIndex, 1);
  } else {
    selections.push(candidateSelection);
    if (selections.length > 2) {
      selections.shift();
    }
  }
  const nextSubview = applySubviewTrackSelections(currentSubview, selections);
  nextSubview.selectedAContigId = null;
  nextSubview.selectedARole = "";
  nextSubview.selectedAPhasedTrackId = null;
  nextSubview.selectedAPhasedTrackItemId = null;
  nextSubview.selectedAPhasedHaplotypeKey = "";
  nextSubview.selectedBContigId = null;
  nextSubview.selectedBRole = "";
  nextSubview.selectedBPhasedTrackId = null;
  nextSubview.selectedBPhasedTrackItemId = null;
  nextSubview.selectedBPhasedHaplotypeKey = "";
  nextSubview.trackPairHiddenCtgs = [];
  nextSubview.trackPairSelectedCtgs = [];
  nextSubview.error = "";
  nextSubview.summary = null;
  if (!selections.length) {
    nextSubview.message = "";
    return nextSubview;
  }
  if (selections.length < 2) {
    nextSubview.message = tSubview(stateOrLocale, "selectedTracks", { count: selections.length });
    return nextSubview;
  }
  const result = buildSubviewSummaryFromTrackSelections({ subview: nextSubview, stateOrLocale });
  if (!result.ok) {
    nextSubview.summary = null;
    nextSubview.error = result.error;
    nextSubview.message = tSubview(stateOrLocale, "selectedTracks", { count: selections.length });
    return nextSubview;
  }
  nextSubview.summary = result.value;
  nextSubview.message = tSubview(stateOrLocale, "enteredTrackMode");
  return nextSubview;
}

export function removeSubviewCandidate({
  subview,
  trackRole,
  contigId,
  phasedTrackId = null,
  phasedTrackItemId = null,
  phasedHaplotypeKey = "",
  stateOrLocale = "zh",
}) {
  const currentSubview = getSubviewState({ subview });
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  const normalizedTrackRole = normalizeSubviewRole(trackRole);
  if (normalizedContigId === null || !normalizedTrackRole) {
    return currentSubview;
  }
  const targetSelection = normalizeSubviewCandidateSelectionItem({
    contigId: normalizedContigId,
    role: normalizedTrackRole,
    phasedTrackId,
    phasedTrackItemId,
    phasedHaplotypeKey,
  });
  const targetKey = buildSubviewCandidateSelectionKey(targetSelection);
  const selections = getSubviewSelections(currentSubview).filter(
    (selection) => {
      if (targetKey) {
        return buildSubviewCandidateSelectionKey(selection) !== targetKey;
      }
      return Number(selection.contigId) !== Number(normalizedContigId)
        || selection.role !== normalizedTrackRole;
    },
  );
  const nextSubview = applySubviewSelections(currentSubview, selections);
  nextSubview.summary = null;
  nextSubview.error = "";
  nextSubview.message = selections.length
    ? tSubview(stateOrLocale, "selectedContigs", { count: selections.length })
    : "";
  return nextSubview;
}

export function removeSubviewTrackSelection({
  subview,
  trackRole,
  source,
  datasetId,
  isMirror,
  stateOrLocale = "zh",
}) {
  const currentSubview = getSubviewState({ subview });
  const normalizedTrackRole = normalizeSubviewTrackRole(trackRole);
  if (!normalizedTrackRole) {
    return currentSubview;
  }
  const selections = getSubviewTrackSelections(currentSubview);
  const hasExplicitTrackMeta =
    source !== undefined
    || datasetId !== undefined
    || isMirror !== undefined;
  let nextSelections = selections.slice();
  if (normalizedTrackRole === "support" && hasExplicitTrackMeta) {
    const normalizedTarget = normalizeSubviewTrackSelectionItem({
      role: normalizedTrackRole,
      source,
      datasetId,
      isMirror,
    });
    const targetKey = buildSubviewTrackSelectionKey(normalizedTarget);
    nextSelections = nextSelections.filter(
      (selection) => buildSubviewTrackSelectionKey(selection) !== targetKey,
    );
  } else {
    const removeIndex = nextSelections.findIndex((selection) => selection.role === normalizedTrackRole);
    if (removeIndex >= 0) {
      nextSelections.splice(removeIndex, 1);
    }
  }
  const nextSubview = applySubviewTrackSelections(currentSubview, nextSelections);
  nextSubview.trackPairHiddenCtgs = [];
  nextSubview.trackPairSelectedCtgs = [];
  nextSubview.summary = null;
  nextSubview.error = "";
  nextSubview.message = nextSelections.length
    ? tSubview(stateOrLocale, "selectedTracks", { count: nextSelections.length })
    : "";
  return nextSubview;
}

export function swapSubviewSummaryOrder({ subview, stateOrLocale = "zh" }) {
  const currentSubview = getSubviewState({ subview });
  const summary = currentSubview.summary;
  if (!summary || typeof summary !== "object") {
    return currentSubview;
  }
  if (String(summary.mode || "") === "track-pair") {
    const topTrack = summary.topTrack;
    const bottomTrack = summary.bottomTrack;
    const hasValidTopTrack = Boolean(normalizeSubviewTrackSummary(topTrack));
    const hasValidBottomTrack = Boolean(normalizeSubviewTrackSummary(bottomTrack));
    if (!hasValidTopTrack || !hasValidBottomTrack) {
      return currentSubview;
    }
    return {
      ...currentSubview,
      flippedCtgs: swapSubviewFlippedCtgSlots(currentSubview.flippedCtgs),
      summary: {
        ...summary,
        topTrack: bottomTrack,
        bottomTrack: topTrack,
      },
      error: "",
      message: tSubview(stateOrLocale, "swappedTrackOrder"),
    };
  }
  const top = summary.top;
  const bottom = summary.bottom;
  const hasValidTop = Boolean(normalizeSubviewSummarySelection(top));
  const hasValidBottom = Boolean(normalizeSubviewSummarySelection(bottom));
  if (!hasValidTop || !hasValidBottom) {
    return currentSubview;
  }
  return {
    ...currentSubview,
    flippedCtgs: swapSubviewFlippedCtgSlots(currentSubview.flippedCtgs),
    summary: {
      ...summary,
      top: bottom,
      bottom: top,
    },
    error: "",
    message: tSubview(stateOrLocale, "swappedTrackOrder"),
  };
}

export function buildSubviewSummaryFromCandidates({
  subview,
  primaryCtgs,
  supportCtgs,
  refCtgs,
  phasedCtgs,
  datasets = [],
  primaryDatasetId = null,
  supportDatasetId = null,
  stateOrLocale = "zh",
}) {
  const normalizedSubview = getSubviewState({ subview });
  const selections = getSubviewSelections(normalizedSubview);
  if (selections.length !== 2) {
    return { ok: false, error: tSubview(stateOrLocale, "requiresTwoContigs") };
  }
  const left = resolveSubviewSelectionCtg(selections[0], { primaryCtgs, supportCtgs, refCtgs, phasedCtgs });
  const right = resolveSubviewSelectionCtg(selections[1], { primaryCtgs, supportCtgs, refCtgs, phasedCtgs });
  if (!left || !right) {
    return { ok: false, error: tSubview(stateOrLocale, "candidateExpired") };
  }
  if (
    selections[0].role === "ref"
    && selections[1].role === "ref"
    && Number(selections[0].contigId) === Number(selections[1].contigId)
  ) {
    return { ok: false, error: "同一个 ref 片段不能同时作为 Subview 的两个成员。" };
  }
  const leftDatasetId = resolveSubviewCandidateDatasetId(selections[0], left, {
    primaryDatasetId,
    supportDatasetId,
  });
  const rightDatasetId = resolveSubviewCandidateDatasetId(selections[1], right, {
    primaryDatasetId,
    supportDatasetId,
  });
  if (
    leftDatasetId !== null &&
    rightDatasetId !== null &&
    leftDatasetId === rightDatasetId &&
    !isDatasetSelfAlignmentAvailable(datasets, leftDatasetId)
  ) {
    return { ok: false, error: tSubview(stateOrLocale, "selfAlignmentUnavailable") };
  }

  let top = selections[0];
  let bottom = selections[1];
  if (selections[0].role !== selections[1].role) {
    if (selections[1].role === "support") {
      top = selections[1];
      bottom = selections[0];
    }
  } else {
    const leftOrder = resolveSubviewCtgOrder(left);
    const rightOrder = resolveSubviewCtgOrder(right);
    if (rightOrder < leftOrder) {
      top = selections[1];
      bottom = selections[0];
    }
  }

  return {
    ok: true,
    value: {
      mode: "2-contig",
      top: normalizeSubviewSummarySelection(top),
      bottom: normalizeSubviewSummarySelection(bottom),
    },
  };
}

export function buildSubviewSummaryFromTrackSelections({
  subview,
  datasets = [],
  primaryDatasetId = null,
  stateOrLocale = "zh",
}) {
  const normalizedSubview = getSubviewState({ subview });
  const selections = getSubviewTrackSelections(normalizedSubview);
  if (selections.length !== 2) {
    return { ok: false, error: tSubview(stateOrLocale, "requiresTwoTracks") };
  }
  const datasetScope = resolveSubviewTrackSummaryDatasetScope({
    datasets,
    primaryDatasetId,
    stateOrLocale,
  });
  const topDatasetId = resolveSubviewTrackSelectionDatasetId(selections[0], {
    primaryDatasetId: datasetScope.primaryDatasetId,
  });
  const bottomDatasetId = resolveSubviewTrackSelectionDatasetId(selections[1], {
    primaryDatasetId: datasetScope.primaryDatasetId,
  });
  if (
    topDatasetId !== null &&
    bottomDatasetId !== null &&
    topDatasetId === bottomDatasetId &&
    !isDatasetSelfAlignmentAvailable(datasetScope.datasets, topDatasetId)
  ) {
    return { ok: false, error: tSubview(stateOrLocale, "selfAlignmentUnavailable") };
  }
  const hasSupport = selections.some((selection) => selection.role === "support");
  const hasPrimaryLike = selections.some((selection) => selection.role === "primary" || selection.role === "phased");
  let top = selections[0];
  let bottom = selections[1];
  if (hasSupport && hasPrimaryLike) {
    top = selections.find((selection) => selection.role === "support") || selections[0];
    bottom = selections.find((selection) => selection.role === "primary" || selection.role === "phased") || selections[1];
  }
  return {
    ok: true,
    value: {
      mode: "track-pair",
      topTrack: normalizeSubviewTrackSummary(top),
      bottomTrack: normalizeSubviewTrackSummary(bottom),
    },
  };
}

export function resolveFilteredSubviewTrackPairSelectionsFromAssembly(assembly) {
  const subview = getSubviewState(assembly);
  if (String(subview.summary?.mode || "") !== "track-pair") {
    return [];
  }
  const pools = buildSubviewTrackPairPoolsFromAssembly(assembly);
  const hiddenKeySet = new Set(
    normalizeSubviewTrackPairHiddenCtgs(subview.trackPairHiddenCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  return filterSubviewTrackPairSelectionCtgs(subview.trackPairSelectedCtgs, pools).filter(
    (entry) => !hiddenKeySet.has(buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId)),
  );
}
