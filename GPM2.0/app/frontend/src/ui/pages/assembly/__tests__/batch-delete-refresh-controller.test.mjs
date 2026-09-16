import test from "node:test";
import assert from "node:assert/strict";

import { createBatchDeleteRefreshController } from "../batch-delete-refresh-controller.js";
import { buildSingleTrackModel } from "../track-layout.js";

for (const deletedIds of [[2], [2, 5]]) {
  test(`mounted main track reflows immediately after deleting ${deletedIds.length} contig(s)`, async () => {
    let state = {
      session: { workspacePath: "/tmp/workspace", projectId: 7 },
      assembly: {
        selectedChrName: "Chr01",
        chrCtgs: [
          { assemblyCtgId: 2, totalLength: 1000000 },
          { assemblyCtgId: 5, totalLength: 2000000 },
          { assemblyCtgId: 8, totalLength: 3000000 },
        ],
        subview: {},
      },
    };
    const store = {
      getState: () => state,
      setState: (next) => { state = next; },
    };
    const layout = () => buildSingleTrackModel({
      ctgs: state.assembly.chrCtgs,
      prefs: { tickBp: 1000000 },
    });
    let displayedTrack = layout();
    const previousTailX = displayedTrack.ctgs.find((ctg) => ctg.assemblyCtgId === 8).x;
    let subviewRefreshes = 0;
    const routeHost = { closest: () => routeHost };
    const { refreshAfterBatchDelete } = createBatchDeleteRefreshController({
      getCurrentProject: () => ({ primaryDatasetId: 11 }),
      loadDeletedCtgsForChr: async () => [],
      loadProjectAssemblyViewState: async () => ({
        finalPathByChr: {}, degapProjectState: {}, trackDragOffsets: [],
      }),
      buildClearedSubviewState: () => ({}),
      createRenderedAssemblyMainTabContent: () => ({}),
      replaceRenderedAssemblySection: () => null,
      patchAssemblyStatusToast() {},
      patchDeletedPrimaryTrackCtgsDom() {
        displayedTrack.ctgs = displayedTrack.ctgs.filter(
          (ctg) => !deletedIds.includes(ctg.assemblyCtgId),
        );
      },
      rerenderAssemblyMainTab() { displayedTrack = layout(); },
      rerenderSubviewPanel() { subviewRefreshes += 1; },
    });

    await refreshAfterBatchDelete(routeHost, store, { deletedAssemblyCtgIds: deletedIds });

    assert.deepEqual(displayedTrack, layout(), "visible geometry must match the post-delete layout");
    assert.ok(displayedTrack.ctgs.find((ctg) => ctg.assemblyCtgId === 8).x < previousTailX);
    assert.equal(subviewRefreshes, 1);
  });
}

test("local batch delete refresh adopts backend-owned Final Path and DEGAP state", async () => {
  const backendTrackDragOffsets = [
    { trackRole: "primary", assemblyCtgId: 90, offsetBp: 120 },
    { trackRole: "phased", assemblyCtgId: 91, phasedTrackId: 9, phasedTrackItemId: 99, offsetBp: -40 },
  ];
  const backendFinalPathByChr = {
    Chr01: {
      chrName: "Chr01",
      segments: [{ segmentId: "deleted", unavailable: true }],
    },
  };
  const backendDegapProjectState = {
    jobs: [{ jobId: "gap-1", endpoint: { unavailable: true } }],
  };
  let state = {
    session: { workspacePath: "/tmp/workspace", projectId: 7 },
    assembly: {
      selectedChrName: "Chr01",
      supportDatasetId: 22,
      chromosomes: [{ chrName: "Chr01", ctgCount: 2, placedBp: 300 }],
      chrCtgs: [
        { assemblyCtgId: 2, totalLength: 100 },
        { assemblyCtgId: 5, totalLength: 200 },
      ],
      finalPathByChr: { Chr01: { segments: [{ assemblyCtgId: 2 }] } },
      degapProjectState: { jobs: [{ endpoint: { assemblyCtgId: 2 } }] },
      supportMirroredCtgs: [{ datasetId: 22, assemblyCtgId: 30 }],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 90, offsetBp: 100 }],
      subviewTrackDragOffsets: [],
      trackSelectedCtgIds: [2],
      selectedDeletedCtgRecordIds: [],
      selectedCtgId: null,
      subview: {},
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = { ...state, ...nextState };
    },
  };
  let rerenderCount = 0;
  const { refreshAfterBatchDelete } = createBatchDeleteRefreshController({
    bindAssemblyPage() {},
    buildClearedSubviewState(assembly) {
      return assembly.subview;
    },
    createRenderedAssemblyMainTabContent() {
      return null;
    },
    getCurrentProject() {
      return { primaryDatasetId: 11 };
    },
    async loadDeletedCtgsForChr() {
      return [{ deletedCtgRecordId: 91 }];
    },
    async loadProjectAssemblyViewState(payload) {
      assert.deepEqual(payload, { workspaceRoot: "/tmp/workspace", projectId: 7 });
      return {
        finalPathByChr: backendFinalPathByChr,
        degapProjectState: backendDegapProjectState,
        trackDragOffsets: backendTrackDragOffsets,
      };
    },
    patchAssemblyStatusToast() {},
    patchDeletedPrimaryTrackCtgsDom() {},
    replaceRenderedAssemblySection() {
      return false;
    },
    rerenderAssemblyMainTab() {
      rerenderCount += 1;
    },
    rerenderSubviewPanel() {},
  });

  await refreshAfterBatchDelete(
    { closest() { return null; } },
    store,
    { deletedAssemblyCtgIds: [2] },
  );

  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 5, totalLength: 200 }]);
  assert.deepEqual(state.assembly.finalPathByChr, backendFinalPathByChr);
  assert.deepEqual(state.assembly.degapProjectState, backendDegapProjectState);
  assert.deepEqual(state.assembly.trackDragOffsets, backendTrackDragOffsets);
  assert.deepEqual(state.assembly.supportMirroredCtgs, [{ datasetId: 22, assemblyCtgId: 30 }]);
  assert.equal(rerenderCount, 1);
});

test("local batch delete refresh ignores a response after project identity changes", async () => {
  let resolvePersistedViewState;
  const persistedViewState = new Promise((resolve) => {
    resolvePersistedViewState = resolve;
  });
  let state = {
    session: { workspacePath: "/tmp/workspace", projectId: 7 },
    assembly: {
      selectedChrName: "Chr01",
      chrCtgs: [{ assemblyCtgId: 2, totalLength: 100 }],
    },
  };
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = { ...state, ...nextState };
    },
  };
  let rerenderCount = 0;
  const { refreshAfterBatchDelete } = createBatchDeleteRefreshController({
    getCurrentProject() {
      return { primaryDatasetId: 11 };
    },
    async loadDeletedCtgsForChr() {
      return [];
    },
    loadProjectAssemblyViewState() {
      return persistedViewState;
    },
    rerenderAssemblyMainTab() {
      rerenderCount += 1;
    },
  });

  const refresh = refreshAfterBatchDelete(
    { closest() { return null; } },
    store,
    { deletedAssemblyCtgIds: [2] },
  );
  state = {
    session: { workspacePath: "/tmp/workspace", projectId: 8 },
    assembly: {
      selectedChrName: "Chr02",
      chrCtgs: [{ assemblyCtgId: 80, totalLength: 500 }],
    },
  };
  resolvePersistedViewState({ finalPathByChr: {}, degapProjectState: {} });
  await refresh;

  assert.equal(state.session.projectId, 8);
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 80, totalLength: 500 }]);
  assert.equal(rerenderCount, 0);
});
