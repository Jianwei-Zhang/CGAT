import { missingSubviewReferenceEvidence } from "./reference-evidence-loading.js";
import { currentAssemblyViewRequest } from "./assembly-view-request.js";

// A task started from a resolved Promise still runs before paint. Wait for a
// frame and a subsequent task; hidden/detached WebViews get a bounded fallback.
export function afterAssemblyPaint(host) {
  const win = host?.ownerDocument?.defaultView;
  if (!win?.requestAnimationFrame) return Promise.resolve();
  return new Promise(resolve => {
    let frame, task, fallback;
    const done = () => {
      win.cancelAnimationFrame?.(frame);
      clearTimeout(task); clearTimeout(fallback); resolve();
    };
    fallback = setTimeout(done, 150);
    frame = win.requestAnimationFrame(() => { task = setTimeout(done, 0); });
  });
}

const details = new WeakMap();
function scopeGuard(store, state, request, table = details) {
  const view = currentAssemblyViewRequest(store);
  return () => {
    const next = store.getState();
    return table.get(store) === request && currentAssemblyViewRequest(store) === view
      && next.session?.workspacePath === state.session?.workspacePath
      && next.session?.projectId === state.session?.projectId
      && next.activeRoute === state.activeRoute
      && next.assembly?.selectedChrName === state.assembly?.selectedChrName;
  };
}

export async function hydrateAssemblyCtgDetail(host, store, deps, { afterPaint = false } = {}) {
  const state = store.getState(), id = state.assembly?.selectedCtgId;
  const request = { active: true }; details.set(store, request);
  const inScope = scopeGuard(store, state, request);
  const current = () => inScope() && store.getState().assembly?.selectedCtgId === id;
  request.current = current;
  if (!id) { request.active = false; return; }
  const refresh = () => (deps.patchSelection || deps.rerender)(host, store, { focus: false });
  try {
    if (afterPaint) await (deps.afterMainPaint || afterAssemblyPaint)(host);
    if (!current()) return;
    const { detail } = await deps.loadSideDataForCtg(state.session.workspacePath, state.session.projectId, id);
    if (!current()) return;
    const assembly = store.getState().assembly;
    const members = detail?.members || [];
    const memberId = members.some(member => member.assemblySeqId === assembly.selectedMemberSeqId)
      ? assembly.selectedMemberSeqId : members[0]?.assemblySeqId || null;
    store.setState({ assembly: { ...assembly, ctgDetail: detail, ctgDetailLoading: false,
      ctgDetailError: "", selectedMemberSeqId: memberId } });
  } catch (error) {
    if (!current()) return;
    store.setState({ assembly: { ...store.getState().assembly, ctgDetail: null, ctgDetailLoading: false,
      ctgDetailError: deps.mapAssemblyError({ error, stateOrLocale: store.getState() }).userMessage,
      selectedMemberSeqId: null } });
  } finally {
    request.active = false;
  }
  if (current()) refresh();
}

export function retryAssemblyCtgDetail(host, store, deps) {
  const state = store.getState();
  if ((state.activeRoute && state.activeRoute !== "assembly") || state.assembly?.loading || !state.assembly?.selectedCtgId) return;
  store.setState({ assembly: { ...state.assembly, ctgDetail: null, ctgDetailLoading: true,
    ctgDetailError: "", selectedMemberSeqId: null } });
  (deps.patchSelection || deps.rerender)(host, store, { focus: false });
  return hydrateAssemblyCtgDetail(host, store, deps, { afterPaint: true });
}

const local = new WeakMap();
export async function restoreAssemblyLocalEvidence(host, store, deps, { afterPaint = false } = {}) {
  const state = store.getState(), summary = state.assembly?.subview?.summary;
  if (!summary || typeof deps.refreshSubviewPairwiseEvidence !== "function") return;
  const request = { active: true }; local.set(store, request);
  const inScope = scopeGuard(store, state, request, local);
  const current = () => inScope() && store.getState().assembly?.subview?.summary === summary;
  request.current = current;
  try {
    if (afterPaint) await (deps.afterMainPaint || afterAssemblyPaint)(host);
    if (!current()) {
      if (inScope()) store.setState({ assembly: { ...store.getState().assembly,
        subviewRestoring: false, subviewRestoringSummary: null, subviewRestoreError: "" } });
      return;
    }
    await deps.refreshSubviewPairwiseEvidence(host, store, { rerenderLoading: false, rerenderLoaded: false });
    if (!inScope()) return;
    const assembly = store.getState().assembly;
    const evidence = assembly.subview?.pairwiseEvidence;
    const failed = current() && evidence?.status === "error";
    const errorMessage = failed
      ? evidence.error?.userMessage || (typeof evidence.error === "string" && evidence.error)
        || deps.mapAssemblyError({ error: evidence.error, stateOrLocale: store.getState() }).userMessage
      : "";
    store.setState({ assembly: { ...assembly, subviewRestoring: false,
      subviewRestoringSummary: failed ? summary : null, subviewRestoreError: errorMessage } });
  } catch (error) {
    if (!inScope()) return;
    store.setState({ assembly: { ...store.getState().assembly, subviewRestoring: false,
      subviewRestoringSummary: current() ? summary : null,
      subviewRestoreError: current() ? deps.mapAssemblyError({ error, stateOrLocale: store.getState() }).userMessage : "" } });
  } finally {
    request.active = false;
  }
  if (inScope()) (deps.patchSubview || deps.rerender)(host, store);
}

// Route/project caches can retain a loading placeholder after an off-route
// response was correctly discarded. Resume only abandoned stages on entry;
// rebinding while a current request is active must not duplicate its query.
export function resumeAssemblyReadyStages(host, store, deps) {
  const state = store.getState(), assembly = state.assembly || {};
  if (state.activeRoute !== "assembly" || assembly.loading) return Promise.resolve([]);
  const tasks = [];
  const detail = details.get(store);
  if (assembly.ctgDetailLoading && !(detail?.active && detail.current())) {
    tasks.push(hydrateAssemblyCtgDetail(host, store, deps, { afterPaint: true }));
  }
  const evidence = local.get(store);
  const rawMissing=missingSubviewReferenceEvidence(assembly);
  const resumeRaw=rawMissing.some(member=>member.referenceEvidence?.status !== "error");
  if (((assembly.subviewRestoring && assembly.subviewRestoringSummary === assembly.subview?.summary) || resumeRaw)
    && !(evidence?.active && evidence.current())) {
    // A discarded request must not be mistaken for a still-running controller
    // request merely because its cached evidence has status=loading.
    if (assembly.subview?.pairwiseEvidence?.status === "loading") {
      const latest = store.getState().assembly;
      store.setState({ assembly: { ...latest, subview: { ...latest.subview,
        pairwiseEvidence: { ...latest.subview.pairwiseEvidence, status: "idle", requestKey: "" },
      } } });
    }
    tasks.push(restoreAssemblyLocalEvidence(host, store, deps, { afterPaint: true }));
  }
  return Promise.all(tasks);
}
