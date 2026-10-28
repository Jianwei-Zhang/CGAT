import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { renderAssemblyPage, createState, readStylesheetTree } from "./tabs-semantics-harness.mjs";
import { resolveAnchoredPanelRect, placeAnchoredPanel, clearAnchoredPanelPlacement } from "../anchored-panel-placement.js";
import { bindMainTrackToolbarPopups } from "../main-track-toolbar-runtime.js";

// Parse the isolated header, not a mock of its intended hierarchy.
function parseHeader(html) {
  const start = html.lastIndexOf("<div", html.indexOf("data-main-view-header"));
  const text = html.slice(start, html.indexOf('<div class="assembly-track-layout"', start));
  const root = { children: [] }, stack = [root];
  for (const tag of text.matchAll(/<\/?([\w-]+)\b([^>]*?)>/g)) {
    if (tag[0].startsWith("</")) { stack.pop(); continue; }
    const attrs = Object.fromEntries([...tag[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(m => [m[1], m[2] ?? ""]));
    const node = { name: tag[1], attrs, children: [] }; stack.at(-1).children.push(node);
    if (!["input", "br", "hr", "img", "path", "line", "rect", "circle"].includes(node.name) && !tag[0].endsWith("/>")) stack.push(node);
  }
  return root.children[0];
}

for (const locale of ["zh", "en"]) test(`precomputed and phase actions lead peer groups after the title (${locale})`, () => {
  const entry = { chrName: "Chr01", mode: "segments", segments: [], grtDisplayAvailable: true };
  const html = renderAssemblyPage({ ...createState({ initializer: {
    datasets: [{ datasetId: 11, name: "primary" }, { datasetId: 22, name: "A very long auxiliary dataset name" }],
    existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22], phasedAssemblyEnabled: true }],
  }, assembly: { supportDatasetId: 22, finalPathByChr: { Chr01: entry },
    grtProjectView: { recipe: { finalPathSchemaVersion: "2" }, baselineFinalPathByChr: { Chr01: entry } } } }), locale });
  const header = parseHeader(html);
  assert.equal(header.children[0].name, "strong");
  const toolbar = header.children[1];
  assert.equal(header.children.length, 2);
  assert.ok(Object.hasOwn(toolbar.attrs, "data-main-track-toolbar"));
  assert.deepEqual(toolbar.children.map(node => node.attrs["data-grt-result-controls"] ? "precomputed"
    : node.attrs["data-create-phased-track"] ? "phase" : node.attrs.class), [
    "precomputed", "phase", "assembly-marker-display", "assembly-track-inline-field", "assembly-track-inline-field",
    "assembly-track-inline-field", "assembly-track-inline-field", "main-view-history-controls",
  ]);
  assert.doesNotMatch(html, /data-main-track-control-layout|data-main-track-quick-actions|assembly-track-panel-quick-actions/);
});

test("CSS right-aligns whole parameter groups with safe extreme-width scrolling, without a resize classifier", () => {
  const css = readStylesheetTree(new URL("../../../../styles/assembly.css", import.meta.url));
  assert.match(css, /\.assembly-track-panel-head\[data-main-view-header\]\s*\{[^}]*flex-wrap: wrap;[^}]*align-items: center;[^}]*justify-content: flex-start;/);
  assert.match(css, /\.assembly-track-inline-controls\[data-main-track-toolbar\]\s*\{[^}]*justify-content: flex-end;[^}]*justify-content: safe flex-end;[^}]*flex-wrap: wrap;[^}]*overflow-x: auto;/);
  assert.match(css, /\.assembly-track-inline-controls\[data-main-track-toolbar\]\s*\{[^}]*flex: 1 1 max-content;[^}]*width: max-content;/);
  assert.match(css, /\[data-main-track-toolbar\] > \*\s*\{[^}]*flex: 0 0 auto;[^}]*white-space: nowrap;/);
  assert.doesNotMatch(css, /data-main-track-control-layout|assembly-track-panel-quick-actions/);
  assert.equal(existsSync(new URL("../main-track-control-layout-runtime.js", import.meta.url)), false);
  const runtime = readFileSync(new URL("../main-track-toolbar-runtime.js", import.meta.url), "utf8");
  assert.doesNotMatch(runtime, /ResizeObserver|getComputedStyle|setState|appendChild|replaceWith/);
});

test("popup rectangles clamp to narrow viewports and open above a low toolbar", () => {
  for (const viewportWidth of [120, 320, 500, 1000]) {
    const rect = resolveAnchoredPanelRect({ anchor: { left: viewportWidth - 80, right: viewportWidth - 10, top: 400, bottom: 430 },
      width: 240, height: 200, viewportWidth, viewportHeight: 480 });
    assert.ok(rect.left >= 0 && rect.left + rect.width <= viewportWidth);
    assert.equal(rect.upward, true);
    assert.equal(rect.top, 196);
    assert.ok(rect.top + Math.min(200, rect.maxHeight) <= 480);
  }
  assert.equal(resolveAnchoredPanelRect({ anchor: { top: 500, bottom: 520, left: 30, right: 60 },
    width: 100, height: 100, viewportWidth: 300, viewportHeight: 480 }), null);
});

function popupFixture() {
  const events = new Map(), windows = new Map(), win = { innerWidth: 800, innerHeight: 500,
    addEventListener: (type, fn) => windows.set(type, fn) };
  let left = 100, reads = 0, open = false;
  const anchor = { ownerDocument: { defaultView: win }, getBoundingClientRect() {
    reads++; return { left, right: left + 86, width: 86, top: 40, bottom: 70 }; },
    querySelector: () => panel };
  const panel = { style: {}, scrollHeight: 200, getBoundingClientRect: () => ({ width: 240, height: 200 }) };
  const host = { closest() { return this; }, querySelector: () => ({}),
    querySelectorAll(selector) { return selector.includes(".is-open") && open ? [anchor] : []; },
    ownerDocument: { defaultView: win }, addEventListener: (type, fn) => events.set(type, fn) };
  return { host, panel, anchor, win, events, windows, setLeft: value => { left = value; },
    setOpen: value => { open = value; }, reads: () => reads };
}

test("popup tracking is bounded and resizing closed controls never measures/reorders the toolbar", () => {
  const f = popupFixture(); bindMainTrackToolbarPopups(f.host); bindMainTrackToolbarPopups(f.host);
  assert.equal(f.events.size, 2); assert.equal(f.windows.size, 2);
  for (let i = 0; i < 30; i++) f.windows.get("resize")();
  assert.equal(f.reads(), 0);
  f.setOpen(true); f.windows.get("resize")();
  assert.equal(f.panel.style.position, "fixed"); assert.equal(f.panel.style.left, "100px");
  f.setLeft(20); f.events.get("scroll")();
  assert.equal(f.panel.style.left, "20px");
});

test("fixed popup sizing recovers after shrinking and clearing only removes placement styles", () => {
  const f = popupFixture(); f.panel.style.color = "red";
  placeAnchoredPanel(f.anchor, f.panel);
  f.win.innerWidth = 160; f.setLeft(20); placeAnchoredPanel(f.anchor, f.panel);
  assert.equal(f.panel.style.width, "144px");
  f.win.innerWidth = 800; placeAnchoredPanel(f.anchor, f.panel);
  assert.equal(f.panel.style.width, "240px");
  clearAnchoredPanelPlacement(f.panel);
  assert.equal(f.panel.style.position, ""); assert.equal(f.panel.style.width, "");
  assert.equal(f.panel.style.color, "red");
});

test("upward popovers measure the reflowed narrow grid before choosing their top", () => {
  const win = { innerWidth: 320, innerHeight: 480 };
  const anchor = { ownerDocument: { defaultView: win }, getBoundingClientRect: () => ({ left: 10, right: 180, top: 400, bottom: 430 }) };
  const panel = { style: {}, getBoundingClientRect() { return { width: this.style.width ? Number.parseFloat(this.style.width) : 720, height: this.style.width ? 360 : 140 }; },
    get scrollHeight() { return this.style.width ? 360 : 140; } };
  const result = placeAnchoredPanel(anchor, panel, { preferredWidth: 720, matchAnchorWidth: false });
  assert.equal(result.upward, true); assert.equal(result.width, 304);
  assert.equal(result.top, 36); assert.equal(result.top + 360, 396);
});
