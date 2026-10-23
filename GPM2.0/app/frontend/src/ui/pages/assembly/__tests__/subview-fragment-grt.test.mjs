import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSubviewComposition } from "../subview-composition-state.js";
import { splitLocalMember, deleteLocalMember, mergeLocalMember, isolateLocalMemberInterval } from "../subview-fragment-model.js";
import { reconcileLocalCompositionWithMain } from "../subview-fragment-reconcile.js";
import { localGrtProjection, projectLocalGrtEvidence } from "../subview-fragment-grt.js";
import { buildGrtResultScene } from "../grt-result-render.js";
import { buildSubviewGrtAnchorScene } from "../subview-grt-anchor-state.js";

const normalize = (members) => normalizeSubviewComposition({ members });
const parent = (id = 10, patch = {}) => ({ assemblyCtgId: id, originSourceSeqId: id === 10 ? 7 : 8, label: `ctg${id}`,
  lengthBp: 100, xBp: 0, source: { role: id === 10 ? "primary" : "support", datasetId: id }, ...patch });
const entry = (member) => { const placed = { ...member, x: member.xBp, width: member.lengthBp };
  return { ...localGrtProjection(placed), key: member.entityKey, endpointKey: `local:${member.entityKey}`,
    ctg: { assemblyCtgId: member.assemblyCtgId, lengthBp: member.lengthBp, orient: member.baseOrientation },
    baseOrientation: member.baseOrientation, locallyFlipped: member.flipped, sourceRole: member.source.role,
    lane: member.lane, rect: { x: member.xBp, width: member.lengthBp }, y: member.lane === "bottom" ? 100 : 10, height: 14 }; };
const interval = (id, start = 1, end = 100) => ({ assemblyCtgId: id, assemblySourceStart: 1, assemblySourceEnd: 100,
  sourceStart: start, sourceEnd: end, datasetName: `ds${id}`, contigName: `ctg${id}`, orientation: "+", segmentId: `s${id}`, pathOrder: id });

for (const flipped of [false, true]) test(`GRT anchors resolve the unique surviving fragment at each source position, flipped=${flipped}`, () => {
  const before = normalize([parent(10, { flipped }), parent(20, { lane: "bottom" })]);
  const split = splitLocalMember(before, "assembly:10", 50);
  const entries = split.composition.members.map(entry);
  const plan = { junctions: [{ kind: "link", left: { ...interval(10), exitSourcePosition: 80 }, right: { ...interval(20), entrySourcePosition: 10 } }] };
  const scene = buildSubviewGrtAnchorScene({ chrName: "Chr1", plan, entries });
  assert.match(scene.markup, /data-subview-anchor-top-base-cut-bp="30"/);
  assert.match(scene.markup, new RegExp(`data-subview-anchor-top-cut-bp="${flipped ? 21 : 30}"`));
  const right = split.members.find((m) => m.localFragment.sourceStart === 51);
  const removed = deleteLocalMember(split.composition, right.entityKey);
  assert.equal(buildSubviewGrtAnchorScene({ chrName: "Chr1", plan, entries: removed.composition.members.map(entry) }).markup, "");
  const duplicate = { ...right, entityKey: "another-instance" };
  assert.equal(buildSubviewGrtAnchorScene({ chrName: "Chr1", plan, entries: [...entries, entry(duplicate)] }).markup, "", "overlapping presentations are ambiguous, not arbitrarily selected");
});

test("read-only GRT adoption overlays are clipped to surviving source bases, including native rebind lineage", () => {
  const before = normalize([parent(), parent(20, { lane: "bottom" })]);
  const split = splitLocalMember(before, "assembly:10", 50);
  const removed = deleteLocalMember(split.composition, split.members[0].entityKey);
  const remaining = removed.composition.members.find((m) => m.source.role === "primary");
  const projected = entry(remaining);
  const scene = buildGrtResultScene({ plan: { visualIntervals: [interval(10, 40, 80)], junctions: [] }, entries: [projected] });
  assert.match(scene.overlaysByKey.get(projected.key), /x="50.00"[^>]*width="30.00"/);
  const joined = mergeLocalMember(split.composition, split.members[0].entityKey, "right");
  const live = [
    { assemblyCtgId: 701, originSourceSeqId: 7, totalLength: 60, sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:10", sourceStart: 1, sourceEnd: 60 } },
    { assemblyCtgId: 702, originSourceSeqId: 7, totalLength: 40, sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:10", sourceStart: 61, sourceEnd: 100 } },
  ];
  const rebound = reconcileLocalCompositionWithMain(joined.composition, live);
  const reboundEntry = entry(rebound.members.find((m) => m.source.role === "primary"));
  assert.equal(reboundEntry.matchesSourceInterval(interval(10)), true);
  assert.equal(reboundEntry.projectSourcePosition(80, interval(10)), 79);
  assert.equal(reboundEntry.matchesSourceInterval(interval(999)), false);
});

for (const orientation of ["+", "-"]) test(`GRT display evidence clips both endpoints with one parameter across a deleted interval, orient=${orientation}`, () => {
  const before = normalize([parent(), parent(20, { lane: "bottom" })]);
  const isolated = isolateLocalMemberInterval(before, "assembly:10", 41, 60);
  const removed = deleteLocalMember(isolated.composition, isolated.member.entityKey);
  const entries = removed.composition.members.map(entry);
  const plan = { visualIntervals: [], junctions: [], displayEvidence: [{ tool: "minimap2",
    source: { ...interval(10), start: 1, end: 100, orientation },
    target: { ...interval(20), start: 1, end: 100 },
  }] };
  const projected = projectLocalGrtEvidence(plan, entries);
  assert.equal(projected.displayEvidence.length, 2);
  assert.deepEqual(projected.displayEvidence.map((e) => [e.source.start, e.source.end]), [[1, 40], [61, 100]]);
  assert.deepEqual(projected.displayEvidence.map((e) => [e.target.start, e.target.end]), orientation === "+" ? [[1, 40], [61, 100]] : [[61, 100], [1, 40]]);
  const scene = buildGrtResultScene({ plan: projected, entries });
  assert.equal((scene.junctionMarkup.match(/<polygon/g) || []).length, 2);
});
