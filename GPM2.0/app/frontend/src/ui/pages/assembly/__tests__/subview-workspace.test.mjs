import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { installSubviewWorkspace, startSubviewWindowDraft, getSubviewWindowStore, changeSubviewWindow } from "../subview-workspace-state.js";
import { renderSubviewEmptyGuide } from "../render-subview-workspace.js";
import { constrainLocalViewPosition } from "../subview-workspace-runtime.js";
import { createSubviewPairwiseController } from "../subview-pairwise-controller.js";
import { createSubviewSelectionController } from "../subview-selection-controller.js";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";

const summary = (left, right) => ({ mode: "2-contig",
  top: { role: "primary", contigId: left }, bottom: { role: "primary", contigId: right } });
function fixture() {
  const state = createState();
  state.activeRoute = "assembly";
  state.locale = "en";
  const store = createStore(state);
  installSubviewWorkspace(store);
  return store;
}
function enter(store, value) {
  store.setState({ assembly: { ...startSubviewWindowDraft(store.getState().assembly),
    subview: { summary: value }, subviewTrackView: { fullRange: true, alignmentLength: 1 } } });
  return store.getState().assembly.subviewWorkspace.activeId;
}

test("idle Local View is guidance only, with the inline Tools entry in both languages", () => {
  for (const locale of ["en", "zh"]) {
    const state = createState(); state.locale = locale;
    const html = renderAssemblyPage(state);
    const panel = html.match(/<article class="subview-selection-panel"[^]*?<\/article>/)[0];
    assert.doesNotMatch(panel, /assembly-view-title|subview-panel-head|subview-tools-toggle"/);
    assert.match(panel, /class="subview-guide-tools" data-subview-tools-toggle="1"/);
    assert.match(panel, /data-app-tooltip-overflow/);
  }
});

test("windows retain independent edits, history and viewport while sharing live Main data", () => {
  const store = fixture();
  const a = enter(store, summary(2, 5));
  const scopedA = getSubviewWindowStore(store, a);
  const snapshot = { ...scopedA.getState().assembly,
    subviewTrackScrollState: { viewportKey: "A", scrollLeft: 320 },
    subviewHistoryByKey: { pair: { past: [1] } }, subviewTrackDragOffsets: [{ offsetBp: 80 }] };
  scopedA.setState({ assembly: snapshot });
  const b = enter(store, summary(5, 8));
  const scopedB = getSubviewWindowStore(store, b);
  scopedA.setState({ assembly: { ...scopedA.getState().assembly, subviewTrackView: { alignmentLength: 50 } } });
  assert.equal(store.getState().assembly.subview.summary.bottom.contigId, 8);
  assert.equal(scopedB.getState().assembly.subviewTrackView.alignmentLength, 1);
  assert.equal(scopedA.getState().assembly.subviewTrackView.alignmentLength, 50);
  changeSubviewWindow(store, a, "activate");
  assert.equal(store.getState().assembly.subviewTrackScrollState.scrollLeft, 320);
  assert.deepEqual(store.getState().assembly.subviewTrackDragOffsets, [{ offsetBp: 80 }]);
  assert.deepEqual(store.getState().assembly.subviewHistoryByKey, { pair: { past: [1] } });
  const main = [...store.getState().assembly.chrCtgs];
  store.setState({ assembly: { ...store.getState().assembly, chrCtgs: main } });
  assert.equal(scopedA.getState().assembly.chrCtgs, main);
  assert.equal(scopedB.getState().assembly.chrCtgs, main);
});

test("minimize and dock preserve the comparison; close drops only the window", () => {
  const store = fixture(); const a = enter(store, summary(2, 5));
  const scoped = getSubviewWindowStore(store, a);
  const snapshot = store.getState().assembly.subview;
  const main = store.getState().assembly.chrCtgs;
  const history = { persisted: { past: ["keep"] } };
  scoped.setState({ assembly: { ...scoped.getState().assembly, subviewHistoryByKey: history } });
  changeSubviewWindow(store, a, "minimize");
  assert.equal(store.getState().assembly.subviewWorkspace.windows[0].minimized, true);
  changeSubviewWindow(store, a, "dock");
  assert.equal(store.getState().assembly.subviewWorkspace.windows[0].floating, false);
  changeSubviewWindow(store, a, "activate");
  assert.equal(store.getState().assembly.subviewWorkspace.windows[0].minimized, false);
  assert.equal(store.getState().assembly.subview, snapshot);
  changeSubviewWindow(store, a, "close");
  assert.equal(store.getState().assembly.subviewWorkspace.windows.length, 0);
  assert.equal(store.getState().assembly.chrCtgs, main);
  assert.equal(store.getState().assembly.subviewHistoryByKey, history);
  scoped.setState({ assembly: { ...scoped.getState().assembly, subview: { summary: summary(8, 9) } } });
  assert.equal(store.getState().assembly.subviewWorkspace.windows.length, 0);
});

test("closed non-active windows and scope ABA cannot receive late writes", () => {
  const store = fixture(); const a = enter(store, summary(2, 5));
  const scoped = getSubviewWindowStore(store, a);
  enter(store, summary(5, 8));
  scoped.setState({ assembly: { ...scoped.getState().assembly, subview: null } });
  assert.equal(store.getState().assembly.subviewWorkspace.windows.length, 1);
  const b = store.getState().assembly.subviewWorkspace.activeId;
  const scopedB = getSubviewWindowStore(store, b);
  for (const selectedChrName of ["Chr02", "Chr01"]) store.setState({ assembly: {
    ...store.getState().assembly, selectedChrName, subview: null } });
  scopedB.setState({ assembly: { ...scopedB.getState().assembly, subview: { summary: summary(1, 2) } } });
  assert.equal(store.getState().assembly.subviewWorkspace.windows.length, 0);
});

test("late pairwise results update the originating window, not the current comparison", async () => {
  const store = fixture();
  let resolve;
  const controller = createSubviewPairwiseController({ session: { subviewPairwiseEvidenceRequestSeq: 0 },
    rerenderSubviewPanel() {}, scheduleDeferredSubviewPanelRerender() {},
    getJunctionInspection: () => new Promise(done => { resolve = done; }) });
  const a = enter(store, summary(2, 5));
  const state = store.getState();
  store.setState({ assembly: { ...state.assembly, subview: { ...state.assembly.subview,
    pairwiseEvidence: controller.buildInitialSubviewPairwiseEvidence(state.assembly.subview.summary,
      state.assembly.subviewTrackView, null, state) } } });
  const loading = controller.loadSubviewPairwiseEvidence({}, store, state.assembly.subview.summary);
  assert.equal(typeof resolve, "function");
  const b = enter(store, summary(5, 8));
  changeSubviewWindow(store, a, "minimize");
  resolve({ hits: [{ id: "owned-by-a" }] });
  await loading;
  assert.equal(getSubviewWindowStore(store, a).getState().assembly.subview.pairwiseEvidence.hits[0].id, "owned-by-a");
  assert.equal(getSubviewWindowStore(store, b).getState().assembly.subview.pairwiseEvidence, undefined);
  assert.equal(store.getState().assembly.subview.summary.bottom.contigId, 8);
});

test("quick entry starts a new task instead of clearing the first comparison", () => {
  const store = fixture(); const a = enter(store, summary(2, 5));
  const controller = createSubviewSelectionController({
    getCurrentProject: () => ({ primaryDatasetId: 1 }),
    invalidateSubviewPairwiseEvidence() {}, resetSubviewTransientState() {},
    rerenderAssemblyMainTab() {}, rerenderSubviewPanel() {},
    buildInitialSubviewPairwiseEvidence: () => null,
    loadSubviewPairwiseEvidence() {},
  });
  controller.handleTrackSubviewCandidateSelection({}, store, { trackRole: "primary", contigId: 5 });
  controller.handleTrackSubviewCandidateSelection({}, store, { trackRole: "primary", contigId: 8 });
  assert.equal(store.getState().assembly.subviewWorkspace.windows.length, 2);
  assert.equal(getSubviewWindowStore(store, a).getState().assembly.subview.summary.top.contigId, 2);
});

test("workspace markup contains a task and independent window controls for every comparison", () => {
  const store = fixture(); const a = enter(store, summary(2, 5)); enter(store, summary(5, 8));
  changeSubviewWindow(store, a, "minimize");
  const html = renderAssemblyPage(store.getState());
  assert.equal((html.match(/data-subview-task=/g) || []).length, 2);
  assert.equal((html.match(/data-local-view-window=/g) || []).length, 2);
  assert.match(html, /class="subview-window is-floating" hidden/);
  assert.equal((html.match(/data-local-view-action="dock"/g) || []).length, 2);
  assert.doesNotMatch(html, /subview-empty-guide/);
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(ids.length, new Set(ids).size, "global control IDs cannot target a different window");
});

test("window drag bounds keep controls reachable, including small viewports", () => {
  assert.deepEqual(constrainLocalViewPosition(-20, 800, 600, 400, 1000, 700), { x: 0, y: 300 });
  assert.deepEqual(constrainLocalViewPosition(80, 100, 1000, 800, 320, 240), { x: 0, y: 0 });
});

test("guide escapes text and window state is not added to persisted Local View fields", () => {
  const html = renderSubviewEmptyGuide({ guide: "<Tools> & text", tools: { toggle: "Tools" } });
  assert.match(html, /&lt;<button/); assert.match(html, /&amp; text/);
  const store = fixture(); enter(store, summary(2, 5));
  assert.equal(store.getState().assembly.subview.subviewWorkspace, undefined);
});


test("workspace installation can recover after a project replaces the Assembly state", () => {
  const store = fixture();
  enter(store, summary(2, 5));
  const old = getSubviewWindowStore(store);
  store.setState({ assembly: { selectedChrName: "Chr02" }, session: { projectId: 8 } });
  assert.equal(old.isLocalViewAlive(), false);
  assert.equal(installSubviewWorkspace(store), true);
  assert.equal(installSubviewWorkspace(store), false);
  enter(store, summary(3, 9));
  assert.equal(store.getState().assembly.subviewWorkspace.windows.length, 1);
  assert.equal(old.isLocalViewAlive(), false);
});


test("new comparisons open above windows that have already been raised many times", () => {
  const store = fixture(); const a = enter(store, summary(2, 5));
  for (let i = 0; i < 8; i++) changeSubviewWindow(store, a, "activate");
  const b = enter(store, summary(5, 8));
  const windows = store.getState().assembly.subviewWorkspace.windows;
  assert.ok(windows.find(item => item.id === b).z > windows.find(item => item.id === a).z);
});
