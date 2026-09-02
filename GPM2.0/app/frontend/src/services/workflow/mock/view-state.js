import { normalizeFinalPathViewMode, sleep } from "../contracts.js";

function buildDefaultProjectAssemblyViewState(projectId) {
  return {
    source: "mock",
    projectId: Number(projectId),
    supportDatasetId: null,
    trackView: {},
    supportDsCtgLenRulesByChr: {},
    supportMirroredCtgs: [],
    hiddenPrimaryCtgIds: [],
    hiddenPrimaryCtgIdsByChr: {},
    trackDragOffsets: [],
    subviewTrackDragOffsets: [],
    subviewAnchorStateByKey: {},
    subviewHistoryByKey: {},
    trackScrollState: {},
    subviewTrackScrollState: {},
    finalPathTrackScrollState: {},
    finalPathViewMode: "graph",
    finalPathByChr: {},
    degapProjectState: {},
  };
}

function cloneProjectAssemblyViewState(value) {
  return structuredClone(value);
}

export function createMockViewStateOperations(mockStore) {
async function getProjectAssemblyViewStateMock({ projectId }) {
  await sleep(80);
  const normalizedProjectId = Number(projectId);
  const current = mockStore.projectAssemblyViewStateByProject.get(normalizedProjectId)
    || buildDefaultProjectAssemblyViewState(normalizedProjectId);
  mockStore.projectAssemblyViewStateByProject.set(normalizedProjectId, current);
  return cloneProjectAssemblyViewState(current);
}

async function setProjectAssemblyViewStateMock({
  projectId,
  supportDatasetId = null,
  trackView = {},
  supportDsCtgLenRulesByChr = {},
  supportMirroredCtgs = [],
  hiddenPrimaryCtgIds = [],
  hiddenPrimaryCtgIdsByChr = {},
  trackDragOffsets = [],
  subviewTrackDragOffsets = [],
  subviewAnchorStateByKey = {},
  subviewHistoryByKey = {},
  trackScrollState = {},
  subviewTrackScrollState = {},
  finalPathTrackScrollState = {},
  finalPathViewMode = "graph",
  finalPathByChr = {},
  degapProjectState = {},
}) {
  await sleep(80);
  const next = {
    source: "mock",
    projectId: Number(projectId),
    supportDatasetId: Number.isFinite(Number(supportDatasetId)) && Number(supportDatasetId) > 0
      ? Math.trunc(Number(supportDatasetId))
      : null,
    trackView: trackView && typeof trackView === "object" && !Array.isArray(trackView) ? trackView : {},
    supportDsCtgLenRulesByChr:
      supportDsCtgLenRulesByChr
      && typeof supportDsCtgLenRulesByChr === "object"
      && !Array.isArray(supportDsCtgLenRulesByChr)
        ? supportDsCtgLenRulesByChr
        : {},
    supportMirroredCtgs: Array.isArray(supportMirroredCtgs) ? supportMirroredCtgs : [],
    hiddenPrimaryCtgIds: Array.isArray(hiddenPrimaryCtgIds) ? hiddenPrimaryCtgIds : [],
    hiddenPrimaryCtgIdsByChr:
      hiddenPrimaryCtgIdsByChr
      && typeof hiddenPrimaryCtgIdsByChr === "object"
      && !Array.isArray(hiddenPrimaryCtgIdsByChr)
        ? hiddenPrimaryCtgIdsByChr
        : {},
    trackDragOffsets: Array.isArray(trackDragOffsets) ? trackDragOffsets : [],
    subviewTrackDragOffsets: Array.isArray(subviewTrackDragOffsets) ? subviewTrackDragOffsets : [],
    subviewAnchorStateByKey:
      subviewAnchorStateByKey
      && typeof subviewAnchorStateByKey === "object"
      && !Array.isArray(subviewAnchorStateByKey)
        ? subviewAnchorStateByKey
        : {},
    subviewHistoryByKey:
      subviewHistoryByKey
      && typeof subviewHistoryByKey === "object"
      && !Array.isArray(subviewHistoryByKey)
        ? subviewHistoryByKey
        : {},
    trackScrollState:
      trackScrollState && typeof trackScrollState === "object" && !Array.isArray(trackScrollState)
        ? trackScrollState
        : {},
    subviewTrackScrollState:
      subviewTrackScrollState
      && typeof subviewTrackScrollState === "object"
      && !Array.isArray(subviewTrackScrollState)
        ? subviewTrackScrollState
        : {},
    finalPathTrackScrollState:
      finalPathTrackScrollState
      && typeof finalPathTrackScrollState === "object"
      && !Array.isArray(finalPathTrackScrollState)
        ? finalPathTrackScrollState
        : {},
    finalPathViewMode: normalizeFinalPathViewMode(finalPathViewMode),
    finalPathByChr:
      finalPathByChr && typeof finalPathByChr === "object" && !Array.isArray(finalPathByChr)
        ? finalPathByChr
        : {},
    degapProjectState:
      degapProjectState && typeof degapProjectState === "object" && !Array.isArray(degapProjectState)
        ? degapProjectState
        : {},
  };
  mockStore.projectAssemblyViewStateByProject.set(Number(projectId), cloneProjectAssemblyViewState(next));
  return cloneProjectAssemblyViewState(next);
}

  return {
    getProjectAssemblyViewState: getProjectAssemblyViewStateMock,
    setProjectAssemblyViewState: setProjectAssemblyViewStateMock,
  };
}
