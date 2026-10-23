import test from "node:test";
import assert from "node:assert/strict";
import { createAssemblyConfirmController } from "../confirm-controller.js";
import { confirmationSkipped } from "../../../shell/confirmation-session.js";
import { requestAppConfirm, requestAppPrompt } from "../../../shell/app-dialog.js";

const fixture = () => {
  let state = { locale: "zh", assembly: {} }, renders = 0;
  const store = { getState: () => state, setState: (patch) => { state = { ...state, ...patch }; } };
  const controller = createAssemblyConfirmController({ createOffsetSubviewManualAnchor() {}, escapeAttr: String, escapeHtml: String,
    getAssemblyI18n: () => ({ page: {} }), tAssembly: (_state, key) => key, rerender() { renders++; } });
  return { store, controller, renders: () => renders };
};
test("confirm opt-out is checked consent, per action, memory only; stale dialogs and cancellation cannot grant consent", async () => {
  const { store, controller: c, renders } = fixture(), host = {};
  const key = "test-sync-delete", options = { confirmationKey: key };
  let pending = c.requestAssemblyConfirm(host, store, "delete", options);
  let id = store.getState().assembly.confirmDialog.id;
  assert.match(c.renderAssemblyConfirmModal(store.getState()), /本次运行不再询问此类操作/);
  c.resolveAssemblyConfirmDialog(host, store, { id: "stale", confirmed: true, skipConfirmation: true });
  assert.equal(store.getState().assembly.confirmDialog.id, id);
  assert.equal(confirmationSkipped(key), false);
  c.resolveAssemblyConfirmDialog(host, store, { id, confirmed: false, skipConfirmation: true });
  assert.equal(await pending, false); assert.equal(confirmationSkipped(key), false);
  pending = c.requestAssemblyConfirm(host, store, "delete", options);
  id = store.getState().assembly.confirmDialog.id;
  c.resolveAssemblyConfirmDialog(host, store, { id, confirmed: true });
  assert.equal(await pending, true); assert.equal(confirmationSkipped(key), false);
  pending = c.requestAssemblyConfirm(host, store, "delete", options);
  id = store.getState().assembly.confirmDialog.id;
  c.resolveAssemblyConfirmDialog(host, store, { id, confirmed: true, skipConfirmation: true });
  assert.equal(await pending, true); assert.equal(confirmationSkipped(key), true);
  const count = renders();
  assert.equal(await c.requestAssemblyConfirm(host, store, "delete another", options), true);
  assert.equal(renders(), count);
  // Generic app dialogs share the same consent, but prompts are never bypassed.
  assert.equal(await requestAppConfirm("delete", options), true);
  assert.equal(await requestAppPrompt("typed input", "", options), null);
  pending = c.requestAssemblyConfirm(host, store, "split", { confirmationKey: "test-sync-split" });
  assert.ok(store.getState().assembly.confirmDialog);
  c.resolveAssemblyConfirmDialog(host, store, { confirmed: false }); await pending;
  const freshSession = await import("../../../shell/confirmation-session.js?new-process-fixture");
  assert.equal(freshSession.confirmationSkipped(key), false);
});
test("confirmations without an explicit action key cannot be skipped", async () => {
  const { store, controller: c } = fixture();
  const pending = c.requestAssemblyConfirm({}, store, "one-off");
  assert.doesNotMatch(c.renderAssemblyConfirmModal(store.getState()), /data-assembly-confirm-skip/);
  c.resolveAssemblyConfirmDialog({}, store, { confirmed: true, skipConfirmation: true });
  assert.equal(await pending, true);
});

test("generic confirmation checkbox is unchecked initially and remembers only a checked submit", async () => {
  const previous = globalThis.document, nodes = [];
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.events = {}; this.checked = false; nodes.push(this); }
    append(...children) { this.children.push(...children); }
    setAttribute() {} addEventListener(name, fn) { this.events[name] = fn; }
    focus() {} select() {} remove() {} showModal() { this.open = true; } close() { this.open = false; this.events.close?.(); }
  }
  globalThis.document = { body: new Element("body"), createElement: (tag) => new Element(tag), createTextNode: (text) => text, querySelector() {} };
  try {
    const key = "test-generic-submit";
    let pending = requestAppConfirm("Delete", { confirmationKey: key });
    let checkbox = nodes.findLast((node) => node.type === "checkbox");
    assert.equal(checkbox.checked, false);
    checkbox.checked = true;
    nodes.findLast((node) => node.dataset.appDialogAction === "cancel").events.click();
    assert.equal(await pending, false); assert.equal(confirmationSkipped(key), false);
    pending = requestAppConfirm("Delete", { confirmationKey: key });
    checkbox = nodes.findLast((node) => node.type === "checkbox"); checkbox.checked = true;
    nodes.findLast((node) => node.tag === "form").events.submit({ preventDefault() {} });
    assert.equal(await pending, true); assert.equal(confirmationSkipped(key), true);
  } finally { globalThis.document = previous; }
});
