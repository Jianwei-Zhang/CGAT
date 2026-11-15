import { readWorkspaceHistory, workspacePathIdentity, WORKSPACE_HISTORY_KEY } from "./workspace-history.js";

export const PROJECT_LIBRARY_KEY = "gpm_next:project_library:v1";
const empty = () => ({ version: 1, partitions: [], collapsed: [] });
const storageDefault = () => globalThis.window?.localStorage;

export function validateLibrary(library) {
  if (library?.version !== 1 || !Array.isArray(library.partitions) || !Array.isArray(library.collapsed)) throw new Error("storage");
  const nodes = new Map();
  for (const node of library.partitions) {
    if (!node || typeof node.id !== "string" || !node.id || nodes.has(node.id)
      || typeof node.name !== "string" || !node.name.trim() || typeof node.parentId !== "string") throw new Error("storage");
    nodes.set(node.id, node);
  }
  for (const node of nodes.values()) {
    const seen = new Set([node.id]);
    let parent = node.parentId;
    while (parent) {
      if (!nodes.has(parent) || seen.has(parent)) throw new Error("storage");
      seen.add(parent); parent = nodes.get(parent).parentId;
    }
  }
  return library;
}

// Corrupt/unavailable storage must not be overwritten by an empty library.
export function readProjectLibrary(storage) {
  try {
    storage ??= storageDefault();
    const raw = storage?.getItem(PROJECT_LIBRARY_KEY);
    return raw ? validateLibrary(JSON.parse(raw)) : empty();
  } catch { return { ...empty(), error: "storage" }; }
}

export function saveProjectLibrary(library, storage) {
  if (library.error) throw new Error("storage");
  validateLibrary(library);
  try {
    storage ??= storageDefault();
    if (!storage) throw new Error("storage");
    storage.setItem(PROJECT_LIBRARY_KEY, JSON.stringify(library));
  } catch { throw new Error("storage"); }
}

export function partitionAncestors(library, id) {
  const nodes = new Map(library.partitions.map(node => [node.id, node]));
  const result = [], seen = new Set();
  while (id && nodes.has(id) && !seen.has(id)) {
    seen.add(id); result.unshift(nodes.get(id)); id = nodes.get(id).parentId;
  }
  return result;
}

export function partitionChoices(library, excludeId = "") {
  const result = [];
  const visit = (parentId, depth, prefix) => {
    library.partitions.filter(node => node.parentId === parentId && node.id !== excludeId)
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
      .forEach(node => {
        const path = [...prefix, node.name];
        result.push({ ...node, depth, path: path.join(" / ") });
        visit(node.id, depth + 1, path);
      });
  };
  visit("", 0, []);
  return result;
}

export function editPartition(library, { id = "", name, parentId = "" }) {
  if (library.error) throw new Error("storage");
  const current = id ? library.partitions.find(node => node.id === id) : null;
  if (id && !current) throw new Error("missing");
  name = String(name ?? current?.name ?? "").trim();
  if (!name || name.length > 120) throw new Error("name");
  if (parentId && !library.partitions.some(node => node.id === parentId)) throw new Error("missing");
  if (id && partitionAncestors(library, parentId).some(node => node.id === id)) throw new Error("cycle");
  if (library.partitions.some(node => node.id !== id && node.parentId === parentId && node.name === name)) throw new Error("duplicate");
  const node = { id: id || globalThis.crypto.randomUUID(), name, parentId };
  return { ...library, partitions: current ? library.partitions.map(item => item.id === id ? node : item) : [...library.partitions, node] };
}

export function partitionDeletionImpact(library, id, records = []) {
  if (library.error) throw new Error("storage");
  if (!id || !library.partitions.some(node => node.id === id)) throw new Error("missing");
  const children = new Map();
  for (const node of library.partitions) {
    if (!children.has(node.parentId)) children.set(node.parentId, []);
    children.get(node.parentId).push(node.id);
  }
  const ids = new Set(), pending = [id];
  while (pending.length) {
    const current = pending.pop();
    if (ids.has(current)) continue;
    ids.add(current);
    pending.push(...children.get(current) || []);
  }
  return { ids: [...ids], projectCount: records.filter(record => ids.has(record.partitionId)).length };
}

export function deletePartition(library, id, records = []) {
  const impact = partitionDeletionImpact(library, id, records);
  const removed = new Set(impact.ids);
  // Commit just the partition registry. projectPartition() resolves deleted IDs to
  // unpartitioned, so projects move atomically with this one storage write. Never
  // rewrite the separate project inventory or risk losing metadata on a partial save.
  return { ...library, partitions: library.partitions.filter(node => !removed.has(node.id)),
    collapsed: library.collapsed.filter(value => !removed.has(value) && !(value === "" && impact.projectCount)) };
}

export function projectPartition(library, record) {
  return library.partitions.some(node => node.id === record.partitionId) ? record.partitionId : "";
}

export function moveProjectToPartition(path, partitionId, storage) {
  storage ??= storageDefault();
  const library = readProjectLibrary(storage);
  if (library.error) throw new Error("storage");
  if (partitionId && !library.partitions.some(node => node.id === partitionId)) throw new Error("missing");
  const records = readWorkspaceHistory(storage);
  const key = workspacePathIdentity(path);
  if (!records.some(record => workspacePathIdentity(record.path) === key)) throw new Error("missing");
  const next = records.map(record => workspacePathIdentity(record.path) === key ? { ...record, partitionId } : record);
  try {
    if (!storage) throw new Error("storage");
    storage.setItem(WORKSPACE_HISTORY_KEY, JSON.stringify(next));
  } catch { throw new Error("storage"); }
}

export function revealProjectPartition(path, storage) {
  const library = readProjectLibrary(storage);
  if (library.error) return false;
  const record = readWorkspaceHistory(storage).find(item => workspacePathIdentity(item.path) === workspacePathIdentity(path));
  if (!record) return false;
  const id = projectPartition(library, record);
  const ancestors = new Set(id ? partitionAncestors(library, id).map(node => node.id) : [""]);
  const collapsed = library.collapsed.filter(value => !ancestors.has(value));
  if (collapsed.length === library.collapsed.length) return false;
  saveProjectLibrary({ ...library, collapsed }, storage);
  return true;
}
