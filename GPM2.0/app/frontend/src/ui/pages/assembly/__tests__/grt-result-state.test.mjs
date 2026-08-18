import test from "node:test";
import assert from "node:assert/strict";

import {
  buildGrtResultPlan,
  projectGrtSourcePositionToCtg,
  resolveGrtResultContext,
  setGrtResultDisplayEnabled,
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
    Chr01: { main: true, subview: true },
    Chr02: { main: true, subview: false },
  });
});

test("only exposes schema 2, unphased, semantically unchanged GRT results", () => {
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
  });

  assembly.finalPathByChr.Chr01.segments[0].source.orientation = "-";
  assembly.finalPathByChr.Chr01.segments[0].orient = "-";
  assert.equal(resolveGrtResultContext(assembly).available, false);

  assembly.finalPathByChr.Chr01 = structuredClone(baseline);
  assembly.grtProjectView.recipe.finalPathSchemaVersion = "1";
  assert.equal(resolveGrtResultContext(assembly).available, false);
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
  assert.match(sameCtgScene.junctionMarkup, /<path class="grt-result-junction"/);
});
