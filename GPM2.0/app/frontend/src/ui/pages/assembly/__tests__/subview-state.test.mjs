import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPhasedSubviewCtgPool,
  buildRefSubviewCtgPool,
  buildSubviewTrackPairPoolsFromAssembly,
  buildSubviewSummaryFromCandidates,
  buildSubviewSummaryFromTrackSelections,
  filterSubviewTrackPairSelectionCtgs,
  getSubviewState,
  removeSubviewTrackSelection,
  resolveSubviewSelectionCtg,
  resolveFilteredSubviewTrackPairSelectionsFromAssembly,
  resolveSubviewTrackSummaryCtgs,
  selectSubviewCandidate,
  selectSubviewTrack,
  swapSubviewSummaryOrder,
} from "../subview-state.js";

function createSubview(overrides = {}) {
  return {
    mode: "2-contig",
    selectedAContigId: null,
    selectedARole: "",
    selectedBContigId: null,
    selectedBRole: "",
    selectedTrackSelections: [],
    selectedTrackARole: "",
    selectedTrackBRole: "",
    selectedTrackBSource: "",
    selectedTrackBDatasetId: null,
    selectedTrackBIsMirror: false,
    trackPairHiddenCtgs: [],
    trackPairSelectedCtgs: [],
    message: "",
    error: "",
    summary: null,
    ...overrides,
  };
}

test("selectSubviewCandidate toggles a selected candidate off", () => {
  const subview = createSubview();

  const afterSelect = selectSubviewCandidate({
    mode: "2-contig",
    subview,
    trackRole: "primary",
    contigId: 11,
  });

  assert.deepEqual(
    {
      selectedAContigId: afterSelect.selectedAContigId,
      selectedARole: afterSelect.selectedARole,
      message: afterSelect.message,
      summary: afterSelect.summary,
      error: afterSelect.error,
    },
    {
      selectedAContigId: 11,
      selectedARole: "primary",
      message: "已选 1/2 个ctg。",
      summary: null,
      error: "",
    },
  );

  const afterToggleOff = selectSubviewCandidate({
    mode: "2-contig",
    subview: afterSelect,
    trackRole: "primary",
    contigId: 11,
  });

  assert.deepEqual(
    {
      selectedAContigId: afterToggleOff.selectedAContigId,
      selectedARole: afterToggleOff.selectedARole,
      message: afterToggleOff.message,
      summary: afterToggleOff.summary,
      error: afterToggleOff.error,
    },
    {
      selectedAContigId: null,
      selectedARole: "",
      message: "",
      summary: null,
      error: "",
    },
  );
});

test("selectSubviewTrack creates a track-pair summary after primary and support selections", () => {
  const afterPrimary = selectSubviewTrack({
    subview: createSubview(),
    trackRole: "primary",
  });

  assert.equal(afterPrimary.summary, null);
  assert.equal(afterPrimary.message, "已选 1/2 条ds轨道。");

  const afterSupport = selectSubviewTrack({
    subview: afterPrimary,
    trackRole: "support",
    source: "mirror",
    datasetId: 8,
    isMirror: true,
  });

  assert.deepEqual(afterSupport.selectedTrackSelections, [
    { role: "primary", source: "mother", datasetId: null, isMirror: false },
    { role: "support", source: "mirror", datasetId: 8, isMirror: true },
  ]);
  assert.deepEqual(afterSupport.summary, {
    mode: "track-pair",
    topTrack: { role: "support", source: "mirror", datasetId: 8, isMirror: true },
    bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
  });
  assert.equal(afterSupport.message, "Subview 已进入轨道模式。");
  assert.equal(afterSupport.error, "");
});

test("buildSubviewSummaryFromCandidates orders support before primary", () => {
  const result = buildSubviewSummaryFromCandidates({
    subview: createSubview({
      selectedAContigId: 11,
      selectedARole: "primary",
      selectedBContigId: 22,
      selectedBRole: "support",
    }),
    primaryCtgs: [
      { assemblyCtgId: 11, order: 20 },
    ],
    supportCtgs: [
      { assemblyCtgId: 22, order: 5 },
    ],
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.value, {
    mode: "2-contig",
    top: { contigId: 22, role: "support" },
    bottom: { contigId: 11, role: "primary" },
  });
});

test("buildSubviewSummaryFromCandidates rejects same-dataset contigs when self alignment is unavailable", () => {
  const result = buildSubviewSummaryFromCandidates({
    subview: createSubview({
      selectedAContigId: 11,
      selectedARole: "primary",
      selectedBContigId: 22,
      selectedBRole: "primary",
    }),
    primaryCtgs: [
      { assemblyCtgId: 11, datasetId: 7, order: 10 },
      { assemblyCtgId: 22, datasetId: 7, order: 20 },
    ],
    supportCtgs: [],
    datasets: [
      { datasetId: 7, selfAlignmentAvailable: false },
    ],
  });

  assert.equal(result.ok, false);
  assert.equal(result.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
});

test("buildSubviewSummaryFromCandidates allows ref plus ds candidates", () => {
  const result = buildSubviewSummaryFromCandidates({
    subview: createSubview({
      selectedAContigId: 9001,
      selectedARole: "ref",
      selectedBContigId: 11,
      selectedBRole: "primary",
    }),
    primaryCtgs: [
      { assemblyCtgId: 11, datasetId: 7, order: 10 },
    ],
    supportCtgs: [],
    refCtgs: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        anchorStart: 1,
        totalLength: 5000,
        segmentStartBp: 1,
        segmentEndBp: 5000,
        hits: [],
      },
    ],
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.value, {
    mode: "2-contig",
    top: { contigId: 9001, role: "ref" },
    bottom: { contigId: 11, role: "primary" },
  });
});

test("buildSubviewSummaryFromCandidates rejects selecting the same ref member twice", () => {
  const result = buildSubviewSummaryFromCandidates({
    subview: createSubview({
      selectedAContigId: 9001,
      selectedARole: "ref",
      selectedBContigId: 9001,
      selectedBRole: "ref",
    }),
    primaryCtgs: [],
    supportCtgs: [],
    refCtgs: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        anchorStart: 1,
        totalLength: 5000,
        segmentStartBp: 1,
        segmentEndBp: 5000,
        hits: [],
      },
    ],
  });

  assert.equal(result.ok, false);
  assert.equal(result.error, "同一个 ref 片段不能同时作为 Subview 的两个成员。");
});

test("buildSubviewSummaryFromTrackSelections rejects fewer than two selections", () => {
  const result = buildSubviewSummaryFromTrackSelections({
    subview: createSubview({
      selectedTrackSelections: [{ role: "primary" }],
    }),
  });

  assert.equal(result.ok, false);
  assert.equal(result.error, "请先选中两条 ds 轨道。");
});

test("selectSubviewTrack allows the ref track as a normal selectable track", () => {
  const afterRef = selectSubviewTrack({
    subview: createSubview(),
    trackRole: "ref",
  });
  assert.deepEqual(afterRef.selectedTrackSelections, [
    { role: "ref", source: "mother", datasetId: null, isMirror: false },
  ]);
  assert.equal(afterRef.summary, null);
  assert.equal(afterRef.message, "已选 1/2 条ds轨道。");

  const afterPrimary = selectSubviewTrack({
    subview: afterRef,
    trackRole: "primary",
  });
  assert.deepEqual(afterPrimary.selectedTrackSelections, [
    { role: "ref", source: "mother", datasetId: null, isMirror: false },
    { role: "primary", source: "mother", datasetId: null, isMirror: false },
  ]);
  assert.deepEqual(afterPrimary.summary, {
    mode: "track-pair",
    topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
    bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
  });
});

test("buildSubviewTrackPairPoolsFromAssembly includes ref members and never creates mirror ref entries", () => {
  const pools = buildSubviewTrackPairPoolsFromAssembly({
    chrCtgs: [{ assemblyCtgId: 11, name: "ctg-a" }],
    supportChrCtgs: [],
    supportMirroredCtgs: [],
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        anchorStart: 1,
        totalLength: 5000,
        segmentStartBp: 1,
        segmentEndBp: 5000,
        hits: [],
      },
    ],
    deletedCtgs: [],
    selectedChrName: "Chr01",
  });

  assert.equal(Array.isArray(pools.refCtgs), true);
  assert.deepEqual(pools.refCtgs.map((item) => item.assemblyCtgId), [9001]);
  assert.equal(
    pools.refCtgs.some((item) => String(item.subviewSource || "") === "mirror"),
    false,
  );
});

test("buildSubviewTrackPairPoolsFromAssembly keeps only support ctgs visible in the main track length filter", () => {
  const pools = buildSubviewTrackPairPoolsFromAssembly({
    trackView: {
      supportDsCtgLen: 10000,
    },
    supportChrCtgs: [
      { assemblyCtgId: 30, name: "support-short", totalLength: 8000, anchorStart: 320 },
      { assemblyCtgId: 31, name: "support-long", totalLength: 15000, anchorStart: 640 },
    ],
    supportMirroredCtgs: [
      {
        assemblyCtgId: 40,
        datasetId: 22,
        chrName: "Chr01",
        name: "mirror-short",
        totalLength: 9000,
        lengthBp: 9000,
        startBp: 1,
        endBp: 9000,
        anchorStart: 960,
      },
      {
        assemblyCtgId: 41,
        datasetId: 22,
        chrName: "Chr01",
        name: "mirror-long",
        totalLength: 16000,
        lengthBp: 16000,
        startBp: 1,
        endBp: 16000,
        anchorStart: 1280,
      },
    ],
    refTrackMembers: [],
    deletedCtgs: [],
    selectedChrName: "Chr01",
  });

  assert.deepEqual(
    pools.supportCtgs.map((item) => item.assemblyCtgId),
    [31, 41],
  );
});

test("buildSubviewTrackPairPoolsFromAssembly backfills mirror hits from the active support track", () => {
  const pools = buildSubviewTrackPairPoolsFromAssembly({
    supportDatasetId: 22,
    supportChrCtgs: [
      {
        assemblyCtgId: 40,
        name: "live-support",
        totalLength: 12000,
        anchorStart: 320,
        hits: [
          { refStart: 1000, refEnd: 2400, ctgStart: 200, ctgEnd: 1600, blockLength: 1400, mapq: 60 },
        ],
      },
    ],
    supportMirroredCtgs: [
      {
        assemblyCtgId: 40,
        datasetId: 22,
        chrName: "Chr01",
        name: "stale-mirror",
        totalLength: 12000,
        lengthBp: 12000,
        startBp: 0,
        endBp: 11999,
        anchorStart: 960,
        hits: [],
      },
    ],
    refTrackMembers: [],
    deletedCtgs: [],
    selectedChrName: "Chr01",
  });
  const mirrorCtgs = resolveSubviewTrackSummaryCtgs(
    { role: "support", source: "mirror", datasetId: 22, isMirror: true },
    pools,
  );

  assert.equal(pools.supportMirrorCtgs.length, 1);
  assert.deepEqual(pools.supportMirrorCtgs[0].hits, [
    { refStart: 1000, refEnd: 2400, ctgStart: 200, ctgEnd: 1600, blockLength: 1400, mapq: 60 },
  ]);
  assert.deepEqual(mirrorCtgs.map((ctg) => ctg.assemblyCtgId), [40]);
  assert.deepEqual(
    filterSubviewTrackPairSelectionCtgs([{ trackRole: "support", contigId: 40 }], pools),
    [{ trackRole: "support", contigId: 40 }],
  );
});

test("resolveSubviewTrackSummaryCtgs keeps phased subview lanes in primary visual order", () => {
  const pools = buildSubviewTrackPairPoolsFromAssembly({
    chrCtgs: [
      { assemblyCtgId: 11, name: "left-primary", totalLength: 5000, anchorStart: 100 },
      { assemblyCtgId: 16, name: "right-primary", totalLength: 2000, anchorStart: 500 },
    ],
    phasedChrTracks: [
      {
        phasedTrackId: 102,
        haplotypeKey: "B",
        label: "Chr01B",
        displayOrder: 2,
        items: [
          { itemId: 9002, phasedTrackId: 102, assemblyCtgId: 16, displayOrder: 1 },
          { itemId: 9001, phasedTrackId: 102, assemblyCtgId: 11, displayOrder: 2 },
        ],
      },
    ],
  });

  const phasedCtgs = resolveSubviewTrackSummaryCtgs(
    { role: "phased", phasedTrackId: 102, haplotypeKey: "B" },
    pools,
  );

  assert.deepEqual(
    phasedCtgs.map((ctg) => ctg.name),
    ["left-primary", "right-primary"],
  );
});

test("buildPhasedSubviewCtgPool projects hits into phased item orientation", () => {
  const [ctg] = buildPhasedSubviewCtgPool({
    primaryCtgs: [
      {
        assemblyCtgId: 11,
        name: "primary-forward",
        orient: "+",
        totalLength: 1000,
        lengthBp: 1000,
        startBp: 0,
        endBp: 999,
        hits: [
          {
            hitKey: "h1",
            ctgStart: 101,
            ctgEnd: 200,
            queryStart: 101,
            queryEnd: 200,
            hitStart: 101,
            hitEnd: 200,
          },
        ],
      },
    ],
    phasedChrTracks: [
      {
        phasedTrackId: 101,
        haplotypeKey: "A",
        items: [
          { itemId: 9001, assemblyCtgId: 11, orient: "-" },
        ],
      },
    ],
  });

  assert.equal(ctg.orient, "-");
  assert.equal(ctg.refOrient, "-");
  assert.equal(ctg.subviewPhasedOrientFlipped, true);
  assert.equal(ctg.phasedTrackItemId, 9001);
  assert.deepEqual(ctg.hits[0], {
    hitKey: "h1",
    ctgStart: 801,
    ctgEnd: 900,
    queryStart: 801,
    queryEnd: 900,
    hitStart: 801,
    hitEnd: 900,
  });
});

test("phased subview candidate selections preserve item identity", () => {
  const afterFirst = selectSubviewCandidate({
    subview: createSubview(),
    trackRole: "phased",
    contigId: 11,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
    phasedHaplotypeKey: "A",
  });
  const afterSecond = selectSubviewCandidate({
    subview: afterFirst,
    trackRole: "phased",
    contigId: 11,
    phasedTrackId: 102,
    phasedTrackItemId: 9002,
    phasedHaplotypeKey: "B",
  });
  const phasedCtgs = [
    { assemblyCtgId: 11, name: "hap-A", phasedTrackId: 101, phasedTrackItemId: 9001, phasedHaplotypeKey: "A" },
    { assemblyCtgId: 11, name: "hap-B", phasedTrackId: 102, phasedTrackItemId: 9002, phasedHaplotypeKey: "B" },
  ];

  assert.equal(afterSecond.selectedAContigId, 11);
  assert.equal(afterSecond.selectedAPhasedTrackItemId, 9001);
  assert.equal(afterSecond.selectedBContigId, 11);
  assert.equal(afterSecond.selectedBPhasedTrackItemId, 9002);
  assert.equal(
    resolveSubviewSelectionCtg(
      {
        contigId: afterSecond.selectedBContigId,
        role: afterSecond.selectedBRole,
        phasedTrackId: afterSecond.selectedBPhasedTrackId,
        phasedTrackItemId: afterSecond.selectedBPhasedTrackItemId,
        phasedHaplotypeKey: afterSecond.selectedBPhasedHaplotypeKey,
      },
      { phasedCtgs },
    )?.name,
    "hap-B",
  );
});

test("buildSubviewTrackPairPoolsFromAssembly filters ref hits to the selected support dataset", () => {
  const pools = buildSubviewTrackPairPoolsFromAssembly({
    chrCtgs: [],
    supportChrCtgs: [],
    supportMirroredCtgs: [],
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        anchorStart: 1,
        totalLength: 5000,
        segmentStartBp: 1,
        segmentEndBp: 5000,
        hits: [
          { datasetId: 8, refStart: 100, refEnd: 400, ctgStart: 1, ctgEnd: 300 },
          { datasetId: 9, refStart: 600, refEnd: 900, ctgStart: 1, ctgEnd: 300 },
        ],
      },
    ],
    deletedCtgs: [],
    selectedChrName: "Chr01",
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
        bottomTrack: { role: "support", source: "mother", datasetId: 8, isMirror: false },
      },
    },
  });

  assert.deepEqual(pools.refCtgs[0].hits.map((hit) => hit.datasetId), [8]);
});

test("buildSubviewTrackPairPoolsFromAssembly filters ref hits to the mirrored support dataset", () => {
  const pools = buildSubviewTrackPairPoolsFromAssembly({
    chrCtgs: [],
    supportChrCtgs: [],
    supportMirroredCtgs: [],
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        anchorStart: 1,
        totalLength: 5000,
        segmentStartBp: 1,
        segmentEndBp: 5000,
        hits: [
          { datasetId: 12, refStart: 100, refEnd: 400, ctgStart: 1, ctgEnd: 300 },
          { datasetId: 4, refStart: 600, refEnd: 900, ctgStart: 1, ctgEnd: 300 },
        ],
      },
    ],
    deletedCtgs: [],
    selectedChrName: "Chr01",
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
        bottomTrack: { role: "support", source: "mirror", datasetId: 12, isMirror: true },
      },
    },
  });

  assert.deepEqual(pools.refCtgs[0].hits.map((hit) => hit.datasetId), [12]);
});

test("buildRefSubviewCtgPool can build a dataset-scoped ref member", () => {
  const [refCtg] = buildRefSubviewCtgPool(
    [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        anchorStart: 1,
        totalLength: 5000,
        segmentStartBp: 1,
        segmentEndBp: 5000,
        hits: [
          { datasetId: 7, refStart: 100, refEnd: 300, ctgStart: 10, ctgEnd: 210 },
          { datasetId: 8, refStart: 400, refEnd: 600, ctgStart: 10, ctgEnd: 210 },
        ],
      },
    ],
    { datasetId: 7 },
  );

  assert.equal(refCtg.hits.length, 1);
  assert.equal(refCtg.hits[0].datasetId, 7);
});

test("removeSubviewTrackSelection removes a support track selection by source and dataset", () => {
  const seeded = selectSubviewTrack({
    subview: createSubview(),
    trackRole: "primary",
  });
  const withSummary = selectSubviewTrack({
    subview: seeded,
    trackRole: "support",
    source: "mirror",
    datasetId: 8,
    isMirror: true,
  });

  const removed = removeSubviewTrackSelection({
    subview: withSummary,
    trackRole: "support",
    source: "mirror",
    datasetId: 8,
    isMirror: true,
  });

  assert.deepEqual(removed.selectedTrackSelections, [
    { role: "primary", source: "mother", datasetId: null, isMirror: false },
  ]);
  assert.equal(removed.summary, null);
  assert.equal(removed.message, "已选 1/2 条ds轨道。");
  assert.equal(removed.error, "");
});

test("swapSubviewSummaryOrder swaps track-pair summary tracks", () => {
  const swapped = swapSubviewSummaryOrder({
    subview: createSubview({
      summary: {
        mode: "track-pair",
        topTrack: { role: "primary" },
        bottomTrack: { role: "support", source: "mirror", datasetId: 8, isMirror: true },
      },
    }),
  });

  assert.deepEqual(swapped.summary, {
    mode: "track-pair",
    topTrack: { role: "support", source: "mirror", datasetId: 8, isMirror: true },
    bottomTrack: { role: "primary" },
  });
  assert.equal(swapped.message, "Subview 已切换上下轨道顺序。");
  assert.equal(swapped.error, "");
});

test("subview state helpers return english status copy when locale is en", () => {
  const selected = selectSubviewCandidate({
    mode: "2-contig",
    subview: createSubview(),
    trackRole: "primary",
    contigId: 11,
    stateOrLocale: "en",
  });
  assert.equal(selected.message, "Selected 1/2 contigs.");

  const entered = selectSubviewTrack({
    subview: selectSubviewTrack({
      subview: createSubview(),
      trackRole: "primary",
      stateOrLocale: "en",
    }),
    trackRole: "support",
    source: "mirror",
    datasetId: 8,
    isMirror: true,
    stateOrLocale: "en",
  });
  assert.equal(entered.message, "Entered track subview mode.");

  const swapped = swapSubviewSummaryOrder({
    subview: createSubview({
      summary: {
        mode: "track-pair",
        topTrack: { role: "primary" },
        bottomTrack: { role: "support", source: "mirror", datasetId: 8, isMirror: true },
      },
    }),
    stateOrLocale: "en",
  });
  assert.equal(swapped.message, "Swapped the subview track order.");
});

test("getSubviewState normalizes legacy track selection fields", () => {
  const state = getSubviewState({
    subview: {
      selectedTrackARole: "primary",
      selectedTrackBRole: "support",
      selectedTrackBSource: "mirror",
      selectedTrackBDatasetId: "8",
      selectedTrackBIsMirror: "true",
      selectedAContigId: "11",
      selectedARole: "primary",
      selectedBContigId: "22",
      selectedBRole: "support",
      summary: { mode: "track-pair" },
    },
  });

  assert.deepEqual(state.selectedTrackSelections, [
    { role: "primary", source: "mother", datasetId: null, isMirror: false },
    { role: "support", source: "mirror", datasetId: 8, isMirror: true },
  ]);
  assert.equal(state.selectedTrackARole, "primary");
  assert.equal(state.selectedTrackBRole, "support");
  assert.equal(state.selectedTrackBSource, "mirror");
  assert.equal(state.selectedTrackBDatasetId, 8);
  assert.equal(state.selectedTrackBIsMirror, true);
});

test("resolveFilteredSubviewTrackPairSelectionsFromAssembly filters hidden and invalid pair entries", () => {
  const result = resolveFilteredSubviewTrackPairSelectionsFromAssembly({
    chrCtgs: [{ assemblyCtgId: 11 }],
    supportChrCtgs: [{ assemblyCtgId: 22, datasetId: 8 }],
    supportMirroredCtgs: [{ assemblyCtgId: 33, datasetId: 8, datasetName: "support" }],
    selectedChrName: "Chr01",
    subview: {
      summary: { mode: "track-pair" },
      trackPairHiddenCtgs: [
        { trackRole: "primary", contigId: 11 },
        { trackRole: "support", contigId: 33 },
      ],
      trackPairSelectedCtgs: [
        { trackRole: "primary", contigId: 11 },
        { trackRole: "support", contigId: 22 },
        { trackRole: "support", contigId: 33 },
        { trackRole: "support", contigId: 44 },
      ],
    },
  });

  assert.deepEqual(result, [
    { trackRole: "support", contigId: 22 },
  ]);
});

// Keep a direct helper regression around the normalized pool filter as well.
test("filterSubviewTrackPairSelections preserves only current-pool entries", () => {
  const result = filterSubviewTrackPairSelectionCtgs(
    [
      { trackRole: "primary", contigId: 11 },
      { trackRole: "support", contigId: 22 },
      { trackRole: "support", contigId: 33 },
    ],
    {
      primaryCtgs: [{ assemblyCtgId: 11 }],
      supportCtgs: [{ assemblyCtgId: 22, datasetId: 8 }],
    },
  );

  assert.deepEqual(result, [
    { trackRole: "primary", contigId: 11 },
    { trackRole: "support", contigId: 22 },
  ]);
});
