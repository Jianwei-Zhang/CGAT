import {
  buildSupportDsStorageKey,
  loadSupportDsState,
  reconcileSupportDsSelection,
  saveSupportDsState,
} from "./support-ds-session.js";
import {
  filterTrackDragOffsets,
  normalizeSupportDatasetId,
} from "./selection-state.js";
import { normalizeFinalPathViewMode } from "./final-path-state.js";
import { normalizeViewportScrollState } from "./scroll-position-state.js";

export function createSupportDatasetController({
  buildClearedSubviewState,
  getSupportDatasetOptions,
  loadSupportChrCtgs,
  persistProjectAssemblyViewState,
  rerender,
  session,
}) {
  function syncSupportDatasetSelection(store, storage = null) {
    const state = store.getState();
    const workspacePath = String(state?.session?.workspacePath || "").trim();
    const projectId = Number(state?.session?.projectId || 0);
    const storageKey = buildSupportDsStorageKey(workspacePath, projectId);

    if (!storageKey) {
      session.lastSupportDsSessionKey = "";
      session.lastSupportDsSelection = null;
      return { changed: false, supportDatasetId: null };
    }

    const supportDatasetOptions = getSupportDatasetOptions(state);
    const candidateIds = new Set(supportDatasetOptions.map((dataset) => dataset.datasetId));
    const currentSelection = normalizeSupportDatasetId(state.assembly.supportDatasetId);

    if (storageKey !== session.lastSupportDsSessionKey) {
      session.lastSupportDsSessionKey = storageKey;
      if (currentSelection !== null && candidateIds.has(currentSelection)) {
        saveSupportDsState(
          workspacePath,
          projectId,
          { supportDatasetId: currentSelection },
          storage || undefined,
        );
        session.lastSupportDsSelection = currentSelection;
        return { changed: false, supportDatasetId: currentSelection };
      }
      const savedState = loadSupportDsState(
        workspacePath,
        projectId,
        storage || undefined,
      );
      const restoredDatasetId = normalizeSupportDatasetId(savedState?.supportDatasetId);
      const nextSelection = restoredDatasetId !== null && candidateIds.has(restoredDatasetId)
        ? restoredDatasetId
        : supportDatasetOptions[0]?.datasetId || null;
      if (nextSelection !== null && nextSelection !== restoredDatasetId) {
        saveSupportDsState(
          workspacePath,
          projectId,
          { supportDatasetId: nextSelection },
          storage || undefined,
        );
      }
      session.lastSupportDsSelection = nextSelection;
      if (normalizeSupportDatasetId(state.assembly.supportDatasetId) !== nextSelection) {
        return { changed: true, supportDatasetId: nextSelection };
      }
      return { changed: false, supportDatasetId: nextSelection };
    }

    const reconciliation = reconcileSupportDsSelection({
      workspacePath,
      projectId,
      currentSelection,
      candidateIds,
      storage: storage || undefined,
    });
    if (reconciliation.invalidated) {
      const fallbackSelection = supportDatasetOptions[0]?.datasetId || null;
      session.lastSupportDsSelection = fallbackSelection;
      if (currentSelection !== fallbackSelection) {
        return { changed: true, supportDatasetId: fallbackSelection };
      }
    }
    if (currentSelection === null && supportDatasetOptions.length > 0) {
      const fallbackSelection = supportDatasetOptions[0]?.datasetId || null;
      session.lastSupportDsSelection = fallbackSelection;
      if (fallbackSelection !== null) {
        saveSupportDsState(
          workspacePath,
          projectId,
          { supportDatasetId: fallbackSelection },
          storage || undefined,
        );
        return { changed: true, supportDatasetId: fallbackSelection };
      }
    }

    if (currentSelection !== session.lastSupportDsSelection) {
      saveSupportDsState(
        workspacePath,
        projectId,
        { supportDatasetId: currentSelection },
        storage || undefined,
      );
      session.lastSupportDsSelection = currentSelection;
    }

    return { changed: false, supportDatasetId: currentSelection };
  }

  function buildAssemblyStateForSupportDatasetSelection(assembly, supportDatasetId) {
    const nextSupportDatasetClearedAssembly = {
      ...assembly,
      supportChrCtgs: [],
    };
    return {
      ...nextSupportDatasetClearedAssembly,
      supportDatasetId,
      trackSelectedCtgIds: [],
      trackDragOffsets: filterTrackDragOffsets(
        nextSupportDatasetClearedAssembly.trackDragOffsets,
        nextSupportDatasetClearedAssembly,
        { preserveUnmatchedSupportOffsets: true },
      ),
      subviewTrackDragOffsets: [],
      selectedDeletedCtgRecordIds: [],
      subview: buildClearedSubviewState(assembly),
      summary: "",
    };
  }

  async function applySupportDatasetSelection(
    host,
    store,
    rawSupportDatasetId,
    overrides = {},
  ) {
    const state = store.getState();
    const supportDatasetId = normalizeSupportDatasetId(rawSupportDatasetId);
    const currentSupportDatasetId = normalizeSupportDatasetId(
      state.assembly.supportDatasetId,
    );
    if (supportDatasetId === currentSupportDatasetId) {
      return false;
    }

    const nextAssemblyState = buildAssemblyStateForSupportDatasetSelection(
      state.assembly,
      supportDatasetId,
    );
    store.setState({
      ...state,
      assembly: nextAssemblyState,
    });
    const rerenderView = overrides.rerenderView || rerender;
    rerenderView(host, store);
    await (overrides.persistProjectAssemblyViewState || persistProjectAssemblyViewState)({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
      supportDatasetId,
      trackView: nextAssemblyState.trackView,
      supportMirroredCtgs: Array.isArray(nextAssemblyState.supportMirroredCtgs)
        ? nextAssemblyState.supportMirroredCtgs
        : [],
      hiddenPrimaryCtgIds: Array.isArray(nextAssemblyState.hiddenPrimaryCtgIds)
        ? nextAssemblyState.hiddenPrimaryCtgIds
        : [],
      trackDragOffsets: Array.isArray(nextAssemblyState.trackDragOffsets)
        ? nextAssemblyState.trackDragOffsets
        : [],
      subviewTrackDragOffsets: Array.isArray(nextAssemblyState.subviewTrackDragOffsets)
        ? nextAssemblyState.subviewTrackDragOffsets
        : [],
      subviewAnchorStateByKey:
        nextAssemblyState.subviewAnchorStateByKey
        && typeof nextAssemblyState.subviewAnchorStateByKey === "object"
        && !Array.isArray(nextAssemblyState.subviewAnchorStateByKey)
          ? nextAssemblyState.subviewAnchorStateByKey
          : {},
      subviewHistoryByKey:
        nextAssemblyState.subviewHistoryByKey
        && typeof nextAssemblyState.subviewHistoryByKey === "object"
        && !Array.isArray(nextAssemblyState.subviewHistoryByKey)
          ? nextAssemblyState.subviewHistoryByKey
          : {},
      trackScrollState: normalizeViewportScrollState(nextAssemblyState.trackScrollState),
      subviewTrackScrollState: normalizeViewportScrollState(
        nextAssemblyState.subviewTrackScrollState,
      ),
      finalPathTrackScrollState: normalizeViewportScrollState(
        nextAssemblyState.finalPathTrackScrollState,
      ),
      membersCardCollapsed: nextAssemblyState.membersCardCollapsed === false ? false : true,
      finalPathViewMode: normalizeFinalPathViewMode(nextAssemblyState.finalPathViewMode),
      finalPathByChr:
        nextAssemblyState.finalPathByChr
        && typeof nextAssemblyState.finalPathByChr === "object"
        && !Array.isArray(nextAssemblyState.finalPathByChr)
          ? nextAssemblyState.finalPathByChr
          : {},
    });

    if (
      !state.session.workspacePath
      || !state.session.projectId
      || !state.assembly.selectedChrName
      || supportDatasetId === null
    ) {
      return true;
    }

    const supportChrCtgs = await (overrides.loadSupportChrCtgs || loadSupportChrCtgs)(
      state.session.workspacePath,
      state.session.projectId,
      state.assembly.selectedChrName,
      supportDatasetId,
    );
    const latestState = store.getState();
    if (
      normalizeSupportDatasetId(latestState.assembly.supportDatasetId) !== supportDatasetId
      || String(latestState.assembly.selectedChrName || "").trim()
        !== String(state.assembly.selectedChrName || "").trim()
    ) {
      return true;
    }

    store.setState({
      ...latestState,
      assembly: {
        ...latestState.assembly,
        supportChrCtgs,
        summary: "",
      },
    });
    rerenderView(host, store);
    return true;
  }

  return {
    applySupportDatasetSelection,
    syncSupportDatasetSelection,
  };
}
