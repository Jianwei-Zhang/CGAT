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

function fixture({ enabled = true } = {}) {
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

test("enabled updater first checks at exactly three seconds after initialization", async () => {
  const f = fixture();
  await f.initialize();
  f.advance(2999);
  assert.deepEqual(f.checks, []);
  f.advance(1);
  assert.deepEqual(f.checks, [3000]);
  f.advance(7000);
  assert.deepEqual(f.checks, [3000], "the obsolete ten-second timer must not remain");
  assert.deepEqual(f.scheduled, [
    { delay: 3000, repeat: false },
    { delay: 6 * 60 * 60 * 1000, repeat: true },
    { delay: 30000, repeat: true },
  ]);
});

test("startup timers wait for initialization rather than application bootstrap", async () => {
  const f = fixture();
  f.advance(10000);
  assert.deepEqual(f.scheduled, []);
  await f.initialize();
  f.advance(2999);
  assert.deepEqual(f.checks, []);
  f.advance(1);
  assert.deepEqual(f.checks, [13000]);
});

test("disabled updater schedules neither startup nor recurring work", async () => {
  const f = fixture({ enabled: false });
  await f.initialize();
  f.advance(12 * 60 * 60 * 1000);
  assert.deepEqual(f.scheduled, []);
  assert.deepEqual(f.checks, []);
  assert.deepEqual(f.notices, []);
});

test("startup change preserves six-hour checks and thirty-second offer retries", async () => {
  const f = fixture();
  await f.initialize();
  f.advance(29999);
  assert.deepEqual(f.notices, []);
  f.advance(1);
  assert.deepEqual(f.notices, [30000]);
  f.advance(6 * 60 * 60 * 1000 - 30000);
  assert.deepEqual(f.checks, [3000, 21600000]);
  assert.equal(f.notices.length, 720);
  assert.equal(f.notices.at(-1), 21600000);
});
