import test from "node:test";
import assert from "node:assert/strict";

import {
  renderManualRefinementExportPreviewModal,
  prepareFrozenManualRefinementAllPreview,
  executeFrozenManualRefinementExport,
} from "../manual-refinement-export-preview.js";
import {
  bindProjectExportPage,
  closeProjectRefinementExportPreview,
  openProjectRefinementExportPreview,
  renderProjectExportPage,
} from "../project-export-page.js";
import { previewMutationStamp } from "../../../services/preview-content-events.js";
import { buildProjectRefinementModel, renderProjectRefinementCard, runImportManualRefinementResults } from "../project-refinement-view.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState: () => state,
    setState: (patch) => {
      state = { ...state, ...patch };
    },
  };
}

test("prepareFrozenManualRefinementAllPreview reads scoped DB state and ignores stale assembly.degap from another project", async () => {
  const store = createStore({
    locale: "zh",
    session: { workspacePath: "/ws/project-b", projectId: 22, projectName: "ProjectB" },
    assembly: {
      // Stale state left over from another project must NOT be used.
      degap: {
        manualRefinement: {
          loci: [{ chr: "Chr99", kind: "gap", segmentId: "stale-gap", label: "STALE", tool: "degap" }],
        },
      },
    },
  });

  const dbQueries = [];
  const modal = await prepareFrozenManualRefinementAllPreview({
    host: null,
    store,
    workspaceRoot: "/ws/project-b",
    projectId: 22,
    projectName: "ProjectB",
    locale: "zh",
    deps: {
      getProjectAssemblyViewState: async (args) => {
        dbQueries.push(args);
        return {
          finalPathByChr: {},
          degapProjectState: {
            manualRefinement: {
              readsMode: "inherit",
              loci: [
                { chr: "Chr02", kind: "gap", segmentId: "gap-2", label: "ctg3 ↔ ctg4", tool: "quartet", tools: ["quartet", "tgsgapcloser"] },
                { chr: "Chr01", kind: "gap", segmentId: "gap-1", label: "ctg1 ↔ ctg2", tool: "degap" },
                { chr: "Chr01", kind: "tel_left", segmentId: "seg-1", label: "ctg1", motif: "TTTAGGG" },
              ],
            },
          },
        };
      },
    },
  });

  assert.deepEqual(dbQueries, [{ workspaceRoot: "/ws/project-b", projectId: 22 }]);
  assert.equal(modal.open, true);
  assert.equal(modal.loci.length, 3);
  assert.deepEqual(modal.request, {
    loci: [
      { chr: "Chr01", kind: "tel_left", segment_id: "seg-1", tools: ["degap"], motif: "TTTAGGG" },
      { chr: "Chr01", kind: "gap", segment_id: "gap-1", tools: ["degap"] },
      { chr: "Chr02", kind: "gap", segment_id: "gap-2", tools: ["tgsgapcloser", "quartet"] },
    ],
  });

  const html = renderManualRefinementExportPreviewModal(modal, store.getState());
  assert.match(html, /data-refinement-export-preview-modal="true"/);
  assert.match(html, /ProjectB · 共 3 个位点 \/ 2 条染色体/);
  assert.match(html, /data-refinement-export-preview-chr="Chr01"/);
  assert.match(html, /data-refinement-export-preview-chr="Chr02"/);
  assert.match(html, /DEGAP TelSeeker/);
  assert.match(html, /Motif: TTTAGGG/);
  assert.match(html, /TGS-GapCloser, quarTeT/);
  assert.match(html, /data-refinement-export-preview-confirm="true"/);
  assert.doesNotMatch(html, /STALE/);
});

test("executeFrozenManualRefinementExport honors cancel, confirms real export, and aborts on project switch mid-dialog", async () => {
  const baseModal = {
    open: true,
    status: "ready",
    workspaceRoot: "/ws/project-b",
    workspacePath: "/ws/project-b",
    projectId: 22,
    projectName: "ProjectB",
    readsMode: "inherit",
    loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap-1", label: "ctg1 ↔ ctg2", tool: "degap", tools: ["degap"] }],
    request: { loci: [{ chr: "Chr01", kind: "gap", segment_id: "gap-1", tools: ["degap"] }] },
    viewState: { finalPathByChr: {}, degapProjectState: {} },
  };
  const store = createStore({
    locale: "zh",
    session: { workspacePath: "/ws/project-b", projectId: 22, projectName: "ProjectB" },
  });

  // 1. OS file dialog canceled -> must NOT invoke exportManualRefinement.
  let exportCalls = 0;
  const canceled = await executeFrozenManualRefinementExport({
    host: null,
    store,
    modal: baseModal,
    deps: {
      pickSaveFilePath: async () => "",
      exportManualRefinement: async () => {
        exportCalls += 1;
        return {};
      },
    },
  });
  assert.equal(canceled.canceled, true);
  assert.equal(exportCalls, 0);

  // 2. Project switched while OS file dialog is open -> must abort without calling exportManualRefinement.
  const switched = await executeFrozenManualRefinementExport({
    host: null,
    store,
    modal: baseModal,
    deps: {
      pickSaveFilePath: async () => {
        store.setState({ session: { workspacePath: "/ws/project-c", projectId: 99, projectName: "ProjectC" } });
        return "/tmp/out.zip";
      },
      exportManualRefinement: async () => {
        exportCalls += 1;
        return {};
      },
    },
  });
  assert.equal(switched.switched, true);
  assert.equal(exportCalls, 0);

  // 3. Confirmed export on matching project -> calls real exportManualRefinement with frozen payload.
  store.setState({ session: { workspacePath: "/ws/project-b", projectId: 22, projectName: "ProjectB" } });
  const receivedPayloads = [];
  const confirmed = await executeFrozenManualRefinementExport({
    host: null,
    store,
    modal: baseModal,
    deps: {
      exportTimestamp: "20261123033000",
      pickSaveFilePath: async () => "/tmp/project_b_all.zip",
      exportManualRefinement: async (payload) => {
        receivedPayloads.push(payload);
        return { batch_sha256: "1234567890abcdef", loci: 1, tasks: 1 };
      },
      getProjectAssemblyViewState: async () => ({ finalPathByChr: {}, degapProjectState: {} }),
      setProjectAssemblyViewState: async () => assert.fail("export must not write the project view state"),
    },
  });
  assert.equal(confirmed.ok, true);
  assert.equal(receivedPayloads.length, 1);
  assert.equal(receivedPayloads[0].workspaceRoot, "/ws/project-b");
  assert.equal(receivedPayloads[0].projectId, 22);
  assert.equal(receivedPayloads[0].outputPath, "/tmp/project_b_all.zip");
  assert.deepEqual(receivedPayloads[0].request, baseModal.request);
  assert.equal(confirmed.receipt.batchSha256, "1234567890abcdef");
});

test("bindProjectExportPage intercepts data-project-export-action=refinement-all to open preview modal before OS save picker", async () => {
  const workspacePath = "/ws/project-menu";
  const projectId = 42;
  const store = createStore({
    locale: "zh",
    activeRoute: "projectExport",
    session: { workspacePath, projectId, projectName: "MenuProj" },
    initializer: {
      datasets: [{ datasetId: 1, name: "hifiasm", fastaAvailable: true }],
      existingProjects: [{ projectId, projectName: "MenuProj", primaryDatasetId: 1, supportDatasetIds: [] }],
    },
    assembly: {
      // Stale degap state from another project must never leak into the menu preview.
      degap: {
        manualRefinement: {
          loci: [{ chr: "Chr88", kind: "gap", segmentId: "wrong-gap", label: "WRONG", tool: "degap" }],
        },
      },
    },
    projectExport: {
      loaded: true,
      loading: false,
      workspacePath,
      projectId,
      mutationStamp: previewMutationStamp({ workspaceRoot: workspacePath, projectId }),
      chromosomes: [{ chrName: "Chr01" }],
      finalPathByChr: {},
      primaryCtgsByChr: {},
      ctgsByChr: {},
    },
  });

  const initialHtml = renderProjectExportPage(store.getState());
  assert.match(initialHtml, /data-project-export-action="all"/);
  assert.match(initialHtml, /data-project-export-action="refinement-all"/);

  const listeners = new Map();
  const host = {
    isConnected: true,
    innerHTML: initialHtml,
    addEventListener(type, fn) {
      const list = listeners.get(type) || [];
      list.push(fn);
      listeners.set(type, list);
    },
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };

  let pickerCalls = 0;
  const exportPayloads = [];
  bindProjectExportPage(host, store, {
    flushAssemblyProjectState: async () => {},
    getProjectAssemblyViewState: async (args) => {
      assert.deepEqual(args, { workspaceRoot: workspacePath, projectId });
      return {
        finalPathByChr: {},
        degapProjectState: {
          manualRefinement: {
            readsMode: "inherit",
            loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap-1", label: "ctg1 ↔ ctg2", tool: "tgsgapcloser" }],
          },
        },
      };
    },
    setProjectAssemblyViewState: async () => assert.fail("export must not write the project view state"),
    exportTimestamp: "20261123033500",
    pickSaveFilePath: async () => {
      pickerCalls += 1;
      return "/tmp/menu_proj_all.zip";
    },
    exportManualRefinement: async (payload) => {
      exportPayloads.push(payload);
      return { batch_sha256: "fedcba9876543210", loci: 1, tasks: 1 };
    },
  });

  const dispatchClick = async (dataset) => {
    const target = {
      dataset,
      closest(selector) {
        if (selector === "[data-project-export-action]" && dataset.projectExportAction) return target;
        if (selector === "[data-refinement-export-preview-cancel]" && dataset.refinementExportPreviewCancel) return target;
        if (selector === "[data-refinement-export-preview-confirm]" && dataset.refinementExportPreviewConfirm) return target;
        return null;
      },
    };
    for (const handler of listeners.get("click") || []) {
      await handler({ target });
    }
  };

  // Step 1: Click menu item -> opens preview modal ONLY, zero picker/export calls.
  await dispatchClick({ projectExportAction: "refinement-all" });
  assert.equal(pickerCalls, 0);
  assert.equal(exportPayloads.length, 0);
  const modalAfterMenuClick = store.getState().projectExport.refinementExportModal;
  assert.equal(modalAfterMenuClick?.open, true);
  assert.equal(modalAfterMenuClick?.status, "ready");
  assert.deepEqual(modalAfterMenuClick?.request, {
    loci: [{ chr: "Chr01", kind: "gap", segment_id: "gap-1", tools: ["tgsgapcloser"] }],
  });

  // Step 2: Click cancel -> closes modal, still zero picker/export calls.
  await dispatchClick({ refinementExportPreviewCancel: "true" });
  assert.equal(store.getState().projectExport.refinementExportModal, null);
  assert.equal(pickerCalls, 0);
  assert.equal(exportPayloads.length, 0);

  // Step 3: Re-open via menu item and click confirm -> opens picker and calls real exportManualRefinement.
  await dispatchClick({ projectExportAction: "refinement-all" });
  await dispatchClick({ refinementExportPreviewConfirm: "true" });
  assert.equal(pickerCalls, 1);
  assert.equal(exportPayloads.length, 1);
  assert.equal(exportPayloads[0].workspaceRoot, workspacePath);
  assert.equal(exportPayloads[0].projectId, projectId);
  assert.equal(exportPayloads[0].outputPath, "/tmp/menu_proj_all.zip");
  assert.equal(store.getState().projectExport.refinementExportModal?.status, "success");
});

test("canceling while the job list loads cannot reopen the export confirmation", async () => {
  const store = createStore({ session: { workspacePath: "/ws/cancel", projectId: 22 } });
  let resolveList;
  const pendingList = new Promise(resolve => { resolveList = resolve; });
  const opening = openProjectRefinementExportPreview(null, store, {
    flushAssemblyProjectState: async () => {},
    getProjectAssemblyViewState: async () => pendingList,
  });
  assert.equal(store.getState().projectExport.refinementExportModal.status, "loading");
  closeProjectRefinementExportPreview(null, store);
  resolveList({ degapProjectState: { manualRefinement: { loci: [{ chr: "Chr01", kind: "gap", segmentId: "gap" }] } } });
  assert.equal(await opening, false);
  assert.equal(store.getState().projectExport.refinementExportModal, null);
});

test("a reopened project shows native export receipts, and stops marking an imported batch as pending", () => {
  const batchSha256 = "b".repeat(64);
  const state = {
    locale: "en",
    session: { workspacePath: "/work/project", projectId: 23 },
    projectExport: {
      workspacePath: "/work/project",
      projectId: 23,
      manualRefinementExports: [{ batchSha256, outputFileName: "Precise tasks.zip", exportedAtMs: 1760000000000,
        lociCount: 1, tasksCount: 1, loci: [{ chr: "Chr03", kind: "gap", segmentId: "segment-gap", tools: ["degap"] }] }],
    },
  };
  assert.equal(buildProjectRefinementModel(state).manual.exportedBatches.length, 1);
  assert.match(renderProjectRefinementCard(state), /python \.lib\/tools\/refine\.py 'Precise tasks\.zip'/);
  state.projectExport.manualRefinementResults = [{ batchSha256, resultSha256: "c".repeat(64), loci: [] }];
  assert.equal(buildProjectRefinementModel(state).manual.exportedBatches.length, 0);
  state.session.workspacePath = "/other/project"; // identical numeric ID in a different workspace
  assert.equal(buildProjectRefinementModel(state).manual.importedResults.length, 0);
});


test("one refinement table compares both automatic tools alongside a manual batch with filled/total and chr counts", async () => {
  const { normalizeGrtProjectView } = await import("../assembly/grt-state.js");
  const grt = normalizeGrtProjectView({ recipe: { schema_version: "5" }, auto_refinement_effects: [
    { tool: "degap", version_id: "d".repeat(64), project_adopted_gaps: 0, accepted_edits: 1, closed: 0, partial: 1, unfilled: 3, rejected: 0 },
    { tool: "quartet", accepted_edits: 2, closed: 2, partial: 0, unfilled: 1, rejected: 1 },
  ] });
  const state = { locale: "zh", session: { projectId: 2, workspacePath: "/col0" },
    projectExport: { projectId: 2, workspacePath: "/col0", grtProjectView: grt,
      manualRefinementResults: [{ resultSha256: "a".repeat(64), batchSha256: "b".repeat(64), applied: 1,
        loci: [{ locusId: "g1", chr: "Chr01", kind: "gap", disposition: "applied", candidates: [
          { tool: "quartet", status: "partial" }, { tool: "degap", status: "closed" }] }] }] } };
  const html = renderProjectRefinementCard(state);
  const table = html.match(/<table [^>]*>[\s\S]+?<\/table>/g);
  assert.equal(table.length, 1);
  assert.match(table[0], /自动精修[\s\S]*?DEGAP<\/th>[\s\S]*?0 \/ 4/);
  assert.match(table[0], /quarTeT<\/th>[\s\S]*?2 \/ 4/);
  assert.match(table[0], /手动精修[\s\S]*?#bbbbbb[\s\S]*?1 \/ 1[\s\S]*?<span class="project-refinement-chr-list">Chr01<\/span>/);
  assert.match(table[0], /项目采用过 0 个 Gap/);
  assert.match(table[0], /data-preview-version="d{64}"/);
  state.initializer = { projectRefinementUi: { projectKey: "/col0::2", expandedBatchKey: `imported:${"b".repeat(64)}` } };
  Object.assign(state.projectExport.manualRefinementResults[0].loci[0], {adoptionState: "active", adoptionRevision: 1, activeTool: "degap"});
  state.projectExport.manualRefinementResults[0].loci[0].candidates[0].switchable = true;
  const expanded = renderProjectRefinementCard(state);
  assert.match(expanded, /data-project-refinement-undo/);
  assert.doesNotMatch(expanded, /data-project-refinement-switch/);
  assert.doesNotMatch(table[0], /data-app-tooltip="Chr01"/);
  assert.doesNotMatch(html, /部分填补|未填补|拒绝/);
  assert.match(html, /<h3 id="project-refinement-title"><button[^>]*data-overview-section-toggle="refinement"[^>]*>[\s\S]*?<span>精修<\/span><\/button><\/h3>\s*<span class="project-section-count"><span aria-hidden="true">·<\/span>4<\/span>/);
  assert.match(html, /<header[^>]*>[\s\S]*?aria-label="导入精修补丁" data-app-tooltip="导入精修补丁"[\s\S]*?<svg[^>]*aria-hidden="true"[\s\S]*?<\/button>[\s\S]*?<\/header>/);
  assert.doesNotMatch(html, /project-refinement-(grid|pane)|<select/);
});

test("pre-summary auto refinement does not guess closures, derives total gaps from baseline and truncates long chromosome lists with head/tail and tooltip", () => {
  const baselineFinalPathByChr = {};
  for (const chrName of ["Chr10", "Chr2", "Chr1", "Chr5", "Chr3", "Chr4"]) {
    baselineFinalPathByChr[chrName] = {
      chrName,
      segments: [
        {
          segmentId: `seg-${chrName}`,
          type: "ctg",
          ctgName: `patch_${chrName}`,
          refinement: { mode: "automatic", tool: "degap", editId: `e-${chrName}`, originalGapIds: [`gap-${chrName}`] },
        },
        ...(chrName === "Chr1" || chrName === "Chr2"
          ? [{ segmentId: `open-${chrName}`, type: "gap", gapSizeBp: 500 }]
          : []),
      ],
    };
  }
  const state = {
    locale: "zh",
    session: { projectId: 9, workspacePath: "/pre-summary" },
    projectExport: {
      projectId: 9,
      workspacePath: "/pre-summary",
      grtProjectView: { recipe: { schemaVersion: "5" }, baselineFinalPathByChr, autoRefinementEffects: [], sourceCards: [] },
    },
  };
  const html = renderProjectRefinementCard(state);
  assert.match(html, /DEGAP<\/th>[\s\S]*?— \/ 8/);
  assert.match(
    html,
    /<span class="project-refinement-chr-list is-truncated" data-app-tooltip="Chr1, Chr2, Chr3, Chr4, Chr5, Chr10">Chr1, Chr2, \.\.\., Chr10<\/span>/,
  );
});

test("one patch picker imports all automatic tools and distinguishes a repeated import", async () => {
  const store = createStore({ locale: "en", initializer: {}, session: { workspacePath: "/ws", projectId: 6 } });
  let calls = 0;
  const deps = {
    pickZipFilePath: async () => "/renamed.zip",
    flushAssemblyProjectState: async () => {},
    getProjectAssemblyViewState: async () => ({}),
    getGrtProjectView: async () => ({}),
    listManualRefinementResults: async () => [],
    reloadProjectOverviewData: async () => {},
    importManualRefinementResults: async ({ workspaceRoot, projectId, zipPath }) => {
      assert.deepEqual([workspaceRoot, projectId, zipPath], ["/ws", 6, "/renamed.zip"]);
      return calls++ === 0
        ? { kind: "automatic", addedTools: ["degap", "tgsgapcloser"], duplicate: false, applied: 2 }
        : { kind: "automatic", addedTools: [], duplicate: true };
    },
  };
  assert.equal(await runImportManualRefinementResults(null, store, null, deps), true);
  assert.match(store.getState().initializer.projectRefinementUi.notice, /2 gap closures adopted/);
  assert.equal(await runImportManualRefinementResults(null, store, null, deps), true);
  assert.match(store.getState().initializer.projectRefinementUi.notice, /already in this project/);
});
