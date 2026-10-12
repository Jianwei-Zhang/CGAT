import test from "node:test";
import assert from "node:assert/strict";
import { createTauriTransport } from "../workflow/tauri-transport.js";
import { beginPreviewContentOperation, finishPreviewContentOperation, previewMutationStamp } from "../preview-content-events.js";

test("pure viewport save is not a content notification but a path edit is", () => {
  const args = { workspaceRoot: "/content-event-test", projectId: 1 };
  const saved = { finalPathByChr: { Chr1: { segments: [], updatedAt: "a" } } };
  const read = beginPreviewContentOperation("get_project_assembly_view_state", args);
  finishPreviewContentOperation(read, "get_project_assembly_view_state", saved, true);
  const before = previewMutationStamp(args);
  const pure = beginPreviewContentOperation("update_project_assembly_view_state", { request: { ...args,
    finalPathByChr: { Chr1: { segments: [], updatedAt: "b" } }, trackScrollState: { left: 4 } } });
  assert.equal(pure.dirty, false);
  assert.equal(previewMutationStamp(args), before);
  const changed = beginPreviewContentOperation("update_project_assembly_view_state", { request: { ...args,
    finalPathByChr: { Chr1: { segments: [{ type: "gap", gapSizeBp: 1 }] } } } });
  assert.notEqual(previewMutationStamp(args), before);
  const pending = previewMutationStamp(args);
  finishPreviewContentOperation(changed, "update_project_assembly_view_state", {}, false);
  assert.notEqual(previewMutationStamp(args), pending);
});


test("cache bridge uses native argument contracts and does not mutate content stamps", async () => {
  const args = { workspaceRoot: "/native-cache-contract", projectId: 1, modelVersion: 2 };
  const calls = [];
  const transport = createTauriTransport({ invoke: async (command, payload) => { calls.push([command, payload]); return { stored: true }; } });
  const before = previewMutationStamp(args);
  await transport.getProjectPreviewCache(args);
  await transport.putProjectPreviewCache({ ...args, expectedIdentity: "id", expectedRevision: 0, payload: {} });
  assert.equal(calls[0][0], "get_project_preview_cache");
  assert.deepEqual(calls[0][1], args);
  assert.equal(calls[1][0], "put_project_preview_cache");
  assert.equal(calls[1][1].request.modelVersion, 2);
  assert.equal(previewMutationStamp(args), before);
});

test("native mutations stamp both start and completion including undo and failed edits", async () => {
  const args = { workspaceRoot: "/native-mutation-contract", projectId: 1 };
  for (const command of ["run_ctg_editor_action", "undo_main_view_history", "redo_main_view_history",
    "create_phased_chr_track", "import_add_ctg_package"]) {
    const before = previewMutationStamp(args);
    const operation = beginPreviewContentOperation(command, args);
    const pending = previewMutationStamp(args);
    assert.notEqual(pending, before, command);
    finishPreviewContentOperation(operation, command, null, false);
    assert.notEqual(previewMutationStamp(args), pending, command);
  }
});
