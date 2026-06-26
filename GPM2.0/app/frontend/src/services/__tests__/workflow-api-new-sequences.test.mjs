import test from "node:test";
import assert from "node:assert/strict";

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;

async function loadWorkflowApi() {
  return import(`../workflow-api.js?test=${Date.now()}-${Math.random()}`);
}

test.afterEach(() => {
  globalThis.fetch = originalFetch;
  if (originalWindow === undefined) {
    delete globalThis.window;
  } else {
    globalThis.window = originalWindow;
  }
});

test("listNewSequences normalizes dev bridge payload to items", async () => {
  globalThis.window = {};
  globalThis.fetch = async (path, options) => {
    assert.equal(path, "/api/list-new-sequences");
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {
      workspaceRoot: "/tmp/workspace",
      projectId: 17,
      limit: 25,
    });
    return {
      ok: true,
      async json() {
        return {
          count: 1,
          items: [
            {
              assemblySeqId: 101,
              datasetName: "ds-a",
              seqName: "seq-1",
              seqLength: 4200,
              hidden: false,
            },
          ],
        };
      },
    };
  };

  const { listNewSequences } = await loadWorkflowApi();
  const result = await listNewSequences({
    workspaceRoot: "/tmp/workspace",
    projectId: 17,
    limit: 25,
  });

  assert.deepEqual(result, {
    items: [
      {
        assemblySeqId: 101,
        datasetName: "ds-a",
        seqName: "seq-1",
        seqLength: 4200,
        hidden: false,
      },
    ],
  });
});

test("listNewSequences applies limit during adapter normalization", async () => {
  globalThis.window = {};
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        items: [
          {
            assemblySeqId: 101,
            datasetName: "ds-a",
            seqName: "seq-1",
            seqLength: 4200,
            hidden: false,
          },
          {
            assemblySeqId: 102,
            datasetName: "ds-a",
            seqName: "seq-2",
            seqLength: 4100,
            hidden: false,
          },
          {
            assemblySeqId: 103,
            datasetName: "ds-b",
            seqName: "seq-3",
            seqLength: 3900,
            hidden: true,
          },
        ],
      };
    },
  });

  const { listNewSequences } = await loadWorkflowApi();
  const result = await listNewSequences({
    workspaceRoot: "/tmp/workspace",
    projectId: 17,
    limit: 2,
  });

  assert.deepEqual(result, {
    items: [
      {
        assemblySeqId: 101,
        datasetName: "ds-a",
        seqName: "seq-1",
        seqLength: 4200,
        hidden: false,
      },
      {
        assemblySeqId: 102,
        datasetName: "ds-a",
        seqName: "seq-2",
        seqLength: 4100,
        hidden: false,
      },
    ],
  });
});

test("listNewSequences normalizes dev bridge errors", async () => {
  globalThis.window = {};
  globalThis.fetch = async () => ({
    ok: false,
    async json() {
      return {
        error: {
          message: "project_id must be provided",
          code: "INVALID_PARAMS",
          detail: "project_id is required",
        },
      };
    },
  });

  const { listNewSequences } = await loadWorkflowApi();

  await assert.rejects(
    () =>
      listNewSequences({
        workspaceRoot: "/tmp/workspace",
        projectId: null,
        limit: 25,
      }),
    (error) => {
      assert.equal(error.message, "project_id must be provided");
      assert.equal(error.code, "INVALID_PARAMS");
      assert.equal(error.detail, "project_id is required");
      assert.equal(error.source, "dev-bridge");
      assert.equal(error.operation, "/api/list-new-sequences");
      return true;
    },
  );
});
