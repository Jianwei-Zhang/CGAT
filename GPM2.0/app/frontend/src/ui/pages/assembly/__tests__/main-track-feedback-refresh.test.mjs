import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../../../state/store.js";
import {
  __testClearAssemblyActionFeedback,
  __testCreateActionFeedbackDismissCoordinator,
} from "../../assembly-page.js";

test("an old feedback timer cannot erase the new result or replace a main-track preview", () => {
  const store = createStore({ assembly: {
    actionStatus: "saving", actionError: "",
    trackDragOffsets: [{ trackRole: "primary", assemblyCtgId: 11, offsetBp: 120 }],
  } });
  let callback;
  let removed = 0;
  const host = { querySelector: () => ({ remove: () => { removed += 1; } }) };
  const rerender = () => assert.fail("toast dismissal must not replace the graph");
  const coordinator = __testCreateActionFeedbackDismissCoordinator({
    setTimeoutFn: (fn) => { callback = fn; return 1; }, clearTimeoutFn() {},
    onDismiss: (signature) => __testClearAssemblyActionFeedback(host, store, rerender, signature),
  });
  coordinator.onFeedbackChange("saving\u0000");
  store.setState({ assembly: { ...store.getState().assembly, actionStatus: "saved" } });
  callback();
  assert.equal(store.getState().assembly.actionStatus, "saved");
  assert.equal(removed, 0);
  coordinator.onFeedbackChange("saved\u0000");
  callback();
  assert.equal(removed, 1);
  assert.equal(store.getState().assembly.actionStatus, "");
  assert.deepEqual(store.getState().assembly.trackDragOffsets,
    [{ trackRole: "primary", assemblyCtgId: 11, offsetBp: 120 }]);
});
