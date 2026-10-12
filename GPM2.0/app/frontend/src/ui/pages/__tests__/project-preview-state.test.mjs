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

test("reused contigs split into independently aligned parts instead of being matched by name alone", () => {
  const segment = { type: "ctg", assemblyCtgId: 1, datasetName: "dsA", ctgName: "ctgA", overallLen: 1000 };
  const [card] = buildProjectPreviewModel({ ...base, finalPathByChr: { Chr1: { segments: [
    { ...segment, start: 1, end: 100 }, { type: "gap", gapSizeBp: 1 }, { ...segment, start: 601, end: 650 },
  ] } } });
  const row = card.tracks.find(track => track.name === "dsA");
  assert.equal(row.positioned.length, 2);
  assert.equal(row.positioned[0].start + row.positioned[0].alignment.usedStart, 0);
  assert.equal(row.positioned[1].start + row.positioned[1].alignment.usedStart, 101);
  assert.equal(row.laneCount, 1);
  assert.equal(card.paths[0].length, 151);
  assert.equal(card.paths[0].parts[1].gap, true);
});

test("a hidden source remains traceable without fabricating reference placement", () => {
  const [card] = buildProjectPreviewModel({ ...base, ctgs: [], referenceGenomeId: 0,
    finalPathByChr: { Chr1: { segments: [sourceSegment] } } });
  assert.equal(card.hasReference, false);
  const item = card.tracks.find(track => track.name === "dsA").positioned[0];
  assert.ok(item.ghostKey);
  assert.equal(item.start + item.alignment.usedStart, 0);
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
