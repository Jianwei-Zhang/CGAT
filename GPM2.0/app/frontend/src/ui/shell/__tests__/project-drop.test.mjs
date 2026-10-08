import test from "node:test";
import assert from "node:assert/strict";
import { bindProjectDrop } from "../project-drop.js";

function node(tag, doc) {
  return { tag, ownerDocument: doc, children: [], hidden: false, attrs: {},
    append(...children) { this.children.push(...children); }, setAttribute(key, value) { this.attrs[key] = value; },
    remove() { this.removed = true; }, querySelector() { return null; } };
}
test("the desktop binder subscribes to Tauri native paths, controls the overlay, and cleans up", async () => {
  const originalWindow = globalThis.window;
  const calls = []; const docEvents = new Map(); const windowEvents = new Map();
  const doc = { createElement: tag => node(tag, doc), querySelector: () => null,
    addEventListener: (key, value) => docEvents.set(key, value), removeEventListener: key => docEvents.delete(key) };
  doc.body = node("body", doc);
  const root = node("app", doc);
  let callback; let unlistened = false;
  let state = { locale: "en", activeRoute: "importer", session: {}, importer: {}, initializer: {} };
  const store = { getState: () => state, setState: patch => { state = { ...state, ...patch }; } };
  globalThis.window = {
    __TAURI__: { core: { invoke: async (command, args) => {
      calls.push([command, args]);
      assert.equal(command, "inspect_project_entry");
      return { kind: "archive", path: args.entryPath, suggestedWorkspace: "D:\\deliveries\\sample_20261008_143025" };
    } }, webviewWindow: { getCurrentWebviewWindow: () => ({ onDragDropEvent: async handler => {
      callback = handler; return () => { unlistened = true; };
    } }) } },
    dispatchEvent: event => calls.push(["event", event.type]),
    addEventListener: (key, value) => windowEvents.set(key, value), removeEventListener: key => windowEvents.delete(key),
  };
  try {
    const cleanup = await bindProjectDrop(root, store);
    const layer = doc.body.children[0]; assert.equal(layer.hidden, true);
    await callback({ payload: { type: "enter", paths: ["D:\\deliveries\\sample.tar.gz"] } });
    assert.equal(layer.hidden, false); assert.equal(layer.attrs.role, "status");
    await callback({ payload: { type: "leave" } }); assert.equal(layer.hidden, true);
    let prevented = false;
    docEvents.get("drop")({ dataTransfer: { types: ["Files"] }, preventDefault: () => { prevented = true; } });
    assert.equal(prevented, true); assert.equal(calls.length, 0);
    await callback({ payload: { type: "drop", paths: ["D:\\deliveries\\sample.tar.gz"] } });
    assert.equal(calls[0][1].entryPath, "D:\\deliveries\\sample.tar.gz");
    assert.match(calls[0][1].timestamp, /^\d{8}_\d{6}$/);
    assert.equal(state.importer.zipPath, "D:\\deliveries\\sample.tar.gz");
    assert.equal(state.importer.requireNewWorkspace, true); assert.equal(layer.hidden, true);
    assert.equal(calls.filter(row => row[0] === "inspect_project_entry").length, 1);
    cleanup(); assert.equal(unlistened, true); assert.equal(layer.removed, true);
    assert.equal(docEvents.size, 0); assert.equal(windowEvents.size, 0);
  } finally { globalThis.window = originalWindow; }
});
