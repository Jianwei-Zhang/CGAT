import { MAX_IMPORT_PARSER_WORKERS, MIN_IMPORT_PARSER_WORKERS } from "./import-parallelism.js";
import {
  DEFAULT_TRACK_COLOR_OVERRIDES,
  applyTrackColorVariables,
  normalizeTrackColors,
  trackColorsEqual,
} from "./track-colors.js";

export const APP_SETTINGS_KEY = "gpm_next:app_settings";
export const PROJECT_SIDEBAR_WIDTH_KEY = "gpm.project-library-width";
export const PROJECT_SIDEBAR_COLLAPSED_KEY = "gpm.project-library-collapsed";
export const SUBVIEW_TOOLS_PREFS_KEY = "gpm.subviewTools.v1";

export const DEFAULT_APP_SETTINGS = Object.freeze({
  theme: "system",
  fontSize: 14,
  graphFontSize: null,
  trackColors: DEFAULT_TRACK_COLOR_OVERRIDES,
  historyCapacity: 0,
  restoreLastWorkspace: true,
  defaultWorkspaceRoot: "",
  importParallelism: "auto",
  localViewDefaultMode: "docked",
  localViewDefaultPinned: true,
  deleteHotkeyEnabled: true,
  autoCheckUpdates: true,
});

function normalizeImportParallelismSetting(value) {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text || text === "auto") return "auto";
  if (/^\d+$/.test(text)) {
    const parsed = Number(text);
    if (Number.isInteger(parsed) && parsed >= MIN_IMPORT_PARSER_WORKERS && parsed <= MAX_IMPORT_PARSER_WORKERS) {
      return String(parsed);
    }
  }
  return "auto";
}

export function normalizeAppSettings(value = {}) {
  return {
    theme: ["system", "light", "dark"].includes(value?.theme) ? value.theme : "system",
    fontSize: [12, 14, 16, 18].includes(value?.fontSize) ? value.fontSize : 14,
    graphFontSize: [10, 12, 14, 16].includes(value?.graphFontSize) ? value.graphFontSize : null,
    trackColors: normalizeTrackColors(value?.trackColors),
    historyCapacity: Number.isSafeInteger(value?.historyCapacity) && value.historyCapacity >= 0
      && value.historyCapacity <= 1000000 ? value.historyCapacity : 0,
    restoreLastWorkspace: typeof value?.restoreLastWorkspace === "boolean" ? value.restoreLastWorkspace : true,
    defaultWorkspaceRoot: typeof value?.defaultWorkspaceRoot === "string" ? value.defaultWorkspaceRoot.trim() : "",
    importParallelism: normalizeImportParallelismSetting(value?.importParallelism),
    localViewDefaultMode: value?.localViewDefaultMode === "floating" ? "floating" : "docked",
    localViewDefaultPinned: typeof value?.localViewDefaultPinned === "boolean" ? value.localViewDefaultPinned : true,
    deleteHotkeyEnabled: typeof value?.deleteHotkeyEnabled === "boolean" ? value.deleteHotkeyEnabled : true,
    autoCheckUpdates: typeof value?.autoCheckUpdates === "boolean" ? value.autoCheckUpdates : true,
  };
}

export function resetAppLayoutPreferences(storage = globalThis.localStorage) {
  storage?.removeItem?.(PROJECT_SIDEBAR_WIDTH_KEY);
  storage?.removeItem?.(PROJECT_SIDEBAR_COLLAPSED_KEY);
  storage?.removeItem?.(SUBVIEW_TOOLS_PREFS_KEY);
}

function readSettings() {
  try { return normalizeAppSettings(JSON.parse(globalThis.localStorage?.getItem(APP_SETTINGS_KEY) || "{}")); }
  catch { return { ...DEFAULT_APP_SETTINGS, trackColors: { ...DEFAULT_TRACK_COLOR_OVERRIDES } }; }
}
let current = readSettings();
export function getAppSettings() { return { ...current, trackColors: { ...current.trackColors } }; }
export function setAppSettings(value, { persist = true } = {}) {
  const next = normalizeAppSettings(value);
  const trackColorsChanged = !trackColorsEqual(current.trackColors, next.trackColors);
  // Persist before changing runtime state: storage failures must remain visible to the user.
  if (persist) globalThis.localStorage?.setItem(APP_SETTINGS_KEY, JSON.stringify(next));
  current = next;
  applyAppTypography();
  applyAppTheme(globalThis.document?.documentElement, undefined, { forceNotify: trackColorsChanged });
  return getAppSettings();
}
export function getHistoryCapacity() { return current.historyCapacity; }
export function retainHistoryEntries(entries) {
  return current.historyCapacity === 0 ? entries : entries.slice(-current.historyCapacity);
}
export function getGraphFontSize() { return current.graphFontSize ?? current.fontSize * 12 / 14; }
export function getGraphTextScale() { return getGraphFontSize() / 10; }
export function applyAppTypography(root = globalThis.document?.documentElement) {
  if (!root) return;
  root.style.setProperty("--app-font-size", `${current.fontSize}px`);
  root.style.setProperty("--graph-font-size", `${getGraphFontSize()}px`);
}
// Conservative fallback also handles CJK identifiers, which are wider than Latin text.
export function estimateGraphTextWidth(text, characterWidth = 6.2) {
  return Math.max(10, [...String(text || "")].reduce((width, char) =>
    width + (char.codePointAt(0) > 255 ? 10 : characterWidth), 0)) * getGraphTextScale();
}

export function resolveAppTheme(preference, systemDark = false) {
  return preference === "dark" || (preference !== "light" && systemDark) ? "dark" : "light";
}

export function resolveNativeWindowTheme(preference) {
  return preference === "dark" ? "dark" : preference === "light" ? "light" : null;
}

let appliedTheme = null;
let lastNativeWindowTheme = undefined;
const themeSubscribers = new Set();

export function syncNativeWindowTheme(preference = current.theme, { force = false } = {}) {
  const target = resolveNativeWindowTheme(preference);
  const nativeWindow = globalThis.window?.__TAURI__?.window?.getCurrentWindow?.();
  if (typeof nativeWindow?.setTheme !== "function") return target;
  if (!force && target === lastNativeWindowTheme) return target;
  lastNativeWindowTheme = target;
  void Promise.resolve(nativeWindow.setTheme(target)).catch(() => {});
  return target;
}

// Theme changes repaint SVG/Canvas series colours, so mounted views subscribe
// once instead of each module watching matchMedia on its own.
export function subscribeAppTheme(listener) {
  if (typeof listener !== "function") return () => {};
  themeSubscribers.add(listener);
  return () => themeSubscribers.delete(listener);
}

export function getAppliedAppTheme() { return appliedTheme; }

export function applyAppTrackColors(root = globalThis.document?.documentElement, theme = appliedTheme) {
  applyTrackColorVariables(root, current.trackColors, { dark: theme === "dark" });
}

export function applyAppTheme(root = globalThis.document?.documentElement, systemDark, { forceNotify = false } = {}) {
  const dark = systemDark ?? globalThis.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? false;
  const theme = resolveAppTheme(current.theme, dark);
  if (root) root.dataset.theme = theme;
  applyAppTrackColors(root, theme);
  syncNativeWindowTheme(current.theme);
  if (theme !== appliedTheme || forceNotify) {
    const previous = appliedTheme;
    appliedTheme = theme;
    for (const listener of [...themeSubscribers]) {
      try {
        listener(theme, previous);
      } catch {
        // A subscriber failure must not block the theme switch itself.
      }
    }
  }
  return theme;
}

// Only system-following settings react to live OS changes. No route rerender is
// needed: every screen, SVG and open dialog inherits the same theme tokens.
export function initializeAppTheme({ root = globalThis.document?.documentElement,
  matchMedia = globalThis.matchMedia?.bind(globalThis) } = {}) {
  const media = matchMedia?.("(prefers-color-scheme: dark)");
  const update = () => applyAppTheme(root, media?.matches ?? false);
  update();
  media?.addEventListener?.("change", update);
  return () => media?.removeEventListener?.("change", update);
}
