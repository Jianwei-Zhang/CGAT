import { createStore } from "./state/store.js";
import { openWorkspace } from "./services/workflow-api.js";
import { renderAppShell } from "./ui/shell/app-shell.js";
import { registerRoutes, renderCurrentRoute } from "./ui/shell/router.js";
import {
  buildProjectSwitchItems,
  buildWorkspaceSwitchItems,
  switchProjectFromShell,
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
    zipPath: "",
    workspaceRoot: "",
    extractedPath: "",
    openWorkspacePath: "",
    historyValidation: {},
    deleteConfirmOpen: false,
    deleteWithFiles: false,
    deleteTargets: [],
    inFlight: false,
    importRunId: null,
    importCancelling: false,
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
      expandedJobId: "",
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
store.subscribe((nextState) => {
  if (nextState.activeRoute !== lastRoute) {
    lastRoute = nextState.activeRoute;
    renderCurrentRoute(app, store);
  }
  const nextWorkspacePath = normalizeWorkspacePath(nextState.session.workspacePath);
  if (nextWorkspacePath && nextWorkspacePath !== lastSessionWorkspacePath) {
    appendWorkspaceHistory(nextWorkspacePath);
  }
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
  const projectSelect = document.querySelector("#session-project-select");
  const labels = getMessages(state, "shell");
  if (workspaceSelect) {
    const workspaceItems = buildWorkspaceSwitchItems({
      state,
      historyRecords: readWorkspaceHistory(),
      labels,
    });
    replaceSelectOptions(workspaceSelect, workspaceItems);
    workspaceSelect.disabled = workspaceItems.length === 1 && !workspaceItems[0]?.value;
  }
  if (projectSelect) {
    const projectItems = buildProjectSwitchItems({ state, labels });
    replaceSelectOptions(projectSelect, projectItems);
    projectSelect.disabled = projectItems.length <= 1;
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
  const projectSelect = root.querySelector("#session-project-select");

  workspaceSelect?.addEventListener("change", async () => {
    const nextWorkspacePath = normalizeWorkspacePath(workspaceSelect.value);
    const currentWorkspacePath = normalizeWorkspacePath(storeRef.getState().session.workspacePath);
    if (!nextWorkspacePath || nextWorkspacePath === currentWorkspacePath) {
      syncSessionHeader(storeRef.getState());
      return;
    }
    try {
      await switchWorkspaceFromShell(storeRef, nextWorkspacePath, { openWorkspace });
      window.dispatchEvent(new Event("gpm-next:route-refresh"));
    } catch (error) {
      const current = storeRef.getState();
      storeRef.setState({
        importer: {
          ...current.importer,
          inFlight: false,
          status: t(current, "importer.runtime.openFailedStatus"),
          summary: String(error?.message || error || ""),
        },
      });
    }
    syncSessionHeader(storeRef.getState());
  });

  projectSelect?.addEventListener("change", () => {
    const nextProjectId = Number(projectSelect.value || 0);
    const changed = switchProjectFromShell(storeRef, nextProjectId);
    syncSessionHeader(storeRef.getState());
    if (changed) {
      window.dispatchEvent(new Event("gpm-next:route-refresh"));
    }
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
    const matchedProject = options.existingProjects.find(
      (item) => Number(item.projectId) === Number(snapshot.projectId),
    );

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
        status: t(storeRef.getState(), "importer.runtime.sessionRestoredStatus"),
        summary: t(storeRef.getState(), "importer.runtime.sessionRestoredSummary"),
        stages: [...storeRef.getState().importer.stages, t(storeRef.getState(), "importer.runtime.sessionRestoredStage")],
      },
      initializer: {
        ...storeRef.getState().initializer,
        optionsLoaded: true,
        optionsError: "",
        packageMetadata: options.packageMetadata || storeRef.getState().initializer.packageMetadata,
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
      activeRoute: matchedProject ? "assembly" : "workspace",
    });
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  } catch {
    clearLastWorkspace();
    storeRef.setState({
      importer: {
        ...storeRef.getState().importer,
        inFlight: false,
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

function appendWorkspaceHistory(workspacePath) {
  const path = normalizeWorkspacePath(workspacePath);
  if (!path) {
    return;
  }
  const now = Date.now();
  const existing = readWorkspaceHistory();
  const deduped = [
    { path, lastUsedAt: now },
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
