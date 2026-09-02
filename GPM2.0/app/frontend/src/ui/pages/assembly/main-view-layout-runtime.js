import { tAssembly } from "./i18n.js";
import { normalizeMainViewHistoryStatus } from "./main-view-history-state.js";

const SUPPORTED_ACTIONS = new Set(["drag-ctg", "create-mirror", "delete-mirror"]);

function describeLayoutAction(state, operation, fallbackKind) {
  const kind = String(operation?.kind || fallbackKind || "").trim().toLowerCase();
  const target = String(operation?.targetName || "").trim()
    || tAssembly(state, "mainHistory.targetFallback");
  try {
    return tAssembly(state, `mainHistory.operations.${kind}`, { target, count: 1 });
  } catch {
    return target;
  }
}

export async function runMainViewLayoutAction(host, store, payload, deps) {
  const state = store.getState();
  const workspaceRoot = String(state?.session?.workspacePath || "").trim();
  const projectId = Number(state?.session?.projectId || 0);
  const chrName = String(state?.assembly?.selectedChrName || "").trim();
  const action = String(payload?.action || "").trim().toLowerCase();
  const history = normalizeMainViewHistoryStatus(state?.assembly?.mainViewHistory, { chrName });
  if (
    !workspaceRoot
    || !Number.isFinite(projectId)
    || projectId <= 0
    || !chrName
    || chrName.toLowerCase() === "unplaced"
    || !SUPPORTED_ACTIONS.has(action)
    || history.inFlight
  ) {
    return false;
  }
  const requiredDeps = [
    "loadProjectAssemblyViewState",
    "mapAssemblyError",
    "rerender",
    "runMainViewLayoutAction",
  ];
  const missing = requiredDeps.filter((name) => typeof deps?.[name] !== "function");
  if (missing.length) {
    throw new TypeError(`Missing main-view layout runtime deps: ${missing.join(", ")}`);
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

  const run = async (isCurrent = () => true) => {
    try {
      const result = await deps.runMainViewLayoutAction({
        workspaceRoot,
        projectId: Math.trunc(projectId),
        chrName,
        action,
        args: payload?.args || {},
      });
      if (!isCurrent()) {
        return false;
      }
      const persisted = await deps.loadProjectAssemblyViewState({
        workspaceRoot,
        projectId: Math.trunc(projectId),
      });
      if (!isCurrent()) {
        return false;
      }
      const latest = store.getState();
      const status = normalizeMainViewHistoryStatus(result?.status, { chrName });
      const invalidated = result?.invalidated === true || status.invalidated;
      store.setState({
        assembly: {
          ...latest.assembly,
          trackDragOffsets: persisted.trackDragOffsets,
          supportMirroredCtgs: persisted.supportMirroredCtgs,
          mainViewHistory: status,
          actionError: invalidated ? tAssembly(latest, "mainHistory.invalidated") : "",
          actionStatus: invalidated
            ? tAssembly(latest, "mainHistory.invalidated")
            : tAssembly(latest, "mainHistory.layoutDone", {
              operation: describeLayoutAction(latest, result?.operation, action),
            }),
        },
      });
      deps.rerender(host, store);
      return result?.changed === true;
    } catch (error) {
      if (!isCurrent()) {
        return false;
      }
      const latest = store.getState();
      const mapped = deps.mapAssemblyError({ error, stateOrLocale: latest });
      store.setState({
        assembly: {
          ...latest.assembly,
          mainViewHistory: {
            ...normalizeMainViewHistoryStatus(latest.assembly?.mainViewHistory, { chrName }),
            inFlight: false,
          },
          actionError: mapped.userMessage,
          actionStatus: tAssembly(latest, "mainHistory.failed"),
        },
      });
      deps.rerender(host, store);
      return false;
    }
  };
  if (typeof deps.runSerializedProjectViewMutation === "function") {
    return deps.runSerializedProjectViewMutation(store, run);
  }
  return run();
}
