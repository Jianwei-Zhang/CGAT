import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const themeCss = readFileSync(new URL("../theme.css", import.meta.url), "utf8");
const baseCss = readFileSync(new URL("../base.css", import.meta.url), "utf8");
const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
const prepaint = html.match(/<script>([\s\S]*?)<\/script>/)[1];

test("dark theme changes surfaces, ink, native controls and statuses without recoloring dataset roles", () => {
  assert.match(themeCss, /:root\[data-theme="dark"\]\s*\{[^}]*color-scheme:\s*dark;/);
  for (const token of ["surface-app", "surface-panel", "surface-card", "surface-subtle", "surface-muted",
    "border-subtle", "border-default", "border-strong", "text-primary", "text-secondary", "text-muted",
    "focus-ring", "danger", "theme-blue-ink", "theme-amber-ink", "theme-red-ink", "theme-green-ink"]) {
    assert.match(themeCss, new RegExp(`--${token}:`));
  }
  for (const [role, fill] of [["primary", "#d2dfef"], ["companion", "#e7dec4"], ["ref", "#cfcfcf"]]) {
    assert.match(baseCss, new RegExp(`--ctg-${role}-fill: ${fill};`));
  }
  assert.doesNotMatch(themeCss, /--ctg-(?:primary|companion|ref)-[\w-]+\s*:/);
  assert.doesNotMatch(themeCss, /filter:\s*invert/);
  assert.match(themeCss, /\.track-ctg-label\.is-outside,[\s\S]*?fill:\s*var\(--text-primary\)/);
  assert.match(themeCss, /\.grt-result-repeat-count\s*\{[^}]*stroke:\s*var\(--surface-panel\)/);
});

test("first paint follows OS or saved preference even with missing, null, or corrupt storage", () => {
  for (const systemDark of [false, true]) {
    for (const stored of [null, "null", "{}", "broken", '{"theme":"system"}', '{"theme":"obsolete"}', '{"theme":"light"}', '{"theme":"dark"}']) {
      const document = {documentElement:{dataset:{}}};
      runInNewContext(prepaint, {document, localStorage:{getItem:()=>stored}, matchMedia:()=>({matches:systemDark})});
      const expected = stored === '{"theme":"dark"}' ? "dark" : stored === '{"theme":"light"}' ? "light" : systemDark ? "dark" : "light";
      assert.equal(document.documentElement.dataset.theme, expected, `${stored}, OS dark=${systemDark}`);
    }
    const document = {documentElement:{dataset:{}}};
    runInNewContext(prepaint, {document, localStorage:{getItem:()=>{throw Error("denied");}}, matchMedia:()=>({matches:systemDark})});
    assert.equal(document.documentElement.dataset.theme, systemDark ? "dark" : "light");
  }
});
