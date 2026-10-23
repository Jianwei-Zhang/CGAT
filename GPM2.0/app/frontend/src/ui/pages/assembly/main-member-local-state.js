import { memberActiveBackingParts, memberSourceInterval, memberEffectiveOrientation, sliceLocalMember } from "./subview-fragment-model.js";

export function resolveMainMemberSourceRange(ctg) {
  const value = ctg?.sourceFragment || ctg?.sourceRange;
  const start = Number(value?.sourceStart), end = Number(value?.sourceEnd);
  return Number.isSafeInteger(start) && Number.isSafeInteger(end) && start > 0 && end >= start
    ? { sourceStart: start, sourceEnd: end, sourceSeqId: Number(value.sourceSeqId) || null } : null;
}
// Only compact generated interval labels when an authoritative source range is
// available. Keep user names and split suffixes intact; the full name remains
// the tooltip/accessibility label, and exact source coordinates have their row.
export function resolveMainMemberCardName(ctg, visibleName) {
  const name = String(visibleName || "");
  if (!resolveMainMemberSourceRange(ctg)) return name;
  return name.replace(/(?:\[\d+[-–]\d+\])+(?=(?:\.\d+)*$)/, "") || name;
}

function legacyContains(summary, id) {
  return summary?.mode === "track-pair" ? [summary.topTrack, summary.bottomTrack].some((track) => track?.role === "primary")
    : [summary?.top, summary?.bottom].some((entry) => entry?.role === "primary" && Number(entry.contigId) === id);
}

// This is annotation only: never replace real Main DS members or their lengths
// with Local View presentations. Repeated local copies count toward objects,
// while covered base counts are unioned so they cannot inflate real sequence.
export function describeMainMemberLocalState(ctg, assembly) {
  const id = Number(ctg?.assemblyCtgId), subview = assembly?.subview;
  if (!id || !subview?.summary) return null;
  if (subview.summary.mode !== "composition") {
    if (!legacyContains(subview.summary, id)) return null;
    if ((subview.trackPairHiddenCtgs || []).some((entry) => entry.trackRole === "primary" && entry.contigId === id)) return { kind: "deleted", count: 0, ranges: [] };
    if ((subview.flippedCtgs || []).some((entry) => entry.contigId === id)) return { kind: "flipped", count: 1, ranges: [] };
    if ((assembly.subviewTrackDragOffsets || []).some((entry) => entry.contigId === id && Number(entry.offsetBp ?? entry.offsetPx))) return { kind: "moved", count: 1, ranges: [] };
    return null;
  }
  const members = (subview.summary.members || []).filter((member) => member.source?.role === "primary"
    && memberActiveBackingParts(member).some((part) => part.assemblyCtgId === id));
  const record = assembly.subviewHistoryByKey?.[subview.historyKey || `composition:${encodeURIComponent(assembly.selectedChrName || "")}`];
  const baseline = record?.default;
  const baselineMembers = baseline?.kind === "composition" ? baseline.composition.members || [] : [];
  const baselineHad = baseline?.kind === "legacy" ? legacyContains(baseline.summary, id)
    : baselineMembers.some((member) => memberActiveBackingParts(member).some((part) => part.assemblyCtgId === id));
  if (!members.length) return baselineHad ? { kind: "deleted", count: 0, ranges: [] } : null;
  const real = resolveMainMemberSourceRange(ctg) || { sourceStart: 1, sourceEnd: Number(ctg.totalLength ?? ctg.lengthBp) };
  const intervals = members.map((member) => memberSourceInterval(member))
    .map((range) => [Math.max(real.sourceStart, range.sourceStart), Math.min(real.sourceEnd, range.sourceEnd)])
    .filter(([start, end]) => end >= start).sort((a, b) => a[0] - b[0]);
  const ranges = [];
  for (const [start, end] of intervals) {
    const previous = ranges.at(-1);
    if (previous && start <= previous[1] + 1) previous[1] = Math.max(end, previous[1]); else ranges.push([start, end]);
  }
  const retainedBp = ranges.reduce((sum, [a, z]) => sum + z - a + 1, 0);
  const totalBp = Number(ctg.totalLength ?? ctg.lengthBp);
  const orient = (ctg.orient ?? ctg.refOrient) === "-" ? "-" : "+";
  const differentDirection = members.some((member) => memberEffectiveOrientation(member) !== orient);
  const joined = members.some((member) => memberActiveBackingParts(member).length > 1);
  const moved = members.some((member) => baselineMembers.some((old) => {
    const a = memberSourceInterval(old), z = memberSourceInterval(member);
    if (a.groupKey !== z.groupKey || a.instanceKey !== z.instanceKey || z.sourceStart < a.sourceStart || z.sourceEnd > a.sourceEnd) return false;
    const expected = sliceLocalMember(old, z.sourceStart, z.sourceEnd);
    return expected && Math.abs(member.xBp - expected.xBp) > 0.01;
  }));
  const kind = retainedBp < totalBp ? "partial" : members.length > 1 ? "objects" : joined ? "merged"
    : differentDirection ? "flipped" : moved ? "moved" : null;
  return kind ? { kind, count: members.length, retainedBp, totalBp, ranges } : null;
}


export function createMainMemberAnnotationRefresh({ rerenderMembers }) {
  const cache = new WeakMap();
  return (host, store) => {
    if (!host || typeof host !== "object") return false;
    const state = store.getState(), assembly = state.assembly, subview = assembly.subview;
    const record = assembly.subviewHistoryByKey?.[subview?.historyKey || `composition:${encodeURIComponent(assembly.selectedChrName || "")}`];
    const references = [subview?.summary, subview?.flippedCtgs, subview?.trackPairHiddenCtgs,
      assembly.subviewTrackDragOffsets, record?.default, assembly.chrCtgs, assembly.deletedCtgs,
      state.locale, assembly.selectedChrName, assembly.membersCardCollapsed];
    const previous = cache.get(host);
    if (previous && references.every((value, index) => value === previous.references[index])) return false;
    const signature = JSON.stringify([subview?.summary, subview?.flippedCtgs, subview?.trackPairHiddenCtgs,
      assembly.subviewTrackDragOffsets, record?.default, state.locale, assembly.selectedChrName, assembly.membersCardCollapsed]);
    const entry = { references, signature };
    cache.set(host, entry); // re-binding the new card must not recursively refresh itself
    if (previous?.signature === signature && previous.references[5] === assembly.chrCtgs && previous.references[6] === assembly.deletedCtgs) return false;
    if (rerenderMembers(host, store) === false) { cache.delete(host); return false; }
    return true;
  };
}
