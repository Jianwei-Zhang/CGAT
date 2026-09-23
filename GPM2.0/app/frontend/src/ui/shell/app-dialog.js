let dialogSequence = 0;

const copy = {
  zh: { confirm: "确认操作", prompt: "输入信息", notice: "提示", ok: "确定", cancel: "取消" },
  en: { confirm: "Confirm action", prompt: "Enter information", notice: "Notice", ok: "OK", cancel: "Cancel" },
};

function requestDialog(mode, message, options = {}) {
  const doc = globalThis.document;
  const cancelled = mode === "prompt" ? null : false;
  if (!doc?.body) return Promise.resolve(cancelled);
  const locale = options.locale || options.store?.getState?.()?.locale
    || doc.querySelector("#app-language-select")?.value || "zh";
  const labels = copy[locale === "en" ? "en" : "zh"];
  const id = `app-dialog-${++dialogSequence}`;
  const previousFocus = doc.activeElement;
  const dialog = doc.createElement("dialog");
  dialog.className = "app-dialog";
  dialog.setAttribute("aria-labelledby", `${id}-title`);
  dialog.setAttribute("aria-describedby", `${id}-message`);
  const form = doc.createElement("form");
  const title = doc.createElement("h2");
  title.id = `${id}-title`;
  title.className = "app-dialog-title";
  title.textContent = options.title || labels[mode];
  const body = doc.createElement("p");
  body.id = `${id}-message`;
  body.className = "app-dialog-message";
  body.textContent = String(message ?? "");
  form.append(title, body);
  let input;
  if (mode === "prompt") {
    input = doc.createElement("input");
    input.type = "text";
    input.className = "app-dialog-input";
    input.value = String(options.defaultValue ?? "");
    input.autocomplete = "off";
    input.setAttribute("aria-labelledby", body.id);
    form.append(input);
  }
  const actions = doc.createElement("div");
  actions.className = "app-dialog-actions";
  const cancel = doc.createElement("button");
  cancel.type = "button";
  cancel.className = "button ghost";
  cancel.dataset.appDialogAction = "cancel";
  cancel.textContent = options.cancelLabel || labels.cancel;
  const confirm = doc.createElement("button");
  confirm.type = "submit";
  confirm.className = "button primary";
  confirm.dataset.appDialogAction = "confirm";
  confirm.textContent = options.confirmLabel || labels.ok;
  if (mode !== "notice") actions.append(cancel);
  actions.append(confirm);
  form.append(actions);
  dialog.append(form);
  doc.body.append(dialog);

  return new Promise(resolve => {
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      if (dialog.open) dialog.close();
      dialog.remove();
      if (previousFocus?.isConnected) previousFocus.focus();
      resolve(value);
    };
    form.addEventListener("submit", event => {
      event.preventDefault();
      finish(input ? input.value : true);
    });
    cancel.addEventListener("click", () => finish(cancelled));
    dialog.addEventListener("cancel", event => {
      event.preventDefault();
      finish(cancelled);
    });
    dialog.addEventListener("close", () => finish(cancelled));
    dialog.showModal();
    (input || (mode === "notice" ? confirm : cancel)).focus();
    input?.select();
  });
}

export function requestAppConfirm(message, options = {}) {
  return requestDialog("confirm", message, options);
}

export function requestAppPrompt(message, defaultValue = "", options = {}) {
  return requestDialog("prompt", message, { ...options, defaultValue });
}

export function requestAppNotice(message, options = {}) {
  return requestDialog("notice", message, options);
}
