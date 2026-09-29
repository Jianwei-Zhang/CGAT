import test from "node:test";
import assert from "node:assert/strict";
import { renderAppShell } from "../app-shell.js";

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
