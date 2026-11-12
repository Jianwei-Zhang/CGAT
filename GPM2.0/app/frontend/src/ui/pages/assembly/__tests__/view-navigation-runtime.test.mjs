import test from "node:test";
import assert from "node:assert/strict";
import { bindAssemblyViewNavigation, unbindAssemblyViewNavigation } from "../view-navigation-runtime.js";
import { viewNavText } from "../view-navigation-ui.js";
import { blockSubviewRenderInput } from "../subview-drag-render-preview.js";
import { VIEW_CONTIG_TARGET, VIEW_CONTROL_TARGET } from "../view-interaction.js";
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
function harness({ resetScrollOnReparent = false } = {}) {
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
  root.dataset = {};
  const capturedPointers = new Set();
  root.setPointerCapture = (id) => capturedPointers.add(id);
  root.releasePointerCapture = (id) => capturedPointers.delete(id);
  root.hasPointerCapture = (id) => capturedPointers.has(id);
  root.closest = () => root;
  root.querySelectorAll = () => [];
  root.ownerDocument = { defaultView: win, createElement() {}, activeElement: null };
  const views = {}, renderedNavigation = [];
  function attachElement(node) {
    node.parentNode = null;
    node.remove = () => {
      if (!node.parentNode) return;
      // Browsers clear descendant scroll offsets when a live layout is moved.
      if (resetScrollOnReparent) {
        for (const view of Object.values(views)) {
          if (view.layout !== node) continue;
          view.scroll.scrollLeft = 0;
          view.scroll.scrollTop = 0;
        }
      }
      const children = node.parentNode.children;
      children.splice(children.indexOf(node), 1);
      node.parentNode = null;
    };
    Object.defineProperty(node, "previousElementSibling", {
      get() { return node.parentNode?.children[node.parentNode.children.indexOf(node) - 1] || null; },
    });
    return node;
  }
  root.ownerDocument.createElement = () => attachElement({
    className: "", dataset: {}, children: [],
    insertBefore(child, before = null) {
      child.remove();
      const index = before ? this.children.indexOf(before) : this.children.length;
      this.children.splice(index, 0, child); child.parentNode = this;
      return child;
    },
    appendChild(child) { return this.insertBefore(child); },
    get firstElementChild() { return this.children[0] || null; },
    set innerHTML(html) {
      renderedNavigation.push(html);
      const role = html.match(/data-view-navigation="([^"]+)"/)[1];
      this.appendChild(views[role].bar);
    },
  });
  for (const role of ["primary", "subview"]) {
    const nodes = new Map();
    const node = (key) => {
      if (!nodes.has(key)) nodes.set(key, {
        style: {}, attrs: {}, value: "500", textContent: "",
        dataset: {}, isConnected: true,
        setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; }, hasAttribute(k) { return k === key; },
        setCustomValidity(value) { this.error = value; }, reportValidity() {}, focus() { root.ownerDocument.activeElement = this; },
      });
      return nodes.get(key);
    };
    const bar = {
      attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; },
      dataset: { viewNavigation: role, navLocale: "zh" }, isConnected: true,
      querySelector(selector) { return node(selector.match(/\[([^='\]]+)/)[1]); },
      querySelectorAll(selector) {
        return [...actions.values()];
      },
    };
    node("data-view-nav-axis").clientWidth = 500;
    const actions = new Map();
    function action(name) {
      if (!actions.has(name)) actions.set(name, {
        dataset: { viewNavAction: name }, attributeWrites: [],
        setAttribute(k, v) { this.attributeWrites.push([k, v]); this[k] = v; },
        getAttribute(k) { return this[k] ?? null; },
        closest(selector) { return selector === "[data-view-nav-action]" ? this : selector === "[data-view-navigation]" ? bar : null; },
      });
      return actions.get(name);
    }
    const originalQuery = bar.querySelector;
    bar.querySelector = (selector) => selector.includes("data-view-nav-action=") ? action(selector.match(/='([^']+)'/)[1]) : originalQuery(selector);
    attachElement(bar);
    const layout = attachElement({ dataset: {} });
    const panel = root.ownerDocument.createElement("div");
    panel.appendChild(bar); panel.appendChild(layout);
    const scroll = new Events();
    Object.assign(scroll, {
      isConnected: true, clientWidth: 1000, scrollWidth: 2000, scrollLeft: 200, scrollTop: 25,
      dataset: { trackRole: role, trackWindowStartBp: "0", trackDomainSpanBp: "1000", trackInnerWidth: "2000", trackViewboxMinX: "0",
        subviewWindowStartBp: "0", subviewDomainSpanBp: "1000", subviewInnerWidth: "2000", subviewViewboxMinX: "0" },
      attrs: {}, setAttribute(k, v) { this.attrs[k] = v; },
      classList: { values: new Set(), toggle(key, on) { if (on) this.values.add(key); else this.values.delete(key); } },
      getBoundingClientRect: () => ({ left: 0, width: 1000 }),
      closest(selector) {
        if (selector === ".assembly-track-layout") return layout;
        return selector.includes(".assembly-track-scroll") ? this : null;
      },
    });
    const display = node("data-view-nav-span");
    display.closest = (selector) => selector === "[data-view-navigation]" ? bar : null;
    const grip = node("data-view-nav-grip");
    grip.closest = (selector) => selector === "[data-view-nav-grip]" ? grip : selector === "[data-view-navigation]" ? bar : null;
    const selection = node("data-view-nav-window");
    selection.closest = selector => selector === "[data-view-navigation]" ? bar : selector === "[data-view-nav-window]" ? selection : null;
    views[role] = { scroll, bar, layout, panel, display, action, grip, selection, axis: node("data-view-nav-axis") };
    views[role].axis.closest = selector => selector === "[data-view-nav-axis]" ? views[role].axis : selector === "[data-view-navigation]" ? bar : null;
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
    preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.propagationStopped = true; }, stopImmediatePropagation() {}, ...extra });
  const bind = () => bindAssemblyViewNavigation(root, store, deps);
  bind();
  return { root, win, frames, views, ticks, store, deps, bind, event, renderedNavigation,
    get observer() { return observer; }, get writes() { return writes; }, get renders() { return renders; }, get persists() { return persists; },
    flush() { for (const [id, fn] of [...frames]) { frames.delete(id); fn(); } },
    dispose() { unbindAssemblyViewNavigation(root); },
  };
}

test("partial refreshes retain exactly one navigation owner without interaction mode state", () => {
  const h = harness();
  try {
    for (let i = 0; i < 12; i++) h.bind();
    assert.equal(h.root.count("wheel"), 1); assert.equal(h.root.count("pointerdown"), 1);
    assert.equal(h.win.count("blur"), 0);
    assert.equal(h.views.primary.scroll.dataset.viewInteractionMode, undefined);
    assert.equal(h.views.subview.scroll.dataset.viewInteractionMode, undefined);
  } finally { h.dispose(); }
  assert.equal(h.root.count("wheel"), 0); assert.equal(h.views.primary.scroll.count("scroll"), 0);
});

for (const role of ["primary", "subview"]) {
  test(`${role} navigation mounting preserves restored scroll through live layout reparenting`, () => {
    const h = harness({ resetScrollOnReparent: true });
    try {
      const view = h.views[role];
      assert.equal(view.scroll.scrollLeft, 200);
      assert.equal(view.scroll.scrollTop, 25);
      assert.equal(view.selection.getAttribute("aria-valuenow"), "100");
      const state = h.store.getState();
      // A scoped render produces a fresh, unwrapped layout; scroll sync runs
      // before navigation mounts its card. Reproduce that ordering repeatedly.
      for (const left of [730, 410, 900]) {
        const previousCard = view.layout.parentNode;
        view.panel.appendChild(view.layout);
        previousCard.remove();
        view.scroll.scrollLeft = left;
        view.scroll.scrollTop = 45;
        h.bind();
        assert.equal(view.scroll.scrollLeft, left);
        assert.equal(view.scroll.scrollTop, 45);
        assert.equal(view.selection.getAttribute("aria-valuenow"), String(left / 2));
        assert.equal(view.scroll.dataset.viewInteractionMode, undefined);
        assert.equal(h.store.getState(), state, "mounting must not change viewport preferences or edits");
        assert.equal(view.panel.children.length, 1);
      }
    } finally { h.dispose(); }
  });

  test(`${role} navigation shares the graphic card without entering the horizontal scroller`, () => {
    const h = harness();
    try {
      const view = h.views[role], card = view.layout.parentNode;
      assert.equal(card.className, "assembly-view-card");
      assert.equal(card.dataset.viewNavigationCard, role);
      assert.deepEqual(card.children, [view.bar, view.layout]);
      assert.equal(view.layout.previousElementSibling, view.bar);
      assert.equal(view.scroll.closest(".assembly-track-layout"), view.layout);
      assert.equal(card.parentNode, view.panel);
      for (let i = 0; i < 5; i++) h.bind();
      assert.deepEqual(view.panel.children, [card]);
      assert.deepEqual(card.children, [view.bar, view.layout]);
      h.store.setState({ ...h.store.getState(), locale: "en" });
      h.bind();
      assert.equal(view.layout.parentNode, card);
      assert.deepEqual(card.children, [view.bar, view.layout]);
      assert.equal(view.bar.dataset.navLocale, "en");
    } finally { h.dispose(); }
  });

  for (const target of ["scroll", "axis"]) {
    test(`${role} ${target} Ctrl + wheel zooms without a mode switch`, () => {
      const h = harness();
      try {
        const view = h.views[role];
        const wheel = h.event(view[target], { ctrlKey: true, deltaY: -100 });
        h.root.emit("wheel", wheel);
        assert.equal(wheel.defaultPrevented, true);
        assert.equal(h.frames.size, 1);
        h.flush(); assert.equal(h.writes, 1);
        const otherRole = role === "primary" ? "subview" : "primary";
        const otherKey = otherRole === "primary" ? "trackView" : "subviewTrackView";
        assert.equal(h.store.getState().assembly[otherKey].visibleSpanBp, 500);
        const otherWheel = h.event(h.views[otherRole][target], { ctrlKey: true, deltaY: -100 });
        h.root.emit("wheel", otherWheel);
        assert.equal(otherWheel.defaultPrevented, true);
        h.flush(); assert.equal(h.writes, 2);
      } finally { h.dispose(); }
    });
  }
}

test("unified navigation never consumes wheel events outside the plot and overview or horizontal gestures", () => {
  const h = harness();
  try {
    for (const role of ["primary", "subview"]) {
      const view = h.views[role];
      for (const target of [view.display, view.action("fit"), { closest: () => null }]) {
        const event = h.event(target, { ctrlKey: true, deltaY: -100 });
        h.root.emit("wheel", event);
        assert.equal(event.defaultPrevented, undefined);
      }
      for (const target of [view.scroll, view.axis]) {
        const event = h.event(target, { ctrlKey: true, deltaY: 10, deltaX: 100 });
        h.root.emit("wheel", event);
        assert.equal(event.defaultPrevented, undefined);
      }
    }
    assert.equal(h.frames.size, 0); assert.equal(h.writes, 0);
  } finally { h.dispose(); }
});

for (const role of ["primary", "subview"]) {
  for (const modifier of ["ctrlKey", "metaKey", "altKey"]) {
    test(`${role} ${modifier} + blank drag is not claimed for panning`, () => {
      const h = harness();
      try {
        const event = h.event(h.views[role].scroll, { [modifier]: true });
        h.root.emit("pointerdown", event);
        assert.notEqual(event.defaultPrevented, true);
        assert.equal(h.root.hasPointerCapture(1), false);
        assert.equal(h.win.count("pointermove"), 0);
        assert.equal(h.writes, 0);
      } finally { h.dispose(); }
    });
  }
  for (const targetSelector of [VIEW_CONTIG_TARGET, VIEW_CONTROL_TARGET]) {
    test(`${role} Contig/control targets retain their own drag and click actions: ${targetSelector}`, () => {
      const h = harness();
      try {
        const scroll = h.views[role].scroll;
        const target = { closest: selector => selector === targetSelector ? target : scroll.closest(selector) };
        for (const modifiers of [{}, { ctrlKey: true }, { metaKey: true }]) {
          const event = h.event(target, modifiers);
          h.root.emit("pointerdown", event);
          assert.notEqual(event.defaultPrevented, true);
          assert.equal(h.root.hasPointerCapture(1), false);
          assert.equal(h.win.count("pointermove"), 0);
        }
      } finally { h.dispose(); }
    });
  }
}

for (const role of ["primary", "subview"]) {
  test(`${role} rebuilding navigation keeps unified gestures without recreating a mode switch`, () => {
    const h = harness();
    try {
      const view = h.views[role];
      view.bar.remove();
      h.bind();
      const html = h.renderedNavigation.at(-1);
      assert.doesNotMatch(html, /toggle-mode|role="switch"|view-nav-mode/);
      h.root.emit("pointerdown", h.event(view.scroll));
      assert.equal(h.root.dataset.viewNavigationGesture, "pan");
    } finally { h.dispose(); }
  });
  test(`${role} blank pan owns the capture cursor through movement and refreshes`, () => {
    const h = harness();
    try {
      const view = h.views[role];
      h.root.emit("pointerdown", h.event(view.scroll));
      assert.equal(h.root.hasPointerCapture(1), true);
      assert.equal(h.root.dataset.viewNavigationGesture, "pan");
      for (const clientX of [190, 170, 220, 180]) {
        h.win.emit("pointermove", h.event(h.root, { clientX }));
        view.scroll.emit("scroll"); h.bind();
        assert.equal(h.root.dataset.viewNavigationGesture, "pan");
        assert.equal(view.scroll.dataset.viewInteractionMode, undefined);
        assert.equal(view.scroll.classList.values.has("is-view-panning"), true);
      }
      assert.equal(view.scroll.scrollLeft, 220);
      assert.equal(h.writes, 0);
      h.win.emit("pointerup", h.event(h.root, { clientX: 180 }));
      assert.equal(h.root.hasPointerCapture(1), false);
      assert.equal(h.root.dataset.viewNavigationGesture, undefined);
      assert.equal(view.scroll.classList.values.has("is-view-panning"), false);
    } finally { h.dispose(); }
  });
  for (const kind of ["window", "left", "right"]) {
    test(`${role} overview ${kind} retains the capture cursor through range refreshes`, () => {
      const h = harness();
      try {
        const view = h.views[role];
        const target = kind === "window" ? view.selection : {
          dataset: { viewNavEdge: kind },
          closest(selector) {
            return selector === "[data-view-navigation]" ? view.bar : selector === "[data-view-nav-edge]" ? this : null;
          },
        };
        h.root.emit("pointerdown", h.event(target));
        assert.equal(h.root.dataset.viewNavigationGesture, kind);
        assert.equal(h.root.hasPointerCapture(1), true);
        for (const clientX of [210, 220]) {
          h.win.emit("pointermove", h.event(h.root, { clientX }));
          h.flush(); h.bind();
          assert.equal(h.root.dataset.viewNavigationGesture, kind);
          assert.equal(view.scroll.dataset.viewInteractionMode, undefined);
        }
        h.win.emit("pointerup", h.event(h.root, { clientX: 220 }));
        assert.equal(h.root.dataset.viewNavigationGesture, undefined);
        assert.equal(h.root.hasPointerCapture(1), false);
      } finally { h.dispose(); }
    });
  }
}

test("wheel is coalesced, excludes controls and becomes inert after unbinding", () => {
  const h = harness();
  for (let i = 0; i < 30; i++) h.root.emit("wheel", h.event(h.views.primary.scroll, { ctrlKey: true, deltaY: -1 }));
  assert.equal(h.frames.size, 1); assert.equal(h.writes, 0);
  h.flush(); assert.equal(h.writes, 1); assert.equal(h.renders, 1);
  h.root.emit("wheel", h.event({ closest: () => ({}) }, { ctrlKey: true, deltaY: -100 }));
  assert.equal(h.frames.size, 0);
  h.root.emit("wheel", h.event(h.views.primary.scroll, { ctrlKey: true, deltaY: -10 }));
  h.dispose(); assert.equal(h.frames.size, 0); assert.equal(h.win.count("pointermove"), 0);
});

for (const termination of ["pointerup", "pointercancel", "lostpointercapture", "blur", "replacement", "removal", "unbind"]) {
  test(`blank pan cleans capture/listeners on ${termination} without store edits`, () => {
    const h = harness();
    try {
      h.root.emit("pointerdown", h.event(h.views.primary.scroll));
      assert.equal(h.win.count("pointermove"), 1); assert.equal(h.win.count("blur"), 1);
      h.win.emit("pointermove", h.event(h.views.primary.scroll, { clientX: 170 }));
      assert.equal(h.views.primary.scroll.scrollLeft, 230); assert.equal(h.writes, 0);
      if (termination === "replacement") { h.views.primary.scroll.isConnected = false; h.observer.callback(); }
      else if (termination === "removal") { h.root.isConnected = false; h.observer.callback(); }
      else if (termination === "unbind") h.dispose();
      else if (termination === "lostpointercapture") h.root.emit(termination, h.event(h.root));
      else h.win.emit(termination, h.event(h.views.primary.scroll));
      for (const name of ["pointermove", "pointerup", "pointercancel", "blur"]) assert.equal(h.win.count(name), 0, name);
      assert.equal(h.observer.active, false); assert.equal(h.writes, 0);
      assert.equal(h.root.dataset.viewNavigationGesture, undefined);
      assert.equal(h.root.hasPointerCapture(1), false);
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
    h.root.emit("wheel", h.event(h.views.primary.scroll, { ctrlKey: true, deltaY: -20 })); h.flush();
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
    h.root.emit("wheel", h.event(h.views.primary.scroll, { ctrlKey: true, deltaY: -100 }));
    const state = h.store.getState();
    h.store.setState({ ...state, assembly: { ...state.assembly, selectedChrName: "Chr2" } });
    h.flush();
    assert.equal(h.writes, 1);
    assert.equal(h.store.getState().assembly.trackView.visibleSpanBp, 500);
  } finally { h.dispose(); }
});


test("legacy tick events cannot restore manual mode or change window geometry", () => {
  const h = harness();
  try {
    const input = h.ticks.trackView.input;
    input.value = "100.25"; h.root.emit("keydown", h.event(input, { key: "Enter" }));
    const manual = h.store.getState().assembly.trackView;
    assert.equal(manual.tickMode, "auto"); assert.equal(manual.tickIntervalBp, 100250);
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

test("explicit empty primary content disables navigation without fabricating a window", () => {
  const h = harness();
  try {
    h.views.primary.scroll.dataset.viewNavigationContent = "0";
    for (const action of ["left", "right", "fit"]) h.views.primary.action(action);
    h.bind();
    assert.equal(h.views.primary.display.textContent, "—");
    for (const action of ["left", "right", "fit"]) assert.equal(h.views.primary.action(action).disabled, true);
    assert.equal(h.views.primary.selection.attrs["aria-disabled"], "true");
    assert.equal(h.views.primary.selection.attrs.tabindex, "-1");
    const before = JSON.stringify(h.store.getState());
    h.root.emit("wheel", h.event(h.views.primary.scroll, { ctrlKey: true, deltaY: -100 })); h.flush();
    h.root.emit("click", h.event(h.views.primary.action("fit")));
    assert.equal(JSON.stringify(h.store.getState()), before);
    assert.equal(h.writes, 0);
  } finally { h.dispose(); }
});

for (const role of ["primary", "subview"]) {
  test(`${role} window text and tooltip follow short, long and unavailable spans without committing input`, () => {
    const h = harness();
    try {
      const view = h.views[role];
      const domainKey = role === "primary" ? "trackDomainSpanBp" : "subviewDomainSpanBp";
      const otherRole = role === "primary" ? "subview" : "primary";
      for (const [domain, expected, precise] of [
        ["1000", "500 bp", "500 bp"],
        ["5000", "2.5 kb", "2,500 bp"],
        ["5000000", "2.5 Mb", "2,500,000 bp"],
        ["128109774", "64.05 Mb", "64,054,887 bp"],
        ["246913578024", "123.46 Gb", "123,456,789,012 bp"],
        ["2000000000000", "1 Tb", "1,000,000,000,000 bp"],
      ]) {
        view.scroll.dataset[domainKey] = domain;
        h.bind();
        assert.equal(view.display.textContent, expected);
        assert.equal(view.display.getAttribute("data-app-tooltip"), precise);
      }
      assert.equal(h.views[otherRole].display.textContent, "500 bp");
      h.root.emit("change", h.event(view.display));
      h.root.emit("keydown", h.event(view.display, { key: "Enter" }));
      assert.equal(h.writes, 0);
      view.scroll.dataset[domainKey] = "0";
      h.bind();
      assert.equal(view.display.textContent, "—");
      assert.equal(view.display.getAttribute("data-app-tooltip"), "—");
      assert.ok(view.action("left").disabled);
    } finally { h.dispose(); }
  });
}

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
  test(`${role} transparent compact target pans instead of resizing without a mode switch`, () => {
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
      assert.equal(view.scroll.dataset.viewInteractionMode, undefined);
      assert.equal(h.win.count("pointermove"), 0);
    } finally { h.dispose(); }
  });
}

for (const role of ["primary", "subview"]) {
  test(`${role} repeated slider key navigation restores equivalent focus after replacement`, () => {
    const h = harness();
    try {
      const view = h.views[role]; view.scroll.scrollWidth = 100000; h.bind();
      const renderKey = role === "primary" ? "rerenderAssemblyMainTab" : "rerenderSubviewPanel";
      h.deps[renderKey] = () => { h.root.ownerDocument.activeElement = null; };
      view.selection.focus();
      for (let n = 0; n < 3; n++) {
        h.root.emit("keydown", h.event(h.root.ownerDocument.activeElement, { key: "ArrowRight" }));
        assert.equal(h.root.ownerDocument.activeElement, view.selection);
      }
      assert.equal(h.writes, 3);
      assert.equal(h.store.getState().assembly[role === "primary" ? "trackView" : "subviewTrackView"].visibleSpanBp, 500);
    } finally { h.dispose(); }
  });
  test(`${role} focused half-window button is restored to replacement rather than detached node`, () => {
    const h = harness();
    try {
      const view = h.views[role], old = view.action("right");
      const replacement = { focus() { h.root.ownerDocument.activeElement = this; } };
      h.root.ownerDocument.activeElement = old;
      const renderKey = role === "primary" ? "rerenderAssemblyMainTab" : "rerenderSubviewPanel";
      const originalQuery = view.bar.querySelector;
      h.deps[renderKey] = () => {
        h.root.ownerDocument.activeElement = null;
        view.bar.querySelector = selector => selector === "[data-view-nav-action='right']" ? replacement : originalQuery(selector);
      };
      h.root.emit("click", h.event(old));
      assert.equal(h.root.ownerDocument.activeElement, replacement);
    } finally { h.dispose(); }
  });
}


for (const role of ["primary", "subview"]) {
  for (const direction of ["left", "right"]) {
    test(`${role} half-window boundary restores slider focus instead of disabled replacement`, () => {
      const h = harness();
      try {
        const view = h.views[role], old = view.action(direction);
        view.scroll.scrollLeft = direction === "left" ? 100 : 900;
        h.bind();
        const replacement = { disabled: false, focus() { assert.fail("disabled control cannot receive focus"); } };
        h.root.ownerDocument.activeElement = old;
        const renderKey = role === "primary" ? "rerenderAssemblyMainTab" : "rerenderSubviewPanel";
        const originalQuery = view.bar.querySelector;
        h.deps[renderKey] = () => {
          h.root.ownerDocument.activeElement = null;
          view.bar.querySelector = selector => selector === `[data-view-nav-action='${direction}']` ? replacement : originalQuery(selector);
        };
        h.root.emit("click", h.event(old));
        assert.equal(replacement.disabled, true);
        assert.equal(h.root.ownerDocument.activeElement, view.selection);
        h.root.emit("keydown", h.event(view.selection, { key: direction === "left" ? "ArrowRight" : "ArrowLeft" }));
        assert.equal(h.root.ownerDocument.activeElement, view.selection);
      } finally { h.dispose(); }
    });
  }
}


for (const [role, viewKey] of [["primary", "trackView"], ["subview", "subviewTrackView"]]) {
  test(`${role} Full range persists overview mode and an explicit zoom exits it`, () => {
    const h = harness();
    try {
      h.root.emit("click", h.event(h.views[role].action("fit")));
      assert.equal(h.store.getState().assembly[viewKey].fullRange, true);
      assert.equal(h.store.getState().assembly[viewKey].allowSubViewportScale, true);
      h.root.emit("wheel", h.event(h.views[role].scroll, { ctrlKey: true, deltaY: -100 }));
      h.flush();
      assert.notEqual(h.store.getState().assembly[viewKey].fullRange, true);
    } finally { h.dispose(); }
  });
}


test("tick options close after 400ms, cancel on return, and dispose pending close timers", () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  const timers = new Map(); let id = 0;
  const h = harness();
  const panel = { hidden: false }, input = { setAttribute() {}, removeAttribute() {} }, toggle = { setAttribute() {} };
  const control = { querySelector: selector => selector === "[data-view-tick-options]" ? panel
    : selector === "[data-view-tick-interval]" ? input : toggle,
    contains: node => node === child };
  const child = { closest: selector => selector === "[data-view-tick-control]" ? control : null };
  try {
    globalThis.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
    globalThis.clearTimeout = timer => timers.delete(timer);
    h.root.emit("pointerout", h.event(child, { relatedTarget: child })); assert.equal(timers.size, 0);
    h.root.emit("pointerout", h.event(child, { relatedTarget: null }));
    assert.equal([...timers.values()][0].delay, 400); assert.equal(panel.hidden, false);
    h.root.emit("pointerover", h.event(child)); assert.equal(timers.size, 0);
    h.root.emit("pointerout", h.event(child, { relatedTarget: null }));
    const callback = [...timers.values()][0].callback; timers.clear(); callback(); assert.equal(panel.hidden, true);
    h.root.emit("pointerout", h.event(child, { relatedTarget: null }));
    h.dispose(); assert.equal(timers.size, 0);
  } finally { h.dispose(); globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
});

for (const role of ["primary", "subview"]) {
  test(`${role} navigation suppresses default menus without altering view state or gesture owners`, () => {
    const h = harness();
    try {
      const view = h.views[role];
      const before = h.store.getState(), writes = h.writes;
      const background = { closest: selector => selector === "[data-view-navigation]" ? view.bar : null };
      for (const target of [background, view.axis, view.selection, view.grip, view.action("left")]) {
        const event = h.event(target, { button: 2 });
        h.root.emit("contextmenu", event);
        assert.equal(event.defaultPrevented, true);
      }
      assert.equal(h.store.getState(), before);
      assert.equal(h.writes, writes);
      assert.equal(h.renders, 0);
      for (let i = 0; i < 5; i++) h.bind();
      assert.equal(h.root.count("contextmenu"), 1);
    } finally { h.dispose(); }
    assert.equal(h.root.count("contextmenu"), 0);
  });
}

test("navigation menu guard leaves editable controls and unrelated business targets alone", () => {
  const h = harness();
  try {
    const field = { closest(selector) {
      return selector === "[data-view-navigation]" ? h.views.primary.bar : this;
    } };
    const contig = { closest() { return null; } };
    const otherRole = { closest: selector => selector === "[data-view-navigation]"
      ? { dataset: { viewNavigation: "final-path" } } : null };
    for (const target of [field, contig, otherRole]) {
      const event = h.event(target, { button: 2 });
      h.root.emit("contextmenu", event);
      assert.notEqual(event.defaultPrevented, true);
    }
  } finally { h.dispose(); }
});


test("Main navigation does not claim a floating Local View's blank pan gesture", () => {
  const h = harness();
  try {
    const local = { dataset: { localViewWindow: "local-test" } };
    const scroll = h.views.subview.scroll, original = scroll.closest;
    scroll.closest = selector => selector === "[data-local-view-window]" ? local : original(selector);
    const before = h.writes;
    h.root.emit("pointerdown", h.event(scroll));
    assert.equal(h.writes, before);
    assert.equal(h.win.count("pointermove"), 0);
  } finally { h.dispose(); }
});

test("a gesture already claimed by drag-to-Final-Path cannot also start panning", () => {
  const h = harness();
  try {
    h.root.emit("pointerdown", h.event(h.views.primary.scroll, { defaultPrevented: true }));
    assert.equal(h.win.count("pointermove"), 0);
  } finally { h.dispose(); }
});


for (const role of ["primary", "subview"]) {
  for (const target of ["scroll", "axis"]) {
    test(`${role} ${target} ordinary wheel remains native page scrolling`, () => {
      const h = harness();
      try {
        const initial = h.store.getState();
        for (const modifiers of [{}, { ctrlKey: false }, { metaKey: true }, { shiftKey: true }, { altKey: true }]) {
          for (const deltaY of [-100, 100]) {
            const event = h.event(h.views[role][target], { deltaY, ...modifiers });
            h.root.emit("wheel", event);
            assert.equal(event.defaultPrevented, undefined);
            assert.equal(event.propagationStopped, undefined);
          }
        }
        assert.equal(h.frames.size, 0);
        assert.equal(h.writes, 0);
        assert.equal(h.renders, 0);
        assert.equal(h.persists, 0);
        assert.equal(h.store.getState(), initial);
      } finally { h.dispose(); }
    });
  }
}

test("ordinary wheel cannot add to an already queued Ctrl zoom", () => {
  const h = harness();
  try {
    h.root.emit("wheel", h.event(h.views.primary.scroll, { ctrlKey: true, deltaY: -100 }));
    const pending = h.frames.size;
    const event = h.event(h.views.primary.scroll, { ctrlKey: false, deltaY: 1000 });
    h.root.emit("wheel", event);
    assert.equal(event.defaultPrevented, undefined);
    assert.equal(h.frames.size, pending);
    h.flush();
    assert.equal(h.writes, 1);
    assert.ok(h.store.getState().assembly.trackView.visibleSpanBp < 500);
  } finally { h.dispose(); }
});

test("Local render covers allow ordinary scrolling but block Ctrl zoom and graph edits", () => {
  const node = new Events();
  blockSubviewRenderInput(node);
  for (const [type, ctrlKey, blocked] of [["wheel", false, false], ["wheel", true, true],
    ["pointerdown", false, true], ["click", false, true], ["keydown", false, true]]) {
    const event = { ctrlKey, preventDefault() { this.defaultPrevented = true; },
      stopPropagation() { this.propagationStopped = true; } };
    node.emit(type, event);
    assert.equal(Boolean(event.defaultPrevented), blocked);
    assert.equal(Boolean(event.propagationStopped), blocked);
  }
});

test("navigation help describes Ctrl-only wheel zoom in both languages", () => {
  for (const locale of ["zh", "en"]) {
    const labels = viewNavText(locale);
    for (const key of ["interaction", "axis"]) {
      assert.match(labels[key], locale === "zh" ? /Ctrl \+ 滚轮缩放/ : /Ctrl \+ wheel to zoom/);
      assert.match(labels[key], locale === "zh" ? /普通滚轮上下滚动/ : /plain wheel scrolls vertically/);
    }
  }
});
