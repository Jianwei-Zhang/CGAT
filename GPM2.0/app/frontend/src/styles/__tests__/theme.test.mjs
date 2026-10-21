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


test("selected SVG and sticky labels keep readable role ink on the same pale contig bars", () => {
  const css = readFileSync(new URL("../assembly.css", import.meta.url), "utf8");
  const rules = [
    [".track-ctg-group.is-active .track-ctg-label", "fill", "primary"],
    [".track-sticky-label.is-active", "color", "primary"],
    [".track-ctg-group.is-companion.is-active .track-ctg-label", "fill", "companion"],
    [".track-sticky-label.is-companion.is-active", "color", "companion"],
    [".track-ctg-group.is-active .track-ctg-label.is-ref", "fill", "ref"],
    [".track-sticky-label.is-ref.is-active", "color", "ref"],
  ];
  for (const [selector, property, role] of rules) {
    const start = css.indexOf(`${selector} {`);
    assert.notEqual(start, -1, selector);
    const rule = css.slice(start, css.indexOf("}", start));
    assert.ok(rule.includes(`${property}: var(--ctg-${role}-text);`), selector);
    assert.doesNotMatch(rule, /--theme-/);
  }
  assert.match(css, /\.track-slot-badge\s*\{[^}]*fill:\s*var\(--theme-ink,\s*#111\)/);
});

test("manual split uses shared Ref and primary colors without implying an auxiliary right fragment", () => {
  const css = readFileSync(new URL("../assembly.css", import.meta.url), "utf8");
  assert.match(css, /\.manual-split-svg text\s*\{[^}]*fill:\s*currentColor/);
  assert.match(css, /\.manual-split-ref\s*\{[^}]*fill:\s*var\(--ctg-ref-fill\);[^}]*stroke:\s*var\(--ctg-ref-stroke\)/);
  assert.match(css, /data-contig-role="companion"\] \.manual-split-contig\s*\{[^}]*fill:\s*var\(--ctg-companion-fill\)/);
  for (const selector of ["contig", "left", "right"]) {
    const start = css.indexOf(`.manual-split-${selector} {`);
    assert.notEqual(start, -1);
    const rule = css.slice(start, css.indexOf("}", start));
    assert.ok(rule.includes("fill: var(--ctg-primary-fill);"));
  }
});
