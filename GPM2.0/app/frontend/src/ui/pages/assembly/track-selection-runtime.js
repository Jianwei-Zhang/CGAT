import {
  normalizeSupportDatasetId,
  normalizeTrackRole,
  normalizeTrackSelectionCtgIds,
} from "./selection-state.js";
import { normalizeSubviewTrackPairSelectionCtgs } from "./subview-state.js";
import { resolveTrackPointerContentPoint } from "./track-viewport.js";

const ASSEMBLY_TRACK_BOX_SELECT_BOUND = Symbol("assemblyTrackBoxSelectBound");
const REQUIRED_TRACK_SELECTION_DEPS = [
  "updateTrackSelection",
  "updateSubviewTrackPairSelection",
];

function assertTrackSelectionDeps(deps) {
  const missing = REQUIRED_TRACK_SELECTION_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing track selection runtime deps: ${missing.join(", ")}`);
}

function getWindowObject() {
  return globalThis.window;
}

function getDocumentObject() {
  return globalThis.document;
}

function ensureTrackSelectionBox(scrollEl) {
  let boxEl = scrollEl.querySelector(".track-selection-box");
  if (boxEl) {
    return boxEl;
  }
  boxEl = getDocumentObject().createElement("div");
  boxEl.className = "track-selection-box is-hidden";
  scrollEl.appendChild(boxEl);
  return boxEl;
}

function hasTrackSelectionDragMoved(start, current) {
  return Math.abs(Number(current.x) - Number(start.x)) >= 4 || Math.abs(Number(current.y) - Number(start.y)) >= 4;
}

function normalizeTrackSelectionRect(start, end) {
  return {
    left: Math.min(start.x, end.x),
    right: Math.max(start.x, end.x),
    top: Math.min(start.y, end.y),
    bottom: Math.max(start.y, end.y),
  };
}

function isTrackRectOverlap(leftRect, rightRect) {
  return !(
    leftRect.right < rightRect.left ||
    leftRect.left > rightRect.right ||
    leftRect.bottom < rightRect.top ||
    leftRect.top > rightRect.bottom
  );
}

function collectTrackSelectedCtgIds(scrollEl, selectionRect) {
  const selected = [];
  scrollEl.querySelectorAll("[data-track-contig-id][data-track-role]").forEach((node) => {
    const trackRole = String(node.getAttribute("data-track-role") || "").trim();
    if (trackRole !== "primary") {
      return;
    }
    const ctgId = normalizeSupportDatasetId(node.getAttribute("data-track-contig-id"));
    if (!ctgId) {
      return;
    }
    const x = Number(node.getAttribute("data-track-rect-x"));
    const y = Number(node.getAttribute("data-track-rect-y"));
    const width = Number(node.getAttribute("data-track-rect-width"));
    const height = Number(node.getAttribute("data-track-rect-height"));
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) {
      return;
    }
    const nodeRect = { left: x, right: x + width, top: y, bottom: y + height };
    if (!isTrackRectOverlap(selectionRect, nodeRect)) {
      return;
    }
    selected.push(ctgId);
  });
  return normalizeTrackSelectionCtgIds(selected);
}

function collectSubviewTrackPairSelectedCtgs(scrollEl, selectionRect) {
  const selected = [];
  scrollEl.querySelectorAll("[data-subview-contig-id][data-subview-track-role]").forEach((node) => {
    const trackRole = normalizeTrackRole(node.getAttribute("data-subview-track-role"));
    const contigId = normalizeSupportDatasetId(node.getAttribute("data-subview-contig-id"));
    if (!trackRole || !contigId) {
      return;
    }
    const x = Number(node.getAttribute("data-subview-rect-x"));
    const y = Number(node.getAttribute("data-subview-rect-y"));
    const width = Number(node.getAttribute("data-subview-rect-width"));
    const height = Number(node.getAttribute("data-subview-rect-height"));
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(width) || !Number.isFinite(height)) {
      return;
    }
    const nodeRect = { left: x, right: x + width, top: y, bottom: y + height };
    if (!isTrackRectOverlap(selectionRect, nodeRect)) {
      return;
    }
    selected.push({ trackRole, contigId });
  });
  return normalizeSubviewTrackPairSelectionCtgs(selected);
}

export function bindTrackBoxSelection(host, store, deps) {
  assertTrackSelectionDeps(deps);
  if (typeof host?.addEventListener !== "function") {
    return;
  }
  if (host[ASSEMBLY_TRACK_BOX_SELECT_BOUND]) {
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
    const scrollEl = event.target?.closest?.(".assembly-track-scroll[data-track-role]");
    if (!scrollEl) {
      return;
    }
    const trackRole = String(scrollEl.getAttribute("data-track-role") || "").trim();
    const isPrimaryTrack = trackRole === "primary";
    const isSubviewTrack = trackRole === "subview";
    if (!isPrimaryTrack && !isSubviewTrack) {
      return;
    }
    if (isPrimaryTrack && event.target?.closest?.("[data-track-contig-id][data-track-role]")) {
      return;
    }
    if (isSubviewTrack && event.target?.closest?.("[data-subview-contig-id][data-subview-track-slot]")) {
      return;
    }

    event.preventDefault();
    const boxEl = ensureTrackSelectionBox(scrollEl);
    const startPoint = resolveTrackPointerContentPoint(event, scrollEl);
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
      currentPoint = resolveTrackPointerContentPoint(moveEvent, scrollEl);
      if (!dragging && hasTrackSelectionDragMoved(startPoint, currentPoint)) {
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
        if (isPrimaryTrack) {
          deps.updateTrackSelection(host, store, []);
        } else {
          deps.updateSubviewTrackPairSelection(host, store, []);
        }
        return;
      }
      const selectionRect = normalizeTrackSelectionRect(startPoint, currentPoint);
      if (isPrimaryTrack) {
        deps.updateTrackSelection(host, store, collectTrackSelectedCtgIds(scrollEl, selectionRect));
        return;
      }
      deps.updateSubviewTrackPairSelection(host, store, collectSubviewTrackPairSelectedCtgs(scrollEl, selectionRect));
    };

    const onPointerUp = () => {
      finishSelection();
    };

    const windowObject = getWindowObject();
    windowObject?.addEventListener?.("pointermove", onPointerMove, true);
    windowObject?.addEventListener?.("pointerup", onPointerUp, true);
  });

  host[ASSEMBLY_TRACK_BOX_SELECT_BOUND] = true;
}
