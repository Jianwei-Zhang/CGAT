import { resolveAnchorOffsetErrorKey } from "./confirm-controller.js";
import {
  createOffsetSubviewManualAnchor,
  deriveSubviewAnchorOffsetSuggestion,
  removeSubviewManualAnchor,
  setSubviewAnchorStateForSummary,
  toggleSubviewAnchorEdge as toggleSubviewAnchorEdgeState,
  upsertSubviewManualAnchor,
} from "./subview-anchor-state.js";
import {
  normalizeSupportDatasetId,
  normalizeTrackRole,
} from "./selection-state.js";
import {
  buildSubviewTrackPairHiddenCtgKey,
  getSubviewState,
  normalizeSubviewFlippedCtgs,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewTrackPairSelectionCtgs,
} from "./subview-state.js";

export function createSubviewInteractionController({
  persistProjectAssemblyViewStateFromStore,
  requestAssemblyAnchorOffsetPrompt,
  rerenderSubviewPanel,
  setAssemblyActionFeedback,
  tAssembly,
}) {
  function setSubviewTrackPairCtgHidden(host, store, { trackRole, contigId, hidden = true }) {
    const normalizedTrackRole = normalizeTrackRole(trackRole);
    const normalizedContigId = normalizeSupportDatasetId(contigId);
    if (!normalizedTrackRole || !normalizedContigId) {
      return;
    }
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    if (String(currentSubview.summary?.mode || "") !== "track-pair") {
      return;
    }
    const current = normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs);
    const targetKey = buildSubviewTrackPairHiddenCtgKey(normalizedTrackRole, normalizedContigId);
    const next = hidden
      ? normalizeSubviewTrackPairHiddenCtgs([
          ...current,
          {
            trackRole: normalizedTrackRole,
            contigId: normalizedContigId,
          },
        ])
      : current.filter(
        (entry) => buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId) !== targetKey,
      );
    const nextSelections = normalizeSubviewTrackPairSelectionCtgs(
      currentSubview.trackPairSelectedCtgs,
    ).filter(
      (entry) => !next.some(
        (hiddenEntry) =>
          buildSubviewTrackPairHiddenCtgKey(hiddenEntry.trackRole, hiddenEntry.contigId)
            === buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
      ),
    );
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...currentSubview,
          trackPairHiddenCtgs: next,
          trackPairSelectedCtgs: nextSelections,
        },
      },
    });
    rerenderSubviewPanel(host, store);
  }

  function buildSubviewAnchorStateByKeyForCurrentSubview(assembly, subview) {
    return setSubviewAnchorStateForSummary(
      assembly?.subviewAnchorStateByKey,
      subview?.summary,
      assembly?.selectedChrName,
      {
        activeAnchors: subview?.activeAnchors || [],
        manualAnchors: subview?.manualAnchors || [],
      },
    );
  }

  async function commitSubviewAnchorState(host, store, nextSubview) {
    const state = store.getState();
    const nextSubviewAnchorStateByKey = buildSubviewAnchorStateByKeyForCurrentSubview(
      state.assembly,
      nextSubview,
    );
    store.setState({
      assembly: {
        ...state.assembly,
        subview: nextSubview,
        subviewAnchorStateByKey: nextSubviewAnchorStateByKey,
      },
    });
    rerenderSubviewPanel(host, store);
    await persistProjectAssemblyViewStateFromStore(host, store);
  }

  async function toggleSubviewAnchorEdge(host, store, { hitKey, edge }) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const nextActiveAnchors = toggleSubviewAnchorEdgeState(
      currentSubview.activeAnchors,
      { hitKey, edge },
    );
    if (
      nextActiveAnchors.length === currentSubview.activeAnchors.length
      && nextActiveAnchors.every((entry, index) =>
        entry.hitKey === currentSubview.activeAnchors[index]?.hitKey
        && entry.edge === currentSubview.activeAnchors[index]?.edge)
    ) {
      return;
    }
    await commitSubviewAnchorState(host, store, {
      ...currentSubview,
      activeAnchors: nextActiveAnchors,
    });
  }

  async function copySubviewAnchorWithOffset(host, store, sourceEdge) {
    const suggestion = deriveSubviewAnchorOffsetSuggestion(
      sourceEdge,
      sourceEdge?.activeOriginalEdges,
    );
    const promptResult = await requestAssemblyAnchorOffsetPrompt(host, store, {
      defaultDirection: suggestion.ok ? suggestion.direction : "",
      defaultValue: suggestion.ok ? suggestion.offsetBp : "",
      sourceEdge,
    });
    if (!promptResult) {
      return;
    }
    const direction = String(promptResult.direction || "").trim();
    const offsetText = String(promptResult.offsetBp ?? "").trim();
    const offsetBp = Number(offsetText);
    const result = createOffsetSubviewManualAnchor(sourceEdge, { direction, offsetBp });
    if (!result.ok) {
      setAssemblyActionFeedback(host, store, {
        actionStatus: "",
        actionError: tAssembly(store.getState(), resolveAnchorOffsetErrorKey(result.reason)),
      });
      return;
    }
    const currentState = store.getState();
    const currentSubview = getSubviewState(currentState.assembly);
    await commitSubviewAnchorState(host, store, {
      ...currentSubview,
      manualAnchors: upsertSubviewManualAnchor(currentSubview.manualAnchors, result.anchor),
    });
    setAssemblyActionFeedback(host, store, {
      actionStatus: tAssembly(store.getState(), "runtime.subviewAnchorOffsetCreated"),
      actionError: "",
    });
  }

  async function deleteSubviewManualAnchor(host, store, { manualAnchorId }) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const nextManualAnchors = removeSubviewManualAnchor(
      currentSubview.manualAnchors,
      manualAnchorId,
    );
    if (nextManualAnchors.length === currentSubview.manualAnchors.length) {
      return;
    }
    await commitSubviewAnchorState(host, store, {
      ...currentSubview,
      manualAnchors: nextManualAnchors,
    });
    setAssemblyActionFeedback(host, store, {
      actionStatus: tAssembly(store.getState(), "runtime.subviewManualAnchorDeleted"),
      actionError: "",
    });
  }

  function toggleSubviewContigFlip(host, store, { slot, assemblyCtgId }, options = {}) {
    const normalizedSlot = String(slot || "").trim().toLowerCase();
    const normalizedContigId = normalizeSupportDatasetId(assemblyCtgId);
    if ((normalizedSlot !== "top" && normalizedSlot !== "bottom") || !normalizedContigId) {
      return;
    }
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    if (!currentSubview.summary) {
      return;
    }
    const current = normalizeSubviewFlippedCtgs(currentSubview.flippedCtgs);
    const next = current.some(
      (entry) => entry.slot === normalizedSlot && entry.contigId === normalizedContigId,
    )
      ? current.filter(
        (entry) => !(entry.slot === normalizedSlot && entry.contigId === normalizedContigId),
      )
      : [...current, { slot: normalizedSlot, contigId: normalizedContigId }];
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...currentSubview,
          flippedCtgs: next,
        },
      },
    });
    const rerenderSubview = typeof options.rerenderSubviewPanel === "function"
      ? options.rerenderSubviewPanel
      : rerenderSubviewPanel;
    rerenderSubview(host, store);
  }

  function clearSubviewTrackPairHiddenCtgs(host, store) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    if (!normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs).length) {
      return;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...currentSubview,
          trackPairHiddenCtgs: [],
        },
      },
    });
    rerenderSubviewPanel(host, store);
  }

  return {
    clearSubviewTrackPairHiddenCtgs,
    copySubviewAnchorWithOffset,
    deleteSubviewManualAnchor,
    setSubviewTrackPairCtgHidden,
    toggleSubviewAnchorEdge,
    toggleSubviewContigFlip,
  };
}
