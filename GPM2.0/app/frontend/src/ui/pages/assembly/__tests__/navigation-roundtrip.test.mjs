import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { createState } from "./tabs-semantics-harness.mjs";
import { installSubviewWorkspace, startSubviewWindowDraft, getSubviewWindowStore, changeSubviewWindow } from "../subview-workspace-state.js";
import { createAssemblyConfirmController, cancelAssemblyConfirmDialog } from "../confirm-controller.js";
import { createSubviewInteractionController } from "../subview-interaction-controller.js";
import { createOffsetSubviewManualAnchor } from "../subview-anchor-state.js";
import { getAssemblyI18n, tAssembly } from "../i18n.js";
import { createSubviewPairwiseController } from "../subview-pairwise-controller.js";
import { selectChromosome } from "../assembly-data-runtime.js";

const summary = (a, b) => ({ mode: "2-contig", top: { role: "primary", contigId: a }, bottom: { role: "support", contigId: b, datasetId: 22 } });
const edge = { hitKey: "hit-1", edge: "left", topEndpointKey: "top", bottomEndpointKey: "bottom",
  topContigId: 2, bottomContigId: 30, topCutBp: 100, bottomCutBp: 200, topLengthBp: 1000, bottomLengthBp: 1000 };
function fixture() {
  const store = createStore({ ...createState(), activeRoute: "assembly" });
  installSubviewWorkspace(store);
  store.setState({ assembly: { ...store.getState().assembly, subview: { summary: summary(2, 30), activeAnchors: [{ hitKey: "hit-1", edge: "left" }] } } });
  const id = store.getState().assembly.subviewWorkspace.activeId;
  return { store, id, scoped: getSubviewWindowStore(store, id) };
}

test("offset-anchor prompt paints immediately from a real scoped store without rebuilding its graph", async () => {
  const f = fixture(); let dialogs = 0, graphRenders = 0, writes = 0;
  const c = createAssemblyConfirmController({ createOffsetSubviewManualAnchor, escapeAttr: String, escapeHtml: String,
    getAssemblyI18n, tAssembly, rerender() { graphRenders++; }, rerenderDialog() { dialogs++; } });
  const interactions = createSubviewInteractionController({ requestAssemblyAnchorOffsetPrompt: c.requestAssemblyAnchorOffsetPrompt,
    persistProjectAssemblyViewStateFromStore: async () => { writes++; }, rerenderSubviewPanel() {}, setAssemblyActionFeedback() {}, tAssembly });
  const before = f.scoped.getState().assembly.subview.summary;
  const pending = interactions.copySubviewAnchorWithOffset({}, f.scoped, edge);
  assert.equal(dialogs, 1); assert.equal(graphRenders, 0);
  assert.equal(f.scoped.getState().assembly.subview.summary, before);
  assert.match(c.renderAssemblyConfirmModal(f.store.getState()), /data-assembly-anchor-offset-direction/);
  const id = f.store.getState().assembly.confirmDialog.id;
  c.resolveAssemblyConfirmDialog({}, f.scoped, { id, confirmed: true, value: { direction: "right", offsetBp: 50 } });
  await pending;
  assert.equal(dialogs, 2); assert.equal(graphRenders, 0); assert.equal(writes, 1);
  const anchors = f.scoped.getState().assembly.subview.manualAnchors;
  assert.equal(anchors.length, 1);
  assert.deepEqual([anchors[0].endpointA.cutBp, anchors[0].endpointB.cutBp].sort((a, b) => a - b), [150, 250]);
  assert.equal(f.store.getState().assembly.confirmDialog, null);
});

for (const change of ["route", "chr", "close"]) test(`offset-anchor dialog cannot apply after its owner changes: ${change}`, async () => {
  const f = fixture(); let writes = 0;
  const c = createAssemblyConfirmController({ createOffsetSubviewManualAnchor, escapeAttr: String, escapeHtml: String,
    getAssemblyI18n, tAssembly, rerender() {}, rerenderDialog() {} });
  const interactions = createSubviewInteractionController({ requestAssemblyAnchorOffsetPrompt: c.requestAssemblyAnchorOffsetPrompt,
    persistProjectAssemblyViewStateFromStore: async () => { writes++; }, rerenderSubviewPanel() {}, setAssemblyActionFeedback() {}, tAssembly });
  const pending = interactions.copySubviewAnchorWithOffset({}, f.scoped, edge);
  if (change === "route") f.store.setState({ activeRoute: "importer" });
  if (change === "chr") f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02", subview: null } });
  if (change === "close") changeSubviewWindow(f.store, f.id, "close");
  cancelAssemblyConfirmDialog(f.store); await pending;
  assert.equal(writes, 0); assert.equal(f.store.getState().assembly.confirmDialog, null);
});

test("Chr A-B-A keeps each task's objects, window state, anchors and viewport but replaces async ownership", () => {
  const f = fixture(), a = f.scoped.getState().assembly;
  f.scoped.setState({ assembly: { ...a, subviewTrackView: { alignmentLength: 100, visibleSpanBp: 700 },
    subviewTrackScrollState: { viewportKey: "Chr01-view", scrollLeft: 210 },
    subview: { ...a.subview, manualAnchors: [createOffsetSubviewManualAnchor(edge, { direction: "right", offsetBp: 50 }).anchor] } } });
  changeSubviewWindow(f.store, f.id, "open-floating");
  changeSubviewWindow(f.store, f.id, "position", { x: 110, y: 90, width: 700, height: 450 });
  const oldScope = f.scoped;
  f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02", subview: null } });
  f.store.setState({ assembly: { ...startSubviewWindowDraft(f.store.getState().assembly), subview: { summary: summary(5, 32) } } });
  const bId = f.store.getState().assembly.subviewWorkspace.activeId;
  f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr01", subview: null } });
  const ws = f.store.getState().assembly.subviewWorkspace;
  assert.equal(ws.activeId, f.id); assert.equal(ws.windows.length, 1);
  const item = ws.windows[0];
  assert.deepEqual([item.opened, item.floating, item.x, item.y, item.width, item.height], [true, true, 110, 90, 700, 450]);
  assert.equal(item.snapshot.subview.summary.bottom.contigId, 30);
  assert.equal(item.snapshot.subview.manualAnchors.length, 1);
  assert.equal(item.snapshot.subviewTrackScrollState.scrollLeft, 210);
  assert.equal(item.snapshot.subviewTrackView.visibleSpanBp, 700);
  assert.equal(oldScope.isLocalViewAlive(), false);
  oldScope.setState({ assembly: { ...oldScope.getState().assembly, actionError: "stale-owner" } });
  assert.notEqual(f.store.getState().assembly.actionError, "stale-owner");
  f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02", subview: null } });
  assert.equal(f.store.getState().assembly.subviewWorkspace.activeId, bId);
  assert.equal(f.store.getState().assembly.subview.summary.bottom.contigId, 32);
});

test("a scoped loading scrim can recover after an off-route response, without duplicating live requests", async () => {
  const f = fixture(), requests = []; let rendered = 0;
  const c = createSubviewPairwiseController({ session: { subviewPairwiseEvidenceRequestSeq: 0 },
    rerenderSubviewPanel() {}, scheduleDeferredSubviewPanelRerender() { rendered++; },
    getJunctionInspection: () => new Promise(resolve => requests.push(resolve)) });
  const first = c.refreshSubviewPairwiseEvidence({}, f.scoped);
  await c.refreshSubviewPairwiseEvidence({}, f.scoped);
  assert.equal(requests.length, 1);
  f.store.setState({ activeRoute: "importer" }); requests[0]({ hits: [{ id: "discarded" }] }); await first;
  assert.equal(f.scoped.getState().assembly.subview.pairwiseEvidence.status, "loading"); assert.equal(rendered, 0);
  f.store.setState({ activeRoute: "assembly" });
  const second = c.refreshSubviewPairwiseEvidence({}, f.scoped);
  await c.refreshSubviewPairwiseEvidence({}, f.scoped);
  assert.equal(requests.length, 2);
  requests[1]({ hits: [{ id: "current" }] }); await second;
  assert.equal(f.scoped.getState().assembly.subview.pairwiseEvidence.status, "loaded");
  assert.equal(f.scoped.getState().assembly.subview.pairwiseEvidence.hits[0].id, "current"); assert.equal(rendered, 1);
});

test("Main Chr A-B-A reloads actual objects and restores valid selection and view span", async () => {
  const store = createStore({ activeRoute: "assembly", locale: "en", session: { workspacePath: "D:/fixture", projectId: 1 },
    assembly: { selectedChrName: "Chr01", loading: false, selectedCtgId: 2, selectedMemberSeqId: 21,
      chrCtgs: [{ assemblyCtgId: 1 }, { assemblyCtgId: 2 }], trackSelectedCtgIds: [2],
      trackView: { visibleSpanBp: 700, alignmentLength: 100 }, trackScrollState: { viewportKey: "Chr01", scrollLeft: 150 } } });
  let deleted = false;
  const deps = { buildClearedSubviewState: () => ({ summary: null }), getCurrentProject: () => ({ primaryDatasetId: 1 }),
    listChrViewCtgs: async ({ chrName }) => ({ items: (chrName === "Chr01" ? deleted ? [1] : [1, 2] : [20, 21]).map(id => ({ assemblyCtgId: id, name: `ctg${id}`, totalLength: 1000, assignedChrName: chrName })) }),
    loadDatasetChrCtgs: async () => [], loadDeletedCtgsForChr: async () => [],
    loadSideDataForCtg: async (_root, _id, id) => ({ detail: { members: [{ assemblySeqId: id * 10 + 1 }] } }),
    mapAssemblyError: ({ error }) => ({ userMessage: String(error) }), normalizeSupportDatasetId: value => Number(value) || null,
    filterPrimaryTrackSelectionCtgIds: (ids, a) => ids.filter(id => a.chrCtgs.some(ctg => ctg.assemblyCtgId === id)), rerender() {} };
  await selectChromosome({}, store, "Chr02", deps);
  store.setState({ assembly: { ...store.getState().assembly, selectedCtgId: 21, trackView: { visibleSpanBp: 300, hiddenSupportCtgs: [{ datasetId: 22, contigId: 32 }] }, trackScrollState: { viewportKey: "Chr02", scrollLeft: 55 } } });
  await selectChromosome({}, store, "Chr01", deps);
  assert.deepEqual(store.getState().assembly.chrCtgs.map(c => c.assemblyCtgId), [1, 2]);
  assert.equal(store.getState().assembly.selectedCtgId, 2); assert.equal(store.getState().assembly.selectedMemberSeqId, 21);
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, [2]);
  assert.equal(store.getState().assembly.trackView.visibleSpanBp, 700); assert.equal(store.getState().assembly.trackScrollState.scrollLeft, 150);
  assert.deepEqual(store.getState().assembly.trackView.hiddenSupportCtgs, [{ datasetId: 22, contigId: 32 }]);
  await selectChromosome({}, store, "Chr02", deps); assert.equal(store.getState().assembly.selectedCtgId, 21);
  deleted = true; await selectChromosome({}, store, "Chr01", deps);
  assert.equal(store.getState().assembly.selectedCtgId, 1); assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, []);
});
