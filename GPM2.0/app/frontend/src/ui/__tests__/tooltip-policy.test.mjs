import test from "node:test";
import assert from "node:assert/strict";
import { renderSubviewToolsToggle } from "../pages/assembly/render-subview-tools.js";
import { renderViewNavigation } from "../pages/assembly/view-navigation-ui.js";
import { readFileSync } from "node:fs";

const source = name => readFileSync(new URL(`../${name}`, import.meta.url), "utf8");

test("visible Tools and Full range actions have no paraphrase hints while icon controls remain explained", () => {
  const escape = value => String(value);
  const tools = renderSubviewToolsToggle({ title: "Local View Tools", toggle: "Tools" }, { escapeHtml: escape, escapeAttr: escape });
  assert.doesNotMatch(tools, /data-app-tooltip/);
  assert.match(tools, /aria-controls=/);
  for (const locale of ["en", "zh"]) {
    const html = renderViewNavigation("primary", locale);
    const fit = html.match(/<button[^>]*data-view-nav-action="fit"[^>]*>/)[0];
    assert.doesNotMatch(fit, /data-app-tooltip/);
    assert.match(html, /data-view-nav-action="left"[^>]*data-app-tooltip=/);
    assert.match(html, /data-view-nav-action="toggle-mode"[^>]*data-app-tooltip=/);
  }
});

test("approved name renderers explicitly opt in rather than globally suppressing ordinary hints", () => {
  const expectations = [
    ["pages/assembly/render-tracks.js", /data-app-tooltip-overflow="\.chr-picker-current"/],
    ["pages/assembly/render-tracks.js", /data-app-tooltip-overflow="span"/],
    ["pages/assembly/render-tracks.js", /data-app-tooltip="\$\{escapeAttr\(dataset.label\)\}" data-app-tooltip-overflow/],
    ["pages/assembly/render-subview.js", /data-app-tooltip-overflow="\.subview-candidate-name"/],
    ["pages/assembly/render-subview-composition.js", /data-app-tooltip-overflow="strong"/],
    ["pages/assembly/final-path-card.js", /data-app-tooltip="\$\{escapeAttr\(fullDisplayName\)\}" data-app-tooltip-overflow/],
    ["pages/assembly/final-path-card.js", /data-app-tooltip-overflow="strong"/],
    ["pages/project-preview-page.js", /data-app-tooltip-overflow="small"/],
  ];
  for (const [file, pattern] of expectations) assert.match(source(file), pattern, file);
  assert.doesNotMatch(source("pages/workspace-page.js"), /class="project-path project-detail-path"[^>]*data-app-tooltip/);
  assert.match(source("shell/app-shell.js"), /nameTooltips: false/);
});
