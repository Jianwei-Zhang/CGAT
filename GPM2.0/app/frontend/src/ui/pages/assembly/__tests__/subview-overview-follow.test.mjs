import { test, assert, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { createIdentityRenderState } from "./identity-render-fixture.mjs";
import { readViewNavigationGeometry } from "../view-navigation-state.js";
import { resolveTrackPrefs } from "../track-prefs.js";
import { assemblyPageSession } from "../page-session.js";
import { readFileSync } from "node:fs";

const attr = (markup, key) => markup.match(new RegExp(`${key}="([^"]*)"`))?.[1];
function overview(state) {
  const html = renderAssemblyPage(state);
  const scroll = html.match(/<div\s+class="assembly-track-scroll subview-track-scroll"[\s\S]*?data-track-role="subview"[\s\S]*?>/)?.[0];
  const svg = html.match(/<svg class="assembly-track-svg subview-track-svg"[^>]*>/)?.[0];
  assert.ok(scroll && svg);
  const width = Number(attr(svg, "width"));
  const geometry = readViewNavigationGeometry({ scrollLeft: 0, scrollWidth: Math.max(1200, width),
    dataset: {
      viewNavigationStartBp: attr(scroll, "data-view-navigation-start-bp"),
      viewNavigationEndBp: attr(scroll, "data-view-navigation-end-bp"),
    } }, {
    viewportWidth: 1200,
    windowStartBp: Number(attr(scroll, "data-subview-window-start-bp")),
    viewboxMinX: Number(attr(scroll, "data-subview-viewbox-min-x")),
    innerWidth: Number(attr(scroll, "data-subview-inner-width")),
    domainSpanBp: Number(attr(scroll, "data-subview-domain-span-bp")),
  });
  assert.ok(width <= 1201, `local content fits one viewport, got ${width}`);
  assert.equal(geometry.range.start, geometry.domain.start);
  assert.ok(Math.abs(geometry.range.span - (geometry.domain.end - geometry.domain.start)) < 0.000001,
    "the selected range covers the full domain within floating-point precision");
  return geometry;
}

for (const mode of ["2-contig", "track-pair", "composition"]) {
  for (const direction of [-1, 1]) {
    test(`${mode} full overview follows ${direction < 0 ? "left" : "right"} expansion and return`, () => {
      const state = createIdentityRenderState(mode);
      state.assembly.subviewTrackView = resolveTrackPrefs({ ...state.assembly.subviewTrackView,
        fullRange: true, allowSubViewportScale: true, visibleSpanBp: 16000 });
      const before = overview(state);
      const move = (offsetBp) => {
        if (mode === "composition") {
          state.assembly.subview.summary.members.find((member) => member.assemblyCtgId === 30).xBp = offsetBp;
        } else {
          state.assembly.subviewTrackDragOffsets = [{ slot: "top", contigId: 30, offsetBp }];
        }
      };
      move(direction * 24000);
      const extended = overview(state);
      assert.ok(direction < 0 ? extended.domain.start < before.domain.start
        : extended.domain.end > before.domain.end);
      // Simulate navigation remembering the last fitted span; return must ignore it.
      state.assembly.subviewTrackView.visibleSpanBp = Math.round(extended.range.span);
      move(0);
      const returned = overview(state);
      assert.ok(returned.range.span < extended.range.span);
      assert.ok(Math.abs(returned.domain.start - before.domain.start) < 40);
      assert.ok(Math.abs(returned.domain.end - before.domain.end) < 40);
    });
  }
}

test("composition full overview ignores a stale scale and empty historical viewport", () => {
  const state = createIdentityRenderState("composition");
  state.assembly.subviewTrackView = resolveTrackPrefs({ fullRange: true, visibleSpanBp: 900000 });
  state.assembly.subviewCompositionViewport = { bpPerPx: 750, leftBp: -500000, topPx: 0 };
  const before = structuredClone(state);
  const geometry = overview(state);
  assert.equal(geometry.domain.start, 0);
  assert.ok(geometry.domain.end <= 16040);
  assert.deepEqual(state, before, "rendering does not mutate persisted members or viewport");
});


for (const mode of ["2-contig", "track-pair", "composition"]) {
  test(`${mode} temporary overview drag renders without changing saved positions or history`, () => {
    const state = createIdentityRenderState(mode);
    state.assembly.subviewTrackView = resolveTrackPrefs({ fullRange: true, visibleSpanBp: 16000 });
    const before = overview(state);
    const savedState = structuredClone(state);
    const previousPreview = assemblyPageSession.subviewTrackDragPreview;
    const member = state.assembly.subview.summary.members?.find((entry) => entry.assemblyCtgId === 30);
    try {
      assemblyPageSession.subviewTrackDragPreview = {
        subview: state.assembly.subview, chrName: state.assembly.selectedChrName,
        offset: { slot: "top", contigId: 30, ...(member
          ? { compositionEntityKey: member.entityKey, dragDeltaBp: -24000 } : { offsetBp: -24000 }) },
      };
      const preview = overview(state);
      assert.ok(preview.domain.start < before.domain.start);
      assert.deepEqual(state, savedState);
      assemblyPageSession.subviewTrackDragPreview = null;
      assert.deepEqual(overview(state).domain, before.domain);
    } finally { assemblyPageSession.subviewTrackDragPreview = previousPreview; }
  });
}

test("shared view card contains both plots and hides only the redundant native scrollbar", () => {
  const css = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.assembly-view-card\s*\{[^}]*box-sizing:\s*border-box[^}]*max-width:\s*100%[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.assembly-track-label-column\s*\{[^}]*box-sizing:\s*border-box/s);
  assert.match(css, /\.assembly-track-scroll\s*\{[^}]*scrollbar-width:\s*none[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.assembly-track-scroll::-webkit-scrollbar\s*\{[^}]*display:\s*none/s);
  assert.match(css, /\.view-nav-span\s*\{[^}]*flex:\s*0 0 auto[^}]*margin-inline-start:\s*12px/s);
  assert.match(css, /\.view-nav-span \[data-view-nav-span\]\s*\{[^}]*text-align:\s*start[^}]*font-variant-numeric:\s*tabular-nums/s);
});
