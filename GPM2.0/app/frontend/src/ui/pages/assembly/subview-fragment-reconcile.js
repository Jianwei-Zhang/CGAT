import { normalizeSubviewComposition, applySubviewComposition } from "./subview-composition-state.js";
import { memberSourceInterval, sliceLocalMember, normalizeLocalFragment, replaceLocalMembers } from "./subview-fragment-model.js";

const canonicalGroup = (key) => String(key || "").replace(/^manual-fragment:(\d+)$/, "assembly:$1");
function sourceOf(ctg) {
  const length = Number(ctg.totalLength ?? ctg.lengthBp);
  const sourceStart = Number(ctg.sourceFragment?.sourceStart || 1);
  return { assemblyCtgId: Number(ctg.assemblyCtgId),
    sourceSeqId: Number(ctg.sourceFragment?.sourceSeqId ?? ctg.originSourceSeqId) || null,
    groupKey: String(ctg.sourceFragment?.groupKey || `assembly:${ctg.assemblyCtgId}`),
    sourceStart, sourceEnd: Number(ctg.sourceFragment?.sourceEnd || sourceStart + length - 1),
    orient: (ctg.orient ?? ctg.refOrient) === "-" ? "-" : "+" };
}

// Rebind source-owned Local View objects after real Main View split/flip/delete
// and history reload. Never pick an independent co-assigned/cross-chr copy just
// because it has the same source sequence. Missing source intervals are removed
// from every local snapshot, so local undo cannot resurrect main-deleted bases.
export function reconcileLocalCompositionWithMain(composition, mainCtgs) {
  let current = normalizeSubviewComposition(composition);
  const sources = (mainCtgs || []).map(sourceOf).filter((source) => Number.isSafeInteger(source.sourceEnd)
    && source.sourceStart > 0 && source.sourceEnd >= source.sourceStart);
  for (const member of current.members.slice()) {
    if (member.source.role !== "primary") continue;
    const range = memberSourceInterval(member);
    const originalIds = new Set(range.parts.map((part) => part.assemblyCtgId));
    const groups = new Set([canonicalGroup(range.groupKey), ...range.parts.map((part) => `assembly:${part.assemblyCtgId}`)]);
    const candidates = sources.filter((source) => (!range.sourceSeqId || !source.sourceSeqId || range.sourceSeqId === source.sourceSeqId)
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
        sourceSeqId: range.sourceSeqId || candidates[0]?.sourceSeqId });
      if (!localFragment) return [];
      return [{ ...sliced,
        ...(start === range.sourceStart && end === range.sourceEnd ? { entityKey: member.entityKey } : {}),
        assemblyCtgId: parts[0].assemblyCtgId, localFragment }];
    });
    current = replaceLocalMembers(current, [member], replacements);
  }
  return normalizeSubviewComposition(current);
}

export function reconcileLocalSubviewWithMain(assembly) {
  if (!assembly || !Array.isArray(assembly.chrCtgs)) return assembly;
  const key = `composition:${encodeURIComponent(String(assembly.selectedChrName || ""))}`;
  const transform = (snapshot) => snapshot?.kind === "composition" ? { ...snapshot,
    composition: reconcileLocalCompositionWithMain(snapshot.composition, assembly.chrCtgs) } : snapshot;
  const record = assembly.subviewHistoryByKey?.[key];
  const subviewHistoryByKey = record ? { ...assembly.subviewHistoryByKey, [key]: { ...record,
    current: transform(record.current), default: transform(record.default),
    past: (record.past || []).map((entry) => ({ ...entry, snapshot: transform(entry.snapshot) })),
    forward: (record.forward || []).map((entry) => ({ ...entry, snapshot: transform(entry.snapshot) })),
  } } : assembly.subviewHistoryByKey;
  const subview = assembly.subview?.summary?.mode === "composition" ? applySubviewComposition(assembly.subview,
    reconcileLocalCompositionWithMain({ members: assembly.subview.summary.members,
      layoutGapBp: assembly.subview.summary.layoutGapBp, activeAnchors: assembly.subview.activeAnchors,
      manualAnchors: assembly.subview.manualAnchors }, assembly.chrCtgs)) : assembly.subview;
  return { ...assembly, subview, subviewHistoryByKey };
}
