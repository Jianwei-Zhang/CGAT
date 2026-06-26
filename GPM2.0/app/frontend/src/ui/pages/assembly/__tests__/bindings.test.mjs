import test from "node:test";
import assert from "node:assert/strict";

import { bindAssemblyPage as bindAssemblyPageImpl } from "../bindings.js";

function createState() {
  return {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
    },
    assembly: {
      loading: false,
      activeTab: "assembly",
      chromosomes: [],
      membersCardCollapsed: true,
      trackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
    },
  };
}

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
}

function createBindingDeps(overrides = {}) {
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindFinalPathExport",
    "bindFinalPathGraphDrag",
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
  return {
    ...deps,
    syncSupportDatasetSelection: () => ({ changed: false, supportDatasetId: null }),
    ...overrides,
  };
}

test("bindings create phased track from the main track toolbar", async () => {
  let clickHandler = null;
  const createButton = {
    disabled: false,
    addEventListener(type, handler) {
      if (type === "click") {
        clickHandler = handler;
      }
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "[data-create-phased-track='1']" ? createButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  let createCalls = 0;
  const deps = createBindingDeps({
    createPhasedChrTrack() {
      createCalls += 1;
    },
  });

  bindAssemblyPageImpl(host, store, deps);
  assert.equal(typeof clickHandler, "function");

  await clickHandler({ preventDefault() {} });

  assert.equal(createCalls, 1);
});

test("support ds ctg len rules dialog only closes from X and confirms dirty drafts", async () => {
  const makeButton = () => {
    const listeners = new Map();
    return {
      listeners,
      addEventListener(type, handler) {
        listeners.set(type, handler);
      },
    };
  };
  const closeButton = makeButton();
  const saveButton = makeButton();
  const resetButton = makeButton();
  const addButton = makeButton();
  const overlayListeners = new Map();
  const rowInputs = {
    startMb: { value: "0" },
    endMb: { value: "10" },
    supportDsCtgLen: { value: "100000" },
  };
  const row = {
    querySelector(selector) {
      const match = selector.match(/data-support-ds-rule-field='([^']+)'/);
      return match ? rowInputs[match[1]] : null;
    },
  };
  const dialog = {
    dataset: {
      supportDsCtgLenRulesChrLength: "10000000",
      supportDsCtgLenRulesDeleteLabel: "删除",
      supportDsCtgLenRulesBaseline: JSON.stringify([
        { startMb: "0", endMb: "10", supportDsCtgLen: "100000" },
      ]),
      supportDsCtgLenRulesUnsavedMessage: "修改尚未保存，确定关闭并放弃修改吗？",
    },
    ownerDocument: {
      createElement() {
        return { dataset: {}, innerHTML: "" };
      },
    },
    querySelector(selector) {
      if (selector === "[data-support-ds-ctg-len-rules-close]") {
        return closeButton;
      }
      if (selector === "[data-support-ds-ctg-len-rules-save]") {
        return saveButton;
      }
      if (selector === "[data-support-ds-ctg-len-rules-reset]") {
        return resetButton;
      }
      if (selector === "[data-support-ds-ctg-len-rules-add]") {
        return addButton;
      }
      if (selector === "[data-support-ds-ctg-len-rules-body]") {
        return { appendChild() {} };
      }
      return null;
    },
    querySelectorAll(selector) {
      return selector === "[data-support-ds-ctg-len-rules-row]" ? [row] : [];
    },
    addEventListener() {},
  };
  const overlay = {
    addEventListener(type, handler) {
      overlayListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "[data-support-ds-ctg-len-rules-dialog]") {
        return dialog;
      }
      if (selector === "[data-support-ds-ctg-len-rules-overlay]") {
        return overlay;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const baseState = createState();
  const store = createStore({
    ...baseState,
    assembly: {
      ...baseState.assembly,
      selectedChrName: "Chr01",
      chromosomes: [{ chrName: "Chr01", chrLength: 10_000_000 }],
      supportDsCtgLenRulesDialogOpen: true,
      supportDsCtgLenRulesByChr: {},
      trackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
        supportDsCtgLen: 0,
      },
    },
  });
  let rerenderCount = 0;
  let persistCount = 0;
  const confirms = [];
  const deps = createBindingDeps({
    rerenderAssemblyMainTab() {
      rerenderCount += 1;
    },
    async persistMainTrackViewState() {
      persistCount += 1;
    },
    async requestAssemblyConfirm(_host, _store, message) {
      confirms.push(message);
      return confirms.length > 1;
    },
  });
  const originalConfirm = globalThis.confirm;
  globalThis.confirm = () => {
    throw new Error("native confirm should not be used");
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    assert.equal(overlayListeners.size, 0);

    rowInputs.supportDsCtgLen.value = "200000";
    await saveButton.listeners.get("click")?.({ preventDefault() {} });
    assert.equal(store.getState().assembly.supportDsCtgLenRulesDialogOpen, true);
    assert.equal(persistCount, 1);
    assert.equal(rerenderCount, 1);

    await resetButton.listeners.get("click")?.({ preventDefault() {} });
    assert.equal(store.getState().assembly.supportDsCtgLenRulesDialogOpen, true);
    assert.equal(persistCount, 2);
    assert.equal(rerenderCount, 2);

    rowInputs.supportDsCtgLen.value = "300000";
    await closeButton.listeners.get("click")?.({ preventDefault() {} });
    assert.equal(store.getState().assembly.supportDsCtgLenRulesDialogOpen, true);
    assert.deepEqual(confirms, ["修改尚未保存，确定关闭并放弃修改吗？"]);

    await closeButton.listeners.get("click")?.({ preventDefault() {} });
    assert.equal(store.getState().assembly.supportDsCtgLenRulesDialogOpen, false);
    assert.equal(confirms.length, 2);
  } finally {
    globalThis.confirm = originalConfirm;
  }
});

test("bindings keep project export jump chromosome when loading an empty assembly cache", () => {
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore({
    ...createState(),
    assembly: {
      ...createState().assembly,
      selectedChrName: "2",
      projectExportScrollToBottom: true,
    },
  });
  const calls = [];
  const deps = createBindingDeps({
    loadAssemblyView(_host, _store, options) {
      calls.push(options);
    },
  });

  bindAssemblyPageImpl(host, store, deps);

  assert.deepEqual(calls, [
    { keepCurrentChr: true, keepCurrentCtg: false },
  ]);
});

test("bindings close the chromosome picker after pointer leaves the picker area", () => {
  const listeners = new Map();
  const pickerArea = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const toggleButton = {
    disabled: false,
    addEventListener() {},
    closest(selector) {
      return selector === ".chr-picker-inline" ? pickerArea : null;
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "#assembly-chr-picker-toggle" ? toggleButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore({
    ...createState(),
    assembly: {
      ...createState().assembly,
      chrPickerOpen: true,
      chromosomes: [{ chrName: "1" }, { chrName: "2" }],
    },
  });
  let nextTimerId = 1;
  const timers = new Map();
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  globalThis.setTimeout = (callback, delayMs) => {
    const timerId = nextTimerId;
    nextTimerId += 1;
    timers.set(timerId, { callback, delayMs });
    return timerId;
  };
  globalThis.clearTimeout = (timerId) => {
    timers.delete(timerId);
  };
  let rerenderCount = 0;
  const deps = createBindingDeps({
    rerender() {
      rerenderCount += 1;
    },
  });

  try {
    bindAssemblyPageImpl(host, store, deps);
    assert.equal(typeof listeners.get("pointerleave"), "function");

    listeners.get("pointerleave")();

    assert.equal(timers.size, 1);
    const [timer] = Array.from(timers.values());
    assert.equal(timer.delayMs, 400);
    assert.equal(store.getState().assembly.chrPickerOpen, true);

    timer.callback();

    assert.equal(store.getState().assembly.chrPickerOpen, false);
    assert.equal(rerenderCount, 1);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test("bindings cancel chromosome picker auto-close when pointer re-enters the picker area", () => {
  const listeners = new Map();
  const pickerArea = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const toggleButton = {
    disabled: false,
    addEventListener() {},
    closest(selector) {
      return selector === ".chr-picker-inline" ? pickerArea : null;
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "#assembly-chr-picker-toggle" ? toggleButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore({
    ...createState(),
    assembly: {
      ...createState().assembly,
      chrPickerOpen: true,
      chromosomes: [{ chrName: "1" }, { chrName: "2" }],
    },
  });
  let nextTimerId = 1;
  const timers = new Map();
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  globalThis.setTimeout = (callback, delayMs) => {
    const timerId = nextTimerId;
    nextTimerId += 1;
    timers.set(timerId, { callback, delayMs });
    return timerId;
  };
  globalThis.clearTimeout = (timerId) => {
    timers.delete(timerId);
  };
  let rerenderCount = 0;
  const deps = createBindingDeps({
    rerender() {
      rerenderCount += 1;
    },
  });

  try {
    bindAssemblyPageImpl(host, store, deps);
    assert.equal(typeof listeners.get("pointerleave"), "function");
    assert.equal(typeof listeners.get("pointerenter"), "function");

    listeners.get("pointerleave")();
    assert.equal(timers.size, 1);

    listeners.get("pointerenter")();

    assert.equal(timers.size, 0);
    assert.equal(store.getState().assembly.chrPickerOpen, true);
    assert.equal(rerenderCount, 0);
  } finally {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
  }
});

test("bindings keep the final-path add button visible after appending a table row", async () => {
  const addListeners = new Map();
  let addButtonRect = {
    top: 960,
    bottom: 984,
    height: 24,
  };
  const addButton = {
    getBoundingClientRect() {
      return addButtonRect;
    },
    addEventListener(type, handler) {
      addListeners.set(type, handler);
    },
  };
  const finalPathList = {
    scrollTop: 0,
    clientHeight: 120,
    scrollHeight: 520,
  };
  const host = {
    querySelector(selector) {
      if (selector === "[data-final-path-card-list]") {
        return finalPathList;
      }
      if (selector === "[data-final-path-add-row]") {
        return addButton;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-add-row]") {
        return [addButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const deps = createBindingDeps({
    appendFinalPathRow: async () => {
      finalPathList.scrollHeight = 780;
      addButtonRect = {
        top: 1110,
        bottom: 1134,
        height: 24,
      };
    },
  });

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
    await addListeners.get("click")?.({
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(finalPathList.scrollTop, 780);
  assert.deepEqual(scrollCalls, [{ left: 0, top: 150, behavior: "auto" }]);
});

test("bindings wire final path graph drag alongside the existing table drag runtime", () => {
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
  let graphDragBound = 0;
  const deps = createBindingDeps({
    bindFinalPathGraphDrag() {
      graphDragBound += 1;
    },
  });

  bindAssemblyPageImpl(host, store, deps);

  assert.equal(graphDragBound, 1);
});

test("bindings wire final path export alongside the existing final path runtimes", () => {
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
  let exportBound = 0;
  const deps = createBindingDeps({
    bindFinalPathExport() {
      exportBound += 1;
    },
  });

  bindAssemblyPageImpl(host, store, deps);

  assert.equal(exportBound, 1);
});

test("bindings wire the band canvas runtime before subview tooltip bindings", () => {
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
  const calls = [];
  const deps = createBindingDeps({
    bindBandCanvasRuntime() {
      calls.push("canvas");
    },
    bindSubviewBandTooltips() {
      calls.push("tooltips");
    },
  });

  bindAssemblyPageImpl(host, store, deps);

  assert.deepEqual(calls.slice(0, 2), ["canvas", "tooltips"]);
});

test("track contig clicks preserve the current viewport when selecting ctg details", async () => {
  const listenerMap = new Map();
  const trackTarget = {
    dataset: {
      trackContigId: "30",
      trackRole: "support",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return [trackTarget];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const selectCalls = [];
  let suppressCount = 0;
  const deps = createBindingDeps({
    markNextTrackAutoFocusSuppressed() {
      suppressCount += 1;
    },
    resolveTrackContigClickAction() {
      return {
        type: "select-ctg",
        contigId: 30,
      };
    },
    async selectCtg(_host, _store, contigId, options) {
      selectCalls.push({ contigId, options });
    },
  });
  const prevented = [];

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("click")?.({
    ctrlKey: false,
    metaKey: false,
    preventDefault() {
      prevented.push(true);
    },
  });

  assert.deepEqual(selectCalls, [
    {
      contigId: 30,
      options: {
        preserveViewport: true,
      },
    },
  ]);
  assert.equal(suppressCount, 1);
  assert.equal(prevented.length, 1);
});

test("member chip clicks preserve the scrolled position of the members panel after rerender", async () => {
  const listenerMap = new Map();
  let currentRegion = {
    scrollTop: 184,
    scrollLeft: 12,
  };
  const chipButton = {
    dataset: {
      assemblyCtgId: "18",
      trackFocusMode: "start",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
    closest(selector) {
      if (selector === ".assembly-member-chip-region") {
        return currentRegion;
      }
      return null;
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-member-chip-region") {
        return currentRegion;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-assembly-ctg-id]") {
        return [chipButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const deps = createBindingDeps({
    normalizeTrackFocusMode(value) {
      return value;
    },
    async selectCtg() {
      currentRegion = {
        scrollTop: 0,
        scrollLeft: 0,
      };
    },
    updateDeletedCtgSelection() {},
  });

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("click")?.({
    ctrlKey: false,
    metaKey: false,
    preventDefault() {},
  });

  assert.equal(currentRegion.scrollTop, 184);
  assert.equal(currentRegion.scrollLeft, 12);
});

test("bindings toggle the members card collapsed state and persist it", async () => {
  const toggleListeners = new Map();
  const toggleButton = {
    addEventListener(type, handler) {
      toggleListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "[data-members-card-toggle='1']") {
        return toggleButton;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  let rerenderCount = 0;
  const persistCalls = [];
  const deps = createBindingDeps({
    rerender() {
      rerenderCount += 1;
    },
    persistMainTrackViewState: async (_host, currentStore) => {
      persistCalls.push({
        membersCardCollapsed: currentStore.getState().assembly.membersCardCollapsed,
      });
    },
  });

  bindAssemblyPageImpl(host, store, deps);
  await toggleListeners.get("click")?.({
    preventDefault() {},
  });

  assert.equal(store.getState().assembly.membersCardCollapsed, false);
  assert.equal(rerenderCount, 1);
  assert.deepEqual(persistCalls, [{ membersCardCollapsed: false }]);
});

test("typing main alignment length then entering subview-ctg commits the latest main-track value first", async () => {
  const alignmentInputListeners = new Map();
  const trackTargetListeners = new Map();
  const alignmentInput = {
    value: "100000",
    closest() {
      return null;
    },
    focus() {},
    addEventListener(type, handler) {
      alignmentInputListeners.set(type, handler);
    },
    setAttribute() {},
  };
  const trackTarget = {
    dataset: {
      trackRole: "primary",
      trackContigId: "2",
    },
    addEventListener(type, handler) {
      trackTargetListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-track-alignment-length") {
        return alignmentInput;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return [trackTarget];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore({
    ...createState(),
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      ...createState().assembly,
      supportDatasetId: 22,
      trackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
      ],
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "support-ctg", totalLength: 15000, anchorStart: 320 },
      ],
      subview: {
        mode: "2-contig",
        selectedAContigId: 30,
        selectedARole: "support",
        selectedBContigId: null,
        selectedBRole: "",
        message: "",
        error: "",
        summary: null,
      },
    },
  });
  let persistCalls = 0;
  const deps = createBindingDeps({
    resolveTrackContigClickAction() {
      return {
        type: "select-subview-candidate",
        trackRole: "primary",
        contigId: 2,
      };
    },
    handleTrackSubviewCandidateSelection(_host, currentStore) {
      const currentState = currentStore.getState();
      currentStore.setState({
        ...currentState,
        assembly: {
          ...currentState.assembly,
          subviewTrackView: {
            ...currentState.assembly.subviewTrackView,
            alignmentLength: currentState.assembly.trackView.alignmentLength,
          },
        },
      });
    },
    async persistMainTrackViewState() {
      persistCalls += 1;
    },
  });
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    alignmentInputListeners.get("blur")?.();
    await trackTargetListeners.get("click")?.({
      ctrlKey: true,
      metaKey: false,
      preventDefault() {},
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(store.getState().assembly.trackView.alignmentLength, 100000);
  assert.equal(store.getState().assembly.subviewTrackView.alignmentLength, 100000);
  assert.ok(persistCalls >= 1);
});

test("typing main alignment length then entering subview-track commits the latest main-track value first", async () => {
  const alignmentInputListeners = new Map();
  const trackLabelListeners = new Map();
  const alignmentInput = {
    value: "100000",
    closest() {
      return null;
    },
    focus() {},
    addEventListener(type, handler) {
      alignmentInputListeners.set(type, handler);
    },
    setAttribute() {},
  };
  const trackLabel = {
    dataset: {
      trackLabelRole: "primary",
      trackLabelSource: "mother",
      trackLabelDatasetId: "",
      trackLabelIsMirror: "0",
    },
    addEventListener(type, handler) {
      trackLabelListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-track-alignment-length") {
        return alignmentInput;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-track-label-role][data-track-label-selectable='1']") {
        return [trackLabel];
      }
      return [];
    },
    addEventListener() {},
  };
  const baseState = createState();
  const store = createStore({
    ...baseState,
    assembly: {
      ...baseState.assembly,
      trackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      subview: {
        ...baseState.assembly.subview,
        selectedTrackSelections: [
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        selectedTrackARole: "support",
        selectedTrackBRole: "",
        summary: null,
      },
    },
  });
  let persistCalls = 0;
  const deps = createBindingDeps({
    handleTrackSubviewTrackSelection(_host, currentStore, payload) {
      assert.equal(payload.trackRole, "primary");
      const currentState = currentStore.getState();
      currentStore.setState({
        ...currentState,
        assembly: {
          ...currentState.assembly,
          subviewTrackView: {
            ...currentState.assembly.subviewTrackView,
            alignmentLength: currentState.assembly.trackView.alignmentLength,
          },
        },
      });
    },
    async persistMainTrackViewState() {
      persistCalls += 1;
    },
  });
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    alignmentInputListeners.get("blur")?.();
    trackLabelListeners.get("click")?.({
      preventDefault() {},
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(store.getState().assembly.trackView.alignmentLength, 100000);
  assert.equal(store.getState().assembly.subviewTrackView.alignmentLength, 100000);
  assert.ok(persistCalls >= 1);
});

test("bindings route phased track labels into subview-track selection with phased identity", async () => {
  const trackLabelListeners = new Map();
  const trackLabel = {
    dataset: {
      trackLabelRole: "phased",
      trackLabelSource: "mother",
      trackLabelDatasetId: "0",
      trackLabelIsMirror: "0",
      trackLabelPhasedTrackId: "101",
      trackLabelPhasedHaplotypeKey: "A",
    },
    addEventListener(type, handler) {
      trackLabelListeners.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-track-label-role][data-track-label-selectable='1']") {
        return [trackLabel];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const calls = [];
  const deps = createBindingDeps({
    handleTrackSubviewTrackSelection(_host, _store, payload) {
      calls.push(payload);
    },
  });

  bindAssemblyPageImpl(host, store, deps);
  trackLabelListeners.get("click")?.({
    preventDefault() {},
  });

  assert.deepEqual(calls, [
    {
      trackRole: "phased",
      source: "mother",
      datasetId: "0",
      isMirror: false,
      phasedTrackId: "101",
      haplotypeKey: "A",
    },
  ]);
});

test("raising subview alignment length within cached pairwise coverage does not request a reload", async () => {
  const inputListeners = new Map();
  const subviewAlignmentInput = {
    value: "20000",
    closest() {
      return null;
    },
    focus() {},
    addEventListener(type, handler) {
      inputListeners.set(type, handler);
    },
    setAttribute() {},
  };
  const host = {
    querySelector(selector) {
      if (selector === "#subview-track-alignment-length") {
        return subviewAlignmentInput;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const baseState = createState();
  const store = createStore({
    ...baseState,
    assembly: {
      ...baseState.assembly,
      subviewTrackView: {
        ...baseState.assembly.subviewTrackView,
        alignmentLength: 10000,
      },
      subview: {
        ...baseState.assembly.subview,
        summary: {
          mode: "2-contig",
          top: { contigId: 30, role: "support" },
          bottom: { contigId: 2, role: "primary" },
        },
        pairwiseEvidence: {
          key: "2-contig:support:30:primary:2",
          status: "loaded",
          loadedMinAlignmentLength: 10000,
          loadedMinMapq: 0,
          hits: [{ alignLength: 12000, mapq: 40 }],
        },
      },
    },
  });
  let refreshCalls = 0;
  const deps = createBindingDeps({
    refreshSubviewPairwiseEvidence() {
      refreshCalls += 1;
    },
  });
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    inputListeners.get("blur")?.();
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(store.getState().assembly.subviewTrackView.alignmentLength, 20000);
  assert.equal(refreshCalls, 0);
});

test("lowering subview alignment length below cached pairwise coverage requests a reload", async () => {
  const inputListeners = new Map();
  const subviewAlignmentInput = {
    value: "5000",
    closest() {
      return null;
    },
    focus() {},
    addEventListener(type, handler) {
      inputListeners.set(type, handler);
    },
    setAttribute() {},
  };
  const host = {
    querySelector(selector) {
      if (selector === "#subview-track-alignment-length") {
        return subviewAlignmentInput;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const baseState = createState();
  const store = createStore({
    ...baseState,
    assembly: {
      ...baseState.assembly,
      subviewTrackView: {
        ...baseState.assembly.subviewTrackView,
        alignmentLength: 10000,
      },
      subview: {
        ...baseState.assembly.subview,
        summary: {
          mode: "2-contig",
          top: { contigId: 30, role: "support" },
          bottom: { contigId: 2, role: "primary" },
        },
        pairwiseEvidence: {
          key: "2-contig:support:30:primary:2",
          status: "loaded",
          loadedMinAlignmentLength: 10000,
          loadedMinMapq: 0,
          hits: [{ alignLength: 12000, mapq: 40 }],
        },
      },
    },
  });
  let refreshCalls = 0;
  const deps = createBindingDeps({
    refreshSubviewPairwiseEvidence() {
      refreshCalls += 1;
    },
  });
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    inputListeners.get("blur")?.();
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(store.getState().assembly.subviewTrackView.alignmentLength, 5000);
  assert.equal(refreshCalls, 1);
});

test("clicking the subview loading cancel button calls the cancel handler", async () => {
  const cancelListeners = new Map();
  const cancelButton = {
    addEventListener(type, handler) {
      cancelListeners.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-subview-pairwise-cancel='1']") {
        return [cancelButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  let cancelCalls = 0;
  const deps = createBindingDeps({
    cancelSubviewPairwiseEvidence() {
      cancelCalls += 1;
    },
  });

  bindAssemblyPageImpl(host, store, deps);
  await cancelListeners.get("click")?.({
    preventDefault() {},
  });

  assert.equal(cancelCalls, 1);
});

test("confirmation dialog confirm button passes prompt input value", async () => {
  const listeners = new Map();
  const confirmButton = {
    dataset: {
      assemblyConfirmAction: "confirm",
      assemblyConfirmId: "dialog-1",
    },
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const promptInput = {
    dataset: {
      assemblyConfirmInput: "dialog-1",
    },
    value: "100000",
  };
  const asNodeList = (nodes) => ({
    forEach(callback) {
      nodes.forEach(callback);
    },
    [Symbol.iterator]() {
      return nodes[Symbol.iterator]();
    },
  });
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-assembly-confirm-action][data-assembly-confirm-id]") {
        return asNodeList([confirmButton]);
      }
      if (selector === "[data-assembly-confirm-input]") {
        return asNodeList([promptInput]);
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const calls = [];
  const deps = createBindingDeps({
    resolveAssemblyConfirmDialog(_host, _store, payload) {
      calls.push(payload);
    },
  });

  bindAssemblyPageImpl(host, store, deps);
  await listeners.get("click")?.({
    preventDefault() {},
  });

  assert.deepEqual(calls, [
    {
      id: "dialog-1",
      confirmed: true,
      value: "100000",
    },
  ]);
});
