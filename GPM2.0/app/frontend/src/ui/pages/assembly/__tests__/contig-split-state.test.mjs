import test from "node:test";
import assert from "node:assert/strict";
import { parseSplitCuts, splitCutFraction, splitCutFromFraction, splitBoundaryCuts, defaultSplitAssignments, splitCopy } from "../contig-split-state.js";
import { renderSplitEvidence } from "../contig-split-runtime.js";
import { resolveAssemblyCtgContextTarget } from "../context-menu.js";

const source = { sourceStart: 101, sourceEnd: 1100, orient: "-", assignedChrName: "ChrA" };
test("split cuts use original inclusive coordinates and reject empty, duplicate, terminal or unsafe cuts", () => {
  assert.deepEqual(parseSplitCuts("900, 500", source), [500, 900]);
  for (const text of ["", "100", "1100", "500,500", "5e2", "500.5", "9007199254740993"]) assert.throws(() => parseSplitCuts(text, source));
});
test("reverse display correctly maps source boundary and clamps both pointer edges", () => {
  assert.equal(splitCutFraction(source, 600), .5);
  assert.equal(splitCutFromFraction(source, .1), 1000);
  assert.equal(splitCutFromFraction(source, 1), 101);
  assert.equal(splitCutFromFraction(source, 0), 1099);
  assert.equal(splitCutFromFraction({ ...source, orient: "+" }, .1), 200);
});
test("alignment shortcuts use query endpoints, never reference endpoints", () => {
  assert.deepEqual(splitBoundaryCuts({ queryStart: 301, queryEnd: 700, refStart: 1, refEnd: 90000 }, source), [300, 700]);
  assert.deepEqual(splitBoundaryCuts({ queryStart: 101, queryEnd: 1100 }, source), []);
});
test("fragment assignments recommend only adequate evidence and retain explicit user choices", () => {
  const preview = { source, parts: [{ sourceStart: 101, sourceEnd: 600, candidates: [{ chrName: "ChrB", highQualityCoveragePercent: 99 }] }, { sourceStart: 601, sourceEnd: 1100, candidates: [{ chrName: "ChrA", highQualityCoveragePercent: 20 }] }] };
  assert.deepEqual(defaultSplitAssignments(preview), ["ChrB", null]);
  assert.deepEqual(defaultSplitAssignments(preview, new Map([["101:600", null]])), [null, null]);
});
test("evidence canvas escapes names and exposes exact accessible alignment boundary buttons", () => {
  const html = renderSplitEvidence({ source, hits: [{ chrName: '<chr"unsafe>', queryStart: 301, queryEnd: 700, refStart: 1, refEnd: 400, mapq: 60 }] }, [500], splitCopy.en);
  assert.match(html, /data-split-cut="300"/);
  assert.match(html, /data-split-cut="700"/);
  assert.match(html, /role="button" tabindex="0"/);
  assert.doesNotMatch(html, /<chr"unsafe>/);
  assert.match(html, /&lt;chr&quot;unsafe&gt;/);
});
test("main alignment band context carries original query boundary data", () => {
  const values = { "data-band-contig-id": "6", "data-band-query-start": "50032560", "data-band-query-end": "76328915" };
  const node = { getAttribute: (name) => values[name] };
  const target = { closest: (selector) => selector.includes("data-band-contig-id") ? node : null };
  assert.deepEqual(resolveAssemblyCtgContextTarget(target), { assemblyCtgId: 6, trackRole: "primary", isMirror: false, datasetId: null, splitQueryStart: 50032560, splitQueryEnd: 76328915 });
});

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

test("ambiguous high-quality candidates stay unplaced rather than selecting by name", () => {
  const preview={source,parts:[{sourceStart:101,sourceEnd:1100,candidates:[{chrName:"A",highQualityCoveragePercent:99},{chrName:"B",highQualityCoveragePercent:98}]}]};
  assert.deepEqual(defaultSplitAssignments(preview),[null]);
});
