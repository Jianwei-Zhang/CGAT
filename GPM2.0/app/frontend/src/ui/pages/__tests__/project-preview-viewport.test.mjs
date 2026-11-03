import test from "node:test";
import assert from "node:assert/strict";
import { createProjectPreviewViewport, projectPreviewViewportBounds } from "../project-preview-viewport.js";

function events() {
  const listeners = new Map();
  return { listeners,
    addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); },
    removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
    emit(name) { for (const fn of listeners.get(name) || []) fn(); },
  };
}
function fixture() {
  let frames = new Map(), id = 0, active = true, observations = 0, disconnects = 0;
  const log = [], geometry = [];
  const win = Object.assign(events(), { innerHeight: 600,
    requestAnimationFrame(fn) { frames.set(++id, fn); return id; },
    cancelAnimationFrame(id) { frames.delete(id); },
    getComputedStyle: node => ({ overflowY: node.overflow || "visible" }),
    ResizeObserver: class { observe() { observations++; } disconnect() { disconnects++; } },
  });
  const doc = Object.assign(events(), { defaultView: win, activeElement: null });
  const nodes = Array.from({ length: 10 }, (_, i) => ({ name: i, dataset: { previewMounted: "false" },
    top: i * 300, contains: node => node?.name === i,
    getBoundingClientRect() { log.push("read"); return { top: this.top, bottom: this.top + 280 }; },
  }));
  const host = Object.assign(events(), { ownerDocument: doc, querySelectorAll: () => nodes });
  const viewport = createProjectPreviewViewport(host, {
    active: () => active,
    mount(node) { log.push("mount"); node.dataset.previewMounted = "true"; },
    unmount(node) { log.push("unmount"); node.dataset.previewMounted = "false"; },
    geometry: items => geometry.push(items.map(node => node.name)),
  });
  return { viewport, host, win, doc, nodes, log, geometry,
    run() { const pending = frames; frames = new Map(); for (const fn of pending.values()) fn(); },
    get pending() { return frames.size; }, get observations() { return observations; }, get disconnects() { return disconnects; },
    deactivate() { active = false; },
  };
}

test("mounts only visible chromosomes plus bounded buffer, batches reads and skips geometry on plain scroll", () => {
  const f = fixture(); f.viewport.start(); f.run();
  assert.deepEqual(f.geometry, [[0, 1, 2, 3]]);
  assert.equal(f.log.slice(0, 10).every(item => item === "read"), true);
  assert.equal(f.nodes.filter(node => node.dataset.previewMounted === "true").length, 4);
  f.doc.emit("scroll"); f.doc.emit("scroll"); assert.equal(f.pending, 1); f.run();
  assert.equal(f.geometry.length, 1);
  for (const node of f.nodes) node.top -= 1800;
  f.doc.emit("scroll"); f.run();
  assert.deepEqual(f.geometry.at(-1), [5, 6, 7, 8, 9]);
  assert.equal(f.nodes[0].dataset.previewMounted, "false");
  f.viewport.stop();
});

test("clipping uses nested scroll ancestor content bounds, not a guessed application container", () => {
  const f = fixture();
  f.host.parentElement = { overflow: "auto", clientTop: 2, clientHeight: 250,
    getBoundingClientRect: () => ({ top: 100 }), parentElement: {
      overflow: "hidden", clientHeight: 190, getBoundingClientRect: () => ({ top: 150 }),
    } };
  assert.deepEqual(projectPreviewViewportBounds(f.host), { top: 150, bottom: 340 });
  f.viewport.start(); f.run(); assert.deepEqual(f.geometry, [[0, 1]]); f.viewport.stop();
});

test("focus pins its card while scrolling, focus departure releases details without removing the header", () => {
  const f = fixture(); f.viewport.start(); f.run(); f.doc.activeElement = { name: 0 };
  for (const node of f.nodes) node.top -= 1800;
  f.doc.emit("scroll"); f.run(); assert.equal(f.nodes[0].dataset.previewMounted, "true");
  f.doc.activeElement = null; f.host.emit("focusout"); f.run();
  assert.equal(f.nodes[0].dataset.previewMounted, "false"); f.viewport.stop();
});

test("refresh and resize remeasure mounted cards; stop cancels frames and rebind has one listener/observer owner", () => {
  const f = fixture(); f.viewport.start(); f.viewport.start(); f.run();
  f.win.emit("resize"); f.viewport.refresh(); assert.equal(f.pending, 1); f.run(); assert.equal(f.geometry.length, 2);
  f.doc.emit("scroll"); f.viewport.stop(); assert.equal(f.pending, 0);
  assert.equal(f.disconnects, 1); assert.equal(f.doc.listeners.get("scroll").size, 0);
  assert.equal(f.host.listeners.get("focusin").size, 0); assert.equal(f.win.listeners.get("resize").size, 0);
  f.viewport.start(); f.run(); assert.equal(f.observations, 2); assert.equal(f.doc.listeners.get("scroll").size, 1);
  assert.equal(f.geometry.length, 3); f.viewport.stop();
});

test("inactive/detached owners never mount stale project results and clipped hidden previews stay light", () => {
  const f = fixture(); f.viewport.start(); f.deactivate(); f.run(); assert.equal(f.geometry.length, 0); f.viewport.stop();
  const g = fixture(); g.host.parentElement = { overflow: "hidden", clientHeight: 0, getBoundingClientRect: () => ({ top: 0 }) };
  g.viewport.start(); g.run(); assert.equal(g.nodes.every(node => node.dataset.previewMounted === "false"), true); g.viewport.stop();
});

test("visual viewport zoom and offset refresh geometry and range", () => {
  const f = fixture(); f.win.visualViewport = Object.assign(events(), { offsetTop: 200, height: 200 });
  f.viewport.start(); f.run(); assert.deepEqual(projectPreviewViewportBounds(f.host), { top: 200, bottom: 400 });
  assert.deepEqual(f.geometry[0], [0, 1]);
  f.win.visualViewport.emit("resize"); f.run(); assert.equal(f.geometry.length, 2);
  f.viewport.stop(); assert.equal(f.win.visualViewport.listeners.get("resize").size, 0);
});


test("card intersection updates range when Overview summary shifts without a scroll or Preview resize", () => {
  const f = fixture();
  // Create a new owner after installing the optional browser API.
  let notify, disconnected = 0; const observed = new Set();
  f.win.IntersectionObserver = class {
    constructor(callback) { notify = callback; }
    observe(node) { observed.add(node); }
    unobserve(node) { observed.delete(node); }
    disconnect() { disconnected++; observed.clear(); }
  };
  const owner = createProjectPreviewViewport(f.host, {
    active: () => true,
    mount: node => { node.dataset.previewMounted = "true"; },
    unmount: node => { node.dataset.previewMounted = "false"; },
    geometry: () => {},
  });
  for (const node of f.nodes) node.top += 1500;
  owner.start(); f.run(); assert.equal(observed.size, 10);
  assert.equal(f.nodes.every(node => node.dataset.previewMounted === "false"), true);
  for (const node of f.nodes) node.top -= 1500;
  notify(); f.run(); assert.equal(f.nodes[0].dataset.previewMounted, "true");
  const removed = f.nodes.pop(); owner.refresh(); f.run(); assert.equal(observed.has(removed), false);
  owner.stop(); assert.equal(disconnected, 1); assert.equal(observed.size, 0);
});
