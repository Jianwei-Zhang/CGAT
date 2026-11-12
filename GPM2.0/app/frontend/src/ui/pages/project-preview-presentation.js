import { getContigPalette } from "./assembly/contig-colors.js";

export const formatProjectPreviewBp = value => value >= 1000000 ? `${(value / 1000000).toFixed(3)} Mb`
  : value >= 1000 ? `${(value / 1000).toFixed(1)} kb` : `${Number(value).toLocaleString("en-US")} bp`;

// Read stable presentation styles, not hover/focus/viewport state. Geometry still
// comes from the complete semantic model, including unmounted chromosomes.
export function readProjectPreviewImageStyle(host) {
  const root = host?.ownerDocument?.documentElement || globalThis.document?.documentElement;
  const computed = node => node && typeof globalThis.getComputedStyle === "function" ? globalThis.getComputedStyle(node) : null;
  const rootStyle = computed(root);
  const style = selector => computed(host?.querySelector?.(selector));
  const card = style(".project-preview-card"), row = style(".project-preview-row");
  const source = style(".project-preview-contig"), reference = style(".project-preview-reference");
  const final = style(".project-preview-final-part");
  const number = (value, fallback) => Number.isFinite(parseFloat(value)) ? parseFloat(value) : fallback;
  const token = (name, fallback) => rootStyle?.getPropertyValue?.(name)?.trim() || fallback;
  const fontSize = number(rootStyle?.fontSize, 14);
  return {
    palette: getContigPalette(),
    fontFamily: rootStyle?.fontFamily || 'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif',
    fontSize: number(style(".project-preview-chr-name")?.fontSize, fontSize),
    labelSize: number(style(".project-preview-track-label")?.fontSize, fontSize * 0.929),
    graphSize: number(style(".project-preview-contig-label")?.fontSize, number(token("--graph-font-size", "12"), 12) * 0.917),
    radius: number(card?.borderTopLeftRadius, number(token("--card-radius", "6"), 6)),
    sourceRadius: number(source?.borderTopLeftRadius, 2),
    referenceRadius: number(reference?.borderTopLeftRadius, 3),
    finalRadius: number(final?.borderTopLeftRadius, 2),
    padding: number(card?.paddingLeft, 16),
    labelWidth: number(row?.gridTemplateColumns, 108),
    columnGap: number(row?.columnGap, 10),
    panel: token("--surface-panel", "#ffffff"),
    header: token("--surface-subtle", "#f8fafc"),
    border: token("--border-subtle", "#dbe3ec"),
    text: token("--text-primary", "#1e293b"),
    title: token("--theme-ink", "#0f172a"),
    muted: token("--text-muted", "#64748b"),
    axisText: token("--theme-muted-ink", "#89919a"),
    line: token("--theme-line", "#edf0f3"),
    selectionStroke: token("--final-path-selection-stroke", "#3b82f6"),
    pathLine: token("--theme-line", "#e8edf1"),
    gap: { fill: token("--gap-marker-fill", "#ffffff"), stroke: token("--border-strong", "#94a3b8"), text: token("--gap-marker-text", "#1b1b1b") },
    warning: token("--theme-amber-ink", "#8a612d"),
    shadow: root?.dataset?.theme === "dark" ? "0.2" : "0.04",
  };
}
