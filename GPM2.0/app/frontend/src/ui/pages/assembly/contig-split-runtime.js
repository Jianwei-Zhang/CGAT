import { splitCopy } from "./contig-split-boundary.js";
import { chrAlignmentCopy } from "./contig-chr-alignments.js";
import { resolveMainViewHistoryAfterMutation } from "./main-view-history-state.js";

// A source edit reloads state without replacing the whole page. Commit all
// three mounted surfaces only after the new native IDs and evidence are ready.
export function createAssemblyContigSplitRuntime(deps) {
  return async function commitAssemblyContigSplit(host, store, action, args, doneMessage = null) {
    const state = store.getState();
    if (state.assembly?.mainViewHistory?.inFlight || state.assembly?.loading) return false;
    const labels = splitCopy[state.locale === "en" ? "en" : "zh"];
    const payload = { workspaceRoot: state.session.workspacePath, projectId: state.session.projectId,
      chrName: state.assembly.selectedChrName, action, args };
    store.setState({ assembly: { ...state.assembly, mainViewHistory: { ...state.assembly.mainViewHistory, inFlight: true } } });
    try {
      const summary = state.assembly.subview?.summary;
      const splitsMain = action === "split-manual-contig" || (action === "edit-local-fragment" && args?.action === "split");
      if (splitsMain && summary && summary.mode !== "composition") {
        // Capture legacy pair/track geometry while the parent IDs still exist.
        // Otherwise a two-contig view cannot resolve a retired parent at reload.
        const prepared = deps.prepareSourceOwnedSubviewHistory(state, host, {
          preserveLegacy: true,
          viewport: deps.resolveCurrentSubviewCompositionViewport(state, host),
          projectHistorical: deps.projectHistorical,
        });
        store.setState({ assembly: { ...prepared, mainViewHistory: store.getState().assembly.mainViewHistory } });
      }
      await deps.flushAssemblyProjectState(host, store);
      if (store.getState().session.workspacePath !== payload.workspaceRoot || store.getState().session.projectId !== payload.projectId
        || store.getState().assembly.selectedChrName !== payload.chrName) return false;
      return await deps.runSerializedProjectViewMutation(store, async (isCurrent) => {
        if (!isCurrent() || store.getState().assembly.selectedChrName !== payload.chrName) return false;
        const result = await deps.runMainViewEditorAction(payload);
        if (!isCurrent()) return false;
        await deps.loadAssemblyView(host, store, { keepCurrentChr: true, keepCurrentCtg: false,
          renderLoading: false, renderResult: false });
        if (!isCurrent()) return false;
        await deps.refreshSubviewPairwiseEvidence(host, store, { rerenderLoading: false, rerenderLoaded: false });
        if (!isCurrent()) return false;
        store.setState({ assembly: { ...store.getState().assembly,
          mainViewHistory: resolveMainViewHistoryAfterMutation(store.getState().assembly.mainViewHistory, result.status, payload.chrName),
          trackSelectedCtgIds: [], actionError: "", actionStatus: action === "add-contig-to-chr" && !result.changed
            ? chrAlignmentCopy[state.locale === "en" ? "en" : "zh"].existing : doneMessage || labels.done } });
        deps.rerenderAssemblyMainTab(host, store);
        deps.rerenderSubviewPanel(host, store);
        deps.rerenderFinalPathCard(host, store);
        return action === "add-contig-to-chr" ? result : true;
      });
    } catch (error) {
      deps.setAssemblyActionFeedback(host, store, { actionError: String(error.message || error) }); return false;
    } finally {
      if (store.getState().session.workspacePath === payload.workspaceRoot && store.getState().session.projectId === payload.projectId) {
        store.setState({ assembly: { ...store.getState().assembly,
          mainViewHistory: { ...store.getState().assembly.mainViewHistory, inFlight: false } } });
      }
    }
  };
}
