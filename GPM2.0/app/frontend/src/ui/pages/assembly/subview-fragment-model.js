import { resolveManualSplitSourceCuts } from "./source-fragment-layout.js";
import { buildSubviewAnchorEndpointKey } from "./subview-anchor-state.js";

const positive = (value) => Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
const orientation = (value) => value === "-" ? "-" : "+";

// Coordinates here are inclusive SOURCE bases, never screen positions. Each
// backing part records the orientation/range of the real entity when projected.
// A local join can span several real entities without merging any of them.
export function normalizeLocalFragment(value) {
  if (!value || typeof value !== "object") return null;
  const sourceStart = positive(value.sourceStart), sourceEnd = positive(value.sourceEnd);
  const groupKey = String(value.groupKey || "").trim();
  const parts = (Array.isArray(value.parts) ? value.parts : []).flatMap((part) => {
    const assemblyCtgId = positive(part?.assemblyCtgId);
    const start = positive(part?.sourceStart), end = positive(part?.sourceEnd);
    return assemblyCtgId && start && end >= start ? [{ assemblyCtgId,
      sourceStart: start, sourceEnd: end, orient: orientation(part.orient) }] : [];
  });
  if (!sourceStart || sourceEnd < sourceStart || !groupKey || !parts.length
    || parts.length !== value.parts.length || new Set(parts.map((part) => part.assemblyCtgId)).size !== parts.length) return null;
  // A persisted joined interval must be fully covered by surviving parts. Gaps
  // are not mergeable sequence and must not be resurrected on project reopen.
  const ranges = parts.map((part) => [Math.max(sourceStart, part.sourceStart), Math.min(sourceEnd, part.sourceEnd)])
    .filter(([start, end]) => end >= start).sort((a, b) => a[0] - b[0]);
  let next = sourceStart;
  for (const [start, end] of ranges) {
    if (start !== next) return null;
    next = Math.max(next, end + 1);
  }
  if (next <= sourceEnd) return null;
  return { sourceSeqId: positive(value.sourceSeqId), groupKey, instanceKey: String(value.instanceKey || groupKey), sourceStart, sourceEnd, parts,
    lineageCtgIds: [...new Set([...(Array.isArray(value.lineageCtgIds) ? value.lineageCtgIds : []), ...parts.map((part) => part.assemblyCtgId)].map(positive).filter(Boolean))].sort((a, b) => a - b),
    ...(Array.isArray(value.nativeCuts) ? { nativeCuts: [...new Set(value.nativeCuts.map(Number)
      .filter((cut) => Number.isSafeInteger(cut) && cut > 0 && cut >= sourceStart - 1 && cut <= sourceEnd))].sort((a, b) => a - b) } : {}),
    ...(Array.isArray(value.manualCuts) ? { manualCuts: [...new Set(value.manualCuts.map(Number)
      .filter((cut) => Number.isSafeInteger(cut) && cut > 0 && cut >= sourceStart - 1 && cut <= sourceEnd))].sort((a, b) => a - b) } : {}),
    ...(Array.isArray(value.suppressedCuts) ? { suppressedCuts: [...new Set(value.suppressedCuts.map(Number)
      .filter((cut) => Number.isSafeInteger(cut) && cut >= sourceStart && cut < sourceEnd))].sort((a, b) => a - b) } : {}),
  };
}

export function memberSourceInterval(member) {
  const local = normalizeLocalFragment(member?.localFragment);
  if (local) return local;
  const original = member?.sourceFragment;
  const length = positive(member?.lengthBp) || 1;
  const sourceStart = positive(original?.sourceStart) || 1;
  const sourceEnd = positive(original?.sourceEnd) || sourceStart + length - 1;
  return { sourceSeqId: positive(original?.sourceSeqId ?? member?.originSourceSeqId),
    groupKey: String(original?.groupKey || `assembly:${member?.assemblyCtgId}`),
    instanceKey: String(member?.entityKey || `assembly:${member?.assemblyCtgId}`),
    sourceStart, sourceEnd,
    nativeCuts: resolveManualSplitSourceCuts(member),
    parts: [{ assemblyCtgId: positive(member?.assemblyCtgId), sourceStart, sourceEnd,
      orient: orientation(member?.backingOrientation ?? member?.baseOrientation) }],
  };
}

export function memberEffectiveOrientation(member) {
  return (member?.baseOrientation === "-") !== Boolean(member?.flipped) ? "-" : "+";
}

export function memberCoordinateToSource(member, coordinate) {
  const range = memberSourceInterval(member);
  return member?.baseOrientation === "-" ? range.sourceEnd - coordinate + 1 : range.sourceStart + coordinate - 1;
}

export function sourceCoordinateToMember(member, coordinate) {
  const range = memberSourceInterval(member);
  return member?.baseOrientation === "-" ? range.sourceEnd - coordinate + 1 : coordinate - range.sourceStart + 1;
}

export function projectBackingCoordinate(member, assemblyCtgId, coordinate) {
  if (!member?.localFragment) {
    if (member?.assemblyCtgId !== Number(assemblyCtgId)) return null;
    return member.backingOrientation && member.backingOrientation !== member.baseOrientation
      ? member.lengthBp - Number(coordinate) + 1 : Number(coordinate);
  }
  const part = member.localFragment.parts.find((entry) => entry.assemblyCtgId === Number(assemblyCtgId));
  if (!part) return null;
  const source = part.orient === "-" ? part.sourceEnd - coordinate + 1 : part.sourceStart + coordinate - 1;
  return sourceCoordinateToMember(member, source);
}

export function memberBackingIds(member) {
  return [...new Set(member?.localFragment ? member.localFragment.parts.map((part) => part.assemblyCtgId)
    : [member?.assemblyCtgId])].filter(Boolean);
}

export function memberAnchorEndpointKey(member) {
  if (member?.localFragment) return `local:${member.entityKey}`;
  return buildSubviewAnchorEndpointKey({ role: member?.source?.role, contigId: member?.assemblyCtgId,
    datasetId: member?.source?.datasetId, source: member?.source?.sourceType,
    isMirror: member?.source?.mirrored, phasedTrackId: member?.source?.phasedTrackId,
    phasedTrackItemId: member?.source?.phasedItemId, phasedHaplotypeKey: member?.source?.hap });
}

function fragmentKey(member, range, start, end) {
  return `local:${encodeURIComponent(member.sourceKey || "")}:${range.sourceSeqId || 0}:${encodeURIComponent(range.groupKey)}:${encodeURIComponent(range.instanceKey)}:${start}-${end}`;
}

export function sliceLocalMember(member, sourceStart, sourceEnd) {
  const range = memberSourceInterval(member);
  if (!positive(sourceStart) || !positive(sourceEnd) || sourceStart < range.sourceStart
    || sourceEnd > range.sourceEnd || sourceEnd < sourceStart) return null;
  const localFragment = normalizeLocalFragment({ ...range, sourceStart, sourceEnd });
  if (!localFragment) return null;
  const reverse = memberEffectiveOrientation(member) === "-";
  return { ...member, entityKey: fragmentKey(member, range, sourceStart, sourceEnd),
    localFragment, lengthBp: sourceEnd - sourceStart + 1,
    xBp: Number(member.xBp || 0) + (reverse ? range.sourceEnd - sourceEnd : sourceStart - range.sourceStart) };
}

// Keep manual anchors attached to surviving source coordinates when an object
// becomes several fragments (or several fragments become one). Deleted points
// lose their anchor; they are never silently snapped to a surviving edge.
export function replaceLocalMembers(composition, replaced, replacements) {
  const keys = new Set(replaced.map((member) => member.entityKey));
  const oldEndpoints = new Map(replaced.map((member) => [memberAnchorEndpointKey(member), member]));
  const remap = (endpoint) => {
    const old = oldEndpoints.get(endpoint?.endpointKey);
    if (!old) return endpoint;
    const source = memberCoordinateToSource(old, endpoint.cutBp);
    const next = replacements.find((member) => {
      const range = memberSourceInterval(member);
      return range.groupKey === memberSourceInterval(old).groupKey
        && range.sourceStart <= source && range.sourceEnd >= source;
    });
    return next ? { ...endpoint, endpointKey: memberAnchorEndpointKey(next),
      contigId: next.assemblyCtgId, cutBp: sourceCoordinateToMember(next, source), lengthBp: next.lengthBp,
      baseOrientation: next.baseOrientation } : null;
  };
  const manualAnchors = (composition.manualAnchors || []).flatMap((anchor) => {
    const endpointA = remap(anchor.endpointA), endpointB = remap(anchor.endpointB);
    return endpointA && endpointB ? [{ ...anchor, endpointA, endpointB }] : [];
  });
  const members = [];
  let inserted = false;
  for (const member of composition.members) {
    if (!keys.has(member.entityKey)) { members.push(member); continue; }
    if (!inserted) { members.push(...replacements); inserted = true; }
  }
  const activeAnchors = (composition.activeAnchors || []).flatMap((anchor) => {
    if (!anchor.descriptor) return [anchor];
    const top = remap(anchor.descriptor.top), bottom = remap(anchor.descriptor.bottom);
    return top && bottom ? [{ ...anchor, descriptor: { top, bottom } }] : [];
  });
  return { ...composition, members, manualAnchors, activeAnchors };
}

export function splitLocalMember(composition, entityKey, cutAfter) {
  const member = composition.members.find((entry) => entry.entityKey === entityKey);
  if (!member) return { composition, changed: false };
  const range = memberSourceInterval(member);
  if (!positive(cutAfter) || cutAfter < range.sourceStart || cutAfter >= range.sourceEnd) return { composition, changed: false };
  const splitSource = { ...member, localFragment: normalizeLocalFragment({ ...range,
    manualCuts: [...(range.manualCuts || []), cutAfter] }) };
  const parts = [sliceLocalMember(splitSource, range.sourceStart, cutAfter), sliceLocalMember(splitSource, cutAfter + 1, range.sourceEnd)];
  if (parts.some((part) => !part)) return { composition, changed: false };
  return { composition: replaceLocalMembers(composition, [member], parts), changed: true, members: parts };
}

// Materialize only the clicked interval and its surviving remainders. This is
// also used by anchor-derived pieces: deactivating an anchor cannot restore a
// deleted interval or collapse an independently moved/flipped object.
export function isolateLocalMemberInterval(composition, entityKey, startBp, endBp) {
  const member = composition.members.find((entry) => entry.entityKey === entityKey);
  if (!member) return { composition, changed: false, member: null };
  if (!positive(startBp) || !positive(endBp) || startBp > endBp || endBp > member.lengthBp) {
    return { composition, changed: false, member: null };
  }
  const first = memberCoordinateToSource(member, startBp), last = memberCoordinateToSource(member, endBp);
  const start = Math.min(first, last), end = Math.max(first, last);
  const range = memberSourceInterval(member);
  if (range.sourceStart === start && range.sourceEnd === end) return { composition, changed: false, member };
  const middle = sliceLocalMember(member, start, end);
  const parts = [range.sourceStart < start ? sliceLocalMember(member, range.sourceStart, start - 1) : null,
    middle, end < range.sourceEnd ? sliceLocalMember(member, end + 1, range.sourceEnd) : null].filter(Boolean);
  return { composition: replaceLocalMembers(composition, [member], parts), changed: true, member: middle };
}

export function deleteLocalMember(composition, entityKey) {
  const member = composition.members.find((entry) => entry.entityKey === entityKey);
  return member ? { composition: replaceLocalMembers(composition, [member], []), changed: true }
    : { composition, changed: false };
}

export function resolveLocalMergeNeighbor(composition, entityKey, side) {
  const member = composition.members.find((entry) => entry.entityKey === entityKey);
  if (!member || !["left", "right"].includes(side)) return null;
  const range = memberSourceInterval(member), orient = memberEffectiveOrientation(member);
  const low = (side === "left") !== (orient === "-");
  const matches = composition.members.filter((entry) => {
    if (entry === member || entry.lane !== member.lane || entry.sourceKey !== member.sourceKey
      || memberEffectiveOrientation(entry) !== orient) return false;
    const other = memberSourceInterval(entry);
    return other.sourceSeqId === range.sourceSeqId && other.groupKey === range.groupKey
      && (low ? other.sourceEnd + 1 === range.sourceStart : range.sourceEnd + 1 === other.sourceStart);
  });
  return matches.length === 1 ? matches[0] : null;
}

export function mergeLocalMember(composition, entityKey, side) {
  const member = composition.members.find((entry) => entry.entityKey === entityKey);
  const neighbor = resolveLocalMergeNeighbor(composition, entityKey, side);
  if (!member || !neighbor) return { composition, changed: false };
  const a = memberSourceInterval(member), b = memberSourceInterval(neighbor);
  const sourceStart = Math.min(a.sourceStart, b.sourceStart), sourceEnd = Math.max(a.sourceEnd, b.sourceEnd);
  const parts = [...new Map([...a.parts, ...b.parts].map((part) => [part.assemblyCtgId, part])).values()];
  const localFragment = normalizeLocalFragment({ ...a, sourceStart, sourceEnd, parts,
    lineageCtgIds: [...(a.lineageCtgIds || []), ...(b.lineageCtgIds || [])],
    nativeCuts: [...(a.nativeCuts || []), ...(b.nativeCuts || [])],
    manualCuts: [...(a.manualCuts || []), ...(b.manualCuts || [])].filter((cut) => cut !== Math.min(a.sourceEnd, b.sourceEnd)),
    suppressedCuts: [...(a.suppressedCuts || []), ...(b.suppressedCuts || []), Math.min(a.sourceEnd, b.sourceEnd)] });
  if (!localFragment) return { composition, changed: false };
  const merged = { ...member, entityKey: fragmentKey(member, a, sourceStart, sourceEnd), localFragment,
    lengthBp: sourceEnd - sourceStart + 1, baseOrientation: memberEffectiveOrientation(member), flipped: false,
    xBp: Math.min(member.xBp, neighbor.xBp), order: Math.min(member.order, neighbor.order) };
  return { composition: replaceLocalMembers(composition, [member, neighbor], [merged]), changed: true, member: merged };
}

// Clip BOTH alignment ends with one common parametric interval. Independently
// clamping endpoints fabricates bands across deleted intervals or unrelated parts.
export function clipLocalAlignment(top, bottom, coordinates) {
  let { topStart, topEnd, bottomStart, bottomEnd } = coordinates;
  const reversed = coordinates.strand === "-";
  if (reversed) [bottomStart, bottomEnd] = [bottomEnd, bottomStart];
  let low = 0, high = 1;
  for (const [start, end, length] of [[topStart, topEnd, top.lengthBp], [bottomStart, bottomEnd, bottom.lengthBp]]) {
    if (![start, end, length].every(Number.isFinite)) return null;
    if (start === end) { if (start < 1 || start > length) return null; continue; }
    const a = (1 - start) / (end - start), b = (length - start) / (end - start);
    low = Math.max(low, Math.min(a, b)); high = Math.min(high, Math.max(a, b));
  }
  if (high < low) return null;
  const lerp = (a, b, t) => a + (b - a) * t;
  return { topStart: lerp(topStart, topEnd, low), topEnd: lerp(topStart, topEnd, high),
    bottomStart: Math.min(lerp(bottomStart, bottomEnd, low), lerp(bottomStart, bottomEnd, high)),
    bottomEnd: Math.max(lerp(bottomStart, bottomEnd, low), lerp(bottomStart, bottomEnd, high)) };
}

export function projectLocalAlignment(top, bottom, topId, bottomId, coordinates) {
  const a = projectBackingCoordinate(top, topId, coordinates.topStart);
  const b = projectBackingCoordinate(top, topId, coordinates.topEnd);
  const c = projectBackingCoordinate(bottom, bottomId, coordinates.bottomStart);
  const d = projectBackingCoordinate(bottom, bottomId, coordinates.bottomEnd);
  if ([a, b, c, d].some((value) => value === null || !Number.isFinite(value))) return null;
  const reversed = ((coordinates.strand === "-") !== (a > b)) !== (c > d);
  const strand = reversed ? "-" : "+";
  const clipped = clipLocalAlignment(top, bottom, { topStart: Math.min(a, b), topEnd: Math.max(a, b),
    bottomStart: Math.min(c, d), bottomEnd: Math.max(c, d), strand });
  return clipped ? { ...clipped, strand } : null;
}

export function filterLocalAnchorCuts(member, cuts) {
  const suppressed = new Set(member.localFragment?.suppressedCuts || []);
  return (cuts || []).filter((cut) => !suppressed.has(memberCoordinateToSource(member, cut)
    - (member.baseOrientation === "-" ? 0 : 1)));
}

export function projectLocalNRegions(member, candidates, compatible = (candidate) => candidate.sourceKey === member.sourceKey) {
  if (!member.localFragment) return null;
  const regions = [];
  for (const id of memberBackingIds(member)) {
    const candidate = candidates.find((entry) => entry.assemblyCtgId === id && compatible(entry));
    for (const region of candidate?.ctg?.nRegions || []) {
      const a = projectBackingCoordinate(member, id, Number(region.ctgStart ?? region.ctg_start ?? region.startBp));
      const b = projectBackingCoordinate(member, id, Number(region.ctgEnd ?? region.ctg_end ?? region.endBp));
      if (![a, b].every(Number.isFinite)) continue;
      const ctgStart = Math.max(1, Math.min(a, b)), ctgEnd = Math.min(member.lengthBp, Math.max(a, b));
      if (ctgEnd >= ctgStart) regions.push({ ...region, ctgStart, ctgEnd });
    }
  }
  return regions;
}

// Explicit local-to-Final-Path append expands a joined local interval into the
// actual backing ranges in source order. No local edit rewrites existing paths.
export function resolveLocalFinalPathContexts(members, context) {
  const member = members.find((entry) => entry.entityKey === context?.localFragmentEntityKey);
  if (!member) return null;
  const isolated = context.start != null || context.end != null
    ? isolateLocalMemberInterval({ members }, member.entityKey, Number(context.start), Number(context.end)).member
    : member;
  if (!isolated) return null;
  const range = memberSourceInterval(isolated);
  let next = range.sourceStart;
  const parts = [];
  for (const part of [...range.parts].sort((a, b) => a.sourceStart - b.sourceStart)) {
    const first = Math.max(next, range.sourceStart, part.sourceStart), last = Math.min(range.sourceEnd, part.sourceEnd);
    if (last < first) continue;
    if (first > next) return null;
    parts.push({ part, first, last }); next = last + 1;
  }
  if (next <= range.sourceEnd) return null;
  const reverse = memberEffectiveOrientation(isolated) === "-";
  if (reverse) parts.reverse();
  return parts.map(({ part, first, last }) => {
    const a = first - part.sourceStart + 1, b = last - part.sourceStart + 1;
    return { ...context, localFragmentEntityKey: undefined, assemblyCtgId: part.assemblyCtgId,
      // Normal assembly ranges are relative to source orientation, whereas Ref
      // segments use their explicit orient and ascending member coordinates.
      ...(member.source.role === "ref" ? { orient: undefined, refOrient: reverse ? "-" : "+", start: a, end: b }
        : { orient: "+", refOrient: "+", start: reverse ? b : a, end: reverse ? a : b }),
    };
  });
}

export function memberActiveBackingParts(member) {
  const range = memberSourceInterval(member);
  return range.parts.filter((part) => part.sourceStart <= range.sourceEnd && part.sourceEnd >= range.sourceStart);
}


// Materialize rendered anchor pieces without inserting a history operation.
// The following drag/edit owns the partition and motion in one undo step.
export function materializeLocalIntervals(composition, descriptors) {
  let next = composition, changed = false;
  const selectedKeys = new Map();
  for (const original of composition.members) {
    const entries = descriptors.filter((entry) => entry.memberKey === original.entityKey);
    if (!entries.length) continue;
    const cuts = [...new Set([1, original.lengthBp + 1, ...entries.flatMap((entry) => [entry.start, entry.end + 1])])]
      .filter((value) => Number.isSafeInteger(value) && value >= 1 && value <= original.lengthBp + 1).sort((a, b) => a - b);
    if (cuts.length === 2) { entries.forEach((entry) => selectedKeys.set(entry.key, original.entityKey)); continue; }
    const replacements = cuts.slice(0, -1).map((start, index) => {
      const end = cuts[index + 1] - 1;
      const a = memberCoordinateToSource(original, start), z = memberCoordinateToSource(original, end);
      const member = sliceLocalMember(original, Math.min(a, z), Math.max(a, z));
      entries.filter((entry) => entry.start === start && entry.end === end).forEach((entry) => selectedKeys.set(entry.key, member.entityKey));
      return member;
    });
    if (replacements.some((member) => !member)) return { composition, changed: false, selectedKeys: new Map() };
    next = replaceLocalMembers(next, [original], replacements);
    changed = true;
  }
  return { composition: next, changed, selectedKeys };
}
