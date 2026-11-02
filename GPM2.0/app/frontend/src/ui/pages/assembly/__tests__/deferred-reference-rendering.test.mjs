import {ensureSubviewReferenceEvidence} from "../reference-evidence-loading.js";
import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { decodeReferenceTracks } from "../../../../services/workflow/reference-transport.js";
import { hasDeferredReferenceHits, readReferenceHits } from "../../../../services/workflow/reference-evidence.js";
import { packReferenceWire } from "../../../../services/__tests__/reference-transport-fixture.mjs";
import { createStore } from "../../../../state/store.js";
import { selectChromosome } from "../assembly-data-runtime.js";
import { buildRefSubviewCtgPool } from "../subview-state.js";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";
import { applySubviewComposition } from "../subview-composition-state.js";
import { clearAssemblySessionCache, rememberAssemblyState, restoreAssemblyState } from "../../../shell/assembly-session-cache.js";

function wire() {
  const group = (id, datasetId, strand, identity) => [id, datasetId, id + 100, strand, identity, 60];
  return { encoding: "reference-hits-v1", items: [0, 1].map(index => ({
    assemblyCtgId: 9001 + index, sourceKind: "ref_segment", referenceChrId: 1,
    referenceChrName: "Chr01", segmentOrder: index + 1,
    segmentStartBp: 1 + index * 16000, segmentEndBp: (index + 1) * 16000,
    anchorStart: 1 + index * 16000, totalLength: 16000, refOrient: "+",
    name: `ref_Chr01:${1 + index * 16000}-${(index + 1) * 16000}`,
    hitGroups: [group(10, 11, "+", 93.27), group(20, 22, "-", 0)],
    hitRows: [[0, 100, 1399, 500, 1799, 1200, 1300, 500, 1799],
      [1, 30, 32, 1000, 1002, 0, 3, 1000, 1002],
      [0, 2000, 3299, 2500, 3799, 1200, 1300, 2500, 3799]],
  })) };
}
function stateWith(members, mode = "none", flip = false) {
  const state = createIdentityRenderState();
  state.assembly.refTrackMembers = members;
  state.assembly.subview.pairwiseEvidence = null;
  if (mode === "none") state.assembly.subview.summary = null;
  if (mode === "primary-pair") state.assembly.subview.summary = { mode: "2-contig", top: { role: "support", contigId: 30 }, bottom: { role: "primary", contigId: 2 } };
  if (mode === "ref-primary") state.assembly.subview.summary = { mode: "2-contig", top: { role: "ref", contigId: 9001 }, bottom: { role: "primary", contigId: 2 } };
  if (mode === "primary-ref") state.assembly.subview.summary = { mode: "2-contig", top: { role: "primary", contigId: 2 }, bottom: { role: "ref", contigId: 9001 } };
  if (mode === "track-ref-primary") state.assembly.subview.summary = { mode: "track-pair", topTrack: { role: "ref" }, bottomTrack: { role: "primary" } };
  if (mode === "track-ref-support") state.assembly.subview.summary = { mode: "track-pair", topTrack: { role: "ref" }, bottomTrack: { role: "support", datasetId: 22, source: "mother" } };
  if (mode === "ref-ref") {
    state.assembly.subview.summary = { mode: "2-contig", top: { role: "ref", contigId: 9001 }, bottom: { role: "ref", contigId: 9002 } };
    state.assembly.subview.activeAnchors = [{ hitKey: "hit-2", edge: "left" }];
  }
  if (flip) state.assembly.subview.flippedCtgs = [{ slot: "top", contigId: mode === "primary-ref" ? 2 : 9001 }];
  if (mode === "composition") {
    const candidates = buildSubviewCompositionCandidates({
      allChrCtgs: state.assembly.chrCtgs, refCtgs: buildRefSubviewCtgPool(members), primaryDatasetId: 11,
    });
    state.assembly.subview = applySubviewComposition({}, { members: candidates.filter(candidate => candidate.assemblyCtgId !== 9002).map(candidate => ({
      ...candidate, lane: candidate.source.role === "ref" ? "top" : "bottom", flipped: flip && candidate.source.role === "ref", xBp: 0,
    })) });
    state.assembly.subviewCompositionCandidates = candidates;
    state.assembly.subviewCompositionCandidatesLoaded = true;
  }
  return state;
}

for (const format of ["v1", "v2"]) for (const mode of ["none", "primary-pair", "ref-primary", "primary-ref", "track-ref-primary", "track-ref-support", "composition", "ref-ref"]) for (const flip of [false, true]) {
  test(`${format} ${mode} flip=${flip}: complete page HTML, band identity, keys, anchors and geometry match full evidence`, () => {
    const full = decodeReferenceTracks(wire()).items;
    const deferred = decodeReferenceTracks(format === "v1" ? wire() : packReferenceWire(wire()), { deferHits: true }).items;
    let reads = 0;
    for (const member of deferred) {
      const evidence = member.referenceEvidence, key = format === "v1" ? "hitRows" : "hitData", data = evidence[key];
      Object.defineProperty(evidence, key, { enumerable: true, get() { reads++; return data; } });
    }
    const expected = renderAssemblyPage(stateWith(full, mode, flip));
    const actual = renderAssemblyPage(stateWith(deferred, mode, flip));
    assert.equal(actual, expected);
    if (mode !== "ref-ref") assert.equal(reads, 0, "metadata/opposite-side projection must not touch packed rows");
    else assert.ok(reads > 0, "raw Ref-to-Ref compatibility must still read its full evidence");
    if (["ref-primary", "primary-ref", "track-ref-primary", "composition"].includes(mode)) {
      assert.match(actual, /data-subview-hit-key=/);
      assert.match(actual, /data-band-identity-pct="93\.27"/);
    }
  });
}

test("metadata pools retain complete evidence and dataset-scoped reads remain exact", () => {
  const members = decodeReferenceTracks(packReferenceWire(wire()), { deferHits: true }).items;
  const filtered = buildRefSubviewCtgPool(members, { datasetId: 11 });
  assert.equal(filtered[0].referenceEvidence, members[0].referenceEvidence);
  assert.equal(Object.hasOwn(filtered[0], "hits"), false);
  assert.deepEqual(readReferenceHits(filtered[0]), readReferenceHits(members[0]).filter(hit => hit.datasetId === 11));
  assert.equal(readReferenceHits(members[0]).length, 3, "the dataset view must not discard backing evidence");
});

test("real chromosome normalization opts into deferral without cloning or reading packed rows", async () => {
  const members = decodeReferenceTracks(packReferenceWire(wire()), { deferHits: true }).items;
  const state = stateWith(members);
  state.activeRoute = "assembly";
  const store = createStore(state);
  const payload = store.getState().assembly.refTrackMembers[0].referenceEvidence;
  const data = payload.hitData;
  Object.defineProperty(payload, "hitData", { enumerable: true, get() { assert.fail("normalization must not decode raw hits"); return data; } });
  await selectChromosome({}, store, "Chr01", {
    getCurrentProject: () => ({ primaryDatasetId: 11 }),
    normalizeSupportDatasetId: id => Number(id),
    buildClearedSubviewState: () => ({ summary: null }),
    listChrViewCtgs: async () => ({ items: state.assembly.chrCtgs }),
    listReferenceTrackMembers: async args => { assert.equal(args.deferHits, true); return { items: store.getState().assembly.refTrackMembers.length ? store.getState().assembly.refTrackMembers : [{ ...members[0], referenceEvidence: payload }] }; },
    loadDatasetChrCtgs: async () => [], loadDeletedCtgsForChr: async () => [],
    loadSideDataForCtg: async () => ({ detail: { members: [] } }),
    mapAssemblyError: ({ error }) => ({ userMessage: error.message }),
    patchSelection() {}, rerender() {},
  });
  assert.equal(store.getState().assembly.error, "");
  assert.equal(store.getState().assembly.refTrackMembers[0].referenceEvidence, payload);
});

test("actual project-state cache restores cloneable deferred evidence and identical rendering", () => {
  clearAssemblySessionCache();
  try {
    const state = stateWith(decodeReferenceTracks(packReferenceWire(wire()), { deferHits: true }).items, "ref-primary");
    const html = renderAssemblyPage(state);
    assert.equal(rememberAssemblyState(state), true);
    const assembly = restoreAssemblyState(state);
    assert.ok(hasDeferredReferenceHits(assembly.refTrackMembers[0]));
    assert.equal(renderAssemblyPage({ ...state, assembly }), html);
    assert.deepEqual(readReferenceHits(assembly.refTrackMembers[0]), readReferenceHits(state.assembly.refTrackMembers[0]));
  } finally { clearAssemblySessionCache(); }
});

for (const flip of [false, true]) {
  test(`preserved anchors below the display threshold retain their original Ref hit keys, flip=${flip}`, () => {
    const legacy = stateWith(decodeReferenceTracks(wire()).items, "ref-ref", flip);
    const deferred = stateWith(decodeReferenceTracks(packReferenceWire(wire()), { deferHits: true }).items, "ref-ref", flip);
    legacy.assembly.subviewTrackView.alignmentLength = 1000;
    deferred.assembly.subviewTrackView.alignmentLength = 1000;
    const expected = renderAssemblyPage(legacy);
    assert.equal(renderAssemblyPage(deferred), expected);
    assert.match(expected, /data-subview-hit-key="[^"]*hit-2/);
  });
}


for (const mode of ["none","primary-pair","ref-primary","primary-ref","track-ref-primary","track-ref-support","composition"]) for (const flip of [false,true]) {
 test(`geometry-only ${mode} flip=${flip} has identical complete HTML and colors without raw Ref hits`,()=>{
  const full=decodeReferenceTracks(wire()).items;
  const geometry=decodeReferenceTracks({encoding:"reference-geometry-v1",items:wire().items},{deferHits:true}).items;
  assert.equal(renderAssemblyPage(stateWith(geometry,mode,flip)),renderAssemblyPage(stateWith(full,mode,flip)));
 });
}
for (const flip of [false,true])test(`Ref/Ref after explicit raw hydration preserves full HTML and hit-N anchors flip=${flip}`,async()=>{
 const full=decodeReferenceTracks(wire()).items;
 const geometry=decodeReferenceTracks({encoding:"reference-geometry-v1",items:wire().items},{deferHits:true}).items;
 const store=createStore(stateWith(geometry,"ref-ref",flip));
 assert.match(renderAssemblyPage(store.getState()),/aria-busy="true"/);
 assert.equal(await ensureSubviewReferenceEvidence(null,store,{load:async()=>decodeReferenceTracks(packReferenceWire(wire()),{deferHits:true}),render(){},mapError:e=>e.message}),true);
 assert.equal(renderAssemblyPage(store.getState()),renderAssemblyPage(stateWith(full,"ref-ref",flip)));
});
