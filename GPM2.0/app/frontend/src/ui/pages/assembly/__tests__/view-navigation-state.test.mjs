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
  assert.equal(readViewNavigationGeometry({ dataset: { viewNavigationContent: "0" }, scrollWidth: 3000, scrollLeft: 400 }, { windowStartBp: 100, viewboxMinX: -100, innerWidth: 2000, domainSpanBp: 4000, viewportWidth: 1000 }), null);
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
test("localized navigation groups movement and places Full range after its axis and shows only a read-only window", () => {
  const zh = renderViewNavigation("primary", "zh"), en = renderViewNavigation("subview", "en");
  for (const action of ["toggle-mode", "left", "right", "fit"]) assert.match(zh, new RegExp(`data-view-nav-action="${action}"`));
  assert.match(zh, /左移半屏/); assert.match(en, /Move right half a window/);
  assert.ok(zh.indexOf('data-view-nav-action="left"') < zh.indexOf("data-view-nav-axis"));
  assert.ok(zh.indexOf('data-view-nav-action="right"') < zh.indexOf("data-view-nav-axis"));
  assert.ok(zh.indexOf("data-view-nav-axis") < zh.indexOf('data-view-nav-action="fit"'));
  assert.ok(zh.indexOf('data-view-nav-action="fit"') < zh.indexOf('data-view-nav-span'));
  assert.equal([...zh.matchAll(/role="switch"/g)].length, 1);
  assert.match(zh, /role="switch" aria-checked="false"/);
  assert.doesNotMatch(zh, /data-view-nav-action="(?:mouse|hand)"|aria-pressed/);
  assert.match(zh, /窗口/); assert.match(zh, />全览<\/button>/); assert.match(en, /Full range/);
  assert.match(en, /data-view-nav-grip aria-hidden="true" hidden/);
  assert.match(en, /<span data-view-nav-span/); assert.match(en, /role="slider"/);
  assert.doesNotMatch(zh, /<input|<select|data-view-nav-unit|data-view-nav-action="(?:minus|plus)"|跨度|适应全部/);
  assert.doesNotMatch(zh, /Ctrl|Space|最小刻度|最多可展示数/);
});
test("tick UI is directly inline with Auto as the default option and custom kb values", () => {
  const auto = renderViewTickControl({}, "zh", "trackView");
  assert.match(auto, /data-view-tick-interval[^>]*value="Auto"/);
  assert.deepEqual([...auto.matchAll(/data-view-tick-option="([^"]+)"/g)].map(match => match[1]), ["Auto", "250", "500", "750", "1000", "10000", "100000"]);
  assert.match(auto, /aria-controls="view-tick-options-trackView"/);
  assert.match(auto, /刻度间隔 \(kb\)/);
  assert.doesNotMatch(auto, /<details|<select|显示设置|data-view-tick-mode/);
  const manual = renderViewTickControl({ tickMode: "manual", tickIntervalBp: 250_000 }, "en", "finalPathTrackView", true);
  assert.match(manual, /Tick interval/); assert.match(manual, /data-view-tick-interval[^>]*value="250"/);
  assert.doesNotMatch(manual, /<details|data-view-navigation|minTickUnitKb|maxTickCount/);
});
