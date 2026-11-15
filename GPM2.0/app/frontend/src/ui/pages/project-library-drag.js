import { readProjectLibrary, partitionAncestors } from "../../services/project-library.js";

export function canDropLibraryItem(library, source, target, root = false) {
  if (library.error || !source || (root && source.kind !== "folder")) return false;
  if (target && !library.partitions.some(node => node.id === target)) return false;
  if (source.kind === "project") return true;
  const node = library.partitions.find(item => item.id === source.id);
  return Boolean(node && (root || target) && node.parentId !== target
    && !partitionAncestors(library, target).some(item => item.id === source.id));
}

const bindings = new WeakMap();
// Pointer-based movement deliberately avoids HTML5/native file drag-and-drop.
export function bindLibraryPointerDrag(host, { busy, move, error, toggle }) {
  bindings.get(host)?.();
  const tree = host.querySelector(".library-tree");
  if (!tree) return;
  const doc = tree.ownerDocument, view = doc.defaultView;
  let drag = null, hoverTimer = null, frame = null, suppressClick = false, observer;
  const clearTarget = () => {
    if (hoverTimer) view.clearTimeout(hoverTimer);
    hoverTimer = null;
    drag?.target?.classList.remove("is-drop-target");
    if (drag) { drag.target = null; drag.targetId = null; }
  };
  const finish = commit => {
    if (!drag) return;
    const previous = drag;
    clearTarget(); drag = null;
    if (frame) view.cancelAnimationFrame(frame);
    frame = null; previous.ghost?.remove();
    tree.classList.remove("is-dragging");
    doc.removeEventListener("keydown", onEscape, true);
    view.removeEventListener("blur", onBlur);
    if (tree.hasPointerCapture?.(previous.pointerId)) tree.releasePointerCapture(previous.pointerId);
    if (previous.active) { suppressClick = true; view.setTimeout(() => { suppressClick = false; }, 0); }
    if (commit && previous.active && previous.destination !== null && !busy()) {
      try { move(previous.source, previous.destination); } catch (cause) { error(cause); }
    }
  };
  const onEscape = event => { if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(false); } };
  const onBlur = () => finish(false);
  const targetAt = () => {
    if (!drag?.active) return;
    const hit = doc.elementFromPoint(drag.x, drag.y);
    const target = hit?.closest("[data-library-folder], [data-library-drop-root]");
    const root = target?.hasAttribute("data-library-drop-root");
    const id = root ? "" : target?.dataset.libraryFolder;
    const valid = target && host.contains(target) && canDropLibraryItem(readProjectLibrary(), drag.source, id, root);
    drag.destination = valid ? id : null;
    if (drag.target === (valid ? target : null)) return;
    clearTarget();
    if (valid) {
      drag.target = target; drag.targetId = id; target.classList.add("is-drop-target");
      if (!root && target.closest("[data-library-group]")?.getAttribute("aria-expanded") === "false") {
        hoverTimer = view.setTimeout(() => {
          if (drag?.target !== target) return;
          try { toggle(id, true); } catch (cause) { finish(false); error(cause); }
        }, 650);
      }
    }
  };
  const tick = () => {
    if (!drag?.active) return;
    const scroller = tree.closest(".project-recent-list"), rect = scroller?.getBoundingClientRect();
    if (rect && drag.x >= rect.left && drag.x <= rect.right && drag.y >= rect.top && drag.y <= rect.bottom) {
      const delta = drag.y < rect.top + 30 ? -8 : drag.y > rect.bottom - 30 ? 8 : 0;
      if (delta) { scroller.scrollTop += delta; targetAt(); }
    }
    frame = view.requestAnimationFrame(tick);
  };
  tree.addEventListener("dragstart", event => event.preventDefault());
  tree.addEventListener("pointerdown", event => {
    if (event.button !== 0 || event.isPrimary === false || busy() || event.pointerType === "touch") return;
    if (!event.target.closest("[data-recent-path], [data-library-select]")) return;
    const row = event.target.closest("[data-library-drag-project], [data-library-drag-folder]");
    if (!row) return;
    drag = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, x: event.clientX, y: event.clientY,
      source: row.hasAttribute("data-library-drag-project") ? { kind: "project", id: row.dataset.libraryDragProject } : { kind: "folder", id: row.dataset.libraryDragFolder },
      label: row.querySelector("strong, .library-folder-name span")?.textContent || "", active: false, destination: null };
    doc.addEventListener("keydown", onEscape, true); view.addEventListener("blur", onBlur);
  });
  tree.addEventListener("pointerleave", () => { if (drag && !drag.active) finish(false); });
  tree.addEventListener("pointermove", event => {
    if (drag?.pointerId !== event.pointerId) return;
    drag.x = event.clientX; drag.y = event.clientY;
    if (!drag.active && Math.hypot(drag.x - drag.startX, drag.y - drag.startY) < 6) return;
    event.preventDefault();
    if (!drag.active) {
      if (busy()) { finish(false); return; }
      drag.active = true; tree.setPointerCapture?.(event.pointerId); tree.classList.add("is-dragging");
      drag.ghost = doc.createElement("div"); drag.ghost.className = "library-drag-ghost"; drag.ghost.textContent = drag.label;
      doc.body.append(drag.ghost); frame = view.requestAnimationFrame(tick);
    }
    drag.ghost.style.left = `${event.clientX + 14}px`; drag.ghost.style.top = `${event.clientY + 12}px`;
    targetAt();
  });
  tree.addEventListener("pointerup", event => {
    if (drag?.pointerId !== event.pointerId) return;
    // Read the actual release location, not an earlier hover target.
    drag.x = event.clientX; drag.y = event.clientY; targetAt(); finish(true);
  });
  for (const type of ["pointercancel", "lostpointercapture"]) tree.addEventListener(type, event => { if (drag?.pointerId === event.pointerId) finish(false); });
  tree.addEventListener("click", event => { if (suppressClick) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
  const dispose = () => { finish(false); observer?.disconnect(); bindings.delete(host); };
  if (view.MutationObserver) {
    observer = new view.MutationObserver(() => { if (!tree.isConnected) dispose(); });
    observer.observe(host.parentElement || host, { childList: true, subtree: true });
  }
  bindings.set(host, dispose);
  return dispose;
}
