function roundViewportMetric(value) {
  return Math.round(Number(value || 0) * 100) / 100;
}

export function resolveActiveTrackScrollElement(host, trackRole, fallbackEl = null) {
  const normalizedRole = String(trackRole || "").trim();
  if (normalizedRole && host?.querySelector) {
    const liveNode = host.querySelector(
      `.assembly-track-scroll[data-track-role='${normalizedRole}']`,
    );
    if (liveNode) {
      return liveNode;
    }
  }
  return fallbackEl;
}

export function resolveTrackPointerContentPoint(event, scrollEl) {
  const rect = scrollEl.getBoundingClientRect();
  const viewBoxMinX = Number(
    scrollEl?.dataset?.trackViewboxMinX
    ?? scrollEl?.dataset?.subviewViewboxMinX
    ?? 0,
  );
  return {
    x: event.clientX - rect.left + scrollEl.scrollLeft + viewBoxMinX,
    y: event.clientY - rect.top + scrollEl.scrollTop,
  };
}

export function readTrackViewportMetrics(scrollEl, trackRole) {
  if (!scrollEl) {
    return null;
  }
  const normalizedRole = String(trackRole || "").trim();
  const dataset = scrollEl.dataset || {};
  const viewportWidth = Number(scrollEl.clientWidth || 0);
  if (normalizedRole === "subview") {
    const domainSpanBp = Number(dataset.subviewDomainSpanBp || 0);
    const innerWidth = Number(dataset.subviewInnerWidth || 0);
    const viewboxMinX = Number(dataset.subviewViewboxMinX || 0);
    if (
      !Number.isFinite(viewportWidth)
      || viewportWidth <= 0
      || !Number.isFinite(domainSpanBp)
      || domainSpanBp <= 0
      || !Number.isFinite(innerWidth)
      || innerWidth <= 0
    ) {
      return null;
    }
    return {
      viewportWidth,
      windowStartBp: 0,
      domainSpanBp,
      innerWidth,
      viewboxMinX: Number.isFinite(viewboxMinX) ? viewboxMinX : 0,
    };
  }
  const windowStartBp = Number(scrollEl.dataset?.trackWindowStartBp || 0);
  const domainSpanBp = Number(scrollEl.dataset?.trackDomainSpanBp || 0);
  const innerWidth = Number(scrollEl.dataset?.trackInnerWidth || 0);
  const viewboxMinX = Number(scrollEl.dataset?.trackViewboxMinX || 0);
  if (
    !Number.isFinite(viewportWidth)
    || viewportWidth <= 0
    || !Number.isFinite(domainSpanBp)
    || domainSpanBp <= 0
    || !Number.isFinite(innerWidth)
    || innerWidth <= 0
  ) {
    return null;
  }
  return {
    viewportWidth,
    windowStartBp: Number.isFinite(windowStartBp) ? windowStartBp : 0,
    domainSpanBp,
    innerWidth,
    viewboxMinX: Number.isFinite(viewboxMinX) ? viewboxMinX : 0,
  };
}

export function resolveViewportAnchorBp(scrollLeft, metrics) {
  const currentScrollLeft = Number(scrollLeft);
  const viewportWidth = Number(metrics?.viewportWidth);
  const windowStartBp = Number(metrics?.windowStartBp || 0);
  const domainSpanBp = Number(metrics?.domainSpanBp || 0);
  const innerWidth = Number(metrics?.innerWidth || 0);
  const viewboxMinX = Number(metrics?.viewboxMinX || 0);
  if (
    !Number.isFinite(currentScrollLeft)
    || !Number.isFinite(viewportWidth)
    || viewportWidth <= 0
    || !Number.isFinite(domainSpanBp)
    || domainSpanBp <= 0
    || !Number.isFinite(innerWidth)
    || innerWidth <= 0
  ) {
    return null;
  }
  const centerUserX =
    currentScrollLeft + viewportWidth / 2 + (Number.isFinite(viewboxMinX) ? viewboxMinX : 0);
  const clampedX = Math.min(innerWidth, Math.max(0, centerUserX));
  return roundViewportMetric(windowStartBp + (clampedX / innerWidth) * domainSpanBp);
}

export function resolveScrollLeftForViewportAnchorBp(anchorBp, metrics) {
  const centerBp = Number(anchorBp);
  const viewportWidth = Number(metrics?.viewportWidth);
  const windowStartBp = Number(metrics?.windowStartBp || 0);
  const domainSpanBp = Number(metrics?.domainSpanBp || 0);
  const innerWidth = Number(metrics?.innerWidth || 0);
  const viewboxMinX = Number(metrics?.viewboxMinX || 0);
  if (
    !Number.isFinite(centerBp)
    || !Number.isFinite(viewportWidth)
    || viewportWidth <= 0
    || !Number.isFinite(domainSpanBp)
    || domainSpanBp <= 0
    || !Number.isFinite(innerWidth)
    || innerWidth <= 0
  ) {
    return null;
  }
  const clampedBp = Math.min(windowStartBp + domainSpanBp, Math.max(windowStartBp, centerBp));
  const userX = ((clampedBp - windowStartBp) / domainSpanBp) * innerWidth;
  return Math.max(
    0,
    Math.round(userX - (Number.isFinite(viewboxMinX) ? viewboxMinX : 0) - viewportWidth / 2),
  );
}

export function resolveTrackScrollLeftForViewboxShift(
  scrollLeft,
  previousMinX,
  nextMinX,
  options = {},
) {
  const currentScrollLeft = Math.max(0, Number(scrollLeft) || 0);
  if (options?.preserveViewport === false) {
    return currentScrollLeft;
  }
  const prev = Number.isFinite(Number(previousMinX)) ? Number(previousMinX) : 0;
  const next = Number.isFinite(Number(nextMinX)) ? Number(nextMinX) : 0;
  const delta = prev - next;
  if (!Number.isFinite(delta) || Math.abs(delta) < 0.01) {
    return currentScrollLeft;
  }
  return Math.max(0, Math.round(currentScrollLeft + delta));
}

export function resolveScrollLeftForViewboxMinXShift(scrollLeft, previousMinX, nextMinX) {
  return resolveTrackScrollLeftForViewboxShift(scrollLeft, previousMinX, nextMinX);
}
