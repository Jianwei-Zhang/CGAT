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
    try {
      return await invoke(command, args, stateOrLocale);
    } catch (error) {
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
    exportDegapJobs({ stateOrLocale = "zh", ...payload }) {
      return invokeNormalized("export_degap_jobs", payload, stateOrLocale);
    },
    ...createTauriImportOperations(context),
    ...createTauriWorkspaceOperations(context),
    ...createTauriAssemblyOperations(context),
    ...createTauriViewStateOperations(context),
  };
}
