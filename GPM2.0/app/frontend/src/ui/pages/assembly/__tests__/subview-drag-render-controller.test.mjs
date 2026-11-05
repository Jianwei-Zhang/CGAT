import test from "node:test";
import assert from "node:assert/strict";
import { createSubviewDragRenderController, sameSubviewRenderSnapshot } from "../subview-drag-render-controller.js";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";

const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture() {
  const f = { jobs: [], mounted: [], bound: [], fallbacks: [], prepared: 0, cancelled: 0, hydrated: [], closed: 0, yields: 0 };
  f.state = createIdentityRenderState();
  f.state.activeRoute = "assembly"; f.state.assembly.activeTab = "assembly";
  f.width = 1200;
  const node = () => ({
    attributes: {}, style: {}, children: [], isConnected: true,
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    appendChild(child) { child.parent = this; this.children.push(child); return child; },
    remove() { this.removed = true; if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); },
    addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
  });
  const makeCard = () => {
    const scroll = node(), layout = node(), card = node();
    scroll.parentElement = layout; card.layout = layout;
    scroll.querySelector = selector => selector === "[data-subview-band-drag-canvas]" && f.canvas !== false ? node() : null;
    scroll.querySelectorAll = selector => selector === "[data-track-band-proxy='1']" ? Array(1000).fill(null) : [];
    card.scroll = scroll;
    card.querySelector = selector => selector === ".subview-track-scroll" ? scroll : null;
    card.replaceWith = next => { card.isConnected = false; f.card = next; };
    return card;
  };
  f.card = makeCard(); f.original = f.card;
  f.document = { documentElement: { dataset: { theme: "dark" } }, createElement(tag) {
    if (tag !== "template") return node();
    const card = makeCard();
    const slots = Array.from({ length: 3 }, (_, i) => ({
      getAttribute: () => String(i), set innerHTML(value) { f.hydrated.push(value); },
    }));
    return { content: { querySelector: () => card, querySelectorAll: () => slots }, set innerHTML(_value) {} };
  } };
  f.head = node(); f.panel = { ...node(), ownerDocument: f.document, querySelector(selector) {
    return selector === ".subview-alignment-card" ? f.card : selector === ".subview-panel-head" ? f.head : null;
  } };
  f.host = { querySelector: () => f.panel };
  f.store = { getState: () => f.state };
  f.preview = { prepareCommit() { f.prepared++; } };
  f.renderer = { render(state, options, current) {
    return new Promise((resolve, reject) => f.jobs.push({ state, options, current, resolve, reject }));
  }, cancel() { f.cancelled++; } };
  f.controller = createSubviewDragRenderController({
    renderer: f.renderer, supported: () => f.supported !== false,
    getWidths: () => ({ subview: f.width }), createCover: node,
    statusDelayMs: f.statusDelayMs ?? 0,
    setTimer(callback, delay) { f.timers = [...(f.timers || []), { callback, delay }]; return f.timers.length; },
    clearTimer(id) { f.clearedTimers = [...(f.clearedTimers || []), id]; },
    yieldTask: async () => { f.yields++; await f.onYield?.(); },
    onBind(_host, _store, card) { f.bound.push(card); return f.onBind?.(); },
    onMounted(_host, _store, card) { f.mounted.push(card); },
    onFallback(_host, _store, error) { f.fallbacks.push(error); },
  });
  f.start = () => f.controller.start(f.host, f.store, f.preview);
  f.reply = (index = 0) => f.jobs[index].resolve({ skeleton: "fixture", batches: ["a", "b", "c"],
    rasters: [{ index: 0, bitmap: { close() { f.closed++; } } }],
  });
  f.patch = patch => { f.state = { ...f.state, assembly: { ...f.state.assembly, ...patch } }; };
  return f;
}

test("release keeps only the plot busy, binds a sparse skeleton and hydrates every batch without mutating store", async () => {
  const f = fixture(), before = structuredClone(f.state), pending = f.start();
  assert.equal(typeof pending.then, "function"); assert.equal(f.prepared, 1);
  assert.equal(f.original.scroll.attributes["aria-busy"], "true");
  const status = f.original.layout.children[0];
  assert.equal(status.attributes.role, "status");
  assert.equal(status.attributes["data-visible"], "1");
  assert.equal(f.head.children.length, 0, "progress never enters the parameter row");
  assert.deepEqual(f.state, before); assert.equal(f.state.assembly.loading, false);
  assert.equal(f.panel.attributes["data-subview-render-incomplete"], "1");
  f.onBind = () => assert.deepEqual(f.hydrated, []);
  f.reply(); assert.equal(await pending, true);
  assert.deepEqual(f.hydrated, ["a", "b", "c"]); assert.equal(f.bound.length, 1);
  assert.equal(f.mounted[0], f.card); assert.equal(f.closed, 1); assert.equal(f.fallbacks.length, 0);
  assert.equal(f.head.children.length, 0); assert.equal(f.card.layout.children.length, 0);
  assert.equal(f.card.scroll.attributes["aria-busy"], undefined);
  assert.equal(f.card.scroll.children.length, 0); assert.deepEqual(f.state, before);
  assert.equal(f.panel.attributes["data-subview-render-incomplete"], undefined);
});

test("render progress is delayed, moves with the replacement plot and clears its pending timer", async () => {
  const f = fixture(); f.statusDelayMs = 350;
  f.controller = createSubviewDragRenderController({
    renderer: f.renderer, supported: () => true, getWidths: () => ({ subview: f.width }),
    createCover: () => ({ ...f.original.layout, children: [] }),
    statusDelayMs: 350,
    setTimer(callback, delay) { f.timers = [{ callback, delay }]; return 7; },
    clearTimer(id) { f.clearedTimers = [id]; }, yieldTask: async () => {},
    onBind(_host, _store, card) { assert.equal(card.layout.children[0].attributes.role, "status"); },
  });
  const pending = f.controller.start(f.host, f.store, f.preview), status = f.original.layout.children[0];
  assert.equal(f.timers[0].delay, 350); assert.equal(status.attributes["data-visible"], undefined);
  f.timers[0].callback(); assert.equal(status.attributes["data-visible"], "1");
  f.reply(); assert.equal(await pending, true);
  assert.deepEqual(f.clearedTimers, [7]); assert.equal(f.card.layout.children.length, 0);
});

for (const kind of ["project", "workspace", "chromosome", "route", "tab", "reload", "detached", "panel"]) {
  test(`pending render rejects a changed ${kind} without mounting or running fallback`, async () => {
    const f = fixture(), pending = f.start();
    if (kind === "project") f.state = { ...f.state, session: { ...f.state.session, projectId: 99 } };
    if (kind === "workspace") f.state = { ...f.state, session: { ...f.state.session, workspacePath: "other" } };
    if (kind === "chromosome") f.patch({ selectedChrName: "other" });
    if (kind === "route") f.state = { ...f.state, activeRoute: "overview" };
    if (kind === "tab") f.patch({ activeTab: "new-sequences" });
    if (kind === "reload") f.patch({ sourceEditingReloadRequired: true });
    if (kind === "detached") f.card.isConnected = false;
    if (kind === "panel") f.panel = {};
    assert.equal(f.jobs[0].current(), false); f.reply();
    assert.equal(await pending, false); assert.equal(f.bound.length, 0); assert.equal(f.fallbacks.length, 0);
    assert.equal(f.closed, 1); assert.equal(f.head.children.length, 0);
  });
}

for (const kind of ["evidence", "offsets", "width", "theme", "locale"]) {
  test(`same-context ${kind} change discards stale packet and retries from current state`, async () => {
    const f = fixture(), pending = f.start();
    if (kind === "evidence") f.patch({ subview: { ...f.state.assembly.subview, pairwiseEvidence: { status: "loaded", hits: [] } } });
    if (kind === "offsets") f.patch({ subviewTrackDragOffsets: [{ slot: "top", contigId: 30, offsetBp: 123 }] });
    if (kind === "width") f.width = 900;
    if (kind === "theme") f.document.documentElement.dataset.theme = "light";
    if (kind === "locale") f.state = { ...f.state, locale: "zh-CN" };
    assert.equal(f.jobs[0].current(), false); f.reply(); await tick();
    assert.equal(f.bound.length, 0); assert.equal(f.jobs.length, 2); assert.equal(f.jobs[1].state, f.state);
    f.reply(1); assert.equal(await pending, true); assert.equal(f.closed, 2); assert.equal(f.mounted.length, 1);
  });
}

test("unrelated action feedback and scroll positions do not restart background geometry", async () => {
  const f = fixture(), pending = f.start();
  f.patch({ actionStatus: "another action", actionError: "notice", trackScrollState: { left: 42 } });
  assert.equal(f.jobs[0].current(), true); f.reply();
  assert.equal(await pending, true); assert.equal(f.jobs.length, 1);
});

test("external rerender cancellation stops hydration and closes transferred bitmaps", async () => {
  const f = fixture(), pending = f.start();
  f.onYield = () => { if (f.hydrated.length === 1) f.controller.cancel(); };
  f.reply(); assert.equal(await pending, false);
  assert.deepEqual(f.hydrated, ["a"]); assert.equal(f.closed, 1);
  assert.equal(f.panel.attributes["data-subview-render-incomplete"], "1");
  assert.equal(f.cancelled, 1); assert.equal(f.mounted.length, 0); assert.equal(f.fallbacks.length, 0);
  assert.equal(f.head.children.length, 0);
});

test("authoritative fallback runs on worker failure, never after a newer rerender cancels it", async () => {
  const f = fixture(), pending = f.start();
  f.jobs[0].reject(new Error("worker crashed")); assert.equal(await pending, false);
  assert.match(f.fallbacks[0].message, /worker crashed/);
  const other = fixture(), stale = other.start();
  other.onYield = () => other.controller.cancel();
  other.jobs[0].reject(new Error("old failure")); assert.equal(await stale, false);
  assert.equal(other.fallbacks.length, 0); assert.equal(other.head.children.length, 0);
});

test("newer release cannot be overwritten by an older result or failure", async () => {
  const f = fixture(), old = f.start(), next = f.start();
  f.reply(); assert.equal(await old, false); assert.equal(f.closed, 1);
  f.reply(1); assert.equal(await next, true); assert.equal(f.mounted.length, 1);
  assert.equal(f.fallbacks.length, 0); assert.equal(f.closed, 2);
});

test("unsupported Worker or missing drag raster keeps the synchronous complete-SVG fallback", () => {
  const f = fixture(); f.supported = false; assert.equal(f.start(), null);
  f.supported = true; f.canvas = false; assert.equal(f.start(), null);
  assert.equal(f.prepared, 0); assert.equal(f.jobs.length, 0);
});

test("cancel releases even a completed idle worker cache", async () => {
  const f = fixture(), pending = f.start(); f.reply(); await pending;
  f.controller.cancel(); assert.equal(f.cancelled, 1);
});

test("snapshot fence includes removed assembly keys and locale but ignores only feedback/scroll", () => {
  const f = fixture(), state = f.state;
  assert.equal(sameSubviewRenderSnapshot(state, { ...state, assembly: { ...state.assembly, actionStatus: "ok" } }), true);
  const removed = { ...state.assembly }; delete removed.subview;
  assert.equal(sameSubviewRenderSnapshot(state, { ...state, assembly: removed }), false);
  assert.equal(sameSubviewRenderSnapshot(state, { ...state, locale: "different" }), false);
});

test("viewport normalization retries off-thread rather than running a blocking nested rerender", async () => {
  const f = fixture(), pending = f.start();
  f.onBind = () => f.bound.length !== 1;
  f.reply(); await tick(); assert.equal(f.jobs.length, 2); assert.deepEqual(f.hydrated, []);
  f.reply(1); assert.equal(await pending, true); assert.equal(f.bound.length, 2);
  assert.deepEqual(f.hydrated, ["a", "b", "c"]); assert.equal(f.fallbacks.length, 0);
});
