import { resolveCurrentFinalPathChrName } from "./final-path-state.js";

const FINAL_PATH_GRAPH_DRAG_BOUND = Symbol("finalPathGraphDragBound");
const GRAPH_DRAG_START_DISTANCE_PX = 4;
let finalPathGraphPreviewState = null;

function normalizeSegmentId(value) {
  return String(value || "").trim();
}

function normalizeSegmentIdList(values) {
  return Array.isArray(values)
    ? values.map((value) => normalizeSegmentId(value)).filter((value) => value)
    : [];
}

function normalizeSlotRects(slotRects) {
  const entries = Object.entries(slotRects && typeof slotRects === "object" ? slotRects : {});
  return Object.fromEntries(entries.map(([segmentId, rect]) => {
    const left = Number(rect?.left);
    const right = Number(rect?.right);
    const fallbackMid = left + ((right - left) / 2);
    const mid = Number.isFinite(Number(rect?.mid)) ? Number(rect.mid) : fallbackMid;
    return [normalizeSegmentId(segmentId), { left, right, mid }];
  }));
}

function getWindowObject() {
  return globalThis.window;
}

function assertFinalPathGraphDragDeps(deps) {
  if (typeof deps?.moveFinalPathRow !== "function" || typeof deps?.rerender !== "function") {
    throw new TypeError("Missing final-path graph drag runtime deps: moveFinalPathRow, rerender");
  }
}

function setFinalPathGraphPreviewState(nextState) {
  finalPathGraphPreviewState = nextState && typeof nextState === "object"
    ? {
        selectedChrName: normalizeSegmentId(nextState.selectedChrName),
        previewSegmentOrder: normalizeSegmentIdList(nextState.previewSegmentOrder),
      }
    : null;
}

export function getFinalPathGraphPreviewState() {
  return finalPathGraphPreviewState;
}

function clearFinalPathGraphPreviewState() {
  finalPathGraphPreviewState = null;
}

function buildPointerLocalX(scrollWrapNode, clientX) {
  const wrapRect = scrollWrapNode?.getBoundingClientRect?.();
  return Number(clientX || 0) - Number(wrapRect?.left || 0) + Number(scrollWrapNode?.scrollLeft || 0);
}

function collectGraphLayoutContext(root) {
  const scrollWrapNode = root?.querySelector?.(".assembly-final-path-svg-wrap") || null;
  const segmentNodes = Array.from(
    root?.querySelectorAll?.("[data-final-path-segment-id][data-final-path-slot-left]") || [],
  );
  const segmentIds = [];
  const slotRects = {};
  const nodesById = new Map();
  segmentNodes.forEach((node) => {
    const segmentId = normalizeSegmentId(node?.dataset?.finalPathSegmentId);
    if (!segmentId) {
      return;
    }
    segmentIds.push(segmentId);
    nodesById.set(segmentId, node);
    slotRects[segmentId] = {
      left: Number(node?.dataset?.finalPathSlotLeft),
      right: Number(node?.dataset?.finalPathSlotRight),
      mid: Number(node?.dataset?.finalPathSlotMid),
    };
  });
  return {
    scrollWrapNode,
    segmentIds,
    slotRects: normalizeSlotRects(slotRects),
    nodesById,
  };
}

function resolveSegmentTargetChrName(segmentNode) {
  return normalizeSegmentId(
    segmentNode?.dataset?.finalPathTargetChrName
    || segmentNode?.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName,
  );
}

function resolveCurrentGraphRoot(host, targetChrName) {
  const normalizedTargetChrName = normalizeSegmentId(targetChrName);
  if (normalizedTargetChrName) {
    const allCard = Array.from(host?.querySelectorAll?.("[data-final-path-all-card]") || [])
      .find((node) => normalizeSegmentId(node?.dataset?.finalPathAllCard) === normalizedTargetChrName);
    if (allCard) {
      return allCard;
    }
  }
  return host?.querySelector?.(".final-path-card") || host;
}

function applyDragTransform(node, offsetPx) {
  if (!node?.setAttribute || !node?.removeAttribute) {
    return;
  }
  const normalizedOffset = Number(offsetPx || 0);
  if (!Number.isFinite(normalizedOffset) || Math.abs(normalizedOffset) < 0.01) {
    node.removeAttribute("transform");
    return;
  }
  node.setAttribute("transform", `translate(${normalizedOffset.toFixed(2)} 0)`);
}

function applyGraphDragPreviewMove({ previewSegmentIds, sourceSegmentId, dragLeft, dragRight, slotRects }) {
  const normalizedPreviewIds = normalizeSegmentIdList(previewSegmentIds);
  const normalizedSourceId = normalizeSegmentId(sourceSegmentId);
  const normalizedRects = normalizeSlotRects(slotRects);
  const sourceIndex = normalizedPreviewIds.indexOf(normalizedSourceId);
  if (sourceIndex < 0) {
    return { previewSegmentIds: normalizedPreviewIds, swapped: false, direction: "" };
  }
  const nextPreviewIds = [...normalizedPreviewIds];
  const leftNeighborId = nextPreviewIds[sourceIndex - 1] || "";
  const rightNeighborId = nextPreviewIds[sourceIndex + 1] || "";
  const draggedLeft = Number(dragLeft);
  const draggedRight = Number(dragRight);
  if (leftNeighborId && Number.isFinite(draggedLeft) && draggedLeft < Number(normalizedRects[leftNeighborId]?.mid)) {
    nextPreviewIds.splice(sourceIndex - 1, 2, normalizedSourceId, leftNeighborId);
    return {
      previewSegmentIds: nextPreviewIds,
      swapped: true,
      direction: "left",
    };
  }
  if (rightNeighborId && Number.isFinite(draggedRight) && draggedRight > Number(normalizedRects[rightNeighborId]?.mid)) {
    nextPreviewIds.splice(sourceIndex, 2, rightNeighborId, normalizedSourceId);
    return {
      previewSegmentIds: nextPreviewIds,
      swapped: true,
      direction: "right",
    };
  }
  return {
    previewSegmentIds: nextPreviewIds,
    swapped: false,
    direction: "",
  };
}

function resolveGraphDragCommitMove({ originalSegmentIds, previewSegmentIds, sourceSegmentId }) {
  const normalizedOriginalIds = normalizeSegmentIdList(originalSegmentIds);
  const normalizedPreviewIds = normalizeSegmentIdList(previewSegmentIds);
  const normalizedSourceId = normalizeSegmentId(sourceSegmentId);
  const originalIndex = normalizedOriginalIds.indexOf(normalizedSourceId);
  const finalIndex = normalizedPreviewIds.indexOf(normalizedSourceId);
  if (originalIndex < 0 || finalIndex < 0 || originalIndex === finalIndex) {
    return null;
  }
  if (finalIndex < originalIndex) {
    const targetSegmentId = normalizedPreviewIds[finalIndex + 1] || "";
    return targetSegmentId
      ? { sourceSegmentId: normalizedSourceId, targetSegmentId, placement: "before" }
      : null;
  }
  const targetSegmentId = normalizedPreviewIds[finalIndex - 1] || "";
  return targetSegmentId
    ? { sourceSegmentId: normalizedSourceId, targetSegmentId, placement: "after" }
    : null;
}

export function __testApplyGraphDragPreviewMove(args) {
  return applyGraphDragPreviewMove(args);
}

export function __testResolveGraphDragCommitMove(args) {
  return resolveGraphDragCommitMove(args);
}

export function __testGetFinalPathGraphPreviewState() {
  return finalPathGraphPreviewState;
}

export function bindFinalPathGraphDrag(host, store, deps = {}) {
  assertFinalPathGraphDragDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host?.[FINAL_PATH_GRAPH_DRAG_BOUND]) {
    return;
  }
  host.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) {
      return;
    }
    const state = store.getState();
    if (state?.assembly?.activeTab !== "assembly" || String(state?.assembly?.finalPathViewMode || "").trim() !== "graph") {
      return;
    }
    const segmentNode = event.target?.closest?.("[data-final-path-segment-id][data-final-path-slot-left]") || null;
    const sourceSegmentId = normalizeSegmentId(segmentNode?.dataset?.finalPathSegmentId);
    if (!segmentNode || !sourceSegmentId) {
      return;
    }
    const targetChrName = resolveSegmentTargetChrName(segmentNode);
    const resolveDragGraphRoot = () => resolveCurrentGraphRoot(host, targetChrName);
    const initialLayout = collectGraphLayoutContext(resolveDragGraphRoot());
    const sourceRect = initialLayout.slotRects[sourceSegmentId];
    if (!initialLayout.scrollWrapNode || !sourceRect) {
      return;
    }
    event.preventDefault();
    const windowObject = getWindowObject();
    const startClientX = Number(event.clientX || 0);
    const startClientY = Number(event.clientY || 0);
    const pointerOffsetWithinSegment = buildPointerLocalX(initialLayout.scrollWrapNode, startClientX) - sourceRect.left;
    let dragging = false;
    let previewSegmentIds = [...initialLayout.segmentIds];

    const cleanup = () => {
      clearFinalPathGraphPreviewState();
      deps.rerender(host, store);
    };

    const onPointerMove = (moveEvent) => {
      const deltaX = Number(moveEvent.clientX || 0) - startClientX;
      const deltaY = Number(moveEvent.clientY || 0) - startClientY;
      if (!dragging && Math.hypot(deltaX, deltaY) < GRAPH_DRAG_START_DISTANCE_PX) {
        return;
      }
      dragging = true;
      const currentLayout = collectGraphLayoutContext(resolveDragGraphRoot());
      const currentSourceRect = currentLayout.slotRects[sourceSegmentId];
      if (!currentLayout.scrollWrapNode || !currentSourceRect) {
        return;
      }
      const pointerLocalX = buildPointerLocalX(currentLayout.scrollWrapNode, Number(moveEvent.clientX || 0));
      const dragLeft = pointerLocalX - pointerOffsetWithinSegment;
      const dragRight = dragLeft + (currentSourceRect.right - currentSourceRect.left);
      const swapResult = applyGraphDragPreviewMove({
        previewSegmentIds,
        sourceSegmentId,
        dragLeft,
        dragRight,
        slotRects: currentLayout.slotRects,
      });
      if (swapResult.swapped) {
        previewSegmentIds = [...swapResult.previewSegmentIds];
        setFinalPathGraphPreviewState({
          selectedChrName: targetChrName || resolveCurrentFinalPathChrName(state?.assembly),
          previewSegmentOrder: previewSegmentIds,
        });
        deps.rerender(host, store);
      }
      const latestLayout = collectGraphLayoutContext(resolveDragGraphRoot());
      const latestSourceRect = latestLayout.slotRects[sourceSegmentId];
      const latestNode = latestLayout.nodesById.get(sourceSegmentId);
      if (!latestSourceRect || !latestNode) {
        return;
      }
      applyDragTransform(latestNode, dragLeft - latestSourceRect.left);
    };

    const onPointerUp = async () => {
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      try {
        if (!dragging) {
          return;
        }
        const payload = resolveGraphDragCommitMove({
          originalSegmentIds: initialLayout.segmentIds,
          previewSegmentIds,
          sourceSegmentId,
        });
        if (payload) {
          setFinalPathGraphPreviewState({
            selectedChrName: targetChrName || resolveCurrentFinalPathChrName(state?.assembly),
            previewSegmentOrder: previewSegmentIds,
          });
          await deps.moveFinalPathRow(host, store, {
            ...payload,
            ...(targetChrName ? { targetChrName } : {}),
          });
        }
      } finally {
        cleanup();
      }
    };

    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
  });
  host[FINAL_PATH_GRAPH_DRAG_BOUND] = true;
}
