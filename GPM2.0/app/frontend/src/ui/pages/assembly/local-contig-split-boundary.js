import { collectSubviewAnchorScene } from "./subview-anchor-objects.js";
import { memberAnchorEndpointKey, memberCoordinateToSource, memberSourceInterval } from "./subview-fragment-model.js";

function localAlignmentEdges(state, host, member) {
  const compositionMode = state.assembly.subview?.summary?.mode === "composition";
  const key = memberAnchorEndpointKey(member), range = memberSourceInterval(member);
  return collectSubviewAnchorScene(host).flatMap((scene) => ["top", "bottom"].flatMap((lane) => {
    const endpoint = scene.descriptor?.[lane];
    if (!endpoint) return [];
    const matches = endpoint.endpointKey === key || !compositionMode
      && endpoint.contigId === member.assemblyCtgId && member.lane === lane
      && (!endpoint.sourceRole || endpoint.sourceRole === member.source.role);
    if (!matches) return [];
    let coordinate = endpoint.baseCutBp ?? endpoint.cutBp;
    if (!endpoint.baseCutBp && !compositionMode && member.flipped) coordinate = member.lengthBp - coordinate + 1;
    if (!Number.isSafeInteger(coordinate) || coordinate < 1 || coordinate > member.lengthBp) return [];
    const sourceBp = endpoint.sourcePosition ?? memberCoordinateToSource(member, coordinate);
    if (sourceBp < range.sourceStart || sourceBp > range.sourceEnd) return [];
    const cutAfter = Number.isSafeInteger(endpoint.sourceCutAfter) ? endpoint.sourceCutAfter
      : sourceBp - (member.baseOrientation === "-" ? 0 : 1);
    return [{ scene, sourceBp, cutAfter }];
  }));
}

export function resolveLocalAlignmentRange(state, host, member) {
  const edges = localAlignmentEdges(state, host, member).filter(({ scene }) => scene.kind === "evidence");
  if (!edges.length) return null;
  return { low: Math.min(...edges.map((edge) => edge.sourceBp)) - 1,
    high: Math.max(...edges.map((edge) => edge.sourceBp)) };
}

export function resolveLocalSplitBoundaries({ range, selectedRange, orient, anchorCuts, alignmentRange }) {
  let low, high;
  if (anchorCuts.length) {
    const starts = [range.sourceStart, ...anchorCuts.map((cut) => cut + 1)];
    const ends = [...anchorCuts, range.sourceEnd];
    const index = starts.findIndex((start, i) => start === selectedRange?.sourceStart && ends[i] === selectedRange?.sourceEnd);
    if (index < 0) return { left: null, right: null };
    low = starts[index] - 1; high = ends[index];
  } else {
    low = alignmentRange?.low; high = alignmentRange?.high;
  }
  const valid = (cut) => Number.isSafeInteger(cut) && cut >= range.sourceStart && cut < range.sourceEnd ? cut : null;
  return { left: valid(orient === "-" ? high : low), right: valid(orient === "-" ? low : high) };
}

export function highlightLocalSplitBoundary(host, state, member, cutAfter, anchored) {
  const created = [];
  for (const edge of localAlignmentEdges(state, host, member)) {
    if (anchored ? edge.cutAfter !== cutAfter : edge.scene.kind !== "evidence"
      || edge.sourceBp !== cutAfter && edge.sourceBp !== cutAfter + 1) continue;
    const source = edge.scene.node, svg = source?.ownerSVGElement;
    const doc = source?.ownerDocument || host?.ownerDocument;
    if (!svg || !doc?.createElementNS) continue;
    const line = doc.createElementNS("http://www.w3.org/2000/svg", "line");
    for (const attribute of ["x1", "x2", "y1", "y2"]) line.setAttribute(attribute, source.getAttribute(attribute));
    line.setAttribute("class", "subview-anchor-line is-focused track-split-preview");
    line.setAttribute("stroke", "red"); line.setAttribute("stroke-width", "3");
    line.setAttribute("pointer-events", "none");
    svg.append(line); created.push(line);
  }
  return () => created.forEach((line) => line.remove());
}
