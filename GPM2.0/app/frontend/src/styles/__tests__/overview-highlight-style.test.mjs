import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = Object.fromEntries(["project-export", "project-preview", "assembly", "base", "theme"].map(name => [
  name, readFileSync(new URL(`../${name}.css`, import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
]));
const root = ".project-export-page [data-overview-preview]";
const usedSelector = `${root} .project-preview-used`;
const resultSelector = `${root} .project-preview-final-part:not(.is-gap)`;

function rule(file, selector) {
  const matches = [...css[file].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selectors]) => selectors.split(",").some(value => value.trim() === selector));
  assert.ok(matches.length, `${file}: missing ${selector}`);
  return matches.map(([, , body]) => body).join("\n");
}

function token(body, property) {
  const match = body.match(new RegExp(`(?:^|;)\\s*${property}:\\s*var\\((--[\\w-]+)\\)\\s*;?`));
  assert.ok(match, `${property}: expected a shared variable`);
  return match[1];
}

test("Overview adopted-source highlights are always visible, independently of card hover or focus", () => {
  const used = rule("project-export", usedSelector);
  assert.match(used, /opacity:\s*1;/);
  assert.match(used, /background:\s*var\(--final-path-selection-fill\);/);
  assert.match(used, /box-shadow:\s*inset 0 0 0 3px var\(--final-path-selection-stroke\);/);
  const visibilityRules = [...css["project-export"].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.includes(".project-preview-used"));
  assert.equal(visibilityRules.length, 1);
  assert.equal(visibilityRules[0][1].trim(), usedSelector, "no hover, focus or selected-card gate");
});

test("Overview uses the exact Assembly Final Path source paint and light/dark intensity", () => {
  const used = rule("project-export", usedSelector);
  const source = rule("assembly", ".final-path-source-highlight");
  assert.equal(token(used, "background"), token(source, "fill"));
  assert.match(source, /stroke:\s*var\(--final-path-selection-stroke\);/);
  assert.match(source, /stroke-width:\s*3;/);
  const light = rule("base", ":root");
  assert.match(light, /--final-path-selection-stroke:\s*#c2410c;/);
  assert.match(light, /--final-path-selection-fill:\s*rgba\(234, 88, 12, 0\.22\);/);
  const dark = rule("theme", ':root[data-theme="dark"]');
  assert.match(dark, /--final-path-selection-stroke:\s*#facc15;/);
  assert.match(dark, /--final-path-selection-fill:\s*rgba\(250, 204, 21, 0\.24\);/);
  assert.doesNotMatch(used, /#[\da-f]|rgba?\(/i, "do not fork the shared theme palette");
});

test("Overview Final Path results keep source fills and gaps while showing a permanent warm outline", () => {
  const result = rule("project-export", resultSelector);
  assert.match(result, /outline:\s*3px solid var\(--final-path-selection-stroke\);/);
  assert.match(result, /outline-offset:\s*-3px;/);
  assert.doesNotMatch(result, /(?:background|color|fill|opacity|filter|transform|border|width|height):/);
  const selected = rule("assembly", '[data-final-path-selected="1"] > .track-ctg');
  assert.match(selected, /stroke:\s*var\(--final-path-selection-stroke\);/);
  assert.match(selected, /stroke-width:\s*3;/);
  assert.doesNotMatch(selected, /(?:^|;)\s*fill:/);
  const resultRules = [...css["project-export"].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.includes(".project-preview-final-part"));
  assert.equal(resultRules.length, 1);
  assert.equal(resultRules[0][1].trim(), resultSelector, "exclude Gap and standalone Preview");
});

test("permanent paint never changes source geometry or emphasizes all card frames", () => {
  const used = rule("project-export", usedSelector);
  assert.doesNotMatch(used, /(?:^|;)\s*(?:left|right|top|bottom|width|height|min-width|border|padding|margin|transform|filter|pointer-events):/);
  const frame = rule("project-preview", ".project-preview-card");
  assert.match(frame, /border:\s*1px solid var\(--border-subtle/);
  assert.doesNotMatch(frame, /--preview-card-ring|--final-path-selection/);
  for (const selector of [".project-preview-card:hover", ".project-preview-card:has(.project-preview-card-header:focus-visible)"]) {
    assert.match(rule("project-preview", selector), /border-color:\s*var\(--preview-card-ring/);
  }
  assert.doesNotMatch(css["project-export"], /\.project-preview-card(?:\s|:|\{)/, "card framing stays owned by existing hover/focus rules");
});

test("standalone Preview retains hover-only highlights and Overview overrides load afterward", () => {
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
