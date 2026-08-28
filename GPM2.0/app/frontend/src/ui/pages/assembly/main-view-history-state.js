export function createEmptyMainViewHistoryStatus(chrName = "") {
  return {
    projectId: 0,
    referenceChrId: 0,
    chrName: String(chrName || "").trim(),
    canUndo: false,
    canRedo: false,
    canReset: false,
    undoOperation: null,
    redoOperation: null,
    appliedOperationCount: 0,
    retainedOperationCount: 0,
    invalidated: false,
    inFlight: false,
  };
}

export function normalizeMainViewHistoryOperation(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const kind = String(value.kind || "").trim().toLowerCase();
  const targetCount = Math.max(0, Math.trunc(Number(value.targetCount || 0)));
  if (!kind || targetCount <= 0) {
    return null;
  }
  return {
    kind,
    targetCount,
    targetName: String(value.targetName || "").trim() || null,
  };
}

export function normalizeMainViewHistoryStatus(value, { chrName = "", inFlight = false } = {}) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const undoOperation = normalizeMainViewHistoryOperation(source.undoOperation);
  const redoOperation = normalizeMainViewHistoryOperation(source.redoOperation);
  return {
    projectId: Math.max(0, Math.trunc(Number(source.projectId || 0))),
    referenceChrId: Math.max(0, Math.trunc(Number(source.referenceChrId || 0))),
    chrName: String(source.chrName || chrName || "").trim(),
    canUndo: source.canUndo === true && Boolean(undoOperation),
    canRedo: source.canRedo === true && Boolean(redoOperation),
    canReset: source.canReset === true && Number(source.appliedOperationCount || 0) > 0,
    undoOperation,
    redoOperation,
    appliedOperationCount: Math.max(0, Math.trunc(Number(source.appliedOperationCount || 0))),
    retainedOperationCount: Math.max(0, Math.trunc(Number(source.retainedOperationCount || 0))),
    invalidated: source.invalidated === true,
    inFlight: inFlight === true || source.inFlight === true,
  };
}

const MAIN_VIEW_HISTORY_ELIGIBLE_ACTIONS = new Set([
  "rename-ctg",
  "flip-ctg",
  "delete-ctg",
  "restore-deleted-ctg",
  "flip-seq",
  "hide-seq",
  "show-seq",
  "set-end-type",
]);

export function isMainViewHistoryEligibleAction(action, args = {}) {
  const normalized = String(action || "").trim().toLowerCase();
  if (normalized === "flip-ctg" && Number(args?.phasedTrackItemId || 0) > 0) {
    return false;
  }
  return MAIN_VIEW_HISTORY_ELIGIBLE_ACTIONS.has(normalized);
}
