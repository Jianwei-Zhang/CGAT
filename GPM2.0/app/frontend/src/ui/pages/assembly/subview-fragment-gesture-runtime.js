import { projectCurrentSubviewToComposition, resolveCurrentSubviewCompositionViewport } from "./subview-composition-controller.js";
import { prepareSourceOwnedSubviewHistory } from "./subview-fragment-history.js";
import { materializeLocalIntervals } from "./subview-fragment-model.js";
import { applySubviewComposition } from "./subview-composition-state.js";
import { preserveSubviewRemovalViewport } from "./subview-removal-viewport.js";

const fingerprint = (subview) => JSON.stringify([subview?.summary, subview?.activeAnchors, subview?.manualAnchors, subview?.flippedCtgs]);
const identity = (state) => JSON.stringify([state.session?.workspacePath, state.session?.projectId, state.assembly?.selectedChrName]);
const blocked = (state) => state.assembly?.loading || state.assembly?.mainViewHistory?.inFlight || state.assembly?.sourceEditingReloadRequired;
const read = (node, key) => String(node?.getAttribute?.(key) || "");

function descriptor(node, state, composition) {
  const id = Number(read(node, "data-subview-fragment-contig-id"));
  const role = read(node, "data-subview-fragment-role"), slot = read(node, "data-subview-fragment-slot");
  const entity = read(node, "data-subview-fragment-entity-key");
  const candidates = composition.members.filter((member) => entity ? member.entityKey === entity
    : member.assemblyCtgId === id && member.source.role === role && member.lane === slot);
  if (candidates.length !== 1) return null;
  const member = candidates[0];
  let start = Number(read(node, "data-subview-fragment-start")), end = Number(read(node, "data-subview-fragment-end"));
  const display = read(node, "data-subview-fragment-coordinate-space") === "display"
    || (!entity && state.assembly.subview?.summary?.mode !== "composition");
  if (display && member.flipped) [start, end] = [member.lengthBp - end + 1, member.lengthBp - start + 1];
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start < 1 || end < start || end > member.lengthBp) return null;
  return { node, memberKey: member.entityKey, start, end,
    key: JSON.stringify([member.entityKey, start, end]), partial: start !== 1 || end !== member.lengthBp };
}

export function createSubviewFragmentGestureRuntime(deps) {
  function prepare(host, store, entries, before, composition) {
    const viewport = resolveCurrentSubviewCompositionViewport(before, host);
    const materialized = materializeLocalIntervals(composition, entries);
    if (!materialized.changed) return null;
    let base = prepareSourceOwnedSubviewHistory(before, host, { viewport, preserveLegacy: true,
      projectHistorical: (state) => deps.projectHistorical(state, host) });
    base = preserveSubviewRemovalViewport(base, host, { viewport });
    const subview = applySubviewComposition(base.subview, materialized.composition);
    const stableHost = host?.closest?.("#route-host") || host;
    store.setState({ assembly: { ...base, subview } });
    deps.rerenderSubviewPanel(stableHost, store);
    let accepted = false;
    return { host: stableHost, selectedKeys: materialized.selectedKeys,
      accept() { accepted = true; },
      rollback() {
        const latest = store.getState();
        if (accepted || identity(latest) !== identity(before) || fingerprint(latest.assembly.subview) !== fingerprint(subview)) return;
        const localKeys = ["subviewHistoryByKey", "subviewCompositionViewport", "subviewTrackView", "subviewAnchorStateByKey", "subviewTrackDragOffsets"];
        store.setState({ assembly: { ...latest.assembly,
          ...Object.fromEntries(localKeys.map((key) => [key, before.assembly[key]])),
          subview: { ...before.assembly.subview, pairwiseEvidence: latest.assembly.subview?.pairwiseEvidence },
        } });
        deps.rerenderSubviewPanel(stableHost, store);
      },
    };
  }

  function deferSubviewFragmentDrag(host, store, event, begin) {
    const before = store.getState();
    if (blocked(before)) return false;
    const fragmentNode = event.target?.closest?.("[data-subview-fragment-key][data-subview-fragment-contig-id]");
    if (!fragmentNode) return false;
    const composition = projectCurrentSubviewToComposition(before, host);
    const entry = descriptor(fragmentNode, before, composition);
    if (!entry?.partial) return false;
    event.preventDefault();
    const win = deps.getWindow?.() || globalThis.window;
    let finished = false;
    const cleanup = () => {
      if (finished) return; finished = true;
      win?.removeEventListener?.("pointermove", move, true);
      win?.removeEventListener?.("pointerup", stop, true);
      win?.removeEventListener?.("pointercancel", stop, true);
    };
    const stop = () => cleanup();
    const move = (nextEvent) => {
      if (finished || (event.pointerId != null && nextEvent.pointerId != null && event.pointerId !== nextEvent.pointerId)) return;
      const latest = store.getState();
      if (blocked(latest) || identity(latest) !== identity(before) || latest.assembly.subview !== before.assembly.subview) { cleanup(); return; }
      if (!Number.isFinite(Number(nextEvent.clientX)) || Math.abs(Number(nextEvent.clientX) - Number(event.clientX)) < 2) return;
      cleanup();
      const prepared = prepare(host, store, [entry], before, composition);
      if (!prepared) return;
      const key = prepared.selectedKeys.get(entry.key);
      const target = [...(prepared.host?.querySelectorAll?.("[data-subview-composition-entity-key][data-subview-contig-id]") || [])]
        .find((node) => read(node, "data-subview-composition-entity-key") === key);
      if (!target) { prepared.rollback(); return; }
      const runtime = begin({ button: 0, target, clientX: event.clientX, clientY: event.clientY,
        pointerId: event.pointerId, preventDefault() {}, defaultPrevented: false }, prepared);
      runtime?.onPointerMove(nextEvent);
    };
    win?.addEventListener?.("pointermove", move, true);
    win?.addEventListener?.("pointerup", stop, true);
    win?.addEventListener?.("pointercancel", stop, true);
    return true;
  }

  function prepareSubviewFragmentSelection(host, store, scrollEl, rect) {
    const before = store.getState();
    if (blocked(before)) return null;
    const composition = projectCurrentSubviewToComposition(before, host);
    const all = [...(scrollEl?.querySelectorAll?.("[data-subview-fragment-key][data-subview-fragment-contig-id]") || [])]
      .map((node) => descriptor(node, before, composition)).filter(Boolean);
    const selected = all.filter(({ node }) => {
      const [x, y, width, height] = ["x", "y", "width", "height"].map((key) => Number(node.getAttribute(key)));
      return [x, y, width, height].every(Number.isFinite) && x <= rect.right && x + width >= rect.left && y <= rect.bottom && y + height >= rect.top;
    });
    if (!selected.some((entry) => entry.partial)) return null;
    const prepared = prepare(host, store, all, before, composition);
    if (!prepared) return null;
    const members = store.getState().assembly.subview.summary.members;
    const entries = selected.flatMap((entry) => {
      const key = prepared.selectedKeys.get(entry.key);
      const member = members.find((value) => value.entityKey === key);
      return member ? [{ trackRole: member.source.role, contigId: member.assemblyCtgId, compositionEntityKey: member.entityKey, slot: member.lane }] : [];
    });
    prepared.accept();
    return { entries, host: prepared.host };
  }
  return { deferSubviewFragmentDrag, prepareSubviewFragmentSelection };
}
