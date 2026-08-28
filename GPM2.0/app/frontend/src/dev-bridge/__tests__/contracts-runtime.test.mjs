import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";

import { createBackendOperations } from "../backend-operations.js";
import { runBackendCommand } from "../backend-runtime.js";
import {
  applyListLimit,
  classifyBridgeErrorCode,
  normalizeToken,
  parseJsonLine,
  parseKeyValueLines,
  requireNumber,
  requireString,
} from "../contracts.js";

function createChildProcess() {
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  return child;
}

test("shared dev bridge contracts validate and normalize boundary values", () => {
  assert.doesNotThrow(() => requireString("workspaceRoot", "D:/workspace"));
  assert.throws(() => requireString("workspaceRoot", "  "), /missing required field/);
  assert.doesNotThrow(() => requireNumber("projectId", 0));
  assert.throws(() => requireNumber("projectId", "1"), /missing required number field/);
  assert.equal(normalizeToken("NULL"), null);
  assert.equal(normalizeToken("-12"), -12);
  assert.equal(normalizeToken("Chr01"), "Chr01");
  assert.deepEqual(applyListLimit([1, 2, 3], 2), [1, 2]);
  assert.deepEqual(applyListLimit([1, 2, 3], -1), [1, 2, 3]);
  assert.equal(classifyBridgeErrorCode("GRT_IMPORT_INVALID_JSON: bad recipe"), "GRT_IMPORT_INVALID_JSON");
  assert.equal(classifyBridgeErrorCode("project_id 7 does not exist"), "NOT_FOUND");
  assert.equal(classifyBridgeErrorCode("project name already exists"), "STATE_CONFLICT");
});

test("shared stdout parsers preserve spaced values and reject malformed JSON lines", () => {
  const record = parseKeyValueLines([
    "stage=validate detail=ignored",
    "project_id=12 project_name=Genome Project support_dataset_ids=2,3",
  ].join("\n"));

  assert.deepEqual(record, {
    project_id: "12",
    project_name: "Genome Project",
    support_dataset_ids: "2,3",
  });
  assert.deepEqual(parseJsonLine('json={"ok":true}\n', "json"), { ok: true });
  assert.throws(() => parseJsonLine("json={", "json"), /invalid json/);
  assert.throws(() => parseJsonLine("other={}", "json"), /missing json/);
});

test("backend process runner forwards executable, args, cwd and output", async () => {
  const child = createChildProcess();
  let spawnCall = null;
  const promise = runBackendCommand({
    args: ["list-project-chromosomes", "D:/workspace", "7"],
    backendExe: "D:/bin/gpm_next_backend.exe",
    cwd: "D:/repo/app",
    env: { GPM_TEST: "1" },
    spawnProcess(executable, args, options) {
      spawnCall = { executable, args, options };
      return child;
    },
  });

  child.stdout.emit("data", Buffer.from("chr id=1\n"));
  child.stderr.emit("data", Buffer.from("diagnostic\n"));
  child.emit("close", 0);

  assert.deepEqual(await promise, {
    stdout: "chr id=1\n",
    stderr: "diagnostic\n",
  });
  assert.deepEqual(spawnCall, {
    executable: "D:/bin/gpm_next_backend.exe",
    args: ["list-project-chromosomes", "D:/workspace", "7"],
    options: {
      cwd: "D:/repo/app",
      stdio: ["ignore", "pipe", "pipe"],
      env: { GPM_TEST: "1" },
    },
  });
});

test("backend process runner exposes non-zero status and stderr diagnostics", async () => {
  const child = createChildProcess();
  const promise = runBackendCommand({
    args: ["open-workspace", "D:/missing"],
    backendExe: "backend.exe",
    cwd: "D:/repo/app",
    spawnProcess() {
      return child;
    },
  });

  child.stderr.emit("data", Buffer.from("workspace not found"));
  child.emit("close", 3);

  await assert.rejects(
    promise,
    /backend command failed \(code=3\)[\s\S]*open-workspace D:\/missing[\s\S]*workspace not found/,
  );
});

test("operation factory exposes every registered operation and maps exact CLI contracts", async () => {
  const calls = [];
  const handlers = createBackendOperations({
    async runBackend(args) {
      calls.push(args);
      if (args[0] === "list-new-sequences") {
        return {
          stdout: [
            "sequence assembly_seq_id=8 dataset=flye seq=ctg8 len=1200 hidden=false",
            "sequence assembly_seq_id=9 dataset=flye seq=ctg9 len=800 hidden=true",
          ].join("\n"),
          stderr: "",
        };
      }
      if (args[0] === "get-runtime-settings") {
        return {
          stdout: 'updated_at=2026-08-09T10:00:00Z degap_workspace_settings_json={"threads":8}',
          stderr: "",
        };
      }
      throw new Error(`unexpected operation ${args[0]}`);
    },
  });

  assert.equal(Object.keys(handlers).length, 41);
  const sequences = await handlers.listNewSequences({
    workspaceRoot: "D:/workspace",
    projectId: 7,
    limit: 1,
  });
  const settings = await handlers.getRuntimeSettings({ workspaceRoot: "D:/workspace" });

  assert.deepEqual(calls, [
    ["list-new-sequences", "D:/workspace", "7"],
    ["get-runtime-settings", "D:/workspace"],
  ]);
  assert.deepEqual(sequences, {
    items: [{
      assemblySeqId: 8,
      datasetName: "flye",
      seqName: "ctg8",
      seqLength: 1200,
      hidden: false,
    }],
  });
  assert.deepEqual(settings, {
    updatedAt: "2026-08-09T10:00:00Z",
    degapWorkspaceSettings: { threads: 8 },
    source: "workspace_db",
  });
});

test("main-view history dev operations map exact CLI contracts", async () => {
  const calls = [];
  const handlers = createBackendOperations({
    async runBackend(args) {
      calls.push(args);
      return { stdout: 'result_json={"changed":true}', stderr: "" };
    },
  });
  const target = { workspaceRoot: "D:/workspace", projectId: 7, chrName: "Chr01" };
  await handlers.getMainViewHistoryStatus(target);
  await handlers.inspectMainViewDelete({ ...target, assemblyCtgIds: [11, 12] });
  await handlers.runMainViewEditorAction({
    ...target,
    action: "rename-ctg",
    args: { assemblyCtgId: 11, newName: "renamed" },
  });
  await handlers.runMainViewBatchDelete({ ...target, assemblyCtgIds: [11, 12] });
  await handlers.executeMainViewHistoryAction({ ...target, action: "redo" });

  assert.deepEqual(calls, [
    ["main-view-history-status", "D:/workspace", "7", "Chr01"],
    ["inspect-main-view-delete", "D:/workspace", "7", "Chr01", "11,12"],
    [
      "run-main-view-editor-action",
      "D:/workspace",
      "7",
      "Chr01",
      "rename-ctg",
      '{"assemblyCtgId":11,"newName":"renamed"}',
    ],
    ["run-main-view-batch-delete", "D:/workspace", "7", "Chr01", "11,12"],
    ["redo-main-view-history", "D:/workspace", "7", "Chr01"],
  ]);
});
