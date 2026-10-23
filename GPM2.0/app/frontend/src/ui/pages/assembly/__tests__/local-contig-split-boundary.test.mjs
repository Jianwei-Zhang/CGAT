import test from "node:test";
import assert from "node:assert/strict";
import { resolveLocalSplitBoundaries, resolveLocalAlignmentRange } from "../local-contig-split-boundary.js";
import { memberAnchorEndpointKey } from "../subview-fragment-model.js";

const range = { sourceStart: 101, sourceEnd: 1100 };
for (const orient of ["+", "-"]) {
  test(`local ${orient} split sides use the alignment envelope until anchors delimit a selected fragment`, () => {
    const resolve = (overrides) => resolveLocalSplitBoundaries({ range, orient,
      selectedRange: range, anchorCuts: [], alignmentRange: { low: 200, high: 900 }, ...overrides });
    assert.deepEqual(resolve({}), orient === "+" ? { left: 200, right: 900 } : { left: 900, right: 200 });
    assert.deepEqual(resolve({ anchorCuts: [300, 700], selectedRange: { sourceStart: 301, sourceEnd: 700 } }),
      orient === "+" ? { left: 300, right: 700 } : { left: 700, right: 300 });
    assert.deepEqual(resolve({ anchorCuts: [300, 700] }), { left: null, right: null });
    assert.deepEqual(resolve({ anchorCuts: [300, 700], selectedRange: { sourceStart: 101, sourceEnd: 300 } }),
      orient === "+" ? { left: 200, right: 300 } : { left: 300, right: 200 });
    assert.deepEqual(resolve({ alignmentRange: { low: 100, high: 1100 } }), { left: null, right: null });
    assert.deepEqual(resolve({ alignmentRange: null }), { left: null, right: null });
  });
}

test("local alignment envelope reads only the current member's evidence, not manual anchors or another lane", () => {
  const member = { assemblyCtgId: 6, entityKey: "assembly:6", lane: "top", source: { role: "primary" },
    baseOrientation: "+", flipped: false, lengthBp: 1000, sourceFragment: range };
  const key = memberAnchorEndpointKey(member);
  const edge = (coordinate, kind = "evidence", endpointKey = key) => {
    const attrs = { "data-subview-anchor-kind": kind, "data-subview-anchor-object-id": `${kind}:${coordinate}` };
    for (const [side, id, targetKey] of [["top", 6, endpointKey], ["bottom", 7, "other"]]) {
      Object.assign(attrs, { [`data-subview-anchor-${side}-endpoint-key`]: targetKey,
        [`data-subview-anchor-${side}-contig-id`]: String(id), [`data-subview-anchor-${side}-cut-bp`]: String(coordinate),
        [`data-subview-anchor-${side}-source-role`]: "primary" });
    }
    return { getAttribute: (name) => attrs[name] ?? null };
  };
  const host = { querySelectorAll: () => [edge(201), edge(800), edge(1, "manual"), edge(999, "evidence", "another-member")] };
  const state = { assembly: { subview: { summary: { mode: "composition" } } } };
  assert.deepEqual(resolveLocalAlignmentRange(state, host, member), { low: 300, high: 900 });
  const legacy = { assembly: { subview: { summary: { mode: "2-contig" } } } };
  const legacyHost = { querySelectorAll: () => [edge(201), edge(800)] };
  assert.deepEqual(resolveLocalAlignmentRange(legacy, legacyHost, { ...member, flipped: true }), { low: 300, high: 900 });
});


for (const orient of ["+", "-"]) test(`local ${orient} unanchored side falls back independently`, () => {
  const resolve = (overrides) => resolveLocalSplitBoundaries({ range, orient,
    anchorCuts: [300], selectedRange: { sourceStart: 301, sourceEnd: 1100 },
    alignmentRange: { low: 200, high: 900 }, ...overrides });
  assert.deepEqual(resolve({}), orient === "+" ? { left: 300, right: 900 } : { left: 900, right: 300 });
  assert.deepEqual(resolve({ anchorCuts: [700], selectedRange: { sourceStart: 101, sourceEnd: 700 } }),
    orient === "+" ? { left: 200, right: 700 } : { left: 700, right: 200 });
  assert.deepEqual(resolve({ anchorCuts: [300, 700], selectedRange: { sourceStart: 701, sourceEnd: 1100 } }),
    orient === "+" ? { left: 700, right: 900 } : { left: 900, right: 700 });
  assert.deepEqual(resolve({ alignmentRange: null }),
    orient === "+" ? { left: 300, right: null } : { left: null, right: 300 });
  assert.deepEqual(resolve({ alignmentRange: { low: 100, high: 1100 } }),
    orient === "+" ? { left: 300, right: null } : { left: null, right: 300 });
  assert.deepEqual(resolve({ selectedRange: { sourceStart: 101, sourceEnd: 300 }, alignmentRange: { low: 300, high: 900 } }),
    orient === "+" ? { left: null, right: 300 } : { left: 300, right: null });
  assert.deepEqual(resolve({ selectedRange: { sourceStart: 101, sourceEnd: 300 }, alignmentRange: { low: 500, high: 900 } }),
    orient === "+" ? { left: null, right: 300 } : { left: 300, right: null });
});
