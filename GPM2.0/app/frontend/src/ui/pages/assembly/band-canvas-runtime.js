import {
  resolveAlignmentBandStyle,
  resolveDarkAlignmentBandStyle,
  sortAlignmentBands,
} from "./alignment-band-style.js";

const TRACK_BAND_CANVAS_BOUND = Symbol("trackBandCanvasBound");
const TRACK_BAND_CANVAS_READY_CLASS = "is-track-band-canvas-ready";
const MAX_CANVAS_BITMAP_DIMENSION = 32767;
const MAX_CANVAS_BITMAP_AREA = 67_108_864;

function resolveAnimationFrameApi() {
  const request = typeof globalThis.requestAnimationFrame === "function"
    ? globalThis.requestAnimationFrame.bind(globalThis)
    : (callback) => globalThis.setTimeout(() => callback(Date.now()), 16);
  const cancel = typeof globalThis.cancelAnimationFrame === "function"
    ? globalThis.cancelAnimationFrame.bind(globalThis)
    : (handle) => globalThis.clearTimeout(handle);
  return { request, cancel };
}

function readTrackBandCanvasScene(layer) {
  const sceneNode = layer?.querySelector?.("[data-track-band-canvas-scene]");
  if (!sceneNode) {
    return null;
  }
  try {
    return JSON.parse(String(sceneNode.textContent || "").trim() || "null");
  } catch {
    return null;
  }
}

function canAllocateCanvasBitmap(width, height, dpr) {
  const bitmapWidth = Math.max(1, Math.round(Math.max(1, Number(width) || 0) * dpr));
  const bitmapHeight = Math.max(1, Math.round(Math.max(1, Number(height) || 0) * dpr));
  if (!Number.isFinite(bitmapWidth) || !Number.isFinite(bitmapHeight)) {
    return false;
  }
  if (bitmapWidth > MAX_CANVAS_BITMAP_DIMENSION || bitmapHeight > MAX_CANVAS_BITMAP_DIMENSION) {
    return false;
  }
  return bitmapWidth * bitmapHeight <= MAX_CANVAS_BITMAP_AREA;
}

function disableCanvas(canvas) {
  if (!canvas) {
    return;
  }
  canvas.width = 1;
  canvas.height = 1;
  if (canvas.style) { canvas.style.width = "0px"; canvas.style.height = "0px"; }
}

function configureCanvas(canvas, width, height, dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1))) {
  const safeWidth = Math.max(1, Math.round(Number(width) || 0));
  const safeHeight = Math.max(1, Math.round(Number(height) || 0));
  if (!canAllocateCanvasBitmap(safeWidth, safeHeight, dpr)) {
    disableCanvas(canvas);
    return null;
  }
  canvas.width = Math.max(1, Math.round(safeWidth * dpr));
  canvas.height = Math.max(1, Math.round(safeHeight * dpr));
  if (canvas.style) { canvas.style.width = `${safeWidth}px`; canvas.style.height = `${safeHeight}px`; }
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, safeWidth, safeHeight);
  context.lineWidth = 1;
  context.lineJoin = "round";
  return {
    context,
    width: safeWidth,
    height: safeHeight,
  };
}

function drawPolygon(context, points, offsetX, styles) {
  if (!Array.isArray(points) || points.length < 3) {
    return;
  }
  context.beginPath();
  points.forEach(([x, y], index) => {
    const px = Number(x || 0) - offsetX;
    const py = Number(y || 0);
    if (index === 0) {
      context.moveTo(px, py);
    } else {
      context.lineTo(px, py);
    }
  });
  context.closePath();
  context.fillStyle = styles.fill;
  context.strokeStyle = styles.stroke;
  context.fill();
  context.stroke();
}

export function paintBandCanvasScene(canvas, scene, { theme = "light", dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1)) } = {}) {
  if (!canvas || !scene) return false;
  const viewportLeft = Number(scene.viewBoxMinX || 0);
  let offsetX = viewportLeft, paintWidth = Number(scene.width);
  // Keep a bounded gutter in the already-painted backing bitmap. Minimum-pixel
  // bands can protrude past a full-range viewport even when their bp endpoints
  // fit; clipping them here would force another complete raster on pointerdown.
  let minX = viewportLeft, maxX = viewportLeft + paintWidth;
  for (const band of scene.bands || []) for (const point of band.points || []) {
    if (!Number.isFinite(point[0])) continue;
    minX = Math.min(minX, point[0]); maxX = Math.max(maxX, point[0]);
  }
  const paddedLeft = Math.floor(minX) - 2, paddedWidth = Math.ceil(maxX) + 2 - paddedLeft;
  if (paddedWidth <= Math.max(paintWidth * 1.25, paintWidth + 16)
    && canAllocateCanvasBitmap(paddedWidth, scene.height, dpr)) {
    offsetX = paddedLeft; paintWidth = paddedWidth;
  }
  const configured = configureCanvas(canvas, paintWidth, scene.height, dpr);
  if (!configured) return false;
  const { context, width, height } = configured;

  if (scene?.clipRect) {
    context.save();
    context.beginPath();
    context.rect(
      Number(scene.clipRect.x || 0) - offsetX,
      Number(scene.clipRect.y || 0),
      Number(scene.clipRect.width || width),
      Number(scene.clipRect.height || height),
    );
    context.clip();
  }

  const dark = theme === "dark";
  const resolveBandStyle = dark ? resolveDarkAlignmentBandStyle : resolveAlignmentBandStyle;
  sortAlignmentBands(Array.isArray(scene.bands) ? scene.bands : []).forEach((band) => {
    drawPolygon(
      context,
      band?.points,
      offsetX,
      resolveBandStyle(band?.tone, band?.identityPct),
    );
  });

  if (scene?.clipRect) {
    context.restore();
  }
  return { canvas, left: offsetX, top: 0, width, height };
}

function drawTrackBandCanvasLayer(layer, scene) {
  const canvas = layer?.querySelector?.("[data-track-band-canvas='1']");
  const theme = layer?.ownerDocument?.documentElement?.dataset?.theme
    ?? globalThis.document?.documentElement?.dataset?.theme ?? "light";
  const painted = paintBandCanvasScene(canvas, scene, { theme });
  if (painted) {
    layer.style.overflow = "hidden";
    canvas.style.transform = `translateX(${painted.left - Number(scene.viewBoxMinX || 0)}px)`;
  }
  return painted;
}

// A Worker-prepared bitmap is adopted only for the exact scene/theme/DPR.
// All SVG hit targets remain authoritative and are hydrated separately.
export function adoptBandCanvasRaster(layer, raster) {
  const canvas = layer?.querySelector?.("[data-track-band-canvas='1']");
  const sceneText = String(layer?.querySelector?.("[data-track-band-canvas-scene]")?.textContent || "");
  const theme = layer?.ownerDocument?.documentElement?.dataset?.theme
    ?? globalThis.document?.documentElement?.dataset?.theme ?? "light";
  const dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1));
  if (!canvas || !raster?.bitmap || raster.sceneText !== sceneText || raster.theme !== theme || raster.dpr !== dpr) return false;
  if (!canAllocateCanvasBitmap(raster.width, raster.height, dpr)
    || raster.bitmap.width !== Math.round(raster.width * dpr)
    || raster.bitmap.height !== Math.round(raster.height * dpr)) return false;
  canvas.width = raster.bitmap.width; canvas.height = raster.bitmap.height;
  canvas.style.width = `${raster.width}px`; canvas.style.height = `${raster.height}px`;
  const context = canvas.getContext("2d");
  if (!context) return false;
  context.drawImage(raster.bitmap, 0, 0);
  canvas.style.transform = `translateX(${raster.left - Number(raster.scene.viewBoxMinX || 0)}px)`;
  layer.style.overflow = "hidden";
  layer[TRACK_BAND_CANVAS_BOUND] = { sceneText, theme, dpr, frameHandle: undefined,
    paintedScene: raster.scene, paintedCanvas: canvas,
    paintedBounds: { canvas, left: raster.left, top: 0, width: raster.width, height: raster.height } };
  layer.closest?.(".assembly-track-scroll")?.classList.add(TRACK_BAND_CANVAS_READY_CLASS);
  return true;
}

export function bindBandCanvasRuntime(host, { synchronous = false } = {}) {
  const { request, cancel } = resolveAnimationFrameApi();
  const layers = host?.querySelectorAll?.("[data-track-band-canvas-layer='1']") || [];
  layers.forEach((layer) => {
    if (!layer) {
      return;
    }
    const sceneNode = layer.querySelector?.("[data-track-band-canvas-scene]");
    const sceneText = String(sceneNode?.textContent || "");
    const activeTheme = layer?.ownerDocument?.documentElement?.dataset?.theme
      ?? globalThis.document?.documentElement?.dataset?.theme ?? "light";
    const dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1));
    const previous = layer[TRACK_BAND_CANVAS_BOUND] || null;
    if (previous?.sceneText === sceneText && (previous?.theme || "light") === activeTheme
      && previous.dpr === dpr && !(synchronous && previous.frameHandle !== undefined)) {
      return;
    }
    if (previous?.frameHandle !== undefined) {
      cancel(previous.frameHandle);
    }
    const trackScroll = layer.closest?.(".assembly-track-scroll") || layer.parentElement || null;
    trackScroll?.classList?.remove?.(TRACK_BAND_CANVAS_READY_CLASS);
    const scene = readTrackBandCanvasScene(layer);
    const draw = () => {
      let drew = false;
      try { drew = drawTrackBandCanvasLayer(layer, scene); } catch { /* Keep the complete SVG fallback. */ }
      if (drew) {
        trackScroll?.classList?.add?.(TRACK_BAND_CANVAS_READY_CLASS);
      } else {
        trackScroll?.classList?.remove?.(TRACK_BAND_CANVAS_READY_CLASS);
      }
      const nextState = layer[TRACK_BAND_CANVAS_BOUND];
      if (nextState) {
        layer[TRACK_BAND_CANVAS_BOUND] = {
          ...nextState,
          frameHandle: undefined,
          paintedBounds: drew || null,
          paintedScene: drew ? scene : null,
          paintedCanvas: drew ? layer.querySelector("[data-track-band-canvas='1']") : null,
        };
      }
    };
    layer[TRACK_BAND_CANVAS_BOUND] = { sceneText, theme: activeTheme, dpr };
    if (synchronous) draw();
    else {
      const pending = layer[TRACK_BAND_CANVAS_BOUND];
      const frameHandle = request(draw);
      if (layer[TRACK_BAND_CANVAS_BOUND] === pending) pending.frameHandle = frameHandle;
    }
  });
}

// Consecutive runs preserve global paint order even when moving and stationary
// bands interleave. Only parallel endpoint rows with rigid per-edge movement can
// share an affine bitmap; anything else retains the complete redraw fallback.
export function compileBandDragBitmapRuns(bands, maxRuns = 16) {
  const runs = [];
  for (const band of bands) {
    const [a, b, c, d] = band.points;
    const [ma, mb, mc, md] = band.moving;
    if (a[1] !== b[1] || c[1] !== d[1] || a[1] === c[1] || ma !== mb || mc !== md) return null;
    const slope = (mc - ma) / (c[1] - a[1]);
    const intercept = ma - slope * a[1];
    let run = runs.at(-1);
    if (!run || run.slope !== slope || run.intercept !== intercept) {
      if (runs.length >= maxRuns) return null;
      run = { slope, intercept, bands: [], minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
      runs.push(run);
    }
    run.bands.push(band);
    for (const [x, y] of band.points) {
      run.minX = Math.min(run.minX, x); run.maxX = Math.max(run.maxX, x);
      run.minY = Math.min(run.minY, y); run.maxY = Math.max(run.maxY, y);
    }
  }
  return runs;
}

// Reuse only a fully painted same-theme scene covering every original vertex
// and the exact ordered records. Release still renders the authoritative scene.
function readReusableBandBitmap(scroll, bands) {
  const layer = scroll.querySelector?.("[data-track-band-canvas-layer='1']");
  const bound = layer?.[TRACK_BAND_CANVAS_BOUND];
  const scene = bound?.paintedScene, canvas = bound?.paintedCanvas;
  const theme = scroll.ownerDocument?.documentElement?.dataset?.theme || "light";
  if (!scene || !canvas || bound.frameHandle !== undefined || bound.theme !== theme
    || bound.dpr !== Math.max(1, Number(globalThis.devicePixelRatio || 1))
    || bound.sceneText !== String(layer.querySelector?.("[data-track-band-canvas-scene]")?.textContent || "")
    || canvas !== layer.querySelector?.("[data-track-band-canvas='1']")
    || scene.bands?.length !== bands.length) return null;
  const { left, width, height } = bound.paintedBounds || {};
  if (!(width > 0 && height > 0) || canvas.width !== Math.round(width * bound.dpr)
    || canvas.height !== Math.round(height * bound.dpr)) return null;
  const clip = scene.clipRect;
  for (let i = 0; i < bands.length; i++) {
    const band = bands[i], original = scene.bands[i];
    if (band.hitKey !== String(original.hitKey || "") || band.identityPct !== original.identityPct
      || band.tone !== original.tone || original.points?.length !== 4) return null;
    for (let j = 0; j < 4; j++) {
      const [x,y] = band.points[j];
      if (Math.abs(original.points[j][0]-x) > 0.000001 || Math.abs(original.points[j][1]-y) > 0.000001
        || x < left || x > left+width || y < 0 || y > height
        || (clip && (x < clip.x || x > clip.x+clip.width || y < clip.y || y > clip.y+clip.height))) return null;
    }
  }
  return { canvas, left, top: 0, width, height };
}

function createBandDragBitmapPreview(document, scroll, bands, nodes, { width, height, clipY, clipHeight }) {
  const runs = compileBandDragBitmapRuns(bands);
  if (!runs?.length) return null;
  const layer = document.createElement("div");
  if (!layer?.appendChild) return null;
  const dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1));
  const reusable = runs.length === 1 ? readReusableBandBitmap(scroll, bands) : null;
  let area = 0;
  for (const run of runs) {
    run.left = Math.floor(run.minX) - 2; run.top = Math.floor(run.minY) - 2;
    run.width = Math.ceil(run.maxX) + 2 - run.left;
    run.height = Math.ceil(run.maxY) + 2 - run.top;
    if (reusable) Object.assign(run, { left: reusable.left, top: reusable.top, width: reusable.width, height: reusable.height });
    area += Math.ceil(run.width * dpr) * Math.ceil(run.height * dpr);
    if (!canAllocateCanvasBitmap(run.width, run.height, dpr) || area > MAX_CANVAS_BITMAP_AREA) return null;
  }
  layer.className = "track-band-canvas-layer subview-band-drag-canvas";
  layer.setAttribute("aria-hidden", "true");
  layer.setAttribute("data-subview-band-drag-canvas", "1");
  layer.setAttribute("data-subview-band-drag-mode", "bitmap-transform");
  Object.assign(layer.style, { width: `${width}px`, height: `${height}px`, overflow: "hidden", pointerEvents: "none" });
  for (const run of runs) {
    const canvas = document.createElement("canvas");
    const configured = configureCanvas(canvas, run.width, run.height);
    if (!configured) return null;
    const { context } = configured;
    if (reusable) {
      context.drawImage(reusable.canvas, 0, 0, run.width, run.height);
      layer.setAttribute("data-subview-band-drag-reused", "1");
    } else {
      context.translate(0, -run.top);
      for (const band of run.bands) drawPolygon(context, band.points, run.left, band.styles);
    }
    Object.assign(canvas.style, { position: "absolute", left: "0", top: "0", transformOrigin: "0 0", willChange: "transform" });
    layer.appendChild(canvas);
    run.canvas = canvas;
  }
  let attached = false, restored = false;
  return {
    nodes: new Set(nodes),
    draw(deltaPx, [minX, minY, spanX, spanY]) {
      if (restored) return false;
      const sx = width / spanX, sy = height / spanY;
      for (const run of runs) {
        // x' = sx * (x + delta * (slope*y + intercept) - minX).
        // Raster origins are included before projection, never accumulated.
        const shear = sx * deltaPx * run.slope;
        const tx = sx * (run.left + deltaPx * (run.slope * run.top + run.intercept) - minX);
        const ty = sy * (run.top - minY);
        run.canvas.style.transform = `matrix(${sx},0,${shear},${sy},${tx},${ty})`;
      }
      if (clipY !== null) {
        const top = Math.max(0, (clipY - minY) * sy);
        const bottom = Math.max(0, height - (clipY + clipHeight - minY) * sy);
        layer.style.clipPath = `inset(${top}px 0 ${bottom}px 0)`;
      }
      if (!attached) {
        scroll.appendChild(layer);
        scroll.classList.add("is-subview-band-canvas-drag-preview");
        attached = true;
      }
      return true;
    },
    restore() {
      if (restored) return;
      restored = true;
      layer.remove();
      scroll.classList.remove("is-subview-band-canvas-drag-preview");
    },
  };
}

// Gesture-local paint records: retain every rendered band and its draw order,
// but never rewrite thousands of SVG proxy points on every pointer frame.
export function createSubviewBandCanvasDragPreview(scroll, actions, { width, height }) {
  const document = scroll?.ownerDocument;
  const svg = scroll?.querySelector?.("svg.assembly-track-svg");
  const nodes = svg?.querySelectorAll?.("polygon.track-collinearity-band[data-track-band-proxy='1']") || [];
  if (!nodes.length || !document?.createElement || !scroll?.appendChild) return null;
  const byNode = new Map(actions.filter((action) => action.kind === "band").map((action) => [action.node, action]));
  const dark = document.documentElement?.dataset?.theme === "dark";
  const resolveStyle = dark ? resolveDarkAlignmentBandStyle : resolveAlignmentBandStyle;
  const bands = [];
  for (const node of nodes) {
    const action = byNode.get(node);
    const points = action?.basePoints || String(node.getAttribute("points") || "").trim().split(/\s+/)
      .map((point) => point.split(",").map(Number));
    if (points.length !== 4 || points.some((point) => point.length !== 2 || !point.every(Number.isFinite))) return null;
    const identityText = node.getAttribute("data-band-identity-pct");
    const identityPct = identityText === null || identityText === "" ? null : Number(identityText);
    const tone = node.classList.contains("is-companion") ? "companion" : "primary";
    bands.push({ points, identityPct, tone, hitKey: String(node.getAttribute("data-subview-hit-key") || ""), styles: resolveStyle(tone, identityPct),
      moving: points.map((_, index) => action?.edgeIndexes.includes(index) ? 1 : 0) });
  }
  const orderedBands = sortAlignmentBands(bands);
  const clip = svg.querySelector("[data-subview-band-clip-rect='1']");
  const clipY = clip ? Number(clip.getAttribute("y")) : null;
  const clipHeight = clip ? Number(clip.getAttribute("height")) : 0;
  try {
    const bitmap = createBandDragBitmapPreview(document, scroll, orderedBands, nodes, { width, height, clipY, clipHeight });
    if (bitmap) return bitmap;
  } catch {
    // Allocation/context failures must keep the exact complete redraw path.
  }
  let canvas, configured;
  try {
    canvas = document.createElement("canvas");
    configured = configureCanvas(canvas, width, height);
  } catch {
    return null;
  }
  if (!configured) return null;
  canvas.className = "track-band-canvas-layer subview-band-drag-canvas";
  canvas.setAttribute("aria-hidden", "true");
  canvas.setAttribute("data-subview-band-drag-canvas", "1");
  canvas.setAttribute("data-subview-band-drag-mode", "redraw");
  const { context } = configured;
  let restored = false;
  let attached = false;
  return {
    nodes: new Set(nodes),
    draw(deltaPx, viewBox) {
      if (restored) return false;
      const [minX, minY, spanX, spanY] = viewBox;
      const scaleX = width / spanX, scaleY = height / spanY;
      context.clearRect(0, 0, configured.width, configured.height);
      if (clip) {
        context.save();
        context.beginPath();
        context.rect(0, (clipY - minY) * scaleY, width, clipHeight * scaleY);
        context.clip();
      }
      for (const band of orderedBands) {
        context.beginPath();
        for (let index = 0; index < band.points.length; index++) {
          const [x, y] = band.points[index];
          const px = (x + band.moving[index] * deltaPx - minX) * scaleX;
          const py = (y - minY) * scaleY;
          if (index === 0) context.moveTo(px, py);
          else context.lineTo(px, py);
        }
        context.closePath();
        context.fillStyle = band.styles.fill;
        context.strokeStyle = band.styles.stroke;
        context.fill();
        context.stroke();
      }
      if (clip) context.restore();
      // Switch paint surfaces only after the first complete successful draw.
      if (!attached) {
        scroll.appendChild(canvas);
        scroll.classList.add("is-subview-band-canvas-drag-preview");
        attached = true;
      }
      return true;
    },
    restore() {
      if (restored) return;
      restored = true;
      canvas.remove();
      scroll.classList.remove("is-subview-band-canvas-drag-preview");
    },
  };
}
