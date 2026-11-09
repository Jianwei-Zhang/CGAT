import { createSubviewRenderCover, blockSubviewRenderInput } from "./subview-drag-render-preview.js";
import { createSubviewBackgroundRenderer, prepareSubviewRenderPacket, yieldSubviewRender, disposeSubviewRenderPacket, retireSubviewDragProxies } from "./subview-background-render.js";
import { bindBandCanvasRuntime, adoptBandCanvasRaster } from "./band-canvas-runtime.js";
import { getAppSettings } from "../../../services/app-settings.js";
import { getAssemblyI18n } from "./i18n.js";
import { resolveCurrentSubviewHistory, formatSubviewHistoryActionLabel } from "./subview-history-state.js";

const ignoredAssemblyKeys = new Set(["actionStatus", "actionError", "trackScrollState", "subviewTrackScrollState", "finalPathTrackScrollState"]);
export function sameSubviewRenderSnapshot(left, right) {
  if (left.locale !== right.locale || left.initializer !== right.initializer) return false;
  if (left.assembly === right.assembly) return true;
  return [...new Set([...Object.keys(left.assembly || {}), ...Object.keys(right.assembly || {})])]
    .every(key => ignoredAssemblyKeys.has(key) || left.assembly?.[key] === right.assembly?.[key]);
}

export function updateSubviewDragHistoryControls(panel, state) {
  const history = resolveCurrentSubviewHistory(state.assembly), labels = getAssemblyI18n(state);
  for (const [action, enabled, label] of [
    ["history-rollback", history.canRollback, history.canRollback
      ? formatSubviewHistoryActionLabel(labels.subview.historyRollbackActionLabel, history.rollbackOperation, labels) : labels.subview.historyRollbackUnavailableLabel],
    ["history-restore-rollback", history.canRestoreRollback, history.canRestoreRollback
      ? formatSubviewHistoryActionLabel(labels.subview.historyRestoreRollbackActionLabel, history.restoreRollbackOperation, labels) : labels.subview.historyRestoreRollbackUnavailableLabel],
    ["history-reset", history.canReset, labels.subview.historyResetAria],
  ]) {
    const button = panel.querySelector(`[data-subview-action="${action}"]`);
    if (!button) continue;
    button.disabled = !enabled;
    button.setAttribute("aria-label", label); button.setAttribute("data-app-tooltip", label);
  }
}

export function createSubviewDragRenderController({
  renderer = createSubviewBackgroundRenderer(),
  supported = () => typeof Worker === "function",
  yieldTask = yieldSubviewRender,
  getWidths, onBind = () => {}, onMounted = () => {}, onFallback = () => {},
  createCover = createSubviewRenderCover,
  statusDelayMs = 350,
  setTimer = globalThis.setTimeout?.bind(globalThis),
  clearTimer = globalThis.clearTimeout?.bind(globalThis),
} = {}) {
  let active = null, serial = 0;
  function cancel() {
    ++serial;
    if (active) { active.cancelled = true; active.cleanup(); active = null; }
    renderer.cancel();
  }
  function start(host, store, preview) {
    const panel = host?.querySelector?.("[data-subview-panel='1']");
    let card = panel?.querySelector?.(".subview-alignment-card");
    const scroll = card?.querySelector?.(".subview-track-scroll");
    const denseBands = scroll?.getAttribute?.("data-subview-band-rendering") === "dense";
    if (!preview?.prepareCommit || !supported() || !scroll
      || !scroll.querySelector("[data-subview-band-drag-canvas]")
      || (!denseBands && (scroll.querySelectorAll?.("[data-track-band-proxy='1']")?.length || 0) < 1000)) return null;
    if (active) cancel();
    const initial = store.getState(), document = panel.ownerDocument;
    const marker = document.createElement("div");
    marker.className = "subview-render-status"; marker.setAttribute("role", "status");
    marker.setAttribute("aria-live", "polite");
    marker.textContent = getAssemblyI18n(initial).subview.renderPending;
    // Keep progress out of the parameter row. The status is absolutely placed
    // over the non-scrolling plot layout and appears only for a visible wait.
    const mountMarker = (nextCard, nextViewport) => {
      (nextViewport?.parentElement || nextCard)?.appendChild?.(marker);
    };
    mountMarker(card, scroll);
    const statusTimer = Number(statusDelayMs) > 0 && typeof setTimer === "function"
      ? setTimer(() => marker.setAttribute("data-visible", "1"), Number(statusDelayMs))
      : (marker.setAttribute("data-visible", "1"), null);
    let cover = null, nextScroll = null;
    // A single input shield avoids toggling `inert` on tens of thousands of
    // SVG descendants (which itself causes a whole-subtree style pause).
    const shield = document.createElement("div");
    shield.setAttribute("aria-hidden", "true");
    Object.assign(shield.style, { position: "absolute", inset: "0", zIndex: "4" });
    blockSubviewRenderInput(shield); scroll.appendChild(shield);
    scroll.setAttribute("aria-busy", "true");
    panel.setAttribute("data-subview-render-incomplete", "1");
    let cleaned = false;
    const job = { id: ++serial, cancelled: false, cleanup() {
      if (cleaned) return; cleaned = true;
      if (statusTimer !== null && typeof clearTimer === "function") clearTimer(statusTimer);
      marker.remove(); shield.remove(); scroll.removeAttribute("aria-busy");
      cover?.remove();
      if (nextScroll) nextScroll.removeAttribute("aria-busy");
    } };
    active = job;
    try {
      preview.prepareCommit();
      updateSubviewDragHistoryControls(panel, initial);
    } catch (error) { cancel(); throw error; }
    const sameContext = () => serial === job.id && !job.cancelled && card.isConnected !== false
      && host.querySelector("[data-subview-panel='1']") === panel
      && panel.querySelector(".subview-alignment-card") === card
      && store.getState().activeRoute === initial.activeRoute
      && store.getState().session?.workspacePath === initial.session?.workspacePath
      && store.getState().session?.projectId === initial.session?.projectId
      && store.getState().assembly?.selectedChrName === initial.assembly?.selectedChrName
      && store.getState().assembly?.activeTab === "assembly"
      && !store.getState().assembly?.loading && !store.getState().assembly?.sourceEditingReloadRequired;
    const contextCurrent = () => active === job && sameContext();
    return (async () => {
      let mounted = false, retired = false;
      try {
        while (contextCurrent()) {
          let state = store.getState(), needsRebind = false;
          const settings = getAppSettings(), settingsKey = JSON.stringify(settings), widths = getWidths(store);
          const theme = document.documentElement.dataset.theme || "light", dpr = Math.max(1, Number(globalThis.devicePixelRatio || 1));
          const current = () => !needsRebind && contextCurrent() && sameSubviewRenderSnapshot(state, store.getState())
            && JSON.stringify(getAppSettings()) === settingsKey && getWidths(store).subview === widths.subview
            && (document.documentElement.dataset.theme || "light") === theme && Math.max(1, Number(globalThis.devicePixelRatio || 1)) === dpr;
          const drawing = renderer.render(state, { settings, widths, theme, dpr }, current);
          void drawing.catch(() => {});
          if (!retired) {
            retired = await retireSubviewDragProxies(scroll, contextCurrent, { yieldTask });
          }
          const packet = await drawing;
          try {
            if (!contextCurrent()) return false;
            if (!packet || !current()) continue;
            const content = await prepareSubviewRenderPacket(document, packet, current, { yieldTask,
              onSkeleton(content) {
                const nextCard = content.querySelector(".subview-alignment-card");
                if (!nextCard) throw new Error("Missing prepared Local View graph");
                const layers = [...nextCard.querySelectorAll("[data-track-band-canvas-layer='1']")];
                for (const raster of packet.rasters || []) adoptBandCanvasRaster(layers[raster.index], raster);
                bindBandCanvasRuntime(nextCard, { synchronous: true });
                cover ||= createCover(scroll);
                nextScroll = nextCard.querySelector(".subview-track-scroll");
                if (!nextScroll) throw new Error("Missing prepared Local View viewport");
                nextScroll.setAttribute("aria-busy", "true");
                nextScroll.appendChild(cover);
                card.replaceWith(nextCard); card = nextCard; mounted = true;
                mountMarker(nextCard, nextScroll);
                // Navigation wraps/reparents the layout and restores scroll.
                // Do this while it is sparse, not after 30,000 nodes exist.
                needsRebind = onBind(host, store, nextCard) === false;
                state = store.getState(); // binding may normalize derived viewport preferences
              },
            });
            if (!contextCurrent()) return false;
            if (!content || !current()) continue;
            // Each batch has already been styled in small input-interleaved
            // tasks. Completion removes only a sparse visual cover.
            await yieldTask();
            if (!current()) continue;
          } finally { disposeSubviewRenderPacket(packet); }
          updateSubviewDragHistoryControls(panel, store.getState());
          panel.removeAttribute("data-subview-render-incomplete");
          active = null; job.cleanup();
          await onMounted(host, store, card);
          return true;
        }
        return false;
      } catch (error) {
        if (contextCurrent()) {
          // Retain the authoritative synchronous renderer for unsupported/error
          // cases, but never let a late result touch a different graph/project.
          active = null; job.cleanup(); renderer.cancel();
          await yieldTask();
          if (sameContext()) {
            onFallback(host, store, error);
            panel.removeAttribute("data-subview-render-incomplete");
          }
        } else if (mounted && !job.cancelled && card.isConnected !== false) throw error;
        return false;
      } finally {
        job.cleanup();
        if (active === job) { active = null; renderer.cancel(); }
      }
    })();
  }
  return { start, cancel };
}
