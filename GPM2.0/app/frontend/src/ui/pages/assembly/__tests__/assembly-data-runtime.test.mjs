import { beginAssemblyViewRequest, currentAssemblyViewRequest } from "../assembly-view-request.js";
import test from "node:test";
import assert from "node:assert/strict";

import { backfillFinalPathOriginIds, handleNewSequenceRowAction, loadAssemblyView, selectChromosome, selectCtg } from "../assembly-data-runtime.js";
import { normalizeFinalPathByChr } from "../final-path-state.js";

test("handleNewSequenceRowAction ignores removed add-seq-to-ctg action", async () => {
  const store = {
    getState() {
      return {
        assembly: {
          selectedCtgId: 7,
        },
      };
    },
  };
  const calls = [];

  await handleNewSequenceRowAction(
    {},
    store,
    { action: "add-seq-to-ctg", assemblySeqId: 11, seqName: "Seq11" },
    {
      async applyEditorAction(_host, _store, payload) {
        calls.push(payload);
      },
      rerender() {
        throw new Error("rerender should not run for removed add-seq-to-ctg path");
      },
      setAssemblyActionFeedback() {
        throw new Error("setAssemblyActionFeedback should not run for removed add-seq-to-ctg path");
      },
    },
  );

  assert.deepEqual(calls, []);
});

test("selectCtg preserves the current viewport when requested by track clicks", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    assembly: {
      loading: false,
      selectedCtgId: 8,
      trackSelectedCtgIds: [8],
      selectedDeletedCtgRecordIds: [1001],
      summary: "",
    },
  };
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
  const pendingFocusModes = [];
  let normalizeCalls = 0;
  let rerenderCount = 0;

  await selectCtg(host, store, 30, { preserveViewport: true }, {
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeTrackFocusMode() {
      normalizeCalls += 1;
      return "center";
    },
    rerender() {
      rerenderCount += 1;
    },
    setPendingTrackAutoFocusMode(mode) {
      pendingFocusModes.push(mode);
    },
  });

  assert.deepEqual(pendingFocusModes, [null]);
  assert.equal(normalizeCalls, 0);
  assert.equal(state.assembly.selectedCtgId, 30);
  assert.equal(state.assembly.loading, false);
  assert.equal(rerenderCount, 2);
});

test("selectChromosome clears stale data while loading and restores target history", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [] }],
    },
    assembly: {
      selectedChrName: "Chr09",
      chrCtgs: [{ assemblyCtgId: 199, name: "ptg000193l@Chr09" }],
      refTrackMembers: [{ assemblyCtgId: 2000101, name: "ref_Chr09" }],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-old" }],
      deletedCtgs: [{ deletedCtgRecordId: 12 }],
      trackSelectedCtgIds: [199],
      hiddenPrimaryCtgIds: [199],
      trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 199, offsetBp: 10 }],
      subviewTrackDragOffsets: [{ slot: "top", contigId: 199, offsetBp: 10 }],
      selectedDeletedCtgRecordIds: [12],
      selectedCtgId: 199,
      selectedMemberSeqId: 88,
      ctgDetail: { members: [{ assemblySeqId: 88 }] },
      editCandidates: { moveTargetCtgs: [{ assemblyCtgId: 199 }], addSeqCandidates: [] },
      mainViewHistory: {
        chrName: "Chr09",
        canUndo: true,
        canRedo: false,
        canReset: true,
        undoOperation: { kind: "rename-ctg", targetCount: 1, targetName: "old" },
        appliedOperationCount: 1,
      },
      subview: { summary: { mode: "ctg" }, trackPairHiddenCtgs: [], trackPairSelectedCtgs: [] },
    },
  };
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
  let resolveChrCtgs;
  const pending = new Promise((resolve) => {
    resolveChrCtgs = resolve;
  });
  const previousViewRequest = currentAssemblyViewRequest(store);
  const loadPromise = selectChromosome(host, store, "Chr10", {
    buildClearedSubviewState() {
      return { summary: null, trackPairHiddenCtgs: [], trackPairSelectedCtgs: [] };
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getMainViewHistoryStatus(payload) {
      assert.deepEqual(payload, {
        workspaceRoot: "/tmp/ws",
        projectId: 9,
        chrName: "Chr10",
      });
      return {
        projectId: 9,
        referenceChrId: 10,
        chrName: "Chr10",
        canUndo: true,
        canRedo: false,
        canReset: true,
        undoOperation: { kind: "flip-ctg", targetCount: 1, targetName: "Ctg8" },
        appliedOperationCount: 1,
        retainedOperationCount: 1,
      };
    },
    async listChrViewCtgs() {
      return pending;
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return { detail: { members: [] }, candidates: { moveTargetCtgs: [], addSeqCandidates: [] } };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    rerender() {},
  });

  assert.equal(state.assembly.selectedChrName, "Chr10");
  assert.deepEqual(state.assembly.chrCtgs, []);
  assert.deepEqual(state.assembly.trackSelectedCtgIds, []);
  assert.deepEqual(state.assembly.deletedCtgs, []);
  assert.equal(state.assembly.selectedCtgId, null);
  assert.equal(state.assembly.ctgDetail, null);
  assert.equal(state.assembly.mainViewHistory.canUndo, false);
  assert.deepEqual(state.assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 199, offsetBp: 10 },
  ]);
  // A queued authoritative refresh may finish while the next chr is loading.
  const latestOffsets = [
    ...state.assembly.trackDragOffsets,
    { trackRole: "primary", assemblyCtgId: 8, offsetBp: -25 },
  ];
  store.setState({ assembly: { ...state.assembly, trackDragOffsets: latestOffsets } });

  resolveChrCtgs({ items: [{ assemblyCtgId: 8, name: "ptg000008l@Chr10" }] });
  assert.notEqual(currentAssemblyViewRequest(store), previousViewRequest);
  await loadPromise;
  assert.deepEqual(state.assembly.trackDragOffsets, latestOffsets);
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 8, name: "ptg000008l@Chr10" }]);
  assert.deepEqual(state.assembly.mainViewHistory, {
    projectId: 9,
    referenceChrId: 10,
    chrName: "Chr10",
    canUndo: true,
    canRedo: false,
    canReset: true,
    undoOperation: { kind: "flip-ctg", targetCount: 1, targetName: "Ctg8" },
    redoOperation: null,
    appliedOperationCount: 1,
    retainedOperationCount: 1,
    invalidated: false,
    inFlight: false,
  });
});

test("selectChromosome ignores stale chromosome responses after a newer selection", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [] }],
    },
    assembly: {
      selectedChrName: "Chr09",
      chrCtgs: [{ assemblyCtgId: 199, name: "ptg000193l@Chr09" }],
      supportDatasetId: null,
      selectedCtgId: 199,
      selectedMemberSeqId: null,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: { summary: null, trackPairHiddenCtgs: [], trackPairSelectedCtgs: [] },
    },
  };
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
  let resolveChr10Ctgs;
  const chr10Pending = new Promise((resolve) => {
    resolveChr10Ctgs = resolve;
  });
  const loadPromise = selectChromosome(host, store, "Chr10", {
    buildClearedSubviewState() {
      return { summary: null, trackPairHiddenCtgs: [], trackPairSelectedCtgs: [] };
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async listChrViewCtgs() {
      return chr10Pending;
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return { detail: { members: [] }, candidates: { moveTargetCtgs: [], addSeqCandidates: [] } };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    rerender() {},
  });

  assert.equal(state.assembly.selectedChrName, "Chr10");
  state = {
    ...state,
    assembly: {
      ...state.assembly,
      selectedChrName: "Chr11",
      chrCtgs: [{ assemblyCtgId: 9, name: "ptg000009l@Chr11" }],
    },
  };

  resolveChr10Ctgs({ items: [{ assemblyCtgId: 8, name: "ptg000008l@Chr10" }] });
  await loadPromise;
  assert.equal(state.assembly.selectedChrName, "Chr11");
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 9, name: "ptg000009l@Chr11" }]);
});

test("loadAssemblyView accepts object assemblyStatus deps and loads chromosome data", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [] }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "chr1",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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
  const rerenders = [];

  const previousViewRequest = currentAssemblyViewRequest(store);
  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    assemblyStatus: {
      loadingChromosomes: "loading...",
      assemblyLoadFailed: "failed",
    },
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return { supportMirroredCtgs: [] };
    },
    getSupportDatasetOptions() {
      return [];
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7" }],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "chr1" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [{ assemblySeqId: 88 }] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender(_host, currentStore) {
      rerenders.push(currentStore.getState().assembly.summary);
    },
  });

  assert.equal(state.assembly.selectedChrName, "chr1");
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 7, name: "Ctg7" }]);
  assert.equal(state.assembly.selectedCtgId, 7);
  assert.equal(state.assembly.selectedMemberSeqId, 88);
  assert.equal(rerenders.length, 2);
  assert.notEqual(currentAssemblyViewRequest(store), previousViewRequest);
});

test("loadAssemblyView selects first support dataset when a project gains its first support ds", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [22] }],
      datasets: [{ datasetId: 22, label: "flye" }],
    },
    assembly: {
      selectedChrName: "chr1",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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
  const loadedSupportDatasetIds = [];

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    assemblyStatus: {
      loadingChromosomes: "loading...",
      assemblyLoadFailed: "failed",
    },
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return { supportDatasetId: null, supportMirroredCtgs: [] };
    },
    getSupportDatasetOptions() {
      return [{ datasetId: 22, label: "flye" }];
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7" }],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "chr1" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs(_workspaceRoot, _projectId, _chrName, datasetId) {
      loadedSupportDatasetIds.push(datasetId);
      return [{ assemblyCtgId: 22, name: "Support22" }];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.equal(state.assembly.supportDatasetId, 22);
  assert.deepEqual(loadedSupportDatasetIds, [22]);
  assert.deepEqual(state.assembly.supportChrCtgs, [{ assemblyCtgId: 22, name: "Support22" }]);
});

test("loadAssemblyView leaves ordinary assembly state when phased project has no chr tracks", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      activePhasedTrackKeyByChr: {},
      activeHitsTrackKeyByChr: {},
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return {};
    },
    getSupportDatasetOptions() {
      return [];
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7" }],
      };
    },
    async listPhasedChrTracks({ parentChrName }) {
      assert.equal(parentChrName, "Chr01");
      return { tracks: [] };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.deepEqual(state.assembly.phasedChrTracks, []);
  assert.equal(state.assembly.isChrPhased, false);
  assert.equal(state.assembly.activePhasedTrackKey, "");
  assert.equal(state.assembly.activeHitsTrackKey, "primary");
});

test("loadAssemblyView maps phased track items to current chromosome ctgs", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      activePhasedTrackKeyByChr: { Chr01: "B" },
      activeHitsTrackKeyByChr: { Chr01: "B" },
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return {};
    },
    getSupportDatasetOptions() {
      return [];
    },
    async listChrViewCtgs() {
      return {
        items: [
          { assemblyCtgId: 7, name: "Ctg7", totalLength: 900, hits: [{ ctgStart: 1, ctgEnd: 10 }] },
        ],
      };
    },
    async listPhasedChrTracks({ parentChrName }) {
      assert.equal(parentChrName, "Chr01");
      return {
        tracks: [
          {
            phasedTrackId: 2,
            haplotypeKey: "B",
            label: "Chr01B",
            displayOrder: 2,
            items: [
              { itemId: 11, phasedTrackId: 2, assemblyCtgId: 7, displayOrder: 2, gapBeforePx: 20 },
              { itemId: 12, phasedTrackId: 2, assemblyCtgId: 7, displayOrder: 1, gapBeforePx: 20 },
            ],
          },
          {
            phasedTrackId: 1,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [],
          },
        ],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.equal(state.assembly.isChrPhased, true);
  assert.equal(state.assembly.activePhasedTrackKey, "B");
  assert.equal(state.assembly.activeHitsTrackKey, "B");
  assert.deepEqual(
    state.assembly.phasedChrTracks.map((track) => track.haplotypeKey),
    ["A", "B"],
  );
  assert.deepEqual(
    state.assembly.phasedChrTracks[1].items.map((item) => item.itemId),
    [12, 11],
  );
  assert.equal(state.assembly.phasedChrTracks[1].items[0].sourceCtg.name, "Ctg7");
  assert.deepEqual(state.assembly.phasedChrTracks[1].items[0].sourceCtg.hits, [
    { ctgStart: 1, ctgEnd: 10 },
  ]);
});

test("loadAssemblyView restores all project offsets including unloaded chromosomes and duplicate phased items", async () => {
  const host = {};
  const otherChrOffsets = [
    { trackRole: "primary", assemblyCtgId: 90, offsetBp: -10 },
    { trackRole: "support", datasetId: 3, assemblyCtgId: 91, offsetBp: 40 },
    { trackRole: "phased", assemblyCtgId: 90, phasedTrackId: 9, phasedTrackItemId: 99, offsetBp: 20 },
  ];
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      activePhasedTrackKeyByChr: {},
      activeHitsTrackKeyByChr: {},
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return {
        trackDragOffsets: [
          ...otherChrOffsets,
          {
            trackRole: "phased",
            assemblyCtgId: 7,
            phasedTrackId: 2,
            phasedTrackItemId: 11,
            offsetBp: 120,
          },
          {
            trackRole: "phased",
            assemblyCtgId: 7,
            phasedTrackId: 2,
            phasedTrackItemId: 12,
            offsetBp: 260,
          },
        ],
      };
    },
    getSupportDatasetOptions() {
      return [];
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7", totalLength: 900 }],
      };
    },
    async listPhasedChrTracks({ parentChrName }) {
      assert.equal(parentChrName, "Chr01");
      return {
        tracks: [
          {
            phasedTrackId: 2,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [
              { itemId: 11, phasedTrackId: 2, assemblyCtgId: 7, displayOrder: 1 },
              { itemId: 12, phasedTrackId: 2, assemblyCtgId: 7, displayOrder: 2 },
            ],
          },
        ],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.deepEqual(
    state.assembly.trackDragOffsets
      .filter((entry) => entry.assemblyCtgId === 7)
      .slice()
      .sort((left, right) => left.phasedTrackItemId - right.phasedTrackItemId),
    [
      {
        trackRole: "phased",
        assemblyCtgId: 7,
        phasedTrackId: 2,
        phasedTrackItemId: 11,
        offsetBp: 120,
      },
      {
        trackRole: "phased",
        assemblyCtgId: 7,
        phasedTrackId: 2,
        phasedTrackItemId: 12,
        offsetBp: 260,
      },
    ],
  );
  assert.deepEqual(
    state.assembly.trackDragOffsets.filter((entry) => entry.assemblyCtgId !== 7)
      .sort((left, right) => left.offsetBp - right.offsetBp),
    otherChrOffsets.slice().sort((left, right) => left.offsetBp - right.offsetBp),
  );
});

test("loadAssemblyView stores refTrackMembers for the selected chromosome", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [] }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      refTrackMembers: [],
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return { supportMirroredCtgs: [] };
    },
    getSupportDatasetOptions() {
      return [];
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7" }],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async listReferenceTrackMembers({ chrName }) {
      assert.equal(chrName, "Chr01");
      return {
        items: [
          { sourceKind: "ref_segment", name: "ref_Chr01:1-5000", segmentStartBp: 1, segmentEndBp: 5000, totalLength: 5000, anchorStart: 1, refOrient: "+", hits: [] },
          { sourceKind: "ref_segment", name: "ref_Chr01:5101-10100", segmentStartBp: 5101, segmentEndBp: 10100, totalLength: 5000, anchorStart: 5101, refOrient: "+", hits: [] },
        ],
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.deepEqual(
    state.assembly.refTrackMembers.map((item) => item.segmentStartBp),
    [1, 5101],
  );
});

test("loadAssemblyView keeps ds tracks when reference-track loading fails", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [22] }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: 22,
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return {};
    },
    getSupportDatasetOptions() {
      return [{ datasetId: 22 }];
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "primary_ctg" }],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async listReferenceTrackMembers() {
      throw new Error("reference.fa missing");
    },
    async loadDatasetChrCtgs() {
      return [{ assemblyCtgId: 22, name: "support_ctg" }];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.equal(state.assembly.error, "");
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 7, name: "primary_ctg" }]);
  assert.deepEqual(state.assembly.supportChrCtgs, [{ assemblyCtgId: 22, name: "support_ctg" }]);
  assert.deepEqual(state.assembly.refTrackMembers, []);
});

test("loadAssemblyView hydrates persisted mirrored ctgs from project assembly view state", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [22] }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "chr1",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: 22,
      supportMirroredCtgs: [],
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    getSupportDatasetOptions() {
      return [{ datasetId: 22 }];
    },
    async getProjectAssemblyViewState({ workspaceRoot, projectId }) {
      assert.equal(workspaceRoot, "/tmp/ws");
      assert.equal(projectId, 9);
      return {
        supportDatasetId: 22,
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 250,
          maxTickCount: 15,
          alignmentLength: 10000,
          mapq: 30,
        },
        trackScrollState: {
          viewportKey: "9:chr1:7:22:10000:250:15:10000:30",
          scrollLeft: 320,
        },
        subviewTrackScrollState: {
          viewportKey: "9:chr1:primary:7:support:1909",
          scrollLeft: 180,
        },
        finalPathTrackScrollState: {
          viewportKey: "9:chr1:graph:250:15",
          scrollLeft: 260,
        },
        supportMirroredCtgs: [{ datasetId: 22, assemblyCtgId: 1909, name: "Ctg1909" }],
        hiddenPrimaryCtgIds: [7],
        hiddenPrimaryCtgIdsByChr: { chr1: [7] },
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 7, offsetBp: 120 }],
        subviewTrackDragOffsets: [{ slot: "top", contigId: 41, offsetBp: 80 }],
      };
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7" }],
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "chr1" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.deepEqual(state.assembly.supportMirroredCtgs, [
    { datasetId: 22, assemblyCtgId: 1909, name: "Ctg1909" },
  ]);
  assert.equal(state.assembly.supportDatasetId, 22);
  assert.deepEqual(state.assembly.trackView, {
    supportDsCtgLen: 10000,
    minTickUnitKb: 250,
    maxTickCount: 15,
    alignmentLength: 10000,
    mapq: 30,
  });
  assert.deepEqual(state.assembly.trackScrollState, {
    viewportKey: "9:chr1:7:22:10000:250:15:10000:30",
    scrollLeft: 320,
  });
  assert.deepEqual(state.assembly.subviewTrackScrollState, {
    viewportKey: "9:chr1:primary:7:support:1909",
    scrollLeft: 180,
  });
  assert.deepEqual(state.assembly.finalPathTrackScrollState, {
    viewportKey: "9:chr1:graph:250:15",
    scrollLeft: 260,
  });
  assert.deepEqual(state.assembly.hiddenPrimaryCtgIds, [7]);
  assert.deepEqual(state.assembly.hiddenPrimaryCtgIdsByChr, { chr1: [7] });
  assert.deepEqual(state.assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 7, offsetBp: 120 },
  ]);
  assert.deepEqual(state.assembly.subviewTrackDragOffsets, [
    { slot: "top", contigId: 41, offsetBp: 80 },
  ]);
});

test("loadAssemblyView canonicalizes persisted GRT overallLen and backfills origin ids", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [] }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      supportMirroredCtgs: [],
      finalPathByChr: {},
      finalPathViewMode: "graph",
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    getSupportDatasetOptions() {
      return [];
    },
    async getProjectAssemblyViewState() {
      return {
        finalPathViewMode: "table",
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 7,
                datasetName: "flye",
                ctgName: "flye_ctg7",
                overallLen: 900,
                start: 1,
                end: 900,
                source: {
                  dataset: "flye",
                  contig: "utig4-001122l",
                  start: 1,
                  end: 900,
                  orientation: "+",
                },
                serverBaseline: true,
              },
            ],
            updatedAt: "1",
          },
        },
      };
    },
    async listChrViewCtgs() {
      return {
        items: [{
          assemblyCtgId: 7,
          name: "Ctg7",
          originId: "utig4-001122l",
          datasetName: "flye",
          totalLength: 1200,
        }],
      };
    },
    async getGrtProjectView() {
      return {
        baselineFinalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [{
              segmentId: "seg-1",
              type: "ctg",
              assemblyCtgId: null,
              datasetName: "flye",
              ctgName: "flye_ctg7",
              originId: "utig4-001122l",
              overallLen: 1200,
              start: 1,
              end: 900,
              source: {
                dataset: "flye",
                contig: "utig4-001122l",
                start: 1,
                end: 900,
                orientation: "+",
              },
              serverBaseline: true,
            }],
          },
        },
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeFinalPathByChr,
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  assert.deepEqual(state.assembly.finalPathByChr, {
    Chr01: {
      mode: "segments",
      chrName: "Chr01",
      totalLength: 900,
      segments: [
        {
          segmentId: "seg-1",
          type: "ctg",
          assemblyCtgId: 7,
          datasetName: "flye",
          ctgName: "flye_ctg7",
          originId: "utig4-001122l",
          overallLen: 1200,
          start: 1,
          end: 900,
          source: {
            dataset: "flye",
            contig: "utig4-001122l",
            start: 1,
            end: 900,
            orientation: "+",
          },
          serverBaseline: true,
        },
      ],
      updatedAt: "1",
    },
  });
  assert.equal(state.assembly.finalPathViewMode, "table");
});

function createChromosomeLoadHarness(overrides = {}) {
  let state = {
    session: { workspacePath: "/tmp/ws", projectId: 9 },
    assembly: { selectedChrName: "Chr01", supportDatasetId: 2, error: "old error" },
  };
  const store = {
    getState: () => state,
    setState: (patch) => { state = { ...state, ...patch }; },
  };
  const deps = {
    buildClearedSubviewState: () => ({ summary: null }),
    getCurrentProject: () => ({ primaryDatasetId: 1, phasedAssemblyEnabled: true }),
    normalizeSupportDatasetId: (id) => id == null ? null : Number(id),
    listChrViewCtgs: async () => ({ items: [{ assemblyCtgId: 8 }] }),
    getMainViewHistoryStatus: async () => ({ canUndo: true }),
    listPhasedChrTracks: async () => ({ tracks: [] }),
    listReferenceTrackMembers: async () => ({ items: [] }),
    loadDatasetChrCtgs: async () => [],
    loadDeletedCtgsForChr: async () => [],
    loadSideDataForCtg: async () => ({ detail: { members: [] }, candidates: {} }),
    mapAssemblyError: ({ error }) => ({ userMessage: error.message }),
    rerender() {},
    ...overrides,
  };
  return { store, deps, select: (chr) => selectChromosome({}, store, chr, deps) };
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

test("chromosome reads overlap while ctg details wait only for primary ctgs", async () => {
  const reads = new Map();
  const start = (name) => {
    const pending = deferred();
    reads.set(name, pending);
    return pending.promise;
  };
  const harness = createChromosomeLoadHarness({
    listChrViewCtgs: () => start("primary"),
    getMainViewHistoryStatus: () => start("history"),
    listPhasedChrTracks: () => start("phased"),
    listReferenceTrackMembers: () => start("reference"),
    loadDatasetChrCtgs: () => start("support"),
    loadDeletedCtgsForChr: () => start("deleted"),
    loadSideDataForCtg: (_root, _project, id) => {
      assert.equal(id, 8);
      return start("details");
    },
  });
  const pending = harness.select("Chr02");
  await new Promise(setImmediate);
  assert.deepEqual([...reads.keys()].sort(), ["deleted", "history", "phased", "primary", "reference", "support"]);
  assert.equal(harness.store.getState().assembly.error, "");
  reads.get("primary").resolve({ items: [{ assemblyCtgId: 8 }] });
  await new Promise(setImmediate);
  assert.ok(reads.has("details"));
  reads.get("details").resolve({ detail: { members: [] }, candidates: {} });
  reads.get("history").resolve({ canUndo: true, undoOperation: { kind: "flip-ctg", targetCount: 1 } });
  reads.get("phased").resolve({ tracks: [{ phasedTrackId: 1, haplotypeKey: "A", items: [{ assemblyCtgId: 8 }] }] });
  reads.get("reference").resolve({ items: [] });
  reads.get("support").resolve([]);
  reads.get("deleted").resolve([]);
  await pending;
  assert.equal(harness.store.getState().assembly.loading, false);
  assert.equal(harness.store.getState().assembly.mainViewHistory.canUndo, true);
  assert.equal(harness.store.getState().assembly.phasedChrTracks[0].items[0].sourceCtg.assemblyCtgId, 8);
});

for (const staleFails of [false, true]) {
  test(`rapid A-B-A switching ignores stale ${staleFails ? "errors" : "results"}`, async () => {
    const first = deferred();
    let calls = 0;
    const harness = createChromosomeLoadHarness({
      listChrViewCtgs: async () => ++calls === 1 ? first.promise : { items: [{ assemblyCtgId: calls }] },
    });
    const oldLoad = harness.select("Chr01");
    await new Promise(setImmediate);
    await harness.select("Chr02");
    await harness.select("Chr01");
    if (staleFails) first.reject(new Error("stale failure"));
    else first.resolve({ items: [{ assemblyCtgId: 100 }] });
    await oldLoad;
    assert.equal(harness.store.getState().assembly.chrCtgs[0].assemblyCtgId, 3);
    assert.equal(harness.store.getState().assembly.error, "");
    assert.equal(harness.store.getState().assembly.loading, false);
  });
}

test("switching workspace discards pending chromosome data even when chr names match", async () => {
  const first = deferred();
  let detailCalls = 0;
  const harness = createChromosomeLoadHarness({
    listChrViewCtgs: () => first.promise,
    loadSideDataForCtg: async () => { detailCalls++; return {}; },
  });
  const oldLoad = harness.select("Chr01");
  harness.store.setState({ session: { workspacePath: "/tmp/new-workspace", projectId: 9 } });
  first.resolve({ items: [{ assemblyCtgId: 100 }] });
  await oldLoad;
  assert.deepEqual(harness.store.getState().assembly.chrCtgs, []);
  assert.equal(detailCalls, 0);
});

test("a current chromosome read failure ends loading and a retry recovers", async () => {
  const harness = createChromosomeLoadHarness({
    getMainViewHistoryStatus: async () => { throw new Error("history unavailable"); },
  });
  await harness.select("Chr02");
  assert.equal(harness.store.getState().assembly.loading, false);
  assert.equal(harness.store.getState().assembly.error, "history unavailable");
  harness.deps.getMainViewHistoryStatus = async () => ({ canUndo: false });
  await harness.select("Chr02");
  assert.equal(harness.store.getState().assembly.loading, false);
  assert.equal(harness.store.getState().assembly.error, "");
  assert.equal(harness.store.getState().assembly.chrCtgs[0].assemblyCtgId, 8);
});


function createInitialLoadHarness(overrides = {}) {
  const harness = createChromosomeLoadHarness({
    getProjectAssemblyViewState: async () => ({}),
    getGrtProjectView: async () => ({}),
    listProjectChromosomes: async () => ({ items: [{ chrName: "Chr01" }] }),
    getSupportDatasetOptions: () => [{ datasetId: 2 }],
    buildSubviewTrackPairHiddenCtgKey: () => "",
    buildSubviewTrackPairPoolsFromAssembly: () => ({}),
    filterPrimaryTrackSelectionCtgIds: (v) => v || [],
    filterSubviewTrackDragOffsetsBySummary: (v) => v || [],
    filterSubviewTrackPairHiddenCtgs: (v) => v || [],
    filterSubviewTrackPairSelectionCtgs: (v) => v || [],
    normalizeDeletedCtgRecordIds: (v) => v || [],
    normalizeSupportMirroredCtgs: (v) => v || [],
    normalizeTrackSelectionCtgIds: (v) => v || [],
    ...overrides,
  });
  harness.store.setState({ assembly: { ...harness.store.getState().assembly, subview: { summary: null } } });
  harness.load = () => loadAssemblyView({}, harness.store, {}, harness.deps);
  return harness;
}

test("initial assembly load overlaps project reads and independent chromosome reads", async () => {
  const view = deferred();
  const reference = deferred();
  const primary = deferred();
  const started = new Set();
  const harness = createInitialLoadHarness({
    getProjectAssemblyViewState: () => { started.add("view"); return view.promise; },
    getGrtProjectView: async () => { started.add("grt"); return {}; },
    listProjectChromosomes: async () => { started.add("chromosomes"); return { items: [{ chrName: "Chr01" }] }; },
    listChrViewCtgs: () => { started.add("primary"); return primary.promise; },
    listReferenceTrackMembers: () => { started.add("reference"); return reference.promise; },
    loadDatasetChrCtgs: async () => { started.add("support"); return []; },
    loadDeletedCtgsForChr: async () => { started.add("deleted"); return []; },
    loadSideDataForCtg: async () => { started.add("details"); return { detail: { members: [] }, candidates: {} }; },
  });
  const pending = harness.load();
  await new Promise(setImmediate);
  assert.deepEqual([...started].sort(), ["chromosomes", "grt", "view"]);
  view.resolve({});
  await new Promise(setImmediate);
  for (const name of ["primary", "reference", "support", "deleted"]) assert.ok(started.has(name), name);
  primary.resolve({ items: [{ assemblyCtgId: 8 }] });
  await new Promise(setImmediate);
  assert.ok(started.has("details"));
  reference.resolve({ items: [] });
  await pending;
  assert.equal(harness.store.getState().assembly.loading, false);
  assert.equal(harness.store.getState().assembly.error, "");
  assert.equal(harness.store.getState().assembly.chrCtgs[0].assemblyCtgId, 8);
});

for (const reject of [false, true]) {
  test(`initial assembly load ignores stale ${reject ? "failure" : "success"} after chr selection`, async () => {
    const first = deferred();
    const harness = createInitialLoadHarness({ getProjectAssemblyViewState: () => first.promise });
    const pending = harness.load();
    await new Promise(setImmediate);
    await harness.select("Chr02");
    if (reject) first.reject(new Error("old load"));
    else first.resolve({});
    await pending;
    assert.equal(harness.store.getState().assembly.selectedChrName, "Chr02");
    assert.equal(harness.store.getState().assembly.loading, false);
    assert.equal(harness.store.getState().assembly.error, "");
  });
}

test("loadAssemblyView keeps split source paths detached from sibling IDs during hydration", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/ws",
      projectId: 9,
    },
    initializer: {
      existingProjects: [{ projectId: 9, primaryDatasetId: 1, supportDatasetIds: [] }],
      datasets: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: null,
      selectedMemberSeqId: null,
      supportDatasetId: null,
      supportMirroredCtgs: [],
      finalPathByChr: {},
      finalPathViewMode: "graph",
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: {
        summary: null,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  };
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

  await loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false }, {
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
      return `${trackRole}:${contigId}`;
    },
    buildSubviewTrackPairPoolsFromAssembly() {
      return { top: [], bottom: [] };
    },
    filterPrimaryTrackSelectionCtgIds(values) {
      return values;
    },
    filterSubviewTrackDragOffsetsBySummary(values) {
      return values;
    },
    filterSubviewTrackPairHiddenCtgs(values) {
      return values;
    },
    filterSubviewTrackPairSelectionCtgs(values) {
      return values;
    },
    filterTrackDragOffsets(values) {
      return values;
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    getSupportDatasetOptions() {
      return [];
    },
    async getProjectAssemblyViewState() {
      return {
        finalPathViewMode: "table",
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 7,
                datasetName: "flye",
                ctgName: "flye_ctg7",
                overallLen: 900,
                start: 1,
                end: 900,
                source: {
                  dataset: "flye",
                  contig: "utig4-001122l",
                  start: 1,
                  end: 900,
                  orientation: "+",
                },
                serverBaseline: true,
              splitFromAssemblyCtgId: 6,
              splitFragmentCtgId: 73,
              },
            ],
            updatedAt: "1",
          },
        },
      };
    },
    async listChrViewCtgs() {
      return {
        items: [{
          assemblyCtgId: 7,
          name: "Ctg7",
          originId: "utig4-001122l",
          datasetName: "flye",
          totalLength: 1200,
        }],
      };
    },
    async getGrtProjectView() {
      return {
        baselineFinalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [{
              segmentId: "seg-1",
              type: "ctg",
              assemblyCtgId: null,
              datasetName: "flye",
              ctgName: "flye_ctg7",
              originId: "utig4-001122l",
              overallLen: 1200,
              start: 1,
              end: 900,
              source: {
                dataset: "flye",
                contig: "utig4-001122l",
                start: 1,
                end: 900,
                orientation: "+",
              },
              serverBaseline: true,
              splitFromAssemblyCtgId: 6,
              splitFragmentCtgId: 73,
            }],
          },
        },
      };
    },
    async listProjectChromosomes() {
      return {
        items: [{ chrName: "Chr01" }],
        referenceGenomeId: 3,
        unplacedCtgCount: 0,
        unplacedBp: 0,
      };
    },
    async loadDatasetChrCtgs() {
      return [];
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    async loadSideDataForCtg() {
      return {
        detail: { members: [] },
        candidates: { moveTargetCtgs: [], addSeqCandidates: [] },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    normalizeDeletedCtgRecordIds(values) {
      return values;
    },
    normalizeFinalPathByChr,
    normalizeSupportDatasetId(value) {
      return value == null ? null : Number(value);
    },
    normalizeSupportMirroredCtgs(values) {
      return values;
    },
    normalizeTrackSelectionCtgIds(values) {
      return values;
    },
    rerender() {},
  });

  const segment = state.assembly.finalPathByChr.Chr01.segments[0];
  assert.equal(segment.assemblyCtgId, null);
  assert.equal(segment.splitFromAssemblyCtgId, 6);
  assert.equal(segment.splitFragmentCtgId, 73);
  assert.deepEqual(normalizeFinalPathByChr(state.assembly.finalPathByChr), state.assembly.finalPathByChr);
});


test("cross-chr inspection copies do not auto-attach to existing Final Path source locators",()=>{
  const copy={assemblyCtgId:42,datasetName:"ds",originId:"tig",sourceFragment:{groupKey:"manual-fragment:chr-add:1:42",sourceStart:101,sourceEnd:1100}};
  const paths={B:{segments:[{type:"ctg",assemblyCtgId:null,source:{dataset:"ds",contig:"tig",start:1,end:2000},start:1,end:2000,serverBaseline:true}]}};
  const before=structuredClone(paths);
  assert.equal(backfillFinalPathOriginIds(paths,"B",[copy],[]),paths);
  assert.deepEqual(paths,before);
  const adopted={B:{segments:[{...paths.B.segments[0],assemblyCtgId:42}]}};
  assert.equal(backfillFinalPathOriginIds(adopted,"B",[copy],[]).B.segments[0].assemblyCtgId,42,"explicit adoption remains valid");
});


for (const mode of ["composition", "track-pair", "2-contig"]) for (const mainSplit of [false, true]) {
  test(`cold assembly load restores ${mode} colored evidence without reselecting Local View, Main split=${mainSplit}`, async () => {
    const { createIdentityRenderState } = await import("./identity-render-fixture.mjs");
    const { renderAssemblyPage } = await import("./tabs-semantics-harness.mjs");
    const { activateSubviewCompositionHistory, buildSubviewCompositionHistoryKey } = await import("../subview-history-state.js");
    const { createSubviewPairwiseController } = await import("../subview-pairwise-controller.js");
    const fixture = createIdentityRenderState(mode);
    const { prepareSourceOwnedSubviewHistory } = await import("../subview-fragment-history.js");
    const { projectRenderedSubviewToComposition } = await import("../subview-composition-controller.js");
    const originalHits = fixture.assembly.subview.pairwiseEvidence.hits;
    const hits = mainSplit ? [
      { ...originalHits[0], subjectAssemblyCtgId: 201 },
      { ...originalHits[6], subjectAssemblyCtgId: 202, subjectStart: 3300, subjectEnd: 4600 },
    ] : originalHits;
    const parent = fixture.assembly.chrCtgs[0];
    const mainCtgs = mainSplit ? [[201, 1, 8000], [202, 8001, 16000]].map(([id, start, end]) => ({
      ...parent, assemblyCtgId: id, totalLength: end - start + 1, lengthBp: end - start + 1,
      sourceFragment: { sourceSeqId: 700, groupKey: "manual-fragment:2", sourceStart: start,
        sourceEnd: end, sourceLength: 16000 },
    })) : fixture.assembly.chrCtgs;
    // This is the same pre-mutation capture used by the Main split action.
    const saved = mainSplit ? prepareSourceOwnedSubviewHistory(fixture, {}, {
      preserveLegacy: true,
      projectHistorical: (historical) => projectRenderedSubviewToComposition(historical, renderAssemblyPage(historical)),
    }) : activateSubviewCompositionHistory(fixture.assembly, { stateOrLocale: fixture }).assembly;
    const events = [], finalHtml = [];
    let controller;
    const harness = createInitialLoadHarness({
      getCurrentProject: () => ({ primaryDatasetId: 11 }),
      getSupportDatasetOptions: () => [{ datasetId: 22 }],
      getProjectAssemblyViewState: async () => ({
        supportDatasetId: 22, subviewHistoryByKey: saved.subviewHistoryByKey,
      }),
      listChrViewCtgs: async () => ({ items: mainCtgs }),
      loadDatasetChrCtgs: async () => fixture.assembly.supportChrCtgs,
      activateSubviewCompositionHistory,
      buildSubviewCompositionHistoryKey,
      refreshSubviewPairwiseEvidence: (...args) => controller.refreshSubviewPairwiseEvidence(...args),
      rerender(_host, store) {
        if (store.getState().assembly.loading) { events.push("loading-render"); return; }
        events.push("ready-render");
        finalHtml.push(renderAssemblyPage(store.getState()));
      },
    });
    // Simulate a fresh process: only persisted history exists; no runtime hits,
    // candidate catalog or previous Local View selection survives.
    harness.store.setState({ ...fixture,
      session: { workspacePath: "D:/fixture", projectId: 7 },
      assembly: { ...fixture.assembly, chromosomes: [], chrCtgs: [], supportChrCtgs: [],
        subview: { summary: null }, subviewHistoryByKey: {},
        subviewCompositionCandidates: [], subviewCompositionCandidatesLoaded: false },
    });
    const fetchEvidence = async () => {
      events.push("evidence-fetch");
      assert.ok(harness.store.getState().assembly.subview.summary, "history must be restored before fetching hits");
      await Promise.resolve();
      return { hits, evidenceSource: "fixture", coverage: [{ status: "ready" }] };
    };
    controller = createSubviewPairwiseController({
      session: { subviewPairwiseEvidenceRequestSeq: 0 },
      getTrackPairwiseEvidence: fetchEvidence, getJunctionInspection: fetchEvidence,
      rerenderSubviewPanel() { assert.fail("cold hydration must not flash a loading card"); },
      scheduleDeferredSubviewPanelRerender() { assert.fail("the assembly loader owns the final render"); },
    });
    await harness.load();
    assert.equal(harness.store.getState().assembly.error, "");
    assert.equal(harness.store.getState().assembly.subview.pairwiseEvidence.status, "loaded");
    assert.deepEqual(events, ["loading-render", "evidence-fetch", "ready-render"]);
    assert.equal(finalHtml.length, 1);
    assert.match(finalHtml[0], /data-subview-hit-key="[^"]*evidence-1[^"]*"/);
    assert.match(finalHtml[0], /data-band-identity-pct="93\.27"/);
    if (mainSplit) {
      const members = harness.store.getState().assembly.subview.summary.members.filter((member) => member.source.role === "primary");
      assert.deepEqual(members.map((member) => member.assemblyCtgId), [201, 202]);
      assert.equal(new Set(members.map((member) => member.entityKey)).size, 2);
      assert.match(finalHtml[0], /data-subview-contig-id="201"/);
      assert.match(finalHtml[0], /data-subview-contig-id="202"/);
      assert.ok(members.every((member) => member.localFragment.parts.length === 1));
    }
  });
}

function waitingNavigationFixture() {
  let release;
  const barrier = new Promise(resolve => { release = resolve; });
  let state = { locale: "en", session: { workspacePath: "D:/project", projectId: 7 },
    assembly: { selectedChrName: "Chr01", chrCtgs: [], supportDatasetId: null,
      finalPathByChr: normalizeFinalPathByChr({ Chr01B: { chrName: "Chr01B", mode: "segments", segments: [] } }) } };
  const store = { getState: () => state, setState: next => { state = { ...state, ...next }; } };
  const reads = []; let renders = 0;
  const deps = {
    waitForProjectViewMutations: () => barrier,
    buildClearedSubviewState: () => ({ summary: null }),
    getCurrentProject: () => ({ primaryDatasetId: 1, supportDatasetIds: [], phasedAssemblyEnabled: false }),
    listChrViewCtgs: async args => { reads.push(args.chrName); return { items: [] }; },
    loadDatasetChrCtgs: async () => [], loadDeletedCtgsForChr: async () => [],
    loadSideDataForCtg: async () => ({ detail: null, candidates: { moveTargetCtgs: [], addSeqCandidates: [] } }),
    mapAssemblyError: ({ error }) => ({ userMessage: error.message }),
    normalizeSupportDatasetId: value => value == null ? null : Number(value),
    rerender: () => { renders++; },
  };
  return { store, deps, reads, release, get renders() { return renders; } };
}

test("chromosome navigation waits for pending project data mutations and uses their latest path cleanup", async () => {
  const f = waitingNavigationFixture();
  const selecting = selectChromosome({}, f.store, "Chr02", f.deps);
  assert.equal(f.store.getState().assembly.selectedChrName, "Chr01");
  assert.deepEqual(f.reads, []);
  assert.equal(f.renders, 0);
  const corrected = normalizeFinalPathByChr({ Chr01A: { chrName: "Chr01A", mode: "segments", segments: [] } });
  f.store.setState({ assembly: { ...f.store.getState().assembly, finalPathByChr: corrected } });
  f.release(); await selecting;
  assert.equal(f.store.getState().assembly.selectedChrName, "Chr02");
  assert.deepEqual(f.reads, ["Chr02"]);
  assert.equal(f.store.getState().assembly.finalPathByChr.Chr01B, undefined);
  assert.ok(f.store.getState().assembly.finalPathByChr.Chr01A);
});

test("only the latest chromosome selection loads after the shared mutation barrier releases", async () => {
  const f = waitingNavigationFixture();
  const first = selectChromosome({}, f.store, "Chr02", f.deps);
  const second = selectChromosome({}, f.store, "Chr03", f.deps);
  f.release(); await Promise.all([first, second]);
  assert.deepEqual(f.reads, ["Chr03"]);
  assert.equal(f.store.getState().assembly.selectedChrName, "Chr03");
});

function quietSelectionFixture() {
  let state = { activeRoute: "assembly", session: { workspacePath: "/ws", projectId: 1 },
    assembly: { selectedChrName: "Chr01", selectedCtgId: 7, loading: false,
      ctgDetail: { assemblyCtgId: 7 }, editCandidates: { old: true }, trackSelectedCtgIds: [7], selectedDeletedCtgRecordIds: [3] } };
  const store = { getState: () => state, setState: patch => { state = { ...state, ...patch }; } };
  const calls = [], pending = [];
  const deps = { loadSideDataForCtg: (_ws, _pid, id) => new Promise((resolve, reject) => pending.push({ id, resolve, reject })),
    mapAssemblyError: ({ error }) => { calls.push("mapError"); return { userMessage: error.message }; },
    normalizeTrackFocusMode: value => value || "center", setPendingTrackAutoFocusMode: mode => calls.push(["focus", mode]),
    patchSelection: (_host, _store, options) => calls.push(["paint", options.focus]),
    rerender: () => { throw Error("quiet selection must not reconstruct the page"); } };
  return { store, calls, pending, select: id => selectCtg({}, store, id, { quiet: true, focusMode: "start" }, deps) };
}

test("member selection paints immediately without global loading and clears old edit data", async () => {
  const f = quietSelectionFixture(); const selecting = f.select(10);
  assert.equal(f.store.getState().assembly.loading, false);
  assert.equal(f.store.getState().assembly.selectedCtgId, 10);
  assert.equal(f.store.getState().assembly.ctgDetail, null);
  assert.deepEqual(f.store.getState().assembly.trackSelectedCtgIds, []);
  assert.deepEqual(f.calls, [["focus", "start"], ["paint", true]]);
  f.pending[0].resolve({ detail: { assemblyCtgId: 10, members: [] }, candidates: { fresh: true } });
  await selecting;
  assert.equal(f.store.getState().assembly.ctgDetail.assemblyCtgId, 10);
  assert.deepEqual(f.calls.at(-1), ["paint", false]);
});

test("rapid A to B to A member selection rejects obsolete successful and failed detail responses", async () => {
  const f = quietSelectionFixture(); const a = f.select(10), b = f.select(20), a2 = f.select(10);
  f.pending[2].resolve({ detail: { assemblyCtgId: 10, version: "latest", members: [] }, candidates: {} }); await a2;
  const calls = f.calls.length;
  f.pending[0].resolve({ detail: { version: "obsolete", members: [] }, candidates: {} }); await a;
  f.pending[1].reject(Error("late failure")); await b;
  assert.equal(f.store.getState().assembly.ctgDetail.version, "latest");
  assert.equal(f.calls.length, calls);
  assert.equal(f.store.getState().assembly.error, "");
});

test("member detail responses cannot publish into another project, chromosome, route or view generation", async () => {
  for (const change of [
    s => ({ session: { ...s.session, projectId: 2 } }),
    s => ({ assembly: { ...s.assembly, selectedChrName: "Chr02" } }),
    () => ({ activeRoute: "projects" }),
    () => null,
  ]) {
    const f = quietSelectionFixture(), selecting = f.select(10), patch = change(f.store.getState());
    if (patch) f.store.setState(patch); else beginAssemblyViewRequest(f.store);
    const state = f.store.getState(), calls = f.calls.length;
    f.pending[0].resolve({ detail: { members: [] }, candidates: {} }); await selecting;
    assert.equal(f.store.getState(), state); assert.equal(f.calls.length, calls);
  }
});

test("chromosome selection leaves the chooser open during and after loading, but respects an explicit pending close", async () => {
  for (const closeDuringLoad of [false, true]) {
    const pending = deferred(), f = createChromosomeLoadHarness({ listChrViewCtgs: () => pending.promise });
    f.store.setState({ assembly: { ...f.store.getState().assembly, chrPickerOpen: true } });
    const loading = f.select("Chr02"); assert.equal(f.store.getState().assembly.chrPickerOpen, true);
    if (closeDuringLoad) f.store.setState({ assembly: { ...f.store.getState().assembly, chrPickerOpen: false } });
    pending.resolve({ items: [{ assemblyCtgId: 8 }] }); await loading;
    assert.equal(f.store.getState().assembly.chrPickerOpen, !closeDuringLoad);
    assert.equal(f.store.getState().assembly.selectedChrName, "Chr02");
  }
});
