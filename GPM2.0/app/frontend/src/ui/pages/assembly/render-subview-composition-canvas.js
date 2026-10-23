import { localGrtProjection, projectLocalGrtEvidence } from "./subview-fragment-grt.js";
import { memberAnchorEndpointKey, memberBackingIds, memberSourceInterval, projectLocalAlignment, memberCoordinateToSource, projectLocalNRegions } from "./subview-fragment-model.js";
import { sourceFragmentDragAttrs, resolveManualSplitSourceCuts, renderSourceSplitMarkers } from "./source-fragment-layout.js";
import { resolveFullRangeVisibleSpan } from "./view-navigation-state.js";
import { renderNRegionMarkersForTrackCtg } from "./n-region-markers.js";
import { getGraphFontSize } from "../../../services/app-settings.js";
import {
  readHitIdentityPct, alignmentBandSvgAttrs, alignmentBandTooltipMetrics,
  sortAlignmentBands, renderAlignmentIdentityLegend,
} from "./alignment-band-style.js";
import {
  deriveSubviewContigFragments,
} from "./subview-anchor-state.js";
import { buildSubviewAnchorObjectId } from "./subview-anchor-objects.js";
import { buildSubviewGrtAnchorScene } from "./subview-grt-anchor-state.js";
import { buildGrtResultScene, renderGrtResultOverlayGroup } from "./grt-result-render.js";
import {
  renderSubviewVirtualRuler,
  resolveHitIdentityPct,
  resolveSubviewRulerGeometry,
  resolveSubviewWorldStartBp,
  sortTrackEntriesForRender,
} from "./track-render-geometry.js";
import { normalizePositiveInt, resolveTrackPrefs, resolveTickBpFromScale } from "./track-prefs.js";
import { resolveSubviewCompositionCandidate, isSubviewCompositionSourceCompatible } from "./subview-composition-candidates.js";
import { buildSubviewCompositionLayout, resolveSubviewCompositionScaleViewport } from "./subview-composition-layout.js";
import { getSubviewComposition } from "./subview-composition-state.js";
import { normalizeSupportDatasetId } from "./selection-state.js";
import {
  formatTrackCtgOrientationLabel,
  buildTrackCtgHoverTitle,
  resolveBoundedTrackCtgLabelPlacement,
  resolveTrackCtgEffectiveOrientation,
  resolveTrackCtgVisibleName,
} from "./track-label-geometry.js";

function getCompositionVerticalMetrics() {
  const scale = Math.max(1, getGraphFontSize() / 12);
  // Keep the legend above the ruler and halve its 34px gap to the top lane.
  return { RULER_Y: 48 * scale, TOP_Y: 65 * scale, BOTTOM_Y: 173 * scale, BAR_HEIGHT: 14 * scale, CONTENT_HEIGHT: 231 * scale };
}

function number(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function hitField(hit, ...keys) {
  for (const key of keys) {
    const value = number(hit?.[key]);
    if (value !== null) return value;
  }
  return null;
}

function sourceName(member, labels) {
  return member.source?.datasetName || member.source?.hap
    || labels?.tools?.compositionManager?.sources?.[member.source?.role]
    || member.source?.role || "";
}

function memberOrientation(member) {
  return resolveTrackCtgEffectiveOrientation(member?.baseOrientation, member?.flipped);
}

function memberDisplayLabel(member) {
  const baseLabel = String(member?.label || "").replace(/(?:\s*\([+-]\))+\s*$/, "").trim();
  return formatTrackCtgOrientationLabel(
    resolveTrackCtgVisibleName({ name: baseLabel }, member?.assemblyCtgId),
    memberOrientation(member),
  );
}

function memberFullDisplayLabel(member) {
  return formatTrackCtgOrientationLabel(member?.label, memberOrientation(member));
}

function endpointKey(member) {
  return memberAnchorEndpointKey(member);
}

function rangeX(member, start, end) {
  const minimum = Math.max(0, Math.min(member.lengthBp, Math.min(start, end)));
  const maximum = Math.max(minimum, Math.min(member.lengthBp, Math.max(start, end)));
  const displayStart = member.flipped ? member.lengthBp - maximum : minimum;
  const displayEnd = member.flipped ? member.lengthBp - minimum : maximum;
  return {
    left: member.x + displayStart / member.bpPerPx,
    right: member.x + displayEnd / member.bpPerPx,
  };
}

function rangeCuts(member, start, end) {
  const minimum = Math.max(1, Math.min(member.lengthBp, Math.min(start, end)));
  const maximum = Math.max(minimum, Math.min(member.lengthBp, Math.max(start, end)));
  return {
    left: member.flipped ? maximum : minimum,
    right: member.flipped ? minimum : maximum,
  };
}

function buildEvidenceBands(layout, evidence, prefs) {
  const indexMembers = (members) => {
    const result = new Map();
    for (const member of members) for (const id of memberBackingIds(member)) {
      if (!result.has(id)) result.set(id, []);
      result.get(id).push(member);
    }
    return result;
  };
  const topById = indexMembers(layout.top), bottomById = indexMembers(layout.bottom);
  return (Array.isArray(evidence?.hits) ? evidence.hits : []).flatMap((hit, index) => {
    const length = normalizePositiveInt(hit?.alignLength ?? hit?.align_length) ?? 0;
    if (length < prefs.alignmentLength || resolveHitIdentityPct(hit) < prefs.minIdentityPct) return [];
    const queryId = normalizeSupportDatasetId(hit?.queryAssemblyCtgId ?? hit?.query_assembly_ctg_id);
    const subjectId = normalizeSupportDatasetId(hit?.subjectAssemblyCtgId ?? hit?.subject_assembly_ctg_id);
    const result = [];
    for (const inverted of [false, true]) {
      const topId = inverted ? subjectId : queryId, bottomId = inverted ? queryId : subjectId;
      const prefixA = inverted ? "subject" : "query", prefixB = inverted ? "query" : "subject";
      const coordinates = {
        topStart: hitField(hit, `${prefixA}Start`, `${prefixA}_start`),
        topEnd: hitField(hit, `${prefixA}End`, `${prefixA}_end`),
        bottomStart: hitField(hit, `${prefixB}Start`, `${prefixB}_start`),
        bottomEnd: hitField(hit, `${prefixB}End`, `${prefixB}_end`),
        strand: String(hit?.strand || hit?.orient || "+").trim(),
      };
      if (Object.values(coordinates).some((value) => value === null)) continue;
      for (const top of topById.get(topId) || []) for (const bottom of bottomById.get(bottomId) || []) {
        const projected = projectLocalAlignment(top, bottom, topId, bottomId, coordinates);
        if (!projected) continue;
        const { topStart, topEnd, bottomStart, bottomEnd, strand } = projected;
        const originalKey = String(hit?.hitKey || `composition-pairwise-${index + 1}`);
        result.push({
          hitKey: top.localFragment || bottom.localFragment ? `${originalKey}|${top.entityKey}|${bottom.entityKey}` : originalKey,
          identityPct: readHitIdentityPct(hit), projectionApproximate: Boolean(hit.projectionApproximate), alignLength: length,
          top, bottom, topRange: rangeX(top, topStart, topEnd), bottomRange: rangeX(bottom, bottomStart, bottomEnd),
          topCuts: rangeCuts(top, topStart, topEnd), bottomCuts: rangeCuts(bottom, bottomStart, bottomEnd),
          reversed: ((strand === "-") !== Boolean(top.flipped)) !== Boolean(bottom.flipped),
        });
      }
    }
    return result;
  });
}

function buildReferenceBands(layout, candidates, prefs) {
  const bands = [];
  for (const top of layout.top) {
    for (const bottom of layout.bottom) {
      const topIsRef = top.source?.role === "ref";
      const bottomIsRef = bottom.source?.role === "ref";
      if (topIsRef === bottomIsRef) continue;
      const ref = topIsRef ? top : bottom;
      const contig = topIsRef ? bottom : top;
      const backingCandidates = memberBackingIds(contig).map((id) => candidates.find((item) => item.assemblyCtgId === id && isSubviewCompositionSourceCompatible(item, contig))).filter(Boolean);
      const referenceStart = Number(ref.reference?.startBp);
      const referenceEnd = Number(ref.reference?.endBp);
      if (!Number.isFinite(referenceStart) || !Number.isFinite(referenceEnd)) continue;
      for (const candidate of backingCandidates) for (const [index, hit] of (Array.isArray(candidate.ctg?.hits) ? candidate.ctg.hits : []).entries()) {
        const length = normalizePositiveInt(hit?.blockLength ?? hit?.block_length) ?? 0;
        if (
          length < prefs.alignmentLength
          || resolveHitIdentityPct(hit) < prefs.minIdentityPct
        ) continue;
        const rawRefStart = hitField(hit, "refStart", "ref_start");
        const rawRefEnd = hitField(hit, "refEnd", "ref_end");
        let ctgStart = hitField(hit, "ctgStart", "ctg_start");
        let ctgEnd = hitField(hit, "ctgEnd", "ctg_end");
        if (ctgStart !== null && ctgEnd !== null && candidate.ctg?.subviewPhasedOrientFlipped) {
          const parentLength = Number(candidate.ctg.totalLength ?? candidate.ctg.lengthBp);
          [ctgStart, ctgEnd] = [parentLength - ctgEnd + 1, parentLength - ctgStart + 1];
        }
        if ([rawRefStart, rawRefEnd, ctgStart, ctgEnd].some((value) => value === null)) continue;
        const overlapStart = Math.max(referenceStart, Math.min(rawRefStart, rawRefEnd));
        const overlapEnd = Math.min(referenceEnd, Math.max(rawRefStart, rawRefEnd));
        if (overlapEnd < overlapStart) continue;
        const refStart = Math.min(rawRefStart, rawRefEnd) - referenceStart + 1;
        const refEnd = Math.max(rawRefStart, rawRefEnd) - referenceStart + 1;
        const topStart = topIsRef ? refStart : ctgStart;
        const topEnd = topIsRef ? refEnd : ctgEnd;
        const bottomStart = bottomIsRef ? refStart : ctgStart;
        const bottomEnd = bottomIsRef ? refEnd : ctgEnd;
        const projected = projectLocalAlignment(top, bottom,
          topIsRef ? ref.assemblyCtgId : candidate.assemblyCtgId,
          bottomIsRef ? ref.assemblyCtgId : candidate.assemblyCtgId,
          { topStart, topEnd, bottomStart, bottomEnd, strand: String(hit?.strand || hit?.orient || "+").trim() });
        if (!projected) continue;
        const strand = projected.strand;
        bands.push({
          hitKey: `reference:${top.entityKey}|${bottom.entityKey}|${String(hit?.hitKey || index + 1)}`,
          identityPct: readHitIdentityPct(hit),
          alignLength: length,
          top,
          bottom,
          topRange: rangeX(top, projected.topStart, projected.topEnd),
          bottomRange: rangeX(bottom, projected.bottomStart, projected.bottomEnd),
          topCuts: rangeCuts(top, projected.topStart, projected.topEnd),
          bottomCuts: rangeCuts(bottom, projected.bottomStart, projected.bottomEnd),
          reversed: ((strand === "-") !== Boolean(top.flipped)) !== Boolean(bottom.flipped),
        });
      }
    }
  }
  return bands;
}

function edgeDescriptor(band, edge) {
  const reversed = band.reversed;
  const topX = edge === "left" ? band.topRange.left : band.topRange.right;
  const bottomX = edge === "left"
    ? (reversed ? band.bottomRange.right : band.bottomRange.left)
    : (reversed ? band.bottomRange.left : band.bottomRange.right);
  const topCut = band.topCuts[edge];
  const bottomCut = band.bottomCuts[reversed
    ? (edge === "left" ? "right" : "left")
    : edge];
  return { topX, bottomX, topCut, bottomCut };
}

function anchorObjectId(edge, kind, identity) {
  return buildSubviewAnchorObjectId(kind, identity, kind === "manual" ? "manual" : edge.edge);
}

function anchorAttrs(edge, kind, identity, active, escapeAttr) {
  const topSource = edge.top.source || {};
  const bottomSource = edge.bottom.source || {};
  const objectId = anchorObjectId(edge, kind, identity);
  return `data-subview-anchor-kind="${kind}" data-subview-anchor-object-id="${escapeAttr(objectId)}"
    data-subview-anchor-hit-key="${escapeAttr(edge.hitKey || "")}" data-subview-anchor-edge="${escapeAttr(edge.edge || "manual")}"
    data-subview-anchor-active="${active ? "1" : "0"}" data-subview-manual-anchor-id="${escapeAttr(edge.manualAnchorId || "")}"
    data-subview-anchor-top-endpoint-key="${escapeAttr(endpointKey(edge.top))}" data-subview-anchor-bottom-endpoint-key="${escapeAttr(endpointKey(edge.bottom))}"
    data-subview-anchor-top-contig-id="${edge.top.assemblyCtgId || 0}" data-subview-anchor-bottom-contig-id="${edge.bottom.assemblyCtgId || 0}"
    data-subview-anchor-top-cut-bp="${Math.round(edge.topCut)}" data-subview-anchor-bottom-cut-bp="${Math.round(edge.bottomCut)}"
    ${Number.isSafeInteger(edge.topSourceCutAfter) ? `data-subview-anchor-top-source-cut-after="${edge.topSourceCutAfter}"` : ""}
    ${Number.isSafeInteger(edge.bottomSourceCutAfter) ? `data-subview-anchor-bottom-source-cut-after="${edge.bottomSourceCutAfter}"` : ""}
    data-subview-anchor-preview="1" data-subview-anchor-top-entity-key="${escapeAttr(edge.top.entityKey || "")}" data-subview-anchor-bottom-entity-key="${escapeAttr(edge.bottom.entityKey || "")}"
    data-subview-anchor-top-length-bp="${edge.top.lengthBp}" data-subview-anchor-bottom-length-bp="${edge.bottom.lengthBp}"
    data-subview-anchor-top-name="${escapeAttr(edge.top.label)}" data-subview-anchor-bottom-name="${escapeAttr(edge.bottom.label)}"
    data-subview-anchor-top-source-role="${escapeAttr(topSource.role || "")}" data-subview-anchor-bottom-source-role="${escapeAttr(bottomSource.role || "")}"
    data-subview-anchor-top-source-kind="${escapeAttr(topSource.sourceType || "")}" data-subview-anchor-bottom-source-kind="${escapeAttr(bottomSource.sourceType || "")}"
    data-subview-anchor-top-source-name="${escapeAttr(topSource.datasetName || topSource.hap || "")}" data-subview-anchor-bottom-source-name="${escapeAttr(bottomSource.datasetName || bottomSource.hap || "")}
    " data-subview-anchor-top-x="${edge.topX.toFixed(4)}" data-subview-anchor-bottom-x="${edge.bottomX.toFixed(4)}"`;
}

function anchorPreviewAttrs(edge, escapeAttr) {
  return `data-subview-anchor-preview="1" data-subview-anchor-top-contig-id="${edge.top.assemblyCtgId || 0}"
    data-subview-anchor-bottom-contig-id="${edge.bottom.assemblyCtgId || 0}"
    data-subview-anchor-top-entity-key="${escapeAttr(edge.top.entityKey || "")}" data-subview-anchor-bottom-entity-key="${escapeAttr(edge.bottom.entityKey || "")}"`;
}

function renderEvidenceAnchors(bands, activeAnchors, escapeAttr) {
  const { TOP_Y, BOTTOM_Y, BAR_HEIGHT } = getCompositionVerticalMetrics();
  const active = new Set((Array.isArray(activeAnchors) ? activeAnchors : [])
    .filter((anchor) => !anchor.descriptor).map((anchor) => `${anchor.hitKey}:${anchor.edge}`));
  return bands.flatMap((band) => ["left", "right"].map((side) => {
    const points = edgeDescriptor(band, side);
    const edge = { ...band, ...points, edge: side };
    const isActive = active.has(`${band.hitKey}:${side}`);
    const attrs = anchorAttrs(edge, "evidence", band.hitKey, isActive, escapeAttr);
    const objectId = anchorObjectId(edge, "evidence", band.hitKey);
    return `<line class="subview-anchor-line${isActive ? " is-active" : ""}" x1="${points.topX.toFixed(2)}"
      y1="${TOP_Y + BAR_HEIGHT}" x2="${points.bottomX.toFixed(2)}" y2="${BOTTOM_Y}"
      stroke="${isActive ? "red" : "transparent"}" stroke-width="3" pointer-events="none"
      data-subview-anchor-object-id="${escapeAttr(objectId)}" ${anchorPreviewAttrs(edge, escapeAttr)} />
      <line class="subview-anchor-hit-zone${isActive ? " is-active" : ""}" x1="${points.topX.toFixed(2)}"
      y1="${TOP_Y + BAR_HEIGHT}" x2="${points.bottomX.toFixed(2)}" y2="${BOTTOM_Y}"
      stroke="transparent" stroke-width="4" pointer-events="stroke" ${attrs} />`;
  })).join("");
}

function renderManualAnchors(layout, anchors, escapeAttr, evidence = false) {
  const { TOP_Y, BOTTOM_Y, BAR_HEIGHT } = getCompositionVerticalMetrics();
  const byEndpoint = new Map(layout.members.map((member) => [endpointKey(member), member]));
  return (Array.isArray(anchors) ? anchors : []).map((anchor) => {
    let top = byEndpoint.get(anchor?.endpointA?.endpointKey);
    let bottom = byEndpoint.get(anchor?.endpointB?.endpointKey);
    let topEndpoint = anchor?.endpointA;
    let bottomEndpoint = anchor?.endpointB;
    if (top?.lane === "bottom" && bottom?.lane === "top") {
      [top, bottom] = [bottom, top];
      [topEndpoint, bottomEndpoint] = [bottomEndpoint, topEndpoint];
    }
    if (!top || !bottom || top.lane !== "top" || bottom.lane !== "bottom") return "";
    const topRange = rangeX(top, topEndpoint.cutBp, topEndpoint.cutBp);
    const bottomRange = rangeX(bottom, bottomEndpoint.cutBp, bottomEndpoint.cutBp);
    const edge = {
      top,
      bottom,
      topX: topRange.left,
      bottomX: bottomRange.left,
      topCut: topEndpoint.cutBp,
      bottomCut: bottomEndpoint.cutBp,
      topSourceCutAfter: topEndpoint.sourceCutAfter,
      bottomSourceCutAfter: bottomEndpoint.sourceCutAfter,
      manualAnchorId: anchor.manualAnchorId,
      hitKey: anchor.hitKey || "",
      edge: evidence ? anchor.edge : "manual",
    };
    const kind = evidence ? "evidence" : "manual";
    const identity = evidence ? anchor.hitKey : anchor.manualAnchorId;
    const objectId = anchorObjectId(edge, kind, identity);
    return `<line class="subview-anchor-line is-active" x1="${edge.topX.toFixed(2)}" y1="${TOP_Y + BAR_HEIGHT}"
      x2="${edge.bottomX.toFixed(2)}" y2="${BOTTOM_Y}" stroke="red" stroke-width="3" pointer-events="none"
      data-subview-anchor-object-id="${escapeAttr(objectId)}" ${anchorPreviewAttrs(edge, escapeAttr)} />
      <line class="subview-anchor-hit-zone is-active" x1="${edge.topX.toFixed(2)}" y1="${TOP_Y + BAR_HEIGHT}"
      x2="${edge.bottomX.toFixed(2)}" y2="${BOTTOM_Y}" stroke="transparent" stroke-width="4"
      pointer-events="stroke" ${anchorAttrs(edge, kind, identity, true, escapeAttr)} />`;
  }).join("");
}

function buildAnchorCutsByEndpoint(layout, bands, activeAnchors, manualAnchors) {
  const cuts = new Map(layout.members.map((member) => [endpointKey(member), []]));
  const add = (key, cut) => {
    const numeric = Number(cut);
    if (!cuts.has(key) || !Number.isInteger(numeric) || numeric <= 0) return;
    cuts.get(key).push(numeric);
  };
  const active = new Set((Array.isArray(activeAnchors) ? activeAnchors : [])
    .map((anchor) => `${anchor.hitKey}:${anchor.edge}`));
  bands.forEach((band) => {
    ["left", "right"].forEach((side) => {
      if (!active.has(`${band.hitKey}:${side}`)) return;
      const edge = edgeDescriptor(band, side);
      add(endpointKey(band.top), edge.topCut);
      add(endpointKey(band.bottom), edge.bottomCut);
    });
  });
  (Array.isArray(manualAnchors) ? manualAnchors : []).forEach((anchor) => {
    add(anchor?.endpointA?.endpointKey, anchor?.endpointA?.cutBp);
    add(anchor?.endpointB?.endpointKey, anchor?.endpointB?.cutBp);
  });
  (activeAnchors || []).forEach((anchor) => {
    add(anchor.descriptor?.top?.endpointKey, anchor.descriptor?.top?.cutBp);
    add(anchor.descriptor?.bottom?.endpointKey, anchor.descriptor?.bottom?.cutBp);
  });
  return cuts;
}

function renderMemberFragments(member, cuts, y, { escapeHtml, escapeAttr }) {
  const { BAR_HEIGHT } = getCompositionVerticalMetrics();
  const fragments = deriveSubviewContigFragments({
    contig: {
      assemblyCtgId: member.assemblyCtgId,
      role: member.source?.role,
      lengthBp: member.lengthBp,
    },
    // Undo Split suppresses a structural marker, not a user's active anchor.
    // These are hit-testing intervals only; they never materialize new ctgs.
    anchorCuts: cuts,
  });
  if (!fragments.length) return "";
  const orientation = memberOrientation(member);
  const separators = [...new Set(cuts)].filter((cut) => Number.isSafeInteger(cut) && cut > 1 && cut <= member.lengthBp)
    .map((cut) => {
      const x = rangeX(member, cut, cut).left;
      return `<line class="main-anchor-fragment-separator subview-anchor-separator" data-main-fragment-role="${escapeAttr(member.source?.role || "support")}"
        data-subview-anchor-cut="${cut}" x1="${x.toFixed(2)}" x2="${x.toFixed(2)}" y1="${y}" y2="${y + BAR_HEIGHT}" pointer-events="none" />`;
    }).join("");
  return fragments.map((fragment) => {
    const range = rangeX(member, fragment.start, fragment.end);
    const width = Math.max(1, range.right - range.left);
    const sourceA = memberCoordinateToSource(member, fragment.start), sourceB = memberCoordinateToSource(member, fragment.end);
    const title = `${memberFullDisplayLabel(member)}: source ${Math.min(sourceA, sourceB).toLocaleString()}-${Math.max(sourceA, sourceB).toLocaleString()}`;
    return `<rect class="subview-fragment-hit-zone" x="${range.left.toFixed(2)}" y="${y}"
        width="${width.toFixed(2)}" height="${BAR_HEIGHT}" fill="transparent"
        data-subview-fragment-key="${escapeAttr(member.entityKey)}:${fragment.start}-${fragment.end}"
        data-subview-fragment-entity-key="${escapeAttr(member.entityKey)}"
        data-subview-fragment-coordinate-space="base"
        data-subview-fragment-slot="${member.lane}"
        data-subview-fragment-role="${escapeAttr(member.source?.role || "support")}"
        data-subview-fragment-contig-id="${member.assemblyCtgId || 0}"
        data-subview-fragment-start="${fragment.start}" data-subview-fragment-end="${fragment.end}"
        data-subview-fragment-ctg-name="${escapeAttr(member.label)}"
        data-subview-fragment-dataset-id="${member.source?.datasetId || 0}"
        data-subview-fragment-is-mirror="${member.source?.mirrored ? "1" : "0"}"
        data-subview-fragment-ref-orient="${escapeAttr(orientation)}"
        data-subview-fragment-source-kind="${escapeAttr(member.source?.sourceType || "assembly_ctg")}"
        data-subview-fragment-reference-chr-id="0"
        data-subview-fragment-reference-chr-name="${escapeAttr(member.reference?.chrName || "")}"
        data-subview-fragment-segment-start-bp="${Number(member.reference?.startBp || 0)}"
        data-subview-fragment-segment-end-bp="${Number(member.reference?.endBp || 0)}"
        data-subview-fragment-phased-track-id="${member.source?.phasedTrackId || 0}"
        data-subview-fragment-phased-track-item-id="${member.source?.phasedItemId || 0}"
        data-subview-fragment-phased-haplotype-key="${escapeAttr(member.source?.hap || "")}">
        <title>${escapeHtml(title)}</title></rect>
      <rect class="subview-fragment-outline" x="${range.left.toFixed(2)}" y="${y}"
        width="${width.toFixed(2)}" height="${BAR_HEIGHT}" rx="4" ry="4"
        fill="none" stroke="transparent" stroke-width="2.5" pointer-events="none" />`;
  }).join("") + separators;
}

function renderMember(member, candidate, candidatesLoaded, cuts, y, labels, {
  escapeHtml,
  escapeAttr,
  resolveTrackToneClass,
  grtOverlay = "",
  splitSourceCuts = [],
  selected = false,
  minVisibleX,
  maxVisibleX,
}) {
  const { BAR_HEIGHT } = getCompositionVerticalMetrics();
  const role = member.source?.role || "support";
  const tone = resolveTrackToneClass(role);
  const source = sourceName(member, labels);
  const label = memberDisplayLabel(member);
  const worldStartBp = resolveSubviewWorldStartBp({ startBp: member.xBp });
  const localRangeTitle = member.localFragment ? ` | source ${member.localFragment.sourceStart.toLocaleString()}-${member.localFragment.sourceEnd.toLocaleString()}` : "";
  const title = `${buildTrackCtgHoverTitle(memberFullDisplayLabel(member), {
    startBp: worldStartBp,
    lengthBp: member.lengthBp,
  })}${source ? ` | ${source}` : ""}${localRangeTitle}`;
  const unavailable = (candidate || !candidatesLoaded ? "" : " is-unavailable")
    + (selected ? " is-multi-selected" : "");
  const orient = memberOrientation(member);
  const placement = resolveBoundedTrackCtgLabelPlacement({
    ctgName: label,
    role,
    rect: member,
    barY: y,
    barHeight: BAR_HEIGHT,
    inlineTextOffsetY: BAR_HEIGHT * 11 / 14,
    outsideLabelAnchor: "bar-middle",
    hideOutsideLabel: true,
    minVisibleX,
    maxVisibleX,
  });
  const labelMarkup = placement.hidden ? ""
    : `<text class="track-ctg-label${tone}${placement.classSuffix}" x="${placement.x.toFixed(2)}" y="${placement.y.toFixed(2)}"${placement.transformAttr} text-anchor="${placement.textAnchor}"
        data-subview-label-slot="${member.lane}" data-subview-label-role="${escapeAttr(role)}"
        data-subview-label-contig-id="${member.assemblyCtgId || 0}">${escapeHtml(label)}</text>`;
  return `<g class="track-ctg-group${tone}${unavailable}" data-subview-composition-entity-key="${escapeAttr(member.entityKey)}"
      data-grt-result-entry-key="${escapeAttr(member.entityKey)}"
      data-subview-track-pair-role="${escapeAttr(role)}" data-subview-track-pair-contig-id="${member.assemblyCtgId || 0}"
      data-subview-track-pair-dataset-id="${member.source?.datasetId || 0}" data-subview-track-pair-is-mirror="${member.source?.mirrored ? "1" : "0"}"
      data-subview-track-pair-phased-track-id="${member.source?.phasedTrackId || 0}"
      data-subview-track-pair-phased-track-item-id="${member.source?.phasedItemId || 0}"
      data-subview-track-pair-phased-haplotype-key="${escapeAttr(member.source?.hap || "")}"
      data-subview-track-slot="${member.lane}" data-subview-track-role="${escapeAttr(role)}"
      data-subview-contig-id="${member.assemblyCtgId || 0}" ${sourceFragmentDragAttrs(candidate?.ctg?.sourceFragment ? candidate.ctg : member, escapeAttr)} data-subview-track-ref-orient="${orient}"
      data-subview-rect-x="${member.x.toFixed(2)}" data-subview-rect-y="${y}"
      data-subview-rect-width="${member.width.toFixed(2)}" data-subview-rect-height="${BAR_HEIGHT}"
      data-subview-world-start-bp="${worldStartBp}">
    <rect class="track-ctg subview-track-ctg${tone}${selected ? " is-multi-selected" : ""}" x="${member.x.toFixed(2)}" y="${y}"
      width="${member.width.toFixed(2)}" height="${BAR_HEIGHT}" rx="4" ry="4" pointer-events="all"><title>${escapeHtml(title)}</title></rect>
    ${renderGrtResultOverlayGroup({ entryKey: member.entityKey, markup: grtOverlay, escapeAttr })}
    ${renderNRegionMarkersForTrackCtg({
      ctg: candidate?.ctg, rect: member, y, barHeight: BAR_HEIGHT,
      isMirror: member.source?.mirrored,
      flipped: member.localFragment ? member.flipped : Boolean(member.flipped) !== Boolean(candidate?.ctg?.subviewPhasedOrientFlipped),
      escapeAttr, escapeHtml,
    })}
    ${renderSourceSplitMarkers(splitSourceCuts, { ...memberSourceInterval(member), orient }, member, y, BAR_HEIGHT, escapeHtml)}
    ${renderMemberFragments(member, cuts, y, { escapeHtml, escapeAttr })}
    ${labelMarkup}
  </g>`;
}

function evidenceStatus(evidence, labels, escapeHtml) {
  const status = String(evidence?.status || "");
  if (status === "loading") return `<span class="muted">${escapeHtml(labels.loadingPairwiseEvidence)}</span>`;
  if (status === "error") return `<span class="error-text">${escapeHtml(evidence.error || labels.compositionEvidenceFailed)}</span>`;
  const coverage = Array.isArray(evidence?.coverage) ? evidence.coverage : [];
  if (coverage.some((item) => item.status === "failed")) return `<span class="error-text">${escapeHtml(labels.compositionEvidencePartialFailed)}</span>`;
  if (coverage.some((item) => item.status === "missing")) return `<span class="muted">${escapeHtml(labels.compositionEvidencePartialMissing)}</span>`;
  if (status === "loaded" && !(evidence?.hits || []).length) return `<span class="muted">${escapeHtml(labels.compositionEvidenceEmpty)}</span>`;
  return "";
}

export function renderSubviewCompositionAlignmentCard({
  subview,
  supportContext,
  trackPrefs,
  grtResult = {},
  i18n,
  viewportWidthPx,
  chrName,
  grtAnchorPlan,
  renderTrackOrderToggleButton = () => "",
  resolveTrackToneClass,
  escapeHtml,
  escapeAttr,
}) {
  const { RULER_Y, TOP_Y, BOTTOM_Y, BAR_HEIGHT, CONTENT_HEIGHT } = getCompositionVerticalMetrics();
  const composition = getSubviewComposition(subview);
  if (!composition?.members.length) return "";
  const prefs = resolveTrackPrefs(trackPrefs);
  const savedViewport = supportContext?.compositionViewport;
  let viewport = !prefs.fullRange && Number(savedViewport?.bpPerPx) > 0 ? savedViewport
    : resolveSubviewCompositionScaleViewport(composition, { trackPrefs: prefs, viewportWidthPx });
  let layout = buildSubviewCompositionLayout(composition, {
    bpPerPx: viewport.bpPerPx,
    viewportWidthPx,
    leftBp: viewport.leftBp,
    fullRange: prefs.fullRange,
  });
  // Full overview uses current members, not the previous world's empty viewport.
  for (let pass = 0; prefs.fullRange && pass < 6; pass += 1) {
    const span = resolveFullRangeVisibleSpan({ contentWidth: layout.width,
      innerWidth: viewportWidthPx, domainSpanBp: viewport.bpPerPx * viewportWidthPx,
      viewportWidth: viewportWidthPx });
    if (span === null) break;
    viewport = { ...viewport, bpPerPx: span / viewportWidthPx };
    layout = buildSubviewCompositionLayout(composition, { ...viewport, viewportWidthPx, fullRange: true });
  }
  const candidates = supportContext?.compositionCandidates || [];
  const candidatesLoaded = supportContext?.compositionCandidatesLoaded === true;
  const grtEntries = layout.members.map((member) => ({
    ...localGrtProjection(member),
    key: member.entityKey,
    ctg: {
      assemblyCtgId: member.assemblyCtgId,
      lengthBp: member.lengthBp,
      orient: member.flipped
        ? (member.baseOrientation === "-" ? "+" : "-")
        : member.baseOrientation,
    },
    endpointKey: endpointKey(member),
    lane: member.lane,
    baseOrientation: member.baseOrientation,
    locallyFlipped: member.flipped,
    name: member.label,
    sourceRole: member.source?.role,
    sourceKind: member.source?.sourceType,
    sourceName: member.source?.datasetName || member.source?.hap || "",
    rect: { x: member.x, width: member.width },
    y: member.lane === "top" ? TOP_Y : BOTTOM_Y,
    height: BAR_HEIGHT,
  }));
  const grtAnchorScene = buildSubviewGrtAnchorScene({
    chrName,
    plan: grtAnchorPlan,
    entries: grtEntries,
    escapeAttr,
  });
  const grtScene = buildGrtResultScene({
    plan: grtResult.context?.available ? projectLocalGrtEvidence(grtResult.plan, grtEntries) : null,
    entries: grtEntries,
    layers: grtResult.context?.subviewLayers,
    escapeHtml,
    gapLabel: i18n.grtResult.gapLabel,
  });
  const bands = sortAlignmentBands([
    ...buildEvidenceBands(layout, subview?.pairwiseEvidence, prefs),
    ...buildReferenceBands(layout, candidates, prefs),
  ]);
  const bandMarkup = bands.map((band) => {
    const bottomLeft = band.reversed ? band.bottomRange.right : band.bottomRange.left;
    const bottomRight = band.reversed ? band.bottomRange.left : band.bottomRange.right;
    const points = [
      `${band.topRange.left.toFixed(2)},${TOP_Y + BAR_HEIGHT}`,
      `${band.topRange.right.toFixed(2)},${TOP_Y + BAR_HEIGHT}`,
      `${bottomRight.toFixed(2)},${BOTTOM_Y}`,
      `${bottomLeft.toFixed(2)},${BOTTOM_Y}`,
    ].join(" ");
    const tone = band.top.source?.role === "support" ? "companion" : "primary";
    const tooltip = `${band.top.label}: ${band.topCuts.left}–${band.topCuts.right} | ${band.bottom.label}: ${band.bottomCuts.left}–${band.bottomCuts.right} | ${alignmentBandTooltipMetrics(band)}${band.projectionApproximate ? " | Approximate projection" : ""}`;
    return `<polygon class="track-collinearity-band${tone === "companion" ? " is-companion" : ""}" points="${points}" ${alignmentBandSvgAttrs(band, tone)} pointer-events="visibleFill"
      data-subview-band-tooltip="${escapeAttr(tooltip)}"
      data-track-band-proxy="1" data-subview-hit-key="${escapeAttr(band.hitKey)}"
      data-subview-top-contig-id="${band.top.assemblyCtgId || 0}" data-subview-top-entity-key="${escapeAttr(band.top.entityKey)}"
      data-subview-bottom-contig-id="${band.bottom.assemblyCtgId || 0}" data-subview-bottom-entity-key="${escapeAttr(band.bottom.entityKey)}" />`;
  }).join("");
  const anchorCutsByEndpoint = buildAnchorCutsByEndpoint(
    layout,
    bands,
    composition.activeAnchors,
    composition.manualAnchors,
  );
  const renderCandidate = (member) => {
    const candidate = resolveSubviewCompositionCandidate(candidates, member);
    return candidate && member.localFragment ? { ...candidate, ctg: { ...candidate.ctg,
      totalLength: member.lengthBp, lengthBp: member.lengthBp, nRegions: projectLocalNRegions(member, candidates, (item) => isSubviewCompositionSourceCompatible(item, member)),
    } } : candidate;
  };
  const splitCuts = (member) => {
    const ids = new Set(memberBackingIds(member));
    const sources = candidates.filter((item) => ids.has(item.assemblyCtgId) && isSubviewCompositionSourceCompatible(item, member));
    const nativeCuts = member.localFragment?.nativeCuts ?? (member.sourceFragment && !member.localFragment
      ? resolveManualSplitSourceCuts(member)
      : sources.length ? sources.flatMap((item) => resolveManualSplitSourceCuts(item.ctg)) : resolveManualSplitSourceCuts(member));
    return [...nativeCuts, ...(member.localFragment?.manualCuts || [])]
      .filter((cut) => !(member.localFragment?.suppressedCuts || []).includes(cut));
  };
  const memberEntries = layout.members.map((member) => ({
    ctg: {
      assemblyCtgId: member.assemblyCtgId,
      lengthBp: member.lengthBp,
      laneIndex: member.lane === "top" ? 0 : 1,
    },
    rect: member,
    markup: renderMember(
      member,
      renderCandidate(member),
      candidatesLoaded,
      anchorCutsByEndpoint.get(endpointKey(member)) || [],
      member.lane === "top" ? TOP_Y : BOTTOM_Y,
      i18n,
      {
        escapeHtml, escapeAttr, resolveTrackToneClass,
        splitSourceCuts: splitCuts(member),
        selected: (subview.trackPairSelectedCtgs || []).some((entry) => entry.compositionEntityKey
          ? entry.compositionEntityKey === member.entityKey
          : entry.contigId === member.assemblyCtgId && entry.trackRole === member.source.role),
        grtOverlay: grtResult.context?.subviewEnabled ? grtScene.overlaysByKey.get(member.entityKey) : "",
        minVisibleX: layout.viewBoxMinX,
        maxVisibleX: layout.viewBoxMinX + layout.width,
      },
    ),
  }));
  const memberMarkup = sortTrackEntriesForRender(memberEntries).map((entry) => entry.markup).join("");
  const topCount = layout.top.length;
  const bottomCount = layout.bottom.length;
  const rulerEndBp = Math.max(
    0,
    ...composition.members.map((member) => member.xBp + member.lengthBp),
  );
  const rulerWidth = Math.max(1, rulerEndBp / layout.bpPerPx);
  const rulerGeometry = resolveSubviewRulerGeometry({
    windowStart: 0,
    windowEnd: rulerEndBp,
    tickBp: resolveTickBpFromScale({ ...prefs, domainSpanBp: Math.max(1, rulerEndBp), visibleSpanBp: viewportWidthPx * layout.bpPerPx, baseViewportPx: viewportWidthPx }),
    innerWidth: rulerWidth,
    domainSpanBp: Math.max(1, rulerEndBp),
    originX: 0,
  });
  const emptyTop = topCount ? "" : `<text class="track-row-empty-label" x="12" y="${TOP_Y + 12}">${escapeHtml(i18n.trackControls.topTrackEmpty)}</text>`;
  const emptyBottom = bottomCount ? "" : `<text class="track-row-empty-label" x="12" y="${BOTTOM_Y + 12}">${escapeHtml(i18n.trackControls.bottomTrackEmpty)}</text>`;
  const trackOrderButtonTopPx = ((TOP_Y + BOTTOM_Y) / 2 - 4).toFixed(2);
  const statusMarkup = topCount && bottomCount
    ? evidenceStatus(subview?.pairwiseEvidence, i18n.subview, escapeHtml)
    : `<span class="muted">${escapeHtml(i18n.subview.compositionEvidenceNeedsBothLanes)}</span>`;
  return `<article class="assembly-track-panel subview-alignment-card" data-subview-composition-scene="1"
    data-grt-result-scene-visible="${grtScene.hasVisibleResult ? "1" : "0"}">
    ${statusMarkup ? `<div class="subview-evidence-status" role="status">${statusMarkup}</div>` : ""}
    <div class="assembly-track-layout subview-track-layout">
      ${renderAlignmentIdentityLegend(i18n.trackControls, escapeAttr)}
      <div class="assembly-track-label-column subview-track-label-column" style="width:136px;height:${CONTENT_HEIGHT}px">
        <div class="assembly-track-label-row" style="top:${TOP_Y - 4}px">${escapeHtml(i18n.subview.tools.compositionManager.lanes.top)}</div>
        ${renderTrackOrderToggleButton({
          className: "is-in-label-column",
          style: `top:${trackOrderButtonTopPx}px`,
          swapTrackOrderLabel: i18n.subview.swapTrackOrderAria,
        })}
        <div class="assembly-track-label-row" style="top:${BOTTOM_Y - 4}px">${escapeHtml(i18n.subview.tools.compositionManager.lanes.bottom)}</div>
      </div>
      <div class="assembly-track-scroll subview-track-scroll" data-track-role="subview"
        data-view-navigation-start-bp="${layout.contentStartBp}"
        data-view-navigation-end-bp="${layout.contentEndBp}"
        data-subview-domain-span-bp="${layout.width * layout.bpPerPx}" data-subview-inner-width="${layout.width}"
        data-subview-viewbox-min-x="${layout.viewBoxMinX}" data-subview-window-start-bp="0">
        <div class="subview-band-tooltip is-hidden" data-subview-band-tooltip-delay-ms="500" aria-hidden="true"></div>
        <svg class="assembly-track-svg subview-track-svg" width="${layout.width}" height="${CONTENT_HEIGHT}"
          viewBox="${layout.viewBoxMinX} 0 ${layout.width} ${CONTENT_HEIGHT}" preserveAspectRatio="xMinYMin meet">
          <line class="track-ruler-line" x1="0" y1="${RULER_Y}" x2="${rulerWidth}" y2="${RULER_Y}" />
          ${renderSubviewVirtualRuler({
            ...rulerGeometry,
            tickY1: RULER_Y,
            tickY2: CONTENT_HEIGHT - 20,
            tickLabelY: RULER_Y - 6 * Math.max(1, getGraphFontSize() / 12),
          })}
          ${bandMarkup}${emptyTop}${emptyBottom}
          ${renderGrtResultOverlayGroup({
            layer: "junction",
            markup: grtResult.context?.subviewEnabled ? grtScene.junctionMarkup : "",
            escapeAttr,
          })}
          ${memberMarkup}
          ${renderEvidenceAnchors(bands, composition.activeAnchors, escapeAttr)}
          ${renderManualAnchors(layout, composition.manualAnchors, escapeAttr)}
          ${renderManualAnchors(layout, composition.activeAnchors.filter((anchor) => anchor.descriptor).map((anchor) => ({ ...anchor, endpointA: anchor.descriptor.top, endpointB: anchor.descriptor.bottom })), escapeAttr, true)}
          ${grtAnchorScene.markup}
        </svg>
      </div>
    </div>
  </article>`;
}
