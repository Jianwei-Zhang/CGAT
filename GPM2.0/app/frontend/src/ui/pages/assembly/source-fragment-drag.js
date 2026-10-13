import { setTrackDragOffset, setSubviewTrackDragOffset } from "./selection-state.js";
import { setSubviewCompositionMemberPosition } from "./subview-composition-state.js";

export function dragTargets(payload) {
  return Array.isArray(payload?.targets) && payload.targets.length ? payload.targets : [payload];
}

export function setTrackDragGroupOffsets(offsets, payload) {
  return dragTargets(payload).reduce(setTrackDragOffset, offsets);
}

export function setSubviewDragGroupOffsets(offsets, payload) {
  return dragTargets(payload).reduce(setSubviewTrackDragOffset, offsets);
}

export function moveSubviewCompositionDrag(composition, payload) {
  let current = composition;
  let changed = false;
  for (const target of dragTargets(payload)) {
    const member = current.members.find((entry) => entry.entityKey === target.compositionEntityKey);
    if (!member || !Number.isFinite(target.dragDeltaBp)) continue;
    const next = setSubviewCompositionMemberPosition(current, member.entityKey, member.xBp + target.dragDeltaBp);
    current = next.composition;
    changed ||= next.changed;
  }
  return { composition: current, changed };
}

// Resolve only the rendered instances in this view. Do not alter selection, or
// link another dataset, phased track, or an unrelated instance of the source.
export function collectSourceFragmentDragTargets(host, node, { subview = false } = {}) {
  const attr = (entry, name) => String(entry?.getAttribute?.(name) || "");
  const positive = (entry, name) => Number(attr(entry, name)) || null;
  const scopeAttrs = subview
    ? ["data-subview-track-role", "data-subview-track-pair-dataset-id",
      "data-subview-track-pair-phased-track-id", "data-subview-track-pair-is-mirror"]
    : ["data-track-role", "data-track-dataset-id", "data-track-phased-track-id"];
  const identity = (entry) => subview ? {
    slot: attr(entry, "data-subview-track-slot"),
    contigId: positive(entry, "data-subview-contig-id"),
    ...(attr(entry, "data-subview-composition-entity-key")
      ? { compositionEntityKey: attr(entry, "data-subview-composition-entity-key") } : {}),
  } : {
    trackRole: attr(entry, "data-track-role"),
    assemblyCtgId: positive(entry, "data-track-contig-id"),
    ...Object.fromEntries([
      ["datasetId", "data-track-dataset-id"],
      ["phasedTrackId", "data-track-phased-track-id"],
      ["phasedTrackItemId", "data-track-phased-track-item-id"],
    ].map(([key, name]) => [key, positive(entry, name)]).filter(([, value]) => value)),
  };
  const first = identity(node);
  const result = [first];
  const seen = new Set([JSON.stringify(first)]);
  const group = attr(node, "data-source-fragment-group");
  const sourceId = attr(node, "data-source-fragment-seq-id");
  if (!group || !sourceId) return result;
  const selector = subview ? "[data-subview-contig-id][data-subview-track-slot]"
    : "[data-track-contig-id][data-track-role]";
  for (const entry of host?.querySelectorAll?.(selector) || []) {
    if (attr(entry, "data-source-fragment-group") !== group
      || attr(entry, "data-source-fragment-seq-id") !== sourceId
      || scopeAttrs.some((name) => (attr(entry, name) || "0") !== (attr(node, name) || "0"))) continue;
    const target = identity(entry);
    if (!(subview ? target.contigId : target.assemblyCtgId)) continue;
    // Composition and legacy track layouts must never share a gesture payload.
    if (Boolean(target.compositionEntityKey) !== Boolean(first.compositionEntityKey)) continue;
    const key = JSON.stringify(target);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(target);
  }
  return result;
}

// Keep each member's pre-gesture offset, including older independent drags.
export function buildSourceFragmentDragPayload(targets, baseOffsets, deltaBp, round) {
  const moved = targets.map((target, index) => ({ ...target,
    ...(target.compositionEntityKey ? { dragDeltaBp: round(deltaBp) }
      : { offsetBp: round(baseOffsets[index] + deltaBp) }),
  }));
  return { ...moved[0], ...(moved.length > 1 ? { targets: moved } : {}) };
}
