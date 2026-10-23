import test from "node:test";
import assert from "node:assert/strict";
import { buildPhasedSubviewCtgPool } from "../subview-state.js";
import { buildSubviewCompositionCandidates, resolveSubviewCompositionCandidate } from "../subview-composition-candidates.js";
import { normalizeSubviewComposition } from "../subview-composition-state.js";
import { splitLocalMember, projectBackingCoordinate, projectLocalAlignment, projectLocalNRegions } from "../subview-fragment-model.js";
import { reconcileLocalCompositionWithMain } from "../subview-fragment-reconcile.js";

const source = { assemblyCtgId: 10, datasetId: 1, datasetName: "ds", originSourceSeqId: 7,
  name: "ctg", orient: "+", totalLength: 100, nRegions: [{ ctgStart: 10, ctgEnd: 20 }],
  hits: [{ ctgStart: 10, ctgEnd: 30, refStart: 200, refEnd: 220, blockLength: 21 }] };
const track = (items) => ({ phasedTrackId: 3, haplotypeKey: "A", items });
function candidates(ctgs, items) {
  return buildSubviewCompositionCandidates({ primaryDatasetId: 1, allChrCtgs: ctgs,
    phasedCtgs: buildPhasedSubviewCtgPool({ primaryCtgs: ctgs, phasedChrTracks: [track(items)] }) });
}

test("a phased orientation differs from its native backing orientation without double-flipping alignments or source N markers", () => {
  const pool = candidates([source], [{ assemblyCtgId: 10, itemId: 5, orient: "-" }]);
  const phased = pool.find((member) => member.source.role === "phased");
  assert.equal(phased.baseOrientation, "-"); assert.equal(phased.backingOrientation, "+");
  assert.equal(projectBackingCoordinate(phased, 10, 10), 91);
  const composition = normalizeSubviewComposition({ members: [phased] });
  const split = splitLocalMember(composition, phased.entityKey, 50);
  const low = split.members[0];
  assert.equal(projectBackingCoordinate(low, 10, 10), 41);
  assert.equal(projectBackingCoordinate(low, 10, 30), 21);
  const target = normalizeSubviewComposition({ members: [{ assemblyCtgId: 20, source: { role: "support" }, lengthBp: 100 }] }).members[0];
  const alignment = projectLocalAlignment(low, target, 10, 20, { topStart: 10, topEnd: 30, bottomStart: 10, bottomEnd: 30, strand: "+" });
  assert.equal(alignment.strand, "-"); assert.equal(alignment.topStart, 21); assert.equal(alignment.topEnd, 41);
  assert.deepEqual(projectLocalNRegions(low, pool).map((region) => [region.ctgStart, region.ctgEnd]), [[31, 41]]);
});

test("native main split rebinds a local phased object to new real children without borrowing another track or primary presentation", () => {
  const oldCandidates = candidates([source], [{ assemblyCtgId: 10, itemId: 5, orient: "-" }]);
  const phased = oldCandidates.find((member) => member.source.role === "phased");
  const local = splitLocalMember(normalizeSubviewComposition({ members: [phased] }), phased.entityKey, 40).composition;
  const live = [[701, 1, 60], [702, 61, 100]].map(([id, start, end]) => ({ ...source, assemblyCtgId: id,
    totalLength: end - start + 1, sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:10", sourceStart: start, sourceEnd: end } }));
  const updated = reconcileLocalCompositionWithMain(local, live);
  assert.deepEqual(updated.members.map((member) => member.lengthBp), [40, 60]);
  const newCandidates = candidates(live, live.map((ctg, index) => ({ assemblyCtgId: ctg.assemblyCtgId, itemId: 50 + index, orient: "-" })));
  for (const member of updated.members) {
    const found = resolveSubviewCompositionCandidate(newCandidates, member);
    assert.equal(found.source.role, "phased"); assert.equal(found.source.phasedTrackId, 3);
  }
  const wrongTrack = newCandidates.map((member) => ({ ...member, source: { ...member.source, phasedTrackId: 999 }, sourceKey: "wrong-track" }));
  assert.equal(resolveSubviewCompositionCandidate(wrongTrack, updated.members[0]), null);
});
