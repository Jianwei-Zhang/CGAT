import test from "node:test";
import assert from "node:assert/strict";
import { bindAssemblyViewNavigation, unbindAssemblyViewNavigation } from "../view-navigation-runtime.js";
import { resolveTrackPrefs } from "../track-prefs.js";

class Events {
  handlers = new Map();
  addEventListener(type, fn) {
    const set = this.handlers.get(type) || new Set(); set.add(fn); this.handlers.set(type, set);
  }
  removeEventListener(type, fn) { this.handlers.get(type)?.delete(fn); }
  emit(type, event = {}) { for (const fn of [...(this.handlers.get(type) || [])]) fn(event); }
  count(type) { return this.handlers.get(type)?.size || 0; }
}
function harness() {
  const root = new Events(), win = new Events(), frames = new Map();
  let frameId = 0, observer;
  win.requestAnimationFrame = (fn) => { frames.set(++frameId, fn); return frameId; };
  win.cancelAnimationFrame = (id) => frames.delete(id);
  win.MutationObserver = class {
    constructor(fn) { observer = this; this.callback = fn; }
    observe() { this.active = true; }
    disconnect() { this.active = false; }
  };
  root.isConnected = true;
  root.closest = () => root;
  root.querySelectorAll = () => [];
  root.ownerDocument = { defaultView: win, createElement() {}, activeElement: null };
  const views = {};
  for (const role of ["primary", "subview"]) {
    const nodes = new Map();
    const node = (key) => {
      if (!nodes.has(key)) nodes.set(key, {
        style: {}, attrs: {}, value: "500", textContent: "",
        dataset: {}, isConnected: true,
        setAttribute(k, v) { this.attrs[k] = v; }, hasAttribute(k) { return k === key; },
        setCustomValidity(value) { this.error = value; }, reportValidity() {}, focus() {},
      });
      return nodes.get(key);
    };
    const bar = {
      dataset: { viewNavigation: role, navLocale: "zh" }, isConnected: true,
      querySelector(selector) { return node(selector.match(/\[([^='\]]+)/)[1]); },
      querySelectorAll(selector) {
        if (selector.includes("mouse")) return ["mouse", "hand"].map(action);
        return [...actions.values()];
      },
    };
    node("data-view-nav-axis").clientWidth = 500;
    const actions = new Map();
    function action(name) {
      if (!actions.has(name)) actions.set(name, {
        dataset: { viewNavAction: name },
        setAttribute(k, v) { this[k] = v; },
        closest(selector) { return selector === "[data-view-nav-action]" ? this : selector === "[data-view-navigation]" ? bar : null; },
      });
      return actions.get(name);
    }
    const originalQuery = bar.querySelector;
    bar.querySelector = (selector) => selector.includes("data-view-nav-action=") ? action(selector.match(/='([^']+)'/)[1]) : originalQuery(selector);
    const scroll = new Events();
    Object.assign(scroll, {
      isConnected: true, clientWidth: 1000, scrollWidth: 2000, scrollLeft: 200,
      dataset: { trackRole: role, trackWindowStartBp: "0", trackDomainSpanBp: "1000", trackInnerWidth: "2000", trackViewboxMinX: "0",
        subviewWindowStartBp: "0", subviewDomainSpanBp: "1000", subviewInnerWidth: "2000", subviewViewboxMinX: "0" },
      classList: { values: new Set(), toggle(key, on) { if (on) this.values.add(key); else this.values.delete(key); } },
      getBoundingClientRect: () => ({ left: 0, width: 1000 }),
      closest(selector) {
        if (selector === ".assembly-track-layout") return { parentNode: root, previousElementSibling: bar };
        return selector.includes(".assembly-track-scroll") ? this : null;
      },
    });
    const display = node("data-view-nav-span");
    display.closest = (selector) => selector === "[data-view-navigation]" ? bar : null;
    const grip = node("data-view-nav-grip");
    grip.closest = (selector) => selector === "[data-view-nav-grip]" ? grip : selector === "[data-view-navigation]" ? bar : null;
    views[role] = { scroll, bar, display, action, grip, selection: node("data-view-nav-window"), axis: node("data-view-nav-axis") };
  }
  const ticks = {};
  for (const key of ["trackView", "subviewTrackView", "finalPathTrackView"]) {
    const control = { dataset: { viewTickControl: key }, querySelector: selector => selector === "[data-view-tick-interval]" ? input : null };
    const input = { value: "Auto", isConnected: true, error: "", focus() {}, reportValidity() {},
      setCustomValidity(error) { this.error = error; },
      closest: selector => selector === "[data-view-tick-control]" ? control : null };
    ticks[key] = { control, input };
  }
  root.querySelector = (selector) => selector.includes("data-view-tick-control=")
    ? ticks[selector.match(/='([^']+)'/)[1]].control
    : views[selector.includes("subview") ? "subview" : "primary"]?.scroll;
  root.contains = (scroll) => scroll.isConnected;
  let state = { locale: "zh", session: { projectId: 1 }, assembly: { selectedChrName: "Chr1", trackView: resolveTrackPrefs({ visibleSpanBp: 500 }), subviewTrackView: resolveTrackPrefs({ visibleSpanBp: 500 }), subview: { summary: { mode: "pair" } } } };
  let writes = 0, persists = 0, renders = 0;
  const store = { getState: () => state, setState(next) { writes++; state = next; } };
  const deps = {
    rerenderAssemblyMainTab() { renders++; }, rerenderSubviewPanel() { renders++; },
    persistMainTrackViewState() { persists++; },
  };
  const event = (target, extra = {}) => ({ target, button: 0, pointerId: 1, clientX: 200,
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, stopImmediatePropagation() {}, ...extra });
  const bind = () => bindAssemblyViewNavigation(root, store, deps);
  bind();
  return { root, win, frames, views, ticks, store, deps, bind, event,
    get observer() { return observer; }, get writes() { return writes; }, get renders() { return renders; }, get persists() { return persists; },
    flush() { for (const [id, fn] of [...frames]) { frames.delete(id); fn(); } },
    dispose() { unbindAssemblyViewNavigation(root); },
  };
}

test("partial refreshes retain exactly one owner and independent default mouse modes", () => {
  const h = harness();
  try {
    for (let i = 0; i < 12; i++) h.bind();
    assert.equal(h.root.count("wheel"), 1); assert.equal(h.root.count("pointerdown"), 1);
    assert.equal(h.win.count("blur"), 0);
    h.root.emit("click", h.event(h.views.primary.action("toggle-mode")));
    assert.equal(h.views.primary.scroll.dataset.viewInteractionMode, "hand");
    assert.equal(h.views.subview.scroll.dataset.viewInteractionMode, "mouse");
  } finally { h.dispose(); }
  assert.equal(h.root.count("wheel"), 0); assert.equal(h.views.primary.scroll.count("scroll"), 0);
});

test("one mode switch toggles mutually exclusive states without changing window/data", () => {
  const h = harness();
  try {
    const mode = h.views.primary.action("toggle-mode");
    assert.equal(mode["aria-checked"], "false");
    const before = JSON.stringify(h.store.getState());
    h.root.emit("click", h.event(mode));
    assert.equal(mode["aria-checked"], "true");
    assert.equal(h.views.primary.scroll.dataset.viewInteractionMode, "hand");
    h.bind();
    assert.equal(mode["aria-checked"], "true");
    h.root.emit("pointerdown", h.event(h.views.primary.scroll));
    assert.equal(h.win.count("pointermove"), 1);
    h.root.emit("click", h.event(mode));
    assert.equal(mode["aria-checked"], "false");
    assert.equal(h.views.primary.scroll.dataset.viewInteractionMode, "mouse");
    assert.equal(h.win.count("pointermove"), 0);
    assert.equal(h.views.subview.action("toggle-mode")["aria-checked"], "false");
    assert.equal(JSON.stringify(h.store.getState()), before);
    assert.equal(h.writes, 0);
  } finally { h.dispose(); }
});

test("wheel is coalesced, excludes controls and becomes inert after unbinding", () => {
  const h = harness();
  for (let i = 0; i < 30; i++) h.root.emit("wheel", h.event(h.views.primary.scroll, { deltaY: -1 }));
  assert.equal(h.frames.size, 1); assert.equal(h.writes, 0);
  h.flush(); assert.equal(h.writes, 1); assert.equal(h.renders, 1);
  h.root.emit("wheel", h.event({ closest: () => ({}) }, { deltaY: -100 }));
  assert.equal(h.frames.size, 0);
  h.root.emit("wheel", h.event(h.views.primary.scroll, { deltaY: -10 }));
  h.dispose(); assert.equal(h.frames.size, 0); assert.equal(h.win.count("pointermove"), 0);
});

for (const termination of ["pointercancel", "blur", "replacement", "removal", "unbind"]) {
  test(`hand pan cleans capture/listeners on ${termination} without store edits`, () => {
    const h = harness();
    try {
      h.root.emit("click", h.event(h.views.primary.action("toggle-mode")));
      h.root.emit("pointerdown", h.event(h.views.primary.scroll));
      assert.equal(h.win.count("pointermove"), 1); assert.equal(h.win.count("blur"), 1);
      h.win.emit("pointermove", h.event(h.views.primary.scroll, { clientX: 170 }));
      assert.equal(h.views.primary.scroll.scrollLeft, 230); assert.equal(h.writes, 0);
      if (termination === "replacement") { h.views.primary.scroll.isConnected = false; h.observer.callback(); }
      else if (termination === "removal") { h.root.isConnected = false; h.observer.callback(); }
      else if (termination === "unbind") h.dispose();
      else h.win.emit(termination, h.event(h.views.primary.scroll));
      for (const name of ["pointermove", "pointerup", "pointercancel", "blur"]) assert.equal(h.win.count(name), 0, name);
      assert.equal(h.observer.active, false); assert.equal(h.writes, 0);
      assert.equal(h.views.primary.scroll.classList.values.has("is-view-panning"), false);
    } finally { h.dispose(); }
  });
}

test("focused input replacement does not reenter commit from synchronous blur/change", () => {
  const h = harness();
  try {
    h.deps.rerenderAssemblyMainTab = () => h.root.emit("change", h.event(h.ticks.trackView.input));
    h.root.emit("keydown", h.event(h.ticks.trackView.input, { key: "Enter" }));
    assert.equal(h.writes, 1);
  } finally { h.dispose(); }
});

test("persistence is debounced and does not write into a newly selected context", async () => {
  const h = harness();
  try {
    h.root.emit("wheel", h.event(h.views.primary.scroll, { deltaY: -20 })); h.flush();
    h.store.setState({ ...h.store.getState(), assembly: { ...h.store.getState().assembly, selectedChrName: "Chr2" } });
    await new Promise(resolve => setTimeout(resolve, 200));
    assert.equal(h.persists, 0);
  } finally { h.dispose(); }
});


test("overview edge buttons support keyboard resizing without changing data context", () => {
  const h = harness();
  try {
    const edge = { dataset: { viewNavEdge: "left" }, hasAttribute: () => false,
      closest(selector) { return selector === "[data-view-navigation]" ? h.views.primary.bar : selector === "[data-view-nav-edge]" ? this : null; } };
    h.root.emit("keydown", h.event(edge, { key: "ArrowRight" }));
    assert.equal(h.store.getState().assembly.trackView.visibleSpanBp, 450);
    assert.equal(h.store.getState().assembly.selectedChrName, "Chr1");
    assert.equal(h.store.getState().assembly.subviewTrackView.visibleSpanBp, 500);
  } finally { h.dispose(); }
});


test("a queued wheel cannot apply an old chromosome window to a newly selected chromosome", () => {
  const h = harness();
  try {
    h.root.emit("wheel", h.event(h.views.primary.scroll, { deltaY: -100 }));
    const state = h.store.getState();
    h.store.setState({ ...state, assembly: { ...state.assembly, selectedChrName: "Chr2" } });
    h.flush();
    assert.equal(h.writes, 1);
    assert.equal(h.store.getState().assembly.trackView.visibleSpanBp, 500);
  } finally { h.dispose(); }
});


test("direct tick entry commits numeric or Auto values without changing window geometry", () => {
  const h = harness();
  try {
    const input = h.ticks.trackView.input;
    input.value = "100.25"; h.root.emit("keydown", h.event(input, { key: "Enter" }));
    const manual = h.store.getState().assembly.trackView;
    assert.equal(manual.tickMode, "manual"); assert.equal(manual.tickIntervalBp, 100250);
    assert.equal(manual.visibleSpanBp, 500); assert.equal(h.views.primary.scroll.scrollLeft, 200);
    input.value = "aUtO"; h.root.emit("change", h.event(input));
    assert.equal(h.store.getState().assembly.trackView.tickMode, "auto");
    assert.equal(h.store.getState().assembly.trackView.visibleSpanBp, 500);
    assert.equal(h.store.getState().assembly.subviewTrackView.tickMode, "auto");
  } finally { h.dispose(); }
});

test("invalid tick values do not commit and Escape restores the last valid Auto value", () => {
  const h = harness();
  try {
    const input = h.ticks.trackView.input;
    for (const value of ["", "0", "-1", "Infinity", "1e6", "abc"]) {
      input.value = value; h.root.emit("change", h.event(input));
      assert.ok(input.error); assert.equal(h.writes, 0);
    }
    h.root.emit("keydown", h.event(input, { key: "Escape" }));
    assert.equal(input.value, "Auto"); assert.equal(input.error, ""); assert.equal(h.writes, 0);
  } finally { h.dispose(); }
});

test("window text follows actual metrics, is automatic in units and cannot commit input", () => {
  const h = harness();
  try {
    assert.equal(h.views.primary.display.textContent, "0.5 kb");
    h.views.primary.scroll.dataset.trackDomainSpanBp = "5000000";
    h.bind(); assert.equal(h.views.primary.display.textContent, "2.5 Mb");
    assert.equal(h.views.subview.display.textContent, "0.5 kb");
    h.root.emit("change", h.event(h.views.primary.display));
    h.root.emit("keydown", h.event(h.views.primary.display, { key: "Enter" }));
    assert.equal(h.writes, 0);
    h.views.primary.scroll.dataset.trackDomainSpanBp = "0";
    h.bind(); assert.equal(h.views.primary.display.textContent, "—");
    assert.ok(h.views.primary.action("left").disabled);
  } finally { h.dispose(); }
});

for (const role of ["primary", "subview"]) {
  test(`${role} compact overview keeps scale accurate and restores handles when wider`, () => {
    const h = harness();
    try {
      const view = h.views[role];
      // Default range is half the complete domain. At 47px the pan target wins.
      view.axis.clientWidth = 94; h.bind();
      assert.equal(view.selection.attrs["data-view-nav-compact"], "true");
      assert.equal(view.selection.style.width, "50%");
      assert.equal(view.grip.hidden, false);
      assert.equal(view.grip.style.width, "47px");
      view.axis.clientWidth = 96; h.bind();
      assert.equal(view.selection.attrs["data-view-nav-compact"], "false");
      assert.equal(view.grip.hidden, true);
      view.axis.clientWidth = 500; view.scroll.scrollWidth = 100000; h.bind();
      assert.equal(view.selection.style.width, "1%");
      assert.equal(view.grip.style.width, "24px");
      assert.equal(view.grip.hidden, false);
      view.scroll.scrollLeft = 0; view.scroll.emit("scroll");
      assert.equal(view.grip.style.left, "0px");
      view.scroll.scrollLeft = 99000; view.scroll.emit("scroll");
      assert.equal(view.grip.style.left, "476px");
    } finally { h.dispose(); }
  });
  test(`${role} transparent compact target pans instead of resizing in default mouse mode`, () => {
    const h = harness();
    try {
      const view = h.views[role], key = role === "primary" ? "trackView" : "subviewTrackView";
      view.scroll.scrollWidth = 100000; h.bind();
      const span = h.store.getState().assembly[key].visibleSpanBp;
      const start = view.scroll.scrollLeft;
      h.root.emit("pointerdown", h.event(view.grip));
      h.win.emit("pointermove", h.event(view.grip, { clientX: 230 })); h.flush();
      h.win.emit("pointerup", h.event(view.grip, { clientX: 230 }));
      assert.equal(h.store.getState().assembly[key].visibleSpanBp, span);
      assert.ok(view.scroll.scrollLeft > start);
      assert.equal(view.scroll.dataset.viewInteractionMode, "mouse");
      assert.equal(h.win.count("pointermove"), 0);
    } finally { h.dispose(); }
  });
}
