import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { readStylesheetImports, readStylesheetTree } from "./style-test-support.mjs";

const entryUrl = new URL("../components.css", import.meta.url);
const expectedImports = [
  "./shared-components.css",
  "./overlays.css",
  "./shell.css",
  "./importer.css",
  "./workspace.css",
  "./assembly.css",
  "./subview.css",
  "./final-path.css",
  "./degap.css",
  "./project-export.css",
];

test("component stylesheet entry keeps the documented cascade order", () => {
  const entry = readFileSync(entryUrl, "utf8");
  const expanded = readStylesheetTree(entryUrl);

  assert.deepEqual(readStylesheetImports(entryUrl), expectedImports);
  assert.ok(entry.trim().split("\n").length <= 12);
  assert.ok(expanded.indexOf(".modal-dialog {") < expanded.indexOf(".assembly-confirm-dialog {"));
  assert.ok(
    expanded.indexOf(".track-collinearity-band {") <
      expanded.indexOf(".subview-track-svg .track-collinearity-band {"),
  );
  assert.ok(
    expanded.indexOf(".assembly-final-path-layout {") <
      expanded.indexOf(".degap-graph-wrap .assembly-final-path-layout {"),
  );
});

test("feature styles declare owners, use LF, and keep responsive rules with their owners", () => {
  for (const relativePath of expectedImports) {
    const source = readFileSync(new URL(relativePath, entryUrl), "utf8");
    assert.match(source, /^\/\* Owner: /, relativePath);
    assert.doesNotMatch(source, /\r/, relativePath);
    assert.doesNotMatch(source, /@import\s/, relativePath);
  }

  assert.match(readFileSync(new URL("./workspace.css", entryUrl), "utf8"), /@media \(max-width: 560px\)/);
  assert.match(readFileSync(new URL("./assembly.css", entryUrl), "utf8"), /@media \(max-width: 1200px\)/);
  assert.match(readFileSync(new URL("./subview.css", entryUrl), "utf8"), /@media \(max-width: 1200px\)/);
  assert.match(readFileSync(new URL("./final-path.css", entryUrl), "utf8"), /@media \(max-width: 760px\)/);
  assert.match(readFileSync(new URL("./project-export.css", entryUrl), "utf8"), /@media \(max-width: 1180px\)/);
});

test("component stylesheet tree keeps unique animation owners", () => {
  const stylesheet = readStylesheetTree(entryUrl);
  const keyframes = [...stylesheet.matchAll(/@keyframes\s+([\w-]+)/g)].map((match) => match[1]);

  assert.deepEqual(keyframes.sort(), ["pipeline-spin", "subview-pairwise-spin"]);
  assert.equal(new Set(keyframes).size, keyframes.length);
});

test("assembly combo menus keep their feature-owned hidden display override", () => {
  const stylesheet = readStylesheetTree(entryUrl);
  const menuRule = stylesheet.match(/\.assembly-track-combo-menu\s*\{([^}]*)\}/);
  const hiddenMenuRule = stylesheet.match(/\.assembly-track-combo-menu\.is-hidden\s*\{([^}]*)\}/);

  assert.ok(menuRule, "expanded component styles should define the assembly combo menu");
  assert.match(menuRule[1], /display:\s*grid;/);
  assert.ok(hiddenMenuRule, "the Assembly owner should override the shared hidden utility");
  assert.match(hiddenMenuRule[1], /display:\s*none;/);
});
