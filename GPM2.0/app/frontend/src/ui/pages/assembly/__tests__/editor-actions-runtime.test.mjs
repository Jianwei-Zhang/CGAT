import test from "node:test";
import assert from "node:assert/strict";

import {
  applyEditorAction,
  deleteSelectedSubviewTrackPairCtgs,
  deleteSelectedTrackCtgs,
  runBatchDeleteTrackCtgs,
  runBatchRestoreDeletedCtgs,
} from "../editor-actions-runtime.js";

test("deleteSelectedSubviewTrackPairCtgs hides normalized subview selections and clears track-pair selection state", async () => {
  const host = {};
  let state = {
    assembly: {
      subview: {
        summary: { mode: "track-pair" },
        trackPairHiddenCtgs: [{ trackRole: "top", contigId: 3 }],
        trackPairSelectedCtgs: [{ trackRole: "bottom", contigId: 9 }],
      },
      actionStatus: "",
      actionError: "old",
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
  const confirms = [];

  await deleteSelectedSubviewTrackPairCtgs(
    host,
    store,
    [{ trackRole: "top", contigId: 7 }],
    {
      rerender(_host, currentStore) {
        rerenders.push(currentStore.getState().assembly.subview.trackPairHiddenCtgs);
      },
    },
    {
      confirm(message) {
        confirms.push(message);
        return true;
      },
      getSubviewState(assembly) {
        return assembly.subview;
      },
      normalizeSubviewTrackPairHiddenCtgs(entries) {
        return entries;
      },
      normalizeSubviewTrackPairSelectionCtgs(entries) {
        return entries;
      },
      resolveFilteredSubviewTrackPairSelectionsFromAssembly() {
        return [{ trackRole: "top", contigId: 7 }];
      },
    },
  );

  assert.deepEqual(confirms, ["确认在 Subview 中临时删除已框选的 1 个 contig 吗？"]);
  assert.deepEqual(state.assembly.subview.trackPairHiddenCtgs, [
    { trackRole: "top", contigId: 3 },
    { trackRole: "top", contigId: 7 },
  ]);
  assert.deepEqual(state.assembly.subview.trackPairSelectedCtgs, []);
  assert.equal(state.assembly.actionStatus, "Subview 轨道模式已临时删除 1 个 contig。");
  assert.equal(state.assembly.actionError, "");
  assert.equal(rerenders.length, 1);
});

test("deleteSelectedTrackCtgs waits for async confirmation before deleting", async () => {
  const host = {};
  let state = {
    assembly: {
      chrCtgs: [{ assemblyCtgId: 2 }],
      hiddenPrimaryCtgIds: [],
      trackSelectedCtgIds: [2],
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
  const calls = [];
  let resolveConfirm = null;
  const pending = deleteSelectedTrackCtgs(
    host,
    store,
    [2],
    {
      async runBatchDeleteTrackCtgs(_host, _store, selectedIds) {
        calls.push(selectedIds);
      },
    },
    {
      confirm() {
        return new Promise((resolve) => {
          resolveConfirm = resolve;
        });
      },
    },
  );

  await Promise.resolve();
  assert.deepEqual(calls, []);

  resolveConfirm(false);
  await pending;
  assert.deepEqual(calls, []);
});

test("applyEditorAction local refresh avoids the loading curtain and uses the local view loader", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      loading: false,
      actionStatus: "",
      actionError: "",
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
  const fullRerenders = [];
  const mainTabRerenders = [];
  const localLoaderOptions = [];

  await applyEditorAction(
    host,
    store,
    {
      action: "flip-ctg",
      args: { assemblyCtgId: 2 },
      keepCurrentCtg: true,
      localRefresh: true,
    },
    {
      appendAuditLog() {},
      buildActionAuditDetail() {
        return {};
      },
      async loadAssemblyView() {
        throw new Error("full loader should not be used");
      },
      async loadAssemblyViewForLocalAssemblyRefresh(_host, currentStore, options) {
        localLoaderOptions.push(options);
        currentStore.setState({
          assembly: {
            ...currentStore.getState().assembly,
            loading: false,
          },
        });
      },
      mapAssemblyError({ error }) {
        return { userMessage: String(error?.message || error || "error") };
      },
      rerender(_host, currentStore) {
        fullRerenders.push(currentStore.getState().assembly.loading);
      },
      rerenderAssemblyMainTab(_host, currentStore) {
        mainTabRerenders.push(currentStore.getState().assembly.loading);
      },
      async runAction() {
        return { changed: true };
      },
    },
  );

  assert.deepEqual(fullRerenders, []);
  assert.deepEqual(mainTabRerenders, []);
  assert.deepEqual(localLoaderOptions, [
    { keepCurrentChr: true, keepCurrentCtg: true, renderLoading: false },
  ]);
  assert.equal(state.assembly.loading, false);
  assert.equal(state.assembly.actionStatus, "flip-ctg 完成（changed=true）。");
});

test("applyEditorAction phased-only refresh avoids reloading primary track data", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      loading: false,
      actionStatus: "",
      actionError: "",
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
  const phasedRefreshes = [];

  await applyEditorAction(
    host,
    store,
    {
      action: "flip-ctg",
      args: { assemblyCtgId: 92, phasedTrackItemId: 9001 },
      keepCurrentCtg: true,
      localRefresh: true,
      phasedOnlyRefresh: true,
    },
    {
      appendAuditLog() {},
      buildActionAuditDetail() {
        return {};
      },
      async loadAssemblyView() {
        throw new Error("full loader should not be used");
      },
      async loadAssemblyViewForLocalAssemblyRefresh() {
        throw new Error("local primary-track loader should not be used");
      },
      mapAssemblyError({ error }) {
        return { userMessage: String(error?.message || error || "error") };
      },
      rerender() {
        throw new Error("full rerender should not be used");
      },
      rerenderAssemblyMainTab() {},
      async runAction() {
        return { changed: true };
      },
      async refreshPhasedTracksForCurrentChr(_host, currentStore) {
        phasedRefreshes.push(currentStore.getState().assembly.loading);
        currentStore.setState({
          assembly: {
            ...currentStore.getState().assembly,
            loading: false,
          },
        });
      },
    },
  );

  assert.deepEqual(phasedRefreshes, [false]);
  assert.equal(state.assembly.loading, false);
  assert.equal(state.assembly.actionStatus, "flip-ctg 完成（changed=true）。");
});

test("runBatchDeleteTrackCtgs local refresh avoids loading rerender", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      chrCtgs: [{ assemblyCtgId: 2 }],
      hiddenPrimaryCtgIds: [],
      trackSelectedCtgIds: [2],
      loading: false,
      actionStatus: "",
      actionError: "",
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
  const rerenderLoadingStates = [];
  let reloadOptions = null;

  const result = await runBatchDeleteTrackCtgs(host, store, [2], {
    appendAuditLog() {},
    buildActionAuditDetail() {
      return {};
    },
    async loadAssemblyView(_host, currentStore, options) {
      reloadOptions = options;
      currentStore.setState({
        assembly: {
          ...currentStore.getState().assembly,
          loading: false,
          chrCtgs: [],
        },
      });
    },
    localRefresh: true,
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error || "error") };
    },
    rerender(_host, currentStore) {
      rerenderLoadingStates.push(currentStore.getState().assembly.loading);
    },
    async runAction() {
      return { changed: true };
    },
  });

  assert.deepEqual(result, { deletedCount: 1, failedCount: 0 });
  assert.deepEqual(rerenderLoadingStates, [false]);
  assert.equal(reloadOptions.renderLoading, false);
});

test("runBatchDeleteTrackCtgs local refresh uses lightweight delete refresh when available", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      chrCtgs: [{ assemblyCtgId: 2 }, { assemblyCtgId: 5 }],
      hiddenPrimaryCtgIds: [],
      trackSelectedCtgIds: [2],
      loading: false,
      actionStatus: "",
      actionError: "",
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
  const refreshCalls = [];
  let loadAssemblyViewCalled = false;
  let rerenderCount = 0;

  const result = await runBatchDeleteTrackCtgs(host, store, [2], {
    appendAuditLog() {},
    buildActionAuditDetail() {
      return {};
    },
    async loadAssemblyView() {
      loadAssemblyViewCalled = true;
    },
    localRefresh: true,
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error || "error") };
    },
    async refreshAfterBatchDelete(_host, currentStore, payload) {
      refreshCalls.push(payload);
      const currentState = currentStore.getState();
      const deletedSet = new Set(payload.deletedAssemblyCtgIds);
      currentStore.setState({
        assembly: {
          ...currentState.assembly,
          chrCtgs: currentState.assembly.chrCtgs.filter(
            (ctg) => !deletedSet.has(Number(ctg.assemblyCtgId)),
          ),
        },
      });
    },
    rerender() {
      rerenderCount += 1;
    },
    async runAction() {
      return { changed: true };
    },
  });

  assert.deepEqual(result, { deletedCount: 1, failedCount: 0 });
  assert.equal(loadAssemblyViewCalled, false);
  assert.equal(rerenderCount, 0);
  assert.deepEqual(refreshCalls.map((call) => call.deletedAssemblyCtgIds), [[2]]);
  assert.deepEqual(state.assembly.chrCtgs, [{ assemblyCtgId: 5 }]);
  assert.deepEqual(state.assembly.trackSelectedCtgIds, []);
});

test("runBatchDeleteTrackCtgs reports per-contig progress while deleting", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha" },
        { assemblyCtgId: 5, name: "ctg-beta" },
      ],
      hiddenPrimaryCtgIds: [],
      trackSelectedCtgIds: [2, 5],
      loading: false,
      actionStatus: "",
      actionError: "",
      batchDeleteProgress: null,
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
  const progressSnapshots = [];

  const result = await runBatchDeleteTrackCtgs(host, store, [2, 5], {
    appendAuditLog() {},
    buildActionAuditDetail() {
      return {};
    },
    async loadAssemblyView() {},
    localRefresh: true,
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error || "error") };
    },
    async refreshAfterBatchDelete() {},
    rerender() {},
    rerenderBatchDeleteProgress(_host, currentStore) {
      const progress = currentStore.getState().assembly.batchDeleteProgress;
      progressSnapshots.push(progress ? JSON.parse(JSON.stringify(progress)) : null);
    },
    async runAction({ args }) {
      if (Number(args?.assemblyCtgId) === 5) {
        throw new Error("delete failed");
      }
      return { changed: true };
    },
  });

  assert.deepEqual(result, { deletedCount: 1, failedCount: 1 });
  assert.deepEqual(
    progressSnapshots.map((progress) => progress && progress.items.map((item) => `${item.assemblyCtgId}:${item.status}`)),
    [
      ["2:running", "5:pending"],
      ["2:success", "5:running"],
      ["2:success", "5:error"],
      null,
    ],
  );
  assert.equal(progressSnapshots[0].items[0].label, "ctg-alpha");
  assert.equal(progressSnapshots[2].items[1].error, "delete failed");
});

test("runBatchDeleteTrackCtgs clears progress when lightweight refresh fails", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      chrCtgs: [{ assemblyCtgId: 2, name: "ctg-alpha" }],
      hiddenPrimaryCtgIds: [],
      trackSelectedCtgIds: [2],
      loading: false,
      actionStatus: "",
      actionError: "",
      batchDeleteProgress: null,
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
  const progressSnapshots = [];

  await assert.rejects(
    runBatchDeleteTrackCtgs(host, store, [2], {
      appendAuditLog() {},
      buildActionAuditDetail() {
        return {};
      },
      async loadAssemblyView() {},
      localRefresh: true,
      mapAssemblyError({ error }) {
        return { userMessage: String(error?.message || error || "error") };
      },
      async refreshAfterBatchDelete() {
        throw new Error("refresh failed");
      },
      rerender() {},
      rerenderBatchDeleteProgress(_host, currentStore) {
        const progress = currentStore.getState().assembly.batchDeleteProgress;
        progressSnapshots.push(progress ? JSON.parse(JSON.stringify(progress)) : null);
      },
      async runAction() {
        return { changed: true };
      },
    }),
    /refresh failed/,
  );

  assert.equal(progressSnapshots.at(-1), null);
});

test("runBatchRestoreDeletedCtgs rebases dragged offsets after restoring another ctg", async () => {
  const host = {};
  let state = {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
      ],
      selectedDeletedCtgRecordIds: [11],
      trackDragOffsets: [
        { trackRole: "primary", assemblyCtgId: 2, offsetBp: 125 },
      ],
      loading: false,
      actionStatus: "",
      actionError: "",
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
  let rebasePreviousAssembly = null;

  const result = await runBatchRestoreDeletedCtgs(host, store, [11], {
    appendAuditLog() {},
    buildActionAuditDetail() {
      return {};
    },
    async loadAssemblyView(_host, currentStore) {
      currentStore.setState({
        assembly: {
          ...currentStore.getState().assembly,
          loading: false,
          chrCtgs: [
            { assemblyCtgId: 1, name: "ctg1", anchorStart: 100, totalLength: 100 },
            { assemblyCtgId: 2, name: "ctg2", anchorStart: 200, totalLength: 50 },
          ],
        },
      });
    },
    localRefresh: true,
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error || "error") };
    },
    async rebaseTrackDragOffsetsAfterRestore(_host, currentStore, previousAssembly) {
      rebasePreviousAssembly = previousAssembly;
      currentStore.setState({
        assembly: {
          ...currentStore.getState().assembly,
          trackDragOffsets: [
            { trackRole: "primary", assemblyCtgId: 2, offsetBp: 25 },
          ],
        },
      });
    },
    rerender() {},
    async runAction() {
      return { changed: true };
    },
  });

  assert.deepEqual(result, { restoredCount: 1, failedCount: 0 });
  assert.deepEqual(
    rebasePreviousAssembly.chrCtgs.map((ctg) => ctg.assemblyCtgId),
    [2],
  );
  assert.deepEqual(state.assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 2, offsetBp: 25 },
  ]);
  assert.deepEqual(state.assembly.selectedDeletedCtgRecordIds, []);
});
