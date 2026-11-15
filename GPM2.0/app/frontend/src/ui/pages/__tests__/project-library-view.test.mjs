import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { renderLibraryTree, renderImportPartition, renderLibraryDialog, renderLibraryMenu, bindProjectLibrary } from "../project-library-view.js";
import { renderProjectsBody } from "../projects-view.js";
import { getMessages } from "../../i18n/index.js";
import { readProjectLibrary, saveProjectLibrary } from "../../../services/project-library.js";
import { readWorkspaceHistory, writeWorkspaceHistory } from "../../../services/workspace-history.js";

const library = { version: 1, collapsed: ["plants"], partitions: [
  { id: "plants", name: "植物", parentId: "" }, { id: "rice", name: "水稻", parentId: "plants" },
  { id: "wheat", name: "小麦", parentId: "plants" }, { id: "animals", name: "动物", parentId: "" },
] };
const state = (locale = "zh", importer = {}) => ({ locale, session: {}, initializer: {}, importer });
function withStorage(fn) {
  const previous = globalThis.window, data = new Map();
  globalThis.window = { localStorage: { getItem: key => data.get(key) ?? null, setItem: (key, value) => data.set(key, value) } };
  try { saveProjectLibrary(library); return fn(); } finally { globalThis.window = previous; }
}

test("empty library keeps the hierarchy, fixed default bucket and right-side import guidance", () => withStorage(() => {
  const s = state(), markup = renderProjectsBody(s, { records: [], messages: getMessages(s, "importer"), summaryHtml: "" });
  assert.match(markup, /class="project-browser"/);
  assert.match(markup, /data-library-group="plants"/);
  assert.match(markup, /data-library-group="rice"/);
  assert.match(markup, /尚未添加项目/);
  assert.match(markup, /data-library-create="root"/);
  assert.equal((markup.match(/data-library-group=""/g) || []).length, 1);
  assert.doesNotMatch(markup, /data-library-drag-folder=""/);
}));

test("nested tree preserves all records under collapsed parents, sorts names and distinguishes projects", () => {
  const records = [{ path: "/z", projectName: "zh97", partitionId: "rice" }, { path: "/m", projectName: "mh63", partitionId: "rice" }, { path: "/old", projectName: "Legacy" }];
  const s = state(); s.session = { workspacePath: "/m" };
  const markup = renderLibraryTree(s, records, library);
  assert.match(markup, /aria-expanded="false" data-library-group="plants"/);
  assert.match(markup, /role="group" hidden/);
  assert.ok(markup.indexOf('"/m"') < markup.indexOf('"/z"'));
  assert.equal((markup.match(/data-workspace-history-row-path=/g) || []).length, 3);
  assert.match(markup, /aria-level="3" aria-selected="true"/);
  assert.match(markup, /data-recent-path="\/m" aria-current="true"/);
  assert.doesNotMatch(markup, /data-project-delete-files|data-project-copy/);
});

test("names and paths are escaped and full-path import destinations disambiguate nesting", () => withStorage(() => {
  const special = { ...library, partitions: [...library.partitions, { id: "x", name: '<img src=x onerror="bad">', parentId: "rice" }] };
  saveProjectLibrary(special);
  const markup = renderLibraryTree(state(), [{ path: '/"<x>', projectName: '<script>bad</script>', partitionId: "x" }], special);
  assert.doesNotMatch(markup, /<script>|<img/);
  assert.match(markup, /&lt;script&gt;/);
  assert.match(markup, /data-app-tooltip-overflow="span"/);
  const picker = renderImportPartition(state("zh", { importPartitionId: "rice" }));
  assert.match(picker, /value="rice" selected>植物 \/ 水稻/);
  assert.match(picker, /<option value="">未分区/);
}));

test("moving a partition excludes itself and descendants; nonempty deletion cannot submit", () => withStorage(() => {
  const markup = renderLibraryDialog(state("en", { libraryDialog: { kind: "move-folder", id: "plants" } }));
  assert.doesNotMatch(markup, /value="plants"|value="rice"|value="wheat"/);
  assert.match(markup, /value="animals"/);
  const deletion = renderLibraryDialog(state("zh", { libraryDialog: { kind: "delete", id: "plants" } }));
  assert.match(deletion, /type="submit"[^>]*disabled/);
  assert.match(deletion, /不会删除项目文件/);
}));

test("unpartitioned is a fixed system entry with import but no rename, child or delete menu", () => {
  const markup = renderLibraryMenu(state("zh", { libraryMenu: { id: "", x: 2, y: 4 } }));
  assert.match(markup, /data-library-action="import"/);
  assert.doesNotMatch(markup, /data-library-action="(?:rename|create|delete|move-folder)"/);
});

function button(extra = {}) {
  const handlers = new Map();
  return { dataset: {}, ...extra, addEventListener: (type, fn) => handlers.set(type, fn), focus() {},
    fire(type, event = {}) { return handlers.get(type)?.({ preventDefault() {}, stopPropagation() {}, ...event }); } };
}
function store(initial) {
  let current = initial; return { getState: () => current, setState: patch => { current = { ...current, ...patch }; } };
}
function host(nodes) {
  return { querySelector: key => nodes[key] || null, querySelectorAll: key => nodes[key] ? [nodes[key]] : [] };
}

test("import selector and inline creation preserve the import draft and preselect the new partition", () => withStorage(() => {
  const input = button({ value: "rice" }), create = button({ dataset: { libraryCreate: "import" } });
  const s = store(state("zh", { importDialogOpen: true, zipPath: "/bundle.zip", projectNameInput: "draft", importPartitionId: "plants" }));
  const h = host({ "#import-partition": input, "[data-library-create]": create });
  const callbacks = { refresh() {}, openImport() {}, openProjectMenu() {} };
  bindProjectLibrary(h, s, callbacks);
  input.fire("change", { target: input }); create.fire("click");
  assert.deepEqual(s.getState().importer.libraryDialog, { kind: "create", parentId: "rice", forImport: true });
  const name = button({ value: "新分区" }), target = button({ value: "rice" }), cancel = button();
  const dialog = button({ querySelector: key => ({ "#library-name": name, "#library-target": target, "[data-library-dialog-close]": cancel }[key]), querySelectorAll: () => [name, target, cancel] });
  const overlay = { setAttribute() {} };
  bindProjectLibrary(host({ ".library-dialog": dialog, "[data-project-import-overlay]": overlay }), s, callbacks);
  assert.equal(overlay.inert, true);
  dialog.fire("submit");
  const created = readProjectLibrary().partitions.at(-1);
  assert.equal(created.name, "新分区"); assert.equal(created.parentId, "rice");
  assert.equal(s.getState().importer.importPartitionId, created.id);
  assert.equal(s.getState().importer.zipPath, "/bundle.zip");
  assert.equal(s.getState().importer.projectNameInput, "draft");
  assert.equal(s.getState().importer.libraryDialog, null);
}));

test("project move dialog changes membership without switching or closing the current project", () => withStorage(() => {
  writeWorkspaceHistory([{ path: "/mh63", projectName: "mh63" }]);
  const initial = state("zh", { libraryDialog: { kind: "move-project", path: "/mh63" } });
  initial.session = { workspacePath: "/mh63", projectId: 1 }; initial.projectPreview = { token: "keep" };
  const s = store(initial), target = button({ value: "rice" }), cancel = button();
  const dialog = button({ querySelector: key => ({ "#library-target": target, "[data-library-dialog-close]": cancel }[key]), querySelectorAll: () => [target, cancel] });
  bindProjectLibrary(host({ ".library-dialog": dialog }), s, { refresh() {}, openImport() {}, openProjectMenu() {} });
  dialog.fire("submit");
  assert.equal(readWorkspaceHistory()[0].partitionId, "rice");
  assert.equal(s.getState().session, initial.session);
  assert.equal(s.getState().projectPreview, initial.projectPreview);
  assert.equal(readProjectLibrary().collapsed.includes("plants"), false);
}));


test("tree rows reserve the menu column in both idle and hover states without changing row height", () => {
  const css = readFileSync(new URL("../../../styles/importer.css", import.meta.url), "utf8");
  assert.match(css, /\.library-tree \.project-recent-row,\s*\.library-tree \.project-recent-row:not\(:hover\):not\(:has\(:focus-visible\)\)\s*\{[^}]*grid-template-columns: minmax\(0, 1fr\) 26px;/);
  assert.match(css, /\.library-tree \.library-row-menu\s*\{\s*opacity: 0;/);
});
