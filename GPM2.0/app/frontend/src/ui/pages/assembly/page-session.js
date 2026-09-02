const DEFAULT_TRACK_VIEWPORT_WIDTHS = Object.freeze({
  primary: 1200,
  subview: 1200,
  finalPath: 1200,
});

function normalizeViewportWidths(nextWidths = null) {
  const source = nextWidths && typeof nextWidths === "object" ? nextWidths : {};
  return Object.fromEntries(
    Object.entries(DEFAULT_TRACK_VIEWPORT_WIDTHS).map(([role, fallback]) => {
      const value = Number(source[role]);
      return [role, Number.isFinite(value) && value > 0 ? value : fallback];
    }),
  );
}

function createSubviewRenderCache() {
  return {
    filteredRefCtgs: new WeakMap(),
    segmentPairs: new Map(),
  };
}

export function createAssemblyPageSession() {
  return {
    lastSupportDsSessionKey: "",
    lastSupportDsSelection: null,
    lastTrackViewportKey: "",
    lastTrackScrollLeft: 0,
    lastPrimaryTrackViewboxMinX: 0,
    lastSubviewViewportKey: "",
    lastSubviewScrollLeft: 0,
    lastFinalPathViewportKey: "",
    lastFinalPathScrollLeft: 0,
    pendingAssemblyScrollStatePersistTimer: null,
    measuredTrackViewportPxByRole: normalizeViewportWidths(),
    suppressNextTrackAutoFocus: false,
    subviewPairwiseEvidenceRequestSeq: 0,
    pendingTrackAutoFocusMode: null,
    trackContigDragActive: false,
    pendingPrimaryViewportAnchorBp: null,
    pendingSubviewViewportAnchorBp: null,
    deferredRerenderCoordinator: null,
    suppressTrackContigClickUntil: 0,
    assemblyConfirmDialogSeq: 0,
    pendingAssemblyConfirmResolvers: new Map(),
    subviewRenderCache: createSubviewRenderCache(),
    finalPathGraphPreviewState: null,
    grtResultToastTimer: null,
    projectViewMutationCoordinator: createProjectViewMutationCoordinator(),
  };
}

export const assemblyPageSession = createAssemblyPageSession();

export function resetAssemblyPageSession(nextWidths = null, { timerApi = globalThis } = {}) {
  if (assemblyPageSession.pendingAssemblyScrollStatePersistTimer !== null) {
    timerApi?.clearTimeout?.(assemblyPageSession.pendingAssemblyScrollStatePersistTimer);
  }
  if (assemblyPageSession.grtResultToastTimer !== null) {
    timerApi?.clearTimeout?.(assemblyPageSession.grtResultToastTimer);
  }
  assemblyPageSession.deferredRerenderCoordinator?.destroy?.();
  assemblyPageSession.deferredRerenderCoordinator?.cancel?.();
  assemblyPageSession.pendingAssemblyConfirmResolvers.forEach((resolve) => resolve(false));
  assemblyPageSession.pendingAssemblyConfirmResolvers.clear();
  assemblyPageSession.projectViewMutationCoordinator?.invalidate?.();

  Object.assign(assemblyPageSession, createAssemblyPageSession(), {
    measuredTrackViewportPxByRole: normalizeViewportWidths(nextWidths),
  });
  return assemblyPageSession.measuredTrackViewportPxByRole;
}

export function destroyAssemblyPageSession(options = {}) {
  resetAssemblyPageSession(null, options);
}
import { createProjectViewMutationCoordinator } from "./project-view-mutation-coordinator.js";
