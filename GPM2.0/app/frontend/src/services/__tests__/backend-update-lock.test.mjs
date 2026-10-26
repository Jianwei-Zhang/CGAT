import test from "node:test";
import assert from "node:assert/strict";
import { invokeCommand, getPendingBackendCommands } from "../backend-api.js";

test("native command tracking prevents install during work and resumes after failed install", async () => {
  const original = globalThis.window;
  const pending = new Map(); const calls = [];
  globalThis.window = { __TAURI__: { core: { invoke(command) {
    calls.push(command); return new Promise((resolve, reject) => pending.set(command, { resolve, reject }));
  } } } };
  try {
    const work = invokeCommand("export_final_path_fasta");
    assert.equal(getPendingBackendCommands(), 1);
    await assert.rejects(invokeCommand("app_update_install"), /update_work_busy/);
    pending.get("export_final_path_fasta").resolve(); await work;
    assert.equal(getPendingBackendCommands(), 0);
    const install = invokeCommand("app_update_install");
    await assert.rejects(invokeCommand("update_project_assembly_view_state"), /update_work_busy/);
    await assert.rejects(invokeCommand("app_update_install"), /update_work_busy/);
    pending.get("app_update_install").reject(new Error("install failed"));
    await assert.rejects(install, /install failed/);
    const retry = invokeCommand("update_project_assembly_view_state");
    pending.get("update_project_assembly_view_state").reject(new Error("save failed"));
    await assert.rejects(retry, /save failed/); assert.equal(getPendingBackendCommands(), 0);
    assert.deepEqual(calls, ["export_final_path_fasta", "app_update_install", "update_project_assembly_view_state"]);
  } finally { globalThis.window = original; }
});
