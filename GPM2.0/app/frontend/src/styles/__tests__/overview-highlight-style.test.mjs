import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = Object.fromEntries(["project-export", "project-preview", "assembly", "base", "theme"].map(name => [
  name, readFileSync(new URL(`../${name}.css`, import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
]));
const root = ".project-export-page [data-overview-preview]";
const card = `${root} .project-preview-card`;
const usedSelector = `${card} .project-preview-used`;
const resultSelector = `${root} .project-preview-final-part:not(.is-gap)`;
const activeCard = [
  `${card}:hover`,
  `${card}:has(.project-preview-card-header:focus-visible)`,
];
const activeUsed = activeCard.map(selector => `${selector} .project-preview-used`);
const activeResults = activeCard.map(selector => `${selector} .project-preview-final-part:not(.is-gap)`);

function rule(file, selector) {
  const matches = [...css[file].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selectors]) => selectors.split(",").some(value => value.trim() === selector));
  assert.ok(matches.length, `${file}: missing ${selector}`);
  return matches.map(([, , body]) => body).join("\n");
}

function selectorsFor(fragment) {
  return [...css["project-export"].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .flatMap(([, selectors]) => selectors.split(",").map(selector => selector.trim()))
    .filter(selector => selector.includes(fragment));
}

test("Overview keeps adopted sources and non-Gap results persistently outlined with the same thin outer stroke", () => {
  for (const selector of [usedSelector, resultSelector]) {
    const body = rule("project-export", selector);
    assert.match(body, /outline:\s*1px solid var\(--final-path-selection-stroke\);/);
    assert.match(body, /outline-offset:\s*0;/);
    assert.doesNotMatch(body, /outline-offset:\s*-|font-weight:/);
  }
  const used = rule("project-export", usedSelector);
  assert.match(used, /opacity:\s*1;/);
  assert.match(used, /background:\s*transparent;/);
  assert.match(used, /box-shadow:\s*none;/);
  assert.match(used, /border-radius:\s*inherit;/);
  assert.doesNotMatch(used, /--preview-selection-fill|inset/);
});

test("hover and keyboard focus thicken every adopted interval and result in only the current card", () => {
  for (const [base, selectors] of [[usedSelector, activeUsed], [resultSelector, activeResults]]) {
    for (const selector of selectors) {
      const body = rule("project-export", selector);
      assert.match(body, /outline-width:\s*2px;/);
      assert.doesNotMatch(body, /(?:opacity|background|fill|box-shadow|filter|font-weight):/);
      assert.ok(css["project-export"].indexOf(selector) > css["project-export"].indexOf(base));
    }
  }
  // Header and whitespace hover emphasize all adopted patches in this card;
  // sibling cards keep their thin persistent outlines, with no fragment state.
  assert.deepEqual([...new Set(selectorsFor(".project-preview-used"))], [usedSelector, ...activeUsed]);
  assert.deepEqual([...new Set(selectorsFor(".project-preview-final-part"))], [resultSelector, ...activeResults]);
  assert.doesNotMatch(css["project-export"], /data-preview-highlighted|data-preview-part-key/);
});

test("Overview retains the shared warm highlight hue in both themes without tinting source interiors", () => {
  const source = rule("assembly", ".final-path-source-highlight");
  assert.match(source, /stroke:\s*var\(--final-path-selection-stroke\);/);
  for (const [file, selector] of [["base", ":root"], ["theme", ':root[data-theme="dark"]']]) {
    assert.match(rule(file, selector), /--final-path-selection-stroke:\s*#[\da-f]+;/i);
  }
  for (const selector of [usedSelector, resultSelector, ...activeUsed, ...activeResults]) {
    assert.doesNotMatch(rule("project-export", selector), /#[\da-f]|rgba?\(/i);
  }
});

test("result feedback preserves role fills and Gaps in both persistent and active states", () => {
  for (const selector of [resultSelector, ...activeResults]) {
    assert.doesNotMatch(rule("project-export", selector), /(?:^|;)\s*(?:background|color|fill|opacity|filter|transform|border|width|height|font-weight):/);
  }
  assert.match(rule("project-preview", ".project-preview-final-part"), /border:\s*1px solid/);
  assert.ok(selectorsFor(".project-preview-final-part").every(selector => selector.endsWith(":not(.is-gap)")));
});

test("outer source and endpoint outlines are not clipped, while labels and unused context retain their clipping", () => {
  for (const selector of [
    `${card} .project-preview-plot`,
    `${card} .project-preview-contig.is-adopted`,
    `${card} .project-preview-reference`,
  ]) {
    assert.match(rule("project-export", selector), /overflow:\s*visible;/);
  }
  assert.match(rule("project-preview", ".project-preview-contig-label"), /overflow:\s*hidden;/);
  assert.match(rule("project-preview", ".project-preview-final-part > span"), /overflow:\s*hidden;/);
  assert.match(rule("project-preview", ".project-preview-contig"), /overflow:\s*hidden;/);
  assert.match(rule("project-preview", ".project-preview-contig.is-context .project-preview-contig-label"), /visibility:\s*hidden;/);
  assert.deepEqual(selectorsFor(".project-preview-contig"), [`${card} .project-preview-contig.is-adopted`]);
});

test("card-level feedback never changes interval geometry or adds fragment glows, and retains the existing card shadow", () => {
  for (const selector of [usedSelector, resultSelector, ...activeUsed, ...activeResults]) {
    const body = rule("project-export", selector);
    assert.doesNotMatch(body, /(?:^|;)\s*(?:left|right|top|bottom|width|height|min-width|border|padding|margin|transform|filter|pointer-events|font-weight):/);
    assert.doesNotMatch(body.replace(/box-shadow:\s*none;/g, ""), /box-shadow:/);
  }
  const frame = rule("project-preview", ".project-preview-card");
  assert.match(frame, /border:\s*1px solid var\(--border-subtle/);
  assert.doesNotMatch(frame, /--preview-card-ring|--final-path-selection/);
  for (const selector of [".project-preview-card:hover", ".project-preview-card:has(.project-preview-card-header:focus-visible)"]) {
    const body = rule("project-preview", selector);
    assert.match(body, /border-color:\s*var\(--preview-card-ring/);
    assert.match(body, /box-shadow:\s*inset 0 0 0 1px var\(--preview-card-ring[^;]*\),\s*0 2px 8px var\(--preview-card-glow/);
  }
});

test("standalone Preview retains its existing whole-card highlights and Overview overrides load afterward", () => {
  const used = rule("project-preview", ".project-preview-used");
  assert.match(used, /opacity:\s*0;/);
  assert.match(used, /background:\s*transparent;/);
  for (const selector of [".project-preview-card:hover .project-preview-used",
    ".project-preview-card:has(.project-preview-card-header:focus-visible) .project-preview-used"]) {
    assert.match(rule("project-preview", selector), /opacity:\s*1;/);
  }
  const imports = readFileSync(new URL("../components.css", import.meta.url), "utf8");
  assert.ok(imports.indexOf('"./project-export.css"') > imports.indexOf('"./project-preview.css"'));
});
