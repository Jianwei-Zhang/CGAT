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
import { splitLocalMember, mergeLocalMember } from "../subview-fragment-model.js";
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

for (const orient of ["+", "-"]) {
  test(`inherited display spacing survives split, merge and explicit compact without changing source lengths (${orient})`, () => {
    const original = normalizeSubviewComposition({ members: [{ ...member(1, "top", 200, 100),
      displayOffsetBp: 15, displayScale: 0.8, baseOrientation: orient,
    }] });
    const layout = (composition) => buildSubviewCompositionLayout(composition, { bpPerPx: 1 });
    const before = layout(original).members[0];
    const split = splitLocalMember(original, "assembly:1", 40);
    assert.equal(split.changed, true);
    const rects = layout(split.composition).members.sort((a, b) => a.x - b.x);
    assert.equal(rects[0].x, before.x);
    assert.equal(rects[0].x + rects[0].width, rects[1].x);
    assert.equal(rects[1].x + rects[1].width, before.x + before.width);
    assert.equal(rects.reduce((sum, entry) => sum + entry.lengthBp, 0), 100);
    for (const [index, side] of [[0, "right"], [1, "left"]]) {
      const merged = mergeLocalMember(split.composition, rects[index].entityKey, side);
      assert.equal(merged.changed, true);
      const result = layout(merged.composition).members[0];
      assert.equal(result.x, before.x);
      assert.equal(result.width, before.width);
      assert.equal(result.xBp, 200);
      assert.equal(result.lengthBp, 100);
    }
    const compacted = compactSubviewCompositionLayout(original);
    assert.equal(compacted.changed, true);
    const compactRect = layout(compacted.composition).members[0];
    assert.equal(compactRect.x, 0);
    assert.equal(compactRect.width, 100);
    const added = addSubviewCompositionMembers(original, [member(2, "top", 0)], "top");
    assert.equal(added.composition.members[1].xBp, before.x + before.width + original.layoutGapBp);
  });
}
