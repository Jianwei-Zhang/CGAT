import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { createStore, __testBuildAssemblyContextMenuItems, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createSubviewFragmentController, resolveLocalFragmentMenu } from "../subview-fragment-controller.js";
import { commitSubviewHistoryOperation, rollbackSubviewHistory, restoreSubviewHistoryRollback, resolveCurrentSubviewHistory } from "../subview-history-state.js";
import { memberAnchorEndpointKey, memberSourceInterval, mergeLocalMember, splitLocalMember } from "../subview-fragment-model.js";

import { reconcileLocalSubviewWithMain } from "../subview-fragment-reconcile.js";

const host = {};
function controller(overrides = {}) {
  const persisted = [];
  const runtime = createSubviewFragmentController({
    projectHistorical: (state) => projectRenderedSubviewToComposition(state, renderAssemblyPage(state)),
    openAnchorContigSplit: async (_host, model, options) => options.commit({ cuts: model.cuts }),
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {},
    persistProjectAssemblyViewStateFromStore: async (_host, store) => { persisted.push(JSON.parse(JSON.stringify(store.getState()))); },
    ...overrides,
  });
  return { ...runtime, persisted };
}
function addAnchor(state, cut = 8000) {
  const composition = projectRenderedSubviewToComposition(state, renderAssemblyPage(state));
  const member = composition.members.find((m) => m.assemblyCtgId === 30);
  const other = composition.members.find((m) => m.assemblyCtgId === 2);
  state.assembly.subview.activeAnchors = [{ hitKey: "test-anchor", edge: "left", descriptor: {
    top: { endpointKey: memberAnchorEndpointKey(member), contigId: 30, cutBp: cut+1, lengthBp: 16000, sourceRole: "support" },
    bottom: { endpointKey: memberAnchorEndpointKey(other), contigId: 2, cutBp: cut+1, lengthBp: 16000, sourceRole: "primary" },
  } }];
}
for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`local anchor hit flips the whole object while deletion is interval-scoped with independent history from ${mode}`, async () => {
    const state = createIdentityRenderState(mode);
    const original = JSON.parse(JSON.stringify(state));
    const store = createStore(state), runtime = controller();
    const context = { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000 };
    assert.equal(await runtime.flipLocalFragment(host, store, context), true);
    const members = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
    assert.equal(members.length, 1);
    assert.deepEqual(members.map((m) => m.flipped), [true]);
    assert.deepEqual(members.map((m) => m.lengthBp), [16000]);
    assert.deepEqual(store.getState().assembly.chrCtgs, original.assembly.chrCtgs);
    assert.deepEqual(store.getState().assembly.supportChrCtgs, original.assembly.supportChrCtgs);
    assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 1);
    const undone = rollbackSubviewHistory(JSON.parse(JSON.stringify(store.getState().assembly)));
    assert.equal(undone.changed, true);
    assert.equal(undone.assembly.subview.summary.mode, original.assembly.subview.summary.mode);
    const redone = restoreSubviewHistoryRollback(undone.assembly);
    assert.equal(redone.changed, true);
    store.setState({ assembly: redone.assembly });
    const middle = members[0];
    assert.equal(await runtime.deleteLocalFragment(host, store, { entityKey: middle.entityKey, start: 1001, end: 3000, coordinateSpace: "base" }), true);
    const surviving = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
    assert.deepEqual(surviving.map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd]), [[1, 1000], [3001, 16000]]);
    assert.equal(runtime.persisted.length, 2);
    assert.equal(store.getState().assembly.subviewTrackView.fullRange, false);
  });
}

test("anchor split and local merge remain local, one history entry per edit", async () => {
  const store = createStore(createIdentityRenderState("composition")), runtime = controller();
  const main = store.getState().assembly.chrCtgs;
  addAnchor(store.getState());
  assert.equal(await runtime.openLocalContigSplit(host, store, { entityKey: "assembly:30" }), true);
  const split = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
  assert.equal(split.length, 2);
  assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 1);
  assert.equal(await runtime.mergeLocalFragment(host, store, { entityKey: split[0].entityKey }, "right"), true);
  const joined = store.getState().assembly.subview.summary.members.find((m) => m.assemblyCtgId === 30);
  assert.equal(joined.lengthBp, 16000);
  assert.ok(joined.localFragment.suppressedCuts.includes(8000), "Undo Split suppresses the structural marker only");
  assert.equal(store.getState().assembly.chrCtgs, main);
  assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 2);
});

test("split dialog cancel or stale view does not change state or persist a partial edit", async () => {
  const store = createStore(createIdentityRenderState("composition"));
  addAnchor(store.getState());
  const before = store.getState();
  const canceled = controller({ openAnchorContigSplit: async () => false });
  assert.equal(await canceled.openLocalContigSplit(host, store, { entityKey: "assembly:30" }), false);
  assert.equal(store.getState(), before);
  assert.equal(canceled.persisted.length, 0);
  const stale = controller({ openAnchorContigSplit: async (_host, _model, options) => {
    store.setState({ assembly: { ...store.getState().assembly, subview: { ...store.getState().assembly.subview } } });
    assert.equal(options.isCurrent(), false);
    await assert.rejects(options.commit({ cuts: [8000] }), /变化|changed/);
    return false;
  } });
  assert.equal(await stale.openLocalContigSplit(host, store, { entityKey: "assembly:30" }), false);
  assert.equal(stale.persisted.length, 0);
});

test("local menu retains scoped deletion and two anchor split scopes, but no undo-split action", () => {
  const state = createIdentityRenderState("composition"), store = createStore(state);
  const context = { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000,
    compositionEntityKey: "assembly:30", fragmentKey: "30:1001-3000" };
  const items = __testBuildAssemblyContextMenuItems({ store, host,
    subviewFragmentContext: context,
    subviewTrackPairContext: { ...context },
    subviewHitContext: { hitKey: "evidence-1" },
  });
  assert.deepEqual(items.map((item) => item.label), ["加入 Final Path", "移至另一轨", "翻转 contig", "分割 contig（仅局部）", "分割 contig（影响主视图）", "删除当前片段"]);
  assert.deepEqual(items[5].children.map((item) => item.label), ["仅从当前局部视图删除", "同步从主视图删除…"]);
  assert.equal(items[5].children[1].disabled, true);
  assert.ok(items[3].disabled && items[4].disabled);

});

for (const mode of ["2-contig", "track-pair"]) {
  test(`${mode} undo restores legacy offsets and later native split rebinds its source backup and redo`, async () => {
    const state = createIdentityRenderState(mode);
    state.assembly.chrCtgs[0].originSourceSeqId = 700;
    const offsets = [{ slot: "bottom", contigId: 2, offsetBp: -900 }];
    state.assembly.subviewTrackDragOffsets = offsets;
    // Expose real rendered layout attributes, as the mounted Local View does.
    // An empty host has no geometry and intentionally uses zero-offset fallback.
    const html = renderAssemblyPage(state);
    const rects = [...html.matchAll(/<[^>]+data-subview-rect-x=[^>]+>/g)].map(([tag]) => ({
      getAttribute: (name) => tag.match(new RegExp(`${name}="([^"]*)"`))?.[1] ?? null,
    }));
    const renderedHost = { querySelectorAll: (selector) => selector ===
      "[data-subview-track-slot][data-subview-contig-id][data-subview-rect-x]" ? rects : [] };
    const store = createStore(state), runtime = controller();
    assert.equal(await runtime.flipLocalFragment(renderedHost, store, {
      assemblyCtgId: 2, trackRole: "primary", slot: "bottom", start: 1001, end: 3000,
    }), true);
    const undone = rollbackSubviewHistory(JSON.parse(JSON.stringify(store.getState().assembly)));
    assert.equal(undone.changed, true);
    assert.equal(undone.assembly.subview.summary.mode, mode);
    assert.deepEqual(undone.assembly.subviewTrackDragOffsets, offsets);
    assert.equal(resolveCurrentSubviewHistory(undone.assembly).record.current.kind, "legacy");
    const parent = state.assembly.chrCtgs[0];
    const children = [[701, 1, 8000], [702, 8001, 16000]].map(([id, start, end]) => ({
      ...parent, assemblyCtgId: id, totalLength: end - start + 1, lengthBp: end - start + 1,
      sourceFragment: { sourceSeqId: 700, groupKey: "manual-fragment:2", sourceStart: start, sourceEnd: end, sourceLength: 16000 },
    }));
    const rebound = reconcileLocalSubviewWithMain({ ...undone.assembly, chrCtgs: children });
    assert.equal(rebound.subview.summary.mode, "composition");
    const primary = rebound.subview.summary.members.find((m) => m.source.role === "primary");
    assert.deepEqual(primary.localFragment.parts.map((part) => part.assemblyCtgId), [701, 702]);
    assert.equal(primary.xBp, projectRenderedSubviewToComposition({ ...state, assembly: undone.assembly },
      renderAssemblyPage({ ...state, assembly: undone.assembly })).members.find((m) => m.source.role === "primary").xBp);
    const redone = restoreSubviewHistoryRollback(JSON.parse(JSON.stringify(rebound)));
    assert.equal(redone.changed, true);
    const pieces = redone.assembly.subview.summary.members.filter((m) => m.source.role === "primary");
    assert.deepEqual(pieces.map((m) => [m.localFragment.sourceStart, m.localFragment.sourceEnd, m.flipped]),
      [[1, 16000, true]]);
    assert.ok(pieces.every((m) => m.localFragment.parts.every((part) => part.assemblyCtgId !== 2)));
  });
}

test("deleted local interval survives anchor disable, persisted reopen and undo of only the anchor change", async () => {
  const state = createIdentityRenderState("composition");
  const store = createStore(state), runtime = controller();
  assert.equal(await runtime.deleteLocalFragment(host, store, {
    assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000,
  }), true);
  const deleted = store.getState().assembly;
  const changed = commitSubviewHistoryOperation(deleted, {
    nextSubview: { ...deleted.subview, activeAnchors: [{ hitKey: "evidence-1", endpoint: "start" }] },
    operation: { kind: "toggle-anchor" },
  });
  assert.equal(changed.changed, true);
  const disabled = commitSubviewHistoryOperation(changed.assembly, {
    nextSubview: { ...changed.assembly.subview, activeAnchors: [] }, operation: { kind: "toggle-anchor" },
  });
  assert.equal(disabled.changed, true);
  const reopened = JSON.parse(JSON.stringify(disabled.assembly));
  const undo = rollbackSubviewHistory(reopened);
  assert.equal(undo.changed, true);
  for (const assembly of [reopened, undo.assembly]) {
    const pieces = assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
    assert.deepEqual(pieces.map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd]),
      [[1, 1000], [3001, 16000]]);
    assert.deepEqual(assembly.chrCtgs, state.assembly.chrCtgs);
  }
});

for (const mode of ["2-contig", "track-pair", "composition"]) test(`${mode}: an anchor-only interval cannot undo a nonexistent split or mutate the view`, async () => {
  const initial = createIdentityRenderState(mode), store = createStore(initial), runtime = controller();
  const context = { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000 };
  const before = JSON.stringify(store.getState());
  const menu = resolveLocalFragmentMenu(store.getState(), host, context);
  assert.equal(menu.left, false); assert.equal(menu.right, false);
  for (const side of ["left", "right"]) assert.equal(await runtime.mergeLocalFragment(host, store, context, side), false);
  assert.equal(JSON.stringify(store.getState()), before);
  assert.equal(runtime.persisted.length, 0);
});

for (const mode of ["2-contig", "track-pair", "composition"]) test(`${mode}: controller split of an anchor interval retains visible marks through reload and repeat split`, async () => {
  const store = createStore(createIdentityRenderState(mode)), runtime = controller();
  addAnchor(store.getState(), 2000);
  const context = { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000 };
  const marks = () => (renderAssemblyPage(store.getState()).split('data-subview-panel="1"')[1].match(/data-manual-split-after="2000"/g) || []).length;
  assert.equal(await runtime.openLocalContigSplit(host, store, context), true);
  assert.equal(marks(), 2);
  store.setState(JSON.parse(JSON.stringify(store.getState())));
  assert.equal(marks(), 2);
  let first = store.getState().assembly.subview.summary.members.find((m) => m.localFragment?.sourceStart === 1);
  assert.equal(await runtime.mergeLocalFragment(host, store, { entityKey: first.entityKey }, "right"), true);
  assert.equal(marks(), 0);
  const merged = store.getState().assembly.subview.summary.members.find((m) => m.localFragment?.sourceStart === 1);
  assert.equal(await runtime.openLocalContigSplit(host, store, { entityKey: merged.entityKey }), true);
  assert.equal(marks(), 2);
});

for (const locale of ["zh", "en"]) for (const role of ["primary", "support"]) for (const fragment of [false, true]) {
  test(`Local menu hides split/unsplit for ${role}, fragment=${fragment}, ${locale}`, () => {
    const state = createIdentityRenderState("composition"); state.locale = locale;
    const id = role === "primary" ? 2 : 30, slot = role === "primary" ? "bottom" : "top";
    const context = { assemblyCtgId: id, trackRole: role, slot, compositionEntityKey: `assembly:${id}`,
      ...(fragment ? { start: 1001, end: 3000, fragmentKey: `${id}:1001-3000` } : {}) };
    const items = __testBuildAssemblyContextMenuItems({ store: createStore(state), host,
      subviewFragmentContext: fragment ? context : null, subviewTrackPairContext: context });
    assert.ok(items.length > 0);
    assert.equal(items.filter((item) => /分割|split/i.test(item.label)).length, 2);
    assert.ok(items.filter((item) => /分割|split/i.test(item.label)).every((item)=>item.disabled));
    const deletion = items.at(-1);
    assert.match(deletion.label, /删除|delete/i);
    assert.equal(deletion.children.length, 2);
    assert.equal(deletion.children[1].disabled, role !== "primary");
  });
}

test("multiple local anchors split the whole target once; a subsequent fragment flip is independent", async () => {
  const state = createIdentityRenderState("composition");
  addAnchor(state, 4000);
  const first = structuredClone(state.assembly.subview.activeAnchors[0]);
  addAnchor(state, 10000);
  first.hitKey = "first-anchor";
  state.assembly.subview.activeAnchors.push(first);
  const store = createStore(state), runtime = controller();
  assert.equal(await runtime.openLocalContigSplit(host, store, { entityKey: "assembly:30", start: 4001, end: 10000 }), true);
  const after = store.getState().assembly;
  const parts = after.subview.summary.members.filter(m => m.assemblyCtgId === 30);
  assert.deepEqual(parts.map(m => memberSourceInterval(m)).map(r => [r.sourceStart,r.sourceEnd]), [[1,4000],[4001,10000],[10001,16000]]);
  assert.equal(resolveCurrentSubviewHistory(after).record.past.length, 1);
  assert.equal(after.subview.activeAnchors.length, 2);
  assert.equal(after.subview.summary.members.filter(m => m.assemblyCtgId === 2).length, 1);
  assert.equal(await runtime.flipLocalFragment(host, store, {entityKey:parts[1].entityKey,start:1,end:100}),true);
  const flipped=store.getState().assembly.subview.summary.members.filter(m=>m.assemblyCtgId===30);
  assert.equal(flipped.length,3);assert.deepEqual(flipped.map(m=>m.flipped),[false,true,false]);
  assert.equal(store.getState().assembly.chrCtgs,state.assembly.chrCtgs);
  const undoFlip=rollbackSubviewHistory(store.getState().assembly);
  const undoSplit=rollbackSubviewHistory(undoFlip.assembly);
  assert.equal(undoSplit.changed,true);
  assert.equal(undoSplit.assembly.subview.summary.members.filter(m=>m.assemblyCtgId===30).length,1);
});
