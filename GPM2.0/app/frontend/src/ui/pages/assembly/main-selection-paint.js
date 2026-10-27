// Selection-only patches deliberately never replace a card, plot, or panel.
// Keeping their owners mounted preserves focus, menus, tooltip and scroll state.
export function paintMainSelection(host, state, { focus = false } = {}) {
  const root = host?.closest?.("#route-host") || host;
  if (!root?.querySelector?.(".assembly-track-unified")) return false;
  const assembly = state.assembly || {};
  const selected = Number(assembly.selectedCtgId || 0);
  const ids = new Set((assembly.trackSelectedCtgIds || []).map(Number));
  const deleted = new Set((assembly.selectedDeletedCtgRecordIds || []).map(Number));
  for (const chip of root.querySelectorAll(".assembly-member-chip-region [data-assembly-ctg-id]")) {
    const id = Number(chip.dataset.assemblyCtgId);
    chip.classList.toggle("is-active", id === selected);
    chip.classList.toggle("is-multi-selected", ids.has(id));
    chip.setAttribute("aria-pressed", String(id === selected || ids.has(id)));
  }
  for (const chip of root.querySelectorAll("[data-deleted-ctg-record-id]")) {
    const active = deleted.has(Number(chip.dataset.deletedCtgRecordId));
    chip.classList.toggle("is-multi-selected", active);
    chip.setAttribute("aria-pressed", String(active));
  }
  for (const group of root.querySelectorAll(".track-ctg-group[data-track-contig-id]")) {
    const id = Number(group.dataset.trackContigId);
    group.classList.toggle("is-active", id === selected);
    group.classList.toggle("is-multi-selected", ids.has(id));
    for (const bar of group.querySelectorAll(".track-ctg")) {
      bar.classList.toggle("is-active", id === selected);
      bar.classList.toggle("is-multi-selected", ids.has(id));
    }
    if (focus && id === selected && group.dataset.trackRole === "primary") {
      const scroll = group.closest(".assembly-track-scroll");
      const x = Number(group.dataset.trackRectX), width = Number(group.dataset.trackRectWidth);
      if (scroll && Number.isFinite(x) && Number.isFinite(width)) {
        const start = x - Number(scroll.dataset.trackViewboxMinX || 0);
        scroll.dataset.focusStart = String(start);
        scroll.dataset.focusCenter = String(start + width / 2);
      }
    }
  }
  // Main multi-selection clears the Local editing selection in state. Remove
  // its paint too, without rebuilding the Local graph or its temporary layers.
  if (!assembly.subview?.trackPairSelectedCtgs?.length) {
    for (const group of root.querySelectorAll("[data-subview-contig-id]")) {
      group.classList.remove("is-multi-selected");
      for (const child of group.querySelectorAll(".is-multi-selected")) child.classList.remove("is-multi-selected");
    }
  }
  return true;
}
