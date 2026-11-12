// Session-only presentation state. Never write this into project files or
// localStorage; changing datasets/models must not change scientific metadata.
const sessions = new Map();
export function projectPreviewSession(key) {
  if (!sessions.has(key)) sessions.set(key, { expanded: new Set(), scrollTop: 0, scrollLeft: 0 });
  return sessions.get(key);
}
export function toggleProjectPreviewChromosome(key, chrName) {
  const session = projectPreviewSession(key);
  if (session.expanded.has(chrName)) session.expanded.delete(chrName);
  else session.expanded.add(chrName);
  return session.expanded.has(chrName);
}
