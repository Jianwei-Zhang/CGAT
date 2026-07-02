import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as renderTracks from "../render-tracks.js";
import {
  addCtgToPhasedChrTrack,
  createPhasedChrTrack,
  initializeProject,
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

test("assembly rerender host resolution falls back from detached route host to current route host", () => {
  const currentRouteHost = { id: "route-host", isConnected: true };
  const fakeDocument = {
    querySelector(selector) {
      return selector === "#route-host" ? currentRouteHost : null;
    },
    contains(node) {
      return node === currentRouteHost;
    },
  };
  const staleRouteHost = {
    id: "route-host",
    isConnected: false,
    ownerDocument: fakeDocument,
    matches(selector) {
      return selector === "#route-host";
    },
    closest(selector) {
      return selector === "#route-host" ? this : null;
    },
  };

  assert.equal(__testResolveCurrentRouteHost(staleRouteHost), currentRouteHost);
});

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

test("check new sequences tab renders API-backed items as rows", () => {
  const html = renderAssemblyPage(createState({ activeTab: "check-new-sequences" }));

  assert.match(html, /新增序列清单/);
  assert.match(html, /<th>操作<\/th>/);
  assert.match(html, /ptg_mock_7001/);
  assert.match(html, /utg_mock_7002/);
  assert.match(html, /hifiasm/);
  assert.match(html, /已显示/);
  assert.match(html, /已隐藏/);
  assert.doesNotMatch(html, /data-new-seq-action="add-seq-to-ctg"/);
  assert.match(html, /data-new-seq-action="locate-seq"/);
  assert.doesNotMatch(html, /纳入当前 contig/);
  assert.match(html, /定位到当前序列/);
  assert.doesNotMatch(html, /后续接入/);
});

test("contig list tab renders sorted Chinese columns and jump affordance", () => {
  const html = renderAssemblyPage(createState({ activeTab: "contig-list" }));

  assert.match(html, /contig 列表/);
  assert.match(html, /染色体/);
  assert.match(html, /总长度/);
  assert.match(html, /定位起点/);
  assert.match(html, /跳转/);
  assert.ok(html.indexOf("ctg-alpha") < html.indexOf("ctg-beta"));
  assert.ok(html.indexOf("ctg-beta") < html.indexOf("ctg-zeta"));
  assert.match(html, /跳转到该 contig/);
  assert.match(html, /data-assembly-ctg-id="2"/);
});

test("assembly track keeps duplicate origin ids as independent contigs", () => {
  const html = renderAssemblyPage(createState({
    chrCtgs: [
      {
        assemblyCtgId: 101,
        name: "pgt000001l@Chr01",
        originId: "pgt000001l",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 6100,
        anchorStart: 100,
      },
      {
        assemblyCtgId: 202,
        name: "pgt000001l@Chr02",
        originId: "pgt000001l",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 6000,
        anchorStart: 7000,
      },
    ],
    selectedCtgId: 202,
    ctgDetail: {
      assemblyCtgId: 202,
      name: "pgt000001l@Chr02",
      totalLength: 6000,
      members: [],
    },
  }));

  assert.match(html, /data-track-contig-id="101"/);
  assert.match(html, /data-track-contig-id="202"/);
  assert.match(html, /pgt000001l@Chr01/);
  assert.match(html, /pgt000001l@Chr02/);
});

test("stats tab shows Chinese core assembly metrics", () => {
  const html = renderAssemblyPage(createState({ activeTab: "stats" }));

  assert.match(html, /参考基因组 ID/);
  assert.match(html, /染色体数/);
  assert.match(html, /已放置 contig 数/);
  assert.match(html, /未放置 contig 数/);
  assert.match(html, /未放置总长度/);
  assert.match(html, /当前 contig/);
  assert.match(html, /4/);
});

test("assembly tab renders english labels when locale is en", () => {
  const html = renderAssemblyPage(createState({
    locale: "en",
    activeTab: "assembly",
  }));

  assert.doesNotMatch(html, /data-tab="assembly"/);
  assert.doesNotMatch(html, /data-tab="contig-list"/);
  assert.doesNotMatch(html, /data-tab="stats"/);
  assert.doesNotMatch(html, /data-tab="check-new-sequences"/);
  assert.doesNotMatch(html, /data-tab="about"/);
  assert.match(html, /Chromosome Chr01/);
  assert.doesNotMatch(html, />Download</);
  assert.match(html, />Primary Alignment View/);
  assert.match(html, /aria-label="Primary Alignment View Controls"/);
  assert.match(html, />Support Dataset</);
  assert.match(html, />Min Tick Unit \(kb\)</);
  assert.match(html, />Max Visible Count</);
  assert.match(html, /_Chr01 Primary ds track members/);
});

test("assembly page shell does not render an extra outer card frame", () => {
  const html = renderAssemblyPage(createState({ activeTab: "assembly" }));

  assert.match(html, /<section class="assembly-tabs">/);
  assert.doesNotMatch(html, /<section class="assembly-tabs card">/);
});

test("assembly page does not render member editor modal copy when locale is en", () => {
  const html = renderAssemblyPage(createState({
    locale: "en",
    assembly: {
      memberEditorModal: {
        open: true,
        ctgId: 8,
        ctgName: "ctg-beta",
        baselineCtgName: "ctg-beta",
        rows: [],
        baselineRows: [],
        deletedMemberIds: [],
        appendCtgDrafts: [],
        dirty: false,
        saving: false,
        status: "",
        error: "",
      },
    },
  }));

  assert.doesNotMatch(html, /aria-label="Contig Member Editor"/);
  assert.doesNotMatch(html, />Contig Name:</);
  assert.doesNotMatch(html, />Order</);
  assert.doesNotMatch(html, />Remove</);
  assert.doesNotMatch(html, /No member drafts yet\./);
  assert.doesNotMatch(html, />Add Member</);
  assert.doesNotMatch(html, /placeholder="Seq ID \/ Ctg ID \/ Ctg Name"/);
  assert.doesNotMatch(html, /placeholder="Start \(optional\)"/);
  assert.doesNotMatch(html, /placeholder="End \(optional\)"/);
  assert.doesNotMatch(html, />Append</);
  assert.doesNotMatch(html, /There are no changes to save\./);
  assert.doesNotMatch(html, />Cancel</);
  assert.doesNotMatch(html, />\s*Save\s*</);
});

test("assembly english view renders localized track labels and mirror empty states", () => {
  const html = renderAssemblyPage(createState({
    locale: "en",
    assembly: {
      supportDatasetId: 22,
      chrCtgs: [],
      supportChrCtgs: [],
      supportMirroredCtgs: [
        {
          datasetId: 22,
          datasetName: "flye",
          assemblyCtgId: 901,
          startBp: 10,
          endBp: 20,
          lengthBp: 11,
          laneIndex: 0,
        },
      ],
      subview: {
        summary: {
          mode: "track-pair",
          topTrack: { role: "support", source: "mirror", datasetId: 22, isMirror: true },
          bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
        },
        trackPairHiddenCtgs: [],
        trackPairSelectedCtgs: [],
      },
    },
  }));

  assert.match(html, />Primary Dataset Track</);
  assert.match(html, />flye Mirror Track</);
  assert.doesNotMatch(html, /主 ds 轨道|辅 ds 轨道|mirror 轨道/);
});

test("assembly main view renders unified single-card track container", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: null,
        supportChrCtgs: [],
      },
    }),
  );

  assert.match(html, /assembly-track-unified/);
  assert.doesNotMatch(html, /assembly-track-stack/);
  assert.match(html, /assembly-track-label-column/);
  assert.match(html, /data-focus-start="/);
  assert.match(html, /ref_chr1/);
  assert.match(html, /主 ds 轨道/);
  assert.doesNotMatch(html, /block_length/);
  assert.doesNotMatch(html, /<h4>ctg 操作<\/h4>/);
  assert.doesNotMatch(html, /<h4>sequence 操作<\/h4>/);
  assert.doesNotMatch(html, /assembly-action-feedback/);
  assert.doesNotMatch(html, /Junction 检查/);
  assert.doesNotMatch(html, /run-junction-inspection-button/);
  assert.doesNotMatch(html, /subview2-a-ctg-id/);
  assert.doesNotMatch(html, /enter-subview-2/);
});

test("assembly main view shows phased-track creation only when project enables phased assembly", () => {
  const ordinaryHtml = renderAssemblyPage(createState());
  const phasedEnabledHtml = renderAssemblyPage(createState({
    initializer: {
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
  }));

  assert.doesNotMatch(ordinaryHtml, /data-create-phased-track="1"/);
  assert.match(phasedEnabledHtml, /data-create-phased-track="1"/);
  assert.match(phasedEnabledHtml, />\+ 分型轨道</);
  assert.doesNotMatch(phasedEnabledHtml, /主分型/);
});

test("assembly main view inserts phased rows after primary and before mirror rows", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      datasets: [
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22], phasedAssemblyEnabled: true }],
    },
    assembly: {
      supportDatasetId: 22,
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "support-a", totalLength: 700, anchorStart: 100, hits: [] },
      ],
      supportMirroredCtgs: [
        {
          datasetId: 22,
          datasetName: "flye",
          assemblyCtgId: 30,
          startBp: 100,
          endBp: 799,
          lengthBp: 700,
          laneIndex: 0,
          hits: [],
        },
      ],
      phasedChrTracks: [
        {
          phasedTrackId: 1,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 101, phasedTrackId: 1, assemblyCtgId: 2, displayOrder: 1 }],
        },
        {
          phasedTrackId: 2,
          haplotypeKey: "B",
          label: "Chr01B",
          displayOrder: 2,
          items: [],
        },
      ],
    },
  }));

  const trackLabels = Array.from(
    html.matchAll(/<div class="assembly-track-label-row[^"]*"[^>]*title="([^"]+)"/g),
    (match) => match[1],
  );
  const supportIndex = trackLabels.indexOf("辅(flye)");
  const primaryIndex = trackLabels.findIndex((label) => label === "主 ds 轨道" || label.startsWith("主("));
  const phasedAIndex = trackLabels.indexOf("主分型 Chr01A");
  const phasedBIndex = trackLabels.indexOf("主分型 Chr01B");
  const mirrorIndex = trackLabels.indexOf("flye-mirror");

  assert.ok(supportIndex >= 0, "expected support row label");
  assert.ok(primaryIndex > supportIndex, "expected primary after support");
  assert.ok(phasedAIndex > primaryIndex, "expected phased A after primary");
  assert.ok(phasedBIndex > phasedAIndex, "expected phased B after A");
  assert.ok(mirrorIndex > phasedBIndex, "expected mirror after phased rows");
  assert.match(html, /class="track-ctg[^"]*is-phased-track/);
  assert.match(html, /该分型轨道暂无 contig/);
});

test("assembly main view keeps compact phased spacing without mirror rows", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
    assembly: {
      supportDatasetId: null,
      supportChrCtgs: [],
      phasedChrTracks: [
        {
          phasedTrackId: 1,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 101, phasedTrackId: 1, assemblyCtgId: 2, displayOrder: 1 }],
        },
      ],
    },
  }));

  const extractRectMetrics = (htmlText, { ctgId, role, phasedTrackItemId = null }) => {
    const phasedAttr = phasedTrackItemId
      ? `[^>]*data-track-phased-track-item-id="${phasedTrackItemId}"`
      : "";
    const match = htmlText.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${role}"${phasedAttr}[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"[^>]*data-track-rect-height="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect metrics for ${role} ctg ${ctgId}`);
    return { x: Number(match[1]), y: Number(match[2]), width: Number(match[3]), height: Number(match[4]) };
  };
  const primary = extractRectMetrics(html, { ctgId: 2, role: "primary" });
  const phased = extractRectMetrics(html, { ctgId: 2, role: "phased", phasedTrackItemId: 101 });
  const topDelta = phased.y - primary.y;

  assert.ok(Math.abs(topDelta - 24) < 0.01, `expected phased top delta 24px without mirror rows, got ${topDelta}`);
});

test("phased track ctg bars reuse the matching primary layout rect", () => {
  const html = renderAssemblyPage(createState({
    initializer: {
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
    assembly: {
      supportDatasetId: null,
      supportChrCtgs: [],
      phasedChrTracks: [
        {
          phasedTrackId: 1,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 101, phasedTrackId: 1, assemblyCtgId: 26, displayOrder: 1, orient: "+" }],
        },
      ],
      chrCtgs: [
        {
          assemblyCtgId: 26,
          name: "contig_26",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1_000_000,
          anchorStart: 1,
          orient: "-",
          refOrient: "-",
        },
        {
          assemblyCtgId: 27,
          name: "contig_27",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1_000_000,
          anchorStart: 1_000_001,
          orient: "+",
          refOrient: "+",
        },
      ],
    },
  }));

  const extractRectMetrics = (htmlText, { ctgId, role, phasedTrackItemId = null }) => {
    const phasedAttr = phasedTrackItemId
      ? `[^>]*data-track-phased-track-item-id="${phasedTrackItemId}"`
      : "";
    const match = htmlText.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${role}"${phasedAttr}[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect metrics for ${role} ctg ${ctgId}`);
    return { x: Number(match[1]), width: Number(match[2]) };
  };
  const primary = extractRectMetrics(html, { ctgId: 26, role: "primary" });
  const phased = extractRectMetrics(html, { ctgId: 26, role: "phased", phasedTrackItemId: 101 });

  assert.equal(phased.x, primary.x);
  assert.equal(phased.width, primary.width);
});

test("assembly tab keeps the main view card and subview card but removes their shared outer card wrapper", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: null,
        supportChrCtgs: [],
      },
    }),
  );

  assert.match(html, /<section class="assembly-track-content-stack">/);
  assert.match(html, /<section class="assembly-main-view">/);
  assert.doesNotMatch(html, /<section class="card assembly-main-view">/);
  assert.match(html, /<div class="assembly-track-unified assembly-track-panel">/);
  assert.match(html, /<article class="card subview-selection-panel"[^>]*>/);
  assert.match(html, /<article class="card final-path-card"/);
});

test("assembly tab renders a loading curtain over assembly content while data is loading", () => {
  const loadingHtml = renderAssemblyPage(
    createState({
      assembly: {
        loading: true,
        summary: "正在加载 chromosome...",
      },
    }),
  );
  const loadedHtml = renderAssemblyPage(createState());

  assert.match(loadingHtml, /data-assembly-loading-curtain="1"/);
  assert.doesNotMatch(loadingHtml, /data-track-contig-id="/);
  assert.doesNotMatch(loadedHtml, /data-assembly-loading-curtain="1"/);
});

test("assembly page renders an app-level confirmation dialog for destructive actions", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "delete-selected",
          message: "确认删除已框选的 2 个 contig 吗？",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="delete-selected"/);
  assert.match(html, /class="assembly-confirm-title is-danger"/);
  assert.match(html, /class="assembly-confirm-message is-danger"/);
  assert.match(html, /确认删除已框选的 2 个 contig 吗？/);
  assert.match(html, /data-assembly-confirm-action="confirm"/);
  assert.match(html, /data-assembly-confirm-action="cancel"/);
});

test("assembly page can render support ds rules unsaved-close confirmation internally", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "support-rules-close",
          message: "修改尚未保存，确定关闭并放弃修改吗？",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="support-rules-close"/);
  assert.match(html, /修改尚未保存，确定关闭并放弃修改吗？/);
  assert.match(html, /data-assembly-confirm-action="confirm"/);
  assert.match(html, /data-assembly-confirm-action="cancel"/);
});

test("assembly page renders an app-level bp threshold prompt dialog", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        confirmDialog: {
          open: true,
          id: "delete-shorter-than",
          mode: "prompt",
          message: "删除小于多少 bp 的主 ds contig？",
          defaultValue: "100000",
        },
      },
    }),
  );

  assert.match(html, /data-assembly-confirm-dialog="delete-shorter-than"/);
  assert.match(html, /删除小于多少 bp 的主 ds contig？/);
  assert.match(html, /data-assembly-confirm-input="delete-shorter-than"/);
  assert.match(html, /value="100000"/);
});

test("assembly tab renders a project-chr members card above main track with name length and member count", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
      },
    }),
  );

  const membersCardIndex = html.indexOf("assembly-members-panel");
  const mainTrackIndex = html.indexOf("assembly-track-unified");
  const ctgGridCount = (html.match(/class="[^"]*ctg-chip-grid[^"]*"/g) || []).length;

  assert.match(html, /assembly-members-panel/);
  assert.match(html, /<div class="chr-strip has-members-panel">[\s\S]*assembly-members-panel-inline is-collapsed/);
  assert.doesNotMatch(html, /<\/div>\s*<article class="card assembly-members-panel"/);
  assert.match(html, /project1_Chr01 主ds轨道成员/);
  assert.match(
    html,
    /<button[^>]*data-members-card-toggle="1"[^>]*aria-expanded="false"[^>]*>/,
  );
  assert.doesNotMatch(html, /assembly-member-chip-region/);
  assert.doesNotMatch(html, /data-track-focus-mode="start"/);
  assert.equal(ctgGridCount, 0);
  assert.ok(membersCardIndex >= 0);
  assert.ok(mainTrackIndex >= 0);
  assert.ok(membersCardIndex < mainTrackIndex);
});

test("assembly tab expands the members card body when membersCardCollapsed is false", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
      },
    }),
  );

  assert.match(html, /project1_Chr01 主ds轨道成员/);
  assert.match(
    html,
    /<button[^>]*data-members-card-toggle="1"[^>]*aria-expanded="true"[^>]*>/,
  );
  assert.match(
    html,
    /<span class="assembly-members-panel-title-inline">\s*<strong>project1_Chr01 主ds轨道成员<\/strong>\s*<button[^>]*data-reset-members-state="1"[^>]*aria-label="重置：撤销删除、撤销隐藏"/,
  );
  assert.match(html, /ctg-beta/);
  assert.match(html, /600 bp/);
  assert.doesNotMatch(html, /600 bp ;/);
  assert.match(html, /data-track-focus-mode="start"/);
  assert.equal((html.match(/class="[^"]*ctg-chip-grid[^"]*"/g) || []).length, 1);
});

test("assembly tab appends deleted members into the same members card without inline restore buttons", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
        deletedCtgs: [
          {
            deletedCtgRecordId: 9101,
            assemblyCtgId: 77,
            name: "ctg-deleted-77",
            memberCount: 2,
            totalLength: 65432,
          },
        ],
      },
    }),
  );

  assert.match(html, /已删除成员/);
  assert.match(
    html,
    /<span class="assembly-members-panel-title-inline">\s*<strong>已删除成员<\/strong>\s*<button[^>]*data-restore-all-deleted-ctgs="1"[^>]*aria-label="撤销全部删除"[^>]*title="撤销全部删除"/,
  );
  assert.match(html, /ctg-deleted-77/);
  assert.match(html, /65,432 bp/);
  assert.doesNotMatch(html, /65,432 bp ;/);
  assert.match(html, /data-deleted-ctg-record-id="9101"/);
  assert.doesNotMatch(html, /data-restore-deleted-ctg-id=/);
  assert.doesNotMatch(html, /撤销删除（Ctg77）/);
});

test("restore-all deleted members button restores every deleted record in the current chr", async () => {
  const listeners = new Map();
  const restoreButton = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "[data-restore-all-deleted-ctgs='1']" ? restoreButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        deletedCtgs: [
          { deletedCtgRecordId: 9101, assemblyCtgId: 77 },
          { deletedCtgRecordId: 9102, assemblyCtgId: 88 },
          { deletedCtgRecordId: null, assemblyCtgId: 99 },
        ],
      },
    }),
  );
  const calls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.restoreSelectedDeletedCtgs = async (_host, _store, selectedRecordIds) => {
    calls.push(selectedRecordIds);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listeners.get("click")?.({ preventDefault() {} });

  assert.deepEqual(calls, [[9101, 9102]]);
});

test("reset members button clears hidden primary contigs and restores every deleted record", async () => {
  const listeners = new Map();
  const resetButton = {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      return selector === "[data-reset-members-state='1']" ? resetButton : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [2, 8],
        deletedCtgs: [
          { deletedCtgRecordId: 9101, assemblyCtgId: 77 },
          { deletedCtgRecordId: 9102, assemblyCtgId: 88 },
        ],
      },
    }),
  );
  const restoreCalls = [];
  const persistedHiddenIds = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async (_host, currentStore) => {
    persistedHiddenIds.push(currentStore.getState().assembly.hiddenPrimaryCtgIds);
  };
  deps.restoreSelectedDeletedCtgs = async (_host, _store, selectedRecordIds) => {
    restoreCalls.push(selectedRecordIds);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listeners.get("click")?.({ preventDefault() {} });

  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, []);
  assert.deepEqual(persistedHiddenIds, [[]]);
  assert.deepEqual(restoreCalls, [[9101, 9102]]);
});

test("member cards render multi-selected style for selected primary ctgs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        trackSelectedCtgIds: [2, 8],
      },
    }),
  );

  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="2"/,
  );
  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="8"/,
  );
});

test("member cards mark primary ctgs assigned to other chromosome groups", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ptg000001l@Chr01",
            originId: "ptg000001l",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            coAssignedChrNames: ["Chr02", "Chr05"],
          },
        ],
      },
    }),
  );

  assert.doesNotMatch(html, /class="ctg-chip-coassigned-tag"/);
  assert.match(
    html,
    /title="ptg000001l@Chr01&#10;同时被分配到：Chr02, Chr05"/,
  );
  assert.match(
    html,
    /<span class="ctg-chip-name is-coassigned" title="ptg000001l@Chr01&#10;同时被分配到：Chr02, Chr05">ptg000001l<\/span>/,
  );
});

test("batch hide patches member DOM without replacing the assembly tab body", async () => {
  const tabBody = {
    innerHTML: "old tab",
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const routeHost = {
    innerHTML: "old route",
    querySelector(selector) {
      return selector === ".tab-body" ? tabBody : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const host = {
    closest(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        membersCardCollapsed: false,
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );
  const patchedHiddenIds = [];
  await __testSetSelectedPrimaryTrackCtgsHidden(host, store, [2], true, {
    async persistProjectAssemblyViewState() {},
    patchPrimaryHiddenCtgDom(_host, _store, hiddenIds) {
      patchedHiddenIds.push(hiddenIds);
      return true;
    },
  });

  assert.equal(routeHost.innerHTML, "old route");
  assert.equal(tabBody.innerHTML, "old tab");
  assert.deepEqual(patchedHiddenIds, [[2]]);
});

test("single hide refreshes final path log after local hidden patch", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathViewMode: "log",
        hiddenPrimaryCtgIds: [],
      },
    }),
  );
  const patchedHiddenIds = [];
  const refreshedHiddenIds = [];

  await __testTogglePrimaryTrackCtgHidden(host, store, 2, true, {
    async persistProjectAssemblyViewState() {},
    patchPrimaryHiddenCtgDom(_host, _store, hiddenIds) {
      patchedHiddenIds.push(hiddenIds);
      return true;
    },
    refreshFinalPathLogAfterPrimaryHiddenPatch(_host, currentStore) {
      refreshedHiddenIds.push(currentStore.getState().assembly.hiddenPrimaryCtgIds);
      return true;
    },
  });

  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, [2]);
  assert.deepEqual(patchedHiddenIds, [[2]]);
  assert.deepEqual(refreshedHiddenIds, [[2]]);
});

test("member cards normalize duplicated and noisy selected primary ctg ids", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        trackSelectedCtgIds: [8, "2", 8, 0, -1, "foo", 2.9],
      },
    }),
  );

  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="2"/,
  );
  assert.match(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="8"/,
  );
  assert.doesNotMatch(
    html,
    /class="ctg-chip [^"]*is-multi-selected[^"]*" data-assembly-ctg-id="5"/,
  );
});

test("hidden primary contig updates card tag and shifts only its own track bar up by 30px", () => {
  const normalHtml = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
        hiddenPrimaryCtgIds: [],
      },
    }),
  );
  const hiddenHtml = renderAssemblyPage(
    createState({
      session: {
        projectName: "project1",
      },
      assembly: {
        selectedChrName: "Chr01",
        membersCardCollapsed: false,
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );

  assert.match(
    hiddenHtml,
    /<button class="ctg-chip[^"]*is-hidden-contig[^"]*" data-assembly-ctg-id="2"[\s\S]*?<span class="ctg-chip-hidden-tag">\s*\(hidden\)<\/span>/,
  );
  assert.match(
    hiddenHtml,
    /<g class="track-ctg-group[^"]*is-hidden-contig[^"]*"[^>]*data-track-contig-id="2"[^>]*>/,
  );
  assert.match(hiddenHtml, /<rect\s+class="track-ctg is-hidden-contig"[\s\S]*?data-track-focus="false"/);

  const extractTrackRectY = (html, ctgId) => {
    const regex = new RegExp(
      `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-rect-y="([^"]+)"`,
    );
    const match = html.match(regex);
    assert.ok(match, `expected data-track-rect-y for ctg ${ctgId}`);
    return Number(match[1]);
  };
  const normalHiddenTargetY = extractTrackRectY(normalHtml, 2);
  const hiddenTargetY = extractTrackRectY(hiddenHtml, 2);
  const normalNeighborY = extractTrackRectY(normalHtml, 8);
  const hiddenNeighborY = extractTrackRectY(hiddenHtml, 8);

  assert.ok(
    Math.abs((normalHiddenTargetY - hiddenTargetY) - 30) < 0.01,
    `expected hidden ctg y shift to be 30px, got normal=${normalHiddenTargetY}, hidden=${hiddenTargetY}`,
  );
  assert.ok(
    Math.abs(normalNeighborY - hiddenNeighborY) < 0.01,
    `expected neighbor ctg y unchanged, got normal=${normalNeighborY}, hidden=${hiddenNeighborY}`,
  );
});

test("hidden primary contig does not render its own collinearity hit bands", () => {
  const buildState = (hiddenPrimaryCtgIds = []) =>
    createState({
      assembly: {
        hiddenPrimaryCtgIds,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [
              {
                refStart: 10_000,
                refEnd: 20_000,
                ctgStart: 5_000,
                ctgEnd: 15_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
          {
            assemblyCtgId: 8,
            name: "ctg-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 300,
            hits: [
              {
                refStart: 30_000,
                refEnd: 40_000,
                ctgStart: 25_000,
                ctgEnd: 35_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
      },
    });

  const visibleHtml = renderAssemblyPage(buildState([]));
  const hiddenHtml = renderAssemblyPage(buildState([8]));
  const countBands = (html) => (html.match(/class="track-collinearity-band"/g) || []).length;

  assert.equal(countBands(visibleHtml), 2);
  assert.equal(countBands(hiddenHtml), 1);
});

test("track drag offsets shift only the targeted primary ctg bar and its hit band", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      assembly: {
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [
              {
                refStart: 10_000,
                refEnd: 20_000,
                ctgStart: 5_000,
                ctgEnd: 15_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
          {
            assemblyCtgId: 8,
            name: "ctg-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 300,
            hits: [
              {
                refStart: 30_000,
                refEnd: 40_000,
                ctgStart: 25_000,
                ctgEnd: 35_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "primary", assemblyCtgId: 8, offsetPx: 120 }]),
  );
  const extractRectX = (html, ctgId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect x for ctg ${ctgId}`);
    return Number(match[1]);
  };
  const extractBandPoints = (html, trackRole, ctgId) => {
    const match = html.match(
      new RegExp(
        `<polygon class="track-collinearity-band(?:\\s+is-companion)?"[^>]*data-band-track-role="${trackRole}"[^>]*data-band-contig-id="${ctgId}"[^>]*points="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected band points for ${trackRole} ctg ${ctgId}`);
    return match[1];
  };

  const baseTargetRectX = extractRectX(baseHtml, 8);
  const movedTargetRectX = extractRectX(movedHtml, 8);
  const baseNeighborRectX = extractRectX(baseHtml, 2);
  const movedNeighborRectX = extractRectX(movedHtml, 2);
  assert.ok(
    Math.abs((movedTargetRectX - baseTargetRectX) - 120) < 0.01,
    `expected target rect shift 120px, got base=${baseTargetRectX}, moved=${movedTargetRectX}`,
  );
  assert.ok(
    Math.abs(movedNeighborRectX - baseNeighborRectX) < 0.01,
    `expected neighbor rect unchanged, got base=${baseNeighborRectX}, moved=${movedNeighborRectX}`,
  );

  assert.notEqual(
    extractBandPoints(baseHtml, "primary", 8),
    extractBandPoints(movedHtml, "primary", 8),
    "expected targeted primary band points to move",
  );
  assert.equal(
    extractBandPoints(baseHtml, "primary", 2),
    extractBandPoints(movedHtml, "primary", 2),
    "expected non-target primary band points to stay",
  );
});

test("track drag offsets also shift support-track ctg bars and their hit bands", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        trackDragOffsets,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
            hits: [
              {
                refStart: 12_000,
                refEnd: 22_000,
                ctgStart: 6_000,
                ctgEnd: 16_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [
              {
                refStart: 10_000,
                refEnd: 20_000,
                ctgStart: 5_000,
                ctgEnd: 15_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "support", assemblyCtgId: 30, offsetPx: 96 }]),
  );
  const extractRectXByRole = (html, trackRole, ctgId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${trackRole}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect x for ${trackRole} ctg ${ctgId}`);
    return Number(match[1]);
  };
  const extractBandPoints = (html, trackRole, ctgId) => {
    const match = html.match(
      new RegExp(
        `<polygon class="track-collinearity-band(?:\\s+is-companion)?"[^>]*data-band-track-role="${trackRole}"[^>]*data-band-contig-id="${ctgId}"[^>]*points="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected band points for ${trackRole} ctg ${ctgId}`);
    return match[1];
  };
  const baseX = extractRectXByRole(baseHtml, "support", 30);
  const movedX = extractRectXByRole(movedHtml, "support", 30);
  assert.ok(Math.abs((movedX - baseX) - 96) < 0.01, `expected support rect shift 96px, got ${movedX - baseX}`);
  assert.notEqual(extractBandPoints(baseHtml, "support", 30), extractBandPoints(movedHtml, "support", 30));
});

test("phased track drag offsets target one item instance even when assembly ctg repeats", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 8, displayOrder: 1 }],
          },
          {
            phasedTrackId: 102,
            haplotypeKey: "B",
            label: "Chr01B",
            items: [{ itemId: 9002, phasedTrackId: 102, assemblyCtgId: 8, displayOrder: 1 }],
          },
        ],
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "ctg-beta",
            assignedChrName: "Chr01",
            memberCount: 2,
            totalLength: 600_000,
            anchorStart: 500,
            hits: [],
          },
        ],
      },
    });
  const extractPhasedRectX = (html, itemId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-phased-track-item-id="${itemId}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected phased item ${itemId} rect x`);
    return Number(match[1]);
  };

  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([
      {
        trackRole: "phased",
        assemblyCtgId: 8,
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        offsetPx: 80,
      },
    ]),
  );

  assert.ok(
    Math.abs((extractPhasedRectX(movedHtml, 9001) - extractPhasedRectX(baseHtml, 9001)) - 80) < 0.01,
    "expected only phased item 9001 to move by 80px",
  );
  assert.ok(
    Math.abs(extractPhasedRectX(movedHtml, 9002) - extractPhasedRectX(baseHtml, 9002)) < 0.01,
    "expected repeated ctg instance 9002 to remain fixed",
  );
});

test("phased track drag offsets keep duplicate same-track hit bands item-scoped", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
      },
      assembly: {
        activeHitsTrackKey: "A",
        isChrPhased: true,
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 8, displayOrder: 1 },
              { itemId: 9002, phasedTrackId: 101, assemblyCtgId: 8, displayOrder: 2 },
            ],
          },
        ],
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "ctg-beta",
            assignedChrName: "Chr01",
            memberCount: 2,
            totalLength: 600_000,
            anchorStart: 500,
            hits: [
              {
                refStart: 100_000,
                refEnd: 190_000,
                ctgStart: 100_000,
                ctgEnd: 190_000,
                blockLength: 90_001,
                mapq: 60,
                strand: "+",
              },
            ],
          },
        ],
      },
    });
  const extractPhasedBandPoints = (html, itemId) => {
    const match = html.match(
      new RegExp(
        `<polygon class="track-collinearity-band is-phased-track"[^>]*data-band-track-role="phased"[^>]*data-band-contig-id="8"[^>]*data-band-phased-track-item-id="${itemId}"[^>]*points="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected phased item ${itemId} hit band`);
    return match[1];
  };

  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([
      {
        trackRole: "phased",
        assemblyCtgId: 8,
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        offsetPx: 80,
      },
    ]),
  );

  assert.notEqual(extractPhasedBandPoints(movedHtml, 9001), extractPhasedBandPoints(baseHtml, 9001));
  assert.equal(extractPhasedBandPoints(movedHtml, 9002), extractPhasedBandPoints(baseHtml, 9002));
});

test("main track hit bands use backend-projected coordinates for flipped contigs", () => {
  const buildState = (orient, hitRange) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
            orient,
            hits: [
              {
                refStart: 12_000,
                refEnd: 22_000,
                ctgStart: hitRange.ctgStart,
                ctgEnd: hitRange.ctgEnd,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [],
          },
        ],
      },
    });
  const extractBandStartX = (html) => {
    const match = html.match(
      /<polygon class="track-collinearity-band is-companion"[^>]*data-band-track-role="support"[^>]*data-band-contig-id="30"[^>]*points="([^"]+)"/,
    );
    assert.ok(match, "expected support band points");
    return Number(match[1].split(/[ ,]/)[0]);
  };

  const plusStartX = extractBandStartX(
    renderAssemblyPage(buildState("+", { ctgStart: 20_000, ctgEnd: 40_000 })),
  );
  const minusStartX = extractBandStartX(
    renderAssemblyPage(buildState("-", { ctgStart: 960_001, ctgEnd: 980_001 })),
  );

  assert.ok(
    minusStartX > plusStartX,
    `expected backend-projected flipped hit band to stay on the right, got plus=${plusStartX}, minus=${minusStartX}`,
  );
});

test("main track hit bands cross when hit strand opposes ctg display orient", () => {
  const buildState = ({ orient, strand }) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
            orient,
            hits: [
              {
                strand,
                refStart: 12_000,
                refEnd: 22_000,
                ctgStart: 20_000,
                ctgEnd: 40_000,
                blockLength: 2_000,
                mapq: 40,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
            hits: [],
          },
        ],
      },
    });
  const extractPoints = (html) => {
    const match = html.match(
      /<polygon class="track-collinearity-band is-companion"[^>]*data-band-track-role="support"[^>]*data-band-contig-id="30"[^>]*points="([^"]+)"/,
    );
    assert.ok(match, "expected support band points");
    return match[1].trim().split(/\s+/).map((point) => {
      const [x, y] = point.split(",").map(Number);
      return { x, y };
    });
  };

  const sameDirectionPoints = extractPoints(renderAssemblyPage(buildState({ orient: "-", strand: "-" })));
  const reversedPoints = extractPoints(renderAssemblyPage(buildState({ orient: "+", strand: "-" })));

  assert.ok(
    sameDirectionPoints[2].x > sameDirectionPoints[3].x,
    `expected non-reversed support band to connect ref right before ref left, got ${JSON.stringify(sameDirectionPoints)}`,
  );
  assert.ok(
    reversedPoints[2].x < reversedPoints[3].x,
    `expected reversed support band to cross by connecting ref left before ref right, got ${JSON.stringify(reversedPoints)}`,
  );
});

test("main-track drag stored in bp stays stable across minTickUnitKb zoom changes", () => {
  const draggedOffsetBp = 180;
  const buildState = ({ minTickUnitKb, trackDragOffsets = [] }) =>
    createState({
      assembly: {
        trackView: {
          minTickUnitKb,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000_000,
            anchorStart: 100,
          },
        ],
        trackDragOffsets,
      },
    });
  const renderMetrics = (html) => {
    const rectMatch = html.match(
      /data-track-contig-id="2"[^>]*data-track-role="primary"[^>]*data-track-rect-x="([^"]+)"/,
    );
    assert.ok(rectMatch, "expected primary ctg rect x");
    const viewMatch = html.match(
      /data-track-role="primary"[\s\S]*?data-track-domain-span-bp="([^"]+)"[\s\S]*?data-track-inner-width="([^"]+)"/,
    );
    assert.ok(viewMatch, "expected primary track domain/width");
    return {
      x: Number(rectMatch[1]),
      domainSpanBp: Number(viewMatch[1]),
      innerWidth: Number(viewMatch[2]),
    };
  };

  const baseFine = renderMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 1000 })));
  const movedFine = renderMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 1000,
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 2, offsetBp: draggedOffsetBp }],
      }),
    ),
  );
  const baseCoarse = renderMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 10000 })));
  const movedCoarse = renderMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 10000,
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 2, offsetBp: draggedOffsetBp }],
      }),
    ),
  );

  const shiftBpFine = ((movedFine.x - baseFine.x) * baseFine.domainSpanBp) / baseFine.innerWidth;
  const shiftBpCoarse = ((movedCoarse.x - baseCoarse.x) * baseCoarse.domainSpanBp) / baseCoarse.innerWidth;

  assert.ok(Math.abs(shiftBpFine - draggedOffsetBp) < 5, `expected fine shift ~${draggedOffsetBp}bp, got ${shiftBpFine}`);
  assert.ok(Math.abs(shiftBpCoarse - draggedOffsetBp) < 5, `expected coarse shift ~${draggedOffsetBp}bp, got ${shiftBpCoarse}`);
  assert.ok(Math.abs(shiftBpFine - shiftBpCoarse) < 5, `expected bp shift stable across zoom, got ${shiftBpFine} vs ${shiftBpCoarse}`);
});

test("main-track drag conversion uses bp-coordinate inner width instead of expanded render width", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000_000,
            anchorStart: 100,
          },
        ],
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 2, offsetPx: -600 }],
      },
    }),
  );

  const trackInnerWidthMatch = html.match(
    /data-track-role="primary"[\s\S]*?data-track-inner-width="([^"]+)"/,
  );
  assert.ok(trackInnerWidthMatch, "expected track inner width dataset");
  const trackInnerWidth = Number(trackInnerWidthMatch[1]);

  const svgWidthMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected primary track svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.ok(
    svgWidth > trackInnerWidth,
    `expected expanded render width (${svgWidth}) > bp-coordinate width (${trackInnerWidth})`,
  );
});

test("subview drag stored in bp stays stable across minTickUnitKb zoom changes", () => {
  const draggedOffsetBp = 1200;
  const buildState = ({ minTickUnitKb, subviewTrackDragOffsets = [] }) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 401,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 201,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 401,
          selectedARole: "support",
          selectedBContigId: 201,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 401, role: "support" },
            bottom: { contigId: 201, role: "primary" },
          },
        },
        subviewTrackDragOffsets,
      },
    });
  const extractSubviewMetrics = (html) => {
    const rectMatch = html.match(
      /data-subview-track-slot="bottom"[\s\S]*?data-subview-rect-x="([^"]+)"/,
    );
    assert.ok(rectMatch, "expected subview bottom rect x");
    const viewMatch = html.match(
      /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-domain-span-bp="([^"]+)"[^>]*data-subview-inner-width="([^"]+)"/,
    );
    assert.ok(viewMatch, "expected subview domain/width");
    return {
      x: Number(rectMatch[1]),
      domainSpanBp: Number(viewMatch[1]),
      innerWidth: Number(viewMatch[2]),
    };
  };

  const baseFine = extractSubviewMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 1000 })));
  const movedFine = extractSubviewMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 1000,
        subviewTrackDragOffsets: [{ slot: "bottom", contigId: 201, offsetBp: draggedOffsetBp }],
      }),
    ),
  );
  const baseCoarse = extractSubviewMetrics(renderAssemblyPage(buildState({ minTickUnitKb: 10000 })));
  const movedCoarse = extractSubviewMetrics(
    renderAssemblyPage(
      buildState({
        minTickUnitKb: 10000,
        subviewTrackDragOffsets: [{ slot: "bottom", contigId: 201, offsetBp: draggedOffsetBp }],
      }),
    ),
  );

  const shiftBpFine = ((movedFine.x - baseFine.x) * baseFine.domainSpanBp) / baseFine.innerWidth;
  const shiftBpCoarse = ((movedCoarse.x - baseCoarse.x) * baseCoarse.domainSpanBp) / baseCoarse.innerWidth;

  assert.ok(Math.abs(shiftBpFine - draggedOffsetBp) < 0.8, `expected fine shift ~${draggedOffsetBp}bp, got ${shiftBpFine}`);
  assert.ok(Math.abs(shiftBpCoarse - draggedOffsetBp) < 0.8, `expected coarse shift ~${draggedOffsetBp}bp, got ${shiftBpCoarse}`);
  assert.ok(Math.abs(shiftBpFine - shiftBpCoarse) < 0.8, `expected bp shift stable across zoom, got ${shiftBpFine} vs ${shiftBpCoarse}`);
});

test("support mirror tracks keep filled bars, share drag offset, and reserve equal tail gap", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
          { datasetId: 33, name: "wtdbg2", label: "wtdbg2" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] }],
      },
      assembly: {
        supportDatasetId: 22,
        trackDragOffsets,
        selectedCtgId: 2,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "wtdbg2",
            chrName: "Chr01",
            assemblyCtgId: 330,
            name: "support-b",
            totalLength: 900_000,
            anchorStart: 130,
            lengthBp: 900_000,
            startBp: 0,
            endBp: 899_999,
            laneIndex: 0,
          },
          {
            datasetId: 22,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 30,
            name: "support-a",
            totalLength: 1_000_000,
            anchorStart: 110,
            lengthBp: 1_000_000,
            startBp: 0,
            endBp: 999_999,
            laneIndex: 0,
          },
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "support", assemblyCtgId: 30, offsetPx: 80 }]),
  );

  assert.match(baseHtml, /flye-mirror/);
  assert.match(baseHtml, /wtdbg2-mirror/);
  assert.match(baseHtml, /class="track-ctg [^"]*is-mirror[^"]*is-companion[^"]*"/);
  assert.match(baseHtml, /data-track-is-mirror="1"/);
  assert.doesNotMatch(baseHtml, /data-band-track-role="support"[^>]*data-band-contig-id="330"/);
  const primaryLabelIndex = baseHtml.indexOf("主(hifiasm)");
  const firstMirrorLabelIndex = baseHtml.indexOf("wtdbg2-mirror");
  const secondMirrorLabelIndex = baseHtml.indexOf("flye-mirror");
  assert.ok(primaryLabelIndex >= 0 && firstMirrorLabelIndex >= 0 && secondMirrorLabelIndex >= 0);
  assert.ok(primaryLabelIndex < firstMirrorLabelIndex);
  assert.ok(firstMirrorLabelIndex < secondMirrorLabelIndex);

  const extractRectX = (html, { ctgId, isMirror }) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="support"[^>]*data-track-is-mirror="${isMirror}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected support rect x for ctg=${ctgId}, mirror=${isMirror}`);
    return Number(match[1]);
  };
  const baseMotherX = extractRectX(baseHtml, { ctgId: 30, isMirror: "0" });
  const movedMotherX = extractRectX(movedHtml, { ctgId: 30, isMirror: "0" });
  const baseMirrorX = extractRectX(baseHtml, { ctgId: 30, isMirror: "1" });
  const movedMirrorX = extractRectX(movedHtml, { ctgId: 30, isMirror: "1" });
  const extractRectY = (html, { ctgId, role, isMirror }) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="${role}"[^>]*data-track-is-mirror="${isMirror}"[^>]*data-track-rect-y="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect y for role=${role} ctg=${ctgId}, mirror=${isMirror}`);
    return Number(match[1]);
  };
  const primaryY = extractRectY(baseHtml, { ctgId: 2, role: "primary", isMirror: "0" });
  const firstMirrorY = extractRectY(baseHtml, { ctgId: 330, role: "support", isMirror: "1" });
  const secondMirrorY = extractRectY(baseHtml, { ctgId: 30, role: "support", isMirror: "1" });
  const supportY = extractRectY(baseHtml, { ctgId: 30, role: "support", isMirror: "0" });
  const extractRulerTop = (html) => {
    const match = html.match(/<line class="track-ruler-line"[^>]*y1="([^"]+)"/);
    assert.ok(match, "expected ruler line y1");
    return Number(match[1]);
  };
  const extractSvgHeight = (html) => {
    const match = html.match(/<svg class="assembly-track-svg"[^>]*height="([^"]+)"/);
    assert.ok(match, "expected assembly track svg height");
    return Number(match[1]);
  };
  const mirrorRectMatches = Array.from(
    baseHtml.matchAll(
      /<g class="track-ctg-group[^"]*"[^>]*data-track-role="support"[^>]*data-track-is-mirror="1"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-height="([^"]+)"/g,
    ),
  );
  assert.ok(mirrorRectMatches.length > 0, "expected mirror ctg rect metrics");
  const lastMirrorBottom = Math.max(...mirrorRectMatches.map((match) => Number(match[1]) + Number(match[2])));
  const topGap = supportY - extractRulerTop(baseHtml);
  const bottomGap = extractSvgHeight(baseHtml) - lastMirrorBottom;

  assert.ok(Math.abs((movedMotherX - baseMotherX) - 80) < 0.01);
  assert.ok(Math.abs((movedMirrorX - baseMirrorX) - 80) < 0.01);
  assert.ok(Math.abs((firstMirrorY - primaryY) - 24) < 0.01);
  assert.ok(Math.abs((secondMirrorY - firstMirrorY) - 24) < 0.01);
  assert.ok(Math.abs(bottomGap - topGap) < 0.01, `expected bottom gap (${bottomGap}) == top gap (${topGap})`);
});

test("mirror track label is selectable and support mother selection does not auto-select mirror label", () => {
  const baseState = {
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      supportChrCtgs: [
        {
          assemblyCtgId: 30,
          name: "support-a",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 1_000_000,
          anchorStart: 110,
        },
      ],
      supportMirroredCtgs: [
        {
          datasetId: 22,
          datasetName: "flye",
          chrName: "Chr01",
          assemblyCtgId: 30,
          name: "support-a",
          totalLength: 1_000_000,
          anchorStart: 110,
          lengthBp: 1_000_000,
          startBp: 0,
          endBp: 999_999,
          laneIndex: 0,
        },
      ],
    },
  };

  const html = renderAssemblyPage(createState(baseState));
  assert.match(
    html,
    /<div class="assembly-track-label-row[^"]*is-mirror-track[^"]*"[^>]*data-track-label-role="support"[^>]*data-track-label-selectable="1"[^>]*>[\s\S]*flye-mirror/,
  );

  const selectedHtml = renderAssemblyPage(
    createState({
      ...baseState,
      assembly: {
        ...baseState.assembly,
        subview: {
          selectedTrackARole: "support",
          selectedTrackBRole: "",
        },
      },
    }),
  );
  assert.match(
    selectedHtml,
    /<div class="assembly-track-label-row[^"]*is-companion[^"]*is-subview-track-selected[^"]*"[^>]*>[\s\S]*辅\(flye\)/,
  );
  assert.doesNotMatch(
    selectedHtml,
    /<div class="assembly-track-label-row[^"]*is-mirror-track[^"]*is-subview-track-selected[^"]*"[^>]*>[\s\S]*flye-mirror/,
  );
});

test("subview support track selection highlights only the matching dataset/source label", () => {
  const html = renderAssemblyPage(
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
          { datasetId: 33, name: "canu2", label: "canu2" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] }],
      },
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "flye-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 110,
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "canu2",
            chrName: "Chr01",
            assemblyCtgId: 1914,
            name: "canu2-a",
            totalLength: 900_000,
            anchorStart: 130,
            lengthBp: 900_000,
            startBp: 0,
            endBp: 899_999,
            laneIndex: 0,
          },
        ],
        subview: {
          selectedTrackARole: "support",
          selectedTrackBRole: "primary",
          selectedTrackBSource: "mother",
          selectedTrackBDatasetId: 22,
          selectedTrackBIsMirror: false,
        },
      },
    }),
  );

  assert.match(
    html,
    /<div class="assembly-track-label-row[^"]*is-companion[^"]*is-subview-track-selected[^"]*"[^>]*data-track-label-source="mother"[^>]*data-track-label-dataset-id="22"[^>]*>[\s\S]*辅\(flye\)/,
  );
  assert.doesNotMatch(
    html,
    /<div class="assembly-track-label-row[^"]*is-mirror-track[^"]*is-subview-track-selected[^"]*"[^>]*data-track-label-source="mirror"[^>]*data-track-label-dataset-id="33"[^>]*>[\s\S]*canu2-mirror/,
  );
});

test("reference track label is selectable for subview-track and ref members expose ref track metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 10100, chrLength: 10100 }],
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-5000",
            referenceChrName: "Chr01",
            segmentStartBp: 1,
            segmentEndBp: 5000,
            anchorStart: 1,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
        ],
      },
    }),
  );

  assert.match(
    html,
    /<div class="assembly-track-label-row[^"]*is-ref[^"]*is-track-selectable[^"]*"[^>]*data-track-label-role="ref"[^>]*data-track-label-selectable="1"[^>]*data-track-label-is-mirror="0"[^>]*>/,
  );
  assert.match(
    html,
    /data-track-contig-id="9001"[^>]*data-track-role="ref"[^>]*data-track-source-kind="ref_segment"[^>]*data-track-reference-chr-name="Chr01"[^>]*data-track-segment-start="1"[^>]*data-track-segment-end="5000"/,
  );
  assert.match(
    html,
    /<text[^>]*class="track-ctg-label track-reference-member-label[^"]*"[^>]*data-track-label-for-contig-id="9001"[^>]*data-track-label-role="ref"[^>]*data-track-label-is-mirror="0"[^>]*>ref_Chr01:1-5000 \(\+\)<\/text>/,
  );
  assert.doesNotMatch(html, /data-track-label-source="mirror"[^>]*data-track-label-role="ref"/);
});

test("subview 2-contig keeps ref bars and labels on the ref gray palette", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-5000",
            referenceChrName: "Chr01",
            segmentStartBp: 1,
            segmentEndBp: 5000,
            anchorStart: 1,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 9001,
          selectedARole: "ref",
          selectedBContigId: 2,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 9001, role: "ref", contigName: "ref_Chr01:1-5000" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
    }),
  );

  assert.match(html, /<div class="assembly-track-label-row is-ref"[^>]*>ref_Chr01:1-5000<\/div>/);
  assert.match(html, /data-subview-track-slot="top"[\s\S]*class="track-ctg subview-track-ctg is-ref"/);
  assert.match(html, /<text class="track-ctg-label[^"]*is-ref[^"]*"[^>]*data-subview-label-slot="top"/);
});

test("subview 2-contig hides labels that do not fit inside bars and keeps hover titles", () => {
  const mainLabel = "main-very-long-subview-contig-label";
  const supportLabel = `support-${"very-long-".repeat(28)}subview-contig-label`;
  const html = renderAssemblyPage(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "primary" },
            bottom: { contigId: 30, role: "support" },
          },
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: mainLabel,
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: supportLabel,
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 500_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.equal(html.includes(`data-subview-label-contig-id="2">${mainLabel} (+)</text>`), false);
  assert.equal(html.includes(`data-subview-label-contig-id="30">${supportLabel} (+)</text>`), false);
  assert.match(html, new RegExp(`<title>${mainLabel} \\|`));
  assert.match(html, new RegExp(`<title>${supportLabel} \\|`));
});

test("subview 2-contig renders anchor fragments for ref members using ref-side hits", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "-",
            hits: [
              {
                hitId: 1,
                datasetId: 11,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-alpha",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 9001,
          selectedARole: "ref",
          selectedBContigId: 2,
          selectedBRole: "primary",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 9001, role: "ref", contigName: "ref_Chr01:1001-2000" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
    }),
  );

  assert.match(
    html,
    /class="subview-anchor-line is-active"[^>]*stroke="red"/,
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-role="ref"[^>]*data-subview-fragment-contig-id="9001"[^>]*data-subview-fragment-start="1"[^>]*data-subview-fragment-end="500"[^>]*data-subview-fragment-ref-orient="-"/,
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-source-kind="ref_segment"[^>]*data-subview-fragment-reference-chr-name="Chr01"[^>]*data-subview-fragment-segment-start-bp="1001"[^>]*data-subview-fragment-segment-end-bp="2000"/,
  );
});

test("subview 2-contig projects only the selected ds hit set onto the ref member", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "+",
            hits: [
              {
                hitId: 1,
                datasetId: 11,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
              {
                hitId: 2,
                datasetId: 11,
                sourceSeqId: 99,
                strand: "+",
                queryStart: 120,
                queryEnd: 420,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            datasetId: 11,
            name: "primary-target",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          supportDsCtgLen: 0,
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedAContigId: 9001,
          selectedARole: "ref",
          selectedBContigId: 2,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 9001, role: "ref" },
            bottom: { contigId: 2, role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*"/g) || [];
  assert.equal(polygons.length, 1);
});

test("render-tracks filters ref subview members to the selected support dataset", () => {
  assert.equal(typeof renderTracks.__testBuildFilteredRefSubviewCtgs, "function");

  const result = renderTracks.__testBuildFilteredRefSubviewCtgs({
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        name: "ref_Chr01:1-5000",
        referenceChrName: "Chr01",
        segmentStartBp: 1,
        segmentEndBp: 5000,
        anchorStart: 1,
        totalLength: 5000,
        refOrient: "+",
        hits: [
          { datasetId: 22, refStart: 100, refEnd: 400, ctgStart: 1, ctgEnd: 300 },
          { datasetId: 33, refStart: 600, refEnd: 900, ctgStart: 1, ctgEnd: 300 },
        ],
      },
    ],
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
        bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
      },
    },
    primaryDatasetId: 11,
  });

  assert.deepEqual(result[0].hits.map((hit) => hit.datasetId), [22]);
});

test("render-tracks reuses cached ref segment pairing for identical inputs", () => {
  assert.equal(typeof renderTracks.__testPairRefSubviewSegmentsWithCache, "function");

  const topSegments = [
    { refStart: 100, refEnd: 400, hitKey: "top-hit", x: 0, width: 10 },
  ];
  const bottomSegments = [
    { refStart: 100, refEnd: 400, hitKey: "bottom-hit", x: 0, width: 10 },
  ];

  const first = renderTracks.__testPairRefSubviewSegmentsWithCache({
    cacheKey: "Chr01:track-pair:22:10000:0",
    topSegments,
    bottomSegments,
    trackMode: "track-pair",
  });
  const second = renderTracks.__testPairRefSubviewSegmentsWithCache({
    cacheKey: "Chr01:track-pair:22:10000:0",
    topSegments,
    bottomSegments,
    trackMode: "track-pair",
  });

  assert.equal(second, first);
});

test("subview track-pair keeps ref track bars and labels on the ref gray palette", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-500000",
            referenceChrName: "Chr01",
            segmentStartBp: 1,
            segmentEndBp: 500000,
            anchorStart: 1,
            totalLength: 500000,
            refOrient: "+",
            hits: [],
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "ref", isMirror: false },
            bottomTrack: { role: "primary", isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
        },
      },
    }),
  );

  assert.match(html, /<div class="assembly-track-label-row is-ref"[^>]*>ref_chr1<\/div>/);
  assert.match(html, /data-subview-track-slot="top"[\s\S]*class="track-ctg subview-track-ctg is-ref"/);
  assert.match(html, /<text class="track-ctg-label[^"]*is-ref[^"]*"[^>]*data-subview-label-slot="top"/);
});

test("subview track-pair hides labels that do not fit inside bars and keeps hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-very-long-trackpair-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-very-long-trackpair-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
            bottomTrack: { role: "primary", source: "mother", datasetId: null, isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(
    html,
    /data-subview-label-slot="bottom"[^>]*>primary-very-long-trackpair-label \(\+\)<\/text>/,
  );
  assert.doesNotMatch(
    html,
    /data-subview-label-slot="top"[^>]*>support-very-long-trackpair-label \(\+\)<\/text>/,
  );
  assert.match(html, /<title>primary-very-long-trackpair-label \|/);
  assert.match(html, /<title>support-very-long-trackpair-label \|/);
});

test("subview track-pair renders anchor fragments for ref members using ref-side hits", () => {
  const stablePairHitKey = "pair:9001:hit-1:2:hit-1";
  const html = renderAssemblyPage(
    createState({
      assembly: {
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "-",
            hits: [
              {
                hitId: 1,
                datasetId: 11,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-alpha",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1200,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "ref",
          selectedTrackBRole: "primary",
          activeAnchors: [{ hitKey: stablePairHitKey, edge: "left" }],
          summary: {
            mode: "track-pair",
            topTrack: { role: "ref", isMirror: false },
            bottomTrack: { role: "primary", isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
        },
      },
    }),
  );

  assert.match(
    html,
    new RegExp(`class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="${stablePairHitKey}"[^>]*data-subview-anchor-edge="left"`),
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-role="ref"[^>]*data-subview-fragment-contig-id="9001"[^>]*data-subview-fragment-start="1"[^>]*data-subview-fragment-end="500"/,
  );
  assert.match(
    html,
    /data-subview-fragment-key="9001:1-500"[^>]*data-subview-fragment-source-kind="ref_segment"[^>]*data-subview-fragment-reference-chr-name="Chr01"/,
  );
});

test("subview track-pair ref projection keeps only support members visible in the main track", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 10000,
          mapq: 0,
        },
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            datasetId: 22,
            name: "support-hidden",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
          {
            assemblyCtgId: 31,
            datasetId: 22,
            name: "support-visible",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
            hits: [
              { refStart: 1501, refEnd: 1800, ctgStart: 101, ctgEnd: 400, blockLength: 300, mapq: 60 },
            ],
          },
        ],
        refTrackMembers: [
          {
            assemblyCtgId: 9001,
            sourceKind: "ref_segment",
            name: "ref_Chr01:1001-2000",
            referenceChrId: 1,
            referenceChrName: "Chr01",
            segmentStartBp: 1001,
            segmentEndBp: 2000,
            anchorStart: 1001,
            totalLength: 1000,
            refOrient: "+",
            hits: [
              {
                hitId: 1,
                datasetId: 22,
                sourceSeqId: 1,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
              {
                hitId: 2,
                datasetId: 22,
                sourceSeqId: 2,
                strand: "+",
                queryStart: 101,
                queryEnd: 400,
                refStart: 1501,
                refEnd: 1800,
                matchLength: 300,
                blockLength: 300,
                mapq: 60,
                ctgStart: 501,
                ctgEnd: 800,
              },
            ],
          },
        ],
        subviewTrackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackSelections: [
            { role: "ref", source: "mother", datasetId: null, isMirror: false },
            { role: "support", source: "mother", datasetId: 22, isMirror: false },
          ],
          selectedTrackARole: "ref",
          selectedTrackBRole: "support",
          selectedTrackBSource: "mother",
          selectedTrackBDatasetId: 22,
          selectedTrackBIsMirror: false,
          summary: {
            mode: "track-pair",
            topTrack: { role: "ref", source: "mother", datasetId: null, isMirror: false },
            bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
          },
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*"/g) || [];
  assert.equal(polygons.length, 1);
  assert.match(html, /support-visible/);
  assert.doesNotMatch(html, /support-hidden/);
});

test("hidden primary ctg bar still applies drag offsets", () => {
  const baseHtml = renderAssemblyPage(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [8],
        trackDragOffsets: [],
      },
    }),
  );
  const movedHtml = renderAssemblyPage(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [8],
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 8, offsetPx: 80 }],
      },
    }),
  );
  const extractRectX = (html, ctgId) => {
    const match = html.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*is-hidden-contig[^"]*"[^>]*data-track-contig-id="${ctgId}"[\\s\\S]*?<rect[\\s\\S]*?x="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected hidden rect x for ctg ${ctgId}`);
    return Number(match[1]);
  };
  const baseX = extractRectX(baseHtml, 8);
  const movedX = extractRectX(movedHtml, 8);
  assert.ok(Math.abs((movedX - baseX) - 80) < 0.01, `expected hidden rect shift 80px, got ${movedX - baseX}`);
});

test("within the same track lane, shorter overlapping ctg bars render above longer bars", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 200_000,
            anchorStart: 2_500_000,
          },
        ],
        trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 8, offsetPx: -520 }],
      },
    }),
  );

  const extractRectMetrics = (markup, ctgId) => {
    const match = markup.match(
      new RegExp(
        `<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="${ctgId}"[^>]*data-track-role="primary"[^>]*data-track-rect-x="([^"]+)"[^>]*data-track-rect-y="([^"]+)"[^>]*data-track-rect-width="([^"]+)"`,
      ),
    );
    assert.ok(match, `expected rect metrics for primary ctg ${ctgId}`);
    return {
      x: Number(match[1]),
      y: Number(match[2]),
      width: Number(match[3]),
    };
  };

  const longRect = extractRectMetrics(html, 2);
  const shortRect = extractRectMetrics(html, 8);
  assert.equal(shortRect.y, longRect.y, "expected both ctgs on the same lane");
  assert.ok(
    shortRect.x < longRect.x + longRect.width && shortRect.x + shortRect.width > longRect.x,
    "expected dragged short ctg to overlap long ctg",
  );

  const longMarkupIndex = html.indexOf(`data-track-contig-id="2" data-track-role="primary"`);
  const shortMarkupIndex = html.indexOf(`data-track-contig-id="8" data-track-role="primary"`);
  assert.ok(longMarkupIndex >= 0 && shortMarkupIndex >= 0, "expected both primary ctg groups in svg");
  assert.ok(shortMarkupIndex > longMarkupIndex, "expected shorter ctg to render after longer ctg (on top)");
});

test("negative drag offsets extend left scrollable range in main track view", () => {
  const buildState = (trackDragOffsets = []) =>
    createState({
      assembly: {
        trackDragOffsets,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 300,
          },
        ],
      },
    });
  const baseHtml = renderAssemblyPage(buildState([]));
  const movedHtml = renderAssemblyPage(
    buildState([{ trackRole: "primary", assemblyCtgId: 2, offsetPx: -220 }]),
  );

  const parseMainTrackWidth = (html) => {
    const svgMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
    assert.ok(svgMatch, "expected main track svg width");
    return Number(svgMatch[1]);
  };
  const parsePrimaryViewboxMinX = (html) => {
    const match = html.match(
      /class="assembly-track-scroll"[\s\S]*?data-track-role="primary"[\s\S]*?data-track-viewbox-min-x="([^"]+)"/,
    );
    assert.ok(match, "expected main track viewBox min-x");
    return Number(match[1]);
  };

  const baseWidth = parseMainTrackWidth(baseHtml);
  const movedWidth = parseMainTrackWidth(movedHtml);
  const movedViewboxMinX = parsePrimaryViewboxMinX(movedHtml);

  assert.ok(movedViewboxMinX < 0, `expected negative viewBox min-x, got ${movedViewboxMinX}`);
  assert.ok(movedWidth > baseWidth, `expected moved width (${movedWidth}) > base width (${baseWidth})`);
  assert.match(
    movedHtml,
    new RegExp(`<svg class="assembly-track-svg"[^>]*viewBox="${movedViewboxMinX} 0 ${movedWidth} `),
  );
});

test("assembly main view renders v1-style collapsible menus with selectable presets and numeric track inputs", () => {
  const html = renderAssemblyPage(createState());

  assert.doesNotMatch(html, /assembly-v1-tool-strip/);
  assert.match(html, /assembly-track-inline-controls/);
  assert.doesNotMatch(html, /data-tool-menu="you-can"/);
  assert.doesNotMatch(html, /data-tool-menu="about-chr"/);
  assert.doesNotMatch(html, /搜索 contig 名称或 ID/);
  assert.doesNotMatch(html, /打开 \/ 收起染色体列表/);
  assert.doesNotMatch(html, /查看当前 contig/);
  assert.doesNotMatch(html, /id="assembly-print-view-button"/);
  assert.doesNotMatch(html, /id="assembly-export-chr-ctg-pmolecule-button"/);
  assert.doesNotMatch(html, /id="assembly-export-agp-button"/);
  assert.doesNotMatch(html, /Controls \/ 控件/);
  assert.match(html, /辅ds_ctg_len\(bp\)/);
  assert.match(html, /最小刻度单位\(kb\)/);
  assert.match(html, /最多可展示数/);
  assert.match(html, /Alignment Length\(bp\)/);
  assert.match(html, /MAPQ/);
  assert.ok(html.indexOf("辅 ds") < html.indexOf("辅ds_ctg_len"));
  assert.ok(html.indexOf("辅ds_ctg_len") < html.indexOf("最小刻度单位"));
  assert.ok(html.indexOf("最小刻度单位") < html.indexOf("最多可展示数"));
  assert.ok(html.indexOf("最多可展示数") < html.indexOf("Alignment Length"));
  assert.ok(html.indexOf("Alignment Length") < html.indexOf("MAPQ"));

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="supportDsCtgLen">/,
  );
  assert.match(
    html,
    /<input\s+id="assembly-track-support-ds-ctg-len"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="0"\s+autocomplete="off"[^>]*>/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开辅ds_ctg_len\(bp\)候选值" aria-expanded="false" aria-controls="assembly-track-support-ds-ctg-len-menu">/,
  );
  assert.match(html, /<div id="assembly-track-support-ds-ctg-len-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="0"/);
  assert.match(html, /data-track-combo-value="1000"/);
  assert.match(html, /data-track-combo-value="10000"/);
  assert.match(html, /data-track-combo-value="100000"/);

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="minTickUnitKb">/,
  );
  assert.match(
    html,
    /<input\s+id="assembly-track-min-tick-unit-kb"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="10000"\s+autocomplete="off"[^>]*>/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开最小刻度单位\(kb\)候选值" aria-expanded="false" aria-controls="assembly-track-min-tick-unit-kb-menu">/,
  );
  assert.match(html, /<span class="assembly-track-control-marker" aria-hidden="true">▾<\/span>/);
  assert.match(html, /<div id="assembly-track-min-tick-unit-kb-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="250"/);
  assert.match(html, /data-track-combo-value="500"/);
  assert.match(html, /data-track-combo-value="750"/);
  assert.match(html, /data-track-combo-value="1000"/);
  assert.match(html, /data-track-combo-value="10000"/);

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="maxTickCount">/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开最多可展示数候选值" aria-expanded="false" aria-controls="assembly-track-max-tick-count-menu">/,
  );
  assert.match(html, /<div id="assembly-track-max-tick-count-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="5"/);
  assert.match(html, /data-track-combo-value="10"/);
  assert.match(html, /data-track-combo-value="15"/);
  assert.match(html, /data-track-combo-value="20"/);

  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="alignmentLength">/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开Alignment Length\(bp\)候选值" aria-expanded="false" aria-controls="assembly-track-alignment-length-menu">/,
  );
  assert.match(html, /<div id="assembly-track-alignment-length-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(html, /data-track-combo-value="1000"/);
  assert.match(html, /data-track-combo-value="10000"/);
  assert.match(html, /data-track-combo-value="100000"/);
  assert.match(
    html,
    /<div class="assembly-track-combo" data-track-combo-field="mapq">/,
  );
  assert.match(
    html,
    /<button type="button" class="assembly-track-combo-toggle" data-track-combo-toggle aria-label="打开MAPQ候选值" aria-expanded="false" aria-controls="assembly-track-mapq-menu">/,
  );
  assert.match(html, /<div id="assembly-track-mapq-menu" class="assembly-track-combo-menu is-hidden" role="listbox">/);
  assert.match(
    html,
    /<input\s+id="assembly-track-mapq"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="0"\s+autocomplete="off"[^>]*>/,
  );
  assert.match(html, /data-track-combo-value="0"/);
  assert.match(html, /data-track-combo-value="30"/);
  assert.match(html, /data-track-combo-value="60"/);
  assert.match(html, /data-track-combo-value="90"/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-min-tick-unit-kb-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-max-tick-count-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-alignment-length-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-mapq-options">/);
  assert.doesNotMatch(html, /<datalist id="assembly-track-support-ds-ctg-len-options">/);
});

test("support ds ctg len rules dialog renders close in header and actions in footer", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDsCtgLenRulesDialogOpen: true,
        supportDsCtgLenRulesByChr: {
          Chr01: [
            { startBp: 1, endBp: 5_000_000, supportDsCtgLen: 100000 },
            { startBp: 5_000_001, endBp: 10_000_000, supportDsCtgLen: 0 },
          ],
        },
        trackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
          supportDsCtgLen: 0,
        },
      },
    }),
  );
  const headMatch = html.match(
    /<div class="assembly-support-ds-len-rules-head">([\s\S]*?)<\/div>\s*<div class="assembly-support-ds-len-rules-body">/,
  );
  assert.ok(headMatch, "expected dialog header");
  assert.match(headMatch[1], /data-support-ds-ctg-len-rules-close="1"/);
  assert.doesNotMatch(headMatch[1], /data-support-ds-ctg-len-rules-reset="1"/);
  assert.doesNotMatch(headMatch[1], /data-support-ds-ctg-len-rules-save="1"/);

  const footMatch = html.match(
    /<div class="assembly-support-ds-len-rules-foot">([\s\S]*?)<\/div>\s*<\/div>\s*<\/article>/,
  );
  assert.ok(footMatch, "expected dialog footer");
  assert.match(footMatch[1], /data-support-ds-ctg-len-rules-add="1"/);
  assert.match(footMatch[1], /data-support-ds-ctg-len-rules-reset="1"/);
  assert.match(footMatch[1], /data-support-ds-ctg-len-rules-save="1"/);
});

test("track combo styles keep dropdown menu unclipped", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-track-combo\s*\{[^}]*overflow:\s*visible;/);
  assert.doesNotMatch(css, /\.assembly-track-combo\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-select-shell\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-fixed-select\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-fixed-select\s*\{[^}]*text-overflow:\s*ellipsis;/);
  assert.match(css, /\.assembly-track-fixed-select\s*\{[^}]*white-space:\s*nowrap;/);
});

test("final path card body css keeps a shared bottom padding for graph and table modes", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-body\s*\{[\s\S]*padding-bottom:\s*\d+px;/);
});

test("assembly card spacing css uses one shared stack gap instead of a standalone final-path margin", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-track-content-stack\s*\{[^}]*display:\s*grid;/);
  assert.match(css, /\.assembly-track-content-stack\s*\{[^}]*gap:\s*8px;/);
  assert.doesNotMatch(css, /\.final-path-card\s*\{[^}]*margin-top:\s*\d+px;/);
});

test("main track panel css uses the same horizontal inset rhythm as subview and final path cards", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.card\s*\{[^}]*padding:\s*10px;/);
  assert.match(css, /\.assembly-track-panel\s*\{[^}]*padding:\s*10px;/);
  assert.match(css, /\.assembly-track-panel\s*\{[^}]*gap:\s*8px;/);
  assert.doesNotMatch(css, /\.assembly-track-panel\s*\{[^}]*padding:\s*6px;/);
});

test("final path table body css keeps a graph-like minimum height without vertical centering", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-table-body\s*\{[^}]*min-height:\s*\d+px;/);
  assert.doesNotMatch(css, /\.final-path-card-table-body\s*\{[^}]*align-items:\s*center;/);
  assert.doesNotMatch(css, /\.final-path-card-table-body\s*\{[^}]*place-items:\s*center;/);
});

test("final path index header css centers the # label over the index column", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-list-head\s*>\s*:first-child\s*\{[\s\S]*justify-content:\s*center;/);
  assert.match(css, /\.final-path-card-list-head\s*>\s*:first-child\s*\{[\s\S]*text-align:\s*center;/);
});

test("final path table css uses responsive grids instead of the old fixed 1550px layout", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(css, /\.final-path-card-list-head\s*\{[^}]*min-width:\s*1550px;/);
  assert.doesNotMatch(css, /\.final-path-card-list\s*\{[^}]*min-width:\s*1550px;/);
  assert.doesNotMatch(css, /\.final-path-card-list-head\s*\{[^}]*grid-template-columns:\s*78px minmax\(1450px,\s*1fr\);/);
  assert.doesNotMatch(css, /\.final-path-sort-row\s*\{[^}]*grid-template-columns:\s*78px minmax\(1450px,\s*1fr\);/);
  assert.match(css, /\.final-path-card-list-head,\s*\.final-path-sort-row\s*\{[\s\S]*grid-template-columns:\s*64px minmax\(0,\s*1fr\);/);
  assert.match(css, /\.final-path-card-list-head-card,\s*\.final-path-sort-card-grid\s*\{[\s\S]*grid-template-columns:\s*var\(--final-path-table-columns\);/);
});

test("final path header css places the mode toggle after title and highlights the active mode", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.final-path-card-head\s*\{[^}]*justify-content:\s*space-between;/);
  assert.match(css, /\.final-path-card-title-row\s*\{[^}]*display:\s*inline-flex;/);
  assert.match(css, /\.final-path-card-head-controls\s*\{[^}]*justify-content:\s*flex-end;/);
  assert.match(css, /\.final-path-card-toggle-button\.is-active\s*\{[^}]*font-weight:\s*700;/);
  assert.match(css, /\.final-path-export\s*\{[^}]*position:\s*relative;/);
  assert.match(css, /\.final-path-export-menu\s*\{[^}]*position:\s*absolute;/);
});

test("track tick label css does not force middle anchor", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(css, /\.track-tick-label\s*\{[^}]*text-anchor:\s*middle;/);
});

test("subview candidate row uses left flow for inline placement next to guide text", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.subview-candidate-row\s*\{[^}]*justify-content:\s*flex-start;/);
});

test("subview selection panel exposes a stable local refresh anchor", () => {
  const html = renderAssemblyPage(createState());

  assert.match(html, /<article class="card subview-selection-panel" data-subview-panel="1">/);
});

test("subview band tooltip keeps each contig interval on its own unwrapped line", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.subview-band-tooltip\s*\{[^}]*white-space:\s*pre;/);
  assert.doesNotMatch(css, /\.subview-band-tooltip\s*\{[^}]*white-space:\s*pre-line;/);
});

test("subview hit bands follow top-track color", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.subview-track-svg\s+\.track-collinearity-band\s*\{[^}]*fill:\s*rgba\(97,\s*129,\s*170,\s*0\.24\);[^}]*stroke:\s*rgba\(97,\s*129,\s*170,\s*0\.38\);/,
  );
  assert.match(
    css,
    /\.subview-track-svg\s+\.track-collinearity-band\.is-companion\s*\{[^}]*fill:\s*rgba\(154,\s*126,\s*78,\s*0\.22\);[^}]*stroke:\s*rgba\(154,\s*126,\s*78,\s*0\.34\);/,
  );
});

test("transparent hit-band proxies are hidden only after canvas is ready", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.assembly-track-scroll\.is-track-band-canvas-ready\s+\.subview-track-svg\s+\.track-collinearity-band\[data-track-band-proxy="1"\]\s*\{[^}]*fill:\s*transparent;[^}]*stroke:\s*transparent;/,
  );
  assert.doesNotMatch(
    css,
    /(^|\n)\.subview-track-svg\s+\.track-collinearity-band\[data-track-band-proxy="1"\]\s*\{[^}]*fill:\s*transparent;/,
  );
});

test("hidden contig css uses dashed chips, blue hidden tag, and outline-only bars", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.ctg-chip\.is-hidden-contig\s*\{[\s\S]*border-style:\s*dashed;/);
  assert.match(css, /\.ctg-chip-hidden-tag\s*\{[\s\S]*color:\s*#2e567f;/);
  assert.match(css, /\.track-ctg\.is-hidden-contig,\s*\.track-ctg\.is-hidden-contig\.is-active,\s*\.track-ctg\.is-hidden-contig\.is-multi-selected\s*\{[\s\S]*fill:\s*none;/);
  assert.match(
    css,
    /\.track-ctg\.is-hidden-contig,\s*\.track-ctg\.is-hidden-contig\.is-active,\s*\.track-ctg\.is-hidden-contig\.is-multi-selected\s*\{[\s\S]*pointer-events:\s*all;/,
  );
});

test("mirror contig css preserves fill color while keeping interaction enabled", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.track-ctg\.is-mirror,\s*\.track-ctg\.is-mirror\.is-active,\s*\.track-ctg\.is-mirror\.is-multi-selected,\s*\.track-ctg\.is-mirror\.is-subview-selected\s*\{[\s\S]*pointer-events:\s*all;/,
  );
  assert.doesNotMatch(
    css,
    /\.track-ctg\.is-mirror,\s*\.track-ctg\.is-mirror\.is-active,\s*\.track-ctg\.is-mirror\.is-multi-selected,\s*\.track-ctg\.is-mirror\.is-subview-selected\s*\{[\s\S]*fill:\s*none;/,
  );
  assert.doesNotMatch(css, /\.track-ctg\.is-mirror\.is-companion/);
});

test("mirror contig labels do not force bold font weight", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.doesNotMatch(css, /\.track-ctg-label\.is-mirror\s*\{[\s\S]*font-weight:/);
});

test("track labels stay on one line and truncate overflow", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-track-label-row\s*\{[^}]*white-space:\s*nowrap;/);
  assert.match(css, /\.assembly-track-label-row\s*\{[^}]*overflow:\s*hidden;/);
  assert.match(css, /\.assembly-track-label-row\s*\{[^}]*text-overflow:\s*ellipsis;/);
  assert.match(css, /\.assembly-track-label-row\s*>\s*span\s*\{[^}]*white-space:\s*nowrap;/);
  assert.match(css, /\.assembly-track-label-row\s*>\s*span\s*\{[^}]*text-overflow:\s*ellipsis;/);
});

test("assembly main view shows 3-track labels when support ds is available", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /辅\(flye\)/);
  assert.match(html, /ref_chr1/);
  assert.match(html, /主\(hifiasm\)/);
  assert.match(html, /Ctrl\/Cmd 选中任意两个ctg进入subview-ctg/);
  assert.doesNotMatch(html, /Junction 检查/);
  assert.doesNotMatch(html, /subview2-a-ctg-id/);
  assert.doesNotMatch(html, /enter-subview-2/);
});

test("main primary track label is selectable for track-level context menu actions", () => {
  const html = renderAssemblyPage(
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
    }),
  );

  assert.match(
    html,
    /class="assembly-track-label-row[^"]*is-track-selectable[^"]*"[^>]*data-track-label-role="primary"[^>]*data-track-label-selectable="1"[^>]*title="主\(hifiasm\)"[^>]*>\s*<span>主\(hifiasm\)<\/span>/,
  );
});

test("main assembly ctg labels expose runtime lookup metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-alpha", refOrient: "-", assignedChrName: "Chr01", memberCount: 1, totalLength: 10_000_000, anchorStart: 100 },
        ],
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", refOrient: "+", assignedChrName: "Chr01", memberCount: 1, totalLength: 10_000_000, anchorStart: 150 },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /<text class="track-ctg-label[^"]*"[^>]*data-track-label-for-contig-id="2"[^>]*data-track-label-role="primary"[^>]*>ctg-alpha \(-\)<\/text>/);
  assert.match(html, /<text class="track-ctg-label[^"]*"[^>]*data-track-label-for-contig-id="30"[^>]*data-track-label-role="support"[^>]*>support-ctg \(\+\)<\/text>/);
});

test("assembly rendering keeps a fixed 20px visual gap between adjacent support-track contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 200,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const matches = [...html.matchAll(/<rect\s+class="track-ctg is-companion"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/g)];
  assert.ok(matches.length >= 2, "expected at least two support-track contig bars");
  const firstX = Number(matches[0][1]);
  const firstWidth = Number(matches[0][2]);
  const secondX = Number(matches[1][1]);
  const visibleGapPx = secondX - (firstX + firstWidth);
  assert.ok(visibleGapPx >= 19.9, `expected visible gap >= 20px, got ${visibleGapPx}`);
});

test("assembly rendering force-separates dense short tail support-track contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 25_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 31,
            name: "support-tail-1",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 200,
          },
          {
            assemblyCtgId: 32,
            name: "support-tail-2",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 300,
          },
          {
            assemblyCtgId: 33,
            name: "support-tail-3",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 400,
          },
          {
            assemblyCtgId: 34,
            name: "support-tail-4",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 500,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const matches = [...html.matchAll(/<rect\s+class="track-ctg is-companion"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/g)];
  assert.ok(matches.length >= 5, "expected dense support-track bars to be rendered");

  const rects = matches.map((match) => ({
    x: Number(match[1]),
    width: Number(match[2]),
  }));
  for (let index = 1; index < rects.length; index += 1) {
    const previous = rects[index - 1];
    const current = rects[index];
    const visibleGapPx = current.x - (previous.x + previous.width);
    assert.ok(visibleGapPx >= 19.9, `expected visible gap >= 20px, got ${visibleGapPx}`);
  }
});

test("assembly rendering does not clip right-side dense primary contigs after forced gap adjustment", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 25_000_000,
            anchorStart: 10,
          },
          {
            assemblyCtgId: 6,
            name: "ctg-tail-1",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 20,
          },
          {
            assemblyCtgId: 7,
            name: "ctg-tail-2",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 30,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-tail-3",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 40,
          },
        ],
      },
    }),
  );

  const svgMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgMatch, "expected rendered assembly track svg");
  const svgWidth = Number(svgMatch[1]);

  const primaryMatches = [...html.matchAll(/<rect\s+class="track-ctg(?![^"]*is-companion)[^"]*"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/g)];
  assert.ok(primaryMatches.length >= 4, "expected dense primary-track contig bars");

  const maxRight = Math.max(...primaryMatches.map((match) => Number(match[1]) + Number(match[2])));
  assert.ok(
    maxRight <= svgWidth + 0.01,
    `expected right-most primary contig to be fully visible within svg width, got ${maxRight} > ${svgWidth}`,
  );
});

test("main track does not render outside tilted labels for narrow contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "main-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*is-outside/);
  assert.match(html, /<title>main-very-long-contig-label \|/);
  assert.match(html, /<title>support-very-long-contig-label \|/);
});

test("track contig labels use assembly orient before reference orient", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "primary-flipped",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 10,
            orient: "-",
            refOrient: "+",
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-flipped",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000_000,
            anchorStart: 10,
            orient: "-",
            refOrient: "+",
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, />primary-flipped \(-\)<\/text>/);
  assert.match(html, />support-flipped \(-\)<\/text>/);
  assert.doesNotMatch(html, />primary-flipped \(\+\)<\/text>/);
  assert.doesNotMatch(html, />support-flipped \(\+\)<\/text>/);
});

test("assembly visible ctg labels strip chr suffix while hover titles keep full names", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        membersCardCollapsed: false,
        supportDatasetId: 22,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ptg000009l@Chr22",
            refOrient: "+",
            assignedChrName: "Chr22",
            memberCount: 1,
            totalLength: 500_000,
            anchorStart: 100,
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "Ctg1617@Chr22",
            refOrient: "-",
            assignedChrName: "Chr22",
            memberCount: 1,
            totalLength: 500_000,
            anchorStart: 320,
          },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "Ctg1617@Chr22" },
            bottom: { contigId: 2, role: "primary", contigName: "ptg000009l@Chr22" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, />ptg000009l \(\+\)<\/text>/);
  assert.match(html, />Ctg1617 \(-\)<\/text>/);
  assert.match(html, /<strong>ptg000009l<\/strong>/);
  assert.match(html, /title="ptg000009l@Chr22"/);
  assert.match(html, /class="subview-candidate-badge" title="ptg000009l@Chr22"><strong>A<\/strong>ptg000009l/);
  assert.match(html, /class="subview-candidate-badge" title="Ctg1617@Chr22"><strong>B<\/strong>Ctg1617/);
  assert.match(html, /<title>ptg000009l@Chr22 \| start=/);
  assert.match(html, /<title>Ctg1617@Chr22 \| start=/);
  assert.doesNotMatch(html, />ptg000009l@Chr22 \(\+\)<\/text>/);
  assert.doesNotMatch(html, />Ctg1617@Chr22 \(-\)<\/text>/);
  assert.doesNotMatch(html, /<strong>ptg000009l@Chr22<\/strong>/);
  assert.doesNotMatch(html, /<strong>A<\/strong>ptg000009l@Chr22/);
});

test("main track hides labels that do not fit inside bars and keeps hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "main-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(html, />main-very-long-contig-label \(\+\)<\/text>/);
  assert.doesNotMatch(html, />support-very-long-contig-label \(\+\)<\/text>/);
  assert.match(html, /<title>main-very-long-contig-label \|/);
  assert.match(html, /<title>support-very-long-contig-label \|/);
});

test("main track keeps narrow contig bars visible without outside labels", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 501,
            name: "main-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 601,
            name: "support-very-long-contig-label",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 10,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const primaryRectMatch = html.match(
    /<rect\s+class="track-ctg(?![^"]*is-companion)[^"]*"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"[\s\S]*?<\/rect>/,
  );
  assert.ok(primaryRectMatch, "expected a primary-track contig bar");

  const companionRectMatch = html.match(
    /<rect\s+class="track-ctg is-companion[^"]*"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"[\s\S]*?<\/rect>/,
  );
  assert.ok(companionRectMatch, "expected a companion-track contig bar");
  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*is-outside/);
  assert.match(html, /<title>main-very-long-contig-label \|/);
  assert.match(html, /<title>support-very-long-contig-label \|/);
});

test("main track hides right-edge overflow labels instead of widening the svg", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 25_000_000,
            anchorStart: 10,
          },
          {
            assemblyCtgId: 6,
            name: "ctg53",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 20,
          },
          {
            assemblyCtgId: 7,
            name: "ctg502",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 30,
          },
          {
            assemblyCtgId: 8,
            name: "ctg497",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 40,
          },
          {
            assemblyCtgId: 9,
            name: "ctg50",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 50,
          },
          {
            assemblyCtgId: 10,
            name: "ctg49",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1_000,
            anchorStart: 60,
          },
        ],
      },
    }),
  );

  const svgMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgMatch, "expected rendered assembly track svg");

  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*is-outside/);
  assert.match(html, /<title>ctg53 \|/);
  assert.match(html, /<title>ctg497 \|/);
});

test("max-scale main track keeps svg width equal to inner width even with a right-edge overflow label", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [
          { chrName: "Chr01", chrOrder: 1, chrLength: 30_000_000, ctgCount: 2, placedBp: 28_100_000 },
        ],
        trackView: {
          minTickUnitKb: 10_000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 28_000_000,
            anchorStart: 1,
          },
          {
            assemblyCtgId: 6,
            name: "right-edge-overflow-label-very-very-very-long-contig-name",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 100_000,
            anchorStart: 29_000_000,
          },
        ],
      },
    }),
  );

  const innerWidthMatch = html.match(
    /data-track-role="primary"[\s\S]*?data-track-inner-width="([^"]+)"/,
  );
  assert.ok(innerWidthMatch, "expected primary track inner width");
  const innerWidth = Number(innerWidthMatch[1]);

  const svgWidthMatch = html.match(/<svg class="assembly-track-svg"[^>]*width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected primary track svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.equal(
    svgWidth,
    innerWidth,
    `expected max-scale primary svg width ${svgWidth} to match inner width ${innerWidth}`,
  );
});

test("companion collinearity band ctg edge stays within the rendered ctg bar after visual gap adjustment", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
            hits: [],
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 10_000_000,
                refStart: 1000,
                refEnd: 10_001_000,
                blockLength: 10_000_000,
              },
            ],
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 200,
            hits: [],
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const supportRectMatch = html.match(/<rect\s+class="track-ctg is-companion"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/);
  assert.ok(supportRectMatch, "expected first companion ctg bar");
  const supportRectX = Number(supportRectMatch[1]);
  const supportRectRight = supportRectX + Number(supportRectMatch[2]);

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected companion-track collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));

  const ctgEdgeLeft = points[0][0];
  const ctgEdgeRight = points[1][0];
  assert.ok(ctgEdgeLeft >= supportRectX - 0.1, `expected band left edge >= bar left edge, got ${ctgEdgeLeft} < ${supportRectX}`);
  assert.ok(
    ctgEdgeRight <= supportRectRight + 0.1,
    `expected band right edge <= bar right edge, got ${ctgEdgeRight} > ${supportRectRight}`,
  );
});

test("mapq threshold filters out low-quality collinearity hits", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 60,
        },
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [],
          },
        ],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-mapq",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 800,
                refStart: 100,
                refEnd: 900,
                blockLength: 1200,
                mapq: 30,
              },
              {
                ctgStart: 900,
                ctgEnd: 1800,
                refStart: 1000,
                refEnd: 1900,
                blockLength: 1200,
                mapq: 60,
              },
            ],
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const companionBandCount = (html.match(/track-collinearity-band is-companion/g) || []).length;
  const sceneMatch = html.match(
    /<script type="application\/json" data-track-band-canvas-scene>([^<]*"kind":"main-track"[^<]*)<\/script>/,
  );
  assert.ok(sceneMatch, "expected a main-track canvas scene");
  const scene = JSON.parse(sceneMatch[1]);
  assert.equal(companionBandCount, 1);
  assert.equal(scene.bands.length, 1);
});

test("mapq input displays manual non-negative value without snapping to presets", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 77,
        },
      },
    }),
  );
  assert.match(
    html,
    /<input\s+id="assembly-track-mapq"\s+class="assembly-track-combo-input"\s+type="text"\s+inputmode="numeric"\s+pattern="\[0-9\]\*"\s+value="77"\s+autocomplete="off"[^>]*>/,
  );
});

test("support ds sync persists fallback selection when restored value is invalid", () => {
  const storage = createSupportDsStorageMock(JSON.stringify({ supportDatasetId: 999 }));
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/workspace-sync-persist", projectId: 77 },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 77, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: null,
      },
    }),
  );

  const result = __testSyncSupportDatasetSelection(store, storage);

  assert.deepEqual(result, { changed: true, supportDatasetId: 22 });
  assert.equal(storage.setCalls.length, 1);
  assert.deepEqual(JSON.parse(storage.readRawValue()), { supportDatasetId: 22 });
});

test("support ds sync selects first option after first support dataset is appended", () => {
  const storage = createSupportDsStorageMock(null);
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/workspace-sync-first-append", projectId: 78 },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        ],
        existingProjects: [{ projectId: 78, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
      assembly: {
        supportDatasetId: null,
      },
    }),
  );

  assert.deepEqual(
    __testSyncSupportDatasetSelection(store, storage),
    { changed: false, supportDatasetId: null },
  );

  store.setState({
    ...store.getState(),
    initializer: {
      ...store.getState().initializer,
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 78, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });

  const result = __testSyncSupportDatasetSelection(store, storage);

  assert.deepEqual(result, { changed: true, supportDatasetId: 22 });
  assert.equal(storage.setCalls.length, 1);
  assert.deepEqual(JSON.parse(storage.readRawValue()), { supportDatasetId: 22 });
});

test("support dataset selection persists project-scoped main track view state", async () => {
  const persisted = [];
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/ws", projectId: 7 },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        supportDatasetId: null,
        supportChrCtgs: [],
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 8,
                datasetName: "",
                ctgName: "flye_ctg8",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 250,
          maxTickCount: 15,
          alignmentLength: 10000,
          mapq: 30,
        },
      },
    }),
  );

  await __testApplySupportDatasetSelection(store, 22, {
    async loadSupportChrCtgs() {
      return [{ assemblyCtgId: 30, name: "Ctg30" }];
    },
    async persistProjectAssemblyViewState(payload) {
      persisted.push(payload);
    },
  });

  assert.equal(store.getState().assembly.supportDatasetId, 22);
  assert.deepEqual(persisted, [
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: 22,
      trackView: {
        supportDsCtgLen: 10000,
        minTickUnitKb: 250,
        maxTickCount: 15,
        alignmentLength: 10000,
        mapq: 30,
      },
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: store.getState().assembly.finalPathByChr,
    },
  ]);
});

test("track click intent uses selectCtg by default and reserves Ctrl/Cmd for subview selection", () => {
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "primary", contigId: 8 }),
    { type: "select-ctg", contigId: 8 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "support", contigId: 30 }),
    { type: "select-ctg", contigId: 30 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "primary", contigId: 8, ctrlKey: true }),
    { type: "select-subview-candidate", trackRole: "primary", contigId: 8 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "phased", contigId: 2, ctrlKey: true }),
    { type: "select-subview-candidate", trackRole: "phased", contigId: 2 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "support", contigId: 30, metaKey: true }),
    { type: "select-subview-candidate", trackRole: "support", contigId: 30 },
  );
  assert.deepEqual(
    __testResolveTrackContigClickAction({ trackRole: "other", contigId: 30 }),
    { type: "noop" },
  );
});

test("assembly rendering marks box-selected track ctgs with multi-selected class", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        trackSelectedCtgIds: [8, 30],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /track-ctg-group is-multi-selected is-companion/);
  assert.match(html, /track-ctg-group is-active is-multi-selected/);
  assert.match(html, /class="track-ctg is-multi-selected is-companion"/);
});

test("context menu opens for track contig glyphs and legacy ctg nodes", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const trackTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return {
          getAttribute(name) {
            if (name === "data-track-contig-id") return "30";
            if (name === "data-track-role") return "support";
            return null;
          },
        };
      }
      if (selector === "[data-assembly-ctg-id]") {
        return null;
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: trackTarget,
    clientX: 12,
    clientY: 34,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.match(menuState.innerHTML, /翻转 contig/);
  assert.match(menuState.innerHTML, /重命名 contig/);
  assert.match(menuState.innerHTML, /镜像 contig/);
  assert.doesNotMatch(menuState.innerHTML, /撤销镜像 contig/);
  assert.doesNotMatch(menuState.innerHTML, /隐藏 contig/);
  assert.doesNotMatch(menuState.innerHTML, /解除隐藏 contig/);
  assert.doesNotMatch(menuState.innerHTML, /删除 contig/);
  assert.doesNotMatch(menuState.innerHTML, /查看\/编辑成员/);
  assert.doesNotMatch(menuState.innerHTML, /更多 contig 操作/);
  assert.doesNotMatch(menuState.innerHTML, /移动锚点/);
  assert.doesNotMatch(menuState.innerHTML, /当前版本未接入/);
});

test("primary track context menu toggles hide/unhide contig label by hidden state", () => {
  const host = {};
  const visibleStore = createStore(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [],
      },
    }),
  );
  const hiddenStore = createStore(
    createState({
      assembly: {
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );

  const visibleItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: "primary" },
    deletedCtgContext: null,
    memberNode: null,
    store: visibleStore,
    host,
  });
  const hiddenItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: "primary" },
    deletedCtgContext: null,
    memberNode: null,
    store: hiddenStore,
    host,
  });

  assert.ok(visibleItems.some((item) => item.label === "隐藏 contig"));
  assert.ok(visibleItems.every((item) => item.label !== "解除隐藏 contig"));
  assert.ok(hiddenItems.some((item) => item.label === "解除隐藏 contig"));
  assert.ok(hiddenItems.every((item) => item.label !== "隐藏 contig"));
});

test("support track context menu exposes mirror toggle and mirror bar keeps only unmirror action", () => {
  const host = {};
  const store = createStore(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 22,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 30,
            name: "support-a",
            totalLength: 10_000_000,
            anchorStart: 100,
            lengthBp: 10_000_000,
            startBp: 0,
            endBp: 9_999_999,
            laneIndex: 0,
          },
        ],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const supportItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  }).map((item) => item.label);
  const mirrorItems = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: true },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  }).map((item) => item.label);

  assert.ok(supportItems.includes("翻转 contig"));
  assert.ok(supportItems.includes("重命名 contig..."));
  assert.ok(supportItems.includes("Append to path"));
  assert.ok(supportItems.includes("撤销镜像 contig"));
  assert.deepEqual(mirrorItems, ["Append to path", "撤销镜像 contig"]);
});

test("phased mode primary contig context menu offers per-haplotype add and append actions", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: "primary", datasetId: null, isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      async addTrackContigToPhasedTrack(_host, _store, payload) {
        calls.push({ type: "add", payload });
      },
      async appendTrackContigToFinalPath(_host, _store, ctgContext, options) {
        calls.push({ type: "append", ctgContext, options });
      },
    },
  });
  const labels = items.map((item) => item.label);

  assert.deepEqual(
    labels.filter((label) => label.startsWith("add to ") || label.startsWith("append to path ")),
    ["add to A", "add to B", "append to path A", "append to path B"],
  );
  assert.equal(labels.includes("Append to path"), false);

  await items.find((item) => item.label === "add to B").run();
  await items.find((item) => item.label === "append to path B").run();

  assert.deepEqual(calls, [
    {
      type: "add",
      payload: {
        phasedTrackId: 102,
        haplotypeKey: "B",
        label: "Chr01B",
        assemblyCtgId: 2,
      },
    },
    {
      type: "append",
      ctgContext: { assemblyCtgId: 2, trackRole: "primary", datasetId: null, isMirror: false },
      options: {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    },
  ]);
});

test("phased mode support contig context menu offers grouped per-haplotype append actions", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      async addTrackContigToPhasedTrack(_host, _store, payload) {
        calls.push({ type: "add", payload });
      },
      async appendTrackContigToFinalPath(_host, _store, ctgContext, options) {
        calls.push({ type: "append", ctgContext, options });
      },
    },
  });
  const labels = items.map((item) => item.label);

  assert.deepEqual(
    labels.filter((label) => label.startsWith("append to path ")),
    ["append to path A", "append to path B"],
  );
  assert.equal(labels.some((label) => label.startsWith("add to ")), false);
  assert.equal(labels.includes("Append to path"), false);

  await items.find((item) => item.label === "append to path B").run();

  assert.deepEqual(calls, [
    {
      type: "append",
      ctgContext: { assemblyCtgId: 30, trackRole: "support", datasetId: 22, isMirror: false },
      options: {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    },
  ]);
});

test("creating a phased track refreshes only the main assembly card", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};
    const created = await initializeProject({
      workspaceRoot: "/tmp/workspace",
      projectName: `project-phased-local-refresh-${Date.now()}`,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: [],
      phasedAssemblyEnabled: true,
    });
    const store = createStore(createState({
      session: {
        workspacePath: "/tmp/workspace",
        projectId: created.projectId,
      },
      assembly: {
        selectedChrName: "Chr01",
        phasedChrTracks: [],
      },
    }));
    let fullPageRenderCount = 0;
    let replacedCount = 0;
    const makeNode = () => ({
      addEventListener() {},
      querySelector() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
      replaceWith() {
        replacedCount += 1;
      },
    });
    const currentSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const nextSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const fakeDocument = {
      createElement(tagName) {
        assert.equal(tagName, "template");
        return {
          set innerHTML(_value) {},
          content: {
            querySelector(selector) {
              return nextSections.get(selector) || null;
            },
          },
        };
      },
      querySelector() {
        return null;
      },
      contains(node) {
        return node === routeHost;
      },
    };
    const routeHost = {
      id: "route-host",
      isConnected: true,
      ownerDocument: fakeDocument,
      matches(selector) {
        return selector === "#route-host";
      },
      closest(selector) {
        return selector === "#route-host" ? this : null;
      },
      querySelector(selector) {
        return currentSections.get(selector) || null;
      },
      querySelectorAll() {
        return [];
      },
      addEventListener() {},
      set innerHTML(_value) {
        fullPageRenderCount += 1;
      },
    };

    await __testCreatePhasedChrTrack(routeHost, store);

    assert.equal(fullPageRenderCount, 0);
    assert.ok(replacedCount >= 2, "expected main-card sections to be replaced");
    assert.equal(store.getState().assembly.phasedChrTracks[0]?.haplotypeKey, "A");
  } finally {
    globalThis.window = previousWindow || {};
  }
});

test("phased track item context menu appends, flips, and removes only that phased instance", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(createState({
    assembly: {
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
      ],
    },
  }));
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: {
      assemblyCtgId: 2,
      trackRole: "phased",
      datasetId: null,
      isMirror: false,
      phasedTrackId: 101,
      phasedTrackItemId: 9001,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      async appendTrackContigToFinalPath(_host, _store, ctgContext, options) {
        calls.push({ type: "append", ctgContext, options });
      },
      async applyEditorAction(_host, _store, payload) {
        calls.push({ type: "flip", payload });
      },
      async removePhasedTrackItem(_host, _store, payload) {
        calls.push({ type: "remove", payload });
      },
    },
  });

  assert.deepEqual(items.map((item) => item.label), ["append to path A", "append to path B", "翻转 contig", "从该分型组删除"]);
  await items[1].run();
  await items[2].run();
  await items[3].run();
  assert.deepEqual(calls, [
    {
      type: "append",
      ctgContext: {
        assemblyCtgId: 2,
        trackRole: "phased",
        datasetId: null,
        isMirror: false,
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        phasedHaplotypeKey: "A",
      },
      options: {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    },
    {
      type: "flip",
      payload: {
        action: "flip-ctg",
        args: { assemblyCtgId: 2, phasedTrackItemId: 9001 },
        keepCurrentCtg: true,
        localRefresh: true,
        phasedOnlyRefresh: true,
      },
    },
    {
      type: "remove",
      payload: { phasedTrackItemId: 9001 },
    },
  ]);
});

test("phased track item orientation is isolated from the main track ctg orientation", () => {
  const buildHtml = ({ primaryOrient, hitStart, hitEnd }) => renderAssemblyPage(createState({
    initializer: {
      datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true }],
    },
    assembly: {
      activeHitsTrackKey: "A",
      supportDatasetId: null,
      supportChrCtgs: [],
      phasedChrTracks: [
        {
          phasedTrackId: 101,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 92, displayOrder: 1, orient: "+" }],
        },
      ],
      chrCtgs: [
        {
          assemblyCtgId: 92,
          name: "contig_92",
          assignedChrName: "Chr01",
          memberCount: 1,
          totalLength: 600_000,
          anchorStart: 500,
          orient: primaryOrient,
          refOrient: primaryOrient,
          hits: [
            {
              refStart: 100_000,
              refEnd: 190_000,
              ctgStart: hitStart,
              ctgEnd: hitEnd,
              blockLength: 90_001,
              mapq: 60,
              strand: "+",
            },
          ],
        },
      ],
    },
  }));
  const extractPhasedBandPoints = (html) => {
    const match = html.match(
      /<polygon class="track-collinearity-band is-phased-track"[^>]*data-band-track-role="phased"[^>]*data-band-contig-id="92"[^>]*points="([^"]+)"/,
    );
    assert.ok(match, "expected phased track hit band");
    return match[1];
  };

  const plusHtml = buildHtml({ primaryOrient: "+", hitStart: 100_000, hitEnd: 190_000 });
  const html = buildHtml({ primaryOrient: "-", hitStart: 410_001, hitEnd: 500_001 });

  assert.match(
    html,
    /<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="92"[^>]*data-track-role="primary"[^>]*data-track-ref-orient="-"/,
  );
  assert.match(
    html,
    /<g class="track-ctg-group[^"]*"[^>]*data-track-contig-id="92"[^>]*data-track-role="phased"[^>]*data-track-ref-orient="\+"[^>]*data-track-phased-track-item-id="9001"/,
  );
  assert.match(html, />contig_92 \(-\)<\/text>/);
  assert.match(html, />contig_92 \(\+\)<\/text>/);
  assert.equal(extractPhasedBandPoints(html), extractPhasedBandPoints(plusHtml));
});

test("adding a dragged primary ctg to a phased track inherits the current visual offset", () => {
  const store = createStore(createState({
    assembly: {
      trackDragOffsets: [
        { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
      ],
    },
  }));

  const changed = __testInheritPrimaryTrackDragOffsetForPhasedItem(store, {
    assemblyCtgId: 8,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
  });

  assert.equal(changed, true);
  assert.deepEqual(store.getState().assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
    {
      trackRole: "phased",
      assemblyCtgId: 8,
      phasedTrackId: 101,
      phasedTrackItemId: 9001,
      offsetBp: 1200,
    },
  ]);
});

test("adding an undragged primary ctg to a phased track leaves phased offsets unchanged", () => {
  const store = createStore(createState({
    assembly: {
      trackDragOffsets: [
        { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
      ],
    },
  }));

  const changed = __testInheritPrimaryTrackDragOffsetForPhasedItem(store, {
    assemblyCtgId: 2,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
  });

  assert.equal(changed, false);
  assert.deepEqual(store.getState().assembly.trackDragOffsets, [
    { trackRole: "primary", assemblyCtgId: 8, offsetBp: 1200 },
  ]);
});

test("removing a phased track item refreshes only the main assembly card", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};
    const created = await initializeProject({
      workspaceRoot: "/tmp/workspace",
      projectName: `project-phased-remove-local-refresh-${Date.now()}`,
      referenceGenomeId: 1,
      primaryDatasetId: 1,
      supportDatasetIds: [],
      phasedAssemblyEnabled: true,
    });
    const createdTrack = await createPhasedChrTrack({
      workspaceRoot: "/tmp/workspace",
      projectId: created.projectId,
      parentChrName: "Chr01",
    });
    const added = await addCtgToPhasedChrTrack({
      workspaceRoot: "/tmp/workspace",
      projectId: created.projectId,
      phasedTrackId: createdTrack.track.phasedTrackId,
      assemblyCtgId: 2,
    });
    const store = createStore(createState({
      session: {
        workspacePath: "/tmp/workspace",
        projectId: created.projectId,
      },
      assembly: {
        selectedChrName: "Chr01",
        phasedChrTracks: [
          {
            ...createdTrack.track,
            items: [added.item],
          },
        ],
        isChrPhased: true,
        activePhasedTrackKey: "A",
      },
    }));
    let fullPageRenderCount = 0;
    let replacedCount = 0;
    const makeNode = () => ({
      addEventListener() {},
      querySelector() {
        return null;
      },
      querySelectorAll() {
        return [];
      },
      replaceWith() {
        replacedCount += 1;
      },
    });
    const currentSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const nextSections = new Map([
      [".chr-strip.has-members-panel", makeNode()],
      [".assembly-track-unified", makeNode()],
    ]);
    const fakeDocument = {
      createElement(tagName) {
        assert.equal(tagName, "template");
        return {
          set innerHTML(_value) {},
          content: {
            querySelector(selector) {
              return nextSections.get(selector) || null;
            },
          },
        };
      },
      querySelector() {
        return null;
      },
      contains(node) {
        return node === routeHost;
      },
    };
    const routeHost = {
      id: "route-host",
      isConnected: true,
      ownerDocument: fakeDocument,
      matches(selector) {
        return selector === "#route-host";
      },
      closest(selector) {
        return selector === "#route-host" ? this : null;
      },
      querySelector(selector) {
        return currentSections.get(selector) || null;
      },
      querySelectorAll() {
        return [];
      },
      addEventListener() {},
      set innerHTML(_value) {
        fullPageRenderCount += 1;
      },
    };

    await __testRemovePhasedTrackItem(routeHost, store, { phasedTrackItemId: added.item.itemId });

    assert.equal(fullPageRenderCount, 0);
    assert.ok(replacedCount >= 2, "expected main-card sections to be replaced");
    assert.equal(store.getState().assembly.phasedChrTracks[0]?.items.length, 0);
  } finally {
    globalThis.window = previousWindow || {};
  }
});

test("primary and phased track labels expose single-active hits toggles", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedChrName: "Chr01",
        activeHitsTrackKey: "primary",
        activeHitsTrackKeyByChr: { Chr01: "primary" },
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const actions = {
    setActiveHitsTrack(_host, _store, payload) {
      calls.push(payload);
    },
  };
  const primaryItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "primary", isMirror: false },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });
  const phasedItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "phased",
      isMirror: false,
      phasedTrackId: 101,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });

  assert.equal(primaryItems[0].label, "隐藏 hits 线");
  assert.equal(phasedItems[0].label, "显示 hits 线");

  await primaryItems[0].run();
  await phasedItems[0].run();

  assert.deepEqual(calls, [{ trackKey: "" }, { trackKey: "A" }]);
});

test("ds-backed track label context menu exposes add new ctg with clicked target", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        selectedChrName: "Chr01",
      },
    }),
  );
  const calls = [];
  const primaryItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "primary", isMirror: false, datasetId: 11 },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      importAddCtgIntoTrack(_host, _store, payload) {
        calls.push(payload);
      },
    },
  });
  const supportItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "support", isMirror: false, datasetId: 22 },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      importAddCtgIntoTrack(_host, _store, payload) {
        calls.push(payload);
      },
    },
  });

  const primaryAdd = primaryItems.find((item) => item.label === "Add new ctg...");
  const supportAdd = supportItems.find((item) => item.label === "Add new ctg...");
  assert.ok(primaryAdd, "expected primary add new ctg menu item");
  assert.ok(supportAdd, "expected support add new ctg menu item");
  await primaryAdd.run();
  await supportAdd.run();
  assert.deepEqual(calls, [
    { targetChr: "Chr01", targetTrack: "hifiasm", datasetId: 11, trackRole: "primary" },
    { targetChr: "Chr01", targetTrack: "flye", datasetId: 22, trackRole: "support" },
  ]);
});

test("phased and mirror track labels do not expose direct add new ctg", () => {
  const store = createStore(
    createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
      assembly: {
        selectedChrName: "Chr01",
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        ],
      },
    }),
  );
  const host = { closest: () => null };
  const phasedItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "phased",
      isMirror: false,
      phasedTrackId: 101,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  });
  const mirrorItems = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: { trackRole: "support", isMirror: true, datasetId: 22 },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
  });
  assert.equal(phasedItems.some((item) => item.label === "Add new ctg..."), false);
  assert.equal(mirrorItems.some((item) => item.label === "Add new ctg..."), false);
});

test("phased track label context menu exposes delete track action", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedChrName: "Chr01",
        activeHitsTrackKey: "primary",
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
        ],
      },
    }),
  );
  const calls = [];
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "phased",
      isMirror: false,
      phasedTrackId: 101,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: {
      deletePhasedTrack(_host, _store, payload) {
        calls.push(payload);
      },
      confirm() {
        return true;
      },
    },
  });

  const deleteItem = items.find((item) => /删除.*分型轨道/.test(item.label));
  assert.ok(deleteItem, "expected phased track delete menu item");
  await deleteItem.run();
  assert.deepEqual(calls, [{ phasedTrackId: 101, haplotypeKey: "A" }]);
});

test("deleting a phased track compacts final path keys with track labels", () => {
  const nextFinalPathByChr = __testCompactFinalPathByDeletedPhasedTrack(
    {
      Chr01A: { chrName: "Chr01A", segments: [{ segmentId: "a" }] },
      Chr01B: { chrName: "Chr01B", segments: [{ segmentId: "b" }] },
      Chr01C: { chrName: "Chr01C", segments: [{ segmentId: "c" }] },
      Chr02: { chrName: "Chr02", segments: [{ segmentId: "ordinary" }] },
    },
    {
      parentChrName: "Chr01",
      deletedPhasedTrackId: 102,
      tracksBefore: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", displayOrder: 1 },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", displayOrder: 2 },
        { phasedTrackId: 103, haplotypeKey: "C", label: "Chr01C", displayOrder: 3 },
      ],
    },
  );

  assert.deepEqual(Object.keys(nextFinalPathByChr).sort(), ["Chr01A", "Chr01B", "Chr02"]);
  assert.deepEqual(nextFinalPathByChr.Chr01B, {
    chrName: "Chr01B",
    segments: [{ segmentId: "c" }],
  });
  assert.deepEqual(nextFinalPathByChr.Chr02, {
    chrName: "Chr02",
    segments: [{ segmentId: "ordinary" }],
  });
});

test("toggling support mirror persists project-scoped mirrored ctgs", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
    },
    assembly: {
      selectedChrName: "Chr01",
      supportDatasetId: 22,
      finalPathByChr: {
        Chr01: {
          mode: "segments",
          chrName: "Chr01",
          segments: [
            {
              segmentId: "seg-1",
              type: "ctg",
              assemblyCtgId: 8,
              datasetName: "",
              ctgName: "ctg-primary",
              overallLen: 500,
              start: 1,
              end: 500,
            },
          ],
          updatedAt: "1",
        },
      },
      chrCtgs: [
        { assemblyCtgId: 8, name: "ctg-primary", totalLength: 500, anchorStart: 0, startBp: 0, endBp: 499 },
      ],
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "ctg-mirror", totalLength: 300, anchorStart: 320, startBp: 0, endBp: 299, laneIndex: 0 },
      ],
      supportMirroredCtgs: [],
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };
  const persisted = [];

  await __testToggleSupportTrackCtgMirror(
    host,
    store,
    {
      datasetId: 22,
      assemblyCtgId: 30,
      shouldMirror: true,
    },
    {
      async persistProjectAssemblyViewState(payload) {
        persisted.push(payload);
      },
    },
  );

  assert.equal(store.getState().assembly.supportMirroredCtgs.length, 1);
  assert.deepEqual(persisted, [
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: 22,
      trackView: store.getState().assembly.trackView,
      supportDsCtgLenRulesByChr: {},
      supportMirroredCtgs: store.getState().assembly.supportMirroredCtgs,
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: store.getState().assembly.finalPathByChr,
      degapProjectState: {},
    },
  ]);
});

test("batch hide and unhide force selected primary contigs to target hidden state", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      session: {
        workspacePath: "/tmp/ws",
        projectId: 7,
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 8,
                datasetName: "",
                ctgName: "ctg-beta",
                overallLen: 600,
                start: 1,
                end: 600,
              },
            ],
            updatedAt: "1",
          },
        },
        hiddenPrimaryCtgIds: [2],
      },
    }),
  );
  const persisted = [];

  await __testSetSelectedPrimaryTrackCtgsHidden(host, store, [2, 8], true, {
    async persistProjectAssemblyViewState(payload) {
      persisted.push(payload);
    },
  });
  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, [2, 8]);
  const hiddenFinalPathByChr = persisted[0].finalPathByChr;

  await __testSetSelectedPrimaryTrackCtgsHidden(host, store, [2, 8], false, {
    async persistProjectAssemblyViewState(payload) {
      persisted.push(payload);
    },
  });
  assert.deepEqual(store.getState().assembly.hiddenPrimaryCtgIds, []);
  assert.deepEqual(persisted, [
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: null,
      trackView: store.getState().assembly.trackView,
      supportDsCtgLenRulesByChr: {},
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [2, 8],
      hiddenPrimaryCtgIdsByChr: { Chr01: [2, 8] },
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: hiddenFinalPathByChr,
      degapProjectState: {},
    },
    {
      workspaceRoot: "/tmp/ws",
      projectId: 7,
      supportDatasetId: null,
      trackView: store.getState().assembly.trackView,
      supportDsCtgLenRulesByChr: {},
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      hiddenPrimaryCtgIdsByChr: {},
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      subviewAnchorStateByKey: {},
      trackScrollState: store.getState().assembly.trackScrollState,
      subviewTrackScrollState: store.getState().assembly.subviewTrackScrollState,
      finalPathTrackScrollState: store.getState().assembly.finalPathTrackScrollState,
      membersCardCollapsed: true,
      finalPathViewMode: "graph",
      finalPathByChr: store.getState().assembly.finalPathByChr,
      degapProjectState: {},
    },
  ]);
});

test("assembly main view renders the persisted final path card for the current chr", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "flye_ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /final-path-track-min-tick-unit-kb/);
  assert.match(html, /final-path-track-max-tick-count/);
  assert.match(html, /assembly-final-path-layout/);
  assert.match(html, /assembly-final-path-svg-wrap/);
  assert.match(html, /assembly-final-path-svg/);
  assert.match(html, /track-ruler-line/);
  assert.match(html, /track-tick-guide/);
  assert.match(html, /track-ctg-group/);
  assert.match(html, /flye_ctg9/);
  assert.match(html, /data-final-path-export-toggle="true"/);
  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.match(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("final path graph hides labels that do not fit inside bars and keeps hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "final-path-very-long-segment-label",
                overallLen: 1_000,
                start: 1,
                end: 1_000,
              },
              {
                segmentId: "gap-1",
                type: "gap",
                gapSizeBp: 499_000,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.doesNotMatch(html, /<text class="track-ctg-label[^"]*"[^>]*>final-path-very-long-segment-label \(\+\)<\/text>/);
  assert.match(html, /<title>final-path-very-long-segment-label \|/);
});

test("assembly main view keeps final path all export while hiding fasta when project dataset fasta is unavailable", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        datasets: [
          { datasetId: 3, name: "flye", label: "flye", fastaAvailable: false },
        ],
        existingProjects: [
          {
            projectId: 7,
            projectName: "projA",
            primaryDatasetId: 3,
            supportDatasetIds: [],
          },
        ],
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "flye",
                ctgName: "ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.doesNotMatch(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("assembly main view keeps final path fasta export visible for full partitioned delivery packages", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        packageMetadata: {
          packageMode: "fast",
          sequenceLayout: "partitioned",
          preassignedChr: true,
          chrAssignmentMinCoveragePercent: 60,
          selfAlignmentScope: "chr_partition",
          crossAlignmentScope: "chr_partition",
        },
        datasets: [
          { datasetId: 3, name: "flye", label: "flye", fastaAvailable: true },
        ],
        existingProjects: [
          {
            projectId: 7,
            projectName: "projA",
            primaryDatasetId: 3,
            supportDatasetIds: [],
          },
        ],
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "flye",
                ctgName: "ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /data-final-path-export-action="png"/);
  assert.match(html, /data-final-path-export-action="tsv"/);
  assert.match(html, /data-final-path-export-action="fasta"/);
  assert.match(html, /data-final-path-export-action="all"/);
});

test("assembly main view renders an empty final path card for the current chr without persisted rows", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {},
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /data-final-path-view-mode="graph"/);
  assert.match(html, /assembly-final-path-svg-wrap/);
  assert.match(html, /data-final-path-export-toggle="true"/);
});

test("phased mode final path card defaults to all haplotypes and omits the parent path card", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [{ segmentId: "parent", type: "gap", gapSizeBp: 100 }],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /data-phased-final-path-key="__all__"/);
  assert.match(html, /data-phased-final-path-current-key="__all__"/);
  assert.match(html, />All <span aria-hidden="true">/);
  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*data-final-path-all-card="Chr01B"/);
  assert.doesNotMatch(html, /projA_Chr01 path/);
  assert.match(html, /data-phased-final-path-key="A"/);
  assert.match(html, /data-phased-final-path-key="B"/);
  assert.match(html, /data-phased-final-path-chr-name="Chr01B"/);
  assert.match(html, /data-final-path-remove-row="hap-b"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01B"[\s\S]*data-final-path-remove-row="hap-b"/);
  assert.match(html, /class="final-path-card-list-head"[\s\S]*>Chr01A<\/div>[\s\S]*class="final-path-card-list-head"[\s\S]*>Chr01B<\/div>/);
});

test("phased mode final path card can select one haplotype independently of the main phased track", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        activePhasedTrackKey: "A",
        activeFinalPathKey: "B",
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [{ segmentId: "hap-a", type: "gap", gapSizeBp: 100 }],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /data-phased-final-path-current-key="B"/);
  assert.match(html, />B <span aria-hidden="true">/);
  assert.match(html, /projA_Chr01B path/);
  assert.doesNotMatch(html, /projA_Chr01A path/);
  assert.match(html, /data-final-path-remove-row="hap-b"/);
});

test("append-to-phased-path focus patch switches single final path selection to the target haplotype", () => {
  const patch = __testResolveAppendToPathFocusPatch(
    {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "B",
      activeFinalPathKeyByChr: {
        Chr01: "B",
      },
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A" },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B" },
      ],
    },
    "A",
  );

  assert.deepEqual(patch, {
    activeFinalPathKey: "A",
    activeFinalPathKeyByChr: {
      Chr01: "A",
    },
  });
});

test("append-to-phased-path focus patch preserves all final path selection", () => {
  const patch = __testResolveAppendToPathFocusPatch(
    {
      selectedChrName: "Chr01",
      isChrPhased: true,
      activeFinalPathKey: "__all__",
      activeFinalPathKeyByChr: {
        Chr01: "__all__",
      },
      phasedChrTracks: [
        { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A" },
        { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B" },
      ],
    },
    "A",
  );

  assert.deepEqual(patch, {});
});

test("phased all final path graph renders haplotype labels in the graph label column", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [{ segmentId: "hap-a", type: "gap", gapSizeBp: 100 }],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [{ segmentId: "hap-b", type: "gap", gapSizeBp: 200 }],
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );

  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*data-final-path-all-graph-label="Chr01A"/);
  assert.match(html, /data-final-path-all-card="Chr01B"[\s\S]*data-final-path-all-graph-label="Chr01B"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01A"[\s\S]*data-final-path-segment-id="hap-a"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01B"[\s\S]*data-final-path-segment-id="hap-b"/);
});

test("phased all DEGAP view renders haplotype graphs and groups only tracks with jobs", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [
              { segmentId: "a-left", type: "ctg", assemblyCtgId: 2, datasetName: "hifiasm", ctgName: "A-left", overallLen: 100, start: 1, end: 100 },
              { segmentId: "gap-a", type: "gap", gapSizeBp: 20 },
              { segmentId: "a-right", type: "ctg", assemblyCtgId: 8, datasetName: "hifiasm", ctgName: "A-right", overallLen: 100, start: 1, end: 100 },
            ],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [
              { segmentId: "b-left", type: "ctg", assemblyCtgId: 12, datasetName: "hifiasm", ctgName: "B-left", overallLen: 100, start: 1, end: 100 },
              { segmentId: "gap-b", type: "gap", gapSizeBp: 20 },
              { segmentId: "b-right", type: "ctg", assemblyCtgId: 18, datasetName: "hifiasm", ctgName: "B-right", overallLen: 100, start: 1, end: 100 },
            ],
          },
        },
        finalPathViewMode: "degap",
        degap: {
          settingsPanelDismissed: true,
          jobs: [
            {
              jobId: "B-left_vs_B-right_Left-job",
              label: "B-left_vs_B-right Left-job",
              chrName: "Chr01B",
              gapSegmentId: "gap-b",
              gapIndex: 2,
              side: "left",
              leftCtg: "B-left",
              rightCtg: "B-right",
              outPath: "/srv/degap/B-left_vs_B-right_Left-job",
              baselineOutPath: "/srv/degap/B-left_vs_B-right_Left-job",
              left: { assemblyCtgId: 12, start: 1, end: 100 },
              right: { assemblyCtgId: 18, start: 1, end: 100 },
              baselineSettings: {
                degapPath: "/opt/DEGAP/bin/DEGAP.py",
                hifiReads: ["/reads/a.fq.gz"],
                gpmServerPath: "/srv/gpm_server",
                outRoot: "/srv/degap",
              },
            },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-final-path-view-mode="degap"/);
  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*data-final-path-all-graph-label="Chr01A"/);
  assert.match(html, /data-final-path-all-card="Chr01B"[\s\S]*data-final-path-all-graph-label="Chr01B"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01A"[\s\S]*data-final-path-segment-id="gap-a"/);
  assert.match(html, /data-final-path-target-chr-name="Chr01B"[\s\S]*data-final-path-segment-id="gap-b"/);
  assert.doesNotMatch(html, /data-degap-job-group="Chr01A"/);
  assert.match(html, /data-degap-job-group="Chr01B"[\s\S]*B-left_vs_B-right Left-job/);
});

test("phased all final path log renders one titled log card per haplotype", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      initializer: {
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [], phasedAssemblyEnabled: true },
        ],
      },
      assembly: {
        isChrPhased: true,
        phasedChrTracks: [
          { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
          { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
        ],
        finalPathByChr: {
          Chr01A: {
            mode: "segments",
            chrName: "Chr01A",
            segments: [
              {
                segmentId: "hap-a",
                type: "ctg",
                assemblyCtgId: 2,
                datasetName: "hifiasm",
                ctgName: "ctg-alpha",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
          },
          Chr01B: {
            mode: "segments",
            chrName: "Chr01B",
            segments: [
              {
                segmentId: "hap-b",
                type: "ctg",
                assemblyCtgId: 8,
                datasetName: "hifiasm",
                ctgName: "ctg-beta",
                overallLen: 600,
                start: 1,
                end: 600,
              },
            ],
          },
        },
        finalPathViewMode: "log",
      },
    }),
  );

  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*class="final-path-all-card-title">Chr01A<\/strong>/);
  assert.match(html, /data-final-path-all-card="Chr01B"[\s\S]*class="final-path-all-card-title">Chr01B<\/strong>/);
  assert.match(html, /data-final-path-all-card="Chr01A"[\s\S]*final-path-log-body[\s\S]*data-final-path-all-card="Chr01B"[\s\S]*final-path-log-body/);
});

test("assembly main view renders a placeholder row for an empty final path in table mode", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {},
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /projA_Chr01 path/);
  assert.match(html, /data-final-path-view-mode="table"/);
  assert.match(html, /data-final-path-empty-row="true"/);
  assert.match(html, /data-final-path-export-toggle="true"/);
});

test("assembly main view renders ref final-path rows as fixed-name bounded segments in table mode", () => {
  const html = renderAssemblyPage(
    createState({
      session: {
        projectName: "projA",
      },
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                sourceKind: "ref_segment",
                assemblyCtgId: 9001,
                referenceChrId: 1,
                referenceChrName: "Chr01",
                datasetName: "",
                ctgName: "ref_Chr01:5201-5600",
                originId: "Chr01",
                overallLen: 5000,
                memberStartBp: 5101,
                memberEndBp: 10100,
                start: 101,
                end: 500,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );

  assert.match(html, /data-final-path-cell="ctg"[^>]*value="ref_Chr01:5201-5600"[^>]*disabled/);
  assert.match(html, /data-final-path-cell="start"[^>]*value="101"/);
  assert.match(html, /data-final-path-cell="end"[^>]*value="500"/);
});

test("assembly page renders a blocking final-path export modal when export job is open", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        finalPathExportJob: {
          open: true,
          kind: "all",
          chrName: "Chr01",
          status: "running",
          currentStep: "导出图(.png)",
          completedOutputs: [],
          cancelRequested: false,
          error: "",
          steps: [
            { kind: "png", label: "图(.png)", outputPath: "a.png" },
            { kind: "tsv", label: "表(.tsv)", outputPath: "a.tsv" },
            { kind: "fasta", label: "序列(.fasta)", outputPath: "a.fasta" },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-final-path-export-modal="true"/);
  assert.match(html, /data-final-path-export-overlay="true"/);
  assert.match(html, /正在导出 final path/);
  assert.match(html, /Chr01/);
  assert.match(html, /data-final-path-export-step-status="running"/);
  assert.match(html, /class="pipeline-spinner"/);
  assert.match(html, /图\(.png\)/);
  assert.match(html, /表\(.tsv\)/);
  assert.match(html, /序列\(.fasta\)/);
  assert.match(html, /data-final-path-export-close="true"/);
});

test("assembly page renders a blocking batch-delete progress modal", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        batchDeleteProgress: {
          open: true,
          current: 1,
          total: 2,
          items: [
            { assemblyCtgId: 2, label: "ctg-alpha", status: "success" },
            { assemblyCtgId: 8, label: "ctg-beta", status: "running" },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-batch-delete-progress-modal="true"/);
  assert.match(html, /批量删除进度/);
  assert.match(html, /1\/2/);
  assert.match(html, /ctg-alpha/);
  assert.match(html, /assembly_ctg_id=2/);
  assert.match(html, /ctg-beta/);
  assert.match(html, /assembly_ctg_id=8/);
  assert.match(html, /pipeline-done/);
  assert.match(html, /pipeline-spinner/);
});

test("assembly page renders add_ctg import progress modal", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        addCtgImportProgress: {
          open: true,
          status: "running",
          summary: "正在导入 add_ctg 包。",
          stages: [
            { label: "index_ref_paf", progressIndex: 2, progressTotal: 4 },
          ],
        },
      },
    }),
  );

  assert.match(html, /data-add-ctg-import-progress-overlay="true"/);
  assert.match(html, /add_ctg 导入进度/);
  assert.match(html, /index_ref_paf \(2\/4\)/);
  assert.match(html, /2\/4/);
  assert.match(html, /pipeline-spinner/);
});

test("add_ctg import progress meter includes frontend stages after backend completion", () => {
  const backendStages = Array.from({ length: 45 }, (_, index) => ({
    label: index === 44 ? "complete" : `backend_stage_${index + 1}`,
    progressIndex: index + 1,
    progressTotal: 45,
  }));
  const html = renderAssemblyPage(
    createState({
      assembly: {
        addCtgImportProgress: {
          open: true,
          status: "success",
          summary: "add_ctg 包导入完成。",
          stages: [
            "workspace_root=/tmp/workspace",
            "project_id=1",
            "target=Chr01/hifiasm",
            "add_ctg_zip_path=/tmp/add.zip",
            "调用后端 import_add_ctg_package",
            ...backendStages,
            "刷新当前 chr 视图",
          ],
        },
      },
    }),
  );

  assert.match(html, /class="import-progress-meter" aria-label="51\/51"/);
  assert.match(html, /刷新当前 chr 视图 \(51\/51\)/);
});

test("derived ctg source tags render in track labels and primary member cards", () => {
  const html = renderAssemblyPage(
    createState({
      initializer: {
        datasets: [{ datasetId: 11, name: "hifiasm", label: "hifiasm" }],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
      assembly: {
        membersCardCollapsed: false,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "gap_filled",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 45_000_000,
            anchorStart: 100,
            derivedSource: "gapfiller",
            derivedTargetDatasetId: 11,
            derivedTargetDatasetName: "hifiasm",
          },
        ],
      },
    }),
  );

  assert.match(html, /track-ctg-source-tag is-source-gapfiller[^>]*> \[gapfiller\]<\/tspan>/);
  assert.match(html, /ctg-chip-source-tag is-source-gapfiller[^>]*>\[gapfiller\]<\/span>/);
});

test("batch delete progress modal closes even when the action host was detached", () => {
  let removed = false;
  const overlay = {
    remove() {
      removed = true;
    },
  };
  let routeHost = null;
  const doc = {
    createElement() {
      return {
        innerHTML: "",
        content: {
          firstElementChild: null,
        },
      };
    },
    querySelector(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  routeHost = {
    ownerDocument: doc,
    querySelector(selector) {
      return selector === "[data-batch-delete-progress-overlay='true']" ? overlay : null;
    },
  };
  const detachedHost = {
    ownerDocument: doc,
    closest() {
      return null;
    },
    querySelector() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        batchDeleteProgress: null,
      },
    }),
  );

  __testRerenderBatchDeleteProgress(detachedHost, store);

  assert.equal(removed, true);
});

test("batch delete progress modal close removes stale overlays outside the route host", () => {
  const removed = [];
  const staleOverlay = {
    remove() {
      removed.push("stale");
    },
  };
  let routeHost = null;
  const doc = {
    createElement() {
      return {
        innerHTML: "",
        content: {
          firstElementChild: null,
        },
      };
    },
    querySelector(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
    querySelectorAll(selector) {
      return selector === "[data-batch-delete-progress-overlay='true']" ? [staleOverlay] : [];
    },
  };
  routeHost = {
    ownerDocument: doc,
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  const detachedHost = {
    ownerDocument: doc,
    closest() {
      return null;
    },
    querySelector() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        batchDeleteProgress: null,
      },
    }),
  );

  __testRerenderBatchDeleteProgress(detachedHost, store);

  assert.deepEqual(removed, ["stale"]);
});

test("assembly page renders completed export steps with a check mark icon", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        finalPathExportJob: {
          open: true,
          kind: "all",
          chrName: "Chr01",
          status: "success",
          currentStep: "序列(.fasta)",
          completedOutputs: ["a.png", "a.tsv", "a.fasta"],
          cancelRequested: false,
          error: "",
          steps: [
            { kind: "png", label: "图(.png)", outputPath: "a.png" },
            { kind: "tsv", label: "表(.tsv)", outputPath: "a.tsv" },
            { kind: "fasta", label: "序列(.fasta)", outputPath: "a.fasta" },
          ],
        },
      },
    }),
  );

  assert.match(html, /class="assembly-final-path-export-body"/);
  assert.match(html, /data-final-path-export-step-status="done"/);
  assert.match(html, /class="pipeline-done"/);
  assert.match(html, /class="muted assembly-final-path-export-status success"/);
  assert.match(html, /&#10003;/);
});

test("export dialog css centers its content block and keeps step icons pinned on the right", () => {
  const css = readFileSync(
    new URL("../../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(css, /\.assembly-final-path-export-dialog\s*\{[^}]*width:\s*min\(680px,\s*calc\(100vw - 64px\)\);/);
  assert.match(css, /\.assembly-final-path-export-dialog\s*\{[^}]*padding:\s*28px 32px;/);
  assert.match(css, /\.assembly-final-path-export-body\s*\{[^}]*width:\s*min\(100%,\s*560px\);/);
  assert.match(css, /\.assembly-final-path-export-body\s*\{[^}]*margin:\s*0 auto 0 24px;/);
  assert.match(css, /\.assembly-final-path-export-step\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+20px;/);
  assert.match(css, /\.assembly-final-path-export-step\s*\{[^}]*width:\s*100%;/);
  assert.match(css, /\.pipeline-step-label\s*\{[^}]*white-space:\s*nowrap;/);
  assert.match(css, /\.pipeline-step-icon\s*\{[^}]*justify-self:\s*end;/);
  assert.match(css, /\.assembly-final-path-export-status\.success\s*\{[^}]*color:\s*#2c6b2f;/);
});

test("bindings commit edits from the editable empty final-path row", async () => {
  const listenerMap = new Map();
  const emptyCtgInput = {
    value: "flye_Ctg30",
    dataset: {
      finalPathEmptyCell: "ctg",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-empty-cell]") {
        return [emptyCtgInput];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {},
        finalPathViewMode: "table",
      },
    }),
  );
  const calls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.createEmptyFinalPathRow = async (_host, _store, payload) => {
    calls.push(payload);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("change")?.();

  assert.deepEqual(calls, [{ field: "ctg", value: "flye_Ctg30" }]);
});

test("bindings send final-path orient edits through updateFinalPathRow", async () => {
  const listenerMap = new Map();
  const orientSelect = {
    value: "-",
    dataset: {
      finalPathCell: "orient",
      finalPathSegmentId: "seg-1",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-cell][data-final-path-segment-id]") {
        return [orientSelect];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "hifiasm",
                ctgName: "Ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
          },
        },
        finalPathViewMode: "table",
      },
    }),
  );
  const calls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "createEmptyFinalPathRow",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.updateFinalPathRow = async (_host, _store, payload) => {
    calls.push(payload);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("change")?.();

  assert.deepEqual(calls, [{ segmentId: "seg-1", field: "orient", value: "-" }]);
});

test("bindings preserve all-mode final-path target chr on table edits", async () => {
  const listenerMap = new Map();
  const input = {
    value: "ctg-alpha",
    dataset: {
      finalPathCell: "ctg",
      finalPathSegmentId: "seg-a",
      finalPathTargetChrName: "Chr01A",
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "[data-final-path-cell][data-final-path-segment-id]") {
        return [input];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState({ assembly: { finalPathViewMode: "table" } }));
  const calls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "createEmptyFinalPathRow",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.updateFinalPathRow = async (_host, _store, payload) => {
    calls.push(payload);
  };

  bindAssemblyPageImpl(host, store, deps);
  await listenerMap.get("change")?.();

  assert.deepEqual(calls, [
    { segmentId: "seg-a", field: "ctg", value: "ctg-alpha", targetChrName: "Chr01A" },
  ]);
});

test("context menu does not expose redundant subview member-editor shortcuts", () => {
  const store = createStore(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support" },
            bottom: { contigId: 2, role: "primary" },
          },
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    memberNode: null,
    store,
    host,
  });
  assert.ok(items.every((item) => item.label !== "编辑上方 ctg 成员"));
  assert.ok(items.every((item) => item.label !== "编辑下方 ctg 成员"));
});

test("member editor modal is absent even when member-editor state is populated", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        ctgDetail: {
          assemblyCtgId: 8,
          name: "ctg-beta",
          members: [
            {
              assemblyCtgMemberId: 1001,
              assemblySeqId: 7001,
              memberOrder: 1,
              seqName: "seq_a",
              datasetName: "flye",
              sourceStart: 1,
              sourceEnd: 100,
              leftEndType: "normal",
              rightEndType: "normal",
              hidden: false,
            },
            {
              assemblyCtgMemberId: 1002,
              assemblySeqId: 7002,
              memberOrder: 2,
              seqName: "seq_b",
              datasetName: "flye",
              sourceStart: 11,
              sourceEnd: 200,
              leftEndType: "normal",
              rightEndType: "normal",
              hidden: false,
            },
          ],
        },
        memberEditorModal: {
          open: true,
          ctgId: 8,
          ctgName: "ctg-beta",
          baselineCtgName: "ctg-beta",
          rows: [
            {
              rowKey: "m-1001",
              assemblyCtgMemberId: 1001,
              assemblySeqId: 7001,
              fixedOrder: 1,
              seqName: "seq_a",
              datasetName: "flye",
              overallLen: 1000,
              sourceStart: 1,
              sourceEnd: 100,
              isNew: false,
            },
            {
              rowKey: "m-1002",
              assemblyCtgMemberId: 1002,
              assemblySeqId: 7002,
              fixedOrder: 2,
              seqName: "seq_b",
              datasetName: "flye",
              overallLen: 2000,
              sourceStart: 11,
              sourceEnd: 200,
              isNew: false,
            },
          ],
        },
      },
    }),
  );
  assert.doesNotMatch(html, /assembly-member-editor-modal/);
  assert.doesNotMatch(html, /Order/);
  assert.doesNotMatch(html, /Overall_len/);
  assert.doesNotMatch(html, /member-editor-row-list/);
  assert.doesNotMatch(html, /member-editor-ctg-name-input/);
  assert.doesNotMatch(html, /Seq ID \/ Ctg ID \/ Ctg Name/);
  assert.doesNotMatch(html, /data-member-row-key="m-1001"/);
});

test("context menu on track blank area exposes batch delete for box-selected ctgs", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const blankTarget = {
    closest() {
      return null;
    },
  };
  listenerMap.get("contextmenu")?.({
    target: blankTarget,
    clientX: 100,
    clientY: 80,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.match(menuState.innerHTML, /删除已框选 contig（2）/);
  assert.match(menuState.innerHTML, /隐藏已框选 contig（2）/);
  assert.match(menuState.innerHTML, /解除隐藏已框选 contig（2）/);
});

test("member-card ctg context menu exposes batch hide/unhide/delete for multi-selection", () => {
  const store = createStore(
    createState({
      assembly: {
        trackSelectedCtgIds: [2, 8],
      },
    }),
  );
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: { assemblyCtgId: 2, trackRole: null },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host: {},
  });

  const labels = items.map((item) => item.label);
  assert.ok(labels.includes("隐藏已框选 contig（2）"));
  assert.ok(labels.includes("解除隐藏已框选 contig（2）"));
  assert.ok(labels.includes("删除已框选 contig（2）"));
  assert.ok(!labels.includes("翻转 contig"));
  assert.ok(!labels.includes("重命名 contig..."));
  assert.ok(!labels.includes("隐藏 contig"));
  assert.ok(!labels.includes("解除隐藏 contig"));
  assert.ok(!labels.includes("删除 contig"));
  assert.ok(!labels.includes("更多 contig 操作（当前版本未接入）"));
});

test("context menu on members blank area exposes batch restore for selected deleted ctgs", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedDeletedCtgRecordIds: [9101, 9102],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const blankTarget = {
    closest() {
      return null;
    },
  };
  listenerMap.get("contextmenu")?.({
    target: blankTarget,
    clientX: 100,
    clientY: 80,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.match(menuState.innerHTML, /撤销删除已框选 contig（2）/);
});

test("context menu on a subview hit exposes left and right anchor toggles for the same hit", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(createState());
  __testBindAssemblyContextMenu(host, store);

  const hitTarget = {
    closest(selector) {
      if (selector === "[data-subview-hit-key]") {
        return {
          getAttribute(name) {
            if (name === "data-subview-hit-key") return "hit-1";
            if (name === "data-subview-hit-left-active") return "0";
            if (name === "data-subview-hit-right-active") return "1";
            return null;
          },
          classList: {
            add() {},
            remove() {},
          },
        };
      }
      if (selector === "[data-member-seq-id]") {
        return null;
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: hitTarget,
    clientX: 100,
    clientY: 80,
    preventDefault() {},
  });

  assert.match(menuState.innerHTML, /left anchor on/);
  assert.match(menuState.innerHTML, /right anchor off/);
});

test("Ctrl/Cmd + right click toggles deleted ctg selection without opening context menu", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedDeletedCtgRecordIds: [9101],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const deletedTarget = {
    closest(selector) {
      if (selector === "[data-deleted-ctg-record-id]") {
        return {
          getAttribute(name) {
            if (name === "data-deleted-ctg-record-id") return "9102";
            if (name === "data-deleted-assembly-ctg-id") return "77";
            return null;
          },
        };
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: deletedTarget,
    clientX: 40,
    clientY: 50,
    ctrlKey: true,
    metaKey: false,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.equal(menuState.innerHTML, "");
  assert.deepEqual(store.getState().assembly.selectedDeletedCtgRecordIds, [9101, 9102]);
});

test("Ctrl/Cmd + right click toggles primary member-card selection without opening context menu", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    closest() {
      return null;
    },
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(
    createState({
      assembly: {
        trackSelectedCtgIds: [2],
      },
    }),
  );
  __testBindAssemblyContextMenu(host, store);

  const preventDefaultCalls = [];
  const memberChipTarget = {
    closest(selector) {
      if (selector === ".assembly-member-chip-region [data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      if (selector === "[data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      if (selector === "[data-track-contig-id][data-track-role]") {
        return null;
      }
      if (selector === "[data-deleted-ctg-record-id]") {
        return null;
      }
      if (selector === "[data-member-seq-id]") {
        return null;
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: memberChipTarget,
    clientX: 40,
    clientY: 50,
    ctrlKey: true,
    metaKey: false,
    preventDefault() {
      preventDefaultCalls.push("called");
    },
  });

  assert.equal(preventDefaultCalls.length, 1);
  assert.equal(menuState.innerHTML, "");
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, [2, 8]);
});

test("member-chip box-selection collector returns both primary and deleted selections", () => {
  const regionEl = {
    querySelectorAll(selector) {
      if (selector === "[data-assembly-ctg-id]") {
        return [
          {
            getAttribute(name) {
              if (name === "data-assembly-ctg-id") return "2";
              return null;
            },
            offsetLeft: 10,
            offsetTop: 10,
            offsetWidth: 80,
            offsetHeight: 40,
          },
          {
            getAttribute(name) {
              if (name === "data-assembly-ctg-id") return "8";
              return null;
            },
            offsetLeft: 180,
            offsetTop: 10,
            offsetWidth: 80,
            offsetHeight: 40,
          },
        ];
      }
      if (selector === "[data-deleted-ctg-record-id]") {
        return [
          {
            getAttribute(name) {
              if (name === "data-deleted-ctg-record-id") return "9101";
              return null;
            },
            offsetLeft: 12,
            offsetTop: 80,
            offsetWidth: 80,
            offsetHeight: 40,
          },
        ];
      }
      return [];
    },
  };
  const selectionRect = {
    left: 0,
    right: 100,
    top: 0,
    bottom: 130,
  };
  const selection = __testCollectMemberChipSelectionResult(regionEl, selectionRect);
  assert.deepEqual(selection.primarySelectedCtgIds, [2]);
  assert.deepEqual(selection.deletedSelectedRecordIds, [9101]);
});

test("Delete hotkey triggers batch delete for box-selected ctgs on assembly tab", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  const deleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "DIV", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async (_host, _store, selectedIds) => {
        deleteCalls.push(selectedIds);
      },
    },
  );

  assert.equal(handled, true);
  assert.equal(event.preventDefaultCalls, 1);
  assert.deepEqual(deleteCalls, [[2, 8]]);
});

test("Delete hotkey triggers subview-local batch delete for box-selected track-pair ctgs", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairSelectedCtgs: [
            { trackRole: "support", contigId: 30 },
            { trackRole: "primary", contigId: 2 },
          ],
        },
      },
    }),
  );
  const subviewDeleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "DIV", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async () => {
        throw new Error("main-track batch delete should not run in this case");
      },
      subviewDeleteFn: async (_host, _store, selectedEntries) => {
        subviewDeleteCalls.push(selectedEntries);
      },
    },
  );

  assert.equal(handled, true);
  assert.equal(event.preventDefaultCalls, 1);
  assert.deepEqual(subviewDeleteCalls, [[
    { trackRole: "primary", contigId: 2 },
    { trackRole: "support", contigId: 30 },
  ]]);
});

test("batch deleting selected track ctgs uses local refresh instead of reloading the assembly view", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      trackSelectedCtgIds: [2, 8, 30],
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  const actionCalls = [];
  const reloadCalls = [];
  const localRefreshCalls = [];
  const hadWindow = Object.prototype.hasOwnProperty.call(globalThis, "window");
  const previousWindow = globalThis.window;
  if (!hadWindow) {
    globalThis.window = {};
  }
  let result;
  try {
    result = await __testRunBatchDeleteTrackCtgs(
      host,
      store,
      [2, 8, 30],
      {
        runAction: async (payload) => {
          actionCalls.push(payload);
          return { changed: true };
        },
        reloadView: async (_host, _store, options) => {
          reloadCalls.push(options);
        },
        refreshAfterBatchDelete: async (_host, _store, payload) => {
          localRefreshCalls.push(payload);
        },
      },
    );
  } finally {
    if (hadWindow) {
      globalThis.window = previousWindow;
    } else {
      delete globalThis.window;
    }
  }

  assert.deepEqual(actionCalls.map((item) => item.args.assemblyCtgId), [2, 8]);
  assert.equal(reloadCalls.length, 0);
  assert.equal(localRefreshCalls.length, 1);
  assert.deepEqual(localRefreshCalls[0].deletedAssemblyCtgIds, [2, 8]);
  assert.deepEqual(localRefreshCalls[0].attemptedAssemblyCtgIds, [2, 8]);
  assert.equal(result.deletedCount, 2);
  assert.deepEqual(store.getState().assembly.trackSelectedCtgIds, []);
});

test("batch restoring selected deleted ctgs reloads view once after all actions", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      selectedDeletedCtgRecordIds: [9101, 9102],
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  const actionCalls = [];
  const reloadCalls = [];
  const hadWindow = Object.prototype.hasOwnProperty.call(globalThis, "window");
  const previousWindow = globalThis.window;
  if (!hadWindow) {
    globalThis.window = {};
  }
  let result;
  try {
    result = await __testRunBatchRestoreDeletedCtgs(
      host,
      store,
      [9101, 9102],
      {
        runAction: async (payload) => {
          actionCalls.push(payload);
          return { restored: true };
        },
        reloadView: async (_host, _store, options) => {
          reloadCalls.push(options);
        },
      },
    );
  } finally {
    if (hadWindow) {
      globalThis.window = previousWindow;
    } else {
      delete globalThis.window;
    }
  }

  assert.deepEqual(actionCalls.map((item) => item.args.deletedCtgRecordId), [9101, 9102]);
  assert.equal(reloadCalls.length, 1);
  assert.deepEqual(reloadCalls[0], {
    keepCurrentChr: true,
    keepCurrentCtg: true,
    renderLoading: false,
  });
  assert.equal(result.restoredCount, 2);
  assert.deepEqual(store.getState().assembly.selectedDeletedCtgRecordIds, []);
});

test("restoring selected deleted ctgs does not require confirm dialog", async () => {
  const host = {
    closest() {
      return null;
    },
  };
  const store = createStore(
    createState({
      assembly: {
        selectedDeletedCtgRecordIds: [9101],
      },
    }),
  );
  const actionCalls = [];
  const reloadCalls = [];
  const hadWindow = Object.prototype.hasOwnProperty.call(globalThis, "window");
  const previousWindow = globalThis.window;
  globalThis.window = {
    ...(hadWindow && previousWindow ? previousWindow : {}),
    confirm() {
      throw new Error("confirm should not be called when restoring deleted contigs");
    },
  };
  try {
    await __testRestoreSelectedDeletedCtgs(host, store, [9101], {
      runAction: async (payload) => {
        actionCalls.push(payload);
        return { restored: true };
      },
      reloadView: async (_host, _store, options) => {
        reloadCalls.push(options);
      },
    });
  } finally {
    if (hadWindow) {
      globalThis.window = previousWindow;
    } else {
      delete globalThis.window;
    }
  }

  assert.deepEqual(actionCalls.map((item) => item.args.deletedCtgRecordId), [9101]);
  assert.equal(reloadCalls.length, 1);
});

test("Delete hotkey is ignored while typing in input fields", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  const deleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "INPUT", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async (_host, _store, selectedIds) => {
        deleteCalls.push(selectedIds);
      },
    },
  );

  assert.equal(handled, false);
  assert.equal(event.preventDefaultCalls, 0);
  assert.deepEqual(deleteCalls, []);
});

test("Delete hotkey still works when last focused element is a button", async () => {
  const store = createStore(
    createState({
      assembly: {
        activeTab: "assembly",
        trackSelectedCtgIds: [2, 8, 30],
      },
    }),
  );
  const deleteCalls = [];
  const event = {
    key: "Delete",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    target: { tagName: "BUTTON", isContentEditable: false },
    preventDefaultCalls: 0,
    preventDefault() {
      this.preventDefaultCalls += 1;
    },
  };

  const handled = await __testHandleTrackDeleteHotkey(
    {},
    store,
    event,
    {
      deleteFn: async (_host, _store, selectedIds) => {
        deleteCalls.push(selectedIds);
      },
    },
  );

  assert.equal(handled, true);
  assert.equal(event.preventDefaultCalls, 1);
  assert.deepEqual(deleteCalls, [[2, 8]]);
});

test("context menu on member row exposes retained sequence actions only", () => {
  const listenerMap = new Map();
  const menuState = {
    classList: {
      add() {},
      remove() {},
    },
    style: {},
    innerHTML: "",
    querySelectorAll() {
      return [];
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return menuState;
      }
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const store = createStore(createState());
  __testBindAssemblyContextMenu(host, store);

  const memberTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return null;
      }
      if (selector === "[data-assembly-ctg-id]") {
        return null;
      }
      if (selector === "[data-member-seq-id]") {
        return {
          getAttribute(name) {
            if (name === "data-member-seq-id") return "101";
            if (name === "data-member-hidden") return "0";
            if (name === "data-member-id") return "401";
            return null;
          },
        };
      }
      return null;
    },
  };

  listenerMap.get("contextmenu")?.({
    target: memberTarget,
    clientX: 24,
    clientY: 16,
    preventDefault() {},
  });

  assert.ok(menuState.innerHTML.indexOf("对齐详情（当前版本未接入）") < menuState.innerHTML.indexOf("定位 Seq 101"));
  assert.ok(menuState.innerHTML.indexOf("定位 Seq 101") < menuState.innerHTML.indexOf("翻转 sequence"));
  assert.ok(menuState.innerHTML.indexOf("翻转 sequence") < menuState.innerHTML.indexOf("隐藏 sequence"));
  assert.match(menuState.innerHTML, /定位 Seq 101/);
  assert.match(menuState.innerHTML, /对齐详情（当前版本未接入）/);
  assert.match(menuState.innerHTML, /锚点联动（当前版本未接入）/);
  assert.match(menuState.innerHTML, /翻转 sequence/);
  assert.match(menuState.innerHTML, /隐藏 sequence/);
  assert.doesNotMatch(menuState.innerHTML, /设置区间/);
  assert.doesNotMatch(menuState.innerHTML, /从当前 contig 移除/);
  assert.doesNotMatch(menuState.innerHTML, /在此 member 后拆分/);
  assert.match(menuState.innerHTML, /当前版本未接入/);
  assert.match(menuState.innerHTML, /disabled/);
});

test("context target resolver prefers track glyph metadata and falls back to legacy ctg nodes", () => {
  const trackTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return {
          getAttribute(name) {
            if (name === "data-track-contig-id") return "30";
            if (name === "data-track-role") return "support";
            return null;
          },
        };
      }
      if (selector === "[data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      return null;
    },
  };
  const legacyTarget = {
    closest(selector) {
      if (selector === "[data-track-contig-id][data-track-role]") {
        return null;
      }
      if (selector === "[data-assembly-ctg-id]") {
        return {
          getAttribute(name) {
            if (name === "data-assembly-ctg-id") return "8";
            return null;
          },
        };
      }
      return null;
    },
  };

  assert.deepEqual(__testResolveAssemblyCtgContextTarget(trackTarget), {
    assemblyCtgId: 30,
    trackRole: "support",
    isMirror: false,
    datasetId: null,
  });
  assert.deepEqual(__testResolveAssemblyCtgContextTarget(legacyTarget), {
    assemblyCtgId: 8,
    trackRole: null,
    isMirror: false,
    datasetId: null,
  });
});

test("action feedback toast auto-dismisses after 1 second", () => {
  const timerApi = createFakeTimerApi();
  let dismissCount = 0;
  const coordinator = __testCreateActionFeedbackDismissCoordinator({
    setTimeoutFn: timerApi.setTimeout,
    clearTimeoutFn: timerApi.clearTimeout,
    onDismiss: () => {
      dismissCount += 1;
    },
  });
  const signature = __testGetAssemblyActionFeedbackSignature({
    actionStatus: "move-ctg 完成（changed=true）。",
    actionError: "",
  });

  coordinator.onFeedbackChange(signature);
  timerApi.advance(999);
  assert.equal(dismissCount, 0);
  timerApi.advance(1);
  assert.equal(dismissCount, 1);
});

test("action feedback toast dismisses 0.5 second after pointer move", () => {
  const timerApi = createFakeTimerApi();
  let dismissCount = 0;
  const coordinator = __testCreateActionFeedbackDismissCoordinator({
    setTimeoutFn: timerApi.setTimeout,
    clearTimeoutFn: timerApi.clearTimeout,
    onDismiss: () => {
      dismissCount += 1;
    },
  });
  const signature = __testGetAssemblyActionFeedbackSignature({
    actionStatus: "move-ctg 完成（changed=true）。",
    actionError: "",
  });

  coordinator.onFeedbackChange(signature);
  timerApi.advance(200);
  coordinator.onPointerMove(signature);
  timerApi.advance(499);
  assert.equal(dismissCount, 0);
  timerApi.advance(1);
  assert.equal(dismissCount, 1);
  timerApi.advance(1000);
  assert.equal(dismissCount, 1);
});

test("subview band tooltip coordinator waits 500ms before showing and hides on leave", () => {
  const timerApi = createFakeTimerApi();
  const calls = [];
  const coordinator = __testCreateSubviewBandTooltipCoordinator({
    setTimeoutFn: timerApi.setTimeout,
    clearTimeoutFn: timerApi.clearTimeout,
    onShow: (context) => {
      calls.push(["show", context.text, context.point.x, context.point.y]);
    },
    onMove: (context) => {
      calls.push(["move", context.text, context.point.x, context.point.y]);
    },
    onHide: () => {
      calls.push(["hide"]);
    },
  });

  const token = { id: "band-1" };
  coordinator.enter({
    token,
    text: "support-top: 2,200-3,400 bp",
    point: { x: 100, y: 120 },
  });
  timerApi.advance(499);
  assert.deepEqual(calls, []);
  coordinator.move({
    token,
    text: "support-top: 2,200-3,400 bp",
    point: { x: 140, y: 160 },
  });
  timerApi.advance(1);
  assert.deepEqual(calls, [["show", "support-top: 2,200-3,400 bp", 140, 160]]);

  coordinator.move({
    token,
    text: "support-top: 2,200-3,400 bp",
    point: { x: 170, y: 180 },
  });
  assert.deepEqual(calls[1], ["move", "support-top: 2,200-3,400 bp", 170, 180]);

  coordinator.leave(token);
  assert.deepEqual(calls[2], ["hide"]);
});

test("track viewport resize coordinator rerenders only when viewport width meaningfully changes", () => {
  let measuredWidth = 1200;
  let viewportWidth = 1200;
  const rerenderWidths = [];
  const coordinator = __testCreateTrackViewportResizeCoordinator({
    getViewportWidth: () => viewportWidth,
    getMeasuredWidth: () => measuredWidth,
    setMeasuredWidth: (nextWidth) => {
      measuredWidth = nextWidth;
    },
    onViewportResize: (nextWidth) => {
      rerenderWidths.push(nextWidth);
    },
  });

  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, []);

  viewportWidth = 1201;
  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, []);

  viewportWidth = 1460;
  assert.equal(coordinator.onResize(), true);
  assert.equal(measuredWidth, 1460);
  assert.deepEqual(rerenderWidths, [1460]);

  viewportWidth = 1460;
  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, [1460]);

  viewportWidth = 0;
  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, [1460]);
});

test("track viewport resize coordinator rerenders when subview or final-path viewport width changes even if primary is stable", () => {
  let measuredWidths = {
    primary: 1200,
    subview: 1200,
    finalPath: 1200,
  };
  let viewportWidths = {
    primary: 1200,
    subview: 1200,
    finalPath: 1200,
  };
  const rerenderWidths = [];
  const coordinator = __testCreateTrackViewportResizeCoordinator({
    getViewportWidths: () => viewportWidths,
    getMeasuredWidths: () => measuredWidths,
    setMeasuredWidths: (nextWidths) => {
      measuredWidths = nextWidths;
    },
    onViewportResize: (nextWidths) => {
      rerenderWidths.push(nextWidths);
    },
  });

  assert.equal(coordinator.onResize(), false);
  assert.deepEqual(rerenderWidths, []);

  viewportWidths = {
    primary: 1200,
    subview: 1180,
    finalPath: 1200,
  };
  assert.equal(coordinator.onResize(), true);
  assert.deepEqual(measuredWidths, {
    primary: 1200,
    subview: 1180,
    finalPath: 1200,
  });
  assert.deepEqual(rerenderWidths, [{
    primary: 1200,
    subview: 1180,
    finalPath: 1200,
  }]);

  viewportWidths = {
    primary: 1200,
    subview: 1180,
    finalPath: 1176,
  };
  assert.equal(coordinator.onResize(), true);
  assert.deepEqual(measuredWidths, {
    primary: 1200,
    subview: 1180,
    finalPath: 1176,
  });
});

test("support-ds change clears subview state and loads support chr ctgs for the selected chr", async () => {
  const store = createStore(
    createState({
      assembly: {
        supportDatasetId: 22,
        selectedChrName: "Chr01",
        summary: "旧摘要",
        supportChrCtgs: [{ assemblyCtgId: 99, name: "stale" }],
        subviewTrackDragOffsets: [
          { slot: "top", contigId: 2, offsetPx: 50 },
          { slot: "bottom", contigId: 30, offsetPx: -20 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "旧消息",
          error: "旧错误",
          summary: { mode: "2-contig" },
        },
      },
    }),
  );
  const loadCalls = [];
  const loadedSupportCtgs = [
    { assemblyCtgId: 31, name: "support-ctg-2", assignedChrName: "Chr01", memberCount: 1, totalLength: 450, anchorStart: 360 },
  ];

  await __testApplySupportDatasetSelection(store, 33, {
    loadSupportChrCtgs: async (workspaceRoot, projectId, chrName, datasetId) => {
      loadCalls.push({ workspaceRoot, projectId, chrName, datasetId });
      return loadedSupportCtgs;
    },
    rerenderView: () => {},
  });

  assert.deepEqual(loadCalls, [
    {
      workspaceRoot: "/tmp/workspace",
      projectId: 7,
      chrName: "Chr01",
      datasetId: 33,
    },
  ]);
  assert.equal(store.getState().assembly.supportDatasetId, 33);
  assert.deepEqual(store.getState().assembly.supportChrCtgs, loadedSupportCtgs);
  assert.deepEqual(store.getState().assembly.subviewTrackDragOffsets, []);
  assert.equal(store.getState().assembly.summary, "");
  assert.deepEqual(store.getState().assembly.subview, {
    mode: "2-contig",
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
    activeAnchors: [],
    manualAnchors: [],
    flippedCtgs: [],
    trackPairHiddenCtgs: [],
    trackPairSelectedCtgs: [],
    message: "",
    error: "",
    summary: null,
  });
});

test("context-menu listeners install only once for the route host", () => {
  const listenerTypes = [];
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-context-menu") {
        return {
          classList: { add() {}, remove() {} },
          style: {},
          innerHTML: "",
          querySelectorAll() {
            return [];
          },
        };
      }
      return null;
    },
    addEventListener(type) {
      listenerTypes.push(type);
    },
  };

  __testBindAssemblyContextMenu(host, createStore(createState()));
  __testBindAssemblyContextMenu(host, createStore(createState()));

  assert.deepEqual(listenerTypes, ["click", "scroll", "contextmenu"]);
});

test("bindings binder rejects missing required deps at the boundary", () => {
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());

  assert.throws(
    () => bindAssemblyPageImpl(host, store, {}),
    /Missing assembly binding deps:/,
  );
});

test("bindings persist main-track view changes after committing a main control input", () => {
  const listenerMap = new Map();
  const input = {
    value: "500",
    closest() {
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-track-min-tick-unit-kb") {
        return input;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const persisted = [];
  const store = createStore(
    createState({
      session: { workspacePath: "/tmp/ws", projectId: 7 },
      assembly: {
        trackView: {
          supportDsCtgLen: 0,
          minTickUnitKb: 250,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
      },
    }),
  );
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async (_host, currentStore) => {
    persisted.push(currentStore.getState().assembly.trackView);
  };

  bindAssemblyPageImpl(host, store, deps);
  listenerMap.get("change")?.();

  assert.deepEqual(store.getState().assembly.trackView, {
    supportDsCtgLen: 0,
    supportDsCtgLenBp: 0,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 10,
    viewSpanKb: 500,
    pixelUnit: 500,
    tickLength: 10000,
    tickBp: 10000,
    alignmentLength: 1000,
    block_length: 1000,
    mapq: 0,
  });
  assert.deepEqual(persisted, [
    {
      supportDsCtgLen: 0,
      supportDsCtgLenBp: 0,
      minTickUnitKb: 500,
      minTickKb: 500,
      maxTickCount: 10,
      viewSpanKb: 500,
      pixelUnit: 500,
      tickLength: 10000,
      tickBp: 10000,
      alignmentLength: 1000,
      block_length: 1000,
      mapq: 0,
    },
  ]);
});

test("bindings switch the final path card between graph and table modes and persist the choice", async () => {
  const tableListeners = new Map();
  const tableButton = {
    dataset: {
      finalPathViewMode: "table",
    },
    addEventListener(type, handler) {
      tableListeners.set(type, handler);
    },
  };
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "button[data-final-path-view-mode]") {
        return [tableButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "flye_ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );
  let rerenderCount = 0;
  const persistCalls = [];
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.rerender = () => {
    rerenderCount += 1;
  };
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async (_host, currentStore) => {
    persistCalls.push({
      finalPathViewMode: currentStore.getState().assembly.finalPathViewMode,
    });
  };

  bindAssemblyPageImpl(host, store, deps);
  await tableListeners.get("click")?.({
    preventDefault() {},
  });

  assert.equal(store.getState().assembly.finalPathViewMode, "table");
  assert.equal(rerenderCount, 1);
  assert.deepEqual(persistCalls, [{ finalPathViewMode: "table" }]);
});

test("bindings keep the switched final-path table fully visible when it fits in the viewport", () => {
  const tableListeners = new Map();
  const tableButton = {
    dataset: {
      finalPathViewMode: "table",
    },
    addEventListener(type, handler) {
      tableListeners.set(type, handler);
    },
  };
  let rerenderCount = 0;
  const graphCard = {
    getBoundingClientRect() {
      return {
        top: 520,
        bottom: 920,
        height: 400,
      };
    },
  };
  const tableCard = {
    getBoundingClientRect() {
      return {
        top: 520,
        bottom: 1040,
        height: 520,
      };
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".final-path-card") {
        return rerenderCount > 0 ? tableCard : graphCard;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "button[data-final-path-view-mode]") {
        return [tableButton];
      }
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                ctgName: "flye_ctg9",
                totalLength: 1200,
              },
            ],
            totalLength: 1200,
            updatedAt: "1",
          },
        },
        finalPathViewMode: "graph",
      },
    }),
  );
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.rerender = () => {
    rerenderCount += 1;
  };
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });

  const originalWindow = globalThis.window;
  const scrollCalls = [];
  globalThis.window = {
    innerHeight: 1000,
    scrollBy(options) {
      scrollCalls.push(options);
    },
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    tableListeners.get("click")?.({
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(store.getState().assembly.finalPathViewMode, "table");
  assert.equal(rerenderCount, 1);
  assert.deepEqual(scrollCalls, [{ left: 0, top: 56, behavior: "auto" }]);
});

test("bindings open track combo upward when the dropdown would overflow the window bottom", () => {
  const toggleListeners = new Map();
  const menuNode = {
    style: {},
    classList: {
      toggle() {},
    },
    getBoundingClientRect() {
      return {
        height: 220,
      };
    },
  };
  const comboNode = {
    classList: {
      values: new Set(),
      toggle(name, enabled) {
        if (enabled) {
          this.values.add(name);
        } else {
          this.values.delete(name);
        }
      },
      contains(name) {
        return this.values.has(name);
      },
    },
    querySelector(selector) {
      if (selector === ".assembly-track-combo-input") {
        return input;
      }
      if (selector === "[data-track-combo-toggle]") {
        return toggleButton;
      }
      if (selector === ".assembly-track-combo-menu") {
        return menuNode;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    getBoundingClientRect() {
      return {
        top: 860,
        bottom: 892,
        height: 32,
      };
    },
    contains() {
      return false;
    },
  };
  const input = {
    value: "10000",
    closest(selector) {
      return selector === "[data-track-combo-field]" ? comboNode : null;
    },
    addEventListener() {},
    focus() {},
    setAttribute() {},
  };
  const toggleButton = {
    addEventListener(type, handler) {
      toggleListeners.set(type, handler);
    },
    setAttribute() {},
  };
  const host = {
    querySelector(selector) {
      if (selector === "#assembly-track-min-tick-unit-kb") {
        return input;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  const store = createStore(createState());
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "rerender",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });

  const originalWindow = globalThis.window;
  globalThis.window = {
    innerHeight: 900,
    setTimeout,
    clearTimeout,
    addEventListener() {},
    removeEventListener() {},
  };

  try {
    bindAssemblyPageImpl(host, store, deps);
    toggleListeners.get("click")?.({
      preventDefault() {},
    });
  } finally {
    globalThis.window = originalWindow;
  }

  assert.equal(comboNode.classList.contains("is-open"), true);
  assert.equal(menuNode.style.top, "auto");
  assert.equal(menuNode.style.bottom, "calc(100% + 2px)");
});

test("bindings update final-path track prefs without persisting main-track view state", () => {
  const listenerMap = new Map();
  const input = {
    value: "500",
    closest() {
      return null;
    },
    addEventListener(type, handler) {
      listenerMap.set(type, handler);
    },
  };
  const finalPathScroll = {
    scrollLeft: 640,
  };
  const host = {
    querySelector(selector) {
      if (selector === "#final-path-track-min-tick-unit-kb") {
        return input;
      }
      if (selector === "[data-final-path-graph-viewport]" || selector === ".assembly-final-path-svg-wrap") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  let persistedCount = 0;
  let rerenderCount = 0;
  let rememberedCount = 0;
  let suppressCount = 0;
  const store = createStore(
    createState({
      assembly: {
        finalPathByChr: {
          Chr01: {
            mode: "segments",
            chrName: "Chr01",
            segments: [
              {
                segmentId: "seg-1",
                type: "ctg",
                assemblyCtgId: 9,
                datasetName: "",
                ctgName: "flye_ctg9",
                overallLen: 1200,
                start: 1,
                end: 1200,
              },
            ],
            updatedAt: "1",
          },
        },
        finalPathTrackView: {
          minTickUnitKb: 250,
          maxTickCount: 10,
        },
      },
    }),
  );
  const deps = Object.fromEntries([
    "appendFinalPathRow",
    "applySupportDatasetSelection",
    "bindBandCanvasRuntime",
    "cancelSubviewPairwiseEvidence",
    "bindAssemblyActionFeedbackDismiss",
    "bindAssemblyContextMenu",
    "bindCtgActions",
    "bindDeletedMemberChipBoxSelection",
    "bindSeqActions",
    "bindStickyCtgLabels",
    "bindSubviewBandTooltips",
    "bindSubviewTrackContigDrag",
    "bindTrackBoxSelection",
    "bindTrackContigDrag",
    "bindTrackScrollSync",
    "bindTrackSelectionHotkeys",
    "bindTrackViewportResize",
    "handleNewSequenceRowAction",
    "handleSubviewCandidateRemoval",
    "handleSubviewSwapTrackOrder",
    "handleSubviewTrackSelectionRemoval",
    "handleTrackSubviewCandidateSelection",
    "handleTrackSubviewTrackSelection",
    "loadAssemblyView",
    "loadNewSequencesTab",
    "markNextTrackAutoFocusSuppressed",
    "persistMainTrackViewState",
    "rememberTrackViewportAnchor",
    "normalizeTrackFocusMode",
    "resolveTrackContigClickAction",
    "removeFinalPathRow",
    "restoreSelectedDeletedCtgs",
    "runCtgSearch",
    "selectChromosome",
    "selectCtg",
    "setAssemblyActionFeedback",
    "shouldSuppressTrackContigClick",
    "syncSupportDatasetSelection",
    "togglePrimaryTrackSelection",
    "moveFinalPathRow",
    "updateFinalPathRow",
    "updateDeletedCtgSelection",
  ].map((name) => [name, () => {}]));
  deps.syncSupportDatasetSelection = () => ({ changed: false, supportDatasetId: null });
  deps.persistMainTrackViewState = async () => {
    persistedCount += 1;
  };
  deps.rerender = () => {
    rerenderCount += 1;
  };
  deps.rememberTrackViewportAnchor = () => {
    rememberedCount += 1;
  };
  deps.markNextTrackAutoFocusSuppressed = () => {
    suppressCount += 1;
  };

  bindAssemblyPageImpl(host, store, deps);
  listenerMap.get("change")?.();

  assert.deepEqual(store.getState().assembly.finalPathTrackView, {
    supportDsCtgLen: 0,
    supportDsCtgLenBp: 0,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 10,
    viewSpanKb: 500,
    pixelUnit: 500,
    tickLength: 10000,
    tickBp: 10000,
    alignmentLength: 10000,
    block_length: 10000,
    mapq: 0,
  });
  assert.deepEqual(store.getState().assembly.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:500:10",
    scrollLeft: 640,
  });
  assert.equal(persistedCount, 0);
  assert.equal(rememberedCount, 0);
  assert.equal(suppressCount, 0);
  assert.equal(rerenderCount, 1);
});

test("track scroll sync restores and persists project-scoped main and subview scroll positions", () => {
  __testResetMeasuredTrackViewportWidths();
  const mainListeners = new Map();
  const subviewListeners = new Map();
  const finalPathScroll = {
    clientWidth: 1200,
  };
  const mainScroll = {
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
      focusCenter: "120",
      focusStart: "40",
    },
    clientWidth: 1200,
    scrollLeft: 0,
    addEventListener(type, handler) {
      mainListeners.set(type, handler);
    },
  };
  const subviewScroll = {
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
    clientWidth: 360,
    scrollLeft: 0,
    addEventListener(type, handler) {
      subviewListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return mainScroll;
      }
      if (selector === ".assembly-track-scroll.subview-track-scroll") {
        return subviewScroll;
      }
      if (selector === ".assembly-final-path-svg-wrap") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role]") {
        return [mainScroll, subviewScroll];
      }
      return [];
    },
  };
  const persisted = [];
  const store = createStore(
    createState({
      session: { projectId: 7 },
      assembly: {
        selectedChrName: "Chr01",
        selectedCtgId: 8,
        supportDatasetId: 22,
        trackView: {
          supportDsCtgLen: 10000,
          minTickUnitKb: 250,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        trackScrollState: {
          viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
          scrollLeft: 320,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 1909,
          selectedBRole: "support",
          selectedTrackARole: "",
          selectedTrackBRole: "",
          trackPairHiddenCtgs: [],
          trackPairSelectedCtgs: [],
          message: "",
          error: "",
          summary: {
            top: { role: "primary", contigId: 8 },
            bottom: { role: "support", contigId: 1909 },
          },
        },
        subviewTrackScrollState: {
          viewportKey: "7:Chr01:primary:8:support:1909",
          scrollLeft: 180,
        },
      },
    }),
  );

  __testBindTrackScrollSync(host, store, {
    schedulePersistAssemblyScrollState(_host, currentStore) {
      persisted.push({
        trackScrollState: currentStore.getState().assembly.trackScrollState,
        subviewTrackScrollState: currentStore.getState().assembly.subviewTrackScrollState,
      });
    },
  });

  assert.equal(mainScroll.scrollLeft, 320);
  assert.equal(subviewScroll.scrollLeft, 180);

  mainScroll.scrollLeft = 460;
  mainListeners.get("scroll")?.();
  assert.deepEqual(store.getState().assembly.trackScrollState, {
    viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
    scrollLeft: 460,
  });

  subviewScroll.scrollLeft = 210;
  subviewListeners.get("scroll")?.();
  assert.deepEqual(store.getState().assembly.subviewTrackScrollState, {
    viewportKey: "7:Chr01:primary:8:support:1909",
    scrollLeft: 210,
  });
  assert.deepEqual(persisted.slice(-2), [
    {
      trackScrollState: {
        viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
        scrollLeft: 460,
      },
      subviewTrackScrollState: {
        viewportKey: "7:Chr01:primary:8:support:1909",
        scrollLeft: 180,
      },
    },
    {
      trackScrollState: {
        viewportKey: "7:Chr01:8:22:10000:250:10:1000:0",
        scrollLeft: 460,
      },
      subviewTrackScrollState: {
        viewportKey: "7:Chr01:primary:8:support:1909",
        scrollLeft: 210,
      },
    },
  ]);
  __testResetMeasuredTrackViewportWidths();
});

test("track scroll sync restores and persists project-scoped final-path scroll positions", () => {
  __testResetMeasuredTrackViewportWidths();
  const mainListeners = new Map();
  const subviewListeners = new Map();
  const finalPathListeners = new Map();
  const mainScroll = {
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
      focusCenter: "120",
      focusStart: "40",
    },
    clientWidth: 1200,
    scrollLeft: 0,
    addEventListener(type, handler) {
      mainListeners.set(type, handler);
    },
  };
  const subviewScroll = {
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
    clientWidth: 360,
    scrollLeft: 0,
    addEventListener(type, handler) {
      subviewListeners.set(type, handler);
    },
  };
  const finalPathScroll = {
    clientWidth: 900,
    scrollLeft: 0,
    addEventListener(type, handler) {
      finalPathListeners.set(type, handler);
    },
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return mainScroll;
      }
      if (selector === ".assembly-track-scroll.subview-track-scroll") {
        return subviewScroll;
      }
      if (selector === ".assembly-final-path-svg-wrap" || selector === "[data-final-path-graph-viewport]") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role]") {
        return [mainScroll, subviewScroll];
      }
      return [];
    },
  };
  const persisted = [];
  const store = createStore(
    createState({
      assembly: {
        selectedChrName: "Chr01",
        selectedCtgId: 8,
        supportDatasetId: 22,
        finalPathViewMode: "graph",
        finalPathTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
        },
        finalPathTrackScrollState: {
          viewportKey: "7:Chr01:graph:10000:10",
          scrollLeft: 480,
        },
      },
    }),
  );

  __testBindTrackScrollSync(host, store, {
    schedulePersistAssemblyScrollState(_host, currentStore) {
      persisted.push(currentStore.getState().assembly.finalPathTrackScrollState);
    },
  });

  assert.equal(finalPathScroll.scrollLeft, 480);

  finalPathScroll.scrollLeft = 620;
  finalPathListeners.get("scroll")?.();

  assert.deepEqual(store.getState().assembly.finalPathTrackScrollState, {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 620,
  });
  assert.deepEqual(persisted.at(-1), {
    viewportKey: "7:Chr01:graph:10000:10",
    scrollLeft: 620,
  });
  __testResetMeasuredTrackViewportWidths();
});

test("track scroll sync requests a rerender when subview viewport width differs from the measured main-view width", () => {
  __testResetMeasuredTrackViewportWidths();
  const mainScroll = {
    dataset: {
      trackRole: "primary",
      trackViewboxMinX: "0",
      focusCenter: "120",
      focusStart: "40",
    },
    clientWidth: 1200,
    scrollLeft: 0,
    addEventListener() {},
  };
  const subviewScroll = {
    dataset: {
      trackRole: "subview",
      subviewViewboxMinX: "0",
    },
    clientWidth: 360,
    scrollLeft: 0,
    addEventListener() {},
  };
  const finalPathScroll = {
    clientWidth: 1200,
  };
  const host = {
    querySelector(selector) {
      if (selector === ".assembly-track-scroll[data-track-role='primary']") {
        return mainScroll;
      }
      if (selector === ".assembly-track-scroll.subview-track-scroll") {
        return subviewScroll;
      }
      if (selector === ".assembly-final-path-svg-wrap") {
        return finalPathScroll;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".assembly-track-scroll[data-track-role]") {
        return [mainScroll, subviewScroll];
      }
      return [];
    },
  };
  const store = createStore(createState());

  assert.equal(__testBindTrackScrollSync(host, store, {
    schedulePersistAssemblyScrollState() {},
  }), true);
  __testResetMeasuredTrackViewportWidths();
});

test("editor action adapter factory forwards shared runtime deps consistently", async () => {
  const runtimeDeps = { marker: "editor-runtime" };
  const calls = [];
  const adapters = __testCreateEditorActionRuntimeAdapters(runtimeDeps, {
    applyEditorAction(host, store, payload, deps) {
      calls.push({ type: "apply", payload, deps });
      return "apply-ok";
    },
    deleteSelectedTrackCtgs(host, store, selectedIds, deps) {
      calls.push({ type: "delete-track", selectedIds, deps });
      return "delete-track-ok";
    },
    deleteSelectedSubviewTrackPairCtgs(host, store, selectedEntries, deps) {
      calls.push({ type: "delete-subview", selectedEntries, deps });
      return "delete-subview-ok";
    },
    restoreSelectedDeletedCtgs(host, store, selectedRecordIds, deps, options) {
      calls.push({ type: "restore", selectedRecordIds, deps, options });
      return "restore-ok";
    },
    runBatchDeleteTrackCtgs(host, store, selectedIds, deps, options) {
      calls.push({ type: "batch-delete", selectedIds, deps, options });
      return "batch-delete-ok";
    },
    runBatchRestoreDeletedCtgs(host, store, selectedRecordIds, deps, options) {
      calls.push({ type: "batch-restore", selectedRecordIds, deps, options });
      return "batch-restore-ok";
    },
  });

  assert.equal(await adapters.applyEditorAction({}, {}, { kind: "join" }), "apply-ok");
  assert.equal(await adapters.deleteSelectedTrackCtgs({}, {}, [7, 8]), "delete-track-ok");
  assert.equal(
    await adapters.deleteSelectedSubviewTrackPairCtgs({}, {}, [{ trackRole: "support", contigId: 9 }]),
    "delete-subview-ok",
  );
  assert.equal(await adapters.restoreSelectedDeletedCtgs({}, {}, [11], { silent: true }), "restore-ok");
  assert.equal(await adapters.runBatchDeleteTrackCtgs({}, {}, [15], { skipReload: true }), "batch-delete-ok");
  assert.equal(
    await adapters.runBatchRestoreDeletedCtgs({}, {}, [19], { suppressFeedback: true }),
    "batch-restore-ok",
  );

  assert.equal(calls[0].deps, runtimeDeps);
  assert.equal(calls[1].deps.marker, "editor-runtime");
  assert.equal(typeof calls[1].deps.runBatchDeleteTrackCtgs, "function");
  assert.equal(calls[1].deps.localRefresh, true);
  assert.notEqual(calls[1].deps, runtimeDeps);
  assert.equal(calls[2].deps, runtimeDeps);
  assert.equal(calls[3].deps.marker, "editor-runtime");
  assert.equal(typeof calls[3].deps.runBatchRestoreDeletedCtgs, "function");
  assert.equal(calls[3].deps.localRefresh, true);
  assert.notEqual(calls[3].deps, runtimeDeps);
  assert.equal(calls[4].deps.marker, "editor-runtime");
  assert.equal(calls[4].deps.localRefresh, true);
  assert.notEqual(calls[4].deps, runtimeDeps);
  assert.deepEqual(calls[4].options, { skipReload: true });
  assert.equal(calls[5].deps.marker, "editor-runtime");
  assert.equal(calls[5].deps.localRefresh, true);
  assert.notEqual(calls[5].deps, runtimeDeps);
  assert.deepEqual(calls[5].options, { suppressFeedback: true });
});

test("assembly page public binder wires host-level listeners once for the same host", () => {
  const listenerTypes = [];
  const host = {
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener(type) {
      listenerTypes.push(type);
    },
  };
  const store = createStore(
    createState({
      initializer: {
        datasets: [],
      },
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 2, placedBp: 3300 }],
      },
    }),
  );
  const originalWindow = globalThis.window;
  globalThis.window = {
    addEventListener() {},
    removeEventListener() {},
    setTimeout,
    clearTimeout,
    print() {},
  };

  try {
    bindAssemblyPage(host, store);
    bindAssemblyPage(host, store);
  } finally {
    globalThis.window = originalWindow;
  }

  assert.deepEqual(listenerTypes, [
    "pointerdown",
    "pointermove",
    "pointerdown",
    "pointerdown",
    "click",
    "pointerover",
    "pointerout",
    "contextmenu",
    "click",
    "change",
    "pointerover",
    "pointerout",
    "click",
    "scroll",
    "contextmenu",
    "pointerdown",
    "pointerdown",
    "pointerdown",
    "pointerdown",
  ]);
});

test("assembly main view renders chr-length reference span, all guides, sparse ruler labels, and hit-filtered bands", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 5,
            name: "ctg-zeta",
            assignedChrName: "Chr01",
            memberCount: 3,
            totalLength: 800,
            anchorStart: 900,
          },
          {
            assemblyCtgId: 2,
            name: "ctg-alpha",
            assignedChrName: "Chr01",
            memberCount: 5,
            totalLength: 900,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 8,
            name: "ctg-beta",
            assignedChrName: "Chr01",
            memberCount: 2,
            totalLength: 999,
            anchorStart: 500,
            hits: [
              {
                ctgStart: 120,
                ctgEnd: 620,
                refStart: 1000,
                refEnd: 1500,
                blockLength: 500,
              },
              {
                ctgStart: 80,
                ctgEnd: 780,
                refStart: 250000,
                refEnd: 250700,
                blockLength: 1000,
              },
            ],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 3, placedBp: 3300, chrLength: 5000000 }],
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 700, anchorStart: 320 },
        ],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const mainTrackSvg = html.match(/<svg[\s\S]*?<\/svg>/)?.[0] || "";
  const tickGuideCount = (mainTrackSvg.match(/track-tick-guide/g) || []).length;
  const tickLabelCount = (mainTrackSvg.match(/track-tick-label/g) || []).length;
  const bandCount = (html.match(/track-collinearity-band/g) || []).length;

  assert.match(html, /data-ref-span-bp="5000000"/);
  assert.match(html, /class="track-band-canvas-layer"[^>]*data-track-band-canvas-scene-kind="main-track"/);
  assert.match(html, /<canvas class="track-band-canvas"[^>]*data-track-band-canvas="1"/);
  assert.match(html, /<rect[\s\S]*class="track-reference-bar"[\s\S]*rx="0"[\s\S]*ry="0"/);
  assert.match(html, /track-collinearity-band[^>]*data-track-band-proxy="1"/);
  assert.equal(tickGuideCount, tickLabelCount + 1);
  assert.equal(tickLabelCount, 20);
  assert.match(html, /<text class="track-tick-label"[^>]*>0<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>250k<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>5,000,000 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,750k<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>50k<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>100k<\/text>/);
  assert.equal(bandCount, 1);
});

test("full-chr ruler ticks stop at ref_chr end even when ctg extends beyond chr length", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-right-overflow",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600000,
            anchorStart: 4700000,
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 600000, chrLength: 4900000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  assert.match(html, /data-ref-span-bp="4900000"/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,500k<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>4,900,000 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>5M<\/text>/);
});

test("reference track renders a single ref member without gap markers when only one segment is present", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 12, chrLength: 12 }],
        refTrackMembers: [
          {
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-12",
            segmentStartBp: 1,
            segmentEndBp: 12,
            anchorStart: 1,
            totalLength: 12,
            refOrient: "+",
            hits: [],
          },
        ],
      },
    }),
  );

  assert.match(html, /class="track-reference-bar"/);
  assert.match(html, /class="track-reference-member"/);
  assert.match(html, /class="track-ctg-label track-reference-member-label is-ref"/);
  assert.doesNotMatch(html, /class="track-reference-gap-marker"/);
});

test("reference track renders multiple ref members with empty spacing for gap-aware references", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 10100, chrLength: 10100 }],
        refTrackMembers: [
          {
            sourceKind: "ref_segment",
            name: "ref_Chr01:1-5000",
            segmentStartBp: 1,
            segmentEndBp: 5000,
            anchorStart: 1,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
          {
            sourceKind: "ref_segment",
            name: "ref_Chr01:5101-10100",
            segmentStartBp: 5101,
            segmentEndBp: 10100,
            anchorStart: 5101,
            totalLength: 5000,
            refOrient: "+",
            hits: [],
          },
        ],
      },
    }),
  );

  const memberCount = (html.match(/class="track-reference-member"/g) || []).length;
  const memberMatches = [...html.matchAll(
    /<rect[^>]*class="track-reference-member"[^>]*x="([^"]+)"[^>]*width="([^"]+)"[^>]*rx="([^"]+)"[^>]*ry="([^"]+)"/g,
  )];

  assert.doesNotMatch(html, /class="track-reference-bar"/);
  assert.equal(memberCount, 2);
  assert.doesNotMatch(html, /class="track-reference-gap-marker"/);
  assert.match(html, /ref_Chr01:1-5000/);
  assert.match(html, /ref_Chr01:5101-10100/);
  assert.equal(memberMatches.length, 2);
  assert.equal(memberMatches[0][3], "4");
  assert.equal(memberMatches[0][4], "4");
  const firstMemberX = Number(memberMatches[0][1]);
  const firstMemberWidth = Number(memberMatches[0][2]);
  const secondMemberX = Number(memberMatches[1][1]);
  const visibleGapPx = secondMemberX - (firstMemberX + firstMemberWidth);
  assert.ok(visibleGapPx >= 14.9, `expected ref member visible gap >= 15px, got ${visibleGapPx}`);
});

test("negative anchors do not shift viewport start when x layout is sequential", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 87,
            name: "ctg-left-overflow",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: -1000,
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  assert.match(html, /data-track-window-start-bp="0"/);
  assert.match(html, /<text class="track-tick-label"[^>]*>0<\/text>/);
  assert.match(html, /<text class="track-tick-label"[^>]*>5,000 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>-1k<\/text>/);
  assert.match(html, /<line class="track-ruler-line" x1="0(?:\.00)?"/);
});

test("collinearity bands use real reference coordinates instead of reusing contig hit coordinates", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 87,
            name: "ctg-real-ref-band",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: -1000,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 400,
                refStart: 4000,
                refEnd: 4400,
                blockLength: 1200,
              },
            ],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  const match = html.match(/<polygon class="track-collinearity-band"[^>]*points="([^"]+)"/);
  assert.ok(match, "expected a rendered collinearity band");
  const points = match[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));
  const xValues = points.map(([x]) => x);

  assert.ok(xValues[0] > 900, `expected ref-left x to land on the right side, got ${xValues[0]}`);
  assert.ok(xValues[1] > xValues[0], "expected ref-right x to be to the right of ref-left");
  assert.ok(xValues[2] < 100, `expected ctg-right x to stay near the left edge, got ${xValues[2]}`);
  assert.ok(xValues[3] <= xValues[2], "expected ctg-left x to be left of ctg-right");
});

test("collinearity bands do not extend left of the visible ref track when hits start near zero", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 87,
            name: "ctg-left-ref-clamp",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: -1000,
            hits: [
              {
                ctgStart: 1,
                ctgEnd: 400,
                refStart: 1,
                refEnd: 100,
                blockLength: 1200,
              },
            ],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 1000,
        },
      },
    }),
  );

  const refBarMatch = html.match(/track-reference-bar"[\s\S]*?x="([^"]+)"/);
  assert.ok(refBarMatch, "expected a rendered reference bar");
  const refTrackX = Number(refBarMatch[1]);

  const bandMatch = html.match(/<polygon class="track-collinearity-band"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected a rendered collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));

  assert.ok(
    points[0][0] >= refTrackX,
    `expected ref-side left edge to stay within the visible ref track, got ${points[0][0]} < ${refTrackX}`,
  );
});

test("collinearity bands do not extend right of the visible ref track when hits end near chr end", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 4300000,
            hits: [],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000000 }],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-right-ref-clamp",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1500,
            anchorStart: 4300000,
            hits: [
              {
                ctgStart: 100,
                ctgEnd: 800,
                refStart: 4999800,
                refEnd: 5000000,
                blockLength: 1500,
              },
            ],
          },
        ],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const refBarMatch = html.match(/track-reference-bar"[\s\S]*?x="([^"]+)"[\s\S]*?width="([^"]+)"/);
  assert.ok(refBarMatch, "expected a rendered reference bar");
  const refTrackRight = Number(refBarMatch[1]) + Number(refBarMatch[2]);

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected a rendered companion-track collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));
  const rightMostX = Math.max(...points.map(([x]) => x));

  assert.ok(
    rightMostX <= refTrackRight,
    `expected right-most band edge to stay within the visible ref track, got ${rightMostX} > ${refTrackRight}`,
  );
});

test("collinearity bands do not artificially widen tiny ref-edge hits", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-main",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 4300000,
            hits: [],
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 2000, chrLength: 5000000 }],
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-tiny-edge-hit",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1500,
            anchorStart: 4300000,
            hits: [
              {
                ctgStart: 100,
                ctgEnd: 300,
                refStart: 4999800,
                refEnd: 5000000,
                blockLength: 1500,
              },
            ],
          },
        ],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion"[^>]*points="([^"]+)"/);
  assert.ok(bandMatch, "expected a rendered companion-track collinearity band");
  const points = bandMatch[1]
    .trim()
    .split(/\s+/)
    .map((pair) => pair.split(",").map((value) => Number(value)));
  const refEdgeWidth = points[2][0] - points[3][0];

  assert.ok(
    refEdgeWidth < 2,
    `expected tiny ref-edge hit to stay narrow, got widened top edge ${refEdgeWidth}`,
  );
});

test("end tick keeps k-unit label and hides previous label when text overlaps", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ctg-end-overlap",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 200000,
            anchorStart: 4600000,
          },
        ],
        chromosomes: [{ chrName: "Chr01", chrOrder: 1, ctgCount: 1, placedBp: 200000, chrLength: 4899999 }],
        supportDatasetId: null,
        supportChrCtgs: [],
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 1000,
        },
      },
    }),
  );

  const tickGuideCount = (html.match(/track-tick-guide/g) || []).length;
  const tickLabelCount = (html.match(/track-tick-label/g) || []).length;

  assert.match(html, /data-ref-span-bp="4899999"/);
  assert.match(html, /<text class="track-tick-label"[^>]*>4,899,999 bp<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,750k<\/text>/);
  assert.doesNotMatch(html, /<text class="track-tick-label"[^>]*>4,899,999<\/text>/);
  assert.equal(tickGuideCount, tickLabelCount + 1);
});

test("selectSubviewCandidate toggles off an already selected candidate", () => {
  const afterToggleOff = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: 22,
    primaryCtgs: [{ assemblyCtgId: 2, name: "ctg-alpha" }],
    supportCtgs: [{ assemblyCtgId: 30, name: "support-ctg" }],
    subview: {
      mode: "2-contig",
      selectedAContigId: 2,
      selectedARole: "primary",
      selectedBContigId: 30,
      selectedBRole: "support",
      message: "",
      error: "",
      summary: {
        mode: "2-contig",
      },
    },
    trackRole: "support",
    contigId: 30,
  });

  assert.equal(afterToggleOff.selectedAContigId, 2);
  assert.equal(afterToggleOff.selectedARole, "primary");
  assert.equal(afterToggleOff.selectedBContigId, null);
  assert.equal(afterToggleOff.selectedBRole, "");
  assert.equal(afterToggleOff.summary, null);
});

test("selectSubviewCandidate keeps at most two candidates and supports same-track picks", () => {
  const baseArgs = {
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: 22,
    primaryCtgs: [
      { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
      { assemblyCtgId: 5, name: "ctg-zeta", anchorStart: 900 },
      { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
    ],
    supportCtgs: [{ assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 }],
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
  };

  const afterFirst = __testSelectSubviewCandidate({
    ...baseArgs,
    trackRole: "primary",
    contigId: 2,
  });
  const afterSecond = __testSelectSubviewCandidate({
    ...baseArgs,
    subview: afterFirst,
    trackRole: "primary",
    contigId: 8,
  });
  const afterThird = __testSelectSubviewCandidate({
    ...baseArgs,
    subview: afterSecond,
    trackRole: "support",
    contigId: 30,
  });

  assert.equal(afterFirst.selectedAContigId, 2);
  assert.equal(afterFirst.selectedARole, "primary");
  assert.equal(afterSecond.selectedAContigId, 2);
  assert.equal(afterSecond.selectedBContigId, 8);
  assert.equal(afterSecond.selectedBRole, "primary");
  assert.equal(afterThird.selectedAContigId, 8);
  assert.equal(afterThird.selectedARole, "primary");
  assert.equal(afterThird.selectedBContigId, 30);
  assert.equal(afterThird.selectedBRole, "support");
  assert.equal(afterThird.summary, null);
});

test("buildSubviewSummaryFromCandidates orders same-ds by chr order and cross-ds with support on top", () => {
  const primaryCtgs = [
    { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
    { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
  ];
  const supportCtgs = [{ assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 }];

  const sameDs = __testBuildSubviewSummaryFromCandidates({
    subview: {
      selectedAContigId: 8,
      selectedARole: "primary",
      selectedBContigId: 2,
      selectedBRole: "primary",
    },
    primaryCtgs,
    supportCtgs,
  });
  assert.equal(sameDs.ok, true);
  assert.equal(sameDs.value.top.contigId, 2);
  assert.equal(sameDs.value.bottom.contigId, 8);

  const crossDs = __testBuildSubviewSummaryFromCandidates({
    subview: {
      selectedAContigId: 2,
      selectedARole: "primary",
      selectedBContigId: 30,
      selectedBRole: "support",
    },
    primaryCtgs,
    supportCtgs,
  });
  assert.equal(crossDs.ok, true);
  assert.equal(crossDs.value.top.role, "support");
  assert.equal(crossDs.value.bottom.role, "primary");
});

test("selectSubviewTrack enters track-pair summary after selecting two ds tracks", () => {
  const afterPrimary = __testSelectSubviewTrack({
    subview: {
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
    },
    trackRole: "primary",
  });
  assert.equal(afterPrimary.selectedTrackARole, "primary");
  assert.equal(afterPrimary.summary, null);
  const afterSupport = __testSelectSubviewTrack({
    subview: afterPrimary,
    trackRole: "support",
  });
  assert.equal(afterSupport.selectedTrackARole, "primary");
  assert.equal(afterSupport.selectedTrackBRole, "support");
  assert.equal(afterSupport.summary.mode, "track-pair");
  assert.equal(afterSupport.summary.topTrack.role, "support");
  assert.equal(afterSupport.summary.bottomTrack.role, "primary");
});

test("enterSubviewFromTrackSelections copies main-track scale prefs into subviewTrackView", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      trackView: {
        supportDsCtgLen: 10000,
        minTickUnitKb: 500,
        maxTickCount: 15,
        alignmentLength: 22222,
        mapq: 44,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      subview: {
        selectedTrackSelections: [
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        selectedTrackARole: "primary",
        selectedTrackBRole: "support",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testEnterSubviewFromTrackSelections(host, store);

  assert.deepEqual(store.getState().assembly.subviewTrackView, {
    supportDsCtgLen: 10000,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 15,
    alignmentLength: 22222,
    block_length: 22222,
    mapq: 44,
  });
});

test("enterSubviewFromTrackSelections starts pairwise evidence loading for ds track pairs", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    session: {
      workspacePath: "",
    },
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      trackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 500,
        maxTickCount: 15,
        alignmentLength: 10000,
        mapq: 0,
      },
      chrCtgs: [{ assemblyCtgId: 2, name: "primary-bottom", datasetId: 11, totalLength: 5000 }],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-top", datasetId: 22, totalLength: 4000 }],
      subview: {
        selectedTrackSelections: [
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
          { role: "primary", source: "mother", datasetId: null, isMirror: false },
        ],
        selectedTrackARole: "support",
        selectedTrackBRole: "primary",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testEnterSubviewFromTrackSelections(host, store);

  const evidence = store.getState().assembly.subview.pairwiseEvidence;
  assert.equal(evidence?.status, "loading");
  assert.equal(
    evidence?.key,
    "track-pair:support:mother:22:30|primary:2",
  );
  assert.notEqual(String(evidence?.requestKey || ""), "");
});

test("track label selection inherits main-track scale prefs when entering subview-track", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    assembly: {
      trackView: {
        supportDsCtgLen: 15000,
        minTickUnitKb: 500,
        maxTickCount: 15,
        alignmentLength: 100000,
        mapq: 44,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 10000,
        mapq: 0,
      },
      subview: {
        selectedTrackSelections: [
          { role: "support", source: "mother", datasetId: 22, isMirror: false },
        ],
        selectedTrackARole: "support",
        selectedTrackBRole: "",
        summary: null,
        message: "",
        error: "",
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testHandleTrackSubviewTrackSelection(host, store, {
    trackRole: "primary",
    source: "mother",
    datasetId: null,
    isMirror: false,
  });

  assert.equal(store.getState().assembly.subview.summary?.mode, "track-pair");
  assert.deepEqual(store.getState().assembly.subviewTrackView, {
    supportDsCtgLen: 15000,
    minTickUnitKb: 500,
    minTickKb: 500,
    maxTickCount: 15,
    alignmentLength: 100000,
    block_length: 100000,
    mapq: 44,
  });
});

test("selectSubviewTrack keeps mirror source when selecting support first then primary", () => {
  const afterSupportMirror = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    source: "mirror",
    datasetId: 22,
    isMirror: true,
  });
  assert.equal(afterSupportMirror.selectedTrackARole, "support");
  assert.equal(afterSupportMirror.selectedTrackBRole, "");
  assert.equal(afterSupportMirror.selectedTrackBSource, "mirror");
  assert.equal(afterSupportMirror.selectedTrackBDatasetId, 22);
  assert.equal(afterSupportMirror.selectedTrackBIsMirror, true);

  const afterPrimary = __testSelectSubviewTrack({
    subview: afterSupportMirror,
    trackRole: "primary",
  });

  assert.equal(afterPrimary.selectedTrackBSource, "mirror");
  assert.equal(afterPrimary.selectedTrackBDatasetId, 22);
  assert.equal(afterPrimary.selectedTrackBIsMirror, true);
  assert.equal(afterPrimary.summary?.mode, "track-pair");
  assert.equal(afterPrimary.summary?.topTrack?.role, "support");
  assert.equal(afterPrimary.summary?.bottomTrack?.role, "primary");
});

test("selectSubviewTrack supports mirror plus mother support tracks", () => {
  const afterMirror = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    source: "mirror",
    datasetId: 33,
    isMirror: true,
  });
  const afterMother = __testSelectSubviewTrack({
    subview: afterMirror,
    trackRole: "support",
    source: "mother",
    datasetId: 22,
    isMirror: false,
  });

  assert.equal(afterMother.selectedTrackARole, "support");
  assert.equal(afterMother.selectedTrackBRole, "support");
  assert.equal(afterMother.summary?.mode, "track-pair");
  assert.equal(afterMother.summary?.topTrack?.role, "support");
  assert.equal(afterMother.summary?.topTrack?.source, "mirror");
  assert.equal(afterMother.summary?.topTrack?.datasetId, 33);
  assert.equal(afterMother.summary?.bottomTrack?.role, "support");
  assert.equal(afterMother.summary?.bottomTrack?.source, "mother");
  assert.equal(afterMother.summary?.bottomTrack?.datasetId, 22);
});

test("selectSubviewTrack supports selecting two mirror support tracks", () => {
  const afterMirror22 = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    source: "mirror",
    datasetId: 22,
    isMirror: true,
  });
  const afterMirror33 = __testSelectSubviewTrack({
    subview: afterMirror22,
    trackRole: "support",
    source: "mirror",
    datasetId: 33,
    isMirror: true,
  });

  assert.equal(afterMirror33.summary?.mode, "track-pair");
  assert.equal(afterMirror33.summary?.topTrack?.role, "support");
  assert.equal(afterMirror33.summary?.topTrack?.source, "mirror");
  assert.equal(afterMirror33.summary?.topTrack?.datasetId, 22);
  assert.equal(afterMirror33.summary?.bottomTrack?.role, "support");
  assert.equal(afterMirror33.summary?.bottomTrack?.source, "mirror");
  assert.equal(afterMirror33.summary?.bottomTrack?.datasetId, 33);
});

test("swapSubviewSummaryOrder swaps top/bottom for both 2-contig and track-pair modes", () => {
  const swappedCtgMode = __testSwapSubviewSummaryOrder({
    subview: {
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
      message: "",
      error: "old-error",
    },
  });
  assert.equal(swappedCtgMode.summary?.top?.contigId, 2);
  assert.equal(swappedCtgMode.summary?.top?.role, "primary");
  assert.equal(swappedCtgMode.summary?.bottom?.contigId, 30);
  assert.equal(swappedCtgMode.summary?.bottom?.role, "support");
  assert.equal(swappedCtgMode.error, "");
  assert.match(swappedCtgMode.message, /上下轨道顺序/);

  const swappedTrackMode = __testSwapSubviewSummaryOrder({
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "support" },
        bottomTrack: { role: "primary" },
      },
      message: "",
      error: "old-error",
    },
  });
  assert.equal(swappedTrackMode.summary?.topTrack?.role, "primary");
  assert.equal(swappedTrackMode.summary?.bottomTrack?.role, "support");
  assert.equal(swappedTrackMode.error, "");
  assert.match(swappedTrackMode.message, /上下轨道顺序/);
});

test("swap track order keeps subview drag offsets by swapping top/bottom slots", () => {
  const swapped = __testSwapSubviewTrackDragOffsetsForSummarySwap([
    { slot: "top", contigId: 101, offsetBp: 321.5 },
    { slot: "bottom", contigId: 202, offsetPx: -44.5 },
  ]);

  assert.deepEqual(swapped, [
    { slot: "top", contigId: 202, offsetPx: -44.5 },
    { slot: "bottom", contigId: 101, offsetBp: 321.5 },
  ]);
});

test("selectSubviewTrack clears ctg-mode selection to keep subview modes mutually exclusive", () => {
  const next = __testSelectSubviewTrack({
    subview: {
      selectedAContigId: 30,
      selectedARole: "support",
      selectedBContigId: 2,
      selectedBRole: "primary",
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
    },
    trackRole: "primary",
  });
  assert.equal(next.selectedTrackARole, "primary");
  assert.equal(next.selectedAContigId, null);
  assert.equal(next.selectedBContigId, null);
  assert.equal(next.summary, null);
});

test("selectSubviewCandidate clears track-mode selection to keep subview modes mutually exclusive", () => {
  const next = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: 22,
    primaryCtgs: [{ assemblyCtgId: 2, name: "ctg-alpha" }],
    supportCtgs: [{ assemblyCtgId: 30, name: "support-ctg" }],
    subview: {
      selectedTrackARole: "support",
      selectedTrackBRole: "primary",
      trackPairHiddenCtgs: [{ trackRole: "support", contigId: 30 }],
      summary: {
        mode: "track-pair",
        topTrack: { role: "support" },
        bottomTrack: { role: "primary" },
      },
    },
    trackRole: "primary",
    contigId: 2,
  });
  assert.equal(next.selectedTrackARole, "");
  assert.equal(next.selectedTrackBRole, "");
  assert.deepEqual(next.trackPairHiddenCtgs, []);
  assert.equal(next.summary, null);
});

test("removeSubviewCandidate clears subview-ctg summary when remaining candidates are fewer than two", () => {
  const next = __testRemoveSubviewCandidate({
    subview: {
      selectedAContigId: 30,
      selectedARole: "support",
      selectedBContigId: 2,
      selectedBRole: "primary",
      summary: {
        mode: "2-contig",
        top: { contigId: 30, role: "support" },
        bottom: { contigId: 2, role: "primary" },
      },
    },
    trackRole: "support",
    contigId: 30,
  });
  assert.equal(next.selectedAContigId, 2);
  assert.equal(next.selectedBContigId, null);
  assert.equal(next.summary, null);
});

test("removeSubviewTrackSelection clears subview-track summary when remaining tracks are fewer than two", () => {
  const next = __testRemoveSubviewTrackSelection({
    subview: {
      selectedTrackARole: "support",
      selectedTrackBRole: "primary",
      trackPairHiddenCtgs: [{ trackRole: "support", contigId: 30 }],
      summary: {
        mode: "track-pair",
        topTrack: { role: "support" },
        bottomTrack: { role: "primary" },
      },
    },
    trackRole: "support",
  });
  assert.equal(next.selectedTrackARole, "primary");
  assert.equal(next.selectedTrackBRole, "");
  assert.deepEqual(next.trackPairHiddenCtgs, []);
  assert.equal(next.summary, null);
});

test("removeSubviewTrackSelection can remove one support selection by source+dataset", () => {
  const next = __testRemoveSubviewTrackSelection({
    subview: {
      selectedTrackSelections: [
        { role: "support", source: "mirror", datasetId: 33, isMirror: true },
        { role: "support", source: "mother", datasetId: 22, isMirror: false },
      ],
      summary: {
        mode: "track-pair",
        topTrack: { role: "support", source: "mirror", datasetId: 33, isMirror: true },
        bottomTrack: { role: "support", source: "mother", datasetId: 22, isMirror: false },
      },
    },
    trackRole: "support",
    source: "mirror",
    datasetId: 33,
    isMirror: true,
  });

  assert.equal(next.selectedTrackSelections?.length, 1);
  assert.equal(next.selectedTrackSelections?.[0]?.role, "support");
  assert.equal(next.selectedTrackSelections?.[0]?.source, "mother");
  assert.equal(next.selectedTrackSelections?.[0]?.datasetId, 22);
  assert.equal(next.summary, null);
});

test("buildSubviewSummaryFromTrackSelections accepts support-support selection", () => {
  const result = __testBuildSubviewSummaryFromTrackSelections({
    subview: {
      selectedTrackSelections: [
        { role: "support", source: "mirror", datasetId: 33, isMirror: true },
        { role: "support", source: "mother", datasetId: 22, isMirror: false },
      ],
    },
  });
  assert.equal(result.ok, true);
  assert.equal(result.value?.mode, "track-pair");
  assert.equal(result.value?.topTrack?.role, "support");
  assert.equal(result.value?.topTrack?.source, "mirror");
  assert.equal(result.value?.topTrack?.datasetId, 33);
  assert.equal(result.value?.bottomTrack?.role, "support");
  assert.equal(result.value?.bottomTrack?.source, "mother");
  assert.equal(result.value?.bottomTrack?.datasetId, 22);
});

test("subview-track mode renders only the selected phased track items", () => {
  const html = renderAssemblyPage(createState({
    assembly: {
      subview: {
        summary: {
          mode: "track-pair",
          topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          bottomTrack: { role: "primary" },
        },
        selectedTrackSelections: [
          { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          { role: "primary" },
        ],
      },
      phasedChrTracks: [
        {
          phasedTrackId: 101,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
        },
      ],
    },
  }));
  const topSlotMarkup = html.match(/data-subview-track-slot="top"[\s\S]*?data-subview-track-slot="bottom"/)?.[0] || "";

  assert.match(topSlotMarkup, /data-subview-track-role="phased"/);
  assert.match(topSlotMarkup, /data-subview-contig-id="2"/);
  assert.match(html, /data-subview-track-pair-phased-track-id="101"/);
  assert.match(html, /data-subview-track-pair-phased-track-item-id="9001"/);
  assert.match(html, /data-subview-track-pair-phased-haplotype-key="A"/);
  assert.doesNotMatch(topSlotMarkup, /data-subview-contig-id="8"/);
});

test("subview-ctg mode exposes phased context metadata for append menus", () => {
  const html = renderAssemblyPage(createState({
    assembly: {
      isChrPhased: true,
      subview: {
        summary: {
          mode: "2-contig",
          top: { contigId: 2, role: "phased", contigName: "ctg-alpha" },
          bottom: { contigId: 8, role: "primary", contigName: "ctg-beta" },
        },
      },
      phasedChrTracks: [
        {
          phasedTrackId: 101,
          haplotypeKey: "A",
          label: "Chr01A",
          displayOrder: 1,
          items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
        },
      ],
    },
  }));
  const topGroup = html.match(
    /data-subview-track-pair-role="phased"[\s\S]*?data-subview-track-slot="top"[\s\S]*?<\/g>/,
  )?.[0] || "";

  assert.match(topGroup, /data-subview-track-pair-role="phased"/);
  assert.match(topGroup, /data-subview-track-pair-contig-id="2"/);
  assert.match(topGroup, /data-subview-track-pair-phased-track-id="101"/);
  assert.match(topGroup, /data-subview-track-pair-phased-track-item-id="9001"/);
  assert.match(topGroup, /data-subview-track-pair-phased-haplotype-key="A"/);
});

test("subview-track mode renders phased lanes in primary visual order", () => {
  const html = renderAssemblyPage(createState({
    assembly: {
      chrCtgs: [
        { assemblyCtgId: 11, name: "left-primary", assignedChrName: "Chr01", totalLength: 5000, anchorStart: 100 },
        { assemblyCtgId: 16, name: "right-primary", assignedChrName: "Chr01", totalLength: 2000, anchorStart: 500 },
      ],
      phasedChrTracks: [
        {
          phasedTrackId: 102,
          haplotypeKey: "B",
          label: "Chr01B",
          displayOrder: 2,
          items: [
            { itemId: 9002, phasedTrackId: 102, assemblyCtgId: 16, displayOrder: 1 },
            { itemId: 9001, phasedTrackId: 102, assemblyCtgId: 11, displayOrder: 2 },
          ],
        },
      ],
      subview: {
        summary: {
          mode: "track-pair",
          topTrack: { role: "primary" },
          bottomTrack: { role: "phased", phasedTrackId: 102, haplotypeKey: "B" },
        },
        selectedTrackSelections: [
          { role: "primary" },
          { role: "phased", phasedTrackId: 102, haplotypeKey: "B" },
        ],
      },
    },
  }));
  const bottomItems = [
    ...html.matchAll(
      /data-subview-track-slot="bottom"[^>]*data-subview-contig-id="([^"]+)"[^>]*data-subview-rect-x="([^"]+)"/g,
    ),
  ].map((match) => ({
    contigId: Number(match[1]),
    x: Number(match[2]),
  }));

  assert.equal(bottomItems.length, 2);
  assert.deepEqual(bottomItems.map((item) => item.contigId), [11, 16]);
  assert.ok(bottomItems[0].x < bottomItems[1].x, `expected phased lane left-to-right order, got ${JSON.stringify(bottomItems)}`);
});

test("context menu shows enter-subview action when exactly two candidates are selected", () => {
  const store = createStore(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: null,
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    memberNode: null,
    store,
    host,
  });
  assert.ok(items.every((item) => item.label !== "进入Subview-ctg"));
});

test("context menu shows local subview delete action in track-pair mode", () => {
  const store = createStore(
    createState({
      assembly: {
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 },
            ],
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    deletedCtgContext: null,
    memberNode: null,
    subviewTrackPairContext: {
      trackRole: "support",
      assemblyCtgId: 30,
    },
    store,
    host,
  });
  assert.ok(items.some((item) => item.label === "在Subview中删除 contig（仅当前视图）"));
});

test("context menu shows flip action for phased ctg in subview track-pair mode", () => {
  const store = createStore(
    createState({
      assembly: {
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 },
            ],
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
            bottomTrack: { role: "primary" },
          },
        },
      },
    }),
  );
  const host = {};
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    deletedCtgContext: null,
    memberNode: null,
    subviewTrackPairContext: {
      trackRole: "phased",
      assemblyCtgId: 2,
      slot: "top",
    },
    store,
    host,
  });
  assert.ok(items.some((item) => item.label === "翻转 contig"));
});

test("subview panel renders chart sub-card with parameter labels after entering", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-ctg" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /<h4>Subview<\/h4>/);
  assert.match(
    html,
    /Ctrl\/Cmd 选中任意两个ctg进入subview-ctg；也支持点击任意两个轨道名进入subview-track。/,
  );
  assert.match(html, /support-ctg vs ctg-alpha/);
  assert.match(html, /data-subview-remove-type="candidate"/);
  assert.match(html, /data-subview-remove-role="support"/);
  assert.match(html, /data-subview-remove-contig-id="30"/);
  assert.match(html, /最小刻度单位\(kb\)/);
  assert.match(html, /最多可展示数/);
  assert.match(html, /Alignment Length\(bp\)/);
  assert.match(html, /MAPQ/);
  assert.match(html, /id="subview-track-min-tick-unit-kb"/);
  assert.match(html, /id="subview-track-max-tick-count"/);
  assert.match(html, /id="subview-track-alignment-length"/);
  assert.match(html, /id="subview-track-mapq"/);
  assert.match(html, /class="assembly-track-layout subview-track-layout"/);
  assert.doesNotMatch(html, /规则：/);
  assert.doesNotMatch(html, /上轨：/);
  assert.doesNotMatch(html, /下轨：/);
  assert.doesNotMatch(html, /命中：/);
  assert.match(html, /support-ctg/);
  assert.match(html, /ctg-alpha/);
});

test("subview track-pair mode renders only mirror support ctg containers when support track source is mirror", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-mother", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "wtdbg2",
            chrName: "Chr01",
            assemblyCtgId: 330,
            name: "support-mirror-only",
            totalLength: 350,
            anchorStart: 360,
            lengthBp: 350,
            startBp: 0,
            endBp: 349,
            laneIndex: 0,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          selectedTrackBDatasetId: 33,
          selectedTrackBIsMirror: true,
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", datasetId: 33, isMirror: true },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
          { datasetId: 33, name: "wtdbg2", label: "wtdbg2" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] },
        ],
      },
    }),
  );

  assert.match(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="330"/);
  assert.doesNotMatch(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="30"/);
});

test("subview track-pair mother support does not include mirror ctgs from other datasets", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "canu2-mother", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 1901,
            name: "flye-mirror-ctg1901",
            totalLength: 1481407,
            anchorStart: 0,
            lengthBp: 1481407,
            startBp: 0,
            endBp: 1481406,
            laneIndex: 0,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          selectedTrackBDatasetId: 22,
          selectedTrackBIsMirror: false,
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "canu2", label: "canu2" },
          { datasetId: 33, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] },
        ],
      },
    }),
  );

  assert.match(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="30"/);
  assert.doesNotMatch(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="1901"/);
});

test("subview track-pair support track skips deleted contigs inherited from main view", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-keep", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
          { assemblyCtgId: 31, name: "support-deleted", assignedChrName: "Chr01", memberCount: 1, totalLength: 280, anchorStart: 720 },
        ],
        deletedCtgs: [
          {
            deletedCtgRecordId: 9101,
            assemblyCtgId: 31,
            name: "support-deleted",
            memberCount: 1,
            totalLength: 280,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="30"/);
  assert.doesNotMatch(html, /data-subview-track-pair-role="support"[^>]*data-subview-track-pair-contig-id="31"/);
});

test("subview track-pair mode renders both ds track labels and local delete context attrs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [
          { projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] },
        ],
      },
    }),
  );

  assert.match(html, /主\(hifiasm\)/);
  assert.match(html, /辅\(flye\)/);
  assert.match(html, /data-subview-track-pair-role="support"/);
  assert.match(html, /data-subview-track-pair-contig-id="30"/);
  assert.match(html, /data-subview-track-pair-dataset-id="22"/);
  assert.match(html, /data-subview-track-pair-is-mirror="0"/);
  assert.match(html, /data-subview-remove-type="track"/);
  assert.doesNotMatch(html, /尚未选择候选 ctg/);
  assert.doesNotMatch(html, /轨道模式：/);
});

test("subview labels expose runtime lookup metadata in both 2-contig and track-pair modes", () => {
  const twoContigHtml = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-top", refOrient: "+", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "primary-bottom", refOrient: "-", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 100 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(twoContigHtml, /data-subview-label-slot="top"[^>]*data-subview-label-role="support"[^>]*data-subview-label-contig-id="30"[^>]*>support-top \(\+\)<\/text>/);
  assert.match(twoContigHtml, /data-subview-label-slot="bottom"[^>]*data-subview-label-role="primary"[^>]*data-subview-label-contig-id="2"[^>]*>primary-bottom \(-\)<\/text>/);

  const trackPairHtml = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-track", refOrient: "-", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "primary-track", refOrient: "+", assignedChrName: "Chr01", memberCount: 1, totalLength: 500_000, anchorStart: 100 },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(trackPairHtml, /data-subview-label-slot="top"[^>]*data-subview-label-role="support"[^>]*data-subview-label-contig-id="30"[^>]*>support-track \(-\)<\/text>/);
  assert.match(trackPairHtml, /data-subview-label-slot="bottom"[^>]*data-subview-label-role="primary"[^>]*data-subview-label-contig-id="2"[^>]*>primary-track \(\+\)<\/text>/);
});

test("subview track-pair strips chr suffix in labels and keeps full hover titles", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "Ctg1617@Chr22", refOrient: "-", assignedChrName: "Chr22", memberCount: 1, totalLength: 500_000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "ptg000009l@Chr22", refOrient: "+", assignedChrName: "Chr22", memberCount: 1, totalLength: 500_000, anchorStart: 100 },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairHiddenCtgs: [],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /data-subview-label-slot="top"[^>]*data-subview-label-role="support"[^>]*data-subview-label-contig-id="30"[^>]*>Ctg1617 \(-\)<\/text>/);
  assert.match(html, /data-subview-label-slot="bottom"[^>]*data-subview-label-role="primary"[^>]*data-subview-label-contig-id="2"[^>]*>ptg000009l \(\+\)<\/text>/);
  assert.match(html, /<title>Ctg1617@Chr22 \| start=/);
  assert.match(html, /<title>ptg000009l@Chr22 \| start=/);
  assert.doesNotMatch(html, /data-subview-label-slot="top"[^>]*>Ctg1617@Chr22 \(-\)<\/text>/);
  assert.doesNotMatch(html, /data-subview-label-slot="bottom"[^>]*>ptg000009l@Chr22 \(\+\)<\/text>/);
});

test("subview local contig flips only affect subview labels and leave main-view labels unchanged", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-track",
            refOrient: "+",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000,
            anchorStart: 100,
          },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 2,
          selectedBRole: "primary",
          flippedCtgs: [{ slot: "bottom", contigId: 2 }],
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "primary", contigName: "primary-track" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-track" },
          },
        },
      },
    }),
  );

  assert.match(html, /data-track-role="primary"[^>]*>[\s\S]*?primary-track \(\+\)<\/text>/);
  assert.match(html, /data-subview-label-slot="top"[^>]*>primary-track \(\+\)<\/text>/);
  assert.match(html, /data-subview-label-slot="bottom"[^>]*>primary-track \(-\)<\/text>/);
});

test("subview local contig flip refreshes only the subview panel", () => {
  const store = createStore(
    createState({
      assembly: {
        subview: {
          mode: "2-contig",
          flippedCtgs: [],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
    }),
  );
  const calls = [];

  __testToggleSubviewContigFlip(
    {},
    store,
    { slot: "top", assemblyCtgId: 30 },
    {
      rerenderSubviewPanel(_host, currentStore) {
        calls.push(currentStore.getState().assembly.subview.flippedCtgs);
      },
    },
  );

  assert.deepEqual(store.getState().assembly.subview.flippedCtgs, [{ slot: "top", contigId: 30 }]);
  assert.deepEqual(calls, [[{ slot: "top", contigId: 30 }]]);
});

test("subview panel rerender uses track renderer deps so local flips paint immediately", () => {
  const store = createStore(
    createState({
      assembly: {
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-track",
            refOrient: "+",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2_000,
            anchorStart: 100,
          },
        ],
        subview: {
          mode: "2-contig",
          flippedCtgs: [{ slot: "bottom", contigId: 2 }],
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "primary", contigName: "primary-track" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-track" },
          },
        },
      },
    }),
  );
  let renderedPanelHtml = "";
  let currentPanel = null;
  const fakeDoc = {
    contains(node) {
      return Boolean(node);
    },
    querySelector(selector) {
      return selector === "#route-host" ? routeHost : null;
    },
  };
  const noopPanel = {
    ownerDocument: fakeDoc,
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };
  currentPanel = {
    ownerDocument: fakeDoc,
    set outerHTML(value) {
      renderedPanelHtml = String(value || "");
      currentPanel = noopPanel;
    },
  };
  const routeHost = {
    ownerDocument: fakeDoc,
    matches(selector) {
      return selector === "#route-host";
    },
    closest() {
      return null;
    },
    querySelector(selector) {
      return selector === "[data-subview-panel='1']" ? currentPanel : null;
    },
    querySelectorAll() {
      return [];
    },
    addEventListener() {},
  };

  __testRerenderSubviewPanel(routeHost, store);

  assert.match(renderedPanelHtml, /data-subview-label-slot="bottom"[^>]*>primary-track \(-\)<\/text>/);
});

test("subview track-pair mode renders tooltip-enabled overlap bands and draggable track metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /class="subview-band-tooltip is-hidden"/);
  assert.match(html, /data-subview-band-tooltip-delay-ms="500"/);
  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 2,200-3,400 bp[^"]*primary-bottom: 2,400-3,600 bp/);
  assert.match(html, /class="track-band-canvas-layer"[^>]*data-track-band-canvas-scene-kind="subview-track-pair"/);
  assert.match(html, /<canvas class="track-band-canvas"[^>]*data-track-band-canvas="1"/);
  assert.match(html, /<polygon class="track-collinearity-band is-companion"[^>]*pointer-events="visibleFill"[^>]*data-track-band-proxy="1"/);
  assert.match(html, /<clipPath id="subview-track-band-clip"/);
  assert.match(html, /<g clip-path="url\(#subview-track-band-clip\)">[\s\S]*<polygon class="track-collinearity-band is-companion"[\s\S]*data-track-band-proxy="1"/);
  assert.match(html, /class="track-ctg subview-track-ctg[^"]*"[^>]*pointer-events="all"/);
  assert.match(html, /data-subview-track-slot="top"[^>]*data-subview-contig-id="30"/);
  assert.match(html, /data-subview-track-slot="bottom"[^>]*data-subview-contig-id="2"/);
  assert.match(html, /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-domain-span-bp="[^"]+"/);
  assert.match(html, /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-inner-width="[^"]+"/);
});

test("subview track-pair bands anchor to each contig lane instead of fixed top row at low tick-unit scales", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-lane0",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3_000_000,
            anchorStart: 100,
            hits: [],
          },
          {
            assemblyCtgId: 31,
            name: "support-hit-lane1",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3_000_000,
            anchorStart: 120,
            hits: [
              { refStart: 13_600_000, refEnd: 13_700_000, ctgStart: 100_000, ctgEnd: 200_000, blockLength: 100_000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3_200_000,
            anchorStart: 100,
            hits: [
              { refStart: 13_600_000, refEnd: 13_700_000, ctgStart: 100_000, ctgEnd: 200_000, blockLength: 100_000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 250,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const topRectMatch = html.match(
    /data-subview-track-slot="top"[^>]*data-subview-contig-id="31"[^>]*data-subview-rect-y="([^"]+)"/,
  );
  assert.ok(topRectMatch, "expected top contig 31 with rect y");
  const topRectY = Number(topRectMatch[1]);

  const polygonMatch = html.match(
    /<polygon class="track-collinearity-band[^"]*"[^>]*points="([^"]+)"[^>]*data-subview-band-tooltip="[^"]*support-hit-lane1[^"]*"/,
  );
  assert.ok(polygonMatch, "expected a band polygon for support-hit-lane1");
  const firstPoint = String(polygonMatch[1] || "").split(" ")[0] || "";
  const firstY = Number(firstPoint.split(",")[1]);
  assert.ok(
    Math.abs(firstY - (topRectY + 14)) < 0.1,
    `expected top band y to align with contig bottom (${topRectY + 14}), got ${firstY}`,
  );
});

test("subview track-pair bands use only the shared ref-overlap slice instead of full hit widths", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 3000, ctgStart: 1, ctgEnd: 2000, blockLength: 2000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 2000,
            anchorStart: 100,
            hits: [
              { refStart: 2000, refEnd: 4000, ctgStart: 1, ctgEnd: 2000, blockLength: 2000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const topRectMatch = html.match(
    /data-subview-track-slot="top"[^>]*data-subview-contig-id="30"[^>]*data-subview-rect-x="([^"]+)"[^>]*data-subview-rect-width="([^"]+)"/,
  );
  assert.ok(topRectMatch, "expected top rect metrics");
  const topRectX = Number(topRectMatch[1]);
  const topRectWidth = Number(topRectMatch[2]);

  const bottomRectMatch = html.match(
    /data-subview-track-slot="bottom"[^>]*data-subview-contig-id="2"[^>]*data-subview-rect-x="([^"]+)"[^>]*data-subview-rect-width="([^"]+)"/,
  );
  assert.ok(bottomRectMatch, "expected bottom rect metrics");
  const bottomRectX = Number(bottomRectMatch[1]);
  const bottomRectWidth = Number(bottomRectMatch[2]);

  const polygonMatch = html.match(
    /<polygon class="track-collinearity-band[^"]*"[^>]*points="([^"]+)"[^>]*data-subview-band-tooltip="[^"]*support-top[^"]*primary-bottom[^"]*"/,
  );
  assert.ok(polygonMatch, "expected a track-pair band polygon");
  const points = String(polygonMatch[1] || "")
    .split(" ")
    .map((point) => point.split(",").map(Number));

  assert.ok(
    Math.abs(points[0][0] - (topRectX + topRectWidth / 2)) < 0.2,
    `expected top overlap to start at half of top rect, got ${points[0][0]}`,
  );
  assert.ok(
    Math.abs(points[1][0] - (topRectX + topRectWidth)) < 0.2,
    `expected top overlap to end at top rect end, got ${points[1][0]}`,
  );
  assert.ok(
    Math.abs(points[2][0] - (bottomRectX + bottomRectWidth / 2)) < 0.2,
    `expected bottom overlap to end at half of bottom rect, got ${points[2][0]}`,
  );
  assert.ok(
    Math.abs(points[3][0] - bottomRectX) < 0.2,
    `expected bottom overlap to start at bottom rect start, got ${points[3][0]}`,
  );
});

test("subview track-pair overlap slice does not inflate a clamped 1px hit to full width", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 1, ctgEnd: 1, blockLength: 1001, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000000,
            anchorStart: 100,
            hits: [
              { refStart: 1500, refEnd: 2000, ctgStart: 1, ctgEnd: 1, blockLength: 501, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const topRectMatch = html.match(
    /data-subview-track-slot="top"[^>]*data-subview-contig-id="30"[^>]*data-subview-rect-x="([^"]+)"[^>]*data-subview-rect-width="([^"]+)"/,
  );
  assert.ok(topRectMatch, "expected top rect metrics");

  const polygonMatch = html.match(
    /<polygon class="track-collinearity-band[^"]*"[^>]*points="([^"]+)"[^>]*data-subview-band-tooltip="[^"]*support-top[^"]*primary-bottom[^"]*"/,
  );
  assert.ok(polygonMatch, "expected a track-pair band polygon");
  const points = String(polygonMatch[1] || "")
    .split(" ")
    .map((point) => point.split(",").map(Number));
  const topProjectedWidth = points[1][0] - points[0][0];
  assert.ok(
    topProjectedWidth < 0.75,
    `expected top overlap width to stay subpixel-to-half-pixel, got ${topProjectedWidth}`,
  );
});

test("subview track-pair mode avoids cross-pair fan-out when adjacent hits slightly overlap at boundaries", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 1, ctgEnd: 1000, blockLength: 1001, mapq: 60 },
              { refStart: 2001, refEnd: 3000, ctgStart: 1001, ctgEnd: 2000, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2050, ctgStart: 1, ctgEnd: 1050, blockLength: 1051, mapq: 60 },
              { refStart: 2000, refEnd: 3000, ctgStart: 1051, ctgEnd: 2050, blockLength: 1001, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(
    /<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/,
  );
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatches = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*"/g) || [];
  assert.equal(
    polygonMatches.length,
    2,
    `expected only the two best ordered bands, got ${polygonMatches.length}`,
  );
});

test("subview track-pair mode ignores malformed hits without explicit contig coordinates", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20_000_000,
            anchorStart: 320,
            hits: [
              { refStart: 12_200_000, refEnd: 13_700_000, blockLength: 1_500_000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20_000_000,
            anchorStart: 100,
            hits: [
              { refStart: 12_200_000, refEnd: 13_700_000, ctgStart: 2_200_000, ctgEnd: 3_700_000, blockLength: 1_500_000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 500,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(html, /data-subview-band-tooltip="/);
});

test("subview track-pair mode marks box-selected ctgs as multi-selected", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairSelectedCtgs: [
            { trackRole: "support", contigId: 30 },
            { trackRole: "primary", contigId: 2 },
          ],
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /data-subview-track-role="support"[\s\S]*class="track-ctg subview-track-ctg is-companion is-multi-selected"/,
  );
  assert.match(
    html,
    /data-subview-track-role="primary"[\s\S]*class="track-ctg subview-track-ctg is-multi-selected"/,
  );
});

test("context menu on blank area exposes batch subview delete for box-selected track-pair ctgs", () => {
  const store = createStore(
    createState({
      assembly: {
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
          },
        ],
        subview: {
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
          trackPairSelectedCtgs: [
            { trackRole: "support", contigId: 30 },
            { trackRole: "primary", contigId: 2 },
          ],
        },
      },
    }),
  );
  const items = __testBuildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    deletedCtgContext: null,
    memberNode: null,
    subviewTrackPairContext: null,
    store,
    host: {},
  });

  assert.ok(
    items.some((item) => item.label === "在Subview中删除已框选 contig（2，仅当前视图）"),
  );
});

test("subview track-pair mode keeps a fixed 20px visible gap between adjacent top-track contigs", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 100,
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10_000_000,
            anchorStart: 200,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const matches = [
    ...html.matchAll(
      /data-subview-track-slot="top"[\s\S]*?data-subview-rect-x="([^"]+)"[\s\S]*?data-subview-rect-width="([^"]+)"/g,
    ),
  ];
  assert.ok(matches.length >= 2, "expected at least two top-track ctg bars");
  const firstX = Number(matches[0][1]);
  const firstWidth = Number(matches[0][2]);
  const secondX = Number(matches[1][1]);
  const visibleGapPx = secondX - (firstX + firstWidth);
  assert.ok(visibleGapPx >= 19.9, `expected visible gap >= 20px, got ${visibleGapPx}`);
});

test("subview track-pair preserves the main track contig order", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-a",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 300,
          },
          {
            assemblyCtgId: 31,
            name: "support-b",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 200,
          },
          {
            assemblyCtgId: 32,
            name: "support-c",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
          },
        ],
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const topIds = [
    ...html.matchAll(/data-subview-track-slot="top"[^>]*data-subview-contig-id="([^"]+)"/g),
  ].map((match) => Number(match[1]));
  assert.deepEqual(topIds.slice(0, 3), [30, 31, 32]);
});

test("subview track-pair drag offsets move the targeted ctg bar", () => {
  const buildHtml = (subviewTrackDragOffsets = []) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 30,
              name: "support-top",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 20000,
              anchorStart: 320,
              hits: [
                { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 2,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 20000,
              anchorStart: 100,
              hits: [
                { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
              ],
            },
          ],
          subview: {
            selectedTrackARole: "primary",
            selectedTrackBRole: "support",
            summary: {
              mode: "track-pair",
              topTrack: { role: "support" },
              bottomTrack: { role: "primary" },
            },
          },
          subviewTrackDragOffsets,
        },
        initializer: {
          datasets: [
            { datasetId: 11, name: "hifiasm", label: "hifiasm" },
            { datasetId: 22, name: "flye", label: "flye" },
          ],
          existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
        },
      }),
    );

  const extractTrackPairRectX = (html, slot, contigId) => {
    const match = html.match(
      new RegExp(`<g[^>]*data-subview-track-slot="${slot}"[^>]*data-subview-contig-id="${contigId}"[^>]*data-subview-rect-x="([^"]+)"`),
    );
    assert.ok(match, `expected ${slot} bar for contig ${contigId}`);
    return Number(match[1]);
  };

  const baseHtml = buildHtml([]);
  const shiftedHtml = buildHtml([{ slot: "top", contigId: 30, offsetPx: 60 }]);

  const baseTopX = extractTrackPairRectX(baseHtml, "top", 30);
  const shiftedTopX = extractTrackPairRectX(shiftedHtml, "top", 30);
  assert.ok(Math.abs((shiftedTopX - baseTopX) - 60) < 0.1, `expected top x shift by 60px, got ${shiftedTopX - baseTopX}`);
});

test("subview renders bands for support-support pairs when one contig comes from mirror track", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 1914,
            name: "Ctg1914",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4_000_000,
            anchorStart: 100,
            hits: [
              { refStart: 5_000_000, refEnd: 5_600_000, ctgStart: 100_000, ctgEnd: 700_000, blockLength: 600_000, mapq: 60 },
            ],
          },
        ],
        supportMirroredCtgs: [
          {
            datasetId: 33,
            datasetName: "flye",
            chrName: "Chr01",
            assemblyCtgId: 1901,
            name: "Ctg1901",
            totalLength: 3_500_000,
            anchorStart: 200,
            lengthBp: 3_500_000,
            startBp: 0,
            endBp: 3_499_999,
            laneIndex: 0,
            hits: [
              { refStart: 5_050_000, refEnd: 5_650_000, ctgStart: 120_000, ctgEnd: 720_000, blockLength: 600_000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 1901,
          selectedARole: "support",
          selectedBContigId: 1914,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 1901, role: "support", contigName: "Ctg1901" },
            bottom: { contigId: 1914, role: "support", contigName: "Ctg1914" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "canu2", label: "canu2" },
          { datasetId: 33, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22, 33] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = Array.from(
    subviewSvgMatch[0].matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.ok(polygons.length > 0, "expected support-support subview bands from mirror/source hits");
});

test("subview track controls render independently from main track controls", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        trackView: {
          minTickUnitKb: 250,
          maxTickCount: 20,
          alignmentLength: 10000,
          mapq: 30,
        },
        subviewTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 5,
          alignmentLength: 1000,
          mapq: 0,
        },
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-ctg", assignedChrName: "Chr01", memberCount: 1, totalLength: 300, anchorStart: 320 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-ctg" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-alpha" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /id="assembly-track-min-tick-unit-kb"[^>]*value="250"/);
  assert.match(html, /id="assembly-track-max-tick-count"[^>]*value="20"/);
  assert.match(html, /id="assembly-track-alignment-length"[^>]*value="10000"/);
  assert.match(html, /id="assembly-track-mapq"[^>]*value="30"/);

  assert.match(html, /id="subview-track-min-tick-unit-kb"[^>]*value="10000"/);
  assert.match(html, /id="subview-track-max-tick-count"[^>]*value="5"/);
  assert.match(html, /id="subview-track-alignment-length"[^>]*value="1000"/);
  assert.match(html, /id="subview-track-mapq"[^>]*value="0"/);
  assert.match(html, /id="assembly-track-min-tick-unit-kb-menu"[\s\S]*data-track-combo-value="100000"/);
  assert.match(html, /id="subview-track-min-tick-unit-kb-menu"[\s\S]*data-track-combo-value="100000"/);
  assert.match(html, /data-subview-action="swap-track-order"/);
  assert.match(
    html,
    /Ctrl\/Cmd 选中任意两个ctg进入subview-ctg；也支持点击任意两个轨道名进入subview-track。<\/p>\s*<div class="subview-candidate-row">/,
  );
  assert.doesNotMatch(html, /已选 \d\/2 个ctg；右键选择“进入Subview-ctg”。/);
  assert.doesNotMatch(html, /已选 \d\/2 条ds轨道。/);
  assert.doesNotMatch(html, /Subview 已进入轨道模式。/);
  assert.doesNotMatch(html, /Subview 已切换上下轨道顺序。/);
  assert.match(
    html,
    /<div class="assembly-track-label-column subview-track-label-column"[\s\S]*class="button ghost tiny subview-track-order-toggle is-in-label-column"[\s\S]*<\/div>\s*<div\s+class="assembly-track-scroll subview-track-scroll"/,
  );
});

test("subview chart uses real relative ctg lengths so top and bottom bars can differ", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-short", assignedChrName: "Chr01", memberCount: 1, totalLength: 600, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-long", assignedChrName: "Chr01", memberCount: 1, totalLength: 2400, anchorStart: 100 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-short" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-long" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const barMatches = Array.from(
    subviewSvgMatch[0].matchAll(/<rect class="track-ctg([^"]*)"[^>]*width="([^"]+)"/g),
  );
  assert.equal(barMatches.length >= 2, true);
  const topWidth = Number(barMatches[0][2]);
  const bottomWidth = Number(barMatches[1][2]);
  assert.ok(
    topWidth < bottomWidth,
    `expected top bar width < bottom bar width, got top=${topWidth}, bottom=${bottomWidth}`,
  );
});

test("subview ctg mode renders independent left/right edge targets for each paired hit", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /class="subview-anchor-hit-zone"[^>]*data-subview-anchor-hit-key="hit-1"[^>]*data-subview-anchor-edge="left"/,
  );
  assert.match(
    html,
    /class="subview-anchor-hit-zone"[^>]*data-subview-anchor-hit-key="hit-1"[^>]*data-subview-anchor-edge="right"/,
  );
});

test("active subview anchors render on the same gap-edge geometry as their hit zones", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /class="subview-anchor-line is-active"[^>]*stroke="red"[^>]*stroke-width="3"/,
  );
  assert.match(
    html,
    /data-subview-track-slot="bottom"[\s\S]*class="subview-anchor-line is-active"[^>]*stroke="red"/,
  );
  assert.match(
    html,
    /class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="hit-1"[^>]*data-subview-anchor-edge="left"/,
  );
  const topBarMatch = html.match(/data-subview-track-slot="top"[^>]*data-subview-rect-y="([^"]+)"[^>]*data-subview-rect-height="([^"]+)"/);
  const bottomBarMatch = html.match(/data-subview-track-slot="bottom"[^>]*data-subview-rect-y="([^"]+)"/);
  const anchorHitZoneMatch = html.match(/class="subview-anchor-hit-zone is-active"[^>]*y1="([^"]+)"[^>]*y2="([^"]+)"/);
  assert.ok(topBarMatch, "expected a top subview ctg bar");
  assert.ok(bottomBarMatch, "expected a bottom subview ctg bar");
  assert.ok(anchorHitZoneMatch, "expected an active anchor hit zone");
  assert.equal(
    Number(anchorHitZoneMatch[1]).toFixed(2),
    (Number(topBarMatch[1]) + Number(topBarMatch[2])).toFixed(2),
  );
  assert.equal(
    Number(anchorHitZoneMatch[2]).toFixed(2),
    Number(bottomBarMatch[1]).toFixed(2),
  );
});

test("subview keeps anchored hits visible after alignment length filters non-anchored hits away", () => {
  const renderWithAlignmentLength = (alignmentLength) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 30,
              name: "support-top",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 5000,
              anchorStart: 320,
              hits: [
                { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 220, blockLength: 1000, mapq: 60 },
                { refStart: 5000, refEnd: 7000, ctgStart: 1101, ctgEnd: 1460, blockLength: 180000, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 8,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 5000,
              anchorStart: 100,
              hits: [
                { refStart: 1000, refEnd: 2000, ctgStart: 801, ctgEnd: 920, blockLength: 1000, mapq: 60 },
                { refStart: 5000, refEnd: 7000, ctgStart: 2101, ctgEnd: 2460, blockLength: 180000, mapq: 60 },
              ],
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 1000,
            maxTickCount: 10,
            alignmentLength,
            mapq: 0,
          },
          subview: {
            mode: "2-contig",
            selectedAContigId: 8,
            selectedARole: "primary",
            selectedBContigId: 30,
            selectedBRole: "support",
            activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
            summary: {
              mode: "2-contig",
              top: { contigId: 30, role: "support", contigName: "support-top" },
              bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
            },
          },
        },
        initializer: {
          datasets: [
            { datasetId: 11, name: "hifiasm", label: "hifiasm" },
            { datasetId: 22, name: "flye", label: "flye" },
          ],
          existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
        },
      }),
    );

  const baseHtml = renderWithAlignmentLength(1000);
  const filteredHtml = renderWithAlignmentLength(100000);

  assert.match(baseHtml, /class="subview-anchor-line is-active"/);
  assert.match(baseHtml, /data-subview-hit-key="hit-1"/);
  assert.match(filteredHtml, /class="subview-anchor-line is-active"/);
  assert.match(filteredHtml, /data-subview-hit-key="hit-1"/);
});

test("subview drag offsets keep anchor lines aligned with the hit polygon edges", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        subviewTrackDragOffsets: [{ slot: "bottom", assemblyCtgId: 8, offsetPx: 180 }],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const bandMatch = html.match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"[^>]*data-subview-hit-key="hit-1"/);
  const lineMatch = html.match(/class="subview-anchor-line is-active"[^>]*x1="([^"]+)"[^>]*y1="([^"]+)"[^>]*x2="([^"]+)"[^>]*y2="([^"]+)"/);
  assert.ok(bandMatch, "expected anchored subview hit polygon");
  assert.ok(lineMatch, "expected active anchor line");
  const [topLeft, , , bottomLeft] = bandMatch[1].split(" ");
  const [topLeftX, topBottomY] = topLeft.split(",").map(Number);
  const [bottomLeftX, bottomTopY] = bottomLeft.split(",").map(Number);

  assert.equal(Number(lineMatch[1]).toFixed(2), topLeftX.toFixed(2));
  assert.equal(Number(lineMatch[2]).toFixed(2), topBottomY.toFixed(2));
  assert.equal(Number(lineMatch[3]).toFixed(2), bottomLeftX.toFixed(2));
  assert.equal(Number(lineMatch[4]).toFixed(2), bottomTopY.toFixed(2));
});

test("anchor-enabled ctgs expose fragment hit zones instead of only whole-contig append targets", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 8,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 8,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 8, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /data-subview-fragment-key="8:1-500"[^>]*data-subview-fragment-contig-id="8"[\s\S]*class="subview-fragment-outline"/,
  );
});

test("subview fragment hover keeps track-colored outlines instead of red", () => {
  const css = readFileSync(new URL("../../../../styles/components.css", import.meta.url), "utf8");

  assert.match(
    css,
    /\.subview-fragment-outline\s*\{[\s\S]*stroke:\s*transparent/i,
  );
  assert.match(
    css,
    /\.subview-fragment-hit-zone\[data-subview-fragment-role="ref"\]:hover\s*\+\s*\.subview-fragment-outline,\s*\.subview-fragment-hit-zone\[data-subview-fragment-role="ref"\]\.is-menu-active\s*\+\s*\.subview-fragment-outline\s*\{[\s\S]*stroke:\s*#8e8e8e/i,
  );
  assert.match(
    css,
    /\.subview-fragment-hit-zone\[data-subview-fragment-role="phased"\]:hover\s*\+\s*\.subview-fragment-outline,\s*\.subview-fragment-hit-zone\[data-subview-fragment-role="phased"\]\.is-menu-active\s*\+\s*\.subview-fragment-outline\s*\{[\s\S]*stroke:\s*#2e567f/i,
  );
  assert.doesNotMatch(css, /\.subview-fragment-hit-zone:hover\s*\+\s*\.subview-fragment-outline[\s\S]*stroke:\s*red/i);
  assert.doesNotMatch(css, /\.subview-fragment-hit-zone\.is-menu-active\s*\+\s*\.subview-fragment-outline[\s\S]*stroke:\s*red/i);
});

test("subview-ctg phased anchor fragments expose hoverable phased hit zones", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        isChrPhased: true,
        supportDatasetId: 22,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "phased-source",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 1000,
            anchorStart: 100,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 501, ctgEnd: 620, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 600,
            anchorStart: 320,
            hits: [
              { refStart: 1000, refEnd: 2000, ctgStart: 101, ctgEnd: 180, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
          summary: {
            mode: "2-contig",
            top: { contigId: 2, role: "phased", contigName: "phased-source" },
            bottom: { contigId: 30, role: "support", contigName: "support-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /data-subview-fragment-role="phased"[^>]*data-subview-fragment-contig-id="2"[\s\S]*class="subview-fragment-outline"/,
  );
  assert.match(html, /data-subview-fragment-phased-track-item-id="9001"/);
  assert.match(
    html,
    /<rect\s+class="subview-fragment-hit-zone"[\s\S]*?data-subview-fragment-role="support"[\s\S]*?data-subview-fragment-contig-id="30"[\s\S]*?<title>support-bottom \| start=0 \| len=600<\/title>[\s\S]*?<\/rect>/,
  );
});

test("subview-track phased anchor fragments expose hoverable phased hit zones", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        isChrPhased: true,
        supportDatasetId: 22,
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "phased-source",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [],
          },
        ],
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 320,
            hits: [],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          activeAnchors: [{ hitKey: "pair-1", edge: "left" }],
          pairwiseEvidence: {
            key: "track-pair:phased:101:A:2|support:mother:22:30",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 2,
                subjectAssemblyCtgId: 30,
                queryStart: 500,
                queryEnd: 900,
                subjectStart: 1000,
                subjectEnd: 1400,
                strand: "+",
                alignLength: 400,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
            bottomTrack: { role: "support", source: "mother", datasetId: 22 },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /data-subview-fragment-role="phased"[^>]*data-subview-fragment-contig-id="2"[\s\S]*class="subview-fragment-outline"/,
  );
  assert.match(html, /data-subview-fragment-phased-track-item-id="9001"/);
  assert.match(
    html,
    /<rect\s+class="subview-fragment-hit-zone"[\s\S]*?data-subview-fragment-role="support"[\s\S]*?data-subview-fragment-contig-id="30"[\s\S]*?<title>support-bottom \| start=0 \| len=5000<\/title>[\s\S]*?<\/rect>/,
  );
});

test("subview track-pair mode also renders active anchors and fragment hit zones", () => {
  const stablePairHitKey = "pair:30:hit-1:2:hit-1";
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          selectedTrackARole: "primary",
          selectedTrackBRole: "support",
          activeAnchors: [{ hitKey: stablePairHitKey, edge: "left" }],
          summary: {
            mode: "track-pair",
            topTrack: { role: "support" },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(
    html,
    /class="subview-anchor-line is-active"[^>]*stroke="red"[^>]*stroke-width="3"/,
  );
  assert.match(
    html,
    new RegExp(`class="subview-anchor-hit-zone is-active"[^>]*data-subview-anchor-hit-key="${stablePairHitKey}"[^>]*data-subview-anchor-edge="left"`),
  );
  assert.match(
    html,
    /data-subview-fragment-contig-id="30"[\s\S]*data-subview-fragment-contig-id="2"/,
  );
});

test("track-pair anchors keep the same paired hit after alignment length changes", () => {
  const stablePairHitKey = "pair:30:hit-2:2:hit-2";
  const renderWithAlignmentLength = (alignmentLength) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 30,
              name: "support-top",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30000000,
              anchorStart: 320,
              hits: [
                { refStart: 2_000_000, refEnd: 2_050_000, ctgStart: 2_000_000, ctgEnd: 2_050_000, blockLength: 10_000, mapq: 60 },
                { refStart: 27_500_000, refEnd: 27_650_000, ctgStart: 26_800_000, ctgEnd: 26_950_000, blockLength: 150_000, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 2,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30000000,
              anchorStart: 100,
              hits: [
                { refStart: 2_010_000, refEnd: 2_060_000, ctgStart: 1_900_000, ctgEnd: 1_950_000, blockLength: 10_000, mapq: 60 },
                { refStart: 27_520_000, refEnd: 27_670_000, ctgStart: 27_100_000, ctgEnd: 27_250_000, blockLength: 150_000, mapq: 60 },
              ],
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 10000,
            maxTickCount: 5,
            alignmentLength,
            mapq: 0,
          },
          subview: {
            selectedTrackARole: "primary",
            selectedTrackBRole: "support",
            activeAnchors: [{ hitKey: stablePairHitKey, edge: "left" }],
            summary: {
              mode: "track-pair",
              topTrack: { role: "support" },
              bottomTrack: { role: "primary" },
            },
          },
        },
        initializer: {
          datasets: [
            { datasetId: 11, name: "hifiasm", label: "hifiasm" },
            { datasetId: 22, name: "flye", label: "flye" },
          ],
          existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
        },
      }),
    );

  const strictHtml = renderWithAlignmentLength(100000);
  const relaxedHtml = renderWithAlignmentLength(10000);

  assert.match(strictHtml, new RegExp(`data-subview-hit-key="${stablePairHitKey}"`));
  assert.match(relaxedHtml, new RegExp(`data-subview-hit-key="${stablePairHitKey}"`));
  const bandMatch = relaxedHtml.match(new RegExp(`<polygon class="track-collinearity-band is-companion" points="([^"]+)"[^>]*data-subview-hit-key="${stablePairHitKey}"`));
  const lineMatch = relaxedHtml.match(new RegExp(`class="subview-anchor-line is-active"[^>]*x1="([^"]+)"[^>]*y1="([^"]+)"[^>]*x2="([^"]+)"[^>]*y2="([^"]+)"[\\s\\S]*data-subview-anchor-hit-key="${stablePairHitKey}"`));
  assert.ok(bandMatch, "expected anchored track-pair hit polygon");
  assert.ok(lineMatch, "expected active anchored line for the stable pair key");
  const [topLeft, , , bottomLeft] = bandMatch[1].split(" ");
  const [topLeftX, topBottomY] = topLeft.split(",").map(Number);
  const [bottomLeftX, bottomTopY] = bottomLeft.split(",").map(Number);
  assert.equal(Number(lineMatch[1]).toFixed(2), topLeftX.toFixed(2));
  assert.equal(Number(lineMatch[2]).toFixed(2), topBottomY.toFixed(2));
  assert.equal(Number(lineMatch[3]).toFixed(2), bottomLeftX.toFixed(2));
  assert.equal(Number(lineMatch[4]).toFixed(2), bottomTopY.toFixed(2));
});

test("subview chart keeps longer top bar when top ctg is longer than bottom ctg", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          { assemblyCtgId: 30, name: "support-long", assignedChrName: "Chr01", memberCount: 1, totalLength: 31000000, anchorStart: 320 },
        ],
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-short", assignedChrName: "Chr01", memberCount: 1, totalLength: 3096643, anchorStart: 100 },
        ],
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-long" },
            bottom: { contigId: 2, role: "primary", contigName: "ctg-short" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const barMatches = Array.from(
    subviewSvgMatch[0].matchAll(/<rect class="track-ctg([^"]*)"[^>]*width="([^"]+)"/g),
  );
  assert.equal(barMatches.length >= 2, true);
  const topWidth = Number(barMatches[0][2]);
  const bottomWidth = Number(barMatches[1][2]);
  assert.ok(
    topWidth > bottomWidth,
    `expected top bar width > bottom bar width, got top=${topWidth}, bottom=${bottomWidth}`,
  );
});

test("subview auto-shifts the shorter contig on first render so paired hits are closer to vertical", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30000,
            anchorStart: 320,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-long" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-short" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const rectMatches = Array.from(
    subviewSvgMatch[0].matchAll(/<rect class="track-ctg([^"]*)"[^>]*x="([^"]+)"[^>]*y="([^"]+)"[^>]*width="([^"]+)"/g),
  );
  assert.ok(rectMatches.length >= 2, "expected both subview contig bars");
  const topX = Number(rectMatches[0][2]);
  const bottomX = Number(rectMatches[1][2]);
  assert.equal(topX, 0, "expected the longer reference bar to stay anchored");
  assert.ok(bottomX > 700, `expected shorter bar to auto-shift right, got x=${bottomX}`);
});

test("max-scale subview keeps svg width equal to base inner width even with a right-edge overflow label", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30_000,
            anchorStart: 320,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 24_000, ctgEnd: 27_000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-short-right-edge-overflow-label-very-very-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 2000, refEnd: 5000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          supportDsCtgLen: 0,
          minTickUnitKb: 10_000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-long" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-short-right-edge-overflow-label-very-very-long" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const innerWidthMatch = html.match(
    /class="assembly-track-scroll subview-track-scroll"[^>]*data-subview-inner-width="([^"]+)"/,
  );
  assert.ok(innerWidthMatch, "expected subview base inner width");
  const innerWidth = Number(innerWidthMatch[1]);

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const svgWidthMatch = subviewSvgMatch[0].match(/<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected subview svg width");
  const svgWidth = Number(svgWidthMatch[1]);

  assert.equal(
    svgWidth,
    innerWidth,
    `expected max-scale subview svg width ${svgWidth} to match base inner width ${innerWidth}`,
  );
});

test("subview keeps automatic shorter-track alignment without exposing drag metadata", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 401,
            name: "support-long",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 30000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 201,
            name: "primary-short",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 10000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 401,
          selectedARole: "support",
          selectedBContigId: 201,
          selectedBRole: "primary",
          summary: {
            mode: "2-contig",
            top: { contigId: 401, role: "support" },
            bottom: { contigId: 201, role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.doesNotMatch(html, /data-subview-track-draggable=/);
  assert.doesNotMatch(html, /data-subview-track-offset-bp=/);
  assert.doesNotMatch(html, /data-subview-track-offset-source=/);
  assert.doesNotMatch(html, /manualTrackOffset/);
});

test("subview drag offsets move only subview bars and remain independent from main-view bars", () => {
  const sharedAssembly = {
    supportDatasetId: 22,
    supportChrCtgs: [
      {
        assemblyCtgId: 401,
        name: "support-short",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 5000,
        anchorStart: 320,
        hits: [
          { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
        ],
      },
    ],
    chrCtgs: [
      {
        assemblyCtgId: 201,
        name: "primary-long",
        assignedChrName: "Chr01",
        memberCount: 1,
        totalLength: 30000,
        anchorStart: 100,
        hits: [
          { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
        ],
      },
    ],
    subviewTrackView: {
      minTickUnitKb: 10000,
      maxTickCount: 10,
      alignmentLength: 1000,
      mapq: 0,
    },
    subview: {
      mode: "2-contig",
      selectedAContigId: 401,
      selectedARole: "support",
      selectedBContigId: 201,
      selectedBRole: "primary",
      summary: {
        mode: "2-contig",
        top: { contigId: 401, role: "support" },
        bottom: { contigId: 201, role: "primary" },
      },
    },
  };
  const baseHtml = renderAssemblyPage(
    createState({
      assembly: {
        ...sharedAssembly,
        subviewTrackDragOffsets: [],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );
  const shiftedHtml = renderAssemblyPage(
    createState({
      assembly: {
        ...sharedAssembly,
        subviewTrackDragOffsets: [{ slot: "top", contigId: 401, offsetPx: 60 }],
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const extractSubviewSlotX = (html, slot) => {
    const match = html.match(new RegExp(`<g[^>]*data-subview-track-slot="${slot}"[^>]*data-subview-rect-x="([^"]+)"`));
    assert.ok(match, `expected subview ${slot} bar`);
    return Number(match[1]);
  };
  const extractMainTrackRectX = (html, trackRole, contigId) => {
    const match = html.match(
      new RegExp(`data-track-contig-id="${contigId}"[^>]*data-track-role="${trackRole}"[^>]*data-track-rect-x="([^"]+)"`),
    );
    assert.ok(match, `expected ${trackRole} track bar for ctg ${contigId}`);
    return Number(match[1]);
  };

  const baseTopX = extractSubviewSlotX(baseHtml, "top");
  const shiftedTopX = extractSubviewSlotX(shiftedHtml, "top");
  assert.ok(Math.abs((shiftedTopX - baseTopX) - 60) < 0.1, `expected subview top x shift by 60px, got ${shiftedTopX - baseTopX}`);

  const baseMainPrimaryX = extractMainTrackRectX(baseHtml, "primary", 201);
  const shiftedMainPrimaryX = extractMainTrackRectX(shiftedHtml, "primary", 201);
  assert.equal(shiftedMainPrimaryX, baseMainPrimaryX);

  const baseMainSupportX = extractMainTrackRectX(baseHtml, "support", 401);
  const shiftedMainSupportX = extractMainTrackRectX(shiftedHtml, "support", 401);
  assert.equal(shiftedMainSupportX, baseMainSupportX);
});

test("subview allows dragging the full-width longer ctg bar", () => {
  const buildHtml = (subviewTrackDragOffsets = []) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 401,
              name: "support-long",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30000,
              anchorStart: 320,
              hits: [
                { refStart: 5000, refEnd: 8000, ctgStart: 24000, ctgEnd: 27000, blockLength: 3000, mapq: 60 },
              ],
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 201,
              name: "primary-short",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 5000,
              anchorStart: 100,
              hits: [
                { refStart: 5000, refEnd: 8000, ctgStart: 1000, ctgEnd: 4000, blockLength: 3000, mapq: 60 },
              ],
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 10000,
            maxTickCount: 10,
            alignmentLength: 1000,
            mapq: 0,
          },
          subview: {
            mode: "2-contig",
            selectedAContigId: 401,
            selectedARole: "support",
            selectedBContigId: 201,
            selectedBRole: "primary",
            summary: {
              mode: "2-contig",
              top: { contigId: 401, role: "support" },
              bottom: { contigId: 201, role: "primary" },
            },
          },
          subviewTrackDragOffsets,
        },
        initializer: {
          datasets: [
            { datasetId: 11, name: "hifiasm", label: "hifiasm" },
            { datasetId: 22, name: "flye", label: "flye" },
          ],
          existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
        },
      }),
    );
  const extractTopX = (html) => {
    const match = html.match(
      /data-subview-track-slot="top"[\s\S]*?data-subview-contig-id="401"[\s\S]*?data-subview-rect-x="([^"]+)"/,
    );
    assert.ok(match, "expected full-width top subview bar");
    return Number(match[1]);
  };

  const baseTopX = extractTopX(buildHtml([]));
  const shiftedRightTopX = extractTopX(buildHtml([{ slot: "top", contigId: 401, offsetPx: 60 }]));
  const shiftedLeftTopX = extractTopX(buildHtml([{ slot: "top", contigId: 401, offsetPx: -60 }]));

  assert.ok(Math.abs((shiftedRightTopX - baseTopX) - 60) < 0.1, `expected full-width top x shift right by 60px, got ${shiftedRightTopX - baseTopX}`);
  assert.ok(Math.abs((shiftedLeftTopX - baseTopX) + 60) < 0.1, `expected full-width top x shift left by 60px, got ${shiftedLeftTopX - baseTopX}`);
});

test("subview collinearity pairing follows reference overlap instead of raw index order", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10000,
            anchorStart: 320,
            hits: [
              { refStart: 100, refEnd: 1100, ctgStart: 200, ctgEnd: 1200, blockLength: 1200, mapq: 60 },
              { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10000,
            anchorStart: 100,
            hits: [
              { refStart: 100, refEnd: 1100, ctgStart: 260, ctgEnd: 1260, blockLength: 1200, mapq: 60 },
              { refStart: 2500, refEnd: 2800, ctgStart: 9000, ctgEnd: 9300, blockLength: 1200, mapq: 60 },
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const svgMarkup = subviewSvgMatch[0];
  const svgWidthMatch = svgMarkup.match(/<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"/);
  assert.ok(svgWidthMatch, "expected subview svg width");
  const svgWidth = Number(svgWidthMatch[1]);
  const polygons = Array.from(
    svgMarkup.matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.equal(polygons.length, 2, "expected two paired subview bands");
  const secondBandPointList = polygons[1][1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const secondBandBottomStartX = secondBandPointList[3][0];
  assert.ok(
    secondBandBottomStartX < svgWidth * 0.6,
    `expected second band to pair with overlapping ref hit instead of far-right noise, got bottomStartX=${secondBandBottomStartX}, svgWidth=${svgWidth}`,
  );
});

test("subview bands skip non-overlapping hit pairs to avoid noisy cross-region links", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10000,
            anchorStart: 320,
            hits: [
              { refStart: 100, refEnd: 1200, ctgStart: 100, ctgEnd: 1200, blockLength: 1200, mapq: 60 },
              { refStart: 7000, refEnd: 8200, ctgStart: 2100, ctgEnd: 3300, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 10000,
            anchorStart: 100,
            hits: [
              { refStart: 100, refEnd: 1200, ctgStart: 140, ctgEnd: 1240, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = Array.from(
    subviewSvgMatch[0].matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.equal(polygons.length, 1, "expected only one overlapping band");
});

test("subview ctg waits for pairwise evidence instead of inferring ds-ds bands from broad ref overlap", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-small",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 100, ctgEnd: 1300, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 40000,
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          pairwiseEvidence: {
            key: "2-contig:support:30:primary:2",
            status: "loading",
            hits: [],
          },
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-small" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-broad" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  assert.doesNotMatch(
    subviewSvgMatch[0],
    /<polygon class="track-collinearity-band is-companion"/,
    "expected no inferred ds-ds band while true pairwise evidence is loading",
  );
  assert.match(html, /data-subview-pairwise-loading="1"/);
  assert.match(html, /data-subview-pairwise-cancel="1"/);
});

test("subview track-pair waits for pairwise evidence instead of inferring ds-ds bands from ref overlap", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 50000,
            anchorStart: 320,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 50000,
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|primary:2",
            status: "loading",
            hits: [],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22 },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  assert.doesNotMatch(
    subviewSvgMatch[0],
    /<polygon class="track-collinearity-band is-companion"/,
    "expected no inferred ds-ds track-pair band while true pairwise evidence is loading",
  );
  assert.match(html, /data-subview-pairwise-loading="1"/);
  assert.match(html, /data-subview-pairwise-cancel="1"/);
});

test("cancelSubviewPairwiseEvidence reverts subview filters to the loaded cache floor", () => {
  let state = createState({
    assembly: {
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 5000,
        mapq: 0,
      },
      subview: {
        mode: "2-contig",
        summary: {
          mode: "2-contig",
          top: { contigId: 30, role: "support", contigName: "support-small" },
          bottom: { contigId: 2, role: "primary", contigName: "primary-broad" },
        },
        pairwiseEvidence: {
          key: "2-contig:support:30:primary:2",
          requestKey: "2-contig:support:30:primary:2|req:9",
          status: "loading",
          requestedMinAlignmentLength: 5000,
          requestedMinMapq: 0,
          loadedMinAlignmentLength: 10000,
          loadedMinMapq: 0,
          hits: [
            {
              queryAssemblyCtgId: 30,
              subjectAssemblyCtgId: 2,
              queryStart: 100,
              queryEnd: 1300,
              subjectStart: 20000,
              subjectEnd: 21200,
              alignLength: 1200,
              mapq: 60,
            },
          ],
        },
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
  let rerenders = 0;

  const cancelled = __testCancelSubviewPairwiseEvidence({}, store, {
    rerender: () => {
      rerenders += 1;
    },
  });

  assert.equal(cancelled, true);
  assert.equal(store.getState().assembly.subviewTrackView.alignmentLength, 10000);
  assert.equal(store.getState().assembly.subviewTrackView.mapq, 0);
  assert.equal(store.getState().assembly.subview.pairwiseEvidence.status, "loaded");
  assert.equal(store.getState().assembly.subview.pairwiseEvidence.requestKey, "");
  assert.equal(rerenders, 1);
});

test("subview ctg uses true pairwise paf intervals for ds-ds bands", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-small",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 100, ctgEnd: 1300, blockLength: 1200, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 40000,
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 40000, ctgStart: 1, ctgEnd: 40000, blockLength: 40000, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          pairwiseEvidence: {
            key: "2-contig:support:30:primary:2",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 100,
                queryEnd: 1300,
                subjectStart: 20000,
                subjectEnd: 21200,
                strand: "-",
                alignLength: 1200,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-small" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-broad" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const topWidth = Math.abs(pointList[1][0] - pointList[0][0]);
  const bottomWidth = Math.abs(pointList[2][0] - pointList[3][0]);
  assert.ok(topWidth < 100, `expected top band to use local paf width, got ${topWidth}`);
  assert.ok(bottomWidth < 100, `expected bottom band to use local paf width, got ${bottomWidth}`);
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected negative-strand subview ctg band to cross, got ${JSON.stringify(pointList)}`,
  );
});

test("subview ctg pairwise bands mirror phased item orientation", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-left",
            assignedChrName: "Chr01",
            totalLength: 1000,
            anchorStart: 300,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 1, ctgEnd: 1000, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-forward",
            assignedChrName: "Chr01",
            totalLength: 1000,
            orient: "+",
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 101, ctgEnd: 200, blockLength: 100, mapq: 60 },
            ],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, orient: "-" },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 50,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          pairwiseEvidence: {
            key: "2-contig:support:30:phased:2:9001:101:A",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 101,
                queryEnd: 200,
                subjectStart: 101,
                subjectEnd: 200,
                strand: "+",
                alignLength: 100,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support" },
            bottom: {
              contigId: 2,
              role: "phased",
              phasedTrackId: 101,
              phasedTrackItemId: 9001,
              phasedHaplotypeKey: "A",
            },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const topCenter = (pointList[0][0] + pointList[1][0]) / 2;
  const bottomCenter = (pointList[2][0] + pointList[3][0]) / 2;
  assert.ok(
    bottomCenter - topCenter > 300,
    `expected phased bottom range to be mirrored to the right, got ${JSON.stringify(pointList)}`,
  );
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected phased one-sided mirror to make the positive-strand pairwise band cross, got ${JSON.stringify(pointList)}`,
  );
});

test("phased track contigs can be selected as subview-ctg candidates", () => {
  const nextSubview = __testSelectSubviewCandidate({
    subview: {},
    trackRole: "phased",
    contigId: 2,
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
    phasedHaplotypeKey: "A",
    stateOrLocale: "zh",
  });

  assert.deepEqual(nextSubview.selectedAContigId, 2);
  assert.equal(nextSubview.selectedARole, "phased");
  assert.equal(nextSubview.selectedAPhasedTrackId, 101);
  assert.equal(nextSubview.selectedAPhasedTrackItemId, 9001);
  assert.equal(nextSubview.selectedAPhasedHaplotypeKey, "A");
});

test("phased track labels preserve identity for subview-track selection", () => {
  const afterPrimary = __testSelectSubviewTrack({
    subview: {},
    trackRole: "primary",
    stateOrLocale: "zh",
  });
  const afterPhased = __testSelectSubviewTrack({
    subview: afterPrimary,
    trackRole: "phased",
    phasedTrackId: 101,
    haplotypeKey: "A",
    stateOrLocale: "zh",
  });

  assert.deepEqual(afterPhased.selectedTrackSelections, [
    { role: "primary", source: "mother", datasetId: null, isMirror: false },
    {
      role: "phased",
      source: "mother",
      datasetId: null,
      isMirror: false,
      phasedTrackId: 101,
      haplotypeKey: "A",
    },
  ]);
  assert.equal(afterPhased.summary?.bottomTrack?.phasedTrackId, 101);
});

test("subview track-pair uses true pairwise paf intervals for ds-ds bands", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|primary:2",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 150,
                queryEnd: 310,
                subjectStart: 700,
                subjectEnd: 950,
                strand: "-",
                alignLength: 160,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22 },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 150-310 bp[^"]*primary-bottom: 700-950 bp/);
  assert.doesNotMatch(html, /support-top: 2,200-3,400 bp/);
  assert.doesNotMatch(html, /primary-bottom: 2,400-3,600 bp/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected negative-strand subview track-pair band to cross, got ${JSON.stringify(pointList)}`,
  );
});

test("subview track-pair pairwise bands mirror phased item orientation", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-left",
            assignedChrName: "Chr01",
            totalLength: 1000,
            anchorStart: 300,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 1, ctgEnd: 1000, blockLength: 1000, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-forward",
            assignedChrName: "Chr01",
            totalLength: 1000,
            orient: "+",
            anchorStart: 100,
            hits: [
              { refStart: 1, refEnd: 1000, ctgStart: 101, ctgEnd: 200, blockLength: 100, mapq: 60 },
            ],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            items: [
              { itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, orient: "-" },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1,
          maxTickCount: 10,
          alignmentLength: 50,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|phased:101:A:2",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 101,
                queryEnd: 200,
                subjectStart: 101,
                subjectEnd: 200,
                strand: "+",
                alignLength: 100,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22 },
            bottomTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  const topCenter = (pointList[0][0] + pointList[1][0]) / 2;
  const bottomCenter = (pointList[2][0] + pointList[3][0]) / 2;
  assert.ok(
    bottomCenter - topCenter > 50,
    `expected phased track-pair range to be mirrored to the right, got ${JSON.stringify(pointList)}`,
  );
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected phased one-sided mirror to make the positive-strand track-pair band cross, got ${JSON.stringify(pointList)}`,
  );
});

test("subview track-pair skips same-contig hits and shows the skipped hint", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        isChrPhased: true,
        activePhasedTrackKey: "A",
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "ptg000004l",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [],
          },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            label: "Chr01A",
            displayOrder: 1,
            items: [
              {
                itemId: 9001,
                phasedTrackId: 101,
                assemblyCtgId: 2,
                displayOrder: 1,
              },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          pairwiseEvidence: {
            key: "track-pair:primary:2|phased:101:A:2",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 2,
                subjectAssemblyCtgId: 2,
                queryStart: 100,
                queryEnd: 220,
                subjectStart: 700,
                subjectEnd: 820,
                strand: "+",
                alignLength: 120,
                mapq: 60,
              },
              {
                hitKey: "pair-2",
                queryAssemblyCtgId: 2,
                subjectAssemblyCtgId: 2,
                queryStart: 700,
                queryEnd: 820,
                subjectStart: 100,
                subjectEnd: 220,
                strand: "+",
                alignLength: 120,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "primary" },
            bottomTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
    }),
  );

  assert.match(html, /<h4>Subview <span class="subview-same-contig-warning">同 ctg 比对已跳过，故无 hits<\/span><\/h4>/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const bandMatches = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band[^"]*" points="[^"]+"/g) || [];
  assert.equal(bandMatches.length, 0, `expected same-contig self hits to be skipped, got ${bandMatches.length}`);
});

test("subview ctg pairwise bands mirror local flips and toggle band direction", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-small",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 3000,
            anchorStart: 320,
            hits: [],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-broad",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 40000,
            anchorStart: 100,
            hits: [],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          flippedCtgs: [{ slot: "bottom", contigId: 2 }],
          pairwiseEvidence: {
            key: "2-contig:support:30:primary:2",
            status: "loaded",
            hits: [
              {
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 100,
                queryEnd: 1300,
                subjectStart: 20000,
                subjectEnd: 21200,
                strand: "+",
                alignLength: 1200,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-small" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-broad" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /data-subview-band-tooltip="[^"]*support-small: 100-1,300 bp[^"]*primary-broad: 18,801-20,001 bp/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected one-sided local flip to cross the subview ctg band, got ${JSON.stringify(pointList)}`,
  );
});

test("subview track-pair pairwise bands mirror local flips and toggle band direction", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 4000,
            anchorStart: 320,
            hits: [],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 5000,
            anchorStart: 100,
            hits: [],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 100,
          mapq: 0,
        },
        subview: {
          mode: "track-pair",
          flippedCtgs: [{ slot: "top", contigId: 30 }],
          pairwiseEvidence: {
            key: "track-pair:support:mother:22:30|primary:2",
            status: "loaded",
            hits: [
              {
                hitKey: "pair-1",
                queryAssemblyCtgId: 30,
                subjectAssemblyCtgId: 2,
                queryStart: 150,
                queryEnd: 310,
                subjectStart: 700,
                subjectEnd: 950,
                strand: "+",
                alignLength: 160,
                mapq: 60,
              },
            ],
          },
          summary: {
            mode: "track-pair",
            topTrack: { role: "support", source: "mother", datasetId: 22 },
            bottomTrack: { role: "primary" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 3,691-3,851 bp[^"]*primary-bottom: 700-950 bp/);
  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview track-pair svg");
  const polygonMatch = subviewSvgMatch[0].match(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/);
  assert.ok(polygonMatch, "expected a pairwise paf band");
  const pointList = polygonMatch[1]
    .split(/\s+/)
    .map((point) => point.split(",").map((value) => Number(value)));
  assert.ok(
    pointList[2][0] < pointList[3][0],
    `expected one-sided local flip to cross the subview track-pair band, got ${JSON.stringify(pointList)}`,
  );
});

test("subview bands expose only top and bottom ctg interval tooltip payload with 500ms hover delay config", () => {
  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 320,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2200, ctgEnd: 3400, blockLength: 1300, mapq: 60 },
            ],
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 20000,
            anchorStart: 100,
            hits: [
              { refStart: 5000, refEnd: 6200, ctgStart: 2400, ctgEnd: 3600, blockLength: 1400, mapq: 60 },
            ],
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  assert.match(html, /data-subview-band-tooltip-delay-ms="500"/);
  assert.match(html, /class="subview-band-tooltip is-hidden"/);
  assert.match(html, /data-subview-band-tooltip="[^"]*support-top: 2,200-3,400 bp[^"]*primary-bottom: 2,400-3,600 bp/);
  assert.match(html, /class="track-band-canvas-layer"[^>]*data-track-band-canvas-scene-kind="subview-ctg"/);
  assert.match(html, /<canvas class="track-band-canvas"[^>]*data-track-band-canvas="1"/);
  assert.match(html, /<polygon class="track-collinearity-band is-companion"[^>]*pointer-events="visibleFill"[^>]*data-track-band-proxy="1"/);
  assert.match(html, /class="track-ctg subview-track-ctg is-companion"[^>]*pointer-events="all"/);
  assert.match(html, /class="track-ctg subview-track-ctg"[^>]*pointer-events="all"/);
  assert.doesNotMatch(html, /data-subview-band-tooltip="[^"]*Ref:/);
});

test("subview low alignment threshold keeps right-side coverage instead of left-biased saturation", () => {
  const leftDenseHits = Array.from({ length: 300 }, (_, index) => {
    const refStart = 1000 + index * 500;
    return {
      refStart,
      refEnd: refStart + 1200,
      ctgStart: 2000 + index * 30,
      ctgEnd: 2000 + index * 30 + 1200,
      blockLength: 1200,
      mapq: 60,
    };
  });
  const rightLongHits = Array.from({ length: 20 }, (_, index) => {
    const refStart = 18_000_000 + index * 300_000;
    const ctgStart = 22_000_000 + index * 150_000;
    return {
      refStart,
      refEnd: refStart + 12_000,
      ctgStart,
      ctgEnd: ctgStart + 12_000,
      blockLength: 12_000,
      mapq: 60,
    };
  });
  const sharedTopHits = [...leftDenseHits, ...rightLongHits];
  const sharedBottomHits = [...leftDenseHits, ...rightLongHits];

  const buildHtml = (alignmentLength) =>
    renderAssemblyPage(
      createState({
        assembly: {
          supportDatasetId: 22,
          supportChrCtgs: [
            {
              assemblyCtgId: 30,
              name: "support-top",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30_000_000,
              anchorStart: 320,
              hits: sharedTopHits,
            },
          ],
          chrCtgs: [
            {
              assemblyCtgId: 2,
              name: "primary-bottom",
              assignedChrName: "Chr01",
              memberCount: 1,
              totalLength: 30_000_000,
              anchorStart: 100,
              hits: sharedBottomHits,
            },
          ],
          subviewTrackView: {
            minTickUnitKb: 10000,
            maxTickCount: 10,
            alignmentLength,
            mapq: 0,
          },
          subview: {
            mode: "2-contig",
            selectedAContigId: 2,
            selectedARole: "primary",
            selectedBContigId: 30,
            selectedBRole: "support",
            message: "",
            error: "",
            summary: {
              mode: "2-contig",
              top: { contigId: 30, role: "support", contigName: "support-top" },
              bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
            },
          },
        },
        initializer: {
          datasets: [
            { datasetId: 11, name: "hifiasm", label: "hifiasm" },
            { datasetId: 22, name: "flye", label: "flye" },
          ],
          existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
        },
      }),
    );

  const lowThresholdHtml = buildHtml(1000);
  const highThresholdHtml = buildHtml(10000);
  const extractMaxBandX = (html) => {
    const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
    assert.ok(subviewSvgMatch, "expected subview svg");
    const svgMarkup = subviewSvgMatch[0];
    const svgWidthMatch = svgMarkup.match(/<svg class="assembly-track-svg subview-track-svg" width="([^"]+)"/);
    assert.ok(svgWidthMatch, "expected subview svg width");
    const svgWidth = Number(svgWidthMatch[1]);
    const polygons = Array.from(
      svgMarkup.matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
    );
    assert.ok(polygons.length > 0, "expected subview band polygons");
    const maxX = Math.max(
      ...polygons.flatMap((polygon) =>
        polygon[1].split(/\s+/).map((point) => Number(point.split(",")[0])),
      ),
    );
    return { maxX, svgWidth };
  };

  const lowThresholdRange = extractMaxBandX(lowThresholdHtml);
  const highThresholdRange = extractMaxBandX(highThresholdHtml);
  assert.ok(
    lowThresholdRange.maxX > lowThresholdRange.svgWidth * 0.7,
    `expected low-threshold view to retain right-side bands, got maxX=${lowThresholdRange.maxX}, svgWidth=${lowThresholdRange.svgWidth}`,
  );
  assert.ok(
    highThresholdRange.maxX > highThresholdRange.svgWidth * 0.7,
    `expected high-threshold view to show right-side bands, got maxX=${highThresholdRange.maxX}, svgWidth=${highThresholdRange.svgWidth}`,
  );
});

test("subview renders all passed overlapping hit pairs without a fixed band cap", () => {
  const overlapHits = Array.from({ length: 260 }, (_, index) => {
    const refStart = 10_000 + index * 20_000;
    const ctgStart = 50_000 + index * 20_000;
    return {
      refStart,
      refEnd: refStart + 5_000,
      ctgStart,
      ctgEnd: ctgStart + 5_000,
      blockLength: 5_000,
      mapq: 60,
    };
  });

  const html = renderAssemblyPage(
    createState({
      assembly: {
        supportDatasetId: 22,
        supportChrCtgs: [
          {
            assemblyCtgId: 30,
            name: "support-top",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 6_000_000,
            anchorStart: 320,
            hits: overlapHits,
          },
        ],
        chrCtgs: [
          {
            assemblyCtgId: 2,
            name: "primary-bottom",
            assignedChrName: "Chr01",
            memberCount: 1,
            totalLength: 6_000_000,
            anchorStart: 100,
            hits: overlapHits,
          },
        ],
        subviewTrackView: {
          minTickUnitKb: 1000,
          maxTickCount: 10,
          alignmentLength: 1000,
          mapq: 0,
        },
        subview: {
          mode: "2-contig",
          selectedAContigId: 2,
          selectedARole: "primary",
          selectedBContigId: 30,
          selectedBRole: "support",
          message: "",
          error: "",
          summary: {
            mode: "2-contig",
            top: { contigId: 30, role: "support", contigName: "support-top" },
            bottom: { contigId: 2, role: "primary", contigName: "primary-bottom" },
          },
        },
      },
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm" },
          { datasetId: 22, name: "flye", label: "flye" },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
      },
    }),
  );

  const subviewSvgMatch = html.match(/<svg class="assembly-track-svg subview-track-svg"[\s\S]*?<\/svg>/);
  assert.ok(subviewSvgMatch, "expected subview svg");
  const polygons = Array.from(
    subviewSvgMatch[0].matchAll(/<polygon class="track-collinearity-band is-companion" points="([^"]+)"/g),
  );
  assert.equal(polygons.length, 260, "expected every overlapping hit pair to be rendered");
});

test("track-driven subview selection enters Subview-ctg immediately after selecting the second candidate", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
      ],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 }],
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 8 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 30 });

  const subview = store.getState().assembly.subview;
  assert.equal(subview.summary?.mode, "2-contig");
  assert.equal(subview.summary?.top?.contigId, 30);
  assert.equal(subview.summary?.bottom?.contigId, 8);
  assert.equal(subview.message, "Subview 已进入。");
  assert.equal(subview.error, "");
});

test("enterSubviewFromCandidates copies main-track scale prefs into subviewTrackView", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      trackView: {
        supportDsCtgLen: 10000,
        minTickUnitKb: 750,
        maxTickCount: 18,
        alignmentLength: 12345,
        mapq: 31,
      },
      subviewTrackView: {
        supportDsCtgLen: 0,
        minTickUnitKb: 10000,
        maxTickCount: 10,
        alignmentLength: 1000,
        mapq: 0,
      },
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
      ],
      supportChrCtgs: [{ assemblyCtgId: 30, name: "support-ctg", totalLength: 15000, anchorStart: 320 }],
      subview: {
        mode: "2-contig",
        selectedAContigId: 8,
        selectedARole: "primary",
        selectedBContigId: 30,
        selectedBRole: "support",
        message: "",
        error: "",
        summary: null,
      },
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testEnterSubviewFromCandidates(host, store);

  assert.deepEqual(store.getState().assembly.subviewTrackView, {
    supportDsCtgLen: 10000,
    minTickUnitKb: 750,
    minTickKb: 750,
    maxTickCount: 18,
    alignmentLength: 12345,
    block_length: 12345,
    mapq: 31,
  });
});

test("track-driven subview selection blocks same-ds contigs when self alignment is unavailable", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
    },
    assembly: {
      supportDatasetId: null,
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", datasetId: 11, anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", datasetId: 11, anchorStart: 500 },
      ],
      supportChrCtgs: [],
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 8 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 2 });

  const subview = store.getState().assembly.subview;
  assert.equal(subview.summary, null);
  assert.equal(subview.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
});

test("track-driven subview selection blocks primary-phased and phased-phased same-ds contigs when self alignment is unavailable", () => {
  const host = {
    closest() {
      return null;
    },
  };
  const scenarios = [
    {
      picks: [
        { trackRole: "primary", contigId: 8 },
        { trackRole: "phased", contigId: 2 },
      ],
      expectedSelections: [
        { contigId: 8, role: "primary" },
        { contigId: 2, role: "phased" },
      ],
    },
    {
      picks: [
        { trackRole: "phased", contigId: 8 },
        { trackRole: "phased", contigId: 2 },
      ],
      expectedSelections: [
        { contigId: 8, role: "phased" },
        { contigId: 2, role: "phased" },
      ],
    },
  ];

  for (const { picks, expectedSelections } of scenarios) {
    let state = createState({
      initializer: {
        datasets: [
          { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
        ],
        existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [] }],
      },
      assembly: {
        supportDatasetId: null,
        chrCtgs: [
          { assemblyCtgId: 2, name: "ctg-alpha", datasetId: 11, anchorStart: 100 },
          { assemblyCtgId: 8, name: "ctg-beta", datasetId: 11, anchorStart: 500 },
        ],
        phasedChrTracks: [
          {
            phasedTrackId: 101,
            haplotypeKey: "A",
            items: [{ itemId: 9001, phasedTrackId: 101, assemblyCtgId: 2, displayOrder: 1 }],
          },
          {
            phasedTrackId: 102,
            haplotypeKey: "B",
            items: [{ itemId: 9002, phasedTrackId: 102, assemblyCtgId: 8, displayOrder: 1 }],
          },
        ],
        supportChrCtgs: [],
      },
    });
    const store = {
      getState() {
        return state;
      },
      setState(nextState) {
        state = {
          ...state,
          ...nextState,
        };
      },
    };

    for (const pick of picks) {
      __testHandleTrackSubviewCandidateSelection(host, store, pick);
    }

    const subview = store.getState().assembly.subview;
    assert.deepEqual(
      [
        { contigId: subview.selectedAContigId, role: subview.selectedARole },
        { contigId: subview.selectedBContigId, role: subview.selectedBRole },
      ],
      expectedSelections,
    );
    assert.equal(subview.summary, null);
    assert.equal(subview.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
  }
});

test("buildSubviewSummaryFromTrackSelections blocks same primary-dataset phased track pairs when self alignment is unavailable", () => {
  const state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
        { datasetId: 22, name: "flye", label: "flye", selfAlignmentAvailable: true },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });
  const scenarios = [
    [
      { role: "primary", source: "mother", datasetId: null, isMirror: false },
      { role: "phased", source: "mother", datasetId: null, isMirror: false, phasedTrackId: 101, haplotypeKey: "A" },
    ],
    [
      { role: "phased", source: "mother", datasetId: null, isMirror: false, phasedTrackId: 101, haplotypeKey: "A" },
      { role: "phased", source: "mother", datasetId: null, isMirror: false, phasedTrackId: 102, haplotypeKey: "B" },
    ],
  ];

  for (const selectedTrackSelections of scenarios) {
    const result = __testBuildSubviewSummaryFromTrackSelections({
      subview: {
        selectedTrackSelections,
      },
      stateOrLocale: state,
    });

    assert.equal(result.ok, false);
    assert.equal(result.error, "该 dataset 未包含 self 比对，不能在同 ds ctg 间进入 Subview。");
  }
});

test("track label selection keeps cross-dataset support-phased pairs available when primary self alignment is unavailable", () => {
  const state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm", selfAlignmentAvailable: false },
        { datasetId: 22, name: "flye", label: "flye", selfAlignmentAvailable: true },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
  });

  const afterSupport = __testSelectSubviewTrack({
    subview: {},
    trackRole: "support",
    datasetId: 22,
    stateOrLocale: state,
  });
  const afterPhased = __testSelectSubviewTrack({
    subview: afterSupport,
    trackRole: "phased",
    phasedTrackId: 101,
    haplotypeKey: "A",
    stateOrLocale: state,
  });

  assert.deepEqual(afterPhased.selectedTrackSelections, [
    { role: "support", source: "mother", datasetId: 22, isMirror: false },
    {
      role: "phased",
      source: "mother",
      datasetId: null,
      isMirror: false,
      phasedTrackId: 101,
      haplotypeKey: "A",
    },
  ]);
  assert.equal(afterPhased.summary?.mode, "track-pair");
  assert.equal(afterPhased.summary?.topTrack?.role, "support");
  assert.equal(afterPhased.summary?.bottomTrack?.role, "phased");
  assert.equal(afterPhased.error, "");
});

test("track-driven subview selection re-enters Subview-ctg when Ctrl/Cmd adjusts an already-complete pair", () => {
  const host = {
    closest() {
      return null;
    },
  };
  let state = createState({
    initializer: {
      datasets: [
        { datasetId: 11, name: "hifiasm", label: "hifiasm" },
        { datasetId: 22, name: "flye", label: "flye" },
      ],
      existingProjects: [{ projectId: 7, primaryDatasetId: 11, supportDatasetIds: [22] }],
    },
    assembly: {
      supportDatasetId: 22,
      chrCtgs: [
        { assemblyCtgId: 2, name: "ctg-alpha", anchorStart: 100 },
        { assemblyCtgId: 8, name: "ctg-beta", anchorStart: 500 },
      ],
      supportChrCtgs: [
        { assemblyCtgId: 30, name: "support-ctg", anchorStart: 320 },
        { assemblyCtgId: 31, name: "support-ctg-2", anchorStart: 640 },
      ],
    },
  });
  const store = {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };

  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "primary", contigId: 8 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 30 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 30 });
  __testHandleTrackSubviewCandidateSelection(host, store, { trackRole: "support", contigId: 31 });

  const subview = store.getState().assembly.subview;
  assert.equal(subview.summary?.mode, "2-contig");
  assert.equal(subview.summary?.top?.contigId, 31);
  assert.equal(subview.summary?.bottom?.contigId, 8);
  assert.equal(subview.message, "Subview 已进入。");
  assert.equal(subview.error, "");
});

test("track-driven subview selection supports same-ds picks without support ds", () => {
  const afterFirst = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: null,
    primaryCtgs: [
      { assemblyCtgId: 8, name: "ctg-beta" },
      { assemblyCtgId: 2, name: "ctg-alpha" },
    ],
    supportCtgs: [],
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
    trackRole: "primary",
    contigId: 8,
  });
  const afterSecond = __testSelectSubviewCandidate({
    mode: "2-contig",
    primaryDatasetId: 11,
    supportDatasetId: null,
    primaryCtgs: [
      { assemblyCtgId: 8, name: "ctg-beta" },
      { assemblyCtgId: 2, name: "ctg-alpha" },
    ],
    supportCtgs: [],
    subview: afterFirst,
    trackRole: "primary",
    contigId: 2,
  });

  assert.equal(afterFirst.selectedAContigId, 8);
  assert.equal(afterFirst.selectedARole, "primary");
  assert.equal(afterFirst.error, "");
  assert.equal(afterSecond.selectedBContigId, 2);
  assert.equal(afterSecond.selectedBRole, "primary");
  assert.equal(afterSecond.summary, null);
});

test("new sequences tab loader returns API items for rendering", async () => {
  const result = await __testLoadNewSequencesTabData(
    { workspaceRoot: "/tmp/workspace", projectId: 7 },
    async () => ({
      items: [
        { assemblySeqId: 1, seqName: "seq-a", datasetName: "hifiasm", seqLength: 1000, hidden: false },
        { assemblySeqId: 2, seqName: "seq-b", datasetName: "flye", seqLength: 2000, hidden: true },
      ],
    }),
  );

  assert.deepEqual(result.items.map((item) => item.seqName), ["seq-a", "seq-b"]);
  assert.equal(result.loadedProjectId, 7);
  assert.equal(result.loadedWorkspacePath, "/tmp/workspace");
  assert.equal(result.error, "");
});

test("new sequences loader reuses cache only for matching workspace and project", () => {
  const cached = {
    error: "",
    items: [{ assemblySeqId: 1 }],
    loadedProjectId: 7,
    loadedWorkspacePath: "/tmp/workspace-a",
  };

  assert.equal(
    __testShouldReuseNewSequencesCache(cached, { workspacePath: "/tmp/workspace-a", projectId: 7 }),
    true,
  );
  assert.equal(
    __testShouldReuseNewSequencesCache(cached, { workspacePath: "/tmp/workspace-b", projectId: 7 }),
    false,
  );
  assert.equal(
    __testShouldReuseNewSequencesCache({ ...cached, error: "boom" }, { workspacePath: "/tmp/workspace-a", projectId: 7 }),
    false,
  );
});
