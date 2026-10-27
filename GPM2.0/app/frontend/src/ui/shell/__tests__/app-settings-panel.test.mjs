import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { APP_SETTINGS_COPY, bindAppSettings, renderSettingsContent } from "../app-settings-panel.js";
import { DEFAULT_APP_SETTINGS, getAppSettings, setAppSettings } from "../../../services/app-settings.js";

for (const locale of ["zh", "en"]) {
  test(`settings expose and select system/light/dark themes in ${locale}`, () => {
    for (const theme of ["system", "light", "dark"]) {
      const output = renderSettingsContent(locale, {...DEFAULT_APP_SETTINGS, theme});
      assert.match(output, /label for="settings-theme-toggle"/);
      assert.match(output, new RegExp(`<option value="${theme}" selected>`));
      assert.match(output, /name="theme"/);
    }
  });
}

for (const locale of ["zh", "en"]) {
  test(`history capacity defaults to unlimited in ${locale}`, () => {
    const output = renderSettingsContent(locale, DEFAULT_APP_SETTINGS);
    assert.match(output, /id="settings-history-input"[^>]+value="(?:不限步数|Unlimited)"/);
    assert.match(output, /<div id="settings-history-option-0" class="assembly-track-combo-option" role="option" aria-selected="true" data-history-option="0">/);
    assert.match(output, /data-history-option="0">(?:不限步数|Unlimited)</);
    assert.match(output, /data-history-option="50">50 (?:步|steps)/);
  });

  test(`restoring defaults describes unlimited history in ${locale}`, () => {
    const copy = APP_SETTINGS_COPY[locale];
    assert.match(copy.restoreConfirm, locale === "zh" ? /恢复为不限步数/ : /return to unlimited/);
    assert.doesNotMatch(copy.restoreConfirm, locale === "zh" ? /恢复为 50 步/ : /return to 50 steps/);
  });
}

for (const locale of ["zh", "en"]) {
  test(`settings reuse the header picker and preserve field names in ${locale}`, () => {
    const html = renderSettingsContent(locale, DEFAULT_APP_SETTINGS);
    assert.equal((html.match(/data-shell-select-toggle/g) || []).length, 4);
    for (const [id, name] of [["theme", "theme"], ["font-size", "fontSize"], ["graph-size", "graphFontSize"], ["language", "language"]]) {
      assert.match(html, new RegExp(`for="settings-${id}-toggle"`));
      assert.match(html, new RegExp(`<select id="settings-${id}" name="${name}" hidden`));
      assert.match(html, new RegExp(`id="settings-${id}-menu"[^>]+role="listbox"`));
    }
    assert.match(html, /value="" selected>Follow Interface|value="" selected>跟随界面/);
    assert.match(html, /class="assembly-track-combo-menu settings-options"/);
    assert.match(html, /name="historyCapacity"[^>]+role="combobox"/);
  });
}

test("settings constrain picker widths and share history option/marker theme tokens", () => {
  const css = readFileSync(new URL("../../../styles/settings.css", import.meta.url), "utf8");
  assert.match(css, /\.settings-row \.shell-select-toggle[^}]+width: 100%; max-width: none/);
  assert.match(css, /\.settings-combobox-toggle[^}]+border-left: 1px solid var\(--border-subtle/);
  assert.match(css, /\.settings-combobox-toggle[^}]+background: var\(--surface-subtle/);
  assert.match(css, /\.settings-options\[hidden\][^}]+display: none/);
  assert.doesNotMatch(css, /\.settings-row select/);
});

test("saving a setting uses localized feedback without throwing; dialog close disposes subscriptions", () => {
  const originalDocument = globalThis.document;
  const previousSettings = getAppSettings();
  const handlers = new Map(); let open, disposed = 0, removed = false;
  const status = { textContent: "", classList: { toggle() {} } };
  const dialog = { ownerDocument: {}, setAttribute() {}, showModal() {}, remove() { removed = true; },
    addEventListener(type, handler) { handlers.set(type, handler); },
    querySelectorAll() { return []; },
    querySelector(selector) { return selector === ".settings-status" ? status : null; } };
  const root = { querySelector() { return { addEventListener(type, handler) { open = handler; }, focus() {} }; } };
  try {
    globalThis.document = { createElement: () => dialog, body: { append() {} } };
    bindAppSettings(root, { getLocale: () => "en", onTypographyChange() {}, onLanguageChange() {},
      updater: { subscribe: () => () => disposed++ } });
    open();
    handlers.get("change")({ target: { name: "theme", value: "dark" } });
    assert.equal(getAppSettings().theme, "dark");
    assert.equal(status.textContent, "Saved");
    handlers.get("close")();
    assert.equal(disposed, 1);
    assert.equal(removed, true);
  } finally { globalThis.document = originalDocument; setAppSettings(previousSettings, { persist: false }); }
});
