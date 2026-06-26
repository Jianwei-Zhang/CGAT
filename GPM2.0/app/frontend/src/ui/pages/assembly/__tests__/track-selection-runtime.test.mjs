import test from "node:test";
import assert from "node:assert/strict";

import { bindTrackBoxSelection } from "../track-selection-runtime.js";

function createWindowStub() {
  const listeners = new Map();
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
  };
}

function createClassList(initial = []) {
  const values = new Set(initial);
  return {
    add(value) {
      values.add(value);
    },
    remove(value) {
      values.delete(value);
    },
    has(value) {
      return values.has(value);
    },
  };
}

function createSelectionBox() {
  return {
    style: {},
    classList: createClassList(["is-hidden"]),
  };
}

function createStore(initialState) {
  return {
    getState() {
      return initialState;
    },
  };
}

test("bindTrackBoxSelection collects primary-track box selections and clears the box on pointerup", () => {
  const originalWindow = globalThis.window;
  const windowStub = createWindowStub();
  globalThis.window = windowStub;

  try {
    const boxEl = createSelectionBox();
    const primaryNode = {
      getAttribute(name) {
        const attrs = {
          "data-track-role": "primary",
          "data-track-contig-id": "5",
          "data-track-rect-x": "10",
          "data-track-rect-y": "12",
          "data-track-rect-width": "50",
          "data-track-rect-height": "20",
        };
        return attrs[name] ?? null;
      },
    };
    const scrollEl = {
      scrollLeft: 0,
      scrollTop: 0,
      dataset: { trackViewboxMinX: "0" },
      getAttribute(name) {
        return name === "data-track-role" ? "primary" : null;
      },
      querySelector(selector) {
        return selector === ".track-selection-box" ? boxEl : null;
      },
      querySelectorAll(selector) {
        return selector === "[data-track-contig-id][data-track-role]" ? [primaryNode] : [];
      },
      appendChild() {},
      getBoundingClientRect() {
        return { left: 0, top: 0 };
      },
    };
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = createStore({
      assembly: {
        activeTab: "assembly",
      },
    });
    const calls = [];

    bindTrackBoxSelection(host, store, {
      updateSubviewTrackPairSelection() {
        calls.push(["subview"]);
      },
      updateTrackSelection(_host, _store, selectedIds) {
        calls.push(["primary", selectedIds]);
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      clientX: 10,
      clientY: 10,
      preventDefault() {
        calls.push(["prevent"]);
      },
      target: {
        closest(selector) {
          if (selector === ".assembly-track-scroll[data-track-role]") {
            return scrollEl;
          }
          return null;
        },
      },
    });

    windowStub.listeners.get("pointermove")?.({ clientX: 40, clientY: 32 });
    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(calls, [
      ["prevent"],
      ["primary", [5]],
    ]);
    assert.equal(boxEl.classList.has("is-hidden"), true);
  } finally {
    globalThis.window = originalWindow;
  }
});

test("bindTrackBoxSelection collects subview box selections in track-pair mode", () => {
  const originalWindow = globalThis.window;
  const windowStub = createWindowStub();
  globalThis.window = windowStub;

  try {
    const boxEl = createSelectionBox();
    const subviewNode = {
      getAttribute(name) {
        const attrs = {
          "data-subview-track-role": "primary",
          "data-subview-contig-id": "12",
          "data-subview-rect-x": "5",
          "data-subview-rect-y": "8",
          "data-subview-rect-width": "40",
          "data-subview-rect-height": "18",
        };
        return attrs[name] ?? null;
      },
    };
    const scrollEl = {
      scrollLeft: 0,
      scrollTop: 0,
      dataset: { subviewViewboxMinX: "0" },
      getAttribute(name) {
        return name === "data-track-role" ? "subview" : null;
      },
      querySelector(selector) {
        return selector === ".track-selection-box" ? boxEl : null;
      },
      querySelectorAll(selector) {
        return selector === "[data-subview-contig-id][data-subview-track-role]" ? [subviewNode] : [];
      },
      appendChild() {},
      getBoundingClientRect() {
        return { left: 0, top: 0 };
      },
    };
    const hostListeners = new Map();
    const host = {
      addEventListener(type, handler) {
        hostListeners.set(type, handler);
      },
    };
    const store = createStore({
      assembly: {
        activeTab: "assembly",
      },
    });
    const calls = [];

    bindTrackBoxSelection(host, store, {
      updateSubviewTrackPairSelection(_host, _store, selectedEntries) {
        calls.push(["subview", selectedEntries]);
      },
      updateTrackSelection() {
        calls.push(["primary"]);
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      clientX: 5,
      clientY: 5,
      preventDefault() {
        calls.push(["prevent"]);
      },
      target: {
        closest(selector) {
          if (selector === ".assembly-track-scroll[data-track-role]") {
            return scrollEl;
          }
          return null;
        },
      },
    });

    windowStub.listeners.get("pointermove")?.({ clientX: 25, clientY: 25 });
    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(calls, [
      ["prevent"],
      ["subview", [{ trackRole: "primary", contigId: 12 }]],
    ]);
    assert.equal(boxEl.classList.has("is-hidden"), true);
  } finally {
    globalThis.window = originalWindow;
  }
});
