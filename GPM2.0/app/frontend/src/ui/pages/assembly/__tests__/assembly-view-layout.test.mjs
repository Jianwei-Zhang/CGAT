import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderViewNavigation } from "../view-navigation-ui.js";

const assemblyCss = readFileSync(new URL("../../../../styles/assembly.css", import.meta.url), "utf8");
const subviewCss = readFileSync(new URL("../../../../styles/subview.css", import.meta.url), "utf8");
const ruleBody = (css, selector) => {
  const start = css.indexOf(`${selector} {`);
  assert.ok(start >= 0, `missing CSS rule: ${selector}`);
  return css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
};

for (const role of ["primary", "subview"]) {
  for (const locale of ["zh", "en"]) {
    test(`${role} ${locale} navigation groups the window label and value after fit`, () => {
      const html = renderViewNavigation(role, locale);
      const label = locale === "zh" ? "窗口：" : "Window:";
      assert.match(html, /data-view-nav-action="fit"/);
      assert.ok(html.indexOf('data-view-nav-action="fit"') < html.indexOf('class="view-nav-span"'));
      assert.ok(html.includes(`<span class="view-nav-span">${label}<span data-view-nav-span`));
      assert.match(html, /data-view-nav-span[^>]*>—<\/span><\/span>/);
    });
  }
}

test("shared window summary reserves a fixed slot without resizing the fit button or navigation axis", () => {
  const group = ruleBody(assemblyCss, ".view-nav-span");
  assert.match(group, /display:\s*inline-flex/);
  assert.match(group, /flex:\s*0 0 24ch/);
  assert.match(group, /min-width:\s*0/);
  assert.match(group, /max-width:\s*calc\(100% - 12px\)/);
  assert.match(group, /white-space:\s*nowrap/);
  assert.match(group, /gap:\s*4px/);
  assert.match(group, /margin-inline-start:\s*12px/);
  const value = ruleBody(assemblyCss, ".view-nav-span [data-view-nav-span]");
  assert.match(value, /flex:\s*1 1 0/);
  assert.match(value, /min-width:\s*0/);
  assert.match(value, /overflow:\s*hidden/);
  assert.match(value, /text-overflow:\s*ellipsis/);
  assert.match(value, /text-align:\s*start/);
  assert.match(value, /font-variant-numeric:\s*tabular-nums/);
  assert.match(ruleBody(assemblyCss, ".assembly-view-navigation"), /flex-wrap:\s*wrap/);
  assert.match(ruleBody(assemblyCss, ".view-nav-range"), /flex:\s*1 1 240px/);
  assert.match(assemblyCss, /@media \(max-width: 520px\)\s*\{[^}]*\}\s*\.view-nav-range\s*\{[^}]*flex-basis:\s*100%/);
});

test("shared view card removes nested panel frames but keeps a local-view divider", () => {
  const panels = ruleBody(assemblyCss,
    ".assembly-main-view > .assembly-track-unified,\n.assembly-main-view > .subview-selection-panel > .subview-alignment-card");
  assert.match(panels, /border:\s*0/);
  assert.match(panels, /padding:\s*0/);
  const local = ruleBody(assemblyCss, ".assembly-main-view > .subview-selection-panel");
  assert.match(local, /border-top:\s*1px solid/);
  assert.match(local, /padding-top:\s*10px/);
  assert.match(ruleBody(subviewCss, ".subview-selection-panel"), /display:\s*grid/);
  assert.match(ruleBody(assemblyCss, ".assembly-view-card"), /border:\s*1px solid/);
});
