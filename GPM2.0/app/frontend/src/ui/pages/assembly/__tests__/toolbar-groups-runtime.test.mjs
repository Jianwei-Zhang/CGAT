import test from "node:test";
import assert from "node:assert/strict";
import { bindToolbarGroups } from "../toolbar-groups-runtime.js";

function events(target = {}) {
  const listeners = new Map();
  return Object.assign(target, {
    addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(fn); },
    removeEventListener(type, fn) { listeners.get(type)?.delete(fn); },
    emit(type, event = {}) { for (const fn of listeners.get(type) || []) fn(event); },
    count() { return [...listeners.values()].reduce((sum, set) => sum + set.size, 0); },
  });
}
function fixture() {
  let resize;
  const observed = new Set();
  const win = events({ innerWidth: 1200, innerHeight: 800, getComputedStyle: () => ({ columnGap: "8px" }),
    ResizeObserver: class { constructor(fn) { resize = fn; } observe(node) { observed.add(node); } disconnect() { observed.clear(); } } });
  const doc = events({ defaultView: win, activeElement: null, fonts: events() });
  const groups = ["display", "filter", "edit"].map((kind, index) => {
    const attrs = new Map();
    const buttonAttrs = new Map();
    const group = { dataset: { toolbarGroup: kind },
      matches: selector => selector === "[data-toolbar-group]",
      hasAttribute: key => attrs.has(key), setAttribute: (key, value) => attrs.set(key, value), removeAttribute: key => attrs.delete(key),
      toggleAttribute(key, on) { if (on) attrs.set(key, ""); else attrs.delete(key); },
      getBoundingClientRect() { return { width: [400, 500, 200][index] }; },
      contains(target) { return target === group || target === button || target === panel || target === input; },
      querySelector(selector) { return selector === "[data-toolbar-group-content]" ? panel : selector === "[data-toolbar-group-toggle]" ? button : null; },
    };
    const button = { ownerDocument: doc, setAttribute: (key, value) => buttonAttrs.set(key, value),
      getAttribute: key => buttonAttrs.get(key), focus() { doc.activeElement = button; },
      closest: selector => selector === "[data-toolbar-group]" ? group : selector === "[data-toolbar-group-toggle]" ? button : null,
      getBoundingClientRect: () => ({ width: 40, left: 40, right: 80, top: 40, bottom: 72 }),
    };
    const input = { value: "10000", closest: selector => selector === "[data-toolbar-group]" ? group : null };
    const panel = { style: {}, scrollHeight: 150, contains: target => target === input,
      getBoundingClientRect: () => ({ width: 320, height: 150 }),
    };
    return Object.assign(group, { button, panel, input });
  });
  const toolbar = { clientWidth: 1200, children: groups };
  const host = events({ ownerDocument: doc, querySelectorAll: selector => selector === "[data-toolbar-group]" ? groups : [toolbar] });
  return { host, groups, toolbar, doc, win, resize: () => resize(), observed };
}

test("live toolbar compacts without cloning fields, supports keyboard/outside close, and expands again", () => {
  const f = fixture();
  const dispose = bindToolbarGroups(f.host);
  assert.equal(f.observed.size, 1);
  assert.ok(f.groups.every(group => !group.hasAttribute("data-toolbar-compact")));
  const edit = f.groups[2], filter = f.groups[1];
  f.toolbar.clientWidth = 1000; f.resize();
  assert.equal(edit.hasAttribute("data-toolbar-compact"), true);
  assert.equal(filter.hasAttribute("data-toolbar-compact"), false);
  assert.equal(edit.button.getAttribute("aria-expanded"), "false");
  f.host.emit("click", { target: edit.button });
  assert.equal(edit.button.getAttribute("aria-expanded"), "true");
  assert.equal(edit.panel.style.position, "fixed");
  f.doc.activeElement = edit.input;
  let prevented = false;
  f.host.emit("keydown", { key: "Escape", target: edit.input, preventDefault() { prevented = true; } });
  assert.equal(prevented, true); assert.equal(f.doc.activeElement, edit.button);
  assert.equal(edit.hasAttribute("data-toolbar-group-open"), false);
  f.host.emit("click", { target: edit.button });
  f.doc.emit("pointerdown", { target: filter.input });
  assert.equal(edit.hasAttribute("data-toolbar-group-open"), false);
  const input = filter.input;
  f.doc.activeElement = input;
  f.toolbar.clientWidth = 600; f.resize();
  assert.equal(filter.hasAttribute("data-toolbar-compact"), true);
  assert.equal(f.doc.activeElement, filter.button);
  f.host.emit("click", { target: filter.button }); input.value = "12000";
  f.toolbar.clientWidth = 1200; f.resize();
  assert.equal(filter.input, input); assert.equal(input.value, "12000");
  assert.equal(filter.hasAttribute("data-toolbar-compact"), false);
  assert.equal(filter.panel.style.position, "");
  const counts = [f.host.count(), f.doc.count(), f.win.count()];
  bindToolbarGroups(f.host);
  assert.deepEqual([f.host.count(), f.doc.count(), f.win.count()], counts);
  dispose();
  assert.equal(f.observed.size, 0);
  assert.deepEqual([f.host.count(), f.doc.count(), f.win.count()], [0, 0, 0]);
});
