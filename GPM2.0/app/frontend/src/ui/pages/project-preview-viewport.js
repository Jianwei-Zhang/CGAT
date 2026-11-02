// DOM virtualization only. All cards and scientific metadata remain in the
// model; light, focusable card shells keep the same track/scroll geometry.
export function projectPreviewViewportBounds(host) {
  const win = host.ownerDocument?.defaultView;
  let top = win?.visualViewport?.offsetTop || 0;
  let bottom = top + (win?.visualViewport?.height || win?.innerHeight || 0);
  for (let parent = host; parent; parent = parent.parentElement) {
    const style = win?.getComputedStyle?.(parent);
    if (!/(auto|scroll|hidden|clip)/.test(style?.overflowY || "")) continue;
    const rect = parent.getBoundingClientRect();
    const start = rect.top + (parent.clientTop || 0);
    top = Math.max(top, start);
    bottom = Math.min(bottom, start + parent.clientHeight);
  }
  return { top, bottom };
}

export function createProjectPreviewViewport(host, callbacks) {
  const doc = host.ownerDocument, win = doc?.defaultView;
  let running = false, frame = null, dirty = true;
  const observed = new Set();
  const request = callback => win?.requestAnimationFrame ? win.requestAnimationFrame(callback) : setTimeout(callback, 0);
  const cancel = id => win?.cancelAnimationFrame ? win.cancelAnimationFrame(id) : clearTimeout(id);
  const flush = () => {
    frame = null;
    if (!running || !callbacks.active()) return;
    const bounds = projectPreviewViewportBounds(host);
    // At most half a viewport (capped at 300px) above and below. No heavy
    // detached-card cache: leaving the window releases source/segment nodes.
    const buffer = Math.min(300, Math.max(0, bounds.bottom - bounds.top) / 2);
    const nodes = [...(host.querySelectorAll?.("[data-preview-chr]") || [])];
    // Summary expansion/collapse can move cards without resizing the Preview
    // itself or emitting scroll. Intersection notifications cover that case.
    const current = new Set(nodes);
    for (const node of observed) if (!current.has(node)) { intersection?.unobserve(node); observed.delete(node); }
    for (const node of nodes) if (!observed.has(node)) { intersection?.observe(node); observed.add(node); }
    const decisions = nodes.map(node => {
      const rect = node.getBoundingClientRect?.();
      const focused = doc?.activeElement && node.contains?.(doc.activeElement);
      return { node, mounted: node.dataset.previewMounted !== "false",
        wanted: Boolean(focused || (rect && bounds.bottom > bounds.top
          && rect.bottom >= bounds.top - buffer && rect.top <= bounds.bottom + buffer)) };
    });
    const measure = [];
    // All geometry reads above finish before mutating any card.
    for (const { node, mounted, wanted } of decisions) {
      if (wanted && !mounted) callbacks.mount(node);
      if (!wanted && mounted) callbacks.unmount(node);
      if (wanted && (!mounted || dirty)) measure.push(node);
    }
    dirty = false;
    if (measure.length) callbacks.geometry(measure);
  };
  const schedule = () => {
    if (running && frame === null) frame = request(flush);
  };
  const refresh = () => { dirty = true; schedule(); };
  const resize = win?.ResizeObserver ? new win.ResizeObserver(refresh) : null;
  const intersection = win?.IntersectionObserver ? new win.IntersectionObserver(schedule) : null;
  return {
    refresh,
    start() {
      if (running) return;
      running = true;
      // Capture handles nested scroll containers without assuming a shell ID.
      doc?.addEventListener?.("scroll", schedule, true);
      host.addEventListener?.("focusin", schedule);
      host.addEventListener?.("focusout", schedule);
      win?.addEventListener?.("resize", refresh);
      win?.visualViewport?.addEventListener?.("resize", refresh);
      win?.visualViewport?.addEventListener?.("scroll", schedule);
      resize?.observe(host);
      refresh();
    },
    stop() {
      running = false;
      if (frame !== null) cancel(frame);
      frame = null;
      resize?.disconnect();
      intersection?.disconnect(); observed.clear();
      doc?.removeEventListener?.("scroll", schedule, true);
      host.removeEventListener?.("focusin", schedule);
      host.removeEventListener?.("focusout", schedule);
      win?.removeEventListener?.("resize", refresh);
      win?.visualViewport?.removeEventListener?.("resize", refresh);
      win?.visualViewport?.removeEventListener?.("scroll", schedule);
    },
  };
}
