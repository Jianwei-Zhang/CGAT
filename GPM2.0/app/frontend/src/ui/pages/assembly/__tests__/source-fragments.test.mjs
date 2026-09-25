import test from "node:test";
import assert from "node:assert/strict";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { normalizeCtgs } from "../track-layout.js";
import { sourceGapBetween } from "../source-fragment-layout.js";

import { createIdentityRenderState } from "./identity-render-fixture.mjs";

const parts = [
  { assemblyCtgId: 1, name: "scaffold[2-10001]", totalLength: 10000, orient: "+", anchorStart: 2,
    sourceFragment: { sourceSeqId: 1, groupKey: "n-fragment:chr:Chr01", sourceStart: 2, sourceEnd: 10001,
      sourceLength: 20005, gapBeforeBp: 1, gapAfterBp: 1 },
    hits: [{ ctgStart: 1, ctgEnd: 10000, refStart: 2, refEnd: 10001, blockLength: 10000, strand: "+" }] },
  { assemblyCtgId: 2, name: "scaffold[10003-20002]", totalLength: 10000, orient: "+", anchorStart: 10003,
    sourceFragment: { sourceSeqId: 1, groupKey: "n-fragment:chr:Chr01", sourceStart: 10003, sourceEnd: 20002,
      sourceLength: 20005, gapBeforeBp: 1, gapAfterBp: 3 },
    hits: [{ ctgStart: 1, ctgEnd: 10000, refStart: 10003, refEnd: 20002, blockLength: 10000, strand: "+" }] },
];

test("source fragments retain original gap coordinates in either orientation", () => {
  assert.deepEqual(normalizeCtgs(parts).map(c => [c.startBp, c.endBp]), [[1, 10000], [10002, 20001]]);
  const reverse = parts.toReversed().map(c => ({ ...c, orient: "-" }));
  assert.deepEqual(normalizeCtgs(reverse, { preserveInputOrder: true }).map(c => [c.startBp, c.endBp]), [[3, 10002], [10004, 20003]]);
  assert.equal(sourceGapBetween(reverse[0], reverse[1]), 1);
  assert.equal(sourceGapBetween(parts[1], parts[0]), null, "reordering must not invent an original connection");
  assert.equal(sourceGapBetween(parts[0], { ...parts[1], orient: "-" }), null);
});

test("main-view bands attach to the split contigs and leave the displayed one-N gap clear", () => {
  const html = renderAssemblyPage(createState({ assembly: {
    selectedChrName: "Chr01", chromosomes: [{ chrName: "Chr01", chrLength: 20005 }],
    selectedCtgId: 1, chrCtgs: parts, supportChrCtgs: [],
    refTrackMembers: [{ segmentStartBp: 1, segmentEndBp: 20005 }],
    trackView: { alignmentLength: 1, supportDsCtgLen: 0 },
  } }));
  const boxes = parts.map(c => {
    const match = html.match(new RegExp(`<g class="track-ctg-group[^>]*data-track-contig-id="${c.assemblyCtgId}"[^>]*data-track-role="primary"[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`));
    assert.ok(match);
    const box = { x: +match[1], width: +match[3] };
    const band = html.match(new RegExp(`<polygon class="track-collinearity-band[^>]*data-band-track-role="primary"[^>]*data-band-contig-id="${c.assemblyCtgId}"[^>]*points="([^"]+)"`));
    assert.ok(band);
    const xs = band[1].split(/\s+/).slice(2).map(p => +p.split(",")[0]).sort((a,b) => a-b);
    assert.ok(Math.abs(xs[0]-box.x)<0.02);
    assert.ok(Math.abs(xs[1]-box.x-box.width)<0.02);
    return box;
  });
  assert.ok(boxes[1].x-boxes[0].x-boxes[0].width>=19.98);
  assert.match(html, /data-source-gap-bp="1"/);
  assert.doesNotMatch(html, /data-n-region-marker="1"/);
});

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode}: clipped endpoint-only evidence is visibly identified as approximate`, () => {
    const state = createIdentityRenderState(mode);
    state.assembly.subview.pairwiseEvidence.hits[0].projectionApproximate = true;
    assert.match(renderAssemblyPage(state), /Approximate projection/);
  });
}
