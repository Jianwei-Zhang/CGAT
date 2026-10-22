import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { bindShellSelects, syncShellSelect, renderShellSelect } from "../shell-select-runtime.js";

function fixture() {
  const doc = { activeElement: null, defaultView: { Event }, handlers: new Map() };
  function element() {
    const classes = new Set(), handlers = new Map();
    return { ownerDocument: doc, attrs: {}, dataset: {}, style: { getPropertyValue: () => "", setProperty() {} }, children: [],
      classList: { add: key => classes.add(key), remove: key => classes.delete(key), contains: key => classes.has(key),
        toggle(key, on) { on ? classes.add(key) : classes.delete(key); } },
      setAttribute(key, value) { this.attrs[key] = value; }, getAttribute(key) { return this.attrs[key]; },
      addEventListener(type, handler) { const list = handlers.get(type) || new Set(); list.add(handler); handlers.set(type, list); },
      removeEventListener(type, handler) { handlers.get(type)?.delete(handler); },
      emit(type, extra = {}) { const event = { type, target: this, preventDefault() {}, ...extra }; for (const handler of [...handlers.get(type) || []]) handler(event); },
      dispatchEvent(event) { for (const handler of [...handlers.get(event.type) || []]) handler(event); },
      replaceChildren(...children) { this.children = children; },
      focus() { doc.activeElement = this; },
      closest(selector) { return selector === "[data-shell-option-index]" ? this : null; },
      handlers,
    };
  }
  Object.assign(doc, element()); doc.createElement = element;
  const select = element(), menu = element(), toggle = element(), caption = element(), combo = element(), root = element();
  select.options = [{ value: "a", textContent: "Project A", selected: true }, { value: "b", textContent: "Project <B>", selected: false }];
  Object.defineProperty(select, "value", {
    get() { return this.options.find(option => option.selected)?.value || ""; },
    set(value) { this.options.forEach(option => { option.selected = option.value === value; }); },
  });
  select.setAttribute("aria-label", "Project");
  combo.querySelector = selector => ({ select, "[data-shell-select-toggle]": toggle,
    "[data-shell-select-menu]": menu, "[data-shell-select-caption]": caption })[selector];
  combo.contains = target => [select, menu, toggle, caption, ...menu.children].includes(target);
  root.querySelectorAll = selector => selector === "[data-shell-select]" ? [combo] : [toggle];
  toggle.closest = () => combo;
  bindShellSelects(root);
  return { root, combo, select, menu, toggle, caption, doc, element };
}

test("shell selects render visible custom controls and hidden selects without duplicating switch contracts", () => {
  const html = renderShellSelect("switch", "Project", [{ value: 'a"', label: "<Project>", selected: true }]);
  assert.match(html, /id="switch" hidden aria-hidden="true" tabindex="-1"/);
  assert.match(html, /aria-haspopup="listbox"/); assert.match(html, /class="assembly-track-combo-menu shell-select-menu is-hidden"/);
  assert.match(html, /&lt;Project&gt;/); assert.doesNotMatch(html, /<Project>/);
});

test("shell selection emits the original change once, updates values/captions and syncs async project options", () => {
  const h = fixture(); let changes = 0;
  h.select.addEventListener("change", () => { changes++; });
  h.toggle.emit("click"); assert.equal(h.menu.classList.contains("is-hidden"), false);
  assert.equal(h.doc.activeElement, h.menu.children[0]);
  h.menu.emit("click", { target: h.menu.children[1] });
  assert.equal(changes, 1); assert.equal(h.select.value, "b");
  assert.equal(h.caption.textContent, "Project <B>"); assert.equal(h.doc.activeElement, h.toggle);
  h.toggle.emit("click"); h.menu.emit("click", { target: h.menu.children[1] }); assert.equal(changes, 1);
  h.select.options = [{ value: "c", textContent: "New workspace", selected: true }];
  syncShellSelect(h.select); assert.equal(h.menu.children.length, 1); assert.equal(h.caption.textContent, "New workspace");
  h.select.disabled = true; syncShellSelect(h.select); h.toggle.emit("click");
  assert.equal(h.toggle.disabled, true); assert.equal(h.menu.classList.contains("is-hidden"), true);
});

test("shell lists preserve keyboard navigation, Escape, Tab and outside dismissal across rebinding", () => {
  const h = fixture(); bindShellSelects(h.root);
  assert.equal(h.toggle.handlers.get("click").size, 1);
  h.combo.emit("keydown", { key: "ArrowDown" }); assert.equal(h.doc.activeElement, h.menu.children[0]);
  h.combo.emit("keydown", { key: "End" }); assert.equal(h.doc.activeElement, h.menu.children[1]);
  h.combo.emit("keydown", { key: "Home" }); assert.equal(h.doc.activeElement, h.menu.children[0]);
  h.combo.emit("keydown", { key: "Escape" }); assert.equal(h.menu.classList.contains("is-hidden"), true);
  assert.equal(h.doc.activeElement, h.toggle);
  h.toggle.emit("click"); h.combo.emit("keydown", { key: "Tab" }); assert.equal(h.menu.classList.contains("is-hidden"), true);
  h.toggle.emit("click"); h.doc.emit("pointerdown", { target: {} }); assert.equal(h.menu.classList.contains("is-hidden"), true);
});

test("shell popups use the shared 400ms grace period and cancel stale timers on reopening", () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  const timers = new Map(); let id = 0;
  try {
    globalThis.setTimeout = (callback, delay) => { timers.set(++id, { callback, delay }); return id; };
    globalThis.clearTimeout = key => timers.delete(key);
    const h = fixture(); h.toggle.emit("click");
    h.combo.emit("pointerleave", { relatedTarget: h.menu.children[0] }); assert.equal(timers.size, 0);
    h.combo.emit("pointerleave", { relatedTarget: null }); assert.equal([...timers.values()][0].delay, 400);
    h.combo.emit("pointerenter"); assert.equal(timers.size, 0);
    h.combo.emit("pointerleave", { relatedTarget: null }); h.toggle.emit("click"); h.toggle.emit("click"); assert.equal(timers.size, 0);
    h.combo.emit("pointerleave", { relatedTarget: null });
    const callback = [...timers.values()][0].callback; timers.clear(); callback();
    assert.equal(h.menu.classList.contains("is-hidden"), true);
    // Language rebuild disposes document listeners rather than duplicating them.
    assert.equal(h.doc.handlers.get("pointerdown").size, 1);
    bindShellSelects(h.root); assert.equal(h.doc.handlers.get("pointerdown").size, 1);
  } finally { globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
});


test("shell popups share support-dataset option tokens rather than OS light/dark native styles", () => {
  const css = readFileSync(new URL("../../../styles/shell.css", import.meta.url), "utf8");
  const assembly = readFileSync(new URL("../../../styles/assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.shell-select-toggle\s*\{[^}]*background:\s*var\(--surface-panel, #fff\)/);
  assert.match(css, /\.shell-select-menu[^}]*max-height:/);
  assert.match(assembly, /\.assembly-track-combo-menu\s*\{[^}]*background:\s*var\(--surface-panel, #fff\)/);
  assert.match(assembly, /\.assembly-track-combo-option\s*\{[^}]*color:\s*var\(--theme-ink/);
});
