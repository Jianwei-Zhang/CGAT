import test from "node:test";
import assert from "node:assert/strict";

import { bindBandCanvasRuntime } from "../band-canvas-runtime.js";
import { resolveAlignmentBandStyle } from "../alignment-band-style.js";

function createClassList() {
  const values = new Set();
  return {
    add(value) {
      values.add(value);
    },
    remove(value) {
      values.delete(value);
    },
    contains(value) {
      return values.has(value);
    },
  };
}

function createCanvasLayer({ context = null, sceneOverrides = {} } = {}) {
  const scrollNode = {
    classList: createClassList(),
  };
  const sceneNode = {
    textContent: JSON.stringify({
      version: 1,
      kind: "subview-ctg",
      width: 200,
      height: 80,
      viewBoxMinX: 0,
      clipRect: null,
      bands: [
        {
          tone: "primary",
          points: [
            [10, 20],
            [60, 20],
            [70, 60],
            [20, 60],
          ],
        },
      ],
      ...sceneOverrides,
    }),
  };
  const canvas = {
    style: {},
    getContext() {
      return context;
    },
  };
  const layer = {
    parentElement: scrollNode,
    querySelector(selector) {
      if (selector === "[data-track-band-canvas='1']") {
        return canvas;
      }
      if (selector === "[data-track-band-canvas-scene]") {
        return sceneNode;
      }
      return null;
    },
  };
  const host = {
    querySelectorAll(selector) {
      return selector === "[data-track-band-canvas-layer='1']" ? [layer] : [];
    },
  };
  return { host, scrollNode };
}

function createContextRecorder() {
  const calls = [];
  return {
    calls,
    setTransform(...args) {
      calls.push(["setTransform", ...args]);
    },
    clearRect(...args) {
      calls.push(["clearRect", ...args]);
    },
    beginPath() {
      calls.push(["beginPath"]);
    },
    moveTo(...args) {
      calls.push(["moveTo", ...args]);
    },
    lineTo(...args) {
      calls.push(["lineTo", ...args]);
    },
    closePath() {
      calls.push(["closePath"]);
    },
    fill() {
      calls.push(["fill"]);
    },
    stroke() {
      calls.push(["stroke"]);
    },
  };
}

test("canvas draws opaque identity fills low-to-high with stable equal-quality ties", () => {
  const originalRequest = globalThis.requestAnimationFrame;
  const originalCancel = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => { callback(0); return 1; };
  globalThis.cancelAnimationFrame = () => {};
  try {
    const paints = [];
    const context = createContextRecorder();
    context.fill = function () { paints.push(this.fillStyle); };
    const points = [[10, 20], [60, 20], [70, 60], [20, 60]];
    const { host } = createCanvasLayer({ context, sceneOverrides: { bands: [
      { identityPct: 100, tone: "primary", points },
      { identityPct: 85, tone: "primary", points },
      { identityPct: null, tone: "primary", points },
      { identityPct: 85, tone: "companion", points },
      { identityPct: 0, tone: "primary", points },
    ] } });
    bindBandCanvasRuntime(host);
    assert.deepEqual(paints, [
      resolveAlignmentBandStyle("primary", null).fill,
      resolveAlignmentBandStyle("primary", 0).fill,
      resolveAlignmentBandStyle("primary", 85).fill,
      resolveAlignmentBandStyle("companion", 85).fill,
      resolveAlignmentBandStyle("primary", 100).fill,
    ]);
    paints.forEach((fill) => assert.ok(fill.startsWith("rgb("), "no alpha blending"));
  } finally {
    globalThis.requestAnimationFrame = originalRequest;
    globalThis.cancelAnimationFrame = originalCancel;
  }
});

test("band canvas marks the track scroll ready only after a successful draw", () => {
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
  const originalDevicePixelRatio = globalThis.devicePixelRatio;
  globalThis.requestAnimationFrame = (callback) => {
    callback(0);
    return 1;
  };
  globalThis.cancelAnimationFrame = () => {};
  globalThis.devicePixelRatio = 1;
  try {
    const context = createContextRecorder();
    const { host, scrollNode } = createCanvasLayer({ context });

    bindBandCanvasRuntime(host);

    assert.equal(scrollNode.classList.contains("is-track-band-canvas-ready"), true);
    assert.ok(context.calls.some((call) => call[0] === "fill"));
  } finally {
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
    globalThis.devicePixelRatio = originalDevicePixelRatio;
  }
});

test("band canvas keeps svg proxy bands visible when canvas drawing cannot start", () => {
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
  globalThis.requestAnimationFrame = (callback) => {
    callback(0);
    return 1;
  };
  globalThis.cancelAnimationFrame = () => {};
  try {
    const { host, scrollNode } = createCanvasLayer({ context: null });

    bindBandCanvasRuntime(host);

    assert.equal(scrollNode.classList.contains("is-track-band-canvas-ready"), false);
  } finally {
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
  }
});

test("band canvas keeps svg proxy bands visible when the requested bitmap is too large", () => {
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;
  const originalDevicePixelRatio = globalThis.devicePixelRatio;
  globalThis.requestAnimationFrame = (callback) => {
    callback(0);
    return 1;
  };
  globalThis.cancelAnimationFrame = () => {};
  globalThis.devicePixelRatio = 1;
  try {
    const context = createContextRecorder();
    const { host, scrollNode } = createCanvasLayer({
      context,
      sceneOverrides: {
        width: 40000,
        height: 80,
      },
    });

    bindBandCanvasRuntime(host);

    assert.equal(scrollNode.classList.contains("is-track-band-canvas-ready"), false);
    assert.equal(context.calls.some((call) => call[0] === "fill"), false);
  } finally {
    globalThis.requestAnimationFrame = originalRequestAnimationFrame;
    globalThis.cancelAnimationFrame = originalCancelAnimationFrame;
    globalThis.devicePixelRatio = originalDevicePixelRatio;
  }
});
