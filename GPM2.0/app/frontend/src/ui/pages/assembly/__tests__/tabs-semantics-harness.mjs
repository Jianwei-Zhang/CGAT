import test from "node:test";
import assert from "node:assert/strict";
import * as renderTracks from "../render-tracks.js";
import { setSubviewAnchorStateForSummary } from "../subview-anchor-state.js";
import { readStylesheetTree } from "../../../../styles/__tests__/style-test-support.mjs";
import {
  addCtgToPhasedChrTrack,
  createPhasedChrTrack,
  initializeProject,
  updateProject,
} from "../../../../services/workflow-api.js";

import { bindAssemblyPage as bindAssemblyPageImpl } from "../bindings.js";
import {
  bindAssemblyPage,
  __testApplySupportDatasetSelection,
  __testBuildAssemblyContextMenuItems,
  __testCreateEditorActionRuntimeAdapters,
  __testBuildSubviewSummaryFromCandidates,
  __testBindAssemblyContextMenu,
  __testCreateActionFeedbackDismissCoordinator,
  __testCreateTrackViewportResizeCoordinator,
  __testCreateSubviewBandTooltipCoordinator,
  __testCreatePhasedChrTrack,
  __testInheritPrimaryTrackDragOffsetForPhasedItem,
  __testRemovePhasedTrackItem,
  __testGetAssemblyActionFeedbackSignature,
  __testEnterSubviewFromCandidates,
  __testEnterSubviewFromTrackSelections,
  __testHandleSubviewSwapTrackOrder,
  __testHandleTrackDeleteHotkey,
  __testBindTrackScrollSync,
  __testCancelSubviewPairwiseEvidence,
  __testResetMeasuredTrackViewportWidths,
  __testLoadNewSequencesTabData,
  __testResolveCurrentRouteHost,
  __testResolveAssemblyCtgContextTarget,
  __testCollectMemberChipSelectionResult,
  __testCompactFinalPathByDeletedPhasedTrack,
  __testSetSelectedPrimaryTrackCtgsHidden,
  __testResolveTrackContigClickAction,
  __testHandleTrackSubviewCandidateSelection,
  __testHandleTrackSubviewTrackSelection,
  __testRunBatchDeleteTrackCtgs,
  __testRunBatchRestoreDeletedCtgs,
  __testRestoreSelectedDeletedCtgs,
  __testRerenderBatchDeleteProgress,
  __testRerenderSubviewPanel,
  __testRenderAssemblyFinalPathCard,
  __testRenderAssemblyMainTrackSections,
  __testResolveAppendToPathFocusPatch,
  __testSyncSupportDatasetSelection,
  __testTogglePrimaryTrackCtgHidden,
  __testToggleSupportTrackCtgMirror,
  __testToggleSubviewContigFlip,
  __testSelectSubviewCandidate,
  __testSelectSubviewTrack,
  __testRemoveSubviewCandidate,
  __testRemoveSubviewTrackSelection,
  __testBuildSubviewSummaryFromTrackSelections,
  __testSwapSubviewSummaryOrder,
  __testSwapSubviewTrackDragOffsetsForSummarySwap,
  __testShouldReuseNewSequencesCache,
  renderAssemblyPage,
} from "../../assembly-page.js";

function createState(overrides = {}) {
  const {
    session: sessionOverrides = {},
    initializer: initializerOverrides = {},
    assembly: assemblyOverrides = {},
    ...legacyAssemblyOverrides
  } = overrides;
  return {
    session: {
      workspacePath: "/tmp/workspace",
      projectId: 7,
      projectName: "示例项目",
      ...sessionOverrides,
    },
    initializer: {
      datasets: [],
      existingProjects: [],
      ...initializerOverrides,
    },
    assembly: {
      loading: false,
      summary: "已加载",
      activeTab: "assembly",
      chromosomes: [
        { chrName: "Chr01", chrOrder: 1, ctgCount: 2, placedBp: 3300 },
        { chrName: "Chr02", chrOrder: 2, ctgCount: 1, placedBp: 700 },
      ],
      chrPickerOpen: false,
      selectedChrName: "Chr01",
      chrCtgs: [
        { assemblyCtgId: 5, name: "ctg-zeta", assignedChrName: "Chr01", memberCount: 3, totalLength: 800, anchorStart: 900 },
        { assemblyCtgId: 2, name: "ctg-alpha", assignedChrName: "Chr01", memberCount: 5, totalLength: 1200, anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", assignedChrName: "Chr01", memberCount: 2, totalLength: 600, anchorStart: 500 },
      ],
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
      selectedCtgId: 8,
      ctgDetail: {
        assemblyCtgId: 8,
        name: "ctg-beta",
        totalLength: 600,
        members: [],
      },
      editCandidates: {
        moveTargetCtgs: [],
        addSeqCandidates: [],
      },
      trackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      finalPathTrackView: {
        minTickUnitKb: 10000,
        maxTickCount: 10,
      },
      trackSelectedCtgIds: [],
      hiddenPrimaryCtgIds: [],
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
      selectedMemberSeqId: null,
      actionStatus: "",
      actionError: "",
      junctionLoading: false,
      junctionStatus: "",
      junctionError: "",
      junctionReport: null,
      error: "",
      referenceGenomeId: 11,
      unplacedCtgCount: 4,
      unplacedBp: 2100,
      newSequences: {
        loading: false,
        error: "",
        items: [
          {
            assemblySeqId: 7001,
            datasetName: "hifiasm",
            seqName: "ptg_mock_7001",
            seqLength: 120000,
            hidden: false,
          },
          {
            assemblySeqId: 7002,
            datasetName: "flye",
            seqName: "utg_mock_7002",
            seqLength: 83000,
            hidden: true,
          },
        ],
      },
      ...legacyAssemblyOverrides,
      ...assemblyOverrides,
    },
  };
}

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
}

function createSupportDsStorageMock(initialRawValue = null) {
  let rawValue = initialRawValue;
  const setCalls = [];
  return {
    setCalls,
    getItem() {
      return rawValue;
    },
    setItem(key, value) {
      setCalls.push({ key, value });
      rawValue = value;
    },
    removeItem() {
      rawValue = null;
    },
    readRawValue() {
      return rawValue;
    },
  };
}

function createFakeTimerApi() {
  let now = 0;
  let nextId = 1;
  const tasks = new Map();
  const runDueTasks = () => {
    while (true) {
      let nextTaskId = null;
      let nextRunAt = Number.POSITIVE_INFINITY;
      for (const [taskId, task] of tasks.entries()) {
        if (task.runAt <= now && task.runAt < nextRunAt) {
          nextTaskId = taskId;
          nextRunAt = task.runAt;
        }
      }
      if (nextTaskId === null) {
        break;
      }
      const task = tasks.get(nextTaskId);
      tasks.delete(nextTaskId);
      task.callback();
    }
  };
  return {
    setTimeout(callback, delayMs) {
      const taskId = nextId++;
      tasks.set(taskId, {
        runAt: now + Number(delayMs || 0),
        callback,
      });
      return taskId;
    },
    clearTimeout(taskId) {
      tasks.delete(taskId);
    },
    advance(ms) {
      now += Number(ms || 0);
      runDueTasks();
    },
  };
}

export {
  test,
  assert,
  readStylesheetTree,
  renderTracks,
  setSubviewAnchorStateForSummary,
  addCtgToPhasedChrTrack,
  createPhasedChrTrack,
  initializeProject,
  updateProject,
  bindAssemblyPageImpl,
  bindAssemblyPage,
  __testApplySupportDatasetSelection,
  __testBuildAssemblyContextMenuItems,
  __testCreateEditorActionRuntimeAdapters,
  __testBuildSubviewSummaryFromCandidates,
  __testBindAssemblyContextMenu,
  __testCreateActionFeedbackDismissCoordinator,
  __testCreateTrackViewportResizeCoordinator,
  __testCreateSubviewBandTooltipCoordinator,
  __testCreatePhasedChrTrack,
  __testInheritPrimaryTrackDragOffsetForPhasedItem,
  __testRemovePhasedTrackItem,
  __testGetAssemblyActionFeedbackSignature,
  __testEnterSubviewFromCandidates,
  __testEnterSubviewFromTrackSelections,
  __testHandleSubviewSwapTrackOrder,
  __testHandleTrackDeleteHotkey,
  __testBindTrackScrollSync,
  __testCancelSubviewPairwiseEvidence,
  __testResetMeasuredTrackViewportWidths,
  __testLoadNewSequencesTabData,
  __testResolveCurrentRouteHost,
  __testResolveAssemblyCtgContextTarget,
  __testCollectMemberChipSelectionResult,
  __testCompactFinalPathByDeletedPhasedTrack,
  __testSetSelectedPrimaryTrackCtgsHidden,
  __testResolveTrackContigClickAction,
  __testHandleTrackSubviewCandidateSelection,
  __testHandleTrackSubviewTrackSelection,
  __testRunBatchDeleteTrackCtgs,
  __testRunBatchRestoreDeletedCtgs,
  __testRestoreSelectedDeletedCtgs,
  __testRerenderBatchDeleteProgress,
  __testRerenderSubviewPanel,
  __testRenderAssemblyFinalPathCard,
  __testRenderAssemblyMainTrackSections,
  __testResolveAppendToPathFocusPatch,
  __testSyncSupportDatasetSelection,
  __testTogglePrimaryTrackCtgHidden,
  __testToggleSupportTrackCtgMirror,
  __testToggleSubviewContigFlip,
  __testSelectSubviewCandidate,
  __testSelectSubviewTrack,
  __testRemoveSubviewCandidate,
  __testRemoveSubviewTrackSelection,
  __testBuildSubviewSummaryFromTrackSelections,
  __testSwapSubviewSummaryOrder,
  __testSwapSubviewTrackDragOffsetsForSummarySwap,
  __testShouldReuseNewSequencesCache,
  renderAssemblyPage,
  createState,
  createStore,
  createSupportDsStorageMock,
  createFakeTimerApi,
};
