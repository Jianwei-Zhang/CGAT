import {
  filterPrimaryTrackSelectionCtgIds,
  normalizeDeletedCtgRecordIds,
  normalizeSupportDatasetId,
} from "./selection-state.js";
import {
  getSubviewSelections,
  getSubviewState,
  resolveFilteredSubviewTrackPairSelectionsFromAssembly,
} from "./subview-state.js";
import {
  buildAssemblyContextMenuItems,
  resolveAssemblyCtgContextTarget,
  resolveDeletedCtgContextTarget,
  resolveFinalPathGraphSegmentContextTarget,
  resolveSubviewAnchorEdgeContextTarget,
  resolveSubviewHitContextTarget,
  resolveSubviewFragmentContextTarget,
  resolveSubviewTrackPairContextTarget,
  resolveTrackLabelContextTarget,
} from "./context-menu.js";

const ASSEMBLY_CONTEXT_MENU_BOUND = Symbol("assemblyContextMenuBound");
const REQUIRED_CONTEXT_MENU_ACTION_NAMES = [
  "enterSubviewFromTrackSelections",
  "enterSubviewFromCandidates",
  "setSubviewTrackPairCtgHidden",
  "toggleSubviewContigFlip",
  "deleteSelectedSubviewTrackPairCtgs",
  "clearSubviewTrackPairHiddenCtgs",
  "setSelectedPrimaryTrackCtgsHidden",
  "deleteSelectedTrackCtgs",
  "runBatchDeleteTrackCtgs",
  "restoreSelectedDeletedCtgs",
  "canEditTrackCtg",
  "addFinalPathContigRelativeToSegment",
  "addFinalPathGapRelativeToSegment",
  "deleteFinalPathSegment",
  "flipFinalPathSegment",
  "toggleSupportTrackCtgMirror",
  "togglePrimaryTrackCtgHidden",
  "toggleSubviewAnchorEdge",
  "appendTrackContigToFinalPath",
  "addTrackContigToPhasedTrack",
  "removePhasedTrackItem",
  "deletePhasedTrack",
  "importAddCtgIntoTrack",
  "setActiveHitsTrack",
  "setAssemblyActionFeedback",
  "applyEditorAction",
  "promptForRenameCtg",
  "promptForDeleteShorterThanLength",
  "buildRenameCtgActionArgs",
  "rerender",
];
const REQUIRED_CONTEXT_MENU_RUNTIME_DEPS = [
  ...REQUIRED_CONTEXT_MENU_ACTION_NAMES,
  "escapeAttr",
  "escapeHtml",
  "updateDeletedCtgSelection",
  "updateTrackSelection",
];

function assertContextMenuRuntimeDeps(deps) {
  const missing = REQUIRED_CONTEXT_MENU_RUNTIME_DEPS.filter((name) => typeof deps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing context menu runtime deps: ${missing.join(", ")}`);
}

function assertContextMenuActionDeps(actionDeps) {
  const missing = REQUIRED_CONTEXT_MENU_ACTION_NAMES.filter((name) => typeof actionDeps?.[name] !== "function");
  if (!missing.length) {
    return;
  }
  throw new TypeError(`Missing context menu action deps: ${missing.join(", ")}`);
}

function positionContextMenuWithinViewport(menu, clientX, clientY) {
  if (!menu || typeof menu.getBoundingClientRect !== "function") {
    return;
  }
  const viewportWidth =
    Number(globalThis.window?.innerWidth)
    || Number(globalThis.document?.documentElement?.clientWidth)
    || 0;
  const viewportHeight =
    Number(globalThis.window?.innerHeight)
    || Number(globalThis.document?.documentElement?.clientHeight)
    || 0;
  if (!Number.isFinite(viewportWidth) || viewportWidth <= 0 || !Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    return;
  }
  const margin = 8;
  const requestedLeft = Number.isFinite(Number(clientX)) ? Number(clientX) : margin;
  const requestedTop = Number.isFinite(Number(clientY)) ? Number(clientY) : margin;
  menu.style.left = `${Math.max(margin, requestedLeft)}px`;
  menu.style.top = `${Math.max(margin, requestedTop)}px`;
  menu.style.maxHeight = "";
  menu.style.overflowY = "";
  const rect = menu.getBoundingClientRect();
  const menuWidth = Math.max(0, Number(rect?.width || menu.offsetWidth || 0));
  const menuHeight = Math.max(0, Number(rect?.height || menu.offsetHeight || 0));
  const maxHeight = Math.max(0, viewportHeight - margin * 2);
  const maxLeft = Math.max(margin, viewportWidth - menuWidth - margin);
  let nextTop = Math.min(Math.max(requestedTop, margin), Math.max(margin, viewportHeight - menuHeight - margin));
  if (menuHeight > maxHeight) {
    menu.style.maxHeight = `${maxHeight}px`;
    menu.style.overflowY = "auto";
    nextTop = margin;
  }
  menu.style.left = `${Math.min(Math.max(requestedLeft, margin), maxLeft)}px`;
  menu.style.top = `${nextTop}px`;
}

export function renderContextMenuItems(items, deps) {
  const { escapeAttr, escapeHtml } = deps;
  return items
    .map((item, index) => {
      const disabled = Boolean(item.disabled);
      const attrs = [];
      if (typeof item.run === "function" && !disabled) {
        attrs.push(`data-menu-action-index="${index}"`);
      }
      if (disabled) {
        attrs.push("disabled");
        attrs.push('aria-disabled="true"');
      }
      attrs.push(`title="${escapeAttr(item.title || item.label)}"`);
      return `<button class="context-menu-item${disabled ? " is-disabled" : ""}" ${attrs.join(" ")}>${escapeHtml(item.label)}</button>`;
    })
    .join("");
}

export function buildAssemblyContextMenuActions(actionDeps, overrides = {}) {
  assertContextMenuActionDeps(actionDeps);
  const resolveAction = (name) =>
    typeof overrides?.[name] === "function" ? overrides[name] : actionDeps[name];
  const confirm = typeof overrides.confirm === "function"
    ? overrides.confirm
    : (message) => globalThis.window?.confirm?.(message) ?? false;
  return {
    enterSubviewFromTrackSelections: resolveAction("enterSubviewFromTrackSelections"),
    enterSubviewFromCandidates: resolveAction("enterSubviewFromCandidates"),
    setSubviewTrackPairCtgHidden: resolveAction("setSubviewTrackPairCtgHidden"),
    toggleSubviewContigFlip: resolveAction("toggleSubviewContigFlip"),
    deleteSelectedSubviewTrackPairCtgs: resolveAction("deleteSelectedSubviewTrackPairCtgs"),
    clearSubviewTrackPairHiddenCtgs: resolveAction("clearSubviewTrackPairHiddenCtgs"),
    setSelectedPrimaryTrackCtgsHidden: resolveAction("setSelectedPrimaryTrackCtgsHidden"),
    deleteSelectedTrackCtgs: resolveAction("deleteSelectedTrackCtgs"),
    runBatchDeleteTrackCtgs: resolveAction("runBatchDeleteTrackCtgs"),
    restoreSelectedDeletedCtgs: resolveAction("restoreSelectedDeletedCtgs"),
    canEditTrackCtg: resolveAction("canEditTrackCtg"),
    addFinalPathContigRelativeToSegment: resolveAction("addFinalPathContigRelativeToSegment"),
    addFinalPathGapRelativeToSegment: resolveAction("addFinalPathGapRelativeToSegment"),
    deleteFinalPathSegment: resolveAction("deleteFinalPathSegment"),
    flipFinalPathSegment: resolveAction("flipFinalPathSegment"),
    toggleSupportTrackCtgMirror: resolveAction("toggleSupportTrackCtgMirror"),
    togglePrimaryTrackCtgHidden: resolveAction("togglePrimaryTrackCtgHidden"),
    toggleSubviewAnchorEdge: resolveAction("toggleSubviewAnchorEdge"),
    appendTrackContigToFinalPath: resolveAction("appendTrackContigToFinalPath"),
    addTrackContigToPhasedTrack: resolveAction("addTrackContigToPhasedTrack"),
    removePhasedTrackItem: resolveAction("removePhasedTrackItem"),
    deletePhasedTrack: resolveAction("deletePhasedTrack"),
    importAddCtgIntoTrack: resolveAction("importAddCtgIntoTrack"),
    setActiveHitsTrack: resolveAction("setActiveHitsTrack"),
    setAssemblyActionFeedback: resolveAction("setAssemblyActionFeedback"),
    openAssemblyContextMenuAt: resolveAction("openAssemblyContextMenuAt"),
    applyEditorAction: resolveAction("applyEditorAction"),
    promptForRenameCtg: resolveAction("promptForRenameCtg"),
    promptForDeleteShorterThanLength: resolveAction("promptForDeleteShorterThanLength"),
    buildRenameCtgActionArgs: resolveAction("buildRenameCtgActionArgs"),
    confirm,
    rerender: overrides.rerender || actionDeps.rerender,
  };
}

export function bindAssemblyContextMenu(host, store, deps) {
  assertContextMenuRuntimeDeps(deps);
  if (host[ASSEMBLY_CONTEXT_MENU_BOUND]) {
    return;
  }

  let activeSubviewFragmentNode = null;
  let activeSubviewHitNode = null;

  const clearSubviewFragmentMenuHighlight = () => {
    activeSubviewFragmentNode?.classList?.remove?.("is-menu-active");
    activeSubviewFragmentNode = null;
  };

  const clearSubviewHitMenuHighlight = () => {
    activeSubviewHitNode?.classList?.remove?.("is-menu-active");
    activeSubviewHitNode = null;
  };

  const setSubviewFragmentMenuHighlight = (target) => {
    clearSubviewFragmentMenuHighlight();
    clearSubviewHitMenuHighlight();
    const fragmentNode = target?.closest?.("[data-subview-fragment-key][data-subview-fragment-contig-id]");
    fragmentNode?.classList?.add?.("is-menu-active");
    activeSubviewFragmentNode = fragmentNode || null;
    const hitNode = target?.closest?.("[data-subview-hit-key]");
    hitNode?.classList?.add?.("is-menu-active");
    activeSubviewHitNode = hitNode || null;
  };

  const closeMenu = () => {
    const menu = host.querySelector("#assembly-context-menu");
    clearSubviewFragmentMenuHighlight();
    clearSubviewHitMenuHighlight();
    if (!menu) {
      return;
    }
    menu.classList.add("is-hidden");
    menu.innerHTML = "";
  };

  const openAssemblyContextMenuAt = (
    hostNode,
    storeValue,
    runtimeDeps,
    {
      clientX = 0,
      clientY = 0,
      ctgContext = null,
      trackLabelContext = null,
      subviewTrackPairContext = null,
      subviewHitContext = null,
      subviewAnchorEdgeContext = null,
      subviewFragmentContext = null,
      deletedCtgContext = null,
      finalPathSegmentContext = null,
      memberNode = null,
      target = null,
    } = {},
  ) => {
    const menu = hostNode.querySelector("#assembly-context-menu");
    if (!menu) {
      return;
    }
    const items = buildAssemblyContextMenuItems({
      ctgContext,
      trackLabelContext,
      subviewTrackPairContext,
      subviewHitContext,
      subviewAnchorEdgeContext,
      subviewFragmentContext,
      deletedCtgContext,
      finalPathSegmentContext,
      memberNode,
      store: storeValue,
      host: hostNode,
      actions: buildAssemblyContextMenuActions(
        {
          ...runtimeDeps,
          openAssemblyContextMenuAt: (nextHost, nextStore, nextPayload) =>
            openAssemblyContextMenuAt(nextHost, nextStore, runtimeDeps, nextPayload),
        },
        runtimeDeps,
      ),
      contextPoint: { clientX, clientY },
    });

    if (!items.length) {
      closeMenu();
      return;
    }
    setSubviewFragmentMenuHighlight(target);
    menu.innerHTML = renderContextMenuItems(items, runtimeDeps);
    menu.classList.remove("is-hidden");
    positionContextMenuWithinViewport(menu, clientX, clientY);

    menu.querySelectorAll("[data-menu-action-index]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event?.stopPropagation?.();
        const index = Number(button.getAttribute("data-menu-action-index") || -1);
        closeMenu();
        if (!Number.isFinite(index) || index < 0 || index >= items.length) {
          return;
        }
        await items[index].run();
      });
    });
  };

  if (typeof host?.addEventListener !== "function") {
    return;
  }

  host.addEventListener("click", () => {
    closeMenu();
  });
  host.addEventListener("scroll", () => {
    closeMenu();
  }, true);

  host.addEventListener("contextmenu", (event) => {
    const menu = host.querySelector("#assembly-context-menu");
    if (!menu) {
      return;
    }
    const state = store.getState();
    if (state.assembly.activeTab !== "assembly") {
      return;
    }
    const ctgContext = resolveAssemblyCtgContextTarget(event.target);
    const trackLabelContext = resolveTrackLabelContextTarget(event.target);
    const subviewTrackPairContext = resolveSubviewTrackPairContextTarget(event.target);
    const subviewHitContext = resolveSubviewHitContextTarget(event.target);
    const subviewAnchorEdgeContext = resolveSubviewAnchorEdgeContextTarget(event.target);
    const subviewFragmentContext = resolveSubviewFragmentContextTarget(event.target);
    const deletedCtgContext = resolveDeletedCtgContextTarget(event.target);
    const finalPathSegmentContext = resolveFinalPathGraphSegmentContextTarget(event.target);
    const primaryMemberChipNode = event.target?.closest?.(
      ".assembly-member-chip-region [data-assembly-ctg-id]",
    );
    if (deletedCtgContext) {
      const deletedCtgRecordId = normalizeSupportDatasetId(deletedCtgContext.deletedCtgRecordId);
      if (deletedCtgRecordId) {
        const current = normalizeDeletedCtgRecordIds(store.getState().assembly.selectedDeletedCtgRecordIds);
        if (event.ctrlKey || event.metaKey) {
          const nextSet = new Set(current);
          if (nextSet.has(deletedCtgRecordId)) {
            nextSet.delete(deletedCtgRecordId);
          } else {
            nextSet.add(deletedCtgRecordId);
          }
          event.preventDefault();
          closeMenu();
          deps.updateDeletedCtgSelection(host, store, Array.from(nextSet.values()));
          return;
        }
        if (!current.includes(deletedCtgRecordId)) {
          deps.updateDeletedCtgSelection(host, store, [deletedCtgRecordId]);
        }
      }
    }
    if (primaryMemberChipNode && !deletedCtgContext) {
      const chipCtgId = normalizeSupportDatasetId(primaryMemberChipNode.getAttribute("data-assembly-ctg-id"));
      if (chipCtgId) {
        const current = filterPrimaryTrackSelectionCtgIds(
          store.getState().assembly.trackSelectedCtgIds,
          store.getState().assembly,
        );
        if (event.ctrlKey || event.metaKey) {
          const nextSet = new Set(current);
          if (nextSet.has(chipCtgId)) {
            nextSet.delete(chipCtgId);
          } else {
            nextSet.add(chipCtgId);
          }
          event.preventDefault();
          closeMenu();
          deps.updateTrackSelection(host, store, Array.from(nextSet.values()));
          return;
        }
        if (!current.includes(chipCtgId)) {
          deps.updateTrackSelection(host, store, [chipCtgId]);
        }
      }
    }
    const latestState = store.getState();
    const selectedTrackCtgIds = filterPrimaryTrackSelectionCtgIds(
      latestState.assembly.trackSelectedCtgIds,
      latestState.assembly,
    );
    const selectedDeletedRecordIds = normalizeDeletedCtgRecordIds(
      latestState.assembly.selectedDeletedCtgRecordIds,
    );
    const subviewSelections = getSubviewSelections(getSubviewState(latestState.assembly));
    const selectedSubviewTrackPairCtgs = resolveFilteredSubviewTrackPairSelectionsFromAssembly(
      latestState.assembly,
    );
    const memberNode = event.target.closest("[data-member-seq-id]");
    if (
      !ctgContext &&
      !trackLabelContext &&
      !subviewTrackPairContext &&
      !subviewHitContext &&
      !subviewAnchorEdgeContext &&
      !subviewFragmentContext &&
      !deletedCtgContext &&
      !finalPathSegmentContext &&
      !memberNode &&
      !selectedTrackCtgIds.length &&
      !selectedDeletedRecordIds.length &&
      !subviewSelections.length &&
      !selectedSubviewTrackPairCtgs.length
    ) {
      return;
    }
    event.preventDefault();
          openAssemblyContextMenuAt(host, store, deps, {
            clientX: event.clientX,
            clientY: event.clientY,
            ctgContext,
      trackLabelContext,
      subviewTrackPairContext,
      subviewHitContext,
      subviewAnchorEdgeContext,
      subviewFragmentContext,
            deletedCtgContext,
            finalPathSegmentContext,
            memberNode,
            target: event.target,
          });
  });

  host[ASSEMBLY_CONTEXT_MENU_BOUND] = true;
}
