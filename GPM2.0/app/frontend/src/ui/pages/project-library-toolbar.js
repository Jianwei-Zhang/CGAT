// Priority is creation, validation, then failed-record cleanup. More is always visible.
export function libraryToolbarOverflow(available, items, gap = 4) {
  let remaining = Math.max(0, available);
  const overflow = [];
  for (const item of items) {
    if (!item.available) continue;
    const width = item.width + gap;
    if (width <= remaining) remaining -= width;
    else overflow.push(item.id);
  }
  return overflow;
}

const bindings = new WeakMap();
export function bindLibraryToolbar(host, onChange) {
  bindings.get(host)?.();
  const header = host.querySelector(".project-recents-header");
  if (!header?.getBoundingClientRect) return;
  const toolbar = header.querySelector(".project-library-toolbar");
  const title = header.querySelector(".project-recents-title-label");
  const count = header.querySelector(".project-count");
  const more = header.querySelector("[data-library-root-menu]");
  if (!toolbar || !title || !more) return;
  const view = header.ownerDocument.defaultView;
  const slots = [...header.querySelectorAll("[data-library-command]")];
  let resize, mutation, removal, disposed = false;
  const sync = () => {
    if (disposed) return;
    if (!header.isConnected) { dispose(); return; }
    const width = header.getBoundingClientRect().width;
    if (!width) return;
    const gap = parseFloat(view.getComputedStyle(toolbar).columnGap) || 4;
    const titleGap = parseFloat(view.getComputedStyle(title.parentElement).columnGap) || 6;
    const titleWidth = title.scrollWidth + (count?.getBoundingClientRect().width || 0) + titleGap;
    const headerGap = parseFloat(view.getComputedStyle(header).columnGap) || 6;
    // Unhide only for this synchronous measurement; no intermediate state is painted.
    const items = slots.map(slot => {
      slot.hidden = false;
      const button = slot.querySelector("button");
      return { id: slot.dataset.libraryCommand, available: !button.hidden, width: button.getBoundingClientRect().width };
    });
    const overflow = libraryToolbarOverflow(width - titleWidth - headerGap - more.getBoundingClientRect().width, items, gap);
    slots.forEach((slot, index) => { slot.hidden = !items[index].available || overflow.includes(items[index].id); });
    host.querySelectorAll("[data-library-overflow-action]").forEach(item => {
      const id = item.dataset.libraryOverflowAction;
      item.hidden = !overflow.includes(id);
      const button = slots.find(slot => slot.dataset.libraryCommand === id)?.querySelector("button");
      if (button) item.disabled = button.disabled;
    });
    onChange(overflow);
  };
  const dispose = () => {
    disposed = true; resize?.disconnect(); mutation?.disconnect(); removal?.disconnect();
    view.removeEventListener("resize", sync);
    header.ownerDocument.fonts?.removeEventListener?.("loadingdone", sync);
    bindings.delete(host);
  };
  if (view.ResizeObserver) { resize = new view.ResizeObserver(sync); resize.observe(header); }
  if (view.MutationObserver) {
    mutation = new view.MutationObserver(sync);
    slots.forEach(slot => mutation.observe(slot.querySelector("button"), { attributes: true, attributeFilter: ["hidden", "disabled"], childList: true, characterData: true, subtree: true }));
    removal = new view.MutationObserver(() => { if (!header.isConnected) dispose(); });
    removal.observe(host.parentElement || host, { childList: true, subtree: true });
  }
  view.addEventListener("resize", sync);
  header.ownerDocument.fonts?.addEventListener?.("loadingdone", sync);
  bindings.set(host, dispose);
  sync();
  return dispose;
}
