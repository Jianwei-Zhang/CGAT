import { resolveAlignmentBandStyle, resolveDarkAlignmentBandStyle } from "./alignment-band-style.js";
import { formatSubviewBandTooltipText } from "./subview-band-tooltip.js";

export const DENSE_SUBVIEW_BAND_THRESHOLD = 1000;
export const DENSE_ANCHOR_SCENE_ATTR = "data-subview-dense-anchor-scene";
export const DENSE_HIT_SURFACE_ATTR = "data-subview-dense-hit-surface";

const ANCHOR_FIELDS = [
  "hitKey", "edge", "topX", "bottomX", "hitTopY", "hitBottomY",
  "topContigId", "bottomContigId", "topCutBp", "bottomCutBp",
  "topEndpointKey", "bottomEndpointKey", "topLengthBp", "bottomLengthBp",
  "topName", "bottomName", "topSourceLabel", "bottomSourceLabel",
  "topSourceRole", "bottomSourceRole", "topSourceKind", "bottomSourceKind",
  "topSourceName", "bottomSourceName",
];
const ANCHOR_DYNAMIC_ATTRIBUTES = [
  "data-subview-anchor-kind", "data-subview-anchor-hit-key", "data-subview-anchor-edge",
  "data-subview-anchor-active", "data-subview-manual-anchor-id",
  "data-subview-anchor-top-endpoint-key", "data-subview-anchor-bottom-endpoint-key",
  "data-subview-anchor-top-contig-id", "data-subview-anchor-bottom-contig-id",
  "data-subview-anchor-top-cut-bp", "data-subview-anchor-bottom-cut-bp",
  "data-subview-anchor-top-length-bp", "data-subview-anchor-bottom-length-bp",
  "data-subview-anchor-top-name", "data-subview-anchor-bottom-name",
  "data-subview-anchor-top-source-label", "data-subview-anchor-bottom-source-label",
  "data-subview-anchor-top-source-role", "data-subview-anchor-bottom-source-role",
  "data-subview-anchor-top-source-kind", "data-subview-anchor-bottom-source-kind",
  "data-subview-anchor-top-source-name", "data-subview-anchor-bottom-source-name",
  "data-subview-anchor-top-x", "data-subview-anchor-bottom-x",
];
const BAND_DYNAMIC_ATTRIBUTES = [
  "data-subview-hit-key", "data-subview-hit-left-active", "data-subview-hit-right-active",
  "data-subview-band-tooltip",
];
const BOUND = Symbol("subviewDenseHitBound");
const BOUND_DOCUMENTS = new WeakSet();
const ANCHOR_CACHE = new WeakMap();
const BAND_CACHE = new WeakMap();
const LAST_POINT_CACHE = new WeakMap();

export function renderSubviewDenseAnchorScene(edges) {
  const records = (Array.isArray(edges) ? edges : []).map((edge) =>
    ANCHOR_FIELDS.map((field) => edge?.[field] ?? null));
  const json = JSON.stringify(records).replaceAll("<", "\\u003c");
  return `<script type="application/json" ${DENSE_ANCHOR_SCENE_ATTR}="1">${json}</script>`;
}

function decodeAnchorRecord(values) {
  const record = {};
  ANCHOR_FIELDS.forEach((field, index) => { record[field] = values?.[index] ?? null; });
  return record;
}

export function readDenseAnchorScene(host) {
  const node = host?.querySelector?.(`[${DENSE_ANCHOR_SCENE_ATTR}="1"]`);
  if (!node) return [];
  const cached = ANCHOR_CACHE.get(node);
  if (cached) return cached.records;
  const text = String(node.textContent || "").trim();
  let records = [];
  try {
    const parsed = JSON.parse(text || "[]");
    if (Array.isArray(parsed)) records = parsed.map(decodeAnchorRecord);
  } catch {
    // Keep the rendered active/manual anchors if a damaged sidecar cannot parse.
  }
  ANCHOR_CACHE.set(node, { records });
  return records;
}

export function readDenseBandScene(scroll) {
  const node = scroll?.querySelector?.("[data-track-band-canvas-scene]");
  if (!node) return null;
  const cached = BAND_CACHE.get(node);
  if (cached) return cached.scene;
  const text = String(node.textContent || "").trim();
  let scene = null;
  try { scene = JSON.parse(text || "null"); } catch { scene = null; }
  BAND_CACHE.set(node, { scene });
  return scene;
}

export function readDenseBandRecords(scroll) {
  const scene = readDenseBandScene(scroll);
  return Array.isArray(scene?.bands) ? scene.bands : [];
}

function pointInPolygon(x, y, points) {
  let inside = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i++) {
    const [xi, yi] = points[i], [xj, yj] = points[j];
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

function distanceToSegment(x, y, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  if (!dx && !dy) return Math.hypot(x - x1, y - y1);
  const t = Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(x - (x1 + t * dx), y - (y1 + t * dy));
}

function eventPoint(surface, point) {
  const svg = surface?.ownerSVGElement;
  const clientX = Number(point?.clientX), clientY = Number(point?.clientY);
  const matrix = svg?.getScreenCTM?.();
  if (!svg || !matrix || !Number.isFinite(clientX) || !Number.isFinite(clientY)) return null;
  try {
    const inverse = matrix.inverse();
    const local = typeof DOMPoint === "function"
      ? new DOMPoint(clientX, clientY).matrixTransform(inverse)
      : (() => { const p = svg.createSVGPoint(); p.x = clientX; p.y = clientY; return p.matrixTransform(inverse); })();
    const scaleX = Math.hypot(matrix.a, matrix.b), scaleY = Math.hypot(matrix.c, matrix.d);
    return { x: local.x, y: local.y, tolerance: 4 / Math.max(0.01, Math.min(scaleX, scaleY)) };
  } catch {
    return null;
  }
}

export function resolveSubviewDenseHit(surface, point) {
  if (!surface || typeof surface.closest !== "function") return null;
  const scroll = surface.closest(".subview-track-scroll");
  const local = eventPoint(surface, point);
  if (!scroll || !local) return null;
  const cacheKey = `${local.x},${local.y},${scroll.scrollLeft},${surface.ownerSVGElement?.getAttribute("viewBox")}`;
  const cached = LAST_POINT_CACHE.get(surface);
  if (cached?.key === cacheKey) return cached.hit;
  let best = null, bestDistance = Infinity;
  for (const record of readDenseAnchorScene(scroll)) {
    const topY = Number(record.hitTopY ?? record.topY), bottomY = Number(record.hitBottomY ?? record.bottomY);
    if (![record.topX, topY, record.bottomX, bottomY].every(Number.isFinite)) continue;
    const distance = distanceToSegment(local.x, local.y, Number(record.topX), topY,
      Number(record.bottomX), bottomY);
    if (distance <= local.tolerance && distance <= bestDistance) {
      best = { kind: "anchor", record }; bestDistance = distance;
    }
  }
  if (!best) {
    const bands = readDenseBandRecords(scroll);
    for (let index = bands.length - 1; index >= 0; index--) {
      const band = bands[index];
      if (Array.isArray(band?.points) && band.points.length >= 3
        && pointInPolygon(local.x, local.y, band.points)) {
        best = { kind: "band", record: band, index };
        break;
      }
    }
  }
  LAST_POINT_CACHE.set(surface, { key: cacheKey, hit: best });
  return best;
}

function setAttributes(node, entries) {
  for (const [name, value] of entries) node.setAttribute(name, value === null || value === undefined ? "" : String(value));
}

function clearDynamicHit(surface) {
  if (!surface) return;
  for (const name of [...ANCHOR_DYNAMIC_ATTRIBUTES, ...BAND_DYNAMIC_ATTRIBUTES, "data-subview-dense-hit-kind"]) {
    surface.removeAttribute(name);
  }
  surface.style?.removeProperty?.("--alignment-band-fill");
  surface.style?.removeProperty?.("--alignment-band-stroke");
  surface.style?.setProperty?.("cursor", "default");
  const proxy = surface.ownerSVGElement?.querySelector?.('[data-subview-dense-hover-proxy="1"]');
  if (proxy) { proxy.setAttribute("points", ""); proxy.style.display = "none"; }
}

function paintBandProxy(surface, record) {
  const svg = surface.ownerSVGElement;
  if (!svg) return;
  let proxy = svg.querySelector('[data-subview-dense-hover-proxy="1"]');
  if (!proxy) {
    proxy = svg.ownerDocument.createElementNS("http://www.w3.org/2000/svg", "polygon");
    proxy.setAttribute("class", "subview-dense-hover-proxy");
    proxy.setAttribute("data-subview-dense-hover-proxy", "1");
    proxy.setAttribute("aria-hidden", "true");
    proxy.setAttribute("pointer-events", "none");
    svg.append(proxy);
  }
  const dark = svg.ownerDocument.documentElement?.dataset?.theme === "dark";
  const style = (dark ? resolveDarkAlignmentBandStyle : resolveAlignmentBandStyle)(record?.tone, record?.identityPct);
  proxy.setAttribute("class", `subview-dense-hover-proxy${record?.tone === "companion" ? " is-companion" : ""}`);
  proxy.setAttribute("points", Array.isArray(record?.points)
    ? record.points.map((point) => `${point[0]},${point[1]}`).join(" ") : "");
  proxy.setAttribute("fill", "none");
  proxy.setAttribute("stroke", style.stroke);
  proxy.setAttribute("stroke-width", "2");
  proxy.style.display = "";
}

function presentHit(surface, hit) {
  if (!surface) return;
  if (!hit) { clearDynamicHit(surface); return; }
  if (hit.kind === "anchor") {
    const record = hit.record || {};
    for (const name of BAND_DYNAMIC_ATTRIBUTES) surface.removeAttribute(name);
    setAttributes(surface, [
      ["data-subview-dense-hit-kind", "anchor"],
      ["data-subview-anchor-kind", "evidence"],
      ["data-subview-anchor-hit-key", record.hitKey],
      ["data-subview-anchor-edge", record.edge],
      ["data-subview-anchor-active", "0"],
      ["data-subview-manual-anchor-id", ""],
      ["data-subview-anchor-top-endpoint-key", record.topEndpointKey],
      ["data-subview-anchor-bottom-endpoint-key", record.bottomEndpointKey],
      ["data-subview-anchor-top-contig-id", record.topContigId ?? 0],
      ["data-subview-anchor-bottom-contig-id", record.bottomContigId ?? 0],
      ["data-subview-anchor-top-cut-bp", record.topCutBp ?? 0],
      ["data-subview-anchor-bottom-cut-bp", record.bottomCutBp ?? 0],
      ["data-subview-anchor-top-length-bp", record.topLengthBp ?? 0],
      ["data-subview-anchor-bottom-length-bp", record.bottomLengthBp ?? 0],
      ["data-subview-anchor-top-name", record.topName],
      ["data-subview-anchor-bottom-name", record.bottomName],
      ["data-subview-anchor-top-source-label", record.topSourceLabel],
      ["data-subview-anchor-bottom-source-label", record.bottomSourceLabel],
      ["data-subview-anchor-top-source-role", record.topSourceRole],
      ["data-subview-anchor-bottom-source-role", record.bottomSourceRole],
      ["data-subview-anchor-top-source-kind", record.topSourceKind],
      ["data-subview-anchor-bottom-source-kind", record.bottomSourceKind],
      ["data-subview-anchor-top-source-name", record.topSourceName],
      ["data-subview-anchor-bottom-source-name", record.bottomSourceName],
      ["data-subview-anchor-top-x", record.topX ?? 0],
      ["data-subview-anchor-bottom-x", record.bottomX ?? 0],
    ]);
    surface.style?.setProperty?.("cursor", "crosshair");
    const proxy = surface.ownerSVGElement?.querySelector?.('[data-subview-dense-hover-proxy="1"]');
    if (proxy) { proxy.setAttribute("points", ""); proxy.style.display = "none"; }
    return;
  }
  const record = hit.record || {};
  for (const name of ANCHOR_DYNAMIC_ATTRIBUTES) surface.removeAttribute(name);
  setAttributes(surface, [
    ["data-subview-dense-hit-kind", "band"],
    ["data-subview-hit-key", record.hitKey],
    ["data-subview-hit-left-active", record.leftActive ? "1" : "0"],
    ["data-subview-hit-right-active", record.rightActive ? "1" : "0"],
    ["data-subview-band-tooltip", formatSubviewBandTooltipText(record.tooltip)],
  ]);
  const dark = surface.ownerDocument.documentElement?.dataset?.theme === "dark";
  const style = (dark ? resolveDarkAlignmentBandStyle : resolveAlignmentBandStyle)(record.tone, record.identityPct);
  surface.style?.setProperty?.("--alignment-band-fill", style.fill);
  surface.style?.setProperty?.("--alignment-band-stroke", style.stroke);
  surface.style?.setProperty?.("cursor", "default");
  paintBandProxy(surface, record);
}

export function bindSubviewDenseHitRuntime(host) {
  const surfaces = [...(host?.querySelectorAll?.(`[${DENSE_HIT_SURFACE_ATTR}="1"]`) || [])];
  if (!surfaces.length) return;
  for (const surface of surfaces) surface[BOUND] = true;
  const document = surfaces[0].ownerDocument;
  if (!document || BOUND_DOCUMENTS.has(document)) return;
  const win = document?.defaultView;
  if (!win?.addEventListener) return;
  BOUND_DOCUMENTS.add(document);
  let activeSurface = null;
  const update = (event, allowPressed = false) => {
    const next = event.target?.closest?.(`[${DENSE_HIT_SURFACE_ATTR}="1"]`) || null;
    if (!next) {
      if (activeSurface) { clearDynamicHit(activeSurface); activeSurface = null; }
      return;
    }
    activeSurface = next;
    if ((!allowPressed && Number(event.buttons || 0) !== 0)
      || next.closest?.(".is-subview-track-drag-preview")) {
      clearDynamicHit(next); return;
    }
    presentHit(next, resolveSubviewDenseHit(next, event));
  };
  // Window capture runs before the document-level tooltip listener, so its
  // target attributes and payload are current for the same pointer event.
  win.addEventListener("pointerover", update, true);
  win.addEventListener("pointermove", update, true);
  win.addEventListener("pointerdown", (event) => update(event, true), true);
  win.addEventListener("pointerout", (event) => {
    if (activeSurface && !activeSurface.contains?.(event.relatedTarget)
      && !event.relatedTarget?.closest?.(`[${DENSE_HIT_SURFACE_ATTR}="1"]`)) {
      clearDynamicHit(activeSurface); activeSurface = null;
    }
  }, true);
}
