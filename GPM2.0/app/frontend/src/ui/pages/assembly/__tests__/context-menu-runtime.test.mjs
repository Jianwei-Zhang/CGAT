import test from "node:test";
import assert from "node:assert/strict";

import {
  bindAssemblyContextMenu,
  bindContextSubmenuInteractions,
  buildAssemblyContextMenuActions,
  positionContextSubmenuWithinViewport,
  renderContextMenuItems,
} from "../context-menu-runtime.js";

function createStubActions() {
  return {
    enterSubviewFromTrackSelections() {},
    enterSubviewFromCandidates() {},
    setSubviewTrackPairCtgHidden() {},
    toggleSubviewContigFlip() {},
    deleteSelectedSubviewTrackPairCtgs() {},
    clearSubviewTrackPairHiddenCtgs() {},
    setSelectedPrimaryTrackCtgsHidden() {},
    deleteSelectedTrackCtgs() {},
    runBatchDeleteTrackCtgs() {},
    restoreSelectedDeletedCtgs() {},
    canEditTrackCtg() {
      return true;
    },
    addFinalPathContigRelativeToSegment() {},
    addFinalPathGapRelativeToSegment() {},
    deleteFinalPathSegment() {},
    flipFinalPathSegment() {},
    openDegapSettings() {},
    requestDegapGapJob() {},
    requestDegapTelseekerJob() {},
    appendTrackContigToFinalPath() {},
    toggleSubviewAnchorEdge() {},
    openAssemblyContextMenuAt() {},
    toggleSupportTrackCtgMirror() {},
    togglePrimaryTrackCtgHidden() {},
    copySubviewAnchorWithOffset() {},
    deleteSubviewManualAnchor() {},
    addTrackContigToPhasedTrack() {},
    removePhasedTrackItem() {},
    deletePhasedTrack() {},
    importAddCtgIntoTrack() {},
    setActiveHitsTrack() {},
    setAssemblyActionFeedback() {},
    applyEditorAction() {},
    promptForRenameCtg() {},
    promptForDeleteShorterThanLength() {},
    buildRenameCtgActionArgs() {},
    rerender() {},
  };
}

function createRuntimeDeps(overrides = {}) {
  return {
    ...createStubActions(),
    escapeAttr(value) {
      return String(value ?? "");
    },
    escapeHtml(value) {
      return String(value ?? "");
    },
    updateDeletedCtgSelection() {},
    updateTrackSelection() {},
    ...overrides,
  };
}

test("buildAssemblyContextMenuActions merges required handlers and runtime overrides", () => {
  const baseActions = createStubActions();
  const overrideConfirm = () => false;
  const overrideRerender = () => "rerendered";
  const actions = buildAssemblyContextMenuActions(baseActions, {
    confirm: overrideConfirm,
    rerender: overrideRerender,
  });

  assert.equal(actions.confirm, overrideConfirm);
  assert.equal(actions.rerender, overrideRerender);
  assert.equal(actions.enterSubviewFromTrackSelections, baseActions.enterSubviewFromTrackSelections);
  assert.equal(typeof actions.deleteSelectedTrackCtgs, "function");
});

test("renderContextMenuItems renders nested items while preserving flat action indexes", () => {
  const html = renderContextMenuItems([
    { label: "Delete", run() {} },
    {
      label: "Add Gap",
      children: [
        { label: "Add Gap Left", run() {} },
        { label: "Add Gap Right", run() {} },
      ],
    },
  ], createRuntimeDeps());

  assert.match(html, /data-menu-action-index="0"/);
  assert.match(html, /data-menu-action-path="0"/);
  assert.match(html, /class="context-menu-submenu-group"/);
  assert.match(html, /aria-haspopup="menu"/);
  assert.match(html, /data-menu-action-path="1\.0"/);
  assert.match(html, /data-menu-action-path="1\.1"/);
});

test("positionContextSubmenuWithinViewport opens a submenu left near the right edge", () => {
  const classSet = new Set();
  const submenu = {
    classList: {
      toggle(name, active) {
        if (active) classSet.add(name);
        else classSet.delete(name);
      },
    },
    style: {},
    getBoundingClientRect() {
      return { width: 180, height: 100 };
    },
  };
  const group = {
    getBoundingClientRect() {
      return { left: 1020, right: 1180, top: 120, bottom: 148 };
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = { innerWidth: 1200, innerHeight: 800 };

  try {
    positionContextSubmenuWithinViewport(group, submenu);
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(classSet.has("opens-left"), true);
});

test("bindContextSubmenuInteractions keeps a submenu open until its wrapper is left", () => {
  const listenerMap = new Map();
  const classSet = new Set();
  const submenu = {
    classList: { toggle() {} },
    style: {},
    getBoundingClientRect() {
      return { width: 180, height: 100 };
    },
  };
  const group = {
    classList: {
      add(name) {
        classSet.add(name);
      },
      remove(name) {
        classSet.delete(name);
      },
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
    querySelector() {
      return submenu;
    },
    getBoundingClientRect() {
      return { left: 100, right: 260, top: 120, bottom: 148 };
    },
  };
  const menu = {
    querySelectorAll(selector) {
      return selector === "[data-context-submenu-group]" ? [group] : [];
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = { innerWidth: 1200, innerHeight: 800 };

  try {
    bindContextSubmenuInteractions(menu);
    listenerMap.get("pointerenter")?.();
    assert.equal(classSet.has("is-open"), true);
    listenerMap.get("pointerleave")?.();
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(classSet.has("is-open"), false);
});

test("bindAssemblyContextMenu clamps the menu inside the viewport bottom edge", () => {
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
    getBoundingClientRect() {
      return {
        width: 220,
        height: 180,
      };
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
  const store = {
    getState() {
      return {
        locale: "zh",
        assembly: {
          activeTab: "assembly",
          trackSelectedCtgIds: [],
          selectedDeletedCtgRecordIds: [],
          hiddenPrimaryCtgIds: [],
          supportMirroredCtgs: [],
          supportDatasetId: null,
          subview: {
            summary: null,
            trackPairHiddenCtgs: [],
            trackPairSelectedCtgs: [],
          },
        },
      };
    },
  };
  const target = {
    closest(selector) {
      if (selector === ".final-path-card[data-final-path-view-mode='graph']") {
        return {};
      }
      if (selector === "[data-final-path-segment-id][data-final-path-segment-type]") {
        return {
          getAttribute(name) {
            if (name === "data-final-path-segment-id") return "seg-1";
            if (name === "data-final-path-segment-type") return "ctg";
            return null;
          },
        };
      }
      return null;
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = {
    innerWidth: 1200,
    innerHeight: 800,
    confirm() {
      return true;
    },
  };

  try {
    bindAssemblyContextMenu(host, store, createRuntimeDeps());
    listenerMap.get("contextmenu")?.({
      target,
      clientX: 40,
      clientY: 760,
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(menuState.style.left, "40px");
  assert.equal(menuState.style.top, "612px");
});

test("bindAssemblyContextMenu dispatches a nested Final Path action by menu path", async () => {
  const listenerMap = new Map();
  const calls = [];
  let childClick = null;
  const childButton = {
    addEventListener(type, handler) {
      if (type === "click") childClick = handler;
    },
    getAttribute(name) {
      return name === "data-menu-action-path" ? "3.1" : null;
    },
  };
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll(selector) {
      if (selector === "[data-menu-action-path]") return [childButton];
      return [];
    },
    getBoundingClientRect() {
      return { width: 220, height: 180 };
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "#assembly-context-menu" ? menuState : null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = {
    getState() {
      return {
        locale: "zh",
        assembly: {
          activeTab: "assembly",
          trackSelectedCtgIds: [],
          selectedDeletedCtgRecordIds: [],
          hiddenPrimaryCtgIds: [],
          supportMirroredCtgs: [],
          supportDatasetId: null,
          subview: {
            summary: null,
            trackPairHiddenCtgs: [],
            trackPairSelectedCtgs: [],
          },
        },
      };
    },
  };
  const target = {
    closest(selector) {
      if (selector === ".final-path-card[data-final-path-view-mode='graph']") return {};
      if (selector === "[data-final-path-segment-id][data-final-path-segment-type]") {
        return {
          getAttribute(name) {
            if (name === "data-final-path-segment-id") return "seg-1";
            if (name === "data-final-path-segment-type") return "ctg";
            return null;
          },
        };
      }
      return null;
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = { innerWidth: 1200, innerHeight: 800 };

  try {
    bindAssemblyContextMenu(host, store, createRuntimeDeps({
      addFinalPathContigRelativeToSegment(...args) {
        calls.push(args);
      },
    }));
    listenerMap.get("contextmenu")?.({
      target,
      clientX: 80,
      clientY: 90,
      preventDefault() {},
    });
    await childClick?.({ stopPropagation() {} });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.deepEqual(calls, [[host, store, { segmentId: "seg-1", placement: "after" }]]);
});

test("bindAssemblyContextMenu renders fragment menu entries for subview fragment targets", () => {
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
    getBoundingClientRect() {
      return {
        width: 220,
        height: 120,
      };
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
  const store = {
    getState() {
      return {
        locale: "zh",
        assembly: {
          activeTab: "assembly",
          trackSelectedCtgIds: [],
          selectedDeletedCtgRecordIds: [],
          hiddenPrimaryCtgIds: [],
          supportMirroredCtgs: [],
          supportDatasetId: 22,
          subview: {
            summary: {
              mode: "2-contig",
            },
            trackPairHiddenCtgs: [],
            trackPairSelectedCtgs: [],
          },
        },
      };
    },
  };
  const target = {
    closest(selector) {
      if (selector === "[data-subview-fragment-key][data-subview-fragment-contig-id]") {
        return {
          getAttribute(name) {
            if (name === "data-subview-fragment-key") return "8:1-500";
            if (name === "data-subview-fragment-contig-id") return "8";
            if (name === "data-subview-fragment-role") return "primary";
            if (name === "data-subview-fragment-start") return "1";
            if (name === "data-subview-fragment-end") return "500";
            if (name === "data-subview-fragment-ctg-name") return "Ctg8";
            if (name === "data-subview-fragment-dataset-id") return "11";
            if (name === "data-subview-fragment-is-mirror") return "0";
            return null;
          },
        };
      }
      return null;
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = {
    innerWidth: 1200,
    innerHeight: 800,
    confirm() {
      return true;
    },
  };

  try {
    bindAssemblyContextMenu(host, store, createRuntimeDeps());
    listenerMap.get("contextmenu")?.({
      target,
      clientX: 80,
      clientY: 90,
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.match(menuState.innerHTML, /Append to path/);
  assert.match(menuState.innerHTML, /翻转 contig/);
  assert.doesNotMatch(menuState.innerHTML, /进入 Ctg8 菜单/);
});

test("bindAssemblyContextMenu keeps fragment outline active while its menu stays open", () => {
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
    getBoundingClientRect() {
      return { width: 220, height: 120 };
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
  const store = {
    getState() {
      return {
        locale: "zh",
        assembly: {
          activeTab: "assembly",
          trackSelectedCtgIds: [],
          selectedDeletedCtgRecordIds: [],
          hiddenPrimaryCtgIds: [],
          supportMirroredCtgs: [],
          supportDatasetId: 22,
          subview: {
            summary: { mode: "2-contig" },
            trackPairHiddenCtgs: [],
            trackPairSelectedCtgs: [],
          },
        },
      };
    },
  };
  const classSet = new Set();
  const fragmentNode = {
    classList: {
      add(name) {
        classSet.add(name);
      },
      remove(name) {
        classSet.delete(name);
      },
    },
    getAttribute(name) {
      if (name === "data-subview-fragment-key") return "8:1-500";
      if (name === "data-subview-fragment-contig-id") return "8";
      if (name === "data-subview-fragment-slot") return "bottom";
      if (name === "data-subview-fragment-role") return "primary";
      if (name === "data-subview-fragment-start") return "1";
      if (name === "data-subview-fragment-end") return "500";
      if (name === "data-subview-fragment-ctg-name") return "Ctg8";
      if (name === "data-subview-fragment-dataset-id") return "11";
      if (name === "data-subview-fragment-is-mirror") return "0";
      if (name === "data-subview-fragment-ref-orient") return "+";
      return null;
    },
  };
  const target = {
    closest(selector) {
      if (selector === "[data-subview-fragment-key][data-subview-fragment-contig-id]") {
        return fragmentNode;
      }
      return null;
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = {
    innerWidth: 1200,
    innerHeight: 800,
    confirm() {
      return true;
    },
  };

  try {
    bindAssemblyContextMenu(host, store, createRuntimeDeps());
    listenerMap.get("contextmenu")?.({
      target,
      clientX: 80,
      clientY: 90,
      preventDefault() {},
    });
    assert.equal(classSet.has("is-menu-active"), true);
    listenerMap.get("click")?.({});
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(classSet.has("is-menu-active"), false);
});

test("bindAssemblyContextMenu renders track-pair fragment local actions", () => {
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
    getBoundingClientRect() {
      return {
        width: 220,
        height: 120,
      };
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
  const store = {
    getState() {
      return {
        locale: "zh",
        assembly: {
          activeTab: "assembly",
          trackSelectedCtgIds: [],
          selectedDeletedCtgRecordIds: [],
          hiddenPrimaryCtgIds: [],
          supportMirroredCtgs: [],
          supportDatasetId: 22,
          subview: {
            summary: {
              mode: "track-pair",
            },
            trackPairHiddenCtgs: [],
            trackPairSelectedCtgs: [],
          },
        },
      };
    },
  };
  const target = {
    closest(selector) {
      if (selector === "[data-subview-fragment-key][data-subview-fragment-contig-id]") {
        return {
          getAttribute(name) {
            if (name === "data-subview-fragment-key") return "30:1-500";
            if (name === "data-subview-fragment-contig-id") return "30";
            if (name === "data-subview-fragment-role") return "support";
            if (name === "data-subview-fragment-start") return "1";
            if (name === "data-subview-fragment-end") return "500";
            if (name === "data-subview-fragment-ctg-name") return "Ctg30";
            if (name === "data-subview-fragment-dataset-id") return "22";
            if (name === "data-subview-fragment-is-mirror") return "0";
            return null;
          },
        };
      }
      return null;
    },
  };
  const originalWindow = globalThis.window;
  globalThis.window = {
    innerWidth: 1200,
    innerHeight: 800,
    confirm() {
      return true;
    },
  };

  try {
    bindAssemblyContextMenu(host, store, createRuntimeDeps());
    listenerMap.get("contextmenu")?.({
      target,
      clientX: 80,
      clientY: 90,
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.match(menuState.innerHTML, /Append to path/);
  assert.match(menuState.innerHTML, /翻转 contig/);
  assert.match(menuState.innerHTML, /在Subview中删除 contig（仅当前视图）/);
  assert.doesNotMatch(menuState.innerHTML, /进入 Ctg30 菜单/);
});
