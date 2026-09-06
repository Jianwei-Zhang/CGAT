import {
  buildSubviewAnchorStateKey,
  buildSubviewSummaryOrderKeys,
  normalizeSubviewActiveAnchors,
  normalizeSubviewManualAnchors,
  setSubviewAnchorStateForSummary,
} from "./subview-anchor-state.js";
import {
  normalizeSupportDatasetId,
  normalizeSubviewTrackDragOffsets,
} from "./selection-state.js";
import {
  buildSubviewTrackPairHiddenCtgKey,
  getSubviewState,
  normalizeSubviewFlippedCtgs,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewTrackPairSelectionCtgs,
  normalizeSubviewTrackSummary,
  swapSubviewSummaryOrder,
} from "./subview-state.js";
import {
  SUBVIEW_COMPOSITION_MODE,
  applySubviewComposition,
  getSubviewComposition,
  normalizeSubviewComposition,
} from "./subview-composition-state.js";

export const SUBVIEW_HISTORY_SCHEMA_VERSION = 1;
export const SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION = 2;
export const SUBVIEW_HISTORY_LIMIT = 50;

const SUBVIEW_HISTORY_OPERATION_KINDS = new Set([
  "hide-contig",
  "hide-contigs",
  "restore-hidden-contigs",
  "toggle-anchor",
  "create-offset-anchor",
  "create-grt-anchor",
  "delete-offset-anchor",
  "delete-anchors",
  "flip-contig",
  "drag-contig",
  "swap-track-order",
  "reset",
  "add-members",
  "remove-members",
  "move-members",
  "replace-composition",
  "compact-layout",
]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizePositiveInt(value) {
  const numeric = Number(value);
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null;
}

function normalizeTimestamp(value, fallback = "") {
  const normalized = String(value || "").trim();
  return normalized || fallback;
}

function nowTimestamp(now = Date.now()) {
  const numeric = Number(now);
  return Number.isFinite(numeric) ? new Date(numeric).toISOString() : new Date().toISOString();
}

export function normalizeSubviewHistoryOperation(value) {
  const kind = String(value?.kind || "").trim();
  if (!SUBVIEW_HISTORY_OPERATION_KINDS.has(kind)) {
    return null;
  }
  const count = normalizePositiveInt(value?.count);
  return {
    kind,
    ...(count ? { count } : {}),
  };
}

export function normalizeSubviewEditableSnapshot(value) {
  const source = isPlainObject(value) ? value : {};
  return {
    topKey: String(source.topKey || "").trim(),
    trackPairHiddenCtgs: normalizeSubviewTrackPairHiddenCtgs(source.trackPairHiddenCtgs),
    flippedCtgs: normalizeSubviewFlippedCtgs(source.flippedCtgs),
    activeAnchors: normalizeSubviewActiveAnchors(source.activeAnchors),
    manualAnchors: normalizeSubviewManualAnchors(source.manualAnchors),
    dragOffsets: normalizeSubviewTrackDragOffsets(source.dragOffsets),
  };
}

function normalizeSubviewHistoryEntry(value) {
  if (!isPlainObject(value)) {
    return null;
  }
  const operation = normalizeSubviewHistoryOperation(value.operation);
  const snapshot = normalizeSubviewEditableSnapshot(value.snapshot);
  if (!operation || !snapshot.topKey) {
    return null;
  }
  return { operation, snapshot };
}

function normalizeSubviewHistoryEntries(values) {
  return (Array.isArray(values) ? values : [])
    .map(normalizeSubviewHistoryEntry)
    .filter(Boolean);
}

export function normalizeSubviewHistoryRecord(value, pairKey = "") {
  if (!isPlainObject(value) || Number(value.version) !== SUBVIEW_HISTORY_SCHEMA_VERSION) {
    return null;
  }
  const normalizedPairKey = String(pairKey || value.pairKey || "").trim();
  if (!normalizedPairKey || String(value.pairKey || normalizedPairKey).trim() !== normalizedPairKey) {
    return null;
  }
  const current = normalizeSubviewEditableSnapshot(value.current);
  const defaultSnapshot = normalizeSubviewEditableSnapshot(value.default);
  if (!current.topKey || !defaultSnapshot.topKey) {
    return null;
  }
  const past = normalizeSubviewHistoryEntries(value.past);
  const forward = normalizeSubviewHistoryEntries(value.forward);
  if (past.length + forward.length > SUBVIEW_HISTORY_LIMIT) {
    return null;
  }
  return {
    version: SUBVIEW_HISTORY_SCHEMA_VERSION,
    pairKey: normalizedPairKey,
    current,
    default: defaultSnapshot,
    past,
    forward,
    updatedAt: normalizeTimestamp(value.updatedAt),
  };
}

export function normalizeSubviewHistoryByKey(value) {
  const source = isPlainObject(value) ? value : {};
  return Object.fromEntries(
    Object.entries(source)
      .map(([pairKey, record]) => {
        const normalizedPairKey = String(pairKey || "").trim();
        return [normalizedPairKey, Number(record?.version) === SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION
          ? normalizeSubviewCompositionHistoryRecord(record, normalizedPairKey)
          : normalizeSubviewHistoryRecord(record, normalizedPairKey)];
      })
      .filter(([pairKey, record]) => pairKey && record),
  );
}

export function buildSubviewCompositionHistoryKey(chrName) {
  const normalizedChrName = String(chrName || "").trim();
  return normalizedChrName ? `composition:${encodeURIComponent(normalizedChrName)}` : "";
}

export function normalizeSubviewCompositionHistorySnapshot(value) {
  if (!isPlainObject(value)) return null;
  const kind = String(value.kind || "").trim();
  if (kind === "composition") {
    return { kind, composition: normalizeSubviewComposition(value.composition || value) };
  }
  if (kind === "legacy" && isPlainObject(value.summary)) {
    const editableSnapshot = normalizeSubviewEditableSnapshot(value.editableSnapshot);
    if (!editableSnapshot.topKey) return null;
    return { kind, summary: value.summary, editableSnapshot };
  }
  return null;
}

function normalizeSubviewCompositionHistoryEntry(value) {
  if (!isPlainObject(value)) return null;
  const operation = normalizeSubviewHistoryOperation(value.operation);
  const snapshot = normalizeSubviewCompositionHistorySnapshot(value.snapshot);
  return operation && snapshot ? { operation, snapshot } : null;
}

export function normalizeSubviewCompositionViewport(value) {
  const source = isPlainObject(value) ? value : {};
  const bpPerPx = Number(source.bpPerPx);
  const leftBp = Number(source.leftBp);
  const topPx = Number(source.topPx);
  return {
    bpPerPx: Number.isFinite(bpPerPx) && bpPerPx > 0 ? bpPerPx : 1_000,
    leftBp: Number.isFinite(leftBp) ? leftBp : 0,
    topPx: Number.isFinite(topPx) ? topPx : 0,
  };
}

export function updateSubviewCompositionViewport(assembly, viewport, now = Date.now()) {
  const normalizedViewport = normalizeSubviewCompositionViewport(viewport);
  const historyKey = String(assembly?.subview?.historyKey || "").trim();
  const pairKey = historyKey.startsWith("composition:")
    ? historyKey
    : buildSubviewCompositionHistoryKey(assembly?.selectedChrName);
  const records = normalizeSubviewHistoryByKey(assembly?.subviewHistoryByKey);
  const record = records[pairKey];
  const nextRecords = record?.version === SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION
    ? {
      ...records,
      [pairKey]: {
        ...record,
        viewport: normalizedViewport,
        updatedAt: nowTimestamp(now),
      },
    }
    : records;
  return {
    ...assembly,
    subviewCompositionViewport: normalizedViewport,
    subviewHistoryByKey: nextRecords,
  };
}

export function normalizeSubviewCompositionHistoryRecord(value, pairKey = "") {
  if (!isPlainObject(value) || Number(value.version) !== SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION) {
    return null;
  }
  const normalizedPairKey = String(pairKey || value.pairKey || "").trim();
  if (!normalizedPairKey.startsWith("composition:")
    || String(value.pairKey || normalizedPairKey).trim() !== normalizedPairKey) {
    return null;
  }
  const current = normalizeSubviewCompositionHistorySnapshot(value.current);
  const defaultSnapshot = normalizeSubviewCompositionHistorySnapshot(value.default);
  if (!current || !defaultSnapshot) return null;
  const past = (Array.isArray(value.past) ? value.past : [])
    .map(normalizeSubviewCompositionHistoryEntry).filter(Boolean);
  const forward = (Array.isArray(value.forward) ? value.forward : [])
    .map(normalizeSubviewCompositionHistoryEntry).filter(Boolean);
  if (past.length + forward.length > SUBVIEW_HISTORY_LIMIT) return null;
  return {
    version: SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION,
    pairKey: normalizedPairKey,
    current,
    default: defaultSnapshot,
    past,
    forward,
    viewport: normalizeSubviewCompositionViewport(value.viewport),
    updatedAt: normalizeTimestamp(value.updatedAt),
  };
}

function resolveSnapshotPairContext(summary, topKey) {
  const orderKeys = buildSubviewSummaryOrderKeys(summary);
  if (!topKey || (topKey !== orderKeys.topKey && topKey !== orderKeys.bottomKey)) {
    return null;
  }
  if (String(summary?.mode || "") === "2-contig") {
    const topId = normalizeSupportDatasetId(summary?.top?.contigId);
    const bottomId = normalizeSupportDatasetId(summary?.bottom?.contigId);
    if (!topId || !bottomId) {
      return null;
    }
    const currentTopIds = new Set([topId]);
    const currentBottomIds = new Set([bottomId]);
    return topKey === orderKeys.topKey
      ? { topIds: currentTopIds, bottomIds: currentBottomIds }
      : { topIds: currentBottomIds, bottomIds: currentTopIds };
  }
  if (String(summary?.mode || "") !== "track-pair") {
    return null;
  }
  const currentTopTrack = normalizeSubviewTrackSummary(summary?.topTrack);
  const currentBottomTrack = normalizeSubviewTrackSummary(summary?.bottomTrack);
  if (!currentTopTrack || !currentBottomTrack) {
    return null;
  }
  // Resolved members are applicability state, not pair identity. A member can
  // disappear under current filters and later return with the same stable ID.
  return {
    trackRoles: new Set([currentTopTrack.role, currentBottomTrack.role]),
  };
}

function isSubviewEditableSnapshotCompatible(snapshot, summary) {
  const normalized = normalizeSubviewEditableSnapshot(snapshot);
  const context = resolveSnapshotPairContext(summary, normalized.topKey);
  if (!context) {
    return false;
  }
  const isTrackPair = String(summary?.mode || "") === "track-pair";
  if (!isTrackPair && normalized.trackPairHiddenCtgs.length) {
    return false;
  }
  if (isTrackPair) {
    return normalized.trackPairHiddenCtgs.every((entry) =>
      context.trackRoles.has(entry.trackRole)
    );
  }
  const allowedBySlot = {
    top: context.topIds,
    bottom: context.bottomIds,
  };
  if (normalized.flippedCtgs.some((entry) =>
    !allowedBySlot[entry.slot]?.has(entry.contigId)
  )) {
    return false;
  }
  if (normalized.dragOffsets.some((entry) =>
    !allowedBySlot[entry.slot]?.has(entry.contigId)
  )) {
    return false;
  }
  const allIds = new Set([...context.topIds, ...context.bottomIds]);
  return normalized.manualAnchors.every((anchor) =>
    allIds.has(anchor.endpointA?.contigId) && allIds.has(anchor.endpointB?.contigId)
  );
}

export function isSubviewHistoryRecordCompatible(record, { summary } = {}) {
  const normalized = normalizeSubviewHistoryRecord(record, record?.pairKey);
  if (!normalized || !summary) {
    return false;
  }
  const snapshots = [
    normalized.current,
    normalized.default,
    ...normalized.past.map((entry) => entry.snapshot),
    ...normalized.forward.map((entry) => entry.snapshot),
  ];
  return snapshots.every((snapshot) =>
    isSubviewEditableSnapshotCompatible(snapshot, summary)
  );
}

export function buildSubviewEditableSnapshot(subview, subviewTrackDragOffsets = []) {
  const normalizedSubview = getSubviewState({ subview });
  const { topKey } = buildSubviewSummaryOrderKeys(normalizedSubview.summary);
  return normalizeSubviewEditableSnapshot({
    topKey,
    trackPairHiddenCtgs: normalizedSubview.trackPairHiddenCtgs,
    flippedCtgs: normalizedSubview.flippedCtgs,
    activeAnchors: normalizedSubview.activeAnchors,
    manualAnchors: normalizedSubview.manualAnchors,
    dragOffsets: subviewTrackDragOffsets,
  });
}

export function buildDefaultSubviewEditableSnapshot(subview) {
  const { topKey } = buildSubviewSummaryOrderKeys(subview?.summary);
  return normalizeSubviewEditableSnapshot({ topKey });
}

export function areSubviewEditableSnapshotsEqual(left, right) {
  return JSON.stringify(normalizeSubviewEditableSnapshot(left))
    === JSON.stringify(normalizeSubviewEditableSnapshot(right));
}

function applySubviewEditableSnapshot(subview, snapshot, stateOrLocale = "zh") {
  const normalizedSnapshot = normalizeSubviewEditableSnapshot(snapshot);
  let nextSubview = getSubviewState({ subview });
  const orderKeys = buildSubviewSummaryOrderKeys(nextSubview.summary);
  if (!normalizedSnapshot.topKey || !orderKeys.topKey || !orderKeys.bottomKey) {
    return null;
  }
  if (normalizedSnapshot.topKey === orderKeys.bottomKey) {
    nextSubview = swapSubviewSummaryOrder({ subview: nextSubview, stateOrLocale });
  } else if (normalizedSnapshot.topKey !== orderKeys.topKey) {
    return null;
  }
  const hiddenKeys = new Set(
    normalizedSnapshot.trackPairHiddenCtgs.map((entry) =>
      buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
    ),
  );
  return {
    subview: {
      ...nextSubview,
      trackPairHiddenCtgs: normalizedSnapshot.trackPairHiddenCtgs,
      trackPairSelectedCtgs: normalizeSubviewTrackPairSelectionCtgs(
        nextSubview.trackPairSelectedCtgs,
      ).filter((entry) => !hiddenKeys.has(
        buildSubviewTrackPairHiddenCtgKey(entry.trackRole, entry.contigId),
      )),
      flippedCtgs: normalizedSnapshot.flippedCtgs,
      activeAnchors: normalizedSnapshot.activeAnchors,
      manualAnchors: normalizedSnapshot.manualAnchors,
    },
    subviewTrackDragOffsets: normalizedSnapshot.dragOffsets,
  };
}

function buildSubviewCompositionHistorySnapshot(subview) {
  const composition = getSubviewComposition(subview);
  if (composition) {
    return { kind: "composition", composition };
  }
  const summary = subview?.summary;
  const editableSnapshot = buildSubviewEditableSnapshot(subview, []);
  return summary && editableSnapshot.topKey
    ? { kind: "legacy", summary, editableSnapshot }
    : { kind: "composition", composition: normalizeSubviewComposition({}) };
}

function applySubviewCompositionHistorySnapshot(subview, snapshot, pairKey, stateOrLocale = "zh") {
  const normalized = normalizeSubviewCompositionHistorySnapshot(snapshot);
  if (!normalized) return null;
  if (normalized.kind === "composition") {
    return applySubviewComposition(subview, normalized.composition, {
      historyKey: pairKey,
      message: "",
    });
  }
  const legacySubview = {
    ...getSubviewState({ subview }),
    mode: String(normalized.summary?.mode || "2-contig"),
    summary: normalized.summary,
  };
  const applied = applySubviewEditableSnapshot(legacySubview, normalized.editableSnapshot, stateOrLocale);
  return applied ? { ...applied.subview, historyKey: pairKey } : null;
}

function areSubviewCompositionHistorySnapshotsEqual(left, right) {
  return JSON.stringify(normalizeSubviewCompositionHistorySnapshot(left))
    === JSON.stringify(normalizeSubviewCompositionHistorySnapshot(right));
}

function createSubviewCompositionHistoryRecord({
  pairKey,
  subview,
  viewport,
  now,
}) {
  const snapshot = buildSubviewCompositionHistorySnapshot(subview);
  return {
    version: SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION,
    pairKey,
    current: snapshot,
    default: snapshot,
    past: [],
    forward: [],
    viewport: normalizeSubviewCompositionViewport(viewport),
    updatedAt: nowTimestamp(now),
  };
}

export function activateSubviewCompositionHistory(assembly, {
  subview = assembly?.subview,
  viewport = assembly?.subviewCompositionViewport,
  now = Date.now(),
  stateOrLocale = "zh",
} = {}) {
  const pairKey = buildSubviewCompositionHistoryKey(assembly?.selectedChrName);
  if (!pairKey) return { assembly, pairKey: "", created: false, invalidated: false };
  const normalizedHistoryByKey = normalizeSubviewHistoryByKey(assembly?.subviewHistoryByKey);
  const rawRecord = assembly?.subviewHistoryByKey?.[pairKey];
  const record = normalizedHistoryByKey[pairKey];
  if (record?.version === SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION) {
    const appliedSubview = applySubviewCompositionHistorySnapshot(
      subview,
      record.current,
      pairKey,
      stateOrLocale,
    );
    if (appliedSubview) {
      return {
        assembly: {
          ...assembly,
          subview: appliedSubview,
          subviewCompositionViewport: record.viewport,
          subviewHistoryByKey: normalizedHistoryByKey,
        },
        pairKey,
        created: false,
        invalidated: false,
      };
    }
  }
  const nextRecord = createSubviewCompositionHistoryRecord({ pairKey, subview, viewport, now });
  return {
    assembly: {
      ...assembly,
      subview: { ...getSubviewState({ subview }), historyKey: pairKey },
      subviewCompositionViewport: nextRecord.viewport,
      subviewHistoryByKey: { ...normalizedHistoryByKey, [pairKey]: nextRecord },
    },
    pairKey,
    created: true,
    invalidated: Boolean(rawRecord),
  };
}

export function commitSubviewCompositionHistoryOperation(assembly, {
  nextSubview,
  operation,
  viewport = assembly?.subviewCompositionViewport,
  now = Date.now(),
  stateOrLocale = "zh",
} = {}) {
  const normalizedOperation = normalizeSubviewHistoryOperation(operation);
  if (!normalizedOperation || !nextSubview?.summary) {
    return { assembly, changed: false, pairKey: "" };
  }
  const activated = activateSubviewCompositionHistory(assembly, { now, viewport, stateOrLocale });
  const pairKey = activated.pairKey;
  const currentAssembly = activated.assembly;
  const record = currentAssembly?.subviewHistoryByKey?.[pairKey];
  if (!record) return { assembly, changed: false, pairKey };
  const currentSnapshot = record.current;
  const nextSnapshot = buildSubviewCompositionHistorySnapshot(nextSubview);
  if (areSubviewCompositionHistorySnapshotsEqual(currentSnapshot, nextSnapshot)) {
    return { assembly: currentAssembly, changed: false, pairKey };
  }
  const nextRecord = {
    ...record,
    current: nextSnapshot,
    past: [...record.past, { operation: normalizedOperation, snapshot: currentSnapshot }]
      .slice(-SUBVIEW_HISTORY_LIMIT),
    forward: [],
    viewport: normalizeSubviewCompositionViewport(viewport),
    updatedAt: nowTimestamp(now),
  };
  const appliedSubview = { ...getSubviewState({ subview: nextSubview }), historyKey: pairKey };
  return {
    assembly: {
      ...currentAssembly,
      subview: appliedSubview,
      subviewCompositionViewport: nextRecord.viewport,
      subviewAnchorStateByKey: syncSubviewAnchorState(currentAssembly, appliedSubview),
      subviewHistoryByKey: setSubviewHistoryRecord(currentAssembly, pairKey, nextRecord),
    },
    changed: true,
    pairKey,
    operation: normalizedOperation,
  };
}

function moveSubviewCompositionHistory(assembly, direction, {
  pairKey,
  now = Date.now(),
  stateOrLocale = "zh",
} = {}) {
  const records = normalizeSubviewHistoryByKey(assembly?.subviewHistoryByKey);
  const record = records[pairKey];
  const source = direction === "forward" ? record?.forward : record?.past;
  if (record?.version !== SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION
    || !Array.isArray(source) || !source.length) {
    return { assembly: { ...assembly, subviewHistoryByKey: records }, changed: false, pairKey };
  }
  const entry = source[source.length - 1];
  const appliedSubview = applySubviewCompositionHistorySnapshot(
    assembly?.subview,
    entry.snapshot,
    pairKey,
    stateOrLocale,
  );
  if (!appliedSubview) return { assembly, changed: false, invalidated: true, pairKey };
  const currentSnapshot = record.current;
  const nextRecord = direction === "forward"
    ? {
        ...record,
        current: entry.snapshot,
        past: [...record.past, { operation: entry.operation, snapshot: currentSnapshot }],
        forward: record.forward.slice(0, -1),
        updatedAt: nowTimestamp(now),
      }
    : {
        ...record,
        current: entry.snapshot,
        past: record.past.slice(0, -1),
        forward: [...record.forward, { operation: entry.operation, snapshot: currentSnapshot }],
        updatedAt: nowTimestamp(now),
      };
  return {
    assembly: {
      ...assembly,
      subview: appliedSubview,
      subviewCompositionViewport: nextRecord.viewport,
      subviewAnchorStateByKey: syncSubviewAnchorState(assembly, appliedSubview),
      subviewHistoryByKey: setSubviewHistoryRecord(assembly, pairKey, nextRecord),
    },
    changed: true,
    pairKey,
    operation: entry.operation,
  };
}

function createSubviewHistoryRecord({ pairKey, subview, subviewTrackDragOffsets, now }) {
  return {
    version: SUBVIEW_HISTORY_SCHEMA_VERSION,
    pairKey,
    current: buildSubviewEditableSnapshot(subview, subviewTrackDragOffsets),
    default: buildDefaultSubviewEditableSnapshot(subview),
    past: [],
    forward: [],
    updatedAt: nowTimestamp(now),
  };
}

function setSubviewHistoryRecord(assembly, pairKey, record) {
  const current = normalizeSubviewHistoryByKey(assembly?.subviewHistoryByKey);
  return {
    ...current,
    [pairKey]: record,
  };
}

function removeSubviewHistoryRecord(assembly, pairKey) {
  const current = normalizeSubviewHistoryByKey(assembly?.subviewHistoryByKey);
  const { [pairKey]: _removed, ...rest } = current;
  return rest;
}

function syncSubviewAnchorState(assembly, subview) {
  return setSubviewAnchorStateForSummary(
    assembly?.subviewAnchorStateByKey,
    subview?.summary,
    assembly?.selectedChrName,
    {
      activeAnchors: subview?.activeAnchors,
      manualAnchors: subview?.manualAnchors,
    },
  );
}

export function activateSubviewHistory(assembly, {
  subview = assembly?.subview,
  subviewTrackDragOffsets = assembly?.subviewTrackDragOffsets,
  now = Date.now(),
  stateOrLocale = "zh",
  validateRecord = null,
} = {}) {
  const historyKey = String(subview?.historyKey || "").trim();
  if (String(subview?.summary?.mode || "") === SUBVIEW_COMPOSITION_MODE
    || historyKey.startsWith("composition:")) {
    return activateSubviewCompositionHistory(assembly, {
      subview,
      viewport: assembly?.subviewCompositionViewport,
      now,
      stateOrLocale,
    });
  }
  const pairKey = buildSubviewAnchorStateKey(subview?.summary, assembly?.selectedChrName);
  if (!pairKey) {
    return { assembly, pairKey: "", created: false, invalidated: false };
  }
  const rawHistoryByKey = isPlainObject(assembly?.subviewHistoryByKey)
    ? assembly.subviewHistoryByKey
    : {};
  const normalizedHistoryByKey = normalizeSubviewHistoryByKey(rawHistoryByKey);
  const hadRawRecord = Object.prototype.hasOwnProperty.call(rawHistoryByKey, pairKey);
  const record = normalizedHistoryByKey[pairKey] || null;
  const recordIsCompatible = record && (
    typeof validateRecord !== "function" || validateRecord(record)
  );
  if (recordIsCompatible) {
    const applied = applySubviewEditableSnapshot(subview, record.current, stateOrLocale);
    if (applied) {
      const nextAssembly = {
        ...assembly,
        subview: applied.subview,
        subviewTrackDragOffsets: applied.subviewTrackDragOffsets,
        subviewAnchorStateByKey: syncSubviewAnchorState(assembly, applied.subview),
        subviewHistoryByKey: normalizedHistoryByKey,
      };
      return { assembly: nextAssembly, pairKey, created: false, invalidated: false };
    }
  }
  const cleanDefault = hadRawRecord
    ? applySubviewEditableSnapshot(
        subview,
        buildDefaultSubviewEditableSnapshot(subview),
        stateOrLocale,
      )
    : null;
  const initialSubview = cleanDefault?.subview || subview;
  const initialDragOffsets = cleanDefault?.subviewTrackDragOffsets || subviewTrackDragOffsets;
  const nextRecord = createSubviewHistoryRecord({
    pairKey,
    subview: initialSubview,
    subviewTrackDragOffsets: initialDragOffsets,
    now,
  });
  const historyWithoutInvalidRecord = hadRawRecord
    ? removeSubviewHistoryRecord({ subviewHistoryByKey: rawHistoryByKey }, pairKey)
    : normalizedHistoryByKey;
  const nextAssembly = {
    ...assembly,
    subview: initialSubview,
    subviewTrackDragOffsets: normalizeSubviewTrackDragOffsets(initialDragOffsets),
    subviewAnchorStateByKey: syncSubviewAnchorState(assembly, initialSubview),
    subviewHistoryByKey: {
      ...historyWithoutInvalidRecord,
      [pairKey]: nextRecord,
    },
  };
  return {
    assembly: nextAssembly,
    pairKey,
    created: true,
    invalidated: hadRawRecord,
  };
}

export function commitSubviewHistoryOperation(assembly, {
  nextSubview,
  nextSubviewTrackDragOffsets = assembly?.subviewTrackDragOffsets,
  operation,
  now = Date.now(),
  stateOrLocale = "zh",
} = {}) {
  if (String(nextSubview?.summary?.mode || "") === SUBVIEW_COMPOSITION_MODE
    || String(assembly?.subview?.historyKey || "").startsWith("composition:")) {
    return commitSubviewCompositionHistoryOperation(assembly, {
      nextSubview,
      operation,
      viewport: assembly?.subviewCompositionViewport,
      now,
      stateOrLocale,
    });
  }
  const normalizedOperation = normalizeSubviewHistoryOperation(operation);
  if (!normalizedOperation || !nextSubview?.summary) {
    return { assembly, changed: false, pairKey: "" };
  }
  const activated = activateSubviewHistory(assembly, { now, stateOrLocale });
  const pairKey = activated.pairKey;
  const currentAssembly = activated.assembly;
  const record = currentAssembly?.subviewHistoryByKey?.[pairKey];
  if (!pairKey || !record) {
    return { assembly, changed: false, pairKey: "" };
  }
  const currentSnapshot = buildSubviewEditableSnapshot(
    currentAssembly.subview,
    currentAssembly.subviewTrackDragOffsets,
  );
  const nextSnapshot = buildSubviewEditableSnapshot(nextSubview, nextSubviewTrackDragOffsets);
  if (areSubviewEditableSnapshotsEqual(currentSnapshot, nextSnapshot)) {
    return { assembly: currentAssembly, changed: false, pairKey };
  }
  const nextPast = [
    ...record.past,
    { operation: normalizedOperation, snapshot: currentSnapshot },
  ].slice(-SUBVIEW_HISTORY_LIMIT);
  const nextRecord = {
    ...record,
    current: nextSnapshot,
    past: nextPast,
    forward: [],
    updatedAt: nowTimestamp(now),
  };
  const nextAssembly = {
    ...currentAssembly,
    subview: nextSubview,
    subviewTrackDragOffsets: normalizeSubviewTrackDragOffsets(nextSubviewTrackDragOffsets),
    subviewAnchorStateByKey: syncSubviewAnchorState(currentAssembly, nextSubview),
    subviewHistoryByKey: setSubviewHistoryRecord(currentAssembly, pairKey, nextRecord),
  };
  return { assembly: nextAssembly, changed: true, pairKey, operation: normalizedOperation };
}

function moveSubviewHistory(assembly, direction, { now = Date.now(), stateOrLocale = "zh" } = {}) {
  const compositionPairKey = String(assembly?.subview?.historyKey || "").startsWith("composition:")
    ? String(assembly.subview.historyKey)
    : String(assembly?.subview?.summary?.mode || "") === SUBVIEW_COMPOSITION_MODE
      ? buildSubviewCompositionHistoryKey(assembly?.selectedChrName)
      : "";
  if (compositionPairKey) {
    return moveSubviewCompositionHistory(assembly, direction, {
      pairKey: compositionPairKey,
      now,
      stateOrLocale,
    });
  }
  const activated = activateSubviewHistory(assembly, { now, stateOrLocale });
  const pairKey = activated.pairKey;
  const currentAssembly = activated.assembly;
  const record = currentAssembly?.subviewHistoryByKey?.[pairKey];
  const source = direction === "forward" ? record?.forward : record?.past;
  if (!record || !Array.isArray(source) || !source.length) {
    return { assembly: currentAssembly, changed: false, pairKey };
  }
  const entry = source[source.length - 1];
  const currentSnapshot = buildSubviewEditableSnapshot(
    currentAssembly.subview,
    currentAssembly.subviewTrackDragOffsets,
  );
  const applied = applySubviewEditableSnapshot(currentAssembly.subview, entry.snapshot, stateOrLocale);
  if (!applied) {
    const cleanDefault = applySubviewEditableSnapshot(
      currentAssembly.subview,
      buildDefaultSubviewEditableSnapshot(currentAssembly.subview),
      stateOrLocale,
    );
    const cleanSubview = cleanDefault?.subview || currentAssembly.subview;
    const cleanDragOffsets = cleanDefault?.subviewTrackDragOffsets || [];
    const cleanRecord = createSubviewHistoryRecord({
      pairKey,
      subview: cleanSubview,
      subviewTrackDragOffsets: cleanDragOffsets,
      now,
    });
    return {
      assembly: {
        ...currentAssembly,
        subview: cleanSubview,
        subviewTrackDragOffsets: cleanDragOffsets,
        subviewAnchorStateByKey: syncSubviewAnchorState(currentAssembly, cleanSubview),
        subviewHistoryByKey: setSubviewHistoryRecord(currentAssembly, pairKey, cleanRecord),
      },
      changed: false,
      invalidated: true,
      pairKey,
    };
  }
  const nextRecord = direction === "forward"
    ? {
        ...record,
        current: entry.snapshot,
        past: [...record.past, { operation: entry.operation, snapshot: currentSnapshot }],
        forward: record.forward.slice(0, -1),
        updatedAt: nowTimestamp(now),
      }
    : {
        ...record,
        current: entry.snapshot,
        past: record.past.slice(0, -1),
        forward: [...record.forward, { operation: entry.operation, snapshot: currentSnapshot }],
        updatedAt: nowTimestamp(now),
      };
  const nextAssembly = {
    ...currentAssembly,
    subview: applied.subview,
    subviewTrackDragOffsets: applied.subviewTrackDragOffsets,
    subviewAnchorStateByKey: syncSubviewAnchorState(currentAssembly, applied.subview),
    subviewHistoryByKey: setSubviewHistoryRecord(currentAssembly, pairKey, nextRecord),
  };
  return {
    assembly: nextAssembly,
    changed: true,
    pairKey,
    operation: entry.operation,
  };
}

export function rollbackSubviewHistory(assembly, options = {}) {
  return moveSubviewHistory(assembly, "past", options);
}

export function restoreSubviewHistoryRollback(assembly, options = {}) {
  return moveSubviewHistory(assembly, "forward", options);
}

export function resetSubviewHistory(assembly, options = {}) {
  const compositionPairKey = String(assembly?.subview?.historyKey || "").startsWith("composition:")
    ? String(assembly.subview.historyKey)
    : String(assembly?.subview?.summary?.mode || "") === SUBVIEW_COMPOSITION_MODE
      ? buildSubviewCompositionHistoryKey(assembly?.selectedChrName)
      : "";
  if (compositionPairKey) {
    const activated = activateSubviewCompositionHistory(assembly, options);
    const record = activated.assembly?.subviewHistoryByKey?.[compositionPairKey];
    if (!record || areSubviewCompositionHistorySnapshotsEqual(record.current, record.default)) {
      return { assembly: activated.assembly, changed: false, pairKey: compositionPairKey };
    }
    const nextSubview = applySubviewCompositionHistorySnapshot(
      activated.assembly.subview,
      record.default,
      compositionPairKey,
      options.stateOrLocale,
    );
    return nextSubview
      ? commitSubviewCompositionHistoryOperation(activated.assembly, {
          nextSubview,
          operation: { kind: "reset" },
          viewport: record.viewport,
          now: options.now,
          stateOrLocale: options.stateOrLocale,
        })
      : { assembly: activated.assembly, changed: false, pairKey: compositionPairKey };
  }
  const activated = activateSubviewHistory(assembly, options);
  const record = activated.assembly?.subviewHistoryByKey?.[activated.pairKey];
  if (!record || areSubviewEditableSnapshotsEqual(record.current, record.default)) {
    return { assembly: activated.assembly, changed: false, pairKey: activated.pairKey };
  }
  const applied = applySubviewEditableSnapshot(
    activated.assembly.subview,
    record.default,
    options.stateOrLocale,
  );
  if (!applied) {
    return { assembly: activated.assembly, changed: false, pairKey: activated.pairKey };
  }
  return commitSubviewHistoryOperation(activated.assembly, {
    nextSubview: applied.subview,
    nextSubviewTrackDragOffsets: applied.subviewTrackDragOffsets,
    operation: { kind: "reset" },
    now: options.now,
    stateOrLocale: options.stateOrLocale,
  });
}

export function resolveCurrentSubviewHistory(assembly) {
  const explicitHistoryKey = String(assembly?.subview?.historyKey || "").trim();
  const pairKey = explicitHistoryKey.startsWith("composition:")
    ? explicitHistoryKey
    : String(assembly?.subview?.summary?.mode || "") === SUBVIEW_COMPOSITION_MODE
      ? buildSubviewCompositionHistoryKey(assembly?.selectedChrName)
      : buildSubviewAnchorStateKey(
          assembly?.subview?.summary,
          assembly?.selectedChrName,
        );
  if (!pairKey) {
    return { pairKey: "", record: null, canRollback: false, canRestoreRollback: false, canReset: false };
  }
  const record = normalizeSubviewHistoryByKey(assembly?.subviewHistoryByKey)[pairKey] || null;
  if (record?.version === SUBVIEW_COMPOSITION_HISTORY_SCHEMA_VERSION) {
    const currentSnapshot = buildSubviewCompositionHistorySnapshot(assembly?.subview);
    return {
      pairKey,
      record,
      canRollback: Boolean(record.past.length),
      canRestoreRollback: Boolean(record.forward.length),
      canReset: !areSubviewCompositionHistorySnapshotsEqual(currentSnapshot, record.default),
      rollbackOperation: record.past.at(-1)?.operation || null,
      restoreRollbackOperation: record.forward.at(-1)?.operation || null,
    };
  }
  const currentSnapshot = buildSubviewEditableSnapshot(
    assembly?.subview,
    assembly?.subviewTrackDragOffsets,
  );
  return {
    pairKey,
    record,
    canRollback: Boolean(record?.past.length),
    canRestoreRollback: Boolean(record?.forward.length),
    canReset: Boolean(record && !areSubviewEditableSnapshotsEqual(currentSnapshot, record.default)),
    rollbackOperation: record?.past.at(-1)?.operation || null,
    restoreRollbackOperation: record?.forward.at(-1)?.operation || null,
  };
}

function formatTemplate(template, vars = {}) {
  return String(template || "").replace(/\{(\w+)\}/g, (_match, key) => String(vars[key] ?? ""));
}

export function formatSubviewHistoryOperation(operation, i18n) {
  const normalized = normalizeSubviewHistoryOperation(operation);
  if (!normalized) {
    return String(i18n?.subview?.historyOperationFallback || "Subview edit");
  }
  const templates = i18n?.subview?.historyOperations || {};
  const template = templates[normalized.kind] || i18n?.subview?.historyOperationFallback;
  return formatTemplate(template, { count: normalized.count || 1 });
}

export function formatSubviewHistoryActionLabel(template, operation, i18n) {
  return formatTemplate(template, {
    action: formatSubviewHistoryOperation(operation, i18n),
  });
}
