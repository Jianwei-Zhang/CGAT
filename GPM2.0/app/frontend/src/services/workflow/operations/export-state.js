import { normalizeWorkflowError } from "../contracts.js";
import { workflowRuntime } from "../runtime.js";

const { isTauriRuntime, callDevBridge, mock, tauri } = workflowRuntime;
const {
  getProjectAssemblyViewState: getProjectAssemblyViewStateMock,
  setProjectAssemblyViewState: setProjectAssemblyViewStateMock,
} = mock;
const {
  getRuntimeSettings: getRuntimeSettingsTauri,
  updateRuntimeSettings: updateRuntimeSettingsTauri,
  getProjectAssemblyViewState: getProjectAssemblyViewStateTauri,
  setProjectAssemblyViewState: setProjectAssemblyViewStateTauri,
} = tauri;

export async function writeFinalPathExportTextFile({ outputPath, text, stateOrLocale = "zh" }) {
  if (!isTauriRuntime()) {
    throw normalizeWorkflowError("final path text export is unavailable in browser preview", {
      code: "BROWSER_EXPORT_UNAVAILABLE",
      source: "browser-preview",
      operation: "write_final_path_export_text_file",
    });
  }
  return tauri.writeFinalPathExportTextFile({ outputPath, text, stateOrLocale });
}

export async function writeFinalPathExportBinaryFile({ outputPath, bytesBase64, stateOrLocale = "zh" }) {
  if (!isTauriRuntime()) {
    throw normalizeWorkflowError("final path binary export is unavailable in browser preview", {
      code: "BROWSER_EXPORT_UNAVAILABLE",
      source: "browser-preview",
      operation: "write_final_path_export_binary_file",
    });
  }
  return tauri.writeFinalPathExportBinaryFile({
    outputPath,
    bytesBase64,
    stateOrLocale,
  });
}

export async function exportFinalPathFasta({
  workspaceRoot,
  projectId,
  chrName,
  finalPathEntry,
  outputPath,
  stateOrLocale = "zh",
}) {
  if (!isTauriRuntime()) {
    throw normalizeWorkflowError("final path fasta export is unavailable in browser preview", {
      code: "BROWSER_EXPORT_UNAVAILABLE",
      source: "browser-preview",
      operation: "export_final_path_fasta",
    });
  }
  return tauri.exportFinalPathFasta({
    workspaceRoot,
    projectId,
    chrName,
    finalPathEntry,
    outputPath,
    stateOrLocale,
  });
}

export async function exportProjectFinalPathFasta({
  workspaceRoot,
  projectId,
  finalPathByChr,
  outputPath,
  stateOrLocale = "zh",
}) {
  if (!isTauriRuntime()) {
    throw normalizeWorkflowError("project final path fasta export is unavailable in browser preview", {
      code: "BROWSER_EXPORT_UNAVAILABLE",
      source: "browser-preview",
      operation: "export_project_final_path_fasta",
    });
  }
  return tauri.exportProjectFinalPathFasta({
    workspaceRoot,
    projectId,
    finalPathByChr,
    outputPath,
    stateOrLocale,
  });
}

export async function exportDegapJobs({
  workspaceRoot,
  projectId,
  outputDir,
  settings,
  jobs,
  stateOrLocale = "zh",
}) {
  const payload = {
    workspaceRoot,
    projectId,
    outputDir,
    settings,
    jobs,
  };
  if (isTauriRuntime()) {
    return tauri.exportDegapJobs({ ...payload, stateOrLocale });
  }
  return callDevBridge("/api/export-degap-jobs", payload);
}

export async function getRuntimeSettings({ workspaceRoot, stateOrLocale = "zh" }) {
  if (isTauriRuntime()) {
    return getRuntimeSettingsTauri({ workspaceRoot, stateOrLocale });
  }
  try {
    return await callDevBridge("/api/runtime-settings-get", {
      workspaceRoot,
    });
  } catch {
    // fallback to preview defaults
  }
  return {
    source: "mock",
    updatedAt: "",
    degapWorkspaceSettings: {},
  };
}

export async function updateRuntimeSettings({
  workspaceRoot,
  degapWorkspaceSettings = {},
  stateOrLocale = "zh",
}) {
  if (isTauriRuntime()) {
    return updateRuntimeSettingsTauri({
      workspaceRoot,
      degapWorkspaceSettings,
      stateOrLocale,
    });
  }
  try {
    return await callDevBridge("/api/runtime-settings-set", {
      workspaceRoot,
      degapWorkspaceSettings,
    });
  } catch {
    // fallback to preview echo
  }
  return {
    source: "mock",
    updatedAt: "",
    degapWorkspaceSettings:
      degapWorkspaceSettings && typeof degapWorkspaceSettings === "object" && !Array.isArray(degapWorkspaceSettings)
        ? degapWorkspaceSettings
        : {},
  };
}

export async function getProjectAssemblyViewState({ workspaceRoot, projectId }) {
  if (isTauriRuntime()) {
    return getProjectAssemblyViewStateTauri({ workspaceRoot, projectId });
  }
  try {
    return await callDevBridge("/api/project-assembly-view-state-get", {
      workspaceRoot,
      projectId,
    });
  } catch {
    // fallback to mock flow
  }
  return getProjectAssemblyViewStateMock({ workspaceRoot, projectId });
}

export async function setProjectAssemblyViewState({
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
  subviewHistoryByKey = {},
  trackScrollState = {},
  subviewTrackScrollState = {},
  finalPathTrackScrollState = {},
  finalPathViewMode = "graph",
  finalPathByChr = {},
  degapProjectState = {},
}) {
  if (isTauriRuntime()) {
    return setProjectAssemblyViewStateTauri({
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
      subviewHistoryByKey,
      trackScrollState,
      subviewTrackScrollState,
      finalPathTrackScrollState,
      finalPathViewMode,
      finalPathByChr,
      degapProjectState,
    });
  }
  try {
    return await callDevBridge("/api/project-assembly-view-state-set", {
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
      subviewHistoryByKey,
      trackScrollState,
      subviewTrackScrollState,
      finalPathTrackScrollState,
      finalPathViewMode,
      finalPathByChr,
      degapProjectState,
    });
  } catch {
    // fallback to mock flow
  }
  return setProjectAssemblyViewStateMock({
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
    subviewHistoryByKey,
    trackScrollState,
    subviewTrackScrollState,
    finalPathTrackScrollState,
    finalPathViewMode,
    finalPathByChr,
    degapProjectState,
  });
}
