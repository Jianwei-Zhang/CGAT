import test from "node:test";
import assert from "node:assert/strict";

import { createStore } from "../../../../state/store.js";
import { createSubviewInteractionController } from "../subview-interaction-controller.js";
import { activateSubviewHistory, resolveCurrentSubviewHistory } from "../subview-history-state.js";

function anchorNode() {
  const attributes = {
    "data-subview-anchor-kind": "evidence",
    "data-subview-anchor-object-id": "edge:hit-1:left",
    "data-subview-anchor-top-endpoint-key": "top-1",
    "data-subview-anchor-top-contig-id": "1",
    "data-subview-anchor-top-cut-bp": "100",
    "data-subview-anchor-top-name": "ctg_top",
    "data-subview-anchor-top-source-label": "GRT · primary",
    "data-subview-anchor-top-source-role": "primary",
    "data-subview-anchor-top-source-kind": "mother",
    "data-subview-anchor-top-source-name": "hifiasm",
    "data-subview-anchor-bottom-endpoint-key": "bottom-2",
    "data-subview-anchor-bottom-contig-id": "2",
    "data-subview-anchor-bottom-cut-bp": "200",
    "data-subview-anchor-bottom-name": "ctg_bottom",
    "data-subview-anchor-bottom-source-label": "User track",
    "data-subview-anchor-bottom-source-role": "support",
    "data-subview-anchor-bottom-source-kind": "mother",
    "data-subview-anchor-bottom-source-name": "flye",
    "data-subview-anchor-top-x": "300",
    "data-subview-anchor-bottom-x": "320",
  };
  return { getAttribute: (name) => attributes[name] ?? null };
}

test("legacy anchor descriptor enrichment persists without adding a history operation", async () => {
  const initial = activateSubviewHistory({
    selectedChrName: "Chr01",
    subviewAnchorStateByKey: {},
    subviewHistoryByKey: {},
    subviewTrackDragOffsets: [],
    subview: {
      mode: "2-contig",
      selectedAContigId: 1,
      selectedARole: "primary",
      selectedBContigId: 2,
      selectedBRole: "support",
      activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
      manualAnchors: [],
      summary: {
        mode: "2-contig",
        top: { role: "primary", contigId: 1 },
        bottom: { role: "support", contigId: 2, datasetId: 22 },
      },
    },
  }, { now: 0 }).assembly;
  const store = createStore({ assembly: initial });
  const host = { querySelectorAll: () => [anchorNode()] };
  let persisted = 0;
  const controller = createSubviewInteractionController({
    async persistProjectAssemblyViewStateFromStore() { persisted += 1; },
    async requestAssemblyAnchorOffsetPrompt() { return null; },
    rerenderSubviewPanel() {},
    setAssemblyActionFeedback() {},
    tAssembly() { return ""; },
  });
  const before = resolveCurrentSubviewHistory(initial);

  assert.equal(await controller.enrichSubviewAnchorDescriptors(host, store), true);

  const assembly = store.getState().assembly;
  const after = resolveCurrentSubviewHistory(assembly);
  assert.equal(assembly.subview.activeAnchors[0].descriptor.top.name, "ctg_top");
  assert.equal(Object.values(assembly.subviewAnchorStateByKey)[0].activeAnchors[0]
    .descriptor.bottom.sourceName, "flye");
  assert.equal(after.record.current.activeAnchors[0].descriptor.top.sourceRole, "primary");
  assert.equal(after.record.current.activeAnchors[0].descriptor.top.sourceLabel, undefined);
  assert.equal(after.record.past.length, before.record.past.length);
  assert.equal(after.record.forward.length, before.record.forward.length);
  assert.equal(persisted, 1);
  assert.equal(await controller.enrichSubviewAnchorDescriptors(host, store), false);
  assert.equal(persisted, 1);
});
