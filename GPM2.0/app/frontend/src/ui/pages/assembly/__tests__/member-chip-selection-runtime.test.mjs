import test from "node:test";
import assert from "node:assert/strict";

import { bindDeletedMemberChipBoxSelection } from "../member-chip-selection-runtime.js";

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

test("bindDeletedMemberChipBoxSelection updates primary and deleted selections from chip region box drag", () => {
  const originalWindow = globalThis.window;
  const windowStub = createWindowStub();
  globalThis.window = windowStub;

  try {
    const boxEl = {
      style: {},
      classList: createClassList(["is-hidden"]),
    };
    const regionEl = {
      scrollLeft: 0,
      scrollTop: 0,
      querySelector(selector) {
        return selector === ".member-chip-selection-box" ? boxEl : null;
      },
      querySelectorAll(selector) {
        if (selector === "[data-assembly-ctg-id]") {
          return [
            {
              getAttribute(name) {
                return name === "data-assembly-ctg-id" ? "2" : null;
              },
              offsetLeft: 12,
              offsetTop: 10,
              offsetWidth: 60,
              offsetHeight: 30,
            },
          ];
        }
        if (selector === "[data-deleted-ctg-record-id]") {
          return [
            {
              getAttribute(name) {
                return name === "data-deleted-ctg-record-id" ? "9101" : null;
              },
              offsetLeft: 12,
              offsetTop: 70,
              offsetWidth: 60,
              offsetHeight: 30,
            },
          ];
        }
        return [];
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
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
          },
        };
      },
    };
    const calls = [];

    bindDeletedMemberChipBoxSelection(host, store, {
      updateDeletedCtgSelection(_host, _store, selectedIds) {
        calls.push(["deleted", selectedIds]);
      },
      updateTrackSelection(_host, _store, selectedIds) {
        calls.push(["primary", selectedIds]);
      },
    });

    hostListeners.get("pointerdown")?.({
      button: 0,
      clientX: 5,
      clientY: 5,
      target: {
        closest(selector) {
          if (selector === ".assembly-member-chip-region") {
            return regionEl;
          }
          return null;
        },
      },
    });

    windowStub.listeners.get("pointermove")?.({ clientX: 90, clientY: 120 });
    windowStub.listeners.get("pointerup")?.();

    assert.deepEqual(calls, [
      ["primary", [2]],
      ["deleted", [9101]],
    ]);
    assert.equal(boxEl.classList.has("is-hidden"), true);
  } finally {
    globalThis.window = originalWindow;
  }
});
