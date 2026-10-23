import { clearOtherViewSelection } from "../selection-state.js";
import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSubviewTrackPairSelectionCtgs, resolveFilteredSubviewTrackPairSelectionsFromAssembly } from "../subview-state.js";
import { normalizeSubviewComposition, applySubviewComposition } from "../subview-composition-state.js";
import { moveSubviewCompositionDrag, buildSourceFragmentDragPayload } from "../source-fragment-drag.js";
import { deleteSelectedSubviewTrackPairCtgs } from "../editor-actions-runtime.js";
import { commitSubviewHistoryOperation, rollbackSubviewHistory, restoreSubviewHistoryRollback } from "../subview-history-state.js";

test("composition box selection preserves instance keys and filters absent objects", () => {
  const composition = normalizeSubviewComposition({ members: [
    { assemblyCtgId: 1, entityKey: "first", source: { role: "primary" }, lengthBp: 100, xBp: 10 },
    { assemblyCtgId: 2, entityKey: "second", source: { role: "support" }, lane: "bottom", lengthBp: 100, xBp: 90 },
  ] });
  const selected = normalizeSubviewTrackPairSelectionCtgs([
    { trackRole: "primary", contigId: 1, compositionEntityKey: "first", slot: "top" },
    { trackRole: "support", contigId: 2, compositionEntityKey: "second", slot: "bottom" },
    { trackRole: "primary", contigId: 1, compositionEntityKey: "missing" },
  ]);
  const subview = applySubviewComposition({}, composition, { trackPairSelectedCtgs: selected });
  assert.equal(resolveFilteredSubviewTrackPairSelectionsFromAssembly({ subview }).length, 2);
  const payload = buildSourceFragmentDragPayload([
    { slot: "top", contigId: 1, compositionEntityKey: "first" },
    { slot: "bottom", contigId: 2, compositionEntityKey: "second" },
  ], [0, 0], -50, (v) => v, true);
  const moved = moveSubviewCompositionDrag(composition, payload);
  assert.deepEqual(moved.composition.members.map((m) => m.xBp), [-40, 40]);
  const next = applySubviewComposition(subview, moved.composition);
  assert.equal(next.trackPairSelectedCtgs.length, 2);
  const assembly = { selectedChrName: "Chr01", subview, subviewHistoryByKey: {} };
  const committed = commitSubviewHistoryOperation(assembly, { nextSubview: next, operation: { kind: "drag-contig" } });
  assert.equal(committed.changed, true);
  const undone = rollbackSubviewHistory(committed.assembly);
  assert.equal(undone.changed, true);
  assert.deepEqual(undone.assembly.subview.summary.members.map((m) => m.xBp), [10, 90]);
  const redone = restoreSubviewHistoryRollback(undone.assembly);
  assert.equal(redone.changed, true);
  assert.deepEqual(redone.assembly.subview.summary.members.map((m) => m.xBp), [-40, 40]);
});

test("Delete after a composition box selection removes exactly selected instances and is undoable", async () => {
  const composition = normalizeSubviewComposition({ members: [
    { assemblyCtgId: 1, entityKey: "a", source: { role: "primary" }, lengthBp: 100, xBp: 10 },
    { assemblyCtgId: 2, entityKey: "b", source: { role: "support" }, lane: "bottom", lengthBp: 100, xBp: 200 },
    { assemblyCtgId: 3, entityKey: "c", source: { role: "primary" }, lengthBp: 100, xBp: 500 },
  ] });
  const selection = [{ trackRole: "primary", contigId: 1, compositionEntityKey: "a" },
    { trackRole: "support", contigId: 2, compositionEntityKey: "b" }];
  const mainCtgs = [{ assemblyCtgId: 1 }, { assemblyCtgId: 3 }];
  let state = { locale: "en", assembly: { selectedChrName: "Chr01", chrCtgs: mainCtgs,
    subview: applySubviewComposition({}, composition, { trackPairSelectedCtgs: selection }) } };
  const store = { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } };
  let persisted = 0;
  await deleteSelectedSubviewTrackPairCtgs({}, store, selection, {
    confirm: async () => true, rerender() {},
    persistProjectAssemblyViewStateFromStore: async () => { persisted += 1; },
  });
  assert.deepEqual(state.assembly.subview.summary.members.map((m) => m.entityKey), ["c"]);
  assert.deepEqual(state.assembly.chrCtgs, mainCtgs);
  assert.equal(persisted, 1);
  const undone = rollbackSubviewHistory(state.assembly);
  assert.equal(undone.changed, true);
  assert.deepEqual(undone.assembly.subview.summary.members.map((m) => m.entityKey), ["a", "b", "c"]);
});

test("a new view selection clears only the other view's stale selection, not its edits", () => {
  const assembly = { trackSelectedCtgIds: [1], subview: { summary: { mode: "composition" },
    trackPairSelectedCtgs: [{ trackRole: "support", contigId: 2 }], manualAnchors: [{ manualAnchorId: "keep" }] } };
  const main = clearOtherViewSelection(assembly, "main");
  assert.deepEqual(main.trackSelectedCtgIds, [1]);
  assert.deepEqual(main.subview.trackPairSelectedCtgs, []);
  assert.equal(main.subview.summary, assembly.subview.summary);
  assert.equal(main.subview.manualAnchors, assembly.subview.manualAnchors);
  const local = clearOtherViewSelection(assembly, "subview");
  assert.deepEqual(local.trackSelectedCtgIds, []);
  assert.equal(local.subview, assembly.subview);
  assert.deepEqual(assembly.trackSelectedCtgIds, [1]);
});
