// Shared biological track & overlay color customization, derivation, and presets.
// Users pick one base hex color per role; light/dark fills, strokes, readable
// contrast ink, alignment band ramps, and white-canvas export palettes are
// derived automatically so tracks stay legible in both themes and exports.

export const TRACK_COLOR_KEYS = Object.freeze(["primary", "companion", "ref", "selection", "grt"]);

export const DEFAULT_TRACK_COLOR_OVERRIDES = Object.freeze({
  primary: null,
  companion: null,
  ref: null,
  selection: null,
  grt: null,
});

export const DEFAULT_TRACK_BASE_COLORS = Object.freeze({
  primary: "#d2dfef",
  companion: "#e7dec4",
  ref: "#cfcfcf",
  selection: "#c2410c",
  grt: "#6c8f78",
});

export const TRACK_COLOR_PRESETS = Object.freeze([
  Object.freeze({
    id: "default",
    colors: DEFAULT_TRACK_COLOR_OVERRIDES,
    swatches: Object.freeze(["#d2dfef", "#e7dec4", "#cfcfcf", "#c2410c", "#6c8f78"]),
  }),
  Object.freeze({
    id: "okabe",
    colors: Object.freeze({
      primary: "#56b4e9",
      companion: "#e69f00",
      ref: "#cbd5e1",
      selection: "#cc79a7",
      grt: "#009e73",
    }),
    swatches: Object.freeze(["#56b4e9", "#e69f00", "#cbd5e1", "#cc79a7", "#009e73"]),
  }),
  Object.freeze({
    id: "nature",
    colors: Object.freeze({
      primary: "#8491b4",
      companion: "#f39b7f",
      ref: "#d5d9de",
      selection: "#e64b35",
      grt: "#00a087",
    }),
    swatches: Object.freeze(["#8491b4", "#f39b7f", "#d5d9de", "#e64b35", "#00a087"]),
  }),
  Object.freeze({
    id: "vivid",
    colors: Object.freeze({
      primary: "#93c5fd",
      companion: "#fcd34d",
      ref: "#d1d5db",
      selection: "#dc2626",
      grt: "#16a34a",
    }),
    swatches: Object.freeze(["#93c5fd", "#fcd34d", "#d1d5db", "#dc2626", "#16a34a"]),
  }),
]);

export const TRACK_COLOR_CSS_VARS = Object.freeze([
  "--ctg-primary-fill",
  "--ctg-primary-stroke",
  "--ctg-primary-text",
  "--ctg-companion-fill",
  "--ctg-companion-stroke",
  "--ctg-companion-text",
  "--ctg-ref-fill",
  "--ctg-ref-stroke",
  "--ctg-ref-text",
  "--final-path-selection-stroke",
  "--final-path-selection-fill",
  "--preview-selection-fill",
  "--alignment-legend-primary-low",
  "--alignment-legend-primary-high",
  "--alignment-legend-companion-low",
  "--alignment-legend-companion-high",
  "--grt-result-mask",
  "--grt-result-fill",
  "--grt-result-stroke",
]);

const HEX_COLOR_RE = /^#[0-9a-f]{6}$/i;

export function normalizeHexColor(value) {
  const text = String(value ?? "").trim();
  if (!HEX_COLOR_RE.test(text)) return null;
  return text.toLowerCase();
}

export function normalizeTrackColors(value) {
  const input = value && typeof value === "object" ? value : {};
  const result = {};
  for (const key of TRACK_COLOR_KEYS) {
    const hex = normalizeHexColor(input[key]);
    result[key] = hex && hex !== DEFAULT_TRACK_BASE_COLORS[key] ? hex : null;
  }
  return result;
}

export function trackColorsEqual(left, right) {
  const a = normalizeTrackColors(left);
  const b = normalizeTrackColors(right);
  return TRACK_COLOR_KEYS.every((key) => a[key] === b[key]);
}

export function hasCustomTrackColors(trackColors) {
  const normalized = normalizeTrackColors(trackColors);
  return TRACK_COLOR_KEYS.some((key) => normalized[key] !== null);
}

export function resolveEffectiveTrackBaseColors(trackColors) {
  const normalized = normalizeTrackColors(trackColors);
  return Object.fromEntries(
    TRACK_COLOR_KEYS.map((key) => [key, normalized[key] || DEFAULT_TRACK_BASE_COLORS[key]]),
  );
}

export function detectTrackColorPreset(trackColors) {
  const normalized = normalizeTrackColors(trackColors);
  const matched = TRACK_COLOR_PRESETS.find((preset) => trackColorsEqual(preset.colors, normalized));
  return matched ? matched.id : "custom";
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function hexToRgb(hex) {
  const normalized = normalizeHexColor(hex);
  if (!normalized) return [0, 0, 0];
  return [
    Number.parseInt(normalized.slice(1, 3), 16),
    Number.parseInt(normalized.slice(3, 5), 16),
    Number.parseInt(normalized.slice(5, 7), 16),
  ];
}

export function rgbToHex(r, g, b) {
  const channel = (v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, "0");
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

export function rgbToHsl(r, g, b) {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = 0;
  if (max === rn) h = (gn - bn) / d + (gn < bn ? 6 : 0);
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return [h * 60, s, l];
}

export function hslToRgb(h, s, l) {
  const hue = ((h % 360) + 360) % 360;
  const sat = clamp(s, 0, 1);
  const lig = clamp(l, 0, 1);
  if (sat === 0) {
    const gray = Math.round(lig * 255);
    return [gray, gray, gray];
  }
  const q = lig < 0.5 ? lig * (1 + sat) : lig + sat - lig * sat;
  const p = 2 * lig - q;
  const hueToChannel = (t) => {
    let x = t;
    if (x < 0) x += 1;
    if (x > 1) x -= 1;
    if (x < 1 / 6) return p + (q - p) * 6 * x;
    if (x < 1 / 2) return q;
    if (x < 2 / 3) return p + (q - p) * (2 / 3 - x) * 6;
    return p;
  };
  const hk = hue / 360;
  return [
    Math.round(hueToChannel(hk + 1 / 3) * 255),
    Math.round(hueToChannel(hk) * 255),
    Math.round(hueToChannel(hk - 1 / 3) * 255),
  ];
}

function relativeLuminance(r, g, b) {
  const toLinear = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
}

function contrastRatio(rgbA, rgbB) {
  const lumA = relativeLuminance(...rgbA);
  const lumB = relativeLuminance(...rgbB);
  const lighter = Math.max(lumA, lumB);
  const darker = Math.min(lumA, lumB);
  return (lighter + 0.05) / (darker + 0.05);
}

export function deriveContigRoleColors(hex, { dark = false } = {}) {
  const normalized = normalizeHexColor(hex) || "#d2dfef";
  const rgb = hexToRgb(normalized);
  const [h, s, l] = rgbToHsl(...rgb);
  const isNeutral = s < 0.08;

  if (!dark) {
    const fill = normalized;
    const strokeL = l > 0.52 ? clamp(l - 0.30, 0.26, 0.58) : clamp(l * 0.72, 0.14, 0.42);
    const strokeS = isNeutral ? s : clamp(s * 0.88, 0.18, 0.78);
    const stroke = rgbToHex(...hslToRgb(h, strokeS, strokeL));

    const fillLum = relativeLuminance(...rgb);
    let textRgb;
    if (fillLum > 0.34) {
      textRgb = hslToRgb(h, isNeutral ? 0 : Math.min(s, 0.50), 0.20);
      if (contrastRatio(rgb, textRgb) < 4.5) textRgb = [17, 24, 39];
    } else {
      textRgb = [248, 250, 252];
      if (contrastRatio(rgb, textRgb) < 4.5) textRgb = [255, 255, 255];
    }
    return { fill, stroke, text: rgbToHex(...textRgb) };
  }

  // Dark canvas (#17212e): map user hue to a calm mid-dark fill with crisp border & light ink.
  const darkFillL = isNeutral ? 0.27 : clamp(0.24 + l * 0.16, 0.25, 0.38);
  const darkFillS = isNeutral ? clamp(s, 0, 0.14) : clamp(s * 0.78, 0.24, 0.62);
  const darkFillRgb = hslToRgb(h, darkFillS, darkFillL);

  const darkStrokeL = isNeutral ? 0.58 : clamp(darkFillL + 0.28, 0.54, 0.68);
  const darkStrokeS = isNeutral ? clamp(s, 0, 0.16) : clamp(s * 0.88, 0.32, 0.74);
  const darkStrokeRgb = hslToRgb(h, darkStrokeS, darkStrokeL);

  let darkTextRgb = hslToRgb(h, isNeutral ? 0.08 : Math.min(s, 0.42), 0.93);
  if (contrastRatio(darkFillRgb, darkTextRgb) < 4.5) darkTextRgb = [241, 245, 249];

  return {
    fill: rgbToHex(...darkFillRgb),
    stroke: rgbToHex(...darkStrokeRgb),
    text: rgbToHex(...darkTextRgb),
  };
}

export function deriveAlignmentBandBaseRgb(hex, { dark = false } = {}) {
  const normalized = normalizeHexColor(hex);
  if (!normalized) return null;
  const [h, s] = rgbToHsl(...hexToRgb(normalized));
  const isNeutral = s < 0.08;
  if (!dark) {
    return hslToRgb(h, isNeutral ? s : clamp(s, 0.28, 0.62), 0.50);
  }
  return hslToRgb(h, isNeutral ? s : clamp(s, 0.34, 0.70), 0.60);
}

function blendBandRgba(baseRgb, canvasRgb, strength, alpha = 0.62) {
  const blended = baseRgb.map((channel, index) => Math.round(canvasRgb[index] + (channel - canvasRgb[index]) * strength));
  return `rgba(${blended.join(", ")}, ${alpha})`;
}

export function deriveSelectionColors(hex, { dark = false } = {}) {
  const normalized = normalizeHexColor(hex);
  if (!normalized) return null;
  const rgb = hexToRgb(normalized);
  if (!dark) {
    return {
      stroke: normalized,
      fill: `rgba(${rgb.join(", ")}, 0.22)`,
      previewFill: `rgba(${rgb.join(", ")}, 0.10)`,
    };
  }
  const [h, s, l] = rgbToHsl(...rgb);
  const darkRgb = l < 0.54 ? hslToRgb(h, clamp(s, 0.45, 0.92), 0.64) : rgb;
  return {
    stroke: rgbToHex(...darkRgb),
    fill: `rgba(${darkRgb.join(", ")}, 0.24)`,
    previewFill: `rgba(${darkRgb.join(", ")}, 0.12)`,
  };
}

export function deriveGrtResultColors(hex, { dark = false } = {}) {
  const normalized = normalizeHexColor(hex);
  if (!normalized) return null;
  const rgb = hexToRgb(normalized);
  const [h, s, l] = rgbToHsl(...rgb);
  if (!dark) {
    const stroke = rgbToHex(...hslToRgb(h, clamp(s, 0.16, 0.75), clamp(l - 0.10, 0.26, 0.52)));
    return {
      mask: `rgba(${rgb.join(", ")}, 0.14)`,
      fill: `rgba(${rgb.join(", ")}, 0.36)`,
      stroke,
    };
  }
  const darkRgb = hslToRgb(h, clamp(s, 0.22, 0.68), clamp(l, 0.46, 0.62));
  return {
    mask: `rgba(${darkRgb.join(", ")}, 0.16)`,
    fill: `rgba(${darkRgb.join(", ")}, 0.30)`,
    stroke: rgbToHex(...hslToRgb(h, clamp(s, 0.25, 0.72), clamp(l + 0.10, 0.54, 0.70))),
  };
}

export function buildTrackColorCssVariables(trackColors, { dark = false } = {}) {
  const normalized = normalizeTrackColors(trackColors);
  const vars = {};

  for (const role of ["primary", "companion", "ref"]) {
    const hex = normalized[role];
    if (hex) {
      const derived = deriveContigRoleColors(hex, { dark });
      vars[`--ctg-${role}-fill`] = derived.fill;
      vars[`--ctg-${role}-stroke`] = derived.stroke;
      vars[`--ctg-${role}-text`] = derived.text;
    } else {
      vars[`--ctg-${role}-fill`] = null;
      vars[`--ctg-${role}-stroke`] = null;
      vars[`--ctg-${role}-text`] = null;
    }
  }

  const canvas = dark ? [23, 33, 46] : [255, 255, 255];
  const lowStrength = dark ? 0.30 : 0.18;
  const highStrength = dark ? 0.80 : 0.68;
  for (const tone of ["primary", "companion"]) {
    const hex = normalized[tone];
    if (hex) {
      const baseRgb = deriveAlignmentBandBaseRgb(hex, { dark });
      vars[`--alignment-legend-${tone}-low`] = blendBandRgba(baseRgb, canvas, lowStrength);
      vars[`--alignment-legend-${tone}-high`] = blendBandRgba(baseRgb, canvas, highStrength);
    } else {
      vars[`--alignment-legend-${tone}-low`] = null;
      vars[`--alignment-legend-${tone}-high`] = null;
    }
  }

  const selection = normalized.selection ? deriveSelectionColors(normalized.selection, { dark }) : null;
  vars["--final-path-selection-stroke"] = selection ? selection.stroke : null;
  vars["--final-path-selection-fill"] = selection ? selection.fill : null;
  vars["--preview-selection-fill"] = selection ? selection.previewFill : null;

  const grt = normalized.grt ? deriveGrtResultColors(normalized.grt, { dark }) : null;
  vars["--grt-result-mask"] = grt ? grt.mask : null;
  vars["--grt-result-fill"] = grt ? grt.fill : null;
  vars["--grt-result-stroke"] = grt ? grt.stroke : null;

  return vars;
}

export function applyTrackColorVariables(root, trackColors, { dark = false } = {}) {
  if (!root?.style) return;
  const vars = buildTrackColorCssVariables(trackColors, { dark });
  for (const [name, value] of Object.entries(vars)) {
    if (value) root.style.setProperty?.(name, value);
    else root.style.removeProperty?.(name);
  }
}
