import test from "node:test";
import assert from "node:assert/strict";

import { runMainViewHistoryControlAction } from "../main-view-history-runtime.js";
import {
  isMainViewHistoryEligibleAction,
  normalizeMainViewHistoryStatus,
} from "../main-view-history-state.js";

function createStore(overrides = {}) {
  let state = {
    locale: "zh",
    session: { workspacePath: "/tmp/workspace", projectId: 7 },
    assembly: {
      selectedChrName: "Chr01",
      selectedCtgId: 9,
      chrCtgs: [{ assemblyCtgId: 9 }, { assemblyCtgId: 12 }],
      trackSelectedCtgIds: [9, 12],
      actionStatus: "",
      actionError: "",
      mainViewHistory: {
        chrName: "Chr01",
        canUndo: true,
        canRedo: false,
        canReset: true,
        undoOperation: { kind: "flip-ctg", targetCount: 1, targetName: "ctg-12" },
        redoOperation: null,
        appliedOperationCount: 1,
        retainedOperationCount: 1,
        inFlight: false,
      },
      ...overrides,
    },
  };
  return {
    getState() {
      return state;
    },
    setState(next) {
      state = { ...state, ...next };
    },
  };
}

test("main-view undo locks controls, reloads the chromosome, and locates one affected ctg", async () => {
  const store = createStore();
  const calls = [];
  const rerenderLocks = [];
  const highlighted = [];
  const focusModes = [];
  const changed = await runMainViewHistoryControlAction({}, store, "undo", {
    async executeMainViewHistoryAction(payload) {
      calls.push(payload);
      assert.equal(store.getState().assembly.mainViewHistory.inFlight, true);
      return {
        changed: true,
        invalidated: false,
        affectedCtgIds: [12],
        operation: { kind: "flip-ctg", targetCount: 1, targetName: "ctg-12" },
        status: {
          chrName: "Chr01",
          canUndo: false,
          canRedo: true,
          canReset: false,
          undoOperation: null,
          redoOperation: { kind: "flip-ctg", targetCount: 1, targetName: "ctg-12" },
          appliedOperationCount: 0,
          retainedOperationCount: 1,
        },
      };
    },
    async loadAssemblyView(_host, currentStore, options) {
      calls.push({ reload: options });
      currentStore.setState({
        assembly: {
          ...currentStore.getState().assembly,
          chrCtgs: [{ assemblyCtgId: 9 }, { assemblyCtgId: 12 }],
        },
      });
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    rerender(_host, currentStore) {
      rerenderLocks.push(currentStore.getState().assembly.mainViewHistory.inFlight);
    },
    scheduleHighlightClear(_host, _store, assemblyCtgId) {
      highlighted.push(assemblyCtgId);
    },
    setPendingTrackAutoFocusMode(mode) {
      focusModes.push(mode);
    },
  });

  assert.equal(changed, true);
  assert.deepEqual(calls, [
    {
      workspaceRoot: "/tmp/workspace",
      projectId: 7,
      chrName: "Chr01",
      action: "undo",
    },
    {
      reload: { keepCurrentChr: true, keepCurrentCtg: true, renderLoading: false },
    },
  ]);
  assert.deepEqual(rerenderLocks, [true, false]);
  assert.equal(store.getState().assembly.selectedCtgId, 12);
  assert.equal(store.getState().assembly.historyHighlightCtgId, 12);
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, []);
  assert.deepEqual(highlighted, [12]);
  assert.deepEqual(focusModes, ["start"]);
  assert.equal(store.getState().assembly.mainViewHistory.canRedo, true);
});

test("main-view reset confirmation names the chromosome and retained applied count", async () => {
  const store = createStore({
    mainViewHistory: {
      chrName: "Chr01",
      canUndo: true,
      canRedo: false,
      canReset: true,
      undoOperation: { kind: "rename-ctg", targetCount: 1, targetName: "ctg-9" },
      redoOperation: null,
      appliedOperationCount: 6,
      retainedOperationCount: 6,
      inFlight: false,
    },
  });
  const messages = [];
  const changed = await runMainViewHistoryControlAction({}, store, "reset", {
    async executeMainViewHistoryAction() {
      throw new Error("reset must not run after cancellation");
    },
    async loadAssemblyView() {},
    mapAssemblyError() {
      return { userMessage: "error" };
    },
    rerender() {},
    confirm(message) {
      messages.push(message);
      return false;
    },
  });

  assert.equal(changed, false);
  assert.equal(messages.length, 1);
  assert.match(messages[0], /确认重置 Chr01/);
  assert.match(messages[0], /当前 6 项/);
});

test("main-view history state preserves an active in-flight lock and excludes phased flips", () => {
  const normalized = normalizeMainViewHistoryStatus({
    chrName: "Chr01",
    canUndo: true,
    undoOperation: { kind: "flip-ctg", targetCount: 1 },
    appliedOperationCount: 1,
    inFlight: true,
  });
  assert.equal(normalized.inFlight, true);
  assert.equal(isMainViewHistoryEligibleAction("flip-ctg", { assemblyCtgId: 2 }), true);
  assert.equal(isMainViewHistoryEligibleAction("flip-ctg", { phasedTrackItemId: 99 }), false);
});
