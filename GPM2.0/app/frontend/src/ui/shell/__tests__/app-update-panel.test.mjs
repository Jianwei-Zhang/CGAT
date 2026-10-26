import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderUpdateSettings, updateStatusText, openUpdateDialog } from "../app-update-panel.js";
import { renderSettingsContent } from "../app-settings-panel.js";

for (const locale of ["en", "zh"]) {
  test(`update section is last and localized (${locale})`, () => {
    const html = renderSettingsContent(locale);
    assert.ok(html.indexOf("settings-update-title") > html.indexOf("settings-editing-title"));
    assert.ok(html.indexOf("settings-update-title") < html.indexOf("settings-footer"));
    const text = renderUpdateSettings(locale, { phase: "available", enabled: true, currentVersion: "2.0.12", version: "<script>" });
    assert.ok(text.includes(locale === "en" ? "Check for updates" : "检查更新"));
    assert.ok(!text.includes("<script>")); assert.match(text, /data-update-view/);
  });
}
test("update errors use current UI language, never raw backend content", () => {
  assert.match(updateStatusText({ error: "update_signature" }, "zh"), /签名/);
  assert.match(updateStatusText({ error: "<script>" }, "en"), /Update failed/);
});
test("update dialog extends existing theme styles without hard-coded colors", () => {
  const css = readFileSync(new URL("../../../styles/app-update.css", import.meta.url), "utf8");
  assert.match(css, /var\(--theme-ink\)/); assert.match(css, /var\(--font-small\)/); assert.doesNotMatch(css, /#[0-9a-f]{3,8}/i);
  const source = readFileSync(new URL("../app-update-panel.js", import.meta.url), "utf8");
  assert.match(source, /app-dialog app-update-dialog/); assert.match(source, /button primary/); assert.match(source, /textContent = text/);
});
test("dialog requests the selected locale and ignores stale notes after language change", async () => {
  const original = globalThis.document; const nodes = new Map(); const calls = [];
  let locale = "en", localeChanged; const pending = {};
  const node = () => ({ textContent: "", hidden: false, disabled: false, checked: false,
    classList: { toggle() {} }, setAttribute() {}, removeAttribute() {}, addEventListener() {}, focus() {} });
  const dialog = { ...node(), querySelector(s) { if (!nodes.has(s)) nodes.set(s, node()); return nodes.get(s); }, showModal() {}, close() {}, remove() {} };
  globalThis.document = { querySelector() {}, activeElement: null, createElement() { return dialog; }, body: { append() {} } };
  try {
    openUpdateDialog({ getState: () => ({ version: "2.0.13", currentVersion: "2.0.12", phase: "available" }),
      subscribe() { return () => {}; }, notes(l) { calls.push(l); return new Promise(resolve => { pending[l] = resolve; }); } },
    { getLocale: () => locale, subscribeLocale(fn) { localeChanged = fn; return () => {}; } });
    locale = "zh"; localeChanged(); pending.zh("中文说明"); await Promise.resolve(); pending.en("English notes"); await Promise.resolve();
    assert.deepEqual(calls, ["en", "zh"]); assert.equal(nodes.get(".app-update-notes").textContent, "中文说明");
  } finally { globalThis.document = original; }
});

test("downloading disables another check but keeps the progress-dialog entry", () => {
  const html = renderUpdateSettings("en", { phase: "downloading", enabled: true, version: "2.0.13", downloaded: 3, total: 10 });
  assert.match(html, /data-update-check disabled/); assert.match(html, /data-update-view/);
  assert.match(html, /30%/);
});
