import test from "node:test";
import assert from "node:assert/strict";

import {
  addSubviewCompositionMembers,
  compactSubviewCompositionLayout,
  moveSubviewCompositionMembers,
  normalizeSubviewComposition,
  removeSubviewCompositionMembers,
  swapSubviewCompositionLanes,
} from "../subview-composition-state.js";
import { buildSubviewCompositionLayout } from "../subview-composition-layout.js";

function member(id, lane, xBp, lengthBp = 100) {
  return {
    assemblyCtgId: id,
    source: { role: "support", datasetId: 20, sourceType: "mother" },
    label: `ctg${id}`,
    lengthBp,
    lane,
    xBp,
    order: id,
  };
}

test("composition identity deduplicates a contig across both lanes", () => {
  const composition = normalizeSubviewComposition({
    members: [member(1, "top", 0), member(1, "bottom", 500)],
  });
  assert.equal(composition.members.length, 1);
  assert.equal(composition.members[0].lane, "top");
});

test("batch add appends new members and moves an existing cross-lane member without moving x", () => {
  const original = normalizeSubviewComposition({
    layoutGapBp: 20,
    members: [member(1, "bottom", 410), member(2, "top", 0, 200)],
  });
  const result = addSubviewCompositionMembers(original, [member(1), member(3, "top", 0, 50)], "top");
  assert.equal(result.addedCount, 1);
  assert.equal(result.movedCount, 1);
  assert.equal(result.composition.members.find((entry) => entry.assemblyCtgId === 1).xBp, 410);
  assert.equal(result.composition.members.find((entry) => entry.assemblyCtgId === 3).xBp, 220);
});

test("remove and move preserve every unaffected world coordinate and orientation", () => {
  const original = normalizeSubviewComposition({
    members: [
      { ...member(1, "top", -50), flipped: true },
      member(2, "top", 500),
      member(3, "bottom", 1000),
    ],
  });
  const removed = removeSubviewCompositionMembers(original, ["assembly:2"]);
  const moved = moveSubviewCompositionMembers(removed.composition, ["assembly:1"], "bottom");
  assert.deepEqual(
    moved.composition.members.map(({ assemblyCtgId, lane, xBp, flipped }) => ({ assemblyCtgId, lane, xBp, flipped })),
    [
      { assemblyCtgId: 1, lane: "bottom", xBp: -50, flipped: true },
      { assemblyCtgId: 3, lane: "bottom", xBp: 1000, flipped: false },
    ],
  );
});

test("swap only changes lanes and compact is explicit and stable", () => {
  const original = normalizeSubviewComposition({
    layoutGapBp: 10,
    members: [member(1, "top", 500), member(2, "top", -100), member(3, "bottom", 90)],
  });
  const swapped = swapSubviewCompositionLanes(original).composition;
  assert.deepEqual(swapped.members.map(({ lane, xBp }) => ({ lane, xBp })), [
    { lane: "bottom", xBp: 500 },
    { lane: "bottom", xBp: -100 },
    { lane: "top", xBp: 90 },
  ]);
  const compacted = compactSubviewCompositionLayout(original).composition;
  assert.equal(compacted.members.find((entry) => entry.assemblyCtgId === 2).xBp, 0);
  assert.equal(compacted.members.find((entry) => entry.assemblyCtgId === 1).xBp, 110);
  assert.equal(compacted.members.find((entry) => entry.assemblyCtgId === 3).xBp, 0);
});

test("layout keeps negative and overlapping world coordinates", () => {
  const layout = buildSubviewCompositionLayout({
    members: [member(1, "top", -1_000, 4_000), member(2, "top", -500, 2_000)],
  }, { bpPerPx: 100, viewportWidthPx: 400, leftBp: 2_000 });
  assert.equal(layout.top[0].x, -10);
  assert.equal(layout.top[1].x, -5);
  assert.equal(layout.top[0].width, 40);
  assert.equal(layout.viewBoxMinX, -10);
});
