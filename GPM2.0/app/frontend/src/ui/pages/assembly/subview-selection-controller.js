import { tAssembly } from "./i18n.js";
import {
  normalizeSupportDatasetId,
  swapSubviewTrackDragOffsetsForSummarySwap,
} from "./selection-state.js";
import { resolveTrackPrefs } from "./track-prefs.js";
import { resolveSubviewAnchorStateForSummary } from "./subview-anchor-state.js";
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
  rerenderSubviewPanel,
}) {
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
    rerenderSubviewPanel(host, store);
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
    const pairwiseEvidence = hasEnteredTrackSubview
      ? buildInitialSubviewPairwiseEvidence(
          nextSubview.summary,
          nextSubviewTrackView,
          state.assembly.subview?.pairwiseEvidence,
          state,
        )
      : null;
    const persistedAnchorState = hasEnteredTrackSubview
      ? resolveSubviewAnchorStateForSummary(
          state.assembly.subviewAnchorStateByKey,
          nextSubview.summary,
          state.assembly.selectedChrName,
        )
      : { activeAnchors: [], manualAnchors: [] };
    store.setState({
      assembly: {
        ...state.assembly,
        subviewTrackView: nextSubviewTrackView,
        subview: hasEnteredTrackSubview
          ? {
            ...nextSubview,
            activeAnchors: persistedAnchorState.activeAnchors,
            manualAnchors: persistedAnchorState.manualAnchors,
            flippedCtgs: [],
            pairwiseEvidence,
          }
          : nextSubview,
        subviewTrackDragOffsets: [],
      },
    });
    rerenderSubviewPanel(host, store);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, nextSubview.summary);
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
    rerenderSubviewPanel(host, store);
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
    rerenderSubviewPanel(host, store);
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
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...nextSubview,
          activeAnchors: persistedAnchorState.activeAnchors,
          manualAnchors: persistedAnchorState.manualAnchors,
          pairwiseEvidence,
        },
        subviewTrackDragOffsets: swapSubviewTrackDragOffsetsForSummarySwap(
          state.assembly.subviewTrackDragOffsets,
        ),
      },
    });
    rerenderSubviewPanel(host, store);
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
      rerenderSubviewPanel(host, store);
      return;
    }
    const nextSubviewTrackView = inheritSubviewTrackViewFromMainTrack(state.assembly);
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      result.value,
      nextSubviewTrackView,
      currentSubview.pairwiseEvidence,
      state,
    );
    const persistedAnchorState = resolveSubviewAnchorStateForSummary(
      state.assembly.subviewAnchorStateByKey,
      result.value,
      state.assembly.selectedChrName,
    );
    store.setState({
      assembly: {
        ...state.assembly,
        subviewTrackView: nextSubviewTrackView,
        subview: {
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
          pairwiseEvidence,
          error: "",
          message: tAssembly(state, "subview.entered"),
        },
        subviewTrackDragOffsets: [],
      },
    });
    rerenderSubviewPanel(host, store);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, result.value);
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
      rerenderSubviewPanel(host, store);
      return;
    }
    const nextSubviewTrackView = inheritSubviewTrackViewFromMainTrack(state.assembly);
    const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
      result.value,
      nextSubviewTrackView,
      currentSubview.pairwiseEvidence,
      state,
    );
    const persistedAnchorState = resolveSubviewAnchorStateForSummary(
      state.assembly.subviewAnchorStateByKey,
      result.value,
      state.assembly.selectedChrName,
    );
    store.setState({
      assembly: {
        ...state.assembly,
        subviewTrackView: nextSubviewTrackView,
        subview: {
          ...currentSubview,
          activeAnchors: persistedAnchorState.activeAnchors,
          manualAnchors: persistedAnchorState.manualAnchors,
          flippedCtgs: [],
          selectedAContigId: null,
          selectedARole: "",
          selectedBContigId: null,
          selectedBRole: "",
          summary: result.value,
          pairwiseEvidence,
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
          error: "",
          message: tAssembly(state, "subview.enteredTrackMode"),
        },
        subviewTrackDragOffsets: [],
      },
    });
    rerenderSubviewPanel(host, store);
    startPairwiseLoadIfNeeded(host, store, pairwiseEvidence, result.value);
  }

  return {
    enterSubviewFromCandidates,
    enterSubviewFromTrackSelections,
    handleSubviewCandidateRemoval,
    handleSubviewSwapTrackOrder,
    handleSubviewTrackSelectionRemoval,
    handleTrackSubviewCandidateSelection,
    handleTrackSubviewTrackSelection,
  };
}
