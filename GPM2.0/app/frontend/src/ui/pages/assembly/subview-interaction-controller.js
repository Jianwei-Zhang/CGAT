import { resolveAnchorOffsetErrorKey } from "./confirm-controller.js";
import {
  buildSubviewAnchorStateKey,
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
import { commitSubviewHistoryOperation } from "./subview-history-state.js";
import {
  collectSubviewAnchorScene,
  deleteSubviewAnchorObjects,
  enrichSubviewAnchorObjectDescriptors,
  findSubviewAnchorDescriptor,
} from "./subview-anchor-objects.js";
import {
  createSubviewManualAnchorFromGrt,
  findSubviewGrtAnchorReference,
  findSubviewManualAnchorByGrtOrigin,
} from "./subview-grt-anchor-state.js";
import {
  applySubviewComposition,
  getSubviewComposition,
  toggleSubviewCompositionMemberFlip,
} from "./subview-composition-state.js";

export function createSubviewInteractionController({
  persistProjectAssemblyViewStateFromStore,
  requestAssemblyAnchorOffsetPrompt,
  rerenderSubviewPanel,
  setAssemblyActionFeedback,
  tAssembly,
}) {
  async function commitSubviewEdit(host, store, {
    nextSubview,
    operation,
    persist = persistProjectAssemblyViewStateFromStore,
    rerender = rerenderSubviewPanel,
  }) {
    const state = store.getState();
    const result = commitSubviewHistoryOperation(state.assembly, {
      nextSubview,
      operation,
      stateOrLocale: state,
    });
    if (!result.changed) {
      return false;
    }
    store.setState({
      assembly: result.assembly,
    });
    rerender(host, store);
    await persist(host, store);
    return true;
  }

  async function setSubviewTrackPairCtgHidden(host, store, { trackRole, contigId, hidden = true }) {
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
    await commitSubviewEdit(host, store, {
      nextSubview: {
        ...currentSubview,
        trackPairHiddenCtgs: next,
        trackPairSelectedCtgs: nextSelections,
      },
      operation: {
        kind: hidden ? "hide-contig" : "restore-hidden-contigs",
        count: 1,
      },
    });
  }

  async function commitSubviewAnchorState(host, store, nextSubview, operation) {
    await commitSubviewEdit(host, store, { nextSubview, operation });
  }

  async function toggleSubviewAnchorEdge(host, store, { hitKey, edge }) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const nextActiveAnchors = toggleSubviewAnchorEdgeState(
      currentSubview.activeAnchors,
      { hitKey, edge, descriptor: findSubviewAnchorDescriptor(host, hitKey, edge) },
    );
    if (
      nextActiveAnchors.length === currentSubview.activeAnchors.length
      && nextActiveAnchors.every((entry, index) =>
        entry.hitKey === currentSubview.activeAnchors[index]?.hitKey
        && entry.edge === currentSubview.activeAnchors[index]?.edge)
    ) {
      return;
    }
    await commitSubviewAnchorState(
      host,
      store,
      {
        ...currentSubview,
        activeAnchors: nextActiveAnchors,
      },
      { kind: "toggle-anchor" },
    );
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
    await commitSubviewAnchorState(
      host,
      store,
      {
        ...currentSubview,
        manualAnchors: upsertSubviewManualAnchor(currentSubview.manualAnchors, result.anchor),
      },
      { kind: "create-offset-anchor" },
    );
    setAssemblyActionFeedback(host, store, {
      actionStatus: tAssembly(store.getState(), "runtime.subviewAnchorOffsetCreated"),
      actionError: "",
    });
  }

  async function copySubviewGrtAnchor(host, store, { originId }) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const existing = findSubviewManualAnchorByGrtOrigin(currentSubview.manualAnchors, originId);
    if (existing) {
      setAssemblyActionFeedback(host, store, {
        actionStatus: tAssembly(state, "runtime.subviewGrtAnchorAlreadyCopied"),
        actionError: "",
      });
      return { status: "existing", objectId: `manual:${existing.manualAnchorId}` };
    }
    const reference = findSubviewGrtAnchorReference(
      state.assembly,
      collectSubviewAnchorScene(host),
      originId,
    );
    const created = createSubviewManualAnchorFromGrt(reference);
    if (!created.ok) {
      const errorKey = created.reason === "grtSameLane"
        ? "runtime.subviewGrtAnchorSameLane"
        : "runtime.subviewGrtAnchorUnavailable";
      setAssemblyActionFeedback(host, store, {
        actionStatus: "",
        actionError: tAssembly(state, errorKey),
      });
      return { status: "unavailable", objectId: "" };
    }
    await commitSubviewAnchorState(
      host,
      store,
      {
        ...currentSubview,
        manualAnchors: upsertSubviewManualAnchor(currentSubview.manualAnchors, created.anchor),
      },
      { kind: "create-grt-anchor" },
    );
    setAssemblyActionFeedback(host, store, {
      actionStatus: tAssembly(store.getState(), "runtime.subviewGrtAnchorCreated"),
      actionError: "",
    });
    return { status: "created", objectId: `manual:${created.anchor.manualAnchorId}` };
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
    await commitSubviewAnchorState(
      host,
      store,
      {
        ...currentSubview,
        manualAnchors: nextManualAnchors,
      },
      { kind: "delete-offset-anchor" },
    );
    setAssemblyActionFeedback(host, store, {
      actionStatus: tAssembly(store.getState(), "runtime.subviewManualAnchorDeleted"),
      actionError: "",
    });
  }

  async function deleteSubviewAnchors(host, store, objectIds) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const result = deleteSubviewAnchorObjects(currentSubview, objectIds);
    if (!result.changed) return false;
    await commitSubviewAnchorState(
      host,
      store,
      {
        ...currentSubview,
        activeAnchors: result.activeAnchors,
        manualAnchors: result.manualAnchors,
      },
      { kind: "delete-anchors", count: result.count },
    );
    setAssemblyActionFeedback(host, store, {
      actionStatus: tAssembly(store.getState(), "runtime.subviewAnchorsDeleted", { count: result.count }),
      actionError: "",
    });
    return true;
  }

  async function enrichSubviewAnchorDescriptors(host, store) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    const enriched = enrichSubviewAnchorObjectDescriptors(
      currentSubview,
      collectSubviewAnchorScene(host),
    );
    if (!enriched.changed) return false;
    const nextSubview = { ...currentSubview, activeAnchors: enriched.activeAnchors };
    const pairKey = String(nextSubview.historyKey || "").startsWith("composition:")
      ? String(nextSubview.historyKey)
      : buildSubviewAnchorStateKey(nextSubview.summary, state.assembly.selectedChrName);
    const currentRecord = state.assembly.subviewHistoryByKey?.[pairKey];
    const subviewHistoryByKey = currentRecord
      ? {
          ...state.assembly.subviewHistoryByKey,
          [pairKey]: {
            ...currentRecord,
            current: currentRecord.version === 2 && currentRecord.current?.kind === "composition"
              ? {
                  ...currentRecord.current,
                  composition: {
                    ...currentRecord.current.composition,
                    activeAnchors: enriched.activeAnchors,
                  },
                }
              : { ...currentRecord.current, activeAnchors: enriched.activeAnchors },
          },
        }
      : state.assembly.subviewHistoryByKey;
    store.setState({
      assembly: {
        ...state.assembly,
        subview: nextSubview,
        subviewAnchorStateByKey: setSubviewAnchorStateForSummary(
          state.assembly.subviewAnchorStateByKey,
          nextSubview.summary,
          state.assembly.selectedChrName,
          nextSubview,
        ),
        subviewHistoryByKey,
      },
    });
    await persistProjectAssemblyViewStateFromStore(host, store);
    return true;
  }

  async function toggleSubviewContigFlip(host, store, { slot, assemblyCtgId }, options = {}) {
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
    if (String(currentSubview.summary.mode || "") === "composition") {
      const composition = getSubviewComposition(currentSubview);
      const member = composition?.members.find(
        (entry) => entry.assemblyCtgId === normalizedContigId && entry.lane === normalizedSlot,
      );
      if (!member) return;
      const toggled = toggleSubviewCompositionMemberFlip(composition, member.entityKey);
      if (!toggled.changed) return;
      await commitSubviewEdit(host, store, {
        nextSubview: applySubviewComposition(currentSubview, toggled.composition),
        operation: { kind: "flip-contig" },
        persist: typeof options.persistProjectAssemblyViewStateFromStore === "function"
          ? options.persistProjectAssemblyViewStateFromStore
          : persistProjectAssemblyViewStateFromStore,
        rerender: typeof options.rerenderSubviewPanel === "function"
          ? options.rerenderSubviewPanel
          : rerenderSubviewPanel,
      });
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
    const rerenderSubview = typeof options.rerenderSubviewPanel === "function"
      ? options.rerenderSubviewPanel
      : rerenderSubviewPanel;
    await commitSubviewEdit(host, store, {
      nextSubview: {
        ...currentSubview,
        flippedCtgs: next,
      },
      operation: { kind: "flip-contig" },
      persist: typeof options.persistProjectAssemblyViewStateFromStore === "function"
        ? options.persistProjectAssemblyViewStateFromStore
        : persistProjectAssemblyViewStateFromStore,
      rerender: rerenderSubview,
    });
  }

  async function clearSubviewTrackPairHiddenCtgs(host, store) {
    const state = store.getState();
    const currentSubview = getSubviewState(state.assembly);
    if (!normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs).length) {
      return;
    }
    const count = normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs).length;
    await commitSubviewEdit(host, store, {
      nextSubview: {
        ...currentSubview,
        trackPairHiddenCtgs: [],
      },
      operation: { kind: "restore-hidden-contigs", count },
    });
  }

  return {
    clearSubviewTrackPairHiddenCtgs,
    copySubviewAnchorWithOffset,
    copySubviewGrtAnchor,
    deleteSubviewAnchors,
    enrichSubviewAnchorDescriptors,
    deleteSubviewManualAnchor,
    setSubviewTrackPairCtgHidden,
    toggleSubviewAnchorEdge,
    toggleSubviewContigFlip,
  };
}
