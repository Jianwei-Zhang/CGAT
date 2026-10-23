import { createState } from "./tabs-semantics-harness.mjs";
import test from "node:test";
import assert from "node:assert/strict";

import { FLOATING_MENU_CLOSE_DELAY_MS } from "../../floating-menu-runtime.js";
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
    moveContextSubviewMemberToOtherLane() {},
    removeContextSubviewMember() {},
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

test("submenus close after the shared delay and reentry cancels dismissal", () => {
  const handlers = new Map(), classes = new Set(), timers = new Map();
  const trigger = { setAttribute() {}, addEventListener() {} };
  const submenu = { style: {}, getBoundingClientRect: () => ({ width: 180, height: 100 }) };
  const group = {
    classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: () => false },
    addEventListener(type, handler) { const list = handlers.get(type) || []; list.push(handler); handlers.set(type, list); },
    querySelector: selector => selector === "[data-context-submenu]" ? submenu : trigger,
    contains: node => node === submenu || node === trigger,
    getBoundingClientRect: () => ({ left: 100, right: 260, top: 120, bottom: 148 }),
  };
  let id = 0;
  const cleanup = bindContextSubmenuInteractions({ querySelectorAll: () => [group] }, {
    setTimeout(callback, delay) { timers.set(++id, { callback, delay }); return id; },
    clearTimeout: timer => timers.delete(timer),
  });
  const fire = (type, relatedTarget = null) => handlers.get(type)?.forEach(handler => handler({ relatedTarget }));
  fire("pointerenter"); assert.equal(classes.has("is-open"), true);
  fire("pointerleave", submenu); assert.equal(timers.size, 0);
  fire("pointerleave"); assert.equal(classes.has("is-open"), true);
  assert.equal([...timers.values()][0].delay, FLOATING_MENU_CLOSE_DELAY_MS);
  fire("pointerenter"); assert.equal(timers.size, 0);
  fire("pointerleave");
  const callback = [...timers.values()][0].callback; timers.clear(); callback();
  assert.equal(classes.has("is-open"), false);
  fire("pointerenter"); fire("pointerleave"); cleanup(); assert.equal(timers.size, 0);
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

  assert.match(menuState.innerHTML, /加入 Final Path/);
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

  assert.match(menuState.innerHTML, /加入 Final Path/);
  assert.match(menuState.innerHTML, /翻转 contig/);
  assert.match(menuState.innerHTML, /删除 contig/);
  assert.doesNotMatch(menuState.innerHTML, /进入 Ctg30 菜单/);
});


test("assembly context menu closes after 400ms, cancels on return, and clears stale close timers", () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  const handlers = new Map(), classes = new Set(), timers = new Map();
  let id = 0;
  const child = { closest: selector => selector === "#assembly-context-menu" ? menu : null };
  const menu = { innerHTML: "contents", contains: node => node === child,
    classList: { add: name => classes.add(name) },
  };
  const host = { querySelector: () => menu,
    addEventListener(type, handler) { handlers.set(type, handler); } };
  try {
    globalThis.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
    globalThis.clearTimeout = timer => timers.delete(timer);
    bindAssemblyContextMenu(host, { getState: () => ({ assembly: { activeTab: "assembly" } }) }, createRuntimeDeps());
    handlers.get("pointerout")({ target: child, relatedTarget: child }); assert.equal(timers.size, 0);
    handlers.get("pointerout")({ target: child, relatedTarget: null });
    assert.equal([...timers.values()][0].delay, 400); assert.equal(menu.innerHTML, "contents");
    handlers.get("pointerover")({ target: child }); assert.equal(timers.size, 0);
    handlers.get("pointerout")({ target: child, relatedTarget: null });
    const callback = [...timers.values()][0].callback; timers.clear(); callback();
    assert.equal(menu.innerHTML, ""); assert.equal(classes.has("is-hidden"), true);
    handlers.get("pointerout")({ target: child, relatedTarget: null });
    handlers.get("keydown")({ key: "Escape" });
    assert.equal(timers.size, 0);
  } finally { globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
});

test("anchor submenu hover/focus previews clean up on leave, blur, Escape, scroll and commit", async (t) => {
  const handlers=new Map(),groups=[],calls=[];let buttons=[];
  const doc={createElementNS:(_ns,tag)=>({tag,attrs:{},children:[],setAttribute(k,v){this.attrs[k]=v;},append(n){this.children.push(n);},remove(){this.removed=true;}})};
  const band={ownerDocument:doc,ownerSVGElement:{append:n=>groups.push(n)},getAttribute:key=>({
    "data-band-query-start":101,"data-band-query-end":300,"data-band-ref-start":201,"data-band-ref-end":400,
    "data-band-left-anchor":"20,90 200,24","data-band-right-anchor":"100,90 250,24"})[key]};
  const menu={classList:{add(){},remove(){}},style:{},getBoundingClientRect:()=>({width:220,height:180}),
    set innerHTML(html){this.markup=html;buttons=[...html.matchAll(/data-menu-action-path="([^"]+)"[^>]*>([^<]*)/g)].map((m)=>({
      label:m[2],handlers:new Map(),getAttribute:()=>m[1],addEventListener(type,fn){this.handlers.set(type,fn);}}));},
    get innerHTML(){return this.markup;},querySelectorAll:selector=>selector==="[data-menu-action-path]"?buttons:[]};
  const host={querySelector:s=>s==="#assembly-context-menu"?menu:null,querySelectorAll:()=>[band],addEventListener:(type,fn)=>handlers.set(type,fn)};
  const state=createState({assembly:{activeTab:"assembly",selectedChrName:"Chr01",trackSelectedCtgIds:[],trackView:{alignmentLength:1},
    chrCtgs:[{assemblyCtgId:2,totalLength:1000,hits:[{queryStart:101,queryEnd:300,refStart:201,refEnd:400,strand:"+",blockLength:200,identityPct:99}]}]}});
  const store={getState:()=>state};
  const track={getAttribute:key=>({"data-track-contig-id":"2","data-track-role":"primary"})[key]??null};
  const target={closest:s=>s==="[data-track-contig-id][data-track-role]"?track:null};
  const original=globalThis.window;globalThis.window={innerWidth:1200,innerHeight:800};t.after(()=>{globalThis.window=original;});
  bindAssemblyContextMenu(host,store,createRuntimeDeps({splitContigAtAnchor:async(_h,_s,anchor)=>calls.push(anchor),openManualContigSplit(){}}));
  const open=()=>{handlers.get("contextmenu")({target,clientX:80,clientY:90,preventDefault(){}});return buttons.find(b=>b.label.includes("锚点 1"));};
  let button=open();assert.ok(button);
  const fire=(name)=>button.handlers.get(name)?.({stopPropagation(){}});
  fire("pointerenter");assert.equal(groups.filter(g=>!g.removed).length,1);
  fire("pointerleave");assert.equal(groups.filter(g=>!g.removed).length,0);
  fire("focus");fire("blur");assert.equal(groups.filter(g=>!g.removed).length,0);
  fire("pointerenter");handlers.get("keydown")({key:"Escape"});assert.equal(groups.filter(g=>!g.removed).length,0);
  button=open();fire("focus");handlers.get("scroll")();assert.equal(groups.filter(g=>!g.removed).length,0);
  button=open();fire("pointerenter");await fire("click");assert.equal(groups.filter(g=>!g.removed).length,0);
  assert.deepEqual(calls.map(c=>c.cutAfter),[100]);
});
