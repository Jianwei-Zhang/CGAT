import { getSubviewWindowStore } from "./subview-workspace-state.js";

export const SOURCE = "[data-source-interval-projection]";

export function readSourceProjection(node) {
  try { return JSON.parse(node?.dataset?.sourceIntervalProjection || "null"); } catch { return null; }
}

// Local fragments already use original source coordinates. Further clip a
// Local trigger to the visible plot, never to its label or a reference axis.
export function correlationSourceRange(node) {
  const range = readSourceProjection(node);
  if (!range) return null;
  const result = { ...range, originalCoordinates: true };
  if (node.dataset.subviewContigId === undefined) return result;
  const viewport = node.closest?.(".subview-track-scroll");
  const bar = node.querySelector?.(".track-ctg");
  const bounds = bar?.getBoundingClientRect?.(), clip = viewport?.getBoundingClientRect?.();
  if (!bounds || !clip || bounds.right <= bounds.left || clip.right <= clip.left) return result;
  const left = Math.max(bounds.left, clip.left), right = Math.min(bounds.right, clip.right);
  if (right <= left) return null;
  const span = range.sourceEnd - range.sourceStart + 1;
  const lo = (left - bounds.left) / (bounds.right - bounds.left);
  const hi = (right - bounds.left) / (bounds.right - bounds.left);
  const start = range.orient === "-" ? 1 - hi : lo;
  const end = range.orient === "-" ? 1 - lo : hi;
  result.sourceStart = Math.max(range.sourceStart, range.sourceStart + Math.floor(start * span));
  result.sourceEnd = Math.min(range.sourceEnd, range.sourceStart + Math.ceil(end * span) - 1);
  return result;
}

export function selectedSourceRanges(surfaces, rootStore) {
  const ranges = [], assembly = rootStore.getState().assembly || {};
  const mainIds = new Set((assembly.trackSelectedCtgIds || [])
    .map(Number).filter(id => Number.isSafeInteger(id) && id > 0));
  const windows = new Map((assembly.subviewWorkspace?.windows || []).map(item => [item.id, item]));
  const localById = new Map();
  for (const [host, surface] of surfaces) {
    const fallback = surface.store.getState().assembly?.subview?.trackPairSelectedCtgs || [];
    const anyLocal = fallback.length || [...windows.values()].some(item => item.opened !== false
      && !item.minimized && item.snapshot?.subview?.trackPairSelectedCtgs?.length);
    if (!mainIds.size && !anyLocal) continue;
    for (const node of host.querySelectorAll(SOURCE)) {
      const d = node.dataset;
      let selected = false;
      if (d.subviewContigId !== undefined) {
        const id = node.closest?.("[data-local-view-window]")?.dataset.localViewWindow;
        const item = windows.get(id);
        if (item && (item.opened === false || item.minimized)) continue;
        if (id && !localById.has(id)) localById.set(id,
          getSubviewWindowStore(rootStore, id).getState().assembly?.subview?.trackPairSelectedCtgs || []);
        const entries = id ? localById.get(id) : fallback;
        selected = entries.some(entry => Number(entry.contigId) === Number(d.subviewContigId)
          && (!d.subviewTrackRole || entry.trackRole === d.subviewTrackRole)
          && (!entry.slot || entry.slot === d.subviewTrackSlot)
          && (!entry.compositionEntityKey || entry.compositionEntityKey === d.subviewCompositionEntityKey));
      } else if (d.trackContigId !== undefined) {
        selected = mainIds.has(Number(d.trackContigId));
      }
      if (selected) {
        const range = correlationSourceRange(node);
        if (range) ranges.push(range);
      }
    }
  }
  return ranges;
}
