import { normalizeSupportDatasetId } from "./selection-state.js";
import { paintBandCanvasScene } from "./band-canvas-runtime.js";
import { renderAssemblySubviewPanel } from "./render-tracks.js";
import { getAssemblyI18n } from "./i18n.js";
import { buildSupportDatasetOptions } from "./support-dataset-options.js";
import { setAppSettings } from "../../../services/app-settings.js";
import { applySubviewRenderDelta, splitSubviewRenderMarkup } from "./subview-render-packet.js";

const escapeHtml = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
export function renderSubviewInWorker(state, { settings, widths, theme = "light", dpr = 1 } = {}) {
  if (settings) setAppSettings(settings, { persist: false });
  const getCurrentProject = state => {
    const id = Number(state.session?.projectId || 0);
    return id && Array.isArray(state.initializer?.existingProjects)
      ? state.initializer.existingProjects.find(project => Number(project.projectId) === id) || null : null;
  };
  const html = renderAssemblySubviewPanel(state, {
    escapeHtml, escapeAttr: value => escapeHtml(value).replaceAll('"', "&quot;"),
    formatBp: value => `${Number(value || 0).toLocaleString("en-US")} bp`,
    getAssemblyI18n, getCurrentProject,
    getDatasetNameById: (datasets, id) => {
      const normalizedId = normalizeSupportDatasetId(id);
      if (!normalizedId) return "";
      const item = Array.isArray(datasets) ? datasets.find(item => Number(item.datasetId) === normalizedId) : null;
      return String(item?.name || item?.label || `ds-${normalizedId}`);
    },
    getSupportDatasetOptions: (state, project = getCurrentProject(state)) => buildSupportDatasetOptions(project, state.initializer?.datasets || []),
    getMeasuredTrackViewportPx: role => widths?.[role],
  });
  const packet = splitSubviewRenderMarkup(html);
  packet.rasters = [];
  if (typeof OffscreenCanvas === "function") {
    for (const [index, match] of [...html.matchAll(/<script[^>]*data-track-band-canvas-scene[^>]*>([\s\S]*?)<\/script>/g)].entries()) {
      try {
        const sceneText = match[1], scene = JSON.parse(sceneText), canvas = new OffscreenCanvas(1, 1);
        const painted = paintBandCanvasScene(canvas, scene, { theme, dpr });
        if (painted) packet.rasters.push({ index, sceneText, scene, theme, dpr,
          left: painted.left, width: painted.width, height: painted.height, bitmap: canvas.transferToImageBitmap() });
      } catch { /* Full vector/Canvas rendering remains the fallback. */ }
    }
  }
  return packet;
}

let state = null;
if (typeof self !== "undefined" && typeof self.postMessage === "function" && typeof document === "undefined") {
  self.onmessage = ({ data }) => {
    try {
      state = applySubviewRenderDelta(state, data.delta);
      const packet = renderSubviewInWorker(state, data);
      self.postMessage({ id: data.id, packet }, packet.rasters.map(raster => raster.bitmap));
    } catch (error) {
      self.postMessage({ id: data.id, error: String(error?.message || error) });
    }
  };
}
