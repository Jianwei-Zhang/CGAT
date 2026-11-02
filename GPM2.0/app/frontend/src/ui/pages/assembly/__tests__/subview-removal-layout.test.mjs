import { test, assert, createStore, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { createSubviewInteractionController } from "../subview-interaction-controller.js";
import { projectRenderedSubviewToComposition, projectCurrentSubviewToComposition, createSubviewCompositionController } from "../subview-composition-controller.js";
import { rollbackSubviewHistory, resolveCurrentSubviewHistory } from "../subview-history-state.js";
import { buildSubviewClearProjection } from "../subview-clear-state.js";
import { deleteSelectedSubviewTrackPairCtgs } from "../editor-actions-runtime.js";
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
  querySelectorAll: (selector) => selector === "[data-subview-track-slot][data-subview-contig-id][data-subview-rect-x]"
    ? [...view.html.matchAll(/<g\b[^>]*data-subview-contig-id="[^>]*>/g)].map(([tag]) => ({
      getAttribute: (name) => attr(tag, name) ?? null,
    })) : [],
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
  assert.equal(zh.subview.guide, "Ctrl/Cmd 选择两个 Contig 或两个轨道进行比较；通过「工具」添加 Contig 进入组合模式。");
  assert.match(en.subview.guide, /Ctrl\/Cmd.*track labels.*Tools.*composition mode/);
});

for (const mode of ["track-pair", "composition"]) {
  for (const fullRange of [true, false]) {
    test(`box-selection Delete in ${mode}, fullRange=${fullRange} preserves remaining geometry`, async () => {
      const state = mode === "track-pair" ? trackPairState(20000, fullRange)
        : createIdentityRenderState("composition");
      let selected;
      if (mode === "composition") {
        const members = state.assembly.subview.summary.members;
        const base = members.find((entry) => entry.assemblyCtgId === 30);
        state.assembly.subview = applySubviewComposition(state.assembly.subview, {
          members: [...members, ...[31, 32].map((id, index) => ({ ...base,
            entityKey: `assembly:${id}`, assemblyCtgId: id, xBp: (index + 2) * 64000,
          }))],
        });
        state.assembly.subviewTrackView = { ...state.assembly.subviewTrackView,
          fullRange, visibleSpanBp: fullRange ? 900000 : 10000 };
        selected = [31, 32].map((contigId) => ({ trackRole: "support", contigId,
          compositionEntityKey: `assembly:${contigId}`, slot: "top" }));
      } else {
        selected = [31, 32].map((contigId) => ({ trackRole: "support", contigId, slot: "top" }));
      }
      const before = scene(state, fullRange ? 0 : 130);
      if (mode === "composition") state.assembly.subviewCompositionViewport = {
        bpPerPx: before.bpPerPx, leftBp: before.leftBp, topPx: 0,
      };
      const store = createStore(state);
      await deleteSelectedSubviewTrackPairCtgs(hostFor(before), store, selected, {
        confirm: async () => true, rerender() {},
        persistProjectAssemblyViewStateFromStore: async () => {},
      });
      const after = scene(store.getState(), before.scroll.scrollLeft);
      assert.equal(store.getState().assembly.subviewTrackView.fullRange, false);
      assert.equal(after.bpPerPx, before.bpPerPx);
      assert.equal(after.leftBp, before.leftBp);
      for (const [key, mark] of before.marks) {
        if (["top:31", "top:32"].includes(key)) assert.equal(after.marks.has(key), false);
        else assert.deepEqual(after.marks.get(key), mark, key);
      }
      const undone = rollbackSubviewHistory(store.getState().assembly);
      assert.equal(undone.changed, true);
      store.setState({ assembly: undone.assembly });
      assert.deepEqual(scene(store.getState(), before.scroll.scrollLeft).marks, before.marks);
    });
  }
}

function compositionController() {
  return createSubviewCompositionController({
    session: {}, getMeasuredTrackViewportPx: () => 1200,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => {},
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {},
    anchorController: { resetScope() {} },
  });
}

function assertHorizontalGeometry(before, after, removedKeys) {
  assert.equal(after.bpPerPx, before.bpPerPx);
  assert.equal(after.leftBp, before.leftBp);
  const worldX = (view, mark) => Number(view.scroll.dataset.subviewWindowStartBp)
    + Number(mark["rect-x"]) * view.bpPerPx;
  for (const [key, mark] of before.marks) {
    if (removedKeys.includes(key)) { assert.equal(after.marks.has(key), false); continue; }
    const next = after.marks.get(key);
    assert.ok(next, key);
    assert.ok(Math.abs(worldX(before, mark) - worldX(after, next)) <= before.bpPerPx * 0.02, `${key} display start`);
    assert.ok(Math.abs(Number(mark["rect-width"]) - Number(next["rect-width"])) <= 0.02, `${key} display width`);
    assert.equal(next["world-start-bp"], mark["world-start-bp"], `${key} logical start`);
    assert.equal(next["track-ref-orient"], mark["track-ref-orient"], `${key} orientation`);
  }
}

for (const [fullRange, lengthBp] of [[true, 32], [true, 20000], [false, 20000]]) {
  for (const slot of ["top", "bottom"]) {
    for (const removedId of [30, 31, 32]) {
      test(`context deletion converting track-pair to composition preserves display gaps (${slot}, ${removedId}, overview=${fullRange}, length=${lengthBp})`, async () => {
        const state = trackPairState(lengthBp, fullRange);
        // Exercise both primary and auxiliary lanes, including middle/edge removals.
        state.assembly.chrCtgs = state.assembly.supportChrCtgs.map((ctg) => ({ ...ctg,
          assemblyCtgId: ctg.assemblyCtgId + 10, datasetId: 11,
        }));
        const before = scene(state);
        const id = slot === "top" ? removedId : removedId + 10;
        const store = createStore(state);
        const projected = projectCurrentSubviewToComposition(state, hostFor(before));
        assert.deepEqual(projectRenderedSubviewToComposition(state, before.html), projected,
          "history migration and live conversion preserve the same display geometry");
        const controller = compositionController();
        assert.equal(await controller.removeContextSubviewMember(hostFor(before), store, {
          assemblyCtgId: id, slot, trackRole: slot === "top" ? "support" : "primary",
        }), true);
        const after = scene(store.getState());
        // Persistence/normalization must retain display geometry independently of source coordinates.
        store.setState({ assembly: JSON.parse(JSON.stringify(store.getState().assembly)) });
        assertHorizontalGeometry(after, scene(store.getState()), []);
        assertHorizontalGeometry(before, after, [`${slot}:${id}`]);
        // A second deletion must retain the captured display geometry too.
        const secondId = [30, 31, 32].find((value) => value !== removedId) + (slot === "bottom" ? 10 : 0);
        assert.equal(await controller.removeContextSubviewMember(hostFor(after), store, {
          entityKey: `assembly:${secondId}`,
        }), true);
        assertHorizontalGeometry(after, scene(store.getState()), [`${slot}:${secondId}`]);
        const undo = rollbackSubviewHistory(store.getState().assembly);
        assert.equal(undo.changed, true);
        store.setState({ assembly: undo.assembly });
        assertHorizontalGeometry(after, scene(store.getState()), []);
      });
    }
  }
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  for (const locale of ["zh", "en"]) {
    test(`local track names share main-view ellipsis and overflow-only tooltip markup (${mode}, ${locale})`, () => {
      const state = createIdentityRenderState(mode);
      state.locale = locale;
      const html = scene(state).html;
      const column = html.match(/<div class="assembly-track-label-column subview-track-label-column"[^>]*>([\s\S]*?)<div\s+class="assembly-track-scroll/)[1];
      const rows = [...column.matchAll(/<div class="assembly-track-label-row[^>]*>/g)];
      assert.equal(rows.length, 2);
      for (const [tag] of rows) {
        assert.equal(attr(tag, "data-app-tooltip-overflow"), "span");
        assert.ok(attr(tag, "data-app-tooltip"));
        assert.equal(attr(tag, "aria-label"), attr(tag, "data-app-tooltip"));
        assert.ok(column.includes(`${tag}<span>`));
        assert.doesNotMatch(tag, /\stitle=/);
      }
    });
  }
}

for (const slot of ["top", "bottom"]) {
  test(`2-contig context deletion preserves the surviving ${slot} bar`, async () => {
    const state = createIdentityRenderState("2-contig");
    state.assembly.subviewTrackDragOffsets = [{ slot: "top", contigId: 30, offsetBp: -2000 }];
    const before = scene(state);
    const store = createStore(state);
    const id = slot === "top" ? 2 : 30;
    assert.equal(await compositionController().removeContextSubviewMember(hostFor(before), store, {
      assemblyCtgId: id, slot: slot === "top" ? "bottom" : "top",
      trackRole: slot === "top" ? "primary" : "support",
    }), true);
    assertHorizontalGeometry(before, scene(store.getState()), [`${slot === "top" ? "bottom" : "top"}:${id}`]);
  });
  for (const role of ["primary", "support", "ref", "phased"]) {
    test(`composition removal retains every other bar in ${slot} lane with ${role} source`, async () => {
      const state = createIdentityRenderState("composition");
      const base = state.assembly.subview.summary.members[0];
      state.assembly.subview = applySubviewComposition(state.assembly.subview, {
        members: [30, 31, 32].map((id, index) => ({ ...base, entityKey: `assembly:${id}`,
          assemblyCtgId: id, source: { ...base.source, role }, lane: slot,
          xBp: index * 20000, displayOffsetBp: index * 100, displayScale: 0.9,
        })),
      });
      const before = scene(state), store = createStore(state);
      assert.equal(await compositionController().removeContextSubviewMember(hostFor(before), store, {
        entityKey: "assembly:31",
      }), true);
      assertHorizontalGeometry(before, scene(store.getState()), [`${slot}:31`]);
    });
  }
}
