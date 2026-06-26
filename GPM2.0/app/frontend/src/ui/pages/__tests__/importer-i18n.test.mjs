import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  __testCreateImporterStatusToastDismissCoordinator,
  bindImporterPage,
  renderImporterPage,
} from "../importer-page.js";
import { en, zh } from "../../i18n/messages/importer.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };
}

function createButton() {
  const listeners = new Map();
  return {
    dataset: {},
    disabled: false,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    click() {
      const handler = listeners.get("click");
      if (handler) {
        return handler({ currentTarget: this, target: this });
      }
      return undefined;
    },
    contextmenu({ clientX = 0, clientY = 0 } = {}) {
      const handler = listeners.get("contextmenu");
      if (handler) {
        return handler({
          currentTarget: this,
          target: this,
          clientX,
          clientY,
          preventDefault() {},
          stopPropagation() {},
        });
      }
      return undefined;
    },
    pointerenter() {
      const handler = listeners.get("pointerenter");
      if (handler) {
        return handler({ currentTarget: this, target: this });
      }
      return undefined;
    },
    pointerleave() {
      const handler = listeners.get("pointerleave");
      if (handler) {
        return handler({ currentTarget: this, target: this });
      }
      return undefined;
    },
  };
}

function createScrollList({ scrollHeight = 1000, clientHeight = 200, scrollTop = 0 } = {}) {
  const listeners = new Map();
  return {
    scrollHeight,
    clientHeight,
    scrollTop,
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    scroll() {
      const handler = listeners.get("scroll");
      if (handler) {
        handler({ currentTarget: this, target: this });
      }
    },
  };
}

function createHost(buttons = {}) {
  const nodeMap = new Map(Object.entries(buttons));
  return {
    innerHTML: "",
    closest(selector) {
      return selector === "#route-host" ? this : null;
    },
    querySelector(selector) {
      return nodeMap.get(selector) || null;
    },
    querySelectorAll(selector) {
      const value = nodeMap.get(selector);
      if (Array.isArray(value)) {
        return value;
      }
      return value ? [value] : [];
    },
  };
}

function createImporterScrollState(overrides = {}) {
  return {
    locale: "zh",
    session: {
      workspacePath: "",
      projectName: "",
      projectId: null,
    },
    importer: {
      zipPath: "",
      workspaceRoot: "",
      extractedPath: "",
      openWorkspacePath: "",
      historyValidation: {},
      deleteConfirmOpen: false,
      deleteWithFiles: false,
      deleteTargets: [],
      inFlight: true,
      importRunId: "import-test",
      importCancelling: false,
      status: "导入中",
      stages: ["stage-1", "stage-2"],
      summary: "正在导入",
      ...overrides,
    },
    initializer: {
      references: [],
      datasets: [],
      existingProjects: [],
    },
    activeRoute: "importer",
  };
}

test("importer add-package labels and errors are translated in Chinese and English", () => {
  assert.equal(zh.buttons.importAddPackage, "导入追加包");
  assert.equal(zh.runtime.importAddPackageSummary, "正在导入数据集追加包。");
  assert.equal(zh.runtime.incompleteAddPackageWorkspaceSummary, "请先加载已有项目区。");
  assert.equal(zh.runtime.incompleteAddPackageZipSummary, "请先选择数据集追加包 zip。");
  assert.equal(zh.runtime.importAddPackageDoneStage, "数据集追加包导入完成并刷新候选项");
  assert.equal(zh.runtime.addPackageHint, "（added {datasetName}）");
  assert.equal(zh.runtime.importFailedSummary, "导入失败：{message}");
  assert.equal(zh.runtime.tauriImportAddPackageStage, "调用后端 import_add_dataset_package");

  assert.equal(en.buttons.importAddPackage, "Import add package");
  assert.equal(en.runtime.importAddPackageSummary, "Importing the dataset add package.");
  assert.equal(en.runtime.incompleteAddPackageWorkspaceSummary, "Open an existing project area first.");
  assert.equal(en.runtime.incompleteAddPackageZipSummary, "Select a dataset add-package ZIP first.");
  assert.equal(en.runtime.importAddPackageDoneStage, "Dataset add package imported and options refreshed");
  assert.equal(en.runtime.addPackageHint, "(added {datasetName})");
  assert.equal(en.runtime.importFailedSummary, "Import failed: {message}");
  assert.equal(en.runtime.tauriImportAddPackageStage, "Invoke backend import_add_dataset_package");
});

test("importer renders concise failed import feedback while keeping open-workspace option visible", () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      localStorage: {
        getItem() {
          return null;
        },
      },
    };
    const html = renderImporterPage({
      locale: "zh",
      session: {
        workspacePath: "",
        projectName: "",
        projectId: null,
      },
      importer: {
        zipPath: "D:/Desktop/bad.no_fasta.zip",
        workspaceRoot: "D:/Desktop/test2",
        extractedPath: "",
        openWorkspacePath: "",
        historyValidation: {},
        deleteConfirmOpen: false,
        deleteWithFiles: false,
        deleteTargets: [],
        inFlight: false,
        status: "导入失败",
        stages: ["validate_input", "extract_bundle"],
        summary: "导入失败：failed to resolve source_seq for locator gpm:contig_6792",
      },
      initializer: {
        references: [],
        datasets: [],
        existingProjects: [],
      },
    });

    assert.match(html, /data-importer-status-toast="1"/);
    assert.match(html, /data-importer-status-banner="1" role="alert"/);
    assert.match(html, /导入失败：failed to resolve source_seq for locator gpm:contig_6792/);
    assert.match(html, /2\. 从已有项目区加载/);
    assert.doesNotMatch(html, /modal-overlay import-progress-overlay/);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("importer does not render loaded-project add-package actions", () => {
  const html = renderImporterPage({
    locale: "en",
    session: {
      workspacePath: "/tmp/workspace",
      projectName: "",
      projectId: null,
    },
    importer: {
      zipPath: "",
      workspaceRoot: "/tmp/workspace",
      extractedPath: "",
      openWorkspacePath: "/tmp/workspace",
      historyValidation: {},
      deleteConfirmOpen: false,
      deleteWithFiles: false,
      deleteTargets: [],
      inFlight: false,
      status: "",
      stages: [],
      summary: "",
    },
    initializer: {
      existingProjects: [
        {
          projectId: 42,
          projectName: "draft-assembly",
          createdAt: "2026-05-15T01:02:03Z",
        },
      ],
    },
  });

  assert.doesNotMatch(html, /draft-assembly/);
  assert.doesNotMatch(html, /data-import-add-package-project-id="42"/);
  assert.doesNotMatch(html, /<h4>Loaded projects<\/h4>/);
});

test("importer workspace history row imports add package without project id and shows added hint", async () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  const previousFetch = globalThis.fetch;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      __TAURI__: null,
      prompt() {
        return "D:/packages/add_new_ds.zip";
      },
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return JSON.stringify([{ path: "D:/ws", lastUsedAt: 1770000000000 }]);
        },
        setItem() {},
      },
    };
    globalThis.setTimeout = (callback, delay) => ({ callback, delay, cancelled: false });
    globalThis.clearTimeout = (timer) => {
      if (timer) {
        timer.cancelled = true;
      }
    };
    let importPayload = null;
    const importDatasetNames = ["new_ds", "new_ds2"];
    let importCallIndex = 0;
    globalThis.fetch = async (path, options) => {
      assert.equal(path, "/api/import-add-dataset-package");
      importPayload = JSON.parse(options.body);
      const importedDatasetName = importDatasetNames[importCallIndex] || "new_ds";
      importCallIndex += 1;
      return {
        ok: true,
        async json() {
          return {
            workspaceRoot: "D:/ws",
            packageMetadata: {
              packageMode: "fast",
              sequenceLayout: "partitioned",
              preassignedChr: true,
              chrAssignmentMinCoveragePercent: 60,
              selfAlignmentScope: "chr_partition",
              crossAlignmentScope: "chr_partition",
            },
            references: [{ referenceGenomeId: 1, name: "Ref" }],
            datasets: [
              { datasetId: 11, name: "primary", label: "primary", contigCount: 1, totalLengthBp: 4 },
              { datasetId: 22, name: "old_ds", label: "old_ds", contigCount: 1, totalLengthBp: 4 },
              { datasetId: 33, name: importedDatasetName, label: importedDatasetName, contigCount: 1, totalLengthBp: 4 },
            ],
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
            datasetId: 33,
            datasetName: importedDatasetName,
            stages: ["validate_input", "complete"],
            message: "done",
          };
        },
      };
    };

    const recentButton = createButton();
    recentButton.dataset.recentPath = "D:/ws";
    const importAddPackageButton = createButton();
    importAddPackageButton.dataset.workspaceImportAddPackagePath = "D:/ws";
    const host = createHost({
      "[data-recent-index]": [recentButton],
      "[data-workspace-import-add-package-path]": importAddPackageButton,
      "[data-workspace-history-context-menu='1']": createButton(),
    });
    const store = createStore({
      activeRoute: "importer",
      locale: "en",
      session: {
        workspacePath: "D:/ws",
        projectName: "",
        projectId: null,
      },
      importer: {
        zipPath: "",
        workspaceRoot: "",
        extractedPath: "",
        openWorkspacePath: "D:/ws",
        historyValidation: {},
        deleteConfirmOpen: false,
        deleteWithFiles: false,
        deleteTargets: [],
        inFlight: false,
        status: "",
        stages: [],
        summary: "",
      },
      initializer: {
        packageMetadata: null,
        references: [],
        datasets: [
          { datasetId: 11, name: "primary", label: "primary", contigCount: 1, totalLengthBp: 4 },
          { datasetId: 22, name: "old_ds", label: "old_ds", contigCount: 1, totalLengthBp: 4 },
        ],
        existingProjects: [
          {
            projectId: 7,
            projectName: "Project A",
            referenceGenomeId: 1,
            primaryDatasetId: 11,
            supportDatasetIds: [22],
          },
        ],
      },
    });

    bindImporterPage(host, store);
    recentButton.contextmenu({ clientX: 12, clientY: 24 });
    assert.match(renderImporterPage(store.getState()), /data-workspace-history-context-menu="1"/);
    assert.match(renderImporterPage(store.getState()), /Import add package/);

    bindImporterPage(host, store);
    await importAddPackageButton.click();

    assert.deepEqual(importPayload, {
      workspaceRoot: "D:/ws",
      zipPath: "D:/packages/add_new_ds.zip",
    });
    assert.deepEqual(store.getState().initializer.existingProjects[0].supportDatasetIds, [22]);
    assert.equal(store.getState().initializer.datasets.some((dataset) => dataset.name === "new_ds"), true);
    assert.match(renderImporterPage(store.getState()), /class="add-package-hint">\(<strong>added<\/strong> new_ds\)<\/span>/);

    await importAddPackageButton.click();

    assert.equal(store.getState().initializer.datasets.some((dataset) => dataset.name === "new_ds2"), true);
    assert.match(
      renderImporterPage(store.getState()),
      /class="add-package-hint">\(<strong>added<\/strong> new_ds,new_ds2\)<\/span>/,
    );

    store.setState({ locale: "zh" });
    assert.match(
      renderImporterPage(store.getState()),
      /class="add-package-hint">（<strong>added<\/strong> new_ds,new_ds2）<\/span>/,
    );
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.fetch = previousFetch;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("importer workspace history add-package menu auto-hides on leave and closes on click", async () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      __TAURI__: null,
      prompt() {
        return "";
      },
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return JSON.stringify([{ path: "D:/ws", lastUsedAt: 1770000000000 }]);
        },
        setItem() {},
      },
    };

    const timers = [];
    globalThis.setTimeout = (callback, delay) => {
      const timer = { callback, delay, cancelled: false };
      timers.push(timer);
      return timer;
    };
    globalThis.clearTimeout = (timer) => {
      if (timer) {
        timer.cancelled = true;
      }
    };
    const runTimers = () => {
      for (const timer of timers.splice(0)) {
        if (!timer.cancelled) {
          timer.callback();
        }
      }
    };

    const recentButton = createButton();
    recentButton.dataset.recentPath = "D:/ws";
    const historyRow = createButton();
    historyRow.dataset.workspaceHistoryRowPath = "D:/ws";
    const menu = createButton();
    menu.dataset.workspaceHistoryContextMenuPath = "D:/ws";
    const importAddPackageButton = createButton();
    importAddPackageButton.dataset.workspaceImportAddPackagePath = "D:/ws";
    const host = createHost({
      "[data-recent-index]": [recentButton],
      "[data-workspace-history-row-path]": [historyRow],
      "[data-workspace-history-context-menu='1']": menu,
      "[data-workspace-import-add-package-path]": importAddPackageButton,
    });
    const store = createStore({
      activeRoute: "importer",
      locale: "en",
      session: {
        workspacePath: "D:/ws",
        projectName: "",
        projectId: null,
      },
      importer: {
        zipPath: "",
        workspaceRoot: "",
        extractedPath: "",
        openWorkspacePath: "D:/ws",
        historyValidation: {},
        deleteConfirmOpen: false,
        deleteWithFiles: false,
        deleteTargets: [],
        inFlight: false,
        status: "",
        stages: [],
        summary: "",
      },
      initializer: {
        packageMetadata: null,
        references: [],
        datasets: [],
        existingProjects: [],
      },
    });

    bindImporterPage(host, store);
    recentButton.contextmenu({ clientX: 12, clientY: 24 });
    bindImporterPage(host, store);
    historyRow.pointerleave();
    assert.equal(timers[0]?.delay, 400);
    assert.equal(store.getState().importer.workspaceContextMenu.open, true);
    runTimers();
    assert.equal(store.getState().importer.workspaceContextMenu, null);

    recentButton.contextmenu({ clientX: 12, clientY: 24 });
    bindImporterPage(host, store);
    historyRow.pointerleave();
    menu.pointerenter();
    runTimers();
    assert.equal(store.getState().importer.workspaceContextMenu.open, true);

    await importAddPackageButton.click();
    assert.equal(store.getState().importer.workspaceContextMenu, null);
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("importer add-package hint keeps added black and dataset names bold", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.list-item-button\s+\.add-package-hint\s*\{[^}]*color:\s*#2c6b2f;[^}]*font-weight:\s*700;/,
  );
  assert.match(
    css,
    /\.list-item-button\s+\.add-package-hint\s+strong\s*\{[^}]*color:\s*#111111;[^}]*font-weight:\s*700;/,
  );
});

test("importer feedback renders as a fixed toast instead of an inline banner", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.importer-status-toast-wrap\s*\{[^}]*position:\s*fixed;[^}]*top:\s*72px;[^}]*right:\s*24px;/,
  );
  assert.match(
    css,
    /\.importer-status-toast\s*\{[^}]*box-shadow:\s*0 4px 16px rgba\(0, 0, 0, 0\.12\);/,
  );
  assert.doesNotMatch(css, /\.importer-status-banner\s*\{/);
});

test("importer feedback toast dismisses after one second", () => {
  const timers = [];
  const dismissed = [];
  const coordinator = __testCreateImporterStatusToastDismissCoordinator({
    setTimeoutFn(callback, delay) {
      const timer = { callback, delay, cancelled: false };
      timers.push(timer);
      return timer;
    },
    clearTimeoutFn(timer) {
      if (timer) {
        timer.cancelled = true;
      }
    },
    onDismiss() {
      dismissed.push(true);
    },
  });

  coordinator.onFeedbackChange("Incomplete parameters\u0000Fill in both paths.");
  coordinator.onFeedbackChange("Incomplete parameters\u0000Fill in both paths.");
  assert.equal(timers.length, 1);
  assert.equal(timers[0].delay, 1000);
  timers[0].callback();
  assert.deepEqual(dismissed, [true]);
});

test("importer english missing-parameter feedback stays translated after binding", async () => {
  const previousDocument = globalThis.document;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    const timers = [];
    globalThis.setTimeout = (callback, delay) => {
      const timer = { callback, delay, cancelled: false };
      timers.push(timer);
      return timer;
    };
    globalThis.clearTimeout = (timer) => {
      if (timer) {
        timer.cancelled = true;
      }
    };
    const importZipStartButton = createButton();
    const host = createHost({
      "#import-zip-start-button": importZipStartButton,
    });
    const store = createStore({
      activeRoute: "importer",
      locale: "en",
      session: {
        workspacePath: "",
        projectName: "",
        projectId: null,
      },
      importer: {
        zipPath: "",
        workspaceRoot: "",
        extractedPath: "",
        openWorkspacePath: "",
        historyValidation: {},
        deleteConfirmOpen: false,
        deleteWithFiles: false,
        deleteTargets: [],
        inFlight: false,
        status: "",
        stages: [],
        summary: "",
      },
      initializer: {
        references: [],
        datasets: [],
        existingProjects: [],
      },
    });

    bindImporterPage(host, store);
    await importZipStartButton.click();

    const nextImporter = store.getState().importer;
    assert.equal(nextImporter.status, "Incomplete parameters");
    assert.equal(nextImporter.summary, "Fill in both the ZIP path and project area directory.");
    assert.equal(timers.at(-1)?.delay, 1000);
    timers.at(-1).callback();
    assert.equal(store.getState().importer.status, "");
    assert.equal(store.getState().importer.summary, "");
  } finally {
    globalThis.document = previousDocument;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("opening an existing workspace does not rerender importer content after switching to workspace route", async () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  try {
    globalThis.document = {
      querySelector() {
        return null;
      },
    };
    globalThis.window = {
      __TAURI__: null,
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return null;
        },
        setItem() {},
        removeItem() {},
      },
    };

    const openWorkspaceButton = createButton();
    const host = createHost({
      "#open-workspace-button": openWorkspaceButton,
    });
    const store = createStore({
      activeRoute: "importer",
      locale: "zh",
      session: {
        workspacePath: "",
        projectName: "",
        projectId: null,
      },
      importer: {
        zipPath: "",
        workspaceRoot: "",
        extractedPath: "",
        openWorkspacePath: "/tmp/ws",
        historyValidation: {},
        deleteConfirmOpen: false,
        deleteWithFiles: false,
        deleteTargets: [],
        inFlight: false,
        status: "",
        stages: [],
        summary: "",
      },
      initializer: {
        references: [],
        datasets: [],
        existingProjects: [],
        selectedReferenceId: "",
        selectedPrimaryDatasetId: "",
        selectedSupportDatasetIds: [],
        projectNameInput: "",
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
        summary: "",
      },
      assembly: {
        loading: false,
        bootstrapping: false,
        summary: "",
        activeTab: "assembly",
        chromosomes: [],
        chrPickerOpen: false,
        selectedChrName: "",
        chrCtgs: [],
        refTrackMembers: [],
        deletedCtgs: [],
        selectedDeletedCtgRecordIds: [],
        selectedCtgId: null,
        ctgDetail: null,
        editCandidates: {
          moveTargetCtgs: [],
          addSeqCandidates: [],
        },
        trackView: {},
        subviewTrackView: {},
        selectedMemberSeqId: null,
        actionStatus: "",
        actionError: "",
        junctionLoading: false,
        junctionStatus: "",
        junctionError: "",
        junctionReport: null,
        supportDatasetId: null,
        supportChrCtgs: [],
        supportMirroredCtgs: [],
        finalPathByChr: {},
        finalPathViewMode: "graph",
        finalPathTrackView: {},
        trackSelectedCtgIds: [],
        hiddenPrimaryCtgIds: [],
        trackDragOffsets: [],
        subviewTrackDragOffsets: [],
        trackScrollState: {},
        subviewTrackScrollState: {},
        finalPathTrackScrollState: {},
        subview: {
          mode: "2-contig",
          selectedAContigId: null,
          selectedARole: "",
          selectedBContigId: null,
          selectedBRole: "",
          message: "",
          error: "",
          summary: null,
        },
        error: "",
      },
    });

    bindImporterPage(host, store);
    openWorkspaceButton.click();
    host.innerHTML = "";
    await new Promise((resolve) => setTimeout(resolve, 260));

    assert.equal(store.getState().activeRoute, "workspace");
    assert.equal(host.innerHTML, "");
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
  }
});

test("import progress modal is the only import summary and shows per-row status icons", () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      localStorage: {
        getItem() {
          return null;
        },
      },
    };
    const html = renderImporterPage({
      locale: "zh",
      importer: {
        zipPath: "",
        workspaceRoot: "",
        extractedPath: "",
        openWorkspacePath: "",
        historyValidation: {},
        deleteConfirmOpen: false,
        deleteWithFiles: false,
        deleteTargets: [],
        inFlight: true,
        importRunId: "import-test",
        importCancelling: false,
        status: "导入中",
        stages: [
          "validate_input：zip_path=a.zip",
          {
            label: "extract_entry：gpm_server/runs/chr_Chr06/result.paf",
            progressIndex: 131,
            progressTotal: 620,
          },
          {
            label: "index_pairwise_paf：chr_Chr06/flye_vs_self/result.paf",
            progressIndex: 550,
            progressTotal: 620,
          },
        ],
        summary: "正在导入",
      },
    });

    assert.match(html, /class="modal-overlay import-progress-overlay"/);
    assert.doesNotMatch(html, /import-progress-actions/);
    assert.match(html, /class="pipeline-done"/);
    assert.match(html, /class="pipeline-spinner"/);
    assert.match(html, /validate_input：zip_path=a\.zip \(1\/621\)/);
    assert.match(html, /extract_entry：gpm_server\/runs\/chr_Chr06\/result\.paf \(132\/621\)/);
    assert.match(html, /index_pairwise_paf：chr_Chr06\/flye_vs_self\/result\.paf \(551\/621\)/);
    assert.match(html, /class="import-progress-meter"/);
    assert.match(html, /551\/621/);
    assert.doesNotMatch(html, /导入摘要/);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("import progress css keeps labels in the wide column and icons pinned right", () => {
  const css = readFileSync(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.pipeline-step-row\.import-progress-step\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+20px;/,
  );
  assert.match(
    css,
    /\.import-progress-step\s+\.pipeline-step-label\s*\{[^}]*grid-column:\s*1\s*\/\s*2;/,
  );
  assert.match(
    css,
    /\.import-progress-step\s+\.pipeline-step-icon\s*\{[^}]*grid-column:\s*2\s*\/\s*3;/,
  );
  assert.match(
    css,
    /\.importer-option-card\s*\{[^}]*display:\s*flex;[^}]*flex-direction:\s*column;/,
  );
  assert.match(
    css,
    /\.importer-start-button\s*\{[^}]*min-height:\s*32px;[^}]*margin-top:\s*auto;/,
  );
});

test("import progress list auto-scrolls to the newest entry by default", () => {
  const progressList = createScrollList({
    scrollHeight: 1200,
    clientHeight: 320,
    scrollTop: 0,
  });
  const host = createHost({
    "[data-import-progress-list='1']": progressList,
  });
  const store = createStore(createImporterScrollState());

  bindImporterPage(host, store);

  assert.equal(progressList.scrollTop, 880);
});

test("import progress list preserves manual scroll until the user returns near bottom", () => {
  const progressList = createScrollList({
    scrollHeight: 1200,
    clientHeight: 320,
    scrollTop: 0,
  });
  const host = createHost({
    "[data-import-progress-list='1']": progressList,
  });
  const store = createStore(createImporterScrollState());

  bindImporterPage(host, store);
  progressList.scrollTop = 240;
  progressList.scroll();

  assert.equal(store.getState().importer.importProgressAutoScroll, false);
  assert.equal(store.getState().importer.importProgressScrollTop, 240);

  const rerenderedList = createScrollList({
    scrollHeight: 1400,
    clientHeight: 320,
    scrollTop: 0,
  });
  bindImporterPage(createHost({
    "[data-import-progress-list='1']": rerenderedList,
  }), store);

  assert.equal(rerenderedList.scrollTop, 240);

  rerenderedList.scrollTop = 1076;
  rerenderedList.scroll();
  assert.equal(store.getState().importer.importProgressAutoScroll, true);

  const latestList = createScrollList({
    scrollHeight: 1600,
    clientHeight: 320,
    scrollTop: 0,
  });
  bindImporterPage(createHost({
    "[data-import-progress-list='1']": latestList,
  }), store);

  assert.equal(latestList.scrollTop, 1280);
});
