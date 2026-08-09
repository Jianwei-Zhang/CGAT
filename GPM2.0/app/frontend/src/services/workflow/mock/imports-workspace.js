import { t } from "../../../ui/i18n/index.js";
import { applyListLimit, sleep } from "../contracts.js";

export function createMockWorkspaceOperations(mockStore) {
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
    grtRecipe: mockStore.grtRecipe,
    packageMetadata: mockStore.packageMetadata,
    references: mockStore.references,
    datasets: mockStore.datasets,
    existingProjects: mockStore.existingProjects,
  };
}

async function initializeProjectMock({
  workspaceRoot,
  projectName,
  phasedAssemblyEnabled = false,
}) {
  await sleep(240);
  const effectiveThreshold = Number(
    mockStore.packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
  );
  const projectId = mockStore.existingProjects.length + 1;
  const referenceGenomeId = Number(mockStore.references[0]?.referenceGenomeId || 1);
  const primaryDatasetId = Number(
    mockStore.datasets.find((dataset) => dataset.label === mockStore.grtRecipe.primaryDataset)?.datasetId
      || mockStore.datasets[0]?.datasetId
      || 1,
  );
  const supportDatasetIds = mockStore.grtRecipe.supportDatasets
    .map((name) => mockStore.datasets.find((dataset) => dataset.label === name)?.datasetId)
    .filter((datasetId) => Number(datasetId) > 0);
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
      isProcessed: true,
      autoPipelineDone: true,
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
    grtProjectView: buildMockGrtProjectView(),
  };
}

function buildMockGrtProjectView() {
  return {
    recipe: {
      workflow: mockStore.grtRecipe.workflow,
      schema_version: mockStore.grtRecipe.schemaVersion,
      final_path_schema_version: mockStore.grtRecipe.finalPathSchemaVersion,
      recipe_id: mockStore.grtRecipe.recipeId,
      primary_dataset: mockStore.grtRecipe.primaryDataset,
      support_datasets: [...mockStore.grtRecipe.supportDatasets],
      reads_qc_enabled: mockStore.grtRecipe.readsQcEnabled,
      donor_set_id: mockStore.grtRecipe.donorSetId,
      tel_donor_set_id: mockStore.grtRecipe.telDonorSetId,
    },
    final_path_by_chr: {},
    source_cards: [],
    verification: {
      chromosome_count: 0,
      segment_count: 0,
      q4_artifact_sha256: "",
    },
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

  return {
    importZipBundle: importZipBundleMock,
    importExtractedBundle: importExtractedBundleMock,
    importAddDatasetPackage: importAddDatasetPackageMock,
    importAddCtgPackage: importAddCtgPackageMock,
    validateWorkspaceIntegrity: validateWorkspaceIntegrityMock,
    deleteWorkspaceDirectory: deleteWorkspaceDirectoryMock,
    listProjectInitializerOptions: listProjectInitializerOptionsMock,
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
  };
}
