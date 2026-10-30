import { deriveSubviewContigFragments } from "./subview-anchor-state.js";
import { mainActiveAnchorKeys, mainAlignmentEndpointKey } from "./main-alignment-anchors.js";
import { resolveTrackCtgOrient } from "./track-label-geometry.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveHitIdentityPct } from "./track-render-geometry.js";

// These intervals are presentation/hit targets, not new assembly contigs.
export function resolveMainAnchorFragments({ ctg, chrName, role, datasetId, active, prefs }) {
  if (!active?.size || !["primary", "support"].includes(role)) return [];
  const sourceStart = Number(ctg.sourceFragment?.sourceStart || 1);
  const sourceEnd = Number(ctg.sourceFragment?.sourceEnd || ctg.totalLength);
  if (!Number.isSafeInteger(sourceStart) || !Number.isSafeInteger(sourceEnd) || sourceEnd <= sourceStart) return [];
  const cuts = new Set();
  for (const hit of ctg.hits || []) {
    const start = Number(hit.queryStart ?? hit.query_start), end = Number(hit.queryEnd ?? hit.query_end);
    if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < sourceStart || end > sourceEnd || start > end
      || (hit.chrName && hit.chrName !== chrName)
      || !(Number(hit.blockLength ?? hit.block_length) >= prefs.alignmentLength)
      || !(resolveHitIdentityPct(hit) >= prefs.minIdentityPct)) continue;
    for (const side of ["left", "right"]) {
      if (!active.has(mainAlignmentEndpointKey(chrName, ctg, hit, side, role, datasetId))) continue;
      const cut = (side === "left") !== (resolveTrackCtgOrient(ctg) === "-") ? start - 1 : end;
      if (cut >= sourceStart && cut < sourceEnd) cuts.add(cut);
    }
  }
  if (!cuts.size) return [];
  // The shared Local View helper takes the first base of the following interval.
  const length = sourceEnd - sourceStart + 1;
  const fragments = deriveSubviewContigFragments({
    contig: { assemblyCtgId: ctg.assemblyCtgId, role, lengthBp: length },
    anchorCuts: [...cuts].map((cut) => cut - sourceStart + 2),
  }).map((fragment) => ({ start: fragment.start + sourceStart - 1, end: fragment.end + sourceStart - 1 }));
  return resolveTrackCtgOrient(ctg) === "-" ? fragments.reverse() : fragments;
}

export function renderMainAnchorFragments({ ctg, rect, y, height, escapeHtml, ...context }) {
  const fragments = resolveMainAnchorFragments({ ctg, ...context });
  if (!fragments.length) return "";
  const start = Number(ctg.sourceFragment?.sourceStart || 1);
  const end = Number(ctg.sourceFragment?.sourceEnd || ctg.totalLength);
  const length = end - start + 1, reverse = resolveTrackCtgOrient(ctg) === "-";
  return fragments.map((fragment, index) => {
    const left = rect.x + (reverse ? end - fragment.end : fragment.start - start) / length * rect.width;
    const width = Math.max(1, (fragment.end - fragment.start + 1) / length * rect.width);
    const geometry = `x="${left.toFixed(2)}" y="${y.toFixed(2)}" width="${width.toFixed(2)}" height="${height}"`;
    return `<rect class="main-anchor-fragment-hit-zone" ${geometry} fill="transparent" pointer-events="all"
      data-main-fragment-start="${fragment.start}" data-main-fragment-end="${fragment.end}"
      data-main-fragment-role="${context.role}">
      <desc data-app-tooltip-source>${escapeHtml(`${ctg.name || ctg.assemblyCtgId}: ${fragment.start.toLocaleString()}–${fragment.end.toLocaleString()}`)}</desc></rect>
      <rect class="main-anchor-fragment-outline" ${geometry} rx="4" ry="4" fill="none" stroke-width="2.5" pointer-events="none" />
      ${index ? `<line class="main-anchor-fragment-separator" data-main-fragment-role="${context.role}"
        x1="${left.toFixed(2)}" x2="${left.toFixed(2)}" y1="${y.toFixed(2)}" y2="${(y + height).toFixed(2)}" pointer-events="none" />` : ""}`;
  }).join("");
}

// Update only the fragment overlays, retaining the live track/scroll/drag nodes.
export function patchMainAnchorFragments(host, assembly, escapeHtml) {
  const active = mainActiveAnchorKeys(assembly), prefs = resolveTrackPrefs(assembly.trackView);
  for (const layer of host?.querySelectorAll?.('[data-main-anchor-fragments="1"]') || []) {
    const group = layer.closest?.("[data-track-contig-id][data-track-role]");
    if (!group) continue;
    const role = group.getAttribute("data-track-role"), id = Number(group.getAttribute("data-track-contig-id"));
    const datasetId = Number(group.getAttribute("data-track-dataset-id"));
    const candidates = role === "primary" ? assembly.chrCtgs : [
      ...(assembly.supportChrCtgs || []).filter((c) => Number(c.datasetId ?? assembly.supportDatasetId) === datasetId),
      ...(assembly.supportMirroredCtgs || []).filter((c) => Number(c.datasetId) === datasetId
        && (!c.chrName || c.chrName === assembly.selectedChrName)),
    ];
    const ctg = (candidates || []).find((c) => Number(c.assemblyCtgId) === id);
    const x = Number(group.getAttribute("data-track-rect-x")), y = Number(group.getAttribute("data-track-rect-y"));
    const width = Number(group.getAttribute("data-track-rect-width")), height = Number(group.getAttribute("data-track-rect-height"));
    const disabled = role === "primary" && assembly.activeHitsTrackKey && assembly.activeHitsTrackKey !== "primary";
    const markup = ctg && !disabled && [x, y, width, height].every(Number.isFinite)
      ? renderMainAnchorFragments({ ctg, chrName: assembly.selectedChrName, role, datasetId, active, prefs,
        rect: { x, width }, y, height, escapeHtml }) : "";
    layer.innerHTML = markup;
    if (markup) group.setAttribute("data-main-anchor-segmented", "1");
    else group.removeAttribute("data-main-anchor-segmented");
  }
}
