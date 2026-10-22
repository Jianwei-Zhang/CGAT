import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const themeCss = readFileSync(new URL("../theme.css", import.meta.url), "utf8");
const baseCss = readFileSync(new URL("../base.css", import.meta.url), "utf8");
const html = readFileSync(new URL("../../../index.html", import.meta.url), "utf8");
const prepaint = html.match(/<script>([\s\S]*?)<\/script>/)[1];

test("dark theme changes surfaces, ink, native controls and statuses and remaps contig bars for the dark canvas", () => {
  assert.match(themeCss, /:root\[data-theme="dark"\]\s*\{[^}]*color-scheme:\s*dark;/);
  for (const token of ["surface-app", "surface-panel", "surface-card", "surface-subtle", "surface-muted",
    "border-subtle", "border-default", "border-strong", "text-primary", "text-secondary", "text-muted",
    "focus-ring", "danger", "theme-blue-ink", "theme-amber-ink", "theme-red-ink", "theme-green-ink"]) {
    assert.match(themeCss, new RegExp(`--${token}:`));
  }
  // Light stays the baseline palette; the mounted dark theme remaps the same
  // role tokens so bars sit on the dark canvas instead of glowing, while
  // hue order (blue > amber > grey) and role ink remain distinguishable.
  for (const [role, fill] of [["primary", "#d2dfef"], ["companion", "#e7dec4"], ["ref", "#cfcfcf"]]) {
    assert.match(baseCss, new RegExp(`--ctg-${role}-fill: ${fill};`));
    assert.match(themeCss, new RegExp(`--ctg-${role}-fill: #`), `dark ${role} fill`);
  }
  assert.doesNotMatch(themeCss, /filter:\s*invert/);
  assert.match(themeCss, /\.track-ctg-label\.is-outside,[\s\S]*?fill:\s*var\(--text-primary\)/);
  assert.match(themeCss, /\.grt-result-repeat-count\s*\{[^}]*stroke:\s*var\(--surface-panel\)/);
  assert.match(themeCss, /:root\[data-theme="dark"\] \.track-ctg\.is-active\s*\{[^}]*fill:\s*#33587f;/);
});

test("native select popup options and groups have explicit dark surfaces and readable enabled or disabled ink", () => {
  assert.match(
    themeCss,
    /:root\[data-theme="dark"\] select option,\s*:root\[data-theme="dark"\] select optgroup\s*\{[^}]*background-color:\s*var\(--surface-panel\);[^}]*color:\s*var\(--text-primary\);/,
  );
  assert.match(
    themeCss,
    /:root\[data-theme="dark"\] select option:disabled,\s*:root\[data-theme="dark"\] select optgroup:disabled,\s*:root\[data-theme="dark"\] select optgroup:disabled option\s*\{[^}]*color:\s*var\(--text-muted\);/,
  );
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


test("Preview and Project Export keep gap markers white and use black or white Preview GAP text for the theme", () => {
  const previewCss = readFileSync(new URL("../project-preview.css", import.meta.url), "utf8");
  const exportCss = readFileSync(new URL("../project-export.css", import.meta.url), "utf8");
  assert.match(baseCss, /--gap-marker-fill:\s*#ffffff;/);
  assert.match(baseCss, /--gap-marker-text:\s*#1b1b1b;/);
  assert.doesNotMatch(themeCss, /--gap-marker-(?:fill|text)\s*:/);
  const gapRule = exportCss.match(/\.project-export-final-path-preview-gap\s*\{([^}]*)\}/)?.[1];
  assert.ok(gapRule);
  assert.match(gapRule, /background:\s*var\(--gap-marker-fill,\s*#ffffff\);/);
  assert.doesNotMatch(gapRule, /background:\s*var\(--(?:surface-|theme-)/);
  assert.match(previewCss, /(?:^|\n)\.project-preview-gap-label\s*\{[^}]*color:\s*#000000;/);
  assert.match(previewCss, /:root\[data-theme="dark"\] \.project-preview-gap-label\s*\{[^}]*color:\s*#ffffff;/);
});

test("dark theme never paints over the Canvas band layer or the track surfaces", () => {
  const assemblyCss = readFileSync(new URL("../assembly.css", import.meta.url), "utf8");
  const subviewCss = readFileSync(new URL("../subview.css", import.meta.url), "utf8");

  // The Canvas band layer sits below the SVG overlay; an opaque themed
  // background on the overlay hides every collinearity band.
  assert.doesNotMatch(themeCss, /:root\[data-theme="dark"\][^{]*\.assembly-track-svg[^{]*\{[^}]*background/);
  assert.doesNotMatch(themeCss, /:root\[data-theme="dark"\][^{]*\.assembly-track-scroll[^{]*\{[^}]*background/);
  assert.doesNotMatch(themeCss, /:root\[data-theme="dark"\][^{]*\.subview-track-svg[^{]*\{[^}]*background/);
  assert.match(assemblyCss, /\[data-track-band-svg-overlay="1"\]\s*\{[^}]*background:\s*transparent;/);
  assert.match(subviewCss, /\.subview-track-svg\s*\{[^}]*background:\s*transparent;/);
  // Surfaces stay theme-aware through the shared tokens instead.
  assert.match(assemblyCss, /\.assembly-track-scroll\s*\{[^}]*background:\s*var\(--surface-panel,\s*#fff\);/);
  assert.match(assemblyCss, /\.assembly-track-svg\s*\{[^}]*background:\s*var\(--surface-panel,\s*#fff\);/);
});

test("preview Ref strip keeps the Assembly Ref palette and gains an outline for the dark canvas", () => {
  const previewCss = readFileSync(new URL("../project-preview.css", import.meta.url), "utf8");
  const rule = previewCss.match(/\.project-preview-reference\s*\{([^}]*)\}/)?.[1];
  assert.ok(rule);
  assert.match(rule, /background:\s*var\(--ctg-ref-fill\);/);
  assert.match(rule, /box-shadow:\s*inset 0 0 0 1px var\(--ctg-ref-stroke\);/);
  assert.match(rule, /height:\s*6px;/);
  assert.doesNotMatch(rule, /height:\s*4px;/);
  // No theme-specific override of the fill: role parity with the Assembly track.
  assert.doesNotMatch(themeCss, /:root\[data-theme="dark"\][^{]*\.project-preview-reference[^{]*\{[^}]*background/);
});

test("dataset editor fields, drop overlay, and loading curtains use theme-aware surfaces in dark mode", () => {
  const importerCss = readFileSync(new URL("../importer.css", import.meta.url), "utf8");
  const assemblyCss = readFileSync(new URL("../assembly.css", import.meta.url), "utf8");
  const subviewCss = readFileSync(new URL("../subview.css", import.meta.url), "utf8");

  assert.match(themeCss, /--theme-loading-scrim:\s*#101720bf;/);
  assert.match(
    importerCss,
    /\.project-dataset-editor input,\s*\.project-dataset-editor textarea\s*\{[^}]*background:\s*var\(--surface-panel,\s*#fff\);[^}]*color:\s*var\(--text-primary,\s*#1e293b\);/,
  );
  assert.match(
    importerCss,
    /\.project-drop-overlay\s*\{[^}]*background:\s*var\(--theme-translucent-surface,\s*rgba\(246,\s*249,\s*255,\s*0\.95\)\);/,
  );
  assert.match(
    assemblyCss,
    /\.assembly-loading-curtain\s*\{[^}]*background:\s*var\(--theme-loading-scrim,\s*rgba\(248,\s*248,\s*248,\s*0\.78\)\);/,
  );
  assert.match(
    subviewCss,
    /\.subview-pairwise-loading-overlay\s*\{[^}]*background:\s*var\(--theme-loading-scrim,\s*rgba\(248,\s*248,\s*248,\s*0\.72\)\);/,
  );
});


test("dark horizontal view navigation distinguishes the window, grid and draggable edges from the trough", () => {
  const css = readFileSync(new URL("../assembly.css", import.meta.url), "utf8");
  const darkToken = name => themeCss.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6});`))?.[1];
  const luminance = hex => {
    const rgb = hex.slice(1).match(/../g).map(value => parseInt(value, 16) / 255)
      .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05)
    / (Math.min(luminance(a), luminance(b)) + 0.05);
  for (const name of ["view-nav-window-fill", "view-nav-window-hover-fill", "view-nav-window-border", "view-nav-window-edge"]) {
    assert.ok(contrast(darkToken(name), darkToken("surface-subtle")) >= 3, name);
  }
  assert.notEqual(darkToken("view-nav-grid"), darkToken("surface-subtle"));
  assert.match(css, /\.view-nav-window\s*\{[^}]*border: 1px solid var\(--view-nav-window-border, #999\);[^}]*background: var\(--view-nav-window-fill, #d6d6d6\);/);
  assert.match(css, /\.view-nav-axis:hover \.view-nav-window\s*\{[^}]*background: var\(--view-nav-window-hover-fill, #c9c9c9\);/);
  assert.match(css, /\.view-nav-edge::after\s*\{[^}]*background: var\(--view-nav-window-edge, #666\);/);
  assert.match(css, /var\(--view-nav-grid, #eee\)/);
});
