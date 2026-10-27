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
  assert.deepEqual(items.map((item) => item.label), ["加入 Final Path", "移至另一轨", "翻转 Contig", "分割 Contig（仅局部）", "分割 Contig（影响主视图）", "删除当前片段"]);
  assert.deepEqual(items[5].children.map((item) => item.label), ["仅从当前局部视图删除", "同步从主视图删除…"]);
  assert.equal(items[5].children[1].disabled, true);
  assert.equal(items[3].disabled, false); assert.equal(items[4].disabled, true);
  assert.deepEqual(items[3].children.map((item) => item.label), ["手动分割…", "左侧分割", "右侧分割"]);
  assert.equal(items[3].children[0].disabled, false);
  assert.ok(items[3].children.slice(1).every((item) => item.disabled));

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
    const primary = rebound.subview.summary.members.filter((m) => m.source.role === "primary");
    assert.deepEqual(primary.map((member) => member.assemblyCtgId), [701, 702]);
    assert.ok(primary.every((member) => member.localFragment.parts.length === 1),
      "a Main split must create independent Local objects rather than one joined backing");
    assert.equal(primary[0].xBp, projectRenderedSubviewToComposition({ ...state, assembly: undone.assembly },
      renderAssemblyPage({ ...state, assembly: undone.assembly })).members.find((m) => m.source.role === "primary").xBp);
    assert.equal(primary[1].xBp, primary[0].xBp + 8000);
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
  test(`Local menu keeps fixed scoped split submenus without requiring anchors for ${role}, fragment=${fragment}, ${locale}`, () => {
    const state = createIdentityRenderState("composition"); state.locale = locale;
    const id = role === "primary" ? 2 : 30, slot = role === "primary" ? "bottom" : "top";
    const context = { assemblyCtgId: id, trackRole: role, slot, compositionEntityKey: `assembly:${id}`,
      ...(fragment ? { start: 1001, end: 3000, fragmentKey: `${id}:1001-3000` } : {}) };
    const items = __testBuildAssemblyContextMenuItems({ store: createStore(state), host,
      subviewFragmentContext: fragment ? context : null, subviewTrackPairContext: context });
    assert.ok(items.length > 0);
    assert.equal(items.filter((item) => /分割|split/i.test(item.label)).length, 2);
    const splitMenus = items.filter((item) => /分割|split/i.test(item.label));
    assert.equal(splitMenus[0].disabled, false);
    assert.equal(splitMenus[1].disabled, role !== "primary");
    for (const menu of splitMenus) {
      assert.deepEqual(menu.children.map((item) => item.label), locale === "zh"
        ? ["手动分割…", "左侧分割", "右侧分割"] : ["Manual split…", "Split left", "Split right"]);
      assert.ok(menu.children.slice(1).every((item) => item.disabled));
    }
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


function twoAnchors(state) {
  addAnchor(state, 4000); const first = structuredClone(state.assembly.subview.activeAnchors[0]);
  addAnchor(state, 10000); first.hitKey = "first-anchor"; state.assembly.subview.activeAnchors.push(first);
}
const selectedContext = (id = 30) => ({ entityKey: `assembly:${id}`, assemblyCtgId: id,
  slot: id === 30 ? "top" : "bottom", trackRole: id === 30 ? "support" : "primary",
  start: 4001, end: 10000, coordinateSpace: "base" });

for (const side of ["left", "right"]) test(`directional local split cuts only the selected ${side} boundary`, async () => {
  const state = createIdentityRenderState("composition"); twoAnchors(state);
  const store = createStore(state), runtime = controller(), context = selectedContext();
  const before = store.getState().assembly.chrCtgs;
  const menu = resolveLocalFragmentMenu(store.getState(), host, context);
  assert.deepEqual(menu.boundaries, { left: 4000, right: 10000 });
  assert.equal(await runtime.openLocalContigSplit(host, store, context,
    { side, expectedKey: menu.splitKey, expectedCut: menu.boundaries[side] }), true);
  const ranges = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30).map(memberSourceInterval);
  assert.deepEqual(ranges.map((range) => [range.sourceStart, range.sourceEnd]),
    side === "left" ? [[1, 4000], [4001, 16000]] : [[1, 10000], [10001, 16000]]);
  assert.equal(store.getState().assembly.chrCtgs, before);
  assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 1);
  assert.equal(runtime.persisted.length, 1);
});

test("manual local split works without anchors and cancel/stale dialogs do not mutate", async () => {
  const store = createStore(createIdentityRenderState("composition"));
  const runtime = controller({ openManualContigSplit: async (_host, model, options) => {
    assert.equal(model.sourceStart, 1); assert.equal(model.sourceEnd, 16000);
    assert.equal(options.isCurrent(), true); return options.commit({ cutAfter: 7000 });
  } });
  assert.equal(await runtime.openLocalContigSplit(host, store, { entityKey: "assembly:30" }, { mode: "manual" }), true);
  const members = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
  assert.deepEqual(members.map(memberSourceInterval).map((range) => [range.sourceStart, range.sourceEnd]), [[1, 7000], [7001, 16000]]);
  assert.equal(runtime.persisted.length, 1);
  const clean = createStore(createIdentityRenderState("composition")), before = clean.getState();
  const cancel = controller({ openManualContigSplit: async () => false });
  assert.equal(await cancel.openLocalContigSplit(host, clean, { entityKey: "assembly:30" }, { mode: "manual" }), false);
  assert.equal(clean.getState(), before); assert.equal(cancel.persisted.length, 0);
  const stale = controller({ openManualContigSplit: async (_host, _model, options) => {
    clean.setState({ assembly: { ...clean.getState().assembly, subview: { ...clean.getState().assembly.subview } } });
    assert.equal(options.isCurrent(), false);
    await assert.rejects(options.commit({ cutAfter: 7000 }), /变化|changed/); return false;
  } });
  assert.equal(await stale.openLocalContigSplit(host, clean, { entityKey: "assembly:30" }, { mode: "manual" }), false);
  assert.equal(stale.persisted.length, 0);
});

test("directional synchronization targets the whole backing member with one cut, not an implicitly isolated fragment", async () => {
  const state = createIdentityRenderState("composition"); twoAnchors(state);
  const store = createStore(state), calls = [];
  const runtime = controller({ synchronizeLocalFragment: async (_host, _store, context, operation) => {
    calls.push({ context, operation }); return true;
  } });
  const context = selectedContext(2);
  assert.equal(resolveLocalFragmentMenu(state, host, context).canSyncSplit, true);
  assert.equal(await runtime.openLocalContigSplit(host, store, context, { side: "left", synchronize: true }), true);
  assert.deepEqual(calls[0].operation, { action: "split", cuts: [4000] });
  assert.equal(calls[0].context.start, undefined); assert.equal(calls[0].context.end, undefined);
  assert.equal(runtime.persisted.length, 0);
});

test("stale or unavailable directional boundaries never edit a different interval", async () => {
  const state = createIdentityRenderState("composition"); twoAnchors(state);
  const store = createStore(state), runtime = controller(), context = selectedContext();
  const model = resolveLocalFragmentMenu(state, host, context);
  assert.equal(await runtime.openLocalContigSplit(host, store, context,
    { side: "left", expectedKey: model.splitKey, expectedCut: 5000 }), false);
  assert.equal(await runtime.openLocalContigSplit(host, store, { entityKey: "assembly:30" }, { side: "left" }), false);
  const before = store.getState();
  store.setState({ assembly: { ...before.assembly, subview: { ...before.assembly.subview, activeAnchors: [] } } });
  assert.equal(await runtime.openLocalContigSplit(host, store, context,
    { side: "left", expectedKey: model.splitKey, expectedCut: 4000 }), false);
  assert.equal(runtime.persisted.length, 0);
});


test("local split menus keep three fixed children and dispatch manual/single-side operations to the chosen scope", async () => {
  const state = createIdentityRenderState("composition"); twoAnchors(state);
  const store = createStore(state), calls = [];
  const context = { ...selectedContext(2), compositionEntityKey: "assembly:2" };
  const items = __testBuildAssemblyContextMenuItems({ store, host, subviewFragmentContext: context,
    actions: { openLocalContigSplit: async (_host, _store, target, options) => { calls.push({ target, options }); return true; } } });
  const splitMenus = items.filter((item) => item.label.startsWith("分割 Contig"));
  assert.equal(splitMenus.length, 2);
  assert.ok(splitMenus.every((item) => !item.disabled && item.run === undefined));
  for (const menu of splitMenus) {
    assert.deepEqual(menu.children.map((item) => item.label), ["手动分割…", "左侧分割", "右侧分割"]);
    assert.ok(menu.children.every((item) => !item.disabled));
  }
  await splitMenus[0].children[0].run(); await splitMenus[0].children[1].run(); await splitMenus[1].children[2].run();
  assert.equal(calls[0].options.mode, "manual"); assert.equal(calls[0].options.synchronize, false);
  assert.equal(calls[1].options.side, "left"); assert.equal(calls[1].options.expectedCut, 4000);
  assert.equal(calls[2].options.side, "right"); assert.equal(calls[2].options.expectedCut, 10000);
  assert.equal(calls[2].options.synchronize, true);
  store.setState({ assembly: { ...state.assembly, subview: { ...state.assembly.subview } } });
  assert.equal(await splitMenus[0].children[1].run(), false); assert.equal(calls.length, 3);
});


function fallbackEvidenceHost(state) {
  const composition = projectRenderedSubviewToComposition(state, renderAssemblyPage(state));
  const previewLines = [];
  const doc = { createElementNS: () => ({ attrs: {}, setAttribute(key, value) { this.attrs[key] = value; },
    remove() { this.removed = true; } }) };
  const svg = { append: (line) => previewLines.push(line) };
  const nodes = [[1001, "left"], [14000, "right"]].map(([coordinate, edge]) => {
    const attrs = { "data-subview-anchor-kind": "evidence", "data-subview-anchor-object-id": `edge:fallback:${edge}`,
      "data-subview-anchor-top-x": "10", "data-subview-anchor-bottom-x": "20",
      x1: "10", x2: "20", y1: "90", y2: "24" };
    for (const [lane, id, role] of [["top", 30, "support"], ["bottom", 2, "primary"]]) {
      const member = composition.members.find((entry) => entry.assemblyCtgId === id);
      Object.assign(attrs, { [`data-subview-anchor-${lane}-endpoint-key`]: memberAnchorEndpointKey(member),
        [`data-subview-anchor-${lane}-contig-id`]: String(id), [`data-subview-anchor-${lane}-cut-bp`]: String(coordinate),
        [`data-subview-anchor-${lane}-source-role`]: role });
    }
    return { getAttribute: (key) => attrs[key] ?? null, ownerDocument: doc, ownerSVGElement: svg };
  });
  return { previewLines, querySelectorAll: (selector) => selector === "[data-subview-anchor-kind][data-subview-anchor-object-id]" ? nodes : [] };
}

for (const synchronize of [false, true]) test(`local fallback side dispatches exactly one original alignment cut; sync=${synchronize}`, async () => {
  const state = createIdentityRenderState("composition"); addAnchor(state, 4000);
  const localHost = fallbackEvidenceHost(state), store = createStore(state), calls = [];
  const context = { ...selectedContext(2), end: 16000, compositionEntityKey: "assembly:2" };
  const model = resolveLocalFragmentMenu(state, localHost, context);
  assert.deepEqual(model.boundaries, { left: 4000, right: 14000 });
  const clearPreview = model.previewSplit(14000);
  assert.equal(localHost.previewLines.length, 1);
  assert.match(localHost.previewLines[0].attrs.class, /is-focused/);
  clearPreview(); assert.equal(localHost.previewLines[0].removed, true);
  const runtime = controller({ synchronizeLocalFragment: async (_host, _store, target, operation) => {
    calls.push({ target, operation }); return true;
  } });
  assert.equal(await runtime.openLocalContigSplit(localHost, store, context,
    { side: "right", synchronize, expectedKey: model.splitKey, expectedCut: 14000 }), true);
  if (synchronize) {
    assert.deepEqual(calls[0].operation, { action: "split", cuts: [14000] });
    assert.equal(calls[0].target.start, undefined); assert.equal(calls[0].target.end, undefined);
  } else {
    const members = store.getState().assembly.subview.summary.members.filter((member) => member.assemblyCtgId === 2);
    assert.deepEqual(members.map(memberSourceInterval).map((range) => [range.sourceStart, range.sourceEnd]), [[1, 14000], [14001, 16000]]);
    assert.equal(runtime.persisted.length, 1);
  }
});
