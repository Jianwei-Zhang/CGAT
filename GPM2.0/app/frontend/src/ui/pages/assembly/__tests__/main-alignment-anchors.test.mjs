import { resolveMainAnchorFragments, renderMainAnchorFragments, patchMainAnchorFragments } from "../main-anchor-fragments.js";
import test from "node:test";
import assert from "node:assert/strict";
import { mainAlignmentKey, mainAlignmentEndpointKey, mainAnchorStateKey, mainActiveAnchorKeys,
  toggleMainAlignmentAnchorState, resolveMainAlignmentContextTarget, resolveMainContigSourcePosition,
  patchMainAlignmentAnchors } from "../main-alignment-anchors.js";
import { resolveSelectedContigSplitBoundaries, isCurrentContigSplitAnchor } from "../contig-split-boundary.js";
import { normalizeSubviewAnchorStateByKey } from "../subview-anchor-state.js";
import { createState, createStore, renderAssemblyPage, __testBuildAssemblyContextMenuItems } from "./tabs-semantics-harness.mjs";

function fixture() {
  return { selectedChrName: "Chr01", trackView: { alignmentLength: 1 }, trackSelectedCtgIds: [],
    chrCtgs: [{ assemblyCtgId: 6, originSourceSeqId: 77, totalLength: 1000, orient: "+", hits:
      [[101, 300, 201, 400], [501, 800, 601, 900]].map(([queryStart, queryEnd, refStart, refEnd]) => ({
        queryStart, queryEnd, refStart, refEnd, ctgStart: queryStart, ctgEnd: queryEnd,
        strand: "+", blockLength: queryEnd - queryStart + 1, identityPct: 99,
      })) }], subviewAnchorStateByKey: { local: { activeAnchors: [{ hitKey: "local-hit", edge: "right" }], manualAnchors: [] } } };
}
function enable(assembly, hitIndex, edge) {
  const ctg = assembly.chrCtgs[0];
  return toggleMainAlignmentAnchorState(assembly, { hitKey: mainAlignmentKey(assembly.selectedChrName, ctg, ctg.hits[hitIndex]), edge });
}
const cuts = (result) => [result?.left?.cutAfter ?? null, result?.right?.cutAfter ?? null];

test("only enabled anchors delimit the clicked fragment; outer alignment shortcuts stay fixed otherwise", () => {
  let assembly = fixture();
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 400)), [100, 800]);
  assembly = enable(enable(assembly, 0, "right"), 1, "left");
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 400)), [300, 500]);
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 200)), [100, 300]);
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 600)), [500, 800]);
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6)), [null, null]);
  const current = resolveSelectedContigSplitBoundaries(assembly, 6, 400).left;
  assert.equal(isCurrentContigSplitAnchor(assembly, current), true);
  assembly = enable(assembly, 0, "right");
  assert.equal(isCurrentContigSplitAnchor(assembly, current), false);
});

test("anchors persist without touching local histories and survive reverse orientation and source splitting", () => {
  let assembly = enable(enable(fixture(), 0, "right"), 1, "left");
  assembly.subviewAnchorStateByKey = normalizeSubviewAnchorStateByKey(JSON.parse(JSON.stringify(assembly.subviewAnchorStateByKey)));
  assert.deepEqual(assembly.subviewAnchorStateByKey.local, fixture().subviewAnchorStateByKey.local);
  assembly.chrCtgs[0].orient = "-";
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 400)), [500, 300]);
  assembly.chrCtgs[0] = { ...assembly.chrCtgs[0], assemblyCtgId: 9, orient: "+", totalLength: 700,
    sourceFragment: { sourceSeqId: 77, sourceStart: 301, sourceEnd: 1000 }, hits: [assembly.chrCtgs[0].hits[1]] };
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 9, 600)), [500, 800]);
  assert.equal(mainActiveAnchorKeys({ ...assembly, selectedChrName: "Chr02" }).size, 0);
});

test("terminal boundaries remain disabled, including reverse full-length alignments", () => {
  for (const orient of ["+", "-"]) {
    const assembly = fixture(); assembly.chrCtgs[0].orient = orient;
    assembly.chrCtgs[0].hits = [{ ...assembly.chrCtgs[0].hits[0], queryStart: 1, queryEnd: 1000 }];
    assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 400)), [null, null]);
    const anchored = enable(assembly, 0, "left");
    assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(anchored, 6, 400)), [null, null]);
  }
});

test("main hit and edge menus exclude contig actions even when the band also resolves a contig target", async () => {
  const assembly = fixture(), ctg = assembly.chrCtgs[0];
  const hitKey = mainAlignmentKey(assembly.selectedChrName, ctg, ctg.hits[0]);
  const store = createStore(createState({ assembly })), calls = [];
  const ctgContext = { assemblyCtgId: 6, trackRole: "primary", sourceBp: 200 };
  const menu = (edge) => __testBuildAssemblyContextMenuItems({ host: {}, store, ctgContext,
    mainAlignmentContext: { hitKey, ...(edge ? { edge } : {}) },
    actions: { toggleMainAlignmentAnchor: (_host, _store, context) => calls.push(context) } });
  const items = menu();
  assert.deepEqual(items.map((item) => item.label), ["启用左侧锚点", "启用右侧锚点"]);
  await items[0].run(); await items[1].run();
  assert.deepEqual(calls.map((c) => c.edge), ["left", "right"]);
  assert.deepEqual(menu("left").map((i) => i.label), ["启用锚点"]);
  store.setState({ assembly: enable(store.getState().assembly, 0, "left") });
  assert.deepEqual(menu("left").map((i) => i.label), ["关闭锚点"]);
  const contigMenu = __testBuildAssemblyContextMenuItems({ host: {}, store, ctgContext,
    actions: { canEditTrackCtg: () => true } });
  assert.ok(contigMenu.some((item) => item.label === "分割 Contig"));
  assert.ok(contigMenu.some((item) => item.label === "重命名 Contig..."));
  assert.ok(!contigMenu.some((item) => item.label.includes("侧锚点")));
  const edgeNode = { getAttribute: (key) => ({ "data-main-alignment-key": hitKey, "data-main-anchor-edge": "right" })[key] };
  assert.deepEqual(resolveMainAlignmentContextTarget({ closest: () => edgeNode }), { hitKey, edge: "right" });
});

test("rendered main anchors expose exact hit targets and update in place without replacing the viewport", () => {
  const assembly = enable(fixture(), 0, "left");
  const html = renderAssemblyPage(createState({ assembly: { ...assembly,
    chromosomes: [{ chrName: "Chr01", chrLength: 1200 }], refTrackMembers: [{ segmentStartBp: 1, segmentEndBp: 1200 }] } }));
  assert.match(html, /data-main-alignment-key=/);
  assert.match(html, /data-main-anchor-edge="left"/);
  assert.match(html, /data-main-anchor-edge="right"/);
  assert.match(html, /stroke="red"[^>]*data-main-anchor-line="1"/);
  const key = mainAlignmentEndpointKey("Chr01", assembly.chrCtgs[0], assembly.chrCtgs[0].hits[0], "left");
  const values = {}, line = { getAttribute: () => key, setAttribute: (k,v) => { values[k] = v; }, classList: { toggle() {} } };
  const host = { scrollLeft: 1800, querySelectorAll: () => [line] };
  patchMainAlignmentAnchors(host, assembly); assert.equal(values.stroke, "red"); assert.equal(host.scrollLeft, 1800);
  patchMainAlignmentAnchors(host, fixture()); assert.equal(values.stroke, "transparent");
});

test("fragment picking uses SVG coordinates, original source offsets and display orientation", () => {
  const assembly = fixture();
  assembly.chrCtgs[0].sourceFragment = { sourceStart: 101, sourceEnd: 1100 };
  const node = { getAttribute: (key) => ({ "data-track-rect-x": "20", "data-track-rect-width": "100" })[key],
    getScreenCTM: () => ({ inverse: () => ({}) }), ownerSVGElement: { createSVGPoint: () => ({
      matrixTransform() { return { x: this.x / 2 }; },
    }) } };
  const target = { closest: (selector) => selector === "[data-track-contig-id][data-track-role]" ? node : null };
  const context = { assemblyCtgId: 6, trackRole: "primary" };
  assert.equal(resolveMainContigSourcePosition(assembly, context, target, 140, 0), 601);
  assembly.chrCtgs[0].orient = "-";
  assert.equal(resolveMainContigSourcePosition(assembly, context, target, 140, 0), 600);
});

test("hidden, filtered, switched chromosomes and mismatched tracks reject stale anchor actions", () => {
  const assembly = fixture(), ctg = assembly.chrCtgs[0];
  const context = { hitKey: mainAlignmentKey("Chr01", ctg, ctg.hits[0]), edge: "left" };
  assert.equal(toggleMainAlignmentAnchorState({ ...assembly, hiddenPrimaryCtgIds: [6] }, context), null);
  assert.equal(toggleMainAlignmentAnchorState({ ...assembly, trackView: { alignmentLength: 5000 } }, context), null);
  assert.equal(toggleMainAlignmentAnchorState({ ...assembly, selectedChrName: "Chr02" }, context), null);
  const supportKey = mainAlignmentEndpointKey("Chr01", ctg, ctg.hits[0], "left", "support", 2);
  assert.notEqual(supportKey, mainAlignmentEndpointKey("Chr01", ctg, ctg.hits[0], "left"));
  assert.ok(mainAnchorStateKey("Chr01").startsWith("main-view|"));
});


const fragmentContext = (assembly) => ({ ctg: assembly.chrCtgs[0], chrName: assembly.selectedChrName,
  role: "primary", active: mainActiveAnchorKeys(assembly), prefs: { alignmentLength: 1, minIdentityPct: 0 } });

test("main anchor fragments match Local View partition semantics and current split boundaries", () => {
  const assembly = enable(enable(fixture(), 0, "right"), 1, "left");
  const original = JSON.stringify(assembly.chrCtgs);
  assert.deepEqual(resolveMainAnchorFragments(fragmentContext(assembly)), [
    { start: 1, end: 300 }, { start: 301, end: 500 }, { start: 501, end: 1000 },
  ]);
  assert.equal(JSON.stringify(assembly.chrCtgs), original);
  for (const orient of ["+", "-"]) {
    assembly.chrCtgs[0].orient = orient;
    const fragments = resolveMainAnchorFragments(fragmentContext(assembly));
    const middle = fragments[1];
    const node = { getAttribute: (key) => key === "data-main-fragment-start" ? String(middle.start) : String(middle.end) };
    const sourceBp = resolveMainContigSourcePosition(assembly, { assemblyCtgId: 6, trackRole: "primary" },
      { closest: (selector) => selector === "[data-main-fragment-start][data-main-fragment-end]" ? node : null }, 0, 0);
    assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, sourceBp)), orient === "+" ? [300, 500] : [500, 300]);
    assert.equal(fragments[0].start, orient === "+" ? 1 : 501);
    const markup = renderMainAnchorFragments({ ...fragmentContext(assembly),
      rect: { x: 20, width: 100 }, y: 90, height: 14, escapeHtml: String });
    assert.equal((markup.match(/class="main-anchor-fragment-hit-zone"/g) || []).length, 3);
    assert.equal((markup.match(/class="main-anchor-fragment-separator"/g) || []).length, 2);
    assert.match(markup, /data-main-fragment-start="301" data-main-fragment-end="500"/);
    assert.match(markup, orient === "+" ? /x1="50.00"/ : /x1="70.00"/);
  }
  assert.deepEqual(resolveMainAnchorFragments(fragmentContext(fixture())), []);
});

test("fragment overlays update in place and disappear after anchors are disabled without touching the contig node", () => {
  const anchored = enable(enable(fixture(), 0, "right"), 1, "left");
  const attrs = new Map(Object.entries({ "data-track-role": "primary", "data-track-contig-id": "6",
    "data-track-dataset-id": "1", "data-track-rect-x": "20", "data-track-rect-y": "90",
    "data-track-rect-width": "100", "data-track-rect-height": "14" }));
  const group = { getAttribute: (key) => attrs.get(key), setAttribute: (key, value) => attrs.set(key, value),
    removeAttribute: (key) => attrs.delete(key) };
  const layer = { innerHTML: "", closest: () => group };
  const host = { scrollLeft: 1800, scrollTop: 200, querySelectorAll: () => [layer] };
  patchMainAnchorFragments(host, anchored, String);
  assert.match(layer.innerHTML, /data-main-fragment-start="301" data-main-fragment-end="500"/);
  assert.equal(attrs.get("data-main-anchor-segmented"), "1");
  assert.equal(host.scrollLeft, 1800); assert.equal(host.scrollTop, 200);
  patchMainAnchorFragments(host, fixture(), String);
  assert.equal(layer.innerHTML, ""); assert.equal(attrs.has("data-main-anchor-segmented"), false);
  assert.equal(layer.closest(), group);
});

test("main fragment overlays honor clipped source ranges and alignment filters", () => {
  const assembly = enable(enable(fixture(), 0, "right"), 1, "left");
  assembly.chrCtgs[0] = { ...assembly.chrCtgs[0], assemblyCtgId: 9, totalLength: 700,
    sourceFragment: { sourceSeqId: 77, sourceStart: 301, sourceEnd: 1000 }, hits: [assembly.chrCtgs[0].hits[1]] };
  assert.deepEqual(resolveMainAnchorFragments(fragmentContext(assembly)), [{ start: 301, end: 500 }, { start: 501, end: 1000 }]);
  assert.deepEqual(resolveMainAnchorFragments({ ...fragmentContext(assembly), prefs: { alignmentLength: 5000, minIdentityPct: 0 } }), []);
  const html = renderAssemblyPage(createState({ assembly: { ...assembly,
    chromosomes: [{ chrName: "Chr01", chrLength: 1200 }], refTrackMembers: [{ segmentStartBp: 1, segmentEndBp: 1200 }] } }));
  assert.match(html, /data-main-anchor-segmented="1"/);
  assert.match(html, /data-main-anchor-fragments="1"/);
  assert.match(html, /data-main-fragment-start="301" data-main-fragment-end="500"/);
});


for (const orient of ["+", "-"]) for (const anchoredSide of ["left", "right"]) {
  test(`main ${orient} single ${anchoredSide} source-side anchor keeps the opposite alignment boundary`, () => {
    let assembly = anchoredSide === "left" ? enable(fixture(), 0, "right") : enable(fixture(), 1, "left");
    assembly.chrCtgs[0].orient = orient;
    const boundaries = resolveSelectedContigSplitBoundaries(assembly, 6, 400);
    const expected = anchoredSide === "left" ? [300, 800] : [100, 500];
    assert.deepEqual(cuts(boundaries), orient === "+" ? expected : expected.reverse());
    assert.equal(isCurrentContigSplitAnchor(assembly, boundaries.left), true);
    assert.equal(isCurrentContigSplitAnchor(assembly, boundaries.right), true);
  });
}

test("main fallback alignment boundary remains actionable in the menu and rejects changed anchors", async () => {
  const assembly = enable(fixture(), 0, "right");
  const fallback = resolveSelectedContigSplitBoundaries(assembly, 6, 400).right;
  const store = createStore(createState({ assembly })), calls = [];
  const menu = __testBuildAssemblyContextMenuItems({ store, host: {},
    ctgContext: { assemblyCtgId: 6, trackRole: "primary", sourceBp: 400 },
    actions: { canEditTrackCtg: () => true, splitContigAtAnchor: async (_host, _store, anchor) => calls.push(anchor) } });
  const split = menu.find((item) => item.label === "分割 Contig");
  assert.equal(split.children[1].disabled, false); assert.equal(split.children[2].disabled, false);
  await split.children[2].run(); assert.equal(calls[0].cutAfter, 800);
  assert.equal(isCurrentContigSplitAnchor(enable(assembly, 1, "left"), fallback), false);
});

test("main fallback edges cannot duplicate an anchor or split an existing source endpoint", () => {
  const lowerEdge = enable(fixture(), 0, "left");
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(lowerEdge, 6, 50)), [null, 100]);
  const upperEdge = enable(fixture(), 1, "right");
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(upperEdge, 6, 900)), [800, null]);
  const assembly = enable(fixture(), 0, "right");
  assembly.chrCtgs[0].sourceFragment = { sourceSeqId: 77, sourceStart: 101, sourceEnd: 800 };
  assembly.chrCtgs[0].totalLength = 700;
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 400)), [300, null]);
});
