import {
  autoAssignChr,
  autoOrientContigs,
  autoOrientContigsForDataset,
  bootstrapProjectAssembly,
  deleteProject,
  initializeProject,
  listProjectInitializerOptions,
  requestAutoPipelineCancel,
  setProjectAutoPipelineDone,
  updateProject,
} from "../../services/workflow-api.js";
import { formatDateTime, formatNumber, getMessages, t as i18nT } from "../i18n/index.js";
import {
  rememberAssemblyState,
  restoreAssemblyState,
} from "../shell/assembly-session-cache.js";
import { buildEmptyProjectExportState } from "../shell/session-switchers.js";

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
  const selectedProject = findProjectById(initializer.existingProjects, state.session.projectId);
  const canEnterAssembly = Boolean(selectedProject?.projectId);
  const editDraft = getEffectiveEditDraft(initializer, selectedProject);
  const editDirty = selectedProject ? isEditDirty(initializer, selectedProject, editDraft) : false;

  const existingProjectList = initializer.existingProjects.length
    ? initializer.existingProjects
        .map(
          (project) =>
            `<div class="project-list-row">
              <button class="list-item-button project-select-button ${
                state.session.projectId === project.projectId ? "is-active" : ""
              }" data-project-select-id="${project.projectId}" data-project-name="${escapeAttr(
                project.projectName,
              )}">
                ${escapeHtml(project.projectName)}
                <span class="muted">${messages.page.createdAt}${escapeHtml(formatCreatedAt(project.createdAt, state.locale))}</span>
              </button>
              <button class="button tiny icon-button danger" title="${escapeAttr(messages.buttons.deleteProject)}" data-project-delete-id="${project.projectId}" data-project-name="${escapeAttr(project.projectName)}">&#128465;</button>
            </div>`,
        )
        .join("")
    : messages.runtime.emptyProjects;

  return `
    <section class="page">
      <header class="page-header">
        <div>
          <p class="kicker">${messages.page.kicker}</p>
          <h3>${messages.page.title}</h3>
        </div>
        <div class="inline-input">
          <button id="initializer-open-create-modal-button" class="button">${messages.buttons.createProject}</button>
          <button id="initializer-enter-assembly-button" class="button ghost" ${
            canEnterAssembly ? "" : "disabled"
          }>${messages.buttons.enterAssembly}</button>
        </div>
      </header>

      <div class="card-grid two">
        <article class="card workspace-existing-card">
          <h4>${messages.cards.existingProjects}</h4>
          <div class="list ${initializer.existingProjects.length ? "" : "muted"}">${existingProjectList}</div>
        </article>
        ${
          selectedProject
            ? renderSelectedProjectCard({
                initializer,
                selectedProject,
                editDraft,
                editDirty,
                locale: state.locale,
                messages,
              })
            : ""
        }
      </div>

      <p class="muted">${escapeHtml(initializer.summary)}</p>
      ${initializer.optionsError ? `<p class="error-text">${escapeHtml(initializer.optionsError)}</p>` : ""}
    </section>
    ${initializer.createModalOpen ? renderCreateProjectModal(initializer, messages, state.locale) : ""}
    ${initializer.autoPipelineModalOpen ? renderAutoPipelineModal(initializer, messages) : ""}
  `;
}

export function bindWorkspacePage(host, store) {
  const state = store.getState();
  const initializer = state.initializer;
  const selectedProject = findProjectById(initializer.existingProjects, state.session.projectId);

  const openCreateModalButton = host.querySelector("#initializer-open-create-modal-button");
  const createModalCloseButton = host.querySelector("#initializer-create-modal-close-button");
  const createModalCancelButton = host.querySelector("#initializer-create-modal-cancel-button");
  const createProjectConfirmButton = host.querySelector("#initializer-create-project-confirm-button");
  const autoPipelineCloseButton = host.querySelector("#initializer-auto-pipeline-close-button");
  const enterAssemblyButton = host.querySelector("#initializer-enter-assembly-button");

  const createProjectNameInput = host.querySelector("#initializer-project-name-input");
  const createReferenceSelect = host.querySelector("#initializer-reference-select");
  const createPrimaryDatasetSelect = host.querySelector("#initializer-primary-dataset-select");
  const createSupportDatasetList = host.querySelector("#initializer-support-dataset-list");
  const createChrAssignmentThresholdInput = host.querySelector(
    "#initializer-chr-assignment-threshold-input",
  );
  const createPhasedAssemblyCheckbox = host.querySelector(
    "#initializer-phased-assembly-enabled-input",
  );

  const projectSelectButtons = host.querySelectorAll("[data-project-select-id]");
  const projectDeleteButtons = host.querySelectorAll("[data-project-delete-id]");

  const editProjectNameInput = host.querySelector("#selected-project-name-input");
  const editReferenceSelect = host.querySelector("#selected-project-reference-select");
  const editPrimaryDatasetSelect = host.querySelector("#selected-project-primary-dataset-select");
  const editSupportDatasetList = host.querySelector("#selected-project-support-dataset-list");
  const editChrAssignmentThresholdInput = host.querySelector(
    "#selected-project-chr-assignment-threshold-input",
  );
  const editPhasedAssemblyCheckbox = host.querySelector(
    "#selected-project-phased-assembly-enabled-input",
  );
  const saveSelectedProjectButton = host.querySelector("#selected-project-save-button");

  openCreateModalButton?.addEventListener("click", () => {
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        createModalOpen: true,
        optionsError: "",
        phasedAssemblyEnabledInput: false,
      },
    });
    rerender(host, store);
  });

  createModalCloseButton?.addEventListener("click", () => {
    closeCreateModal(host, store);
  });
  createModalCancelButton?.addEventListener("click", () => {
    closeCreateModal(host, store);
  });

  createProjectConfirmButton?.addEventListener("click", async () => {
    await createProject(host, store);
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
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
  });

  createProjectNameInput?.addEventListener("input", (event) => {
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        projectNameInput: String(event.target.value || "").trim(),
      },
    });
  });

  createReferenceSelect?.addEventListener("change", (event) => {
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        selectedReferenceId: String(event.target.value || ""),
      },
    });
  });

  createPrimaryDatasetSelect?.addEventListener("change", (event) => {
    const nextPrimary = String(event.target.value || "");
    const current = store.getState().initializer;
    const nextSupport = (current.selectedSupportDatasetIds || []).filter(
      (id) => String(id) !== nextPrimary,
    );
    store.setState({
      initializer: {
        ...current,
        selectedPrimaryDatasetId: nextPrimary,
        selectedSupportDatasetIds: nextSupport,
      },
    });
    rerender(host, store);
  });

  createSupportDatasetList?.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const current = store.getState().initializer;
      const datasetId = Number(checkbox.dataset.supportDatasetId);
      const has = (current.selectedSupportDatasetIds || []).includes(datasetId);
      const nextSupport = has
        ? current.selectedSupportDatasetIds.filter((id) => id !== datasetId)
        : [...current.selectedSupportDatasetIds, datasetId];
      store.setState({
        initializer: {
          ...current,
          selectedSupportDatasetIds: nextSupport,
        },
      });
    });
  });

  createChrAssignmentThresholdInput?.addEventListener("input", (event) => {
    if (isChrAssignmentServerOwned(store.getState().initializer)) {
      return;
    }
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        chrAssignmentMinCoveragePercentInput: String(event.target.value || "").trim(),
      },
    });
  });
  const commitCreateChrAssignmentThreshold = (rawValue) => {
    const current = store.getState().initializer;
    if (isChrAssignmentServerOwned(current)) {
      return;
    }
    const nextValue = clampChrAssignmentThresholdInput(
      rawValue ?? current.chrAssignmentMinCoveragePercentInput,
      60,
    );
    if (nextValue === String(current.chrAssignmentMinCoveragePercentInput || "").trim()) {
      return;
    }
    store.setState({
      initializer: {
        ...current,
        chrAssignmentMinCoveragePercentInput: nextValue,
      },
    });
    rerender(host, store);
  };
  createChrAssignmentThresholdInput?.addEventListener("blur", (event) => {
    commitCreateChrAssignmentThreshold(event.target.value);
  });
  createChrAssignmentThresholdInput?.addEventListener("change", (event) => {
    commitCreateChrAssignmentThreshold(event.target.value);
  });
  createPhasedAssemblyCheckbox?.addEventListener("change", (event) => {
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        phasedAssemblyEnabledInput: Boolean(event.target.checked),
      },
    });
  });

  projectSelectButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const projectId = Number(button.dataset.projectSelectId || 0);
      const selected = findProjectById(store.getState().initializer.existingProjects, projectId);
      if (!selected) {
        return;
      }
      const currentState = store.getState();
      rememberAssemblyState(currentState);
      const nextDraft = buildEditDraftFromProject(selected);
      const nextSession = {
        ...currentState.session,
        projectId: selected.projectId,
        projectName: selected.projectName || "",
      };
      const fallbackAssembly = {
        ...currentState.assembly,
        ...buildEmptyAssemblyViewState(currentState),
      };
      const nextAssembly = restoreAssemblyState(
        {
          ...currentState,
          session: nextSession,
        },
        fallbackAssembly,
      );
      store.setState({
        session: nextSession,
        initializer: {
          ...currentState.initializer,
          summary: i18nT(currentState, "workspace.runtime.selectedProjectSummary", {
            projectName: selected.projectName,
            createdAt: formatCreatedAt(selected.createdAt, currentState.locale),
          }),
          optionsError: "",
          editProjectId: selected.projectId,
          editProjectNameInput: nextDraft.projectName,
          editReferenceId: String(nextDraft.referenceGenomeId),
          editPrimaryDatasetId: String(nextDraft.primaryDatasetId),
          editSupportDatasetIds: [...nextDraft.supportDatasetIds],
          editChrAssignmentMinCoveragePercentInput: String(
            nextDraft.chrAssignmentMinCoveragePercent,
          ),
          editPhasedAssemblyEnabledInput: nextDraft.phasedAssemblyEnabled,
        },
        assembly: nextAssembly,
      });
      rerender(host, store);
    });
  });

  projectDeleteButtons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.stopPropagation();
      const projectId = Number(button.dataset.projectDeleteId || 0);
      const projectName = String(button.dataset.projectName || "");
      if (!projectId) {
        return;
      }
      const confirmed = window.confirm(
        i18nT(store.getState(), "workspace.prompts.deleteProjectConfirm", {
          projectName: projectName || projectId,
          projectId,
        }),
      );
      if (!confirmed) {
        return;
      }
      await runDeleteProject(host, store, projectId, projectName);
    });
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

  editReferenceSelect?.addEventListener("change", (event) => {
    if (selectedProject?.isProcessed) {
      return;
    }
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        editProjectId: selectedProject?.projectId || current.editProjectId,
        editReferenceId: String(event.target.value || ""),
      },
    });
    rerender(host, store);
  });

  editPrimaryDatasetSelect?.addEventListener("change", (event) => {
    if (selectedProject?.isProcessed) {
      return;
    }
    const nextPrimary = String(event.target.value || "");
    const current = store.getState().initializer;
    const nextSupport = (current.editSupportDatasetIds || []).filter(
      (id) => String(id) !== nextPrimary,
    );
    store.setState({
      initializer: {
        ...current,
        editProjectId: selectedProject?.projectId || current.editProjectId,
        editPrimaryDatasetId: nextPrimary,
        editSupportDatasetIds: nextSupport,
      },
    });
    rerender(host, store);
  });

  editSupportDatasetList?.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const current = store.getState().initializer;
      const datasetId = Number(checkbox.dataset.editSupportDatasetId);
      const isExistingProcessedSupport =
        Boolean(selectedProject?.isProcessed) &&
        normalizeSupportDatasetIds(
          selectedProject?.supportDatasetIds || [],
          selectedProject?.primaryDatasetId,
        ).includes(datasetId);
      if (isExistingProcessedSupport && !checkbox.checked) {
        checkbox.checked = true;
        return;
      }
      const has = (current.editSupportDatasetIds || []).includes(datasetId);
      if (has === Boolean(checkbox.checked)) {
        return;
      }
      const nextSupport = checkbox.checked
        ? [...current.editSupportDatasetIds, datasetId]
        : current.editSupportDatasetIds.filter((id) => id !== datasetId);
      store.setState({
        initializer: {
          ...current,
          editProjectId: selectedProject?.projectId || current.editProjectId,
          editSupportDatasetIds: nextSupport,
        },
      });
      rerender(host, store);
    });
  });

  editChrAssignmentThresholdInput?.addEventListener("input", (event) => {
    if (selectedProject?.isProcessed || isChrAssignmentServerOwned(store.getState().initializer)) {
      return;
    }
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        editProjectId: selectedProject?.projectId || current.editProjectId,
        editChrAssignmentMinCoveragePercentInput: String(event.target.value || "").trim(),
      },
    });
  });
  const commitEditChrAssignmentThreshold = (rawValue) => {
    if (selectedProject?.isProcessed || isChrAssignmentServerOwned(store.getState().initializer)) {
      return;
    }
    const current = store.getState().initializer;
    const nextValue = clampChrAssignmentThresholdInput(
      rawValue ?? current.editChrAssignmentMinCoveragePercentInput,
      selectedProject?.chrAssignmentMinCoveragePercent ?? 60,
    );
    if (nextValue === String(current.editChrAssignmentMinCoveragePercentInput || "").trim()) {
      return;
    }
    store.setState({
      initializer: {
        ...current,
        editProjectId: selectedProject?.projectId || current.editProjectId,
        editChrAssignmentMinCoveragePercentInput: nextValue,
      },
    });
    rerender(host, store);
  };
  editChrAssignmentThresholdInput?.addEventListener("blur", (event) => {
    commitEditChrAssignmentThreshold(event.target.value);
  });
  editChrAssignmentThresholdInput?.addEventListener("change", (event) => {
    commitEditChrAssignmentThreshold(event.target.value);
  });
  editPhasedAssemblyCheckbox?.addEventListener("change", (event) => {
    if (selectedProject?.isProcessed && selectedProject.phasedAssemblyEnabled) {
      event.target.checked = true;
      return;
    }
    const current = store.getState().initializer;
    store.setState({
      initializer: {
        ...current,
        editProjectId: selectedProject?.projectId || current.editProjectId,
        editPhasedAssemblyEnabledInput: Boolean(event.target.checked),
      },
    });
    rerender(host, store);
  });

  saveSelectedProjectButton?.addEventListener("click", async () => {
    await saveSelectedProject(host, store);
  });
}

function closeCreateModal(host, store) {
  const current = store.getState().initializer;
  store.setState({
    initializer: {
      ...current,
      createModalOpen: false,
    },
  });
  rerender(host, store);
}

function renderCreateProjectModal(initializer, messages, locale) {
  const thresholdServerOwned = isChrAssignmentServerOwned(initializer);
  const thresholdHint = thresholdServerOwned
    ? messages.cards.chrAssignmentThresholdLockedHint
    : messages.cards.chrAssignmentThresholdHint;
  const referenceOptions = initializer.references.length
    ? initializer.references
        .map(
          (reference) =>
            `<option value="${reference.referenceGenomeId}" ${
              String(reference.referenceGenomeId) === String(initializer.selectedReferenceId)
                ? "selected"
                : ""
            }>${escapeHtml(reference.name || reference.label)}</option>`,
        )
        .join("")
    : `<option value="">${messages.page.noReference}</option>`;
  const primaryDatasetOptions = initializer.datasets.length
    ? initializer.datasets
        .map(
          (dataset) =>
            `<option value="${dataset.datasetId}" ${
              String(dataset.datasetId) === String(initializer.selectedPrimaryDatasetId)
                ? "selected"
                : ""
            }>${escapeHtml(formatDatasetOptionLabel(messages, locale, dataset))}</option>`,
        )
        .join("")
    : `<option value="">${messages.page.noDataset}</option>`;
  const supportDatasetList = initializer.datasets.length
    ? initializer.datasets
        .map((dataset) => {
          const checked = initializer.selectedSupportDatasetIds.includes(dataset.datasetId)
            ? "checked"
            : "";
          const disabled =
            String(dataset.datasetId) === String(initializer.selectedPrimaryDatasetId)
              ? "disabled"
              : "";
          return `<label class="checkbox-item"><input type="checkbox" data-support-dataset-id="${dataset.datasetId}" ${checked} ${disabled} />${escapeHtml(formatDatasetOptionLabel(messages, locale, dataset))}</label>`;
        })
        .join("")
    : messages.page.noOptions;
  return `
    <div class="modal-overlay">
      <article class="card modal-dialog">
        <header class="page-header">
          <h4>${messages.cards.createNewProject}</h4>
          <button id="initializer-create-modal-close-button" class="button ghost" type="button">${messages.buttons.close}</button>
        </header>
        <label>${messages.cards.projectName}</label>
        <input id="initializer-project-name-input" type="text" placeholder="${escapeAttr(messages.page.projectNamePlaceholder)}" value="${escapeAttr(initializer.projectNameInput)}" />
        <label>${messages.cards.referenceGenome}</label>
        <select id="initializer-reference-select">
          <option value="">${messages.page.chooseReference}</option>
          ${referenceOptions}
        </select>
        <label>${messages.cards.primaryDataset}</label>
        <select id="initializer-primary-dataset-select">
          <option value="">${messages.page.choosePrimaryDataset}</option>
          ${primaryDatasetOptions}
        </select>
        <label>${messages.cards.supportDataset}</label>
        <div id="initializer-support-dataset-list" class="checklist ${initializer.datasets.length ? "" : "muted"}">${supportDatasetList}</div>
        <label>${messages.cards.chrAssignmentThreshold}<span class="muted"> ${thresholdHint}</span></label>
        <input
          id="initializer-chr-assignment-threshold-input"
          type="number"
          min="0"
          max="100"
          step="0.1"
          value="${escapeAttr(String(getChrAssignmentThresholdInputValue(initializer)))}"
          ${thresholdServerOwned ? "disabled" : ""}
        />
        <label class="checkbox-item">
          <input
            id="initializer-phased-assembly-enabled-input"
            type="checkbox"
            role="switch"
            ${initializer.phasedAssemblyEnabledInput ? "checked" : ""}
          />
          ${messages.cards.phasedAssemblyEnabled}
          <span class="muted">${messages.cards.phasedAssemblyEnabledHint}</span>
        </label>
        <div class="inline-input">
          <button id="initializer-create-modal-cancel-button" class="button ghost" type="button">${messages.buttons.cancel}</button>
          <button id="initializer-create-project-confirm-button" class="button" ${
            initializer.creating ? "disabled" : ""
          } type="button">${messages.buttons.createProject}</button>
        </div>
      </article>
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

function renderSelectedProjectCard({ initializer, selectedProject, editDraft, editDirty, locale, messages }) {
  const isProcessed = Boolean(selectedProject.isProcessed);
  const thresholdServerOwned = isChrAssignmentServerOwned(initializer);
  const thresholdLocked = isProcessed || thresholdServerOwned;
  const existingProcessedSupportDatasetIds = normalizeSupportDatasetIds(
    selectedProject.supportDatasetIds || [],
    selectedProject.primaryDatasetId,
  );
  const thresholdHint = thresholdServerOwned
    ? messages.cards.chrAssignmentThresholdLockedHint
    : messages.cards.chrAssignmentThresholdHint;
  const referenceOptions = initializer.references.length
    ? initializer.references
        .map(
          (reference) =>
            `<option value="${reference.referenceGenomeId}" ${
              String(reference.referenceGenomeId) === String(editDraft.referenceGenomeId)
                ? "selected"
                : ""
            }>${escapeHtml(reference.name || reference.label)}</option>`,
        )
        .join("")
    : `<option value="">${messages.page.noReference}</option>`;
  const primaryDatasetOptions = initializer.datasets.length
    ? initializer.datasets
        .map(
          (dataset) =>
            `<option value="${dataset.datasetId}" ${
              String(dataset.datasetId) === String(editDraft.primaryDatasetId) ? "selected" : ""
            }>${escapeHtml(formatDatasetOptionLabel(messages, locale, dataset))}</option>`,
        )
        .join("")
    : `<option value="">${messages.page.noDataset}</option>`;
  const editSupportDatasetList = initializer.datasets.length
    ? initializer.datasets
        .map((dataset) => {
          const checked = (editDraft.supportDatasetIds || []).includes(dataset.datasetId)
            ? "checked"
            : "";
          const isExistingProcessedSupport =
            isProcessed && existingProcessedSupportDatasetIds.includes(dataset.datasetId);
          const disabled =
            isExistingProcessedSupport || String(dataset.datasetId) === String(editDraft.primaryDatasetId)
              ? "disabled"
              : "";
          return `<label class="checkbox-item"><input type="checkbox" data-edit-support-dataset-id="${dataset.datasetId}" ${checked} ${disabled} />${escapeHtml(formatDatasetOptionLabel(messages, locale, dataset))}</label>`;
        })
        .join("")
    : messages.page.noOptions;

  return `
    <article class="card workspace-selected-card">
      <header class="page-header">
        <div>
          <h4>${escapeHtml(i18nT(locale, "workspace.cards.selectedProject", { projectName: selectedProject.projectName }))}</h4>
          <p class="muted">${messages.page.createdAt}${escapeHtml(formatCreatedAt(selectedProject.createdAt, locale))}</p>
        </div>
        <button id="selected-project-save-button" class="button" ${
          initializer.updating || !editDirty ? "disabled" : ""
        }>${messages.buttons.save}</button>
      </header>
      <label>${messages.cards.projectName}</label>
      <input
        id="selected-project-name-input"
        type="text"
        value="${escapeAttr(editDraft.projectName)}"
      />
      <label>${messages.cards.referenceGenome}</label>
      <select id="selected-project-reference-select" ${isProcessed ? "disabled" : ""}>
        <option value="">${messages.page.chooseReference}</option>
        ${referenceOptions}
      </select>
      <label>${messages.cards.primaryDataset}</label>
      <select id="selected-project-primary-dataset-select" ${isProcessed ? "disabled" : ""}>
        <option value="">${messages.page.choosePrimaryDataset}</option>
        ${primaryDatasetOptions}
      </select>
      <label>${messages.cards.supportDataset}</label>
      <div id="selected-project-support-dataset-list" class="checklist ${initializer.datasets.length ? "" : "muted"}">${editSupportDatasetList}</div>
      <label>${messages.cards.chrAssignmentThreshold}<span class="muted"> ${thresholdHint}</span></label>
      <input
        id="selected-project-chr-assignment-threshold-input"
        type="number"
        min="0"
        max="100"
        step="0.1"
        value="${escapeAttr(String(thresholdServerOwned ? getServerChrAssignmentThreshold(initializer) : editDraft.chrAssignmentMinCoveragePercent))}"
        ${thresholdLocked ? "disabled" : ""}
      />
      <label class="checkbox-item">
        <input
          id="selected-project-phased-assembly-enabled-input"
          type="checkbox"
          role="switch"
          ${editDraft.phasedAssemblyEnabled ? "checked" : ""}
          ${isProcessed && selectedProject.phasedAssemblyEnabled ? "disabled" : ""}
        />
        ${messages.cards.phasedAssemblyEnabled}
        <span class="muted">${messages.cards.phasedAssemblyEnabledHint}</span>
      </label>
      ${
        isProcessed
          ? `<p class="muted">${messages.runtime.processedProjectHint}</p>`
          : `<p class="muted">${messages.runtime.editableProjectHint}</p>`
      }
    </article>
  `;
}

async function createProject(host, store) {
  const state = store.getState();
  const workspaceRoot = state.session.workspacePath;
  const initializer = state.initializer;

  if (!workspaceRoot) {
    store.setState({
      initializer: {
        ...initializer,
        optionsError: i18nT(state, "workspace.runtime.workspaceRequired"),
      },
    });
    rerender(host, store);
    return;
  }

  if (
    !initializer.projectNameInput ||
    !initializer.selectedReferenceId ||
    !initializer.selectedPrimaryDatasetId
  ) {
    store.setState({
      initializer: {
        ...initializer,
        optionsError: i18nT(state, "workspace.runtime.requiredFields"),
      },
    });
    rerender(host, store);
    return;
  }

  const chrAssignmentMinCoveragePercent = isChrAssignmentServerOwned(initializer)
    ? getServerChrAssignmentThreshold(initializer)
    : normalizeChrAssignmentThreshold(initializer.chrAssignmentMinCoveragePercentInput ?? "60");
  if (
    !Number.isFinite(chrAssignmentMinCoveragePercent) ||
    chrAssignmentMinCoveragePercent < 0 ||
    chrAssignmentMinCoveragePercent > 100
  ) {
    store.setState({
      initializer: {
        ...initializer,
        optionsError: "chr_assignment_min_coverage_percent must be between 0 and 100",
      },
    });
    rerender(host, store);
    return;
  }

  store.setState({
    initializer: {
      ...initializer,
      creating: true,
      optionsError: "",
      summary: i18nT(state, "workspace.runtime.creatingProject"),
    },
  });
  rerender(host, store);

  try {
    const result = await initializeProject({
      workspaceRoot,
      projectName: initializer.projectNameInput,
      referenceGenomeId: Number(initializer.selectedReferenceId),
      primaryDatasetId: Number(initializer.selectedPrimaryDatasetId),
      supportDatasetIds: initializer.selectedSupportDatasetIds,
      chrAssignmentMinCoveragePercent,
      phasedAssemblyEnabled: Boolean(initializer.phasedAssemblyEnabledInput),
    });
    const selectedProject = findProjectById(result.existingProjects || [], result.projectId);
    const nextDraft = buildEditDraftFromProject(selectedProject);

    store.setState({
      session: {
        ...state.session,
        projectId: result.projectId,
        projectName: result.projectName,
      },
      initializer: {
        ...store.getState().initializer,
        creating: false,
        createModalOpen: false,
        existingProjects: result.existingProjects,
        summary: i18nT(store.getState(), "workspace.runtime.projectCreated", {
          projectName: result.projectName,
        }),
        editProjectId: selectedProject?.projectId ?? null,
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
      projectExport: buildEmptyProjectExportState(),
    });
  } catch (error) {
    store.setState({
      initializer: {
        ...store.getState().initializer,
        creating: false,
        optionsError: String(error.message || error),
        summary: i18nT(store.getState(), "workspace.runtime.projectCreateFailed"),
      },
    });
  }

  rerender(host, store);
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
    window.dispatchEvent(new Event("gpm-next:route-refresh"));
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

async function runDeleteProject(host, store, projectId, projectName) {
  const state = store.getState();
  const workspaceRoot = state.session.workspacePath;
  if (!workspaceRoot) {
    store.setState({
      initializer: {
        ...state.initializer,
        optionsError: i18nT(state, "workspace.runtime.workspaceRequired"),
      },
    });
    rerender(host, store);
    return;
  }

  store.setState({
    initializer: {
      ...state.initializer,
      optionsError: "",
      summary: i18nT(state, "workspace.runtime.deletingProject", {
        projectName: projectName || projectId,
      }),
    },
  });
  rerender(host, store);

  try {
    const result = await deleteProject({ workspaceRoot, projectId });
    const latestState = store.getState();
    const isDeletedCurrent = Number(latestState.session.projectId) === Number(projectId);
    const existingProjects = Array.isArray(result.existingProjects)
      ? result.existingProjects
      : latestState.initializer.existingProjects.filter(
          (project) => Number(project.projectId) !== Number(projectId),
        );
    store.setState({
      session: isDeletedCurrent
        ? {
            ...latestState.session,
            projectId: null,
            projectName: "",
          }
        : latestState.session,
      initializer: {
        ...latestState.initializer,
        existingProjects,
        summary: i18nT(store.getState(), "workspace.runtime.projectDeleted", {
          projectName: projectName || projectId,
        }),
        editProjectId: isDeletedCurrent ? null : latestState.initializer.editProjectId,
        editProjectNameInput: isDeletedCurrent ? "" : latestState.initializer.editProjectNameInput,
        editReferenceId: isDeletedCurrent ? "" : latestState.initializer.editReferenceId,
        editPrimaryDatasetId: isDeletedCurrent ? "" : latestState.initializer.editPrimaryDatasetId,
        editSupportDatasetIds: isDeletedCurrent ? [] : latestState.initializer.editSupportDatasetIds,
        editChrAssignmentMinCoveragePercentInput: isDeletedCurrent
          ? "60"
          : latestState.initializer.editChrAssignmentMinCoveragePercentInput,
        editPhasedAssemblyEnabledInput: isDeletedCurrent
          ? false
          : latestState.initializer.editPhasedAssemblyEnabledInput,
      },
      assembly: {
        ...latestState.assembly,
        ...(isDeletedCurrent ? buildEmptyAssemblyViewState(latestState) : {}),
      },
      projectExport: Number(latestState.projectExport?.projectId || 0) === Number(projectId)
        ? buildEmptyProjectExportState()
        : latestState.projectExport,
    });
  } catch (error) {
    store.setState({
      initializer: {
        ...store.getState().initializer,
        optionsError: String(error.message || error),
        summary: i18nT(store.getState(), "workspace.runtime.projectDeleteFailed"),
      },
    });
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
  if (Number(initializer.editProjectId || 0) !== Number(selectedProject.projectId || 0)) {
    return buildEditDraftFromProject(selectedProject);
  }
  if (selectedProject.isProcessed) {
    const source = buildEditDraftFromProject(selectedProject);
    return {
      ...source,
      projectName: String(initializer.editProjectNameInput || "").trim(),
      supportDatasetIds: mergeAppendOnlySupportDatasetIds(
        source.supportDatasetIds,
        initializer.editSupportDatasetIds || [],
        source.primaryDatasetId,
      ),
      phasedAssemblyEnabled:
        Boolean(source.phasedAssemblyEnabled) || Boolean(initializer.editPhasedAssemblyEnabledInput),
    };
  }
  return {
    projectName: String(initializer.editProjectNameInput || "").trim(),
    referenceGenomeId: Number(initializer.editReferenceId || 0),
    primaryDatasetId: Number(initializer.editPrimaryDatasetId || 0),
    supportDatasetIds: normalizeSupportDatasetIds(
      initializer.editSupportDatasetIds || [],
      initializer.editPrimaryDatasetId,
    ),
    chrAssignmentMinCoveragePercent: isChrAssignmentServerOwned(initializer)
      ? getServerChrAssignmentThreshold(initializer)
      : normalizeChrAssignmentThreshold(initializer.editChrAssignmentMinCoveragePercentInput),
    phasedAssemblyEnabled: Boolean(initializer.editPhasedAssemblyEnabledInput),
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
  if (project.isProcessed) {
    return (
      source.projectName !== String(draft.projectName || "").trim() ||
      !sameNumberArray(source.supportDatasetIds, draft.supportDatasetIds || []) ||
      (!source.phasedAssemblyEnabled && Boolean(draft.phasedAssemblyEnabled))
    );
  }
  const thresholdDirty = isChrAssignmentServerOwned(initializer)
    ? false
    : Number(source.chrAssignmentMinCoveragePercent) !==
      Number(draft.chrAssignmentMinCoveragePercent);
  return (
    source.projectName !== String(draft.projectName || "").trim() ||
    Number(source.referenceGenomeId) !== Number(draft.referenceGenomeId || 0) ||
    Number(source.primaryDatasetId) !== Number(draft.primaryDatasetId || 0) ||
    !sameNumberArray(source.supportDatasetIds, draft.supportDatasetIds || []) ||
    Boolean(source.phasedAssemblyEnabled) !== Boolean(draft.phasedAssemblyEnabled) ||
    thresholdDirty
  );
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
  return raw;
}

function rerender(host, store) {
  const routeHost = host.closest("#route-host");
  if (!routeHost) {
    return;
  }
  routeHost.innerHTML = renderWorkspacePage(store.getState());
  bindWorkspacePage(routeHost, store);
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
