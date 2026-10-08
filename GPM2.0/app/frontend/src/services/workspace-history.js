export const WORKSPACE_HISTORY_KEY = "gpm_next:workspace_history";

// Structural normalization only. Filesystem case/realpath equivalence is resolved
// by the native backend, not guessed by lowercasing case-sensitive directories.
export function workspacePathIdentity(value) {
  let path = String(value || "").trim();
  if (/^[a-z]:[\\/]/i.test(path) || path.startsWith("\\\\") || path.startsWith("//")) path = path.replace(/\\/g, "/");
  if (path.startsWith("//?/UNC/")) path = `//${path.slice(8)}`;
  else if (path.startsWith("//?/")) path = path.slice(4);
  return path.replace(/\/+$/, "") || (path.startsWith("/") ? "/" : "");
}

export function deduplicateWorkspaceHistory(records = []) {
  const next = [];
  const indices = new Map();
  for (const value of records) {
    const record = typeof value === "string" ? { path: value, lastUsedAt: 0 } : value;
    const path = typeof record?.path === "string" ? record.path.trim() : "";
    const key = workspacePathIdentity(path);
    if (!key) continue;
    const index = indices.get(key);
    if (index === undefined) {
      indices.set(key, next.length);
      next.push({ ...record, path });
    } else {
      // Preserve the first record's position and user metadata, retaining any
      // extra metadata that only exists on a duplicate legacy record.
      next[index] = { ...record, ...next[index] };
    }
  }
  return next.slice(-20);
}

export function readWorkspaceHistory(storage = globalThis.window?.localStorage) {
  try {
    const records = JSON.parse(storage?.getItem(WORKSPACE_HISTORY_KEY) || "[]");
    return Array.isArray(records) ? deduplicateWorkspaceHistory(records) : [];
  } catch { return []; }
}

export function writeWorkspaceHistory(records, storage = globalThis.window?.localStorage) {
  try { storage?.setItem(WORKSPACE_HISTORY_KEY, JSON.stringify(deduplicateWorkspaceHistory(records))); }
  catch { /* The workspace can still open when storage is unavailable. */ }
}

export function updateWorkspaceHistory(records = [], workspacePath, projectName = "", lastUsedAt = Date.now()) {
  const next = deduplicateWorkspaceHistory(records);
  const path = String(workspacePath || "").trim();
  const key = workspacePathIdentity(path);
  if (!key) return next;
  const index = next.findIndex(record => workspacePathIdentity(record.path) === key);
  if (index < 0) next.push({ path, projectName: String(projectName || ""), lastUsedAt });
  else next[index] = { ...next[index], path,
    projectName: String(projectName || next[index].projectName || ""), lastUsedAt };
  return next.slice(-20);
}

export function reconcileWorkspaceHistory(workspacePath, aliases = [], storage = globalThis.window?.localStorage) {
  const keys = new Set([workspacePath, ...aliases].map(workspacePathIdentity));
  const records = readWorkspaceHistory(storage).map(record => keys.has(workspacePathIdentity(record.path))
    ? { ...record, path: workspacePath } : record);
  writeWorkspaceHistory(records, storage);
}
