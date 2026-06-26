import test from "node:test";
import assert from "node:assert/strict";

import {
  deriveSubviewContigFragments,
  deriveSubviewHitEdgeAnchors,
  normalizeSubviewActiveAnchors,
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
