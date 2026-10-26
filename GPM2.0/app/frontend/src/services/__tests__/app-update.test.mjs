import test from "node:test";
import assert from "node:assert/strict";
import { createAppUpdater, UPDATE_SNOOZE_KEY, UPDATE_SNOOZE_MS, updateWorkBusy } from "../app-update.js";

function fixture(overrides = {}) {
  const values = new Map();
  const calls = [], notices = [];
  let progress;
  const storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v) };
  const info = { enabled: true, currentVersion: "2.0.12", version: "2.0.13", ready: false };
  const updater = createAppUpdater({ storage, now: () => 1000,
    invoke: async (command, args) => { calls.push([command, args]); return command === "app_update_status" ? { ...info, version: null } : command === "app_update_check" ? info : "App notes"; },
    listen: async (_, fn) => { progress = fn; return () => {}; }, onOffer: () => notices.push(true), ...overrides });
  return { updater, calls, notices, storage, values, progress: payload => progress({ payload }) };
}
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

test("automatic check offers a newer version; manual bypasses persisted 24h suppression", async () => {
  const f = fixture(); await f.updater.initialize(); f.storage.setItem(UPDATE_SNOOZE_KEY, 2000);
  await f.updater.check(); assert.equal(f.notices.length, 0);
  await f.updater.check({ manual: true }); assert.equal(f.notices.length, 1);
  assert.equal(f.updater.dismiss(true), true); assert.equal(f.values.get(UPDATE_SNOOZE_KEY), String(1000 + UPDATE_SNOOZE_MS));
});
test("snooze expires at 24h exactly and survives controller recreation", async () => {
  let now = 1000; const f = fixture({ now: () => now }); await f.updater.initialize(); await f.updater.check(); f.updater.dismiss(true);
  const g = fixture({ storage: f.storage, now: () => now }); await g.updater.initialize(); await g.updater.check(); assert.equal(g.notices.length, 0);
  now += UPDATE_SNOOZE_MS; g.updater.notify(); assert.equal(g.notices.length, 1);
});
test("later suppresses only this session; manual view still works", async () => {
  const f = fixture(); await f.updater.initialize(); await f.updater.check(); f.updater.dismiss();
  f.updater.notify(); assert.equal(f.notices.length, 1); f.updater.notify(true); assert.equal(f.notices.length, 2);
});
test("busy/modal app defers automatic notification without losing the offer", async () => {
  let busy = true; const f = fixture({ canNotify: () => !busy }); await f.updater.initialize(); await f.updater.check();
  assert.equal(f.notices.length, 0); busy = false; f.updater.notify(); assert.equal(f.notices.length, 1);
});
test("failed snooze persistence does not pretend to close the reminder", async () => {
  const f = fixture({ storage: { getItem() {}, setItem() { throw Error(); } } });
  await f.updater.initialize(); await f.updater.check(); assert.equal(f.updater.dismiss(true), false);
  assert.equal(f.updater.getState().error, "update_storage");
});
test("download is deduplicated and progress cannot overwrite state after completion", async () => {
  const wait = deferred(); let downloads = 0;
  const f = fixture({ invoke: async command => {
    if (command === "app_update_download") { downloads++; return wait.promise; }
    return { enabled: true, version: "2.0.13", ready: false };
  } });
  await f.updater.initialize(); const p = f.updater.download(); await f.updater.download();
  f.progress({ downloaded: 5, total: 10, source: "docs" }); assert.equal(f.updater.getState().downloaded, 5);
  wait.resolve(); await p; assert.equal(downloads, 1); assert.equal(f.updater.getState().phase, "ready");
  f.progress({ downloaded: 1 }); assert.equal(f.updater.getState().downloaded, 5);
});
test("install waits for save and refuses to install after save failure", async () => {
  const f = fixture({ prepareInstall: async () => { throw Error("update_save_failed"); } });
  await f.updater.initialize(); await f.updater.check(); await f.updater.download(); await f.updater.install();
  assert.equal(f.updater.getState().phase, "ready"); assert.equal(f.updater.getState().error, "update_save_failed");
  assert.ok(!f.calls.some(([command]) => command === "app_update_install"));
});
test("install deduplicates and rechecks activity after flushing", async () => {
  let busy = false; const wait = deferred(); let installs = 0;
  const f = fixture({ isBusy: () => busy, prepareInstall: () => wait.promise,
    invoke: async command => { if (command === "app_update_install") installs++; return { enabled: true, ready: true, version: "2.0.13" }; } });
  await f.updater.initialize(); const p = f.updater.install(); await f.updater.install(); busy = true; wait.resolve(); await p;
  assert.equal(installs, 0); assert.equal(f.updater.getState().error, "update_work_busy");
});
test("successful install follows successful save", async () => {
  const order = []; const f = fixture({ prepareInstall: async () => order.push("save"),
    invoke: async command => { if (command === "app_update_install") order.push("install"); return { enabled: true, ready: true, version: "2.0.13" }; } });
  await f.updater.initialize(); await f.updater.install(); assert.deepEqual(order, ["save", "install"]);
});
test("failed auto check is silent and never shown as up to date", async () => {
  const f = fixture({ invoke: async command => { if (command === "app_update_check") throw "update_check_failed"; return { enabled: true }; } });
  await f.updater.initialize(); await f.updater.check(); assert.equal(f.updater.getState().phase, "error"); assert.equal(f.notices.length, 0);
});
test("only requested locale is fetched; no full bilingual note request", async () => {
  const f = fixture(); await f.updater.notes("en"); await f.updater.notes("zh");
  assert.deepEqual(f.calls, [["app_update_notes", { locale: "en" }], ["app_update_notes", { locale: "zh" }]]);
});
test("unconfigured builds and browser preview do not attempt network checks", async () => {
  const f = fixture({ invoke: async () => ({ enabled: false }) }); await f.updater.initialize(); await f.updater.check({ manual: true });
  assert.equal(f.updater.getState().phase, "unavailable"); assert.equal(f.notices.length, 0);
});
test("work guard covers imports, exports, mutations and native commands", () => {
  for (const state of [{ importer: { inFlight: true } }, { initializer: { autoPipelineRunning: true } },
    { assembly: { mainViewHistory: { inFlight: true } } }, { projectExport: { loading: true } }]) assert.equal(updateWorkBusy(state), true);
  assert.equal(updateWorkBusy({}, 1), true); assert.equal(updateWorkBusy({}), false);
});

test("checking without an offer shows latest, not an empty update dialog", async () => {
  const f = fixture({ invoke: async () => ({ enabled: true, currentVersion: "2.0.12", version: null }) });
  await f.updater.initialize(); await f.updater.check({ manual: true });
  assert.equal(f.updater.getState().phase, "latest"); assert.equal(f.notices.length, 0);
});
test("snooze applied from download/install action persists without closing the dialog", async () => {
  const f = fixture(); await f.updater.initialize(); await f.updater.check();
  assert.equal(f.updater.snooze(), true); assert.equal(f.values.get(UPDATE_SNOOZE_KEY), String(1000 + UPDATE_SNOOZE_MS));
  f.updater.notify(true); assert.equal(f.notices.length, 1);
});
test("snooze applies to all automatic version offers during the 24h interval", async () => {
  let version = "2.0.13";
  const f = fixture({ invoke: async () => ({ enabled: true, version }) });
  await f.updater.initialize(); await f.updater.check(); f.updater.dismiss(true);
  version = "2.0.14"; await f.updater.check(); assert.equal(f.notices.length, 1);
  assert.equal(f.updater.getState().version, "2.0.14");
});
test("a failed progress listener disables checks instead of pretending updates are usable", async () => {
  const f = fixture({ listen: async () => { throw Error("unavailable"); } });
  await f.updater.initialize(); await f.updater.check(); assert.equal(f.updater.getState().enabled, false);
});

test("24h reminders resume in the same long-running App session", async () => {
  let now = 1000; const f = fixture({ now: () => now });
  await f.updater.initialize(); await f.updater.check(); f.updater.dismiss(true);
  now += UPDATE_SNOOZE_MS - 1; f.updater.notify(); assert.equal(f.notices.length, 1);
  now++; f.updater.notify(); assert.equal(f.notices.length, 2);
});
