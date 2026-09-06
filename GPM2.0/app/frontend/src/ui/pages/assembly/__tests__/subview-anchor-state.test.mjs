import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSubviewAnchorStateKey,
  createOffsetSubviewManualAnchor,
  deriveSubviewAnchorOffsetSuggestion,
  deriveSubviewContigFragments,
  deriveSubviewHitEdgeAnchors,
  normalizeSubviewManualAnchors,
  normalizeSubviewActiveAnchors,
  resolveSubviewAnchorStateForSummary,
  resolveSubviewManualAnchorDisplayCut,
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

test("active evidence anchors preserve a normalized endpoint descriptor for unavailable evidence", () => {
  const descriptor = {
    top: {
      endpointKey: "top-1", contigId: 1, cutBp: 100, lengthBp: 1000,
      name: "ctg_alpha", sourceRole: "primary", sourceKind: "mother", sourceName: "hifiasm",
    },
    bottom: {
      endpointKey: "bottom-2", contigId: 2, cutBp: 200,
      name: "ctg_beta", sourceRole: "support", sourceKind: "mother", sourceName: "flye",
    },
  };
  const anchors = toggleSubviewAnchorEdge([], { hitKey: "hit-1", edge: "left", descriptor });

  assert.deepEqual(anchors, [{ hitKey: "hit-1", edge: "left", descriptor }]);
  assert.deepEqual(normalizeSubviewActiveAnchors([...anchors, { hitKey: "hit-1", edge: "left" }]), anchors);
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
    topName: "ctg_top",
    bottomName: "ctg_bottom",
    topSourceLabel: "GRT · primary",
    bottomSourceLabel: "User track",
    topSourceRole: "primary",
    bottomSourceRole: "support",
    topSourceKind: "mother",
    bottomSourceKind: "mother",
    topSourceName: "hifiasm",
    bottomSourceName: "flye",
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
  assert.deepEqual(
    normalizeSubviewManualAnchors([created.anchor]).map((anchor) => [
      anchor.endpointA.name,
      anchor.endpointA.sourceRole,
      anchor.endpointA.sourceName,
      anchor.endpointB.name,
      anchor.endpointB.sourceRole,
      anchor.endpointB.sourceName,
    ]),
    [["ctg_bottom", "support", "flye", "ctg_top", "primary", "hifiasm"]],
  );

  const rejected = createOffsetSubviewManualAnchor(sourceEdge, {
    direction: "right",
    offsetBp: 400,
  });
  assert.equal(rejected.ok, false);
  assert.equal(rejected.reason, "out-of-range");
});

test("assembly-space manual anchors preserve their GRT origin and convert local flip once", () => {
  const [anchor] = normalizeSubviewManualAnchors([{
    manualAnchorId: "grt-copy:one",
    coordinateSpace: "assembly",
    origin: {
      kind: "grt",
      originId: "one",
      baselineKey: "baseline",
      chrName: "Chr01",
      connectionKind: "gap",
      endpointSources: [{ assemblyCtgId: 1, sourcePosition: 300, pathOrder: 0 }],
    },
    endpointA: { endpointKey: "top", contigId: 1, cutBp: 901, lengthBp: 1000, baseOrientation: "-" },
    endpointB: { endpointKey: "bottom", contigId: 2, cutBp: 200, lengthBp: 1000, baseOrientation: "+" },
  }]);

  assert.equal(anchor.coordinateSpace, "assembly");
  assert.equal(anchor.origin.originId, "one");
  assert.equal(anchor.origin.connectionKind, "gap");
  const reversedEndpoint = [anchor.endpointA, anchor.endpointB]
    .find((endpoint) => endpoint.endpointKey === "top");
  assert.equal(reversedEndpoint.baseOrientation, "-");
  assert.equal(resolveSubviewManualAnchorDisplayCut(anchor, reversedEndpoint, {
    lengthBp: 1000, locallyFlipped: true,
  }), 100);
  assert.equal(resolveSubviewManualAnchorDisplayCut(anchor, reversedEndpoint, {
    lengthBp: 1000, locallyFlipped: false,
  }), 901);
  assert.equal(resolveSubviewManualAnchorDisplayCut(
    { ...anchor, coordinateSpace: "display" }, reversedEndpoint,
    { lengthBp: 1000, locallyFlipped: true },
  ), 901);
});

function createCrossedActiveAnchorPair() {
  const leftAnchor = {
    kind: "evidence",
    active: true,
    hitKey: "hit-left",
    edge: "right",
    topEndpointKey: "top-ctg-10",
    bottomEndpointKey: "bottom-ctg-30",
    topContigId: 10,
    bottomContigId: 30,
    topCutBp: 400,
    bottomCutBp: 500,
    topLengthBp: 1000,
    bottomLengthBp: 1000,
    topX: 60,
    bottomX: 20,
  };
  const rightAnchor = {
    kind: "evidence",
    active: true,
    hitKey: "hit-right",
    edge: "left",
    topEndpointKey: "top-ctg-10",
    bottomEndpointKey: "bottom-ctg-31",
    topContigId: 10,
    bottomContigId: 31,
    topCutBp: 200,
    bottomCutBp: 700,
    topLengthBp: 1000,
    bottomLengthBp: 1000,
    topX: 40,
    bottomX: 80,
  };
  return { leftAnchor, rightAnchor };
}

test("deriveSubviewAnchorOffsetSuggestion uses the unique crossed pair and continuous track interval", () => {
  const { leftAnchor, rightAnchor } = createCrossedActiveAnchorPair();
  const activeOriginalEdges = [leftAnchor, rightAnchor];

  assert.deepEqual(
    deriveSubviewAnchorOffsetSuggestion(leftAnchor, activeOriginalEdges),
    {
      ok: true,
      reason: "",
      direction: "left",
      offsetBp: 200,
      offsetPrimarySlot: "top",
      partnerHitKey: "hit-right",
      partnerEdge: "left",
      validationReason: "",
    },
  );
  assert.deepEqual(
    deriveSubviewAnchorOffsetSuggestion(rightAnchor, activeOriginalEdges),
    {
      ok: true,
      reason: "",
      direction: "right",
      offsetBp: 200,
      offsetPrimarySlot: "top",
      partnerHitKey: "hit-left",
      partnerEdge: "right",
      validationReason: "",
    },
  );
});

test("deriveSubviewAnchorOffsetSuggestion keeps direction and bp after top and bottom swap", () => {
  const { leftAnchor, rightAnchor } = createCrossedActiveAnchorPair();
  const swapSlots = (edge) => ({
    ...edge,
    topEndpointKey: edge.bottomEndpointKey,
    bottomEndpointKey: edge.topEndpointKey,
    topContigId: edge.bottomContigId,
    bottomContigId: edge.topContigId,
    topCutBp: edge.bottomCutBp,
    bottomCutBp: edge.topCutBp,
    topLengthBp: edge.bottomLengthBp,
    bottomLengthBp: edge.topLengthBp,
    topX: edge.bottomX,
    bottomX: edge.topX,
  });
  const swappedLeft = swapSlots(leftAnchor);
  const swappedRight = swapSlots(rightAnchor);

  const suggestion = deriveSubviewAnchorOffsetSuggestion(
    swappedLeft,
    [swappedLeft, swappedRight],
  );
  assert.equal(suggestion.ok, true);
  assert.equal(suggestion.direction, "left");
  assert.equal(suggestion.offsetBp, 200);
  assert.equal(suggestion.offsetPrimarySlot, "bottom");
});

test("deriveSubviewAnchorOffsetSuggestion is role agnostic for two support tracks and zoom scaling", () => {
  const { leftAnchor, rightAnchor } = createCrossedActiveAnchorPair();
  const projectDisplayX = (edge) => ({
    ...edge,
    topTrackRole: "support",
    bottomTrackRole: "support",
    topX: (edge.topX * 2.5) + 120,
    bottomX: (edge.bottomX * 2.5) + 120,
  });
  const projectedLeft = projectDisplayX(leftAnchor);
  const projectedRight = projectDisplayX(rightAnchor);

  const suggestion = deriveSubviewAnchorOffsetSuggestion(
    projectedRight,
    [projectedLeft, projectedRight],
  );
  assert.equal(suggestion.ok, true);
  assert.equal(suggestion.direction, "right");
  assert.equal(suggestion.offsetBp, 200);
  assert.equal(suggestion.offsetPrimarySlot, "top");
});

test("deriveSubviewAnchorOffsetSuggestion leaves ambiguous or ineligible pairs without a default", () => {
  const { leftAnchor, rightAnchor } = createCrossedActiveAnchorPair();
  const thirdCrossing = {
    ...rightAnchor,
    hitKey: "hit-third",
    edge: "right",
    topX: 30,
    bottomX: 90,
  };
  assert.equal(
    deriveSubviewAnchorOffsetSuggestion(leftAnchor, [leftAnchor]).reason,
    "no-crossing",
  );
  assert.equal(
    deriveSubviewAnchorOffsetSuggestion(
      leftAnchor,
      [leftAnchor, { ...rightAnchor, active: false }],
    ).reason,
    "no-crossing",
  );
  assert.equal(
    deriveSubviewAnchorOffsetSuggestion(
      leftAnchor,
      [leftAnchor, rightAnchor, thirdCrossing],
    ).reason,
    "ambiguous-crossing",
  );
  assert.equal(
    deriveSubviewAnchorOffsetSuggestion(
      leftAnchor,
      [leftAnchor, { ...rightAnchor, bottomEndpointKey: leftAnchor.bottomEndpointKey }],
    ).reason,
    "ambiguous-offset-primary",
  );
  assert.equal(
    deriveSubviewAnchorOffsetSuggestion(
      leftAnchor,
      [
        leftAnchor,
        {
          ...rightAnchor,
          topEndpointKey: "top-ctg-11",
          topContigId: 11,
        },
      ],
    ).reason,
    "ambiguous-offset-primary",
  );
  assert.equal(
    deriveSubviewAnchorOffsetSuggestion(
      leftAnchor,
      [
        leftAnchor,
        {
          ...rightAnchor,
          kind: "manual",
          manualAnchorId: "manual-1",
        },
      ],
    ).reason,
    "no-crossing",
  );
});

test("deriveSubviewAnchorOffsetSuggestion preserves an out-of-range automatic value for editing", () => {
  const { leftAnchor, rightAnchor } = createCrossedActiveAnchorPair();
  const outOfRangeLeft = {
    ...leftAnchor,
    bottomCutBp: 100,
  };
  const suggestion = deriveSubviewAnchorOffsetSuggestion(
    outOfRangeLeft,
    [outOfRangeLeft, rightAnchor],
  );

  assert.equal(suggestion.ok, true);
  assert.equal(suggestion.direction, "left");
  assert.equal(suggestion.offsetBp, 200);
  assert.equal(suggestion.validationReason, "out-of-range");
});
