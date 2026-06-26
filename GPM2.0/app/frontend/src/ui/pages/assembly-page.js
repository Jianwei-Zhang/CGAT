import {
  pickDirectoryPath,
  pickZipFilePath,
  pickSaveFilePath,
} from "../../services/backend-api.js";
import {
  appendEditAuditLog,
  addCtgToPhasedChrTrack as addCtgToPhasedChrTrackApi,
  createPhasedChrTrack as createPhasedChrTrackApi,
  deletePhasedChrTrack as deletePhasedChrTrackApi,
  exportDegapJobs,
  exportFinalPathFasta,
  getCtgDetail,
  importAddCtgPackage,
  getJunctionInspection,
  getTrackPairwiseEvidence,
  listChrViewCtgs,
  listCtgEditCandidates,
  listDeletedCtgs,
  listNewSequences,
  listPhasedChrTracks,
  listProjectChromosomes,
  listReferenceTrackMembers,
  removePhasedChrTrackItem as removePhasedChrTrackItemApi,
  runCtgEditorAction,
  writeFinalPathExportBinaryFile,
  writeFinalPathExportTextFile,
} from "../../services/workflow-api.js";
import {
  buildSupportDsStorageKey,
  loadSupportDsState,
  reconcileSupportDsSelection,
  saveSupportDsState,
} from "./assembly/support-ds-session.js";
import {
  loadProjectAssemblyViewState as loadProjectAssemblyViewStateImpl,
  persistProjectAssemblyViewState as persistProjectAssemblyViewStateImpl,
} from "./assembly/project-view-state.js";
import {
  bindAssemblyPage as bindAssemblyPageImpl,
} from "./assembly/bindings.js";
import {
  bindAssemblyContextMenu as bindAssemblyContextMenuImpl,
  buildAssemblyContextMenuActions as buildAssemblyContextMenuActionsImpl,
} from "./assembly/context-menu-runtime.js";
import {
  bindSubviewTrackContigDrag as bindSubviewTrackContigDragImpl,
  bindTrackContigDrag as bindTrackContigDragImpl,
} from "./assembly/track-drag-runtime.js";
import {
  bindTrackBoxSelection as bindTrackBoxSelectionImpl,
} from "./assembly/track-selection-runtime.js";
import {
  bindStickyCtgLabels as bindStickyCtgLabelsImpl,
} from "./assembly/sticky-ctg-label-runtime.js";
import {
  bindBandCanvasRuntime as bindBandCanvasRuntimeImpl,
} from "./assembly/band-canvas-runtime.js";
import {
  clearSubviewTrackDragPreview,
  clearTrackDragPreview,
  previewSubviewTrackContigDrag,
  previewTrackContigDrag,
} from "./assembly/track-drag-preview-runtime.js";
import {
  bindTrackSelectionHotkeys as bindTrackSelectionHotkeysImpl,
  handleTrackDeleteHotkey as handleTrackDeleteHotkeyImpl,
} from "./assembly/track-hotkeys-runtime.js";
import {
  bindDeletedMemberChipBoxSelection as bindDeletedMemberChipBoxSelectionImpl,
  collectMemberChipSelectionResult as collectMemberChipSelectionResultImpl,
} from "./assembly/member-chip-selection-runtime.js";
import {
  bindCtgActions as bindCtgActionsImpl,
} from "./assembly/ctg-actions-runtime.js";
import {
  bindSeqActions as bindSeqActionsImpl,
} from "./assembly/seq-actions-runtime.js";
import {
  applyEditorAction as applyEditorActionImpl,
  deleteSelectedSubviewTrackPairCtgs as deleteSelectedSubviewTrackPairCtgsImpl,
  deleteSelectedTrackCtgs as deleteSelectedTrackCtgsImpl,
  restoreSelectedDeletedCtgs as restoreSelectedDeletedCtgsImpl,
  runBatchDeleteTrackCtgs as runBatchDeleteTrackCtgsImpl,
  runBatchRestoreDeletedCtgs as runBatchRestoreDeletedCtgsImpl,
} from "./assembly/editor-actions-runtime.js";
import {
  handleNewSequenceRowAction as handleNewSequenceRowActionImpl,
  loadAssemblyView as loadAssemblyViewImpl,
  loadDatasetChrCtgs as loadDatasetChrCtgsImpl,
  loadDeletedCtgsForChr as loadDeletedCtgsForChrImpl,
  loadSideDataForCtg as loadSideDataForCtgImpl,
  runCtgSearch as runCtgSearchImpl,
  selectChromosome as selectChromosomeImpl,
  selectCtg as selectCtgImpl,
} from "./assembly/assembly-data-runtime.js";
import {
  addFinalPathContigRelativeToSegment as addFinalPathContigRelativeToSegmentImpl,
  addFinalPathGapRelativeToSegment as addFinalPathGapRelativeToSegmentImpl,
  appendTrackContigToFinalPath as appendTrackContigToFinalPathImpl,
  appendFinalPathRow as appendFinalPathRowImpl,
  createEmptyFinalPathRow as createEmptyFinalPathRowImpl,
  flipFinalPathSegment as flipFinalPathSegmentImpl,
  moveFinalPathRow as moveFinalPathRowImpl,
  removeFinalPathRow as removeFinalPathRowImpl,
  updateFinalPathRow as updateFinalPathRowImpl,
} from "./assembly/final-path-runtime.js";
import {
  launchFinalPathExportJob as launchFinalPathExportJobImpl,
} from "./assembly/final-path-export-runtime.js";
import {
  bindDegapCard as bindDegapCardImpl,
} from "./assembly/degap-runtime.js";
import {
  FINAL_PATH_ALL_KEY,
  normalizeFinalPathViewMode,
  resolveFinalPathSelectionKey,
} from "./assembly/final-path-state.js";
import {
  getAssemblyI18n,
  tAssembly,
} from "./assembly/i18n.js";
import { mapAssemblyError } from "./assembly/error-contract.js";
import { buildDualTrackModel } from "./assembly/track-layout.js";
import {
  rebaseTrackDragOffsetsForStableCtgPositions,
} from "./assembly/track-drag-offset-rebase.js";
import {
  ALIGNMENT_LENGTH_OPTIONS,
  MAPQ_OPTIONS,
  MAX_TICK_COUNT_OPTIONS,
  MIN_TICK_UNIT_KB_OPTIONS,
  SUPPORT_DS_CTG_LEN_BP_OPTIONS,
  normalizeNonNegativeInt,
  normalizePositiveInt,
  resolveTrackInnerWidthFromScale,
  resolveTickBpFromScale,
  resolveTrackPrefs,
} from "./assembly/track-prefs.js";
import {
  areSubviewTrackDragOffsetsEqual,
  areTrackDragOffsetsEqual,
  buildSupportMirrorKey,
  buildSubviewTrackDragOffsetKey,
  buildTrackDragOffsetKey,
  filterPrimaryTrackSelectionCtgIds,
  filterSubviewTrackDragOffsetsBySummary,
  filterTrackDragOffsets,
  normalizeDeletedCtgRecordIds,
  normalizeHiddenPrimaryCtgIdsByChr,
  normalizeSupportMirrorEntry,
  normalizeSupportMirroredCtgs,
  normalizeSupportDatasetId,
  normalizeTrackDragOffsets,
  normalizeTrackSelectionCtgIds,
  normalizeTrackRole,
  normalizeSubviewTrackDragOffsets,
  setSubviewTrackDragOffset,
  setTrackDragOffset,
  swapSubviewTrackDragOffsetsForSummarySwap,
} from "./assembly/selection-state.js";
import {
  areViewportScrollStatesEqual,
  buildFinalPathTrackViewportKey,
  buildMainTrackViewportKey,
  buildSubviewTrackViewportKey,
  normalizeViewportScrollState,
  resolvePersistedViewportScrollLeft,
} from "./assembly/scroll-position-state.js";
import {
  applySubviewSelections as applySubviewSelectionsImpl,
  applySubviewTrackSelections as applySubviewTrackSelectionsImpl,
  buildSubviewSummaryFromCandidates as buildSubviewSummaryFromCandidatesImpl,
  buildSubviewSummaryFromTrackSelections as buildSubviewSummaryFromTrackSelectionsImpl,
  buildSupportSubviewCtgPool,
  buildSubviewTrackPairHiddenCtgKey as buildSubviewTrackPairHiddenCtgKeyImpl,
  buildSubviewTrackPairPoolsFromAssembly as buildSubviewTrackPairPoolsFromAssemblyImpl,
  buildSubviewTrackSelectionKey as buildSubviewTrackSelectionKeyImpl,
  filterSubviewTrackPairHiddenCtgs as filterSubviewTrackPairHiddenCtgsImpl,
  filterSubviewTrackPairSelectionCtgs as filterSubviewTrackPairSelectionCtgsImpl,
  normalizeSubviewFlippedCtgs as normalizeSubviewFlippedCtgsImpl,
  getSubviewSelections as getSubviewSelectionsImpl,
  getSubviewState as getSubviewStateImpl,
  getSubviewTrackSelections as getSubviewTrackSelectionsImpl,
  normalizeSubviewRole as normalizeSubviewRoleImpl,
  normalizeSubviewSummarySelection as normalizeSubviewSummarySelectionImpl,
  normalizeSubviewTrackPairHiddenCtgs as normalizeSubviewTrackPairHiddenCtgsImpl,
  normalizeSubviewTrackPairSelectionCtgs as normalizeSubviewTrackPairSelectionCtgsImpl,
  normalizeSubviewTrackRole as normalizeSubviewTrackRoleImpl,
  normalizeSubviewTrackSummary as normalizeSubviewTrackSummaryImpl,
  normalizeSubviewTrackSelections as normalizeSubviewTrackSelectionsImpl,
  normalizeSubviewTrackSelectionItem as normalizeSubviewTrackSelectionItemImpl,
  normalizeSubviewTrackSource as normalizeSubviewTrackSourceImpl,
  removeSubviewCandidate as removeSubviewCandidateImpl,
  removeSubviewTrackSelection as removeSubviewTrackSelectionImpl,
  resolveFilteredSubviewTrackPairSelectionsFromAssembly as resolveFilteredSubviewTrackPairSelectionsFromAssemblyImpl,
  resolveSubviewCtgOrder as resolveSubviewCtgOrderImpl,
  resolveSubviewSelectionCtg as resolveSubviewSelectionCtgImpl,
  resolveSubviewTrackRoleCtgs as resolveSubviewTrackRoleCtgsImpl,
  resolveSubviewTrackSummaryCtgs as resolveSubviewTrackSummaryCtgsImpl,
  selectSubviewCandidate as selectSubviewCandidateImpl,
  selectSubviewTrack as selectSubviewTrackImpl,
  swapSubviewSummaryOrder as swapSubviewSummaryOrderImpl,
} from "./assembly/subview-state.js";
import {
  buildSubviewPairwiseEvidenceKey as buildSubviewPairwiseEvidenceKeyImpl,
  shouldLoadSubviewPairwiseEvidence as shouldLoadSubviewPairwiseEvidenceImpl,
  shouldRefetchSubviewPairwiseEvidence,
} from "./assembly/subview-pairwise-evidence-state.js";
import {
  toggleSubviewAnchorEdge as toggleSubviewAnchorEdgeImpl,
} from "./assembly/subview-anchor-state.js";
import {
  buildChrLengthsByName,
  filterSupportCtgsBySupportDsCtgLenRules,
  getSupportDsCtgLenRulesForChr,
} from "./assembly/support-ds-ctg-len-rules.js";
import {
  buildAssemblyContextMenuItems,
  resolveAssemblyCtgContextTarget,
  resolveDeletedCtgContextTarget,
  resolveSubviewTrackPairContextTarget,
  resolveTrackLabelContextTarget,
} from "./assembly/context-menu.js";
import {
  convertTrackOffsetPxToBp,
  renderAssemblyMainTab as renderAssemblyMainTabImpl,
  renderAssemblySubviewPanel as renderAssemblySubviewPanelImpl,
  resolveSubviewTrackDragOffsetBp,
  resolveTrackDragOffsetBp,
  roundTrackMetric,
  SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS,
} from "./assembly/render-tracks.js";
import { renderAssemblyPage as renderAssemblyPageShell } from "./assembly/render-shell.js";
import {
  readTrackViewportMetrics,
  resolveActiveTrackScrollElement,
  resolveTrackPointerContentPoint,
  resolveScrollLeftForViewportAnchorBp,
  resolveTrackScrollLeftForViewboxShift,
  resolveViewportAnchorBp,
} from "./assembly/track-viewport.js";

const endTypeOptions = ["normal", "gap", "telomere"];
const renderTracksDeps = {
  escapeAttr,
  escapeHtml,
  formatBp,
  getAssemblyI18n,
  getCurrentProject,
  getDatasetNameById,
  getMeasuredTrackViewportPx: (role) => getMeasuredTrackViewportPx(role),
  getSupportDatasetOptions,
};
function renderAssemblyMainTab(state) {
  return renderAssemblyMainTabImpl(state, renderTracksDeps);
}
const assemblyPageShellDeps = {
  buildAssemblyStats,
  escapeHtml,
  formatAnchorStart,
  formatBp,
  getAssemblyI18n,
  getNewSequencesState,
  getSortedContigListItems,
  renderAddCtgImportProgressModal,
  renderAssemblyMainTab,
  renderAssemblyConfirmModal,
  renderBatchDeleteProgressModal,
  renderFinalPathExportModal,
  renderNewSequenceRowActions,
};
export function renderAssemblyPage(state) {
  return renderAssemblyPageShell(state, assemblyPageShellDeps);
}
let lastSupportDsSessionKey = "";
let lastSupportDsSelection = null;
let lastTrackViewportKey = "";
let lastTrackScrollLeft = 0;
let lastPrimaryTrackViewboxMinX = 0;
let lastSubviewViewportKey = "";
let lastSubviewScrollLeft = 0;
let lastFinalPathViewportKey = "";
let lastFinalPathScrollLeft = 0;
let pendingAssemblyScrollStatePersistTimer = null;
let measuredTrackViewportPxByRole = {
  primary: 1200,
  subview: 1200,
  finalPath: 1200,
};
let suppressNextTrackAutoFocus = false;
let subviewPairwiseEvidenceRequestSeq = 0;
let pendingTrackAutoFocusMode = null;
let trackContigDragActive = false;
let pendingPrimaryViewportAnchorBp = null;
let pendingSubviewViewportAnchorBp = null;
let deferredRerenderCoordinator = null;
const ASSEMBLY_ACTION_FEEDBACK_DISMISS = Symbol("assemblyActionFeedbackDismiss");
const ASSEMBLY_TRACK_RESIZE_BOUND = Symbol("assemblyTrackResizeBound");
const ASSEMBLY_SUBVIEW_BAND_TOOLTIP_BOUND = Symbol("assemblySubviewBandTooltipBound");
const ACTION_FEEDBACK_AUTO_DISMISS_MS = 1000;
const ACTION_FEEDBACK_POINTER_DISMISS_MS = 500;
let suppressTrackContigClickUntil = 0;
let assemblyConfirmDialogSeq = 0;
const pendingAssemblyConfirmResolvers = new Map();

function renderAssemblyConfirmModal(state) {
  const dialog = state.assembly?.confirmDialog;
  if (!dialog?.open) {
    return "";
  }
  const pageI18n = getAssemblyI18n(state).page || {};
  const id = String(dialog.id || "");
  const mode = dialog.mode === "prompt" ? "prompt" : "confirm";
  const title = pageI18n.confirmDialogTitle || "确认操作";
  const message = String(dialog.message || "");
  const confirmLabel = pageI18n.confirmDialogConfirm || "确定";
  const cancelLabel = pageI18n.confirmDialogCancel || "取消";
  const dangerClass = dialog.danger === true || mode === "confirm" ? " is-danger" : "";
  const promptInput = mode === "prompt"
    ? `
        <input
          type="text"
          inputmode="numeric"
          class="assembly-confirm-input"
          value="${escapeAttr(String(dialog.defaultValue || ""))}"
          data-assembly-confirm-input="${escapeAttr(id)}"
          autofocus
        >
      `
    : "";
  return `
    <div class="modal-overlay assembly-confirm-overlay" data-assembly-confirm-overlay="true">
      <article
        class="card modal-dialog assembly-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(title)}"
        data-assembly-confirm-dialog="${escapeAttr(id)}"
        data-assembly-confirm-mode="${escapeAttr(mode)}"
      >
        <h4 class="assembly-confirm-title${dangerClass}">${escapeHtml(title)}</h4>
        <p class="assembly-confirm-message${dangerClass}">${escapeHtml(message)}</p>
        ${promptInput}
        <div class="assembly-confirm-actions">
          <button
            type="button"
            class="button primary"
            data-assembly-confirm-action="confirm"
            data-assembly-confirm-id="${escapeAttr(id)}"
          >${escapeHtml(confirmLabel)}</button>
          <button
            type="button"
            class="button ghost"
            data-assembly-confirm-action="cancel"
            data-assembly-confirm-id="${escapeAttr(id)}"
          >${escapeHtml(cancelLabel)}</button>
        </div>
      </article>
    </div>
  `;
}

function requestAssemblyConfirm(host, store, message) {
  if (!host || !store) {
    return Promise.resolve(globalThis.window?.confirm?.(message) ?? false);
  }
  const state = store.getState();
  const id = `assembly-confirm-${assemblyConfirmDialogSeq += 1}`;
  const previousId = String(state.assembly?.confirmDialog?.id || "");
  const previousResolve = pendingAssemblyConfirmResolvers.get(previousId);
  if (previousResolve) {
    pendingAssemblyConfirmResolvers.delete(previousId);
    previousResolve(false);
  }
  return new Promise((resolve) => {
    pendingAssemblyConfirmResolvers.set(id, resolve);
    store.setState({
      assembly: {
        ...state.assembly,
        confirmDialog: {
          open: true,
          id,
          mode: "confirm",
          danger: true,
          message: String(message || ""),
        },
      },
    });
    rerender(host, store);
  });
}

function requestAssemblyPrompt(host, store, message, defaultValue = "") {
  if (!host || !store) {
    if (typeof globalThis.window?.prompt !== "function") {
      return Promise.resolve("");
    }
    return Promise.resolve(globalThis.window.prompt(message, String(defaultValue)) ?? "");
  }
  const state = store.getState();
  const id = `assembly-confirm-${assemblyConfirmDialogSeq += 1}`;
  const previousId = String(state.assembly?.confirmDialog?.id || "");
  const previousResolve = pendingAssemblyConfirmResolvers.get(previousId);
  if (previousResolve) {
    pendingAssemblyConfirmResolvers.delete(previousId);
    previousResolve("");
  }
  return new Promise((resolve) => {
    pendingAssemblyConfirmResolvers.set(id, resolve);
    store.setState({
      assembly: {
        ...state.assembly,
        confirmDialog: {
          open: true,
          id,
          mode: "prompt",
          danger: false,
          message: String(message || ""),
          defaultValue: String(defaultValue ?? ""),
        },
      },
    });
    rerender(host, store);
  });
}

function resolveAssemblyConfirmDialog(host, store, { id, confirmed, value }) {
  const state = store.getState();
  const dialogId = String(id || state.assembly?.confirmDialog?.id || "");
  const resolve = pendingAssemblyConfirmResolvers.get(dialogId);
  const mode = state.assembly?.confirmDialog?.mode === "prompt" ? "prompt" : "confirm";
  pendingAssemblyConfirmResolvers.delete(dialogId);
  store.setState({
    assembly: {
      ...state.assembly,
      confirmDialog: null,
    },
  });
  rerender(host, store);
  if (resolve) {
    resolve(mode === "prompt"
      ? (confirmed ? String(value ?? "") : "")
      : Boolean(confirmed));
  }
}

function createDeferredRerenderCoordinator(options = {}) {
  const request = typeof options?.requestAnimationFrame === "function"
    ? options.requestAnimationFrame
    : (typeof globalThis.requestAnimationFrame === "function"
      ? globalThis.requestAnimationFrame.bind(globalThis)
      : (callback) => globalThis.setTimeout(() => callback(Date.now()), 16));
  const cancel = typeof options?.cancelAnimationFrame === "function"
    ? options.cancelAnimationFrame
    : (typeof globalThis.cancelAnimationFrame === "function"
      ? globalThis.cancelAnimationFrame.bind(globalThis)
      : (token) => globalThis.clearTimeout(token));
  const rerenderImpl = typeof options?.rerender === "function" ? options.rerender : rerender;
  const rerenderSubviewPanelImpl =
    typeof options?.rerenderSubviewPanel === "function"
      ? options.rerenderSubviewPanel
      : rerenderImpl;
  let frameToken = null;
  let pendingHost = null;
  let pendingStore = null;
  let pendingMode = "";

  const scheduleWithMode = (host, store, mode) => {
    pendingHost = host;
    pendingStore = store;
    if (mode === "full" || !pendingMode) {
      pendingMode = mode;
    }
    if (frameToken !== null) {
      return;
    }
    frameToken = request(() => {
      frameToken = null;
      const nextHost = pendingHost;
      const nextStore = pendingStore;
      const nextMode = pendingMode;
      pendingHost = null;
      pendingStore = null;
      pendingMode = "";
      if (!nextHost || !nextStore) {
        return;
      }
      if (nextMode === "subview-panel") {
        rerenderSubviewPanelImpl(nextHost, nextStore);
        return;
      }
      rerenderImpl(nextHost, nextStore);
    });
  };

  return {
    schedule(host, store) {
      scheduleWithMode(host, store, "full");
    },
    scheduleSubviewPanel(host, store) {
      scheduleWithMode(host, store, "subview-panel");
    },
    cancel() {
      if (frameToken === null) {
        pendingHost = null;
        pendingStore = null;
        pendingMode = "";
        return false;
      }
      cancel(frameToken);
      frameToken = null;
      pendingHost = null;
      pendingStore = null;
      pendingMode = "";
      return true;
    },
  };
}

function getDeferredRerenderCoordinator() {
  if (!deferredRerenderCoordinator) {
    deferredRerenderCoordinator = createDeferredRerenderCoordinator();
  }
  return deferredRerenderCoordinator;
}

function scheduleDeferredRerender(host, store) {
  getDeferredRerenderCoordinator().schedule(host, store);
}

function scheduleDeferredSubviewPanelRerender(host, store) {
  getDeferredRerenderCoordinator().scheduleSubviewPanel(host, store);
}

function cancelDeferredRerender() {
  getDeferredRerenderCoordinator().cancel();
}

export function __testCreateDeferredRerenderCoordinator(options = {}) {
  return createDeferredRerenderCoordinator(options);
}

function resolveFinalPathExportKindLabel(job, labels) {
  const kind = String(job?.kind || "").trim().toLowerCase();
  if (kind === "png") {
    return labels.finalPathExportPng || "图(.png)";
  }
  if (kind === "tsv") {
    return labels.finalPathExportTsv || "表(.tsv)";
  }
  if (kind === "fasta") {
    return labels.finalPathExportFasta || "序列(.fasta)";
  }
  if (kind === "log") {
    return labels.finalPathExportLog || "日志(.log)";
  }
  if (kind === "degap-jobs") {
    return labels.finalPathExportDegapJobs || "DEGAP-JOBS";
  }
  if (kind === "all") {
    return labels.finalPathExportAll || "All";
  }
  return kind || (labels.finalPathExport || "Export");
}

function resolveFinalPathExportStatusText(job, labels) {
  if (job?.status === "success") {
    return labels.finalPathExportCompleted || "已完成导出";
  }
  if (job?.status === "error") {
    return labels.finalPathExportFailed || "导出失败";
  }
  if (job?.status === "canceled") {
    return labels.finalPathExportCanceled || "已终止，已保留已导出的文件";
  }
  const template = labels.finalPathExportRunning || "正在执行：{step}";
  return template.replace("{step}", String(job?.currentStep || "").trim());
}

function renderFinalPathExportStepIcon(status) {
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

function resolveFinalPathExportStepStatus(job, step) {
  const completedOutputs = Array.isArray(job?.completedOutputs) ? job.completedOutputs : [];
  const completedStepIds = Array.isArray(job?.completedStepIds) ? job.completedStepIds : [];
  const currentStep = String(job?.currentStep || "").trim();
  const stepLabel = String(step?.label || "").trim();
  const stepId = String(step?.id || "").trim();
  if (stepId && completedStepIds.includes(stepId)) {
    return "done";
  }
  if (completedOutputs.includes(step?.outputPath)) {
    return "done";
  }
  if (job?.kind === "degap-jobs" && ["degap-prepare", "degap-job", "degap-manifest"].includes(step?.kind)) {
    if (job?.status === "running") {
      return "running";
    }
    if (job?.status === "error") {
      return "error";
    }
  }
  if (job?.status === "running" && currentStep && stepLabel && currentStep.includes(stepLabel)) {
    return "running";
  }
  if (job?.status === "error" && currentStep && stepLabel && currentStep.includes(stepLabel)) {
    return "error";
  }
  if (job?.status === "canceled") {
    return "skipped";
  }
  return "pending";
}

function renderFinalPathExportSteps(job) {
  const displaySteps = Array.isArray(job?.displaySteps) ? job.displaySteps : [];
  const steps = displaySteps.length ? displaySteps : Array.isArray(job?.steps) ? job.steps : [];
  if (!steps.length) {
    return "";
  }
  return `
    <div class="assembly-final-path-export-steps">
      ${steps.map((step) => {
        const stepStatus = resolveFinalPathExportStepStatus(job, step);
        return `
          <div
            class="pipeline-step-row assembly-final-path-export-step ${stepStatus}"
            data-final-path-export-step-status="${escapeAttr(stepStatus)}"
          >
            <span class="pipeline-step-label">${escapeHtml(String(step?.label || ""))}</span>
            <span class="pipeline-step-icon">${renderFinalPathExportStepIcon(stepStatus)}</span>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function renderFinalPathExportCompletedOutputs(job) {
  const outputs = Array.isArray(job?.completedOutputs) ? job.completedOutputs : [];
  if (!outputs.length) {
    return "";
  }
  return `
    <ul class="assembly-final-path-export-output-list">
      ${outputs.map((outputPath) => `<li>${escapeHtml(String(outputPath || ""))}</li>`).join("")}
    </ul>
  `;
}

function resolveBatchDeleteProgressIconStatus(status) {
  if (status === "success") {
    return "done";
  }
  if (status === "error") {
    return "error";
  }
  if (status === "running") {
    return "running";
  }
  return "pending";
}

function renderAddCtgImportProgressModal(state) {
  const progress = state.assembly?.addCtgImportProgress;
  if (!progress?.open) {
    return "";
  }
  const runtimeI18n = getAssemblyI18n(state).runtime || {};
  const allStages = Array.isArray(progress.stages) ? progress.stages : [];
  const recentOffset = Math.max(0, allStages.length - 60);
  const recentStages = allStages.slice(recentOffset);
  const progressMeta = buildAssemblyImportProgressMeta(allStages);
  const status = String(progress.status || "running");
  const isTerminal = status === "success" || status === "error";
  const title = runtimeI18n.addCtgImportProgressTitle || "add_ctg 导入进度";
  const summary = String(progress.summary || runtimeI18n.addCtgImportProgressSubtitle || "正在导入 add_ctg 包。");
  const stageItems = recentStages.length
    ? recentStages.map((stage, index) => {
      const absoluteIndex = recentOffset + index;
      const rowStatus = isTerminal && index === recentStages.length - 1
        ? status
        : index === recentStages.length - 1
          ? "running"
          : "done";
      const iconStatus = resolveAddCtgImportProgressIconStatus(rowStatus);
      return `
        <div class="pipeline-step-row import-progress-step add-ctg-import-progress-step ${escapeAttr(rowStatus)}">
          <span class="pipeline-step-label">${escapeHtml(formatAssemblyImportProgressStage(stage, absoluteIndex, progressMeta))}</span>
          <span class="pipeline-step-icon">${renderFinalPathExportStepIcon(iconStatus)}</span>
        </div>
      `;
    }).join("")
    : `<div class="pipeline-step-row import-progress-step add-ctg-import-progress-step running">
        <span class="pipeline-step-label">${escapeHtml(runtimeI18n.addCtgImportNotStarted || "准备导入...")}</span>
        <span class="pipeline-step-icon">${renderFinalPathExportStepIcon("running")}</span>
      </div>`;
  const closeButton = isTerminal
    ? `<button type="button" class="button ghost tiny import-progress-close" data-add-ctg-import-close="1" title="${escapeAttr(runtimeI18n.addCtgImportClose || "关闭")}">x</button>`
    : "";
  const percent = progressMeta.total > 0
    ? Math.max(0, Math.min(100, (progressMeta.current / progressMeta.total) * 100))
    : 0;
  const meter = progressMeta.total > 0
    ? `<div class="import-progress-meter" aria-label="${escapeAttr(`${progressMeta.current}/${progressMeta.total}`)}">
        <div class="import-progress-meter-track">
          <div class="import-progress-meter-fill" style="width: ${escapeAttr(percent.toFixed(1))}%;"></div>
        </div>
        <span class="import-progress-meter-text">${escapeHtml(`${progressMeta.current}/${progressMeta.total}`)}</span>
      </div>`
    : "";
  return `
    <div class="modal-overlay import-progress-overlay add-ctg-import-progress-overlay" data-add-ctg-import-progress-overlay="true">
      <article class="card modal-dialog import-progress-dialog add-ctg-import-progress-dialog" role="dialog" aria-modal="true" aria-label="${escapeAttr(title)}">
        ${closeButton}
        <div class="import-progress-heading">
          ${isTerminal ? "" : `<span class="pipeline-spinner" aria-hidden="true"></span>`}
          <div>
            <div class="import-progress-title-row">
              <h4>${escapeHtml(title)}</h4>
              ${meter}
            </div>
            <p class="muted">${escapeHtml(summary)}</p>
            ${progress.error ? `<p class="error-text">${escapeHtml(String(progress.error))}</p>` : ""}
          </div>
        </div>
        <div class="import-progress-list add-ctg-import-progress-list">${stageItems}</div>
      </article>
    </div>
  `;
}

function resolveAddCtgImportProgressIconStatus(status) {
  if (status === "success") {
    return "done";
  }
  if (status === "error") {
    return "error";
  }
  if (status === "running") {
    return "running";
  }
  return "pending";
}

function buildAssemblyImportProgressMeta(stages) {
  const list = Array.isArray(stages) ? stages : [];
  const progressOffset = list.findIndex((stage) => {
    if (!stage || typeof stage !== "object") {
      return false;
    }
    const progressIndex = Number(stage.progressIndex);
    return Number.isFinite(progressIndex) && progressIndex > 0;
  });
  const offset = progressOffset >= 0 ? progressOffset : 0;
  let latestProgressIndex = 0;
  let latestProgressTotal = 0;
  for (const stage of list) {
    if (stage && typeof stage === "object") {
      const progressIndex = Number(stage.progressIndex);
      const progressTotal = Number(stage.progressTotal);
      if (Number.isFinite(progressIndex) && progressIndex > latestProgressIndex) {
        latestProgressIndex = progressIndex;
      }
      if (Number.isFinite(progressTotal) && progressTotal > latestProgressTotal) {
        latestProgressTotal = progressTotal;
      }
    }
  }
  const current = latestProgressIndex > 0
    ? Math.max(list.length, offset + latestProgressIndex)
    : list.length;
  const total = Math.max(list.length, latestProgressTotal > 0 ? offset + latestProgressTotal : list.length);
  return {
    offset,
    current: Math.min(current, total),
    total,
  };
}

function formatAssemblyImportProgressStage(stage, index, progressMeta) {
  const label = stage && typeof stage === "object"
    ? String(stage.label || stage.text || "")
    : String(stage || "");
  const progressIndex = stage && typeof stage === "object" ? Number(stage.progressIndex) : 0;
  const displayIndex = Number.isFinite(progressIndex) && progressIndex > 0
    ? progressMeta.offset + progressIndex
    : index + 1;
  if (!progressMeta.total) {
    return label;
  }
  return `${label} (${displayIndex}/${progressMeta.total})`;
}

function renderBatchDeleteProgressModal(state) {
  const progress = state.assembly?.batchDeleteProgress;
  if (!progress?.open) {
    return "";
  }
  const runtimeI18n = getAssemblyI18n(state).runtime || {};
  const items = Array.isArray(progress.items) ? progress.items : [];
  const total = Math.max(0, Number(progress.total) || items.length);
  const current = Math.min(total, Math.max(0, Number(progress.current) || 0));
  const percent = total > 0 ? Math.round((current / total) * 100) : 0;
  const title = runtimeI18n.batchDeleteProgressTitle || "批量删除进度";
  const subtitle = runtimeI18n.batchDeleteProgressSubtitle || "正在删除选中的 contig。";
  return `
    <div
      class="modal-overlay import-progress-overlay batch-delete-progress-overlay"
      data-batch-delete-progress-overlay="true"
    >
      <article
        class="card modal-dialog import-progress-dialog batch-delete-progress-dialog"
        data-batch-delete-progress-modal="true"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(title)}"
      >
        <div class="import-progress-heading">
          <span class="pipeline-spinner" aria-hidden="true"></span>
          <div>
            <div class="import-progress-title-row">
              <h4>${escapeHtml(title)}</h4>
              <div class="import-progress-meter" aria-label="${escapeAttr(`${current}/${total}`)}">
                <div class="import-progress-meter-track">
                  <div class="import-progress-meter-fill" style="width: ${escapeAttr(percent)}%;"></div>
                </div>
                <span class="import-progress-meter-text">${escapeHtml(`${current}/${total}`)}</span>
              </div>
            </div>
            <p class="muted">${escapeHtml(subtitle)}</p>
          </div>
        </div>
        <div class="import-progress-list batch-delete-progress-list">
          ${items.map((item) => {
            const status = String(item?.status || "pending");
            const iconStatus = resolveBatchDeleteProgressIconStatus(status);
            const label = String(item?.label || `Ctg${item?.assemblyCtgId ?? ""}`).trim();
            const idText = `assembly_ctg_id=${item?.assemblyCtgId ?? ""}`;
            return `
              <div
                class="pipeline-step-row import-progress-step batch-delete-progress-step ${escapeAttr(status)}"
                data-batch-delete-progress-row="${escapeAttr(item?.assemblyCtgId ?? "")}"
                data-batch-delete-progress-status="${escapeAttr(status)}"
              >
                <span class="pipeline-step-label">
                  ${escapeHtml(label)}
                  <span class="muted">${escapeHtml(idText)}</span>
                  ${item?.error ? `<span class="error-text">${escapeHtml(String(item.error))}</span>` : ""}
                </span>
                <span class="pipeline-step-icon">${renderFinalPathExportStepIcon(iconStatus)}</span>
              </div>
            `;
          }).join("")}
        </div>
      </article>
    </div>
  `;
}

function renderFinalPathExportModal(state) {
  const job = state.assembly?.finalPathExportJob;
  if (!job?.open) {
    return "";
  }
  const pageI18n = getAssemblyI18n(state).page || {};
  const kindLabel = resolveFinalPathExportKindLabel(job, pageI18n);
  const statusText = resolveFinalPathExportStatusText(job, pageI18n);
  const statusClass = job?.status === "success" ? "success" : "";
  return `
    <div class="modal-overlay assembly-final-path-export-overlay" data-final-path-export-overlay="true">
      <article
        class="card modal-dialog assembly-final-path-export-dialog"
        data-final-path-export-modal="true"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(pageI18n.finalPathExportDialogTitle || "正在导出 final path")}"
      >
        <button
          type="button"
          class="button ghost tiny assembly-final-path-export-close"
          data-final-path-export-close="true"
        >x</button>
        <div class="assembly-final-path-export-body">
          <header class="assembly-final-path-export-head">
            <h4>${escapeHtml(pageI18n.finalPathExportDialogTitle || "正在导出 final path")}</h4>
            <p class="muted">${escapeHtml(`${String(job?.chrName || "").trim()} · ${kindLabel}`)}</p>
          </header>
          ${renderFinalPathExportSteps(job)}
          <p class="muted assembly-final-path-export-status ${escapeAttr(statusClass)}">${escapeHtml(statusText)}</p>
          ${job?.error ? `<p class="error-text">${escapeHtml(String(job.error || ""))}</p>` : ""}
          ${renderFinalPathExportCompletedOutputs(job)}
        </div>
      </article>
    </div>
  `;
}

function resolveSubviewAutoTrackOffsets({ topLengthBp, bottomLengthBp, domainEnd, segmentPairs }) {
  if (topLengthBp === bottomLengthBp) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const shorterTrack = topLengthBp < bottomLengthBp ? "top" : "bottom";
  const shorterLengthBp = shorterTrack === "top" ? topLengthBp : bottomLengthBp;
  const maxOffsetBp = Math.max(0, domainEnd - shorterLengthBp);
  if (!Array.isArray(segmentPairs) || !segmentPairs.length || maxOffsetBp <= 0) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const offsetCandidates = segmentPairs
    .map(({ topSegment, bottomSegment }) => {
      const topMid = (Number(topSegment?.ctgStart) + Number(topSegment?.ctgEnd)) / 2;
      const bottomMid = (Number(bottomSegment?.ctgStart) + Number(bottomSegment?.ctgEnd)) / 2;
      if (!Number.isFinite(topMid) || !Number.isFinite(bottomMid)) {
        return null;
      }
      const rawOffsetBp = shorterTrack === "top" ? bottomMid - topMid : topMid - bottomMid;
      return clampSubviewTrackOffsetBp(rawOffsetBp, maxOffsetBp);
    })
    .filter((value) => Number.isFinite(value));
  if (!offsetCandidates.length) {
    return { topOffsetBp: 0, bottomOffsetBp: 0 };
  }
  const resolvedOffsetBp = resolveMedianNumber(offsetCandidates);
  return shorterTrack === "top"
    ? { topOffsetBp: resolvedOffsetBp, bottomOffsetBp: 0 }
    : { topOffsetBp: 0, bottomOffsetBp: resolvedOffsetBp };
}

function clampSubviewTrackOffsetBp(value, maxOffsetBp) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.min(Math.max(0, numeric), Math.max(0, Number(maxOffsetBp) || 0));
}

function resolveMedianNumber(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middleIndex = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) {
    return sorted[middleIndex];
  }
  return (sorted[middleIndex - 1] + sorted[middleIndex]) / 2;
}

function pairSubviewSegmentsByReference(topSegments, bottomSegments) {
  const safeTopSegments = Array.isArray(topSegments) ? [...topSegments] : [];
  const safeBottomSegments = Array.isArray(bottomSegments) ? [...bottomSegments] : [];
  if (!safeTopSegments.length || !safeBottomSegments.length) {
    return [];
  }
  safeTopSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });
  safeBottomSegments.sort((left, right) => {
    if (left.refStart !== right.refStart) {
      return left.refStart - right.refStart;
    }
    return left.refEnd - right.refEnd;
  });

  const pairs = [];
  let bottomWindowStart = 0;
  for (const topSegment of safeTopSegments) {
    while (
      bottomWindowStart < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomWindowStart]?.refEnd || 0) <= Number(topSegment.refStart || 0)
    ) {
      bottomWindowStart += 1;
    }
    for (
      let bottomIndex = bottomWindowStart;
      bottomIndex < safeBottomSegments.length &&
      Number(safeBottomSegments[bottomIndex]?.refStart || 0) < Number(topSegment.refEnd || 0);
      bottomIndex += 1
    ) {
      const bottomSegment = safeBottomSegments[bottomIndex];
      if (resolveRefOverlapBp(topSegment, bottomSegment) <= 0) {
        continue;
      }
      pairs.push({
        topSegment,
        bottomSegment,
      });
    }
  }
  return pairs;
}

function resolveRefOverlapBp(leftSegment, rightSegment) {
  const leftStart = Math.min(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const leftEnd = Math.max(Number(leftSegment?.refStart) || 0, Number(leftSegment?.refEnd) || 0);
  const rightStart = Math.min(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const rightEnd = Math.max(Number(rightSegment?.refStart) || 0, Number(rightSegment?.refEnd) || 0);
  const start = Math.max(leftStart, rightStart);
  const end = Math.min(leftEnd, rightEnd);
  return Math.max(0, end - start);
}

function getSubviewSelections(subview) {
  return getSubviewSelectionsImpl(subview);
}

function normalizeSubviewTrackSelectionItem(item) {
  return normalizeSubviewTrackSelectionItemImpl(item);
}

function buildSubviewTrackSelectionKey(selection) {
  return buildSubviewTrackSelectionKeyImpl(selection);
}

function normalizeSubviewTrackSelections(values) {
  return normalizeSubviewTrackSelectionsImpl(values);
}

function getSubviewTrackSelections(subview) {
  return getSubviewTrackSelectionsImpl(subview);
}

function applySubviewSelections(subview, selections) {
  return applySubviewSelectionsImpl(subview, selections);
}

function applySubviewTrackSelections(subview, selections) {
  return applySubviewTrackSelectionsImpl(subview, selections);
}

function normalizeSubviewRole(role) {
  return normalizeSubviewRoleImpl(role);
}

function normalizeSubviewTrackRole(role) {
  return normalizeSubviewTrackRoleImpl(role);
}

function normalizeSubviewTrackSource(source) {
  return normalizeSubviewTrackSourceImpl(source);
}

function normalizeSubviewTrackSummary(selection) {
  return normalizeSubviewTrackSummaryImpl(selection);
}

function normalizeSubviewTrackPairHiddenCtgs(values) {
  return normalizeSubviewTrackPairHiddenCtgsImpl(values);
}

function normalizeSubviewFlippedCtgs(values) {
  return normalizeSubviewFlippedCtgsImpl(values);
}

function normalizeSubviewTrackPairSelectionCtgs(values) {
  return normalizeSubviewTrackPairSelectionCtgsImpl(values);
}

function buildSubviewTrackPairHiddenCtgKey(trackRole, contigId) {
  return buildSubviewTrackPairHiddenCtgKeyImpl(trackRole, contigId);
}

function getSubviewTrackPairSelections(subview) {
  return normalizeSubviewTrackPairSelectionCtgsImpl(subview?.trackPairSelectedCtgs);
}

export function __testSelectSubviewCandidate(args) {
  return selectSubviewCandidate(args);
}

export function __testSelectSubviewTrack(args) {
  return selectSubviewTrack(args);
}

export function __testRemoveSubviewCandidate(args) {
  return removeSubviewCandidate(args);
}

export function __testRemoveSubviewTrackSelection(args) {
  return removeSubviewTrackSelection(args);
}

export function __testBuildSubviewSummaryFromTrackSelections(args) {
  return buildSubviewSummaryFromTrackSelections(args);
}

export function __testSwapSubviewSummaryOrder(args) {
  return swapSubviewSummaryOrder(args);
}

export function __testSwapSubviewTrackDragOffsetsForSummarySwap(args) {
  return swapSubviewTrackDragOffsetsForSummarySwap(args);
}

export function __testResolveTrackContigClickAction(args) {
  return resolveTrackContigClickAction(args);
}

export function __testHandleTrackSubviewCandidateSelection(host, store, args) {
  return handleTrackSubviewCandidateSelection(host, store, args);
}

export function __testHandleTrackSubviewTrackSelection(host, store, args) {
  return handleTrackSubviewTrackSelection(host, store, args);
}

export function __testEnterSubviewFromCandidates(host, store) {
  return enterSubviewFromCandidates(host, store);
}

export function __testEnterSubviewFromTrackSelections(host, store) {
  return enterSubviewFromTrackSelections(host, store);
}

function handleTrackSubviewCandidateSelection(host, store, {
  trackRole,
  contigId,
  phasedTrackId = null,
  phasedTrackItemId = null,
  phasedHaplotypeKey = "",
}) {
  const state = store.getState();
  const currentProject = getCurrentProject(state);
  const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
  const nextSubview = selectSubviewCandidate({
    mode: getSubviewState(state.assembly).mode,
    primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
    supportDatasetId: normalizeSupportDatasetId(state.assembly.supportDatasetId),
    primaryCtgs: pools.primaryCtgs,
    supportCtgs: pools.supportCtgs,
    refCtgs: pools.refCtgs,
    subview: state.assembly.subview,
    trackRole,
    contigId,
    phasedTrackId,
    phasedTrackItemId,
    phasedHaplotypeKey,
    stateOrLocale: state,
  });

  store.setState({
    assembly: {
      ...state.assembly,
      subview: nextSubview,
      subviewTrackDragOffsets: [],
    },
  });
  if (getSubviewSelections(nextSubview).length === 2) {
    enterSubviewFromCandidates(host, store);
    return;
  }
  rerender(host, store);
}

function handleTrackSubviewTrackSelection(host, store, {
  trackRole,
  source = "mother",
  datasetId = null,
  isMirror = false,
  phasedTrackId = null,
  haplotypeKey = "",
}) {
  const state = store.getState();
  const nextSubview = selectSubviewTrack({
    subview: state.assembly.subview,
    trackRole,
    source,
    datasetId,
    isMirror,
    phasedTrackId,
    haplotypeKey,
    stateOrLocale: state,
  });
  const hasEnteredTrackSubview = Boolean(nextSubview.summary);
  const nextSubviewTrackView = hasEnteredTrackSubview
    ? inheritSubviewTrackViewFromMainTrack(state.assembly)
    : state.assembly.subviewTrackView;
  const pairwiseEvidence = hasEnteredTrackSubview
    ? buildInitialSubviewPairwiseEvidence(
        nextSubview.summary,
        nextSubviewTrackView,
        state.assembly.subview?.pairwiseEvidence,
        state,
      )
    : null;
  store.setState({
    assembly: {
      ...state.assembly,
      subviewTrackView: nextSubviewTrackView,
      subview: hasEnteredTrackSubview
        ? {
          ...nextSubview,
          activeAnchors: [],
          flippedCtgs: [],
          pairwiseEvidence,
        }
        : nextSubview,
      subviewTrackDragOffsets: [],
    },
  });
  rerender(host, store);
  if (pairwiseEvidence && String(pairwiseEvidence.status || "") === "loading") {
    loadSubviewPairwiseEvidence(host, store, nextSubview.summary);
  }
}

function handleSubviewCandidateRemoval(host, store, {
  trackRole,
  contigId,
  phasedTrackId = null,
  phasedTrackItemId = null,
  phasedHaplotypeKey = "",
}) {
  const state = store.getState();
  const nextSubview = removeSubviewCandidate({
    subview: state.assembly.subview,
    trackRole,
    contigId,
    phasedTrackId,
    phasedTrackItemId,
    phasedHaplotypeKey,
    stateOrLocale: state,
  });
  store.setState({
    assembly: {
      ...state.assembly,
      subview: nextSubview,
      subviewTrackDragOffsets: [],
    },
  });
  rerender(host, store);
}

function handleSubviewTrackSelectionRemoval(host, store, { trackRole, source, datasetId, isMirror }) {
  const state = store.getState();
  const nextSubview = removeSubviewTrackSelection({
    subview: state.assembly.subview,
    trackRole,
    source,
    datasetId,
    isMirror,
    stateOrLocale: state,
  });
  store.setState({
    assembly: {
      ...state.assembly,
      subview: nextSubview,
      subviewTrackDragOffsets: [],
    },
  });
  rerender(host, store);
}

function handleSubviewSwapTrackOrder(host, store) {
  const state = store.getState();
  const nextSubview = swapSubviewSummaryOrder({
    subview: state.assembly.subview,
    stateOrLocale: state,
  });
  if (!nextSubview.summary) {
    return;
  }
  const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
    nextSubview.summary,
    state.assembly.subviewTrackView || state.assembly.trackView,
    state.assembly.subview?.pairwiseEvidence,
    state,
  );
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...nextSubview,
        pairwiseEvidence,
      },
      subviewTrackDragOffsets: swapSubviewTrackDragOffsetsForSummarySwap(
        state.assembly.subviewTrackDragOffsets,
      ),
    },
  });
  rerender(host, store);
  if (pairwiseEvidence && String(pairwiseEvidence.status || "") === "loading") {
    loadSubviewPairwiseEvidence(host, store, nextSubview.summary);
  }
}

function selectSubviewCandidate(args) {
  return selectSubviewCandidateImpl(args);
}

function selectSubviewTrack(args) {
  return selectSubviewTrackImpl(args);
}

function removeSubviewCandidate(args) {
  return removeSubviewCandidateImpl(args);
}

function removeSubviewTrackSelection(args) {
  return removeSubviewTrackSelectionImpl(args);
}

function swapSubviewSummaryOrder(args) {
  return swapSubviewSummaryOrderImpl(args);
}

function buildSubviewSummaryFromCandidates(args) {
  return buildSubviewSummaryFromCandidatesImpl(args);
}

function buildSubviewSummaryFromTrackSelections(args) {
  return buildSubviewSummaryFromTrackSelectionsImpl(args);
}

function resolveSubviewCtgOrder(ctg) {
  return resolveSubviewCtgOrderImpl(ctg);
}

function normalizeSubviewSummarySelection(selection) {
  return normalizeSubviewSummarySelectionImpl(selection);
}

function buildSubviewPairwiseEvidenceKey(summary, scope = {}) {
  return buildSubviewPairwiseEvidenceKeyImpl(summary, scope);
}

function issueSubviewPairwiseEvidenceRequestKey(summary, scope = {}) {
  const key = String(scope?.key || buildSubviewPairwiseEvidenceKey(summary, scope));
  if (!key) {
    return "";
  }
  subviewPairwiseEvidenceRequestSeq += 1;
  return `${key}|req:${subviewPairwiseEvidenceRequestSeq}`;
}

function shouldLoadSubviewPairwiseEvidence(summary) {
  return shouldLoadSubviewPairwiseEvidenceImpl(summary);
}

function buildInitialSubviewPairwiseEvidence(summary, trackPrefs = {}, previousEvidence = null, state = null) {
  if (!shouldLoadSubviewPairwiseEvidence(summary)) {
    return null;
  }
  const prefs = resolveTrackPrefs(trackPrefs || {});
  const scope = resolveSubviewPairwiseEvidenceScope(state || { assembly: {} }, summary) || {};
  const key = String(scope?.key || buildSubviewPairwiseEvidenceKey(summary, scope));
  const previousForKey =
    previousEvidence && String(previousEvidence?.key || "") === key
      ? previousEvidence
      : null;
  const requestedMinAlignmentLength = Math.max(1, normalizePositiveInt(prefs.alignmentLength) ?? 1);
  const requestedMinMapq = Math.max(0, normalizeNonNegativeInt(prefs.mapq) ?? 0);
  const loadedMinAlignmentLength = Math.max(
    1,
    normalizePositiveInt(previousForKey?.loadedMinAlignmentLength ?? previousForKey?.minAlignmentLength)
      ?? requestedMinAlignmentLength,
  );
  const loadedMinMapq = Math.max(
    0,
    normalizeNonNegativeInt(previousForKey?.loadedMinMapq ?? previousForKey?.minMapq)
      ?? requestedMinMapq,
  );
  const shouldRefetch = shouldRefetchSubviewPairwiseEvidence({
    summary,
    trackPrefs: prefs,
    evidence: previousForKey,
    scope,
  });
  return {
    key,
    requestKey: shouldRefetch
      ? issueSubviewPairwiseEvidenceRequestKey(summary, scope)
      : String(previousForKey?.requestKey || ""),
    requestedMinAlignmentLength,
    requestedMinMapq,
    loadedMinAlignmentLength,
    loadedMinMapq,
    minAlignmentLength: requestedMinAlignmentLength,
    minMapq: requestedMinMapq,
    status: shouldRefetch ? "loading" : String(previousForKey?.status || "loaded"),
    hits: Array.isArray(previousForKey?.hits) ? previousForKey.hits : [],
    evidenceSource: String(previousForKey?.evidenceSource || ""),
    evidenceHitCount: Number(previousForKey?.evidenceHitCount || 0),
    error: shouldRefetch ? "" : String(previousForKey?.error || ""),
  };
}

function resolveSubviewPairwiseEvidenceScope(state, summary) {
  if (!shouldLoadSubviewPairwiseEvidence(summary)) {
    return null;
  }
  const mode = String(summary?.mode || "").trim();
  if (mode === "track-pair") {
    const topTrack = normalizeSubviewTrackSummary(summary?.topTrack);
    const bottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
    const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
    const topAssemblyCtgIds = resolveSubviewTrackSummaryCtgs(topTrack, pools)
      .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
      .filter((value) => value);
    const bottomAssemblyCtgIds = resolveSubviewTrackSummaryCtgs(bottomTrack, pools)
      .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
      .filter((value) => value);
    return {
      mode: "track-pair",
      topAssemblyCtgIds,
      bottomAssemblyCtgIds,
      key: buildSubviewPairwiseEvidenceKey(summary, {
        topAssemblyCtgIds,
        bottomAssemblyCtgIds,
      }),
    };
  }
  return {
    mode: "2-contig",
    key: buildSubviewPairwiseEvidenceKey(summary),
  };
}

function resolveSubviewPairwiseEvidenceParams(state, summary) {
  const scope = resolveSubviewPairwiseEvidenceScope(state, summary);
  if (!scope?.key) {
    return null;
  }
  const workspaceRoot = String(state.session?.workspacePath || "").trim();
  const projectId = Number(state.session?.projectId || 0);
  if (!workspaceRoot || !projectId) {
    return null;
  }
  const evidence = state.assembly?.subview?.pairwiseEvidence || null;
  const prefs = resolveTrackPrefs(state.assembly?.subviewTrackView || state.assembly?.trackView || {});
  const baseParams = {
    mode: scope.mode,
    key: scope.key,
    requestKey: String(evidence?.requestKey || ""),
    workspaceRoot,
    projectId,
    minAlignmentLength: Math.max(
      1,
      normalizePositiveInt(evidence?.requestedMinAlignmentLength ?? prefs.alignmentLength) ?? 1,
    ),
    minMapq: Math.max(
      0,
      normalizeNonNegativeInt(evidence?.requestedMinMapq ?? prefs.mapq) ?? 0,
    ),
  };
  if (scope.mode === "track-pair") {
    if (!scope.topAssemblyCtgIds?.length || !scope.bottomAssemblyCtgIds?.length) {
      return null;
    }
    return {
      ...baseParams,
      topAssemblyCtgIds: scope.topAssemblyCtgIds,
      bottomAssemblyCtgIds: scope.bottomAssemblyCtgIds,
    };
  }
  const top = normalizeSubviewSummarySelection(summary?.top);
  const bottom = normalizeSubviewSummarySelection(summary?.bottom);
  if (!top?.contigId || !bottom?.contigId) {
    return null;
  }
  return {
    ...baseParams,
    leftAssemblyCtgId: top.contigId,
    rightAssemblyCtgId: bottom.contigId,
  };
}

function resolveCurrentSubviewPairwiseEvidenceKey(state) {
  const summary = state.assembly?.subview?.summary || null;
  const scope = resolveSubviewPairwiseEvidenceScope(state, summary);
  return String(scope?.key || buildSubviewPairwiseEvidenceKey(summary) || "");
}

async function loadSubviewPairwiseEvidence(host, store, summary) {
  const startState = store.getState();
  const params = resolveSubviewPairwiseEvidenceParams(startState, summary);
  if (!params) {
    return;
  }
  try {
    const report = params.mode === "track-pair"
      ? await getTrackPairwiseEvidence(params)
      : await getJunctionInspection(params);
    const currentState = store.getState();
    if (
      resolveCurrentSubviewPairwiseEvidenceKey(currentState) !== params.key
      || String(currentState.assembly?.subview?.pairwiseEvidence?.key || "") !== params.key
      || String(currentState.assembly?.subview?.pairwiseEvidence?.requestKey || "") !== params.requestKey
    ) {
      return;
    }
    store.setState({
      assembly: {
        ...currentState.assembly,
        subview: {
          ...getSubviewState(currentState.assembly),
          pairwiseEvidence: {
            key: params.key,
            requestKey: params.requestKey,
            requestedMinAlignmentLength: params.minAlignmentLength,
            requestedMinMapq: params.minMapq,
            loadedMinAlignmentLength: params.minAlignmentLength,
            loadedMinMapq: params.minMapq,
            minAlignmentLength: params.minAlignmentLength,
            minMapq: params.minMapq,
            status: "loaded",
            hits: Array.isArray(report?.hits) ? report.hits : [],
            evidenceSource: String(report?.evidenceSource || ""),
            evidenceHitCount: Number(report?.evidenceHitCount || 0),
            error: "",
          },
        },
      },
    });
    scheduleDeferredSubviewPanelRerender(host, store);
  } catch (error) {
    const currentState = store.getState();
    if (
      resolveCurrentSubviewPairwiseEvidenceKey(currentState) !== params.key
      || String(currentState.assembly?.subview?.pairwiseEvidence?.key || "") !== params.key
      || String(currentState.assembly?.subview?.pairwiseEvidence?.requestKey || "") !== params.requestKey
    ) {
      return;
    }
    store.setState({
      assembly: {
        ...currentState.assembly,
        subview: {
          ...getSubviewState(currentState.assembly),
          pairwiseEvidence: {
            key: params.key,
            requestKey: params.requestKey,
            requestedMinAlignmentLength: params.minAlignmentLength,
            requestedMinMapq: params.minMapq,
            loadedMinAlignmentLength: Math.max(
              1,
              normalizePositiveInt(currentState.assembly?.subview?.pairwiseEvidence?.loadedMinAlignmentLength
                ?? currentState.assembly?.subview?.pairwiseEvidence?.minAlignmentLength
                ?? params.minAlignmentLength)
                ?? params.minAlignmentLength,
            ),
            loadedMinMapq: Math.max(
              0,
              normalizeNonNegativeInt(currentState.assembly?.subview?.pairwiseEvidence?.loadedMinMapq
                ?? currentState.assembly?.subview?.pairwiseEvidence?.minMapq
                ?? params.minMapq)
                ?? params.minMapq,
            ),
            minAlignmentLength: params.minAlignmentLength,
            minMapq: params.minMapq,
            status: "error",
            hits: Array.isArray(currentState.assembly?.subview?.pairwiseEvidence?.hits)
              ? currentState.assembly.subview.pairwiseEvidence.hits
              : [],
            error: mapAssemblyError({ error, stateOrLocale: currentState }),
          },
        },
      },
    });
    scheduleDeferredSubviewPanelRerender(host, store);
  }
}

function resolveSubviewSelectionCtg(selection, supportContext) {
  return resolveSubviewSelectionCtgImpl(selection, supportContext);
}

function resolveSubviewTrackSummaryCtgs(trackSelection, supportContext) {
  return resolveSubviewTrackSummaryCtgsImpl(trackSelection, supportContext);
}

function resolveSubviewTrackRoleCtgs(trackRole, supportContext) {
  return resolveSubviewTrackRoleCtgsImpl(trackRole, supportContext);
}

function filterSubviewTrackPairHiddenCtgs(values, pools) {
  return filterSubviewTrackPairHiddenCtgsImpl(values, pools);
}

function filterSubviewTrackPairSelectionCtgs(values, pools) {
  return filterSubviewTrackPairSelectionCtgsImpl(values, pools);
}

function buildSubviewTrackPairPoolsFromAssembly(assembly) {
  return buildSubviewTrackPairPoolsFromAssemblyImpl(assembly);
}

function resolveFilteredSubviewTrackPairSelectionsFromAssembly(assembly) {
  return resolveFilteredSubviewTrackPairSelectionsFromAssemblyImpl(assembly);
}

function enterSubviewFromCandidates(host, store) {
  const state = store.getState();
  const currentProject = getCurrentProject(state);
  const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
  const result = buildSubviewSummaryFromCandidates({
    subview: state.assembly.subview,
    primaryCtgs: pools.primaryCtgs,
    supportCtgs: pools.supportCtgs,
    refCtgs: pools.refCtgs,
    phasedCtgs: pools.phasedCtgs,
    datasets: state.initializer?.datasets || [],
    primaryDatasetId: normalizeSupportDatasetId(currentProject?.primaryDatasetId),
    supportDatasetId: normalizeSupportDatasetId(state.assembly.supportDatasetId),
    stateOrLocale: state,
  });
  const currentSubview = getSubviewState(state.assembly);
  if (!result.ok) {
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...currentSubview,
          activeAnchors: [],
          flippedCtgs: [],
          error: result.error,
          summary: null,
        },
        subviewTrackDragOffsets: [],
      },
    });
    rerender(host, store);
    return;
  }
  const nextSubviewTrackView = inheritSubviewTrackViewFromMainTrack(state.assembly);
  const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
    result.value,
    nextSubviewTrackView,
    currentSubview.pairwiseEvidence,
    state,
  );
  store.setState({
    assembly: {
      ...state.assembly,
      subviewTrackView: nextSubviewTrackView,
        subview: {
          ...currentSubview,
          activeAnchors: [],
          flippedCtgs: [],
          selectedTrackSelections: [],
        selectedTrackARole: "",
        selectedTrackBRole: "",
        selectedTrackBSource: "",
        selectedTrackBDatasetId: null,
        selectedTrackBIsMirror: false,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
        summary: result.value,
        pairwiseEvidence,
        error: "",
        message: tAssembly(state, "subview.entered"),
      },
      subviewTrackDragOffsets: [],
    },
  });
  rerender(host, store);
  if (pairwiseEvidence && String(pairwiseEvidence.status || "") === "loading") {
    loadSubviewPairwiseEvidence(host, store, result.value);
  }
}

function refreshSubviewPairwiseEvidence(host, store) {
  const state = store.getState();
  const summary = state.assembly?.subview?.summary || null;
  const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
    summary,
    state.assembly?.subviewTrackView || state.assembly?.trackView,
    state.assembly?.subview?.pairwiseEvidence,
    state,
  );
  if (!pairwiseEvidence) {
    return;
  }
  const currentEvidence = state.assembly?.subview?.pairwiseEvidence || null;
  const shouldFetch = String(pairwiseEvidence.requestKey || "") !== String(currentEvidence?.requestKey || "");
  const shouldUpdateState = JSON.stringify(pairwiseEvidence) !== JSON.stringify(currentEvidence || null);
  if (!shouldUpdateState && !shouldFetch) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...getSubviewState(state.assembly),
        pairwiseEvidence,
      },
    },
  });
  if (shouldUpdateState) {
    rerender(host, store);
  }
  if (shouldFetch) {
    loadSubviewPairwiseEvidence(host, store, summary);
  }
}

function cancelSubviewPairwiseEvidence(host, store, options = {}) {
  const rerenderImpl = typeof options?.rerender === "function" ? options.rerender : rerender;
  const rerenderAfter = options?.rerenderAfter !== false;
  const state = store.getState();
  const currentSubview = getSubviewState(state.assembly);
  const evidence = currentSubview?.pairwiseEvidence || null;
  if (!evidence || String(evidence?.status || "") !== "loading") {
    return false;
  }
  const nextAlignmentLength = Math.max(
    1,
    normalizePositiveInt(
      evidence?.loadedMinAlignmentLength
      ?? evidence?.minAlignmentLength
      ?? state.assembly?.subviewTrackView?.alignmentLength,
    ) ?? 1,
  );
  const nextMapq = Math.max(
    0,
    normalizeNonNegativeInt(
      evidence?.loadedMinMapq
      ?? evidence?.minMapq
      ?? state.assembly?.subviewTrackView?.mapq,
    ) ?? 0,
  );
  const hasCachedHits = Array.isArray(evidence?.hits) && evidence.hits.length > 0;
  store.setState({
    assembly: {
      ...state.assembly,
      subviewTrackView: {
        ...resolveTrackPrefs(state.assembly?.subviewTrackView || state.assembly?.trackView || {}),
        alignmentLength: nextAlignmentLength,
        mapq: nextMapq,
      },
      subview: {
        ...currentSubview,
        pairwiseEvidence: {
          ...evidence,
          requestKey: "",
          requestedMinAlignmentLength: nextAlignmentLength,
          requestedMinMapq: nextMapq,
          loadedMinAlignmentLength: nextAlignmentLength,
          loadedMinMapq: nextMapq,
          minAlignmentLength: nextAlignmentLength,
          minMapq: nextMapq,
          status: hasCachedHits ? "loaded" : "cancelled",
          error: "",
        },
      },
    },
  });
  if (rerenderAfter) {
    rerenderImpl(host, store);
  }
  return true;
}

function enterSubviewFromTrackSelections(host, store) {
  const state = store.getState();
  const result = buildSubviewSummaryFromTrackSelections({
    subview: state.assembly.subview,
    stateOrLocale: state,
  });
  const currentSubview = getSubviewState(state.assembly);
  if (!result.ok) {
    store.setState({
      assembly: {
        ...state.assembly,
        subview: {
          ...currentSubview,
          activeAnchors: [],
          flippedCtgs: [],
          error: result.error,
          summary: null,
        },
        subviewTrackDragOffsets: [],
      },
    });
    rerender(host, store);
    return;
  }
  const nextSubviewTrackView = inheritSubviewTrackViewFromMainTrack(state.assembly);
  const pairwiseEvidence = buildInitialSubviewPairwiseEvidence(
    result.value,
    nextSubviewTrackView,
    currentSubview.pairwiseEvidence,
    state,
  );
  store.setState({
    assembly: {
      ...state.assembly,
      subviewTrackView: nextSubviewTrackView,
      subview: {
        ...currentSubview,
        activeAnchors: [],
        flippedCtgs: [],
        selectedAContigId: null,
        selectedARole: "",
        selectedBContigId: null,
        selectedBRole: "",
        summary: result.value,
        pairwiseEvidence,
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
        error: "",
        message: tAssembly(state, "subview.enteredTrackMode"),
      },
      subviewTrackDragOffsets: [],
    },
  });
  rerender(host, store);
  if (pairwiseEvidence && String(pairwiseEvidence.status || "") === "loading") {
    loadSubviewPairwiseEvidence(host, store, result.value);
  }
}

function inheritSubviewTrackViewFromMainTrack(assembly) {
  const mainTrackPrefs = resolveTrackPrefs(assembly?.trackView);
  return {
    ...(assembly?.subviewTrackView || {}),
    supportDsCtgLen: mainTrackPrefs.supportDsCtgLen,
    minTickUnitKb: mainTrackPrefs.minTickUnitKb,
    minTickKb: mainTrackPrefs.minTickUnitKb,
    maxTickCount: mainTrackPrefs.maxTickCount,
    alignmentLength: mainTrackPrefs.alignmentLength,
    block_length: mainTrackPrefs.alignmentLength,
    mapq: mainTrackPrefs.mapq,
  };
}

function setSubviewTrackPairCtgHidden(host, store, { trackRole, contigId, hidden = true }) {
  const normalizedTrackRole = normalizeTrackRole(trackRole);
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  if (!normalizedTrackRole || !normalizedContigId) {
    return;
  }
  const state = store.getState();
  const currentSubview = getSubviewState(state.assembly);
  if (String(currentSubview.summary?.mode || "") !== "track-pair") {
    return;
  }
  const current = normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs);
  const targetKey = buildSubviewTrackPairHiddenCtgKey(normalizedTrackRole, normalizedContigId);
  const next = hidden
    ? normalizeSubviewTrackPairHiddenCtgs([
        ...current,
        {
          trackRole: normalizedTrackRole,
          contigId: normalizedContigId,
        },
      ])
    : current.filter(
      (entry) => buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId) !== targetKey,
    );
  const nextSelections = getSubviewTrackPairSelections(currentSubview).filter(
    (entry) => !next.some(
      (hiddenEntry) =>
        buildSubviewTrackPairHiddenCtgKey(hiddenEntry.trackRole, hiddenEntry.contigId)
          === buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...currentSubview,
        trackPairHiddenCtgs: next,
        trackPairSelectedCtgs: nextSelections,
      },
    },
  });
  rerender(host, store);
}

function toggleSubviewAnchorEdge(host, store, { hitKey, edge }) {
  const state = store.getState();
  const currentSubview = getSubviewState(state.assembly);
  const nextActiveAnchors = toggleSubviewAnchorEdgeImpl(currentSubview.activeAnchors, { hitKey, edge });
  if (
    nextActiveAnchors.length === currentSubview.activeAnchors.length
    && nextActiveAnchors.every((entry, index) =>
      entry.hitKey === currentSubview.activeAnchors[index]?.hitKey
      && entry.edge === currentSubview.activeAnchors[index]?.edge)
  ) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...currentSubview,
        activeAnchors: nextActiveAnchors,
      },
    },
  });
  rerender(host, store);
}

function toggleSubviewContigFlip(host, store, { slot, assemblyCtgId }, options = {}) {
  const normalizedSlot = String(slot || "").trim().toLowerCase();
  const normalizedContigId = normalizeSupportDatasetId(assemblyCtgId);
  if ((normalizedSlot !== "top" && normalizedSlot !== "bottom") || !normalizedContigId) {
    return;
  }
  const state = store.getState();
  const currentSubview = getSubviewState(state.assembly);
  if (!currentSubview.summary) {
    return;
  }
  const current = normalizeSubviewFlippedCtgs(currentSubview.flippedCtgs);
  const next = current.some((entry) => entry.slot === normalizedSlot && entry.contigId === normalizedContigId)
    ? current.filter((entry) => !(entry.slot === normalizedSlot && entry.contigId === normalizedContigId))
    : [...current, { slot: normalizedSlot, contigId: normalizedContigId }];
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...currentSubview,
        flippedCtgs: next,
      },
    },
  });
  const rerenderSubview = typeof options.rerenderSubviewPanel === "function"
    ? options.rerenderSubviewPanel
    : rerenderSubviewPanel;
  rerenderSubview(host, store);
}

function clearSubviewTrackPairHiddenCtgs(host, store) {
  const state = store.getState();
  const currentSubview = getSubviewState(state.assembly);
  if (!normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs).length) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...currentSubview,
        trackPairHiddenCtgs: [],
      },
    },
  });
  rerender(host, store);
}

function normalizeTrackFocusMode(rawMode) {
  return String(rawMode || "").trim().toLowerCase() === "start" ? "start" : "center";
}

export function bindAssemblyPage(host, store) {
  const result = bindAssemblyPageImpl(host, store, createAssemblyPageBindingDeps());
  scrollAssemblyToBottomIfRequested(host, store);
  return result;
}

function scrollAssemblyToBottomIfRequested(host, store) {
  const state = store.getState();
  if (!state.assembly?.projectExportScrollToBottom || state.assembly.loading) {
    return;
  }
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      projectExportScrollToBottom: false,
    },
  });
  const routeHost = resolveCurrentRouteHost(host) || host;
  const doc = routeHost?.ownerDocument || globalThis.document;
  const scrollTarget = routeHost?.querySelector?.(".final-path-card")
    || routeHost?.querySelector?.("[data-final-path-graph-viewport]")
    || routeHost;
  const scrollContainers = [
    routeHost?.closest?.(".stage-panel"),
    doc?.scrollingElement,
    doc?.documentElement,
    doc?.body,
  ].filter(Boolean);
  const applyScroll = () => {
    scrollTarget?.scrollIntoView?.({ block: "end" });
    scrollContainers.forEach((node) => {
      node.scrollTop = node.scrollHeight;
    });
  };
  const requestFrame = globalThis.requestAnimationFrame || ((callback) => globalThis.setTimeout(callback, 0));
  requestFrame(() => requestFrame(applyScroll));
}

function createAssemblyPageBindingDeps() {
  return {
    appendFinalPathRow,
    createEmptyFinalPathRow,
    applySupportDatasetSelection,
    cancelSubviewPairwiseEvidence,
    bindAssemblyActionFeedbackDismiss,
    bindAssemblyContextMenu: (host, store) => bindAssemblyContextMenuImpl(host, store, contextMenuRuntimeDeps),
    bindCtgActions: (host, store) => bindCtgActionsImpl(host, store, {
      ...ctgActionsRuntimeDeps,
      confirm: (message) => requestAssemblyConfirm(host, store, message),
    }),
    bindDeletedMemberChipBoxSelection: (host, store) => bindDeletedMemberChipBoxSelectionImpl(
      host,
      store,
      memberChipSelectionRuntimeDeps,
    ),
    exportFinalPathArtifacts: (payload) => launchFinalPathExportJobImpl({
      ...payload,
      deps: {
        ...payload?.deps,
        getMeasuredTrackViewportPx: (role) => getMeasuredTrackViewportPx(role),
        rerender,
        mapAssemblyError,
        pickDirectoryPath,
        pickSaveFilePath,
        exportDegapJobs,
        exportFinalPathFasta,
        writeFinalPathExportBinaryFile,
        writeFinalPathExportTextFile,
      },
    }),
    bindDegapCard: (host, store) => bindDegapCardImpl(host, store, {
      rerender,
      confirm: (message) => requestAssemblyConfirm(host, store, message),
      mapAssemblyError,
      persistDegapProjectState: (nextHost, nextStore) =>
        persistProjectAssemblyViewStateFromStore(nextHost, nextStore, projectAssemblyViewStateRuntimeDeps),
    }),
    bindBandCanvasRuntime: (host) => bindBandCanvasRuntimeImpl(host),
    bindSeqActions: (host, store) => bindSeqActionsImpl(host, store, seqActionsRuntimeDeps),
    bindStickyCtgLabels: (host) => bindStickyCtgLabelsImpl(host),
    bindSubviewBandTooltips,
    bindSubviewTrackContigDrag: (host, store) => bindSubviewTrackContigDragImpl(host, store, trackDragRuntimeDeps),
    bindTrackBoxSelection: (host, store) => bindTrackBoxSelectionImpl(host, store, trackSelectionRuntimeDeps),
    bindTrackContigDrag: (host, store) => bindTrackContigDragImpl(host, store, trackDragRuntimeDeps),
    bindTrackScrollSync,
    bindTrackSelectionHotkeys: (host, store) => bindTrackSelectionHotkeysImpl(host, store, trackHotkeyBindingDeps),
    bindTrackViewportResize,
    createPhasedChrTrack,
    handleNewSequenceRowAction,
    handleSubviewCandidateRemoval,
    handleSubviewSwapTrackOrder,
    handleSubviewTrackSelectionRemoval,
    handleTrackSubviewCandidateSelection,
    handleTrackSubviewTrackSelection,
    loadAssemblyView,
    loadNewSequencesTab,
    normalizeTrackFocusMode,
    markNextTrackAutoFocusSuppressed: () => {
      suppressNextTrackAutoFocus = true;
    },
    persistMainTrackViewState,
    requestAssemblyConfirm,
    rerenderAssemblyMainTab,
    refreshSubviewPairwiseEvidence,
    rememberTrackViewportAnchor,
    rerender,
    resolveAssemblyConfirmDialog,
    resolveTrackContigClickAction,
    removeFinalPathRow,
    restoreSelectedDeletedCtgs: editorActionRuntimeAdapters.restoreSelectedDeletedCtgs,
    runCtgSearch,
    selectChromosome,
    selectCtg,
    setAssemblyActionFeedback,
    setActivePhasedFinalPathTrack,
    shouldSuppressTrackContigClick,
    syncSupportDatasetSelection,
    togglePrimaryTrackSelection,
    moveFinalPathRow,
    updateFinalPathRow,
    updateDeletedCtgSelection,
  };
}

function normalizeTrackViewportRole(role) {
  const normalized = String(role || "").trim().toLowerCase();
  if (normalized === "subview") {
    return "subview";
  }
  if (normalized === "final-path" || normalized === "finalpath") {
    return "finalPath";
  }
  return "primary";
}

function normalizeViewportWidthValue(value) {
  const numeric = Math.round(Number(value || 0));
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}

function normalizeTrackViewportWidths(widths) {
  if (typeof widths === "number") {
    const resolvedWidth = normalizeViewportWidthValue(widths);
    return {
      primary: resolvedWidth,
      subview: resolvedWidth,
      finalPath: resolvedWidth,
    };
  }
  return {
    primary: normalizeViewportWidthValue(widths?.primary),
    subview: normalizeViewportWidthValue(widths?.subview),
    finalPath: normalizeViewportWidthValue(widths?.finalPath ?? widths?.["final-path"]),
  };
}

function resolveMeasuredTrackViewportWidths(nextWidths, currentWidths = measuredTrackViewportPxByRole) {
  const normalizedCurrent = normalizeTrackViewportWidths(currentWidths);
  const normalizedNext = normalizeTrackViewportWidths(nextWidths);
  return {
    primary: normalizedNext.primary || normalizedCurrent.primary || 1200,
    subview: normalizedNext.subview || normalizedCurrent.subview || normalizedCurrent.primary || 1200,
    finalPath: normalizedNext.finalPath || normalizedCurrent.finalPath || normalizedCurrent.primary || 1200,
  };
}

function haveMeasuredTrackViewportWidthsChanged(currentWidths, nextWidths) {
  const normalizedCurrent = normalizeTrackViewportWidths(currentWidths);
  const normalizedNext = normalizeTrackViewportWidths(nextWidths);
  return ["primary", "subview", "finalPath"].some((role) => {
    const nextValue = normalizedNext[role];
    if (nextValue <= 0) {
      return false;
    }
    return Math.abs(nextValue - normalizedCurrent[role]) > 1;
  });
}

function getMeasuredTrackViewportPx(role = "primary") {
  const normalizedRole = normalizeTrackViewportRole(role);
  return measuredTrackViewportPxByRole[normalizedRole] || measuredTrackViewportPxByRole.primary || 1200;
}

function readAssemblyTrackViewportWidths(host) {
  const primaryScroll = host?.querySelector?.(".assembly-track-scroll[data-track-role='primary']") || null;
  const subviewScroll = host?.querySelector?.(".assembly-track-scroll.subview-track-scroll") || null;
  const finalPathScroll =
    host?.querySelector?.("[data-final-path-graph-viewport]")
    || host?.querySelector?.(".assembly-final-path-svg-wrap")
    || null;
  return {
    primary: normalizeViewportWidthValue(primaryScroll?.clientWidth),
    subview: normalizeViewportWidthValue(subviewScroll?.clientWidth),
    finalPath: normalizeViewportWidthValue(finalPathScroll?.clientWidth),
  };
}

function createEditorActionRuntimeAdapters(editorRuntimeDeps, impls = {}) {
  const {
    applyEditorAction = applyEditorActionImpl,
    deleteSelectedSubviewTrackPairCtgs = deleteSelectedSubviewTrackPairCtgsImpl,
    deleteSelectedTrackCtgs = deleteSelectedTrackCtgsImpl,
    restoreSelectedDeletedCtgs = restoreSelectedDeletedCtgsImpl,
    runBatchDeleteTrackCtgs = runBatchDeleteTrackCtgsImpl,
    runBatchRestoreDeletedCtgs = runBatchRestoreDeletedCtgsImpl,
  } = impls;

  const batchRefreshRuntimeDeps = {
    ...editorRuntimeDeps,
    loadAssemblyView:
      editorRuntimeDeps.loadAssemblyViewForLocalAssemblyRefresh || editorRuntimeDeps.loadAssemblyView,
    localRefresh: true,
    rerender: editorRuntimeDeps.rerenderAssemblyMainTab || editorRuntimeDeps.rerender,
  };
  const batchDeleteRuntimeDeps = {
    ...batchRefreshRuntimeDeps,
    runBatchDeleteTrackCtgs: (host, store, selectedIds, options = {}) => runBatchDeleteTrackCtgs(
      host,
      store,
      selectedIds,
      batchRefreshRuntimeDeps,
      options,
    ),
  };
  const batchRestoreRuntimeDeps = {
    ...batchRefreshRuntimeDeps,
    runBatchRestoreDeletedCtgs: (host, store, selectedRecordIds, options = {}) => runBatchRestoreDeletedCtgs(
      host,
      store,
      selectedRecordIds,
      batchRefreshRuntimeDeps,
      options,
    ),
  };

  return {
    applyEditorAction: (host, store, payload) => applyEditorAction(host, store, payload, editorRuntimeDeps),
    deleteSelectedSubviewTrackPairCtgs: (host, store, selectedEntries) => deleteSelectedSubviewTrackPairCtgs(
      host,
      store,
      selectedEntries,
      editorRuntimeDeps,
      {
        confirm: (message) => editorRuntimeDeps.confirm(message, { host, store }),
      },
    ),
    deleteSelectedTrackCtgs: (host, store, selectedIds) => deleteSelectedTrackCtgs(
      host,
      store,
      selectedIds,
      batchDeleteRuntimeDeps,
      {
        confirm: (message) => batchDeleteRuntimeDeps.confirm(message, { host, store }),
      },
    ),
    restoreSelectedDeletedCtgs: (host, store, selectedRecordIds, options = {}) => restoreSelectedDeletedCtgs(
      host,
      store,
      selectedRecordIds,
      batchRestoreRuntimeDeps,
      options,
    ),
    runBatchDeleteTrackCtgs: batchDeleteRuntimeDeps.runBatchDeleteTrackCtgs,
    runBatchRestoreDeletedCtgs: batchRestoreRuntimeDeps.runBatchRestoreDeletedCtgs,
  };
}

const assemblyDataLoaderDeps = {
  getCtgDetail,
  listChrViewCtgs,
  listCtgEditCandidates,
  listDeletedCtgs,
  normalizeSupportDatasetId,
};

const assemblyDataRuntimeDeps = {
  applyEditorAction: (host, store, payload) => editorActionRuntimeAdapters.applyEditorAction(host, store, payload),
  buildClearedSubviewState,
  buildSubviewTrackPairHiddenCtgKey,
  buildSubviewTrackPairPoolsFromAssembly,
  filterPrimaryTrackSelectionCtgIds,
  filterSubviewTrackDragOffsetsBySummary,
  filterSubviewTrackPairHiddenCtgs,
  filterSubviewTrackPairSelectionCtgs,
  filterTrackDragOffsets,
  getCurrentProject,
  getProjectAssemblyViewState: (args) => loadProjectAssemblyViewStateImpl(args),
  getSupportDatasetOptions,
  listChrViewCtgs,
  listPhasedChrTracks,
  listProjectChromosomes,
  listReferenceTrackMembers,
  loadDatasetChrCtgs,
  loadDeletedCtgsForChr,
  loadSideDataForCtg,
  mapAssemblyError,
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
  normalizeSupportMirroredCtgs,
  normalizeTrackFocusMode,
  normalizeTrackSelectionCtgIds,
  rerender,
  selectCtg: (host, store, assemblyCtgId) => selectCtgImpl(
    host,
    store,
    assemblyCtgId,
    {},
    assemblyDataRuntimeDeps,
  ),
  setAssemblyActionFeedback,
  setPendingTrackAutoFocusMode: (mode) => {
    pendingTrackAutoFocusMode = mode;
  },
};

const projectAssemblyViewStateRuntimeDeps = {
  persistProjectAssemblyViewState: (args) => persistProjectAssemblyViewStateImpl(args),
};

const editorActionsRuntimeDeps = {
  appendAuditLog,
  buildActionAuditDetail,
  loadAssemblyView,
  loadAssemblyViewForLocalAssemblyRefresh,
  mapAssemblyError,
  rebaseTrackDragOffsetsAfterRestore,
  refreshPhasedTracksForCurrentChr,
  refreshAfterBatchDelete,
  rerender,
  rerenderAssemblyMainTab,
  rerenderBatchDeleteProgress,
  runAction: runCtgEditorAction,
  confirm: (message, context = {}) => requestAssemblyConfirm(context.host, context.store, message),
};

const editorActionRuntimeAdapters = createEditorActionRuntimeAdapters(editorActionsRuntimeDeps);

const contextMenuRuntimeDeps = {
  addFinalPathContigRelativeToSegment,
  addFinalPathGapRelativeToSegment,
  applyEditorAction: editorActionRuntimeAdapters.applyEditorAction,
  buildRenameCtgActionArgs,
  canEditTrackCtg,
  clearSubviewTrackPairHiddenCtgs,
  deleteFinalPathSegment,
  deleteSelectedSubviewTrackPairCtgs: editorActionRuntimeAdapters.deleteSelectedSubviewTrackPairCtgs,
  deleteSelectedTrackCtgs: editorActionRuntimeAdapters.deleteSelectedTrackCtgs,
  runBatchDeleteTrackCtgs: editorActionRuntimeAdapters.runBatchDeleteTrackCtgs,
  enterSubviewFromCandidates,
  enterSubviewFromTrackSelections,
  escapeAttr,
  escapeHtml,
  flipFinalPathSegment,
  addTrackContigToPhasedTrack,
  deletePhasedTrack,
  importAddCtgIntoTrack,
  openAssemblyContextMenuAt: () => {},
  promptForRenameCtg,
  promptForDeleteShorterThanLength,
  confirm: (message, context = {}) => requestAssemblyConfirm(context.host, context.store, message),
  setAssemblyActionFeedback,
  restoreSelectedDeletedCtgs: editorActionRuntimeAdapters.restoreSelectedDeletedCtgs,
  rerender,
  appendTrackContigToFinalPath,
  removePhasedTrackItem,
  setSelectedPrimaryTrackCtgsHidden,
  setActiveHitsTrack,
  setSubviewTrackPairCtgHidden,
  togglePrimaryTrackCtgHidden,
  toggleSubviewContigFlip,
  toggleSubviewAnchorEdge,
  toggleSupportTrackCtgMirror,
  updateDeletedCtgSelection,
  updateTrackSelection,
};

const trackDragRuntimeDeps = {
  applySubviewTrackDragOffset,
  applyTrackDragOffset,
  clearSubviewTrackDragPreview,
  clearTrackDragPreview,
  convertTrackOffsetPxToBp,
  persistSubviewTrackDragOffsets,
  persistTrackDragOffsets,
  previewSubviewTrackContigDrag,
  previewTrackContigDrag,
  resolveActiveTrackScrollElement,
  resolveSubviewTrackDragOffsetBp,
  resolveTrackDragOffsetBp,
  roundTrackMetric,
  setTrackContigDragActive: (value) => {
    trackContigDragActive = Boolean(value);
  },
  setSuppressTrackContigClickUntil: (value) => {
    suppressTrackContigClickUntil = value;
  },
};

const trackSelectionRuntimeDeps = {
  updateSubviewTrackPairSelection,
  updateTrackSelection,
};

const memberChipSelectionRuntimeDeps = {
  updateDeletedCtgSelection,
  updateTrackSelection,
};

const trackHotkeyActionDeps = {
  deleteSelectedSubviewTrackPairCtgs: editorActionRuntimeAdapters.deleteSelectedSubviewTrackPairCtgs,
  deleteSelectedTrackCtgs: editorActionRuntimeAdapters.deleteSelectedTrackCtgs,
};

const trackHotkeyBindingDeps = {
  handleTrackDeleteHotkey: (host, store, event, overrides = {}) => handleTrackDeleteHotkeyImpl(
    host,
    store,
    event,
    { ...trackHotkeyActionDeps, ...overrides },
  ),
};

const ctgActionsRuntimeDeps = {
  applyEditorAction: editorActionRuntimeAdapters.applyEditorAction,
};

const seqActionsRuntimeDeps = {
  applyEditorAction: editorActionRuntimeAdapters.applyEditorAction,
  pickSelectedMember,
};

async function handleNewSequenceRowAction(host, store, payload) {
  return handleNewSequenceRowActionImpl(host, store, payload, assemblyDataRuntimeDeps);
}

async function loadAssemblyView(host, store, options) {
  return loadAssemblyViewImpl(host, store, options, assemblyDataRuntimeDeps);
}

async function loadAssemblyViewForLocalAssemblyRefresh(host, store, options) {
  return loadAssemblyViewImpl(host, store, options, {
    ...assemblyDataRuntimeDeps,
    rerender: rerenderAssemblyMainTab,
  });
}

async function createPhasedChrTrack(host, store) {
  const state = store.getState();
  const workspaceRoot = state.session?.workspacePath;
  const projectId = state.session?.projectId;
  const parentChrName = String(state.assembly?.selectedChrName || "").trim();
  if (!workspaceRoot || !projectId || !parentChrName) {
    return;
  }
  try {
    await createPhasedChrTrackApi({
      workspaceRoot,
      projectId,
      parentChrName,
    });
    await refreshPhasedTracksForCurrentChr(host, store);
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: "",
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackCreated"),
    });
  } catch (error) {
    const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: mappedError.userMessage,
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackCreateFailed"),
    });
  }
}

function hydratePhasedTracksForCurrentAssembly(tracks, assembly) {
  const primaryById = new Map(
    (Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [])
      .map((ctg) => [normalizeSupportDatasetId(ctg?.assemblyCtgId), ctg])
      .filter(([ctgId]) => ctgId !== null),
  );
  return (Array.isArray(tracks) ? tracks : [])
    .map((track) => ({
      ...track,
      phasedTrackId: normalizeSupportDatasetId(track?.phasedTrackId),
      displayOrder: Number(track?.displayOrder || 0),
      haplotypeKey: String(track?.haplotypeKey || "").trim(),
      label: String(track?.label || "").trim(),
      items: (Array.isArray(track?.items) ? track.items : [])
        .slice()
        .sort((left, right) =>
          Number(left?.displayOrder || 0) - Number(right?.displayOrder || 0)
          || Number(left?.itemId || left?.phasedTrackItemId || 0) - Number(right?.itemId || right?.phasedTrackItemId || 0),
        )
        .map((item) => ({
          ...item,
          itemId: normalizeSupportDatasetId(item?.itemId ?? item?.phasedTrackItemId),
          phasedTrackId: normalizeSupportDatasetId(item?.phasedTrackId ?? track?.phasedTrackId),
          assemblyCtgId: normalizeSupportDatasetId(item?.assemblyCtgId),
          sourceCtg: primaryById.get(normalizeSupportDatasetId(item?.assemblyCtgId)) || item?.sourceCtg || null,
        })),
    }))
    .filter((track) => track.phasedTrackId && track.haplotypeKey)
    .sort((left, right) => left.displayOrder - right.displayOrder || left.phasedTrackId - right.phasedTrackId);
}

function resolvePrimaryTrackDragOffsetForCtg(assembly, assemblyCtgId) {
  const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
  if (!normalizedCtgId) {
    return null;
  }
  const targetKey = buildTrackDragOffsetKey("primary", normalizedCtgId);
  return normalizeTrackDragOffsets(assembly?.trackDragOffsets).find(
    (entry) => buildTrackDragOffsetKey(entry.trackRole, entry.assemblyCtgId, entry) === targetKey,
  ) || null;
}

function inheritPrimaryTrackDragOffsetForPhasedItem(store, {
  assemblyCtgId,
  phasedTrackId,
  phasedTrackItemId,
}) {
  const state = store.getState();
  const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
  const normalizedTrackId = normalizeSupportDatasetId(phasedTrackId);
  const normalizedItemId = normalizeSupportDatasetId(phasedTrackItemId);
  if (!normalizedCtgId || !normalizedTrackId || !normalizedItemId) {
    return false;
  }
  const sourceOffset = resolvePrimaryTrackDragOffsetForCtg(state.assembly, normalizedCtgId);
  if (!sourceOffset) {
    return false;
  }
  const nextOffset = {
    trackRole: "phased",
    assemblyCtgId: normalizedCtgId,
    phasedTrackId: normalizedTrackId,
    phasedTrackItemId: normalizedItemId,
    ...(Number.isFinite(Number(sourceOffset.offsetBp))
      ? { offsetBp: sourceOffset.offsetBp }
      : { offsetPx: sourceOffset.offsetPx }),
  };
  const currentOffsets = normalizeTrackDragOffsets(state.assembly?.trackDragOffsets);
  const nextOffsets = setTrackDragOffset(currentOffsets, nextOffset);
  if (areTrackDragOffsetsEqual(currentOffsets, nextOffsets)) {
    return false;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      trackDragOffsets: nextOffsets,
    },
  });
  return true;
}

async function refreshPhasedTracksForCurrentChr(host, store) {
  const state = store.getState();
  const workspaceRoot = state.session?.workspacePath;
  const projectId = state.session?.projectId;
  const parentChrName = String(state.assembly?.selectedChrName || "").trim();
  if (!workspaceRoot || !projectId || !parentChrName) {
    return [];
  }
  const result = await listPhasedChrTracks({
    workspaceRoot,
    projectId,
    parentChrName,
  });
  const phasedChrTracks = hydratePhasedTracksForCurrentAssembly(result?.tracks, store.getState().assembly);
  const nextActiveKey = phasedChrTracks.some((track) =>
    track.haplotypeKey === store.getState().assembly?.activePhasedTrackKey,
  )
    ? store.getState().assembly.activePhasedTrackKey
    : (phasedChrTracks[0]?.haplotypeKey || "");
  store.setState({
    assembly: {
      ...store.getState().assembly,
      phasedChrTracks,
      isChrPhased: Boolean(phasedChrTracks.length),
      activePhasedTrackKey: nextActiveKey,
      activePhasedTrackKeyByChr: {
        ...(store.getState().assembly?.activePhasedTrackKeyByChr || {}),
        [parentChrName]: nextActiveKey,
      },
    },
  });
  rerenderAssemblyMainTab(host, store);
  return phasedChrTracks;
}

async function addTrackContigToPhasedTrack(host, store, { phasedTrackId, assemblyCtgId, haplotypeKey = "" }) {
  const state = store.getState();
  const workspaceRoot = state.session?.workspacePath;
  const projectId = state.session?.projectId;
  const normalizedTrackId = normalizeSupportDatasetId(phasedTrackId);
  const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
  const normalizedKey = String(haplotypeKey || "").trim();
  if (!workspaceRoot || !projectId || !normalizedTrackId || !normalizedCtgId) {
    return;
  }
  try {
    const addedResult = await addCtgToPhasedChrTrackApi({
      workspaceRoot,
      projectId,
      phasedTrackId: normalizedTrackId,
      assemblyCtgId: normalizedCtgId,
    });
    const inheritedDragOffset = inheritPrimaryTrackDragOffsetForPhasedItem(store, {
      assemblyCtgId: normalizedCtgId,
      phasedTrackId: normalizedTrackId,
      phasedTrackItemId: addedResult?.item?.itemId ?? addedResult?.item?.phasedTrackItemId,
    });
    if (state.assembly?.selectedChrName && normalizedKey) {
      store.setState({
        assembly: {
          ...store.getState().assembly,
          activePhasedTrackKey: normalizedKey,
          activePhasedTrackKeyByChr: {
            ...(store.getState().assembly?.activePhasedTrackKeyByChr || {}),
            [state.assembly.selectedChrName]: normalizedKey,
          },
        },
      });
    }
    await refreshPhasedTracksForCurrentChr(host, store);
    if (inheritedDragOffset) {
      void persistTrackDragOffsets(host, store);
    }
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: "",
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemAdded", { key: normalizedKey }),
    });
  } catch (error) {
    const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: mappedError.userMessage,
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemAddFailed"),
    });
  }
}

async function removePhasedTrackItem(host, store, { phasedTrackItemId }) {
  const state = store.getState();
  const workspaceRoot = state.session?.workspacePath;
  const projectId = state.session?.projectId;
  const normalizedItemId = normalizeSupportDatasetId(phasedTrackItemId);
  if (!workspaceRoot || !projectId || !normalizedItemId) {
    return;
  }
  try {
    await removePhasedChrTrackItemApi({
      workspaceRoot,
      projectId,
      phasedTrackItemId: normalizedItemId,
    });
    await refreshPhasedTracksForCurrentChr(host, store);
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: "",
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemRemoved"),
    });
  } catch (error) {
    const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: mappedError.userMessage,
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackItemRemoveFailed"),
    });
  }
}

function compactFinalPathByDeletedPhasedTrack(finalPathByChr, {
  parentChrName,
  tracksBefore,
  deletedPhasedTrackId,
}) {
  const source = finalPathByChr && typeof finalPathByChr === "object" ? finalPathByChr : {};
  const orderedTracks = (Array.isArray(tracksBefore) ? tracksBefore : [])
    .slice()
    .sort((left, right) =>
      Number(left?.displayOrder || 0) - Number(right?.displayOrder || 0)
      || Number(left?.phasedTrackId || 0) - Number(right?.phasedTrackId || 0),
    );
  const deletedIndex = orderedTracks.findIndex(
    (track) => normalizeSupportDatasetId(track?.phasedTrackId) === deletedPhasedTrackId,
  );
  if (deletedIndex < 0) {
    return { ...source };
  }
  const next = { ...source };
  const deletedLabel = String(orderedTracks[deletedIndex]?.label || "").trim();
  if (deletedLabel) {
    delete next[deletedLabel];
  }
  orderedTracks.slice(deletedIndex + 1).forEach((track, index) => {
    const oldLabel = String(track?.label || "").trim();
    const nextKey = String.fromCharCode("A".charCodeAt(0) + deletedIndex + index);
    const nextLabel = `${parentChrName}${nextKey}`;
    if (!oldLabel || oldLabel === nextLabel || !Object.prototype.hasOwnProperty.call(next, oldLabel)) {
      return;
    }
    next[nextLabel] = {
      ...next[oldLabel],
      chrName: nextLabel,
    };
    delete next[oldLabel];
  });
  return next;
}

function resolveActivePhasedKeyAfterDelete({ currentKey, tracksAfter, deletedKey }) {
  const keys = (Array.isArray(tracksAfter) ? tracksAfter : [])
    .map((track) => String(track?.haplotypeKey || "").trim())
    .filter(Boolean);
  if (!keys.length) {
    return "";
  }
  if (currentKey && currentKey !== deletedKey && keys.includes(currentKey)) {
    return currentKey;
  }
  if (deletedKey && keys.includes(deletedKey)) {
    return deletedKey;
  }
  return keys[Math.max(0, keys.length - 1)] || "";
}

async function deletePhasedTrack(host, store, { phasedTrackId, haplotypeKey = "" }) {
  const state = store.getState();
  const workspaceRoot = state.session?.workspacePath;
  const projectId = state.session?.projectId;
  const parentChrName = String(state.assembly?.selectedChrName || "").trim();
  const normalizedTrackId = normalizeSupportDatasetId(phasedTrackId);
  const normalizedKey = String(haplotypeKey || "").trim();
  if (!workspaceRoot || !projectId || !parentChrName || !normalizedTrackId) {
    return;
  }
  const tracksBefore = Array.isArray(state.assembly?.phasedChrTracks)
    ? state.assembly.phasedChrTracks
    : [];
  try {
    await deletePhasedChrTrackApi({
      workspaceRoot,
      projectId,
      phasedTrackId: normalizedTrackId,
    });
    const nextFinalPathByChr = compactFinalPathByDeletedPhasedTrack(state.assembly?.finalPathByChr, {
      parentChrName,
      tracksBefore,
      deletedPhasedTrackId: normalizedTrackId,
    });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        finalPathByChr: nextFinalPathByChr,
      },
    });
    const tracksAfter = await refreshPhasedTracksForCurrentChr(host, store);
    const nextActiveKey = resolveActivePhasedKeyAfterDelete({
      currentKey: state.assembly?.activePhasedTrackKey,
      tracksAfter,
      deletedKey: normalizedKey,
    });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        activePhasedTrackKey: nextActiveKey,
        activePhasedTrackKeyByChr: {
          ...(store.getState().assembly?.activePhasedTrackKeyByChr || {}),
          [parentChrName]: nextActiveKey,
        },
      },
    });
    rerenderAssemblyMainTab(host, store);
    await persistMainTrackViewState(host, store);
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: "",
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackDeleted", { key: normalizedKey }),
    });
  } catch (error) {
    const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
    setAssemblyActionFeedbackInMainTab(host, store, {
      actionError: mappedError.userMessage,
      actionStatus: tAssembly(store.getState(), "runtime.phasedTrackDeleteFailed"),
    });
  }
}

async function importAddCtgIntoTrack(host, store, payload = {}) {
  const snapshot = store.getState();
  const workspaceRoot = String(snapshot.session?.workspacePath || "").trim();
  const projectId = Number(snapshot.session?.projectId || 0);
  const selectedChrName = String(snapshot.assembly?.selectedChrName || "").trim();
  const targetChr = String(payload.targetChr || selectedChrName).trim();
  const targetTrack = String(payload.targetTrack || "").trim();
  if (!workspaceRoot || !projectId || !targetChr || !targetTrack) {
    setAssemblyActionFeedback(host, store, {
      actionStatus: "",
      actionError: tAssembly(snapshot, "runtime.addCtgImportMissingTarget"),
    });
    return;
  }
  const zipPath = await pickZipFilePath(snapshot);
  if (!zipPath) {
    return;
  }
  const runId = createAddCtgImportRunId();
  setAddCtgImportProgress(host, store, {
    open: true,
    status: "running",
    runId,
    summary: tAssembly(snapshot, "runtime.addCtgImportProgressSubtitle"),
    stages: [
      `workspace_root=${workspaceRoot}`,
      `project_id=${projectId}`,
      `target=${targetChr}/${targetTrack}`,
      `add_ctg_zip_path=${zipPath}`,
    ],
    error: "",
  });
  try {
    const result = await importAddCtgPackage({
      workspaceRoot,
      projectId,
      zipPath,
      expectedTargetChr: targetChr,
      expectedTargetTrack: targetTrack,
      runId,
      stateOrLocale: snapshot,
      onStage: (stage) => {
        if (String(store.getState().assembly?.addCtgImportProgress?.runId || "") !== runId) {
          return;
        }
        appendAddCtgImportStage(host, store, stage);
      },
    });
    if (String(store.getState().assembly?.addCtgImportProgress?.runId || "") !== runId) {
      return;
    }
    const importedMessage = result?.message || tAssembly(store.getState(), "runtime.addCtgImportDone");
    appendAddCtgImportStage(host, store, tAssembly(store.getState(), "runtime.addCtgImportRefreshStage"));
    await selectChromosome(host, store, targetChr);
    const latest = store.getState();
    store.setState({
      ...latest,
      initializer: {
        ...latest.initializer,
        ...(Array.isArray(result?.datasets) ? { datasets: result.datasets } : {}),
        ...(Array.isArray(result?.existingProjects) ? { existingProjects: result.existingProjects } : {}),
        ...(Array.isArray(result?.references) ? { references: result.references } : {}),
        ...(result?.packageMetadata ? { packageMetadata: result.packageMetadata } : {}),
      },
      assembly: {
        ...latest.assembly,
        addCtgImportProgress: {
          ...(latest.assembly?.addCtgImportProgress || {}),
          open: true,
          status: "success",
          summary: importedMessage,
          error: "",
        },
        actionStatus: tAssembly(latest, "runtime.addCtgImportDoneWithName", {
          ctgName: result?.ctgName || "-",
          targetTrack,
        }),
        actionError: "",
      },
    });
    rerender(host, store);
  } catch (error) {
    if (String(store.getState().assembly?.addCtgImportProgress?.runId || "") !== runId) {
      return;
    }
    const latest = store.getState();
    const mappedError = mapAssemblyError({ error, stateOrLocale: latest });
    store.setState({
      ...latest,
      assembly: {
        ...latest.assembly,
        addCtgImportProgress: {
          ...(latest.assembly?.addCtgImportProgress || {}),
          open: true,
          status: "error",
          summary: tAssembly(latest, "runtime.addCtgImportFailed"),
          stages: [
            ...(latest.assembly?.addCtgImportProgress?.stages || []),
            tAssembly(latest, "runtime.addCtgImportFailed"),
          ],
          error: mappedError.userMessage,
        },
        actionStatus: tAssembly(latest, "runtime.addCtgImportFailed"),
        actionError: mappedError.userMessage,
      },
    });
    rerender(host, store);
  }
}

function createAddCtgImportRunId() {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `add-ctg-${Date.now()}-${randomPart}`;
}

function setAddCtgImportProgress(host, store, progress) {
  const state = store.getState();
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      addCtgImportProgress: progress,
    },
  });
  rerender(host, store);
}

function appendAddCtgImportStage(host, store, stage) {
  const state = store.getState();
  const current = state.assembly?.addCtgImportProgress || {};
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      addCtgImportProgress: {
        ...current,
        stages: [...(Array.isArray(current.stages) ? current.stages : []), stage],
      },
    },
  });
  rerender(host, store);
}

function setActiveHitsTrack(host, store, { trackKey = "primary" }) {
  const state = store.getState();
  const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
  const normalizedTrackKey = String(trackKey || "").trim();
  if (!selectedChrName) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      activeHitsTrackKey: normalizedTrackKey,
      activeHitsTrackKeyByChr: {
        ...(state.assembly?.activeHitsTrackKeyByChr || {}),
        [selectedChrName]: normalizedTrackKey || "__none",
      },
    },
  });
  rerender(host, store);
}

function setActivePhasedFinalPathTrack(host, store, { trackKey = "" }) {
  const state = store.getState();
  const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
  const normalizedTrackKey = String(trackKey || "").trim();
  const tracks = Array.isArray(state.assembly?.phasedChrTracks) ? state.assembly.phasedChrTracks : [];
  const isAll = normalizedTrackKey === "__all__";
  const hasTrack = isAll || tracks.some((track) =>
    String(track?.haplotypeKey || "").trim() === normalizedTrackKey,
  );
  if (!selectedChrName || !normalizedTrackKey || !hasTrack) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      activeFinalPathKey: normalizedTrackKey,
      activeFinalPathKeyByChr: {
        ...(state.assembly?.activeFinalPathKeyByChr || {}),
        [selectedChrName]: normalizedTrackKey,
      },
    },
  });
  rerender(host, store);
}

function resolveAppendToPathFocusPatch(assembly, activePhasedTrackKey) {
  const selectedChrName = String(assembly?.selectedChrName || "").trim();
  const normalizedTrackKey = String(activePhasedTrackKey || "").trim();
  if (!selectedChrName || !normalizedTrackKey) {
    return {};
  }
  const currentFinalPathKey = resolveFinalPathSelectionKey(assembly);
  if (currentFinalPathKey === FINAL_PATH_ALL_KEY || currentFinalPathKey === normalizedTrackKey) {
    return {};
  }
  return {
    activeFinalPathKey: normalizedTrackKey,
    activeFinalPathKeyByChr: {
      ...(assembly?.activeFinalPathKeyByChr || {}),
      [selectedChrName]: normalizedTrackKey,
    },
  };
}

async function refreshAfterBatchDelete(host, store, payload = {}) {
  const state = store.getState();
  const deletedIds = filterPrimaryTrackSelectionCtgIds(
    payload.deletedAssemblyCtgIds,
    state.assembly,
  );
  const deletedIdSet = new Set(deletedIds);
  const removedCtgs = (Array.isArray(state.assembly?.chrCtgs) ? state.assembly.chrCtgs : [])
    .filter((ctg) => deletedIdSet.has(Number(ctg?.assemblyCtgId || 0)));
  const nextChrCtgs = (Array.isArray(state.assembly?.chrCtgs) ? state.assembly.chrCtgs : [])
    .filter((ctg) => !deletedIdSet.has(Number(ctg?.assemblyCtgId || 0)));
  const currentProject = getCurrentProject(state);
  const primaryDatasetId = normalizeSupportDatasetId(currentProject?.primaryDatasetId);
  const deletedCtgs = await loadDeletedCtgsForChr(
    state.session.workspacePath,
    state.session.projectId,
    state.assembly.selectedChrName,
    primaryDatasetId,
  );
  const selectedCtgWasDeleted = deletedIdSet.has(Number(state.assembly?.selectedCtgId || 0));
  const nextAssemblyBase = {
    ...state.assembly,
    chromosomes: updateChromosomeSummariesAfterLocalDelete(
      state.assembly?.chromosomes,
      state.assembly?.selectedChrName,
      removedCtgs,
    ),
    chrCtgs: nextChrCtgs,
    deletedCtgs,
    selectedDeletedCtgRecordIds: [],
    trackSelectedCtgIds: [],
    hiddenPrimaryCtgIds: filterPrimaryTrackSelectionCtgIds(
      state.assembly?.hiddenPrimaryCtgIds,
      { ...state.assembly, chrCtgs: nextChrCtgs },
    ),
    selectedCtgId: selectedCtgWasDeleted ? null : state.assembly?.selectedCtgId,
    selectedMemberSeqId: selectedCtgWasDeleted ? null : state.assembly?.selectedMemberSeqId,
    ctgDetail: selectedCtgWasDeleted ? null : state.assembly?.ctgDetail,
    editCandidates: selectedCtgWasDeleted
      ? { moveTargetCtgs: [], addSeqCandidates: [] }
      : state.assembly?.editCandidates,
    subview: deletedIds.length ? buildClearedSubviewState(state.assembly) : state.assembly?.subview,
    subviewTrackDragOffsets: deletedIds.length ? [] : state.assembly?.subviewTrackDragOffsets,
  };
  const nextAssembly = {
    ...nextAssemblyBase,
    trackDragOffsets: filterTrackDragOffsets(state.assembly?.trackDragOffsets, nextAssemblyBase),
  };
  store.setState({
    ...state,
    assembly: nextAssembly,
  });

  const routeHost = host?.closest?.("#route-host") || null;
  if (!routeHost) {
    rerenderAssemblyMainTab(host, store);
    return;
  }
  const nextContent = createRenderedAssemblyMainTabContent(routeHost, store.getState());
  if (!nextContent) {
    rerenderAssemblyMainTab(host, store);
    return;
  }
  const replacedMembersPanel = replaceRenderedAssemblySection(
    routeHost,
    nextContent,
    ".assembly-members-panel",
  );
  if (replacedMembersPanel) {
    bindAssemblyPage(replacedMembersPanel, store);
  }
  patchAssemblyStatusToast(routeHost, nextContent);
  patchDeletedPrimaryTrackCtgsDom(routeHost, deletedIds);
  if (deletedIds.length) {
    rerenderSubviewPanel(host, store);
  }
}

async function selectChromosome(host, store, chrName) {
  return selectChromosomeImpl(host, store, chrName, assemblyDataRuntimeDeps);
}

async function selectCtg(host, store, assemblyCtgId, options = {}) {
  return selectCtgImpl(host, store, assemblyCtgId, options, assemblyDataRuntimeDeps);
}

async function runCtgSearch(host, store, rawKeyword) {
  return runCtgSearchImpl(host, store, rawKeyword, {
    mapAssemblyError,
    rerender,
    selectCtg: (targetHost, targetStore, assemblyCtgId) => selectCtgImpl(
      targetHost,
      targetStore,
      assemblyCtgId,
      {},
      assemblyDataRuntimeDeps,
    ),
  });
}

async function loadSideDataForCtg(workspaceRoot, projectId, assemblyCtgId) {
  return loadSideDataForCtgImpl(workspaceRoot, projectId, assemblyCtgId, assemblyDataLoaderDeps);
}

function getCurrentProject(state) {
  const currentProjectId = Number(state?.session?.projectId || 0);
  if (!currentProjectId || !Array.isArray(state.initializer?.existingProjects)) {
    return null;
  }
  return (
    state.initializer.existingProjects.find(
      (project) => Number(project.projectId) === currentProjectId,
    ) || null
  );
}

function getSupportDatasetOptions(state, currentProject = getCurrentProject(state)) {
  if (!currentProject) {
    return [];
  }
  return (currentProject.supportDatasetIds || [])
    .map((datasetId) => normalizeSupportDatasetId(datasetId))
    .filter((datasetId) => datasetId !== null)
    .map((datasetId) => ({
      datasetId,
      label: getDatasetNameById(state.initializer?.datasets || [], datasetId),
    }));
}

function getDatasetNameById(datasets, datasetId) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
  if (!normalizedDatasetId) {
    return "";
  }
  const matched = Array.isArray(datasets)
    ? datasets.find((dataset) => Number(dataset.datasetId) === normalizedDatasetId)
    : null;
  return String(matched?.name || matched?.label || `ds-${normalizedDatasetId}`);
}

function updateChromosomeSummariesAfterLocalDelete(chromosomes, chrName, removedCtgs) {
  const selectedChrName = String(chrName || "").trim();
  const removedList = Array.isArray(removedCtgs) ? removedCtgs : [];
  if (!selectedChrName || !removedList.length || !Array.isArray(chromosomes)) {
    return Array.isArray(chromosomes) ? chromosomes : [];
  }
  const removedBp = removedList.reduce(
    (sum, ctg) => sum + Math.max(0, normalizeNonNegativeInt(ctg?.totalLength) ?? 0),
    0,
  );
  return chromosomes.map((chromosome) => {
    if (String(chromosome?.chrName || "").trim() !== selectedChrName) {
      return chromosome;
    }
    return {
      ...chromosome,
      ctgCount: Math.max(0, Math.max(0, normalizeNonNegativeInt(chromosome?.ctgCount) ?? 0) - removedList.length),
      placedBp: Math.max(0, Math.max(0, normalizeNonNegativeInt(chromosome?.placedBp) ?? 0) - removedBp),
    };
  });
}

async function loadDatasetChrCtgs(workspaceRoot, projectId, chrName, datasetId) {
  return loadDatasetChrCtgsImpl(workspaceRoot, projectId, chrName, datasetId, assemblyDataLoaderDeps);
}

async function loadDeletedCtgsForChr(workspaceRoot, projectId, chrName, datasetId = null) {
  return loadDeletedCtgsForChrImpl(
    workspaceRoot,
    projectId,
    chrName,
    datasetId,
    assemblyDataLoaderDeps,
  );
}

async function appendTrackContigToFinalPath(host, store, ctgContext, options = {}) {
  const activePhasedTrackKey = String(options.activePhasedTrackKey || "").trim();
  if (activePhasedTrackKey) {
    const state = store.getState();
    const selectedChrName = String(state.assembly?.selectedChrName || "").trim();
    if (selectedChrName) {
      store.setState({
        assembly: {
          ...state.assembly,
          activePhasedTrackKey,
          activePhasedTrackKeyByChr: {
            ...(state.assembly?.activePhasedTrackKeyByChr || {}),
            [selectedChrName]: activePhasedTrackKey,
          },
          ...resolveAppendToPathFocusPatch(state.assembly, activePhasedTrackKey),
        },
      });
    }
  }
  return appendTrackContigToFinalPathImpl(host, store, ctgContext, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  }, options);
}

async function appendFinalPathRow(host, store, payload = {}) {
  return appendFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function addFinalPathGapRelativeToSegment(host, store, payload) {
  return addFinalPathGapRelativeToSegmentImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function addFinalPathContigRelativeToSegment(host, store, payload) {
  return addFinalPathContigRelativeToSegmentImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function createEmptyFinalPathRow(host, store, payload) {
  return createEmptyFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function flipFinalPathSegment(host, store, payload) {
  return flipFinalPathSegmentImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function updateFinalPathRow(host, store, payload) {
  return updateFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function deleteFinalPathSegment(host, store, payload) {
  return removeFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function removeFinalPathRow(host, store, payload) {
  return removeFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function moveFinalPathRow(host, store, payload) {
  return moveFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender,
  });
}

async function updateSupportDatasetSelection(host, store, rawSupportDatasetId) {
  await applySupportDatasetSelection(host, store, rawSupportDatasetId);
}

function bindTrackViewportResize(host, store) {
  const routeHost = host?.closest?.("#route-host") || null;
  if (routeHost && routeHost !== host) {
    return;
  }
  if (typeof globalThis.window?.addEventListener !== "function") {
    return;
  }
  if (host[ASSEMBLY_TRACK_RESIZE_BOUND]) {
    return;
  }
  const coordinator = createTrackViewportResizeCoordinator({
    getViewportWidths: () => readAssemblyTrackViewportWidths(host),
    getMeasuredWidths: () => measuredTrackViewportPxByRole,
    setMeasuredWidths: (nextWidths) => {
      measuredTrackViewportPxByRole = resolveMeasuredTrackViewportWidths(nextWidths, measuredTrackViewportPxByRole);
    },
    onViewportResize: () => {
      rerender(host, store);
    },
  });
  const onResize = () => {
    coordinator.onResize();
  };
  globalThis.window.addEventListener("resize", onResize);
  host[ASSEMBLY_TRACK_RESIZE_BOUND] = {
    coordinator,
    onResize,
  };
}

function setAssemblyViewportScrollState(store, fieldName, nextValue) {
  const state = store.getState();
  const normalizedNextValue = normalizeViewportScrollState(nextValue);
  if (areViewportScrollStatesEqual(state.assembly?.[fieldName], normalizedNextValue)) {
    return false;
  }
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      [fieldName]: normalizedNextValue,
    },
  });
  return true;
}

function schedulePersistAssemblyScrollState(
  host,
  store,
  deps = projectAssemblyViewStateRuntimeDeps,
  timerApi = resolveTimerApi(),
) {
  if (pendingAssemblyScrollStatePersistTimer !== null) {
    timerApi.clearTimeout(pendingAssemblyScrollStatePersistTimer);
  }
  pendingAssemblyScrollStatePersistTimer = timerApi.setTimeout(() => {
    pendingAssemblyScrollStatePersistTimer = null;
    void persistProjectAssemblyViewStateFromStore(host, store, deps);
  }, 120);
}

function bindTrackScrollSync(host, store, deps = {}) {
  const schedulePersistScrollState =
    deps.schedulePersistAssemblyScrollState || schedulePersistAssemblyScrollState;
  let viewportChanged = false;
  const finalPathScrollEl =
    host?.querySelector?.("[data-final-path-graph-viewport]")
    || host?.querySelector?.(".assembly-final-path-svg-wrap")
    || null;
  const nextMeasuredTrackViewportWidths = resolveMeasuredTrackViewportWidths(
    readAssemblyTrackViewportWidths(host),
    measuredTrackViewportPxByRole,
  );
  if (haveMeasuredTrackViewportWidthsChanged(measuredTrackViewportPxByRole, nextMeasuredTrackViewportWidths)) {
    measuredTrackViewportPxByRole = nextMeasuredTrackViewportWidths;
    viewportChanged = true;
  }
  const trackScrollEls = Array.from(host?.querySelectorAll?.(".assembly-track-scroll[data-track-role]") || []);
  const subviewTrackScrollEls = trackScrollEls.filter(
    (element) => String(element.dataset.trackRole || "").trim() === "subview",
  );
  const syncedTrackScrollEls = trackScrollEls.filter(
    (element) => String(element.dataset.trackRole || "").trim() !== "subview",
  );
  if (!syncedTrackScrollEls.length) {
    lastTrackViewportKey = "";
    lastTrackScrollLeft = 0;
    lastPrimaryTrackViewboxMinX = 0;
    if (setAssemblyViewportScrollState(store, "trackScrollState", {})) {
      schedulePersistScrollState(host, store);
    }
  } else {
    const primaryScroll = syncedTrackScrollEls.find(
      (element) => element.dataset.trackRole === "primary",
    );
    const currentPrimaryViewboxMinX = Number(primaryScroll?.dataset.trackViewboxMinX || 0);
    if (Number.isFinite(currentPrimaryViewboxMinX)) {
      lastTrackScrollLeft = resolveTrackScrollLeftForViewboxShift(
        lastTrackScrollLeft,
        lastPrimaryTrackViewboxMinX,
        currentPrimaryViewboxMinX,
        { preserveViewport: !trackContigDragActive },
      );
      lastPrimaryTrackViewboxMinX = currentPrimaryViewboxMinX;
    }
    if (pendingPrimaryViewportAnchorBp !== null) {
      const anchoredScrollLeft = resolveScrollLeftForViewportAnchorBp(
        pendingPrimaryViewportAnchorBp,
        readTrackViewportMetrics(primaryScroll, "primary"),
      );
      if (anchoredScrollLeft !== null) {
        lastTrackScrollLeft = anchoredScrollLeft;
      }
      pendingPrimaryViewportAnchorBp = null;
    }

    let state = store.getState();
    const nextViewportKey = buildMainTrackViewportKey(state);
    const shouldApplyPendingFocus = Boolean(pendingTrackAutoFocusMode);
    if (nextViewportKey !== lastTrackViewportKey || shouldApplyPendingFocus) {
      lastTrackViewportKey = nextViewportKey;
      const persistedScrollLeft = resolvePersistedViewportScrollLeft(
        state.assembly.trackScrollState,
        nextViewportKey,
      );
      if (shouldApplyPendingFocus) {
        const focusCenter = Number(primaryScroll?.dataset.focusCenter || 0);
        const focusStart = Number(primaryScroll?.dataset.focusStart || 0);
        const viewportWidth = primaryScroll?.clientWidth || 0;
        if (pendingTrackAutoFocusMode === "start") {
          lastTrackScrollLeft = Math.max(0, Math.round(focusStart));
        } else {
          lastTrackScrollLeft = Math.max(0, Math.round(focusCenter - viewportWidth / 2));
        }
      } else if (suppressNextTrackAutoFocus) {
        suppressNextTrackAutoFocus = false;
      } else if (persistedScrollLeft !== null) {
        lastTrackScrollLeft = persistedScrollLeft;
      } else {
        const focusCenter = Number(primaryScroll?.dataset.focusCenter || 0);
        const viewportWidth = primaryScroll?.clientWidth || 0;
        lastTrackScrollLeft = Math.max(0, Math.round(focusCenter - viewportWidth / 2));
      }
      pendingTrackAutoFocusMode = null;
    }
    if (setAssemblyViewportScrollState(store, "trackScrollState", {
      viewportKey: lastTrackViewportKey,
      scrollLeft: lastTrackScrollLeft,
    })) {
      state = store.getState();
      schedulePersistScrollState(host, store);
    }

    applyTrackScrollLeft(syncedTrackScrollEls, lastTrackScrollLeft);

    let syncing = false;
    syncedTrackScrollEls.forEach((element) => {
      element.addEventListener("scroll", () => {
        if (syncing) {
          return;
        }
        syncing = true;
        lastTrackScrollLeft = element.scrollLeft;
        applyTrackScrollLeft(syncedTrackScrollEls, lastTrackScrollLeft, element);
        if (setAssemblyViewportScrollState(store, "trackScrollState", {
          viewportKey: lastTrackViewportKey,
          scrollLeft: lastTrackScrollLeft,
        })) {
          schedulePersistScrollState(host, store);
        }
        syncing = false;
      });
    });

    if (!subviewTrackScrollEls.length) {
      lastSubviewViewportKey = "";
      lastSubviewScrollLeft = 0;
      if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {})) {
        schedulePersistScrollState(host, store);
      }
    } else {
      state = store.getState();
      const nextSubviewViewportKey = buildSubviewTrackViewportKey(state);
      if (nextSubviewViewportKey !== lastSubviewViewportKey) {
        lastSubviewViewportKey = nextSubviewViewportKey;
        lastSubviewScrollLeft = resolvePersistedViewportScrollLeft(
          state.assembly.subviewTrackScrollState,
          nextSubviewViewportKey,
        ) ?? 0;
      }
      const primarySubviewScroll = subviewTrackScrollEls[0] || null;
      if (pendingSubviewViewportAnchorBp !== null) {
        const anchoredScrollLeft = resolveScrollLeftForViewportAnchorBp(
          pendingSubviewViewportAnchorBp,
          readTrackViewportMetrics(primarySubviewScroll, "subview"),
        );
        if (anchoredScrollLeft !== null) {
          lastSubviewScrollLeft = anchoredScrollLeft;
        }
        pendingSubviewViewportAnchorBp = null;
      }
      if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {
        viewportKey: lastSubviewViewportKey,
        scrollLeft: lastSubviewScrollLeft,
      })) {
        schedulePersistScrollState(host, store);
      }
      applyTrackScrollLeft(subviewTrackScrollEls, lastSubviewScrollLeft);

      let subviewSyncing = false;
      subviewTrackScrollEls.forEach((element) => {
        element.addEventListener("scroll", () => {
          if (subviewSyncing) {
            return;
          }
          subviewSyncing = true;
          lastSubviewScrollLeft = element.scrollLeft;
          applyTrackScrollLeft(subviewTrackScrollEls, lastSubviewScrollLeft, element);
          if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {
            viewportKey: lastSubviewViewportKey,
            scrollLeft: lastSubviewScrollLeft,
          })) {
            schedulePersistScrollState(host, store);
          }
          subviewSyncing = false;
        });
      });
    }

    state = store.getState();
    const nextFinalPathViewportKey = buildFinalPathTrackViewportKey(state);
    if (finalPathScrollEl) {
      if (nextFinalPathViewportKey !== lastFinalPathViewportKey) {
        lastFinalPathViewportKey = nextFinalPathViewportKey;
        lastFinalPathScrollLeft = resolvePersistedViewportScrollLeft(
          state.assembly.finalPathTrackScrollState,
          nextFinalPathViewportKey,
        ) ?? 0;
      }
      if (setAssemblyViewportScrollState(store, "finalPathTrackScrollState", {
        viewportKey: lastFinalPathViewportKey,
        scrollLeft: lastFinalPathScrollLeft,
      })) {
        schedulePersistScrollState(host, store);
      }
      finalPathScrollEl.scrollLeft = lastFinalPathScrollLeft;
      let finalPathSyncing = false;
      if (typeof finalPathScrollEl.addEventListener === "function") {
        finalPathScrollEl.addEventListener("scroll", () => {
          if (finalPathSyncing) {
            return;
          }
          finalPathSyncing = true;
          lastFinalPathScrollLeft = Number(finalPathScrollEl.scrollLeft || 0);
          if (setAssemblyViewportScrollState(store, "finalPathTrackScrollState", {
            viewportKey: lastFinalPathViewportKey,
            scrollLeft: lastFinalPathScrollLeft,
          })) {
            schedulePersistScrollState(host, store);
          }
          finalPathSyncing = false;
        });
      }
    }
    return viewportChanged;
  }

  if (!subviewTrackScrollEls.length) {
    lastSubviewViewportKey = "";
    lastSubviewScrollLeft = 0;
    if (setAssemblyViewportScrollState(store, "subviewTrackScrollState", {})) {
      schedulePersistScrollState(host, store);
    }
  }
  return false;
}

function applyTrackScrollLeft(trackScrollEls, scrollLeft, sourceElement = null) {
  trackScrollEls.forEach((element) => {
    if (element === sourceElement) {
      return;
    }
    element.scrollLeft = scrollLeft;
  });
}

function bindSubviewBandTooltips(host) {
  const timerApi = resolveTimerApi();
  const scrollNodes = host.querySelectorAll?.(".subview-track-scroll") || [];
  scrollNodes.forEach((scrollNode) => {
    if (!scrollNode || scrollNode[ASSEMBLY_SUBVIEW_BAND_TOOLTIP_BOUND]) {
      return;
    }
    const tooltipNode = scrollNode.querySelector?.(".subview-band-tooltip");
    if (!tooltipNode) {
      return;
    }
    const coordinator = createSubviewBandTooltipCoordinator({
      setTimeoutFn: timerApi.setTimeout.bind(timerApi),
      clearTimeoutFn: timerApi.clearTimeout.bind(timerApi),
      hoverDelayMs: SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS,
      onShow: ({ text, point }) => {
        showSubviewBandTooltip(scrollNode, tooltipNode, text, point);
      },
      onMove: ({ text, point }) => {
        showSubviewBandTooltip(scrollNode, tooltipNode, text, point);
      },
      onHide: () => {
        hideSubviewBandTooltip(tooltipNode);
      },
    });
    const bandNodes = scrollNode.querySelectorAll?.("[data-subview-band-tooltip]") || [];
    bandNodes.forEach((bandNode) => {
      bandNode.addEventListener("pointerenter", (event) => {
        coordinator.enter({
          token: bandNode,
          text: readSubviewBandTooltipText(bandNode),
          point: resolveTrackPointerContentPoint(event, scrollNode),
        });
      });
      bandNode.addEventListener("pointermove", (event) => {
        coordinator.move({
          token: bandNode,
          text: readSubviewBandTooltipText(bandNode),
          point: resolveTrackPointerContentPoint(event, scrollNode),
        });
      });
      bandNode.addEventListener("pointerleave", () => {
        coordinator.leave(bandNode);
      });
    });
    scrollNode.addEventListener("scroll", () => {
      coordinator.hide();
    });
    scrollNode[ASSEMBLY_SUBVIEW_BAND_TOOLTIP_BOUND] = {
      coordinator,
    };
  });
}

function readSubviewBandTooltipText(node) {
  return String(node?.getAttribute?.("data-subview-band-tooltip") || "").replaceAll(" | ", "\n");
}

function showSubviewBandTooltip(scrollNode, tooltipNode, text, point) {
  tooltipNode.textContent = String(text || "");
  tooltipNode.classList.remove("is-hidden");
  tooltipNode.setAttribute("aria-hidden", "false");

  const scrollLeft = Number(scrollNode?.scrollLeft || 0);
  const scrollTop = Number(scrollNode?.scrollTop || 0);
  const viewportWidth = Number(scrollNode?.clientWidth || 0);
  const viewportHeight = Number(scrollNode?.clientHeight || 0);
  const tooltipWidth = Number(tooltipNode?.offsetWidth || 0);
  const tooltipHeight = Number(tooltipNode?.offsetHeight || 0);
  const desiredLeft = Number(point?.x || 0) + 14;
  const desiredTop = Number(point?.y || 0) + 14;
  const maxLeft = Math.max(scrollLeft + 8, scrollLeft + viewportWidth - tooltipWidth - 8);
  const maxTop = Math.max(scrollTop + 8, scrollTop + viewportHeight - tooltipHeight - 8);
  const left = Math.min(Math.max(scrollLeft + 8, desiredLeft), maxLeft);
  const top = Math.min(Math.max(scrollTop + 8, desiredTop), maxTop);
  tooltipNode.style.left = `${left}px`;
  tooltipNode.style.top = `${top}px`;
}

function hideSubviewBandTooltip(tooltipNode) {
  tooltipNode.classList.add("is-hidden");
  tooltipNode.setAttribute("aria-hidden", "true");
}

function syncSupportDatasetSelection(store, storage = null) {
  const state = store.getState();
  const workspacePath = String(state?.session?.workspacePath || "").trim();
  const projectId = Number(state?.session?.projectId || 0);
  const storageKey = buildSupportDsStorageKey(workspacePath, projectId);

  if (!storageKey) {
    lastSupportDsSessionKey = "";
    lastSupportDsSelection = null;
    return { changed: false, supportDatasetId: null };
  }

  const supportDatasetOptions = getSupportDatasetOptions(state);
  const candidateIds = new Set(supportDatasetOptions.map((dataset) => dataset.datasetId));
  const currentSelection = normalizeSupportDatasetId(state.assembly.supportDatasetId);

  if (storageKey !== lastSupportDsSessionKey) {
    lastSupportDsSessionKey = storageKey;
    if (currentSelection !== null && candidateIds.has(currentSelection)) {
      saveSupportDsState(workspacePath, projectId, { supportDatasetId: currentSelection }, storage || undefined);
      lastSupportDsSelection = currentSelection;
      return { changed: false, supportDatasetId: currentSelection };
    }
    const savedState = loadSupportDsState(workspacePath, projectId, storage || undefined);
    const restoredDatasetId = normalizeSupportDatasetId(savedState?.supportDatasetId);
    const nextSelection =
      restoredDatasetId !== null && candidateIds.has(restoredDatasetId)
        ? restoredDatasetId
        : supportDatasetOptions[0]?.datasetId || null;
    if (nextSelection !== null && nextSelection !== restoredDatasetId) {
      saveSupportDsState(workspacePath, projectId, { supportDatasetId: nextSelection }, storage || undefined);
    }
    lastSupportDsSelection = nextSelection;
    if (normalizeSupportDatasetId(state.assembly.supportDatasetId) !== nextSelection) {
      return { changed: true, supportDatasetId: nextSelection };
    }
    return { changed: false, supportDatasetId: nextSelection };
  }

  const reconciliation = reconcileSupportDsSelection({
    workspacePath,
    projectId,
    currentSelection,
    candidateIds,
    storage: storage || undefined,
  });
  if (reconciliation.invalidated) {
    const fallbackSelection = supportDatasetOptions[0]?.datasetId || null;
    lastSupportDsSelection = fallbackSelection;
    if (currentSelection !== fallbackSelection) {
      return { changed: true, supportDatasetId: fallbackSelection };
    }
  }
  if (currentSelection === null && supportDatasetOptions.length > 0) {
    const fallbackSelection = supportDatasetOptions[0]?.datasetId || null;
    lastSupportDsSelection = fallbackSelection;
    if (fallbackSelection !== null) {
      saveSupportDsState(workspacePath, projectId, { supportDatasetId: fallbackSelection }, storage || undefined);
      return { changed: true, supportDatasetId: fallbackSelection };
    }
  }

  if (currentSelection !== lastSupportDsSelection) {
    saveSupportDsState(workspacePath, projectId, { supportDatasetId: currentSelection }, storage || undefined);
    lastSupportDsSelection = currentSelection;
  }

  return { changed: false, supportDatasetId: currentSelection };
}

function rerender(host, store) {
  cancelDeferredRerender();
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    return;
  }
  routeHost.innerHTML = renderAssemblyPage(store.getState());
  bindAssemblyPage(routeHost, store);
}

function rerenderAssemblyMainTab(host, store) {
  cancelDeferredRerender();
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    rerender(host, store);
    return;
  }
  const doc = routeHost.ownerDocument || globalThis.document;
  if (!doc?.createElement) {
    rerender(host, store);
    return;
  }
  const template = doc.createElement("template");
  template.innerHTML = renderAssemblyMainTab(store.getState());
  const nextContent = template.content;
  const replacedNodes = [
    replaceRenderedAssemblySection(routeHost, nextContent, ".chr-strip.has-members-panel"),
    replaceRenderedAssemblySection(routeHost, nextContent, ".assembly-track-unified"),
  ].filter(Boolean);
  if (!replacedNodes.length) {
    rerender(host, store);
    return;
  }
  replacedNodes.forEach((node) => {
    bindAssemblyPage(node, store);
  });
}

function isConnectedToDocument(node, doc) {
  if (!node) {
    return false;
  }
  if (typeof node.isConnected === "boolean") {
    return node.isConnected;
  }
  if (typeof doc?.contains === "function") {
    return doc.contains(node);
  }
  return true;
}

function resolveCurrentRouteHost(host) {
  const doc = host?.ownerDocument || globalThis.document;
  const directRouteHost = host?.matches?.("#route-host")
    ? host
    : host?.closest?.("#route-host");
  if (isConnectedToDocument(directRouteHost, doc)) {
    return directRouteHost;
  }
  return doc?.querySelector?.("#route-host") || directRouteHost || host || null;
}

const BATCH_DELETE_PROGRESS_OVERLAY_SELECTOR = "[data-batch-delete-progress-overlay='true']";

function collectBatchDeleteProgressOverlays(routeHost, doc) {
  const roots = [routeHost, doc, globalThis.document].filter(Boolean);
  const overlays = [];
  const seen = new Set();
  for (const root of roots) {
    if (typeof root.querySelectorAll === "function") {
      for (const overlay of root.querySelectorAll(BATCH_DELETE_PROGRESS_OVERLAY_SELECTOR)) {
        if (overlay && !seen.has(overlay)) {
          seen.add(overlay);
          overlays.push(overlay);
        }
      }
      continue;
    }
    const overlay = root.querySelector?.(BATCH_DELETE_PROGRESS_OVERLAY_SELECTOR);
    if (overlay && !seen.has(overlay)) {
      seen.add(overlay);
      overlays.push(overlay);
    }
  }
  return overlays;
}

function removeBatchDeleteProgressOverlays(routeHost, doc) {
  collectBatchDeleteProgressOverlays(routeHost, doc).forEach((overlay) => {
    overlay.remove?.();
  });
}

function rerenderBatchDeleteProgress(host, store) {
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    return;
  }
  const doc = routeHost.ownerDocument || host?.ownerDocument || globalThis.document;
  if (!doc?.createElement) {
    return;
  }
  const currentOverlays = collectBatchDeleteProgressOverlays(routeHost, doc);
  const currentOverlay = currentOverlays[0] || null;
  const nextHtml = renderBatchDeleteProgressModal(store.getState());
  if (!nextHtml) {
    removeBatchDeleteProgressOverlays(routeHost, doc);
    return;
  }
  currentOverlays.slice(1).forEach((overlay) => {
    overlay.remove?.();
  });
  const template = doc.createElement("template");
  template.innerHTML = nextHtml;
  const nextOverlay = template.content.firstElementChild;
  if (!nextOverlay) {
    removeBatchDeleteProgressOverlays(routeHost, doc);
    return;
  }
  if (currentOverlay) {
    currentOverlay.replaceWith(nextOverlay);
    return;
  }
  (routeHost.querySelector?.(".page") || routeHost).appendChild(nextOverlay);
}

function createRenderedAssemblyMainTabContent(routeHost, state) {
  const doc = routeHost?.ownerDocument || globalThis.document;
  if (!doc?.createElement) {
    return null;
  }
  const template = doc.createElement("template");
  template.innerHTML = renderAssemblyMainTab(state);
  return template.content;
}

function replaceRenderedAssemblySection(routeHost, nextContent, selector) {
  const current = routeHost.querySelector(selector);
  const next = nextContent?.querySelector?.(selector) || null;
  if (!current || !next || typeof current.replaceWith !== "function") {
    return null;
  }
  current.replaceWith(next);
  return next;
}

function patchAssemblyStatusToast(routeHost, nextContent) {
  const currentMain = routeHost?.querySelector?.(".assembly-main-view") || null;
  if (!currentMain) {
    return false;
  }
  const currentToast = currentMain.querySelector?.(".assembly-status-toast-wrap") || null;
  const nextToast = nextContent?.querySelector?.(".assembly-status-toast-wrap") || null;
  if (currentToast && nextToast && typeof currentToast.replaceWith === "function") {
    currentToast.replaceWith(nextToast);
    return true;
  }
  if (currentToast && typeof currentToast.remove === "function") {
    currentToast.remove();
    return true;
  }
  if (!currentToast && nextToast && typeof currentMain.insertBefore === "function") {
    currentMain.insertBefore(nextToast, currentMain.firstChild || null);
    return true;
  }
  return false;
}

function getElementDatasetValue(element, key, attrName) {
  if (element?.dataset && Object.prototype.hasOwnProperty.call(element.dataset, key)) {
    return element.dataset[key];
  }
  return typeof element?.getAttribute === "function" ? element.getAttribute(attrName) : "";
}

function queryElementsByNumericDataset(root, selector, datasetKey, attrName, targetId) {
  const normalizedId = Number(targetId || 0);
  if (!normalizedId) {
    return [];
  }
  return Array.from(root?.querySelectorAll?.(selector) || []).filter((element) =>
    Number(getElementDatasetValue(element, datasetKey, attrName) || 0) === normalizedId,
  );
}

function patchMemberChipHiddenState(chip, shouldHide, hiddenTagText) {
  chip?.classList?.toggle?.("is-hidden-contig", shouldHide);
  const existingTag = chip?.querySelector?.(".ctg-chip-hidden-tag") || null;
  if (!shouldHide) {
    existingTag?.remove?.();
    return;
  }
  if (existingTag) {
    return;
  }
  const titleNode = chip?.querySelector?.("strong") || null;
  titleNode?.insertAdjacentHTML?.(
    "beforeend",
    ` <span class="ctg-chip-hidden-tag">${escapeHtml(hiddenTagText)}</span>`,
  );
}

function patchPrimaryTrackCtgHiddenState(group, shouldHide) {
  if (!group) {
    return;
  }
  if (group.dataset && group.dataset.primaryHiddenBase === undefined) {
    group.dataset.primaryHiddenBase = group.classList?.contains?.("is-hidden-contig") ? "1" : "0";
  }
  const baseHidden = group.dataset?.primaryHiddenBase === "1";
  const offset = shouldHide === baseHidden ? 0 : shouldHide ? -30 : 30;
  group.classList?.toggle?.("is-hidden-contig", shouldHide);
  group.querySelectorAll?.(".track-ctg")?.forEach((node) => {
    node.classList?.toggle?.("is-hidden-contig", shouldHide);
  });
  if (offset === 0) {
    group.removeAttribute?.("transform");
  } else {
    group.setAttribute?.("transform", `translate(0 ${offset})`);
  }
}

function parseTrackBandPointsAttr(value) {
  return String(value || "")
    .trim()
    .split(/\s+/)
    .map((pair) => {
      const [x, y] = pair.split(",").map((part) => Number(part));
      return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null;
    })
    .filter(Boolean);
}

function rebuildMainTrackCanvasBandsFromSvg(root) {
  const scrollEls = Array.from(root?.querySelectorAll?.(".assembly-track-scroll[data-track-role='primary']") || []);
  let changed = false;
  scrollEls.forEach((scrollEl) => {
    const overlay = scrollEl.querySelector?.("[data-track-band-svg-overlay='1']");
    if (!overlay) {
      return;
    }
    const bands = Array.from(overlay.querySelectorAll?.(".track-collinearity-band[data-track-band-proxy='1']") || [])
      .filter((band) => band?.dataset?.hiddenByPrimaryCtg !== "1" && band?.style?.display !== "none")
      .map((band) => {
        const points = parseTrackBandPointsAttr(band.getAttribute?.("points"));
        if (points.length < 4) {
          return null;
        }
        return {
          hitKey: "",
          tone: band?.dataset?.bandTrackRole === "support" ? "companion" : "primary",
          points,
        };
      })
      .filter(Boolean);
    Array.from(scrollEl.querySelectorAll?.("[data-track-band-canvas-layer='1'][data-track-band-canvas-scene-kind='main-track']") || [])
      .forEach((layer) => {
        const sceneNode = layer.querySelector?.("[data-track-band-canvas-scene]");
        if (!sceneNode) {
          return;
        }
        try {
          const scene = JSON.parse(String(sceneNode.textContent || "").trim() || "null");
          if (!scene || typeof scene !== "object") {
            return;
          }
          scene.bands = bands;
          sceneNode.textContent = JSON.stringify(scene);
          changed = true;
        } catch {
          // Ignore malformed canvas scene data and leave the current canvas untouched.
        }
      });
  });
  if (changed) {
    bindBandCanvasRuntimeImpl(root);
  }
}

function patchPrimaryHiddenCtgDom(host, store, nextHiddenIds, options = {}) {
  const routeHost = host?.closest?.("#route-host") || null;
  if (!routeHost?.querySelectorAll) {
    return false;
  }
  const state = store.getState();
  const hiddenSet = new Set(filterPrimaryTrackSelectionCtgIds(nextHiddenIds, state.assembly));
  const changedIds = filterPrimaryTrackSelectionCtgIds(options.changedIds, state.assembly);
  if (!changedIds.length) {
    return false;
  }
  if (changedIds.some((ctgId) => !hiddenSet.has(ctgId))) {
    return false;
  }
  const hiddenTagText = getAssemblyI18n(state).page.deletedHiddenTag;
  let touched = false;
  changedIds.forEach((ctgId) => {
    queryElementsByNumericDataset(
      routeHost,
      ".assembly-member-chip-region [data-assembly-ctg-id]",
      "assemblyCtgId",
      "data-assembly-ctg-id",
      ctgId,
    ).forEach((chip) => {
      patchMemberChipHiddenState(chip, true, hiddenTagText);
      touched = true;
    });
    queryElementsByNumericDataset(
      routeHost,
      "[data-track-role='primary'][data-track-contig-id]",
      "trackContigId",
      "data-track-contig-id",
      ctgId,
    ).forEach((group) => {
      patchPrimaryTrackCtgHiddenState(group, true);
      touched = true;
    });
    queryElementsByNumericDataset(
      routeHost,
      "[data-band-track-role='primary'][data-band-contig-id]",
      "bandContigId",
      "data-band-contig-id",
      ctgId,
    ).forEach((band) => {
      if (band.dataset) {
        band.dataset.hiddenByPrimaryCtg = "1";
      }
      if (band.style) {
        band.style.display = "none";
      }
      touched = true;
    });
  });
  if (touched) {
    rebuildMainTrackCanvasBandsFromSvg(routeHost);
  }
  return touched;
}

function refreshFinalPathLogAfterPrimaryHiddenPatch(host, store) {
  const state = store.getState();
  if (normalizeFinalPathViewMode(state.assembly?.finalPathViewMode) !== "log") {
    return false;
  }
  rerenderAssemblyMainTab(host, store);
  return true;
}

function patchDeletedPrimaryTrackCtgsDom(host, deletedIds) {
  const routeHost = host?.closest?.("#route-host") || null;
  if (!routeHost?.querySelectorAll) {
    return false;
  }
  const normalizedIds = normalizeTrackSelectionCtgIds(deletedIds);
  if (!normalizedIds.length) {
    return false;
  }
  let touched = false;
  normalizedIds.forEach((ctgId) => {
    queryElementsByNumericDataset(
      routeHost,
      "[data-track-role='primary'][data-track-contig-id]",
      "trackContigId",
      "data-track-contig-id",
      ctgId,
    ).forEach((group) => {
      group.remove?.();
      touched = true;
    });
    queryElementsByNumericDataset(
      routeHost,
      "[data-band-track-role='primary'][data-band-contig-id]",
      "bandContigId",
      "data-band-contig-id",
      ctgId,
    ).forEach((band) => {
      band.remove?.();
      touched = true;
    });
  });
  if (touched) {
    rebuildMainTrackCanvasBandsFromSvg(routeHost);
  }
  return touched;
}

function rerenderSubviewPanel(host, store) {
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    rerender(host, store);
    return;
  }
  const currentPanel = routeHost.querySelector("[data-subview-panel='1']");
  if (!currentPanel) {
    rerender(host, store);
    return;
  }
  currentPanel.outerHTML = renderAssemblySubviewPanelImpl(store.getState(), renderTracksDeps);
  const nextPanel = routeHost.querySelector("[data-subview-panel='1']");
  if (!nextPanel) {
    rerender(host, store);
    return;
  }
  bindAssemblyPage(nextPanel, store);
}

export async function __testLoadNewSequencesTabData(
  { workspaceRoot, projectId, limit = 200 },
  loader = listNewSequences,
) {
  const result = await loader({ workspaceRoot, projectId, limit });
  return {
    loading: false,
    error: "",
    items: Array.isArray(result?.items) ? result.items : [],
    loadedProjectId: Number(projectId) || null,
    loadedWorkspacePath: String(workspaceRoot || "").trim(),
  };
}

export function __testShouldReuseNewSequencesCache(currentState, { workspacePath, projectId }) {
  return shouldReuseNewSequencesCache(currentState, { workspacePath, projectId });
}

export function __testResolveCurrentRouteHost(host) {
  return resolveCurrentRouteHost(host);
}

async function loadNewSequencesTab(host, store) {
  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return;
  }
  const currentState = getNewSequencesState(state.assembly);
  if (shouldReuseNewSequencesCache(currentState, {
    workspacePath: state.session.workspacePath,
    projectId: state.session.projectId,
  })) {
    return;
  }

  store.setState({
    assembly: {
      ...state.assembly,
      newSequences: {
        ...currentState,
        loading: true,
        error: "",
      },
    },
  });
  rerender(host, store);

  try {
    const nextState = await __testLoadNewSequencesTabData({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
    });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        newSequences: nextState,
      },
    });
  } catch (error) {
    const mappedError = mapAssemblyError({ error });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        newSequences: {
          loading: false,
          error: mappedError.userMessage,
          items: [],
          loadedProjectId: Number(state.session.projectId) || null,
          loadedWorkspacePath: String(state.session.workspacePath || "").trim(),
        },
      },
    });
  }
  rerender(host, store);
}

function renderActionFeedback(assembly) {
  const parts = [];
  if (assembly.actionStatus) {
    parts.push(`<p class="muted">${escapeHtml(assembly.actionStatus)}</p>`);
  }
  if (assembly.actionError) {
    parts.push(`<p class="error-text">${escapeHtml(assembly.actionError)}</p>`);
  }
  return parts.join("");
}

function renderNewSequenceRowActions(item, state = { locale: "zh" }) {
  const i18n = getAssemblyI18n(state);
  const assemblySeqId = Number(item?.assemblySeqId || 0);
  if (!assemblySeqId) {
    return `<span class="muted">${escapeHtml(i18n.runtime.noActionsAvailable)}</span>`;
  }
  const seqName = escapeAttr(item?.seqName || "");
  return `
    <div class="inline-input assembly-new-seq-actions">
      <button
        type="button"
        class="button ghost tiny"
        data-new-seq-action="locate-seq"
        data-assembly-seq-id="${assemblySeqId}"
        data-seq-name="${seqName}"
      >
        ${escapeHtml(i18n.runtime.locateCurrentSequence)}
      </button>
    </div>
  `;
}

function rememberTrackViewportAnchor(host, viewKey = "trackView") {
  const isSubview = viewKey === "subviewTrackView";
  const trackRole = isSubview ? "subview" : "primary";
  const scrollEl = resolveActiveTrackScrollElement(host, trackRole, null);
  const metrics = readTrackViewportMetrics(scrollEl, trackRole);
  const centerBp = resolveViewportAnchorBp(scrollEl?.scrollLeft || 0, metrics);
  if (centerBp === null) {
    if (isSubview) {
      pendingSubviewViewportAnchorBp = null;
    } else {
      pendingPrimaryViewportAnchorBp = null;
    }
    return null;
  }
  if (isSubview) {
    pendingSubviewViewportAnchorBp = centerBp;
  } else {
    pendingPrimaryViewportAnchorBp = centerBp;
  }
  return centerBp;
}

function isTrackRectOverlap(leftRect, rightRect) {
  return !(
    leftRect.right < rightRect.left ||
    leftRect.left > rightRect.right ||
    leftRect.bottom < rightRect.top ||
    leftRect.top > rightRect.bottom
  );
}

function updateTrackSelection(host, store, selectedIds) {
  const state = store.getState();
  const normalized = filterPrimaryTrackSelectionCtgIds(selectedIds, state.assembly);
  const current = normalizeTrackSelectionCtgIds(state.assembly.trackSelectedCtgIds);
  if (current.length === normalized.length && current.every((value, index) => value === normalized[index])) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      trackSelectedCtgIds: normalized,
    },
  });
  rerender(host, store);
}

function updateSubviewTrackPairSelection(host, store, selectedEntries) {
  const state = store.getState();
  const currentSubview = getSubviewState(state.assembly);
  if (String(currentSubview.summary?.mode || "") !== "track-pair") {
    return;
  }
  const pools = buildSubviewTrackPairPoolsFromAssembly(state.assembly);
  const hiddenKeySet = new Set(
    normalizeSubviewTrackPairHiddenCtgs(currentSubview.trackPairHiddenCtgs).map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  const normalized = filterSubviewTrackPairSelectionCtgs(selectedEntries, pools).filter(
    (entry) => !hiddenKeySet.has(buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId)),
  );
  const current = resolveFilteredSubviewTrackPairSelectionsFromAssembly(state.assembly);
  if (
    current.length === normalized.length
    && current.every(
      (entry, index) =>
        entry.trackRole === normalized[index]?.trackRole
        && entry.contigId === normalized[index]?.contigId,
    )
  ) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...currentSubview,
        trackPairSelectedCtgs: normalized,
      },
    },
  });
  rerender(host, store);
}

function togglePrimaryTrackSelection(host, store, assemblyCtgId) {
  const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
  if (!normalizedCtgId) {
    return;
  }
  const state = store.getState();
  const current = filterPrimaryTrackSelectionCtgIds(state.assembly.trackSelectedCtgIds, state.assembly);
  const nextSet = new Set(current);
  if (nextSet.has(normalizedCtgId)) {
    nextSet.delete(normalizedCtgId);
  } else {
    nextSet.add(normalizedCtgId);
  }
  updateTrackSelection(host, store, Array.from(nextSet.values()));
}

function shouldSuppressTrackContigClick() {
  return Date.now() <= suppressTrackContigClickUntil;
}

function applyTrackDragOffset(host, store, nextOffset) {
  const state = store.getState();
  const normalizedCurrent = normalizeTrackDragOffsets(state.assembly.trackDragOffsets);
  const normalizedNext = setTrackDragOffset(normalizedCurrent, nextOffset);
  if (areTrackDragOffsetsEqual(normalizedCurrent, normalizedNext)) {
    return;
  }
  suppressNextTrackAutoFocus = true;
  store.setState({
    assembly: {
      ...state.assembly,
      trackDragOffsets: normalizedNext,
    },
  });
  rerender(host, store);
}

async function rebaseTrackDragOffsetsAfterRestore(
  host,
  store,
  previousAssembly,
  deps = projectAssemblyViewStateRuntimeDeps,
) {
  const state = store.getState();
  const currentOffsets = normalizeTrackDragOffsets(state.assembly?.trackDragOffsets);
  const nextOffsets = filterTrackDragOffsets(
    rebaseTrackDragOffsetsForStableCtgPositions({
      trackRole: "primary",
      previousCtgs: previousAssembly?.chrCtgs,
      nextCtgs: state.assembly?.chrCtgs,
      trackDragOffsets: currentOffsets,
    }),
    state.assembly,
  );
  if (areTrackDragOffsetsEqual(currentOffsets, nextOffsets)) {
    return;
  }
  store.setState({
    ...state,
    assembly: {
      ...state.assembly,
      trackDragOffsets: nextOffsets,
    },
  });
  await persistProjectAssemblyViewStateFromStore(host, store, deps);
}

function applySubviewTrackDragOffset(host, store, nextOffset) {
  const state = store.getState();
  const normalizedCurrent = normalizeSubviewTrackDragOffsets(state.assembly.subviewTrackDragOffsets);
  const normalizedNext = setSubviewTrackDragOffset(normalizedCurrent, nextOffset);
  if (areSubviewTrackDragOffsetsEqual(normalizedCurrent, normalizedNext)) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      subviewTrackDragOffsets: normalizedNext,
    },
  });
  rerender(host, store);
}

async function persistProjectAssemblyViewStateFromStore(
  host,
  store,
  deps = projectAssemblyViewStateRuntimeDeps,
) {
  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return;
  }
  try {
    const normalizedFinalPathByChr =
      state.assembly.finalPathByChr &&
      typeof state.assembly.finalPathByChr === "object" &&
      !Array.isArray(state.assembly.finalPathByChr)
        ? state.assembly.finalPathByChr
        : {};
    const selectedChrName = String(state.assembly.selectedChrName || "").trim();
    const hiddenPrimaryCtgIds = Array.isArray(state.assembly.hiddenPrimaryCtgIds)
      ? state.assembly.hiddenPrimaryCtgIds
      : [];
    const hiddenPrimaryCtgIdsByChr = {
      ...normalizeHiddenPrimaryCtgIdsByChr(state.assembly.hiddenPrimaryCtgIdsByChr),
    };
    if (selectedChrName) {
      if (hiddenPrimaryCtgIds.length) {
        hiddenPrimaryCtgIdsByChr[selectedChrName] = hiddenPrimaryCtgIds;
      } else {
        delete hiddenPrimaryCtgIdsByChr[selectedChrName];
      }
    }
    const finalPathByChrWithHidden = (() => {
      if (!selectedChrName || !normalizedFinalPathByChr[selectedChrName]) {
        return normalizedFinalPathByChr;
      }
      const nextEntry = {
        ...normalizedFinalPathByChr[selectedChrName],
      };
      if (hiddenPrimaryCtgIds.length) {
        nextEntry.hiddenPrimaryCtgIds = hiddenPrimaryCtgIds;
      } else {
        delete nextEntry.hiddenPrimaryCtgIds;
      }
      return {
        ...normalizedFinalPathByChr,
        [selectedChrName]: nextEntry,
      };
    })();
    await deps.persistProjectAssemblyViewState({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
      supportDatasetId: normalizeSupportDatasetId(state.assembly.supportDatasetId),
      trackView: state.assembly.trackView,
      supportDsCtgLenRulesByChr:
        state.assembly.supportDsCtgLenRulesByChr
        && typeof state.assembly.supportDsCtgLenRulesByChr === "object"
        && !Array.isArray(state.assembly.supportDsCtgLenRulesByChr)
          ? state.assembly.supportDsCtgLenRulesByChr
          : {},
      supportMirroredCtgs: Array.isArray(state.assembly.supportMirroredCtgs)
        ? state.assembly.supportMirroredCtgs
        : [],
      hiddenPrimaryCtgIds,
      hiddenPrimaryCtgIdsByChr,
      trackDragOffsets: Array.isArray(state.assembly.trackDragOffsets)
        ? state.assembly.trackDragOffsets
        : [],
      subviewTrackDragOffsets: Array.isArray(state.assembly.subviewTrackDragOffsets)
        ? state.assembly.subviewTrackDragOffsets
        : [],
      trackScrollState: normalizeViewportScrollState(state.assembly.trackScrollState),
      subviewTrackScrollState: normalizeViewportScrollState(state.assembly.subviewTrackScrollState),
      finalPathTrackScrollState: normalizeViewportScrollState(state.assembly.finalPathTrackScrollState),
      membersCardCollapsed: state.assembly.membersCardCollapsed === false ? false : true,
      finalPathViewMode: normalizeFinalPathViewMode(state.assembly.finalPathViewMode),
      finalPathByChr: finalPathByChrWithHidden,
      degapProjectState:
        state.assembly.degapProjectState &&
        typeof state.assembly.degapProjectState === "object" &&
        !Array.isArray(state.assembly.degapProjectState)
          ? state.assembly.degapProjectState
          : {},
    });
  } catch (error) {
    const mappedError = mapAssemblyError({ error, stateOrLocale: store.getState() });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        actionStatus: "",
        actionError: mappedError.userMessage,
      },
    });
    rerender(host, store);
  }
}

async function persistTrackDragOffsets(host, store, deps = projectAssemblyViewStateRuntimeDeps) {
  return persistProjectAssemblyViewStateFromStore(host, store, deps);
}

async function persistSubviewTrackDragOffsets(host, store, deps = projectAssemblyViewStateRuntimeDeps) {
  return persistProjectAssemblyViewStateFromStore(host, store, deps);
}

async function persistMainTrackViewState(host, store, deps = projectAssemblyViewStateRuntimeDeps) {
  return persistProjectAssemblyViewStateFromStore(host, store, deps);
}

async function persistHiddenPrimaryCtgIds(host, store, deps = projectAssemblyViewStateRuntimeDeps) {
  return persistProjectAssemblyViewStateFromStore(host, store, deps);
}

function setSelectedPrimaryTrackCtgsHidden(
  host,
  store,
  selectedIds,
  shouldHide,
  deps = projectAssemblyViewStateRuntimeDeps,
) {
  const state = store.getState();
  const normalized = filterPrimaryTrackSelectionCtgIds(selectedIds, state.assembly);
  if (!normalized.length) {
    return;
  }
  const currentHiddenIds = new Set(
    filterPrimaryTrackSelectionCtgIds(state.assembly.hiddenPrimaryCtgIds, state.assembly),
  );
  normalized.forEach((ctgId) => {
    if (shouldHide) {
      currentHiddenIds.add(ctgId);
      return;
    }
    currentHiddenIds.delete(ctgId);
  });
  const nextHiddenIds = filterPrimaryTrackSelectionCtgIds(Array.from(currentHiddenIds.values()), state.assembly);
  const selectedChrName = String(state.assembly.selectedChrName || "").trim();
  const hiddenPrimaryCtgIdsByChr = {
    ...normalizeHiddenPrimaryCtgIdsByChr(state.assembly.hiddenPrimaryCtgIdsByChr),
  };
  if (selectedChrName) {
    if (nextHiddenIds.length) {
      hiddenPrimaryCtgIdsByChr[selectedChrName] = nextHiddenIds;
    } else {
      delete hiddenPrimaryCtgIdsByChr[selectedChrName];
    }
  }
  const nextAssemblyState = {
    ...state.assembly,
    hiddenPrimaryCtgIds: nextHiddenIds,
    hiddenPrimaryCtgIdsByChr,
    actionStatus: shouldHide
      ? tAssembly(state, "runtime.hideSelectedDone", {
        visibilityVerb: tAssembly(state, "runtime.hideSelectedVerbHide"),
        count: normalized.length,
      })
      : tAssembly(state, "runtime.hideSelectedDone", {
        visibilityVerb: tAssembly(state, "runtime.hideSelectedVerbShow"),
        count: normalized.length,
      }),
    actionError: "",
  };
  store.setState({
    ...state,
    assembly: nextAssemblyState,
  });
  const didPatchDom = (deps.patchPrimaryHiddenCtgDom || patchPrimaryHiddenCtgDom)(
    host,
    store,
    nextHiddenIds,
    { changedIds: normalized },
  );
  if (didPatchDom) {
    (deps.refreshFinalPathLogAfterPrimaryHiddenPatch || refreshFinalPathLogAfterPrimaryHiddenPatch)(
      host,
      store,
    );
  }
  if (!didPatchDom) {
    rerenderAssemblyMainTab(host, store);
  }
  return persistHiddenPrimaryCtgIds(host, {
    getState() {
      return {
        ...state,
        assembly: nextAssemblyState,
      };
    },
  }, deps);
}

function togglePrimaryTrackCtgHidden(
  host,
  store,
  assemblyCtgId,
  shouldHide,
  deps = projectAssemblyViewStateRuntimeDeps,
) {
  const normalizedCtgId = normalizeSupportDatasetId(assemblyCtgId);
  if (!normalizedCtgId) {
    return;
  }
  const state = store.getState();
  const currentHiddenIds = new Set(
    filterPrimaryTrackSelectionCtgIds(state.assembly.hiddenPrimaryCtgIds, state.assembly),
  );
  if (shouldHide) {
    currentHiddenIds.add(normalizedCtgId);
  } else {
    currentHiddenIds.delete(normalizedCtgId);
  }
  const nextHiddenIds = filterPrimaryTrackSelectionCtgIds(Array.from(currentHiddenIds.values()), state.assembly);
  const previousHiddenIds = filterPrimaryTrackSelectionCtgIds(state.assembly.hiddenPrimaryCtgIds, state.assembly);
  if (
    nextHiddenIds.length === previousHiddenIds.length &&
    nextHiddenIds.every((value, index) => value === previousHiddenIds[index])
  ) {
    return;
  }
  const selectedChrName = String(state.assembly.selectedChrName || "").trim();
  const hiddenPrimaryCtgIdsByChr = {
    ...normalizeHiddenPrimaryCtgIdsByChr(state.assembly.hiddenPrimaryCtgIdsByChr),
  };
  if (selectedChrName) {
    if (nextHiddenIds.length) {
      hiddenPrimaryCtgIdsByChr[selectedChrName] = nextHiddenIds;
    } else {
      delete hiddenPrimaryCtgIdsByChr[selectedChrName];
    }
  }
  const nextAssemblyState = {
    ...state.assembly,
    hiddenPrimaryCtgIds: nextHiddenIds,
    hiddenPrimaryCtgIdsByChr,
    actionStatus: shouldHide
      ? tAssembly(state, "runtime.hideContigDone", {
        assemblyCtgId: normalizedCtgId,
        visibilityVerb: tAssembly(state, "runtime.hideContigVerbHide"),
      })
      : tAssembly(state, "runtime.hideContigDone", {
        assemblyCtgId: normalizedCtgId,
        visibilityVerb: tAssembly(state, "runtime.hideContigVerbShow"),
      }),
    actionError: "",
  };
  store.setState({
    ...state,
    assembly: nextAssemblyState,
  });
  const didPatchDom = (deps.patchPrimaryHiddenCtgDom || patchPrimaryHiddenCtgDom)(
    host,
    store,
    nextHiddenIds,
    { changedIds: [normalizedCtgId] },
  );
  if (didPatchDom) {
    (deps.refreshFinalPathLogAfterPrimaryHiddenPatch || refreshFinalPathLogAfterPrimaryHiddenPatch)(
      host,
      store,
    );
  }
  if (!didPatchDom) {
    rerenderAssemblyMainTab(host, store);
  }
  return persistHiddenPrimaryCtgIds(host, {
    getState() {
      return {
        ...state,
        assembly: nextAssemblyState,
      };
    },
  }, deps);
}

function buildSupportMirrorEntryFromAssemblyState(state, datasetId, assemblyCtgId) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
  const normalizedAssemblyCtgId = normalizeSupportDatasetId(assemblyCtgId);
  if (!normalizedDatasetId || !normalizedAssemblyCtgId) {
    return null;
  }
  const activeSupportDatasetId = normalizeSupportDatasetId(state.assembly.supportDatasetId);
  if (activeSupportDatasetId !== normalizedDatasetId) {
    return null;
  }
  const trackPrefs = resolveTrackPrefs(state.assembly.trackView);
  const supportDsCtgLenBp = Math.max(0, normalizeNonNegativeInt(trackPrefs.supportDsCtgLen) ?? 0);
  const chrLengthsByName = buildChrLengthsByName(state.assembly.chromosomes);
  const selectedChrName = String(state.assembly.selectedChrName || "").trim();
  const supportDsCtgLenRules = getSupportDsCtgLenRulesForChr(
    state.assembly.supportDsCtgLenRulesByChr,
    selectedChrName,
    { chrLength: chrLengthsByName[selectedChrName] },
  );
  const supportTrackCtgs = filterSupportCtgsBySupportDsCtgLenRules(
    Array.isArray(state.assembly.supportChrCtgs) ? state.assembly.supportChrCtgs : [],
    {
      rules: supportDsCtgLenRules,
      defaultSupportDsCtgLen: supportDsCtgLenBp,
    },
  );
  const model = buildDualTrackModel({
    primaryCtgs: state.assembly.chrCtgs,
    companionCtgs: supportTrackCtgs,
    selectedPrimaryCtgId: state.assembly.selectedCtgId,
    selectedCompanionCtgId: state.assembly.selectedCtgId,
    prefs: trackPrefs,
  });
  const liveCtg = (Array.isArray(model?.companion?.ctgs) ? model.companion.ctgs : []).find(
    (ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId) === normalizedAssemblyCtgId,
  );
  if (!liveCtg) {
    return null;
  }
  const datasetName = getDatasetNameById(state.initializer?.datasets || [], normalizedDatasetId);
  return normalizeSupportMirrorEntry({
    datasetId: normalizedDatasetId,
    datasetName,
    chrName: String(state.assembly.selectedChrName || "").trim(),
    assemblyCtgId: normalizedAssemblyCtgId,
    name: String(liveCtg?.name || `Ctg${normalizedAssemblyCtgId}`),
    totalLength: Math.max(
      1,
      normalizePositiveInt(liveCtg?.totalLength ?? liveCtg?.lengthBp) ?? 1,
    ),
    anchorStart: normalizeNonNegativeInt(liveCtg?.anchorStart),
    lengthBp: Math.max(1, normalizePositiveInt(liveCtg?.lengthBp ?? liveCtg?.totalLength) ?? 1),
    startBp: Math.max(0, normalizeNonNegativeInt(liveCtg?.startBp) ?? 0),
    endBp: Math.max(
      1,
      normalizePositiveInt(liveCtg?.endBp)
        ?? (Math.max(0, normalizeNonNegativeInt(liveCtg?.startBp) ?? 0)
          + Math.max(1, normalizePositiveInt(liveCtg?.lengthBp ?? liveCtg?.totalLength) ?? 1)
          - 1),
    ),
    laneIndex: Math.max(0, normalizeNonNegativeInt(liveCtg?.laneIndex) ?? 0),
    hits: Array.isArray(liveCtg?.hits) ? liveCtg.hits.map((hit) => ({ ...hit })) : [],
  });
}

async function toggleSupportTrackCtgMirror(
  host,
  store,
  { datasetId, assemblyCtgId, shouldMirror },
  deps = projectAssemblyViewStateRuntimeDeps,
) {
  const normalizedDatasetId = normalizeSupportDatasetId(datasetId);
  const normalizedAssemblyCtgId = normalizeSupportDatasetId(assemblyCtgId);
  if (!normalizedDatasetId || !normalizedAssemblyCtgId) {
    return;
  }
  const state = store.getState();
  const currentMirrors = normalizeSupportMirroredCtgs(state.assembly.supportMirroredCtgs);
  const targetKey = buildSupportMirrorKey(normalizedDatasetId, normalizedAssemblyCtgId);
  const hasTarget = currentMirrors.some(
    (entry) => buildSupportMirrorKey(entry.datasetId, entry.assemblyCtgId) === targetKey,
  );
  let nextMirrors = currentMirrors;
  if (shouldMirror) {
    if (hasTarget) {
      return;
    }
    const nextEntry = buildSupportMirrorEntryFromAssemblyState(
      state,
      normalizedDatasetId,
      normalizedAssemblyCtgId,
    );
    if (!nextEntry) {
      store.setState({
        assembly: {
          ...state.assembly,
          actionStatus: "",
          actionError: tAssembly(state, "runtime.mirrorMissingSupport", {
            assemblyCtgId: normalizedAssemblyCtgId,
          }),
        },
      });
      rerender(host, store);
      return;
    }
    nextMirrors = normalizeSupportMirroredCtgs([...currentMirrors, nextEntry]);
  } else {
    if (!hasTarget) {
      return;
    }
    nextMirrors = currentMirrors.filter(
      (entry) => buildSupportMirrorKey(entry.datasetId, entry.assemblyCtgId) !== targetKey,
    );
  }
  store.setState({
    assembly: {
      ...state.assembly,
      supportMirroredCtgs: nextMirrors,
      actionStatus: shouldMirror
        ? tAssembly(state, "runtime.mirrorDone", { assemblyCtgId: normalizedAssemblyCtgId })
        : tAssembly(state, "runtime.unmirrorDone", { assemblyCtgId: normalizedAssemblyCtgId }),
      actionError: "",
    },
  });
  rerender(host, store);
  await persistProjectAssemblyViewStateFromStore(host, store, deps);
}

function updateDeletedCtgSelection(host, store, selectedRecordIds) {
  const normalized = normalizeDeletedCtgRecordIds(selectedRecordIds);
  const state = store.getState();
  const current = normalizeDeletedCtgRecordIds(state.assembly.selectedDeletedCtgRecordIds);
  if (current.length === normalized.length && current.every((value, index) => value === normalized[index])) {
    return;
  }
  store.setState({
    assembly: {
      ...state.assembly,
      selectedDeletedCtgRecordIds: normalized,
    },
  });
  rerender(host, store);
}

export function __testBindAssemblyContextMenu(host, store) {
  bindAssemblyContextMenuImpl(host, store, contextMenuRuntimeDeps);
}

export function __testBuildAssemblyContextMenuItems(args) {
  const input = args || {};
  return buildAssemblyContextMenuItems({
    ...input,
    actions: buildAssemblyContextMenuActionsImpl(contextMenuRuntimeDeps, input.actions || {}),
  });
}

export function __testResolveAssemblyCtgContextTarget(target) {
  return resolveAssemblyCtgContextTarget(target);
}

export function __testSyncSupportDatasetSelection(store, storage = null) {
  return syncSupportDatasetSelection(store, storage);
}

export async function __testToggleSupportTrackCtgMirror(host, store, payload, options = {}) {
  return toggleSupportTrackCtgMirror(
    host,
    store,
    payload,
    {
      persistProjectAssemblyViewState:
        options.persistProjectAssemblyViewState
        || projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    },
  );
}

export async function __testHandleTrackDeleteHotkey(host, store, event, options = {}) {
  return handleTrackDeleteHotkeyImpl(
    host,
    store,
    event,
    {
      ...trackHotkeyActionDeps,
      deleteSelectedTrackCtgs: options.deleteFn || trackHotkeyActionDeps.deleteSelectedTrackCtgs,
      deleteSelectedSubviewTrackPairCtgs: options.subviewDeleteFn || trackHotkeyActionDeps.deleteSelectedSubviewTrackPairCtgs,
    },
  );
}

export async function __testRunBatchDeleteTrackCtgs(host, store, selectedIds, options = {}) {
  return editorActionRuntimeAdapters.runBatchDeleteTrackCtgs(host, store, selectedIds, options);
}

export async function __testRunBatchRestoreDeletedCtgs(host, store, selectedRecordIds, options = {}) {
  return editorActionRuntimeAdapters.runBatchRestoreDeletedCtgs(host, store, selectedRecordIds, options);
}

export async function __testRestoreSelectedDeletedCtgs(host, store, selectedRecordIds, options = {}) {
  return editorActionRuntimeAdapters.restoreSelectedDeletedCtgs(host, store, selectedRecordIds, options);
}

export function __testCollectMemberChipSelectionResult(regionEl, selectionRect) {
  return collectMemberChipSelectionResultImpl(regionEl, selectionRect);
}

export function __testCreateEditorActionRuntimeAdapters(editorRuntimeDeps, impls = {}) {
  return createEditorActionRuntimeAdapters(editorRuntimeDeps, impls);
}

export function __testResolveAppendToPathFocusPatch(assembly, activePhasedTrackKey) {
  return resolveAppendToPathFocusPatch(assembly, activePhasedTrackKey);
}

export function __testRerenderAssemblyMainTab(host, store) {
  return rerenderAssemblyMainTab(host, store);
}

export function __testRerenderSubviewPanel(host, store) {
  return rerenderSubviewPanel(host, store);
}

export function __testRerenderBatchDeleteProgress(host, store) {
  return rerenderBatchDeleteProgress(host, store);
}

export function __testCompactFinalPathByDeletedPhasedTrack(finalPathByChr, options) {
  return compactFinalPathByDeletedPhasedTrack(finalPathByChr, options);
}

export function __testSetSelectedPrimaryTrackCtgsHidden(
  host,
  store,
  selectedIds,
  shouldHide,
  options = {},
) {
  return setSelectedPrimaryTrackCtgsHidden(host, store, selectedIds, shouldHide, {
    patchPrimaryHiddenCtgDom: options.patchPrimaryHiddenCtgDom || patchPrimaryHiddenCtgDom,
    refreshFinalPathLogAfterPrimaryHiddenPatch:
      options.refreshFinalPathLogAfterPrimaryHiddenPatch || refreshFinalPathLogAfterPrimaryHiddenPatch,
    persistProjectAssemblyViewState:
      options.persistProjectAssemblyViewState || (async (payload) => payload),
  });
}

export function __testTogglePrimaryTrackCtgHidden(
  host,
  store,
  assemblyCtgId,
  shouldHide,
  options = {},
) {
  return togglePrimaryTrackCtgHidden(host, store, assemblyCtgId, shouldHide, {
    patchPrimaryHiddenCtgDom: options.patchPrimaryHiddenCtgDom || patchPrimaryHiddenCtgDom,
    refreshFinalPathLogAfterPrimaryHiddenPatch:
      options.refreshFinalPathLogAfterPrimaryHiddenPatch || refreshFinalPathLogAfterPrimaryHiddenPatch,
    persistProjectAssemblyViewState:
      options.persistProjectAssemblyViewState || (async (payload) => payload),
  });
}

export function __testBuildSubviewSummaryFromCandidates(args) {
  return buildSubviewSummaryFromCandidates(args);
}

function resolveTrackContigClickAction({
  trackRole,
  contigId,
  phasedTrackId = null,
  phasedTrackItemId = null,
  phasedHaplotypeKey = "",
  ctrlKey = false,
  metaKey = false,
}) {
  const normalizedContigId = normalizeSupportDatasetId(contigId);
  const normalizedTrackRole = String(trackRole || "").trim();
  const normalizedPhasedTrackId = normalizeSupportDatasetId(phasedTrackId);
  const normalizedPhasedTrackItemId = normalizeSupportDatasetId(phasedTrackItemId);
  const normalizedPhasedHaplotypeKey = String(phasedHaplotypeKey || "").trim();
  if (
    normalizedContigId === null ||
    (
      normalizedTrackRole !== "primary"
      && normalizedTrackRole !== "support"
      && normalizedTrackRole !== "ref"
      && normalizedTrackRole !== "phased"
    )
  ) {
    return { type: "noop" };
  }
  if (ctrlKey || metaKey) {
    const action = {
      type: "select-subview-candidate",
      trackRole: normalizedTrackRole,
      contigId: normalizedContigId,
    };
    if (normalizedTrackRole === "phased") {
      if (normalizedPhasedTrackId !== null) {
        action.phasedTrackId = normalizedPhasedTrackId;
      }
      if (normalizedPhasedTrackItemId !== null) {
        action.phasedTrackItemId = normalizedPhasedTrackItemId;
      }
      if (normalizedPhasedHaplotypeKey) {
        action.phasedHaplotypeKey = normalizedPhasedHaplotypeKey;
      }
    }
    return action;
  }
  if (normalizedTrackRole === "ref") {
    return { type: "noop" };
  }
  return {
    type: "select-ctg",
    contigId: normalizedContigId,
  };
}

function promptForRenameCtg(host, store, assemblyCtgId) {
  if (typeof window === "undefined" || typeof window.prompt !== "function") {
    return "";
  }
  const state = store.getState();
  const currentCtg = (state.assembly.chrCtgs || []).find(
    (ctg) => Number(ctg.assemblyCtgId) === Number(assemblyCtgId),
  );
  const defaultName = String(currentCtg?.name || "").trim();
  return window.prompt(tAssembly(state, "prompts.renameContig", { assemblyCtgId }), defaultName) ?? "";
}

function promptForDeleteShorterThanLength(host, store, defaultValue = 100000) {
  const state = store.getState();
  return requestAssemblyPrompt(
    host,
    store,
    tAssembly(state, "prompts.deleteShorterThanLength"),
    String(defaultValue),
  );
}

function buildRenameCtgActionArgs(assemblyCtgId, rawName) {
  const normalizedAssemblyCtgId = normalizeSupportDatasetId(assemblyCtgId);
  const newName = String(rawName || "").trim();
  if (normalizedAssemblyCtgId === null || !newName) {
    return null;
  }
  return {
    assemblyCtgId: normalizedAssemblyCtgId,
    newName,
  };
}

function buildAssemblyStateForSupportDatasetSelection(assembly, supportDatasetId) {
  const nextSupportDatasetClearedAssembly = {
    ...assembly,
    supportChrCtgs: [],
  };
  return {
    ...nextSupportDatasetClearedAssembly,
    supportDatasetId,
    trackSelectedCtgIds: [],
    trackDragOffsets: filterTrackDragOffsets(
      nextSupportDatasetClearedAssembly.trackDragOffsets,
      nextSupportDatasetClearedAssembly,
      { preserveUnmatchedSupportOffsets: true },
    ),
    subviewTrackDragOffsets: [],
    selectedDeletedCtgRecordIds: [],
    subview: buildClearedSubviewState(assembly),
    summary: "",
  };
}

async function applySupportDatasetSelection(
  host,
  store,
  rawSupportDatasetId,
  {
    loadSupportChrCtgs = loadDatasetChrCtgs,
    persistProjectAssemblyViewState = projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerenderView = rerender,
  } = {},
) {
  const state = store.getState();
  const supportDatasetId = normalizeSupportDatasetId(rawSupportDatasetId);
  const currentSupportDatasetId = normalizeSupportDatasetId(state.assembly.supportDatasetId);
  if (supportDatasetId === currentSupportDatasetId) {
    return false;
  }

  const nextAssemblyState = buildAssemblyStateForSupportDatasetSelection(state.assembly, supportDatasetId);
  store.setState({
    ...state,
    assembly: nextAssemblyState,
  });
  rerenderView(host, store);
  await persistProjectAssemblyViewState({
    workspaceRoot: state.session.workspacePath,
    projectId: state.session.projectId,
    supportDatasetId,
    trackView: nextAssemblyState.trackView,
    supportMirroredCtgs: Array.isArray(nextAssemblyState.supportMirroredCtgs)
      ? nextAssemblyState.supportMirroredCtgs
      : [],
    hiddenPrimaryCtgIds: Array.isArray(nextAssemblyState.hiddenPrimaryCtgIds)
      ? nextAssemblyState.hiddenPrimaryCtgIds
      : [],
    trackDragOffsets: Array.isArray(nextAssemblyState.trackDragOffsets)
      ? nextAssemblyState.trackDragOffsets
      : [],
    subviewTrackDragOffsets: Array.isArray(nextAssemblyState.subviewTrackDragOffsets)
      ? nextAssemblyState.subviewTrackDragOffsets
      : [],
    trackScrollState: normalizeViewportScrollState(nextAssemblyState.trackScrollState),
    subviewTrackScrollState: normalizeViewportScrollState(nextAssemblyState.subviewTrackScrollState),
    finalPathTrackScrollState: normalizeViewportScrollState(nextAssemblyState.finalPathTrackScrollState),
    membersCardCollapsed: nextAssemblyState.membersCardCollapsed === false ? false : true,
    finalPathViewMode: normalizeFinalPathViewMode(nextAssemblyState.finalPathViewMode),
    finalPathByChr:
      nextAssemblyState.finalPathByChr &&
      typeof nextAssemblyState.finalPathByChr === "object" &&
      !Array.isArray(nextAssemblyState.finalPathByChr)
        ? nextAssemblyState.finalPathByChr
        : {},
  });

  if (
    !state.session.workspacePath ||
    !state.session.projectId ||
    !state.assembly.selectedChrName ||
    supportDatasetId === null
  ) {
    return true;
  }

  const supportChrCtgs = await loadSupportChrCtgs(
    state.session.workspacePath,
    state.session.projectId,
    state.assembly.selectedChrName,
    supportDatasetId,
  );
  const latestState = store.getState();
  if (
    normalizeSupportDatasetId(latestState.assembly.supportDatasetId) !== supportDatasetId ||
    String(latestState.assembly.selectedChrName || "").trim() !==
      String(state.assembly.selectedChrName || "").trim()
  ) {
    return true;
  }

  store.setState({
    ...latestState,
    assembly: {
      ...latestState.assembly,
      supportChrCtgs,
      summary: "",
    },
  });
  rerenderView(host, store);
  return true;
}

export async function __testApplySupportDatasetSelection(store, rawSupportDatasetId, options = {}) {
  return applySupportDatasetSelection(null, store, rawSupportDatasetId, {
    loadSupportChrCtgs: options.loadSupportChrCtgs,
    persistProjectAssemblyViewState: options.persistProjectAssemblyViewState || (async () => ({})),
    rerenderView: options.rerenderView || (() => {}),
  });
}

export function __testBindTrackScrollSync(host, store, deps = {}) {
  return bindTrackScrollSync(host, store, deps);
}

export function __testResetMeasuredTrackViewportWidths(nextWidths = null) {
  lastTrackViewportKey = "";
  lastTrackScrollLeft = 0;
  lastPrimaryTrackViewboxMinX = 0;
  lastSubviewViewportKey = "";
  lastSubviewScrollLeft = 0;
  lastFinalPathViewportKey = "";
  lastFinalPathScrollLeft = 0;
  pendingPrimaryViewportAnchorBp = null;
  pendingSubviewViewportAnchorBp = null;
  measuredTrackViewportPxByRole = resolveMeasuredTrackViewportWidths(
    nextWidths || {
      primary: 1200,
      subview: 1200,
      finalPath: 1200,
    },
    {
      primary: 1200,
      subview: 1200,
      finalPath: 1200,
    },
  );
  return measuredTrackViewportPxByRole;
}

function pickSelectedMember(assembly) {
  const members = assembly.ctgDetail?.members || [];
  if (!members.length) {
    return null;
  }
  return (
    members.find((member) => member.assemblySeqId === assembly.selectedMemberSeqId) || members[0]
  );
}

function findMemberBySeqId(assembly, assemblySeqId) {
  const members = assembly?.ctgDetail?.members || [];
  const normalizedSeqId = normalizeSupportDatasetId(assemblySeqId);
  if (!normalizedSeqId) {
    return null;
  }
  return members.find((member) => Number(member.assemblySeqId) === normalizedSeqId) || null;
}

function getSubviewState(assembly) {
  return getSubviewStateImpl(assembly);
}

function buildClearedSubviewState(assembly) {
  return {
    ...getSubviewStateImpl(assembly),
    selectedAContigId: null,
    selectedARole: "",
    selectedBContigId: null,
    selectedBRole: "",
    selectedTrackSelections: [],
    selectedTrackARole: "",
    selectedTrackBRole: "",
    selectedTrackBSource: "",
    selectedTrackBDatasetId: null,
    selectedTrackBIsMirror: false,
    trackPairHiddenCtgs: [],
    trackPairSelectedCtgs: [],
    message: "",
    error: "",
    summary: null,
  };
}

function normalizeSubviewMode() {
  return "2-contig";
}

function buildPrimaryCtgIdSet(assembly) {
  return new Set(
    (Array.isArray(assembly?.chrCtgs) ? assembly.chrCtgs : [])
      .map((ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId))
      .filter((ctgId) => ctgId !== null),
  );
}

function buildPhasedCtgIdSet(assembly) {
  return new Set(
    (Array.isArray(assembly?.phasedChrTracks) ? assembly.phasedChrTracks : [])
      .flatMap((track) => (Array.isArray(track?.items) ? track.items : []))
      .map((item) => normalizeSupportDatasetId(item?.assemblyCtgId))
      .filter((ctgId) => ctgId !== null),
  );
}

function canEditTrackCtg(ctgContext, assembly) {
  const ctgId = normalizeSupportDatasetId(ctgContext?.assemblyCtgId);
  if (!ctgId) {
    return false;
  }
  const trackRole = String(ctgContext?.trackRole || "").trim();
  if (trackRole === "primary" || trackRole === "") {
    return buildPrimaryCtgIdSet(assembly).has(ctgId);
  }
  if (trackRole === "support") {
    return (Array.isArray(assembly?.supportChrCtgs) ? assembly.supportChrCtgs : []).some(
      (ctg) => normalizeSupportDatasetId(ctg?.assemblyCtgId) === ctgId,
    );
  }
  if (trackRole === "phased") {
    return buildPhasedCtgIdSet(assembly).has(ctgId);
  }
  return false;
}

function buildActionAuditDetail(action, args, changed) {
  const argText = JSON.stringify(args || {});
  if (changed === null) {
    return `${action} args=${argText}`;
  }
  return `${action} changed=${changed ? "true" : "false"} args=${argText}`;
}

function appendAuditLog(store, { category, action, detail }) {
  const snapshot = store.getState();
  if (snapshot.session.workspacePath && snapshot.session.projectId) {
    void appendEditAuditLog({
      workspaceRoot: snapshot.session.workspacePath,
      projectId: snapshot.session.projectId,
      category,
      action,
      detail,
    });
  }
}

function bindAssemblyActionFeedbackDismiss(host, store) {
  const binding = ensureAssemblyActionFeedbackDismissBinding(host);
  binding.store = store;
  const signature = getAssemblyActionFeedbackSignature(store.getState().assembly);
  binding.coordinator.onFeedbackChange(signature);
}

function ensureAssemblyActionFeedbackDismissBinding(host) {
  if (host[ASSEMBLY_ACTION_FEEDBACK_DISMISS]) {
    return host[ASSEMBLY_ACTION_FEEDBACK_DISMISS];
  }
  const timerApi = resolveTimerApi();
  const binding = {
    store: null,
    coordinator: null,
  };
  binding.coordinator = createActionFeedbackDismissCoordinator({
    setTimeoutFn: timerApi.setTimeout.bind(timerApi),
    clearTimeoutFn: timerApi.clearTimeout.bind(timerApi),
    autoDismissMs: ACTION_FEEDBACK_AUTO_DISMISS_MS,
    pointerDismissMs: ACTION_FEEDBACK_POINTER_DISMISS_MS,
    onDismiss: () => {
      if (!binding.store) {
        return;
      }
      clearAssemblyActionFeedback(host, binding.store);
    },
  });
  if (typeof host?.addEventListener !== "function") {
    host[ASSEMBLY_ACTION_FEEDBACK_DISMISS] = binding;
    return binding;
  }
  host.addEventListener(
    "pointermove",
    () => {
      if (!binding.store) {
        return;
      }
      const signature = getAssemblyActionFeedbackSignature(binding.store.getState().assembly);
      if (!signature) {
        return;
      }
      binding.coordinator.onPointerMove(signature);
    },
    true,
  );
  host[ASSEMBLY_ACTION_FEEDBACK_DISMISS] = binding;
  return binding;
}

function resolveTimerApi() {
  if (
    typeof window !== "undefined" &&
    typeof window.setTimeout === "function" &&
    typeof window.clearTimeout === "function"
  ) {
    return window;
  }
  return globalThis;
}

function clearAssemblyActionFeedback(host, store) {
  const currentAssembly = store.getState().assembly;
  if (!currentAssembly.actionStatus && !currentAssembly.actionError) {
    return;
  }
  store.setState({
    assembly: {
      ...currentAssembly,
      actionStatus: "",
      actionError: "",
    },
  });
  rerender(host, store);
}

function createActionFeedbackDismissCoordinator({
  setTimeoutFn,
  clearTimeoutFn,
  autoDismissMs = ACTION_FEEDBACK_AUTO_DISMISS_MS,
  pointerDismissMs = ACTION_FEEDBACK_POINTER_DISMISS_MS,
  onDismiss,
} = {}) {
  const timerApi = resolveTimerApi();
  const scheduleTimeout =
    typeof setTimeoutFn === "function" ? setTimeoutFn : timerApi.setTimeout.bind(timerApi);
  const cancelTimeout =
    typeof clearTimeoutFn === "function" ? clearTimeoutFn : timerApi.clearTimeout.bind(timerApi);

  let currentSignature = "";
  let autoDismissTimer = null;
  let pointerDismissTimer = null;

  const clearAutoDismissTimer = () => {
    if (autoDismissTimer === null) {
      return;
    }
    cancelTimeout(autoDismissTimer);
    autoDismissTimer = null;
  };
  const clearPointerDismissTimer = () => {
    if (pointerDismissTimer === null) {
      return;
    }
    cancelTimeout(pointerDismissTimer);
    pointerDismissTimer = null;
  };
  const clearTimers = () => {
    clearAutoDismissTimer();
    clearPointerDismissTimer();
  };
  const dismiss = () => {
    currentSignature = "";
    clearTimers();
    onDismiss?.();
  };

  return {
    onFeedbackChange(signature) {
      const normalizedSignature = String(signature || "");
      if (!normalizedSignature) {
        currentSignature = "";
        clearTimers();
        return;
      }
      if (normalizedSignature === currentSignature) {
        return;
      }
      currentSignature = normalizedSignature;
      clearTimers();
      autoDismissTimer = scheduleTimeout(() => {
        autoDismissTimer = null;
        dismiss();
      }, autoDismissMs);
    },
    onPointerMove(signature) {
      const normalizedSignature = String(signature || "");
      if (!normalizedSignature) {
        return;
      }
      currentSignature = normalizedSignature;
      clearPointerDismissTimer();
      pointerDismissTimer = scheduleTimeout(() => {
        pointerDismissTimer = null;
        dismiss();
      }, pointerDismissMs);
    },
    dispose() {
      currentSignature = "";
      clearTimers();
    },
  };
}

function createSubviewBandTooltipCoordinator({
  setTimeoutFn,
  clearTimeoutFn,
  hoverDelayMs = SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS,
  onShow,
  onMove,
  onHide,
} = {}) {
  const timerApi = resolveTimerApi();
  const scheduleTimeout =
    typeof setTimeoutFn === "function" ? setTimeoutFn : timerApi.setTimeout.bind(timerApi);
  const cancelTimeout =
    typeof clearTimeoutFn === "function" ? clearTimeoutFn : timerApi.clearTimeout.bind(timerApi);

  let activeToken = null;
  let pendingContext = null;
  let hoverTimer = null;
  let visible = false;

  const clearHoverTimer = () => {
    if (hoverTimer === null) {
      return;
    }
    cancelTimeout(hoverTimer);
    hoverTimer = null;
  };
  const hide = () => {
    activeToken = null;
    pendingContext = null;
    clearHoverTimer();
    if (!visible) {
      return;
    }
    visible = false;
    onHide?.();
  };

  return {
    enter(context) {
      if (!context?.token) {
        return;
      }
      hide();
      pendingContext = context;
      hoverTimer = scheduleTimeout(() => {
        hoverTimer = null;
        if (!pendingContext?.token) {
          return;
        }
        const resolvedContext = pendingContext;
        pendingContext = null;
        activeToken = resolvedContext.token;
        visible = true;
        onShow?.(resolvedContext);
      }, hoverDelayMs);
    },
    move(context) {
      if (!context?.token) {
        return;
      }
      if (pendingContext?.token === context.token) {
        pendingContext = context;
        return;
      }
      if (visible && activeToken === context.token) {
        onMove?.(context);
      }
    },
    leave(token) {
      if (pendingContext?.token === token) {
        pendingContext = null;
        clearHoverTimer();
      }
      if (visible && activeToken === token) {
        hide();
      }
    },
    hide,
    dispose() {
      hide();
    },
  };
}

function createTrackViewportResizeCoordinator({
  getViewportWidths,
  getViewportWidth,
  getMeasuredWidths,
  getMeasuredWidth,
  setMeasuredWidths,
  setMeasuredWidth,
  onViewportResize,
}) {
  return {
    onResize() {
      const currentWidths = normalizeTrackViewportWidths(
        getMeasuredWidths?.() ?? getMeasuredWidth?.(),
      );
      const nextWidths = resolveMeasuredTrackViewportWidths(
        getViewportWidths?.() ?? getViewportWidth?.(),
        currentWidths,
      );
      if (!haveMeasuredTrackViewportWidthsChanged(currentWidths, nextWidths)) {
        return false;
      }
      if (typeof setMeasuredWidths === "function") {
        setMeasuredWidths(nextWidths);
      } else if (typeof setMeasuredWidth === "function") {
        setMeasuredWidth(nextWidths.primary);
      }
      onViewportResize?.(typeof getViewportWidths === "function" ? nextWidths : nextWidths.primary);
      return true;
    },
  };
}

function getAssemblyActionFeedbackSignature(assembly) {
  const actionStatus = String(assembly?.actionStatus || "").trim();
  const actionError = String(assembly?.actionError || "").trim();
  if (!actionStatus && !actionError) {
    return "";
  }
  return `${actionStatus}\u0000${actionError}`;
}

function setAssemblyActionFeedback(host, store, { actionStatus = "", actionError = "" }) {
  store.setState({
    assembly: {
      ...store.getState().assembly,
      actionError,
      actionStatus,
    },
  });
  rerender(host, store);
}

function setAssemblyActionFeedbackInMainTab(host, store, { actionStatus = "", actionError = "" }) {
  store.setState({
    assembly: {
      ...store.getState().assembly,
      actionError,
      actionStatus,
    },
  });
  rerenderAssemblyMainTab(host, store);
}

export function __testCreateActionFeedbackDismissCoordinator(options) {
  return createActionFeedbackDismissCoordinator(options);
}

export function __testCreateTrackViewportResizeCoordinator(options) {
  return createTrackViewportResizeCoordinator(options);
}

export function __testCreateSubviewBandTooltipCoordinator(options) {
  return createSubviewBandTooltipCoordinator(options);
}

export function __testCreatePhasedChrTrack(host, store) {
  return createPhasedChrTrack(host, store);
}

export function __testRemovePhasedTrackItem(host, store, payload) {
  return removePhasedTrackItem(host, store, payload);
}

export function __testInheritPrimaryTrackDragOffsetForPhasedItem(store, payload) {
  return inheritPrimaryTrackDragOffsetForPhasedItem(store, payload);
}

export function __testCancelSubviewPairwiseEvidence(host, store, options = {}) {
  return cancelSubviewPairwiseEvidence(host, store, options);
}

export function __testToggleSubviewContigFlip(host, store, payload, options = {}) {
  return toggleSubviewContigFlip(host, store, payload, options);
}

export function __testGetAssemblyActionFeedbackSignature(assembly) {
  return getAssemblyActionFeedbackSignature(assembly);
}

function displayNullable(value) {
  if (value === null || value === undefined) {
    return "NULL";
  }
  return String(value);
}

function getSortedContigListItems(items) {
  return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
    const leftStart = normalizeSortableAnchor(left.anchorStart);
    const rightStart = normalizeSortableAnchor(right.anchorStart);
    if (leftStart !== rightStart) {
      return leftStart - rightStart;
    }
    return Number(left.assemblyCtgId || 0) - Number(right.assemblyCtgId || 0);
  });
}

function buildAssemblyStats(assembly, i18n) {
  const placedCtgCount = (assembly.chromosomes || []).reduce(
    (sum, chr) => sum + Number(chr.ctgCount || 0),
    0,
  );
  const placedBp = (assembly.chromosomes || []).reduce(
    (sum, chr) => sum + Number(chr.placedBp || 0),
    0,
  );
  const selectedCtg = assembly.ctgDetail?.name || "-";
  return [
    { label: i18n.statsLabels.referenceGenomeId, value: displayNullable(assembly.referenceGenomeId || "-") },
    { label: i18n.statsLabels.chrCount, value: String((assembly.chromosomes || []).length) },
    { label: i18n.statsLabels.placedCtgCount, value: String(placedCtgCount) },
    { label: i18n.statsLabels.unplacedCtgCount, value: String(Number(assembly.unplacedCtgCount || 0)) },
    { label: i18n.statsLabels.placedBp, value: formatBp(placedBp) },
    { label: i18n.statsLabels.unplacedBp, value: formatBp(assembly.unplacedBp || 0) },
    { label: i18n.statsLabels.currentChr, value: String(assembly.selectedChrName || "-") },
    { label: i18n.statsLabels.currentCtg, value: String(selectedCtg) },
  ];
}

function getNewSequencesState(assembly) {
  return {
    loading: Boolean(assembly.newSequences?.loading),
    error: String(assembly.newSequences?.error || ""),
    items: Array.isArray(assembly.newSequences?.items) ? assembly.newSequences.items : [],
    loadedProjectId: assembly.newSequences?.loadedProjectId ?? null,
    loadedWorkspacePath: String(assembly.newSequences?.loadedWorkspacePath || "").trim(),
  };
}

function shouldReuseNewSequencesCache(currentState, { workspacePath, projectId }) {
  return (
    !currentState.error &&
    currentState.items.length > 0 &&
    Number(currentState.loadedProjectId) === Number(projectId) &&
    String(currentState.loadedWorkspacePath || "").trim() === String(workspacePath || "").trim()
  );
}

function normalizeSortableAnchor(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : Number.MAX_SAFE_INTEGER;
}

function formatAnchorStart(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? `${parsed.toLocaleString("en-US")} bp` : "-";
}

function formatBp(value) {
  const number = Number(value || 0);
  return `${number.toLocaleString("en-US")} bp`;
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
