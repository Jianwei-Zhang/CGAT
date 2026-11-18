// Content-sized toolbar inputs only. Never change values, focus or app state.
const contexts = new WeakMap();
const TOOLBAR = ":is([data-main-track-toolbar], [data-subview-toolbar])";
export const TOOLBAR_INPUT_MIN_WIDTH = 44;
export const TOOLBAR_INPUT_MAX_WIDTH = 140;
export const TOOLBAR_DATASET_MAX_WIDTH = 180;
const pixels = value => Number.parseFloat(value) || 0;

export function resolveToolbarControlWidth(textWidth, chromeWidth, { support = false } = {}) {
  const width = Math.ceil(Math.max(0, Number(textWidth) || 0) + Math.max(0, Number(chromeWidth) || 0) + 2);
  return Math.max(TOOLBAR_INPUT_MIN_WIDTH,
    Math.min(support ? TOOLBAR_DATASET_MAX_WIDTH : TOOLBAR_INPUT_MAX_WIDTH, width));
}

export function syncToolbarControlWidth(combo) {
  if (!combo?.closest?.(TOOLBAR)) return false;
  const control = combo.querySelector?.(".assembly-track-combo-input, .assembly-support-dataset-toggle");
  const doc = combo.ownerDocument;
  const win = doc?.defaultView;
  if (!control || !win?.getComputedStyle || !combo.style?.setProperty) return false;
  let context = contexts.get(doc);
  if (!context) {
    context = doc.createElement?.("canvas")?.getContext?.("2d");
    if (!context) return false;
    contexts.set(doc, context);
  }
  const style = win.getComputedStyle(control), shell = win.getComputedStyle(combo);
  context.font = style.font || `${style.fontWeight || "400"} ${style.fontSize || "13px"} ${style.fontFamily || "sans-serif"}`;
  const support = combo.dataset?.trackComboField === "supportDatasetId";
  const value = String((support ? control.textContent : control.value) ?? "");
  const textWidth = context.measureText(value).width
    + Math.max(0, [...value].length - 1) * pixels(style.letterSpacing);
  // The arrow is absolute; its clearance is already in input padding-right.
  const chromeWidth = pixels(style.paddingLeft) + pixels(style.paddingRight)
    + pixels(style.borderLeftWidth) + pixels(style.borderRightWidth)
    + pixels(shell.borderLeftWidth) + pixels(shell.borderRightWidth);
  const width = resolveToolbarControlWidth(textWidth, chromeWidth,
    { support });
  combo.style.setProperty("--toolbar-combo-width", `${width}px`);
  return true;
}

export function syncToolbarControlWidths(host) {
  for (const combo of host?.querySelectorAll?.(`${TOOLBAR} [data-track-combo-field]`) || []) syncToolbarControlWidth(combo);
}
