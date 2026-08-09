import {
  test,
  assert,
  __testLoadNewSequencesTabData,
  __testShouldReuseNewSequencesCache,
} from "./tabs-semantics-harness.mjs";

test("new sequences tab loader returns API items for rendering", async () => {
  const result = await __testLoadNewSequencesTabData(
    { workspaceRoot: "/tmp/workspace", projectId: 7 },
    async () => ({
      items: [
        { assemblySeqId: 1, seqName: "seq-a", datasetName: "hifiasm", seqLength: 1000, hidden: false },
        { assemblySeqId: 2, seqName: "seq-b", datasetName: "flye", seqLength: 2000, hidden: true },
      ],
    }),
  );

  assert.deepEqual(result.items.map((item) => item.seqName), ["seq-a", "seq-b"]);
  assert.equal(result.loadedProjectId, 7);
  assert.equal(result.loadedWorkspacePath, "/tmp/workspace");
  assert.equal(result.error, "");
});

test("new sequences loader reuses cache only for matching workspace and project", () => {
  const cached = {
    error: "",
    items: [{ assemblySeqId: 1 }],
    loadedProjectId: 7,
    loadedWorkspacePath: "/tmp/workspace-a",
  };

  assert.equal(
    __testShouldReuseNewSequencesCache(cached, { workspacePath: "/tmp/workspace-a", projectId: 7 }),
    true,
  );
  assert.equal(
    __testShouldReuseNewSequencesCache(cached, { workspacePath: "/tmp/workspace-b", projectId: 7 }),
    false,
  );
  assert.equal(
    __testShouldReuseNewSequencesCache({ ...cached, error: "boom" }, { workspacePath: "/tmp/workspace-a", projectId: 7 }),
    false,
  );
});
