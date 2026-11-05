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
  canvas.style.width = "0px";
  canvas.style.height = "0px";
}

function configureCanvas(canvas, width, height) {
  const safeWidth = Math.max(1, Math.round(Number(width) || 0));
  const safeHeight = Math.max(1, Math.round(Number(height) || 0));
  const dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1));
  if (!canAllocateCanvasBitmap(safeWidth, safeHeight, dpr)) {
    disableCanvas(canvas);
    return null;
  }
  canvas.width = Math.max(1, Math.round(safeWidth * dpr));
  canvas.height = Math.max(1, Math.round(safeHeight * dpr));
  canvas.style.width = `${safeWidth}px`;
  canvas.style.height = `${safeHeight}px`;
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

function drawTrackBandCanvasLayer(layer, scene) {
  const canvas = layer?.querySelector?.("[data-track-band-canvas='1']");
  if (!canvas || !scene) {
    return false;
  }
  const configured = configureCanvas(canvas, scene.width, scene.height);
  if (!configured) {
    return false;
  }
  const { context, width, height } = configured;
  const offsetX = Number(scene.viewBoxMinX || 0);

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

  const dark = (layer?.ownerDocument || globalThis.document)?.documentElement?.dataset?.theme === "dark";
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
  return true;
}

export function bindBandCanvasRuntime(host) {
  const { request, cancel } = resolveAnimationFrameApi();
  const layers = host?.querySelectorAll?.("[data-track-band-canvas-layer='1']") || [];
  layers.forEach((layer) => {
    if (!layer) {
      return;
    }
    const sceneNode = layer.querySelector?.("[data-track-band-canvas-scene]");
    const sceneText = String(sceneNode?.textContent || "");
    const activeTheme = (layer?.ownerDocument || globalThis.document)?.documentElement?.dataset?.theme || "light";
    const previous = layer[TRACK_BAND_CANVAS_BOUND] || null;
    if (previous?.sceneText === sceneText && (previous?.theme || "light") === activeTheme) {
      return;
    }
    if (previous?.frameHandle !== undefined) {
      cancel(previous.frameHandle);
    }
    const trackScroll = layer.closest?.(".assembly-track-scroll") || layer.parentElement || null;
    trackScroll?.classList?.remove?.(TRACK_BAND_CANVAS_READY_CLASS);
    const scene = readTrackBandCanvasScene(layer);
    const frameHandle = request(() => {
      const drew = drawTrackBandCanvasLayer(layer, scene);
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
        };
      }
    });
    layer[TRACK_BAND_CANVAS_BOUND] = {
      sceneText,
      theme: activeTheme,
      frameHandle,
    };
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

function createBandDragBitmapPreview(document, scroll, bands, nodes, { width, height, clipY, clipHeight }) {
  const runs = compileBandDragBitmapRuns(bands);
  if (!runs?.length) return null;
  const layer = document.createElement("div");
  if (!layer?.appendChild) return null;
  const dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1));
  let area = 0;
  for (const run of runs) {
    run.left = Math.floor(run.minX) - 2; run.top = Math.floor(run.minY) - 2;
    run.width = Math.ceil(run.maxX) + 2 - run.left;
    run.height = Math.ceil(run.maxY) + 2 - run.top;
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
    context.translate(0, -run.top);
    for (const band of run.bands) drawPolygon(context, band.points, run.left, band.styles);
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
    bands.push({ points, identityPct, styles: resolveStyle(tone, identityPct),
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
