import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { APP_SETTINGS_COPY, SETTINGS_TABS, bindAppSettings, renderSettingsContent } from "../app-settings-panel.js";
import { DEFAULT_APP_SETTINGS, getAppSettings, setAppSettings } from "../../../services/app-settings.js";
import { clearSkippedConfirmations, rememberConfirmation } from "../confirmation-session.js";

for (const locale of ["zh", "en"]) {
  test(`settings expose visual theme cards for system/light/dark in ${locale}`, () => {
    for (const theme of ["system", "light", "dark"]) {
      const output = renderSettingsContent(locale, { ...DEFAULT_APP_SETTINGS, theme }, "appearance");
      assert.match(output, new RegExp(`data-settings-radio="theme" data-settings-value="${theme}" aria-checked="true"`));
    }
  });
}

for (const locale of ["zh", "en"]) {
  test(`history capacity renders preset buttons and custom numeric input in ${locale}`, () => {
    const output = renderSettingsContent(locale, DEFAULT_APP_SETTINGS, "editing");
    assert.match(output, /data-history-preset="0" aria-pressed="true"/);
    assert.match(output, /data-history-preset="50" aria-pressed="false"/);
    assert.match(output, /id="settings-history-input" name="historyCapacity"/);
    const custom = renderSettingsContent(locale, { ...DEFAULT_APP_SETTINGS, historyCapacity: 75 }, "editing");
    assert.match(custom, /data-history-preset="0" aria-pressed="false"/);
    assert.match(custom, /id="settings-history-input"[^>]+value="75"/);
  });

  test(`restoring defaults preserves display language and describes unlimited history in ${locale}`, () => {
    const copy = APP_SETTINGS_COPY[locale];
    assert.match(copy.restoreConfirm, locale === "zh" ? /界面语言将保持不变/ : /Display language stays unchanged/);
    assert.match(copy.restoreConfirm, locale === "zh" ? /恢复为不限步数/ : /returns to unlimited/);
  });
}

for (const locale of ["zh", "en"]) {
  test(`settings render all four balanced category panels with modern controls in ${locale}`, () => {
    const html = renderSettingsContent(locale, DEFAULT_APP_SETTINGS, "general", { skippedConfirmations: 2 });
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

    assert.match(generalPanel, /data-settings-radio="language"/);
    assert.match(generalPanel, /name="restoreLastWorkspace"/);
    assert.match(generalPanel, /name="defaultWorkspaceRoot"/);
    assert.match(generalPanel, /id="settings-import-parallelism" name="importParallelism"/);

    assert.match(appearancePanel, /data-settings-radio="theme"/);
    assert.match(appearancePanel, /data-settings-radio="fontSize"/);
    assert.match(appearancePanel, /data-settings-radio="graphFontSize"/);
    assert.match(appearancePanel, /class="settings-preview settings-preview-card"/);
    assert.doesNotMatch(appearancePanel, /<details/);
    assert.match(appearancePanel, /data-settings-reset-layout/);

    assert.match(editingPanel, /name="historyCapacity"/);
    assert.match(editingPanel, /data-settings-radio="localViewDefaultMode"/);
    assert.match(editingPanel, /name="localViewDefaultPinned"/);
    assert.match(editingPanel, /name="deleteHotkeyEnabled"/);
    assert.match(editingPanel, /data-settings-reset-confirmations/);
    assert.doesNotMatch(editingPanel, /data-settings-reset-confirmations disabled/);

    assert.match(updatesPanel, /id="settings-update-title"/);
    assert.match(updatesPanel, /name="autoCheckUpdates"/);
    assert.match(updatesPanel, /data-settings-copy-diagnostics/);
  });

  test(`selecting an initial activeTab exposes only that category panel in ${locale}`, () => {
    const html = renderSettingsContent(locale, DEFAULT_APP_SETTINGS, "editing");
    assert.match(html, /id="settings-tab-editing"[^>]+aria-selected="true"/);
    assert.doesNotMatch(html, /id="settings-panel-editing"[^>]+hidden>/);
    assert.match(html, /id="settings-panel-general"[^>]+hidden>/);
  });
}

test("settings stylesheet defines segmented controls, switches, theme cards, and live preview card", () => {
  const css = readFileSync(new URL("../../../styles/settings.css", import.meta.url), "utf8");
  assert.match(css, /\.settings-segmented\s*\{/);
  assert.match(css, /\.settings-switch-track\s*\{/);
  assert.match(css, /\.settings-theme-cards\s*\{/);
  assert.match(css, /\.settings-preview-card\s*\{/);
  assert.match(css, /\.settings-row \.shell-select-toggle[^}]+width: 100%; max-width: none/);
});

test("saving settings updates switches, radios, confirmations, layout reset, and disposes on close", async () => {
  const originalDocument = globalThis.document;
  const previousSettings = getAppSettings();
  const handlers = new Map();
  let clickOpen, disposed = 0, removed = false, layoutResets = 0, languageChanges = 0;
  const status = { textContent: "", classList: { toggle() {} } };
  const confDesc = { textContent: "" };
  const confButton = { disabled: false };
  const dialog = {
    ownerDocument: {},
    setAttribute() {},
    showModal() {},
    close() { handlers.get("close")?.(); },
    remove() { removed = true; },
    addEventListener(type, handler) { handlers.set(type, handler); },
    querySelectorAll() { return []; },
    querySelector(selector) {
      if (selector === ".settings-status") return status;
      if (selector === "[data-settings-confirmations-desc]") return confDesc;
      if (selector === "[data-settings-reset-confirmations]") return confButton;
      return null;
    },
  };
  const root = {
    querySelector() {
      return {
        addEventListener(type, handler) { if (type === "click") clickOpen = handler; },
        removeEventListener() {},
        focus() {},
      };
    },
  };
  try {
    globalThis.document = { createElement: () => dialog, body: { append() {} } };
    rememberConfirmation("test-settings-panel-reset");
    const controller = bindAppSettings(root, {
      getLocale: () => "en",
      onTypographyChange() {},
      onLanguageChange() { languageChanges++; },
      onLayoutReset() { layoutResets++; },
      updater: { subscribe: () => () => disposed++, getState: () => ({ phase: "idle", enabled: true }) },
    });
    assert.equal(controller.isOpen(), false);
    clickOpen();
    assert.equal(controller.isOpen(), true);

    handlers.get("change")({ target: { name: "restoreLastWorkspace", type: "checkbox", checked: false } });
    assert.equal(getAppSettings().restoreLastWorkspace, false);
    assert.equal(status.textContent, "Saved");

    handlers.get("change")({ target: { name: "deleteHotkeyEnabled", type: "checkbox", checked: false } });
    assert.equal(getAppSettings().deleteHotkeyEnabled, false);

    handlers.get("click")({ target: { closest: selector => selector === "[data-settings-radio]" ? { dataset: { settingsRadio: "theme", settingsValue: "dark" } } : null } });
    assert.equal(getAppSettings().theme, "dark");

    handlers.get("click")({ target: { closest: selector => selector === "[data-settings-radio]" ? { dataset: { settingsRadio: "localViewDefaultMode", settingsValue: "floating" } } : null } });
    assert.equal(getAppSettings().localViewDefaultMode, "floating");

    await handlers.get("click")({ target: { closest: selector => selector === "[data-settings-reset-layout]" ? {} : null } });
    assert.equal(layoutResets, 1);

    await handlers.get("click")({ target: { closest: selector => selector === "[data-settings-reset-confirmations]" ? {} : null } });
    assert.equal(confButton.disabled, true);
    assert.match(confDesc.textContent, /No confirmation prompts skipped/);
    assert.equal(languageChanges, 0);

    controller.close();
    assert.equal(controller.isOpen(), false);
    assert.equal(disposed, 1);
    assert.equal(removed, true);
  } finally {
    clearSkippedConfirmations();
    globalThis.document = originalDocument;
    setAppSettings(previousSettings, { persist: false });
  }
});

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
  const root = { querySelector() { return { addEventListener(type, handler) { if (type === "click") open = handler; }, removeEventListener() {}, focus() {} }; } };
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
  } finally {
    globalThis.document = originalDocument;
  }
});
