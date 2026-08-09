export function createAssemblyDomPatchController({
  bindBandCanvasRuntime,
  escapeHtml,
  filterPrimaryTrackSelectionCtgIds,
  getAssemblyI18n,
  normalizeTrackSelectionCtgIds,
  renderAssemblyMainTrackSections,
}) {
  function createRenderedAssemblyMainTabContent(routeHost, state) {
    const doc = routeHost?.ownerDocument || globalThis.document;
    if (!doc?.createElement) {
      return null;
    }
    const template = doc.createElement("template");
    template.innerHTML = renderAssemblyMainTrackSections(state);
    return template.content;
  }

  function replaceRenderedAssemblySection(routeHost, nextContent, selector) {
    const current = routeHost.querySelector(selector);
    const next = nextContent?.querySelector?.(selector) || null;
    if (!current || !next || typeof current.replaceWith !== "function") {
      return null;
    }
    current.replaceWith(next);
    return next;
  }

  function patchAssemblyStatusToast(routeHost, nextContent) {
    const currentMain = routeHost?.querySelector?.(".assembly-main-view") || null;
    if (!currentMain) {
      return false;
    }
    const currentToast = currentMain.querySelector?.(".assembly-status-toast-wrap") || null;
    const nextToast = nextContent?.querySelector?.(".assembly-status-toast-wrap") || null;
    if (currentToast && nextToast && typeof currentToast.replaceWith === "function") {
      currentToast.replaceWith(nextToast);
      return true;
    }
    if (currentToast && typeof currentToast.remove === "function") {
      currentToast.remove();
      return true;
    }
    if (!currentToast && nextToast && typeof currentMain.insertBefore === "function") {
      currentMain.insertBefore(nextToast, currentMain.firstChild || null);
      return true;
    }
    return false;
  }

  function getElementDatasetValue(element, key, attrName) {
    if (element?.dataset && Object.prototype.hasOwnProperty.call(element.dataset, key)) {
      return element.dataset[key];
    }
    return typeof element?.getAttribute === "function" ? element.getAttribute(attrName) : "";
  }

  function queryElementsByNumericDataset(root, selector, datasetKey, attrName, targetId) {
    const normalizedId = Number(targetId || 0);
    if (!normalizedId) {
      return [];
    }
    return Array.from(root?.querySelectorAll?.(selector) || []).filter((element) =>
      Number(getElementDatasetValue(element, datasetKey, attrName) || 0) === normalizedId,
    );
  }

  function patchMemberChipHiddenState(chip, shouldHide, hiddenTagText) {
    chip?.classList?.toggle?.("is-hidden-contig", shouldHide);
    const existingTag = chip?.querySelector?.(".ctg-chip-hidden-tag") || null;
    if (!shouldHide) {
      existingTag?.remove?.();
      return;
    }
    if (existingTag) {
      return;
    }
    const titleNode = chip?.querySelector?.("strong") || null;
    titleNode?.insertAdjacentHTML?.(
      "beforeend",
      ` <span class="ctg-chip-hidden-tag">${escapeHtml(hiddenTagText)}</span>`,
    );
  }

  function patchPrimaryTrackCtgHiddenState(group, shouldHide) {
    if (!group) {
      return;
    }
    if (group.dataset && group.dataset.primaryHiddenBase === undefined) {
      group.dataset.primaryHiddenBase = group.classList?.contains?.("is-hidden-contig") ? "1" : "0";
    }
    const baseHidden = group.dataset?.primaryHiddenBase === "1";
    const offset = shouldHide === baseHidden ? 0 : shouldHide ? -30 : 30;
    group.classList?.toggle?.("is-hidden-contig", shouldHide);
    group.querySelectorAll?.(".track-ctg")?.forEach((node) => {
      node.classList?.toggle?.("is-hidden-contig", shouldHide);
    });
    if (offset === 0) {
      group.removeAttribute?.("transform");
    } else {
      group.setAttribute?.("transform", `translate(0 ${offset})`);
    }
  }

  function parseTrackBandPointsAttr(value) {
    return String(value || "")
      .trim()
      .split(/\s+/)
      .map((pair) => {
        const [x, y] = pair.split(",").map((part) => Number(part));
        return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
      })
      .filter(Boolean);
  }

  function rebuildMainTrackCanvasBandsFromSvg(root) {
    const scrollEls = Array.from(root?.querySelectorAll?.(".assembly-track-scroll[data-track-role='primary']") || []);
    let changed = false;
    scrollEls.forEach((scrollEl) => {
      const overlay = scrollEl.querySelector?.("[data-track-band-svg-overlay='1']");
      if (!overlay) {
        return;
      }
      const bands = Array.from(overlay.querySelectorAll?.(".track-collinearity-band[data-track-band-proxy='1']") || [])
        .filter((band) => band?.dataset?.hiddenByPrimaryCtg !== "1" && band?.style?.display !== "none")
        .map((band) => {
          const points = parseTrackBandPointsAttr(band.getAttribute?.("points"));
          if (points.length < 4) {
            return null;
          }
          return {
            hitKey: "",
            tone: band?.dataset?.bandTrackRole === "support" ? "companion" : "primary",
            points,
          };
        })
        .filter(Boolean);
      Array.from(scrollEl.querySelectorAll?.("[data-track-band-canvas-layer='1'][data-track-band-canvas-scene-kind='main-track']") || [])
        .forEach((layer) => {
          const sceneNode = layer.querySelector?.("[data-track-band-canvas-scene]");
          if (!sceneNode) {
            return;
          }
          try {
            const scene = JSON.parse(String(sceneNode.textContent || "").trim() || "null");
            if (!scene || typeof scene !== "object") {
              return;
            }
            scene.bands = bands;
            sceneNode.textContent = JSON.stringify(scene);
            changed = true;
          } catch {
            // Ignore malformed canvas scene data and leave the current canvas untouched.
          }
        });
    });
    if (changed) {
      bindBandCanvasRuntime(root);
    }
  }

  function patchPrimaryHiddenCtgDom(host, store, nextHiddenIds, options = {}) {
    const routeHost = host?.closest?.("#route-host") || null;
    if (!routeHost?.querySelectorAll) {
      return false;
    }
    const state = store.getState();
    const hiddenSet = new Set(filterPrimaryTrackSelectionCtgIds(nextHiddenIds, state.assembly));
    const changedIds = filterPrimaryTrackSelectionCtgIds(options.changedIds, state.assembly);
    if (!changedIds.length) {
      return false;
    }
    if (changedIds.some((ctgId) => !hiddenSet.has(ctgId))) {
      return false;
    }
    const hiddenTagText = getAssemblyI18n(state).page.deletedHiddenTag;
    let touched = false;
    changedIds.forEach((ctgId) => {
      queryElementsByNumericDataset(
        routeHost,
        ".assembly-member-chip-region [data-assembly-ctg-id]",
        "assemblyCtgId",
        "data-assembly-ctg-id",
        ctgId,
      ).forEach((chip) => {
        patchMemberChipHiddenState(chip, true, hiddenTagText);
        touched = true;
      });
      queryElementsByNumericDataset(
        routeHost,
        "[data-track-role='primary'][data-track-contig-id]",
        "trackContigId",
        "data-track-contig-id",
        ctgId,
      ).forEach((group) => {
        patchPrimaryTrackCtgHiddenState(group, true);
        touched = true;
      });
      queryElementsByNumericDataset(
        routeHost,
        "[data-band-track-role='primary'][data-band-contig-id]",
        "bandContigId",
        "data-band-contig-id",
        ctgId,
      ).forEach((band) => {
        if (band.dataset) {
          band.dataset.hiddenByPrimaryCtg = "1";
        }
        if (band.style) {
          band.style.display = "none";
        }
        touched = true;
      });
    });
    if (touched) {
      rebuildMainTrackCanvasBandsFromSvg(routeHost);
    }
    return touched;
  }

  function patchDeletedPrimaryTrackCtgsDom(host, deletedIds) {
    const routeHost = host?.closest?.("#route-host") || null;
    if (!routeHost?.querySelectorAll) {
      return false;
    }
    const normalizedIds = normalizeTrackSelectionCtgIds(deletedIds);
    if (!normalizedIds.length) {
      return false;
    }
    let touched = false;
    normalizedIds.forEach((ctgId) => {
      queryElementsByNumericDataset(
        routeHost,
        "[data-track-role='primary'][data-track-contig-id]",
        "trackContigId",
        "data-track-contig-id",
        ctgId,
      ).forEach((group) => {
        group.remove?.();
        touched = true;
      });
      queryElementsByNumericDataset(
        routeHost,
        "[data-band-track-role='primary'][data-band-contig-id]",
        "bandContigId",
        "data-band-contig-id",
        ctgId,
      ).forEach((band) => {
        band.remove?.();
        touched = true;
      });
    });
    if (touched) {
      rebuildMainTrackCanvasBandsFromSvg(routeHost);
    }
    return touched;
  }

  return {
    createRenderedAssemblyMainTabContent,
    patchAssemblyStatusToast,
    patchDeletedPrimaryTrackCtgsDom,
    patchPrimaryHiddenCtgDom,
    replaceRenderedAssemblySection,
  };
}
