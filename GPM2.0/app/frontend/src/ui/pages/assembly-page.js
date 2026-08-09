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
  getGrtProjectView,
  importAddCtgPackage,
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
  assemblyPageSession,
  resetAssemblyPageSession,
} from "./assembly/page-session.js";
import {
  createAssemblyConfirmController,
} from "./assembly/confirm-controller.js";
import {
  createDeferredRerenderCoordinator,
} from "./assembly/deferred-rerender-runtime.js";
import {
  createAssemblyDomPatchController,
} from "./assembly/dom-patch-runtime.js";
import {
  createSubviewInteractionController,
} from "./assembly/subview-interaction-controller.js";
import {
  createSubviewPairwiseController,
} from "./assembly/subview-pairwise-controller.js";
import {
  createSubviewSelectionController,
} from "./assembly/subview-selection-controller.js";
import {
  compactFinalPathByDeletedPhasedTrack,
  createPhasedTrackController,
} from "./assembly/phased-track-controller.js";
import {
  createAddCtgImportController,
} from "./assembly/add-ctg-import-controller.js";
import {
  createMainTrackStateController,
} from "./assembly/main-track-state-controller.js";
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
  bindSubviewRulerRuntime as bindSubviewRulerRuntimeImpl,
} from "./assembly/subview-ruler-runtime.js";
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
  restoreFinalPathFromGrtBaseline as restoreFinalPathFromGrtBaselineImpl,
  updateFinalPathRow as updateFinalPathRowImpl,
} from "./assembly/final-path-runtime.js";
import {
  launchFinalPathExportJob as launchFinalPathExportJobImpl,
} from "./assembly/final-path-export-runtime.js";
import {
  bindDegapCard as bindDegapCardImpl,
  openDegapSettings as openDegapSettingsImpl,
  requestDegapGapJob as requestDegapGapJobImpl,
  requestDegapTelseekerJob as requestDegapTelseekerJobImpl,
} from "./assembly/degap-runtime.js";
import {
  FINAL_PATH_ALL_KEY,
  normalizeFinalPathViewMode,
  resolveFinalPathSelectionKey,
} from "./assembly/final-path-state.js";
import { normalizeGrtProjectView } from "./assembly/grt-state.js";
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
  resolveTrackInnerWidthFromScale,
  resolveTickBpFromScale,
} from "./assembly/track-prefs.js";
import {
  areSubviewTrackDragOffsetsEqual,
  areTrackDragOffsetsEqual,
  buildSubviewTrackDragOffsetKey,
  buildTrackDragOffsetKey,
  filterPrimaryTrackSelectionCtgIds,
  filterSubviewTrackDragOffsetsBySummary,
  filterTrackDragOffsets,
  normalizeDeletedCtgRecordIds,
  normalizeHiddenPrimaryCtgIdsByChr,
  normalizeSupportMirroredCtgs,
  normalizeSupportDatasetId,
  normalizeTrackDragOffsets,
  normalizeTrackSelectionCtgIds,
  normalizeSubviewTrackDragOffsets,
  setSubviewTrackDragOffset,
  setTrackDragOffset,
  swapSubviewTrackDragOffsetsForSummarySwap,
} from "./assembly/selection-state.js";
import {
  areViewportScrollStatesEqual,
  buildFinalPathTrackViewportKey,
  normalizeViewportScrollState,
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
  createOffsetSubviewManualAnchor,
} from "./assembly/subview-anchor-state.js";
import {
  buildAssemblyContextMenuItems,
  resolveAssemblyCtgContextTarget,
  resolveDeletedCtgContextTarget,
  resolveSubviewTrackPairContextTarget,
  resolveTrackLabelContextTarget,
} from "./assembly/context-menu.js";
import {
  convertTrackOffsetPxToBp,
  renderAssemblyFinalPathCard as renderAssemblyFinalPathCardImpl,
  renderAssemblyMainTab as renderAssemblyMainTabImpl,
  renderAssemblyMainTrackSections as renderAssemblyMainTrackSectionsImpl,
  renderAssemblyStatusToast as renderAssemblyStatusToastImpl,
  renderAssemblySubviewPanel as renderAssemblySubviewPanelImpl,
  resolveSubviewTrackDragOffsetBp,
  resolveTrackDragOffsetBp,
  roundTrackMetric,
  SUBVIEW_BAND_TOOLTIP_HOVER_DELAY_MS,
} from "./assembly/render-tracks.js";
import { renderAssemblyPage as renderAssemblyPageShell } from "./assembly/render-shell.js";
import {
  resolveActiveTrackScrollElement,
  resolveTrackPointerContentPoint,
} from "./assembly/track-viewport.js";
import {
  createAssemblyViewportController,
  createTrackViewportResizeCoordinator,
} from "./assembly/viewport-runtime.js";

const endTypeOptions = ["normal", "gap", "telomere"];
const {
  bindTrackScrollSync,
  bindTrackViewportResize,
  getMeasuredTrackViewportPx,
  rememberTrackViewportAnchor,
} = createAssemblyViewportController({
  session: assemblyPageSession,
  getPersistDeps: () => projectAssemblyViewStateRuntimeDeps,
  getTimerApi: () => resolveTimerApi(),
  persistProjectAssemblyViewStateFromStore: (host, store, deps) =>
    persistProjectAssemblyViewStateFromStore(host, store, deps),
  rerender: (host, store) => rerender(host, store),
});
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
function renderAssemblyMainTrackSections(state) {
  return renderAssemblyMainTrackSectionsImpl(state, renderTracksDeps);
}
const {
  renderAssemblyConfirmModal,
  requestAssemblyConfirm,
  requestAssemblyPrompt,
  requestAssemblyAnchorOffsetPrompt,
  resolveAssemblyConfirmDialog,
} = createAssemblyConfirmController({
  createOffsetSubviewManualAnchor,
  escapeAttr,
  escapeHtml,
  getAssemblyI18n,
  rerender,
  tAssembly,
});
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
const {
  createRenderedAssemblyMainTabContent,
  patchAssemblyStatusToast,
  patchDeletedPrimaryTrackCtgsDom,
  patchPrimaryHiddenCtgDom,
  replaceRenderedAssemblySection,
} = createAssemblyDomPatchController({
  bindBandCanvasRuntime: bindBandCanvasRuntimeImpl,
  escapeHtml,
  filterPrimaryTrackSelectionCtgIds,
  getAssemblyI18n,
  normalizeTrackSelectionCtgIds,
  renderAssemblyMainTrackSections,
});
const {
  clearSubviewTrackPairHiddenCtgs,
  copySubviewAnchorWithOffset,
  deleteSubviewManualAnchor,
  setSubviewTrackPairCtgHidden,
  toggleSubviewAnchorEdge,
  toggleSubviewContigFlip,
} = createSubviewInteractionController({
  persistProjectAssemblyViewStateFromStore: (host, store) =>
    persistProjectAssemblyViewStateFromStore(host, store),
  requestAssemblyAnchorOffsetPrompt,
  rerenderSubviewPanel: (host, store) => rerenderSubviewPanel(host, store),
  setAssemblyActionFeedback: (host, store, feedback) =>
    setAssemblyActionFeedback(host, store, feedback),
  tAssembly,
});
const {
  buildInitialSubviewPairwiseEvidence,
  buildSubviewPairwiseEvidenceKey,
  cancelSubviewPairwiseEvidence,
  loadSubviewPairwiseEvidence,
  refreshSubviewPairwiseEvidence,
  shouldLoadSubviewPairwiseEvidence,
} = createSubviewPairwiseController({
  session: assemblyPageSession,
  rerenderSubviewPanel: (host, store) => rerenderSubviewPanel(host, store),
  scheduleDeferredSubviewPanelRerender: (host, store) =>
    scheduleDeferredSubviewPanelRerender(host, store),
});
const {
  enterSubviewFromCandidates,
  enterSubviewFromTrackSelections,
  handleSubviewCandidateRemoval,
  handleSubviewSwapTrackOrder,
  handleSubviewTrackSelectionRemoval,
  handleTrackSubviewCandidateSelection,
  handleTrackSubviewTrackSelection,
} = createSubviewSelectionController({
  buildInitialSubviewPairwiseEvidence,
  getCurrentProject: (state) => getCurrentProject(state),
  loadSubviewPairwiseEvidence,
  rerenderSubviewPanel: (host, store) => rerenderSubviewPanel(host, store),
});
const {
  addTrackContigToPhasedTrack,
  createPhasedChrTrack,
  deletePhasedTrack,
  inheritPrimaryTrackDragOffsetForPhasedItem,
  refreshPhasedTracksForCurrentChr,
  removePhasedTrackItem,
} = createPhasedTrackController({
  addCtgToPhasedChrTrack: addCtgToPhasedChrTrackApi,
  createPhasedChrTrack: createPhasedChrTrackApi,
  deletePhasedChrTrack: deletePhasedChrTrackApi,
  listPhasedChrTracks,
  mapAssemblyError,
  persistMainTrackViewState: (host, store) => persistMainTrackViewState(host, store),
  persistTrackDragOffsets: (host, store) => persistTrackDragOffsets(host, store),
  removePhasedChrTrackItem: removePhasedChrTrackItemApi,
  rerenderAssemblyMainTab: (host, store) => rerenderAssemblyMainTab(host, store),
  setAssemblyActionFeedbackInMainTab: (host, store, feedback) =>
    setAssemblyActionFeedbackInMainTab(host, store, feedback),
});
const {
  importAddCtgIntoTrack,
} = createAddCtgImportController({
  importAddCtgPackage,
  mapAssemblyError,
  pickZipFilePath,
  rerender: (host, store) => rerender(host, store),
  selectChromosome: (host, store, chrName) => selectChromosome(host, store, chrName),
});
const {
  setActiveHitsTrack,
  setSelectedPrimaryTrackCtgsHidden,
  togglePrimaryTrackCtgHidden,
  togglePrimaryTrackSelection,
  toggleSupportTrackCtgMirror,
  updateDeletedCtgSelection,
  updateTrackSelection,
} = createMainTrackStateController({
  buildDualTrackModel,
  getDatasetNameById,
  patchPrimaryHiddenCtgDom,
  persistProjectAssemblyViewStateFromStore: (host, store, overrides) =>
    persistProjectAssemblyViewStateFromStore(
      host,
      store,
      typeof overrides?.persistProjectAssemblyViewState === "function"
        ? overrides
        : projectAssemblyViewStateRuntimeDeps,
    ),
  refreshFinalPathLogAfterPrimaryHiddenPatch,
  rerender: (host, store) => rerender(host, store),
  rerenderAssemblyMainTab: (host, store) => rerenderAssemblyMainTab(host, store),
});
export function renderAssemblyPage(state) {
  return renderAssemblyPageShell(state, assemblyPageShellDeps);
}
const ASSEMBLY_ACTION_FEEDBACK_DISMISS = Symbol("assemblyActionFeedbackDismiss");
const ASSEMBLY_SUBVIEW_BAND_TOOLTIP_BOUND = Symbol("assemblySubviewBandTooltipBound");
const ACTION_FEEDBACK_AUTO_DISMISS_MS = 1000;
const ACTION_FEEDBACK_POINTER_DISMISS_MS = 500;

function getDeferredRerenderCoordinator() {
  if (!assemblyPageSession.deferredRerenderCoordinator) {
    assemblyPageSession.deferredRerenderCoordinator = createDeferredRerenderCoordinator({
      rerender,
      rerenderSubviewPanel,
    });
  }
  return assemblyPageSession.deferredRerenderCoordinator;
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

export function __testHandleSubviewSwapTrackOrder(host, store) {
  return handleSubviewSwapTrackOrder(host, store);
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

function normalizeTrackFocusMode(rawMode) {
  return String(rawMode || "").trim().toLowerCase() === "start" ? "start" : "center";
}

export function bindAssemblyPage(host, store, options = {}) {
  const result = bindAssemblyPageImpl(
    host,
    store,
    createAssemblyPageBindingDeps(options),
    { scope: options.scope },
  );
  if (!options.scope) {
    scrollAssemblyToBottomIfRequested(host, store);
  }
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

function createAssemblyPageBindingDeps(options = {}) {
  const rerenderImpl = typeof options.rerender === "function" ? options.rerender : rerender;
  const rerenderAssemblyMainTabImpl = typeof options.rerenderAssemblyMainTab === "function"
    ? options.rerenderAssemblyMainTab
    : rerenderAssemblyMainTab;
  return {
    appendFinalPathRow,
    createEmptyFinalPathRow,
    applySupportDatasetSelection,
    cancelSubviewPairwiseEvidence,
    bindAssemblyActionFeedbackDismiss: (host, store) => bindAssemblyActionFeedbackDismiss(
      host,
      store,
      { rerender: rerenderImpl },
    ),
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
    bindDegapCard: (host, store) => bindDegapCardImpl(host, store, degapRuntimeDeps),
    bindBandCanvasRuntime: (host) => bindBandCanvasRuntimeImpl(host),
    bindSubviewRulerRuntime: (host) => bindSubviewRulerRuntimeImpl(host),
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
      assemblyPageSession.suppressNextTrackAutoFocus = true;
    },
    persistMainTrackViewState,
    requestAssemblyConfirm,
    requestAssemblyAnchorOffsetPrompt,
    rerenderAssemblyMainTab: rerenderAssemblyMainTabImpl,
    rerenderFinalPathCard,
    rerenderSubviewPanel,
    refreshSubviewPairwiseEvidence,
    rememberTrackViewportAnchor,
    rerender: rerenderImpl,
    resolveAssemblyConfirmDialog,
    resolveTrackContigClickAction,
    removeFinalPathRow,
    restoreFinalPathFromGrtBaseline,
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
  getGrtProjectView,
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
  normalizeGrtProjectView,
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
    assemblyPageSession.pendingTrackAutoFocusMode = mode;
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

const degapRuntimeDeps = {
  rerender,
  confirm: (message, context = {}) => requestAssemblyConfirm(context.host, context.store, message),
  mapAssemblyError,
  persistDegapProjectState: (host, store) =>
    persistProjectAssemblyViewStateFromStore(host, store, projectAssemblyViewStateRuntimeDeps),
};

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
  openDegapSettings: (host, store) => openDegapSettingsImpl(host, store, degapRuntimeDeps),
  requestDegapGapJob: (host, store, payload) =>
    requestDegapGapJobImpl(host, store, payload, degapRuntimeDeps),
  requestDegapTelseekerJob: (host, store, payload) =>
    requestDegapTelseekerJobImpl(host, store, payload, degapRuntimeDeps),
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
  copySubviewAnchorWithOffset,
  deleteSubviewManualAnchor,
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
    assemblyPageSession.trackContigDragActive = Boolean(value);
  },
  setSuppressTrackContigClickUntil: (value) => {
    assemblyPageSession.suppressTrackContigClickUntil = value;
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
  rerenderFinalPathCard(host, store);
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
    rerender: rerenderFinalPathCard,
  }, options);
}

async function appendFinalPathRow(host, store, payload = {}) {
  return appendFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function restoreFinalPathFromGrtBaseline(host, store, payload = {}) {
  return restoreFinalPathFromGrtBaselineImpl(host, store, payload, {
    confirm: (message) => requestAssemblyConfirm(host, store, message),
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function addFinalPathGapRelativeToSegment(host, store, payload) {
  return addFinalPathGapRelativeToSegmentImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function addFinalPathContigRelativeToSegment(host, store, payload) {
  return addFinalPathContigRelativeToSegmentImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function createEmptyFinalPathRow(host, store, payload) {
  return createEmptyFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function flipFinalPathSegment(host, store, payload) {
  return flipFinalPathSegmentImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function updateFinalPathRow(host, store, payload) {
  return updateFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function deleteFinalPathSegment(host, store, payload) {
  return removeFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function removeFinalPathRow(host, store, payload) {
  return removeFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function moveFinalPathRow(host, store, payload) {
  return moveFinalPathRowImpl(host, store, payload, {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
  });
}

async function updateSupportDatasetSelection(host, store, rawSupportDatasetId) {
  await applySupportDatasetSelection(host, store, rawSupportDatasetId);
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
    assemblyPageSession.lastSupportDsSessionKey = "";
    assemblyPageSession.lastSupportDsSelection = null;
    return { changed: false, supportDatasetId: null };
  }

  const supportDatasetOptions = getSupportDatasetOptions(state);
  const candidateIds = new Set(supportDatasetOptions.map((dataset) => dataset.datasetId));
  const currentSelection = normalizeSupportDatasetId(state.assembly.supportDatasetId);

  if (storageKey !== assemblyPageSession.lastSupportDsSessionKey) {
    assemblyPageSession.lastSupportDsSessionKey = storageKey;
    if (currentSelection !== null && candidateIds.has(currentSelection)) {
      saveSupportDsState(workspacePath, projectId, { supportDatasetId: currentSelection }, storage || undefined);
      assemblyPageSession.lastSupportDsSelection = currentSelection;
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
    assemblyPageSession.lastSupportDsSelection = nextSelection;
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
    assemblyPageSession.lastSupportDsSelection = fallbackSelection;
    if (currentSelection !== fallbackSelection) {
      return { changed: true, supportDatasetId: fallbackSelection };
    }
  }
  if (currentSelection === null && supportDatasetOptions.length > 0) {
    const fallbackSelection = supportDatasetOptions[0]?.datasetId || null;
    assemblyPageSession.lastSupportDsSelection = fallbackSelection;
    if (fallbackSelection !== null) {
      saveSupportDsState(workspacePath, projectId, { supportDatasetId: fallbackSelection }, storage || undefined);
      return { changed: true, supportDatasetId: fallbackSelection };
    }
  }

  if (currentSelection !== assemblyPageSession.lastSupportDsSelection) {
    saveSupportDsState(workspacePath, projectId, { supportDatasetId: currentSelection }, storage || undefined);
    assemblyPageSession.lastSupportDsSelection = currentSelection;
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
  template.innerHTML = renderAssemblyMainTrackSections(store.getState());
  const nextContent = template.content;
  const replacedNodes = [
    replaceRenderedAssemblySection(routeHost, nextContent, ".chr-strip.has-members-panel"),
    replaceRenderedAssemblySection(routeHost, nextContent, ".assembly-track-unified"),
  ].filter(Boolean);
  if (!replacedNodes.length) {
    rerender(host, store);
    return;
  }
  patchAssemblyStatusToast(routeHost, nextContent);
  replacedNodes.forEach((node) => {
    bindAssemblyPage(node, store, {
      scope: "main",
      rerender: rerenderAssemblyMainTab,
      rerenderAssemblyMainTab,
    });
  });
}

function rerenderFinalPathCard(host, store) {
  cancelDeferredRerender();
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    rerender(host, store);
    return;
  }
  const currentCard = routeHost.querySelector?.(".final-path-card") || null;
  const doc = routeHost.ownerDocument || host?.ownerDocument || globalThis.document;
  if (!currentCard || !doc?.createElement) {
    rerender(host, store);
    return;
  }
  const currentScrollEl = currentCard.querySelector?.("[data-final-path-graph-viewport]")
    || currentCard.querySelector?.(".assembly-final-path-svg-wrap")
    || null;
  const currentScrollLeft = Number(currentScrollEl?.scrollLeft || 0);
  const currentState = store.getState();
  if (currentScrollEl && Number.isFinite(currentScrollLeft)) {
    const nextScrollState = normalizeViewportScrollState({
      viewportKey: buildFinalPathTrackViewportKey(currentState),
      scrollLeft: currentScrollLeft,
    });
    if (!areViewportScrollStatesEqual(currentState.assembly?.finalPathTrackScrollState, nextScrollState)) {
      store.setState({
        ...currentState,
        assembly: {
          ...currentState.assembly,
          finalPathTrackScrollState: nextScrollState,
        },
      });
    }
  }
  const template = doc.createElement("template");
  template.innerHTML = renderAssemblyFinalPathCardImpl(store.getState(), renderTracksDeps);
  const nextCard = template.content.firstElementChild;
  if (!nextCard || !nextCard.matches?.(".final-path-card")) {
    rerender(host, store);
    return;
  }
  currentCard.replaceWith(nextCard);

  const toastTemplate = doc.createElement("template");
  toastTemplate.innerHTML = `<section class="assembly-main-view">${renderAssemblyStatusToastImpl(store.getState(), renderTracksDeps)}</section>`;
  patchAssemblyStatusToast(routeHost, toastTemplate.content);
  bindAssemblyPage(nextCard, store, {
    scope: "final-path",
    rerender: rerenderFinalPathCard,
  });
  return nextCard;
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

function refreshFinalPathLogAfterPrimaryHiddenPatch(host, store) {
  const state = store.getState();
  if (normalizeFinalPathViewMode(state.assembly?.finalPathViewMode) !== "log") {
    return false;
  }
  rerenderAssemblyMainTab(host, store);
  return true;
}

function rerenderSubviewPanel(host, store) {
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    rerender(host, store);
    return;
  }
  if (typeof routeHost.querySelector !== "function") {
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
  bindAssemblyPage(nextPanel, store, {
    scope: "subview",
    rerender: rerenderSubviewPanel,
  });
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

function isTrackRectOverlap(leftRect, rightRect) {
  return !(
    leftRect.right < rightRect.left ||
    leftRect.left > rightRect.right ||
    leftRect.bottom < rightRect.top ||
    leftRect.top > rightRect.bottom
  );
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

function shouldSuppressTrackContigClick() {
  return Date.now() <= assemblyPageSession.suppressTrackContigClickUntil;
}

function applyTrackDragOffset(host, store, nextOffset) {
  const state = store.getState();
  const normalizedCurrent = normalizeTrackDragOffsets(state.assembly.trackDragOffsets);
  const normalizedNext = setTrackDragOffset(normalizedCurrent, nextOffset);
  if (areTrackDragOffsetsEqual(normalizedCurrent, normalizedNext)) {
    return;
  }
  assemblyPageSession.suppressNextTrackAutoFocus = true;
  store.setState({
    assembly: {
      ...state.assembly,
      trackDragOffsets: normalizedNext,
    },
  });
  rerenderAssemblyMainTab(host, store);
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
  rerenderSubviewPanel(host, store);
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
      subviewAnchorStateByKey:
        state.assembly.subviewAnchorStateByKey
        && typeof state.assembly.subviewAnchorStateByKey === "object"
        && !Array.isArray(state.assembly.subviewAnchorStateByKey)
          ? state.assembly.subviewAnchorStateByKey
          : {},
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

export function __testRenderAssemblyMainTrackSections(state) {
  return renderAssemblyMainTrackSections(state);
}

export function __testRenderAssemblyFinalPathCard(state) {
  return renderAssemblyFinalPathCardImpl(state, renderTracksDeps);
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
    subviewAnchorStateByKey:
      nextAssemblyState.subviewAnchorStateByKey
      && typeof nextAssemblyState.subviewAnchorStateByKey === "object"
      && !Array.isArray(nextAssemblyState.subviewAnchorStateByKey)
        ? nextAssemblyState.subviewAnchorStateByKey
        : {},
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
  return resetAssemblyPageSession(nextWidths);
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

function bindAssemblyActionFeedbackDismiss(host, store, options = {}) {
  const binding = ensureAssemblyActionFeedbackDismissBinding(host, options);
  binding.store = store;
  const signature = getAssemblyActionFeedbackSignature(store.getState().assembly);
  binding.coordinator.onFeedbackChange(signature);
}

function ensureAssemblyActionFeedbackDismissBinding(host, options = {}) {
  if (host[ASSEMBLY_ACTION_FEEDBACK_DISMISS]) {
    if (typeof options.rerender === "function") {
      host[ASSEMBLY_ACTION_FEEDBACK_DISMISS].rerender = options.rerender;
    }
    return host[ASSEMBLY_ACTION_FEEDBACK_DISMISS];
  }
  const timerApi = resolveTimerApi();
  const binding = {
    store: null,
    coordinator: null,
    rerender: typeof options.rerender === "function" ? options.rerender : rerender,
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
      clearAssemblyActionFeedback(host, binding.store, binding.rerender);
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

function clearAssemblyActionFeedback(host, store, rerenderImpl = rerender) {
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
  rerenderImpl(host, store);
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
