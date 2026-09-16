import test from "node:test";
import assert from "node:assert/strict";
import { bindMarkerDisplayMenus } from "../marker-display-menu-runtime.js";
import { scheduleDelayedFloatingClose, cancelDelayedFloatingClose } from "../../floating-menu-runtime.js";

function fixture() {
  const events = new Map(), timers = new Map();
  let nextTimer = 0, focusCount = 0;
  const panel = { hidden: true };
  const root = {
    querySelector: selector => selector === "[data-marker-display-toggle]" ? button : panel,
    contains: node => [root, button, input, panel].includes(node),
    closest: () => root,
  };
  const button = {
    expanded: "false",
    closest: selector => selector === "[data-marker-display-toggle]" ? button : root,
    getAttribute: () => button.expanded,
    setAttribute: (_name, value) => { button.expanded = value; },
    focus: () => { focusCount += 1; },
  };
  const input = { closest: selector => selector === ".assembly-marker-display" ? root : null };
  const host = {
    querySelectorAll: () => [root],
    addEventListener(type, callback) {
      const list = events.get(type) || [];
      list.push(callback); events.set(type, list);
    },
  };
  const options = {
    setTimeout: (callback, delay) => { const id = ++nextTimer; timers.set(id, { callback, delay }); return id; },
    clearTimeout: id => timers.delete(id),
  };
  const fire = (type, target = button, extra = {}) => {
    const event = { target, preventDefault() {}, stopPropagation() {}, ...extra };
    events.get(type)?.forEach(callback => callback(event));
  };
  const flush = () => { const pending = [...timers.values()]; timers.clear(); pending.forEach(timer => timer.callback()); };
  bindMarkerDisplayMenus(host, options);
  return { host, options, root, button, panel, input, timers, events, fire, flush, focusCount: () => focusCount };
}

test("repeated menu opens and rebinding have one owner and preserve checkbox focus", () => {
  const f = fixture();
  bindMarkerDisplayMenus(f.host, f.options);
  const nested = { parentElement: f.host, addEventListener() { assert.fail("nested owner"); } };
  bindMarkerDisplayMenus(nested, f.options);
  assert.equal(f.events.get("click").length, 1);
  for (let i = 0; i < 30; i++) {
    f.fire("click");
    assert.equal(f.panel.hidden, false);
    assert.equal(f.button.expanded, "true");
    f.fire("click", f.input);
    assert.equal(f.panel.hidden, false);
    f.fire("click");
    assert.equal(f.panel.hidden, true);
  }
  assert.equal(f.focusCount(), 0);
});

test("pointer departure closes after 400ms; returning or moving inside cancels dismissal", () => {
  const f = fixture();
  f.fire("click");
  f.fire("pointerout", f.input, { relatedTarget: f.button });
  assert.equal(f.timers.size, 0);
  f.fire("pointerout", f.input, { relatedTarget: null });
  assert.equal(f.panel.hidden, false);
  assert.equal([...f.timers.values()][0].delay, 400);
  f.fire("pointerover", f.button);
  f.flush();
  assert.equal(f.panel.hidden, false);
  f.fire("pointerout", f.input, { relatedTarget: null });
  f.flush();
  assert.equal(f.panel.hidden, true);
  assert.equal(f.button.expanded, "false");
});

test("focusout never hides synchronously; focus reentry cancels; Escape and outside click dismiss", () => {
  const f = fixture();
  f.fire("click");
  f.fire("focusout", f.input, { relatedTarget: null });
  assert.equal(f.panel.hidden, false);
  f.fire("focusin", f.button);
  f.flush();
  assert.equal(f.panel.hidden, false);
  f.fire("keydown", f.input, { key: "Escape" });
  assert.equal(f.panel.hidden, true);
  assert.equal(f.focusCount(), 1);
  f.fire("click");
  f.fire("pointerdown", { closest: () => null });
  assert.equal(f.panel.hidden, true);
  assert.equal(f.timers.size, 0);
});

test("floating-menu timers retain the browser global receiver", () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  const owner = {};
  try {
    globalThis.setTimeout = function () { assert.equal(this, globalThis); return 99; };
    globalThis.clearTimeout = function (id) { assert.equal(this, globalThis); assert.equal(id, 99); };
    scheduleDelayedFloatingClose(owner, "timer", () => {});
    cancelDelayedFloatingClose(owner, "timer");
    assert.equal(owner.timer, null);
  } finally {
    globalThis.setTimeout = originalSet;
    globalThis.clearTimeout = originalClear;
  }
});
