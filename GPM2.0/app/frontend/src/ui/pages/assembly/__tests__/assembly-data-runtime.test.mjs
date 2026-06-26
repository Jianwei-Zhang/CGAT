import test from "node:test";
import assert from "node:assert/strict";

import { handleNewSequenceRowAction, loadAssemblyView, selectChromosome, selectCtg } from "../assembly-data-runtime.js";
import { normalizeFinalPathByChr } from "../final-path-state.js";
import { filterTrackDragOffsets as filterAssemblyTrackDragOffsets } from "../selection-state.js";

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

test("selectChromosome clears stale member and track data while loading a new chromosome", async () => {
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
  const loadPromise = selectChromosome(host, store, "Chr10", {
    buildClearedSubviewState() {
      return { summary: null, trackPairHiddenCtgs: [], trackPairSelectedCtgs: [] };
    },
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
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

  resolveChrCtgs({ items: [{ assemblyCtgId: 8, name: "ptg000008l@Chr10" }] });
  await loadPromise;
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 8, name: "ptg000008l@Chr10" }]);
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

test("loadAssemblyView restores persisted drag offsets for duplicate phased items", async () => {
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
    filterTrackDragOffsets: filterAssemblyTrackDragOffsets,
    getCurrentProject(currentState) {
      return currentState.initializer.existingProjects[0];
    },
    async getProjectAssemblyViewState() {
      return {
        trackDragOffsets: [
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

test("loadAssemblyView hydrates finalPathByChr from project assembly view state and backfills missing origin ids", async () => {
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
                datasetName: "",
                ctgName: "flye_ctg7",
                overallLen: 900,
                start: 1,
                end: 900,
              },
            ],
            updatedAt: "1",
          },
        },
      };
    },
    async listChrViewCtgs() {
      return {
        items: [{ assemblyCtgId: 7, name: "Ctg7", originId: "utig4-001122l" }],
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
          datasetName: "",
          ctgName: "flye_ctg7",
          originId: "utig4-001122l",
          overallLen: 900,
          start: 1,
          end: 900,
        },
      ],
      updatedAt: "1",
    },
  });
  assert.equal(state.assembly.finalPathViewMode, "table");
});
