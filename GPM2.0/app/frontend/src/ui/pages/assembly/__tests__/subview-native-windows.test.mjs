import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import { createNativeSubviewWindows } from "../subview-native-windows.js";
import { installSubviewWorkspace, changeSubviewWindow, startSubviewWindowDraft } from "../subview-workspace-state.js";
import { getAssemblyI18n } from "../i18n.js";
function fixture({ failOpen = false } = {}) {
  const store = createStore({ activeRoute: "assembly", locale: "en", session: { projectId: 1, workspacePath: "fixture" }, assembly: {
    selectedChrName: "chr1", subview: { summary: { mode: "2-contig", top: { role: "primary", contigId: 1 }, bottom: { role: "primary", contigId: 2 } } },
  } });
  installSubviewWorkspace(store);
  let serial = 0, destroyedListener;
  const urls = [], calls = [], main = { unminimize: async () => { calls.push("restore-main"); }, setFocus: async () => { calls.push("focus-main"); } };
  const win = { __GPM_NATIVE_LOCAL_VIEWS__: true, location: { href: "http://tauri.localhost/", origin: "http://tauri.localhost" },
    crypto: { randomUUID: () => `12345678-1234-1234-1234-${String(++serial).padStart(12, "0")}` },
    open(url) { if (failOpen) throw new Error("native creation failed"); urls.push(new URL(url)); },
    MutationObserver: class { observe() {} disconnect() {} },
    __TAURI__: { window: { getCurrentWindow: () => main }, event: { listen: async (_event, fn) => { destroyedListener = fn; return () => {}; } },
      webviewWindow: { WebviewWindow: { getByLabel: async () => null } } },
  };
  const doc = { defaultView: win, documentElement: { dataset: {}, style: { getPropertyValue: () => "" } } };
  const root = { ownerDocument: doc, isConnected: true };
  const manager = createNativeSubviewWindows(root, store, { getLabels: getAssemblyI18n, disposeWindow() {} });
  return { store, win, root, manager, urls, calls, notifyDestroyed: payload => destroyedListener({ payload }), id: store.getState().assembly.subviewWorkspace.activeId };
}

test("native mode opens each task once and does not copy project state", () => {
  const f = fixture();
  try {
    assert.equal(f.urls.length, 1); assert.equal(f.urls[0].pathname, "/local-view.html");
    assert.equal(f.urls[0].searchParams.get("view"), f.id);
    assert.equal(f.urls[0].searchParams.get("pinned"), "1");
    assert.equal(f.store.getState().assembly.subviewNativeWindows, true);
    f.manager.sync(); assert.equal(f.urls.length, 1);
    const assembly = f.store.getState().assembly;
    f.store.setState({ assembly: { ...startSubviewWindowDraft(assembly), subview: assembly.subview } });
    assert.equal(f.urls.length, 2);
  } finally { f.manager.destroy(); }
});

test("invalid token, closed task and changed generation cannot connect a late peer", async () => {
  const f = fixture();
  try {
    await assert.rejects(f.win.__gpmLocalViews.connect(f.id, "wrong", {}), /expired/);
    const token = f.urls[0].searchParams.get("token");
    changeSubviewWindow(f.store, f.id, "close");
    await assert.rejects(f.win.__gpmLocalViews.connect(f.id, token, {}), /expired/);
    assert.equal(f.store.getState().assembly.subviewWorkspace.windows.length, 0);
  } finally { f.manager.destroy(); }
});

test("native creation failure preserves task content by returning it to the dock", () => {
  const f = fixture({ failOpen: true });
  try {
    const task = f.store.getState().assembly.subviewWorkspace.windows[0];
    assert.equal(task.floating, false); assert.equal(task.opened, true);
    assert.equal(task.snapshot.subview.summary.bottom.contigId, 2);
    assert.match(f.store.getState().assembly.subviewNativeError, /native creation failed/);
  } finally { f.manager.destroy(); }
});

test("docked activation targets main OS window and manager destruction prevents new popups", async () => {
  const f = fixture();
  changeSubviewWindow(f.store, f.id, "open-docked"); await f.manager.focus(f.id);
  assert.deepEqual(f.calls, ["restore-main", "focus-main"]);
  f.manager.destroy();
  changeSubviewWindow(f.store, f.id, "open-floating"); assert.equal(f.urls.length, 1);
  assert.equal(f.win.__gpmLocalViews, undefined);
});

test("browser fallback does not pretend in-page floats are native windows", () => {
  assert.equal(createNativeSubviewWindows({ ownerDocument: { defaultView: {} } }, {}, {}), null);
});


test("delayed native destroyed event cannot close a reopened task with the same stable ID", () => {
  const f = fixture();
  try {
    const token = f.urls[0].searchParams.get("token");
    changeSubviewWindow(f.store, f.id, "open-docked");
    changeSubviewWindow(f.store, f.id, "open-floating");
    const newToken = f.urls[1].searchParams.get("token");
    assert.notEqual(newToken, token);
    f.notifyDestroyed({ view: f.id, token });
    assert.equal(f.store.getState().assembly.subviewWorkspace.windows.length, 1);
    f.notifyDestroyed({ view: f.id, token: newToken });
    assert.equal(f.store.getState().assembly.subviewWorkspace.windows.length, 0);
  } finally { f.manager.destroy(); }
});


test("native drag coordinates resolve only a live owner document", async () => {
  const f = fixture();
  try {
    let point = { label: "main", x: 25, y: 80, pressed: true, escape: false };
    f.win.__TAURI__.core = { invoke: async name => { assert.equal(name, "probe_local_view_drag"); return point; } };
    assert.equal((await f.manager.dragPoint()).document, f.root.ownerDocument);
    point = { ...point, label: "local-view-expired--old-token" };
    assert.equal((await f.manager.dragPoint()).document, null);
    let resolve;
    f.win.__TAURI__.core.invoke = () => new Promise(done => { resolve = done; });
    const delayed = f.manager.dragPoint();
    f.store.setState({ assembly: { ...f.store.getState().assembly, selectedChrName: "chr2" } });
    resolve({ ...point, label: "main" });
    assert.equal(await delayed, null);
  } finally { f.manager.destroy(); }
});


test("reopening an unpinned native view preserves its native opening preference", () => {
  const f = fixture();
  try {
    changeSubviewWindow(f.store, f.id, "pin");
    changeSubviewWindow(f.store, f.id, "open-docked");
    changeSubviewWindow(f.store, f.id, "open-floating");
    assert.equal(f.urls.at(-1).searchParams.get("pinned"), "0");
    assert.equal(f.store.getState().assembly.subviewWorkspace.windows[0].pinned, false);
  } finally { f.manager.destroy(); }
});
