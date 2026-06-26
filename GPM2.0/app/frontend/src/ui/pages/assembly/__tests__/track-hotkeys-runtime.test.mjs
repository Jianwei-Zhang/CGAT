import test from "node:test";
import assert from "node:assert/strict";

import { bindTrackSelectionHotkeys } from "../track-hotkeys-runtime.js";

test("bindTrackSelectionHotkeys registers one window keydown handler per host and routes events", async () => {
  const originalWindow = globalThis.window;
  const listenerMap = new Map();
  globalThis.window = {
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };

  try {
    const host = {};
    const store = {
      getState() {
        return {
          assembly: {
            activeTab: "assembly",
            trackSelectedCtgIds: [2],
          },
        };
      },
    };
    const calls = [];

    bindTrackSelectionHotkeys(host, store, {
      handleTrackDeleteHotkey: async (_host, _store, event) => {
        calls.push(event.key);
      },
    });
    bindTrackSelectionHotkeys(host, store, {
      handleTrackDeleteHotkey: async () => {
        throw new Error("duplicate binding should not replace existing handler");
      },
    });

    assert.equal(listenerMap.size, 1);
    assert.equal(typeof listenerMap.get("keydown"), "function");

    await listenerMap.get("keydown")?.({ key: "Delete" });

    assert.deepEqual(calls, ["Delete"]);
  } finally {
    globalThis.window = originalWindow;
  }
});
