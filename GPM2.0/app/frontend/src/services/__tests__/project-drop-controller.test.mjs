import test from "node:test";
import assert from "node:assert/strict";
import { createProjectDropController, localWorkspaceTimestamp, relocateWorkspaceSuggestion, projectEntryBusy } from "../project-drop-controller.js";

function harness(overrides = {}) {
  let state = { locale: "en", activeRoute: "assembly", importer: {}, initializer: {}, session: { workspacePath: "/previous", projectId: 4 } };
  const calls = []; const notices = [];
  const store = { getState: () => state, setState: patch => { state = { ...state, ...patch }; } };
  const handle = createProjectDropController({ store, now: () => new Date(2026, 9, 8, 14, 30, 25),
    inspect: async (path, stamp) => { calls.push(["inspect", path, stamp]); return { kind: "archive", path, suggestedWorkspace: "/deliveries/sample_20261008_143025" }; },
    prepareSwitch: async () => calls.push(["flush"]),
    openWorkspace: async path => calls.push(["open", path]),
    importExtracted: async path => calls.push(["import", path]),
    notice: async message => notices.push(message), refresh: () => calls.push(["refresh"]),
    overlay: (...args) => calls.push(["overlay", ...args]), ...overrides,
  });
  return { store, handle, calls, notices };
}
const drop = path => ({ payload: { type: "drop", paths: [path] } });

test("local timestamp includes seconds with filename-safe padding", () => {
  assert.equal(localWorkspaceTimestamp(new Date(2026, 0, 2, 3, 4, 5)), "20260102_030405");
});
for (const suffix of [".zip", ".tar.gz", ".tgz"]) {
  test(`native ${suffix} drop prepares the existing editable import dialog without importing`, async () => {
    const h = harness(); assert.equal(await h.handle(drop(`/deliveries/sample${suffix}`)), true);
    assert.deepEqual(h.calls.find(row => row[0] === "inspect"), ["inspect", `/deliveries/sample${suffix}`, "20261008_143025"]);
    const state = h.store.getState();
    assert.equal(state.activeRoute, "importer"); assert.equal(state.importer.importDialogOpen, true);
    assert.equal(state.importer.requireNewWorkspace, true);
    assert.equal(state.importer.workspaceRoot, "/deliveries/sample_20261008_143025");
    assert.deepEqual(state.session, { workspacePath: "/previous", projectId: 4 });
    assert.equal(h.calls.some(row => row[0] === "open" || row[0] === "import"), false);
    assert.ok(h.calls.findIndex(row => row[0] === "flush") < h.calls.findIndex(row => row[0] === "refresh"));
    const path = state.importer.workspaceRoot;
    await h.handle({ type: "leave" }); assert.equal(h.store.getState().importer.workspaceRoot, path);
  });
}
test("existing workspace goes only through open; extracted delivery goes only through import", async () => {
  for (const kind of ["workspace", "extracted"]) {
    const h = harness({ inspect: async () => ({ kind, path: "/resolved/gpm_server" }) });
    assert.equal(await h.handle(drop("/wrapper")), true);
    assert.ok(h.calls.some(row => row[0] === (kind === "workspace" ? "open" : "import") && row[1] === "/resolved/gpm_server"));
    assert.equal(h.calls.some(row => row[0] === (kind === "workspace" ? "import" : "open")), false);
    assert.equal(h.store.getState().importer.entryResolving, false);
  }
});
test("dropping the active canonical workspace is a no-op", async () => {
  const h = harness({ inspect: async () => ({ kind: "workspace", path: "/previous/" }) });
  assert.equal(await h.handle(drop("/alias")), true);
  assert.equal(h.calls.some(row => ["open", "flush", "import"].includes(row[0])), false);
  assert.match(h.notices[0], /already open/); assert.equal(h.store.getState().activeRoute, "assembly");
});
test("multi-item, fake filename and busy drops cannot reach the filesystem inspector", async () => {
  for (const payload of [{ type: "drop", paths: ["/a", "/b"] }, { type: "drop", files: [{ name: "a.zip" }] }, { type: "drop", paths: [null] }]) {
    const h = harness(); await h.handle(payload);
    assert.equal(h.calls.some(row => row[0] === "inspect"), false); assert.equal(h.notices.length, 1);
  }
  for (const patch of [{ importer: { restoringSession: true } }, { importer: { inFlight: true } }, { importer: { copyDialog: { open: true } } },
    { importer: { importDialogOpen: true } }, { initializer: { updating: true } }, { initializer: { autoPipelineRunning: true } }]) {
    const h = harness(); h.store.setState(patch); await h.handle(drop("/a.zip"));
    assert.equal(h.calls.some(row => row[0] === "inspect"), false); assert.match(h.notices[0], /Finish/);
  }
});
test("a second native drop while classification is pending cannot duplicate the operation", async () => {
  let resolve; let count = 0;
  const h = harness({ inspect: () => { count++; return new Promise(r => { resolve = r; }); } });
  const pending = h.handle(drop("/sample.zip"));
  assert.equal(h.store.getState().importer.entryResolving, true);
  assert.equal(await h.handle(drop("/sample.zip")), false);
  resolve({ kind: "archive", path: "/sample.zip", suggestedWorkspace: "/sample_20261008_143025" });
  await pending; assert.equal(count, 1); assert.equal(h.store.getState().importer.entryResolving, false);
});
test("conflicting work started during inspection prevents session switching", async () => {
  let resolve;
  const h = harness({ inspect: () => new Promise(r => { resolve = r; }) });
  const pending = h.handle(drop("/sample.zip"));
  h.store.setState({ initializer: { updating: true } });
  resolve({ kind: "archive", path: "/sample.zip", suggestedWorkspace: "/destination" });
  assert.equal(await pending, false); assert.equal(h.store.getState().activeRoute, "assembly");
  assert.equal(h.calls.some(row => row[0] === "flush"), false);
});
test("failed classification, save, and workspace opens preserve the previous session and expose errors", async () => {
  for (const overrides of [
    { inspect: async () => { throw new Error("broken database"); } },
    { prepareSwitch: async () => { throw new Error("save failed"); } },
    { inspect: async () => ({ kind: "workspace", path: "/other" }), openWorkspace: async () => { throw new Error("open failed"); } },
  ]) {
    const h = harness(overrides); assert.equal(await h.handle(drop("/input")), false);
    assert.equal(h.store.getState().session.workspacePath, "/previous");
    assert.equal(h.store.getState().importer.entryResolving, false); assert.equal(h.notices.length, 1);
  }
});
test("overlay clears after leave and does not alter the project state", async () => {
  const h = harness(); const original = h.store.getState();
  await h.handle({ type: "enter", paths: ["/sample.zip"] }); await h.handle({ type: "leave" });
  assert.equal(h.store.getState(), original);
  assert.equal(h.calls.at(-1)[1], false);
});
test("entry-resolving prevents button-based work from racing a drop", () => {
  assert.equal(projectEntryBusy({ importer: { entryResolving: true } }), true);
  assert.equal(projectEntryBusy({ importer: { entryResolving: true } }, { includeResolving: false }), false);
});

test("choosing a new parent preserves the editable suggested-directory leaf", () => {
  assert.equal(relocateWorkspaceSuggestion("D:\\New Parent", "D:\\Deliveries\\sample_20261008_143025"), "D:/New Parent/sample_20261008_143025");
  assert.equal(relocateWorkspaceSuggestion("/new-parent/", "/deliveries/custom-name"), "/new-parent/custom-name");
});
