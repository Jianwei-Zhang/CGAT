import test from "node:test";
import assert from "node:assert/strict";

import { createSubviewSelectionController } from "../subview-selection-controller.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(patch) {
      state = {
        ...state,
        ...patch,
      };
    },
  };
}

test("removing a Subview track selection refreshes main-track and Subview selection styling", () => {
  const renderCalls = [];
  const controller = createSubviewSelectionController({
    rerenderAssemblyMainTab() {
      renderCalls.push("main");
    },
    rerenderSubviewPanel() {
      renderCalls.push("subview");
    },
  });
  const store = createStore({
    locale: "zh",
    assembly: {
      subview: {
        mode: "track-pair",
        selectedTrackSelections: [
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        summary: {
          mode: "track-pair",
          topTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
          bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
        },
      },
      subviewTrackDragOffsets: [{ trackRole: "primary", offsetPx: 20 }],
    },
  });

  controller.handleSubviewTrackSelectionRemoval({}, store, {
    trackRole: "primary",
    source: "mother",
    datasetId: null,
    isMirror: false,
  });

  const assembly = store.getState().assembly;
  assert.deepEqual(assembly.subview.selectedTrackSelections, [
    { role: "support", source: "mother", datasetId: 22, isMirror: false },
  ]);
  assert.equal(assembly.subview.summary, null);
  assert.deepEqual(assembly.subviewTrackDragOffsets, []);
  assert.deepEqual(renderCalls, ["main", "subview"]);
});
