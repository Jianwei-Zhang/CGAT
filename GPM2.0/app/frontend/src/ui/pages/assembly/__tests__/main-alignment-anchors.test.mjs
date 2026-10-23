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
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 200)), [null, 300]);
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 6, 600)), [500, null]);
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
  assert.deepEqual(cuts(resolveSelectedContigSplitBoundaries(assembly, 9, 600)), [500, null]);
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

test("main hit and edge menus use the same anchor labels and pass the exact selected edge", async () => {
  const assembly = fixture(), ctg = assembly.chrCtgs[0];
  const hitKey = mainAlignmentKey(assembly.selectedChrName, ctg, ctg.hits[0]);
  const store = createStore(createState({ assembly })), calls = [];
  const menu = (edge) => __testBuildAssemblyContextMenuItems({ host: {}, store,
    mainAlignmentContext: { hitKey, ...(edge ? { edge } : {}) },
    actions: { toggleMainAlignmentAnchor: (_host, _store, context) => calls.push(context) } });
  const items = menu(); assert.equal(items.length, 2);
  await items[0].run(); await items[1].run();
  assert.deepEqual(calls.map((c) => c.edge), ["left", "right"]);
  assert.deepEqual(menu("left").map((i) => i.label), ["启用锚点"]);
  store.setState({ assembly: enable(store.getState().assembly, 0, "left") });
  assert.deepEqual(menu("left").map((i) => i.label), ["关闭锚点"]);
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
