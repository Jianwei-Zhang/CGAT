import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSubviewComposition, applySubviewComposition } from "../subview-composition-state.js";
import { reconcileLocalCompositionWithMain, reconcileLocalSubviewWithMain } from "../subview-fragment-reconcile.js";
import { projectBackingCoordinate, splitLocalMember, memberSourceInterval } from "../subview-fragment-model.js";
import { commitSubviewHistoryOperation, rollbackSubviewHistory } from "../subview-history-state.js";

const parent = { assemblyCtgId: 10, originSourceSeqId: 7, lengthBp: 100, label: "ctg", xBp: 500,
  source: { role: "primary", datasetId: 2 }, baseOrientation: "+" };
const live = (id, start, end, orient = "+") => ({ assemblyCtgId: id, originSourceSeqId: 7,
  totalLength: end - start + 1, orient, sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:10", sourceStart: start, sourceEnd: end } });

test("real main split and undo rebind the backing entities without merging independent local partitions", () => {
  const composition = normalizeSubviewComposition({ members: [parent] });
  const local = splitLocalMember(composition, "assembly:10", 60).composition;
  const rebound = reconcileLocalCompositionWithMain(local, [live(11, 1, 40), live(12, 41, 100)]);
  assert.deepEqual(rebound.members.map((m) => m.lengthBp), [60, 40]);
  assert.deepEqual(rebound.members.map((m) => m.entityKey), local.members.map((m) => m.entityKey));
  assert.equal(rebound.members[0].localFragment.parts.length, 2);
  assert.equal(projectBackingCoordinate(rebound.members[0], 12, 1), 41);
  const undoneMain = reconcileLocalCompositionWithMain(rebound, [{ assemblyCtgId: 10, originSourceSeqId: 7, totalLength: 100, orient: "+" }]);
  assert.deepEqual(undoneMain.members.map((m) => m.lengthBp), [60, 40]);
  assert.ok(undoneMain.members.every((m) => m.localFragment.parts[0].assemblyCtgId === 10));
});

test("real partial main deletion clips all local snapshots and preserves surviving world positions", () => {
  const initial = normalizeSubviewComposition({ members: [parent] });
  const split = splitLocalMember(initial, "assembly:10", 50).composition;
  const subview = applySubviewComposition({}, initial);
  const operation = commitSubviewHistoryOperation({ selectedChrName: "Chr1", subview }, {
    nextSubview: applySubviewComposition(subview, split), operation: { kind: "split-contig" },
  });
  const updated = reconcileLocalSubviewWithMain({ ...operation.assembly,
    chrCtgs: [live(11, 1, 30), live(12, 71, 100)] });
  assert.deepEqual(updated.subview.summary.members.map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd, m.xBp]), [[1, 30, 500], [71, 100, 570]]);
  const undo = rollbackSubviewHistory(updated);
  assert.equal(undo.changed, true);
  assert.deepEqual(undo.assembly.subview.summary.members.map((m) => [memberSourceInterval(m).sourceStart, memberSourceInterval(m).sourceEnd]), [[1, 30], [71, 100]]);
  assert.equal(updated.subviewHistoryByKey["composition:Chr1"].past.length, 1);
});

test("native orientation changes update coordinate mapping without flipping the independent local instance", () => {
  const initial = normalizeSubviewComposition({ members: [parent] });
  const updated = reconcileLocalCompositionWithMain(initial, [{ assemblyCtgId: 10, originSourceSeqId: 7, totalLength: 100, orient: "-" }]);
  assert.equal(updated.members[0].baseOrientation, "+");
  assert.equal(updated.members[0].flipped, false);
  assert.equal(projectBackingCoordinate(updated.members[0], 10, 100), 1);
  assert.equal(updated.members[0].xBp, 500);
});

test("same-source independent copies are never used to resurrect a deleted instance, and auxiliary members stay independent", () => {
  const initial = normalizeSubviewComposition({ members: [parent, { ...parent, assemblyCtgId: 20, source: { role: "support", datasetId: 3 } }] });
  const updated = reconcileLocalCompositionWithMain(initial, [{ ...live(30, 1, 100), sourceFragment: { ...live(30, 1, 100).sourceFragment, groupKey: "manual-fragment:other-instance" } }]);
  assert.deepEqual(updated.members.map((m) => m.assemblyCtgId), [20]);
});


test("pairwise evidence cache identity follows real backing changes while local object identity stays stable", async () => {
  const { buildSubviewPairwiseEvidenceKey } = await import("../subview-pairwise-evidence-state.js");
  const initial = normalizeSubviewComposition({ members: [parent, { ...parent, assemblyCtgId: 20,
    lane: "bottom", source: { role: "support", datasetId: 3 } }] });
  const original = buildSubviewPairwiseEvidenceKey({ mode: "composition", members: initial.members });
  const rebound = reconcileLocalCompositionWithMain(initial, [live(11, 1, 40), live(12, 41, 100)]);
  assert.equal(rebound.members[0].entityKey, initial.members[0].entityKey);
  const next = buildSubviewPairwiseEvidenceKey({ mode: "composition", members: rebound.members });
  assert.notEqual(next, original);
  assert.equal(next, "composition:primary:2:mother:11+12|support:3:mother:20");
  assert.deepEqual(rebound.members[0].localFragment.parts.map((part) => [part.assemblyCtgId, part.sourceStart, part.sourceEnd]),
    [[11, 1, 40], [12, 41, 100]], "source intervals remain exact even though evidence is cached by backing IDs");
});


for (const baseOrientation of ["+", "-"]) for (const flipped of [false, true]) {
  for (const sourceKnown of [false, true]) {
    test(`Main split materializes independent Local pieces and preserves anchors: base=${baseOrientation}, flipped=${flipped}, sourceKnown=${sourceKnown}`, async () => {
      const { memberAnchorEndpointKey } = await import("../subview-fragment-model.js");
      const primary = { ...parent, originSourceSeqId: sourceKnown ? 7 : undefined,
        baseOrientation, flipped, lane: "bottom" };
      const support = { ...parent, assemblyCtgId: 20, lane: "top", source: { role: "support", datasetId: 3 } };
      const initial = normalizeSubviewComposition({ members: [primary, support] });
      const selected = initial.members[0];
      initial.manualAnchors = [{ manualAnchorId: "cut-anchor", endpointA: {
        endpointKey: memberAnchorEndpointKey(selected), contigId: 10, lengthBp: 100,
        cutBp: baseOrientation === "-" ? 61 : 41, sourceCutAfter: 40,
      }, endpointB: { endpointKey: memberAnchorEndpointKey(initial.members[1]), contigId: 20,
        cutBp: 50, lengthBp: 100 } }];
      const updated = reconcileLocalSubviewWithMain({ selectedChrName: "Chr1",
        subview: applySubviewComposition({}, initial), chrCtgs: [live(11, 1, 40), live(12, 41, 100)] });
      const members = updated.subview.summary.members.filter((member) => member.source.role === "primary");
      assert.equal(members.length, 2, "not one aggregate object with only an internal marker");
      assert.deepEqual(members.map((member) => [member.assemblyCtgId, member.lengthBp]), [[11, 40], [12, 60]]);
      assert.equal(new Set(members.map((member) => member.entityKey)).size, 2);
      const reverse = (baseOrientation === "-") !== flipped;
      assert.deepEqual(members.map((member) => member.xBp), reverse ? [560, 500] : [500, 540]);
      assert.ok(members.every((member) => member.baseOrientation === baseOrientation && member.flipped === flipped));
      assert.equal(updated.subview.manualAnchors.length, 1);
      const endpoint = updated.subview.manualAnchors[0].endpointA;
      assert.equal(endpoint.sourceCutAfter, 40);
      assert.equal(endpoint.contigId, baseOrientation === "-" ? 11 : 12);
      assert.ok(members.some((member) => memberAnchorEndpointKey(member) === endpoint.endpointKey));
      const again = reconcileLocalSubviewWithMain(updated);
      assert.deepEqual(again.subview.summary.members, updated.subview.summary.members, "reload must be idempotent");
    });
  }
}

test("a local merge remains explicit and survives Main reload without rejoining unrelated local pieces", async () => {
  const { mergeLocalMember } = await import("../subview-fragment-model.js");
  const { activateSubviewCompositionHistory } = await import("../subview-history-state.js");
  const initial = { selectedChrName: "Chr1", subview: applySubviewComposition({}, { members: [parent] }),
    chrCtgs: [{ ...parent, totalLength: 100 }] };
  const activated = activateSubviewCompositionHistory(initial).assembly;
  let updated = reconcileLocalSubviewWithMain({ ...activated, chrCtgs: [live(11, 1, 40), live(12, 41, 100)] });
  assert.equal(updated.subview.summary.members.length, 2);
  const key = "composition:Chr1";
  assert.equal(updated.subviewHistoryByKey[key].past.length, 0, "Main splitting must not add a Local undo step");
  assert.equal(updated.subviewHistoryByKey[key].current.composition.members.length, 2);
  const left = updated.subview.summary.members[0];
  const merged = mergeLocalMember({ members: updated.subview.summary.members }, left.entityKey, "right");
  assert.equal(merged.changed, true);
  updated = commitSubviewHistoryOperation(updated, {
    nextSubview: applySubviewComposition(updated.subview, merged.composition), operation: { kind: "merge-fragments" },
  }).assembly;
  const reopened = reconcileLocalSubviewWithMain(JSON.parse(JSON.stringify(updated)));
  assert.equal(reopened.subview.summary.members.length, 1, "respect the user's explicit local merge");
  assert.deepEqual(reopened.subview.summary.members[0].localFragment.suppressedCuts, [40]);
});

test("local history can still restore its old presentation without undoing the real Main split", () => {
  const initial = { selectedChrName: "Chr1", subview: applySubviewComposition({}, { members: [parent] }) };
  const shifted = { ...initial.subview.summary.members[0], xBp: 900 };
  const edited = commitSubviewHistoryOperation(initial, {
    nextSubview: applySubviewComposition(initial.subview, { members: [shifted] }), operation: { kind: "drag-contig" },
  }).assembly;
  const updated = reconcileLocalSubviewWithMain({ ...edited, chrCtgs: [live(11, 1, 40), live(12, 41, 100)] });
  assert.equal(updated.subview.summary.members.length, 2);
  assert.equal(updated.subviewHistoryByKey["composition:Chr1"].past.length, 1);
  const undo = rollbackSubviewHistory(updated);
  assert.equal(undo.changed, true);
  const reopened = reconcileLocalSubviewWithMain(undo.assembly);
  assert.equal(reopened.chrCtgs.length, 2, "local undo never restores the retired Main parent");
  assert.equal(reopened.subview.summary.members.length, 1);
  assert.equal(reopened.subview.summary.members[0].xBp, 500);
});


test("previously saved aggregate backing is split on reopen unless the user explicitly merged it", () => {
  const children = [live(11, 1, 40), live(12, 41, 100)];
  const aggregate = reconcileLocalCompositionWithMain(normalizeSubviewComposition({ members: [parent] }), children);
  // Older versions rebound both native IDs to one Local rectangle and only
  // drew an internal cut; this is not an intentional user merge.
  delete aggregate.members[0].localFragment.suppressedCuts;
  const sourceBefore = JSON.stringify(children);
  const reopened = reconcileLocalSubviewWithMain({ selectedChrName: "Chr1",
    subview: applySubviewComposition({}, aggregate), chrCtgs: children });
  assert.deepEqual(reopened.subview.summary.members.map((member) => [member.assemblyCtgId, member.lengthBp]),
    [[11, 40], [12, 60]]);
  assert.equal(JSON.stringify(reopened.chrCtgs), sourceBefore, "rebind must not perform another native split");
});
