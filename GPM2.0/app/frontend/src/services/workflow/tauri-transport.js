import { beginPreviewContentOperation, finishPreviewContentOperation } from "../preview-content-events.js";
import {
  invokeCommand as defaultInvokeCommand,
  listenBackendEvent as defaultListenBackendEvent,
} from "../backend-api.js";
import { normalizeWorkflowError } from "./contracts.js";
import { createTauriAssemblyOperations } from "./tauri/assembly.js";
import { createTauriImportOperations } from "./tauri/imports.js";
import { createTauriViewStateOperations } from "./tauri/view-state.js";
import { createTauriWorkspaceOperations } from "./tauri/workspace.js";

export function createTauriTransport({
  invoke = defaultInvokeCommand,
  listen = defaultListenBackendEvent,
  getPackageMetadataFallback = () => ({}),
} = {}) {
  async function invokeNormalized(command, args, stateOrLocale) {
    const operation = beginPreviewContentOperation(command, args);
    try {
      const result = await invoke(command, args, stateOrLocale);
      finishPreviewContentOperation(operation, command, result, true);
      return result;
    } catch (error) {
      finishPreviewContentOperation(operation, command, null, false);
      throw normalizeWorkflowError(error, {
        code: "TAURI_INVOKE_ERROR",
        source: "tauri",
        operation: command,
      });
    }
  }

  const context = {
    invokeCommand: invokeNormalized,
    listenBackendEvent: listen,
    getPackageMetadataFallback,
  };

  return {
    requestImportCancel({ runId, stateOrLocale = "zh" }) {
      return invokeNormalized("request_import_cancel", { runId }, stateOrLocale);
    },
    previewProjectRefinementVersion({ workspaceRoot, projectId, tool, versionId, stateOrLocale = "zh" }) {
      return invokeNormalized("preview_project_refinement_version", { workspaceRoot, projectId, tool, versionId }, stateOrLocale);
    },
    getGrtProjectView({ workspaceRoot, projectId }) {
      return invokeNormalized("get_grt_project_view", { workspaceRoot, projectId });
    },
    writeFinalPathExportTextFile({ outputPath, text, stateOrLocale = "zh" }) {
      return invokeNormalized("write_final_path_export_text_file", { outputPath, text }, stateOrLocale);
    },
    writeFinalPathExportBinaryFile({ outputPath, bytesBase64, stateOrLocale = "zh" }) {
      return invokeNormalized(
        "write_final_path_export_binary_file",
        { outputPath, bytesBase64 },
        stateOrLocale,
      );
    },
    exportFinalPathFasta({
      workspaceRoot,
      projectId,
      chrName,
      finalPathEntry,
      outputPath,
      stateOrLocale = "zh",
    }) {
      return invokeNormalized(
        "export_final_path_fasta",
        { workspaceRoot, projectId, chrName, finalPathEntry, outputPath },
        stateOrLocale,
      );
    },
    exportProjectFinalPathFasta({
      workspaceRoot,
      projectId,
      finalPathByChr,
      outputPath,
      stateOrLocale = "zh",
    }) {
      return invokeNormalized(
        "export_project_final_path_fasta",
        { workspaceRoot, projectId, finalPathByChr, outputPath },
        stateOrLocale,
      );
    },
    exportFinalPathAgp({
      workspaceRoot,
      projectId,
      chrName,
      finalPathEntry,
      outputPath,
      stateOrLocale = "zh",
    }) {
      return invokeNormalized(
        "export_final_path_agp",
        { workspaceRoot, projectId, chrName, finalPathEntry, outputPath },
        stateOrLocale,
      );
    },
    exportProjectFinalPathAgp({
      workspaceRoot,
      projectId,
      finalPathByChr,
      outputPath,
      stateOrLocale = "zh",
    }) {
      return invokeNormalized(
        "export_project_final_path_agp",
        { workspaceRoot, projectId, finalPathByChr, outputPath },
        stateOrLocale,
      );
    },
    exportDegapJobs({ stateOrLocale = "zh", ...payload }) {
      return invokeNormalized("export_degap_jobs", payload, stateOrLocale);
    },
    exportManualRefinement({ workspaceRoot, projectId, outputPath, request, stateOrLocale = "zh" }) {
      return invokeNormalized(
        "export_manual_refinement",
        { workspaceRoot, projectId, outputPath, request },
        stateOrLocale,
      );
    },
    importManualRefinementResults({ workspaceRoot, projectId, zipPath, stateOrLocale = "zh" }) {
      return invokeNormalized(
        "import_manual_refinement_results",
        { workspaceRoot, projectId, zipPath },
        stateOrLocale,
      );
    },
    listManualRefinementResults({ workspaceRoot, projectId, stateOrLocale = "zh" }) {
      return invokeNormalized(
        "list_manual_refinement_results",
        { workspaceRoot, projectId },
        stateOrLocale,
      );
    },
    listManualRefinementExports({ workspaceRoot, projectId, stateOrLocale = "zh" }) {
      return invokeNormalized("list_manual_refinement_exports", { workspaceRoot, projectId }, stateOrLocale);
    },
    undoManualRefinementLocus({ workspaceRoot, projectId, locusId, expectedRevision, stateOrLocale = "zh" }) {
      return invokeNormalized(
        "undo_manual_refinement_locus",
        { workspaceRoot, projectId, locusId, expectedRevision },
        stateOrLocale,
      );
    },
    switchManualRefinementLocus({
      workspaceRoot,
      projectId,
      locusId,
      expectedRevision,
      resultSha256,
      tool,
      stateOrLocale = "zh",
    }) {
      return invokeNormalized(
        "switch_manual_refinement_locus",
        { workspaceRoot, projectId, locusId, expectedRevision, resultSha256, tool },
        stateOrLocale,
      );
    },
    ...createTauriImportOperations(context),
    ...createTauriWorkspaceOperations(context),
    ...createTauriAssemblyOperations(context),
    ...createTauriViewStateOperations(context),
  };
}
