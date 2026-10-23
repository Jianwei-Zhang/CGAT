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
