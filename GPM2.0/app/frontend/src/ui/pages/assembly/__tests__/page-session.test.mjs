import test from "node:test";
import assert from "node:assert/strict";

import {
  assemblyPageSession,
  createAssemblyPageSession,
  resetAssemblyPageSession,
} from "../page-session.js";

test("assembly page sessions start with independent runtime state", () => {
  const first = createAssemblyPageSession();
  const second = createAssemblyPageSession();

  first.pendingAssemblyConfirmResolvers.set("dialog-1", () => {});
  first.measuredTrackViewportPxByRole.primary = 640;

  assert.equal(second.pendingAssemblyConfirmResolvers.size, 0);
  assert.equal(second.measuredTrackViewportPxByRole.primary, 1200);
});

test("resetAssemblyPageSession clears disposable state and restores defaults", () => {
  const clearedTimers = [];
  const resolved = [];
  const coordinatorCalls = [];
  assemblyPageSession.pendingAssemblyScrollStatePersistTimer = 91;
  assemblyPageSession.deferredRerenderCoordinator = {
    destroy() {
      coordinatorCalls.push("destroy");
    },
    cancel() {
      coordinatorCalls.push("cancel");
    },
  };
  assemblyPageSession.pendingAssemblyConfirmResolvers.set("dialog-1", (value) => resolved.push(value));
  assemblyPageSession.lastTrackViewportKey = "project-7";
  assemblyPageSession.trackContigDragActive = true;
  assemblyPageSession.finalPathGraphPreviewState = { previewSegmentOrder: ["seg-1"] };
  const previousSubviewRenderCache = assemblyPageSession.subviewRenderCache;
  assemblyPageSession.subviewRenderCache.segmentPairs.set("pair-1", [{ id: 1 }]);

  const widths = resetAssemblyPageSession(
    { primary: 720, subview: 480, finalPath: 0 },
    { timerApi: { clearTimeout: (timerId) => clearedTimers.push(timerId) } },
  );

  assert.deepEqual(clearedTimers, [91]);
  assert.deepEqual(coordinatorCalls, ["destroy", "cancel"]);
  assert.deepEqual(resolved, [false]);
  assert.equal(assemblyPageSession.pendingAssemblyConfirmResolvers.size, 0);
  assert.equal(assemblyPageSession.lastTrackViewportKey, "");
  assert.equal(assemblyPageSession.trackContigDragActive, false);
  assert.equal(assemblyPageSession.finalPathGraphPreviewState, null);
  assert.notEqual(assemblyPageSession.subviewRenderCache, previousSubviewRenderCache);
  assert.equal(assemblyPageSession.subviewRenderCache.segmentPairs.size, 0);
  assert.deepEqual(widths, { primary: 720, subview: 480, finalPath: 1200 });
});
