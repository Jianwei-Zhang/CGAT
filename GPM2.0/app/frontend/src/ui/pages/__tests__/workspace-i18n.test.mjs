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
    locale = "en",
    session: sessionOverrides = {},
    initializer: initializerOverrides = {},
    assembly: assemblyOverrides = {},
  } = overrides;
  return {
    locale,
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
      grtRecipe: {
        workflow: "gpm_grt_precomputed_v2",
        recipeId: "recipe-test",
        primaryDataset: "hifiasm",
        supportDatasets: ["flye", "canu"],
        readsQcEnabled: false,
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

test("project summary has no nested creation step", () => {
  const html = renderWorkspacePage(createState());
  assert.match(html, />Current project</);
  assert.match(html, />Enter Assembly</);
  assert.doesNotMatch(html, /Create Project|Existing Projects|Project Initialization/);
});

test("legacy creation state cannot expose a phased capability switch", () => {
  const html = renderWorkspacePage(createState({ initializer: { createModalOpen: true } }));
  assert.doesNotMatch(html, /initializer-phased-assembly-enabled-input|Create New Project/);
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

test("legacy directories offer every project without choosing one implicitly", () => {
  const html = renderWorkspacePage(createState({ initializer: { existingProjects: [
    { projectId: 7, projectName: "First" }, { projectId: 9, projectName: "Second" },
  ] } }));
  assert.match(html, /legacy-project-select/);
  assert.match(html, /value="7"[^>]*>First/);
  assert.match(html, /value="9"[^>]*>Second/);
  assert.match(html, /initializer-enter-assembly-button[^>]*disabled/);
});

test("Chinese project summary uses project terminology", () => {
  const html = renderWorkspacePage(createState({ locale: "zh" }));
  assert.match(html, /当前项目/);
  assert.doesNotMatch(html, /项目区|创建新项目/);
});

test("selected GRT project renders immutable recipe fields and an editable name only", () => {
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
      references: [{ referenceGenomeId: 1, name: "ref_a" }],
      datasets: [
        { datasetId: 11, name: "hifiasm", contigCount: 10, totalLengthBp: 1000 },
        { datasetId: 12, name: "flye", contigCount: 11, totalLengthBp: 2000 },
        { datasetId: 14, name: "canu", contigCount: 12, totalLengthBp: 3000 },
      ],
    },
  }));

  assert.match(
    html,
    /<input\s+id="selected-project-name-input"[\s\S]*?value="project_locked"[\s\S]*?\/>/,
  );
  assert.doesNotMatch(
    html.match(/<input\s+id="selected-project-name-input"[\s\S]*?\/>/)?.[0] || "",
    /disabled/,
  );
  assert.match(html, /class="workspace-recipe-summary"/);
  assert.match(html, /class="workspace-recipe-label">Reference Genome<\/span>/);
  assert.match(html, /class="workspace-recipe-value">ref_a<\/span>/);
  assert.match(html, /class="workspace-recipe-value">hifiasm<\/span>/);
  assert.match(html, /class="workspace-recipe-value">flye, canu<\/span>/);
  assert.match(html, /class="workspace-recipe-value is-disabled">Disabled<\/span>/);
  assert.doesNotMatch(html, /recipe-test/);
  assert.doesNotMatch(html, /Only the project name can be changed here/);
  assert.doesNotMatch(html, /id="selected-project-reference-select"/);
  assert.doesNotMatch(html, /id="selected-project-primary-dataset-select"/);
  assert.doesNotMatch(html, /id="selected-project-support-dataset-list"/);
  assert.doesNotMatch(html, /id="selected-project-chr-assignment-threshold-input"/);
  assert.doesNotMatch(html, /id="selected-project-phased-assembly-enabled-input"/);
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

test("synthetic legacy phased control is ignored", async () => {
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
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, true);

    await saveButton.click();

    assert.equal(calls.length, 0);
    assert.equal(store.getState().initializer.existingProjects[0].phasedAssemblyEnabled, true);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, true);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("selected-project rename preserves the locked GRT recipe fields", async () => {
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
            assert.equal(args.request.projectId, 7);
            assert.equal(args.request.projectName, "project_renamed");
            assert.equal(args.request.referenceGenomeId, 1);
            assert.equal(args.request.primaryDatasetId, 11);
            assert.deepEqual(args.request.supportDatasetIds, [12]);
            assert.equal(args.request.phasedAssemblyEnabled, false);
            return {
              projectId: 7,
              projectName: "project_renamed",
              referenceGenomeId: 1,
              primaryDatasetId: 11,
              supportDatasetIds: [12],
              phasedAssemblyEnabled: false,
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
    assert.equal(store.getState().initializer.existingProjects[0].referenceGenomeId, 1);
    assert.equal(store.getState().initializer.existingProjects[0].primaryDatasetId, 11);
    assert.deepEqual(store.getState().initializer.existingProjects[0].supportDatasetIds, [12]);
    assert.equal(store.getState().initializer.existingProjects[0].phasedAssemblyEnabled, false);
    assert.equal(store.getState().initializer.editProjectNameInput, "project_renamed");
    assert.equal(store.getState().initializer.editPrimaryDatasetId, "11");
    assert.deepEqual(store.getState().initializer.editSupportDatasetIds, [12]);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, false);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("processed selected-project rename ignores synthetic legacy recipe controls", async () => {
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
              assert.equal(args.request.projectId, 7);
              assert.equal(args.request.projectName, "project_processed_renamed");
              assert.equal(args.request.referenceGenomeId, 1);
              assert.equal(args.request.primaryDatasetId, 11);
              assert.deepEqual(args.request.supportDatasetIds, [12]);
              assert.equal(args.request.phasedAssemblyEnabled, false);
              return {
                projectId: 7,
                projectName: "project_processed_renamed",
                referenceGenomeId: 1,
                primaryDatasetId: 11,
                supportDatasetIds: [12],
                phasedAssemblyEnabled: false,
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

    assert.equal(calls.length, 1);
    assert.deepEqual(calls.map((call) => call.command), ["update_project"]);
    assert.equal(store.getState().session.projectName, "project_processed_renamed");
    assert.equal(store.getState().initializer.existingProjects[0].projectName, "project_processed_renamed");
    assert.equal(store.getState().initializer.existingProjects[0].referenceGenomeId, 1);
    assert.equal(store.getState().initializer.existingProjects[0].primaryDatasetId, 11);
    assert.deepEqual(store.getState().initializer.existingProjects[0].supportDatasetIds, [12]);
    assert.equal(store.getState().initializer.existingProjects[0].phasedAssemblyEnabled, false);
    assert.equal(store.getState().initializer.editProjectNameInput, "project_processed_renamed");
    assert.equal(store.getState().initializer.editReferenceId, "1");
    assert.equal(store.getState().initializer.editPrimaryDatasetId, "11");
    assert.deepEqual(store.getState().initializer.editSupportDatasetIds, [12]);
    assert.equal(store.getState().initializer.editPhasedAssemblyEnabledInput, false);
    assert.equal(store.getState().initializer.autoPipelineModalOpen, false);
    assert.equal(store.getState().initializer.autoPipelineRunning, false);
    assert.deepEqual(store.getState().initializer.autoPipelineSteps, []);
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
