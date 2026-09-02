import { resolveTrackScrollLeftForViewboxShift } from "./track-viewport.js";

const MAIN_TRACK_PREVIEW_CLASS = "is-track-drag-preview";
const SUBVIEW_TRACK_PREVIEW_CLASS = "is-subview-track-drag-preview";
const ORIGINAL_POINTS_ATTR = "data-drag-preview-original-points";
const ORIGINAL_TRANSFORM_ATTR = "data-drag-preview-original-transform";
const ORIGINAL_STYLE_TRANSFORM_ATTR = "data-drag-preview-original-style-transform";
const ORIGINAL_X1_ATTR = "data-drag-preview-original-x1";
const ORIGINAL_X2_ATTR = "data-drag-preview-original-x2";
const ORIGINAL_X_ATTR = "data-drag-preview-original-x";
const PREVIEW_GROUP_ATTR = "data-drag-preview-group";
const PREVIEW_BAND_ATTR = "data-drag-preview-band";
const PREVIEW_STICKY_LABEL_ATTR = "data-drag-preview-sticky-label";
const PREVIEW_JUNCTION_LINE_ATTR = "data-drag-preview-junction-line";
const PREVIEW_JUNCTION_LABEL_ATTR = "data-drag-preview-junction-label";
const PREVIEW_ENVELOPE_ATTR = "data-drag-preview-envelope";
const ORIGINAL_WIDTH_ATTR = "data-drag-preview-original-width";
const ORIGINAL_VIEW_BOX_ATTR = "data-drag-preview-original-view-box";
const ORIGINAL_STYLE_WIDTH_ATTR = "data-drag-preview-original-style-width";
const ORIGINAL_SUBVIEW_VIEWBOX_MIN_X_ATTR = "data-drag-preview-original-subview-viewbox-min-x";
const PREVIEW_ENVELOPE_MIN_X_ATTR = "data-drag-preview-envelope-min-x";
const PREVIEW_ENVELOPE_MAX_X_ATTR = "data-drag-preview-envelope-max-x";
const MISSING_ATTRIBUTE_VALUE = "__gpm_missing_attribute__";

function parsePolygonPoints(pointsText) {
  return String(pointsText || "")
    .trim()
    .split(/\s+/)
    .map((token) => token.split(",").map((value) => Number(value)))
    .filter((pair) => pair.length === 2 && Number.isFinite(pair[0]) && Number.isFinite(pair[1]));
}

function stringifyPolygonPoints(points) {
  return points
    .map(([x, y]) => `${Number(x || 0).toFixed(2)},${Number(y || 0).toFixed(2)}`)
    .join(" ");
}

function shiftPolygonEdge(pointsText, edgeIndexes, offsetPx) {
  const points = parsePolygonPoints(pointsText);
  if (!points.length) {
    return String(pointsText || "");
  }
  edgeIndexes.forEach((index) => {
    if (!Array.isArray(points[index])) {
      return;
    }
    points[index][0] = Number(points[index][0] || 0) + Number(offsetPx || 0);
  });
  return stringifyPolygonPoints(points);
}

function applyGroupPreview(groupNode, offsetPx) {
  if (!groupNode) {
    return;
  }
  if (!groupNode.hasAttribute?.(ORIGINAL_TRANSFORM_ATTR)) {
    const originalTransform = groupNode.getAttribute?.("transform");
    groupNode.setAttribute?.(ORIGINAL_TRANSFORM_ATTR, originalTransform === null ? "" : originalTransform);
  }
  const normalizedOffset = Number(offsetPx || 0);
  if (!Number.isFinite(normalizedOffset) || Math.abs(normalizedOffset) < 0.01) {
    const originalTransform = groupNode.getAttribute?.(ORIGINAL_TRANSFORM_ATTR) || "";
    if (originalTransform) {
      groupNode.setAttribute?.("transform", originalTransform);
    } else {
      groupNode.removeAttribute?.("transform");
    }
  } else {
    groupNode.setAttribute?.("transform", `translate(${normalizedOffset.toFixed(2)} 0)`);
  }
  groupNode.setAttribute?.(PREVIEW_GROUP_ATTR, "1");
}

function applyBandPreview(bandNode, edgeIndexes, offsetPx) {
  if (!bandNode) {
    return;
  }
  if (!bandNode.hasAttribute?.(ORIGINAL_POINTS_ATTR)) {
    bandNode.setAttribute?.(ORIGINAL_POINTS_ATTR, bandNode.getAttribute?.("points") || "");
  }
  const originalPoints = bandNode.getAttribute?.(ORIGINAL_POINTS_ATTR) || "";
  bandNode.setAttribute?.("points", shiftPolygonEdge(originalPoints, edgeIndexes, offsetPx));
  bandNode.setAttribute?.(PREVIEW_BAND_ATTR, "1");
}

function applyStickyLabelPreview(labelNode, offsetPx) {
  if (!labelNode) {
    return;
  }
  if (!labelNode.hasAttribute?.(ORIGINAL_STYLE_TRANSFORM_ATTR)) {
    labelNode.setAttribute?.(ORIGINAL_STYLE_TRANSFORM_ATTR, String(labelNode.style?.transform || ""));
  }
  const normalizedOffset = Number(offsetPx || 0);
  labelNode.style.transform = Number.isFinite(normalizedOffset) && Math.abs(normalizedOffset) >= 0.01
    ? `translateX(${normalizedOffset}px)`
    : "";
  labelNode.setAttribute?.(PREVIEW_STICKY_LABEL_ATTR, "1");
}

function applyJunctionLinePreview(lineNode, leftOffsetPx, rightOffsetPx) {
  if (!lineNode) {
    return;
  }
  if (!lineNode.hasAttribute?.(ORIGINAL_X1_ATTR)) {
    lineNode.setAttribute?.(ORIGINAL_X1_ATTR, lineNode.getAttribute?.("x1") || "0");
  }
  if (!lineNode.hasAttribute?.(ORIGINAL_X2_ATTR)) {
    lineNode.setAttribute?.(ORIGINAL_X2_ATTR, lineNode.getAttribute?.("x2") || "0");
  }
  const originalX1 = Number(lineNode.getAttribute?.(ORIGINAL_X1_ATTR) || 0);
  const originalX2 = Number(lineNode.getAttribute?.(ORIGINAL_X2_ATTR) || 0);
  lineNode.setAttribute?.("x1", (originalX1 + Number(leftOffsetPx || 0)).toFixed(2));
  lineNode.setAttribute?.("x2", (originalX2 + Number(rightOffsetPx || 0)).toFixed(2));
  lineNode.setAttribute?.(PREVIEW_JUNCTION_LINE_ATTR, "1");
}

function applyJunctionLabelPreview(labelNode, offsetPx) {
  if (!labelNode) {
    return;
  }
  if (!labelNode.hasAttribute?.(ORIGINAL_X_ATTR)) {
    labelNode.setAttribute?.(ORIGINAL_X_ATTR, labelNode.getAttribute?.("x") || "0");
  }
  const originalX = Number(labelNode.getAttribute?.(ORIGINAL_X_ATTR) || 0);
  labelNode.setAttribute?.("x", (originalX + Number(offsetPx || 0)).toFixed(2));
  labelNode.setAttribute?.(PREVIEW_JUNCTION_LABEL_ATTR, "1");
}

function applyGrtJunctionPreview(host, groupNodes, offsetPx) {
  const entryKeys = new Set();
  groupNodes.forEach((groupNode) => {
    const entryKey = String(groupNode.getAttribute?.("data-grt-result-entry-key") || "").trim();
    if (entryKey) {
      entryKeys.add(entryKey);
    }
  });
  if (!entryKeys.size) {
    return;
  }
  const normalizedOffset = Number(offsetPx || 0);
  const junctionNodes = host?.querySelectorAll?.("[data-grt-result-junction]") || [];
  junctionNodes.forEach((junctionNode) => {
    const leftEntryKey = String(
      junctionNode.getAttribute?.("data-grt-result-junction-left-entry-key") || "",
    ).trim();
    const rightEntryKey = String(
      junctionNode.getAttribute?.("data-grt-result-junction-right-entry-key") || "",
    ).trim();
    const leftMatched = entryKeys.has(leftEntryKey);
    const rightMatched = entryKeys.has(rightEntryKey);
    if (!leftMatched && !rightMatched) {
      return;
    }
    const leftOffset = leftMatched ? normalizedOffset : 0;
    const rightOffset = rightMatched ? normalizedOffset : 0;
    if (leftMatched && rightMatched) {
      applyGroupPreview(junctionNode, leftOffset);
      return;
    }
    const lineNodes = junctionNode.querySelectorAll?.("[data-grt-result-junction-line='1']") || [];
    lineNodes.forEach((lineNode) => applyJunctionLinePreview(lineNode, leftOffset, rightOffset));
    const labelOffset = (leftOffset + rightOffset) / 2;
    const labelNodes = junctionNode.querySelectorAll?.("[data-grt-result-junction-label='1']") || [];
    labelNodes.forEach((labelNode) => applyJunctionLabelPreview(labelNode, labelOffset));
  });
}

function applyGrtDisplayEvidencePreview(host, groupNodes, offsetPx) {
  const entryKeys = new Set();
  groupNodes.forEach((groupNode) => {
    const entryKey = String(groupNode.getAttribute?.("data-grt-result-entry-key") || "").trim();
    if (entryKey) {
      entryKeys.add(entryKey);
    }
  });
  if (!entryKeys.size) {
    return;
  }
  const evidenceNodes = host?.querySelectorAll?.("[data-grt-display-evidence]") || [];
  evidenceNodes.forEach((evidenceNode) => {
    const sourceEntryKey = String(
      evidenceNode.getAttribute?.("data-grt-display-evidence-source-entry-key") || "",
    ).trim();
    const targetEntryKey = String(
      evidenceNode.getAttribute?.("data-grt-display-evidence-target-entry-key") || "",
    ).trim();
    const edgeIndexes = [];
    if (entryKeys.has(sourceEntryKey)) {
      edgeIndexes.push(0, 1);
    }
    if (entryKeys.has(targetEntryKey)) {
      edgeIndexes.push(2, 3);
    }
    if (edgeIndexes.length) {
      applyBandPreview(evidenceNode, edgeIndexes, offsetPx);
    }
  });
}

function isLabelInsideGroup(labelNode, groupNode) {
  if (!labelNode || !groupNode || typeof groupNode.contains !== "function") {
    return false;
  }
  return groupNode.contains(labelNode);
}

function parseSvgViewBox(value) {
  const parts = String(value || "")
    .trim()
    .split(/\s+/)
    .map(Number);
  if (parts.length !== 4 || parts.some((part) => !Number.isFinite(part))) {
    return null;
  }
  return parts;
}

function formatPreviewMetric(value) {
  return String(Math.round(Number(value || 0) * 100) / 100);
}

function rememberPreviewAttribute(node, originalAttributeName, targetAttributeName) {
  if (!node || node.hasAttribute?.(originalAttributeName)) {
    return;
  }
  const currentValue = node.getAttribute?.(targetAttributeName);
  node.setAttribute?.(
    originalAttributeName,
    currentValue === null ? MISSING_ATTRIBUTE_VALUE : currentValue,
  );
}

function restorePreviewAttribute(node, originalAttributeName, targetAttributeName) {
  if (!node?.hasAttribute?.(originalAttributeName)) {
    return;
  }
  const originalValue = node.getAttribute?.(originalAttributeName);
  if (originalValue === MISSING_ATTRIBUTE_VALUE) {
    node.removeAttribute?.(targetAttributeName);
  } else {
    node.setAttribute?.(targetAttributeName, originalValue || "");
  }
  node.removeAttribute?.(originalAttributeName);
}

function restoreSubviewPreviewEnvelope(host) {
  const envelopeNodes = host?.querySelectorAll?.(`[${PREVIEW_ENVELOPE_ATTR}='1']`) || [];
  envelopeNodes.forEach((node) => {
    restorePreviewAttribute(node, ORIGINAL_WIDTH_ATTR, "width");
    restorePreviewAttribute(node, ORIGINAL_VIEW_BOX_ATTR, "viewBox");
    restorePreviewAttribute(node, ORIGINAL_X_ATTR, "x");
    restorePreviewAttribute(
      node,
      ORIGINAL_SUBVIEW_VIEWBOX_MIN_X_ATTR,
      "data-subview-viewbox-min-x",
    );
    if (node.hasAttribute?.(ORIGINAL_STYLE_WIDTH_ATTR)) {
      node.style.width = node.getAttribute?.(ORIGINAL_STYLE_WIDTH_ATTR) || "";
      node.removeAttribute?.(ORIGINAL_STYLE_WIDTH_ATTR);
    }
    node.removeAttribute?.(PREVIEW_ENVELOPE_MIN_X_ATTR);
    node.removeAttribute?.(PREVIEW_ENVELOPE_MAX_X_ATTR);
    node.removeAttribute?.(PREVIEW_ENVELOPE_ATTR);
  });
}

function applySubviewPreviewEnvelope(groupNodes, offsetPx, { pointerClientX = null } = {}) {
  const normalizedOffset = Number(offsetPx || 0);
  if (!Number.isFinite(normalizedOffset)) {
    return undefined;
  }
  const groupsByScroll = new Map();
  groupNodes.forEach((groupNode) => {
    const scrollNode = groupNode.closest?.(
      ".assembly-track-scroll[data-track-role='subview']",
    );
    if (!scrollNode) {
      return;
    }
    const groups = groupsByScroll.get(scrollNode) || [];
    groups.push(groupNode);
    groupsByScroll.set(scrollNode, groups);
  });
  let previewState;
  groupsByScroll.forEach((groups, scrollNode) => {
    const canvasLayer = Array.from(
      scrollNode.querySelectorAll?.(
        "[data-track-band-canvas-scene-kind='subview-ctg']",
      ) || [],
    )[0] || Array.from(
      scrollNode.querySelectorAll?.(
        "[data-track-band-canvas-scene-kind='subview-track-pair']",
      ) || [],
    )[0] || null;
    const svgNode = Array.from(
      scrollNode.querySelectorAll?.(".subview-track-svg") || [],
    )[0] || null;
    const clipRectNodes = Array.from(
      scrollNode.querySelectorAll?.("[data-subview-band-clip-rect='1']") || [],
    );
    if (!canvasLayer || !svgNode) {
      return;
    }
    rememberPreviewAttribute(svgNode, ORIGINAL_WIDTH_ATTR, "width");
    rememberPreviewAttribute(svgNode, ORIGINAL_VIEW_BOX_ATTR, "viewBox");
    rememberPreviewAttribute(
      scrollNode,
      ORIGINAL_SUBVIEW_VIEWBOX_MIN_X_ATTR,
      "data-subview-viewbox-min-x",
    );
    if (!canvasLayer.hasAttribute?.(ORIGINAL_STYLE_WIDTH_ATTR)) {
      canvasLayer.setAttribute?.(ORIGINAL_STYLE_WIDTH_ATTR, String(canvasLayer.style?.width || ""));
    }
    const originalViewBox = parseSvgViewBox(
      svgNode.getAttribute?.(ORIGINAL_VIEW_BOX_ATTR)
      || svgNode.getAttribute?.("viewBox"),
    );
    if (!originalViewBox) {
      return;
    }
    const [baseMinX, baseMinY, baseWidth, baseHeight] = originalViewBox;
    const baseMaxX = baseMinX + baseWidth;
    const storedEnvelopeMinXAttr = scrollNode.getAttribute?.(PREVIEW_ENVELOPE_MIN_X_ATTR);
    const storedEnvelopeMaxXAttr = scrollNode.getAttribute?.(PREVIEW_ENVELOPE_MAX_X_ATTR);
    const storedEnvelopeMinX = storedEnvelopeMinXAttr === null
      ? Number.NaN
      : Number(storedEnvelopeMinXAttr);
    const storedEnvelopeMaxX = storedEnvelopeMaxXAttr === null
      ? Number.NaN
      : Number(storedEnvelopeMaxXAttr);
    const previousMinX = Number.isFinite(storedEnvelopeMinX)
      ? storedEnvelopeMinX
      : baseMinX;
    const previousMaxX = Number.isFinite(storedEnvelopeMaxX)
      ? storedEnvelopeMaxX
      : baseMaxX;
    const previewBounds = groups
      .map((groupNode) => {
        const x = Number(groupNode.getAttribute?.("data-subview-rect-x"));
        const width = Number(groupNode.getAttribute?.("data-subview-rect-width"));
        if (!Number.isFinite(x) || !Number.isFinite(width) || width < 0) {
          return null;
        }
        return {
          left: x + normalizedOffset,
          right: x + width + normalizedOffset,
        };
      })
      .filter(Boolean);
    if (!previewBounds.length) {
      return;
    }
    const previewLeft = Math.min(...previewBounds.map((bounds) => bounds.left));
    const previewRight = Math.max(...previewBounds.map((bounds) => bounds.right));
    const nextMinX = Math.floor(Math.min(previousMinX, baseMinX, previewLeft));
    const nextMaxX = Math.ceil(Math.max(previousMaxX, baseMaxX, previewRight));
    const nextWidth = Math.max(baseWidth, nextMaxX - nextMinX);
    const formattedWidth = formatPreviewMetric(nextWidth);
    const formattedMinX = formatPreviewMetric(nextMinX);
    svgNode.setAttribute?.("width", formattedWidth);
    svgNode.setAttribute?.(
      "viewBox",
      `${formattedMinX} ${formatPreviewMetric(baseMinY)} ${formattedWidth} ${formatPreviewMetric(baseHeight)}`,
    );
    canvasLayer.style.width = `${formattedWidth}px`;
    clipRectNodes.forEach((clipRectNode) => {
      rememberPreviewAttribute(clipRectNode, ORIGINAL_X_ATTR, "x");
      rememberPreviewAttribute(clipRectNode, ORIGINAL_WIDTH_ATTR, "width");
      clipRectNode.setAttribute?.("x", formattedMinX);
      clipRectNode.setAttribute?.("width", formattedWidth);
      clipRectNode.setAttribute?.(PREVIEW_ENVELOPE_ATTR, "1");
    });
    scrollNode.setAttribute?.("data-subview-viewbox-min-x", formattedMinX);
    scrollNode.setAttribute?.(PREVIEW_ENVELOPE_MIN_X_ATTR, formattedMinX);
    scrollNode.setAttribute?.(PREVIEW_ENVELOPE_MAX_X_ATTR, formatPreviewMetric(nextMaxX));
    svgNode.setAttribute?.(PREVIEW_ENVELOPE_ATTR, "1");
    canvasLayer.setAttribute?.(PREVIEW_ENVELOPE_ATTR, "1");
    scrollNode.setAttribute?.(PREVIEW_ENVELOPE_ATTR, "1");

    const viewportWidth = Math.max(0, Number(scrollNode.clientWidth || 0));
    const currentScrollLeft = Math.max(0, Number(scrollNode.scrollLeft || 0));
    let nextScrollLeft = resolveTrackScrollLeftForViewboxShift(
      currentScrollLeft,
      previousMinX,
      nextMinX,
    );
    if (
      viewportWidth > 0
      && pointerClientX !== null
      && pointerClientX !== ""
      && Number.isFinite(Number(pointerClientX))
    ) {
      const viewportRect = scrollNode.getBoundingClientRect?.();
      const viewportLeft = Number(viewportRect?.left);
      const viewportRight = Number(viewportRect?.right);
      const pointerX = Number(pointerClientX);
      if (Number.isFinite(viewportLeft) && Number.isFinite(viewportRight)) {
        if (pointerX < viewportLeft) {
          nextScrollLeft -= viewportLeft - pointerX;
        } else if (pointerX > viewportRight) {
          nextScrollLeft += pointerX - viewportRight;
        }
      }
    }
    const maxScrollLeft = Math.max(0, nextWidth - viewportWidth);
    nextScrollLeft = Math.max(0, Math.min(maxScrollLeft, Math.round(nextScrollLeft)));
    scrollNode.scrollLeft = nextScrollLeft;
    previewState = {
      scrollLeft: nextScrollLeft,
      viewboxMinX: nextMinX,
      viewportLeftX: nextMinX + nextScrollLeft,
    };
  });
  return previewState;
}

function clearPreviewNodes(host, previewClassName) {
  host?.classList?.remove?.(previewClassName);
  restoreSubviewPreviewEnvelope(host);
  const previewGroups = host?.querySelectorAll?.(`[${PREVIEW_GROUP_ATTR}='1']`) || [];
  previewGroups.forEach((groupNode) => {
    const originalTransform = groupNode.getAttribute?.(ORIGINAL_TRANSFORM_ATTR) || "";
    if (originalTransform) {
      groupNode.setAttribute?.("transform", originalTransform);
    } else {
      groupNode.removeAttribute?.("transform");
    }
    groupNode.removeAttribute?.(PREVIEW_GROUP_ATTR);
    groupNode.removeAttribute?.(ORIGINAL_TRANSFORM_ATTR);
  });
  const previewBands = host?.querySelectorAll?.(`[${PREVIEW_BAND_ATTR}='1']`) || [];
  previewBands.forEach((bandNode) => {
    const originalPoints = bandNode.getAttribute?.(ORIGINAL_POINTS_ATTR) || "";
    bandNode.setAttribute?.("points", originalPoints);
    bandNode.removeAttribute?.(PREVIEW_BAND_ATTR);
    bandNode.removeAttribute?.(ORIGINAL_POINTS_ATTR);
  });
  const previewStickyLabels = host?.querySelectorAll?.(`[${PREVIEW_STICKY_LABEL_ATTR}='1']`) || [];
  previewStickyLabels.forEach((labelNode) => {
    labelNode.style.transform = labelNode.getAttribute?.(ORIGINAL_STYLE_TRANSFORM_ATTR) || "";
    labelNode.removeAttribute?.(PREVIEW_STICKY_LABEL_ATTR);
    labelNode.removeAttribute?.(ORIGINAL_STYLE_TRANSFORM_ATTR);
  });
  const previewJunctionLines = host?.querySelectorAll?.(`[${PREVIEW_JUNCTION_LINE_ATTR}='1']`) || [];
  previewJunctionLines.forEach((lineNode) => {
    lineNode.setAttribute?.("x1", lineNode.getAttribute?.(ORIGINAL_X1_ATTR) || "0");
    lineNode.setAttribute?.("x2", lineNode.getAttribute?.(ORIGINAL_X2_ATTR) || "0");
    lineNode.removeAttribute?.(PREVIEW_JUNCTION_LINE_ATTR);
    lineNode.removeAttribute?.(ORIGINAL_X1_ATTR);
    lineNode.removeAttribute?.(ORIGINAL_X2_ATTR);
  });
  const previewJunctionLabels = host?.querySelectorAll?.(`[${PREVIEW_JUNCTION_LABEL_ATTR}='1']`) || [];
  previewJunctionLabels.forEach((labelNode) => {
    labelNode.setAttribute?.("x", labelNode.getAttribute?.(ORIGINAL_X_ATTR) || "0");
    labelNode.removeAttribute?.(PREVIEW_JUNCTION_LABEL_ATTR);
    labelNode.removeAttribute?.(ORIGINAL_X_ATTR);
  });
}

function buildTrackPreviewSelector({ trackRole, assemblyCtgId, phasedTrackId = null, phasedTrackItemId = null }) {
  let selector = `[data-track-contig-id="${assemblyCtgId}"][data-track-role="${trackRole}"]`;
  if (String(trackRole || "").trim() === "phased") {
    if (phasedTrackItemId) {
      selector += `[data-track-phased-track-item-id="${phasedTrackItemId}"]`;
    } else if (phasedTrackId) {
      selector += `[data-track-phased-track-id="${phasedTrackId}"]`;
    }
  }
  return selector;
}

function buildTrackBandPreviewSelector({ trackRole, assemblyCtgId, phasedTrackId = null, phasedTrackItemId = null }) {
  let selector = `[data-band-track-role="${trackRole}"][data-band-contig-id="${assemblyCtgId}"]`;
  if (String(trackRole || "").trim() === "phased") {
    if (phasedTrackItemId) {
      selector += `[data-band-phased-track-item-id="${phasedTrackItemId}"]`;
    } else if (phasedTrackId) {
      selector += `[data-band-phased-track-id="${phasedTrackId}"]`;
    }
  }
  return selector;
}

function buildTrackStickyLabelPreviewSelector({ trackRole, assemblyCtgId, isMirror = false, phasedTrackId = null, phasedTrackItemId = null }) {
  const mirrorFlag = isMirror ? "1" : "0";
  let key = `track:${trackRole}:${assemblyCtgId}:${mirrorFlag}`;
  if (String(trackRole || "").trim() === "phased") {
    if (phasedTrackItemId) {
      key += `:item:${phasedTrackItemId}`;
    } else if (phasedTrackId) {
      key += `:track:${phasedTrackId}`;
    }
  }
  return `[data-sticky-label-key="${key}"]`;
}

export function previewTrackContigDrag(host, {
  trackRole,
  assemblyCtgId,
  phasedTrackId = null,
  phasedTrackItemId = null,
  offsetPx,
}) {
  if (!host) {
    return;
  }
  host.classList?.add?.(MAIN_TRACK_PREVIEW_CLASS);
  const groupNodes = host.querySelectorAll?.(
    buildTrackPreviewSelector({ trackRole, assemblyCtgId, phasedTrackId, phasedTrackItemId }),
  ) || [];
  groupNodes.forEach((groupNode) => {
    applyGroupPreview(groupNode, offsetPx);
    const stickyLabelNodes = host.querySelectorAll?.(
      buildTrackStickyLabelPreviewSelector({
        trackRole,
        assemblyCtgId,
        isMirror: groupNode.getAttribute?.("data-track-is-mirror") === "1",
        phasedTrackId,
        phasedTrackItemId,
      }),
    ) || [];
    stickyLabelNodes.forEach((labelNode) => applyStickyLabelPreview(labelNode, offsetPx));
  });
  applyGrtJunctionPreview(host, groupNodes, offsetPx);
  applyGrtDisplayEvidencePreview(host, groupNodes, offsetPx);

  const edgeIndexes = String(trackRole || "").trim() === "support" ? [0, 1] : [2, 3];
  const bandNodes = host.querySelectorAll?.(
    buildTrackBandPreviewSelector({ trackRole, assemblyCtgId, phasedTrackId, phasedTrackItemId }),
  ) || [];
  bandNodes.forEach((bandNode) => applyBandPreview(bandNode, edgeIndexes, offsetPx));
}

export function clearTrackDragPreview(host) {
  clearPreviewNodes(host, MAIN_TRACK_PREVIEW_CLASS);
}

export function previewSubviewTrackContigDrag(
  host,
  { slot, contigId, offsetPx, pointerClientX = null },
) {
  if (!host) {
    return;
  }
  host.classList?.add?.(SUBVIEW_TRACK_PREVIEW_CLASS);
  const groupNodes = host.querySelectorAll?.(
    `[data-subview-track-slot="${slot}"][data-subview-contig-id="${contigId}"]`,
  ) || [];
  groupNodes.forEach((groupNode) => {
    applyGroupPreview(groupNode, offsetPx);
    const trackRole = String(groupNode.getAttribute?.("data-subview-track-role") || "").trim();
    if (!trackRole) {
      return;
    }
    const stickyLabelNodes = host.querySelectorAll?.(
      `[data-sticky-label-key="subview:${slot}:${trackRole}:${contigId}"]`,
    ) || [];
    stickyLabelNodes.forEach((labelNode) => applyStickyLabelPreview(labelNode, offsetPx));
    const labelNodes = host.querySelectorAll?.(
      `[data-subview-label-slot="${slot}"][data-subview-label-role="${trackRole}"][data-subview-label-contig-id="${contigId}"]`,
    ) || [];
    labelNodes.forEach((labelNode) => {
      if (!isLabelInsideGroup(labelNode, groupNode)) {
        applyStickyLabelPreview(labelNode, offsetPx);
      }
    });
  });
  applyGrtJunctionPreview(host, groupNodes, offsetPx);
  applyGrtDisplayEvidencePreview(host, groupNodes, offsetPx);

  const edgeIndexes = String(slot || "").trim() === "top" ? [0, 1] : [2, 3];
  const bandSelector = String(slot || "").trim() === "top"
    ? `[data-subview-top-contig-id="${contigId}"]`
    : `[data-subview-bottom-contig-id="${contigId}"]`;
  const bandNodes = host.querySelectorAll?.(bandSelector) || [];
  bandNodes.forEach((bandNode) => applyBandPreview(bandNode, edgeIndexes, offsetPx));
  return applySubviewPreviewEnvelope(groupNodes, offsetPx, { pointerClientX });
}

export function clearSubviewTrackDragPreview(host) {
  clearPreviewNodes(host, SUBVIEW_TRACK_PREVIEW_CLASS);
}

export function __testShiftPolygonEdge(pointsText, edgeIndexes, offsetPx) {
  return shiftPolygonEdge(pointsText, edgeIndexes, offsetPx);
}
