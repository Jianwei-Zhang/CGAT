import test from "node:test";
import assert from "node:assert/strict";
import { buildProjectPreviewModel } from "../project-preview-state.js";
import { layoutProjectPreviewCard, syncProjectPreviewSources } from "../project-preview-layout.js";

const fixture = () => buildProjectPreviewModel({
  chromosomes: [{ chrName: "chr01", chrLength: 44000000 }], referenceGenomeId: 1,
  datasets: [{ datasetId: 1, name: "pre" }, { datasetId: 2, name: "assembly" }],
  project: { primaryDatasetId: 1, supportDatasetIds: [2] },
  ctgs: [
    { assemblyCtgId: 1, datasetId: 1, datasetName: "pre", name: "main", totalLength: 44000000,
      assignedChrName: "chr01", anchorStart: 0 },
    { assemblyCtgId: 2, datasetId: 2, datasetName: "assembly", name: "donor", totalLength: 31000000,
      assignedChrName: "chr01", anchorStart: -4760, orient: "-", sourceFragment: { sourceStart: 1, sourceEnd: 31000000 } },
  ], finalPathByChr: { chr01: { segments: [
    { type: "ctg", assemblyCtgId: 1, datasetName: "pre", ctgName: "main", start: 1, end: 10000000 },
    { type: "ctg", start: 17930000, end: 17930100,
      source: { dataset: "assembly", contig: "donor", start: 17930000, end: 17930100, orientation: "-" } },
    { type: "gap", gapSizeBp: 1 },
    { type: "ctg", assemblyCtgId: 1, datasetName: "pre", ctgName: "main", start: 10010000, end: 20000000 },
    { type: "ctg", start: 17930000, end: 17930100,
      source: { dataset: "assembly", contig: "donor", start: 17930000, end: 17930100, orientation: "+" } },
  ] } },
})[0];
const close = (actual, expected) => assert.ok(Math.abs(actual - expected) < 1e-7, `${actual} != ${expected}`);

test("all adopted intervals follow Final Path display boundaries, including reused reverse sources and resize", () => {
  const card = fixture(), before = structuredClone(card);
  for (const width of [1800, 900, 360]) {
    const geometry = layoutProjectPreviewCard(card, width);
    const path = geometry.paths.get("chr01");
    assert.ok(path[1].width >= 8, "keep short Final Path fragments visible rather than imposing bp scale");
    assert.ok(path[2].width >= 8, "keep gaps visible");
    for (const row of geometry.tracks) for (const body of row) {
      for (const highlight of body.highlights) {
        const target = path[highlight.patch.part.index];
        close(highlight.x, target.x); close(highlight.width, target.width);
        assert.ok(highlight.x >= body.x - 1e-7);
        assert.ok(highlight.x + highlight.width <= body.x + body.width + 1e-7);
      }
      assert.ok(body.width <= width, "never inflate a tiny donor scale over its whole body");
    }
    assert.equal(geometry.tracks[1].length, 1, "one complete donor body, not a body per use");
    assert.equal(geometry.tracks[1][0].highlights.length, 2);
  }
  assert.deepEqual(card, before, "display mapping cannot mutate scientific metadata");
});

test("split original fragments map only their covered portion within an enlarged path part", () => {
  for (const orientation of ["+", "-"]) {
    const [card] = buildProjectPreviewModel({ chromosomes: [{ chrName: "chr1", chrLength: 1000000 }],
      referenceGenomeId: 1, ctgs: [
        { assemblyCtgId: 1, datasetName: "a", name: "fragment", originId: "original", totalLength: 50,
          assignedChrName: "chr1", anchorStart: 0, sourceFragment: { sourceStart: 101, sourceEnd: 150 } },
      ], finalPathByChr: { chr1: { segments: [{ type: "ctg", start: 101, end: 200,
        source: { dataset: "a", contig: "original", start: 101, end: 200, orientation } }] } } });
    const geometry = layoutProjectPreviewCard(card, 1000), target = geometry.paths.get("chr1")[0];
    const patch = geometry.tracks[0][0].highlights[0];
    close(patch.width, target.width / 2);
    close(patch.x, target.x + (orientation === "-" ? target.width / 2 : 0));
  }
});

test("DOM source bodies and children are remeasured against the same path geometry", () => {
  const card = fixture();
  const sources = card.tracks.map(track => track.positioned.map(item => {
    const patches = item.highlights.map(() => ({ style: {} }));
    return { style: {}, patches, querySelectorAll: () => patches, querySelector: () => null };
  }));
  const plot = { clientWidth: 900 };
  const node = {
    querySelector: selector => selector === ".project-preview-reference" ? null : plot,
    querySelectorAll: () => sources.map(items => ({ querySelectorAll: () => items })),
  };
  for (const width of [900, 1700]) {
    plot.clientWidth = width; syncProjectPreviewSources(node, card);
    const geometry = layoutProjectPreviewCard(card, width);
    sources.forEach((row, i) => row.forEach((source, j) => {
      const body = geometry.tracks[i][j];
      close(parseFloat(source.style.left), body.x);
      source.patches.forEach((patch, k) => {
        close(parseFloat(source.style.left) + parseFloat(patch.style.left), body.highlights[k].x);
        close(parseFloat(patch.style.width), body.highlights[k].width);
      });
    }));
  }
});


test("explicit Ref adoption and separate phased paths use their own displayed segments", () => {
  const card = fixture();
  const refPart = { pathName: "phase2", index: 1, start: 1, length: 50,
    segment: { type: "ref", orient: "-" } };
  card.paths.push({ name: "phase2", length: 51, parts: [
    { pathName: "phase2", index: 0, start: 0, length: 1, gap: true, segment: { type: "gap" } }, refPart,
  ] });
  card.refHighlights = [{ start: 100, end: 150, part: refPart }];
  card.reference.reverse = true;
  const geometry = layoutProjectPreviewCard(card, 900);
  const ref = geometry.reference.highlights[0], target = geometry.paths.get("phase2")[1];
  close(ref.x, target.x); close(ref.width, target.width);
  for (const row of geometry.tracks) for (const body of row) for (const patch of body.highlights) {
    close(patch.x, geometry.paths.get("chr01")[patch.patch.part.index].x);
  }
});

test("empty paths keep unadopted context finite without inventing an adopted placement", () => {
  const card = fixture(); card.paths = [];
  card.tracks.forEach(track => track.positioned.forEach(item => { item.highlights = []; }));
  for (const width of [0, 800]) {
    const geometry = layoutProjectPreviewCard(card, width);
    for (const body of [geometry.reference, ...geometry.tracks.flat()]) {
      assert.ok(Number.isFinite(body.x) && Number.isFinite(body.width));
      assert.equal(body.highlights.length, 0);
    }
  }
});
