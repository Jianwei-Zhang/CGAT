import test from "node:test";
import assert from "node:assert/strict";
import { resolveSubviewContigDropTarget } from "../contig-drop-target.js";
import { projectMainDraggedMember } from "../subview-composition-controller.js";
import { normalizeSubviewCompositionMember } from "../subview-composition-state.js";

const candidate = normalizeSubviewCompositionMember({ assemblyCtgId: 9, lengthBp: 1000,
  baseOrientation: "+", source: { role: "primary", datasetId: 7 },
  sourceFragment: { sourceSeqId: 11, groupKey: "source9", sourceStart: 2001, sourceEnd: 3000 } });

test("Main slices preserve original source interval and backing orientation", () => {
  const sliced = projectMainDraggedMember(candidate, { start: 2201, end: 2450, coordinateSpace: "source", refOrient: "-" });
  assert.equal(sliced.lengthBp, 250); assert.equal(sliced.baseOrientation, "-"); assert.equal(sliced.backingOrientation, "+");
  assert.equal(sliced.localFragment.sourceStart, 2201); assert.equal(sliced.localFragment.sourceEnd, 2450);
  assert.deepEqual(sliced.localFragment.parts, [{ assemblyCtgId: 9, sourceStart: 2001, sourceEnd: 3000, orient: "+" }]);
  assert.equal(candidate.localFragment, undefined);
});
for (const context of [ { start: 100, end: 200, coordinateSpace: "source" },
  { start: 2200, end: 2300, coordinateSpace: "display" }, { start: 2200 },
  { start: 2300, end: 2200, coordinateSpace: "source" } ]) test(`invalid dragged ranges never widen: ${JSON.stringify(context)}`, () => {
  assert.equal(projectMainDraggedMember(candidate, context), null);
});
test("whole Main member retains source identity without unnecessary slicing", () => {
  assert.equal(projectMainDraggedMember(candidate, {}), candidate);
  assert.equal(projectMainDraggedMember(candidate, { start: 2001, end: 3000, coordinateSpace: "source" }), candidate);
});
test("drop lanes use scaled destination geometry and reject rulers and hidden windows", () => {
  const window = { dataset: { localViewWindow: "local-1" }, closest: () => null };
  const svg = { dataset: { subviewDropTopY: "100", subviewDropBottomY: "250" },
    getAttribute: () => "350", getBoundingClientRect: () => ({ top: 200, height: 700 }) };
  const surface = { querySelector: () => svg, getBoundingClientRect: () => ({ left: 40, top: 200, bottom: 900, width: 600 }) };
  const node = { closest: selector => selector === "[data-local-view-window]" ? window : selector === ".subview-track-scroll" ? surface : null };
  assert.equal(resolveSubviewContigDropTarget(node, 220), null);
  assert.equal(resolveSubviewContigDropTarget(node, 420).lane, "top");
  assert.equal(resolveSubviewContigDropTarget(node, 730).lane, "bottom");
  window.hidden = true; assert.equal(resolveSubviewContigDropTarget(node, 420), null);
});
