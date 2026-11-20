import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createNativeSubviewVisibility } from "../subview-native-visibility.js";

function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }
function fixture(overrides = {}) {
  const state = { minimized: true, current: true }, calls = [], errors = [];
  const handle = Object.fromEntries(["hide", "unminimize", "show"].map(name => [name, async () => { calls.push(name); await overrides[name]?.(); }]));
  const visibility = createNativeSubviewVisibility({ handle, isCurrent: () => state.current,
    isMinimized: () => state.minimized, onError: error => errors.push(error) });
  return { state, calls, errors, visibility };
}

test("minimizing hides the popup without entering OS minimized state; restore unminimizes and shows", async () => {
  const f = fixture();
  assert.equal(await f.visibility.sync(), true);
  await f.visibility.sync();
  assert.deepEqual(f.calls, ["hide"]);
  f.state.minimized = false; await f.visibility.sync();
  assert.deepEqual(f.calls, ["hide", "unminimize", "show"]);
});

test("restoring waits for an in-flight hide", async () => {
  const gate = deferred(), f = fixture({ hide: () => gate.promise });
  const hiding = f.visibility.sync(); await Promise.resolve();
  f.state.minimized = false; const restoring = f.visibility.sync();
  await Promise.resolve(); assert.deepEqual(f.calls, ["hide"]);
  gate.resolve(); await hiding; assert.equal(await restoring, true);
  assert.deepEqual(f.calls, ["hide", "unminimize", "show"]);
});

test("minimizing during an OS restore does not flash the popup", async () => {
  const gate = deferred(), f = fixture({ unminimize: () => gate.promise });
  f.state.minimized = false;
  const restoring = f.visibility.sync(); await Promise.resolve();
  f.state.minimized = true; const hiding = f.visibility.sync();
  gate.resolve(); assert.equal(await restoring, false); await hiding;
  assert.deepEqual(f.calls, ["unminimize", "hide"]);
});

test("rapid hide/restore/hide requests settle on the last task state", async () => {
  const f = fixture();
  const a = f.visibility.sync(); f.state.minimized = false; const b = f.visibility.sync();
  f.state.minimized = true; const c = f.visibility.sync();
  await Promise.all([a, b, c]); assert.deepEqual(f.calls, ["hide"]);
});

test("closing or switching projects fences a pending restore", async () => {
  const gate = deferred(), f = fixture({ unminimize: () => gate.promise });
  f.state.minimized = false; const restoring = f.visibility.sync(); await Promise.resolve();
  f.state.current = false; gate.resolve(); assert.equal(await restoring, false);
  assert.deepEqual(f.calls, ["unminimize"]);
});

test("native failure reports once rather than retrying on every store notification; explicit retry works", async () => {
  let fail = true;
  const f = fixture({ show: () => { if (fail) throw new Error("show failed"); } });
  f.state.minimized = false;
  assert.equal(await f.visibility.sync(), false); await f.visibility.sync();
  assert.equal(f.errors.length, 1); assert.deepEqual(f.calls, ["unminimize", "show"]);
  fail = false; assert.equal(await f.visibility.sync(true), true);
  assert.deepEqual(f.calls, ["unminimize", "show", "unminimize", "show"]);
});

test("task activation can restore an externally minimized window even if the cached task state is visible", async () => {
  const f = fixture(); f.state.minimized = false;
  await f.visibility.sync(); await f.visibility.sync(true);
  assert.deepEqual(f.calls, ["unminimize", "show", "unminimize", "show"]);
});

test("only Local windows receive hide permission and the manager no longer requests native minimization", () => {
  const capabilities = new URL("../../../../../../src-tauri/capabilities/", import.meta.url);
  const local = JSON.parse(readFileSync(new URL("local-view.json", capabilities)));
  const main = JSON.parse(readFileSync(new URL("default.json", capabilities)));
  assert.ok(local.permissions.includes("core:window:allow-hide"));
  assert.ok(!local.permissions.includes("core:window:allow-minimize"));
  assert.ok(!main.permissions.includes("core:window:allow-hide"));
  const manager = readFileSync(new URL("../subview-native-windows.js", import.meta.url), "utf8");
  assert.doesNotMatch(manager, /\.handle\.minimize\(/);
});
