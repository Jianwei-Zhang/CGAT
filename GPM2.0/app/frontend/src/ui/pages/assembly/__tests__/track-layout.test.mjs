import test from "node:test";
import assert from "node:assert/strict";
import {
  buildDualTrackModel,
  buildSingleTrackModel,
  normalizeCtgs,
  placeIntoLanes,
} from "../track-layout.js";
import { resolveTrackPrefs } from "../track-prefs.js";

test("normalizeCtgs sorts contigs by anchor start and lays out from zero with contiguous bp spans", () => {
  const result = normalizeCtgs([
    { assemblyCtgId: 2, name: "B", anchorStart: 999999, totalLength: 200 },
    { assemblyCtgId: 1, name: "A", anchorStart: 100, totalLength: 50 },
  ]);

  assert.deepEqual(
    result.map((item) => ({
      assemblyCtgId: item.assemblyCtgId,
      startBp: item.startBp,
      endBp: item.endBp,
      lengthBp: item.lengthBp,
    })),
    [
      { assemblyCtgId: 1, startBp: 0, endBp: 49, lengthBp: 50 },
      { assemblyCtgId: 2, startBp: 50, endBp: 249, lengthBp: 200 },
    ],
  );
});

test("normalizeCtgs keeps contiguous data coordinates for adjacent long contigs", () => {
  const result = normalizeCtgs([
    { assemblyCtgId: 1, name: "A", anchorStart: 10, totalLength: 10_000_000 },
    { assemblyCtgId: 2, name: "B", anchorStart: 20, totalLength: 10_000_000 },
  ]);

  assert.equal(result[0].startBp, 0);
  assert.equal(result[1].startBp, 10_000_000);
});

test("buildSingleTrackModel keeps a visible pixel gap between adjacent contigs on the same lane", () => {
  const model = buildSingleTrackModel({
    ctgs: [
      { assemblyCtgId: 1, anchorStart: 10, totalLength: 10_000_000, name: "A" },
      { assemblyCtgId: 2, anchorStart: 20, totalLength: 10_000_000, name: "B" },
    ],
    prefs: { viewSpanKb: 500, tickBp: 10_000, alignmentLength: 1_000 },
  });
  const lane0 = model.ctgs.filter((ctg) => ctg.laneIndex === 0);
  assert.equal(lane0.length, 2);
  const [first, second] = lane0;
  const visibleGapPx = second.x - (first.x + first.width);
  assert.ok(visibleGapPx >= 20, `expected visible gap >= 20px, got ${visibleGapPx}`);
});

test("buildSingleTrackModel force-separates dense short tail contigs instead of stacking them", () => {
  const model = buildSingleTrackModel({
    ctgs: [
      { assemblyCtgId: 1, anchorStart: 10, totalLength: 25_000_000, name: "A" },
      { assemblyCtgId: 2, anchorStart: 20, totalLength: 1_000, name: "B1" },
      { assemblyCtgId: 3, anchorStart: 30, totalLength: 1_000, name: "B2" },
      { assemblyCtgId: 4, anchorStart: 40, totalLength: 1_000, name: "B3" },
      { assemblyCtgId: 5, anchorStart: 50, totalLength: 1_000, name: "B4" },
    ],
    prefs: { viewSpanKb: 10000, tickBp: 10_000, alignmentLength: 1_000 },
  });

  const lane0 = model.ctgs
    .filter((ctg) => ctg.laneIndex === 0)
    .sort((left, right) => left.x - right.x);
  for (let index = 1; index < lane0.length; index += 1) {
    const previous = lane0[index - 1];
    const current = lane0[index];
    const visibleGapPx = current.x - (previous.x + previous.width);
    assert.ok(
      visibleGapPx >= 20,
      `expected visible gap >= 20px between ${previous.name} and ${current.name}, got ${visibleGapPx}`,
    );
  }
});

test("placeIntoLanes keeps non-overlapping contigs in the same lane", () => {
  const result = placeIntoLanes(
    [
      { assemblyCtgId: 1, startBp: 100, endBp: 299, lengthBp: 200 },
      { assemblyCtgId: 2, startBp: 250, endBp: 449, lengthBp: 200 },
      { assemblyCtgId: 3, startBp: 500, endBp: 649, lengthBp: 150 },
    ],
    25,
  );

  assert.deepEqual(
    result.map((item) => [item.assemblyCtgId, item.laneIndex]),
    [
      [1, 0],
      [2, 1],
      [3, 0],
    ],
  );
});

test("buildSingleTrackModel normalizes discrete prefs and stamps tick indices", () => {
  const prefs = resolveTrackPrefs({
    pixelUnit: 2600,
    tickLength: 75000,
    alignmentLength: 6500,
  });
  const model = buildSingleTrackModel({
    ctgs: [
      { assemblyCtgId: 1, anchorStart: 100, totalLength: 200, name: "A" },
      { assemblyCtgId: 2, anchorStart: 900, totalLength: 600, name: "B" },
    ],
    selectedCtgId: 2,
    prefs,
    windowStart: 0,
    windowEnd: 250000,
    innerWidth: 600,
  });

  assert.equal(model.viewSpanBp, 500000);
  assert.deepEqual(
    model.ticks.map((tick) => ({ bp: tick.bp, index: tick.index })),
    [
      { bp: 100000, index: 1 },
      { bp: 200000, index: 2 },
    ],
  );
  assert.ok(model.ctgs.every((item) => item.x >= 0 && item.width > 0));
  assert.equal(model.ctgs.find((item) => item.assemblyCtgId === 2)?.isSelected, true);
});

test("buildDualTrackModel returns aligned view window for primary and companion", () => {
  const model = buildDualTrackModel({
    primaryCtgs: [{ assemblyCtgId: 1, anchorStart: 1000, totalLength: 5000, name: "A" }],
    companionCtgs: [{ assemblyCtgId: 2, anchorStart: 1200, totalLength: 3000, name: "B" }],
    prefs: { viewSpanKb: 1000, tickBp: 10000, alignmentLength: 1000 },
  });

  assert.equal(model.primary.windowStart, model.companion.windowStart);
  assert.equal(model.primary.windowEnd, model.companion.windowEnd);
  assert.equal(model.primary.innerWidth, model.companion.innerWidth);
  assert.deepEqual(model.primary.ticks, model.companion.ticks);
  assert.ok(model.primary.ticks.length > 0);
});

test("buildDualTrackModel starts shared window at zero even when anchor starts are large", () => {
  const model = buildDualTrackModel({
    primaryCtgs: [{ assemblyCtgId: 1, anchorStart: 10000, totalLength: 500, name: "Primary" }],
    companionCtgs: [{ assemblyCtgId: 2, anchorStart: 12000, totalLength: 200, name: "Companion" }],
    prefs: { viewSpanKb: 500, tickBp: 10000, alignmentLength: 10000 },
  });

  assert.equal(model.windowStart, 0);
  assert.ok(model.companion.ctgs.every((ctg) => ctg.x >= 0));
});

test("buildSingleTrackModel ignores negative anchor values for x layout and keeps first ctg at origin", () => {
  const model = buildSingleTrackModel({
    ctgs: [
      { assemblyCtgId: 87, anchorStart: -331498, totalLength: 15938225, name: "Ctg87" },
      { assemblyCtgId: 88, anchorStart: 16765154, totalLength: 15179766, name: "Ctg88" },
    ],
    selectedCtgId: 87,
    prefs: { viewSpanKb: 1000, tickBp: 10000, alignmentLength: 1000 },
  });

  const ctg87 = model.ctgs.find((item) => item.assemblyCtgId === 87);
  assert.equal(model.windowStart, 0);
  assert.equal(ctg87?.startBp, 0);
  assert.ok(ctg87 && ctg87.x >= 0);
});
