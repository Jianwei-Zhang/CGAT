const MAIN_TRACK_PREVIEW_CLASS = "is-track-drag-preview";
const SUBVIEW_TRACK_PREVIEW_CLASS = "is-subview-track-drag-preview";
const ORIGINAL_POINTS_ATTR = "data-drag-preview-original-points";
const ORIGINAL_TRANSFORM_ATTR = "data-drag-preview-original-transform";
const ORIGINAL_STYLE_TRANSFORM_ATTR = "data-drag-preview-original-style-transform";
const PREVIEW_GROUP_ATTR = "data-drag-preview-group";
const PREVIEW_BAND_ATTR = "data-drag-preview-band";
const PREVIEW_STICKY_LABEL_ATTR = "data-drag-preview-sticky-label";

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

function isLabelInsideGroup(labelNode, groupNode) {
  if (!labelNode || !groupNode || typeof groupNode.contains !== "function") {
    return false;
  }
  return groupNode.contains(labelNode);
}

function clearPreviewNodes(host, previewClassName) {
  host?.classList?.remove?.(previewClassName);
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

  const edgeIndexes = String(trackRole || "").trim() === "support" ? [0, 1] : [2, 3];
  const bandNodes = host.querySelectorAll?.(
    buildTrackBandPreviewSelector({ trackRole, assemblyCtgId, phasedTrackId, phasedTrackItemId }),
  ) || [];
  bandNodes.forEach((bandNode) => applyBandPreview(bandNode, edgeIndexes, offsetPx));
}

export function clearTrackDragPreview(host) {
  clearPreviewNodes(host, MAIN_TRACK_PREVIEW_CLASS);
}

export function previewSubviewTrackContigDrag(host, { slot, contigId, offsetPx }) {
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

  const edgeIndexes = String(slot || "").trim() === "top" ? [0, 1] : [2, 3];
  const bandSelector = String(slot || "").trim() === "top"
    ? `[data-subview-top-contig-id="${contigId}"]`
    : `[data-subview-bottom-contig-id="${contigId}"]`;
  const bandNodes = host.querySelectorAll?.(bandSelector) || [];
  bandNodes.forEach((bandNode) => applyBandPreview(bandNode, edgeIndexes, offsetPx));
}

export function clearSubviewTrackDragPreview(host) {
  clearPreviewNodes(host, SUBVIEW_TRACK_PREVIEW_CLASS);
}

export function __testShiftPolygonEdge(pointsText, edgeIndexes, offsetPx) {
  return shiftPolygonEdge(pointsText, edgeIndexes, offsetPx);
}
