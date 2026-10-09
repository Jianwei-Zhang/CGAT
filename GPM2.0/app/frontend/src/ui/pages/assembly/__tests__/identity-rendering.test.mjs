import { readFileSync } from "node:fs";
import { getAppSettings, setAppSettings } from "../../../../services/app-settings.js";
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
    const legends = [...html.matchAll(/<div class="alignment-identity-legend"[^>]*>[\s\S]*?<\/div>/g)];
    assert.equal(legends.length, 2, "one legend in the main chart and one in Subview");
    legends.forEach(([legend]) => assert.doesNotMatch(legend, /未知|Unknown|unknown/));
    assert.equal(
      [...html.matchAll(/<div class="assembly-track-layout(?: subview-track-layout)?">\s*<div class="alignment-identity-legend"[^>]*>/g)].length,
      2,
      "legends belong inside the chart layouts, not in standalone card rows",
    );
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

for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode}: legends stay above the axis while the first-track gap is halved`, () => {
    const settings = getAppSettings();
    try {
      for (const [fontSize, graphFontSize] of [[12, 10], [14, 12], [18, 16], [18, 10]]) {
        setAppSettings({ ...settings, fontSize, graphFontSize }, { persist: false });
        const html = renderAssemblyPage(createIdentityRenderState(mode));
        const scale = Math.max(1, graphFontSize / 12);
        const layouts = [...html.matchAll(/<div class="assembly-track-layout(?: subview-track-layout)?">([\s\S]*?)<\/svg>/g)];
        assert.equal(layouts.length, 2);
        const axes = layouts.map(([layout]) => layout.match(/<line class="track-ruler-line"[^>]*>/));
        const legends = layouts.map(([layout]) => layout.match(/<div class="alignment-identity-legend"[^>]*>/));
        assert.equal(axes.length, 2);
        assert.equal(legends.length, 2);
        axes.forEach(([axis], index) => {
          const rulerTop = Number(attr(axis, "y1"));
          assert.equal(rulerTop, 48 * scale, "keep the ruler below the original legend position");
          assert.equal(attr(axis, "y2"), String(rulerTop));
          assert.equal(attr(legends[index][0], "style"), undefined,
            "CSS keeps the legend in its original upper-right position");
          const bars = [...layouts[index][0].matchAll(/<rect\s+class="track-ctg(?:\s[^"]*)?"[^>]*>/g)];
          assert.ok(bars.length > 0);
          const firstTrackTop = Math.min(...bars.map(([bar]) => Number(attr(bar, "y"))));
          const expectedGap = mode === "composition" && index === 1 ? 17 : 30;
          assert.ok(Math.abs(firstTrackTop - rulerTop - expectedGap * scale) < 0.01,
            "first-track gap is half of the previous 34/60 scaled pixels");
        });
        if (mode === "composition") {
          assert.match(html, new RegExp(`class="assembly-track-svg subview-track-svg"[^>]*height="${231 * scale}"`),
            "composition retains lane separation with the halved top gap");
        }
      }
    } finally {
      setAppSettings(settings, { persist: false });
    }
  });
}

test("identity legend remains a non-interactive overlay pinned to the right", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  const legendRule = css.match(/\.alignment-identity-legend\s*\{([^}]*)\}/)?.[1];
  assert.ok(legendRule);
  assert.match(legendRule, /position:\s*absolute/);
  assert.match(legendRule, /right:\s*12px/);
  assert.match(legendRule, /pointer-events:\s*none/);
  assert.match(legendRule, /top:\s*8px/, "preserve the original legend position above the axis");
});
