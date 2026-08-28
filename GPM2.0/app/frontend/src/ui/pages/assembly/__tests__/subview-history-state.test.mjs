import test from "node:test";
import assert from "node:assert/strict";

import {
  SUBVIEW_HISTORY_LIMIT,
  activateSubviewHistory,
  commitSubviewHistoryOperation,
  isSubviewHistoryRecordCompatible,
  resetSubviewHistory,
  resolveCurrentSubviewHistory,
  restoreSubviewHistoryRollback,
  rollbackSubviewHistory,
} from "../subview-history-state.js";
import { swapSubviewSummaryOrder } from "../subview-state.js";

function buildAssembly() {
  return {
    selectedChrName: "Chr01",
    subviewAnchorStateByKey: {},
    subviewHistoryByKey: {},
    subviewTrackDragOffsets: [],
    subview: {
      mode: "2-contig",
      selectedAContigId: 1,
      selectedARole: "primary",
      selectedBContigId: 2,
      selectedBRole: "support",
      activeAnchors: [],
      manualAnchors: [],
      flippedCtgs: [],
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
      summary: {
        mode: "2-contig",
        top: { role: "primary", contigId: 1, datasetId: 11 },
        bottom: { role: "support", contigId: 2, datasetId: 22 },
      },
    },
  };
}

function buildTrackPairAssembly() {
  return {
    selectedChrName: "Chr01",
    subviewAnchorStateByKey: {},
    subviewHistoryByKey: {},
    subviewTrackDragOffsets: [],
    subview: {
      mode: "subview-track",
      activeAnchors: [],
      manualAnchors: [],
      flippedCtgs: [],
      trackPairHiddenCtgs: [],
      trackPairSelectedCtgs: [],
      summary: {
        mode: "track-pair",
        topTrack: { role: "primary", source: "mother" },
        bottomTrack: { role: "support", source: "mother", datasetId: 22 },
      },
    },
  };
}

function commitTrackPairEdits(assembly, now = 1) {
  return commitSubviewHistoryOperation(assembly, {
    nextSubview: {
      ...assembly.subview,
      trackPairHiddenCtgs: [{ trackRole: "support", contigId: 2 }],
      flippedCtgs: [{ slot: "top", contigId: 1 }],
      activeAnchors: [{ hitKey: "pair:1:hit-a:2:hit-b", edge: "left" }],
      manualAnchors: [{
        manualAnchorId: "manual-1-2",
        endpointA: { endpointKey: "role:primary:ctg:1", contigId: 1, cutBp: 20 },
        endpointB: { endpointKey: "role:support:ctg:2", contigId: 2, cutBp: 30 },
      }],
    },
    nextSubviewTrackDragOffsets: [{ slot: "bottom", contigId: 2, offsetBp: 40 }],
    operation: { kind: "hide-contig" },
    now,
  }).assembly;
}

test("Subview history activation creates one order-insensitive pair record", () => {
  const first = activateSubviewHistory(buildAssembly(), { now: 0 });
  assert.equal(first.created, true);
  assert.match(first.pairKey, /^2-contig\|chr:Chr01\|/);
  assert.equal(Object.keys(first.assembly.subviewHistoryByKey).length, 1);

  const reversedSubview = swapSubviewSummaryOrder({ subview: first.assembly.subview });
  const second = activateSubviewHistory({
    ...first.assembly,
    subview: reversedSubview,
  }, { now: 1 });
  assert.equal(second.pairKey, first.pairKey);
  assert.equal(second.created, false);
  assert.equal(second.assembly.subview.summary.top.contigId, 1);
});

test("Subview history rolls back and restores one operation at a time", () => {
  let assembly = activateSubviewHistory(buildAssembly(), { now: 0 }).assembly;
  let committed = commitSubviewHistoryOperation(assembly, {
    nextSubviewTrackDragOffsets: [{ slot: "top", contigId: 1, offsetBp: 10 }],
    nextSubview: assembly.subview,
    operation: { kind: "drag-contig" },
    now: 1,
  });
  assembly = committed.assembly;
  committed = commitSubviewHistoryOperation(assembly, {
    nextSubviewTrackDragOffsets: [{ slot: "top", contigId: 1, offsetBp: 20 }],
    nextSubview: assembly.subview,
    operation: { kind: "drag-contig" },
    now: 2,
  });
  assembly = committed.assembly;

  const rolledBack = rollbackSubviewHistory(assembly, { now: 3 });
  assert.equal(rolledBack.changed, true);
  assert.equal(rolledBack.assembly.subviewTrackDragOffsets[0].offsetBp, 10);
  assert.equal(resolveCurrentSubviewHistory(rolledBack.assembly).canRestoreRollback, true);

  const rolledBackAgain = rollbackSubviewHistory(rolledBack.assembly, { now: 4 });
  assert.deepEqual(rolledBackAgain.assembly.subviewTrackDragOffsets, []);

  const restoredOnce = restoreSubviewHistoryRollback(rolledBackAgain.assembly, { now: 5 });
  assert.equal(restoredOnce.assembly.subviewTrackDragOffsets[0].offsetBp, 10);
  assert.equal(restoredOnce.assembly.subviewHistoryByKey[restoredOnce.pairKey].forward.length, 1);
});

test("A new Subview edit after rollback clears forward history", () => {
  let assembly = activateSubviewHistory(buildAssembly(), { now: 0 }).assembly;
  assembly = commitSubviewHistoryOperation(assembly, {
    nextSubview: { ...assembly.subview, flippedCtgs: [{ slot: "top", contigId: 1 }] },
    operation: { kind: "flip-contig" },
    now: 1,
  }).assembly;
  assembly = rollbackSubviewHistory(assembly, { now: 2 }).assembly;
  assert.equal(resolveCurrentSubviewHistory(assembly).canRestoreRollback, true);

  assembly = commitSubviewHistoryOperation(assembly, {
    nextSubview: {
      ...assembly.subview,
      activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
    },
    operation: { kind: "toggle-anchor" },
    now: 3,
  }).assembly;
  assert.equal(resolveCurrentSubviewHistory(assembly).canRestoreRollback, false);
});

test("Subview reset restores the first-entered default and is itself rollback-able", () => {
  let assembly = activateSubviewHistory(buildAssembly(), { now: 0 }).assembly;
  const swapped = swapSubviewSummaryOrder({ subview: assembly.subview });
  assembly = commitSubviewHistoryOperation(assembly, {
    nextSubview: {
      ...swapped,
      activeAnchors: [{ hitKey: "hit-1", edge: "right" }],
      flippedCtgs: [{ slot: "bottom", contigId: 1 }],
      trackPairHiddenCtgs: [{ trackRole: "primary", contigId: 1 }],
    },
    nextSubviewTrackDragOffsets: [{ slot: "bottom", contigId: 1, offsetBp: 50 }],
    operation: { kind: "swap-track-order" },
    now: 1,
  }).assembly;

  const reset = resetSubviewHistory(assembly, { now: 2 });
  assert.equal(reset.changed, true);
  assert.equal(reset.assembly.subview.summary.top.contigId, 1);
  assert.deepEqual(reset.assembly.subview.activeAnchors, []);
  assert.deepEqual(reset.assembly.subview.flippedCtgs, []);
  assert.deepEqual(reset.assembly.subview.trackPairHiddenCtgs, []);
  assert.deepEqual(reset.assembly.subviewTrackDragOffsets, []);
  assert.equal(resolveCurrentSubviewHistory(reset.assembly).canReset, false);

  const undoReset = rollbackSubviewHistory(reset.assembly, { now: 3 });
  assert.equal(undoReset.assembly.subview.summary.top.contigId, 2);
  assert.equal(undoReset.assembly.subviewTrackDragOffsets[0].offsetBp, 50);
});

test("Subview history keeps only the latest 50 logical operations per pair", () => {
  let assembly = activateSubviewHistory(buildAssembly(), { now: 0 }).assembly;
  for (let index = 1; index <= SUBVIEW_HISTORY_LIMIT + 1; index += 1) {
    assembly = commitSubviewHistoryOperation(assembly, {
      nextSubview: assembly.subview,
      nextSubviewTrackDragOffsets: [{ slot: "top", contigId: 1, offsetBp: index }],
      operation: { kind: "drag-contig" },
      now: index,
    }).assembly;
  }
  const status = resolveCurrentSubviewHistory(assembly);
  assert.equal(status.record.past.length, SUBVIEW_HISTORY_LIMIT);
  assert.equal(status.record.forward.length, 0);
  assert.equal(status.record.current.dragOffsets[0].offsetBp, SUBVIEW_HISTORY_LIMIT + 1);
});

test("Subview track-pair history keeps saved edits when new ctgs join the same tracks", () => {
  let assembly = activateSubviewHistory(buildTrackPairAssembly(), { now: 0 }).assembly;
  assembly = commitTrackPairEdits(assembly);
  const enteredSubview = {
    ...assembly.subview,
    trackPairHiddenCtgs: [],
    flippedCtgs: [],
    activeAnchors: [],
    manualAnchors: [],
  };

  const activation = activateSubviewHistory({
    ...assembly,
    chrCtgs: [{ assemblyCtgId: 1 }, { assemblyCtgId: 3 }],
    supportChrCtgs: [
      { assemblyCtgId: 2, datasetId: 22 },
      { assemblyCtgId: 4, datasetId: 22 },
    ],
    subview: enteredSubview,
    subviewTrackDragOffsets: [],
  }, {
    now: 2,
    validateRecord: (record) => isSubviewHistoryRecordCompatible(record, {
      summary: enteredSubview.summary,
    }),
  });

  assert.equal(activation.created, false);
  assert.equal(activation.invalidated, false);
  assert.deepEqual(activation.assembly.subview.trackPairHiddenCtgs, [
    { trackRole: "support", contigId: 2 },
  ]);
  assert.deepEqual(activation.assembly.subview.flippedCtgs, [
    { slot: "top", contigId: 1 },
  ]);
  assert.deepEqual(activation.assembly.subviewTrackDragOffsets, [
    { slot: "bottom", contigId: 2, offsetBp: 40 },
  ]);
  assert.equal(
    JSON.stringify(activation.assembly.subviewHistoryByKey).includes('"contigId":3'),
    false,
  );
  assert.equal(
    JSON.stringify(activation.assembly.subviewHistoryByKey).includes('"contigId":4'),
    false,
  );
});

test("Subview track-pair history keeps temporarily absent ctg edits dormant and restores them", () => {
  let assembly = activateSubviewHistory(buildTrackPairAssembly(), { now: 0 }).assembly;
  assembly = commitTrackPairEdits(assembly);
  const record = resolveCurrentSubviewHistory(assembly).record;

  assert.equal(isSubviewHistoryRecordCompatible(record, {
    summary: assembly.subview.summary,
  }), true);

  const dormant = activateSubviewHistory({
    ...assembly,
    chrCtgs: [{ assemblyCtgId: 1 }],
    supportChrCtgs: [{ assemblyCtgId: 4, datasetId: 22 }],
    subview: {
      ...assembly.subview,
      trackPairHiddenCtgs: [],
      flippedCtgs: [],
      activeAnchors: [],
      manualAnchors: [],
    },
    subviewTrackDragOffsets: [],
  }, {
    now: 2,
    validateRecord: (candidate) => isSubviewHistoryRecordCompatible(candidate, {
      summary: assembly.subview.summary,
    }),
  });

  assert.equal(dormant.invalidated, false);
  assert.equal(dormant.assembly.subview.trackPairHiddenCtgs[0].contigId, 2);
  assert.equal(dormant.assembly.subview.manualAnchors[0].endpointB.contigId, 2);
  assert.equal(dormant.assembly.subviewTrackDragOffsets[0].contigId, 2);

  const restored = activateSubviewHistory({
    ...dormant.assembly,
    supportChrCtgs: [
      { assemblyCtgId: 2, datasetId: 22 },
      { assemblyCtgId: 4, datasetId: 22 },
    ],
  }, {
    now: 3,
    validateRecord: (candidate) => isSubviewHistoryRecordCompatible(candidate, {
      summary: dormant.assembly.subview.summary,
    }),
  });
  assert.equal(restored.invalidated, false);
  assert.equal(restored.assembly.subview.trackPairHiddenCtgs[0].contigId, 2);
  assert.equal(restored.assembly.subview.manualAnchors[0].endpointB.contigId, 2);
});

test("Subview track-pair back forward and reset preserve dormant member history", () => {
  let assembly = activateSubviewHistory(buildTrackPairAssembly(), { now: 0 }).assembly;
  assembly = commitTrackPairEdits(assembly, 1);
  assembly = commitSubviewHistoryOperation(assembly, {
    nextSubview: {
      ...assembly.subview,
      flippedCtgs: [],
    },
    operation: { kind: "flip-contig" },
    now: 2,
  }).assembly;

  const rolledBack = rollbackSubviewHistory(assembly, { now: 3 });
  assert.deepEqual(rolledBack.assembly.subview.flippedCtgs, [
    { slot: "top", contigId: 1 },
  ]);
  assert.equal(rolledBack.assembly.subview.trackPairHiddenCtgs[0].contigId, 2);

  const restored = restoreSubviewHistoryRollback(rolledBack.assembly, { now: 4 });
  assert.deepEqual(restored.assembly.subview.flippedCtgs, []);
  assert.equal(restored.assembly.subviewTrackDragOffsets[0].contigId, 2);

  const reset = resetSubviewHistory(restored.assembly, { now: 5 });
  assert.deepEqual(reset.assembly.subview.trackPairHiddenCtgs, []);
  assert.deepEqual(reset.assembly.subview.manualAnchors, []);
  assert.deepEqual(reset.assembly.subviewTrackDragOffsets, []);

  const undoReset = rollbackSubviewHistory(reset.assembly, { now: 6 });
  assert.equal(undoReset.assembly.subview.trackPairHiddenCtgs[0].contigId, 2);
  assert.equal(undoReset.assembly.subview.manualAnchors[0].endpointB.contigId, 2);
  assert.equal(undoReset.assembly.subviewTrackDragOffsets[0].contigId, 2);
});

test("Subview track-pair history still rejects state owned by a track outside the pair", () => {
  const activation = activateSubviewHistory(buildTrackPairAssembly(), { now: 0 });
  const record = {
    ...activation.assembly.subviewHistoryByKey[activation.pairKey],
    current: {
      ...activation.assembly.subviewHistoryByKey[activation.pairKey].current,
      trackPairHiddenCtgs: [{ trackRole: "ref", contigId: 99 }],
    },
  };

  assert.equal(isSubviewHistoryRecordCompatible(record, {
    summary: activation.assembly.subview.summary,
  }), false);
});

test("Subview history invalidates only the current pair when a persisted contig reference is stale", () => {
  const current = activateSubviewHistory(buildAssembly(), { now: 0 });
  const other = activateSubviewHistory({
    ...buildAssembly(),
    selectedChrName: "Chr02",
  }, { now: 0 });
  const staleCurrentRecord = {
    ...current.assembly.subviewHistoryByKey[current.pairKey],
    current: {
      ...current.assembly.subviewHistoryByKey[current.pairKey].current,
      flippedCtgs: [{ slot: "top", contigId: 999 }],
    },
  };
  const assembly = {
    ...current.assembly,
    subviewHistoryByKey: {
      [current.pairKey]: staleCurrentRecord,
      [other.pairKey]: other.assembly.subviewHistoryByKey[other.pairKey],
    },
  };
  const activation = activateSubviewHistory(assembly, {
    now: 1,
    validateRecord: (record) => isSubviewHistoryRecordCompatible(record, {
      summary: assembly.subview.summary,
    }),
  });

  assert.equal(activation.invalidated, true);
  assert.deepEqual(activation.assembly.subview.flippedCtgs, []);
  assert.deepEqual(activation.assembly.subviewHistoryByKey[current.pairKey].past, []);
  assert.ok(activation.assembly.subviewHistoryByKey[other.pairKey]);
});

test("Subview rollback resets the current pair when its next history snapshot is invalid", () => {
  let assembly = activateSubviewHistory(buildAssembly(), { now: 0 }).assembly;
  assembly = commitSubviewHistoryOperation(assembly, {
    nextSubview: {
      ...assembly.subview,
      activeAnchors: [{ hitKey: "hit-1", edge: "left" }],
    },
    operation: { kind: "toggle-anchor" },
    now: 1,
  }).assembly;
  const status = resolveCurrentSubviewHistory(assembly);
  assembly = {
    ...assembly,
    subviewHistoryByKey: {
      ...assembly.subviewHistoryByKey,
      [status.pairKey]: {
        ...status.record,
        past: [{
          ...status.record.past[0],
          snapshot: { ...status.record.past[0].snapshot, topKey: "stale-endpoint" },
        }],
      },
    },
  };

  const rollback = rollbackSubviewHistory(assembly, { now: 2 });

  assert.equal(rollback.invalidated, true);
  assert.deepEqual(rollback.assembly.subview.activeAnchors, []);
  assert.deepEqual(rollback.assembly.subviewHistoryByKey[status.pairKey].past, []);
});
