import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { APP_SETTINGS_COPY, SETTINGS_TABS, bindAppSettings, renderSettingsContent } from "../app-settings-panel.js";
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

for (const locale of ["zh", "en"]) {
  test(`settings organize controls into four categorized panels with ARIA tabs in ${locale}`, () => {
    const html = renderSettingsContent(locale, DEFAULT_APP_SETTINGS);
    assert.match(html, /role="tablist"[^>]+aria-orientation="vertical"/);
    for (const tab of SETTINGS_TABS) {
      assert.match(html, new RegExp(`id="settings-tab-${tab}"[^>]+data-settings-tab="${tab}"[^>]+aria-controls="settings-panel-${tab}"`));
      assert.match(html, new RegExp(`role="tabpanel" id="settings-panel-${tab}" data-settings-panel="${tab}"`));
    }
    assert.match(html, /id="settings-tab-general"[^>]+aria-selected="true"/);
    assert.doesNotMatch(html, /id="settings-panel-general"[^>]+hidden>/);
    for (const inactive of ["appearance", "editing", "updates"]) {
      assert.match(html, new RegExp(`id="settings-tab-${inactive}"[^>]+aria-selected="false"`));
      assert.match(html, new RegExp(`id="settings-panel-${inactive}"[^>]+hidden>`));
    }
    const generalPanel = html.slice(html.indexOf('id="settings-panel-general"'), html.indexOf('id="settings-panel-appearance"'));
    const appearancePanel = html.slice(html.indexOf('id="settings-panel-appearance"'), html.indexOf('id="settings-panel-editing"'));
    const editingPanel = html.slice(html.indexOf('id="settings-panel-editing"'), html.indexOf('id="settings-panel-updates"'));
    const updatesPanel = html.slice(html.indexOf('id="settings-panel-updates"'), html.indexOf('class="settings-footer"'));
    assert.match(generalPanel, /name="language"/);
    assert.doesNotMatch(generalPanel, /name="theme"/);
    assert.match(appearancePanel, /name="theme"[\s\S]*name="fontSize"[\s\S]*name="graphFontSize"[\s\S]*class="settings-preview"/);
    assert.doesNotMatch(appearancePanel, /name="language"/);
    assert.match(editingPanel, /name="historyCapacity"/);
    assert.match(updatesPanel, /id="settings-update-title"/);
  });

  test(`selecting an initial activeTab exposes only that category panel in ${locale}`, () => {
    const html = renderSettingsContent(locale, DEFAULT_APP_SETTINGS, "editing");
    assert.match(html, /id="settings-tab-editing"[^>]+aria-selected="true"/);
    assert.doesNotMatch(html, /id="settings-panel-editing"[^>]+hidden>/);
    assert.match(html, /id="settings-panel-general"[^>]+hidden>/);
  });
}

test("category tabs switch panels by click and keyboard, and toggle the update indicator dot", () => {
  const originalDocument = globalThis.document;
  const handlers = new Map();
  let open, updateSubscriber, updateState = { phase: "idle", enabled: true };
  const makeClassList = initial => {
    const set = new Set(initial);
    return {
      contains: name => set.has(name),
      toggle: (name, force) => (force === undefined ? (set.has(name) ? (set.delete(name), false) : (set.add(name), true)) : (force ? set.add(name) : set.delete(name), force)),
    };
  };
  const tabs = SETTINGS_TABS.map(id => {
    const attrs = new Map([["aria-selected", String(id === "general")]]);
    const node = {
      dataset: { settingsTab: id },
      tabIndex: id === "general" ? 0 : -1,
      focused: false,
      classList: makeClassList(id === "general" ? ["settings-nav-item", "is-active"] : ["settings-nav-item"]),
      setAttribute(name, value) { attrs.set(name, value); },
      getAttribute(name) { return attrs.get(name); },
      focus() { node.focused = true; },
      closest(selector) { return selector === "[data-settings-tab]" ? node : null; },
    };
    return node;
  });
  const panels = SETTINGS_TABS.map(id => ({
    dataset: { settingsPanel: id },
    hidden: id !== "general",
    innerHTML: "",
    contains() { return false; },
    querySelector() { return null; },
  }));
  const dot = { hidden: true };
  const content = { scrollTop: 42 };
  const dialog = {
    ownerDocument: {},
    setAttribute() {},
    showModal() {},
    remove() {},
    addEventListener(type, handler) { handlers.set(type, handler); },
    querySelectorAll(selector) {
      if (selector === "[data-settings-tab]") return tabs;
      if (selector === "[data-settings-panel]") return panels;
      return [];
    },
    querySelector(selector) {
      if (selector === "[data-settings-update-dot]") return dot;
      if (selector === "[data-settings-update]") return panels[3];
      if (selector === ".settings-content") return content;
      const match = selector.match(/^\[data-settings-tab="(.+)"\]$/);
      if (match) return tabs.find(tab => tab.dataset.settingsTab === match[1]) || null;
      return null;
    },
  };
  const root = { querySelector() { return { addEventListener(type, handler) { open = handler; }, focus() {} }; } };
  try {
    globalThis.document = { activeElement: null, createElement: () => dialog, body: { append() {} } };
    bindAppSettings(root, {
      getLocale: () => "en",
      onTypographyChange() {},
      onLanguageChange() {},
      updater: {
        getState: () => updateState,
        subscribe(fn) { updateSubscriber = fn; return () => {}; },
      },
    });
    open();
    assert.equal(dot.hidden, true);
    updateState = { phase: "available", enabled: true, version: "2.0.21" };
    updateSubscriber();
    assert.equal(dot.hidden, false);

    handlers.get("click")({ target: tabs[1] });
    assert.equal(tabs[1].getAttribute("aria-selected"), "true");
    assert.equal(tabs[0].getAttribute("aria-selected"), "false");
    assert.equal(panels[1].hidden, false);
    assert.equal(panels[0].hidden, true);
    assert.equal(content.scrollTop, 0);

    let prevented = false;
    handlers.get("keydown")({ target: tabs[1], key: "ArrowDown", preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
    assert.equal(tabs[2].getAttribute("aria-selected"), "true");
    assert.equal(tabs[2].focused, true);
    assert.equal(panels[2].hidden, false);

    handlers.get("keydown")({ target: tabs[2], key: "End", preventDefault() {} });
    assert.equal(tabs[3].getAttribute("aria-selected"), "true");
    assert.equal(panels[3].hidden, false);

    handlers.get("keydown")({ target: tabs[3], key: "Home", preventDefault() {} });
    assert.equal(tabs[0].getAttribute("aria-selected"), "true");
    assert.equal(panels[0].hidden, false);
  } finally { globalThis.document = originalDocument; }
});
