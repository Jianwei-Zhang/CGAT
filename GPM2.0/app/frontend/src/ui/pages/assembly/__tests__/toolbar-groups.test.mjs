import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToolbarGroup } from "../toolbar-groups.js";
import { resolveCompactToolbarGroups } from "../toolbar-groups-runtime.js";
import { renderTrackIdentity } from "../track-identity.js";
import { getMessages } from "../../../i18n/index.js";
import { renderAssemblyPage, createState } from "./tabs-semantics-harness.mjs";

const metrics = [
  { kind: "display", width: 400, compactWidth: 60 },
  { kind: "filter", width: 500, compactWidth: 60 },
  { kind: "edit", width: 200, compactWidth: 50 },
];
test("toolbar groups stay inline when they fit, then compact editing before filters", () => {
  assert.deepEqual(resolveCompactToolbarGroups(1116, metrics), []);
  assert.deepEqual(resolveCompactToolbarGroups(1000, metrics), ["edit"]);
  assert.deepEqual(resolveCompactToolbarGroups(700, metrics), ["edit", "filter"]);
  assert.deepEqual(resolveCompactToolbarGroups(250, metrics), ["edit", "filter", "display"]);
  assert.deepEqual(resolveCompactToolbarGroups(0, []), []);
});
test("bilingual group captions explain purpose without adding headings or input tooltips", () => {
  for (const locale of ["zh", "en"]) {
    const i18n = getMessages(locale, "assembly");
    for (const kind of ["display", "filter", "edit"]) {
      const html = renderToolbarGroup(kind, '<input value="5">', i18n);
      assert.match(html, new RegExp(`data-toolbar-group="${kind}"`));
      assert.match(html, /data-toolbar-group-toggle aria-expanded="true" data-app-tooltip=/);
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
