import { resolveLocalFragmentContext, resolveLocalFragmentMenu } from "./subview-fragment-controller.js";
import { prepareSourceOwnedSubviewHistory } from "./subview-fragment-history.js";
import { resolveCurrentSubviewCompositionViewport } from "./subview-composition-controller.js";
import { reconcileLocalCompositionWithMain } from "./subview-fragment-reconcile.js";
import { memberSourceInterval, memberActiveBackingParts, deleteLocalMember, splitLocalMember } from "./subview-fragment-model.js";
import { applySubviewComposition } from "./subview-composition-state.js";
import { commitSubviewCompositionHistoryOperation } from "./subview-history-state.js";
import { preserveSubviewRemovalViewport } from "./subview-removal-viewport.js";
import { resolveMainViewHistoryAfterMutation } from "./main-view-history-state.js";
import { localFragmentCopy } from "./subview-fragment-copy.js";

const sameIdentity = (a, b) => a.session?.workspacePath === b.session?.workspacePath
  && a.session?.projectId === b.session?.projectId && a.assembly?.selectedChrName === b.assembly?.selectedChrName;
const editableKey = (subview) => JSON.stringify([subview?.summary, subview?.flippedCtgs, subview?.activeAnchors, subview?.manualAnchors]);

export function buildLocalFragmentSyncRequest(state, host, context, operation) {
  const resolved = resolveLocalFragmentContext(state, host, context);
  const menu = resolveLocalFragmentMenu(state, host, context);
  if (!resolved || !menu?.canSync || !["split", "delete"].includes(operation?.action)) return null;
  const range = memberSourceInterval(resolved.member);
  if (operation.action === "split" && (!Number.isSafeInteger(operation.cutAfter)
    || operation.cutAfter < range.sourceStart || operation.cutAfter >= range.sourceEnd)) return null;
  return { ...resolved, args: { action: operation.action, sourceStart: range.sourceStart, sourceEnd: range.sourceEnd,
    ...(operation.action === "split" ? { cutAfter: operation.cutAfter } : {}),
    targets: memberActiveBackingParts(resolved.member).map((part) => ({ ...part })),
  } };
}

function confirmation(state, request, impact) {
  const en = state.locale === "en", { sourceStart, sourceEnd, action, targets } = request.args;
  const counts = [impact?.finalPathReferenceCount, impact?.degapReferenceCount, impact?.phasedItemCount, impact?.exportRecordCount]
    .map((value) => Math.max(0, Number(value) || 0));
  return en
    ? `${action === "delete" ? "Delete" : "Split"} source interval ${sourceStart.toLocaleString()}–${sourceEnd.toLocaleString()} and synchronize ${targets.length} real Main View entity/entities?\nFinal Path references: ${counts[0]}; GRT/DeGap references: ${counts[1]}; phased items: ${counts[2]}; export records: ${counts[3]}.\nAlready-adopted DNA remains an immutable source interval in Final Path; it is not silently deleted. Main and Local Views each record one undo step. Local undo restores only the local presentation.`
    : `确认${action === "delete" ? "删除" : "分割"}源区间 ${sourceStart.toLocaleString()}–${sourceEnd.toLocaleString()}，并同步修改 ${targets.length} 个主视图真实实体吗？\nFinal Path 引用：${counts[0]}；GRT/DeGap 引用：${counts[1]}；单倍型条目：${counts[2]}；导出记录：${counts[3]}。\n已加入 Final Path 的 DNA 保留为不可变源区间，不会被静默删除。主视图与局部视图各记录一次回溯；局部撤销只恢复局部展示。`;
}

export function createSubviewFragmentSyncRuntime(deps) {
  return async function synchronizeLocalFragment(host, store, context, operation) {
    const before = store.getState(), request = buildLocalFragmentSyncRequest(before, host, context, operation);
    if (!request || !before.session?.workspacePath || !before.session?.projectId) return false;
    const labels = localFragmentCopy[before.locale === "en" ? "en" : "zh"];
    const sameBefore = () => sameIdentity(store.getState(), before)
      && store.getState().assembly.subview === before.assembly.subview
      && !store.getState().assembly.mainViewHistory?.inFlight && !store.getState().assembly.loading;
    const viewport = resolveCurrentSubviewCompositionViewport(before, host);
    let installed = null, nativeCommitted = false;
    try {
      const impact = await deps.inspectMainViewDelete({ workspaceRoot: before.session.workspacePath,
        projectId: before.session.projectId, chrName: before.assembly.selectedChrName,
        assemblyCtgIds: request.args.targets.map((part) => part.assemblyCtgId) });
      if (!sameBefore()) return false;
      if (!(await deps.confirm(confirmation(before, request, impact), { host, store, confirmationKey: `local-to-main-${operation.action}` }))) return false;
      if (!sameBefore()) return false;
      installed = prepareSourceOwnedSubviewHistory(before, host, { viewport,
        projectHistorical: (state) => deps.projectHistorical(state, host) });
      installed = preserveSubviewRemovalViewport(installed, host, { viewport });
      store.setState({ assembly: { ...installed,
        mainViewHistory: { ...installed.mainViewHistory, inFlight: true }, actionError: "" } });
      const stillInstalled = () => sameIdentity(store.getState(), before)
        && editableKey(store.getState().assembly.subview) === editableKey(installed.subview);
      await deps.flushBefore(host, store);
      if (!stillInstalled()) return false;
      const desired = operation.action === "split"
        ? splitLocalMember(request.composition, request.member.entityKey, operation.cutAfter)
        : deleteLocalMember(request.composition, request.member.entityKey);
      if (!desired.changed) return false;
      // A synchronized edit is two user-visible edits: keep the local
      // presentation edit in Local View history before Main owns its native
      // mutation. The native operation remains a separate Main history entry.
      const localBase = store.getState().assembly;
      const localNext = applySubviewComposition(localBase.subview, desired.composition, { trackPairSelectedCtgs: [] });
      const localCommitted = commitSubviewCompositionHistoryOperation(localBase, { nextSubview: localNext,
        viewport, operation: { kind: operation.action === "split" ? "split-contig" : "remove-members", count: 1 }, stateOrLocale: before });
      if (!localCommitted.changed) return false;
      store.setState({ assembly: { ...localCommitted.assembly,
        mainViewHistory: { ...localCommitted.assembly.mainViewHistory, inFlight: true } } });
      installed = store.getState().assembly;
      return await deps.serialize(store, async (isCurrent) => {
        if (!isCurrent() || !stillInstalled()) return false;
        try {
          const result = await deps.runMainViewEditorAction({ workspaceRoot: before.session.workspacePath,
            projectId: before.session.projectId, chrName: before.assembly.selectedChrName,
            action: "edit-local-fragment", args: request.args });
          nativeCommitted = result?.changed === true;
          if (!isCurrent() || !sameIdentity(store.getState(), before)) return false;
          store.setState({ assembly: { ...store.getState().assembly,
            mainViewHistory: { ...resolveMainViewHistoryAfterMutation(store.getState().assembly.mainViewHistory,
              result.status, before.assembly.selectedChrName), inFlight: true } } });
          await deps.loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false, renderLoading: false });
          if (!isCurrent() || !sameIdentity(store.getState(), before)) return false;
          const latest = store.getState();
          if (latest.assembly.error) throw new Error(latest.assembly.error);
          const composition = reconcileLocalCompositionWithMain(desired.composition, latest.assembly.chrCtgs, latest.assembly.deletedCtgs);
          const historyKey = installed.subview.historyKey;
          const record = installed.subviewHistoryByKey?.[historyKey];
          if (!record) throw new Error("Local View history snapshot is missing");
          const oldDeletedIds = new Set((before.assembly.deletedCtgs || []).map((ctg) => Number(ctg.assemblyCtgId)));
          const recoverDeletedCtgIds = operation.action === "delete" ? (latest.assembly.deletedCtgs || [])
            .map((ctg) => Number(ctg.assemblyCtgId)).filter((id) => !oldDeletedIds.has(id)) : [];
          const rebind = (snapshot) => snapshot?.kind === "composition" ? { ...snapshot,
            composition: reconcileLocalCompositionWithMain(snapshot.composition, latest.assembly.chrCtgs,
              latest.assembly.deletedCtgs, { recoverDeletedCtgIds }),
          } : snapshot;
          // loadAssemblyView reads the pre-mutation persisted history. Never use
          // that older record as the source for this newly committed local edit.
          // Rebind the captured transaction history after native IDs are known.
          const nextSubview = applySubviewComposition(latest.assembly.subview, composition,
            { historyKey, trackPairSelectedCtgs: [] });
          const local = { assembly: { ...latest.assembly, subview: nextSubview,
            subviewCompositionViewport: installed.subviewCompositionViewport,
            subviewTrackView: installed.subviewTrackView,
            subviewHistoryByKey: { ...latest.assembly.subviewHistoryByKey,
              [historyKey]: { ...record, current: { kind: "composition", composition }, default: rebind(record.default),
                past: record.past.map((entry) => ({ ...entry, snapshot: rebind(entry.snapshot) })),
                forward: record.forward.map((entry) => ({ ...entry, snapshot: rebind(entry.snapshot) })),
              },
            },
          } };
          store.setState({ assembly: { ...local.assembly, subview: { ...local.assembly.subview, trackPairSelectedCtgs: [] },
            trackSelectedCtgIds: [], actionError: "", actionStatus: labels.syncDone } });
          await deps.persistNow(host, store);
          if (!isCurrent() || !sameIdentity(store.getState(), before)) return false;
          store.setState({ assembly: { ...store.getState().assembly,
            mainViewHistory: { ...store.getState().assembly.mainViewHistory, inFlight: false } } });
          deps.rerenderMain(host, store); deps.rerenderSubviewPanel(host, store);
          deps.refreshSubviewPairwiseEvidence?.(host, store);
          return true;
        } catch (error) {
          if (isCurrent() && sameIdentity(store.getState(), before) && !nativeCommitted) {
            restoreLocalState(store, before);
            await deps.persistNow(host, store);
          }
          throw error;
        }
      });
    } catch (error) {
      if (!sameIdentity(store.getState(), before)) return false;
      if (installed && !nativeCommitted) restoreLocalState(store, before);
      store.setState({ assembly: { ...store.getState().assembly,
        sourceEditingReloadRequired: nativeCommitted || store.getState().assembly.sourceEditingReloadRequired,
        actionError: `${nativeCommitted ? labels.syncRefreshFailed + " " : ""}${String(error?.message || error)}`,
        actionStatus: "" } });
      deps.rerenderMain(host, store); deps.rerenderSubviewPanel(host, store);
      return false;
    } finally {
      if (installed && sameIdentity(store.getState(), before) && store.getState().assembly.mainViewHistory?.inFlight) {
        store.setState({ assembly: { ...store.getState().assembly,
          mainViewHistory: { ...store.getState().assembly.mainViewHistory, inFlight: false } } });
        deps.rerenderMain(host, store); deps.rerenderSubviewPanel(host, store);
      }
    }
  };
}

function restoreLocalState(store, before) {
  const latest = store.getState();
  const localKeys = ["subview", "subviewHistoryByKey", "subviewAnchorStateByKey", "subviewCompositionViewport",
    "subviewTrackView", "subviewTrackDragOffsets"];
  store.setState({ assembly: { ...latest.assembly,
    ...Object.fromEntries(localKeys.map((key) => [key, before.assembly[key]])) } });
}
