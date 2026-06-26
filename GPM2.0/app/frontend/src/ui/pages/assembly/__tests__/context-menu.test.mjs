import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAssemblyContextMenuItems,
  resolveAssemblyCtgContextTarget,
  resolveDeletedCtgContextTarget,
  resolveFinalPathGraphSegmentContextTarget,
  resolveSubviewAnchorEdgeContextTarget,
  resolveSubviewFragmentContextTarget,
  resolveSubviewTrackPairContextTarget,
  resolveTrackLabelContextTarget,
} from "../context-menu.js";

function createStore(assemblyOverrides = {}) {
  return {
    getState() {
      return {
        locale: "zh",
        assembly: {
          activeTab: "assembly",
          chrCtgs: [
            { assemblyCtgId: 2, name: "ctg-alpha" },
            { assemblyCtgId: 8, name: "ctg-beta" },
          ],
          trackSelectedCtgIds: [],
          selectedDeletedCtgRecordIds: [],
          hiddenPrimaryCtgIds: [],
          supportMirroredCtgs: [],
          supportDatasetId: null,
          subview: {
            summary: null,
            trackPairHiddenCtgs: [],
            trackPairSelectedCtgs: [],
          },
          ...assemblyOverrides,
        },
      };
    },
  };
}

function createContextMenuActionsCapture(calls = []) {
  const capture = (name) => (...args) => {
    calls.push({ name, args });
  };
  return {
    enterSubviewFromTrackSelections: capture("enterSubviewFromTrackSelections"),
    enterSubviewFromCandidates: capture("enterSubviewFromCandidates"),
    setSubviewTrackPairCtgHidden: capture("setSubviewTrackPairCtgHidden"),
    toggleSubviewContigFlip: capture("toggleSubviewContigFlip"),
    deleteSelectedSubviewTrackPairCtgs: capture("deleteSelectedSubviewTrackPairCtgs"),
    clearSubviewTrackPairHiddenCtgs: capture("clearSubviewTrackPairHiddenCtgs"),
    setSelectedPrimaryTrackCtgsHidden: capture("setSelectedPrimaryTrackCtgsHidden"),
    deleteSelectedTrackCtgs: capture("deleteSelectedTrackCtgs"),
    runBatchDeleteTrackCtgs: capture("runBatchDeleteTrackCtgs"),
    restoreSelectedDeletedCtgs: capture("restoreSelectedDeletedCtgs"),
    canEditTrackCtg() {
      return true;
    },
    addFinalPathContigRelativeToSegment: capture("addFinalPathContigRelativeToSegment"),
    addFinalPathGapRelativeToSegment: capture("addFinalPathGapRelativeToSegment"),
    deleteFinalPathSegment: capture("deleteFinalPathSegment"),
    flipFinalPathSegment: capture("flipFinalPathSegment"),
    toggleSupportTrackCtgMirror: capture("toggleSupportTrackCtgMirror"),
    togglePrimaryTrackCtgHidden: capture("togglePrimaryTrackCtgHidden"),
    toggleSubviewAnchorEdge: capture("toggleSubviewAnchorEdge"),
    appendTrackContigToFinalPath: capture("appendTrackContigToFinalPath"),
    addTrackContigToPhasedTrack: capture("addTrackContigToPhasedTrack"),
    removePhasedTrackItem: capture("removePhasedTrackItem"),
    deletePhasedTrack: capture("deletePhasedTrack"),
    importAddCtgIntoTrack: capture("importAddCtgIntoTrack"),
    setActiveHitsTrack: capture("setActiveHitsTrack"),
    setAssemblyActionFeedback: capture("setAssemblyActionFeedback"),
    openAssemblyContextMenuAt: capture("openAssemblyContextMenuAt"),
    applyEditorAction: capture("applyEditorAction"),
    promptForRenameCtg() {
      return "";
    },
    promptForDeleteShorterThanLength() {
      return "";
    },
    buildRenameCtgActionArgs() {
      return null;
    },
    confirm() {
      return true;
    },
    rerender: capture("rerender"),
  };
}

test("resolveAssemblyCtgContextTarget parses track node mirror metadata", () => {
  const target = {
    closest(selector) {
      if (selector !== "[data-track-contig-id][data-track-role]") {
        return null;
      }
      return {
        getAttribute(name) {
          if (name === "data-track-contig-id") return "30";
          if (name === "data-track-role") return "support";
          if (name === "data-track-is-mirror") return "1";
          if (name === "data-track-dataset-id") return "22";
          return null;
        },
      };
    },
  };

  assert.deepEqual(resolveAssemblyCtgContextTarget(target), {
    assemblyCtgId: 30,
    trackRole: "support",
    isMirror: true,
    datasetId: 22,
  });
});

test("resolveDeletedCtgContextTarget parses deleted ctg target metadata", () => {
  const target = {
    closest(selector) {
      if (selector !== "[data-deleted-ctg-record-id]") {
        return null;
      }
      return {
        getAttribute(name) {
          if (name === "data-deleted-ctg-record-id") return "9101";
          if (name === "data-deleted-assembly-ctg-id") return "77";
          return null;
        },
      };
    },
  };

  assert.deepEqual(resolveDeletedCtgContextTarget(target), {
    deletedCtgRecordId: 9101,
    assemblyCtgId: 77,
  });
});

test("resolveFinalPathGraphSegmentContextTarget parses graph segment metadata", () => {
  const target = {
    closest(selector) {
      if (selector === ".final-path-card[data-final-path-view-mode='graph']") {
        return {};
      }
      if (selector === "[data-final-path-segment-id][data-final-path-segment-type]") {
        return {
          getAttribute(name) {
            if (name === "data-final-path-segment-id") return "seg-2";
            if (name === "data-final-path-segment-type") return "gap";
            return null;
          },
        };
      }
      return null;
    },
  };

  assert.deepEqual(resolveFinalPathGraphSegmentContextTarget(target), {
    segmentId: "seg-2",
    segmentType: "gap",
  });
});

test("resolveSubviewTrackPairContextTarget parses dataset and mirror metadata", () => {
  const target = {
    closest(selector) {
      if (selector !== "[data-subview-track-pair-role][data-subview-track-pair-contig-id]") {
        return null;
      }
      return {
        getAttribute(name) {
          if (name === "data-subview-track-pair-role") return "support";
          if (name === "data-subview-track-pair-contig-id") return "30";
          if (name === "data-subview-track-pair-dataset-id") return "22";
          if (name === "data-subview-track-pair-is-mirror") return "1";
          if (name === "data-subview-track-slot") return "top";
          if (name === "data-subview-track-ref-orient") return "-";
          if (name === "data-subview-track-pair-phased-track-id") return "101";
          if (name === "data-subview-track-pair-phased-track-item-id") return "9001";
          if (name === "data-subview-track-pair-phased-haplotype-key") return "A";
          return null;
        },
      };
    },
  };

  assert.deepEqual(resolveSubviewTrackPairContextTarget(target), {
    assemblyCtgId: 30,
    trackRole: "support",
    datasetId: 22,
    isMirror: true,
    slot: "top",
    refOrient: "-",
    phasedTrackId: 101,
    phasedTrackItemId: 9001,
    phasedHaplotypeKey: "A",
  });
});

test("resolveSubviewAnchorEdgeContextTarget parses anchor edge metadata", () => {
  const target = {
    closest(selector) {
      if (selector !== "[data-subview-anchor-hit-key][data-subview-anchor-edge]") {
        return null;
      }
      return {
        getAttribute(name) {
          if (name === "data-subview-anchor-hit-key") return "hit-1";
          if (name === "data-subview-anchor-edge") return "left";
          if (name === "data-subview-anchor-active") return "1";
          return null;
        },
      };
    },
  };

  assert.deepEqual(resolveSubviewAnchorEdgeContextTarget(target), {
    hitKey: "hit-1",
    edge: "left",
    active: true,
  });
});

test("resolveSubviewFragmentContextTarget parses fragment metadata", () => {
  const target = {
    closest(selector) {
      if (selector !== "[data-subview-fragment-key][data-subview-fragment-contig-id]") {
        return null;
      }
      return {
        getAttribute(name) {
          if (name === "data-subview-fragment-key") return "8:1-500";
          if (name === "data-subview-fragment-contig-id") return "8";
          if (name === "data-subview-fragment-role") return "primary";
          if (name === "data-subview-fragment-start") return "1";
          if (name === "data-subview-fragment-end") return "500";
          if (name === "data-subview-fragment-ctg-name") return "Ctg8";
          if (name === "data-subview-fragment-dataset-id") return "11";
          if (name === "data-subview-fragment-is-mirror") return "0";
          if (name === "data-subview-fragment-slot") return "bottom";
          if (name === "data-subview-fragment-ref-orient") return "-";
          if (name === "data-subview-fragment-source-kind") return "ref_segment";
          if (name === "data-subview-fragment-reference-chr-id") return "1";
          if (name === "data-subview-fragment-reference-chr-name") return "Chr01";
          if (name === "data-subview-fragment-segment-start-bp") return "1001";
          if (name === "data-subview-fragment-segment-end-bp") return "2000";
          if (name === "data-subview-fragment-phased-track-id") return "102";
          if (name === "data-subview-fragment-phased-track-item-id") return "9002";
          if (name === "data-subview-fragment-phased-haplotype-key") return "B";
          return null;
        },
      };
    },
  };

  assert.deepEqual(resolveSubviewFragmentContextTarget(target), {
    fragmentKey: "8:1-500",
    assemblyCtgId: 8,
    trackRole: "primary",
    start: 1,
    end: 500,
    ctgName: "Ctg8",
    datasetId: 11,
    isMirror: false,
    slot: "bottom",
    refOrient: "-",
    sourceKind: "ref_segment",
    referenceChrId: 1,
    referenceChrName: "Chr01",
    segmentStartBp: 1001,
    segmentEndBp: 2000,
    phasedTrackId: 102,
    phasedTrackItemId: 9002,
    phasedHaplotypeKey: "B",
  });
});

test("resolveTrackLabelContextTarget parses the ref track label without mirror metadata", () => {
  const target = {
    closest(selector) {
      if (selector !== "[data-track-label-role][data-track-label-selectable='1']") {
        return null;
      }
      return {
        getAttribute(name) {
          if (name === "data-track-label-role") return "ref";
          if (name === "data-track-label-source") return "mother";
          if (name === "data-track-label-is-mirror") return "0";
          if (name === "data-track-label-dataset-id") return "0";
          return null;
        },
      };
    },
  };

  assert.deepEqual(resolveTrackLabelContextTarget(target), {
    trackRole: "ref",
    source: "mother",
    isMirror: false,
    datasetId: null,
    phasedTrackId: null,
    phasedHaplotypeKey: "",
  });
});

test("buildAssemblyContextMenuItems keeps ref track context free of mirror and edit actions", () => {
  const items = buildAssemblyContextMenuItems({
    ctgContext: {
      assemblyCtgId: 9001,
      trackRole: "ref",
      isMirror: false,
      datasetId: null,
      sourceKind: "ref_segment",
      referenceChrName: "Chr01",
      segmentStart: 1,
      segmentEnd: 5000,
    },
    trackLabelContext: null,
    subviewTrackPairContext: null,
    subviewHitContext: null,
    subviewAnchorEdgeContext: null,
    subviewFragmentContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    memberNode: null,
    host: {},
    store: createStore({
      refTrackMembers: [
        {
          assemblyCtgId: 9001,
          sourceKind: "ref_segment",
          name: "ref_Chr01:1-5000",
        },
      ],
    }),
    actions: createContextMenuActionsCapture([]),
  });

  const labels = items.map((item) => item.label);
  assert.equal(labels.some((label) => /mirror/i.test(label)), false);
  assert.equal(labels.some((label) => /重命名|rename/i.test(label)), false);
  assert.equal(labels.some((label) => /翻转|flip/i.test(label)), false);
});

test("buildAssemblyContextMenuItems passes ref fragment metadata through append-to-path", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    refTrackMembers: [
      {
        assemblyCtgId: 9001,
        sourceKind: "ref_segment",
        referenceChrId: 1,
        referenceChrName: "Chr01",
        segmentStartBp: 1001,
        segmentEndBp: 2000,
        name: "ref_Chr01:1001-2000",
      },
    ],
  });

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    subviewHitContext: null,
    subviewAnchorEdgeContext: null,
    subviewFragmentContext: {
      fragmentKey: "9001:1-500",
      assemblyCtgId: 9001,
      slot: "top",
      trackRole: "ref",
      start: 1,
      end: 500,
      ctgName: "ref_Chr01:1001-2000",
      datasetId: null,
      isMirror: false,
      refOrient: "-",
      sourceKind: "ref_segment",
      referenceChrId: 1,
      referenceChrName: "Chr01",
      segmentStartBp: 1001,
      segmentEndBp: 2000,
    },
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  const item = items.find((entry) => entry.label === "Append to path");
  assert.ok(item);
  await item.run();
  assert.deepEqual(calls.at(-1), {
    name: "appendTrackContigToFinalPath",
    args: [
      host,
      store,
      {
        assemblyCtgId: 9001,
        slot: "top",
        trackRole: "ref",
        datasetId: null,
        isMirror: false,
        refOrient: "-",
        start: 1,
        end: 500,
        sourceKind: "ref_segment",
        referenceChrId: 1,
        referenceChrName: "Chr01",
        segmentStartBp: 1001,
        segmentEndBp: 2000,
      },
    ],
  });
});

test("buildAssemblyContextMenuItems shows batch actions when multiple primary track ctgs are selected", async () => {
  const store = createStore({
    trackSelectedCtgIds: [2, 8],
  });
  const calls = [];
  const host = {};

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.ok(items.some((item) => item.label === "隐藏已框选 contig（2）"));
  assert.ok(items.some((item) => item.label === "解除隐藏已框选 contig（2）"));
  assert.ok(items.some((item) => item.label === "删除已框选 contig（2）"));
  const deleteItem = items.find((item) => item.label === "删除已框选 contig（2）");
  await deleteItem.run();
  assert.deepEqual(calls.at(-1), {
    name: "deleteSelectedTrackCtgs",
    args: [host, store, [2, 8]],
  });
});

test("buildAssemblyContextMenuItems deletes primary track ctgs shorter than prompted threshold from the track label", async () => {
  const store = createStore({
    chrCtgs: [
      { assemblyCtgId: 2, name: "ctg-short-a", totalLength: 99999 },
      { assemblyCtgId: 8, name: "ctg-long", totalLength: 100000 },
      { assemblyCtgId: 13, name: "ctg-short-b", totalLength: 500 },
    ],
  });
  const calls = [];
  const host = {};
  const actions = createContextMenuActionsCapture(calls);
  actions.promptForDeleteShorterThanLength = () => "100000";
  actions.confirm = (message) => {
    calls.push({ name: "confirm", args: [message] });
    return true;
  };

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "primary",
      source: "mother",
      isMirror: false,
      datasetId: null,
    },
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });

  const item = items.find((entry) => entry.label === "删除小于指定长度的 contig...");
  assert.ok(item);
  await item.run();

  assert.deepEqual(calls, [
    {
      name: "confirm",
      args: ["将删除当前 chr 中 2 个小于 100000 bp 的主 ds contig，是否继续？"],
    },
    {
      name: "runBatchDeleteTrackCtgs",
      args: [host, store, [2, 13]],
    },
  ]);
});

test("buildAssemblyContextMenuItems waits for async shorter-than threshold input", async () => {
  const store = createStore({
    chrCtgs: [
      { assemblyCtgId: 2, name: "ctg-short-a", totalLength: 99999 },
      { assemblyCtgId: 8, name: "ctg-long", totalLength: 100000 },
      { assemblyCtgId: 13, name: "ctg-short-b", totalLength: 500 },
    ],
  });
  const calls = [];
  const host = {};
  const actions = createContextMenuActionsCapture(calls);
  let resolveThreshold = null;
  actions.promptForDeleteShorterThanLength = () => new Promise((resolve) => {
    resolveThreshold = resolve;
  });
  actions.confirm = (message) => {
    calls.push({ name: "confirm", args: [message] });
    return true;
  };

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "primary",
      source: "mother",
      isMirror: false,
      datasetId: null,
    },
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });

  const item = items.find((entry) => entry.label === "删除小于指定长度的 contig...");
  assert.ok(item);
  const pending = item.run();
  await Promise.resolve();
  assert.deepEqual(calls, []);

  resolveThreshold("100000");
  await pending;
  assert.deepEqual(calls, [
    {
      name: "confirm",
      args: ["将删除当前 chr 中 2 个小于 100000 bp 的主 ds contig，是否继续？"],
    },
    {
      name: "runBatchDeleteTrackCtgs",
      args: [host, store, [2, 13]],
    },
  ]);
});

test("buildAssemblyContextMenuItems reports when no primary ctgs are shorter than the threshold", async () => {
  const store = createStore({
    chrCtgs: [
      { assemblyCtgId: 2, name: "ctg-a", totalLength: 100000 },
      { assemblyCtgId: 8, name: "ctg-b", totalLength: 200000 },
    ],
  });
  const calls = [];
  const host = {};
  const actions = createContextMenuActionsCapture(calls);
  actions.promptForDeleteShorterThanLength = () => "100000";
  actions.confirm = (message) => {
    calls.push({ name: "confirm", args: [message] });
    return true;
  };

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: {
      trackRole: "primary",
      source: "mother",
      isMirror: false,
      datasetId: null,
    },
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions,
  });

  const item = items.find((entry) => entry.label === "删除小于指定长度的 contig...");
  assert.ok(item);
  await item.run();

  assert.deepEqual(calls, [
    {
      name: "setAssemblyActionFeedback",
      args: [host, store, {
        actionStatus: "没有小于 100000 bp 的主 ds contig。",
      }],
    },
  ]);
});

test("buildAssemblyContextMenuItems exposes track-pair flip and delete actions when summary.mode is track-pair", async () => {
  const store = createStore({
    subview: {
      summary: {
        mode: "track-pair",
      },
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
    },
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
  });
  const calls = [];
  const host = {};

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: {
      trackRole: "support",
      assemblyCtgId: 30,
      slot: "top",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.ok(items.some((item) => item.label === "翻转 contig"));
  assert.ok(items.some((item) => item.label === "在Subview中删除 contig（仅当前视图）"));
  const flipItem = items.find((item) => item.label === "翻转 contig");
  const deleteItem = items.find((item) => item.label === "在Subview中删除 contig（仅当前视图）");
  await flipItem.run();
  assert.deepEqual(calls.at(-1), {
    name: "toggleSubviewContigFlip",
    args: [host, store, {
      slot: "top",
      assemblyCtgId: 30,
    }],
  });
  await deleteItem.run();
  assert.deepEqual(calls.at(-1), {
    name: "setSubviewTrackPairCtgHidden",
    args: [host, store, { trackRole: "support", contigId: 30, hidden: true }],
  });
});

test("buildAssemblyContextMenuItems shows restore action for deleted contig selections", async () => {
  const store = createStore({
    selectedDeletedCtgRecordIds: [9101],
  });
  const calls = [];
  const host = {};

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  const item = items.find((entry) => entry.label === "撤销删除已框选 contig（1）");
  assert.ok(item);
  await item.run();
  assert.deepEqual(calls.at(-1), {
    name: "restoreSelectedDeletedCtgs",
    args: [host, store, [9101]],
  });
});

test("buildAssemblyContextMenuItems does not show enter-subview-ctg when two contig candidates are selected", () => {
  const store = createStore({
    subview: {
      mode: "2-contig",
      selectedAContigId: 2,
      selectedARole: "primary",
      selectedBContigId: 30,
      selectedBRole: "support",
      message: "",
      error: "",
      summary: null,
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
    },
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host: {},
    actions: createContextMenuActionsCapture(),
  });

  assert.ok(items.every((item) => item.label !== "进入Subview-ctg"));
});

test("buildAssemblyContextMenuItems does not show track-mode Subview entry in main-view context menu", () => {
  const store = createStore({
    subview: {
      selectedTrackSelections: [
        { role: "primary", source: "mother", datasetId: 11, isMirror: false },
        { role: "support", source: "mother", datasetId: 22, isMirror: false },
      ],
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
      summary: null,
    },
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host: {},
    actions: createContextMenuActionsCapture(),
  });

  assert.ok(items.every((item) => item.label !== "进入Subview-轨道"));
});

test("buildAssemblyContextMenuItems exposes anchor-on when a subview edge is inactive", async () => {
  const calls = [];
  const host = {};
  const store = createStore();
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    subviewAnchorEdgeContext: {
      hitKey: "hit-1",
      edge: "left",
      active: false,
    },
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(items.map((item) => item.label), ["anchor on"]);
  await items[0].run();
  assert.deepEqual(calls.at(-1), {
    name: "toggleSubviewAnchorEdge",
    args: [host, store, { hitKey: "hit-1", edge: "left", active: true }],
  });
});

test("buildAssemblyContextMenuItems exposes anchor-off when a subview edge is active", () => {
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    subviewAnchorEdgeContext: {
      hitKey: "hit-1",
      edge: "left",
      active: true,
    },
    memberNode: null,
    store: createStore(),
    host: {},
    actions: createContextMenuActionsCapture(),
  });

  assert.deepEqual(items.map((item) => item.label), ["anchor off"]);
});

test("buildAssemblyContextMenuItems exposes fragment append and direct flip actions in 2-contig mode", async () => {
  const calls = [];
  const host = {};
  const store = createStore();
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    subviewFragmentContext: {
      fragmentKey: "8:1-500",
      assemblyCtgId: 8,
      slot: "bottom",
      trackRole: "primary",
      start: 1,
      end: 500,
      ctgName: "Ctg8",
      datasetId: 11,
      isMirror: false,
      refOrient: "-",
    },
    memberNode: null,
    store,
    host,
    contextPoint: { clientX: 100, clientY: 120 },
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(items.map((item) => item.label), ["Append to path", "翻转 contig"]);

  await items[0].run();
  assert.deepEqual(calls.at(-1), {
    name: "appendTrackContigToFinalPath",
    args: [host, store, {
      assemblyCtgId: 8,
      slot: "bottom",
      trackRole: "primary",
      datasetId: 11,
      isMirror: false,
      refOrient: "-",
      start: 1,
      end: 500,
      sourceKind: undefined,
      referenceChrId: undefined,
      referenceChrName: undefined,
      segmentStartBp: undefined,
      segmentEndBp: undefined,
    }],
  });

  await items[1].run();
  assert.deepEqual(calls.at(-1), {
    name: "toggleSubviewContigFlip",
    args: [host, store, {
      slot: "bottom",
      assemblyCtgId: 8,
    }],
  });
});

test("buildAssemblyContextMenuItems offers phased append targets for subview-ctg fragments", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    selectedChrName: "Chr01",
    isChrPhased: true,
    phasedChrTracks: [
      { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
      { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
    ],
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    subviewFragmentContext: {
      fragmentKey: "8:1-500",
      assemblyCtgId: 8,
      slot: "bottom",
      trackRole: "primary",
      start: 1,
      end: 500,
      ctgName: "Ctg8",
      datasetId: 11,
      isMirror: false,
      refOrient: "-",
    },
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(
    items.map((item) => item.label).filter((label) => label.startsWith("append to path ")),
    ["append to path A", "append to path B"],
  );
  assert.equal(items.some((item) => item.label === "Append to path"), false);

  await items.find((item) => item.label === "append to path B").run();
  assert.deepEqual(calls.at(-1), {
    name: "appendTrackContigToFinalPath",
    args: [
      host,
      store,
      {
        assemblyCtgId: 8,
        slot: "bottom",
        trackRole: "primary",
        datasetId: 11,
        isMirror: false,
        refOrient: "-",
        start: 1,
        end: 500,
        sourceKind: undefined,
        referenceChrId: undefined,
        referenceChrName: undefined,
        segmentStartBp: undefined,
        segmentEndBp: undefined,
      },
      {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    ],
  });
});

test("buildAssemblyContextMenuItems offers all phased append targets for phased subview fragments", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    selectedChrName: "Chr01",
    isChrPhased: true,
    phasedChrTracks: [
      { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
      { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
    ],
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    subviewFragmentContext: {
      fragmentKey: "2:1-500",
      assemblyCtgId: 2,
      slot: "top",
      trackRole: "phased",
      start: 1,
      end: 500,
      ctgName: "Ctg2",
      datasetId: 11,
      isMirror: false,
      refOrient: "+",
      phasedTrackId: 101,
      phasedTrackItemId: 9001,
      phasedHaplotypeKey: "A",
    },
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(
    items.map((item) => item.label).filter((label) => label.startsWith("append to path ")),
    ["append to path A", "append to path B"],
  );

  await items.find((item) => item.label === "append to path B").run();
  assert.equal(calls.at(-1).name, "appendTrackContigToFinalPath");
  assert.equal(calls.at(-1).args[2].phasedHaplotypeKey, "A");
  assert.deepEqual(calls.at(-1).args[3], {
    targetChrName: "Chr01B",
    activePhasedTrackKey: "B",
  });
});

test("buildAssemblyContextMenuItems offers all phased append targets in subview-track mode", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    selectedChrName: "Chr01",
    isChrPhased: true,
    phasedChrTracks: [
      { phasedTrackId: 101, haplotypeKey: "A", label: "Chr01A", items: [] },
      { phasedTrackId: 102, haplotypeKey: "B", label: "Chr01B", items: [] },
    ],
    subview: {
      summary: {
        mode: "track-pair",
        topTrack: { role: "phased", phasedTrackId: 101, haplotypeKey: "A" },
        bottomTrack: { role: "primary" },
      },
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
    },
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: {
      assemblyCtgId: 2,
      slot: "top",
      trackRole: "phased",
      datasetId: null,
      isMirror: false,
      refOrient: "+",
      phasedTrackId: 101,
      phasedTrackItemId: 9001,
      phasedHaplotypeKey: "A",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(
    items.map((item) => item.label).filter((label) => label.startsWith("append to path ")),
    ["append to path A", "append to path B"],
  );

  await items.find((item) => item.label === "append to path B").run();
  assert.deepEqual(calls.at(-1), {
    name: "appendTrackContigToFinalPath",
    args: [
      host,
      store,
      {
        assemblyCtgId: 2,
        slot: "top",
        trackRole: "phased",
        datasetId: null,
        isMirror: false,
        refOrient: "+",
        phasedTrackId: 101,
        phasedTrackItemId: 9001,
        phasedHaplotypeKey: "A",
      },
      {
        targetChrName: "Chr01B",
        activePhasedTrackKey: "B",
      },
    ],
  });
});

test("buildAssemblyContextMenuItems exposes fragment-local subview actions in track-pair mode", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    subview: {
      summary: {
        mode: "track-pair",
      },
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
    },
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: null,
    subviewFragmentContext: {
      fragmentKey: "30:1-500",
      assemblyCtgId: 30,
      slot: "top",
      trackRole: "support",
      start: 1,
      end: 500,
      ctgName: "Ctg30",
      datasetId: 22,
      isMirror: false,
      refOrient: "-",
    },
    memberNode: null,
    store,
    host,
    contextPoint: { clientX: 100, clientY: 120 },
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(items.map((item) => item.label), [
    "Append to path",
    "翻转 contig",
    "在Subview中删除 contig（仅当前视图）",
  ]);

  await items[1].run();
  assert.deepEqual(calls.at(-1), {
    name: "toggleSubviewContigFlip",
    args: [host, store, {
      slot: "top",
      assemblyCtgId: 30,
    }],
  });

  await items[2].run();
  assert.deepEqual(calls.at(-1), {
    name: "setSubviewTrackPairCtgHidden",
    args: [host, store, { trackRole: "support", contigId: 30, hidden: true }],
  });
});

test("buildAssemblyContextMenuItems exposes final-path graph ctg actions", async () => {
  const calls = [];
  const host = {};
  const store = createStore();

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: {
      segmentId: "seg-1",
      segmentType: "ctg",
    },
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(
    items.map((item) => item.label),
    ["删除", "翻转", "左侧 add gap", "右侧 add gap", "左侧 add ctg", "右侧 add ctg"],
  );

  await items[2].run();
  assert.deepEqual(calls.at(-1), {
    name: "addFinalPathGapRelativeToSegment",
    args: [host, store, { segmentId: "seg-1", placement: "before" }],
  });

  await items[5].run();
  assert.deepEqual(calls.at(-1), {
    name: "addFinalPathContigRelativeToSegment",
    args: [host, store, { segmentId: "seg-1", placement: "after" }],
  });
});

test("buildAssemblyContextMenuItems exposes delete only for final-path graph gaps", async () => {
  const calls = [];
  const host = {};
  const store = createStore();

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    finalPathSegmentContext: {
      segmentId: "seg-2",
      segmentType: "gap",
    },
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  assert.deepEqual(items.map((item) => item.label), ["删除"]);
  await items[0].run();
  assert.deepEqual(calls.at(-1), {
    name: "deleteFinalPathSegment",
    args: [host, store, { segmentId: "seg-2" }],
  });
});

test("buildAssemblyContextMenuItems exposes Append to path for any main-view ctg container", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    supportDatasetId: 22,
  });

  const items = buildAssemblyContextMenuItems({
    ctgContext: {
      assemblyCtgId: 30,
      trackRole: "support",
      datasetId: 22,
      isMirror: true,
    },
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  const item = items.find((entry) => entry.label === "Append to path");
  assert.ok(item);
  await item.run();
  assert.deepEqual(calls.at(-1), {
    name: "appendTrackContigToFinalPath",
    args: [
      host,
      store,
      {
        assemblyCtgId: 30,
        trackRole: "support",
        datasetId: 22,
        isMirror: true,
      },
    ],
  });
});

test("buildAssemblyContextMenuItems routes main-view flip through local editor refresh", async () => {
  const calls = [];
  const host = {};
  const store = createStore();

  const items = buildAssemblyContextMenuItems({
    ctgContext: {
      assemblyCtgId: 2,
      trackRole: "primary",
    },
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  const item = items.find((entry) => entry.label === "翻转 contig");
  assert.ok(item);
  await item.run();
  assert.deepEqual(calls.at(-1), {
    name: "applyEditorAction",
    args: [host, store, {
      action: "flip-ctg",
      args: { assemblyCtgId: 2 },
      keepCurrentCtg: true,
      localRefresh: true,
    }],
  });
});

test("buildAssemblyContextMenuItems exposes Append to path for subview ctg containers", async () => {
  const calls = [];
  const host = {};
  const store = createStore({
    supportDatasetId: 22,
    subview: {
      summary: {
        mode: "track-pair",
      },
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
    },
  });

  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: {
      assemblyCtgId: 30,
      slot: "top",
      trackRole: "support",
      datasetId: 22,
      isMirror: false,
      refOrient: "-",
    },
    deletedCtgContext: null,
    memberNode: null,
    store,
    host,
    actions: createContextMenuActionsCapture(calls),
  });

  const item = items.find((entry) => entry.label === "Append to path");
  assert.ok(item);
  await item.run();
  assert.deepEqual(calls.at(-1), {
    name: "appendTrackContigToFinalPath",
    args: [
      host,
      store,
      {
        assemblyCtgId: 30,
        slot: "top",
        trackRole: "support",
        datasetId: 22,
        isMirror: false,
        refOrient: "-",
      },
    ],
  });
});

test("buildAssemblyContextMenuItems renders english labels when locale is en", () => {
  const store = createStore({
    trackSelectedCtgIds: [2, 8],
  });
  const items = buildAssemblyContextMenuItems({
    ctgContext: null,
    trackLabelContext: null,
    subviewTrackPairContext: null,
    deletedCtgContext: null,
    memberNode: null,
    store: {
      getState() {
        return {
          ...store.getState(),
          locale: "en",
        };
      },
    },
    host: {},
    actions: createContextMenuActionsCapture([]),
  });

  assert.ok(items.some((item) => item.label === "Hide Selected Contigs (2)"));
  assert.ok(items.some((item) => item.label === "Show Selected Contigs (2)"));
  assert.ok(items.some((item) => item.label === "Delete Selected Contigs (2)"));
});
