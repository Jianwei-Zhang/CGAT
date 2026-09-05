import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { bindSubviewTools } from "../subview-tools-runtime.js";
import { SUBVIEW_TOOLS_STORAGE_KEY } from "../subview-tools-state.js";
import { getAssemblyI18n } from "../i18n.js";
import { shouldHandleTrackDeleteHotkey } from "../track-hotkeys-runtime.js";

function fixture(saved = null) {
  const nodes = [];
  let doc;
  function node(dataset = {}) {
    const listeners = new Map();
    const value = {
      dataset, style: {}, attrs: {}, scrollTop: 0, isConnected: true, listeners,
      classList: { toggle() {} },
      setAttribute(name, val) { this.attrs[name] = val; },
      addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(fn); },
      removeEventListener(type, fn) { listeners.get(type)?.delete(fn); },
      emit(type, detail = {}) {
        const event = { target: this, stopPropagation() {}, preventDefault() {}, ...detail };
        for (const fn of listeners.get(type) || []) fn(event);
      },
      closest(selector) {
        return selector.split(",").some((part) => {
          const match = part.match(/^\[data-([\w-]+)(?:="([^"]+)")?\]$/);
          if (!match) return part === "button" && this.tagName === "BUTTON";
          const key = match[1].replace(/-([a-z])/g, (_, ch) => ch.toUpperCase());
          return Object.hasOwn(this.dataset, key) && (!match[2] || this.dataset[key] === match[2]);
        }) ? this : null;
      },
      focus() { doc.activeElement = this; },
      remove() { this.isConnected = false; nodes.splice(nodes.indexOf(this), 1); },
      setPointerCapture(id) { this.pointer = id; },
      hasPointerCapture(id) { return this.pointer === id; },
      releasePointerCapture() { this.pointer = null; },
    };
    return value;
  }
  const storage = new Map(saved ? [[SUBVIEW_TOOLS_STORAGE_KEY, JSON.stringify(saved)]] : []);
  const win = { ...node(), innerWidth: 1200, innerHeight: 800,
    localStorage: { getItem: (key) => storage.get(key), setItem: (key, v) => storage.set(key, v) },
    frames: new Map(),
    requestAnimationFrame(fn) { this.frames.set(1, fn); return 1; },
    cancelAnimationFrame(id) { this.frames.delete(id); },
  };
  const panel = { getBoundingClientRect: () => ({ right: 1100, top: 200 }),
    canvas: { width: 950, height: 420, scrollLeft: 250, scale: 2 } };
  const toggle = node({ subviewToolsToggle: "1" });
  const host = { ...node(), querySelector: (s) => s === "[data-subview-panel]" ? panel : toggle,
    querySelectorAll: () => [toggle] };
  doc = {
    defaultView: win, documentElement: { clientWidth: 1200, clientHeight: 800 },
    body: { appendChild: (n) => nodes.push(n) },
    createElement() {
      const overlay = node();
      let html = "";
      Object.defineProperty(overlay, "innerHTML", { get: () => html, set(markup) {
        html = markup;
        overlay.controls = [node({ subviewToolsWindow: "1" }), node({ subviewToolsContent: "1" }),
          node({ subviewToolsTab: "anchors" }), node({ subviewToolsTab: "composition" }),
          node({ subviewToolsClose: "1" }), node({ subviewToolsDrag: "1" }),
          node({ subviewToolsResize: "both" })];
      } });
      overlay.querySelector = (s) => overlay.controls?.find((n) => n.closest(s)) || null;
      return overlay;
    },
  };
  host.ownerDocument = doc;
  const store = createStore({ activeRoute: "assembly", session: { projectId: 1 },
    assembly: { activeTab: "assembly", selectedChrName: "Chr1", trackSelectedCtgIds: [1] } });
  const resets = [];
  const deps = { session: {}, getLabels: (state) => getAssemblyI18n(state).subview.tools,
    escapeHtml: String, escapeAttr: String, resetScope: (key) => resets.push(key) };
  return { host, store, deps, win, nodes, panel, toggle, doc, storage, resets,
    open() { host.emit("click", { target: toggle }); },
    control(key) { return nodes[0].querySelector(`[data-subview-tools-${key}]`); },
  };
}

test("toggle is local, binding is idempotent, canvas clicks keep the floating window open", () => {
  const f = fixture();
  const original = structuredClone(f.store.getState());
  const canvas = { ...f.panel.canvas };
  const runtime = bindSubviewTools(f.host, f.store, f.deps);
  assert.equal(f.nodes.length, 0);
  assert.equal(bindSubviewTools(f.host, f.store, f.deps), runtime);
  assert.equal(f.host.listeners.get("click").size, 1);
  f.open();
  assert.equal(f.nodes.length, 1);
  assert.equal(f.toggle.attrs["aria-expanded"], "true");
  f.host.emit("click", { target: { closest: () => null } });
  assert.equal(f.nodes.length, 1);
  f.nodes[0].emit("click", { target: f.control("close") });
  assert.equal(f.nodes.length, 0);
  assert.equal(f.doc.activeElement, f.toggle);
  assert.deepEqual(f.store.getState(), original);
  assert.deepEqual(f.panel.canvas, canvas);
  runtime.destroy();
});

test("drag and keyboard resize persist on completion and clean up cancelled gestures", () => {
  const f = fixture();
  const runtime = bindSubviewTools(f.host, f.store, f.deps);
  f.open();
  const initial = JSON.parse(f.storage.get(SUBVIEW_TOOLS_STORAGE_KEY)).rect;
  f.nodes[0].emit("pointerdown", { target: f.control("drag"), button: 0, pointerId: 3, clientX: 800, clientY: 250 });
  f.win.emit("pointermove", { pointerId: 3, clientX: 750, clientY: 290 });
  assert.equal(f.win.frames.size, 1);
  assert.deepEqual(JSON.parse(f.storage.get(SUBVIEW_TOOLS_STORAGE_KEY)).rect, initial);
  f.win.emit("pointercancel", { pointerId: 3 });
  const moved = JSON.parse(f.storage.get(SUBVIEW_TOOLS_STORAGE_KEY)).rect;
  assert.equal(moved.left, initial.left - 50);
  assert.equal(moved.top, initial.top + 40);
  assert.equal(f.win.frames.size, 0);
  assert.equal(f.win.listeners.get("pointermove").size, 0);
  f.nodes[0].emit("keydown", { target: f.control("resize"), key: "ArrowRight" });
  assert.equal(JSON.parse(f.storage.get(SUBVIEW_TOOLS_STORAGE_KEY)).rect.width, 330);
  f.nodes[0].emit("keydown", { target: f.control("resize"), key: "ArrowDown", shiftKey: true });
  assert.equal(JSON.parse(f.storage.get(SUBVIEW_TOOLS_STORAGE_KEY)).rect.height, 421);
  runtime.destroy();
});

test("tabs, chromosome, route and viewport changes restore preferences without stale content", () => {
  const f = fixture({ version: 1, open: true, tab: "anchors", rect: { left: 9999, top: 9999, width: 320, height: 420 } });
  const runtime = bindSubviewTools(f.host, f.store, f.deps);
  assert.equal(f.nodes.length, 1);
  assert.equal(f.control("window").style.left, "872px");
  f.nodes[0].emit("keydown", { target: f.nodes[0].querySelector('[data-subview-tools-tab="anchors"]'), key: "ArrowRight" });
  assert.equal(f.doc.activeElement.dataset.subviewToolsTab, "composition");
  f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "Chr2" } });
  assert.equal(f.resets.length, 2);
  assert.ok(f.resets.at(-1).includes("Chr2"));
  f.store.setState({ activeRoute: "workspace" });
  assert.equal(f.nodes.length, 0);
  assert.equal(f.win.listeners.get("resize").size, 0);
  assert.equal(JSON.parse(f.storage.get(SUBVIEW_TOOLS_STORAGE_KEY)).open, true);
  f.store.setState({ activeRoute: "assembly" });
  assert.equal(f.nodes.length, 1);
  f.win.innerWidth = 240;
  f.win.innerHeight = 180;
  f.win.emit("resize");
  assert.equal(f.control("window").style.width, "224px");
  f.nodes[0].emit("keydown", { target: f.control("content"), key: "Escape" });
  assert.equal(f.nodes.length, 0);
  runtime.destroy();
  assert.equal(f.host.listeners.get("click").size, 0);
});

test("popup controls cannot trigger the window capture Delete hotkey", () => {
  const f = fixture();
  assert.equal(shouldHandleTrackDeleteHotkey({ key: "Delete", target: { tagName: "BUTTON", closest: () => ({}) } },
    f.store.getState()), false);
  assert.equal(shouldHandleTrackDeleteHotkey({ key: "Delete", target: { tagName: "DIV", closest: () => null } },
    f.store.getState()), true);
});
