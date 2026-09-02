import test from "node:test";
import assert from "node:assert/strict";

import { createProjectViewMutationCoordinator } from "../project-view-mutation-coordinator.js";

test("project-view mutation coordinator serializes writes and survives one failure", async () => {
  const coordinator = createProjectViewMutationCoordinator();
  const events = [];
  let releaseFirst;
  const first = coordinator.enqueue(async () => {
    events.push("first-start");
    await new Promise((resolve) => {
      releaseFirst = resolve;
    });
    events.push("first-end");
    throw new Error("expected test failure");
  });
  const second = coordinator.enqueue(async () => {
    events.push("second");
    return 2;
  });
  await Promise.resolve();
  assert.deepEqual(events, ["first-start"]);
  releaseFirst();
  await assert.rejects(first, /expected test failure/);
  assert.equal(await second, 2);
  assert.deepEqual(events, ["first-start", "first-end", "second"]);
});

test("invalidating the project-view coordinator skips queued stale work", async () => {
  const coordinator = createProjectViewMutationCoordinator();
  let releaseFirst;
  const first = coordinator.enqueue(async (isCurrent) => {
    await new Promise((resolve) => {
      releaseFirst = resolve;
    });
    return isCurrent();
  });
  let staleRan = false;
  const stale = coordinator.enqueue(async () => {
    staleRan = true;
  });
  await Promise.resolve();
  coordinator.invalidate();
  releaseFirst();
  assert.equal(await first, false);
  assert.deepEqual(await stale, { skipped: true });
  assert.equal(staleRan, false);
  assert.equal(await coordinator.enqueue(async () => "fresh"), "fresh");
});
