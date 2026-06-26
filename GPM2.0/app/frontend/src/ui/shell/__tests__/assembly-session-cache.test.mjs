import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAssemblyCacheKey,
  buildAssemblyDomCacheKey,
  clearAssemblySessionCache,
  rememberAssemblyDom,
  rememberAssemblyState,
  restoreAssemblyDom,
  restoreAssemblyState,
} from "../assembly-session-cache.js";

function createState({ workspacePath = "D:/ws", projectId = 7, locale = "zh", assembly = {} } = {}) {
  return {
    locale,
    session: {
      workspacePath,
      projectId,
      projectName: projectId ? `project-${projectId}` : "",
    },
    assembly: {
      loading: false,
      selectedChrName: "",
      chromosomes: [],
      chrCtgs: [],
      ...assembly,
    },
  };
}

function createHost(nodes = []) {
  return {
    childNodes: [...nodes],
    dataset: {},
    replaceChildren(...nextNodes) {
      this.childNodes = nextNodes;
    },
  };
}

test("assembly cache keys are scoped by workspace and project", () => {
  assert.equal(
    buildAssemblyCacheKey(createState({ workspacePath: "D:/ws", projectId: 7 })),
    "D:/ws::7",
  );
  assert.equal(buildAssemblyCacheKey(createState({ workspacePath: "", projectId: 7 })), "");
  assert.equal(buildAssemblyCacheKey(createState({ workspacePath: "D:/ws", projectId: null })), "");
});

test("assembly DOM cache keys include locale so cached labels cannot cross languages", () => {
  assert.equal(
    buildAssemblyDomCacheKey(createState({ workspacePath: "D:/ws", projectId: 7, locale: "en" })),
    "D:/ws::7::en",
  );
});

test("assembly state cache restores a cloned snapshot and enforces LRU capacity", () => {
  clearAssemblySessionCache();

  rememberAssemblyState(createState({
    projectId: 1,
    assembly: { selectedChrName: "Chr01", chrCtgs: [{ assemblyCtgId: 1 }] },
  }), { maxEntries: 2 });
  rememberAssemblyState(createState({
    projectId: 2,
    assembly: { selectedChrName: "Chr02", chrCtgs: [{ assemblyCtgId: 2 }] },
  }), { maxEntries: 2 });

  const restoredFirst = restoreAssemblyState(
    createState({ projectId: 1 }),
    { selectedChrName: "", chrCtgs: [] },
  );
  assert.equal(restoredFirst.selectedChrName, "Chr01");
  restoredFirst.chrCtgs[0].assemblyCtgId = 999;
  assert.equal(
    restoreAssemblyState(createState({ projectId: 1 }), {}).chrCtgs[0].assemblyCtgId,
    1,
  );

  rememberAssemblyState(createState({
    projectId: 3,
    assembly: { selectedChrName: "Chr03", chrCtgs: [{ assemblyCtgId: 3 }] },
  }), { maxEntries: 2 });

  assert.deepEqual(restoreAssemblyState(createState({ projectId: 2 }), { selectedChrName: "" }), {
    selectedChrName: "",
  });
  assert.equal(restoreAssemblyState(createState({ projectId: 1 }), {}).selectedChrName, "Chr01");
});

test("assembly DOM cache preserves node identity across route detach and restore", () => {
  clearAssemblySessionCache();

  const node = { id: "assembly-root" };
  const host = createHost([node]);
  host.dataset.route = "assembly";
  host.dataset.assemblyDomCacheKey = buildAssemblyDomCacheKey(createState({ projectId: 7 }));

  assert.equal(rememberAssemblyDom(host, createState({ projectId: 7 })), true);
  host.replaceChildren({ id: "workspace-root" });

  assert.equal(restoreAssemblyDom(host, createState({ projectId: 7 })), true);
  assert.equal(host.childNodes[0], node);
  assert.equal(host.dataset.route, "assembly");
});
