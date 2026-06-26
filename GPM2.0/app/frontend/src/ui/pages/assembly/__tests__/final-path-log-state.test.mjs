import test from "node:test";
import assert from "node:assert/strict";

import {
  buildFinalPathLogModel,
  buildFinalPathLogTsvText,
  canUseFinalPathLog,
} from "../final-path-log-state.js";

function createFinalPathEntry() {
  return {
    mode: "segments",
    chrName: "Chr01",
    segments: [
      {
        segmentId: "seg-1",
        type: "ctg",
        assemblyCtgId: 1,
        datasetName: "hifiasm",
        ctgName: "ptg000001l",
        originId: "ptg000001l",
        overallLen: 1000,
        start: 101,
        end: 400,
      },
      {
        segmentId: "seg-2",
        type: "gap",
        gapSizeBp: 100,
      },
      {
        segmentId: "seg-3",
        type: "ctg",
        assemblyCtgId: 3,
        datasetName: "flye",
        ctgName: "flye_ctg_3",
        originId: "flye_ctg_3",
        overallLen: 900,
        start: 900,
        end: 601,
      },
      {
        segmentId: "seg-4",
        type: "ctg",
        assemblyCtgId: 2,
        datasetName: "hifiasm",
        ctgName: "ptg000002l",
        originId: "ptg000002l",
        overallLen: 2000,
        start: 1,
        end: 500,
      },
    ],
  };
}

test("buildFinalPathLogModel counts primary appended segment length and hidden-only full length", () => {
  const model = buildFinalPathLogModel({
    chrName: "Chr01",
    finalPathEntry: createFinalPathEntry(),
    finalPathByChr: {
      Chr01: createFinalPathEntry(),
      Chr02: {
        mode: "segments",
        chrName: "Chr02",
        segments: [
          {
            segmentId: "other-1",
            type: "ctg",
            assemblyCtgId: 2,
            datasetName: "hifiasm",
            ctgName: "ptg000002l",
            originId: "ptg000002l",
            overallLen: 2000,
            start: 1,
            end: 2000,
          },
        ],
      },
    },
    primaryCtgs: [
      { assemblyCtgId: 1, name: "ptg000001l", originId: "ptg000001l", totalLength: 1000 },
      { assemblyCtgId: 2, name: "ptg000002l", originId: "ptg000002l", totalLength: 2000 },
      { assemblyCtgId: 4, name: "ptg000004l", originId: "ptg000004l", totalLength: 4000 },
    ],
    hiddenPrimaryCtgIds: [2, 4],
    primaryDatasetName: "hifiasm",
  });

  assert.equal(model.primaryCount.used, 3);
  assert.equal(model.primaryCount.total, 3);
  assert.equal(model.primaryCount.appended, 2);
  assert.equal(model.primaryCount.hidden, 1);
  assert.equal(model.primaryLength.usedBp, 4800);
  assert.equal(model.primaryLength.appendedBp, 800);
  assert.equal(model.primaryLength.hiddenBp, 4000);
  assert.equal(model.primaryLength.totalBp, 7000);
  assert.deepEqual(
    model.primaryCount.appendedRows.map((row) => [row.ctgName, row.finalPathStart, row.finalPathEnd, row.lengthBp]),
    [
      ["ptg000001l", 1, 300, 300],
      ["ptg000002l", 701, 1200, 500],
    ],
  );
  assert.deepEqual(
    model.primaryCount.hiddenRows.map((row) => [row.ctgName, row.counted, row.countedLengthBp]),
    [
      ["ptg000002l", false, 0],
      ["ptg000004l", true, 4000],
    ],
  );
  assert.deepEqual(
    model.supportRows.map((row) => [row.datasetName, row.ctgName, row.finalPathStart, row.finalPathEnd]),
    [["flye", "flye_ctg_3", 401, 700]],
  );
  assert.deepEqual(
    model.otherChrPrimaryRows.map((row) => [row.ctgName, row.finalPathStart, row.finalPathEnd, row.usedByChrNames]),
    [["ptg000002l", 701, 1200, ["Chr02"]]],
  );
});

test("buildFinalPathLogTsvText exports summary and non-primary detail sections", () => {
  const model = buildFinalPathLogModel({
    chrName: "Chr01",
    finalPathEntry: createFinalPathEntry(),
    primaryCtgs: [
      { assemblyCtgId: 1, name: "ptg000001l", originId: "ptg000001l", totalLength: 1000 },
      { assemblyCtgId: 2, name: "ptg000002l", originId: "ptg000002l", totalLength: 2000 },
    ],
    hiddenPrimaryCtgIds: [],
    primaryDatasetName: "hifiasm",
  });
  const text = buildFinalPathLogTsvText(model);
  const lines = text.trimEnd().split("\n");

  assert.match(lines[0], /^primary_ctg_count\thifiasm\t\t\t\t\t\t\t2\/2$/);
  assert.match(lines[1], /^primary_ctg_length\thifiasm\t\t\t\t\t\t\t800\/3000$/);
  assert.equal(lines[2], "section\tdataset\tctg\torigin_id\tstart\tend\tlength_bp\tused_by_chr\tcounted");
  assert.match(text, /primary_ctg_count\thifiasm\t\t\t\t\t\t\t2\/2/);
  assert.match(text, /primary_ctg_length\thifiasm\t\t\t\t\t\t\t800\/3000/);
  assert.doesNotMatch(text, /primary_appended/);
  assert.doesNotMatch(text, /primary_hidden/);
  assert.match(text, /support\tflye\tflye_ctg_3\tflye_ctg_3\t401\t700\t300\t\ttrue/);
});

test("buildFinalPathLogTsvText omits detail header when no detail rows exist", () => {
  const text = buildFinalPathLogTsvText(buildFinalPathLogModel({
    chrName: "Chr01",
    finalPathEntry: {
      mode: "segments",
      chrName: "Chr01",
      segments: [
        {
          segmentId: "seg-1",
          type: "ctg",
          assemblyCtgId: 1,
          datasetName: "hifiasm",
          ctgName: "ptg000001l",
          originId: "ptg000001l",
          overallLen: 1000,
          start: 1,
          end: 1000,
        },
      ],
    },
    primaryCtgs: [
      { assemblyCtgId: 1, name: "ptg000001l", originId: "ptg000001l", totalLength: 1000 },
    ],
    hiddenPrimaryCtgIds: [],
    primaryDatasetName: "hifiasm",
  }));

  assert.deepEqual(text.trimEnd().split("\n"), [
    "primary_ctg_count\thifiasm\t\t\t\t\t\t\t1/1",
    "primary_ctg_length\thifiasm\t\t\t\t\t\t\t1000/1000",
  ]);
});

test("canUseFinalPathLog returns false when final path contains reference segments", () => {
  assert.equal(canUseFinalPathLog(createFinalPathEntry()), true);
  assert.equal(
    canUseFinalPathLog({
      mode: "segments",
      chrName: "Chr01",
      segments: [
        {
          segmentId: "ref-1",
          type: "ctg",
          sourceKind: "ref_segment",
          ctgName: "ref_Chr01:1-100",
          start: 1,
          end: 100,
        },
      ],
    }),
    false,
  );
});
