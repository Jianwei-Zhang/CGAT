// Session-only presentation state for the Home / Project Overview page.
// Never writes into project files or localStorage.

const sessions = new Map();

export function overviewSectionProjectKey(state) {
  const workspacePath = String(state?.session?.workspacePath || "").trim();
  const projectId = Number(state?.session?.projectId || 0);
  if (!workspacePath || !Number.isFinite(projectId) || projectId <= 0) {
    return "";
  }
  return `${workspacePath}::${Math.trunc(projectId)}`;
}

export function overviewSectionsSession(key) {
  const normalized = String(key || "").trim();
  if (!normalized) {
    return { sections: {}, previewFilter: { query: "", gapsOnly: false } };
  }
  if (!sessions.has(normalized)) {
    sessions.set(normalized, {
      sections: {},
      previewFilter: { query: "", gapsOnly: false },
    });
  }
  return sessions.get(normalized);
}

export function isOverviewSectionExpanded(state, sectionName, { defaultExpanded = true, forceExpanded = false } = {}) {
  if (forceExpanded) return true;
  const key = overviewSectionProjectKey(state);
  if (!key) return Boolean(defaultExpanded);
  const override = overviewSectionsSession(key).sections[sectionName];
  return typeof override === "boolean" ? override : Boolean(defaultExpanded);
}

export function toggleOverviewSection(state, sectionName, { defaultExpanded = true } = {}) {
  const key = overviewSectionProjectKey(state);
  if (!key) return Boolean(defaultExpanded);
  const session = overviewSectionsSession(key);
  const current = typeof session.sections[sectionName] === "boolean"
    ? session.sections[sectionName]
    : Boolean(defaultExpanded);
  const next = !current;
  session.sections[sectionName] = next;
  return next;
}

export function resetOverviewSectionsSession(key) {
  if (key) sessions.delete(String(key));
  else sessions.clear();
}

export function getPreviewFilterState(key) {
  return overviewSectionsSession(key).previewFilter;
}

export function setPreviewFilterState(key, patch = {}) {
  const session = overviewSectionsSession(key);
  session.previewFilter = {
    query: patch.query !== undefined ? String(patch.query) : session.previewFilter.query,
    gapsOnly: patch.gapsOnly !== undefined ? Boolean(patch.gapsOnly) : session.previewFilter.gapsOnly,
  };
  return session.previewFilter;
}

export function cardHasGaps(card) {
  return (card?.paths || []).some(path => (path?.parts || []).some(part => Boolean(part?.gap)));
}

export function countCardGaps(card) {
  let count = 0;
  for (const path of card?.paths || []) {
    for (const part of path?.parts || []) {
      if (part?.gap) count += 1;
    }
  }
  return count;
}

export function filterPreviewCards(cards = [], filter = {}) {
  const query = String(filter?.query || "").trim().toLowerCase();
  const gapsOnly = Boolean(filter?.gapsOnly);
  if (!query && !gapsOnly) return cards;
  return cards.filter(card => {
    if (gapsOnly && !cardHasGaps(card)) return false;
    if (!query) return true;
    const chrMatch = String(card?.chrName || "").toLowerCase().includes(query);
    if (chrMatch) return true;
    return (card?.paths || []).some(path => String(path?.name || "").toLowerCase().includes(query));
  });
}
