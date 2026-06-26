import {
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
} from "./selection-state.js";
import {
  getSubviewState,
  normalizeSubviewTrackPairHiddenCtgs,
  normalizeSubviewTrackPairSelectionCtgs,
  resolveFilteredSubviewTrackPairSelectionsFromAssembly,
} from "./subview-state.js";

function normalizeBoolean(value) {
  if (value === true || value === "true") {
    return true;
  }
  if (value === false || value === "false") {
    return false;
  }
  return null;
}

function assertRuntimeDeps(label, deps, requiredNames) {
  const missing = requiredNames.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing ${label} runtime deps: ${missing.join(", ")}`);
}

function getConfirm(overrides = {}, deps = {}) {
  if (typeof overrides.confirm === "function") {
    return overrides.confirm;
  }
  if (typeof deps.confirm === "function") {
    return deps.confirm;
  }
  return (message) => globalThis.window?.confirm?.(message) ?? false;
}

function buildBatchFailedSuffix(stateOrLocale, count) {
  return Number(count) > 0 ? tAssembly(stateOrLocale, "runtime.batchFailedSuffix", { count }) : "";
}

function resolveBatchDeleteProgressLabel(assembly, assemblyCtgId) {
  const numericId = Number(assemblyCtgId);
  const ctg = Array.isArray(assembly?.chrCtgs)
    ? assembly.chrCtgs.find((item) => Number(item?.assemblyCtgId) === numericId)
    : null;
  const name = String(ctg?.name || ctg?.displayName || "").trim();
  return name || `Ctg${numericId}`;
}

function buildBatchDeleteProgress(assembly, assemblyCtgIds) {
  const normalizedIds = Array.isArray(assemblyCtgIds) ? assemblyCtgIds : [];
  return {
    open: true,
    current: 0,
    total: normalizedIds.length,
    items: normalizedIds.map((assemblyCtgId, index) => ({
      assemblyCtgId,
      label: resolveBatchDeleteProgressLabel(assembly, assemblyCtgId),
      status: index === 0 ? "running" : "pending",
      error: "",
    })),
  };
}

function updateBatchDeleteProgressItem(progress, assemblyCtgId, updates) {
  const numericId = Number(assemblyCtgId);
  const items = (Array.isArray(progress?.items) ? progress.items : []).map((item) => (
    Number(item?.assemblyCtgId) === numericId
      ? { ...item, ...updates }
      : { ...item }
  ));
  const current = items.filter((item) => item.status === "success" || item.status === "error").length;
  return {
    ...progress,
    current,
    items,
  };
}

function startNextBatchDeleteProgressItem(progress, assemblyCtgId) {
  const numericId = Number(assemblyCtgId);
  return {
    ...progress,
    items: (Array.isArray(progress?.items) ? progress.items : []).map((item) => (
      Number(item?.assemblyCtgId) === numericId && item.status === "pending"
        ? { ...item, status: "running" }
        : { ...item }
    )),
  };
}

function setBatchDeleteProgress(host, store, deps, progress) {
  const latestState = store.getState();
  store.setState({
    assembly: {
      ...latestState.assembly,
      batchDeleteProgress: progress,
    },
  });
  if (typeof deps.rerenderBatchDeleteProgress === "function") {
    deps.rerenderBatchDeleteProgress(host, store);
  }
}

function clearBatchDeleteProgress(host, store, deps) {
  setBatchDeleteProgress(host, store, deps, null);
}

function getBatchDeleteErrorMessage(error) {
  return String(error?.message || error || "error");
}

export async function applyEditorAction(host, store, payload, deps, overrides = {}) {
  assertRuntimeDeps("editor action", deps, [
    "appendAuditLog",
    "buildActionAuditDetail",
    "loadAssemblyView",
    "mapAssemblyError",
    "rerender",
    "runAction",
  ]);
  const { action, args, keepCurrentCtg } = payload || {};
  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return;
  }
  const useLocalRefresh = payload?.localRefresh === true || deps.localRefresh === true;
  const rerenderForMode = useLocalRefresh && typeof deps.rerenderAssemblyMainTab === "function"
    ? deps.rerenderAssemblyMainTab
    : deps.rerender;
  store.setState({
    assembly: {
      ...state.assembly,
      loading: useLocalRefresh ? state.assembly.loading : true,
      actionError: "",
      actionStatus: tAssembly(state, "runtime.actionRunningStatus", { action }),
      summary: tAssembly(state, "runtime.actionRunningSummary", { action }),
    },
  });
  if (!useLocalRefresh) {
    rerenderForMode(host, store);
  }

  const runAction = overrides.runAction || deps.runAction;
  const reloadView = overrides.reloadView
    || (useLocalRefresh && typeof deps.loadAssemblyViewForLocalAssemblyRefresh === "function"
      ? deps.loadAssemblyViewForLocalAssemblyRefresh
      : deps.loadAssemblyView);

  try {
    const result = await runAction({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
      action,
      args,
    });
    const changed = normalizeBoolean(result?.changed);
    const detail = deps.buildActionAuditDetail(action, args, changed);
    store.setState({
      assembly: {
        ...store.getState().assembly,
        actionStatus:
          changed === null
            ? tAssembly(store.getState(), "runtime.actionDone", { action })
            : tAssembly(store.getState(), "runtime.actionDoneChanged", {
              action,
              changed: changed ? "true" : "false",
            }),
      },
    });
    deps.appendAuditLog(store, {
      category: "editor",
      action,
      detail,
    });
    if (payload?.phasedOnlyRefresh === true && typeof deps.refreshPhasedTracksForCurrentChr === "function") {
      await deps.refreshPhasedTracksForCurrentChr(host, store);
    } else {
      await reloadView(host, store, {
        keepCurrentChr: true,
        keepCurrentCtg,
        renderLoading: !useLocalRefresh,
      });
    }
  } catch (error) {
    const mappedError = deps.mapAssemblyError({ error, stateOrLocale: store.getState() });
    store.setState({
      assembly: {
        ...store.getState().assembly,
        loading: false,
        actionError: mappedError.userMessage,
        actionStatus: tAssembly(store.getState(), "runtime.actionFailed", { action }),
      },
    });
    rerenderForMode(host, store);
  }
}

export async function deleteSelectedTrackCtgs(host, store, selectedIds, deps, overrides = {}) {
  assertRuntimeDeps("delete track ctgs", deps, [
    "runBatchDeleteTrackCtgs",
  ]);
  const normalized = filterPrimaryTrackSelectionCtgIds(selectedIds, store.getState().assembly);
  if (!normalized.length) {
    return;
  }
  const confirm = getConfirm(overrides, deps);
  if (!(await confirm(tAssembly(store.getState(), "runtime.batchDeleteConfirm", { count: normalized.length })))) {
    return;
  }
  await deps.runBatchDeleteTrackCtgs(host, store, normalized, overrides);
}

export async function deleteSelectedSubviewTrackPairCtgs(host, store, selectedEntries, deps, overrides = {}) {
  assertRuntimeDeps("delete subview track-pair ctgs", deps, [
    "rerender",
  ]);
  const state = store.getState();
  const currentSubview = (overrides.getSubviewState || getSubviewState)(state.assembly);
  if (String(currentSubview.summary?.mode || "") !== "track-pair") {
    return;
  }
  const normalizeSelections =
    overrides.normalizeSubviewTrackPairSelectionCtgs || normalizeSubviewTrackPairSelectionCtgs;
  const resolveSelections =
    overrides.resolveFilteredSubviewTrackPairSelectionsFromAssembly
    || resolveFilteredSubviewTrackPairSelectionsFromAssembly;
  const normalizeHidden =
    overrides.normalizeSubviewTrackPairHiddenCtgs || normalizeSubviewTrackPairHiddenCtgs;
  const normalized = resolveSelections({
    ...state.assembly,
    subview: {
      ...currentSubview,
      trackPairSelectedCtgs: normalizeSelections(selectedEntries),
    },
  });
  if (!normalized.length) {
    return;
  }
  const confirm = getConfirm(overrides, deps);
  if (!(await confirm(tAssembly(store.getState(), "runtime.batchSubviewDeleteConfirm", { count: normalized.length })))) {
    return;
  }
  const hiddenNext = normalizeHidden([
    ...normalizeHidden(currentSubview.trackPairHiddenCtgs),
    ...normalized,
  ]);
  store.setState({
    assembly: {
      ...state.assembly,
      subview: {
        ...currentSubview,
        trackPairHiddenCtgs: hiddenNext,
        trackPairSelectedCtgs: [],
      },
      actionStatus: tAssembly(state, "runtime.subviewDeletedStatus", { count: normalized.length }),
      actionError: "",
    },
  });
  deps.rerender(host, store);
}

export async function restoreSelectedDeletedCtgs(host, store, selectedRecordIds, deps, overrides = {}) {
  assertRuntimeDeps("restore deleted ctgs", deps, [
    "runBatchRestoreDeletedCtgs",
  ]);
  const normalized = normalizeDeletedCtgRecordIds(selectedRecordIds);
  if (!normalized.length) {
    return;
  }
  await deps.runBatchRestoreDeletedCtgs(host, store, normalized, overrides);
}

export async function runBatchDeleteTrackCtgs(host, store, selectedIds, deps, overrides = {}) {
  assertRuntimeDeps("batch delete track ctgs", deps, [
    "appendAuditLog",
    "buildActionAuditDetail",
    "loadAssemblyView",
    "mapAssemblyError",
    "rerender",
    "runAction",
  ]);
  const normalized = filterPrimaryTrackSelectionCtgIds(selectedIds, store.getState().assembly);
  if (!normalized.length) {
    return { deletedCount: 0, failedCount: 0 };
  }

  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return { deletedCount: 0, failedCount: normalized.length };
  }
  const useLocalRefresh = deps.localRefresh === true || overrides.localRefresh === true;

  store.setState({
    assembly: {
      ...state.assembly,
      loading: useLocalRefresh ? state.assembly.loading : true,
      actionError: "",
      actionStatus: tAssembly(state, "runtime.batchDeleteRunningStatus", { count: normalized.length }),
      summary: tAssembly(state, "runtime.batchDeleteRunningSummary"),
    },
  });
  if (!useLocalRefresh) {
    deps.rerender(host, store);
  }

  const runAction = overrides.runAction || deps.runAction;
  const reloadView = overrides.reloadView || deps.loadAssemblyView;
  const refreshAfterBatchDelete = overrides.refreshAfterBatchDelete || deps.refreshAfterBatchDelete;
  let deletedCount = 0;
  const deletedAssemblyCtgIds = [];
  const failed = [];
  let progress = buildBatchDeleteProgress(state.assembly, normalized);
  setBatchDeleteProgress(host, store, deps, progress);
  for (const [index, assemblyCtgId] of normalized.entries()) {
    try {
      const result = await runAction({
        workspaceRoot: state.session.workspacePath,
        projectId: state.session.projectId,
        action: "delete-ctg",
        args: { assemblyCtgId },
      });
      const changed = normalizeBoolean(result?.changed);
      if (changed !== false) {
        deletedCount += 1;
        deletedAssemblyCtgIds.push(assemblyCtgId);
      }
      deps.appendAuditLog(store, {
        category: "editor",
        action: "delete-ctg",
          detail: deps.buildActionAuditDetail("delete-ctg", { assemblyCtgId }, changed),
      });
      progress = updateBatchDeleteProgressItem(progress, assemblyCtgId, {
        status: "success",
        error: "",
      });
    } catch (error) {
      failed.push({ assemblyCtgId, error });
      progress = updateBatchDeleteProgressItem(progress, assemblyCtgId, {
        status: "error",
        error: getBatchDeleteErrorMessage(error),
      });
    }
    const nextAssemblyCtgId = normalized[index + 1];
    if (nextAssemblyCtgId !== undefined) {
      progress = startNextBatchDeleteProgressItem(progress, nextAssemblyCtgId);
    }
    setBatchDeleteProgress(host, store, deps, progress);
  }

  const applyFinalFeedback = () => {
    const latestState = store.getState();
    const firstError = failed[0]?.error || null;
    const mappedError = firstError ? deps.mapAssemblyError({ error: firstError, stateOrLocale: latestState }) : null;
    const failedSuffix = buildBatchFailedSuffix(latestState, failed.length);
    store.setState({
      assembly: {
        ...latestState.assembly,
        trackSelectedCtgIds: [],
        actionStatus: tAssembly(latestState, "runtime.batchDeleteDone", {
          deletedCount,
          total: normalized.length,
          failedSuffix,
        }),
        actionError: mappedError
          ? tAssembly(latestState, "runtime.batchDeletePartialError", { message: mappedError.userMessage })
          : "",
      },
    });
  };
  if (useLocalRefresh && typeof refreshAfterBatchDelete === "function") {
    applyFinalFeedback();
    try {
      await refreshAfterBatchDelete(host, store, {
        deletedAssemblyCtgIds,
        attemptedAssemblyCtgIds: normalized,
        failed,
        keepCurrentChr: true,
        keepCurrentCtg: false,
        renderLoading: false,
      });
    } finally {
      clearBatchDeleteProgress(host, store, deps);
    }
  } else {
    try {
      await reloadView(host, store, {
        keepCurrentChr: true,
        keepCurrentCtg: false,
        renderLoading: !useLocalRefresh,
      });
      applyFinalFeedback();
    } finally {
      clearBatchDeleteProgress(host, store, deps);
    }
    deps.rerender(host, store);
  }

  return {
    deletedCount,
    failedCount: failed.length,
  };
}

export async function runBatchRestoreDeletedCtgs(host, store, selectedRecordIds, deps, overrides = {}) {
  assertRuntimeDeps("batch restore deleted ctgs", deps, [
    "appendAuditLog",
    "buildActionAuditDetail",
    "loadAssemblyView",
    "mapAssemblyError",
    "rerender",
    "runAction",
  ]);
  const normalized = normalizeDeletedCtgRecordIds(selectedRecordIds);
  if (!normalized.length) {
    return { restoredCount: 0, failedCount: 0 };
  }

  const state = store.getState();
  if (!state.session.workspacePath || !state.session.projectId) {
    return { restoredCount: 0, failedCount: normalized.length };
  }
  const useLocalRefresh = deps.localRefresh === true || overrides.localRefresh === true;

  store.setState({
    assembly: {
      ...state.assembly,
      loading: useLocalRefresh ? state.assembly.loading : true,
      actionError: "",
      actionStatus: tAssembly(state, "runtime.batchRestoreRunningStatus", { count: normalized.length }),
      summary: tAssembly(state, "runtime.batchRestoreRunningSummary"),
    },
  });
  if (!useLocalRefresh) {
    deps.rerender(host, store);
  }

  const runAction = overrides.runAction || deps.runAction;
  const reloadView = overrides.reloadView || deps.loadAssemblyView;
  let restoredCount = 0;
  const failed = [];
  for (const deletedCtgRecordId of normalized) {
    try {
      await runAction({
        workspaceRoot: state.session.workspacePath,
        projectId: state.session.projectId,
        action: "restore-deleted-ctg",
        args: { deletedCtgRecordId },
      });
      restoredCount += 1;
      deps.appendAuditLog(store, {
        category: "editor",
        action: "restore-deleted-ctg",
        detail: deps.buildActionAuditDetail("restore-deleted-ctg", { deletedCtgRecordId }, true),
      });
    } catch (error) {
      failed.push({ deletedCtgRecordId, error });
    }
  }

  await reloadView(host, store, {
    keepCurrentChr: true,
    keepCurrentCtg: true,
    renderLoading: !useLocalRefresh,
  });
  if (typeof deps.rebaseTrackDragOffsetsAfterRestore === "function") {
    await deps.rebaseTrackDragOffsetsAfterRestore(host, store, state.assembly);
  }

  const latestState = store.getState();
  const firstError = failed[0]?.error || null;
  const mappedError = firstError ? deps.mapAssemblyError({ error: firstError, stateOrLocale: latestState }) : null;
  const failedSuffix = buildBatchFailedSuffix(latestState, failed.length);
  store.setState({
    assembly: {
      ...latestState.assembly,
      selectedDeletedCtgRecordIds: [],
      actionStatus: tAssembly(latestState, "runtime.batchRestoreDone", {
        restoredCount,
        total: normalized.length,
        failedSuffix,
      }),
      actionError: mappedError
        ? tAssembly(latestState, "runtime.batchRestorePartialError", { message: mappedError.userMessage })
        : "",
    },
  });
  deps.rerender(host, store);

  return {
    restoredCount,
    failedCount: failed.length,
  };
}
import { tAssembly } from "./i18n.js";
