import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createAssemblyViewportController } from "../viewport-runtime.js";
import { createSubviewFragmentController } from "../subview-fragment-controller.js";
import { projectRenderedSubviewToComposition } from "../subview-composition-controller.js";
import { rollbackSubviewHistory, restoreSubviewHistoryRollback } from "../subview-history-state.js";

const attrs = (tag) => Object.fromEntries([...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
function harness(mode) {
  let state = createIdentityRenderState(mode), current;
  state.assembly.subviewTrackView = { ...state.assembly.subviewTrackView,
    fullRange: false, allowSubViewportScale: true, visibleSpanBp: 4000 };
  if (mode === "composition") state.assembly.subviewCompositionViewport = { bpPerPx: 4, leftBp: 0, topPx: 0 };
  const anchorKey = renderAssemblyPage(state).match(/data-subview-anchor-hit-key="([^"]+)"/)?.[1];
  assert.ok(anchorKey);
  state.assembly.subview.activeAnchors = [{ hitKey: anchorKey, edge: "left" }, { hitKey: anchorKey, edge: "right" }];
  const store = { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } };
  const session = { measuredTrackViewportPxByRole: { primary: 1200, subview: 1200, finalPath: 1200 },
    pendingSubviewViewportAnchorBp: null, pendingPrimaryViewportAnchorBp: null };
  const retired = [], persisted = [];
  const host = { querySelector: (selector) => selector.includes("subview-track-scroll") ? current.scroll : null,
    querySelectorAll: (selector) => selector === ".assembly-track-scroll[data-track-role]" ? [current.scroll]
      : selector.includes("data-subview-anchor-kind") ? current.anchors
      : selector === "[data-subview-track-slot][data-subview-contig-id][data-subview-rect-x]" ? current.rects : [] };
  const viewport = createAssemblyViewportController({ session, rerender() {}, persistProjectAssemblyViewStateFromStore() {} });
  function render() {
    if (current) { current.scroll.isConnected = false; current.scroll.scrollLeft = 0; retired.push(current.scroll); }
    const html = renderAssemblyPage(state);
    const data = attrs(html.match(/<div[^>]*class="assembly-track-scroll subview-track-scroll"[^>]*>/)[0]);
    const dataset = Object.fromEntries(Object.entries(data).filter(([key]) => key.startsWith("data-"))
      .map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase()), value]));
    const listeners = [];
    const scroll = { dataset, clientWidth: 1200, scrollLeft: 0, isConnected: true,
      addEventListener: (type, fn) => { if (type === "scroll") listeners.push(fn); },
      emit: () => listeners.forEach((fn) => fn()) };
    const rects = [...html.matchAll(/<[^>]+data-subview-rect-x=[^>]+>/g)].map(([tag]) => {
      const data = attrs(tag); return { getAttribute: (key) => data[key] ?? null };
    });
    const fragments = [...html.matchAll(/<rect\b[^>]*class="subview-fragment-hit-zone"[^>]*>/g)].map(([tag]) => attrs(tag));
    const anchors = [...html.matchAll(/<[^>]*data-subview-anchor-kind=[^>]*>/g)].map(([tag]) => {
      const data = attrs(tag); return { getAttribute: (key) => data[key]?.replaceAll("&amp;", "&") ?? null };
    });
    current = { scroll, rects, fragments, anchors };
    viewport.bindTrackScrollSync(host, store, { scope: "subview", schedulePersistAssemblyScrollState() {} });
  }
  const controller = createSubviewFragmentController({
    projectHistorical: (s) => projectRenderedSubviewToComposition(s, renderAssemblyPage(s)),
    openAnchorContigSplit: async (_host, model, options) => options.commit({ cuts: model.cuts }),
    rerenderSubviewPanel: render, refreshSubviewPairwiseEvidence() {},
    persistProjectAssemblyViewStateFromStore: async () => persisted.push(JSON.parse(JSON.stringify(state.assembly))),
  });
  render();
  return { store, host, controller, render, retired, persisted, session,
    get scroll() { return current.scroll; },
    get fragmentContext() {
      const node = current.fragments.find((f) => f["data-subview-fragment-contig-id"] === "30"
        && Number(f["data-subview-fragment-start"]) > 1 && Number(f["data-subview-fragment-end"]) < 16000);
      assert.ok(node, "real anchor-cut middle fragment exists");
      return { assemblyCtgId: 30, trackRole: "support", slot: "top",
        start: Number(node["data-subview-fragment-start"]), end: Number(node["data-subview-fragment-end"]),
        coordinateSpace: node["data-subview-fragment-coordinate-space"] };
    },
    worldLeft() { const s = current.scroll; return Number(s.dataset.subviewWindowStartBp || 0)
      + (s.scrollLeft + Number(s.dataset.subviewViewboxMinX || 0)) * Number(s.dataset.subviewDomainSpanBp) / Number(s.dataset.subviewInnerWidth); },
  };
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  for (const action of ["deleteLocalFragment", "flipLocalFragment", "openLocalContigSplit", "moveLocalFragmentToOtherLane", "mergeLocalFragment"]) {
    test(`${mode} ${action} and undo/redo ignore retired-panel scroll events`, async () => {
      const h = harness(mode);
      h.scroll.scrollLeft = 800; h.scroll.emit();
      const left = h.worldLeft();
      assert.ok(left > 0);
      let context = h.fragmentContext;
      if (action === "mergeLocalFragment") {
        assert.equal(await h.controller.openLocalContigSplit(h.host, h.store, context), true);
        const piece = h.store.getState().assembly.subview.summary.members.find((m) =>
          m.assemblyCtgId === 30 && m.localFragment?.sourceStart === context.start);
        assert.ok(piece);
        context = { entityKey: piece.entityKey };
      }
      assert.equal(await h.controller[action](h.host, h.store, context, "right"), true);
      assert.ok(Math.abs(h.worldLeft() - left) < 1, "edit keeps the visible source position");
      const after = JSON.parse(JSON.stringify(h.store.getState().assembly));
      for (const scroll of h.retired) scroll.emit();
      assert.deepEqual(h.store.getState().assembly.subviewCompositionViewport, after.subviewCompositionViewport,
        "queued reset from removed panel must not overwrite the new world viewport");
      h.render();
      assert.ok(Math.abs(h.worldLeft() - left) < 1, "later evidence refresh must not jump left");
      for (const move of [rollbackSubviewHistory, restoreSubviewHistoryRollback]) {
        const result = move(h.store.getState().assembly);
        assert.equal(result.changed, true);
        h.store.setState({ assembly: result.assembly }); h.render();
        assert.ok(Math.abs(h.worldLeft() - left) < 1, "undo/redo keeps the visible source position");
        const beforeLate = JSON.parse(JSON.stringify(h.store.getState().assembly));
        for (const scroll of h.retired) scroll.emit();
        assert.deepEqual(h.store.getState().assembly.subviewTrackScrollState, beforeLate.subviewTrackScrollState);
        assert.deepEqual(h.store.getState().assembly.subviewCompositionViewport, beforeLate.subviewCompositionViewport);
      }
      h.scroll.scrollLeft += 25; h.scroll.emit();
      assert.equal(h.session.lastSubviewScrollLeft, h.scroll.scrollLeft, "live scrolling still works");
    });
  }
}

for (const [scope, role, field] of [["main", "primary", "trackScrollState"],
  ["subview", "subview", "subviewTrackScrollState"], ["final-path", "final-path", "finalPathTrackScrollState"]]) {
  test(`${scope} rejects detached and old-context scrolls but preserves live scrolling after rebind`, () => {
    let state = createIdentityRenderState("composition"), active;
    state.session = { workspacePath: "D:/one", projectId: 7 };
    const store = { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } };
    const session = { measuredTrackViewportPxByRole: { primary: 1200, subview: 1200, finalPath: 1200 },
      pendingPrimaryViewportAnchorBp: null, pendingSubviewViewportAnchorBp: null };
    let persists = 0;
    const deps = { scope, schedulePersistAssemblyScrollState() { persists++; } };
    function element() {
      const listeners = new Set();
      return { isConnected: true, scrollLeft: 0, clientWidth: 1200,
        dataset: { trackRole: role, subviewDomainSpanBp: "16000", subviewInnerWidth: "800", subviewViewboxMinX: "0" },
        addEventListener: (type, fn) => { if (type === "scroll") listeners.add(fn); },
        removeEventListener: (type, fn) => { if (type === "scroll") listeners.delete(fn); },
        emit: () => [...listeners].forEach((fn) => fn()), listeners };
    }
    const host = { querySelector: (selector) => selector.includes(scope === "final-path" ? "final-path" : role === "primary" ? "primary" : "subview") ? active : null,
      querySelectorAll: () => scope === "final-path" ? [] : [active] };
    const controller = createAssemblyViewportController({ session, rerender() {}, persistProjectAssemblyViewStateFromStore() {} });
    active = element(); controller.bindTrackScrollSync(host, store, deps);
    active.scrollLeft = 600; active.emit();
    assert.equal(state.assembly[field].scrollLeft, 600);
    const old = active; old.isConnected = false; old.scrollLeft = 0;
    active = element(); controller.bindTrackScrollSync(host, store, deps);
    const saved = JSON.stringify(state), calls = persists;
    old.emit();
    assert.equal(JSON.stringify(state), saved); assert.equal(persists, calls);
    assert.equal(active.scrollLeft, 600);
    controller.bindTrackScrollSync(host, store, deps);
    assert.equal(active.listeners.size, 1, "rebinding removes obsolete handlers");
    for (const changedContext of [{ ...state.session, workspacePath: "D:/two" }, { ...state.session, projectId: 8 }]) {
      const previous = state.session;
      state = { ...state, session: changedContext };
      const before = JSON.stringify(state);
      active.scrollLeft += 50; active.emit();
      assert.equal(JSON.stringify(state), before, "old context cannot write into new workspace/project");
      state = { ...state, session: previous };
    }
    const previousChr = state.assembly.selectedChrName;
    state = { ...state, assembly: { ...state.assembly, selectedChrName: "Chr99" } };
    const beforeChr = JSON.stringify(state);
    active.scrollLeft += 50; active.emit();
    assert.equal(JSON.stringify(state), beforeChr);
    state = { ...state, assembly: { ...state.assembly, selectedChrName: previousChr } };
    controller.bindTrackScrollSync(host, store, deps);
    active.scrollLeft = 725; active.emit();
    assert.equal(state.assembly[field].scrollLeft, 725);
  });
}

test("scrolling after legacy undo remains the viewport when redoing the local edit", async () => {
  const h = harness("2-contig");
  h.scroll.scrollLeft = 800; h.scroll.emit();
  await h.controller.deleteLocalFragment(h.host, h.store, h.fragmentContext);
  h.store.setState({ assembly: rollbackSubviewHistory(h.store.getState().assembly).assembly }); h.render();
  h.scroll.scrollLeft += 150; h.scroll.emit();
  const left = h.worldLeft();
  h.store.setState({ assembly: restoreSubviewHistoryRollback(h.store.getState().assembly).assembly }); h.render();
  assert.ok(Math.abs(h.worldLeft() - left) < 1);
});
