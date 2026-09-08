import test from "node:test";
import assert from "node:assert/strict";
import { defaultProjectName, openProjectWorkspace } from "../project-session.js";

test("project names use the final directory and handle extracted bundles and Windows paths", () => {
  assert.equal(defaultProjectName("D:\\data\\rice\\gpm_server\\"), "rice");
  assert.equal(defaultProjectName("/data/rice/"), "rice");
  assert.equal(defaultProjectName("/data/rice/gpm_server"), "rice");
});

test("new directories initialize once with phased capability enabled, even on concurrent opens", async () => {
  let creations = 0;
  let projects = [];
  const deps = {
    openWorkspace: async () => ({ existingProjects: projects, datasets: [{ datasetId: 4 }] }),
    initializeProject: async request => {
      creations++;
      assert.equal(request.projectName, "rice");
      assert.equal(request.phasedAssemblyEnabled, true);
      projects = [{ projectId: 12, projectName: request.projectName }];
      return { existingProjects: projects };
    },
  };
  const [first, second] = await Promise.all([
    openProjectWorkspace({ workspaceRoot: "/test/rice" }, deps),
    openProjectWorkspace({ workspaceRoot: "/test/rice" }, deps),
  ]);
  assert.equal(creations, 1);
  assert.deepEqual(first, second);
  await openProjectWorkspace({ workspaceRoot: "/test/rice" }, deps);
  assert.equal(creations, 1);
});

test("existing multi-project directories preserve every project and do not rename or recreate them", async () => {
  const projects = [{ projectId: 4, projectName: "A" }, { projectId: 8, projectName: "B" }];
  const result = await openProjectWorkspace({ workspaceRoot: "/legacy", projectName: "replacement" }, {
    openWorkspace: async () => ({ existingProjects: projects }),
    initializeProject: () => assert.fail("must not initialize an existing project"),
  });
  assert.deepEqual(result.existingProjects, projects);
});

test("failed initialization is retryable with the same name without reimporting payloads", async () => {
  let calls = 0;
  const deps = {
    openWorkspace: async () => ({ existingProjects: [] }),
    initializeProject: async request => {
      assert.equal(request.projectName, "Custom name");
      if (++calls === 1) throw new Error("database unavailable");
      return { existingProjects: [{ projectId: 1, projectName: request.projectName }] };
    },
  };
  const args = { workspaceRoot: "/pending", projectName: " Custom name " };
  await assert.rejects(openProjectWorkspace(args, deps), error => {
    assert.equal(error.pendingProjectPath, "/pending");
    return error.message === "database unavailable";
  });
  const result = await openProjectWorkspace(args, deps);
  assert.equal(result.existingProjects.length, 1);
  assert.equal(calls, 2);
});

test("invalid directories fail before initialization", async () => {
  await assert.rejects(openProjectWorkspace({ workspaceRoot: "/missing" }, {
    openWorkspace: async () => { throw new Error("missing directory"); },
    initializeProject: () => assert.fail("must not initialize invalid input"),
  }), /missing directory/);
});
