import { assemblyPageSession } from "./page-session.js";

export function resolveAnchorOffsetErrorKey(reason) {
  if (reason === "out-of-range") {
    return "runtime.subviewAnchorOffsetOutOfRange";
  }
  if (reason === "invalid-anchor") {
    return "runtime.subviewAnchorOffsetInvalidAnchor";
  }
  return "runtime.subviewAnchorOffsetInvalid";
}
export function createAssemblyConfirmController(deps = {}) {
  const {
    createOffsetSubviewManualAnchor,
    escapeAttr,
    escapeHtml,
    getAssemblyI18n,
    rerender,
    tAssembly,
  } = deps;
  if (
    typeof createOffsetSubviewManualAnchor !== "function"
    || typeof escapeAttr !== "function"
    || typeof escapeHtml !== "function"
    || typeof getAssemblyI18n !== "function"
    || typeof rerender !== "function"
    || typeof tAssembly !== "function"
  ) {
    throw new Error("confirm-controller.js missing required dependencies");
  }

function renderAssemblyConfirmModal(state) {
  const dialog = state.assembly?.confirmDialog;
  if (!dialog?.open) {
    return "";
  }
  const pageI18n = getAssemblyI18n(state).page || {};
  const promptsI18n = getAssemblyI18n(state).prompts || {};
  const id = String(dialog.id || "");
  const rawMode = String(dialog.mode || "").trim();
  const mode = rawMode === "prompt" || rawMode === "anchor-offset" ? rawMode : "confirm";
  const title = mode === "anchor-offset"
    ? (promptsI18n.anchorOffsetTitle || pageI18n.confirmDialogTitle || "确认操作")
    : (pageI18n.confirmDialogTitle || "确认操作");
  const message = String(dialog.message || "");
  const confirmLabel = pageI18n.confirmDialogConfirm || "确定";
  const cancelLabel = pageI18n.confirmDialogCancel || "取消";
  const dangerClass = dialog.danger === true || mode === "confirm" ? " is-danger" : "";
  const promptInput = mode === "prompt"
    ? `
        <input
          type="text"
          inputmode="numeric"
          class="assembly-confirm-input"
          value="${escapeAttr(String(dialog.defaultValue || ""))}"
          data-assembly-confirm-input="${escapeAttr(id)}"
          autofocus
        >
      `
    : "";
  const offsetDirection = ["left", "right"].includes(String(dialog.defaultDirection || "").trim())
    ? String(dialog.defaultDirection).trim()
    : "";
  const anchorOffsetResult = mode === "anchor-offset"
    ? createOffsetSubviewManualAnchor(dialog.anchorOffsetSourceEdge, {
      direction: offsetDirection,
      offsetBp: dialog.defaultValue,
    })
    : null;
  const hasAnchorOffsetDraft = mode === "anchor-offset"
    && Boolean(offsetDirection || String(dialog.defaultValue ?? "").trim());
  const anchorOffsetError = hasAnchorOffsetDraft && !anchorOffsetResult?.ok
    ? tAssembly(state, resolveAnchorOffsetErrorKey(anchorOffsetResult?.reason))
    : "";
  const anchorOffsetFields = mode === "anchor-offset"
    ? `
        <div class="assembly-anchor-offset-fields">
          <fieldset class="assembly-anchor-offset-direction">
            <legend>${escapeHtml(promptsI18n.anchorOffsetDirectionLabel || "Direction")}</legend>
            <label>
              <input
                type="radio"
                name="assembly-anchor-offset-direction-${escapeAttr(id)}"
                value="right"
                data-assembly-anchor-offset-direction="${escapeAttr(id)}"
                ${offsetDirection === "right" ? "checked" : ""}
              >
              <span>${escapeHtml(promptsI18n.anchorOffsetRight || "right")}</span>
            </label>
            <label>
              <input
                type="radio"
                name="assembly-anchor-offset-direction-${escapeAttr(id)}"
                value="left"
                data-assembly-anchor-offset-direction="${escapeAttr(id)}"
                ${offsetDirection === "left" ? "checked" : ""}
              >
              <span>${escapeHtml(promptsI18n.anchorOffsetLeft || "left")}</span>
            </label>
          </fieldset>
          <label class="assembly-anchor-offset-bp-field">
            <span>${escapeHtml(promptsI18n.anchorOffsetBpLabel || "Offset bp")}</span>
            <input
              type="number"
              min="1"
              step="1"
              inputmode="numeric"
              class="assembly-confirm-input"
              value="${escapeAttr(String(dialog.defaultValue || ""))}"
              data-assembly-confirm-input="${escapeAttr(id)}"
              autofocus
            >
          </label>
          <p
            class="assembly-anchor-offset-error${anchorOffsetError ? "" : " is-hidden"}"
            data-assembly-anchor-offset-error="${escapeAttr(id)}"
            aria-live="polite"
          >${escapeHtml(anchorOffsetError)}</p>
        </div>
      `
    : "";
  return `
    <div class="modal-overlay assembly-confirm-overlay" data-assembly-confirm-overlay="true">
      <article
        class="card modal-dialog assembly-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="${escapeAttr(title)}"
        data-assembly-confirm-dialog="${escapeAttr(id)}"
        data-assembly-confirm-mode="${escapeAttr(mode)}"
      >
        <h4 class="assembly-confirm-title${dangerClass}">${escapeHtml(title)}</h4>
        <p class="assembly-confirm-message${dangerClass}">${escapeHtml(message)}</p>
        ${promptInput}
        ${anchorOffsetFields}
        <div class="assembly-confirm-actions">
          <button
            type="button"
            class="button primary"
            data-assembly-confirm-action="confirm"
            data-assembly-confirm-id="${escapeAttr(id)}"
            ${mode === "anchor-offset" && !anchorOffsetResult?.ok ? "disabled" : ""}
          >${escapeHtml(confirmLabel)}</button>
          <button
            type="button"
            class="button ghost"
            data-assembly-confirm-action="cancel"
            data-assembly-confirm-id="${escapeAttr(id)}"
          >${escapeHtml(cancelLabel)}</button>
        </div>
      </article>
    </div>
  `;
}

function requestAssemblyConfirm(host, store, message) {
  if (!host || !store) {
    return Promise.resolve(globalThis.window?.confirm?.(message) ?? false);
  }
  const state = store.getState();
  const id = `assembly-confirm-${assemblyPageSession.assemblyConfirmDialogSeq += 1}`;
  const previousId = String(state.assembly?.confirmDialog?.id || "");
  const previousResolve = assemblyPageSession.pendingAssemblyConfirmResolvers.get(previousId);
  if (previousResolve) {
    assemblyPageSession.pendingAssemblyConfirmResolvers.delete(previousId);
    previousResolve(false);
  }
  return new Promise((resolve) => {
    assemblyPageSession.pendingAssemblyConfirmResolvers.set(id, resolve);
    store.setState({
      assembly: {
        ...state.assembly,
        confirmDialog: {
          open: true,
          id,
          mode: "confirm",
          danger: true,
          message: String(message || ""),
        },
      },
    });
    rerender(host, store);
  });
}

function requestAssemblyPrompt(host, store, message, defaultValue = "") {
  if (!host || !store) {
    if (typeof globalThis.window?.prompt !== "function") {
      return Promise.resolve("");
    }
    return Promise.resolve(globalThis.window.prompt(message, String(defaultValue)) ?? "");
  }
  const state = store.getState();
  const id = `assembly-confirm-${assemblyPageSession.assemblyConfirmDialogSeq += 1}`;
  const previousId = String(state.assembly?.confirmDialog?.id || "");
  const previousResolve = assemblyPageSession.pendingAssemblyConfirmResolvers.get(previousId);
  if (previousResolve) {
    assemblyPageSession.pendingAssemblyConfirmResolvers.delete(previousId);
    previousResolve("");
  }
  return new Promise((resolve) => {
    assemblyPageSession.pendingAssemblyConfirmResolvers.set(id, resolve);
    store.setState({
      assembly: {
        ...state.assembly,
        confirmDialog: {
          open: true,
          id,
          mode: "prompt",
          danger: false,
          message: String(message || ""),
          defaultValue: String(defaultValue ?? ""),
        },
      },
    });
    rerender(host, store);
  });
}

function requestAssemblyAnchorOffsetPrompt(host, store, options = {}) {
  const normalizedOptions = options && typeof options === "object" && !Array.isArray(options)
    ? options
    : { defaultValue: options };
  const defaultDirection = ["left", "right"].includes(
    String(normalizedOptions.defaultDirection || "").trim(),
  )
    ? String(normalizedOptions.defaultDirection).trim()
    : "";
  const defaultValue = String(normalizedOptions.defaultValue ?? "");
  const sourceEdge = normalizedOptions.sourceEdge && typeof normalizedOptions.sourceEdge === "object"
    ? normalizedOptions.sourceEdge
    : null;
  const message = tAssembly(store?.getState?.() || "zh", "prompts.anchorOffsetMessage");
  if (!host || !store) {
    if (typeof globalThis.window?.prompt !== "function") {
      return Promise.resolve(null);
    }
    const offsetInput = globalThis.window.prompt(message, String(defaultValue)) ?? "";
    return Promise.resolve({
      direction: defaultDirection || "right",
      offsetBp: offsetInput,
    });
  }
  const state = store.getState();
  const id = `assembly-confirm-${assemblyPageSession.assemblyConfirmDialogSeq += 1}`;
  const previousId = String(state.assembly?.confirmDialog?.id || "");
  const previousResolve = assemblyPageSession.pendingAssemblyConfirmResolvers.get(previousId);
  if (previousResolve) {
    assemblyPageSession.pendingAssemblyConfirmResolvers.delete(previousId);
    previousResolve(null);
  }
  return new Promise((resolve) => {
    assemblyPageSession.pendingAssemblyConfirmResolvers.set(id, resolve);
    store.setState({
      assembly: {
        ...state.assembly,
        confirmDialog: {
          open: true,
          id,
          mode: "anchor-offset",
          danger: false,
          message,
          defaultDirection,
          defaultValue,
          anchorOffsetSourceEdge: sourceEdge,
        },
      },
    });
    rerender(host, store);
  });
}

function resolveAssemblyConfirmDialog(host, store, { id, confirmed, value }) {
  const state = store.getState();
  const dialogId = String(id || state.assembly?.confirmDialog?.id || "");
  const resolve = assemblyPageSession.pendingAssemblyConfirmResolvers.get(dialogId);
  const rawMode = String(state.assembly?.confirmDialog?.mode || "").trim();
  const mode = rawMode === "prompt" || rawMode === "anchor-offset" ? rawMode : "confirm";
  assemblyPageSession.pendingAssemblyConfirmResolvers.delete(dialogId);
  store.setState({
    assembly: {
      ...state.assembly,
      confirmDialog: null,
    },
  });
  rerender(host, store);
  if (resolve) {
    if (mode === "anchor-offset") {
      resolve(confirmed && value && typeof value === "object" ? value : null);
      return;
    }
    resolve(mode === "prompt"
      ? (confirmed ? String(value ?? "") : "")
      : Boolean(confirmed));
  }
}

  return {
    renderAssemblyConfirmModal,
    requestAssemblyConfirm,
    requestAssemblyPrompt,
    requestAssemblyAnchorOffsetPrompt,
    resolveAssemblyConfirmDialog,
  };
}
