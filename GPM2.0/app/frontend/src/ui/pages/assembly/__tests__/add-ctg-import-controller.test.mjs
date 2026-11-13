import test from "node:test";
import assert from "node:assert/strict";

import { createAddCtgImportController } from "../add-ctg-import-controller.js";

function createStore(initialState) {
  let state = initialState;
  return {
    getState() {
      return state;
    },
    setState(nextState) {
      state = {
        ...state,
        ...nextState,
      };
    },
  };
}

function createInitialState() {
  return {
    locale: "en",
    session: {
      workspacePath: "D:/workspace/demo",
      projectId: 7,
    },
    initializer: {
      datasets: [],
      existingProjects: [],
      references: [],
    },
    assembly: {
      selectedChrName: "Chr01",
      actionStatus: "",
      actionError: "",
      addCtgImportProgress: null,
    },
  };
}

test("add-ctg import picker cancellation leaves state unchanged", async () => {
  const initialState = createInitialState();
  const store = createStore(initialState);
  let importCalls = 0;
  let rerenderCalls = 0;
  const controller = createAddCtgImportController({
    async importAddCtgPackage() {
      importCalls += 1;
    },
    mapAssemblyError() {
      throw new Error("error mapping should not run");
    },
    async pickZipFilePath() {
      return "";
    },
    rerender() {
      rerenderCalls += 1;
    },
    async selectChromosome() {
      throw new Error("chromosome refresh should not run");
    },
  });

  await controller.importAddCtgIntoTrack({}, store, {
    targetChr: "Chr01",
    targetTrack: "hifiasm-hap1",
  });

  assert.equal(importCalls, 0);
  assert.equal(rerenderCalls, 0);
  assert.deepEqual(store.getState(), initialState);
});

test("add-ctg import forwards target identity and merges successful refresh data", async () => {
  const store = createStore(createInitialState());
  const calls = [];
  const refreshedChromosomes = [];
  let rerenderCalls = 0;
  const controller = createAddCtgImportController({
    async importAddCtgPackage(payload) {
      calls.push(payload);
      payload.onStage("backend stage");
      return {
        message: "imported",
        ctgName: "ptg0001l",
        datasets: [{ datasetId: 11, name: "hifiasm" }],
        existingProjects: [{ projectId: 7 }],
        references: [{ referenceId: 3 }],
        packageMetadata: { hasDatasetFasta: true },
      };
    },
    mapAssemblyError({ error }) {
      return { userMessage: String(error?.message || error) };
    },
    async pickZipFilePath() {
      return "D:/packages/add_ctg.zip";
    },
    rerender() {
      rerenderCalls += 1;
    },
    async selectChromosome(_host, _store, chrName) {
      refreshedChromosomes.push(chrName);
    },
  });

  await controller.importAddCtgIntoTrack({}, store, {
    targetChr: "Chr02",
    targetTrack: "hifiasm-hap2",
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].workspaceRoot, "D:/workspace/demo");
  assert.equal(calls[0].projectId, 7);
  assert.equal(calls[0].zipPath, "D:/packages/add_ctg.zip");
  assert.equal(calls[0].expectedTargetChr, "Chr02");
  assert.equal(calls[0].expectedTargetTrack, "hifiasm-hap2");
  assert.match(calls[0].runId, /^add-ctg-/);
  assert.deepEqual(refreshedChromosomes, ["Chr02"]);
  assert.equal(store.getState().assembly.addCtgImportProgress.status, "success");
  assert.equal(store.getState().assembly.addCtgImportProgress.summary, "imported");
  assert.ok(store.getState().assembly.addCtgImportProgress.stages.includes("backend stage"));
  assert.deepEqual(store.getState().initializer.datasets, [{ datasetId: 11, name: "hifiasm" }]);
  assert.deepEqual(store.getState().initializer.packageMetadata, { hasDatasetFasta: true });
  assert.equal(store.getState().assembly.actionError, "");
  assert.ok(rerenderCalls >= 3);
});


test("DEGAP batch import uses receipt targets and associates only matching jobs", async () => {
  const initial = createInitialState();
  initial.assembly.degap = { jobs: [
    { jobId: "gap", chrName: "Chr02" }, { jobId: "gap", chrName: "Chr03" },
  ] };
  initial.assembly.finalPath = { segments: ["unchanged"] };
  const store = createStore(initial);
  const calls = [];
  const controller = createAddCtgImportController({
    async importAddCtgPackage(payload) {
      calls.push(payload);
      return { targetChr: "Chr02", degapResults: [{ jobId: "gap", chrName: "Chr02", token: "abc", ctgName: "candidate" }] };
    },
    mapAssemblyError: ({ error }) => ({ userMessage: String(error) }),
    async pickZipFilePath() { return "D:/degap_results.zip"; },
    rerender() {},
    async selectChromosome(_host, _store, name) { assert.equal(name, "Chr02"); },
  });
  await controller.importAddCtgIntoTrack({}, store, { degapResults: true });
  assert.equal(calls[0].expectedTargetChr, "");
  assert.equal(calls[0].expectedTargetTrack, "");
  assert.equal(store.getState().assembly.degap.jobs[0].importedResults.length, 1);
  assert.equal(store.getState().assembly.degap.jobs[1].importedResults.length, 0);
  assert.deepEqual(store.getState().assembly.finalPath, { segments: ["unchanged"] });
  assert.equal(calls[0].degapResultsOnly, true);
  assert.equal(store.getState().assembly.addCtgImportProgress.status, "success");
});
