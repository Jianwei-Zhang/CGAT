import { t as i18nT } from "../i18n/index.js";
import {
  clearAssemblySessionCache,
  rememberAssemblyState,
  restoreAssemblyState,
} from "./assembly-session-cache.js";

function normalizeWorkspacePath(value) {
  return String(value || "").trim();
}

function normalizeProjectId(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function findProjectById(existingProjects, projectId) {
  const normalizedId = normalizeProjectId(projectId);
  if (!Array.isArray(existingProjects) || !normalizedId) {
    return null;
  }
  return existingProjects.find((project) => Number(project.projectId) === normalizedId) || null;
}

function normalizeSupportDatasetIds(ids, primaryDatasetId) {
  const primaryId = Number(primaryDatasetId || 0);
  const seen = new Set();
  const normalized = [];
  for (const raw of ids || []) {
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0 || id === primaryId || seen.has(id)) {
      continue;
    }
    seen.add(id);
    normalized.push(id);
  }
  return normalized;
}

function buildEditDraftFromProject(project) {
  if (!project) {
    return {
      projectName: "",
      referenceGenomeId: "",
      primaryDatasetId: "",
      supportDatasetIds: [],
      chrAssignmentMinCoveragePercent: 60,
      phasedAssemblyEnabled: false,
    };
  }
  return {
    projectName: String(project.projectName || "").trim(),
    referenceGenomeId: Number(project.referenceGenomeId || 0),
    primaryDatasetId: Number(project.primaryDatasetId || 0),
    supportDatasetIds: normalizeSupportDatasetIds(project.supportDatasetIds || [], project.primaryDatasetId),
    chrAssignmentMinCoveragePercent: Number(project.chrAssignmentMinCoveragePercent ?? 60),
    phasedAssemblyEnabled: Boolean(project.phasedAssemblyEnabled),
  };
}

function buildEmptyAssemblyViewState(stateOrLocale) {
  return {
    loading: false,
    bootstrapping: false,
    summary: i18nT(stateOrLocale, "workspace.runtime.assemblySummary"),
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
      selectedTrackARole: "",
      selectedTrackBRole: "",
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
      message: "",
      error: "",
      summary: null,
    },
    error: "",
  };
}

export function buildEmptyProjectExportState() {
  return {
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
  };
}

export function buildWorkspaceSwitchItems({ state, historyRecords = [], labels }) {
  const currentPath = normalizeWorkspacePath(state?.session?.workspacePath);
  const seen = new Set();
  const items = [];
  if (!currentPath) {
    items.push({
      value: "",
      label: labels?.notOpened || "",
      selected: true,
    });
  }
  const candidates = [
    currentPath ? { path: currentPath } : null,
    ...historyRecords,
  ];
  for (const record of candidates) {
    const path = normalizeWorkspacePath(record?.path);
    if (!path || seen.has(path)) {
      continue;
    }
    seen.add(path);
    items.push({
      value: path,
      label: path,
      selected: path === currentPath,
    });
  }
  return items;
}

export function buildProjectSwitchItems({ state, labels }) {
  const currentProjectId = normalizeProjectId(state?.session?.projectId);
  const projects = Array.isArray(state?.initializer?.existingProjects)
    ? state.initializer.existingProjects
    : [];
  return [
    {
      value: "",
      label: labels?.noProjectSelected || "",
      selected: !currentProjectId,
    },
    ...projects.map((project) => ({
      value: String(project.projectId || ""),
      label: String(project.projectName || project.projectId || "").trim(),
      selected: Number(project.projectId) === currentProjectId,
    })),
  ];
}

export async function switchWorkspaceFromShell(store, workspaceRoot, { openWorkspace }) {
  const normalizedPath = normalizeWorkspacePath(workspaceRoot);
  if (!normalizedPath || typeof openWorkspace !== "function") {
    return false;
  }
  const options = await openWorkspace({ workspaceRoot: normalizedPath });
  clearAssemblySessionCache();
  const current = store.getState();
  const references = Array.isArray(options?.references) ? options.references : [];
  const datasets = Array.isArray(options?.datasets) ? options.datasets : [];
  const existingProjects = Array.isArray(options?.existingProjects) ? options.existingProjects : [];
  const packageMetadata = options?.packageMetadata || current.initializer.packageMetadata;
  store.setState({
    activeRoute: "workspace",
    session: {
      ...current.session,
      workspacePath: normalizedPath,
      projectId: null,
      projectName: "",
    },
    importer: {
      ...current.importer,
      inFlight: false,
      workspaceRoot: normalizedPath,
      openWorkspacePath: normalizedPath,
      historyValidation: {},
      deleteConfirmOpen: false,
      deleteWithFiles: false,
      deleteTargets: [],
      status: i18nT(current, "importer.runtime.workspaceLoadedStatus"),
      summary: i18nT(current, "importer.runtime.workspaceLoadedSummary"),
    },
    initializer: {
      ...current.initializer,
      optionsLoaded: true,
      optionsError: "",
      packageMetadata,
      references,
      datasets,
      existingProjects,
      selectedReferenceId: references[0]?.referenceGenomeId || "",
      selectedPrimaryDatasetId: datasets[0]?.datasetId || "",
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
    assembly: {
      ...current.assembly,
      ...buildEmptyAssemblyViewState(current),
    },
    projectExport: buildEmptyProjectExportState(),
  });
  return true;
}

export function switchProjectFromShell(store, projectId) {
  const current = store.getState();
  const selected = findProjectById(current.initializer?.existingProjects, projectId);
  if (!selected) {
    return false;
  }
  rememberAssemblyState(current);
  const nextDraft = buildEditDraftFromProject(selected);
  const nextSession = {
    ...current.session,
    projectId: selected.projectId,
    projectName: selected.projectName || "",
  };
  const fallbackAssembly = {
    ...current.assembly,
    ...buildEmptyAssemblyViewState(current),
  };
  const nextAssembly = restoreAssemblyState(
    {
      ...current,
      session: nextSession,
    },
    fallbackAssembly,
  );
  store.setState({
    session: nextSession,
    initializer: {
      ...current.initializer,
      optionsError: "",
      summary: i18nT(current, "workspace.runtime.selectedProjectSummary", {
        projectName: selected.projectName,
        createdAt: selected.createdAt || "-",
      }),
      editProjectId: selected.projectId,
      editProjectNameInput: nextDraft.projectName,
      editReferenceId: String(nextDraft.referenceGenomeId),
      editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
      editSupportDatasetIds: [...nextDraft.supportDatasetIds],
      editChrAssignmentMinCoveragePercentInput: String(nextDraft.chrAssignmentMinCoveragePercent),
      editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
    },
    assembly: nextAssembly,
    projectExport: buildEmptyProjectExportState(),
  });
  return true;
}
