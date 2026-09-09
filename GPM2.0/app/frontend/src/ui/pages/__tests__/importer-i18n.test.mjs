import test from "node:test";
import assert from "node:assert/strict";

import {
  __testCreateImporterStatusToastDismissCoordinator,
  bindImporterPage,
  renderImporterPage,
} from "../importer-page.js";
import { en, zh } from "../../i18n/messages/importer.js";
import { readStylesheetTree } from "../../../styles/__tests__/style-test-support.mjs";

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
    setAttribute(name, value) { this[name] = value; },
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
    pointerdown({ button = 0, isPrimary = true } = {}) {
      const handler = listeners.get("pointerdown");
      if (handler) {
        return handler({
          currentTarget: this,
          target: this,
          button,
          isPrimary,
        });
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
    change(checked) {
      this.checked = checked;
      const handler = listeners.get("change");
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

function createDeferred() {
  let resolve;
  let reject;
  const promise = new Promise((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
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
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
      inFlight: true,
      importRunId: "import-test",
      importCancelling: false,
      importCancelError: "",
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
  assert.equal(zh.runtime.incompleteAddPackageWorkspaceSummary, "请先加载已有项目。");
  assert.equal(zh.runtime.incompleteAddPackageZipSummary, "请先选择数据集追加包 zip。");
  assert.equal(zh.runtime.importAddPackageDoneStage, "数据集追加包导入完成并刷新候选项");
  assert.equal(zh.runtime.addPackageHint, "（added {datasetName}）");
  assert.equal(zh.runtime.importFailedSummary, "导入失败：{message}");
  assert.equal(zh.runtime.importCancellingStatus, "终止请求中");
  assert.equal(zh.runtime.importProgressIndeterminate, "正在处理导入任务...");
  assert.equal(zh.runtime.importCancelRequestFailedSummary, "终止请求失败：{message}");
  assert.equal(zh.runtime.importCancelFinishedStatus, "终止请求已提交");
  assert.equal(zh.runtime.importCancelFinishedSummary, "导入流程已结束。");
  assert.equal(zh.runtime.tauriImportAddPackageStage, "调用后端 import_add_dataset_package");
  assert.equal(zh.progressStages.validate_grt_source_fastas, "校验 reference/dataset FASTA 与 FAI");
  assert.equal(zh.progressStages.validate_grt_app_required_files, "检查 App 交付包必需文件");
  assert.equal(zh.progressStages.validate_grt_app_fai, "校验来源与 reference 的 FAI 长度");
  assert.equal(zh.runtime.importPhaseProgress, "阶段 {current}/{total}");
  assert.equal(zh.buttons.validateHistory, "校验项目");
  assert.equal(zh.buttons.deleteFailedRecords, "删除失败项目");
  assert.equal(zh.page.deleteFailedConfirmTitle, "删除失败项目");
  assert.equal(zh.page.deleteWithFiles, "是否同步删除对应文件（此操作不可逆，请谨慎操作）");
  assert.equal(zh.runtime.deleteDoneFailedHistorySummary, "已从项目库删除 {count} 个校验失败项目。");

  assert.equal(en.buttons.importAddPackage, "Import add package");
  assert.equal(en.runtime.importAddPackageSummary, "Importing the dataset add package.");
  assert.equal(en.runtime.incompleteAddPackageWorkspaceSummary, "Open an existing project first.");
  assert.equal(en.runtime.incompleteAddPackageZipSummary, "Select a dataset add-package ZIP first.");
  assert.equal(en.runtime.importAddPackageDoneStage, "Dataset add package imported and options refreshed");
  assert.equal(en.runtime.addPackageHint, "(added {datasetName})");
  assert.equal(en.runtime.importFailedSummary, "Import failed: {message}");
  assert.equal(en.runtime.importCancellingStatus, "Cancellation requested");
  assert.equal(en.runtime.importProgressIndeterminate, "Processing the import...");
  assert.equal(en.runtime.importCancelRequestFailedSummary, "Cancellation request failed: {message}");
  assert.equal(en.runtime.importCancelFinishedStatus, "Cancellation requested");
  assert.equal(en.runtime.importCancelFinishedSummary, "The import has ended.");
  assert.equal(en.runtime.tauriImportAddPackageStage, "Invoke backend import_add_dataset_package");
  assert.equal(en.progressStages.validate_grt_source_fastas, "Validate reference/dataset FASTA and FAI");
  assert.equal(en.progressStages.validate_grt_app_required_files, "Check required App delivery files");
  assert.equal(en.progressStages.validate_grt_app_fai, "Validate source and reference FAI lengths");
  assert.equal(en.runtime.importPhaseProgress, "Phase {current}/{total}");
  assert.equal(en.buttons.validateHistory, "Validate projects");
  assert.equal(en.buttons.deleteFailedRecords, "Delete failed projects");
  assert.equal(en.page.deleteFailedConfirmTitle, "Delete failed projects");
  assert.equal(en.page.deleteWithFiles, "Also delete files on disk (irreversible).");
  assert.equal(en.runtime.deleteDoneFailedHistorySummary, "Removed {count} projects that failed validation from the library.");
});

test("importer bulk delete removes only current failed history records", async () => {
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
    let persistedHistory = [
      { path: "D:/ws-valid", lastUsedAt: 3 },
      { path: "D:/ws-failed-b", lastUsedAt: 2 },
      { path: "D:/ws-failed-a", lastUsedAt: 1 },
    ];
    globalThis.window = {
      __TAURI__: null,
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return JSON.stringify(persistedHistory);
        },
        setItem(_key, value) {
          persistedHistory = JSON.parse(value);
        },
      },
    };
    globalThis.setTimeout = () => ({ cancelled: false });
    globalThis.clearTimeout = () => {};
    let deleteRequestCount = 0;
    globalThis.fetch = async () => {
      deleteRequestCount += 1;
      throw new Error("unexpected backend request");
    };

    const deleteFailedButton = createButton();
    const cancelDeleteButton = createButton();
    const confirmDeleteButton = createButton();
    const deleteWithFilesCheckbox = createButton();
    const host = createHost({
      "#delete-failed-history-button": deleteFailedButton,
      "#cancel-delete-selected-button": cancelDeleteButton,
      "#confirm-delete-selected-button": confirmDeleteButton,
      "#delete-with-files-checkbox": deleteWithFilesCheckbox,
    });
    const state = createImporterScrollState({
      zipPath: "D:/source-package.zip",
      openWorkspacePath: "D:/ws-failed-a",
      historyValidatedPaths: ["D:/ws-valid", "D:/ws-failed-a", "D:/ws-failed-b"],
      historyValidation: {
        "D:/ws-valid": { ok: true, message: "" },
        "D:/ws-failed-a": { ok: false, message: "missing project.sqlite" },
        "D:/ws-failed-b": { ok: false, message: "missing result.paf" },
        "D:/stale-failed": { ok: false, message: "stale result" },
      },
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
      inFlight: false,
      importRunId: null,
      status: "",
      summary: "",
    });
    state.session = {
      workspacePath: "D:/ws-failed-a",
      projectName: "active-project",
      projectId: 42,
    };
    const store = createStore(state);

    const initialHtml = renderImporterPage(store.getState());
    assert.match(initialHtml, /id="validate-history-button"[^>]*>校验项目<\/button>\s*<button id="delete-failed-history-button"[^>]*>删除失败项目<\/button>/);
    assert.doesNotMatch(initialHtml, /id="delete-failed-history-button"[^>]*hidden/);

    bindImporterPage(host, store);
    deleteFailedButton.click();

    assert.equal(store.getState().importer.deleteConfirmOpen, true);
    assert.equal(store.getState().importer.deleteSelectionMode, "failed-history");
    assert.deepEqual(store.getState().importer.deleteTargets, ["D:/ws-failed-b", "D:/ws-failed-a"]);

    const confirmHtml = renderImporterPage(store.getState());
    assert.match(confirmHtml, /删除失败项目/);
    assert.match(confirmHtml, /D:\/ws-failed-a/);
    assert.match(confirmHtml, /D:\/ws-failed-b/);
    assert.match(confirmHtml, /id="delete-with-files-checkbox" type="checkbox"/);
    assert.match(confirmHtml, /是否同步删除对应文件（此操作不可逆，请谨慎操作）/);
    assert.doesNotMatch(confirmHtml, /id="delete-with-files-checkbox" type="checkbox" checked/);

    cancelDeleteButton.click();
    assert.equal(store.getState().importer.deleteConfirmOpen, false);
    assert.equal(store.getState().importer.deleteSelectionMode, "");
    assert.equal(persistedHistory.length, 3);

    deleteFailedButton.click();
    store.setState({
      importer: {
        ...store.getState().importer,
        deleteTargets: [
          ...store.getState().importer.deleteTargets,
          "D:/ws-valid",
          "D:/stale-failed",
        ],
      },
    });
    await confirmDeleteButton.click();

    assert.deepEqual(persistedHistory, [
      { path: "D:/ws-valid", lastUsedAt: 3 },
    ]);
    assert.deepEqual(store.getState().importer.historyValidation, {
      "D:/ws-valid": { ok: true, message: "" },
      "D:/stale-failed": { ok: false, message: "stale result" },
    });
    assert.equal(store.getState().importer.zipPath, "D:/source-package.zip");
    assert.equal(store.getState().importer.openWorkspacePath, "D:/ws-failed-a");
    assert.deepEqual(store.getState().session, {
      workspacePath: "D:/ws-failed-a",
      projectName: "active-project",
      projectId: 42,
    });
    assert.equal(store.getState().importer.summary, "已从项目库删除 2 个校验失败项目。");
    assert.equal(store.getState().importer.deleteSelectionMode, "");
    assert.equal(deleteRequestCount, 0);
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.fetch = previousFetch;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("deleting the active Windows workspace closes its project despite path spelling differences", async () => {
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
    let persistedHistory = [
      { path: "D:/ws-valid", lastUsedAt: 2 },
      { path: "D:/ws-failed", lastUsedAt: 1 },
    ];
    const invokeCalls = [];
    globalThis.window = {
      __TAURI__: {
        core: {
          async invoke(command, payload) {
            invokeCalls.push({ command, payload });
            return {
              workspaceRoot: payload.workspaceRoot,
              deleted: true,
            };
          },
        },
      },
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return JSON.stringify(persistedHistory);
        },
        setItem(_key, value) {
          persistedHistory = JSON.parse(value);
        },
      },
    };
    globalThis.setTimeout = () => ({ cancelled: false });
    globalThis.clearTimeout = () => {};

    const deleteFailedButton = createButton();
    const deleteWithFilesCheckbox = createButton();
    const confirmDeleteButton = createButton();
    const host = createHost({
      "#delete-failed-history-button": deleteFailedButton,
      "#delete-with-files-checkbox": deleteWithFilesCheckbox,
      "#confirm-delete-selected-button": confirmDeleteButton,
    });
    const state = createImporterScrollState({
      zipPath: "D:/source-package.zip",
      openWorkspacePath: "D:/ws-failed",
      historyValidatedPaths: ["D:/ws-valid", "D:/ws-failed"],
      historyValidation: {
        "D:/ws-valid": { ok: true, message: "" },
        "D:/ws-failed": { ok: false, message: "missing project.sqlite" },
        "D:/stale-failed": { ok: false, message: "stale result" },
      },
      deleteConfirmOpen: false,
      deleteSelectionMode: "",
      deleteWithFiles: false,
      deleteTargets: [],
      inFlight: false,
      importRunId: null,
      status: "",
      summary: "",
    });
    state.session = {
      workspacePath: "d:\\WS-FAILED\\",
      projectName: "active-project",
      projectId: 42,
    };
    const store = createStore(state);

    bindImporterPage(host, store);
    deleteFailedButton.click();
    deleteWithFilesCheckbox.change(true);
    store.setState({
      importer: {
        ...store.getState().importer,
        deleteTargets: ["D:/ws-failed", "D:/ws-valid", "D:/stale-failed"],
      },
    });
    await confirmDeleteButton.click();

    assert.deepEqual(invokeCalls, [
      {
        command: "delete_workspace_directory",
        payload: { workspaceRoot: "D:/ws-failed" },
      },
    ]);
    assert.deepEqual(persistedHistory, [
      { path: "D:/ws-valid", lastUsedAt: 2 },
    ]);
    assert.deepEqual(store.getState().importer.historyValidation, {
      "D:/ws-valid": { ok: true, message: "" },
      "D:/stale-failed": { ok: false, message: "stale result" },
    });
    assert.equal(store.getState().importer.zipPath, "D:/source-package.zip");
    assert.equal(store.getState().importer.openWorkspacePath, "");
    assert.deepEqual(store.getState().session, {
      workspacePath: "",
      projectName: "",
      projectId: null,
    });
    assert.doesNotMatch(renderImporterPage(store.getState()), /class="project-current"/);
    assert.equal(store.getState().importer.summary, "已删除 1 条记录，其中目录删除 1 条。");
    assert.match(store.getState().importer.stages[0], /已删除目录：D:\/ws-failed/);
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("failed file deletion retains the current project and reports a persistent error", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  const record = { path: "/active", lastUsedAt: 1 };
  let history = [record];
  try {
    globalThis.document = { querySelector: () => null };
    globalThis.setTimeout = () => 0;
    globalThis.clearTimeout = () => {};
    globalThis.window = {
      __TAURI__: { core: { invoke: async () => { throw new Error("Permission denied"); } } },
      dispatchEvent() {},
      localStorage: {
        getItem: () => JSON.stringify(history),
        setItem: (_key, value) => { history = JSON.parse(value); },
      },
    };
    const initial = createImporterScrollState({
      inFlight: false, importRunId: null, deleteWithFiles: true,
      deleteConfirmOpen: true, deleteTargets: ["/active"],
    });
    initial.session = { workspacePath: "/active", projectId: 1, projectName: "Active" };
    const store = createStore(initial);
    const confirm = createButton();
    bindImporterPage(createHost({ "#confirm-delete-selected-button": confirm }), store);
    await confirm.click();
    assert.deepEqual(history, [record]);
    assert.deepEqual(store.getState().session, initial.session);
    assert.match(store.getState().importer.projectError, /Permission denied/);
    assert.match(store.getState().importer.summary, /已删除 0 条记录/);
    assert.equal(store.getState().importer.inFlight, false);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("deleting the active project record closes its card when disk deletion is unchecked", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const previousSetTimeout = globalThis.setTimeout;
  const previousClearTimeout = globalThis.clearTimeout;
  let history = [{ path: "D:/active", lastUsedAt: 1 }];
  try {
    globalThis.document = { querySelector: () => null };
    globalThis.setTimeout = () => 0;
    globalThis.clearTimeout = () => {};
    globalThis.window = {
      dispatchEvent() {},
      localStorage: {
        getItem: () => JSON.stringify(history),
        setItem: (_key, value) => { history = JSON.parse(value); },
      },
    };
    const initial = createImporterScrollState({
      inFlight: false,
      importRunId: null,
      deleteConfirmOpen: true,
      deleteSelectionMode: "project",
      deleteWithFiles: false,
      deleteTargets: ["D:/active"],
      openWorkspacePath: "D:/active",
    });
    initial.session = { workspacePath: "D:/active", projectId: 1, projectName: "Active" };
    const store = createStore(initial);
    const confirm = createButton();
    bindImporterPage(createHost({ "#confirm-delete-selected-button": confirm }), store);

    await confirm.click();

    assert.deepEqual(history, []);
    assert.deepEqual(store.getState().session, {
      workspacePath: "",
      projectId: null,
      projectName: "",
    });
    assert.equal(store.getState().importer.openWorkspacePath, "");
    assert.doesNotMatch(renderImporterPage(store.getState()), /class="project-current"/);
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("project validation updates in place and preserves the rename draft across retries and toast dismissal", async () => {
  const previousWindow = globalThis.window;
  const firstResult = createDeferred();
  const calls = [];
  const timers = [];
  let repaired = false;
  const paths = ["D:/good", "D:/missing", "D:/unavailable"];
  try {
    globalThis.window = {
      localStorage: { getItem: () => JSON.stringify(paths.map(path => ({ path }))) },
      setTimeout(callback) { timers.push(callback); return timers.length; },
      clearTimeout() {},
      __TAURI__: { core: { invoke: async (command, { workspaceRoot }) => {
        assert.equal(command, "validate_workspace_integrity");
        calls.push(workspaceRoot);
        if (repaired) return { ok: true };
        if (workspaceRoot === "D:/good") return firstResult.promise;
        if (workspaceRoot === "D:/missing") return { ok: false, missing: ["project.sqlite"] };
        throw new Error("Path <unavailable>");
      } } },
    };
    const validate = Object.assign(createButton(), {
      setAttribute(name, value) { this[name] = value; },
    });
    const remove = Object.assign(createButton(), { hidden: true });
    const input = Object.assign(createButton(), { value: "Unsaved name" });
    const page = { toastHtml: "", insertAdjacentHTML(_position, html) { this.toastHtml = html; } };
    const errors = paths.map(path => ({ dataset: { projectValidationPath: path }, hidden: true, textContent: "" }));
    const toast = { removed: false, remove() { this.removed = true; } };
    const host = createHost({
      "#validate-history-button": validate,
      "#delete-failed-history-button": remove,
      "#selected-project-name-input": input,
      ".projects-page": page,
      "[data-project-validation-path]": errors,
      '[data-importer-status-toast="1"]': toast,
    });
    host.innerHTML = "Existing project detail and focused rename input";
    const state = createImporterScrollState({ inFlight: false, importRunId: null, status: "Previous operation", summary: "Finished" });
    state.session = { workspacePath: paths[0], projectId: 1, projectName: "Original" };
    state.initializer = { ...state.initializer, renameProjectKey: `${paths[0]}:1`, editProjectNameInput: input.value };
    const store = createStore(state);
    bindImporterPage(host, store);
    const pending = validate.click();
    await validate.click();
    remove.click();
    assert.deepEqual(calls, [paths[0]]);
    assert.equal(store.getState().importer.historyValidating, true);
    assert.equal(store.getState().importer.inFlight, false);
    assert.equal(store.getState().importer.deleteConfirmOpen, false);
    assert.equal(validate.disabled, true);
    assert.equal(validate.textContent, "校验中…");
    assert.equal(remove.hidden, true);
    timers[0]();
    assert.equal(toast.removed, true);
    assert.equal(host.innerHTML, "Existing project detail and focused rename input");

    firstResult.resolve({ ok: true });
    await pending;
    assert.equal(store.getState().importer.historyValidating, false);
    assert.equal(validate.disabled, false);
    assert.equal(validate.textContent, "校验项目");
    assert.equal(remove.hidden, false);
    assert.equal(remove.disabled, false);
    assert.match(page.toastHtml, /importer-status-toast.*[\s\S]*校验完成：通过 1 个，失败 2 个。/);
    assert.deepEqual(store.getState().importer.historyValidatedPaths, paths);
    assert.doesNotMatch(renderImporterPage(store.getState()), /project-validation-summary/);
    assert.ok(errors.every(node => node.hidden && node.textContent === ""));
    assert.doesNotMatch(renderImporterPage(store.getState()), /data-project-validation-path/);

    repaired = true;
    const retry = validate.click();
    assert.equal(remove.hidden, true);
    await retry;
    assert.match(page.toastHtml, /校验完成：通过 3 个，失败 0 个。/);
    assert.equal(remove.hidden, true);
    assert.equal(remove.disabled, true);
    assert.ok(errors.every(node => node.hidden && node.textContent === ""));
    assert.equal(host.innerHTML, "Existing project detail and focused rename input");
    assert.equal(host.querySelector("#selected-project-name-input"), input);
    assert.equal(input.value, "Unsaved name");
    assert.equal(store.getState().initializer.editProjectNameInput, "Unsaved name");
    assert.equal(store.getState().session, state.session);
    assert.equal(timers.length, 3);
    timers.at(-1)();
    assert.equal(store.getState().importer.status, "");
    assert.equal(host.innerHTML, "Existing project detail and focused rename input");
  } finally {
    globalThis.window = previousWindow;
  }
});

test("selecting a project preserves the library and replaces only detail after a successful open", async () => {
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  const opened = createDeferred();
  const started = createDeferred();
  let history = [{ path: "D:/old", projectName: "Old", lastUsedAt: 2 }, { path: "D:/new", projectName: "New", lastUsedAt: 1 }];
  const calls = [];
  const events = [];
  const makeRow = record => {
    const button = createButton();
    button.dataset.recentPath = record.path;
    const status = { textContent: "", hidden: true };
    const error = { dataset: { projectValidationPath: record.path }, textContent: "", hidden: true };
    const nodes = {
      "[data-recent-path]": button,
      ".project-recent-name strong": { textContent: record.projectName },
      ".project-open-status": status,
      ".project-recent-time time": { textContent: "" },
    };
    return Object.assign(createButton(), {
      dataset: { workspaceHistoryRowPath: record.path }, button, error,
      classList: { toggle(_name, active) { this.active = active; } },
      querySelector: selector => nodes[selector] || null,
    });
  };
  const rows = history.map(makeRow);
  const list = {
    children: [...rows],
    insertBefore(row, target) {
      this.children.splice(this.children.indexOf(row), 1);
      this.children.splice(target ? this.children.indexOf(target) : this.children.length, 0, row);
    },
  };
  const enter = createButton();
  const nextDetail = createHost({ "#initializer-enter-assembly-button": enter });
  let detailWrites = 0;
  let detailHtml = "Old detail";
  const detail = { set outerHTML(html) { detailWrites += 1; detailHtml = html; } };
  const page = { toastHtml: "", insertAdjacentHTML(_where, html) { this.toastHtml = html; } };
  const remove = createButton();
  const validate = createButton();
  const host = createHost({
    ".projects-page": page,
    ".project-current, .project-no-selection": detail,
    ".project-current": nextDetail,
    ".project-recent-list": list,
    "[data-workspace-history-row-path]": rows,
    "[data-recent-index]": rows.map(row => row.button),
    "[data-project-validation-path]": rows.map(row => row.error),
    "#validate-history-button": validate,
    "#delete-failed-history-button": remove,
  });
  host.innerHTML = "Mounted project page";
  const initial = createImporterScrollState({ inFlight: false, importRunId: null, status: "", summary: "",
    historyValidatedPaths: ["D:/old"], historyValidation: { "D:/old": { ok: false, message: "Previous check" } },
  });
  initial.session = { workspacePath: "D:/old", projectId: 1, projectName: "Old" };
  initial.initializer.editProjectNameInput = "Unsaved draft";
  const store = createStore(initial);
  const setState = store.setState;
  store.setState = patch => {
    if (patch.session && patch.session.workspacePath !== store.getState().session.workspacePath) {
      history = history.map(record => record.path === patch.session.workspacePath
        ? { ...record, projectName: patch.session.projectName, lastUsedAt: 3 }
        : record);
    }
    setState(patch);
  };
  try {
    globalThis.document = { querySelector: () => null };
    globalThis.window = {
      localStorage: { getItem: () => JSON.stringify(history) },
      dispatchEvent: event => events.push(event.type),
      setTimeout: () => 1, clearTimeout() {},
      __TAURI__: { core: { invoke: async (command, { workspaceRoot }) => {
        assert.equal(command, "open_workspace");
        calls.push(workspaceRoot);
        if (workspaceRoot === "D:/old") throw new Error("Cannot open old project");
        started.resolve();
        return opened.promise;
      } } },
    };
    bindImporterPage(host, store);
    await rows[0].button.click();
    assert.deepEqual(calls, []);
    assert.equal(store.getState().initializer.editProjectNameInput, "Unsaved draft");

    const pending = rows[1].button.click();
    await started.promise;
    await rows[0].button.click();
    assert.deepEqual(calls, ["D:/new"]);
    assert.equal(rows[1].button["aria-busy"], "true");
    assert.equal(validate.disabled, false);
    assert.equal(detailWrites, 0);
    assert.equal(host.innerHTML, "Mounted project page");
    opened.resolve({ existingProjects: [{ projectId: 2, projectName: "New", autoPipelineDone: true }], references: [], datasets: [] });
    await pending;
    assert.equal(store.getState().session.workspacePath, "D:/new");
    assert.equal(detailWrites, 1);
    assert.match(detailHtml, /<h2>New<\/h2>/);
    assert.equal(list.children[0], rows[0]);
    assert.equal(list.children[1], rows[1]);
    assert.equal(rows[0].button["aria-current"], "false");
    assert.equal(rows[1].button["aria-current"], "true");
    assert.equal(rows[1].button.disabled, false);
    assert.equal(remove.hidden, false);
    assert.deepEqual(events, []);

    await rows[0].button.click();
    assert.equal(store.getState().session.workspacePath, "D:/new");
    assert.equal(detailWrites, 1);
    assert.equal(host.innerHTML, "Mounted project page");
    assert.match(page.toastHtml, /Cannot open old project/);
    assert.equal(remove.hidden, true);
    await enter.click();
    assert.equal(store.getState().activeRoute, "assembly");
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
  }
});

test("importer hides bulk delete when validation has no failed projects", () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      localStorage: {
        getItem() {
          return JSON.stringify([{ path: "D:/ws-valid", lastUsedAt: 1 }]);
        },
      },
    };
    const state = createImporterScrollState({
      historyValidation: {
        "D:/ws-valid": { ok: true, message: "" },
      },
      inFlight: false,
      importRunId: null,
      status: "",
      summary: "",
    });

    const html = renderImporterPage(state);
    assert.match(html, /id="delete-failed-history-button"[^>]*disabled[^>]*hidden/);
    assert.doesNotMatch(html, /项目库操作|一键删除失败记录/);
  } finally {
    globalThis.window = previousWindow;
  }
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
    assert.match(html, /打开项目/);
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

test("importer workspace history row imports add packages without expanding the compact project card", async () => {
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
    assert.deepEqual(store.getState().importer.addPackageHintsByWorkspacePath["D:/ws"], ["new_ds"]);
    assert.doesNotMatch(renderImporterPage(store.getState()), /class="add-package-hint"/);

    await importAddPackageButton.click();

    assert.equal(store.getState().initializer.datasets.some((dataset) => dataset.name === "new_ds2"), true);
    assert.deepEqual(store.getState().importer.addPackageHintsByWorkspacePath["D:/ws"], ["new_ds", "new_ds2"]);
    assert.doesNotMatch(renderImporterPage(store.getState()), /class="add-package-hint"/);

    store.setState({ locale: "zh" });
    assert.doesNotMatch(renderImporterPage(store.getState()), /class="add-package-hint"/);
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
  const css = readStylesheetTree(
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
  const css = readStylesheetTree(
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
    assert.equal(nextImporter.summary, "Fill in both the ZIP path and project directory.");
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

test("opening an existing workspace stays on the unified projects page", async () => {
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
    await openWorkspaceButton.click();

    assert.equal(store.getState().activeRoute, "importer");
    assert.match(host.innerHTML, /projects-page/);
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
  }
});

test("import progress modal truncates the active label and uses icon-only row statuses", () => {
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
            label: "index_pairwise_paf：my_hifiasm_vs_self (runs/chr_Chr06/my_hifiasm_vs_self/result.paf) (550/620)",
            progressIndex: 550,
            progressTotal: 620,
          },
        ],
        summary: zh.runtime.importZipSummary,
      },
    });

    assert.match(html, /class="modal-overlay import-progress-overlay importer-import-progress-overlay"/);
    assert.match(html, /role="dialog"/);
    assert.match(html, /aria-label="导入进度"/);
    assert.match(html, /aria-describedby="import-progress-dialog-summary"/);
    assert.match(html, /data-import-cancel="1"/);
    assert.match(html, /aria-label="终止导入"/);
    assert.doesNotMatch(html, /aria-labelledby="import-progress-dialog-title"/);
    assert.doesNotMatch(html, /importer-import-progress-header/);
    assert.doesNotMatch(html, /importer-import-progress-status-mark/);
    assert.doesNotMatch(html, /importer-import-progress-overview-head/);
    assert.doesNotMatch(html, />导入进度</);
    assert.doesNotMatch(html, /导入进行中/);
    assert.doesNotMatch(html, /当前阶段/);
    assert.doesNotMatch(html, /import-progress-actions/);
    assert.match(
      html,
      /<strong class="importer-import-progress-current-stage">index_pairwise_paf：my_hifiasm_vs_self<\/strong>/,
    );
    assert.doesNotMatch(html, /importer-import-progress-current-stage" title=/);
    assert.match(
      html,
      /<p id="import-progress-dialog-summary" class="importer-import-progress-summary" aria-live="polite">正在导入 zip 交付包。<\/p>/,
    );
    assert.match(
      html,
      /class="importer-import-progress-step-icon is-done" role="img" aria-label="已完成"/,
    );
    assert.match(
      html,
      /class="importer-import-progress-step-icon is-running" role="img" aria-label="进行中"/,
    );
    assert.doesNotMatch(html, />已完成</);
    assert.doesNotMatch(html, />进行中</);
    assert.doesNotMatch(html, /importer-import-progress-step-status/);
    assert.doesNotMatch(html, /class="pipeline-done"/);
    assert.match(html, /class="pipeline-spinner"/);
    assert.doesNotMatch(html, /importer-import-progress-log-head/);
    assert.doesNotMatch(html, /importer-import-progress-log-count/);
    assert.match(html, /<details class="importer-import-progress-log"[^>]*><summary>详细过程<\/summary>/);
    assert.doesNotMatch(html, /已记录 \d+ 项/);
    assert.match(html, /validate_input：zip_path=a\.zip \(1\/621\)/);
    assert.match(html, /extract_entry：gpm_server\/runs\/chr_Chr06\/result\.paf \(132\/621\)/);
    assert.match(html, /index_pairwise_paf：my_hifiasm_vs_self \(runs\/chr_Chr06\/my_hifiasm_vs_self\/result\.paf\) \(551\/621\)/);
    assert.match(html, /class="import-progress-meter"/);
    assert.match(html, /data-progress-mode="step"/);
    assert.match(html, /aria-valuenow="551"/);
    assert.match(html, /551\/621/);
    assert.doesNotMatch(html, /导入摘要/);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("import progress renders only the most recent 60 log entries", () => {
  const previousWindow = globalThis.window;
  try {
    globalThis.window = {
      localStorage: {
        getItem() {
          return null;
        },
      },
    };
    const stages = Array.from(
      { length: 65 },
      (_, index) => `event-${String(index + 1).padStart(2, "0")}`,
    );
    const html = renderImporterPage({
      locale: "en",
      importer: {
        ...createImporterScrollState().importer,
        importRunId: "import-log-window-test",
        stages,
        summary: "Processing",
      },
    });

    const renderedRows = html.match(
      /class="pipeline-step-row import-progress-step importer-import-progress-step/g,
    ) || [];
    assert.equal(renderedRows.length, 60);
    for (const omittedStage of stages.slice(0, 5)) {
      assert.equal(html.includes(omittedStage), false);
    }
    assert.match(html, /event-06/);
    assert.match(html, /event-65/);
    assert.doesNotMatch(html, /Events recorded:/);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("import progress uses phase metadata and labels GRT validation instead of archive-entry completion", () => {
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
        importRunId: "import-phase-test",
        importCancelling: false,
        status: "导入中",
        stages: [
          {
            stageCode: "normalize_workspace_layout",
            detail: "promoted D:\\Desktop\\example1\\gpm_server into D:\\Desktop\\example1",
            label: "normalize_workspace_layout：promoted ...",
            phaseIndex: 3,
            phaseTotal: 7,
          },
          {
            stageCode: "validate_grt_contract_start",
            detail: "starting full GRT package validation",
            label: "validate_grt_contract_start：starting full GRT package validation",
            phaseIndex: 4,
            phaseTotal: 7,
            progressIndex: 673,
            progressTotal: 674,
          },
          {
            stageCode: "validate_grt_source_fastas",
            detail: "validating reference and dataset FASTA/FAI",
            label: "validate_grt_source_fastas：validating reference and dataset FASTA/FAI",
            phaseIndex: 4,
            phaseTotal: 7,
            progressIndex: 674,
            progressTotal: 674,
          },
        ],
        summary: "正在导入",
      },
    });

    assert.match(html, /整理项目目录/);
    assert.match(html, /校验 reference\/dataset FASTA 与 FAI/);
    assert.match(html, /阶段 4\/7/);
    assert.doesNotMatch(html, /673\/674/);
    assert.doesNotMatch(html, /validate_grt_source_fastas：/);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("import progress css keeps the active label on one line and uses status icons", () => {
  const css = readStylesheetTree(
    new URL("../../../styles/components.css", import.meta.url),
    "utf8",
  );

  assert.match(
    css,
    /\.importer-import-progress-dialog \.pipeline-step-row\.import-progress-step\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto;[^}]*border-bottom:\s*1px\s+solid\s+#edf1f5;/,
  );
  assert.match(
    css,
    /\.importer-import-progress-dialog \.import-progress-step\s+\.pipeline-step-label\s*\{[^}]*grid-column:\s*1\s*\/\s*2;/,
  );
  assert.match(
    css,
    /\.importer-import-progress-step-icon\s*\{[^}]*grid-column:\s*2\s*\/\s*3;[^}]*display:\s*inline-grid;/,
  );
  assert.doesNotMatch(css, /\.importer-import-progress-step-status\s*\{/);
  assert.doesNotMatch(
    css,
    /\.importer-import-progress-log-(?:head|count)\s*\{/,
  );
  assert.match(css, /\.importer-import-progress-overlay\s*\{/);
  assert.match(
    css,
    /\.importer-import-progress-dialog\s*\{[^}]*width:\s*min\(900px,[^}]*max-height:\s*min\(760px,[^}]*border-radius:\s*8px;/,
  );
  assert.match(
    css,
    /\.projects-page \.importer-import-progress-dialog \.import-progress-close\s*\{[^}]*position:\s*absolute;[^}]*top:\s*12px;[^}]*right:\s*12px;/,
  );
  assert.match(
    css,
    /\.importer-import-progress-overview\s*\{[^}]*padding:\s*24px\s+32px\s+18px;[^}]*background:\s*#ffffff;/,
  );
  assert.match(
    css,
    /\.importer-import-progress-current-stage\s*\{[^}]*overflow:\s*hidden;[^}]*text-overflow:\s*ellipsis;[^}]*white-space:\s*nowrap;/,
  );
  assert.match(
    css,
    /\.importer-import-progress-summary\s*\{[^}]*position:\s*absolute;[^}]*width:\s*1px;[^}]*clip-path:\s*inset\(50%\);/,
  );
  assert.match(
    css,
    /\.importer-import-progress-dialog \.import-progress-list\s*\{[^}]*min-height:\s*180px;[^}]*max-height:\s*min\(46vh,\s*420px\);[^}]*border:\s*0;[^}]*background:\s*transparent;/,
  );
  assert.match(
    css,
    /@media \(max-width:\s*640px\)\s*\{[\s\S]*?\.importer-import-progress-dialog\s*\{[^}]*border-radius:\s*8px;/,
  );
  assert.doesNotMatch(
    css,
    /\.importer-import-progress-(?:header|title-group|status-mark|title-block|eyebrow|section-label|overview-head)/,
  );
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
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

test("import progress uses an indeterminate meter when no reliable total exists", () => {
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
      locale: "en",
      importer: {
        ...createImporterScrollState().importer,
        importRunId: "import-indeterminate-test",
        stages: ["Preparing import"],
        summary: "Processing",
      },
    });

    assert.match(html, /aria-label="Import progress"/);
    assert.doesNotMatch(html, /Current stage/);
    assert.match(html, /data-progress-mode="indeterminate"/);
    assert.match(html, /aria-valuetext="Processing the import\.\.\."/);
    assert.doesNotMatch(html, /aria-valuenow=/);
    assert.doesNotMatch(html, /Events recorded:/);
  } finally {
    globalThis.window = previousWindow;
  }
});

test("import progress cancellation starts on pointerdown and keeps the dialog until the import settles", async () => {
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
    const importDeferred = createDeferred();
    const cancelDeferred = createDeferred();
    const calls = [];
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke(command, args) {
            calls.push({ command, args });
            if (command === "import_zip") {
              return importDeferred.promise;
            }
            if (command === "request_import_cancel") {
              return cancelDeferred.promise;
            }
            if (command === "initialize_project") return Promise.resolve({ projectId: 1, projectName: "empty", existingProjects: [{ projectId: 1, projectName: "empty", phasedAssemblyEnabled: true }] });
            throw new Error(`unexpected command: ${command}`);
          },
        },
      },
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return null;
        },
        setItem() {},
        removeItem() {},
      },
    };
    globalThis.setTimeout = () => ({ cancelled: false });
    globalThis.clearTimeout = () => {};

    const importZipStartButton = createButton();
    const cancelButton = createButton();
    const host = createHost({
      "#import-zip-start-button": importZipStartButton,
      "[data-import-cancel]": cancelButton,
      "[data-import-progress-list='1']": createScrollList(),
    });
    const store = createStore(createImporterScrollState({
      zipPath: "bundle.zip",
      workspaceRoot: "D:/empty",
      inFlight: false,
      importRunId: null,
      status: "",
      stages: [],
      summary: "",
    }));

    bindImporterPage(host, store);
    const importRun = importZipStartButton.click();
    const runId = store.getState().importer.importRunId;
    assert.equal(store.getState().importer.inFlight, true);

    const cancelRun = cancelButton.pointerdown();
    assert.equal(store.getState().importer.inFlight, true);
    assert.equal(store.getState().importer.importRunId, runId);
    assert.equal(store.getState().importer.importCancelling, true);
    assert.match(host.innerHTML, /disabled aria-disabled="true"/);
    assert.match(host.innerHTML, /importer-import-progress-cancel-spinner/);

    const duplicateCancelRun = cancelButton.click();
    await duplicateCancelRun;
    assert.equal(
      calls.filter(({ command }) => command === "request_import_cancel").length,
      1,
    );

    cancelDeferred.resolve({ runId, cancelRequested: true });
    await cancelRun;
    assert.equal(store.getState().importer.importCancelling, true);
    assert.match(host.innerHTML, /已请求终止导入/);

    importDeferred.reject(new Error("import cancelled by backend"));
    await importRun;
    assert.equal(store.getState().importer.inFlight, false);
    assert.equal(store.getState().importer.importRunId, null);
    assert.equal(store.getState().importer.importCancelling, false);
    assert.equal(store.getState().importer.status, zh.runtime.importCancelFinishedStatus);
    assert.equal(store.getState().importer.summary, zh.runtime.importCancelFinishedSummary);
    assert.doesNotMatch(store.getState().importer.summary, /import cancelled by backend/);
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("normal import success wins over a pending cancellation response", async () => {
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
    const importDeferred = createDeferred();
    const cancelDeferred = createDeferred();
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke(command) {
            if (command === "import_zip") {
              return importDeferred.promise;
            }
            if (command === "request_import_cancel") {
              return cancelDeferred.promise;
            }
            if (command === "list_project_initializer_options" || command === "open_workspace") {
              return Promise.resolve({
                packageMetadata: {},
                grtRecipe: null,
                references: [{ referenceGenomeId: 1 }],
                datasets: [{ datasetId: 2 }],
                existingProjects: [],
              });
            }
            if (command === "initialize_project") return Promise.resolve({ projectId: 1, projectName: "empty", existingProjects: [{ projectId: 1, projectName: "empty", phasedAssemblyEnabled: true }] });
            throw new Error(`unexpected command: ${command}`);
          },
        },
      },
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return null;
        },
        setItem() {},
        removeItem() {},
      },
    };
    globalThis.setTimeout = () => ({ cancelled: false });
    globalThis.clearTimeout = () => {};

    const importZipStartButton = createButton();
    const cancelButton = createButton();
    const host = createHost({
      "#import-zip-start-button": importZipStartButton,
      "[data-import-cancel]": cancelButton,
      "[data-import-progress-list='1']": createScrollList(),
    });
    const store = createStore(createImporterScrollState({
      zipPath: "bundle.zip",
      workspaceRoot: "D:/empty",
      inFlight: false,
      importRunId: null,
      status: "",
      stages: [],
      summary: "",
    }));

    bindImporterPage(host, store);
    const importRun = importZipStartButton.click();
    const runId = store.getState().importer.importRunId;
    const cancelRun = cancelButton.click();
    importDeferred.resolve({
      workspaceRoot: "D:/empty",
      message: "Import finished normally",
    });
    await importRun;

    assert.equal(store.getState().activeRoute, "importer");
    assert.equal(store.getState().importer.importRunId, null);
    assert.equal(store.getState().importer.importCancelling, false);
    assert.equal(store.getState().importer.status, zh.runtime.importDoneStatus);
    assert.equal(store.getState().importer.summary, "Import finished normally");

    cancelDeferred.reject(new Error(`late cancellation for ${runId}`));
    await cancelRun;
    assert.equal(store.getState().importer.status, zh.runtime.importDoneStatus);
    assert.equal(store.getState().importer.summary, "Import finished normally");
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});

test("import cancellation request failures restore the running dialog", async () => {
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
    const importDeferred = createDeferred();
    const cancelDeferred = createDeferred();
    globalThis.window = {
      __TAURI__: {
        core: {
          invoke(command) {
            if (command === "import_zip") {
              return importDeferred.promise;
            }
            if (command === "request_import_cancel") {
              return cancelDeferred.promise;
            }
            throw new Error(`unexpected command: ${command}`);
          },
        },
      },
      dispatchEvent() {},
      localStorage: {
        getItem() {
          return null;
        },
        setItem() {},
        removeItem() {},
      },
    };
    globalThis.setTimeout = () => ({ cancelled: false });
    globalThis.clearTimeout = () => {};

    const importZipStartButton = createButton();
    const cancelButton = createButton();
    const host = createHost({
      "#import-zip-start-button": importZipStartButton,
      "[data-import-cancel]": cancelButton,
      "[data-import-progress-list='1']": createScrollList(),
    });
    const store = createStore(createImporterScrollState({
      zipPath: "bundle.zip",
      workspaceRoot: "D:/empty",
      inFlight: false,
      importRunId: null,
      status: "",
      stages: [],
      summary: "",
    }));

    bindImporterPage(host, store);
    const importRun = importZipStartButton.click();
    const runId = store.getState().importer.importRunId;
    const cancelRun = cancelButton.click();
    cancelDeferred.reject(new Error("cancel service unavailable"));
    await cancelRun;

    const currentImporter = store.getState().importer;
    assert.equal(currentImporter.inFlight, true);
    assert.equal(currentImporter.importRunId, runId);
    assert.equal(currentImporter.importCancelling, false);
    assert.equal(currentImporter.summary, zh.runtime.importZipSummary);
    assert.equal(
      currentImporter.importCancelError,
      "终止请求失败：cancel service unavailable",
    );
    assert.doesNotMatch(host.innerHTML, /disabled aria-disabled="true"/);

    importDeferred.reject(new Error("stop test"));
    await importRun;
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
    globalThis.setTimeout = previousSetTimeout;
    globalThis.clearTimeout = previousClearTimeout;
  }
});
