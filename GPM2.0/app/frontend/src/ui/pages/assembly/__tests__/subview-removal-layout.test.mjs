import { test, assert, createStore, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { createSubviewInteractionController } from "../subview-interaction-controller.js";
import { createSubviewCompositionController } from "../subview-composition-controller.js";
import { rollbackSubviewHistory, resolveCurrentSubviewHistory } from "../subview-history-state.js";
import { buildSubviewClearProjection } from "../subview-clear-state.js";
import { applySubviewComposition } from "../subview-composition-state.js";
import { zh, en } from "../../../i18n/messages/assembly.js";

const attr = (html, name) => html.match(new RegExp(`${name}="([^"]*)"`))?.[1];
function scene(state, scrollLeft = 0) {
  const html = renderAssemblyPage(state);
  const scrollTag = html.match(/<div\s+class="assembly-track-scroll subview-track-scroll"[^>]*>/)?.[0];
  const svg = html.match(/<svg class="assembly-track-svg subview-track-svg"[^>]*>/)?.[0];
  assert.ok(scrollTag && svg, "local graph remains rendered");
  const dataset = Object.fromEntries([
    ["subviewDomainSpanBp", "data-subview-domain-span-bp"],
    ["subviewInnerWidth", "data-subview-inner-width"],
    ["subviewWindowStartBp", "data-subview-window-start-bp"],
    ["subviewViewboxMinX", "data-subview-viewbox-min-x"],
  ].map(([key, name]) => [key, attr(scrollTag, name)]));
  const scroll = { clientWidth: 1200, scrollWidth: Math.max(1200, Number(attr(svg, "width"))), scrollLeft, dataset };
  const bpPerPx = Number(dataset.subviewDomainSpanBp) / Number(dataset.subviewInnerWidth);
  const leftBp = Number(dataset.subviewWindowStartBp)
    + (Number(dataset.subviewViewboxMinX) + scrollLeft) * bpPerPx;
  const marks = new Map();
  for (const node of html.matchAll(/<g\b[^>]*data-subview-contig-id="[^>]*>/g)) {
    const tag = node[0];
    const key = `${attr(tag, "data-subview-track-slot")}:${attr(tag, "data-subview-contig-id")}`;
    marks.set(key, Object.fromEntries(["rect-x", "rect-y", "rect-width", "track-ref-orient", "world-start-bp"]
      .map((name) => [name, attr(tag, `data-subview-${name}`)])));
  }
  return { scroll, bpPerPx, leftBp, marks, html };
}
const hostFor = (view) => ({
  querySelector: (selector) => selector === ".subview-track-scroll" ? view.scroll : null,
  querySelectorAll: () => [],
});
function interaction() {
  return createSubviewInteractionController({
    persistProjectAssemblyViewStateFromStore: async () => {},
    requestAssemblyAnchorOffsetPrompt: async () => null,
    rerenderSubviewPanel() {}, setAssemblyActionFeedback() {}, tAssembly() { return ""; },
  });
}
function trackPairState(lengthBp, fullRange) {
  const state = createIdentityRenderState("track-pair");
  const original = state.assembly.supportChrCtgs[0];
  state.assembly.supportChrCtgs = [30, 31, 32].map((id) => ({
    ...original, assemblyCtgId: id, name: `companion-${id}`, lengthBp, totalLength: lengthBp,
  }));
  state.assembly.subviewTrackView = { ...state.assembly.subviewTrackView,
    fullRange, allowSubViewportScale: true, visibleSpanBp: fullRange ? 900000 : 10000 };
  state.assembly.subview.flippedCtgs = [{ slot: "top", contigId: 31 }];
  state.assembly.subviewTrackDragOffsets = [{ slot: "top", contigId: 30, offsetBp: -lengthBp / 2 }];
  return state;
}
function assertStable(before, after, removedKey) {
  assert.equal(after.marks.has(removedKey), false);
  assert.equal(after.bpPerPx, before.bpPerPx, "rendered scale is unchanged");
  assert.equal(after.leftBp, before.leftBp, "left world coordinate is unchanged");
  for (const [key, mark] of before.marks) {
    if (key !== removedKey) assert.deepEqual(after.marks.get(key), mark, `${key} keeps its display and logical position`);
  }
}

for (const [name, lengthBp, fullRange] of [["short overview", 32, true], ["overview", 20000, true], ["zoomed", 20000, false]]) {
  for (const contigId of [30, 31, 32]) {
    test(`removing ${contigId} from track-pair ${name} keeps other ctgs, scale and viewport`, async () => {
      const store = createStore(trackPairState(lengthBp, fullRange));
      const before = scene(store.getState(), fullRange ? 0 : 130);
      const controller = interaction();
      await controller.setSubviewTrackPairCtgHidden(hostFor(before), store, { trackRole: "support", contigId });
      const removed = store.getState().assembly;
      assert.equal(removed.subviewTrackView.fullRange, false);
      assert.equal(removed.subviewTrackView.allowSubViewportScale, true);
      assert.equal(resolveCurrentSubviewHistory(removed).record.past.at(-1).operation.kind, "hide-contig");
      assertStable(before, scene(store.getState(), before.scroll.scrollLeft), `top:${contigId}`);
      const undo = rollbackSubviewHistory(removed);
      assert.equal(undo.changed, true);
      store.setState({ assembly: undo.assembly });
      assert.deepEqual(scene(store.getState(), before.scroll.scrollLeft).marks, before.marks, "undo restores the original layout");
      const cleared = buildSubviewClearProjection(store.getState().assembly);
      assert.equal(cleared.changed, true);
      assert.equal(cleared.assembly.subview.trackPairLayoutGapBp, undefined);
      assert.equal(cleared.assembly.subview.trackPairLayoutViewport, undefined);
    });
  }
}

test("explicit track-pair overview fits remaining content after removal", async () => {
  const store = createStore(trackPairState(20000, true));
  const before = scene(store.getState());
  await interaction().setSubviewTrackPairCtgHidden(hostFor(before), store, { trackRole: "support", contigId: 32 });
  const assembly = store.getState().assembly;
  store.setState({ assembly: { ...assembly,
    subviewTrackView: { ...assembly.subviewTrackView, fullRange: true },
  } });
  const fitted = scene(store.getState());
  assert.ok(fitted.bpPerPx < before.bpPerPx, "overview no longer fits the removed rightmost slot");
  assert.ok(fitted.scroll.scrollWidth <= 1201);
  assert.equal(fitted.marks.has("top:32"), false);
});

for (const xBp of [-48000, 64000]) {
  test(`composition removal at ${xBp} stops auto-fit and retains world positions and viewport`, async () => {
    const state = createIdentityRenderState("composition");
    const members = state.assembly.subview.summary.members;
    const edge = { ...members.find((entry) => entry.assemblyCtgId === 30),
      entityKey: "assembly:31", assemblyCtgId: 31, xBp, flipped: true };
    state.assembly.subview = applySubviewComposition(state.assembly.subview, { members: [...members, edge] });
    state.assembly.subviewTrackView = { ...state.assembly.subviewTrackView, fullRange: true, visibleSpanBp: 900000 };
    const before = scene(state);
    // Navigation mounts persist the current fitted world viewport.
    state.assembly.subviewCompositionViewport = { bpPerPx: before.bpPerPx, leftBp: before.leftBp, topPx: 0 };
    const store = createStore(state);
    const controller = createSubviewCompositionController({
      session: {}, getMeasuredTrackViewportPx: () => 1200,
      listChrViewCtgs: async () => ({ items: [] }),
      persistProjectAssemblyViewStateFromStore: async () => {},
      rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {},
      anchorController: { resetScope() {} },
    });
    assert.equal(await controller.removeContextSubviewMember(hostFor(before), store, { entityKey: edge.entityKey }), true);
    const removed = store.getState().assembly;
    assert.equal(removed.subviewTrackView.fullRange, false);
    assert.deepEqual(removed.subview.summary.members, members);
    assertStable(before, scene(store.getState()), "top:31");
    const undo = rollbackSubviewHistory(removed);
    assert.equal(undo.changed, true);
    store.setState({ assembly: undo.assembly });
    assert.deepEqual(scene(store.getState()).marks, before.marks);
    store.setState({ assembly: { ...removed,
      subviewTrackView: { ...removed.subviewTrackView, fullRange: true },
    } });
    assert.ok(scene(store.getState()).bpPerPx < before.bpPerPx, "explicit overview refits remaining composition members");
  });
}

test("Chinese and English local view guidance include pair, track and composition entry points", () => {
  assert.equal(zh.subview.guide, "Ctrl/Cmd 选择两个 ctg 或两个轨道进行比较；通过「工具」添加 ctg 进入组合模式。");
  assert.match(en.subview.guide, /Ctrl\/Cmd.*track labels.*Tools.*composition mode/);
});
