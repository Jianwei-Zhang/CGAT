import {
  deleteWorkspaceDirectory,
  importAddDatasetPackage,
  importExtractedBundle,
  importZipBundle,
  listProjectInitializerOptions,
  requestImportCancel,
  validateWorkspaceIntegrity,
} from "../../services/workflow-api.js";
import { flushAssemblyProjectState } from "./assembly-page.js";
import { defaultProjectName } from "../../services/project-session.js";
import { openProjectWorkspace as openWorkspace } from "../../services/project-session.js";
import { renderProjectsBody, projectLabels, syncProjectValidation } from "./projects-view.js";
import { renderWorkspacePage, bindWorkspacePage } from "./workspace-page.js";
import { switchProjectFromShell, closeProjectSession, buildEmptyAssemblyViewState, buildEmptyProjectExportState } from "../shell/session-switchers.js";
import { clearAssemblySessionCache } from "../shell/assembly-session-cache.js";
import { resetAssemblyPageSession } from "./assembly/page-session.js";
import { pickDirectoryPath, pickZipFilePath } from "../../services/backend-api.js";
import { formatDateTime, getMessages, t as i18nT } from "../i18n/index.js";

const WORKSPACE_HISTORY_KEY = "gpm_next:workspace_history";
const IMPORT_PROGRESS_BOTTOM_THRESHOLD_PX = 24;
const IMPORTER_STATUS_TOAST_AUTO_DISMISS_MS = 1000;
const IMPORTER_STATUS_TOAST_DISMISS = Symbol("importerStatusToastDismiss");
const DELETE_SELECTION_MODE_FAILED_HISTORY = "failed-history";
const DELETE_SELECTION_MODE_PROJECT = "project";
const PROJECT_MENU_BINDING = Symbol("projectMenuBinding");

export function renderImporterPage(state) {
  const importer = state.importer;
  const messages = getMessages(state, "importer");
  const importProgressOverlay = importer.inFlight && importer.importRunId
    ? renderImportProgressOverlay(importer, messages)
    : "";
  const statusToast = renderImporterStatusToast(importer, messages);
  const recentRecords = readWorkspaceHistory();
  const workspaceContextMenu = importer.workspaceContextMenu || {};
  const deleteTargets = normalizePathList(importer.deleteTargets);
  const deleteFailedHistoryOnly = importer.deleteSelectionMode === DELETE_SELECTION_MODE_FAILED_HISTORY;
  return `
    <section class="page projects-page">
      ${renderProjectsBody(state, { records: recentRecords, messages, formatTime, renderAddPackageHint,
        summaryHtml: state.session?.workspacePath ? renderWorkspacePage(state) : "" })}
      ${statusToast}
      ${
        importer.deleteConfirmOpen
          ? `
            <div class="modal-overlay" data-modal-close="true">
              <article class="card modal-dialog" role="dialog" aria-modal="true" aria-label="${escapeAttr(
                deleteFailedHistoryOnly ? messages.page.deleteFailedConfirmTitle : messages.page.deleteConfirmTitle,
              )}" data-modal-dialog="true">
                <h4>${deleteFailedHistoryOnly ? messages.page.deleteFailedConfirmTitle : messages.page.deleteConfirmTitle}</h4>
                <p>${deleteFailedHistoryOnly
                  ? escapeHtml(i18nT(state, "importer.page.deleteFailedConfirmMessage", { count: deleteTargets.length }))
                  : messages.page.deleteConfirmMessage}</p>
                <div class="list">
                  ${deleteTargets
                    .map((path) => `<div class="list-item">${escapeHtml(path)}</div>`)
                    .join("")}
                </div>
                <label class="checkbox-item">
                  <input id="delete-with-files-checkbox" type="checkbox" ${importer.deleteWithFiles ? "checked" : ""} />
                  ${messages.page.deleteWithFiles}
                </label>
                <div class="inline-input">
                  <button id="confirm-delete-selected-button" class="button">${
                    deleteFailedHistoryOnly ? messages.buttons.confirmDeleteFailed : messages.buttons.confirmDelete
                  }</button>
                  <button id="cancel-delete-selected-button" class="button ghost">${messages.buttons.cancel}</button>
                </div>
              </article>
            </div>
          `
          : ""
      }

      ${importProgressOverlay}
      ${workspaceContextMenu.open ? renderWorkspaceHistoryContextMenu(workspaceContextMenu, messages) : ""}
    </section>
  `;
}

export function bindImporterPage(host, store) {
  host[PROJECT_MENU_BINDING]?.();
  const dismissMenus = event => {
    host.querySelectorAll("details.project-row-menu[open]").forEach(menu => {
      if (event.type === "keydown" && event.key !== "Escape") return;
      if (event.type === "pointerdown" && menu.contains(event.target)) return;
      menu.open = false;
      if (event.type === "keydown") menu.querySelector("summary")?.focus();
    });
  };
  host.addEventListener?.("pointerdown", dismissMenus);
  host.addEventListener?.("keydown", dismissMenus);
  host[PROJECT_MENU_BINDING] = () => {
    host.removeEventListener?.("pointerdown", dismissMenus);
    host.removeEventListener?.("keydown", dismissMenus);
  };
  host.querySelectorAll("details.project-row-menu").forEach(menu => {
    menu.addEventListener("toggle", () => {
      if (!menu.open) return;
      host.querySelectorAll("details.project-row-menu[open]").forEach(other => {
        if (other !== menu) other.open = false;
      });
    });
  });
  if (store.getState().initializer) bindWorkspacePage(host, store);
  bindProjectEntryControls(host, store);
  const zipPathInput = host.querySelector("#zip-path-input");
  const zipWorkspaceRootInput = host.querySelector("#zip-workspace-root-input");
  const extractedPathInput = host.querySelector("#extracted-path-input");
  const openWorkspacePathInput = host.querySelector("#open-workspace-path-input");
  const pickZipButton = host.querySelector("#pick-zip-button");
  const pickZipWorkspaceButton = host.querySelector("#pick-zip-workspace-button");
  const pickExtractedButton = host.querySelector("#pick-extracted-button");
  const pickOpenWorkspaceButton = host.querySelector("#pick-open-workspace-button");
  const importZipStartButton = host.querySelector("#import-zip-start-button");
  const importExtractedStartButton = host.querySelector("#import-extracted-start-button");
  const openWorkspaceButton = host.querySelector("#open-workspace-button");
  const validateHistoryButton = host.querySelector("#validate-history-button");
  const deleteFailedHistoryButton = host.querySelector("#delete-failed-history-button");
  const confirmDeleteSelectedButton = host.querySelector("#confirm-delete-selected-button");
  const cancelDeleteSelectedButton = host.querySelector("#cancel-delete-selected-button");
  const deleteWithFilesCheckbox = host.querySelector("#delete-with-files-checkbox");
  const modalOverlay = host.querySelector("[data-modal-close='true']");
  const modalDialog = host.querySelector("[data-modal-dialog='true']");
  const cancelImportButtons = host.querySelectorAll("[data-import-cancel]");
  const importProgressList = host.querySelector("[data-import-progress-list='1']");
  const recentPickButtons = host.querySelectorAll("[data-recent-index]");
  const workspaceHistoryRows = host.querySelectorAll("[data-workspace-history-row-path]");
  const historyDeleteButtons = host.querySelectorAll("[data-delete-history-path]");
  const workspaceContextMenu = host.querySelector("[data-workspace-history-context-menu='1']");
  const importAddPackageMenuButtons = host.querySelectorAll("[data-workspace-import-add-package-path]");

  host.querySelector("details.importer-import-progress-log")?.addEventListener("toggle", event => {
    updateImporterState(store, { progressDetailsOpen: event.target.open });
  });
  bindImportProgressScroll(importProgressList, store);
  bindImporterStatusToastDismiss(host, store);

  zipPathInput?.addEventListener("input", (event) => {
    updateImporterState(store, {
      zipPath: event.target.value.trim(),
    });
  });

  zipWorkspaceRootInput?.addEventListener("input", (event) => {
    updateImporterState(store, {
      workspaceRoot: event.target.value.trim(),
    });
  });

  extractedPathInput?.addEventListener("input", (event) => {
    updateImporterState(store, {
      extractedPath: event.target.value.trim(),
    });
  });

  openWorkspacePathInput?.addEventListener("input", (event) => {
    updateImporterState(store, {
      openWorkspacePath: event.target.value.trim(),
    });
  });

  pickZipButton?.addEventListener("click", async () => {
    const selectedPath = await pickZipFilePath(store.getState());
    if (!selectedPath) {
      return;
    }
    updateImporterState(store, { zipPath: selectedPath });
    rerender(host, store);
  });

  pickZipWorkspaceButton?.addEventListener("click", async () => {
    const selectedPath = await pickDirectoryPath(store.getState());
    if (!selectedPath) {
      return;
    }
    updateImporterState(store, { workspaceRoot: selectedPath });
    rerender(host, store);
  });

  pickExtractedButton?.addEventListener("click", async () => {
    const selectedPath = await pickDirectoryPath(store.getState());
    if (!selectedPath) {
      return;
    }
    updateImporterState(store, { extractedPath: selectedPath });
    rerender(host, store);
  });

  pickOpenWorkspaceButton?.addEventListener("click", async () => {
    const selectedPath = await pickDirectoryPath(store.getState());
    if (!selectedPath) {
      return;
    }
    updateImporterState(store, { openWorkspacePath: selectedPath });
    rerender(host, store);
  });

  importZipStartButton?.addEventListener("click", async (event) => {
    event.preventDefault?.();
    await runImportZipFlow(host, store);
  });

  importExtractedStartButton?.addEventListener("click", async (event) => {
    event.preventDefault?.();
    await runImportExtractedFlow(host, store);
  });

  openWorkspaceButton?.addEventListener("click", async () => {
    await runOpenWorkspaceFlow(host, store);
  });

  validateHistoryButton?.addEventListener("click", async () => {
    await runValidateHistoryFlow(host, store);
  });

  deleteFailedHistoryButton?.addEventListener("click", () => {
    const snapshot = store.getState();
    if (snapshot.importer.inFlight || snapshot.importer.historyValidating || snapshot.initializer?.autoPipelineRunning) return;
    const failedPaths = getFailedHistoryPaths(
      readWorkspaceHistory(),
      snapshot.importer.historyValidation,
      snapshot.importer.historyValidatedPaths,
    );
    openDeleteSelectionConfirm(host, store, failedPaths, DELETE_SELECTION_MODE_FAILED_HISTORY);
  });

  confirmDeleteSelectedButton?.addEventListener("click", async () => {
    await runDeleteSelectedFlow(host, store);
  });

  cancelDeleteSelectedButton?.addEventListener("click", () => {
    updateImporterState(store, {
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
    });
    rerender(host, store);
  });

  modalOverlay?.addEventListener("click", () => {
    updateImporterState(store, {
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
    });
    rerender(host, store);
  });

  modalDialog?.addEventListener("click", (event) => {
    event.stopPropagation();
  });

  deleteWithFilesCheckbox?.addEventListener("change", (event) => {
    updateImporterState(store, {
      deleteWithFiles: event.target.checked,
    });
  });

  cancelImportButtons.forEach((button) => {
    button.addEventListener("pointerdown", async (event) => {
      if (event.isPrimary === false || Number(event.button) !== 0) {
        return;
      }
      await cancelCurrentImport(host, store);
    });
    button.addEventListener("click", async () => {
      await cancelCurrentImport(host, store);
    });
  });

  recentPickButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const state = store.getState();
      if (state.importer.inFlight || state.initializer?.autoPipelineRunning || state.initializer?.updating) return;
      const workspacePath = String(button.dataset.recentPath || "").trim();
      if (!workspacePath) {
        return;
      }
      if (state.session.projectId && workspacePathListIncludes([state.session.workspacePath], workspacePath)) return;
      await runOpenWorkspaceFlow(host, store, workspacePath);
    });
    button.addEventListener("contextmenu", (event) => {
      event.preventDefault?.();
      const workspacePath = String(button.dataset.recentPath || "").trim();
      if (!workspacePath) {
        return;
      }
      const x = Number.isFinite(Number(event.clientX)) ? Number(event.clientX) : 0;
      const y = Number.isFinite(Number(event.clientY)) ? Number(event.clientY) : 0;
      updateImporterState(store, {
        workspaceContextMenu: {
          open: true,
          workspacePath,
          x,
          y,
        },
      });
      rerender(host, store);
    });
  });

  workspaceHistoryRows.forEach((row) => {
    row.addEventListener("pointerenter", () => {
      const workspacePath = String(row.dataset.workspaceHistoryRowPath || "").trim();
      cancelWorkspaceContextMenuClose(workspacePath, store);
    });
    row.addEventListener("pointerleave", () => {
      const workspacePath = String(row.dataset.workspaceHistoryRowPath || "").trim();
      scheduleWorkspaceContextMenuClose(host, store, workspacePath);
    });
  });

  historyDeleteButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const workspacePath = String(button.dataset.deleteHistoryPath || "").trim();
      if (!workspacePath) {
        return;
      }
      openDeleteSelectionConfirm(host, store, [workspacePath]);
    });
  });

  workspaceContextMenu?.addEventListener("click", (event) => {
    event.stopPropagation?.();
  });
  workspaceContextMenu?.addEventListener("pointerenter", () => {
    cancelWorkspaceContextMenuClose(workspaceContextMenu.dataset.workspaceHistoryContextMenuPath || "", store);
  });
  workspaceContextMenu?.addEventListener("pointerleave", () => {
    scheduleWorkspaceContextMenuClose(
      host,
      store,
      workspaceContextMenu.dataset.workspaceHistoryContextMenuPath || "",
    );
  });

  importAddPackageMenuButtons.forEach((importAddPackageMenuButton) => importAddPackageMenuButton.addEventListener("click", async (event) => {
    event.stopPropagation?.();
    const workspacePath = String(importAddPackageMenuButton.dataset.workspaceImportAddPackagePath || "").trim();
    closeWorkspaceContextMenu(host, store, workspacePath);
    await runImportAddPackageFlow(host, store, workspacePath);
  }));
}

function bindProjectEntryControls(host, store) {
  const busy = () => store.getState().importer.inFlight || store.getState().initializer?.autoPipelineRunning;
  const openDirectory = async (oldPath = "") => {
    if (busy()) return;
    const path = await pickDirectoryPath(store.getState());
    if (!path) return;
    const opened = await runOpenWorkspaceFlow(host, store, path);
    if (opened && oldPath && oldPath !== path) {
      removeWorkspaceHistoryPaths([oldPath]);
      rerender(host, store);
    }
  };
  host.querySelector("#project-import-button")?.addEventListener("click", () => {
    if (busy()) return;
    updateImporterState(store, { importDialogOpen: true, projectError: "", pendingProjectPath: "" });
    rerender(host, store);
    host.querySelector("#zip-path-input, #extracted-path-input")?.focus();
  });
  host.querySelector("#project-open-button")?.addEventListener("click", () => openDirectory());
  host.querySelectorAll("[data-project-relocate]").forEach(button => button.addEventListener("click", () => openDirectory(button.dataset.projectRelocate)));
  const closeImport = () => {
    if (busy()) return;
    updateImporterState(store, { importDialogOpen: false });
    rerender(host, store);
    host.querySelector("#project-import-button")?.focus();
  };
  host.querySelector("[data-project-import-close]")?.addEventListener("click", closeImport);
  host.querySelector("[data-project-import-overlay]")?.addEventListener("click", event => {
    if (event.target === event.currentTarget) closeImport();
  });
  const dialog = host.querySelector(".project-import-dialog");
  dialog?.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault?.(); closeImport(); }
    if (event.key === "Tab") {
      const controls = [...dialog.querySelectorAll("input,button")].filter(node => !node.disabled);
      const next = event.shiftKey ? controls.at(-1) : controls[0];
      if (event.target === (event.shiftKey ? controls[0] : controls.at(-1))) {
        event.preventDefault?.(); next?.focus();
      }
    }
  });
  dialog?.addEventListener("input", () => {
    const extracted = store.getState().importer.importSource === "extracted";
    const source = host.querySelector(extracted ? "#extracted-path-input" : "#zip-path-input")?.value.trim();
    const directory = extracted ? source : host.querySelector("#zip-workspace-root-input")?.value.trim();
    dialog.querySelector('[type="submit"]').disabled = !source || !directory;
    dialog.querySelector("#import-project-name").placeholder = directory ? defaultProjectName(directory) : projectLabels(store.getState()).nameDefault;
  });
  host.querySelectorAll('[name="project-source"]').forEach(input => input.addEventListener("change", () => {
    updateImporterState(store, { importSource: input.value, projectError: "" });
    rerender(host, store);
    host.querySelector(`[name="project-source"][value="${input.value}"]`)?.focus();
  }));
  host.querySelector("#import-project-name")?.addEventListener("input", event => {
    updateImporterState(store, { projectNameInput: event.target.value });
  });
  host.querySelector("#project-retry-button")?.addEventListener("click", async () => {
    if (busy()) return;
    await runOpenWorkspaceFlow(host, store, store.getState().importer.pendingProjectPath);
  });
  host.querySelector("#legacy-project-select")?.addEventListener("change", async event => {
    if (busy() || !event.target.value) return;
    const projectId = Number(event.target.value);
    updateImporterState(store, { inFlight: true, projectError: "" });
    try {
      await flushAssemblyProjectState(host, store);
      switchProjectFromShell(store, projectId);
    } catch (error) {
      updateImporterState(store, { projectError: String(error.message || error) });
    } finally {
      updateImporterState(store, { inFlight: false });
      rerender(host, store);
    }
  });
  host.querySelectorAll("[data-project-delete-files]").forEach(button => button.addEventListener("click", () => {
    if (busy()) return;
    openDeleteSelectionConfirm(host, store, [button.dataset.projectDeleteFiles], DELETE_SELECTION_MODE_PROJECT);
    updateImporterState(store, { deleteWithFiles: true });
    rerender(host, store);
  }));
}

async function runImportZipFlow(host, store) {
  const snapshot = store.getState();
  const importer = snapshot.importer;
  if (!importer.zipPath || !importer.workspaceRoot) {
    updateImporterState(store, {
      status: i18nT(snapshot, "importer.runtime.incompleteParamsStatus"),
      summary: i18nT(snapshot, "importer.runtime.incompleteZipSummary"),
    });
    rerender(host, store);
    return;
  }

  if (importer.inFlight) return;
  const runId = createImportRunId("zip");
  updateImporterState(store, {
    inFlight: true,
    importRunId: runId,
    importCancelling: false,
    importCancelError: "",
    importProgressAutoScroll: true,
    importProgressScrollTop: 0,
    status: i18nT(snapshot, "importer.runtime.importInProgressStatus"),
    summary: i18nT(snapshot, "importer.runtime.importZipSummary"),
    stages: [
      i18nT(snapshot, "importer.runtime.zipStageValidatePath"),
      i18nT(snapshot, "importer.runtime.zipStageValidateWorkspace"),
    ],
  });
  rerender(host, store);

  let importOperationCompleted = false;
  try {
    const result = await importZipBundle({
      zipPath: importer.zipPath,
      workspaceRoot: importer.workspaceRoot,
      runId,
      stateOrLocale: snapshot,
      onStage: (stageText) => {
        if (String(store.getState().importer.importRunId || "") !== runId) {
          return;
        }
        const current = store.getState().importer;
        updateImporterState(store, {
          stages: [...current.stages, stageText],
        });
        rerender(host, store);
      },
    });
    importOperationCompleted = true;
    updateImporterState(store, { pendingProjectPath: result.workspaceRoot });
    if (String(store.getState().importer.importRunId || "") !== runId) {
      return;
    }
    await enterWorkspaceAfterImport(store, {
      workspaceRoot: result.workspaceRoot,
      importerStatus: i18nT(snapshot, "importer.runtime.importDoneStatus"),
      importerSummary: result.message,
      appendStage: i18nT(snapshot, "importer.runtime.importZipDoneStage"),
    });
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  } catch (error) {
    if (String(store.getState().importer.importRunId || "") !== runId) {
      return;
    }
    updateImporterState(
      store,
      buildImportCompletionErrorPatch(
        error,
        snapshot,
        store.getState().importer,
        importOperationCompleted,
      ),
    );
  }

  rerender(host, store);
}

async function runImportExtractedFlow(host, store) {
  const snapshot = store.getState();
  const importer = snapshot.importer;
  if (!importer.extractedPath) {
    updateImporterState(store, {
      status: i18nT(snapshot, "importer.runtime.incompleteParamsStatus"),
      summary: i18nT(snapshot, "importer.runtime.incompleteExtractedSummary"),
    });
    rerender(host, store);
    return;
  }

  if (importer.inFlight) return;
  const runId = createImportRunId("extracted");
  updateImporterState(store, {
    inFlight: true,
    importRunId: runId,
    importCancelling: false,
    importCancelError: "",
    importProgressAutoScroll: true,
    importProgressScrollTop: 0,
    status: i18nT(snapshot, "importer.runtime.importInProgressStatus"),
    summary: i18nT(snapshot, "importer.runtime.importExtractedSummary"),
    stages: [i18nT(snapshot, "importer.runtime.extractedStageValidate"), `extract_path=${importer.extractedPath}`],
  });
  rerender(host, store);

  let importOperationCompleted = false;
  try {
    const result = await importExtractedBundle({
      extractedPath: importer.extractedPath,
      runId,
      stateOrLocale: snapshot,
      onStage: (stageText) => {
        if (String(store.getState().importer.importRunId || "") !== runId) {
          return;
        }
        const current = store.getState().importer;
        updateImporterState(store, {
          stages: [...current.stages, stageText],
        });
        rerender(host, store);
      },
    });
    importOperationCompleted = true;
    updateImporterState(store, { pendingProjectPath: result.workspaceRoot });
    if (String(store.getState().importer.importRunId || "") !== runId) {
      return;
    }
    await enterWorkspaceAfterImport(store, {
      workspaceRoot: result.workspaceRoot,
      importerStatus: i18nT(snapshot, "importer.runtime.importDoneStatus"),
      importerSummary: result.message,
      appendStage: i18nT(snapshot, "importer.runtime.importExtractedDoneStage"),
    });
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  } catch (error) {
    if (String(store.getState().importer.importRunId || "") !== runId) {
      return;
    }
    updateImporterState(
      store,
      buildImportCompletionErrorPatch(
        error,
        snapshot,
        store.getState().importer,
        importOperationCompleted,
      ),
    );
  }

  rerender(host, store);
}

async function runImportAddPackageFlow(host, store, workspaceRoot) {
  const snapshot = store.getState();
  const normalizedWorkspaceRoot = String(workspaceRoot || "").trim();
  if (!normalizedWorkspaceRoot) {
    updateImporterState(store, {
      workspaceContextMenu: null,
      status: i18nT(snapshot, "importer.runtime.incompleteParamsStatus"),
      summary: i18nT(snapshot, "importer.runtime.incompleteAddPackageWorkspaceSummary"),
    });
    rerender(host, store);
    return;
  }

  const zipPath = await pickZipFilePath(snapshot);
  if (!zipPath) {
    updateImporterState(store, { workspaceContextMenu: null });
    rerender(host, store);
    return;
  }

  const runId = createImportRunId("add-package");
  updateImporterState(store, {
    workspaceContextMenu: null,
    inFlight: true,
    importRunId: runId,
    importCancelling: false,
    importCancelError: "",
    importProgressAutoScroll: true,
    importProgressScrollTop: 0,
    workspaceRoot: normalizedWorkspaceRoot,
    openWorkspacePath: normalizedWorkspaceRoot,
    status: i18nT(snapshot, "importer.runtime.importInProgressStatus"),
    summary: i18nT(snapshot, "importer.runtime.importAddPackageSummary"),
    stages: [`workspace_root=${normalizedWorkspaceRoot}`, `add_zip_path=${zipPath}`],
  });
  rerender(host, store);

  let importOperationCompleted = false;
  try {
    const result = await importAddDatasetPackage({
      workspaceRoot: normalizedWorkspaceRoot,
      zipPath,
      runId,
      stateOrLocale: snapshot,
      onStage: (stageText) => {
        if (String(store.getState().importer.importRunId || "") !== runId) {
          return;
        }
        const current = store.getState().importer;
        updateImporterState(store, {
          stages: [...current.stages, stageText],
        });
        rerender(host, store);
      },
    });
    importOperationCompleted = true;
    updateImporterState(store, { pendingProjectPath: result.workspaceRoot });
    if (String(store.getState().importer.importRunId || "") !== runId) {
      return;
    }
    updateImporterState(store, { pendingProjectPath: "" });
    applyAddPackageImportedState(store, {
      workspaceRoot: result.workspaceRoot || normalizedWorkspaceRoot,
      packageMetadata: result.packageMetadata,
      references: result.references,
      datasets: result.datasets,
      existingProjects: result.existingProjects,
      datasetName: result.datasetName || "",
      importerSummary: result.message,
      appendStage: i18nT(snapshot, "importer.runtime.importAddPackageDoneStage"),
    });
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  } catch (error) {
    if (String(store.getState().importer.importRunId || "") !== runId) {
      return;
    }
    updateImporterState(
      store,
      buildImportCompletionErrorPatch(
        error,
        snapshot,
        store.getState().importer,
        importOperationCompleted,
      ),
    );
  }

  rerender(host, store);
}

async function runOpenWorkspaceFlow(host, store, forcedWorkspacePath = "") {
  const snapshot = store.getState();
  const importer = snapshot.importer;
  if (importer.inFlight || snapshot.initializer?.autoPipelineRunning || snapshot.initializer?.updating) return false;
  const workspaceRoot = String(forcedWorkspacePath || importer.openWorkspacePath || "").trim();
  if (!workspaceRoot) {
    updateImporterState(store, {
      status: i18nT(snapshot, "importer.runtime.incompleteParamsStatus"),
      summary: i18nT(snapshot, "importer.runtime.incompleteOpenSummary"),
    });
    rerender(host, store);
    return;
  }

  updateImporterState(store, {
    inFlight: true,
    projectError: "",
    importRunId: null,
    importCancelling: false,
    importCancelError: "",
    status: i18nT(snapshot, "importer.runtime.openInProgressStatus"),
    summary: i18nT(snapshot, "importer.runtime.openSummary"),
    openWorkspacePath: workspaceRoot,
    stages: [i18nT(snapshot, "importer.runtime.openStageValidateWorkspace"), `workspace_root=${workspaceRoot}`],
  });
  if (!syncProjectSelection(host, store, { openingPath: workspaceRoot })) rerender(host, store);

  try {
    await flushAssemblyProjectState(host, store);
    const options = await openWorkspace({ workspaceRoot, projectName: importer.pendingProjectPath === workspaceRoot ? importer.projectNameInput : "" });
    const defaultReferenceId = options.references[0]?.referenceGenomeId || "";
    const defaultPrimaryDatasetId = options.datasets[0]?.datasetId || "";
    applyWorkspaceLoadedState(store, {
      workspaceRoot,
      packageMetadata: options.packageMetadata,
      grtRecipe: options.grtRecipe,
      references: options.references,
      datasets: options.datasets,
      existingProjects: options.existingProjects,
      defaultReferenceId,
      defaultPrimaryDatasetId,
      importerStatus: i18nT(snapshot, "importer.runtime.workspaceLoadedStatus"),
      importerSummary: i18nT(snapshot, "importer.runtime.workspaceLoadedSummary"),
      appendStage: i18nT(snapshot, "importer.runtime.workspaceLoadedStage"),
    });
    if (!syncProjectSelection(host, store, { replaceDetail: true })) rerender(host, store);
    return true;
  } catch (error) {
    updateImporterState(store, {
      projectError: String(error.message || error),
      pendingProjectPath: error.pendingProjectPath || "",
      historyValidation: { ...store.getState().importer.historyValidation, [workspaceRoot]: { ok: false, message: String(error.message || error) } },
      historyValidatedPaths: (store.getState().importer.historyValidatedPaths || []).filter(path => path !== workspaceRoot),
      inFlight: false,
      importRunId: null,
      importCancelling: false,
      importCancelError: "",
      status: i18nT(snapshot, "importer.runtime.openFailedStatus"),
      summary: String(error.message || error),
    });
  }

  if (store.getState().importer.pendingProjectPath || !syncProjectSelection(host, store)) rerender(host, store);
}

// Keep the project library mounted while opening a project; replace only the detail after success.
function syncProjectSelection(host, store, { openingPath = "", replaceDetail = false } = {}) {
  const state = store.getState();
  if (state.activeRoute !== "importer") return false;
  const routeHost = host.closest("#route-host") || host;
  const detail = routeHost.querySelector(".project-current, .project-no-selection");
  const list = routeHost.querySelector(".project-recent-list");
  const rows = [...routeHost.querySelectorAll("[data-workspace-history-row-path]")];
  const records = readWorkspaceHistory();
  const rowByPath = new Map(rows.map(row => [row.dataset.workspaceHistoryRowPath, row]));
  if (!detail || !list || rows.length !== records.length || records.some(record => !rowByPath.has(record.path))) return false;
  const labels = projectLabels(state);
  records.forEach((record, index) => {
    const row = rowByPath.get(record.path);
    const active = workspacePathListIncludes([state.session.workspacePath], record.path);
    const opening = record.path === openingPath;
    row.classList.toggle("is-active", active);
    const button = row.querySelector("[data-recent-path]");
    button.disabled = opening;
    button.setAttribute("aria-current", String(active));
    button.setAttribute("aria-busy", String(opening));
    button.dataset.recentIndex = String(index);
    const name = row.querySelector(".project-recent-name strong");
    const projectName = (active && state.session.projectName) || record.projectName || defaultProjectName(record.path);
    if (name.textContent !== projectName) name.textContent = projectName;
    const status = row.querySelector(".project-open-status");
    status.hidden = !active && !opening;
    status.textContent = opening ? labels.loading : labels.opened;
    const time = row.querySelector(".project-recent-time time");
    const formattedTime = formatTime(record.lastUsedAt, state.locale);
    if (time.textContent !== formattedTime) time.textContent = formattedTime;
    if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
  });
  if (!state.importer.projectError) routeHost.querySelector("[data-project-page-error]")?.remove();
  if (!state.importer.pendingProjectPath) routeHost.querySelector(".project-pending")?.remove();
  if (replaceDetail) {
    detail.outerHTML = renderWorkspacePage(state);
    const nextDetail = routeHost.querySelector(".project-current");
    bindWorkspacePage(nextDetail, store);
    bindProjectEntryControls(nextDetail, store);
  }
  syncProjectValidation(routeHost, state, records);
  syncImporterStatusToast(routeHost, store);
  syncSessionHeader(store);
  return true;
}

async function runValidateHistoryFlow(host, store) {
  const snapshot = store.getState();
  if (snapshot.importer.inFlight || snapshot.importer.historyValidating || snapshot.initializer?.autoPipelineRunning) return;
  const historyRecords = readWorkspaceHistory();
  const workspacePaths = historyRecords.map((item) => item.path);
  if (workspacePaths.length === 0) return;

  updateImporterState(store, { historyValidating: true });
  syncProjectValidation(host, store.getState(), historyRecords);

  const historyValidation = {};
  for (const workspaceRoot of workspacePaths) {
    try {
      const result = await validateWorkspaceIntegrity({ workspaceRoot });
      if (result.ok) {
        historyValidation[workspaceRoot] = {
          ok: true,
          message: "",
        };
      } else {
        const missing = Array.isArray(result.missing) ? result.missing.join(", ") : i18nT(store.getState(), "importer.runtime.unknownMissing");
        historyValidation[workspaceRoot] = {
          ok: false,
          message: missing,
        };
      }
    } catch (error) {
      const message = String(error.message || error);
      historyValidation[workspaceRoot] = {
        ok: false,
        message,
      };
    }
  }

  const currentRecords = readWorkspaceHistory();
  const previousValidation = store.getState().importer.historyValidation || {};
  updateImporterState(store, {
    historyValidating: false,
    historyValidatedPaths: currentRecords.filter(record => historyValidation[record.path]).map(record => record.path),
    historyValidation: Object.fromEntries(currentRecords
      .filter(record => historyValidation[record.path] || previousValidation[record.path])
      .map(record => [record.path, historyValidation[record.path] || previousValidation[record.path]])),
  });
  syncProjectValidation(host, store.getState(), currentRecords);
  const results = currentRecords.map(record => historyValidation[record.path]).filter(Boolean);
  const failCount = results.filter(result => result.ok === false).length;
  updateImporterState(store, {
    status: i18nT(store.getState(), failCount ? "importer.runtime.validateDoneStatus" : "importer.runtime.validateOkStatus"),
    summary: i18nT(store.getState(), "importer.runtime.validateDoneSummary", { okCount: results.length - failCount, failCount }),
  });
  syncImporterStatusToast(host, store);
}

function openDeleteSelectionConfirm(host, store, deleteTargets, deleteSelectionMode = "") {
  const selectedPaths = normalizePathList(deleteTargets);
  if (selectedPaths.length === 0) {
    updateImporterState(store, {
      status: i18nT(store.getState(), "importer.runtime.notSelectedStatus"),
      summary: i18nT(store.getState(), "importer.runtime.notSelectedSummary"),
    });
    rerender(host, store);
    return;
  }
  updateImporterState(store, {
    deleteConfirmOpen: true,
    deleteSelectionMode,
    deleteWithFiles: false,
    deleteTargets: selectedPaths,
    status: i18nT(store.getState(), "importer.runtime.deleteConfirmStatus"),
    summary: i18nT(store.getState(), "importer.runtime.deleteConfirmSummary", {
      count: selectedPaths.length,
    }),
  });
  rerender(host, store);
}

async function runDeleteSelectedFlow(host, store) {
  const snapshot = store.getState();
  const importer = snapshot.importer;
  const deleteFailedHistoryOnly = importer.deleteSelectionMode === DELETE_SELECTION_MODE_FAILED_HISTORY;
  const deleteProjectRecord = importer.deleteSelectionMode === DELETE_SELECTION_MODE_PROJECT;
  const requestedPaths = normalizePathList(importer.deleteTargets);
  const failedHistoryPaths = deleteFailedHistoryOnly
    ? new Set(getFailedHistoryPaths(readWorkspaceHistory(), importer.historyValidation, importer.historyValidatedPaths))
    : null;
  const selectedPaths = failedHistoryPaths
    ? requestedPaths.filter((path) => failedHistoryPaths.has(path))
    : requestedPaths;
  if (importer.inFlight) return;
  const deleteWithFiles = importer.deleteWithFiles === true;
  if (selectedPaths.length === 0) {
    updateImporterState(store, {
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
      status: i18nT(snapshot, "importer.runtime.notSelectedStatus"),
      summary: i18nT(snapshot, "importer.runtime.notSelectedSummary"),
    });
    rerender(host, store);
    return;
  }

  updateImporterState(store, {
    inFlight: true,
    status: i18nT(snapshot, "importer.runtime.deleteInProgressStatus"),
    summary: deleteWithFiles
      ? i18nT(snapshot, "importer.runtime.deleteWithFilesSummary")
      : i18nT(snapshot, deleteFailedHistoryOnly
        ? "importer.runtime.deleteFailedHistorySummary"
        : "importer.runtime.deleteHistorySummary"),
    stages: [],
  });
  rerender(host, store);

  const stages = [];
  let deletedDirCount = 0;
  const removedPaths = [];
  const failures = [];
  if (deleteWithFiles) {
    for (const workspaceRoot of selectedPaths) {
      try {
        const result = await deleteWorkspaceDirectory({ workspaceRoot });
        if (!result.deleted && result.reason !== "not_found") {
          throw new Error(result.reason || projectLabels(store.getState()).deleteFailed);
        }
        removedPaths.push(workspaceRoot);
        if (result.deleted) {
          deletedDirCount += 1;
          stages.push(i18nT(store.getState(), "importer.runtime.deleteDirRemovedStage", {
            workspaceRoot,
          }));
        } else {
          stages.push(i18nT(store.getState(), "importer.runtime.deleteDirMissingStage", {
            workspaceRoot,
          }));
        }
      } catch (error) {
        failures.push(`${workspaceRoot}: ${String(error.message || error)}`);
        stages.push(i18nT(store.getState(), "importer.runtime.deleteDirFailedStage", {
          workspaceRoot,
          message: String(error.message || error),
        }));
      }
    }
  }

  const completedPaths = deleteWithFiles ? removedPaths : selectedPaths;
  removeWorkspaceHistoryPaths(completedPaths);

  const nextSession = { ...store.getState().session };
  const closedWorkspacePaths = deleteProjectRecord ? completedPaths : removedPaths;
  if (workspacePathListIncludes(closedWorkspacePaths, nextSession.workspacePath)) {
    closeProjectSession(store);
    nextSession.workspacePath = "";
    nextSession.projectId = null;
    nextSession.projectName = "";
  }

  const currentImporter = store.getState().importer;
  const nextValidation = { ...(currentImporter.historyValidation || {}) };
  for (const path of selectedPaths) {
    if (completedPaths.includes(path)) delete nextValidation[path];
  }
  store.setState({
    session: nextSession,
    importer: {
      ...currentImporter,
      inFlight: false,
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
      historyValidation: nextValidation,
      openWorkspacePath: workspacePathListIncludes(closedWorkspacePaths, currentImporter.openWorkspacePath)
        ? ""
        : currentImporter.openWorkspacePath,
      projectError: failures.join("\n"),
      status: failures.length ? projectLabels(store.getState()).deleteFailed : i18nT(store.getState(), "importer.runtime.deleteDoneStatus"),
      summary: deleteWithFiles
        ? i18nT(store.getState(), "importer.runtime.deleteDoneWithFilesSummary", {
          count: completedPaths.length,
          deletedDirCount,
        })
        : i18nT(store.getState(), deleteFailedHistoryOnly
          ? "importer.runtime.deleteDoneFailedHistorySummary"
          : "importer.runtime.deleteDoneHistorySummary", {
          count: selectedPaths.length,
        }),
      stages,
    },
    activeRoute: "importer",
  });
  window.dispatchEvent(new Event("gpm-next:route-refresh"));
  rerender(host, store);
}

async function enterWorkspaceAfterImport(store, payload) {
  const { workspaceRoot, importerStatus, importerSummary, appendStage } = payload;
  await flushAssemblyProjectState(globalThis.document?.querySelector("#route-host"), store);
  updateImporterState(store, { stages: [...store.getState().importer.stages, projectLabels(store.getState()).pending] });
  const options = await openWorkspace({ workspaceRoot, projectName: store.getState().importer.projectNameInput });
  const defaultReferenceId = options.references[0]?.referenceGenomeId || "";
  const defaultPrimaryDatasetId = options.datasets[0]?.datasetId || "";
  applyWorkspaceLoadedState(store, {
    workspaceRoot,
    packageMetadata: options.packageMetadata,
    grtRecipe: options.grtRecipe,
    references: options.references,
    datasets: options.datasets,
    existingProjects: options.existingProjects,
    defaultReferenceId,
    defaultPrimaryDatasetId,
    importerStatus,
    importerSummary,
    appendStage,
  });
}

function applyWorkspaceLoadedState(store, payload) {
  const {
    workspaceRoot,
    packageMetadata,
    grtRecipe,
    references,
    datasets,
    existingProjects,
    defaultReferenceId,
    defaultPrimaryDatasetId,
    importerStatus,
    importerSummary,
    appendStage,
  } = payload;
  const current = store.getState();
  const selectedProject = existingProjects.length === 1 ? existingProjects[0] : null;
  resetAssemblyPageSession();
  clearAssemblySessionCache();
  store.setState({
    session: {
      ...current.session,
      workspacePath: workspaceRoot,
      projectName: selectedProject?.projectName || "",
      projectId: selectedProject?.projectId || null,
    },
    importer: {
      ...current.importer,
      inFlight: false,
      importRunId: null,
      importCancelling: false,
      importCancelError: "",
      workspaceRoot,
      openWorkspacePath: workspaceRoot,
      historyValidation: Object.fromEntries(Object.entries(current.importer.historyValidation || {}).filter(([path]) => path !== workspaceRoot)),
      historyValidatedPaths: (current.importer.historyValidatedPaths || []).filter(path => path !== workspaceRoot),
      importDialogOpen: false,
      pendingProjectPath: "",
      projectError: "",
      projectNameInput: "",
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
      status: importerStatus,
      summary: importerSummary,
      stages: appendStage ? [...current.importer.stages, appendStage] : [...current.importer.stages],
    },
    initializer: {
      ...current.initializer,
      optionsLoaded: true,
      optionsError: "",
      packageMetadata: packageMetadata || current.initializer.packageMetadata,
      grtRecipe: grtRecipe || null,
      references,
      datasets,
      existingProjects,
      selectedReferenceId: defaultReferenceId,
      selectedPrimaryDatasetId: defaultPrimaryDatasetId,
      selectedSupportDatasetIds: [],
      projectNameInput: "",
      chrAssignmentMinCoveragePercentInput: String(
        packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
      ),
      phasedAssemblyEnabledInput: false,
      createModalOpen: false,
      autoPipelineModalOpen: false,
      autoPipelineRunning: false,
      autoPipelineCanClose: true,
      autoPipelineSteps: [],
      autoPipelineRunId: null,
      autoPipelineCancelRequested: false,
      updating: false,
      editProjectId: null,
      editProjectNameInput: "",
      editReferenceId: "",
      editPrimaryDatasetId: "",
      editSupportDatasetIds: [],
      editChrAssignmentMinCoveragePercentInput: String(
        packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
      ),
      editPhasedAssemblyEnabledInput: false,
      summary: i18nT(current, "importer.runtime.optionsLoadedSummary"),
    },
    assembly: { ...current.assembly, ...buildEmptyAssemblyViewState(current) },
    projectExport: buildEmptyProjectExportState(),
    activeRoute: "importer",
  });
}

function applyAddPackageImportedState(store, payload) {
  const {
    workspaceRoot,
    packageMetadata,
    references,
    datasets,
    existingProjects,
    datasetName,
    importerSummary,
    appendStage,
  } = payload;
  const current = store.getState();
  const sameWorkspace = String(current.session?.workspacePath || "") === String(workspaceRoot || "");
  store.setState({
    session: {
      ...current.session,
      workspacePath: workspaceRoot,
      projectId: sameWorkspace ? current.session.projectId : null,
      projectName: sameWorkspace ? current.session.projectName : "",
    },
    importer: {
      ...current.importer,
      inFlight: false,
      importRunId: null,
      importCancelling: false,
      importCancelError: "",
      workspaceRoot,
      openWorkspacePath: workspaceRoot,
      status: i18nT(current, "importer.runtime.importDoneStatus"),
      summary: importerSummary,
      stages: appendStage ? [...current.importer.stages, appendStage] : [...current.importer.stages],
      addPackageHintsByWorkspacePath: buildNextAddPackageHints(
        current.importer.addPackageHintsByWorkspacePath,
        workspaceRoot,
        datasetName || "dataset",
      ),
    },
    initializer: {
      ...current.initializer,
      optionsLoaded: true,
      optionsError: "",
      packageMetadata: packageMetadata || current.initializer.packageMetadata,
      references: Array.isArray(references) ? references : current.initializer.references,
      datasets: Array.isArray(datasets) ? datasets : current.initializer.datasets,
      existingProjects: Array.isArray(existingProjects)
        ? existingProjects
        : current.initializer.existingProjects,
      summary: i18nT(current, "importer.runtime.optionsLoadedSummary"),
    },
    activeRoute: current.activeRoute,
  });
}

function updateImporterState(store, patch) {
  store.setState({
    importer: {
      ...store.getState().importer,
      ...patch,
    },
  });
}

function buildNextAddPackageHints(hintsByWorkspacePath, workspaceRoot, datasetName) {
  const hints = hintsByWorkspacePath && typeof hintsByWorkspacePath === "object"
    ? hintsByWorkspacePath
    : {};
  const nextName = String(datasetName || "dataset").trim() || "dataset";
  const previousNames = normalizeAddPackageHintNames(hints[workspaceRoot]);
  const nextNames = previousNames.includes(nextName)
    ? previousNames
    : [...previousNames, nextName];
  return {
    ...hints,
    [workspaceRoot]: nextNames,
  };
}

function normalizeAddPackageHintNames(value) {
  const rawNames = Array.isArray(value) ? value : [value];
  return rawNames
    .map((name) => String(name || "").trim())
    .filter(Boolean);
}

function renderAddPackageHint(state, hintValue) {
  const datasetNames = normalizeAddPackageHintNames(hintValue);
  if (!datasetNames.length) {
    return "";
  }
  const placeholder = "__ADD_PACKAGE_DATASET_NAMES__";
  const template = i18nT(state, "importer.runtime.addPackageHint", {
    datasetName: placeholder,
  });
  const placeholderIndex = template.indexOf(placeholder);
  if (placeholderIndex === -1) {
    return `<span class="add-package-hint">${escapeHtml(template)}</span>`;
  }
  const beforeNames = template.slice(0, placeholderIndex);
  const afterNames = template.slice(placeholderIndex + placeholder.length);
  const addedLabel = "added";
  const addedIndex = beforeNames.indexOf(addedLabel);
  const escapedNames = datasetNames.map((name) => escapeHtml(name)).join(",");
  if (addedIndex === -1) {
    return `<span class="add-package-hint">${escapeHtml(beforeNames)}${escapedNames}${escapeHtml(afterNames)}</span>`;
  }
  return `<span class="add-package-hint">${escapeHtml(beforeNames.slice(0, addedIndex))}<strong>${addedLabel}</strong>${escapeHtml(
    beforeNames.slice(addedIndex + addedLabel.length),
  )}${escapedNames}${escapeHtml(afterNames)}</span>`;
}

let workspaceContextMenuCloseTimer = null;

function cancelWorkspaceContextMenuClose(workspacePath = "", store = null) {
  const currentPath = store?.getState?.().importer?.workspaceContextMenu?.workspacePath || "";
  if (workspacePath && currentPath && String(workspacePath) !== String(currentPath)) {
    return;
  }
  if (workspaceContextMenuCloseTimer) {
    clearTimeout(workspaceContextMenuCloseTimer);
    workspaceContextMenuCloseTimer = null;
  }
}

function scheduleWorkspaceContextMenuClose(host, store, workspacePath = "") {
  const currentPath = store.getState().importer?.workspaceContextMenu?.workspacePath || "";
  if (!currentPath || (workspacePath && String(workspacePath) !== String(currentPath))) {
    return;
  }
  cancelWorkspaceContextMenuClose(currentPath, store);
  workspaceContextMenuCloseTimer = setTimeout(() => {
    workspaceContextMenuCloseTimer = null;
    closeWorkspaceContextMenu(host, store, currentPath);
  }, 400);
}

function closeWorkspaceContextMenu(host, store, workspacePath = "") {
  const current = store.getState();
  const contextMenu = current.importer?.workspaceContextMenu || {};
  if (!contextMenu.open || (workspacePath && String(contextMenu.workspacePath || "") !== String(workspacePath))) {
    return;
  }
  cancelWorkspaceContextMenuClose(contextMenu.workspacePath || "", store);
  updateImporterState(store, { workspaceContextMenu: null });
  rerender(host, store);
}

function renderWorkspaceHistoryContextMenu(contextMenu, messages) {
  const left = Number.isFinite(Number(contextMenu.x)) ? Number(contextMenu.x) : 0;
  const top = Number.isFinite(Number(contextMenu.y)) ? Number(contextMenu.y) : 0;
  const workspacePath = String(contextMenu.workspacePath || "").trim();
  return `
    <div class="context-menu" data-workspace-history-context-menu="1" data-workspace-history-context-menu-path="${escapeAttr(workspacePath)}" style="left: ${left}px; top: ${top}px;">
      <button class="context-menu-item" data-workspace-import-add-package-path="${escapeAttr(workspacePath)}">${escapeHtml(messages.buttons.importAddPackage)}</button>
    </div>
  `;
}

function renderImportProgressOverlay(importer, messages) {
  const allStages = Array.isArray(importer.stages) ? importer.stages : [];
  const progressMeta = buildImportProgressMeta(allStages);
  const recentOffset = Math.max(0, allStages.length - 60);
  const recentStages = allStages.slice(recentOffset);
  const isCancelling = importer.importCancelling === true;
  const summary = isCancelling
    ? messages.runtime.importCancellingSummary
    : String(importer.summary || messages.runtime.importProgressIndeterminate);
  const currentStage = stripImportCurrentStageSuffix(recentStages.length
    ? getImportStageLabel(recentStages[recentStages.length - 1], messages)
    : messages.runtime.notStarted);
  const cancelLabel = isCancelling
    ? messages.buttons.cancelImportPending
    : messages.buttons.cancelImport;
  const cancelIcon = isCancelling
    ? `<span class="pipeline-spinner importer-import-progress-cancel-spinner" aria-hidden="true"></span>`
    : `<svg viewBox="0 0 20 20" width="16" height="16" focusable="false" aria-hidden="true">
        <path d="M5 5l10 10M15 5L5 15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      </svg>`;
  const stageItems = recentStages.length
    ? recentStages
        .map((stage, index) => {
          const absoluteIndex = recentOffset + index;
          const isLatest = index === recentStages.length - 1;
          const status = isLatest
            ? isCancelling ? "cancelling" : "running"
            : "done";
          const statusLabelForRow = status === "cancelling"
            ? messages.runtime.importProgressCancellingStatus
            : status === "running"
              ? messages.runtime.importProgressRunningStatus
              : messages.runtime.importProgressDoneStatus;
          const currentAttribute = isLatest ? ' aria-current="step"' : "";
          return `<li class="pipeline-step-row import-progress-step importer-import-progress-step ${escapeAttr(status)}" data-import-progress-step-status="${escapeAttr(status)}"${currentAttribute}>
            <span class="pipeline-step-label">${escapeHtml(formatImportProgressStage(stage, absoluteIndex, progressMeta, messages))}</span>
            ${renderImportProgressStatusIcon(status, statusLabelForRow)}
          </li>`;
        })
        .join("")
    : `<li class="pipeline-step-row import-progress-step importer-import-progress-step ${isCancelling ? "cancelling" : "running"}" data-import-progress-step-status="${isCancelling ? "cancelling" : "running"}" aria-current="step">
        <span class="pipeline-step-label">${escapeHtml(messages.runtime.notStarted)}</span>
        ${renderImportProgressStatusIcon(
          isCancelling ? "cancelling" : "running",
          isCancelling
            ? messages.runtime.importProgressCancellingStatus
            : messages.runtime.importProgressRunningStatus,
        )}
      </li>`;
  return `
    <div class="modal-overlay import-progress-overlay importer-import-progress-overlay">
      <article
        class="card modal-dialog import-progress-dialog importer-import-progress-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(messages.page.importProgressTitle)}"
        aria-describedby="import-progress-dialog-summary"
      >
        <button
          type="button"
          class="button ghost import-progress-close importer-import-progress-close"
          data-import-cancel="1"
          aria-label="${escapeAttr(cancelLabel)}"
          title="${escapeAttr(cancelLabel)}"
          ${isCancelling ? 'disabled aria-disabled="true"' : ""}
        >
          ${cancelIcon}
        </button>
        <section class="importer-import-progress-overview">
          <strong class="importer-import-progress-current-stage">${escapeHtml(currentStage)}</strong>
          ${renderImportProgressMeter(progressMeta, messages)}
          <p id="import-progress-dialog-summary" class="importer-import-progress-summary" aria-live="polite">${escapeHtml(summary)}</p>
          ${importer.importCancelError
            ? `<p class="importer-import-progress-error" role="alert">${escapeHtml(String(importer.importCancelError))}</p>`
            : ""}
        </section>
        <details class="importer-import-progress-log" ${importer.progressDetailsOpen ? "open" : ""}><summary>${escapeHtml(messages.page.importProgressDetailsTitle)}</summary>
          <ul class="status-list import-progress-list importer-import-progress-list" data-import-progress-list="1">${stageItems}</ul>
        </details>
      </article>
    </div>
  `;
}

function renderImportProgressStatusIcon(status, label) {
  const stateClass = status === "done"
    ? "is-done"
    : status === "cancelling"
      ? "is-cancelling"
      : "is-running";
  const icon = status === "done"
    ? `<svg viewBox="0 0 16 16" width="14" height="14" focusable="false" aria-hidden="true">
        <path d="M3 8.25 6.25 11.5 13 4.75" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>`
    : `<span class="pipeline-spinner" aria-hidden="true"></span>`;
  return `<span class="importer-import-progress-step-icon ${stateClass}" role="img" aria-label="${escapeAttr(label)}">${icon}</span>`;
}

function renderImporterStatusToast(importer, messages) {
  if (importer.inFlight) {
    return "";
  }
  const status = String(importer.status || "").trim();
  const summary = String(importer.summary || "").trim();
  if ((!status && !summary) || [messages.runtime.notStarted, messages.runtime.workspaceLoadedStatus, messages.runtime.sessionRestoredStatus].includes(status)) {
    return "";
  }
  const isError = status === messages.runtime.importFailedStatus || status === messages.runtime.openFailedStatus;
  return `
    <div class="importer-status-toast-wrap" data-importer-status-toast="1" aria-live="polite">
      <div class="importer-status-toast ${isError ? "error" : ""}" data-importer-status-banner="1" ${isError ? 'role="alert"' : ""}>
        ${status ? `<strong>${escapeHtml(status)}</strong>` : ""}
        ${summary ? `<span>${escapeHtml(summary)}</span>` : ""}
      </div>
    </div>
  `;
}

function bindImporterStatusToastDismiss(host, store) {
  const binding = ensureImporterStatusToastDismissBinding(host);
  binding.store = store;
  const signature = getImporterStatusToastSignature(store.getState().importer);
  binding.coordinator.onFeedbackChange(signature);
}

function syncImporterStatusToast(host, store) {
  const state = store.getState();
  if (state.activeRoute !== "importer") return;
  const page = host.querySelector(".projects-page");
  host.querySelector('[data-importer-status-toast="1"]')?.remove();
  if (page) page.insertAdjacentHTML("beforeend", renderImporterStatusToast(state.importer, getMessages(state, "importer")));
  const binding = ensureImporterStatusToastDismissBinding(host);
  binding.coordinator.onFeedbackChange("");
  bindImporterStatusToastDismiss(host, store);
}

function ensureImporterStatusToastDismissBinding(host) {
  if (host[IMPORTER_STATUS_TOAST_DISMISS]) {
    return host[IMPORTER_STATUS_TOAST_DISMISS];
  }
  const timerApi = resolveImporterTimerApi();
  const binding = {
    store: null,
    coordinator: null,
  };
  binding.coordinator = createImporterStatusToastDismissCoordinator({
    setTimeoutFn: timerApi.setTimeout.bind(timerApi),
    clearTimeoutFn: timerApi.clearTimeout.bind(timerApi),
    autoDismissMs: IMPORTER_STATUS_TOAST_AUTO_DISMISS_MS,
    onDismiss: () => {
      if (!binding.store) {
        return;
      }
      clearImporterStatusToast(host, binding.store);
    },
  });
  host[IMPORTER_STATUS_TOAST_DISMISS] = binding;
  return binding;
}

function getImporterStatusToastSignature(importer) {
  if (importer?.inFlight) {
    return "";
  }
  const status = String(importer?.status || "").trim();
  const summary = String(importer?.summary || "").trim();
  if (!status && !summary) {
    return "";
  }
  return `${status}\u0000${summary}`;
}

function clearImporterStatusToast(host, store) {
  const currentImporter = store.getState().importer;
  if (!currentImporter.status && !currentImporter.summary) {
    return;
  }
  updateImporterState(store, {
    status: "",
    summary: "",
  });
  host.querySelector('[data-importer-status-toast="1"]')?.remove();
}

function resolveImporterTimerApi() {
  if (
    typeof window !== "undefined" &&
    typeof window.setTimeout === "function" &&
    typeof window.clearTimeout === "function"
  ) {
    return window;
  }
  return globalThis;
}

function createImporterStatusToastDismissCoordinator({
  setTimeoutFn,
  clearTimeoutFn,
  autoDismissMs = IMPORTER_STATUS_TOAST_AUTO_DISMISS_MS,
  onDismiss,
} = {}) {
  const timerApi = resolveImporterTimerApi();
  const scheduleTimeout =
    typeof setTimeoutFn === "function" ? setTimeoutFn : timerApi.setTimeout.bind(timerApi);
  const cancelTimeout =
    typeof clearTimeoutFn === "function" ? clearTimeoutFn : timerApi.clearTimeout.bind(timerApi);
  let currentSignature = "";
  let autoDismissTimer = null;

  const clearAutoDismissTimer = () => {
    if (autoDismissTimer === null) {
      return;
    }
    cancelTimeout(autoDismissTimer);
    autoDismissTimer = null;
  };

  const dismiss = () => {
    currentSignature = "";
    clearAutoDismissTimer();
    onDismiss?.();
  };

  return {
    onFeedbackChange(signature) {
      const normalizedSignature = String(signature || "");
      if (!normalizedSignature) {
        currentSignature = "";
        clearAutoDismissTimer();
        return;
      }
      if (normalizedSignature === currentSignature) {
        return;
      }
      currentSignature = normalizedSignature;
      clearAutoDismissTimer();
      autoDismissTimer = scheduleTimeout(() => {
        autoDismissTimer = null;
        dismiss();
      }, autoDismissMs);
    },
    dispose() {
      currentSignature = "";
      clearAutoDismissTimer();
    },
  };
}

function formatImporterMessage(template, replacements = {}) {
  let message = String(template || "");
  for (const [key, value] of Object.entries(replacements)) {
    message = message.replaceAll(`{${key}}`, String(value ?? ""));
  }
  return message;
}

function getImportErrorFirstLine(error) {
  const raw = String(error?.message || error || "").trim();
  return raw.split(/\r?\n/).map((line) => line.trim()).find(Boolean) || "-";
}

function formatImportFailureSummary(error, stateOrLocale) {
  return i18nT(stateOrLocale, "importer.runtime.importFailedSummary", {
    message: getImportErrorFirstLine(error),
  });
}

function formatImportEndedAfterCancelSummary(stateOrLocale) {
  return i18nT(stateOrLocale, "importer.runtime.importCancelFinishedSummary");
}

function formatImportCancelRequestError(error, stateOrLocale) {
  return i18nT(stateOrLocale, "importer.runtime.importCancelRequestFailedSummary", {
    message: getImportErrorFirstLine(error),
  });
}

function buildImportCompletionErrorPatch(
  error,
  stateOrLocale,
  importer,
  importOperationCompleted,
) {
  const cancellationWasRequested = !importOperationCompleted && importer?.importCancelling === true;
  return {
    projectError: cancellationWasRequested ? "" : String(error?.message || error),
    importDialogOpen: !importOperationCompleted,
    pendingProjectPath: importOperationCompleted ? importer.pendingProjectPath : "",
    inFlight: false,
    importRunId: null,
    importCancelling: false,
    importCancelError: "",
    status: cancellationWasRequested
      ? i18nT(stateOrLocale, "importer.runtime.importCancelFinishedStatus")
      : i18nT(stateOrLocale, "importer.runtime.importFailedStatus"),
    summary: cancellationWasRequested
      ? formatImportEndedAfterCancelSummary(stateOrLocale)
      : formatImportFailureSummary(error, stateOrLocale),
  };
}

function buildImportProgressMeta(stages) {
  let latestPhaseIndex = 0;
  let latestPhaseTotal = 0;
  for (const stage of stages) {
    const phaseIndex = getStagePhaseIndex(stage);
    const phaseTotal = getStagePhaseTotal(stage);
    if (phaseIndex > latestPhaseIndex) {
      latestPhaseIndex = phaseIndex;
    }
    if (phaseTotal > latestPhaseTotal) {
      latestPhaseTotal = phaseTotal;
    }
  }
  if (latestPhaseTotal > 0) {
    return {
      mode: "phase",
      current: Math.min(latestPhaseIndex, latestPhaseTotal),
      total: latestPhaseTotal,
    };
  }

  const progressOffset = findFirstProgressStageIndex(stages);
  const offset = progressOffset >= 0 ? progressOffset : 0;
  let latestProgressIndex = 0;
  let latestProgressTotal = 0;
  for (const stage of stages) {
    const progressIndex = getStageProgressIndex(stage);
    const progressTotal = getStageProgressTotal(stage);
    if (progressIndex > latestProgressIndex) {
      latestProgressIndex = progressIndex;
    }
    if (progressTotal > latestProgressTotal) {
      latestProgressTotal = progressTotal;
    }
  }
  if (latestProgressTotal > 0) {
    const current = latestProgressIndex > 0
      ? offset + latestProgressIndex
      : stages.length;
    const total = Math.max(stages.length, offset + latestProgressTotal);
    return {
      mode: "step",
      offset,
      current: Math.min(current, total),
      total,
    };
  }

  return {
    mode: "indeterminate",
    offset,
    current: latestProgressIndex > 0 ? offset + latestProgressIndex : stages.length,
    total: 0,
  };
}

function findFirstProgressStageIndex(stages) {
  return stages.findIndex((stage) => getStageProgressIndex(stage) > 0);
}

function formatImportProgressStage(stage, absoluteIndex, progressMeta, messages) {
  const label = stripImportProgressSuffix(getImportStageLabel(stage, messages));
  if (progressMeta.mode === "phase") {
    return label;
  }
  const progressIndex = getStageProgressIndex(stage);
  const displayIndex = progressIndex > 0
    ? progressMeta.offset + progressIndex
    : absoluteIndex + 1;
  if (progressMeta.total <= 0) {
    return label;
  }
  return `${label} (${displayIndex}/${progressMeta.total})`;
}

function getImportStageLabel(stage, messages) {
  if (stage && typeof stage === "object") {
    const stageCode = String(stage.stageCode || "").trim();
    const template = messages?.progressStages?.[stageCode];
    if (template) {
      return String(template).replaceAll("{detail}", String(stage.detail || ""));
    }
    return String(stage.label || stage.text || "");
  }
  return String(stage || "");
}

function getStageProgressIndex(stage) {
  if (!stage || typeof stage !== "object") {
    return 0;
  }
  const value = Number(stage.progressIndex);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function getStageProgressTotal(stage) {
  if (!stage || typeof stage !== "object") {
    return 0;
  }
  const value = Number(stage.progressTotal);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function getStagePhaseIndex(stage) {
  if (!stage || typeof stage !== "object") {
    return 0;
  }
  const value = Number(stage.phaseIndex);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function getStagePhaseTotal(stage) {
  if (!stage || typeof stage !== "object") {
    return 0;
  }
  const value = Number(stage.phaseTotal);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function stripImportProgressSuffix(value) {
  return String(value || "").replace(/\s*(?:\(\d+\/\d+\)|（\d+\/\d+）)\s*$/, "");
}

function stripImportCurrentStageSuffix(value) {
  return stripImportProgressSuffix(value)
    .replace(/\s*(?:\([^()]*\)|（[^（）]*）)\s*$/, "")
    .trimEnd();
}

function renderImportProgressMeter(progressMeta, messages) {
  const isDeterminate = progressMeta.mode !== "indeterminate" && progressMeta.total > 0;
  const mode = isDeterminate ? progressMeta.mode : "indeterminate";
  const meterText = mode === "phase"
    ? formatImporterMessage(messages.runtime.importPhaseProgress, {
      current: progressMeta.current,
      total: progressMeta.total,
    })
    : mode === "step"
      ? formatImporterMessage(messages.runtime.importStepProgress, {
        current: progressMeta.current,
        total: progressMeta.total,
      })
      : messages.runtime.importProgressIndeterminate;
  const percent = isDeterminate
    ? Math.max(0, Math.min(100, (progressMeta.current / progressMeta.total) * 100))
    : 0;
  const ariaValues = isDeterminate
    ? ` aria-valuemin="0" aria-valuemax="${escapeAttr(progressMeta.total)}" aria-valuenow="${escapeAttr(progressMeta.current)}"`
    : "";
  const fillStyle = isDeterminate
    ? ` style="width: ${escapeAttr(percent.toFixed(1))}%;"`
    : "";
  return `<div
    class="import-progress-meter"
    data-progress-mode="${escapeAttr(mode)}"
    role="progressbar"
    aria-label="${escapeAttr(meterText)}"
    aria-valuetext="${escapeAttr(meterText)}"${ariaValues}
  >
    <div class="import-progress-meter-track">
      <div class="import-progress-meter-fill"${fillStyle}></div>
    </div>
    <span class="import-progress-meter-text">${escapeHtml(meterText)}</span>
  </div>`;
}

function bindImportProgressScroll(progressList, store) {
  if (!progressList) {
    return;
  }
  const importer = store.getState().importer || {};
  const runId = String(importer.importRunId || "");
  syncImportProgressScroll(progressList, importer);
  progressList.addEventListener("scroll", (event) => {
    const latestImporter = store.getState().importer || {};
    if (!latestImporter.inFlight || String(latestImporter.importRunId || "") !== runId) {
      return;
    }
    const target = event.currentTarget || progressList;
    updateImporterState(store, {
      importProgressAutoScroll: isImportProgressNearBottom(target),
      importProgressScrollTop: Number(target.scrollTop || 0),
    });
  });
}

function syncImportProgressScroll(progressList, importer) {
  if (!importer?.inFlight || !importer?.importRunId) {
    return;
  }
  if (importer.importProgressAutoScroll === false) {
    progressList.scrollTop = clampImportProgressScrollTop(
      Number(importer.importProgressScrollTop || 0),
      progressList,
    );
    return;
  }
  progressList.scrollTop = getImportProgressBottomScrollTop(progressList);
}

function isImportProgressNearBottom(progressList) {
  return getImportProgressBottomScrollTop(progressList) - Number(progressList.scrollTop || 0)
    <= IMPORT_PROGRESS_BOTTOM_THRESHOLD_PX;
}

function getImportProgressBottomScrollTop(progressList) {
  return Math.max(
    0,
    Number(progressList.scrollHeight || 0) - Number(progressList.clientHeight || 0),
  );
}

function clampImportProgressScrollTop(scrollTop, progressList) {
  const bottom = getImportProgressBottomScrollTop(progressList);
  if (!Number.isFinite(scrollTop) || scrollTop <= 0) {
    return 0;
  }
  return Math.min(scrollTop, bottom);
}

async function cancelCurrentImport(host, store) {
  const snapshot = store.getState();
  const importer = snapshot.importer || {};
  const runId = String(importer.importRunId || "").trim();
  if (!runId || !importer.inFlight || importer.importCancelling) {
    return;
  }
  updateImporterState(store, {
    importCancelling: true,
    importCancelError: "",
    summary: i18nT(snapshot, "importer.runtime.importCancellingSummary"),
  });
  rerender(host, store);

  try {
    const result = await requestImportCancel({ runId, stateOrLocale: snapshot });
    const currentImporter = store.getState().importer || {};
    if (
      String(currentImporter.importRunId || "") !== runId
      || !currentImporter.inFlight
    ) {
      return;
    }
    if (result === false || result?.cancelRequested === false) {
      throw new Error(i18nT(snapshot, "importer.runtime.importCancelRequestNotAccepted"));
    }
    const currentStages = Array.isArray(currentImporter.stages)
      ? currentImporter.stages
      : [];
    updateImporterState(store, {
      stages: [
        ...currentStages,
        i18nT(snapshot, "importer.runtime.importCancelRequestedStage"),
      ],
    });
    rerender(host, store);
  } catch (error) {
    const currentImporter = store.getState().importer || {};
    if (
      String(currentImporter.importRunId || "") !== runId
      || !currentImporter.inFlight
    ) {
      return;
    }
    updateImporterState(store, {
      importCancelling: false,
      importCancelError: formatImportCancelRequestError(error, snapshot),
      summary: importer.summary,
    });
    rerender(host, store);
  }
}

function createImportRunId(prefix) {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now()}-${randomPart}`;
}

function readWorkspaceHistory() {
  try {
    const raw = window.localStorage.getItem(WORKSPACE_HISTORY_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .map((item) => {
        if (!item || typeof item.path !== "string") {
          return null;
        }
        const path = item.path.trim();
        if (!path) {
          return null;
        }
        return {
          path,
          ...(item.projectName ? { projectName: String(item.projectName) } : {}),
          lastUsedAt: Number.isFinite(Number(item.lastUsedAt))
            ? Number(item.lastUsedAt)
            : Date.now(),
        };
      })
      .filter(Boolean)
      .sort((a, b) => b.lastUsedAt - a.lastUsedAt);
  } catch {
    return [];
  }
}

function writeWorkspaceHistory(records) {
  try {
    window.localStorage.setItem(WORKSPACE_HISTORY_KEY, JSON.stringify(records));
  } catch {
    // ignore localStorage failures
  }
}

function removeWorkspaceHistoryPaths(paths) {
  const dropSet = new Set(normalizePathList(paths));
  if (dropSet.size === 0) {
    return;
  }
  const nextRecords = readWorkspaceHistory().filter((item) => !dropSet.has(item.path));
  writeWorkspaceHistory(nextRecords);
}

function getFailedHistoryPaths(historyRecords, validationMap, validatedPaths = []) {
  const validated = new Set(validatedPaths);
  const validation = validationMap && typeof validationMap === "object" ? validationMap : {};
  return historyRecords
    .map((item) => item.path)
    .filter((path) => validated.has(path) && validation[path]?.ok === false);
}

function normalizePathList(paths) {
  if (!Array.isArray(paths)) {
    return [];
  }
  const deduped = new Set();
  for (const path of paths) {
    const normalized = String(path || "").trim();
    if (normalized) {
      deduped.add(normalized);
    }
  }
  return Array.from(deduped);
}

function workspacePathListIncludes(paths, candidatePath) {
  const candidateIdentity = normalizeWorkspacePathIdentity(candidatePath);
  return Boolean(candidateIdentity) && paths.some(
    (path) => normalizeWorkspacePathIdentity(path) === candidateIdentity,
  );
}

function normalizeWorkspacePathIdentity(value) {
  const normalized = String(value || "").trim().replace(/\\/g, "/").replace(/\/+$/, "");
  return /^(?:[a-z]:\/|\/\/)/i.test(normalized) ? normalized.toLowerCase() : normalized;
}

function formatTime(timestamp, locale = "zh") {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) {
    return getMessages(locale, "importer").runtime.unknownTime;
  }
  try {
    return formatDateTime(locale, new Date(value));
  } catch {
    return String(value);
  }
}

function rerender(host, store) {
  if (store.getState().activeRoute !== "importer") {
    syncSessionHeader(store);
    return;
  }
  const routeHost = host.closest("#route-host");
  if (!routeHost) {
    return;
  }
  routeHost.innerHTML = renderImporterPage(store.getState());
  bindImporterPage(routeHost, store);
  syncSessionHeader(store);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}

function syncSessionHeader(store) {
  if (!globalThis.document) return;
  const state = store.getState();
  const workspace = document.querySelector("#session-workspace");
  const title = document.querySelector("#session-title");
  const shellMessages = getMessages(state, "shell");
  if (workspace) {
    workspace.textContent = state.session.workspacePath || shellMessages.notOpened;
  }
  if (title) {
    title.textContent = state.session.projectName
      ? `${shellMessages.currentProjectPrefix}${state.session.projectName}`
      : shellMessages.noProjectSelected;
  }
}

export function __testCreateImporterStatusToastDismissCoordinator(options = {}) {
  return createImporterStatusToastDismissCoordinator(options);
}
