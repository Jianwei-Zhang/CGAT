import { normalizeSubviewAnchorStateByKey, toggleSubviewAnchorEdge } from "./subview-anchor-state.js";
import { resolveTrackCtgOrient } from "./track-label-geometry.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveHitIdentityPct } from "./track-render-geometry.js";

// Reuse the persisted anchor registry, but never overwrite a Local View's state/history.
export const mainAnchorStateKey = (chrName) => `main-view|${encodeURIComponent(chrName || "")}`;
export function mainAlignmentKey(chrName, ctg, hit, role = "primary", datasetId = 0) {
  return JSON.stringify([chrName, role, role === "primary" ? 0 : Number(datasetId || 0),
    Number(ctg.assemblyCtgId), Number(ctg.sourceStart ?? ctg.sourceFragment?.sourceStart ?? 1),
    Number(ctg.sourceEnd ?? ctg.sourceFragment?.sourceEnd ?? ctg.totalLength), resolveTrackCtgOrient(ctg),
    Number(hit.queryStart ?? hit.query_start), Number(hit.queryEnd ?? hit.query_end),
    Number(hit.refStart ?? hit.ref_start), Number(hit.refEnd ?? hit.ref_end), hit.strand === "-" ? "-" : "+"]);
}
// Anchor identity follows an immutable source endpoint, so splitting/flipping a contig
// does not discard the other anchors. Dataset/role/chromosome prevent cross-track leakage.
export function mainAlignmentEndpointKey(chrName, ctg, hit, edge, role = "primary", datasetId = 0) {
  const low = (edge === "left") !== (resolveTrackCtgOrient(ctg) === "-");
  const cutAfter = low ? Number(hit.queryStart ?? hit.query_start) - 1 : Number(hit.queryEnd ?? hit.query_end);
  const refBp = low !== (hit.strand === "-") ? Number(hit.refStart ?? hit.ref_start) : Number(hit.refEnd ?? hit.ref_end);
  const sourceSeqId = Number(ctg.originSourceSeqId ?? ctg.sourceFragment?.sourceSeqId ?? ctg.sourceSeqId);
  if (!Number.isSafeInteger(cutAfter) || cutAfter < 0 || !Number.isSafeInteger(refBp) || refBp < 1) return "";
  return JSON.stringify([chrName, role, role === "primary" ? 0 : Number(datasetId || 0),
    sourceSeqId > 0 ? `source:${sourceSeqId}` : `ctg:${ctg.assemblyCtgId}`, cutAfter, refBp]);
}
export function mainActiveAnchorKeys(assembly) {
  return new Set((assembly?.subviewAnchorStateByKey?.[mainAnchorStateKey(assembly.selectedChrName)]?.activeAnchors || [])
    .map(({ hitKey }) => hitKey));
}

export function resolveMainAlignmentContextTarget(target) {
  const node = target?.closest?.("[data-main-alignment-key]");
  if (!node) return null;
  const hitKey = node.getAttribute("data-main-alignment-key");
  const edge = node.getAttribute("data-main-anchor-edge");
  if (!hitKey) return null;
  return { hitKey, ...(edge === "left" || edge === "right" ? { edge } : {}) };
}

export function findMainAlignment(assembly, context) {
  if (!context?.hitKey) return null;
  const prefs = resolveTrackPrefs(assembly.trackView);
  for (const [role, ctgs] of [["primary", assembly.chrCtgs], ["support", [...(assembly.supportChrCtgs || []),
    ...(assembly.supportMirroredCtgs || []).filter((c) => !c.chrName || c.chrName === assembly.selectedChrName)]]]) {
    for (const ctg of ctgs || []) {
      if (role === "primary" && (assembly.hiddenPrimaryCtgIds || []).map(Number).includes(Number(ctg.assemblyCtgId))) continue;
      for (const hit of ctg.hits || []) {
        if (hit.chrName && hit.chrName !== assembly.selectedChrName
          || Number(hit.blockLength ?? hit.block_length) < prefs.alignmentLength
          || resolveHitIdentityPct(hit) < prefs.minIdentityPct) continue;
        const datasetId = ctg.datasetId ?? assembly.supportDatasetId;
        if (mainAlignmentKey(assembly.selectedChrName, ctg, hit, role, datasetId) === context.hitKey) {
          return { ctg, hit, role };
        }
      }
    }
  }
  return null;
}

export function toggleMainAlignmentAnchorState(assembly, context) {
  const match = findMainAlignment(assembly, context);
  if (!["left", "right"].includes(context?.edge) || !match) return null;
  const hitKey = mainAlignmentEndpointKey(assembly.selectedChrName, match.ctg, match.hit, context.edge,
    match.role, match.ctg.datasetId ?? assembly.supportDatasetId);
  if (!hitKey) return null;
  const key = mainAnchorStateKey(assembly.selectedChrName);
  const states = normalizeSubviewAnchorStateByKey(assembly.subviewAnchorStateByKey);
  const current = states[key] || { activeAnchors: [], manualAnchors: [] };
  const activeAnchors = toggleSubviewAnchorEdge(current.activeAnchors, { hitKey, edge: "left" });
  if (activeAnchors.length) states[key] = { ...current, activeAnchors };
  else delete states[key];
  return { ...assembly, subviewAnchorStateByKey: states };
}

export function renderMainAlignmentAnchors(band, active, escapeAttr) {
  if (!band.mainHitKey) return "";
  return ["left", "right"].map((edge) => {
    const enabled = active.has(band.mainEndpointKeys[edge]);
    const points = band.anchors[edge];
    const attrs = `data-band-track-role="${band.trackRole}" data-band-contig-id="${band.contigId}"
      data-main-alignment-key="${escapeAttr(band.mainHitKey)}" data-main-anchor-edge="${edge}"
      data-main-anchor-key="${escapeAttr(band.mainEndpointKeys[edge])}"`;
    return `<polyline class="subview-anchor-line${enabled ? " is-active" : ""}" points="${points}"
      fill="none" stroke="${enabled ? "red" : "transparent"}" stroke-width="3" pointer-events="none" data-main-anchor-line="1" ${attrs} />
      <polyline class="subview-anchor-hit-zone" points="${points}" fill="none" stroke="transparent"
      stroke-width="6" pointer-events="stroke" ${attrs} />`;
  }).join("");
}

// Map the click through the actual SVG transform/contig rectangle, not viewport or Ref coordinates.
export function resolveMainContigSourcePosition(assembly, context, target, clientX, clientY) {
  if (context?.trackRole !== "primary") return null;
  const ctg = assembly.chrCtgs?.find((c) => Number(c.assemblyCtgId) === Number(context.assemblyCtgId));
  if (!ctg) return null;
  const start = Number(ctg.sourceFragment?.sourceStart || 1);
  const end = Number(ctg.sourceFragment?.sourceEnd || ctg.totalLength);
  const fragment = target?.closest?.("[data-main-fragment-start][data-main-fragment-end]");
  if (fragment) {
    const low = Number(fragment.getAttribute("data-main-fragment-start"));
    const high = Number(fragment.getAttribute("data-main-fragment-end"));
    if (Number.isSafeInteger(low) && Number.isSafeInteger(high) && low >= start && high <= end && low <= high) {
      return low + Math.floor((high - low) / 2);
    }
    return null;
  }
  const track = target?.closest?.("[data-track-contig-id][data-track-role]");
  const band = target?.closest?.('[data-band-contig-id][data-band-track-role="primary"]');
  const node = track || band;
  const matrix = node?.getScreenCTM?.();
  const point = node?.ownerSVGElement?.createSVGPoint?.();
  if (!matrix || !point || !Number.isFinite(clientX) || !Number.isFinite(clientY)) return null;
  point.x = clientX; point.y = clientY;
  const x = point.matrixTransform(matrix.inverse()).x;
  let left, width, low = start, high = end;
  if (track) {
    left = Number(track.getAttribute("data-track-rect-x"));
    width = Number(track.getAttribute("data-track-rect-width"));
  } else {
    left = Number(band.getAttribute("data-band-left-anchor")?.split(",")[0]);
    width = Number(band.getAttribute("data-band-right-anchor")?.split(",")[0]) - left;
    low = Number(band.getAttribute("data-band-query-start"));
    high = Number(band.getAttribute("data-band-query-end"));
  }
  if (!Number.isFinite(left) || !(width > 0) || !Number.isSafeInteger(low) || !Number.isSafeInteger(high)) return null;
  const fraction = Math.max(0, Math.min(1, (x - left) / width));
  const offset = Math.min(high - low, Math.floor(fraction * (high - low + 1)));
  return resolveTrackCtgOrient(ctg) === "-" ? high - offset : low + offset;
}

export function patchMainAlignmentAnchors(host, assembly) {
  const active = mainActiveAnchorKeys(assembly);
  for (const line of host?.querySelectorAll?.('[data-main-anchor-line="1"]') || []) {
    const enabled = active.has(line.getAttribute("data-main-anchor-key"));
    line.setAttribute("stroke", enabled ? "red" : "transparent");
    line.classList?.toggle("is-active", enabled);
  }
}
