import { collectContigDragTargets, buildSourceFragmentDragPayload } from "./source-fragment-drag.js";
import { normalizeSupportDatasetId, normalizeTrackRole } from "./selection-state.js";

const ASSEMBLY_TRACK_CONTIG_DRAG_BOUND = Symbol("assemblyTrackContigDragBound");
const ASSEMBLY_SUBVIEW_TRACK_CONTIG_DRAG_BOUND = Symbol("assemblySubviewTrackContigDragBound");
const TRACK_CONTIG_CLICK_SUPPRESS_MS = 250;

const REQUIRED_TRACK_DRAG_DEPS = [
  "clearTrackDragPreview",
  "commitTrackDragOffset",
  "convertTrackOffsetPxToBp",
  "resolveActiveTrackScrollElement",
  "previewTrackContigDrag",
  "resolveTrackDragOffsetBp",
  "roundTrackMetric",
  "setTrackContigDragActive",
  "setSuppressTrackContigClickUntil",
];

const REQUIRED_SUBVIEW_TRACK_DRAG_DEPS = [
  "applySubviewTrackDragOffset",
  "clearSubviewTrackDragPreview",
  "convertTrackOffsetPxToBp",
  "persistSubviewTrackDragOffsets",
  "previewSubviewTrackContigDrag",
  "resolveActiveTrackScrollElement",
  "resolveSubviewTrackDragOffsetBp",
  "roundTrackMetric",
];

function assertTrackDragDeps(deps) {
  const missing = REQUIRED_TRACK_DRAG_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing track drag runtime deps: ${missing.join(", ")}`);
}

function assertSubviewTrackDragDeps(deps) {
  const missing = REQUIRED_SUBVIEW_TRACK_DRAG_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing subview track drag runtime deps: ${missing.join(", ")}`);
}

function normalizeSubviewTrackSlot(slot) {
  const normalizedSlot = String(slot || "").trim();
  if (normalizedSlot === "top" || normalizedSlot === "bottom") {
    return normalizedSlot;
  }
  return "";
}

function getWindowObject() {
  return globalThis.window;
}

function hasBoundTrackDragHost(host, bindingKey) {
  // A partial panel replacement still bubbles to the bound route host.
  // Per-element guards alone would install a second owner for every gesture.
  let current = host;
  while (current) {
    if (current[bindingKey]) return true;
    current = current.parentElement || current.parentNode || null;
  }
  return false;
}

function createFrameScheduler(flush) {
  let frameToken = null;
  return {
    schedule() {
      if (frameToken !== null) {
        return;
      }
      const windowObject = getWindowObject();
      if (typeof windowObject?.requestAnimationFrame === "function") {
        frameToken = windowObject.requestAnimationFrame(() => {
          frameToken = null;
          flush();
        });
        return;
      }
      frameToken = setTimeout(() => {
        frameToken = null;
        flush();
      }, 0);
    },
    flushNow() {
      if (frameToken === null) {
        return false;
      }
      const windowObject = getWindowObject();
      if (typeof windowObject?.cancelAnimationFrame === "function") {
        windowObject.cancelAnimationFrame(frameToken);
      } else {
        clearTimeout(frameToken);
      }
      frameToken = null;
      flush();
      return true;
    },
    cancel() {
      if (frameToken === null) {
        return false;
      }
      const windowObject = getWindowObject();
      if (typeof windowObject?.cancelAnimationFrame === "function") {
        windowObject.cancelAnimationFrame(frameToken);
      } else {
        clearTimeout(frameToken);
      }
      frameToken = null;
      return true;
    },
  };
}

function resolveSubviewPointerWorldX(scrollEl, clientX) {
  const pointerX = Number(clientX);
  const viewportLeft = Number(scrollEl?.getBoundingClientRect?.()?.left);
  const viewBoxMinX = Number(scrollEl?.dataset?.subviewViewboxMinX || 0);
  const scrollLeft = Number(scrollEl?.scrollLeft || 0);
  if (
    !Number.isFinite(pointerX)
    || !Number.isFinite(viewportLeft)
    || !Number.isFinite(viewBoxMinX)
    || !Number.isFinite(scrollLeft)
  ) {
    return null;
  }
  return viewBoxMinX + scrollLeft + pointerX - viewportLeft;
}

export function bindTrackContigDrag(host, store, deps) {
  assertTrackDragDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (hasBoundTrackDragHost(host, ASSEMBLY_TRACK_CONTIG_DRAG_BOUND)) {
    return;
  }

  host.addEventListener("pointerdown", (event) => {
    if (event.defaultPrevented || event.target?.closest?.("[data-view-interaction-mode='hand']")?.dataset?.viewInteractionMode === "hand" || event.button !== 0 || event.ctrlKey || event.metaKey) {
      return;
    }
    const state = store.getState();
    if (state.assembly.activeTab !== "assembly" || state.assembly.mainViewHistory?.inFlight === true) {
      return;
    }
    const trackNode = event.target?.closest?.("[data-track-contig-id][data-track-role]");
    if (!trackNode) {
      return;
    }
    const trackRole = normalizeTrackRole(trackNode.getAttribute("data-track-role"));
    const sourceKind = String(trackNode.getAttribute("data-track-source-kind") || "").trim();
    const assemblyCtgId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-contig-id"));
    const datasetId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-dataset-id"));
    const phasedTrackId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-phased-track-id"));
    const phasedTrackItemId = normalizeSupportDatasetId(trackNode.getAttribute("data-track-phased-track-item-id"));
    if (trackRole === "ref" || sourceKind === "ref_segment") {
      return;
    }
    if (!trackRole || !assemblyCtgId) {
      return;
    }
    const scrollEl = trackNode.closest(".assembly-track-scroll[data-track-role='primary']");
    if (!scrollEl) {
      return;
    }

    event.preventDefault();
    deps.setTrackContigDragActive(true);
    const startClientX = Number(event.clientX || 0);
    const startScrollLeft = Number(scrollEl.scrollLeft || 0);
    const scaleContext = {
      domainSpanBp: Number(scrollEl.dataset.trackDomainSpanBp || 0),
      innerWidth: Number(scrollEl.dataset.trackInnerWidth || 0),
    };
    const baseOffsetBp = deps.resolveTrackDragOffsetBp(
      state.assembly.trackDragOffsets,
      trackRole,
      assemblyCtgId,
      {
        ...scaleContext,
        datasetId,
        phasedTrackId,
        phasedTrackItemId,
      },
    );
    const targets = collectContigDragTargets(scrollEl, trackNode, {
      selectedIds: state.assembly.trackSelectedCtgIds || [],
    });
    const baseOffsets = targets.map((target) => deps.resolveTrackDragOffsetBp(
      state.assembly.trackDragOffsets, target.trackRole, target.assemblyCtgId,
      { ...scaleContext, ...target },
    ));
    const dragPayload = (offsetBp) => buildSourceFragmentDragPayload(
      targets, baseOffsets, offsetBp - baseOffsetBp, deps.roundTrackMetric, true,
    );
    let dragging = false;
    let pendingOffsetBp = baseOffsetBp;
    const fullRangeDrag = state.assembly.trackView?.fullRange === true
      && typeof deps.previewFullRangeTrackContigDrag === "function"
      && typeof deps.clearFullRangeTrackDragPreview === "function";
    const dragHost = fullRangeDrag ? scrollEl.closest?.("#route-host") || host : host;
    let lastPointerClientX = startClientX;
    let cancelled = false;
    const sameContext = () => {
      const next = store.getState();
      return !next.assembly?.mainViewHistory?.inFlight && !next.assembly?.loading
        && next.session?.workspacePath === state.session?.workspacePath
        && next.session?.projectId === state.session?.projectId
        && next.assembly?.selectedChrName === state.assembly?.selectedChrName
        && next.assembly?.supportDatasetId === state.assembly?.supportDatasetId;
    };

    const scheduler = createFrameScheduler(() => {
      if (!sameContext()) { onPointerCancel(); return; }
      if (fullRangeDrag) {
        deps.previewFullRangeTrackContigDrag(dragHost, store, dragPayload(pendingOffsetBp));
        return;
      }
      const offsetPx = deps.roundTrackMetric(
        deltaOffsetBpToPx(pendingOffsetBp - baseOffsetBp, deps, scaleContext),
      );
      deps.previewTrackContigDrag(scrollEl, {
        trackRole,
        assemblyCtgId,
        ...(datasetId ? { datasetId } : {}),
        ...(phasedTrackId ? { phasedTrackId } : {}),
        ...(phasedTrackItemId ? { phasedTrackItemId } : {}),
        offsetPx,
        ...(targets.length > 1 ? { targets } : {}),
      });
    });

    const updatePendingOffset = (moveEvent) => {
      if (cancelled) return;
      if (!sameContext()) { onPointerCancel(); return; }
      if (!Number.isFinite(Number(moveEvent?.clientX))) return;
      const currentClientX = Number(moveEvent.clientX || 0);
      const currentScrollEl = deps.resolveActiveTrackScrollElement(dragHost, "primary", scrollEl);
      if (fullRangeDrag) {
        if (!dragging && Math.abs(currentClientX - startClientX) < 2) return;
        const deltaX = currentClientX - lastPointerClientX;
        if (!deltaX) return;
        dragging = true;
        // Rebase each physical pointer step onto the latest fitted scale. A
        // stationary release must not convert the auto-refit into extra motion.
        pendingOffsetBp = deps.roundTrackMetric(pendingOffsetBp + deps.convertTrackOffsetPxToBp(deltaX, {
          domainSpanBp: Number(currentScrollEl?.dataset?.trackDomainSpanBp || 0),
          innerWidth: Number(currentScrollEl?.dataset?.trackInnerWidth || 0),
        }));
        lastPointerClientX = currentClientX;
        scheduler.schedule();
        return;
      }
      const currentScrollLeft = Number(currentScrollEl?.scrollLeft || 0);
      const deltaX = deps.roundTrackMetric((currentClientX - startClientX) + (currentScrollLeft - startScrollLeft));
      if (!dragging && Math.abs(deltaX) < 2) {
        return;
      }
      dragging = true;
      pendingOffsetBp = deps.roundTrackMetric(
        baseOffsetBp + deps.convertTrackOffsetPxToBp(deltaX, scaleContext),
      );
      scheduler.schedule();
    };

    const onPointerMove = (moveEvent) => updatePendingOffset(moveEvent);
    const detachListeners = () => {
      const windowObject = getWindowObject();
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      windowObject?.removeEventListener?.("pointercancel", onPointerCancel, true);
    };
    const clearPreview = () => deps.clearTrackDragPreview(scrollEl);
    const onPointerUp = (upEvent) => {
      if (cancelled) return;
      detachListeners();
      try {
        updatePendingOffset(upEvent);
        if (cancelled) return;
        scheduler.flushNow();
        if (cancelled) return;
        if (fullRangeDrag) deps.clearFullRangeTrackDragPreview(dragHost, store);
        if (dragging) {
          deps.setSuppressTrackContigClickUntil(Date.now() + TRACK_CONTIG_CLICK_SUPPRESS_MS);
          const committed = deps.commitTrackDragOffset(dragHost, store, dragPayload(pendingOffsetBp));
          // Keep the released geometry until the authoritative refresh. Scope
          // cleanup to the old scroll node so it cannot erase a newer preview.
          void Promise.resolve(committed).then((changed) => {
            clearPreview();
            if (fullRangeDrag && changed === false) deps.clearFullRangeTrackDragPreview(dragHost, store, { cancelled: true, released: true });
          }, () => {
            clearPreview();
            if (fullRangeDrag) deps.clearFullRangeTrackDragPreview(dragHost, store, { cancelled: true, released: true });
          });
        } else {
          clearPreview();
        }
      } catch (error) {
        clearPreview();
        if (fullRangeDrag) deps.clearFullRangeTrackDragPreview(dragHost, store, { cancelled: true });
        throw error;
      } finally {
        deps.setTrackContigDragActive(false);
      }
    };
    const onPointerCancel = () => {
      cancelled = true;
      detachListeners();
      scheduler.cancel();
      clearPreview();
      if (fullRangeDrag) deps.clearFullRangeTrackDragPreview(dragHost, store, { cancelled: true });
      deps.setTrackContigDragActive(false);
    };

    const windowObject = getWindowObject();
    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
    windowObject?.addEventListener?.("pointercancel", onPointerCancel, true);
  });

  host[ASSEMBLY_TRACK_CONTIG_DRAG_BOUND] = true;
}

export function bindSubviewTrackContigDrag(host, store, deps) {
  assertSubviewTrackDragDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (hasBoundTrackDragHost(host, ASSEMBLY_SUBVIEW_TRACK_CONTIG_DRAG_BOUND)) {
    return;
  }

  const startDrag = (event) => {
    const runtimeHost = host;
    if (event.defaultPrevented || event.target?.closest?.("[data-view-interaction-mode='hand']")?.dataset?.viewInteractionMode === "hand" || event.button !== 0 || event.ctrlKey || event.metaKey) {
      return;
    }
    const state = store.getState();
    if (state.assembly.activeTab !== "assembly" || state.assembly.loading || state.assembly.mainViewHistory?.inFlight || state.assembly.sourceEditingReloadRequired) {
      return;
    }
    const trackNode = event.target?.closest?.("[data-subview-contig-id][data-subview-track-slot]");
    if (!trackNode) {
      return;
    }
    const scrollEl = trackNode.closest(".assembly-track-scroll[data-track-role='subview']");
    if (!scrollEl) {
      return;
    }
    // Anchor hit zones belong to this contig/member. A drag changes its
    // position, never materializes the anchor's display intervals as objects.
    const slot = normalizeSubviewTrackSlot(trackNode.getAttribute("data-subview-track-slot"));
    const contigId = normalizeSupportDatasetId(trackNode.getAttribute("data-subview-contig-id"));
    const compositionEntityKey = String(
      trackNode.getAttribute("data-subview-composition-entity-key") || "",
    ).trim();
    if (!slot || !contigId) {
      return;
    }

    event.preventDefault();
    const startClientX = Number(event.clientX || 0);
    const startScrollLeft = Number(scrollEl.scrollLeft || 0);
    const startCompositionPointerWorldX = compositionEntityKey
      ? resolveSubviewPointerWorldX(scrollEl, startClientX)
      : null;
    const scaleContext = {
      domainSpanBp: Number(scrollEl.dataset.subviewDomainSpanBp || 0),
      innerWidth: Number(scrollEl.dataset.subviewInnerWidth || 0),
    };
    const baseOffsetBp = compositionEntityKey ? 0 : deps.resolveSubviewTrackDragOffsetBp(
      state.assembly.subviewTrackDragOffsets,
      slot,
      contigId,
      scaleContext,
    );
    const targets = collectContigDragTargets(scrollEl, trackNode, {
      subview: true, selectedEntries: state.assembly.subview?.trackPairSelectedCtgs || [],
    });
    const baseOffsets = targets.map((target) => target.compositionEntityKey ? 0
      : deps.resolveSubviewTrackDragOffsetBp(state.assembly.subviewTrackDragOffsets,
        target.slot, target.contigId, scaleContext));
    const dragPayload = (offsetBp) => buildSourceFragmentDragPayload(
      targets, baseOffsets, offsetBp - baseOffsetBp, deps.roundTrackMetric, true,
    );
    let dragging = false;
    let pendingOffsetBp = baseOffsetBp;
    let previewAutoScrollDeltaPx = 0;
    let pendingPreviewScrollLeft = null;
    let pendingPreviewViewportLeftX = null;
    let pendingPointerClientX = startClientX;
    const fullRangeDrag = state.assembly.subviewTrackView?.fullRange === true
      && typeof deps.previewFullRangeSubviewContigDrag === "function"
      && typeof deps.clearFullRangeSubviewDragPreview === "function";
    const dragHost = fullRangeDrag ? scrollEl.closest?.("#route-host") || runtimeHost : runtimeHost;
    let lastPointerClientX = startClientX;
    let finished = false;
    const sameContext = () => {
      const next = store.getState();
      return !next.assembly?.mainViewHistory?.inFlight && !next.assembly?.loading
        && next.session?.workspacePath === state.session?.workspacePath
        && next.session?.projectId === state.session?.projectId
        && next.assembly?.selectedChrName === state.assembly?.selectedChrName
        && next.assembly?.subview === state.assembly?.subview;
    };

    const scheduler = createFrameScheduler(() => {
      if (!sameContext()) { finish(false); return; }
      if (fullRangeDrag) {
        deps.previewFullRangeSubviewContigDrag(dragHost, store, dragPayload(pendingOffsetBp));
        return;
      }
      const offsetPx = deps.roundTrackMetric(
        deltaOffsetBpToPx(pendingOffsetBp - baseOffsetBp, deps, scaleContext),
      );
      const previewResult = deps.previewSubviewTrackContigDrag(runtimeHost, {
        slot,
        contigId,
        ...(compositionEntityKey ? { compositionEntityKey } : {}),
        offsetPx,
        ...(targets.length > 1 ? { targets } : {}),
        pointerClientX: pendingPointerClientX,
      });
      const nextScrollLeft = Number(previewResult?.scrollLeft);
      if (Number.isFinite(nextScrollLeft)) {
        pendingPreviewScrollLeft = Math.max(0, nextScrollLeft);
        previewAutoScrollDeltaPx = pendingPreviewScrollLeft - startScrollLeft;
      }
      const nextViewportLeftX = Number(previewResult?.viewportLeftX);
      if (Number.isFinite(nextViewportLeftX)) {
        pendingPreviewViewportLeftX = nextViewportLeftX;
      }
    });

    const updatePendingPointerPosition = (pointerEvent) => {
      if (finished) return;
      if (!sameContext()) { finish(false); return; }
      const currentClientX = Number(pointerEvent?.clientX);
      if (!Number.isFinite(currentClientX)) {
        return;
      }
      pendingPointerClientX = currentClientX;
      const currentScrollEl = deps.resolveActiveTrackScrollElement(dragHost, "subview", scrollEl);
      if (fullRangeDrag) {
        if (!dragging && Math.abs(currentClientX - startClientX) < 2) return;
        const deltaX = currentClientX - lastPointerClientX;
        if (!deltaX) return;
        dragging = true;
        pendingOffsetBp = deps.roundTrackMetric(pendingOffsetBp + deps.convertTrackOffsetPxToBp(deltaX, {
          domainSpanBp: Number(currentScrollEl?.dataset?.subviewDomainSpanBp || 0),
          innerWidth: Number(currentScrollEl?.dataset?.subviewInnerWidth || 0),
        }));
        lastPointerClientX = currentClientX;
        scheduler.schedule();
        return;
      }
      const currentScrollLeft = Number(currentScrollEl?.scrollLeft || 0);
      const scrollDeltaX = (currentScrollLeft - startScrollLeft) - previewAutoScrollDeltaPx;
      const currentCompositionPointerWorldX = compositionEntityKey
        ? resolveSubviewPointerWorldX(currentScrollEl, currentClientX)
        : null;
      const deltaX = deps.roundTrackMetric(
        compositionEntityKey
          && startCompositionPointerWorldX !== null
          && currentCompositionPointerWorldX !== null
          ? currentCompositionPointerWorldX - startCompositionPointerWorldX
          : (currentClientX - startClientX) + scrollDeltaX,
      );
      if (!dragging && Math.abs(deltaX) < 2) {
        return;
      }
      dragging = true;
      pendingOffsetBp = deps.roundTrackMetric(
        baseOffsetBp + deps.convertTrackOffsetPxToBp(deltaX, scaleContext),
      );
      scheduler.schedule();
    };

    const onPointerMove = (moveEvent) => {
      updatePendingPointerPosition(moveEvent);
    };

    const finish = (shouldCommit) => {
      if (finished) return;
      // Async evidence or a context switch must not apply the drag to a new pair.
      if (!sameContext()) shouldCommit = false;
      const windowObject = getWindowObject();
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      windowObject?.removeEventListener?.("pointercancel", onPointerCancel, true);
      if (shouldCommit) {
        scheduler.flushNow();
      } else {
        scheduler.cancel();
      }
      if (finished) return;
      finished = true;
      deps.clearSubviewTrackDragPreview(runtimeHost);
      if (fullRangeDrag) deps.clearFullRangeSubviewDragPreview(dragHost, store);
      const hasEffectiveMovement = dragging
        && Math.abs(pendingOffsetBp - baseOffsetBp) >= 0.000001;
      if (shouldCommit && hasEffectiveMovement) {
        deps.setSuppressTrackContigClickUntil?.(Date.now() + TRACK_CONTIG_CLICK_SUPPRESS_MS);
        deps.applySubviewTrackDragOffset(dragHost, store, dragPayload(pendingOffsetBp));
        if (
          Number.isFinite(pendingPreviewScrollLeft)
          || Number.isFinite(pendingPreviewViewportLeftX)
        ) {
          const activeScrollEl = deps.resolveActiveTrackScrollElement(runtimeHost, "subview", scrollEl);
          if (activeScrollEl) {
            const activeViewboxMinX = Number(activeScrollEl.dataset?.subviewViewboxMinX || 0);
            const nextScrollLeft = Number.isFinite(pendingPreviewViewportLeftX)
              && Number.isFinite(activeViewboxMinX)
              ? pendingPreviewViewportLeftX - activeViewboxMinX
              : pendingPreviewScrollLeft;
            activeScrollEl.scrollLeft = Math.max(0, Number(nextScrollLeft) || 0);
          }
        }
        void deps.persistSubviewTrackDragOffsets(dragHost, store);
      } else {
        if (fullRangeDrag && dragging) deps.clearFullRangeSubviewDragPreview(dragHost, store, { cancelled: true });
      }
    };

    const onPointerUp = (upEvent) => {
      updatePendingPointerPosition(upEvent);
      finish(true);
    };
    const onPointerCancel = () => finish(false);

    const windowObject = getWindowObject();
    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
    windowObject?.addEventListener?.("pointercancel", onPointerCancel, true);

    return { onPointerMove, onPointerUp, onPointerCancel };
  };
  host.addEventListener("pointerdown", startDrag);

  host[ASSEMBLY_SUBVIEW_TRACK_CONTIG_DRAG_BOUND] = true;
}

function deltaOffsetBpToPx(offsetBp, deps, scaleContext) {
  const converted = deps.convertTrackOffsetPxToBp(1, scaleContext);
  if (!Number.isFinite(converted) || Math.abs(converted) < 0.000001) {
    return 0;
  }
  return Number(offsetBp || 0) / converted;
}
