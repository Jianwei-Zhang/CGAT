import { test, assert, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { resolveAlignmentBandStyle } from "../alignment-band-style.js";
import { __testPairRefSubviewSegmentsWithCache } from "../render-subview.js";

const attr = (markup, key) => markup.match(new RegExp(`${key}="([^"]*)"`))?.[1];
const bands = (html, subview = true) => [...html.matchAll(/<polygon class="track-collinearity-band[^>]*>/g)]
  .map(([markup]) => markup).filter((markup) => markup.includes("data-subview-hit-key") === subview);
const identities = (items) => items.map((markup) => attr(markup, "data-band-identity-pct"));
const expectedOrder = ["", "0", "80", "85", "90", "93.27", "95", "100"];

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode}: SVG, Canvas, tooltip and filter share identity without changing anchors`, () => {
    const state = createIdentityRenderState(mode);
    const snapshot = structuredClone(state.assembly.subview);
    const html = renderAssemblyPage(state);
    const polygons = bands(html);
    assert.deepEqual(identities(polygons), expectedOrder);
    polygons.forEach((markup) => {
      const raw = attr(markup, "data-band-identity-pct");
      assert.equal(attr(markup, "fill"), resolveAlignmentBandStyle("companion", raw).fill);
      assert.equal(attr(markup, "pointer-events"), "visibleFill");
    });
    assert.match(html, /Identity: 93.27% \| Alignment length: 1,300 bp/);
    assert.match(html, /Identity: Unknown/);
    assert.match(html, /Identity: 0.00%/);
    assert.match(html, /alignment-identity-legend/);
    if (mode !== "composition") {
      const scenes = [...html.matchAll(/<script type="application\/json" data-track-band-canvas-scene>(.*?)<\/script>/gs)]
        .map((match) => JSON.parse(match[1].replaceAll("&quot;", '"').replaceAll("&amp;", "&")));
      const scene = scenes.find((scene) => scene.kind === (mode === "2-contig" ? "subview-ctg" : "subview-track-pair"));
      assert.deepEqual(scene.bands.map((band) => String(band.identityPct ?? "")), expectedOrder);
    }
    state.assembly.subviewTrackView.minIdentityPct = 90;
    const filtered = renderAssemblyPage(state);
    assert.deepEqual(identities(bands(filtered)), ["90", "93.27", "95", "100"]);
    bands(filtered).forEach((markup) => assert.ok(polygons.includes(markup), "filter must not alter colors, hit keys or anchor flags"));
    assert.deepEqual(state.assembly.subview, snapshot);
    const anchorsBefore = [...html.matchAll(/data-subview-anchor-hit-key="([^"]+)"/g)].map((match) => match[1]);
    [...filtered.matchAll(/data-subview-anchor-hit-key="([^"]+)"/g)].forEach((match) => assert.ok(anchorsBefore.includes(match[1])));
  });
}

test("main view shades and sorts both track palettes and keeps threshold survivors unchanged", () => {
  const state = createIdentityRenderState();
  const html = renderAssemblyPage(state);
  const original = bands(html, false);
  for (const [role, tone] of [["primary", "primary"], ["support", "companion"]]) {
    const items = original.filter((markup) => attr(markup, "data-band-track-role") === role);
    assert.deepEqual(identities(items), expectedOrder);
    items.forEach((markup) => assert.equal(attr(markup, "fill"), resolveAlignmentBandStyle(tone, attr(markup, "data-band-identity-pct")).fill));
  }
  state.assembly.trackView.minIdentityPct = 90;
  bands(renderAssemblyPage(state), false).forEach((markup) => assert.ok(original.includes(markup)));
});

test("segment-pair cache refreshes identity and length even when geometry is unchanged", () => {
  const segment = { hitKey: "same", refStart: 1, refEnd: 100, x: 0, width: 100, identityPct: 90, alignLength: 100 };
  const initial = __testPairRefSubviewSegmentsWithCache({ cacheKey: "identity-refresh", topSegments: [segment], bottomSegments: [segment] });
  const next = { ...segment, identityPct: 95, alignLength: 110 };
  const refreshed = __testPairRefSubviewSegmentsWithCache({ cacheKey: "identity-refresh", topSegments: [next], bottomSegments: [next] });
  assert.notEqual(initial, refreshed);
  assert.equal(refreshed[0].topSegment.identityPct, 95);
  assert.equal(refreshed[0].topSegment.alignLength, 110);
});

for (const mode of ["2-contig", "track-pair"]) {
  test(`${mode}: reference-side projections carry the original alignment identity`, () => {
    const state = createIdentityRenderState(mode);
    state.assembly.refTrackMembers = [{
      assemblyCtgId: 9001, sourceKind: "ref_segment", name: "ref_Chr01:1-16000",
      referenceChrName: "Chr01", segmentStartBp: 1, segmentEndBp: 16000,
      anchorStart: 1, totalLength: 16000, refOrient: "+", hits: [],
    }];
    state.assembly.subview.summary = mode === "2-contig" ? {
      mode, top: { role: "ref", contigId: 9001 }, bottom: { role: "primary", contigId: 2 },
    } : { mode, topTrack: { role: "ref" }, bottomTrack: { role: "primary" } };
    const html = renderAssemblyPage(state);
    assert.deepEqual(identities(bands(html)), expectedOrder);
    assert.match(html, /Identity: 93.27% \| Alignment length: 1,300 bp/);
  });
}

test("legacy reference overlap does not invent direct ctg-to-ctg identity", () => {
  const state = createIdentityRenderState();
  state.assembly.subview.pairwiseEvidence = null;
  const html = renderAssemblyPage(state);
  assert.ok(bands(html).length > 0);
  assert.ok(identities(bands(html)).every((identity) => identity === ""));
  assert.match(html, /Identity: Unknown \(reference overlap; not a direct alignment\)/);
});
