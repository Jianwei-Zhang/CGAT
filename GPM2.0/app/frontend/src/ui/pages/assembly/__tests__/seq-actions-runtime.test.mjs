import test from "node:test";
import assert from "node:assert/strict";

import { bindSeqActions } from "../seq-actions-runtime.js";

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

test("bindSeqActions routes retained flip hide and end-type actions through injected editor runner", async () => {
  const flipButton = createButton();
  const hideShowButton = createButton();
  const setEndTypeButton = createButton();
  const removeSeqButton = createButton();
  const nodes = new Map([
    ["#flip-seq-button", flipButton],
    ["#hide-show-seq-button", hideShowButton],
    ["#set-seq-range-button", null],
    ["#set-end-type-button", setEndTypeButton],
    ["#remove-seq-from-ctg-button", removeSeqButton],
    ["#split-ctg-button", null],
    ["#set-join-type-button", null],
    ["#set-gap-size-button", null],
    ["#left-end-type-select", { value: "gap" }],
    ["#right-end-type-select", { value: "telomere" }],
  ]);
  const host = {
    querySelector(selector) {
      return nodes.get(selector) ?? null;
    },
  };
  const store = {
    getState() {
      return { assembly: {} };
    },
  };
  const member = { assemblySeqId: 12, hidden: false };
  const calls = [];

  bindSeqActions(host, store, {
    async applyEditorAction(_host, _store, payload) {
      calls.push(payload);
    },
    pickSelectedMember() {
      return member;
    },
  });

  await flipButton.click();
  await hideShowButton.click();
  await setEndTypeButton.click();
  await removeSeqButton.click();

  assert.deepEqual(calls, [
    {
      action: "flip-seq",
      args: { assemblySeqId: 12 },
      keepCurrentCtg: true,
    },
    {
      action: "hide-seq",
      args: { assemblySeqId: 12 },
      keepCurrentCtg: true,
    },
    {
      action: "set-end-type",
      args: {
        assemblySeqId: 12,
        leftEndType: "gap",
        rightEndType: "telomere",
      },
      keepCurrentCtg: true,
    },
  ]);
  assert.equal(removeSeqButton.hasListener("click"), false);
});
