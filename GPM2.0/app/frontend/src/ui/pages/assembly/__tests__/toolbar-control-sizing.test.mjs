import test from "node:test";
import assert from "node:assert/strict";
import { resolveToolbarControlWidth, syncToolbarControlWidth, syncToolbarControlWidths } from "../toolbar-control-sizing.js";

function fixture({ value = "0", support = false, inToolbar = true } = {}) {
  const values = new Map(); let canvases = 0;
  const control = { value: support ? "" : value, textContent: support ? value : "", focus() { throw new Error("must not move focus"); } };
  const context = { font: "", measureText: text => ({ width: [...text].length * 7 }) };
  const doc = { createElement(tag) { assert.equal(tag, "canvas"); canvases++; return { getContext: () => context }; },
    defaultView: { getComputedStyle: node => node === control
      ? { font: "400 13px sans-serif", paddingLeft: "8px", paddingRight: "24px", letterSpacing: "normal" }
      : { borderLeftWidth: "1px", borderRightWidth: "1px" } } };
  const combo = { ownerDocument: doc, dataset: { trackComboField: support ? "supportDatasetId" : "minIdentityPct" },
    style: { setProperty: (key, value) => values.set(key, value) }, closest: () => inToolbar ? {} : null, querySelector: () => control };
  return { combo, control, values, context, canvases: () => canvases };
}
test("content sizing has a compact minimum and distinct numeric/dataset caps", () => {
  assert.equal(resolveToolbarControlWidth(7, 34), 44);
  assert.equal(resolveToolbarControlWidth(42, 34), 78);
  assert.equal(resolveToolbarControlWidth(10000, 34), 140);
  assert.equal(resolveToolbarControlWidth(10000, 34, { support: true }), 180);
});
test("typing resizes only the input shell without rewriting values or moving focus", () => {
  const f = fixture();
  assert.equal(syncToolbarControlWidth(f.combo), true);
  assert.equal(f.values.get("--toolbar-combo-width"), "44px");
  f.control.value = "123456"; syncToolbarControlWidth(f.combo);
  assert.equal(f.values.get("--toolbar-combo-width"), "78px");
  f.control.value = "123456789012345678901234567890"; syncToolbarControlWidth(f.combo);
  assert.equal(f.values.get("--toolbar-combo-width"), "140px");
  assert.equal(f.control.value, "123456789012345678901234567890");
  f.control.value = "0"; syncToolbarControlWidth(f.combo);
  assert.equal(f.values.get("--toolbar-combo-width"), "44px");
  assert.equal(f.canvases(), 1);
  assert.equal(f.context.font, "400 13px sans-serif");
});
test("dataset buttons measure their visible caption, not their empty button value", () => {
  const f = fixture({ value: "flye", support: true }); syncToolbarControlWidth(f.combo);
  assert.equal(f.values.get("--toolbar-combo-width"), "64px");
  f.control.textContent = "Long auxiliary dataset name ".repeat(5); syncToolbarControlWidth(f.combo);
  assert.equal(f.values.get("--toolbar-combo-width"), "180px");
});
test("sizing stays scoped to Main/Local toolbars and tolerates detached test hosts", () => {
  const f = fixture({ inToolbar: false });
  assert.equal(syncToolbarControlWidth(f.combo), false);
  assert.equal(f.values.size, 0);
  assert.equal(syncToolbarControlWidth(null), false);
  syncToolbarControlWidths({}); syncToolbarControlWidths({ querySelectorAll: () => [null, f.combo] });
  assert.equal(f.canvases(), 0);
});
