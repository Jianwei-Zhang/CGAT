import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectExportLogText,
  buildProjectExportStatsModel,
} from "../project-export-state.js";

test("project export stats aggregate primary usage and assignment without ref segments", () => {
  const model = buildProjectExportStatsModel({
    chromosomes: [{ chrName: "Chr01" }, { chrName: "Chr02" }],
    primaryDatasetName: "hifiasm",
    unplacedCtgCount: 1,
    unplacedBp: 500,
    primaryCtgsByChr: {
      Chr01: [
        {
          assemblyCtgId: 1,
          name: "ptg1",
          datasetName: "hifiasm",
          totalLength: 1000,
        },
      ],
      Chr02: [
        {
          assemblyCtgId: 2,
          name: "ptg2",
          datasetName: "hifiasm",
          totalLength: 2000,
        },
      ],
    },
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        hiddenPrimaryCtgIds: [2],
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            sourceKind: "assembly_ctg",
            assemblyCtgId: 1,
            datasetName: "hifiasm",
            ctgName: "ptg1",
            overallLen: 1000,
            start: 1,
            end: 1000,
          },
          {
            segmentId: "seg-2",
            type: "ctg",
            sourceKind: "assembly_ctg",
            assemblyCtgId: 10,
            datasetName: "flye",
            ctgName: "contig_10",
            originId: "contig_10",
            overallLen: 300,
            start: 1,
            end: 300,
          },
        ],
      },
      Chr02: {
        mode: "segments",
        chrName: "Chr02",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            sourceKind: "assembly_ctg",
            assemblyCtgId: 2,
            datasetName: "hifiasm",
            ctgName: "ptg2",
            overallLen: 2000,
            start: 1,
            end: 2000,
          },
        ],
      },
    },
  });

  assert.equal(model.statsDisabledByRef, false);
  assert.equal(model.finalPathChrCount, 2);
  assert.equal(model.primaryCount.used, 2);
  assert.equal(model.primaryCount.assigned, 2);
  assert.equal(model.primaryLength.usedBp, 3000);
  assert.equal(model.primaryLength.assignedBp, 3000);
  assert.equal(model.assignment.unassignedCount, 1);
  assert.equal(model.assignment.unassignedBp, 500);
  assert.equal(model.supportRows.length, 1);
  assert.match(buildProjectExportLogText(model), /support\tChr01\tflye\tcontig_10/);
});

test("project export stats count hidden primary contigs from per-chr main-track state", () => {
  const model = buildProjectExportStatsModel({
    chromosomes: [{ chrName: "Chr01" }],
    primaryDatasetName: "hifiasm",
    primaryCtgsByChr: {
      Chr01: [
        {
          assemblyCtgId: 1,
          name: "ptg1",
          datasetName: "hifiasm",
          totalLength: 1000,
        },
        {
          assemblyCtgId: 2,
          name: "ptg2",
          datasetName: "hifiasm",
          totalLength: 2000,
        },
      ],
    },
    hiddenPrimaryCtgIdsByChr: {
      Chr01: [2],
    },
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            sourceKind: "assembly_ctg",
            assemblyCtgId: 1,
            datasetName: "hifiasm",
            ctgName: "ptg1",
            overallLen: 1000,
            start: 1,
            end: 1000,
          },
        ],
      },
    },
  });

  assert.equal(model.primaryCount.used, 2);
  assert.equal(model.primaryCount.appended, 1);
  assert.equal(model.primaryCount.hidden, 1);
  assert.equal(model.primaryLength.usedBp, 3000);
  assert.equal(model.primaryLength.appendedBp, 1000);
  assert.equal(model.primaryLength.hiddenBp, 2000);
  assert.equal(model.primaryCount.label, "2/2");
});

test("project export stats disable all statistics when any final path contains ref", () => {
  const model = buildProjectExportStatsModel({
    chromosomes: [{ chrName: "Chr01" }],
    primaryDatasetName: "hifiasm",
    primaryCtgsByChr: {
      Chr01: [
        {
          assemblyCtgId: 1,
          name: "ptg1",
          datasetName: "hifiasm",
          totalLength: 1000,
        },
      ],
    },
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            sourceKind: "ref_segment",
            referenceChrName: "Chr01",
            memberStartBp: 1,
            memberEndBp: 1000,
            originId: "Chr01",
            overallLen: 1000,
            start: 1,
            end: 1000,
          },
        ],
      },
    },
  });

  assert.equal(model.statsDisabledByRef, true);
  assert.equal(model.canExportLog, false);
  assert.deepEqual(model.refChrNames, ["Chr01"]);
  assert.equal(model.primaryCount.used, 0);
  assert.equal(model.supportRows.length, 0);
  assert.equal(buildProjectExportLogText(model), "");
});
