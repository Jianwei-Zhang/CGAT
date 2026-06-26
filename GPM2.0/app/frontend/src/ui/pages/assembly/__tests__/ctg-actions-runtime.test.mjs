import test from "node:test";
import assert from "node:assert/strict";

import { bindCtgActions } from "../ctg-actions-runtime.js";

function createButton() {
  const listeners = new Map();
  return {
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
    async click() {
      await listeners.get("click")?.();
    },
    hasListener(type) {
      return listeners.has(type);
    },
  };
}

test("bindCtgActions routes retained rename flip and delete actions through injected editor action runner", async () => {
  const renameButton = createButton();
  const flipButton = createButton();
  const deleteButton = createButton();
  const appendButton = createButton();
  const nodes = new Map([
    ["#rename-ctg-button", renameButton],
    ["#flip-ctg-button", flipButton],
    ["#delete-ctg-button", deleteButton],
    ["#append-ctg-button", appendButton],
    ["#rename-ctg-input", { value: "  renamed ctg  " }],
  ]);
  const host = {
    querySelector(selector) {
      return nodes.get(selector) ?? null;
    },
  };
  const store = {
    getState() {
      return {
        assembly: {
          selectedCtgId: 7,
        },
      };
    },
  };
  const calls = [];
  const confirms = [];

  bindCtgActions(host, store, {
    async applyEditorAction(_host, _store, payload) {
      calls.push(payload);
    },
    confirm(message) {
      confirms.push(message);
      return true;
    },
  });

  await renameButton.click();
  await flipButton.click();
  await deleteButton.click();
  await appendButton.click();

  assert.deepEqual(calls, [
    {
      action: "rename-ctg",
      args: {
        assemblyCtgId: 7,
        newName: "renamed ctg",
      },
      keepCurrentCtg: true,
    },
    {
      action: "flip-ctg",
      args: { assemblyCtgId: 7 },
      keepCurrentCtg: true,
      localRefresh: true,
    },
    {
      action: "delete-ctg",
      args: { assemblyCtgId: 7 },
      keepCurrentCtg: false,
    },
  ]);
  assert.deepEqual(confirms, ["确认删除 Ctg7 吗？"]);
  assert.equal(appendButton.hasListener("click"), false);
});

test("bindCtgActions waits for async delete confirmation", async () => {
  const deleteButton = createButton();
  const nodes = new Map([
    ["#delete-ctg-button", deleteButton],
  ]);
  const host = {
    querySelector(selector) {
      return nodes.get(selector) ?? null;
    },
  };
  const store = {
    getState() {
      return {
        assembly: {
          selectedCtgId: 7,
        },
      };
    },
  };
  const calls = [];
  let resolveConfirm = null;

  bindCtgActions(host, store, {
    async applyEditorAction(_host, _store, payload) {
      calls.push(payload);
    },
    confirm() {
      return new Promise((resolve) => {
        resolveConfirm = resolve;
      });
    },
  });

  const pending = deleteButton.click();
  await Promise.resolve();
  assert.deepEqual(calls, []);

  resolveConfirm(false);
  await pending;
  assert.deepEqual(calls, []);
});
