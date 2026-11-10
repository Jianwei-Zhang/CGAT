import test from "node:test";
import assert from "node:assert/strict";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { buildSubviewCompositionCandidates } from "../subview-composition-candidates.js";
import { buildPhasedSubviewCtgPool } from "../subview-state.js";
import { readDenseAnchorScene } from "../subview-dense-hit-runtime.js";
import { sliceLocalMember } from "../subview-fragment-model.js";
import { __testPairRefSubviewSegmentsWithCache } from "../render-subview.js";
import { resolveSubviewSegmentPairReversed } from "../subview-band-orientation.js";
import { applySubviewComposition } from "../subview-composition-state.js";

const attrs = text => Object.fromEntries([...text.matchAll(/([\w-]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
function tags(html, tag) {
  return [...html.matchAll(new RegExp(`<${tag}\\b([^>]+)>`, "g"))].map(m => attrs(m[1]));
}
function localBands(html) {
  return tags(html, "polygon").filter(p => p["data-subview-hit-key"]);
}
const points = band => band.points.split(" ").map(p => p.split(",").map(Number));
const crossed = band => { const p = points(band); return (p[1][0] - p[0][0]) * (p[3][0] - p[2][0]) > 0; };

function referenceState(mode, { role = "primary", swapped = false, orient = "+", strand = "+",
  sourceFlip = false, refFlip = false, refOrient = "+" } = {}) {
  const state = createIdentityRenderState(mode);
  const source = role === "primary" ? state.assembly.chrCtgs[0] : state.assembly.supportChrCtgs[0];
  Object.assign(source, { orient, refOrient: orient, hits: [{
    strand, ctgStart: orient === "-" ? 6001 : 2001, ctgEnd: orient === "-" ? 14000 : 10000,
    refStart: 4001, refEnd: 12000, blockLength: 8000, identityPct: 99,
  }] });
  const ref = { assemblyCtgId: 9001, sourceKind: "ref_segment", referenceChrId: 1,
    referenceChrName: "Chr01", segmentOrder: 1, segmentStartBp: 1, segmentEndBp: 32000,
    totalLength: 32000, refOrient, name: "ref_Chr01:1-32000", hits: [] };
  state.assembly.refTrackMembers = [ref];
  const sourceSlot = swapped ? "top" : "bottom", refSlot = swapped ? "bottom" : "top";
  const selection = { role, contigId: source.assemblyCtgId, ...(role === "support" ? { datasetId: 22, source: "mother" } : {}) };
  const refSelection = { role: "ref", contigId: 9001 };
  state.assembly.subview = { summary: mode === "track-pair"
    ? { mode, [`${sourceSlot}Track`]: selection, [`${refSlot}Track`]: refSelection }
    : { mode: "2-contig", [sourceSlot]: selection, [refSlot]: refSelection },
    flippedCtgs: [...(sourceFlip ? [{ slot: sourceSlot, contigId: source.assemblyCtgId }] : []),
      ...(refFlip ? [{ slot: refSlot, contigId: 9001 }] : [])], activeAnchors: [] };
  if (mode === "composition") {
    const candidates = buildSubviewCompositionCandidates({ allChrCtgs: [source], refCtgs: [ref], primaryDatasetId: 11 });
    state.assembly.subview = applySubviewComposition({}, { members: candidates.map(c => ({ ...c,
      lane: c.source.role === "ref" ? refSlot : sourceSlot, xBp: 0,
      flipped: c.source.role === "ref" ? refFlip : sourceFlip })) });
    state.assembly.subviewCompositionCandidates = candidates;
    state.assembly.subviewCompositionCandidatesLoaded = true;
  }
  return state;
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  for (const role of ["primary", "support"]) for (const swapped of [false, true]) {
    test(`${mode} ${role} Ref projection swapped=${swapped}: raw strand, Main orientation and both local flips`, () => {
      for (const orient of ["+", "-"]) for (const strand of ["+", "-"])
        for (const sourceFlip of [false, true]) for (const refFlip of [false, true]) {
          const args = { role, swapped, orient, strand, sourceFlip, refFlip };
          const html = renderAssemblyPage(referenceState(mode, args));
          const bands = localBands(html);
          assert.equal(bands.length, 1, JSON.stringify(args));
          const reversed = ((orient !== strand) !== sourceFlip) !== refFlip;
          assert.equal(crossed(bands[0]), reversed, JSON.stringify(args));
          const edges = tags(html, "line").filter(e => e["data-subview-anchor-edge"]);
          assert.equal(edges.length, 2);
          const p = points(bands[0]);
          for (const [index, edge] of ["left", "right"].entries()) {
            const anchor = edges.find(e => e["data-subview-anchor-edge"] === edge);
            assert.equal(Number(anchor.x1), p[index][0]);
            assert.equal(Number(anchor.x2), p[index === 0 ? 3 : 2][0]);
          }
          // Legacy cuts are display-local bp; composition descriptors intentionally
          // retain base-member bp and apply the local flip only for drawing.
          const left = edges.find(e => e["data-subview-anchor-edge"] === "left");
          const right = edges.find(e => e["data-subview-anchor-edge"] === "right");
          const topFlipped = mode === "composition" && (swapped ? sourceFlip : refFlip);
          const bottomFlipped = mode === "composition" && (swapped ? refFlip : sourceFlip);
          assert.equal(Number(left["data-subview-anchor-top-cut-bp"]) > Number(right["data-subview-anchor-top-cut-bp"]), Boolean(topFlipped));
          assert.equal(Number(left["data-subview-anchor-bottom-cut-bp"]) > Number(right["data-subview-anchor-bottom-cut-bp"]), reversed !== Boolean(bottomFlipped));
        }
    });
  }
  test(`${mode}: reversed reference base orientation mirrors its interval and cancels a reversed source endpoint`, () => {
    const html = renderAssemblyPage(referenceState(mode, { orient: "-", strand: "+", refOrient: "-" }));
    assert.equal(crossed(localBands(html)[0]), false);
    const edges = tags(html, "line").filter(e => e["data-subview-anchor-edge"]);
    assert.equal(Number(edges.find(e => e["data-subview-anchor-edge"] === "left")["data-subview-anchor-top-cut-bp"]), 20001);
    assert.equal(Number(edges.find(e => e["data-subview-anchor-edge"] === "right")["data-subview-anchor-top-cut-bp"]), 28000);
  });
  test(`${mode}: actual pairwise orientation is pair-level, not XORed twice`, () => {
    for (const strand of ["+", "-"]) for (const topFlip of [false, true]) for (const bottomFlip of [false, true]) {
      const state = createIdentityRenderState(mode);
      state.assembly.subview.pairwiseEvidence.hits.forEach(hit => { hit.strand = strand; });
      if (mode === "composition") state.assembly.subview.summary.members.forEach(member => { member.flipped = member.lane === "top" ? topFlip : bottomFlip; });
      else state.assembly.subview.flippedCtgs = [...(topFlip ? [{ slot: "top", contigId: 30 }] : []), ...(bottomFlip ? [{ slot: "bottom", contigId: 2 }] : [])];
      const bands = localBands(renderAssemblyPage(state));
      assert.equal(bands.length, 8);
      assert.ok(bands.every(b => crossed(b) === (((strand === "-") !== topFlip) !== bottomFlip)));
    }
  });
}

test("track-pair visual separation preserves full CTG widths at the reference scale", () => {
  const state = referenceState("track-pair");
  const first = state.assembly.chrCtgs[0];
  state.assembly.chrCtgs.push({ ...first, assemblyCtgId: 3, name: "second", totalLength: 32000, hits: [] });
  for (const fullRange of [false, true]) {
    state.assembly.subviewTrackView.fullRange = fullRange;
    const html = renderAssemblyPage(state);
    const bars = tags(html, "g").filter(g => g["data-subview-track-pair-contig-id"]);
    const width = id => Number(bars.find(g => g["data-subview-track-pair-contig-id"] === String(id))["data-subview-rect-width"]);
    assert.ok(Math.abs(width(2) * 2 - width(9001)) < 0.03, "short bar must not be shrunk to make space");
    assert.ok(Math.abs(width(3) - width(9001)) < 0.03);
  }
});

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode}: phased Ref projection composes backing, phased and local orientations exactly once`, () => {
    for (const orient of ["+", "-"]) for (const phaseOrient of ["+", "-"])
      for (const strand of ["+", "-"]) for (const sourceFlip of [false, true]) {
        const state = referenceState(mode, { orient, strand, sourceFlip });
        const phasedChrTracks = [{ phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A",
          items: [{ itemId: 701, assemblyCtgId: 2, orient: phaseOrient }] }];
        state.assembly.phasedChrTracks = phasedChrTracks;
        if (mode === "composition") {
          const candidates = buildSubviewCompositionCandidates({ primaryDatasetId: 11,
            refCtgs: state.assembly.refTrackMembers,
            phasedCtgs: buildPhasedSubviewCtgPool({ primaryCtgs: state.assembly.chrCtgs, phasedChrTracks }) });
          state.assembly.subview = applySubviewComposition({}, { members: candidates.map(c => ({ ...c,
            lane: c.source.role === "ref" ? "top" : "bottom", flipped: c.source.role !== "ref" && sourceFlip })) });
          state.assembly.subviewCompositionCandidates = candidates;
        } else {
          state.assembly.subview.summary[mode === "track-pair" ? "bottomTrack" : "bottom"] = {
            role: "phased", contigId: 2, phasedTrackId: 101, phasedTrackItemId: 701, haplotypeKey: "A" };
        }
        const bands = localBands(renderAssemblyPage(state));
        assert.equal(bands.length, 1);
        assert.equal(crossed(bands[0]), (phaseOrient !== strand) !== sourceFlip, JSON.stringify({ orient, phaseOrient, strand, sourceFlip }));
      }
  });
  test(`${mode}: mirrored support tracks preserve their reference-hit orientation`, () => {
    for (const sourceFlip of [false, true]) {
      const state = referenceState(mode, { role: "support", orient: "-", strand: "+", sourceFlip });
      const mirrored = { ...state.assembly.supportChrCtgs[0], chrName: "Chr01" };
      state.assembly.supportMirroredCtgs = [mirrored];
      if (mode === "composition") {
        const candidates = buildSubviewCompositionCandidates({ primaryDatasetId: 11,
          refCtgs: state.assembly.refTrackMembers, supportMirroredCtgs: [mirrored] });
        state.assembly.subview = applySubviewComposition({}, { members: candidates.map(c => ({ ...c,
          lane: c.source.role === "ref" ? "top" : "bottom", flipped: c.source.role !== "ref" && sourceFlip })) });
        state.assembly.subviewCompositionCandidates = candidates;
      } else Object.assign(state.assembly.subview.summary[mode === "track-pair" ? "bottomTrack" : "bottom"], { source: "mirror", isMirror: true });
      const bands = localBands(renderAssemblyPage(state));
      assert.equal(bands.length, 1);
      assert.equal(crossed(bands[0]), !sourceFlip);
    }
  });
}

test("composition clipping a reverse-oriented CTG preserves the corresponding reference interval", () => {
  for (const sourceFlip of [false, true]) {
    const state = referenceState("composition", { orient: "-", strand: "+", sourceFlip });
    const members = state.assembly.subview.summary.members;
    const index = members.findIndex(m => m.source.role !== "ref");
    members[index] = sliceLocalMember(members[index], 3001, 7000);
    assert.equal(members[index].lengthBp, 4000);
    const html = renderAssemblyPage(state);
    const bands = localBands(html);
    assert.equal(bands.length, 1);
    assert.equal(crossed(bands[0]), !sourceFlip);
    const anchors = tags(html, "line").filter(e => e["data-subview-anchor-edge"]);
    assert.deepEqual(anchors.map(e => Number(e["data-subview-anchor-top-cut-bp"])).sort((a, b) => a - b), [5001, 9000]);
    assert.deepEqual(anchors.map(e => Number(e["data-subview-anchor-bottom-cut-bp"])).sort((a, b) => a - b), [1, 4000]);
  }
});

test("reference-overlap cache includes endpoint direction even when symmetric geometry is unchanged", () => {
  const segment = { ctgId: 2, hitKey: "symmetric", refStart: 100, refEnd: 200, refMid: 150,
    ctgStart: 100, ctgEnd: 200, x: 10, width: 100, referenceReversed: false };
  for (const trackMode of ["track-pair", "2-contig"]) {
    for (const topReversed of [false, true]) for (const bottomReversed of [false, true]) {
      const pairs = __testPairRefSubviewSegmentsWithCache({ cacheKey: "orientation-regression", trackMode,
        topSegments: [{ ...segment, referenceReversed: topReversed }],
        bottomSegments: [{ ...segment, referenceReversed: bottomReversed }] });
      assert.equal(pairs.length, 1);
      assert.equal(resolveSubviewSegmentPairReversed(pairs[0].topSegment, pairs[0].bottomSegment), topReversed !== bottomReversed);
    }
  }
});

for (const mode of ["2-contig", "track-pair"]) {
  test(`${mode}: dense Canvas bands and compact anchors retain inverted reference geometry`, () => {
    const state = referenceState(mode, { orient: "-", strand: "+" });
    const ctg = state.assembly.chrCtgs[0];
    ctg.hits = Array.from({ length: 1001 }, () => ({ ...ctg.hits[0] }));
    const html = renderAssemblyPage(state);
    const kind = mode === "track-pair" ? "subview-track-pair" : "subview-ctg";
    const scene = JSON.parse(html.match(new RegExp(`data-track-band-canvas-scene-kind="${kind}"[\\s\\S]*?<script type="application/json" data-track-band-canvas-scene>(.*?)</script>`))[1]);
    const node = { textContent: html.match(/data-subview-dense-anchor-scene="1">(.*?)<\/script>/)[1] };
    const anchors = readDenseAnchorScene({ querySelector: () => node });
    assert.equal(scene.bands.length, 1001);
    assert.equal(anchors.length, 2002);
    for (const band of scene.bands) {
      const p = band.points;
      assert.ok((p[1][0] - p[0][0]) * (p[3][0] - p[2][0]) > 0);
    }
    const left = anchors.find(a => a.edge === "left"), right = anchors.find(a => a.edge === "right");
    assert.equal(left.topCutBp, 4001);
    assert.equal(left.bottomCutBp, 14000);
    assert.equal(right.topCutBp, 12000);
    assert.equal(right.bottomCutBp, 6001);
  });
}
