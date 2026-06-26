const STORAGE_PREFIX = "gpm_next:assembly-support-ds";

export function buildSupportDsStorageKey(workspacePath, projectId) {
  const normalizedWorkspacePath = normalizeWorkspacePath(workspacePath);
  const normalizedProjectId = normalizeId(projectId);
  if (!normalizedWorkspacePath || normalizedProjectId === null) {
    return "";
  }
  return `${STORAGE_PREFIX}:${normalizedWorkspacePath}:${normalizedProjectId}`;
}

export function loadSupportDsState(workspacePath, projectId, storage = getDefaultStorage()) {
  const storageKey = buildSupportDsStorageKey(workspacePath, projectId);
  if (!storageKey || !storage) {
    return null;
  }

  try {
    const raw = storage.getItem(storageKey);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    const supportDatasetId = normalizeId(parsed?.supportDatasetId);
    if (supportDatasetId === null) {
      return null;
    }
    return { supportDatasetId };
  } catch {
    return null;
  }
}

export function saveSupportDsState(workspacePath, projectId, supportState, storage = getDefaultStorage()) {
  const storageKey = buildSupportDsStorageKey(workspacePath, projectId);
  if (!storageKey || !storage) {
    return;
  }

  try {
    const supportDatasetId = normalizeId(supportState?.supportDatasetId);
    if (supportDatasetId === null) {
      storage.removeItem(storageKey);
      return;
    }
    storage.setItem(storageKey, JSON.stringify({ supportDatasetId }));
  } catch {
    // ignore storage failures
  }
}

export function reconcileSupportDsSelection({
  workspacePath,
  projectId,
  currentSelection,
  candidateIds,
  storage = getDefaultStorage(),
}) {
  const normalizedCurrentSelection = normalizeId(currentSelection);
  const normalizedCandidateIds = normalizeCandidateIds(candidateIds);
  if (normalizedCurrentSelection === null) {
    return {
      supportDatasetId: null,
      invalidated: false,
    };
  }

  if (normalizedCandidateIds.has(normalizedCurrentSelection)) {
    return {
      supportDatasetId: normalizedCurrentSelection,
      invalidated: false,
    };
  }

  saveSupportDsState(workspacePath, projectId, { supportDatasetId: null }, storage);
  return {
    supportDatasetId: null,
    invalidated: true,
  };
}

function getDefaultStorage() {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}

function normalizeWorkspacePath(workspacePath) {
  return String(workspacePath || "").trim();
}

function normalizeId(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }
  return Math.trunc(parsed);
}

function normalizeCandidateIds(candidateIds) {
  const normalized = new Set();
  if (!candidateIds || typeof candidateIds[Symbol.iterator] !== "function") {
    return normalized;
  }
  for (const candidateId of candidateIds) {
    const normalizedCandidateId = normalizeId(candidateId);
    if (normalizedCandidateId !== null) {
      normalized.add(normalizedCandidateId);
    }
  }
  return normalized;
}
