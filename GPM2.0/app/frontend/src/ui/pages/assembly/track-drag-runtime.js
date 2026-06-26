import { normalizeSupportDatasetId, normalizeTrackRole } from "./selection-state.js";

const ASSEMBLY_TRACK_CONTIG_DRAG_BOUND = Symbol("assemblyTrackContigDragBound");
const ASSEMBLY_SUBVIEW_TRACK_CONTIG_DRAG_BOUND = Symbol("assemblySubviewTrackContigDragBound");
const TRACK_CONTIG_CLICK_SUPPRESS_MS = 250;

const REQUIRED_TRACK_DRAG_DEPS = [
  "applyTrackDragOffset",
  "clearTrackDragPreview",
  "convertTrackOffsetPxToBp",
  "resolveActiveTrackScrollElement",
  "previewTrackContigDrag",
  "resolveTrackDragOffsetBp",
  "roundTrackMetric",
  "persistTrackDragOffsets",
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
  };
}

export function bindTrackContigDrag(host, store, deps) {
  assertTrackDragDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host[ASSEMBLY_TRACK_CONTIG_DRAG_BOUND]) {
    return;
  }

  host.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) {
      return;
    }
    const state = store.getState();
    if (state.assembly.activeTab !== "assembly") {
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
    let dragging = false;
    let pendingOffsetBp = baseOffsetBp;

    const scheduler = createFrameScheduler(() => {
      const offsetPx = deps.roundTrackMetric(
        deltaOffsetBpToPx(pendingOffsetBp - baseOffsetBp, deps, scaleContext),
      );
      deps.previewTrackContigDrag(host, {
        trackRole,
        assemblyCtgId,
        ...(datasetId ? { datasetId } : {}),
        ...(phasedTrackId ? { phasedTrackId } : {}),
        ...(phasedTrackItemId ? { phasedTrackItemId } : {}),
        offsetPx,
      });
    });

    const onPointerMove = (moveEvent) => {
      const currentClientX = Number(moveEvent.clientX || 0);
      const currentScrollEl = deps.resolveActiveTrackScrollElement(host, "primary", scrollEl);
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

    const onPointerUp = () => {
      const windowObject = getWindowObject();
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      try {
        scheduler.flushNow();
        deps.clearTrackDragPreview(host);
        if (dragging) {
          deps.applyTrackDragOffset(host, store, {
            trackRole,
            assemblyCtgId,
            ...(datasetId ? { datasetId } : {}),
            ...(phasedTrackId ? { phasedTrackId } : {}),
            ...(phasedTrackItemId ? { phasedTrackItemId } : {}),
            offsetBp: pendingOffsetBp,
          });
          void deps.persistTrackDragOffsets(host, store);
        }
        if (dragging) {
          deps.setSuppressTrackContigClickUntil(Date.now() + TRACK_CONTIG_CLICK_SUPPRESS_MS);
        }
      } finally {
        deps.setTrackContigDragActive(false);
      }
    };

    const windowObject = getWindowObject();
    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
  });

  host[ASSEMBLY_TRACK_CONTIG_DRAG_BOUND] = true;
}

export function bindSubviewTrackContigDrag(host, store, deps) {
  assertSubviewTrackDragDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host[ASSEMBLY_SUBVIEW_TRACK_CONTIG_DRAG_BOUND]) {
    return;
  }

  host.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) {
      return;
    }
    const state = store.getState();
    if (state.assembly.activeTab !== "assembly") {
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
    const slot = normalizeSubviewTrackSlot(trackNode.getAttribute("data-subview-track-slot"));
    const contigId = normalizeSupportDatasetId(trackNode.getAttribute("data-subview-contig-id"));
    if (!slot || !contigId) {
      return;
    }

    event.preventDefault();
    const startClientX = Number(event.clientX || 0);
    const startScrollLeft = Number(scrollEl.scrollLeft || 0);
    const scaleContext = {
      domainSpanBp: Number(scrollEl.dataset.subviewDomainSpanBp || 0),
      innerWidth: Number(scrollEl.dataset.subviewInnerWidth || 0),
    };
    const baseOffsetBp = deps.resolveSubviewTrackDragOffsetBp(
      state.assembly.subviewTrackDragOffsets,
      slot,
      contigId,
      scaleContext,
    );
    let dragging = false;
    let pendingOffsetBp = baseOffsetBp;

    const scheduler = createFrameScheduler(() => {
      const offsetPx = deps.roundTrackMetric(
        deltaOffsetBpToPx(pendingOffsetBp - baseOffsetBp, deps, scaleContext),
      );
      deps.previewSubviewTrackContigDrag(host, {
        slot,
        contigId,
        offsetPx,
      });
    });

    const onPointerMove = (moveEvent) => {
      const currentClientX = Number(moveEvent.clientX || 0);
      const currentScrollEl = deps.resolveActiveTrackScrollElement(host, "subview", scrollEl);
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

    const onPointerUp = () => {
      const windowObject = getWindowObject();
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      scheduler.flushNow();
      deps.clearSubviewTrackDragPreview(host);
      if (dragging) {
        deps.applySubviewTrackDragOffset(host, store, {
          slot,
          contigId,
          offsetBp: pendingOffsetBp,
        });
        void deps.persistSubviewTrackDragOffsets(host, store);
      }
    };

    const windowObject = getWindowObject();
    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
  });

  host[ASSEMBLY_SUBVIEW_TRACK_CONTIG_DRAG_BOUND] = true;
}

function deltaOffsetBpToPx(offsetBp, deps, scaleContext) {
  const converted = deps.convertTrackOffsetPxToBp(1, scaleContext);
  if (!Number.isFinite(converted) || Math.abs(converted) < 0.000001) {
    return 0;
  }
  return Number(offsetBp || 0) / converted;
}
