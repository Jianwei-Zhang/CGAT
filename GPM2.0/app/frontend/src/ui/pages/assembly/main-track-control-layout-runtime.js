const MAIN_TRACK_CONTROL_LAYOUT_BOUND = Symbol("mainTrackControlLayoutBound");
const MAIN_TRACK_CONTROL_LAYOUT_SELECTOR = "[data-main-track-control-layout]";
const LAYOUT_TOLERANCE_PX = 1;

function readFiniteWidth(value) {
  const numeric = typeof value === "string" ? Number.parseFloat(value) : Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : 0;
}

function measureElementWidth(node) {
  if (!node) {
    return 0;
  }
  const rectWidth = readFiniteWidth(node.getBoundingClientRect?.()?.width);
  return rectWidth
    || readFiniteWidth(node.offsetWidth)
    || readFiniteWidth(node.clientWidth);
}

function readElementGap(node, getComputedStyleImpl) {
  if (!node || typeof getComputedStyleImpl !== "function") {
    return 0;
  }
  try {
    const style = getComputedStyleImpl(node);
    return readFiniteWidth(style?.columnGap) || readFiniteWidth(style?.gap);
  } catch {
    return 0;
  }
}

function measureChildContentWidth(node, getComputedStyleImpl) {
  const widths = Array.from(node?.children || [])
    .map((child) => measureElementWidth(child))
    .filter((width) => width > 0);
  if (!widths.length) {
    return 0;
  }
  const gap = readElementGap(node, getComputedStyleImpl);
  return widths.reduce((total, width) => total + width, 0) + gap * (widths.length - 1);
}

export function resolveMainTrackControlLayout({
  availableWidth = 0,
  titleWidth = 0,
  quickActionsWidth = 0,
  inlineControlsWidth = 0,
  headerGap = 0,
  actionsGap = 0,
} = {}) {
  const available = Math.max(0, Number(availableWidth) || 0);
  const title = Math.max(0, Number(titleWidth) || 0);
  const quick = Math.max(0, Number(quickActionsWidth) || 0);
  const controls = Math.max(0, Number(inlineControlsWidth) || 0);
  const outerGap = title > 0 && (quick > 0 || controls > 0)
    ? Math.max(0, Number(headerGap) || 0)
    : 0;
  const innerGap = quick > 0 && controls > 0
    ? Math.max(0, Number(actionsGap) || 0)
    : 0;
  const singleRowWidth = title + outerGap + quick + innerGap + controls;
  if (singleRowWidth <= available + LAYOUT_TOLERANCE_PX) {
    return "single";
  }
  const titleRowWidth = title + (quick > 0 ? outerGap + quick : 0);
  if (titleRowWidth <= available + LAYOUT_TOLERANCE_PX) {
    return "split";
  }
  return "stacked";
}

export function measureMainTrackControlLayout(header, options = {}) {
  const getComputedStyleImpl = options.getComputedStyle
    || globalThis.getComputedStyle?.bind(globalThis);
  const title = header?.querySelector?.("[data-main-track-control-title]");
  const actions = header?.querySelector?.("[data-main-track-control-actions]");
  const quickActions = header?.querySelector?.("[data-main-track-quick-actions]");
  const inlineControls = header?.querySelector?.("[data-main-track-inline-controls]");
  return {
    availableWidth: measureElementWidth(header),
    titleWidth: measureElementWidth(title),
    quickActionsWidth: measureChildContentWidth(quickActions, getComputedStyleImpl),
    inlineControlsWidth: measureChildContentWidth(inlineControls, getComputedStyleImpl),
    headerGap: readElementGap(header, getComputedStyleImpl),
    actionsGap: readElementGap(actions, getComputedStyleImpl),
  };
}

export function syncMainTrackControlLayout(header, options = {}) {
  if (!header?.dataset) {
    return "stacked";
  }
  const layout = resolveMainTrackControlLayout(
    measureMainTrackControlLayout(header, options),
  );
  if (header.dataset.mainTrackControlLayout !== layout) {
    header.dataset.mainTrackControlLayout = layout;
  }
  return layout;
}

function resolveFrameApi(options = {}) {
  const request = typeof options.requestAnimationFrame === "function"
    ? options.requestAnimationFrame
    : (typeof globalThis.requestAnimationFrame === "function"
      ? globalThis.requestAnimationFrame.bind(globalThis)
      : (callback) => globalThis.setTimeout(() => callback(Date.now()), 16));
  const cancel = typeof options.cancelAnimationFrame === "function"
    ? options.cancelAnimationFrame
    : (typeof globalThis.cancelAnimationFrame === "function"
      ? globalThis.cancelAnimationFrame.bind(globalThis)
      : (handle) => globalThis.clearTimeout(handle));
  return { request, cancel };
}

function bindMainTrackControlHeader(header, options = {}) {
  const existing = header?.[MAIN_TRACK_CONTROL_LAYOUT_BOUND];
  if (existing) {
    existing.sync();
    return existing.cleanup;
  }
  const { request, cancel } = resolveFrameApi(options);
  const ResizeObserverImpl = Object.hasOwn(options, "ResizeObserver")
    ? options.ResizeObserver
    : globalThis.ResizeObserver;
  const windowObject = Object.hasOwn(options, "windowObject")
    ? options.windowObject
    : globalThis.window;
  let observer = null;
  let frameHandle;
  let frameScheduled = false;
  let disposed = false;

  const sync = () => syncMainTrackControlLayout(header, options);
  const cleanup = () => {
    if (disposed) {
      return;
    }
    disposed = true;
    observer?.disconnect?.();
    windowObject?.removeEventListener?.("resize", schedule);
    if (frameHandle !== undefined) {
      cancel(frameHandle);
    }
    delete header[MAIN_TRACK_CONTROL_LAYOUT_BOUND];
  };
  const schedule = () => {
    if (disposed || frameScheduled) {
      return;
    }
    if (header.isConnected === false) {
      cleanup();
      return;
    }
    frameScheduled = true;
    frameHandle = request(() => {
      frameScheduled = false;
      frameHandle = undefined;
      if (header.isConnected === false) {
        cleanup();
        return;
      }
      sync();
    });
  };

  sync();
  if (typeof ResizeObserverImpl === "function") {
    observer = new ResizeObserverImpl(schedule);
    const observedNodes = [
      header,
      header.querySelector?.("[data-main-track-control-title]"),
      header.querySelector?.("[data-main-track-quick-actions]"),
      header.querySelector?.("[data-main-track-inline-controls]"),
    ].filter(Boolean);
    observedNodes.forEach((node) => observer.observe?.(node));
  } else {
    windowObject?.addEventListener?.("resize", schedule);
  }
  header[MAIN_TRACK_CONTROL_LAYOUT_BOUND] = { cleanup, sync };
  return cleanup;
}

export function bindMainTrackControlLayout(host, options = {}) {
  const headers = host?.matches?.(MAIN_TRACK_CONTROL_LAYOUT_SELECTOR)
    ? [host]
    : Array.from(host?.querySelectorAll?.(MAIN_TRACK_CONTROL_LAYOUT_SELECTOR) || []);
  const cleanups = headers.map((header) => bindMainTrackControlHeader(header, options));
  return () => cleanups.forEach((cleanup) => cleanup?.());
}
