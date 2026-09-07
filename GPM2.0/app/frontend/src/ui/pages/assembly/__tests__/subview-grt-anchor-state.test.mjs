import test from "node:test";
import assert from "node:assert/strict";

import { buildGrtResultPlan } from "../grt-result-state.js";
import {
  buildSubviewGrtAnchorObjectId,
  buildSubviewGrtAnchorOriginId,
  buildSubviewGrtAnchorReferences,
  buildSubviewGrtAnchorScene,
  buildSubviewGrtBaselineKey,
  createSubviewManualAnchorFromGrt,
  findSubviewManualAnchorByGrtOrigin,
} from "../subview-grt-anchor-state.js";

function sourceSegment(id, assemblyCtgId, start, end, orientation = "+") {
  return {
    segmentId: id,
    type: "ctg",
    assemblyCtgId,
    assemblySourceStart: 1,
    assemblySourceEnd: 10_000,
    datasetName: "primary",
    ctgName: `ctg${assemblyCtgId}`,
    overallLen: 10_000,
    start: orientation === "-" ? end : start,
    end: orientation === "-" ? start : end,
    source: {
      dataset: "primary",
      contig: `ctg${assemblyCtgId}`,
      start,
      end,
      orientation,
    },
  };
}

function baseline(kind = "link") {
  return {
    mode: "segments",
    chrName: "Chr01",
    grtDisplayAvailable: true,
    segments: [
      sourceSegment("left", 11, 100, 1000, "+"),
      ...(kind === "gap" ? [{ segmentId: "gap", type: "gap", gapSizeBp: 250 }] : []),
      sourceSegment("right", 22, 2000, 3000, "+"),
    ],
  };
}

function assemblyWithBaseline(entry) {
  return {
    selectedChrName: "Chr01",
    finalPathByChr: { Chr01: { mode: "segments", chrName: "Chr01", segments: [] } },
    grtProjectView: { baselineFinalPathByChr: { Chr01: entry } },
  };
}

function referenceIdentity(entry) {
  const plan = buildGrtResultPlan(entry);
  const baselineKey = buildSubviewGrtBaselineKey("Chr01", plan);
  const originId = buildSubviewGrtAnchorOriginId("Chr01", baselineKey, plan.junctions[0]);
  return { baselineKey, originId, objectId: buildSubviewGrtAnchorObjectId(originId) };
}

function descriptor(reference, { sameLane = false } = {}) {
  return {
    top: {
      endpointKey: "role:primary:ctg:11",
      contigId: 11,
      cutBp: 1000,
      baseCutBp: 9001,
      lengthBp: 10_000,
      baseOrientation: "-",
      lane: "top",
      name: "ctg11",
      sourceRole: "primary",
    },
    bottom: {
      endpointKey: "role:support:ctg:22",
      contigId: 22,
      cutBp: 2000,
      baseCutBp: 2000,
      lengthBp: 10_000,
      baseOrientation: "+",
      lane: sameLane ? "top" : "bottom",
      name: "ctg22",
      sourceRole: "support",
    },
  };
}

test("GRT references come from the immutable baseline only when present in the scene", () => {
  const entry = baseline("gap");
  entry.displayEvidence = [{ evidenceId: "must-not-be-an-anchor" }];
  const assembly = assemblyWithBaseline(entry);
  const identity = referenceIdentity(entry);

  assert.deepEqual(buildSubviewGrtAnchorReferences(assembly), []);

  const references = buildSubviewGrtAnchorReferences(assembly, [{
    objectId: identity.objectId,
    kind: "grt",
    descriptor: descriptor(),
    topX: 10,
    bottomX: 20,
  }]);
  assert.equal(references.length, 1);
  assert.equal(references[0].connectionKind, "gap");
  assert.equal(references[0].gapSizeBp, 250);
  assert.equal(references[0].readOnly, true);
  assert.equal(references[0].canDelete, false);
  assert.equal(references[0].canCopy, true);
  assert.equal(references[0].applicability, "applied");
});

test("scene projection resolves exact IDs and applies base orientation plus local flip once", () => {
  const plan = buildGrtResultPlan(baseline());
  const scene = buildSubviewGrtAnchorScene({
    chrName: "Chr01",
    plan,
    entries: [
      {
        endpointKey: "role:primary:ctg:11",
        lane: "top",
        baseOrientation: "-",
        locallyFlipped: true,
        ctg: { assemblyCtgId: 11, lengthBp: 10_000, orient: "+" },
        rect: { x: 0, width: 100 },
        y: 20,
        height: 14,
      },
      {
        endpointKey: "role:support:ctg:22",
        lane: "bottom",
        baseOrientation: "+",
        locallyFlipped: false,
        ctg: { assemblyCtgId: 22, lengthBp: 10_000, orient: "+" },
        rect: { x: 50, width: 100 },
        y: 100,
        height: 14,
      },
    ],
  });

  assert.match(scene.markup, /data-subview-anchor-kind="grt"/);
  assert.match(scene.markup, /data-subview-anchor-top-base-cut-bp="9001"/);
  assert.match(scene.markup, /data-subview-anchor-top-cut-bp="1000"/);
  assert.match(scene.markup, /data-subview-anchor-bottom-base-cut-bp="2000"/);

  const unresolved = buildSubviewGrtAnchorScene({
    chrName: "Chr01",
    plan,
    entries: [{
      endpointKey: "same-name",
      lane: "top",
      name: "ctg11",
      ctg: { assemblyCtgId: 999, lengthBp: 10_000, orient: "+" },
      rect: { x: 0, width: 100 },
      y: 20,
      height: 14,
    }],
  });
  assert.equal(unresolved.markup, "");
});

test("cross-lane GRT objects copy once into persistent assembly-space user anchors", () => {
  const entry = baseline();
  const assembly = assemblyWithBaseline(entry);
  const raw = referenceIdentity(entry);
  const applied = buildSubviewGrtAnchorReferences(assembly, [{
    objectId: raw.objectId,
    kind: "grt",
    descriptor: descriptor(raw),
    topX: 10,
    bottomX: 20,
  }])[0];

  assert.equal(applied.canLocate, true);
  assert.equal(applied.canCopy, true);
  const copied = createSubviewManualAnchorFromGrt(applied);
  assert.equal(copied.ok, true);
  assert.equal(copied.anchor.coordinateSpace, "assembly");
  assert.equal(copied.anchor.origin.kind, "grt");
  assert.equal(copied.anchor.origin.connectionKind, "link");
  assert.deepEqual(copied.anchor.endpointA.cutBp, 9001);
  assert.equal(findSubviewManualAnchorByGrtOrigin([copied.anchor], raw.originId)?.manualAnchorId,
    copied.anchor.manualAnchorId);

  const sameLane = buildSubviewGrtAnchorReferences(assembly, [{
    objectId: raw.objectId,
    kind: "grt",
    descriptor: descriptor(raw, { sameLane: true }),
    topX: 10,
    bottomX: 20,
  }])[0];
  assert.equal(sameLane.canLocate, true);
  assert.equal(sameLane.canCopy, false);
  assert.equal(sameLane.reason, "grtSameLane");
  assert.equal(createSubviewManualAnchorFromGrt(sameLane).ok, false);

  const gapEntry = baseline("gap");
  const gapAssembly = assemblyWithBaseline(gapEntry);
  const before = structuredClone(gapAssembly);
  const rawGap = referenceIdentity(gapEntry);
  const appliedGap = buildSubviewGrtAnchorReferences(gapAssembly, [{
    objectId: rawGap.objectId,
    kind: "grt",
    descriptor: descriptor(rawGap),
    topX: 10,
    bottomX: 20,
  }])[0];
  const copiedGap = createSubviewManualAnchorFromGrt(appliedGap);
  assert.equal(copiedGap.anchor.origin.connectionKind, "gap");
  assert.equal(Object.hasOwn(copiedGap.anchor, "gapSizeBp"), false);
  assert.deepEqual(gapAssembly, before);
});
