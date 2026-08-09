import {
  test,
  assert,
  bindAssemblyPageImpl,
  bindAssemblyPage,
  __testApplySupportDatasetSelection,
  __testBuildAssemblyContextMenuItems,
  __testCreateEditorActionRuntimeAdapters,
  __testBindAssemblyContextMenu,
  __testCreateActionFeedbackDismissCoordinator,
  __testCreateTrackViewportResizeCoordinator,
  __testCreateSubviewBandTooltipCoordinator,
  __testGetAssemblyActionFeedbackSignature,
  __testHandleTrackDeleteHotkey,
  __testBindTrackScrollSync,
  __testResetMeasuredTrackViewportWidths,
  __testResolveAssemblyCtgContextTarget,
  __testCollectMemberChipSelectionResult,
  __testRunBatchDeleteTrackCtgs,
  __testRunBatchRestoreDeletedCtgs,
  __testRestoreSelectedDeletedCtgs,
  renderAssemblyPage,
  createState,
  createStore,
  createFakeTimerApi,
} from "./tabs-semantics-harness.mjs";

test("context menu does not expose redundant subview member-editor shortcuts", () => {
  const store = createStore(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support" },
            bottom: { contigId: 2, role: "primary" },
          },
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
  assert.ok(items.every((item) => item.label !== "编辑上方 ctg 成员"));
  assert.ok(items.every((item) => item.label !== "编辑下方 ctg 成员"));
});

test("member editor modal is absent even when member-editor state is populated", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        ctgDetail: {
          assemblyCtgId: 8,
          name: "ctg-beta",
          members: [
            {
              assemblyCtgMemberId: 1001,
              assemblySeqId: 7001,
              memberOrder: 1,
              seqName: "seq_a",
              datasetName: "flye",
              sourceStart: 1,
              sourceEnd: 100,
              leftEndType: "normal",
              rightEndType: "normal",
              hidden: false,
            },
            {
              assemblyCtgMemberId: 1002,
              assemblySeqId: 7002,
              memberOrder: 2,
              seqName: "seq_b",
              datasetName: "flye",
              sourceStart: 11,
              sourceEnd: 200,
              leftEndType: "normal",
              rightEndType: "normal",
              hidden: false,
            },
          ],
        },
        memberEditorModal: {
          open: true,
          ctgId: 8,
          ctgName: "ctg-beta",
          baselineCtgName: "ctg-beta",
          rows: [
            {
              rowKey: "m-1001",
              assemblyCtgMemberId: 1001,
              assemblySeqId: 7001,
              fixedOrder: 1,
              seqName: "seq_a",
              datasetName: "flye",
              overallLen: 1000,
              sourceStart: 1,
              sourceEnd: 100,
              isNew: false,
            },
            {
              rowKey: "m-1002",
              assemblyCtgMemberId: 1002,
              assemblySeqId: 7002,
              fixedOrder: 2,
              seqName: "seq_b",
              datasetName: "flye",
              overallLen: 2000,
              sourceStart: 11,
              sourceEnd: 200,
              isNew: false,
            },
          ],
        },
      },
    }),
  );
  assert.doesNotMatch(html, /assembly-member-editor-modal/);
  assert.doesNotMatch(html, /Order/);
  assert.doesNotMatch(html, /Overall_len/);
  assert.doesNotMatch(html, /member-editor-row-list/);
  assert.doesNotMatch(html, /member-editor-ctg-name-input/);
  assert.doesNotMatch(html, /Seq ID \/ Ctg ID \/ Ctg Name/);
  assert.doesNotMatch(html, /data-member-row-key="m-1001"/);
});

test("context menu on track blank area exposes batch delete for box-selected ctgs", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const blankTarget = {
    closest() {
      return null;
    },
  };
  listenerMap.get("contextmenu")?.({
    target: blankTarget,
    clientX: 100,
    clientY: 80,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.match(menuState.innerHTML, /删除已框选 contig（2）/);
  assert.match(menuState.innerHTML, /隐藏已框选 contig（2）/);
  assert.match(menuState.innerHTML, /解除隐藏已框选 contig（2）/);
});

test("member-card ctg context menu exposes batch hide/unhide/delete for multi-selection", () => {
  const store = createStore(
    createState({
      assembly: {
        trackSelectedCtgIds: [2, 8],
      },
    }),
  );
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: null },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host: {},
  });

  const labels = items.map((item) => item.label);
  assert.ok(labels.includes("隐藏已框选 contig（2）"));
  assert.ok(labels.includes("解除隐藏已框选 contig（2）"));
  assert.ok(labels.includes("删除已框选 contig（2）"));
  assert.ok(!labels.includes("翻转 contig"));
  assert.ok(!labels.includes("重命名 contig..."));
  assert.ok(!labels.includes("隐藏 contig"));
  assert.ok(!labels.includes("解除隐藏 contig"));
  assert.ok(!labels.includes("删除 contig"));
  assert.ok(!labels.includes("更多 contig 操作（当前版本未接入）"));
});

test("context menu on members blank area exposes batch restore for selected deleted ctgs", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedDeletedCtgRecordIds: [9101, 9102],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const blankTarget = {
    closest() {
      return null;
    },
  };
  listenerMap.get("contextmenu")?.({
    target: blankTarget,
    clientX: 100,
    clientY: 80,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.match(menuState.innerHTML, /撤销删除已框选 contig（2）/);
});

test("context menu on a subview hit exposes left and right anchor toggles for the same hit", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(createState());
  __testBindAssemblyContextMenu(host, store);

  const hitTarget = {
    closest(selector) {
      if (selector === "[data-subview-hit-key]") {
        return {
          getAttribute(name) {
            if (name === "data-subview-hit-key") return "hit-1";
            if (name === "data-subview-hit-left-active") return "0";
            if (name === "data-subview-hit-right-active") return "1";
            return null;
          },
          classList: {
            add() {},
            remove() {},
          },
        };
      }
      if (selector === "[data-member-seq-id]") {
        return null;
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: hitTarget,
    clientX: 100,
    clientY: 80,
    preventDefault() {},
  });

  assert.match(menuState.innerHTML, /left anchor on/);
  assert.match(menuState.innerHTML, /right anchor off/);
});

test("Ctrl/Cmd + right click toggles deleted ctg selection without opening context menu", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedDeletedCtgRecordIds: [9101],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const deletedTarget = {
    closest(selector) {
      if (selector === "[data-deleted-ctg-record-id]") {
        return {
          getAttribute(name) {
            if (name === "data-deleted-ctg-record-id") return "9102";
            if (name === "data-deleted-assembly-ctg-id") return "77";
            return null;
          },
        };
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: deletedTarget,
    clientX: 40,
    clientY: 50,
    ctrlKey: true,
    metaKey: false,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.equal(menuState.innerHTML, "");
  assert.deepEqual(store.getState().assembly.selectedDeletedCtgRecordIds, [9101, 9102]);
});

test("Ctrl/Cmd + right click toggles primary member-card selection without opening context menu", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        trackSelectedCtgIds: [2],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const memberChipTarget = {
    closest(selector) {
      if (selector === ".assembly-member-chip-region [data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      if (selector === "[data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      if (selector === "[data-track-contig-id][data-track-role]") {
        return null;
      }
      if (selector === "[data-deleted-ctg-record-id]") {
        return null;
      }
      if (selector === "[data-member-seq-id]") {
        return null;
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: memberChipTarget,
    clientX: 40,
    clientY: 50,
    ctrlKey: true,
    metaKey: false,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.equal(menuState.innerHTML, "");
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, [2, 8]);
});

test("member-chip box-selection collector returns both primary and deleted selections", () => {
  const regionEl = {
    querySelectorAll(selector) {
      if (selector === "[data-assembly-ctg-id]") {
        return [
          {
            getAttribute(name) {
              if (name === "data-assembly-ctg-id") return "2";
              return null;
            },
            offsetLeft: 10,
            offsetTop: 10,
            offsetWidth: 80,
            offsetHeight: 40,
          },
          {
            getAttribute(name) {
              if (name === "data-assembly-ctg-id") return "8";
              return null;
            },
            offsetLeft: 180,
            offsetTop: 10,
            offsetWidth: 80,
            offsetHeight: 40,
          },
        ];
      }
      if (selector === "[data-deleted-ctg-record-id]") {
        return [
          {
            getAttribute(name) {
              if (name === "data-deleted-ctg-record-id") return "9101";
              return null;
            },
            offsetLeft: 12,
            offsetTop: 80,
            offsetWidth: 80,
            offsetHeight: 40,
          },
        ];
      }
      return [];
    },
  };
  const selectionRect = {
    left: 0,
    right: 100,
    top: 0,
    bottom: 130,
  };
  const selection = __testCollectMemberChipSelectionResult(regionEl, selectionRect);
  assert.deepEqual(selection.primarySelectedCtgIds, [2]);
  assert.deepEqual(selection.deletedSelectedRecordIds, [9101]);
});

test("Delete hotkey triggers batch delete for box-selected ctgs on assembly tab", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  const deleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "DIV", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async (_host, _store, selectedIds) => {
        deleteCalls.push(selectedIds);
      },
    },
  );

  assert.equal(handled, true);
  assert.equal(event.preventDefaultCalls, 1);
  assert.deepEqual(deleteCalls, [[2, 8]]);
});

test("Delete hotkey triggers subview-local batch delete for box-selected track-pair ctgs", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairSelectedCtgs: [
            { trackRole: "support", contigId: 30 },
            { trackRole: "primary", contigId: 2 },
          ],
        },
      },
    }),
  );
  const subviewDeleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "DIV", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async () => {
        throw new Error("main-track batch delete should not run in this case");
      },
      subviewDeleteFn: async (_host, _store, selectedEntries) => {
        subviewDeleteCalls.push(selectedEntries);
      },
    },
  );

  assert.equal(handled, true);
  assert.equal(event.preventDefaultCalls, 1);
  assert.deepEqual(subviewDeleteCalls, [[
    { trackRole: "primary", contigId: 2 },
    { trackRole: "support", contigId: 30 },
  ]]);
});

test("batch deleting selected track ctgs uses local refresh instead of reloading the assembly view", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      trackSelectedCtgIds: [2, 8, 30],
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

  const actionCalls = [];
  const reloadCalls = [];
  const localRefreshCalls = [];
  const hadWindow = Object.prototype.hasOwnProperty.call(globalThis, "window");
  const previousWindow = globalThis.window;
  if (!hadWindow) {
    globalThis.window = {};
  }
  let result;
  try {
    result = await __testRunBatchDeleteTrackCtgs(
      host,
      store,
      [2, 8, 30],
      {
        runAction: async (payload) => {
          actionCalls.push(payload);
          return { changed: true };
        },
        reloadView: async (_host, _store, options) => {
          reloadCalls.push(options);
        },
        refreshAfterBatchDelete: async (_host, _store, payload) => {
          localRefreshCalls.push(payload);
        },
      },
    );
  } finally {
    if (hadWindow) {
      globalThis.window = previousWindow;
    } else {
      delete globalThis.window;
    }
  }

  assert.deepEqual(actionCalls.map((item) => item.args.assemblyCtgId), [2, 8]);
  assert.equal(reloadCalls.length, 0);
  assert.equal(localRefreshCalls.length, 1);
  assert.deepEqual(localRefreshCalls[0].deletedAssemblyCtgIds, [2, 8]);
  assert.deepEqual(localRefreshCalls[0].attemptedAssemblyCtgIds, [2, 8]);
  assert.equal(result.deletedCount, 2);
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, []);
});

test("batch restoring selected deleted ctgs reloads view once after all actions", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      selectedDeletedCtgRecordIds: [9101, 9102],
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

  const actionCalls = [];
  const reloadCalls = [];
  const hadWindow = Object.prototype.hasOwnProperty.call(globalThis, "window");
  const previousWindow = globalThis.window;
  if (!hadWindow) {
    globalThis.window = {};
  }
  let result;
  try {
    result = await __testRunBatchRestoreDeletedCtgs(
      host,
      store,
      [9101, 9102],
      {
        runAction: async (payload) => {
          actionCalls.push(payload);
          return { restored: true };
        },
        reloadView: async (_host, _store, options) => {
          reloadCalls.push(options);
        },
      },
    );
  } finally {
    if (hadWindow) {
      globalThis.window = previousWindow;
    } else {
      delete globalThis.window;
    }
  }

  assert.deepEqual(actionCalls.map((item) => item.args.deletedCtgRecordId), [9101, 9102]);
  assert.equal(reloadCalls.length, 1);
  assert.deepEqual(reloadCalls[0], {
    keepCurrentChr: true,
    keepCurrentCtg: true,
    renderLoading: false,
  });
  assert.equal(result.restoredCount, 2);
  assert.deepEqual(store.getState().assembly.selectedDeletedCtgRecordIds, []);
});

test("restoring selected deleted ctgs does not require confirm dialog", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedDeletedCtgRecordIds: [9101],
      },
    }),
  );
  const actionCalls = [];
  const reloadCalls = [];
  const hadWindow = Object.prototype.hasOwnProperty.call(globalThis, "window");
  const previousWindow = globalThis.window;
  globalThis.window = {
    ...(hadWindow && previousWindow ? previousWindow : {}),
    confirm() {
      throw new Error("confirm should not be called when restoring deleted contigs");
    },
  };
  try {
    await __testRestoreSelectedDeletedCtgs(host, store, [9101], {
      runAction: async (payload) => {
        actionCalls.push(payload);
        return { restored: true };
      },
      reloadView: async (_host, _store, options) => {
        reloadCalls.push(options);
      },
    });
  } finally {
    if (hadWindow) {
      globalThis.window = previousWindow;
    } else {
      delete globalThis.window;
    }
  }

  assert.deepEqual(actionCalls.map((item) => item.args.deletedCtgRecordId), [9101]);
  assert.equal(reloadCalls.length, 1);
});

test("Delete hotkey is ignored while typing in input fields", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  const deleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "INPUT", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async (_host, _store, selectedIds) => {
        deleteCalls.push(selectedIds);
      },
    },
  );

  assert.equal(handled, false);
  assert.equal(event.preventDefaultCalls, 0);
  assert.deepEqual(deleteCalls, []);
});

test("Delete hotkey still works when last focused element is a button", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  const deleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "BUTTON", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async (_host, _store, selectedIds) => {
        deleteCalls.push(selectedIds);
      },
    },
  );

  assert.equal(handled, true);
  assert.equal(event.preventDefaultCalls, 1);
  assert.deepEqual(deleteCalls, [[2, 8]]);
});

test("context menu on member row exposes retained sequence actions only", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(createState());
  __testBindAssemblyContextMenu(host, store);

  const memberTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return null;
      }
      if (selector === "[data-assembly-ctg-id]") {
        return null;
      }
      if (selector === "[data-member-seq-id]") {
        return {
          getAttribute(name) {
            if (name === "data-member-seq-id") return "101";
            if (name === "data-member-hidden") return "0";
            if (name === "data-member-id") return "401";
            return null;
          },
        };
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: memberTarget,
    clientX: 24,
    clientY: 16,
    preventDefault() {},
  });

  assert.ok(menuState.innerHTML.indexOf("对齐详情（当前版本未接入）") < menuState.innerHTML.indexOf("定位 Seq 101"));
  assert.ok(menuState.innerHTML.indexOf("定位 Seq 101") < menuState.innerHTML.indexOf("翻转 sequence"));
  assert.ok(menuState.innerHTML.indexOf("翻转 sequence") < menuState.innerHTML.indexOf("隐藏 sequence"));
  assert.match(menuState.innerHTML, /定位 Seq 101/);
  assert.match(menuState.innerHTML, /对齐详情（当前版本未接入）/);
  assert.match(menuState.innerHTML, /锚点联动（当前版本未接入）/);
  assert.match(menuState.innerHTML, /翻转 sequence/);
  assert.match(menuState.innerHTML, /隐藏 sequence/);
  assert.doesNotMatch(menuState.innerHTML, /设置区间/);
  assert.doesNotMatch(menuState.innerHTML, /从当前 contig 移除/);
  assert.doesNotMatch(menuState.innerHTML, /在此 member 后拆分/);
  assert.match(menuState.innerHTML, /当前版本未接入/);
  assert.match(menuState.innerHTML, /disabled/);
});

test("context target resolver prefers track glyph metadata and falls back to legacy ctg nodes", () => {
  const trackTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return {
          getAttribute(name) {
            if (name === "data-track-contig-id") return "30";
            if (name === "data-track-role") return "support";
            return null;
          },
        };
      }
      if (selector === "[data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      return null;
    },
  };
  const legacyTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return null;
      }
      if (selector === "[data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      return null;
    },
  };

  assert.deepEqual(__testResolveAssemblyCtgContextTarget(trackTarget), {
    assemblyCtgId: 30,
    trackRole: "support",
    isMirror: false,
    datasetId: null,
  });
  assert.deepEqual(__testResolveAssemblyCtgContextTarget(legacyTarget), {
    assemblyCtgId: 8,
    trackRole: null,
    isMirror: false,
    datasetId: null,
  });
});

test("action feedback toast auto-dismisses after 1 second", () => {
  const timerApi = createFakeTimerApi();
  let dismissCount = 0;
  const coordinator = __testCreateActionFeedbackDismissCoordinator({
    setTimeoutFn: timerApi.setTimeout,
    clearTimeoutFn: timerApi.clearTimeout,
    onDismiss: () => {
      dismissCount += 1;
    },
  });
  const signature = __testGetAssemblyActionFeedbackSignature({
    actionStatus: "move-ctg 完成（changed=true）。",
    actionError: "",
  });

  coordinator.onFeedbackChange(signature);
  timerApi.advance(999);
  assert.equal(dismissCount, 0);
  timerApi.advance(1);
  assert.equal(dismissCount, 1);
});

test("action feedback toast dismisses 0.5 second after pointer move", () => {
  const timerApi = createFakeTimerApi();
  let dismissCount = 0;
  const coordinator = __testCreateActionFeedbackDismissCoordinator({
    setTimeoutFn: timerApi.setTimeout,
    clearTimeoutFn: timerApi.clearTimeout,
    onDismiss: () => {
      dismissCount += 1;
    },
  });
  const signature = __testGetAssemblyActionFeedbackSignature({
    actionStatus: "move-ctg 完成（changed=true）。",
    actionError: "",
  });

  coordinator.onFeedbackChange(signature);
  timerApi.advance(200);
  coordinator.onPointerMove(signature);
  timerApi.advance(499);
  assert.equal(dismissCount, 0);
  timerApi.advance(1);
  assert.equal(dismissCount, 1);
  timerApi.advance(1000);
  assert.equal(dismissCount, 1);
});

test("subview band tooltip coordinator waits 500ms before showing and hides on leave", () => {
  const timerApi = createFakeTimerApi();
  const calls = [];
  const coordinator = __testCreateSubviewBandTooltipCoordinator({
    setTimeoutFn: timerApi.setTimeout,
    clearTimeoutFn: timerApi.clearTimeout,
    onShow: (context) => {
      calls.push(["show", context.text, context.point.x, context.point.y]);
    },
    onMove: (context) => {
      calls.push(["move", context.text, context.point.x, context.point.y]);
    },
    onHide: () => {
      calls.push(["hide"]);
    },
  });

  const token = { id: "band-1" };
  coordinator.enter({
    token,
    text: "support-top: 2,200-3,400 bp",
    point: { x: 100, y: 120 },
  });
  timerApi.advance(499);
  assert.deepEqual(calls, []);
  coordinator.move({
    token,
    text: "support-top: 2,200-3,400 bp",
    point: { x: 140, y: 160 },
  });
  timerApi.advance(1);
  assert.deepEqual(calls, [["show", "support-top: 2,200-3,400 bp", 140, 160]]);

  coordinator.move({
    token,
    text: "support-top: 2,200-3,400 bp",
    point: { x: 170, y: 180 },
  });
  assert.deepEqual(calls[1], ["move", "support-top: 2,200-3,400 bp", 170, 180]);

  coordinator.leave(token);
  assert.deepEqual(calls[2], ["hide"]);
});

test("track viewport resize coordinator rerenders only when viewport width meaningfully changes", () => {
  let measuredWidth = 1200;
  let viewportWidth = 1200;
  const rerenderWidths = [];
  const coordinator = __testCreateTrackViewportResizeCoordinator({
    getViewportWidth: () => viewportWidth,
    getMeasuredWidth: () => measuredWidth,
    setMeasuredWidth: (nextWidth) => {
      measuredWidth = nextWidth;
    },
    onViewportResize: (nextWidth) => {
      rerenderWidths.push(nextWidth);
    },
  });

  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, []);

  viewportWidth = 1201;
  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, []);

  viewportWidth = 1460;
  assert.equal(coordinator.onResize(), true);
  assert.equal(measuredWidth, 1460);
  assert.deepEqual(rerenderWidths, [1460]);

  viewportWidth = 1460;
  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, [1460]);

  viewportWidth = 0;
  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, [1460]);
});

test("track viewport resize coordinator rerenders when subview or final-path viewport width changes even if primary is stable", () => {
  let measuredWidths = {
    primary: 1200,
    subview: 1200,
    finalPath: 1200,
  };
  let viewportWidths = {
    primary: 1200,
    subview: 1200,
    finalPath: 1200,
  };
  const rerenderWidths = [];
  const coordinator = __testCreateTrackViewportResizeCoordinator({
    getViewportWidths: () => viewportWidths,
    getMeasuredWidths: () => measuredWidths,
    setMeasuredWidths: (nextWidths) => {
      measuredWidths = nextWidths;
    },
    onViewportResize: (nextWidths) => {
      rerenderWidths.push(nextWidths);
    },
  });

  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, []);

  viewportWidths = {
    primary: 1200,
    subview: 1180,
    finalPath: 1200,
  };
  assert.equal(coordinator.onResize(), true);
  assert.deepEqual(measuredWidths, {
    primary: 1200,
    subview: 1180,
    finalPath: 1200,
  });
  assert.deepEqual(rerenderWidths, [{
    primary: 1200,
    subview: 1180,
    finalPath: 1200,
  }]);

  viewportWidths = {
    primary: 1200,
    subview: 1180,
    finalPath: 1176,
  };
  assert.equal(coordinator.onResize(), true);
  assert.deepEqual(measuredWidths, {
    primary: 1200,
    subview: 1180,
    finalPath: 1176,
  });
});

test("support-ds change clears subview state and loads support chr ctgs for the selected chr", async () => {
  const store = createStore(
    createState({
      assembly: {
        supportDatasetId: 22,
        selectedChrName: "Chr01",
        summary: "旧摘要",
        supportChrCtgs: [{ assemblyCtgId: 99, name: "stale" }],
        subviewTrackDragOffsets: [
          { slot: "top", contigId: 2, offsetPx: 50 },
          { slot: "bottom", contigId: 30, offsetPx: -20 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "旧消息",
          error: "旧错误",
          summary: { mode: "2-contig" },
        },
      },
    }),
  );
  const loadCalls = [];
  const loadedSupportCtgs = [
    { assemblyCtgId: 31, name: "support-ctg-2", assignedChrName: "Chr01", memberCount: 1, totalLength: 450, anchorStart: 360 },
  ];

  await __testApplySupportDatasetSelection(store, 33, {
    loadSupportChrCtgs: async (workspaceRoot, projectId, chrName, datasetId) => {
      loadCalls.push({ workspaceRoot, projectId, chrName, datasetId });
      return loadedSupportCtgs;
    },
    rerenderView: () => {},
  });

  assert.deepEqual(loadCalls, [
    {
      workspaceRoot: "/tmp/workspace",
      projectId: 7,
      chrName: "Chr01",
      datasetId: 33,
    },
  ]);
  assert.equal(store.getState().assembly.supportDatasetId, 33);
  assert.deepEqual(store.getState().assembly.supportChrCtgs, loadedSupportCtgs);
  assert.deepEqual(store.getState().assembly.subviewTrackDragOffsets, []);
  assert.equal(store.getState().assembly.summary, "");
  assert.deepEqual(store.getState().assembly.subview, {
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
    activeAnchors: [],
    manualAnchors: [],
    flippedCtgs: [],
    trackPairHiddenCtgs: [],
    trackPairSelectedCtgs: [],
    message: "",
    error: "",
    summary: null,
  });
});

test("context-menu listeners install only once for the route host", () => {
  const listenerTypes = [];
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return {
          classList: { add() {}, remove() {} },
          style: {},
          innerHTML: "",
          querySelectorAll() {
            return [];
          },
        };
      }
      return null;
    },
    addEventListener(type) {
      listenerTypes.push(type);
    },
  };

  __testBindAssemblyContextMenu(host, createStore(createState()));
  __testBindAssemblyContextMenu(host, createStore(createState()));

  assert.deepEqual(listenerTypes, ["click", "scroll", "contextmenu"]);
});

test("bindings binder rejects missing required deps at the boundary", () => {
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());

  assert.throws(
    () => bindAssemblyPageImpl(host, store, {}),
    /Missing assembly binding deps:/,
  );
});

test("bindings persist main-track view changes after committing a main control input", () => {
  const listenerMap = new Map();
  const input = {
    value: "500",
    closest() {
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-track-min-tick-unit-kb") {
        return input;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const persisted = [];
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/ws", projectId: 7 },
      assembly: {
        trackView: {
          supportDsCtgLen: 0,
          minTickUnitKb: 250,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
      },
    }),
  );
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async (_host, currentStore) => {
    persisted.push(currentStore.getState().assembly.trackView);
  };

  bindAssemblyPageImpl(host, store, deps);
  listenerMap.get("change")?.();

  assert.deepEqual(store.getState().assembly.trackView, {
    supportDsCtgLen: 0,
    supportDsCtgLenBp: 0,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 10,
    viewSpanKb: 500,
    pixelUnit: 500,
    tickLength: 10000,
    tickBp: 10000,
    alignmentLength: 1000,
    block_length: 1000,
    mapq: 0,
  });
  assert.deepEqual(persisted, [
    {
      supportDsCtgLen: 0,
      supportDsCtgLenBp: 0,
      minTickUnitKb: 500,
      minTickKb: 500,
      maxTickCount: 10,
      viewSpanKb: 500,
      pixelUnit: 500,
      tickLength: 10000,
      tickBp: 10000,
      alignmentLength: 1000,
      block_length: 1000,
      mapq: 0,
    },
  ]);
});

test("bindings switch the final path card between graph and table modes and persist the choice", async () => {
  const tableListeners = new Map();
  const tableButton = {
    dataset: {
      finalPathViewMode: "table",
    },
    addEventListener(type, handler) {
      tableListeners.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "button[data-final-path-view-mode]") {
        return [tableButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "flye_ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );
  let rerenderCount = 0;
  const persistCalls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.rerender = () => {
    rerenderCount += 1;
  };
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async (_host, currentStore) => {
    persistCalls.push({
      finalPathViewMode: currentStore.getState().assembly.finalPathViewMode,
    });
  };

  bindAssemblyPageImpl(host, store, deps);
  await tableListeners.get("click")?.({
    preventDefault() {},
  });

  assert.equal(store.getState().assembly.finalPathViewMode, "table");
  assert.equal(rerenderCount, 1);
  assert.deepEqual(persistCalls, [{ finalPathViewMode: "table" }]);
});

test("bindings keep the switched final-path table fully visible when it fits in the viewport", () => {
  const tableListeners = new Map();
  const tableButton = {
    dataset: {
      finalPathViewMode: "table",
    },
    addEventListener(type, handler) {
      tableListeners.set(type, handler);
    },
  };
  let rerenderCount = 0;
  const graphCard = {
    getBoundingClientRect() {
      return {
        top: 520,
        bottom: 920,
        height: 400,
      };
    },
  };
  const tableCard = {
    getBoundingClientRect() {
      return {
        top: 520,
        bottom: 1040,
        height: 520,
      };
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".final-path-card") {
        return rerenderCount > 0 ? tableCard : graphCard;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "button[data-final-path-view-mode]") {
        return [tableButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                ctgName: "flye_ctg9",
                totalLength: 1200,
              },
            ],
            totalLength: 1200,
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.rerender = () => {
    rerenderCount += 1;
  };
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });

  const originalWindow = globalThis.window;
  const scrollCalls = [];
  globalThis.window = {
    innerHeight: 1000,
    scrollBy(options) {
      scrollCalls.push(options);
    },
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    tableListeners.get("click")?.({
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(store.getState().assembly.finalPathViewMode, "table");
  assert.equal(rerenderCount, 1);
  assert.deepEqual(scrollCalls, [{ left: 0, top: 56, behavior: "auto" }]);
});

test("bindings open track combo upward when the dropdown would overflow the window bottom", () => {
  const toggleListeners = new Map();
  const menuNode = {
    style: {},
    classList: {
      toggle() {},
    },
    getBoundingClientRect() {
      return {
        height: 220,
      };
    },
  };
  const comboNode = {
    classList: {
      values: new Set(),
      toggle(name, enabled) {
        if (enabled) {
          this.values.add(name);
        } else {
          this.values.delete(name);
        }
      },
      contains(name) {
        return this.values.has(name);
      },
    },
    querySelector(selector) {
      if (selector === ".assembly-track-combo-input") {
        return input;
      }
      if (selector === "[data-track-combo-toggle]") {
        return toggleButton;
      }
      if (selector === ".assembly-track-combo-menu") {
        return menuNode;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    getBoundingClientRect() {
      return {
        top: 860,
        bottom: 892,
        height: 32,
      };
    },
    contains() {
      return false;
    },
  };
  const input = {
    value: "10000",
    closest(selector) {
      return selector === "[data-track-combo-field]" ? comboNode : null;
    },
    addEventListener() {},
    focus() {},
    setAttribute() {},
  };
  const toggleButton = {
    addEventListener(type, handler) {
      toggleListeners.set(type, handler);
    },
    setAttribute() {},
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-track-min-tick-unit-kb") {
        return input;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });

  const originalWindow = globalThis.window;
  globalThis.window = {
    innerHeight: 900,
    setTimeout,
    clearTimeout,
    addEventListener() {},
    removeEventListener() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    toggleListeners.get("click")?.({
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(comboNode.classList.contains("is-open"), true);
  assert.equal(menuNode.style.top, "auto");
  assert.equal(menuNode.style.bottom, "calc(100% + 2px)");
});

test("bindings update final-path track prefs without persisting main-track view state", () => {
  const listenerMap = new Map();
  const input = {
    value: "500",
    closest() {
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const finalPathScroll = {
    scrollLeft: 640,
  };
  const host = {
    querySelector(selector) {
      if (selector === "#final-path-track-min-tick-unit-kb") {
        return input;
      }
      if (selector === "[data-final-path-graph-viewport]" || selector === ".assembly-final-path-svg-wrap") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  let persistedCount = 0;
  let rerenderCount = 0;
  let rememberedCount = 0;
  let suppressCount = 0;
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "flye_ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathTrackView: {
          minTickUnitKb: 250,
          maxTickCount: 10,
        },
      },
    }),
  );
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async () => {
    persistedCount += 1;
  };
  deps.rerender = () => {
    rerenderCount += 1;
  };
  deps.rememberTrackViewportAnchor = () => {
    rememberedCount += 1;
  };
  deps.markNextTrackAutoFocusSuppressed = () => {
    suppressCount += 1;
  };

  bindAssemblyPageImpl(host, store, deps);
  listenerMap.get("change")?.();

  assert.deepEqual(store.getState().assembly.finalPathTrackView, {
    supportDsCtgLen: 0,
    supportDsCtgLenBp: 0,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 10,
    viewSpanKb: 500,
    pixelUnit: 500,
    tickLength: 10000,
    tickBp: 10000,
    alignmentLength: 10000,
    block_length: 10000,
    mapq: 0,
  });
  assert.deepEqual(store.getState().assembly.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:500:10",
    scrollLeft: 640,
  });
  assert.equal(persistedCount, 0);
  assert.equal(rememberedCount, 0);
  assert.equal(suppressCount, 0);
  assert.equal(rerenderCount, 1);
});

test("track scroll sync restores and persists project-scoped main and subview scroll positions", () => {
  __testResetMeasuredTrackViewportWidths();
  const mainListeners = new Map();
  const subviewListeners = new Map();
  const finalPathScroll = {
    clientWidth: 1200,
  };
  const mainScroll = {
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
      focusCenter: "120",
      focusStart: "40",
    },
    clientWidth: 1200,
    scrollLeft: 0,
    addEventListener(type, handler) {
      mainListeners.set(type, handler);
    },
  };
  const subviewScroll = {
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
    clientWidth: 360,
    scrollLeft: 0,
    addEventListener(type, handler) {
      subviewListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return mainScroll;
      }
      if (selector === ".assembly-track-scroll.subview-track-scroll") {
        return subviewScroll;
      }
      if (selector === ".assembly-final-path-svg-wrap") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role]") {
        return [mainScroll, subviewScroll];
      }
      return [];
    },
  };
  const persisted = [];
  const store = createStore(
    createState({
      session: { projectId: 7 },
      assembly: {
        selectedChrName: "Chr01",
        selectedCtgId: 8,
        supportDatasetId: 22,
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 250,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        trackScrollState: {
          viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
          scrollLeft: 320,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 1909,
          selectedBRole: "support",
          selectedTrackARole: "",
          selectedTrackBRole: "",
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
          message: "",
          error: "",
          summary: {
            top: { role: "primary", contigId: 8 },
            bottom: { role: "support", contigId: 1909 },
          },
        },
        subviewTrackScrollState: {
          viewportKey: "7:Chr01:primary:8:support:1909",
          scrollLeft: 180,
        },
      },
    }),
  );

  __testBindTrackScrollSync(host, store, {
    schedulePersistAssemblyScrollState(_host, currentStore) {
      persisted.push({
        trackScrollState: currentStore.getState().assembly.trackScrollState,
        subviewTrackScrollState: currentStore.getState().assembly.subviewTrackScrollState,
      });
    },
  });

  assert.equal(mainScroll.scrollLeft, 320);
  assert.equal(subviewScroll.scrollLeft, 180);

  mainScroll.scrollLeft = 460;
  mainListeners.get("scroll")?.();
  assert.deepEqual(store.getState().assembly.trackScrollState, {
    viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
    scrollLeft: 460,
  });

  subviewScroll.scrollLeft = 210;
  subviewListeners.get("scroll")?.();
  assert.deepEqual(store.getState().assembly.subviewTrackScrollState, {
    viewportKey: "7:Chr01:primary:8:support:1909",
    scrollLeft: 210,
  });
  assert.deepEqual(persisted.slice(-2), [
    {
      trackScrollState: {
        viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
        scrollLeft: 460,
      },
      subviewTrackScrollState: {
        viewportKey: "7:Chr01:primary:8:support:1909",
        scrollLeft: 180,
      },
    },
    {
      trackScrollState: {
        viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
        scrollLeft: 460,
      },
      subviewTrackScrollState: {
        viewportKey: "7:Chr01:primary:8:support:1909",
        scrollLeft: 210,
      },
    },
  ]);
  __testResetMeasuredTrackViewportWidths();
});

test("track scroll sync restores and persists project-scoped final-path scroll positions", () => {
  __testResetMeasuredTrackViewportWidths();
  const mainListeners = new Map();
  const subviewListeners = new Map();
  const finalPathListeners = new Map();
  const mainScroll = {
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
      focusCenter: "120",
      focusStart: "40",
    },
    clientWidth: 1200,
    scrollLeft: 0,
    addEventListener(type, handler) {
      mainListeners.set(type, handler);
    },
  };
  const subviewScroll = {
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
    clientWidth: 360,
    scrollLeft: 0,
    addEventListener(type, handler) {
      subviewListeners.set(type, handler);
    },
  };
  const finalPathScroll = {
    clientWidth: 900,
    scrollLeft: 0,
    addEventListener(type, handler) {
      finalPathListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return mainScroll;
      }
      if (selector === ".assembly-track-scroll.subview-track-scroll") {
        return subviewScroll;
      }
      if (selector === ".assembly-final-path-svg-wrap" || selector === "[data-final-path-graph-viewport]") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role]") {
        return [mainScroll, subviewScroll];
      }
      return [];
    },
  };
  const persisted = [];
  const store = createStore(
    createState({
      assembly: {
        selectedChrName: "Chr01",
        selectedCtgId: 8,
        supportDatasetId: 22,
        finalPathViewMode: "graph",
        finalPathTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
        },
        finalPathTrackScrollState: {
          viewportKey: "7:Chr01:graph:10000:10",
          scrollLeft: 480,
        },
      },
    }),
  );

  __testBindTrackScrollSync(host, store, {
    schedulePersistAssemblyScrollState(_host, currentStore) {
      persisted.push(currentStore.getState().assembly.finalPathTrackScrollState);
    },
  });

  assert.equal(finalPathScroll.scrollLeft, 480);

  finalPathScroll.scrollLeft = 620;
  finalPathListeners.get("scroll")?.();

  assert.deepEqual(store.getState().assembly.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 620,
  });
  assert.deepEqual(persisted.at(-1), {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 620,
  });
  __testResetMeasuredTrackViewportWidths();
});

test("scoped track scroll sync preserves unrelated viewport state", () => {
  __testResetMeasuredTrackViewportWidths();
  const store = createStore(createState({
    assembly: {
      trackScrollState: { viewportKey: "main", scrollLeft: 320 },
      subviewTrackScrollState: { viewportKey: "subview", scrollLeft: 180 },
      finalPathTrackScrollState: { viewportKey: "final-path", scrollLeft: 480 },
    },
  }));
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };

  __testBindTrackScrollSync(host, store, {
    scope: "final-path",
    schedulePersistAssemblyScrollState() {
      assert.fail("a scoped bind without its viewport must not clear or persist sibling state");
    },
  });

  assert.deepEqual(store.getState().assembly.trackScrollState, {
    viewportKey: "main",
    scrollLeft: 320,
  });
  assert.deepEqual(store.getState().assembly.subviewTrackScrollState, {
    viewportKey: "subview",
    scrollLeft: 180,
  });
  assert.deepEqual(store.getState().assembly.finalPathTrackScrollState, {
    viewportKey: "final-path",
    scrollLeft: 480,
  });
  __testResetMeasuredTrackViewportWidths();
});

test("track scroll sync requests a rerender when subview viewport width differs from the measured main-view width", () => {
  __testResetMeasuredTrackViewportWidths();
  const mainScroll = {
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
      focusCenter: "120",
      focusStart: "40",
    },
    clientWidth: 1200,
    scrollLeft: 0,
    addEventListener() {},
  };
  const subviewScroll = {
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
    clientWidth: 360,
    scrollLeft: 0,
    addEventListener() {},
  };
  const finalPathScroll = {
    clientWidth: 1200,
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return mainScroll;
      }
      if (selector === ".assembly-track-scroll.subview-track-scroll") {
        return subviewScroll;
      }
      if (selector === ".assembly-final-path-svg-wrap") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role]") {
        return [mainScroll, subviewScroll];
      }
      return [];
    },
  };
  const store = createStore(createState());

  assert.equal(__testBindTrackScrollSync(host, store, {
    schedulePersistAssemblyScrollState() {},
  }), true);
  __testResetMeasuredTrackViewportWidths();
});

test("editor action adapter factory forwards shared runtime deps consistently", async () => {
  const runtimeDeps = { marker: "editor-runtime" };
  const calls = [];
  const adapters = __testCreateEditorActionRuntimeAdapters(runtimeDeps, {
    applyEditorAction(host, store, payload, deps) {
      calls.push({ type: "apply", payload, deps });
      return "apply-ok";
    },
    deleteSelectedTrackCtgs(host, store, selectedIds, deps) {
      calls.push({ type: "delete-track", selectedIds, deps });
      return "delete-track-ok";
    },
    deleteSelectedSubviewTrackPairCtgs(host, store, selectedEntries, deps) {
      calls.push({ type: "delete-subview", selectedEntries, deps });
      return "delete-subview-ok";
    },
    restoreSelectedDeletedCtgs(host, store, selectedRecordIds, deps, options) {
      calls.push({ type: "restore", selectedRecordIds, deps, options });
      return "restore-ok";
    },
    runBatchDeleteTrackCtgs(host, store, selectedIds, deps, options) {
      calls.push({ type: "batch-delete", selectedIds, deps, options });
      return "batch-delete-ok";
    },
    runBatchRestoreDeletedCtgs(host, store, selectedRecordIds, deps, options) {
      calls.push({ type: "batch-restore", selectedRecordIds, deps, options });
      return "batch-restore-ok";
    },
  });

  assert.equal(await adapters.applyEditorAction({}, {}, { kind: "join" }), "apply-ok");
  assert.equal(await adapters.deleteSelectedTrackCtgs({}, {}, [7, 8]), "delete-track-ok");
  assert.equal(
    await adapters.deleteSelectedSubviewTrackPairCtgs({}, {}, [{ trackRole: "support", contigId: 9 }]),
    "delete-subview-ok",
  );
  assert.equal(await adapters.restoreSelectedDeletedCtgs({}, {}, [11], { silent: true }), "restore-ok");
  assert.equal(await adapters.runBatchDeleteTrackCtgs({}, {}, [15], { skipReload: true }), "batch-delete-ok");
  assert.equal(
    await adapters.runBatchRestoreDeletedCtgs({}, {}, [19], { suppressFeedback: true }),
    "batch-restore-ok",
  );

  assert.equal(calls[0].deps, runtimeDeps);
  assert.equal(calls[1].deps.marker, "editor-runtime");
  assert.equal(typeof calls[1].deps.runBatchDeleteTrackCtgs, "function");
  assert.equal(calls[1].deps.localRefresh, true);
  assert.notEqual(calls[1].deps, runtimeDeps);
  assert.equal(calls[2].deps, runtimeDeps);
  assert.equal(calls[3].deps.marker, "editor-runtime");
  assert.equal(typeof calls[3].deps.runBatchRestoreDeletedCtgs, "function");
  assert.equal(calls[3].deps.localRefresh, true);
  assert.notEqual(calls[3].deps, runtimeDeps);
  assert.equal(calls[4].deps.marker, "editor-runtime");
  assert.equal(calls[4].deps.localRefresh, true);
  assert.notEqual(calls[4].deps, runtimeDeps);
  assert.deepEqual(calls[4].options, { skipReload: true });
  assert.equal(calls[5].deps.marker, "editor-runtime");
  assert.equal(calls[5].deps.localRefresh, true);
  assert.notEqual(calls[5].deps, runtimeDeps);
  assert.deepEqual(calls[5].options, { suppressFeedback: true });
});

test("assembly page public binder wires host-level listeners once for the same host", () => {
  const listenerTypes = [];
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener(type) {
      listenerTypes.push(type);
    },
  };
  const store = createStore(
    createState({
      initializer: {
        datasets: [],
      },
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 2, placedBp: 3300 }],
      },
    }),
  );
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPage(host, store);
    bindAssemblyPage(host, store);
  } finally {
    globalThis.window = originalWindow;
  }

  assert.deepEqual(listenerTypes, [
    "pointerdown",
    "pointermove",
    "pointerdown",
    "pointerdown",
    "click",
    "pointerover",
    "pointerout",
    "click",
    "click",
    "scroll",
    "contextmenu",
    "pointerdown",
    "pointerdown",
    "pointerdown",
    "pointerdown",
  ]);
});
