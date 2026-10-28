import { layoutProjectPreviewPath } from "./assembly/final-path-visual-layout.js";

// Presentation only: Final Path owns the visual positions (including its short
// segment floor). Source metadata and biological coordinates remain untouched.
export function layoutProjectPreviewCard(card, viewportWidth) {
  const width = Math.max(0, Number(viewportWidth) || 0);
  const scale = width / Math.max(1, card.domain.end - card.domain.start);
  const paths = new Map(card.paths.map(path => [path.name,
    layoutProjectPreviewPath(path.parts, width, card.domain)]));
  const contextPath = card.paths.find(path => path.parts.length);
  const contextLayouts = contextPath && paths.get(contextPath.name);
  const project = position => {
    if (!contextPath) return (position - card.domain.start) * scale;
    const index = contextPath.parts.findIndex(part => position <= part.start + part.length);
    if (index < 0) {
      const last = contextPath.parts.at(-1), layout = contextLayouts.at(-1);
      return layout.x + layout.width + (position - last.start - last.length) * scale;
    }
    const part = contextPath.parts[index], layout = contextLayouts[index];
    if (position < part.start) return layout.x + (position - part.start) * scale;
    return layout.x + (position - part.start) / part.length * layout.width;
  };
  const clip = (start, end) => {
    const x = Math.min(width, Math.max(0, start));
    return { x, width: Math.max(0, Math.min(width, end) - x) };
  };
  const adopted = (patch, reference = false) => {
    const part = patch.part, layout = paths.get(part.pathName)?.[part.index];
    if (!layout || !(part.length > 0)) return null;
    const source = part.source;
    const offset = reference ? 0 : source?.orient === "-"
      ? source.end - (patch.coveredEnd ?? source.end)
      : (patch.coveredStart ?? source?.start ?? 0) - (source?.start ?? 0);
    const x = layout.x + offset / part.length * layout.width;
    return { ...clip(x, x + (patch.end - patch.start) / part.length * layout.width), patch };
  };
  const body = (start, length, patches, reference = false) => {
    const highlights = patches.map(patch => adopted(patch, reference)).filter(Boolean);
    if (!highlights.length) return { ...clip(project(start), project(start + length)), highlights };
    // Preserve unused source tails, but never extrapolate an 8px tiny donor's
    // enlarged scale over its entire chromosome-length body. Each adopted use
    // gets its own exact path mapping, including repeated and reversed uses.
    const before = Math.max(0, Math.min(...patches.map(patch => patch.start)));
    const after = Math.max(0, length - Math.max(...patches.map(patch => patch.end)));
    return { ...clip(Math.min(...highlights.map(part => part.x)) - before * scale,
      Math.max(...highlights.map(part => part.x + part.width)) + after * scale), highlights };
  };
  const reference = card.reference || { start: 0, reverse: false };
  const refPatches = card.refHighlights.map(patch => ({ ...patch,
    start: reference.reverse ? card.refLength - patch.end : patch.start,
    end: reference.reverse ? card.refLength - patch.start : patch.end }));
  return { paths,
    reference: body(reference.start, card.refLength, refPatches, true),
    tracks: card.tracks.map(track => track.positioned.map(item => body(item.start, item.length, item.highlights))) };
}

const place = (node, layout, origin = 0) => {
  if (!node || !layout) return;
  node.style.left = `${layout.x - origin}px`;
  node.style.width = `${layout.width}px`;
  node.style.minWidth = "0";
};
const fitLabel = label => {
  if (label?.style) label.style.visibility = Number(label.scrollWidth || 0) > Number(label.clientWidth || 0) ? "hidden" : "";
};

// Called after path measurement, on first paint, cached remount and resize.
export function syncProjectPreviewSources(node, card) {
  const plot = node.querySelector?.(".project-preview-final-plot, .project-preview-plot");
  if (!(plot?.clientWidth > 0)) return;
  const geometry = layoutProjectPreviewCard(card, plot.clientWidth);
  const apply = (source, layout) => {
    place(source, layout);
    [...(source?.querySelectorAll(".project-preview-used") || [])].forEach((patch, index) =>
      place(patch, layout.highlights[index], layout.x));
    fitLabel(source?.querySelector("[data-preview-source-fit-label]"));
  };
  apply(node.querySelector(".project-preview-reference"), geometry.reference);
  [...node.querySelectorAll(".project-preview-source-plots")].forEach((track, trackIndex) => {
    [...track.querySelectorAll(".project-preview-contig")].forEach((source, index) =>
      apply(source, geometry.tracks[trackIndex][index]));
  });
}
