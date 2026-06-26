import test from "node:test";
import assert from "node:assert/strict";

import {
  areSubviewTrackDragOffsetsEqual,
  areTrackDragOffsetsEqual,
  buildSupportMirrorKey,
  buildSubviewTrackDragOffsetKey,
  buildTrackDragOffsetKey,
  filterPrimaryTrackSelectionCtgIds,
  filterSubviewTrackDragOffsetsBySummary,
  filterTrackDragOffsets,
  normalizeDeletedCtgRecordIds,
  normalizeSupportMirrorEntry,
  normalizeSupportMirroredCtgs,
  normalizeTrackDragOffsets,
  normalizeTrackSelectionCtgIds,
  normalizeSubviewTrackDragOffsets,
  setSubviewTrackDragOffset,
  setTrackDragOffset,
  swapSubviewTrackDragOffsetsForSummarySwap,
} from "../selection-state.js";

test("normalizeTrackSelectionCtgIds dedupes, truncates, and sorts ids", () => {
  assert.deepEqual(
    normalizeTrackSelectionCtgIds([7, "3", 7.9, 0, -2, "foo", 2]),
    [2, 3, 7],
  );
});

test("normalizeSupportMirrorEntry resolves required ids and defaults optional fields", () => {
  assert.deepEqual(
    normalizeSupportMirrorEntry({
      datasetId: "8.7",
      assemblyCtgId: 12.2,
      datasetName: " support ",
      chrName: " Chr01 ",
      originId: " ptg000123l ",
      totalLength: "42",
      lengthBp: "18",
      startBp: "5",
      laneIndex: "2",
      hits: [{ id: 1 }, null],
      isSelected: 1,
    }),
    {
      datasetId: 8,
      datasetName: " support ",
      chrName: "Chr01",
      assemblyCtgId: 12,
      name: "Ctg12",
      originId: "ptg000123l",
      totalLength: 42,
      anchorStart: null,
      lengthBp: 18,
      startBp: 5,
      endBp: 22,
      laneIndex: 2,
      hits: [{ id: 1 }],
      isSelected: true,
    },
  );
});

test("setTrackDragOffset sets and clears an offset by key", () => {
  assert.deepEqual(
    setTrackDragOffset(
      [
        { trackRole: "primary", assemblyCtgId: 2, offsetBp: 1.2 },
        { trackRole: "support", assemblyCtgId: 8, offsetPx: 3.4 },
      ],
      { trackRole: "primary", assemblyCtgId: 2, offsetBp: 0 },
    ),
    [{ trackRole: "support", assemblyCtgId: 8, offsetPx: 3.4 }],
  );
  assert.deepEqual(
    setTrackDragOffset([], { trackRole: "primary", assemblyCtgId: 5, offsetPx: 9.6 }),
    [{ trackRole: "primary", assemblyCtgId: 5, offsetPx: 9.6 }],
  );
});

test("setTrackDragOffset replaces and clears legacy support offsets with dataset-scoped keys", () => {
  assert.deepEqual(
    setTrackDragOffset(
      [{ trackRole: "support", assemblyCtgId: 8, offsetBp: 12 }],
      { trackRole: "support", datasetId: 22, assemblyCtgId: 8, offsetBp: 30 },
    ),
    [{ trackRole: "support", datasetId: 22, assemblyCtgId: 8, offsetBp: 30 }],
  );
  assert.deepEqual(
    setTrackDragOffset(
      [{ trackRole: "support", assemblyCtgId: 8, offsetBp: 12 }],
      { trackRole: "support", datasetId: 22, assemblyCtgId: 8, offsetBp: 0 },
    ),
    [],
  );
});

test("setSubviewTrackDragOffset sets and clears an offset by key", () => {
  assert.deepEqual(
    setSubviewTrackDragOffset(
      [
        { slot: "top", contigId: 11, offsetBp: 2.2 },
        { slot: "bottom", contigId: 22, offsetPx: 4.4 },
      ],
      { slot: "top", contigId: 11, offsetBp: 0 },
    ),
    [{ slot: "bottom", contigId: 22, offsetPx: 4.4 }],
  );
  assert.deepEqual(
    setSubviewTrackDragOffset([], { slot: "bottom", contigId: 33, offsetPx: 7.7 }),
    [{ slot: "bottom", contigId: 33, offsetPx: 7.7 }],
  );
});

test("swapSubviewTrackDragOffsetsForSummarySwap swaps top and bottom slots", () => {
  assert.deepEqual(
    swapSubviewTrackDragOffsetsForSummarySwap([
      { slot: "top", contigId: 11, offsetBp: 3.2 },
      { slot: "bottom", contigId: 22, offsetPx: 4.4 },
    ]),
    [
      { slot: "top", contigId: 22, offsetPx: 4.4 },
      { slot: "bottom", contigId: 11, offsetBp: 3.2 },
    ],
  );
});

test("filterTrackDragOffsets keeps offsets for chrCtgs, supportChrCtgs, and mirrored support ctgs", () => {
  assert.deepEqual(
    filterTrackDragOffsets(
      [
        { trackRole: "primary", assemblyCtgId: 5, offsetBp: 1 },
        { trackRole: "primary", assemblyCtgId: 9, offsetBp: 1 },
        { trackRole: "support", assemblyCtgId: 8, offsetBp: 2 },
        { trackRole: "support", assemblyCtgId: 13, offsetBp: 3 },
      ],
      {
        chrCtgs: [{ assemblyCtgId: 5 }],
        supportChrCtgs: [{ assemblyCtgId: 8 }],
        supportMirroredCtgs: [{ datasetId: 4, assemblyCtgId: 13, totalLength: 10 }],
      },
    ),
    [
      { trackRole: "primary", assemblyCtgId: 5, offsetBp: 1 },
      { trackRole: "support", assemblyCtgId: 8, offsetBp: 2 },
      { trackRole: "support", assemblyCtgId: 13, offsetBp: 3 },
    ],
  );
});

test("filterSubviewTrackDragOffsetsBySummary keeps offsets for the selected top and bottom contigs", () => {
  assert.deepEqual(
    filterSubviewTrackDragOffsetsBySummary(
      [
        { slot: "top", contigId: 1, offsetBp: 1 },
        { slot: "top", contigId: 2, offsetBp: 2 },
        { slot: "bottom", contigId: 3, offsetBp: 3 },
      ],
      {
        top: { contigId: 1 },
        bottom: { contigId: 3 },
      },
    ),
    [
      { slot: "top", contigId: 1, offsetBp: 1 },
      { slot: "bottom", contigId: 3, offsetBp: 3 },
    ],
  );
});

test("normalizeDeletedCtgRecordIds dedupes and sorts record ids", () => {
  assert.deepEqual(normalizeDeletedCtgRecordIds([9, "4", 9.3, 0, -1, "foo", 2]), [2, 4, 9]);
});

test("filterPrimaryTrackSelectionCtgIds keeps only chr contig ids", () => {
  assert.deepEqual(
    filterPrimaryTrackSelectionCtgIds([9, 3, 5, 5], {
      chrCtgs: [{ assemblyCtgId: 3 }, { assemblyCtgId: 9 }],
    }),
    [3, 9],
  );
});

test("normalizeSupportMirroredCtgs dedupes mirrored entries by dataset and contig", () => {
  assert.deepEqual(
    normalizeSupportMirroredCtgs([
      { datasetId: 4, assemblyCtgId: 7, totalLength: 12, startBp: 1 },
      { datasetId: 4, assemblyCtgId: 7, totalLength: 18, startBp: 2, originId: "ptg000007l" },
      { datasetId: 5, assemblyCtgId: 8, totalLength: 20, startBp: 3 },
    ]),
    [
      {
        datasetId: 4,
        datasetName: "",
        chrName: "",
        assemblyCtgId: 7,
        name: "Ctg7",
        originId: "ptg000007l",
        totalLength: 18,
        anchorStart: null,
        lengthBp: 18,
        startBp: 2,
        endBp: 19,
        laneIndex: 0,
        hits: [],
        isSelected: false,
      },
      {
        datasetId: 5,
        datasetName: "",
        chrName: "",
        assemblyCtgId: 8,
        name: "Ctg8",
        originId: "",
        totalLength: 20,
        anchorStart: null,
        lengthBp: 20,
        startBp: 3,
        endBp: 22,
        laneIndex: 0,
        hits: [],
        isSelected: false,
      },
    ],
  );
});

test("filterTrackDragOffsets can preserve inactive support dataset offsets during support ds switches", () => {
  assert.deepEqual(
    filterTrackDragOffsets(
      [
        { trackRole: "support", datasetId: 22, assemblyCtgId: 8, offsetBp: 120 },
        { trackRole: "support", datasetId: 33, assemblyCtgId: 13, offsetBp: 240 },
        { trackRole: "primary", assemblyCtgId: 99, offsetBp: 360 },
      ],
      {
        supportDatasetId: 33,
        chrCtgs: [],
        supportChrCtgs: [{ assemblyCtgId: 13 }],
        supportMirroredCtgs: [],
      },
      { preserveUnmatchedSupportOffsets: true },
    ),
    [
      { trackRole: "support", datasetId: 22, assemblyCtgId: 8, offsetBp: 120 },
      { trackRole: "support", datasetId: 33, assemblyCtgId: 13, offsetBp: 240 },
    ],
  );
});

test("build helper keys normalize invalid ids to zero", () => {
  assert.equal(buildSupportMirrorKey("foo", 7), "0:7");
  assert.equal(buildTrackDragOffsetKey("primary", "8"), "primary:8");
  assert.equal(buildTrackDragOffsetKey("support", "8", { datasetId: "22" }), "support:22:8");
  assert.equal(buildSubviewTrackDragOffsetKey("bottom", "9"), "bottom:9");
});

test("normalizeTrackDragOffsets and normalizeSubviewTrackDragOffsets preserve zero-free ordering", () => {
  assert.deepEqual(
    normalizeTrackDragOffsets([
      { trackRole: "support", assemblyCtgId: 8, offsetPx: 4.2 },
      { trackRole: "primary", assemblyCtgId: 5, offsetBp: 1.1 },
      { trackRole: "primary", assemblyCtgId: 5, offsetBp: 2.2 },
    ]),
    [
      { trackRole: "primary", assemblyCtgId: 5, offsetBp: 2.2 },
      { trackRole: "support", assemblyCtgId: 8, offsetPx: 4.2 },
    ],
  );
  assert.deepEqual(
    normalizeSubviewTrackDragOffsets([
      { slot: "bottom", contigId: 2, offsetBp: 1.1 },
      { slot: "top", contigId: 3, offsetPx: 4.2 },
      { slot: "top", contigId: 3, offsetPx: 6.6 },
    ]),
    [
      { slot: "top", contigId: 3, offsetPx: 6.6 },
      { slot: "bottom", contigId: 2, offsetBp: 1.1 },
    ],
  );
});

test("areTrackDragOffsetsEqual and areSubviewTrackDragOffsetsEqual compare normalized values", () => {
  assert.equal(
    areTrackDragOffsetsEqual(
      [{ trackRole: "primary", assemblyCtgId: 5, offsetBp: 1 }],
      [{ trackRole: "primary", assemblyCtgId: 5, offsetBp: "1.0" }],
    ),
    true,
  );
  assert.equal(
    areSubviewTrackDragOffsetsEqual(
      [{ slot: "top", contigId: 2, offsetPx: 1 }],
      [{ slot: "top", contigId: 2, offsetPx: "1.0" }],
    ),
    true,
  );
});
