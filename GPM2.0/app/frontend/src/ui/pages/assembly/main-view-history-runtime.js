import { tAssembly } from "./i18n.js";
import {
  createEmptyMainViewHistoryStatus,
  normalizeMainViewHistoryStatus,
} from "./main-view-history-state.js";

function assertRuntimeDeps(deps) {
  const required = ["executeMainViewHistoryAction", "loadAssemblyView", "mapAssemblyError", "rerender"];
  const missing = required.filter((name) => typeof deps?.[name] !== "function");
  if (missing.length) {
    throw new TypeError(`Missing main-view history runtime deps: ${missing.join(", ")}`);
  }
}

function describeHistoryOperation(state, operation) {
  const kind = String(operation?.kind || "").trim().toLowerCase();
  const target = String(operation?.targetName || "").trim()
    || tAssembly(state, "mainHistory.targetFallback");
  const count = Math.max(0, Math.trunc(Number(operation?.targetCount || 0)));
  if (!kind) {
    return target;
  }
  try {
    return tAssembly(state, `mainHistory.operations.${kind}`, { target, count });
  } catch {
    return target;
  }
}

export async function runMainViewHistoryControlAction(host, store, action, deps, overrides = {}) {
  assertRuntimeDeps(deps);
  const state = store.getState();
  const chrName = String(state.assembly?.selectedChrName || "").trim();
  if (
    !state.session?.workspacePath
    || !state.session?.projectId
    || !chrName
    || chrName.toLowerCase() === "unplaced"
  ) {
    return false;
  }
  const history = normalizeMainViewHistoryStatus(state.assembly.mainViewHistory, { chrName });
  const previousSelectedCtgId = Number(state.assembly?.selectedCtgId || 0);
  const normalizedAction = String(action || "").trim().toLowerCase();
  if (
    history.inFlight
    || (normalizedAction === "undo" && !history.canUndo)
    || (normalizedAction === "redo" && !history.canRedo)
    || (normalizedAction === "reset" && !history.canReset)
  ) {
    return false;
  }
  if (normalizedAction === "reset") {
    const confirm = overrides.confirm || deps.confirm || ((message) => globalThis.window?.confirm?.(message));
    const message = tAssembly(state, "mainHistory.resetConfirm", {
      chrName,
      count: history.appliedOperationCount,
    });
    if (!(await confirm(message, { host, store }))) {
      return false;
    }
  }

  store.setState({
    assembly: {
      ...state.assembly,
      mainViewHistory: { ...history, inFlight: true },
      actionError: "",
      actionStatus: tAssembly(state, "mainHistory.running"),
    },
  });
  deps.rerender(host, store);
  try {
    const result = await deps.executeMainViewHistoryAction({
      workspaceRoot: state.session.workspacePath,
      projectId: state.session.projectId,
      chrName,
      action: normalizedAction,
    });
    const status = normalizeMainViewHistoryStatus(result?.status, { chrName });
    const affectedCtgIds = Array.isArray(result?.affectedCtgIds)
      ? result.affectedCtgIds.map(Number).filter((id) => id > 0)
      : [];
    const operationKind = String(result?.operation?.kind || "").trim();
    const operationSummary = describeHistoryOperation(store.getState(), result?.operation);
    const isSingleTarget = affectedCtgIds.length === 1;
    await deps.loadAssemblyView(host, store, {
      keepCurrentChr: true,
      keepCurrentCtg: true,
      renderLoading: false,
    });
    const latest = store.getState();
    const targetStillExists = isSingleTarget
      && latest.assembly.chrCtgs.some(
        (ctg) => Number(ctg?.assemblyCtgId) === Number(affectedCtgIds[0]),
      );
    const shouldLocate = targetStillExists && operationKind !== "reset";
    const previousSelectionStillExists = previousSelectedCtgId > 0
      && latest.assembly.chrCtgs.some(
        (ctg) => Number(ctg?.assemblyCtgId) === previousSelectedCtgId,
      );
    const selectedCtgId = shouldLocate
      ? affectedCtgIds[0]
      : (previousSelectionStillExists ? previousSelectedCtgId : null);
    const invalidated = result?.invalidated === true || status.invalidated;
    store.setState({
      assembly: {
        ...latest.assembly,
        mainViewHistory: status,
        selectedCtgId,
        historyHighlightCtgId: shouldLocate ? affectedCtgIds[0] : null,
        trackSelectedCtgIds: [],
        actionError: invalidated ? tAssembly(latest, "mainHistory.invalidated") : "",
        actionStatus: invalidated
          ? tAssembly(latest, "mainHistory.invalidated")
          : tAssembly(latest, "mainHistory.done", {
            action: tAssembly(latest, `mainHistory.actions.${normalizedAction}`),
            operation: operationSummary,
          }),
      },
    });
    if (shouldLocate && typeof deps.setPendingTrackAutoFocusMode === "function") {
      deps.setPendingTrackAutoFocusMode("start");
    }
    deps.rerender(host, store);
    if (shouldLocate && typeof deps.scheduleHighlightClear === "function") {
      deps.scheduleHighlightClear(host, store, affectedCtgIds[0]);
    }
    return result?.changed === true;
  } catch (error) {
    const latest = store.getState();
    const mapped = deps.mapAssemblyError({ error, stateOrLocale: latest });
    store.setState({
      assembly: {
        ...latest.assembly,
        mainViewHistory: {
          ...normalizeMainViewHistoryStatus(latest.assembly.mainViewHistory, { chrName }),
          inFlight: false,
        },
        actionError: mapped.userMessage,
        actionStatus: tAssembly(latest, "mainHistory.failed"),
      },
    });
    deps.rerender(host, store);
    return false;
  }
}

export function clearMainViewHistoryForUnavailableChr(assembly) {
  return {
    ...assembly,
    mainViewHistory: createEmptyMainViewHistoryStatus(""),
  };
}
