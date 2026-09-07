import test from "node:test";
import assert from "node:assert/strict";

import { createSupportDatasetController } from "../support-dataset-controller.js";

test("support dataset switching persists offsets for every chromosome and dataset", async () => {
  const offsets = [
    { trackRole: "primary", assemblyCtgId: 90, offsetBp: 120 },
    { trackRole: "phased", assemblyCtgId: 91, phasedTrackId: 9, phasedTrackItemId: 99, offsetBp: -40 },
    { trackRole: "support", datasetId: 2, assemblyCtgId: 92, offsetBp: 50 },
  ];
  let state = {
    session: { workspacePath: "/tmp/workspace", projectId: 7 },
    assembly: {
      selectedChrName: "Chr01", supportDatasetId: 2,
      chrCtgs: [{ assemblyCtgId: 1 }], supportChrCtgs: [{ assemblyCtgId: 2 }],
      trackDragOffsets: offsets, subview: { summary: { mode: "ctg" } },
    },
  };
  const store = {
    getState: () => state,
    setState(patch) { state = { ...state, ...patch }; },
  };
  let saved;
  const controller = createSupportDatasetController({
    session: {},
    buildClearedSubviewState: () => ({ summary: null }),
    getSupportDatasetOptions: () => [],
    rerender() {},
    async persistProjectAssemblyViewState(payload) { saved = payload; },
    async loadSupportChrCtgs() {
      assert.deepEqual(store.getState().assembly.trackDragOffsets, offsets);
      return [{ assemblyCtgId: 3 }];
    },
  });
  assert.equal(await controller.applySupportDatasetSelection({}, store, 3), true);
  assert.deepEqual(saved.trackDragOffsets, offsets);
  assert.deepEqual(state.assembly.trackDragOffsets, offsets);
  assert.deepEqual(state.assembly.supportChrCtgs, [{ assemblyCtgId: 3 }]);
  assert.equal(state.assembly.subview.summary, null);
});
