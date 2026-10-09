import test from "node:test";
import assert from "node:assert/strict";
import { createAssemblyViewportController } from "../viewport-runtime.js";
import { buildSubviewTrackViewportKey } from "../scroll-position-state.js";

function harness(mode = "composition") {
  const session = { measuredTrackViewportPxByRole: { primary: 1000, subview: 1000, finalPath: 1000 } };
  const handlers = new Map();
  const widths = { primary: 1000, subview: 1000, finalPath: 1000 };
  let state = { assembly: { selectedChrName: "Chr1", subview: { summary: { mode, members: [{ xBp: -5000, lengthBp: 100000 }] } },
    subviewCompositionViewport: { bpPerPx: 10, leftBp: -1000, topPx: 15 }, subviewTrackView: { visibleSpanBp: 10000 },
    trackDragOffsets: [{ ctgId: 1, offsetBp: 99 }], subviewHistoryByKey: {} } };
  let writes = 0, renders = 0;
  const store = { getState: () => state, setState(next) { writes++; state = next; } };
  const host = { closest: () => host,
    querySelector(selector) { return { clientWidth: selector.includes("subview") ? widths.subview : selector.includes("final-path") ? widths.finalPath : widths.primary }; },
    querySelectorAll() { assert.fail("must rerender before syncing stale composition DOM"); } };
  const controller = createAssemblyViewportController({ session, getWindow: () => ({ addEventListener(name, fn) { handlers.set(name, fn); } }),
    rerender() { renders++; }, persistProjectAssemblyViewStateFromStore() {} });
  controller.bindTrackViewportResize(host, store);
  return { session, widths, store, controller, host, get writes() { return writes; }, get renders() { return renders; }, resize() { handlers.get("resize")(); } };
}

test("composition resize preserves signed interval across repeated shrink/grow without edits", () => {
  const h = harness(), data = h.store.getState().assembly.trackDragOffsets;
  for (const width of [500, 1500, 1000, 700, 1000]) {
    h.widths.subview = width; h.resize();
    const a = h.store.getState().assembly, viewport = a.subviewCompositionViewport;
    assert.ok(Math.abs(viewport.bpPerPx * width - 10000) < 1e-8);
    assert.equal(viewport.leftBp, -1000); assert.equal(viewport.topPx, 15);
    assert.equal(a.subviewTrackView.visibleSpanBp, 10000);
    assert.equal(a.trackDragOffsets, data); assert.deepEqual(a.subviewHistoryByKey, {});
  }
  assert.equal(h.writes, 5); assert.equal(h.renders, 5);
  h.resize(); assert.equal(h.writes, 5); assert.equal(h.renders, 5);
});

test("composition measured-width rebind rebases before stale pixel scroll synchronization", () => {
  const h = harness(); h.session.lastSubviewViewportKey = buildSubviewTrackViewportKey(h.store.getState()); h.widths.subview = 800;
  assert.equal(h.controller.bindTrackScrollSync(h.host, h.store, { scope: "subview" }), true);
  assert.equal(h.session.measuredTrackViewportPxByRole.subview, 800);
  assert.equal(h.store.getState().assembly.subviewCompositionViewport.bpPerPx, 12.5);
  assert.equal(h.store.getState().assembly.subviewCompositionViewport.leftBp, -1000);
  assert.equal(h.writes, 1);
});

test("unmeasurable width and other local modes do not rebase composition preferences", () => {
  const h = harness(); h.widths.subview = 0; h.resize(); assert.equal(h.writes, 0);
  const other = harness("pair"); other.widths.subview = 500; other.resize();
  assert.equal(other.writes, 0); assert.equal(other.renders, 1);
  assert.equal(other.store.getState().assembly.subviewCompositionViewport.bpPerPx, 10);
});


test("composition restored scroll events retain precise world left and real movement updates it", () => {
  const h = harness(), listeners = new Map();
  let pixels = 0;
  const scroll = {
    clientWidth: 1000,
    dataset: { trackRole: "subview", subviewViewboxMinX: "-200", subviewDomainSpanBp: "100000", subviewInnerWidth: "10000" },
    get scrollLeft() { return pixels; }, set scrollLeft(value) { pixels = Math.round(value); },
    addEventListener(type, handler) { listeners.set(type, handler); },
  };
  h.host.querySelectorAll = () => [scroll];
  h.store.setState({ ...h.store.getState(), assembly: { ...h.store.getState().assembly,
    subviewCompositionViewport: { bpPerPx: 10, leftBp: -1003.25, topPx: 15 },
  } });
  h.controller.bindTrackScrollSync(h.host, h.store, { scope: "subview", schedulePersistAssemblyScrollState() {} });
  assert.equal(scroll.scrollLeft, 100);
  listeners.get("scroll")();
  assert.equal(h.store.getState().assembly.subviewCompositionViewport.leftBp, -1003.25);
  scroll.scrollLeft += 5; listeners.get("scroll")();
  assert.equal(h.store.getState().assembly.subviewCompositionViewport.leftBp, -950);
});
