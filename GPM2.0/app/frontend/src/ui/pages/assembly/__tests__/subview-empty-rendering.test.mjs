import { test, assert, createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { applySubviewComposition, removeSubviewCompositionMembers } from "../subview-composition-state.js";

function assertEmptyPanel(state) {
  const html = renderAssemblyPage(state);
  assert.match(html, /data-subview-panel="1"/);
  assert.match(html, /<h4>Subview<\/h4>/);
  assert.match(html, /subview-panel-guide/);
  assert.match(html, /data-subview-tools-toggle/);
  assert.doesNotMatch(html, /subview-alignment-card|subview-track-layout|subview-track-svg|subview-track-min-tick-unit-kb/);
}

test("initial and empty composition Subviews render only the status row", () => {
  const state = createState();
  assertEmptyPanel(state);
  state.assembly.subview = applySubviewComposition({}, { members: [] });
  assertEmptyPanel(state);
});

test("removing the final composition member hides the graph and restoring a member shows it again", () => {
  const composition = { members: [{ assemblyCtgId: 1, source: { role: "primary", datasetId: 11 },
    lengthBp: 1000, label: "ctg1", lane: "top", xBp: 0 }] };
  const state = createState({ assembly: { subview: applySubviewComposition({}, composition) } });
  assert.match(renderAssemblyPage(state), /subview-track-svg/);
  const removed = removeSubviewCompositionMembers(composition, ["assembly:1"]);
  state.assembly.subview = applySubviewComposition(state.assembly.subview, removed.composition);
  const before = structuredClone(state.assembly.subview);
  assertEmptyPanel(state);
  assert.deepEqual(state.assembly.subview, before, "empty rendering does not clear undo state");
  state.assembly.subview = applySubviewComposition(state.assembly.subview, composition);
  assert.match(renderAssemblyPage(state), /subview-track-svg/);
});

test("track-pair renders a single populated lane but hides the graph once both lanes are empty", () => {
  const state = createState({ assembly: {
    chrCtgs: [{ assemblyCtgId: 1, name: "ctg1", totalLength: 1000, anchorStart: 0 }],
    supportChrCtgs: [],
    subview: { summary: { mode: "track-pair",
      topTrack: { role: "support", source: "mother", datasetId: 22 },
      bottomTrack: { role: "primary", source: "mother", datasetId: 11 } } },
  } });
  assert.match(renderAssemblyPage(state), /subview-track-svg/);
  state.assembly.subview.trackPairHiddenCtgs = [{ trackRole: "primary", contigId: 1 }];
  assertEmptyPanel(state);
  state.assembly.chrCtgs = [];
  state.assembly.subview.trackPairHiddenCtgs = [];
  assertEmptyPanel(state);
});
