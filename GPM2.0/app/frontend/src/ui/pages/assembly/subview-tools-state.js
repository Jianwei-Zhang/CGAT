export const SUBVIEW_TOOLS_STORAGE_KEY = "gpm.subviewTools.v1";
export const SUBVIEW_TOOLS_ID = "subview-tools";
export const SUBVIEW_TOOLS_TABS = Object.freeze(["anchors", "composition"]);

export function normalizeSubviewToolsPreferences(value) {
  const source = value?.version === 1 ? value : {};
  const rect = source.rect;
  const validRect = rect && ["left", "top", "width", "height"].every(
    (key) => typeof rect[key] === "number" && Number.isFinite(rect[key]),
  ) && rect.width > 0 && rect.height > 0;
  return {
    version: 1,
    open: source.open === true,
    tab: SUBVIEW_TOOLS_TABS.includes(source.tab) ? source.tab : "anchors",
    rect: validRect
      ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height }
      : null,
  };
}

export function constrainSubviewToolsRect(rect, viewport, anchor = null) {
  const availableWidth = Math.max(1, Number(viewport.width) || 1);
  const availableHeight = Math.max(1, Number(viewport.height) || 1);
  const marginX = Math.min(8, Math.max(0, (availableWidth - 1) / 2));
  const marginY = Math.min(8, Math.max(0, (availableHeight - 1) / 2));
  const leftEdge = (Number(viewport.left) || 0) + marginX;
  const topEdge = (Number(viewport.top) || 0) + marginY;
  const maxWidth = Math.min(420, availableWidth - marginX * 2);
  const maxHeight = availableHeight - marginY * 2;
  const width = Math.min(maxWidth, Math.max(Math.min(280, maxWidth), rect?.width ?? 320));
  const height = Math.min(maxHeight, Math.max(Math.min(220, maxHeight), rect?.height ?? 420));
  return {
    left: Math.max(leftEdge, Math.min(rect?.left ?? ((anchor?.right ?? availableWidth) - width - 8),
      leftEdge + availableWidth - marginX * 2 - width)),
    top: Math.max(topEdge, Math.min(rect?.top ?? ((anchor?.top ?? topEdge) + 36),
      topEdge + availableHeight - marginY * 2 - height)),
    width,
    height,
  };
}

export function buildSubviewToolsScopeKey(state) {
  return JSON.stringify([
    state?.session?.workspacePath || "", state?.session?.projectId ?? null,
    state?.assembly?.selectedChrName || "",
  ]);
}

export function isSubviewToolsPageVisible(state) {
  return (state?.activeRoute ?? "assembly") === "assembly"
    && state?.assembly?.activeTab === "assembly";
}

export function resolveSubviewToolsTabKey(current, key) {
  const index = SUBVIEW_TOOLS_TABS.indexOf(current);
  if (key === "Home") return SUBVIEW_TOOLS_TABS[0];
  if (key === "End") return SUBVIEW_TOOLS_TABS.at(-1);
  if (key === "ArrowRight" || key === "ArrowLeft") {
    return SUBVIEW_TOOLS_TABS[(index + (key === "ArrowRight" ? 1 : -1)
      + SUBVIEW_TOOLS_TABS.length) % SUBVIEW_TOOLS_TABS.length];
  }
  return current;
}
