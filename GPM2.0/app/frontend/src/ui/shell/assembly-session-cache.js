const DEFAULT_MAX_CACHE_ENTRIES = 3;

const assemblyStateCache = new Map();
const assemblyDomCache = new Map();

function normalizeWorkspacePath(value) {
  return String(value || "").trim();
}

function normalizeProjectId(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.trunc(numeric) : null;
}

function normalizeLocale(value) {
  return String(value || "").trim() === "en" ? "en" : "zh";
}

function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function resolveMaxEntries(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0
    ? Math.max(1, Math.trunc(numeric))
    : DEFAULT_MAX_CACHE_ENTRIES;
}

function touchEntry(map, key, value, maxEntries) {
  if (!key) {
    return false;
  }
  if (map.has(key)) {
    map.delete(key);
  }
  map.set(key, value);
  const limit = resolveMaxEntries(maxEntries);
  while (map.size > limit) {
    const oldestKey = map.keys().next().value;
    map.delete(oldestKey);
  }
  return true;
}

export function buildAssemblyCacheKey(stateOrSession) {
  const session = stateOrSession?.session || stateOrSession || {};
  const workspacePath = normalizeWorkspacePath(session.workspacePath);
  const projectId = normalizeProjectId(session.projectId);
  if (!workspacePath || !projectId) {
    return "";
  }
  return `${workspacePath}::${projectId}`;
}

export function buildAssemblyDomCacheKey(stateOrSession) {
  const baseKey = buildAssemblyCacheKey(stateOrSession);
  if (!baseKey) {
    return "";
  }
  return `${baseKey}::${normalizeLocale(stateOrSession?.locale)}`;
}

export function rememberAssemblyState(state, options = {}) {
  const key = buildAssemblyCacheKey(state);
  if (!key || !state?.assembly) {
    return false;
  }
  return touchEntry(
    assemblyStateCache,
    key,
    cloneValue({
      ...state.assembly,
      loading: false,
      bootstrapping: false,
    }),
    options.maxEntries,
  );
}

export function restoreAssemblyState(state, fallbackAssembly = {}) {
  const key = buildAssemblyCacheKey(state);
  if (!key || !assemblyStateCache.has(key)) {
    return cloneValue(fallbackAssembly);
  }
  const cached = assemblyStateCache.get(key);
  touchEntry(assemblyStateCache, key, cached, DEFAULT_MAX_CACHE_ENTRIES);
  return cloneValue(cached);
}

export function rememberAssemblyDom(host, state, options = {}) {
  const key = String(host?.dataset?.assemblyDomCacheKey || buildAssemblyDomCacheKey(state));
  const nodes = Array.from(host?.childNodes || []);
  if (!key || !nodes.length) {
    return false;
  }
  return touchEntry(assemblyDomCache, key, { nodes }, options.maxEntries);
}

export function restoreAssemblyDom(host, state) {
  const key = buildAssemblyDomCacheKey(state);
  const cached = key ? assemblyDomCache.get(key) : null;
  if (!host || !cached?.nodes?.length || typeof host.replaceChildren !== "function") {
    return false;
  }
  host.replaceChildren(...cached.nodes);
  if (host.dataset) {
    host.dataset.route = "assembly";
    host.dataset.assemblyDomCacheKey = key;
  }
  touchEntry(assemblyDomCache, key, cached, DEFAULT_MAX_CACHE_ENTRIES);
  return true;
}

export function clearAssemblySessionCache() {
  assemblyStateCache.clear();
  assemblyDomCache.clear();
}
