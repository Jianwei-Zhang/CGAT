import { memberAnchorEndpointKey, memberCoordinateToSource, memberSourceInterval, splitLocalMember } from "./subview-fragment-model.js";

export const wholeMemberContext = (context) => ({ ...context, start: undefined, end: undefined, fragmentKey: undefined });
export function normalizeAnchorCuts(cuts, range) {
  return [...new Set((cuts || []).map(Number).filter((cut) => Number.isSafeInteger(cut)
    && cut >= range.sourceStart && cut < range.sourceEnd))].sort((a,b) => a-b);
}
export function localAnchorCuts(composition, member) {
  const key = memberAnchorEndpointKey(member), range = memberSourceInterval(member);
  const endpoints = [...(composition.manualAnchors || []).flatMap((a) => [a.endpointA,a.endpointB]),
    ...(composition.activeAnchors || []).flatMap((a) => [a.descriptor?.top,a.descriptor?.bottom])];
  return normalizeAnchorCuts(endpoints.filter((e) => e?.endpointKey === key).map((e) =>
    Number.isSafeInteger(e.sourceCutAfter) ? e.sourceCutAfter
      : memberCoordinateToSource(member, e.cutBp) - (member.baseOrientation === "-" ? 0 : 1)), range);
}
export function splitLocalMemberAtAnchors(composition, entityKey, cuts) {
  const member = composition.members.find((m) => m.entityKey === entityKey);
  if (!member) return { composition, changed: false };
  const normalized = normalizeAnchorCuts(cuts, memberSourceInterval(member));
  if (!normalized.length) return { composition, changed: false };
  let current = composition, remaining = member;
  for (const cut of normalized) {
    const result = splitLocalMember(current, remaining.entityKey, cut);
    if (!result.changed) return { composition, changed: false };
    current = result.composition; remaining = result.members[1];
  }
  return { composition: current, changed: true };
}
export function anchorSplitRanges(model, cuts) {
  const boundaries = [model.sourceStart, ...normalizeAnchorCuts(cuts, model).map((c) => c+1), model.sourceEnd+1];
  const ranges = boundaries.slice(0,-1).map((start,i) => [start,boundaries[i+1]-1]);
  return model.orient === "-" ? ranges.reverse() : ranges;
}
