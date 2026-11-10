import test from "node:test";
import assert from "node:assert/strict";
import { LOCAL_VIEW_RESIZE_EDGES, constrainLocalViewRect, resizeLocalViewRect,
  resolveLocalViewWindowGesture } from "../subview-window-geometry.js";

const rect = { left: 200, top: 150, width: 700, height: 400 };
for (const edge of LOCAL_VIEW_RESIZE_EDGES) test(`resize ${edge} changes only the chosen edges`, () => {
  const next = resizeLocalViewRect(rect, edge, 40, 30, 1400, 900);
  assert.equal(next.x, edge.includes("w") ? 240 : 200);
  assert.equal(next.y, edge.includes("n") ? 180 : 150);
  assert.equal(next.width, 700 + (edge.includes("e") ? 40 : edge.includes("w") ? -40 : 0));
  assert.equal(next.height, 400 + (edge.includes("s") ? 30 : edge.includes("n") ? -30 : 0));
});

for (const edge of LOCAL_VIEW_RESIZE_EDGES) test(`resize ${edge} keeps minimum dimensions and viewport bounds`, () => {
  for (const delta of [-10000, 10000]) {
    const next = resizeLocalViewRect(rect, edge, delta, delta, 1400, 900);
    assert.ok(next.width >= 480 && next.height >= 220);
    assert.ok(next.x >= 0 && next.y >= 0);
    assert.ok(next.x + next.width <= 1400 && next.y + next.height <= 900);
  }
});

test("small viewports remain reachable and saved dimensions are clamped on viewport resize", () => {
  assert.deepEqual(constrainLocalViewRect({ x: 700, y: 400, width: 1000, height: 800 }, 320, 200),
    { x: 0, y: 0, width: 320, height: 200 });
  assert.deepEqual(resizeLocalViewRect(rect, "nw", 10000, 10000, 320, 200),
    { x: 0, y: 0, width: 320, height: 200 });
});

test("header whitespace starts a move but controls, labels and menus do not", () => {
  const blank = { closest: selector => selector === "[data-local-view-drag]" ? {} : null };
  assert.equal(resolveLocalViewWindowGesture(blank), "move");
  assert.equal(resolveLocalViewWindowGesture({ closest: () => null }), null);
  for (const selector of ["button", "input", "label", "summary", "details", "select", "textarea",
    ".assembly-track-inline-field", ".assembly-track-combo", ".subview-history-controls", "[data-view-tick-control]"]) {
    const target = { closest: query => query === "[data-local-view-drag]" || query.split(",").includes(selector) ? {} : null };
    assert.equal(resolveLocalViewWindowGesture(target), null, selector);
  }
  for (const edge of LOCAL_VIEW_RESIZE_EDGES) assert.equal(resolveLocalViewWindowGesture({
    closest: selector => selector === "[data-local-view-resize]" ? { dataset: { localViewResize: edge } } : null,
  }), edge);
});
