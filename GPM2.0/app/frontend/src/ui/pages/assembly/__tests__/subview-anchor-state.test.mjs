import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSubviewAnchorStateKey,
  createOffsetSubviewManualAnchor,
  deriveSubviewContigFragments,
  deriveSubviewHitEdgeAnchors,
  normalizeSubviewManualAnchors,
  normalizeSubviewActiveAnchors,
  resolveSubviewAnchorStateForSummary,
  setSubviewAnchorStateForSummary,
  toggleSubviewAnchorEdge,
} from "../subview-anchor-state.js";

test("toggleSubviewAnchorEdge keeps left and right edges independent", () => {
  const once = toggleSubviewAnchorEdge([], { hitKey: "hit-1", edge: "left" });
  const twice = toggleSubviewAnchorEdge(once, { hitKey: "hit-1", edge: "right" });

  assert.deepEqual(once, [{ hitKey: "hit-1", edge: "left" }]);
  assert.deepEqual(twice, [
    { hitKey: "hit-1", edge: "left" },
    { hitKey: "hit-1", edge: "right" },
  ]);
});

test("normalizeSubviewActiveAnchors removes invalid and duplicate edge entries", () => {
  assert.deepEqual(
    normalizeSubviewActiveAnchors([
      { hitKey: "hit-1", edge: "left" },
      { hitKey: "hit-1", edge: "left" },
      { hitKey: "hit-1", edge: "right" },
      { hitKey: "", edge: "left" },
      null,
    ]),
    [
      { hitKey: "hit-1", edge: "left" },
      { hitKey: "hit-1", edge: "right" },
    ],
  );
});

test("deriveSubviewContigFragments splits one contig by multiple anchor positions and drops zero-length intervals", () => {
  const fragments = deriveSubviewContigFragments({
    contig: { assemblyCtgId: 8, role: "primary", lengthBp: 1000, orient: "+" },
    anchorCuts: [250, 250, 700],
  });

  assert.deepEqual(
    fragments.map((fragment) => [fragment.start, fragment.end]),
    [
      [1, 249],
      [250, 699],
      [700, 1000],
    ],
  );
});

test("deriveSubviewHitEdgeAnchors maps the same visual edge line to top and bottom contig coordinates independently", () => {
  const anchors = deriveSubviewHitEdgeAnchors({
    hitKey: "hit-9",
    top: { contigId: 30, start: 101, end: 180, xLeft: 400, xRight: 480 },
    bottom: { contigId: 8, start: 501, end: 620, xLeft: 420, xRight: 500 },
  });

  assert.deepEqual(anchors[0], {
    hitKey: "hit-9",
    edge: "left",
    topContigId: 30,
    topCutBp: 101,
    bottomContigId: 8,
    bottomCutBp: 501,
  });
  assert.deepEqual(anchors[1], {
    hitKey: "hit-9",
    edge: "right",
    topContigId: 30,
    topCutBp: 180,
    bottomContigId: 8,
    bottomCutBp: 620,
  });
});

test("buildSubviewAnchorStateKey is insensitive to top and bottom order", () => {
  const left = {
    mode: "2-contig",
    top: { role: "support", contigId: 30, datasetId: 22 },
    bottom: { role: "primary", contigId: 8 },
  };
  const right = {
    mode: "2-contig",
    top: { role: "primary", contigId: 8 },
    bottom: { role: "support", contigId: 30, datasetId: 22 },
  };

  assert.equal(
    buildSubviewAnchorStateKey(left, "Chr05"),
    buildSubviewAnchorStateKey(right, "Chr05"),
  );
});

test("set and resolve subview anchor state by summary use the order-insensitive key", () => {
  const first = {
    mode: "track-pair",
    topTrack: { role: "support", source: "mother", datasetId: 22 },
    bottomTrack: { role: "primary" },
  };
  const swapped = {
    mode: "track-pair",
    topTrack: { role: "primary" },
    bottomTrack: { role: "support", source: "mother", datasetId: 22 },
  };
  const stateByKey = setSubviewAnchorStateForSummary({}, first, "Chr05", {
    activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
    manualAnchors: [],
  });

  assert.deepEqual(resolveSubviewAnchorStateForSummary(stateByKey, swapped, "Chr05"), {
    activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
    manualAnchors: [],
  });
});

test("createOffsetSubviewManualAnchor shifts both endpoints and rejects out-of-range copies", () => {
  const sourceEdge = {
    hitKey: "hit-1",
    edge: "left",
    topEndpointKey: "top",
    bottomEndpointKey: "bottom",
    topContigId: 30,
    bottomContigId: 8,
    topCutBp: 100,
    bottomCutBp: 200,
    topLengthBp: 1000,
    bottomLengthBp: 500,
  };

  const created = createOffsetSubviewManualAnchor(sourceEdge, {
    direction: "right",
    offsetBp: 50,
  });

  assert.equal(created.ok, true);
  assert.deepEqual(
    normalizeSubviewManualAnchors([created.anchor]).map((anchor) => [
      anchor.endpointA.cutBp,
      anchor.endpointB.cutBp,
    ]),
    [[200 + 50, 100 + 50]],
  );

  const rejected = createOffsetSubviewManualAnchor(sourceEdge, {
    direction: "right",
    offsetBp: 400,
  });
  assert.equal(rejected.ok, false);
  assert.equal(rejected.reason, "out-of-range");
});
