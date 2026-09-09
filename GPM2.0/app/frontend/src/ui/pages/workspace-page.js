import {
  autoAssignChr,
  autoOrientContigs,
  autoOrientContigsForDataset,
  bootstrapProjectAssembly,
  listProjectInitializerOptions,
  requestAutoPipelineCancel,
  setProjectAutoPipelineDone,
  updateProject,
} from "../../services/workflow-api.js";
import { formatDateTime, formatNumber, getMessages, t as i18nT } from "../i18n/index.js";
import { buildEmptyProjectExportState } from "../shell/session-switchers.js";
import { normalizeFinalPathByChr } from "./assembly/final-path-state.js";
import { projectLabels } from "./projects-view.js";
import { projectIcon } from "./project-icons.js";
import { defaultProjectName } from "../../services/project-session.js";

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
    grtProjectView: {
      recipe: {},
      baselineFinalPathByChr: {},
      sourceCards: [],
      verification: {},
    },
    grtResultDisplayByChr: {},
    grtResultToast: null,
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

const AUTO_PIPELINE_CANCEL_ERROR = "__AUTO_PIPELINE_CANCELLED__";

export function renderWorkspacePage(state) {
  const initializer = state.initializer;
  const messages = getMessages(state, "workspace");
  const labels = projectLabels(state);
  const selectedProject = findProjectById(initializer.existingProjects, state.session.projectId);
  const editDraft = getEffectiveEditDraft(initializer, selectedProject);
  const editDirty = selectedProject ? isEditDirty(initializer, selectedProject, editDraft) : false;
  const busy = state.importer?.inFlight || initializer.autoPipelineRunning || initializer.updating;
  const renameOpen = initializer.renameProjectKey === `${state.session.workspacePath}:${selectedProject?.projectId}`;
  return `<section class="project-current">
    <div class="project-detail-overview">
      <div class="project-identity">
        <div class="project-title-row"><h2>${escapeHtml(selectedProject?.projectName || defaultProjectName(state.session.workspacePath))}</h2>
          ${selectedProject && !renameOpen ? `<button id="selected-project-rename-button" class="button project-icon-button" title="${labels.rename}" aria-label="${labels.rename}" ${busy ? "disabled" : ""}>${projectIcon("rename")}</button>` : ""}
        </div>
        <p class="project-path project-detail-path" title="${escapeAttr(state.session.workspacePath)}">${escapeHtml(state.session.workspacePath)}</p>
      </div>
      <button id="initializer-enter-assembly-button" class="button project-primary project-enter-assembly" ${!selectedProject || busy ? "disabled" : ""}>${messages.buttons.enterAssembly}${projectIcon("arrow")}</button>
    </div>
    ${selectedProject && renameOpen ? `<form class="project-rename-form" data-project-rename-form>
      <label for="selected-project-name-input">${messages.cards.projectName}</label>
      <div class="project-rename-controls"><input id="selected-project-name-input" type="text" value="${escapeAttr(editDraft.projectName)}" ${busy ? "disabled" : ""} />
        <button type="submit" id="selected-project-save-button" class="button project-icon-button project-primary" title="${labels.saved}" aria-label="${labels.saved}" ${busy || !editDirty ? "disabled" : ""}>${projectIcon("check")}</button>
        <button type="button" id="selected-project-rename-cancel" class="button project-icon-button" title="${labels.cancel}" aria-label="${labels.cancel}" ${busy ? "disabled" : ""}>${projectIcon("close")}</button>
      </div>
    </form>` : ""}
    ${initializer.existingProjects.length > 1 ? `<label class="project-legacy-picker">${labels.legacy}
      <select id="legacy-project-select" ${busy ? "disabled" : ""}><option value="">${labels.legacyProjects}</option>
        ${initializer.existingProjects.map(project => `<option value="${project.projectId}" ${selectedProject?.projectId === project.projectId ? "selected" : ""}>${escapeHtml(project.projectName)}</option>`).join("")}
      </select></label>` : ""}
    ${selectedProject ? renderSelectedProjectCard({ initializer, selectedProject, locale: state.locale, messages }) : ""}
    ${initializer.optionsError ? `<p class="error-text" role="alert">${escapeHtml(initializer.optionsError)}</p>` : ""}
  </section>
  ${initializer.autoPipelineModalOpen ? renderAutoPipelineModal(initializer, messages) : ""}`;
}

export function bindWorkspacePage(host, store) {
  const state = store.getState();
  const initializer = state.initializer;
  const selectedProject = findProjectById(initializer.existingProjects, state.session.projectId);

  const autoPipelineCloseButton = host.querySelector("#initializer-auto-pipeline-close-button");
  const enterAssemblyButton = host.querySelector("#initializer-enter-assembly-button");

  const editProjectNameInput = host.querySelector("#selected-project-name-input");
  const saveSelectedProjectButton = host.querySelector("#selected-project-save-button");
  const renameButton = host.querySelector("#selected-project-rename-button");
  const cancelRenameButton = host.querySelector("#selected-project-rename-cancel");
  const renameForm = host.querySelector("[data-project-rename-form]");
  const renameBusy = () => store.getState().importer?.inFlight || store.getState().initializer.updating || store.getState().initializer.autoPipelineRunning;
  renameButton?.addEventListener("click", () => {
    if (!selectedProject || renameBusy()) return;
    store.setState({ initializer: { ...store.getState().initializer,
      renameProjectKey: `${state.session.workspacePath}:${selectedProject.projectId}`,
      editProjectId: selectedProject.projectId, editProjectNameInput: selectedProject.projectName,
    } });
    rerender(host, store);
    host.querySelector("#selected-project-name-input")?.focus?.();
    host.querySelector("#selected-project-name-input")?.select?.();
  });
  const cancelRename = () => {
    if (renameBusy()) return;
    store.setState({ initializer: { ...store.getState().initializer, renameProjectKey: "", editProjectNameInput: selectedProject?.projectName || "" } });
    rerender(host, store);
    host.querySelector("#selected-project-rename-button")?.focus?.();
  };
  cancelRenameButton?.addEventListener("click", cancelRename);
  renameForm?.addEventListener("submit", async event => {
    event.preventDefault();
    if (!renameBusy()) await saveSelectedProject(host, store);
  });
  renameForm?.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); cancelRename(); }
  });

  autoPipelineCloseButton?.addEventListener("click", async () => {
    const current = store.getState().initializer;
    if (current.autoPipelineRunning) {
      const workspaceRoot = String(store.getState().session.workspacePath || "");
      const projectId = Number(store.getState().session.projectId || 0);
      const runId = String(current.autoPipelineRunId || "").trim();
      store.setState({
        initializer: {
          ...current,
          autoPipelineCancelRequested: true,
          summary: i18nT(store.getState(), "workspace.runtime.cancelAutoPipeline"),
        },
      });
      rerender(host, store);
      if (workspaceRoot && projectId > 0 && runId) {
        try {
          await requestAutoPipelineCancel({ workspaceRoot, projectId, runId });
        } catch {
          // keep local cancel flag; backend command may still stop at next frontend cancellation check
        }
      }
      return;
    }
    store.setState({
      initializer: {
        ...current,
        autoPipelineModalOpen: false,
      },
    });
    rerender(host, store);
  });

  enterAssemblyButton?.addEventListener("click", async () => {
    const next = store.getState();
    const project = findProjectById(next.initializer.existingProjects, next.session.projectId);
    if (!project) {
      return;
    }
    if (!project.autoPipelineDone) {
      await runAutoPipelineBeforeAssembly(host, store, project);
      return;
    }
    store.setState({ activeRoute: "assembly" });
    globalThis.window?.dispatchEvent?.(new Event("gpm-next:route-refresh"));
  });

  editProjectNameInput?.addEventListener("input", (event) => {
    const current = store.getState().initializer;
    const nextInitializer = {
      ...current,
      editProjectId: selectedProject?.projectId || current.editProjectId,
      editProjectNameInput: String(event.target.value || "").trim(),
    };
    store.setState({
      initializer: nextInitializer,
    });
    syncSelectedProjectSaveButton(saveSelectedProjectButton, nextInitializer, selectedProject);
  });

  saveSelectedProjectButton?.addEventListener("click", async event => {
    event.preventDefault?.();
    if (renameBusy()) return;
    await saveSelectedProject(host, store);
  });
}

function renderWorkspaceRecipeSummary({ recipe = {}, messages, referenceName = "" }) {
  const supportDatasets = Array.isArray(recipe.supportDatasets)
    ? recipe.supportDatasets.filter((value) => String(value || "").trim())
    : [];
  const fields = [];
  if (referenceName) {
    fields.push({ label: messages.cards.referenceGenome, value: referenceName });
  }
  fields.push(
    { label: messages.cards.primaryDataset, value: recipe.primaryDataset || "-" },
    { label: messages.cards.supportDataset, value: supportDatasets.join(", ") || "-" },
    {
      label: messages.cards.readsQc,
      value: recipe.readsQcEnabled ? messages.cards.enabled : messages.cards.disabled,
      valueClass: recipe.readsQcEnabled ? "is-enabled" : "is-disabled",
    },
  );
  return `
    <div class="workspace-recipe-summary" data-grt-recipe-summary="true">
      <div class="workspace-recipe-grid">
        ${fields
          .map(
            ({ label, value, valueClass = "" }) => `
              <div class="workspace-recipe-field">
                <span class="workspace-recipe-label">${label}</span>
                <span class="workspace-recipe-value${valueClass ? ` ${valueClass}` : ""}">${escapeHtml(value)}</span>
              </div>
            `,
          )
          .join("")}
      </div>
    </div>
  `;
}

function renderAutoPipelineModal(initializer, messages) {
  const rows = (initializer.autoPipelineSteps || [])
    .map((step) => {
      const stateClass = step.status || "pending";
      const icon = renderPipelineStepIcon(step.status);
      const detail = step.detail ? `<span class="muted">${escapeHtml(step.detail)}</span>` : "";
      return `<div class="pipeline-step-row ${stateClass}">
        <span class="pipeline-step-icon">${icon}</span>
        <span class="pipeline-step-label">${escapeHtml(step.label || step.id || "")}</span>
        ${detail}
      </div>`;
    })
    .join("");
  return `
    <div class="modal-overlay">
      <article class="card modal-dialog">
        <header class="page-header">
          <h4>${escapeHtml(initializer.autoPipelineTitle || messages.cards.autoPipelineTitle)}</h4>
          <button id="initializer-auto-pipeline-close-button" class="button ghost" type="button">${
            initializer.autoPipelineRunning ? messages.buttons.abort : messages.buttons.close
          }</button>
        </header>
        <div class="tool-grid">
          ${rows || `<p class="muted">${messages.cards.autoPipelineEmpty}</p>`}
        </div>
        <p class="muted">${escapeHtml(initializer.autoPipelineHint || messages.cards.autoPipelineHint)}</p>
      </article>
    </div>
  `;
}

function renderPipelineStepIcon(status) {
  if (status === "running") {
    return `<span class="pipeline-spinner" aria-hidden="true"></span>`;
  }
  if (status === "done") {
    return `<span class="pipeline-done" aria-hidden="true">&#10003;</span>`;
  }
  if (status === "error") {
    return `<span class="pipeline-error" aria-hidden="true">&#10007;</span>`;
  }
  if (status === "skipped") {
    return `<span class="pipeline-skipped" aria-hidden="true">-</span>`;
  }
  return `<span class="pipeline-pending" aria-hidden="true">&#9675;</span>`;
}

function renderSelectedProjectCard({ initializer, selectedProject, locale, messages }) {
  const recipe = initializer.grtRecipe || {};
  const referenceName = selectedProject.referenceName
    || initializer.references.find(
      (reference) => Number(reference.referenceGenomeId) === Number(selectedProject.referenceGenomeId),
    )?.name
    || "-";

  return `
    <div class="project-metadata">
      ${renderWorkspaceRecipeSummary({
        recipe: {
          ...recipe,
          primaryDataset: recipe.primaryDataset || selectedProject.primaryDatasetName || "-",
        },
        messages,
        referenceName,
      })}
      <p class="project-created muted">${projectLabels({ locale }).created}<span>${escapeHtml(formatCreatedAt(selectedProject.createdAt, locale))}</span></p>
    </div>
  `;
}

async function saveSelectedProject(host, store) {
  const state = store.getState();
  const workspaceRoot = state.session.workspacePath;
  const selectedProject = findProjectById(state.initializer.existingProjects, state.session.projectId);
  if (!workspaceRoot || !selectedProject) {
    return;
  }
  const draft = getEffectiveEditDraft(state.initializer, selectedProject);
  if (!isEditDirty(state.initializer, selectedProject, draft)) {
    return;
  }
  const appendedSupportDatasetIds = getProcessedProjectAppendedSupportDatasetIds(
    selectedProject,
    draft,
  );
  if (selectedProject.isProcessed && appendedSupportDatasetIds.length > 0) {
    await saveProcessedProjectWithAppendPipeline(
      host,
      store,
      selectedProject,
      draft,
      appendedSupportDatasetIds,
    );
    return;
  }
  if (
    !Number.isFinite(draft.chrAssignmentMinCoveragePercent) ||
    draft.chrAssignmentMinCoveragePercent < 0 ||
    draft.chrAssignmentMinCoveragePercent > 100
  ) {
    store.setState({
      initializer: {
        ...state.initializer,
        optionsError: "chr_assignment_min_coverage_percent must be between 0 and 100",
      },
    });
    rerender(host, store);
    return;
  }

  store.setState({
    initializer: {
      ...state.initializer,
      updating: true,
      optionsError: "",
      summary: i18nT(state, "workspace.runtime.savingProject", {
        projectName: selectedProject.projectName,
      }),
    },
  });
  rerender(host, store);

  try {
    const result = await updateProject({
      workspaceRoot,
      projectId: selectedProject.projectId,
      projectName: draft.projectName,
      referenceGenomeId: draft.referenceGenomeId,
      primaryDatasetId: draft.primaryDatasetId,
      supportDatasetIds: draft.supportDatasetIds,
      chrAssignmentMinCoveragePercent: draft.chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled: draft.phasedAssemblyEnabled,
      stateOrLocale: state,
    });
    const { nextProject, nextExistingProjects, nextDraft } = buildSavedSelectedProjectState(
      state.initializer.existingProjects,
      selectedProject,
      draft,
      result,
    );
    store.setState({
      session: {
        ...store.getState().session,
        projectName: nextProject.projectName || draft.projectName,
      },
      initializer: {
        ...store.getState().initializer,
        updating: false,
        renameProjectKey: "",
        existingProjects: nextExistingProjects,
        summary: i18nT(store.getState(), "workspace.runtime.projectSaved", {
          projectName: nextProject.projectName || draft.projectName,
        }),
        editProjectId: nextProject.projectId ?? null,
        editProjectNameInput: nextDraft.projectName,
        editReferenceId: String(nextDraft.referenceGenomeId),
        editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
        editSupportDatasetIds: [...nextDraft.supportDatasetIds],
        editChrAssignmentMinCoveragePercentInput: String(nextDraft.chrAssignmentMinCoveragePercent),
        editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
      },
    });
  } catch (error) {
    store.setState({
      initializer: {
        ...store.getState().initializer,
        updating: false,
        optionsError: String(error.message || error),
        summary: i18nT(store.getState(), "workspace.runtime.projectSaveFailed"),
      },
    });
  }
  rerender(host, store);
}

async function saveProcessedProjectWithAppendPipeline(
  host,
  store,
  selectedProject,
  draft,
  appendedSupportDatasetIds,
) {
  const state = store.getState();
  const workspaceRoot = state.session.workspacePath;
  const runId = Date.now();
  const steps = buildProcessedProjectAppendSteps(state, appendedSupportDatasetIds);
  store.setState({
    initializer: {
      ...state.initializer,
      updating: true,
      autoPipelineModalOpen: true,
      autoPipelineRunning: true,
      autoPipelineCanClose: true,
      autoPipelineSteps: steps,
      autoPipelineRunId: runId,
      autoPipelineCancelRequested: false,
      autoPipelineTitle: i18nT(state, "workspace.cards.processedUpdatePipelineTitle"),
      autoPipelineHint: i18nT(state, "workspace.cards.processedUpdatePipelineHint"),
      optionsError: "",
      summary: i18nT(state, "workspace.runtime.savingProject", {
        projectName: selectedProject.projectName,
      }),
    },
  });
  rerender(host, store);

  const isCancelled = () => {
    const current = store.getState().initializer;
    return (
      Number(current.autoPipelineRunId || 0) === Number(runId) &&
      Boolean(current.autoPipelineCancelRequested)
    );
  };
  const throwIfCancelled = () => {
    if (isCancelled()) {
      throw new Error(AUTO_PIPELINE_CANCEL_ERROR);
    }
  };
  const setStep = (stepId, patch) => {
    const current = store.getState().initializer;
    if (Number(current.autoPipelineRunId || 0) !== Number(runId)) {
      return;
    }
    store.setState({
      initializer: {
        ...current,
        autoPipelineSteps: (current.autoPipelineSteps || []).map((step) =>
          step.id === stepId ? { ...step, ...patch } : step,
        ),
      },
    });
    rerender(host, store);
  };

  try {
    throwIfCancelled();
    setStep("save_project", {
      status: "running",
      detail: i18nT(store.getState(), "workspace.pipeline.saveProjectRunning"),
    });
    const result = await updateProject({
      workspaceRoot,
      projectId: selectedProject.projectId,
      projectName: draft.projectName,
      referenceGenomeId: draft.referenceGenomeId,
      primaryDatasetId: draft.primaryDatasetId,
      supportDatasetIds: draft.supportDatasetIds,
      chrAssignmentMinCoveragePercent: draft.chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled: draft.phasedAssemblyEnabled,
      stateOrLocale: state,
    });
    const { nextProject, nextExistingProjects, nextDraft } = buildSavedSelectedProjectState(
      state.initializer.existingProjects,
      selectedProject,
      draft,
      result,
    );
    setStep("save_project", {
      status: "done",
      detail: i18nT(store.getState(), "workspace.pipeline.saveProjectDone"),
    });
    setStep("append_support", {
      status: "done",
      detail: i18nT(store.getState(), "workspace.pipeline.appendSupportDone", {
        datasetCount: appendedSupportDatasetIds.length,
      }),
    });
    store.setState({
      session: {
        ...store.getState().session,
        projectName: nextProject.projectName || draft.projectName,
      },
      initializer: {
        ...store.getState().initializer,
        existingProjects: nextExistingProjects,
        editProjectId: nextProject.projectId ?? null,
        editProjectNameInput: nextDraft.projectName,
        editReferenceId: String(nextDraft.referenceGenomeId),
        editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
        editSupportDatasetIds: [...nextDraft.supportDatasetIds],
        editChrAssignmentMinCoveragePercentInput: String(nextDraft.chrAssignmentMinCoveragePercent),
        editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
      },
    });

    throwIfCancelled();
    setStep("auto_orient_dataset", {
      status: "running",
      detail: i18nT(store.getState(), "workspace.pipeline.orientDatasetRunning", {
        datasetCount: appendedSupportDatasetIds.length,
      }),
    });
    const orientTotals = {
      orientedCtgCount: 0,
      flippedCtgCount: 0,
    };
    for (const datasetId of appendedSupportDatasetIds) {
      throwIfCancelled();
      const orient = await autoOrientContigsForDataset({
        workspaceRoot,
        projectId: selectedProject.projectId,
        datasetId,
        runId: String(runId),
      });
      orientTotals.orientedCtgCount += Number(orient.orientedCtgCount || 0);
      orientTotals.flippedCtgCount += Number(orient.flippedCtgCount || 0);
    }
    setStep("auto_orient_dataset", {
      status: "done",
      detail: i18nT(store.getState(), "workspace.pipeline.orientDone", {
        orientedCtgCount: orientTotals.orientedCtgCount,
        flippedCtgCount: orientTotals.flippedCtgCount,
      }),
    });

    store.setState({
      session: {
        ...store.getState().session,
        projectName: nextProject.projectName || draft.projectName,
      },
      initializer: {
        ...store.getState().initializer,
        updating: false,
        autoPipelineRunning: false,
        autoPipelineCanClose: true,
        autoPipelineModalOpen: true,
        autoPipelineRunId: null,
        autoPipelineCancelRequested: false,
        existingProjects: nextExistingProjects,
        summary: i18nT(store.getState(), "workspace.runtime.projectSaved", {
          projectName: nextProject.projectName || draft.projectName,
        }),
        editProjectId: nextProject.projectId ?? null,
        editProjectNameInput: nextDraft.projectName,
        editReferenceId: String(nextDraft.referenceGenomeId),
        editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
        editSupportDatasetIds: [...nextDraft.supportDatasetIds],
        editChrAssignmentMinCoveragePercentInput: String(nextDraft.chrAssignmentMinCoveragePercent),
        editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
      },
    });
    rerender(host, store);
  } catch (error) {
    const failedMessage = String(error.message || error);
    const normalizedMessage = failedMessage.toLowerCase();
    const isCancelledError =
      failedMessage === AUTO_PIPELINE_CANCEL_ERROR ||
      normalizedMessage.includes("auto pipeline cancelled");
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        updating: false,
        autoPipelineRunning: false,
        autoPipelineCanClose: true,
        autoPipelineModalOpen: true,
        autoPipelineSteps: (current.autoPipelineSteps || []).map((step) =>
          step.status === "pending" || step.status === "running"
            ? {
                ...step,
                status: isCancelledError ? "skipped" : "error",
                detail: isCancelledError
                  ? i18nT(store.getState(), "workspace.pipeline.cancelled")
                  : failedMessage,
              }
            : step,
        ),
        autoPipelineRunId: null,
        autoPipelineCancelRequested: false,
        optionsError: isCancelledError ? "" : failedMessage,
        summary: isCancelledError
          ? i18nT(store.getState(), "workspace.runtime.autoPipelineStopped")
          : i18nT(store.getState(), "workspace.runtime.projectSaveFailed"),
      },
    });
    rerender(host, store);
  }
}

function buildSavedSelectedProjectState(existingProjects, selectedProject, draft, result) {
  const refreshedProjects = Array.isArray(result.existingProjects) ? result.existingProjects : [];
  const refreshedProject = findProjectById(refreshedProjects, selectedProject.projectId);
  const nextProject =
    refreshedProject ||
    {
      ...selectedProject,
      projectName: String(result.projectName || draft.projectName || selectedProject.projectName || "").trim(),
      referenceGenomeId: Number(
        result.referenceGenomeId ?? draft.referenceGenomeId ?? selectedProject.referenceGenomeId ?? 0,
      ),
      primaryDatasetId: Number(
        result.primaryDatasetId ?? draft.primaryDatasetId ?? selectedProject.primaryDatasetId ?? 0,
      ),
      supportDatasetIds: normalizeSupportDatasetIds(
        Array.isArray(result.supportDatasetIds) && result.supportDatasetIds.length
          ? result.supportDatasetIds
          : draft.supportDatasetIds,
        result.primaryDatasetId ?? draft.primaryDatasetId ?? selectedProject.primaryDatasetId,
      ),
      chrAssignmentMinCoveragePercent: Number(
        result.chrAssignmentMinCoveragePercent ??
          draft.chrAssignmentMinCoveragePercent ??
          selectedProject.chrAssignmentMinCoveragePercent ??
          60,
      ),
      phasedAssemblyEnabled:
        typeof result.phasedAssemblyEnabled === "boolean"
          ? result.phasedAssemblyEnabled
          : Boolean(draft.phasedAssemblyEnabled),
      isProcessed: Boolean(result.isProcessed ?? selectedProject.isProcessed),
    };
  const nextExistingProjects =
    refreshedProjects.length && refreshedProject
      ? refreshedProjects
      : existingProjects.map((project) =>
          Number(project.projectId) === Number(selectedProject.projectId)
            ? { ...project, ...nextProject, supportDatasetIds: [...nextProject.supportDatasetIds] }
            : project,
        );
  return {
    nextProject,
    nextExistingProjects,
    nextDraft: buildEditDraftFromProject(nextProject),
  };
}

async function runAutoPipelineBeforeAssembly(host, store, project) {
  const state = store.getState();
  const workspaceRoot = state.session.workspacePath;
  if (!workspaceRoot || !project?.projectId) {
    return;
  }

  let latestProject = project;
  try {
    const latestOptions = await listProjectInitializerOptions({ workspaceRoot });
    const refreshedProjects = latestOptions.existingProjects || [];
    store.setState({
      initializer: {
        ...store.getState().initializer,
        packageMetadata: normalizePackageMetadata(latestOptions.packageMetadata),
        grtRecipe: latestOptions.grtRecipe || store.getState().initializer.grtRecipe,
        existingProjects: refreshedProjects,
      },
    });
    const matched = findProjectById(refreshedProjects, project.projectId);
    if (matched) {
      latestProject = matched;
      const nextDraft = buildEditDraftFromProject(matched);
      store.setState({
        initializer: {
          ...store.getState().initializer,
          editProjectId: matched.projectId,
          editProjectNameInput: nextDraft.projectName,
          editReferenceId: String(nextDraft.referenceGenomeId),
          editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
          editSupportDatasetIds: [...nextDraft.supportDatasetIds],
          editChrAssignmentMinCoveragePercentInput: String(nextDraft.chrAssignmentMinCoveragePercent),
          editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
        },
      });
      rerender(host, store);
    }
  } catch {
    // ignore refresh failures; continue with current in-memory project snapshot
  }

  const needsBootstrap = !latestProject.isProcessed;
  const steps = buildAutoPipelineSteps(store.getState(), { needsBootstrap });
  const runId = Date.now();
  store.setState({
    initializer: {
      ...store.getState().initializer,
      autoPipelineModalOpen: true,
      autoPipelineRunning: true,
      autoPipelineCanClose: true,
      autoPipelineSteps: steps,
      autoPipelineRunId: runId,
      autoPipelineCancelRequested: false,
      autoPipelineTitle: "",
      autoPipelineHint: "",
      optionsError: "",
      summary: i18nT(store.getState(), "workspace.runtime.autoPipelineRunning", {
        projectName: latestProject.projectName,
      }),
    },
  });
  rerender(host, store);

  const isCancelled = () => {
    const current = store.getState().initializer;
    return (
      Number(current.autoPipelineRunId || 0) === Number(runId) &&
      Boolean(current.autoPipelineCancelRequested)
    );
  };
  const throwIfCancelled = () => {
    if (isCancelled()) {
      throw new Error(AUTO_PIPELINE_CANCEL_ERROR);
    }
  };

  const setStep = (stepId, patch) => {
    const current = store.getState().initializer;
    if (Number(current.autoPipelineRunId || 0) !== Number(runId)) {
      return;
    }
    const nextSteps = (current.autoPipelineSteps || []).map((step) =>
      step.id === stepId ? { ...step, ...patch } : step,
    );
    store.setState({
      initializer: {
        ...current,
        autoPipelineSteps: nextSteps,
      },
    });
    rerender(host, store);
  };

  try {
    throwIfCancelled();
    if (needsBootstrap) {
      setStep("bootstrap", { status: "running", detail: i18nT(store.getState(), "workspace.pipeline.bootstrapRunning") });
      try {
        const bootstrap = await bootstrapProjectAssembly({
          workspaceRoot,
          projectId: latestProject.projectId,
          runId: String(runId),
        });
        setStep("bootstrap", {
          status: "done",
          detail: i18nT(store.getState(), "workspace.pipeline.bootstrapDone", {
            assemblySeqCount: bootstrap.assemblySeqCount,
            assemblyCtgCount: bootstrap.assemblyCtgCount,
          }),
        });
      } catch (error) {
        const bootstrapError = String(error.message || error);
        if (bootstrapError.includes("already has assembly_seq rows")) {
          setStep("bootstrap", {
            status: "skipped",
            detail: i18nT(store.getState(), "workspace.pipeline.bootstrapSkippedExisting"),
          });
        } else {
          throw error;
        }
      }
      throwIfCancelled();
    }

    if (!isChrAssignmentServerOwned(store.getState().initializer)) {
      throwIfCancelled();
      setStep("auto_assign_chr", { status: "running", detail: i18nT(store.getState(), "workspace.pipeline.assignRunning") });
      const assign = await autoAssignChr({
        workspaceRoot,
        projectId: latestProject.projectId,
        runId: String(runId),
      });
      setStep("auto_assign_chr", {
        status: "done",
        detail: i18nT(store.getState(), "workspace.pipeline.assignDone", {
          assignedCount: assign.assignedCount,
          noEvidenceCount: assign.noEvidenceCount,
        }),
      });
      throwIfCancelled();
    }

    throwIfCancelled();
    setStep("auto_orient", { status: "running", detail: i18nT(store.getState(), "workspace.pipeline.orientRunning") });
    const orient = await autoOrientContigs({
      workspaceRoot,
      projectId: latestProject.projectId,
      runId: String(runId),
    });
    setStep("auto_orient", {
      status: "done",
      detail: i18nT(store.getState(), "workspace.pipeline.orientDone", {
        orientedCtgCount: orient.orientedCtgCount,
        flippedCtgCount: orient.flippedCtgCount,
      }),
    });
    throwIfCancelled();

    const marked = await setProjectAutoPipelineDone({
      workspaceRoot,
      projectId: latestProject.projectId,
      done: true,
    });
    const refreshedProject = findProjectById(
      marked.existingProjects || [],
      latestProject.projectId,
    );
    const nextDraft = buildEditDraftFromProject(refreshedProject);
    store.setState({
      session: {
        ...store.getState().session,
        projectName: refreshedProject?.projectName || latestProject.projectName || "",
      },
      initializer: {
        ...store.getState().initializer,
        autoPipelineRunning: false,
        autoPipelineCanClose: true,
        autoPipelineModalOpen: false,
        autoPipelineRunId: null,
        autoPipelineCancelRequested: false,
        existingProjects: marked.existingProjects || [],
        summary: i18nT(store.getState(), "workspace.runtime.autoPipelineDone", {
          projectName: refreshedProject?.projectName || latestProject.projectName,
        }),
        editProjectId: refreshedProject?.projectId ?? latestProject.projectId,
        editProjectNameInput: nextDraft.projectName,
        editReferenceId: String(nextDraft.referenceGenomeId),
        editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
        editSupportDatasetIds: [...nextDraft.supportDatasetIds],
        editChrAssignmentMinCoveragePercentInput: String(nextDraft.chrAssignmentMinCoveragePercent),
        editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
      },
      assembly: {
        ...store.getState().assembly,
        ...buildEmptyAssemblyViewState(store.getState()),
      },
      activeRoute: "assembly",
    });
    globalThis.window?.dispatchEvent?.(new Event("gpm-next:route-refresh"));
  } catch (error) {
    const failedMessage = String(error.message || error);
    const normalizedMessage = failedMessage.toLowerCase();
    const isCancelledError =
      failedMessage === AUTO_PIPELINE_CANCEL_ERROR ||
      normalizedMessage.includes("auto pipeline cancelled");
    if (isCancelledError) {
      const current = store.getState().initializer;
      if (Number(current.autoPipelineRunId || 0) !== Number(runId)) {
        return;
      }
      const nextSteps = (current.autoPipelineSteps || []).map((step) =>
        step.status === "pending" || step.status === "running"
          ? { ...step, status: "skipped", detail: i18nT(store.getState(), "workspace.pipeline.cancelled") }
          : step,
      );
      store.setState({
        initializer: {
          ...current,
          autoPipelineRunning: false,
          autoPipelineCanClose: true,
          autoPipelineModalOpen: true,
          autoPipelineSteps: nextSteps,
          autoPipelineRunId: null,
          autoPipelineCancelRequested: false,
          optionsError: "",
          summary: i18nT(store.getState(), "workspace.runtime.autoPipelineStopped"),
        },
      });
      rerender(host, store);
      return;
    }
    const current = store.getState().initializer;
    const nextSteps = (current.autoPipelineSteps || []).map((step) =>
      step.status === "running"
        ? { ...step, status: "error", detail: failedMessage }
        : step,
    );
    store.setState({
      initializer: {
        ...current,
        autoPipelineRunning: false,
        autoPipelineCanClose: true,
        autoPipelineModalOpen: true,
        autoPipelineSteps: nextSteps,
        autoPipelineRunId: null,
        autoPipelineCancelRequested: false,
        optionsError: failedMessage,
        summary: i18nT(store.getState(), "workspace.runtime.autoPipelineFailed"),
      },
    });
    rerender(host, store);
    return;
  }

  rerender(host, store);
}

function findProjectById(existingProjects, projectId) {
  if (!Array.isArray(existingProjects) || !projectId) {
    return null;
  }
  return (
    existingProjects.find((project) => Number(project.projectId) === Number(projectId)) || null
  );
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

function getEffectiveEditDraft(initializer, selectedProject) {
  if (!selectedProject) {
    return buildEditDraftFromProject(null);
  }
  const source = buildEditDraftFromProject(selectedProject);
  if (Number(initializer.editProjectId || 0) !== Number(selectedProject.projectId || 0)) {
    return source;
  }
  return {
    ...source,
    projectName: String(initializer.editProjectNameInput || "").trim(),
  };
}

function normalizePackageMetadata(packageMetadata) {
  return {
    packageMode: String(packageMetadata?.packageMode || "fast"),
    sequenceLayout: String(packageMetadata?.sequenceLayout || "partitioned"),
    preassignedChr: true,
    chrAssignmentMinCoveragePercent: Number(
      packageMetadata?.chrAssignmentMinCoveragePercent ?? 60,
    ),
    selfAlignmentScope: String(packageMetadata?.selfAlignmentScope || "chr_partition"),
    crossAlignmentScope: String(packageMetadata?.crossAlignmentScope || "chr_partition"),
  };
}

function isChrAssignmentServerOwned(initializer) {
  return Boolean(normalizePackageMetadata(initializer?.packageMetadata).preassignedChr);
}

function getServerChrAssignmentThreshold(initializer) {
  const numeric = Number(
    normalizePackageMetadata(initializer?.packageMetadata).chrAssignmentMinCoveragePercent,
  );
  return Number.isFinite(numeric) ? numeric : 60;
}

function getChrAssignmentThresholdInputValue(initializer) {
  return isChrAssignmentServerOwned(initializer)
    ? getServerChrAssignmentThreshold(initializer)
    : initializer.chrAssignmentMinCoveragePercentInput ?? "60";
}

export function buildAutoPipelineSteps(stateOrLocale, { needsBootstrap = true } = {}) {
  const messagesState = stateOrLocale;
  const serverOwned = isChrAssignmentServerOwned(messagesState?.initializer);
  return [
    {
      id: "bootstrap",
      label: i18nT(messagesState, "workspace.pipeline.bootstrapLabel"),
      status: needsBootstrap ? "pending" : "skipped",
      detail: needsBootstrap ? "" : i18nT(messagesState, "workspace.pipeline.bootstrapSkipped"),
    },
    {
      id: "auto_assign_chr",
      label: i18nT(messagesState, "workspace.pipeline.autoAssignLabel"),
      status: serverOwned ? "skipped" : "pending",
      detail: serverOwned
        ? i18nT(messagesState, "workspace.pipeline.assignSkippedImported")
        : "",
    },
    {
      id: "auto_orient",
      label: i18nT(messagesState, "workspace.pipeline.autoOrientLabel"),
      status: "pending",
      detail: "",
    },
  ];
}

function buildProcessedProjectAppendSteps(stateOrLocale, appendedSupportDatasetIds) {
  return [
    {
      id: "save_project",
      label: i18nT(stateOrLocale, "workspace.pipeline.saveProjectLabel"),
      status: "pending",
      detail: "",
    },
    {
      id: "append_support",
      label: i18nT(stateOrLocale, "workspace.pipeline.appendSupportLabel"),
      status: "pending",
      detail: i18nT(stateOrLocale, "workspace.pipeline.appendSupportPending", {
        datasetCount: appendedSupportDatasetIds.length,
      }),
    },
    {
      id: "auto_orient_dataset",
      label: i18nT(stateOrLocale, "workspace.pipeline.autoOrientNewDatasetLabel"),
      status: "pending",
      detail: "",
    },
  ];
}

function normalizeChrAssignmentThreshold(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : Number.NaN;
}

function clampChrAssignmentThresholdInput(value, fallbackValue = 60) {
  const fallback = normalizeChrAssignmentThreshold(fallbackValue);
  const resolvedFallback = Number.isFinite(fallback)
    ? Math.max(0, Math.min(100, fallback))
    : 60;
  const numeric = normalizeChrAssignmentThreshold(value);
  if (!Number.isFinite(numeric)) {
    return String(resolvedFallback);
  }
  return String(Math.max(0, Math.min(100, numeric)));
}

function normalizeSupportDatasetIds(ids, primaryDatasetId) {
  const primaryId = Number(primaryDatasetId || 0);
  const seen = new Set();
  const normalized = [];
  for (const raw of ids || []) {
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) {
      continue;
    }
    if (id === primaryId || seen.has(id)) {
      continue;
    }
    seen.add(id);
    normalized.push(id);
  }
  return normalized;
}

function mergeAppendOnlySupportDatasetIds(existingIds, draftIds, primaryDatasetId) {
  const merged = normalizeSupportDatasetIds(existingIds || [], primaryDatasetId);
  const seen = new Set(merged);
  for (const id of normalizeSupportDatasetIds(draftIds || [], primaryDatasetId)) {
    if (!seen.has(id)) {
      seen.add(id);
      merged.push(id);
    }
  }
  return merged;
}

function getProcessedProjectAppendedSupportDatasetIds(selectedProject, draft) {
  if (!selectedProject?.isProcessed) {
    return [];
  }
  const existing = new Set(
    normalizeSupportDatasetIds(
      selectedProject.supportDatasetIds || [],
      selectedProject.primaryDatasetId,
    ),
  );
  return normalizeSupportDatasetIds(draft.supportDatasetIds || [], draft.primaryDatasetId)
    .filter((datasetId) => !existing.has(datasetId));
}

function isEditDirty(initializer, project, draft) {
  if (!project || !draft) {
    return false;
  }
  const source = buildEditDraftFromProject(project);
  return source.projectName !== String(draft.projectName || "").trim();
}

function syncSelectedProjectSaveButton(button, initializer, selectedProject) {
  if (!button) {
    return;
  }
  const draft = getEffectiveEditDraft(initializer, selectedProject);
  button.disabled = Boolean(initializer.updating || !isEditDirty(initializer, selectedProject, draft));
}

function sameNumberArray(left, right) {
  const a = (left || []).map((value) => Number(value));
  const b = (right || []).map((value) => Number(value));
  if (a.length !== b.length) {
    return false;
  }
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) {
      return false;
    }
  }
  return true;
}

function formatDatasetOptionLabel(messages, stateOrLocale, dataset) {
  const name = String(dataset?.name || dataset?.label || "").trim();
  const contigCount = normalizeNonNegativeInt(dataset?.contigCount);
  const totalLengthBp = normalizeNonNegativeInt(dataset?.totalLengthBp);
  return i18nT(stateOrLocale, "workspace.page.datasetOptionLabel", {
    name,
    contigCount: formatNumber(stateOrLocale, contigCount),
    totalLengthBp: formatNumber(stateOrLocale, totalLengthBp),
  });
}

function normalizeNonNegativeInt(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return 0;
  }
  return Math.trunc(numeric);
}

function formatCreatedAt(value, locale = "zh") {
  const raw = String(value || "").trim();
  if (!raw) {
    return "-";
  }
  const seconds = Number(raw);
  if (Number.isFinite(seconds) && seconds > 0) {
    const date = new Date(seconds * 1000);
    if (!Number.isNaN(date.getTime())) {
      return formatDateTime(locale, date);
    }
  }
  const date = new Date(raw);
  if (!Number.isNaN(date.getTime())) return formatDateTime(locale, date);
  return raw;
}

function rerender(host, store) {
  const routeHost = host.closest("#route-host");
  if (!routeHost) {
    return;
  }
  globalThis.window?.dispatchEvent?.(new Event("gpm-next:route-refresh"));
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
