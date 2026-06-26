import {
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
  normalizeTrackSelectionCtgIds,
} from "./selection-state.js";

const ASSEMBLY_MEMBER_CHIP_BOX_SELECT_BOUND = Symbol("assemblyMemberChipBoxSelectBound");
const REQUIRED_MEMBER_CHIP_SELECTION_DEPS = [
  "updateDeletedCtgSelection",
  "updateTrackSelection",
];

function assertMemberChipSelectionDeps(deps) {
  const missing = REQUIRED_MEMBER_CHIP_SELECTION_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing member chip selection runtime deps: ${missing.join(", ")}`);
}

function getWindowObject() {
  return globalThis.window;
}

function getDocumentObject() {
  return globalThis.document;
}

function hasSelectionDragMoved(start, current) {
  return Math.abs(Number(current.x) - Number(start.x)) >= 4 || Math.abs(Number(current.y) - Number(start.y)) >= 4;
}

function normalizeSelectionRect(start, end) {
  return {
    left: Math.min(start.x, end.x),
    right: Math.max(start.x, end.x),
    top: Math.min(start.y, end.y),
    bottom: Math.max(start.y, end.y),
  };
}

function isRectOverlap(leftRect, rightRect) {
  return !(
    leftRect.right < rightRect.left ||
    leftRect.left > rightRect.right ||
    leftRect.bottom < rightRect.top ||
    leftRect.top > rightRect.bottom
  );
}

function ensureMemberChipSelectionBox(regionEl) {
  let boxEl = regionEl.querySelector(".member-chip-selection-box");
  if (boxEl) {
    return boxEl;
  }
  boxEl = getDocumentObject().createElement("div");
  boxEl.className = "member-chip-selection-box is-hidden";
  regionEl.appendChild(boxEl);
  return boxEl;
}

function resolveMemberChipPointerContentPoint(event, regionEl) {
  const rect = regionEl.getBoundingClientRect();
  return {
    x: event.clientX - rect.left + regionEl.scrollLeft,
    y: event.clientY - rect.top + regionEl.scrollTop,
  };
}

function resolveMemberChipNodeRect(node) {
  const x = Number(node?.offsetLeft);
  const y = Number(node?.offsetTop);
  const width = Number(node?.offsetWidth);
  const height = Number(node?.offsetHeight);
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) {
    return null;
  }
  return {
    left: x,
    right: x + width,
    top: y,
    bottom: y + height,
  };
}

function collectPrimarySelectedCtgIds(regionEl, selectionRect) {
  const selected = [];
  regionEl.querySelectorAll("[data-assembly-ctg-id]").forEach((node) => {
    const assemblyCtgId = normalizeSupportDatasetId(node.getAttribute("data-assembly-ctg-id"));
    if (!assemblyCtgId) {
      return;
    }
    const nodeRect = resolveMemberChipNodeRect(node);
    if (!nodeRect || !isRectOverlap(selectionRect, nodeRect)) {
      return;
    }
    selected.push(assemblyCtgId);
  });
  return normalizeTrackSelectionCtgIds(selected);
}

function collectDeletedSelectedCtgRecordIds(regionEl, selectionRect) {
  const selected = [];
  regionEl.querySelectorAll("[data-deleted-ctg-record-id]").forEach((node) => {
    const deletedCtgRecordId = normalizeSupportDatasetId(node.getAttribute("data-deleted-ctg-record-id"));
    if (!deletedCtgRecordId) {
      return;
    }
    const nodeRect = resolveMemberChipNodeRect(node);
    if (!nodeRect || !isRectOverlap(selectionRect, nodeRect)) {
      return;
    }
    selected.push(deletedCtgRecordId);
  });
  return normalizeDeletedCtgRecordIds(selected);
}

export function collectMemberChipSelectionResult(regionEl, selectionRect) {
  return {
    primarySelectedCtgIds: collectPrimarySelectedCtgIds(regionEl, selectionRect),
    deletedSelectedRecordIds: collectDeletedSelectedCtgRecordIds(regionEl, selectionRect),
  };
}

export function bindDeletedMemberChipBoxSelection(host, store, deps) {
  assertMemberChipSelectionDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host[ASSEMBLY_MEMBER_CHIP_BOX_SELECT_BOUND]) {
    return;
  }
  host.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) {
      return;
    }
    const state = store.getState();
    if (state.assembly.activeTab !== "assembly") {
      return;
    }
    const regionEl = event.target?.closest?.(".assembly-member-chip-region");
    if (!regionEl) {
      return;
    }
    if (event.target?.closest?.("[data-assembly-ctg-id]")) {
      return;
    }
    if (event.target?.closest?.("[data-deleted-ctg-record-id]")) {
      return;
    }

    const boxEl = ensureMemberChipSelectionBox(regionEl);
    const startPoint = resolveMemberChipPointerContentPoint(event, regionEl);
    let currentPoint = startPoint;
    let dragging = false;

    const updateSelectionBox = () => {
      const left = Math.min(startPoint.x, currentPoint.x);
      const top = Math.min(startPoint.y, currentPoint.y);
      const width = Math.abs(currentPoint.x - startPoint.x);
      const height = Math.abs(currentPoint.y - startPoint.y);
      boxEl.style.left = `${left}px`;
      boxEl.style.top = `${top}px`;
      boxEl.style.width = `${width}px`;
      boxEl.style.height = `${height}px`;
      boxEl.classList.remove("is-hidden");
    };

    const onPointerMove = (moveEvent) => {
      currentPoint = resolveMemberChipPointerContentPoint(moveEvent, regionEl);
      if (!dragging && hasSelectionDragMoved(startPoint, currentPoint)) {
        dragging = true;
      }
      if (dragging) {
        updateSelectionBox();
      }
    };

    const finishSelection = () => {
      const windowObject = getWindowObject();
      windowObject?.removeEventListener?.("pointermove", onPointerMove, true);
      windowObject?.removeEventListener?.("pointerup", onPointerUp, true);
      boxEl.classList.add("is-hidden");
      if (!dragging) {
        deps.updateTrackSelection(host, store, []);
        deps.updateDeletedCtgSelection(host, store, []);
        return;
      }
      const selectionRect = normalizeSelectionRect(startPoint, currentPoint);
      const selection = collectMemberChipSelectionResult(regionEl, selectionRect);
      if (selection.primarySelectedCtgIds.length > 0 || selection.deletedSelectedRecordIds.length > 0) {
        if (selection.primarySelectedCtgIds.length > 0) {
          deps.updateTrackSelection(host, store, selection.primarySelectedCtgIds);
        }
        if (selection.deletedSelectedRecordIds.length > 0) {
          deps.updateDeletedCtgSelection(host, store, selection.deletedSelectedRecordIds);
        }
        return;
      }
      deps.updateTrackSelection(host, store, []);
      deps.updateDeletedCtgSelection(host, store, []);
    };

    const onPointerUp = () => {
      finishSelection();
    };

    const windowObject = getWindowObject();
    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
  });

  host[ASSEMBLY_MEMBER_CHIP_BOX_SELECT_BOUND] = true;
}
