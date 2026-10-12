// In-flight mutation stamps complement transactional SQLite revisions. They
// prevent an earlier metadata response from racing a mutation in this session.
const epochs = new Map();
const savedPaths = new Map();
const mutations = new Set([
  "run_ctg_editor_action", "run_main_view_editor_action", "run_main_view_layout_action",
  "run_main_view_batch_delete", "execute_main_view_history_action", "undo_main_view_history", "redo_main_view_history", "reset_main_view_history", "restore_deleted_ctg",
  "bootstrap_project_assembly", "auto_assign_chr", "auto_orient_contigs", "auto_orient_contigs_for_dataset",
  "create_phased_chr_track", "delete_phased_chr_track", "add_ctg_to_phased_chr_track",
  "remove_phased_chr_track_item", "reorder_phased_chr_track_items", "flip_phased_chr_track_item",
  "update_project", "delete_project", "update_project_catalog", "import_add_dataset_package", "import_add_ctg_package",
]);

export function previewSemanticSignature(value) {
  return JSON.stringify(value, function(key, item) {
    if (key === "updatedAt") return undefined;
    if (item && typeof item === "object" && !Array.isArray(item)) {
      return Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]]));
    }
    return item;
  });
}

function keys(args) {
  const request = args?.request || args || {};
  const workspace = String(request.workspaceRoot || "").trim();
  const project = Number(request.projectId || 0);
  return { workspace, key: workspace && project > 0 ? JSON.stringify([workspace, project]) : "" };
}

export function previewMutationStamp(args) {
  const { workspace, key } = keys(args);
  return `${epochs.get(workspace) || 0}:${epochs.get(key) || 0}`;
}

export function beginPreviewContentOperation(command, args) {
  const identity = keys(args);
  const paths = command === "update_project_assembly_view_state"
    ? previewSemanticSignature(args?.request?.finalPathByChr || {}) : null;
  const dirty = mutations.has(command) || (paths !== null && savedPaths.get(identity.key) !== paths);
  const key = identity.key || identity.workspace;
  if (dirty && key) epochs.set(key, (epochs.get(key) || 0) + 1);
  return { ...identity, dirty, paths };
}

export function finishPreviewContentOperation(operation, command, result, success) {
  const key = operation.key || operation.workspace;
  if (operation.dirty && key) epochs.set(key, (epochs.get(key) || 0) + 1);
  if (success && operation.key && ["get_project_assembly_view_state", "update_project_assembly_view_state"].includes(command)) {
    savedPaths.set(operation.key, previewSemanticSignature(result?.finalPathByChr || {}));
  }
}
