import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { bindLocalViewCloseSave } from "../local-view-close-save.js";

test("close waits for task persistence and concurrent close requests share one flush", async () => {
  let handler, resolve, calls = 0, prevented = 0;
  const unlisten = () => {};
  assert.equal(await bindLocalViewCloseSave({ windowHandle: { onCloseRequested(callback) { handler = callback; return unlisten; } },
    flush: () => { calls++; return new Promise(r => { resolve = r; }); } }), unlisten);
  let done = false;
  const first = handler({ preventDefault() { prevented++; } }).then(() => { done = true; });
  const second = handler({ preventDefault() { prevented++; } });
  await Promise.resolve(); assert.equal(calls, 1); assert.equal(done, false);
  resolve(); await Promise.all([first, second]); assert.equal(prevented, 0);
});

test("save failure prevents close, reports once, and a later close can retry", async () => {
  let handler, fail = true, errors = 0, prevented = 0;
  await bindLocalViewCloseSave({ windowHandle: { onCloseRequested(callback) { handler = callback; } },
    flush: async () => { if (fail) throw new Error("disk full"); }, onError: () => { errors++; } });
  const event = { preventDefault() { prevented++; } };
  await Promise.all([handler(event), handler(event)]);
  assert.equal(prevented, 2); assert.equal(errors, 1);
  fail = false; await handler(event); assert.equal(prevented, 2);
});

test("browser mode needs no native close listener and Tauri main can finish its deferred close", async () => {
  assert.equal(typeof await bindLocalViewCloseSave({ flush: async () => {} }), "function");
  const capability = JSON.parse(await readFile(new URL("../../../../../src-tauri/capabilities/default.json", import.meta.url), "utf8"));
  assert.deepEqual(capability.windows, ["main"]);
  assert.ok(capability.permissions.includes("core:window:allow-destroy"));
});
