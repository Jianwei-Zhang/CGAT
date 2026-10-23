import test from "node:test";
import assert from "node:assert/strict";
import { normalizeFinalPathByChr } from "../final-path-state.js";
import { renderManualSplitMarkers } from "../source-fragment-layout.js";
test("split source provenance survives Final Path normalization and a second persistence cycle", () => {
  const paths = { A: { mode: "segments", chrName: "A", segments: [{ type: "ctg", segmentId: "split", assemblyCtgId: null,
    splitFromAssemblyCtgId: 6, splitFragmentCtgId: 73, datasetName: "ds", ctgName: "tig", originId: "tig",
    overallLen: 1000, start: 1000, end: 501, source: { dataset: "ds", contig: "tig", start: 501, end: 1000, orientation: "-" } }] } };
  const normalized = normalizeFinalPathByChr(paths);
  assert.equal(normalized.A.segments[0].splitFragmentCtgId,73);
  assert.equal(normalized.A.segments[0].splitFromAssemblyCtgId,6);
  assert.equal(normalized.A.segments[0].assemblyCtgId,null);
  assert.deepEqual(normalizeFinalPathByChr(normalized),normalized);
});
test("manual split is a visible boundary with no synthetic N gap, including reversed moved fragments", () => {
  const ctg={orient:"-",sourceFragment:{groupKey:"manual-fragment:6",sourceStart:501,sourceEnd:1000,sourceLength:1000}};
  const html=renderManualSplitMarkers(ctg,{x:10,width:100},20,14,(v)=>v);
  assert.match(html,/data-manual-split-after="500"/);
  assert.match(html,/no inserted bases/);
  assert.doesNotMatch(html,/Gap:|bp N/);
  assert.equal(renderManualSplitMarkers({...ctg,sourceFragment:{...ctg.sourceFragment,groupKey:"n-fragment:6"}},{x:10,width:100},20,14,(v)=>v),"");
});


test("splitting the right side of an N-delimited contig does not mark its natural left endpoint", () => {
  const ctg = { orient: "+", sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:6",
    sourceStart: 59056812, sourceEnd: 70000000, sourceLength: 83707350, gapBeforeBp: 100, gapAfterBp: 0 } };
  const html = renderManualSplitMarkers(ctg, { x: 10, width: 100 }, 20, 14, (v) => v);
  assert.doesNotMatch(html, /data-manual-split-after="59056811"/);
  assert.match(html, /data-manual-split-after="70000000"/);
  const flipped = renderManualSplitMarkers({ ...ctg, orient: "-" }, { x: 10, width: 100 }, 20, 14, (v) => v);
  assert.doesNotMatch(flipped, /data-manual-split-after="59056811"/);
  assert.match(flipped, /d="M 8 17 /, "the real high-source cut follows the flipped left side");
});

test("natural high-source N boundary is not a cut, and deleting a sibling does not hide the surviving real cut", () => {
  const ctg = { orient: "+", sourceFragment: { sourceSeqId: 7, groupKey: "manual-fragment:6",
    sourceStart: 5001, sourceEnd: 9000, sourceLength: 20000, gapBeforeBp: 0, gapAfterBp: 100 } };
  const html = renderManualSplitMarkers(ctg, { x: 1000, width: 100 }, 20, 14, (v) => v);
  assert.match(html, /data-manual-split-after="5000"/);
  assert.doesNotMatch(html, /data-manual-split-after="9000"/);
});
