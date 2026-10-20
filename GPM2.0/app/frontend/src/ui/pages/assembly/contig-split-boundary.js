import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveHitIdentityPct } from "./track-render-geometry.js";
import { resolveTrackCtgOrient } from "./track-label-geometry.js";

export const splitCopy = {
  zh: { title: "分割 contig", left: "在比对最左侧分割", right: "在比对最右侧分割",
    unavailable: "没有可用的比对边界，或边界已在 contig 端部", stale: "比对或当前视图已变化，请重新打开菜单。",
    done: "已分割 contig；两段保留在原轨道，可撤销。" },
  en: { title: "Split contig", left: "Split at leftmost alignment", right: "Split at rightmost alignment",
    unavailable: "No alignment boundary, or the boundary is already at the contig end", stale: "Alignment or view changed. Reopen the menu.",
    done: "Contig split; both fragments remain on the original track. Undo is available." },
};

// Use the same per-hit length/identity filters as the main Ref-band renderer.
// The viewport does not crop biological evidence. Current chromosome data only.
export function resolveContigSplitBoundaries(assembly, assemblyCtgId) {
  if (assembly?.activeHitsTrackKey && assembly.activeHitsTrackKey !== "primary") return null;
  const ctg = assembly?.chrCtgs?.find((c) => Number(c.assemblyCtgId) === Number(assemblyCtgId));
  if (!ctg || (assembly.hiddenPrimaryCtgIds || []).map(Number).includes(Number(assemblyCtgId))) return null;
  const prefs = resolveTrackPrefs(assembly.trackView);
  const sourceStart = Number(ctg.sourceFragment?.sourceStart || 1);
  const sourceEnd = Number(ctg.sourceFragment?.sourceEnd || ctg.totalLength);
  const reverse = resolveTrackCtgOrient(ctg) === "-";
  const hits = (ctg.hits || []).filter((h) => Number(h.blockLength ?? h.block_length) >= prefs.alignmentLength
    && resolveHitIdentityPct(h) >= prefs.minIdentityPct
    && !(h.chrName && h.chrName !== assembly.selectedChrName));
  const intervals = hits.map((h) => [Number(h.queryStart ?? h.query_start), Number(h.queryEnd ?? h.query_end)])
    .filter(([a,b]) => Number.isSafeInteger(a) && Number.isSafeInteger(b) && a >= sourceStart && b <= sourceEnd && a <= b);
  if (!intervals.length) return null;
  const low = Math.min(...intervals.map(([a]) => a)) - 1;
  const high = Math.max(...intervals.map(([,b]) => b));
  const valid = (cut) => cut >= sourceStart && cut < sourceEnd ? cut : null;
  return { assemblyCtgId: Number(assemblyCtgId), left: valid(reverse ? high : low), right: valid(reverse ? low : high),
    reverse, minAlignmentLength: prefs.alignmentLength, minIdentityPct: prefs.minIdentityPct };
}

// Attach the preview to the exact rendered band edge, not to a guessed Ref X.
export function highlightContigSplitBoundary(host, boundary, side) {
  if (!boundary || boundary[side] == null) return () => {};
  const created = [];
  const lowSide = (side === "left") !== boundary.reverse;
  const attribute = lowSide ? "data-band-query-start" : "data-band-query-end";
  const coordinate = boundary[side] + (lowSide ? 1 : 0);
  const selector = `[data-band-track-role="primary"][data-band-contig-id="${boundary.assemblyCtgId}"]`;
  for (const band of host.querySelectorAll?.(selector) || []) {
    if (Number(band.getAttribute(attribute)) !== coordinate) continue;
    const points = band.getAttribute(`data-band-${side}-anchor`);
    if (!points || !band.ownerSVGElement) continue;
    const doc = band.ownerDocument || host.ownerDocument;
    if (!doc?.createElementNS) continue;
    const group = doc.createElementNS("http://www.w3.org/2000/svg", "g");
    group.setAttribute("class", "track-split-preview");
    group.setAttribute("data-contig-split-preview", "1");
    const line = doc.createElementNS("http://www.w3.org/2000/svg", "polyline");
    line.setAttribute("points", points);
    line.setAttribute("class", "subview-anchor-line is-focused track-split-preview-line");
    group.append(line);
    const [x,y] = points.split(" ")[0].split(",");
    const dot = doc.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx",x); dot.setAttribute("cy",y); dot.setAttribute("r","5");
    group.append(dot); band.ownerSVGElement.append(group); created.push(group);
  }
  return () => created.forEach((node) => node.remove());
}

export function bandBoundaryAnchors(points, direction, reversed) {
  const p = points.split(" ");
  if (direction === "down") return { left: `${p[0]} ${p[3]}`, right: `${p[1]} ${p[2]}` };
  return reversed ? { left: `${p[2]} ${p[1]}`, right: `${p[3]} ${p[0]}` }
    : { left: `${p[3]} ${p[0]}`, right: `${p[2]} ${p[1]}` };
}
