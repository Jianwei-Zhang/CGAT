import { bindAssemblyNavigation, syncAssemblyNavigation } from "./ui/shell/assembly-navigation.js";
import { requestAppConfirm, requestAppNotice } from "./ui/shell/app-dialog.js";
import { bindLocalViewCloseSave } from "./ui/shell/local-view-close-save.js";
import { bindAppTooltips, hideAppTooltips } from "./ui/app-tooltip-runtime.js";
import "./styles/tooltips.css";
import { releaseProjectOverviewPreview, releaseProjectPathOverview } from "./ui/pages/project-export-page.js";
import { retagAssemblyDomLocale } from "./ui/shell/assembly-session-cache.js";
import { patchLocaleMarkup } from "./ui/i18n/presentation-patch.js";
import { renderAssemblyPage, syncAssemblyTransientInteractions, disposeAssemblyTransientInteractions } from "./ui/pages/assembly-page.js";
import { createAppUpdater, updateWorkBusy } from "./services/app-update.js";
import { invokeCommand, listenBackendEvent, getPendingBackendCommands, pickDirectoryPath } from "./services/backend-api.js";
import { openUpdateDialog } from "./ui/shell/app-update-panel.js";
import "./styles/app-update.css";
import { bindShellSelects } from "./ui/shell/shell-select-runtime.js";
import { projectEntryBusy } from "./services/project-drop-controller.js";
import { bindProjectDrop } from "./ui/shell/project-drop.js";
import { readWorkspaceHistory as readSharedHistory, writeWorkspaceHistory as writeSharedHistory } from "./services/workspace-history.js";
import { applyAppTypography, getAppSettings, initializeAppTheme, subscribeAppTheme } from "./services/app-settings.js";
import { bindAppSettings } from "./ui/shell/app-settings-panel.js";
import "./styles/settings.css";
import { createStore } from "./state/store.js";
import { flushAssemblyProjectState, selectAssemblyChromosome } from "./ui/pages/assembly-page.js";
import { openProjectWorkspace as openWorkspace } from "./services/project-session.js";
import { bindAppShellUpdateIndicator, bindAppThemeToggle, renderAppShell } from "./ui/shell/app-shell.js";
import { registerRoutes, renderCurrentRoute } from "./ui/shell/router.js";
import {
  migrateWorkspaceHistoryToArrivalOrder,
  switchWorkspaceFromShell,
  updateWorkspaceHistory,
} from "./ui/shell/session-switchers.js";
import { getMessages, t } from "./ui/i18n/index.js";
import { relocalizeAppState } from "./ui/i18n/state-relocalize.js";
import "./styles/base.css";
import "./styles/theme.css";
import "./styles/layout.css";
import "./styles/components.css";

const LAST_WORKSPACE_KEY = "gpm_next:last_workspace";
const LOCALE_STORAGE_KEY = "gpm_next:locale";
const app = document.getElementById("app");
const initialLocale = readPreferredLocale();
const store = createStore({
  activeRoute: "importer",
  assemblyNavigation: { partitionId: null, workspacePath: "", busy: false },
  locale: initialLocale,
  runtime: {
    ready: true,
    mode: window.__TAURI__?.core?.invoke ? "Tauri Runtime" : "Browser Preview",
  },
  session: {
    workspacePath: "",
    projectName: "",
    projectId: null,
  },
  importer: {
    importDialogOpen: false,
    importPartitionId: "",
    libraryDialog: null,
    libraryMenu: null,
    libraryError: "",
    libraryOverflowActions: [],
    librarySelectedId: null,
    libraryRevealedPath: "",
    libraryQuery: "",
    libraryRenamingId: "",
    libraryRenameError: "",
    restoringSession: getAppSettings().restoreLastWorkspace !== false,
    importSource: "zip",
    projectNameInput: "",
    projectError: "",
    pendingProjectPath: "",
    zipPath: "",
    workspaceRoot: "",
    extractedPath: "",
    openWorkspacePath: "",
    historyValidation: {},
    copyDialog: null,
    deleteConfirmOpen: false,
    deleteSelectionMode: "",
    deleteWithFiles: false,
    deleteTargets: [],
    inFlight: false,
    importRunId: null,
    importCancelling: false,
    importCancelError: "",
    importProgressDismissed: false,
    importParallelism: getAppSettings().importParallelism || "auto",
    status: getMessages(initialLocale, "importer").runtime.notStarted,
    stages: [],
    summary: t(initialLocale, "importer.page.title"),
  },
  initializer: {
    loading: false,
    optionsLoaded: false,
    optionsError: "",
    packageMetadata: {
      packageMode: "fast",
      sequenceLayout: "partitioned",
      preassignedChr: true,
      chrAssignmentMinCoveragePercent: 60,
      selfAlignmentScope: "chr_partition",
      crossAlignmentScope: "chr_partition",
    },
    grtRecipe: null,
    references: [],
    datasets: [],
    existingProjects: [],
    selectedReferenceId: "",
    selectedPrimaryDatasetId: "",
    selectedSupportDatasetIds: [],
    projectNameInput: "",
    chrAssignmentMinCoveragePercentInput: "60",
    phasedAssemblyEnabledInput: false,
    createModalOpen: false,
    autoPipelineModalOpen: false,
    autoPipelineRunning: false,
    autoPipelineCanClose: true,
    autoPipelineSteps: [],
    autoPipelineRunId: null,
    autoPipelineCancelRequested: false,
    creating: false,
    updating: false,
    editProjectId: null,
    editProjectNameInput: "",
    editReferenceId: "",
    editPrimaryDatasetId: "",
    editSupportDatasetIds: [],
    editChrAssignmentMinCoveragePercentInput: "60",
    editPhasedAssemblyEnabledInput: false,
    summary: t(initialLocale, "workspace.runtime.initializerSummary"),
  },
  assembly: {
    loading: false,
    bootstrapping: false,
    summary: t(initialLocale, "workspace.runtime.assemblySummary"),
    activeTab: "assembly",
    chromosomes: [],
    chrPickerOpen: false,
    selectedChrName: "",
    chrCtgs: [],
    refTrackMembers: [],
    phasedChrTracks: [],
    isChrPhased: false,
    activePhasedTrackKey: "",
    activeHitsTrackKey: "primary",
    activePhasedTrackKeyByChr: {},
    activeHitsTrackKeyByChr: {},
    deletedCtgs: [],
    selectedDeletedCtgRecordIds: [],
    selectedCtgId: null,
    ctgDetail: null,
    editCandidates: {
      moveTargetCtgs: [],
      addSeqCandidates: [],
    },
    trackView: {
      supportDsCtgLen: 0,
      minTickUnitKb: 10000,
      maxTickCount: 10,
      alignmentLength: 10000,
      minIdentityPct: 0,
    },
    subviewTrackView: {
      supportDsCtgLen: 0,
      minTickUnitKb: 10000,
      maxTickCount: 10,
      alignmentLength: 10000,
      minIdentityPct: 0,
    },
    selectedMemberSeqId: null,
    actionStatus: "",
    actionError: "",
    junctionLoading: false,
    junctionStatus: "",
    junctionError: "",
    junctionReport: null,
    supportDatasetId: null,
    supportChrCtgs: [],
    supportMirroredCtgs: [],
    supportDsCtgLenRulesByChr: {},
    supportDsCtgLenRulesDialogOpen: false,
    finalPathByChr: {},
    grtProjectView: {
      recipe: {},
      baselineFinalPathByChr: {},
      sourceCards: [],
      verification: {},
    },
    grtResultDisplayByChr: {},
    grtResultToast: null,
    finalPathViewMode: "graph",
    degapProjectState: {},
    degap: {
      settings: {},
      jobs: [],
      settingsPanelDismissed: false,
      panelOpen: false,
      feedback: "",
      error: "",
      menu: null,
      pendingJobIntent: null,
      expandedJobId: "",
      collapsedJobCardChrNames: [],
      trackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
      },
      loadedWorkspaceRoot: "",
      loadingWorkspaceSettings: false,
    },
    finalPathTrackView: {
      minTickUnitKb: 10000,
      maxTickCount: 10,
    },
    trackSelectedCtgIds: [],
    hiddenPrimaryCtgIds: [],
    hiddenPrimaryCtgIdsByChr: {},
    trackDragOffsets: [],
    subviewTrackDragOffsets: [],
    subviewAnchorStateByKey: {},
    subviewHistoryByKey: {},
    mainViewHistory: {
      projectId: 0,
      referenceChrId: 0,
      chrName: "",
      canUndo: false,
      canRedo: false,
      canReset: false,
      undoOperation: null,
      redoOperation: null,
      appliedOperationCount: 0,
      retainedOperationCount: 0,
      invalidated: false,
      inFlight: false,
    },
    historyHighlightCtgId: null,
    trackScrollState: {
      viewportKey: "",
      scrollLeft: 0,
    },
    subviewTrackScrollState: {
      viewportKey: "",
      scrollLeft: 0,
    },
    finalPathTrackScrollState: {
      viewportKey: "",
      scrollLeft: 0,
    },
    subview: {
      mode: "2-contig",
      selectedAContigId: null,
      selectedARole: "",
      selectedBContigId: null,
      selectedBRole: "",
      message: "",
      error: "",
      summary: null,
    },
    error: "",
  },
  projectPreview: null,
  projectExport: {
    loading: false,
    loaded: false,
    error: "",
    projectId: null,
    chromosomes: [],
    unplacedCtgCount: 0,
    unplacedBp: 0,
    finalPathByChr: {},
    primaryCtgsByChr: {},
    job: null,
  },
});

void bindLocalViewCloseSave({
  windowHandle: window.__GPM_NATIVE_LOCAL_VIEWS__ ? window.__TAURI__?.window?.getCurrentWindow?.() : null,
  flush: () => flushAssemblyProjectState(document.querySelector("#route-host"), store),
  confirmDiscard: error => {
    const locale = store.getState().locale, en = locale === "en";
    return requestAppConfirm(`${en
      ? "Local View tasks could not be saved. If the project folder was moved or deleted, restore it to its original location and retry. Close without saving? Unsaved Local View changes will be lost."
      : "局部比对任务保存失败。如果项目文件夹已被移动或删除，可恢复到原路径后重试。是否不保存并关闭？尚未保存的局部视图更改将丢失。"}\n\n${error?.message || error}`, {
      locale,
      title: en ? "Close without saving?" : "不保存并关闭？",
      confirmLabel: en ? "Close without saving" : "不保存并关闭",
      cancelLabel: en ? "Keep open" : "保持打开",
    });
  },
}).catch(error => console.error("Local View close-save listener failed", error));

const updater = createAppUpdater({
  invoke: invokeCommand, listen: listenBackendEvent, storage: window.localStorage,
  isBusy: () => updateWorkBusy(store.getState(), getPendingBackendCommands()),
  canNotify: () => !document.hidden && !document.querySelector("dialog[open], .modal-overlay, [role='dialog'][aria-modal='true']"),
  prepareInstall: async () => {
    try { await flushAssemblyProjectState(document.querySelector("#route-host"), store); }
    catch { throw new Error("update_save_failed"); }
  },
  onOffer: () => openUpdateDialog(updater, {
    getLocale: () => store.getState().locale,
    subscribeLocale: fn => store.subscribe(fn),
  }),
});
void updater.initialize().then(() => {
  if (!updater.getState().enabled) return;
  // One automatic check per launch; notification retries reuse its result.
  if (typeof getAppSettings !== "function" || getAppSettings().autoCheckUpdates !== false) {
    void updater.check();
  }
  setInterval(() => updater.notify(), 30_000);
});

document.documentElement.lang = initialLocale === "en" ? "en" : "zh-CN";
migrateWorkspaceHistoryToArrivalOrder(window.localStorage);
applyAppTypography();
initializeAppTheme();
// Chart colours live in SVG attributes and Canvas pixels, so a theme switch has
// to repaint the mounted route instead of relying on CSS alone.
subscribeAppTheme(() => {
  window.dispatchEvent(new Event("gpm-next:route-refresh"));
});
let settingsController = null;
app.innerHTML = renderAppShell(store.getState());
bindAppTooltips(app);
settingsController = bindSettings(app, store);
bindGlobalSettingsShortcut(() => settingsController);
void listenBackendEvent("gpm-open-settings", () => settingsController?.open?.()).catch(() => {});
bindGlobalSessionSwitchers(app, store);
registerRoutes(app, store, () => {
  renderCurrentRoute(app, store);
});
renderCurrentRoute(app, store);
syncSessionHeader(store.getState());
bindProjectDrop(app, store).catch(error => console.error("GPM drag/drop setup failed", error));
if (getAppSettings().restoreLastWorkspace !== false) {
  restoreLastWorkspace(store).finally(() => {
    store.setState({ importer: { ...store.getState().importer, restoringSession: false } });
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  });
}

let lastRoute = store.getState().activeRoute;
let lastSessionWorkspacePath = normalizeWorkspacePath(store.getState().session.workspacePath);
let lastSessionProjectName = store.getState().session.projectName;
store.subscribe((nextState) => {
  if (nextState.activeRoute !== lastRoute) {
    lastRoute = nextState.activeRoute;
    renderCurrentRoute(app, store);
  }
  const nextWorkspacePath = normalizeWorkspacePath(nextState.session.workspacePath);
  if (nextWorkspacePath && nextWorkspacePath !== lastSessionWorkspacePath) {
    appendWorkspaceHistory(nextWorkspacePath, nextState.session.projectName);
  }
  if (nextWorkspacePath && nextState.session.projectName !== lastSessionProjectName) {
    const records = readWorkspaceHistory();
    writeWorkspaceHistory(records.map(record => record.path === nextWorkspacePath ? { ...record, projectName: nextState.session.projectName } : record));
  }
  lastSessionProjectName = nextState.session.projectName;
  lastSessionWorkspacePath = nextWorkspacePath;
  syncSessionHeader(nextState);
  persistLastWorkspace(nextState);
  persistLocale(nextState);
});

window.addEventListener("gpm-next:route-refresh", () => {
  renderCurrentRoute(app, store);
});

function syncSessionHeader(state) {
  syncAssemblyNavigation(app, state);
  document.querySelectorAll(".route-button").forEach(button => {
    const needsProject = ["projectPreview", "assembly", "projectExport"].includes(button.dataset.route);
    button.disabled = (needsProject && (!state.session.workspacePath || !state.session.projectId))
      || projectEntryBusy(state);
    button.setAttribute("data-app-tooltip", needsProject && !state.session.projectId
      ? (state.locale === "en" ? "Open a project first" : "请先打开项目") : "");
  });
}

function persistLastWorkspace(state) {
  try {
    const workspacePath = normalizeWorkspacePath(state.session.workspacePath);
    if (!workspacePath) {
      window.localStorage.removeItem(LAST_WORKSPACE_KEY);
      return;
    }
    const payload = {
      workspacePath,
      projectId: state.session.projectId ?? null,
      projectName: String(state.session.projectName || ""),
    };
    window.localStorage.setItem(LAST_WORKSPACE_KEY, JSON.stringify(payload));
  } catch {
    // ignore localStorage failures
  }
}

function readLastWorkspace() {
  try {
    const raw = window.localStorage.getItem(LAST_WORKSPACE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.workspacePath !== "string") {
      return null;
    }
    const workspacePath = normalizeWorkspacePath(parsed.workspacePath);
    if (!workspacePath) {
      return null;
    }
    return {
      workspacePath,
      projectId: parsed.projectId ?? null,
      projectName: typeof parsed.projectName === "string" ? parsed.projectName : "",
    };
  } catch {
    return null;
  }
}

function clearLastWorkspace() {
  try {
    window.localStorage.removeItem(LAST_WORKSPACE_KEY);
  } catch {
    // ignore localStorage failures
  }
}

function readPreferredLocale() {
  try {
    const value = String(window.localStorage.getItem(LOCALE_STORAGE_KEY) || "").trim();
    return value === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
}

function persistLocale(state) {
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, state.locale === "en" ? "en" : "zh");
  } catch {
    // ignore localStorage failures
  }
}

function applyGlobalLanguageChange(root, storeRef, locale) {
  const value = locale === "en" ? "en" : "zh";
  document.documentElement.lang = value === "en" ? "en" : "zh-CN";
  hideAppTooltips(root);
  const previous = storeRef.getState();
  if (previous.locale === value) return;
  const next = relocalizeAppState(previous, value);
  storeRef.setState(next);
  if (previous.activeRoute === "assembly") {
    patchLocaleMarkup(root, renderAppShell(previous), renderAppShell(next));
    const routeHost = root.querySelector("#route-host");
    patchLocaleMarkup(routeHost, renderAssemblyPage(previous), renderAssemblyPage(next));
    retagAssemblyDomLocale(routeHost, next);
    syncAssemblyTransientInteractions(routeHost, storeRef);
    syncSessionHeader(next);
    return;
  }
  disposeAssemblyTransientInteractions(root.querySelector("#route-host"));
  releaseProjectOverviewPreview(root.querySelector("#route-host"));
  releaseProjectPathOverview(root.querySelector("#route-host"));
  root.innerHTML = renderAppShell(storeRef.getState());
  settingsController = bindSettings(root, storeRef);
  bindGlobalSessionSwitchers(root, storeRef);
  registerRoutes(root, storeRef, () => {
    renderCurrentRoute(root, storeRef);
  });
  renderCurrentRoute(root, storeRef);
  syncSessionHeader(storeRef.getState());
}

function bindGlobalSettingsShortcut(getController) {
  window.addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.key !== ",") {
      return;
    }
    const controller = getController();
    if (!controller) return;
    if (controller.isOpen()) {
      event.preventDefault();
      controller.close();
      return;
    }
    if (document.querySelector("dialog[open], .modal-overlay, [role='dialog'][aria-modal='true']")) {
      return;
    }
    event.preventDefault();
    controller.open();
  });
}

function bindGlobalSessionSwitchers(root, storeRef) {
  bindAssemblyNavigation(root, storeRef, {
    flush: () => flushAssemblyProjectState(root.querySelector("#route-host"), storeRef),
    switchWorkspace: path => switchWorkspaceFromShell(storeRef, path, { openWorkspace }),
    selectChromosome: name => selectAssemblyChromosome(root.querySelector("#route-host"), storeRef, name),
    refresh: () => window.dispatchEvent(new Event("gpm-next:route-refresh")),
    notice: message => requestAppNotice(message, { store: storeRef }),
  });
}

async function restoreLastWorkspace(storeRef) {
  const snapshot = readLastWorkspace();
  if (!snapshot?.workspacePath) {
    return;
  }

  storeRef.setState({
    importer: {
      ...storeRef.getState().importer,
      workspaceRoot: snapshot.workspacePath,
      status: t(storeRef.getState(), "importer.runtime.sessionRestoringStatus"),
      summary: t(storeRef.getState(), "importer.runtime.sessionRestoringSummary", {
        workspacePath: snapshot.workspacePath,
      }),
      stages: [t(storeRef.getState(), "importer.runtime.sessionRestoringStage")],
    },
  });

  try {
    const options = await openWorkspace({ workspaceRoot: snapshot.workspacePath });
    const defaultReferenceId = options.references[0]?.referenceGenomeId || "";
    const defaultPrimaryDatasetId = options.datasets[0]?.datasetId || "";
    if (storeRef.getState().session.workspacePath || storeRef.getState().importer.inFlight || storeRef.getState().importer.importDialogOpen) return;
    const matchedProject = options.existingProjects.length === 1 ? options.existingProjects[0] : null;

    storeRef.setState({
      session: {
        ...storeRef.getState().session,
        workspacePath: (options.workspaceRoot || snapshot.workspacePath),
        projectId: matchedProject?.projectId || null,
        projectName: matchedProject?.projectName || "",
      },
      importer: {
        ...storeRef.getState().importer,
        workspaceRoot: (options.workspaceRoot || snapshot.workspacePath),
        openWorkspacePath: (options.workspaceRoot || snapshot.workspacePath),
        inFlight: false,
        importRunId: null,
        importCancelling: false,
        importCancelError: "",
        status: t(storeRef.getState(), "importer.runtime.sessionRestoredStatus"),
        summary: t(storeRef.getState(), "importer.runtime.sessionRestoredSummary"),
        stages: [...storeRef.getState().importer.stages, t(storeRef.getState(), "importer.runtime.sessionRestoredStage")],
      },
      initializer: {
        ...storeRef.getState().initializer,
        optionsLoaded: true,
        optionsError: "",
        packageMetadata: options.packageMetadata || storeRef.getState().initializer.packageMetadata,
        grtRecipe: options.grtRecipe || null,
        references: options.references,
        datasets: options.datasets,
        existingProjects: options.existingProjects,
        selectedReferenceId: defaultReferenceId,
        selectedPrimaryDatasetId: defaultPrimaryDatasetId,
        selectedSupportDatasetIds: [],
        chrAssignmentMinCoveragePercentInput: String(
          options.packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
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
          options.packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
        ),
        editPhasedAssemblyEnabledInput: false,
        summary: matchedProject
          ? t(storeRef.getState(), "workspace.runtime.restoredProjectSummary", {
            projectName: matchedProject.projectName,
            projectId: matchedProject.projectId,
          })
          : t(storeRef.getState(), "workspace.runtime.restoredWorkspaceSummary"),
      },
      activeRoute: "importer",
    });
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  } catch (error) {
    if (storeRef.getState().session.workspacePath || storeRef.getState().importer.inFlight || storeRef.getState().importer.importDialogOpen) return;
    clearLastWorkspace();
    storeRef.setState({
      importer: {
        ...storeRef.getState().importer,
        inFlight: false,
        importRunId: null,
        importCancelling: false,
        importCancelError: "",
        projectError: String(error?.message || error),
        pendingProjectPath: error.pendingProjectPath || "",
        status: t(storeRef.getState(), "importer.runtime.sessionRestoreFailedStatus"),
        summary: t(storeRef.getState(), "importer.runtime.sessionRestoreFailedSummary"),
        stages: [],
      },
      session: {
        ...storeRef.getState().session,
        workspacePath: "",
        projectId: null,
        projectName: "",
      },
    });
  }
}

function normalizeWorkspacePath(value) {
  return String(value || "").trim();
}

function readWorkspaceHistory() { return readSharedHistory(); }

function writeWorkspaceHistory(records) { writeSharedHistory(records); }

function appendWorkspaceHistory(workspacePath, projectName = "") {
  const path = normalizeWorkspacePath(workspacePath);
  if (!path) {
    return;
  }
  writeWorkspaceHistory(updateWorkspaceHistory(readWorkspaceHistory(), path, projectName));
}


function bindSettings(root, storeRef) {
  bindShellSelects(root);
  bindAppThemeToggle(root, { getLocale: () => storeRef.getState().locale });
  bindAppShellUpdateIndicator(root, updater);
  return bindAppSettings(root, {
    updater,
    getLocale: () => storeRef.getState().locale === "en" ? "en" : "zh",
    getRuntimeMode: () => storeRef.getState().runtime?.mode || "",
    onTypographyChange: () => window.dispatchEvent(new Event("gpm-next:route-refresh")),
    onLanguageChange: locale => applyGlobalLanguageChange(root, storeRef, locale),
    onPickDirectory: () => pickDirectoryPath(storeRef.getState()),
    onLayoutReset: () => {
      root.querySelector(".project-browser")?.style?.removeProperty("--project-sidebar-width");
      window.dispatchEvent(new Event("gpm-next:route-refresh"));
    },
  });
}
