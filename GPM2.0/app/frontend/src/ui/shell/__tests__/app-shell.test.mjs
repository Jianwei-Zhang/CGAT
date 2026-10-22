import { applyAppTheme, DEFAULT_APP_SETTINGS, getAppSettings, setAppSettings, APP_SETTINGS_KEY } from "../../../services/app-settings.js";
import test from "node:test";
import assert from "node:assert/strict";
import { bindAppThemeToggle, renderAppShell } from "../app-shell.js";

test("app shell omits the former top card", () => {
  const html = renderAppShell({
    runtime: { mode: "Tauri Runtime" },
    locale: "zh",
  });

  assert.doesNotMatch(html, /class="topbar/);
  assert.doesNotMatch(html, />运行时</);
  assert.doesNotMatch(html, />装配工作台</);
  assert.match(html, />项目</);
  assert.match(html, />装配</);
  assert.match(html, />项目导出</);
});

test("app shell renders project and language switches inline before settings", () => {
  const html = renderAppShell({
    runtime: { mode: "Tauri Runtime" },
    locale: "zh",
  });

  assert.match(html, /id="app-language-select"/);
  assert.match(
    html,
    /<div class="nav-session-controls">[\s\S]*class="nav-session-field"[\s\S]*id="session-workspace-select"[\s\S]*class="nav-session-field nav-session-field-language"[\s\S]*id="app-language-select"[\s\S]*data-app-settings/,
  );
});

test("app shell renders english labels when locale is en", () => {
  const html = renderAppShell({
    runtime: { mode: "Tauri Runtime" },
    locale: "en",
  });

  assert.doesNotMatch(html, />Assembly Workbench</);
  assert.doesNotMatch(html, /data-route="workspace"/);
  assert.match(html, />Project</);
  assert.match(html, />Assembly</);
  assert.match(html, />Project Export</);
  assert.doesNotMatch(html, />Records</);
  assert.doesNotMatch(html, />Settings</);
  assert.match(html, />Project</);
  assert.match(html, />中文</);
  assert.match(html, />English</);
  assert.doesNotMatch(html, />Chinese</);
});


test("preview navigation is placed between Project and Assembly in both languages", () => {
  for (const locale of ["zh", "en"]) {
    const html = renderAppShell({ locale });
    assert.match(html, /data-route="importer"[\s\S]*data-route="projectPreview"[\s\S]*data-route="assembly"[\s\S]*data-route="projectExport"/);
    assert.match(html, locale === "zh" ? />预览<\/button>/ : />Preview<\/button>/);
  }
});


test("theme shortcut sits between language and Settings and labels the next action", () => {
  try {
    for (const [theme, action] of [["dark", "light"], ["light", "dark"]]) {
      setAppSettings({ theme }, { persist: false });
      const html = renderAppShell({ locale: "en" });
      assert.match(html, /id="app-language-select"[\s\S]*data-app-theme-toggle[\s\S]*data-app-settings/);
      assert.ok(html.includes(`aria-label="Switch to ${action} mode"`));
      assert.ok(html.includes(`aria-pressed="${theme === "dark"}"`));
      assert.match(html, /data-app-theme-toggle[^>]*>[\s\S]*?<svg/);
    }
  } finally { setAppSettings(DEFAULT_APP_SETTINGS, { persist: false }); }
});

test("theme shortcut persists light/dark, preserves other settings, follows settings changes, and rebinds once", () => {
  const storage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  const listeners = new Set();
  const button = { innerHTML: "", title: "", attrs: {},
    setAttribute(name, value) { this.attrs[name] = value; },
    addEventListener(name, listener) { assert.equal(name, "click"); listeners.add(listener); },
    removeEventListener(name, listener) { listeners.delete(listener); },
    click() { for (const listener of listeners) listener(); },
  };
  const root = { querySelector: () => button };
  let saved, locale = "zh";
  try {
    Object.defineProperty(globalThis, "localStorage", { configurable: true,
      value: { setItem(key, value) { assert.equal(key, APP_SETTINGS_KEY); saved = JSON.parse(value); } } });
    setAppSettings({ theme: "system", fontSize: 18, graphFontSize: 14, historyCapacity: 123 }, { persist: false });
    applyAppTheme({ dataset: {} }, true);
    bindAppThemeToggle(root, { getLocale: () => locale });
    assert.equal(button.title, "切换浅色模式");
    button.click();
    assert.equal(saved.theme, "light");
    assert.equal(saved.fontSize, 18);
    assert.equal(saved.graphFontSize, 14);
    assert.equal(saved.historyCapacity, 123);
    assert.equal(button.title, "切换深色模式");
    assert.equal(button.attrs["aria-pressed"], "false");
    button.click();
    assert.equal(getAppSettings().theme, "dark");
    locale = "en";
    bindAppThemeToggle(root, { getLocale: () => locale });
    assert.equal(listeners.size, 1);
    assert.equal(button.title, "Switch to light mode");
    setAppSettings({ ...getAppSettings(), theme: "light" }, { persist: false });
    assert.equal(button.title, "Switch to dark mode");
    button.click();
    assert.equal(saved.theme, "dark");
    // A failed save leaves the applied theme and button state unchanged.
    Object.defineProperty(globalThis, "localStorage", { configurable: true,
      value: { setItem() { throw Error("quota"); } } });
    button.click();
    assert.equal(getAppSettings().theme, "dark");
    assert.equal(button.title, "Switch to light mode");
  } finally {
    if (storage) Object.defineProperty(globalThis, "localStorage", storage);
    else delete globalThis.localStorage;
    setAppSettings(DEFAULT_APP_SETTINGS, { persist: false });
    root.querySelector = () => null;
    bindAppThemeToggle(root, { getLocale: () => locale });
    assert.equal(listeners.size, 0);
  }
});
