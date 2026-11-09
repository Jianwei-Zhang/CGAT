import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = Object.fromEntries(["project-export", "project-preview", "assembly", "base", "theme"].map(name => [
  name, readFileSync(new URL(`../${name}.css`, import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, ""),
]));
const root = ".project-export-page [data-overview-preview]";
const usedSelector = `${root} .project-preview-card .project-preview-used`;
const activeUsed = `${usedSelector}[data-preview-highlighted="1"]`;
const resultSelector = `${root} .project-preview-final-part[data-preview-highlighted="1"]:not(.is-gap)`;

function rule(file, selector) {
  const matches = [...css[file].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selectors]) => selectors.split(",").some(value => value.trim() === selector));
  assert.ok(matches.length, `${file}: missing ${selector}`);
  return matches.map(([, , body]) => body).join("\n");
}

test("Overview source highlights stay hidden even when the whole card is hovered or focused", () => {
  assert.match(rule("project-export", usedSelector), /opacity:\s*0;/);
  assert.match(rule("project-export", activeUsed), /opacity:\s*1;/);
  assert.equal((usedSelector.match(/[.[]/g) || []).length, 4, "match focused-card rule specificity");
  const visibilityRules = [...css["project-export"].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.includes(".project-preview-used"));
  assert.deepEqual(visibilityRules.map(([, selector]) => selector.trim()), [usedSelector, activeUsed]);
  assert.ok(css["project-export"].indexOf(activeUsed) > css["project-export"].indexOf(usedSelector));
});

test("Overview uses the Assembly warm hue with thinner strokes and lighter theme-aware fill", () => {
  const used = rule("project-export", usedSelector);
  assert.match(used, /background:\s*var\(--preview-selection-fill\);/);
  assert.match(used, /box-shadow:\s*inset 0 0 0 2px var\(--final-path-selection-stroke\);/);
  const source = rule("assembly", ".final-path-source-highlight");
  assert.match(source, /stroke:\s*var\(--final-path-selection-stroke\);/);
  const fill = (body, name) => Number(body.match(new RegExp(`${name}: rgba\\([^;]+, ([\\d.]+)\\);`))[1]);
  for (const [file, selector] of [["base", ":root"], ["theme", ':root[data-theme="dark"]']]) {
    const body = rule(file, selector);
    const light = fill(body, "--preview-selection-fill"), strong = fill(body, "--final-path-selection-fill");
    assert.ok(light > 0 && light <= strong / 2, "Overview fill should be at most half the Assembly opacity");
  }
  assert.doesNotMatch(used, /#[\da-f]|rgba?\(/i);
});

test("Final Path role fills and 1px borders are the default; only an inspected non-Gap result has a warm outline", () => {
  const result = rule("project-export", resultSelector);
  assert.match(result, /outline:\s*2px solid var\(--final-path-selection-stroke\);/);
  assert.match(result, /outline-offset:\s*-2px;/);
  assert.doesNotMatch(result, /(?:background|color|fill|opacity|filter|transform|border|width|height):/);
  assert.match(rule("project-preview", ".project-preview-final-part"), /border:\s*1px solid/);
  const resultRules = [...css["project-export"].matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selector]) => selector.includes(".project-preview-final-part"));
  assert.equal(resultRules.length, 1);
  assert.equal(resultRules[0][1].trim(), resultSelector);
});

test("inspecting fragments never changes geometry or promotes every card frame", () => {
  const used = rule("project-export", usedSelector);
  assert.doesNotMatch(used, /(?:^|;)\s*(?:left|right|top|bottom|width|height|min-width|border|padding|margin|transform|filter|pointer-events):/);
  const frame = rule("project-preview", ".project-preview-card");
  assert.match(frame, /border:\s*1px solid var\(--border-subtle/);
  assert.doesNotMatch(frame, /--preview-card-ring|--final-path-selection/);
  for (const selector of [".project-preview-card:hover", ".project-preview-card:has(.project-preview-card-header:focus-visible)"]) {
    assert.match(rule("project-preview", selector), /border-color:\s*var\(--preview-card-ring/);
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
