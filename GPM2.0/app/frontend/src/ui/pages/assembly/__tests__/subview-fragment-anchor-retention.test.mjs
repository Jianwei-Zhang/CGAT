import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createSubviewFragmentController } from "../subview-fragment-controller.js";
import { createSubviewInteractionController } from "../subview-interaction-controller.js";
import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import { memberAnchorEndpointKey, memberCoordinateToSource } from "../subview-fragment-model.js";
import { collectSubviewAnchorScene } from "../subview-anchor-objects.js";
import { rollbackSubviewHistory, restoreSubviewHistoryRollback } from "../subview-history-state.js";

function createStore(initial) { let state = initial; return { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } }; }

function sceneHost(store) {
  return { querySelectorAll(selector) {
    const html = renderAssemblyPage(store.getState());
    const tags = selector.includes("data-subview-anchor-kind")
      ? [...html.matchAll(/<[^>]+data-subview-anchor-kind=[^>]*>/g)]
      : selector.includes("data-subview-rect-x") ? [...html.matchAll(/<[^>]+data-subview-rect-x=[^>]*>/g)] : [];
    return tags.map(([tag]) => {
      const data = Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map((m) =>
        [m[1], m[2].replaceAll("&quot;", '"').replaceAll("&amp;", "&")]));
      return { getAttribute: (name) => data[name] ?? null };
    });
  } };
}
for (const mode of ["2-contig", "track-pair", "composition", "composition-flipped"]) for (const descriptor of [false, true]) for (const start of [1800, 1801]) {
  test(`${mode} deletion ${start}–2299 retains outside evidence anchors, stored descriptors=${descriptor}`, async () => {
    const initial = createIdentityRenderState(mode.replace("-flipped", ""));
    if (mode.endsWith("-flipped")) initial.assembly.subview.summary.members.find((m) => m.assemblyCtgId === 30).flipped = true;
    const store = createStore(initial), host = sceneHost(store);
    const edges = collectSubviewAnchorScene(host).filter((edge) => edge.kind === "evidence"
      && [500, 1800, 2300, 3600].includes(edge.descriptor?.top.cutBp));
    assert.equal(edges.length, 4);
    const ids = edges.map((edge) => ({ hitKey: edge.node.getAttribute("data-subview-anchor-hit-key"),
      edge: edge.node.getAttribute("data-subview-anchor-edge") }));
    if (descriptor) {
      const controller = createSubviewInteractionController({ rerenderSubviewPanel() {}, persistProjectAssemblyViewStateFromStore: async () => {} });
      for (const id of ids) await controller.toggleSubviewAnchorEdge(host, store, id);
    } else {
      const state = store.getState();
      store.setState({ assembly: { ...state.assembly, subview: { ...state.assembly.subview, activeAnchors: ids } } });
    }
    const expected = edges.map((edge) => edge.objectId).sort();
    const runtime = createSubviewFragmentController({
      projectHistorical: (state) => projectRenderedSubviewToComposition(state, renderAssemblyPage(state)),
      rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {}, persistProjectAssemblyViewStateFromStore: async () => {},
    });
    assert.equal(await runtime.deleteLocalFragment(host, store, {
      assemblyCtgId: 30, trackRole: "support", slot: "top", start, end: 2299,
    }), true);
    const active = () => collectSubviewAnchorScene(host).filter((edge) =>
      edge.node.getAttribute("data-subview-anchor-active") === "1").map((edge) => edge.objectId).sort();
    const checkSourcePoints = () => {
      const members = store.getState().assembly.subview.summary.members;
      for (const edge of collectSubviewAnchorScene(host).filter((entry) => entry.node.getAttribute("data-subview-anchor-active") === "1")) {
        const original = edges.find((entry) => entry.objectId === edge.objectId);
        for (const side of ["top", "bottom"]) {
          const endpoint = edge.descriptor[side];
          const member = members.find((entry) => memberAnchorEndpointKey(entry) === endpoint.endpointKey);
          assert.ok(member);
          assert.equal(memberCoordinateToSource(member, endpoint.cutBp), original.descriptor[side].cutBp,
            "surviving anchor stays on the exact same source base");
        }
      }
    };
    assert.deepEqual(active(), expected, "anchors outside deleted bases must remain visibly active");
    checkSourcePoints();
    const rollbackButton = renderAssemblyPage(store.getState()).match(/<button[^>]*data-subview-action="history-rollback"[^>]*>/)?.[0];
    assert.ok(rollbackButton, "local deletion exposes its history control");
    assert.doesNotMatch(rollbackButton, /\bdisabled\b/, "local deletion remains undoable after render");
    const after = JSON.parse(JSON.stringify(store.getState().assembly));
    store.setState({ assembly: rollbackSubviewHistory(after).assembly });
    assert.deepEqual(active(), edges.map((edge) => edge.objectId).sort());
    store.setState({ assembly: restoreSubviewHistoryRollback(store.getState().assembly).assembly });
    assert.deepEqual(active(), expected);
    store.setState(JSON.parse(JSON.stringify(store.getState())));
    assert.deepEqual(active(), expected);
    checkSourcePoints();
  });
}


test("outside anchors survive main history reload followed by local undo/redo without crossing history ownership", async () => {
  const { runMainViewHistoryControlAction } = await import("../main-view-history-runtime.js");
  const { reconcileLocalSubviewWithMain } = await import("../subview-fragment-reconcile.js");
  const initial = createIdentityRenderState("composition");
  initial.session = { workspacePath: "D:/fixture", projectId: 7 };
  const operation = { kind: "flip-ctg", targetCount: 1, targetName: "primary" };
  initial.assembly.mainViewHistory = { chrName: "Chr01", canUndo: true, undoOperation: operation,
    appliedOperationCount: 1, retainedOperationCount: 1, inFlight: false };
  const store = createStore(initial), host = sceneHost(store);
  const edges = collectSubviewAnchorScene(host).filter((edge) => edge.kind === "evidence"
    && [500, 1800, 2300, 3600].includes(edge.descriptor?.top.cutBp));
  initial.assembly.subview.activeAnchors = edges.map((edge) => ({ hitKey: edge.node.getAttribute("data-subview-anchor-hit-key"), edge: edge.node.getAttribute("data-subview-anchor-edge") }));
  const originalMainHistory = JSON.parse(JSON.stringify(initial.assembly.mainViewHistory));
  const runtime = createSubviewFragmentController({
    projectHistorical: (state) => projectRenderedSubviewToComposition(state, renderAssemblyPage(state)),
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {}, persistProjectAssemblyViewStateFromStore: async () => {},
  });
  await runtime.deleteLocalFragment(host, store, { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1800, end: 2299 });
  assert.deepEqual(store.getState().assembly.mainViewHistory, originalMainHistory);
  const active = () => collectSubviewAnchorScene(host).filter((edge) => edge.node.getAttribute("data-subview-anchor-active") === "1").map((edge) => edge.objectId).sort();
  const expected = edges.map((edge) => edge.objectId).sort();
  for (const action of ["undo", "redo"]) {
    const before = store.getState().assembly, historyKey = before.subview.historyKey;
    const localDepth = before.subviewHistoryByKey[historyKey].past.length;
    assert.equal(await runMainViewHistoryControlAction(host, store, action, {
      executeMainViewHistoryAction: async () => ({ changed: true, affectedCtgIds: [2], operation,
        status: { chrName: "Chr01", canUndo: action === "redo", canRedo: action === "undo",
          undoOperation: action === "redo" ? operation : null, redoOperation: action === "undo" ? operation : null,
          appliedOperationCount: action === "undo" ? 0 : 1, retainedOperationCount: 1 } }),
      loadAssemblyView: async () => {
        const assembly = store.getState().assembly;
        store.setState({ assembly: reconcileLocalSubviewWithMain({ ...assembly,
          chrCtgs: assembly.chrCtgs.map((ctg) => ({ ...ctg, orient: action === "undo" ? "-" : "+" })) }) });
      },
      mapAssemblyError: ({ error }) => ({ userMessage: error.message }), rerender() {},
    }), true, store.getState().assembly.actionError || JSON.stringify(store.getState().assembly.mainViewHistory));
    assert.equal(store.getState().assembly.subviewHistoryByKey[historyKey].past.length, localDepth);
    assert.deepEqual(active(), expected);
    const mainHistory = JSON.parse(JSON.stringify(store.getState().assembly.mainViewHistory));
    store.setState({ assembly: rollbackSubviewHistory(store.getState().assembly).assembly });
    assert.deepEqual(active(), edges.map((edge) => edge.objectId).sort(), "local undo keeps anchors through native parent rebind");
    store.setState({ assembly: restoreSubviewHistoryRollback(store.getState().assembly).assembly });
    assert.deepEqual(active(), expected);
    assert.deepEqual(store.getState().assembly.mainViewHistory, mainHistory);
  }
});
