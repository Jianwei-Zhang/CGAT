import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const readCss = name => readFileSync(new URL(`../${name}.css`, import.meta.url), "utf8");
const assemblyCss = readCss("assembly");
const rule = selector => {
  const start = assemblyCss.indexOf(`${selector} {`);
  assert.notEqual(start, -1, selector);
  return assemblyCss.slice(start + selector.length + 2, assemblyCss.indexOf("}", start));
};

test("Final Path correlation has dedicated high-contrast warm tokens in both themes", () => {
  const light = readCss("base").match(/:root\s*\{([^}]+)\}/)[1];
  const darkRoots = [...readCss("theme").matchAll(/:root\[data-theme="dark"\]\s*\{([^}]+)\}/g)]
    .map(match => match[1]).join("\n");
  assert.match(light, /--final-path-selection-stroke:\s*#c2410c;/);
  assert.match(light, /--final-path-selection-fill:\s*rgba\(234, 88, 12, 0\.22\);/);
  assert.match(darkRoots, /--final-path-selection-stroke:\s*#facc15;/);
  assert.match(darkRoots, /--final-path-selection-fill:\s*rgba\(250, 204, 21, 0\.24\);/);
});

test("selected Final Path bars keep their source fill and use a bold non-scaling warm outline", () => {
  const selected = rule('[data-final-path-selected="1"] > .track-ctg');
  assert.match(selected, /stroke:\s*var\(--final-path-selection-stroke\);/);
  assert.match(selected, /stroke-width:\s*3;/);
  assert.match(selected, /vector-effect:\s*non-scaling-stroke;/);
  assert.doesNotMatch(selected, /^\s*(?:fill|filter|opacity|stroke-opacity|width|height|transform):/m);
  const row = rule('.final-path-sort-row[data-final-path-selected="1"]');
  assert.match(row, /outline:\s*3px solid var\(--final-path-selection-stroke\);/);
  assert.match(row, /outline-offset:\s*-3px;/);
  assert.doesNotMatch(row, /(?:background|border|box-shadow|filter):/);
});

test("Main and Local source overlays share the theme-aware warm fill and never capture input", () => {
  const overlay = rule(".final-path-source-highlight");
  assert.match(overlay, /fill:\s*var\(--final-path-selection-fill\);/);
  assert.match(overlay, /stroke:\s*var\(--final-path-selection-stroke\);/);
  assert.match(overlay, /stroke-width:\s*3;/);
  assert.match(overlay, /vector-effect:\s*non-scaling-stroke;/);
  assert.match(overlay, /pointer-events:\s*none;/);
  assert.doesNotMatch(overlay, /(?:filter|box-shadow):/);
});
