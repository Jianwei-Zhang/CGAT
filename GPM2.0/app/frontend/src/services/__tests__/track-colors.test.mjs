import test from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_TRACK_BASE_COLORS,
  DEFAULT_TRACK_COLOR_OVERRIDES,
  TRACK_COLOR_KEYS,
  TRACK_COLOR_PRESETS,
  applyTrackColorVariables,
  buildTrackColorCssVariables,
  deriveAlignmentBandBaseRgb,
  deriveContigRoleColors,
  detectTrackColorPreset,
  hasCustomTrackColors,
  normalizeHexColor,
  normalizeTrackColors,
} from "../track-colors.js";
import { DEFAULT_APP_SETTINGS, setAppSettings, subscribeAppTheme } from "../app-settings.js";
import { getContigPalette } from "../../ui/pages/assembly/contig-colors.js";
import { resolveAlignmentBandStyle, resolveDarkAlignmentBandStyle } from "../../ui/pages/assembly/alignment-band-style.js";

test("normalizeTrackColors validates hex strings and collapses defaults to null", () => {
  assert.deepEqual(normalizeTrackColors(null), DEFAULT_TRACK_COLOR_OVERRIDES);
  assert.deepEqual(normalizeTrackColors({
    primary: "#D2DFEF",
    companion: "  #E69F00 ",
    ref: "invalid",
    selection: "#fff",
    grt: "#009E73",
  }), {
    primary: null,
    companion: "#e69f00",
    ref: null,
    selection: null,
    grt: "#009e73",
  });
  assert.equal(normalizeHexColor("#AbCdEf"), "#abcdef");
  assert.equal(normalizeHexColor("rgb(0,0,0)"), null);
});

test("preset detection matches built-in palettes and reports custom when modified", () => {
  assert.equal(detectTrackColorPreset(DEFAULT_TRACK_COLOR_OVERRIDES), "default");
  assert.equal(hasCustomTrackColors(DEFAULT_TRACK_COLOR_OVERRIDES), false);
  for (const preset of TRACK_COLOR_PRESETS) {
    assert.equal(detectTrackColorPreset(preset.colors), preset.id);
  }
  assert.equal(detectTrackColorPreset({ primary: "#123456" }), "custom");
  assert.equal(hasCustomTrackColors({ primary: "#123456" }), true);
});

test("deriveContigRoleColors generates readable light and dark triplets from any base hex", () => {
  for (const hex of ["#56b4e9", "#1d4ed8", "#facc15", "#111827", "#cbd5e1"]) {
    const light = deriveContigRoleColors(hex, { dark: false });
    assert.equal(light.fill, hex);
    assert.match(light.stroke, /^#[0-9a-f]{6}$/);
    assert.match(light.text, /^#[0-9a-f]{6}$/);
    assert.notEqual(light.fill, light.text);

    const dark = deriveContigRoleColors(hex, { dark: true });
    assert.match(dark.fill, /^#[0-9a-f]{6}$/);
    assert.match(dark.stroke, /^#[0-9a-f]{6}$/);
    assert.match(dark.text, /^#[0-9a-f]{6}$/);
    assert.notEqual(dark.fill, dark.text);
  }
});

test("applyTrackColorVariables sets custom CSS tokens and removes cleared defaults", () => {
  const props = new Map();
  const root = {
    style: {
      setProperty: (k, v) => props.set(k, v),
      removeProperty: (k) => props.delete(k),
    },
  };
  const okabe = TRACK_COLOR_PRESETS.find((item) => item.id === "okabe");
  applyTrackColorVariables(root, okabe.colors, { dark: false });
  assert.equal(props.get("--ctg-primary-fill"), "#56b4e9");
  assert.equal(props.get("--final-path-selection-stroke"), "#cc79a7");
  assert.ok(props.get("--alignment-legend-primary-high")?.startsWith("rgba("));
  assert.ok(props.get("--grt-result-fill")?.startsWith("rgba("));

  // Clearing back to default removes all inline overrides so base.css/theme.css govern.
  applyTrackColorVariables(root, DEFAULT_TRACK_COLOR_OVERRIDES, { dark: false });
  assert.equal(props.size, 0);
  const vars = buildTrackColorCssVariables(DEFAULT_TRACK_COLOR_OVERRIDES, { dark: true });
  assert.ok(Object.values(vars).every((value) => value === null));
});

test("custom track colors update publication exports, alignment bands, and notify theme subscribers", () => {
  const originalDocument = globalThis.document;
  const props = new Map();
  const root = {
    dataset: { theme: "dark" },
    style: {
      setProperty: (k, v) => props.set(k, v),
      removeProperty: (k) => props.delete(k),
    },
  };
  let notifications = 0;
  const unsubscribe = subscribeAppTheme(() => { notifications += 1; });
  try {
    globalThis.document = { documentElement: root };
    const defaultBand = resolveAlignmentBandStyle("primary", 95);
    const defaultDarkBand = resolveDarkAlignmentBandStyle("primary", 95);

    setAppSettings({
      ...DEFAULT_APP_SETTINGS,
      theme: "dark",
      trackColors: { ...DEFAULT_TRACK_COLOR_OVERRIDES, primary: "#22c55e", companion: "#f97316" },
    }, { persist: false });

    assert.ok(notifications >= 1);
    // White-canvas export palette reflects custom colors even while UI is in dark mode.
    const exportPalette = getContigPalette();
    assert.equal(exportPalette.primary.fill, "#22c55e");
    assert.equal(exportPalette.companion.fill, "#f97316");
    assert.equal(exportPalette.ref.fill, DEFAULT_TRACK_BASE_COLORS.ref);

    // Alignment band ramps follow the custom track hues in both light and dark modes.
    assert.notDeepEqual(resolveAlignmentBandStyle("primary", 95), defaultBand);
    assert.notDeepEqual(resolveDarkAlignmentBandStyle("primary", 95), defaultDarkBand);
    assert.ok(Array.isArray(deriveAlignmentBandBaseRgb("#22c55e", { dark: false })));
    assert.equal(TRACK_COLOR_KEYS.length, 5);
  } finally {
    unsubscribe();
    setAppSettings(DEFAULT_APP_SETTINGS, { persist: false });
    globalThis.document = originalDocument;
  }
});
