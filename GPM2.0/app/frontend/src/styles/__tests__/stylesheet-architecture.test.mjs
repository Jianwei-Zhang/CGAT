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
  assert.match(readFileSync(new URL("./subview.css", entryUrl), "utf8"), /@media \(max-width: 700px\)/);
  assert.match(readFileSync(new URL("./final-path.css", entryUrl), "utf8"), /@media \(max-width: 760px\)/);
  assert.match(readFileSync(new URL("./project-export.css", entryUrl), "utf8"), /@media \(max-width: 1180px\)/);
});

test("component stylesheet tree keeps unique animation owners", () => {
  const stylesheet = readStylesheetTree(entryUrl);
  const keyframes = [...stylesheet.matchAll(/@keyframes\s+([\w-]+)/g)].map((match) => match[1]);

  assert.deepEqual(keyframes.sort(), [
    "importer-import-progress-indeterminate",
    "main-view-history-chip-pulse",
    "main-view-history-track-pulse",
    "pipeline-spin",
    "subview-pairwise-spin",
  ]);
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

test("assembly status toast stays above desktop controls and returns to flow on narrow screens", () => {
  const assemblyCss = readFileSync(new URL("./assembly.css", entryUrl), "utf8");
  const desktopRule = assemblyCss.match(/\.assembly-status-toast-wrap\s*\{([^}]*)\}/);
  const responsiveCss = assemblyCss.slice(assemblyCss.indexOf("@media (max-width: 1200px)"));
  const narrowRule = responsiveCss.match(/\.assembly-status-toast-wrap\s*\{([^}]*)\}/);

  assert.ok(desktopRule);
  assert.match(desktopRule[1], /top:\s*-34px;/);
  assert.match(desktopRule[1], /max-width:\s*min\(560px,\s*62vw\);/);
  assert.ok(narrowRule);
  assert.match(narrowRule[1], /position:\s*static;/);
  assert.match(narrowRule[1], /max-width:\s*none;/);
});


test("project library actions share the title row without squeezing button labels", () => {
  const importerCss = readFileSync(new URL("./importer.css", entryUrl), "utf8");
  const headerRule = importerCss.match(/\.project-recents-header\s*\{([^}]*)\}/);
  const titleRule = importerCss.match(/\.project-recents-header h4\s*\{([^}]*)\}/);
  const actionsRule = importerCss.match(/\.project-library-actions\s*\{([^}]*)\}/);
  const buttonRule = importerCss.match(/\.projects-page \.project-history-action\s*\{([^}]*)\}/);

  assert.ok(headerRule);
  assert.match(headerRule[1], /display:\s*flex;/);
  assert.match(headerRule[1], /flex-wrap:\s*wrap;/);
  assert.match(headerRule[1], /align-items:\s*center;/);
  assert.ok(titleRule);
  assert.match(titleRule[1], /flex:\s*0 0 auto;/);
  assert.match(titleRule[1], /white-space:\s*nowrap;/);
  assert.ok(actionsRule);
  assert.match(actionsRule[1], /flex-wrap:\s*wrap;/);
  assert.match(actionsRule[1], /margin-left:\s*auto;/);
  assert.match(actionsRule[1], /flex:\s*0 0 auto;/);
  assert.match(actionsRule[1], /max-width:\s*100%;/);
  assert.ok(buttonRule);
  assert.match(buttonRule[1], /flex:\s*0 0 auto;/);
  assert.match(buttonRule[1], /white-space:\s*nowrap;/);
  assert.match(importerCss, /\.projects-page \.project-library-actions \[hidden\][^{]*\{[^}]*display:\s*none;/);
});

test("importer toast keeps its status horizontal and wraps long workspace paths", () => {
  const overlaysCss = readFileSync(new URL("./overlays.css", entryUrl), "utf8");
  const toastRule = overlaysCss.match(/\.importer-status-toast\s*\{([^}]*)\}/);
  const statusRule = overlaysCss.match(/\.importer-status-toast > strong\s*\{([^}]*)\}/);
  const summaryRule = overlaysCss.match(/\.importer-status-toast > span\s*\{([^}]*)\}/);

  assert.ok(toastRule);
  assert.match(toastRule[1], /min-width:\s*0;/);
  assert.ok(statusRule);
  assert.match(statusRule[1], /flex:\s*0 0 auto;/);
  assert.match(statusRule[1], /white-space:\s*nowrap;/);
  assert.ok(summaryRule);
  assert.match(summaryRule[1], /min-width:\s*0;/);
  assert.match(summaryRule[1], /overflow-wrap:\s*anywhere;/);
});
