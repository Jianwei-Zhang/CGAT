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

// A gesture owns the clicked object unless it belongs to the explicit selection.
// Provenance is not a movement constraint: same-source siblings do not opt in.
export function collectContigDragTargets(host, node, {
  subview = false, selectedIds = [], selectedEntries = [],
} = {}) {
  const attr = (entry, name) => String(entry?.getAttribute?.(name) || "");
  const positive = (entry, name) => Number(attr(entry, name)) || null;
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
  const ids = new Set((Array.isArray(selectedIds) ? selectedIds : []).map(Number));
  const selections = new Set((Array.isArray(selectedEntries) ? selectedEntries : []).map((entry) =>
    entry.compositionEntityKey ? `entity:${entry.compositionEntityKey}`
      : `${entry.trackRole}:${Number(entry.contigId)}:${entry.slot || ""}`));
  const selected = (entry) => {
    if (!subview) return attr(entry, "data-track-role") === "primary"
      && ids.has(positive(entry, "data-track-contig-id"));
    const key = `${attr(entry, "data-subview-track-role")}:${positive(entry, "data-subview-contig-id")}:`;
    return selections.has(`entity:${attr(entry, "data-subview-composition-entity-key")}`)
      || selections.has(key) || selections.has(key + attr(entry, "data-subview-track-slot"));
  };
  const first = identity(node);
  const result = [first];
  if (!selected(node)) return result;
  const seen = new Set([JSON.stringify(first)]);
  const selector = subview ? "[data-subview-contig-id][data-subview-track-slot]"
    : "[data-track-contig-id][data-track-role]";
  for (const entry of host?.querySelectorAll?.(selector) || []) {
    if (!selected(entry)) continue;
    const target = identity(entry);
    if (!(subview ? target.contigId : target.assemblyCtgId)) continue;
    if (subview) {
      if (Boolean(target.compositionEntityKey) !== Boolean(first.compositionEntityKey)) continue;
    } else if (target.trackRole !== first.trackRole
      || (target.datasetId || 0) !== (first.datasetId || 0)
      || (target.phasedTrackId || 0) !== (first.phasedTrackId || 0)) continue;
    const key = JSON.stringify(target);
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(target);
  }
  return result;
}

// Keep each member's pre-gesture offset, including older independent drags.
export function buildSourceFragmentDragPayload(targets, baseOffsets, deltaBp, round, explicitSelection = false) {
  const moved = targets.map((target, index) => ({ ...target,
    ...(target.compositionEntityKey ? { dragDeltaBp: round(deltaBp) }
      : { offsetBp: round(baseOffsets[index] + deltaBp) }),
  }));
  return { ...moved[0], ...(moved.length > 1 ? { targets: moved, ...(explicitSelection ? { dragSelection: true } : {}) } : {}) };
}
