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
  getMainViewHistoryStatus,
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
  runMainViewBatchDelete,
  runMainViewEditorAction,
  runMainViewLayoutAction as runMainViewLayoutActionApi,
  executeMainViewHistoryAction,
  inspectMainViewDelete,
  writeFinalPathExportBinaryFile,
  writeFinalPathExportTextFile,
} from "../../services/workflow-api.js";
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
  commitSubviewHistoryOperation,
} from "./assembly/subview-history-state.js";
import {
  runMainViewHistoryControlAction as runMainViewHistoryControlActionImpl,
} from "./assembly/main-view-history-runtime.js";
import {
  runMainViewLayoutAction as runMainViewLayoutActionImpl,
} from "./assembly/main-view-layout-runtime.js";
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
  createSupportDatasetController,
} from "./assembly/support-dataset-controller.js";
import {
  createBatchDeleteRefreshController,
} from "./assembly/batch-delete-refresh-controller.js";
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
  createAssemblyProgressModalRenderer,
} from "./assembly/progress-modals.js";
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
  requestAssemblyNotice,
  requestAssemblyPrompt,
  requestAssemblyAnchorOffsetPrompt,
  resolveAssemblyConfirmDialog,
} = createAssemblyConfirmController({
  createOffsetSubviewManualAnchor,
  escapeAttr,
  escapeHtml,
  getAssemblyI18n,
  rerender,
  rerenderDialog: rerenderAssemblyConfirmModal,
  tAssembly,
});
const {
  renderAddCtgImportProgressModal,
  renderBatchDeleteProgressModal,
  renderFinalPathExportModal,
} = createAssemblyProgressModalRenderer({
  escapeAttr,
  escapeHtml,
  getAssemblyI18n,
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
  handleSubviewHistoryReset,
  handleSubviewHistoryRestoreRollback,
  handleSubviewHistoryRollback,
  handleSubviewSwapTrackOrder,
  handleSubviewTrackSelectionRemoval,
  handleTrackSubviewCandidateSelection,
  handleTrackSubviewTrackSelection,
} = createSubviewSelectionController({
  buildInitialSubviewPairwiseEvidence,
  getCurrentProject: (state) => getCurrentProject(state),
  loadSubviewPairwiseEvidence,
  persistProjectAssemblyViewStateFromStore: (host, store) =>
    persistProjectAssemblyViewStateFromStore(host, store),
  rerenderAssemblyMainTab: (host, store) => rerenderAssemblyMainTab(host, store),
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
  requestAssemblyNotice,
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
  runMainViewLayoutAction: (host, store, payload) =>
    runMainViewLayoutActionImpl(host, store, payload, mainViewLayoutRuntimeDeps),
  refreshFinalPathLogAfterPrimaryHiddenPatch,
  rerender: (host, store) => rerender(host, store),
  rerenderAssemblyMainTab: (host, store) => rerenderAssemblyMainTab(host, store),
});
const {
  applySupportDatasetSelection,
  syncSupportDatasetSelection,
} = createSupportDatasetController({
  buildClearedSubviewState,
  getSupportDatasetOptions,
  loadSupportChrCtgs: (workspaceRoot, projectId, chrName, datasetId) =>
    loadDatasetChrCtgs(workspaceRoot, projectId, chrName, datasetId),
  persistProjectAssemblyViewState: (args) =>
    projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState(args),
  rerender: (host, store) => rerender(host, store),
  session: assemblyPageSession,
});
const {
  refreshAfterBatchDelete,
} = createBatchDeleteRefreshController({
  bindAssemblyPage: (host, store) => bindAssemblyPage(host, store),
  buildClearedSubviewState,
  createRenderedAssemblyMainTabContent,
  getCurrentProject,
  loadDeletedCtgsForChr: (workspaceRoot, projectId, chrName, datasetId) =>
    loadDeletedCtgsForChr(workspaceRoot, projectId, chrName, datasetId),
  loadProjectAssemblyViewState: (args) => loadProjectAssemblyViewStateImpl(args),
  patchAssemblyStatusToast,
  patchDeletedPrimaryTrackCtgsDom,
  replaceRenderedAssemblySection,
  rerenderAssemblyMainTab: (host, store) => rerenderAssemblyMainTab(host, store),
  rerenderSubviewPanel: (host, store) => rerenderSubviewPanel(host, store),
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
    handleSubviewHistoryReset,
    handleSubviewHistoryRestoreRollback,
    handleSubviewHistoryRollback,
    handleSubviewSwapTrackOrder,
    runMainViewHistoryControlAction: (host, store, action) =>
      runMainViewHistoryControlActionImpl(host, store, action, mainViewHistoryRuntimeDeps),
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
    deleteSelectedTrackCtgs: (host, store, selectedIds, options = {}) => deleteSelectedTrackCtgs(
      host,
      store,
      selectedIds,
      batchDeleteRuntimeDeps,
      {
        confirm: (message) => batchDeleteRuntimeDeps.confirm(message, { host, store }),
        ...options,
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
  getMainViewHistoryStatus,
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

const mainViewLayoutRuntimeDeps = {
  loadProjectAssemblyViewState: (args) => loadProjectAssemblyViewStateImpl(args),
  mapAssemblyError,
  rerender: rerenderAssemblyMainTab,
  runMainViewLayoutAction: runMainViewLayoutActionApi,
  runSerializedProjectViewMutation: (store, task) =>
    runSerializedProjectViewMutation(store, task),
};

const editorActionsRuntimeDeps = {
  appendAuditLog,
  buildActionAuditDetail,
  loadAssemblyView,
  loadAssemblyViewForLocalAssemblyRefresh,
  mapAssemblyError,
  persistProjectAssemblyViewStateFromStore: (host, store) =>
    persistProjectAssemblyViewStateFromStore(host, store),
  rebaseTrackDragOffsetsAfterRestore,
  refreshPhasedTracksForCurrentChr,
  refreshAfterBatchDelete,
  rerender,
  rerenderAssemblyMainTab,
  rerenderBatchDeleteProgress,
  runAction: runCtgEditorAction,
  runMainAction: runMainViewEditorAction,
  runBatchDelete: runMainViewBatchDelete,
  inspectMainViewDelete,
  confirm: (message, context = {}) => requestAssemblyConfirm(context.host, context.store, message),
};

const editorActionRuntimeAdapters = createEditorActionRuntimeAdapters(editorActionsRuntimeDeps);

const mainViewHistoryRuntimeDeps = {
  executeMainViewHistoryAction,
  loadAssemblyView,
  mapAssemblyError,
  runSerializedProjectViewMutation: (store, task) =>
    runSerializedProjectViewMutation(store, task),
  rerender: rerenderAssemblyMainTab,
  setPendingTrackAutoFocusMode: (mode) => {
    assemblyPageSession.pendingTrackAutoFocusMode = mode;
  },
  confirm: (message, context = {}) => requestAssemblyConfirm(context.host, context.store, message),
  scheduleHighlightClear: (host, store, assemblyCtgId) => {
    globalThis.setTimeout(() => {
      const state = store.getState();
      if (Number(state.assembly?.historyHighlightCtgId) !== Number(assemblyCtgId)) {
        return;
      }
      store.setState({
        assembly: {
          ...state.assembly,
          historyHighlightCtgId: null,
        },
      });
      rerenderAssemblyMainTab(host, store);
    }, 1400);
  },
};

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
  clearSubviewTrackDragPreview,
  clearTrackDragPreview,
  commitTrackDragOffset,
  convertTrackOffsetPxToBp,
  persistSubviewTrackDragOffsets,
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
  deleteSelectedTrackCtgs: editorActionRuntimeAdapters.deleteSelectedTrackCtgs,
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

function rerenderGrtResultConsumers(host, store) {
  rerenderAssemblyMainTab(host, store);
  rerenderSubviewPanel(host, store);
}

function createFinalPathMutationRuntimeDeps(overrides = {}) {
  return {
    persistProjectAssemblyViewState:
      projectAssemblyViewStateRuntimeDeps.persistProjectAssemblyViewState,
    rerender: rerenderFinalPathCard,
    rerenderGrtResultConsumers,
    ...overrides,
  };
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
  return appendTrackContigToFinalPathImpl(
    host,
    store,
    ctgContext,
    createFinalPathMutationRuntimeDeps(),
    options,
  );
}

async function appendFinalPathRow(host, store, payload = {}) {
  return appendFinalPathRowImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
}

async function restoreFinalPathFromGrtBaseline(host, store, payload = {}) {
  return restoreFinalPathFromGrtBaselineImpl(host, store, payload, createFinalPathMutationRuntimeDeps({
    confirm: (message) => requestAssemblyConfirm(host, store, message),
  }));
}

async function addFinalPathGapRelativeToSegment(host, store, payload) {
  return addFinalPathGapRelativeToSegmentImpl(
    host,
    store,
    payload,
    createFinalPathMutationRuntimeDeps(),
  );
}

async function addFinalPathContigRelativeToSegment(host, store, payload) {
  return addFinalPathContigRelativeToSegmentImpl(
    host,
    store,
    payload,
    createFinalPathMutationRuntimeDeps(),
  );
}

async function createEmptyFinalPathRow(host, store, payload) {
  return createEmptyFinalPathRowImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
}

async function flipFinalPathSegment(host, store, payload) {
  return flipFinalPathSegmentImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
}

async function updateFinalPathRow(host, store, payload) {
  return updateFinalPathRowImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
}

async function deleteFinalPathSegment(host, store, payload) {
  return removeFinalPathRowImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
}

async function removeFinalPathRow(host, store, payload) {
  return removeFinalPathRowImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
}

async function moveFinalPathRow(host, store, payload) {
  return moveFinalPathRowImpl(host, store, payload, createFinalPathMutationRuntimeDeps());
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

function rerender(host, store) {
  cancelDeferredRerender();
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    return;
  }
  routeHost.innerHTML = renderAssemblyPage(store.getState());
  bindAssemblyPage(routeHost, store);
}

function rerenderAssemblyConfirmModal(host, store) {
  const routeHost = resolveCurrentRouteHost(host);
  if (!routeHost) {
    return;
  }
  const currentOverlay = routeHost.querySelector?.("[data-assembly-confirm-overlay='true']") || null;
  const nextHtml = renderAssemblyConfirmModal(store.getState());
  if (!nextHtml) {
    currentOverlay?.remove?.();
    return;
  }
  const doc = routeHost.ownerDocument || host?.ownerDocument || globalThis.document;
  if (!doc?.createElement) {
    rerender(host, store);
    return;
  }
  const template = doc.createElement("template");
  template.innerHTML = nextHtml;
  const nextOverlay = template.content.firstElementChild;
  if (!nextOverlay) {
    return;
  }
  if (currentOverlay) {
    currentOverlay.replaceWith(nextOverlay);
  } else {
    (routeHost.querySelector?.(".page") || routeHost).appendChild(nextOverlay);
  }
  bindAssemblyPage(nextOverlay, store, { scope: "main" });
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

function commitTrackDragOffset(host, store, nextOffset) {
  const state = store.getState();
  const normalizedCurrent = normalizeTrackDragOffsets(state.assembly?.trackDragOffsets);
  const normalizedNext = setTrackDragOffset(normalizedCurrent, nextOffset);
  if (areTrackDragOffsetsEqual(normalizedCurrent, normalizedNext)) {
    return Promise.resolve(false);
  }
  assemblyPageSession.suppressNextTrackAutoFocus = true;
  return runMainViewLayoutActionImpl(
    host,
    store,
    { action: "drag-ctg", args: nextOffset },
    mainViewLayoutRuntimeDeps,
  );
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
  const committed = commitSubviewHistoryOperation(state.assembly, {
    nextSubview: state.assembly.subview,
    nextSubviewTrackDragOffsets: normalizedNext,
    operation: { kind: "drag-contig" },
    stateOrLocale: state,
  });
  if (!committed.changed) {
    return;
  }
  store.setState({ assembly: committed.assembly });
  rerenderSubviewPanel(host, store);
}

async function persistProjectAssemblyViewStateFromStore(
  host,
  store,
  deps = projectAssemblyViewStateRuntimeDeps,
) {
  const requestedIdentity = captureProjectViewIdentity(store.getState());
  if (!requestedIdentity) {
    return;
  }
  return assemblyPageSession.projectViewMutationCoordinator.enqueue(async (isCurrent) => {
    if (!isCurrent() || !matchesProjectViewIdentity(store.getState(), requestedIdentity)) {
      return;
    }
    return persistProjectAssemblyViewStateFromStoreNow(host, store, deps, requestedIdentity);
  });
}

function captureProjectViewIdentity(state) {
  const workspaceRoot = String(state?.session?.workspacePath || "").trim();
  const projectId = Number(state?.session?.projectId || 0);
  if (!workspaceRoot || !Number.isFinite(projectId) || projectId <= 0) {
    return null;
  }
  return { workspaceRoot, projectId: Math.trunc(projectId) };
}

function matchesProjectViewIdentity(state, identity) {
  const current = captureProjectViewIdentity(state);
  return Boolean(
    current
    && identity
    && current.workspaceRoot === identity.workspaceRoot
    && current.projectId === identity.projectId,
  );
}

function runSerializedProjectViewMutation(store, task) {
  const requestedIdentity = captureProjectViewIdentity(store?.getState?.());
  if (!requestedIdentity || typeof task !== "function") {
    return Promise.resolve(false);
  }
  return assemblyPageSession.projectViewMutationCoordinator.enqueue((isCoordinatorCurrent) => {
    const isCurrent = () =>
      isCoordinatorCurrent() && matchesProjectViewIdentity(store.getState(), requestedIdentity);
    if (!isCurrent()) {
      return false;
    }
    return task(isCurrent);
  });
}

async function persistProjectAssemblyViewStateFromStoreNow(
  host,
  store,
  deps,
  requestedIdentity,
) {
  const state = store.getState();
  if (!matchesProjectViewIdentity(state, requestedIdentity)) {
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
      workspaceRoot: requestedIdentity.workspaceRoot,
      projectId: requestedIdentity.projectId,
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
      subviewHistoryByKey:
        state.assembly.subviewHistoryByKey
        && typeof state.assembly.subviewHistoryByKey === "object"
        && !Array.isArray(state.assembly.subviewHistoryByKey)
          ? state.assembly.subviewHistoryByKey
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
    if (!matchesProjectViewIdentity(store.getState(), requestedIdentity)) {
      return;
    }
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
      runMainViewLayoutAction: options.runMainViewLayoutAction,
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
