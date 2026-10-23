import test from "node:test";
import assert from "node:assert/strict";
import { collectContigDragTargets, buildSourceFragmentDragPayload,
  setTrackDragGroupOffsets, setSubviewDragGroupOffsets, moveSubviewCompositionDrag,
} from "../source-fragment-drag.js";
import { normalizeSubviewComposition } from "../subview-composition-state.js";

const round = (value) => Math.round(value * 100) / 100;
function node(id, overrides = {}, subview = false) {
  const attrs = {
    "data-source-fragment-seq-id": "1", "data-source-fragment-group": "n-fragment:chr:one",
    ...(subview ? { "data-subview-contig-id": String(id), "data-subview-track-slot": "top",
      "data-subview-track-role": "primary", "data-subview-track-pair-dataset-id": "0" }
      : { "data-track-contig-id": String(id), "data-track-role": "primary", "data-track-dataset-id": "0" }),
    ...overrides,
  };
  return { getAttribute: (name) => attrs[name] ?? null };
}

test("a plain drag moves only the clicked object, never same-source siblings", () => {
  const first = node(1), sibling = node(2);
  assert.deepEqual(collectContigDragTargets({ querySelectorAll: () => [first, sibling] }, first),
    [{ trackRole: "primary", assemblyCtgId: 1 }]);
});

test("a selected leader moves the explicit visible selection, including unrelated sources", () => {
  const first = node(1), sibling = node(2), unrelated = node(3, { "data-source-fragment-seq-id": "2" });
  const support = node(4, { "data-track-role": "support" });
  const host = { querySelectorAll: () => [first, sibling, unrelated, support, unrelated] };
  assert.deepEqual(collectContigDragTargets(host, first, { selectedIds: [1, 3, 4, 999] }), [
    { trackRole: "primary", assemblyCtgId: 1 }, { trackRole: "primary", assemblyCtgId: 3 },
  ]);
  assert.deepEqual(collectContigDragTargets(host, sibling, { selectedIds: [1, 3] }),
    [{ trackRole: "primary", assemblyCtgId: 2 }]);
});

test("explicit selection does not cross native track instance boundaries", () => {
  const first = node(1, { "data-track-phased-track-id": "40", "data-track-phased-track-item-id": "50" });
  const second = node(2, { "data-track-phased-track-id": "40", "data-track-phased-track-item-id": "51" });
  const otherTrack = node(3, { "data-track-phased-track-id": "41", "data-track-phased-track-item-id": "52" });
  const targets = collectContigDragTargets({ querySelectorAll: () => [first, second, otherTrack] }, first,
    { selectedIds: [1, 2, 3] });
  assert.deepEqual(targets.map((entry) => [entry.assemblyCtgId, entry.phasedTrackId, entry.phasedTrackItemId]),
    [[1, 40, 50], [2, 40, 51]]);
});

test("same delta preserves old independent offsets, zero removes only the affected offset", () => {
  const targets = [1, 2].map((assemblyCtgId) => ({ trackRole: "primary", assemblyCtgId }));
  const before = [...targets.map((entry, i) => ({ ...entry, offsetBp: [10, -15][i] })),
    { trackRole: "primary", assemblyCtgId: 3, offsetBp: 77 }];
  const payload = buildSourceFragmentDragPayload(targets, [10, -15], 15, round);
  assert.deepEqual(payload.targets.map((entry) => entry.offsetBp), [25, 0]);
  const after = setTrackDragGroupOffsets(before, payload);
  assert.equal(after.find((entry) => entry.assemblyCtgId === 1).offsetBp, 25);
  assert.equal(after.some((entry) => entry.assemblyCtgId === 2), false);
  assert.equal(after.find((entry) => entry.assemblyCtgId === 3).offsetBp, 77);
  assert.equal(before[0].offsetBp, 10);
});

test("subview selection may occupy different lanes without implicit mirror inclusion", () => {
  const first = node(1, {}, true), second = node(2, { "data-subview-track-slot": "bottom" }, true);
  const mirror = node(3, { "data-subview-track-pair-is-mirror": "1" }, true);
  const targets = collectContigDragTargets({ querySelectorAll: () => [first, second, mirror] }, first, { subview: true,
    selectedEntries: [{ trackRole: "primary", contigId: 1 }, { trackRole: "primary", contigId: 2 }],
  });
  assert.deepEqual(targets, [{ slot: "top", contigId: 1 }, { slot: "bottom", contigId: 2 }]);
  const payload = buildSourceFragmentDragPayload(targets, [-20, 40], -10, round);
  assert.deepEqual(setSubviewDragGroupOffsets([], payload), [
    { slot: "top", contigId: 1, offsetBp: -30 }, { slot: "bottom", contigId: 2, offsetBp: 30 },
  ]);
});

test("composition drag moves sibling positions without merging members or changing other properties", () => {
  const composition = normalizeSubviewComposition({ members: [
    { assemblyCtgId: 1, xBp: -100, lengthBp: 40, flipped: true },
    { assemblyCtgId: 2, xBp: 200, lengthBp: 80, lane: "bottom" },
    { assemblyCtgId: 3, xBp: 900, lengthBp: 10 },
  ] });
  const targets = composition.members.slice(0, 2).map((member) => ({
    slot: member.lane, contigId: member.assemblyCtgId, compositionEntityKey: member.entityKey,
  }));
  const payload = buildSourceFragmentDragPayload(targets, [0, 0], -12.5, round);
  const result = moveSubviewCompositionDrag(composition, payload);
  assert.equal(result.changed, true);
  assert.deepEqual(result.composition.members.map((entry) => entry.xBp), [-112.5, 187.5, 900]);
  result.composition.members.forEach((entry, i) => {
    assert.deepEqual({ ...entry, xBp: composition.members[i].xBp }, composition.members[i]);
  });
  assert.deepEqual(composition.members.map((entry) => entry.xBp), [-100, 200, 900]);
});

test("local selection can translate both datasets and honors composition instance identity", () => {
  const first = node(1, { "data-subview-composition-entity-key": "fragment:a" }, true);
  const other = node(2, { "data-subview-track-role": "support", "data-subview-track-slot": "bottom",
    "data-subview-composition-entity-key": "fragment:b" }, true);
  const sameSource = node(1, { "data-subview-composition-entity-key": "fragment:c" }, true);
  const targets = collectContigDragTargets({ querySelectorAll: () => [first, other, sameSource] }, first, {
    subview: true, selectedEntries: [{ compositionEntityKey: "fragment:a" }, { compositionEntityKey: "fragment:b" }],
  });
  assert.deepEqual(targets, [
    { slot: "top", contigId: 1, compositionEntityKey: "fragment:a" },
    { slot: "bottom", contigId: 2, compositionEntityKey: "fragment:b" },
  ]);
  const payload = buildSourceFragmentDragPayload(targets, [0, 0], -15, round, true);
  assert.equal(payload.dragSelection, true);
  assert.deepEqual(payload.targets.map((entry) => entry.dragDeltaBp), [-15, -15]);
});
