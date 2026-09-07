import { test, assert, createState, createStore, renderAssemblyPage } from "./tabs-semantics-harness.mjs";
import { resolveSubviewCompositionScaleViewport } from "../subview-composition-layout.js";
import { applySubviewComposition } from "../subview-composition-state.js";
import {
  createSubviewCompositionController,
  projectCurrentSubviewToComposition,
} from "../subview-composition-controller.js";
import {
  restoreSubviewHistoryRollback,
  rollbackSubviewHistory,
} from "../subview-history-state.js";

function member(lengthBp, xBp = 0) {
  return { assemblyCtgId: 1, source: { role: "primary", datasetId: 11 },
    label: "ctg1", lengthBp, xBp, lane: "top" };
}

test("composition scale fits short content just as main tracks do and caps long visible spans", () => {
  for (const [unit, count] of [[1, 5], [1, 10], [2, 10], [10000, 20]]) {
    const trackPrefs = { minTickUnitKb: unit, maxTickCount: count };
    for (const width of [600, 1200]) {
      for (const length of [1200, 60_000_000]) {
        const viewport = resolveSubviewCompositionScaleViewport({ members: [member(length)] }, {
          trackPrefs, viewportWidthPx: width,
        });
        const visibleSpan = Math.min(length, unit * count * 1000);
        assert.ok(Math.abs(viewport.bpPerPx * width - visibleSpan) < 1);
        assert.equal(viewport.leftBp, 0);
      }
    }
  }
});

test("composition zoom preserves a signed center until fitting requires clamping to content bounds", () => {
  const composition = { members: [member(100_000, -50_000)] };
  const before = structuredClone(composition);
  const viewport = resolveSubviewCompositionScaleViewport(composition, {
    trackPrefs: { minTickUnitKb: 1, maxTickCount: 10 }, viewportWidthPx: 1000, centerBp: -30_000,
  });
  assert.equal(viewport.bpPerPx, 10);
  assert.equal(viewport.leftBp, -35_000);
  const fitted = resolveSubviewCompositionScaleViewport(composition, {
    trackPrefs: { minTickUnitKb: 10000, maxTickCount: 10 }, viewportWidthPx: 1000, centerBp: -30_000,
  });
  assert.equal(fitted.bpPerPx, 100);
  assert.equal(fitted.leftBp, -50_000);
  assert.deepEqual(composition, before);
});

test("composition without a saved viewport renders using its actual extent and toolbar scale", () => {
  const state = createState({ assembly: {
    subview: applySubviewComposition({}, { members: [member(1200)] }),
    subviewCompositionViewport: {},
  } });
  const html = renderAssemblyPage(state);
  assert.match(html, /data-subview-rect-width="1200.00"/);
  assert.match(html, /data-subview-domain-span-bp="1200"/);
});

test("adding the first member initializes a fitted viewport and later edits retain its scale", async () => {
  const candidate = { ...member(1200), candidateKey: "assembly:1", entityKey: "assembly:1" };
  const session = {};
  let hasGraph = false;
  const host = { querySelector: () => hasGraph ? {} : null, querySelectorAll: () => [] };
  const store = createStore(createState({ assembly: {
    subview: applySubviewComposition({}, { members: [] }),
    subviewCompositionCandidates: [candidate], subviewCompositionCandidatesLoaded: true,
  } }));
  let persisted = 0;
  const controller = createSubviewCompositionController({
    session, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => { persisted += 1; },
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {},
    anchorController: { resetScope() {} },
  });
  const scopeKey = "fixture";
  controller.resetScope(scopeKey);
  session.subviewCompositionToolsState.checkedKeys = [candidate.candidateKey];
  const context = { host, store, scopeKey, sync() {} };
  controller.onAction({ target: { closest: (selector) =>
    selector === "[data-subview-composition-confirm-add]" ? {} : null } }, context);
  await Promise.resolve();
  assert.equal(store.getState().assembly.subviewCompositionViewport.bpPerPx, 2);
  assert.equal(persisted, 1);
  hasGraph = true;
  controller.onAction({ target: { closest: (selector) =>
    selector === "[data-subview-composition-move]"
      ? { dataset: { subviewCompositionMove: "assembly:1", subviewCompositionTargetLane: "bottom" } }
      : null } }, context);
  await Promise.resolve();
  assert.equal(store.getState().assembly.subviewCompositionViewport.bpPerPx, 2);
  assert.equal(store.getState().assembly.subview.summary.members[0].lane, "bottom");
  assert.equal(persisted, 2);
});

test("projecting a default Subview preserves logical bp positions instead of display rect spacing", () => {
  const state = createState({ assembly: {
    subview: {
      mode: "2-contig",
      summary: {
        mode: "2-contig",
        top: { contigId: 2, role: "primary" },
        bottom: { contigId: 5, role: "primary" },
      },
    },
  } });
  const scroll = { dataset: {
    subviewDomainSpanBp: "10000",
    subviewInnerWidth: "1000",
    subviewWindowStartBp: "2500",
  } };
  const attrsById = {
    2: {
      "data-subview-track-slot": "top",
      "data-subview-contig-id": "2",
      "data-subview-rect-x": "450",
      "data-subview-world-start-bp": "-1250",
    },
    5: {
      "data-subview-track-slot": "bottom",
      "data-subview-contig-id": "5",
      "data-subview-rect-x": "120",
    },
  };
  const host = {
    querySelector: (selector) => selector === ".subview-track-scroll" ? scroll : null,
    querySelectorAll: () => Object.values(attrsById).map((attrs) => ({
      getAttribute: (name) => Object.hasOwn(attrs, name) ? attrs[name] : null,
    })),
  };

  const composition = projectCurrentSubviewToComposition(state, host);
  const top = composition.members.find((entry) => entry.assemblyCtgId === 2);
  const bottom = composition.members.find((entry) => entry.assemblyCtgId === 5);
  assert.equal(top.xBp, -1250);
  assert.equal(bottom.xBp, 3700);
});

test("projecting a track-pair excludes contigs already removed from the current Subview", () => {
  const state = createState({ assembly: {
    supportDatasetId: 22,
    supportChrCtgs: [
      { assemblyCtgId: 30, datasetId: 22, name: "support-30", assignedChrName: "Chr01", totalLength: 700 },
      { assemblyCtgId: 31, datasetId: 22, name: "support-31", assignedChrName: "Chr01", totalLength: 900 },
    ],
    subview: {
      mode: "track-pair",
      summary: {
        mode: "track-pair",
        topTrack: { role: "primary", source: "mother" },
        bottomTrack: { role: "support", source: "mother", datasetId: 22 },
      },
      trackPairHiddenCtgs: [
        { trackRole: "primary", contigId: 8 },
        { trackRole: "support", contigId: 30 },
      ],
    },
  } });
  const composition = projectCurrentSubviewToComposition(state, {
    querySelector: () => null,
    querySelectorAll: () => [],
  });
  const ids = composition.members.map((entry) => entry.assemblyCtgId);
  assert.equal(ids.includes(8), false);
  assert.equal(ids.includes(30), false);
  assert.equal(ids.includes(2), true);
  assert.equal(ids.includes(31), true);
});

test("context-menu lane move projects a 2-contig Subview and commits once", async () => {
  const state = createState({ assembly: {
    subview: {
      mode: "2-contig",
      summary: {
        mode: "2-contig",
        top: { contigId: 2, role: "primary" },
        bottom: { contigId: 5, role: "primary" },
      },
      flippedCtgs: [{ slot: "top", contigId: 2 }],
    },
  } });
  const scroll = { dataset: {
    subviewDomainSpanBp: "10000",
    subviewInnerWidth: "1000",
    subviewWindowStartBp: "2500",
  }, scrollLeft: 0 };
  const attrsById = {
    2: { "data-subview-track-slot": "top", "data-subview-contig-id": "2", "data-subview-world-start-bp": "-1250" },
    5: { "data-subview-track-slot": "bottom", "data-subview-contig-id": "5", "data-subview-world-start-bp": "3700" },
  };
  const host = {
    querySelector: (selector) => selector === ".subview-track-scroll" ? scroll : null,
    querySelectorAll: () => Object.values(attrsById).map((attrs) => ({
      getAttribute: (name) => Object.hasOwn(attrs, name) ? attrs[name] : null,
    })),
  };
  const store = createStore(state);
  let rerendered = 0;
  let refreshed = 0;
  let persisted = 0;
  const controller = createSubviewCompositionController({
    session: {}, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => { persisted += 1; },
    rerenderSubviewPanel() { rerendered += 1; },
    refreshSubviewPairwiseEvidence() { refreshed += 1; },
    anchorController: { resetScope() {} },
  });

  const changed = await controller.moveContextSubviewMemberToOtherLane(
    host,
    store,
    { assemblyCtgId: 2, slot: "top", trackRole: "primary" },
  );

  assert.equal(changed, true);
  const assembly = store.getState().assembly;
  assert.equal(assembly.subview.summary.mode, "composition");
  const moved = assembly.subview.summary.members.find((entry) => entry.assemblyCtgId === 2);
  assert.equal(moved.lane, "bottom");
  assert.equal(moved.xBp, -1250);
  assert.equal(moved.flipped, true);
  const history = assembly.subviewHistoryByKey[assembly.subview.historyKey];
  assert.equal(history.past.length, 1);
  assert.equal(history.past[0].operation.kind, "move-members");
  assert.equal(rerendered, 1);
  assert.equal(refreshed, 1);
  assert.equal(persisted, 1);
});

test("context-menu remove projects a 2-contig Subview and keeps the other member", async () => {
  const store = createStore(createState({ assembly: {
    subview: {
      mode: "2-contig",
      summary: {
        mode: "2-contig",
        top: { contigId: 2, role: "primary" },
        bottom: { contigId: 5, role: "primary" },
      },
    },
  } }));
  const host = { querySelector: () => null, querySelectorAll: () => [] };
  let persisted = 0;
  const controller = createSubviewCompositionController({
    session: {}, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => { persisted += 1; },
    rerenderSubviewPanel() {}, refreshSubviewPairwiseEvidence() {},
    anchorController: { resetScope() {} },
  });

  const changed = await controller.removeContextSubviewMember(
    host,
    store,
    { assemblyCtgId: 2, slot: "top", trackRole: "primary" },
  );

  assert.equal(changed, true);
  const assembly = store.getState().assembly;
  assert.equal(assembly.subview.summary.mode, "composition");
  assert.deepEqual(assembly.subview.summary.members.map((entry) => entry.assemblyCtgId), [5]);
  const history = assembly.subviewHistoryByKey[assembly.subview.historyKey];
  assert.equal(history.past.length, 1);
  assert.equal(history.past[0].operation.kind, "remove-members");
  assert.equal(history.past[0].operation.count, 1);
  assert.equal(persisted, 1);
});

test("context-menu lane move preserves xBp and records one composition history step", async () => {
  const original = {
    ...member(1200, -3456),
    entityKey: "assembly:1",
    baseOrientation: "-",
    flipped: true,
    source: { role: "primary", datasetId: 11, sourceType: "mother" },
  };
  const store = createStore(createState({ assembly: {
    subview: applySubviewComposition({}, { members: [original] }),
    subviewCompositionViewport: { bpPerPx: 4, leftBp: -5000, topPx: 0 },
  } }));
  const before = structuredClone(store.getState().assembly.subview.summary.members[0]);
  let rerendered = 0;
  let refreshed = 0;
  let persisted = 0;
  const controller = createSubviewCompositionController({
    session: {}, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => { persisted += 1; },
    rerenderSubviewPanel() { rerendered += 1; },
    refreshSubviewPairwiseEvidence() { refreshed += 1; },
    anchorController: { resetScope() {} },
  });

  const changed = await controller.moveContextSubviewMemberToOtherLane(
    { querySelector: () => null },
    store,
    { entityKey: "assembly:1" },
  );

  assert.equal(changed, true);
  const assembly = store.getState().assembly;
  const moved = assembly.subview.summary.members[0];
  assert.equal(moved.lane, "bottom");
  assert.equal(moved.xBp, before.xBp);
  assert.equal(moved.baseOrientation, before.baseOrientation);
  assert.equal(moved.flipped, before.flipped);
  assert.deepEqual(moved.source, before.source);
  const history = assembly.subviewHistoryByKey[assembly.subview.historyKey];
  assert.equal(history.past.length, 1);
  assert.equal(history.past[0].operation.kind, "move-members");
  assert.equal(history.past[0].operation.count, 1);
  const rolledBack = rollbackSubviewHistory(assembly);
  assert.equal(rolledBack.changed, true);
  assert.equal(rolledBack.assembly.subview.summary.members[0].lane, "top");
  assert.equal(rolledBack.assembly.subview.summary.members[0].xBp, before.xBp);
  const restored = restoreSubviewHistoryRollback(rolledBack.assembly);
  assert.equal(restored.changed, true);
  assert.equal(restored.assembly.subview.summary.members[0].lane, "bottom");
  assert.equal(restored.assembly.subview.summary.members[0].xBp, before.xBp);
  assert.equal(rerendered, 1);
  assert.equal(refreshed, 1);
  assert.equal(persisted, 1);
});

test("context-menu remove deletes one composition member and records one history step", async () => {
  const keep = { ...member(900, 2200), entityKey: "assembly:2", assemblyCtgId: 2, lane: "bottom" };
  const remove = { ...member(1200, -3456), entityKey: "assembly:1", assemblyCtgId: 1 };
  const store = createStore(createState({ assembly: {
    subview: applySubviewComposition({}, { members: [remove, keep] }),
    subviewCompositionViewport: { bpPerPx: 4, leftBp: -5000, topPx: 0 },
  } }));
  let rerendered = 0;
  let refreshed = 0;
  let persisted = 0;
  const controller = createSubviewCompositionController({
    session: {}, getMeasuredTrackViewportPx: () => 600,
    listChrViewCtgs: async () => ({ items: [] }),
    persistProjectAssemblyViewStateFromStore: async () => { persisted += 1; },
    rerenderSubviewPanel() { rerendered += 1; },
    refreshSubviewPairwiseEvidence() { refreshed += 1; },
    anchorController: { resetScope() {} },
  });

  const changed = await controller.removeContextSubviewMember(
    { querySelector: () => null },
    store,
    { entityKey: "assembly:1" },
  );

  assert.equal(changed, true);
  const assembly = store.getState().assembly;
  assert.deepEqual(assembly.subview.summary.members.map((entry) => entry.entityKey), ["assembly:2"]);
  assert.equal(assembly.subview.summary.members[0].xBp, keep.xBp);
  assert.equal(assembly.subview.summary.members[0].lane, keep.lane);
  const history = assembly.subviewHistoryByKey[assembly.subview.historyKey];
  assert.equal(history.past.length, 1);
  assert.equal(history.past[0].operation.kind, "remove-members");
  assert.equal(history.past[0].operation.count, 1);
  assert.equal(rerendered, 1);
  assert.equal(refreshed, 1);
  assert.equal(persisted, 1);
});
