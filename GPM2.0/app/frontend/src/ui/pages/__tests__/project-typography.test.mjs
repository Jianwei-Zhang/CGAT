import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const styles = Object.fromEntries(["base", "importer", "project-export", "project-preview", "final-path"].map(name => [
  name, readFileSync(new URL(`../../../styles/${name}.css`, import.meta.url), "utf8"),
]));

// Inspect declarations without adding a browser or dependency to these CSS contracts.
function rule(file, selector) {
  const css = styles[file].replace(/\/\*[\s\S]*?\*\//g, "");
  const matches = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, selectors]) => selectors.split(",").some(value => value.trim() === selector));
  assert.ok(matches.length, `${file}: missing ${selector}`);
  return Object.fromEntries(matches.flatMap(([, , body]) => body.split(";").filter(value => value.includes(":"))
    .map(value => { const at = value.indexOf(":"); return [value.slice(0, at).trim(), value.slice(at + 1).trim()]; })));
}

function font(file, selector, size, weight) {
  const declarations = rule(file, selector);
  assert.equal(declarations["font-size"], `var(--font-${size})`, `${selector}: font-size`);
  if (weight) assert.equal(declarations["font-weight"], String(weight), `${selector}: font-weight`);
}

test("Project and Overview use the same scalable heading tier for identities and section titles", () => {
  font("importer", ".project-title-row", "title", 600);
  font("project-export", ".project-export-identity dd > .project-export-project-badge", "title", 600);
  font("importer", ".project-current .project-section-divider", "title");
  font("project-export", ".project-export-page .project-section-divider", "title");
  assert.equal(rule("importer", ".project-section-divider > h3")["font-weight"], "600");
  for (const selector of [".project-export-panel h4", ".project-export-detail-heading h4"]) {
    font("project-export", selector, "title", 600);
  }
});

test("pseudomolecule names align at the secondary heading tier without changing standalone Preview", () => {
  font("project-export", ".project-current .project-export-final-path-row-label", "section", 600);
  font("project-export", ".project-export-page [data-overview-preview] .project-preview-chr-name", "section", 600);
  font("project-preview", ".project-preview-chr-name", "body", 700);
  font("project-preview", ".project-preview-heading h2", "heading", 700);
});

test("main content, datasets and controls stay below headings in the body tier", () => {
  font("importer", ".project-dataset-table", "body");
  font("project-export", ".project-export-page", "body");
  font("project-export", ".project-export-identity dd > .project-dataset-role", "body");
  font("project-export", ".project-export-used-metrics", "body");
  font("project-export", ".project-export-assignment", "body");
  for (const selector of [".project-export-page .button", ".project-export-page .final-path-export-item",
    ".project-export-page [data-overview-preview] .project-preview-open", ".project-export-detail-toggle"]) {
    font("project-export", selector, "body");
  }
  for (const selector of [".project-export-used-row strong", ".project-export-assignment-value", ".project-export-detail-sort"]) {
    assert.equal(rule("project-export", selector)["font-weight"], "600");
  }
});

test("Overview overrides both shared table and cell sizes without changing Assembly tables", () => {
  font("final-path", ".final-path-log-table.project-export-detail-table", "small");
  font("final-path", ".final-path-log-table.project-export-detail-table td", "small");
  for (const selector of [".project-export-page .project-export-detail-table",
    ".project-export-page .project-export-detail-table th", ".project-export-page .project-export-detail-table td"]) {
    font("project-export", selector, "body");
  }
  assert.equal(rule("project-export", ".project-export-page .project-export-detail-table th")["font-weight"], "600");
  const imports = readFileSync(new URL("../../../styles/components.css", import.meta.url), "utf8");
  assert.ok(imports.indexOf('"./project-export.css"') > imports.indexOf('"./final-path.css"'), "equal-specificity Overview rules load after shared Final Path rules");
});

test("metadata, type badges and length summaries share the small tier on both pages", () => {
  for (const selector of [".project-detail-path", ".project-detail-created", ".project-heading-meta",
    ".project-dataset-table small", ".project-dataset-role", ".project-section-count"]) {
    font("importer", selector, "small");
  }
  for (const selector of [".project-export-identity dt", ".project-export-summary-line", ".project-export-legend",
    ".project-export-detail-count", ".project-current .project-export-final-path-preview-length"]) {
    font("project-export", selector, "small");
  }
  for (const selector of [".project-preview-card-summary", ".project-preview-track-label", ".project-preview-axis"]) {
    font("project-preview", selector, "small");
  }
});

test("graph labels retain their independent font setting rather than inheriting interface tiers", () => {
  font("project-export", ".project-export-final-path-preview-ctg", "graph-small");
  font("project-preview", ".project-preview-contig-label", "graph-small");
  font("project-preview", ".project-preview-final-part > span", "graph-small");
  assert.match(rule("base", ":root")["--font-graph-small"], /var\(--graph-font-size, 12px\)/);
});

test("all four interface tiers scale together with App font size", () => {
  const base = rule("base", ":root");
  assert.equal(base["font-size"], "var(--app-font-size, 14px)");
  const names = ["title", "section", "body", "small"];
  const ratios = names.map(name => {
    assert.match(base[`--font-${name}`], /^[0-9.]+rem$/);
    return Number.parseFloat(base[`--font-${name}`]);
  });
  for (const baseline of [12, 14, 16, 18]) {
    const sizes = ratios.map(ratio => ratio * baseline);
    assert.ok(sizes.every((size, i) => i === 0 || sizes[i - 1] > size));
  }
  for (const [i, size] of [18, 16, 14, 13].entries()) assert.ok(Math.abs(ratios[i] * 14 - size) < 0.02);
});
