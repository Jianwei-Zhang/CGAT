import test from "node:test";
import assert from "node:assert/strict";
import { renderAppShell } from "../app-shell.js";

test("app shell session cards do not render runtime card", () => {
  const html = renderAppShell({
    runtime: { mode: "Tauri Runtime" },
    locale: "zh",
  });

  assert.doesNotMatch(html, />运行时</);
  assert.match(html, />项目区</);
  assert.match(html, />项目</);
  assert.match(html, />项目导出</);
});

test("app shell renders language switch as session meta card at right side", () => {
  const html = renderAppShell({
    runtime: { mode: "Tauri Runtime" },
    locale: "zh",
  });

  assert.match(html, /id="app-language-select"/);
  assert.match(
    html,
    /<div class="session-meta">[\s\S]*id="session-workspace-select"[\s\S]*id="session-project-select"[\s\S]*id="app-language-select"/,
  );
});

test("app shell renders english labels when locale is en", () => {
  const html = renderAppShell({
    runtime: { mode: "Tauri Runtime" },
    locale: "en",
  });

  assert.match(html, />Assembly Workbench</);
  assert.match(html, />Import</);
  assert.match(html, />Project Area</);
  assert.match(html, />Assembly</);
  assert.match(html, />Project Export</);
  assert.doesNotMatch(html, />Records</);
  assert.doesNotMatch(html, />Settings</);
  assert.match(html, />Project</);
  assert.match(html, />中文</);
  assert.match(html, />English</);
  assert.doesNotMatch(html, />Chinese</);
});
