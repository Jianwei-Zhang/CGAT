import { test, assert, createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { applySubviewComposition } from "../subview-composition-state.js";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";

function overlapState() {
  const candidates = buildSubviewCompositionCandidates({
    primaryDatasetId: 1,
    allChrCtgs: [
      { assemblyCtgId: 1, datasetId: 1, name: "short@Chr01", lengthBp: 2000 },
      { assemblyCtgId: 2, datasetId: 1, name: "long@Chr01", lengthBp: 20000 },
      { assemblyCtgId: 3, datasetId: 2, name: "tiny@Chr01", lengthBp: 20 },
      { assemblyCtgId: 4, datasetId: 2, name: "medium@Chr01", lengthBp: 4000 },
      { assemblyCtgId: 5, datasetId: 2, name: "bottom-long@Chr01", lengthBp: 12000 },
    ],
  });
  const positions = { 1: 2000, 2: -2000, 3: 3000, 4: 4000, 5: 2000 };
  return createState({ assembly: {
    subview: applySubviewComposition({}, { members: candidates.map((member) => ({
      ...member, lane: member.assemblyCtgId < 4 ? "top" : "bottom",
      xBp: positions[member.assemblyCtgId],
    })) }),
    subviewCompositionCandidates: candidates,
    subviewCompositionCandidatesLoaded: true,
    subviewCompositionViewport: { bpPerPx: 10, leftBp: 0, topPx: 0 },
  } });
}

function memberGroups(state) {
  return [...renderAssemblyPage(state).matchAll(/<g class="track-ctg-group[^\"]*" data-subview-composition-entity-key="([^\"]+)"([\s\S]*?)<\/g>/g)]
    .map(([, key, markup]) => ({ key, markup }));
}

test("composition paints overlapping short members in front independently in both lanes", () => {
  const state = overlapState();
  const before = structuredClone(state.assembly);
  assert.deepEqual(memberGroups(state).map(({ key }) => key), [
    "assembly:2", "assembly:1", "assembly:3", "assembly:5", "assembly:4",
  ]);
  assert.deepEqual(state.assembly, before, "paint order must not reorder canonical members or positions");
  for (const bpPerPx of [5, 20, 100]) {
    state.assembly.subviewCompositionViewport.bpPerPx = bpPerPx;
    assert.deepEqual(memberGroups(state).map(({ key }) => key), [
      "assembly:2", "assembly:1", "assembly:3", "assembly:5", "assembly:4",
    ]);
  }
});

test("composition labels use shared fitting, padding, orientation and canvas bounds", () => {
  const state = overlapState();
  let groups = memberGroups(state);
  assert.doesNotMatch(groups.find(({ key }) => key === "assembly:3").markup, /<text/);
  assert.match(groups.find(({ key }) => key === "assembly:3").markup, /<title>tiny@Chr01 \(\+\)/);
  assert.match(groups.find(({ key }) => key === "assembly:1").markup,
    /<text[^>]*x="204.00"[^>]*text-anchor="start"[^>]*>short \(\+\)<\/text>/);
  assert.match(groups.find(({ key }) => key === "assembly:2").markup, /<text[^>]*x="-196.00"/);
  state.assembly.subviewCompositionViewport.bpPerPx = 100;
  groups = memberGroups(state);
  assert.doesNotMatch(groups.find(({ key }) => key === "assembly:1").markup, /<text/);
  assert.match(groups.find(({ key }) => key === "assembly:2").markup, />long \(\+\)<\/text>/);
});

test("composition ordering follows current overlap after movement without repacking", () => {
  const state = overlapState();
  const members = state.assembly.subview.summary.members;
  const short = members.find((member) => member.assemblyCtgId === 1);
  short.xBp = -6000;
  let groups = memberGroups(state);
  assert.deepEqual(groups.slice(0, 3).map(({ key }) => key), ["assembly:1", "assembly:2", "assembly:3"]);
  assert.match(groups[0].markup, /data-subview-rect-x="-600.00"/);
  short.xBp = -3000; // Partial overlap with the long member, not containment.
  groups = memberGroups(state);
  assert.deepEqual(groups.slice(0, 3).map(({ key }) => key), ["assembly:2", "assembly:1", "assembly:3"]);
  assert.match(groups[1].markup, /data-subview-rect-x="-300.00"/);
});
