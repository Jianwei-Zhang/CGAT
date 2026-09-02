import test from "node:test";
import assert from "node:assert/strict";

import {
  buildGrtResultPlan,
  projectGrtSourcePositionToCtg,
  resolveGrtResultContext,
  setGrtResultDisplayEnabled,
  setGrtResultLayerEnabled,
} from "../grt-result-state.js";
import { buildGrtResultScene } from "../grt-result-render.js";

function sourceSegment(id, start, end, orientation = "+", assemblyCtgId = 11) {
  return {
    segmentId: id,
    type: "ctg",
    assemblyCtgId,
    assemblySourceStart: 1,
    assemblySourceEnd: 10_000,
    datasetName: "primary",
    ctgName: "ctg1",
    overallLen: 10_000,
    start: orientation === "-" ? end : start,
    end: orientation === "-" ? start : end,
    source: { dataset: "primary", contig: "ctg1", start, end, orientation },
  };
}

function entry(segments) {
  return {
    mode: "segments",
    chrName: "Chr01",
    grtDisplayAvailable: true,
    segments,
  };
}

test("keeps independent per-chromosome main and Subview switches", () => {
  const mainOn = setGrtResultDisplayEnabled({}, "Chr01", "main", true);
  const bothOn = setGrtResultDisplayEnabled(mainOn, "Chr01", "subview", true);
  const otherChr = setGrtResultDisplayEnabled(bothOn, "Chr02", "main", true);

  assert.deepEqual(otherChr, {
    Chr01: {
      main: true,
      subview: true,
      mainLayers: { resultPath: true, alignmentEvidence: true },
      subviewLayers: { resultPath: true, alignmentEvidence: true },
    },
    Chr02: {
      main: true,
      subview: false,
      mainLayers: { resultPath: true, alignmentEvidence: true },
      subviewLayers: { resultPath: true, alignmentEvidence: true },
    },
  });
});

test("keeps main and Subview layer selections independent and defaults legacy state on", () => {
  const mainEvidenceOff = setGrtResultLayerEnabled(
    { Chr01: { main: true, subview: true } },
    "Chr01",
    "main",
    "alignmentEvidence",
    false,
  );
  const subviewPathOff = setGrtResultLayerEnabled(
    mainEvidenceOff,
    "Chr01",
    "subview",
    "resultPath",
    false,
  );

  assert.deepEqual(subviewPathOff.Chr01.mainLayers, {
    resultPath: true,
    alignmentEvidence: false,
  });
  assert.deepEqual(subviewPathOff.Chr01.subviewLayers, {
    resultPath: false,
    alignmentEvidence: true,
  });
  assert.equal(subviewPathOff.Chr01.main, true);
  assert.equal(subviewPathOff.Chr01.subview, true);
});

test("only exposes display schemas, unphased, semantically unchanged GRT results", () => {
  const baseline = entry([sourceSegment("a", 1, 1000)]);
  const assembly = {
    selectedChrName: "Chr01",
    isChrPhased: false,
    finalPathByChr: { Chr01: structuredClone(baseline) },
    grtProjectView: {
      recipe: { finalPathSchemaVersion: "2" },
      baselineFinalPathByChr: { Chr01: baseline },
    },
    grtResultDisplayByChr: { Chr01: { main: true, subview: true } },
  };

  assert.deepEqual(resolveGrtResultContext(assembly), {
    chrName: "Chr01",
    baselineEntry: baseline,
    currentEntry: assembly.finalPathByChr.Chr01,
    available: true,
    mainEnabled: true,
    subviewEnabled: true,
    mainLayers: { resultPath: true, alignmentEvidence: true },
    subviewLayers: { resultPath: true, alignmentEvidence: true },
  });

  assembly.grtProjectView.recipe.finalPathSchemaVersion = "3";
  assert.equal(resolveGrtResultContext(assembly).available, true);

  assembly.finalPathByChr.Chr01.segments[0].source.orientation = "-";
  assembly.finalPathByChr.Chr01.segments[0].orient = "-";
  assert.equal(resolveGrtResultContext(assembly).available, false);

  assembly.finalPathByChr.Chr01 = structuredClone(baseline);
  assembly.grtProjectView.recipe.finalPathSchemaVersion = "1";
  assert.equal(resolveGrtResultContext(assembly).available, false);
});

test("renders accepted MUMmer and local minimap2 evidence as distinct passive bands", () => {
  const baseline = entry([
    sourceSegment("donor", 1, 1000, "+", 11),
    sourceSegment("primary", 1, 1000, "+", 22),
  ]);
  baseline.displayEvidence = [
    {
      evidenceId: "mummer-left",
      tool: "mummer",
      role: "left_anchor",
      association: "supporting_precursor",
      alignedLength: 501,
      identity: 0.9989,
      mapq: null,
      source: {
        assemblyCtgId: 11,
        assemblySourceStart: 1,
        assemblySourceEnd: 10_000,
        start: 100,
        end: 600,
        orientation: "+",
      },
      target: {
        assemblyCtgId: 22,
        assemblySourceStart: 1,
        assemblySourceEnd: 10_000,
        start: 200,
        end: 700,
        orientation: "+",
      },
    },
    {
      evidenceId: "minimap-right",
      tool: "minimap2",
      role: "right_anchor",
      association: "accepted",
      alignedLength: 401,
      identity: 0.997,
      mapq: 60,
      source: {
        assemblyCtgId: 11,
        assemblySourceStart: 1,
        assemblySourceEnd: 10_000,
        start: 700,
        end: 1100,
        orientation: "+",
      },
      target: {
        assemblyCtgId: 22,
        assemblySourceStart: 1,
        assemblySourceEnd: 10_000,
        start: 800,
        end: 1200,
        orientation: "+",
      },
    },
  ];
  const scene = buildGrtResultScene({
    plan: buildGrtResultPlan(baseline),
    entries: [
      { key: "top", ctg: { assemblyCtgId: 11, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 20, height: 14 },
      { key: "bottom", ctg: { assemblyCtgId: 22, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 100, height: 14 },
    ],
  });

  assert.equal(scene.hasVisibleJunction, true);
  assert.match(scene.junctionMarkup, /class="grt-display-evidence-band is-mummer is-supporting-precursor"/);
  assert.match(scene.junctionMarkup, /data-grt-display-evidence="mummer-left"/);
  assert.match(scene.junctionMarkup, /data-grt-display-evidence-source-entry-key="top"/);
  assert.match(scene.junctionMarkup, /data-grt-display-evidence-target-entry-key="bottom"/);
  assert.match(scene.junctionMarkup, /class="grt-display-evidence-band is-minimap2"/);
  assert.match(scene.junctionMarkup, /MAPQ 60/);

  const pathOnlyScene = buildGrtResultScene({
    plan: buildGrtResultPlan(baseline),
    entries: [
      { key: "top", ctg: { assemblyCtgId: 11, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 20, height: 14 },
      { key: "bottom", ctg: { assemblyCtgId: 22, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 100, height: 14 },
    ],
    layers: { resultPath: true, alignmentEvidence: false },
  });
  assert.doesNotMatch(pathOnlyScene.junctionMarkup, /data-grt-display-evidence=/);
  assert.equal(pathOnlyScene.overlaysByKey.size, 2);

  const evidenceOnlyScene = buildGrtResultScene({
    plan: buildGrtResultPlan(baseline),
    entries: [
      { key: "top", ctg: { assemblyCtgId: 11, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 20, height: 14 },
      { key: "bottom", ctg: { assemblyCtgId: 22, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 100, height: 14 },
    ],
    layers: { resultPath: false, alignmentEvidence: true },
  });
  assert.match(evidenceOnlyScene.junctionMarkup, /data-grt-display-evidence=/);
  assert.equal(evidenceOnlyScene.overlaysByKey.size, 0);
});

test("merges true continuity but keeps noncontiguous source regions and link endpoints", () => {
  const plan = buildGrtResultPlan(entry([
    sourceSegment("a", 1, 1000),
    sourceSegment("b", 1001, 2000),
    sourceSegment("c", 3000, 4000),
  ]));

  assert.deepEqual(
    plan.visualIntervals.map((interval) => [interval.sourceStart, interval.sourceEnd]),
    [[1, 2000], [3000, 4000]],
  );
  assert.equal(plan.junctions.length, 1);
  assert.equal(plan.junctions[0].kind, "link");
  assert.equal(plan.junctions[0].left.exitSourcePosition, 2000);
  assert.equal(plan.junctions[0].right.entrySourcePosition, 3000);
});

test("uses reverse-strand continuity and retains real Final Path gaps", () => {
  const plan = buildGrtResultPlan(entry([
    sourceSegment("a", 3001, 4000, "-"),
    sourceSegment("b", 2001, 3000, "-"),
    { segmentId: "gap", type: "gap", gapSizeBp: 250 },
    sourceSegment("c", 1, 1000, "-"),
  ]));

  assert.deepEqual(
    plan.visualIntervals.map((interval) => [interval.sourceStart, interval.sourceEnd]),
    [[1, 1000], [2001, 4000]],
  );
  assert.equal(plan.junctions.length, 1);
  assert.deepEqual(
    { kind: plan.junctions[0].kind, gapSizeBp: plan.junctions[0].gapSizeBp },
    { kind: "gap", gapSizeBp: 250 },
  );
});

test("counts repeated overlapping semantic occurrences and projects source positions by ctg orientation", () => {
  const plan = buildGrtResultPlan(entry([
    sourceSegment("a", 1, 1000),
    sourceSegment("b", 500, 1200),
  ]));

  assert.equal(plan.visualIntervals.length, 1);
  assert.equal(plan.visualIntervals[0].occurrences.length, 2);
  assert.equal(projectGrtSourcePositionToCtg(1000, plan.intervals[0], "+"), 1000);
  assert.equal(projectGrtSourcePositionToCtg(1000, plan.intervals[0], "-"), 9001);
});

test("renders cross-lane links as lines, same-ctg links as arcs, and gap labels truthfully", () => {
  const crossPlan = buildGrtResultPlan(entry([
    sourceSegment("a", 1, 1000, "+", 11),
    { segmentId: "gap", type: "gap", gapSizeBp: 300 },
    sourceSegment("b", 1, 1000, "+", 22),
  ]));
  const crossScene = buildGrtResultScene({
    plan: crossPlan,
    entries: [
      { key: "top", ctg: { assemblyCtgId: 11, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 20, height: 14 },
      { key: "bottom", ctg: { assemblyCtgId: 22, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 100, height: 14 },
    ],
  });
  assert.equal(crossScene.hasVisibleJunction, true);
  assert.match(crossScene.junctionMarkup, /<line class="grt-result-junction is-gap"/);
  assert.match(crossScene.junctionMarkup, /data-grt-result-junction-left-entry-key="top"/);
  assert.match(crossScene.junctionMarkup, /data-grt-result-junction-right-entry-key="bottom"/);
  assert.match(crossScene.junctionMarkup, /data-grt-result-junction-line="1"/);
  assert.match(crossScene.junctionMarkup, /GRT gap · 300 bp/);

  const sameCtgPlan = buildGrtResultPlan(entry([
    sourceSegment("a", 1, 1000),
    sourceSegment("b", 3000, 4000),
  ]));
  const sameCtgScene = buildGrtResultScene({
    plan: sameCtgPlan,
    entries: [
      { key: "only", ctg: { assemblyCtgId: 11, lengthBp: 10_000, orient: "+" }, rect: { x: 0, width: 1000 }, y: 40, height: 14 },
    ],
  });
  assert.equal(sameCtgScene.hasVisibleJunction, true);
  assert.match(sameCtgScene.junctionMarkup, /data-grt-result-junction-left-entry-key="only"/);
  assert.match(sameCtgScene.junctionMarkup, /data-grt-result-junction-right-entry-key="only"/);
  assert.match(sameCtgScene.junctionMarkup, /<path class="grt-result-junction"/);
});
