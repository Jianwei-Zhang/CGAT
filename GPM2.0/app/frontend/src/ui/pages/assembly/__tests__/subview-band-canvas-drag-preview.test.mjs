import test from "node:test";
import assert from "node:assert/strict";
import { createSubviewBandCanvasDragPreview, compileBandDragBitmapRuns } from "../band-canvas-runtime.js";
import { resolveAlignmentBandStyle, resolveDarkAlignmentBandStyle } from "../alignment-band-style.js";

function fixture({ count = 1, dark = false, contextAvailable = true, clip = false } = {}) {
  const calls = [], paints = [], classes = new Set(), children = [];
  let reads = 0, writes = 0;
  const context = Object.fromEntries(["setTransform", "clearRect", "beginPath", "closePath", "moveTo", "lineTo", "stroke", "save", "restore", "rect", "clip"]
    .map((name) => [name, (...args) => calls.push([name, ...args])]));
  context.fill = () => paints.push({ fill: context.fillStyle, points: calls.slice(calls.findLastIndex((call) => call[0] === "beginPath") + 1)
    .filter((call) => call[0] === "moveTo" || call[0] === "lineTo").map((call) => call.slice(1)) });
  const bands = Array.from({ length: count }, (_, index) => {
    const attrs = { points: "10,20 30,20 80,60 50,60", "data-band-identity-pct": String(80 + index % 21) };
    return { attrs, classList: { contains: (name) => name === "is-companion" && index % 2 === 1 },
      getAttribute(name) { reads++; return attrs[name] ?? null; },
      setAttribute() { writes++; } };
  });
  const actions = bands.map((node) => ({ kind: "band", node, edgeIndexes: [0, 1], basePoints: [[10,20],[30,20],[80,60],[50,60]] }));
  const clipNode = { getAttribute: (name) => ({ y: "21", height: "38" })[name] ?? null };
  const svg = { querySelectorAll: () => bands, querySelector: () => clip ? clipNode : null };
  const canvas = { style: {}, setAttribute() {}, getContext: () => contextAvailable ? context : null,
    remove: () => { const index = children.indexOf(canvas); if (index >= 0) children.splice(index, 1); } };
  const scroll = { ownerDocument: { documentElement: { dataset: { theme: dark ? "dark" : "light" } }, createElement: () => canvas },
    querySelector: () => svg, appendChild: (child) => children.push(child),
    classList: { add: (name) => classes.add(name), remove: (name) => classes.delete(name) } };
  return { scroll, canvas, bands, actions, calls, paints, classes, children, counts: () => ({ reads, writes }),
    create: (options = {}) => createSubviewBandCanvasDragPreview(scroll, actions, { width: 100, height: 80, ...options }) };
}

for (const edgeIndexes of [[0,1], [2,3], [0,1,2,3], []]) {
  test(`Canvas follows exactly the moving endpoints ${edgeIndexes} through outward and inward refits`, () => {
    const f = fixture(); f.actions[0].edgeIndexes = edgeIndexes;
    const before = structuredClone(f.bands[0].attrs), handle = f.create(), counts = f.counts();
    assert.equal(f.children.length, 0, "do not hide original paint before a successful frame");
    for (const delta of [150, -200, 0]) {
      handle.draw(delta, [-50, 0, 200, 80]);
      const expected = f.actions[0].basePoints.map(([x,y], index) => [(x + (edgeIndexes.includes(index) ? delta : 0) + 50) / 2, y]);
      assert.deepEqual(f.paints.at(-1).points, expected);
    }
    assert.deepEqual(f.counts(), counts, "pointer frames must not read or write proxy attributes");
    assert.deepEqual(f.bands[0].attrs, before);
    assert.equal(f.classes.has("is-subview-band-canvas-drag-preview"), true);
    assert.equal(f.children.length, 1);
    handle.restore(); handle.restore();
    assert.equal(f.classes.size, 0); assert.equal(f.children.length, 0);
    assert.equal(handle.draw(1, [0,0,100,80]), false);
  });
}

for (const dark of [false, true]) test(`Canvas retains absolute identity, unknown values, companion tone and stable paint order (${dark ? "dark" : "light"})`, () => {
  const f = fixture({ count: 4, dark });
  [100, 85, "", 85].forEach((identity, index) => { f.bands[index].attrs["data-band-identity-pct"] = String(identity); });
  f.actions[2].edgeIndexes = [];
  const handle = f.create(); handle.draw(20, [0,0,100,80]);
  const style = dark ? resolveDarkAlignmentBandStyle : resolveAlignmentBandStyle;
  assert.deepEqual(f.paints.map((paint) => paint.fill), [style("primary", null).fill, style("companion", 85).fill,
    style("companion", 85).fill, style("primary", 100).fill]);
  assert.equal(f.paints[0].points[0][0], 10, "unmoved bands remain in the same frame");
  handle.restore();
});

test("stationary bands without a drag action and clipped reversed bands are not omitted", () => {
  const f = fixture({ count: 2, clip: true }); f.actions.pop();
  const handle = f.create(); handle.draw(-20, [-100,0,200,80]);
  assert.equal(f.paints.length, 2);
  assert.deepEqual(f.calls.find((call) => call[0] === "rect"), ["rect", 0, 21, 100, 38]);
  assert.deepEqual(f.paints[0].points, [[45,20],[55,20],[90,60],[75,60]]);
  assert.deepEqual(f.paints[1].points, [[55,20],[65,20],[90,60],[75,60]]);
  handle.restore();
});

test("Canvas unavailability, allocation limits and malformed geometry leave the original SVG fallback untouched", () => {
  for (const scenario of ["unavailable", "throws", "oversize", "malformed"]) {
    const f = fixture({ contextAvailable: scenario !== "unavailable" });
    if (scenario === "throws") f.canvas.getContext = () => { throw new Error("Canvas context unavailable"); };
    if (scenario === "malformed") f.actions[0].basePoints = [[NaN, 1]];
    assert.equal(f.create(scenario === "oversize" ? { width: 40000 } : {}), null);
    assert.equal(f.children.length, 0); assert.equal(f.classes.size, 0); assert.equal(f.counts().writes, 0);
  }
});

test("11,004 visible records remain complete without any per-frame SVG band mutation", () => {
  const f = fixture({ count: 11004 }), handle = f.create(), counts = f.counts();
  for (const delta of [100, -100, 0]) handle.draw(delta, [-100,0,300,80]);
  assert.equal(f.paints.length, 11004 * 3);
  assert.deepEqual(f.counts(), counts);
  handle.restore();
});


test("a failed first paint leaves the original surface visible and the gesture can still restore", () => {
  const f = fixture(), handle = f.create();
  f.scroll.appendChild = () => { throw new Error("detached graph"); };
  assert.throws(() => handle.draw(10, [0,0,100,80]), /detached graph/);
  assert.equal(f.classes.size, 0); assert.equal(f.children.length, 0);
  handle.restore();
});


function bitmapFixture(options = {}) {
  const f = fixture(options), canvases = [];
  f.scroll.ownerDocument.createElement = (tag) => {
    const children = [], attrs = new Map();
    const node = { style: {}, className: "", children, setAttribute: (name, value) => attrs.set(name, value),
      getAttribute: (name) => attrs.get(name), appendChild: (child) => children.push(child),
      remove() { const index = f.children.indexOf(node); if (index >= 0) f.children.splice(index, 1); } };
    if (tag === "canvas") {
      const context = f.canvas.getContext();
      if (context) context.translate = (...args) => f.calls.push(["translate", ...args]);
      node.getContext = () => context;
      canvases.push(node);
    }
    return node;
  };
  return { ...f, canvases };
}

for (const edges of [[0,1], [2,3], [0,1,2,3], []]) test(`bitmap affine preview preserves every endpoint for motion ${edges}`, () => {
  const f = bitmapFixture({ clip: true }); f.actions[0].edgeIndexes = edges;
  const handle = f.create(), paints = f.paints.length, counts = f.counts();
  assert.equal(paints, 1, "rasterize complete evidence once before the gesture");
  const canvas = f.canvases[0];
  for (const delta of [150, -200, 0, 600]) {
    handle.draw(delta, [-50,10,200,160]);
    const matrix = canvas.style.transform.slice(7,-1).split(",").map(Number);
    // Cached bitmap uses a two-pixel gutter around x=10..80, y=20..60.
    f.actions[0].basePoints.forEach(([x,y], index) => {
      const localX = x-8, localY = y-18;
      const actual = [matrix[0]*localX + matrix[2]*localY + matrix[4], matrix[3]*localY + matrix[5]];
      const expected = [(x+(edges.includes(index)?delta:0)+50)/2, (y-10)/2];
      actual.forEach((value, axis) => assert.ok(Math.abs(value-expected[axis]) < 1e-9));
    });
    assert.equal(f.children[0].style.clipPath, "inset(5.5px 0 55.5px 0)");
  }
  assert.equal(f.paints.length, paints, "no per-frame rasterization");
  assert.deepEqual(f.counts(), counts, "no per-frame SVG reads/writes");
  assert.equal(f.children[0].getAttribute("data-subview-band-drag-mode"), "bitmap-transform");
  assert.equal(canvas.style.transformOrigin, "0 0");
  handle.restore(); handle.restore();
  assert.equal(f.children.length, 0); assert.equal(f.classes.size, 0);
  assert.equal(handle.draw(1, [0,0,100,80]), false);
});

test("interleaved stationary/moving bitmap runs preserve identity paint order, not motion-group order", () => {
  const f = bitmapFixture({ count: 4 });
  f.actions[1].edgeIndexes = []; f.actions[3].edgeIndexes = [];
  const handle = f.create(); handle.draw(10, [0,0,100,80]);
  assert.equal(f.children[0].children.length, 4);
  assert.deepEqual(f.paints.map(p => p.fill), [0,1,2,3].map(i => resolveAlignmentBandStyle(i%2 ? "companion" : "primary",80+i).fill));
  handle.restore();
});

test("unsafe affine geometry and excessive interleaving use complete redraw without dropping records", () => {
  const f = bitmapFixture({ count: 18 });
  f.actions.forEach((action,index) => { if(index%2) action.edgeIndexes=[]; });
  const handle = f.create(); handle.draw(10, [0,0,100,80]);
  assert.equal(f.children[0].getAttribute("data-subview-band-drag-mode"), "redraw");
  assert.equal(f.paints.length, 18); handle.restore();
  for (const band of [
    { points:[[0,0],[1,1],[2,10],[3,10]],moving:[1,1,0,0] },
    { points:[[0,0],[1,0],[2,0],[3,0]],moving:[1,1,0,0] },
    { points:[[0,0],[1,0],[2,10],[3,10]],moving:[1,0,0,0] },
  ]) assert.equal(compileBandDragBitmapRuns([band]), null);
});

test("oversized cached bitmaps fall back to bounded viewport redraw", () => {
  const f = bitmapFixture(); f.actions[0].basePoints[2][0]=40000;
  const handle = f.create(); handle.draw(10,[0,0,100,80]);
  assert.equal(f.children[0].getAttribute("data-subview-band-drag-mode"), "redraw");
  assert.equal(f.paints.length, 1); handle.restore();
});

test("11,004 real-size records rasterize once, then 60 pointer frames only transform the cached layer", () => {
  const f = bitmapFixture({ count: 11004 }), handle = f.create(), counts = f.counts();
  assert.equal(f.paints.length,11004);
  for(let frame=0;frame<60;frame++) handle.draw(frame-30,[-100,0,300,80]);
  assert.equal(f.paints.length,11004); assert.deepEqual(f.counts(),counts);
  assert.equal(f.children[0].children.length,1);
  handle.restore();
});


test("crossed reverse-strand bands obey the same affine endpoint mapping without changing their order", () => {
  const f = bitmapFixture();
  f.actions[0].basePoints = [[10,20],[30,20],[50,60],[80,60]];
  f.actions[0].edgeIndexes = [2,3];
  const handle = f.create(); handle.draw(-90,[-100,0,400,80]);
  const matrix = f.canvases[0].style.transform.slice(7,-1).split(",").map(Number);
  for (const [index,[x,y]] of f.actions[0].basePoints.entries()) {
    const actual = matrix[0]*(x-8)+matrix[2]*(y-18)+matrix[4];
    const expected = (x+(index>=2?-90:0)+100)/4;
    assert.ok(Math.abs(actual-expected)<1e-9);
  }
  assert.equal(f.paints.length,1); handle.restore();
});
