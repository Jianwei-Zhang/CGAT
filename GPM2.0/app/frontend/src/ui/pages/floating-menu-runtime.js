// Shared departure grace period for transient menus. Reentry cancels it;
// dialogs, persistent panels and editable-input commit timers are not menus.
export const FLOATING_MENU_CLOSE_DELAY_MS = 400;

function resolveTimerApi(options = {}) {
  return {
    setTimeout: options.setTimeout || globalThis.setTimeout.bind(globalThis),
    clearTimeout: options.clearTimeout || globalThis.clearTimeout.bind(globalThis),
  };
}

export function cancelDelayedFloatingClose(owner, timerKey, options = {}) {
  if (!owner || !timerKey || owner[timerKey] === null || owner[timerKey] === undefined) {
    return;
  }
  const timerApi = resolveTimerApi(options);
  timerApi.clearTimeout?.(owner[timerKey]);
  owner[timerKey] = null;
}

export function scheduleDelayedFloatingClose(owner, timerKey, callback, options = {}) {
  if (!owner || !timerKey || typeof callback !== "function") {
    return;
  }
  const timerApi = resolveTimerApi(options);
  cancelDelayedFloatingClose(owner, timerKey, options);
  const delayMs = Number(options.delayMs ?? FLOATING_MENU_CLOSE_DELAY_MS);
  if (delayMs <= 0) {
    callback();
    return;
  }
  owner[timerKey] = timerApi.setTimeout?.(() => {
    owner[timerKey] = null;
    callback();
  }, delayMs);
}

export function bindDelegatedDelayedFloatingClose(host, {
  rootSelector,
  timerKey,
  close,
  delayMs = FLOATING_MENU_CLOSE_DELAY_MS,
  setTimeout,
  clearTimeout,
} = {}) {
  if (typeof host?.addEventListener !== "function" || !rootSelector || !timerKey || typeof close !== "function") {
    return;
  }
  const timerOptions = { delayMs, setTimeout, clearTimeout };
  const enter = (event) => {
    if (event.target?.closest?.(rootSelector)) {
      cancelDelayedFloatingClose(host, timerKey, timerOptions);
    }
  };
  const leave = (event) => {
    const root = event.target?.closest?.(rootSelector);
    if (!root || root.contains?.(event.relatedTarget)) return;
    scheduleDelayedFloatingClose(host, timerKey, () => close(root), timerOptions);
  };
  host.addEventListener("pointerover", enter);
  host.addEventListener("pointerout", leave);
  host.addEventListener("focusin", enter);
  host.addEventListener("focusout", leave);
  return () => {
    cancelDelayedFloatingClose(host, timerKey, timerOptions);
    host.removeEventListener?.("pointerover", enter);
    host.removeEventListener?.("pointerout", leave);
    host.removeEventListener?.("focusin", enter);
    host.removeEventListener?.("focusout", leave);
  };
}

// Direct bindings for popup roots which own their lifecycle (e.g. submenus).
// Keep timers node-local so another popup cannot cancel or close this one.
export function bindDelayedFloatingClose(root, close, options = {}) {
  const timerKey = options.timerKey || Symbol("floatingCloseTimer");
  const cancel = () => cancelDelayedFloatingClose(root, timerKey, options);
  const leave = (event) => {
    if (!root.contains?.(event?.relatedTarget)) {
      scheduleDelayedFloatingClose(root, timerKey, close, options);
    }
  };
  root.addEventListener?.("pointerenter", cancel);
  root.addEventListener?.("pointerleave", leave);
  root.addEventListener?.("focusin", cancel);
  root.addEventListener?.("focusout", leave);
  return () => {
    cancel();
    root.removeEventListener?.("pointerenter", cancel);
    root.removeEventListener?.("pointerleave", leave);
    root.removeEventListener?.("focusin", cancel);
    root.removeEventListener?.("focusout", leave);
  };
}
