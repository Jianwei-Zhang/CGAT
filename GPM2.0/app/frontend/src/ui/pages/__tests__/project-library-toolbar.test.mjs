import test from "node:test";
import assert from "node:assert/strict";
import { libraryToolbarOverflow, bindLibraryToolbar } from "../project-library-toolbar.js";

for (const [locale, validateWidth, failedWidth] of [["zh", 28, 64], ["en", 28, 88]]) {
  test(`${locale} measured priority fits wide, medium and narrow headers without duplicate operations`, () => {
    const items = [ { id: "create", width: 28, available: true },
      { id: "validate", width: validateWidth, available: true }, { id: "delete-failed", width: failedWidth, available: true } ];
    assert.deepEqual(libraryToolbarOverflow(400, items), []);
    assert.deepEqual(libraryToolbarOverflow(32 + validateWidth + 4, items), ["delete-failed"]);
    assert.deepEqual(libraryToolbarOverflow(40, items), ["validate", "delete-failed"]);
    assert.deepEqual(libraryToolbarOverflow(0, items), ["create", "validate", "delete-failed"]);
    assert.deepEqual(libraryToolbarOverflow(40, items.map(item => ({ ...item, available: item.id !== "delete-failed" }))), ["validate"]);
  });
}

test("toolbar responds to sidebar width, live failure availability and menu disabled states", () => {
  const observers = [], changes = [];
  class Observer { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} disconnect() { this.disconnected = true; } }
  const view = { ResizeObserver: Observer, MutationObserver: Observer,
    getComputedStyle: () => ({ columnGap: "4" }), addEventListener() {}, removeEventListener() {} };
  let width = 400;
  const commands = ["create", "validate", "delete-failed"];
  const buttons = commands.map((id, index) => ({ hidden: index === 2, disabled: false, getBoundingClientRect: () => ({ width: [28, 28, 88][index] }) }));
  const slots = commands.map((id, index) => ({ dataset: { libraryCommand: id }, hidden: false, querySelector: () => buttons[index] }));
  const menuItems = commands.map(id => ({ dataset: { libraryOverflowAction: id }, hidden: true }));
  const title = { scrollWidth: 64, parentElement: {} }, count = { getBoundingClientRect: () => ({ width: 24 }) };
  const more = { getBoundingClientRect: () => ({ width: 28 }) };
  const header = { isConnected: true, ownerDocument: { defaultView: view }, getBoundingClientRect: () => ({ width }),
    querySelector: selector => ({ ".project-library-toolbar": {}, ".project-recents-title-label": title, ".project-count": count, "[data-library-root-menu]": more }[selector]),
    querySelectorAll: () => slots };
  const host = { querySelector: () => header, querySelectorAll: () => menuItems };
  const dispose = bindLibraryToolbar(host, actions => changes.push(actions));
  assert.deepEqual(changes.at(-1), []);
  assert.deepEqual(slots.map(slot => slot.hidden), [false, false, true]);
  width = 220; observers[0].callback();
  assert.deepEqual(changes.at(-1), [], "both icon actions fit without overflowing validation");
  width = 180; observers[0].callback();
  assert.deepEqual(changes.at(-1), ["validate"]);
  assert.deepEqual(menuItems.map(item => item.hidden), [true, false, true]);
  buttons[2].hidden = false; observers[1].callback();
  assert.deepEqual(changes.at(-1), ["validate", "delete-failed"]);
  buttons[1].disabled = true; observers[1].callback(); assert.equal(menuItems[1].disabled, true);
  width = 400; observers[0].callback();
  assert.deepEqual(changes.at(-1), []);
  assert.deepEqual(slots.map(slot => slot.hidden), [false, false, false]);
  assert.ok(menuItems.every(item => item.hidden));
  // Widths are measured again, not cached from the former locale.
  title.scrollWidth = 200; observers[0].callback();
  assert.deepEqual(changes.at(-1), ["delete-failed"]);
  dispose(); assert.ok(observers.every(observer => observer.disconnected));
});
