const REQUIRED_CTG_ACTION_RUNTIME_DEPS = [
  "applyEditorAction",
];

function assertCtgActionRuntimeDeps(deps) {
  const missing = REQUIRED_CTG_ACTION_RUNTIME_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing ctg action runtime deps: ${missing.join(", ")}`);
}

function getConfirm(overrides = {}) {
  if (typeof overrides.confirm === "function") {
    return overrides.confirm;
  }
  return (message) => globalThis.window?.confirm?.(message) ?? false;
}

export function bindCtgActions(host, store, deps) {
  assertCtgActionRuntimeDeps(deps);
  const confirm = getConfirm(deps);
  const queryHost = typeof host?.querySelector === "function"
    ? host.querySelector.bind(host)
    : () => null;
  const renameButton = queryHost("#rename-ctg-button");
  const flipCtgButton = queryHost("#flip-ctg-button");
  const deleteCtgButton = queryHost("#delete-ctg-button");

  renameButton?.addEventListener("click", async () => {
    const state = store.getState();
    const assemblyCtgId = state.assembly.selectedCtgId;
    const input = queryHost("#rename-ctg-input");
    const newName = String(input?.value || "").trim();
    if (!assemblyCtgId || !newName) {
      return;
    }
    await deps.applyEditorAction(host, store, {
      action: "rename-ctg",
      args: {
        assemblyCtgId,
        newName,
      },
      keepCurrentCtg: true,
    });
  });

  flipCtgButton?.addEventListener("click", async () => {
    const assemblyCtgId = store.getState().assembly.selectedCtgId;
    if (!assemblyCtgId) {
      return;
    }
    await deps.applyEditorAction(host, store, {
      action: "flip-ctg",
      args: { assemblyCtgId },
      keepCurrentCtg: true,
      localRefresh: true,
    });
  });

  deleteCtgButton?.addEventListener("click", async () => {
    const assemblyCtgId = store.getState().assembly.selectedCtgId;
    if (!assemblyCtgId) {
      return;
    }
    if (!(await confirm(tAssembly(store.getState(), "contextMenu.deleteContigConfirm", { assemblyCtgId })))) {
      return;
    }
    await deps.applyEditorAction(host, store, {
      action: "delete-ctg",
      args: { assemblyCtgId },
      keepCurrentCtg: false,
    });
  });

}
import { tAssembly } from "./i18n.js";
