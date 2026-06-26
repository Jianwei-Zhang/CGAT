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

function resolveBandToneStyle(tone) {
  return String(tone || "").trim() === "companion"
    ? {
        fill: "rgba(154, 126, 78, 0.22)",
        stroke: "rgba(154, 126, 78, 0.34)",
      }
    : {
        fill: "rgba(97, 129, 170, 0.24)",
        stroke: "rgba(97, 129, 170, 0.38)",
      };
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

  (Array.isArray(scene.bands) ? scene.bands : []).forEach((band) => {
    drawPolygon(
      context,
      band?.points,
      offsetX,
      resolveBandToneStyle(band?.tone),
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
    const previous = layer[TRACK_BAND_CANVAS_BOUND] || null;
    if (previous?.sceneText === sceneText) {
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
      frameHandle,
    };
  });
}
