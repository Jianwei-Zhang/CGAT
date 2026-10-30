// Resolve painted object colours, not a coarse primary/companion palette.
// Canvas hit proxies retain their opaque paint in the alignment custom properties.
export function parseTooltipColor(value) {
  const text = String(value || "").trim().toLowerCase();
  if (!text || ["none", "transparent"].includes(text)) return null;
  const hex = text.match(/^#([\da-f]{3,8})$/i)?.[1];
  if (hex && [3, 4, 6, 8].includes(hex.length)) {
    const full = hex.length < 5 ? [...hex].map(c => c + c).join("") : hex;
    return [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16)).concat(full.length === 8 ? parseInt(full.slice(6), 16) / 255 : 1);
  }
  const rgb = text.match(/^rgba?\((.*)\)$/)?.[1];
  const srgb = text.match(/^color\(srgb\s+(.*)\)$/)?.[1];
  if (rgb || srgb) {
    const parts = (rgb || srgb).replaceAll(",", " ").replace("/", " ").trim().split(/\s+/);
    const channels = parts.slice(0, 3).map(v => parseFloat(v) * (v.endsWith("%") ? 2.55 : srgb ? 255 : 1));
    const alpha = parts[3] === undefined ? 1 : parseFloat(parts[3]) / (parts[3].endsWith("%") ? 100 : 1);
    if (channels.length === 3 && [...channels, alpha].every(Number.isFinite)) return [...channels, Math.max(0, Math.min(1, alpha))];
  }
  return ({ white: [255, 255, 255, 1], black: [0, 0, 0, 1], red: [255, 0, 0, 1] })[text] || null;
}

export function compositeTooltipColor(front, back) {
  if (!front) return back;
  if (!back) return front;
  const alpha = front[3] + back[3] * (1 - front[3]);
  return alpha ? front.slice(0, 3).map((c, i) => (c * front[3] + back[i] * back[3] * (1 - front[3])) / alpha).concat(alpha) : [0, 0, 0, 0];
}
const cssRgb = color => `rgb(${color.slice(0, 3).map(Math.round).join(", ")})`;
const luminance = rgb => rgb.slice(0, 3).map(v => {
  v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
}).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
const number = value => value === undefined || value === "" ? 1 : Number.isFinite(Number(value)) ? Number(value) : 1;

export function resolveTooltipColors(node, { getStyle, dark = false } = {}) {
  const read = element => element && (getStyle?.(element) || element.style || {});
  const defaultColors = dark
    ? { background: "#223044", color: "#e5edf7", borderColor: "#42546a" }
    : { background: "#ffffff", color: "#1e293b", borderColor: "#cbd5e1" };
  if (!node) return defaultColors;
  let paint = node;
  // The transparent LGZ target is separate from the actual painted interval/line.
  if (node.matches?.(".grt-result-hover-proxy")) {
    paint = node.parentElement?.querySelector?.(".grt-result-interval, .grt-result-junction") || node;
  } else if (node.matches?.(".subview-fragment-hit-zone, .main-anchor-fragment-hit-zone")) {
    // Anchor fragments are transparent intervals over a painted source ctg.
    for (let parent = node.parentElement; parent && String(parent.tagName).toLowerCase() !== "svg"; parent = parent.parentElement) {
      const source = parent.querySelector?.(":scope > .track-ctg");
      if (source) { paint = source; break; }
    }
  } else if (String(node.tagName || "").toLowerCase() === "g") {
    paint = node.querySelector?.(".track-ctg, .final-path-gap-marker")
      || [...(node.querySelectorAll?.("rect, polygon, path, line, circle, ellipse, polyline") || [])].find(candidate => {
        const value = read(candidate) || {};
        const fill = String(candidate.tagName).toLowerCase() === "line" ? null : parseTooltipColor(value.fill);
        const stroke = parseTooltipColor(value.stroke);
        return number(value.opacity) > 0 && (fill?.[3] > 0 || stroke?.[3] > 0);
      }) || node;
  }
  const style = read(paint) || {};
  const isSvg = paint.namespaceURI === "http://www.w3.org/2000/svg";
  const proxy = paint.matches?.(".track-collinearity-band[data-track-band-proxy]");
  let color = isSvg ? (String(paint.tagName).toLowerCase() === "line" ? null : parseTooltipColor(style.fill || paint.getAttribute?.("fill"))) : parseTooltipColor(style.backgroundColor);
  let strength = number(style.fillOpacity);
  if (proxy && (!color || !color[3])) {
    color = parseTooltipColor(style.getPropertyValue?.(dark ? "--alignment-band-dark-fill" : "--alignment-band-fill"));
    strength = 1; // The proxy's opacity/fill is intentionally suppressed, not the Canvas paint.
  }
  if (isSvg && (!color || !color[3])) {
    color = parseTooltipColor(style.stroke || paint.getAttribute?.("stroke"));
    strength = number(style.strokeOpacity);
  }
  if (!color || !color[3]) return defaultColors;
  if (!isSvg && !node.matches?.(".ctg-chip, .project-preview-contig, .project-preview-used, .project-preview-reference, .project-preview-final-part, .final-path-log-ratio-segment, [data-app-tooltip-color]")) {
    // A neutral UI control surface is not an object colour. Plain controls use
    // the approved tooltip defaults; genuinely coloured controls still match.
    const rootStyle = read(node.ownerDocument?.documentElement);
    const neutral = [defaultColors.background, ...["app", "panel", "card", "subtle", "muted", "elevated"]
      .map(name => rootStyle?.getPropertyValue?.(`--surface-${name}`))].map(parseTooltipColor).filter(Boolean);
    if (neutral.some(value => value.every((channel, i) => Math.abs(channel - color[i]) < .01))) return defaultColors;
  }
  color = [...color]; color[3] *= isSvg ? strength : 1;
  // Composite transparent evidence and object opacity against the actual plot/
  // ancestor surfaces. Reusing the same alpha over a floating panel is wrong.
  for (let current = paint; current; current = current.parentElement) {
    const currentStyle = read(current) || {};
    if (current !== paint) {
      // LGZ result intervals are painted over an optional mask and the source
      // ctg, not directly over the page. These sibling SVG paints are not CSS
      // backgroundColor, so resolve them explicitly in their stacking order.
      if (paint.matches?.(".grt-result-interval") && String(current.tagName).toLowerCase() === "g") {
        const layer = current.querySelector?.(":scope > .grt-result-mask") || current.querySelector?.(":scope > .track-ctg");
        if (layer) {
          const layerStyle = read(layer) || {}, underlay = parseTooltipColor(layerStyle.fill || layer.getAttribute?.("fill"));
          if (underlay) {
            underlay[3] *= number(layerStyle.fillOpacity) * number(layerStyle.opacity);
            color = compositeTooltipColor(color, underlay);
          }
        }
      }
      color = compositeTooltipColor(color, parseTooltipColor(currentStyle.backgroundColor));
    }
    if (!(current === paint && proxy)) color[3] *= number(currentStyle.opacity);
  }
  color = compositeTooltipColor(color, dark ? [23, 33, 46, 1] : [255, 255, 255, 1]);
  const darkInk = [30, 41, 59], lightInk = [248, 250, 252];
  const l = luminance(color), contrast = ink => (Math.max(l, luminance(ink)) + .05) / (Math.min(l, luminance(ink)) + .05);
  const ink = contrast(darkInk) >= contrast(lightInk) ? darkInk : lightInk;
  const border = color.slice(0, 3).map(c => l > .35 ? c * .75 : c + (255 - c) * .3);
  return { background: cssRgb(color), color: cssRgb(ink), borderColor: cssRgb(border) };
}
