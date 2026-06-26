import test from "node:test";
import assert from "node:assert/strict";

import {
  formatDateTime,
  formatNumber,
  getLocale,
  getMessages,
  t,
} from "../index.js";

test("getLocale resolves locale from state or raw locale input", () => {
  assert.equal(getLocale("zh"), "zh");
  assert.equal(getLocale("en"), "en");
  assert.equal(getLocale({ locale: "en" }), "en");
  assert.equal(getLocale({ locale: "zh" }), "zh");
  assert.equal(getLocale({ locale: "fr" }), "zh");
  assert.equal(getLocale({}), "zh");
});

test("getMessages returns the domain catalog for zh and en", () => {
  assert.equal(getMessages({ locale: "zh" }, "shell").title, "装配工作台");
  assert.equal(getMessages({ locale: "en" }, "shell").title, "Assembly Workbench");
  assert.equal(getMessages({ locale: "zh" }, "shell").workspace, "项目区");
  assert.equal(getMessages({ locale: "en" }, "shell").workspace, "Project Area");
});

test("t resolves nested keys for zh and en", () => {
  assert.equal(t({ locale: "zh" }, "shell.title"), "装配工作台");
  assert.equal(t({ locale: "en" }, "shell.title"), "Assembly Workbench");
});

test("t interpolates named variables", () => {
  assert.equal(
    t("en", "workspace.cards.selectedProject", { projectName: "demo" }),
    "Selected Project: demo",
  );
  assert.equal(
    t("zh", "workspace.cards.selectedProject", { projectName: "demo" }),
    "已选择项目：demo",
  );
});

test("getMessages throws for removed records and settings domains", () => {
  assert.throws(
    () => getMessages({ locale: "en" }, "records"),
    /Missing i18n domain "records" for locale "en"/,
  );
  assert.throws(
    () => getMessages({ locale: "en" }, "settings"),
    /Missing i18n domain "settings" for locale "en"/,
  );
});

test("t throws a clear error for missing paths", () => {
  assert.throws(
    () => t("en", "shell.missingKey"),
    /Missing i18n message for path "shell\.missingKey" in locale "en"/,
  );
});

test("formatNumber uses locale-aware separators", () => {
  assert.equal(formatNumber("zh", 1200000), "1,200,000");
  assert.equal(formatNumber("en", 1200000), "1,200,000");
});

test("formatDateTime uses locale-aware output", () => {
  assert.match(formatDateTime("en", "2026-04-04 10:00:00"), /2026/);
  assert.match(formatDateTime("zh", "2026-04-04 10:00:00"), /2026/);
});
