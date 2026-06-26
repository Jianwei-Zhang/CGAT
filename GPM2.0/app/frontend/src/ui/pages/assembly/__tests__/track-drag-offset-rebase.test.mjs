import test from "node:test";
import assert from "node:assert/strict";

import {
  rebaseTrackDragOffsetsForStableCtgPositions,
} from "../track-drag-offset-rebase.js";

test("rebaseTrackDragOffsetsForStableCtgPositions keeps a dragged ctg stable after another ctg is restored", () => {
  const result = rebaseTrackDragOffsetsForStableCtgPositions({
    trackRole: "primary",
    previousCtgs: [
      { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
    ],
    nextCtgs: [
      { assemblyCtgId: 1, name: "ctg1", anchorStart: 100, totalLength: 100 },
      { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
    ],
    trackDragOffsets: [
      { trackRole: "primary", assemblyCtgId: 2, offsetBp: 125 },
    ],
  });

  assert.deepEqual(result, [
    { trackRole: "primary", assemblyCtgId: 2, offsetBp: 25 },
  ]);
});

test("rebaseTrackDragOffsetsForStableCtgPositions removes offsets that become the restored base position", () => {
  const result = rebaseTrackDragOffsetsForStableCtgPositions({
    trackRole: "primary",
    previousCtgs: [
      { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
    ],
    nextCtgs: [
      { assemblyCtgId: 1, name: "ctg1", anchorStart: 100, totalLength: 100 },
      { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
    ],
    trackDragOffsets: [
      { trackRole: "primary", assemblyCtgId: 2, offsetBp: 100 },
    ],
  });

  assert.deepEqual(result, []);
});

test("rebaseTrackDragOffsetsForStableCtgPositions does not create offsets for untouched ctgs", () => {
  const result = rebaseTrackDragOffsetsForStableCtgPositions({
    trackRole: "primary",
    previousCtgs: [
      { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
    ],
    nextCtgs: [
      { assemblyCtgId: 1, name: "ctg1", anchorStart: 100, totalLength: 100 },
      { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
    ],
    trackDragOffsets: [],
  });

  assert.deepEqual(result, []);
});
