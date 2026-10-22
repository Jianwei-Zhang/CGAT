import { createStore } from "../../state/store.js";
import { loadProjectPreviewData } from "./project-preview-page.js";
import { previewSession, rememberPreviewEntry } from "./project-preview-cache.js";
import { previewProjectKey } from "./project-preview-state.js";

// Prepare saved content without changing the active project, route, DOM, or
// inheriting unsaved Assembly edits from the project open before this import.
// Reuse the normal loader so revision checks, model versions, persistence and
// stale-publication protection cannot diverge between import and Preview.
export async function prepareProjectPreviewData(store, { workspaceRoot, project, datasets }, deps = {}, options = {}) {
  const previewStore = createStore({
    locale: store.getState().locale,
    activeRoute: "importer",
    session: { workspacePath: workspaceRoot, projectId: project.projectId },
    initializer: { existingProjects: [project], datasets: datasets || [] },
    assembly: { finalPathByChr: {} },
  });
  const key = previewProjectKey(previewStore.getState());
  const previous = previewSession(store).entries.get(key);
  if (previous) rememberPreviewEntry(previewStore, key, previous);
  const loaded = await loadProjectPreviewData(null, previewStore, deps, {
    background: true, shouldContinue: options.shouldContinue,
  });
  if (!loaded) return null;
  const entry = previewSession(previewStore).entries.get(key);
  rememberPreviewEntry(store, key, entry);
  return previewStore.getState().projectPreview;
}
