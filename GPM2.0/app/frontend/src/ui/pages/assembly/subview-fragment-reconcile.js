import { resolveManualSplitSourceCuts } from "./source-fragment-layout.js";
import { normalizeSubviewComposition, applySubviewComposition } from "./subview-composition-state.js";
import { memberSourceInterval, sliceLocalMember, normalizeLocalFragment, replaceLocalMembers } from "./subview-fragment-model.js";

const canonicalGroup = (key) => String(key || "").replace(/^manual-fragment:(\d+)$/, "assembly:$1");
function sourceOf(ctg) {
  const length = Number(ctg.totalLength ?? ctg.lengthBp);
  const sourceStart = Number(ctg.sourceFragment?.sourceStart || 1);
  return { assemblyCtgId: Number(ctg.assemblyCtgId), deleted: Boolean(ctg.deletedCtgRecordId),
    // Deletion records expose identity/range, not N-boundary metadata. Never
    // infer a new cut from a nonzero archived sourceStart alone.
    nativeCuts: ctg.deletedCtgRecordId ? [] : resolveManualSplitSourceCuts(ctg),
    sourceSeqId: Number(ctg.sourceFragment?.sourceSeqId ?? ctg.originSourceSeqId) || null,
    groupKey: String(ctg.sourceFragment?.groupKey || `assembly:${ctg.assemblyCtgId}`),
    sourceStart, sourceEnd: Number(ctg.sourceFragment?.sourceEnd || sourceStart + length - 1),
    orient: (ctg.orient ?? ctg.refOrient) === "-" ? "-" : "+" };
}

// Rebind source-owned Local View objects after real Main View split/flip/delete
// and history reload. Never pick an independent co-assigned/cross-chr copy just
// because it has the same source sequence. Missing source intervals are removed
// from ordinary local snapshots. Explicit local history recovery (and legacy
// undo-split objects) may retain archived backing, never a native Main entity.
export function reconcileLocalCompositionWithMain(composition, mainCtgs, deletedCtgs = [], { recoverDeletedCtgIds = [], materializeSplits = false } = {}) {
  const deletedSources = (Array.isArray(deletedCtgs) ? deletedCtgs : []).filter((ctg) => ctg.sourceRange).map((ctg) => ({
    ...ctg, sourceFragment: { ...ctg.sourceRange, groupKey: ctg.sourceGroupKey || `assembly:${ctg.assemblyCtgId}` },
  }));
  let current = normalizeSubviewComposition(composition);
  const sources = (mainCtgs || []).map(sourceOf).filter((source) => Number.isSafeInteger(source.sourceEnd)
    && source.sourceStart > 0 && source.sourceEnd >= source.sourceStart);
  for (const member of current.members.slice()) {
    if (!["primary", "phased"].includes(member.source.role)) continue;
    const range = memberSourceInterval(member);
    const originalIds = new Set(range.parts.map((part) => part.assemblyCtgId));
    // An N-delimited parent receives a manual group at its first real cut.
    // Later descendants keep that retired parent's group, not their immediate
    // predecessor ID. Preserve the known ancestry rather than dropping them.
    const groups = new Set([canonicalGroup(range.groupKey),
      ...[...originalIds, ...(range.lineageCtgIds || [])].map((id) => `assembly:${id}`)]);
    // Only the native tombstones created by this synchronized deletion may
    // back a local undo snapshot. Do not revive other or future Main deletions.
    const archiveIds = new Set([...(range.archivedCtgIds || []), ...recoverDeletedCtgIds]);
    const available = [...sources, ...deletedSources.filter((ctg) => range.restoredLocally
      || archiveIds.has(Number(ctg.assemblyCtgId))).map(sourceOf)];
    const family = available.filter((source) => (!range.sourceSeqId || !source.sourceSeqId || range.sourceSeqId === source.sourceSeqId)
      && (originalIds.has(source.assemblyCtgId) || groups.has(canonicalGroup(source.groupKey))))
      .sort((a, b) => a.sourceStart - b.sourceStart || a.assemblyCtgId - b.assemblyCtgId);
    const candidates = family.filter((source) => source.sourceStart <= range.sourceEnd && source.sourceEnd >= range.sourceStart);
    if (!member.localFragment && candidates.length === 1 && !candidates[0].deleted) {
      const live = candidates[0], old = range.parts[0];
      if (live.assemblyCtgId === old.assemblyCtgId && live.sourceStart === old.sourceStart
        && live.sourceEnd === old.sourceEnd && live.orient === old.orient) continue;
    }
    const spans = [];
    for (const candidate of candidates) {
      const start = Math.max(range.sourceStart, candidate.sourceStart), end = Math.min(range.sourceEnd, candidate.sourceEnd);
      const last = spans.at(-1);
      if (last && start <= last[1] + 1) last[1] = Math.max(last[1], end); else spans.push([start, end]);
    }
    // Contiguous backing is not one interactive object: an external Main
    // split must materialize its boundaries in the open Local View. Historical
    // snapshots, however, retain their presentation (local undo never undoes
    // the real Main mutation), and an explicit local merge suppresses its cut.
    const backingCuts = family.slice(1).flatMap((candidate, index) =>
      family[index].sourceEnd + 1 === candidate.sourceStart ? [candidate.sourceStart - 1] : []);
    const internalCuts = backingCuts.filter((cut) => cut >= range.sourceStart && cut < range.sourceEnd);
    const retainedCuts = internalCuts.filter((cut) => !(range.suppressedCuts || []).includes(cut));
    const intervals = materializeSplits ? spans.flatMap(([start, end]) => {
      const boundaries = [start, ...retainedCuts.filter((cut) => cut >= start && cut < end)
        .map((cut) => cut + 1), end + 1];
      return boundaries.slice(0, -1).map((left, index) => [left, boundaries[index + 1] - 1]);
    }) : spans;
    const replacements = intervals.flatMap(([start, end]) => {
      const sliced = sliceLocalMember(member, start, end);
      if (!sliced) return [];
      const parts = candidates.filter((candidate) => candidate.sourceStart <= end && candidate.sourceEnd >= start)
        .map(({ assemblyCtgId, sourceStart, sourceEnd, orient }) => ({ assemblyCtgId, sourceStart, sourceEnd, orient }));
      const archivedCtgIds = [...new Set([...(range.archivedCtgIds || []), ...candidates
        .filter((candidate) => candidate.deleted && parts.some((part) => part.assemblyCtgId === candidate.assemblyCtgId))
        .map((candidate) => candidate.assemblyCtgId)])];
      const localFragment = normalizeLocalFragment({ ...sliced.localFragment, parts,
        ...(archivedCtgIds.length ? { archivedCtgIds } : {}),
        suppressedCuts: [...(range.suppressedCuts || []), ...(materializeSplits ? [] : internalCuts)],
        nativeCuts: [...backingCuts, ...candidates.flatMap((candidate) => candidate.nativeCuts),
          ...(range.nativeCuts || []).filter((cut) => candidates.some((candidate) => candidate.deleted
            && cut >= candidate.sourceStart - 1 && cut <= candidate.sourceEnd))],
        sourceSeqId: range.sourceSeqId || candidates[0]?.sourceSeqId });
      if (!localFragment) return [];
      return [{ ...sliced,
        ...(start === range.sourceStart && end === range.sourceEnd ? { entityKey: member.entityKey } : {}),
        assemblyCtgId: parts[0].assemblyCtgId, localFragment }];
    });
    current = replaceLocalMembers(current, [member], replacements);
  }
  if (current.deletedFragments?.length) {
    current.deletedFragments = current.deletedFragments.flatMap((entry) => {
      const rebound = reconcileLocalCompositionWithMain({ members: [entry.member] }, [...(mainCtgs || []), ...deletedSources]);
      return rebound.members.map((member) => ({ ...entry, member }));
    });
  }
  return normalizeSubviewComposition(current);
}

export function reconcileLocalSubviewWithMain(assembly) {
  if (!assembly || !Array.isArray(assembly.chrCtgs)) return assembly;
  const key = `composition:${encodeURIComponent(String(assembly.selectedChrName || ""))}`;
  const transform = (snapshot, materializeSplits = false) => {
    if (snapshot?.kind === "composition") return { ...snapshot, composition: reconcileLocalCompositionWithMain(snapshot.composition, assembly.chrCtgs, assembly.deletedCtgs, { materializeSplits }) };
    if (snapshot?.kind !== "legacy" || !snapshot.sourceProjection) return snapshot;
    const rebound = reconcileLocalCompositionWithMain(snapshot.sourceProjection, assembly.chrCtgs, assembly.deletedCtgs, { materializeSplits });
    return JSON.stringify(rebound) === JSON.stringify(normalizeSubviewComposition(snapshot.sourceProjection)) ? snapshot
      : { kind: "composition", composition: rebound };
  };
  const record = assembly.subviewHistoryByKey?.[key];
  const subviewHistoryByKey = record ? { ...assembly.subviewHistoryByKey, [key]: { ...record,
    current: transform(record.current, true), default: transform(record.default),
    past: (record.past || []).map((entry) => ({ ...entry, snapshot: transform(entry.snapshot) })),
    forward: (record.forward || []).map((entry) => ({ ...entry, snapshot: transform(entry.snapshot) })),
  } } : assembly.subviewHistoryByKey;
  let subview = assembly.subview?.summary?.mode === "composition" ? applySubviewComposition(assembly.subview,
    reconcileLocalCompositionWithMain({ members: assembly.subview.summary.members, deletedFragments: assembly.subview.summary.deletedFragments,
      layoutGapBp: assembly.subview.summary.layoutGapBp, activeAnchors: assembly.subview.activeAnchors,
      manualAnchors: assembly.subview.manualAnchors }, assembly.chrCtgs, assembly.deletedCtgs, { materializeSplits: true })) : assembly.subview;
  if (assembly.subview?.historyKey === key && record?.current?.kind === "legacy"
    && subviewHistoryByKey[key]?.current?.kind === "composition") {
    subview = applySubviewComposition(subview, subviewHistoryByKey[key].current.composition);
  }
  return { ...assembly, subview, subviewHistoryByKey };
}
