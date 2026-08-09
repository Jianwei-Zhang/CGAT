import {
  applyListLimit,
  normalizeWorkflowError,
} from "../contracts.js";
import { workflowRuntime } from "../runtime.js";

const { isTauriRuntime, callDevBridge, mock, tauri } = workflowRuntime;
const {
  listProjectInitializerOptions: listProjectInitializerOptionsMock,
  validateWorkspaceIntegrity: validateWorkspaceIntegrityMock,
  deleteWorkspaceDirectory: deleteWorkspaceDirectoryMock,
  initializeProject: initializeProjectMock,
  getGrtProjectView: buildMockGrtProjectView,
  deleteProject: deleteProjectMock,
  updateProject: updateProjectMock,
  bootstrapProjectAssembly: bootstrapProjectAssemblyMock,
  autoAssignChr: autoAssignChrMock,
  autoOrientContigs: autoOrientContigsMock,
  autoOrientContigsForDataset: autoOrientContigsForDatasetMock,
  setProjectAutoPipelineDone: setProjectAutoPipelineDoneMock,
  listProjectChromosomes: listProjectChromosomesMock,
  listNewSequences: listNewSequencesMock,
} = mock;
const {
  listProjectInitializerOptions: listProjectInitializerOptionsTauri,
  openWorkspace: openWorkspaceTauri,
  validateWorkspaceIntegrity: validateWorkspaceIntegrityTauri,
  deleteWorkspaceDirectory: deleteWorkspaceDirectoryTauri,
  initializeProject: initializeProjectTauri,
  deleteProject: deleteProjectTauri,
  updateProject: updateProjectTauri,
  bootstrapProjectAssembly: bootstrapProjectAssemblyTauri,
  autoAssignChr: autoAssignChrTauri,
  autoOrientContigs: autoOrientContigsTauri,
  autoOrientContigsForDataset: autoOrientContigsForDatasetTauri,
  requestAutoPipelineCancel: requestAutoPipelineCancelTauri,
  setProjectAutoPipelineDone: setProjectAutoPipelineDoneTauri,
  listProjectChromosomes: listProjectChromosomesTauri,
  listNewSequences: listNewSequencesTauri,
} = tauri;

export async function listProjectInitializerOptions({ workspaceRoot }) {
  if (isTauriRuntime()) {
    return listProjectInitializerOptionsTauri({ workspaceRoot });
  }
  try {
    return await callDevBridge("/api/list-project-initializer-options", {
      workspaceRoot,
    });
  } catch {
    // fallback to mock flow
  }
  return listProjectInitializerOptionsMock({ workspaceRoot });
}

export async function openWorkspace({ workspaceRoot }) {
  if (isTauriRuntime()) {
    return openWorkspaceTauri({ workspaceRoot });
  }
  try {
    return await callDevBridge("/api/open-workspace", {
      workspaceRoot,
    });
  } catch {
    // fallback to existing behavior in browser preview
  }
  return listProjectInitializerOptionsMock({ workspaceRoot });
}

export async function validateWorkspaceIntegrity({ workspaceRoot }) {
  if (isTauriRuntime()) {
    return validateWorkspaceIntegrityTauri({ workspaceRoot });
  }
  try {
    return await callDevBridge("/api/validate-workspace-integrity", {
      workspaceRoot,
    });
  } catch {
    // fallback to mock flow
  }
  return validateWorkspaceIntegrityMock({ workspaceRoot });
}

export async function deleteWorkspaceDirectory({ workspaceRoot }) {
  if (isTauriRuntime()) {
    return deleteWorkspaceDirectoryTauri({ workspaceRoot });
  }
  try {
    return await callDevBridge("/api/delete-workspace-directory", {
      workspaceRoot,
    });
  } catch {
    // fallback to mock flow
  }
  return deleteWorkspaceDirectoryMock({ workspaceRoot });
}

export async function initializeProject({
  workspaceRoot,
  projectName,
  phasedAssemblyEnabled = false,
}) {
  if (isTauriRuntime()) {
    return initializeProjectTauri({
      workspaceRoot,
      projectName,
      phasedAssemblyEnabled,
    });
  }
  try {
    return await callDevBridge("/api/initialize-project", {
      workspaceRoot,
      projectName,
      phasedAssemblyEnabled,
    });
  } catch {
    // fallback to mock flow
  }
  return initializeProjectMock({
    workspaceRoot,
    projectName,
    phasedAssemblyEnabled,
  });
}

export async function getGrtProjectView({ workspaceRoot, projectId }) {
  if (isTauriRuntime()) {
    return tauri.getGrtProjectView({ workspaceRoot, projectId });
  }
  try {
    return await callDevBridge("/api/get-grt-project-view", { workspaceRoot, projectId });
  } catch {
    // fallback to mock flow
  }
  return buildMockGrtProjectView();
}

export async function deleteProject({ workspaceRoot, projectId }) {
  if (isTauriRuntime()) {
    return deleteProjectTauri({ workspaceRoot, projectId });
  }
  try {
    return await callDevBridge("/api/delete-project", {
      workspaceRoot,
      projectId,
    });
  } catch {
    // fallback to mock flow
  }
  return deleteProjectMock({ workspaceRoot, projectId });
}

export async function updateProject({
  workspaceRoot,
  projectId,
  projectName,
  referenceGenomeId,
  primaryDatasetId,
  supportDatasetIds,
  chrAssignmentMinCoveragePercent = 60,
  phasedAssemblyEnabled,
  stateOrLocale = "zh",
}) {
  if (isTauriRuntime()) {
    return updateProjectTauri({
      workspaceRoot,
      projectId,
      projectName,
      referenceGenomeId,
      primaryDatasetId,
      supportDatasetIds,
      chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled,
      stateOrLocale,
    });
  }
  try {
    return await callDevBridge("/api/update-project", {
      workspaceRoot,
      projectId,
      projectName,
      referenceGenomeId,
      primaryDatasetId,
      supportDatasetIds,
      chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled,
    });
  } catch {
    // fallback to mock flow
  }
  return updateProjectMock({
    workspaceRoot,
    projectId,
    projectName,
    referenceGenomeId,
    primaryDatasetId,
    supportDatasetIds,
    chrAssignmentMinCoveragePercent,
    phasedAssemblyEnabled,
    stateOrLocale,
  });
}

export async function bootstrapProjectAssembly({ workspaceRoot, projectId, runId = null }) {
  if (isTauriRuntime()) {
    return bootstrapProjectAssemblyTauri({ workspaceRoot, projectId, runId });
  }
  try {
    return await callDevBridge("/api/bootstrap-project-assembly", {
      workspaceRoot,
      projectId,
      runId,
    });
  } catch {
    // fallback to mock flow
  }
  return bootstrapProjectAssemblyMock({ workspaceRoot, projectId, runId });
}

export async function autoAssignChr({ workspaceRoot, projectId, runId = null }) {
  if (isTauriRuntime()) {
    return autoAssignChrTauri({ workspaceRoot, projectId, runId });
  }
  try {
    return await callDevBridge("/api/auto-assign-chr", {
      workspaceRoot,
      projectId,
      runId,
    });
  } catch {
    // fallback to mock flow
  }
  return autoAssignChrMock({ workspaceRoot, projectId, runId });
}

export async function autoOrientContigs({ workspaceRoot, projectId, runId = null }) {
  if (isTauriRuntime()) {
    return autoOrientContigsTauri({ workspaceRoot, projectId, runId });
  }
  try {
    return await callDevBridge("/api/auto-orient-contigs", {
      workspaceRoot,
      projectId,
      runId,
    });
  } catch {
    // fallback to mock flow
  }
  return autoOrientContigsMock({ workspaceRoot, projectId, runId });
}

export async function autoOrientContigsForDataset({
  workspaceRoot,
  projectId,
  datasetId,
  runId = null,
}) {
  if (isTauriRuntime()) {
    return autoOrientContigsForDatasetTauri({ workspaceRoot, projectId, datasetId, runId });
  }
  try {
    return await callDevBridge("/api/auto-orient-contigs-for-dataset", {
      workspaceRoot,
      projectId,
      datasetId,
      runId,
    });
  } catch {
    // fallback to mock flow
  }
  return autoOrientContigsForDatasetMock({ workspaceRoot, projectId, datasetId, runId });
}

export async function requestAutoPipelineCancel({ workspaceRoot, projectId, runId }) {
  const normalizedRunId = String(runId || "").trim();
  if (!workspaceRoot || !projectId || !normalizedRunId) {
    return { requested: false };
  }
  if (isTauriRuntime()) {
    return requestAutoPipelineCancelTauri({
      workspaceRoot,
      projectId,
      runId: normalizedRunId,
    });
  }
  try {
    return await callDevBridge("/api/request-auto-pipeline-cancel", {
      workspaceRoot,
      projectId,
      runId: normalizedRunId,
    });
  } catch {
    // fallback to mock flow
  }
  return { requested: true };
}

export async function setProjectAutoPipelineDone({ workspaceRoot, projectId, done = true }) {
  if (isTauriRuntime()) {
    return setProjectAutoPipelineDoneTauri({ workspaceRoot, projectId, done });
  }
  try {
    return await callDevBridge("/api/set-project-auto-pipeline-done", {
      workspaceRoot,
      projectId,
      done,
    });
  } catch {
    // fallback to mock flow
  }
  return setProjectAutoPipelineDoneMock({ workspaceRoot, projectId, done });
}

export async function listProjectChromosomes({ workspaceRoot, projectId }) {
  if (isTauriRuntime()) {
    return listProjectChromosomesTauri({ workspaceRoot, projectId });
  }
  try {
    return await callDevBridge("/api/list-project-chromosomes", {
      workspaceRoot,
      projectId,
    });
  } catch {
    // fallback to mock flow
  }
  return listProjectChromosomesMock({ workspaceRoot, projectId });
}

export async function listNewSequences({ workspaceRoot, projectId, limit = 200 }) {
  if (isTauriRuntime()) {
    return listNewSequencesTauri({ workspaceRoot, projectId, limit });
  }
  try {
    const response = await callDevBridge("/api/list-new-sequences", {
      workspaceRoot,
      projectId,
      limit,
    });
    return {
      items: applyListLimit(response.items, limit),
    };
  } catch (error) {
    if (
      !error ||
      typeof error !== "object" ||
      (!("source" in error) && !("code" in error) && !("operation" in error))
    ) {
      return listNewSequencesMock({ workspaceRoot, projectId, limit });
    }
    throw normalizeWorkflowError(error, {
      code: "DEV_BRIDGE_ERROR",
      source: "dev-bridge",
      operation: "/api/list-new-sequences",
    });
  }
}
