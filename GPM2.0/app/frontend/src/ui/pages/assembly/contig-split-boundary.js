import { mainActiveAnchorKeys, mainAlignmentEndpointKey } from "./main-alignment-anchors.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveHitIdentityPct } from "./track-render-geometry.js";
import { resolveTrackCtgOrient } from "./track-label-geometry.js";

export const splitCopy = {
  zh: { title: "分割 contig", manual: "手动分割…", left: "左侧分割", right: "右侧分割",
    unavailable: "没有可用边界、尚未选中锚点片段，或边界已在 contig 端部", stale: "比对或当前视图已变化，请重新打开菜单。",
    undoTitle: "撤销分割 contig", undoLeft: "撤销左侧分割", undoRight: "撤销右侧分割",
    undoUnavailable: "该侧没有可合并的同源相邻分割片段", undoDone: "已撤销该侧分割；可通过主视图撤销/重做恢复。",
    done: "已分割 contig；各片段保留在原轨道，可撤销。" },
  en: { title: "Split contig", manual: "Manual split…", left: "Split left", right: "Split right",
    unavailable: "No boundary, no anchor-delimited fragment selected, or boundary at contig end", stale: "Alignment or view changed. Reopen the menu.",
    undoTitle: "Undo contig split", undoLeft: "Undo left split", undoRight: "Undo right split",
    undoUnavailable: "No compatible adjacent split fragment on this side", undoDone: "Split boundary removed. Main-view undo/redo is available.",
    done: "Contig split; all fragments remain on the original track. Undo is available." },
};

// Immutable source model shared by anchor preview and legacy boundary helpers.
export function resolveContigSplitModel(assembly, assemblyCtgId) {
  const ctg = assembly?.chrCtgs?.find((c) => Number(c.assemblyCtgId) === Number(assemblyCtgId));
  if (!ctg || (assembly.hiddenPrimaryCtgIds || []).map(Number).includes(Number(assemblyCtgId))) return null;
  const prefs = resolveTrackPrefs(assembly.trackView);
  const sourceStart = Number(ctg.sourceFragment?.sourceStart || 1);
  const sourceEnd = Number(ctg.sourceFragment?.sourceEnd || ctg.totalLength);
  if (!Number.isSafeInteger(sourceStart) || !Number.isSafeInteger(sourceEnd) || sourceStart < 1 || sourceEnd <= sourceStart) return null;
  const orient = resolveTrackCtgOrient(ctg);
  const hits = (ctg.hits || []).filter((h) => Number(h.blockLength ?? h.block_length) >= prefs.alignmentLength
    && resolveHitIdentityPct(h) >= prefs.minIdentityPct
    && !(h.chrName && h.chrName !== assembly.selectedChrName))
    .map((h) => ({ queryStart: Number(h.queryStart ?? h.query_start), queryEnd: Number(h.queryEnd ?? h.query_end),
      refStart: Number(h.refStart ?? h.ref_start), refEnd: Number(h.refEnd ?? h.ref_end), strand: h.strand }))
    .filter((h) => Number.isSafeInteger(h.queryStart) && Number.isSafeInteger(h.queryEnd)
      && h.queryStart >= sourceStart && h.queryEnd <= sourceEnd && h.queryStart <= h.queryEnd);
  const chromosome = assembly.chromosomes?.find((c) => c.chrName === assembly.selectedChrName);
  const refLength = Number(chromosome?.chrLength || chromosome?.length)
    || Math.max(0, ...hits.map((h) => Number.isFinite(h.refEnd) ? h.refEnd : 0));
  return { assemblyCtgId: Number(assemblyCtgId), name: String(ctg.name || ctg.originId || "contig"),
    sourceSeqId: Number(ctg.originSourceSeqId ?? ctg.sourceFragment?.sourceSeqId) || null,
    sourceStart, sourceEnd, orient, chrName: String(assembly.selectedChrName || ""), refLength, hits,
    minAlignmentLength: prefs.alignmentLength, minIdentityPct: prefs.minIdentityPct };
}

// Each visible alignment endpoint is a shortcut, including interior boundaries.
// Keep distinct Ref anchors even when they share the same source cut.
export function resolveContigSplitAnchors(assembly, assemblyCtgId, { includeTerminals = false } = {}) {
  if (assembly?.activeHitsTrackKey && assembly.activeHitsTrackKey !== "primary") return [];
  const model = resolveContigSplitModel(assembly, assemblyCtgId);
  if (!model) return [];
  const seen = new Set();
  return model.hits.flatMap((hit) => ["start", "end"].flatMap((edge) => {
    const cutAfter = edge === "start" ? hit.queryStart - 1 : hit.queryEnd;
    if (includeTerminals ? cutAfter < model.sourceStart - 1 || cutAfter > model.sourceEnd
      : cutAfter < model.sourceStart || cutAfter >= model.sourceEnd) return [];
    const refBp = (edge === "start") !== (hit.strand === "-") ? hit.refStart : hit.refEnd;
    if (!Number.isSafeInteger(refBp) || refBp < 1) return [];
    const anchor = { assemblyCtgId: model.assemblyCtgId, cutAfter, edge, refBp,
      queryStart: hit.queryStart, queryEnd: hit.queryEnd, refStart: hit.refStart, refEnd: hit.refEnd,
      orient: model.orient, strand: hit.strand === "-" ? "-" : "+",
      sourceStart: model.sourceStart, sourceEnd: model.sourceEnd, chrName: model.chrName };
    const key = JSON.stringify(anchor);
    if (seen.has(key)) return [];
    seen.add(key);
    return [anchor];
  })).sort((a, b) => (model.orient === "-" ? b.cutAfter - a.cutAfter : a.cutAfter - b.cutAfter)
    || a.refBp - b.refBp);
}

// Only enabled anchors partition the current source interval; unrelated hit endpoints do not.
export function resolveSelectedContigSplitBoundaries(assembly, assemblyCtgId, sourceBp = null) {
  const model = resolveContigSplitModel(assembly, assemblyCtgId);
  if (!model) return null;
  const candidates = resolveContigSplitAnchors(assembly, assemblyCtgId, { includeTerminals: true });
  const active = mainActiveAnchorKeys(assembly);
  const enabled = candidates.filter((anchor) => {
    const side = (anchor.edge === "start") !== (model.orient === "-") ? "left" : "right";
    return active.has(mainAlignmentEndpointKey(model.chrName, model, anchor, side));
  }).sort((a, b) => a.cutAfter - b.cutAfter);
  let low, high;
  if (enabled.length) {
    if (!Number.isSafeInteger(sourceBp) || sourceBp < model.sourceStart || sourceBp > model.sourceEnd) {
      return { left: null, right: null, key: "unselected" };
    }
    low = enabled.filter((a) => a.cutAfter < sourceBp).at(-1)?.cutAfter ?? model.sourceStart - 1;
    high = enabled.find((a) => a.cutAfter >= sourceBp)?.cutAfter ?? model.sourceEnd;
  } else {
    low = Math.min(...model.hits.map((h) => h.queryStart)) - 1;
    high = Math.max(...model.hits.map((h) => h.queryEnd));
  }
  const key = JSON.stringify([model.sourceStart, model.sourceEnd, model.orient, model.chrName,
    enabled.map((a) => [a.cutAfter, a.refBp]), low, high]);
  const at = (cut, side) => {
    const anchor = cut >= model.sourceStart && cut < model.sourceEnd
      ? (enabled.length ? enabled : candidates).find((a) => a.cutAfter === cut) : null;
    return anchor ? { ...anchor, selection: { sourceBp, side, key } } : null;
  };
  return { key, left: at(model.orient === "-" ? high : low, "left"),
    right: at(model.orient === "-" ? low : high, "right") };
}

export function isCurrentContigSplitAnchor(assembly, anchor) {
  if (anchor?.selection) {
    const live = resolveSelectedContigSplitBoundaries(assembly, anchor.assemblyCtgId, anchor.selection.sourceBp);
    if (live?.key !== anchor.selection.key || live?.[anchor.selection.side]?.cutAfter !== anchor.cutAfter) return false;
  }
  return resolveContigSplitAnchors(assembly, anchor?.assemblyCtgId)
    .some((live) => Object.keys(live).every((key) => live[key] === anchor[key]));
}

// Use actual rendered edge points: no guessed geometry and no viewport movement.
export function highlightContigSplitAnchor(host, anchor) {
  const reverse = anchor.orient === "-";
  const side = (anchor.edge === "start") !== reverse ? "left" : "right";
  const bands = [...(host?.querySelectorAll?.(`[data-band-track-role="primary"][data-band-contig-id="${anchor.assemblyCtgId}"]`) || [])]
    .filter((band) => Number(band.getAttribute("data-band-query-start")) === anchor.queryStart
      && Number(band.getAttribute("data-band-query-end")) === anchor.queryEnd
      && (Number(band.getAttribute("data-band-ref-start")) === anchor.refBp
        || Number(band.getAttribute("data-band-ref-end")) === anchor.refBp));
  return highlightContigSplitBoundary({ querySelectorAll: () => bands, ownerDocument: host?.ownerDocument },
    { assemblyCtgId: anchor.assemblyCtgId, reverse, [side]: anchor.cutAfter }, side);
}

// Use all current-Ref hits passing the same per-hit filters as the main renderer.
export function resolveContigSplitBoundaries(assembly, assemblyCtgId) {
  if (assembly?.activeHitsTrackKey && assembly.activeHitsTrackKey !== "primary") return null;
  const model = resolveContigSplitModel(assembly, assemblyCtgId);
  if (!model?.hits.length) return null;
  const low = Math.min(...model.hits.map((h) => h.queryStart)) - 1;
  const high = Math.max(...model.hits.map((h) => h.queryEnd));
  const reverse = model.orient === "-";
  const valid = (cut) => cut >= model.sourceStart && cut < model.sourceEnd ? cut : null;
  return { assemblyCtgId: model.assemblyCtgId, left: valid(reverse ? high : low), right: valid(reverse ? low : high),
    reverse, minAlignmentLength: model.minAlignmentLength, minIdentityPct: model.minIdentityPct };
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

// Restore one source boundary, never join unrelated contigs or synthesize gap bases.
export function resolveContigUnsplitModel(assembly, assemblyCtgId) {
  const ctg = assembly?.chrCtgs?.find((c) => Number(c.assemblyCtgId) === Number(assemblyCtgId));
  const fragment = ctg?.sourceFragment;
  if (!fragment?.groupKey?.startsWith("manual-fragment:")) return null;
  const hidden = new Set((assembly.hiddenPrimaryCtgIds || []).map(Number));
  const orient = resolveTrackCtgOrient(ctg);
  const deleted = (assembly.deletedCtgs || []).filter((c) => c.sourceGroupKey && c.sourceRange)
    .map((c) => ({ ...c, sourceFragment: { ...c.sourceRange, groupKey: c.sourceGroupKey } }));
  const sameGroup = [...(assembly.chrCtgs || []), ...deleted].filter((c) => c !== ctg
    && c.sourceFragment?.groupKey === fragment.groupKey
    && Number(c.sourceFragment.sourceSeqId) === Number(fragment.sourceSeqId));
  // A cross-chromosome inspection copy alone is not a split state.
  if (!sameGroup.length && (fragment.groupKey.startsWith("manual-fragment:chr-add:")
    || Number(fragment.sourceStart) === 1 && Number(fragment.sourceEnd) === Number(fragment.sourceLength))) return null;
  const result = { assemblyCtgId: Number(assemblyCtgId), left: null, right: null };
  if (hidden.has(Number(assemblyCtgId))) return result;
  for (const side of ["left", "right"]) {
    const low = (side === "left") !== (orient === "-");
    const candidates = sameGroup.filter((c) => !hidden.has(Number(c.assemblyCtgId))
      && resolveTrackCtgOrient(c) === orient
      && (low ? Number(c.sourceFragment.sourceEnd) + 1 === Number(fragment.sourceStart)
        : Number(fragment.sourceEnd) + 1 === Number(c.sourceFragment.sourceStart)));
    if (candidates.length !== 1) continue;
    const neighbor = candidates[0];
    result[side] = { assemblyCtgId: Number(assemblyCtgId), neighborCtgId: Number(neighbor.assemblyCtgId), side,
      ...(neighbor.deletedCtgRecordId ? { neighborDeletedRecordId: neighbor.deletedCtgRecordId } : {}),
      sourceStart: Number(fragment.sourceStart), sourceEnd: Number(fragment.sourceEnd), orient,
      neighborSourceStart: Number(neighbor.sourceFragment.sourceStart), neighborSourceEnd: Number(neighbor.sourceFragment.sourceEnd) };
  }
  return result;
}
