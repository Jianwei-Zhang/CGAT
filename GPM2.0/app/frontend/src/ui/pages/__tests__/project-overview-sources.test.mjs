import test from "node:test";
import assert from "node:assert/strict";
import { groupProjectOverviewSources } from "../project-overview-sources.js";

test("overview groups once without changing order or guessing primary membership", () => {
  const ctgs = [
    { assemblyCtgId: 3, assignedChrName: "Chr1", datasetId: 2, derivedTargetDatasetId: 1, originId: "derived" },
    { assemblyCtgId: 1, assignedChrName: "Chr1", datasetId: 1, sourceFragment: { sourceStart: 10 }, anchorStart: -100, orient: "-" },
    { assemblyCtgId: 4, assignedChrName: "Chr1", datasetId: null, derivedTargetDatasetId: 1 },
    { assemblyCtgId: 2, assignedChrName: "Chr2", datasetId: 2 },
    { assemblyCtgId: 5, assignedChrName: null, datasetId: 1 },
    { assemblyCtgId: 6, assignedChrName: "unknown", datasetId: 1 },
  ];
  const result = groupProjectOverviewSources({ chromosomes: [{ chrName: "Chr1" }, { chrName: "Chr2" }, { chrName: "Empty" }],
    ctgs, primaryCtgIds: [1, 3, 5] });
  assert.deepEqual(result.ctgsByChr.Chr1, ctgs.slice(0, 3));
  assert.deepEqual(result.primaryCtgsByChr.Chr1, ctgs.slice(0, 2));
  assert.equal(result.primaryCtgsByChr.Chr1[1], ctgs[1], "reuse the summary object and all provenance");
  assert.deepEqual(result.primaryCtgsByChr.Chr2, []);
  assert.deepEqual(result.ctgsByChr.Empty, []);
  assert.equal(result.ctgsByChr.unknown, undefined);
});

test("overview treats chromosome names as data, including object prototype names", () => {
  const ctg = { assemblyCtgId: 1, assignedChrName: "__proto__" };
  const result = groupProjectOverviewSources({ chromosomes: [{ chrName: "__proto__" }], ctgs: [ctg], primaryCtgIds: [1] });
  assert.deepEqual(result.ctgsByChr.__proto__, [ctg]);
  assert.deepEqual(result.primaryCtgsByChr.__proto__, [ctg]);
});

test("malformed or old overview source responses cannot silently publish empty statistics", () => {
  for (const sources of [null, {}, { items: [] }, { chromosomes: [], ctgs: [] }, { chromosomes: [], primaryCtgIds: [] }]) {
    assert.throws(() => groupProjectOverviewSources(sources), /Invalid project overview source payload/);
  }
});
