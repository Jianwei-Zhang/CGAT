const REQUIRED_SEQ_ACTION_RUNTIME_DEPS = [
  "applyEditorAction",
  "pickSelectedMember",
];

function assertSeqActionRuntimeDeps(deps) {
  const missing = REQUIRED_SEQ_ACTION_RUNTIME_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing seq action runtime deps: ${missing.join(", ")}`);
}

export function bindSeqActions(host, store, deps) {
  assertSeqActionRuntimeDeps(deps);
  const queryHost = typeof host?.querySelector === "function"
    ? host.querySelector.bind(host)
    : () => null;
  const flipSeqButton = queryHost("#flip-seq-button");
  const hideShowSeqButton = queryHost("#hide-show-seq-button");
  const setEndTypeButton = queryHost("#set-end-type-button");

  flipSeqButton?.addEventListener("click", async () => {
    const member = deps.pickSelectedMember(store.getState().assembly);
    if (!member) {
      return;
    }
    await deps.applyEditorAction(host, store, {
      action: "flip-seq",
      args: { assemblySeqId: member.assemblySeqId },
      keepCurrentCtg: true,
    });
  });

  hideShowSeqButton?.addEventListener("click", async () => {
    const member = deps.pickSelectedMember(store.getState().assembly);
    if (!member) {
      return;
    }
    await deps.applyEditorAction(host, store, {
      action: member.hidden ? "show-seq" : "hide-seq",
      args: { assemblySeqId: member.assemblySeqId },
      keepCurrentCtg: true,
    });
  });

  setEndTypeButton?.addEventListener("click", async () => {
    const member = deps.pickSelectedMember(store.getState().assembly);
    const leftSelect = queryHost("#left-end-type-select");
    const rightSelect = queryHost("#right-end-type-select");
    if (!member || !leftSelect || !rightSelect) {
      return;
    }
    await deps.applyEditorAction(host, store, {
      action: "set-end-type",
      args: {
        assemblySeqId: member.assemblySeqId,
        leftEndType: leftSelect.value,
        rightEndType: rightSelect.value,
      },
      keepCurrentCtg: true,
    });
  });
}
