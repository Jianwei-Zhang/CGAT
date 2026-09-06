import {
  normalizeSubviewActiveAnchors,
  normalizeSubviewManualAnchors,
} from "./subview-anchor-state.js";
import { normalizeSupportDatasetId } from "./selection-state.js";

export const SUBVIEW_COMPOSITION_MODE = "composition";
export const SUBVIEW_COMPOSITION_DEFAULT_GAP_BP = 20_000;

export function normalizeSubviewCompositionLane(value) {
  return String(value || "").trim().toLowerCase() === "bottom" ? "bottom" : "top";
}

function normalizeOrientation(value) {
  return String(value || "").trim() === "-" ? "-" : "+";
}

function normalizeFiniteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function normalizeNonNegativeOrder(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric >= 0 ? numeric : fallback;
}

function normalizePositiveLength(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.max(1, Math.round(numeric)) : 1;
}

function normalizeReference(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const chrName = String(value.chrName || value.referenceChrName || "").trim();
  const startBp = Math.max(1, Math.round(normalizeFiniteNumber(value.startBp ?? value.segmentStartBp, 1)));
  const endBp = Math.max(startBp, Math.round(normalizeFiniteNumber(
    value.endBp ?? value.segmentEndBp,
    startBp,
  )));
  return chrName ? { chrName, startBp, endBp } : null;
}

export function buildSubviewCompositionEntityKey(value) {
  const assemblyCtgId = normalizeSupportDatasetId(value?.assemblyCtgId ?? value?.contigId);
  if (assemblyCtgId) return `assembly:${assemblyCtgId}`;
  const reference = normalizeReference(value?.reference || value);
  return reference
    ? `ref:${encodeURIComponent(reference.chrName)}:${reference.startBp}-${reference.endBp}`
    : "";
}

export function normalizeSubviewCompositionSource(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const rawRole = String(source.role || "").trim();
  const role = ["primary", "support", "phased", "ref"].includes(rawRole) ? rawRole : "support";
  const sourceType = String(source.sourceType || source.source || "mother").trim() || "mother";
  return {
    role,
    datasetId: normalizeSupportDatasetId(source.datasetId),
    datasetName: String(source.datasetName || "").trim(),
    sourceType,
    phasedTrackId: normalizeSupportDatasetId(source.phasedTrackId),
    phasedItemId: normalizeSupportDatasetId(source.phasedItemId ?? source.phasedTrackItemId),
    hap: String(source.hap || source.haplotypeKey || source.phasedHaplotypeKey || "").trim(),
    mirrored: source.mirrored === true || source.isMirror === true || sourceType === "mirror",
  };
}

export function buildSubviewCompositionSourceKey(value) {
  const source = normalizeSubviewCompositionSource(value?.source || value);
  return [
    source.role,
    source.datasetId || 0,
    source.sourceType,
    source.phasedTrackId || 0,
    source.phasedItemId || 0,
    source.hap,
  ].join(":");
}

export function normalizeSubviewCompositionMember(value, fallbackOrder = 0) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const assemblyCtgId = normalizeSupportDatasetId(value.assemblyCtgId ?? value.contigId);
  const reference = normalizeReference(value.reference);
  const entityKey = String(value.entityKey || buildSubviewCompositionEntityKey({
    assemblyCtgId,
    reference,
  })).trim();
  if (!entityKey) return null;
  const source = normalizeSubviewCompositionSource(value.source || value);
  return {
    entityKey,
    sourceKey: String(value.sourceKey || buildSubviewCompositionSourceKey(source)).trim(),
    assemblyCtgId,
    source,
    reference,
    label: String(value.label || value.name || entityKey).trim() || entityKey,
    lengthBp: normalizePositiveLength(value.lengthBp ?? value.totalLength),
    baseOrientation: normalizeOrientation(value.baseOrientation ?? value.orient ?? value.refOrient),
    lane: normalizeSubviewCompositionLane(value.lane),
    xBp: normalizeFiniteNumber(value.xBp, 0),
    flipped: value.flipped === true,
    order: normalizeNonNegativeOrder(value.order, fallbackOrder),
  };
}

export function normalizeSubviewCompositionMembers(values) {
  const seen = new Set();
  return (Array.isArray(values) ? values : [])
    .map((value, index) => normalizeSubviewCompositionMember(value, index))
    .filter((member) => {
      if (!member || seen.has(member.entityKey)) return false;
      seen.add(member.entityKey);
      return true;
    });
}

export function normalizeSubviewComposition(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const gap = Number(source.layoutGapBp);
  return {
    members: normalizeSubviewCompositionMembers(source.members),
    layoutGapBp: Number.isFinite(gap) && gap >= 0 ? gap : SUBVIEW_COMPOSITION_DEFAULT_GAP_BP,
    activeAnchors: normalizeSubviewActiveAnchors(source.activeAnchors),
    manualAnchors: normalizeSubviewManualAnchors(source.manualAnchors),
  };
}

export function createSubviewCompositionSummary(composition) {
  const normalized = normalizeSubviewComposition(composition);
  return {
    mode: SUBVIEW_COMPOSITION_MODE,
    members: normalized.members,
    layoutGapBp: normalized.layoutGapBp,
  };
}

export function getSubviewComposition(subview) {
  const summary = subview?.summary;
  if (String(summary?.mode || "").trim() !== SUBVIEW_COMPOSITION_MODE) return null;
  return normalizeSubviewComposition({
    members: summary?.members,
    layoutGapBp: summary?.layoutGapBp,
    activeAnchors: subview?.activeAnchors,
    manualAnchors: subview?.manualAnchors,
  });
}

export function applySubviewComposition(subview, composition, patch = {}) {
  const normalized = normalizeSubviewComposition(composition);
  return {
    ...subview,
    mode: SUBVIEW_COMPOSITION_MODE,
    selectedAContigId: null,
    selectedARole: "",
    selectedAPhasedTrackId: null,
    selectedAPhasedTrackItemId: null,
    selectedAPhasedHaplotypeKey: "",
    selectedBContigId: null,
    selectedBRole: "",
    selectedBPhasedTrackId: null,
    selectedBPhasedTrackItemId: null,
    selectedBPhasedHaplotypeKey: "",
    selectedTrackSelections: [],
    selectedTrackARole: "",
    selectedTrackBRole: "",
    selectedTrackBSource: "",
    selectedTrackBDatasetId: null,
    selectedTrackBIsMirror: false,
    trackPairHiddenCtgs: [],
    trackPairSelectedCtgs: [],
    flippedCtgs: [],
    activeAnchors: normalized.activeAnchors,
    manualAnchors: normalized.manualAnchors,
    summary: createSubviewCompositionSummary(normalized),
    error: "",
    ...patch,
  };
}

function resolveLaneRight(members, lane, gapBp) {
  const laneMembers = members.filter((member) => member.lane === lane);
  if (!laneMembers.length) return 0;
  return Math.max(...laneMembers.map((member) => member.xBp + member.lengthBp)) + gapBp;
}

export function addSubviewCompositionMembers(composition, candidates, lane) {
  const normalized = normalizeSubviewComposition(composition);
  const targetLane = normalizeSubviewCompositionLane(lane);
  const members = normalized.members.map((member) => ({ ...member }));
  const memberIndexByKey = new Map(members.map((member, index) => [member.entityKey, index]));
  let nextX = resolveLaneRight(members, targetLane, normalized.layoutGapBp);
  let nextOrder = members.reduce((maximum, member) => Math.max(maximum, member.order), -1) + 1;
  let addedCount = 0;
  let movedCount = 0;
  const existingKeys = [];
  normalizeSubviewCompositionMembers(candidates).forEach((candidate) => {
    const existingIndex = memberIndexByKey.get(candidate.entityKey);
    if (existingIndex !== undefined) {
      const existing = members[existingIndex];
      if (existing.lane === targetLane) {
        existingKeys.push(existing.entityKey);
        return;
      }
      members[existingIndex] = { ...existing, lane: targetLane, order: nextOrder };
      nextOrder += 1;
      movedCount += 1;
      return;
    }
    const member = {
      ...candidate,
      lane: targetLane,
      xBp: nextX,
      order: nextOrder,
    };
    members.push(member);
    memberIndexByKey.set(member.entityKey, members.length - 1);
    nextX += member.lengthBp + normalized.layoutGapBp;
    nextOrder += 1;
    addedCount += 1;
  });
  return {
    composition: { ...normalized, members },
    changed: addedCount > 0 || movedCount > 0,
    addedCount,
    movedCount,
    existingKeys,
  };
}

export function removeSubviewCompositionMembers(composition, entityKeys) {
  const normalized = normalizeSubviewComposition(composition);
  const removeKeys = new Set((Array.isArray(entityKeys) ? entityKeys : [entityKeys])
    .map((key) => String(key || "").trim()).filter(Boolean));
  const members = normalized.members.filter((member) => !removeKeys.has(member.entityKey));
  return {
    composition: { ...normalized, members },
    changed: members.length !== normalized.members.length,
    removedCount: normalized.members.length - members.length,
  };
}

export function moveSubviewCompositionMembers(composition, entityKeys, lane) {
  const normalized = normalizeSubviewComposition(composition);
  const targetLane = normalizeSubviewCompositionLane(lane);
  const moveKeys = new Set((Array.isArray(entityKeys) ? entityKeys : [entityKeys])
    .map((key) => String(key || "").trim()).filter(Boolean));
  let nextOrder = normalized.members.reduce((maximum, member) => Math.max(maximum, member.order), -1) + 1;
  let movedCount = 0;
  const members = normalized.members.map((member) => {
    if (!moveKeys.has(member.entityKey) || member.lane === targetLane) return member;
    movedCount += 1;
    const moved = { ...member, lane: targetLane, order: nextOrder };
    nextOrder += 1;
    return moved;
  });
  return {
    composition: { ...normalized, members },
    changed: movedCount > 0,
    movedCount,
  };
}

export function swapSubviewCompositionLanes(composition) {
  const normalized = normalizeSubviewComposition(composition);
  if (!normalized.members.length) return { composition: normalized, changed: false };
  return {
    composition: {
      ...normalized,
      members: normalized.members.map((member) => ({
        ...member,
        lane: member.lane === "top" ? "bottom" : "top",
      })),
    },
    changed: true,
  };
}

export function compactSubviewCompositionLayout(composition) {
  const normalized = normalizeSubviewComposition(composition);
  const positions = new Map();
  for (const lane of ["top", "bottom"]) {
    let xBp = 0;
    normalized.members
      .filter((member) => member.lane === lane)
      .sort((left, right) => left.xBp - right.xBp || left.order - right.order
        || left.entityKey.localeCompare(right.entityKey))
      .forEach((member) => {
        positions.set(member.entityKey, xBp);
        xBp += member.lengthBp + normalized.layoutGapBp;
      });
  }
  const members = normalized.members.map((member) => ({
    ...member,
    xBp: positions.get(member.entityKey) ?? member.xBp,
  }));
  return {
    composition: { ...normalized, members },
    changed: members.some((member, index) => member.xBp !== normalized.members[index].xBp),
  };
}

export function setSubviewCompositionMemberPosition(composition, entityKey, xBp) {
  const normalized = normalizeSubviewComposition(composition);
  const key = String(entityKey || "").trim();
  const position = Number(xBp);
  if (!key || !Number.isFinite(position)) return { composition: normalized, changed: false };
  let changed = false;
  const members = normalized.members.map((member) => {
    if (member.entityKey !== key || member.xBp === position) return member;
    changed = true;
    return { ...member, xBp: position };
  });
  return { composition: { ...normalized, members }, changed };
}

export function toggleSubviewCompositionMemberFlip(composition, entityKey) {
  const normalized = normalizeSubviewComposition(composition);
  const key = String(entityKey || "").trim();
  let changed = false;
  const members = normalized.members.map((member) => {
    if (member.entityKey !== key) return member;
    changed = true;
    return { ...member, flipped: !member.flipped };
  });
  return { composition: { ...normalized, members }, changed };
}
