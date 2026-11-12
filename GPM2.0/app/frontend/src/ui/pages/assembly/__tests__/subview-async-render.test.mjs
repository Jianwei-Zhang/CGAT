import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { installSubviewWorkspace, changeSubviewWindow, getSubviewWindowStore } from "../subview-workspace-state.js";
import { createSubviewCompositionController } from "../subview-composition-controller.js";
import { createSubviewPairwiseController } from "../subview-pairwise-controller.js";
import { createDeferredRerenderCoordinator } from "../deferred-rerender-runtime.js";

function fixture() {
  const candidates = [2, 5, 8].map(id => ({ assemblyCtgId: id,
    source: { role: "primary", datasetId: 11 }, label: `ctg${id}`, lengthBp: 1200,
    candidateKey: `assembly:${id}`, entityKey: `assembly:${id}` }));
  const store = createStore({ ...createState({ assembly: { subview: null,
    subviewCompositionCandidates: candidates, subviewCompositionCandidatesLoaded: true,
    subviewTrackView: { alignmentLength: 1, minIdentityPct: 0 },
  } }), activeRoute: "assembly" });
  installSubviewWorkspace(store);
  const frames = [], requests = [], pending = [], paints = new Map(), completedPaints = [];
  const paint = (_host, owner) => {
    const scoped = getSubviewWindowStore(owner);
    paints.set(scoped.localViewWindowId, renderAssemblyPage(scoped.getState()));
  };
  const coordinators = new WeakMap();
  const pairwise = createSubviewPairwiseController({
    session: { subviewPairwiseEvidenceRequestSeq: 0 },
    getTrackPairwiseEvidence(params) {
      return new Promise((resolve, reject) => requests.push({ params, resolve, reject }));
    },
    rerenderSubviewPanel: paint,
    scheduleDeferredSubviewPanelRerender(host, scoped) {
      let coordinator = coordinators.get(scoped);
      if (!coordinator) {
        coordinator = createDeferredRerenderCoordinator({
          requestAnimationFrame: callback => frames.push(callback),
          rerenderSubviewPanel(host, owner) {
            completedPaints.push({ host, id: owner.localViewWindowId });
            paint(host, owner);
          },
        });
        coordinators.set(scoped, coordinator);
      }
      coordinator.scheduleSubviewPanel(host, scoped);
    },
  });
  const controller = createSubviewCompositionController({ session: {},
    getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => {},
    rerenderSubviewPanel: paint,
    refreshSubviewPairwiseEvidence(host, owner) {
      pending.push(pairwise.refreshSubviewPairwiseEvidence(host, owner));
    },
    anchorController: { resetScope() {} },
  });
  // The context-menu route can have no window node (new/unmounted window).
  const add = (id, targetWindowId = null, lane = "top") => controller.addContextCtgToComposition(null, store,
    { assemblyCtgId: id, trackRole: "primary" }, lane,
    { targetWindowId, workspaceGeneration: store.getState().assembly.subviewWorkspace.generation });
  const finish = async (fail = false) => {
    const request = requests.at(-1);
    if (fail) request.reject(new Error("evidence fixture failure"));
    else request.resolve({ hits: [{ hitKey: "ready-without-click", queryAssemblyCtgId: 2,
      subjectAssemblyCtgId: 5, queryStart: 10, queryEnd: 1100, subjectStart: 20, subjectEnd: 1110,
      alignLength: 1090, identityPct: 97, strand: "+" }], evidenceSource: "fixture", coverage: [] });
    await Promise.all(pending);
    while (frames.length) frames.shift()(0);
  };
  return { store, add, finish, paints, completedPaints, frames, pending, requests };
}

for (const fail of [false, true]) test(`right-click addition paints async ${fail ? "error" : "bands"} without another operation`, async () => {
  const f = fixture();
  await f.add(2);
  const id = f.store.getState().assembly.subviewWorkspace.activeId;
  await f.add(5, id, "bottom");
  assert.equal(f.requests.length, 1);
  assert.equal(getSubviewWindowStore(f.store, id).getState().assembly.subview.pairwiseEvidence.status, "loading");
  assert.doesNotMatch(f.paints.get(id), /data-subview-hit-key="ready-without-click"/);
  await f.finish(fail);
  assert.deepEqual(f.completedPaints, [{ host: null, id }]);
  const evidence = getSubviewWindowStore(f.store, id).getState().assembly.subview.pairwiseEvidence;
  assert.equal(evidence.status, fail ? "error" : "loaded");
  if (fail) assert.ok(f.paints.get(id).includes(evidence.error.userMessage));
  else assert.match(f.paints.get(id), /data-subview-hit-key="ready-without-click"/);
});

test("async completion refreshes its owning window even after another view becomes active", async () => {
  const f = fixture(); await f.add(2);
  const id = f.store.getState().assembly.subviewWorkspace.activeId;
  await f.add(5, id, "bottom");
  await f.add(8);
  const other = f.store.getState().assembly.subviewWorkspace.activeId;
  const otherPaint = f.paints.get(other);
  await f.finish();
  assert.deepEqual(f.completedPaints, [{ host: null, id }]);
  assert.match(f.paints.get(id), /data-subview-hit-key="ready-without-click"/);
  assert.equal(f.paints.get(other), otherPaint);
  assert.equal(f.store.getState().assembly.subviewWorkspace.activeId, other);
});

for (const transition of ["close", "scope", "route"]) test(`queued completion cannot repaint a ${transition === "close" ? "closed window" : transition === "scope" ? "replaced chromosome scope" : "left assembly route"}`, async () => {
  const f = fixture(); await f.add(2);
  const id = f.store.getState().assembly.subviewWorkspace.activeId;
  await f.add(5, id, "bottom");
  f.requests[0].resolve({ hits: [], coverage: [] });
  await Promise.all(f.pending);
  assert.equal(f.frames.length, 1);
  if (transition === "close") changeSubviewWindow(f.store, id, "close");
  else if (transition === "route") f.store.setState({ activeRoute: "importer" });
  else f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr02" } });
  while (f.frames.length) f.frames.shift()(0);
  assert.deepEqual(f.completedPaints, []);
});
