import test from "node:test";
import assert from "node:assert/strict";

import { createBatchDeleteRefreshController } from "../batch-delete-refresh-controller.js";

test("local batch delete refresh adopts backend-owned Final Path and DEGAP state", async () => {
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
      trackDragOffsets: [],
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
