import {
  test,
  assert,
  setSubviewAnchorStateForSummary,
  __testBuildAssemblyContextMenuItems,
  __testBuildSubviewSummaryFromCandidates,
  __testEnterSubviewFromTrackSelections,
  __testHandleSubviewSwapTrackOrder,
  __testHandleTrackSubviewTrackSelection,
  __testSelectSubviewCandidate,
  __testSelectSubviewTrack,
  __testRemoveSubviewCandidate,
  __testRemoveSubviewTrackSelection,
  __testBuildSubviewSummaryFromTrackSelections,
  __testSwapSubviewSummaryOrder,
  __testSwapSubviewTrackDragOffsetsForSummarySwap,
  renderAssemblyPage,
  createState,
  createStore,
} from "./tabs-semantics-harness.mjs";

test("selectSubviewCandidate toggles off an already selected candidate", () => {
  const afterToggleOff = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: 22,
    primaryCtgs: [{ assemblyCtgId: 2, name: "ctg-alpha" }],
    supportCtgs: [{ assemblyCtgId: 30, name: "support-ctg" }],
    subview: {
      mode: "2-contig",
      selectedAContigId: 2,
      selectedARole: "primary",
      selectedBContigId: 30,
      selectedBRole: "support",
      message: "",
      error: "",
      summary: {
        mode: "2-contig",
      },
    },
    trackRole: "support",
    contigId: 30,
  });

  assert.equal(afterToggleOff.selectedAContigId, 2);
  assert.equal(afterToggleOff.selectedARole, "primary");
  assert.equal(afterToggleOff.selectedBContigId, null);
  assert.equal(afterToggleOff.selectedBRole, "");
  assert.equal(afterToggleOff.summary, null);
});

test("selectSubviewCandidate keeps at most two candidates and supports same-track picks", () => {
  const baseArgs = {
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: 22,
    primaryCtgs: [
      { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
      { assemblyCtgId: 5, name: "ctg-zeta", anchorStart: 900 },
      { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
    ],
    supportCtgs: [{ assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 }],
    subview: {
      mode: "2-contig",
      selectedAContigId: null,
      selectedARole: "",
      selectedBContigId: null,
      selectedBRole: "",
      message: "",
      error: "",
      summary: null,
    },
  };

  const afterFirst = __testSelectSubviewCandidate({
    ...baseArgs,
    trackRole: "primary",
    contigId: 2,
  });
  const afterSecond = __testSelectSubviewCandidate({
    ...baseArgs,
    subview: afterFirst,
    trackRole: "primary",
    contigId: 8,
  });
  const afterThird = __testSelectSubviewCandidate({
    ...baseArgs,
    subview: afterSecond,
    trackRole: "support",
    contigId: 30,
  });

  assert.equal(afterFirst.selectedAContigId, 2);
  assert.equal(afterFirst.selectedARole, "primary");
  assert.equal(afterSecond.selectedAContigId, 2);
  assert.equal(afterSecond.selectedBContigId, 8);
  assert.equal(afterSecond.selectedBRole, "primary");
  assert.equal(afterThird.selectedAContigId, 8);
  assert.equal(afterThird.selectedARole, "primary");
  assert.equal(afterThird.selectedBContigId, 30);
  assert.equal(afterThird.selectedBRole, "support");
  assert.equal(afterThird.summary, null);
});

test("buildSubviewSummaryFromCandidates orders same-ds by chr order and cross-ds with support on top", () => {
  const primaryCtgs = [
    { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
    { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
  ];
  const supportCtgs = [{ assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 }];

  const sameDs = __testBuildSubviewSummaryFromCandidates({
    subview: {
      selectedAContigId: 8,
      selectedARole: "primary",
      selectedBContigId: 2,
      selectedBRole: "primary",
    },
    primaryCtgs,
    supportCtgs,
  });
  assert.equal(sameDs.ok, true);
  assert.equal(sameDs.value.top.contigId, 2);
  assert.equal(sameDs.value.bottom.contigId, 8);

  const crossDs = __testBuildSubviewSummaryFromCandidates({
    subview: {
      selectedAContigId: 2,
      selectedARole: "primary",
      selectedBContigId: 30,
      selectedBRole: "support",
    },
    primaryCtgs,
    supportCtgs,
  });
  assert.equal(crossDs.ok, true);
  assert.equal(crossDs.value.top.role, "support");
  assert.equal(crossDs.value.bottom.role, "primary");
});

test("selectSubviewTrack enters track-pair summary after selecting two ds tracks", () => {
  const afterPrimary = __testSelectSubviewTrack({
    subview: {
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
    },
    trackRole: "primary",
  });
  assert.equal(afterPrimary.selectedTrackARole, "primary");
  assert.equal(afterPrimary.summary, null);
  const afterSupport = __testSelectSubviewTrack({
    subview: afterPrimary,
    trackRole: "support",
  });
  assert.equal(afterSupport.selectedTrackARole, "primary");
  assert.equal(afterSupport.selectedTrackBRole, "support");
  assert.equal(afterSupport.summary.mode, "track-pair");
  assert.equal(afterSupport.summary.topTrack.role, "support");
  assert.equal(afterSupport.summary.bottomTrack.role, "primary");
});

test("enterSubviewFromTrackSelections copies main-track scale prefs into subviewTrackView", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      trackView: {
        supportDsCtgLen: 10000,
        minTickUnitKb: 500,
        maxTickCount: 15,
        alignmentLength: 22222,
        mapq: 44,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      subview: {
        selectedTrackSelections: [
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        selectedTrackARole: "primary",
        selectedTrackBRole: "support",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testEnterSubviewFromTrackSelections(host, store);

  assert.deepEqual(store.getState().assembly.subviewTrackView, {
    supportDsCtgLen: 10000,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 15,
    alignmentLength: 22222,
    block_length: 22222,
    mapq: 44,
  });
});

test("enterSubviewFromTrackSelections restores persisted subview anchors for track pairs", () => {
  const host = {
    closest() {
      return null;
    },
  };
  const summary = {
    mode: "track-pair",
    topTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
    bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
  };
  const storedAnchorState = {
    activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
    manualAnchors: [{
      manualAnchorId: "manual:support:120:primary:220",
      endpointA: { endpointKey: "role-primary:ctg-2", contigId: 2, cutBp: 220, lengthBp: 1000 },
      endpointB: { endpointKey: "role-support:ctg-30:ds-22", contigId: 30, cutBp: 120, lengthBp: 900 },
    }],
  };
  let state = createState({
    assembly: {
      subviewAnchorStateByKey: setSubviewAnchorStateForSummary(
        {},
        summary,
        "Chr01",
        storedAnchorState,
      ),
      subview: {
        selectedTrackSelections: [
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
        ],
        selectedTrackARole: "support",
        selectedTrackBRole: "primary",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testEnterSubviewFromTrackSelections(host, store);

  assert.deepEqual(store.getState().assembly.subview.activeAnchors, storedAnchorState.activeAnchors);
  assert.equal(store.getState().assembly.subview.manualAnchors[0]?.manualAnchorId, storedAnchorState.manualAnchors[0].manualAnchorId);
  assert.deepEqual(
    store.getState().assembly.subview.manualAnchors[0]
      ? [
        store.getState().assembly.subview.manualAnchors[0].endpointA.cutBp,
        store.getState().assembly.subview.manualAnchors[0].endpointB.cutBp,
      ]
      : [],
    [220, 120],
  );
});

test("enterSubviewFromTrackSelections starts pairwise evidence loading for ds track pairs", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    session: {
      workspacePath: "",
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      trackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 500,
        maxTickCount: 15,
        alignmentLength: 10000,
        mapq: 0,
      },
      chrCtgs: [{ assemblyCtgId: 2, name: "primary-bottom", datasetId: 11, totalLength: 5000 }],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-top", datasetId: 22, totalLength: 4000 }],
      subview: {
        selectedTrackSelections: [
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
        ],
        selectedTrackARole: "support",
        selectedTrackBRole: "primary",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testEnterSubviewFromTrackSelections(host, store);

  const evidence = store.getState().assembly.subview.pairwiseEvidence;
  assert.equal(evidence?.status, "loading");
  assert.equal(
    evidence?.key,
    "track-pair:support:mother:22:30|primary:2",
  );
  assert.notEqual(String(evidence?.requestKey || ""), "");
});

test("swap subview track order keeps persisted anchors visible", () => {
  const host = {
    closest() {
      return null;
    },
  };
  const summary = {
    mode: "track-pair",
    topTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
    bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
  };
  const storedAnchorState = {
    activeAnchors: [{ hitKey: "hit-1", edge: "right" }],
    manualAnchors: [{
      manualAnchorId: "manual:support:150:primary:250",
      endpointA: { endpointKey: "role-primary:ctg-2", contigId: 2, cutBp: 250, lengthBp: 1000 },
      endpointB: { endpointKey: "role-support:ctg-30:ds-22", contigId: 30, cutBp: 150, lengthBp: 900 },
    }],
  };
  let state = createState({
    assembly: {
      subviewAnchorStateByKey: setSubviewAnchorStateForSummary(
        {},
        summary,
        "Chr01",
        storedAnchorState,
      ),
      subview: {
        summary,
        activeAnchors: [],
        manualAnchors: [],
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testHandleSubviewSwapTrackOrder(host, store);

  assert.equal(store.getState().assembly.subview.summary.topTrack.role, "primary");
  assert.deepEqual(store.getState().assembly.subview.activeAnchors, storedAnchorState.activeAnchors);
  assert.equal(store.getState().assembly.subview.manualAnchors[0]?.manualAnchorId, storedAnchorState.manualAnchors[0].manualAnchorId);
  assert.deepEqual(
    store.getState().assembly.subview.manualAnchors[0]
      ? [
        store.getState().assembly.subview.manualAnchors[0].endpointA.cutBp,
        store.getState().assembly.subview.manualAnchors[0].endpointB.cutBp,
      ]
      : [],
    [250, 150],
  );
});

test("track label selection inherits main-track scale prefs when entering subview-track", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      trackView: {
        supportDsCtgLen: 15000,
        minTickUnitKb: 500,
        maxTickCount: 15,
        alignmentLength: 100000,
        mapq: 44,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      subview: {
        selectedTrackSelections: [
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        selectedTrackARole: "support",
        selectedTrackBRole: "",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testHandleTrackSubviewTrackSelection(host, store, {
    trackRole: "primary",
    source: "mother",
    datasetId: null,
    isMirror: false,
  });

  assert.equal(store.getState().assembly.subview.summary?.mode, "track-pair");
  assert.deepEqual(store.getState().assembly.subviewTrackView, {
    supportDsCtgLen: 15000,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 15,
    alignmentLength: 100000,
    block_length: 100000,
    mapq: 44,
  });
});

test("selectSubviewTrack keeps mirror source when selecting support first then primary", () => {
  const afterSupportMirror = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    source: "mirror",
    datasetId: 22,
    isMirror: true,
  });
  assert.equal(afterSupportMirror.selectedTrackARole, "support");
  assert.equal(afterSupportMirror.selectedTrackBRole, "");
  assert.equal(afterSupportMirror.selectedTrackBSource, "mirror");
  assert.equal(afterSupportMirror.selectedTrackBDatasetId, 22);
  assert.equal(afterSupportMirror.selectedTrackBIsMirror, true);

  const afterPrimary = __testSelectSubviewTrack({
    subview: afterSupportMirror,
    trackRole: "primary",
  });

  assert.equal(afterPrimary.selectedTrackBSource, "mirror");
  assert.equal(afterPrimary.selectedTrackBDatasetId, 22);
  assert.equal(afterPrimary.selectedTrackBIsMirror, true);
  assert.equal(afterPrimary.summary?.mode, "track-pair");
  assert.equal(afterPrimary.summary?.topTrack?.role, "support");
  assert.equal(afterPrimary.summary?.bottomTrack?.role, "primary");
});

test("selectSubviewTrack supports mirror plus mother support tracks", () => {
  const afterMirror = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    source: "mirror",
    datasetId: 33,
    isMirror: true,
  });
  const afterMother = __testSelectSubviewTrack({
    subview: afterMirror,
    trackRole: "support",
    source: "mother",
    datasetId: 22,
    isMirror: false,
  });

  assert.equal(afterMother.selectedTrackARole, "support");
  assert.equal(afterMother.selectedTrackBRole, "support");
  assert.equal(afterMother.summary?.mode, "track-pair");
  assert.equal(afterMother.summary?.topTrack?.role, "support");
  assert.equal(afterMother.summary?.topTrack?.source, "mirror");
  assert.equal(afterMother.summary?.topTrack?.datasetId, 33);
  assert.equal(afterMother.summary?.bottomTrack?.role, "support");
  assert.equal(afterMother.summary?.bottomTrack?.source, "mother");
  assert.equal(afterMother.summary?.bottomTrack?.datasetId, 22);
});

test("selectSubviewTrack supports selecting two mirror support tracks", () => {
  const afterMirror22 = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    source: "mirror",
    datasetId: 22,
    isMirror: true,
  });
  const afterMirror33 = __testSelectSubviewTrack({
    subview: afterMirror22,
    trackRole: "support",
    source: "mirror",
    datasetId: 33,
    isMirror: true,
  });

  assert.equal(afterMirror33.summary?.mode, "track-pair");
  assert.equal(afterMirror33.summary?.topTrack?.role, "support");
  assert.equal(afterMirror33.summary?.topTrack?.source, "mirror");
  assert.equal(afterMirror33.summary?.topTrack?.datasetId, 22);
  assert.equal(afterMirror33.summary?.bottomTrack?.role, "support");
  assert.equal(afterMirror33.summary?.bottomTrack?.source, "mirror");
  assert.equal(afterMirror33.summary?.bottomTrack?.datasetId, 33);
});

test("swapSubviewSummaryOrder swaps top/bottom for both 2-contig and track-pair modes", () => {
  const swappedCtgMode = __testSwapSubviewSummaryOrder({
    subview: {
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
      message: "",
      error: "old-error",
    },
  });
  assert.equal(swappedCtgMode.summary?.top?.contigId, 2);
  assert.equal(swappedCtgMode.summary?.top?.role, "primary");
  assert.equal(swappedCtgMode.summary?.bottom?.contigId, 30);
  assert.equal(swappedCtgMode.summary?.bottom?.role, "support");
  assert.equal(swappedCtgMode.error, "");
  assert.match(swappedCtgMode.message, /上下轨道顺序/);

  const swappedTrackMode = __testSwapSubviewSummaryOrder({
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "support" },
        bottomTrack: { role: "primary" },
      },
      message: "",
      error: "old-error",
    },
  });
  assert.equal(swappedTrackMode.summary?.topTrack?.role, "primary");
  assert.equal(swappedTrackMode.summary?.bottomTrack?.role, "support");
  assert.equal(swappedTrackMode.error, "");
  assert.match(swappedTrackMode.message, /上下轨道顺序/);
});

test("swap track order keeps subview drag offsets by swapping top/bottom slots", () => {
  const swapped = __testSwapSubviewTrackDragOffsetsForSummarySwap([
    { slot: "top", contigId: 101, offsetBp: 321.5 },
    { slot: "bottom", contigId: 202, offsetPx: -44.5 },
  ]);

  assert.deepEqual(swapped, [
    { slot: "top", contigId: 202, offsetPx: -44.5 },
    { slot: "bottom", contigId: 101, offsetBp: 321.5 },
  ]);
});

test("selectSubviewTrack clears ctg-mode selection to keep subview modes mutually exclusive", () => {
  const next = __testSelectSubviewTrack({
    subview: {
      selectedAContigId: 30,
      selectedARole: "support",
      selectedBContigId: 2,
      selectedBRole: "primary",
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
    },
    trackRole: "primary",
  });
  assert.equal(next.selectedTrackARole, "primary");
  assert.equal(next.selectedAContigId, null);
  assert.equal(next.selectedBContigId, null);
  assert.equal(next.summary, null);
});

test("selectSubviewCandidate clears track-mode selection to keep subview modes mutually exclusive", () => {
  const next = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: 22,
    primaryCtgs: [{ assemblyCtgId: 2, name: "ctg-alpha" }],
    supportCtgs: [{ assemblyCtgId: 30, name: "support-ctg" }],
    subview: {
      selectedTrackARole: "support",
      selectedTrackBRole: "primary",
      trackPairHiddenCtgs: [{ trackRole: "support", contigId: 30 }],
      summary: {
        mode: "track-pair",
        topTrack: { role: "support" },
        bottomTrack: { role: "primary" },
      },
    },
    trackRole: "primary",
    contigId: 2,
  });
  assert.equal(next.selectedTrackARole, "");
  assert.equal(next.selectedTrackBRole, "");
  assert.deepEqual(next.trackPairHiddenCtgs, []);
  assert.equal(next.summary, null);
});

test("removeSubviewCandidate clears subview-ctg summary when remaining candidates are fewer than two", () => {
  const next = __testRemoveSubviewCandidate({
    subview: {
      selectedAContigId: 30,
      selectedARole: "support",
      selectedBContigId: 2,
      selectedBRole: "primary",
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
    },
    trackRole: "support",
    contigId: 30,
  });
  assert.equal(next.selectedAContigId, 2);
  assert.equal(next.selectedBContigId, null);
  assert.equal(next.summary, null);
});

test("removeSubviewTrackSelection clears subview-track summary when remaining tracks are fewer than two", () => {
  const next = __testRemoveSubviewTrackSelection({
    subview: {
      selectedTrackARole: "support",
      selectedTrackBRole: "primary",
      trackPairHiddenCtgs: [{ trackRole: "support", contigId: 30 }],
      summary: {
        mode: "track-pair",
        topTrack: { role: "support" },
        bottomTrack: { role: "primary" },
      },
    },
    trackRole: "support",
  });
  assert.equal(next.selectedTrackARole, "primary");
  assert.equal(next.selectedTrackBRole, "");
  assert.deepEqual(next.trackPairHiddenCtgs, []);
  assert.equal(next.summary, null);
});

test("removeSubviewTrackSelection can remove one support selection by source+dataset", () => {
  const next = __testRemoveSubviewTrackSelection({
    subview: {
      selectedTrackSelections: [
        { role: "support", source: "mirror", datasetId: 33, isMirror: true },
        { role: "support", source: "mother", datasetId: 22, isMirror: false },
      ],
      summary: {
        mode: "track-pair",
        topTrack: { role: "support", source: "mirror", datasetId: 33, isMirror: true },
        bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
      },
    },
    trackRole: "support",
    source: "mirror",
    datasetId: 33,
    isMirror: true,
  });

  assert.equal(next.selectedTrackSelections?.length, 1);
  assert.equal(next.selectedTrackSelections?.[0]?.role, "support");
  assert.equal(next.selectedTrackSelections?.[0]?.source, "mother");
  assert.equal(next.selectedTrackSelections?.[0]?.datasetId, 22);
  assert.equal(next.summary, null);
});

test("buildSubviewSummaryFromTrackSelections accepts support-support selection", () => {
  const result = __testBuildSubviewSummaryFromTrackSelections({
    subview: {
      selectedTrackSelections: [
        { role: "support", source: "mirror", datasetId: 33, isMirror: true },
        { role: "support", source: "mother", datasetId: 22, isMirror: false },
      ],
    },
  });
  assert.equal(result.ok, true);
  assert.equal(result.value?.mode, "track-pair");
  assert.equal(result.value?.topTrack?.role, "support");
  assert.equal(result.value?.topTrack?.source, "mirror");
  assert.equal(result.value?.topTrack?.datasetId, 33);
  assert.equal(result.value?.bottomTrack?.role, "support");
  assert.equal(result.value?.bottomTrack?.source, "mother");
  assert.equal(result.value?.bottomTrack?.datasetId, 22);
});

test("subview-track mode renders only the selected phased track items", () => {
  const html = renderAssemblyPage(createState({
    assembly: {
      subview: {
        summary: {
          mode: "track-pair",
          topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          bottomTrack: { role: "primary" },
        },
        selectedTrackSelections: [
          { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          { role: "primary" },
        ],
      },
      phasedChrTracks: [
        {
          phasedTrackId: 101,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
        },
      ],
    },
  }));
  const topSlotMarkup = html.match(/data-subview-track-slot="top"[\s\S]*?data-subview-track-slot="bottom"/)?.[0] || "";

  assert.match(topSlotMarkup, /data-subview-track-role="phased"/);
  assert.match(topSlotMarkup, /data-subview-contig-id="2"/);
  assert.match(html, /data-subview-track-pair-phased-track-id="101"/);
  assert.match(html, /data-subview-track-pair-phased-track-item-id="9001"/);
  assert.match(html, /data-subview-track-pair-phased-haplotype-key="A"/);
  assert.doesNotMatch(topSlotMarkup, /data-subview-contig-id="8"/);
});

test("subview-ctg mode exposes phased context metadata for append menus", () => {
  const html = renderAssemblyPage(createState({
    assembly: {
      isChrPhased: true,
      subview: {
        summary: {
          mode: "2-contig",
          top: { contigId: 2, role: "phased", contigName: "ctg-alpha" },
          bottom: { contigId: 8, role: "primary", contigName: "ctg-beta" },
        },
      },
      phasedChrTracks: [
        {
          phasedTrackId: 101,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
        },
      ],
    },
  }));
  const topGroup = html.match(
    /data-subview-track-pair-role="phased"[\s\S]*?data-subview-track-slot="top"[\s\S]*?<\/g>/,
  )?.[0] || "";

  assert.match(topGroup, /data-subview-track-pair-role="phased"/);
  assert.match(topGroup, /data-subview-track-pair-contig-id="2"/);
  assert.match(topGroup, /data-subview-track-pair-phased-track-id="101"/);
  assert.match(topGroup, /data-subview-track-pair-phased-track-item-id="9001"/);
  assert.match(topGroup, /data-subview-track-pair-phased-haplotype-key="A"/);
});

test("subview-track mode renders phased lanes in primary visual order", () => {
  const html = renderAssemblyPage(createState({
    assembly: {
      chrCtgs: [
        { assemblyCtgId: 11, name: "left-primary", assignedChrName: "Chr01", totalLength: 5000, anchorStart: 100 },
        { assemblyCtgId: 16, name: "right-primary", assignedChrName: "Chr01", totalLength: 2000, anchorStart: 500 },
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
      subview: {
        summary: {
          mode: "track-pair",
          topTrack: { role: "primary" },
          bottomTrack: { role: "phased", phasedTrackId: 102, haplotypeKey: "B" },
        },
        selectedTrackSelections: [
          { role: "primary" },
          { role: "phased", phasedTrackId: 102, haplotypeKey: "B" },
        ],
      },
    },
  }));
  const bottomItems = [
    ...html.matchAll(
      /data-subview-track-slot="bottom"[^>]*data-subview-contig-id="([^"]+)"[^>]*data-subview-rect-x="([^"]+)"/g,
    ),
  ].map((match) => ({
    contigId: Number(match[1]),
    x: Number(match[2]),
  }));

  assert.equal(bottomItems.length, 2);
  assert.deepEqual(bottomItems.map((item) => item.contigId), [11, 16]);
  assert.ok(bottomItems[0].x < bottomItems[1].x, `expected phased lane left-to-right order, got ${JSON.stringify(bottomItems)}`);
});

test("context menu shows enter-subview action when exactly two candidates are selected", () => {
  const store = createStore(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: null,
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    memberNode: null,
    store,
    host,
  });
  assert.ok(items.every((item) => item.label !== "进入Subview-ctg"));
});

test("context menu shows local subview delete action in track-pair mode", () => {
  const store = createStore(
    createState({
      assembly: {
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 },
            ],
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    deletedCtgContext: null,
    memberNode: null,
    subviewTrackPairContext: {
      trackRole: "support",
      assemblyCtgId: 30,
    },
    store,
    host,
  });
  assert.ok(items.some((item) => item.label === "在Subview中删除 contig（仅当前视图）"));
});

test("context menu shows flip action for phased ctg in subview track-pair mode", () => {
  const store = createStore(
    createState({
      assembly: {
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 },
            ],
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
            bottomTrack: { role: "primary" },
          },
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    deletedCtgContext: null,
    memberNode: null,
    subviewTrackPairContext: {
      trackRole: "phased",
      assemblyCtgId: 2,
      slot: "top",
    },
    store,
    host,
  });
  assert.ok(items.some((item) => item.label === "翻转 contig"));
});
