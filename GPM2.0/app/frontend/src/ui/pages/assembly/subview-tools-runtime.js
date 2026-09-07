import {
  SUBVIEW_TOOLS_STORAGE_KEY,
  buildSubviewToolsScopeKey,
  constrainSubviewToolsRect,
  isSubviewToolsPageVisible,
  normalizeSubviewToolsPreferences,
  resolveSubviewToolsTabKey,
} from "./subview-tools-state.js";
import { renderSubviewTools } from "./render-subview-tools.js";

export function bindSubviewTools(host, store, deps) {
  const doc = host?.ownerDocument;
  if (!doc?.body?.appendChild || !doc.createElement || !host?.addEventListener) return null;
  const existing = deps.session.subviewTools;
  if (existing?.host === host && existing.store === store) {
    existing.sync();
    return existing;
  }
  existing?.destroy();
  const runtime = createSubviewToolsRuntime(host, store, deps);
  deps.session.subviewTools = runtime;
  runtime.sync();
  return runtime;
}

function createSubviewToolsRuntime(host, store, deps) {
  const doc = host.ownerDocument;
  const win = deps.windowObject ?? doc.defaultView;
  let storage;
  let preferences = normalizeSubviewToolsPreferences(null);
  try {
    storage = deps.storage ?? win?.localStorage;
    preferences = normalizeSubviewToolsPreferences(JSON.parse(storage?.getItem(SUBVIEW_TOOLS_STORAGE_KEY) || "null"));
  } catch { /* A local UI preference must not block the assembly page. */ }
  let scopeKey = "";
  let overlay = null;
  let lastMarkup = "";
  let gesture = null;
  let frame = null;
  let destroyed = false;
  let viewportBound = false;
  const tabScroll = new Map();

  function captureContentFocus() {
    const active = doc.activeElement;
    const keys = [
      "subviewAnchorSearch",
      "subviewAnchorCheck",
      "subviewAnchorListRow",
      "subviewAnchorDelete",
      "subviewAnchorCopyGrt",
      "subviewCompositionSearch",
      "subviewCompositionCandidate",
      "subviewCompositionMember",
      "subviewCompositionFocus",
    ];
    const key = keys.find((candidate) => Object.hasOwn(active?.dataset || {}, candidate));
    if (!key) return null;
    return {
      key,
      value: active.dataset[key],
      selectionStart: Number.isInteger(active.selectionStart) ? active.selectionStart : null,
      selectionEnd: Number.isInteger(active.selectionEnd) ? active.selectionEnd : null,
    };
  }

  function restoreContentFocus(snapshot) {
    if (!snapshot || !overlay?.querySelectorAll) return;
    const attribute = snapshot.key.replace(/[A-Z]/g, (character) => `-${character.toLowerCase()}`);
    const target = Array.from(overlay.querySelectorAll(`[data-${attribute}]`))
      .find((node) => node.dataset?.[snapshot.key] === snapshot.value);
    if (!target) return;
    target.focus?.({ preventScroll: true });
    if (snapshot.selectionStart !== null && typeof target.setSelectionRange === "function") {
      target.setSelectionRange(snapshot.selectionStart, snapshot.selectionEnd);
    }
  }

  function viewport() {
    return {
      left: win?.visualViewport?.offsetLeft ?? 0,
      top: win?.visualViewport?.offsetTop ?? 0,
      width: win?.visualViewport?.width ?? win?.innerWidth ?? doc.documentElement.clientWidth,
      height: win?.visualViewport?.height ?? win?.innerHeight ?? doc.documentElement.clientHeight,
    };
  }

  function save() {
    try { storage?.setItem(SUBVIEW_TOOLS_STORAGE_KEY, JSON.stringify(preferences)); } catch { /* optional */ }
  }

  function applyRect() {
    if (!overlay) return;
    const panel = overlay.querySelector("[data-subview-tools-window]");
    if (!panel) return;
    for (const key of ["left", "top", "width", "height"]) {
      panel.style[key] = `${preferences.rect[key]}px`;
    }
  }

  function keepOnScreen() {
    preferences = { ...preferences, rect: constrainSubviewToolsRect(preferences.rect, viewport(),
      host.querySelector("[data-subview-panel]")?.getBoundingClientRect()) };
    applyRect();
  }

  function focusTab() {
    overlay?.querySelector(`[data-subview-tools-tab="${preferences.tab}"]`)?.focus({ preventScroll: true });
  }

  function bindViewport(active) {
    if (active === viewportBound) return;
    viewportBound = active;
    const method = active ? "addEventListener" : "removeEventListener";
    win?.[method]("resize", onViewportChanged);
    win?.visualViewport?.[method]("resize", onViewportChanged);
    win?.visualViewport?.[method]("scroll", onViewportChanged);
  }

  function onViewportChanged() {
    endGesture();
    keepOnScreen();
    save();
  }

  function unmount() {
    endGesture();
    bindViewport(false);
    overlay?.remove();
    overlay = null;
    lastMarkup = "";
  }

  function sync() {
    if (destroyed) return;
    const state = store.getState();
    const nextScope = buildSubviewToolsScopeKey(state);
    if (scopeKey !== nextScope) {
      endGesture();
      tabScroll.clear();
      deps.resetScope?.(nextScope);
      scopeKey = nextScope;
      lastMarkup = "";
    }
    const visible = preferences.open && isSubviewToolsPageVisible(state)
      && host.isConnected !== false && Boolean(host.querySelector("[data-subview-panel]"));
    host.querySelectorAll("[data-subview-tools-toggle]").forEach((button) => {
      button.setAttribute("aria-expanded", String(visible));
      button.classList.toggle("is-active", visible);
    });
    if (!visible) {
      unmount();
      return;
    }
    if (!overlay) {
      overlay = doc.createElement("div");
      overlay.dataset.subviewToolsHost = "1";
      overlay.addEventListener("click", onClick);
      overlay.addEventListener("input", onInput);
      overlay.addEventListener("dblclick", onDoubleClick);
      overlay.addEventListener("keydown", onKeyDown);
      overlay.addEventListener("pointerdown", onPointerDown);
      overlay.addEventListener("dragstart", onDragStart);
      overlay.addEventListener("dragover", onDragOver);
      overlay.addEventListener("drop", onDrop);
      overlay.addEventListener("dragend", onDragEnd);
      doc.body.appendChild(overlay);
      bindViewport(true);
    }
    const labels = deps.getLabels(state);
    const content = deps.renderContent?.({
      host, state, tab: preferences.tab, scopeKey, labels,
      escapeHtml: deps.escapeHtml, escapeAttr: deps.escapeAttr,
    }) || "";
    const markup = renderSubviewTools(preferences, labels, { ...deps, content });
    if (markup !== lastMarkup && !gesture) {
      const oldContent = overlay.querySelector("[data-subview-tools-content]");
      const scrollTop = oldContent?.scrollTop ?? tabScroll.get(preferences.tab) ?? 0;
      const focusSnapshot = captureContentFocus();
      overlay.innerHTML = markup;
      overlay.querySelector("[data-subview-tools-content]").scrollTop = scrollTop;
      restoreContentFocus(focusSnapshot);
      lastMarkup = markup;
    }
    keepOnScreen();
    deps.afterRender?.({ host, overlay, store, state, tab: preferences.tab, scopeKey });
  }

  function close({ focusToggle = true } = {}) {
    preferences = { ...preferences, open: false };
    save();
    sync();
    if (focusToggle) {
      host.querySelector("[data-subview-tools-toggle]")?.focus({ preventScroll: true });
    }
  }

  function selectTab(tab) {
    const scrollTop = overlay?.querySelector("[data-subview-tools-content]")?.scrollTop ?? 0;
    tabScroll.set(preferences.tab, scrollTop);
    preferences = normalizeSubviewToolsPreferences({ ...preferences, tab });
    save();
    sync();
    const content = overlay?.querySelector("[data-subview-tools-content]");
    if (content) content.scrollTop = tabScroll.get(preferences.tab) ?? 0;
    focusTab();
  }

  function onToggle(event) {
    if (!event.target?.closest?.("[data-subview-tools-toggle]")) return;
    if (preferences.open) return close();
    preferences = { ...preferences, open: true };
    sync();
    save();
    focusTab();
  }

  function onClick(event) {
    event.stopPropagation();
    if (event.target.closest("[data-subview-tools-close]")) return close();
    const tab = event.target.closest("[data-subview-tools-tab]")?.dataset.subviewToolsTab;
    if (tab) return selectTab(tab);
    deps.onAction?.(event, { host, store, scopeKey, sync });
  }

  function onInput(event) {
    event.stopPropagation();
    deps.onInput?.(event, { host, store, scopeKey, sync });
  }

  function onDoubleClick(event) {
    event.stopPropagation();
    deps.onDoubleClick?.(event, { host, store, scopeKey, sync });
  }

  function onKeyDown(event) {
    event.stopPropagation();
    deps.onContentKeyDown?.(event, { host, store, scopeKey, sync });
    if (event.defaultPrevented) return;
    if (event.key === "Escape") {
      event.preventDefault();
      if (!deps.closeContent?.()) close();
      else sync();
      return;
    }
    if (event.target.closest("[data-subview-tools-tab]")) {
      const nextTab = resolveSubviewToolsTabKey(preferences.tab, event.key);
      if (nextTab !== preferences.tab) {
        event.preventDefault();
        selectTab(nextTab);
      }
    }
    if (event.target.closest("[data-subview-tools-resize]") && event.key.startsWith("Arrow")) {
      event.preventDefault();
      const step = event.shiftKey ? 1 : 10;
      const delta = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[event.key];
      if (!delta) return;
      preferences = { ...preferences, rect: { ...preferences.rect,
        width: preferences.rect.width + delta[0], height: preferences.rect.height + delta[1] } };
      keepOnScreen();
      save();
    }
  }

  function onPointerDown(event) {
    event.stopPropagation();
    if (event.button !== 0 || gesture) return;
    const resize = event.target.closest("[data-subview-tools-resize]");
    const drag = event.target.closest("[data-subview-tools-drag]");
    if (!resize && (!drag || event.target.closest("button,input,select,textarea,a"))) return;
    event.preventDefault();
    gesture = { node: resize || drag, id: event.pointerId, x: event.clientX, y: event.clientY,
      rect: { ...preferences.rect }, resize: resize?.dataset.subviewToolsResize };
    gesture.node.setPointerCapture?.(event.pointerId);
    win?.addEventListener("pointermove", onPointerMove);
    win?.addEventListener("pointerup", onPointerEnd);
    win?.addEventListener("pointercancel", onPointerEnd);
  }

  function onDragStart(event) {
    deps.onDragStart?.(event, { host, store, scopeKey, sync });
  }

  function onDragOver(event) {
    deps.onDragOver?.(event, { host, store, scopeKey, sync });
  }

  function onDrop(event) {
    deps.onDrop?.(event, { host, store, scopeKey, sync });
  }

  function onDragEnd(event) {
    deps.onDragEnd?.(event, { host, store, scopeKey, sync });
  }

  function onPointerMove(event) {
    if (!gesture || event.pointerId !== gesture.id) return;
    const dx = event.clientX - gesture.x;
    const dy = event.clientY - gesture.y;
    const rect = { ...gesture.rect };
    if (gesture.resize) {
      if (gesture.resize !== "bottom") rect.width += dx;
      if (gesture.resize !== "right") rect.height += dy;
    } else {
      rect.left += dx;
      rect.top += dy;
    }
    preferences = { ...preferences, rect: constrainSubviewToolsRect(rect, viewport()) };
    if (frame === null) frame = win.requestAnimationFrame(() => { frame = null; applyRect(); });
  }

  function onPointerEnd(event) {
    if (event.pointerId !== gesture?.id) return;
    endGesture();
    sync();
  }

  function endGesture() {
    if (!gesture) return;
    if (frame !== null) win?.cancelAnimationFrame(frame);
    frame = null;
    if (gesture.node.hasPointerCapture?.(gesture.id)) gesture.node.releasePointerCapture(gesture.id);
    gesture = null;
    win?.removeEventListener("pointermove", onPointerMove);
    win?.removeEventListener("pointerup", onPointerEnd);
    win?.removeEventListener("pointercancel", onPointerEnd);
    applyRect();
    save();
  }

  host.addEventListener("click", onToggle);
  const unsubscribe = store.subscribe?.(sync);
  return {
    host, store, sync, close,
    destroy() {
      destroyed = true;
      unmount();
      unsubscribe?.();
      host.removeEventListener("click", onToggle);
      deps.resetScope?.("");
    },
  };
}
