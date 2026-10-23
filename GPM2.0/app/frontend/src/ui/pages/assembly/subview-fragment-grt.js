import { memberSourceInterval, sourceCoordinateToMember } from "./subview-fragment-model.js";

// Optional projection interface consumed by the shared GRT renderers. Matching
// uses real source lineage, not display labels or an arbitrary same-source copy.
export function localGrtProjection(member) {
  const range = memberSourceInterval(member);
  const rootId = Number(String(range.instanceKey || "").match(/^assembly:(\d+)/)?.[1]);
  const ids = new Set([...(range.lineageCtgIds || []), ...range.parts.map((part) => part.assemblyCtgId), rootId].filter(Boolean));
  const matchesSourceInterval = (interval) => ids.has(Number(interval?.assemblyCtgId));
  const projectSourcePositionToCtg = (position, interval) => {
    const value = Number(position);
    return matchesSourceInterval(interval) && Number.isSafeInteger(value) && value >= range.sourceStart && value <= range.sourceEnd
      ? sourceCoordinateToMember(member, value) : null;
  };
  return { sourceRange: range, matchesSourceInterval, projectSourcePositionToCtg,
    projectSourcePosition(position, interval) {
      const base = projectSourcePositionToCtg(position, interval);
      if (base == null) return null;
      const display = member.flipped ? member.lengthBp - base + 1 : base;
      return member.x + ((display - 1) / member.lengthBp) * member.width;
    },
    clipSourceInterval(interval) {
      if (!matchesSourceInterval(interval)) return null;
      const sourceStart = Math.max(range.sourceStart, Number(interval.sourceStart));
      const sourceEnd = Math.min(range.sourceEnd, Number(interval.sourceEnd));
      if (!Number.isFinite(sourceStart) || !Number.isFinite(sourceEnd) || sourceEnd < sourceStart) return null;
      const occurrences = (interval.occurrences || []).flatMap((occurrence) => {
        const start = Math.max(sourceStart, occurrence.sourceStart), end = Math.min(sourceEnd, occurrence.sourceEnd);
        return end >= start ? [{ ...occurrence, sourceStart: start, sourceEnd: end }] : [];
      });
      return { ...interval, sourceStart, sourceEnd, ...(interval.occurrences ? { occurrences } : {}) };
    },
  };
}

// Clip paired GRT display evidence with one shared alignment parameter. A band
// must not span a deleted interval or attach its two ends to different objects.
export function projectLocalGrtEvidence(plan, entries) {
  if (!plan || !(plan.displayEvidence || []).length) return plan;
  const displayEvidence = plan.displayEvidence.flatMap((evidence) => {
    if (!evidence.source || !evidence.target) return [];
    const sources = entries.filter((entry) => entry.matchesSourceInterval?.(evidence.source));
    const targets = entries.filter((entry) => entry.matchesSourceInterval?.(evidence.target));
    const result = [];
    for (const source of sources) for (const target of targets) {
      if (source === target) continue;
      const a = evidence.source.orientation === "-" ? evidence.source.end : evidence.source.start;
      const z = evidence.source.orientation === "-" ? evidence.source.start : evidence.source.end;
      const b = evidence.target.orientation === "-" ? evidence.target.end : evidence.target.start;
      const y = evidence.target.orientation === "-" ? evidence.target.start : evidence.target.end;
      let low = 0, high = 1;
      for (const [first, last, range] of [[a, z, source.sourceRange], [b, y, target.sourceRange]]) {
        if (![first, last, range.sourceStart, range.sourceEnd].every(Number.isFinite)) { high = -1; break; }
        if (first === last) { if (first < range.sourceStart || first > range.sourceEnd) high = -1; continue; }
        const left = (range.sourceStart - first) / (last - first), right = (range.sourceEnd - first) / (last - first);
        low = Math.max(low, Math.min(left, right)); high = Math.min(high, Math.max(left, right));
      }
      if (high < low) continue;
      const clip = (interval, first, last, entry) => {
        // GRT source coordinates are inclusive integer bases; inward rounding
        // must not fabricate a base at an unavailable edge.
        const p = first + (last - first) * low, q = first + (last - first) * high;
        const start = Math.ceil(Math.min(p, q) - 1e-7), end = Math.floor(Math.max(p, q) + 1e-7);
        return end >= start ? { ...interval, start, end, localEntryKey: entry.key } : null;
      };
      const clippedSource = clip(evidence.source, a, z, source), clippedTarget = clip(evidence.target, b, y, target);
      if (clippedSource && clippedTarget) result.push({ ...evidence, source: clippedSource, target: clippedTarget });
    }
    return result;
  });
  return { ...plan, displayEvidence };
}
