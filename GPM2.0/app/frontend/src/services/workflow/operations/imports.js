import { workflowRuntime } from "../runtime.js";

const { isTauriRuntime, callDevBridge, mock, tauri } = workflowRuntime;
const {
  importZipBundle: importZipBundleMock,
  importExtractedBundle: importExtractedBundleMock,
  importAddDatasetPackage: importAddDatasetPackageMock,
  importAddCtgPackage: importAddCtgPackageMock,
} = mock;
const {
  importZipBundle: importZipBundleTauri,
  importExtractedBundle: importExtractedBundleTauri,
  importAddDatasetPackage: importAddDatasetPackageTauri,
  importAddCtgPackage: importAddCtgPackageTauri,
} = tauri;

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
      packageMetadata: response.packageMetadata || mock.getPackageMetadata(),
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

export async function requestImportCancel({ runId, stateOrLocale = "zh" }) {
  const normalizedRunId = String(runId || "").trim();
  if (!normalizedRunId) {
    return { cancelRequested: false };
  }
  if (!isTauriRuntime()) {
    return { runId: normalizedRunId, cancelRequested: true };
  }
  return tauri.requestImportCancel({ runId: normalizedRunId, stateOrLocale });
}
