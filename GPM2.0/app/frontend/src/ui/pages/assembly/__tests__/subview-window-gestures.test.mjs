import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { bindSubviewWorkspace } from "../subview-workspace-runtime.js";
import { installSubviewWorkspace, changeSubviewWindow } from "../subview-workspace-state.js";
import { getAssemblyI18n } from "../i18n.js";

function fixture() {
  const emitter = () => ({ events: new Map(), addEventListener(type, fn) { this.events.set(type, fn); },
    removeEventListener(type) { this.events.delete(type); } });
  const store = createStore({ activeRoute: "assembly", locale: "en", assembly: { selectedChrName: "Chr01",
    subview: { summary: { mode: "2-contig", top: { role: "primary", contigId: 1 }, bottom: { role: "primary", contigId: 2 } } } } });
  installSubviewWorkspace(store); const id = store.getState().assembly.subviewWorkspace.activeId;
  changeSubviewWindow(store, id, "position", { x: 100, y: 100, width: 700, height: 400 });
  const win = { ...emitter(), innerWidth: 1400, innerHeight: 900 };
  const doc = { ...emitter(), defaultView: win, createElement() { throw new Error("unexpected render"); } };
  const values = new Map(), classes = new Set(["is-floating"]);
  const node = { ...emitter(), dataset: { localViewWindow: id }, hidden: false,
    classList: { contains: key => classes.has(key), toggle(key, on) { on ? classes.add(key) : classes.delete(key); } },
    style: { setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key) },
    querySelector: () => null, setAttribute() {}, setPointerCapture() {}, releasePointerCapture() {},
    getBoundingClientRect: () => ({ left: 100, top: 100, width: 700, height: 400 }) };
  const section = { querySelector: () => null, querySelectorAll: () => [node], contains: () => true };
  const root = { ...emitter(), ownerDocument: doc, isConnected: true, matches: () => true,
    querySelector: selector => selector === "[data-subview-workspace]" ? section : null };
  let refreshes = 0;
  const runtime = bindSubviewWorkspace(root, store, { getLabels: state => getAssemblyI18n(state).subview,
    bindWindow() {}, syncTools() {}, render() { throw new Error("unexpected render"); }, refresh() { refreshes++; } });
  const target = edge => ({ closest(selector) {
    if (selector === "[data-local-view-window]") return node;
    if (selector === "[data-local-view-resize]" && edge) return { dataset: { localViewResize: edge } };
    return selector === "[data-local-view-drag]" ? {} : null;
  } });
  const event = (extra = {}) => ({ pointerId: 1, button: 0, clientX: 300, clientY: 200, preventDefault() {}, stopPropagation() {}, ...extra });
  const down = (edge = null) => root.events.get("pointerdown")(event({ target: target(edge) }));
  const move = () => doc.events.get("pointermove")(event({ clientX: 350, clientY: 225 }));
  return { store, id, node, root, doc, win, values, runtime, down, move, event, refreshes: () => refreshes,
    item: () => store.getState().assembly.subviewWorkspace.windows.find(item => item.id === id) };
}

test("resize changes DOM geometry during preview and commits/refreshes its owner once", () => {
  const f = fixture(), before = f.store.getState().assembly.subview;
  f.down("se"); f.move();
  assert.equal(f.item().width, 700); assert.equal(f.values.get("--local-width"), "750px"); assert.equal(f.refreshes(), 0);
  f.doc.events.get("pointerup")(f.event());
  assert.equal(f.item().width, 750); assert.equal(f.item().height, 425); assert.equal(f.refreshes(), 1);
  assert.equal(f.store.getState().assembly.subview, before);
  f.runtime.destroy();
});

test("moving header whitespace commits position without graph rebuilding", () => {
  const f = fixture(); f.down(); f.move(); f.doc.events.get("pointerup")(f.event());
  assert.equal(f.item().x, 150); assert.equal(f.item().y, 125); assert.equal(f.item().width, 700);
  assert.equal(f.refreshes(), 0); f.runtime.destroy();
});

for (const cancel of ["pointercancel", "Escape", "blur", "lostpointercapture"]) test(`resize ${cancel} restores the original geometry`, () => {
  const f = fixture(); f.down("se"); f.move();
  if (cancel === "Escape") f.doc.events.get("keydown")(f.event({ key: "Escape" }));
  else if (cancel === "blur") f.win.events.get("blur")({});
  else if (cancel === "lostpointercapture") f.root.events.get(cancel)(f.event());
  else f.doc.events.get(cancel)(f.event());
  assert.equal(f.item().width, 700); assert.equal(f.values.get("--local-width"), "700px");
  assert.equal(f.refreshes(), 0); f.runtime.destroy();
});

test("closing an owner while resizing discards the preview instead of reviving it", () => {
  const f = fixture(); f.down("se"); f.move(); changeSubviewWindow(f.store, f.id, "close");
  f.doc.events.get("pointerup")(f.event());
  assert.equal(f.store.getState().assembly.subviewWorkspace.windows.length, 0);
  assert.equal(f.refreshes(), 0); f.runtime.destroy();
});

test("destroy detaches gesture listeners and suppresses already queued shared-data rendering", async () => {
  const f = fixture();
  for (let i = 0; i < 2; i++) f.store.setState({ assembly: { ...f.store.getState().assembly, chrCtgs: [] } });
  f.down("se"); f.move(); f.runtime.destroy(); await Promise.resolve();
  assert.equal(f.item().width, 700);
  assert.equal(f.doc.events.size, 0); assert.equal(f.win.events.size, 0); assert.equal(f.root.events.size, 0);
});


test("restoring a resized window into a smaller viewport clamps geometry and refreshes its own graph", () => {
  const f = fixture(); changeSubviewWindow(f.store, f.id, "minimize");
  f.win.innerWidth = 600; f.win.innerHeight = 350;
  const button = { dataset: { localViewId: f.id, localViewAction: "activate" } };
  f.root.events.get("click")(f.event({ target: { closest: () => button } }));
  assert.equal(f.item().minimized, false); assert.equal(f.item().width, 600); assert.equal(f.item().height, 350);
  assert.equal(f.item().x, 0); assert.equal(f.item().y, 0); assert.equal(f.refreshes(), 1);
  f.runtime.destroy();
});
