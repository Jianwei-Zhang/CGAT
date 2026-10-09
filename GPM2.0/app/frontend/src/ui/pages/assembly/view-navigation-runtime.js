import { resolveTrackPrefs } from "./track-prefs.js";
import { readTrackViewportMetrics } from "./track-viewport.js";
import { clampViewRange, zoomViewRange, moveViewRange, parseViewSpan, formatViewSpan, readViewNavigationGeometry } from "./view-navigation-state.js";
import { renderViewNavigation, viewNavText } from "./view-navigation-ui.js";
import { assemblyPageSession } from "./page-session.js";
import { updateSubviewCompositionViewport } from "./subview-history-state.js";

const BOUND = Symbol("assemblyViewNavigation");
const viewKeyFor = (role) => role === "primary" ? "trackView" : "subviewTrackView";
const scrollSelector = (role) => `.assembly-track-scroll[data-track-role='${role}']`;

// One controller per route host: partial main/local replacement must not add gesture owners.
export function bindAssemblyViewNavigation(host, store, deps = {}) {
  const root = host?.closest?.("#route-host") || host;
  const document = root?.ownerDocument;
  if (!document?.createElement || !root?.querySelectorAll || !root?.addEventListener) return;
  const window = document.defaultView || globalThis.window;
  if (!root[BOUND]) root[BOUND] = createController(root, store, window);
  const controller = root[BOUND];
  controller.deps = deps;
  controller.mount();
}

export function unbindAssemblyViewNavigation(host) {
  const root = host?.closest?.("#route-host") || host;
  root?.[BOUND]?.dispose();
  if (root) delete root[BOUND];
}

function createController(root, store, window) {
  const controller = { deps: {}, roles: {}, gesture: null, frame: null, pending: null, persistTimers: new Map(), suppressClickUntil: 0, applyingRange: false };
  const listeners = [], scrollListeners = new Map();
  const listen = (target, type, callback, options) => {
    target?.addEventListener(type, callback, options);
    listeners.push(() => target?.removeEventListener(type, callback, options));
  };
  const gestureObserver = window?.MutationObserver ? new window.MutationObserver(() => {
    const gesture = controller.gesture;
    if (gesture && (!root.isConnected || !gesture.scroll?.isConnected || gesture.scroll !== scrollFor(gesture.role))) endGesture(true);
  }) : null;
  const requestFrame = (fn) => window?.requestAnimationFrame?.(fn) ?? setTimeout(fn, 16);
  const cancelFrame = (id) => { if (window?.cancelAnimationFrame) window.cancelAnimationFrame(id); else clearTimeout(id); };
  const locale = () => store.getState()?.locale || store.getState()?.assembly?.locale || "zh";
  const scrollFor = (role) => root.querySelector(scrollSelector(role));
  const geometryFor = (role) => {
    const scroll = scrollFor(role);
    return readViewNavigationGeometry(scroll, readTrackViewportMetrics(scroll, role));
  };
  const roleOf = (node) => node?.closest?.("[data-view-navigation]")?.dataset?.viewNavigation
    || node?.closest?.(".assembly-track-scroll[data-track-role]")?.dataset?.trackRole;
  const contextKey = (role) => {
    const state = store.getState(), a = state.assembly || {};
    return `${state.session?.projectId || ""}:${a.selectedChrName || ""}:${role === "primary" ? a.supportDatasetId || "" : JSON.stringify(a.subview?.summary || {})}`;
  };
  function persist(role, viewKey = viewKeyFor(role)) {
    clearTimeout(controller.persistTimers.get(viewKey));
    const key = contextKey(role);
    controller.persistTimers.set(viewKey, setTimeout(() => {
      controller.persistTimers.delete(viewKey);
      if (!root.isConnected || key !== contextKey(role) || !scrollFor(role)) return;
      if (viewKey === "trackView") void controller.deps.persistMainTrackViewState?.(root, store);
      else if (role === "subview" && store.getState().assembly?.subview?.summary?.mode === "composition") {
        void controller.deps.persistProjectAssemblyViewStateFromStore?.(root, store);
      }
    }, 160));
  }

  function sync(role) {
    const current = controller.roles[role], scroll = scrollFor(role);
    if (!current?.bar?.isConnected || !scroll) return;
    const bar = current.bar, geometry = geometryFor(role);
    scroll.dataset.viewInteractionMode = current.mode;
    scroll.classList.toggle("is-view-panning", controller.gesture?.role === role && controller.gesture?.kind === "pan");
    const modeSwitch = bar.querySelector("[data-view-nav-action='toggle-mode']");
    modeSwitch.setAttribute("aria-checked", String(current.mode === "hand"));
    modeSwitch.setAttribute("title", viewNavText(locale())[current.mode]);
    if (!geometry) {
      bar.querySelector("[data-view-nav-span]").textContent = "—";
      bar.querySelectorAll("button,input,select").forEach((node) => { node.disabled = true; });
      return;
    }
    const { domain, range } = geometry;
    bar.querySelectorAll("button,input,select").forEach((node) => { node.disabled = false; });
    const selection = bar.querySelector("[data-view-nav-window]");
    selection.style.left = `${100 * (range.start - domain.start) / (domain.end - domain.start)}%`;
    selection.style.width = `${100 * range.span / (domain.end - domain.start)}%`;
    selection.setAttribute("aria-valuemin", String(Math.round(domain.start)));
    selection.setAttribute("aria-valuemax", String(Math.round(domain.end - range.span)));
    selection.setAttribute("aria-valuenow", String(Math.round(range.start)));
    selection.setAttribute("aria-valuetext", `${Math.round(range.start).toLocaleString("en-US")}–${Math.round(range.start + range.span).toLocaleString("en-US")} bp`);
    const epsilon = Math.max(0.01, geometry.bpPerPx / 2);
    bar.querySelector("[data-view-nav-action='left']").disabled = range.start <= domain.start + epsilon;
    bar.querySelector("[data-view-nav-action='right']").disabled = range.start + range.span >= domain.end - epsilon;
    const formatted = formatViewSpan(range.span);
    bar.querySelector("[data-view-nav-span]").textContent = `${formatted.value} ${formatted.unit}`;
    const t = viewNavText(locale());
    bar.title = `${t.group}: ${Math.round(range.start).toLocaleString("en-US")}–${Math.round(range.start + range.span).toLocaleString("en-US")} bp`;
  }
  function applyRange(role, requested) {
    const geometry = geometryFor(role), scroll = scrollFor(role);
    if (!geometry || !scroll) return;
    const range = clampViewRange(requested, geometry.domain);
    if (!range) return;
    const state = store.getState(), viewKey = viewKeyFor(role), a = state.assembly;
    let next = { ...a, [viewKey]: resolveTrackPrefs({ ...a[viewKey], visibleSpanBp: Math.max(1, Math.round(range.span)) }) };
    if (role === "subview" && a.subview?.summary?.mode === "composition") {
      next = updateSubviewCompositionViewport(next, {
        ...a.subviewCompositionViewport, bpPerPx: range.span / scroll.clientWidth, leftBp: range.start,
      });
    }
    controller.deps.markNextTrackAutoFocusSuppressed?.();
    const anchorKey = role === "primary" ? "pendingPrimaryViewportAnchorBp" : "pendingSubviewViewportAnchorBp";
    assemblyPageSession[anchorKey] = range.start + range.span / 2;
    store.setState({ ...state, assembly: next });
    const rerender = role === "primary" ? controller.deps.rerenderAssemblyMainTab : controller.deps.rerenderSubviewPanel;
    controller.applyingRange = true;
    try { rerender?.(root, store); } finally { controller.applyingRange = false; }
    if (controller.gesture?.role === role) controller.gesture.scroll = scrollFor(role);
    // Explicit range positioning also covers scoped refreshes that don't restore an anchor.
    const currentScroll = scrollFor(role), metrics = readTrackViewportMetrics(currentScroll, role);
    if (metrics && currentScroll) {
      const px = (range.start - metrics.windowStartBp) * metrics.innerWidth / metrics.domainSpanBp - metrics.viewboxMinX;
      currentScroll.scrollLeft = Math.max(0, px);
    }
    sync(role);
    persist(role);
  }
  function flushPending() {
    if (controller.frame !== null) { cancelFrame(controller.frame); controller.frame = null; }
    const pending = controller.pending; controller.pending = null;
    if (pending && root.isConnected && pending.key === contextKey(pending.role)) applyRange(pending.role, pending.range);
  }
  function queueRange(role, range) {
    if (controller.pending && controller.pending.role !== role) flushPending();
    controller.pending = { role, range, key: contextKey(role) };
    if (controller.frame === null) controller.frame = requestFrame(() => { controller.frame = null; flushPending(); });
  }
  function closeTickOptions(control) {
    const menu = control?.querySelector?.("[data-view-tick-options]");
    if (!menu) return;
    menu.hidden = true;
    const input = control.querySelector("[data-view-tick-interval]");
    input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant");
    control.querySelector("[data-view-tick-toggle]").setAttribute("aria-expanded", "false");
  }
  function tickOptions(control) { return [...(control.querySelectorAll?.("[data-view-tick-option]") || [])]; }
  function selectTickOption(control, index) {
    const options = tickOptions(control);
    options.forEach((option, position) => option.setAttribute("aria-selected", String(position === index)));
    if (options[index]) control.querySelector("[data-view-tick-interval]").setAttribute("aria-activedescendant", options[index].id);
  }
  function openTickOptions(control) {
    for (const other of root.querySelectorAll("[data-view-tick-control]")) if (other !== control) closeTickOptions(other);
    const menu = control.querySelector("[data-view-tick-options]");
    if (!menu) return;
    menu.hidden = false;
    const input = control.querySelector("[data-view-tick-interval]");
    input.setAttribute("aria-expanded", "true");
    control.querySelector("[data-view-tick-toggle]").setAttribute("aria-expanded", "true");
    input.focus({ preventScroll: true });
    const index = tickOptions(control).findIndex(option => option.dataset.viewTickOption.toLowerCase() === input.value.trim().toLowerCase());
    selectTickOption(control, Math.max(0, index));
  }
  function changeTicks(control) {
    const input = control.querySelector("[data-view-tick-interval]");
    const value = String(input?.value || "").trim();
    const mode = value.toLowerCase() === "auto" ? "auto" : "manual";
    const viewKey = control.dataset.viewTickControl, state = store.getState();
    if (!["trackView", "subviewTrackView", "finalPathTrackView"].includes(viewKey)) return;
    const current = resolveTrackPrefs(state.assembly?.[viewKey]);
    const parsed = mode === "manual" ? parseViewSpan(value, "kb") : current.tickIntervalBp;
    if (parsed === null) {
      input?.setCustomValidity(viewNavText(locale()).tickInvalid); input?.reportValidity(); return;
    }
    input?.setCustomValidity("");
    closeTickOptions(control);
    controller.deps.rememberTrackViewportAnchor?.(root, viewKey);
    controller.deps.markNextTrackAutoFocusSuppressed?.();
    store.setState({ ...state, assembly: { ...state.assembly, [viewKey]: resolveTrackPrefs({ ...current, tickMode: mode, tickIntervalBp: parsed }) } });
    const rerender = viewKey === "trackView" ? controller.deps.rerenderAssemblyMainTab
      : viewKey === "subviewTrackView" ? controller.deps.rerenderSubviewPanel : controller.deps.rerenderFinalPathCard;
    controller.applyingRange = true;
    try { rerender?.(root, store); } finally { controller.applyingRange = false; }
    const next = root.querySelector(`[data-view-tick-control='${viewKey}']`);
    next?.querySelector("[data-view-tick-interval]")?.focus?.({ preventScroll: true });
    if (viewKey !== "finalPathTrackView") persist(viewKey === "trackView" ? "primary" : "subview");
  }
  function endGesture(cancelled = false) {
    const gesture = controller.gesture;
    if (!gesture) return;
    controller.gesture = null;
    gestureObserver?.disconnect();
    window?.removeEventListener("blur", onBlur);
    if (cancelled) { if (controller.frame !== null) cancelFrame(controller.frame); controller.frame = null; controller.pending = null; }
    else flushPending();
    window?.removeEventListener("pointermove", onPointerMove, true);
    window?.removeEventListener("pointerup", onPointerUp, true);
    window?.removeEventListener("pointercancel", onPointerCancel, true);
    try { root.releasePointerCapture?.(gesture.pointerId); } catch { /* removed capture */ }
    if (gesture.moved) controller.suppressClickUntil = Date.now() + 350;
    sync(gesture.role); persist(gesture.role);
  }
  function onPointerMove(event) {
    const gesture = controller.gesture;
    if (!gesture || event.pointerId !== gesture.pointerId) return;
    if (!root.isConnected || !gesture.scroll?.isConnected || gesture.scroll !== scrollFor(gesture.role)) { endGesture(true); return; }
    const dx = event.clientX - gesture.clientX;
    if (Math.abs(dx) >= 3) gesture.moved = true;
    if (!gesture.moved) return;
    event.preventDefault();
    if (gesture.kind === "pan") {
      const scroll = scrollFor(gesture.role);
      if (scroll) scroll.scrollLeft = gesture.scrollLeft - dx;
      sync(gesture.role);
      return;
    }
    const delta = dx / gesture.axisWidth * (gesture.domain.end - gesture.domain.start);
    let next;
    if (gesture.kind === "window") next = moveViewRange(gesture.range, gesture.domain, delta);
    else if (gesture.kind === "left") {
      const end = gesture.range.start + gesture.range.span;
      const minimum = clampViewRange({ start: gesture.range.start, span: 1 }, gesture.domain).span;
      const start = Math.max(gesture.domain.start, Math.min(end - minimum, gesture.range.start + delta));
      next = { start, span: end - start };
    } else {
      const minimum = clampViewRange({ start: gesture.range.start, span: 1 }, gesture.domain).span;
      const end = Math.max(gesture.range.start + minimum, Math.min(gesture.domain.end, gesture.range.start + gesture.range.span + delta));
      next = { start: gesture.range.start, span: end - gesture.range.start };
    }
    queueRange(gesture.role, next);
  }
  function onPointerUp(event) { if (event.pointerId === controller.gesture?.pointerId) endGesture(); }
  function onPointerCancel(event) { if (event.pointerId === controller.gesture?.pointerId) endGesture(true); }
  listen(root, "pointerdown", (event) => {
    // Keep focus and drafts on the combobox until a choice is explicitly committed.
    if (event.button === 0 && event.target?.closest?.("[data-view-tick-toggle],[data-view-tick-option]")) { event.preventDefault(); return; }
    if (event.button !== 0 || controller.gesture || event.target?.closest?.("input,select,textarea,[contenteditable='true']")) return;
    const role = roleOf(event.target);
    if (!["primary", "subview"].includes(role)) return;
    const edge = event.target.closest("[data-view-nav-edge]");
    const selection = event.target.closest("[data-view-nav-window]");
    const plot = event.target.closest(scrollSelector(role));
    const kind = edge?.dataset.viewNavEdge || (selection ? "window" : plot && controller.roles[role]?.mode === "hand" ? "pan" : null);
    const geometry = geometryFor(role), scroll = scrollFor(role);
    if (!kind || !geometry || !scroll) return;
    flushPending();
    event.preventDefault(); event.stopPropagation();
    controller.gesture = { role, kind, scroll, pointerId: event.pointerId, clientX: event.clientX,
      scrollLeft: scroll.scrollLeft, ...geometry, axisWidth: Math.max(1, controller.roles[role].bar.querySelector("[data-view-nav-axis]").clientWidth), moved: false };
    try { root.setPointerCapture?.(event.pointerId); } catch { /* synthetic/unsupported pointer */ }
    gestureObserver?.observe(root.ownerDocument, { childList: true, subtree: true });
    window?.addEventListener("blur", onBlur);
    window?.addEventListener("pointermove", onPointerMove, true);
    window?.addEventListener("pointerup", onPointerUp, true);
    window?.addEventListener("pointercancel", onPointerCancel, true);
    sync(role);
  }, true);
  listen(root, "wheel", (event) => {
    if (event.target?.closest?.("input,select,textarea,button,summary,[contenteditable='true']")) return;
    const axis = event.target?.closest?.("[data-view-nav-axis]");
    const plot = event.target?.closest?.(".assembly-track-scroll[data-track-role]");
    const role = roleOf(event.target), geometry = geometryFor(role);
    if ((!axis && !plot) || !["primary", "subview"].includes(role) || !geometry || controller.gesture) return;
    if (!Number.isFinite(event.deltaY) || !event.deltaY || Math.abs(event.deltaX || 0) > Math.abs(event.deltaY)) return;
    event.preventDefault(); event.stopPropagation();
    const range = controller.pending?.role === role && controller.pending.key === contextKey(role) ? controller.pending.range : geometry.range;
    const rect = plot?.getBoundingClientRect();
    const fraction = rect ? Math.max(0, Math.min(1, (event.clientX - rect.left) / geometry.domain.viewportWidth)) : 0.5;
    const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? geometry.domain.viewportWidth : 1);
    queueRange(role, zoomViewRange(range, geometry.domain, Math.exp(Math.max(-240, Math.min(240, delta)) / 400), fraction));
  }, { capture: true, passive: false });
  listen(root, "click", (event) => {
    const tickControl = event.target?.closest?.("[data-view-tick-control]");
    for (const control of root.querySelectorAll("[data-view-tick-control]")) if (control !== tickControl) closeTickOptions(control);
    if (tickControl && event.target.closest("[data-view-tick-toggle]")) {
      const menu = tickControl.querySelector("[data-view-tick-options]");
      if (menu.hidden) openTickOptions(tickControl); else closeTickOptions(tickControl);
      return;
    }
    const option = event.target?.closest?.("[data-view-tick-option]");
    if (tickControl && option) {
      tickControl.querySelector("[data-view-tick-interval]").value = option.dataset.viewTickOption;
      changeTicks(tickControl); return;
    }
    if (Date.now() < controller.suppressClickUntil && event.target?.closest?.(".assembly-track-scroll[data-track-role]")) {
      event.preventDefault(); event.stopImmediatePropagation(); return;
    }
    const button = event.target?.closest?.("[data-view-nav-action]");
    if (!button || button.disabled) return;
    const role = roleOf(button), current = controller.roles[role], action = button.dataset.viewNavAction;
    if (!current) return;
    flushPending();
    if (action === "toggle-mode") { endGesture(true); current.mode = current.mode === "mouse" ? "hand" : "mouse"; sync(role); return; }
    const geometry = geometryFor(role); if (!geometry) return;
    const { range, domain } = geometry;
    if (action === "left" || action === "right") applyRange(role, moveViewRange(range, domain, (action === "left" ? -1 : 1) * range.span / 2));
    if (action === "fit") {
      applyRange(role, { start: domain.start, span: domain.end - domain.start });
      // Fixed-pixel labels can extend beyond the old domain after a scale change.
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const next = geometryFor(role);
        if (!next || next.range.span >= next.domain.end - next.domain.start - next.bpPerPx) break;
        applyRange(role, { start: next.domain.start, span: next.domain.end - next.domain.start });
      }
    }
  }, true);
  listen(root, "change", (event) => {
    // Replacing a focused input can synchronously emit blur/change in Chromium.
    if (controller.applyingRange || event.target?.isConnected === false) return;
    const control = event.target?.closest?.("[data-view-tick-control]");
    if (control) changeTicks(control);
  });
  listen(root, "focusout", (event) => {
    const control = event.target?.closest?.("[data-view-tick-control]");
    if (control && !control.contains?.(event.relatedTarget)) closeTickOptions(control);
  });
  listen(root, "keydown", (event) => {
    const control = event.target?.closest?.("[data-view-tick-control]");
    if (control && ["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      const menu = control.querySelector("[data-view-tick-options]");
      if (menu?.hidden) openTickOptions(control);
      else {
        const options = tickOptions(control), index = options.findIndex(option => option.getAttribute("aria-selected") === "true");
        selectTickOption(control, Math.max(0, Math.min(options.length - 1, index + (event.key === "ArrowDown" ? 1 : -1))));
      }
      return;
    }
    if (control && event.key === "Enter") {
      event.preventDefault();
      const menu = control.querySelector("[data-view-tick-options]");
      if (menu && !menu.hidden) {
        const option = tickOptions(control).find(option => option.getAttribute("aria-selected") === "true");
        if (option) control.querySelector("[data-view-tick-interval]").value = option.dataset.viewTickOption;
      }
      changeTicks(control); return;
    }
    if (control && event.key === "Tab") closeTickOptions(control);
    if (control && event.key === "Escape") {
      event.preventDefault();
      const prefs = resolveTrackPrefs(store.getState().assembly?.[control.dataset.viewTickControl]);
      const input = control.querySelector("[data-view-tick-interval]");
      input.value = prefs.tickMode === "auto" ? "Auto" : String(prefs.tickIntervalBp / 1000);
      input.setCustomValidity(""); closeTickOptions(control);
      return;
    }
    const bar = event.target?.closest?.("[data-view-navigation]"); if (!bar) return;
    const edge = event.target.closest?.("[data-view-nav-edge]");
    if (!edge && !event.target.hasAttribute("data-view-nav-window")) return;
    const role = bar.dataset.viewNavigation, geometry = geometryFor(role); if (!geometry) return;
    if (["ArrowLeft", "ArrowRight"].includes(event.key)) {
      event.preventDefault();
      const direction = event.key === "ArrowLeft" ? -1 : 1;
      if (!edge) applyRange(role, moveViewRange(geometry.range, geometry.domain, direction * geometry.range.span / 2));
      else {
        const { range, domain } = geometry, end = range.start + range.span;
        const minimum = clampViewRange({ start: range.start, span: 1 }, domain).span;
        const delta = direction * range.span / 10;
        const start = edge.dataset.viewNavEdge === "left" ? Math.max(domain.start, Math.min(end - minimum, range.start + delta)) : range.start;
        const right = edge.dataset.viewNavEdge === "right" ? Math.max(start + minimum, Math.min(domain.end, end + delta)) : end;
        applyRange(role, { start, span: right - start });
      }
    }
  });
  function onBlur() { endGesture(true); }
  controller.dispose = () => {
    for (const control of root.querySelectorAll("[data-view-tick-control]")) closeTickOptions(control);
    endGesture(true);
    if (controller.frame !== null) cancelFrame(controller.frame);
    controller.frame = null; controller.pending = null;
    for (const timer of controller.persistTimers.values()) clearTimeout(timer);
    controller.persistTimers.clear();
    for (const remove of listeners) remove();
    for (const [scroll, listener] of scrollListeners) scroll.removeEventListener("scroll", listener);
    scrollListeners.clear(); controller.roles = {};
  };
  controller.mount = () => {
    for (const control of root.querySelectorAll("[data-view-tick-control]")) closeTickOptions(control);
    for (const role of ["primary", "subview"]) {
      const scroll = scrollFor(role), layout = scroll?.closest(".assembly-track-layout");
      if (!scroll || !layout?.parentNode) {
        if (controller.gesture?.role === role) endGesture(true);
        delete controller.roles[role];
        continue;
      }
      const key = contextKey(role), previous = controller.roles[role];
      if (controller.gesture?.role === role && (previous?.key !== key || (!controller.applyingRange && controller.gesture.scroll !== scroll))) endGesture(true);
      const current = previous?.key === key ? previous : { key, mode: "mouse" };
      const localeKey = locale();
      let bar = layout.previousElementSibling;
      if (bar?.dataset?.viewNavigation !== role || bar.dataset.navLocale !== localeKey) {
        if (bar?.dataset?.viewNavigation === role) bar.remove();
        const wrapper = root.ownerDocument.createElement("div"); wrapper.innerHTML = renderViewNavigation(role, localeKey);
        bar = wrapper.firstElementChild; bar.dataset.navLocale = localeKey;
        layout.parentNode.insertBefore(bar, layout);
      }
      current.bar = bar; controller.roles[role] = current;
      // On wide rows align the overview with the actual plot gutter, including font changes.
      // Narrow rows prioritize a usable axis with Full range attached on its right.
      if (typeof bar.getBoundingClientRect === "function") {
        const rangeControls = bar.querySelector(".view-nav-range");
        const axis = bar.querySelector("[data-view-nav-axis]");
        const previousInset = Number.parseFloat(rangeControls.style.paddingLeft) || 0;
        const inset = bar.clientWidth >= 700
          ? Math.max(0, previousInset + scroll.getBoundingClientRect().left - axis.getBoundingClientRect().left) : 0;
        rangeControls.style.paddingLeft = `${Math.round(inset)}px`;
      }
      if (!scrollListeners.has(scroll)) {
        const listener = () => sync(role);
        scroll.addEventListener("scroll", listener, { passive: true }); scrollListeners.set(scroll, listener);
      }
      sync(role);
    }
    for (const [scroll, listener] of scrollListeners) {
      if (!root.contains(scroll)) { scroll.removeEventListener("scroll", listener); scrollListeners.delete(scroll); }
    }
  };
  return controller;
}
