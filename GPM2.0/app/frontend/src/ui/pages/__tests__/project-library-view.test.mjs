import { projectIcon } from "../project-icons.js";
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { renderLibraryTree, renderImportPartition, renderLibraryDialog, renderLibraryMenu, bindProjectLibrary } from "../project-library-view.js";
import { renderProjectsBody } from "../projects-view.js";
import { getMessages } from "../../i18n/index.js";
import { readProjectLibrary, saveProjectLibrary, projectPartition } from "../../../services/project-library.js";
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

test("moving a partition excludes descendants; deleting a nonempty partition requires explicit confirmation", () => withStorage(() => {
  const markup = renderLibraryDialog(state("en", { libraryDialog: { kind: "move-folder", id: "plants" } }));
  assert.doesNotMatch(markup, /value="plants"|value="rice"|value="wheat"/);
  assert.match(markup, /value="animals"/);
  const deletion = renderLibraryDialog(state("zh", { libraryDialog: { kind: "delete", id: "plants" } }));
  assert.doesNotMatch(deletion, /type="submit"[^>]*disabled/);
  assert.match(deletion, /将删除 3 个分区（含当前分区），移动 0 个项目/);
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


for (const id of ["", "plants", "rice"]) {
  test(`clicking partition name toggles persisted expansion without switching the project: ${id || "unpartitioned"}`, () => withStorage(() => {
    const selected = new Set(), attrs = new Map(), children = { hidden: library.collapsed.includes(id) };
    const row = { classList: { add: key => selected.add(key), remove: key => selected.delete(key) } };
    const name = button({ dataset: { librarySelect: id }, closest: () => row });
    const toggle = { setAttribute: (key, value) => attrs.set(key, value) };
    const group = { dataset: { libraryGroup: id }, hasAttribute: () => true, setAttribute: (key, value) => attrs.set(key, value),
      querySelector: key => key === ":scope > [role=group]" ? children : toggle };
    const initial = state("zh", { libraryRevealedPath: "/active" });
    initial.session = { workspacePath: "/active", projectId: 1 };
    const s = store(initial);
    const h = host({ "[data-library-select]": name, "[data-library-group]": group });
    bindProjectLibrary(h, s, { refresh() {}, openImport() {}, openProjectMenu() {} });
    const before = readProjectLibrary().collapsed.includes(id);
    name.fire("click");
    assert.equal(readProjectLibrary().collapsed.includes(id), !before);
    assert.equal(children.hidden, !before);
    assert.equal(s.getState().session, initial.session);
    name.fire("click");
    assert.equal(readProjectLibrary().collapsed.includes(id), before);
    assert.equal(children.hidden, before);
  }));
}

for (const locale of ["en", "zh"]) {
  test(`${locale} root menu exposes only overflow commands and does not duplicate the visible create button`, () => {
    const wide = renderLibraryMenu(state(locale, { libraryMenu: { root: true }, libraryOverflowActions: [] }));
    assert.match(wide, /data-library-overflow-action="create" hidden/);
    assert.match(wide, /data-library-overflow-action="validate" hidden/);
    assert.match(wide, /data-library-overflow-action="delete-failed" hidden/);
    const narrow = renderLibraryMenu(state(locale, { libraryMenu: { root: true }, libraryOverflowActions: ["validate", "delete-failed"] }));
    assert.match(narrow, /data-library-overflow-action="create" hidden/);
    assert.doesNotMatch(narrow, /data-library-overflow-action="(?:validate|delete-failed)" hidden/);
    assert.match(narrow, locale === "en" ? /Validate/ : /校验项目/);
    assert.match(narrow, locale === "en" ? /Delete failed/ : /删除失败/);
  });
}


for (const action of ["validate", "delete-failed"]) {
  test(`overflow ${action} delegates to the existing action and respects disabled state`, () => withStorage(() => {
    globalThis.window.innerWidth = 800; globalThis.window.innerHeight = 600;
    let called = 0;
    const item = button({ dataset: { libraryAction: action }, hidden: false, disabled: false });
    const menu = button({ style: {}, getBoundingClientRect: () => ({ left: 10, top: 10, width: 150, height: 100 }),
      querySelectorAll: () => [item], remove() {}, contains: () => true });
    const original = { click() { called++; } };
    const s = store(state("en", { libraryMenu: { root: true }, libraryOverflowActions: [action] }));
    const h = host({ "[data-library-menu]": menu, [action === "validate" ? "#validate-history-button" : "#delete-failed-history-button"]: original });
    bindProjectLibrary(h, s, { refresh() {}, openImport() {}, openProjectMenu() {} });
    item.disabled = true; item.fire("click"); assert.equal(called, 0);
    item.disabled = false; item.fire("click"); assert.equal(called, 1);
    assert.equal(s.getState().importer.libraryMenu, null);
  }));
}


for (const locale of ["zh", "en"]) {
  test(`${locale} deletion confirmation counts all nested partitions and projects without deleting project files`, () => withStorage(() => {
    writeWorkspaceHistory([{ path: "/direct", partitionId: "plants" }, { path: "/nested", partitionId: "rice" }, { path: "/other", partitionId: "animals" }]);
    const markup = renderLibraryDialog(state(locale, { libraryDialog: { kind: "delete", id: "plants" } }));
    assert.match(markup, locale === "zh" ? /将删除 3 个分区（含当前分区），移动 2 个项目/ : /Partitions to delete: 3.*Projects to move: 2/);
    assert.match(markup, locale === "zh" ? /内部项目全部移到“未分区”，不会删除项目文件/ : /projects will move to Unpartitioned; no project files will be deleted/);
    assert.doesNotMatch(markup, /type="submit"[^>]*disabled/);
    const missing = renderLibraryDialog(state(locale, { libraryDialog: { kind: "delete", id: "missing" } }));
    assert.match(missing, /type="submit"[^>]*disabled/);
  }));
}

for (const action of ["confirm", "cancel", "storage-failure"]) {
  test(`nonempty partition deletion ${action} preserves project inventory and the open project`, () => withStorage(() => {
    const records = [{ path: "/mh63", partitionId: "rice", projectName: "mh63", note: "keep" }, { path: "/other", partitionId: "animals" }];
    writeWorkspaceHistory(records);
    const initial = state("zh", { libraryDialog: { kind: "delete", id: "plants" }, libraryRevealedPath: "/mh63",
      librarySelectedId: "rice", importPartitionId: "rice" });
    initial.session = { workspacePath: "/mh63", projectId: 1 }; initial.projectPreview = { token: "keep" };
    const s = store(initial), cancel = button();
    const dialog = button({ querySelector: key => key === "[data-library-dialog-close]" ? cancel : null, querySelectorAll: () => [cancel] });
    bindProjectLibrary(host({ ".library-dialog": dialog }), s, { refresh() {}, openImport() {}, openProjectMenu() {} });
    if (action === "storage-failure") globalThis.window.localStorage.setItem = () => { throw new Error("quota"); };
    if (action === "cancel") cancel.fire("click"); else dialog.fire("submit");
    assert.equal(s.getState().session, initial.session);
    assert.equal(s.getState().projectPreview, initial.projectPreview);
    assert.deepEqual(readWorkspaceHistory(), records);
    const next = readProjectLibrary();
    if (action === "confirm") {
      assert.deepEqual(next.partitions.map(node => node.id), ["animals"]);
      assert.equal(projectPartition(next, records[0]), "");
      assert.equal(projectPartition(next, records[1]), "animals");
      assert.equal(s.getState().importer.libraryDialog, null);
      assert.equal(s.getState().importer.importPartitionId, "");
      assert.equal(s.getState().importer.librarySelectedId, "");
    } else {
      assert.deepEqual(next, library);
      assert.equal(projectPartition(next, records[0]), "rice");
      if (action === "storage-failure") assert.equal(s.getState().importer.libraryDialog.error, "storage");
      else assert.equal(s.getState().importer.libraryDialog, null);
    }
  }));
}


for (const locale of ["zh", "en"]) {
  test(`${locale} every library menu action starts with its matching decorative icon and keeps readable text`, () => {
    const expected = { create: "newPartition", validate: "validate", "delete-failed": "delete", collapse: "collapse", expand: "expand",
      import: "import", rename: "rename", "move-folder": "arrow", delete: "delete" };
    for (const menu of [{ root: true }, { id: "plants" }, { id: "" }]) {
      const markup = renderLibraryMenu(state(locale, { libraryMenu: menu, libraryOverflowActions: ["create", "validate", "delete-failed"] }));
      const items = [...markup.matchAll(/<button[^>]*data-library-action="([^"]+)"[^>]*>([\s\S]*?)<\/button>/g)];
      assert.ok(items.length);
      for (const [, action, content] of items) {
        assert.ok(content.startsWith(projectIcon(expected[action])), `${action} has the matching icon first`);
        assert.match(content, /<svg[^>]*aria-hidden="true"[^>]*focusable="false"/);
        assert.match(content, /<span>[^<]+<\/span>$/);
      }
    }
  });
}

test("library menus use visible content width without changing the project context menu minimum", () => {
  const css = readFileSync(new URL("../../../styles/importer.css", import.meta.url), "utf8");
  assert.match(css, /\.workspace-history-context-menu\[data-library-menu\]\s*\{[^}]*width: max-content;[^}]*min-width: 0;/);
  assert.match(css, /\[data-library-menu\] \.context-menu-item\s*\{[^}]*display: flex;[^}]*gap: 8px;/);
  assert.match(css, /\[data-library-menu\] \[hidden\][^{]*\{[^}]*display: none !important/);
  const overlays = readFileSync(new URL("../../../styles/overlays.css", import.meta.url), "utf8");
  assert.match(overlays, /\.workspace-history-context-menu\s*\{[^}]*min-width: min\(224px,[^}]*max-width: calc\(100vw - 16px\)/);
});
