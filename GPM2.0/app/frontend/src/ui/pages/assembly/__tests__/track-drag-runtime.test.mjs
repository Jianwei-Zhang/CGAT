import test from "node:test";
import assert from "node:assert/strict";

import {
  bindSubviewTrackContigDrag,
  bindTrackContigDrag,
} from "../track-drag-runtime.js";

function createStore(initialState) {
  return {
    getState() {
      return initialState;
    },
  };
}

function createHost() {
  const listeners = new Map();
  return {
    listeners,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
}

function createWindowStub() {
  const listeners = new Map();
  let nextFrameToken = 1;
  const frameCallbacks = new Map();
  return {
    listeners,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    removeEventListener(type, handler) {
      if (listeners.get(type) === handler) {
        listeners.delete(type);
      }
    },
    requestAnimationFrame(callback) {
      const token = nextFrameToken;
      nextFrameToken += 1;
      frameCallbacks.set(token, callback);
      return token;
    },
    cancelAnimationFrame(token) {
      frameCallbacks.delete(token);
    },
    flushAnimationFrame() {
      const entries = Array.from(frameCallbacks.entries());
      frameCallbacks.clear();
      entries.forEach(([, callback]) => callback(Date.now()));
    },
  };
}

test("bindTrackContigDrag previews during move and applies pending primary-track drag offset on release", () => {
  const originalWindow = globalThis.window;
  const windowStub = createWindowStub();
  globalThis.window = windowStub;

  try {
    const host = createHost();
    const store = createStore({
      assembly: {
        activeTab: "assembly",
        trackDragOffsets: [],
      },
    });
    const scrollEl = {
      scrollLeft: 4,
      dataset: {
        trackDomainSpanBp: "100",
        trackInnerWidth: "100",
      },
    };
    const trackNode = {
      getAttribute(name) {
        if (name === "data-track-role") return "primary";
        if (name === "data-track-contig-id") return "8";
        return null;
      },
      closest(selector) {
        if (selector === ".assembly-track-scroll[data-track-role='primary']") {
          return scrollEl;
        }
        return null;
      },
    };
    const target = {
      closest(selector) {
        if (selector === "[data-track-contig-id][data-track-role]") {
          return trackNode;
        }
        return null;
      },
    };

    const calls = [];
    bindTrackContigDrag(host, store, {
      clearTrackDragPreview() {
        calls.push(["clear-preview"]);
      },
      applyTrackDragOffset(_host, _store, payload) {
        calls.push(["apply", payload]);
      },
      convertTrackOffsetPxToBp(value) {
        return value;
      },
      previewTrackContigDrag(_host, payload) {
        calls.push(["preview", payload]);
      },
      resolveActiveTrackScrollElement() {
        return scrollEl;
      },
      resolveTrackDragOffsetBp() {
        return 5;
      },
      roundTrackMetric(value) {
        return value;
      },
      persistTrackDragOffsets() {
        calls.push(["persist"]);
      },
      setTrackContigDragActive(value) {
        calls.push(["drag-active", value]);
      },
      setSuppressTrackContigClickUntil(value) {
        calls.push(["suppress", value]);
      },
    });

    host.listeners.get("pointerdown")?.({
      button: 0,
      clientX: 10,
      ctrlKey: false,
      metaKey: false,
      preventDefault() {
        calls.push(["prevent"]);
      },
      target,
    });

    windowStub.listeners.get("pointermove")?.({ clientX: 25 });
    windowStub.flushAnimationFrame();
    assert.deepEqual(calls[2], ["preview", { trackRole: "primary", assemblyCtgId: 8, offsetPx: 15 }]);
    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(calls[0], ["prevent"]);
    assert.deepEqual(calls[1], ["drag-active", true]);
    assert.deepEqual(calls[3], ["clear-preview"]);
    assert.deepEqual(calls[4], ["apply", { trackRole: "primary", assemblyCtgId: 8, offsetBp: 20 }]);
    assert.deepEqual(calls[5], ["persist"]);
    assert.equal(calls[6][0], "suppress");
    assert.equal(typeof calls[6][1], "number");
    assert.deepEqual(calls[7], ["drag-active", false]);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("bindTrackContigDrag ignores ref-track members", () => {
  const originalWindow = globalThis.window;
  const windowStub = createWindowStub();
  globalThis.window = windowStub;

  try {
    const host = createHost();
    const store = createStore({
      assembly: {
        activeTab: "assembly",
        trackDragOffsets: [],
      },
    });
    const trackNode = {
      getAttribute(name) {
        if (name === "data-track-role") return "ref";
        if (name === "data-track-contig-id") return "9001";
        if (name === "data-track-source-kind") return "ref_segment";
        return null;
      },
      closest() {
        throw new Error("ref members should return before resolving scroll container");
      },
    };
    const target = {
      closest(selector) {
        if (selector === "[data-track-contig-id][data-track-role]") {
          return trackNode;
        }
        return null;
      },
    };

    const calls = [];
    bindTrackContigDrag(host, store, {
      clearTrackDragPreview() {
        calls.push(["clear-preview"]);
      },
      applyTrackDragOffset(_host, _store, payload) {
        calls.push(["apply", payload]);
      },
      convertTrackOffsetPxToBp(value) {
        return value;
      },
      previewTrackContigDrag(_host, payload) {
        calls.push(["preview", payload]);
      },
      resolveActiveTrackScrollElement() {
        return null;
      },
      resolveTrackDragOffsetBp() {
        return 0;
      },
      roundTrackMetric(value) {
        return value;
      },
      persistTrackDragOffsets() {
        calls.push(["persist"]);
      },
      setTrackContigDragActive(value) {
        calls.push(["drag-active", value]);
      },
      setSuppressTrackContigClickUntil(value) {
        calls.push(["suppress", value]);
      },
    });

    host.listeners.get("pointerdown")?.({
      button: 0,
      clientX: 10,
      ctrlKey: false,
      metaKey: false,
      preventDefault() {
        calls.push(["prevent"]);
      },
      target,
    });

    assert.deepEqual(calls, []);
    assert.equal(windowStub.listeners.has("pointermove"), false);
    assert.equal(windowStub.listeners.has("pointerup"), false);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("bindSubviewTrackContigDrag previews during move and applies pending subview offset on release", () => {
  const originalWindow = globalThis.window;
  const windowStub = createWindowStub();
  globalThis.window = windowStub;

  try {
    const host = createHost();
    const store = createStore({
      assembly: {
        activeTab: "assembly",
        subviewTrackDragOffsets: [],
      },
    });
    const scrollEl = {
      scrollLeft: 3,
      dataset: {
        subviewDomainSpanBp: "100",
        subviewInnerWidth: "100",
      },
    };
    const trackNode = {
      getAttribute(name) {
        if (name === "data-subview-track-slot") return "top";
        if (name === "data-subview-contig-id") return "12";
        return null;
      },
      closest(selector) {
        if (selector === ".assembly-track-scroll[data-track-role='subview']") {
          return scrollEl;
        }
        return null;
      },
    };
    const target = {
      closest(selector) {
        if (selector === "[data-subview-contig-id][data-subview-track-slot]") {
          return trackNode;
        }
        return null;
      },
    };

    const calls = [];
    bindSubviewTrackContigDrag(host, store, {
      clearSubviewTrackDragPreview() {
        calls.push(["clear-preview"]);
      },
      applySubviewTrackDragOffset(_host, _store, payload) {
        calls.push(["apply", payload]);
      },
      convertTrackOffsetPxToBp(value) {
        return value;
      },
      previewSubviewTrackContigDrag(_host, payload) {
        calls.push(["preview", payload]);
      },
      resolveActiveTrackScrollElement() {
        return scrollEl;
      },
      resolveSubviewTrackDragOffsetBp() {
        return 7;
      },
      roundTrackMetric(value) {
        return value;
      },
      persistSubviewTrackDragOffsets() {
        calls.push(["persist"]);
      },
    });

    host.listeners.get("pointerdown")?.({
      button: 0,
      clientX: 5,
      ctrlKey: false,
      metaKey: false,
      preventDefault() {
        calls.push(["prevent"]);
      },
      target,
    });

    windowStub.listeners.get("pointermove")?.({ clientX: 17 });
    windowStub.flushAnimationFrame();
    assert.deepEqual(calls[1], ["preview", { slot: "top", contigId: 12, offsetPx: 12 }]);
    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(calls, [
      ["prevent"],
      ["preview", { slot: "top", contigId: 12, offsetPx: 12 }],
      ["clear-preview"],
      ["apply", { slot: "top", contigId: 12, offsetBp: 19 }],
      ["persist"],
    ]);
  } finally {
    globalThis.window = originalWindow;
  }
});
