import { normalizeFinalPathViewMode } from "../contracts.js";

export function createTauriViewStateOperations({ invokeCommand }) {
async function getProjectAssemblyViewStateTauri({ workspaceRoot, projectId }) {
  return invokeCommand("get_project_assembly_view_state", {
    workspaceRoot,
    projectId,
  });
}

async function setProjectAssemblyViewStateTauri({
  workspaceRoot,
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
  trackScrollState = {},
  subviewTrackScrollState = {},
  finalPathTrackScrollState = {},
  finalPathViewMode = "graph",
  finalPathByChr = {},
  degapProjectState = {},
}) {
  return invokeCommand("update_project_assembly_view_state", {
    request: {
      workspaceRoot,
      projectId,
      supportDatasetId,
      trackView,
      supportDsCtgLenRulesByChr,
      supportMirroredCtgs,
      hiddenPrimaryCtgIds,
      hiddenPrimaryCtgIdsByChr,
      trackDragOffsets,
      subviewTrackDragOffsets,
      subviewAnchorStateByKey,
      trackScrollState,
      subviewTrackScrollState,
      finalPathTrackScrollState,
      finalPathViewMode,
      finalPathByChr,
      degapProjectState,
    },
  });
}

async function getRuntimeSettingsTauri({ workspaceRoot, stateOrLocale = "zh" }) {
  return invokeCommand("get_runtime_settings", {
    workspaceRoot,
  }, stateOrLocale);
}

async function updateRuntimeSettingsTauri({
  workspaceRoot,
  degapWorkspaceSettings = {},
  stateOrLocale = "zh",
}) {
  return invokeCommand("update_runtime_settings", {
    workspaceRoot,
    degapWorkspaceSettings,
  }, stateOrLocale);
}

  return {
    getProjectAssemblyViewState: getProjectAssemblyViewStateTauri,
    setProjectAssemblyViewState: setProjectAssemblyViewStateTauri,
    getRuntimeSettings: getRuntimeSettingsTauri,
    updateRuntimeSettings: updateRuntimeSettingsTauri,
  };
}
