import test from "node:test";
import assert from "node:assert/strict";

import { runMainViewLayoutAction } from "../main-view-layout-runtime.js";

function createStore() {
  let state = {
    locale: "zh",
    session: { workspacePath: "/tmp/workspace", projectId: 7 },
    assembly: {
      selectedChrName: "Chr01",
      trackDragOffsets: [],
      supportMirroredCtgs: [],
      actionStatus: "",
      actionError: "",
      mainViewHistory: {
        chrName: "Chr01",
        canUndo: false,
        canRedo: false,
        canReset: false,
        appliedOperationCount: 0,
        retainedOperationCount: 0,
        inFlight: false,
      },
    },
  };
  return {
    getState: () => state,
    setState(next) {
      state = { ...state, ...next };
    },
  };
}

test("main-view layout action reloads authoritative offsets and history in one serialized task", async () => {
  const store = createStore();
  const calls = [];
  const changed = await runMainViewLayoutAction(
    {},
    store,
    {
      action: "drag-ctg",
      args: { trackRole: "primary", assemblyCtgId: 11, offsetBp: 120 },
    },
    {
      async runSerializedProjectViewMutation(currentStore, task) {
        calls.push("serialized");
        assert.equal(currentStore, store);
        return task(() => true);
      },
      async runMainViewLayoutAction(payload) {
        calls.push(payload);
        assert.equal(store.getState().assembly.mainViewHistory.inFlight, true);
        return {
          changed: true,
          operation: { kind: "drag-ctg", targetCount: 1, targetName: "ctg11" },
          status: {
            chrName: "Chr01",
            canUndo: true,
            canRedo: false,
            canReset: true,
            undoOperation: { kind: "drag-ctg", targetCount: 1, targetName: "ctg11" },
            redoOperation: null,
            appliedOperationCount: 1,
            retainedOperationCount: 1,
          },
        };
      },
      async loadProjectAssemblyViewState(identity) {
        calls.push({ load: identity });
        return {
          trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 11, offsetBp: 120 }],
          supportMirroredCtgs: [{ datasetId: 22, assemblyCtgId: 30 }],
        };
      },
      mapAssemblyError({ error }) {
        return { userMessage: String(error?.message || error) };
      },
      rerender() {
        calls.push("render");
      },
    },
  );

  assert.equal(changed, true);
  assert.deepEqual(calls[2], {
    workspaceRoot: "/tmp/workspace",
    projectId: 7,
    chrName: "Chr01",
    action: "drag-ctg",
    args: { trackRole: "primary", assemblyCtgId: 11, offsetBp: 120 },
  });
  assert.deepEqual(store.getState().assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 11, offsetBp: 120 },
  ]);
  assert.equal(store.getState().assembly.mainViewHistory.canUndo, true);
  assert.equal(store.getState().assembly.mainViewHistory.inFlight, false);
});

test("main-view layout action ignores an obsolete project response", async () => {
  const store = createStore();
  let current = true;
  const changed = await runMainViewLayoutAction(
    {},
    store,
    { action: "delete-mirror", args: { datasetId: 22, assemblyCtgId: 30 } },
    {
      async runSerializedProjectViewMutation(_store, task) {
        return task(() => current);
      },
      async runMainViewLayoutAction() {
        current = false;
        return { changed: true };
      },
      async loadProjectAssemblyViewState() {
        throw new Error("stale action must not reload another project");
      },
      mapAssemblyError() {
        throw new Error("stale action must not report into another project");
      },
      rerender() {},
    },
  );
  assert.equal(changed, false);
});
