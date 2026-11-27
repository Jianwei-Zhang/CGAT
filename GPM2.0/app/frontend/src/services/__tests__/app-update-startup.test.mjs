import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

// Execute the actual bootstrap schedule, not a duplicated scheduler. Importing
// main.js itself would also initialize the complete DOM/native application.
const mainSource = readFileSync(new URL("../../main.js", import.meta.url), "utf8");
const start = mainSource.indexOf("void updater.initialize().then(() => {");
assert.notEqual(start, -1);
const end = mainSource.indexOf("\n});", start);
assert.notEqual(end, -1);
const startupSource = mainSource.slice(start, end + "\n});".length);

function fixture({ enabled = true, autoCheckUpdates = true } = {}) {
  let now = 0;
  let nextId = 0;
  let finishInitialization;
  const initialized = new Promise(resolve => { finishInitialization = resolve; });
  const pending = new Map();
  const scheduled = [];
  const checks = [];
  const notices = [];
  const schedule = (callback, delay, repeat) => {
    scheduled.push({ delay, repeat });
    pending.set(++nextId, { callback, due: now + delay, repeat, delay });
    return nextId;
  };
  const updater = {
    initialize: () => initialized,
    getState: () => ({ enabled }),
    check: () => { checks.push(now); return Promise.resolve(); },
    notify: () => { notices.push(now); },
  };
  runInNewContext(startupSource, {
    updater,
    getAppSettings: () => ({ autoCheckUpdates }),
    setTimeout: (callback, delay) => schedule(callback, delay, false),
    setInterval: (callback, delay) => schedule(callback, delay, true),
  });
  return {
    checks, notices, scheduled,
    async initialize() {
      finishInitialization();
      await initialized;
      await Promise.resolve();
    },
    advance(ms) {
      const target = now + ms;
      for (;;) {
        const entry = [...pending.entries()]
          .filter(([, timer]) => timer.due <= target)
          .sort((a, b) => a[1].due - b[1].due)[0];
        if (!entry) break;
        const [id, timer] = entry;
        now = timer.due;
        if (timer.repeat) timer.due += timer.delay;
        else pending.delete(id);
        timer.callback();
      }
      now = target;
    },
  };
}

test("enabled updater checks immediately once after initialization, with no delayed or periodic checks", async () => {
  const f = fixture();
  await f.initialize();
  assert.deepEqual(f.checks, [0]);
  f.advance(3000);
  assert.deepEqual(f.checks, [0], "no three-second check should remain");
  f.advance(7000);
  assert.deepEqual(f.checks, [0], "no older ten-second check should remain");
  assert.deepEqual(f.scheduled, [{ delay: 30000, repeat: true }]);
});

test("startup check waits only for initialization, not an additional timer", async () => {
  const f = fixture();
  f.advance(10000);
  assert.deepEqual(f.scheduled, []);
  assert.deepEqual(f.checks, []);
  await f.initialize();
  assert.deepEqual(f.checks, [10000]);
  f.advance(3000);
  assert.deepEqual(f.checks, [10000]);
});

test("disabled updater schedules neither startup nor recurring work", async () => {
  const f = fixture({ enabled: false });
  await f.initialize();
  f.advance(12 * 60 * 60 * 1000);
  assert.deepEqual(f.scheduled, []);
  assert.deepEqual(f.checks, []);
  assert.deepEqual(f.notices, []);
});

test("thirty-second offer retries do not perform another update check, even after six hours", async () => {
  const f = fixture();
  await f.initialize();
  f.advance(29999);
  assert.deepEqual(f.notices, []);
  f.advance(1);
  assert.deepEqual(f.notices, [30000]);
  f.advance(12 * 60 * 60 * 1000 - 30000);
  assert.deepEqual(f.checks, [0]);
  assert.equal(f.notices.length, 1440);
  assert.equal(f.notices.at(-1), 43200000);
});

test("autoCheckUpdates=false skips automatic startup check without disabling manual checks", async () => {
  const f = fixture({ autoCheckUpdates: false });
  await f.initialize();
  assert.deepEqual(f.checks, []);
  f.advance(60000);
  assert.deepEqual(f.checks, []);
});
