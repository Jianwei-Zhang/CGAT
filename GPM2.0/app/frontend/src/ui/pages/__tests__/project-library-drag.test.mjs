import test from "node:test";
import assert from "node:assert/strict";
import { canDropLibraryItem, bindLibraryPointerDrag } from "../project-library-drag.js";
import { saveProjectLibrary } from "../../../services/project-library.js";

const library = { version: 1, collapsed: [], partitions: [
  { id: "plants", name: "Plants", parentId: "" }, { id: "rice", name: "Rice", parentId: "plants" },
] };

test("drop targets distinguish library root, unpartitioned, projects, and descendant cycles", () => {
  assert.equal(canDropLibraryItem(library, { kind: "project", id: "/a" }, "rice"), true);
  assert.equal(canDropLibraryItem(library, { kind: "project", id: "/a" }, ""), true);
  assert.equal(canDropLibraryItem(library, { kind: "project", id: "/a" }, "", true), false);
  assert.equal(canDropLibraryItem(library, { kind: "folder", id: "plants" }, "rice"), false);
  assert.equal(canDropLibraryItem(library, { kind: "folder", id: "plants" }, "plants"), false);
  assert.equal(canDropLibraryItem(library, { kind: "folder", id: "rice" }, ""), false);
  assert.equal(canDropLibraryItem(library, { kind: "folder", id: "rice" }, "", true), true);
  assert.equal(canDropLibraryItem(library, { kind: "project", id: "/a" }, "missing"), false);
});

function emitter(extra = {}) {
  const handlers = new Map(), classes = new Set();
  return { ...extra, style: {}, classList: { add: value => classes.add(value), remove: value => classes.delete(value), contains: value => classes.has(value) },
    addEventListener(type, callback) { handlers.set(type, [...(handlers.get(type) || []), callback]); },
    removeEventListener(type, callback) { handlers.set(type, (handlers.get(type) || []).filter(item => item !== callback)); },
    emit(type, event = {}) { for (const callback of handlers.get(type) || []) callback({ button: 0, pointerId: 1, clientX: 20, clientY: 20, preventDefault() {}, stopPropagation() {}, ...event }); },
  };
}
function harness(fn) {
  const previous = globalThis.window, data = new Map(), timers = new Map();
  const view = emitter({ localStorage: { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) },
    setTimeout(callback) { const id = timers.size + 1; timers.set(id, callback); return id; }, clearTimeout(id) { timers.delete(id); }, requestAnimationFrame() { return 1; }, cancelAnimationFrame() {} });
  globalThis.window = view;
  try {
    saveProjectLibrary(library);
    let hit = null, captures = 0, busy = false;
    const moves = [], errors = [], ghosts = [];
    const doc = emitter({ defaultView: view, elementFromPoint: () => hit,
      body: { append: node => ghosts.push(node) }, createElement: () => ({ style: {}, remove() { this.removed = true; } }) });
    const tree = emitter({ ownerDocument: doc, isConnected: true, closest: () => null,
      setPointerCapture() { captures++; }, hasPointerCapture: () => false });
    const host = { querySelector: () => tree, contains: () => true };
    const row = { hasAttribute: () => true, dataset: { libraryDragProject: "/mh63" }, querySelector: () => ({ textContent: "mh63" }) };
    const target = { closest: selector => selector.includes("data-library-drag") ? row : target };
    const folder = id => emitter({ dataset: { libraryFolder: id }, hasAttribute: () => false, closest: () => null });
    const dispose = bindLibraryPointerDrag(host, { busy: () => busy, move: (...args) => moves.push(args), error: cause => errors.push(cause), toggle() {} });
    const start = () => tree.emit("pointerdown", { target });
    const hover = id => { const node = folder(id); hit = { closest: () => node }; return node; };
    fn({ tree, doc, view, start, hover, moves, errors, ghosts, captures: () => captures, setBusy: value => { busy = value; }, clearHit: () => { hit = null; }, dispose });
    dispose();
  } finally { globalThis.window = previous; }
}

test("ordinary project click never captures the pointer or suppresses its open action", () => harness(({ start, tree, moves, captures }) => {
  start(); tree.emit("pointerup");
  let suppressed = false;
  tree.emit("click", { stopImmediatePropagation() { suppressed = true; } });
  assert.equal(captures(), 0); assert.equal(suppressed, false); assert.equal(moves.length, 0);
}));

test("internal pointer drag moves once and suppresses accidental project opening", () => harness(({ start, hover, tree, moves, captures, ghosts }) => {
  start(); const destination = hover("rice"); tree.emit("pointermove", { clientX: 80 });
  assert.equal(captures(), 1); assert.equal(destination.classList.contains("is-drop-target"), true);
  tree.emit("pointerup", { clientX: 80 });
  assert.deepEqual(moves, [[{ kind: "project", id: "/mh63" }, "rice"]]);
  assert.equal(ghosts[0].removed, true);
  let suppressed = false; tree.emit("click", { stopImmediatePropagation() { suppressed = true; } }); assert.equal(suppressed, true);
}));

test("release outside the last hovered partition cancels instead of using a stale destination", () => harness(({ start, hover, tree, clearHit, moves }) => {
  start(); hover("rice"); tree.emit("pointermove", { clientX: 80 }); clearHit(); tree.emit("pointerup", { clientX: 90 });
  assert.equal(moves.length, 0);
}));

for (const cancel of ["Escape", "pointercancel", "lostpointercapture", "blur", "dispose"]) {
  test(`${cancel} cancels drag without changing project membership`, () => harness(({ start, hover, tree, doc, view, dispose, moves, ghosts }) => {
    start(); hover("rice"); tree.emit("pointermove", { clientX: 80 });
    if (cancel === "Escape") doc.emit("keydown", { key: "Escape" });
    else if (cancel === "blur") view.emit("blur");
    else if (cancel === "dispose") dispose();
    else tree.emit(cancel);
    tree.emit("pointerup", { clientX: 80 });
    assert.equal(moves.length, 0); assert.equal(ghosts[0].removed, true);
  }));
}

test("busy state prevents drag start and also vetoes a drop started before a blocking operation", () => harness(({ start, hover, tree, setBusy, moves, captures }) => {
  setBusy(true); start(); tree.emit("pointermove", { clientX: 80 }); assert.equal(captures(), 0);
  setBusy(false); start(); hover("rice"); tree.emit("pointermove", { clientX: 80 });
  setBusy(true); tree.emit("pointerup", { clientX: 80 }); assert.equal(moves.length, 0);
}));
