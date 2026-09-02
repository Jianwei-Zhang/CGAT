import {
  filterPrimaryTrackSelectionCtgIds,
  filterTrackDragOffsets,
  normalizeSupportDatasetId,
} from "./selection-state.js";
import { normalizeNonNegativeInt } from "./track-prefs.js";

function updateChromosomeSummariesAfterLocalDelete(chromosomes, chrName, removedCtgs) {
  const selectedChrName = String(chrName || "").trim();
  const removedList = Array.isArray(removedCtgs) ? removedCtgs : [];
  if (!selectedChrName || !removedList.length || !Array.isArray(chromosomes)) {
    return Array.isArray(chromosomes) ? chromosomes : [];
  }
  const removedBp = removedList.reduce(
    (sum, ctg) => sum + Math.max(0, normalizeNonNegativeInt(ctg?.totalLength) ?? 0),
    0,
  );
  return chromosomes.map((chromosome) => {
    if (String(chromosome?.chrName || "").trim() !== selectedChrName) {
      return chromosome;
    }
    return {
      ...chromosome,
      ctgCount: Math.max(
        0,
        Math.max(0, normalizeNonNegativeInt(chromosome?.ctgCount) ?? 0)
          - removedList.length,
      ),
      placedBp: Math.max(
        0,
        Math.max(0, normalizeNonNegativeInt(chromosome?.placedBp) ?? 0) - removedBp,
      ),
    };
  });
}

export function createBatchDeleteRefreshController({
  bindAssemblyPage,
  buildClearedSubviewState,
  createRenderedAssemblyMainTabContent,
  getCurrentProject,
  loadDeletedCtgsForChr,
  loadProjectAssemblyViewState,
  patchAssemblyStatusToast,
  patchDeletedPrimaryTrackCtgsDom,
  replaceRenderedAssemblySection,
  rerenderAssemblyMainTab,
  rerenderSubviewPanel,
}) {
  async function refreshAfterBatchDelete(host, store, payload = {}) {
    const state = store.getState();
    const deletedIds = filterPrimaryTrackSelectionCtgIds(
      payload.deletedAssemblyCtgIds,
      state.assembly,
    );
    const deletedIdSet = new Set(deletedIds);
    const currentProject = getCurrentProject(state);
    const primaryDatasetId = normalizeSupportDatasetId(currentProject?.primaryDatasetId);
    const requestWorkspacePath = state.session.workspacePath;
    const requestProjectId = state.session.projectId;
    const requestChrName = state.assembly.selectedChrName;
    const [deletedCtgs, persistedViewState] = await Promise.all([
      loadDeletedCtgsForChr(
        requestWorkspacePath,
        requestProjectId,
        requestChrName,
        primaryDatasetId,
      ),
      loadProjectAssemblyViewState({
        workspaceRoot: requestWorkspacePath,
        projectId: requestProjectId,
      }),
    ]);
    const latestState = store.getState();
    if (
      latestState.session.workspacePath !== requestWorkspacePath
      || latestState.session.projectId !== requestProjectId
      || latestState.assembly.selectedChrName !== requestChrName
    ) {
      return;
    }
    const currentChrCtgs = Array.isArray(latestState.assembly?.chrCtgs)
      ? latestState.assembly.chrCtgs
      : [];
    const removedCtgs = currentChrCtgs.filter(
      (ctg) => deletedIdSet.has(Number(ctg?.assemblyCtgId || 0)),
    );
    const nextChrCtgs = currentChrCtgs.filter(
      (ctg) => !deletedIdSet.has(Number(ctg?.assemblyCtgId || 0)),
    );
    const selectedCtgWasDeleted = deletedIdSet.has(
      Number(latestState.assembly?.selectedCtgId || 0),
    );
    const nextAssemblyBase = {
      ...latestState.assembly,
      chromosomes: updateChromosomeSummariesAfterLocalDelete(
        latestState.assembly?.chromosomes,
        latestState.assembly?.selectedChrName,
        removedCtgs,
      ),
      chrCtgs: nextChrCtgs,
      deletedCtgs,
      finalPathByChr: persistedViewState.finalPathByChr,
      degapProjectState: persistedViewState.degapProjectState,
      selectedDeletedCtgRecordIds: [],
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: filterPrimaryTrackSelectionCtgIds(
        latestState.assembly?.hiddenPrimaryCtgIds,
        { ...latestState.assembly, chrCtgs: nextChrCtgs },
      ),
      selectedCtgId: selectedCtgWasDeleted ? null : latestState.assembly?.selectedCtgId,
      selectedMemberSeqId: selectedCtgWasDeleted ? null : latestState.assembly?.selectedMemberSeqId,
      ctgDetail: selectedCtgWasDeleted ? null : latestState.assembly?.ctgDetail,
      editCandidates: selectedCtgWasDeleted
        ? { moveTargetCtgs: [], addSeqCandidates: [] }
        : latestState.assembly?.editCandidates,
      subview: deletedIds.length
        ? buildClearedSubviewState(latestState.assembly)
        : latestState.assembly?.subview,
      subviewTrackDragOffsets: deletedIds.length
        ? []
        : latestState.assembly?.subviewTrackDragOffsets,
    };
    const nextAssembly = {
      ...nextAssemblyBase,
      trackDragOffsets: filterTrackDragOffsets(
        latestState.assembly?.trackDragOffsets,
        nextAssemblyBase,
      ),
    };
    store.setState({
      ...latestState,
      assembly: nextAssembly,
    });

    const routeHost = host?.closest?.("#route-host") || null;
    if (!routeHost) {
      rerenderAssemblyMainTab(host, store);
      return;
    }
    const nextContent = createRenderedAssemblyMainTabContent(routeHost, store.getState());
    if (!nextContent) {
      rerenderAssemblyMainTab(host, store);
      return;
    }
    const replacedMembersPanel = replaceRenderedAssemblySection(
      routeHost,
      nextContent,
      ".assembly-members-panel",
    );
    if (replacedMembersPanel) {
      bindAssemblyPage(replacedMembersPanel, store);
    }
    patchAssemblyStatusToast(routeHost, nextContent);
    patchDeletedPrimaryTrackCtgsDom(routeHost, deletedIds);
    if (deletedIds.length) {
      rerenderSubviewPanel(host, store);
    }
  }

  return { refreshAfterBatchDelete };
}
