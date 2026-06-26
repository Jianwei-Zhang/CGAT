import { t } from "../ui/i18n/index.js";
import { invokeCommand, isTauriRuntime, listenBackendEvent } from "./backend-api.js";

const mockStore = {
  packageMetadata: {
    packageMode: "fast",
    sequenceLayout: "partitioned",
    preassignedChr: true,
    chrAssignmentMinCoveragePercent: 60,
    selfAlignmentScope: "chr_partition",
    crossAlignmentScope: "chr_partition",
  },
  references: [
    {
      referenceGenomeId: 1,
      label: "Ref #1 (Chr01-12 + Chloroplast)",
    },
  ],
  datasets: [
    { datasetId: 1, label: "hifiasm", contigCount: 1154, totalLengthBp: 408532119, selfAlignmentAvailable: true },
    { datasetId: 2, label: "flye", contigCount: 1327, totalLengthBp: 401886542, selfAlignmentAvailable: true },
    { datasetId: 3, label: "wtdbg2", contigCount: 1899, totalLengthBp: 395447286, selfAlignmentAvailable: true },
  ],
  existingProjects: [],
  phasedChrTracks: [],
  nextPhasedTrackId: 1,
  nextPhasedTrackItemId: 1,
};

function normalizeFinalPathViewMode(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "log") {
    return "log";
  }
  if (normalized === "degap") {
    return "degap";
  }
  if (normalized === "table") {
    return "table";
  }
  return "graph";
}

export async function importZipBundle({ zipPath, workspaceRoot, onStage, runId = "", stateOrLocale = "zh" }) {
  if (isTauriRuntime()) {
    return importZipBundleTauri({ zipPath, workspaceRoot, onStage, runId, stateOrLocale });
  }
  try {
    const response = await callDevBridge("/api/import-zip", {
      zipPath,
      workspaceRoot,
    });
    for (const stage of response.stages || []) {
      onStage?.(stage);
    }
    return {
      workspaceRoot: response.workspaceRoot,
      message: response.message,
    };
  } catch {
    // fallback to mock flow
  }
  return importZipBundleMock({ zipPath, workspaceRoot, onStage, stateOrLocale });
}

export async function importExtractedBundle({ extractedPath, onStage, runId = "", stateOrLocale = "zh" }) {
  if (isTauriRuntime()) {
    return importExtractedBundleTauri({ extractedPath, onStage, runId, stateOrLocale });
  }
  try {
    const response = await callDevBridge("/api/import-extracted", {
      extractedPath,
    });
    for (const stage of response.stages || []) {
      onStage?.(stage);
    }
    return {
      workspaceRoot: response.workspaceRoot,
      message: response.message,
    };
  } catch {
    // fallback to mock flow
  }
  return importExtractedBundleMock({ extractedPath, onStage, stateOrLocale });
}

export async function importAddDatasetPackage({
  workspaceRoot,
  zipPath,
  onStage,
  runId = "",
  stateOrLocale = "zh",
}) {
  if (isTauriRuntime()) {
    return importAddDatasetPackageTauri({
      workspaceRoot,
      zipPath,
      onStage,
      runId,
      stateOrLocale,
    });
  }
  try {
    const response = await callDevBridge("/api/import-add-dataset-package", {
      workspaceRoot,
      zipPath,
    });
    for (const stage of response.stages || []) {
      onStage?.(stage);
    }
    return {
      workspaceRoot: response.workspaceRoot || workspaceRoot,
      packageMetadata: response.packageMetadata || mockStore.packageMetadata,
      references: response.references || [],
      datasets: response.datasets || [],
      existingProjects: response.existingProjects || [],
      datasetId: response.datasetId,
      datasetName: response.datasetName,
      message: response.message,
    };
  } catch {
    // fallback to mock flow
  }
  return importAddDatasetPackageMock({
    workspaceRoot,
    zipPath,
    onStage,
    stateOrLocale,
  });
}

export async function importAddCtgPackage({
  workspaceRoot,
  projectId,
  zipPath,
  expectedTargetChr = "",
  expectedTargetTrack = "",
  onStage,
  runId = "",
  stateOrLocale = "zh",
}) {
  if (isTauriRuntime()) {
    return importAddCtgPackageTauri({
      workspaceRoot,
      projectId,
      zipPath,
      expectedTargetChr,
      expectedTargetTrack,
      onStage,
      runId,
      stateOrLocale,
    });
  }
  return importAddCtgPackageMock({
    workspaceRoot,
    projectId,
    zipPath,
    expectedTargetChr,
    expectedTargetTrack,
    onStage,
    stateOrLocale,
  });
}

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
  referenceGenomeId,
  primaryDatasetId,
  supportDatasetIds,
  chrAssignmentMinCoveragePercent = 60,
  phasedAssemblyEnabled = false,
}) {
  if (isTauriRuntime()) {
    return initializeProjectTauri({
      workspaceRoot,
      projectName,
      referenceGenomeId,
      primaryDatasetId,
      supportDatasetIds,
      chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled,
    });
  }
  try {
    return await callDevBridge("/api/initialize-project", {
      workspaceRoot,
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
  return initializeProjectMock({
    workspaceRoot,
    projectName,
    referenceGenomeId,
    primaryDatasetId,
    supportDatasetIds,
    chrAssignmentMinCoveragePercent,
    phasedAssemblyEnabled,
  });
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

export async function listChrViewCtgs({ workspaceRoot, projectId, chrName, datasetId = null }) {
  if (isTauriRuntime()) {
    return listChrViewCtgsTauri({ workspaceRoot, projectId, chrName, datasetId });
  }
  try {
    return await callDevBridge("/api/list-chr-view-ctgs", {
      workspaceRoot,
      projectId,
      chrName,
      datasetId,
    });
  } catch {
    // fallback to mock flow
  }
  return listChrViewCtgsMock({ workspaceRoot, projectId, chrName, datasetId });
}

export async function listReferenceTrackMembers({ workspaceRoot, projectId, chrName }) {
  if (isTauriRuntime()) {
    return listReferenceTrackMembersTauri({ workspaceRoot, projectId, chrName });
  }
  try {
    return await callDevBridge("/api/list-reference-track-members", {
      workspaceRoot,
      projectId,
      chrName,
    });
  } catch {
    // fallback to mock flow
  }
  return listReferenceTrackMembersMock({ workspaceRoot, projectId, chrName });
}

export async function listPhasedChrTracks({ workspaceRoot, projectId, parentChrName }) {
  if (isTauriRuntime()) {
    return listPhasedChrTracksTauri({ workspaceRoot, projectId, parentChrName });
  }
  try {
    return await callDevBridge("/api/list-phased-chr-tracks", {
      workspaceRoot,
      projectId,
      parentChrName,
    });
  } catch {
    // fallback to mock flow
  }
  return listPhasedChrTracksMock({ projectId, parentChrName });
}

export async function createPhasedChrTrack({ workspaceRoot, projectId, parentChrName }) {
  if (isTauriRuntime()) {
    return createPhasedChrTrackTauri({ workspaceRoot, projectId, parentChrName });
  }
  try {
    return await callDevBridge("/api/create-phased-chr-track", {
      workspaceRoot,
      projectId,
      parentChrName,
    });
  } catch {
    // fallback to mock flow
  }
  return createPhasedChrTrackMock({ projectId, parentChrName });
}

export async function deletePhasedChrTrack({ workspaceRoot, projectId, phasedTrackId }) {
  if (isTauriRuntime()) {
    return deletePhasedChrTrackTauri({ workspaceRoot, projectId, phasedTrackId });
  }
  try {
    return await callDevBridge("/api/delete-phased-chr-track", {
      workspaceRoot,
      projectId,
      phasedTrackId,
    });
  } catch {
    // fallback to mock flow
  }
  return deletePhasedChrTrackMock({ projectId, phasedTrackId });
}

export async function addCtgToPhasedChrTrack({
  workspaceRoot,
  projectId,
  phasedTrackId,
  assemblyCtgId,
}) {
  if (isTauriRuntime()) {
    return addCtgToPhasedChrTrackTauri({
      workspaceRoot,
      projectId,
      phasedTrackId,
      assemblyCtgId,
    });
  }
  try {
    return await callDevBridge("/api/add-ctg-to-phased-chr-track", {
      workspaceRoot,
      projectId,
      phasedTrackId,
      assemblyCtgId,
    });
  } catch {
    // fallback to mock flow
  }
  return addCtgToPhasedChrTrackMock({ projectId, phasedTrackId, assemblyCtgId });
}

export async function removePhasedChrTrackItem({ workspaceRoot, projectId, phasedTrackItemId }) {
  if (isTauriRuntime()) {
    return removePhasedChrTrackItemTauri({ workspaceRoot, projectId, phasedTrackItemId });
  }
  try {
    return await callDevBridge("/api/remove-phased-chr-track-item", {
      workspaceRoot,
      projectId,
      phasedTrackItemId,
    });
  } catch {
    // fallback to mock flow
  }
  return removePhasedChrTrackItemMock({ projectId, phasedTrackItemId });
}

export async function reorderPhasedChrTrackItems({
  workspaceRoot,
  projectId,
  phasedTrackId,
  itemIds,
}) {
  if (isTauriRuntime()) {
    return reorderPhasedChrTrackItemsTauri({ workspaceRoot, projectId, phasedTrackId, itemIds });
  }
  try {
    return await callDevBridge("/api/reorder-phased-chr-track-items", {
      workspaceRoot,
      projectId,
      phasedTrackId,
      itemIds,
    });
  } catch {
    // fallback to mock flow
  }
  return reorderPhasedChrTrackItemsMock({ projectId, phasedTrackId, itemIds });
}

export async function listDeletedCtgs({ workspaceRoot, projectId, chrName = "", datasetId = null }) {
  if (isTauriRuntime()) {
    return listDeletedCtgsTauri({ workspaceRoot, projectId, chrName, datasetId });
  }
  try {
    return await callDevBridge("/api/list-deleted-ctgs", {
      workspaceRoot,
      projectId,
      chrName,
      datasetId,
    });
  } catch {
    // fallback to mock flow
  }
  return listDeletedCtgsMock({ workspaceRoot, projectId, chrName, datasetId });
}

export async function restoreDeletedCtg({ workspaceRoot, projectId, deletedCtgRecordId }) {
  if (isTauriRuntime()) {
    return restoreDeletedCtgTauri({ workspaceRoot, projectId, deletedCtgRecordId });
  }
  try {
    return await callDevBridge("/api/restore-deleted-ctg", {
      workspaceRoot,
      projectId,
      deletedCtgRecordId,
    });
  } catch {
    // fallback to mock flow
  }
  return restoreDeletedCtgMock({ workspaceRoot, projectId, deletedCtgRecordId });
}

export async function getCtgDetail({ workspaceRoot, projectId, assemblyCtgId }) {
  if (isTauriRuntime()) {
    return getCtgDetailTauri({ workspaceRoot, projectId, assemblyCtgId });
  }
  try {
    return await callDevBridge("/api/get-ctg-detail", {
      workspaceRoot,
      projectId,
      assemblyCtgId,
    });
  } catch {
    // fallback to mock flow
  }
  return getCtgDetailMock({ workspaceRoot, projectId, assemblyCtgId });
}

export async function listCtgEditCandidates({ workspaceRoot, projectId, assemblyCtgId }) {
  if (isTauriRuntime()) {
    return listCtgEditCandidatesTauri({ workspaceRoot, projectId, assemblyCtgId });
  }
  try {
    return await callDevBridge("/api/list-ctg-edit-candidates", {
      workspaceRoot,
      projectId,
      assemblyCtgId,
    });
  } catch {
    // fallback to mock flow
  }
  return listCtgEditCandidatesMock({ workspaceRoot, projectId, assemblyCtgId });
}

export async function runCtgEditorAction({ workspaceRoot, projectId, action, args }) {
  const normalizedAction = normalizeSupportedCtgEditorAction(action);
  if (isTauriRuntime()) {
    return runCtgEditorActionTauri({ workspaceRoot, projectId, action: normalizedAction, args });
  }
  try {
    return await callDevBridge("/api/ctg-editor-action", {
      workspaceRoot,
      projectId,
      action: normalizedAction,
      args,
    });
  } catch {
    // fallback to mock flow
  }
  return runCtgEditorActionMock({ workspaceRoot, projectId, action: normalizedAction, args });
}

export async function getJunctionInspection({
  workspaceRoot,
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
  minAlignmentLength = null,
  minMapq = null,
}) {
  if (isTauriRuntime()) {
    return getJunctionInspectionTauri({
      workspaceRoot,
      projectId,
      leftAssemblyCtgId,
      rightAssemblyCtgId,
      minAlignmentLength,
      minMapq,
    });
  }
  try {
    return await callDevBridge("/api/get-junction-inspection", {
      workspaceRoot,
      projectId,
      leftAssemblyCtgId,
      rightAssemblyCtgId,
      minAlignmentLength,
      minMapq,
    });
  } catch {
    // fallback to mock flow
  }
  return getJunctionInspectionMock({
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minMapq,
  });
}

export async function getTrackPairwiseEvidence({
  workspaceRoot,
  projectId,
  topAssemblyCtgIds,
  bottomAssemblyCtgIds,
  minAlignmentLength = null,
  minMapq = null,
}) {
  if (isTauriRuntime()) {
    return getTrackPairwiseEvidenceTauri({
      workspaceRoot,
      projectId,
      topAssemblyCtgIds,
      bottomAssemblyCtgIds,
      minAlignmentLength,
      minMapq,
    });
  }
  try {
    return await callDevBridge("/api/get-track-pairwise-evidence", {
      workspaceRoot,
      projectId,
      topAssemblyCtgIds,
      bottomAssemblyCtgIds,
      minAlignmentLength,
      minMapq,
    });
  } catch {
    // fallback to mock flow
  }
  return getTrackPairwiseEvidenceMock({
    workspaceRoot,
    projectId,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    minAlignmentLength,
    minMapq,
  });
}

export async function appendEditAuditLog({ workspaceRoot, projectId, category, action, detail }) {
  if (isTauriRuntime()) {
    return appendEditAuditLogTauri({ workspaceRoot, projectId, category, action, detail });
  }
  try {
    return await callDevBridge("/api/append-edit-audit-log", {
      workspaceRoot,
      projectId,
      category,
      action,
      detail,
    });
  } catch {
    // fallback to mock flow
  }
  return appendEditAuditLogMock({ workspaceRoot, projectId, category, action, detail });
}

export async function writeFinalPathExportTextFile({ outputPath, text, stateOrLocale = "zh" }) {
  if (!isTauriRuntime()) {
    throw normalizeWorkflowError("final path text export is unavailable in browser preview", {
      code: "BROWSER_EXPORT_UNAVAILABLE",
      source: "browser-preview",
      operation: "write_final_path_export_text_file",
    });
  }
  try {
    return await invokeCommand("write_final_path_export_text_file", {
      outputPath,
      text,
    }, stateOrLocale);
  } catch (error) {
    throw normalizeWorkflowError(error, {
      code: "TAURI_INVOKE_ERROR",
      source: "tauri",
      operation: "write_final_path_export_text_file",
    });
  }
}

export async function writeFinalPathExportBinaryFile({ outputPath, bytesBase64, stateOrLocale = "zh" }) {
  if (!isTauriRuntime()) {
    throw normalizeWorkflowError("final path binary export is unavailable in browser preview", {
      code: "BROWSER_EXPORT_UNAVAILABLE",
      source: "browser-preview",
      operation: "write_final_path_export_binary_file",
    });
  }
  try {
    return await invokeCommand("write_final_path_export_binary_file", {
      outputPath,
      bytesBase64,
    }, stateOrLocale);
  } catch (error) {
    throw normalizeWorkflowError(error, {
      code: "TAURI_INVOKE_ERROR",
      source: "tauri",
      operation: "write_final_path_export_binary_file",
    });
  }
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
  try {
    return await invokeCommand("export_final_path_fasta", {
      workspaceRoot,
      projectId,
      chrName,
      finalPathEntry,
      outputPath,
    }, stateOrLocale);
  } catch (error) {
    throw normalizeWorkflowError(error, {
      code: "TAURI_INVOKE_ERROR",
      source: "tauri",
      operation: "export_final_path_fasta",
    });
  }
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
  try {
    return await invokeCommand("export_project_final_path_fasta", {
      workspaceRoot,
      projectId,
      finalPathByChr,
      outputPath,
    }, stateOrLocale);
  } catch (error) {
    throw normalizeWorkflowError(error, {
      code: "TAURI_INVOKE_ERROR",
      source: "tauri",
      operation: "export_project_final_path_fasta",
    });
  }
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
    try {
      return await invokeCommand("export_degap_jobs", payload, stateOrLocale);
    } catch (error) {
      throw normalizeWorkflowError(error, {
        code: "TAURI_INVOKE_ERROR",
        source: "tauri",
        operation: "export_degap_jobs",
      });
    }
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
    trackScrollState,
    subviewTrackScrollState,
    finalPathTrackScrollState,
    finalPathViewMode,
    finalPathByChr,
    degapProjectState,
  });
}

async function importZipBundleMock({ zipPath, workspaceRoot, onStage, stateOrLocale = "zh" }) {
  onStage?.(t(stateOrLocale, "importer.runtime.importMockValidateZipAndWorkspace"));
  await sleep(250);
  onStage?.(t(stateOrLocale, "importer.runtime.importMockInspectBundle"));
  await sleep(300);
  onStage?.(t(stateOrLocale, "importer.runtime.importMockCreateWorkspace"));
  await sleep(300);
  return {
    workspaceRoot,
    message: t(stateOrLocale, "importer.runtime.importMockDoneZip", { zipPath, workspaceRoot }),
  };
}

async function importExtractedBundleMock({ extractedPath, onStage, stateOrLocale = "zh" }) {
  onStage?.(t(stateOrLocale, "importer.runtime.importMockValidateExtracted"));
  await sleep(260);
  onStage?.(t(stateOrLocale, "importer.runtime.importMockResolveWorkspaceRoot"));
  await sleep(320);
  const normalized = String(extractedPath || "").replace(/[\\/]+$/, "");
  const workspaceRoot = /(?:^|[\\/])gpm_server$/i.test(normalized)
    ? normalized
    : `${normalized}/gpm_server`;
  return {
    workspaceRoot,
    message: t(stateOrLocale, "importer.runtime.importMockDoneExtracted", { workspaceRoot }),
  };
}

async function validateWorkspaceIntegrityMock({ workspaceRoot }) {
  await sleep(100);
  return {
    workspaceRoot,
    ok: true,
    missing: [],
    resultPafCount: 1,
  };
}

async function deleteWorkspaceDirectoryMock({ workspaceRoot }) {
  await sleep(120);
  return {
    workspaceRoot,
    deleted: true,
  };
}

async function listProjectInitializerOptionsMock({ workspaceRoot }) {
  await sleep(200);
  return {
    workspaceRoot,
    packageMetadata: mockStore.packageMetadata,
    references: mockStore.references,
    datasets: mockStore.datasets,
    existingProjects: mockStore.existingProjects,
  };
}

async function initializeProjectMock({
  workspaceRoot,
  projectName,
  referenceGenomeId,
  primaryDatasetId,
  supportDatasetIds,
  chrAssignmentMinCoveragePercent = 60,
  phasedAssemblyEnabled = false,
}) {
  await sleep(240);
  const effectiveThreshold = Number(
    mockStore.packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
  );
  const projectId = mockStore.existingProjects.length + 1;
  mockStore.existingProjects = [
    ...mockStore.existingProjects,
    {
      projectId,
      projectName,
      referenceGenomeId,
      primaryDatasetId,
      supportDatasetIds: [...supportDatasetIds],
      chrAssignmentMinCoveragePercent: effectiveThreshold,
      phasedAssemblyEnabled: Boolean(phasedAssemblyEnabled),
      isProcessed: false,
      autoPipelineDone: false,
      workspaceRoot,
    },
  ];
  return {
    projectId,
    projectName,
    chrAssignmentMinCoveragePercent: effectiveThreshold,
    phasedAssemblyEnabled: Boolean(phasedAssemblyEnabled),
    supportDatasetIds: [...supportDatasetIds],
    existingProjects: mockStore.existingProjects,
  };
}

async function importAddDatasetPackageMock({
  workspaceRoot,
  zipPath,
  onStage,
  stateOrLocale = "zh",
}) {
  onStage?.(t(stateOrLocale, "importer.runtime.importMockAddPackageValidate"));
  await sleep(180);
  const datasetId = mockStore.datasets.reduce(
    (maxId, dataset) => Math.max(maxId, Number(dataset.datasetId || 0)),
    0,
  ) + 1;
  const baseName = String(zipPath || "").split(/[\\/]/).pop()?.replace(/\.zip$/i, "") || "added_dataset";
  const datasetName = baseName.replace(/^add[_-]/i, "") || `dataset_${datasetId}`;
  onStage?.(t(stateOrLocale, "importer.runtime.importMockAddPackageMerge"));
  await sleep(220);
  mockStore.datasets = [
    ...mockStore.datasets,
    {
      datasetId,
      label: datasetName,
      name: datasetName,
      contigCount: 0,
      totalLengthBp: 0,
      selfAlignmentAvailable: true,
    },
  ];
  return {
    workspaceRoot,
    packageMetadata: mockStore.packageMetadata,
    references: mockStore.references,
    datasets: mockStore.datasets,
    existingProjects: mockStore.existingProjects,
    datasetId,
    datasetName,
    message: t(stateOrLocale, "importer.runtime.importMockAddPackageDone", { zipPath }),
  };
}

async function importAddCtgPackageMock({
  workspaceRoot,
  projectId,
  zipPath,
  expectedTargetChr = "",
  expectedTargetTrack = "",
  onStage,
  stateOrLocale = "zh",
}) {
  onStage?.(t(stateOrLocale, "importer.runtime.importMockAddPackageValidate"));
  await sleep(120);
  onStage?.(t(stateOrLocale, "importer.runtime.importMockAddPackageMerge"));
  await sleep(160);
  const baseName = String(zipPath || "").split(/[\\/]/).pop()?.replace(/\.zip$/i, "") || "derived_ctg";
  return {
    workspaceRoot,
    projectId,
    datasetId: 0,
    sourceSeqId: 0,
    assemblyCtgId: 0,
    ctgName: baseName.replace(/^add[_-]/i, "") || "derived_ctg",
    targetTrack: expectedTargetTrack,
    targetChr: expectedTargetChr,
    message: t(stateOrLocale, "importer.runtime.tauriImportAddCtgPackageDone"),
  };
}

async function deleteProjectMock({ projectId }) {
  await sleep(120);
  mockStore.existingProjects = mockStore.existingProjects.filter(
    (item) => Number(item.projectId) !== Number(projectId),
  );
  return {
    projectId,
    deleted: true,
    existingProjects: mockStore.existingProjects,
  };
}

async function updateProjectMock({
  projectId,
  projectName,
  referenceGenomeId,
  primaryDatasetId,
  supportDatasetIds,
  chrAssignmentMinCoveragePercent = 60,
  phasedAssemblyEnabled,
  stateOrLocale = "zh",
}) {
  await sleep(150);
  const normalizedProjectId = Number(projectId);
  const nextName = String(projectName || "").trim();
  const target = mockStore.existingProjects.find(
    (item) => Number(item.projectId) === normalizedProjectId,
  );
  if (!target) {
    throw new Error(`project_id ${normalizedProjectId} does not exist`);
  }
  if (!nextName) {
    throw new Error("project_name must not be blank");
  }
  const isNameConflict = mockStore.existingProjects.some(
    (item) =>
      Number(item.projectId) !== normalizedProjectId &&
      String(item.projectName || "").toLowerCase() === nextName.toLowerCase(),
  );
  if (isNameConflict) {
    throw new Error(`project_name '${nextName}' already exists`);
  }
  const nextReferenceId = Number(referenceGenomeId);
  const nextPrimaryId = Number(primaryDatasetId);
  const nextSupportIds = Array.isArray(supportDatasetIds)
    ? supportDatasetIds.map((id) => Number(id))
    : [];
  const nextThreshold = Number(
    target.chrAssignmentMinCoveragePercent
      ?? mockStore.packageMetadata?.chrAssignmentMinCoveragePercent
      ?? 60,
  );
  const requestedThreshold = Number(chrAssignmentMinCoveragePercent ?? nextThreshold);
  const nextPhasedAssemblyEnabled =
    typeof phasedAssemblyEnabled === "boolean"
      ? phasedAssemblyEnabled
      : Boolean(target.phasedAssemblyEnabled);
  if (!Number.isFinite(nextThreshold) || nextThreshold < 0 || nextThreshold > 100) {
    throw new Error("chr_assignment_min_coverage_percent must be between 0 and 100");
  }
  if (target.isProcessed) {
    if (nextReferenceId !== Number(target.referenceGenomeId)) {
      throw new Error(t(stateOrLocale, "workspace.runtime.updateProcessedLocked"));
    }
    if (nextPrimaryId !== Number(target.primaryDatasetId)) {
      throw new Error(t(stateOrLocale, "workspace.runtime.updateProcessedLocked"));
    }
    if (Number.isFinite(requestedThreshold) && requestedThreshold !== nextThreshold) {
      throw new Error(t(stateOrLocale, "workspace.runtime.updateProcessedLocked"));
    }
    const existingSupportIds = Array.isArray(target.supportDatasetIds)
      ? target.supportDatasetIds.map((id) => Number(id))
      : [];
    for (const datasetId of existingSupportIds) {
      if (!nextSupportIds.includes(datasetId)) {
        throw new Error(t(stateOrLocale, "workspace.runtime.updateProcessedLocked"));
      }
    }
    if (target.phasedAssemblyEnabled && !nextPhasedAssemblyEnabled) {
      throw new Error(t(stateOrLocale, "workspace.runtime.updateProcessedLocked"));
    }
    const mergedSupportIds = [...existingSupportIds];
    for (const datasetId of nextSupportIds) {
      if (!mergedSupportIds.includes(datasetId)) {
        mergedSupportIds.push(datasetId);
      }
    }
    target.projectName = nextName;
    target.supportDatasetIds = mergedSupportIds;
    target.phasedAssemblyEnabled = Boolean(target.phasedAssemblyEnabled) || nextPhasedAssemblyEnabled;
    return {
      projectId: normalizedProjectId,
      projectName: nextName,
      referenceGenomeId: target.referenceGenomeId,
      primaryDatasetId: target.primaryDatasetId,
      supportDatasetIds: [...mergedSupportIds],
      chrAssignmentMinCoveragePercent: nextThreshold,
      phasedAssemblyEnabled: Boolean(target.phasedAssemblyEnabled),
      isProcessed: true,
      existingProjects: [...mockStore.existingProjects],
    };
  }

  target.projectName = nextName;
  target.referenceGenomeId = nextReferenceId;
  target.primaryDatasetId = nextPrimaryId;
  target.supportDatasetIds = nextSupportIds;
  target.chrAssignmentMinCoveragePercent = nextThreshold;
  target.phasedAssemblyEnabled = nextPhasedAssemblyEnabled;

  return {
    projectId: normalizedProjectId,
    projectName: nextName,
    referenceGenomeId: nextReferenceId,
    primaryDatasetId: nextPrimaryId,
    supportDatasetIds: [...nextSupportIds],
    chrAssignmentMinCoveragePercent: nextThreshold,
    phasedAssemblyEnabled: nextPhasedAssemblyEnabled,
    isProcessed: Boolean(target.isProcessed),
    existingProjects: [...mockStore.existingProjects],
  };
}

async function bootstrapProjectAssemblyMock() {
  await sleep(300);
  return {
    projectId: 1,
    assemblySeqCount: 6,
    assemblyCtgCount: 6,
    assemblyMemberCount: 6,
  };
}

async function autoAssignChrMock({ projectId }) {
  await sleep(240);
  return {
    projectId,
    processedCtgCount: 6,
    assignedCount: 6,
    repositionedCount: 0,
    clearedCount: 0,
    skippedManualCount: 0,
    noEvidenceCount: 0,
    refreshedChrCount: 2,
  };
}

async function autoOrientContigsMock({ projectId }) {
  await sleep(260);
  return {
    projectId,
    processedCtgCount: 6,
    orientedCtgCount: 6,
    flippedCtgCount: 2,
    noEvidenceCount: 0,
    skippedManualCount: 0,
  };
}

async function autoOrientContigsForDatasetMock({ projectId, datasetId }) {
  await sleep(180);
  return {
    projectId,
    datasetId,
    processedCtgCount: 2,
    orientedCtgCount: 2,
    flippedCtgCount: 1,
    noEvidenceCount: 0,
    skippedManualCount: 0,
  };
}

async function setProjectAutoPipelineDoneMock({ projectId, done }) {
  await sleep(80);
  mockStore.existingProjects = mockStore.existingProjects.map((item) =>
    Number(item.projectId) === Number(projectId)
      ? { ...item, autoPipelineDone: Boolean(done), isProcessed: true }
      : item,
  );
  return {
    projectId,
    autoPipelineDone: Boolean(done),
    existingProjects: mockStore.existingProjects,
  };
}

async function listProjectChromosomesMock({ projectId }) {
  await sleep(180);
  return {
    projectId,
    referenceGenomeId: 1,
    unplacedCtgCount: 0,
    unplacedBp: 0,
    items: [
      {
        chrName: "Chr01",
        chrOrder: 1,
        chrLength: 45027022,
        ctgCount: 4,
        placedBp: 43988320,
      },
      {
        chrName: "Chr02",
        chrOrder: 2,
        chrLength: 37301368,
        ctgCount: 2,
        placedBp: 22405854,
      },
    ],
  };
}

async function listNewSequencesMock({ limit }) {
  await sleep(120);
  return {
    items: applyListLimit([
      {
        assemblySeqId: 7001,
        datasetName: "hifiasm",
        seqName: "ptg_mock_7001",
        seqLength: 120000,
        hidden: false,
      },
      {
        assemblySeqId: 7002,
        datasetName: "flye",
        seqName: "utg_mock_7002",
        seqLength: 83000,
        hidden: true,
      },
    ], limit),
  };
}

async function listChrViewCtgsMock({ chrName, datasetId = null }) {
  await sleep(150);
  const samples = {
    Chr01: [
      {
        assemblyCtgId: 1,
        name: "Ctg1",
        assignedChrName: "Chr01",
        chrOrder: 1,
        anchorStart: 58212,
        refOrient: "+",
        placementMode: "auto",
        memberCount: 1,
        totalLength: 437166,
        datasetId: 1,
        datasetName: "hifiasm",
        originId: "utig4-001122l",
        hits: [
          {
            ctgStart: 1200,
            ctgEnd: 5200,
            blockLength: 4000,
          },
          {
            ctgStart: 9200,
            ctgEnd: 9800,
            blockLength: 600,
          },
        ],
      },
      {
        assemblyCtgId: 2,
        name: "Ctg2",
        assignedChrName: "Chr01",
        chrOrder: 2,
        anchorStart: 338097,
        refOrient: "+",
        placementMode: "auto",
        memberCount: 1,
        totalLength: 14814047,
        datasetId: 2,
        datasetName: "flye",
        originId: "contig_98",
        hits: [],
      },
    ],
    Chr02: [
      {
        assemblyCtgId: 3,
        name: "Ctg3",
        assignedChrName: "Chr02",
        chrOrder: 1,
        anchorStart: 45000,
        refOrient: "+",
        placementMode: "auto",
        memberCount: 2,
        totalLength: 6300000,
        datasetId: 1,
        datasetName: "hifiasm",
        originId: "",
        hits: [],
      },
    ],
  };
  const normalizedDatasetId = Number(datasetId);
  const items = (samples[chrName] || []).filter((item) => {
    if (!Number.isFinite(normalizedDatasetId) || normalizedDatasetId <= 0) {
      return true;
    }
    return Number(item.datasetId) === Math.trunc(normalizedDatasetId);
  });
  return {
    items,
  };
}

async function listReferenceTrackMembersMock({ chrName }) {
  await sleep(80);
  const normalizedChrName = String(chrName || "").trim() || "Chr01";
  return {
    items: [
      {
        sourceKind: "ref_segment",
        referenceChrId: 1,
        referenceChrName: normalizedChrName,
        segmentOrder: 1,
        segmentStartBp: 1,
        segmentEndBp: 5000000,
        name: `ref_${normalizedChrName}:1-5000000`,
        anchorStart: 1,
        totalLength: 5000000,
        refOrient: "+",
        hits: [],
      },
    ],
  };
}

const PHASED_HAPLOTYPE_KEYS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");
const DEFAULT_PHASED_TRACK_GAP_BEFORE_PX = 20;

async function listPhasedChrTracksMock({ projectId, parentChrName }) {
  await sleep(60);
  const normalizedProjectId = Number(projectId);
  const normalizedParentChrName = normalizeRequiredText("parentChrName", parentChrName);
  return {
    projectId: normalizedProjectId,
    parentChrName: normalizedParentChrName,
    tracks: mockStore.phasedChrTracks
      .filter(
        (track) =>
          Number(track.projectId) === normalizedProjectId &&
          track.parentChrName === normalizedParentChrName,
      )
      .sort((left, right) => left.displayOrder - right.displayOrder)
      .map(clonePhasedTrack),
  };
}

async function createPhasedChrTrackMock({ projectId, parentChrName }) {
  await sleep(80);
  const normalizedProjectId = Number(projectId);
  const normalizedParentChrName = normalizeRequiredText("parentChrName", parentChrName);
  const project = mockStore.existingProjects.find(
    (item) => Number(item.projectId) === normalizedProjectId,
  );
  if (!project) {
    throw new Error(`project_id ${normalizedProjectId} does not exist`);
  }
  if (!project.phasedAssemblyEnabled) {
    throw new Error(`project_id ${normalizedProjectId} has phased assembly disabled`);
  }
  const existingKeys = new Set(
    mockStore.phasedChrTracks
      .filter(
        (track) =>
          Number(track.projectId) === normalizedProjectId &&
          track.parentChrName === normalizedParentChrName,
      )
      .map((track) => track.haplotypeKey),
  );
  const haplotypeKey = PHASED_HAPLOTYPE_KEYS.find((key) => !existingKeys.has(key));
  if (!haplotypeKey) {
    throw new Error(`parent_chr_name '${normalizedParentChrName}' already has 26 phased tracks`);
  }
  const displayOrder =
    Math.max(
      0,
      ...mockStore.phasedChrTracks
        .filter(
          (track) =>
            Number(track.projectId) === normalizedProjectId &&
            track.parentChrName === normalizedParentChrName,
        )
        .map((track) => Number(track.displayOrder) || 0),
    ) + 1;
  const track = {
    phasedTrackId: mockStore.nextPhasedTrackId,
    projectId: normalizedProjectId,
    parentChrName: normalizedParentChrName,
    haplotypeKey,
    label: `${normalizedParentChrName}${haplotypeKey}`,
    displayOrder,
    items: [],
  };
  mockStore.nextPhasedTrackId += 1;
  mockStore.phasedChrTracks = [...mockStore.phasedChrTracks, track];
  return { track: clonePhasedTrack(track) };
}

async function deletePhasedChrTrackMock({ projectId, phasedTrackId }) {
  await sleep(70);
  const track = findMockPhasedTrack(projectId, phasedTrackId);
  mockStore.phasedChrTracks = mockStore.phasedChrTracks.filter(
    (item) => item.phasedTrackId !== track.phasedTrackId,
  );
  compactMockPhasedTracks(track.projectId, track.parentChrName);
  return {
    projectId: track.projectId,
    phasedTrackId: track.phasedTrackId,
    parentChrName: track.parentChrName,
    haplotypeKey: track.haplotypeKey,
    label: track.label,
    deleted: true,
  };
}

function compactMockPhasedTracks(projectId, parentChrName) {
  const tracks = mockStore.phasedChrTracks
    .filter((track) =>
      Number(track.projectId) === Number(projectId)
      && track.parentChrName === parentChrName,
    )
    .sort((left, right) => left.displayOrder - right.displayOrder || left.phasedTrackId - right.phasedTrackId);
  tracks.forEach((track, index) => {
    const haplotypeKey = PHASED_HAPLOTYPE_KEYS[index] || track.haplotypeKey;
    track.haplotypeKey = haplotypeKey;
    track.label = `${parentChrName}${haplotypeKey}`;
    track.displayOrder = index + 1;
  });
}

async function addCtgToPhasedChrTrackMock({ projectId, phasedTrackId, assemblyCtgId }) {
  await sleep(70);
  const track = findMockPhasedTrack(projectId, phasedTrackId);
  const displayOrder = Math.max(0, ...track.items.map((item) => Number(item.displayOrder) || 0)) + 1;
  const item = {
    itemId: mockStore.nextPhasedTrackItemId,
    phasedTrackId: track.phasedTrackId,
    assemblyCtgId: Number(assemblyCtgId),
    displayOrder,
    gapBeforePx: DEFAULT_PHASED_TRACK_GAP_BEFORE_PX,
    orient: "+",
  };
  mockStore.nextPhasedTrackItemId += 1;
  track.items = [...track.items, item];
  return { item: { ...item } };
}

async function removePhasedChrTrackItemMock({ projectId, phasedTrackItemId }) {
  await sleep(60);
  const { track, item } = findMockPhasedTrackItem(projectId, phasedTrackItemId);
  track.items = track.items.filter((candidate) => candidate.itemId !== item.itemId);
  return {
    projectId: track.projectId,
    phasedTrackId: track.phasedTrackId,
    phasedTrackItemId: item.itemId,
    removed: true,
  };
}

async function reorderPhasedChrTrackItemsMock({ projectId, phasedTrackId, itemIds }) {
  await sleep(70);
  const track = findMockPhasedTrack(projectId, phasedTrackId);
  const normalizedItemIds = Array.isArray(itemIds) ? itemIds.map((item) => Number(item)) : [];
  const currentIds = track.items.map((item) => item.itemId);
  if (normalizedItemIds.length !== currentIds.length) {
    throw new Error("itemIds must exactly match the current phased track items");
  }
  const sortedRequested = [...normalizedItemIds].sort((left, right) => left - right);
  const sortedCurrent = [...currentIds].sort((left, right) => left - right);
  const sameSet = sortedRequested.every((itemId, index) => itemId === sortedCurrent[index]);
  if (!sameSet) {
    throw new Error("itemIds must exactly match the current phased track items");
  }
  const itemById = new Map(track.items.map((item) => [item.itemId, item]));
  track.items = normalizedItemIds.map((itemId, index) => ({
    ...itemById.get(itemId),
    displayOrder: index + 1,
  }));
  return {
    projectId: track.projectId,
    phasedTrackId: track.phasedTrackId,
    itemCount: track.items.length,
  };
}

function normalizeRequiredText(name, value) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    throw new Error(`${name} must not be blank`);
  }
  return normalized;
}

function findMockPhasedTrack(projectId, phasedTrackId) {
  const normalizedProjectId = Number(projectId);
  const normalizedTrackId = Number(phasedTrackId);
  const track = mockStore.phasedChrTracks.find(
    (item) =>
      Number(item.projectId) === normalizedProjectId &&
      Number(item.phasedTrackId) === normalizedTrackId,
  );
  if (!track) {
    throw new Error(`phased_track_id ${normalizedTrackId} does not exist`);
  }
  return track;
}

function findMockPhasedTrackItem(projectId, phasedTrackItemId) {
  const normalizedItemId = Number(phasedTrackItemId);
  for (const track of mockStore.phasedChrTracks) {
    if (Number(track.projectId) !== Number(projectId)) {
      continue;
    }
    const item = track.items.find((candidate) => Number(candidate.itemId) === normalizedItemId);
    if (item) {
      return { track, item };
    }
  }
  throw new Error(`phased_track_item_id ${normalizedItemId} does not exist`);
}

function normalizeMockOrient(value) {
  return String(value || "").trim() === "-" ? "-" : "+";
}

function clonePhasedTrack(track) {
  return {
    ...track,
    items: track.items.map((item) => ({ ...item })),
  };
}

async function listDeletedCtgsMock({ chrName, datasetId = null }) {
  await sleep(80);
  if (String(chrName || "").trim() && String(chrName || "").trim() !== "Chr01") {
    return { items: [] };
  }
  const normalizedDatasetId = Number(datasetId);
  return {
    items: [
      {
        deletedCtgRecordId: 9901,
        projectId: 7,
        assemblyCtgId: 77,
        name: "ctg-deleted-77",
        assignedChrName: "Chr01",
        chrOrder: 9,
        anchorStart: 880000,
        refOrient: "+",
        placementMode: "manual",
        memberCount: 2,
        totalLength: 65432,
        deletedAt: "1775000000",
        datasetId: 11,
      },
    ].filter((item) => {
      if (!Number.isFinite(normalizedDatasetId) || normalizedDatasetId <= 0) {
        return true;
      }
      return Number(item.datasetId) === Math.trunc(normalizedDatasetId);
    }),
  };
}

async function restoreDeletedCtgMock({ projectId, deletedCtgRecordId }) {
  await sleep(100);
  return {
    projectId,
    deletedCtgRecordId,
    assemblyCtgId: 77,
    restoredMemberCount: 2,
    refreshedChrCount: 1,
  };
}

async function getCtgDetailMock({ assemblyCtgId }) {
  await sleep(120);
  return {
    assemblyCtgId,
    name: `Ctg${assemblyCtgId}`,
    assignedChrName: "Chr01",
    chrOrder: 1,
    anchorStart: 58212,
    refOrient: "+",
    placementMode: "auto",
    members: [
      {
        assemblyCtgMemberId: 5000 + assemblyCtgId,
        memberOrder: 1,
        assemblySeqId: 1000 + assemblyCtgId,
        datasetName: "hifiasm",
        seqName: `ptg${String(assemblyCtgId).padStart(6, "0")}l`,
        seqLength: 437166,
        orient: "+",
        sourceStart: 1,
        sourceEnd: 437166,
        leftEndType: "normal",
        rightEndType: "normal",
        hidden: false,
      },
    ],
  };
}

async function listCtgEditCandidatesMock() {
  await sleep(120);
  return {
    moveTargetCtgs: [
      { assemblyCtgId: 2, name: "Ctg2", assignedChrName: "Chr01", chrOrder: 2 },
      { assemblyCtgId: 3, name: "Ctg3", assignedChrName: "Chr02", chrOrder: 1 },
    ],
    addSeqCandidates: [
      {
        assemblySeqId: 7001,
        datasetName: "hifiasm",
        seqName: "ptg_mock_7001",
        seqLength: 120000,
        hidden: false,
      },
      {
        assemblySeqId: 7002,
        datasetName: "flye",
        seqName: "utg_mock_7002",
        seqLength: 83000,
        hidden: true,
      },
    ],
  };
}

async function runCtgEditorActionMock({ projectId, action, args = {} }) {
  await sleep(100);
  if (action === "flip-ctg" && Number(args?.phasedTrackItemId || 0) > 0) {
    const { item } = findMockPhasedTrackItem(projectId, args.phasedTrackItemId);
    item.orient = normalizeMockOrient(item.orient) === "-" ? "+" : "-";
  }
  return {
    action,
    changed: true,
  };
}

const SUPPORTED_CTG_EDITOR_ACTIONS = new Set([
  "rename-ctg",
  "flip-ctg",
  "delete-ctg",
  "restore-deleted-ctg",
  "flip-seq",
  "hide-seq",
  "show-seq",
  "set-end-type",
]);

function normalizeSupportedCtgEditorAction(action) {
  const normalized = String(action || "").trim().toLowerCase();
  if (SUPPORTED_CTG_EDITOR_ACTIONS.has(normalized)) {
    return normalized;
  }
  throw new Error(`unsupported ctg editor action: ${normalized || "<empty>"}`);
}

async function getJunctionInspectionMock({
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
}) {
  await sleep(220);
  return {
    projectId,
    assignedChrName: "Chr01",
    placementRelation: "overlap",
    overlapBp: 3245,
    gapBp: null,
    sameDataset: true,
    evidenceSource: "self_paf",
    evidenceHitCount: 1,
    left: {
      assemblyCtgId: leftAssemblyCtgId,
      name: `Ctg${leftAssemblyCtgId}`,
    },
    right: {
      assemblyCtgId: rightAssemblyCtgId,
      name: `Ctg${rightAssemblyCtgId}`,
    },
    hits: [
      {
        queryAssemblyCtgId: leftAssemblyCtgId,
        querySourceSeqId: 4503,
        querySourceSeqName: "ctg499",
        subjectAssemblyCtgId: rightAssemblyCtgId,
        subjectSourceSeqId: 1959,
        subjectSourceSeqName: "ctg577",
        strand: "+",
        queryStart: 12,
        queryEnd: 3212,
        subjectStart: 19,
        subjectEnd: 3219,
        mapq: 60,
        identityPct: 99.61,
        alignLength: 3200,
        mismatchCount: 5,
        gapOpenCount: 0,
        evalue: 0,
        bitScore: 5812,
        evidenceOrigin: "self_paf",
      },
    ],
  };
}

async function getTrackPairwiseEvidenceMock({
  projectId,
  topAssemblyCtgIds = [],
  bottomAssemblyCtgIds = [],
}) {
  await sleep(220);
  const topAssemblyCtgId = Number(topAssemblyCtgIds[0] || 0);
  const bottomAssemblyCtgId = Number(bottomAssemblyCtgIds[0] || 0);
  return {
    projectId,
    assignedChrName: "Chr01",
    sameDataset: topAssemblyCtgId > 0 && bottomAssemblyCtgId > 0,
    evidenceSource: "self_paf",
    evidenceHitCount: topAssemblyCtgId > 0 && bottomAssemblyCtgId > 0 ? 1 : 0,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    hits: topAssemblyCtgId > 0 && bottomAssemblyCtgId > 0
      ? [
          {
            queryAssemblyCtgId: topAssemblyCtgId,
            querySourceSeqId: 4503,
            querySourceSeqName: `ctg${topAssemblyCtgId}`,
            subjectAssemblyCtgId: bottomAssemblyCtgId,
            subjectSourceSeqId: 1959,
            subjectSourceSeqName: `ctg${bottomAssemblyCtgId}`,
            strand: "+",
            queryStart: 12,
            queryEnd: 3212,
            subjectStart: 19,
            subjectEnd: 3219,
            mapq: 60,
            identityPct: 99.61,
            alignLength: 3200,
            mismatchCount: 5,
            gapOpenCount: 0,
            evalue: 0,
            bitScore: 5812,
            evidenceOrigin: "self_paf",
          },
        ]
      : [],
  };
}

async function appendEditAuditLogMock({ projectId, category, action, detail }) {
  await sleep(60);
  return {
    id: Math.trunc(Date.now() / 1000),
    projectId,
    category: category || "session",
    action: action || "unknown",
    detail: detail || null,
    createdAt: String(Math.floor(Date.now() / 1000)),
  };
}

async function getProjectAssemblyViewStateMock({ projectId }) {
  await sleep(80);
  return {
    source: "mock",
    projectId,
    supportDatasetId: null,
    trackView: {},
    supportDsCtgLenRulesByChr: {},
    supportMirroredCtgs: [],
    hiddenPrimaryCtgIds: [],
    hiddenPrimaryCtgIdsByChr: {},
    trackDragOffsets: [],
    subviewTrackDragOffsets: [],
    trackScrollState: {},
    subviewTrackScrollState: {},
    finalPathTrackScrollState: {},
    finalPathViewMode: "graph",
    finalPathByChr: {},
    degapProjectState: {},
  };
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
  trackScrollState = {},
  subviewTrackScrollState = {},
  finalPathTrackScrollState = {},
  finalPathViewMode = "graph",
  finalPathByChr = {},
  degapProjectState = {},
}) {
  await sleep(80);
  return {
    source: "mock",
    projectId,
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
}

export async function requestImportCancel({ runId, stateOrLocale = "zh" }) {
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) {
    return { cancelRequested: false };
  }
  if (!isTauriRuntime()) {
    return { runId: normalizedRunId, cancelRequested: true };
  }
  return invokeCommand("request_import_cancel", { runId: normalizedRunId }, stateOrLocale);
}

async function withImportProgressListener(runId, onStage, operation) {
  const normalizedRunId = String(runId || "").trim();
  let unlisten = () => {};
  if (normalizedRunId) {
    unlisten = await listenBackendEvent("gpm-next://import-progress", (event) => {
      const payload = event?.payload || {};
      if (String(payload.runId || "") !== normalizedRunId) {
        return;
      }
      const fallback = `${payload.stage || ""}：${payload.detail || ""}`;
      const stage = {
        label: String(payload.label || fallback),
        text: String(payload.text || payload.label || fallback),
      };
      const progressIndex = Number(payload.progressIndex);
      const progressTotal = Number(payload.progressTotal);
      if (Number.isFinite(progressIndex) && progressIndex > 0) {
        stage.progressIndex = progressIndex;
      }
      if (Number.isFinite(progressTotal) && progressTotal > 0) {
        stage.progressTotal = progressTotal;
      }
      onStage?.(stage);
    });
  }
  try {
    return await operation();
  } finally {
    unlisten();
  }
}

async function importZipBundleTauri({ zipPath, workspaceRoot, onStage, runId = "", stateOrLocale = "zh" }) {
  onStage?.(t(stateOrLocale, "importer.runtime.tauriImportZipStage"));
  const result = await withImportProgressListener(runId, onStage, () => invokeCommand("import_zip", {
    zipPath,
    workspaceRoot,
    runId,
  }, stateOrLocale));
  return {
    workspaceRoot: result.workspaceRoot || workspaceRoot,
    message: result.message || t(stateOrLocale, "importer.runtime.tauriImportZipDone"),
  };
}

async function importExtractedBundleTauri({ extractedPath, onStage, runId = "", stateOrLocale = "zh" }) {
  onStage?.(t(stateOrLocale, "importer.runtime.tauriImportExtractedStage"));
  const result = await withImportProgressListener(runId, onStage, () => invokeCommand("import_extracted", {
    extractedPath,
    runId,
  }, stateOrLocale));
  return {
    workspaceRoot: result.workspaceRoot,
    message: result.message || t(stateOrLocale, "importer.runtime.tauriImportExtractedDone"),
  };
}

async function importAddDatasetPackageTauri({
  workspaceRoot,
  zipPath,
  onStage,
  runId = "",
  stateOrLocale = "zh",
}) {
  onStage?.(t(stateOrLocale, "importer.runtime.tauriImportAddPackageStage"));
  const result = await withImportProgressListener(runId, onStage, () => invokeCommand("import_add_dataset_package", {
    workspaceRoot,
    zipPath,
    runId,
  }, stateOrLocale));
  return {
    workspaceRoot: result.workspaceRoot || workspaceRoot,
    packageMetadata: result.packageMetadata || mockStore.packageMetadata,
    references: result.references || [],
    datasets: result.datasets || [],
    existingProjects: result.existingProjects || [],
    datasetId: result.datasetId,
    datasetName: result.datasetName,
    message: result.message || t(stateOrLocale, "importer.runtime.tauriImportAddPackageDone"),
  };
}

async function importAddCtgPackageTauri({
  workspaceRoot,
  projectId,
  zipPath,
  expectedTargetChr = "",
  expectedTargetTrack = "",
  onStage,
  runId = "",
  stateOrLocale = "zh",
}) {
  onStage?.(t(stateOrLocale, "importer.runtime.tauriImportAddCtgPackageStage"));
  const result = await withImportProgressListener(runId, onStage, () => invokeCommand("import_add_ctg_package", {
    workspaceRoot,
    projectId,
    zipPath,
    expectedTargetChr,
    expectedTargetTrack,
    runId,
  }, stateOrLocale));
  return {
    workspaceRoot: result.workspaceRoot || workspaceRoot,
    packageMetadata: result.packageMetadata || mockStore.packageMetadata,
    references: result.references || [],
    datasets: result.datasets || [],
    existingProjects: result.existingProjects || [],
    datasetId: result.datasetId,
    sourceSeqId: result.sourceSeqId,
    assemblyCtgId: result.assemblyCtgId,
    ctgName: result.ctgName,
    targetTrack: result.targetTrack,
    targetChr: result.targetChr,
    message: result.message || t(stateOrLocale, "importer.runtime.tauriImportAddCtgPackageDone"),
  };
}

async function listProjectInitializerOptionsTauri({ workspaceRoot }) {
  const result = await invokeCommand("list_project_initializer_options", {
    workspaceRoot,
  });
  return {
    workspaceRoot,
    packageMetadata: result.packageMetadata || {
      packageMode: "fast",
      sequenceLayout: "partitioned",
      preassignedChr: true,
      chrAssignmentMinCoveragePercent: 60,
      selfAlignmentScope: "chr_partition",
      crossAlignmentScope: "chr_partition",
    },
    references: result.references || [],
    datasets: result.datasets || [],
    existingProjects: result.existingProjects || [],
  };
}

async function openWorkspaceTauri({ workspaceRoot }) {
  const result = await invokeCommand("open_workspace", {
    workspaceRoot,
  });
  return {
    workspaceRoot,
    packageMetadata: result.packageMetadata || {
      packageMode: "fast",
      sequenceLayout: "partitioned",
      preassignedChr: true,
      chrAssignmentMinCoveragePercent: 60,
      selfAlignmentScope: "chr_partition",
      crossAlignmentScope: "chr_partition",
    },
    references: result.references || [],
    datasets: result.datasets || [],
    existingProjects: result.existingProjects || [],
  };
}

async function validateWorkspaceIntegrityTauri({ workspaceRoot }) {
  return invokeCommand("validate_workspace_integrity", {
    workspaceRoot,
  });
}

async function deleteWorkspaceDirectoryTauri({ workspaceRoot }) {
  return invokeCommand("delete_workspace_directory", {
    workspaceRoot,
  });
}

async function initializeProjectTauri({
  workspaceRoot,
  projectName,
  referenceGenomeId,
  primaryDatasetId,
  supportDatasetIds,
  chrAssignmentMinCoveragePercent = 60,
  phasedAssemblyEnabled = false,
}) {
  const result = await invokeCommand("initialize_project", {
    workspaceRoot,
    projectName,
    referenceGenomeId,
    primaryDatasetId,
    supportDatasetIds,
    chrAssignmentMinCoveragePercent,
    phasedAssemblyEnabled,
  });
  return {
    projectId: result.projectId,
    projectName: result.projectName || projectName,
    chrAssignmentMinCoveragePercent:
      result.chrAssignmentMinCoveragePercent ?? chrAssignmentMinCoveragePercent,
    phasedAssemblyEnabled: Boolean(result.phasedAssemblyEnabled),
    existingProjects: result.existingProjects || [],
  };
}

async function deleteProjectTauri({ workspaceRoot, projectId }) {
  const result = await invokeCommand("delete_project", {
    workspaceRoot,
    projectId,
  });
  const response = {
    projectId,
    deleted: Boolean(result.deleted),
  };
  if (Array.isArray(result.existingProjects)) {
    response.existingProjects = result.existingProjects;
  }
  return response;
}

async function updateProjectTauri({
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
  const result = await invokeCommand("update_project", {
    workspaceRoot,
    projectId,
    projectName,
    referenceGenomeId,
    primaryDatasetId,
    supportDatasetIds,
    chrAssignmentMinCoveragePercent,
    phasedAssemblyEnabled,
  }, stateOrLocale);
  return {
    projectId: result.projectId || projectId,
    projectName: result.projectName || projectName,
    referenceGenomeId: result.referenceGenomeId || referenceGenomeId,
    primaryDatasetId: result.primaryDatasetId || primaryDatasetId,
    supportDatasetIds: Array.isArray(result.supportDatasetIds)
      ? result.supportDatasetIds
      : Array.isArray(supportDatasetIds)
        ? supportDatasetIds
        : [],
    chrAssignmentMinCoveragePercent:
      result.chrAssignmentMinCoveragePercent ?? chrAssignmentMinCoveragePercent,
    phasedAssemblyEnabled: Boolean(result.phasedAssemblyEnabled),
    isProcessed: Boolean(result.isProcessed),
    existingProjects: result.existingProjects || [],
  };
}

async function bootstrapProjectAssemblyTauri({ workspaceRoot, projectId, runId = null }) {
  const result = await invokeCommand("bootstrap_project_assembly", {
    workspaceRoot,
    projectId,
    runId,
  });
  return {
    projectId: result.projectId || projectId,
    assemblySeqCount: result.assemblySeqCount || 0,
    assemblyCtgCount: result.assemblyCtgCount || 0,
    assemblyMemberCount: result.assemblyMemberCount || 0,
  };
}

async function autoAssignChrTauri({ workspaceRoot, projectId, runId = null }) {
  const result = await invokeCommand("auto_assign_chr", {
    workspaceRoot,
    projectId,
    runId,
  });
  return {
    projectId: result.projectId || projectId,
    processedCtgCount: result.processedCtgCount || 0,
    assignedCount: result.assignedCount || 0,
    repositionedCount: result.repositionedCount || 0,
    clearedCount: result.clearedCount || 0,
    skippedManualCount: result.skippedManualCount || 0,
    noEvidenceCount: result.noEvidenceCount || 0,
    refreshedChrCount: result.refreshedChrCount || 0,
  };
}

async function autoOrientContigsTauri({ workspaceRoot, projectId, runId = null }) {
  const result = await invokeCommand("auto_orient_contigs", {
    workspaceRoot,
    projectId,
    runId,
  });
  return {
    projectId: result.projectId || projectId,
    processedCtgCount: result.processedCtgCount || 0,
    orientedCtgCount: result.orientedCtgCount || 0,
    flippedCtgCount: result.flippedCtgCount || 0,
    noEvidenceCount: result.noEvidenceCount || 0,
    skippedManualCount: result.skippedManualCount || 0,
  };
}

async function autoOrientContigsForDatasetTauri({
  workspaceRoot,
  projectId,
  datasetId,
  runId = null,
}) {
  const result = await invokeCommand("auto_orient_contigs_for_dataset", {
    workspaceRoot,
    projectId,
    datasetId,
    runId,
  });
  return {
    projectId: result.projectId || projectId,
    datasetId: result.datasetId || datasetId,
    processedCtgCount: result.processedCtgCount || 0,
    orientedCtgCount: result.orientedCtgCount || 0,
    flippedCtgCount: result.flippedCtgCount || 0,
    noEvidenceCount: result.noEvidenceCount || 0,
    skippedManualCount: result.skippedManualCount || 0,
  };
}

async function setProjectAutoPipelineDoneTauri({ workspaceRoot, projectId, done = true }) {
  const result = await invokeCommand("set_project_auto_pipeline_done", {
    workspaceRoot,
    projectId,
    done,
  });
  return {
    projectId: result.projectId || projectId,
    autoPipelineDone: Boolean(result.autoPipelineDone),
    existingProjects: result.existingProjects || [],
  };
}

async function requestAutoPipelineCancelTauri({ workspaceRoot, projectId, runId }) {
  return invokeCommand("request_auto_pipeline_cancel", {
    workspaceRoot,
    projectId,
    runId,
  });
}

async function listProjectChromosomesTauri({ workspaceRoot, projectId }) {
  const result = await invokeWorkflowCommand("list_project_chromosomes", {
    workspaceRoot,
    projectId,
  });
  return {
    projectId,
    referenceGenomeId: result.referenceGenomeId || 0,
    unplacedCtgCount: result.unplacedCtgCount || 0,
    unplacedBp: result.unplacedBp || 0,
    items: result.items || [],
  };
}

async function listNewSequencesTauri({ workspaceRoot, projectId, limit }) {
  const result = await invokeWorkflowCommand("list_new_sequences", {
    workspaceRoot,
    projectId,
    limit,
  });
  return {
    items: applyListLimit(result.items, limit),
  };
}

async function listChrViewCtgsTauri({ workspaceRoot, projectId, chrName, datasetId = null }) {
  const result = await invokeWorkflowCommand("list_chr_view_ctgs", {
    workspaceRoot,
    projectId,
    chrName,
    datasetId,
  });
  return {
    items: result.items || [],
  };
}

async function listReferenceTrackMembersTauri({ workspaceRoot, projectId, chrName }) {
  const result = await invokeWorkflowCommand("list_reference_track_members", {
    workspaceRoot,
    projectId,
    chrName,
  });
  return {
    items: result.items || [],
  };
}

async function listPhasedChrTracksTauri({ workspaceRoot, projectId, parentChrName }) {
  const result = await invokeWorkflowCommand("list_phased_chr_tracks", {
    workspaceRoot,
    projectId,
    parentChrName,
  });
  return {
    projectId: result.projectId || projectId,
    parentChrName: result.parentChrName || parentChrName,
    tracks: result.tracks || [],
  };
}

async function createPhasedChrTrackTauri({ workspaceRoot, projectId, parentChrName }) {
  return invokeWorkflowCommand("create_phased_chr_track", {
    workspaceRoot,
    projectId,
    parentChrName,
  });
}

async function deletePhasedChrTrackTauri({ workspaceRoot, projectId, phasedTrackId }) {
  return invokeWorkflowCommand("delete_phased_chr_track", {
    workspaceRoot,
    projectId,
    phasedTrackId,
  });
}

async function addCtgToPhasedChrTrackTauri({
  workspaceRoot,
  projectId,
  phasedTrackId,
  assemblyCtgId,
}) {
  return invokeWorkflowCommand("add_ctg_to_phased_chr_track", {
    workspaceRoot,
    projectId,
    phasedTrackId,
    assemblyCtgId,
  });
}

async function removePhasedChrTrackItemTauri({
  workspaceRoot,
  projectId,
  phasedTrackItemId,
}) {
  return invokeWorkflowCommand("remove_phased_chr_track_item", {
    workspaceRoot,
    projectId,
    phasedTrackItemId,
  });
}

async function reorderPhasedChrTrackItemsTauri({
  workspaceRoot,
  projectId,
  phasedTrackId,
  itemIds,
}) {
  return invokeWorkflowCommand("reorder_phased_chr_track_items", {
    workspaceRoot,
    projectId,
    phasedTrackId,
    itemIds,
  });
}

async function listDeletedCtgsTauri({ workspaceRoot, projectId, chrName = "", datasetId = null }) {
  const result = await invokeWorkflowCommand("list_deleted_ctgs", {
    workspaceRoot,
    projectId,
    chrName: String(chrName || "").trim() || null,
    datasetId: Number.isFinite(Number(datasetId)) && Number(datasetId) > 0 ? Math.trunc(Number(datasetId)) : null,
  });
  return {
    items: result.items || [],
  };
}

async function restoreDeletedCtgTauri({ workspaceRoot, projectId, deletedCtgRecordId }) {
  return invokeWorkflowCommand("restore_deleted_ctg", {
    workspaceRoot,
    projectId,
    deletedCtgRecordId,
  });
}

async function getCtgDetailTauri({ workspaceRoot, projectId, assemblyCtgId }) {
  return invokeWorkflowCommand("get_ctg_detail", {
    workspaceRoot,
    projectId,
    assemblyCtgId,
  });
}

async function listCtgEditCandidatesTauri({ workspaceRoot, projectId, assemblyCtgId }) {
  const result = await invokeWorkflowCommand("list_ctg_edit_candidates", {
    workspaceRoot,
    projectId,
    assemblyCtgId,
  });
  return {
    moveTargetCtgs: result.moveTargetCtgs || [],
    addSeqCandidates: result.addSeqCandidates || [],
  };
}

async function runCtgEditorActionTauri({ workspaceRoot, projectId, action, args }) {
  return invokeWorkflowCommand("run_ctg_editor_action", {
    workspaceRoot,
    projectId,
    action,
    args,
  });
}

async function getJunctionInspectionTauri({
  workspaceRoot,
  projectId,
  leftAssemblyCtgId,
  rightAssemblyCtgId,
  minAlignmentLength = null,
  minMapq = null,
}) {
  return invokeWorkflowCommand("get_junction_inspection", {
    workspaceRoot,
    projectId,
    leftAssemblyCtgId,
    rightAssemblyCtgId,
    minAlignmentLength,
    minMapq,
  });
}

async function getTrackPairwiseEvidenceTauri({
  workspaceRoot,
  projectId,
  topAssemblyCtgIds,
  bottomAssemblyCtgIds,
  minAlignmentLength = null,
  minMapq = null,
}) {
  return invokeWorkflowCommand("get_track_pairwise_evidence", {
    workspaceRoot,
    projectId,
    topAssemblyCtgIds,
    bottomAssemblyCtgIds,
    minAlignmentLength,
    minMapq,
  });
}

async function appendEditAuditLogTauri({ workspaceRoot, projectId, category, action, detail }) {
  return invokeCommand("append_edit_audit_log", {
    workspaceRoot,
    projectId,
    category,
    action,
    detail,
  });
}

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
  trackScrollState = {},
  subviewTrackScrollState = {},
  finalPathTrackScrollState = {},
  finalPathViewMode = "graph",
  finalPathByChr = {},
  degapProjectState = {},
}) {
  return invokeCommand("update_project_assembly_view_state", {
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
    trackScrollState,
    subviewTrackScrollState,
    finalPathTrackScrollState,
    finalPathViewMode,
    finalPathByChr,
    degapProjectState,
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

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function callDevBridge(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw normalizeWorkflowError(body.error || `dev bridge error: ${response.status}`, {
      code: body.code || "DEV_BRIDGE_ERROR",
      source: "dev-bridge",
      operation: path,
      detail: body.detail || null,
    });
  }
  return body;
}

async function invokeWorkflowCommand(command, args) {
  try {
    return await invokeCommand(command, args);
  } catch (error) {
    throw normalizeWorkflowError(error, {
      code: "TAURI_INVOKE_ERROR",
      source: "tauri",
      operation: command,
    });
  }
}

export function __testNormalizeWorkflowError(error, defaults = {}) {
  return normalizeWorkflowError(error, defaults);
}

function normalizeWorkflowError(error, defaults = {}) {
  const baseError =
    error && typeof error === "object" ? error : new Error(String(error || "workflow error"));
  const message =
    String(
      baseError.message ||
        baseError.data?.message ||
        defaults.message ||
        "workflow error",
    ) || "workflow error";
  const normalized = new Error(message);
  normalized.name = baseError.name || "Error";
  normalized.code = String(
    baseError.code ||
      baseError.data?.code ||
      defaults.code ||
      "WORKFLOW_ERROR",
  );
  normalized.source = baseError.source || defaults.source || "workflow";
  normalized.operation = baseError.operation || defaults.operation || "";
  normalized.detail = baseError.detail || baseError.data?.detail || defaults.detail || null;
  normalized.data = baseError.data || defaults.data || null;
  normalized.cause = baseError;
  return normalized;
}

function applyListLimit(items, limit) {
  const normalizedItems = Array.isArray(items) ? items : [];
  const normalizedLimit = Number(limit);
  if (!Number.isFinite(normalizedLimit) || normalizedLimit < 0) {
    return normalizedItems;
  }
  return normalizedItems.slice(0, normalizedLimit);
}
