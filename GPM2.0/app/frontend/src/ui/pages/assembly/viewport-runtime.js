import {
  areViewportScrollStatesEqual,
  buildFinalPathTrackViewportKey,
  buildMainTrackViewportKey,
  buildSubviewTrackViewportKey,
  normalizeViewportScrollState,
  resolvePersistedViewportScrollLeft,
} from "./scroll-position-state.js";
import {
  readTrackViewportMetrics,
  resolveActiveTrackScrollElement,
  resolveScrollLeftForViewportAnchorBp,
  resolveTrackScrollLeftForViewboxShift,
  resolveViewportAnchorBp,
} from "./track-viewport.js";

const ASSEMBLY_TRACK_RESIZE_BOUND = Symbol("assemblyTrackResizeBound");

function normalizeTrackViewportRole(role) {
  const normalized = String(role || "").trim().toLowerCase();
  if (normalized === "subview") {
    return "subview";
  }
  if (normalized === "final-path" || normalized === "finalpath") {
    return "finalPath";
  }
  return "primary";
}

function normalizeViewportWidthValue(value) {
  const numeric = Math.round(Number(value || 0));
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}

function normalizeTrackViewportWidths(widths) {
  if (typeof widths === "number") {
    const resolvedWidth = normalizeViewportWidthValue(widths);
    return {
      primary: resolvedWidth,
      subview: resolvedWidth,
      finalPath: resolvedWidth,
    };
  }
  return {
    primary: normalizeViewportWidthValue(widths?.primary),
    subview: normalizeViewportWidthValue(widths?.subview),
    finalPath: normalizeViewportWidthValue(widths?.finalPath ?? widths?.["final-path"]),
  };
}

export function resolveMeasuredTrackViewportWidths(nextWidths, currentWidths = {}) {
  const normalizedCurrent = normalizeTrackViewportWidths(currentWidths);
  const normalizedNext = normalizeTrackViewportWidths(nextWidths);
  return {
    primary: normalizedNext.primary || normalizedCurrent.primary || 1200,
    subview: normalizedNext.subview || normalizedCurrent.subview || normalizedCurrent.primary || 1200,
    finalPath: normalizedNext.finalPath || normalizedCurrent.finalPath || normalizedCurrent.primary || 1200,
  };
}

export function haveMeasuredTrackViewportWidthsChanged(currentWidths, nextWidths) {
  const normalizedCurrent = normalizeTrackViewportWidths(currentWidths);
  const normalizedNext = normalizeTrackViewportWidths(nextWidths);
  return ["primary", "subview", "finalPath"].some((role) => {
    const nextValue = normalizedNext[role];
    if (nextValue <= 0) {
      return false;
    }
    return Math.abs(nextValue - normalizedCurrent[role]) > 1;
  });
}

export function createTrackViewportResizeCoordinator({
  getViewportWidths,
  getViewportWidth,
  getMeasuredWidths,
  getMeasuredWidth,
  setMeasuredWidths,
  setMeasuredWidth,
  onViewportResize,
}) {
  return {
    onResize() {
      const currentWidths = normalizeTrackViewportWidths(
        getMeasuredWidths?.() ?? getMeasuredWidth?.(),
      );
      const nextWidths = resolveMeasuredTrackViewportWidths(
        getViewportWidths?.() ?? getViewportWidth?.(),
        currentWidths,
      );
      if (!haveMeasuredTrackViewportWidthsChanged(currentWidths, nextWidths)) {
        return false;
      }
      if (typeof setMeasuredWidths === "function") {
        setMeasuredWidths(nextWidths);
      } else if (typeof setMeasuredWidth === "function") {
        setMeasuredWidth(nextWidths.primary);
      }
      onViewportResize?.(typeof getViewportWidths === "function" ? nextWidths : nextWidths.primary);
      return true;
    },
  };
}

export function createAssemblyViewportController({
  session,
  getPersistDeps = () => ({}),
  getTimerApi = () => globalThis,
  getWindow = () => globalThis.window,
  persistProjectAssemblyViewStateFromStore,
  rerender,
}) {
  function getMeasuredTrackViewportPx(role = "primary") {
    const normalizedRole = normalizeTrackViewportRole(role);
    return session.measuredTrackViewportPxByRole[normalizedRole]
      || session.measuredTrackViewportPxByRole.primary
      || 1200;
  }

  function readAssemblyTrackViewportWidths(host) {
    const primaryScroll = host?.querySelector?.(".assembly-track-scroll[data-track-role='primary']") || null;
    const subviewScroll = host?.querySelector?.(".assembly-track-scroll.subview-track-scroll") || null;
    const finalPathScroll =
      host?.querySelector?.("[data-final-path-graph-viewport]")
      || host?.querySelector?.(".assembly-final-path-svg-wrap")
      || null;
    return {
      primary: normalizeViewportWidthValue(primaryScroll?.clientWidth),
      subview: normalizeViewportWidthValue(subviewScroll?.clientWidth),
      finalPath: normalizeViewportWidthValue(finalPathScroll?.clientWidth),
    };
  }

  function bindTrackViewportResize(host, store) {
    const routeHost = host?.closest?.("#route-host") || null;
    if (routeHost && routeHost !== host) {
      return;
    }
    const windowObject = getWindow();
    if (typeof windowObject?.addEventListener !== "function") {
      return;
    }
    if (host[ASSEMBLY_TRACK_RESIZE_BOUND]) {
      return;
    }
    const coordinator = createTrackViewportResizeCoordinator({
      getViewportWidths: () => readAssemblyTrackViewportWidths(host),
      getMeasuredWidths: () => session.measuredTrackViewportPxByRole,
      setMeasuredWidths: (nextWidths) => {
        session.measuredTrackViewportPxByRole = resolveMeasuredTrackViewportWidths(
          nextWidths,
          session.measuredTrackViewportPxByRole,
        );
      },
      onViewportResize: () => {
        rerender(host, store);
      },
    });
    const onResize = () => {
      coordinator.onResize();
    };
    windowObject.addEventListener("resize", onResize);
    host[ASSEMBLY_TRACK_RESIZE_BOUND] = {
      coordinator,
      onResize,
    };
  }

  function setAssemblyViewportScrollState(store, fieldName, nextValue) {
    const state = store.getState();
    const normalizedNextValue = normalizeViewportScrollState(nextValue);
    if (areViewportScrollStatesEqual(state.assembly?.[fieldName], normalizedNextValue)) {
      return false;
    }
    store.setState({
      ...state,
      assembly: {
        ...state.assembly,
        [fieldName]: normalizedNextValue,
      },
    });
    return true;
  }

  function schedulePersistAssemblyScrollState(
    host,
    store,
    deps = getPersistDeps(),
    timerApi = getTimerApi(),
  ) {
    if (session.pendingAssemblyScrollStatePersistTimer !== null) {
      timerApi.clearTimeout(session.pendingAssemblyScrollStatePersistTimer);
    }
    session.pendingAssemblyScrollStatePersistTimer = timerApi.setTimeout(() => {
      session.pendingAssemblyScrollStatePersistTimer = null;
      void persistProjectAssemblyViewStateFromStore(host, store, deps);
    }, 120);
  }

  function applyTrackScrollLeft(trackScrollEls, scrollLeft, sourceElement = null) {
    trackScrollEls.forEach((element) => {
      if (element === sourceElement) {
        return;
      }
      element.scrollLeft = scrollLeft;
    });
  }

  function bindTrackScrollSync(host, store, deps = {}) {
    const schedulePersistScrollState =
      deps.schedulePersistAssemblyScrollState || schedulePersistAssemblyScrollState;
    const requestedScope = String(deps.scope || "all").trim().toLowerCase();
    const scope = ["main", "subview", "final-path"].includes(requestedScope)
      ? requestedScope
      : "all";
    const shouldBindMain = scope === "all" || scope === "main";
    const shouldBindSubview = scope === "all" || scope === "subview";
    const shouldBindFinalPath = scope === "all" || scope === "final-path";
    const hasTemporaryLoadingMarkup = Boolean(store.getState().assembly?.loading);
    const shouldClearMissing = scope === "all" && !hasTemporaryLoadingMarkup;
    let viewportChanged = false;
    const nextMeasuredTrackViewportWidths = resolveMeasuredTrackViewportWidths(
      readAssemblyTrackViewportWidths(host),
      session.measuredTrackViewportPxByRole,
    );
    if (haveMeasuredTrackViewportWidthsChanged(
      session.measuredTrackViewportPxByRole,
      nextMeasuredTrackViewportWidths,
    )) {
      session.measuredTrackViewportPxByRole = nextMeasuredTrackViewportWidths;
      viewportChanged = true;
    }
    const trackScrollEls = Array.from(
      host?.querySelectorAll?.(".assembly-track-scroll[data-track-role]") || [],
    );
    const subviewTrackScrollEls = trackScrollEls.filter(
      (element) => String(element.dataset.trackRole || "").trim() === "subview",
    );
    const syncedTrackScrollEls = trackScrollEls.filter(
      (element) => String(element.dataset.trackRole || "").trim() !== "subview",
    );

    if (shouldBindMain && !syncedTrackScrollEls.length && shouldClearMissing) {
      session.lastTrackViewportKey = "";
      session.lastTrackScrollLeft = 0;
      session.lastPrimaryTrackViewboxMinX = 0;
      if (setAssemblyViewportScrollState(store, "trackScrollState", {})) {
        schedulePersistScrollState(host, store);
      }
    } else if (shouldBindMain && syncedTrackScrollEls.length) {
      const primaryScroll = syncedTrackScrollEls.find(
        (element) => element.dataset.trackRole === "primary",
      );
      const currentPrimaryViewboxMinX = Number(primaryScroll?.dataset.trackViewboxMinX || 0);
      if (Number.isFinite(currentPrimaryViewboxMinX)) {
        session.lastTrackScrollLeft = resolveTrackScrollLeftForViewboxShift(
          session.lastTrackScrollLeft,
          session.lastPrimaryTrackViewboxMinX,
          currentPrimaryViewboxMinX,
          { preserveViewport: !session.trackContigDragActive },
        );
        session.lastPrimaryTrackViewboxMinX = currentPrimaryViewboxMinX;
      }
      if (session.pendingPrimaryViewportAnchorBp !== null) {
        const anchoredScrollLeft = resolveScrollLeftForViewportAnchorBp(
          session.pendingPrimaryViewportAnchorBp,
          readTrackViewportMetrics(primaryScroll, "primary"),
        );
        if (anchoredScrollLeft !== null) {
          session.lastTrackScrollLeft = anchoredScrollLeft;
        }
        session.pendingPrimaryViewportAnchorBp = null;
      }

      const state = store.getState();
      const nextViewportKey = buildMainTrackViewportKey(state);
      const shouldApplyPendingFocus = Boolean(session.pendingTrackAutoFocusMode);
      if (nextViewportKey !== session.lastTrackViewportKey || shouldApplyPendingFocus) {
        session.lastTrackViewportKey = nextViewportKey;
        const persistedScrollLeft = resolvePersistedViewportScrollLeft(
          state.assembly.trackScrollState,
          nextViewportKey,
        );
        if (shouldApplyPendingFocus) {
          const focusCenter = Number(primaryScroll?.dataset.focusCenter || 0);
          const focusStart = Number(primaryScroll?.dataset.focusStart || 0);
          const viewportWidth = primaryScroll?.clientWidth || 0;
          if (session.pendingTrackAutoFocusMode === "start") {
            session.lastTrackScrollLeft = Math.max(0, Math.round(focusStart));
          } else {
            session.lastTrackScrollLeft = Math.max(0, Math.round(focusCenter - viewportWidth / 2));
          }
        } else if (session.suppressNextTrackAutoFocus) {
          session.suppressNextTrackAutoFocus = false;
        } else if (persistedScrollLeft !== null) {
          session.lastTrackScrollLeft = persistedScrollLeft;
        } else {
          const focusCenter = Number(primaryScroll?.dataset.focusCenter || 0);
          const viewportWidth = primaryScroll?.clientWidth || 0;
          session.lastTrackScrollLeft = Math.max(0, Math.round(focusCenter - viewportWidth / 2));
        }
        session.pendingTrackAutoFocusMode = null;
      }
      if (setAssemblyViewportScrollState(store, "trackScrollState", {
        viewportKey: session.lastTrackViewportKey,
        scrollLeft: session.lastTrackScrollLeft,
      })) {
        schedulePersistScrollState(host, store);
      }
      applyTrackScrollLeft(syncedTrackScrollEls, session.lastTrackScrollLeft);

      let syncing = false;
      syncedTrackScrollEls.forEach((element) => {
        element.addEventListener("scroll", () => {
          if (syncing) {
            return;
          }
          syncing = true;
          session.lastTrackScrollLeft = element.scrollLeft;
          applyTrackScrollLeft(syncedTrackScrollEls, session.lastTrackScrollLeft, element);
          if (setAssemblyViewportScrollState(store, "trackScrollState", {
            viewportKey: session.lastTrackViewportKey,
            scrollLeft: session.lastTrackScrollLeft,
          })) {
            schedulePersistScrollState(host, store);
          }
          syncing = false;
        });
      });
    }

    if (shouldBindSubview && !subviewTrackScrollEls.length && shouldClearMissing) {
      session.lastSubviewViewportKey = "";
      session.lastSubviewScrollLeft = 0;
      if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {})) {
        schedulePersistScrollState(host, store);
      }
    } else if (shouldBindSubview && subviewTrackScrollEls.length) {
      const state = store.getState();
      const nextSubviewViewportKey = buildSubviewTrackViewportKey(state);
      if (nextSubviewViewportKey !== session.lastSubviewViewportKey) {
        session.lastSubviewViewportKey = nextSubviewViewportKey;
        session.lastSubviewScrollLeft = resolvePersistedViewportScrollLeft(
          state.assembly.subviewTrackScrollState,
          nextSubviewViewportKey,
        ) ?? 0;
      }
      const primarySubviewScroll = subviewTrackScrollEls[0] || null;
      if (session.pendingSubviewViewportAnchorBp !== null) {
        const anchoredScrollLeft = resolveScrollLeftForViewportAnchorBp(
          session.pendingSubviewViewportAnchorBp,
          readTrackViewportMetrics(primarySubviewScroll, "subview"),
        );
        if (anchoredScrollLeft !== null) {
          session.lastSubviewScrollLeft = anchoredScrollLeft;
        }
        session.pendingSubviewViewportAnchorBp = null;
      }
      if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {
        viewportKey: session.lastSubviewViewportKey,
        scrollLeft: session.lastSubviewScrollLeft,
      })) {
        schedulePersistScrollState(host, store);
      }
      applyTrackScrollLeft(subviewTrackScrollEls, session.lastSubviewScrollLeft);

      let subviewSyncing = false;
      subviewTrackScrollEls.forEach((element) => {
        element.addEventListener("scroll", () => {
          if (subviewSyncing) {
            return;
          }
          subviewSyncing = true;
          session.lastSubviewScrollLeft = element.scrollLeft;
          applyTrackScrollLeft(subviewTrackScrollEls, session.lastSubviewScrollLeft, element);
          if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {
            viewportKey: session.lastSubviewViewportKey,
            scrollLeft: session.lastSubviewScrollLeft,
          })) {
            schedulePersistScrollState(host, store);
          }
          subviewSyncing = false;
        });
      });
    }

    if (shouldBindFinalPath) {
      const finalPathScrollEl =
        host?.querySelector?.("[data-final-path-graph-viewport]")
        || host?.querySelector?.(".assembly-final-path-svg-wrap")
        || null;
      if (finalPathScrollEl) {
        const state = store.getState();
        const nextFinalPathViewportKey = buildFinalPathTrackViewportKey(state);
        if (nextFinalPathViewportKey !== session.lastFinalPathViewportKey) {
          session.lastFinalPathViewportKey = nextFinalPathViewportKey;
          session.lastFinalPathScrollLeft = resolvePersistedViewportScrollLeft(
            state.assembly.finalPathTrackScrollState,
            nextFinalPathViewportKey,
          ) ?? 0;
        }
        if (setAssemblyViewportScrollState(store, "finalPathTrackScrollState", {
          viewportKey: session.lastFinalPathViewportKey,
          scrollLeft: session.lastFinalPathScrollLeft,
        })) {
          schedulePersistScrollState(host, store);
        }
        finalPathScrollEl.scrollLeft = session.lastFinalPathScrollLeft;
        let finalPathSyncing = false;
        if (typeof finalPathScrollEl.addEventListener === "function") {
          finalPathScrollEl.addEventListener("scroll", () => {
            if (finalPathSyncing) {
              return;
            }
            finalPathSyncing = true;
            session.lastFinalPathScrollLeft = Number(finalPathScrollEl.scrollLeft || 0);
            if (setAssemblyViewportScrollState(store, "finalPathTrackScrollState", {
              viewportKey: session.lastFinalPathViewportKey,
              scrollLeft: session.lastFinalPathScrollLeft,
            })) {
              schedulePersistScrollState(host, store);
            }
            finalPathSyncing = false;
          });
        }
      }
    }
    return viewportChanged;
  }

  function rememberTrackViewportAnchor(host, viewKey = "trackView") {
    const isSubview = viewKey === "subviewTrackView";
    const trackRole = isSubview ? "subview" : "primary";
    const scrollEl = resolveActiveTrackScrollElement(host, trackRole, null);
    const metrics = readTrackViewportMetrics(scrollEl, trackRole);
    const centerBp = resolveViewportAnchorBp(scrollEl?.scrollLeft || 0, metrics);
    if (centerBp === null) {
      if (isSubview) {
        session.pendingSubviewViewportAnchorBp = null;
      } else {
        session.pendingPrimaryViewportAnchorBp = null;
      }
      return null;
    }
    if (isSubview) {
      session.pendingSubviewViewportAnchorBp = centerBp;
    } else {
      session.pendingPrimaryViewportAnchorBp = centerBp;
    }
    return centerBp;
  }

  return {
    bindTrackScrollSync,
    bindTrackViewportResize,
    getMeasuredTrackViewportPx,
    readAssemblyTrackViewportWidths,
    rememberTrackViewportAnchor,
  };
}
