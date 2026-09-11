import test from "node:test";
import assert from "node:assert/strict";
import { bindProjectCatalog, projectCatalogKey, renderProjectCatalog } from "../project-catalog-view.js";
import { listProjectCatalog, updateProjectCatalog } from "../../../services/project-catalog.js";
import { createWorkspaceOperations } from "../../../dev-bridge/operations/workspace.js";

function fixture() {
  const row = { objectType: "dataset", objectId: 1, originalName: "original", displayName: "current <name>", note: "line 1\n<script>line 2</script>", role: "primary",
    statistics: { sequenceCount: 3, totalLengthBp: 100, n50: 60, n90: 30, l50: 1, longest: 60 },
    locations: [], availableFileCount: 0, fastaAvailable: false, selfAlignmentAvailable: true };
  const data = { projectId: 1, datasets: [row], references: [{ ...row, objectType: "reference", displayName: "reference", role: "reference", note: "" }] };
  const state = { locale: "en", session: { workspacePath: "D:/one", projectId: 1 }, initializer: {
    datasets: [{ datasetId: 1, name: "original", contigCount: 3, totalLengthBp: 100 }], references: [{ referenceGenomeId: 1, name: "ref" }],
    existingProjects: [{ projectId: 1, supportDatasetIds: [] }],
  } };
  state.initializer.projectCatalog = { key: projectCatalogKey(state), data };
  return { state, data, row };
}

function element(dataset = {}) {
  const handlers = {};
  return { dataset, disabled: false, addEventListener(type, fn) { handlers[type] = fn; },
    fire(type, event = {}) { return handlers[type]?.({ preventDefault() {}, ...event }); } };
}

function harness(state) {
  let current = state;
  const store = { getState: () => current, setState(patch) { current = { ...current, ...patch }; } };
  const edit = element({ catalogEdit: "dataset:1" });
  const form = element();
  form.elements = { displayName: { value: "new name" }, note: { value: "new note" } };
  const reset = element();
  const cancel = element();
  const retry = element();
  const host = {
    querySelector(selector) {
      if (selector === "#project-data-catalog") return {};
      if (selector === "[data-catalog-retry]") return retry;
      if (selector === "[data-catalog-reset]") return reset;
      if (selector === "[data-catalog-cancel]") return cancel;
      if (selector === "[data-catalog-form]" && current.initializer.projectCatalog?.editor) return form;
      return null;
    },
    querySelectorAll(selector) { return selector === "[data-catalog-edit]" ? [edit] : []; },
  };
  const bind = deps => bindProjectCatalog(host, store, () => {}, deps);
  return { store, host, edit, form, reset, cancel, retry, bind };
}

test("catalog uses one table with data type first and reference first, escaping names and notes", () => {
  const { state } = fixture();
  const html = renderProjectCatalog(state);
  assert.match(html, /Datasets/);
  assert.match(html, /Reference genome/);
  assert.equal((html.match(/<table /g) || []).length, 1);
  assert.doesNotMatch(html, /<h3>|data-catalog-refresh|data-catalog-retry|Refresh datasets|is-primary/);
  assert.match(html, /<colgroup><col span="7"><col class="project-dataset-actions-column"><\/colgroup>/);
  assert.match(html, /<thead><tr><th scope="col">Data type<\/th><th scope="col">Name/);
  assert.ok(html.indexOf('data-catalog-object="reference:1"') < html.indexOf('data-catalog-object="dataset:1"'));
  assert.match(html, /current &lt;name&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /60 bp/);
  assert.match(html, /30 bp/);
  state.locale = "zh";
  assert.match(renderProjectCatalog(state), /数据类型/);
  assert.doesNotMatch(renderProjectCatalog(state), /<h3>|刷新数据集|is-primary/);
});

test("failed loading offers retry without a permanent refresh button", async () => {
  const { state, data } = fixture();
  state.initializer.projectCatalog = null;
  const h = harness(state);
  h.bind({ listProjectCatalog: async () => { throw new Error("offline"); } });
  await new Promise(done => setImmediate(done));
  assert.match(renderProjectCatalog(h.store.getState()), /data-catalog-retry[^>]*>Retry<\/button>/);
  h.bind({ listProjectCatalog: async () => data });
  h.retry.fire("click");
  await new Promise(done => setImmediate(done));
  assert.equal(h.store.getState().initializer.projectCatalog.data, data);
  assert.doesNotMatch(renderProjectCatalog(h.store.getState()), /data-catalog-retry|data-catalog-refresh/);
});

test("light package details do not invent a usable location and reset preserves the note until saved", () => {
  const { state, row } = fixture();
  const h = harness(state);
  h.bind(); h.edit.fire("click"); h.bind();
  assert.match(renderProjectCatalog(h.store.getState()), /<dialog[^>]*aria-modal="true"/);
  assert.match(renderProjectCatalog(h.store.getState()), /<details class="project-catalog-more" >/);
  assert.match(renderProjectCatalog(h.store.getState()), /Sequence files not included or unavailable/);
  assert.doesNotMatch(renderProjectCatalog(h.store.getState()), /data-catalog-copy/);
  h.form.fire("input");
  h.reset.fire("click");
  assert.equal(h.store.getState().initializer.projectCatalog.editor.displayName, row.originalName);
  assert.equal(h.store.getState().initializer.projectCatalog.editor.note, "new note");
  h.cancel.fire("click");
  assert.equal(h.store.getState().initializer.projectCatalog.editor, null);
  assert.equal(h.store.getState().initializer.projectCatalog.data.datasets[0].displayName, row.displayName);
});

test("save persists current name and note, keeps canonical name and updates display labels", async () => {
  const { state, data } = fixture();
  const h = harness(state);
  let payload;
  const deps = { updateProjectCatalog: async request => {
    payload = request;
    return { ...data, datasets: [{ ...data.datasets[0], displayName: request.displayName, note: request.note }] };
  } };
  h.bind(deps); h.edit.fire("click"); h.bind(deps);
  h.form.fire("input"); await h.form.fire("submit");
  assert.deepEqual(payload, { workspaceRoot: "D:/one", projectId: 1, objectType: "dataset", objectId: 1, displayName: "new name", note: "new note" });
  assert.equal(h.store.getState().initializer.datasets[0].name, "original");
  assert.equal(h.store.getState().initializer.datasets[0].displayName, "new name");
  assert.equal(h.store.getState().initializer.projectCatalog.editor, null);
});

test("failed save retains the editable draft and displays the error", async () => {
  const { state } = fixture();
  const h = harness(state);
  const deps = { updateProjectCatalog: async () => { throw new Error("disk full"); } };
  h.bind(deps); h.edit.fire("click"); h.bind(deps);
  h.form.fire("input"); await h.form.fire("submit");
  const catalog = h.store.getState().initializer.projectCatalog;
  assert.equal(catalog.editor.note, "new note");
  assert.equal(catalog.saving, false);
  assert.match(renderProjectCatalog(h.store.getState()), /disk full/);
});

test("a late load cannot replace another project's catalog", async () => {
  const { state, data } = fixture();
  state.initializer.projectCatalog = null;
  const h = harness(state);
  let resolve;
  h.bind({ listProjectCatalog: () => new Promise(done => { resolve = done; }) });
  h.store.setState({ session: { workspacePath: "D:/two", projectId: 1 } });
  resolve(data);
  await new Promise(done => setImmediate(done));
  assert.equal(h.store.getState().initializer.projectCatalog.data, undefined);
  assert.doesNotMatch(renderProjectCatalog(h.store.getState()), /current &lt;name&gt;/);
});

test("a late save cannot replace another project's catalog and reset uses the immutable initial name", async () => {
  const { state, data } = fixture();
  const h = harness(state);
  let resolve;
  let payload;
  const deps = { updateProjectCatalog: request => { payload = request; return new Promise(done => { resolve = done; }); } };
  h.bind(deps); h.edit.fire("click"); h.bind(deps);
  h.reset.fire("click"); h.bind(deps);
  const pending = h.form.fire("submit");
  assert.equal(payload.resetName, true);
  assert.equal(payload.displayName, undefined);
  const other = { key: "other", data: { projectId: 2, datasets: [], references: [] } };
  h.store.setState({ session: { workspacePath: "D:/two", projectId: 2 }, initializer: { ...h.store.getState().initializer, projectCatalog: other } });
  resolve(data); await pending;
  assert.equal(h.store.getState().initializer.projectCatalog, other);
});

test("Tauri receives nested update payload and a backend failure is never reported as a mock save", async () => {
  const previous = globalThis.window;
  const calls = [];
  globalThis.window = { __TAURI__: { core: { invoke: async (...args) => { calls.push(args); throw new Error("read only"); } } } };
  try {
    await assert.rejects(listProjectCatalog({ workspaceRoot: "D:/one", projectId: 1 }), /read only/);
    await assert.rejects(updateProjectCatalog({ workspaceRoot: "D:/one", projectId: 1, objectType: "dataset", objectId: 1, note: "hi\nthere" }), /read only/);
    assert.deepEqual(calls[1], ["update_project_catalog", { workspaceRoot: "D:/one", request: { projectId: 1, objectType: "dataset", objectId: 1, note: "hi\nthere" } }]);
  } finally { globalThis.window = previous; }
});

test("dev bridge passes names and multiline notes as a single JSON argument", async () => {
  const calls = [];
  const ops = createWorkspaceOperations({ runBackend: async args => { calls.push(args); return { stdout: '{"projectId":1,"datasets":[],"references":[]}' }; } });
  await ops.listProjectCatalog({ workspaceRoot: "D:/one", projectId: 1 });
  const request = { projectId: 1, objectType: "dataset", objectId: 1, displayName: "A 'quoted' name", note: "line 1\nline 2" };
  await ops.updateProjectCatalog({ workspaceRoot: "D:/one", ...request });
  assert.deepEqual(calls[0], ["list-project-catalog", "D:/one", "1"]);
  assert.deepEqual(JSON.parse(calls[1][2]), request);
});
