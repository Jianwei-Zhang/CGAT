import { cancelDelayedFloatingClose, scheduleDelayedFloatingClose } from "../floating-menu-runtime.js";

const BOUND = Symbol("markerDisplayMenuBound");
const CLOSE_TIMER = "__markerDisplayCloseTimer";
const ROOT = ".assembly-marker-display";

export function bindMarkerDisplayMenus(host, options = {}) {
  if (!host?.addEventListener || host[BOUND]) return;
  for (let parent = host.parentElement; parent; parent = parent.parentElement) {
    if (parent[BOUND]) return;
  }
  if (!host.querySelectorAll?.(ROOT)?.length) return;
  host[BOUND] = true;
  const cancel = (root) => cancelDelayedFloatingClose(root, CLOSE_TIMER, options);
  const setOpen = (root, open) => {
    const button = root?.querySelector?.("[data-marker-display-toggle]");
    const panel = root?.querySelector?.(".assembly-marker-display-menu");
    if (!button || !panel) return;
    cancel(root);
    panel.hidden = !open;
    button.setAttribute("aria-expanded", String(open));
  };
  const schedule = (root) => scheduleDelayedFloatingClose(root, CLOSE_TIMER, () => setOpen(root, false), options);
  host.addEventListener("click", (event) => {
    const button = event.target?.closest?.("[data-marker-display-toggle]");
    if (!button) return;
    setOpen(button.closest(ROOT), button.getAttribute("aria-expanded") !== "true");
  });
  host.addEventListener("pointerdown", (event) => {
    const inside = event.target?.closest?.(ROOT);
    host.querySelectorAll?.(ROOT)?.forEach((root) => {
      if (root !== inside) setOpen(root, false);
    });
  }, true);
  for (const type of ["pointerover", "focusin"]) {
    host.addEventListener(type, (event) => {
      const root = event.target?.closest?.(ROOT);
      if (root) cancel(root);
    });
  }
  for (const type of ["pointerout", "focusout"]) {
    host.addEventListener(type, (event) => {
      const root = event.target?.closest?.(ROOT);
      if (root && !root.contains(event.relatedTarget)) schedule(root);
    });
  }
  host.addEventListener("keydown", (event) => {
    const root = event.target?.closest?.(ROOT);
    if (!root || event.key !== "Escape") return;
    // Move focus before hiding the panel; never collapse a native <details>
    // synchronously inside its focusout handler.
    root.querySelector("[data-marker-display-toggle]")?.focus?.();
    setOpen(root, false);
    event.preventDefault();
    event.stopPropagation();
  });
}
