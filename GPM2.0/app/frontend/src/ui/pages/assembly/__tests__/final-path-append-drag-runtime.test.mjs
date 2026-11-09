import test from "node:test";
import assert from "node:assert/strict";
import { bindFinalPathAppendDrag, resolveFinalPathDragSource, resolveFinalPathDropTarget } from "../final-path-append-drag-runtime.js";
import { resolveAssemblyCtgContextTarget } from "../context-menu.js";

function classes() {
  const values = new Set();
  return { add: name => values.add(name), remove: name => values.delete(name), contains: name => values.has(name),
    toggle: (name, value) => value ? values.add(name) : values.delete(name) };
}
function fixture({ mode = "hand", view = "graph" } = {}) {
  const listeners = new Map(), windowListeners = new Map(), added = [], calls = [];
  const win = { innerWidth: 1000, innerHeight: 800,
    addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name),
    requestAnimationFrame: () => 1, cancelAnimationFrame() {} };
  let hit = null;
  const doc = { defaultView: win, elementFromPoint: () => hit,
    body: { appendChild: node => added.push(node) }, createElement: () => ({ style: {}, classList: classes(),
      offsetWidth: 180, offsetHeight: 30, setAttribute() {}, remove() { this.removed = true; } }) };
  const root = { ownerDocument: doc, isConnected: true, style: {}, closest: () => null,
    addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name),
    setPointerCapture() {}, releasePointerCapture() {} };
  const attrs = { "data-track-contig-id": "9", "data-track-role": "primary", "data-track-ref-orient": "-",
    "data-main-fragment-start": "201", "data-main-fragment-end": "450" };
  const source = { isConnected: true, getAttribute: name => attrs[name] ?? null,
    closest(selector) {
      if (selector.includes("data-local-view-window") || selector.includes("data-subview" ) && !selector.includes("data-track-contig-id")) return null;
      if (selector.includes("data-view-interaction-mode")) return mode === "hand" ? { dataset: { viewInteractionMode: mode } } : null;
      if (selector.includes("data-track-contig-id") || selector.includes("data-main-fragment")) return source;
      return null;
    } };
  const card = { dataset: { finalPathViewMode: view, finalPathTargetChrName: "Chr01B" } };
  const surface = { classList: classes(), closest: selector => selector === ".final-path-card" ? card
    : selector.includes("data-final-path-target-chr-name") ? card : null };
  const target = { closest: selector => selector.includes("data-final-path-graph-viewport") ? surface : null };
  let state = { activeRoute: "assembly", session: { workspacePath: "/fixture", projectId: 1 },
    assembly: { activeTab: "assembly", selectedChrName: "Chr01", chrCtgs: [] } };
  const store = { getState: () => state };
  const deps = { labels: () => ({ drag: "drag", drop: "drop {path}" }), append: (...args) => calls.push(args) };
  const runtime = bindFinalPathAppendDrag(root, store, deps);
  const event = (x, y, patch = {}) => ({ target: source, pointerId: 1, button: 0, clientX: x, clientY: y,
    preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...patch });
  return { root, store, source, target, surface, runtime, listeners, windowListeners, added, calls, event,
    setHit: value => { hit = value; }, setState: value => { state = value; } };
}

test("Main right-click and drag resolve the same red-anchor source range", () => {
  const f = fixture();
  const context = resolveFinalPathDragSource(f.source);
  assert.deepEqual(context, resolveAssemblyCtgContextTarget(f.source));
  assert.equal(context.start, 201); assert.equal(context.end, 450);
  assert.equal(context.coordinateSpace, "source"); assert.equal(context.refOrient, "-");
});

for (const view of ["graph", "table"]) test(`hand-mode contig drag appends once to the ${view} target with the original range`, () => {
  const f = fixture({ view });
  const down = f.event(100, 100); f.listeners.get("pointerdown")(down);
  assert.equal(down.stopped, true);
  f.setHit(f.target); f.windowListeners.get("pointermove")(f.event(220, 500));
  assert.equal(f.surface.classList.contains("is-final-path-append-target"), true);
  f.windowListeners.get("pointerup")(f.event(220, 500));
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0][2].start, 201);
  assert.deepEqual(f.calls[0][3], { targetChrName: "Chr01B" });
  assert.equal(f.surface.classList.contains("is-final-path-append-target"), false);
  assert.equal(f.added[0].removed, true);
  assert.equal(f.windowListeners.size, 0);
});

test("mouse mode and blank hand-mode plot do not reserve the drag gesture", () => {
  const f = fixture({ mode: "mouse" }); const down = f.event(0, 0);
  f.listeners.get("pointerdown")(down); assert.equal(down.stopped, undefined);
  const g = fixture(); const blank = g.event(0, 0, { target: { closest: () => null } });
  g.listeners.get("pointerdown")(blank); assert.equal(blank.stopped, undefined);
});

for (const reason of ["escape", "pointercancel", "blur", "outside", "stale", "click"]) test(`cancelled or invalid append gesture is a no-op: ${reason}`, () => {
  const f = fixture(); f.listeners.get("pointerdown")(f.event(100, 100));
  f.setHit(reason === "outside" ? null : f.target);
  if (reason !== "click") f.windowListeners.get("pointermove")(f.event(200, 500));
  if (reason === "escape") f.windowListeners.get("keydown")(f.event(200, 500, { key: "Escape" }));
  else if (["pointercancel", "blur"].includes(reason)) f.windowListeners.get(reason)();
  else {
    if (reason === "stale") f.setState({ ...f.store.getState(), session: { projectId: 2 } });
    f.windowListeners.get("pointerup")(f.event(200, 500));
  }
  assert.equal(f.calls.length, 0); assert.equal(f.windowListeners.size, 0);
});

test("the log and headers are not accepted as drop targets; binding is idempotent", () => {
  const f = fixture({ view: "log" });
  assert.equal(resolveFinalPathDropTarget(f.target), null);
  assert.equal(resolveFinalPathDropTarget({ closest: () => null }), null);
  assert.equal(bindFinalPathAppendDrag(f.root, f.store, { append() {} }), f.runtime);
});


for (const coordinateSpace of ["display", "base"]) for (const role of ["primary", "support", "ref", "phased"]) {
  test(`Local ${role}/${coordinateSpace} drag retains interval, orientation and source identity`, () => {
    const attrs = { "data-subview-fragment-key": "slice", "data-subview-fragment-contig-id": "9",
      "data-subview-fragment-role": role, "data-subview-fragment-slot": "top",
      "data-subview-fragment-start": "101", "data-subview-fragment-end": "350",
      "data-subview-fragment-coordinate-space": coordinateSpace, "data-subview-fragment-ref-orient": "-",
      "data-subview-fragment-dataset-id": "11", "data-subview-fragment-is-mirror": "1",
      "data-subview-fragment-phased-track-id": "4", "data-subview-fragment-phased-haplotype-key": "A",
      "data-subview-fragment-source-kind": role === "ref" ? "ref_segment" : "assembly_ctg",
      "data-subview-fragment-reference-chr-name": "Chr01", "data-subview-fragment-segment-start-bp": "2001",
      "data-subview-fragment-segment-end-bp": "3200",
      ...(coordinateSpace === "base" ? { "data-subview-fragment-entity-key": "local:9" } : {}) };
    const node = { getAttribute: name => attrs[name] ?? null, closest(selector) {
      return selector.includes("data-subview-fragment") || selector.includes("data-track-contig-id") ? node : null;
    } };
    const context = resolveFinalPathDragSource(node);
    assert.equal(context.start, 101); assert.equal(context.end, 350);
    assert.equal(context.coordinateSpace, coordinateSpace); assert.equal(context.refOrient, "-");
    assert.equal(context.isMirror, true); assert.equal(context.phasedTrackId, 4);
    assert.equal(context.localFragmentEntityKey, coordinateSpace === "base" ? "local:9" : undefined);
    if (role === "ref") assert.equal(context.segmentStartBp, 2001);
    attrs["data-subview-fragment-start"] = "0";
    assert.equal(resolveFinalPathDragSource(node), null, "bad fragment metadata cannot fall back to its whole parent");
  });
}

test("joined Local fragments with an entity key need not have one backing contig ID", () => {
  const attrs = { "data-subview-fragment-key": "joined:1", "data-subview-fragment-contig-id": "0",
    "data-subview-fragment-role": "primary", "data-subview-fragment-start": "21", "data-subview-fragment-end": "50",
    "data-subview-fragment-entity-key": "joined:entity", "data-subview-fragment-coordinate-space": "base" };
  const node = { getAttribute: name => attrs[name] ?? null, closest: selector => selector.includes("data-subview-fragment") ? node : null };
  assert.equal(resolveFinalPathDragSource(node).localFragmentEntityKey, "joined:entity");
});
