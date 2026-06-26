import test from "node:test";
import assert from "node:assert/strict";

import {
  getCurrentChrFinalPath,
  normalizeFinalPathByChr,
  resolveCurrentFinalPathChrName,
} from "../final-path-state.js";

test("normalizeFinalPathByChr only keeps segment-based entries and drops legacy direct rows", () => {
  const normalized = normalizeFinalPathByChr({
    Chr01: {
      mode: "direct-ctg",
      chrName: "Chr01",
      assemblyCtgId: 7,
      datasetName: "flye",
      ctgName: "flye_ctg7",
      totalLength: 900,
      updatedAt: "",
    },
    Chr02: {
      mode: "segments",
      chrName: "Chr02",
      segments: [
        {
          type: "ctg",
          segmentId: "a",
          assemblyCtgId: 9,
          datasetName: "hifiasm",
          ctgName: "Ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 10,
          end: 800,
        },
        {
          type: "gap",
          segmentId: "b",
          gapSizeBp: 100,
        },
      ],
      updatedAt: "5",
    },
  });

  assert.deepEqual(normalized, {
    Chr02: {
      mode: "segments",
      chrName: "Chr02",
      segments: [
        {
          segmentId: "a",
          type: "ctg",
          assemblyCtgId: 9,
          datasetName: "hifiasm",
          ctgName: "Ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 10,
          end: 800,
        },
        {
          segmentId: "b",
          type: "gap",
          gapSizeBp: 100,
        },
      ],
      totalLength: 891,
      updatedAt: "5",
    },
  });
});

test("normalizeFinalPathByChr drops invalid segment rows", () => {
  const normalized = normalizeFinalPathByChr({
    Chr02: {
      mode: "segments",
      chrName: "Chr02",
      segments: [
        {
          type: "ctg",
          segmentId: "a",
          assemblyCtgId: 9,
          datasetName: "hifiasm",
          ctgName: "Ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 10,
          end: 800,
        },
        {
          type: "ctg",
          segmentId: "broken",
          assemblyCtgId: 10,
          ctgName: "",
          overallLen: 0,
          start: 2,
          end: 1,
        },
      ],
    },
  });

  assert.deepEqual(normalized, {
    Chr02: {
      mode: "segments",
      chrName: "Chr02",
      segments: [
        {
          segmentId: "a",
          type: "ctg",
          assemblyCtgId: 9,
          datasetName: "hifiasm",
          ctgName: "Ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 10,
          end: 800,
        },
      ],
      totalLength: 791,
      updatedAt: "",
    },
  });
});

test("normalizeFinalPathByChr applies explicit negative orient to initial forward ranges", () => {
  const normalized = normalizeFinalPathByChr({
    Chr01: {
      mode: "segments",
      chrName: "Chr01",
      segments: [
        {
          type: "ctg",
          segmentId: "seg-1",
          assemblyCtgId: 9,
          datasetName: "hifiasm",
          ctgName: "Ctg9",
          originId: "utig4-001122l",
          overallLen: 1200,
          orient: "-",
          start: 1,
          end: 1200,
        },
      ],
    },
  });

  assert.deepEqual(normalized.Chr01.segments[0], {
    segmentId: "seg-1",
    type: "ctg",
    assemblyCtgId: 9,
    datasetName: "hifiasm",
    ctgName: "Ctg9",
    originId: "utig4-001122l",
    overallLen: 1200,
    start: 1200,
    end: 1,
  });
});

test("getCurrentChrFinalPath returns only the selected segment-based chromosome entry", () => {
  const current = getCurrentChrFinalPath({
    selectedChrName: "Chr03",
    finalPathByChr: {
      Chr02: {
        mode: "segments",
        chrName: "Chr02",
        segments: [{ segmentId: "seg-1", type: "gap", gapSizeBp: 100 }],
      },
      Chr03: {
        mode: "segments",
        chrName: "Chr03",
        segments: [
          {
            segmentId: "seg-1",
            type: "ctg",
            assemblyCtgId: 9,
            datasetName: "",
            ctgName: "flye_ctg9",
            originId: "utig4-001122l",
            overallLen: 1200,
            start: 1,
            end: 1200,
          },
        ],
        updatedAt: "1",
      },
    },
  });

  assert.equal(current.mode, "segments");
  assert.equal(current.chrName, "Chr03");
  assert.equal(current.totalLength, 1200);
  assert.equal(current.segments.length, 1);
  assert.equal(current.segments[0].ctgName, "flye_ctg9");
  assert.equal(current.segments[0].originId, "utig4-001122l");
});

test("getCurrentChrFinalPath resolves the active final-path haplotype entry", () => {
  const assembly = {
    selectedChrName: "Chr01",
    isChrPhased: true,
    activePhasedTrackKey: "B",
    activeFinalPathKey: "B",
    phasedChrTracks: [
      { haplotypeKey: "A", label: "Chr01A" },
      { haplotypeKey: "B", label: "Chr01B" },
    ],
    finalPathByChr: {
      Chr01: {
        mode: "segments",
        chrName: "Chr01",
        segments: [{ segmentId: "parent", type: "gap", gapSizeBp: 100 }],
      },
      Chr01B: {
        mode: "segments",
        chrName: "Chr01B",
        segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
      },
    },
  };

  assert.equal(resolveCurrentFinalPathChrName(assembly), "Chr01B");
  assert.equal(getCurrentChrFinalPath(assembly).chrName, "Chr01B");
  assert.equal(getCurrentChrFinalPath(assembly).segments[0].segmentId, "hap-b");
});

test("normalizeFinalPathByChr preserves per-chr hidden primary ctg ids", () => {
  const result = normalizeFinalPathByChr({
    Chr01: {
      mode: "segments",
      chrName: "Chr01",
      hiddenPrimaryCtgIds: [2, "2", 3, 0, "bad"],
      segments: [
        {
          segmentId: "seg-1",
          type: "ctg",
          assemblyCtgId: 1,
          datasetName: "hifiasm",
          ctgName: "ptg1",
          overallLen: 1000,
          start: 1,
          end: 1000,
        },
      ],
    },
  });

  assert.deepEqual(result.Chr01.hiddenPrimaryCtgIds, [2, 3]);
});
