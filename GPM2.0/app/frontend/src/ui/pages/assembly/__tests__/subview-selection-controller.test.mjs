import test from "node:test";
import assert from "node:assert/strict";

import { createSubviewSelectionController } from "../subview-selection-controller.js";
import {
  activateSubviewHistory,
  commitSubviewHistoryOperation,
} from "../subview-history-state.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(patch) {
      state = {
        ...state,
        ...patch,
      };
    },
  };
}

function createCompositionBackedState() {
  const compositionKey = "composition:Chr01";
  const composition = {
    members: [
      {
        entityKey: "assembly:91",
        sourceKey: "support:22:mother:0:0:",
        assemblyCtgId: 91,
        source: { role: "support", datasetId: 22, sourceType: "mother" },
        label: "old-composition-ctg",
        lengthBp: 1_000,
        baseOrientation: "+",
        lane: "top",
        xBp: 0,
        flipped: false,
        order: 0,
      },
    ],
    layoutGapBp: 20_000,
    activeAnchors: [],
    manualAnchors: [],
  };
  const compositionSnapshot = { kind: "composition", composition };
  return {
    locale: "zh",
    initializer: {
      datasets: [
        { datasetId: 11, name: "primary" },
        { datasetId: 22, name: "support" },
      ],
    },
    assembly: {
      selectedChrName: "Chr01",
      supportDatasetId: 22,
      trackView: { alignmentLength: 1_000, mapq: 0 },
      subviewTrackView: { alignmentLength: 500, mapq: 10 },
      chrCtgs: [
        { assemblyCtgId: 2, name: "primary-2", assignedChrName: "Chr01", totalLength: 2_000 },
      ],
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "support-30", assignedChrName: "Chr01", totalLength: 3_000 },
        { assemblyCtgId: 91, name: "old-composition-ctg", assignedChrName: "Chr01", totalLength: 1_000 },
      ],
      subviewTrackDragOffsets: [{ trackRole: "support", contigId: 91, offsetPx: 40 }],
      subviewCompositionViewport: { bpPerPx: 4, leftBp: 120, topPx: 8 },
      subviewHistoryByKey: {
        [compositionKey]: {
          version: 2,
          pairKey: compositionKey,
          current: compositionSnapshot,
          default: compositionSnapshot,
          past: [],
          forward: [],
          viewport: { bpPerPx: 4, leftBp: 120, topPx: 8 },
          updatedAt: "2026-09-07T00:00:00.000Z",
        },
      },
      subview: {
        mode: "composition",
        historyKey: compositionKey,
        summary: {
          mode: "composition",
          members: composition.members,
          layoutGapBp: composition.layoutGapBp,
        },
        activeAnchors: [],
        manualAnchors: [],
        pairwiseEvidence: {
          key: "old-composition-evidence",
          requestKey: "old-composition-request",
          status: "loading",
        },
      },
    },
  };
}

function createEntryHarness(initialState) {
  const pairwiseBuilds = [];
  const pairwiseLoads = [];
  const persisted = [];
  const invalidations = [];
  const transientResets = [];
  const toolsCloses = [];
  const renderCalls = [];
  const store = createStore(initialState);
  const controller = createSubviewSelectionController({
    buildInitialSubviewPairwiseEvidence(summary, trackView, previousEvidence) {
      pairwiseBuilds.push({ summary, trackView, previousEvidence });
      return {
        key: `new-${summary.mode}-evidence`,
        requestKey: `new-${summary.mode}-request`,
        status: "loading",
      };
    },
    getCurrentProject() {
      return { primaryDatasetId: 11 };
    },
    closeSubviewTools() {
      toolsCloses.push("close");
    },
    invalidateSubviewPairwiseEvidence() {
      invalidations.push("invalidate");
    },
    loadSubviewPairwiseEvidence(_host, _store, summary) {
      pairwiseLoads.push(summary);
    },
    persistProjectAssemblyViewStateFromStore() {
      persisted.push(store.getState().assembly.subview.historyKey);
    },
    rerenderAssemblyMainTab() {
      renderCalls.push("main");
    },
    rerenderSubviewPanel() {
      renderCalls.push("subview");
    },
    resetSubviewTransientState() {
      transientResets.push("reset");
    },
  });
  return {
    controller,
    invalidations,
    pairwiseBuilds,
    pairwiseLoads,
    persisted,
    renderCalls,
    store,
    toolsCloses,
    transientResets,
  };
}

function withSavedTwoContigHistory(state) {
  const compositionSubview = state.assembly.subview;
  const compositionOffsets = state.assembly.subviewTrackDragOffsets;
  const compositionViewport = state.assembly.subviewCompositionViewport;
  const pairSubview = {
    mode: "2-contig",
    selectedAContigId: 2,
    selectedARole: "primary",
    selectedBContigId: 30,
    selectedBRole: "support",
    activeAnchors: [],
    manualAnchors: [],
    flippedCtgs: [],
    trackPairHiddenCtgs: [],
    trackPairSelectedCtgs: [],
    summary: {
      mode: "2-contig",
      top: { contigId: 30, role: "support" },
      bottom: { contigId: 2, role: "primary" },
    },
  };
  const activated = activateSubviewHistory({ ...state.assembly, subview: pairSubview }, { now: 1 });
  const committed = commitSubviewHistoryOperation(activated.assembly, {
    nextSubview: {
      ...activated.assembly.subview,
      flippedCtgs: [{ slot: "top", contigId: 30 }],
    },
    nextSubviewTrackDragOffsets: [{ slot: "top", contigId: 30, offsetBp: 25 }],
    operation: { kind: "flip-contig" },
    now: 2,
  });
  return {
    ...state,
    assembly: {
      ...committed.assembly,
      subview: compositionSubview,
      subviewTrackDragOffsets: compositionOffsets,
      subviewCompositionViewport: compositionViewport,
    },
  };
}

test("removing a Subview track selection refreshes main-track and Subview selection styling", () => {
  const renderCalls = [];
  const controller = createSubviewSelectionController({
    rerenderAssemblyMainTab() {
      renderCalls.push("main");
    },
    rerenderSubviewPanel() {
      renderCalls.push("subview");
    },
  });
  const store = createStore({
    locale: "zh",
    assembly: {
      subview: {
        mode: "track-pair",
        selectedTrackSelections: [
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        summary: {
          mode: "track-pair",
          topTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
          bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
        },
      },
      subviewTrackDragOffsets: [{ trackRole: "primary", offsetPx: 20 }],
    },
  });

  controller.handleSubviewTrackSelectionRemoval({}, store, {
    trackRole: "primary",
    source: "mother",
    datasetId: null,
    isMirror: false,
  });

  const assembly = store.getState().assembly;
  assert.deepEqual(assembly.subview.selectedTrackSelections, [
    { role: "support", source: "mother", datasetId: 22, isMirror: false },
  ]);
  assert.equal(assembly.subview.summary, null);
  assert.deepEqual(assembly.subviewTrackDragOffsets, []);
  assert.deepEqual(renderCalls, ["main", "subview"]);
});

test("clearing a custom composition resets the active Subview once and closes its tools", () => {
  const harness = createEntryHarness(createCompositionBackedState());

  assert.equal(harness.controller.handleSubviewClear({}, harness.store), true);

  const assembly = harness.store.getState().assembly;
  assert.equal(assembly.subview.mode, "2-contig");
  assert.equal(assembly.subview.summary, null);
  assert.equal(assembly.subview.pairwiseEvidence, undefined);
  assert.deepEqual(assembly.subviewCompositionViewport, {});
  assert.deepEqual(assembly.subviewTrackDragOffsets, []);
  assert.equal(assembly.subviewHistoryByKey["composition:Chr01"], undefined);
  assert.deepEqual(harness.invalidations, ["invalidate"]);
  assert.deepEqual(harness.transientResets, ["reset"]);
  assert.deepEqual(harness.toolsCloses, ["close"]);
  assert.deepEqual(harness.renderCalls, ["main", "subview"]);
  assert.equal(harness.persisted.length, 1);

  assert.equal(harness.controller.handleSubviewClear({}, harness.store), false);
  assert.deepEqual(harness.invalidations, ["invalidate"]);
  assert.deepEqual(harness.toolsCloses, ["close"]);
  assert.equal(harness.persisted.length, 1);
});

test("the shared track-order action swaps a composition in one undoable step", () => {
  const harness = createEntryHarness(createCompositionBackedState());

  harness.controller.handleSubviewSwapTrackOrder({}, harness.store);

  let assembly = harness.store.getState().assembly;
  assert.equal(assembly.subview.summary.members[0].lane, "bottom");
  assert.equal(assembly.subview.summary.members[0].xBp, 0);
  assert.equal(assembly.subview.summary.members[0].flipped, false);
  assert.equal(assembly.subviewHistoryByKey["composition:Chr01"].past.length, 1);

  harness.controller.handleSubviewHistoryRollback({}, harness.store);
  assembly = harness.store.getState().assembly;
  assert.equal(assembly.subview.summary.members[0].lane, "top");
  assert.equal(assembly.subview.summary.members[0].xBp, 0);
  assert.equal(assembly.subview.summary.members[0].flipped, false);
});

test("two-contig quick entry clears the active graph and creates a fresh default pair", () => {
  const compositionKey = "composition:Chr01";
  const harness = createEntryHarness(withSavedTwoContigHistory(createCompositionBackedState()));

  harness.controller.handleTrackSubviewCandidateSelection({}, harness.store, {
    trackRole: "primary",
    contigId: 2,
  });

  const pendingAssembly = harness.store.getState().assembly;
  assert.equal(pendingAssembly.subview.mode, "2-contig");
  assert.equal(pendingAssembly.subview.summary, null);
  assert.equal(pendingAssembly.subview.historyKey, undefined);
  assert.equal(pendingAssembly.subview.pairwiseEvidence, undefined);
  assert.deepEqual(pendingAssembly.subviewCompositionViewport, {});
  assert.equal(pendingAssembly.subviewHistoryByKey[compositionKey], undefined);
  assert.deepEqual(harness.invalidations, ["invalidate"]);
  assert.deepEqual(harness.transientResets, ["reset"]);
  assert.equal(harness.persisted.length, 1);

  harness.controller.handleTrackSubviewCandidateSelection({}, harness.store, {
    trackRole: "support",
    contigId: 30,
  });

  const assembly = harness.store.getState().assembly;
  assert.equal(assembly.subview.mode, "2-contig");
  assert.equal(assembly.subview.summary.mode, "2-contig");
  assert.deepEqual(assembly.subview.summary.top, { contigId: 30, role: "support" });
  assert.deepEqual(assembly.subview.summary.bottom, { contigId: 2, role: "primary" });
  assert.equal(assembly.subview.historyKey, undefined);
  assert.equal(
    Object.keys(assembly.subviewHistoryByKey).filter((key) => !key.startsWith("composition:")).length,
    1,
  );
  assert.deepEqual(assembly.subview.flippedCtgs, []);
  assert.deepEqual(assembly.subview.activeAnchors, []);
  assert.deepEqual(assembly.subview.manualAnchors, []);
  assert.deepEqual(assembly.subviewTrackDragOffsets, []);
  assert.deepEqual(assembly.subviewCompositionViewport, {});
  assert.equal(assembly.subview.pairwiseEvidence.key, "new-2-contig-evidence");
  assert.equal(assembly.subviewHistoryByKey[compositionKey], undefined);
  assert.equal(harness.pairwiseBuilds.length, 1);
  assert.equal(harness.pairwiseBuilds[0].summary.mode, "2-contig");
  assert.equal(harness.pairwiseBuilds[0].previousEvidence, undefined);
  assert.deepEqual(harness.pairwiseLoads.map((summary) => summary.mode), ["2-contig"]);
  assert.equal(harness.persisted.length, 2);
});

test("two-track quick entry clears the active graph and creates fresh default tracks", () => {
  const compositionKey = "composition:Chr01";
  const harness = createEntryHarness(createCompositionBackedState());

  harness.controller.handleTrackSubviewTrackSelection({}, harness.store, {
    trackRole: "primary",
  });

  const pendingAssembly = harness.store.getState().assembly;
  assert.equal(pendingAssembly.subview.mode, "track-pair");
  assert.equal(pendingAssembly.subview.summary, null);
  assert.equal(pendingAssembly.subview.historyKey, undefined);
  assert.equal(pendingAssembly.subview.pairwiseEvidence, undefined);
  assert.deepEqual(pendingAssembly.subviewCompositionViewport, {});
  assert.equal(pendingAssembly.subviewHistoryByKey[compositionKey], undefined);
  assert.deepEqual(harness.invalidations, ["invalidate"]);
  assert.deepEqual(harness.transientResets, ["reset"]);
  assert.equal(harness.persisted.length, 1);

  harness.controller.handleTrackSubviewTrackSelection({}, harness.store, {
    trackRole: "support",
    source: "mother",
    datasetId: 22,
  });

  const assembly = harness.store.getState().assembly;
  assert.equal(assembly.subview.mode, "track-pair");
  assert.equal(assembly.subview.summary.mode, "track-pair");
  assert.deepEqual(assembly.subview.summary.topTrack, {
    role: "support",
    source: "mother",
    datasetId: 22,
    isMirror: false,
  });
  assert.deepEqual(assembly.subview.summary.bottomTrack, {
    role: "primary",
    source: "mother",
    datasetId: null,
    isMirror: false,
  });
  assert.equal(assembly.subview.historyKey, undefined);
  assert.equal(
    Object.keys(assembly.subviewHistoryByKey).filter((key) => !key.startsWith("composition:")).length,
    1,
  );
  assert.deepEqual(assembly.subviewTrackDragOffsets, []);
  assert.deepEqual(assembly.subview.activeAnchors, []);
  assert.deepEqual(assembly.subview.manualAnchors, []);
  assert.deepEqual(assembly.subviewCompositionViewport, {});
  assert.equal(assembly.subview.pairwiseEvidence.key, "new-track-pair-evidence");
  assert.equal(assembly.subviewHistoryByKey[compositionKey], undefined);
  assert.equal(harness.pairwiseBuilds.length, 1);
  assert.equal(harness.pairwiseBuilds[0].summary.mode, "track-pair");
  assert.equal(harness.pairwiseBuilds[0].previousEvidence, undefined);
  assert.deepEqual(harness.pairwiseLoads.map((summary) => summary.mode), ["track-pair"]);
  assert.equal(harness.persisted.length, 2);
});
