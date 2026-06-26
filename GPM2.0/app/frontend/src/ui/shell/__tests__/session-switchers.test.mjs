import test from "node:test";
import assert from "node:assert/strict";

import {
  buildProjectSwitchItems,
  buildWorkspaceSwitchItems,
  switchProjectFromShell,
  switchWorkspaceFromShell,
} from "../session-switchers.js";
import { clearAssemblySessionCache } from "../assembly-session-cache.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = nextState;
    },
  };
}

test("buildWorkspaceSwitchItems includes current workspace and history records without duplicates", () => {
  const items = buildWorkspaceSwitchItems({
    state: {
      session: {
        workspacePath: "/tmp/current",
      },
    },
    historyRecords: [
      { path: "/tmp/history-a" },
      { path: "/tmp/current" },
      { path: "/tmp/history-b" },
    ],
    labels: {
      notOpened: "未打开",
    },
  });

  assert.deepEqual(
    items.map((item) => ({ value: item.value, selected: item.selected })),
    [
      { value: "/tmp/current", selected: true },
      { value: "/tmp/history-a", selected: false },
      { value: "/tmp/history-b", selected: false },
    ],
  );
});

test("buildProjectSwitchItems returns placeholder when no project is selected", () => {
  const items = buildProjectSwitchItems({
    state: {
      session: {
        projectId: null,
      },
      initializer: {
        existingProjects: [
          { projectId: 7, projectName: "project-a" },
          { projectId: 8, projectName: "project-b" },
        ],
      },
    },
    labels: {
      noProjectSelected: "未选择项目",
    },
  });

  assert.equal(items[0].value, "");
  assert.equal(items[0].selected, true);
  assert.equal(items[1].label, "project-a");
  assert.equal(items[2].label, "project-b");
});

test("switchWorkspaceFromShell opens a new workspace and clears the current project selection", async () => {
  const store = createStore({
    activeRoute: "assembly",
    locale: "zh",
    session: {
      workspacePath: "/tmp/old",
      projectId: 11,
      projectName: "old-project",
    },
    importer: {
      stages: [],
    },
    initializer: {
      existingProjects: [{ projectId: 11, projectName: "old-project" }],
    },
    assembly: {
      selectedChrName: "Chr01",
      chrCtgs: [{ assemblyCtgId: 1 }],
      refTrackMembers: [{ assemblyCtgId: 2 }],
      supportMirroredCtgs: [{ assemblyCtgId: 3 }],
      trackDragOffsets: [{ assemblyCtgId: 1, offsetBp: 10 }],
      subviewTrackDragOffsets: [{ contigId: 1, offsetBp: 20 }],
    },
  });

  await switchWorkspaceFromShell(store, "/tmp/new", {
    openWorkspace: async ({ workspaceRoot }) => {
      assert.equal(workspaceRoot, "/tmp/new");
      return {
        references: [{ referenceGenomeId: 1 }],
        datasets: [{ datasetId: 101 }],
        existingProjects: [{ projectId: 22, projectName: "new-project" }],
      };
    },
  });

  const next = store.getState();
  assert.equal(next.activeRoute, "workspace");
  assert.equal(next.session.workspacePath, "/tmp/new");
  assert.equal(next.session.projectId, null);
  assert.equal(next.session.projectName, "");
  assert.deepEqual(next.initializer.existingProjects, [{ projectId: 22, projectName: "new-project" }]);
  assert.equal(next.assembly.selectedChrName, "");
  assert.deepEqual(next.assembly.chrCtgs, []);
});

test("switchProjectFromShell updates the current project and resets assembly runtime state", () => {
  clearAssemblySessionCache();
  const store = createStore({
    activeRoute: "assembly",
    locale: "zh",
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
      projectName: "project-a",
    },
    initializer: {
      existingProjects: [
        {
          projectId: 7,
          projectName: "project-a",
          referenceGenomeId: 1,
          primaryDatasetId: 11,
          supportDatasetIds: [22],
          createdAt: "1710000000000",
        },
        {
          projectId: 8,
          projectName: "project-b",
          referenceGenomeId: 2,
          primaryDatasetId: 33,
          supportDatasetIds: [44, 55],
          createdAt: "1710000001000",
        },
      ],
      editProjectId: null,
      editProjectNameInput: "",
      editReferenceId: "",
      editPrimaryDatasetId: "",
      editSupportDatasetIds: [],
        editChrAssignmentMinCoveragePercentInput: "60",
      summary: "",
    },
    assembly: {
      selectedChrName: "Chr02",
      chrCtgs: [{ assemblyCtgId: 99 }],
      refTrackMembers: [{ assemblyCtgId: 199 }],
      supportMirroredCtgs: [{ assemblyCtgId: 299 }],
      hiddenPrimaryCtgIds: [99],
      trackDragOffsets: [{ assemblyCtgId: 99, offsetBp: 10 }],
      subviewTrackDragOffsets: [{ contigId: 99, offsetBp: 20 }],
      finalPathByChr: { Chr02: { segments: [{ segmentId: "x" }] } },
      subview: { summary: { mode: "2-contig" } },
    },
  });

  const changed = switchProjectFromShell(store, 8);

  assert.equal(changed, true);
  const next = store.getState();
  assert.equal(next.session.projectId, 8);
  assert.equal(next.session.projectName, "project-b");
  assert.equal(next.initializer.editProjectId, 8);
  assert.equal(next.initializer.editProjectNameInput, "project-b");
  assert.equal(next.initializer.editReferenceId, "2");
  assert.equal(next.initializer.editPrimaryDatasetId, "33");
  assert.deepEqual(next.initializer.editSupportDatasetIds, [44, 55]);
  assert.equal(next.assembly.selectedChrName, "");
  assert.deepEqual(next.assembly.chrCtgs, []);
  assert.deepEqual(next.assembly.finalPathByChr, {});
});

test("switchProjectFromShell restores cached assembly state when returning to an opened project", () => {
  clearAssemblySessionCache();
  const store = createStore({
    activeRoute: "assembly",
    locale: "zh",
    session: {
      workspacePath: "/tmp/ws",
      projectId: 7,
      projectName: "project-a",
    },
    initializer: {
      existingProjects: [
        {
          projectId: 7,
          projectName: "project-a",
          referenceGenomeId: 1,
          primaryDatasetId: 11,
          supportDatasetIds: [22],
          createdAt: "1710000000000",
        },
        {
          projectId: 8,
          projectName: "project-b",
          referenceGenomeId: 2,
          primaryDatasetId: 33,
          supportDatasetIds: [44],
          createdAt: "1710000001000",
        },
      ],
      editProjectId: null,
      editProjectNameInput: "",
      editReferenceId: "",
      editPrimaryDatasetId: "",
      editSupportDatasetIds: [],
      editChrAssignmentMinCoveragePercentInput: "60",
      summary: "",
    },
    assembly: {
      loading: false,
      selectedChrName: "Chr07",
      chrCtgs: [{ assemblyCtgId: 700 }],
      refTrackMembers: [{ assemblyCtgId: 701 }],
      finalPathByChr: { Chr07: { segments: [{ segmentId: "a" }] } },
    },
  });

  assert.equal(switchProjectFromShell(store, 8), true);
  assert.equal(store.getState().assembly.selectedChrName, "");

  store.setState({
    ...store.getState(),
    assembly: {
      ...store.getState().assembly,
      selectedChrName: "Chr08",
      chrCtgs: [{ assemblyCtgId: 800 }],
      finalPathByChr: { Chr08: { segments: [{ segmentId: "b" }] } },
    },
  });

  assert.equal(switchProjectFromShell(store, 7), true);
  assert.equal(store.getState().assembly.selectedChrName, "Chr07");
  assert.deepEqual(store.getState().assembly.chrCtgs, [{ assemblyCtgId: 700 }]);
  assert.deepEqual(store.getState().assembly.finalPathByChr, {
    Chr07: { segments: [{ segmentId: "a" }] },
  });

  assert.equal(switchProjectFromShell(store, 8), true);
  assert.equal(store.getState().assembly.selectedChrName, "Chr08");
  assert.deepEqual(store.getState().assembly.chrCtgs, [{ assemblyCtgId: 800 }]);
});
