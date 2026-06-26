import test from "node:test";
import assert from "node:assert/strict";
import { renderImporterPage } from "../importer-page.js";
import { renderWorkspacePage } from "../workspace-page.js";

test("importer page renders english labels when locale is en", () => {
  const html = renderImporterPage({
    locale: "en",
    importer: {
      stages: [],
      historyValidation: {},
      deleteTargets: [],
      openWorkspacePath: "",
      zipPath: "",
      workspaceRoot: "",
      extractedPath: "",
      deleteConfirmOpen: false,
      deleteWithFiles: false,
      inFlight: false,
      status: "Not started",
      summary: "Import summary",
    },
  });

  assert.match(html, />Import and Open Project Area</);
  assert.match(html, />1A\. Import ZIP bundle</);
  assert.match(html, />2\. Open existing project area</);
  assert.match(html, />Validate history</);
  assert.match(html, />No history yet\.</);
});

test("workspace page renders english labels when locale is en", () => {
  const state = {
    locale: "en",
    session: { workspacePath: "D:/ws", projectId: null, projectName: "" },
    initializer: {
      existingProjects: [],
      selectedReferenceId: "",
      selectedPrimaryDatasetId: "",
      selectedSupportDatasetIds: [],
      references: [],
      datasets: [],
      projectNameInput: "",
      chrAssignmentMinCoveragePercentInput: "60",
      createModalOpen: false,
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
      optionsError: "",
      summary: "Fill in the project information and create a project.",
    },
    assembly: {
      loading: false,
      error: "",
      bootstrapping: false,
      summary: "Select a project to load the assembly main view.",
      subviewTrackView: {
        alignmentLength: 10000,
      },
    },
  };
  const html = renderWorkspacePage(state);

  assert.match(html, />Project Initialization</);
  assert.match(html, />Project Area</);
  assert.match(html, />Existing Projects</);
  assert.match(html, />Create Project</);
  assert.match(html, />Enter Assembly</);
  assert.equal(state.assembly.subviewTrackView?.alignmentLength, 10000);
});
