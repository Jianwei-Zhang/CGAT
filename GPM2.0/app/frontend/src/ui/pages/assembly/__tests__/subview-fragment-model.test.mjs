import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSubviewComposition } from "../subview-composition-state.js";
import {
  memberSourceInterval, memberCoordinateToSource, sourceCoordinateToMember,
  projectBackingCoordinate, memberBackingIds, memberAnchorEndpointKey,
  sliceLocalMember, splitLocalMember, isolateLocalMemberInterval, deleteLocalMember,
  mergeLocalMember, resolveLocalMergeNeighbor, normalizeLocalFragment, clipLocalAlignment,
} from "../subview-fragment-model.js";
import { commitSubviewHistoryOperation, rollbackSubviewHistory, restoreSubviewHistoryRollback } from "../subview-history-state.js";
import { applySubviewComposition } from "../subview-composition-state.js";

const original = (patch = {}) => normalizeSubviewComposition({ members: [{ assemblyCtgId: 10,
  originSourceSeqId: 7, label: "ctg", source: { role: "primary", datasetId: 2 },
  lengthBp: 100, lane: "top", baseOrientation: "+", xBp: 500, ...patch }] }).members[0];
const composition = (members) => normalizeSubviewComposition({ members });

for (const baseOrientation of ["+", "-"]) for (const flipped of [false, true]) {
  test(`source-coordinate split and independent deletion preserve placement, orient=${baseOrientation}, flip=${flipped}`, () => {
    const before = original({ baseOrientation, flipped });
    const split = splitLocalMember(composition([before]), before.entityKey, 40);
    assert.equal(split.changed, true);
    assert.deepEqual(split.members.map((m) => m.lengthBp), [40, 60]);
    assert.deepEqual(split.members.map((m) => [m.localFragment.sourceStart, m.localFragment.sourceEnd]), [[1, 40], [41, 100]]);
    assert.equal(new Set(split.members.map((m) => m.entityKey)).size, 2);
    const reverse = (baseOrientation === "-") !== flipped;
    assert.deepEqual(split.members.map((m) => m.xBp), reverse ? [560, 500] : [500, 540]);
    const after = deleteLocalMember(split.composition, split.members[0].entityKey);
    assert.equal(after.composition.members.length, 1);
    assert.deepEqual(after.composition.members[0], split.members[1]);
    assert.deepEqual(memberSourceInterval(before).parts, [{ assemblyCtgId: 10, sourceStart: 1, sourceEnd: 100, orient: baseOrientation }]);
  });
}

test("anchor-derived middle deletion keeps both remainders and cannot resurrect deleted bases by merge", () => {
  const parent = original();
  const isolated = isolateLocalMemberInterval(composition([parent]), parent.entityKey, 31, 70);
  assert.equal(isolated.changed, true);
  assert.equal(isolated.member.lengthBp, 40);
  const removed = deleteLocalMember(isolated.composition, isolated.member.entityKey);
  assert.deepEqual(removed.composition.members.map((m) => [m.localFragment.sourceStart, m.localFragment.sourceEnd]), [[1, 30], [71, 100]]);
  assert.equal(resolveLocalMergeNeighbor(removed.composition, removed.composition.members[0].entityKey, "right"), null);
  const roundtrip = normalizeSubviewComposition(JSON.parse(JSON.stringify(removed.composition)));
  assert.deepEqual(roundtrip.members, removed.composition.members);
});

test("reverse anchor interval refers to base-oriented parent coordinates, not screen-left source bases", () => {
  const parent = original({ baseOrientation: "-" });
  const isolated = isolateLocalMemberInterval(composition([parent]), parent.entityKey, 11, 30);
  assert.deepEqual([isolated.member.localFragment.sourceStart, isolated.member.localFragment.sourceEnd], [71, 90]);
  assert.equal(isolated.member.xBp, 510);
  assert.equal(memberCoordinateToSource(isolated.member, 1), 90);
  assert.equal(sourceCoordinateToMember(isolated.member, 71), 20);
  assert.equal(projectBackingCoordinate(isolated.member, 10, 11), 1);
  assert.equal(projectBackingCoordinate(isolated.member, 10, 30), 20);
});

test("local merge joins compatible real siblings only locally and maps evidence from both backing IDs", () => {
  const a = original({ assemblyCtgId: 10, sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:x", sourceStart: 201, sourceEnd: 240 }, lengthBp: 40 });
  const b = original({ assemblyCtgId: 11, sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:x", sourceStart: 241, sourceEnd: 300 }, lengthBp: 60, xBp: 540 });
  const before = composition([a, b]);
  const joined = mergeLocalMember(before, a.entityKey, "right");
  assert.equal(joined.changed, true);
  assert.equal(joined.member.lengthBp, 100);
  assert.deepEqual(memberBackingIds(joined.member), [10, 11]);
  assert.equal(projectBackingCoordinate(joined.member, 10, 1), 1);
  assert.equal(projectBackingCoordinate(joined.member, 11, 1), 41);
  assert.equal(projectBackingCoordinate(joined.member, 11, 60), 100);
  assert.equal(projectBackingCoordinate(joined.member, 99, 1), null);
  assert.equal(before.members.length, 2, "no original or main entity is mutated");
  const resplit = splitLocalMember(joined.composition, joined.member.entityKey, 250);
  assert.deepEqual(resplit.members.map((m) => m.lengthBp), [50, 50]);
});

test("merge rejects other source instances, orientations, lanes, datasets and missing deleted intervals", () => {
  const parent = original();
  const split = splitLocalMember(composition([parent]), parent.entityKey, 40);
  const [a, b] = split.members;
  for (const patch of [{ flipped: true }, { lane: "bottom" }, { sourceKey: "other" },
    { localFragment: { ...b.localFragment, groupKey: "copy:other" } },
    { localFragment: { ...b.localFragment, sourceSeqId: 8 } }]) {
    const result = mergeLocalMember(composition([a, { ...b, ...patch }]), a.entityKey, "right");
    assert.equal(result.changed, false, JSON.stringify(patch));
  }
});

test("flip and deletion histories retain independent intervals through undo, redo and serialization", () => {
  const parent = original();
  const initial = composition([parent]);
  const isolated = isolateLocalMemberInterval(initial, parent.entityKey, 21, 60);
  isolated.member.flipped = true;
  const subview = applySubviewComposition({}, initial);
  const changed = commitSubviewHistoryOperation({ selectedChrName: "Chr1", subview }, {
    nextSubview: applySubviewComposition(subview, isolated.composition), operation: { kind: "flip-contig" },
  });
  assert.equal(changed.changed, true);
  const loaded = JSON.parse(JSON.stringify(changed.assembly));
  const undo = rollbackSubviewHistory(loaded);
  assert.equal(undo.changed, true);
  assert.equal(undo.assembly.subview.summary.members.length, 1);
  const redo = restoreSubviewHistoryRollback(undo.assembly);
  assert.equal(redo.changed, true);
  assert.deepEqual(redo.assembly.subview.summary.members, normalizeSubviewComposition(isolated.composition).members);
});

test("manual anchors migrate with source intervals and disappear only if their bases are deleted", () => {
  const parent = original();
  const other = original({ assemblyCtgId: 20, lane: "bottom" });
  const base = composition([parent, other]);
  base.manualAnchors = [25, 75].map((cutBp) => ({ manualAnchorId: `anchor${cutBp}`,
    endpointA: { endpointKey: memberAnchorEndpointKey(parent), contigId: 10, cutBp, lengthBp: 100 },
    endpointB: { endpointKey: memberAnchorEndpointKey(other), contigId: 20, cutBp, lengthBp: 100 } }));
  const sliced = isolateLocalMemberInterval(base, parent.entityKey, 21, 60);
  assert.equal(sliced.composition.manualAnchors[0].endpointA.cutBp, 5);
  assert.equal(sliced.composition.manualAnchors[1].endpointA.cutBp, 15);
  const removed = deleteLocalMember(sliced.composition, sliced.member.entityKey);
  assert.deepEqual(removed.composition.manualAnchors.map((a) => a.manualAnchorId), ["anchor75"]);
});

test("invalid persisted coverage is rejected instead of reconstructing a missing interval", () => {
  assert.equal(normalizeLocalFragment({ sourceStart: 1, sourceEnd: 100, groupKey: "g", parts: [
    { assemblyCtgId: 1, sourceStart: 1, sourceEnd: 40 }, { assemblyCtgId: 2, sourceStart: 61, sourceEnd: 100 },
  ] }), null);
  const member = original();
  for (const cut of [0, 100, 101, 40.5, NaN]) assert.equal(splitLocalMember(composition([member]), member.entityKey, cut).changed, false);
  assert.equal(sliceLocalMember(member, 0, 40), null);
});

test("alignment clipping uses a common parameter on both ends including reverse strands", () => {
  const bounds = { lengthBp: 40 };
  const forward = clipLocalAlignment(bounds, bounds, { topStart: -19, topEnd: 80, bottomStart: -19, bottomEnd: 80, strand: "+" });
  for (const [key, expected] of Object.entries({ topStart: 1, topEnd: 40, bottomStart: 1, bottomEnd: 40 })) assert.ok(Math.abs(forward[key] - expected) < 1e-9);
  const clip = clipLocalAlignment(bounds, { lengthBp: 100 }, { topStart: -19, topEnd: 80, bottomStart: 1, bottomEnd: 100, strand: "-" });
  assert.ok(Math.abs(clip.bottomStart - 41) < 1e-9);
  assert.ok(Math.abs(clip.bottomEnd - 80) < 1e-9);
  assert.equal(clipLocalAlignment(bounds, bounds, { topStart: 50, topEnd: 100, bottomStart: 1, bottomEnd: 30 }), null);
});


test("joined reverse parts project alignments and N intervals in the member coordinate system", async () => {
  const { projectLocalAlignment, projectLocalNRegions, filterLocalAnchorCuts, resolveLocalFinalPathContexts } = await import("../subview-fragment-model.js");
  const parent = original({ baseOrientation: "-" });
  const split = splitLocalMember(composition([parent]), parent.entityKey, 40);
  const joined = mergeLocalMember(split.composition, split.members[0].entityKey, "left");
  assert.equal(joined.changed, true);
  assert.equal(joined.member.baseOrientation, "-");
  assert.deepEqual(filterLocalAnchorCuts(joined.member, [61]), []);
  const other = original({ assemblyCtgId: 20, lane: "bottom" });
  const projected = projectLocalAlignment(split.members[0], other, 10, 20,
    { topStart: 50, topEnd: 90, bottomStart: 10, bottomEnd: 50, strand: "+" });
  assert.ok(projected);
  assert.equal(projected.topStart, 1);
  const regions = projectLocalNRegions(split.members[0], [{ assemblyCtgId: 10, sourceKey: parent.sourceKey,
    ctg: { nRegions: [{ ctgStart: 50, ctgEnd: 80 }, { ctgStart: 1, ctgEnd: 10 }] } }]);
  assert.deepEqual(regions.map((r) => [r.ctgStart, r.ctgEnd]), [[1, 20]]);
  assert.equal(resolveLocalFinalPathContexts([parent], { localFragmentEntityKey: parent.entityKey, start: 0, end: 20 }), null);
});

test("stored evidence anchor descriptors follow their exact source bases across a local split and deletion", () => {
  const parent = original(), other = original({ assemblyCtgId: 20, lane: "bottom" });
  const base = composition([parent, other]);
  base.activeAnchors = [{ hitKey: "hit", edge: "left", descriptor: {
    top: { endpointKey: memberAnchorEndpointKey(parent), contigId: 10, cutBp: 25, lengthBp: 100 },
    bottom: { endpointKey: memberAnchorEndpointKey(other), contigId: 20, cutBp: 25, lengthBp: 100 },
  } }];
  const isolated = isolateLocalMemberInterval(base, parent.entityKey, 21, 60);
  assert.equal(isolated.composition.activeAnchors[0].descriptor.top.cutBp, 5);
  assert.equal(isolated.composition.activeAnchors[0].descriptor.top.endpointKey, memberAnchorEndpointKey(isolated.member));
  assert.equal(deleteLocalMember(isolated.composition, isolated.member.entityKey).composition.activeAnchors.length, 0);
});


test("persisted local ranges reject ambiguous overlapping or duplicate backing instances", () => {
  const range = { sourceSeqId: 7, groupKey: "g", sourceStart: 1, sourceEnd: 100 };
  for (const parts of [
    [{ assemblyCtgId: 1, sourceStart: 1, sourceEnd: 100 }, { assemblyCtgId: 2, sourceStart: 50, sourceEnd: 100 }],
    [{ assemblyCtgId: 1, sourceStart: 1, sourceEnd: 50 }, { assemblyCtgId: 1, sourceStart: 51, sourceEnd: 100 }],
    [{ assemblyCtgId: 1, sourceStart: 1, sourceEnd: 100 }, { assemblyCtgId: 0, sourceStart: 1, sourceEnd: 100 }],
  ]) assert.equal(normalizeLocalFragment({ ...range, parts }), null);
});


test("re-adding a real parent after local edits creates an independent instance instead of aliasing interval keys", async () => {
  const { addSubviewCompositionMembers } = await import("../subview-composition-state.js");
  const parent = original();
  const split = splitLocalMember(composition([parent]), parent.entityKey, 40);
  const added = addSubviewCompositionMembers(split.composition, [parent], "top");
  assert.equal(added.changed, true);
  const copy = added.composition.members.find((member) => !member.localFragment);
  assert.notEqual(copy.entityKey, parent.entityKey);
  assert.equal(addSubviewCompositionMembers(added.composition, [parent], "top").changed, false);
  const copySplit = splitLocalMember(added.composition, copy.entityKey, 40);
  assert.equal(copySplit.changed, true);
  assert.equal(new Set(copySplit.composition.members.map((member) => member.entityKey)).size, 4);
  const removed = deleteLocalMember(copySplit.composition, copySplit.members[0].entityKey);
  assert.equal(removed.composition.members.length, 3);
  assert.ok(removed.composition.members.some((member) => member.entityKey === split.members[0].entityKey));
});
