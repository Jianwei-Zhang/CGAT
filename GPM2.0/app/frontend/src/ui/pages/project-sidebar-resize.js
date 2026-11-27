import { projectIcon } from "./project-icons.js";

// UI-only preference: never write layout changes to project data or rerender previews per move.
const STORAGE_KEY = "gpm.project-library-width";
export const SIDEBAR_COLLAPSED_KEY = "gpm.project-library-collapsed";
const bindings = new WeakMap();
const MIN_WIDTH = 220;
const MAX_WIDTH = 560;
const DETAIL_MIN_WIDTH = 400;

export function readProjectSidebarCollapsed(storage = globalThis.window?.localStorage) {
  try {
    return storage?.getItem?.(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeProjectSidebarCollapsed(collapsed, storage = globalThis.window?.localStorage) {
  try {
    if (collapsed) storage?.setItem?.(SIDEBAR_COLLAPSED_KEY, "1");
    else storage?.removeItem?.(SIDEBAR_COLLAPSED_KEY);
  } catch {
    /* Optional preference. */
  }
}

export function projectSidebarBounds(containerWidth) {
  return { min: MIN_WIDTH, max: Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, containerWidth - DETAIL_MIN_WIDTH)) };
}

export function bindProjectSidebarResize(host) {
  bindings.get(host)?.();
  const browser = host.querySelector(".project-browser");
  const handle = host.querySelector(".project-sidebar-splitter");
  if (!browser || !handle) return;
  const view = browser.ownerDocument?.defaultView || globalThis.window;
  let preferred = null;
  let collapsed = false;
  try {
    const saved = Number(view.localStorage.getItem(STORAGE_KEY));
    if (Number.isFinite(saved) && saved >= MIN_WIDTH && saved <= MAX_WIDTH) preferred = saved;
    collapsed = view.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1";
  } catch { /* Storage can be unavailable; resizing still works for this binding. */ }
  let width = 280;
  let drag = null;
  let observer;
  let disposed = false;
  let containerWidth = browser.getBoundingClientRect().width;
  const listeners = [];
  const bounds = () => projectSidebarBounds(browser.getBoundingClientRect().width);
  const defaultWidth = () => Number.parseFloat(view.getComputedStyle(browser).getPropertyValue("--project-sidebar-default")) || 280;
  const apply = requested => {
    const { min, max } = bounds();
    width = Math.round(Math.max(min, Math.min(max, requested)));
    browser.style.setProperty("--project-sidebar-width", `${width}px`);
    handle.setAttribute("aria-valuemin", String(min));
    handle.setAttribute("aria-valuemax", String(max));
    handle.setAttribute("aria-valuenow", String(width));
  };
  const syncCollapsed = () => {
    if (collapsed) browser.classList.add("is-sidebar-collapsed");
    else browser.classList.remove("is-sidebar-collapsed");
    const toggleBtn = browser.querySelector?.("[data-project-sidebar-toggle]");
    if (toggleBtn) {
      const label = collapsed ? (toggleBtn.dataset?.expandLabel || "") : (toggleBtn.dataset?.collapseLabel || "");
      toggleBtn.setAttribute("aria-expanded", String(!collapsed));
      if (label) {
        toggleBtn.setAttribute("aria-label", label);
        toggleBtn.setAttribute("data-app-tooltip", label);
      }
      toggleBtn.innerHTML = projectIcon(collapsed ? "sidebarExpand" : "sidebarCollapse");
    }
    for (const selector of ["#project-import-button", "#project-open-button"]) {
      const btn = browser.querySelector?.(selector);
      if (!btn) continue;
      if (collapsed) {
        const label = btn.getAttribute?.("aria-label") || "";
        if (label) btn.setAttribute("data-app-tooltip", label);
      } else {
        btn.removeAttribute?.("data-app-tooltip");
      }
    }
  };
  const setCollapsed = next => {
    collapsed = Boolean(next);
    finish();
    writeProjectSidebarCollapsed(collapsed, view?.localStorage);
    syncCollapsed();
    if (!collapsed) apply(preferred ?? defaultWidth());
  };
  const save = () => {
    preferred = width;
    try { view.localStorage.setItem(STORAGE_KEY, String(width)); } catch { /* Optional preference. */ }
  };
  const finish = (commit = false) => {
    if (!drag) return;
    const { pointerId, startWidth } = drag;
    drag = null;
    browser.classList.remove("is-sidebar-resizing");
    if (commit) save();
    else apply(startWidth);
    if (handle.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
  };
  const on = (type, listener) => {
    handle.addEventListener(type, listener);
    listeners.push(() => handle.removeEventListener(type, listener));
  };
  const onNode = (node, type, listener) => {
    if (!node?.addEventListener) return;
    node.addEventListener(type, listener);
    listeners.push(() => node.removeEventListener(type, listener));
  };
  onNode(browser.querySelector?.("[data-project-sidebar-toggle]"), "click", () => {
    setCollapsed(!collapsed);
  });
  onNode(browser.querySelector?.("[data-project-sidebar-expand]"), "click", () => {
    if (collapsed) setCollapsed(false);
  });
  on("pointerdown", event => {
    if (collapsed || event.button !== 0 || event.isPrimary === false || drag) return;
    event.preventDefault();
    handle.focus({ preventScroll: true });
    handle.setPointerCapture(event.pointerId);
    drag = { pointerId: event.pointerId, startX: event.clientX, startWidth: width };
    browser.classList.add("is-sidebar-resizing");
  });
  on("pointermove", event => {
    if (drag?.pointerId !== event.pointerId) return;
    apply(drag.startWidth + event.clientX - drag.startX);
  });
  on("pointerup", event => {
    if (drag?.pointerId !== event.pointerId) return;
    apply(drag.startWidth + event.clientX - drag.startX);
    finish(true);
  });
  on("pointercancel", event => { if (drag?.pointerId === event.pointerId) finish(); });
  on("lostpointercapture", event => { if (drag?.pointerId === event.pointerId) finish(); });
  on("keydown", event => {
    if (event.key === "Escape" && drag) { event.preventDefault(); finish(); return; }
    if (collapsed || drag || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const { min, max } = bounds();
    const step = event.shiftKey ? 40 : 10;
    apply(event.key === "Home" ? min : event.key === "End" ? max : width + (event.key === "ArrowLeft" ? -step : step));
    save();
  });
  on("dblclick", () => {
    if (collapsed) return;
    finish();
    preferred = null;
    try { view.localStorage.removeItem(STORAGE_KEY); } catch { /* Optional preference. */ }
    apply(defaultWidth());
  });
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    finish();
    observer?.disconnect();
    listeners.splice(0).forEach(remove => remove());
    bindings.delete(host);
  };
  syncCollapsed();
  apply(preferred ?? defaultWidth());
  if (view.ResizeObserver) {
    observer = new view.ResizeObserver(() => {
      // Route replacement removes the observed grid and delivers a final zero-size observation.
      if (!browser.isConnected) { dispose(); return; }
      const nextWidth = browser.getBoundingClientRect().width;
      if (nextWidth === containerWidth) return;
      containerWidth = nextWidth;
      finish();
      if (!collapsed) apply(preferred ?? defaultWidth());
    });
    observer.observe(browser);
  }
  bindings.set(host, dispose);
  return dispose;
}
