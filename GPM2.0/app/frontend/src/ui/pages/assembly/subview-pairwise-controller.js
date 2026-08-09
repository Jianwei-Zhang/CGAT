import {
  getJunctionInspection,
  getTrackPairwiseEvidence,
} from "../../../services/workflow-api.js";
import { mapAssemblyError } from "./error-contract.js";
import {
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackPrefs,
} from "./track-prefs.js";
import { normalizeSupportDatasetId } from "./selection-state.js";
import {
  buildSubviewTrackPairPoolsFromAssembly,
  getSubviewState,
  normalizeSubviewSummarySelection,
  normalizeSubviewTrackSummary,
  resolveSubviewTrackSummaryCtgs,
} from "./subview-state.js";
import {
  buildSubviewPairwiseEvidenceKey,
  shouldLoadSubviewPairwiseEvidence,
  shouldRefetchSubviewPairwiseEvidence,
} from "./subview-pairwise-evidence-state.js";

export function createSubviewPairwiseController({
  session,
  rerenderSubviewPanel,
  scheduleDeferredSubviewPanelRerender,
}) {
  function issueSubviewPairwiseEvidenceRequestKey(summary, scope = {}) {
    const key = String(scope?.key || buildSubviewPairwiseEvidenceKey(summary, scope));
    if (!key) {
      return "";
    }
    session.subviewPairwiseEvidenceRequestSeq += 1;
    return `${key}|req:${session.subviewPairwiseEvidenceRequestSeq}`;
  }

  function resolveSubviewPairwiseEvidenceScope(state, summary) {
    if (!shouldLoadSubviewPairwiseEvidence(summary)) {
      return null;
    }
    const mode = String(summary?.mode || "").trim();
    if (mode === "track-pair") {
      const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
      const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
      const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
      const topAssemblyCtgIds = resolveSubviewTrackSummaryCtgs(topTrack, pools)
        .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
        .filter((value) => value);
      const bottomAssemblyCtgIds = resolveSubviewTrackSummaryCtgs(bottomTrack, pools)
        .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
        .filter((value) => value);
      return {
        mode: "track-pair",
        topAssemblyCtgIds,
        bottomAssemblyCtgIds,
        key: buildSubviewPairwiseEvidenceKey(summary, {
          topAssemblyCtgIds,
          bottomAssemblyCtgIds,
        }),
      };
    }
    return {
      mode: "2-contig",
      key: buildSubviewPairwiseEvidenceKey(summary),
    };
  }

  function buildInitialSubviewPairwiseEvidence(
    summary,
    trackPrefs = {},
    previousEvidence = null,
    state = null,
  ) {
    if (!shouldLoadSubviewPairwiseEvidence(summary)) {
      return null;
    }
    const prefs = resolveTrackPrefs(trackPrefs || {});
    const scope = resolveSubviewPairwiseEvidenceScope(state || { assembly: {} }, summary) || {};
    const key = String(scope?.key || buildSubviewPairwiseEvidenceKey(summary, scope));
    const previousForKey =
      previousEvidence && String(previousEvidence?.key || "") === key
        ? previousEvidence
        : null;
    const requestedMinAlignmentLength = Math.max(
      1,
      normalizePositiveInt(prefs.alignmentLength) ?? 1,
    );
    const requestedMinMapq = Math.max(0, normalizeNonNegativeInt(prefs.mapq) ?? 0);
    const loadedMinAlignmentLength = Math.max(
      1,
      normalizePositiveInt(
        previousForKey?.loadedMinAlignmentLength ?? previousForKey?.minAlignmentLength,
      ) ?? requestedMinAlignmentLength,
    );
    const loadedMinMapq = Math.max(
      0,
      normalizeNonNegativeInt(previousForKey?.loadedMinMapq ?? previousForKey?.minMapq)
        ?? requestedMinMapq,
    );
    const shouldRefetch = shouldRefetchSubviewPairwiseEvidence({
      summary,
      trackPrefs: prefs,
      evidence: previousForKey,
      scope,
    });
    return {
      key,
      requestKey: shouldRefetch
        ? issueSubviewPairwiseEvidenceRequestKey(summary, scope)
        : String(previousForKey?.requestKey || ""),
      requestedMinAlignmentLength,
      requestedMinMapq,
      loadedMinAlignmentLength,
      loadedMinMapq,
      minAlignmentLength: requestedMinAlignmentLength,
      minMapq: requestedMinMapq,
      status: shouldRefetch ? "loading" : String(previousForKey?.status || "loaded"),
      hits: Array.isArray(previousForKey?.hits) ? previousForKey.hits : [],
      evidenceSource: String(previousForKey?.evidenceSource || ""),
      evidenceHitCount: Number(previousForKey?.evidenceHitCount || 0),
      error: shouldRefetch ? "" : String(previousForKey?.error || ""),
    };
  }

  function resolveSubviewPairwiseEvidenceParams(state, summary) {
    const scope = resolveSubviewPairwiseEvidenceScope(state, summary);
    if (!scope?.key) {
      return null;
    }
    const workspaceRoot = String(state.session?.workspacePath || "").trim();
    const projectId = Number(state.session?.projectId || 0);
    if (!workspaceRoot || !projectId) {
      return null;
    }
    const evidence = state.assembly?.subview?.pairwiseEvidence || null;
    const prefs = resolveTrackPrefs(
      state.assembly?.subviewTrackView || state.assembly?.trackView || {},
    );
    const baseParams = {
      mode: scope.mode,
      key: scope.key,
      requestKey: String(evidence?.requestKey || ""),
      workspaceRoot,
      projectId,
      minAlignmentLength: Math.max(
        1,
        normalizePositiveInt(evidence?.requestedMinAlignmentLength ?? prefs.alignmentLength) ?? 1,
      ),
      minMapq: Math.max(
        0,
        normalizeNonNegativeInt(evidence?.requestedMinMapq ?? prefs.mapq) ?? 0,
      ),
    };
    if (scope.mode === "track-pair") {
      if (!scope.topAssemblyCtgIds?.length || !scope.bottomAssemblyCtgIds?.length) {
        return null;
      }
      return {
        ...baseParams,
        topAssemblyCtgIds: scope.topAssemblyCtgIds,
        bottomAssemblyCtgIds: scope.bottomAssemblyCtgIds,
      };
    }
    const top = normalizeSubviewSummarySelection(summary?.top);
    const bottom = normalizeSubviewSummarySelection(summary?.bottom);
    if (!top?.contigId || !bottom?.contigId) {
      return null;
    }
    return {
      ...baseParams,
      leftAssemblyCtgId: top.contigId,
      rightAssemblyCtgId: bottom.contigId,
    };
  }

  function resolveCurrentSubviewPairwiseEvidenceKey(state) {
    const summary = state.assembly?.subview?.summary || null;
    const scope = resolveSubviewPairwiseEvidenceScope(state, summary);
    return String(scope?.key || buildSubviewPairwiseEvidenceKey(summary) || "");
  }

  function isCurrentRequest(state, params) {
    return (
      resolveCurrentSubviewPairwiseEvidenceKey(state) === params.key
      && String(state.assembly?.subview?.pairwiseEvidence?.key || "") === params.key
      && String(state.assembly?.subview?.pairwiseEvidence?.requestKey || "") === params.requestKey
    );
  }

  async function loadSubviewPairwiseEvidence(host, store, summary) {
    const startState = store.getState();
    const params = resolveSubviewPairwiseEvidenceParams(startState, summary);
    if (!params) {
      return;
    }
    try {
      const report = params.mode === "track-pair"
        ? await getTrackPairwiseEvidence(params)
        : await getJunctionInspection(params);
      const currentState = store.getState();
      if (!isCurrentRequest(currentState, params)) {
        return;
      }
      store.setState({
        assembly: {
          ...currentState.assembly,
          subview: {
            ...getSubviewState(currentState.assembly),
            pairwiseEvidence: {
              key: params.key,
              requestKey: params.requestKey,
              requestedMinAlignmentLength: params.minAlignmentLength,
              requestedMinMapq: params.minMapq,
              loadedMinAlignmentLength: params.minAlignmentLength,
              loadedMinMapq: params.minMapq,
              minAlignmentLength: params.minAlignmentLength,
              minMapq: params.minMapq,
              status: "loaded",
              hits: Array.isArray(report?.hits) ? report.hits : [],
              evidenceSource: String(report?.evidenceSource || ""),
              evidenceHitCount: Number(report?.evidenceHitCount || 0),
              error: "",
            },
          },
        },
      });
      scheduleDeferredSubviewPanelRerender(host, store);
    } catch (error) {
      const currentState = store.getState();
      if (!isCurrentRequest(currentState, params)) {
        return;
      }
      const currentEvidence = currentState.assembly?.subview?.pairwiseEvidence || null;
      store.setState({
        assembly: {
          ...currentState.assembly,
          subview: {
            ...getSubviewState(currentState.assembly),
            pairwiseEvidence: {
              key: params.key,
              requestKey: params.requestKey,
              requestedMinAlignmentLength: params.minAlignmentLength,
              requestedMinMapq: params.minMapq,
              loadedMinAlignmentLength: Math.max(
                1,
                normalizePositiveInt(
                  currentEvidence?.loadedMinAlignmentLength
                    ?? currentEvidence?.minAlignmentLength
                    ?? params.minAlignmentLength,
                ) ?? params.minAlignmentLength,
              ),
              loadedMinMapq: Math.max(
                0,
                normalizeNonNegativeInt(
                  currentEvidence?.loadedMinMapq
                    ?? currentEvidence?.minMapq
                    ?? params.minMapq,
                ) ?? params.minMapq,
              ),
              minAlignmentLength: params.minAlignmentLength,
              minMapq: params.minMapq,
              status: "error",
              hits: Array.isArray(currentEvidence?.hits) ? currentEvidence.hits : [],
              error: mapAssemblyError({ error, stateOrLocale: currentState }),
            },
          },
        },
      });
      scheduleDeferredSubviewPanelRerender(host, store);
    }
  }

  function refreshSubviewPairwiseEvidence(host, store) {
    const state = store.getState();
    const summary = state.assembly?.subview?.summary || null;
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      summary,
      state.assembly?.subviewTrackView || state.assembly?.trackView,
      state.assembly?.subview?.pairwiseEvidence,
      state,
    );
    if (!pairwiseEvidence) {
      return;
    }
    const currentEvidence = state.assembly?.subview?.pairwiseEvidence || null;
    const shouldFetch = String(pairwiseEvidence.requestKey || "")
      !== String(currentEvidence?.requestKey || "");
    const shouldUpdateState = JSON.stringify(pairwiseEvidence)
      !== JSON.stringify(currentEvidence || null);
    if (!shouldUpdateState && !shouldFetch) {
      return;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...getSubviewState(state.assembly),
          pairwiseEvidence,
        },
      },
    });
    if (shouldUpdateState) {
      rerenderSubviewPanel(host, store);
    }
    if (shouldFetch) {
      loadSubviewPairwiseEvidence(host, store, summary);
    }
  }

  function cancelSubviewPairwiseEvidence(host, store, options = {}) {
    const rerender = typeof options?.rerender === "function"
      ? options.rerender
      : rerenderSubviewPanel;
    const rerenderAfter = options?.rerenderAfter !== false;
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const evidence = currentSubview?.pairwiseEvidence || null;
    if (!evidence || String(evidence?.status || "") !== "loading") {
      return false;
    }
    const nextAlignmentLength = Math.max(
      1,
      normalizePositiveInt(
        evidence?.loadedMinAlignmentLength
          ?? evidence?.minAlignmentLength
          ?? state.assembly?.subviewTrackView?.alignmentLength,
      ) ?? 1,
    );
    const nextMapq = Math.max(
      0,
      normalizeNonNegativeInt(
        evidence?.loadedMinMapq
          ?? evidence?.minMapq
          ?? state.assembly?.subviewTrackView?.mapq,
      ) ?? 0,
    );
    const hasCachedHits = Array.isArray(evidence?.hits) && evidence.hits.length > 0;
    store.setState({
      assembly: {
        ...state.assembly,
        subviewTrackView: {
          ...resolveTrackPrefs(state.assembly?.subviewTrackView || state.assembly?.trackView || {}),
          alignmentLength: nextAlignmentLength,
          mapq: nextMapq,
        },
        subview: {
          ...currentSubview,
          pairwiseEvidence: {
            ...evidence,
            requestKey: "",
            requestedMinAlignmentLength: nextAlignmentLength,
            requestedMinMapq: nextMapq,
            loadedMinAlignmentLength: nextAlignmentLength,
            loadedMinMapq: nextMapq,
            minAlignmentLength: nextAlignmentLength,
            minMapq: nextMapq,
            status: hasCachedHits ? "loaded" : "cancelled",
            error: "",
          },
        },
      },
    });
    if (rerenderAfter) {
      rerender(host, store);
    }
    return true;
  }

  return {
    buildInitialSubviewPairwiseEvidence,
    buildSubviewPairwiseEvidenceKey,
    cancelSubviewPairwiseEvidence,
    loadSubviewPairwiseEvidence,
    refreshSubviewPairwiseEvidence,
    shouldLoadSubviewPairwiseEvidence,
  };
}
