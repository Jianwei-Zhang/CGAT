import { loadAssemblyView } from "../assembly-data-runtime.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createSubviewFragmentSyncRuntime, buildLocalFragmentSyncRequest } from "../subview-fragment-sync-runtime.js";
import { prepareSourceOwnedSubviewHistory } from "../subview-fragment-history.js";
import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import { reconcileLocalSubviewWithMain } from "../subview-fragment-reconcile.js";
import { buildSubviewCompositionHistoryKey, activateSubviewCompositionHistory, commitSubviewHistoryOperation, rollbackSubviewHistory, restoreSubviewHistoryRollback, resolveCurrentSubviewHistory } from "../subview-history-state.js";
import { memberSourceInterval } from "../subview-fragment-model.js";

function createStore(initial) { let state = initial; return { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } }; }
const host = {}, viewport = { bpPerPx: 20, leftBp: 0, topPx: 0 };
const project = (state) => projectRenderedSubviewToComposition(state, renderAssemblyPage(state));
function stateFor(mode, orient = "+") {
  const state = createIdentityRenderState(mode);
  state.session = { workspacePath: "D:/fixture", projectId: 7 };
  state.assembly.mainViewHistory = { chrName: "Chr01", inFlight: false, appliedOperationCount: 0 };
  Object.assign(state.assembly.chrCtgs[0], { orient, originSourceSeqId: 700 });
  if (mode === "composition") Object.assign(state.assembly.subview.summary.members.find((m) => m.assemblyCtgId === 2), { baseOrientation: orient, originSourceSeqId: 700 });
  return state;
}
function runtime(store, overrides = {}) {
  const calls = [], persisted = [];
  let inside = false, children = [], deleted = [], historyCount = 0;
  const api = createSubviewFragmentSyncRuntime({
    projectHistorical: project,
    inspectMainViewDelete: async (args) => { calls.push(["inspect", args]); return { finalPathReferenceCount: 2, degapReferenceCount: 1 }; },
    confirm: async (message) => { calls.push(["confirm", message]); return true; },
    flushBefore: async () => { assert.equal(inside, false); calls.push(["flush"]); persisted.push(JSON.parse(JSON.stringify(store.getState().assembly))); },
    serialize: async (_store, task) => { inside = true; try { return await task(() => true); } finally { inside = false; } },
    runMainViewEditorAction: async (request) => {
      assert.equal(inside, true); calls.push(["native", request]); historyCount += 1;
      const { args } = request, parent = store.getState().assembly.chrCtgs[0];
      const cuts = [args.sourceStart - 1, args.cutAfter, ...(args.cuts || []), args.sourceEnd].filter((cut) => cut > 0 && cut < parent.totalLength).sort((a, b) => a - b);
      const boundaries = [1, ...new Set(cuts.map((cut) => cut + 1)), parent.totalLength + 1];
      children = boundaries.slice(0, -1).flatMap((start, index) => {
        const end = boundaries[index + 1] - 1;
        if (args.action === "delete" && start >= args.sourceStart && end <= args.sourceEnd) {
          const whole = start === 1 && end === parent.totalLength;
          deleted.push({ assemblyCtgId: whole ? parent.assemblyCtgId : 701 + index, deletedCtgRecordId: 91 + index,
            totalLength: end - start + 1, refOrient: parent.orient,
            sourceGroupKey: whole ? "" : "manual-fragment:2", sourceRange: { sourceSeqId: 700, sourceStart: start, sourceEnd: end } });
          return [];
        }
        return [{ ...parent, assemblyCtgId: 701 + index, totalLength: end - start + 1, lengthBp: end - start + 1,
          sourceFragment: { sourceSeqId: 700, groupKey: "manual-fragment:2", sourceStart: start, sourceEnd: end, sourceLength: 16000 } }];
      });
      return { changed: true, status: { chrName: "Chr01", canUndo: true, appliedOperationCount: historyCount } };
    },
    loadAssemblyView: async (_host, _store, options) => {
      const latest = store.getState();
      // Use the production loader, including reading the OLD flushed history
      // and activating it. A reconcile-only mock misses this regression.
      const saved = persisted.at(-1);
      await loadAssemblyView(host, store, options, {
        getProjectAssemblyViewState: async () => ({ ...saved, supportDatasetId: 22 }),
        getCurrentProject: () => ({ primaryDatasetId: 11 }), getSupportDatasetOptions: () => [{ datasetId: 22 }],
        listProjectChromosomes: async () => ({ items: [{ chrName: "Chr01" }] }),
        listChrViewCtgs: async () => ({ items: children }), loadDatasetChrCtgs: async () => latest.assembly.supportChrCtgs,
        loadDeletedCtgsForChr: async () => deleted, loadSideDataForCtg: async () => ({ detail: { members: [] }, candidates: {} }),
        getMainViewHistoryStatus: async () => latest.assembly.mainViewHistory,
        buildClearedSubviewState: () => ({ summary: null }), buildSubviewTrackPairHiddenCtgKey: () => "",
        buildSubviewTrackPairPoolsFromAssembly: () => ({}),
        filterPrimaryTrackSelectionCtgIds: (v) => v || [], filterSubviewTrackDragOffsetsBySummary: (v) => v || [],
        filterSubviewTrackPairHiddenCtgs: (v) => v || [], filterSubviewTrackPairSelectionCtgs: (v) => v || [],
        normalizeDeletedCtgRecordIds: (v) => v || [], normalizeSupportDatasetId: (id) => id == null ? null : Number(id),
        normalizeSupportMirroredCtgs: (v) => v || [], normalizeTrackSelectionCtgIds: (v) => v || [],
        buildSubviewCompositionHistoryKey, activateSubviewCompositionHistory,
        mapAssemblyError: ({ error }) => ({ userMessage: error.message }), rerender() { calls.push(["loader-render"]); },
      });
      assert.equal(store.getState().assembly.error, "");
      calls.push(["reload", options]);
    },
    persistNow: async () => { assert.equal(inside, true); calls.push(["persist"]); persisted.push(JSON.parse(JSON.stringify(store.getState().assembly))); },
    rerenderMain() { calls.push(["render-main"]); },
    rerenderSubviewPanel() { calls.push(["render-subview"]); },
    rerenderFinalPathCard() { calls.push(["render-final-path"]); },
    async refreshSubviewPairwiseEvidence(_host, _store, options) {
      calls.push(["evidence-start", options]);
      await Promise.resolve();
      calls.push(["evidence-ready"]);
    },
    ...overrides,
  });
  return { run: (context, action) => api(host, store, context, action), calls, persisted, historyCount: () => historyCount };
}
const contextFor = (mode, start = 1001, end = 5000) => ({ assemblyCtgId: 2, trackRole: "primary", slot: "bottom", start, end,
  ...(mode === "composition" ? { entityKey: "assembly:2" } : {}) });

for (const mode of ["composition", "2-contig", "track-pair"]) {
  test(`synchronized ${mode} split waits for evidence and renders each card only once`, async () => {
    const store = createStore(stateFor(mode));
    const api = runtime(store);
    assert.equal(await api.run(contextFor(mode), { action: "split", cutAfter: 3000 }), true);
    assert.deepEqual(api.calls.filter(([name]) => name === "reload")[0][1], {
      keepCurrentChr: true, keepCurrentCtg: false, renderLoading: false, renderResult: false,
    });
    assert.deepEqual(api.calls.filter(([name]) => name === "evidence-start")[0][1], {
      rerenderLoading: false, rerenderLoaded: false,
    });
    assert.deepEqual(api.calls.map(([name]) => name), [
      "inspect", "confirm", "flush", "native", "reload", "evidence-start", "evidence-ready",
      "persist", "render-main", "render-subview", "render-final-path",
    ], "no loader page replacement or loading-state card replacement may precede the final render");
  });
}

test("synchronized split commits one Local View entry and one Main View entry, and keeps them independent", async () => {
  const state = stateFor("composition");
  state.assembly = activateSubviewCompositionHistory(state.assembly, { stateOrLocale: state }).assembly;
  const store = createStore(state), api = runtime(store);
  const beforeDepth = resolveCurrentSubviewHistory(state.assembly).record.past.length;
  assert.equal(await api.run(contextFor("composition"), { action: "split", cutAfter: 3000 }), true);
  const after = store.getState().assembly;
  assert.equal(resolveCurrentSubviewHistory(after).record.past.length, beforeDepth + 1);
  assert.equal(after.mainViewHistory.appliedOperationCount, 1);
  const localUndone = rollbackSubviewHistory(JSON.parse(JSON.stringify(after)));
  assert.equal(localUndone.changed, true);
  assert.equal(localUndone.assembly.chrCtgs.length, after.chrCtgs.length, "Local undo does not undo Main split");
  assert.equal(localUndone.assembly.mainViewHistory.appliedOperationCount, 1);
  const localRedone = restoreSubviewHistoryRollback(localUndone.assembly);
  assert.equal(localRedone.changed, true);
  assert.equal(localRedone.assembly.chrCtgs.length, after.chrCtgs.length);
});

for (const mode of ["2-contig", "track-pair", "composition"]) for (const action of ["split", "delete"]) {
  test(`${mode} synchronized ${action} inspects dependencies, mutates main once and preserves independent local history`, async () => {
    const state = stateFor(mode), store = createStore(state), api = runtime(store);
    assert.equal(await api.run(contextFor(mode), { action, ...(action === "split" ? { cutAfter: 3000 } : {}) }), true);
    const after = store.getState().assembly;
    assert.equal(api.historyCount(), 1);
    assert.equal(after.mainViewHistory.appliedOperationCount, 1);
    assert.equal(after.mainViewHistory.inFlight, false);
    assert.equal(after.chrCtgs.length, action === "split" ? 4 : 2);
    assert.deepEqual(api.calls.map(([kind]) => kind), ["inspect", "confirm", "flush", "native", "reload", "evidence-start", "evidence-ready", "persist", "render-main", "render-subview", "render-final-path"]);
    assert.match(api.calls[1][1], /不可变源区间/);
    const request = api.calls.find(([kind]) => kind === "native")[1];
    assert.equal(request.action, "edit-local-fragment");
    assert.deepEqual(request.args.targets, [{ assemblyCtgId: 2, sourceStart: 1, sourceEnd: 16000, orient: "+" }]);
    const local = after.subview.summary.members.filter((m) => m.source.role === "primary");
    assert.deepEqual(local.map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd]),
      action === "split" ? [[1, 1000], [1001, 3000], [3001, 5000], [5001, 16000]] : [[1, 1000], [5001, 16000]]);
    const record = resolveCurrentSubviewHistory(after).record;
    assert.equal(record.default.kind, "composition");
    assert.ok(record.default.composition.members.filter((m) => m.source.role === "primary").every((m) =>
      m.localFragment.parts.every((part) => part.assemblyCtgId !== 2)));
    if (action === "split") {
      const undo = rollbackSubviewHistory(JSON.parse(JSON.stringify(after)));
      assert.equal(undo.changed, true);
      assert.equal(undo.assembly.chrCtgs.length, 4, "local undo must not undo real Main View split");
      assert.equal(undo.assembly.subview.summary.members.filter((m) => m.source.role === "primary").length, 1);
    }
    assert.equal(api.persisted.length, 2);
  });
}

for (const mode of ["2-contig", "track-pair"]) {
  test(`legacy ${mode} history migration keeps past/redo, flip state and exact rendered offsets`, () => {
    const state = stateFor(mode);
    const first = commitSubviewHistoryOperation(state.assembly, {
      nextSubview: { ...state.assembly.subview, flippedCtgs: [{ slot: "bottom", contigId: 2 }] }, operation: { kind: "flip-contig" },
    });
    const second = commitSubviewHistoryOperation(first.assembly, { nextSubview: first.assembly.subview,
      nextSubviewTrackDragOffsets: [{ slot: "bottom", contigId: 2, offsetBp: -900 }], operation: { kind: "drag-contig" },
    });
    const undo = rollbackSubviewHistory(second.assembly);
    const before = { ...state, assembly: undo.assembly };
    const prepared = prepareSourceOwnedSubviewHistory(before, host, { viewport, projectHistorical: project });
    const previous = resolveCurrentSubviewHistory(undo.assembly).record;
    const record = resolveCurrentSubviewHistory(prepared).record;
    assert.equal(record.past.length, previous.past.length); assert.equal(record.forward.length, previous.forward.length);
    assert.equal(record.current.composition.members.find((m) => m.assemblyCtgId === 2).flipped, true);
    const next = record.forward[0].snapshot.composition;
    const oldProjection = project({ ...state, assembly: second.assembly });
    assert.deepEqual(next.members.map((m) => [m.entityKey, m.xBp, m.flipped]), oldProjection.members.map((m) => [m.entityKey, m.xBp, m.flipped]));
  });
}

test("cancel, stale confirmation, native failure and committed refresh failure do not silently repeat or leak edits", async () => {
  const before = stateFor("composition"), store = createStore(before);
  const canceled = runtime(store, { confirm: async () => false });
  assert.equal(await canceled.run(contextFor("composition"), { action: "delete" }), false);
  assert.equal(canceled.historyCount(), 0); assert.equal(canceled.persisted.length, 0);
  assert.equal(store.getState().assembly, before.assembly);
  const stale = runtime(store, { confirm: async () => {
    store.setState({ assembly: { ...store.getState().assembly, subview: { ...store.getState().assembly.subview } } }); return true;
  } });
  assert.equal(await stale.run(contextFor("composition"), { action: "delete" }), false);
  assert.equal(stale.historyCount(), 0); assert.equal(stale.persisted.length, 0);
  const prior = store.getState().assembly;
  const rejected = runtime(store, { runMainViewEditorAction: async () => { throw new Error("LOCAL_FRAGMENT_STALE_SOURCE"); } });
  assert.equal(await rejected.run(contextFor("composition"), { action: "delete" }), false);
  assert.equal(store.getState().assembly.subview, prior.subview);
  assert.equal(store.getState().assembly.mainViewHistory.inFlight, false);
  assert.match(store.getState().assembly.actionError, /STALE_SOURCE/);
  const committed = runtime(store, { loadAssemblyView: async () => { throw new Error("refresh failed"); } });
  assert.equal(await committed.run(contextFor("composition"), { action: "delete" }), false);
  assert.equal(committed.historyCount(), 1);
  assert.equal(store.getState().assembly.sourceEditingReloadRequired, true);
  assert.match(store.getState().assembly.actionError, /已提交/);
  assert.equal(buildLocalFragmentSyncRequest(store.getState(), host, contextFor("composition"), { action: "delete" }), null);
});

test("a project switch during native completion never writes the old local view into the new project", async () => {
  const store = createStore(stateFor("composition"));
  const api = runtime(store, { runMainViewEditorAction: async () => {
    const next = stateFor("composition"); next.session = { ...next.session, projectId: 999 };
    store.setState(next); return { changed: true, status: { chrName: "Chr01" } };
  } });
  assert.equal(await api.run(contextFor("composition"), { action: "delete" }), false);
  assert.equal(store.getState().session.projectId, 999);
  assert.equal(store.getState().assembly.chrCtgs[0].assemblyCtgId, 2);
  assert.equal(api.calls.some(([kind]) => kind === "persist"), false);
});


test("legacy locally-flipped anchor ranges synchronize the clicked source bases, not the opposite parent interval", async () => {
  const { resolveLocalFragmentContext } = await import("../subview-fragment-controller.js");
  const state = stateFor("2-contig");
  state.assembly.subview.flippedCtgs = [{ slot: "bottom", contigId: 2 }];
  const requested = buildLocalFragmentSyncRequest(state, host, { ...contextFor("2-contig", 1001, 3000), coordinateSpace: "display" }, { action: "delete" });
  assert.deepEqual([requested.args.sourceStart, requested.args.sourceEnd], [13001, 15000]);
  const local = resolveLocalFragmentContext(state, host, { ...contextFor("2-contig", 1001, 3000), coordinateSpace: "display" });
  assert.equal(local.member.lengthBp, 2000);
  const store = createStore(state), api = runtime(store);
  assert.equal(await api.run({ ...contextFor("2-contig", 1001, 3000), coordinateSpace: "display" }, { action: "delete" }), true);
  assert.deepEqual(store.getState().assembly.chrCtgs.map((ctg) => [ctg.sourceFragment.sourceStart, ctg.sourceFragment.sourceEnd]), [[1, 13000], [15001, 16000]]);
});


test("legacy evidence and manual anchors preserve source points and canonical endpoint identity through projection", async () => {
  const { buildSubviewAnchorEndpointKey } = await import("../subview-anchor-state.js");
  const { memberAnchorEndpointKey } = await import("../subview-fragment-model.js");
  const state = stateFor("2-contig");
  state.assembly.subview.flippedCtgs = [{ slot: "top", contigId: 30 }];
  const top = buildSubviewAnchorEndpointKey({ role: "support", contigId: 30, datasetId: 22 });
  const bottom = buildSubviewAnchorEndpointKey({ role: "primary", contigId: 2, datasetId: 11 });
  state.assembly.subview.manualAnchors = [{ manualAnchorId: "keep", coordinateSpace: "assembly",
    endpointA: { endpointKey: top, contigId: 30, cutBp: 500, lengthBp: 16000, sourceRole: "support" },
    endpointB: { endpointKey: bottom, contigId: 2, cutBp: 1000, lengthBp: 16000, sourceRole: "primary" } }];
  state.assembly.subview.activeAnchors = [{ hitKey: "evidence-1", edge: "left" }];
  const projected = project(state);
  const member = projected.members.find((m) => m.assemblyCtgId === 30);
  const manual = projected.manualAnchors[0];
  const endpoint = [manual.endpointA, manual.endpointB].find((e) => e.contigId === 30);
  assert.equal(endpoint.endpointKey, memberAnchorEndpointKey(member));
  assert.equal(endpoint.cutBp, 500, "assembly-space GRT/manual coordinates must not be flipped twice");
  assert.equal(projected.activeAnchors[0].descriptor.top.endpointKey, memberAnchorEndpointKey(member));
});

for (const mode of ["2-contig", "track-pair", "composition"]) test(`${mode}: Main owns synchronized deletion; local undo-split restores only local bases and survives reload`, async () => {
  const { createSubviewFragmentController } = await import("../subview-fragment-controller.js");
  const { restoreSubviewHistoryRollback } = await import("../subview-history-state.js");
  const store = createStore(stateFor(mode)), api = runtime(store);
  assert.equal(await api.run(contextFor(mode), { action: "delete" }), true);
  let assembly = store.getState().assembly;
  assert.equal(resolveCurrentSubviewHistory(assembly).record.past.length, 1, "the local deletion is one Local View history entry");
  assert.equal(assembly.subview.summary.deletedFragments.length, 1);
  const beforeMain = JSON.stringify([assembly.chrCtgs, assembly.deletedCtgs, assembly.mainViewHistory]);
  const left = assembly.subview.summary.members.find((m) => m.source.role === "primary");
  const controller = createSubviewFragmentController({ projectHistorical: project, rerenderSubviewPanel() {}, persistProjectAssemblyViewStateFromStore: async () => {} });
  assert.equal(await controller.mergeLocalFragment(host, store, { entityKey: left.entityKey }, "right"), true);
  assembly = store.getState().assembly;
  assert.equal(assembly.subview.summary.members.find((m) => m.source.role === "primary").lengthBp, 5000);
  assert.equal(JSON.stringify([assembly.chrCtgs, assembly.deletedCtgs, assembly.mainViewHistory]), beforeMain);
  const reloaded = reconcileLocalSubviewWithMain(JSON.parse(JSON.stringify(assembly)));
  assert.equal(reloaded.subview.summary.members.find((m) => m.source.role === "primary").lengthBp, 5000);
  const undone = rollbackSubviewHistory(reloaded);
  assert.equal(undone.changed, true);
  assert.equal(undone.assembly.subview.summary.members.find((m) => m.source.role === "primary").lengthBp, 1000);
  const redone = restoreSubviewHistoryRollback(undone.assembly);
  assert.equal(redone.changed, true);
  assert.equal(redone.assembly.subview.summary.members.find((m) => m.source.role === "primary").lengthBp, 5000);
  assert.equal(JSON.stringify([redone.assembly.chrCtgs, redone.assembly.deletedCtgs, redone.assembly.mainViewHistory]), beforeMain);
});

test("synchronized deletion preserves previous local actions and recovery metadata through local rollback", async () => {
  const { createSubviewFragmentController, resolveLocalFragmentMenu } = await import("../subview-fragment-controller.js");
  const store = createStore(stateFor("composition"));
  const local = createSubviewFragmentController({ projectHistorical: project, rerenderSubviewPanel() {}, persistProjectAssemblyViewStateFromStore: async () => {} });
  const support = store.getState().assembly.subview.summary.members.find((m) => m.source.role === "support");
  assert.equal(await local.flipLocalFragment(host, store, { entityKey: support.entityKey }), true);
  const depth = resolveCurrentSubviewHistory(store.getState().assembly).record.past.length;
  const api = runtime(store);
  assert.equal(await api.run(contextFor("composition"), { action: "delete" }), true);
  assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, depth + 1);
  const beforeMain = JSON.stringify(store.getState().assembly.chrCtgs);
  const rollback = rollbackSubviewHistory(store.getState().assembly);
  assert.equal(rollback.changed, true);
  store.setState({ assembly: rollback.assembly });
  assert.equal(store.getState().assembly.subview.summary.members.find((m) => m.entityKey === support.entityKey).flipped, true, "undo delete leaves the earlier local flip intact");
  assert.equal(JSON.stringify(store.getState().assembly.chrCtgs), beforeMain);
  const recovered = store.getState().assembly.subview.summary.members.find((m) => m.source.role === "primary");
  assert.equal(recovered.lengthBp, 16000, "local history restores deleted bases without restoring Main entities");
  assert.ok(recovered.localFragment.archivedCtgIds.length > 0);
  assert.equal(resolveLocalFragmentMenu(store.getState(), host, { entityKey: recovered.entityKey }).canSync, false);
  const earlier = rollbackSubviewHistory(store.getState().assembly);
  assert.equal(earlier.changed, true);
  assert.equal(earlier.assembly.subview.summary.members.find((m) => m.entityKey === support.entityKey).flipped, false);
});

for (const mode of ["2-contig", "track-pair", "composition"]) for (const full of [false, true]) {
  test(`${mode}: synchronized ${full ? "whole ctg" : "anchor interval"} deletion survives persisted reload with independently undoable source coverage`, async () => {
    const { collectSubviewAnchorScene } = await import("../subview-anchor-objects.js");
    const state = stateFor(mode), store = createStore(state);
    const scene = { querySelectorAll() { return [...renderAssemblyPage(store.getState()).matchAll(/<[^>]*data-subview-anchor-kind=[^>]*>/g)]
      .map(([tag]) => { const attrs = Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map((m) => [m[1], m[2].replaceAll("&amp;", "&").replaceAll("&quot;", '"')]));
        return { getAttribute: (key) => attrs[key] ?? null }; }); } };
    const edges = collectSubviewAnchorScene(scene).filter((edge) => edge.kind === "evidence" && [500,1800].includes(edge.descriptor.top.cutBp));
    assert.equal(edges.length, 2);
    state.assembly.subview.activeAnchors = edges.map((edge) => ({ hitKey: edge.node.getAttribute("data-subview-anchor-hit-key"),
      edge: edge.node.getAttribute("data-subview-anchor-edge"), descriptor: edge.descriptor }));
    const original = project(store.getState());
    const api = runtime(store);
    assert.equal(await api.run(contextFor(mode, full ? 1 : 500, full ? 16000 : 1799), { action: "delete" }), true);
    const after = store.getState().assembly, main = JSON.stringify([after.chrCtgs, after.deletedCtgs, after.mainViewHistory]);
    assert.equal(resolveCurrentSubviewHistory(after).record.past.length, 1);
    const saved = JSON.parse(JSON.stringify(api.persisted.at(-1)));
    // Native history status is loaded afresh; inFlight is not a persisted field.
    saved.mainViewHistory = after.mainViewHistory;
    assert.equal(resolveCurrentSubviewHistory(saved).record.past.length, 1, "the final persisted history includes the local entry");
    const reopened = reconcileLocalSubviewWithMain(activateSubviewCompositionHistory(saved).assembly);
    assert.equal(reopened.subview.summary.members.filter((m) => m.source.role === "primary").reduce((n,m) => n+m.lengthBp,0), full ? 0 : 14700);
    const undo = rollbackSubviewHistory(reopened);
    assert.equal(undo.changed, true);
    const recovered = reconcileLocalSubviewWithMain(undo.assembly);
    assert.equal(JSON.stringify([recovered.chrCtgs,recovered.deletedCtgs,recovered.mainViewHistory]), main);
    const member = recovered.subview.summary.members.find((m) => m.source.role === "primary");
    assert.equal(member.lengthBp, 16000);
    assert.deepEqual([member.localFragment.sourceStart, member.localFragment.sourceEnd], [1,16000]);
    assert.ok(member.localFragment.archivedCtgIds.length);
    store.setState({ assembly: recovered });
    const active = collectSubviewAnchorScene(scene).filter((edge) => edge.node.getAttribute("data-subview-anchor-active") === "1");
    assert.equal(active.length, 2);
    assert.deepEqual(active.map((edge) => edge.descriptor.bottom.cutBp).sort((a,b)=>a-b),
      original.activeAnchors.map((a)=>a.descriptor.bottom.cutBp).sort((a,b)=>a-b));
    const tags = [...renderAssemblyPage(store.getState()).matchAll(/<rect[^>]*class="subview-fragment-hit-zone"[^>]*>/g)].map(([tag]) => tag);
    assert.ok(tags.some((tag) => tag.includes('data-subview-fragment-start="500"') && tag.includes('data-subview-fragment-end="1799"')),
      "undo restores anchor hit ranges rather than only red lines");
    const redo = restoreSubviewHistoryRollback(recovered);
    assert.equal(redo.changed, true);
    assert.equal(redo.assembly.subview.summary.members.filter((m) => m.source.role === "primary").reduce((n,m) => n+m.lengthBp,0), full ? 0 : 14700);
    assert.equal(JSON.stringify([redo.assembly.chrCtgs,redo.assembly.deletedCtgs,redo.assembly.mainViewHistory]), main);
    // A distinct future Main deletion must not be implicitly restored just
    // because this object's snapshot can recover the earlier archived ID.
    if (!full) {
      const victim = recovered.chrCtgs.at(-1);
      const future = reconcileLocalSubviewWithMain({ ...recovered,
        chrCtgs: recovered.chrCtgs.filter((ctg) => ctg !== victim),
        deletedCtgs: [...recovered.deletedCtgs, { ...victim, deletedCtgRecordId: 999,
          sourceGroupKey: victim.sourceFragment.groupKey, sourceRange: victim.sourceFragment }],
      });
      assert.equal(future.subview.summary.members.find((m) => m.source.role === "primary").lengthBp, 1799);
    }
  });
}

for (const localFirst of [false, true]) test(`Main deletion undo/redo and local undo remain independent, local-first=${localFirst}`, async () => {
  const { runMainViewHistoryControlAction } = await import("../main-view-history-runtime.js");
  const state = stateFor("composition"), parents = state.assembly.chrCtgs;
  const store = createStore(state), api = runtime(store);
  assert.equal(await api.run(contextFor("composition"), { action: "delete" }), true);
  const deletedMain = store.getState().assembly.chrCtgs, archives = store.getState().assembly.deletedCtgs;
  if (localFirst) store.setState({ assembly: rollbackSubviewHistory(store.getState().assembly).assembly });
  const localHistory = () => { const r = resolveCurrentSubviewHistory(store.getState().assembly).record;
    return [r.past.length, r.forward.length]; };
  const expectedHistory = localHistory();
  const localRanges = () => store.getState().assembly.subview.summary.members.filter((m) => m.source.role === "primary")
    .map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd]);
  const ranges = localRanges();
  for (const action of ["undo", "redo"]) {
    const current = store.getState().assembly;
    store.setState({ assembly: { ...current, mainViewHistory: { chrName: "Chr01", canUndo: true, canRedo: true,
      undoOperation: { kind: "delete-local-fragment", targetCount: 1 }, redoOperation: { kind: "delete-local-fragment", targetCount: 1 } } } });
    assert.equal(await runMainViewHistoryControlAction(host, store, action, {
      executeMainViewHistoryAction: async () => ({ changed: true, affectedCtgIds: [2,701,702,703],
        operation: { kind: "delete-local-fragment", targetCount: 1 }, status: { chrName: "Chr01" } }),
      loadAssemblyView: async () => { const assembly = store.getState().assembly;
        store.setState({ assembly: reconcileLocalSubviewWithMain({ ...assembly,
          chrCtgs: action === "undo" ? parents : deletedMain, deletedCtgs: action === "undo" ? [] : archives }) }); },
      mapAssemblyError: ({ error }) => ({ userMessage: error.message }), rerender() {}, refreshSubviewPairwiseEvidence() {},
    }), true);
    assert.deepEqual(localHistory(), expectedHistory);
    assert.deepEqual(localRanges(), ranges);
  }
  if (!localFirst) {
    store.setState({ assembly: rollbackSubviewHistory(store.getState().assembly).assembly });
    assert.deepEqual(localRanges(), [[1,16000]]);
  }
  assert.deepEqual(store.getState().assembly.chrCtgs, deletedMain);
});

for (const orient of ["+", "-"]) test(`multiple ${orient} anchor cuts survive production reload as one local and one main history entry`, async () => {
  const state = stateFor("composition", orient);
  const store = createStore(state), api = runtime(store);
  assert.equal(await api.run({ entityKey: "assembly:2" }, { action: "split", cuts: [4000, 8000, 12000] }), true);
  const after = store.getState().assembly;
  assert.equal(api.historyCount(), 1);
  assert.equal(after.chrCtgs.length, 4);
  assert.equal(resolveCurrentSubviewHistory(after).record.past.length, 1);
  const ranges = after.subview.summary.members.filter(m => m.source.role === "primary")
    .map(m => memberSourceInterval(m)).sort((a,b) => a.sourceStart-b.sourceStart);
  assert.deepEqual(ranges.map(r => [r.sourceStart,r.sourceEnd]), [[1,4000],[4001,8000],[8001,12000],[12001,16000]]);
  const undone = rollbackSubviewHistory(JSON.parse(JSON.stringify(after)));
  assert.equal(undone.changed, true);
  assert.equal(undone.assembly.chrCtgs.length, 4);
  assert.equal(undone.assembly.mainViewHistory.appliedOperationCount, 1);
  const redone = restoreSubviewHistoryRollback(undone.assembly);
  assert.equal(redone.changed, true);
  assert.deepEqual(redone.assembly.subview.summary.members, after.subview.summary.members);
});
