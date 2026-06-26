const ASSEMBLY_STICKY_CTG_LABEL_BOUND = Symbol("assemblyStickyCtgLabelBound");

function buildNoStickyDecision() {
  return {
    showSticky: false,
    hideOriginal: false,
    stickyLeft: null,
    visibleLeft: null,
    visibleRight: null,
    visibleWidth: 0,
  };
}

function estimateTrackCtgLabelWidth(labelText) {
  const text = String(labelText || "");
  return Math.max(10, text.length * 6.2);
}

function readNodeClassName(node) {
  return String(node?.getAttribute?.("class") || "");
}

function readNodeText(node) {
  return String(node?.textContent || "");
}

function readTrimmedAttribute(node, name) {
  return String(node?.getAttribute?.(name) || "").trim();
}

function resolveRuntimeDocument(options = {}) {
  return options.document || globalThis.document || null;
}

function readScrollViewboxMinX(scrollEl) {
  const dataset = scrollEl?.dataset || {};
  const value = dataset.trackViewboxMinX ?? dataset.subviewViewboxMinX ?? 0;
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function resolveScrollViewport(scrollEl) {
  const viewportWidth = Number(scrollEl?.clientWidth || 0);
  const viewboxMinX = readScrollViewboxMinX(scrollEl);
  const viewportLeft = Number(scrollEl?.scrollLeft || 0) + viewboxMinX;
  return {
    viewportWidth,
    viewportLeft,
    viewportRight: viewportLeft + viewportWidth,
  };
}

function ensureStickyLabelLayer(scrollEl, options = {}) {
  const existingLayer = scrollEl?.querySelector?.(".track-sticky-label-layer");
  if (existingLayer) {
    return existingLayer;
  }
  const documentRef = resolveRuntimeDocument(options);
  if (!documentRef?.createElement) {
    return null;
  }
  const layer = documentRef.createElement("div");
  layer.setAttribute("class", "track-sticky-label-layer");
  layer.setAttribute("aria-hidden", "true");
  scrollEl?.appendChild?.(layer);
  return layer;
}

function updateStickyLabelLayerLayout(layer, scrollEl) {
  if (!layer || !scrollEl) {
    return;
  }
  const scrollLeft = Math.max(0, Number(scrollEl.scrollLeft || 0));
  const viewportWidth = Math.max(0, Number(scrollEl.clientWidth || 0));
  layer.style.left = `${scrollLeft}px`;
  layer.style.width = `${viewportWidth}px`;
}

function buildStickyLabelClassName(originalLabelNode, groupNode) {
  const originalClasses = readNodeClassName(originalLabelNode)
    .split(/\s+/)
    .filter(Boolean)
    .filter((className) => className !== "is-outside" && !className.startsWith("is-tilt-") && className !== "is-sticky-hidden");
  const nextClasses = new Set(["track-sticky-label", ...originalClasses]);
  if (readNodeClassName(groupNode).split(/\s+/).includes("is-active")) {
    nextClasses.add("is-active");
  }
  return Array.from(nextClasses).join(" ");
}

function buildMainTrackTarget(groupNode, scrollEl) {
  const contigId = readTrimmedAttribute(groupNode, "data-track-contig-id");
  const role = readTrimmedAttribute(groupNode, "data-track-role");
  if (!contigId || !role) {
    return null;
  }
  const mirrorFlag = readTrimmedAttribute(groupNode, "data-track-is-mirror") || "0";
  const phasedTrackId = role === "phased" ? readTrimmedAttribute(groupNode, "data-track-phased-track-id") : "";
  const phasedTrackItemId = role === "phased" ? readTrimmedAttribute(groupNode, "data-track-phased-track-item-id") : "";
  const phasedLabelSelector = phasedTrackItemId
    ? `[data-track-label-phased-track-item-id="${phasedTrackItemId}"]`
    : phasedTrackId
      ? `[data-track-label-phased-track-id="${phasedTrackId}"]`
      : "";
  const originalLabelNode = scrollEl?.querySelector?.(
    `[data-track-label-for-contig-id="${contigId}"][data-track-label-role="${role}"][data-track-label-is-mirror="${mirrorFlag}"]${phasedLabelSelector}`,
  );
  const phasedKeySuffix = role === "phased"
    ? phasedTrackItemId
      ? `:item:${phasedTrackItemId}`
      : phasedTrackId
        ? `:track:${phasedTrackId}`
        : ""
    : "";
  return {
    key: `track:${role}:${contigId}:${mirrorFlag}${phasedKeySuffix}`,
    rectX: Number(groupNode?.getAttribute?.("data-track-rect-x")),
    rectY: Number(groupNode?.getAttribute?.("data-track-rect-y")),
    rectWidth: Number(groupNode?.getAttribute?.("data-track-rect-width")),
    rectHeight: Number(groupNode?.getAttribute?.("data-track-rect-height")),
    labelText: readNodeText(originalLabelNode) || String(groupNode?.getAttribute?.("data-track-contig-name") || ""),
    originalLabelNode,
    groupNode,
  };
}

function buildSubviewTrackTarget(groupNode, scrollEl) {
  const slot = String(groupNode?.getAttribute?.("data-subview-track-slot") || "").trim();
  const role = String(groupNode?.getAttribute?.("data-subview-track-role") || "").trim();
  const contigId = String(groupNode?.getAttribute?.("data-subview-contig-id") || "").trim();
  if (!slot || !role || !contigId) {
    return null;
  }
  const originalLabelNode = scrollEl?.querySelector?.(
    `[data-subview-label-slot="${slot}"][data-subview-label-role="${role}"][data-subview-label-contig-id="${contigId}"]`,
  );
  return {
    key: `subview:${slot}:${role}:${contigId}`,
    rectX: Number(groupNode?.getAttribute?.("data-subview-rect-x")),
    rectY: Number(groupNode?.getAttribute?.("data-subview-rect-y")),
    rectWidth: Number(groupNode?.getAttribute?.("data-subview-rect-width")),
    rectHeight: Number(groupNode?.getAttribute?.("data-subview-rect-height")),
    labelText: readNodeText(originalLabelNode) || String(groupNode?.getAttribute?.("data-subview-contig-id") || ""),
    originalLabelNode,
    groupNode,
  };
}

function collectStickyTargets(scrollEl) {
  const trackRole = String(scrollEl?.dataset?.trackRole || "").trim();
  if (trackRole === "subview") {
    return Array.from(
      scrollEl?.querySelectorAll?.("[data-subview-contig-id][data-subview-track-role]") || [],
    )
      .map((groupNode) => buildSubviewTrackTarget(groupNode, scrollEl))
      .filter(Boolean);
  }
  return Array.from(
    scrollEl?.querySelectorAll?.("[data-track-contig-id][data-track-role]") || [],
  )
    .map((groupNode) => buildMainTrackTarget(groupNode, scrollEl))
    .filter(Boolean);
}

function setOriginalLabelHidden(labelNode, hidden) {
  labelNode?.classList?.toggle?.("is-sticky-hidden", Boolean(hidden));
}

function updateStickyLabelNode(labelNode, target, decision, viewportLeft) {
  const overlayLeft = Math.max(0, Number(decision.stickyLeft || 0) - Number(viewportLeft || 0));
  const rectY = Math.max(0, Number(target.rectY || 0));
  const rectHeight = Math.max(0, Number(target.rectHeight || 0));
  labelNode.textContent = target.labelText;
  labelNode.setAttribute("class", buildStickyLabelClassName(target.originalLabelNode, target.groupNode));
  labelNode.setAttribute("data-sticky-label-key", target.key);
  labelNode.style.left = `${overlayLeft}px`;
  labelNode.style.top = `${rectY}px`;
  labelNode.style.height = `${rectHeight}px`;
  labelNode.style.lineHeight = `${rectHeight}px`;
  labelNode.style.maxWidth = `${Math.max(0, Number(decision.visibleWidth || 0))}px`;
}

export function syncStickyCtgLabels(scrollEl, options = {}) {
  const layer = ensureStickyLabelLayer(scrollEl, options);
  if (!layer) {
    return;
  }
  updateStickyLabelLayerLayout(layer, scrollEl);
  const viewport = resolveScrollViewport(scrollEl);
  const targets = collectStickyTargets(scrollEl);
  const documentRef = resolveRuntimeDocument(options);
  const activeStickyKeys = new Set();
  const stickyNodesByKey = new Map(
    Array.from(layer.querySelectorAll?.(".track-sticky-label") || []).map((node) => [
      String(node?.getAttribute?.("data-sticky-label-key") || ""),
      node,
    ]),
  );

  targets.forEach((target) => {
    const decision = resolveStickyLabelDisplay({
      rectX: target.rectX,
      rectWidth: target.rectWidth,
      viewportLeft: viewport.viewportLeft,
      viewportRight: viewport.viewportRight,
      labelWidth: estimateTrackCtgLabelWidth(target.labelText),
    });

    setOriginalLabelHidden(target.originalLabelNode, decision.hideOriginal);
    if (!decision.showSticky) {
      return;
    }

    let stickyLabelNode = stickyNodesByKey.get(target.key) || null;
    if (!stickyLabelNode) {
      stickyLabelNode = documentRef?.createElement?.("div") || null;
      if (!stickyLabelNode) {
        return;
      }
      layer.appendChild(stickyLabelNode);
      stickyNodesByKey.set(target.key, stickyLabelNode);
    }

    updateStickyLabelNode(stickyLabelNode, target, decision, viewport.viewportLeft);
    activeStickyKeys.add(target.key);
  });

  stickyNodesByKey.forEach((node, key) => {
    if (activeStickyKeys.has(key)) {
      return;
    }
    node?.remove?.();
  });
}

export function bindStickyCtgLabels(host, options = {}) {
  const scrollNodes = Array.from(
    host?.querySelectorAll?.(".assembly-track-scroll[data-track-role]") || [],
  );
  scrollNodes.forEach((scrollNode) => {
    if (!scrollNode) {
      return;
    }
    if (!scrollNode[ASSEMBLY_STICKY_CTG_LABEL_BOUND]) {
      const onScroll = () => {
        syncStickyCtgLabels(scrollNode, options);
      };
      scrollNode.addEventListener?.("scroll", onScroll);
      scrollNode[ASSEMBLY_STICKY_CTG_LABEL_BOUND] = {
        onScroll,
      };
    }
    syncStickyCtgLabels(scrollNode, options);
  });
}

export function resolveStickyLabelDisplay({
  rectX,
  rectWidth,
  viewportLeft,
  viewportRight,
  labelWidth,
}) {
  const barLeft = Number(rectX);
  const width = Number(rectWidth);
  const viewLeft = Number(viewportLeft);
  const viewRight = Number(viewportRight);
  const textWidth = Number(labelWidth);

  if (
    !Number.isFinite(barLeft)
    || !Number.isFinite(width)
    || width <= 0
    || !Number.isFinite(viewLeft)
    || !Number.isFinite(viewRight)
    || viewRight <= viewLeft
  ) {
    return buildNoStickyDecision();
  }

  const barRight = barLeft + width;
  const visibleLeft = Math.max(barLeft, viewLeft);
  const visibleRight = Math.min(barRight, viewRight);
  const visibleWidth = Math.max(0, visibleRight - visibleLeft);

  if (visibleWidth <= 0) {
    return buildNoStickyDecision();
  }

  const leftClipped = barLeft < viewLeft;
  if (!leftClipped) {
    return {
      showSticky: false,
      hideOriginal: false,
      stickyLeft: null,
      visibleLeft,
      visibleRight,
      visibleWidth,
    };
  }

  if (!Number.isFinite(textWidth) || textWidth <= 0 || textWidth > visibleWidth) {
    return {
      showSticky: false,
      hideOriginal: true,
      stickyLeft: null,
      visibleLeft,
      visibleRight,
      visibleWidth,
    };
  }

  return {
    showSticky: true,
    hideOriginal: true,
    stickyLeft: visibleLeft,
    visibleLeft,
    visibleRight,
    visibleWidth,
  };
}
