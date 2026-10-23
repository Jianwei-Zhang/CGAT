import { prepareSourceOwnedSubviewHistory } from "./subview-fragment-history.js";
import { getSubviewState } from "./subview-state.js";
import { projectCurrentSubviewToComposition, resolveCurrentSubviewCompositionViewport } from "./subview-composition-controller.js";
import { applySubviewComposition, moveSubviewCompositionMembers } from "./subview-composition-state.js";
import { commitSubviewCompositionHistoryOperation } from "./subview-history-state.js";
import { preserveSubviewRemovalViewport } from "./subview-removal-viewport.js";
import { isolateLocalMemberInterval, deleteLocalMember, splitLocalMember, mergeLocalMember,
  resolveLocalMergeNeighbor, memberSourceInterval, memberEffectiveOrientation, memberActiveBackingParts } from "./subview-fragment-model.js";
import { localFragmentCopy } from "./subview-fragment-copy.js";

export function resolveLocalFragmentContext(state, host, context) {
  if (state?.assembly?.loading || state?.assembly?.sourceEditingReloadRequired || state?.assembly?.mainViewHistory?.inFlight) return null;
  let composition = projectCurrentSubviewToComposition(state, host);
  const entityKey = String(context?.entityKey || context?.compositionEntityKey || "");
  const matches = composition.members.filter((member) => entityKey ? member.entityKey === entityKey
    : member.assemblyCtgId === Number(context?.assemblyCtgId)
      && (!context?.slot || member.lane === context.slot)
      && (!context?.trackRole || member.source.role === context.trackRole));
  if (matches.length !== 1) return null;
  let member = matches[0];
  if (context?.start != null || context?.end != null) {
    if (context.start == null || context.end == null) return null;
    let start = Number(context.start), end = Number(context.end);
    const displayCoordinates = context.coordinateSpace === "display"
      || (!context.coordinateSpace && state.assembly.subview?.summary?.mode !== "composition");
    if (displayCoordinates && member.flipped) [start, end] = [member.lengthBp - end + 1, member.lengthBp - start + 1];
    const isolated = isolateLocalMemberInterval(composition, member.entityKey, start, end);
    if (!isolated.member) return null;
    composition = isolated.composition; member = isolated.member;
  }
  return { composition, member };
}

export function resolveLocalFragmentMenu(state, host, context) {
  const resolved = resolveLocalFragmentContext(state, host, context);
  if (!resolved) return null;
  const { composition, member } = resolved;
  const primaryById = new Map((state.assembly.chrCtgs || []).map((ctg) => [Number(ctg.assemblyCtgId), ctg]));
  const eligibleChr = Boolean(state.assembly.selectedChrName) && String(state.assembly.selectedChrName).toLowerCase() !== "unplaced";
  const validTargets = memberActiveBackingParts(member).every((part) => {
    const real = primaryById.get(part.assemblyCtgId);
    const length = Number(real?.totalLength ?? real?.lengthBp);
    return length > 0 && part.sourceStart === Number(real?.sourceFragment?.sourceStart || 1)
      && part.sourceEnd === Number(real?.sourceFragment?.sourceEnd || length)
      && part.orient === ((real?.orient ?? real?.refOrient) === "-" ? "-" : "+");
  });
  return { member, range: memberSourceInterval(member), canSplit: member.lengthBp > 1,
    canSync: member.source.role === "primary" && eligibleChr && validTargets,
    left: Boolean(resolveLocalMergeNeighbor(composition, member.entityKey, "left")),
    right: Boolean(resolveLocalMergeNeighbor(composition, member.entityKey, "right")),
  };
}

export function createSubviewFragmentController(deps) {
  const labels = (state) => localFragmentCopy[state.locale === "en" ? "en" : "zh"];
  const sameContext = (store, before) => {
    const latest = store.getState();
    return latest.session?.workspacePath === before.session?.workspacePath
      && latest.session?.projectId === before.session?.projectId
      && latest.assembly?.selectedChrName === before.assembly?.selectedChrName
      && latest.assembly?.subview === before.assembly?.subview;
  };
  async function commit(host, store, before, composition, kind) {
    if (!sameContext(store, before)) return false;
    const viewport = resolveCurrentSubviewCompositionViewport(before, host);
    const prepared = prepareSourceOwnedSubviewHistory(before, host, { viewport, preserveLegacy: true,
      projectHistorical: (state) => deps.projectHistorical(state, host) });
    const base = preserveSubviewRemovalViewport(prepared, host, { viewport });
    const nextSubview = applySubviewComposition(getSubviewState(base), composition, { trackPairSelectedCtgs: [] });
    const result = commitSubviewCompositionHistoryOperation(base, { nextSubview, viewport,
      operation: { kind, count: 1 }, stateOrLocale: before });
    if (!result.changed) return false;
    store.setState({ assembly: { ...result.assembly, actionStatus: labels(before).localDone, actionError: "" } });
    deps.rerenderSubviewPanel(host, store);
    deps.refreshSubviewPairwiseEvidence?.(host, store);
    await deps.persistProjectAssemblyViewStateFromStore(host, store);
    return true;
  }
  async function edit(host, store, context, kind, mutate) {
    const state = store.getState(), resolved = resolveLocalFragmentContext(state, host, context);
    if (!resolved) return false;
    const result = mutate(resolved.composition, resolved.member);
    return result.changed ? commit(host, store, state, result.composition, kind) : false;
  }
  const deleteLocalFragment = (host, store, context) => edit(host, store, context, "remove-members",
    (composition, member) => deleteLocalMember(composition, member.entityKey));
  const flipLocalFragment = (host, store, context) => edit(host, store, context, "flip-contig", (composition, member) => ({
    changed: true, composition: { ...composition, members: composition.members.map((entry) => entry === member ? { ...entry, flipped: !entry.flipped } : entry) },
  }));
  const moveLocalFragmentToOtherLane = (host, store, context) => edit(host, store, context, "move-members",
    (composition, member) => moveSubviewCompositionMembers(composition, [member.entityKey], member.lane === "top" ? "bottom" : "top"));
  const mergeLocalFragment = (host, store, context, side) => edit(host, store, context, "merge-fragments",
    (composition, member) => mergeLocalMember(composition, member.entityKey, side));
  async function openLocalContigSplit(host, store, context, { synchronize = false } = {}) {
    const state = store.getState(), resolved = resolveLocalFragmentContext(state, host, context);
    if (!resolved || resolved.member.lengthBp < 2) return false;
    const { member } = resolved, range = memberSourceInterval(member);
    const model = { assemblyCtgId: member.assemblyCtgId, name: member.label,
      sourceStart: range.sourceStart, sourceEnd: range.sourceEnd,
      orient: memberEffectiveOrientation(member), hits: [], refLength: 0 };
    return deps.openManualContigSplit(host, model, { locale: state.locale,
      isCurrent: () => sameContext(store, state),
      commit: async ({ cutAfter }) => {
        if (!sameContext(store, state)) throw new Error(labels(state).stale);
        if (synchronize) {
          if (!deps.synchronizeLocalFragment) throw new Error(labels(state).syncPending);
          return deps.synchronizeLocalFragment(host, store, context, { action: "split", cutAfter });
        }
        const result = splitLocalMember(resolved.composition, member.entityKey, cutAfter);
        return result.changed ? commit(host, store, state, result.composition, "split-contig") : false;
      },
    });
  }
  return { deleteLocalFragment, flipLocalFragment, moveLocalFragmentToOtherLane, mergeLocalFragment, openLocalContigSplit };
}
