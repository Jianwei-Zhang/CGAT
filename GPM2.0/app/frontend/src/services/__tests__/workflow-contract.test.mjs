import assert from "node:assert/strict";
import test from "node:test";

import * as workflowApi from "../workflow-api.js";
import { callDevBridge } from "../workflow/dev-transport.js";
import { createWorkflowMockBackend } from "../workflow/mock-backend.js";
import { WORKFLOW_OPERATION_CONTRACTS } from "../workflow/operation-contract.js";
import { createTauriTransport } from "../workflow/tauri-transport.js";

test("workflow registry covers every public operation and Tauri adapter method", () => {
  const publicNames = Object.keys(workflowApi)
    .filter((name) => !name.startsWith("__test"))
    .sort();
  const contractNames = WORKFLOW_OPERATION_CONTRACTS.map(({ name }) => name).sort();
  const tauri = createTauriTransport({
    invoke: async () => ({}),
    listen: async () => () => {},
  });

  assert.deepEqual(contractNames, publicNames);
  assert.deepEqual(Object.keys(tauri).sort(), publicNames);
  assert.ok(WORKFLOW_OPERATION_CONTRACTS.every(({ preview }) =>
    ["bridge", "mock", "unavailable"].includes(preview)));
});

test("Tauri transport preserves exact command payload and normalizes failures", async () => {
  const calls = [];
  const tauri = createTauriTransport({
    async invoke(command, payload, locale) {
      calls.push({ command, payload, locale });
      if (command === "export_final_path_fasta") {
        throw { code: "FINAL_PATH_INVALID", message: "invalid final path" };
      }
      return { items: [] };
    },
    listen: async () => () => {},
  });

  await tauri.listChrViewCtgs({
    workspaceRoot: "D:/workspace",
    projectId: 7,
    chrName: "Chr01",
    datasetId: 2,
  });
  await assert.rejects(
    tauri.exportFinalPathFasta({
      workspaceRoot: "D:/workspace",
      projectId: 7,
      chrName: "Chr01",
      finalPathEntry: { segments: [] },
      outputPath: "D:/out.fa",
    }),
    (error) => {
      assert.equal(error.code, "FINAL_PATH_INVALID");
      assert.equal(error.source, "tauri");
      assert.equal(error.operation, "export_final_path_fasta");
      return true;
    },
  );

  assert.deepEqual(calls[0], {
    command: "list_chr_view_ctgs",
    payload: {
      workspaceRoot: "D:/workspace",
      projectId: 7,
      chrName: "Chr01",
      datasetId: 2,
    },
    locale: undefined,
  });
});

test("Tauri transport normalizes each domain at the injected invoke boundary", async () => {
  const rejected = { code: "INVALID_PARAMS", message: "invalid request" };
  const tauri = createTauriTransport({
    async invoke() {
      throw rejected;
    },
    listen: async () => () => {},
  });
  const cases = [
    [
      "import_zip",
      () => tauri.importZipBundle({ zipPath: "D:/input.zip", workspaceRoot: "D:/workspace" }),
    ],
    ["open_workspace", () => tauri.openWorkspace({ workspaceRoot: "D:/workspace" })],
    [
      "list_chr_view_ctgs",
      () => tauri.listChrViewCtgs({
        workspaceRoot: "D:/workspace",
        projectId: 7,
        chrName: "Chr01",
      }),
    ],
    ["get_runtime_settings", () => tauri.getRuntimeSettings({ workspaceRoot: "D:/workspace" })],
  ];

  for (const [operation, invokeOperation] of cases) {
    await assert.rejects(invokeOperation, (error) => {
      assert.equal(error.code, "INVALID_PARAMS");
      assert.equal(error.source, "tauri");
      assert.equal(error.operation, operation);
      assert.equal(error.cause, rejected);
      return true;
    });
  }
});

test("dev transport preserves structured error envelope fields", async () => {
  await assert.rejects(
    callDevBridge("/api/open-workspace", { workspaceRoot: "D:/missing" }, {
      fetchImpl: async () => ({
        ok: false,
        status: 404,
        async json() {
          return {
            code: "WORKSPACE_NOT_FOUND",
            message: "workspace is missing",
            operation: "POST /open-workspace",
            data: { workspaceRoot: "D:/missing" },
          };
        },
      }),
    }),
    (error) => {
      assert.equal(error.code, "WORKSPACE_NOT_FOUND");
      assert.equal(error.message, "workspace is missing");
      assert.equal(error.operation, "POST /open-workspace");
      assert.deepEqual(error.data, { workspaceRoot: "D:/missing" });
      return true;
    },
  );
});

test("mock backend factories isolate mutable preview state", async () => {
  const first = createWorkflowMockBackend();
  const second = createWorkflowMockBackend();

  await first.initializeProject({ workspaceRoot: "D:/one", projectName: "one" });
  const firstOptions = await first.listProjectInitializerOptions({ workspaceRoot: "D:/one" });
  const secondOptions = await second.listProjectInitializerOptions({ workspaceRoot: "D:/two" });

  assert.equal(firstOptions.existingProjects.length, 1);
  assert.equal(secondOptions.existingProjects.length, 0);
});
