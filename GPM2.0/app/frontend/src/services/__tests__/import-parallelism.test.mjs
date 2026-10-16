import test from "node:test";
import assert from "node:assert/strict";

import {
  importParserWorkerChoices,
  normalizeImportParserWorkers,
  recommendedImportParserWorkers,
} from "../import-parallelism.js";

test("import parser recommendation leaves one CPU free and stays within backend limits", () => {
  assert.equal(recommendedImportParserWorkers(1), 1);
  assert.equal(recommendedImportParserWorkers(4), 3);
  assert.equal(recommendedImportParserWorkers(16), 8);
  assert.equal(recommendedImportParserWorkers(null), 1);
  assert.deepEqual(importParserWorkerChoices(), ["1", "2", "3", "4", "5", "6", "7", "8"]);
});

test("invalid or legacy auto values resolve to the current numeric recommendation", () => {
  assert.equal(normalizeImportParserWorkers("6", 8), "6");
  assert.equal(normalizeImportParserWorkers("auto", 8), "7");
  assert.equal(normalizeImportParserWorkers("99", 4), "3");
});
