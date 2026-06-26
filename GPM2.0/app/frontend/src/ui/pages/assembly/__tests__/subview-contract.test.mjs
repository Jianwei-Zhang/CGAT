import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSubviewRenderModel,
  validateSubviewSelection,
} from "../subview-contract.js";

test("validateSubviewSelection accepts 2-contig cross-dataset selection", () => {
  const result = validateSubviewSelection({
    mode: "2-contig",
    primaryDatasetId: 101,
    supportDatasetId: 202,
    selections: {
      A: { contigId: 11, datasetId: 101 },
      B: { contigId: 22, datasetId: 202 },
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.value.mode, "2-contig");
  assert.deepEqual(result.value.graphPairs, [
    {
      pairId: "AB",
      leftSlot: "A",
      rightSlot: "B",
      boundaryOnB: "left",
      renderable: true,
    },
  ]);
});

test("buildSubviewRenderModel only encodes AB pair in 2-contig mode", () => {
  const result = buildSubviewRenderModel({
    mode: "2-contig",
    primaryDatasetId: 101,
    supportDatasetId: 202,
    selections: {
      A: { contigId: 11, datasetId: 101, contigName: "ctg-A" },
      B: { contigId: 22, datasetId: 202, contigName: "ctg-B" },
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.value.mode, "2-contig");
  assert.deepEqual(
    result.value.graphPairs.map((item) => ({
      pairId: item.pairId,
      leftSlot: item.leftSlot,
      rightSlot: item.rightSlot,
      boundaryOnB: item.boundaryOnB,
    })),
    [{ pairId: "AB", leftSlot: "A", rightSlot: "B", boundaryOnB: "left" }],
  );
});

test("validateSubviewSelection rejects missing contig selections with Chinese error", () => {
  const result = validateSubviewSelection({
    mode: "2-contig",
    primaryDatasetId: 101,
    supportDatasetId: 202,
    selections: {
      A: { contigId: 11, datasetId: 101 },
      B: null,
    },
  });

  assert.equal(result.ok, false);
  assert.equal(result.error, "双 contig 模式需要同时选择 A / B contig");
});

test("validateSubviewSelection rejects slot-dataset mismatches with Chinese error", () => {
  const result = validateSubviewSelection({
    mode: "2-contig",
    primaryDatasetId: 101,
    supportDatasetId: 202,
    selections: {
      A: { contigId: 11, datasetId: 202 },
      B: { contigId: 22, datasetId: 101 },
    },
  });

  assert.equal(result.ok, false);
  assert.equal(result.error, "A 必须来自主 ds，B 必须来自辅 ds");
});

test("validateSubviewSelection returns english errors when locale is en", () => {
  const result = validateSubviewSelection({
    mode: "2-contig",
    primaryDatasetId: 101,
    supportDatasetId: 202,
    selections: {
      A: { contigId: 11, datasetId: 202 },
      B: { contigId: 22, datasetId: 101 },
    },
    stateOrLocale: "en",
  });

  assert.equal(result.ok, false);
  assert.equal(result.error, "A must come from the primary dataset and B must come from the support dataset.");
});
