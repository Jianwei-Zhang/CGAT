import test from "node:test";
import assert from "node:assert/strict";
import { bindSupportDatasetPicker } from "../support-dataset-picker-runtime.js";

function setup() {
  const doc = { activeElement: null, defaultView: { Event } };
  const node = (dataset = {}, textContent = "") => {
    const handlers = new Map();
    const classes = new Set();
    return {
      dataset, textContent, attributes: {}, ownerDocument: doc,
      classList: { contains: key => classes.has(key), toggle(key, active) { active ? classes.add(key) : classes.delete(key); } },
      setAttribute(key, value) { this.attributes[key] = value; },
      addEventListener(type, handler) { if (!handlers.has(type)) handlers.set(type, []); handlers.get(type).push(handler); },
      dispatchEvent(event) { for (const handler of handlers.get(event.type) || []) handler(event); },
      emit(type, detail = {}) {
        const event = { type, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, ...detail };
        this.dispatchEvent(event); return event;
      },
      focus() { doc.activeElement = this; },
    };
  };
  const toggle = node({ supportDatasetLabel: "辅 ds" });
  const options = [22, 33, 44].map(id => node({ supportDatasetOption: String(id) }, `ds-${id}`));
  const select = node(); select.value = "22";
  const combo = node();
  combo.contains = target => [select, toggle, ...options].includes(target);
  combo.querySelector = () => toggle;
  combo.querySelectorAll = () => options;
  select.closest = () => combo;
  const changes = [];
  select.addEventListener("change", event => changes.push({ value: select.value, bubbles: event.bubbles }));
  let closedOthers = 0;
  const bind = () => bindSupportDatasetPicker({
    select,
    setOpen(target, open) { target.classList.toggle("is-open", open); toggle.setAttribute("aria-expanded", String(open)); },
    closeOthers() { closedOthers++; },
  });
  bind();
  return { doc, select, toggle, options, combo, changes, bind, closedOthers: () => closedOthers };
}

test("dataset choices reuse the select change contract, update the caption, and skip unchanged selections", () => {
  const h = setup(); h.toggle.emit("click");
  assert.equal(h.combo.classList.contains("is-open"), true);
  assert.equal(h.closedOthers(), 1);
  assert.equal(h.doc.activeElement, h.options[0]);
  h.options[1].emit("click");
  assert.deepEqual(h.changes, [{ value: "33", bubbles: true }]);
  assert.equal(h.toggle.textContent, "ds-33");
  assert.equal(h.toggle.attributes["aria-label"], "辅 ds: ds-33");
  assert.equal(h.options[1].attributes["aria-selected"], "true");
  assert.equal(h.options[0].attributes["aria-selected"], "false");
  assert.equal(h.toggle.attributes["aria-expanded"], "false");
  assert.equal(h.doc.activeElement, h.toggle);
  h.options[1].emit("click");
  assert.equal(h.changes.length, 1);
});

test("dataset keyboard navigation and Escape never change the value before selection", () => {
  const h = setup(); h.toggle.emit("keydown", { key: "ArrowDown" });
  h.options[0].emit("keydown", { key: "ArrowDown" });
  assert.equal(h.doc.activeElement, h.options[1]);
  h.options[1].emit("keydown", { key: "End" });
  assert.equal(h.doc.activeElement, h.options[2]);
  h.options[2].emit("keydown", { key: "Escape" });
  assert.equal(h.doc.activeElement, h.toggle);
  assert.equal(h.toggle.attributes["aria-expanded"], "false");
  assert.deepEqual(h.changes, []);
});

test("Tab and focus leaving the picker dismiss the menu without trapping focus", () => {
  const h = setup(); h.toggle.emit("click");
  const tab = h.options[0].emit("keydown", { key: "Tab" });
  assert.notEqual(tab.defaultPrevented, true);
  assert.equal(h.toggle.attributes["aria-expanded"], "false");
  h.toggle.emit("click");
  h.combo.emit("focusout", { relatedTarget: h.options[1] });
  assert.equal(h.toggle.attributes["aria-expanded"], "true");
  h.combo.emit("focusout", { relatedTarget: {} });
  assert.equal(h.toggle.attributes["aria-expanded"], "false");
});

test("repeated binding is inert and external select changes synchronize the visible picker", () => {
  const h = setup(); h.bind(); h.toggle.emit("click");
  assert.equal(h.closedOthers(), 1);
  assert.equal(h.toggle.attributes["aria-expanded"], "true");
  h.select.value = "44"; h.select.emit("change");
  assert.equal(h.toggle.textContent, "ds-44");
  assert.equal(h.options[2].attributes["aria-selected"], "true");
});
