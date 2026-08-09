import { normalizePositiveInt } from "./track-prefs.js";
import { normalizeSupportDatasetId } from "./selection-state.js";

export function resolveTrackCtgDisplayName(ctg, fallbackId) {
  const resolvedName = String(ctg?.name || "").trim();
  if (resolvedName) {
    return resolvedName;
  }
  const contigId = normalizeSupportDatasetId(fallbackId ?? ctg?.assemblyCtgId);
  return contigId ? `Ctg${contigId}` : "";
}

function stripTrackCtgAssignmentSuffix(name) {
  const text = String(name || "").trim();
  const atIndex = text.lastIndexOf("@");
  if (atIndex <= 0 || atIndex >= text.length - 1) {
    return text;
  }
  const suffix = text.slice(atIndex + 1);
  if (!suffix || /\s/.test(suffix)) {
    return text;
  }
  return text.slice(0, atIndex);
}

export function resolveTrackCtgVisibleName(ctg, fallbackId) {
  return stripTrackCtgAssignmentSuffix(resolveTrackCtgDisplayName(ctg, fallbackId));
}

export function resolveTrackCtgOrient(ctg) {
  const orient = String((ctg?.orient ?? ctg?.refOrient ?? ctg?.ref_orient) || "").trim();
  return orient === "-" ? "-" : "+";
}

export function resolveTrackCtgLabelText(ctg, fallbackId) {
  const displayName = resolveTrackCtgVisibleName(ctg, fallbackId);
  if (!displayName) {
    return "";
  }
  return `${displayName} (${resolveTrackCtgOrient(ctg)})`;
}

export function buildTrackCtgHoverTitle(ctgName, { startBp = 0, lengthBp = 0 } = {}) {
  return `${String(ctgName || "").trim()} | start=${normalizePositiveInt(startBp) || 0} | len=${normalizePositiveInt(lengthBp) || 0}`;
}

function resolveTrackCtgLabelPlacement({
  ctgName,
  role,
  rect,
  barY,
  barHeight,
  inlineTextOffsetY,
  outsideLabelAnchor = "trailing-edge",
  hideOutsideLabel = false,
}) {
  const inlineX = Number(rect?.x || 0) + 4;
  const inlineY = Number(barY || 0) + Number(inlineTextOffsetY || 0);
  const estimatedLabelWidth = estimateTrackCtgLabelWidth(ctgName);
  const fitsInsideBar = Number(rect?.width || 0) >= estimatedLabelWidth + 8;
  if (fitsInsideBar) {
    return {
      x: inlineX,
      y: inlineY,
      classSuffix: "",
      transformAttr: "",
      textAnchor: "start",
      tiltAngleDeg: 0,
    };
  }

  if (hideOutsideLabel) {
    return {
      x: inlineX,
      y: inlineY,
      classSuffix: " is-hidden-label",
      transformAttr: "",
      textAnchor: "start",
      tiltAngleDeg: 0,
      hidden: true,
    };
  }

  const isCompanion = String(role || "") === "support";
  const outsideX = outsideLabelAnchor === "bar-middle"
    ? Number.isFinite(Number(rect?.centerX))
      ? Number(rect.centerX)
      : Number(rect?.x || 0) + Number(rect?.width || 0) / 2
    : Number(rect?.x || 0) + Number(rect?.width || 0) + 2;
  const outsideY = isCompanion
    ? Number(barY || 0) - 2
    : Number(barY || 0) + Number(barHeight || 0) + 10;
  const angle = isCompanion ? -25 : 25;
  return {
    x: outsideX,
    y: outsideY,
    classSuffix: isCompanion ? " is-outside is-tilt-up" : " is-outside is-tilt-down",
    transformAttr: buildTrackCtgLabelTransformAttr({
      tiltAngleDeg: angle,
      x: outsideX,
      y: outsideY,
    }),
    textAnchor: "start",
    tiltAngleDeg: angle,
  };
}

function buildTrackCtgLabelTransformAttr({
  tiltAngleDeg = 0,
  x,
  y,
}) {
  const angle = Number(tiltAngleDeg) || 0;
  if (!angle) {
    return "";
  }
  return ` transform="rotate(${angle} ${Number(x).toFixed(2)} ${Number(y).toFixed(2)})"`;
}

export function resolveBoundedTrackCtgLabelPlacement({
  minVisibleX = -Infinity,
  maxVisibleX = Infinity,
  ...args
}) {
  const placement = resolveTrackCtgLabelPlacement(args);
  if (!placement) {
    return placement;
  }
  const resolvedMinX = Number.isFinite(minVisibleX) ? Number(minVisibleX) : -Infinity;
  const resolvedMaxX = Number.isFinite(maxVisibleX) ? Number(maxVisibleX) : Infinity;
  if (!(resolvedMinX < resolvedMaxX)) {
    return placement;
  }
  const bounds = resolveTrackCtgLabelBounds({
    x: placement.x,
    labelText: args.ctgName,
    tiltAngleDeg: placement.tiltAngleDeg,
    textAnchor: placement.textAnchor,
  });
  let shiftX = 0;
  if (bounds.left < resolvedMinX) {
    shiftX += resolvedMinX - bounds.left;
  }
  if (bounds.right + shiftX > resolvedMaxX) {
    shiftX += resolvedMaxX - (bounds.right + shiftX);
  }
  if (Math.abs(shiftX) < 0.01) {
    return placement;
  }
  const nextX = Number(placement.x) + shiftX;
  return {
    ...placement,
    x: nextX,
    transformAttr: buildTrackCtgLabelTransformAttr({
      tiltAngleDeg: placement.tiltAngleDeg,
      x: nextX,
      y: placement.y,
    }),
  };
}

function estimateTrackCtgLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(10, text.length * 6.2);
}

export function resolveTrackCtgLabelRightBoundary({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackCtgLabelWidth(labelText);
  const projectedWidth = width * Math.cos((Math.abs(Number(tiltAngleDeg) || 0) * Math.PI) / 180);
  if (textAnchor === "end") {
    return baseX;
  }
  if (textAnchor === "middle") {
    return baseX + projectedWidth / 2;
  }
  return baseX + projectedWidth;
}

export function resolveTrackCtgLabelLeftBoundary({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  const baseX = Number(x) || 0;
  const width = estimateTrackCtgLabelWidth(labelText);
  const projectedWidth = width * Math.cos((Math.abs(Number(tiltAngleDeg) || 0) * Math.PI) / 180);
  if (textAnchor === "end") {
    return baseX - projectedWidth;
  }
  if (textAnchor === "middle") {
    return baseX - projectedWidth / 2;
  }
  return baseX;
}

function resolveTrackCtgLabelBounds({
  x,
  labelText,
  tiltAngleDeg = 0,
  textAnchor = "start",
}) {
  return {
    left: resolveTrackCtgLabelLeftBoundary({
      x,
      labelText,
      tiltAngleDeg,
      textAnchor,
    }),
    right: resolveTrackCtgLabelRightBoundary({
      x,
      labelText,
      tiltAngleDeg,
      textAnchor,
    }),
  };
}
