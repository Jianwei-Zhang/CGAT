import { createStore } from "./state/store.js";
import { flushAssemblyProjectState } from "./ui/pages/assembly-page.js";
import { openProjectWorkspace as openWorkspace } from "./services/project-session.js";
import { renderAppShell } from "./ui/shell/app-shell.js";
import { registerRoutes, renderCurrentRoute } from "./ui/shell/router.js";
import {
  buildWorkspaceSwitchItems,
  switchWorkspaceFromShell,
} from "./ui/shell/session-switchers.js";
import { getMessages, t } from "./ui/i18n/index.js";
import { relocalizeAppState } from "./ui/i18n/state-relocalize.js";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";

const LAST_WORKSPACE_KEY = "gpm_next:last_workspace";
const WORKSPACE_HISTORY_KEY = "gpm_next:workspace_history";
const LOCALE_STORAGE_KEY = "gpm_next:locale";
const app = document.getElementById("app");
const initialLocale = readPreferredLocale();
const store = createStore({
  activeRoute: "importer",
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
    importSource: "zip",
    projectNameInput: "",
    projectError: "",
    pendingProjectPath: "",
    zipPath: "",
    workspaceRoot: "",
    extractedPath: "",
    openWorkspacePath: "",
    historyValidation: {},
    deleteConfirmOpen: false,
    deleteSelectionMode: "",
    deleteWithFiles: false,
    deleteTargets: [],
    inFlight: false,
    importRunId: null,
    importCancelling: false,
    importCancelError: "",
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
      mapq: 0,
    },
    subviewTrackView: {
      supportDsCtgLen: 0,
      minTickUnitKb: 10000,
      maxTickCount: 10,
      alignmentLength: 10000,
      mapq: 0,
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

app.innerHTML = renderAppShell(store.getState());
bindGlobalLanguageSwitch(app, store);
bindGlobalSessionSwitchers(app, store);
registerRoutes(app, store, () => {
  renderCurrentRoute(app, store);
});
renderCurrentRoute(app, store);
syncSessionHeader(store.getState());
restoreLastWorkspace(store);

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
  syncLanguageSwitch(nextState);
  persistLastWorkspace(nextState);
  persistLocale(nextState);
});

window.addEventListener("gpm-next:route-refresh", () => {
  renderCurrentRoute(app, store);
});

function syncSessionHeader(state) {
  const workspaceSelect = document.querySelector("#session-workspace-select");
  const labels = getMessages(state, "shell");
  document.querySelectorAll(".route-button").forEach(button => {
    const needsProject = ["assembly", "projectExport"].includes(button.dataset.route);
    button.disabled = (needsProject && (!state.session.workspacePath || !state.session.projectId))
      || state.importer.inFlight || state.initializer.autoPipelineRunning;
    button.title = needsProject && !state.session.projectId
      ? (state.locale === "en" ? "Open a project first" : "请先打开项目") : "";
  });
  if (workspaceSelect) {
    const workspaceItems = buildWorkspaceSwitchItems({
      state,
      historyRecords: readWorkspaceHistory(),
      labels,
    });
    replaceSelectOptions(workspaceSelect, workspaceItems);
    workspaceSelect.disabled = state.importer.inFlight || state.initializer.autoPipelineRunning || (workspaceItems.length === 1 && !workspaceItems[0]?.value);
  }
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

function syncLanguageSwitch(state) {
  const select = document.querySelector("#app-language-select");
  if (select) {
    const nextValue = state.locale === "en" ? "en" : "zh";
    if (select.value !== nextValue) {
      select.value = nextValue;
    }
  }
}

function bindGlobalLanguageSwitch(root, storeRef) {
  const select = root.querySelector("#app-language-select");
  select?.addEventListener("change", () => {
    const value = select.value === "en" ? "en" : "zh";
    storeRef.setState(relocalizeAppState(storeRef.getState(), value));
    root.innerHTML = renderAppShell(storeRef.getState());
    bindGlobalLanguageSwitch(root, storeRef);
    bindGlobalSessionSwitchers(root, storeRef);
    registerRoutes(root, storeRef, () => {
      renderCurrentRoute(root, storeRef);
    });
    renderCurrentRoute(root, storeRef);
    syncSessionHeader(storeRef.getState());
    syncLanguageSwitch(storeRef.getState());
  });
}

function bindGlobalSessionSwitchers(root, storeRef) {
  const workspaceSelect = root.querySelector("#session-workspace-select");

  workspaceSelect?.addEventListener("change", async () => {
    const nextWorkspacePath = normalizeWorkspacePath(workspaceSelect.value);
    const currentWorkspacePath = normalizeWorkspacePath(storeRef.getState().session.workspacePath);
    if (!nextWorkspacePath || nextWorkspacePath === currentWorkspacePath) {
      syncSessionHeader(storeRef.getState());
      return;
    }
    try {
      const before = storeRef.getState();
      storeRef.setState({ importer: { ...before.importer, inFlight: true, projectError: "" } });
      await flushAssemblyProjectState(document.querySelector("#route-host"), storeRef);
      await switchWorkspaceFromShell(storeRef, nextWorkspacePath, { openWorkspace });
      window.dispatchEvent(new Event("gpm-next:route-refresh"));
    } catch (error) {
      const current = storeRef.getState();
      storeRef.setState({
        importer: {
          ...current.importer,
          inFlight: false,
          importRunId: null,
          importCancelling: false,
          importCancelError: "",
          projectError: String(error?.message || error),
          pendingProjectPath: error.pendingProjectPath || "",
          status: t(current, "importer.runtime.openFailedStatus"),
          summary: String(error?.message || error || ""),
        },
        activeRoute: "importer",
      });
      window.dispatchEvent(new Event("gpm-next:route-refresh"));
    }
    syncSessionHeader(storeRef.getState());
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
        workspacePath: snapshot.workspacePath,
        projectId: matchedProject?.projectId || null,
        projectName: matchedProject?.projectName || "",
      },
      importer: {
        ...storeRef.getState().importer,
        workspaceRoot: snapshot.workspacePath,
        openWorkspacePath: snapshot.workspacePath,
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
        const path = normalizeWorkspacePath(item.path);
        if (!path) {
          return null;
        }
        return {
          path,
          projectName: String(item.projectName || ""),
          lastUsedAt: Number.isFinite(Number(item.lastUsedAt))
            ? Number(item.lastUsedAt)
            : Date.now(),
        };
      })
      .filter(Boolean);
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

function appendWorkspaceHistory(workspacePath, projectName = "") {
  const path = normalizeWorkspacePath(workspacePath);
  if (!path) {
    return;
  }
  const now = Date.now();
  const existing = readWorkspaceHistory();
  const deduped = [
    { path, projectName, lastUsedAt: now },
    ...existing.filter((item) => normalizeWorkspacePath(item.path) !== path),
  ]
    .slice(0, 20)
    .sort((a, b) => b.lastUsedAt - a.lastUsedAt);
  writeWorkspaceHistory(deduped);
}

function replaceSelectOptions(select, items) {
  const nextOptions = items
    .map(
      (item) =>
        `<option value="${escapeAttr(item.value)}" ${item.selected ? "selected" : ""}>${escapeHtml(
          item.label,
        )}</option>`,
    )
    .join("");
  if (select.innerHTML !== nextOptions) {
    select.innerHTML = nextOptions;
  }
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll('"', "&quot;");
}
