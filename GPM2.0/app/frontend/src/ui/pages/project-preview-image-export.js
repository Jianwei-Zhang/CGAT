import { pickSaveFilePath } from "../../services/backend-api.js";
import { writeFinalPathExportBinaryFile } from "../../services/workflow-api.js";
import { projectIcon } from "./project-icons.js";
import { getMessages } from "../i18n/index.js";
import { formatProjectPreviewBp as bp, readProjectPreviewImageStyle } from "./project-preview-presentation.js";
import { projectPreviewDisplayCards, layoutProjectPreviewCard } from "./project-preview-layout.js";
import { resolveFinalPathSegmentDisplayName } from "./assembly/final-path-state.js";
import { previewProjectKey } from "./project-preview-state.js";
import { previewStateIsApplicable } from "./project-preview-cache.js";

const running = new WeakSet();
const xml = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const text = (x, y, value, options = "") => `<text x="${x}" y="${y}" ${options}>${xml(value)}</text>`;
const rect = (x, y, width, height, fill, stroke = "none", extra = "") =>
  `<rect x="${x}" y="${y}" width="${Math.max(0, width)}" height="${height}" fill="${fill}" stroke="${stroke}" ${extra}/>`;
const projectName = state => state.session?.projectName
  || state.initializer?.existingProjects?.find(project => Number(project.projectId) === Number(state.session?.projectId))?.projectName
  || "project";
const exportable = state => state.projectPreview?.loaded && !state.projectPreview.loading
  && !state.projectPreview.error && state.projectPreview.cards?.length > 0 && previewStateIsApplicable(state);
export const previewImageExportIsRunning = store => running.has(store);

// The action lives in Overview's toolbar, outside the independently updated
// Preview subtree. Standalone Preview still uses its own local action root.
export const previewImageActionRoot = host => host?.closest?.("[data-overview-project]") || host;
export function renderPreviewImageDownloadButton(state) {
  const label = xml(getMessages(state, "projectPreview").download);
  return `<button type="button" class="button project-preview-download" data-preview-download data-app-tooltip="${label}" aria-label="${label}" disabled>${projectIcon("imageDownload")}</button>`;
}
export function syncPreviewImageDownloadButton(host, store) {
  const button = previewImageActionRoot(host)?.querySelector?.("[data-preview-download]");
  if (button) button.disabled = running.has(store) || !exportable(store.getState());
}

// Build from ALL semantic cards, not the mounted/visible viewport. Native SVG
// primitives avoid screenshot/foreignObject dependencies and resolve all colors.
export function buildProjectPreviewSvgSnapshot(state, { width = 1440, style = readProjectPreviewImageStyle(), palette = style.palette,
  highlightAdopted = true } = {}) {
  if (!exportable(state)) throw new Error("Preview is not ready");
  const labels = getMessages(state, "projectPreview");
  // Keep the measured on-screen plot width, including minimum-pixel parts.
  // Only require enough room for the label column and a nonempty plot.
  width = Math.round(Math.max(2 * (style.padding + 21) + style.labelWidth + style.columnGap + 1, Number(width) || 1440));
  const inset = 20, bodyLeft = inset + style.padding + 1;
  const left = bodyLeft + style.labelWidth + style.columnGap, right = width - bodyLeft, plotWidth = right - left;
  const lineHeight = style.labelSize * 1.45, rowHeight = Math.max(20, lineHeight) + 4;
  const headerHeight = style.fontSize * 1.45 + 21;
  let y = 20;
  const shapes = [], cardBounds = [];
  const context = globalThis.document?.createElement?.("canvas")?.getContext?.("2d");
  const measure = (value, size, bold = false) => {
    if (context?.measureText) {
      context.font = `${bold ? "700 " : ""}${size}px ${style.fontFamily}`;
      return context.measureText(String(value)).width;
    }
    return [...String(value)].reduce((sum, char) => sum + (/[^\x00-\xff]/.test(char) ? size : size * 0.6), 0);
  };
  const ellipsis = (value, available, size) => {
    if (measure(value, size) <= available) return value;
    const chars = [...String(value)];
    while (chars.length && measure(`${chars.join("")}…`, size) > available) chars.pop();
    return chars.length ? `${chars.join("")}…` : "";
  };
  const label = (yy, value, color = style.text, bold = false) => text(bodyLeft, yy + 14,
    ellipsis(value, style.labelWidth, style.labelSize), `fill="${xml(color)}"${bold ? ' font-weight="600"' : ""}`);
  const roleColors = role => palette[role] || palette.companion;
  for (const [cardIndex, card] of projectPreviewDisplayCards(state.projectPreview.cards).entries()) {
    const top = y, clipId = `preview-card-${cardIndex}`;
    const paths = card.paths.filter(path => path.parts.length);
    const summary = [card.hasReference ? `Ref ${bp(card.refLength)}` : "",
      paths.length ? `Final Path ${paths.map(path => bp(path.length)).join(" / ")}` : ""].filter(Boolean).join(" · ");
    const summaryX = bodyLeft + measure(card.chrName, style.fontSize, true) + 12;
    const content = [rect(inset, top, width - inset * 2, headerHeight, style.header),
      `<path d="M${inset} ${top + headerHeight}H${width - inset}" stroke="${xml(style.border)}"/>`,
      text(bodyLeft, top + 10 + style.fontSize, card.chrName, `fill="${xml(style.title)}" font-size="${style.fontSize}" font-weight="700"`),
      text(summaryX, top + 10 + style.fontSize, ellipsis(summary, Math.max(0, right - summaryX), style.labelSize), `fill="${xml(style.muted)}"`)];
    y += headerHeight + 10;
    const geometry = layoutProjectPreviewCard(card, plotWidth);
    const bar = (layout, yy, colors, name = "", height = 16, radius = style.sourceRadius, extra = "") => {
      const sx = left + layout.x, w = layout.width;
      if (!(w > 0)) return;
      // Inset strokes match the App's border-box/inset-shadow outlines.
      content.push(rect(sx, yy, w, height, xml(colors.fill), "none", `rx="${radius}" ${extra}`),
        rect(sx + 0.5, yy + 0.5, Math.max(0, w - 1), height - 1, "none", xml(colors.stroke), `rx="${Math.max(0, radius - 0.5)}"`));
      if (name && measure(name, style.graphSize) + 6 <= w - 2) content.push(text(sx + 4, yy + 12, name,
        `fill="${xml(colors.text)}" font-size="${style.graphSize}"`));
    };
    const used = (layout, yy, role, height) => {
      if (!highlightAdopted || !(layout.width > 0)) return;
      const stroke = Math.min(2, layout.width / 2, height / 2);
      content.push(rect(left + layout.x + stroke / 2, yy + stroke / 2,
        layout.width - stroke, height - stroke, "none", xml(style.selectionStroke), `stroke-width="${stroke}" data-preview-adopted-outline="1"`));
    };
    for (const path of card.paths.length ? card.paths : [{ name: card.chrName, parts: [] }]) {
      const named = path.name !== card.chrName;
      content.push(label(y, "Final Path", style.text, true));
      if (named) content.push(label(y + lineHeight, path.name, style.axisText));
      if (!path.parts.length) content.push(text(left, y + 14, labels.noPath, `fill="${xml(style.axisText)}"`));
      const layouts = geometry.paths.get(path.name);
      path.parts.forEach((part, index) => {
        const name = part.gap ? "" : `${resolveFinalPathSegmentDisplayName(part.segment)}${(part.source?.orient || part.segment.orient) === "-" ? " (−)" : ""}`;
        bar(layouts[index], y + 2, part.gap ? style.gap : roleColors(part.role), name, 16, style.finalRadius);
        if (!part.gap) used(layouts[index], y + 2, part.role, 16);
      });
      y += Math.max(rowHeight, (named ? lineHeight * 2 : lineHeight) + 4);
    }
    content.push(label(y, labels.compositionAxis, style.axisText),
      text(left, y + 14, bp(card.domain.start), `fill="${xml(style.axisText)}"`),
      text(right, y + 14, bp(card.domain.end), `fill="${xml(style.axisText)}" text-anchor="end"`),
      `<path d="M${left} ${y + 21}H${right}" stroke="${xml(style.line)}"/>`);
    y += rowHeight;
    if (card.hasReference) {
      content.push(label(y, "Ref"));
      bar(geometry.reference, y + 6, roleColors("ref"), "", 6, style.referenceRadius);
      geometry.reference.highlights.forEach(patch => used(patch, y + 6, patch.patch.part.role, 6));
      y += rowHeight;
    }
    card.tracks.forEach((track, trackIndex) => {
      const colors = roleColors(track.role);
      content.push(`<circle cx="${bodyLeft + 3.5}" cy="${y + 10}" r="3.5" fill="${xml(colors.stroke)}"/>`,
        text(bodyLeft + 13, y + 14, ellipsis(track.name || labels.unknown, style.labelWidth - 13, style.labelSize)));
      track.positioned.forEach((item, index) => {
        const layout = geometry.tracks[trackIndex][index];
        const name = item.highlights.length ? `${item.name}${(item.displayOrient || (item.reverse ? "-" : "+")) === "-" ? " (−)" : ""}` : "";
        bar(layout, y + 2, colors, name, 16, style.sourceRadius, `data-source-length="${item.length}"`);
        layout.highlights.forEach(patch => used(patch, y + 2, track.role, 16));
      });
      if (!track.positioned.length) content.push(text(left, y + 14, "—", `fill="${xml(style.axisText)}"`));
      y += rowHeight;
    });
    if (card.unresolvedCount) { content.push(text(bodyLeft, y + 16, ellipsis(`${labels.unresolved} (${card.unresolvedCount})`, right - bodyLeft, style.labelSize), `fill="${xml(style.warning)}"`)); y += rowHeight; }
    y += 12;
    const cardWidth = width - inset * 2, cardHeight = y - top;
    const cardMarkup = [`<defs><clipPath id="${clipId}">${rect(inset, top, cardWidth, cardHeight, "#fff", "none", `rx="${style.radius}"`)}</clipPath></defs>`,
      rect(inset, top, cardWidth, cardHeight, xml(style.panel), "none", `rx="${style.radius}" filter="url(#preview-shadow)"`),
      `<g clip-path="url(#${clipId})">${content.join("")}</g>`,
      rect(inset + 0.5, top + 0.5, cardWidth - 1, cardHeight - 1, "none", xml(style.border), `rx="${Math.max(0, style.radius - 0.5)}"`)].join("");
    shapes.push(cardMarkup);
    cardBounds.push({ top, bottom: y, svgMarkup: cardMarkup });
    y += 16;
  }
  const height = Math.ceil(y + 4);
  // SVG is not constrained by canvas limits. PNG checks them before allocation;
  // PDF rasterizes bounded, whole-card pages instead of one enormous canvas.
  const rasterScale = previewRasterScale(width, height);
  const svgHeader = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="${xml(style.fontFamily)}" font-size="${style.labelSize}" fill="${xml(style.text)}"><title>${xml(projectName(state))}</title><defs><filter id="preview-shadow" x="-2%" y="-5%" width="104%" height="112%"><feDropShadow dx="0" dy="1" stdDeviation="1" flood-color="#0f172a" flood-opacity="${style.shadow}"/></filter></defs>${rect(0, 0, width, height, xml(style.panel))}`;
  return { width, height, rasterScale, cardBounds, svgHeader, tooLargeMessage: labels.exportTooLarge,
    svgMarkup: `${svgHeader}${shapes.join("")}</svg>` };
}

export const previewRasterScale = (width, height) => Math.min(2, 32000 / width, 32000 / height, Math.sqrt(40000000 / (width * height)));

export function previewBytesBase64(bytes) {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
  return btoa(binary);
}

export async function renderProjectPreviewPng(snapshot) {
  if (!(snapshot.rasterScale >= 1)) throw new Error(snapshot.tooLargeMessage);
  await globalThis.document?.fonts?.ready;
  const url = URL.createObjectURL(new Blob([snapshot.svgMarkup], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("Failed to decode preview image"));
      image.src = url;
    });
    const canvas = document.createElement("canvas"), scale = snapshot.rasterScale;
    canvas.width = Math.floor(snapshot.width * scale); canvas.height = Math.floor(snapshot.height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Failed to create preview image canvas");
    context.scale(scale, scale); context.drawImage(image, 0, 0, snapshot.width, snapshot.height);
    const data = canvas.toDataURL("image/png");
    if (!data.startsWith("data:image/png;base64,")) throw new Error("Failed to encode complete preview image");
    return data.slice("data:image/png;base64,".length);
  } finally { URL.revokeObjectURL(url); }
}

export async function exportProjectPreviewImage(host, store, deps = {}) {
  if (running.has(store) || !exportable(store.getState())) return false;
  const state = store.getState(), key = previewProjectKey(state), cards = state.projectPreview.cards;
  const current = () => previewProjectKey(store.getState()) === key && store.getState().projectPreview?.cards === cards
    && exportable(store.getState());
  const status = host.querySelector?.("[data-preview-export-error]");
  if (status) { status.hidden = true; status.textContent = ""; }
  running.add(store);
  const button = previewImageActionRoot(host)?.querySelector?.("[data-preview-download]");
  if (button) button.disabled = true;
  try {
    const screenWidth = host.querySelector?.(".project-preview-cards")?.clientWidth;
    const snapshot = buildProjectPreviewSvgSnapshot(state, { width: screenWidth > 0 ? screenWidth + 40 : undefined,
      style: readProjectPreviewImageStyle(host) });
    const fileName = String(projectName(state)).replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[ .]+$/g, "") || "project";
    let targetPath = await (deps.pickSaveFilePath || pickSaveFilePath)({ defaultPath: `${fileName}_preview.svg`,
      filters: [{ name: "SVG", extensions: ["svg"] }, { name: "PNG", extensions: ["png"] }, { name: "PDF", extensions: ["pdf"] }] }, state);
    if (!targetPath || !current()) return false;
    const extension = /\.([^./\\]+)$/.exec(targetPath)?.[1]?.toLowerCase();
    const format = extension || "svg";
    if (!extension) targetPath += ".svg";
    let bytesBase64;
    if (format === "svg") bytesBase64 = previewBytesBase64(new TextEncoder().encode(snapshot.svgMarkup));
    else if (format === "png") bytesBase64 = await (deps.renderProjectPreviewPng || renderProjectPreviewPng)(snapshot);
    else if (format === "pdf") {
      const render = deps.renderProjectPreviewPdf || (await import("./project-preview-pdf-export.js")).renderProjectPreviewPdf;
      bytesBase64 = await render(snapshot, deps.renderProjectPreviewPng || renderProjectPreviewPng);
    } else throw new Error(getMessages(state, "projectPreview").exportUnsupportedFormat);
    if (!current()) return false;
    await (deps.writeFinalPathExportBinaryFile || writeFinalPathExportBinaryFile)({ outputPath: targetPath, bytesBase64, stateOrLocale: state });
    return true;
  } catch (error) {
    if (current()) {
      const node = host.querySelector?.("[data-preview-export-error]");
      if (node) { node.textContent = getMessages(state, "projectPreview").exportFailed.replace("{message}", String(error?.message || error)); node.hidden = false; }
    }
    return false;
  } finally {
    running.delete(store);
    syncPreviewImageDownloadButton(host, store);
  }
}
