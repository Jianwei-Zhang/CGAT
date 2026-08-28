import { tAssembly } from "./i18n.js";
import {
  normalizeSupportDatasetId,
  swapSubviewTrackDragOffsetsForSummarySwap,
} from "./selection-state.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveSubviewAnchorStateForSummary } from "./subview-anchor-state.js";
import {
  activateSubviewHistory,
  commitSubviewHistoryOperation,
  isSubviewHistoryRecordCompatible,
  resetSubviewHistory,
  restoreSubviewHistoryRollback,
  rollbackSubviewHistory,
} from "./subview-history-state.js";
import {
  buildSubviewSummaryFromCandidates,
  buildSubviewSummaryFromTrackSelections,
  buildSubviewTrackPairPoolsFromAssembly,
  getSubviewSelections,
  getSubviewState,
  removeSubviewCandidate,
  removeSubviewTrackSelection,
  selectSubviewCandidate,
  selectSubviewTrack,
  swapSubviewSummaryOrder,
} from "./subview-state.js";

export function createSubviewSelectionController({
  buildInitialSubviewPairwiseEvidence,
  getCurrentProject,
  loadSubviewPairwiseEvidence,
  persistProjectAssemblyViewStateFromStore = async () => {},
  rerenderAssemblyMainTab,
  rerenderSubviewPanel,
}) {
  function rerenderSubviewSelectionRegions(host, store) {
    rerenderAssemblyMainTab(host, store);
    rerenderSubviewPanel(host, store);
  }

  function inheritSubviewTrackViewFromMainTrack(assembly) {
    const mainTrackPrefs = resolveTrackPrefs(assembly?.trackView);
    return {
      ...(assembly?.subviewTrackView || {}),
      supportDsCtgLen: mainTrackPrefs.supportDsCtgLen,
      minTickUnitKb: mainTrackPrefs.minTickUnitKb,
      minTickKb: mainTrackPrefs.minTickUnitKb,
      maxTickCount: mainTrackPrefs.maxTickCount,
      alignmentLength: mainTrackPrefs.alignmentLength,
      block_length: mainTrackPrefs.alignmentLength,
      mapq: mainTrackPrefs.mapq,
    };
  }

  function startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, summary) {
    if (pairwiseEvidence && String(pairwiseEvidence.status || "") === "loading") {
      loadSubviewPairwiseEvidence(host, store, summary);
    }
  }

  function activateEnteredSubviewHistory(state, subview, subviewTrackDragOffsets = []) {
    const assembly = {
      ...state.assembly,
      subview,
      subviewTrackDragOffsets,
    };
    const pools = buildSubviewTrackPairPoolsFromAssembly(assembly);
    return activateSubviewHistory(
      assembly,
      {
        stateOrLocale: state,
        validateRecord: (record) => isSubviewHistoryRecordCompatible(record, {
          summary: subview.summary,
          pools,
        }),
      },
    );
  }

  function persistActivatedSubviewHistoryIfNeeded(host, store, activation) {
    if (!activation?.created && !activation?.invalidated) {
      return;
    }
    void persistProjectAssemblyViewStateFromStore(host, store);
  }

  function handleTrackSubviewCandidateSelection(host, store, {
    trackRole,
    contigId,
    phasedTrackId = null,
    phasedTrackItemId = null,
    phasedHaplotypeKey = "",
  }) {
    const state = store.getState();
    const currentProject = getCurrentProject(state);
    const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
    const nextSubview = selectSubviewCandidate({
      mode: getSubviewState(state.assembly).mode,
      primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
      supportDatasetId: normalizeSupportDatasetId(state.assembly.supportDatasetId),
      primaryCtgs: pools.primaryCtgs,
      supportCtgs: pools.supportCtgs,
      refCtgs: pools.refCtgs,
      subview: state.assembly.subview,
      trackRole,
      contigId,
      phasedTrackId,
      phasedTrackItemId,
      phasedHaplotypeKey,
      stateOrLocale: state,
    });

    store.setState({
      assembly: {
        ...state.assembly,
        subview: nextSubview,
        subviewTrackDragOffsets: [],
      },
    });
    if (getSubviewSelections(nextSubview).length === 2) {
      enterSubviewFromCandidates(host, store);
      return;
    }
    rerenderSubviewSelectionRegions(host, store);
  }

  function handleTrackSubviewTrackSelection(host, store, {
    trackRole,
    source = "mother",
    datasetId = null,
    isMirror = false,
    phasedTrackId = null,
    haplotypeKey = "",
  }) {
    const state = store.getState();
    const nextSubview = selectSubviewTrack({
      subview: state.assembly.subview,
      trackRole,
      source,
      datasetId,
      isMirror,
      phasedTrackId,
      haplotypeKey,
      stateOrLocale: state,
    });
    const hasEnteredTrackSubview = Boolean(nextSubview.summary);
    const nextSubviewTrackView = hasEnteredTrackSubview
      ? inheritSubviewTrackViewFromMainTrack(state.assembly)
      : state.assembly.subviewTrackView;
    const persistedAnchorState = hasEnteredTrackSubview
      ? resolveSubviewAnchorStateForSummary(
          state.assembly.subviewAnchorStateByKey,
          nextSubview.summary,
          state.assembly.selectedChrName,
        )
      : { activeAnchors: [], manualAnchors: [] };
    const enteredSubview = hasEnteredTrackSubview
      ? {
          ...nextSubview,
          activeAnchors: persistedAnchorState.activeAnchors,
          manualAnchors: persistedAnchorState.manualAnchors,
          flippedCtgs: [],
        }
      : nextSubview;
    const activation = hasEnteredTrackSubview
      ? activateEnteredSubviewHistory(state, enteredSubview)
      : null;
    const activatedSubview = activation?.assembly?.subview || enteredSubview;
    const pairwiseEvidence = hasEnteredTrackSubview
      ? buildInitialSubviewPairwiseEvidence(
          activatedSubview.summary,
          nextSubviewTrackView,
          state.assembly.subview?.pairwiseEvidence,
          state,
        )
      : null;
    store.setState({
      assembly: hasEnteredTrackSubview
        ? {
            ...activation.assembly,
            subviewTrackView: nextSubviewTrackView,
            subview: {
              ...activatedSubview,
              pairwiseEvidence,
              ...(activation.invalidated
                ? { message: tAssembly(state, "subview.historyInvalidCleared") }
                : {}),
            },
          }
        : {
            ...state.assembly,
            subviewTrackView: nextSubviewTrackView,
            subview: enteredSubview,
            subviewTrackDragOffsets: [],
          },
    });
    rerenderSubviewSelectionRegions(host, store);
    persistActivatedSubviewHistoryIfNeeded(host, store, activation);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, activatedSubview.summary);
  }

  function handleSubviewCandidateRemoval(host, store, {
    trackRole,
    contigId,
    phasedTrackId = null,
    phasedTrackItemId = null,
    phasedHaplotypeKey = "",
  }) {
    const state = store.getState();
    const nextSubview = removeSubviewCandidate({
      subview: state.assembly.subview,
      trackRole,
      contigId,
      phasedTrackId,
      phasedTrackItemId,
      phasedHaplotypeKey,
      stateOrLocale: state,
    });
    store.setState({
      assembly: {
        ...state.assembly,
        subview: nextSubview,
        subviewTrackDragOffsets: [],
      },
    });
    rerenderSubviewSelectionRegions(host, store);
  }

  function handleSubviewTrackSelectionRemoval(
    host,
    store,
    { trackRole, source, datasetId, isMirror },
  ) {
    const state = store.getState();
    const nextSubview = removeSubviewTrackSelection({
      subview: state.assembly.subview,
      trackRole,
      source,
      datasetId,
      isMirror,
      stateOrLocale: state,
    });
    store.setState({
      assembly: {
        ...state.assembly,
        subview: nextSubview,
        subviewTrackDragOffsets: [],
      },
    });
    rerenderSubviewSelectionRegions(host, store);
  }

  function handleSubviewSwapTrackOrder(host, store) {
    const state = store.getState();
    const nextSubview = swapSubviewSummaryOrder({
      subview: state.assembly.subview,
      stateOrLocale: state,
    });
    if (!nextSubview.summary) {
      return;
    }
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      nextSubview.summary,
      state.assembly.subviewTrackView || state.assembly.trackView,
      state.assembly.subview?.pairwiseEvidence,
      state,
    );
    const persistedAnchorState = resolveSubviewAnchorStateForSummary(
      state.assembly.subviewAnchorStateByKey,
      nextSubview.summary,
      state.assembly.selectedChrName,
    );
    const committed = commitSubviewHistoryOperation(state.assembly, {
      nextSubview: {
        ...nextSubview,
        activeAnchors: persistedAnchorState.activeAnchors,
        manualAnchors: persistedAnchorState.manualAnchors,
        pairwiseEvidence,
      },
      nextSubviewTrackDragOffsets: swapSubviewTrackDragOffsetsForSummarySwap(
        state.assembly.subviewTrackDragOffsets,
      ),
      operation: { kind: "swap-track-order" },
      stateOrLocale: state,
    });
    if (!committed.changed) {
      return;
    }
    store.setState({ assembly: committed.assembly });
    rerenderSubviewPanel(host, store);
    void persistProjectAssemblyViewStateFromStore(host, store);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, nextSubview.summary);
  }

  function enterSubviewFromCandidates(host, store) {
    const state = store.getState();
    const currentProject = getCurrentProject(state);
    const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
    const result = buildSubviewSummaryFromCandidates({
      subview: state.assembly.subview,
      primaryCtgs: pools.primaryCtgs,
      supportCtgs: pools.supportCtgs,
      refCtgs: pools.refCtgs,
      phasedCtgs: pools.phasedCtgs,
      datasets: state.initializer?.datasets || [],
      primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
      supportDatasetId: normalizeSupportDatasetId(state.assembly.supportDatasetId),
      stateOrLocale: state,
    });
    const currentSubview = getSubviewState(state.assembly);
    if (!result.ok) {
      store.setState({
        assembly: {
          ...state.assembly,
          subview: {
            ...currentSubview,
            activeAnchors: [],
            manualAnchors: [],
            flippedCtgs: [],
            error: result.error,
            summary: null,
          },
          subviewTrackDragOffsets: [],
        },
      });
      rerenderSubviewSelectionRegions(host, store);
      return;
    }
    const nextSubviewTrackView = inheritSubviewTrackViewFromMainTrack(state.assembly);
    const persistedAnchorState = resolveSubviewAnchorStateForSummary(
      state.assembly.subviewAnchorStateByKey,
      result.value,
      state.assembly.selectedChrName,
    );
    const enteredSubview = {
      ...currentSubview,
      activeAnchors: persistedAnchorState.activeAnchors,
      manualAnchors: persistedAnchorState.manualAnchors,
      flippedCtgs: [],
      selectedTrackSelections: [],
      selectedTrackARole: "",
      selectedTrackBRole: "",
      selectedTrackBSource: "",
      selectedTrackBDatasetId: null,
      selectedTrackBIsMirror: false,
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
      summary: result.value,
      error: "",
      message: tAssembly(state, "subview.entered"),
    };
    const activation = activateEnteredSubviewHistory(state, enteredSubview);
    const activatedSubview = activation.assembly.subview;
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      activatedSubview.summary,
      nextSubviewTrackView,
      currentSubview.pairwiseEvidence,
      state,
    );
    store.setState({
      assembly: {
        ...activation.assembly,
        subviewTrackView: nextSubviewTrackView,
        subview: {
          ...activatedSubview,
          pairwiseEvidence,
          ...(activation.invalidated
            ? { message: tAssembly(state, "subview.historyInvalidCleared") }
            : {}),
        },
      },
    });
    rerenderSubviewSelectionRegions(host, store);
    persistActivatedSubviewHistoryIfNeeded(host, store, activation);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, activatedSubview.summary);
  }

  function enterSubviewFromTrackSelections(host, store) {
    const state = store.getState();
    const result = buildSubviewSummaryFromTrackSelections({
      subview: state.assembly.subview,
      stateOrLocale: state,
    });
    const currentSubview = getSubviewState(state.assembly);
    if (!result.ok) {
      store.setState({
        assembly: {
          ...state.assembly,
          subview: {
            ...currentSubview,
            activeAnchors: [],
            flippedCtgs: [],
            error: result.error,
            summary: null,
          },
          subviewTrackDragOffsets: [],
        },
      });
      rerenderSubviewSelectionRegions(host, store);
      return;
    }
    const nextSubviewTrackView = inheritSubviewTrackViewFromMainTrack(state.assembly);
    const persistedAnchorState = resolveSubviewAnchorStateForSummary(
      state.assembly.subviewAnchorStateByKey,
      result.value,
      state.assembly.selectedChrName,
    );
    const enteredSubview = {
      ...currentSubview,
      activeAnchors: persistedAnchorState.activeAnchors,
      manualAnchors: persistedAnchorState.manualAnchors,
      flippedCtgs: [],
      selectedAContigId: null,
      selectedARole: "",
      selectedBContigId: null,
      selectedBRole: "",
      summary: result.value,
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
      error: "",
      message: tAssembly(state, "subview.enteredTrackMode"),
    };
    const activation = activateEnteredSubviewHistory(state, enteredSubview);
    const activatedSubview = activation.assembly.subview;
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      activatedSubview.summary,
      nextSubviewTrackView,
      currentSubview.pairwiseEvidence,
      state,
    );
    store.setState({
      assembly: {
        ...activation.assembly,
        subviewTrackView: nextSubviewTrackView,
        subview: {
          ...activatedSubview,
          pairwiseEvidence,
          ...(activation.invalidated
            ? { message: tAssembly(state, "subview.historyInvalidCleared") }
            : {}),
        },
      },
    });
    rerenderSubviewSelectionRegions(host, store);
    persistActivatedSubviewHistoryIfNeeded(host, store, activation);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, activatedSubview.summary);
  }

  function applySubviewHistoryTransition(host, store, transition) {
    const state = store.getState();
    const result = transition(state.assembly, { stateOrLocale: state });
    if (!result.changed) {
      if (result.invalidated) {
        store.setState({
          assembly: {
            ...result.assembly,
            subview: {
              ...result.assembly.subview,
              message: tAssembly(state, "subview.historyInvalidCleared"),
            },
          },
        });
        rerenderSubviewPanel(host, store);
        void persistProjectAssemblyViewStateFromStore(host, store);
      }
      return;
    }
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      result.assembly.subview.summary,
      result.assembly.subviewTrackView || result.assembly.trackView,
      state.assembly.subview?.pairwiseEvidence,
      state,
    );
    store.setState({
      assembly: {
        ...result.assembly,
        subview: {
          ...result.assembly.subview,
          pairwiseEvidence,
        },
      },
    });
    rerenderSubviewPanel(host, store);
    void persistProjectAssemblyViewStateFromStore(host, store);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, result.assembly.subview.summary);
  }

  function handleSubviewHistoryRollback(host, store) {
    applySubviewHistoryTransition(host, store, rollbackSubviewHistory);
  }

  function handleSubviewHistoryRestoreRollback(host, store) {
    applySubviewHistoryTransition(host, store, restoreSubviewHistoryRollback);
  }

  function handleSubviewHistoryReset(host, store) {
    applySubviewHistoryTransition(host, store, resetSubviewHistory);
  }

  return {
    enterSubviewFromCandidates,
    enterSubviewFromTrackSelections,
    handleSubviewCandidateRemoval,
    handleSubviewHistoryReset,
    handleSubviewHistoryRestoreRollback,
    handleSubviewHistoryRollback,
    handleSubviewSwapTrackOrder,
    handleSubviewTrackSelectionRemoval,
    handleTrackSubviewCandidateSelection,
    handleTrackSubviewTrackSelection,
  };
}
