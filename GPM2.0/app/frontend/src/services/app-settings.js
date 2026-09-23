export const APP_SETTINGS_KEY = "gpm_next:app_settings";
export const DEFAULT_APP_SETTINGS = Object.freeze({ fontSize: 14, graphFontSize: null, historyCapacity: 50 });

export function normalizeAppSettings(value = {}) {
  return {
    fontSize: [12, 14, 16, 18].includes(value?.fontSize) ? value.fontSize : 14,
    graphFontSize: [10, 12, 14, 16].includes(value?.graphFontSize) ? value.graphFontSize : null,
    historyCapacity: Number.isSafeInteger(value?.historyCapacity) && value.historyCapacity >= 0
      && value.historyCapacity <= 1000000 ? value.historyCapacity : 50,
  };
}

function readSettings() {
  try { return normalizeAppSettings(JSON.parse(globalThis.localStorage?.getItem(APP_SETTINGS_KEY) || "{}")); }
  catch { return { ...DEFAULT_APP_SETTINGS }; }
}
let current = readSettings();
export function getAppSettings() { return { ...current }; }
export function setAppSettings(value, { persist = true } = {}) {
  const next = normalizeAppSettings(value);
  // Persist before changing runtime state: storage failures must remain visible to the user.
  if (persist) globalThis.localStorage?.setItem(APP_SETTINGS_KEY, JSON.stringify(next));
  current = next;
  applyAppTypography();
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
