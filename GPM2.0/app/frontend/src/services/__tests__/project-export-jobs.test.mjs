import test from "node:test";
import assert from "node:assert/strict";
import { createStore } from "../../state/store.js";
import { updateWorkBusy } from "../app-update.js";
import { exportJobScope, currentProjectExportJob, beginProjectExportJob, ownsCurrentProjectExport,
  updateProjectExportJob, syncCurrentProjectExportJob, finishProjectExportJob, hasRunningProjectExports } from "../project-export-jobs.js";
const state = (workspacePath = "/a", projectId = 7) => ({ session: { workspacePath, projectId }, projectExport: { job: null } });
const job = name => ({ status: "running", projectName: name, completedOutputs: [], cancelRequested: false });

test("background exports retain project ownership and keep the updater busy after switching projects", () => {
  const store = createStore(state()), a = beginProjectExportJob(store, store.getState(), job("A"));
  let b;
  try {
    assert.equal(ownsCurrentProjectExport(store, a), true);
    assert.equal(beginProjectExportJob(store, store.getState(), job("duplicate")), null);
    store.setState(state("/b")); assert.equal(currentProjectExportJob(store), null);
    assert.equal(ownsCurrentProjectExport(store, a), false);
    assert.equal(updateWorkBusy(store.getState()), true);
    b = beginProjectExportJob(store, store.getState(), job("B"));
    updateProjectExportJob(a, { ...a.job, status: "success", completedOutputs: ["/exports/A.tsv"] });
    finishProjectExportJob(store, a);
    assert.equal(hasRunningProjectExports(), true, "B is still running");
    assert.equal(currentProjectExportJob(store).projectName, "B");
    store.setState(state());
    assert.equal(currentProjectExportJob(store).status, "success");
    assert.deepEqual(currentProjectExportJob(store).completedOutputs, ["/exports/A.tsv"]);
    syncCurrentProjectExportJob(store, null); assert.equal(currentProjectExportJob(store), null);
  } finally {
    updateProjectExportJob(a, { ...a.job, status: "success" }); finishProjectExportJob(store, a);
    if (b) { updateProjectExportJob(b, { ...b.job, status: "success" }); finishProjectExportJob(store, b); }
  }
  assert.equal(hasRunningProjectExports(), false); assert.equal(updateWorkBusy({}), false);
});

test("cancellation survives route/project departure and another workspace with the same numeric ID cannot own it", () => {
  const store = createStore(state()), owner = beginProjectExportJob(store, store.getState(), job("A"));
  try {
    syncCurrentProjectExportJob(store, { ...owner.job, cancelRequested: true });
    store.setState(state("/other", 7));
    assert.equal(ownsCurrentProjectExport(store, owner), false); assert.equal(currentProjectExportJob(store), null);
    assert.equal(owner.job.cancelRequested, true);
    store.setState(state()); assert.equal(currentProjectExportJob(store).cancelRequested, true);
    assert.notEqual(exportJobScope(state()), exportJobScope(state("/other")));
  } finally { updateProjectExportJob(owner, { ...owner.job, status: "canceled" }); finishProjectExportJob(store, owner); }
});

test("completed-job retention is bounded without dropping running jobs", () => {
  const store = createStore(state()), active = beginProjectExportJob(store, store.getState(), job("active"));
  try {
    for (let id = 1; id <= 6; id++) {
      store.setState(state("/completed", id));
      const owner = beginProjectExportJob(store, store.getState(), job(String(id)));
      updateProjectExportJob(owner, { ...owner.job, status: "success" }); finishProjectExportJob(store, owner);
    }
    store.setState(state("/completed", 1)); assert.equal(currentProjectExportJob(store), null);
    store.setState(state("/completed", 6)); assert.equal(currentProjectExportJob(store).status, "success");
    store.setState(state()); assert.equal(currentProjectExportJob(store), active.job);
  } finally { updateProjectExportJob(active, { ...active.job, status: "success" }); finishProjectExportJob(store, active); }
});

test("unacknowledged errors/results are never evicted when more than three projects finish", () => {
  const store = createStore(state());
  for (let id = 1; id <= 4; id++) {
    store.setState(state("/unack", id));
    const owner = beginProjectExportJob(store, store.getState(), { ...job(String(id)), open: true });
    updateProjectExportJob(owner, { ...owner.job, status: id === 1 ? "error" : "success", error: id === 1 ? "write failed" : "", completedOutputs: [`/output/${id}.tsv`] });
    finishProjectExportJob(store, owner);
  }
  for (let id = 1; id <= 4; id++) {
    store.setState(state("/unack", id));
    assert.equal(currentProjectExportJob(store).projectName, String(id));
    assert.deepEqual(currentProjectExportJob(store).completedOutputs, [`/output/${id}.tsv`]);
  }
  store.setState(state("/unack", 1)); assert.equal(currentProjectExportJob(store).error, "write failed");
  syncCurrentProjectExportJob(store, null); assert.equal(currentProjectExportJob(store), null);
  assert.equal(hasRunningProjectExports(), false);
});
