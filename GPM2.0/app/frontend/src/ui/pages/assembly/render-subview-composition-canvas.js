import {
  buildSubviewAnchorEndpointKey,
  deriveSubviewContigFragments,
} from "./subview-anchor-state.js";
import { buildSubviewAnchorObjectId } from "./subview-anchor-objects.js";
import { buildSubviewGrtAnchorScene } from "./subview-grt-anchor-state.js";
import { buildGrtResultScene } from "./grt-result-render.js";
import { renderSubviewVirtualRuler, resolveHitMapq, sortTrackEntriesForRender } from "./track-render-geometry.js";
import { normalizePositiveInt, resolveTrackPrefs } from "./track-prefs.js";
import { resolveSubviewCompositionCandidate } from "./subview-composition-candidates.js";
import { buildSubviewCompositionLayout } from "./subview-composition-layout.js";
import { getSubviewComposition } from "./subview-composition-state.js";
import { normalizeSupportDatasetId } from "./selection-state.js";
import {
  formatTrackCtgOrientationLabel,
  resolveBoundedTrackCtgLabelPlacement,
  resolveTrackCtgEffectiveOrientation,
  resolveTrackCtgVisibleName,
} from "./track-label-geometry.js";

const TOP_Y = 82;
const BOTTOM_Y = 190;
const BAR_HEIGHT = 14;
const CONTENT_HEIGHT = 248;

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
  return buildSubviewAnchorEndpointKey({
    role: member.source?.role,
    contigId: member.assemblyCtgId,
    datasetId: member.source?.datasetId,
    source: member.source?.sourceType,
    isMirror: member.source?.mirrored,
    phasedTrackId: member.source?.phasedTrackId,
    phasedTrackItemId: member.source?.phasedItemId,
    phasedHaplotypeKey: member.source?.hap,
  });
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
  const topById = new Map(layout.top.filter((member) => member.assemblyCtgId)
    .map((member) => [member.assemblyCtgId, member]));
  const bottomById = new Map(layout.bottom.filter((member) => member.assemblyCtgId)
    .map((member) => [member.assemblyCtgId, member]));
  return (Array.isArray(evidence?.hits) ? evidence.hits : []).map((hit, index) => {
    const length = normalizePositiveInt(hit?.alignLength ?? hit?.align_length) ?? 0;
    if (length < prefs.alignmentLength || resolveHitMapq(hit) < prefs.mapq) return null;
    const queryId = normalizeSupportDatasetId(hit?.queryAssemblyCtgId ?? hit?.query_assembly_ctg_id);
    const subjectId = normalizeSupportDatasetId(hit?.subjectAssemblyCtgId ?? hit?.subject_assembly_ctg_id);
    let top = topById.get(queryId);
    let bottom = bottomById.get(subjectId);
    let topStart = hitField(hit, "queryStart", "query_start");
    let topEnd = hitField(hit, "queryEnd", "query_end");
    let bottomStart = hitField(hit, "subjectStart", "subject_start");
    let bottomEnd = hitField(hit, "subjectEnd", "subject_end");
    if (!top || !bottom) {
      top = topById.get(subjectId);
      bottom = bottomById.get(queryId);
      topStart = hitField(hit, "subjectStart", "subject_start");
      topEnd = hitField(hit, "subjectEnd", "subject_end");
      bottomStart = hitField(hit, "queryStart", "query_start");
      bottomEnd = hitField(hit, "queryEnd", "query_end");
    }
    if (!top || !bottom || [topStart, topEnd, bottomStart, bottomEnd].some((value) => value === null)) {
      return null;
    }
    const topRange = rangeX(top, topStart, topEnd);
    const bottomRange = rangeX(bottom, bottomStart, bottomEnd);
    const strand = String(hit?.strand || hit?.orient || "+").trim();
    const reversed = ((strand === "-") !== Boolean(top.flipped)) !== Boolean(bottom.flipped);
    return {
      hitKey: String(hit?.hitKey || `composition-pairwise-${index + 1}`),
      top,
      bottom,
      topRange,
      bottomRange,
      topCuts: rangeCuts(top, topStart, topEnd),
      bottomCuts: rangeCuts(bottom, bottomStart, bottomEnd),
      reversed,
    };
  }).filter(Boolean);
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
      const candidate = resolveSubviewCompositionCandidate(candidates, contig);
      const referenceStart = Number(ref.reference?.startBp);
      const referenceEnd = Number(ref.reference?.endBp);
      if (!candidate || !Number.isFinite(referenceStart) || !Number.isFinite(referenceEnd)) continue;
      for (const [index, hit] of (Array.isArray(candidate.ctg?.hits) ? candidate.ctg.hits : []).entries()) {
        const length = normalizePositiveInt(hit?.blockLength ?? hit?.block_length) ?? 0;
        if (length < prefs.alignmentLength || resolveHitMapq(hit) < prefs.mapq) continue;
        const rawRefStart = hitField(hit, "refStart", "ref_start");
        const rawRefEnd = hitField(hit, "refEnd", "ref_end");
        const ctgStart = hitField(hit, "ctgStart", "ctg_start");
        const ctgEnd = hitField(hit, "ctgEnd", "ctg_end");
        if ([rawRefStart, rawRefEnd, ctgStart, ctgEnd].some((value) => value === null)) continue;
        const overlapStart = Math.max(referenceStart, Math.min(rawRefStart, rawRefEnd));
        const overlapEnd = Math.min(referenceEnd, Math.max(rawRefStart, rawRefEnd));
        if (overlapEnd < overlapStart) continue;
        const refStart = overlapStart - referenceStart + 1;
        const refEnd = overlapEnd - referenceStart + 1;
        const topStart = topIsRef ? refStart : ctgStart;
        const topEnd = topIsRef ? refEnd : ctgEnd;
        const bottomStart = bottomIsRef ? refStart : ctgStart;
        const bottomEnd = bottomIsRef ? refEnd : ctgEnd;
        const strand = String(hit?.strand || hit?.orient || "+").trim();
        bands.push({
          hitKey: `reference:${top.entityKey}|${bottom.entityKey}|${String(hit?.hitKey || index + 1)}`,
          top,
          bottom,
          topRange: rangeX(top, topStart, topEnd),
          bottomRange: rangeX(bottom, bottomStart, bottomEnd),
          topCuts: rangeCuts(top, topStart, topEnd),
          bottomCuts: rangeCuts(bottom, bottomStart, bottomEnd),
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

function anchorAttrs(edge, kind, identity, active, escapeAttr) {
  const topSource = edge.top.source || {};
  const bottomSource = edge.bottom.source || {};
  const objectId = buildSubviewAnchorObjectId(kind, identity, kind === "manual" ? "manual" : edge.edge);
  return `data-subview-anchor-kind="${kind}" data-subview-anchor-object-id="${escapeAttr(objectId)}"
    data-subview-anchor-hit-key="${escapeAttr(edge.hitKey || "")}" data-subview-anchor-edge="${escapeAttr(edge.edge || "manual")}"
    data-subview-anchor-active="${active ? "1" : "0"}" data-subview-manual-anchor-id="${escapeAttr(edge.manualAnchorId || "")}"
    data-subview-anchor-top-endpoint-key="${escapeAttr(endpointKey(edge.top))}" data-subview-anchor-bottom-endpoint-key="${escapeAttr(endpointKey(edge.bottom))}"
    data-subview-anchor-top-contig-id="${edge.top.assemblyCtgId || 0}" data-subview-anchor-bottom-contig-id="${edge.bottom.assemblyCtgId || 0}"
    data-subview-anchor-top-cut-bp="${Math.round(edge.topCut)}" data-subview-anchor-bottom-cut-bp="${Math.round(edge.bottomCut)}"
    data-subview-anchor-top-length-bp="${edge.top.lengthBp}" data-subview-anchor-bottom-length-bp="${edge.bottom.lengthBp}"
    data-subview-anchor-top-name="${escapeAttr(edge.top.label)}" data-subview-anchor-bottom-name="${escapeAttr(edge.bottom.label)}"
    data-subview-anchor-top-source-role="${escapeAttr(topSource.role || "")}" data-subview-anchor-bottom-source-role="${escapeAttr(bottomSource.role || "")}"
    data-subview-anchor-top-source-kind="${escapeAttr(topSource.sourceType || "")}" data-subview-anchor-bottom-source-kind="${escapeAttr(bottomSource.sourceType || "")}"
    data-subview-anchor-top-source-name="${escapeAttr(topSource.datasetName || topSource.hap || "")}" data-subview-anchor-bottom-source-name="${escapeAttr(bottomSource.datasetName || bottomSource.hap || "")}
    " data-subview-anchor-top-x="${edge.topX.toFixed(4)}" data-subview-anchor-bottom-x="${edge.bottomX.toFixed(4)}"`;
}

function renderEvidenceAnchors(bands, activeAnchors, escapeAttr) {
  const active = new Set((Array.isArray(activeAnchors) ? activeAnchors : [])
    .map((anchor) => `${anchor.hitKey}:${anchor.edge}`));
  return bands.flatMap((band) => ["left", "right"].map((side) => {
    const points = edgeDescriptor(band, side);
    const edge = { ...band, ...points, edge: side };
    const isActive = active.has(`${band.hitKey}:${side}`);
    const attrs = anchorAttrs(edge, "evidence", band.hitKey, isActive, escapeAttr);
    return `<line class="subview-anchor-line${isActive ? " is-active" : ""}" x1="${points.topX.toFixed(2)}"
      y1="${TOP_Y + BAR_HEIGHT}" x2="${points.bottomX.toFixed(2)}" y2="${BOTTOM_Y}"
      stroke="${isActive ? "red" : "transparent"}" stroke-width="3" pointer-events="none" />
      <line class="subview-anchor-hit-zone${isActive ? " is-active" : ""}" x1="${points.topX.toFixed(2)}"
      y1="${TOP_Y + BAR_HEIGHT}" x2="${points.bottomX.toFixed(2)}" y2="${BOTTOM_Y}"
      stroke="transparent" stroke-width="4" pointer-events="stroke" ${attrs} />`;
  })).join("");
}

function renderManualAnchors(layout, anchors, escapeAttr) {
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
      manualAnchorId: anchor.manualAnchorId,
      edge: "manual",
    };
    return `<line class="subview-anchor-line is-active" x1="${edge.topX.toFixed(2)}" y1="${TOP_Y + BAR_HEIGHT}"
      x2="${edge.bottomX.toFixed(2)}" y2="${BOTTOM_Y}" stroke="red" stroke-width="3" pointer-events="none" />
      <line class="subview-anchor-hit-zone is-active" x1="${edge.topX.toFixed(2)}" y1="${TOP_Y + BAR_HEIGHT}"
      x2="${edge.bottomX.toFixed(2)}" y2="${BOTTOM_Y}" stroke="transparent" stroke-width="4"
      pointer-events="stroke" ${anchorAttrs(edge, "manual", anchor.manualAnchorId, true, escapeAttr)} />`;
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
  return cuts;
}

function renderMemberFragments(member, cuts, y, { escapeHtml, escapeAttr }) {
  const fragments = deriveSubviewContigFragments({
    contig: {
      assemblyCtgId: member.assemblyCtgId,
      role: member.source?.role,
      lengthBp: member.lengthBp,
    },
    anchorCuts: cuts,
  });
  if (!fragments.length) return "";
  const orientation = memberOrientation(member);
  return fragments.map((fragment) => {
    const range = rangeX(member, fragment.start, fragment.end);
    const width = Math.max(1, range.right - range.left);
    const title = `${memberFullDisplayLabel(member)}:${fragment.start.toLocaleString()}-${fragment.end.toLocaleString()}`;
    return `<rect class="subview-fragment-hit-zone" x="${range.left.toFixed(2)}" y="${y}"
        width="${width.toFixed(2)}" height="${BAR_HEIGHT}" fill="transparent"
        data-subview-fragment-key="${escapeAttr(fragment.fragmentKey)}"
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
  }).join("");
}

function renderMember(member, candidate, candidatesLoaded, cuts, y, labels, {
  escapeHtml,
  escapeAttr,
  resolveTrackToneClass,
  grtOverlay = "",
  minVisibleX,
  maxVisibleX,
}) {
  const role = member.source?.role || "support";
  const tone = resolveTrackToneClass(role);
  const source = sourceName(member, labels);
  const label = memberDisplayLabel(member);
  const title = `${memberFullDisplayLabel(member)} · ${source} · ${member.lengthBp.toLocaleString()} bp`;
  const unavailable = candidate || !candidatesLoaded ? "" : " is-unavailable";
  const orient = memberOrientation(member);
  const placement = resolveBoundedTrackCtgLabelPlacement({
    ctgName: label,
    role,
    rect: member,
    barY: y,
    barHeight: BAR_HEIGHT,
    inlineTextOffsetY: 11,
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
      data-subview-contig-id="${member.assemblyCtgId || 0}" data-subview-track-ref-orient="${orient}"
      data-subview-rect-x="${member.x.toFixed(2)}" data-subview-rect-y="${y}"
      data-subview-rect-width="${member.width.toFixed(2)}" data-subview-rect-height="${BAR_HEIGHT}">
    <title>${escapeHtml(title)}</title>
    <rect class="track-ctg subview-track-ctg${tone}" x="${member.x.toFixed(2)}" y="${y}"
      width="${member.width.toFixed(2)}" height="${BAR_HEIGHT}" rx="4" ry="4" pointer-events="all" />
    ${grtOverlay}
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
  historyControls,
  viewportWidthPx,
  chrName,
  grtAnchorPlan,
  resolveTrackToneClass,
  escapeHtml,
  escapeAttr,
}) {
  const composition = getSubviewComposition(subview);
  if (!composition) return "";
  const prefs = resolveTrackPrefs(trackPrefs);
  const viewport = supportContext?.compositionViewport || {};
  const layout = buildSubviewCompositionLayout(composition, {
    bpPerPx: viewport.bpPerPx,
    viewportWidthPx,
    leftBp: viewport.leftBp,
  });
  const candidates = supportContext?.compositionCandidates || [];
  const candidatesLoaded = supportContext?.compositionCandidatesLoaded === true;
  const grtEntries = layout.members.map((member) => ({
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
    plan: grtResult.context?.available ? grtResult.plan : null,
    entries: grtEntries,
    layers: grtResult.context?.subviewLayers,
    escapeHtml,
    gapLabel: i18n.grtResult.gapLabel,
  });
  const bands = [
    ...buildEvidenceBands(layout, subview?.pairwiseEvidence, prefs),
    ...buildReferenceBands(layout, candidates, prefs),
  ];
  const bandMarkup = bands.map((band) => {
    const bottomLeft = band.reversed ? band.bottomRange.right : band.bottomRange.left;
    const bottomRight = band.reversed ? band.bottomRange.left : band.bottomRange.right;
    const points = [
      `${band.topRange.left.toFixed(2)},${TOP_Y + BAR_HEIGHT}`,
      `${band.topRange.right.toFixed(2)},${TOP_Y + BAR_HEIGHT}`,
      `${bottomRight.toFixed(2)},${BOTTOM_Y}`,
      `${bottomLeft.toFixed(2)},${BOTTOM_Y}`,
    ].join(" ");
    return `<polygon class="track-collinearity-band" points="${points}" pointer-events="visibleFill"
      data-track-band-proxy="1" data-subview-hit-key="${escapeAttr(band.hitKey)}"
      data-subview-top-contig-id="${band.top.assemblyCtgId || 0}"
      data-subview-bottom-contig-id="${band.bottom.assemblyCtgId || 0}" />`;
  }).join("");
  const anchorCutsByEndpoint = buildAnchorCutsByEndpoint(
    layout,
    bands,
    composition.activeAnchors,
    composition.manualAnchors,
  );
  const memberEntries = layout.members.map((member) => ({
    ctg: {
      assemblyCtgId: member.assemblyCtgId,
      lengthBp: member.lengthBp,
      laneIndex: member.lane === "top" ? 0 : 1,
    },
    rect: member,
    markup: renderMember(
      member,
      resolveSubviewCompositionCandidate(candidates, member),
      candidatesLoaded,
      anchorCutsByEndpoint.get(endpointKey(member)) || [],
      member.lane === "top" ? TOP_Y : BOTTOM_Y,
      i18n,
      {
        escapeHtml, escapeAttr, resolveTrackToneClass,
        grtOverlay: grtResult.context?.subviewEnabled ? grtScene.overlaysByKey.get(member.entityKey) : "",
        minVisibleX: layout.viewBoxMinX,
        maxVisibleX: layout.viewBoxMinX + layout.width,
      },
    ),
  }));
  const memberMarkup = sortTrackEntriesForRender(memberEntries).map((entry) => entry.markup).join("");
  const topCount = layout.top.length;
  const bottomCount = layout.bottom.length;
  const emptyTop = topCount ? "" : `<text class="track-row-empty-label" x="12" y="${TOP_Y + 12}">${escapeHtml(i18n.trackControls.topTrackEmpty)}</text>`;
  const emptyBottom = bottomCount ? "" : `<text class="track-row-empty-label" x="12" y="${BOTTOM_Y + 12}">${escapeHtml(i18n.trackControls.bottomTrackEmpty)}</text>`;
  return `<article class="assembly-track-panel subview-alignment-card" data-subview-composition-scene="1"
    data-grt-result-scene-visible="${grtScene.hasVisibleResult ? "1" : "0"}">
    <div class="assembly-track-panel-head"><strong>${escapeHtml(i18n.subview.compositionTitle
      .replace("{top}", topCount).replace("{bottom}", bottomCount))}</strong>${historyControls}
      ${topCount && bottomCount
        ? evidenceStatus(subview?.pairwiseEvidence, i18n.subview, escapeHtml)
        : `<span class="muted">${escapeHtml(i18n.subview.compositionEvidenceNeedsBothLanes)}</span>`}</div>
    <div class="assembly-track-layout subview-track-layout">
      <div class="assembly-track-label-column subview-track-label-column" style="width:136px;height:${CONTENT_HEIGHT}px">
        <div class="assembly-track-label-row" style="top:${TOP_Y - 4}px">${escapeHtml(i18n.subview.tools.compositionManager.lanes.top)}</div>
        <div class="assembly-track-label-row" style="top:${BOTTOM_Y - 4}px">${escapeHtml(i18n.subview.tools.compositionManager.lanes.bottom)}</div>
      </div>
      <div class="assembly-track-scroll subview-track-scroll" data-track-role="subview"
        data-subview-domain-span-bp="${Math.round(layout.width * layout.bpPerPx)}" data-subview-inner-width="${layout.width}"
        data-subview-viewbox-min-x="${layout.viewBoxMinX}">
        <svg class="assembly-track-svg subview-track-svg" width="${layout.width}" height="${CONTENT_HEIGHT}"
          viewBox="${layout.viewBoxMinX} 0 ${layout.width} ${CONTENT_HEIGHT}" preserveAspectRatio="xMinYMin meet">
          <line class="track-ruler-line" x1="${layout.viewBoxMinX}" y1="48" x2="${layout.viewBoxMinX + layout.width}" y2="48" />
          ${renderSubviewVirtualRuler({
            windowStart: layout.viewBoxMinX * layout.bpPerPx,
            windowEnd: (layout.viewBoxMinX + layout.width) * layout.bpPerPx,
            originX: layout.viewBoxMinX,
            tickBp: prefs.minTickUnitKb * 1000,
            innerWidth: layout.width,
            domainSpanBp: layout.width * layout.bpPerPx,
            tickY1: 48,
            tickY2: CONTENT_HEIGHT - 20,
            tickLabelY: 42,
          })}
          ${bandMarkup}${emptyTop}${emptyBottom}
          ${grtResult.context?.subviewEnabled ? grtScene.junctionMarkup : ""}
          ${memberMarkup}
          ${renderEvidenceAnchors(bands, composition.activeAnchors, escapeAttr)}
          ${renderManualAnchors(layout, composition.manualAnchors, escapeAttr)}
          ${grtAnchorScene.markup}
        </svg>
      </div>
    </div>
  </article>`;
}
