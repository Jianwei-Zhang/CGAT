import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createMainTrackDragPreview } from "../main-track-drag-preview.js";

function fixture({ role = "primary", count = 2, canvasAvailable = true, dark = false } = {}) {
  const all = [], children = [], paints = [];
  let queries = 0, reads = 0, writes = 0, fills = 0, failPaint = false;
  const node = (attrs = {}, classNames = []) => {
    const attributes = new Map(Object.entries(attrs)), classes = new Set(classNames);
    const result = {
      style: {}, isConnected: true,
      classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
      getAttribute(name) { reads++; return attributes.get(name) ?? null; },
      hasAttribute: name => attributes.has(name),
      setAttribute(name, value) { writes++; attributes.set(name, String(value)); },
      removeAttribute: name => attributes.delete(name),
    };
    all.push(result);
    return result;
  };
  const group = node({ "data-track-contig-id": "1", "data-track-role": role });
  const sibling = node({ "data-track-contig-id": "2", "data-track-role": role, transform: "translate(7 0)" });
  const bands = Array.from({ length: count }, (_, index) => node({
    points: "10,20 30,20 80,60 50,60", "data-band-identity-pct": String(80 + index % 21),
  }, index % 2 ? ["is-companion"] : []));
  const active = node({ points: "10,20 50,60", stroke: "red", "data-main-anchor-edge": "left" }, ["subview-anchor-line"]);
  const hidden = node({ points: "10,20 50,60", stroke: "transparent", "data-main-anchor-edge": "right" }, ["subview-anchor-line"]);
  const hitZone = node({ points: "10,20 50,60", "data-main-anchor-edge": "left" }, ["subview-anchor-hit-zone"]);
  const svg = node({ width: "200", height: "80", viewBox: "-100 0 200 80" });
  svg.firstElementChild = group; svg.childElementCount = 5;
  svg.querySelector = () => { queries++; return null; };
  svg.querySelectorAll = selector => { queries++; return selector.startsWith("polygon.") ? bands : []; };
  const context = Object.fromEntries(["setTransform", "clearRect", "closePath", "stroke"].map(name => [name, () => {}]));
  let points = [];
  context.beginPath = () => { points = []; };
  context.moveTo = context.lineTo = (x, y) => points.push([x, y]);
  context.fill = () => {
    if (failPaint) throw Error("paint failed");
    fills++;
    if (count <= 2) paints.push({ points: [...points], fill: context.fillStyle });
  };
  const canvas = { style: {}, setAttribute() {}, getContext: () => canvasAvailable ? context : null,
    remove() { const i = children.indexOf(canvas); if (i >= 0) children.splice(i, 1); } };
  const scroll = node();
  scroll.contains = child => child === svg;
  scroll.ownerDocument = { documentElement: { dataset: { theme: dark ? "dark" : "light" } }, createElement: () => canvas };
  scroll.appendChild = child => children.push(child);
  scroll.querySelector = selector => { queries++; return selector === "svg.assembly-track-svg" ? svg : null; };
  scroll.querySelectorAll = selector => {
    queries++;
    if (selector === `[data-track-contig-id="1"][data-track-role="${role}"]`) return [group];
    if (selector === `[data-track-contig-id="2"][data-track-role="${role}"]`) return [sibling];
    if (selector === `[data-band-track-role="${role}"][data-band-contig-id="2"]`) return [bands[1]];
    if (selector === `[data-band-track-role="${role}"][data-band-contig-id="1"]`) return [bands[0], active, hidden, hitZone];
    const preview = selector.match(/^\[([^=]+)='1'\]$/);
    return preview ? all.filter(item => item.hasAttribute(preview[1])) : [];
  };
  return { scroll, svg, group, sibling, bands, active, hidden, hitZone, children, paints,
    counts: () => ({ queries, reads, writes, fills }), failPaint: () => { failPaint = true; },
    create: (targets = undefined) => createMainTrackDragPreview(scroll, { trackRole: role, assemblyCtgId: 1, targets }) };
}

for (const role of ["primary", "support"]) for (const dark of [false, true]) {
  test(`Main ${role} Canvas keeps every band and active anchor without per-frame DOM queries (${dark ? "dark" : "light"})`, () => {
    const f = fixture({ role, dark }), handle = f.create();
    assert.equal(f.children.length, 0, "do not switch away from SVG before a successful paint");
    const before = f.counts();
    for (const delta of [25, -40, 0]) {
      handle.update(delta);
      const moved = [[10,20],[30,20],[80,60],[50,60]].map(([x,y], index) =>
        [x + 100 + ((role === "support" ? index < 2 : index >= 2) ? delta : 0), y]);
      assert.deepEqual(f.paints.at(-2).points, moved);
      assert.deepEqual(f.paints.at(-1).points, [[110,20],[130,20],[180,60],[150,60]], "stationary bands remain visible");
      assert.equal(f.bands[0].getAttribute("points"), "10,20 30,20 80,60 50,60");
      assert.equal(f.active.getAttribute("points"), `${(10 + delta).toFixed(2)},20.00 50.00,60.00`);
      assert.equal(handle.isCurrent(), true);
    }
    assert.equal(f.counts().queries, before.queries);
    assert.equal(f.hidden.getAttribute("points"), "10,20 50,60");
    assert.equal(f.hitZone.getAttribute("points"), "10,20 50,60");
    assert.equal(f.children.length, 1);
    handle.restore(); handle.restore();
    assert.equal(f.children.length, 0);
    assert.equal(f.scroll.classList.contains("is-track-drag-preview"), false);
    assert.equal(f.scroll.classList.contains("is-subview-band-canvas-drag-preview"), false);
    assert.equal(f.active.getAttribute("points"), "10,20 50,60");
    assert.equal(f.group.getAttribute("transform"), null);
    assert.equal(handle.isCurrent(), false);
  });
}

for (const failure of ["context", "paint"]) test(`Main Canvas ${failure} failure retains complete compiled SVG preview`, () => {
  const f = fixture({ canvasAvailable: failure !== "context" }), handle = f.create();
  if (failure === "paint") { handle.update(10); f.failPaint(); }
  handle.update(25);
  assert.equal(f.children.length, 0);
  assert.equal(f.scroll.classList.contains("is-subview-band-canvas-drag-preview"), false);
  assert.equal(f.bands[0].getAttribute("points"), "10.00,20.00 30.00,20.00 105.00,60.00 75.00,60.00");
  assert.equal(f.bands[1].getAttribute("points"), "10,20 30,20 80,60 50,60");
  handle.restore();
  assert.equal(f.bands[0].getAttribute("points"), "10,20 30,20 80,60 50,60");
});

test("Main preview refuses missing or invalid plots and detects graph replacement", () => {
  assert.equal(createMainTrackDragPreview({ querySelector: () => null }, {}), null);
  const invalid = fixture(); invalid.svg.setAttribute("width", "0");
  assert.equal(invalid.create(), null);
  const f = fixture(), handle = f.create();
  f.svg.firstElementChild = {};
  assert.equal(handle.isCurrent(), false);
  handle.restore();
});

test("chr6-sized Main scene keeps all 6,016 bands without rewriting polygon or inactive-anchor geometry", () => {
  const f = fixture({ count: 6016 }), handle = f.create();
  let forbiddenWrites = 0;
  for (const node of [...f.bands, f.hidden, f.hitZone]) node.setAttribute = () => { forbiddenWrites++; };
  const before = f.counts();
  for (const delta of [20, -30, 0]) handle.update(delta);
  assert.equal(f.counts().fills, 6016 * 3);
  assert.equal(f.counts().queries, before.queries);
  assert.equal(forbiddenWrites, 0);
  handle.restore();
});

test("Canvas success hides Main SVG proxies only after complete paint; active anchors stay visible", () => {
  const css = readFileSync(new URL("../../../../styles/subview.css", import.meta.url), "utf8");
  assert.match(css, /\.is-subview-band-canvas-drag-preview \[data-track-band-svg-overlay="1"\] \.track-collinearity-band\[data-track-band-proxy="1"\]/);
  assert.match(css, /\.is-track-drag-preview \.subview-anchor-line\[stroke="transparent"\]/);
  assert.doesNotMatch(css, /\.is-track-drag-preview \.subview-anchor-line\s*[,\{]/);
});

for (const role of ["primary", "support"]) test(`Main ${role} selected fragments share a delta without merging their placement`, () => {
  const f = fixture({ role }), handle = f.create([1, 2].map(assemblyCtgId => ({ trackRole: role, assemblyCtgId })));
  handle.update(20);
  assert.equal(f.group.getAttribute("transform"), "translate(20.00 0)");
  assert.equal(f.sibling.getAttribute("transform"), "translate(20.00 0) translate(7 0)");
  assert.deepEqual(f.paints.at(-1).points, f.paints.at(-2).points);
  handle.restore();
  assert.equal(f.sibling.getAttribute("transform"), "translate(7 0)");
});
