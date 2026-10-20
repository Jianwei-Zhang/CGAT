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
