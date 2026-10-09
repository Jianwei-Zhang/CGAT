import { test, assert, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { readViewNavigationGeometry, resolveFullRangeVisibleSpan } from "../view-navigation-state.js";
import { resolveTrackPrefs } from "../track-prefs.js";

const attr = (markup, key) => markup.match(new RegExp(`${key}="([^"]*)"`))?.[1];
function overview(state) {
  const html = renderAssemblyPage(state);
  const scroll = html.match(/<div\s+class="assembly-track-scroll"[\s\S]*?data-track-role="primary"[\s\S]*?>/)?.[0];
  const svg = html.match(/<svg class="assembly-track-svg"[^>]*>/)?.[0];
  assert.ok(scroll && svg);
  const width = Number(attr(svg, "width"));
  const metrics = {
    viewportWidth: 1200,
    windowStartBp: Number(attr(scroll, "data-track-window-start-bp")),
    viewboxMinX: Number(attr(scroll, "data-track-viewbox-min-x")),
    innerWidth: Number(attr(scroll, "data-track-inner-width")),
    domainSpanBp: Number(attr(scroll, "data-track-domain-span-bp")),
  };
  const geometry = readViewNavigationGeometry({
    scrollLeft: 0, scrollWidth: Math.max(1200, width),
    dataset: {
      viewNavigationStartBp: attr(scroll, "data-view-navigation-start-bp"),
      viewNavigationEndBp: attr(scroll, "data-view-navigation-end-bp"),
    },
  }, metrics);
  assert.ok(width <= 1201, "current content is refitted into one viewport");
  assert.equal(geometry.range.start, geometry.domain.start);
  assert.equal(geometry.range.span, geometry.domain.end - geometry.domain.start,
    "overview selection remains 100 percent, not the old window fraction");
  return geometry;
}

for (const direction of [-1, 1]) {
  test(`full range expands and contracts after a ${direction < 0 ? "left" : "right"} boundary drag`, () => {
    const state = createIdentityRenderState();
    state.assembly.chromosomes[0].chrLength = 16000;
    state.assembly.trackView = resolveTrackPrefs({ ...state.assembly.trackView,
      fullRange: true, allowSubViewportScale: true, visibleSpanBp: 16000 });
    const baseline = overview(state);
    state.assembly.trackDragOffsets = [{ trackRole: "support", datasetId: 22,
      assemblyCtgId: 30, offsetBp: direction * 24000 }];
    const expanded = overview(state);
    assert.ok(expanded.range.span > baseline.range.span);
    if (direction < 0) assert.ok(expanded.domain.start < baseline.domain.start);
    else assert.ok(expanded.domain.end > baseline.domain.end);
    // Leave the old expanded span in preferences to reproduce the stale-blank bug.
    state.assembly.trackView.visibleSpanBp = Math.round(expanded.range.span);
    state.assembly.trackDragOffsets = [];
    const restored = overview(state);
    assert.ok(Math.abs(restored.domain.start - baseline.domain.start) <= restored.bpPerPx);
    assert.ok(Math.abs(restored.domain.end - baseline.domain.end) <= restored.bpPerPx);
    assert.ok(restored.range.span < expanded.range.span,
      "previous viewport padding is not retained as current content");
    assert.equal(state.assembly.trackView.fullRange, true);
  });
}

test("returning one outlier does not trim the reference or the opposite outlier", () => {
  const state = createIdentityRenderState();
  state.assembly.chromosomes[0].chrLength = 16000;
  state.assembly.trackView = resolveTrackPrefs({ ...state.assembly.trackView,
    fullRange: true, allowSubViewportScale: true });
  state.assembly.trackDragOffsets = [
    { trackRole: "support", datasetId: 22, assemblyCtgId: 30, offsetBp: -24000 },
    { trackRole: "primary", assemblyCtgId: 2, offsetBp: 24000 },
  ];
  const both = overview(state);
  state.assembly.trackView.visibleSpanBp = Math.round(both.range.span);
  state.assembly.trackDragOffsets.shift();
  const rightOnly = overview(state);
  assert.ok(rightOnly.domain.start >= 0);
  assert.ok(rightOnly.domain.end >= 40000);
  assert.ok(rightOnly.range.span < both.range.span);
});

test("refitting uses current content for both growth and shrinkage", () => {
  assert.equal(resolveFullRangeVisibleSpan({ contentWidth: 1800, innerWidth: 1200,
    domainSpanBp: 16000, viewportWidth: 1200 }), 24000);
  assert.equal(resolveFullRangeVisibleSpan({ contentWidth: 600, innerWidth: 600,
    domainSpanBp: 16000, viewportWidth: 1200 }), 16000);
  assert.equal(resolveFullRangeVisibleSpan({ contentWidth: 1200, innerWidth: 1200,
    domainSpanBp: 16000, viewportWidth: 1200 }), null);
});

test("actual content bounds override empty scroll padding on either side", () => {
  for (const [start, end, minX] of [[0, 16000, 0], [-8000, 16000, -400]]) {
    const geometry = readViewNavigationGeometry({ scrollWidth: 1200, scrollLeft: 0,
      dataset: { viewNavigationStartBp: String(start), viewNavigationEndBp: String(end) } },
    { windowStartBp: 0, viewboxMinX: minX, innerWidth: 800,
      domainSpanBp: 16000, viewportWidth: 1200 });
    assert.deepEqual(geometry.domain, { start, end, viewportWidth: 1200 });
    assert.equal(geometry.range.span, end - start);
  }
});


test("a contig originally outside the reference does not keep its old empty envelope", () => {
  const state = createIdentityRenderState();
  state.assembly.chromosomes[0].chrLength = 16000;
  state.assembly.trackView = resolveTrackPrefs({ ...state.assembly.trackView,
    fullRange: true, allowSubViewportScale: true });
  // Source layout is cumulative sequence length, not anchorStart. A 40 kb
  // contig genuinely extends beyond the 16 kb reference before being moved.
  state.assembly.chrCtgs[0].totalLength = 40000;
  state.assembly.chrCtgs[0].lengthBp = 40000;
  const original = overview(state);
  state.assembly.trackView.visibleSpanBp = Math.round(original.range.span);
  state.assembly.trackDragOffsets = [{ trackRole: "primary", assemblyCtgId: 2, offsetBp: -24000 }];
  const returned = overview(state);
  assert.ok(returned.domain.end < original.domain.end,
    "original source layout coordinates are not treated as an occupied right boundary");
  assert.ok(returned.domain.end <= 16000 + returned.bpPerPx);
});
