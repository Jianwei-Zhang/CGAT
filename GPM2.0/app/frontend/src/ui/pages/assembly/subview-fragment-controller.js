import { getSubviewState } from "./subview-state.js";
import { projectCurrentSubviewToComposition, resolveCurrentSubviewCompositionViewport } from "./subview-composition-controller.js";
import { applySubviewComposition, moveSubviewCompositionMembers } from "./subview-composition-state.js";
import { commitSubviewCompositionHistoryOperation } from "./subview-history-state.js";
import { preserveSubviewRemovalViewport } from "./subview-removal-viewport.js";
import { isolateLocalMemberInterval, deleteLocalMember, splitLocalMember, mergeLocalMember,
  resolveLocalMergeNeighbor, memberSourceInterval, memberEffectiveOrientation } from "./subview-fragment-model.js";
import { localFragmentCopy } from "./subview-fragment-copy.js";

export function resolveLocalFragmentContext(state, host, context) {
  if (state?.assembly?.loading || state?.assembly?.mainViewHistory?.inFlight) return null;
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
    const isolated = isolateLocalMemberInterval(composition, member.entityKey, Number(context.start), Number(context.end));
    if (!isolated.member) return null;
    composition = isolated.composition; member = isolated.member;
  }
  return { composition, member };
}

export function resolveLocalFragmentMenu(state, host, context) {
  const resolved = resolveLocalFragmentContext(state, host, context);
  if (!resolved) return null;
  const { composition, member } = resolved;
  const primaryIds = new Set((state.assembly.chrCtgs || []).map((ctg) => Number(ctg.assemblyCtgId)));
  return { member, range: memberSourceInterval(member), canSplit: member.lengthBp > 1,
    canSync: member.source.role === "primary" && memberSourceInterval(member).parts.every((part) => primaryIds.has(part.assemblyCtgId)),
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
    const base = preserveSubviewRemovalViewport(store.getState().assembly, host, { viewport });
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
