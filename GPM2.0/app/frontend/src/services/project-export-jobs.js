// Runtime-only export ownership. A project switch must not cancel an output
// snapshot or let its progress overwrite another project's job/data surface.
const sessions = new WeakMap();
const running = new Set();
export function exportJobScope(state) {
  return JSON.stringify([String(state.session?.workspacePath || "").trim(), Number(state.session?.projectId || 0)]);
}
function jobs(store) {
  if (!sessions.has(store)) sessions.set(store, new Map());
  return sessions.get(store);
}
function trim(map) {
  // Never evict an unacknowledged error/result receipt. Only dismissed/closed
  // records are eligible for the bounded convenience cache.
  const completed = [...map].filter(([, owner]) => owner.job.status !== "running" && owner.job.open !== true);
  while (completed.length > 3) map.delete(completed.shift()[0]);
}
export function currentProjectExportJob(store) { return jobs(store).get(exportJobScope(store.getState()))?.job || null; }
export function beginProjectExportJob(store, state, job) {
  const map = jobs(store), key = exportJobScope(state);
  if (map.get(key)?.job.status === "running") return null;
  const owner = { key, job }; map.delete(key); map.set(key, owner); running.add(owner); trim(map); return owner;
}
export function ownsCurrentProjectExport(store, owner) {
  return owner.key === exportJobScope(store.getState()) && jobs(store).get(owner.key) === owner;
}
export function updateProjectExportJob(owner, job) {
  owner.job = job;
  if (job.status !== "running") running.delete(owner);
}
export function syncCurrentProjectExportJob(store, job) {
  const map = jobs(store), key = exportJobScope(store.getState()), owner = map.get(key);
  if (!owner) return;
  if (job) updateProjectExportJob(owner, job);
  else if (owner.job.status !== "running") map.delete(key);
}
export function finishProjectExportJob(store, owner) { running.delete(owner); trim(jobs(store)); }
export function hasRunningProjectExports() { return running.size > 0; }
