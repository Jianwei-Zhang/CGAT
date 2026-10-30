import test from "node:test";
import assert from "node:assert/strict";
import { createState, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { normalizeCtgs } from "../track-layout.js";
import { renderSourceGapConnections, sourceGapBetween } from "../source-fragment-layout.js";

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

function gapLines(html) {
  return [...html.matchAll(/<line class="track-source-gap"[^>]*>/g)].map(([markup]) => ({
    edge: markup.match(/data-source-gap-edge="([^"]+)"/)[1],
    bp: Number(markup.match(/data-source-gap-bp="([^"]+)"/)[1]),
    x1: Number(markup.match(/x1="([^"]+)"/)[1]),
    x2: Number(markup.match(/x2="([^"]+)"/)[1]),
    y1: Number(markup.match(/y1="([^"]+)"/)[1]),
    y2: Number(markup.match(/y2="([^"]+)"/)[1]),
  }));
}

function assertGapEdges(html, left, right) {
  const lines = gapLines(html);
  assert.deepEqual(lines.map(line => line.edge), ["top", "bottom"]);
  for (const line of lines) {
    const expectedY = left.y + (line.edge === "bottom" ? left.height : 0);
    assert.equal(line.bp, 1);
    assert.ok(Math.abs(line.x1 - left.x - left.width) < 0.02);
    assert.ok(Math.abs(line.x2 - right.x) < 0.02);
    assert.ok(Math.abs(line.y1 - expectedY) < 0.02);
    assert.equal(line.y1, line.y2);
    assert.notEqual(line.y1, left.y + left.height / 2);
  }
}

for (const height of [14, 28]) {
  for (const orient of ["+", "-"]) {
    test(`source-gap edges align to both fragment boundaries at height ${height}, orientation ${orient}`, () => {
      const ctgs = orient === "+" ? parts : parts.toReversed().map(ctg => ({ ...ctg, orient }));
      const entries = ctgs.map((ctg, index) => ({ ctg, rect: { x: 10 + index * 60, width: 40 }, y: 25, height }));
      const html = renderSourceGapConnections(entries, text => text);
      assertGapEdges(html, { ...entries[0].rect, y: 25, height }, entries[1].rect);
      assert.equal((html.match(/<desc data-app-tooltip-source>Gap: 1 bp N<\/desc>/g) || []).length, 2);
      assert.equal((html.match(/stroke-dasharray="2 2"/g) || []).length, 2);
    });
  }
}

test("source-gap connections do not join unrelated, reordered, flipped, overlapping, or different-lane fragments", () => {
  const left = { ctg: parts[0], rect: { x: 10, width: 40 }, y: 25, height: 14 };
  const right = { ctg: parts[1], rect: { x: 70, width: 40 }, y: 25, height: 14 };
  for (const invalidRight of [
    { ...right, ctg: { ...parts[1], sourceFragment: null } },
    { ...right, ctg: { ...parts[1], sourceFragment: { ...parts[1].sourceFragment, sourceSeqId: 2 } } },
    { ...right, ctg: { ...parts[1], sourceFragment: { ...parts[1].sourceFragment, groupKey: "another-group" } } },
    { ...right, ctg: parts[0] },
    { ...right, ctg: { ...parts[1], orient: "-" } },
    { ...right, rect: { x: 50, width: 40 } },
    { ...right, rect: { x: 45, width: 40 } },
    { ...right, y: 60 },
    { ...right, height: 28 },
  ]) {
    assert.equal(renderSourceGapConnections([left, invalidRight], text => text), "");
  }
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
    assert.match(match[0], /data-source-fragment-seq-id="1"/);
    assert.match(match[0], /data-source-fragment-group="n-fragment:chr:Chr01"/);
    assert.match(match[0], /data-source-gap-drag-key="main:/);
    const height = html.match(new RegExp(`data-track-contig-id="${c.assemblyCtgId}"[^>]*data-track-role="primary"[^>]*data-track-rect-height="([^"]+)"`));
    assert.ok(height);
    const box = { x: +match[1], y: +match[2], width: +match[3], height: +height[1] };
    const band = html.match(new RegExp(`<polygon class="track-collinearity-band[^>]*data-band-track-role="primary"[^>]*data-band-contig-id="${c.assemblyCtgId}"[^>]*points="([^"]+)"`));
    assert.ok(band);
    const xs = band[1].split(/\s+/).slice(2).map(p => +p.split(",")[0]).sort((a,b) => a-b);
    assert.ok(Math.abs(xs[0]-box.x)<0.02);
    assert.ok(Math.abs(xs[1]-box.x-box.width)<0.02);
    return box;
  });
  assert.ok(boxes[1].x-boxes[0].x-boxes[0].width>=19.98);
  assertGapEdges(html, boxes[0], boxes[1]);
  assert.doesNotMatch(html, /data-n-region-marker="1"/);
});

test("track-pair local view aligns source-gap edges with the split contig rectangles", () => {
  const state = createIdentityRenderState("track-pair");
  state.assembly.chrCtgs = parts;
  state.assembly.subview.pairwiseEvidence = { status: "loaded", hits: [] };
  const html = renderAssemblyPage(state);
  const svg = html.match(/<svg class="assembly-track-svg subview-track-svg"[^>]*>([\s\S]*?)<\/svg>/)?.[1];
  assert.ok(svg, "track-pair local-view SVG must be rendered");
  const boxes = parts.map(ctg => {
    const group = svg.match(new RegExp(`<g\\s+class="track-ctg-group[^>]*data-subview-track-pair-contig-id="${ctg.assemblyCtgId}"[^>]*>`))?.[0];
    assert.ok(group, `local-view rectangle for fragment ${ctg.assemblyCtgId}`);
    assert.match(group, /data-source-fragment-seq-id="1"/);
    assert.match(group, /data-source-fragment-group="n-fragment:chr:Chr01"/);
    assert.match(group, /data-source-gap-drag-key="subview:/);
    const attr = name => Number(group.match(new RegExp(`data-subview-rect-${name}="([^"]+)"`))[1]);
    return { x: attr("x"), y: attr("y"), width: attr("width"), height: attr("height") };
  });
  assertGapEdges(svg, boxes[0], boxes[1]);
});

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode}: clipped endpoint-only evidence is visibly identified as approximate`, () => {
    const state = createIdentityRenderState(mode);
    state.assembly.subview.pairwiseEvidence.hits[0].projectionApproximate = true;
    assert.match(renderAssemblyPage(state), /Approximate projection/);
  });
}
