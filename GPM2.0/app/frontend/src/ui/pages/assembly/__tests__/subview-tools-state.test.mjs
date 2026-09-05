import test from "node:test";
import assert from "node:assert/strict";
import {
  buildSubviewToolsScopeKey,
  constrainSubviewToolsRect,
  normalizeSubviewToolsPreferences,
  resolveSubviewToolsTabKey,
} from "../subview-tools-state.js";
import { renderSubviewTools } from "../render-subview-tools.js";
import { getAssemblyI18n } from "../i18n.js";

test("invalid preferences default closed and only finite geometry is restored", () => {
  const defaults = { version: 1, open: false, tab: "anchors", rect: null };
  assert.deepEqual(normalizeSubviewToolsPreferences(null), defaults);
  assert.deepEqual(normalizeSubviewToolsPreferences({ version: 9, open: true }), defaults);
  assert.deepEqual(normalizeSubviewToolsPreferences({ version: 1, open: 1, tab: "other",
    rect: { left: 0, top: 0, width: Infinity, height: 200 } }), defaults);
  const valid = { version: 1, open: true, tab: "composition",
    rect: { left: -20, top: 0, width: 320, height: 420 } };
  assert.deepEqual(normalizeSubviewToolsPreferences(valid), valid);
});

test("popup starts at the Subview corner and fits a smaller or offset viewport", () => {
  const rect = constrainSubviewToolsRect(null, { width: 1200, height: 800 }, { right: 1000, top: 150 });
  assert.deepEqual(rect, { left: 672, top: 186, width: 320, height: 420 });
  const narrow = constrainSubviewToolsRect(rect, { width: 240, height: 180, left: 30, top: 50 });
  assert.deepEqual(narrow, { left: 38, top: 58, width: 224, height: 164 });
  const large = constrainSubviewToolsRect({ left: -100, top: -100, width: 999, height: 999 },
    { width: 1000, height: 800 });
  assert.deepEqual(large, { left: 8, top: 8, width: 420, height: 784 });
  const tiny = constrainSubviewToolsRect(rect, { width: 1, height: 1 });
  assert.deepEqual(tiny, { left: 0, top: 0, width: 1, height: 1 });
});

test("scope includes workspace, project and chromosome; tabs wrap by keyboard", () => {
  const state = { session: { workspacePath: "a", projectId: 2 }, assembly: { selectedChrName: "Chr1" } };
  assert.notEqual(buildSubviewToolsScopeKey(state), buildSubviewToolsScopeKey({ ...state,
    assembly: { selectedChrName: "Chr2" } }));
  assert.equal(resolveSubviewToolsTabKey("anchors", "ArrowLeft"), "composition");
  assert.equal(resolveSubviewToolsTabKey("composition", "ArrowRight"), "anchors");
  assert.equal(resolveSubviewToolsTabKey("composition", "Home"), "anchors");
  assert.equal(resolveSubviewToolsTabKey("anchors", "End"), "composition");
  assert.equal(resolveSubviewToolsTabKey("anchors", "Tab"), "anchors");
});

test("both locales render a non-modal dialog, keyboard tabs and resize controls", () => {
  const escape = (v) => String(v).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
  for (const locale of ["zh", "en"]) {
    const labels = { ...getAssemblyI18n({ locale }).subview.tools, title: '<title "test">' };
    const html = renderSubviewTools({ tab: "anchors" }, labels, { escapeHtml: escape, escapeAttr: escape });
    assert.match(html, /role="dialog"\s+aria-modal="false"/);
    assert.match(html, /role="tablist"/);
    assert.match(html, /aria-selected="true"\s+tabindex="0"/);
    assert.match(html, /data-subview-tools-resize="both"/);
    assert.match(html, /&lt;title &quot;test&quot;>/);
    assert.doesNotMatch(html, /modal-overlay|inert|<title /);
    assert.ok(html.includes(labels.anchors));
    assert.ok(html.includes(labels.composition));
  }
});
