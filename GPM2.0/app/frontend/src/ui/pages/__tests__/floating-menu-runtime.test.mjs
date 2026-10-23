import test from "node:test";
import assert from "node:assert/strict";
import { FLOATING_MENU_CLOSE_DELAY_MS, scheduleDelayedFloatingClose } from "../floating-menu-runtime.js";

test("floating menus retain the default grace period unless explicitly overridden", () => {
  const owner = {}, key = Symbol("close"), timers = new Map();
  let closed = false;
  scheduleDelayedFloatingClose(owner, key, () => { closed = true; }, {
    setTimeout(callback, delay) { timers.set(1, { callback, delay }); return 1; },
    clearTimeout(id) { timers.delete(id); },
  });
  assert.equal(closed, false);
  assert.equal(timers.get(1).delay, FLOATING_MENU_CLOSE_DELAY_MS);
  timers.get(1).callback();
  assert.equal(closed, true);
  assert.equal(owner[key], null);
});

test("an explicit zero closes synchronously and cancels any previous departure timer", () => {
  const key = Symbol("close"), owner = { [key]: 17 }, cancelled = [];
  let closed = false;
  scheduleDelayedFloatingClose(owner, key, () => { closed = true; }, {
    delayMs: 0,
    setTimeout() { assert.fail("immediate close must not schedule a timer"); },
    clearTimeout(id) { cancelled.push(id); },
  });
  assert.equal(closed, true);
  assert.deepEqual(cancelled, [17]);
  assert.equal(owner[key], null);
});
