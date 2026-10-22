import test from "node:test";
import assert from "node:assert/strict";
import { buildSupportDatasetOptions } from "../support-dataset-options.js";

test("four-dataset project exposes all three supports, independent of chromosome hits", () => {
  assert.deepEqual(buildSupportDatasetOptions({primaryDatasetId: 1, supportDatasetIds: [2, "3", 4]},
    [{datasetId: 1, name: "main"}, {datasetId: 2, name: "support-a"},
      {datasetId: 3, name: "support-b", displayName: "Renamed support"}, {datasetId: 4, name: "support-c"}]),
  [{datasetId: 2, label: "support-a"}, {datasetId: 3, label: "Renamed support"}, {datasetId: 4, label: "support-c"}]);
});

test("all valid supports survive missing catalog rows and there is no two-support cap", () => {
  const ids = Array.from({length: 8}, (_, i) => i + 2);
  assert.deepEqual(buildSupportDatasetOptions({supportDatasetIds: ids}).map(item => item.datasetId), ids);
  assert.deepEqual(buildSupportDatasetOptions(null), []);
});
