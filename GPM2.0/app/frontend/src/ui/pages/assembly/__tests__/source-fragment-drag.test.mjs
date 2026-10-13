import test from "node:test";
import assert from "node:assert/strict";
import { collectSourceFragmentDragTargets, buildSourceFragmentDragPayload,
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

test("drag membership uses source AND instance identity, not selection, name, or orientation", () => {
  const first = node(1);
  const sibling = node(2, { "data-track-ref-orient": "-" });
  const others = [node(3, { "data-source-fragment-seq-id": "2" }),
    node(4, { "data-source-fragment-group": "n-fragment:chr:another" }),
    node(5, { "data-track-role": "support" }),
    node(6, { "data-track-dataset-id": "2" }),
    node(7, { "data-source-fragment-group": "" })];
  const host = { querySelectorAll: () => [first, sibling, ...others, sibling] };
  assert.deepEqual(collectSourceFragmentDragTargets(host, first), [
    { trackRole: "primary", assemblyCtgId: 1 }, { trackRole: "primary", assemblyCtgId: 2 },
  ]);
  assert.deepEqual(collectSourceFragmentDragTargets(host, others.at(-1)), [
    { trackRole: "primary", assemblyCtgId: 7 },
  ]);
});

test("phased siblings stay on the same track and retain distinct item identities", () => {
  const phased = (id, track, item) => node(id, { "data-track-role": "phased",
    "data-track-phased-track-id": String(track), "data-track-phased-track-item-id": String(item) });
  const first = phased(1, 40, 50), second = phased(2, 40, 51), otherTrack = phased(2, 41, 52);
  const targets = collectSourceFragmentDragTargets({ querySelectorAll: () => [first, second, otherTrack] }, first);
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

test("subview siblings may occupy different lanes but never another source representation", () => {
  const first = node(1, {}, true), second = node(2, { "data-subview-track-slot": "bottom" }, true);
  const mirror = node(3, { "data-subview-track-pair-is-mirror": "1" }, true);
  const targets = collectSourceFragmentDragTargets({ querySelectorAll: () => [first, second, mirror] }, first, { subview: true });
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
