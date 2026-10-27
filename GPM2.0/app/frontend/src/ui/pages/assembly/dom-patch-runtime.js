export function createAssemblyDomPatchController({
  bindBandCanvasRuntime,
  escapeHtml,
  filterPrimaryTrackSelectionCtgIds,
  getAssemblyI18n,
  normalizeTrackSelectionCtgIds,
  renderAssemblyMainTrackSections,
  renderAssemblySubviewPanel = null,
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

  function createRenderedContent(routeHost, html) {
    const doc = routeHost?.ownerDocument || globalThis.document;
    if (!doc?.createElement) {
      return null;
    }
    const template = doc.createElement("template");
    template.innerHTML = String(html || "");
    return template.content;
  }

  function collectElementsByAttribute(root, selector, attributeName) {
    const collected = new Map();
    Array.from(root?.querySelectorAll?.(selector) || []).forEach((element) => {
      const value = typeof element?.getAttribute === "function"
        ? String(element.getAttribute(attributeName) || "").trim()
        : "";
      if (value) {
        collected.set(value, element);
      }
    });
    return collected;
  }

  function patchGrtResultOverlayNodes(liveRoot, nextRoot) {
    let touched = false;
    [
      ["[data-grt-result-overlay-key]", "data-grt-result-overlay-key"],
      ["[data-grt-result-overlay-layer]", "data-grt-result-overlay-layer"],
    ].forEach(([selector, attributeName]) => {
      const nextNodes = collectElementsByAttribute(nextRoot, selector, attributeName);
      if (!nextNodes.size) {
        return;
      }
      Array.from(liveRoot?.querySelectorAll?.(selector) || []).forEach((liveNode) => {
        const marker = String(liveNode?.getAttribute?.(attributeName) || "").trim();
        const nextNode = marker ? nextNodes.get(marker) : null;
        if (!nextNode) {
          return;
        }
        const nextMarkup = String(nextNode.innerHTML ?? "");
        if (String(liveNode.innerHTML ?? "") !== nextMarkup) {
          liveNode.innerHTML = nextMarkup;
          touched = true;
        }
      });
    });
    return touched;
  }

  function patchGrtResultToastNode(liveRoot, nextRoot) {
    const liveToast = liveRoot?.querySelector?.(".grt-result-toast") || null;
    const nextToast = nextRoot?.querySelector?.(".grt-result-toast") || null;
    if (liveToast && nextToast) {
      if (String(liveToast.outerHTML || "") !== String(nextToast.outerHTML || "")) {
        liveToast.replaceWith(nextToast);
      }
      return;
    }
    if (liveToast) {
      liveToast.remove?.();
      return;
    }
    if (nextToast?.nodeType === 1) {
      // The renderers place the toast directly after the card/track head.
      const anchor = liveRoot?.querySelector?.(".subview-panel-head")
        || liveRoot?.querySelector?.(".assembly-track-panel-head")
        || liveRoot?.firstElementChild
        || null;
      anchor?.insertAdjacentElement?.("afterend", nextToast);
    }
  }

  // Toggling the GRT result switch must not rebuild the whole view: the visual
  // layers are patched in place so the plot keeps its scroll and zoom state.
  function patchGrtResultOverlaysDom(host, store, scope) {
    const normalizedScope = scope === "main" ? "main" : "subview";
    const routeHost = host?.closest?.("#route-host") || host;
    if (!routeHost?.querySelector) {
      return false;
    }
    const liveRoot = normalizedScope === "main"
      ? routeHost.querySelector('[data-grt-result-card="main"]')?.closest?.(".assembly-track-unified") || null
      : routeHost.querySelector("[data-subview-panel='1']");
    if (!liveRoot) {
      return false;
    }
    const state = store.getState();
    const nextHtml = normalizedScope === "main"
      ? renderAssemblyMainTrackSections(state)
      : typeof renderAssemblySubviewPanel === "function"
        ? renderAssemblySubviewPanel(state)
        : "";
    const nextRoot = createRenderedContent(routeHost, nextHtml);
    if (!nextRoot) {
      return false;
    }
    const overlaySelector = "[data-grt-result-overlay-key], [data-grt-result-overlay-layer]";
    if (
      nextRoot.querySelectorAll(overlaySelector).length
      && !liveRoot.querySelectorAll?.(overlaySelector).length
    ) {
      // The mounted view does not expose the expected layers; rebuild instead
      // of leaving stale overlays on screen.
      return false;
    }
    patchGrtResultOverlayNodes(liveRoot, nextRoot);
    patchGrtResultToastNode(liveRoot, nextRoot);
    return true;
  }

  // Local edits update the panel head and plot as sibling replacements. Keeping
  // the mounted panel node prevents WebView2 from flashing the whole window and
  // preserves the scroll container until its replacement is ready.
  function patchSubviewPanelDom(host, store) {
    const routeHost = host?.closest?.("#route-host") || host;
    const livePanel = routeHost?.querySelector?.("[data-subview-panel='1']") || null;
    if (!livePanel || typeof renderAssemblySubviewPanel !== "function") return null;
    const nextContent = createRenderedContent(routeHost, renderAssemblySubviewPanel(store.getState()));
    const nextPanel = nextContent?.querySelector?.("[data-subview-panel='1']") || null;
    if (!nextPanel) return null;
    const selectors = [".subview-panel-head", ".subview-alignment-card"];
    const replacements = selectors.map((selector) => ({
      current: livePanel.querySelector(selector),
      next: nextPanel.querySelector(selector),
    }));
    if (replacements.some(({ current, next }) => Boolean(current) !== Boolean(next)
      || (current && typeof current.replaceWith !== "function"))) return null;
    const currentScroll = livePanel.querySelector(".subview-track-scroll");
    const scrollLeft = Number(currentScroll?.scrollLeft || 0);
    const scrollTop = Number(currentScroll?.scrollTop || 0);
    const replaced = replacements.flatMap(({ current, next }) => {
      if (!current || !next) return [];
      current.replaceWith(next);
      return [next];
    });
    if (!replaced.length) return null;
    const nextScroll = livePanel.querySelector(".subview-track-scroll");
    if (nextScroll) { nextScroll.scrollLeft = scrollLeft; nextScroll.scrollTop = scrollTop; }
    patchGrtResultToastNode(livePanel, nextPanel);
    const liveError = livePanel.querySelector(":scope > .error-text");
    const nextError = nextPanel.querySelector(":scope > .error-text");
    if (liveError && nextError) liveError.replaceWith(nextError);
    else if (liveError) liveError.remove?.();
    else if (nextError) (livePanel.querySelector(".grt-result-toast")
      || livePanel.querySelector(".subview-panel-head"))?.insertAdjacentElement?.("afterend", nextError);
    return replaced;
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
    const wasHidden = chip?.classList?.contains?.("is-hidden-contig") === true;
    chip?.classList?.toggle?.("is-hidden-contig", shouldHide);
    const details = chip?.querySelector?.(".ctg-chip-details");
    if (details) {
      if (wasHidden === shouldHide) return;
      const tooltip = chip.getAttribute("data-member-tooltip") || "";
      const lines = tooltip.split("\n").filter(line => line !== hiddenTagText);
      if (shouldHide) lines.push(hiddenTagText);
      chip.setAttribute("data-member-tooltip", lines.join("\n"));
      let tags = details.querySelector(".ctg-chip-tags");
      if (!tags && shouldHide) {
        details.insertAdjacentHTML("beforeend", `<span class="ctg-chip-tags" data-member-state-count="1"><span class="ctg-chip-hidden-tag">${escapeHtml(hiddenTagText)}</span></span>`);
      } else if (tags) {
        if (shouldHide && !tags.querySelector(".ctg-chip-hidden-tag")) tags.insertAdjacentHTML("beforeend", `<span class="ctg-chip-hidden-tag">${escapeHtml(hiddenTagText)}</span>`);
        const count = Math.max(0, Number(tags.dataset.memberStateCount || 1) + (shouldHide ? 1 : -1));
        tags.dataset.memberStateCount = String(count);
        const more = tags.querySelector(".ctg-chip-more-states");
        if (count > 1 && more) more.textContent = `+${count - 1}`;
        else if (count > 1) tags.insertAdjacentHTML("beforeend", `<span class="ctg-chip-more-states">+${count - 1}</span>`);
        else more?.remove();
        if (!shouldHide) tags.querySelector(".ctg-chip-hidden-tag")?.remove();
        if (!count) tags.remove();
      }
      return;
    }
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
            identityPct: band?.dataset?.bandIdentityPct ?? null,
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
    patchGrtResultOverlaysDom,
    patchSubviewPanelDom,
    patchDeletedPrimaryTrackCtgsDom,
    patchPrimaryHiddenCtgDom,
    replaceRenderedAssemblySection,
  };
}
