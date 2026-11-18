// Runtime-only navigation memory. Authoritative chromosome objects are always
// reloaded; this stores selection and viewing preferences, never database rows.
const sessions = new WeakMap();
const fields = ["trackView", "trackScrollState", "finalPathTrackScrollState", "selectedCtgId",
  "selectedMemberSeqId", "trackSelectedCtgIds", "selectedDeletedCtgRecordIds"];
const projectKey = state => JSON.stringify([state.session?.workspacePath, state.session?.projectId]);
const scopeKey = (state, chrName) => JSON.stringify([chrName, state.assembly?.supportDatasetId ?? null]);
function session(store, state) {
  const root = store.localViewRootStore || store;
  let cached = sessions.get(root);
  const key = projectKey(state);
  if (!cached || cached.key !== key) sessions.set(root, cached = { key, chromosomes: new Map() });
  return cached;
}
export function rememberChromosomeView(store, state = store.getState()) {
  const a = state.assembly;
  if (!a?.selectedChrName || a.loading) return;
  const snapshot = Object.fromEntries(fields.filter(key => a[key] !== undefined).map(key => [key, a[key]]));
  session(store, state).chromosomes.set(scopeKey(state, a.selectedChrName), snapshot);
}
export function restoreChromosomeView(store, chrName, state = store.getState()) {
  const snapshot = session(store, state).chromosomes.get(scopeKey(state, chrName));
  if (!snapshot) return null;
  if (!snapshot.trackView) return snapshot;
  // Hidden auxiliary objects are project data, not a viewing preference. Never
  // undo another chromosome's hide/restore by restoring an older prefs object.
  const { hiddenSupportCtgs: _hidden, ...prefs } = snapshot.trackView;
  const hidden = state.assembly?.trackView?.hiddenSupportCtgs;
  return { ...snapshot, trackView: { ...prefs, ...(hidden ? { hiddenSupportCtgs: hidden } : {}) } };
}
