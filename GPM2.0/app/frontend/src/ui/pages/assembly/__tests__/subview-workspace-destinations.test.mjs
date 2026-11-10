import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { createState, __testBuildAssemblyContextMenuItems } from "./tabs-semantics-harness.mjs";
import { installSubviewWorkspace, changeSubviewWindow, getSubviewWindowStore } from "../subview-workspace-state.js";
import { createSubviewCompositionController } from "../subview-composition-controller.js";

const member = (id, role = "primary") => ({ assemblyCtgId: id, source: { role, datasetId: 11 },
  label: `ctg${id}`, lengthBp: 1200, candidateKey: `assembly:${id}`, entityKey: `assembly:${id}` });
function fixture(load) {
  const store = createStore(createState({ assembly: { subview: null, trackSelectedCtgIds: [],
    subviewCompositionCandidates: load ? [] : [member(2), member(5), member(8)],
    subviewCompositionCandidatesLoaded: !load } }));
  installSubviewWorkspace(store);
  let writes = 0;
  const controller = createSubviewCompositionController({ session: {}, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: load || (async () => ({ items: [] })),
    persistProjectAssemblyViewStateFromStore: async () => { writes++; },
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {}, anchorController: { resetScope() {} } });
  const add = (id, targetWindowId = null, lane = "top") => controller.addContextCtgToComposition(null, store,
    { assemblyCtgId: id, trackRole: "primary" }, lane,
    { targetWindowId, workspaceGeneration: store.getState().assembly.subviewWorkspace.generation });
  return { store, controller, add, writes: () => writes };
}
const members = (store, id) => getSubviewWindowStore(store, id).getState().assembly.subview.summary.members;

test("new destination is empty, old destination is isolated, minimized target is restored", async () => {
  const { store, add } = fixture();
  assert.equal(await add(2), true);
  const a = store.getState().assembly.subviewWorkspace.activeId;
  assert.equal(await add(5), true);
  const b = store.getState().assembly.subviewWorkspace.activeId;
  assert.notEqual(a, b);
  assert.deepEqual(members(store, a).map(m => m.assemblyCtgId), [2]);
  assert.deepEqual(members(store, b).map(m => m.assemblyCtgId), [5]);
  changeSubviewWindow(store, a, "minimize");
  assert.equal(await add(8, a, "bottom"), true);
  assert.equal(store.getState().assembly.subviewWorkspace.activeId, a);
  assert.equal(store.getState().assembly.subviewWorkspace.windows.find(w => w.id === a).minimized, false);
  assert.deepEqual(members(store, a).map(m => [m.assemblyCtgId, m.lane]), [[2, "top"], [8, "bottom"]]);
  assert.deepEqual(members(store, b).map(m => m.assemblyCtgId), [5]);
});

test("new destination consumes explicit Main multiselection once", async () => {
  const { store, add } = fixture();
  store.setState({ assembly: { ...store.getState().assembly, trackSelectedCtgIds: [2, 5] } });
  await add(2);
  assert.deepEqual(store.getState().assembly.subview.summary.members.map(m => m.assemblyCtgId), [2, 5]);
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, []);
  await add(8);
  assert.deepEqual(store.getState().assembly.subview.summary.members.map(m => m.assemblyCtgId), [8]);
});

test("menu has new and every existing destination, and closes over the exact window identity", async () => {
  const { store, add } = fixture(); await add(2); const a = store.getState().assembly.subviewWorkspace.activeId;
  await add(5); changeSubviewWindow(store, a, "minimize");
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({ ctgContext: { assemblyCtgId: 8, trackRole: "primary" },
    host: {}, store, actions: { canEditTrackCtg: () => false,
      addContextCtgToComposition: (...args) => calls.push(args) } });
  const menu = items.find(item => item.label === "加入局部视图");
  assert.equal(menu.children.length, 3);
  assert.equal(menu.children[0].label, "新建局部比对");
  assert.match(menu.children[1].label, /^#1 /);
  assert.match(menu.children[2].label, /^#2 /);
  await menu.children[1].children[1].run();
  assert.equal(calls[0][3], "bottom"); assert.equal(calls[0][4].targetWindowId, a);
});

test("a closed destination never falls back to the active window", async () => {
  const f = fixture(); await f.add(2); const a = f.store.getState().assembly.subviewWorkspace.activeId;
  await f.add(5); changeSubviewWindow(f.store, a, "close"); const before = f.writes();
  assert.equal(await f.add(8, a), false); assert.equal(f.writes(), before);
  assert.deepEqual(f.store.getState().assembly.subview.summary.members.map(m => m.assemblyCtgId), [5]);
});

for (const transition of ["close", "scope"]) test(`candidate load cannot commit after target ${transition}`, async () => {
  const f = fixture(); await f.add(2); const a = f.store.getState().assembly.subviewWorkspace.activeId;
  f.store.setState({ assembly: { ...f.store.getState().assembly, subviewCompositionCandidates: [], subviewCompositionCandidatesLoaded: false } });
  let resolve;
  const controller = createSubviewCompositionController({ session: {}, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: () => new Promise(done => { resolve = done; }),
    persistProjectAssemblyViewStateFromStore() { assert.fail("stale operation must not persist"); },
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {}, anchorController: { resetScope() {} } });
  const pending = controller.addContextCtgToComposition(null, f.store, { assemblyCtgId: 5, trackRole: "primary" }, "top",
    { targetWindowId: a, workspaceGeneration: f.store.getState().assembly.subviewWorkspace.generation });
  if (transition === "close") changeSubviewWindow(f.store, a, "close");
  else f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02", subview: null } });
  resolve({ items: [] });
  assert.equal(await pending, false);
  assert.equal(f.store.getState().assembly.subviewWorkspace.windows.length, 0);
});


test("the same backing contig in multiple phased tracks keeps its exact source identity", async () => {
  const f = fixture();
  const candidate = track => ({ ...member(2, "phased"), source: { role: "phased", datasetId: 11,
    phasedTrackId: track, phasedItemId: track + 10, hap: String(track) } });
  f.store.setState({ assembly: { ...f.store.getState().assembly, subviewCompositionCandidates: [candidate(1), candidate(2)] } });
  assert.equal(await f.controller.addContextCtgToComposition(null, f.store, {
    assemblyCtgId: 2, trackRole: "phased", datasetId: 11, phasedTrackId: 2, phasedTrackItemId: 12,
    phasedHaplotypeKey: "2",
  }, "bottom", { targetWindowId: null }), true);
  assert.equal(f.store.getState().assembly.subview.summary.members[0].source.phasedTrackId, 2);
  const writes = f.writes();
  assert.equal(await f.controller.addContextCtgToComposition(null, f.store, {
    assemblyCtgId: 2, trackRole: "phased", phasedTrackId: 3,
  }, "top", { targetWindowId: null }), false);
  assert.equal(f.writes(), writes);
});

test("an old menu generation cannot create a view after scope ABA", async () => {
  const f = fixture();
  const old = f.store.getState().assembly.subviewWorkspace.generation;
  const chr = f.store.getState().assembly.selectedChrName;
  for (const selectedChrName of ["another", chr]) f.store.setState({ assembly: {
    ...f.store.getState().assembly, selectedChrName, subview: null } });
  assert.equal(await f.controller.addContextCtgToComposition(null, f.store, {
    assemblyCtgId: 2, trackRole: "primary",
  }, "top", { targetWindowId: null, workspaceGeneration: old }), false);
  assert.equal(f.writes(), 0);
});
