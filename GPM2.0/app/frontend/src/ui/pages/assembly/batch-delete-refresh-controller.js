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
    const currentChrCtgs = Array.isArray(state.assembly?.chrCtgs)
      ? state.assembly.chrCtgs
      : [];
    const removedCtgs = currentChrCtgs.filter(
      (ctg) => deletedIdSet.has(Number(ctg?.assemblyCtgId || 0)),
    );
    const nextChrCtgs = currentChrCtgs.filter(
      (ctg) => !deletedIdSet.has(Number(ctg?.assemblyCtgId || 0)),
    );
    const currentProject = getCurrentProject(state);
    const primaryDatasetId = normalizeSupportDatasetId(currentProject?.primaryDatasetId);
    const deletedCtgs = await loadDeletedCtgsForChr(
      state.session.workspacePath,
      state.session.projectId,
      state.assembly.selectedChrName,
      primaryDatasetId,
    );
    const selectedCtgWasDeleted = deletedIdSet.has(
      Number(state.assembly?.selectedCtgId || 0),
    );
    const nextAssemblyBase = {
      ...state.assembly,
      chromosomes: updateChromosomeSummariesAfterLocalDelete(
        state.assembly?.chromosomes,
        state.assembly?.selectedChrName,
        removedCtgs,
      ),
      chrCtgs: nextChrCtgs,
      deletedCtgs,
      selectedDeletedCtgRecordIds: [],
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: filterPrimaryTrackSelectionCtgIds(
        state.assembly?.hiddenPrimaryCtgIds,
        { ...state.assembly, chrCtgs: nextChrCtgs },
      ),
      selectedCtgId: selectedCtgWasDeleted ? null : state.assembly?.selectedCtgId,
      selectedMemberSeqId: selectedCtgWasDeleted ? null : state.assembly?.selectedMemberSeqId,
      ctgDetail: selectedCtgWasDeleted ? null : state.assembly?.ctgDetail,
      editCandidates: selectedCtgWasDeleted
        ? { moveTargetCtgs: [], addSeqCandidates: [] }
        : state.assembly?.editCandidates,
      subview: deletedIds.length
        ? buildClearedSubviewState(state.assembly)
        : state.assembly?.subview,
      subviewTrackDragOffsets: deletedIds.length
        ? []
        : state.assembly?.subviewTrackDragOffsets,
    };
    const nextAssembly = {
      ...nextAssemblyBase,
      trackDragOffsets: filterTrackDragOffsets(
        state.assembly?.trackDragOffsets,
        nextAssemblyBase,
      ),
    };
    store.setState({
      ...state,
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
