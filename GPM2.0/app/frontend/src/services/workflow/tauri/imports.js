import { t } from "../../../ui/i18n/index.js";

export function createTauriImportOperations({
  invokeCommand,
  listenBackendEvent,
  getPackageMetadataFallback,
}) {
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
        stageCode: String(payload.stage || ""),
        detail: String(payload.detail || ""),
        label: String(payload.label || fallback),
        text: String(payload.text || payload.label || fallback),
      };
      const progressIndex = Number(payload.progressIndex);
      const progressTotal = Number(payload.progressTotal);
      const phaseIndex = Number(payload.phaseIndex);
      const phaseTotal = Number(payload.phaseTotal);
      if (Number.isFinite(progressIndex) && progressIndex > 0) {
        stage.progressIndex = progressIndex;
      }
      if (Number.isFinite(progressTotal) && progressTotal > 0) {
        stage.progressTotal = progressTotal;
      }
      if (Number.isFinite(phaseIndex) && phaseIndex > 0) {
        stage.phaseIndex = phaseIndex;
      }
      if (Number.isFinite(phaseTotal) && phaseTotal > 0) {
        stage.phaseTotal = phaseTotal;
      }
      const pairwise = payload.pairwise;
      if (pairwise && typeof pairwise === "object") {
        stage.pairwise = {
          activeRun: String(pairwise.activeRun || ""),
          activePath: String(pairwise.activePath || ""),
          currentBytes: Number(pairwise.currentBytes) || 0,
          totalBytes: Number(pairwise.totalBytes) || 0,
          parsedRows: Number(pairwise.parsedRows) || 0,
          writtenHits: Number(pairwise.writtenHits) || 0,
          fileIndex: Number(pairwise.fileIndex) || 0,
          fileTotal: Number(pairwise.fileTotal) || 0,
          overallBytes: Number(pairwise.overallBytes) || 0,
          overallTotalBytes: Number(pairwise.overallTotalBytes) || 0,
        };
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

async function importZipBundleTauri({ zipPath, workspaceRoot, onStage, runId = "", importParallelism = "auto", stateOrLocale = "zh" }) {
  onStage?.(t(stateOrLocale, "importer.runtime.tauriImportZipStage"));
  const result = await withImportProgressListener(runId, onStage, () => invokeCommand("import_zip", {
    zipPath,
    workspaceRoot,
    runId,
    importParallelism,
  }, stateOrLocale));
  return {
    workspaceRoot: result.workspaceRoot || workspaceRoot,
    message: result.message || t(stateOrLocale, "importer.runtime.tauriImportZipDone"),
  };
}

async function importExtractedBundleTauri({ extractedPath, onStage, runId = "", importParallelism = "auto", stateOrLocale = "zh" }) {
  onStage?.(t(stateOrLocale, "importer.runtime.tauriImportExtractedStage"));
  const result = await withImportProgressListener(runId, onStage, () => invokeCommand("import_extracted", {
    extractedPath,
    runId,
    importParallelism,
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
    packageMetadata: result.packageMetadata || getPackageMetadataFallback(),
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
    packageMetadata: result.packageMetadata || getPackageMetadataFallback(),
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

  return {
    importZipBundle: importZipBundleTauri,
    importExtractedBundle: importExtractedBundleTauri,
    importAddDatasetPackage: importAddDatasetPackageTauri,
    importAddCtgPackage: importAddCtgPackageTauri,
  };
}
