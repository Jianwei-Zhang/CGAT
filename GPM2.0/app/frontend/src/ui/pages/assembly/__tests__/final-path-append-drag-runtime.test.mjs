import test from "node:test";
import assert from "node:assert/strict";
import { bindFinalPathAppendDrag, resolveFinalPathDragSource, resolveFinalPathDropTarget } from "../final-path-append-drag-runtime.js";
import { resolveAssemblyCtgContextTarget } from "../context-menu.js";

function classes() {
  const values = new Set();
  return { add: name => values.add(name), remove: name => values.delete(name), contains: name => values.has(name),
    toggle: (name, value) => value ? values.add(name) : values.delete(name) };
}
function fixture({ view = "graph", transfer = false, nativePoint = null } = {}) {
  const listeners = new Map(), windowListeners = new Map(), added = [], calls = [];
  const win = { innerWidth: 1000, innerHeight: 800,
    addEventListener: (name, fn) => windowListeners.set(name, fn), removeEventListener: name => windowListeners.delete(name),
    requestAnimationFrame: () => 1, cancelAnimationFrame() {} };
  let hit = null;
  const doc = { defaultView: win, elementFromPoint: () => hit,
    body: { appendChild: node => added.push(node) }, createElement: () => ({ style: {}, classList: classes(),
      offsetWidth: 180, offsetHeight: 30, setAttribute() {}, remove() { this.removed = true; } }) };
  const root = { ownerDocument: doc, isConnected: true, style: {}, dataset: {}, closest: () => null,
    addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name),
    setPointerCapture() {}, releasePointerCapture() {} };
  const attrs = { "data-track-contig-id": "9", "data-track-role": "primary", "data-track-ref-orient": "-",
    "data-main-fragment-start": "201", "data-main-fragment-end": "450" };
  const source = { isConnected: true, getAttribute: name => attrs[name] ?? null,
    closest(selector) {
      if (selector.includes("data-local-view-window") || selector.includes("data-subview" ) && !selector.includes("data-track-contig-id")) return null;
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
  const localCalls = [], cancelled = [];
  const deps = { labels: () => ({ drag: "drag", drop: "drop {path}", addLane: "add {lane}", moveLane: "move {lane}", top: "top", bottom: "bottom" }),
    append: (...args) => calls.push(args),
    ...(transfer ? { dropLocal: (...args) => localCalls.push(args), cancelHorizontal: () => cancelled.push(true) } : {}),
    ...(nativePoint ? { dragPoint: nativePoint } : {}),
  };
  const runtime = bindFinalPathAppendDrag(root, store, deps);
  const event = (x, y, patch = {}) => ({ target: source, pointerId: 1, button: 0, clientX: x, clientY: y,
    preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, ...patch });
  return { root, doc, store, source, target, surface, runtime, deps, listeners, windowListeners, added, calls, localCalls, cancelled, event,
    setHit: value => { hit = value; }, setState: value => { state = value; } };
}

test("Main right-click and drag resolve the same red-anchor source range", () => {
  const f = fixture();
  const context = resolveFinalPathDragSource(f.source);
  assert.deepEqual(context, resolveAssemblyCtgContextTarget(f.source));
  assert.equal(context.start, 201); assert.equal(context.end, 450);
  assert.equal(context.coordinateSpace, "source"); assert.equal(context.refOrient, "-");
});

for (const view of ["graph", "table"]) test(`contig drag appends once to the ${view} target with the original range`, () => {
  const f = fixture({ view });
  const down = f.event(100, 100); f.listeners.get("pointerdown")(down);
  assert.equal(down.stopped, undefined);
  assert.equal(f.root.dataset.viewContigGesture, "pending");
  f.setHit(f.target); f.windowListeners.get("pointermove")(f.event(220, 500));
  assert.equal(f.surface.classList.contains("is-final-path-append-target"), true);
  assert.equal(f.root.dataset.viewContigGesture, "drag");
  f.windowListeners.get("pointerup")(f.event(220, 500));
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0][2].start, 201);
  assert.deepEqual(f.calls[0][3], { targetChrName: "Chr01B" });
  assert.equal(f.surface.classList.contains("is-final-path-append-target"), false);
  assert.equal(f.added[0].removed, true);
  assert.equal(f.windowListeners.size, 0);
  assert.equal(f.root.dataset.viewContigGesture, undefined);
});

test("Contig pointerdown and blank plot do not reserve the drag gesture", () => {
  const f = fixture(); const down = f.event(0, 0);
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


function localDestination(doc, id = "local-target") {
  const window = { dataset: { localViewWindow: id }, closest: () => null };
  const svg = { dataset: { subviewDropTopY: "100", subviewDropBottomY: "250" },
    getBoundingClientRect: () => ({ top: 0, height: 350 }), getAttribute: () => "350" };
  const surface = { classList: classes(), querySelector: () => svg,
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 500, bottom: 350 }) };
  const target = { closest: selector => selector === "[data-local-view-window]" ? window
    : selector === ".subview-track-scroll" ? surface : null };
  return { target, window, surface, doc };
}

test("horizontal movement leaves the positional controller in charge", () => {
  const f = fixture({ transfer: true });
  const down = f.event(100, 100); f.listeners.get("pointerdown")(down);
  assert.equal(down.defaultPrevented, undefined);
  f.windowListeners.get("pointermove")(f.event(240, 104));
  f.windowListeners.get("pointerup")(f.event(240, 104));
  assert.equal(f.cancelled.length, 0); assert.equal(f.calls.length, 0); assert.equal(f.localCalls.length, 0);
});

for (const [lane, y] of [["top", 110], ["bottom", 260]]) test(`Main vertical transfer adds to the chosen ${lane} lane without a horizontal commit`, async () => {
  const f = fixture({ transfer: true });
  const dest = localDestination(f.doc); f.setHit(dest.target);
  f.listeners.get("pointerdown")(f.event(20, 20));
  f.windowListeners.get("pointermove")(f.event(22, y));
  assert.equal(f.cancelled.length, 1);
  f.windowListeners.get("pointerup")(f.event(22, y));
  assert.equal(f.localCalls.length, 1); assert.equal(f.calls.length, 0);
  const payload = f.localCalls[0][2];
  assert.equal(payload.target.lane, lane); assert.equal(payload.target.id, "local-target");
  assert.equal(payload.context.start, 201); assert.equal(payload.context.end, 450);
  assert.equal(payload.sourceWindowId, null);
});

test("native transfer hit tests the destination document, not captured source client coordinates", async () => {
  let point;
  const f = fixture({ transfer: true, nativePoint: async () => point });
  const destinationDoc = { ...f.doc, elementFromPoint: () => f.target };
  point = { document: destinationDoc, x: 20, y: 600, pressed: true };
  f.doc.defaultView.setTimeout = () => 1; f.doc.defaultView.clearTimeout = () => {};
  f.listeners.get("pointerdown")(f.event(100, 100));
  f.windowListeners.get("pointermove")(f.event(-800, -900));
  await Promise.resolve();
  assert.equal(f.surface.classList.contains("is-final-path-append-target"), true);
  f.windowListeners.get("pointerup")(f.event(-800, -900));
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0][3].targetChrName, "Chr01B");
});

test("native release requires a fresh valid target and cannot append to its last hover", async () => {
  let point;
  const f = fixture({ transfer: true, nativePoint: async () => point });
  f.doc.defaultView.setTimeout = () => 1; f.doc.defaultView.clearTimeout = () => {};
  f.setHit(f.target); point = { document: f.doc, x: 20, y: 600, pressed: true };
  f.listeners.get("pointerdown")(f.event(100, 100));
  f.windowListeners.get("pointermove")(f.event(200, 500)); await Promise.resolve();
  point = { document: null, pressed: false };
  f.windowListeners.get("pointerup")(f.event(200, 500));
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.calls.length, 0); assert.equal(f.localCalls.length, 0);
});

test("a delayed native release cannot write into a newly selected project", async () => {
  let resolve;
  const f = fixture({ transfer: true, nativePoint: () => new Promise(done => { resolve = done; }) });
  f.doc.defaultView.setTimeout = () => 1; f.doc.defaultView.clearTimeout = () => {};
  f.setHit(f.target); f.listeners.get("pointerdown")(f.event(100, 100));
  f.windowListeners.get("pointermove")(f.event(200, 500));
  f.windowListeners.get("pointerup")(f.event(200, 500));
  f.setState({ ...f.store.getState(), session: { projectId: 222 } });
  resolve({ document: f.doc, x: 200, y: 500, pressed: false });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.calls.length, 0); assert.equal(f.localCalls.length, 0);
});

for (const lane of ["top", "bottom"]) test(`native Main-to-Local transfer resolves the ${lane} lane in its owning document`, async () => {
  let point;
  const f = fixture({ transfer: true, nativePoint: async () => point });
  const dest = localDestination(null);
  const destinationDoc = { ...f.doc, elementFromPoint: () => dest.target };
  point = { document: destinationDoc, x: 100, y: lane === "top" ? 110 : 260, pressed: true };
  f.doc.defaultView.setTimeout = () => 1; f.doc.defaultView.clearTimeout = () => {};
  f.listeners.get("pointerdown")(f.event(100, 100));
  f.windowListeners.get("pointermove")(f.event(-800, 400)); await Promise.resolve();
  f.windowListeners.get("pointerup")(f.event(-800, 400));
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.localCalls.length, 1); assert.equal(f.localCalls[0][2].target.lane, lane);
});


function useLocalSource(f, id = "local-source", slot = "top") {
  const owner = { dataset: { localViewWindow: id } };
  const attrs = { "data-subview-track-pair-role": "primary", "data-subview-track-pair-contig-id": "9",
    "data-subview-composition-entity-key": "source-owned:9", "data-subview-track-slot": slot,
    "data-subview-track-ref-orient": "-", "data-subview-track-pair-dataset-id": "7" };
  f.root.closest = selector => selector === "[data-local-view-window]" ? owner : null;
  // The binding root is the owner if bound anew; this existing fixture binds
  // first and uses root equality only for event ownership checks.
  f.source.getAttribute = name => attrs[name] ?? null;
  f.source.closest = selector => selector === "[data-local-view-window]" ? owner
    : selector.includes("data-subview-fragment") && !selector.includes("data-track-contig-id") ? null
    : selector.includes("data-subview-track-pair") || selector.includes("data-track-contig-id") ? f.source : null;
}

for (const lane of ["top", "bottom"]) test(`Local ctg transfer into ${lane} ${lane === "top" ? "is a no-op" : "moves its source-owned member"}`, () => {
  const f = fixture({ transfer: true }); useLocalSource(f);
  const destination = localDestination(f.doc, "local-source"); f.setHit(destination.target);
  f.listeners.get("pointerdown")(f.event(20, 20));
  const y = lane === "top" ? 110 : 260;
  f.windowListeners.get("pointermove")(f.event(22, y));
  f.windowListeners.get("pointerup")(f.event(22, y));
  assert.equal(f.localCalls.length, lane === "top" ? 0 : 1);
  if (lane === "bottom") {
    assert.equal(f.localCalls[0][2].sourceWindowId, "local-source");
    assert.equal(f.localCalls[0][2].localContext.compositionEntityKey, "source-owned:9");
    assert.equal(f.localCalls[0][2].target.lane, "bottom");
  }
});
test("Local transfers do not silently copy members into a different Local task", () => {
  const f = fixture({ transfer: true }); useLocalSource(f);
  f.setHit(localDestination(f.doc, "local-other").target);
  f.listeners.get("pointerdown")(f.event(20, 20));
  f.windowListeners.get("pointermove")(f.event(22, 260));
  f.windowListeners.get("pointerup")(f.event(22, 260));
  assert.equal(f.localCalls.length, 0); assert.equal(f.calls.length, 0);
});


test("contig drag into an actual destination takes over even after mostly horizontal motion", () => {
  const f = fixture({ transfer: true });
  f.setHit(localDestination(f.doc).target);
  f.listeners.get("pointerdown")(f.event(20, 20));
  f.windowListeners.get("pointermove")(f.event(800, 110));
  f.windowListeners.get("pointerup")(f.event(800, 110));
  assert.equal(f.cancelled.length, 1); assert.equal(f.localCalls.length, 1);
});
test("contig drag leaving its native client area transfers instead of committing an offset", async () => {
  const f = fixture({ transfer: true, nativePoint: async () => ({ document: null, pressed: true }) });
  f.doc.defaultView.setTimeout = () => 1; f.doc.defaultView.clearTimeout = () => {};
  f.listeners.get("pointerdown")(f.event(100, 100));
  f.windowListeners.get("pointermove")(f.event(1200, 100));
  assert.equal(f.cancelled.length, 1);
  f.runtime.cancel(); await Promise.resolve();
  assert.equal(f.calls.length, 0);
});

for (const modifier of ["ctrlKey", "metaKey"]) {
  test(`${modifier} + Contig pointerdown stays available to click selection`, () => {
    const f = fixture();
    const down = f.event(100, 100, { [modifier]: true });
    f.listeners.get("pointerdown")(down);
    assert.notEqual(down.defaultPrevented, true);
    assert.notEqual(down.stopped, true);
    assert.equal(f.windowListeners.size, 0);
    f.runtime.destroy();
  });
}

test("lost capture clears the Contig cursor and cancels positional preview", () => {
  const f = fixture({ transfer: true });
  f.listeners.get("pointerdown")(f.event(100, 100));
  assert.equal(f.root.dataset.viewContigGesture, "pending");
  f.listeners.get("lostpointercapture")({ pointerId: 1 });
  assert.equal(f.root.dataset.viewContigGesture, undefined);
  assert.equal(f.windowListeners.size, 0);
  assert.equal(f.cancelled.length, 1);
  f.runtime.destroy();
});
