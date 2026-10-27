import { runFinalPathExportAction } from "../final-path-export-runtime.js";
import { test, assert, renderAssemblyPage, createState, createStore } from "./tabs-semantics-harness.mjs";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";
import { applySubviewComposition, normalizeSubviewComposition } from "../subview-composition-state.js";
import { sliceLocalMember } from "../subview-fragment-model.js";

const projections = html => [...html.matchAll(/data-source-interval-projection="([^"]+)"/g)]
  .map(match => JSON.parse(match[1].replaceAll("&quot;", '"').replaceAll("&amp;", "&")));

test("real Main and clipped/reversed Local rendering publish biological intervals independently of plot positions", () => {
  const ctg = { assemblyCtgId: 1, datasetId: 1, datasetName: "Data", name: "ctg1", totalLength: 10000,
    anchorStart: 900000, refOrient: "+", assignedChrName: "Chr01" };
  const candidates = buildSubviewCompositionCandidates({ primaryDatasetId: 1, allChrCtgs: [ctg] });
  const parent = normalizeSubviewComposition({ members: [{ ...candidates[0], lane: "top", xBp: 123456 }] }).members[0];
  const member = sliceLocalMember(parent, 4001, 8000); member.flipped = true;
  const html = renderAssemblyPage(createState({ assembly: { chrCtgs: [ctg],
    subview: applySubviewComposition({}, { members: [member] }), subviewCompositionCandidates: candidates,
    subviewCompositionCandidatesLoaded: true } }));
  const ranges = projections(html);
  assert.ok(ranges.some(range => range.assemblyCtgId === 1 && range.sourceStart === 1 && range.sourceEnd === 10000));
  assert.ok(ranges.some(range => range.parts?.[0].assemblyCtgId === 1 && range.sourceStart === 4001
    && range.sourceEnd === 8000 && range.orient === "-"));
  assert.ok(ranges.every(range => range.sourceStart !== 123456 && range.sourceStart !== 900000));
});

test("live Final Path has a complete localized controlled tooltip and no duplicate native title", () => {
  for (const [locale, adopted, source] of [["en", "Adopted length", "Source contig length"], ["zh", "采用片段长度", "源 Contig 总长度"]]) {
    const html = renderAssemblyPage({ ...createState({ assembly: { finalPathByChr: { Chr01: { chrName: "Chr01", mode: "segments",
      segments: [{ type: "ctg", segmentId: "selected", assemblyCtgId: 1, datasetName: "Data", ctgName: "ctg1",
        overallLen: 10000, start: 5001, end: 10000 }] } } } }), locale });
    assert.ok(html.includes(`${adopted}: 5,000 bp`));
    assert.ok(html.includes(`${source}: 10,000 bp`));
    assert.match(html, /data-final-path-tooltip="Data_ctg1\n/);
    assert.doesNotMatch(html, /<title>Data_ctg1/);
    assert.match(html, /<desc>Data_ctg1\n/);
  }
});


test("mirrored split sources supply original interval and full source length to live tooltips", () => {
  const mirrored = { assemblyCtgId: 90, datasetId: 2, datasetName: "Data", name: "mirror", totalLength: 4000,
    sourceFragment: { sourceSeqId: 7, groupKey: "source:7", sourceStart: 6001, sourceEnd: 10000, sourceLength: 15000 } };
  const html = renderAssemblyPage({ ...createState({ assembly: { supportMirroredCtgs: [mirrored],
    finalPathByChr: { Chr01: { chrName: "Chr01", mode: "segments", segments: [{ type: "ctg", segmentId: "mirror",
      assemblyCtgId: 90, datasetName: "Data", ctgName: "mirror", overallLen: 4000, start: 1, end: 4000 }] } } } }), locale: "en" });
  assert.match(html, /Source contig length: 15,000 bp/);
  assert.match(html, /Source interval: 6,001–10,000 bp/);
});


test("synthetic graph exports retain mirrored source provenance and standalone tooltips", async () => {
  const mirrored = { assemblyCtgId: 90, name: "mirror", totalLength: 4000,
    sourceFragment: { sourceSeqId: 7, groupKey: "source:7", sourceStart: 6001, sourceEnd: 10000, sourceLength: 15000 } };
  const store = createStore(createState({ assembly: { supportMirroredCtgs: [mirrored], finalPathViewMode: "table",
    finalPathByChr: { Chr01: { chrName: "Chr01", mode: "segments", segments: [{ type: "ctg", segmentId: "mirror",
      assemblyCtgId: 90, datasetName: "Data", ctgName: "mirror", overallLen: 4000, start: 1, end: 4000 }] } } } }));
  let snapshots = 0;
  await runFinalPathExportAction({ host: { querySelector: () => null }, store, kind: "png", deps: {
    pickSaveFilePath: async () => "mock.png", getExportTimestamp: () => "20261028000000",
    renderFinalPathViewportPng: async snapshot => {
      snapshots++;
      assert.match(snapshot.svgMarkup, /<title>Data_mirror\n/);
      assert.match(snapshot.svgMarkup, /Source contig length: 15,000 bp/);
      assert.match(snapshot.svgMarkup, /Source interval: 6,001–10,000 bp/);
      return "YWJj";
    }, writeFinalPathExportBinaryFile: async () => {},
  } });
  assert.equal(snapshots, 1);
});
