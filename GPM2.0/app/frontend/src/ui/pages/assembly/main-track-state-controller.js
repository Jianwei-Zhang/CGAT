import { tAssembly } from "./i18n.js";
import {
  buildSupportMirrorKey,
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
  normalizeHiddenPrimaryCtgIdsByChr,
  normalizeSupportDatasetId,
  normalizeSupportMirrorEntry,
  normalizeSupportMirroredCtgs,
  normalizeTrackSelectionCtgIds,
} from "./selection-state.js";
import {
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackPrefs,
} from "./track-prefs.js";
import {
  buildChrLengthsByName,
  filterSupportCtgsBySupportDsCtgLenRules,
  getSupportDsCtgLenRulesForChr,
} from "./support-ds-ctg-len-rules.js";

export function createMainTrackStateController({
  buildDualTrackModel,
  getDatasetNameById,
  patchPrimaryHiddenCtgDom,
  persistProjectAssemblyViewStateFromStore,
  refreshFinalPathLogAfterPrimaryHiddenPatch,
  rerender,
  rerenderAssemblyMainTab,
}) {
  function setActiveHitsTrack(host, store, { trackKey = "primary" }) {
    const state = store.getState();
    const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
    const normalizedTrackKey = String(trackKey || "").trim();
    if (!selectedChrName) {
      return;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        activeHitsTrackKey: normalizedTrackKey,
        activeHitsTrackKeyByChr: {
          ...(state.assembly?.activeHitsTrackKeyByChr || {}),
          [selectedChrName]: normalizedTrackKey || "__none",
        },
      },
    });
    rerender(host, store);
  }

  function updateTrackSelection(host, store, selectedIds) {
    const state = store.getState();
    const normalized = filterPrimaryTrackSelectionCtgIds(selectedIds, state.assembly);
    const current = normalizeTrackSelectionCtgIds(state.assembly.trackSelectedCtgIds);
    if (
      current.length === normalized.length
      && current.every((value, index) => value === normalized[index])
    ) {
      return;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        trackSelectedCtgIds: normalized,
      },
    });
    rerender(host, store);
  }

  function togglePrimaryTrackSelection(host, store, assemblyCtgId) {
    const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
    if (!normalizedCtgId) {
      return;
    }
    const state = store.getState();
    const current = filterPrimaryTrackSelectionCtgIds(
      state.assembly.trackSelectedCtgIds,
      state.assembly,
    );
    const nextSet = new Set(current);
    if (nextSet.has(normalizedCtgId)) {
      nextSet.delete(normalizedCtgId);
    } else {
      nextSet.add(normalizedCtgId);
    }
    updateTrackSelection(host, store, Array.from(nextSet.values()));
  }

  function updateDeletedCtgSelection(host, store, selectedRecordIds) {
    const normalized = normalizeDeletedCtgRecordIds(selectedRecordIds);
    const state = store.getState();
    const current = normalizeDeletedCtgRecordIds(state.assembly.selectedDeletedCtgRecordIds);
    if (
      current.length === normalized.length
      && current.every((value, index) => value === normalized[index])
    ) {
      return;
    }
    store.setState({
      assembly: {
        ...state.assembly,
        selectedDeletedCtgRecordIds: normalized,
      },
    });
    rerender(host, store);
  }

  function buildHiddenPrimaryCtgState(state, nextHiddenIds, actionStatus) {
    const selectedChrName = String(state.assembly.selectedChrName || "").trim();
    const hiddenPrimaryCtgIdsByChr = {
      ...normalizeHiddenPrimaryCtgIdsByChr(state.assembly.hiddenPrimaryCtgIdsByChr),
    };
    if (selectedChrName) {
      if (nextHiddenIds.length) {
        hiddenPrimaryCtgIdsByChr[selectedChrName] = nextHiddenIds;
      } else {
        delete hiddenPrimaryCtgIdsByChr[selectedChrName];
      }
    }
    return {
      ...state.assembly,
      hiddenPrimaryCtgIds: nextHiddenIds,
      hiddenPrimaryCtgIdsByChr,
      actionStatus,
      actionError: "",
    };
  }

  function patchHiddenPrimaryCtgs(
    host,
    store,
    nextHiddenIds,
    changedIds,
    overrides = {},
  ) {
    const didPatchDom = (overrides.patchPrimaryHiddenCtgDom || patchPrimaryHiddenCtgDom)(
      host,
      store,
      nextHiddenIds,
      { changedIds },
    );
    if (didPatchDom) {
      (
        overrides.refreshFinalPathLogAfterPrimaryHiddenPatch
        || refreshFinalPathLogAfterPrimaryHiddenPatch
      )(host, store);
      return;
    }
    rerenderAssemblyMainTab(host, store);
  }

  function persistHiddenPrimaryCtgs(host, state, nextAssemblyState, overrides) {
    return persistProjectAssemblyViewStateFromStore(host, {
      getState() {
        return {
          ...state,
          assembly: nextAssemblyState,
        };
      },
    }, overrides);
  }

  function setSelectedPrimaryTrackCtgsHidden(
    host,
    store,
    selectedIds,
    shouldHide,
    overrides = {},
  ) {
    const state = store.getState();
    const normalized = filterPrimaryTrackSelectionCtgIds(selectedIds, state.assembly);
    if (!normalized.length) {
      return;
    }
    const currentHiddenIds = new Set(
      filterPrimaryTrackSelectionCtgIds(state.assembly.hiddenPrimaryCtgIds, state.assembly),
    );
    normalized.forEach((ctgId) => {
      if (shouldHide) {
        currentHiddenIds.add(ctgId);
        return;
      }
      currentHiddenIds.delete(ctgId);
    });
    const nextHiddenIds = filterPrimaryTrackSelectionCtgIds(
      Array.from(currentHiddenIds.values()),
      state.assembly,
    );
    const nextAssemblyState = buildHiddenPrimaryCtgState(
      state,
      nextHiddenIds,
      tAssembly(state, "runtime.hideSelectedDone", {
        visibilityVerb: tAssembly(
          state,
          shouldHide ? "runtime.hideSelectedVerbHide" : "runtime.hideSelectedVerbShow",
        ),
        count: normalized.length,
      }),
    );
    store.setState({
      ...state,
      assembly: nextAssemblyState,
    });
    patchHiddenPrimaryCtgs(host, store, nextHiddenIds, normalized, overrides);
    return persistHiddenPrimaryCtgs(host, state, nextAssemblyState, overrides);
  }

  function togglePrimaryTrackCtgHidden(
    host,
    store,
    assemblyCtgId,
    shouldHide,
    overrides = {},
  ) {
    const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
    if (!normalizedCtgId) {
      return;
    }
    const state = store.getState();
    const currentHiddenIds = new Set(
      filterPrimaryTrackSelectionCtgIds(state.assembly.hiddenPrimaryCtgIds, state.assembly),
    );
    if (shouldHide) {
      currentHiddenIds.add(normalizedCtgId);
    } else {
      currentHiddenIds.delete(normalizedCtgId);
    }
    const nextHiddenIds = filterPrimaryTrackSelectionCtgIds(
      Array.from(currentHiddenIds.values()),
      state.assembly,
    );
    const previousHiddenIds = filterPrimaryTrackSelectionCtgIds(
      state.assembly.hiddenPrimaryCtgIds,
      state.assembly,
    );
    if (
      nextHiddenIds.length === previousHiddenIds.length
      && nextHiddenIds.every((value, index) => value === previousHiddenIds[index])
    ) {
      return;
    }
    const nextAssemblyState = buildHiddenPrimaryCtgState(
      state,
      nextHiddenIds,
      tAssembly(state, "runtime.hideContigDone", {
        assemblyCtgId: normalizedCtgId,
        visibilityVerb: tAssembly(
          state,
          shouldHide ? "runtime.hideContigVerbHide" : "runtime.hideContigVerbShow",
        ),
      }),
    );
    store.setState({
      ...state,
      assembly: nextAssemblyState,
    });
    patchHiddenPrimaryCtgs(host, store, nextHiddenIds, [normalizedCtgId], overrides);
    return persistHiddenPrimaryCtgs(host, state, nextAssemblyState, overrides);
  }

  function buildSupportMirrorEntryFromAssemblyState(state, datasetId, assemblyCtgId) {
    const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
    const normalizedAssemblyCtgId = normalizeSupportDatasetId(assemblyCtgId);
    if (!normalizedDatasetId || !normalizedAssemblyCtgId) {
      return null;
    }
    const activeSupportDatasetId = normalizeSupportDatasetId(state.assembly.supportDatasetId);
    if (activeSupportDatasetId !== normalizedDatasetId) {
      return null;
    }
    const trackPrefs = resolveTrackPrefs(state.assembly.trackView);
    const supportDsCtgLenBp = Math.max(
      0,
      normalizeNonNegativeInt(trackPrefs.supportDsCtgLen) ?? 0,
    );
    const chrLengthsByName = buildChrLengthsByName(state.assembly.chromosomes);
    const selectedChrName = String(state.assembly.selectedChrName || "").trim();
    const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
      state.assembly.supportDsCtgLenRulesByChr,
      selectedChrName,
      { chrLength: chrLengthsByName[selectedChrName] },
    );
    const supportTrackCtgs = filterSupportCtgsBySupportDsCtgLenRules(
      Array.isArray(state.assembly.supportChrCtgs) ? state.assembly.supportChrCtgs : [],
      {
        rules: supportDsCtgLenRules,
        defaultSupportDsCtgLen: supportDsCtgLenBp,
      },
    );
    const model = buildDualTrackModel({
      primaryCtgs: state.assembly.chrCtgs,
      companionCtgs: supportTrackCtgs,
      selectedPrimaryCtgId: state.assembly.selectedCtgId,
      selectedCompanionCtgId: state.assembly.selectedCtgId,
      prefs: trackPrefs,
    });
    const liveCtg = (Array.isArray(model?.companion?.ctgs) ? model.companion.ctgs : []).find(
      (ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId) === normalizedAssemblyCtgId,
    );
    if (!liveCtg) {
      return null;
    }
    const datasetName = getDatasetNameById(
      state.initializer?.datasets || [],
      normalizedDatasetId,
    );
    return normalizeSupportMirrorEntry({
      datasetId: normalizedDatasetId,
      datasetName,
      chrName: String(state.assembly.selectedChrName || "").trim(),
      assemblyCtgId: normalizedAssemblyCtgId,
      name: String(liveCtg?.name || `Ctg${normalizedAssemblyCtgId}`),
      totalLength: Math.max(
        1,
        normalizePositiveInt(liveCtg?.totalLength ?? liveCtg?.lengthBp) ?? 1,
      ),
      anchorStart: normalizeNonNegativeInt(liveCtg?.anchorStart),
      lengthBp: Math.max(
        1,
        normalizePositiveInt(liveCtg?.lengthBp ?? liveCtg?.totalLength) ?? 1,
      ),
      startBp: Math.max(0, normalizeNonNegativeInt(liveCtg?.startBp) ?? 0),
      endBp: Math.max(
        1,
        normalizePositiveInt(liveCtg?.endBp)
          ?? (Math.max(0, normalizeNonNegativeInt(liveCtg?.startBp) ?? 0)
            + Math.max(
              1,
              normalizePositiveInt(liveCtg?.lengthBp ?? liveCtg?.totalLength) ?? 1,
            )
            - 1),
      ),
      laneIndex: Math.max(0, normalizeNonNegativeInt(liveCtg?.laneIndex) ?? 0),
      orient: liveCtg?.orient ?? liveCtg?.refOrient ?? liveCtg?.ref_orient,
      hits: Array.isArray(liveCtg?.hits) ? liveCtg.hits.map((hit) => ({ ...hit })) : [],
    });
  }

  async function toggleSupportTrackCtgMirror(
    host,
    store,
    { datasetId, assemblyCtgId, shouldMirror },
    overrides = {},
  ) {
    const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
    const normalizedAssemblyCtgId = normalizeSupportDatasetId(assemblyCtgId);
    if (!normalizedDatasetId || !normalizedAssemblyCtgId) {
      return;
    }
    const state = store.getState();
    const currentMirrors = normalizeSupportMirroredCtgs(state.assembly.supportMirroredCtgs);
    const targetKey = buildSupportMirrorKey(normalizedDatasetId, normalizedAssemblyCtgId);
    const hasTarget = currentMirrors.some(
      (entry) => buildSupportMirrorKey(entry.datasetId, entry.assemblyCtgId) === targetKey,
    );
    let nextMirrors = currentMirrors;
    if (shouldMirror) {
      if (hasTarget) {
        return;
      }
      const nextEntry = buildSupportMirrorEntryFromAssemblyState(
        state,
        normalizedDatasetId,
        normalizedAssemblyCtgId,
      );
      if (!nextEntry) {
        store.setState({
          assembly: {
            ...state.assembly,
            actionStatus: "",
            actionError: tAssembly(state, "runtime.mirrorMissingSupport", {
              assemblyCtgId: normalizedAssemblyCtgId,
            }),
          },
        });
        rerender(host, store);
        return;
      }
      nextMirrors = normalizeSupportMirroredCtgs([...currentMirrors, nextEntry]);
    } else {
      if (!hasTarget) {
        return;
      }
      nextMirrors = currentMirrors.filter(
        (entry) => buildSupportMirrorKey(entry.datasetId, entry.assemblyCtgId) !== targetKey,
      );
    }
    store.setState({
      assembly: {
        ...state.assembly,
        supportMirroredCtgs: nextMirrors,
        actionStatus: shouldMirror
          ? tAssembly(state, "runtime.mirrorDone", {
            assemblyCtgId: normalizedAssemblyCtgId,
          })
          : tAssembly(state, "runtime.unmirrorDone", {
            assemblyCtgId: normalizedAssemblyCtgId,
          }),
        actionError: "",
      },
    });
    rerender(host, store);
    await persistProjectAssemblyViewStateFromStore(host, store, overrides);
  }

  return {
    setActiveHitsTrack,
    setSelectedPrimaryTrackCtgsHidden,
    togglePrimaryTrackCtgHidden,
    togglePrimaryTrackSelection,
    toggleSupportTrackCtgMirror,
    updateDeletedCtgSelection,
    updateTrackSelection,
  };
}
