import test from "node:test";
import assert from "node:assert/strict";

import {
  bindWorkspacePage,
  buildAutoPipelineSteps,
  renderWorkspacePage,
} from "../workspace-page.js";
import { clearAssemblySessionCache } from "../../shell/assembly-session-cache.js";

function createState(overrides = {}) {
  const {
    session: sessionOverrides = {},
    initializer: initializerOverrides = {},
    assembly: assemblyOverrides = {},
  } = overrides;
  return {
    locale: "en",
    session: {
      workspacePath: "D:/ws",
      projectName: "",
      projectId: null,
      ...sessionOverrides,
    },
    initializer: {
      loading: false,
      optionsLoaded: true,
      optionsError: "",
      references: [],
      datasets: [],
      existingProjects: [],
      selectedReferenceId: "",
      selectedPrimaryDatasetId: "",
      selectedSupportDatasetIds: [],
      projectNameInput: "",
      chrAssignmentMinCoveragePercentInput: "60",
      phasedAssemblyEnabledInput: false,
      createModalOpen: false,
      packageMetadata: {
        packageMode: "fast",
        sequenceLayout: "partitioned",
        preassignedChr: true,
        chrAssignmentMinCoveragePercent: 60,
        selfAlignmentScope: "chr_partition",
        crossAlignmentScope: "chr_partition",
      },
      autoPipelineModalOpen: false,
      autoPipelineRunning: false,
      autoPipelineCanClose: true,
      autoPipelineSteps: [],
      autoPipelineRunId: null,
      autoPipelineCancelRequested: false,
      creating: false,
      updating: false,
      editProjectId: null,
      editProjectNameInput: "",
      editReferenceId: "",
      editPrimaryDatasetId: "",
      editSupportDatasetIds: [],
      editChrAssignmentMinCoveragePercentInput: "60",
      editPhasedAssemblyEnabledInput: false,
      summary: "Fill in the project information and create a project.",
      ...initializerOverrides,
    },
    assembly: {
      loading: false,
      selectedChrName: "",
      chrCtgs: [],
      refTrackMembers: [],
      deletedCtgs: [],
      selectedDeletedCtgRecordIds: [],
      supportMirroredCtgs: [],
      hiddenPrimaryCtgIds: [],
      trackDragOffsets: [],
      subviewTrackDragOffsets: [],
      finalPathByChr: {},
      ...assemblyOverrides,
    },
  };
}

function createStore(initialState) {
  let state = structuredClone(initialState);
  return {
    getState() {
      return state;
    },
    setState(partial) {
      state = {
        ...state,
        ...partial,
      };
    },
  };
}

function createButton() {
  const listeners = new Map();
  return {
    dataset: {},
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    async click() {
      const handler = listeners.get("click");
      if (handler) {
        await handler({ currentTarget: this, target: this, stopPropagation() {} });
      }
    },
    async contextmenu({ clientX = 0, clientY = 0 } = {}) {
      const handler = listeners.get("contextmenu");
      if (handler) {
        await handler({
          currentTarget: this,
          target: this,
          clientX,
          clientY,
          preventDefault() {},
          stopPropagation() {},
        });
      }
    },
  };
}

function createProjectSelectButton(projectId) {
  const button = createButton();
  button.dataset.projectSelectId = String(projectId);
  return button;
}

function createInput(initialValue = "") {
  const listeners = new Map();
  return {
    value: initialValue,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    async input(nextValue) {
      this.value = nextValue;
      const handler = listeners.get("input");
      if (handler) {
        await handler({ currentTarget: this, target: this });
      }
    },
    async blur() {
      const handler = listeners.get("blur");
      if (handler) {
        await handler({ currentTarget: this, target: this });
      }
    },
    async change(nextValue = this.value) {
      this.value = nextValue;
      const handler = listeners.get("change");
      if (handler) {
        await handler({ currentTarget: this, target: this });
      }
    },
  };
}

function createCheckbox(initialChecked = false) {
  const listeners = new Map();
  return {
    checked: initialChecked,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    async change(nextChecked = this.checked) {
      this.checked = nextChecked;
      const handler = listeners.get("change");
      if (handler) {
        await handler({ currentTarget: this, target: this });
      }
    },
  };
}

function createHost(nodeMap = {}) {
  const nodes = new Map(Object.entries(nodeMap));
  return {
    innerHTML: "",
    closest() {
      return null;
    },
    querySelector(selector) {
      const value = nodes.get(selector);
      return Array.isArray(value) ? value[0] || null : value || null;
    },
    querySelectorAll(selector) {
      const value = nodes.get(selector);
      if (!value) {
        return [];
      }
      return Array.isArray(value) ? value : [value];
    },
  };
}

function createRouteHost(nodeMap = {}) {
  const nodes = new Map(Object.entries(nodeMap));
  let html = "";
  let renderCount = 0;
  return {
    get innerHTML() {
      return html;
    },
    set innerHTML(value) {
      html = value;
      renderCount += 1;
    },
    get renderCount() {
      return renderCount;
    },
    closest(selector) {
      return selector === "#route-host" ? this : null;
    },
    querySelector(selector) {
      const value = nodes.get(selector);
      return Array.isArray(value) ? value[0] || null : value || null;
    },
    querySelectorAll(selector) {
      const value = nodes.get(selector);
      if (!value) {
        return [];
      }
      return Array.isArray(value) ? value : [value];
    },
  };
}

test("workspace page renders english labels for page shell and empty project state", () => {
  const html = renderWorkspacePage(createState());

  assert.match(html, />Project Area</);
  assert.match(html, />Project Initialization</);
  assert.match(html, />Create Project</);
  assert.match(html, />Enter Assembly</);
  assert.match(html, />Existing Projects</);
  assert.match(html, />No projects loaded\./);
});

test("workspace project rows do not expose add-package context menu", () => {
  const html = renderWorkspacePage(createState({
    initializer: {
      existingProjects: [
        {
          projectId: 7,
          projectName: "Project A",
          referenceGenomeId: 1,
          primaryDatasetId: 11,
          supportDatasetIds: [22],
          createdAt: "2026-05-25T01:02:03Z",
        },
      ],
    },
  }));

  assert.doesNotMatch(html, /data-project-context-menu/);
  assert.doesNotMatch(html, /data-project-import-add-package-id/);
  assert.doesNotMatch(html, /Import add package/);
});

test("workspace page renders english create-project modal labels", () => {
  const html = renderWorkspacePage(createState({
    initializer: {
      createModalOpen: true,
    },
  }));

  assert.match(html, />Create New Project</);
  assert.match(html, />Close</);
  assert.match(html, />Project Name</);
  assert.match(html, />Reference Genome</);
  assert.match(html, />Primary Dataset</);
  assert.match(html, />Support Dataset</);
  assert.match(html, />Cancel</);
});

test("workspace create-project modal renders server-owned chr assignment threshold as disabled", () => {
  const html = renderWorkspacePage(createState({
    initializer: {
      createModalOpen: true,
      chrAssignmentMinCoveragePercentInput: "72.5",
      packageMetadata: {
        packageMode: "fast",
        sequenceLayout: "partitioned",
        preassignedChr: true,
        chrAssignmentMinCoveragePercent: 72.5,
        selfAlignmentScope: "chr_partition",
        crossAlignmentScope: "chr_partition",
      },
    },
  }));

  assert.match(
    html,
    />Chr assignment threshold \(%\)<span class="muted"> fixed by the imported server delivery package and used on the server for chromosome grouping<\/span><\/label>/,
  );
  assert.match(
    html,
    /<input\s+id="initializer-chr-assignment-threshold-input"[\s\S]*?value="72\.5"[\s\S]*?disabled[\s\S]*?\/>/,
  );
});

test("workspace create-project modal renders phased assembly switch off by default", () => {
  const html = renderWorkspacePage(createState({
    initializer: {
      createModalOpen: true,
    },
  }));

  assert.match(html, /Enable phased assembly/);
  assert.match(
    html,
    /<input\s+id="initializer-phased-assembly-enabled-input"[\s\S]*?type="checkbox"[\s\S]*?role="switch"[\s\S]*?\/>/,
  );
  assert.doesNotMatch(
    html,
    /<input\s+id="initializer-phased-assembly-enabled-input"[\s\S]*?checked[\s\S]*?\/>/,
  );
});

test("workspace create-project phased assembly switch updates the create draft", async () => {
  const phasedAssemblyCheckbox = createCheckbox(false);
  const host = createRouteHost({
    "#initializer-phased-assembly-enabled-input": phasedAssemblyCheckbox,
  });
  const store = createStore(createState({
    initializer: {
      createModalOpen: true,
      phasedAssemblyEnabledInput: false,
    },
  }));

  bindWorkspacePage(host, store);
  await phasedAssemblyCheckbox.change(true);

  assert.equal(store.getState().initializer.phasedAssemblyEnabledInput, true);
  assert.equal(host.renderCount, 0);
});

test("workspace create-project modal renders server-owned chr assignment threshold as disabled for server delivery packages", () => {
  const html = renderWorkspacePage(createState({
    initializer: {
      createModalOpen: true,
      chrAssignmentMinCoveragePercentInput: "72",
      packageMetadata: {
        packageMode: "fast",
        sequenceLayout: "partitioned",
        preassignedChr: true,
        chrAssignmentMinCoveragePercent: 72,
        selfAlignmentScope: "chr_partition",
        crossAlignmentScope: "chr_partition",
      },
    },
  }));

  assert.match(
    html,
    />Chr assignment threshold \(%\)<span class="muted"> fixed by the imported server delivery package and used on the server for chromosome grouping<\/span><\/label>/,
  );
  assert.match(
    html,
    /<input\s+id="initializer-chr-assignment-threshold-input"[\s\S]*?value="72"[\s\S]*?disabled[\s\S]*?\/>/,
  );
});

test("workspace page renders english dataset option summaries when locale is en", () => {
  const html = renderWorkspacePage(createState({
    initializer: {
      createModalOpen: true,
      datasets: [
        {
          datasetId: 2,
          name: "canu2",
          contigCount: 1234,
          totalLengthBp: 567890,
        },
      ],
    },
  }));

  assert.match(html, /canu2 \(contigs = 1,234, total length = 567,890 bp\)/);
  assert.doesNotMatch(html, /contig数/);
});

test("processed projects render only unsafe selected-project fields as locked", () => {
  const html = renderWorkspacePage(createState({
    session: {
      projectId: 7,
      projectName: "project_locked",
    },
    initializer: {
      existingProjects: [
        {
          projectId: 7,
          projectName: "project_locked",
          createdAt: "1710000000",
          referenceGenomeId: 1,
          primaryDatasetId: 11,
          supportDatasetIds: [12],
          chrAssignmentMinCoveragePercent: 66,
          phasedAssemblyEnabled: true,
          isProcessed: true,
        },
      ],
      references: [{ referenceId: 1, name: "ref_a" }],
      datasets: [
        { datasetId: 11, name: "hifiasm", contigCount: 10, totalLengthBp: 1000 },
        { datasetId: 12, name: "flye", contigCount: 11, totalLengthBp: 2000 },
        { datasetId: 14, name: "canu", contigCount: 12, totalLengthBp: 3000 },
      ],
      editPhasedAssemblyEnabledInput: true,
    },
  }));

  assert.match(html, />Chr assignment threshold \(%\)<span class="muted"> fixed by the imported server delivery package and used on the server for chromosome grouping<\/span><\/label>/);
  assert.match(
    html,
    /<input\s+id="selected-project-name-input"[\s\S]*?value="project_locked"[\s\S]*?\/>/,
  );
  assert.doesNotMatch(
    html.match(/<input\s+id="selected-project-name-input"[\s\S]*?\/>/)?.[0] || "",
    /disabled/,
  );
  assert.match(
    html,
    /<input\s+id="selected-project-chr-assignment-threshold-input"[\s\S]*?value="60"[\s\S]*?disabled[\s\S]*?\/>/,
  );
  assert.match(
    html,
    /data-edit-support-dataset-id="12" checked disabled/,
  );
  assert.match(
    html,
    /data-edit-support-dataset-id="14"\s+ \/>canu/,
  );
  assert.match(
    html,
    /<input\s+id="selected-project-phased-assembly-enabled-input"[\s\S]*?checked[\s\S]*?disabled[\s\S]*?\/>/,
  );
  assert.match(
    html,
    />This project has entered assembly: you can rename it, append support datasets, and enable phased assembly; reference, primary dataset, and chr assignment threshold stay locked\.<\/p>/,
  );
});

test("processed selected-project name input mutates the edit draft", async () => {
  const previousDocument = globalThis.document;
  const projectNameInput = createInput("project_locked");
  const saveButton = createButton();
  saveButton.disabled = true;
  const host = createRouteHost({
    "#selected-project-name-input": projectNameInput,
    "#selected-project-save-button": saveButton,
  });
  const store = createStore(createState({
    session: {
      projectId: 7,
      projectName: "project_locked",
    },
    initializer: {
      editProjectNameInput: "project_locked",
      existingProjects: [
        {
          projectId: 7,
          projectName: "project_locked",
          createdAt: "1710000000",
          referenceGenomeId: 1,
          primaryDatasetId: 11,
          supportDatasetIds: [12],
          chrAssignmentMinCoveragePercent: 66,
          isProcessed: true,
        },
      ],
    },
  }));

  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    bindWorkspacePage(host, store);
    await projectNameInput.input("renamed");

    assert.equal(store.getState().initializer.editProjectNameInput, "renamed");
    assert.equal(host.renderCount, 0);
    assert.equal(saveButton.disabled, false);
  } finally {
    globalThis.document = previousDocument;
  }
});

test("processed selected-project phased assembly switch does not mutate the edit draft", async () => {
  const phasedAssemblyCheckbox = createCheckbox(true);
  const host = createRouteHost({
    "#selected-project-phased-assembly-enabled-input": phasedAssemblyCheckbox,
  });
  const store = createStore(createState({
    session: {
      projectId: 7,
      projectName: "project_locked",
    },
    initializer: {
      editPhasedAssemblyEnabledInput: true,
      existingProjects: [
        {
          projectId: 7,
          projectName: "project_locked",
          createdAt: "1710000000",
          referenceGenomeId: 1,
          primaryDatasetId: 11,
          supportDatasetIds: [12],
          chrAssignmentMinCoveragePercent: 66,
          phasedAssemblyEnabled: true,
          isProcessed: true,
        },
      ],
    },
  }));

  bindWorkspacePage(host, store);
  await phasedAssemblyCheckbox.change(false);

  assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, true);
  assert.equal(host.renderCount, 0);
});

test("selected-project phased assembly switch can be saved before assembly starts", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const phasedAssemblyCheckbox = createCheckbox(true);
  const saveButton = createButton();
  const calls = [];
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            assert.equal(command, "update_project");
            assert.equal(args.projectId, 7);
            assert.equal(args.phasedAssemblyEnabled, false);
            return {
              projectId: 7,
              projectName: "project_editable",
              referenceGenomeId: 1,
              primaryDatasetId: 11,
              supportDatasetIds: [12],
              chrAssignmentMinCoveragePercent: 60,
              phasedAssemblyEnabled: false,
              isProcessed: false,
              existingProjects: [
                {
                  projectId: 7,
                  projectName: "project_editable",
                  createdAt: "1710000000",
                  referenceGenomeId: 1,
                  primaryDatasetId: 11,
                  supportDatasetIds: [12],
                  chrAssignmentMinCoveragePercent: 60,
                  phasedAssemblyEnabled: false,
                  isProcessed: false,
                },
              ],
            };
          },
        },
      },
    };
    const host = createRouteHost({
      "#selected-project-phased-assembly-enabled-input": phasedAssemblyCheckbox,
      "#selected-project-save-button": saveButton,
    });
    const store = createStore(createState({
      session: {
        projectId: 7,
        projectName: "project_editable",
      },
      initializer: {
        editProjectId: 7,
        editProjectNameInput: "project_editable",
        editReferenceId: "1",
        editPrimaryDatasetId: "11",
        editSupportDatasetIds: [12],
        editChrAssignmentMinCoveragePercentInput: "60",
        editPhasedAssemblyEnabledInput: true,
        existingProjects: [
          {
            projectId: 7,
            projectName: "project_editable",
            createdAt: "1710000000",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [12],
            chrAssignmentMinCoveragePercent: 60,
            phasedAssemblyEnabled: true,
            isProcessed: false,
          },
        ],
      },
    }));

    bindWorkspacePage(host, store);
    await phasedAssemblyCheckbox.change(false);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, false);

    await saveButton.click();

    assert.equal(calls.length, 1);
    assert.equal(store.getState().initializer.existingProjects[0].phasedAssemblyEnabled, false);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, false);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("selected-project primary and support dataset changes persist before assembly starts", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const projectNameInput = createInput("project_editable");
  const referenceSelect = createInput("1");
  const primaryDatasetSelect = createInput("11");
  const supportDatasetCheckbox = createCheckbox(false);
  supportDatasetCheckbox.dataset = { editSupportDatasetId: "14" };
  const supportDatasetList = {
    querySelectorAll(selector) {
      if (selector === "input[type='checkbox']") {
        return [supportDatasetCheckbox];
      }
      return [];
    },
  };
  const phasedAssemblyCheckbox = createCheckbox(false);
  const saveButton = createButton();
  const calls = [];
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            assert.equal(command, "update_project");
            assert.equal(args.projectId, 7);
            assert.equal(args.projectName, "project_renamed");
            assert.equal(args.referenceGenomeId, 2);
            assert.equal(args.primaryDatasetId, 13);
            assert.deepEqual(args.supportDatasetIds, [12, 14]);
            assert.equal(args.phasedAssemblyEnabled, true);
            return {
              projectId: 7,
              projectName: "project_renamed",
              referenceGenomeId: 2,
              primaryDatasetId: 13,
              supportDatasetIds: [12, 14],
              phasedAssemblyEnabled: true,
              chrAssignmentMinCoveragePercent: 60,
              isProcessed: false,
            };
          },
        },
      },
    };
    const host = createRouteHost({
      "#selected-project-name-input": projectNameInput,
      "#selected-project-reference-select": referenceSelect,
      "#selected-project-primary-dataset-select": primaryDatasetSelect,
      "#selected-project-support-dataset-list": supportDatasetList,
      "#selected-project-phased-assembly-enabled-input": phasedAssemblyCheckbox,
      "#selected-project-save-button": saveButton,
    });
    const store = createStore(createState({
      session: {
        projectId: 7,
        projectName: "project_editable",
      },
      initializer: {
        editProjectId: 7,
        editProjectNameInput: "project_editable",
        editReferenceId: "1",
        editPrimaryDatasetId: "11",
        editSupportDatasetIds: [12],
        editChrAssignmentMinCoveragePercentInput: "60",
        editPhasedAssemblyEnabledInput: false,
        existingProjects: [
          {
            projectId: 7,
            projectName: "project_editable",
            createdAt: "1710000000",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [12],
            chrAssignmentMinCoveragePercent: 60,
            phasedAssemblyEnabled: false,
            isProcessed: false,
          },
        ],
        references: [
          { referenceGenomeId: 1, name: "ref_a" },
          { referenceGenomeId: 2, name: "ref_b" },
        ],
        datasets: [
          { datasetId: 11, name: "hifiasm", contigCount: 10, totalLengthBp: 1000 },
          { datasetId: 12, name: "flye", contigCount: 11, totalLengthBp: 2000 },
          { datasetId: 13, name: "wtdbg2", contigCount: 12, totalLengthBp: 3000 },
          { datasetId: 14, name: "canu", contigCount: 13, totalLengthBp: 4000 },
        ],
      },
    }));

    bindWorkspacePage(host, store);
    await projectNameInput.input("project_renamed");
    await referenceSelect.change("2");
    await primaryDatasetSelect.change("13");
    await supportDatasetCheckbox.change(true);
    await phasedAssemblyCheckbox.change(true);
    await saveButton.click();

    assert.equal(calls.length, 1);
    assert.equal(store.getState().session.projectName, "project_renamed");
    assert.equal(store.getState().initializer.existingProjects.length, 1);
    assert.equal(store.getState().initializer.existingProjects[0].projectName, "project_renamed");
    assert.equal(store.getState().initializer.existingProjects[0].referenceGenomeId, 2);
    assert.equal(store.getState().initializer.existingProjects[0].primaryDatasetId, 13);
    assert.deepEqual(store.getState().initializer.existingProjects[0].supportDatasetIds, [12, 14]);
    assert.equal(store.getState().initializer.existingProjects[0].phasedAssemblyEnabled, true);
    assert.equal(store.getState().initializer.editProjectNameInput, "project_renamed");
    assert.equal(store.getState().initializer.editPrimaryDatasetId, "13");
    assert.deepEqual(store.getState().initializer.editSupportDatasetIds, [12, 14]);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, true);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("processed selected-project panel saves rename, support append, and phased enablement", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const projectNameInput = createInput("project_processed");
  const referenceSelect = createInput("2");
  const primaryDatasetSelect = createInput("13");
  const existingSupportCheckbox = createCheckbox(true);
  existingSupportCheckbox.dataset = { editSupportDatasetId: "12" };
  const newSupportCheckbox = createCheckbox(false);
  newSupportCheckbox.dataset = { editSupportDatasetId: "14" };
  const supportDatasetList = {
    querySelectorAll(selector) {
      if (selector === "input[type='checkbox']") {
        return [existingSupportCheckbox, newSupportCheckbox];
      }
      return [];
    },
  };
  const phasedAssemblyCheckbox = createCheckbox(false);
  const saveButton = createButton();
  const calls = [];
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            calls.push({ command, args });
            if (command === "update_project") {
              assert.equal(args.projectId, 7);
              assert.equal(args.projectName, "project_processed_renamed");
              assert.equal(args.referenceGenomeId, 1);
              assert.equal(args.primaryDatasetId, 11);
              assert.deepEqual(args.supportDatasetIds, [12, 14]);
              assert.equal(args.phasedAssemblyEnabled, true);
              return {
                projectId: 7,
                projectName: "project_processed_renamed",
                referenceGenomeId: 1,
                primaryDatasetId: 11,
                supportDatasetIds: [12, 14],
                phasedAssemblyEnabled: true,
                chrAssignmentMinCoveragePercent: 60,
                isProcessed: true,
              };
            }
            assert.equal(command, "auto_orient_contigs_for_dataset");
            assert.equal(args.projectId, 7);
            assert.equal(args.datasetId, 14);
            return {
              projectId: 7,
              datasetId: 14,
              processedCtgCount: 3,
              orientedCtgCount: 3,
              flippedCtgCount: 1,
              noEvidenceCount: 0,
              skippedManualCount: 0,
            };
          },
        },
      },
    };
    const host = createRouteHost({
      "#selected-project-name-input": projectNameInput,
      "#selected-project-reference-select": referenceSelect,
      "#selected-project-primary-dataset-select": primaryDatasetSelect,
      "#selected-project-support-dataset-list": supportDatasetList,
      "#selected-project-phased-assembly-enabled-input": phasedAssemblyCheckbox,
      "#selected-project-save-button": saveButton,
    });
    const store = createStore(createState({
      session: {
        projectId: 7,
        projectName: "project_processed",
      },
      initializer: {
        editProjectId: 7,
        editProjectNameInput: "project_processed",
        editReferenceId: "2",
        editPrimaryDatasetId: "13",
        editSupportDatasetIds: [12],
        editChrAssignmentMinCoveragePercentInput: "72.5",
        editPhasedAssemblyEnabledInput: false,
        existingProjects: [
          {
            projectId: 7,
            projectName: "project_processed",
            createdAt: "1710000000",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [12],
            chrAssignmentMinCoveragePercent: 60,
            phasedAssemblyEnabled: false,
            isProcessed: true,
          },
        ],
        references: [
          { referenceGenomeId: 1, name: "ref_a" },
          { referenceGenomeId: 2, name: "ref_b" },
        ],
        datasets: [
          { datasetId: 11, name: "hifiasm", contigCount: 10, totalLengthBp: 1000 },
          { datasetId: 12, name: "flye", contigCount: 11, totalLengthBp: 2000 },
          { datasetId: 13, name: "wtdbg2", contigCount: 12, totalLengthBp: 3000 },
          { datasetId: 14, name: "canu", contigCount: 13, totalLengthBp: 4000 },
        ],
      },
    }));

    bindWorkspacePage(host, store);
    await existingSupportCheckbox.change(false);
    assert.deepEqual(store.getState().initializer.editSupportDatasetIds, [12]);
    await projectNameInput.input("project_processed_renamed");
    await referenceSelect.change("2");
    await primaryDatasetSelect.change("13");
    await newSupportCheckbox.change(true);
    await phasedAssemblyCheckbox.change(true);
    await saveButton.click();

    assert.equal(calls.length, 2);
    assert.deepEqual(calls.map((call) => call.command), [
      "update_project",
      "auto_orient_contigs_for_dataset",
    ]);
    assert.equal(store.getState().session.projectName, "project_processed_renamed");
    assert.equal(store.getState().initializer.existingProjects[0].projectName, "project_processed_renamed");
    assert.equal(store.getState().initializer.existingProjects[0].referenceGenomeId, 1);
    assert.equal(store.getState().initializer.existingProjects[0].primaryDatasetId, 11);
    assert.deepEqual(store.getState().initializer.existingProjects[0].supportDatasetIds, [12, 14]);
    assert.equal(store.getState().initializer.existingProjects[0].phasedAssemblyEnabled, true);
    assert.equal(store.getState().initializer.editProjectNameInput, "project_processed_renamed");
    assert.equal(store.getState().initializer.editReferenceId, "1");
    assert.equal(store.getState().initializer.editPrimaryDatasetId, "11");
    assert.deepEqual(store.getState().initializer.editSupportDatasetIds, [12, 14]);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, true);
    assert.equal(store.getState().initializer.autoPipelineModalOpen, true);
    assert.equal(store.getState().initializer.autoPipelineRunning, false);
    assert.deepEqual(
      store.getState().initializer.autoPipelineSteps.map((step) => [step.id, step.status]),
      [
        ["save_project", "done"],
        ["append_support", "done"],
        ["auto_orient_dataset", "done"],
      ],
    );
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("workspace auto pipeline marks local chr assignment as skipped for server preassigned bundles", () => {
  const steps = buildAutoPipelineSteps(createState({
    initializer: {
      packageMetadata: {
        packageMode: "fast",
        sequenceLayout: "partitioned",
        preassignedChr: true,
        chrAssignmentMinCoveragePercent: 60,
        selfAlignmentScope: "chr_partition",
        crossAlignmentScope: "chr_partition",
      },
    },
  }), {
    needsBootstrap: true,
  });

  assert.deepEqual(
    steps.map((step) => ({ id: step.id, status: step.status })),
    [
      { id: "bootstrap", status: "pending" },
      { id: "auto_assign_chr", status: "skipped" },
      { id: "auto_orient", status: "pending" },
    ],
  );
});

test("create project uses the imported server chr assignment threshold", async () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {};

    const createProjectConfirmButton = createButton();
    const host = createHost({
      "#initializer-create-project-confirm-button": createProjectConfirmButton,
    });
    const store = createStore(createState({
      initializer: {
        optionsLoaded: true,
        createModalOpen: true,
        projectNameInput: "project_custom_threshold",
        selectedReferenceId: "1",
        selectedPrimaryDatasetId: "11",
        selectedSupportDatasetIds: [12],
        chrAssignmentMinCoveragePercentInput: "72.5",
        phasedAssemblyEnabledInput: true,
        packageMetadata: {
          packageMode: "fast",
          sequenceLayout: "partitioned",
          preassignedChr: true,
          chrAssignmentMinCoveragePercent: 60,
          selfAlignmentScope: "chr_partition",
          crossAlignmentScope: "chr_partition",
        },
        references: [{ referenceGenomeId: 1, name: "ref_a" }],
        datasets: [
          { datasetId: 11, name: "hifiasm", contigCount: 10, totalLengthBp: 1000 },
          { datasetId: 12, name: "flye", contigCount: 11, totalLengthBp: 2000 },
        ],
      },
    }));

    bindWorkspacePage(host, store);
    await createProjectConfirmButton.click();

    const createdProject = store.getState().initializer.existingProjects.find(
      (project) => project.projectName === "project_custom_threshold",
    );
    assert.ok(createdProject, "expected project to be created");
    assert.equal(createdProject.chrAssignmentMinCoveragePercent, 60);
    assert.equal(createdProject.phasedAssemblyEnabled, true);
    assert.equal(store.getState().initializer.editChrAssignmentMinCoveragePercentInput, "60");
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, true);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("workspace project card selection restores cached assembly state when returning to an opened project", async () => {
  clearAssemblySessionCache();
  const previousDocument = globalThis.document;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };

    const projectAButton = createProjectSelectButton(7);
    const projectBButton = createProjectSelectButton(8);
    const host = createRouteHost({});
    host.querySelectorAll = (selector) => {
      if (selector === "[data-project-select-id]") {
        return [projectAButton, projectBButton];
      }
      return [];
    };
    const store = createStore(createState({
      session: {
        projectId: 7,
        projectName: "project-a",
      },
      initializer: {
        packageMetadata: {
          packageMode: "fast",
          sequenceLayout: "partitioned",
          preassignedChr: true,
          chrAssignmentMinCoveragePercent: 60,
          selfAlignmentScope: "chr_partition",
          crossAlignmentScope: "chr_partition",
        },
        existingProjects: [
          {
            projectId: 7,
            projectName: "project-a",
            createdAt: "1710000000",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [12],
            chrAssignmentMinCoveragePercent: 60,
          },
          {
            projectId: 8,
            projectName: "project-b",
            createdAt: "1710000100",
            referenceGenomeId: 2,
            primaryDatasetId: 21,
            supportDatasetIds: [22],
            chrAssignmentMinCoveragePercent: 70,
          },
        ],
      },
      assembly: {
        selectedChrName: "Chr07",
        chrCtgs: [{ assemblyCtgId: 700 }],
        finalPathByChr: { Chr07: { segments: [{ segmentId: "a" }] } },
      },
    }));

    bindWorkspacePage(host, store);
    await projectBButton.click();
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

    await projectAButton.click();
    assert.equal(store.getState().assembly.selectedChrName, "Chr07");
    assert.deepEqual(store.getState().assembly.chrCtgs, [{ assemblyCtgId: 700 }]);
    assert.deepEqual(store.getState().assembly.finalPathByChr, {
      Chr07: { segments: [{ segmentId: "a" }] },
    });
  } finally {
    globalThis.document = previousDocument;
  }
});

test("delete project removes only the deleted card when backend omits refreshed project list", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      confirm: () => true,
      __TAURI__: {
        core: {
          invoke: async (command, args) => {
            assert.equal(command, "delete_project");
            assert.equal(args.projectId, 8);
            return {
              projectId: 8,
              deleted: true,
            };
          },
        },
      },
    };

    const deleteProjectBButton = createButton();
    deleteProjectBButton.dataset.projectDeleteId = "8";
    deleteProjectBButton.dataset.projectName = "project-b";
    const host = createRouteHost({});
    host.querySelectorAll = (selector) => {
      if (selector === "[data-project-delete-id]") {
        return [deleteProjectBButton];
      }
      return [];
    };
    const store = createStore({
      ...createState({
      session: {
        projectId: 7,
        projectName: "project-a",
      },
      initializer: {
        existingProjects: [
          {
            projectId: 7,
            projectName: "project-a",
            createdAt: "1710000000",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [12],
            chrAssignmentMinCoveragePercent: 60,
          },
          {
            projectId: 8,
            projectName: "project-b",
            createdAt: "1710000100",
            referenceGenomeId: 2,
            primaryDatasetId: 21,
            supportDatasetIds: [22],
            chrAssignmentMinCoveragePercent: 70,
          },
        ],
      },
      }),
      projectExport: {
        loading: false,
        loaded: true,
        error: "",
        projectId: 8,
        chromosomes: [{ chrName: "ChrOld" }],
        finalPathByChr: {
          ChrOld: { segments: [{ segmentId: "old" }] },
        },
        primaryCtgsByChr: {
          ChrOld: [{ assemblyCtgId: 8 }],
        },
      },
    });

    bindWorkspacePage(host, store);
    await deleteProjectBButton.click();

    assert.deepEqual(
      store.getState().initializer.existingProjects.map((project) => project.projectId),
      [7],
    );
    assert.equal(store.getState().session.projectId, 7);
    assert.equal(store.getState().session.projectName, "project-a");
    assert.equal(store.getState().projectExport.projectId, null);
    assert.deepEqual(store.getState().projectExport.finalPathByChr, {});
    assert.deepEqual(store.getState().projectExport.chromosomes, []);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("server-owned selected-project chr threshold input ignores typing", async () => {
  const previousDocument = globalThis.document;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };

    const thresholdInput = createInput("60");
    const host = createRouteHost({
      "#selected-project-chr-assignment-threshold-input": thresholdInput,
    });
    const store = createStore(createState({
      session: {
        projectId: 7,
        projectName: "project_editable",
      },
      initializer: {
        packageMetadata: {
          packageMode: "fast",
          sequenceLayout: "partitioned",
          preassignedChr: true,
          chrAssignmentMinCoveragePercent: 60,
          selfAlignmentScope: "chr_partition",
          crossAlignmentScope: "chr_partition",
        },
        existingProjects: [
          {
            projectId: 7,
            projectName: "project_editable",
            createdAt: "1710000000",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [12],
            chrAssignmentMinCoveragePercent: 60,
            isProcessed: false,
          },
        ],
      },
    }));

    bindWorkspacePage(host, store);
    await thresholdInput.input("101");

    assert.equal(host.renderCount, 0);
    assert.equal(store.getState().initializer.editChrAssignmentMinCoveragePercentInput, "60");

    await thresholdInput.blur();

    assert.equal(store.getState().initializer.editChrAssignmentMinCoveragePercentInput, "60");
    assert.equal(host.renderCount, 0);
  } finally {
    globalThis.document = previousDocument;
  }
});

test("server-owned create-project chr threshold input ignores typing", async () => {
  const previousDocument = globalThis.document;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };

    const thresholdInput = createInput("60");
    const host = createRouteHost({
      "#initializer-chr-assignment-threshold-input": thresholdInput,
    });
    const store = createStore(createState({
      initializer: {
        createModalOpen: true,
        chrAssignmentMinCoveragePercentInput: "60",
        packageMetadata: {
          packageMode: "fast",
          sequenceLayout: "partitioned",
          preassignedChr: true,
          chrAssignmentMinCoveragePercent: 60,
          selfAlignmentScope: "chr_partition",
          crossAlignmentScope: "chr_partition",
        },
      },
    }));

    bindWorkspacePage(host, store);
    await thresholdInput.input("-110");

    assert.equal(host.renderCount, 0);
    assert.equal(store.getState().initializer.chrAssignmentMinCoveragePercentInput, "60");

    await thresholdInput.blur();

    assert.equal(store.getState().initializer.chrAssignmentMinCoveragePercentInput, "60");
    assert.equal(host.renderCount, 0);
  } finally {
    globalThis.document = previousDocument;
  }
});
