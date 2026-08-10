import { applyListLimit } from "../contracts.js";

export function createTauriWorkspaceOperations({ invokeCommand }) {
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
    grtRecipe: result.grtRecipe || null,
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
    grtRecipe: result.grtRecipe || null,
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
  phasedAssemblyEnabled = false,
}) {
  const result = await invokeCommand("initialize_project", {
    request: {
      workspaceRoot,
      projectName,
      phasedAssemblyEnabled: Boolean(phasedAssemblyEnabled),
    },
  });
  return {
    projectId: result.projectId,
    projectName: result.projectName || projectName,
    chrAssignmentMinCoveragePercent:
      result.chrAssignmentMinCoveragePercent ?? 60,
    phasedAssemblyEnabled: Boolean(result.phasedAssemblyEnabled),
    supportDatasetIds: result.supportDatasetIds || [],
    grtProjectView: result.grtProjectView || null,
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
    request: {
      workspaceRoot,
      projectId,
      projectName,
      referenceGenomeId,
      primaryDatasetId,
      supportDatasetIds,
      chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled,
    },
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
  const result = await invokeCommand("list_project_chromosomes", {
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
  const result = await invokeCommand("list_new_sequences", {
    workspaceRoot,
    projectId,
    limit,
  });
  return {
    items: applyListLimit(result.items, limit),
  };
}

  return {
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
    setProjectAutoPipelineDone: setProjectAutoPipelineDoneTauri,
    requestAutoPipelineCancel: requestAutoPipelineCancelTauri,
    listProjectChromosomes: listProjectChromosomesTauri,
    listNewSequences: listNewSequencesTauri,
  };
}
