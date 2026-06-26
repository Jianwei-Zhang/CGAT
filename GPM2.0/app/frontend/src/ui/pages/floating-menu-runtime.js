export const FLOATING_MENU_CLOSE_DELAY_MS = 400;

function resolveTimerApi(options = {}) {
  return {
    setTimeout: options.setTimeout || globalThis.setTimeout,
    clearTimeout: options.clearTimeout || globalThis.clearTimeout,
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
  owner[timerKey] = timerApi.setTimeout?.(() => {
    owner[timerKey] = null;
    callback();
  }, Number(options.delayMs || FLOATING_MENU_CLOSE_DELAY_MS));
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
  host.addEventListener("pointerover", (event) => {
    if (event.target?.closest?.(rootSelector)) {
      cancelDelayedFloatingClose(host, timerKey, timerOptions);
    }
  });
  host.addEventListener("pointerout", (event) => {
    const root = event.target?.closest?.(rootSelector);
    if (!root || root.contains?.(event.relatedTarget)) {
      return;
    }
    scheduleDelayedFloatingClose(host, timerKey, () => close(root), timerOptions);
  });
}
