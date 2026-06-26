const FINAL_PATH_CARD_DRAG_BOUND = Symbol("finalPathCardDragBound");
const DRAG_START_DISTANCE_PX = 4;

function getWindowObject() {
  return globalThis.window;
}

function getDocumentObject() {
  return globalThis.document;
}

function assertFinalPathCardDragDeps(deps) {
  if (typeof deps?.moveFinalPathRow === "function") {
    return;
  }
  throw new TypeError("Missing final-path card drag runtime dep: moveFinalPathRow");
}

function clearRowMarkers(rows) {
  rows.forEach((rowNode) => {
    rowNode.classList?.remove("is-dragging");
    rowNode.classList?.remove("is-drop-before");
    rowNode.classList?.remove("is-drop-after");
  });
}

function updateGhostPosition(ghostNode, pointerOffset, clientX, clientY) {
  if (!ghostNode?.style) {
    return;
  }
  ghostNode.style.left = `${Math.round(clientX - pointerOffset.x)}px`;
  ghostNode.style.top = `${Math.round(clientY - pointerOffset.y)}px`;
}

function syncGhostFormValues(sourceNode, ghostNode) {
  const sourceFields = Array.from(sourceNode?.querySelectorAll?.("input, textarea, select") || []);
  const ghostFields = Array.from(ghostNode?.querySelectorAll?.("input, textarea, select") || []);
  if (!sourceFields.length || sourceFields.length !== ghostFields.length) {
    return;
  }
  sourceFields.forEach((sourceField, index) => {
    const ghostField = ghostFields[index];
    if (!ghostField) {
      return;
    }
    if ("value" in sourceField && "value" in ghostField) {
      ghostField.value = sourceField.value;
    }
    if ("checked" in sourceField && "checked" in ghostField) {
      ghostField.checked = sourceField.checked;
    }
    const tagName = String(sourceField?.tagName || ghostField?.tagName || "").toUpperCase();
    if (tagName !== "SELECT") {
      return;
    }
    if ("selectedIndex" in sourceField && "selectedIndex" in ghostField) {
      ghostField.selectedIndex = sourceField.selectedIndex;
    }
    const sourceOptions = Array.from(sourceField.options || []);
    const ghostOptions = Array.from(ghostField.options || []);
    sourceOptions.forEach((sourceOption, optionIndex) => {
      const ghostOption = ghostOptions[optionIndex];
      if (!ghostOption) {
        return;
      }
      ghostOption.selected = sourceOption.selected;
    });
  });
}

function applyGhostLayoutContext(sourceNode, ghostNode) {
  const style = ghostNode?.style;
  if (!style) {
    return;
  }
  const tableBodyNode = sourceNode?.closest?.(".final-path-card-table-body") || null;
  const readComputedStyle = typeof globalThis.getComputedStyle === "function"
    ? globalThis.getComputedStyle.bind(globalThis)
    : null;
  const tableColumns = String(
    readComputedStyle?.(tableBodyNode)?.getPropertyValue?.("--final-path-table-columns") || "",
  ).trim();
  if (!tableColumns) {
    return;
  }
  if (typeof style.setProperty === "function") {
    style.setProperty("--final-path-table-columns", tableColumns);
    return;
  }
  style["--final-path-table-columns"] = tableColumns;
}

function createDragGhost(cardNode, rect) {
  const ghostNode = cardNode?.cloneNode?.(true);
  if (!ghostNode) {
    return null;
  }
  syncGhostFormValues(cardNode, ghostNode);
  applyGhostLayoutContext(cardNode, ghostNode);
  ghostNode.classList?.add("is-drag-ghost");
  if (ghostNode.style) {
    ghostNode.style.position = "fixed";
    ghostNode.style.width = `${Math.round(rect.width)}px`;
    ghostNode.style.left = `${Math.round(rect.left)}px`;
    ghostNode.style.top = `${Math.round(rect.top)}px`;
    ghostNode.style.pointerEvents = "none";
    ghostNode.style.zIndex = "9999";
  }
  return ghostNode;
}

function resolveRowCardRect(rowNode) {
  const cardNode = rowNode?.querySelector?.("[data-final-path-card-body]");
  const rect = cardNode?.getBoundingClientRect?.();
  if (!rect || !Number.isFinite(rect.top) || !Number.isFinite(rect.bottom)) {
    return null;
  }
  return {
    rowNode,
    top: rect.top,
    bottom: rect.bottom,
  };
}

function resolveNearestDropTarget(rows, sourceRowNode, draggedTop, draggedBottom) {
  let bestTarget = null;
  const candidateRects = [];
  rows.forEach((rowNode) => {
    if (!rowNode || rowNode === sourceRowNode) {
      return;
    }
    const rect = resolveRowCardRect(rowNode);
    if (!rect) {
      return;
    }
    candidateRects.push(rect);

    const crossedAfterDistance = draggedTop - rect.bottom;
    if (crossedAfterDistance >= 0) {
      if (!bestTarget || crossedAfterDistance < bestTarget.distance) {
        bestTarget = {
          rowNode,
          placement: "after",
          distance: crossedAfterDistance,
        };
      }
    }

    const crossedBeforeDistance = draggedBottom - rect.top;
    if (crossedBeforeDistance >= 0) {
      if (!bestTarget || crossedBeforeDistance < bestTarget.distance) {
        bestTarget = {
          rowNode,
          placement: "before",
          distance: crossedBeforeDistance,
        };
      }
    }
  });
  if (bestTarget || candidateRects.length === 0) {
    return bestTarget;
  }

  const firstRect = candidateRects[0];
  if (draggedBottom <= firstRect.top) {
    return {
      rowNode: firstRect.rowNode,
      placement: "before",
      distance: firstRect.top - draggedBottom,
    };
  }

  const lastRect = candidateRects[candidateRects.length - 1];
  if (draggedTop >= lastRect.bottom) {
    return {
      rowNode: lastRect.rowNode,
      placement: "after",
      distance: draggedTop - lastRect.bottom,
    };
  }

  return bestTarget;
}

export function bindFinalPathCardDrag(host, store, deps) {
  assertFinalPathCardDragDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host[FINAL_PATH_CARD_DRAG_BOUND]) {
    return;
  }

  host.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey) {
      return;
    }
    const state = store.getState();
    if (state?.assembly?.activeTab !== "assembly") {
      return;
    }
    const handleNode = event.target?.closest?.("[data-final-path-row-drag-id]");
    if (!handleNode) {
      return;
    }
    const sourceSegmentId = String(handleNode.dataset.finalPathRowDragId || "").trim();
    const targetChrName = String(handleNode.dataset.finalPathTargetChrName || handleNode.closest?.("[data-final-path-target-chr-name]")?.dataset?.finalPathTargetChrName || "").trim();
    const sourceRowNode = handleNode.closest?.("[data-final-path-row-id]") || null;
    const sourceCardNode = sourceRowNode?.querySelector?.("[data-final-path-card-body]") || null;
    const listNode = sourceRowNode?.closest?.("[data-final-path-card-list]") || null;
    if (!sourceSegmentId || !sourceRowNode || !sourceCardNode || !listNode) {
      return;
    }

    event.preventDefault();
    const windowObject = getWindowObject();
    const startClientX = Number(event.clientX || 0);
    const startClientY = Number(event.clientY || 0);
    const rows = Array.from(listNode.querySelectorAll?.("[data-final-path-row-id]") || []);
    const sourceRect = sourceCardNode.getBoundingClientRect?.();
    const pointerOffset = {
      x: sourceRect && Number.isFinite(startClientX) ? Math.max(10, startClientX - sourceRect.left) : 24,
      y: sourceRect && Number.isFinite(startClientY) ? Math.max(10, startClientY - sourceRect.top) : 18,
    };
    let ghostNode = null;
    let dragging = false;
    let targetSegmentId = "";
    let placement = "before";

    const cleanup = () => {
      clearRowMarkers(rows);
      ghostNode?.remove?.();
      ghostNode = null;
    };

    const onPointerMove = (moveEvent) => {
      const deltaX = Number(moveEvent.clientX || 0) - startClientX;
      const deltaY = Number(moveEvent.clientY || 0) - startClientY;
      if (!dragging && Math.hypot(deltaX, deltaY) < DRAG_START_DISTANCE_PX) {
        return;
      }
      if (!dragging) {
        dragging = true;
        clearRowMarkers(rows);
        sourceRowNode.classList?.add("is-dragging");
        if (sourceRect) {
          ghostNode = createDragGhost(sourceCardNode, sourceRect);
          if (ghostNode) {
            getDocumentObject()?.body?.appendChild?.(ghostNode);
          }
        }
      }
      const currentClientX = Number(moveEvent.clientX || 0);
      const currentClientY = Number(moveEvent.clientY || 0);
      updateGhostPosition(ghostNode, pointerOffset, currentClientX, currentClientY);
      const draggedTop = currentClientY - pointerOffset.y;
      const draggedBottom = draggedTop + Number(sourceRect?.height || 0);
      const target = resolveNearestDropTarget(rows, sourceRowNode, draggedTop, draggedBottom);
      clearRowMarkers(rows);
      sourceRowNode.classList?.add("is-dragging");
      targetSegmentId = "";
      placement = "before";
      if (!target?.rowNode) {
        return;
      }
      targetSegmentId = String(target.rowNode.dataset.finalPathRowId || "").trim();
      placement = target.placement;
      target.rowNode.classList?.add(placement === "after" ? "is-drop-after" : "is-drop-before");
    };

    const onPointerUp = () => {
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      try {
        if (!dragging || !targetSegmentId || targetSegmentId === sourceSegmentId) {
          return;
        }
        void deps.moveFinalPathRow(host, store, {
          sourceSegmentId,
          targetSegmentId,
          placement,
          ...(targetChrName ? { targetChrName } : {}),
        });
      } finally {
        cleanup();
      }
    };

    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
  });

  host[FINAL_PATH_CARD_DRAG_BOUND] = true;
}
