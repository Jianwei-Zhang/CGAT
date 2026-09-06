import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSubviewCompositionCandidates,
  filterSubviewCompositionCandidates,
} from "../subview-composition-candidates.js";

test("candidate projection includes all datasets and distinguishes same names by stable identity", () => {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 10,
    allChrCtgs: [
      { assemblyCtgId: 1, datasetId: 10, datasetName: "primary", name: "same", lengthBp: 100 },
      { assemblyCtgId: 2, datasetId: 20, datasetName: "support-a", name: "same", lengthBp: 200 },
      { assemblyCtgId: 3, datasetId: 30, datasetName: "support-b", name: "third", lengthBp: 300 },
    ],
  });
  assert.deepEqual(candidates.map((entry) => entry.entityKey), ["assembly:1", "assembly:2", "assembly:3"]);
  assert.deepEqual(candidates.map((entry) => entry.source.role), ["primary", "support", "support"]);
  assert.equal(filterSubviewCompositionCandidates(candidates, { query: "same" }).length, 2);
  assert.equal(filterSubviewCompositionCandidates(candidates, { source: "primary" }).length, 1);
});

test("alternate phased and mirror presentations retain source identity but share entity identity", () => {
  const candidates = buildSubviewCompositionCandidates({
    allChrCtgs: [{ assemblyCtgId: 7, datasetId: 20, name: "ctg7", lengthBp: 100 }],
    supportMirroredCtgs: [{ assemblyCtgId: 7, datasetId: 20, name: "ctg7 mirror", lengthBp: 100 }],
    phasedCtgs: [{ assemblyCtgId: 7, datasetId: 20, name: "ctg7 H1", lengthBp: 100,
      phasedTrackId: 4, phasedTrackItemId: 9, phasedHaplotypeKey: "H1" }],
  });
  assert.equal(candidates.length, 3);
  assert.equal(new Set(candidates.map((entry) => entry.entityKey)).size, 1);
  assert.equal(new Set(candidates.map((entry) => entry.sourceKey)).size, 3);
});

test("reference segments use chromosome range identity instead of their backing assembly contig", () => {
  const candidates = buildSubviewCompositionCandidates({
    allChrCtgs: [{ assemblyCtgId: 7, datasetId: 20, name: "ctg7", lengthBp: 100 }],
    refCtgs: [{
      assemblyCtgId: 7,
      name: "Chr01:100-199",
      referenceChrName: "Chr01",
      segmentStartBp: 100,
      segmentEndBp: 199,
      lengthBp: 100,
    }],
  });
  assert.deepEqual(candidates.map((entry) => entry.entityKey), [
    "assembly:7",
    "ref:Chr01:100-199",
  ]);
});
