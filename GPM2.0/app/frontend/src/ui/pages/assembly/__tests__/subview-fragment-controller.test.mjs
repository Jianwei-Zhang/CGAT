import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { createStore, __testBuildAssemblyContextMenuItems } from "./tabs-semantics-harness.mjs";
import { createSubviewFragmentController, resolveLocalFragmentMenu } from "../subview-fragment-controller.js";
import { rollbackSubviewHistory, restoreSubviewHistoryRollback, resolveCurrentSubviewHistory } from "../subview-history-state.js";
import { memberSourceInterval, mergeLocalMember, splitLocalMember, filterLocalAnchorCuts } from "../subview-fragment-model.js";

const host = {};
function controller(overrides = {}) {
  const persisted = [];
  const runtime = createSubviewFragmentController({
    openManualContigSplit: async (_host, model, options) => options.commit({ cutAfter: Math.floor((model.sourceStart + model.sourceEnd) / 2) }),
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {},
    persistProjectAssemblyViewStateFromStore: async (_host, store) => { persisted.push(JSON.parse(JSON.stringify(store.getState()))); },
    ...overrides,
  });
  return { ...runtime, persisted };
}
for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`local anchor fragment flip and deletion are interval-scoped with independent history from ${mode}`, async () => {
    const state = createIdentityRenderState(mode);
    const original = JSON.parse(JSON.stringify(state));
    const store = createStore(state), runtime = controller();
    const context = { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000 };
    assert.equal(await runtime.flipLocalFragment(host, store, context), true);
    const members = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
    assert.equal(members.length, 3);
    assert.deepEqual(members.map((m) => m.flipped), [false, true, false]);
    assert.deepEqual(members.map((m) => m.lengthBp), [1000, 2000, 13000]);
    assert.deepEqual(store.getState().assembly.chrCtgs, original.assembly.chrCtgs);
    assert.deepEqual(store.getState().assembly.supportChrCtgs, original.assembly.supportChrCtgs);
    assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 1);
    const undone = rollbackSubviewHistory(JSON.parse(JSON.stringify(store.getState().assembly)));
    assert.equal(undone.changed, true);
    assert.equal(undone.assembly.subview.summary.mode, original.assembly.subview.summary.mode);
    const redone = restoreSubviewHistoryRollback(undone.assembly);
    assert.equal(redone.changed, true);
    store.setState({ assembly: redone.assembly });
    const middle = members[1];
    assert.equal(await runtime.deleteLocalFragment(host, store, { entityKey: middle.entityKey }), true);
    const surviving = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
    assert.deepEqual(surviving.map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd]), [[1, 1000], [3001, 16000]]);
    assert.equal(runtime.persisted.length, 2);
    assert.equal(store.getState().assembly.subviewTrackView.fullRange, false);
  });
}

test("manual split and local merge remain local, one history entry per edit", async () => {
  const store = createStore(createIdentityRenderState("composition")), runtime = controller();
  const main = store.getState().assembly.chrCtgs;
  assert.equal(await runtime.openLocalContigSplit(host, store, { entityKey: "assembly:30" }), true);
  const split = store.getState().assembly.subview.summary.members.filter((m) => m.assemblyCtgId === 30);
  assert.equal(split.length, 2);
  assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 1);
  assert.equal(await runtime.mergeLocalFragment(host, store, { entityKey: split[0].entityKey }, "right"), true);
  const joined = store.getState().assembly.subview.summary.members.find((m) => m.assemblyCtgId === 30);
  assert.equal(joined.lengthBp, 16000);
  assert.deepEqual(filterLocalAnchorCuts(joined, [8001]), []);
  assert.equal(store.getState().assembly.chrCtgs, main);
  assert.equal(resolveCurrentSubviewHistory(store.getState().assembly).record.past.length, 2);
});

test("split dialog cancel or stale view does not change state or persist a partial edit", async () => {
  const store = createStore(createIdentityRenderState("composition"));
  const before = store.getState();
  const canceled = controller({ openManualContigSplit: async () => false });
  assert.equal(await canceled.openLocalContigSplit(host, store, { entityKey: "assembly:30" }), false);
  assert.equal(store.getState(), before);
  assert.equal(canceled.persisted.length, 0);
  const stale = controller({ openManualContigSplit: async (_host, _model, options) => {
    store.setState({ assembly: { ...store.getState().assembly, subview: { ...store.getState().assembly.subview } } });
    assert.equal(options.isCurrent(), false);
    await assert.rejects(options.commit({ cutAfter: 8000 }), /变化|changed/);
    return false;
  } });
  assert.equal(await stale.openLocalContigSplit(host, store, { entityKey: "assembly:30" }), false);
  assert.equal(stale.persisted.length, 0);
});

test("local menu has ordered scoped split/delete and local-only merge, with no redundant remove or anchor actions", () => {
  const state = createIdentityRenderState("composition"), store = createStore(state);
  const context = { assemblyCtgId: 30, trackRole: "support", slot: "top", start: 1001, end: 3000,
    compositionEntityKey: "assembly:30", fragmentKey: "30:1001-3000" };
  const items = __testBuildAssemblyContextMenuItems({ store, host,
    subviewFragmentContext: context,
    subviewTrackPairContext: { ...context },
    subviewHitContext: { hitKey: "evidence-1" },
  });
  assert.deepEqual(items.map((item) => item.label), ["加入 Final Path", "移至另一轨", "翻转 contig", "分割当前片段", "合并局部片段", "删除当前片段"]);
  assert.deepEqual(items[3].children.map((item) => item.label), ["仅在当前局部视图分割…", "分割并同步主视图…"]);
  assert.deepEqual(items[4].children.map((item) => item.label), ["与左侧片段合并", "与右侧片段合并"]);
  assert.equal(items[3].children[1].disabled, true);
  assert.equal(items[5].children[1].disabled, true);
  const model = resolveLocalFragmentMenu(state, host, context);
  assert.equal(model.left, true); assert.equal(model.right, true);
});
