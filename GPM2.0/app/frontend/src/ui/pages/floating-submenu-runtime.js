import { bindDelayedFloatingClose, cancelDelayedFloatingClose } from "./floating-menu-runtime.js";

export function positionContextSubmenuWithinViewport(group, submenu) {
  if (!group || !submenu || typeof group.getBoundingClientRect !== "function") {
    return;
  }
  const viewportWidth = Number((submenu.ownerDocument?.defaultView || globalThis.window)?.innerWidth)
    || Number(globalThis.document?.documentElement?.clientWidth)
    || 0;
  const viewportHeight = Number((submenu.ownerDocument?.defaultView || globalThis.window)?.innerHeight)
    || Number(globalThis.document?.documentElement?.clientHeight)
    || 0;
  if (viewportWidth <= 0 || viewportHeight <= 0) {
    return;
  }
  const margin = 8;
  const groupRect = group.getBoundingClientRect();
  const submenuRect = typeof submenu.getBoundingClientRect === "function"
    ? submenu.getBoundingClientRect()
    : {};
  const submenuWidth = Math.max(0, Number(submenuRect?.width || submenu.offsetWidth || 0));
  const submenuHeight = Math.max(0, Number(submenuRect?.height || submenu.offsetHeight || 0));
  const availableRight = Math.max(0, viewportWidth - Number(groupRect?.right || 0) - margin);
  const availableLeft = Math.max(0, Number(groupRect?.left || 0) - margin);
  submenu.classList?.toggle?.(
    "opens-left",
    submenuWidth > availableRight && availableLeft > availableRight,
  );

  const groupTop = Number(groupRect?.top || 0);
  const defaultTop = -4;
  const minTop = margin - groupTop;
  const maxTop = viewportHeight - margin - groupTop - submenuHeight;
  submenu.style.top = `${Math.max(minTop, Math.min(defaultTop, maxTop))}px`;
}

export function bindFloatingSubmenus(menu, { keyboard = false, ...options } = {}) {
  const cleanups = [];
  menu?.querySelectorAll?.("[data-context-submenu-group]").forEach((group) => {
    const submenu = group.querySelector?.("[data-context-submenu]");
    const trigger = group.querySelector?.("[data-context-submenu-trigger]");
    if (!submenu || !trigger) {
      return;
    }
    const closeTimer = Symbol("submenuCloseTimer");
    const open = () => {
      if (trigger.disabled || group.classList?.contains?.("is-disabled")) return;
      cancelDelayedFloatingClose(group, closeTimer, options);
      group.classList?.add?.("is-open");
      trigger?.setAttribute?.("aria-expanded", "true");
      positionContextSubmenuWithinViewport(group, submenu);
    };
    const close = () => {
      group.classList?.remove?.("is-open");
      trigger?.setAttribute?.("aria-expanded", "false");
    };
    const onClick = event => {
      event.stopPropagation();
      open();
      if (keyboard && event.detail === 0) submenu.querySelector("button:not(:disabled)")?.focus();
    };
    const onKey = event => {
      const choices = [...submenu.querySelectorAll("button:not(:disabled)")];
      const index = choices.indexOf(event.target);
      if (event.target === trigger && event.key === "ArrowRight") {
        open(); choices[0]?.focus();
      } else if ((event.key === "Escape" || event.key === "ArrowLeft") && group.classList.contains("is-open")) {
        close(); trigger.focus();
      } else if (index >= 0 && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
        choices[(index + (event.key === "ArrowDown" ? 1 : choices.length - 1)) % choices.length].focus();
      } else return;
      event.preventDefault(); event.stopPropagation();
    };
    const unbindClose = bindDelayedFloatingClose(group, close, { delayMs: 0, ...options, timerKey: closeTimer });
    group.addEventListener?.("pointerenter", open);
    trigger.addEventListener?.("click", onClick);
    if (keyboard) group.addEventListener("keydown", onKey);
    cleanups.push(() => {
      unbindClose();
      group.removeEventListener?.("pointerenter", open);
      trigger.removeEventListener?.("click", onClick);
      if (keyboard) group.removeEventListener("keydown", onKey);
      close();
    });
  });
  return () => cleanups.forEach(cleanup => cleanup());
}
