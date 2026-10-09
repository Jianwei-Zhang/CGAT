import test from "node:test";
import assert from "node:assert/strict";
import { clampViewRange, zoomViewRange, moveViewRange, parseViewSpan, formatViewSpan, readViewNavigationGeometry } from "../view-navigation-state.js";
import { resolveTrackPrefs, resolveTrackInnerWidthFromScale, resolveTickBpFromScale, MAX_TRACK_RENDER_PX } from "../track-prefs.js";
import { renderViewNavigation, renderViewTickControl } from "../view-navigation-ui.js";
import { buildMainTrackViewportKey } from "../scroll-position-state.js";
const domain = { start: -100, end: 900, viewportWidth: 1000 };

test("range clamping respects signed local domains and keeps span at the right edge", () => {
  assert.deepEqual(clampViewRange({ start: 850, span: 200 }, domain), { start: 700, span: 200 });
  assert.deepEqual(clampViewRange({ start: -150, span: 200 }, domain), { start: -100, span: 200 });
  assert.deepEqual(clampViewRange({ start: 10, span: 1500 }, domain), { start: -100, span: 1000 });
  assert.equal(clampViewRange({ start: 0, span: 1 }, { start: 5, end: 5 }), null);
});
test("zoom preserves the cursor genomic point rather than the left edge", () => {
  const current = { start: 100, span: 400 };
  const next = zoomViewRange(current, domain, .5, .25);
  assert.deepEqual(next, { start: 150, span: 200 });
  assert.equal(next.start + next.span * .25, current.start + current.span * .25);
  assert.deepEqual(zoomViewRange(current, domain, .5), { start: 200, span: 200 });
});
test("half-window moves clamp without changing the window span", () => {
  const range = { start: 600, span: 200 };
  assert.deepEqual(moveViewRange(range, domain, range.span / 2), { start: 700, span: 200 });
  assert.deepEqual(moveViewRange({ start: 700, span: 200 }, domain, 100), { start: 700, span: 200 });
  assert.deepEqual(moveViewRange({ start: -50, span: 200 }, domain, -100), { start: -100, span: 200 });
});
test("extreme zoom has a finite render bound", () => {
  const large = { start: 0, end: 1e9, viewportWidth: 1200 };
  const range = zoomViewRange({ start: 0, span: 1e9 }, large, 1e-12);
  assert.ok(range.span >= 1e9 * 1200 / MAX_TRACK_RENDER_PX);
  assert.equal(resolveTrackInnerWidthFromScale({ domainSpanBp: 1e9, visibleSpanBp: 1, baseViewportPx: 1200 }), MAX_TRACK_RENDER_PX);
});
test("span input validates explicit genomic units and meaningful decimals", () => {
  assert.equal(parseViewSpan("2.5", "Mb"), 2_500_000);
  assert.equal(parseViewSpan(".001", "kb"), 1);
  assert.equal(parseViewSpan(" 25 ", "kb"), 25_000);
  for (const invalid of ["", "0", "-1", "Infinity", "NaN", "1e3", "0x10", "abc", "9007199254740992"]) assert.equal(parseViewSpan(invalid, "Mb"), null, invalid);
  assert.equal(parseViewSpan("2", "pixels"), null);
  assert.deepEqual(formatViewSpan(2_500_000), { value: "2.5", unit: "Mb" });
  assert.deepEqual(formatViewSpan(1), { value: "0.001", unit: "kb" });
});
test("viewport geometry includes viewbox origin and native scroll position", () => {
  const geometry = readViewNavigationGeometry({ scrollWidth: 3000, scrollLeft: 400 }, { windowStartBp: 100, viewboxMinX: -100, innerWidth: 2000, domainSpanBp: 4000, viewportWidth: 1000 });
  assert.deepEqual(geometry.domain, { start: -100, end: 5900, viewportWidth: 1000 });
  assert.deepEqual(geometry.range, { start: 700, span: 2000 });
  assert.equal(readViewNavigationGeometry(null, null), null);
});
test("legacy scale migrates once and ticks cannot change the new span", () => {
  const legacy = resolveTrackPrefs({ minTickUnitKb: 500, maxTickCount: 15 });
  assert.equal(legacy.visibleSpanBp, 7_500_000);
  const manual = resolveTrackPrefs({ ...legacy, tickMode: "manual", tickIntervalBp: 250_000, minTickUnitKb: 1 });
  assert.equal(manual.visibleSpanBp, legacy.visibleSpanBp);
  const auto = resolveTrackPrefs({ ...manual, tickMode: "auto" });
  assert.equal(auto.visibleSpanBp, legacy.visibleSpanBp);
  const options = { domainSpanBp: 30_000_000, baseViewportPx: 1000 };
  assert.equal(resolveTrackInnerWidthFromScale({ ...legacy, ...options }), resolveTrackInnerWidthFromScale({ ...manual, ...options }));
  assert.equal(resolveTickBpFromScale({ ...manual, ...options }), 250_000);
  assert.equal(resolveTickBpFromScale({ ...auto, ...options }), 1_000_000);
});
test("short content fits the viewport regardless of requested legacy/new span", () => {
  assert.equal(resolveTrackInnerWidthFromScale({ domainSpanBp: 1200, visibleSpanBp: 1e8, baseViewportPx: 600 }), 600);
});
test("ruler-only preferences do not invalidate main viewport scroll identity", () => {
  const state = { session: { projectId: 1 }, assembly: { selectedChrName: "Chr1", trackView: resolveTrackPrefs({ visibleSpanBp: 1e6 }) } };
  const next = structuredClone(state); next.assembly.trackView.tickIntervalBp = 10; next.assembly.trackView.tickMode = "manual";
  assert.equal(buildMainTrackViewportKey(next), buildMainTrackViewportKey(state));
});
test("localized navigation provides unambiguous modes, half-window controls and units", () => {
  const zh = renderViewNavigation("primary", "zh"), en = renderViewNavigation("subview", "en");
  for (const action of ["mouse", "hand", "left", "right", "minus", "plus", "fit"]) assert.match(zh, new RegExp(`data-view-nav-action="${action}"`));
  assert.match(zh, /左移半屏/); assert.match(en, /Move right half a window/);
  assert.match(en, /data-view-nav-unit/); assert.match(en, /role="slider"/);
  assert.doesNotMatch(zh, /Ctrl|Space|最小刻度|最多可展示数/);
});
test("tick UI is interval-only, automatic by default, manual interval is explicit", () => {
  const auto = renderViewTickControl({}, "zh", "trackView");
  assert.match(auto, /显示设置/); assert.match(auto, /value="auto" selected/);
  assert.match(auto, /data-view-tick-interval[^>]* hidden/);
  const manual = renderViewTickControl({ tickMode: "manual", tickIntervalBp: 250_000 }, "en", "finalPathTrackView", true);
  assert.match(manual, /Tick interval/); assert.match(manual, /value="250"/);
  assert.doesNotMatch(manual, /<details|data-view-navigation|minTickUnitKb|maxTickCount/);
});
