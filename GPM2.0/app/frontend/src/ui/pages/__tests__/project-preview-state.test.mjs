import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../state/store.js";
import { buildProjectPreviewModel, previewProjectKey, requestPreviewChromosome } from "../project-preview-state.js";

const base = {
  chromosomes: [{ chrName: "Chr1", chrOrder: 1, chrLength: 2500 }], referenceGenomeId: 1,
  datasets: [{ datasetId: 1, name: "dsA" }, { datasetId: 2, name: "dsB" }],
  project: { primaryDatasetId: 1, supportDatasetIds: [2] },
  ctgs: [{ assemblyCtgId: 1, datasetId: 1, datasetName: "dsA", name: "ctgA", originId: "sourceA",
    assignedChrName: "Chr1", anchorStart: 400, orient: "+", refOrient: "+", memberCount: 1, totalLength: 1000,
    sourceFragment: { sourceStart: 1001, sourceEnd: 2000 } }],
};
const sourceSegment = { type: "ctg", overallLen: 2000, start: 1200, end: 1101, orient: "-",
  datasetName: "dsA", ctgName: "sourceA", source: { dataset: "dsA", contig: "sourceA", start: 1101, end: 1200, orientation: "-" } };

test("original-source fragments are aligned by adopted interval, including reverse orientation", () => {
  const [card] = buildProjectPreviewModel({ ...base, finalPathByChr: { Chr1: { segments: [sourceSegment] } } });
  const item = card.tracks.find(track => track.name === "dsA").positioned[0];
  assert.equal(item.start + item.highlights[0].start, card.paths[0].parts[0].start);
  assert.equal(item.highlights[0].end - item.highlights[0].start, 100);
  assert.equal(item.alignment.usedStart, 800);
  assert.equal(item.reverse, true);
  assert.equal(card.tracks.find(track => track.name === "dsA").laneCount, 1);
  assert.equal(card.tracks.find(track => track.name === "dsB").items.length, 0);
});

test("reused contigs keep one complete body and all adopted intervals", () => {
  const segment = { type: "ctg", assemblyCtgId: 1, datasetName: "dsA", ctgName: "ctgA", overallLen: 1000 };
  const [card] = buildProjectPreviewModel({ ...base, finalPathByChr: { Chr1: { segments: [
    { ...segment, start: 1, end: 100 }, { type: "gap", gapSizeBp: 1 }, { ...segment, start: 601, end: 650 },
  ] } } });
  const row = card.tracks.find(track => track.name === "dsA");
  assert.equal(row.positioned.length, 1);
  assert.equal(row.positioned[0].length, 1000);
  assert.deepEqual(row.positioned[0].highlights.map(patch => [patch.start, patch.end]), [[0, 100], [600, 650]]);
  assert.equal(row.positioned[0].start + row.positioned[0].highlights[0].start, 0);
  assert.equal(row.laneCount, 1);
  assert.equal(card.paths[0].length, 151);
  assert.equal(card.paths[0].parts[1].gap, true);
});

test("a hidden source remains traceable without fabricating reference placement", () => {
  const [card] = buildProjectPreviewModel({ ...base, ctgs: [], referenceGenomeId: 0,
    finalPathByChr: { Chr1: { segments: [sourceSegment] } } });
  assert.equal(card.hasReference, false);
  const track = card.tracks.find(track => track.name === "dsA"), item = track.unpositioned[0];
  assert.equal(track.positioned.length, 0);
  assert.ok(item.ghostKey);
  assert.equal(item.start, null);
  assert.equal(card.paths[0].length, 100);
});

test("card navigation requests the real chromosome without discarding current assembly edits", () => {
  const store = createStore({ activeRoute: "projectPreview", session: { workspacePath: "/ws", projectId: 1 },
    assembly: { selectedChrName: "Chr2", finalPathByChr: { draft: {} } },
    projectPreview: { chromosomes: [{ chrName: "Chr1" }] } });
  store.setState({ projectPreview: { ...store.getState().projectPreview, key: previewProjectKey(store.getState()) } });
  assert.ok(previewProjectKey(store.getState()));
  assert.equal(requestPreviewChromosome(store, "missing"), false);
  assert.equal(requestPreviewChromosome(store, "Chr1"), true);
  assert.equal(store.getState().activeRoute, "assembly");
  assert.equal(store.getState().assembly.previewRequestedChrName, "Chr1");
  assert.equal(store.getState().assembly.selectedChrName, "Chr2");
  assert.deepEqual(store.getState().assembly.finalPathByChr, { draft: {} });
});


test("reference follows the adopted contig anchor, including the NC_141022.1 left overhang", () => {
  const [card] = buildProjectPreviewModel({
    chromosomes: [{ chrName: "NC_141022.1", chrLength: 63929756 }], referenceGenomeId: 1,
    project: { primaryDatasetId: 1 },
    ctgs: [{ assemblyCtgId: 6, datasetId: 1, datasetName: "Mishima_AB", name: "ptg000006l",
      assignedChrName: "NC_141022.1", anchorStart: -25919310, orient: "-", totalLength: 76328920 },
    { assemblyCtgId: 40, datasetId: 1, datasetName: "Mishima_AB", name: "ptg000040l",
      assignedChrName: "NC_141022.1", anchorStart: 50475386, orient: "-", totalLength: 12765239 }],
    finalPathByChr: { "NC_141022.1": { segments: [
      { type: "ctg", start: 76328920, end: 1, source: { dataset: "Mishima_AB", contig: "ptg000006l", start: 1, end: 76328920, orientation: "-" } },
      { type: "gap", gapSizeBp: 100 },
      { type: "ctg", start: 12765239, end: 1, source: { dataset: "Mishima_AB", contig: "ptg000040l", start: 1, end: 12765239, orientation: "-" } },
    ] } },
  });
  assert.equal(card.reference.start, 25919310);
  assert.equal(card.reference.reverse, false);
  assert.deepEqual(card.reference.alignment, { pathName: "NC_141022.1", index: 0, offset: 25919310 });
  assert.equal(card.domain.end, 89849066);
  assert.equal(card.tracks[0].positioned[0].start, 0);
  assert.equal(card.paths[0].parts[2].start, 76329020);
});

test("trimmed and reversed adoption projects Ref and unused context through the same origin", () => {
  const [card] = buildProjectPreviewModel({ ...base,
    ctgs: [...base.ctgs, { ...base.ctgs[0], assemblyCtgId: 2, name: "unused", anchorStart: 500, totalLength: 50 }],
    finalPathByChr: { Chr1: { segments: [sourceSegment] } } });
  // Adopted source positions 1101..1200 are reversed. The whole Ref reverses
  // around that interval, rather than silently retaining its original origin.
  assert.equal(card.reference.start, -1900);
  assert.equal(card.reference.reverse, true);
  assert.equal(card.reference.alignment.offset, -1900);
  const unused = card.tracks[0].positioned.find(item => !item.alignment);
  assert.equal(unused.start, 50);
});

test("explicit reference adoption supplies its own origin; unknown sources do not invent anchors", () => {
  const [card] = buildProjectPreviewModel({ ...base, ctgs: [], finalPathByChr: { Chr1: { segments: [
    { type: "gap", gapSizeBp: 1000 },
    { type: "ctg", sourceKind: "ref_segment", referenceChrName: "Chr1", start: 501, end: 600,
      memberStartBp: 1, memberEndBp: 2500, overallLen: 2500 },
  ] } } });
  assert.equal(card.reference.start, 500);
  assert.equal(card.domain.end, 3000);
  const [unknown] = buildProjectPreviewModel({ ...base, ctgs: [], finalPathByChr: { Chr1: { segments: [sourceSegment] } } });
  assert.deepEqual(unknown.reference, { start: 0, reverse: false, alignment: null });
});


test("four datasets retain one primary and all three supports with shared Assembly role colors", () => {
  const datasets = [1, 2, 3, 4].map(datasetId => ({datasetId, name: `ds${datasetId}`}));
  const [card] = buildProjectPreviewModel({ ...base, datasets,
    project: {primaryDatasetId: 1, supportDatasetIds: [2, 3, 4]},
    ctgs: datasets.map(ds => ({assemblyCtgId: ds.datasetId, datasetId: ds.datasetId,
      datasetName: ds.name, name: `ctg${ds.datasetId}`, totalLength: 100, anchorStart: 0, assignedChrName: "Chr1"})),
    finalPathByChr: {Chr1: {segments: datasets.map(ds => ({type: "ctg", assemblyCtgId: ds.datasetId,
      datasetName: ds.name, ctgName: `ctg${ds.datasetId}`, start: 1, end: 100, overallLen: 100}))}} });
  assert.equal(card.tracks.length, 4);
  assert.deepEqual(card.tracks.map(t => t.role), ["primary", "companion", "companion", "companion"]);
  assert.deepEqual(card.tracks.map(t => t.color), ["#d2dfef", "#e7dec4", "#e7dec4", "#e7dec4"]);
  assert.deepEqual(card.paths[0].parts.map(p => p.role), ["primary", "companion", "companion", "companion"]);
});


test("mirrored and original aliases of a tiny donor produce one adopted source, not extra lanes", () => {
  const donor = { ...base.ctgs[0], name: "donor@Chr1", originId: "donor", totalLength: 31678158,
    sourceFragment: { sourceStart: 1, sourceEnd: 31678158 } };
  const [card] = buildProjectPreviewModel({ ...base, ctgs: [donor,
    { ...donor, assemblyCtgId: 2, name: "donor", assignedChrName: "Chr2" }],
    finalPathByChr: { Chr1: { segments: [{ type: "ctg", start: 17930989, end: 17953329,
      source: { dataset: "dsA", contig: "donor", start: 17930989, end: 17953329, orientation: "+" } }] } } });
  const row = card.tracks[0];
  assert.equal(row.positioned.length, 1);
  assert.equal(row.laneCount, 1);
  assert.equal(row.positioned[0].alignment.usedEnd - row.positioned[0].alignment.usedStart, 22341);
  assert.equal(card.paths[0].length, 22341);
});


test("full sources include unused portions, overhangs and unused Contigs in one compact row", () => {
  const ctg = { ...base.ctgs[0], totalLength: 1000, anchorStart: -100 };
  const [card] = buildProjectPreviewModel({ ...base, ctgs: [ctg,
    { ...ctg, assemblyCtgId: 2, name: "unused", originId: "unused", anchorStart: -200, totalLength: 3000 }],
    finalPathByChr: { Chr1: { segments: [sourceSegment] } } });
  const track = card.tracks[0];
  assert.equal(track.positioned.length, 2);
  assert.equal(track.laneCount, 1);
  for (const item of track.positioned) {
    assert.ok(card.domain.start <= item.start);
    assert.ok(card.domain.end >= item.start + item.length);
  }
  assert.ok(card.domain.start <= card.reference.start);
  assert.ok(card.domain.end >= card.reference.start + card.refLength);
  assert.equal(track.positioned[0].lane, 0);
  assert.equal(track.positioned[1].lane, 0);
  assert.ok(track.positioned[0].length >= track.positioned[1].length, "paint large backgrounds before small intervals");
});

test("overlapping auxiliary whole sources retain all bodies on one compact dataset strip", () => {
  const [card] = buildProjectPreviewModel({ ...base, ctgs: [0,1].map(i => ({ ...base.ctgs[0],
    assemblyCtgId: i + 1, name: `donor${i}`, originId: `donor${i}`, datasetName: "dsB", datasetId: 2,
    totalLength: 3000, anchorStart: 0, sourceFragment: null })),
    finalPathByChr: { Chr1: { segments: [0,1].map(i => ({ type: "ctg", assemblyCtgId: i + 1,
      datasetName: "dsB", start: i * 100 + 1, end: i * 100 + 50, overallLen: 3000 })) } } });
  const track = card.tracks.find(track => track.name === "dsB");
  assert.equal(track.laneCount, 1);
  assert.ok(track.positioned.every(item => item.length === 3000));
  assert.ok(track.positioned.every(item => item.highlights[0].end - item.highlights[0].start === 50));
});


test("a reverse-oriented assembly source keeps its complete body and nine adopted intervals", () => {
  const length = 43923636;
  const [card] = buildProjectPreviewModel({ chromosomes: [{ chrName: "chr01", chrLength: 43929697 }], referenceGenomeId: 1,
    datasets: [{ datasetId: 1, name: "pre" }, { datasetId: 2, name: "assembly" }],
    project: { primaryDatasetId: 1, supportDatasetIds: [2] },
    ctgs: [{ assemblyCtgId: 90, datasetId: 2, datasetName: "assembly", name: "contig_32@chr01", originId: "contig_32",
      totalLength: length, assignedChrName: "chr01", anchorStart: -4760, orient: "-", refOrient: null,
      sourceFragment: { sourceStart: 1, sourceEnd: length } }],
    finalPathByChr: { chr01: { segments: Array.from({ length: 9 }, (_, i) => ({ type: "ctg",
      start: 1000000 * (i + 1), end: 1000000 * (i + 1) + 99, orient: "-",
      source: { dataset: "assembly", contig: "contig_32", start: 1000000 * (i + 1), end: 1000000 * (i + 1) + 99, orientation: "-" } })) } } });
  const row = card.tracks.find(track => track.name === "assembly");
  assert.equal(row.positioned.length, 1);
  const item = row.positioned[0];
  assert.equal(item.length, length); assert.equal(item.displayOrient, "-");
  assert.equal(item.highlights.length, 9);
  assert.equal(item.highlights.reduce((sum, patch) => sum + patch.end - patch.start, 0), 900);
  assert.ok(card.domain.start <= item.start && card.domain.end >= item.start + length);
});
