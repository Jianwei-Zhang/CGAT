import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { createState } from "./tabs-semantics-harness.mjs";
import { installSubviewWorkspace, startSubviewWindowDraft, changeSubviewWindow, getSubviewWindowStore, hydrateSubviewTasks } from "../subview-workspace-state.js";
import { normalizeSubviewTasks, taskScopeKey } from "../subview-task-state.js";
import { installSubviewTaskPersistence } from "../subview-task-persistence.js";
import { renderSubviewTaskbar, subviewTaskMenuItems, subviewWindowDescription, renderSubviewWindowChrome } from "../render-subview-workspace.js";
import { getAssemblyI18n } from "../i18n.js";
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
function fixture() {
  const state = createState(); state.activeRoute = "assembly"; state.locale = "en";
  state.session.workspacePath = "D:/mock-tasks"; state.session.projectId = 1;
  const store = createStore(state); installSubviewWorkspace(store); return store;
}
function enter(store, left = 2, right = 5) {
  store.setState({ assembly: { ...startSubviewWindowDraft(store.getState().assembly),
    subview: { summary: { mode: "2-contig", top: { role: "primary", contigId: left }, bottom: { role: "primary", contigId: right } } } } });
  return store.getState().assembly.subviewWorkspace.activeId;
}
const windows = store => store.getState().assembly.subviewWorkspace.windows;
const document = store => store.getState().assembly.localViewTasks;

test("task order and current numbering change without changing stable IDs or scoped ownership", () => {
  const store = fixture(); const a = enter(store), b = enter(store, 5, 8), c = enter(store, 8, 9);
  const scoped = getSubviewWindowStore(store, a);
  changeSubviewWindow(store, a, "reorder", { beforeId: c });
  assert.deepEqual(windows(store).map(item => item.id), [b, c, a]);
  assert.deepEqual(windows(store).map(item => item.number), [1, 2, 3]);
  assert.equal(scoped.isLocalViewAlive(), true);
  changeSubviewWindow(store, c, "close");
  assert.deepEqual(windows(store).map(item => item.number), [1, 2]);
  assert.equal(scoped.getState().assembly.subview.summary.bottom.contigId, 5);
  assert.deepEqual(document(store).scopes[taskScopeKey(store.getState().assembly)].map(item => item.id), [b, a]);
});

test("single docked slot replaces views without deleting tasks or changing floating peers", () => {
  const store = fixture(); const a = enter(store), b = enter(store), c = enter(store);
  changeSubviewWindow(store, a, "open-docked");
  changeSubviewWindow(store, c, "open-docked");
  assert.equal(windows(store).find(item => item.id === a).opened, false);
  assert.equal(windows(store).find(item => item.id === b).floating, true);
  changeSubviewWindow(store, a, "activate");
  assert.equal(windows(store).find(item => item.id === c).opened, false);
  assert.equal(windows(store).filter(item => item.opened && !item.floating).length, 1);
  changeSubviewWindow(store, b, "activate");
  assert.equal(windows(store).find(item => item.id === a).opened, true);
  assert.equal(windows(store).length, 3);
});

test("durable task round trip includes logical edits and notes but excludes evidence and window state", () => {
  const store = fixture(), a = enter(store); const scoped = getSubviewWindowStore(store, a);
  scoped.setState({ assembly: { ...scoped.getState().assembly, subview: { ...scoped.getState().assembly.subview,
    flippedCtgs: [{ slot: "top", contigId: 2 }], pairwiseEvidence: { hits: [{ biological: "not-a-layout-field" }], requestKey: "pending" } } } });
  changeSubviewWindow(store, a, "metadata", { name: "  my view  ", note: "Line 1\nLine 2" });
  changeSubviewWindow(store, a, "position", { x: 1, y: 2, width: 900, height: 700 });
  changeSubviewWindow(store, a, "native-geometry", { nativeBounds: { x: -1000, y: 200, width: 900, height: 700 } });
  changeSubviewWindow(store, a, "minimize");
  const saved = JSON.parse(JSON.stringify(document(store)));
  const text = JSON.stringify(saved);
  for (const key of ["pairwiseEvidence", "requestKey", "biological", "minimized", "maximized", "floating", "opened", "nativeBounds", '"width"', '"height"']) assert.ok(!text.includes(key), key);
  const restored = fixture(); hydrateSubviewTasks(restored, saved, document(restored));
  const task = windows(restored)[0];
  assert.equal(task.id, a); assert.equal(task.name, "my view"); assert.equal(task.note, "Line 1\nLine 2");
  assert.equal(task.opened, false); assert.equal(task.minimized, false);
  assert.deepEqual(task.snapshot.subview.flippedCtgs, [{ slot: "top", contigId: 2 }]);
  changeSubviewWindow(restored, a, "activate");
  assert.equal(windows(restored)[0].floating, false);
  assert.equal(restored.getState().assembly.subview.summary.bottom.contigId, 5);
});

test("different chromosome and support scopes restore unopened tasks; project changes cannot inherit them", () => {
  const store = fixture(), a = enter(store);
  const original = store.getState().assembly.selectedChrName;
  for (const selectedChrName of ["other", original]) store.setState({ assembly: { ...store.getState().assembly, selectedChrName } });
  assert.equal(windows(store)[0].id, a); assert.equal(windows(store)[0].opened, false);
  const support = store.getState().assembly.supportDatasetId;
  for (const supportDatasetId of [987, support]) store.setState({ assembly: { ...store.getState().assembly, supportDatasetId } });
  assert.equal(windows(store)[0].id, a);
  store.setState({ session: { ...store.getState().session, projectId: 2 } });
  assert.equal(windows(store).length, 0);
});

test("metadata is escaped, taskbar keeps only close, and maximize is unavailable in every state", () => {
  const store = fixture(), a = enter(store);
  changeSubviewWindow(store, a, "metadata", { name: '<img src=x onerror="boom">', note: 'note <script>' });
  const labels = getAssemblyI18n(store.getState()).subview;
  const html = renderSubviewTaskbar(store.getState().assembly.subviewWorkspace, labels, store.getState().assembly);
  assert.match(html, /draggable="false"/); assert.match(html, /&lt;img/); assert.doesNotMatch(html, /<img|<script|action="minimize"/);
  assert.match(subviewWindowDescription(windows(store)[0], labels).tooltip, /note <script>/);
  assert.ok(!subviewTaskMenuItems(windows(store)[0], labels).some(item => item.action === "maximize"));
  changeSubviewWindow(store, a, "open-docked");
  assert.ok(!subviewTaskMenuItems(windows(store)[0], labels).some(item => item.action === "maximize"));
  assert.equal(changeSubviewWindow(store, a, "maximize"), false);
});

test("geometry, focus and evidence-only changes do not dirty the durable task document", () => {
  const store = fixture(), a = enter(store), before = document(store);
  changeSubviewWindow(store, a, "position", { x: 25, y: 100 });
  changeSubviewWindow(store, a, "minimize"); changeSubviewWindow(store, a, "activate");
  assert.equal(document(store), before);
  const scoped = getSubviewWindowStore(store, a);
  scoped.setState({ assembly: { ...scoped.getState().assembly, subview: { ...scoped.getState().assembly.subview, pairwiseEvidence: { hits: [1, 2] } } } });
  assert.equal(document(store), before);
});

test("future/corrupt documents fail closed instead of becoming empty saved data", () => {
  assert.throws(() => normalizeSubviewTasks({ version: 2, scopes: {} }), /Unsupported/);
  assert.throws(() => normalizeSubviewTasks({ version: 1, scopes: { bad: [] } }), /Invalid/);
  assert.deepEqual(normalizeSubviewTasks(null), { version: 1, scopes: {} });
});

test("async task hydration preserves edits made while reading and serializes saves", async () => {
  const savedStore = fixture(); enter(savedStore); const saved = document(savedStore);
  const store = fixture(); let resolve; const writes = [];
  const controller = installSubviewTaskPersistence(store, { saveDelay: 0, load: () => new Promise(r => { resolve = r; }), save: async args => { writes.push(args); } });
  await tick(); const a = enter(store, 8, 9); changeSubviewWindow(store, a, "metadata", { name: "new edit" });
  resolve(saved); await controller.flush();
  assert.equal(windows(store).length, 2); assert.equal(windows(store).at(-1).id, a);
  assert.equal(windows(store)[0].opened, false, "previously unseen saved task is retained, not overwritten");
  assert.equal(writes.at(-1).state.scopes[taskScopeKey(store.getState().assembly)].at(-1).name, "new edit");
  controller.destroy();
});

test("saved tasks supersede a legacy active-view bootstrap; closing during load does not resurrect", () => {
  const savedStore = fixture(); const savedId = enter(savedStore); const saved = document(savedStore);
  const store = fixture(); enter(store); const baseline = document(store);
  hydrateSubviewTasks(store, saved, baseline);
  assert.deepEqual(windows(store).map(item => item.id), [savedId]);
  const other = fixture(); hydrateSubviewTasks(other, saved, document(other));
  const otherBaseline = document(other);
  changeSubviewWindow(other, savedId, "close"); hydrateSubviewTasks(other, saved, otherBaseline);
  assert.equal(windows(other).length, 0);
});

test("late project load cannot hydrate another project or resurrect an ABA generation", async () => {
  const savedStore = fixture(); enter(savedStore); const saved = document(savedStore);
  const store = fixture(), loads = [];
  const controller = installSubviewTaskPersistence(store, { saveDelay: 0, load: args => new Promise(resolve => loads.push({ args, resolve })), save: async () => {} });
  await tick();
  store.setState({ session: { ...store.getState().session, projectId: 2 } }); await tick();
  loads[0].resolve(saved); await tick(); assert.equal(windows(store).length, 0);
  loads[1].resolve({ version: 1, scopes: {} }); await controller.flush();
  assert.equal(windows(store).length, 0); controller.destroy();
});

test("load failure never triggers an empty save and explicit flush reports it", async () => {
  const store = fixture(); let writes = 0;
  const controller = installSubviewTaskPersistence(store, { saveDelay: 0, load: async () => { throw new Error("read failed"); }, save: async () => { writes++; } });
  await assert.rejects(controller.flush(), /read failed/); assert.equal(writes, 0);
  assert.match(store.getState().assembly.localViewTaskSaveError, /read failed/); controller.destroy();
});


test("failed autosave does not spin; an explicit retry saves the latest edit", async () => {
  const store = fixture(); const a = enter(store); let fail = true, writes = 0;
  const controller = installSubviewTaskPersistence(store, { saveDelay: 0, load: async () => ({ version: 1, scopes: {} }), save: async () => {
    writes++; if (fail) throw new Error("disk full");
  } });
  await tick(); await tick();
  assert.equal(writes, 1);
  assert.match(store.getState().assembly.localViewTaskSaveError, /disk full/);
  changeSubviewWindow(store, a, "metadata", { note: "keep this edit" });
  await tick(); await tick(); assert.equal(writes, 2);
  fail = false; await controller.flush();
  assert.equal(writes, 3); assert.equal(store.getState().assembly.localViewTaskSaveError, "");
  controller.destroy();
});

test("project A writes remain serialized before B loading and carry A's captured identity", async () => {
  const store = fixture(); enter(store); const writes = []; let release;
  const controller = installSubviewTaskPersistence(store, { saveDelay: 0, load: async () => ({ version: 1, scopes: {} }), save: args => {
    writes.push(args); return writes.length === 1 ? new Promise(resolve => { release = resolve; }) : Promise.resolve();
  } });
  await tick();
  store.setState({ session: { ...store.getState().session, projectId: 2 } });
  assert.equal(writes[0].projectId, 1);
  release(); await controller.flush();
  assert.equal(writes.at(-1).projectId, 2);
  assert.equal(windows(store).length, 0); controller.destroy();
});


test("composition task restores source-backed fragments, lane positions and genomic viewport", () => {
  const store = fixture();
  store.setState({ assembly: { ...startSubviewWindowDraft(store.getState().assembly),
    subview: { mode: "composition", summary: { mode: "composition", layoutGapBp: 30, members: [{
      entityKey: "source-fragment", assemblyCtgId: 2, originSourceSeqId: 17,
      source: { role: "primary", datasetId: 11 }, lane: "bottom", xBp: -400, lengthBp: 100,
      baseOrientation: "-", flipped: true, displayOffsetBp: 20, displayScale: 2,
    }] } }, subviewCompositionViewport: { leftBp: -500, bpPerPx: 20, topPx: 12 } } });
  const saved = document(store); const restored = fixture(); hydrateSubviewTasks(restored, saved, document(restored));
  const snapshot = windows(restored)[0].snapshot, member = snapshot.subview.summary.members[0];
  assert.equal(member.originSourceSeqId, 17); assert.equal(member.source.datasetId, 11);
  assert.equal(member.lane, "bottom"); assert.equal(member.xBp, -400); assert.equal(member.displayScale, 2);
  assert.equal(member.flipped, true); assert.equal(member.baseOrientation, "-");
  assert.deepEqual(snapshot.subviewCompositionViewport, { leftBp: -500, bpPerPx: 20, topPx: 12 });
});

test("menu labels and grouping are concise and consistent in both languages", () => {
  const store = fixture(); enter(store);
  for (const locale of ["zh", "en"]) {
    store.setState({ locale }); const labels = getAssemblyI18n(store.getState()).subview;
    const menu = subviewTaskMenuItems(windows(store)[0], labels);
    assert.deepEqual(menu.map(item => item.group), ["open", "open", "window", "metadata", "metadata", "close"]);
    assert.deepEqual(menu.map(item => item.label), locale === "zh"
      ? ["停靠打开", "悬浮打开", "最小化", "重命名", "编辑备注", "关闭"]
      : ["Open docked", "Open floating", "Minimize", "Rename", "Edit notes", "Close"]);
    assert.equal(menu[0].checked, false); assert.equal(menu[1].checked, true);
    assert.equal(menu.at(-1).danger, true);
  }
});


test("untouched empty scopes allow legacy migration; explicitly closed scopes stay empty", () => {
  const store = fixture(), scope = taskScopeKey(store.getState().assembly);
  assert.equal(Object.hasOwn(document(store).scopes, scope), false);
  const id = enter(store); changeSubviewWindow(store, id, "close");
  assert.equal(Object.hasOwn(document(store).scopes, scope), true);
  assert.deepEqual(document(store).scopes[scope], []);
});


test("Main loading cannot overwrite a task activated after the request began", () => {
  const store = fixture(), a = enter(store, 2, 5), b = enter(store, 5, 8);
  changeSubviewWindow(store, a, "activate"); const stale = store.getState().assembly.subview;
  store.setState({ assembly: { ...store.getState().assembly, loading: true } });
  changeSubviewWindow(store, b, "activate");
  store.setState({ assembly: { ...store.getState().assembly, loading: false, subview: stale } });
  assert.equal(store.getState().assembly.subviewWorkspace.activeId, b);
  assert.equal(getSubviewWindowStore(store, b).getState().assembly.subview.summary.bottom.contigId, 8);
  assert.equal(windows(store).length, 2);
});

test("Main loading cannot resurrect a task closed while the request was in flight", () => {
  const store = fixture(), a = enter(store, 2, 5), stale = store.getState().assembly.subview;
  store.setState({ assembly: { ...store.getState().assembly, loading: true } });
  changeSubviewWindow(store, a, "close");
  store.setState({ assembly: { ...store.getState().assembly, loading: false, subview: stale } });
  assert.equal(windows(store).length, 0);
  assert.equal(store.getState().assembly.subview, null);
});


test("application pin defaults on but never enters the project task document", () => {
  const store = fixture(), id = enter(store);
  const saved = structuredClone(document(store)), scoped = getSubviewWindowStore(store, id);
  const summary = scoped.getState().assembly.subview.summary;
  assert.equal(windows(store)[0].pinned, true);
  changeSubviewWindow(store, id, "pin");
  assert.equal(windows(store)[0].pinned, false);
  assert.equal(scoped.getState().assembly.subview.summary, summary);
  assert.deepEqual(document(store), saved);
  changeSubviewWindow(store, id, "pin");
  assert.equal(windows(store)[0].pinned, true);
  assert.deepEqual(document(store), saved);
  changeSubviewWindow(store, id, "open-docked");
  assert.equal(changeSubviewWindow(store, id, "pin"), false);
  changeSubviewWindow(store, id, "open-floating");
  assert.equal(windows(store)[0].pinned, true);
});

for (const locale of ["en", "zh"]) test(`native pin chrome and menu agree and disappear when docked (${locale})`, () => {
  const store = fixture(), id = enter(store);
  const labels = getAssemblyI18n({ locale }).subview;
  const assembly = () => ({ ...store.getState().assembly, subviewNativeWindows: true, subviewWindowRendering: id });
  const menu = () => subviewTaskMenuItems(windows(store)[0], labels, assembly());
  let chrome = renderSubviewWindowChrome(assembly(), labels, true);
  assert.match(chrome, /data-local-view-action="pin"[^>]*aria-pressed="true"/);
  assert.ok(chrome.indexOf('data-local-view-action="pin"') < chrome.indexOf('data-local-view-action="minimize"'));
  assert.equal(menu().find(item => item.action === "pin").role, "menuitemcheckbox");
  assert.equal(menu().find(item => item.action === "pin").checked, true);
  changeSubviewWindow(store, id, "pin");
  assert.equal(menu().find(item => item.action === "pin").checked, false);
  assert.match(renderSubviewWindowChrome(assembly(), labels, true), /aria-pressed="false"/);
  changeSubviewWindow(store, id, "open-docked");
  assert.ok(!menu().some(item => item.action === "pin"));
  assert.doesNotMatch(renderSubviewWindowChrome(assembly(), labels, true), /data-local-view-action="pin"/);
});
