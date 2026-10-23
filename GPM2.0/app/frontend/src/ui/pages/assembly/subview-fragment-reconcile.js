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
// from ordinary local snapshots. Explicit local undo-split may keep read-only
// tombstone-backed intervals, but never restores a native Main entity.
export function reconcileLocalCompositionWithMain(composition, mainCtgs, deletedCtgs = []) {
  const deletedSources = (Array.isArray(deletedCtgs) ? deletedCtgs : []).filter((ctg) => ctg.sourceGroupKey && ctg.sourceRange).map((ctg) => ({
    ...ctg, sourceFragment: { ...ctg.sourceRange, groupKey: ctg.sourceGroupKey },
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
    const available = range.restoredLocally ? [...sources, ...deletedSources.map(sourceOf)] : sources;
    const candidates = available.filter((source) => (!range.sourceSeqId || !source.sourceSeqId || range.sourceSeqId === source.sourceSeqId)
      && (originalIds.has(source.assemblyCtgId) || groups.has(canonicalGroup(source.groupKey)))
      && source.sourceStart <= range.sourceEnd && source.sourceEnd >= range.sourceStart)
      .sort((a, b) => a.sourceStart - b.sourceStart || a.assemblyCtgId - b.assemblyCtgId);
    if (!member.localFragment && candidates.length === 1) {
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
    const replacements = spans.flatMap(([start, end]) => {
      const sliced = sliceLocalMember(member, start, end);
      if (!sliced) return [];
      const parts = candidates.filter((candidate) => candidate.sourceStart <= end && candidate.sourceEnd >= start)
        .map(({ assemblyCtgId, sourceStart, sourceEnd, orient }) => ({ assemblyCtgId, sourceStart, sourceEnd, orient }));
      const localFragment = normalizeLocalFragment({ ...sliced.localFragment, parts,
        nativeCuts: [...candidates.flatMap((candidate) => candidate.nativeCuts),
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
  const transform = (snapshot) => {
    if (snapshot?.kind === "composition") return { ...snapshot, composition: reconcileLocalCompositionWithMain(snapshot.composition, assembly.chrCtgs, assembly.deletedCtgs) };
    if (snapshot?.kind !== "legacy" || !snapshot.sourceProjection) return snapshot;
    const rebound = reconcileLocalCompositionWithMain(snapshot.sourceProjection, assembly.chrCtgs, assembly.deletedCtgs);
    return JSON.stringify(rebound) === JSON.stringify(normalizeSubviewComposition(snapshot.sourceProjection)) ? snapshot
      : { kind: "composition", composition: rebound };
  };
  const record = assembly.subviewHistoryByKey?.[key];
  const subviewHistoryByKey = record ? { ...assembly.subviewHistoryByKey, [key]: { ...record,
    current: transform(record.current), default: transform(record.default),
    past: (record.past || []).map((entry) => ({ ...entry, snapshot: transform(entry.snapshot) })),
    forward: (record.forward || []).map((entry) => ({ ...entry, snapshot: transform(entry.snapshot) })),
  } } : assembly.subviewHistoryByKey;
  let subview = assembly.subview?.summary?.mode === "composition" ? applySubviewComposition(assembly.subview,
    reconcileLocalCompositionWithMain({ members: assembly.subview.summary.members, deletedFragments: assembly.subview.summary.deletedFragments,
      layoutGapBp: assembly.subview.summary.layoutGapBp, activeAnchors: assembly.subview.activeAnchors,
      manualAnchors: assembly.subview.manualAnchors }, assembly.chrCtgs, assembly.deletedCtgs)) : assembly.subview;
  if (assembly.subview?.historyKey === key && record?.current?.kind === "legacy"
    && subviewHistoryByKey[key]?.current?.kind === "composition") {
    subview = applySubviewComposition(subview, subviewHistoryByKey[key].current.composition);
  }
  return { ...assembly, subview, subviewHistoryByKey };
}
