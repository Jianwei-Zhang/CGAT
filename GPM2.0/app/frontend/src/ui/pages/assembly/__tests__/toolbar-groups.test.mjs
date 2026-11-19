import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToolbarGroup } from "../toolbar-groups.js";
import { renderTrackIdentity } from "../track-identity.js";
import { getMessages } from "../../../i18n/index.js";
import { renderAssemblyPage, createState } from "./tabs-semantics-harness.mjs";

const css = readFileSync(new URL("../../../../styles/assembly-toolbar.css", import.meta.url), "utf8");
function ruleBody(selector) {
  const rules = css.replace(/\/\*[\s\S]*?\*\//g, "").matchAll(/([^{}]+)\{([^{}]*)\}/g);
  const rule = [...rules].find(match => match[1].trim() === selector);
  assert.ok(rule, `missing toolbar rule: ${selector}`);
  return rule[2];
}

test("toolbar spacing responds to container width but is bounded instead of filling the row", () => {
  const selector = ".assembly-track-inline-controls[data-main-track-toolbar],\n"
    + ".assembly-track-inline-controls[data-subview-toolbar],\n"
    + ".subview-window .assembly-track-inline-controls[data-subview-toolbar]";
  const toolbar = ruleBody(selector);
  assert.match(toolbar, /display:\s*flex;/);
  assert.match(toolbar, /flex-wrap:\s*wrap;/);
  assert.match(toolbar, /container-type:\s*inline-size;/);
  assert.match(toolbar, /overflow:\s*visible;/);
  assert.doesNotMatch(toolbar, /space-between|overflow-x:\s*auto/);
  assert.match(toolbar, /column-gap:\s*clamp\(12px, 2\.4cqw, 36px\)/);
  assert.doesNotMatch(css, /data-toolbar-compact|data-toolbar-group-open/);
});

test("logical groups wrap complete controls inside flex-enclosed tonal trays with unified 26px controls", () => {
  const group = ruleBody(".assembly-toolbar-group,\n.subview-window [data-subview-toolbar] > .assembly-toolbar-group");
  assert.match(group, /display:\s*inline-flex;/);
  assert.match(group, /flex-wrap:\s*wrap;/);
  assert.match(group, /align-items:\s*center;/);
  assert.match(group, /border:\s*0;/);
  assert.match(group, /background:\s*var\(--surface-subtle/);
  assert.match(ruleBody(".assembly-toolbar-group-content"), /display:\s*contents;/);
  assert.match(ruleBody(".assembly-toolbar-group-label,\n.assembly-toolbar-group-content > *"), /display:\s*inline-flex;/);
  assert.match(css, /--toolbar-control-size: 26px;/);
  assert.match(ruleBody(".subview-window .assembly-track-inline-controls[data-subview-toolbar]"), /--toolbar-control-size: 26px;/);
  const html = renderToolbarGroup("filter", ["", '<label id="first">first</label>', '<label id="second">second</label>'], getMessages("en", "assembly"));
  assert.match(html, /class="assembly-toolbar-group-start">[\s\S]*?class="assembly-toolbar-group-label"[\s\S]*?<label id="first">first<\/label><\/div> <label id="second">second<\/label>/);
  assert.equal(renderToolbarGroup("filter", ["", " "], getMessages("en", "assembly")), "");
});

test("toolbar inputs and preset menus have separate content-based width limits", () => {
  const prefix = ":is([data-main-track-toolbar], [data-subview-toolbar])";
  const combo = ruleBody(`${prefix} .assembly-toolbar-group .assembly-track-inline-field .assembly-track-combo`);
  assert.match(combo, /width:\s*var\(--toolbar-combo-width, 64px\)/);
  assert.match(combo, /min-width:\s*44px;/);
  assert.match(combo, /max-width:\s*140px;/);
  assert.match(ruleBody(`${prefix} .assembly-toolbar-group .assembly-track-inline-field .assembly-track-combo.is-support`), /max-width:\s*180px;/);
  const menu = ruleBody(`${prefix} .assembly-track-combo-menu`);
  assert.match(menu, /right:\s*auto;/);
  assert.match(menu, /width:\s*max-content;/);
  assert.match(menu, /max-width:\s*min\(240px, calc\(100vw - 16px\)\);/);
});
test("bilingual group captions explain purpose without adding headings or input tooltips", () => {
  for (const locale of ["zh", "en"]) {
    const i18n = getMessages(locale, "assembly");
    for (const kind of ["display", "filter", "edit"]) {
      const html = renderToolbarGroup(kind, '<input value="5">', i18n);
      assert.match(html, new RegExp(`data-toolbar-group="${kind}"`));
      assert.match(html, /<span class="assembly-toolbar-group-label" tabindex="0" data-app-tooltip=/);
      assert.match(html, /aria-description=/);
      assert.doesNotMatch(html, /<button|aria-expanded|toolbar-group-toggle|toolbar-group-chevron/);
      assert.match(html, /<input value="5">/);
      assert.doesNotMatch(html, /<h[1-6]/);
      const local = renderToolbarGroup(kind, '<input value="5">', i18n, { local: true });
      assert.doesNotMatch(local, /创建分相轨道|Create phased tracks/);
    }
    assert.equal(renderToolbarGroup("display", "", i18n), "");
  }
});
test("role suffixes are separate non-shrinking items; only escaped names truncate", () => {
  for (const [role, marker] of [["primary", "P"], ["support", "A"], ["ref", "R"]]) {
    const name = `Long_<&>_${"dataset".repeat(20)}`;
    const html = renderTrackIdentity(role === "ref" ? name : `${name} [${marker}]`, role);
    assert.match(html, /class="assembly-track-label-name">Long_&lt;&amp;&gt;_/);
    assert.ok(html.endsWith(`<span class="assembly-track-role-marker" aria-hidden="true">[${marker}]</span>`));
    assert.equal(html.split(`[${marker}]`).length - 1, 1);
  }
  assert.match(renderTrackIdentity("user [P] [P]", "primary"), /label-name">user \[P\]<\/span>/);
  assert.doesNotMatch(renderTrackIdentity("Haplotype 1", "phased"), /role-marker/);
  const css = readFileSync(new URL("../../../../styles/assembly-toolbar.css", import.meta.url), "utf8");
  assert.match(css, /\.assembly-track-label-row > \.assembly-track-role-marker\s*\{[^}]*flex: 0 0 auto;[^}]*overflow: visible;/);
  assert.match(css, /\.assembly-track-label-row > \.assembly-track-label-name\s*\{[^}]*text-overflow: ellipsis;/);
});
test("main render groups existing fields once and puts track creation with history, not display", () => {
  const html = renderAssemblyPage(createState({ initializer: { phasedAssembly: true, existingProjects: [{ projectId: 7, phasedAssemblyEnabled: true }] } }));
  const toolbar = html.slice(html.indexOf("data-main-track-toolbar"), html.indexOf("data-main-track-toolbar") + 18000);
  const display = toolbar.indexOf('data-toolbar-group="display"');
  const filter = toolbar.indexOf('data-toolbar-group="filter"');
  const edit = toolbar.indexOf('data-toolbar-group="edit"');
  assert.ok(display >= 0 && filter > display && edit > filter);
  assert.ok(toolbar.indexOf('data-marker-display-toggle') < filter);
  assert.ok(toolbar.indexOf('id="assembly-track-alignment-length"') > filter);
  assert.ok(toolbar.indexOf('data-create-phased-track') > edit);
  assert.ok(toolbar.indexOf('data-main-history-action="undo"') > edit);
  for (const id of ["assembly-track-support-ds-ctg-len", "assembly-track-alignment-length", "assembly-track-identity-pct"]) {
    assert.equal(html.split(`id="${id}"`).length - 1, 1);
  }
});
