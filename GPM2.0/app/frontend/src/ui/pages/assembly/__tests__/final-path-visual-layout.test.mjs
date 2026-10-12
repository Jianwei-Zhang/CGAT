import test from "node:test";
import assert from "node:assert/strict";
import { layoutFinalPathStrip, syncFinalPathStripGeometry } from "../final-path-visual-layout.js";

const ctg = length => ({ segment: { type: "ctg" }, length });
const gap = length => ({ segment: { type: "gap" }, length });

test("short contigs and gaps share Assembly's 8px floor without overlap", () => {
  const layouts = layoutFinalPathStrip([ctg(1000000), gap(1), ctg(1), ctg(1000000)], 800, 2000002);
  assert.equal(layouts.length, 4);
  assert.ok(layouts[1].width >= 8);
  assert.ok(layouts[2].width >= 8);
  layouts.forEach((item, index) => {
    assert.ok(item.width > 0);
    if (index) assert.ok(Math.abs(item.x - layouts[index - 1].x - layouts[index - 1].width) < 1e-8);
  });
  assert.ok(Math.abs(layouts.at(-1).x + layouts.at(-1).width - 800) < 1e-8);
});

test("a short chromosome remains proportional unless its visibility floor is needed", () => {
  assert.equal(layoutFinalPathStrip([ctg(100)], 800, 200)[0].width, 400);
  assert.equal(layoutFinalPathStrip([ctg(1)], 800, 1000000)[0].width, 8);
  const dense = layoutFinalPathStrip(Array.from({ length: 20 }, () => ctg(1)), 100, 20);
  assert.ok(dense.every(item => item.width >= 5 - 1e-8));
  assert.ok(Math.abs(dense.at(-1).x + dense.at(-1).width - 100) < 1e-8);
});

test("adopted source overlays use the same measured layout as the matching Final Path", () => {
  const patch = { style: {} }, label = { style: {} };
  const source = { dataset: { finalPathSourcePath: "Chr1", finalPathSourceIndex: "1",
    finalPathSourceOffset: "0", finalPathUsedStart: "10", finalPathUsedEnd: "11",
    finalPathSourceLength: "100" }, style: {},
    querySelector: selector => selector === ".project-preview-used" ? patch : label };
  const nodes = [1000000, 1].map(length => ({ dataset: { finalPathKind: "ctg", finalPathLength: String(length) }, style: {} }));
  const strip = { dataset: { finalPathStrip: "1", finalPathName: "Chr1", finalPathDomain: "1000001" }, clientWidth: 800,
    querySelectorAll: selector => selector === "[data-final-path-segment]" ? nodes : [],
    closest: () => ({ querySelectorAll: () => [source] }) };
  syncFinalPathStripGeometry({ querySelectorAll: () => [strip] });
  assert.equal(nodes[1].style.width, "8px");
  const absolutePatchX = parseFloat(source.style.left) + 1 + parseFloat(patch.style.left);
  assert.ok(Math.abs(absolutePatchX - parseFloat(nodes[1].style.left)) <= 1);
  assert.equal(label.style.left, patch.style.left);
  assert.equal(label.style.width, patch.style.width);
});


test("preview path labels hide completely when too narrow and reappear after resize", () => {
  const nodes = [ctg(100), gap(1), ctg(1000)].map((item, index) => {
    const node = { dataset: { finalPathKind: item.segment.type, finalPathLength: String(item.length) }, style: {} };
    const label = { style: {}, scrollWidth: [70, 27, 40][index],
      get clientWidth() { return Math.max(0, Math.floor(parseFloat(node.style.width) - 2)); } };
    node.querySelector = selector => selector === "[data-final-path-fit-label]" ? label : null;
    node.label = label;
    return node;
  });
  const strip = { dataset: { finalPathStrip: "1", finalPathDomain: "1101" }, clientWidth: 80,
    querySelectorAll: selector => selector === "[data-final-path-segment]" ? nodes : [] };
  const host = { querySelectorAll: () => [strip] };
  syncFinalPathStripGeometry(host);
  assert.equal(nodes[0].label.style.visibility, "hidden");
  assert.equal(nodes[1].label.style.visibility, "hidden");
  assert.equal(nodes[2].label.style.visibility, "");
  strip.clientWidth = 1000;
  syncFinalPathStripGeometry(host);
  assert.equal(nodes[0].label.style.visibility, "");
  assert.equal(nodes[1].label.style.visibility, "hidden");
});


test("source contig labels fit the adopted interval, not the full source strip", () => {
  const patch = { style: {} };
  const label = { dataset: { previewSourceFitLabel: "1" }, style: {}, scrollWidth: 90,
    get clientWidth() { return Math.max(0, Math.floor(parseFloat(this.style.width))); } };
  const source = { dataset: { finalPathSourcePath: "Chr1", finalPathSourceIndex: "0",
    finalPathSourceOffset: "0", finalPathUsedStart: "10", finalPathUsedEnd: "60",
    finalPathSourceLength: "1000" }, style: {},
    querySelector: selector => selector === ".project-preview-used" ? patch : label };
  const node = { dataset: { finalPathKind: "ctg", finalPathLength: "1000" }, style: {} };
  const strip = { dataset: { finalPathStrip: "1", finalPathName: "Chr1", finalPathDomain: "1000" }, clientWidth: 800,
    querySelectorAll: selector => selector === "[data-final-path-segment]" ? [node] : [],
    closest: () => ({ querySelectorAll: () => [source] }) };
  const contextLabel = { dataset: { previewSourceFitLabel: "1" }, style: {}, clientWidth: 30, scrollWidth: 90 };
  const host = { querySelectorAll: selector => selector === "[data-final-path-strip]" ? [strip] : [label, contextLabel] };
  syncFinalPathStripGeometry(host);
  assert.equal(label.style.visibility, "hidden");
  assert.equal(contextLabel.style.visibility, "hidden");
  strip.clientWidth = 3000;
  contextLabel.clientWidth = 120;
  syncFinalPathStripGeometry(host);
  assert.equal(label.style.visibility, "");
  assert.equal(contextLabel.style.visibility, "");
});
