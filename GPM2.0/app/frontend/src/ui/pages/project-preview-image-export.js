import { pickSaveFilePath } from "../../services/backend-api.js";
import { writeFinalPathExportBinaryFile } from "../../services/workflow-api.js";
import { projectIcon } from "./project-icons.js";
import { getMessages } from "../i18n/index.js";
import { getContigPalette } from "./assembly/contig-colors.js";
import { layoutProjectPreviewCard } from "./project-preview-layout.js";
import { resolveFinalPathSegmentDisplayName } from "./assembly/final-path-state.js";
import { previewProjectKey } from "./project-preview-state.js";
import { previewStateIsApplicable } from "./project-preview-cache.js";

const running = new WeakSet();
const xml = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
const bp = value => `${Number(value).toLocaleString("en-US")} bp`;
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
export function buildProjectPreviewSvgSnapshot(state, { width = 1440, palette = getContigPalette() } = {}) {
  if (!exportable(state)) throw new Error("Preview is not ready");
  const labels = getMessages(state, "projectPreview");
  width = Math.round(Math.min(2000, Math.max(1000, Number(width) || 1440)));
  const left = 176, right = width - 28, plotWidth = right - left;
  let y = 20;
  const shapes = [];
  const label = (yy, value) => text(32, yy + 14, value);
  for (const card of state.projectPreview.cards) {
    const top = y;
    const summary = [card.hasReference ? `Ref ${bp(card.refLength)}` : "",
      ...card.paths.filter(path => path.parts.length).map(path => `Final Path ${bp(path.length)}`)].filter(Boolean).join(" · ");
    const content = [text(32, y + 23, card.chrName, 'font-size="16" font-weight="700"'),
      text(164, y + 23, summary, 'fill="#64748b"')];
    y += 42;
    const geometry = layoutProjectPreviewCard(card, plotWidth);
    content.push(label(y, labels.compositionAxis), text(left, y + 14, bp(card.domain.start)),
      text(right, y + 14, bp(card.domain.end), 'text-anchor="end"'),
      `<path d="M${left} ${y + 21}H${right}" stroke="#cbd5e1"/>`);
    y += 30;
    const bar = (layout, yy, role, name = "", height = 16, extra = "") => {
      const colors = palette[role] || palette.companion;
      const sx = left + layout.x, w = layout.width;
      if (!(w > 0)) return;
      content.push(rect(sx, yy + 2, w, height, colors.fill, colors.stroke, extra));
      // Keep complete labels or omit them; no clipping into neighbouring bars.
      if (name && [...String(name)].length * 8 + 8 <= w) content.push(text(sx + 4, yy + 14, name, `fill="${colors.text}" font-size="12"`));
    };
    const used = (layout, yy, role, height = 14) => {
      if (layout.width > 0) content.push(rect(left + layout.x, yy + 3, layout.width, height,
        "none", palette[role]?.stroke || palette.companion.stroke, 'stroke-width="2"'));
    };
    if (card.hasReference) {
      content.push(label(y, "Ref"));
      bar(geometry.reference, y + 4, "ref", "", 6);
      geometry.reference.highlights.forEach(patch => used(patch, y + 2, patch.patch.part.role, 8));
      y += 26;
    }
    card.tracks.forEach((track, trackIndex) => {
      content.push(label(y, track.name || labels.unknown));
      track.positioned.forEach((item, index) => {
        const layout = geometry.tracks[trackIndex][index];
        bar(layout, y, track.role, `${item.name}${(item.displayOrient || (item.reverse ? "-" : "+")) === "-" ? " (−)" : ""}`,
          16, `data-source-length="${item.length}"`);
        layout.highlights.forEach(patch => used(patch, y, track.role));
      });
      if (!track.positioned.length) content.push(text(left, y + 14, "—"));
      y += 26;
    });
    content.push(`<path d="M32 ${y}H${right}" stroke="#cbd5e1"/>`); y += 8;
    for (const path of card.paths) {
      content.push(label(y, path.name === card.chrName ? "Final Path" : `Final Path ${path.name}`));
      if (!path.parts.length) content.push(text(left, y + 14, labels.noPath));
      const layouts = geometry.paths.get(path.name);
      path.parts.forEach((part, index) => {
        const layout = layouts[index], sx = left + layout.x;
        const colors = part.gap ? { fill: "#ffffff", stroke: "#64748b", text: "#1e293b" } : palette[part.role];
        content.push(rect(sx, y + 2, layout.width, 16, colors.fill, colors.stroke));
        const name = part.gap ? "" : `${resolveFinalPathSegmentDisplayName(part.segment)}${(part.source?.orient || part.segment.orient) === "-" ? " (−)" : ""}`;
        if (name && [...name].length * 8 + 8 <= layout.width) content.push(text(sx + 4, y + 14, name, `fill="${colors.text}" font-size="12"`));
      });
      y += 26;
    }
    if (card.unresolvedCount) { content.push(text(32, y + 14, `${labels.unresolved} (${card.unresolvedCount})`, 'fill="#8a612d"')); y += 24; }
    y += 10;
    shapes.push(rect(20, top, width - 40, y - top, "#ffffff", "#cbd5e1", 'rx="5"'), ...content);
    y += 16;
  }
  const height = Math.ceil(y + 8);
  // Bound both dimensions and total canvas memory before allocating. Never
  // silently truncate cards, produce an empty data URL or save a partial image.
  const rasterScale = Math.min(2, 32000 / width, 32000 / height, Math.sqrt(40000000 / (width * height)));
  if (rasterScale < 1) throw new Error(labels.exportTooLarge);
  return { width, height, rasterScale,
    svgMarkup: `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="system-ui, Segoe UI, Microsoft YaHei, sans-serif" font-size="13" fill="#1e293b"><title>${xml(projectName(state))}</title>${rect(0, 0, width, height, "#ffffff")}${shapes.join("")}</svg>` };
}

export async function renderProjectPreviewPng(snapshot) {
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
    const snapshot = buildProjectPreviewSvgSnapshot(state, { width: host.querySelector?.(".project-preview-cards")?.clientWidth });
    const fileName = String(projectName(state)).replace(/[<>:"/\\|?*\x00-\x1f]/g, "_").replace(/[ .]+$/g, "") || "project";
    const targetPath = await (deps.pickSaveFilePath || pickSaveFilePath)({ defaultPath: `${fileName}_preview.png`,
      filters: [{ name: "PNG", extensions: ["png"] }] }, state);
    if (!targetPath || !current()) return false;
    const bytesBase64 = await (deps.renderProjectPreviewPng || renderProjectPreviewPng)(snapshot);
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
