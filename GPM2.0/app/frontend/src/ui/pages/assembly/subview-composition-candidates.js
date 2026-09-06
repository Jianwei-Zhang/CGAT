import { normalizeSupportDatasetId } from "./selection-state.js";
import {
  buildSubviewCompositionEntityKey,
  buildSubviewCompositionSourceKey,
  normalizeSubviewCompositionMember,
} from "./subview-composition-state.js";

function resolveRole(ctg, primaryDatasetId) {
  const explicit = String(ctg?.role || ctg?.trackRole || "").trim();
  if (["primary", "support", "phased", "ref"].includes(explicit)) return explicit;
  return normalizeSupportDatasetId(ctg?.datasetId) === normalizeSupportDatasetId(primaryDatasetId)
    ? "primary"
    : "support";
}

function projectCandidate(ctg, sourcePatch, index) {
  const source = {
    role: sourcePatch.role,
    datasetId: normalizeSupportDatasetId(ctg?.datasetId ?? sourcePatch.datasetId),
    datasetName: String(ctg?.datasetName || sourcePatch.datasetName || "").trim(),
    sourceType: sourcePatch.sourceType,
    phasedTrackId: normalizeSupportDatasetId(ctg?.phasedTrackId ?? sourcePatch.phasedTrackId),
    phasedItemId: normalizeSupportDatasetId(
      ctg?.phasedTrackItemId ?? ctg?.itemId ?? sourcePatch.phasedItemId,
    ),
    hap: String(ctg?.phasedHaplotypeKey || sourcePatch.hap || "").trim(),
    mirrored: sourcePatch.sourceType === "mirror",
  };
  const reference = source.role === "ref" ? {
    chrName: String(ctg?.referenceChrName || ctg?.chrName || "").trim(),
    startBp: ctg?.segmentStartBp ?? ctg?.startBp,
    endBp: ctg?.segmentEndBp ?? ctg?.endBp,
  } : null;
  const member = normalizeSubviewCompositionMember({
    entityKey: buildSubviewCompositionEntityKey(source.role === "ref"
      ? { reference }
      : { assemblyCtgId: ctg?.assemblyCtgId }),
    sourceKey: buildSubviewCompositionSourceKey(source),
    assemblyCtgId: ctg?.assemblyCtgId,
    source,
    reference,
    label: ctg?.name || ctg?.ctgName,
    lengthBp: ctg?.lengthBp ?? ctg?.totalLength,
    baseOrientation: ctg?.orient ?? ctg?.refOrient,
    lane: "top",
    xBp: 0,
    order: index,
  }, index);
  return member ? {
    ...member,
    candidateKey: `${member.entityKey}|${member.sourceKey}`,
    sourceOrder: index,
    ctg: { ...ctg },
  } : null;
}

export function buildSubviewCompositionCandidates({
  allChrCtgs = [],
  supportMirroredCtgs = [],
  phasedCtgs = [],
  refCtgs = [],
  primaryDatasetId = null,
  selectedChrName = "",
  deletedCtgs = [],
} = {}) {
  const deletedIds = new Set((Array.isArray(deletedCtgs) ? deletedCtgs : [])
    .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId)).filter(Boolean));
  const chrName = String(selectedChrName || "").trim();
  const groups = [
    ...(Array.isArray(allChrCtgs) ? allChrCtgs : []).map((ctg) => ({
      ctg,
      source: { role: resolveRole(ctg, primaryDatasetId), sourceType: "mother" },
    })),
    ...(Array.isArray(supportMirroredCtgs) ? supportMirroredCtgs : [])
      .filter((ctg) => !chrName || !ctg?.chrName || String(ctg.chrName) === chrName)
      .map((ctg) => ({ ctg, source: { role: "support", sourceType: "mirror" } })),
    ...(Array.isArray(phasedCtgs) ? phasedCtgs : [])
      .map((ctg) => ({ ctg, source: { role: "phased", sourceType: "phased" } })),
    ...(Array.isArray(refCtgs) ? refCtgs : [])
      .map((ctg) => ({ ctg, source: { role: "ref", sourceType: "ref_segment" } })),
  ];
  const seenSourceKeys = new Set();
  return groups
    .map((entry, index) => projectCandidate(entry.ctg, entry.source, index))
    .filter((candidate) => {
      if (!candidate || (candidate.assemblyCtgId && deletedIds.has(candidate.assemblyCtgId))) return false;
      const key = `${candidate.entityKey}|${candidate.sourceKey}`;
      if (seenSourceKeys.has(key)) return false;
      seenSourceKeys.add(key);
      return true;
    });
}

export function filterSubviewCompositionCandidates(candidates, { query = "", source = "all" } = {}) {
  const normalizedQuery = String(query || "").trim().toLocaleLowerCase();
  const normalizedSource = String(source || "all").trim();
  return (Array.isArray(candidates) ? candidates : []).filter((candidate) => {
    if (normalizedSource !== "all" && candidate?.source?.role !== normalizedSource) return false;
    if (!normalizedQuery) return true;
    const haystack = [
      candidate?.label,
      candidate?.source?.datasetName,
      candidate?.source?.role,
      candidate?.source?.sourceType,
    ].join(" ").toLocaleLowerCase();
    return haystack.includes(normalizedQuery);
  });
}

export function resolveSubviewCompositionCandidate(candidates, member) {
  const source = Array.isArray(candidates) ? candidates : [];
  return source.find((candidate) => candidate.entityKey === member?.entityKey
    && candidate.sourceKey === member?.sourceKey)
    || source.find((candidate) => candidate.entityKey === member?.entityKey)
    || null;
}
