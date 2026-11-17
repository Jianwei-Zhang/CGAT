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


for (const discard of [false, true]) test(`failed save ${discard ? "can close only after explicit discard" : "keeps open when discard is cancelled"}`, async () => {
  let handler, resolve, prompts = 0, prevented = 0, finished = false;
  const error = new Error("failed to open workspace db: unable to open database file");
  await bindLocalViewCloseSave({ windowHandle: { onCloseRequested(callback) { handler = callback; } },
    flush: async () => { throw error; },
    confirmDiscard: received => {
      assert.equal(received, error); prompts++;
      return new Promise(r => { resolve = r; });
    } });
  const event = { preventDefault() { prevented++; } };
  const first = handler(event).then(() => { finished = true; });
  const second = handler(event);
  while (!resolve) await Promise.resolve();
  assert.equal(prompts, 1); assert.equal(finished, false);
  resolve(discard); await Promise.all([first, second]);
  assert.equal(prevented, discard ? 0 : 2);
});

test("failed or non-boolean discard decisions never close an unsaved project", async () => {
  for (const decision of [async () => { throw new Error("dialog unavailable"); }, async () => undefined, async () => "yes"]) {
    let handler, prevented = 0;
    await bindLocalViewCloseSave({ windowHandle: { onCloseRequested(callback) { handler = callback; } },
      flush: async () => { throw new Error("disk full"); }, confirmDiscard: decision });
    await handler({ preventDefault() { prevented++; } });
    assert.equal(prevented, 1);
  }
});

test("cancelled discard permits saving normally after the project is restored", async () => {
  let handler, missing = true, prompts = 0, prevented = 0;
  await bindLocalViewCloseSave({ windowHandle: { onCloseRequested(callback) { handler = callback; } },
    flush: async () => { if (missing) throw new Error("missing project"); },
    confirmDiscard: async () => { prompts++; return false; } });
  const event = { preventDefault() { prevented++; } };
  await handler(event); missing = false; await handler(event);
  assert.equal(prompts, 1); assert.equal(prevented, 1);
});

test("successful persistence never asks to discard", async () => {
  let handler;
  await bindLocalViewCloseSave({ windowHandle: { onCloseRequested(callback) { handler = callback; } },
    flush: async () => {}, confirmDiscard: () => assert.fail("unexpected discard dialog") });
  await handler({ preventDefault() { assert.fail("saved window should close"); } });
});
