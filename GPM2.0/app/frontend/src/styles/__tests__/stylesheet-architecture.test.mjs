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
  "./project-preview.css",
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
  assert.ok(entry.trim().split("\n").length <= 13);
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
    "importer-import-progress-activity",
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
  const buttonRule = importerCss.match(/\.projects-page \.project-history-action, \.project-history-action-slot::before\s*\{([^}]*)\}/);

  assert.ok(headerRule);
  assert.match(headerRule[1], /display:\s*grid;/);
  assert.match(headerRule[1], /grid-template-columns:\s*minmax\(0, 1fr\) auto;/);
  assert.match(headerRule[1], /align-items:\s*center;/);
  assert.ok(titleRule);
  assert.match(titleRule[1], /min-width:\s*0;/);
  assert.match(titleRule[1], /white-space:\s*nowrap;/);
  assert.ok(actionsRule);
  assert.match(actionsRule[1], /flex-wrap:\s*nowrap;/);
  assert.match(actionsRule[1], /gap:\s*4px;/);
  assert.match(actionsRule[1], /display:\s*flex;/);
  assert.match(actionsRule[1], /min-width:\s*0;/);
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


test("routes share the content inset except for the full-bleed Project library", () => {
  const layoutCss = readFileSync(new URL("./layout.css", entryUrl), "utf8");
  const importerCss = readFileSync(new URL("./importer.css", entryUrl), "utf8");
  const assemblyCss = readFileSync(new URL("./assembly.css", entryUrl), "utf8");
  assert.match(layoutCss, /--route-content-inset:\s*8px/);
  assert.match(layoutCss, /\.panel\.stage-panel\s*\{[^}]*padding:\s*var\(--route-content-inset\)/);
  assert.match(layoutCss, /#route-host > :is\(\.page, \.projects-page, \.project-preview-page\)\s*\{[^}]*margin:\s*0;[^}]*padding:\s*0;/);
  const projectRule = importerCss.match(/\.stage-panel:has\(\.projects-page\)\s*\{([^}]*)\}/)?.[1];
  assert.ok(projectRule);
  assert.match(projectRule, /padding:\s*0;/);
  assert.match(projectRule, /overflow:\s*hidden;/);
  assert.match(assemblyCss, /\.assembly-tabs > \.tab-body\s*\{[^}]*padding:\s*0;/);
});


test("internal cards share one radius token while outer panels stay square", () => {
  const baseCss = readFileSync(new URL("./base.css", entryUrl), "utf8");
  const sharedCss = readFileSync(new URL("./shared-components.css", entryUrl), "utf8");
  assert.match(baseCss, /--card-radius:\s*6px;/);
  assert.match(sharedCss, /\.panel\s*\{[^}]*border-radius:\s*0;/);
  const owners = [
    ["shared-components.css", ".card"],
    ["importer.css", ".project-recent-row"],
    ["importer.css", ".project-current .workspace-recipe-field"],
    ["importer.css", ".project-dataset-scroll"],
    ["workspace.css", ".workspace-recipe-summary"],
    ["project-preview.css", ".project-preview-card"],
    ["assembly.css", ".assembly-view-card"],
    ["assembly.css", ".assembly-track-panel"],
    ["subview.css", ".subview-tools-window"],
    ["subview.css", ".subview-anchor-object"],
    ["final-path.css", ".final-path-all-card"],
    ["final-path.css", ".final-path-sort-card"],
    ["degap.css", ".degap-job-card"],
    ["project-export.css", ".project-export-panel"],
    ["project-export.css", ".project-export-detail-section"],
  ];
  for (const [owner, selector] of owners) {
    const css = readFileSync(new URL(`./${owner}`, entryUrl), "utf8");
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const rule = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
    assert.ok(rule, `${owner}: ${selector}`);
    assert.match(rule[1], /border-radius:\s*var\(--card-radius\);/, `${owner}: ${selector}`);
  }
  // Do not clip generic cards: their export and combo menus may extend outside.
  assert.doesNotMatch(sharedCss.match(/\.card\s*\{([^}]*)\}/)[1], /overflow:\s*hidden/);
});

test("root tokens define unified slate surfaces, borders, focus rings, and calibrated contig colors", () => {
  const baseCss = readFileSync(new URL("./base.css", entryUrl), "utf8");
  for (const token of [
    "--surface-app:",
    "--surface-panel:",
    "--surface-card:",
    "--surface-subtle:",
    "--surface-muted:",
    "--border-subtle:",
    "--border-default:",
    "--text-primary:",
    "--text-secondary:",
    "--text-muted:",
    "--action-primary-bg:",
    "--focus-ring:",
    "--shadow-xs:",
    "--shadow-md:",
    "--ctg-primary-fill:",
    "--ctg-companion-fill:",
    "--ctg-ref-fill:",
  ]) {
    assert.ok(baseCss.includes(token), `expected ${token} in base.css`);
  }
});

test("shell navigation uses a segmented control bar and bounded selected-name workspace selector without legacy gray gradients", () => {
  const shellCss = readFileSync(new URL("./shell.css", entryUrl), "utf8");
  const stylesheet = readStylesheetTree(entryUrl);

  assert.match(shellCss, /\.route-nav\s*\{[^}]*border-radius:\s*7px;[^}]*background:\s*var\(--surface-muted/);
  assert.match(shellCss, /\.route-button\.is-active\s*\{[^}]*background:\s*var\(--surface-panel,\s*#ffffff\);/);
  assert.match(shellCss, /\.nav-session-field select\s*\{[^}]*width:\s*var\(--workspace-select-width,\s*12ch\)/);
  assert.doesNotMatch(shellCss, /width:\s*96px;/);
  assert.doesNotMatch(stylesheet, /linear-gradient\(#(?:fafafa|f6f6f6|fbfbfb|ffffff|f0f0f0|ededed)/);
});

test("final path card shares the main view subtle surface and keeps table and log layouts compact and aligned", () => {
  const assemblyCss = readFileSync(new URL("./assembly.css", entryUrl), "utf8");
  const finalPathCss = readFileSync(new URL("./final-path.css", entryUrl), "utf8");

  assert.match(assemblyCss, /\.assembly-main-view\.card\s*\{[^}]*background:\s*var\(--surface-subtle,\s*#f8fafc\);/);
  assert.match(finalPathCss, /\.final-path-card\.card\s*\{[^}]*background:\s*var\(--surface-subtle,\s*#f8fafc\);/);
  assert.match(finalPathCss, /\.final-path-card-list-head\s*>\s*:first-child\s*\{[^}]*background:\s*var\(--surface-muted,\s*#eef2f6\);/);
  assert.match(finalPathCss, /\.final-path-card-list-head-card\s*\{[^}]*padding:\s*4px 8px 4px 11px;[^}]*background:\s*var\(--surface-muted,\s*#eef2f6\);/);
  assert.match(finalPathCss, /\.final-path-card-list\s*\{[^}]*gap:\s*5px;/);
  assert.match(finalPathCss, /\.final-path-sort-card\s*\{[^}]*border-left:\s*4px solid var\(--ctg-primary-stroke,\s*#6d85a1\);[^}]*padding:\s*4px 8px;[^}]*cursor:\s*grab;/);
  assert.match(finalPathCss, /\.final-path-card-cell input:disabled[\s\S]*?border-color:\s*transparent;[\s\S]*?pointer-events:\s*none;/);
  assert.match(finalPathCss, /\.final-path-log-summary\s*\{[^}]*background:\s*var\(--surface-panel,\s*#ffffff\);/);
  assert.match(finalPathCss, /\.final-path-log-table-wrap\s*\{[^}]*background:\s*var\(--surface-panel,\s*#ffffff\);/);
});
